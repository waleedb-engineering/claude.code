"""ClipForge AI — dünner FastAPI-Layer über dem bestehenden Pipeline-Kern.

Dies ist NUR eine HTTP-Brücke. Die komplette Produktlogik liegt unverändert in
clipforge.pipeline.run_pipeline. Hier gibt es keine Analyse-/Render-Logik,
keine Datenbank, kein Auth, keine neuen Features.

Start (aus dem Ordner api/):
    uvicorn app:app --reload --port 8000
oder vom Repo-Root:
    uvicorn api.app:app --reload --port 8000
"""

from __future__ import annotations

import datetime
import glob
import io
import json
import os
import shutil
import sys
import zipfile

# Eigenen Ordner auf den Pfad legen, damit `import clipforge` / `import jobs`
# unabhängig vom Startverzeichnis funktioniert.
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, StreamingResponse

from clipforge.ffmpeg_utils import FFmpegNotFound, ensure_ffmpeg
from jobs import Job, JobRegistry

# Erlaubte Video-Endungen (Fehlerfall: ungültiger Dateityp)
ALLOWED_EXT = {".mp4", ".mov", ".mkv", ".webm", ".avi", ".m4v"}

JOBS_DIR = os.environ.get(
    "CLIPFORGE_JOBS_DIR", os.path.join(os.path.dirname(os.path.abspath(__file__)), "jobs")
)

app = FastAPI(title="ClipForge AI API", version="0.1.0")

# CORS offen für lokale Entwicklung (Next.js-Client kommt in Schritt 3).
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)

registry = JobRegistry(JOBS_DIR)


# --------------------------------------------------------------------------
# Helfer
# --------------------------------------------------------------------------

def _require_job(job_id: str):
    job = registry.get(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="Job nicht gefunden.")
    return job


def _mp4_paths(job: Job) -> list[str]:
    """Alle gerenderten Clip-MP4s im Job-Ordner (sortiert)."""
    return sorted(glob.glob(os.path.join(job.job_dir, "clip_*.mp4")))


def _files_summary(job: Job) -> dict:
    """Übersicht über die im Job-Ordner vorhandenen Ergebnis-Dateien."""
    mp4s = _mp4_paths(job)
    result = job.result or {}
    return {
        "clip_count": result.get("clip_count", 0),
        "mp4_count": len(mp4s),
        "has_transcript": os.path.exists(os.path.join(job.job_dir, "transcript.json")),
        "has_clips_json": os.path.exists(os.path.join(job.job_dir, "clips.json")),
        "exports_ready": len(mp4s) > 0,
    }


# --------------------------------------------------------------------------
# Health
# --------------------------------------------------------------------------

@app.get("/health")
def health() -> dict:
    """Prüft, ob das Backend (und FFmpeg) bereit ist."""
    ffmpeg_ok = True
    ffmpeg_error = None
    try:
        ensure_ffmpeg()
    except FFmpegNotFound as exc:
        ffmpeg_ok = False
        ffmpeg_error = str(exc)
    return {
        "status": "ok",
        "service": "clipforge-api",
        "version": app.version,
        "ffmpeg": ffmpeg_ok,
        "ffmpeg_error": ffmpeg_error,
        "jobs_dir": JOBS_DIR,
    }


# --------------------------------------------------------------------------
# Jobs
# --------------------------------------------------------------------------

