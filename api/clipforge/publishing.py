"""Publishing Planner — lokale Publishing-Drafts OHNE Plattform-Anbindung.

Safe-MVP (siehe docs/PUBLISHING_AGENT_PLAN.md):
  - Drafts anlegen/listen/bearbeiten/löschen, lokal als JSON pro Draft.
  - Validierung (MP4 da, 9:16, Titel/Caption, keine Viralitätsversprechen).
  - Publishing Pack (MP4 + Metadaten + Texte) als lokaler ZIP-Export.

HART AUSGESCHLOSSEN in diesem Modul:
  - kein OAuth, keine Token-Speicherung
  - kein Upload zu TikTok/Instagram/YouTube, keine externen API-Calls
  - kein Hintergrund-Scheduling (scheduled_at ist nur gespeicherte Metadaten)

Statusmodell: draft → ready → scheduled → publishing → published / failed /
canceled. Die Zustände publishing/published/failed sind für den späteren
echten Publisher reserviert und hier NICHT setzbar.
"""

from __future__ import annotations

import datetime
import glob
import json
import os
import re
import shutil
import subprocess
import uuid
from typing import Any

from .rerender import manual_export_path, list_manual_exports

PUBLISHING_DIR_NAME = "publishing"

PLATFORMS = ("youtube_shorts", "tiktok", "instagram_reels")

STATUSES = (
    "draft", "ready", "scheduled", "publishing", "published", "failed", "canceled",
)
# Nur diese Status darf der Nutzer im Planner setzen (Rest: echter Publisher).
USER_SETTABLE_STATUSES = ("draft", "ready", "scheduled", "canceled")

# Formulierungen, die wir NIE in Publishing-Texten mitgeben (keine falschen
# Versprechen). Case-insensitive Teilstring-Suche.
_FORBIDDEN_CLAIMS = (
    "garantiert viral", "viralität garantiert", "viral garantiert",
    "guaranteed viral", "guaranteed to go viral", "100% viral",
)

# Statische Plattform-Hinweise für das Publishing Pack (Quelle: offizielle
# Doku, Stand siehe docs/PUBLISHING_AGENT_PLAN.md — kein API-Call).
PLATFORM_NOTES = {
    "youtube_shorts": (
        "YouTube Shorts (manueller Upload):\n"
        "- Hochformat 9:16, #Shorts im Titel/Beschreibung hilft der Einordnung.\n"
        "- Upload per API wäre möglich (videos.insert), aber unverifizierte\n"
        "  API-Projekte laden nur als 'privat' hoch — daher hier nur Pack.\n"
        "- Titel + Beschreibung aus diesem Pack einfügen, Sichtbarkeit wählen,\n"
        "  optional geplantes Veröffentlichungsdatum im YouTube Studio setzen."
    ),
    "tiktok": (
        "TikTok (manueller Upload):\n"
        "- Caption + Hashtags aus diesem Pack einfügen.\n"
        "- Offizielle Content Posting API erfordert App-Audit (video.publish);\n"
        "  ohne Audit nur private Posts — daher hier nur Pack.\n"
        "- Pinned Comment nach dem Posten manuell anheften."
    ),
    "instagram_reels": (
        "Instagram Reels (manueller Upload):\n"
        "- Caption + Hashtags aus diesem Pack einfügen.\n"
        "- Offizielle Graph API braucht Professional-Account und ein öffentlich\n"
        "  erreichbares Video-URL-Hosting — passt nicht zu local-first, daher Pack.\n"
        "- Pinned Comment nach dem Posten manuell anheften."
    ),
}

_ID_RE = re.compile(r"^[a-f0-9]{12}$")


class PublishingError(Exception):
    """Nutzerfehler (ungültige Eingabe / unsichere ID) — im API-Layer → 400."""


def _now() -> str:
    return datetime.datetime.now(datetime.timezone.utc).isoformat()


def publishing_dir(job_dir: str) -> str:
    return os.path.join(job_dir, PUBLISHING_DIR_NAME)


def _safe_publishing_id(publishing_id: str) -> bool:
    return bool(publishing_id) and bool(_ID_RE.match(publishing_id))


