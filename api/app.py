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
from pydantic import BaseModel

from clipforge.brand_kit import (
    BrandKitError,
    load_brand_kit,
    save_brand_kit,
)
from clipforge.captions import STYLES as CAPTION_STYLES
from clipforge.ffmpeg_utils import FFmpegNotFound, ensure_ffmpeg
from clipforge.rerender import (
    ManualExportError,
    RerenderError,
    delete_manual_export,
    list_manual_exports,
    manual_dir,
    manual_export_path,
    rerender_clip,
)
from jobs import (
    STATUS_CANCELED,
    STATUS_COMPLETED,
    STATUS_FAILED,
    STATUS_INCOMPLETE,
    STATUS_INTERRUPTED,
    STATUS_PROCESSING,
    STATUS_QUEUED,
    Job,
    JobBusy,
    JobNotCancelable,
    JobNotFound,
    JobRegistry,
    UnsafeJobPath,
)

# Erlaubte Video-Endungen (Fehlerfall: ungültiger Dateityp)
ALLOWED_EXT = {".mp4", ".mov", ".mkv", ".webm", ".avi", ".m4v"}

JOBS_DIR = os.environ.get(
    "CLIPFORGE_JOBS_DIR", os.path.join(os.path.dirname(os.path.abspath(__file__)), "jobs")
)

# Parallel verarbeitete Jobs (FFmpeg-lastig). Stabilität vor Geschwindigkeit:
# Default 2, per CLIPFORGE_MAX_WORKERS überschreibbar (1 = strikt seriell).
def _max_workers() -> int:
    try:
        return max(1, int(os.environ.get("CLIPFORGE_MAX_WORKERS", "2")))
    except ValueError:
        return 2


def _max_upload_mb() -> int:
    try:
        return max(1, int(os.environ.get("CLIPFORGE_MAX_UPLOAD_MB", "500")))
    except ValueError:
        return 500


def _max_batch_files() -> int:
    try:
        return max(1, int(os.environ.get("CLIPFORGE_MAX_BATCH_FILES", "10")))
    except ValueError:
        return 10


def _upload_size(file: UploadFile) -> int:
    """Ermittelt die Upload-Größe ohne Einlesen (SpooledTemporaryFile seek)."""
    try:
        file.file.seek(0, os.SEEK_END)
        size = file.file.tell()
        file.file.seek(0)
        return size
    except (OSError, AttributeError):
        return 0


app = FastAPI(title="ClipForge AI API", version="0.1.0")

# CORS offen für lokale Entwicklung (Next.js-Client kommt in Schritt 3).
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)

registry = JobRegistry(JOBS_DIR, max_workers=_max_workers())

# Persistente Jobs nach (Neu-)Start aus jobs/ wiederherstellen. Robust:
# kaputte Ordner werden übersprungen, Warnungen werden geloggt. Es wird nie
# ein Job automatisch fortgesetzt.
_restore_warnings = registry.restore()
if _restore_warnings:
    print(f"[clipforge] Job-Restore: {len(_restore_warnings)} Hinweis(e):")
    for _w in _restore_warnings:
        print(f"[clipforge]   - {_w}")
_restored_count = len(registry.list())
if _restored_count:
    print(f"[clipforge] {_restored_count} Job(s) aus {JOBS_DIR} wiederhergestellt.")


# --------------------------------------------------------------------------
# Helfer
# --------------------------------------------------------------------------

def _require_job(job_id: str):
    job = registry.get(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="Job nicht gefunden.")
    return job


def _mp4_paths(job: Job) -> list[str]:
    """Alle automatisch gerenderten Clip-MP4s im Job-Ordner (sortiert)."""
    return sorted(glob.glob(os.path.join(job.job_dir, "clip_*.mp4")))


def _find_input_file(job: Job) -> str | None:
    """Findet die hochgeladene Quelldatei (jobs/<id>/input.*), falls vorhanden."""
    for path in sorted(glob.glob(os.path.join(job.job_dir, "input.*"))):
        if os.path.isfile(path):
            return path
    return None


