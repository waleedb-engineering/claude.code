"""Audio- und Video-Signale je Sekunde (FFmpeg-Pipes, streamend).

Audio (16 kHz mono): Lautheit (dBFS), plötzlicher Anstieg, „laut + hell“
(Schrei-/Jubel-Heuristik über spektralen Schwerpunkt), Stille.
Video (2 Bilder/s, 64×36 Graustufen): Bewegungsenergie, Szenenwechsel.

Alles Heuristiken auf messbaren Größen — keine Emotionserkennung. Die
Begründungen im Scoring benennen genau diese Größen.
"""

from __future__ import annotations

import subprocess

import numpy as np

SR = 16000
VW, VH, VFPS = 64, 36, 2


class SignalError(Exception):
    pass


def _pipe(cmd: list[str]):
    return subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL)


def audio_features(path: str, should_cancel=None) -> dict:
    """→ {loudness_db[], centroid_hz[]} je Sekunde."""
    proc = _pipe(["ffmpeg", "-v", "error", "-i", path, "-vn", "-ac", "1", "-ar", str(SR),
                  "-f", "s16le", "-"])
    loud, cent = [], []
    freqs = np.fft.rfftfreq(SR // 4, 1 / SR)
    try:
        while True:
            if should_cancel and should_cancel():
                raise SignalError("abgebrochen")
            buf = proc.stdout.read(SR * 2)  # 1 Sekunde
            if not buf:
                break
            x = np.frombuffer(buf, dtype=np.int16).astype(np.float32) / 32768.0
            if x.size == 0:
                break
            rms = float(np.sqrt(np.mean(x * x)) + 1e-9)
            loud.append(20 * np.log10(rms))
            # spektraler Schwerpunkt über 4 Fenster à 250 ms (gemittelt)
            cs = []
            for k in range(0, x.size - SR // 4 + 1, SR // 4):
                seg = x[k:k + SR // 4]
                mag = np.abs(np.fft.rfft(seg * np.hanning(seg.size)))
                s = float(mag.sum())
                if s > 1e-6:
                    cs.append(float((mag * freqs).sum() / s))
            cent.append(float(np.mean(cs)) if cs else 0.0)
    finally:
        proc.stdout.close()
        proc.wait(timeout=30)
    if not loud:
        raise SignalError("Keine Audiospur gefunden.")
    return {"loudness_db": loud, "centroid_hz": cent}


def video_features(path: str, should_cancel=None) -> dict:
    """→ {motion[], scene[]} je Sekunde (Mittelwert/Maximum der 2 Bilder)."""
    proc = _pipe(["ffmpeg", "-v", "error", "-i", path, "-an", "-vf",
                  f"fps={VFPS},scale={VW}:{VH},format=gray", "-f", "rawvideo", "-"])
    size = VW * VH
    prev = None
    diffs = []
    try:
        while True:
            if should_cancel and should_cancel():
                raise SignalError("abgebrochen")
            buf = proc.stdout.read(size)
            if len(buf) < size:
                break
            frame = np.frombuffer(buf, dtype=np.uint8).astype(np.float32)
            diffs.append(0.0 if prev is None else float(np.mean(np.abs(frame - prev))))
            prev = frame
    finally:
        proc.stdout.close()
        proc.wait(timeout=30)
    motion, scene = [], []
    for i in range(0, len(diffs), VFPS):
        chunk = diffs[i:i + VFPS]
        motion.append(float(np.mean(chunk)))
        scene.append(float(np.max(chunk)))
    return {"motion": motion, "scene": scene}


# ------------------------------------------------------------ Normierung
def robust_z(series, window: int = 301, floor: float = 1.0) -> np.ndarray:
    """z-Wert gegen den gleitenden Median (±window/2 s) und die MAD.

    `floor` verhindert, dass in sehr ruhigen Abschnitten winzige
    Schwankungen riesige z-Werte erzeugen (Rausch-Untergrenze)."""
    x = np.asarray(series, dtype=np.float32)
    n = x.size
    if n == 0:
        return x
    half = window // 2
    pad = np.pad(x, (half, half), mode="edge")
    if n > 4000:  # lange Streams: Median auf 5-s-Raster, dann interpolieren
        idx = np.arange(0, n, 5)
        med = np.array([np.median(pad[i:i + window]) for i in idx])
        mad = np.array([np.median(np.abs(pad[i:i + window] - m)) for i, m in zip(idx, med)])
        med = np.interp(np.arange(n), idx, med)
        mad = np.interp(np.arange(n), idx, mad)
    else:
        from numpy.lib.stride_tricks import sliding_window_view
        win = sliding_window_view(pad, window)
        med = np.median(win, axis=1)
        mad = np.median(np.abs(win - med[:, None]), axis=1)
    return (x - med) / (1.4826 * mad + floor)


def smooth(series, k: int = 3) -> np.ndarray:
    x = np.asarray(series, dtype=np.float32)
    if k <= 1 or x.size < k:
        return x
    return np.convolve(x, np.ones(k) / k, mode="same")
