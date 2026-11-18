"""Studio-Projekte: Schema, Validierung, konfliktsichere Versionierung.

Ein Projekt liegt als `projects/<id>/project.json`. Jede Speicherung erhöht
`version`; Editor-Schreibzugriffe müssen die erwartete Version mitgeben
(Optimistic Locking → `version_conflict`). Vor jedem Überschreiben wird ein
Snapshot abgelegt (letzte 25), der wiederhergestellt werden kann.
Alte/unvollständige Projektdateien werden beim Laden rückwärtskompatibel
auf das aktuelle Schema gehoben (`migrate`).
"""

from __future__ import annotations

import copy
import os
import re
import shutil
import threading

from .errors import StudioError
from .storage import (
    new_id, now_iso, read_json, require_id, safe_child, safe_filename,
    studio_dir, write_json_atomic,
)

SCHEMA = 1
MAX_SNAPSHOTS = 25
ASPECT_RATIOS = ("9:16", "16:9", "1:1", "4:5")
RESOLUTIONS = ("720p", "1080p", "4k")
CAPTION_STYLES = ("minimal", "bold", "karaoke", "dynamic", "none")
VISUAL_MODES = ("motion", "static", "media", "ai_image", "split", "ai_video", "avatar")
STYLES = ("clean", "cinematic")
LANGUAGES = ("de", "en")
WORKFLOWS = (
    "prompt", "script", "article_url", "website_review", "social_url", "pdf",
    "audio", "music", "podcast", "longform", "media", "job", "product_ad",
    "cinematic", "idea", "youtube", "avatar",
)
IMAGE_EXT = {".png", ".jpg", ".jpeg", ".webp"}
VIDEO_EXT = {".mp4", ".mov", ".mkv", ".webm", ".avi", ".m4v"}
_HEX = re.compile(r"^#[0-9a-fA-F]{6}$")
_locks: dict[str, threading.RLock] = {}
_locks_guard = threading.Lock()


def _lock(pid: str) -> threading.RLock:
    with _locks_guard:
        return _locks.setdefault(pid, threading.RLock())


def _clamp(value, lo, hi, default):
    try:
        return max(lo, min(hi, float(value)))
    except (TypeError, ValueError):
        return default


def normalize_scene(raw: dict, project_dir: str | None = None) -> dict:
    """Validiert/normalisiert eine Szene (unbekannte Felder werden verworfen)."""
    if not isinstance(raw, dict):
        raise StudioError("scene_invalid", "Szene hat ein ungültiges Format.")
    sid = raw.get("id")
    from .storage import is_safe_id
    scene = {
        "id": sid if is_safe_id(sid) else new_id(),
        "kind": raw.get("kind") if raw.get("kind") in ("hook", "body", "cta") else "body",
        "text": str(raw.get("text") or "")[:1200].strip(),
        "voice_text": (str(raw["voice_text"])[:1200].strip()
                       if raw.get("voice_text") not in (None, "") else None),
        "visual_prompt": str(raw.get("visual_prompt") or "")[:300].strip(),
        "headline": str(raw.get("headline") or "")[:60].strip(),
        "duration": None,
        "pause_after": _clamp(raw.get("pause_after"), 0.0, 5.0, 0.0),
    }
    if raw.get("duration") not in (None, "", 0):
        scene["duration"] = _clamp(raw.get("duration"), 0.5, 120.0, None)
    visual = raw.get("visual") if isinstance(raw.get("visual"), dict) else {}
    mode = visual.get("mode") if visual.get("mode") in VISUAL_MODES else "motion"
    media = visual.get("media")
    if media is not None:
        media = safe_filename(str(media))
        if project_dir is not None:
            path = safe_child(os.path.join(project_dir, "media"), media)
            if not os.path.isfile(path):
                raise StudioError("media_not_found",
                                  f"Mediendatei '{media}' gibt es in diesem Projekt nicht.", 404)
    if mode == "media" and not media:
        mode = "motion"
    color = visual.get("color") if _HEX.match(str(visual.get("color") or "")) else None
    try:
        seed = max(0, int(visual.get("seed") or 0))
    except (TypeError, ValueError):
        seed = 0
    scene["visual"] = {"mode": mode, "media": media, "color": color, "seed": seed}
    # Szenen aus Original-Audio (Audio→Video): Ausschnitt + echte Wort-Timings
    src = raw.get("audio_source")
    if isinstance(src, dict):
        try:
            start, end = float(src["start"]), float(src["end"])
            if 0 <= start < end:
                scene["audio_source"] = {"start": round(start, 3), "end": round(end, 3)}
        except (KeyError, TypeError, ValueError):
            pass
    words = raw.get("words")
    if isinstance(words, list) and "audio_source" in scene:
        clean = []
        for w in words[:400]:
            try:
                clean.append({"text": str(w["text"])[:60], "start": float(w["start"]),
                              "end": float(w["end"])})
            except (KeyError, TypeError, ValueError):
                continue
        scene["words"] = clean
    return scene