@app.post("/api/jobs")
async def create_job(
    file: UploadFile = File(...),
    transcript: UploadFile | None = File(default=None),
    top_n: int = Form(default=5),
    remove_silence: bool = Form(default=True),
    caption_mode: str = Form(default="karaoke"),
    caption_style: str = Form(default="high_energy"),
    reframe_mode: str = Form(default="smart"),
) -> dict:
    """Lädt ein Video hoch, legt einen Job an und startet die Analyse im Hintergrund.

    `transcript` (optional, JSON) spiegelt das bestehende CLI-Flag --transcript
    und erlaubt das Überspringen der lokalen Whisper-Transkription (nützlich für
    schnelle/deterministische Tests). Kein neues Feature — nur ein vorhandener
    Kern-Parameter, über HTTP erreichbar gemacht.
    """
    filename = file.filename or ""
    ext = os.path.splitext(filename)[1].lower()
    if not filename or ext not in ALLOWED_EXT:
        raise HTTPException(
            status_code=400,
            detail=(
                f"Ungültiger Dateityp '{ext or '?'}'. Erlaubt: "
                f"{', '.join(sorted(ALLOWED_EXT))}."
            ),
        )

    top_n = max(1, int(top_n))
    job = registry.create(
        filename=filename,
        top_n=top_n,
        remove_silence=remove_silence,
        caption_mode=caption_mode,
        caption_style=caption_style,
        reframe_mode=reframe_mode,
    )

    # Upload speichern: jobs/<id>/input.<ext>
    input_path = os.path.join(job.job_dir, f"input{ext}")
    try:
        with open(input_path, "wb") as out:
            shutil.copyfileobj(file.file, out)
    finally:
        await file.close()
    job.input_path = input_path

    # Optionales Transkript speichern
    if transcript is not None and transcript.filename:
        transcript_path = os.path.join(job.job_dir, "source_transcript.json")
        try:
            with open(transcript_path, "wb") as out:
                shutil.copyfileobj(transcript.file, out)
        finally:
            await transcript.close()
        job.transcript_path = transcript_path

    registry.start(job)
    return {"job_id": job.id, "status": job.status}


@app.get("/api/jobs")
def list_jobs() -> dict:
    """Listet alle Jobs mit Kurzstatus."""
    return {"jobs": [job.summary() for job in registry.list()]}


@app.get("/api/jobs/{job_id}")
def get_job(job_id: str) -> dict:
    """Voller Status: Zustand, Progress/Logs, Fehler, Ergebnisübersicht.

    Zusätzlich `files`: Anzahl erkannter Clips, Anzahl MP4-Exporte, und ob
    transcript.json / clips.json vorhanden sind.
    """
    job = _require_job(job_id)
    data = job.to_dict()
    data["files"] = _files_summary(job)
    return data


@app.get("/api/jobs/{job_id}/transcript")
def get_transcript(job_id: str):
    """Gibt transcript.json zurück (falls vorhanden)."""
    job = _require_job(job_id)
    path = os.path.join(job.job_dir, "transcript.json")
    if not os.path.exists(path):
        raise HTTPException(
            status_code=404,
            detail="transcript.json noch nicht vorhanden (Job evtl. nicht fertig).",
        )
    return FileResponse(path, media_type="application/json", filename="transcript.json")


@app.get("/api/jobs/{job_id}/clips")
def get_clips(job_id: str):
    """Gibt clips.json zurück (falls vorhanden)."""
    job = _require_job(job_id)
    path = os.path.join(job.job_dir, "clips.json")
    if not os.path.exists(path):
        raise HTTPException(
            status_code=404,
            detail="clips.json noch nicht vorhanden (Job evtl. nicht fertig).",
        )
    return FileResponse(path, media_type="application/json", filename="clips.json")


def _resolve_clip_path(job: Job, clip_index: int) -> tuple[str, str]:
    """Liefert (absoluter_pfad, dateiname) des Clips oder wirft 404."""
    result = job.result or {}
    clips = result.get("clips") or []
    if not clips:
        raise HTTPException(
            status_code=404,
            detail="Keine Clips vorhanden (Job nicht fertig oder leeres Ergebnis).",
        )
    match = next((c for c in clips if c["index"] == clip_index), None)
    if match is None:
        raise HTTPException(status_code=404, detail=f"Clip {clip_index} nicht gefunden.")
    output_file = match.get("output_file")
    if not output_file:
        raise HTTPException(
            status_code=404, detail="Exportdatei fehlt (Clip wurde nicht gerendert)."
        )
    path = os.path.join(job.job_dir, output_file)
    if not os.path.exists(path):
        raise HTTPException(
            status_code=404, detail="Exportdatei fehlt auf dem Datenträger."
        )
    return path, output_file


@app.get("/api/jobs/{job_id}/clips/{clip_index}/download")
def download_clip(job_id: str, clip_index: int):
    """Lädt den gerenderten Clip <clip_index> (1-basiert) als MP4 (Attachment)."""
    job = _require_job(job_id)
    path, output_file = _resolve_clip_path(job, clip_index)
    # filename= -> Content-Disposition: attachment (erzwingt Download)
    return FileResponse(path, media_type="video/mp4", filename=output_file)


