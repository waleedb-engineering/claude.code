"""Externe Provider (optional, kostenpflichtig). Adapter gegen die offiziellen
REST-APIs; automatisierte Tests injizieren `HTTP_POST` — ein echter Call
passiert nur mit gesetztem API-Key UND Budget. Fehlertexte enthalten nie Keys.
"""

from __future__ import annotations

import base64
import json
import os
import urllib.error
import urllib.request

from ..errors import ProviderError
from .base import ImageProvider, VoiceProvider, VoiceResult


def _http_post(url: str, headers: dict, payload: dict, timeout: float = 120.0) -> bytes:
    req = urllib.request.Request(
        url, data=json.dumps(payload).encode("utf-8"), method="POST",
        headers={"Content-Type": "application/json", **headers})
    with urllib.request.urlopen(req, timeout=timeout) as resp:  # noqa: S310 — feste HTTPS-Hosts
        return resp.read(64 * 1024 * 1024)


# In Tests ersetzbar (Monkeypatch) — nie ein echter Netz-Call in der Suite.
HTTP_POST = _http_post


def _post(provider: str, url: str, headers: dict, payload: dict) -> bytes:
    try:
        return HTTP_POST(url, headers, payload)
    except urllib.error.HTTPError as exc:
        raise ProviderError(provider, f"HTTP {exc.code}") from None
    except Exception as exc:  # noqa: BLE001
        raise ProviderError(provider, f"Anfrage fehlgeschlagen ({type(exc).__name__})") from None


class ElevenLabsVoice(VoiceProvider):
    id, label = "elevenlabs", "ElevenLabs (Cloud)"
    local, paid = False, True
    env_keys = ("ELEVENLABS_API_KEY",)
    requires_flag = "studio_external_providers"
    languages = ("de", "en", "es", "fr", "it", "pt", "pl", "nl", "tr")
    setup_hint = "ELEVENLABS_API_KEY in .env setzen (elevenlabs.io → Profile → API Keys)."
    _VOICES = [  # öffentliche Standard-Voice-IDs (multilingual nutzbar)
        ("21m00Tcm4TlvDq8ikWAM", "Rachel", "neutral"),
        ("pNInz6obpgDQGcFmaJgB", "Adam", "calm"),
        ("EXAVITQu4vr4xnSDxMaL", "Bella", "friendly"),
        ("ErXwobaYiN019PkySvjV", "Antoni", "energetic"),
    ]

    def voices(self, language):
        return [{"id": v, "label": n, "tone": t, "language": language}
                for v, n, t in self._VOICES]

    def estimate_cost(self, chars):
        from ..costs import price
        return chars / 1000.0 * price("elevenlabs_per_1k_chars")

    def synthesize(self, text, language, voice_id, out_path):
        ids = {v for v, _, _ in self._VOICES}
        voice = voice_id if voice_id in ids else self._VOICES[0][0]
        body = _post(self.id, f"https://api.elevenlabs.io/v1/text-to-speech/{voice}",
                     {"xi-api-key": os.environ.get("ELEVENLABS_API_KEY", ""),
                      "Accept": "audio/mpeg"},
                     {"text": text, "model_id": os.environ.get(
                         "CLIPFORGE_ELEVENLABS_MODEL", "eleven_multilingual_v2")})
        if len(body) < 64:
            raise ProviderError(self.id, "leere Audio-Antwort")
        with open(out_path, "wb") as fh:
            fh.write(body)
        return VoiceResult(path=out_path, cost_usd=self.estimate_cost(len(text)))


class OpenAIVoice(VoiceProvider):
    id, label = "openai_tts", "OpenAI TTS (Cloud)"
    local, paid = False, True
    env_keys = ("OPENAI_API_KEY",)
    requires_flag = "studio_external_providers"
    languages = ("de", "en", "es", "fr", "it", "pt", "nl", "pl", "tr", "ja")
    setup_hint = "OPENAI_API_KEY in .env setzen (platform.openai.com → API keys)."
    _VOICES = [("alloy", "neutral"), ("onyx", "calm"), ("nova", "friendly"),
               ("echo", "energetic")]

    def voices(self, language):
        return [{"id": v, "label": v, "tone": t, "language": language} for v, t in self._VOICES]

    def estimate_cost(self, chars):
        from ..costs import price
        return chars / 1000.0 * price("openai_tts_per_1k_chars")

    def synthesize(self, text, language, voice_id, out_path):
        voice = voice_id if voice_id in {v for v, _ in self._VOICES} else "alloy"
        body = _post(self.id, "https://api.openai.com/v1/audio/speech",
                     {"Authorization": "Bearer " + os.environ.get("OPENAI_API_KEY", "")},
                     {"model": os.environ.get("CLIPFORGE_OPENAI_TTS_MODEL", "tts-1"),
                      "voice": voice, "input": text, "response_format": "mp3"})
        if len(body) < 64:
            raise ProviderError(self.id, "leere Audio-Antwort")
        with open(out_path, "wb") as fh:
            fh.write(body)
        return VoiceResult(path=out_path, cost_usd=self.estimate_cost(len(text)))


class OpenAIImage(ImageProvider):
    id, label = "openai_image", "OpenAI Bilder (Cloud)"
    local, paid = False, True
    env_keys = ("OPENAI_API_KEY",)
    requires_flag = "studio_external_providers"
    setup_hint = "OPENAI_API_KEY in .env setzen (platform.openai.com → API keys)."

    def estimate_cost(self, images):
        from ..costs import price
        return images * price("openai_image_per_image")

    def generate(self, prompt, width, height, out_path):
        if width == height:
            size = "1024x1024"
        else:
            size = "1024x1536" if height > width else "1536x1024"
        body = _post(self.id, "https://api.openai.com/v1/images/generations",
                     {"Authorization": "Bearer " + os.environ.get("OPENAI_API_KEY", "")},
                     {"model": os.environ.get("CLIPFORGE_OPENAI_IMAGE_MODEL", "gpt-image-1"),
                      "prompt": prompt[:3000], "size": size, "n": 1})
        try:
            b64 = json.loads(body)["data"][0]["b64_json"]
            raw = base64.b64decode(b64)
        except Exception:  # noqa: BLE001 — Antwort ist nicht vertrauenswürdig
            raise ProviderError(self.id, "unerwartetes Antwortformat") from None
        if raw[:8] != b"\x89PNG\r\n\x1a\n" and raw[:3] != b"\xff\xd8\xff" and raw[:4] != b"RIFF":
            raise ProviderError(self.id, "Antwort ist kein Bild")
        with open(out_path, "wb") as fh:
            fh.write(raw)
        return self.estimate_cost(1)