def _draft_path(job_dir: str, publishing_id: str) -> str:
    if not _safe_publishing_id(publishing_id):
        raise PublishingError(f"Ungültige publishing_id: {publishing_id!r}")
    path = os.path.join(publishing_dir(job_dir), f"{publishing_id}.json")
    # Defense-in-depth: Ergebnis muss strikt im publishing/-Ordner liegen.
    root = os.path.realpath(publishing_dir(job_dir))
    if not os.path.realpath(path).startswith(root + os.sep):
        raise PublishingError("Pfad außerhalb des Publishing-Ordners.")
    return path


# ==========================================================================
# Quelle auflösen (Auto-Clip oder manueller Export) + Texte vorbefüllen
# ==========================================================================

def _load_clips_json(job_dir: str) -> dict | None:
    path = os.path.join(job_dir, "clips.json")
    if not os.path.exists(path):
        return None
    try:
        with open(path, "r", encoding="utf-8") as fh:
            return json.load(fh)
    except (OSError, ValueError):
        return None


def _resolve_auto_clip(job_dir: str, clip_index: int) -> tuple[str, dict]:
    """(mp4_path, clip_dict) für den 1-basierten Auto-Clip-Index."""
    cj = _load_clips_json(job_dir)
    clips = (cj or {}).get("clips") or []
    if not clips:
        raise PublishingError("Keine Auto-Clips vorhanden (clips.json fehlt/leer).")
    if not (1 <= clip_index <= len(clips)):
        raise PublishingError(f"Clip-Index {clip_index} existiert nicht (1–{len(clips)}).")
    clip = clips[clip_index - 1]
    out = clip.get("output_path") or ""
    # output_path kann absolut sein (alter Job-Ordner) → auf Basename im
    # aktuellen job_dir zurückfallen; niemals außerhalb des job_dir lesen.
    candidates = []
    if out:
        real = os.path.realpath(out)
        if real.startswith(os.path.realpath(job_dir) + os.sep):
            candidates.append(real)
        candidates.append(os.path.join(job_dir, os.path.basename(out)))
    for path in candidates:
        if os.path.exists(path):
            return path, clip
    # letzter Versuch: Namensschema clip_NN_*.mp4
    matches = sorted(glob.glob(os.path.join(job_dir, f"clip_{clip_index:02d}_*.mp4")))
    if matches:
        return matches[0], clip
    return "", clip  # fehlende MP4 ist ein Validierungs-, kein Erstellungsfehler


def _resolve_manual_export(job_dir: str, export_id: str) -> str:
    path = manual_export_path(job_dir, export_id)
    if path is None:
        raise PublishingError(f"Ungültige manual_export_id: {export_id!r}")
    return path if os.path.exists(path) else ""


def _prefill_from_content_package(clip: dict | None, platform: str) -> dict:
    """Titel/Caption/Beschreibung/Hashtags aus dem Content-Paket des Clips."""
    out = {"title": "", "caption": "", "description": "", "hashtags": [],
           "pinned_comment": ""}
    cp = (clip or {}).get("content_package") or {}
    if not cp:
        return out
    hook = cp.get("primary_hook") or ""
    plat = cp.get(platform) or {}
    out["title"] = plat.get("title") or hook
    out["caption"] = plat.get("caption") or ""
    out["description"] = plat.get("description") or ""
    out["hashtags"] = list(plat.get("hashtags") or [])
    out["pinned_comment"] = plat.get("pinned_comment") or ""
    return out


# ==========================================================================
# CRUD
# ==========================================================================

