"""Audio-Helfer: Dauer, Beat-Erkennung, Musikbibliothek (lokale Dateien)."""

from __future__ import annotations

import os
import subprocess

from .errors import StudioError
from .storage import safe_child, safe_filename, studio_dir

AUDIO_EXT = {".mp3", ".wav", ".m4a", ".aac", ".ogg", ".flac"}
_SR = 11025
_HOP = 128


def run_ffmpeg(cmd: list[str], what: str, timeout: int = 1800) -> None:
    """FFmpeg strikt als Argumentliste (nie über eine Shell)."""
    try:
        proc = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
    except subprocess.TimeoutExpired as exc:
        raise StudioError("render_timeout", f"{what}: Zeitlimit überschritten.", 500) from exc
    except OSError as exc:
        raise StudioError("ffmpeg_missing", "FFmpeg wurde nicht gefunden.", 503) from exc
    if proc.returncode != 0:
        raise StudioError(
            "ffmpeg_failed", f"{what} ist fehlgeschlagen.", 500,
            {"stderr_tail": proc.stderr[-600:]})


def media_duration(path: str) -> float:
    try:
        out = subprocess.run(
            ["ffprobe", "-v", "error", "-show_entries", "format=duration",
             "-of", "default=nw=1:nk=1", path],
            capture_output=True, text=True, timeout=60)
        return max(0.0, float(out.stdout.strip() or 0.0))
    except (OSError, ValueError, subprocess.TimeoutExpired):
        return 0.0


