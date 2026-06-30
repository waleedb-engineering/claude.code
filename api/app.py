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

import os
import shutil
import sys

# Eigenen Ordner auf den Pfad legen, damit `import clipforge` / `import jobs`
# unabhängig vom Startverzeichnis funktioniert.
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse

from clipforge.ffmpeg_utils import FFmpegNotFound, ensure_ffmpeg
from jobs import JobRegistry

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
    job = registry.create(filename=filename, top_n=top_n)

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
    """Voller Status: Zustand, Progress/Logs, Fehler, Ergebnisübersicht."""
    job = _require_job(job_id)
    return job.to_dict()


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


@app.get("/api/jobs/{job_id}/clips/{clip_index}/download")
def download_clip(job_id: str, clip_index: int):
    """Lädt den gerenderten Clip <clip_index> (1-basiert) als MP4."""
    job = _require_job(job_id)
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
    return FileResponse(path, media_type="video/mp4", filename=output_file)


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