def create_draft(
    job_dir: str,
    job_id: str,
    *,
    platform: str,
    source_type: str,
    source_clip_index: int | None = None,
    manual_export_id: str | None = None,
    title: str | None = None,
    caption: str | None = None,
    description: str | None = None,
    hashtags: list[str] | None = None,
    pinned_comment: str | None = None,
    scheduled_at: str | None = None,
) -> dict:
    if platform not in PLATFORMS:
        raise PublishingError(
            f"Ungültige Plattform {platform!r} (erlaubt: {', '.join(PLATFORMS)})."
        )
    clip: dict | None = None
    if source_type == "auto_clip":
        if not source_clip_index:
            raise PublishingError("source_clip_index fehlt für source_type=auto_clip.")
        mp4_path, clip = _resolve_auto_clip(job_dir, int(source_clip_index))
    elif source_type == "manual_export":
        if not manual_export_id:
            raise PublishingError("manual_export_id fehlt für source_type=manual_export.")
        mp4_path = _resolve_manual_export(job_dir, manual_export_id)
        # Texte aus dem Quell-Clip des Exports übernehmen (falls auffindbar)
        for exp in list_manual_exports(job_dir):
            if exp.get("export_id") == manual_export_id:
                idx = exp.get("source_clip_index")
                if isinstance(idx, int):
                    cj = _load_clips_json(job_dir) or {}
                    clips = cj.get("clips") or []
                    if 1 <= idx <= len(clips):
                        clip = clips[idx - 1]
                break
    else:
        raise PublishingError(
            f"Ungültiger source_type {source_type!r} (auto_clip | manual_export)."
        )

    pre = _prefill_from_content_package(clip, platform)
    now = _now()
    draft = {
        "publishing_id": uuid.uuid4().hex[:12],
        "job_id": job_id,
        "source_type": source_type,
        "source_clip_index": int(source_clip_index) if source_clip_index else None,
        "manual_export_id": manual_export_id,
        "mp4_path": mp4_path,
        "platform": platform,
        "title": title if title is not None else pre["title"],
        "caption": caption if caption is not None else pre["caption"],
        "description": description if description is not None else pre["description"],
        "hashtags": hashtags if hashtags is not None else pre["hashtags"],
        "pinned_comment": pinned_comment if pinned_comment is not None else pre["pinned_comment"],
        "scheduled_at": scheduled_at,
        "status": "draft",
        "validation": None,
        "created_at": now,
        "updated_at": now,
        "published_at": None,
        "external_post_id": None,  # erst mit echtem Publisher (später)
        "error": None,
    }
    os.makedirs(publishing_dir(job_dir), exist_ok=True)
    with open(_draft_path(job_dir, draft["publishing_id"]), "w", encoding="utf-8") as fh:
        json.dump(draft, fh, ensure_ascii=False, indent=2)
    return draft


def list_drafts(job_dir: str) -> list[dict]:
    pdir = publishing_dir(job_dir)
    if not os.path.isdir(pdir):
        return []
    out: list[dict] = []
    for path in glob.glob(os.path.join(pdir, "*.json")):
        try:
            with open(path, "r", encoding="utf-8") as fh:
                out.append(json.load(fh))
        except (OSError, ValueError):
            continue
    out.sort(key=lambda d: d.get("created_at") or "", reverse=True)
    return out


def load_draft(job_dir: str, publishing_id: str) -> dict | None:
    path = _draft_path(job_dir, publishing_id)
    if not os.path.exists(path):
        return None
    try:
        with open(path, "r", encoding="utf-8") as fh:
            return json.load(fh)
    except (OSError, ValueError):
        return None


_EDITABLE_FIELDS = (
    "platform", "title", "caption", "description", "hashtags",
    "pinned_comment", "scheduled_at", "status",
)


def update_draft(job_dir: str, publishing_id: str, patch: dict) -> dict:
    draft = load_draft(job_dir, publishing_id)
    if draft is None:
        raise FileNotFoundError(publishing_id)
    for key, value in patch.items():
        if key not in _EDITABLE_FIELDS or value is None:
            continue
        if key == "platform" and value not in PLATFORMS:
            raise PublishingError(f"Ungültige Plattform {value!r}.")
        if key == "status" and value not in USER_SETTABLE_STATUSES:
            raise PublishingError(
                f"Status {value!r} kann nicht manuell gesetzt werden "
                f"(erlaubt: {', '.join(USER_SETTABLE_STATUSES)})."
            )
        if key == "hashtags":
            if not isinstance(value, list):
                raise PublishingError("hashtags muss eine Liste sein.")
            value = [str(h) for h in value]
        draft[key] = value
    draft["updated_at"] = _now()
    with open(_draft_path(job_dir, publishing_id), "w", encoding="utf-8") as fh:
        json.dump(draft, fh, ensure_ascii=False, indent=2)
    return draft


def delete_draft(job_dir: str, publishing_id: str) -> bool:
    path = _draft_path(job_dir, publishing_id)
    if not os.path.exists(path):
        return False
    os.remove(path)
    return True


