"""Publishing-Ergänzungen des Studios: Plattform-Readiness, Planung,
Direktveröffentlichung und manuell bestätigte Veröffentlichung.

Sicherheitsprinzip: Nichts wird ohne ausdrückliche Bestätigung des Nutzers
veröffentlicht. Sofort-Posts brauchen `confirm=true` im Aufruf; geplante
Posts eine je Entwurf gespeicherte Freigabe (Zeitpunkt + Einstellungen).
Fehlgeschlagene Posts werden NICHT automatisch wiederholt (Doppel-Post-Gefahr).
Fallback bleibt das Export-Pack.
"""

from __future__ import annotations

import datetime
import os

from ..publishing import apply_publish_state, list_drafts, load_draft
from .storage import new_id, now_iso
from .errors import StudioError
from .safe_fetch import validate_url
from .social import X_COST_PER_VIDEO_POST

# Entwurfs-Plattform → Konto-Plattform für die Direktveröffentlichung
DIRECT = {"tiktok": "tiktok", "instagram_reels": "instagram", "x": "x"}
_SETUP = {
    "instagram": ["Instagram-Business- oder Creator-Konto", "Meta-App mit „Instagram API mit "
                  "Instagram-Login“ anlegen (developers.facebook.com), Berechtigung "
                  "instagram_business_content_publish (für fremde Konten: App-Review)",
                  "INSTAGRAM_APP_ID und INSTAGRAM_APP_SECRET setzen, HTTPS-Weiterleitung eintragen",
                  "Konto unter Studio → Einrichtung verbinden"],
    "x": ["X-Entwicklerkonto mit Nutzungsabrechnung (kostenpflichtig je Post)",
          "OAuth-2.0-App mit Schreibrechten, Scopes tweet.write media.write offline.access",
          "X_CLIENT_ID und X_CLIENT_SECRET setzen", "Konto unter Studio → Einrichtung verbinden"],
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
    from . import accounts
    tt = accounts.status("tiktok")
    tt_steps = {
        "not_configured": ["TikTok-Entwickler-App anlegen (developers.tiktok.com), Content Posting API "
                           "mit Scope video.upload aktivieren",
                           "TIKTOK_CLIENT_KEY und TIKTOK_CLIENT_SECRET setzen",
                           "Konto unter Studio → Einrichtung verbinden"],
        "not_connected": ["Konto unter Studio → Einrichtung verbinden"],
        "expired": ["TikTok-Konto neu verbinden"],
        "connected": [],
    }[tt["state"]]
    out.append({
        "platform": "tiktok", "state": "ready" if tt["state"] == "connected" else "not_connected",
        "adapter": "tiktok_inbox_upload", "upload_visibility": "tiktok_drafts",
        "oauth_ready": tt["state"] != "not_configured", "setup_steps": tt_steps,
        "fallback": "export_pack", "live_verified": False,
        "note": ("Upload in deine TikTok-Entwürfe; veröffentlichen tust du selbst in der "
                 "TikTok-App. Gegen die echte API noch ungetestet.")})
    for platform, acct in (("instagram_reels", "instagram"), ("x", "x")):
        st = accounts.status(acct)
        steps = {"not_configured": _SETUP[acct],
                 "not_connected": ["Konto unter Studio → Einrichtung verbinden"],
                 "expired": ["Konto neu verbinden"], "connected": []}[st["state"]]
        out.append({
            "platform": platform, "state": "ready" if st["state"] == "connected" else "not_connected",
            "adapter": f"{acct}_direct_post", "upload_visibility": "public",
            "oauth_ready": st["state"] != "not_configured", "setup_steps": steps,
            "fallback": "export_pack", "live_verified": False,
            "cost_per_post_usd": X_COST_PER_VIDEO_POST if acct == "x" else 0.0,
            "note": ("Öffentliche Veröffentlichung nur nach deiner Bestätigung. "
                     "Gegen die echte API noch ungetestet.")})
    return out


def draft_state(draft: dict, readiness: list[dict]) -> str:
    """Eindeutiger Anzeigezustand eines Drafts."""
    status = draft.get("status")
    if status == "published":
        return "published"
    if status == "failed":
        return "failed"
    if draft.get("upload_state") == "in_tiktok_drafts":
        return "in_platform_drafts"
    if draft.get("upload_state") == "uploading" and draft.get("publish_platform") in DIRECT:
        return "uploading"
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
    """Markiert fällige geplante Drafts als `due`. Lädt selbst nichts hoch;
    Einträge mit gespeicherter Freigabe (`auto_publish`) bekommen `auto=True`,
    der Aufrufer startet dann den Post."""
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
                        "platform": draft.get("platform"),
                        "auto": bool((draft.get("auto_publish") or {}).get("approved_at"))})
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


# ------------------------------------------------------------- TikTok

