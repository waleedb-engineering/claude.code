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

from .captions import make_captions
from .config import Settings
from .ffmpeg_utils import detect_silences, ensure_ffmpeg, probe
from .models import ScoredClip
from .reframe import plan_reframe
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
    video_path: str,
    clip: ScoredClip,
    out_path: str,
    settings: Settings,
    ass_path: str,
    crop_filter: str,
) -> None:
    """Originaler Single-Pass-Render (Captions + Crop werden übergeben)."""
    vf = f"{crop_filter},ass='{_escape_ass_path(ass_path)}'"
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


def _render_with_silence(
    video_path: str,
    clip: ScoredClip,
    out_path: str,
    settings: Settings,
    keeps,
    ass_path: str,
    crop_filter: str,
) -> None:
    """Render mit entfernten Pausen (harte Schnitte). Captions bereits re-gemappt."""
    expr = select_expr(keeps)
    # select/setpts staucht Video, aselect/asetpts staucht Audio identisch
    # -> Bild und Ton bleiben synchron. Einfachanführungszeichen schützen
    # die Kommas im between()-Ausdruck im Filtergraph.
    vf = (
        f"select='{expr}',setpts=N/FRAME_RATE/TB,"
        f"{crop_filter},ass='{_escape_ass_path(ass_path)}'"
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


def _render_with_silence_smoothed(
    video_path: str,
    clip: ScoredClip,
    out_path: str,
    settings: Settings,
    keeps,
    ass_path: str,
    crop_filter: str,
) -> None:
    """Wie _render_with_silence, aber mit kurzen Audio-Fades an den Schnitten.

    Video: select/setpts (identisch). Audio: pro Keep-Segment atrim + 15ms
    Fade-in/-out, dann concat. Gesamtdauer bleibt = Summe der Keep-Längen →
    A/V und Captions bleiben synchron.
    """
    expr = select_expr(keeps)
    v_chain = (
        f"[0:v]select='{expr}',setpts=N/FRAME_RATE/TB,"
        f"{crop_filter},ass='{_escape_ass_path(ass_path)}'[v]"
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
    caption_mode: str = "karaoke",
    caption_style: str = "high_energy",
    reframe_mode: str = "smart",
    brand_overrides: dict | None = None,
    progress: LogFn | None = None,
) -> RenderInfo:
    """Rendert einen einzelnen Clip. Gibt RenderInfo zurück.

    Bei remove_silence=False ist das Verhalten identisch zum Original.
    `audio_smoothing` (nur relevant bei remove_silence) glättet harte
    Audio-Schnitte mit sehr kurzen Fades; bei Fehler wird auf den einfachen
    Silence-Render und zuletzt auf den normalen Render zurückgefallen.
    `caption_mode` (standard|karaoke) und `caption_style` (clean|high_energy)
    steuern die Untertitel; ohne Wort-Timestamps fällt Karaoke auf Standard
    zurück. `reframe_mode` (center|smart|face) steuert den 9:16-Ausschnitt;
    ohne erkanntes Gesicht wird mittig gecroppt. Infos in clip.caption_info /
    clip.reframe_info.
    """
    ensure_ffmpeg()
    os.makedirs(os.path.dirname(os.path.abspath(out_path)), exist_ok=True)
    log = progress or (lambda _m: None)
    out_w, out_h = settings.output_width, settings.output_height
    duration = clip.end - clip.start

    # --- Reframe planen (einmal pro Clip; nie ein harter Fehler) ---
    try:
        media = probe(video_path)
        crop_filter, reframe_info = plan_reframe(
            video_path, clip.start, clip.end,
            media.width, media.height, out_w, out_h, reframe_mode,
        )
    except Exception as exc:  # noqa: BLE001 — Reframe darf Export nie blocken
        from .reframe import center_crop_filter
        crop_filter = center_crop_filter(out_w, out_h)
        reframe_info = {
            "requested_mode": reframe_mode, "applied_mode": "center",
            "fallback": True, "fallback_reason": f"Reframe-Fehler: {type(exc).__name__}",
            "detection_method": None, "frames_analyzed": 0,
            "faces_detected_count": 0, "focus_x": None, "crop_x": None,
            "crop_strategy": "center", "smoothing_applied": False,
        }
    clip.reframe_info = reframe_info
    _rf = reframe_info
    msg = f"  Reframe: {_rf['applied_mode']} (angefragt {_rf['requested_mode']})"
    if _rf.get("crop_strategy") == "static_smart":
        msg += (
            f", Fokus x={_rf['focus_x']}, {_rf['faces_detected_count']} Gesicht(er) "
            f"in {_rf['frames_analyzed']} Frames"
        )
    if _rf["fallback"]:
        msg += f" — Fallback: {_rf['fallback_reason']}"
    log(msg)

    def _caps(words, cs: float, ce: float):
        return make_captions(
            words, cs, ce, mode=caption_mode, style=caption_style,
            width=out_w, height=out_h, overrides=brand_overrides,
        )

    def _log_caps(cap: dict) -> None:
        msg = (
            f"  Captions: Modus {cap['applied_mode']} "
            f"(angefragt {cap['requested_mode']}), Style {cap['caption_style']}, "
            f"{cap['caption_blocks_count']} Blöcke"
        )
        if cap["fallback"]:
            msg += f" — Fallback: {cap['fallback_reason']}"
        log(msg)

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
        # Captions auf der gestauchten (re-gemappten) Zeitachse
        cap_words = remap_words(clip.words, clip.start, keeps)
        ass_text, cap_info = _caps(cap_words, 0.0, info.final_duration)
        _log_caps(cap_info)
        ass_path = _write_ass_tmp(ass_text)
        try:
            # Stufe 1: Silence-Render mit Audio-Glättung
            if audio_smoothing:
                try:
                    _render_with_silence_smoothed(
                        video_path, clip, out_path, settings, keeps, ass_path,
                        crop_filter,
                    )
                    info.applied = True
                    info.audio_smoothing = True
                    log("  Audio-Smoothing: 15 ms Fades an Schnitten angewandt.")
                    clip.output_path = out_path
                    clip.silence_info = info.to_dict()
                    clip.caption_info = cap_info
                    return info
                except Exception as exc:  # noqa: BLE001 — eine Stufe zurück
                    log(
                        f"  ⚠ Audio-Smoothing fehlgeschlagen ({type(exc).__name__}) "
                        f"→ einfacher Silence-Render."
                    )

            # Stufe 2: einfacher Silence-Render (harte Schnitte)
            _render_with_silence(
                video_path, clip, out_path, settings, keeps, ass_path, crop_filter
            )
            info.applied = True
            info.audio_smoothing = False
            clip.output_path = out_path
            clip.silence_info = info.to_dict()
            clip.caption_info = cap_info
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
        finally:
            _safe_unlink(ass_path)

    # Stufe 3 / Normalfall: Plain-Render (Captions auf Original-Zeitachse)
    ass_text, cap_info = _caps(clip.words, clip.start, clip.end)
    _log_caps(cap_info)
    ass_path = _write_ass_tmp(ass_text)
    try:
        _render_plain(video_path, clip, out_path, settings, ass_path, crop_filter)
    finally:
        _safe_unlink(ass_path)
    clip.output_path = out_path
    clip.silence_info = info.to_dict()
    clip.caption_info = cap_info
    return info