# ==========================================================================
# Publisher-Transitions (nur für den echten Publisher — NICHT nutzer-setzbar)
# ==========================================================================

# Felder, die AUSSCHLIESSLICH der echte Publisher (YouTubeUploadService) setzen
# darf. Der nutzerseitige update_draft() fasst diese NIE an.
_PUBLISHER_FIELDS = frozenset({
    "status", "external_post_id", "published_at", "error",
    "publish_attempt_id", "publish_started_at", "publish_completed_at",
    "publish_platform", "publish_attempt_count", "last_publish_error",
    "idempotency_state", "publish_attempts", "upload_progress",
})


def apply_publish_state(job_dir: str, publishing_id: str, updates: dict) -> dict:
    """Trusted Writer für Publisher-Statusübergänge + Idempotenzfelder.

    Umgeht bewusst die USER_SETTABLE_STATUSES-Sperre von update_draft(), ist
    aber auf `_PUBLISHER_FIELDS` beschränkt und speichert atomar (tmp+rename),
    damit ein Absturz mitten im Schreiben den Draft nicht beschädigt.

    Enthält NIE Tokens/Secrets — `error`/`last_publish_error` sind sanitisierte
    Fehlercodes/-texte (der Aufrufer stellt das sicher)."""
    draft = load_draft(job_dir, publishing_id)
    if draft is None:
        raise FileNotFoundError(publishing_id)
    for key, value in updates.items():
        if key not in _PUBLISHER_FIELDS:
            raise PublishingError(f"Feld {key!r} ist kein Publisher-Feld.")
        if key == "status" and value not in STATUSES:
            raise PublishingError(f"Ungültiger Status {value!r}.")
        draft[key] = value
    draft["updated_at"] = _now()
    path = _draft_path(job_dir, publishing_id)
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as fh:
        json.dump(draft, fh, ensure_ascii=False, indent=2)
    os.replace(tmp, path)  # atomar
    return draft


def _find_source_clip(job_dir: str, draft: dict) -> dict | None:
    """Rekonstruiert den Quell-Clip (für Content-Paket-Texte) — bestmöglich."""
    if draft.get("source_type") == "auto_clip" and draft.get("source_clip_index"):
        cj = _load_clips_json(job_dir) or {}
        clips = cj.get("clips") or []
        idx = draft["source_clip_index"]
        if 1 <= idx <= len(clips):
            return clips[idx - 1]
    elif draft.get("source_type") == "manual_export" and draft.get("manual_export_id"):
        for exp in list_manual_exports(job_dir):
            if exp.get("export_id") == draft["manual_export_id"]:
                idx = exp.get("source_clip_index")
                if isinstance(idx, int):
                    cj = _load_clips_json(job_dir) or {}
                    clips = cj.get("clips") or []
                    if 1 <= idx <= len(clips):
                        return clips[idx - 1]
                break
    return None


