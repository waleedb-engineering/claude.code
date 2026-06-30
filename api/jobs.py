"""In-Memory Job-Registry für die ClipForge-API.

Bewusst minimal: ein dict im Prozess + ein ThreadPool für die Hintergrund-
Ausführung + je Job ein Ordner unter jobs/<id>/. KEINE Datenbank, kein Redis,
kein Celery. Die eigentliche Arbeit macht ausschließlich der bestehende
Pipeline-Kern via clipforge.pipeline.run_pipeline — hier wird keine Logik
dupliziert.
"""

from __future__ import annotations

import datetime
import json
import os
import threading
import uuid
from concurrent.futures import ThreadPoolExecutor
from dataclasses import asdict, dataclass, field

from clipforge.config import get_settings
from clipforge.ffmpeg_utils import FFmpegNotFound, ensure_ffmpeg
from clipforge.pipeline import run_pipeline

# --- Statuswerte (wie spezifiziert) ---
STATUS_QUEUED = "queued"
STATUS_PROCESSING = "processing"
STATUS_COMPLETED = "completed"
STATUS_FAILED = "failed"


def _now() -> str:
    return datetime.datetime.now(datetime.timezone.utc).isoformat()


@dataclass
class Job:
    id: str
    status: str
    filename: str
    job_dir: str
    top_n: int
    created_at: str
    updated_at: str
    input_path: str | None = None
    transcript_path: str | None = None
    remove_silence: bool = True
    progress: list[str] = field(default_factory=list)  # dient auch als Log
    error: str | None = None
    result: dict | None = None

    def to_dict(self) -> dict:
        return asdict(self)

    def summary(self) -> dict:
        return {
            "id": self.id,
            "status": self.status,
            "filename": self.filename,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "clip_count": (self.result or {}).get("clip_count"),
            "error": self.error,
        }


class JobRegistry:
    def __init__(self, base_dir: str, max_workers: int = 2) -> None:
        self.base_dir = os.path.abspath(base_dir)
        os.makedirs(self.base_dir, exist_ok=True)
        self._jobs: dict[str, Job] = {}
        self._lock = threading.Lock()
        self._pool = ThreadPoolExecutor(
            max_workers=max_workers, thread_name_prefix="clipforge-job"
        )

    # ---------- Lese-/Schreibzugriffe (thread-safe) ----------

    def create(self, filename: str, top_n: int, remove_silence: bool = True) -> Job:
        job_id = uuid.uuid4().hex[:12]
        job_dir = os.path.join(self.base_dir, job_id)
        os.makedirs(job_dir, exist_ok=True)
        job = Job(
            id=job_id,
            status=STATUS_QUEUED,
            filename=filename,
            job_dir=job_dir,
            top_n=top_n,
            remove_silence=remove_silence,
            created_at=_now(),
            updated_at=_now(),
        )
        with self._lock:
            self._jobs[job_id] = job
        self._persist(job)
        return job

    def get(self, job_id: str) -> Job | None:
        with self._lock:
            return self._jobs.get(job_id)

    def list(self) -> list[Job]:
        with self._lock:
            return sorted(self._jobs.values(), key=lambda j: j.created_at, reverse=True)

    # ---------- interne Helfer ----------

    def _persist(self, job: Job) -> None:
        """Schreibt job.json in den Job-Ordner (reines Debug-/Inspektions-Dump)."""
        try:
            with open(os.path.join(job.job_dir, "job.json"), "w", encoding="utf-8") as fh:
                json.dump(job.to_dict(), fh, ensure_ascii=False, indent=2)
        except OSError:
            pass

    def _update(self, job: Job, **changes) -> None:
        with self._lock:
            for key, value in changes.items():
                setattr(job, key, value)
            job.updated_at = _now()
        self._persist(job)

    def _append_progress(self, job: Job, message: str) -> None:
        with self._lock:
            job.progress.append(message)
            job.updated_at = _now()
        self._persist(job)

    # ---------- Hintergrund-Ausführung ----------

    def start(self, job: Job) -> None:
        """Stellt den Job in den ThreadPool — kehrt sofort zurück."""
        self._pool.submit(self._run, job)

    def _run(self, job: Job) -> None:
        self._update(job, status=STATUS_PROCESSING)

        # Fehlerfall: FFmpeg fehlt
        try:
            ensure_ffmpeg()
        except FFmpegNotFound as exc:
            self._append_progress(job, f"FEHLER: {exc}")
            self._update(job, status=STATUS_FAILED, error=f"FFmpeg fehlt: {exc}")
            return

        if not job.input_path or not os.path.exists(job.input_path):
            self._update(job, status=STATUS_FAILED, error="Eingabedatei fehlt.")
            return

        def progress(message: str) -> None:
            self._append_progress(job, message)

        # Eigentliche Arbeit: bestehender Pipeline-Kern, KEINE Duplizierung
        try:
            pr = run_pipeline(
                video_path=job.input_path,
                output_dir=job.job_dir,
                settings=get_settings(),
                transcript_path=job.transcript_path,
                top_n=job.top_n,
                render=True,
                remove_silence=job.remove_silence,
                progress=progress,
            )
        except Exception as exc:  # noqa: BLE001 — Pipeline-Fehler sauber melden
            self._append_progress(job, f"FEHLER: {exc}")
            self._update(
                job, status=STATUS_FAILED, error=f"{type(exc).__name__}: {exc}"
            )
            return

        # Ergebnis-Übersicht (aus den bestehenden Kern-Objekten abgeleitet)
        clips = []
        for i, clip in enumerate(pr.clips, start=1):
            out = clip.output_path
            clips.append(
                {
                    "index": i,
                    "score": clip.score,
                    "start": clip.start,
                    "end": clip.end,
                    "duration": clip.duration,
                    "scorer": clip.scorer,
                    "output_file": os.path.basename(out) if out else None,
                    "downloadable": bool(out and os.path.exists(out)),
                }
            )
        result = {
            "clip_count": len(pr.clips),
            "rendered_count": len(pr.rendered),
            "language": pr.transcript.language,
            "duration": pr.transcript.duration,
            "clips": clips,
        }
        # Fehlerbehandlung: leeres Ergebnis (kein Crash, aber klar markiert)
        if len(pr.clips) == 0:
            result["warning"] = (
                "Leeres Ergebnis: keine Clips erzeugt. Mögliche Ursache: Video "
                "zu kurz, keine Sprache erkannt, oder Längen-Grenzen zu eng."
            )

        self._update(job, status=STATUS_COMPLETED, result=result)
