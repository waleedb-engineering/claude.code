"""StudioService: Workflows Quelle → Projekt → Szenen → Render → Export.

Die gesamte Fachlogik des Studios läuft über diese Klasse; HTTP-Routen, CLI
und Automation rufen nur sie auf. Lange Arbeit (Ingest, Render) läuft als
persistente Hintergrund-Aufgabe (`tasks.TaskManager`).
"""

from __future__ import annotations

import json
import os
import shutil

from ..config import get_settings
from ..ffmpeg_utils import probe
from ..models import CandidateClip, Word
from . import extract, safe_fetch, scriptgen
from .audio import AUDIO_EXT, detect_beats, run_ffmpeg
from .costs import CostLedger, estimate_project
from .errors import BudgetExceeded, StudioError
from .flags import is_enabled
from .options import ProductionOptions, options_of
from .projects import (
    IMAGE_EXT, VIDEO_EXT, WORKFLOWS, ProjectStore, apply_patch, new_project,
    normalize_scene, summary,
)
from .quality import pre_render_checks
from .render import RenderCanceled, render_project, render_scene_preview
from .storage import new_id, now_iso, read_json, require_id, safe_child, safe_filename, write_json_atomic
from .tasks import TaskCanceled, TaskManager

TEXT_WORKFLOWS = ("prompt", "script", "cinematic", "idea", "product_ad")
URL_WORKFLOWS = ("article_url", "website_review", "social_url")
FILE_WORKFLOWS = ("pdf", "audio", "music", "podcast", "longform", "media")
UNAVAILABLE = {
    "avatar": (None,
               "Talking Avatar ist nicht verfügbar: Es ist noch kein Avatar-Provider "
               "angebunden."),
}
SOURCE_EXT = {
    "pdf": {".pdf"},
    "audio": AUDIO_EXT | VIDEO_EXT,
    "music": AUDIO_EXT,
    "podcast": AUDIO_EXT | VIDEO_EXT,
    "longform": VIDEO_EXT,
    "youtube": VIDEO_EXT,
}
WORKFLOW_INFO = [
    # id, braucht, lokal lauffähig
    ("prompt", "text", True), ("script", "text", True), ("article_url", "url", True),
    ("website_review", "url", True), ("social_url", "url", True), ("pdf", "file", True),
    ("audio", "file", True), ("music", "file", True), ("podcast", "file", True),
    ("longform", "file", True), ("media", "file", True), ("job", "job", True),
    ("product_ad", "product", True), ("cinematic", "text", True),
    ("youtube", "youtube", True), ("avatar", "text", False),
]


def _env_mb(name: str, default: int) -> int:
    try:
        return max(1, int(os.environ.get(name, default)))
    except (TypeError, ValueError):
        return default


def save_upload(fileobj, dest: str, max_bytes: int) -> int:
    """Streamt einen Upload nach `dest` und bricht hart am Größenlimit ab."""
    total = 0
    tmp = dest + ".upload"
    try:
        with open(tmp, "wb") as out:
            while True:
                chunk = fileobj.read(1024 * 1024)
                if not chunk:
                    break
                total += len(chunk)
                if total > max_bytes:
                    raise StudioError(
                        "file_too_large",
                        f"Die Datei ist zu groß (Maximum {max_bytes // (1024 * 1024)} MB).", 413)
                out.write(chunk)
        if total == 0:
            raise StudioError("file_empty", "Die Datei ist leer.", 400)
        os.replace(tmp, dest)
    finally:
        if os.path.exists(tmp):
            os.remove(tmp)
    return total


def _sniff_image(path: str) -> bool:
    with open(path, "rb") as fh:
        head = fh.read(16)
    return (head.startswith(b"\x89PNG\r\n\x1a\n") or head.startswith(b"\xff\xd8\xff")
            or (head[:4] == b"RIFF" and head[8:12] == b"WEBP"))


def _probe_av(path: str) -> dict:
    try:
        info = probe(path)
    except Exception as exc:  # noqa: BLE001
        raise StudioError("file_unreadable",
                          "Die Datei ist kein lesbares Audio/Video.", 415) from exc
    if info.duration <= 0 or (not info.has_audio and not info.width):
        raise StudioError("file_unreadable", "Die Datei ist kein lesbares Audio/Video.", 415)
    max_minutes = _env_mb("CLIPFORGE_STUDIO_MAX_SOURCE_MINUTES", 180)
    if info.duration > max_minutes * 60:
        raise StudioError(
            "file_too_long",
            f"Die Datei ist zu lang ({info.duration / 60:.0f} Minuten, Maximum {max_minutes}).",
            413)
    return {"duration": round(info.duration, 2), "width": info.width,
            "height": info.height, "has_audio": info.has_audio}


