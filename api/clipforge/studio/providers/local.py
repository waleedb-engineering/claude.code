"""Lokale Provider: laufen ohne Netz und ohne Zugangsdaten."""

from __future__ import annotations

import math
import os
import platform
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


def speech_seconds(text: str, speed: float = 1.0) -> float:
    return max(1.0, len((text or "").split()) / (WORDS_PER_SECOND * max(0.25, speed)))


class SilentVoice(VoiceProvider):
    """Kein Voice-over: Stille in Lesedauer (Captions bleiben getaktet)."""

    id, label = "none", "Ohne Stimme (nur Captions/Musik)"
    produces_speech = False

    def voices(self, language):
        return [{"id": "silent", "label": "Stille", "tone": "neutral", "language": language}]

    def synthesize(self, text, language, voice_id, out_path, model=None, speed=1.0):
        seconds = speech_seconds(text, speed)
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

    def synthesize(self, text, language, voice_id, out_path, model=None, speed=1.0):
        seconds = speech_seconds(text, speed)
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
    live_verified = False  # in der Entwicklungsumgebung (Linux) nicht ausführbar
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

    def synthesize(self, text, language, voice_id, out_path, model=None, speed=1.0):
        allowed = {v for v, _ in self._VOICES.get(language, self._VOICES["en"])}
        voice = voice_id if voice_id in allowed else next(iter(
            v for v, _ in self._VOICES.get(language, self._VOICES["en"])))
        with tempfile.TemporaryDirectory() as tmp:
            txt = os.path.join(tmp, "in.txt")
            aiff = os.path.join(tmp, "out.aiff")
            with open(txt, "w", encoding="utf-8") as fh:
                fh.write(text)
            _run(["say", "-v", voice, "-r", str(int(175 * speed)), "-f", txt, "-o", aiff],
                 self.id)
            _run(["ffmpeg", "-y", "-i", aiff, "-ac", "1", "-ar", "44100", out_path], self.id)
        return VoiceResult(path=out_path)


class EspeakVoice(VoiceProvider):
    """eSpeak NG — lokal und kostenlos auf Windows, macOS und Linux.

    Bevorzugt die Bibliothek aus dem pip-Paket `espeakng-loader` (keine
    Systeminstallation nötig, liefert echte Wort-Zeitpunkte für Captions);
    sonst ein installiertes `espeak-ng`-Programm. Klang: deutlich synthetisch.
    """

    id, label = "espeak", "eSpeak NG (lokal, alle Systeme)"
    setup_hint = "`pip install espeakng-loader` (in requirements.txt enthalten)."
    _VOICES = {
        "de": [("de", "Deutsch männlich", "neutral"), ("de+f3", "Deutsch weiblich", "friendly"),
               ("de+m3", "Deutsch ruhig", "calm")],
        "en": [("en-us", "English (US) male", "neutral"), ("en-us+f3", "English (US) female", "friendly"),
               ("en-gb", "English (UK)", "calm")],
    }

    def _binary(self):
        return shutil.which("espeak-ng") or shutil.which("espeak")

    def configured(self):
        from . import espeak_lib
        return espeak_lib.available() or self._binary() is not None

    def voices(self, language):
        return [{"id": v, "label": label, "tone": tone, "language": language}
                for v, label, tone in self._VOICES.get(language, self._VOICES["en"])]

    def synthesize(self, text, language, voice_id, out_path, model=None, speed=1.0):
        from . import espeak_lib
        options = self._VOICES.get(language, self._VOICES["en"])
        voice = voice_id if voice_id in {v for v, _, _ in options} else options[0][0]
        if espeak_lib.available():
            try:
                words = espeak_lib.synthesize(text, voice, out_path, speed=speed)
            except RuntimeError as exc:
                raise ProviderError(self.id, str(exc)) from None
            return VoiceResult(path=out_path, words=words)
        with tempfile.TemporaryDirectory() as tmp:
            txt = os.path.join(tmp, "in.txt")
            with open(txt, "w", encoding="utf-8") as fh:
                fh.write(text)
            _run([self._binary(), "-v", voice, "-s", str(int(165 * speed)), "-f", txt,
                  "-w", out_path], self.id)
        return VoiceResult(path=out_path)


# PowerShell-Skript für Windows-SAPI. Text und Parameter kommen über
# Umgebungsvariablen, NIE über die Kommandozeile (kein Quoting-/Injection-Risiko).
_SAPI_SCRIPT = (
    "Add-Type -AssemblyName System.Speech;"
    "$s = New-Object System.Speech.Synthesis.SpeechSynthesizer;"
    "if ($env:CF_VOICE) { $s.SelectVoice($env:CF_VOICE) };"
    "$s.Rate = [int]$env:CF_RATE;"
    "$s.SetOutputToWaveFile($env:CF_OUT);"
    "$s.Speak([IO.File]::ReadAllText($env:CF_TEXT, [Text.Encoding]::UTF8));"
    "$s.Dispose()"
)
_SAPI_LIST = (
    "Add-Type -AssemblyName System.Speech;"
    "(New-Object System.Speech.Synthesis.SpeechSynthesizer).GetInstalledVoices() |"
    " Where-Object { $_.Enabled } | ForEach-Object {"
    " $_.VoiceInfo.Name + '|' + $_.VoiceInfo.Culture.Name + '|' + $_.VoiceInfo.Gender }"
)


def _powershell() -> str | None:
    return shutil.which("powershell") or shutil.which("pwsh")


