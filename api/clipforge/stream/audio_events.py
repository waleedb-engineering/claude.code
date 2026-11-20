"""Lokale Audio-Ereignis-Klassifikation (akustische Heuristik, kein trainiertes Modell).

Klassen je Sekunde: silence, speech, music, laughter, cheering, applause, screaming.
Grundlage sind messbare Merkmale aus derselben FFmpeg-Pipe wie die Lautheit
(keine zweite Dekodierung):

- rms_db           Lautheit
- flatness         spektrale Flachheit (0 tonal … 1 rauschartig)
- envmod           Anteil der Hüllkurven-Modulation bei 2–8 Hz (Silbenrhythmus)
- harm             Periodizität (normierte Autokorrelation im Tonhöhenbereich)
- pitch            geschätzte Grundfrequenz (Hz)
- onsets           Hüllkurven-Sprünge > 6 dB je Sekunde (Klatschen)
- steady           Gleichmäßigkeit der Hüllkurve (Musik/Dauerton)

Die Werte sind **heuristische Wahrscheinlichkeiten**: auf synthetischen
Signalen geprüft, nicht gegen einen annotierten Audio-Datensatz kalibriert.
Sie fließen nur gedämpft in das Highlight-Scoring ein und lassen sich
abschalten (``CLIPFORGE_AUDIO_EVENTS=0`` bzw. Analyse-Parameter).

Ein trainiertes Modell (YAMNet/PANNs als ONNX) war in der Entwicklungsumgebung
nicht ladbar (Modell-Hosts gesperrt) — siehe docs/STREAM_INTELLIGENCE.md.
"""

from __future__ import annotations

import os

import numpy as np

CLASSES = ("silence", "speech", "music", "laughter", "cheering", "applause", "screaming")
EVENT_CLASSES = ("laughter", "cheering", "applause", "screaming")
LABEL = {"silence": "Stille", "speech": "Sprache", "music": "Musik", "laughter": "Lachen",
         "cheering": "Jubel", "applause": "Applaus", "screaming": "Schreien"}
SUB = 400  # 25-ms-Teilfenster bei 16 kHz


def enabled() -> bool:
    return os.environ.get("CLIPFORGE_AUDIO_EVENTS", "1") not in ("0", "false", "no")


