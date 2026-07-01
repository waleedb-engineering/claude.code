"""Manuelles Re-Rendering eines einzelnen Clips mit vom Nutzer gesetzten Optionen.

Bewusst dünn: baut aus dem bereits vorhandenen `transcript.json` einen frischen
`ScoredClip` für das neue [start, end]-Fenster und ruft dann die **bestehende**
`render_clip()`-Funktion auf. Es wird KEINE Render-Logik dupliziert.

Manuelle Exporte landen strikt getrennt unter `jobs/<id>/manual_exports/` und
überschreiben nie die automatischen Clips (`clip_*.mp4` im Job-Root).
"""

from __future__ import annotations

import datetime
import glob
import json
import os
from typing import Callable

from .config import Settings, get_settings
from .models import CandidateClip, Transcript
from .render import render_clip
from .scoring import score_heuristic
from .transcribe import load_transcript_json

ProgressFn = Callable[[str], None]

# Sinnvolle Längen-Grenzen für einen manuellen Export (Sekunden).
MIN_MANUAL_SECONDS = 5.0
MAX_MANUAL_SECONDS = 90.0

MANUAL_DIR_NAME = "manual_exports"

_VALID_CAPTION_STYLES = {"clean", "high_energy"}
_VALID_REFRAME_MODES = {"center", "smart", "face"}


class RerenderError(ValueError):
    """Fachlicher Validierungsfehler (→ HTTP 400)."""


def manual_dir(job_dir: str) -> str:
    return os.path.join(job_dir, MANUAL_DIR_NAME)


def _words_in_range(transcript: Transcript, start: float, end: float):
    """Alle Wörter, die den Bereich [start, end] überlappen."""
    return [w for w in transcript.words if w.end > start and w.start < end]


def validate_times(
    start_time: float,
    end_time: float,
    *,
    source_duration: float | None = None,
) -> tuple[float, float]:
    """Validiert Start/Ende und gibt geklammerte Werte zurück (oder wirft)."""
    try:
        start = float(start_time)
        end = float(end_time)
    except (TypeError, ValueError):
        raise RerenderError("start_time und end_time müssen Zahlen sein.")

    if start < 0:
        raise RerenderError("start_time darf nicht negativ sein.")
    if end <= start:
        raise RerenderError("end_time muss größer als start_time sein.")

    duration = end - start
    if duration < MIN_MANUAL_SECONDS:
        raise RerenderError(
            f"Clip zu kurz ({duration:.1f}s). Minimum {MIN_MANUAL_SECONDS:.0f}s."
        )
    if duration > MAX_MANUAL_SECONDS:
        raise RerenderError(
            f"Clip zu lang ({duration:.1f}s). Maximum {MAX_MANUAL_SECONDS:.0f}s."
        )
    if source_duration is not None and end > source_duration + 0.5:
        raise RerenderError(
            f"end_time ({end:.1f}s) liegt hinter dem Videoende "
            f"({source_duration:.1f}s)."
        )
    return start, end


def find_source_video(job_dir: str) -> str | None:
    """Findet die hochgeladene Quelldatei (jobs/<id>/input.*) — server-neustart-fest."""
    matches = sorted(glob.glob(os.path.join(job_dir, "input.*")))
    for path in matches:
        if os.path.isfile(path):
            return path
    return None


def _timestamp() -> str:
    return datetime.datetime.now(datetime.timezone.utc).strftime("%Y%m%dT%H%M%SZ")


