"""Automatische B-Roll: passende Bilder/Clips je Szene.

Reihenfolge der Quellen:
1. Eigene Mediathek des Projekts (Dateiname + vergebene Schlagwörter) — kostenlos.
2. Optional Stock-Anbieter mit eigenem (kostenlosem) API-Schlüssel:
   Pexels (Pexels-Lizenz) und Pixabay (Pixabay Content License). Beide erlauben
   laut ihren Bedingungen kostenlose kommerzielle Nutzung ohne Pflicht-Nennung;
   ClipForge speichert trotzdem Herkunft, Urheber und Lizenz je Datei.

Keine Suche bei anderen Quellen (z. B. Google-Bilder), weil deren Nutzung
nicht geklärt ist.
"""

from __future__ import annotations

import json
import os
import re
import urllib.parse

from . import safe_fetch
from .errors import StudioError
from .storage import new_id, now_iso, read_json, safe_child, safe_filename, write_json_atomic
from .credentials import secret

IMAGE_EXT = {".png", ".jpg", ".jpeg", ".webp"}
VIDEO_EXT = {".mp4", ".mov", ".mkv", ".webm", ".avi", ".m4v"}

_STOP = set("""
aber alle allem allen aller alles als also am an ander andere anderem anderen anderer anderes
auch auf aus bei bin bis bist da damit dann das dass dein deine dem den denn der des dich die
dies diese diesem diesen dieser dieses dir doch dort du durch ein eine einem einen einer eines
er es etwas euch euer für gegen gibt hab habe haben hat hatte hier hin hinter ich ihm ihn ihr
im in ist ja jede jedem jeden jeder jedes jetzt kann kein keine man mehr mein meine mich mir
mit muss nach nicht nichts noch nun nur ob oder ohne sehr sein seine sich sie sind so soll
sollte sondern sonst über um und uns unser unter viel vom von vor war waren was weil weiter
welche wenn wer werden wie wieder will wir wird wirst wo wurde zu zum zur zwar zwischen
a about after all also an and any are as at be because been but by can could do does for from
get got had has have he her here him his how i if in into is it its just like make many me
more most my no not now of on one only or other our out over so some such than that the
their them then there these they this to up us very was we were what when which who why will
with would you your
""".split())

LICENSES = {
    "pexels": {"name": "Pexels-Lizenz", "url": "https://www.pexels.com/license/",
               "commercial": True, "attribution_required": False},
    "pixabay": {"name": "Pixabay Content License", "url": "https://pixabay.com/service/license-summary/",
                "commercial": True, "attribution_required": False},
}

# Test-Hook: (url, headers) -> dict (JSON)
API_GET = None
DOWNLOAD_KWARGS: dict = {}


def keywords(text: str, limit: int = 6) -> list[str]:
    words = re.findall(r"[A-Za-zÄÖÜäöüß]{3,}", text or "")
    seen, out = set(), []
    for w in words:
        lw = w.lower()
        if lw in _STOP or lw in seen:
            continue
        seen.add(lw)
        out.append(lw)
    # längere Wörter tragen mehr Bedeutung
    return sorted(out, key=lambda w: (-len(w), out.index(w)))[:limit]


def _stem(word: str) -> str:
    for suf in ("ungen", "ung", "en", "er", "es", "e", "s", "n"):
        if len(word) > len(suf) + 3 and word.endswith(suf):
            return word[: -len(suf)]
    return word


# ------------------------------------------------------------ Mediathek
def _meta_path(project_dir: str) -> str:
    return os.path.join(project_dir, "media_meta.json")


def media_meta(project_dir: str) -> dict:
    data = read_json(_meta_path(project_dir), {})
    return data if isinstance(data, dict) else {}


def set_media_meta(project_dir: str, name: str, **fields) -> dict:
    meta = media_meta(project_dir)
    entry = dict(meta.get(name) or {})
    if "tags" in fields:
        tags = fields.pop("tags") or []
        if isinstance(tags, str):
            tags = tags.split(",")
        entry["tags"] = list(dict.fromkeys(
            t.strip().lower()[:40] for t in tags if str(t).strip()))[:30]
    entry.update({k: v for k, v in fields.items() if v is not None})
    meta[name] = entry
    write_json_atomic(_meta_path(project_dir), meta)
    return entry


def _tokens(name: str, entry: dict) -> set[str]:
    base = os.path.splitext(name)[0]
    base = re.sub(r"_[0-9a-f]{6}$", "", base)  # Upload-Suffix
    toks = {_stem(t.lower()) for t in re.split(r"[^A-Za-zÄÖÜäöüß]+", base) if len(t) >= 3}
    for tag in entry.get("tags") or []:
        toks |= {_stem(t) for t in re.split(r"\s+", tag) if len(t) >= 3}
    if entry.get("query"):
        toks |= {_stem(t) for t in str(entry["query"]).split() if len(t) >= 3}
    return toks