def _manual_mp4_paths(job: Job) -> list[str]:
    """Alle manuell re-gerenderten MP4s (jobs/<id>/manual_exports/, sortiert)."""
    d = manual_dir(job.job_dir)
    if not os.path.isdir(d):
        return []
    return sorted(glob.glob(os.path.join(d, "*.mp4")))


def _read_clips_json(job: Job) -> dict | None:
    """Liest clips.json (oder None bei Fehlen/Defekt)."""
    path = os.path.join(job.job_dir, "clips.json")
    if not os.path.exists(path):
        return None
    try:
        with open(path, "r", encoding="utf-8") as fh:
            return json.load(fh)
    except (OSError, ValueError):
        return None


def _build_content_packages_doc(cj: dict | None, job_id: str, now: str) -> dict | None:
    """Baut das content_packages.json-Dokument aus clips.json (oder None)."""
    if cj is None:
        return None
    packages = []
    for i, c in enumerate(cj.get("clips") or [], start=1):
        md = c.get("metadata") or {}
        title = None
        for key in ("tiktok", "reels", "shorts"):
            t = (md.get(key) or {}).get("title")
            if t:
                title = t
                break
        content_package = c.get("content_package")
        if not title and content_package:
            title = (content_package.get("youtube_shorts") or {}).get("title")
        if not title:
            title = f"Clip {i}"
        packages.append({
            "clip_index": i,
            "title": title,
            "transcript_excerpt": (c.get("text") or "")[:200],
            "content_package": content_package,
        })
    return {"job_id": job_id, "export_created_at": now, "clips": packages}


def _files_summary(job: Job) -> dict:
    """Übersicht über die im Job-Ordner vorhandenen Ergebnis-Dateien."""
    mp4s = _mp4_paths(job)
    manual = _manual_mp4_paths(job)
    result = job.result or {}
    auto_count = len(mp4s)
    manual_count = len(manual)
    total = auto_count + manual_count
    return {
        "clip_count": result.get("clip_count", 0),
        "mp4_count": auto_count,
        "input_file_exists": _find_input_file(job) is not None,
        "transcript_exists": os.path.exists(os.path.join(job.job_dir, "transcript.json")),
        "clips_json_exists": os.path.exists(os.path.join(job.job_dir, "clips.json")),
        # rückwärtskompatible Aliasnamen (bestehendes Frontend nutzt diese)
        "has_transcript": os.path.exists(os.path.join(job.job_dir, "transcript.json")),
        "has_clips_json": os.path.exists(os.path.join(job.job_dir, "clips.json")),
        "exports_ready": auto_count > 0,
        # Export-Management (Auto vs. manuell)
        "auto_export_count": auto_count,
        "manual_export_count": manual_count,
        "total_export_count": total,
        "has_manual_exports": manual_count > 0,
        "all_exports_ready": total > 0,
    }


def _human_size(n: int) -> str:
    """Bytes → menschenlesbar (z. B. '6.2 MB'). Rein kosmetisch."""
    size = float(n)
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if size < 1024 or unit == "TB":
            return f"{size:.0f} {unit}" if unit == "B" else f"{size:.1f} {unit}"
        size /= 1024
    return f"{size:.1f} TB"


# Status, deren Jobs als „problematisch" gelten und gesammelt aufgeräumt werden
# dürfen. completed/queued/processing gehören BEWUSST nicht dazu.
CLEANUP_STATUSES = (STATUS_FAILED, STATUS_INTERRUPTED, STATUS_INCOMPLETE)


