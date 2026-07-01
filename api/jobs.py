"""In-Memory Job-Registry für die ClipForge-API.

Bewusst minimal: ein dict im Prozess + ein ThreadPool für die Hintergrund-
Ausführung + je Job ein Ordner unter jobs/<id>/. KEINE Datenbank, kein Redis,
kein Celery. Die eigentliche Arbeit macht ausschließlich der bestehende
Pipeline-Kern via clipforge.pipeline.run_pipeline — hier wird keine Logik
dupliziert.
"""

from __future__ import annotations

import dataclasses
import datetime
import glob
import json
import os
import shutil
import threading
import uuid
from concurrent.futures import ThreadPoolExecutor
from dataclasses import asdict, dataclass, field

from clipforge.config import get_settings
from clipforge.ffmpeg_utils import FFmpegNotFound, ensure_ffmpeg
from clipforge.pipeline import PipelineCanceled, run_pipeline

# --- Statuswerte (wie spezifiziert) ---
STATUS_QUEUED = "queued"
STATUS_PROCESSING = "processing"
STATUS_COMPLETED = "completed"
STATUS_FAILED = "failed"
# --- Zusätzliche Zustände nach Server-Neustart (Restore) ---
STATUS_INTERRUPTED = "interrupted"   # war beim Neustart aktiv → nicht fortgesetzt
STATUS_INCOMPLETE = "incomplete"     # Ergebnis-Dateien fehlen (unvollständig)
STATUS_CANCELED = "canceled"         # vom Nutzer kooperativ abgebrochen

# Zustände, aus denen ein Abbruch (Cancel) noch sinnvoll ist.
CANCELABLE_STATUSES = (STATUS_QUEUED, STATUS_PROCESSING)


class JobNotFound(Exception):
    """Job existiert weder in der Registry noch auf der Platte (→ 404)."""


class JobBusy(Exception):
    """Job wird gerade verarbeitet — Löschen nur mit force (→ 409)."""


class JobNotCancelable(Exception):
    """Job ist bereits in einem Endzustand — nicht abbrechbar (→ 409)."""


class UnsafeJobPath(Exception):
    """job_id ergibt einen Pfad außerhalb von jobs/ (→ 400)."""


def _now() -> str:
    return datetime.datetime.now(datetime.timezone.utc).isoformat()


