"""Lokale Provider: laufen ohne Netz und ohne Zugangsdaten."""

from __future__ import annotations

import math
import os
import shutil
import struct
import subprocess
import tempfile
import wave

from ..errors import ProviderError
from .base import ImageProvider, VoiceProvider, VoiceResult

WORDS_PER_SECOND = 2.6


def _run(cmd: list[str], provider: str, timeout: int = 120) -> None:
    try:
        proc = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise ProviderError(provider, f"Programmstart fehlgeschlagen ({type(exc).__name__})") from exc
    if proc.returncode != 0:
        raise ProviderError(provider, "Programm meldete einen Fehler")


def speech_seconds(text: str) -> float:
    return max(1.0, len((text or "").split()) / WORDS_PER_SECOND)


class SilentVoice(VoiceProvider):
    """Kein Voice-over: Stille in Lesedauer (Captions bleiben getaktet)."""

    id, label = "none", "Ohne Stimme (nur Captions/Musik)"
    produces_speech = False

    def voices(self, language):
        return [{"id": "silent", "label": "Stille", "tone": "neutral", "language": language}]

    def synthesize(self, text, language, voice_id, out_path, model=None):
        seconds = speech_seconds(text)
        with wave.open(out_path, "wb") as wf:
            wf.setnchannels(1)
            wf.setsampwidth(2)
            wf.setframerate(44100)
            wf.writeframes(b"\x00\x00" * int(44100 * seconds))
        return VoiceResult(path=out_path)


class MockVoice(VoiceProvider):
    """Test-/Demo-Provider: Platzhalter-Ton statt Sprache (KEINE echte Stimme)."""

    id, label = "mock", "Mock-Stimme (Testton, keine Sprache)"
    requires_flag = "studio_mock_providers"
    produces_speech = False

    def voices(self, language):
        return [
            {"id": "mock_low", "label": "Mock tief", "tone": "calm", "language": language},
            {"id": "mock_high", "label": "Mock hoch", "tone": "energetic", "language": language},
        ]

    def synthesize(self, text, language, voice_id, out_path, model=None):
        seconds = speech_seconds(text)
        freq = 330.0 if voice_id == "mock_high" else 220.0
        rate = 44100
        frames = bytearray()
        for n in range(int(rate * seconds)):
            # an-/abschwellender Ton je "Wort" → hörbar getaktet, aber keine Sprache
            env = 0.5 * (1 - math.cos(2 * math.pi * WORDS_PER_SECOND * n / rate))
            frames += struct.pack("<h", int(9000 * env * math.sin(2 * math.pi * freq * n / rate)))
        with wave.open(out_path, "wb") as wf:
            wf.setnchannels(1)
            wf.setsampwidth(2)
            wf.setframerate(rate)
            wf.writeframes(bytes(frames))
        return VoiceResult(path=out_path)


class MacSayVoice(VoiceProvider):
    """macOS `say` — echte lokale Sprachausgabe (Deutsch + Englisch)."""

    id, label = "macos_say", "macOS Systemstimme (lokal)"
    setup_hint = "Nur auf macOS verfügbar (Programm `say`)."
    _VOICES = {
        "de": [("Anna", "neutral"), ("Markus", "calm"), ("Petra", "friendly")],
        "en": [("Samantha", "neutral"), ("Daniel", "calm"), ("Karen", "friendly")],
    }

    def configured(self):
        return shutil.which("say") is not None

    def voices(self, language):
        return [{"id": v, "label": v, "tone": t, "language": language}
                for v, t in self._VOICES.get(language, self._VOICES["en"])]

    def synthesize(self, text, language, voice_id, out_path, model=None):
        allowed = {v for v, _ in self._VOICES.get(language, self._VOICES["en"])}
        voice = voice_id if voice_id in allowed else next(iter(
            v for v, _ in self._VOICES.get(language, self._VOICES["en"])))
        with tempfile.TemporaryDirectory() as tmp:
            txt = os.path.join(tmp, "in.txt")
            aiff = os.path.join(tmp, "out.aiff")
            with open(txt, "w", encoding="utf-8") as fh:
                fh.write(text)
            _run(["say", "-v", voice, "-f", txt, "-o", aiff], self.id)
            _run(["ffmpeg", "-y", "-i", aiff, "-ac", "1", "-ar", "44100", out_path], self.id)
        return VoiceResult(path=out_path)


class EspeakVoice(VoiceProvider):
    """espeak-ng — lokale (robotische) Sprachausgabe, Linux/Windows/macOS."""

    id, label = "espeak", "espeak-ng (lokal)"
    setup_hint = "espeak-ng installieren (z. B. `apt-get install espeak-ng` / `brew install espeak-ng`)."

    def _binary(self):
        return shutil.which("espeak-ng") or shutil.which("espeak")

    def configured(self):
        return self._binary() is not None

    def voices(self, language):
        return [{"id": language, "label": f"espeak {language}", "tone": "neutral",
                 "language": language}]

    def synthesize(self, text, language, voice_id, out_path, model=None):
        lang = language if language in ("de", "en") else "en"
        with tempfile.TemporaryDirectory() as tmp:
            txt = os.path.join(tmp, "in.txt")
            with open(txt, "w", encoding="utf-8") as fh:
                fh.write(text)
            _run([self._binary(), "-v", lang, "-s", "165", "-f", txt, "-w", out_path], self.id)
        return VoiceResult(path=out_path)


class MockImage(ImageProvider):
    """Test-/Demo-Bildprovider: lokales Verlaufsbild, kein KI-Bild."""

    id, label = "mock_image", "Mock-Bild (lokaler Verlauf, kein KI-Bild)"
    requires_flag = "studio_mock_providers"

    def generate(self, prompt, width, height, out_path):
        seed = sum(ord(c) for c in (prompt or "x")) % 1000
        _run(["ffmpeg", "-y", "-f", "lavfi", "-i",
              f"gradients=s={width}x{height}:seed={seed}:d=1", "-frames:v", "1", out_path],
             self.id)
        return 0.0