def duplicate_draft(
    job_dir: str,
    job_id: str,
    publishing_id: str,
    *,
    platform: str | None = None,
    copy_schedule: bool = False,
) -> dict:
    """Dupliziert einen Draft (neue publishing_id, Original bleibt unverändert).

    Wechselt die Plattform, versucht dafür die Texte aus dem Content-Paket
    der Quelle neu abzuleiten; ist die Quelle nicht rekonstruierbar, werden
    die Original-Texte übernommen und ein `warning` gesetzt.
    """
    original = load_draft(job_dir, publishing_id)
    if original is None:
        raise FileNotFoundError(publishing_id)

    new_platform = platform or original["platform"]
    if new_platform not in PLATFORMS:
        raise PublishingError(
            f"Ungültige Plattform {new_platform!r} (erlaubt: {', '.join(PLATFORMS)})."
        )

    warning: str | None = None
    if new_platform != original["platform"]:
        clip = _find_source_clip(job_dir, original)
        cp = (clip or {}).get("content_package") or {}
        if cp.get(new_platform):
            pre = _prefill_from_content_package(clip, new_platform)
            title, caption = pre["title"], pre["caption"]
            description, hashtags = pre["description"], pre["hashtags"]
            pinned_comment = pre["pinned_comment"]
        else:
            title, caption = original["title"], original["caption"]
            description, hashtags = original["description"], original["hashtags"]
            pinned_comment = original["pinned_comment"]
            warning = (
                "Konnte Texte nicht plattformspezifisch neu ableiten (Quelle/"
                "Content-Paket nicht rekonstruierbar) — Original-Texte übernommen."
            )
    else:
        title, caption = original["title"], original["caption"]
        description, hashtags = original["description"], original["hashtags"]
        pinned_comment = original["pinned_comment"]

    now = _now()
    new_draft = {
        "publishing_id": uuid.uuid4().hex[:12],
        "job_id": job_id,
        "source_type": original.get("source_type"),
        "source_clip_index": original.get("source_clip_index"),
        "manual_export_id": original.get("manual_export_id"),
        "mp4_path": original.get("mp4_path"),
        "platform": new_platform,
        "title": title,
        "caption": caption,
        "description": description,
        "hashtags": list(hashtags or []),
        "pinned_comment": pinned_comment,
        "scheduled_at": original.get("scheduled_at") if copy_schedule else None,
        "status": "draft",
        "validation": None,
        "created_at": now,
        "updated_at": now,
        "published_at": None,
        "external_post_id": None,
        "error": None,
        "duplicated_from": original["publishing_id"],
    }
    if warning:
        new_draft["warning"] = warning
    os.makedirs(publishing_dir(job_dir), exist_ok=True)
    with open(_draft_path(job_dir, new_draft["publishing_id"]), "w", encoding="utf-8") as fh:
        json.dump(new_draft, fh, ensure_ascii=False, indent=2)
    return validate_draft(job_dir, new_draft["publishing_id"])


# ==========================================================================
# Validierung
# ==========================================================================

def _probe_dimensions(mp4_path: str) -> tuple[int, int] | None:
    """(width, height) via ffprobe — None, wenn nicht bestimmbar."""
    if not shutil.which("ffprobe"):
        return None
    try:
        res = subprocess.run(
            ["ffprobe", "-v", "error", "-select_streams", "v:0",
             "-show_entries", "stream=width,height", "-of", "csv=p=0", mp4_path],
            capture_output=True, text=True, timeout=15,
        )
        w, h = res.stdout.strip().split(",")[:2]
        return int(w), int(h)
    except (OSError, ValueError, subprocess.SubprocessError):
        return None


def _contains_forbidden_claim(*texts: str) -> bool:
    joined = " ".join(t or "" for t in texts).lower()
    return any(claim in joined for claim in _FORBIDDEN_CLAIMS)


# --- Qualitäts-Richtwerte -------------------------------------------------
# Bewusst GROBE lokale Richtwerte (keine offiziellen Plattform-Limits!).
# Sollen nur auf ungewöhnlich lange/leere Texte hinweisen, nicht Plattform-
# regeln vorschreiben. Vor echtem Upload gelten die jeweiligen offiziellen
# Grenzen (siehe docs/PUBLISHING_AGENT_PLAN.md, TODOs).
_TITLE_SOFT_LIMIT = 100
_CAPTION_SOFT_LIMIT = 2200
_HASHTAGS_SOFT_LIMIT = 15


def _quality_hints(draft: dict) -> list[str]:
    hints: list[str] = []
    title = (draft.get("title") or "").strip()
    caption = (draft.get("caption") or "").strip()
    hashtags = draft.get("hashtags") or []
    if len(title) > _TITLE_SOFT_LIMIT:
        hints.append("title_too_long")
    if len(caption) > _CAPTION_SOFT_LIMIT:
        hints.append("caption_too_long")
    if len(hashtags) > _HASHTAGS_SOFT_LIMIT:
        hints.append("too_many_hashtags")
    if draft.get("platform") in ("tiktok", "instagram_reels") and not (
        draft.get("pinned_comment") or ""
    ).strip():
        hints.append("missing_pinned_comment")
    scheduled = draft.get("scheduled_at")
    if scheduled:
        try:
            dt = datetime.datetime.fromisoformat(str(scheduled).replace("Z", "+00:00"))
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=datetime.timezone.utc)
            if dt < datetime.datetime.now(datetime.timezone.utc):
                hints.append("scheduled_in_past")
        except ValueError:
            pass
    if not title and not caption:
        hints.append("weak_metadata")
    return hints


