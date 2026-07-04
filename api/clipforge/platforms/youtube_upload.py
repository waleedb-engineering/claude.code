"""YouTube Private Upload — erster echter Uploadpfad (Phase 3, PRIVATE-only).

Was dieses Modul tut:
  - Lädt einen validierten YouTube-Draft nach **expliziter Bestätigung** als
    **privates** Video über die offizielle YouTube Data API v3 hoch
    (`videos.insert`, resumable), mit Token-Refresh, Idempotenz und sicheren
    Statusübergängen.

Was dieses Modul bewusst NICHT tut:
  - KEIN public/unlisted Upload, KEIN Auto-Posting, KEIN Scheduling.
  - KEIN Upload ohne Feature-Flag + gültiges Token + exakte Bestätigung.
  - KEIN Fake-Erfolg: `published`/`external_post_id` NUR bei eindeutigem
    API-Erfolg (`'id'` in der Antwort).
  - KEIN Token/Secret in Rückgaben, Logs oder Exceptions.

Sicherheits-/Robustheits-Invarianten:
  - Netzwerkabbruch nach möglichem Remote-Erfolg → `uncertain` (blockiert
    blindes Retry), NICHT einfach `failed`.
  - Doppelter Upload ausgeschlossen (external_post_id / succeeded / in_progress
    / uncertain blockieren).
  - Die Google-Interaktion (Credentials-Refresh + Upload) ist **injizierbar**;
    in Tests wird sie gemockt — NIE ein echter Google-Call.

Quellen (offizielle Doku, abgerufen 2026-07-03):
  https://developers.google.com/youtube/v3/guides/uploading_a_video
  - `youtube.videos().insert(part="snippet,status", body={...},
    media_body=MediaFileUpload(file, chunksize=-1, resumable=True))`
  - Resumable-Loop: `status, response = request.next_chunk()`, Erfolg wenn
    `'id' in response`.
  - Retriable-Status: `[500, 502, 503, 504]`; Exponential-Backoff mit Jitter.
  - Library: `google-api-python-client` (`googleapiclient.discovery.build`,
    `googleapiclient.http.MediaFileUpload`).
  https://developers.google.com/youtube/v3/docs/videos/insert  (Fehler/Quota)
"""

from __future__ import annotations

import os

from ..config import Settings
from ..publishing import (
    apply_publish_state,
    build_validation_summary,
    load_draft,
    publishing_dir,
)
from . import youtube_state as ystate
from .youtube_auth import REQUIRED_SCOPE, YouTubeTokenStore
from .youtube_oauth import (
    GOOGLE_TOKEN_ENDPOINT,
    YouTubeOAuthConfig,
    sanitize_token_payload,
)

# --------------------------------------------------------------------------
# Stabile interne Fehlercodes (nie rohe Google-Exceptions nach außen)
# --------------------------------------------------------------------------

UPLOAD_DISABLED = "upload_disabled"
OAUTH_NOT_READY = "oauth_not_ready"
TOKEN_MISSING = "token_missing"
REAUTH_REQUIRED = "reauth_required"
TOKEN_REFRESH_FAILED = "token_refresh_failed"
UPLOAD_DEPENDENCY_MISSING = "upload_dependency_missing"
INVALID_DRAFT = "invalid_draft"
MP4_MISSING = "mp4_missing"
ALREADY_UPLOADED = "already_uploaded"
UPLOAD_IN_PROGRESS = "upload_in_progress"
UPLOAD_STATE_UNCERTAIN = "upload_state_uncertain"
INVALID_PRIVACY = "invalid_privacy_status"
CONFIRMATION_REQUIRED = "confirmation_required"
QUOTA_EXCEEDED = "quota_exceeded"
RATE_LIMITED = "rate_limited"
PERMISSION_DENIED = "permission_denied"
INVALID_CREDENTIALS = "invalid_credentials"
UPLOAD_FAILED = "upload_failed"
UPLOAD_RESULT_UNCERTAIN = "upload_result_uncertain"

# Nur PRIVATE ist in dieser Phase erlaubt.
ALLOWED_PRIVACY = "private"
CONFIRM_PRIVATE = "UPLOAD_PRIVATE"

# Offiziell dokumentierte Retriable-HTTP-Status (Resumable-Upload-Guide).
RETRIABLE_STATUS_CODES = (500, 502, 503, 504)

TITLE_MAX = 100  # offiziell dokumentiertes Titel-Limit


# --------------------------------------------------------------------------
# Idempotenz
# --------------------------------------------------------------------------

IDEMPOTENCY_STATES = (
    "never_attempted", "in_progress", "succeeded", "failed", "uncertain",
)


def derive_idempotency_state(draft: dict) -> str:
    """Leitet den Idempotenz-Zustand ab. Explizites `idempotency_state` gewinnt;
    sonst wird aus Legacy-Feldern (external_post_id/status) rekonstruiert."""
    state = draft.get("idempotency_state")
    if state in IDEMPOTENCY_STATES:
        return state
    if draft.get("external_post_id"):
        return "succeeded"
    status = draft.get("status")
    if status == "published":
        return "succeeded"
    if status == "publishing":
        return "in_progress"
    if status == "failed":
        return "failed"
    return "never_attempted"


# Fehler-Kategorie (persistiert als `last_error_category`, kein Secret).
_AUTH_CODES = frozenset({REAUTH_REQUIRED, INVALID_CREDENTIALS, TOKEN_MISSING,
                         TOKEN_REFRESH_FAILED})
_UNCERTAIN_CODES = frozenset({UPLOAD_RESULT_UNCERTAIN, UPLOAD_STATE_UNCERTAIN})
_RETRYABLE_CODES = frozenset({RATE_LIMITED})


def error_category(code: str | None) -> str | None:
    if code is None:
        return None
    if code in _AUTH_CODES:
        return "auth"
    if code in _UNCERTAIN_CODES:
        return "uncertain"
    if code in _RETRYABLE_CODES:
        return "retryable"
    return "non_retryable"


# --------------------------------------------------------------------------
# Injizierbare Fehlersignale (Refresh/Upload)
# --------------------------------------------------------------------------