def rerender_clip(
    job_dir: str,
    clip_index: int,
    *,
    start_time: float,
    end_time: float,
    title: str | None = None,
    caption_style: str = "high_energy",
    caption_mode: str = "karaoke",
    remove_silence: bool = True,
    reframe_mode: str = "smart",
    export_name: str | None = None,
    settings: Settings | None = None,
    progress: ProgressFn | None = None,
) -> dict:
    """Rendert den Clip <clip_index> mit manuellen Optionen neu.

    Gibt das Metadaten-dict des neuen Exports zurück. Wirft `RerenderError`
    bei Validierungsfehlern (→ 400) und `FileNotFoundError`, wenn Quellvideo
    oder Transkript fehlen (→ 404/409 im API-Layer).
    """
    settings = settings or get_settings()
    log = progress or (lambda _m: None)

    # Optionen normalisieren
    caption_style = caption_style if caption_style in _VALID_CAPTION_STYLES else "high_energy"
    reframe_mode = reframe_mode if reframe_mode in _VALID_REFRAME_MODES else "smart"

    video_path = find_source_video(job_dir)
    if not video_path:
        raise FileNotFoundError("Quellvideo (input.*) im Job-Ordner nicht gefunden.")

    transcript_path = os.path.join(job_dir, "transcript.json")
    if not os.path.exists(transcript_path):
        raise FileNotFoundError("transcript.json im Job-Ordner nicht gefunden.")
    transcript = load_transcript_json(transcript_path)

    start, end = validate_times(
        start_time, end_time, source_duration=transcript.duration or None
    )

    # Frischen ScoredClip für das neue Fenster bauen (echte Heuristik wiederverwenden).
    words = _words_in_range(transcript, start, end)
    text = " ".join(w.text for w in words).strip()
    candidate = CandidateClip(start=start, end=end, text=text, words=words)
    scored = score_heuristic(candidate, settings)
    if title:
        scored.metadata = {}  # Auto-Metadaten hier bewusst leer; Titel kommt aus JSON

    out_dir = manual_dir(job_dir)
    os.makedirs(out_dir, exist_ok=True)

    ts = _timestamp()
    export_id = f"clip_{clip_index}_{ts}"
    out_path = os.path.join(out_dir, f"{export_id}.mp4")

    log(f"Re-Render Clip {clip_index}: {start:.2f}-{end:.2f}s ({end - start:.1f}s)")

    warning: str | None = None
    try:
        render_clip(
            video_path,
            scored,
            out_path,
            settings,
            remove_silence=remove_silence,
            caption_mode=caption_mode,
            caption_style=caption_style,
            reframe_mode=reframe_mode,
            progress=progress,
        )
    except Exception as exc:  # noqa: BLE001 — sauberer Fehler nach oben
        raise RuntimeError(f"Re-Render fehlgeschlagen: {exc}") from exc

    if not os.path.exists(out_path):
        raise RuntimeError("Re-Render lieferte keine Ausgabedatei.")

    silence_info = scored.silence_info or {}
    reframe_info = scored.reframe_info or {}
    if silence_info.get("fallback") or reframe_info.get("fallback"):
        warning = "Teilweise Fallback beim Rendern (siehe silence_info/reframe_info)."

    final_duration = float(
        silence_info.get("final_duration") or round(end - start, 2)
    )

    metadata = {
        "export_id": export_id,
        "source_clip_index": clip_index,
        "created_at": datetime.datetime.now(datetime.timezone.utc).isoformat(),
        "start_time": round(start, 3),
        "end_time": round(end, 3),
        "original_start_time": None,  # vom API-Layer nachgetragen, falls bekannt
        "original_end_time": None,
        "final_duration": round(final_duration, 2),
        "title": title or None,
        "caption_mode": caption_mode,
        "caption_style": caption_style,
        "remove_silence": bool(remove_silence),
        "reframe_mode": reframe_mode,
        "score": scored.score,
        "output_file": os.path.basename(out_path),
        "silence_info": silence_info or None,
        "reframe_info": reframe_info or None,
        "caption_info": scored.caption_info or None,
        "warning": warning,
    }

    meta_path = os.path.join(out_dir, f"{export_id}.json")
    with open(meta_path, "w", encoding="utf-8") as fh:
        json.dump(metadata, fh, ensure_ascii=False, indent=2)

    log(f"Manueller Export gespeichert: {metadata['output_file']}")
    return metadata


def list_manual_exports(job_dir: str) -> list[dict]:
    """Liefert alle manuellen Export-Metadaten eines Jobs (neueste zuerst)."""
    out_dir = manual_dir(job_dir)
    if not os.path.isdir(out_dir):
        return []
    exports: list[dict] = []
    for meta_path in glob.glob(os.path.join(out_dir, "*.json")):
        try:
            with open(meta_path, "r", encoding="utf-8") as fh:
                data = json.load(fh)
        except (OSError, ValueError):
            continue
        mp4 = os.path.join(out_dir, data.get("output_file") or "")
        data["available"] = bool(data.get("output_file") and os.path.exists(mp4))
        exports.append(data)
    exports.sort(key=lambda d: d.get("created_at") or "", reverse=True)
    return exports


def _safe_export_id(export_id: str) -> bool:
    """True, wenn export_id sicher ist (kein Path-Traversal / Pfad-Trenner)."""
    return bool(export_id) and not (
        "/" in export_id
        or "\\" in export_id
        or ".." in export_id
        or os.path.isabs(export_id)
    )


def manual_export_path(job_dir: str, export_id: str) -> str | None:
    """Absoluter MP4-Pfad eines manuellen Exports oder None. Schützt vor Traversal."""
    if not _safe_export_id(export_id):
        return None
    out_dir = manual_dir(job_dir)
    path = os.path.join(out_dir, f"{export_id}.mp4")
    if os.path.exists(path) and os.path.isfile(path):
        return path
    return None


class ManualExportError(Exception):
    """export_id ergibt einen Pfad außerhalb von manual_exports/ (→ 400)."""


def delete_manual_export(job_dir: str, export_id: str) -> dict | None:
    """Löscht MP4 + Sidecar-JSON eines manuellen Exports.

    Sicherheit: `export_id` wird validiert und beide Zielpfade müssen strikt
    innerhalb von `manual_exports/` liegen (realpath-Prüfung). Es wird niemals
    ein Auto-Clip oder eine Datei außerhalb dieses Ordners angefasst.

    Rückgabe:
      - dict {deleted, export_id, removed_files, removed_bytes} bei Erfolg
      - None, wenn kein Bestandteil existiert (→ 404)
    Wirft ManualExportError bei unsicherer export_id (→ 400).
    """
    if not _safe_export_id(export_id):
        raise ManualExportError(f"Ungültige export_id: {export_id!r}")

    out_dir = manual_dir(job_dir)
    base = os.path.realpath(out_dir)
    candidates = [f"{export_id}.mp4", f"{export_id}.json"]

    removed_files: list[str] = []
    removed_bytes = 0
    any_existed = False
    for name in candidates:
        path = os.path.join(out_dir, name)
        # Doppelter Schutz: aufgelöster Pfad muss unter manual_exports/ liegen.
        real = os.path.realpath(path)
        if os.path.dirname(real) != base:
            raise ManualExportError(f"Pfad außerhalb von manual_exports/: {name!r}")
        if os.path.exists(real) and os.path.isfile(real):
            any_existed = True
            try:
                size = os.path.getsize(real)
            except OSError:
                size = 0
            try:
                os.remove(real)
                removed_files.append(name)
                removed_bytes += size
            except OSError:
                pass

    if not any_existed:
        return None

    return {
        "deleted": True,
        "export_id": export_id,
        "removed_files": removed_files,
        "removed_bytes": removed_bytes,
    }
