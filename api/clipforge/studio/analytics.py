"""Analytics: echte Ergebnisse je veröffentlichtem Draft + Remix.

Grundsatz: KEINE erfundenen Zahlen. Jede Metrik trägt ihre Herkunft:
  manual     – vom Nutzer eingetragen
  synced     – über einen Plattform-Adapter abgerufen
  estimated  – nur das Performance-Potenzial (Heuristik vor Veröffentlichung)
Fehlt ein Wert, bleibt er `null` (nie 0 als Platzhalter).
"""

from __future__ import annotations

import os

from ..publishing import list_drafts, load_draft
from .errors import StudioError
from .storage import now_iso, read_json, require_id, studio_dir, write_json_atomic

FIELDS = ("views", "likes", "comments", "shares", "reach", "saves")
# Pflicht: mindestens einer der Basiswerte; der Rest ist optional (nicht jede
# Plattform liefert ihn — es werden nur gelieferte Werte gespeichert)


def _path(job_id: str, publishing_id: str) -> str:
    base = os.path.join(studio_dir(), "analytics")
    os.makedirs(base, exist_ok=True)
    safe_job = "".join(c for c in job_id if c.isalnum())[:32]
    if not safe_job or safe_job != job_id:
        raise StudioError("invalid_id", "Ungültige Job-ID.", 400)
    return os.path.join(base, f"{safe_job}_{require_id(publishing_id, 'Publishing-ID')}.json")


def _clean(values: dict) -> dict:
    out = {}
    for key in FIELDS:
        value = values.get(key)
        if value in (None, ""):
            out[key] = None
            continue
        try:
            number = int(value)
        except (TypeError, ValueError) as exc:
            raise StudioError("validation_error", f"'{key}' muss eine ganze Zahl sein.") from exc
        if number < 0:
            raise StudioError("validation_error", f"'{key}' darf nicht negativ sein.")
        out[key] = number
    if all(v is None for v in out.values()):
        raise StudioError("validation_error", "Bitte mindestens einen Wert angeben.")
    return out


def _require_published(job_dir: str, publishing_id: str) -> dict:
    draft = load_draft(job_dir, publishing_id)
    if draft is None:
        raise StudioError("draft_not_found", "Publishing-Draft nicht gefunden.", 404)
    if draft.get("status") != "published":
        raise StudioError(
            "draft_not_published",
            "Metriken gibt es nur für veröffentlichte Entwürfe. Markiere den Entwurf "
            "zuerst als veröffentlicht.", 409)
    return draft


def record(job_id: str, job_dir: str, publishing_id: str, values: dict, source: str) -> dict:
    _require_published(job_dir, publishing_id)
    entry = {**_clean(values), "source": source, "captured_at": now_iso()}
    path = _path(job_id, publishing_id)
    data = read_json(path, None) or {"job_id": job_id, "publishing_id": publishing_id,
                                     "entries": []}
    data["entries"] = (data["entries"] + [entry])[-200:]
    write_json_atomic(path, data)
    return entry


def engagement(entry: dict) -> float | None:
    """(Likes + Kommentare + Shares) / Aufrufe — nur wenn Aufrufe bekannt sind."""
    views = entry.get("views")
    if not views:
        return None
    acts = sum(entry.get(k) or 0 for k in ("likes", "comments", "shares"))
    return round(acts / views, 4)


def history(job_id: str, publishing_id: str) -> list[dict]:
    data = read_json(_path(job_id, publishing_id), None) or {}
    return data.get("entries") or []


def default_youtube_fetcher(upload_service):
    """Echter Abruf über die YouTube Data API (nur mit verbundenem Konto).
    In Tests wird immer ein Fake injiziert."""
    def _fetch(video_id: str) -> dict:
        from googleapiclient.discovery import build  # type: ignore
        creds, err = upload_service.prepare_credentials()
        if err:
            raise RuntimeError("credentials_unavailable")
        creds, err = upload_service.refresh_credentials_if_needed(creds)
        if err:
            raise RuntimeError("credentials_unavailable")
        youtube = build("youtube", "v3", credentials=creds, cache_discovery=False)
        resp = youtube.videos().list(part="statistics", id=video_id).execute()
        for item in resp.get("items") or []:
            if item.get("id") == video_id:
                stats = item.get("statistics") or {}
                return {"views": stats.get("viewCount"), "likes": stats.get("likeCount"),
                        "comments": stats.get("commentCount")}
        raise LookupError("video_not_found")
    return _fetch


def sync(job_id: str, job_dir: str, publishing_id: str, fetchers: dict) -> dict:
    """Ruft Metriken über den Plattform-Adapter ab (falls vorhanden)."""
    draft = _require_published(job_dir, publishing_id)
    platform = draft.get("platform")
    fetcher = fetchers.get(platform)
    post_id = draft.get("external_post_id")
    if platform == "tiktok":  # Direct Post: publish_id ≠ Video-ID
        post_id = draft.get("external_video_id")
    if fetcher is None or not post_id:
        raise StudioError(
            "metrics_unavailable",
            "Für diesen Entwurf gibt es keinen Metrik-Abruf (Plattform nicht verbunden "
            "oder manuell veröffentlicht). Bitte Werte manuell eintragen.", 409,
            {"platform": platform, "fallback": "manual"})
    try:
        values = fetcher(post_id)
    except Exception as exc:  # noqa: BLE001 — nie Fake-Werte bei Fehler
        raise StudioError(
            "metrics_sync_failed",
            f"Der Abruf ist fehlgeschlagen ({type(exc).__name__}). Es wurden keine "
            f"Werte gespeichert.", 502) from exc
    return record(job_id, job_dir, publishing_id, values, "synced")