def library_matches(project_dir: str, text: str, exclude: set[str] | None = None) -> list[dict]:
    """Medien der Projekt-Mediathek, sortiert nach Treffern mit dem Szenentext."""
    mdir = os.path.join(project_dir, "media")
    if not os.path.isdir(mdir):
        return []
    meta = media_meta(project_dir)
    keys = {_stem(k) for k in keywords(text, 12)}
    out = []
    for name in sorted(os.listdir(mdir)):
        ext = os.path.splitext(name)[1].lower()
        if ext not in IMAGE_EXT | VIDEO_EXT or name in (exclude or set()):
            continue
        hits = keys & _tokens(name, meta.get(name, {}))
        if hits:
            out.append({"source": "library", "name": name, "score": len(hits),
                        "matched": sorted(hits),
                        "kind": "image" if ext in IMAGE_EXT else "video"})
    return sorted(out, key=lambda m: (-m["score"], m["name"]))


# ------------------------------------------------------------ Stock
def _get_json(url: str, headers: dict) -> dict:
    """Such-API (feste Hosts api.pexels.com / pixabay.com, daher urllib)."""
    if API_GET is not None:
        return API_GET(url, headers)
    import urllib.error
    import urllib.request
    host = urllib.parse.urlparse(url).hostname
    if host not in ("api.pexels.com", "pixabay.com"):
        raise StudioError("validation_error", "Unerlaubter Stock-Host.")
    req = urllib.request.Request(url, headers={**headers, "User-Agent": "ClipForge"})
    try:
        with urllib.request.urlopen(req, timeout=20) as resp:  # noqa: S310 — feste Hosts
            body = resp.read(2 * 1024 * 1024 + 1)
    except urllib.error.HTTPError as exc:
        if exc.code in (400, 401, 403):
            raise StudioError("credential_rejected",
                              "Der Stock-Anbieter hat den Schlüssel abgelehnt.", 502) from None
        if exc.code == 429:
            raise StudioError("rate_limited", "Stock-Anbieter: zu viele Anfragen, bitte später.",
                              429) from None
        raise StudioError("provider_failed", f"Stock-Suche fehlgeschlagen (HTTP {exc.code}).",
                          502) from None
    except OSError as exc:
        raise StudioError("provider_unreachable", "Stock-Anbieter nicht erreichbar.", 502) from exc
    if len(body) > 2 * 1024 * 1024:
        raise StudioError("provider_failed", "Antwort zu groß.", 502)
    return json.loads(body.decode("utf-8"))


def stock_available() -> list[str]:
    return [p for p, env in (("pexels", "PEXELS_API_KEY"), ("pixabay", "PIXABAY_API_KEY"))
            if secret(env)]


def _orientation(aspect: str) -> str:
    return {"9:16": "portrait", "4:5": "portrait", "16:9": "landscape"}.get(aspect, "square")


def search_stock(provider: str, query: str, aspect: str = "9:16", kind: str = "video",
                 limit: int = 6) -> list[dict]:
    if provider not in LICENSES:
        raise StudioError("validation_error", "Unbekannter Stock-Anbieter.")
    query = " ".join(query.split())[:80]
    if not query:
        return []
    if provider == "pexels":
        key = secret("PEXELS_API_KEY")
        if not key:
            raise StudioError("credential_not_set", "Kein Pexels-Schlüssel hinterlegt.", 409)
        q = urllib.parse.urlencode({"query": query, "per_page": limit,
                                    "orientation": _orientation(aspect)})
        if kind == "video":
            data = _get_json(f"https://api.pexels.com/videos/search?{q}", {"Authorization": key})
            out = []
            for v in data.get("videos", [])[:limit]:
                files = [f for f in v.get("video_files", []) if f.get("file_type") == "video/mp4"
                         and f.get("link")]
                # Datei passend zu 1080p, nicht unnötig groß
                files.sort(key=lambda f: abs((f.get("height") or 0) - 1920)
                           if _orientation(aspect) == "portrait" else abs((f.get("width") or 0) - 1920))
                if not files:
                    continue
                out.append({"source": "pexels", "kind": "video", "id": str(v.get("id")),
                            "preview": v.get("image"), "download": files[0]["link"],
                            "duration": v.get("duration"), "author": (v.get("user") or {}).get("name"),
                            "page": v.get("url"), "license": LICENSES["pexels"]})
            return out
        data = _get_json(f"https://api.pexels.com/v1/search?{q}", {"Authorization": key})
        return [{"source": "pexels", "kind": "image", "id": str(p.get("id")),
                 "preview": (p.get("src") or {}).get("medium"),
                 "download": (p.get("src") or {}).get("large2x") or (p.get("src") or {}).get("original"),
                 "author": p.get("photographer"), "page": p.get("url"),
                 "license": LICENSES["pexels"]} for p in data.get("photos", [])[:limit]]
    key = secret("PIXABAY_API_KEY")
    if not key:
        raise StudioError("credential_not_set", "Kein Pixabay-Schlüssel hinterlegt.", 409)
    params = {"key": key, "q": query, "per_page": max(3, limit), "safesearch": "true"}
    if kind == "video":
        data = _get_json("https://pixabay.com/api/videos/?" + urllib.parse.urlencode(params), {})
        out = []
        for h in data.get("hits", [])[:limit]:
            vids = h.get("videos") or {}
            f = vids.get("large") or vids.get("medium") or vids.get("small") or {}
            if not f.get("url"):
                continue
            out.append({"source": "pixabay", "kind": "video", "id": str(h.get("id")),
                        "preview": f.get("thumbnail"), "download": f["url"],
                        "duration": h.get("duration"), "author": h.get("user"),
                        "page": h.get("pageURL"), "license": LICENSES["pixabay"]})
        return out
    params["image_type"] = "photo"
    params["orientation"] = "vertical" if _orientation(aspect) == "portrait" else "horizontal"
    data = _get_json("https://pixabay.com/api/?" + urllib.parse.urlencode(params), {})
    return [{"source": "pixabay", "kind": "image", "id": str(h.get("id")),
             "preview": h.get("previewURL"), "download": h.get("largeImageURL"),
             "author": h.get("user"), "page": h.get("pageURL"),
             "license": LICENSES["pixabay"]} for h in data.get("hits", [])[:limit]]


