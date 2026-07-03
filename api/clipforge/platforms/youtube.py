"""YouTube-Publishing-Adapter — Phase 1: Dry-Run, KEIN echter Upload.

Was dieser Adapter tut:
  - `dry_run()`: baut die Metadaten, die an die offizielle YouTube Data API
    (`videos.insert`) gehen WÜRDEN, und listet Checks/Warnungen/Blocker.
  - `publish()`: prüft alle Sicherheitsbedingungen (Feature-Flag, Bestätigung,
    Credentials, Validierung, Idempotenz). Selbst wenn alles erfüllt ist,
    passiert in dieser Phase KEIN echter Upload — Rückgabe `not_implemented`.

Was dieser Adapter NICHT tut (bewusst):
  - kein echter API-Call, kein OAuth-Flow, kein Token-Handling/Speichern
  - keine Secrets in Rückgaben oder Logs (nur Dateiname, nie Pfad/Token)
  - kein externer Netzwerkzugriff

Quellen/Details: docs/YOUTUBE_PUBLISHING.md.
"""

from __future__ import annotations

import os

from ..config import Settings
from ..publishing import build_validation_summary
from .base import PlatformAdapter
from .youtube_auth import REQUIRED_SCOPE, YouTubeTokenStore

# Offiziell dokumentierte privacyStatus-Werte (YouTube Data API v3).
YOUTUBE_PRIVACY_STATUSES = ("private", "unlisted", "public")
DEFAULT_PRIVACY = "private"

# Bestätigungs-Phrasen (müssen exakt passen).
CONFIRM_PRIVATE = "UPLOAD_PRIVATE"
CONFIRM_PUBLIC = "UPLOAD_PUBLIC"

UPLOAD_DISABLED_MESSAGE = "YouTube upload is disabled. Dry-run only."

# Offiziell dokumentiertes Titel-Limit; Description-Limit als TODO (siehe Doku).
TITLE_MAX = 100

_UPLOAD_ENDPOINT = (
    "POST https://www.googleapis.com/upload/youtube/v3/videos"
    "?part=snippet,status&uploadType=resumable"
)


