"""eSpeak NG direkt über die Bibliothek aus dem pip-Paket `espeakng-loader`.

Warum: `espeakng-loader` liefert libespeak-ng samt Sprachdaten fertig für
Windows, macOS und Linux. Damit gibt es auf jedem System eine lokale,
kostenlose Stimme, ohne dass ein Programm installiert werden muss.

Zusätzlich liefert eSpeak echte Wort-Zeitpunkte (WORD-Events). Damit sind
Captions für diese Stimme wortgenau statt geschätzt.

eSpeak hat globalen Zustand und ist nicht threadsicher → alle Aufrufe laufen
unter einer Prozess-Sperre.
"""

from __future__ import annotations

import ctypes
import os
import threading
import wave

_lock = threading.Lock()
_state: dict = {}

AUDIO_OUTPUT_SYNCHRONOUS = 2
INITIALIZE_DONT_EXIT = 0x8000
CHARS_UTF8 = 1
POS_CHARACTER = 1
PARAM_RATE = 1
PARAM_VOLUME = 2
PARAM_PITCH = 3
EVENT_LIST_TERMINATED = 0
EVENT_WORD = 1
EVENT_SAMPLERATE = 8


class _EventId(ctypes.Union):
    _fields_ = [("number", ctypes.c_int), ("name", ctypes.c_char_p),
                ("string", ctypes.c_char * 8)]


class _Event(ctypes.Structure):
    _fields_ = [("type", ctypes.c_int), ("unique_identifier", ctypes.c_uint),
                ("text_position", ctypes.c_int), ("length", ctypes.c_int),
                ("audio_position", ctypes.c_int), ("sample", ctypes.c_int),
                ("user_data", ctypes.c_void_p), ("id", _EventId)]


_CALLBACK = ctypes.CFUNCTYPE(ctypes.c_int, ctypes.POINTER(ctypes.c_short), ctypes.c_int,
                             ctypes.POINTER(_Event))


def available() -> bool:
    try:
        import espeakng_loader  # noqa: F401
    except ImportError:
        return False
    try:
        return os.path.isfile(espeakng_loader.get_library_path())
    except Exception:  # noqa: BLE001
        return False


def _init() -> dict:
    if _state.get("lib"):
        return _state
    import espeakng_loader
    lib = ctypes.CDLL(espeakng_loader.get_library_path())
    data = espeakng_loader.get_data_path()
    lib.espeak_Initialize.restype = ctypes.c_int
    lib.espeak_Initialize.argtypes = [ctypes.c_int, ctypes.c_int, ctypes.c_char_p, ctypes.c_int]
    lib.espeak_SetSynthCallback.argtypes = [_CALLBACK]
    lib.espeak_SetVoiceByName.argtypes = [ctypes.c_char_p]
    lib.espeak_SetVoiceByName.restype = ctypes.c_int
    lib.espeak_SetParameter.argtypes = [ctypes.c_int, ctypes.c_int, ctypes.c_int]
    lib.espeak_Synth.argtypes = [ctypes.c_void_p, ctypes.c_size_t, ctypes.c_uint, ctypes.c_int,
                                 ctypes.c_uint, ctypes.c_uint, ctypes.POINTER(ctypes.c_uint),
                                 ctypes.c_void_p]
    lib.espeak_Synth.restype = ctypes.c_int
    # Pfad = Ordner, der "espeak-ng-data" enthält
    rate = lib.espeak_Initialize(AUDIO_OUTPUT_SYNCHRONOUS, 0,
                                 os.path.dirname(data).encode("utf-8"), INITIALIZE_DONT_EXIT)
    if rate <= 0:
        raise RuntimeError("eSpeak NG konnte nicht initialisiert werden")
    samples: list[bytes] = []
    events: list[tuple[int, int, int]] = []

    def _cb(wav, num, evts):
        if num > 0 and wav:
            samples.append(ctypes.string_at(wav, num * 2))
        i = 0
        while evts and evts[i].type != EVENT_LIST_TERMINATED:
            if evts[i].type == EVENT_WORD:
                events.append((evts[i].audio_position, evts[i].text_position, evts[i].length))
            i += 1
        return 0
    callback = _CALLBACK(_cb)  # Referenz halten, sonst gibt Python sie frei
    lib.espeak_SetSynthCallback(callback)
    _state.update(lib=lib, rate=rate, samples=samples, events=events, callback=callback)
    return _state


