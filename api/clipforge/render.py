"""Rendert einen ScoredClip zu einem fertigen 9:16-MP4 mit Untertiteln.

Pipeline pro Clip:
  1) Schneide den Zeitbereich [start, end] aus dem Quellvideo.
  2) Reframe auf 9:16 via Center-Crop (MVP). TODO: Speaker/Face-Tracking.
  3) Brenne die ASS-Untertitel ein.

Alles in EINEM ffmpeg-Aufruf (schnell, keine Zwischendateien außer dem
temporären ASS-File).
"""

from __future__ import annotations

import os
import subprocess
import tempfile

from .captions import build_ass
from .config import Settings
from .ffmpeg_utils import ensure_ffmpeg
from .models import ScoredClip


def _crop_filter(out_w: int, out_h: int) -> str:
    """FFmpeg-Filter: skaliere/croppe Quelle mittig auf out_w x out_h (9:16).

    Wir skalieren so, dass die Zielfläche vollständig bedeckt ist
    ('increase'), und schneiden dann mittig zu.
    """
    return (
        f"scale={out_w}:{out_h}:force_original_aspect_ratio=increase,"
        f"crop={out_w}:{out_h}"
    )


def render_clip(
    video_path: str,
    clip: ScoredClip,
    out_path: str,
    settings: Settings,
) -> str:
    """Rendert einen einzelnen Clip. Gibt out_path zurück."""
    ensure_ffmpeg()
    out_w, out_h = settings.output_width, settings.output_height

    ass = build_ass(
        words=clip.words,
        clip_start=clip.start,
        clip_end=clip.end,
        width=out_w,
        height=out_h,
    )

    os.makedirs(os.path.dirname(os.path.abspath(out_path)), exist_ok=True)

    with tempfile.NamedTemporaryFile(
        "w", suffix=".ass", delete=False, encoding="utf-8"
    ) as fh:
        ass_path = fh.name
        fh.write(ass)

    try:
        # ass-Filter braucht einen escapeten Pfad
        ass_escaped = ass_path.replace("\\", "\\\\").replace(":", "\\:")
        vf = f"{_crop_filter(out_w, out_h)},ass='{ass_escaped}'"

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
        proc = subprocess.run(cmd, capture_output=True, text=True)
        if proc.returncode != 0:
            raise RuntimeError(
                f"ffmpeg-Rendering fehlgeschlagen (Clip {clip.start:.1f}-"
                f"{clip.end:.1f}s):\n{proc.stderr[-1500:]}"
            )
    finally:
        try:
            os.unlink(ass_path)
        except OSError:
            pass

    clip.output_path = out_path
    return out_path