def new_project(*, title: str, workflow: str, language: str = "de") -> dict:
    now = now_iso()
    return migrate({
        "schema": SCHEMA, "id": new_id(), "title": title[:120] or "Neues Video",
        "workflow": workflow, "language": language, "created_at": now,
        "updated_at": now, "version": 0,
    })


def migrate(data: dict) -> dict:
    """Hebt beliebige (alte) Projekt-dicts auf das aktuelle Schema. Idempotent."""
    p = dict(data)
    p.setdefault("schema", SCHEMA)
    p.setdefault("title", "Unbenanntes Projekt")
    if p.get("workflow") not in WORKFLOWS:
        p["workflow"] = "script"
    if p.get("language") not in LANGUAGES:
        p["language"] = "de"
    p.setdefault("tone", "")
    if p.get("style") not in STYLES:
        p["style"] = "clean"
    if p.get("aspect_ratio") not in ASPECT_RATIOS:
        p["aspect_ratio"] = "9:16"
    if p.get("resolution") not in RESOLUTIONS:
        p["resolution"] = "1080p"
    if p.get("status") not in ("draft", "ingesting", "ready", "failed"):
        p["status"] = "draft"
    p.setdefault("status_error", None)
    p["source"] = p.get("source") if isinstance(p.get("source"), dict) else {}
    p["script"] = p.get("script") if isinstance(p.get("script"), dict) else {}
    scenes = p.get("scenes") if isinstance(p.get("scenes"), list) else []
    fixed = []
    for s in scenes:
        try:
            fixed.append(normalize_scene(s))
        except StudioError:
            continue
    p["scenes"] = fixed
    voice = p.get("voice") if isinstance(p.get("voice"), dict) else {}
    p["voice"] = {"provider": str(voice.get("provider") or "auto"),
                  "voice_id": voice.get("voice_id") or None,
                  "tone": str(voice.get("tone") or ""),
                  "speed": round(_clamp(voice.get("speed"), 0.5, 2.0, 1.0), 2)}
    music = p.get("music") if isinstance(p.get("music"), dict) else {}
    p["music"] = {"track": music.get("track") or None,
                  "volume": _clamp(music.get("volume"), 0.0, 1.0, 0.25),
                  "ducking": bool(music.get("ducking", True)),
                  "beat_sync": bool(music.get("beat_sync", False))}
    caps = p.get("captions") if isinstance(p.get("captions"), dict) else {}
    p["captions"] = {
        "style": caps.get("style") if caps.get("style") in CAPTION_STYLES else "karaoke",
        "use_brand": bool(caps.get("use_brand", True))}
    vis = p.get("visuals") if isinstance(p.get("visuals"), dict) else {}
    p["visuals"] = {
        "image_provider": str(vis.get("image_provider") or "openai_image"),
        "gameplay_media": vis.get("gameplay_media") or None,
        "avatar_image": vis.get("avatar_image") or None,
        "video_provider": str(vis.get("video_provider") or "fal_video"),
        "avatar_provider": str(vis.get("avatar_provider") or "fal_avatar"),
        "headlines": bool(vis.get("headlines", True))}
    from .options import ProductionOptions
    legacy = dict(p.get("options") or {}) if isinstance(p.get("options"), dict) else {}
    if "duration_target" not in legacy and isinstance(p["source"].get("target_seconds"), (int, float)):
        legacy["duration_target"] = p["source"]["target_seconds"]  # altes Feld übernehmen
    p["options"] = ProductionOptions.from_dict(legacy).to_dict()
    p["budget_limit_usd"] = _clamp(p.get("budget_limit_usd"), 0.0, 10000.0, 0.0)
    p["lineage"] = p.get("lineage") if isinstance(p.get("lineage"), dict) else {}
    p.setdefault("linked_job_id", None)
    p["exports"] = p.get("exports") if isinstance(p.get("exports"), list) else []
    try:
        p["version"] = int(p.get("version") or 0)
    except (TypeError, ValueError):
        p["version"] = 0
    p.setdefault("created_at", now_iso())
    p.setdefault("updated_at", p["created_at"])
    return p


_EDITABLE = ("title", "language", "tone", "style", "aspect_ratio", "resolution",
             "scenes", "voice", "music", "captions", "visuals", "budget_limit_usd",
             "options")


