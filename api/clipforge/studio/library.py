"""Mediathek je Benutzerbereich: wiederverwendbare Videos, Bilder, Audio, Musik,
Soundeffekte, Sprachaufnahmen, generierte Assets und Marken-Elemente.

Ablage: ``<studio>/library/files/<id><ext>`` + ``index.json``.

- Duplikate werden per SHA-256 erkannt (gleiche Datei → vorhandener Eintrag).
- Herkunft/Lizenz je Eintrag (Upload, Projekt, Stock, generiert; Lizenzname/-URL,
  Urheber) — bei Fremdmedien Pflichtangaben für die Weiterverwendung.
- „In Projekt verwenden“ kopiert die Datei in das Projekt (Projekte bleiben
  in sich geschlossen) und protokolliert die Nutzung.
- Löschen eines genutzten Eintrags verlangt eine ausdrückliche Bestätigung;
  Projekte behalten ihre Kopie.
"""

from __future__ import annotations

import hashlib
import os
import shutil
import threading

from .audio import AUDIO_EXT
from .errors import StudioError
from .projects import IMAGE_EXT, VIDEO_EXT
from .storage import new_id, now_iso, read_json, require_id, safe_child, studio_dir, write_json_atomic

KINDS = ("video", "image", "audio", "music", "sfx", "voice", "generated", "brand")
SOURCES = ("upload", "project", "stock", "generated", "recording")
_lock = threading.RLock()


def _base() -> str:
    path = os.path.join(studio_dir(), "library")
    os.makedirs(os.path.join(path, "files"), exist_ok=True)
    return path


def _index() -> list[dict]:
    data = read_json(os.path.join(_base(), "index.json"), [])
    return data if isinstance(data, list) else []


def _save(items: list[dict]) -> None:
    write_json_atomic(os.path.join(_base(), "index.json"), items)


def _sha256(path: str) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def media_type(ext: str) -> str:
    if ext in IMAGE_EXT:
        return "image"
    if ext in VIDEO_EXT:
        return "video"
    if ext in AUDIO_EXT:
        return "audio"
    raise StudioError("file_type_not_allowed", f"Dateityp '{ext or '?'}' wird in der Mediathek nicht unterstützt.", 415)


def _display_name(name: str) -> str:
    """Anzeigename: ohne Pfadanteile und Steuerzeichen (gespeichert wird unter der ID)."""
    base = os.path.basename(str(name or "").replace("\\", "/"))
    return "".join(c for c in base if c.isprintable()).strip()[:120]


def _clean_tags(tags) -> list[str]:
    if isinstance(tags, str):
        tags = tags.split(",")
    out = []
    for t in tags or []:
        t = " ".join(str(t).lower().split())[:30]
        if t and t not in out:
            out.append(t)
    return out[:20]


def _provenance(raw: dict | None) -> dict:
    raw = raw if isinstance(raw, dict) else {}
    src = raw.get("source") if raw.get("source") in SOURCES else "upload"
    lic = raw.get("license") if isinstance(raw.get("license"), dict) else {}
    out = {"source": src, "author": str(raw.get("author") or "")[:80] or None,
           "url": str(raw.get("url") or "")[:300] or None,
           "license": {"name": str(lic.get("name") or "")[:60] or None, "url": str(lic.get("url") or "")[:300] or None}}
    if out["url"] and not out["url"].startswith(("https://", "http://")):
        out["url"] = None
    if out["license"]["url"] and not out["license"]["url"].startswith(("https://", "http://")):
        out["license"]["url"] = None
    return out