def second_features(x: np.ndarray, sr: int) -> dict:
    """Merkmale einer Sekunde Mono-Audio (float32, −1…1)."""
    n = x.size // SUB
    if n < 8:
        return {"flatness": 0.0, "envmod": 0.0, "harm": 0.0, "pitch": 0.0, "onsets": 0.0, "steady": 0.0,
                "regular": 0.0}
    frames = x[: n * SUB].reshape(n, SUB)
    env = np.sqrt(np.mean(frames * frames, axis=1)) + 1e-6
    env_db = 20 * np.log10(env)
    # spektrale Flachheit (Mittel über 4 Fenster)
    flats = []
    for k in range(0, x.size - sr // 4 + 1, sr // 4):
        p = np.abs(np.fft.rfft(x[k:k + sr // 4] * np.hanning(sr // 4))) ** 2 + 1e-12
        p = p[5:]  # Gleichanteil/Brummen ignorieren
        flats.append(float(np.exp(np.mean(np.log(p))) / np.mean(p)))
    flatness = float(np.mean(flats)) if flats else 0.0
    # Hüllkurven-Modulation 2–8 Hz (Fensterrate 40 Hz)
    e = env - env.mean()
    spec = np.abs(np.fft.rfft(e * np.hanning(e.size))) ** 2
    fr = np.fft.rfftfreq(e.size, SUB / sr)
    total = float(spec[1:].sum()) + 1e-12
    band = (fr >= 2) & (fr <= 8)
    envmod = float(spec[band].sum() / total)
    # Regelmäßigkeit: Anteil der stärksten Modulationsfrequenz (±1 Bin) im 2–8-Hz-Band
    # („ha-ha-ha“ ist periodisch, Sprache unregelmäßig)
    bspec = spec[band]
    if bspec.size >= 3 and bspec.sum() > 0:
        i = int(np.argmax(bspec))
        regular = float(bspec[max(0, i - 1):i + 2].sum() / bspec.sum())
    else:
        regular = 0.0
    rel_var = float(np.std(env) / (np.mean(env) + 1e-9))
    steady = float(1.0 / (1.0 + 4 * rel_var))
    onsets = float(np.sum(np.diff(env_db) > 6.0))
    # Periodizität und Tonhöhe über das lauteste 64-ms-Fenster
    w = 1024
    centre = int(np.argmax(env)) * SUB
    a = max(0, min(x.size - w, centre - w // 2))
    seg = x[a:a + w] - np.mean(x[a:a + w])
    ac = np.correlate(seg, seg, mode="full")[w - 1:]
    harm, pitch = 0.0, 0.0
    if ac[0] > 1e-9:
        ac = ac / ac[0]
        lo, hi = sr // 1000, sr // 80  # 80–1000 Hz
        lag = lo + int(np.argmax(ac[lo:hi]))
        harm, pitch = float(max(0.0, ac[lag])), float(sr / lag)
    return {"flatness": round(flatness, 4), "envmod": round(envmod, 4), "harm": round(harm, 4),
            "pitch": round(pitch, 1), "onsets": onsets, "steady": round(steady, 4), "regular": round(regular, 4)}


def _sig(x):
    return 1.0 / (1.0 + np.exp(-x))


def classify(audio: dict) -> dict:
    """Merkmalsreihen (aus signals.audio_features) → {klasse: [p je Sekunde]}."""
    loud = np.asarray(audio["loudness_db"], dtype=np.float32)
    if "flatness" not in audio:
        return {}
    keys = ("flatness", "envmod", "harm", "pitch", "onsets", "steady", "regular")
    f = {k: np.asarray(audio.get(k) or [0.0] * loud.size, dtype=np.float32) for k in keys}
    cent = np.asarray(audio["centroid_hz"], dtype=np.float32)
    active = loud[loud > -50]
    base = float(np.median(active)) if active.size else -30.0
    rel = loud - base  # Lautheit relativ zur typischen Lautheit dieser Aufnahme
    voiced_pitch = _sig((f["pitch"] - 85) / 15) * _sig((420 - f["pitch"]) / 40)
    high_pitch = _sig((f["pitch"] - 380) / 40)
    out = {
        "silence": _sig((-48 - loud) / 3),
        "speech": _sig((f["envmod"] - 0.25) / 0.08) * _sig((f["harm"] - 0.3) / 0.08) * voiced_pitch
                  * _sig((0.35 - f["flatness"]) / 0.08) * _sig((rel + 8) / 3) * _sig((0.75 - f["regular"]) / 0.08),
        "music": _sig((f["steady"] - 0.6) / 0.08) * _sig((f["harm"] - 0.3) / 0.08) * _sig((0.3 - f["envmod"]) / 0.08)
                 * _sig((0.3 - f["flatness"]) / 0.08) * _sig((loud + 45) / 3),
        "laughter": _sig((f["envmod"] - 0.35) / 0.08) * _sig((f["regular"] - 0.7) / 0.06)
                    * _sig((f["harm"] - 0.3) / 0.08) * _sig((rel - 1.0) / 2.0) * _sig((f["pitch"] - 150) / 30),
        "cheering": _sig((f["flatness"] - 0.18) / 0.05) * _sig((cent - 1200) / 300) * _sig((rel - 4.0) / 2.0)
                    * _sig((f["steady"] - 0.45) / 0.1) * _sig((5 - f["onsets"]) / 1.5),
        "applause": _sig((f["flatness"] - 0.25) / 0.06) * _sig((f["onsets"] - 3.5) / 1.0) * _sig((rel - 1.0) / 2.0),
        "screaming": _sig((rel - 6.0) / 2.0) * high_pitch * _sig((f["harm"] - 0.45) / 0.1)
                     * _sig((cent - 900) / 200) * _sig((0.3 - f["flatness"]) / 0.08),
    }
    # gegenseitiger Ausschluss: ein sehr lauter hoher Dauerton ist eher Schrei als Hintergrundmusik
    out["music"] = out["music"] * (1 - 0.85 * out["screaming"])
    return {k: [round(float(v), 3) for v in np.clip(arr, 0, 1)] for k, arr in out.items()}


def summary(events: dict, start: int, end: int) -> dict:
    """Höchste Wahrscheinlichkeit je Ereignisklasse in [start, end) (für Begründungen)."""
    out = {}
    for k in EVENT_CLASSES + ("music", "speech"):
        series = events.get(k) or []
        seg = series[max(0, start):max(start + 1, end)]
        if seg:
            out[k] = round(max(seg), 2)
    return out