def tiktok_prepare(job_dir: str, publishing_id: str, confirm: bool) -> dict:
    """Prüft alles VOR dem Upload. Idempotent: läuft schon/ist fertig → kein zweiter Upload."""
    from . import accounts
    draft = load_draft(job_dir, publishing_id)
    if draft is None:
        raise StudioError("draft_not_found", "Publishing-Draft nicht gefunden.", 404)
    if draft.get("platform") != "tiktok":
        raise StudioError("wrong_platform", "Dieser Entwurf ist nicht für TikTok.", 409)
    if not confirm:
        raise StudioError("confirmation_required",
                          "Bitte ausdrücklich bestätigen (confirm=true), dass das Video in deine "
                          "TikTok-Entwürfe hochgeladen werden soll.", 400)
    if draft.get("publish_platform") == "tiktok" and draft.get("upload_state") in (
            "uploading", "in_tiktok_drafts") or draft.get("status") == "published":
        return {"already": True, "draft": draft}
    if accounts.status("tiktok")["state"] != "connected":
        raise StudioError("platform_not_connected", "TikTok ist nicht verbunden.", 409)
    mp4 = draft.get("mp4_path") or ""
    if not mp4 or not os.path.isfile(mp4):
        raise StudioError("video_missing", "Die Videodatei dieses Entwurfs fehlt.", 409)
    draft = apply_publish_state(job_dir, publishing_id, {
        "status": "publishing", "publish_platform": "tiktok", "upload_state": "uploading",
        "publish_started_at": now_iso(), "error": None, "publish_attempt_id": new_id()})
    return {"already": False, "draft": draft}


def tiktok_upload(job_dir: str, publishing_id: str, progress=None) -> dict:
    from . import accounts
    draft = load_draft(job_dir, publishing_id)
    try:
        publish_id = accounts.upload_to_inbox(draft["mp4_path"], progress)
    except StudioError as exc:
        apply_publish_state(job_dir, publishing_id, {
            "status": "failed", "upload_state": "failed",
            "error": exc.message, "last_error_code": exc.code})
        raise
    apply_publish_state(job_dir, publishing_id, {
        "external_post_id": publish_id, "upload_state": "uploaded",
        "last_upload_activity_at": now_iso()})
    return tiktok_refresh(job_dir, publishing_id)


def tiktok_refresh(job_dir: str, publishing_id: str) -> dict:
    """Status bei TikTok abfragen und ehrlich übernehmen."""
    from . import accounts
    draft = load_draft(job_dir, publishing_id)
    if draft is None:
        raise StudioError("draft_not_found", "Publishing-Draft nicht gefunden.", 404)
    publish_id = draft.get("external_post_id")
    if draft.get("publish_platform") != "tiktok" or not publish_id:
        raise StudioError("not_uploaded", "Dieser Entwurf wurde noch nicht an TikTok übergeben.", 409)
    st = accounts.fetch_status(publish_id)
    updates: dict = {"last_upload_activity_at": now_iso()}
    if st["state"] == "published":
        updates.update(status="published", upload_state="published", publish_source="tiktok",
                       published_at=draft.get("published_at") or now_iso())
        if st.get("post_id"):
            updates["external_video_id"] = st["post_id"]
    elif st["state"] == "in_tiktok_drafts":
        updates.update(status="publishing", upload_state="in_tiktok_drafts")
    elif st["state"] == "failed":
        updates.update(status="failed", upload_state="failed",
                       error=f"TikTok: {str(st.get('fail_reason') or 'fehlgeschlagen')[:160]}")
    return {"draft": apply_publish_state(job_dir, publishing_id, updates), "tiktok": st}


# ------------------------------------------------------- Direktveröffentlichung

def _caption(draft: dict, limit: int) -> str:
    from .social import caption
    return caption(draft.get("title") or "", draft.get("description") or draft.get("caption") or "",
                   list(draft.get("hashtags") or []), limit)


def _check_options(platform: str, options: dict, confirm_cost: bool) -> dict:
    from .social import TT_PRIVACY
    opts = {}
    if platform == "tiktok":
        privacy = options.get("privacy_level")
        if privacy not in TT_PRIVACY:
            raise StudioError("validation_error",
                              "Bitte die TikTok-Sichtbarkeit wählen (privacy_level).")
        opts = {"privacy_level": privacy,
                **{k: bool(options.get(k)) for k in ("disable_comment", "disable_duet",
                                                     "disable_stitch")}}
    elif platform == "instagram_reels":
        opts = {"share_to_feed": bool(options.get("share_to_feed", True))}
    elif platform == "x" and not confirm_cost:
        from .social import X_COST_PER_VIDEO_POST
        raise StudioError("cost_confirmation_required",
                          f"Ein Video-Post auf X kostet laut Nutzungsabrechnung ca. "
                          f"{X_COST_PER_VIDEO_POST:.3f} USD. Bitte bestätigen (confirm_cost=true).",
                          402, {"estimated_usd": X_COST_PER_VIDEO_POST})
    return opts


def _ready_draft(job_dir: str, publishing_id: str) -> tuple[dict, str]:
    from . import accounts
    draft = load_draft(job_dir, publishing_id)
    if draft is None:
        raise StudioError("draft_not_found", "Publishing-Draft nicht gefunden.", 404)
    platform = draft.get("platform")
    if platform not in DIRECT:
        raise StudioError("wrong_platform", "Für diese Plattform gibt es keine Direktveröffentlichung.", 409)
    if accounts.status(DIRECT[platform])["state"] != "connected":
        raise StudioError("platform_not_connected", f"{platform} ist nicht verbunden.", 409)
    mp4 = draft.get("mp4_path") or ""
    if not mp4 or not os.path.isfile(mp4):
        raise StudioError("video_missing", "Die Videodatei dieses Entwurfs fehlt.", 409)
    return draft, platform