def build_validation_summary(draft: dict, checks: dict | None = None) -> dict:
    """Fasst Checkliste + Qualitäts-Hinweise zusammen (für UI + globale Liste).

    Nutzt gespeicherte `checks` (aus `validate_draft`), falls vorhanden;
    sonst best-effort ohne ffprobe-Aufruf (nur Dateipräsenz + Textfelder).
    `format_9_16` bleibt `None`, wenn es nie geprüft wurde (nicht blockierend).
    """
    checks = checks or {}
    mp4_path = draft.get("mp4_path") or ""
    mp4_exists = checks.get("mp4_exists")
    if mp4_exists is None:
        mp4_exists = bool(mp4_path) and os.path.exists(mp4_path)
    format_9_16 = checks.get("format_9_16")
    platform = draft.get("platform")
    platform_selected = platform in PLATFORMS
    title_present = checks.get("title_present")
    if title_present is None:
        title_present = bool((draft.get("title") or "").strip())
    caption_present = checks.get("caption_present")
    if caption_present is None:
        caption_present = bool((draft.get("caption") or "").strip())
    hashtags_present = checks.get("hashtags_present")
    if hashtags_present is None:
        hashtags_present = bool(draft.get("hashtags"))
    no_viral_guarantee = checks.get("no_virality_claim")
    if no_viral_guarantee is None:
        no_viral_guarantee = not _contains_forbidden_claim(
            draft.get("title", ""), draft.get("caption", ""),
            draft.get("description", ""), " ".join(draft.get("hashtags") or []),
        )
    safe_status = draft.get("status") not in ("publishing", "published", "failed")
    required_text_ok = title_present if platform == "youtube_shorts" else caption_present

    checklist = {
        "mp4_exists": mp4_exists,
        "format_9_16": format_9_16,
        "title_present": title_present,
        "caption_present": caption_present,
        "hashtags_present": hashtags_present,
        "platform_selected": platform_selected,
        "no_viral_guarantee": no_viral_guarantee,
        "safe_status": safe_status,
    }
    blocking: list[str] = []
    if not mp4_exists:
        blocking.append("mp4_exists")
    if not platform_selected:
        blocking.append("platform_selected")
    if not required_text_ok:
        blocking.append("required_text_present")
    if not no_viral_guarantee:
        blocking.append("no_viral_guarantee")
    if format_9_16 is False:
        blocking.append("format_9_16")
    if not safe_status:
        blocking.append("safe_status")

    quality_hints = _quality_hints(draft)
    return {
        "is_valid": len(blocking) == 0,
        "blocking_issues_count": len(blocking),
        "blocking_issues": blocking,
        "warnings_count": len(quality_hints),
        "checklist": checklist,
        "quality_hints": quality_hints,
    }


def validate_draft(job_dir: str, publishing_id: str) -> dict:
    """Prüft den Draft und speichert das Ergebnis im Draft (validation-Feld).

    Bestehen alle harten Checks → Status draft→ready. Fällt ein harter Check
    durch, geht ready→draft zurück (kein versehentliches 'ready').
    """
    draft = load_draft(job_dir, publishing_id)
    if draft is None:
        raise FileNotFoundError(publishing_id)

    mp4 = draft.get("mp4_path") or ""
    mp4_exists = bool(mp4) and os.path.exists(mp4)
    size_bytes = os.path.getsize(mp4) if mp4_exists else 0

    dims = _probe_dimensions(mp4) if mp4_exists else None
    if dims is None:
        format_9_16: bool | None = None if mp4_exists else False
    else:
        w, h = dims
        format_9_16 = h > 0 and abs((w / h) - (9 / 16)) <= 0.05

    platform = draft.get("platform")
    platform_valid = platform in PLATFORMS
    title_present = bool((draft.get("title") or "").strip())
    caption_present = bool((draft.get("caption") or "").strip())
    description_present = bool((draft.get("description") or "").strip())
    hashtags_present = bool(draft.get("hashtags"))
    no_virality_claim = not _contains_forbidden_claim(
        draft.get("title", ""), draft.get("caption", ""),
        draft.get("description", ""), " ".join(draft.get("hashtags") or []),
    )
    # Plattform-abhängige Textpflicht: YouTube braucht Titel, TikTok/Reels Caption.
    text_ok = title_present if platform == "youtube_shorts" else caption_present

    checks = {
        "mp4_exists": mp4_exists,
        "format_9_16": format_9_16,  # None = nicht bestimmbar (ffprobe fehlt)
        "file_size_bytes": size_bytes,
        "platform_valid": platform_valid,
        "title_present": title_present,
        "caption_present": caption_present,
        "description_present": description_present,
        "hashtags_present": hashtags_present,
        "no_virality_claim": no_virality_claim,
        "required_text_present": text_ok,
    }
    summary = build_validation_summary(draft, checks)
    passed = summary["is_valid"]
    validation = {
        "passed": passed, "checks": checks, "checked_at": _now(),
        "summary": summary,
    }
    draft["validation"] = validation
    if passed and draft.get("status") == "draft":
        draft["status"] = "ready"
    elif not passed and draft.get("status") == "ready":
        draft["status"] = "draft"
    draft["updated_at"] = _now()
    with open(_draft_path(job_dir, publishing_id), "w", encoding="utf-8") as fh:
        json.dump(draft, fh, ensure_ascii=False, indent=2)
    return draft


