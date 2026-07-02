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

    def __init__(self, settings: Settings):
        self.settings = settings

    # ---- interne Helfer --------------------------------------------------

    def _feature_enabled(self) -> bool:
        return bool(self.settings.enable_youtube_upload)

    def _credentials_configured(self) -> bool:
        return bool(self.settings.youtube_credentials_configured)

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