def detect_beats(path: str, max_seconds: float = 600.0) -> dict:
    """Schätzt Tempo + Beat-Zeitpunkte (Energie-Onsets + Autokorrelation).

    Rein lokal (ffmpeg → PCM → numpy). Liefert {"bpm", "beats", "confidence"}.
    Bei zu kurzem/gleichförmigem Material: bpm None und leere Beat-Liste.
    """
    import numpy as np

    try:
        proc = subprocess.run(
            ["ffmpeg", "-v", "error", "-i", path, "-t", f"{max_seconds:.1f}", "-vn",
             "-ac", "1", "-ar", str(_SR), "-f", "s16le", "-"],
            capture_output=True, timeout=300)
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise StudioError("beat_detection_failed", "Audio konnte nicht gelesen werden.", 422) from exc
    if proc.returncode != 0 or len(proc.stdout) < _SR * 2 * 2:
        return {"bpm": None, "beats": [], "confidence": 0.0}
    samples = np.frombuffer(proc.stdout, dtype="<i2").astype(np.float32) / 32768.0
    n_frames = len(samples) // _HOP
    frames = samples[: n_frames * _HOP].reshape(n_frames, _HOP)
    energy = np.log1p(50.0 * np.sqrt((frames ** 2).mean(axis=1)))
    onset = np.maximum(0.0, np.diff(energy, prepend=energy[0]))
    if onset.max() <= 1e-6:
        return {"bpm": None, "beats": [], "confidence": 0.0}
    # leicht glätten: Onsets, die zwischen zwei Frames fallen, korrelieren trotzdem
    onset = np.convolve(onset, np.array([0.25, 0.5, 1.0, 0.5, 0.25]), mode="same")
    onset = onset - onset.mean()
    fps = _SR / _HOP
    lag_min, lag_max = int(fps * 60 / 180), int(fps * 60 / 60)
    lag_max = min(lag_max, len(onset) // 2)
    if lag_max <= lag_min:
        return {"bpm": None, "beats": [], "confidence": 0.0}
    ac = np.array([float(np.dot(onset[:-lag], onset[lag:])) for lag in range(lag_min, lag_max + 1)])
    if ac.max() <= 0:
        return {"bpm": None, "beats": [], "confidence": 0.0}
    # Tempo-Prior um 120 BPM gegen Oktavfehler (halbes/doppeltes Tempo)
    lags = np.arange(lag_min, lag_max + 1)
    prior = np.exp(-0.5 * (np.log2((60.0 * fps / lags) / 120.0)) ** 2)
    best = int((ac * prior).argmax())
    # Oktav-Korrektur: trägt die halbe Periode fast genauso gut, ist sie der Beat
    half = (lag_min + best) / 2.0
    if half >= lag_min:
        lo = int(half) - lag_min
        near = ac[max(0, lo - 1): lo + 3]
        if len(near) and near.max() >= 0.7 * ac[best]:
            best = max(0, lo - 1) + int(near.argmax())
    lag = lag_min + best
    # parabolische Verfeinerung des Maximums
    if 0 < best < len(ac) - 1:
        a, b, c = ac[best - 1], ac[best], ac[best + 1]
        denom = a - 2 * b + c
        if abs(denom) > 1e-9:
            lag = lag + 0.5 * (a - c) / denom
    period = lag / fps
    bpm = 60.0 / period
    # Phase: Kamm über das Onset-Signal legen
    pos = np.maximum(onset, 0.0)
    step = lag
    best_phase, best_score = 0, -1.0
    for phase in range(int(round(step))):
        idx = np.arange(phase, len(pos), step).astype(int)
        score = float(pos[idx].sum())
        if score > best_score:
            best_phase, best_score = phase, score
    duration = len(samples) / _SR
    beats, t = [], best_phase / fps
    while t < duration:
        beats.append(round(float(t), 3))
        t += period
    confidence = float(ac[best] / (float(np.dot(onset, onset)) + 1e-9))
    return {"bpm": round(float(bpm), 1), "beats": beats,
            "confidence": round(max(0.0, min(1.0, confidence)), 3)}


def snap_durations(durations: list[float], minimums: list[float], beats: list[float]) -> list[float]:
    """Verschiebt Szenenschnitte auf Beats (nie kürzer als das Szenen-Minimum)."""
    if len(beats) < 2:
        return list(durations)
    period = beats[1] - beats[0]
    # Raster rechnerisch verlängern (Musik wird im Render geloopt)
    beats = list(beats)
    horizon = sum(durations) + sum(minimums) + period * 4
    while beats[-1] < horizon:
        beats.append(round(beats[-1] + period, 3))
    out, t = [], 0.0
    for dur, minimum in zip(durations, minimums):
        target = t + dur
        earliest = t + max(minimum, period * 0.9)
        candidates = [b for b in beats if b >= earliest - 1e-6]
        if candidates:
            cut = min(candidates, key=lambda b: abs(b - target))
        else:  # Musik zu Ende → Raster rechnerisch fortsetzen
            k = max(1, round((target - beats[0]) / period))
            cut = beats[0] + k * period
            while cut < earliest:
                cut += period
        out.append(round(cut - t, 3))
        t = cut
    return out


# ---------------------------------------------------------------- Bibliothek

def music_dir() -> str:
    path = os.environ.get("CLIPFORGE_MUSIC_DIR") or os.path.join(studio_dir(), "music")
    os.makedirs(path, exist_ok=True)
    return path


def list_music() -> list[dict]:
    out = []
    base = music_dir()
    for name in sorted(os.listdir(base)):
        full = os.path.join(base, name)
        if os.path.isfile(full) and os.path.splitext(name)[1].lower() in AUDIO_EXT:
            out.append({"id": name, "name": os.path.splitext(name)[0],
                        "bytes": os.path.getsize(full),
                        "duration": round(media_duration(full), 2)})
    return out


def music_path(track_id: str) -> str:
    name = safe_filename(track_id)
    if name != track_id or os.path.splitext(name)[1].lower() not in AUDIO_EXT:
        raise StudioError("music_not_found", "Musiktitel nicht gefunden.", 404)
    path = safe_child(music_dir(), name)
    if not os.path.isfile(path):
        raise StudioError("music_not_found", "Musiktitel nicht gefunden.", 404)
    return path