class StudioService:
    def __init__(self, registry=None, base: str | None = None,
                 tasks: TaskManager | None = None, transcriber=None) -> None:
        self.store = ProjectStore(base)
        self.tasks = tasks or TaskManager(base)
        self.registry = registry          # bestehende ClipForge-JobRegistry (optional)
        self.transcriber = transcriber    # injizierbar (Tests: Mock statt Whisper)
        self.fetch_kwargs: dict = {}      # injizierbar (Tests: Fake-Transport/-Resolver)
        self.llm_client = None
        self.tasks.register("ingest", self._task_ingest)
        self.tasks.register("render", self._task_render)
        self.tasks.register("scene", self._task_scene)
        self.tasks.on_finish(self._on_task_finish)

    def _on_task_finish(self, task: dict) -> None:
        """Hält den Projektstatus konsistent, wenn ein Ingest NICHT sauber endet.

        Ohne das bliebe ein Projekt nach Cancel oder Prozessneustart für immer
        auf „ingesting“ stehen.
        """
        if task.get("kind") != "ingest" or task["status"] not in ("canceled", "interrupted"):
            return
        pid = task.get("project_id")
        if not pid or not self.store.exists(pid):
            return
        if task["status"] == "canceled":
            new_status, err = "draft", {"code": "canceled",
                                        "message": "Die Verarbeitung wurde abgebrochen."}
        else:
            new_status, err = "failed", {
                "code": "interrupted",
                "message": "Die Verarbeitung wurde durch einen Neustart unterbrochen. "
                           "Bitte erneut starten."}

        def apply(p: dict) -> None:
            if p["status"] == "ingesting":
                p["status"], p["status_error"] = new_status, err
        self.store.mutate(pid, apply)

    # ---------------------------------------------------------- Übersicht
    @staticmethod
    def workflows() -> list[dict]:
        out = []
        for wid, needs, local in WORKFLOW_INFO:
            available, reason = True, ""
            if wid in UNAVAILABLE:
                available, reason = False, UNAVAILABLE[wid][1]
            elif needs == "url" and not is_enabled("studio_url_import"):
                available, reason = False, "URL-Import ist per Feature Flag deaktiviert."
            out.append({"id": wid, "needs": needs, "available": available,
                        "reason": reason, "local": local})
        return out

    # ----------------------------------------------------------- Anlegen
    def create_project(self, req: dict) -> dict:
        workflow = req.get("workflow")
        if workflow not in WORKFLOWS:
            raise StudioError("validation_error", "Unbekannter Workflow.")
        if workflow in UNAVAILABLE:
            raise StudioError("workflow_unavailable", UNAVAILABLE[workflow][1], 409)
        language = req.get("language") if req.get("language") in ("de", "en") else "de"
        project = new_project(title=str(req.get("title") or "").strip(),
                              workflow=workflow, language=language)
        source: dict = {"type": workflow}
        if workflow in ("prompt", "cinematic", "idea"):
            text = str(req.get("prompt") or "").strip()
            if len(text) < 3:
                raise StudioError("validation_error", "Bitte ein Thema bzw. einen Prompt eingeben.")
            source["text"] = text[:20000]
        elif workflow == "script":
            text = str(req.get("script") or "").strip()
            if len(text.split()) < 3:
                raise StudioError("validation_error", "Bitte ein Skript mit mindestens drei Wörtern eingeben.")
            source["text"] = text[:50000]
        elif workflow in URL_WORKFLOWS:
            if not is_enabled("studio_url_import"):
                raise StudioError("feature_disabled", "URL-Import ist deaktiviert.", 403)
            safe_fetch.validate_url(str(req.get("url") or ""))
            source["url"] = str(req["url"]).strip()
        elif workflow == "product_ad":
            product = req.get("product") if isinstance(req.get("product"), dict) else {}
            name = str(product.get("name") or "").strip()
            if not name:
                raise StudioError("validation_error", "Bitte einen Produktnamen angeben.")
            benefits = product.get("benefits") or []
            if isinstance(benefits, str):
                benefits = [b.strip() for b in benefits.split("\n")]
            source["product"] = {
                "name": name[:120], "problem": str(product.get("problem") or "")[:300],
                "benefits": [str(b)[:200] for b in benefits if str(b).strip()][:5],
                "price": str(product.get("price") or "")[:40],
                "cta": str(product.get("cta") or "")[:120]}
        elif workflow == "youtube":
            if not is_enabled("studio_youtube_import"):
                raise StudioError("feature_disabled", "YouTube-Import ist deaktiviert.", 403)
            from .youtube_import import canonical_url, video_id
            vid = video_id(str(req.get("url") or ""))
            if req.get("rights_confirmed") is not True:
                raise StudioError(
                    "rights_confirmation_required",
                    "Bitte bestätigen, dass du Rechteinhaber des Videos bist oder die "
                    "Erlaubnis zur Bearbeitung hast.")
            source["url"] = canonical_url(vid)
            source["video_id"] = vid
            source["rights"] = {"confirmed": True, "confirmed_at": now_iso(),
                                "statement": "Rechteinhaber oder Erlaubnis zur Bearbeitung",
                                "verified": False}
        elif workflow == "job":
            job_id = str(req.get("job_id") or "")
            if self.registry is None or self.registry.get(job_id) is None:
                raise StudioError("job_not_found", "ClipForge-Job nicht gefunden.", 404)
            source["job_id"] = job_id
        else:  # Datei-Workflows: Quelle wird separat hochgeladen
            source["text"] = str(req.get("prompt") or "").strip()[:20000]
        project["source"] = source
        project["tone"] = str(req.get("tone") or "")[:40]
        if workflow == "cinematic":
            project["style"] = "cinematic"
        try:
            target = int(req.get("target_seconds") or 45)
        except (TypeError, ValueError):
            target = 45
        project["source"]["target_seconds"] = max(10, min(target, 600))
        # EIN typisiertes Produktionsmodell: API → project.json → Pipeline
        raw_options = dict(req.get("options") or {})
        raw_options.setdefault("duration_target", project["source"]["target_seconds"])
        options = ProductionOptions.from_dict(raw_options, strict=True)
        project["options"] = options.to_dict()
        project["source"]["target_seconds"] = options.duration_target
        if req.get("aspect_ratio") is None:
            project["aspect_ratio"] = options.default_aspect_ratio()
        if isinstance(req.get("lineage"), dict):
            project["lineage"] = req["lineage"]
        if workflow == "music":
            project["voice"] = {"provider": "none", "voice_id": "silent", "tone": ""}
        created = self.store.create(project)
        settings_patch = {k: req[k] for k in (
            "aspect_ratio", "resolution", "captions", "voice", "music", "style",
            "budget_limit_usd") if req.get(k) is not None}
        if settings_patch:
            created = self.store.save(
                apply_patch(created, settings_patch, self.store.dir(created["id"])))
        return created

    # ----------------------------------------------------------- Uploads
    def upload_source(self, pid: str, filename: str, fileobj, kind: str = "source") -> dict:
        project = self.store.load(pid)
        pdir = self.store.dir(pid)
        ext = os.path.splitext(filename or "")[1].lower()
        if kind == "transcript":
            if ext not in (".json", ".srt", ".vtt"):
                raise StudioError("file_type_not_allowed",
                                  "Transkript: .json, .srt oder .vtt erwartet.", 415)
            dest = os.path.join(pdir, "source", "transcript.json")
            raw = dest + ".upload" + ext
            save_upload(fileobj, raw, 20 * 1024 * 1024)
            try:
                if ext == ".json":
                    from ..transcribe import load_transcript_json
                    load_transcript_json(raw)
                    os.replace(raw, dest)
                else:
                    from .youtube_import import subtitles_to_transcript
                    with open(raw, "r", encoding="utf-8", errors="replace") as fh:
                        data = subtitles_to_transcript(fh.read(), project["language"])
                    write_json_atomic(dest, data)
            except StudioError:
                raise
            except Exception as exc:  # noqa: BLE001
                raise StudioError("file_unreadable", "Das Transkript ist ungültig.", 415) from exc
            finally:
                if os.path.exists(raw):
                    os.remove(raw)
            self.store.mutate(pid, lambda p: p["source"].update(transcript_file="transcript.json"))
            return {"file": "transcript.json", "kind": "transcript"}
        allowed = SOURCE_EXT.get(project["workflow"])
        if not allowed:
            raise StudioError("upload_not_expected",
                              "Dieser Workflow erwartet keine Quelldatei.", 409)
        if ext not in allowed:
            raise StudioError(
                "file_type_not_allowed",
                f"Dateityp '{ext or '?'}' ist für diesen Workflow nicht erlaubt "
                f"({', '.join(sorted(allowed))}).", 415)
        limit = _env_mb("CLIPFORGE_STUDIO_MAX_PDF_MB", 50) if ext == ".pdf" else \
            _env_mb("CLIPFORGE_MAX_UPLOAD_MB", 500)
        name = "source" + ext
        dest = safe_child(os.path.join(pdir, "source"), name)
        size = save_upload(fileobj, dest, limit * 1024 * 1024)
        meta: dict = {"bytes": size, "original_name": safe_filename(filename)}
        try:
            if ext == ".pdf":
                with open(dest, "rb") as fh:
                    if fh.read(5) != b"%PDF-":
                        raise StudioError("file_unreadable", "Die Datei ist kein gültiges PDF.", 415)
            else:
                meta.update(_probe_av(dest))
        except StudioError:
            os.remove(dest)
            raise
        self.store.mutate(pid, lambda p: p["source"].update(file=name, file_meta=meta))
        return {"file": name, "kind": "source", **meta}

    def upload_media(self, pid: str, filename: str, fileobj) -> dict:
        self.store.load(pid)
        pdir = self.store.dir(pid)
        name = safe_filename(filename)
        ext = os.path.splitext(name)[1].lower()
        if ext not in IMAGE_EXT | VIDEO_EXT | AUDIO_EXT:
            raise StudioError("file_type_not_allowed",
                              f"Dateityp '{ext or '?'}' wird nicht unterstützt.", 415)
        stem = os.path.splitext(name)[0]
        name = f"{stem}_{new_id()[:6]}{ext}"
        dest = safe_child(os.path.join(pdir, "media"), name)
        os.makedirs(os.path.dirname(dest), exist_ok=True)
        limit = 25 if ext in IMAGE_EXT else _env_mb("CLIPFORGE_MAX_UPLOAD_MB", 500)
        size = save_upload(fileobj, dest, limit * 1024 * 1024)
        meta: dict = {"bytes": size}
        try:
            if ext in IMAGE_EXT:
                if not _sniff_image(dest):
                    raise StudioError("file_unreadable", "Die Datei ist kein gültiges Bild.", 415)
                kind = "image"
            else:
                meta.update(_probe_av(dest))
                kind = "audio" if ext in AUDIO_EXT else "video"
        except StudioError:
            os.remove(dest)
            raise
        return {"name": name, "kind": kind, **meta}

    def list_media(self, pid: str) -> list[dict]:
        mdir = os.path.join(self.store.dir(pid), "media")
        out = []
        if os.path.isdir(mdir):
            for name in sorted(os.listdir(mdir)):
                ext = os.path.splitext(name)[1].lower()
                kind = ("image" if ext in IMAGE_EXT else "video" if ext in VIDEO_EXT
                        else "audio" if ext in AUDIO_EXT else None)
                if kind:
                    out.append({"name": name, "kind": kind,
                                "bytes": os.path.getsize(os.path.join(mdir, name))})
        return out

    def media_path(self, pid: str, name: str) -> str:
        path = safe_child(os.path.join(self.store.dir(pid), "media"), name)
        if not os.path.isfile(path):
            raise StudioError("media_not_found", "Mediendatei nicht gefunden.", 404)
        return path

    def delete_media(self, pid: str, name: str) -> None:
        project = self.store.load(pid)
        path = self.media_path(pid, name)
        used = any(s["visual"].get("media") == name for s in project["scenes"]) or \
            project["visuals"].get("gameplay_media") == name or \
            project["music"].get("track") == f"project:{name}"
        if used:
            raise StudioError("media_in_use", "Die Datei wird im Projekt noch verwendet.", 409)
        os.remove(path)

    # ------------------------------------------------------------ Ingest
    def start_ingest(self, pid: str, idempotency_key: str | None = None) -> dict:
        project = self.store.load(pid)
        if project["workflow"] in SOURCE_EXT and not project["source"].get("file"):
            raise StudioError("source_missing", "Bitte zuerst die Quelldatei hochladen.", 409)
        if project["workflow"] == "media" and not any(
                m["kind"] in ("image", "video") for m in self.list_media(pid)):
            raise StudioError("source_missing", "Bitte zuerst Bilder oder Videos hochladen.", 409)
        for task in self.tasks.list(pid):
            if task["kind"] == "ingest" and task["status"] in ("queued", "running"):
                return task
        self.store.mutate(pid, lambda p: p.update(status="ingesting", status_error=None))
        return self.tasks.submit("ingest", pid, {}, idempotency_key)

    def _artifact(self, pid: str, name: str, data: dict) -> None:
        data = {"created_at": now_iso(), **data}
        write_json_atomic(os.path.join(self.store.dir(pid), "artifacts", name), data)

    def list_artifacts(self, pid: str) -> list[dict]:
        adir = os.path.join(self.store.dir(pid), "artifacts")
        out = []
        if os.path.isdir(adir):
            for name in sorted(os.listdir(adir)):
                if name.endswith(".json"):
                    data = read_json(os.path.join(adir, name), {}) or {}
                    out.append({"name": name, "created_at": data.get("created_at"),
                                "bytes": os.path.getsize(os.path.join(adir, name))})
        return out

    def get_artifact(self, pid: str, name: str) -> dict:
        if not name.endswith(".json"):
            raise StudioError("artifact_not_found", "Artefakt nicht gefunden.", 404)
        data = read_json(safe_child(os.path.join(self.store.dir(pid), "artifacts"), name), None)
        if data is None:
            raise StudioError("artifact_not_found", "Artefakt nicht gefunden.", 404)
        return data

    def _task_ingest(self, task: dict, progress, should_cancel) -> dict:
        pid = task["project_id"]
        try:
            result = self._ingest(pid, progress, should_cancel)
        except TaskCanceled:
            raise  # kein Fehler: der Finish-Hook setzt den Projektstatus
        except StudioError as exc:
            self.store.mutate(pid, lambda p: p.update(status="failed", status_error=exc.to_dict()))
            raise
        except Exception as exc:  # noqa: BLE001
            err = {"code": "internal_error",
                   "message": f"Unerwarteter Fehler bei der Verarbeitung ({type(exc).__name__})."}
            self.store.mutate(pid, lambda p: p.update(status="failed", status_error=err))
            raise StudioError(err["code"], err["message"], 500) from exc
        return result

    def _ingest(self, pid: str, progress, should_cancel) -> dict:
        project = self.store.load(pid)
        pdir = self.store.dir(pid)
        wf = project["workflow"]
        src = project["source"]
        settings = get_settings()
        options = options_of(project)
        title = project["title"] if project["title"] != "Neues Video" else ""
        text = src.get("text") or ""
        scenes: list[dict] | None = None
        extra: dict = {}

        if wf in URL_WORKFLOWS:
            progress("Seite wird sicher abgerufen …")
            fetched = safe_fetch.fetch(src["url"], **self.fetch_kwargs)
            self._artifact(pid, "fetch.json", {
                "url": fetched.url, "final_url": fetched.final_url,
                "status": fetched.status, "content_type": fetched.content_type,
                "bytes": len(fetched.body), "redirects": fetched.redirects})
            progress("Text wird extrahiert …")
            data = extract.extract_html(fetched.body, fetched.content_type)
            self._artifact(pid, "extraction.json", {"source": "url", **data})
            text, title = data["text"], title or data["title"]
            extra["source_meta"] = {k: data[k] for k in ("title", "description", "site_name",
                                                         "word_count")}
        elif wf == "pdf":
            progress("PDF-Text wird extrahiert …")
            data = extract.extract_pdf(safe_child(os.path.join(pdir, "source"), src["file"]))
            self._artifact(pid, "extraction.json", {"source": "pdf", **data})
            text, title = data["text"], title or data["title"]
            extra["source_meta"] = {k: data[k] for k in ("title", "pages", "word_count")}
        elif wf == "job":
            job = self.registry.get(src["job_id"]) if self.registry else None
            tj = read_json(os.path.join(job.job_dir, "transcript.json"), None) if job else None
            if not tj or not tj.get("segments"):
                raise StudioError("job_no_transcript",
                                  "Der Job hat (noch) kein Transkript.", 409)
            text = " ".join(s.get("text", "") for s in tj["segments"]).strip()
            self._artifact(pid, "extraction.json", {
                "source": "job", "job_id": src["job_id"], "text": text,
                "word_count": len(text.split())})
            title = title or job.filename
        elif wf == "audio":
            transcript = self._transcript(pid, src, settings, progress)
            scenes = self._scenes_from_transcript(transcript)
            extra["audio_file"] = src["file"]
            extra["language"] = transcript.get("language")
            title = title or os.path.splitext(src.get("file_meta", {}).get("original_name", "Audio"))[0]
        elif wf == "music":
            track = self._adopt_source_as_media(pid, src["file"])
            progress("Beats werden erkannt …")
            beats = detect_beats(safe_child(os.path.join(pdir, "media"), track))
            self._artifact(pid, "beats.json", {"track": track, "bpm": beats["bpm"],
                                               "beat_count": len(beats["beats"]),
                                               "confidence": beats["confidence"],
                                               "beats": beats["beats"][:2000]})
            extra["music_track"] = f"project:{track}"
            if not text:
                scenes = [normalize_scene({"text": "", "duration": 2.0,
                                           "visual": {"mode": "motion", "seed": i}})
                          for i in range(8)]
        elif wf in ("podcast", "longform"):
            return self._start_shorts_job(pid, project, progress)
        elif wf == "youtube":
            from .youtube_import import fetch_metadata
            progress("Öffentliche YouTube-Metadaten werden abgerufen …")
            meta = fetch_metadata(src["video_id"], self.fetch_kwargs)
            self._artifact(pid, "youtube.json", {**meta, "rights": src.get("rights")})

            def remember(p: dict) -> None:
                p["source"]["meta"] = {k: meta[k] for k in ("title", "author", "thumbnail")}
                if meta.get("title") and p["title"] in ("Neues Video", "New video"):
                    p["title"] = meta["title"][:120]
            self.store.mutate(pid, remember)
            return self._start_shorts_job(pid, self.store.load(pid), progress)
        elif wf == "media":
            media = [m for m in self.list_media(pid) if m["kind"] in ("image", "video")]
            if not media:
                raise StudioError("source_missing", "Bitte zuerst Bilder oder Videos hochladen.", 409)
            lines = [ln.strip() for ln in text.split("\n") if ln.strip()]
            scenes = [normalize_scene({
                "text": lines[i] if i < len(lines) else "",
                "kind": "hook" if i == 0 else "body", "duration": 3.0,
                "visual": {"mode": "media", "media": m["name"]}}) for i, m in enumerate(media)]

        if should_cancel():
            raise TaskCanceled()
        script_meta: dict = {}
        if scenes is None:
            progress("Skript und Szenen werden erstellt …")
            script = scriptgen.generate_script(
                workflow=wf, source_text=text, title=title, language=project["language"],
                target_seconds=options.duration_target, tone=project.get("tone") or "",
                style="cinematic lighting" if project["style"] == "cinematic" else "",
                product=src.get("product"), settings=settings, llm_client=self.llm_client,
                brief=options)
            scenes = [normalize_scene({**s, "visual": {"mode": options.media_type, "seed": i}})
                      for i, s in enumerate(script["scenes"])]
            if scenes and wf != "audio":
                scenes[0]["headline"] = " ".join(script["title"].split()[:4])[:40]
            title = title or script["title"]
            script_meta = {k: script[k] for k in ("generator", "needs_review", "notes")}
            self._artifact(pid, "script.json", {"workflow": wf, "options": options.to_dict(),
                                                **script})
        if not scenes:
            raise StudioError("script_empty", "Aus der Quelle konnten keine Szenen erstellt werden.", 422)
        if should_cancel():  # letzter Checkpoint: nach Cancel nichts mehr schreiben
            raise TaskCanceled()

        def apply(p: dict) -> None:
            p["scenes"] = scenes
            p["script"] = script_meta
            p["status"], p["status_error"] = "ready", None
            if title and p["title"] in ("Neues Video", "New video", "Unbenanntes Projekt"):
                p["title"] = title[:120]
            if extra.get("source_meta"):
                p["source"]["meta"] = extra["source_meta"]
            if extra.get("audio_file"):
                p["source"]["audio_file"] = extra["audio_file"]
                if extra.get("language") in ("de", "en"):
                    p["language"] = extra["language"]
            if extra.get("music_track"):
                p["music"].update(track=extra["music_track"], beat_sync=True, volume=0.9)
        saved = self.store.mutate(pid, apply)
        return {"scene_count": len(saved["scenes"]), "version": saved["version"],
                "generator": script_meta.get("generator")}

    def _transcript(self, pid: str, src: dict, settings, progress) -> dict:
        pdir = self.store.dir(pid)
        if src.get("transcript_file"):
            progress("Mitgeliefertes Transkript wird geladen …")
            data = read_json(os.path.join(pdir, "source", "transcript.json"), None)
            if not data or not data.get("segments"):
                raise StudioError("transcription_empty", "Das Transkript ist leer.", 422)
        else:
            progress("Audio wird lokal transkribiert (Whisper) …")
            data = extract.transcribe_media(
                safe_child(os.path.join(pdir, "source"), src["file"]), settings, self.transcriber)
        self._artifact(pid, "transcript.json", data)
        return data

    @staticmethod
    def _scenes_from_transcript(transcript: dict) -> list[dict]:
        scenes, bucket = [], []

        def flush() -> None:
            if not bucket:
                return
            start, end = bucket[0]["start"], bucket[-1]["end"]
            words = []
            for seg in bucket:
                for w in seg.get("words") or []:
                    words.append({"text": w["text"], "start": max(0.0, w["start"] - start),
                                  "end": max(0.0, w["end"] - start)})
            scenes.append(normalize_scene({
                "text": " ".join(s.get("text", "").strip() for s in bucket).strip(),
                "kind": "hook" if not scenes else "body",
                "audio_source": {"start": start, "end": end}, "words": words,
                "visual": {"mode": "motion", "seed": len(scenes)}}))
            bucket.clear()

        for seg in transcript.get("segments") or []:
            if float(seg.get("end", 0)) <= float(seg.get("start", 0)):
                continue
            if bucket:
                span = float(seg["end"]) - float(bucket[0]["start"])
                count = sum(len(s.get("text", "").split()) for s in bucket)
                if span > 9.0 or count + len(seg.get("text", "").split()) > 26:
                    flush()
            bucket.append(seg)
        flush()
        return scenes[:80]

    def _adopt_source_as_media(self, pid: str, source_name: str) -> str:
        pdir = self.store.dir(pid)
        ext = os.path.splitext(source_name)[1].lower()
        name = f"track{ext}"
        dest = safe_child(os.path.join(pdir, "media"), name)
        os.makedirs(os.path.dirname(dest), exist_ok=True)
        shutil.copyfile(safe_child(os.path.join(pdir, "source"), source_name), dest)
        return name

    def _start_shorts_job(self, pid: str, project: dict, progress) -> dict:
        """Podcast/Longform → bestehender Shorts-Pipeline-Job (kein Duplikat)."""
        if self.registry is None:
            raise StudioError("jobs_unavailable", "Die Shorts-Pipeline ist nicht verfügbar.", 503)
        pdir = self.store.dir(pid)
        src = project["source"]
        source = safe_child(os.path.join(pdir, "source"), src["file"])
        top_n = 3
        job = self.registry.create(
            filename=src.get("file_meta", {}).get("original_name") or src["file"], top_n=top_n,
            caption_mode="karaoke", caption_style="high_energy")
        info = probe(source)
        if info.width and info.height:
            ext = os.path.splitext(source)[1].lower()
            job.input_path = os.path.join(job.job_dir, f"input{ext}")
            shutil.copyfile(source, job.input_path)
        else:  # reines Audio → Video mit ruhigem Hintergrund für die Pipeline
            progress("Audio wird für die Shorts-Pipeline in ein Video gewandelt …")
            job.input_path = os.path.join(job.job_dir, "input.mp4")
            run_ffmpeg(["ffmpeg", "-y", "-f", "lavfi", "-i",
                        "gradients=s=1280x720:c0=#1e3a8a:c1=#7c3aed:speed=0.01:r=15",
                        "-i", source, "-map", "0:v", "-map", "1:a", "-shortest",
                        "-c:v", "libx264", "-preset", "ultrafast", "-pix_fmt", "yuv420p",
                        "-c:a", "aac", job.input_path], "Audio→Video")
        tfile = os.path.join(pdir, "source", "transcript.json")
        if src.get("transcript_file") and os.path.isfile(tfile):
            job.transcript_path = os.path.join(job.job_dir, "source_transcript.json")
            shutil.copyfile(tfile, job.transcript_path)
        self.registry.start(job)
        self._artifact(pid, "shorts_job.json", {"job_id": job.id, "top_n": top_n})

        def apply(p: dict) -> None:
            p["linked_job_id"] = job.id
            p["status"], p["status_error"] = "ready", None
        self.store.mutate(pid, apply)
        progress(f"Shorts-Job {job.id} gestartet.")
        return {"linked_job_id": job.id}

    # ------------------------------------------------------------ Editor
    def update_project(self, pid: str, patch: dict, expected_version: int | None) -> dict:
        if expected_version is None:
            raise StudioError("version_required",
                              "expected_version fehlt (Schutz vor überschriebenen Änderungen).", 428)
        project = self.store.load(pid)
        updated = apply_patch(project, patch, self.store.dir(pid))
        return self.store.save(updated, expected_version)

    def scene_operation(self, pid: str, op: str, expected_version: int | None,
                        scene_id: str | None = None, payload: dict | None = None) -> dict:
        """Serverseitige Szenen-Operationen (für API/CLI/Agenten ohne Editor)."""
        if expected_version is None:
            raise StudioError("version_required", "expected_version fehlt.", 428)
        project = self.store.load(pid)
        scenes = list(project["scenes"])
        payload = payload or {}
        idx = next((i for i, s in enumerate(scenes) if s["id"] == scene_id), None)
        if op == "add":
            scene = normalize_scene({**payload, "id": None}, self.store.dir(pid))
            pos = len(scenes) if idx is None else idx + 1
            scenes.insert(pos, scene)
        elif op == "reorder":
            order = payload.get("order") or []
            by_id = {s["id"]: s for s in scenes}
            if sorted(order) != sorted(by_id):
                raise StudioError("validation_error",
                                  "Die Reihenfolge muss genau alle Szenen-IDs enthalten.")
            scenes = [by_id[i] for i in order]
        else:
            if idx is None:
                raise StudioError("scene_not_found", "Szene nicht gefunden.", 404)
            if op == "delete":
                scenes.pop(idx)
            elif op == "duplicate":
                scenes.insert(idx + 1, {**scenes[idx], "id": new_id()})
            elif op == "update":
                scenes[idx] = normalize_scene({**scenes[idx], **payload, "id": scene_id},
                                              self.store.dir(pid))
            elif op == "move":
                to = max(0, min(len(scenes) - 1, int(payload.get("to", idx))))
                scenes.insert(to, scenes.pop(idx))
            else:
                raise StudioError("validation_error", f"Unbekannte Operation '{op}'.")
        project["scenes"] = scenes
        return self.store.save(project, expected_version)

    def regenerate_scene(self, pid: str, scene_id: str, expected_version: int | None,
                         visual_prompt: str | None = None) -> dict:
        """Erzeugt das Visual EINER Szene neu (neuer Seed) + Szenen-Vorschau."""
        if expected_version is None:
            raise StudioError("version_required", "expected_version fehlt.", 428)
        project = self.store.load(pid)
        scene = next((s for s in project["scenes"] if s["id"] == scene_id), None)
        if scene is None:
            raise StudioError("scene_not_found", "Szene nicht gefunden.", 404)
        scene["visual"]["seed"] = int(scene["visual"].get("seed") or 0) + 1
        if visual_prompt is not None:
            scene["visual_prompt"] = str(visual_prompt)[:300]
        saved = self.store.save(project, expected_version)
        task = self.tasks.submit("scene", pid, {"scene_id": scene_id})
        return {"project": saved, "task": task}

    # ------------------------------------------------------------ Render
    def estimate(self, pid: str) -> dict:
        project = self.store.load(pid)
        est = estimate_project(project)
        est["spent_usd"] = CostLedger(self.store.dir(pid), project["budget_limit_usd"]).spent
        return est

    def quality(self, pid: str) -> dict:
        return pre_render_checks(self.store.load(pid))

    def start_render(self, pid: str, mode: str = "final",
                     idempotency_key: str | None = None, inline: bool = False) -> dict:
        if mode not in ("final", "preview"):
            raise StudioError("validation_error", "mode muss 'final' oder 'preview' sein.")
        project = self.store.load(pid)
        if project.get("linked_job_id") and not project["scenes"]:
            raise StudioError(
                "render_not_applicable",
                "Dieses Projekt wird von der Shorts-Pipeline verarbeitet (siehe verknüpfter Job).", 409)
        checks = pre_render_checks(project)
        if checks["blocking"]:
            raise StudioError("quality_blocked", "Die Qualitätsprüfung blockiert den Render.",
                              409, {"checks": [c for c in checks["checks"] if c["level"] == "fail"]})
        est = estimate_project(project)
        spent = CostLedger(self.store.dir(pid), project["budget_limit_usd"]).spent
        if est["total_usd"] > 0 and spent + est["total_usd"] > project["budget_limit_usd"] + 1e-9:
            raise BudgetExceeded(
                f"Geschätzte Kosten {est['total_usd']:.2f} USD übersteigen das Budget "
                f"({project['budget_limit_usd']:.2f} USD, verbraucht {spent:.2f}). "
                f"Es wurde nichts gestartet.",
                {"estimate_usd": est["total_usd"], "spent_usd": spent,
                 "budget_limit_usd": project["budget_limit_usd"]})
        for task in self.tasks.list(pid):
            if task["kind"] == "render" and task["status"] in ("queued", "running") \
                    and task["params"].get("mode") == mode:
                return task
        return self.tasks.submit("render", pid, {"mode": mode}, idempotency_key,
                                 run_inline=inline)

    def _task_render(self, task: dict, progress, should_cancel) -> dict:
        pid = task["project_id"]
        project = self.store.load(pid)
        try:
            report = render_project(project, self.store.dir(pid), mode=task["params"]["mode"],
                                    progress=progress, should_cancel=should_cancel)
        except RenderCanceled as exc:
            raise TaskCanceled() from exc
        return {k: report[k] for k in ("render_id", "file", "mode", "width", "height",
                                       "duration", "warnings")} | {
            "quality_passed": report["quality"]["passed"]}

    def _task_scene(self, task: dict, progress, should_cancel) -> dict:
        pid = task["project_id"]
        report = render_scene_preview(self.store.load(pid), self.store.dir(pid),
                                      task["params"]["scene_id"], progress=progress)
        return {k: report[k] for k in ("render_id", "file", "mode", "scene_id", "duration",
                                       "warnings")}

    def list_renders(self, pid: str) -> list[dict]:
        rdir = os.path.join(self.store.dir(pid), "renders")
        out = []
        if os.path.isdir(rdir):
            for name in os.listdir(rdir):
                if name.endswith(".json"):
                    data = read_json(os.path.join(rdir, name), None)
                    if isinstance(data, dict) and os.path.isfile(
                            os.path.join(rdir, data.get("file") or "")):
                        data["_mtime"] = os.stat(os.path.join(rdir, name)).st_mtime_ns
                        out.append(data)
        # rendered_at hat nur Sekunden-Auflösung → genaue Dateizeit als Zweitschlüssel,
        # damit „neuester Render“ auch bei mehreren Renders pro Sekunde eindeutig ist.
        return sorted(out, key=lambda r: (r.get("rendered_at") or "", r.get("_mtime", 0)),
                      reverse=True)

    def get_render(self, pid: str, render_id: str) -> dict:
        require_id(render_id, "Render-ID")
        data = read_json(os.path.join(self.store.dir(pid), "renders", f"{render_id}.json"), None)
        if not isinstance(data, dict):
            raise StudioError("render_not_found", "Render nicht gefunden.", 404)
        return data

    def render_file(self, pid: str, render_id: str) -> str:
        require_id(render_id, "Render-ID")
        path = os.path.join(self.store.dir(pid), "renders", f"{render_id}.mp4")
        if not os.path.isfile(path):
            raise StudioError("render_not_found", "Render-Datei nicht gefunden.", 404)
        return path

    # ------------------------------------------------- Export → Publishing
    def export_to_job(self, pid: str, render_id: str | None = None) -> dict:
        """Übergibt einen finalen Render als ClipForge-Job an den Publishing-Planner.

        Idempotent je Render: derselbe Render erzeugt nie zwei Jobs.
        Es wird NICHTS veröffentlicht — nur ein lokaler Job mit Content-Paket.
        """
        from ..content import generate_content_package
        from ..scoring import score_heuristic

        if self.registry is None:
            raise StudioError("jobs_unavailable", "Die Job-Verwaltung ist nicht verfügbar.", 503)
        project = self.store.load(pid)
        renders = [r for r in self.list_renders(pid) if r.get("mode") == "final"]
        if render_id:
            report = self.get_render(pid, render_id)
            if report.get("mode") != "final":
                raise StudioError("render_not_final", "Nur finale Renders können exportiert werden.", 409)
        elif renders:
            report = renders[0]
        else:
            raise StudioError("render_missing", "Bitte zuerst einen finalen Render erstellen.", 409)
        for exp in project["exports"]:
            if exp.get("render_id") == report["render_id"] and self.registry.get(exp["job_id"]):
                return {**exp, "already_exported": True}
        mp4 = self.render_file(pid, report["render_id"])
        text = " ".join(s["text"] for s in project["scenes"] if s["text"]).strip() or project["title"]
        tokens = text.split()
        dur = float(report["duration"]) or 1.0
        words = [Word(text=t, start=i * dur / len(tokens), end=(i + 1) * dur / len(tokens))
                 for i, t in enumerate(tokens)]
        settings = get_settings()
        clip = score_heuristic(CandidateClip(start=0.0, end=dur, text=text, words=words), settings)
        package, _ = generate_content_package(clip, settings, language=project["language"])
        package = dict(package)
        tiktok = package.get("tiktok") or {}
        package["x"] = {"caption": (tiktok.get("caption") or project["title"])[:270],
                        "hashtags": list(tiktok.get("hashtags") or [])[:3]}
        clip.content_package = package
        score = int(clip.score)

        def build(job_dir: str) -> dict:
            name = f"clip_01_score{score}.mp4"
            out = os.path.join(job_dir, name)
            shutil.copyfile(mp4, out)
            clip.output_path = out
            data = clip.to_dict()
            data["studio_project_id"] = pid
            clips_json = {
                "source": f"studio:{pid}", "scorer": "Heuristik", "analyzer_version": "v1",
                "analyzer_mode": "rule_based", "caption_style": project["captions"]["style"],
                "studio": {"project_id": pid, "render_id": report["render_id"],
                           "title": project["title"], "workflow": project["workflow"]},
                "disclaimer": ("Der Performance-Potential-Score ist eine Wahrscheinlichkeits-"
                               "Einschätzung auf Basis messbarer Signale und KEINE Garantie "
                               "für Reichweite oder Viralität."),
                "clips": [data]}
            with open(os.path.join(job_dir, "clips.json"), "w", encoding="utf-8") as fh:
                json.dump(clips_json, fh, ensure_ascii=False, indent=2)
            return {"clip_count": 1, "rendered_count": 1, "language": project["language"],
                    "duration": dur, "studio_project_id": pid,
                    "clips": [{"index": 1, "score": clip.score, "start": 0.0, "end": dur,
                               "duration": dur, "scorer": clip.scorer, "output_file": name,
                               "downloadable": True}]}

        job = self.registry.import_completed(f"Studio: {project['title']}"[:120], build)
        export = {"job_id": job.id, "render_id": report["render_id"], "exported_at": now_iso(),
                  "performance_potential": clip.score}
        self.store.mutate(pid, lambda p: p["exports"].append(export))
        return {**export, "already_exported": False}

    # ------------------------------------------------------ Voice / Remix
    def voice_options(self, language: str, tone: str = "") -> dict:
        from .providers import _VOICES, select_voice
        providers = []
        for prov in _VOICES:
            state, hint = prov.status()
            if state == "disabled":
                continue
            providers.append({
                "id": prov.id, "label": prov.label, "status": state, "hint": hint,
                "paid": prov.paid, "local": prov.local,
                "produces_speech": prov.produces_speech,
                "supports_language": language in prov.languages or prov.id == "none",
                "voices": prov.voices(language) if state == "ready" else []})
        return {"language": language, "tone": tone, "providers": providers,
                "auto_selection": select_voice(language, tone)}

    def voice_preview(self, language: str, provider_id: str, voice_id: str | None,
                      text: str = "", confirm_cost: bool = False, speed: float = 1.0) -> str:
        """Kurze Hörprobe (gecacht). Kostenpflichtige Provider nur mit Bestätigung."""
        import hashlib
        from .providers import get_voice, require_ready, select_voice
        if language not in ("de", "en"):
            raise StudioError("validation_error", "Sprache nicht unterstützt (de, en).")
        choice = select_voice(language, "", provider_id or "auto", voice_id)
        provider = get_voice(choice["provider"])
        require_ready(provider)
        sample = (text or ("Das ist eine kurze Hörprobe dieser Stimme." if language == "de"
                           else "This is a short preview of this voice."))[:200]
        if provider.paid and not confirm_cost:
            raise StudioError(
                "confirmation_required",
                f"Diese Hörprobe kostet ca. {provider.estimate_cost(len(sample)):.3f} USD. "
                f"Bitte mit confirm_cost=true bestätigen.", 409)
        from .storage import studio_dir
        pdir = os.path.join(studio_dir(), "previews")
        os.makedirs(pdir, exist_ok=True)
        speed = max(0.5, min(2.0, float(speed or 1.0)))
        key = hashlib.sha256(
            f"{provider.id}|{choice['voice_id']}|{language}|{sample}|{speed}".encode()).hexdigest()[:20]
        raw, out = os.path.join(pdir, key + ".raw"), os.path.join(pdir, key + ".mp3")
        if not os.path.isfile(out):
            from .errors import ProviderError
            try:
                provider.synthesize(sample, language, choice["voice_id"], raw, speed=speed)
            except ProviderError as exc:
                raise StudioError("provider_failed", f"Hörprobe fehlgeschlagen ({exc}).", 502) from exc
            try:
                run_ffmpeg(["ffmpeg", "-y", "-i", raw, "-ac", "1", "-b:a", "96k", out], "Hörprobe")
            finally:
                if os.path.exists(raw):
                    os.remove(raw)
        return out

    def remix(self, pid: str, metrics: dict | None = None, title: str | None = None) -> dict:
        """Dupliziert ein Projekt und hält fest, welche Merkmale übernommen wurden."""
        from .analytics import remix_traits
        source = self.store.load(pid)
        traits = remix_traits(source, metrics)
        return self.store.duplicate(
            pid, title or f"{source['title']} (Remix)",
            {"remix_of": pid, "traits": traits})

    # ------------------------------------------------------------- Sonst.
    def project_view(self, pid: str) -> dict:
        project = self.store.load(pid)
        tasks = self.tasks.list(pid, limit=10)
        return {"project": project, "tasks": tasks, "renders": self.list_renders(pid)[:10],
                "media": self.list_media(pid), "artifacts": self.list_artifacts(pid)}

    def delete_project(self, pid: str) -> None:
        for task in self.tasks.list(pid):
            if task["status"] in ("queued", "running"):
                raise StudioError("project_busy", "Für das Projekt läuft noch eine Aufgabe.", 409)
        self.store.delete(pid)

    def list_projects(self) -> list[dict]:
        return self.store.list()

    def summary(self, pid: str) -> dict:
        return summary(self.store.load(pid))
