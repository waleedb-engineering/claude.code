"""Stream Intelligence: Quellen verwalten, analysieren, Highlights rendern.

Speicher je Benutzerbereich: <studio>/streams/<id>/
  meta.json      Titel, Plattform, Rechtebestätigung, Dateien, Status
  source.<ext>   Video (Upload/OBS-Aufnahme)
  chat.json      normierter Chat (aus dem importierten Export)
  analysis.json  Ergebnis inkl. Heatmap und Highlights (manuell korrigierbar)
  previews/      schnelle Vorschauen je Highlight

Gerenderte Highlights werden als normaler ClipForge-Job angelegt — damit
gelten Clip-Editor, Publishing-Planner und Analytics unverändert.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess

from ..studio.errors import StudioError
from ..studio.storage import (new_id, now_iso, read_json, require_id, safe_child, studio_dir,
                              write_json_atomic)
from . import analyze as analyze_mod
from .chat import ChatMessage, parse_chat

PLATFORMS = ("twitch", "youtube", "kick", "obs", "upload")
VIDEO_EXT = {".mp4", ".mkv", ".mov", ".webm", ".flv", ".ts", ".m4v"}
CHAT_EXT = {".json", ".jsonl", ".csv", ".txt"}
HOW_TO_GET = {
    "twitch": "Eigenes VOD: Creator-Dashboard → Inhalte → Videoproduzent → Herunterladen. "
              "Chat: mit TwitchDownloader (Chat → JSON) exportieren.",
    "youtube": "Eigenes Video: YouTube Studio → Inhalte → ⋮ → Herunterladen. Chat-Replay: "
               "z. B. mit chat-downloader als JSON exportieren.",
    "kick": "Eigenes VOD herunterladen; Chat als JSON/CSV exportieren (keine offizielle Chat-API).",
    "obs": "OBS-Aufnahme (am besten MKV) hochladen; im Live-Modus direkt die wachsende Datei.",
    "upload": "Beliebiges eigenes Video.",
}


class StreamService:
    def __init__(self, tasks, registry=None, transcriber=None) -> None:
        self.tasks = tasks
        self.registry = registry
        self.transcriber = transcriber  # Tests: Mock; sonst faster-whisper
        tasks.register("stream_analyze", self._task_analyze)
        tasks.register("stream_render", self._task_render)
        tasks.register("stream_preview", self._task_preview)

    # ------------------------------------------------------------ Ablage
    def _base(self) -> str:
        path = os.path.join(studio_dir(), "streams")
        os.makedirs(path, exist_ok=True)
        return path

    def dir(self, sid: str) -> str:
        return safe_child(self._base(), require_id(sid, "Stream-ID"))

    def load(self, sid: str) -> dict:
        meta = read_json(os.path.join(self.dir(sid), "meta.json"), None)
        if not isinstance(meta, dict):
            raise StudioError("stream_not_found", "Quelle nicht gefunden.", 404)
        return meta

    def _save(self, meta: dict) -> dict:
        meta["updated_at"] = now_iso()
        write_json_atomic(os.path.join(self.dir(meta["id"]), "meta.json"), meta)
        return meta

    def list(self) -> list[dict]:
        out = []
        for sid in sorted(os.listdir(self._base())):
            meta = read_json(os.path.join(self._base(), sid, "meta.json"), None)
            if isinstance(meta, dict):
                out.append(meta)
        return sorted(out, key=lambda m: m.get("created_at", ""), reverse=True)

    def create(self, *, title: str, platform: str, rights_confirmed: bool, user: str | None) -> dict:
        if platform not in PLATFORMS:
            raise StudioError("validation_error", f"Plattform: {', '.join(PLATFORMS)}.")
        if rights_confirmed is not True:
            raise StudioError("rights_confirmation_required",
                              "Bitte bestätigen, dass du die Aufnahme und den Chat auswerten und "
                              "daraus Clips veröffentlichen darfst (eigener Stream oder Erlaubnis).")
        sid = new_id()
        os.makedirs(self.dir(sid))
        return self._save({
            "id": sid, "title": (title or "Stream").strip()[:120], "platform": platform,
            "created_at": now_iso(), "status": "new", "video": None, "chat": None,
            "rights": {"confirmed": True, "at": now_iso(), "by": user or "lokal", "verified": False},
            "how_to_get": HOW_TO_GET[platform]})

    def delete(self, sid: str) -> None:
        self.load(sid)
        shutil.rmtree(self.dir(sid), ignore_errors=True)

    def upload_video(self, sid: str, filename: str, fileobj, save_upload, limit_mb: int) -> dict:
        meta = self.load(sid)
        ext = os.path.splitext(filename or "")[1].lower()
        if ext not in VIDEO_EXT:
            raise StudioError("file_type_not_allowed", f"Videoformat '{ext}' wird nicht unterstützt.", 415)
        dest = os.path.join(self.dir(sid), f"source{ext}")
        size = save_upload(fileobj, dest, limit_mb * 1024 * 1024)
        from ..ffmpeg_utils import probe
        try:
            info = probe(dest)
        except Exception as exc:  # noqa: BLE001
            os.remove(dest)
            raise StudioError("file_unreadable", "Die Datei ist kein lesbares Video.", 415) from exc
        meta["video"] = {"file": os.path.basename(dest), "original_name": (filename or "")[:120],
                         "bytes": size, "duration": round(info.duration or 0, 2),
                         "width": info.width, "height": info.height, "has_audio": info.has_audio}
        meta["status"] = "ready"
        return self._save(meta)

    def upload_chat(self, sid: str, filename: str, raw: bytes) -> dict:
        meta = self.load(sid)
        ext = os.path.splitext(filename or "")[1].lower()
        if ext not in CHAT_EXT:
            raise StudioError("file_type_not_allowed", "Chat-Export als JSON, JSON-Lines oder CSV.", 415)
        try:
            msgs, fmt = parse_chat(raw, filename)
        except ValueError as exc:
            raise StudioError("chat_unreadable", str(exc), 422) from exc
        write_json_atomic(os.path.join(self.dir(sid), "chat.json"),
                          [[round(m.t, 2), m.user, m.text, m.emotes] for m in msgs])
        meta["chat"] = {"format": fmt, "messages": len(msgs), "first": round(msgs[0].t, 1),
                        "last": round(msgs[-1].t, 1),
                        "users": len({m.user for m in msgs}), "original_name": (filename or "")[:120]}
        return self._save(meta)

    def _chat(self, sid: str) -> list[ChatMessage] | None:
        rows = read_json(os.path.join(self.dir(sid), "chat.json"), None)
        if not rows:
            return None
        return [ChatMessage(float(r[0]), r[1], r[2], r[3] or []) for r in rows]

    def source_path(self, sid: str) -> str:
        meta = self.load(sid)
        if not meta.get("video"):
            raise StudioError("source_missing", "Bitte zuerst das Video hochladen.", 409)
        return os.path.join(self.dir(sid), meta["video"]["file"])

    # ---------------------------------------------------------- Analyse
    def start_analyze(self, sid: str, params: dict) -> dict:
        self.source_path(sid)
        clean = {"keywords": [str(k)[:40] for k in (params.get("keywords") or [])][:20],
                 "chat_delay": params.get("chat_delay"),
                 "max_clips": max(1, min(20, int(params.get("max_clips") or 8))),
                 "pre": max(2.0, min(30.0, float(params.get("pre") or 10))),
                 "post": max(2.0, min(30.0, float(params.get("post") or 8))),
                 "max_len": max(10.0, min(180.0, float(params.get("max_len") or 60))),
                 "transcribe": bool(params.get("transcribe", True))}
        if clean["chat_delay"] is not None:
            clean["chat_delay"] = max(0.0, min(30.0, float(clean["chat_delay"])))
        meta = self.load(sid)
        meta["status"] = "analyzing"
        self._save(meta)
        return self.tasks.submit("stream_analyze", None, {"stream_id": sid, **clean})

    def _transcriber(self):
        if self.transcriber is not None:
            return self.transcriber
        try:
            import faster_whisper  # noqa: F401
        except ImportError:
            return None
        from ..transcribe import transcribe_video
        return transcribe_video

    def _task_analyze(self, task: dict, progress, should_cancel) -> dict:
        from ..config import get_settings
        p = task["params"]
        sid = p["stream_id"]
        try:
            result = analyze_mod.analyze(
                self.source_path(sid), chat=self._chat(sid),
                transcriber=self._transcriber() if p.get("transcribe") else None,
                settings=get_settings(), keywords=p.get("keywords"), chat_delay=p.get("chat_delay"),
                max_clips=p["max_clips"], pre=p["pre"], post=p["post"], max_len=p["max_len"],
                progress=progress, should_cancel=should_cancel)
        except Exception as exc:
            meta = self.load(sid)
            meta["status"] = "failed"
            meta["error"] = str(exc)[:200]
            self._save(meta)
            if isinstance(exc, StudioError):
                raise
            raise StudioError("analysis_failed", f"Analyse fehlgeschlagen ({type(exc).__name__}).", 500) from exc
        result["analyzed_at"] = now_iso()
        result["params"] = {k: v for k, v in p.items() if k != "stream_id"}
        write_json_atomic(os.path.join(self.dir(sid), "analysis.json"), result)
        meta = self.load(sid)
        meta["status"] = "analyzed"
        meta["highlight_count"] = len(result["highlights"])
        self._save(meta)
        return {"highlights": len(result["highlights"]), "signals": result["signals"],
                "chat_delay": result["chat_delay"]}

    def analysis(self, sid: str) -> dict:
        self.load(sid)
        data = read_json(os.path.join(self.dir(sid), "analysis.json"), None)
        if not isinstance(data, dict):
            raise StudioError("analysis_missing", "Noch keine Analyse vorhanden.", 404)
        return {k: v for k, v in data.items() if not k.startswith("_")}

    def update_highlight(self, sid: str, hid: str, start: float | None, end: float | None,
                         title: str | None) -> dict:
        """Manuelle Korrektur der Grenzen (Ein-/Ausstieg) oder des Titels."""
        path = os.path.join(self.dir(sid), "analysis.json")
        data = read_json(path, None)
        if not isinstance(data, dict):
            raise StudioError("analysis_missing", "Noch keine Analyse vorhanden.", 404)
        h = next((x for x in data["highlights"] if x["id"] == hid), None)
        if h is None:
            raise StudioError("highlight_not_found", "Highlight nicht gefunden.", 404)
        s = h["start"] if start is None else float(start)
        e = h["end"] if end is None else float(end)
        if not (0 <= s < e <= data["duration"] + 0.01) or e - s < 3 or e - s > 180:
            raise StudioError("validation_error", "Ungültige Grenzen (3–180 s innerhalb der Aufnahme).")
        h.update(start=round(s, 2), end=round(e, 2), edited=True)
        if title is not None:
            h["title"] = title.strip()[:120]
        words = data.get("_words") or []
        h["text"] = " ".join(w["text"] for w in words if s <= w["start"] <= e)[:600]
        write_json_atomic(path, data)
        return h

    # ---------------------------------------------------------- Vorschau
    def preview_path(self, sid: str, hid: str) -> str:
        if not (len(hid) == 3 and hid[0] == "h" and hid[1:].isdigit()):
            raise StudioError("validation_error", "Ungültige Highlight-ID.")
        return os.path.join(self.dir(sid), "previews", f"{hid}.mp4")

    def start_preview(self, sid: str, hid: str) -> dict:
        self.preview_path(sid, hid)
        self.analysis(sid)
        return self.tasks.submit("stream_preview", None, {"stream_id": sid, "highlight": hid})

    def _highlight(self, sid: str, hid: str) -> dict:
        data = read_json(os.path.join(self.dir(sid), "analysis.json"), {}) or {}
        h = next((x for x in data.get("highlights", []) if x["id"] == hid), None)
        if h is None:
            raise StudioError("highlight_not_found", "Highlight nicht gefunden.", 404)
        return h

    def _task_preview(self, task: dict, progress, should_cancel) -> dict:
        sid, hid = task["params"]["stream_id"], task["params"]["highlight"]
        h = self._highlight(sid, hid)
        out = self.preview_path(sid, hid)
        os.makedirs(os.path.dirname(out), exist_ok=True)
        subprocess.run(["ffmpeg", "-y", "-v", "error", "-ss", f"{h['start']:.2f}", "-to", f"{h['end']:.2f}",
                        "-i", self.source_path(sid), "-vf", "scale=-2:360", "-c:v", "libx264",
                        "-preset", "ultrafast", "-crf", "30", "-c:a", "aac", "-b:a", "96k",
                        "-movflags", "+faststart", out], check=True, timeout=600)
        return {"preview": hid}

    # ------------------------------------------------------------ Render
    def start_render(self, sid: str, ids: list[str], options: dict) -> dict:
        if self.registry is None:
            raise StudioError("jobs_unavailable", "Die Job-Verwaltung ist nicht verfügbar.", 503)
        for hid in ids:
            self._highlight(sid, hid)
        if not ids:
            raise StudioError("validation_error", "Bitte mindestens ein Highlight wählen.")
        opts = {"reframe_mode": options.get("reframe_mode") if options.get("reframe_mode") in
                ("smart", "center", "face") else "smart",
                "remove_silence": bool(options.get("remove_silence", True)),
                "caption_mode": "karaoke" if options.get("caption_mode", "karaoke") == "karaoke" else "standard",
                "caption_style": options.get("caption_style") if options.get("caption_style") in
                ("clean", "high_energy") else "high_energy"}
        return self.tasks.submit("stream_render", None, {"stream_id": sid, "ids": ids[:20], **opts})

    def _task_render(self, task: dict, progress, should_cancel) -> dict:
        from ..config import get_settings
        from ..models import ScoreBreakdown, ScoredClip, Word
        from ..render import render_clip
        from ..content import generate_content_package
        from ..studio.tasks import TaskCanceled
        p = task["params"]
        sid = p["stream_id"]
        meta = self.load(sid)
        src = self.source_path(sid)
        data = read_json(os.path.join(self.dir(sid), "analysis.json"), {}) or {}
        words = [Word(w["text"], w["start"], w["end"]) for w in data.get("_words", [])]
        settings = get_settings()
        chosen = [self._highlight(sid, hid) for hid in p["ids"]]

        def build(job_dir: str) -> dict:
            clips = []
            for i, h in enumerate(chosen, start=1):
                if should_cancel():
                    raise TaskCanceled()
                progress(f"Clip {i}/{len(chosen)} wird gerendert ({h['start']:.0f}–{h['end']:.0f} s) …")
                cw = [w for w in words if h["start"] <= w.start < h["end"]]
                sc = float(h["score"])
                clip = ScoredClip(
                    start=h["start"], end=h["end"], text=h.get("text") or meta["title"], score=sc,
                    breakdown=ScoreBreakdown(hook=sc, clarity=sc, emotion=sc, pacing=sc, payoff=sc),
                    reason="; ".join(h["reasons"][:4]), words=cw, scorer="stream_signals",
                    analyzer_version="stream-v1", analyzer_mode="multimodal_signals",
                    performance_score=sc, score_reason="; ".join(h["reasons"][:4]))
                out = os.path.join(job_dir, f"clip_{i:02d}_score{int(sc)}.mp4")
                render_clip(src, clip, out, settings, remove_silence=p["remove_silence"],
                            caption_mode=p["caption_mode"], caption_style=p["caption_style"],
                            reframe_mode=p["reframe_mode"], progress=progress)
                clip.output_path = out
                try:
                    clip.content_package, _ = generate_content_package(clip, settings, language="de")
                except Exception:  # noqa: BLE001 — Texte sind optional
                    clip.content_package = None
                d = clip.to_dict()
                d["stream"] = {"stream_id": sid, "highlight": h["id"], "chat_categories":
                               h.get("chat_categories"), "top_terms": h.get("top_terms")}
                clips.append(d)
            with open(os.path.join(job_dir, "clips.json"), "w", encoding="utf-8") as fh:
                json.dump({"source": f"stream:{sid}", "scorer": "Stream-Signale",
                           "analyzer_version": "stream-v1", "analyzer_mode": "multimodal_signals",
                           "caption_mode": p["caption_mode"], "caption_style": p["caption_style"],
                           "reframe_mode": p["reframe_mode"], "remove_silence": p["remove_silence"],
                           "stream": {"id": sid, "title": meta["title"], "platform": meta["platform"]},
                           "disclaimer": data.get("disclaimer"), "clips": clips},
                          fh, ensure_ascii=False, indent=2)
            return {"clip_count": len(clips), "rendered_count": len(clips), "language": "de",
                    "duration": meta["video"]["duration"],
                    "clips": [{"index": i + 1, "score": c["score"], "start": c["start"], "end": c["end"],
                               "output": os.path.basename(c["output_path"] or "")}
                              for i, c in enumerate(clips)]}

        job = self.registry.import_completed(f"{meta['title']} (Highlights)", build)
        meta["jobs"] = (meta.get("jobs") or []) + [{"job_id": job.id, "highlights": p["ids"],
                                                     "created_at": now_iso()}]
        self._save(meta)
        return {"job_id": job.id, "clips": len(p["ids"])}
