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
from ..publishing import apply_publish_state, build_validation_summary
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


def _default_uploader(creds, body: dict, media_path: str) -> dict:
    """Echter resumable Upload via google-api-python-client. Gibt bei Erfolg
    die (sanitisierte) API-Antwort mit `id` zurück; klassifizierbare Fehler
    werden als Exceptions durchgereicht und vom Service klassifiziert."""
    try:
        from googleapiclient.discovery import build  # type: ignore
        from googleapiclient.http import MediaFileUpload  # type: ignore
    except Exception:  # noqa: BLE001
        raise UploadDependencyMissing()
    youtube = build("youtube", "v3", credentials=creds, cache_discovery=False)
    media = MediaFileUpload(media_path, chunksize=-1, resumable=True)
    request = youtube.videos().insert(part="snippet,status", body=body,
                                      media_body=media)
    response = None
    while response is None:
        _status, response = request.next_chunk()
    return response or {}


# --------------------------------------------------------------------------
# Service
# --------------------------------------------------------------------------

class YouTubeUploadService:
    """Isolierter, sicherer Private-Upload-Service. Alle Google-Interaktionen
    sind injizierbar → Tests laufen ohne echte Google-Verbindung."""

    def __init__(
        self,
        settings: Settings,
        token_store: YouTubeTokenStore | None = None,
        *,
        credentials_loader=None,
        refresher=None,
        uploader=None,
        now_fn=None,
    ) -> None:
        self.settings = settings
        self.oauth_config = YouTubeOAuthConfig.from_settings(settings)
        self.token_store = token_store or YouTubeTokenStore(
            settings.youtube_token_service_name, settings.youtube_token_account
        )
        self._credentials_loader = credentials_loader or _default_credentials_loader
        self._refresher = refresher or _default_refresher
        self._uploader = uploader or _default_uploader
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

    def refresh_credentials_if_needed(self, creds):
        """Refresht nur bei Bedarf. Rückgabe: (creds, error_code_or_None).

        - Access-Token noch gültig → kein Refresh.
        - Abgelaufen + refresh_token → offizieller Refresh, danach neuen Stand
          NUR über Keychain speichern.
        - Kein refresh_token → reauth_required.
        - Refresh-Fehler → token_refresh_failed.
        """
        if getattr(creds, "valid", False):
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
        laufenden Upload und leaken nichts."""
        old = self.token_store.read_token() or {}
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

        # 8) Credentials + Refresh
        creds, err = self.prepare_credentials()
        if err:
            return blocked(err, "Kein verwendbares Token für den Upload.")
        creds, err = self.refresh_credentials_if_needed(creds)
        if err:
            return blocked(err, "Token konnte nicht aufgefrischt werden.")

        # 9) Transaktion: publishing/in_progress + neuer Versuch (VOR dem Call,
        #    damit ein Absturz mittendrin als in_progress geblockt bleibt).
        import uuid
        attempt_id = uuid.uuid4().hex
        started_at = self._now()
        attempt_count = int(draft.get("publish_attempt_count") or 0) + 1
        try:
            apply_publish_state(job_dir, publishing_id, {
                "status": "publishing",
                "idempotency_state": "in_progress",
                "publish_attempt_id": attempt_id,
                "publish_started_at": started_at,
                "publish_attempt_count": attempt_count,
                "publish_platform": "youtube_shorts",
                "last_publish_error": None,
            })
        except Exception:  # noqa: BLE001
            return blocked(UPLOAD_FAILED, "Interner Fehler beim Statuswechsel.")

        body = self.build_upload_request(draft)
        media_path = draft.get("mp4_path")

        # 10) Upload ausführen — Google-Interaktion ist injiziert/mockbar.
        try:
            raw = self._uploader(creds, body, media_path)
        except Exception as exc:  # noqa: BLE001 — klassifizieren, nie leaken
            code = self.classify_error(exc)
            uncertain = code in (UPLOAD_RESULT_UNCERTAIN, UPLOAD_STATE_UNCERTAIN)
            self._record_failure(job_dir, publishing_id, code, uncertain, attempt_count)
            msg = ("Upload-Ergebnis unklar — bitte YouTube-Konto prüfen, "
                   "bevor erneut versucht wird." if uncertain
                   else "Upload fehlgeschlagen.")
            return {**base, "error_code": code, "status": "failed",
                    "idempotency_state": "uncertain" if uncertain else "failed",
                    "message": msg}

        # 11) Erfolg NUR bei eindeutiger id.
        result = self.sanitize_result(raw)
        video_id = result.get("video_id")
        if not video_id:
            # Antwort ohne id → Ergebnis unklar (kein Fake-published).
            self._record_failure(job_dir, publishing_id, UPLOAD_RESULT_UNCERTAIN,
                                 True, attempt_count)
            return {**base, "error_code": UPLOAD_RESULT_UNCERTAIN,
                    "status": "failed", "idempotency_state": "uncertain",
                    "message": "Upload-Ergebnis unklar (keine Video-ID)."}

        completed_at = self._now()
        try:
            apply_publish_state(job_dir, publishing_id, {
                "status": "published",
                "idempotency_state": "succeeded",
                "external_post_id": video_id,
                "published_at": completed_at,
                "publish_completed_at": completed_at,
                "last_publish_error": None,
                "error": None,
            })
        except Exception:  # noqa: BLE001 — Remote erfolgreich, lokal nicht
            # Video existiert remote, lokale Persistenz scheiterte → uncertain.
            return {**base, "error_code": UPLOAD_RESULT_UNCERTAIN,
                    "status": "publishing", "idempotency_state": "uncertain",
                    "external_post_id": video_id,
                    "message": "Upload war erfolgreich, lokale Speicherung "
                               "schlug fehl — bitte Status prüfen."}

        return {
            "success": True,
            "error_code": None,
            "status": "published",
            "publishing_id": publishing_id,
            "external_post_id": video_id,
            "privacy_status": ALLOWED_PRIVACY,
            "idempotency_state": "succeeded",
            "published_at": completed_at,
            "message": "Privates Video erfolgreich hochgeladen (privat).",
            "no_secrets": True,
        }

    def _record_failure(self, job_dir: str, publishing_id: str, code: str,
                        uncertain: bool, attempt_count: int) -> None:
        """Persistiert einen fehlgeschlagenen/unklaren Versuch (ohne Secrets)."""
        try:
            apply_publish_state(job_dir, publishing_id, {
                "status": "failed",
                "idempotency_state": "uncertain" if uncertain else "failed",
                "last_publish_error": code,
                "error": code,
                "publish_completed_at": self._now(),
            })
        except Exception:  # noqa: BLE001
            pass


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
    for attr in ("_get_reason", "error_details"):
        pass
    return None


def _is_network_error(error: Exception) -> bool:
    name = type(error).__name__.lower()
    return any(k in name for k in ("timeout", "connection", "httplib", "ssl"))