def _dir_stats(path: str) -> tuple[int, int]:
    """(Anzahl Dateien, Gesamtgröße in Bytes) eines Verzeichnisbaums."""
    files = 0
    total = 0
    for root, _dirs, names in os.walk(path):
        for name in names:
            fp = os.path.join(root, name)
            try:
                total += os.path.getsize(fp)
                files += 1
            except OSError:
                pass
    return files, total


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
    caption_mode: str = "karaoke"
    caption_style: str = "high_energy"
    reframe_mode: str = "smart"
    progress: list[str] = field(default_factory=list)  # dient auch als Log
    error: str | None = None
    result: dict | None = None
    # --- Restore-Metadaten (nach Server-Neustart) ---
    restored: bool = False
    restored_at: str | None = None
    interrupted: bool = False
    restore_warning: str | None = None
    # --- Cancel-Metadaten (kooperativer Abbruch) ---
    cancel_requested: bool = False
    canceled_at: str | None = None
    cancel_reason: str | None = None

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
            "restored": self.restored,
            "interrupted": self.interrupted,
            "restore_warning": self.restore_warning,
            "cancel_requested": self.cancel_requested,
            "canceled_at": self.canceled_at,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "Job":
        """Baut ein Job-Objekt aus einem (evtl. alten) job.json-dict.

        Unbekannte Keys werden ignoriert, fehlende bekommen Defaults —
        so bleibt das Laden vorwärts-/rückwärtskompatibel.
        """
        field_names = {f.name for f in dataclasses.fields(cls)}
        kwargs = {k: v for k, v in data.items() if k in field_names}
        return cls(**kwargs)


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

    def create(
        self,
        filename: str,
        top_n: int,
        remove_silence: bool = True,
        caption_mode: str = "karaoke",
        caption_style: str = "high_energy",
        reframe_mode: str = "smart",
    ) -> Job:
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
            caption_mode=caption_mode,
            caption_style=caption_style,
            reframe_mode=reframe_mode,
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

    # ---------- Löschen (sicher, nur innerhalb jobs/) ----------

    def safe_job_dir(self, job_id: str) -> str:
        """Validiert job_id und liefert den **garantiert** in jobs/ liegenden Pfad.

        Blockt Path-Traversal (`..`), absolute Pfade, Pfad-Trenner und alles,
        was nach realpath-Auflösung nicht strikt unterhalb von base_dir liegt.
        """
        if (
            not job_id
            or "/" in job_id
            or "\\" in job_id
            or ".." in job_id
            or os.path.isabs(job_id)
            or job_id in (".", "")
        ):
            raise UnsafeJobPath(f"Ungültige job_id: {job_id!r}")
        base = os.path.realpath(self.base_dir)
        target = os.path.realpath(os.path.join(base, job_id))
        # target muss echt unterhalb von base liegen (nicht base selbst).
        if target == base or os.path.commonpath([base, target]) != base:
            raise UnsafeJobPath(f"Pfad außerhalb von jobs/: {job_id!r}")
        return target

    def delete(self, job_id: str, force: bool = False) -> dict:
        """Löscht den kompletten Job-Ordner + entfernt den Job aus der Registry.

        Wirft UnsafeJobPath (→400), JobNotFound (→404), JobBusy (→409).
        Löscht niemals außerhalb von jobs/.
        """
        target = self.safe_job_dir(job_id)  # kann UnsafeJobPath werfen

        with self._lock:
            job = self._jobs.get(job_id)
        exists_on_disk = os.path.isdir(target)
        if job is None and not exists_on_disk:
            raise JobNotFound(f"Job {job_id} nicht gefunden.")

        if job is not None and job.status == STATUS_PROCESSING and not force:
            raise JobBusy(
                "Job wird gerade verarbeitet. Löschen erst nach Abschluss "
                "(oder mit force=true)."
            )

        removed_files, removed_bytes = _dir_stats(target) if exists_on_disk else (0, 0)
        partial_error: str | None = None
        if exists_on_disk:
            try:
                shutil.rmtree(target)
            except OSError as exc:
                # Teilweise gelöscht? Rest zählen, Fehler klar melden.
                still_files, _still_bytes = _dir_stats(target)
                partial_error = (
                    f"Ordner konnte nicht vollständig gelöscht werden "
                    f"({type(exc).__name__}): {exc}. Noch {still_files} Datei(en) übrig."
                )

        with self._lock:
            self._jobs.pop(job_id, None)

        result = {
            "deleted": partial_error is None,
            "job_id": job_id,
            "removed_files_count": removed_files,
            "removed_bytes": removed_bytes,
        }
        if partial_error:
            result["error"] = partial_error
        return result

    # ---------- Kooperativer Abbruch (Cancel) ----------

    def request_cancel(self, job_id: str, reason: str | None = None) -> dict:
        """Setzt das Cancel-Flag eines queued/processing-Jobs.

        Kooperativ: die Verarbeitung stoppt am nächsten sicheren Checkpoint
        (ein bereits laufender FFmpeg-Schritt läuft zu Ende). Wirft JobNotFound
        (→404) und JobNotCancelable (→409) bei Endzuständen.
        """
        with self._lock:
            job = self._jobs.get(job_id)
        if job is None:
            raise JobNotFound(f"Job {job_id} nicht gefunden.")
        if job.status not in CANCELABLE_STATUSES:
            raise JobNotCancelable(
                f"Job im Status '{job.status}' ist nicht abbrechbar."
            )

        with self._lock:
            job.cancel_requested = True
            job.cancel_reason = reason
            job.updated_at = _now()
            # queued (noch nicht vom Worker gestartet) → sofort canceled setzen.
            if job.status == STATUS_QUEUED:
                job.status = STATUS_CANCELED
                job.canceled_at = _now()
            current_status = job.status
        self._append_progress(job, "Abbruch angefordert.")

        immediate = current_status == STATUS_CANCELED
        return {
            "canceled": True,
            "job_id": job_id,
            "status": current_status,
            "message": (
                "Job abgebrochen (war noch nicht in Verarbeitung)."
                if immediate else
                "Abbruch angefordert — Job stoppt am nächsten sicheren "
                "Checkpoint (laufender Render-Schritt läuft zu Ende)."
            ),
        }

    def is_cancel_requested(self, job_id: str) -> bool:
        """Thread-sicherer Cancel-Check für die Pipeline/den Worker."""
        with self._lock:
            job = self._jobs.get(job_id)
            return bool(job and job.cancel_requested)

    # ---------- Wiederherstellung nach Server-Neustart ----------

    def restore(self) -> list[str]:
        """Scannt den jobs/-Ordner und lädt vorhandene Jobs in die Registry.

        Robust: kaputte Job-Ordner werden übersprungen (nie ein Crash), jede
        Auffälligkeit landet als Warnung in der Rückgabeliste. Bereits im
        Speicher vorhandene Jobs (diese Session) werden NICHT überschrieben.
        Es wird niemals ein Job automatisch neu gestartet.
        """
        warnings: list[str] = []
        if not os.path.isdir(self.base_dir):
            return warnings
        for name in sorted(os.listdir(self.base_dir)):
            job_dir = os.path.join(self.base_dir, name)
            if not os.path.isdir(job_dir):
                continue
            with self._lock:
                already = name in self._jobs
            if already:
                continue
            try:
                job, warn = self._restore_one(name, job_dir)
            except Exception as exc:  # noqa: BLE001 — ein kaputter Job darf nie crashen
                warnings.append(
                    f"Job {name}: übersprungen ({type(exc).__name__}: {exc})"
                )
                continue
            if job is None:
                warnings.append(f"Job {name}: übersprungen (kein gültiger Job-Ordner)")
                continue
            with self._lock:
                self._jobs[job.id] = job
            self._persist(job)  # normalisierten Status + Restore-Flags festschreiben
            if warn:
                warnings.append(f"Job {name}: {warn}")
        return warnings

    def _restore_one(self, job_id: str, job_dir: str) -> tuple[Job | None, str | None]:
        """Stellt einen einzelnen Job aus seinem Ordner wieder her."""
        job_json_path = os.path.join(job_dir, "job.json")
        data: dict | None = None
        warn: str | None = None
        if os.path.exists(job_json_path):
            try:
                with open(job_json_path, "r", encoding="utf-8") as fh:
                    data = json.load(fh)
            except (OSError, ValueError):
                data = None
                warn = "job.json defekt — aus vorhandenen Dateien rekonstruiert"

        clips_json = os.path.join(job_dir, "clips.json")
        has_clips_json = os.path.exists(clips_json)
        mp4s = sorted(glob.glob(os.path.join(job_dir, "clip_*.mp4")))
        has_mp4 = len(mp4s) > 0

        if data:
            job = Job.from_dict(data)
            # Pfade/ID immer an den tatsächlichen Ordner binden (portabel).
            job.id = job_id
            job.job_dir = job_dir
        else:
            # Rekonstruktion ohne job.json: minimaler Job aus den Dateien.
            input_path = self._find_input(job_dir)
            created = self._dir_ctime(job_dir)
            job = Job(
                id=job_id,
                status=STATUS_INCOMPLETE,
                filename=os.path.basename(input_path) if input_path else job_id,
                job_dir=job_dir,
                top_n=0,
                created_at=created,
                updated_at=created,
                input_path=input_path,
                transcript_path=None,
            )
            if warn is None:
                warn = "kein job.json — aus vorhandenen Dateien rekonstruiert"

        prior_status = job.status

        # result.clips wird für Preview/Download benötigt — sicherstellen.
        if not (job.result or {}).get("clips"):
            rebuilt = self._reconstruct_result(job_dir, mp4s)
            if rebuilt is not None:
                job.result = rebuilt

        # --- Status normalisieren ---
        if prior_status in (STATUS_QUEUED, STATUS_PROCESSING):
            if has_clips_json and has_mp4:
                # Render war vor dem Absturz bereits fertig geschrieben.
                job.status = STATUS_COMPLETED
                job.interrupted = False
            else:
                job.status = STATUS_INTERRUPTED
                job.interrupted = True
                job.restore_warning = (
                    "Job war beim Neustart aktiv und wurde unterbrochen. "
                    "Es wird nicht automatisch fortgesetzt — bitte neu hochladen."
                )
        elif prior_status == STATUS_FAILED:
            job.status = STATUS_FAILED
        elif prior_status == STATUS_CANCELED:
            job.status = STATUS_CANCELED
        elif prior_status == STATUS_COMPLETED:
            if not (has_clips_json and has_mp4):
                job.status = STATUS_INCOMPLETE
                job.restore_warning = (
                    "Ergebnis unvollständig: clips.json oder gerenderte MP4s "
                    "fehlen auf dem Datenträger."
                )
        else:
            # Rekonstruiert (kein Status): aus Dateien ableiten.
            job.status = STATUS_COMPLETED if (has_clips_json and has_mp4) else STATUS_INCOMPLETE
            if job.status == STATUS_INCOMPLETE and job.restore_warning is None:
                job.restore_warning = "Ergebnis unvollständig (fehlende Dateien)."

        job.restored = True
        job.restored_at = _now()
        if warn and job.restore_warning is None:
            job.restore_warning = warn
        return job, (job.restore_warning or warn)

    @staticmethod
    def _find_input(job_dir: str) -> str | None:
        for path in sorted(glob.glob(os.path.join(job_dir, "input.*"))):
            if os.path.isfile(path):
                return path
        return None

    @staticmethod
    def _dir_ctime(job_dir: str) -> str:
        try:
            ts = os.path.getctime(job_dir)
            return datetime.datetime.fromtimestamp(
                ts, datetime.timezone.utc
            ).isoformat()
        except OSError:
            return _now()

    @staticmethod
    def _reconstruct_result(job_dir: str, mp4s: list[str]) -> dict | None:
        """Baut ein result-dict (mit clips) aus clips.json + MP4s (+ transcript)."""
        clips_path = os.path.join(job_dir, "clips.json")
        if not os.path.exists(clips_path):
            return None
        try:
            with open(clips_path, "r", encoding="utf-8") as fh:
                cj = json.load(fh)
        except (OSError, ValueError):
            return None

        language = None
        duration = None
        tpath = os.path.join(job_dir, "transcript.json")
        if os.path.exists(tpath):
            try:
                with open(tpath, "r", encoding="utf-8") as fh:
                    tj = json.load(fh)
                language = tj.get("language")
                duration = tj.get("duration")
            except (OSError, ValueError):
                pass

        clips = []
        for i, c in enumerate(cj.get("clips") or [], start=1):
            prefix = f"clip_{i:02d}_"
            match = next(
                (m for m in mp4s if os.path.basename(m).startswith(prefix)), None
            )
            clips.append({
                "index": i,
                "score": c.get("score"),
                "start": c.get("start"),
                "end": c.get("end"),
                "duration": c.get("duration"),
                "scorer": c.get("scorer"),
                "output_file": os.path.basename(match) if match else None,
                "downloadable": bool(match),
            })
        return {
            "clip_count": len(clips),
            "rendered_count": sum(1 for c in clips if c["downloadable"]),
            "language": language,
            "duration": duration,
            "clips": clips,
        }

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
        # Abbruch vor Start (Job war queued und wurde inzwischen abgebrochen).
        if job.cancel_requested:
            self._append_progress(job, "Abgebrochen, bevor die Verarbeitung startete.")
            self._update(job, status=STATUS_CANCELED, canceled_at=_now())
            return

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

        def should_cancel() -> bool:
            return self.is_cancel_requested(job.id)

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
                caption_mode=job.caption_mode,
                caption_style=job.caption_style,
                reframe_mode=job.reframe_mode,
                progress=progress,
                should_cancel=should_cancel,
            )
        except PipelineCanceled:
            self._append_progress(job, "Verarbeitung am Checkpoint abgebrochen.")
            self._update(job, status=STATUS_CANCELED, canceled_at=_now())
            return
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
