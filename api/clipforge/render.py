"""Rendert einen ScoredClip zu einem fertigen 9:16-MP4 mit Untertiteln.

Pipeline pro Clip:
  1) Schneide den Zeitbereich [start, end] aus dem Quellvideo.
  2) Optional: entferne stille Pausen ("schnelle Schnitte").
  3) Reframe auf 9:16 via Center-Crop (MVP). TODO: Speaker/Face-Tracking.
  4) Brenne die ASS-Untertitel ein.

Alles in EINEM ffmpeg-Aufruf (schnell, keine Zwischendateien außer dem
temporären ASS-File).
"""

from __future__ import annotations

import os
import subprocess
import tempfile
from dataclasses import dataclass
from typing import Callable

from .captions import build_ass
from .config import Settings
from .ffmpeg_utils import detect_silences, ensure_ffmpeg
from .models import ScoredClip
from .silence import keep_intervals, remap_words, removed_seconds, select_expr

LogFn = Callable[[str], None]


@dataclass
class RenderInfo:
    """Was beim Rendern eines Clips passiert ist (für Logs/Transparenz)."""

    silence_enabled: bool = False
    n_silences: int = 0
    removed_seconds: float = 0.0
    applied: bool = False      # Silence-Removal tatsächlich angewandt?
    fallback: bool = False     # auf normalen Render zurückgefallen?


def _crop_filter(out_w: int, out_h: int) -> str:
    """FFmpeg-Filter: skaliere/croppe Quelle mittig auf out_w x out_h (9:16)."""
    return (
        f"scale={out_w}:{out_h}:force_original_aspect_ratio=increase,"
        f"crop={out_w}:{out_h}"
    )


def _escape_ass_path(ass_path: str) -> str:
    return ass_path.replace("\\", "\\\\").replace(":", "\\:")


def _write_ass_tmp(ass: str) -> str:
    with tempfile.NamedTemporaryFile(
        "w", suffix=".ass", delete=False, encoding="utf-8"
    ) as fh:
        fh.write(ass)
        return fh.name


def _run_ffmpeg(cmd: list[str], clip: ScoredClip) -> None:
    proc = subprocess.run(cmd, capture_output=True, text=True)
    if proc.returncode != 0:
        raise RuntimeError(
            f"ffmpeg-Rendering fehlgeschlagen (Clip {clip.start:.1f}-"
            f"{clip.end:.1f}s):\n{proc.stderr[-1500:]}"
        )


def _render_plain(
    video_path: str, clip: ScoredClip, out_path: str, settings: Settings
) -> None:
    """Originaler Single-Pass-Render (unverändertes Verhalten)."""
    out_w, out_h = settings.output_width, settings.output_height
    ass = build_ass(
        words=clip.words,
        clip_start=clip.start,
        clip_end=clip.end,
        width=out_w,
        height=out_h,
    )
    ass_path = _write_ass_tmp(ass)
    try:
        vf = f"{_crop_filter(out_w, out_h)},ass='{_escape_ass_path(ass_path)}'"
        cmd = [
            "ffmpeg", "-y",
            "-ss", f"{clip.start:.3f}",
            "-to", f"{clip.end:.3f}",
            "-i", video_path,
            "-vf", vf,
            "-c:v", "libx264", "-preset", "veryfast", "-crf", "20",
            "-c:a", "aac", "-b:a", "128k",
            "-movflags", "+faststart",
            out_path,
        ]
        _run_ffmpeg(cmd, clip)
    finally:
        _safe_unlink(ass_path)


def _render_with_silence(
    video_path: str,
    clip: ScoredClip,
    out_path: str,
    settings: Settings,
    keeps,
) -> None:
    """Render mit entfernten Pausen. Captions sind bereits re-gemappt."""
    out_w, out_h = settings.output_width, settings.output_height
    new_duration = sum(b - a for a, b in keeps)
    new_words = remap_words(clip.words, clip.start, keeps)
    ass = build_ass(
        words=new_words,
        clip_start=0.0,
        clip_end=new_duration,
        width=out_w,
        height=out_h,
    )
    ass_path = _write_ass_tmp(ass)
    try:
        expr = select_expr(keeps)
        # select/setpts staucht Video, aselect/asetpts staucht Audio identisch
        # -> Bild und Ton bleiben synchron. Einfachanführungszeichen schützen
        # die Kommas im between()-Ausdruck im Filtergraph.
        vf = (
            f"select='{expr}',setpts=N/FRAME_RATE/TB,"
            f"{_crop_filter(out_w, out_h)},ass='{_escape_ass_path(ass_path)}'"
        )
        af = f"aselect='{expr}',asetpts=N/SR/TB"
        cmd = [
            "ffmpeg", "-y",
            "-ss", f"{clip.start:.3f}",
            "-to", f"{clip.end:.3f}",
            "-i", video_path,
            "-vf", vf,
            "-af", af,
            "-c:v", "libx264", "-preset", "veryfast", "-crf", "20",
            "-c:a", "aac", "-b:a", "128k",
            "-movflags", "+faststart",
            out_path,
        ]
        _run_ffmpeg(cmd, clip)
    finally:
        _safe_unlink(ass_path)


def _safe_unlink(path: str) -> None:
    try:
        os.unlink(path)
    except OSError:
        pass


def render_clip(
    video_path: str,
    clip: ScoredClip,
    out_path: str,
    settings: Settings,
    *,
    remove_silence: bool = False,
    progress: LogFn | None = None,
) -> RenderInfo:
    """Rendert einen einzelnen Clip. Gibt RenderInfo zurück.

    Bei remove_silence=False ist das Verhalten identisch zum Original.
    """
    ensure_ffmpeg()
    os.makedirs(os.path.dirname(os.path.abspath(out_path)), exist_ok=True)
    log = progress or (lambda _m: None)
    info = RenderInfo(silence_enabled=remove_silence)

    keeps = None
    if remove_silence:
        try:
            duration = clip.end - clip.start
            silences = detect_silences(
                video_path,
                noise_db=settings.silence_db,
                min_seconds=settings.silence_min_seconds,
                start=clip.start,
                end=clip.end,
            )
            candidate = keep_intervals(silences, duration, pad=0.10)
            removed = removed_seconds(candidate, duration)
            kept = sum(b - a for a, b in candidate)
            info.n_silences = len(silences)
            info.removed_seconds = round(removed, 2)

            if removed < 0.30 or kept < 1.0:
                log(
                    f"  Silence-Removal: {len(silences)} Stelle(n), nur "
                    f"{removed:.2f}s entfernbar → kein Schnitt (zu wenig)."
                )
            else:
                keeps = candidate
                log(
                    f"  Silence-Removal: {len(silences)} Stelle(n), entferne "
                    f"{removed:.1f}s ({duration:.1f}s → {kept:.1f}s)."
                )
        except Exception as exc:  # noqa: BLE001 — nie die Pipeline killen
            keeps = None
            info.fallback = True
            log(
                f"  ⚠ Silence-Removal-Analyse fehlgeschlagen "
                f"({type(exc).__name__}) → normaler Render."
            )

    if keeps is not None:
        try:
            _render_with_silence(video_path, clip, out_path, settings, keeps)
            info.applied = True
            clip.output_path = out_path
            return info
        except Exception as exc:  # noqa: BLE001 — Fallback auf normalen Render
            info.fallback = True
            info.applied = False
            log(
                f"  ⚠ Silence-Render fehlgeschlagen ({type(exc).__name__}) → "
                f"Fallback auf normalen Render."
            )

    _render_plain(video_path, clip, out_path, settings)
    clip.output_path = out_path
    return info