def synthesize(text: str, voice: str, out_wav: str, speed: float = 1.0,
               pitch: int = 50) -> list[dict]:
    """Schreibt ein Mono-WAV und liefert Wort-Timings [{text,start,end}] in Sekunden."""
    with _lock:
        st = _init()
        lib = st["lib"]
        st["samples"].clear()
        st["events"].clear()
        if lib.espeak_SetVoiceByName(voice.encode("utf-8")) != 0:
            raise RuntimeError(f"eSpeak-Stimme '{voice}' nicht gefunden")
        lib.espeak_SetParameter(PARAM_RATE, int(max(80, min(450, 165 * speed))), 0)
        lib.espeak_SetParameter(PARAM_PITCH, int(max(0, min(99, pitch))), 0)
        lib.espeak_SetParameter(PARAM_VOLUME, 100, 0)
        raw = text.encode("utf-8") + b"\x00"
        buf = ctypes.create_string_buffer(raw)
        err = lib.espeak_Synth(buf, len(raw), 0, POS_CHARACTER, 0, CHARS_UTF8, None, None)
        if err != 0:
            raise RuntimeError(f"eSpeak-Synthese fehlgeschlagen ({err})")
        lib.espeak_Synchronize()
        pcm = b"".join(st["samples"])
        events = list(st["events"])
        rate = st["rate"]
    if not pcm:
        raise RuntimeError("eSpeak lieferte kein Audio")
    with wave.open(out_wav, "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(rate)
        wf.writeframes(pcm)
    total = len(pcm) / 2 / rate
    return _word_timings(text, events, total)


def _word_timings(text: str, events: list[tuple[int, int, int]], total: float) -> list[dict]:
    """Wort-Zeitpunkte für JEDES Wort des Texts.

    eSpeak meldet nicht für jedes Wort ein Event (kurze Funktionswörter werden
    teils zusammengezogen). Darum gilt der Text als Grundlage: Wörter mit
    Event bekommen dessen Zeitpunkt, die übrigen werden zwischen den Nachbarn
    nach Zeichenposition interpoliert.
    """
    import re
    tokens = [(m.start(), m.group()) for m in re.finditer(r"\S+", text)]
    if not tokens or not events:
        return []
    at = {max(0, pos - 1): ms / 1000.0 for ms, pos, _length in events}
    starts: list[float | None] = []
    for offset, tok in tokens:
        hit = next((at[o] for o in range(offset, offset + len(tok)) if o in at), None)
        starts.append(hit)
    if starts[0] is None:
        starts[0] = 0.0
    known = [(tokens[i][0], t) for i, t in enumerate(starts) if t is not None]
    known.append((len(text), total))
    for i, t in enumerate(starts):
        if t is not None:
            continue
        off = tokens[i][0]
        left = max((k for k in known if k[0] <= off), key=lambda k: k[0])
        right = min((k for k in known if k[0] > off), key=lambda k: k[0])
        span = max(1, right[0] - left[0])
        starts[i] = left[1] + (right[1] - left[1]) * (off - left[0]) / span
    for i in range(1, len(starts)):  # monoton halten
        starts[i] = max(starts[i], starts[i - 1])
    out = []
    for i, (_off, tok) in enumerate(tokens):
        end = starts[i + 1] if i + 1 < len(starts) else total
        clean = tok.strip(".,;:!?\"'()…„“")
        out.append({"text": clean or tok, "start": round(starts[i], 3),
                    "end": round(max(starts[i] + 0.05, end), 3)})
    return out
