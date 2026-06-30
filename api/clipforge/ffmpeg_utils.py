"""Dünne Wrapper um ffmpeg / ffprobe."""

from __future__ import annotations

import json
import re
import shutil
import subprocess
from dataclasses import dataclass


class FFmpegNotFound(RuntimeError):
    pass


def ensure_ffmpeg() -> None:
    """Stellt sicher, dass ffmpeg und ffprobe verfügbar sind."""
    for tool in ("ffmpeg", "ffprobe"):
        if shutil.which(tool) is None:
            raise FFmpegNotFound(
                f"'{tool}' wurde nicht gefunden. Bitte FFmpeg installieren "
                f"(z.B. 'apt-get install ffmpeg')."
            )


@dataclass
class MediaInfo:
    duration: float
    width: int
    height: int
    has_audio: bool


def probe(path: str) -> MediaInfo:
    """Liest Mediendaten via ffprobe."""
    ensure_ffmpeg()
    cmd = [
        "ffprobe", "-v", "error",
        "-print_format", "json",
        "-show_format", "-show_streams",
        path,
    ]
    out = subprocess.run(cmd, capture_output=True, text=True, check=True)
    data = json.loads(out.stdout)

    duration = float(data.get("format", {}).get("duration", 0.0) or 0.0)
    width = height = 0
    has_audio = False
    for stream in data.get("streams", []):
        if stream.get("codec_type") == "video" and not width:
            width = int(stream.get("width", 0) or 0)
            height = int(stream.get("height", 0) or 0)
        if stream.get("codec_type") == "audio":
            has_audio = True
    return MediaInfo(duration=duration, width=width, height=height, has_audio=has_audio)


def extract_audio(video_path: str, out_wav_path: str, sample_rate: int = 16000) -> str:
    """Extrahiert Mono-WAV (16 kHz) — ideal für Whisper."""
    ensure_ffmpeg()
    cmd = [
        "ffmpeg", "-y", "-i", video_path,
        "-vn", "-ac", "1", "-ar", str(sample_rate),
        "-f", "wav", out_wav_path,
    ]
    subprocess.run(cmd, capture_output=True, text=True, check=True)
    return out_wav_path


def detect_silences(
    path: str, noise_db: float = -30.0, min_seconds: float = 0.6
) -> list[tuple[float, float]]:
    """Erkennt Stille-Intervalle via ffmpeg silencedetect.

    Rückgabe: Liste von (start, end) der Stille-Bereiche (absolute Sekunden).
    Wird für "schnelle Schnitte" (Entfernen von Pausen) genutzt.
    """
    ensure_ffmpeg()
    cmd = [
        "ffmpeg", "-i", path,
        "-af", f"silencedetect=noise={noise_db}dB:d={min_seconds}",
        "-f", "null", "-",
    ]
    proc = subprocess.run(cmd, capture_output=True, text=True)
    # silencedetect schreibt nach stderr
    text = proc.stderr
    silences: list[tuple[float, float]] = []
    start: float | None = None
    for m in re.finditer(r"silence_(start|end):\s*(-?[0-9.]+)", text):
        kind, val = m.group(1), float(m.group(2))
        if kind == "start":
            start = val
        elif kind == "end" and start is not None:
            silences.append((start, val))
            start = None
    return silences