class UploadError(Exception):
    """Basis. `code` ist ein stabiler, sicherer Fehlercode (kein Secret)."""

    code = UPLOAD_FAILED

    def __init__(self, code: str | None = None):
        self.code = code or self.code
        super().__init__(self.code)


class ReauthRequired(UploadError):
    code = REAUTH_REQUIRED


class TokenRefreshFailed(UploadError):
    code = TOKEN_REFRESH_FAILED


class UploadDependencyMissing(UploadError):
    code = UPLOAD_DEPENDENCY_MISSING


class UploadUncertain(UploadError):
    """Remote-Ergebnis ist unklar (z. B. Netzwerkabbruch nach möglichem
    Erfolg). Muss als `uncertain` behandelt werden, nicht als `failed`."""

    code = UPLOAD_RESULT_UNCERTAIN


# --------------------------------------------------------------------------
# Default-Google-Implementierungen (defensiv importiert; nie in Tests genutzt)
# --------------------------------------------------------------------------

def _default_credentials_loader(config: YouTubeOAuthConfig, payload: dict,
                                client_secret: str | None):
    """Rekonstruiert google.oauth2.credentials.Credentials aus der (sanitisierten)
    Token-Payload. Der `client_secret` kommt frisch aus der Secrets-Datei
    (nur für den Refresh nötig) — wird NIE geloggt/gespeichert."""
    try:
        from google.oauth2.credentials import Credentials  # type: ignore
    except Exception:  # noqa: BLE001
        raise UploadDependencyMissing()
    expiry = None
    exp = payload.get("expiry")
    if isinstance(exp, str) and exp:
        try:
            import datetime
            expiry = datetime.datetime.fromisoformat(exp.replace("Z", "+00:00"))
            if expiry.tzinfo is not None:
                expiry = expiry.astimezone(datetime.timezone.utc).replace(tzinfo=None)
        except ValueError:
            expiry = None
    creds = Credentials(
        token=payload.get("access_token"),
        refresh_token=payload.get("refresh_token"),
        token_uri=payload.get("token_uri") or GOOGLE_TOKEN_ENDPOINT,
        client_id=payload.get("client_id"),
        client_secret=client_secret,
        scopes=payload.get("scopes") or [REQUIRED_SCOPE],
    )
    if expiry is not None:
        creds.expiry = expiry
    return creds


def _default_refresher(creds) -> None:
    """Refresht Credentials über den offiziellen google-auth-Mechanismus."""
    try:
        from google.auth.transport.requests import Request  # type: ignore
    except Exception:  # noqa: BLE001
        raise UploadDependencyMissing()
    creds.refresh(Request())


def _default_session_factory(creds, body: dict, media_path: str, chunk_bytes: int = -1):
    """Baut eine **resumable Upload-Session** (google-api-python-client). Das
    zurückgegebene Request-Objekt hat `next_chunk() -> (status, response)` und
    verwaltet den Session-URI + Offset intern (Recovery bei retriablen Fehlern
    passiert durch erneuten `next_chunk()`-Aufruf auf DEMSELBEN Objekt)."""
    try:
        from googleapiclient.discovery import build  # type: ignore
        from googleapiclient.http import MediaFileUpload  # type: ignore
    except Exception:  # noqa: BLE001
        raise UploadDependencyMissing()
    youtube = build("youtube", "v3", credentials=creds, cache_discovery=False)
    media = MediaFileUpload(media_path, chunksize=chunk_bytes, resumable=True)
    return youtube.videos().insert(part="snippet,status", body=body,
                                   media_body=media)


class _LegacyUploaderSession:
    """Adapter, der einen alten `uploader(creds, body, media) -> dict` als
    Session mit `next_chunk()` verpackt (Rückwärtskompatibilität für Prompt 27
    und den app-Seam `_youtube_upload_uploader`)."""

    def __init__(self, uploader, creds, body, media_path):
        self._uploader = uploader
        self._creds = creds
        self._body = body
        self._media_path = media_path

    def next_chunk(self):
        # Ein „Chunk" = ein vollständiger Uploadversuch; Fehler propagieren.
        return None, self._uploader(self._creds, self._body, self._media_path)


# --------------------------------------------------------------------------
# Retry Policy (kontrolliert, testbar; keine echten sleeps in Unit-Tests)
# --------------------------------------------------------------------------

# Retry-Kategorien.
RETRYABLE = "retryable"
NON_RETRYABLE = "non_retryable"
AUTH_REFRESHABLE = "auth_refreshable"
UNCERTAIN = "uncertain"


class YouTubeRetryPolicy:
    """Zentrale, dokumentierte Retry-/Backoff-Policy.

    Kategorien: `retryable` · `non_retryable` · `auth_refreshable` · `uncertain`.
    `sleep_fn`/`jitter_fn` sind injizierbar → Unit-Tests schlafen NIE real und
    haben deterministischen Jitter.

    Quellen (offiziell, abgerufen 2026-07-03):
      - Retriable HTTP: `[500, 502, 503, 504]` + Netzwerk-Exceptions,
        Exponential-Backoff mit Jitter (Resumable-Upload-Guide, Prompt 27).
      - `quotaExceeded (403)` = Kontingent erschöpft → **nicht** aggressiv
        wiederholen; `badRequest (400)`/`forbidden (403)`/`notFound (404)` =
        permanent (docs/errors). `rateLimitExceeded`/`429` → retriable mit
        Backoff (Policy; nicht explizit in der Fehler-Referenz → TODO-verifiziert).
    """

    def __init__(self, *, max_attempts: int = 5, initial_delay_seconds: float = 1.0,
                 max_delay_seconds: float = 32.0, multiplier: float = 2.0,
                 jitter_enabled: bool = True, jitter_fn=None):
        self.max_attempts = max(1, int(max_attempts))
        self.initial_delay_seconds = max(0.0, float(initial_delay_seconds))
        self.max_delay_seconds = max(0.0, float(max_delay_seconds))
        self.multiplier = max(1.0, float(multiplier))
        self.jitter_enabled = bool(jitter_enabled)
        import random
        self._jitter_fn = jitter_fn or random.random

    def classify_retryability(self, error: Exception) -> str:
        if isinstance(error, UploadUncertain):
            return UNCERTAIN
        code = getattr(error, "code", None) if isinstance(error, UploadError) else None
        status = _http_status(error)
        reason = _http_reason(error)
        if status == 401 or code == INVALID_CREDENTIALS:
            return AUTH_REFRESHABLE
        if status == 403:
            if reason == "quotaExceeded":
                return NON_RETRYABLE
            if reason == "rateLimitExceeded":
                return RETRYABLE
            return NON_RETRYABLE  # forbidden/permission
        if status == 429:
            return RETRYABLE
        if status in RETRIABLE_STATUS_CODES:
            return RETRYABLE
        if _is_network_error(error):
            return RETRYABLE
        return NON_RETRYABLE

    def should_retry(self, error: Exception, attempt: int) -> bool:
        """attempt = wievielter RETRY-Versuch (1-basiert)."""
        return (self.classify_retryability(error) == RETRYABLE
                and attempt < self.max_attempts)

    def calculate_delay(self, attempt: int) -> float:
        """Exponentielles Backoff mit optionalem Full-Jitter. attempt 1-basiert."""
        raw = self.initial_delay_seconds * (self.multiplier ** max(0, attempt - 1))
        raw = min(self.max_delay_seconds, raw)
        if self.jitter_enabled:
            return max(0.0, float(self._jitter_fn()) * raw)
        return raw