def direct_prepare(job_dir: str, publishing_id: str, *, confirm: bool, options: dict | None = None,
                   confirm_cost: bool = False, approval: dict | None = None) -> dict:
    """Prüft alles VOR dem Post. Idempotent (kein zweiter Post für denselben Entwurf)."""
    if not confirm:
        raise StudioError("confirmation_required",
                          "Bitte ausdrücklich bestätigen (confirm=true), dass das Video "
                          "veröffentlicht werden soll.", 400)
    draft = load_draft(job_dir, publishing_id)
    if draft and (draft.get("status") == "published" or (
            draft.get("publish_mode") == "direct" and draft.get("upload_state") == "uploading")):
        return {"already": True, "draft": draft}
    draft, platform = _ready_draft(job_dir, publishing_id)
    opts = _check_options(platform, options or {}, confirm_cost)
    draft = apply_publish_state(job_dir, publishing_id, {
        "status": "publishing", "publish_platform": platform, "publish_mode": "direct",
        "publish_attempt_id": new_id(),
        "upload_state": "uploading", "publish_started_at": now_iso(), "error": None,
        "publish_options": opts,
        "publish_approval": approval or {"source": "sofort", "approved_at": now_iso()}})
    return {"already": False, "draft": draft}


def direct_publish(job_dir: str, publishing_id: str, progress=None) -> dict:
    """Führt den Post aus. Bei Fehler: Status failed, KEIN automatischer neuer Versuch."""
    from . import social
    draft = load_draft(job_dir, publishing_id)
    platform, opts = draft.get("publish_platform"), draft.get("publish_options") or {}
    try:
        if platform == "tiktok":
            pid = social.tiktok_direct_post(draft["mp4_path"], title=_caption(draft, 2200),
                                            progress=progress, **opts)
            apply_publish_state(job_dir, publishing_id, {"external_post_id": pid,
                                                         "upload_state": "uploaded"})
            return tiktok_refresh(job_dir, publishing_id)["draft"]
        if platform == "instagram_reels":
            media_id = social.instagram_publish(draft["mp4_path"], text=_caption(draft, 2200),
                                                progress=progress, **opts)
            url = None
            try:
                url = social.instagram_metrics(media_id).get("url")
            except StudioError:
                pass
        elif platform == "x":
            media_id = social.x_post(draft["mp4_path"], text=_caption(draft, 280), progress=progress)
            url = f"https://x.com/i/status/{media_id}"
        else:
            raise StudioError("wrong_platform", "Unbekannte Plattform.", 409)
    except StudioError as exc:
        apply_publish_state(job_dir, publishing_id, {
            "status": "failed", "upload_state": "failed", "error": exc.message,
            "last_error_code": exc.code})
        raise
    return apply_publish_state(job_dir, publishing_id, {
        "status": "published", "upload_state": "published", "publish_source": platform,
        "external_post_id": media_id, "external_url": url, "published_at": now_iso(),
        "schedule_state": None})


def schedule_direct(job_dir: str, publishing_id: str, *, at: str, approve: bool,
                    options: dict | None = None, confirm_cost: bool = False) -> dict:
    """Plant eine automatische Veröffentlichung — nur mit ausdrücklicher Freigabe."""
    if not approve:
        raise StudioError("confirmation_required",
                          "Bitte ausdrücklich freigeben (approve=true), dass ClipForge zum "
                          "geplanten Zeitpunkt automatisch veröffentlicht.", 400)
    when = _parse(at)
    now = datetime.datetime.now(datetime.timezone.utc)
    if when is None or when <= now + datetime.timedelta(minutes=1):
        raise StudioError("validation_error", "Der Zeitpunkt muss in der Zukunft liegen.")
    draft, platform = _ready_draft(job_dir, publishing_id)
    if draft.get("status") == "published":
        raise StudioError("already_published", "Bereits veröffentlicht.", 409)
    opts = _check_options(platform, options or {}, confirm_cost)
    return apply_publish_state(job_dir, publishing_id, {
        "status": "scheduled", "scheduled_at": when.isoformat(timespec="seconds"),
        "schedule_state": None,
        "auto_publish": {"approved_at": now_iso(), "options": opts, "confirm_cost": confirm_cost,
                         "platform": platform}})


def cancel_schedule(job_dir: str, publishing_id: str) -> dict:
    draft = load_draft(job_dir, publishing_id)
    if draft is None:
        raise StudioError("draft_not_found", "Publishing-Draft nicht gefunden.", 404)
    if draft.get("status") != "scheduled":
        raise StudioError("not_scheduled", "Dieser Entwurf ist nicht geplant.", 409)
    return apply_publish_state(job_dir, publishing_id, {
        "status": "draft", "scheduled_at": None, "schedule_state": None, "auto_publish": None})