@app.get("/api/jobs/{job_id}/clips/{clip_index}/preview")
def preview_clip(job_id: str, clip_index: int):
    """Streamt den Clip browserfähig (inline, mit Range-Support fürs Abspielen).

    Ohne `filename=` setzt Starlette keine attachment-Disposition -> der Browser
    spielt das Video inline ab. FileResponse beantwortet Range-Requests (206),
    was Seeking in der <video>-Vorschau ermöglicht.
    """
    job = _require_job(job_id)
    path, _ = _resolve_clip_path(job, clip_index)
    return FileResponse(path, media_type="video/mp4")


@app.get("/api/jobs/{job_id}/exports.zip")
def export_zip(job_id: str):
    """Bündelt alle vorhandenen MP4-Clips (+ clips.json/transcript.json/meta) als ZIP."""
    job = _require_job(job_id)
    mp4s = _mp4_paths(job)
    if not mp4s:
        raise HTTPException(
            status_code=404,
            detail="Keine exportierten Clips vorhanden (Job nicht fertig oder leeres Ergebnis).",
        )

    # Schnitt-/Scorer-Infos aus clips.json lesen (falls vorhanden)
    scorer = None
    remove_silence = job.remove_silence
    audio_smoothing = False
    total_removed = 0.0
    caption_mode = job.caption_mode
    caption_style = job.caption_style
    caption_fallback_count = 0
    reframe_mode = job.reframe_mode
    reframe_fallback_count = 0
    clips_json_path = os.path.join(job.job_dir, "clips.json")
    if os.path.exists(clips_json_path):
        try:
            with open(clips_json_path, "r", encoding="utf-8") as fh:
                cj = json.load(fh)
            scorer = cj.get("scorer")
            remove_silence = cj.get("remove_silence", remove_silence)
            audio_smoothing = bool(cj.get("audio_smoothing", False))
            total_removed = float(cj.get("total_removed_silence_seconds", 0.0))
            caption_mode = cj.get("caption_mode", caption_mode)
            caption_style = cj.get("caption_style", caption_style)
            caption_fallback_count = int(cj.get("caption_fallback_count", 0))
            reframe_mode = cj.get("reframe_mode", reframe_mode)
            reframe_fallback_count = int(cj.get("reframe_fallback_count", 0))
        except (OSError, ValueError):
            pass

    now = datetime.datetime.now(datetime.timezone.utc).isoformat()
    metadata = {
        "job_id": job.id,
        "source_filename": job.filename,
        "export_created_at": now,
        "exported_at": now,  # rückwärtskompatibel
        "clip_count": (job.result or {}).get("clip_count", len(mp4s)),
        "mp4_count": len(mp4s),
        "scorer": scorer,
        "remove_silence": remove_silence,
        "audio_smoothing": audio_smoothing,
        "total_removed_silence_seconds": round(total_removed, 2),
        "caption_mode": caption_mode,
        "caption_style": caption_style,
        "caption_fallback_count": caption_fallback_count,
        "reframe_mode": reframe_mode,
        "reframe_fallback_count": reframe_fallback_count,
        "reframe_note": "Reframe/Gesichtserkennung läuft lokal, ohne Cloud.",
        "disclaimer": (
            "Der Performance-Potential-Score ist eine Wahrscheinlichkeits-"
            "Einschätzung und keine Garantie für Reichweite oder Viralität."
        ),
    }

    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        for path in mp4s:
            zf.write(path, arcname=os.path.basename(path))
        # optionale Begleitdateien
        for optional in ("clips.json", "transcript.json"):
            p = os.path.join(job.job_dir, optional)
            if os.path.exists(p):
                zf.write(p, arcname=optional)
        zf.writestr("metadata.json", json.dumps(metadata, ensure_ascii=False, indent=2))
    buf.seek(0)

    filename = f"clipforge_{job.id}_clips.zip"
    return StreamingResponse(
        buf,
        media_type="application/zip",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@app.get("/api/jobs/{job_id}/files")
def list_files(job_id: str) -> dict:
    """Listet alle Dateien im Job-Ordner."""
    job = _require_job(job_id)
    files = []
    for name in sorted(os.listdir(job.job_dir)):
        full = os.path.join(job.job_dir, name)
        if os.path.isfile(full):
            files.append({"name": name, "size_bytes": os.path.getsize(full)})
    return {"job_id": job_id, "files": files}
