"""Publishing-Ergänzungen des Studios: Plattform-Readiness, Planung, manuell
bestätigte Veröffentlichung.

Sicherheitsprinzip: Hier wird NIE etwas hochgeladen. Der einzige echte Upload
bleibt der bestehende, mehrfach abgesicherte PRIVATE-YouTube-Pfad. Für alle
anderen Plattformen gibt es bewusst keinen Upload-Adapter — der Fallback ist
das Export-Pack. „Veröffentlicht“ wird nur gesetzt, wenn der Nutzer das
ausdrücklich bestätigt (oder der YouTube-Pfad es belegt).
"""

from __future__ import annotations

import datetime
import os

from ..publishing import PLATFORMS, apply_publish_state, list_drafts, load_draft
from .errors import StudioError
from .safe_fetch import validate_url

_NO_ADAPTER = {
    "tiktok": "TikTok Content Posting API erfordert ein App-Audit; kein Adapter vorhanden.",
    "instagram_reels": "Instagram Graph API braucht öffentlich gehostete Videos; kein Adapter vorhanden.",
    "x": "X-API für Medien-Uploads ist kostenpflichtig; kein Adapter vorhanden.",
}


def platform_readiness(settings, youtube: dict | None) -> list[dict]:
    """Zustand je Plattform: ready | not_connected (+ Einrichtungsschritte)."""
    yt = youtube or {}
    yt_ready = bool(settings.enable_youtube_upload and yt.get("token_present")
                    and yt.get("client_secrets_configured"))
    steps = []
    if not settings.enable_youtube_upload:
        steps.append("CLIPFORGE_ENABLE_YOUTUBE_UPLOAD=true setzen")
    if not yt.get("oauth_enabled"):
        steps.append("CLIPFORGE_ENABLE_YOUTUBE_OAUTH=true setzen")
    if not yt.get("client_secrets_configured"):
        steps.append("CLIPFORGE_YOUTUBE_CLIENT_SECRETS auf die OAuth-Client-Datei zeigen lassen")
    if not yt.get("token_present"):
        steps.append("YouTube-Konto über den Publishing-Planner verbinden")
    out = [{
        "platform": "youtube_shorts", "state": "ready" if yt_ready else "not_connected",
        "adapter": "youtube_private_upload", "upload_visibility": "private",
        "oauth_ready": bool(yt.get("can_start_auth") or yt.get("token_present")),
        "setup_steps": [] if yt_ready else steps,
        "fallback": "export_pack",
        "note": "Upload ausschließlich als PRIVAT und nur nach ausdrücklicher Bestätigung.",
    }]
    for platform in PLATFORMS:
        if platform == "youtube_shorts":
            continue
        out.append({
            "platform": platform, "state": "not_connected", "adapter": None,
            "upload_visibility": None, "oauth_ready": False,
            "setup_steps": ["Export-Pack herunterladen und manuell hochladen"],
            "fallback": "export_pack", "note": _NO_ADAPTER[platform]})
    return out


def draft_state(draft: dict, readiness: list[dict]) -> str:
    """Eindeutiger Anzeigezustand eines Drafts."""
    status = draft.get("status")
    if status == "published":
        return "published"
    if status == "failed":
        return "failed"
    if status == "scheduled":
        return "due" if draft.get("schedule_state") == "due" else "scheduled"
    state = next((r["state"] for r in readiness if r["platform"] == draft.get("platform")),
                 "not_connected")
    return "ready" if state == "ready" else "not_connected"


def _parse(ts: str) -> datetime.datetime | None:
    try:
        dt = datetime.datetime.fromisoformat(str(ts).replace("Z", "+00:00"))
    except ValueError:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=datetime.timezone.utc)
    return dt


def scheduler_tick(registry, now: datetime.datetime) -> list[dict]:
    """Markiert fällige geplante Drafts als `due`. Lädt NIE etwas hoch."""
    due = []
    for job in registry.list():
        if not os.path.isdir(job.job_dir):
            continue
        for draft in list_drafts(job.job_dir):
            if draft.get("status") != "scheduled" or draft.get("schedule_state") == "due":
                continue
            when = _parse(draft.get("scheduled_at") or "")
            if when is None or when > now:
                continue
            apply_publish_state(job.job_dir, draft["publishing_id"], {
                "schedule_state": "due",
                "schedule_due_at": now.isoformat(timespec="seconds")})
            due.append({"job_id": job.id, "publishing_id": draft["publishing_id"],
                        "platform": draft.get("platform")})
    return due


def mark_published(job_dir: str, publishing_id: str, *, confirm: bool,
                   url: str | None = None, published_at: str | None = None) -> dict:
    """Nutzer bestätigt, dass ER den Post manuell veröffentlicht hat.

    Idempotent: ein bereits veröffentlichter Draft bleibt unverändert.
    """
    draft = load_draft(job_dir, publishing_id)
    if draft is None:
        raise StudioError("draft_not_found", "Publishing-Draft nicht gefunden.", 404)
    if not confirm:
        raise StudioError(
            "confirmation_required",
            "Bitte ausdrücklich bestätigen (confirm=true), dass der Beitrag manuell "
            "veröffentlicht wurde. ClipForge veröffentlicht nichts von selbst.", 400)
    if draft.get("status") == "published":
        return draft
    if url:
        validate_url(url)
    when = _parse(published_at) if published_at else None
    if published_at and when is None:
        raise StudioError("validation_error", "published_at ist kein gültiger Zeitstempel.")
    stamp = (when or datetime.datetime.now(datetime.timezone.utc)).isoformat(timespec="seconds")
    return apply_publish_state(job_dir, publishing_id, {
        "status": "published", "published_at": stamp, "publish_source": "manual",
        "external_url": url or None, "schedule_state": None})