class WindowsSapiVoice(VoiceProvider):
    """Windows-Systemstimmen (SAPI) — lokal, kostenlos, keine Installation.

    Welche Sprachen verfügbar sind, hängt von den in Windows installierten
    Sprachpaketen ab (Einstellungen → Zeit und Sprache → Sprache).
    """

    id, label = "windows_sapi", "Windows-Systemstimme (lokal)"
    live_verified = False  # nur mit nachgebildetem PowerShell-Aufruf getestet
    setup_hint = "Nur unter Windows. Weitere Stimmen über Windows-Sprachpakete."
    _cache: list | None = None

    def configured(self):
        return platform.system() == "Windows" and _powershell() is not None

    def installed(self) -> list[dict]:
        if self._cache is None:
            try:
                proc = subprocess.run([_powershell(), "-NoProfile", "-NonInteractive", "-Command",
                                       _SAPI_LIST], capture_output=True, text=True, timeout=30)
                rows = [line.split("|") for line in proc.stdout.splitlines() if line.count("|") == 2]
            except (OSError, subprocess.TimeoutExpired):
                rows = []
            WindowsSapiVoice._cache = [
                {"id": name, "label": name, "language": culture[:2].lower(),
                 "tone": "friendly" if gender.lower() == "female" else "neutral"}
                for name, culture, gender in rows]
        return self._cache

    def voices(self, language):
        return [v for v in self.installed() if v["language"] == language]

    def synthesize(self, text, language, voice_id, out_path, model=None, speed=1.0):
        options = self.voices(language)
        if not options:
            raise ProviderError(self.id, f"keine Windows-Stimme für '{language}' installiert")
        voice = voice_id if voice_id in {v["id"] for v in options} else options[0]["id"]
        # SAPI-Rate: -10 … 10; 1,0 → 0, 2,0 → +10, 0,5 → -10 (näherungsweise)
        rate = max(-10, min(10, round(math.log2(max(0.25, speed)) * 10)))
        with tempfile.TemporaryDirectory() as tmp:
            txt = os.path.join(tmp, "in.txt")
            with open(txt, "w", encoding="utf-8") as fh:
                fh.write(text)
            env = {**os.environ, "CF_VOICE": voice, "CF_RATE": str(rate),
                   "CF_OUT": os.path.abspath(out_path), "CF_TEXT": txt}
            try:
                proc = subprocess.run([_powershell(), "-NoProfile", "-NonInteractive", "-Command",
                                       _SAPI_SCRIPT], capture_output=True, text=True,
                                      timeout=300, env=env)
            except (OSError, subprocess.TimeoutExpired) as exc:
                raise ProviderError(self.id, f"PowerShell fehlgeschlagen ({type(exc).__name__})") from None
            if proc.returncode != 0 or not os.path.isfile(out_path):
                raise ProviderError(self.id, "Windows-Sprachausgabe fehlgeschlagen")
        return VoiceResult(path=out_path)


def piper_dir() -> str:
    from ..storage import studio_dir
    path = os.environ.get("CLIPFORGE_PIPER_VOICES") or os.path.join(studio_dir(), "piper")
    os.makedirs(path, exist_ok=True)
    return path


class PiperVoice(VoiceProvider):
    """Piper TTS — lokale neuronale Stimmen (gute Qualität), alle Systeme.

    Braucht das pip-Paket `piper-tts` und mindestens ein Stimmmodell
    (`*.onnx` + `*.onnx.json`) im Piper-Ordner. Modelle lädt
    `python -m piper.download_voices de_DE-thorsten-medium --data-dir <Ordner>`.
    """

    id, label = "piper", "Piper (lokal, neuronal)"
    live_verified = False  # ohne echtes Stimmmodell getestet
    setup_hint = ("Stimmmodell laden: `python -m piper.download_voices de_DE-thorsten-medium "
                  "--data-dir api/studio_data/piper` (bzw. en_US-lessac-medium).")
    _loaded: dict = {}

    def _models(self) -> list[dict]:
        try:
            import piper  # noqa: F401
        except ImportError:
            return []
        out = []
        base = piper_dir()
        for name in sorted(os.listdir(base)):
            if not name.endswith(".onnx") or not os.path.isfile(os.path.join(base, name + ".json")):
                continue
            stem = name[:-5]
            out.append({"id": stem, "label": stem, "tone": "neutral",
                        "language": stem.split("_")[0].lower(),
                        "path": os.path.join(base, name)})
        return out

    def configured(self):
        return bool(self._models())

    def voices(self, language):
        return [{k: v for k, v in m.items() if k != "path"}
                for m in self._models() if m["language"] == language]

    def synthesize(self, text, language, voice_id, out_path, model=None, speed=1.0):
        models = [m for m in self._models() if m["language"] == language]
        if not models:
            raise ProviderError(self.id, f"kein Piper-Modell für '{language}'")
        chosen = next((m for m in models if m["id"] == voice_id), models[0])
        try:
            from piper import PiperVoice as _Voice
            from piper import SynthesisConfig
            if chosen["path"] not in self._loaded:
                PiperVoice._loaded[chosen["path"]] = _Voice.load(chosen["path"])
            cfg = SynthesisConfig(length_scale=1.0 / max(0.25, speed))
            with wave.open(out_path, "wb") as wf:
                self._loaded[chosen["path"]].synthesize_wav(text, wf, syn_config=cfg)
        except ProviderError:
            raise
        except Exception as exc:  # noqa: BLE001 — Modellfehler → sauberer Fallback
            raise ProviderError(self.id, f"Piper-Fehler ({type(exc).__name__})") from None
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