_ALLOWED_DOWNLOAD_HOSTS = ("videos.pexels.com", "images.pexels.com", "player.vimeo.com",
                           "pixabay.com", "cdn.pixabay.com")


def import_stock(project_dir: str, item: dict, query: str) -> str:
    """Lädt ein Stock-Ergebnis in die Mediathek und speichert die Herkunft."""
    url = str(item.get("download") or "")
    host = urllib.parse.urlparse(url).hostname or ""
    if item.get("source") not in LICENSES or not url.startswith("https://") or not any(
            host == h or host.endswith("." + h) for h in _ALLOWED_DOWNLOAD_HOSTS):
        raise StudioError("validation_error", "Nur Downloads direkt von Pexels/Pixabay.")
    is_video = item.get("kind") == "video"
    res = safe_fetch.fetch(url, allowed_types=("video/mp4",) if is_video else
                           ("image/jpeg", "image/png", "image/webp"),
                           max_bytes=(200 if is_video else 25) * 1024 * 1024,
                           timeout=120, max_redirects=5, **DOWNLOAD_KWARGS)
    if not res.body:
        raise StudioError("provider_failed", f"Download fehlgeschlagen (HTTP {res.status}).", 502)
    ext = ".mp4" if is_video else {"image/png": ".png", "image/webp": ".webp"}.get(
        res.content_type.split(";")[0].strip(), ".jpg")
    slug = "-".join(keywords(query, 3)) or "broll"
    name = safe_filename(f"{slug}_{item['source']}_{new_id()[:6]}{ext}")
    dest = safe_child(os.path.join(project_dir, "media"), name)
    os.makedirs(os.path.dirname(dest), exist_ok=True)
    with open(dest, "wb") as fh:
        fh.write(res.body)
    set_media_meta(project_dir, name, tags=keywords(query, 6), query=query,
                   origin={"source": item["source"], "id": item.get("id"),
                           "author": item.get("author"), "page": item.get("page"),
                           "license": item.get("license") or LICENSES[item["source"]],
                           "imported_at": now_iso()})
    return name


# ------------------------------------------------------------ Automatik
AUTO_MODES = ("motion", "static")


def auto_assign(project: dict, project_dir: str, *, overwrite: bool = False,
                stock=None) -> tuple[list, list]:
    """Weist Szenen ohne eigenes Visual passende Mediathek-Dateien zu.

    → (neue Szenenliste, Protokoll). Szenen, die der Benutzer schon mit einem
    Medium/KI-Visual belegt hat, bleiben unverändert (außer overwrite=True).
    Jedes Medium wird möglichst nur einmal verwendet.
    """
    used: set[str] = set()
    scenes, log = [], []
    for scene in project.get("scenes", []):
        s = json.loads(json.dumps(scene))
        mode = s["visual"]["mode"]
        if mode == "media" and s["visual"].get("media"):
            used.add(s["visual"]["media"])
        if mode not in AUTO_MODES and not (overwrite and mode == "media"):
            scenes.append(s)
            continue
        text = " ".join([s.get("text") or "", s.get("visual_prompt") or "", s.get("headline") or ""])
        matches = library_matches(project_dir, text, exclude=used) or \
            library_matches(project_dir, text)
        if matches:
            best = matches[0]
            s["visual"] = {**s["visual"], "mode": "media", "media": best["name"]}
            used.add(best["name"])
            log.append({"scene": s["id"], "media": best["name"], "matched": best["matched"],
                        "source": "library"})
        elif stock is not None:
            name = stock(text)
            if name:
                s["visual"] = {**s["visual"], "mode": "media", "media": name}
                used.add(name)
                log.append({"scene": s["id"], "media": name, "source": "stock"})
        scenes.append(s)
    return scenes, log