def apply_patch(project: dict, patch: dict, project_dir: str) -> dict:
    """Wendet Editor-Änderungen an (nur erlaubte Felder, alles validiert)."""
    p = copy.deepcopy(project)
    for key, value in patch.items():
        if key not in _EDITABLE or value is None:
            continue
        if key == "title":
            if not str(value).strip():
                raise StudioError("validation_error", "Der Titel darf nicht leer sein.")
            p["title"] = str(value).strip()[:120]
        elif key == "language":
            if value not in LANGUAGES:
                raise StudioError("validation_error", "Sprache nicht unterstützt (de, en).")
            p["language"] = value
        elif key == "style":
            if value not in STYLES:
                raise StudioError("validation_error", "Unbekannter Stil.")
            p["style"] = value
        elif key == "aspect_ratio":
            if value not in ASPECT_RATIOS:
                raise StudioError("validation_error", "Seitenverhältnis nicht unterstützt.")
            p["aspect_ratio"] = value
        elif key == "resolution":
            if value not in RESOLUTIONS:
                raise StudioError("validation_error", "Auflösung nicht unterstützt.")
            p["resolution"] = value
        elif key == "scenes":
            if not isinstance(value, list) or len(value) > 80:
                raise StudioError("validation_error", "Ungültige Szenenliste (max. 80).")
            scenes = [normalize_scene(s, project_dir) for s in value]
            ids = [s["id"] for s in scenes]
            if len(set(ids)) != len(ids):
                raise StudioError("validation_error", "Szenen-IDs müssen eindeutig sein.")
            p["scenes"] = scenes
        elif key == "captions":
            if not isinstance(value, dict) or value.get("style") not in CAPTION_STYLES:
                raise StudioError("validation_error", "Unbekannter Caption-Stil.")
            p["captions"] = value
        elif key == "music":
            if not isinstance(value, dict):
                raise StudioError("validation_error", "Ungültige Musik-Einstellungen.")
            track = value.get("track")
            if track:
                resolve_music(project_dir, str(track))
            p["music"] = value
        elif key == "visuals":
            if not isinstance(value, dict):
                raise StudioError("validation_error", "Ungültige Visual-Einstellungen.")
            av = value.get("avatar_image")
            if av:
                av = safe_filename(str(av))
                if os.path.splitext(av)[1].lower() not in IMAGE_EXT or not os.path.isfile(
                        safe_child(os.path.join(project_dir, "media"), av)):
                    raise StudioError("media_not_found", "Avatar-Bild nicht gefunden.", 404)
                value = {**value, "avatar_image": av}
            gm = value.get("gameplay_media")
            if gm:
                gm = safe_filename(str(gm))
                if not os.path.isfile(safe_child(os.path.join(project_dir, "media"), gm)):
                    raise StudioError("media_not_found", "Gameplay-Datei nicht gefunden.", 404)
                value = {**value, "gameplay_media": gm}
            p["visuals"] = value
        elif key == "options":
            from .options import ProductionOptions
            if not isinstance(value, dict):
                raise StudioError("validation_error", "Ungültige Produktionsoptionen.")
            p["options"] = ProductionOptions.from_dict(
                {**p.get("options", {}), **value}, strict=True).to_dict()
        elif key == "voice":
            if not isinstance(value, dict):
                raise StudioError("validation_error", "Ungültige Voice-Einstellungen.")
            pid = str(value.get("provider") or "auto")
            if pid != "auto":
                from .providers import get_voice
                get_voice(pid)
            p["voice"] = value
        else:
            p[key] = value
    return migrate(p)


def resolve_music(project_dir: str, track: str) -> str:
    """`library:<datei>` oder `project:<datei>` → geprüfter absoluter Pfad."""
    from .audio import AUDIO_EXT, music_path
    kind, _, name = track.partition(":")
    if kind == "library":
        return music_path(name)
    if kind == "project":
        safe = safe_filename(name)
        path = safe_child(os.path.join(project_dir, "media"), safe)
        if safe == name and os.path.isfile(path) and os.path.splitext(safe)[1].lower() in AUDIO_EXT:
            return path
    raise StudioError("music_not_found", "Musiktitel nicht gefunden.", 404)