class YouTubeAdapter(PlatformAdapter):
    platform = "youtube_shorts"

    def __init__(self, settings: Settings, token_store: YouTubeTokenStore | None = None):
        self.settings = settings
        # Token-Store injizierbar (Tests mocken keyring); Default aus Settings.
        self.token_store = token_store or YouTubeTokenStore(
            settings.youtube_token_service_name, settings.youtube_token_account
        )

    # ---- interne Helfer --------------------------------------------------

    def _feature_enabled(self) -> bool:
        return bool(self.settings.enable_youtube_upload)

    def _oauth_enabled(self) -> bool:
        return bool(self.settings.enable_youtube_oauth)

    def _credentials_configured(self) -> bool:
        return bool(self.settings.youtube_credentials_configured)

    def _credentials_basename(self) -> str | None:
        path = self.settings.youtube_client_secrets_file
        return os.path.basename(path) if path else None

    def _build_request_metadata(self, draft: dict, privacy_status: str) -> dict:
        """Baut die snippet/status-Metadaten für `videos.insert`.

        Enthält NIE Token/Secrets/Binärdaten — nur die JSON-Metadaten, die
        Teil des Upload-Requests wären.
        """
        hashtags = draft.get("hashtags") or []
        tags = [h.lstrip("#") for h in hashtags if h]
        description = (draft.get("description") or "").strip()
        if hashtags:
            description = (description + "\n\n" + " ".join(hashtags)).strip()
        status: dict = {
            "privacyStatus": privacy_status,
            "selfDeclaredMadeForKids": False,
        }
        # publishAt plant eine spätere Veröffentlichung. Laut Doku muss dafür
        # privacyStatus=private sein — TODO offiziell final verifizieren.
        if draft.get("scheduled_at"):
            status["publishAt"] = draft["scheduled_at"]
        return {
            "snippet": {
                "title": (draft.get("title") or "").strip()[:TITLE_MAX],
                "description": description,
                "tags": tags,
                "categoryId": str(self.settings.youtube_category_id),
            },
            "status": status,
        }

    # ---- Interface -------------------------------------------------------

    def validate_draft(self, draft: dict) -> dict:
        """YouTube-Validierung = lokale Validation-Summary (ohne ffprobe-Aufruf,
        nutzt gespeicherte Checks, falls vorhanden)."""
        checks = (draft.get("validation") or {}).get("checks") or {}
        return build_validation_summary(draft, checks)

    def dry_run(self, draft: dict) -> dict:
        summary = self.validate_draft(draft)
        checklist = summary["checklist"]

        mp4 = draft.get("mp4_path") or ""
        mp4_exists = bool(mp4) and os.path.exists(mp4)
        title_present = bool((draft.get("title") or "").strip())
        description_present = bool((draft.get("description") or "").strip())
        no_viral = bool(checklist.get("no_viral_guarantee", True))
        feature_enabled = self._feature_enabled()
        creds = self._credentials_configured()

        checks = {
            "mp4_exists": mp4_exists,
            "format_9_16": checklist.get("format_9_16"),
            "title_present": title_present,
            "description_present": description_present,
            "no_viral_guarantee": no_viral,
            "upload_feature_enabled": feature_enabled,
            "credentials_configured": creds,
        }

        blocked_reasons: list[str] = []
        if not mp4_exists:
            blocked_reasons.append("MP4 file is missing.")
        if not title_present:
            blocked_reasons.append("A title is required for YouTube.")
        if not no_viral:
            blocked_reasons.append("Text contains a virality guarantee — remove it.")
        if not feature_enabled:
            blocked_reasons.append(UPLOAD_DISABLED_MESSAGE)
        if not creds:
            blocked_reasons.append("YouTube credentials are not configured.")

        warnings: list[str] = []
        if not description_present:
            warnings.append(
                "Description is empty — YouTube allows it, but it helps discovery."
            )
        if checklist.get("format_9_16") is None:
            warnings.append("Aspect ratio not verified (ffprobe unavailable).")
        elif checklist.get("format_9_16") is False:
            warnings.append("Video is not 9:16 — it may not be treated as a Short.")
        if draft.get("external_post_id"):
            warnings.append(
                "This draft already has an external_post_id — re-uploading would "
                "create a duplicate."
            )

        # would_upload = ein echter publish() hätte grünes Licht (nur die
        # Nicht-Implementierung stünde noch im Weg). Rein informativ.
        would_upload = feature_enabled and creds and not blocked_reasons

        return {
            "platform": self.platform,
            "enabled": feature_enabled,
            "would_upload": would_upload,
            "video_file": os.path.basename(mp4) if mp4 else None,
            "title": draft.get("title") or "",
            "description": draft.get("description") or "",
            "hashtags": draft.get("hashtags") or [],
            "privacy_status": DEFAULT_PRIVACY,
            "scheduled_at": draft.get("scheduled_at"),
            "checks": checks,
            "warnings": warnings,
            "blocked_reasons": blocked_reasons,
            "request_preview": {
                "endpoint": _UPLOAD_ENDPOINT,
                "metadata": self._build_request_metadata(draft, DEFAULT_PRIVACY),
                "video_body": "<local MP4 — not included in preview>",
                "note": (
                    "Preview contains only public video metadata — no "
                    "credentials and no binary body. Dry-run performs NO upload."
                ),
            },
            "upload_implemented": False,
        }

    def publish(
        self, draft: dict, *, confirm: str | None = None, privacy_status: str = DEFAULT_PRIVACY
    ) -> dict:
        """Sicher blockierter Publish. Gibt in dieser Phase NIEMALS einen
        echten Erfolg zurück (kein Fake-Success, kein Statuswechsel auf
        published)."""
        privacy = (privacy_status or DEFAULT_PRIVACY).strip().lower()
        result: dict = {
            "platform": self.platform,
            "outcome": "",  # disabled | needs_confirmation | not_ready | not_implemented
            "message": "",
            "blocked_reasons": [],
            "privacy_status": privacy,
            "external_post_id": None,
            "draft_status_changed": False,
        }

        # 1) Feature-Flag: standardmäßig AUS.
        if not self._feature_enabled():
            result["outcome"] = "disabled"
            result["message"] = UPLOAD_DISABLED_MESSAGE
            result["blocked_reasons"].append("feature_disabled")
            return result

        # 2) Gültiger privacyStatus.
        if privacy not in YOUTUBE_PRIVACY_STATUSES:
            result["outcome"] = "needs_confirmation"
            result["message"] = (
                f"Invalid privacy_status {privacy!r} "
                f"(allowed: {', '.join(YOUTUBE_PRIVACY_STATUSES)})."
            )
            result["blocked_reasons"].append("invalid_privacy_status")
            return result

        # 3) Explizite Bestätigungs-Phrase (public verlangt eine strengere).
        needed = CONFIRM_PUBLIC if privacy == "public" else CONFIRM_PRIVATE
        if confirm != needed:
            result["outcome"] = "needs_confirmation"
            result["message"] = (
                f"Confirmation phrase {needed!r} is required for "
                f"privacy_status={privacy}."
            )
            result["blocked_reasons"].append("confirmation_required")
            return result

        # 4) Credentials vorhanden? (nur Existenzprüfung, kein Token-Handling)
        if not self._credentials_configured():
            result["outcome"] = "not_ready"
            result["message"] = "YouTube credentials are not configured."
            result["blocked_reasons"].append("credentials_not_configured")
            return result

        # 5) Draft muss validiert & gültig sein.
        summary = self.validate_draft(draft)
        if not summary["is_valid"]:
            result["outcome"] = "not_ready"
            result["message"] = "Draft did not pass validation."
            result["blocked_reasons"] = list(summary["blocking_issues"])
            return result

        # 6) Idempotenz: schon hochgeladen? → nicht doppelt posten.
        if draft.get("external_post_id"):
            result["outcome"] = "not_ready"
            result["message"] = (
                "Draft already has an external_post_id — refusing to upload twice."
            )
            result["blocked_reasons"].append("already_uploaded")
            return result

        # 7) Alle Vorbedingungen erfüllt — ABER echter Upload ist (bewusst)
        #    noch nicht implementiert. KEIN Fake-Erfolg, KEIN Statuswechsel.
        result["outcome"] = "not_implemented"
        result["message"] = (
            "All preconditions met, but the real YouTube upload is not "
            "implemented yet (Phase 1: dry-run only). No upload was performed "
            "and the draft status is unchanged."
        )
        return result

    # ---- OAuth-Readiness (Phase 2) --------------------------------------
    # Rein informativ & sicher: prüft, OB ein OAuth/Upload später möglich wäre.
    # Es werden NIE Secrets/Tokens gelesen, ausgegeben oder geloggt.

    def credentials_readiness(self) -> dict:
        return {
            "configured": self._credentials_configured(),
            "file_exists": bool(self.settings.youtube_credentials_configured),
            "basename": self._credentials_basename(),  # nur Dateiname, nie Pfad
        }

    def token_readiness(self) -> dict:
        """Token-Store-Status (nur Status-Strings, keine Token-Werte)."""
        return self.token_store.get_summary()

    def overall_readiness(self) -> dict:
        """Vollständige, sichere Readiness-Übersicht für die API/UI.

        Die OAuth-Teilaussagen (can_start_auth, redirect_uri, oauth_flow_status)
        stammen aus dem OAuth-Flow-Skelett (`youtube_oauth`) — eine einzige
        Quelle der Wahrheit für Draft- UND globalen OAuth-Status."""
        enabled = self._feature_enabled()
        oauth_enabled = self._oauth_enabled()
        creds = self.credentials_readiness()
        tok = self.token_readiness()

        blocked_reasons: list[str] = []
        warnings: list[str] = []
        next_steps: list[str] = []

        if not creds["configured"]:
            blocked_reasons.append("credentials_not_configured")
            next_steps.append(
                "Set CLIPFORGE_YOUTUBE_CLIENT_SECRETS to your OAuth client "
                "secrets file path."
            )
        elif not creds["file_exists"]:
            blocked_reasons.append("credentials_file_missing")
            next_steps.append(
                "Client secrets file not found at the configured path."
            )

        if not tok["store_available"]:
            blocked_reasons.append("token_store_unavailable")
            next_steps.append(
                "Install the 'keyring' package and configure an OS keychain "
                "backend — there is no plaintext fallback."
            )
        else:
            status = tok["token_status"]
            if status == "not_authenticated":
                next_steps.append(
                    "Authorize via the YouTube OAuth flow "
                    "(Phase 2: flow not yet implemented)."
                )
            elif status == "invalid_token":
                warnings.append("stored_token_unreadable_or_corrupt")
                next_steps.append(
                    "Clear the stored YouTube token and re-authorize."
                )

        if not oauth_enabled:
            warnings.append("oauth_actions_disabled")
            next_steps.append(
                "Set CLIPFORGE_ENABLE_YOUTUBE_OAUTH=true to enable OAuth actions."
            )

        # Single source of truth für den OAuth-Status: das Flow-Skelett.
        oauth_status = self._oauth_status()
        can_attempt_oauth = bool(oauth_status["can_start_auth"])

        # Der Flow selbst kann jetzt eine Consent-URL erzeugen (Phase 2b), führt
        # aber weiterhin KEINEN echten Token-Exchange/Upload aus.
        oauth_flow_status = "ready_to_start" if can_attempt_oauth else "blocked"

        # Echter Upload bleibt in Phase 2/2b IMMER unmöglich.
        next_steps.append("Real upload stays disabled until Phase 3.")

        return {
            "platform": self.platform,
            "enabled": enabled,
            "oauth_enabled": oauth_enabled,
            "credentials_configured": creds["configured"],
            "credentials_file_exists": creds["file_exists"],
            "credentials_file_basename": creds["basename"],
            "token_store_available": tok["store_available"],
            "token_present": tok["token_present"],
            "token_status": tok["token_status"],
            "required_scope": REQUIRED_SCOPE,
            "redirect_uri": oauth_status["redirect_uri"],  # kein Secret (Loopback)
            "can_attempt_oauth": can_attempt_oauth,
            "can_start_auth": can_attempt_oauth,
            "can_attempt_upload": False,  # Phase 2/2b: niemals
            "blocked_reasons": blocked_reasons,
            "warnings": warnings,
            "next_steps": next_steps,
            "upload_status": "not_implemented",
            "oauth_flow_status": oauth_flow_status,
        }

    def _oauth_status(self) -> dict:
        """OAuth-Status aus dem Flow-Skelett (readiness) — nur Metadaten,
        keine Tokens/Secrets. Ein Wegwerf-State-Store genügt hier."""
        from .youtube_oauth import (
            OAuthStateStore,
            YouTubeOAuthConfig,
            YouTubeOAuthService,
        )

        service = YouTubeOAuthService(
            config=YouTubeOAuthConfig.from_settings(self.settings),
            token_store=self.token_store,
            state_store=OAuthStateStore(),
        )
        return service.readiness()

    def start_auth(self) -> dict:
        """OAuth-Flow starten — in Phase 2 bewusst NICHT ausgeführt.

        Öffnet KEINEN Browser, kontaktiert Google NICHT, speichert nichts.
        Gibt nur sichere Anweisungen/Status zurück (keine Secrets)."""
        readiness = self.overall_readiness()
        if not self._oauth_enabled():
            return {
                "started": False,
                "status": "oauth_disabled",
                "message": (
                    "YouTube OAuth is disabled. Set CLIPFORGE_ENABLE_YOUTUBE_OAUTH="
                    "true to work on the OAuth flow."
                ),
                "readiness": readiness,
            }
        return {
            "started": False,
            "status": "not_implemented_auth_flow",
            "message": (
                "OAuth prerequisites are checked, but the interactive Google "
                "OAuth flow is not implemented in this phase. No browser was "
                "opened and no token was created."
            ),
            "required_scope": REQUIRED_SCOPE,
            "readiness": readiness,
        }

    def logout(self) -> dict:
        """Löscht ein evtl. gespeichertes Token (idempotent, ohne Leak)."""
        return self.token_store.delete_token()