def add_file(path: str, original_name: str, *, kind: str | None = None, tags=None, provenance: dict | None = None,
             move: bool = False) -> dict:
    """Datei aufnehmen. → Eintrag (mit ``duplicate: True``, falls schon vorhanden)."""
    ext = os.path.splitext(original_name or path)[1].lower()
    mtype = media_type(ext)
    if kind is not None and kind not in KINDS:
        raise StudioError("validation_error", f"Art: {', '.join(KINDS)}.")
    if kind in ("music", "sfx", "voice") and mtype == "image":
        raise StudioError("validation_error", "Musik/Effekte/Sprache müssen Audio- oder Videodateien sein.")
    digest = _sha256(path)
    with _lock:
        items = _index()
        dup = next((x for x in items if x["sha256"] == digest), None)
        if dup:
            if move and os.path.exists(path):
                os.remove(path)
            return {**dup, "duplicate": True}
        eid = new_id()
        dest = os.path.join(_base(), "files", eid + ext)
        (shutil.move if move else shutil.copyfile)(path, dest)
        meta: dict = {}
        if mtype in ("video", "audio"):
            try:
                from ..ffmpeg_utils import probe
                info = probe(dest)
                meta = {"duration": round(info.duration or 0, 2), "width": info.width or None,
                        "height": info.height or None, "has_audio": info.has_audio}
            except Exception as exc:  # noqa: BLE001
                os.remove(dest)
                raise StudioError("file_unreadable", "Die Datei ist keine lesbare Medien-Datei.", 415) from exc
        entry = {"id": eid, "name": _display_name(original_name or os.path.basename(path)) or eid + ext,
                 "file": eid + ext, "media_type": mtype, "kind": kind or mtype, "tags": _clean_tags(tags),
                 "sha256": digest, "bytes": os.path.getsize(dest), **meta,
                 "provenance": _provenance(provenance), "created_at": now_iso(), "usage": []}
        items.append(entry)
        _save(items)
        return entry


def get(eid: str) -> dict:
    require_id(eid, "Mediathek-ID")
    e = next((x for x in _index() if x["id"] == eid), None)
    if e is None:
        raise StudioError("not_found", "Eintrag nicht gefunden.", 404)
    return e


def file_path(eid: str) -> str:
    e = get(eid)
    return safe_child(os.path.join(_base(), "files"), e["file"])


def search(q: str = "", kind: str | None = None, tag: str | None = None) -> list[dict]:
    terms = [t for t in (q or "").lower().split() if t]
    out = []
    for e in _index():
        if kind and e["kind"] != kind and e["media_type"] != kind:
            continue
        if tag and tag.lower() not in e["tags"]:
            continue
        hay = " ".join([e["name"].lower(), *e["tags"], e["kind"], (e["provenance"].get("author") or "").lower()])
        if all(t in hay for t in terms):
            out.append(e)
    return sorted(out, key=lambda e: e["created_at"], reverse=True)


def update(eid: str, patch: dict) -> dict:
    with _lock:
        items = _index()
        e = next((x for x in items if x["id"] == eid), None)
        if e is None:
            raise StudioError("not_found", "Eintrag nicht gefunden.", 404)
        if "name" in patch and str(patch["name"]).strip():
            e["name"] = _display_name(patch["name"]) or e["name"]
        if "tags" in patch:
            e["tags"] = _clean_tags(patch["tags"])
        if "kind" in patch:
            if patch["kind"] not in KINDS:
                raise StudioError("validation_error", f"Art: {', '.join(KINDS)}.")
            e["kind"] = patch["kind"]
        if "provenance" in patch:
            e["provenance"] = _provenance(patch["provenance"])
        _save(items)
        return e


def delete(eid: str, force: bool = False) -> dict:
    with _lock:
        items = _index()
        e = next((x for x in items if x["id"] == eid), None)
        if e is None:
            raise StudioError("not_found", "Eintrag nicht gefunden.", 404)
        projects = sorted({u["project_id"] for u in e.get("usage", [])})
        if projects and not force:
            raise StudioError("library_in_use",
                              f"Wird in {len(projects)} Projekt(en) verwendet. Die Projekte behalten ihre Kopie — "
                              "zum Löschen bestätigen.", 409, {"projects": projects})
        path = os.path.join(_base(), "files", e["file"])
        if os.path.exists(path):
            os.remove(path)
        _save([x for x in items if x["id"] != eid])
        return {"deleted": True, "projects_keep_copy": projects}


def record_use(eid: str, project_id: str, media_name: str) -> None:
    with _lock:
        items = _index()
        e = next((x for x in items if x["id"] == eid), None)
        if e is None:
            return
        e.setdefault("usage", []).append({"project_id": project_id, "media": media_name, "at": now_iso()})
        e["usage"] = e["usage"][-200:]
        _save(items)