class ProjectStore:
    def __init__(self, base: str | None = None) -> None:
        self.base = os.path.join(base or studio_dir(), "projects")
        os.makedirs(self.base, exist_ok=True)

    def dir(self, pid: str) -> str:
        return safe_child(self.base, require_id(pid, "Projekt-ID"))

    def _path(self, pid: str) -> str:
        return os.path.join(self.dir(pid), "project.json")

    def exists(self, pid: str) -> bool:
        try:
            return os.path.isfile(self._path(pid))
        except StudioError:
            return False

    def load(self, pid: str) -> dict:
        data = read_json(self._path(pid), None)
        if not isinstance(data, dict):
            raise StudioError("project_not_found", "Projekt nicht gefunden.", 404)
        project = migrate(data)
        project["id"] = pid
        return project

    def create(self, project: dict) -> dict:
        pid = project["id"]
        pdir = self.dir(pid)
        for sub in ("source", "artifacts", "media", "renders", "cache", "versions"):
            os.makedirs(os.path.join(pdir, sub), exist_ok=True)
        project = migrate(project)
        project["version"] = 1
        write_json_atomic(self._path(pid), project)
        return project

    def save(self, project: dict, expected_version: int | None = None) -> dict:
        """Speichert atomar. Mit expected_version: Konflikt → 409."""
        pid = project["id"]
        with _lock(pid):
            current = self.load(pid)
            if expected_version is not None and int(expected_version) != current["version"]:
                raise StudioError(
                    "version_conflict",
                    "Das Projekt wurde zwischenzeitlich geändert. Bitte neu laden.",
                    409, {"current_version": current["version"],
                          "expected_version": int(expected_version)})
            self._snapshot(pid, current)
            project = migrate(project)
            project["version"] = current["version"] + 1
            project["created_at"] = current["created_at"]
            project["updated_at"] = now_iso()
            write_json_atomic(self._path(pid), project)
            return project

    def mutate(self, pid: str, fn) -> dict:
        """Interne (Hintergrund-)Änderung unter Sperre, ohne Versionsprüfung."""
        with _lock(pid):
            project = self.load(pid)
            fn(project)
            return self.save(project)

    def _snapshot(self, pid: str, current: dict) -> None:
        vdir = os.path.join(self.dir(pid), "versions")
        os.makedirs(vdir, exist_ok=True)
        write_json_atomic(os.path.join(vdir, f"v{current['version']:06d}.json"), current)
        files = sorted(f for f in os.listdir(vdir) if f.endswith(".json"))
        for old in files[:-MAX_SNAPSHOTS]:
            try:
                os.remove(os.path.join(vdir, old))
            except OSError:
                pass

    def versions(self, pid: str) -> list[dict]:
        vdir = os.path.join(self.dir(pid), "versions")
        out = []
        if os.path.isdir(vdir):
            for name in sorted(os.listdir(vdir), reverse=True):
                data = read_json(os.path.join(vdir, name), None)
                if isinstance(data, dict):
                    out.append({"version": data.get("version"),
                                "updated_at": data.get("updated_at"),
                                "scene_count": len(data.get("scenes") or [])})
        return out

    def restore_version(self, pid: str, version: int) -> dict:
        path = os.path.join(self.dir(pid), "versions", f"v{int(version):06d}.json")
        data = read_json(path, None)
        if not isinstance(data, dict):
            raise StudioError("version_not_found", "Diese Version gibt es nicht (mehr).", 404)
        data["id"] = pid
        return self.save(data)

    def list(self) -> list[dict]:
        out = []
        for name in os.listdir(self.base):
            try:
                p = self.load(name)
            except StudioError:
                continue
            out.append(summary(p))
        return sorted(out, key=lambda s: s["updated_at"], reverse=True)

    def delete(self, pid: str) -> None:
        pdir = self.dir(pid)
        if not os.path.isfile(os.path.join(pdir, "project.json")):
            raise StudioError("project_not_found", "Projekt nicht gefunden.", 404)
        shutil.rmtree(pdir, ignore_errors=True)

    def duplicate(self, pid: str, title: str | None = None, lineage: dict | None = None) -> dict:
        src = self.load(pid)
        new = copy.deepcopy(src)
        new["id"] = new_id()
        new["title"] = (title or f"{src['title']} (Kopie)")[:120]
        new["exports"] = []
        new["linked_job_id"] = None
        new["lineage"] = {"parent_id": pid, **(lineage or {})}
        new["created_at"] = new["updated_at"] = now_iso()
        created = self.create(new)
        for sub in ("media", "source", "artifacts"):
            s, d = os.path.join(self.dir(pid), sub), os.path.join(self.dir(new["id"]), sub)
            if os.path.isdir(s):
                shutil.copytree(s, d, dirs_exist_ok=True)
        return created


def summary(p: dict) -> dict:
    return {
        "id": p["id"], "title": p["title"], "workflow": p["workflow"],
        "language": p["language"], "status": p["status"],
        "status_error": p.get("status_error"), "aspect_ratio": p["aspect_ratio"],
        "resolution": p["resolution"], "scene_count": len(p["scenes"]),
        "version": p["version"], "linked_job_id": p.get("linked_job_id"),
        "export_count": len(p.get("exports") or []),
        "created_at": p["created_at"], "updated_at": p["updated_at"],
    }