# --------------------------------------------------------------------------
# Service
# --------------------------------------------------------------------------

class YouTubeUploadService:
    """Isolierter, sicherer Private-Upload-Service. Alle Google-Interaktionen
    sind injizierbar → Tests laufen ohne echte Google-Verbindung."""

    # Wie viele Attempt-Einträge in der Draft-History maximal behalten werden.
    _MAX_ATTEMPT_HISTORY = 20

    def __init__(
        self,
        settings: Settings,
        token_store: YouTubeTokenStore | None = None,
        *,
        credentials_loader=None,
        refresher=None,
        uploader=None,
        session_factory=None,
        retry_policy: "YouTubeRetryPolicy | None" = None,
        sleep_fn=None,
        now_fn=None,
    ) -> None:
        self.settings = settings
        self.oauth_config = YouTubeOAuthConfig.from_settings(settings)
        self.token_store = token_store or YouTubeTokenStore(
            settings.youtube_token_service_name, settings.youtube_token_account
        )
        self._credentials_loader = credentials_loader or _default_credentials_loader
        self._refresher = refresher or _default_refresher
        # Upload-Nahtstelle: `session_factory` (neu, resumable) hat Vorrang;
        # sonst Legacy-`uploader` (Prompt 27); sonst der echte Google-Default.
        self._session_factory = session_factory
        self._uploader = uploader
        self.retry_policy = retry_policy or YouTubeRetryPolicy(
            max_attempts=settings.youtube_upload_max_attempts,
            initial_delay_seconds=settings.youtube_upload_initial_delay,
            max_delay_seconds=settings.youtube_upload_max_delay,
        )
        import time as _time
        self._sleep = sleep_fn or _time.sleep
        import datetime
        self._now = now_fn or (
            lambda: datetime.datetime.now(datetime.timezone.utc).isoformat())

    # -- kleine Helfer ----------------------------------------------------

    def _oauth_ready(self) -> bool:
        return bool(
            self.settings.enable_youtube_oauth
            and self.oauth_config.client_secrets_configured()
            and self.token_store.is_available()
        )

    def _read_client_secret(self) -> str | None:
        """Liest NUR das client_secret (für den Refresh) frisch aus der Datei.
        Wird NIE geloggt/gespeichert/zurückgegeben."""
        path = self.oauth_config.client_secrets_path
        if not path or not os.path.exists(path):
            return None
        try:
            import json
            with open(path, "r", encoding="utf-8") as fh:
                data = json.load(fh)
            section = data.get("installed") or data.get("web") or {}
            secret = section.get("client_secret")
            return secret if isinstance(secret, str) and secret else None
        except Exception:  # noqa: BLE001 — nie Details/Pfad propagieren
            return None

    def _draft_valid(self, draft: dict) -> bool:
        """Prüft die INHALTLICHE Validität (MP4/Format/Titel/kein Viral-Claim).

        Der `safe_status`-Check der Validierung wird bewusst ignoriert: Er
        markiert publishing/published/failed als „unsicher" — das ist eine
        Nutzer-Schranke, nicht relevant für den Publisher selbst (sonst wäre ein
        Retry eines `failed`-Drafts unmöglich)."""
        checks = (draft.get("validation") or {}).get("checks") or {}
        summary = build_validation_summary(draft, checks)
        content_blocking = [b for b in summary["blocking_issues"] if b != "safe_status"]
        return len(content_blocking) == 0

    def _mp4_exists(self, draft: dict) -> bool:
        mp4 = draft.get("mp4_path") or ""
        return bool(mp4) and os.path.exists(mp4)

    # -- Readiness (auch für Dry-Run) -------------------------------------

    def readiness(self, draft: dict) -> dict:
        """Sichere Upload-Readiness — NIE Token/Secrets. Enthält alle Gates,
        die der echte Upload prüft, plus den Idempotenz-Zustand."""
        feature = bool(self.settings.enable_youtube_upload)
        oauth_ready = self._oauth_ready()
        token_present = False
        token_refresh_possible = False
        if self.token_store.is_available():
            payload = self.token_store.read_token()
            if isinstance(payload, dict):
                token_present = bool(payload.get("access_token"))
                token_refresh_possible = bool(payload.get("refresh_token"))
        draft_valid = self._draft_valid(draft)
        mp4_exists = self._mp4_exists(draft)
        idem = derive_idempotency_state(draft)
        already = bool(draft.get("external_post_id")) or idem == "succeeded"

        blocked: list[str] = []
        warnings: list[str] = []
        if not feature:
            blocked.append(UPLOAD_DISABLED)
        if not oauth_ready:
            blocked.append(OAUTH_NOT_READY)
        if oauth_ready and not token_present:
            blocked.append(TOKEN_MISSING)
        if not draft_valid:
            blocked.append(INVALID_DRAFT)
        if not mp4_exists:
            blocked.append(MP4_MISSING)
        if already:
            blocked.append(ALREADY_UPLOADED)
        elif idem == "in_progress":
            blocked.append(UPLOAD_IN_PROGRESS)
        elif idem == "uncertain":
            blocked.append(UPLOAD_STATE_UNCERTAIN)

        if token_present and not token_refresh_possible:
            warnings.append("no_refresh_token")

        can_attempt = feature and oauth_ready and token_present and draft_valid \
            and mp4_exists and idem in ("never_attempted", "failed")

        return {
            "upload_feature_enabled": feature,
            "oauth_ready": oauth_ready,
            "token_present": token_present,
            "token_refresh_possible": token_refresh_possible,
            "draft_valid": draft_valid,
            "mp4_exists": mp4_exists,
            "idempotency_state": idem,
            "already_uploaded": already,
            "publish_attempt_count": int(draft.get("publish_attempt_count") or 0),
            "can_attempt_private_upload": bool(can_attempt),
            "privacy_status": ALLOWED_PRIVACY,
            "blocked_reasons": blocked,
            "warnings": warnings,
            "no_secrets": True,
        }

    # -- Credentials / Refresh --------------------------------------------

    def prepare_credentials(self):
        """Lädt das Token aus dem Store und rekonstruiert Credentials.
        Rückgabe: (creds, None) oder (None, error_code). Loggt NIE Tokenwerte."""
        if not self.token_store.is_available():
            return None, TOKEN_MISSING
        payload = self.token_store.read_token()
        if not isinstance(payload, dict) or not payload.get("access_token"):
            return None, TOKEN_MISSING
        client_secret = self._read_client_secret()
        try:
            creds = self._credentials_loader(self.oauth_config, payload, client_secret)
        except UploadDependencyMissing:
            return None, UPLOAD_DEPENDENCY_MISSING
        except Exception:  # noqa: BLE001 — nie rohe Exception/Secret
            return None, INVALID_CREDENTIALS
        return creds, None

    def refresh_credentials_if_needed(self, creds, force: bool = False):
        """Refresht nur bei Bedarf (oder `force=True`, z. B. nach 401).
        Rückgabe: (creds, error_code_or_None).

        - Access-Token noch gültig und nicht `force` → kein Refresh.
        - Abgelaufen/`force` + refresh_token → offizieller Refresh, danach neuen
          Stand NUR über Keychain speichern.
        - Kein refresh_token → reauth_required.
        - Refresh-Fehler → token_refresh_failed.
        """
        if not force and getattr(creds, "valid", False):
            return creds, None
        if not getattr(creds, "refresh_token", None):
            return None, REAUTH_REQUIRED
        try:
            self._refresher(creds)
        except UploadDependencyMissing:
            return None, UPLOAD_DEPENDENCY_MISSING
        except Exception:  # noqa: BLE001 — nie rohe Exception/Secret
            return None, TOKEN_REFRESH_FAILED
        self._persist_refreshed(creds)
        return creds, None

    def _persist_refreshed(self, creds) -> None:
        """Speichert den aufgefrischten Tokenstand NUR über den Keychain
        (kein Plaintext). Fehler beim Speichern sind nicht kritisch für den
        laufenden Upload und leaken nichts.

        Audit-Fix: Wurde das Token zwischenzeitlich gelöscht (Logout WÄHREND
        des Refresh), wird NICHT gespeichert — sonst würde der Refresh das
        gerade ausgeloggte Token „wiederbeleben"."""
        old = self.token_store.read_token()
        if old is None:
            return  # Logout während Refresh → Token bleibt gelöscht
        expiry = getattr(creds, "expiry", None)
        merged = dict(old)
        if getattr(creds, "token", None):
            merged["access_token"] = creds.token
        if expiry is not None:
            try:
                merged["expiry"] = expiry.isoformat()
            except Exception:  # noqa: BLE001
                pass
        clean = sanitize_token_payload(merged)
        if clean is not None:
            try:
                self.token_store.save_token(clean)
            except Exception:  # noqa: BLE001
                pass

    # -- Request-Body -----------------------------------------------------

    def build_upload_request(self, draft: dict) -> dict:
        """Baut den `videos.insert`-Body (snippet+status). privacyStatus IMMER
        `private`. Enthält NIE Token/Secrets/Binärdaten."""
        hashtags = draft.get("hashtags") or []
        tags = [h.lstrip("#") for h in hashtags if h]
        description = (draft.get("description") or "").strip()
        if hashtags:
            description = (description + "\n\n" + " ".join(hashtags)).strip()
        return {
            "snippet": {
                "title": (draft.get("title") or "").strip()[:TITLE_MAX],
                "description": description,
                "tags": tags,
                "categoryId": str(self.settings.youtube_category_id),
            },
            "status": {
                "privacyStatus": ALLOWED_PRIVACY,
                "selfDeclaredMadeForKids": False,
            },
        }

    # -- Fehlerklassifikation ---------------------------------------------

    def classify_error(self, error: Exception) -> str:
        """Bildet eine (Google-)Exception auf einen stabilen internen Code ab.
        Gibt NIE die rohe Exception/Message mit möglichen Secrets zurück."""
        if isinstance(error, UploadUncertain):
            return UPLOAD_RESULT_UNCERTAIN
        if isinstance(error, UploadError):
            return error.code
        status = _http_status(error)
        reason = _http_reason(error)
        if status == 401:
            return INVALID_CREDENTIALS
        if status == 403:
            if reason == "quotaExceeded":
                return QUOTA_EXCEEDED
            if reason == "rateLimitExceeded":
                return RATE_LIMITED
            return PERMISSION_DENIED
        if status == 429:
            return RATE_LIMITED
        if status in RETRIABLE_STATUS_CODES:
            # 5xx nach abgeschicktem Upload → Ergebnis unklar (nicht blind retry).
            return UPLOAD_RESULT_UNCERTAIN
        if _is_network_error(error):
            return UPLOAD_RESULT_UNCERTAIN
        return UPLOAD_FAILED

    def sanitize_result(self, result: dict | None) -> dict:
        """Reduziert die API-Antwort auf sichere Felder (video id + Status).
        Entfernt alles Übrige — NIE Token/Header/Rohdaten."""
        result = result or {}
        snippet = result.get("snippet") or {}
        status = result.get("status") or {}
        return {
            "video_id": result.get("id"),
            "privacy_status": status.get("privacyStatus"),
            "title": snippet.get("title"),
        }

    # -- Der eigentliche Private-Upload -----------------------------------

    def upload_private(
        self, job_dir: str, publishing_id: str, draft: dict, *,
        confirm: str | None, privacy_status: str = ALLOWED_PRIVACY,
    ) -> dict:
        """Führt den sicheren Private-Upload durch (oder blockiert sauber).

        Gibt IMMER ein Dict mit `success` + `error_code`/`external_post_id`
        etc. zurück — NIE Token/Secrets. `published`/`external_post_id` NUR bei
        eindeutigem API-Erfolg."""
        idem = derive_idempotency_state(draft)
        base = {
            "success": False,
            "error_code": None,
            "status": draft.get("status"),
            "publishing_id": publishing_id,
            "external_post_id": draft.get("external_post_id"),
            "privacy_status": ALLOWED_PRIVACY,
            "idempotency_state": idem,
            "published_at": draft.get("published_at"),
            "message": "",
            "no_secrets": True,
        }

        def blocked(code: str, message: str) -> dict:
            return {**base, "error_code": code, "message": message}

        # 1) Feature-Flag
        if not self.settings.enable_youtube_upload:
            return blocked(UPLOAD_DISABLED,
                           "YouTube-Upload ist deaktiviert (Feature-Flag aus).")
        # 2) Nur PRIVATE
        if (privacy_status or "").strip().lower() != ALLOWED_PRIVACY:
            return blocked(INVALID_PRIVACY,
                           "Nur privacy_status='private' ist erlaubt "
                           "(kein public/unlisted).")
        # 3) Exakte Bestätigung
        if confirm != CONFIRM_PRIVATE:
            return blocked(CONFIRMATION_REQUIRED,
                           f"Bestätigung {CONFIRM_PRIVATE!r} ist erforderlich.")
        # 4) OAuth ready
        if not self._oauth_ready():
            return blocked(OAUTH_NOT_READY,
                           "OAuth ist nicht bereit (Flag/Secrets/Token-Store).")
        # 5) Idempotenz-Gates ZUERST (präziser Grund; verhindert Doppel-Upload).
        if base["external_post_id"] or idem == "succeeded":
            return blocked(ALREADY_UPLOADED,
                           "Draft wurde bereits hochgeladen (external_post_id).")
        if idem == "in_progress":
            return blocked(UPLOAD_IN_PROGRESS,
                           "Ein Upload läuft bereits (in_progress).")
        if idem == "uncertain":
            return blocked(UPLOAD_STATE_UNCERTAIN,
                           "Vorheriges Upload-Ergebnis ist unklar — bitte "
                           "YouTube-Konto prüfen, bevor erneut versucht wird.")
        # 6) Draft inhaltlich valide
        if not self._draft_valid(draft):
            return blocked(INVALID_DRAFT, "Draft ist nicht valide.")
        # 7) MP4 vorhanden
        if not self._mp4_exists(draft):
            return blocked(MP4_MISSING, "MP4-Datei fehlt.")

        # 8) ATOMARER CLAIM — genau EIN Request darf einen Upload starten.
        #    (O_EXCL-Lockdatei; paralleler Request → sofort geblockt.)
        claim = self._acquire_claim(job_dir, publishing_id)
        if claim is None:
            return blocked(UPLOAD_IN_PROGRESS,
                           "Ein Upload läuft bereits (paralleler Request).")

        import uuid
        ctx = {"retry_count": 0}
        attempt_id = uuid.uuid4().hex
        started_at = self._now()

        def _entry(outcome: str, error_code: str | None) -> dict:
            return {"attempt_id": attempt_id, "started_at": started_at,
                    "completed_at": self._now(), "outcome": outcome,
                    "error_code": error_code, "retry_count": int(ctx["retry_count"])}

        def _fail(code: str, message: str, *, to: str, outcome: str) -> dict:
            self._to_state(job_dir, publishing_id, to, error_code=code,
                           retry_count=ctx["retry_count"],
                           attempt_entry=_entry(outcome, code))
            idem = "uncertain" if to == ystate.STATE_UNCERTAIN else "failed"
            return {**base, "error_code": code, "status": "failed",
                    "idempotency_state": idem, "retry_count": ctx["retry_count"],
                    "message": message}

        try:
            # 8b) Nach dem Claim FRISCH nachladen + Idempotenz erneut prüfen —
            #     schließt das sequentielle Race-Fenster (Winner hat evtl. schon
            #     published/geclaimt, bevor dieser Request den Lock bekam).
            fresh = load_draft(job_dir, publishing_id) or draft
            fidem = derive_idempotency_state(fresh)
            if fresh.get("external_post_id") or fidem == "succeeded":
                return blocked(ALREADY_UPLOADED, "Draft wurde bereits hochgeladen.")
            if fidem == "in_progress":
                return blocked(UPLOAD_IN_PROGRESS, "Ein Upload läuft bereits.")
            if fidem == "uncertain":
                return blocked(UPLOAD_STATE_UNCERTAIN,
                               "Vorheriges Ergebnis unklar — bitte Studio prüfen.")

            attempt_count = int(fresh.get("publish_attempt_count") or 0) + 1

            # 9) → preparing (Attempt-Metadaten persistieren).
            self._to_state(job_dir, publishing_id, ystate.STATE_PREPARING,
                           current_attempt=attempt_count, retry_count=0,
                           extra={"publish_attempt_id": attempt_id,
                                  "publish_started_at": started_at,
                                  "publish_attempt_count": attempt_count,
                                  "publish_platform": "youtube_shorts",
                                  "upload_progress": None})

            # 10) Credentials + Refresh (aus preparing → failed/reauth bei Fehler).
            creds, err = self.prepare_credentials()
            if err:
                to = (ystate.STATE_REAUTH_REQUIRED
                      if err in (TOKEN_MISSING, REAUTH_REQUIRED, INVALID_CREDENTIALS)
                      else ystate.STATE_FAILED)
                return _fail(err, "Kein verwendbares Token für den Upload.",
                             to=to, outcome="failed")
            creds, err = self.refresh_credentials_if_needed(creds)
            if err:
                to = (ystate.STATE_REAUTH_REQUIRED
                      if err in (REAUTH_REQUIRED, INVALID_CREDENTIALS)
                      else ystate.STATE_FAILED)
                return _fail(err, "Token konnte nicht aufgefrischt werden.",
                             to=to, outcome="failed")

            # 11) preparing → uploading.
            self._to_state(job_dir, publishing_id, ystate.STATE_UPLOADING)
            body = self.build_upload_request(draft)
            media_path = draft.get("mp4_path")

            def _on_progress(status) -> None:
                self._persist_progress(job_dir, publishing_id, status)

            def _state_cb(to: str) -> None:
                self._to_state(job_dir, publishing_id, to,
                               retry_count=ctx["retry_count"])

            # 12) Upload mit kontrolliertem Retry/Backoff. Tests: injiziert,
            #     kein echter Google-Call, kein echtes Sleep.
            try:
                raw = self._run_upload(creds, body, media_path, ctx,
                                       _on_progress, _state_cb)
            except UploadUncertain:
                return _fail(UPLOAD_RESULT_UNCERTAIN,
                             "Upload-Ergebnis unklar — bitte YouTube-Studio "
                             "prüfen, bevor erneut versucht wird.",
                             to=ystate.STATE_UNCERTAIN, outcome="uncertain")
            except Exception as exc:  # noqa: BLE001 — klassifizieren, nie leaken
                code = self.classify_error(exc)
                if code in (UPLOAD_RESULT_UNCERTAIN, UPLOAD_STATE_UNCERTAIN):
                    return _fail(code, "Upload-Ergebnis unklar — bitte "
                                 "YouTube-Studio prüfen.",
                                 to=ystate.STATE_UNCERTAIN, outcome="uncertain")
                to = (ystate.STATE_REAUTH_REQUIRED
                      if code in (REAUTH_REQUIRED, INVALID_CREDENTIALS)
                      else ystate.STATE_FAILED)
                return _fail(code, "Upload fehlgeschlagen.", to=to, outcome="failed")

            # 13) Erfolg NUR bei eindeutiger id.
            result = self.sanitize_result(raw)
            video_id = result.get("video_id")
            if not video_id:
                return _fail(UPLOAD_RESULT_UNCERTAIN,
                             "Upload-Ergebnis unklar (keine Video-ID).",
                             to=ystate.STATE_UNCERTAIN, outcome="uncertain")

            # 14) uploading → reconciling (external_post_id CHECKPOINT persistieren)
            #     → published. Das Zwischen-Checkpoint macht Crash-Recovery
            #     (Fenster E) über die eindeutige ID möglich.
            completed_at = self._now()
            try:
                self._to_state(job_dir, publishing_id, ystate.STATE_RECONCILING,
                               reconciliation_status="confirmed_on_upload",
                               extra={"external_post_id": video_id})
                self._to_state(job_dir, publishing_id, ystate.STATE_PUBLISHED,
                               attempt_entry=_entry("succeeded", None),
                               extra={"external_post_id": video_id,
                                      "published_at": completed_at})
            except Exception:  # noqa: BLE001 — Remote erfolgreich, lokal nicht
                return {**base, "error_code": UPLOAD_RESULT_UNCERTAIN,
                        "status": "publishing", "idempotency_state": "uncertain",
                        "external_post_id": video_id, "retry_count": ctx["retry_count"],
                        "message": "Upload war erfolgreich, lokale Speicherung "
                                   "schlug fehl — bitte Status prüfen."}

            return {
                "success": True, "error_code": None, "status": "published",
                "publishing_id": publishing_id, "external_post_id": video_id,
                "privacy_status": ALLOWED_PRIVACY, "idempotency_state": "succeeded",
                "published_at": completed_at, "retry_count": ctx["retry_count"],
                "message": "Privates Video erfolgreich hochgeladen (privat).",
                "no_secrets": True,
            }
        finally:
            self._release_claim(claim)

    # -- Upload-Ausführung mit Retry/Backoff ------------------------------

    def _new_session(self, creds, body: dict, media_path: str):
        if self._session_factory is not None:
            return self._session_factory(creds, body, media_path)
        if self._uploader is not None:
            return _LegacyUploaderSession(self._uploader, creds, body, media_path)
        return _default_session_factory(
            creds, body, media_path, self.settings.youtube_upload_chunk_bytes)

    def _run_upload(self, creds, body: dict, media_path: str, ctx: dict,
                    on_progress, state_cb=None):
        """Treibt den resumable Upload mit kontrolliertem Retry/Backoff.

        - Retriable (5xx/429/rateLimit/Netzwerk): → `retry_wait` (persistiert),
          Backoff, → `uploading`, dann `next_chunk()` auf DERSELBEN Session
          (resumable Resume — kein Duplikat).
        - 401/auth: → `auth_refresh` (persistiert), **maximal ein** erzwungener
          Refresh + neue Session, → `uploading`. Danach → Fehler.
        - Nicht retriable: sofort abbrechen.
        - Retriable erschöpft: `UploadUncertain` (möglicher Remote-Commit — NIE
          blind neu starten).
        `state_cb(to_state)` persistiert die Zwischenzustände (crash-sicher).
        Wirft `UploadUncertain` oder eine klassifizierbare Exception.
        """
        policy = self.retry_policy
        session = self._new_session(creds, body, media_path)
        response = None
        refreshed_once = False

        def _cb(to: str) -> None:
            if state_cb is not None:
                state_cb(to)

        while response is None:
            try:
                status, response = session.next_chunk()
                if status is not None and on_progress is not None:
                    on_progress(status)
            except UploadUncertain:
                raise
            except Exception as exc:  # noqa: BLE001
                cat = policy.classify_retryability(exc)
                if cat == UNCERTAIN:
                    raise UploadUncertain()
                if cat == AUTH_REFRESHABLE and not refreshed_once:
                    refreshed_once = True
                    _cb(ystate.STATE_AUTH_REFRESH)  # crash-sichtbarer Checkpoint
                    new_creds, err = self.refresh_credentials_if_needed(creds, force=True)
                    if err == REAUTH_REQUIRED:
                        raise ReauthRequired()
                    if err == TOKEN_REFRESH_FAILED:
                        raise TokenRefreshFailed()
                    if err == UPLOAD_DEPENDENCY_MISSING:
                        raise UploadDependencyMissing()
                    if err:
                        raise  # unbekannt → als invalid_credentials failen
                    creds = new_creds
                    # 401 ⇒ Chunks wurden nicht akzeptiert ⇒ neue Session ist sicher.
                    session = self._new_session(creds, body, media_path)
                    response = None
                    _cb(ystate.STATE_UPLOADING)
                    continue
                if cat == RETRYABLE and policy.should_retry(exc, ctx["retry_count"] + 1):
                    ctx["retry_count"] += 1
                    _cb(ystate.STATE_RETRY_WAIT)  # crash-sichtbarer Checkpoint
                    self._sleep(policy.calculate_delay(ctx["retry_count"]))
                    _cb(ystate.STATE_UPLOADING)
                    continue  # dieselbe Session fortsetzen (resumable)
                if cat == RETRYABLE:
                    # Retries erschöpft → möglicher Remote-Erfolg unklar.
                    raise UploadUncertain()
                raise  # non_retryable
        return response or {}

    # -- Persistente State-Transition (crash-sicher, ohne Secrets) --------

    def _to_state(self, job_dir: str, publishing_id: str, to: str, *,
                  error_code: str | None = None, retry_count: int | None = None,
                  current_attempt: int | None = None, attempt_entry: dict | None = None,
                  reconciliation_status: str | None = None,
                  requires_manual_check: bool | None = None,
                  requires_reauth: bool | None = None,
                  extra: dict | None = None) -> dict:
        current = load_draft(job_dir, publishing_id) or {}
        ex = dict(extra or {})
        if attempt_entry is not None:
            raw_att = current.get("publish_attempts")
            hist = [e for e in raw_att if isinstance(e, dict)] if isinstance(raw_att, list) else []
            hist.append(_safe_attempt_entry(attempt_entry))
            ex["publish_attempts"] = hist[-self._MAX_ATTEMPT_HISTORY:]
            ex.setdefault("publish_completed_at", attempt_entry.get("completed_at"))
        updates = ystate.transition(
            current, to, now=self._now(),
            error_category=error_category(error_code), error_code=error_code,
            retry_count=retry_count, current_attempt=current_attempt,
            requires_manual_check=requires_manual_check, requires_reauth=requires_reauth,
            reconciliation_status=reconciliation_status, extra=ex)
        apply_publish_state(job_dir, publishing_id, updates)
        return updates

    # -- Atomarer Claim / Lock (Race-Schutz) ------------------------------

    def _claim_path(self, job_dir: str, publishing_id: str) -> str:
        return os.path.join(publishing_dir(job_dir), f"{publishing_id}.uploadlock")

    def _acquire_claim(self, job_dir: str, publishing_id: str):
        """Atomarer Claim per O_CREAT|O_EXCL. Genau EIN Aufrufer gewinnt; alle
        parallelen Requests bekommen `None` (bereits geclaimt). Enthält KEINE
        Secrets. Gibt den Lock-Pfad (Handle) zurück oder None."""
        path = self._claim_path(job_dir, publishing_id)
        try:
            os.makedirs(os.path.dirname(path), exist_ok=True)
            fd = os.open(path, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
        except FileExistsError:
            return None
        except OSError:
            return None
        try:
            os.write(fd, self._now().encode("ascii", "ignore"))
        except OSError:
            pass
        finally:
            os.close(fd)
        return path

    def _release_claim(self, claim) -> None:
        if not claim:
            return
        try:
            os.unlink(claim)
        except OSError:
            pass

    # -- Progress (additiv, ohne Secrets) ---------------------------------

    def _persist_progress(self, job_dir: str, publishing_id: str, status) -> None:
        """Best-effort: schreibt Fortschritt (bytes/percent) in den Draft, damit
        ein paralleler upload-status-Poll ihn sehen kann. Kein Secret/Session-URI.
        """
        prog = _extract_progress(status)
        if prog is None:
            return
        try:
            apply_publish_state(job_dir, publishing_id, {"upload_progress": prog})
        except Exception:  # noqa: BLE001
            pass

    # -- Upload-Status / Recovery-Check -----------------------------------

    def is_stale(self, draft: dict, now: str | None = None) -> bool:
        """True, wenn der Draft in einem aktiven Zustand ist und seit
        `stale_upload_seconds` keine Aktivität mehr hatte (verwaist/crash)."""
        state = ystate.current_state(draft)
        if state not in ystate.ACTIVE_STATES:
            return False
        activity = (draft.get("last_upload_activity_at")
                    or draft.get("last_transition_at")
                    or draft.get("upload_started_at"))
        age = _age_seconds(activity, now or self._now())
        if age is None:
            return False
        return age > int(self.settings.youtube_stale_upload_seconds)

    def upload_status(self, draft: dict) -> dict:
        """Sichere Status-/Recovery-Übersicht (für den Endpoint). Keine Secrets,
        keine Session-URIs."""
        state = ystate.current_state(draft)
        idem = derive_idempotency_state(draft)
        ext_present = bool(draft.get("external_post_id"))
        last_err = draft.get("last_publish_error")
        requires_reauth = bool(draft.get("requires_reauth")) or (
            state == ystate.STATE_REAUTH_REQUIRED) or (
            last_err in (TOKEN_MISSING, REAUTH_REQUIRED, INVALID_CREDENTIALS))
        requires_manual_check = bool(draft.get("requires_manual_check")) or (
            state == ystate.STATE_UNCERTAIN)
        stale = self.is_stale(draft)
        # Retry NUR aus ruhenden, nicht-terminalen Zuständen — NIE aus uncertain
        # (dort erst reconcilen/Studio prüfen) und nie bei vorhandener id.
        can_retry = state in (ystate.STATE_IDLE, ystate.STATE_FAILED) and not ext_present
        can_reconcile = state in (ystate.STATE_RECONCILING, ystate.STATE_UNCERTAIN) or (
            stale and state in ystate.ACTIVE_STATES)
        history = draft.get("publish_attempts")
        if not isinstance(history, list):
            history = []
        att_summary = [_safe_attempt_entry(a) for a in history[-self._MAX_ATTEMPT_HISTORY:]]
        return {
            "status": draft.get("status"),
            "state": state,
            "idempotency_state": idem,
            "is_stale": bool(stale),
            "publish_attempt_count": int(draft.get("publish_attempt_count") or 0),
            "current_attempt": draft.get("current_attempt"),
            "retry_count": int(draft.get("retry_count") or 0),
            "last_publish_error": last_err,
            "last_error_category": draft.get("last_error_category"),
            "external_post_id_present": ext_present,
            "can_retry": bool(can_retry),
            "can_reconcile": bool(can_reconcile),
            "requires_manual_check": bool(requires_manual_check),
            "requires_reauth": bool(requires_reauth),
            "last_activity_at": (draft.get("last_upload_activity_at")
                                 or draft.get("last_transition_at")),
            "reconciliation_status": draft.get("reconciliation_status"),
            "reconciliation_checked_at": draft.get("reconciliation_checked_at"),
            "upload_progress": draft.get("upload_progress"),
            "attempt_history_summary": att_summary,
            "transition_history_summary": ystate.transition_history_summary(draft),
            "no_secrets": True,
        }

    # -- Sicherer manueller Real-Testmodus (nie in automatischen Tests) ---

    def real_test_ready(self, draft: dict) -> tuple[bool, list[str]]:
        """Prüft ALLE Voraussetzungen für einen echten manuellen Test-Upload.
        Beide Flags müssen an sein; Automatische Tests setzen das Real-Test-Flag
        NIE. Rückgabe: (ok, fehlende_reasons)."""
        reasons: list[str] = []
        if not self.settings.enable_youtube_upload:
            reasons.append(UPLOAD_DISABLED)
        if not self.settings.enable_youtube_real_test:
            reasons.append("real_test_flag_missing")
        rd = self.readiness(draft)
        if not rd["oauth_ready"]:
            reasons.append(OAUTH_NOT_READY)
        if not rd["token_present"]:
            reasons.append(TOKEN_MISSING)
        if not rd["draft_valid"]:
            reasons.append(INVALID_DRAFT)
        if not rd["mp4_exists"]:
            reasons.append(MP4_MISSING)
        if not self.token_store.is_available():
            reasons.append(TOKEN_MISSING)
        return (len(reasons) == 0, reasons)


# --------------------------------------------------------------------------
# HTTP-/Netzwerk-Helfer (defensiv — kein harter Google-Import)
# --------------------------------------------------------------------------

def _http_status(error: Exception):
    """Best-effort HTTP-Status aus einer googleapiclient HttpError-artigen
    Exception (ohne harten Import)."""
    for attr in ("status_code", "status"):
        val = getattr(error, attr, None)
        if isinstance(val, int):
            return val
    resp = getattr(error, "resp", None)
    if resp is not None:
        val = getattr(resp, "status", None)
        try:
            return int(val)
        except (TypeError, ValueError):
            return None
    return None


def _http_reason(error: Exception) -> str | None:
    """Best-effort Google-'reason' (z. B. quotaExceeded/rateLimitExceeded)."""
    reason = getattr(error, "reason", None)
    if isinstance(reason, str) and reason and reason[:1].islower():
        return reason
    return None


def _is_network_error(error: Exception) -> bool:
    name = type(error).__name__.lower()
    return any(k in name for k in ("timeout", "connection", "httplib", "ssl"))


def _age_seconds(iso_ts, now_iso) -> float | None:
    """Alter (Sekunden) eines ISO-Timestamps relativ zu `now_iso`. None bei
    fehlendem/unparsbarem Wert."""
    import datetime
    if not isinstance(iso_ts, str) or not iso_ts:
        return None
    try:
        a = datetime.datetime.fromisoformat(iso_ts.replace("Z", "+00:00"))
        b = datetime.datetime.fromisoformat(str(now_iso).replace("Z", "+00:00"))
    except (ValueError, TypeError):
        return None
    if a.tzinfo is None:
        a = a.replace(tzinfo=datetime.timezone.utc)
    if b.tzinfo is None:
        b = b.replace(tzinfo=datetime.timezone.utc)
    return (b - a).total_seconds()


# Nur diese Felder eines Attempt-Eintrags werden persistiert/zurückgegeben —
# garantiert keine Tokens/Header/Session-URIs/rohe Exceptions.
_ATTEMPT_FIELDS = ("attempt_id", "started_at", "completed_at", "outcome",
                   "error_code", "retry_count")


def _safe_attempt_entry(entry) -> dict:
    # Audit-Fix: korrupte (Nicht-Dict-)Einträge aus einer beschädigten
    # Draft-Datei dürfen den Status-Endpoint nie crashen (500).
    if not isinstance(entry, dict):
        return {"attempt_id": None, "outcome": "corrupt_entry"}
    out: dict = {}
    for k in _ATTEMPT_FIELDS:
        v = entry.get(k)
        if isinstance(v, (str, int, float, bool)) or v is None:
            out[k] = v
    return out


def _extract_progress(status) -> dict | None:
    """Liest Fortschritt aus einem google MediaUploadProgress-Status (best-effort).
    Enthält NUR Zahlen — nie den (sensiblen) resumable Session-URI."""
    if status is None:
        return None
    uploaded = getattr(status, "resumable_progress", None)
    total = getattr(status, "total_size", None)
    percent = None
    prog_fn = getattr(status, "progress", None)
    if callable(prog_fn):
        try:
            percent = round(float(prog_fn()) * 100.0, 1)
        except Exception:  # noqa: BLE001
            percent = None
    if uploaded is None and percent is None:
        return None
    return {
        "bytes_uploaded": int(uploaded) if isinstance(uploaded, (int, float)) else None,
        "total_bytes": int(total) if isinstance(total, (int, float)) else None,
        "progress_percent": percent,
    }