def _clip_for(job_dir: str, draft: dict) -> dict:
    cj = read_json(os.path.join(job_dir, "clips.json"), None) or {}
    clips = cj.get("clips") or []
    idx = draft.get("source_clip_index")
    clip = clips[idx - 1] if isinstance(idx, int) and 1 <= idx <= len(clips) else {}
    return {"clip": clip, "studio": cj.get("studio") or {}}


def overview(registry) -> dict:
    """Alle veröffentlichten Drafts mit Potenzial (geschätzt) und echten Zahlen."""
    rows = []
    for job in registry.list():
        if not os.path.isdir(job.job_dir):
            continue
        for draft in list_drafts(job.job_dir):
            if draft.get("status") != "published":
                continue
            info = _clip_for(job.job_dir, draft)
            entries = history(job.id, draft["publishing_id"])
            latest = entries[-1] if entries else None
            score = info["clip"].get("score")
            rows.append({
                "job_id": job.id, "publishing_id": draft["publishing_id"],
                "platform": draft.get("platform"), "title": draft.get("title") or "",
                "published_at": draft.get("published_at"),
                "publish_source": draft.get("publish_source") or "platform",
                "external_url": draft.get("external_url"),
                "studio_project_id": info["studio"].get("project_id"),
                "group": f"{job.id}:{draft.get('source_clip_index') or draft.get('manual_export_id')}",
                "performance_potential": (
                    {"value": score, "source": "estimated"} if score is not None else None),
                "metrics": ({**{k: latest.get(k) for k in FIELDS},
                             "engagement_rate": engagement(latest),
                             "source": latest["source"], "captured_at": latest["captured_at"]}
                            if latest else None),
                "metric_entries": len(entries),
            })
    rows.sort(key=lambda r: r["published_at"] or "", reverse=True)
    return {"rows": rows, "hook_comparisons": _hook_comparisons(rows),
            "potential_vs_actual": _potential_vs_actual(rows),
            "legend": {"manual": "manuell eingetragen", "synced": "von der Plattform abgerufen",
                       "estimated": "Schätzung (Performance-Potenzial), keine Messung"}}


def _hook_comparisons(rows: list[dict]) -> list[dict]:
    """Gleicher Clip, mehrere veröffentlichte Titel/Hooks → Vergleich nach Views."""
    groups: dict[str, list[dict]] = {}
    for row in rows:
        groups.setdefault(row["group"], []).append(row)
    out = []
    for key, items in groups.items():
        if len(items) < 2:
            continue
        variants = [{"publishing_id": r["publishing_id"], "platform": r["platform"],
                     "hook": r["title"],
                     "views": (r["metrics"] or {}).get("views"),
                     "source": (r["metrics"] or {}).get("source")} for r in items]
        measured = [v for v in variants if v["views"] is not None]
        best = max(measured, key=lambda v: v["views"])["publishing_id"] if len(measured) >= 2 else None
        out.append({"group": key, "variants": variants, "best_publishing_id": best,
                    "note": None if best else "Zu wenige Messwerte für einen Vergleich."})
    return out


def _potential_vs_actual(rows: list[dict]) -> dict:
    pairs = [{"publishing_id": r["publishing_id"], "title": r["title"],
              "potential": r["performance_potential"]["value"],
              "views": r["metrics"]["views"], "views_source": r["metrics"]["source"]}
             for r in rows
             if r["performance_potential"] and r["metrics"] and r["metrics"]["views"] is not None]
    agreement = None
    if len(pairs) >= 3:  # Anteil gleich geordneter Paare (Kendall-artig)
        same = total = 0
        for i in range(len(pairs)):
            for j in range(i + 1, len(pairs)):
                dp = pairs[i]["potential"] - pairs[j]["potential"]
                dv = pairs[i]["views"] - pairs[j]["views"]
                if dp == 0 or dv == 0:
                    continue
                total += 1
                same += 1 if (dp > 0) == (dv > 0) else 0
        agreement = round(same / total, 2) if total else None
    return {"pairs": pairs, "rank_agreement": agreement,
            "note": ("Ab drei Messpunkten: Anteil der Paare, bei denen höheres Potenzial "
                     "auch mehr Views bedeutete. Keine Prognose.")}


def remix_traits(project: dict, metrics: dict | None) -> dict:
    """Merkmale, die ein Remix vom erfolgreichen Projekt übernimmt."""
    scenes = project.get("scenes") or []
    words = [len(s["text"].split()) for s in scenes if s.get("text")]
    return {
        "caption_style": project["captions"]["style"], "aspect_ratio": project["aspect_ratio"],
        "style": project["style"], "voice": project["voice"],
        "music_track": project["music"].get("track"),
        "scene_count": len(scenes),
        "avg_scene_words": round(sum(words) / len(words), 1) if words else None,
        "hook": scenes[0]["text"] if scenes else None,
        "based_on_metrics": metrics,
    }