def _job_storage(job: Job) -> dict:
    """Per-Job-Speicherinfo. Robust: kaputte/fehlende Ordner ergeben 0 Bytes."""
    from jobs import _dir_stats  # lokal, um zyklische Importe zu vermeiden

    try:
        files, total = _dir_stats(job.job_dir) if os.path.isdir(job.job_dir) else (0, 0)
    except OSError:
        files, total = 0, 0
    try:
        auto = len(_mp4_paths(job))
        manual = len(_manual_mp4_paths(job))
    except OSError:
        auto = manual = 0
    return {
        "job_id": job.id,
        "status": job.status,
        "filename": job.filename,
        "files_count": files,
        "bytes": total,
        "human_size": _human_size(total),
        "auto_export_count": auto,
        "manual_export_count": manual,
        "restored": job.restored,
        "created_at": job.created_at,
        "updated_at": job.updated_at,
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

    max_mb = _max_upload_mb()
    size = _upload_size(file)
    if size > max_mb * 1024 * 1024:
        await file.close()
        raise HTTPException(
            status_code=413,
            detail=(
                f"Datei zu groß ({size / 1024 / 1024:.0f} MB). "
                f"Maximum {max_mb} MB pro Datei."
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


@app.post("/api/jobs/batch")
async def create_jobs_batch(
    files: list[UploadFile] = File(...),
    top_n: int = Form(default=5),
    remove_silence: bool = Form(default=True),
    caption_mode: str = Form(default="karaoke"),
    caption_style: str = Form(default="high_energy"),
    reframe_mode: str = Form(default="smart"),
) -> dict:
    """Legt für mehrere hochgeladene Videos je einen Job an.

    Robust: eine ungültige/fehlerhafte Datei bricht den Batch NICHT ab — jede
    Datei bekommt ein eigenes Ergebnis (accepted + job_id oder error). Die
    tatsächliche Parallelität begrenzt der ThreadPool (CLIPFORGE_MAX_WORKERS),
    hier werden Jobs nur angelegt und eingereiht. Speicherung wie beim
    Einzel-Upload unter jobs/<id>/ → Restore/Delete/Storage funktionieren gleich.
    """
    if not files:
        raise HTTPException(status_code=400, detail="Keine Dateien übermittelt.")

    max_files = _max_batch_files()
    if len(files) > max_files:
        # Ganze Anfrage ablehnen: zu viele Dateien (Schutz vor Überlast).
        for f in files:
            await f.close()
        raise HTTPException(
            status_code=400,
            detail=(
                f"Zu viele Dateien ({len(files)}). Maximum {max_files} pro Batch."
            ),
        )

    max_bytes = _max_upload_mb() * 1024 * 1024
    top_n = max(1, int(top_n))
    results: list[dict] = []
    accepted = 0
    for file in files:
        filename = file.filename or ""
        ext = os.path.splitext(filename)[1].lower()
        if not filename or ext not in ALLOWED_EXT:
            await file.close()
            results.append({
                "filename": filename or "(ohne Namen)",
                "accepted": False, "job_id": None,
                "error": (
                    f"Ungültiger Dateityp '{ext or '?'}'. Erlaubt: "
                    f"{', '.join(sorted(ALLOWED_EXT))}."
                ),
            })
            continue
        size = _upload_size(file)
        if size > max_bytes:
            await file.close()
            results.append({
                "filename": filename, "accepted": False, "job_id": None,
                "error": (
                    f"Datei zu groß ({size / 1024 / 1024:.0f} MB). "
                    f"Maximum {_max_upload_mb()} MB pro Datei."
                ),
            })
            continue
        try:
            job = registry.create(
                filename=filename, top_n=top_n, remove_silence=remove_silence,
                caption_mode=caption_mode, caption_style=caption_style,
                reframe_mode=reframe_mode,
            )
            input_path = os.path.join(job.job_dir, f"input{ext}")
            with open(input_path, "wb") as out:
                shutil.copyfileobj(file.file, out)
            job.input_path = input_path
            registry.start(job)
            accepted += 1
            results.append({
                "filename": filename, "accepted": True,
                "job_id": job.id, "error": None,
            })
        except Exception as exc:  # noqa: BLE001 — eine Datei darf den Batch nie killen
            results.append({
                "filename": filename, "accepted": False, "job_id": None,
                "error": f"{type(exc).__name__}: {exc}",
            })
        finally:
            await file.close()

    return {
        "accepted_count": accepted,
        "rejected_count": len(files) - accepted,
        "results": results,
    }


@app.get("/api/config")
def get_config() -> dict:
    """Frontend-relevante Limits/Optionen — damit die UI keine Werte doppelt pflegt."""
    return {
        "max_upload_mb": _max_upload_mb(),
        "max_batch_files": _max_batch_files(),
        "max_workers": _max_workers(),
        "supported_video_types": sorted(ALLOWED_EXT),
    }


@app.get("/api/caption-styles")
def get_caption_styles() -> dict:
    """Liste der verfügbaren Caption-Styles (zentral aus captions.STYLES)."""
    styles = [
        {
            "style_id": sid,
            "name": s.name,
            "description": s.description,
            "recommended_for": s.recommended_for,
            "preview_label": s.preview_label,
        }
        for sid, s in CAPTION_STYLES.items()
    ]
    return {"styles": styles, "default": "clean"}


@app.get("/api/brand-kit")
def get_brand_kit() -> dict:
    """Aktuelles Brand Kit (oder Defaults, falls keine Datei existiert)."""
    return load_brand_kit()


class BrandKitPayload(BaseModel):
    brand_name: str = ""
    primary_color: str = "#FFDD00"
    secondary_color: str = "#000000"
    font_family: str | None = None
    caption_style_default: str = "clean"
    highlight_keywords: list[str] = []
    watermark_text: str = ""
    watermark_enabled: bool = False


@app.post("/api/brand-kit")
def post_brand_kit(payload: BrandKitPayload) -> dict:
    """Validiert und speichert das Brand Kit lokal. Ungültig → 400."""
    try:
        return save_brand_kit(payload.model_dump())
    except BrandKitError as exc:
        raise HTTPException(status_code=400, detail=str(exc))


@app.get("/api/jobs")
def list_jobs() -> dict:
    """Listet alle Jobs mit Kurzstatus."""
    return {"jobs": [job.summary() for job in registry.list()]}


@app.get("/api/storage")
def storage_summary(largest: int = 10) -> dict:
    """Lokale Speicher-Übersicht über alle Jobs im jobs/-Ordner.

    Nutzt ausschließlich Registry + Dateisystem (keine DB). Kaputte Job-Ordner
    ergeben 0 Bytes und crashen nicht. `processing`-Jobs werden nur gezählt,
    nie als Cleanup-Kandidat gelistet.
    """
    by_status = {
        STATUS_COMPLETED: 0, STATUS_FAILED: 0, STATUS_INTERRUPTED: 0,
        STATUS_INCOMPLETE: 0, STATUS_PROCESSING: 0, STATUS_QUEUED: 0,
        STATUS_CANCELED: 0,
    }
    total_bytes = 0
    auto_exports = 0
    manual_exports = 0
    per_job: list[dict] = []
    # canceled ist eine EIGENE Gruppe: getrennt sichtbar, aber NICHT Teil des
    # Standard-Bulk-Cleanups (failed/interrupted/incomplete) — damit bewusst
    # abgebrochene Jobs nicht versehentlich gesammelt gelöscht werden.
    cleanup = {STATUS_FAILED: [], STATUS_INTERRUPTED: [], STATUS_INCOMPLETE: [],
               "completed_without_exports": [], STATUS_CANCELED: []}

    for job in registry.list():
        try:
            info = _job_storage(job)
        except Exception:  # noqa: BLE001 — ein kaputter Job darf /storage nie killen
            continue
        by_status[job.status] = by_status.get(job.status, 0) + 1
        total_bytes += info["bytes"]
        auto_exports += info["auto_export_count"]
        manual_exports += info["manual_export_count"]
        per_job.append(info)

        if job.status in cleanup:
            cleanup[job.status].append(job.id)
        elif (
            job.status == STATUS_COMPLETED
            and info["auto_export_count"] == 0
            and info["manual_export_count"] == 0
        ):
            cleanup["completed_without_exports"].append(job.id)

    largest_jobs = sorted(per_job, key=lambda d: d["bytes"], reverse=True)[
        : max(0, largest)
    ]

    return {
        "jobs_root": registry.base_dir,
        "total_jobs": len(per_job),
        "total_bytes": total_bytes,
        "total_human": _human_size(total_bytes),
        "by_status": by_status,
        "counts": {
            "auto_exports": auto_exports,
            "manual_exports": manual_exports,
            "total_exports": auto_exports + manual_exports,
        },
        "largest_jobs": largest_jobs,
        "cleanup_candidates": cleanup,
    }


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


@app.delete("/api/jobs/{job_id}")
def delete_job(job_id: str, force: bool = False) -> dict:
    """Löscht den kompletten Job-Ordner (jobs/<id>/) und entfernt ihn aus der Registry.

    - Löscht **nie** außerhalb von jobs/ (Path-Traversal geblockt).
    - `processing`-Jobs → `409` (außer `?force=true`).
    - Unbekannter Job → `404`.
    Antwort: `{deleted, job_id, removed_files_count, removed_bytes}`.
    """
    try:
        result = registry.delete(job_id, force=force)
    except UnsafeJobPath as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    except JobNotFound:
        raise HTTPException(status_code=404, detail="Job nicht gefunden.")
    except JobBusy as exc:
        raise HTTPException(status_code=409, detail=str(exc))
    if not result.get("deleted"):
        # teilweise gelöscht → klar melden statt still zu schlucken
        raise HTTPException(status_code=500, detail=result.get("error") or "Löschen fehlgeschlagen.")
    return result


@app.post("/api/jobs/{job_id}/cancel")
def cancel_job(job_id: str) -> dict:
    """Bricht einen queued/processing-Job kooperativ ab.

    - queued → sofort `canceled`.
    - processing → `cancel_requested` gesetzt; die Pipeline stoppt am nächsten
      sicheren Checkpoint (laufender Render-Schritt läuft zu Ende). Bereits
      gerenderte Dateien bleiben erhalten.
    - Endzustand (completed/failed/interrupted/incomplete/canceled) → `409`.
    - Unbekannter Job → `404`.
    """
    try:
        return registry.request_cancel(job_id)
    except JobNotFound:
        raise HTTPException(status_code=404, detail="Job nicht gefunden.")
    except JobNotCancelable as exc:
        raise HTTPException(status_code=409, detail=str(exc))


class BulkDeleteRequest(BaseModel):
    job_ids: list[str] = []
    confirm: str | None = None
    force: bool = False


@app.post("/api/jobs/bulk-delete")
def bulk_delete_jobs(req: BulkDeleteRequest) -> dict:
    """Löscht mehrere Jobs über dieselbe sichere `registry.delete()`-Logik.

    - `confirm` muss exakt `"DELETE"` sein → sonst `400`.
    - Leere `job_ids` → `400`.
    - Teilweises Scheitern bricht nicht ab; jedes Ergebnis wird einzeln
      berichtet. `processing`-Jobs ohne `force` werden nicht gelöscht.
    """
    if req.confirm != "DELETE":
        raise HTTPException(
            status_code=400, detail='confirm muss exakt "DELETE" sein.'
        )
    if not req.job_ids:
        raise HTTPException(status_code=400, detail="job_ids darf nicht leer sein.")

    results: list[dict] = []
    deleted_count = 0
    failed_count = 0
    removed_bytes = 0
    for job_id in req.job_ids:
        try:
            res = registry.delete(job_id, force=req.force)
        except UnsafeJobPath as exc:
            results.append({"job_id": job_id, "deleted": False, "error": str(exc)})
            failed_count += 1
            continue
        except JobNotFound:
            results.append({"job_id": job_id, "deleted": False, "error": "Job nicht gefunden."})
            failed_count += 1
            continue
        except JobBusy:
            results.append({
                "job_id": job_id, "deleted": False,
                "error": "processing job cannot be deleted without force",
            })
            failed_count += 1
            continue
        if res.get("deleted"):
            deleted_count += 1
            removed_bytes += res.get("removed_bytes", 0)
            results.append({
                "job_id": job_id, "deleted": True,
                "removed_files_count": res.get("removed_files_count", 0),
                "removed_bytes": res.get("removed_bytes", 0),
            })
        else:
            failed_count += 1
            results.append({
                "job_id": job_id, "deleted": False,
                "error": res.get("error") or "Löschen fehlgeschlagen.",
            })

    return {
        "deleted_count": deleted_count,
        "failed_count": failed_count,
        "removed_bytes": removed_bytes,
        "removed_human": _human_size(removed_bytes),
        "results": results,
    }


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


# --------------------------------------------------------------------------
# Manuelle Re-Renders (Web-Clip-Editor)
# --------------------------------------------------------------------------

class RerenderRequest(BaseModel):
    start_time: float
    end_time: float
    title: str | None = None
    caption_style: str | None = "high_energy"
    caption_mode: str | None = "karaoke"
    remove_silence: bool = True
    reframe_mode: str | None = "smart"
    export_name: str | None = None


def _original_clip_times(job: Job, clip_index: int) -> tuple[float | None, float | None]:
    """Start/Ende des ursprünglichen Auto-Clips (für Metadaten), falls vorhanden."""
    clips = (job.result or {}).get("clips") or []
    match = next((c for c in clips if c.get("index") == clip_index), None)
    if match:
        return match.get("start"), match.get("end")
    return None, None


@app.post("/api/jobs/{job_id}/clips/{clip_index}/rerender")
def rerender(job_id: str, clip_index: int, req: RerenderRequest) -> dict:
    """Rendert einen bestehenden Clip mit manuell gesetzten Optionen neu.

    Der neue Export landet unter jobs/<id>/manual_exports/ und überschreibt die
    automatischen Clips NICHT. Validierungsfehler → 400, fehlende Quell-Dateien
    → 409/404, Render-Fehler → 500 mit klarer Meldung.
    """
    job = _require_job(job_id)

    # Clip-Index muss zu einem erkannten Clip gehören.
    clips = (job.result or {}).get("clips") or []
    if not any(c.get("index") == clip_index for c in clips):
        raise HTTPException(
            status_code=404, detail=f"Clip {clip_index} nicht gefunden."
        )

    logs: list[str] = []
    try:
        metadata = rerender_clip(
            job.job_dir,
            clip_index,
            start_time=req.start_time,
            end_time=req.end_time,
            title=req.title,
            caption_style=req.caption_style or "high_energy",
            caption_mode=req.caption_mode or "karaoke",
            remove_silence=bool(req.remove_silence),
            reframe_mode=req.reframe_mode or "smart",
            export_name=req.export_name,
            progress=logs.append,
        )
    except RerenderError as exc:  # Validierung → 400
        raise HTTPException(status_code=400, detail=str(exc))
    except FileNotFoundError as exc:  # Quellvideo/Transkript fehlt → 409
        raise HTTPException(status_code=409, detail=str(exc))
    except Exception as exc:  # noqa: BLE001 — Render-/Systemfehler → 500
        raise HTTPException(status_code=500, detail=str(exc))

    # Original-Zeiten für die Metadaten nachtragen.
    o_start, o_end = _original_clip_times(job, clip_index)
    metadata["original_start_time"] = o_start
    metadata["original_end_time"] = o_end
    # Persistiertes JSON ebenfalls aktualisieren.
    meta_path = os.path.join(
        job.job_dir, "manual_exports", f"{metadata['export_id']}.json"
    )
    try:
        with open(meta_path, "w", encoding="utf-8") as fh:
            json.dump(metadata, fh, ensure_ascii=False, indent=2)
    except OSError:
        pass

    metadata["log"] = logs
    return metadata


@app.get("/api/jobs/{job_id}/manual-exports")
def get_manual_exports(job_id: str) -> dict:
    """Listet alle manuellen Exporte eines Jobs (neueste zuerst)."""
    job = _require_job(job_id)
    return {"job_id": job_id, "exports": list_manual_exports(job.job_dir)}


@app.get("/api/jobs/{job_id}/manual-exports/{export_id}/preview")
def preview_manual_export(job_id: str, export_id: str):
    """Streamt einen manuell gerenderten Clip inline (Range-Support fürs Abspielen)."""
    job = _require_job(job_id)
    path = manual_export_path(job.job_dir, export_id)
    if not path:
        raise HTTPException(status_code=404, detail="Manueller Export nicht gefunden.")
    return FileResponse(path, media_type="video/mp4")


@app.get("/api/jobs/{job_id}/manual-exports/{export_id}/download")
def download_manual_export(job_id: str, export_id: str):
    """Lädt einen manuell gerenderten Clip als MP4 (Attachment)."""
    job = _require_job(job_id)
    path = manual_export_path(job.job_dir, export_id)
    if not path:
        raise HTTPException(status_code=404, detail="Manueller Export nicht gefunden.")
    return FileResponse(path, media_type="video/mp4", filename=f"{export_id}.mp4")


@app.delete("/api/jobs/{job_id}/manual-exports/{export_id}")
def delete_manual_export_endpoint(job_id: str, export_id: str) -> dict:
    """Löscht MP4 + Sidecar-JSON eines manuellen Exports.

    - Fasst **keine** Auto-Clips an, löscht nur innerhalb von manual_exports/.
    - Unsichere `export_id` → `400`; nicht vorhanden → `404`.
    Antwort: `{deleted, export_id, removed_files, removed_bytes}`.
    """
    job = _require_job(job_id)
    try:
        result = delete_manual_export(job.job_dir, export_id)
    except ManualExportError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    if result is None:
        raise HTTPException(status_code=404, detail="Manueller Export nicht gefunden.")
    return result


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
    content_generator = None
    content_fallback_count = 0
    brand_kit_used = False
    brand_kit_name = None
    cj = _read_clips_json(job)
    if cj is not None:
        scorer = cj.get("scorer")
        remove_silence = cj.get("remove_silence", remove_silence)
        audio_smoothing = bool(cj.get("audio_smoothing", False))
        total_removed = float(cj.get("total_removed_silence_seconds", 0.0))
        caption_mode = cj.get("caption_mode", caption_mode)
        caption_style = cj.get("caption_style", caption_style)
        caption_fallback_count = int(cj.get("caption_fallback_count", 0))
        reframe_mode = cj.get("reframe_mode", reframe_mode)
        reframe_fallback_count = int(cj.get("reframe_fallback_count", 0))
        content_generator = cj.get("content_generator")
        content_fallback_count = int(cj.get("content_fallback_count", 0))
        brand_kit_used = bool(cj.get("brand_kit_used"))
        brand_kit_name = cj.get("brand_kit_name")

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
        "caption_style_default": caption_style,
        "caption_fallback_count": caption_fallback_count,
        "reframe_mode": reframe_mode,
        "reframe_fallback_count": reframe_fallback_count,
        "reframe_note": "Reframe/Gesichtserkennung läuft lokal, ohne Cloud.",
        "content_generator": content_generator,
        "content_fallback_count": content_fallback_count,
        "brand_kit_used": brand_kit_used,
        "brand_kit_name": brand_kit_name,
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

        # content_packages.json: publizierfertige Texte je Clip (Begleitdatei)
        content_packages_doc = _build_content_packages_doc(cj, job.id, now)
        if content_packages_doc is not None:
            zf.writestr(
                "content_packages.json",
                json.dumps(content_packages_doc, ensure_ascii=False, indent=2),
            )
    buf.seek(0)

    filename = f"clipforge_{job.id}_clips.zip"
    return StreamingResponse(
        buf,
        media_type="application/zip",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


def _collect_manual_for_zip(job: Job) -> tuple[list[tuple[str, dict]], list[str]]:
    """Sammelt (mp4_pfad, metadata) je manuellem Export + Warnungen.

    Kaputte Metadateien und fehlende MP4s werden übersprungen und als Warnung
    zurückgegeben (crasht nie).
    """
    d = manual_dir(job.job_dir)
    items: list[tuple[str, dict]] = []
    warnings: list[str] = []
    if not os.path.isdir(d):
        return items, warnings
    for meta_path in sorted(glob.glob(os.path.join(d, "*.json"))):
        base = os.path.basename(meta_path)
        try:
            with open(meta_path, "r", encoding="utf-8") as fh:
                meta = json.load(fh)
        except (OSError, ValueError):
            warnings.append(f"Kaputte Metadatei übersprungen: {base}")
            continue
        out = meta.get("output_file")
        mp4 = os.path.join(d, out) if out else None
        if not mp4 or not os.path.exists(mp4):
            warnings.append(
                f"MP4 fehlt zu {meta.get('export_id') or base} — übersprungen."
            )
            continue
        items.append((mp4, meta))
    return items, warnings


@app.get("/api/jobs/{job_id}/all-exports.zip")
def all_exports_zip(job_id: str):
    """Vollständiges Paket: Auto-Clips + manuelle Exporte + alle JSONs.

    Separater Endpoint — verändert `exports.zip` NICHT. Ordnerstruktur:
        auto_clips/…   manual_exports/…   data/…
    """
    job = _require_job(job_id)
    auto_mp4s = _mp4_paths(job)
    manual_items, warnings = _collect_manual_for_zip(job)

    if not auto_mp4s and not manual_items:
        raise HTTPException(
            status_code=404,
            detail="Keine Exporte vorhanden (weder Auto-Clips noch manuelle Exporte).",
        )

    now = datetime.datetime.now(datetime.timezone.utc).isoformat()
    cj = _read_clips_json(job)
    content_generator = (cj or {}).get("content_generator")
    remove_silence = (cj or {}).get("remove_silence", job.remove_silence)
    reframe_mode = (cj or {}).get("reframe_mode", job.reframe_mode)

    metadata = {
        "job_id": job.id,
        "source_filename": job.filename,
        "export_created_at": now,
        "auto_clip_count": len(auto_mp4s),
        "manual_export_count": len(manual_items),
        "total_mp4_count": len(auto_mp4s) + len(manual_items),
        "remove_silence": remove_silence,
        "reframe_mode": reframe_mode,
        "caption_style_default": (cj or {}).get("caption_style"),
        "content_generator": content_generator,
        "brand_kit_used": bool((cj or {}).get("brand_kit_used")),
        "brand_kit_name": (cj or {}).get("brand_kit_name"),
        "warnings": warnings,
        "disclaimer": (
            "Der Performance-Potential-Score ist eine Wahrscheinlichkeits-"
            "Einschätzung und keine Garantie für Reichweite oder Viralität."
        ),
    }

    manual_exports_doc = {
        "job_id": job.id,
        "export_created_at": now,
        "exports": [meta for _, meta in manual_items],
    }

    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        # 1) Auto-Clips
        for path in auto_mp4s:
            zf.write(path, arcname=f"auto_clips/{os.path.basename(path)}")
        # 2) manuelle Exporte
        for mp4, _meta in manual_items:
            zf.write(mp4, arcname=f"manual_exports/{os.path.basename(mp4)}")
        # 3) Daten
        for optional in ("clips.json", "transcript.json"):
            p = os.path.join(job.job_dir, optional)
            if os.path.exists(p):
                zf.write(p, arcname=f"data/{optional}")
        content_packages_doc = _build_content_packages_doc(cj, job.id, now)
        if content_packages_doc is not None:
            zf.writestr(
                "data/content_packages.json",
                json.dumps(content_packages_doc, ensure_ascii=False, indent=2),
            )
        zf.writestr(
            "data/manual_exports.json",
            json.dumps(manual_exports_doc, ensure_ascii=False, indent=2),
        )
        zf.writestr(
            "data/metadata.json",
            json.dumps(metadata, ensure_ascii=False, indent=2),
        )
    buf.seek(0)

    filename = f"clipforge_{job.id}_all_exports.zip"
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