def draft_list_summary(draft: dict) -> dict:
    """Kompakte Zusammenfassung eines Drafts für Listen-Ansichten (job- und
    jobübergreifend). Läuft ohne ffprobe-Aufruf (nutzt gespeicherte Checks,
    falls vorhanden)."""
    validation = draft.get("validation") or {}
    checks = validation.get("checks") or {}
    summary = build_validation_summary(draft, checks)
    mp4_path = draft.get("mp4_path") or ""
    return {
        "publishing_id": draft["publishing_id"],
        "job_id": draft["job_id"],
        "source_type": draft.get("source_type"),
        "source_clip_index": draft.get("source_clip_index"),
        "manual_export_id": draft.get("manual_export_id"),
        "platform": draft.get("platform"),
        "title": draft.get("title"),
        "caption": draft.get("caption"),
        "hashtags": draft.get("hashtags") or [],
        "status": draft.get("status"),
        "scheduled_at": draft.get("scheduled_at"),
        "validation_summary": summary,
        "mp4_exists": bool(mp4_path) and os.path.exists(mp4_path),
        "created_at": draft.get("created_at"),
        "updated_at": draft.get("updated_at"),
    }


# ==========================================================================
# Publishing Pack (lokaler ZIP-Inhalt — KEIN Upload)
# ==========================================================================

def pack_contents(draft: dict) -> tuple[str, list[tuple[str, str]], dict]:
    """Baut den Pack-Inhalt: (mp4_pfad, [(arcname, text)], metadata-dict).

    Der API-Layer zippt das Ergebnis; hier passiert bewusst kein I/O außer
    dem, was schon im Draft steht.
    """
    platform = draft.get("platform") or ""
    hashtags = draft.get("hashtags") or []
    caption_lines = [draft.get("caption") or ""]
    if hashtags:
        caption_lines += ["", " ".join(hashtags)]
    texts: list[tuple[str, str]] = [
        ("caption.txt", "\n".join(caption_lines).strip() + "\n"),
        ("description.txt", (draft.get("description") or "") + "\n"),
        ("platform_notes.txt",
         PLATFORM_NOTES.get(platform, "Keine Hinweise für diese Plattform.") + "\n"),
    ]
    metadata = {
        "publishing_id": draft.get("publishing_id"),
        "job_id": draft.get("job_id"),
        "platform": platform,
        "title": draft.get("title"),
        "caption": draft.get("caption"),
        "description": draft.get("description"),
        "hashtags": hashtags,
        "pinned_comment": draft.get("pinned_comment"),
        "scheduled_at": draft.get("scheduled_at"),
        "status": draft.get("status"),
        "validation": draft.get("validation"),
        "created_at": draft.get("created_at"),
        "pack_created_at": _now(),
        "disclaimer": (
            "Kein automatischer Upload. Der Performance-Potential-Score ist "
            "eine Einschätzung, keine Garantie für Reichweite oder Viralität."
        ),
    }
    return draft.get("mp4_path") or "", texts, metadata
