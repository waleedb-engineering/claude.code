"""Ideen-Bibliothek: vom Nutzer selbst gespeicherte Referenzen.

Es gibt KEINE mitgelieferten Fremddaten und kein Scraping von Plattformen.
Gespeichert wird nur, was der Nutzer einträgt (URL, Notizen, Tags, eigene
Zahlen). „Als Inspiration verwenden“ übernimmt Struktur-Merkmale (Hook-Typ,
Format, Nische) — niemals fremde Inhalte.
"""

from __future__ import annotations

import os

from .errors import StudioError
from .safe_fetch import validate_url
from .storage import new_id, now_iso, read_json, require_id, studio_dir, write_json_atomic

HOOK_TYPES = ("question", "bold_claim", "number", "story", "how_to", "contrast", "other")
FORMATS = ("talking_head", "voiceover_broll", "list", "tutorial", "story", "review",
           "ad", "meme", "other")
PLATFORMS = ("youtube", "tiktok", "instagram", "x", "other")
ORIGINALITY_NOTICE = {
    "de": ("Inspiration, keine Kopie: Übernimm nur Struktur und Idee. Text, Bild- und "
           "Tonmaterial der Referenz dürfen nicht kopiert werden."),
    "en": ("Inspiration, not a copy: reuse structure and idea only. Do not copy the "
           "reference's wording, footage or audio."),
}


def _dir() -> str:
    path = os.path.join(studio_dir(), "ideas")
    os.makedirs(path, exist_ok=True)
    return path


def _path(idea_id: str) -> str:
    return os.path.join(_dir(), f"{require_id(idea_id, 'Ideen-ID')}.json")


def _metric(value):
    if value in (None, ""):
        return None
    try:
        number = int(value)
    except (TypeError, ValueError) as exc:
        raise StudioError("validation_error", "Metriken müssen ganze Zahlen sein.") from exc
    if number < 0:
        raise StudioError("validation_error", "Metriken dürfen nicht negativ sein.")
    return number


def _normalize(data: dict, existing: dict | None = None) -> dict:
    base = dict(existing or {})
    title = str(data.get("title", base.get("title", ""))).strip()[:200]
    url = str(data.get("url", base.get("url", "")) or "").strip()
    if url:
        validate_url(url)
    if not title and not url:
        raise StudioError("validation_error", "Bitte Titel oder URL angeben.")
    tags = data.get("tags", base.get("tags", []))
    if isinstance(tags, str):
        tags = tags.split(",")
    tags = list(dict.fromkeys(str(t).strip().lower()[:30] for t in tags if str(t).strip()))[:15]

    def pick(key, allowed):
        value = data.get(key, base.get(key))
        return value if value in allowed else "other"

    metrics_in = data.get("metrics") if isinstance(data.get("metrics"), dict) else \
        (base.get("metrics") or {})
    metrics = {k: _metric(metrics_in.get(k)) for k in ("views", "likes", "comments")}
    has_metrics = any(v is not None for v in metrics.values())
    return {
        "id": base.get("id") or new_id(),
        "title": title or url, "url": url,
        "notes": str(data.get("notes", base.get("notes", "")) or "")[:2000],
        "niche": str(data.get("niche", base.get("niche", "")) or "").strip().lower()[:40],
        "tags": tags,
        "hook_type": pick("hook_type", HOOK_TYPES),
        "format": pick("format", FORMATS),
        "platform": pick("platform", PLATFORMS),
        "metrics": {**metrics, "source": "manual" if has_metrics else None},
        "created_at": base.get("created_at") or now_iso(),
        "updated_at": now_iso(),
    }


def create(data: dict) -> dict:
    idea = _normalize(data)
    write_json_atomic(_path(idea["id"]), idea)
    return idea


def get(idea_id: str) -> dict:
    data = read_json(_path(idea_id), None)
    if not isinstance(data, dict):
        raise StudioError("idea_not_found", "Idee nicht gefunden.", 404)
    return data


def update(idea_id: str, data: dict) -> dict:
    idea = _normalize(data, get(idea_id))
    write_json_atomic(_path(idea_id), idea)
    return idea


def delete(idea_id: str) -> None:
    get(idea_id)
    os.remove(_path(idea_id))


def search(q: str = "", niche: str = "", hook_type: str = "", fmt: str = "",
           tag: str = "", platform: str = "") -> list[dict]:
    out = []
    needle = q.strip().lower()
    for name in os.listdir(_dir()):
        if not name.endswith(".json"):
            continue
        idea = read_json(os.path.join(_dir(), name), None)
        if not isinstance(idea, dict):
            continue
        hay = " ".join([idea.get("title", ""), idea.get("notes", ""), idea.get("niche", ""),
                        " ".join(idea.get("tags") or []), idea.get("url", "")]).lower()
        if needle and needle not in hay:
            continue
        if niche and idea.get("niche") != niche.lower():
            continue
        if hook_type and idea.get("hook_type") != hook_type:
            continue
        if fmt and idea.get("format") != fmt:
            continue
        if platform and idea.get("platform") != platform:
            continue
        if tag and tag.lower() not in (idea.get("tags") or []):
            continue
        out.append(idea)
    return sorted(out, key=lambda i: i.get("created_at") or "", reverse=True)


def inspiration_request(idea: dict, topic: str, language: str) -> dict:
    """Baut die Projekt-Anfrage für „Als Inspiration verwenden“."""
    topic = (topic or "").strip()
    if len(topic) < 3:
        raise StudioError(
            "validation_error",
            "Bitte ein eigenes Thema angeben — die Referenz selbst wird nicht kopiert.")
    return {
        "workflow": "idea", "language": language, "prompt": topic,
        "title": topic[:80],
        "lineage": {"idea_id": idea["id"],
                    "traits": {"hook_type": idea["hook_type"], "format": idea["format"],
                               "niche": idea["niche"]},
                    "originality_notice": ORIGINALITY_NOTICE.get(language, ORIGINALITY_NOTICE["de"])},
    }
