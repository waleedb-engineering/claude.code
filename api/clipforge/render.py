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
from .silence import (
    audio_smoothing_filter,
    keep_intervals,
    remap_words,
    removed_seconds,
    select_expr,
)

LogFn = Callable[[str], None]


@dataclass
class RenderInfo:
    """Was beim Rendern eines Clips passiert ist (für Logs/Transparenz)."""

    silence_enabled: bool = False        # remove_silence angefragt?
    n_silences: int = 0                  # erkannte Stille-Stellen
    removed_seconds: float = 0.0         # entfernte Gesamtdauer (s)
    original_duration: float = 0.0       # ursprüngliche Clip-Dauer (s)
    final_duration: float = 0.0          # finale Clip-Dauer (s)
    applied: bool = False                # Silence-Removal tatsächlich angewandt?
    audio_smoothing: bool = False        # kurze Fades an Schnitten angewandt?
    fallback: bool = False               # auf einfacheren Render zurückgefallen?

    def to_dict(self) -> dict:
        return {
            "remove_silence": self.silence_enabled,
            "n_silences": self.n_silences,
            "removed_seconds": round(self.removed_seconds, 2),
            "original_duration": round(self.original_duration, 2),
            "final_duration": round(self.final_duration, 2),
            "applied": self.applied,
            "audio_smoothing": self.audio_smoothing,
            "fallback": self.fallback,
        }


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


def _render_with_silence_smoothed(
    video_path: str,
    clip: ScoredClip,
    out_path: str,
    settings: Settings,
    keeps,
) -> None:
    """Wie _render_with_silence, aber mit kurzen Audio-Fades an den Schnitten.

    Video: select/setpts (identisch). Audio: pro Keep-Segment atrim + 15ms
    Fade-in/-out, dann concat. Gesamtdauer bleibt = Summe der Keep-Längen →
    A/V und Captions bleiben synchron.
    """
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
        v_chain = (
            f"[0:v]select='{expr}',setpts=N/FRAME_RATE/TB,"
            f"{_crop_filter(out_w, out_h)},ass='{_escape_ass_path(ass_path)}'[v]"
        )
        a_chain = audio_smoothing_filter(keeps, fade=0.015)
        filter_complex = f"{v_chain};{a_chain}"
        cmd = [
            "ffmpeg", "-y",
            "-ss", f"{clip.start:.3f}",
            "-to", f"{clip.end:.3f}",
            "-i", video_path,
            "-filter_complex", filter_complex,
            "-map", "[v]", "-map", "[a]",
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
    audio_smoothing: bool = True,
    progress: LogFn | None = None,
) -> RenderInfo:
    """Rendert einen einzelnen Clip. Gibt RenderInfo zurück.

    Bei remove_silence=False ist das Verhalten identisch zum Original.
    `audio_smoothing` (nur relevant bei remove_silence) glättet harte
    Audio-Schnitte mit sehr kurzen Fades; bei Fehler wird auf den einfachen
    Silence-Render und zuletzt auf den normalen Render zurückgefallen.
    """
    ensure_ffmpeg()
    os.makedirs(os.path.dirname(os.path.abspath(out_path)), exist_ok=True)
    log = progress or (lambda _m: None)
    duration = clip.end - clip.start
    info = RenderInfo(
        silence_enabled=remove_silence,
        original_duration=duration,
        final_duration=duration,
    )

    keeps = None
    if remove_silence:
        try:
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
        info.final_duration = sum(b - a for a, b in keeps)

        # Stufe 1: Silence-Render mit Audio-Glättung (kurze Fades an Schnitten)
        if audio_smoothing:
            try:
                _render_with_silence_smoothed(
                    video_path, clip, out_path, settings, keeps
                )
                info.applied = True
                info.audio_smoothing = True
                log("  Audio-Smoothing: 15 ms Fades an Schnitten angewandt.")
                clip.output_path = out_path
                clip.silence_info = info.to_dict()
                return info
            except Exception as exc:  # noqa: BLE001 — eine Stufe zurückfallen
                log(
                    f"  ⚠ Audio-Smoothing fehlgeschlagen ({type(exc).__name__}) "
                    f"→ einfacher Silence-Render."
                )

        # Stufe 2: einfacher Silence-Render (harte Schnitte, ohne Glättung)
        try:
            _render_with_silence(video_path, clip, out_path, settings, keeps)
            info.applied = True
            info.audio_smoothing = False
            clip.output_path = out_path
            clip.silence_info = info.to_dict()
            return info
        except Exception as exc:  # noqa: BLE001 — auf normalen Render zurück
            info.fallback = True
            info.applied = False
            info.audio_smoothing = False
            info.final_duration = info.original_duration
            log(
                f"  ⚠ Silence-Render fehlgeschlagen ({type(exc).__name__}) → "
                f"Fallback auf normalen Render."
            )

    # Stufe 3 / Normalfall: unveränderter Plain-Render
    _render_plain(video_path, clip, out_path, settings)
    clip.output_path = out_path
    clip.silence_info = info.to_dict()
    return info
