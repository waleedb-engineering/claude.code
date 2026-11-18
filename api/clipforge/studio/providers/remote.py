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
from .base import ImageProvider, Provider, VoiceProvider, VoiceResult
from ..credentials import secret


class ResponseTooLarge(ValueError):
    pass


def max_response_bytes() -> int:
    try:
        mb = int(os.environ.get("CLIPFORGE_PROVIDER_MAX_RESPONSE_MB", "50"))
    except ValueError:
        mb = 50
    return max(1, mb) * 1024 * 1024


def _http_post(url: str, headers: dict, payload: dict, timeout: float = 120.0) -> bytes:
    """POST an einen FEST im Code stehenden Provider-Host.

    Die Antwort wird in Blöcken gelesen und hart begrenzt: ist sie größer als
    das Limit, wird abgebrochen (statt still abzuschneiden und eine kaputte
    Datei zu speichern).
    """
    req = urllib.request.Request(
        url, data=json.dumps(payload).encode("utf-8"), method="POST",
        headers={"Content-Type": "application/json", **headers})
    limit = max_response_bytes()
    with urllib.request.urlopen(req, timeout=timeout) as resp:  # noqa: S310 — feste HTTPS-Hosts
        declared = resp.headers.get("Content-Length")
        if declared and declared.isdigit() and int(declared) > limit:
            raise ResponseTooLarge()
        chunks, total = [], 0
        while True:
            chunk = resp.read(65536)
            if not chunk:
                break
            total += len(chunk)
            if total > limit:
                raise ResponseTooLarge()
            chunks.append(chunk)
        return b"".join(chunks)


def looks_like_audio(data: bytes) -> bool:
    """Magic-Bytes statt Content-Type-Header: MP3 (ID3/Frame-Sync), WAV, OGG, FLAC."""
    head = data[:12]
    return (head[:3] == b"ID3" or (len(head) > 1 and head[0] == 0xFF and head[1] & 0xE0 == 0xE0)
            or (head[:4] == b"RIFF" and head[8:12] == b"WAVE") or head[:4] in (b"OggS", b"fLaC"))


# In Tests ersetzbar (Monkeypatch) — nie ein echter Netz-Call in der Suite.
HTTP_POST = _http_post


def _post(provider: str, url: str, headers: dict, payload: dict) -> bytes:
    try:
        return HTTP_POST(url, headers, payload)
    except urllib.error.HTTPError as exc:
        raise ProviderError(provider, f"HTTP {exc.code}") from None
    except ResponseTooLarge:
        raise ProviderError(provider, "Antwort überschreitet das Größenlimit") from None
    except Exception as exc:  # noqa: BLE001
        raise ProviderError(provider, f"Anfrage fehlgeschlagen ({type(exc).__name__})") from None


class ElevenLabsVoice(VoiceProvider):
    id, label = "elevenlabs", "ElevenLabs (Cloud)"
    local, paid, live_verified = False, True, False
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

    def _all(self) -> list[tuple[str, str, str]]:
        """Standardstimmen + eigene, mit Einwilligung geklonte Stimmen."""
        from ..voice_clone import list_clones
        clones = [(c["voice_id"], f"{c['name']} (geklont)", "custom")
                  for c in list_clones() if c.get("provider") == "elevenlabs"]
        return [*self._VOICES, *clones]

    def voices(self, language):
        return [{"id": v, "label": n, "tone": t, "language": language}
                for v, n, t in self._all()]

    def estimate_cost(self, chars):
        from ..costs import price
        return chars / 1000.0 * price("elevenlabs_per_1k_chars")

    def synthesize(self, text, language, voice_id, out_path, model=None, speed=1.0):
        ids = {v for v, _, _ in self._all()}
        voice = voice_id if voice_id in ids else self._VOICES[0][0]
        body = _post(self.id, f"https://api.elevenlabs.io/v1/text-to-speech/{voice}",
                     {"xi-api-key": (secret("ELEVENLABS_API_KEY") or ""),
                      "Accept": "audio/mpeg"},
                     {"text": text, "model_id": model or os.environ.get(
                         "CLIPFORGE_ELEVENLABS_MODEL", "eleven_multilingual_v2"),
                      # ElevenLabs erlaubt 0,7–1,2
                      "voice_settings": {"speed": round(max(0.7, min(1.2, speed)), 2)}})
        if len(body) < 64 or not looks_like_audio(body):
            raise ProviderError(self.id, "Antwort ist kein Audio")
        with open(out_path, "wb") as fh:
            fh.write(body)
        return VoiceResult(path=out_path, cost_usd=self.estimate_cost(len(text)))


class OpenAIVoice(VoiceProvider):
    id, label = "openai_tts", "OpenAI TTS (Cloud)"
    local, paid, live_verified = False, True, False
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

    def synthesize(self, text, language, voice_id, out_path, model=None, speed=1.0):
        voice = voice_id if voice_id in {v for v, _ in self._VOICES} else "alloy"
        body = _post(self.id, "https://api.openai.com/v1/audio/speech",
                     {"Authorization": "Bearer " + (secret("OPENAI_API_KEY") or "")},
                     {"model": model or os.environ.get("CLIPFORGE_OPENAI_TTS_MODEL", "tts-1"),
                      "voice": voice, "input": text, "response_format": "mp3",
                      "speed": round(max(0.25, min(4.0, speed)), 2)})
        if len(body) < 64 or not looks_like_audio(body):
            raise ProviderError(self.id, "Antwort ist kein Audio")
        with open(out_path, "wb") as fh:
            fh.write(body)
        return VoiceResult(path=out_path, cost_usd=self.estimate_cost(len(text)))


class OpenAIImage(ImageProvider):
    id, label = "openai_image", "OpenAI Bilder (Cloud)"
    local, paid, live_verified = False, True, False
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
                     {"Authorization": "Bearer " + (secret("OPENAI_API_KEY") or "")},
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


# --------------------------------------------------------------- Stimmklon

def _multipart(fields: dict, files: list[tuple[str, str, bytes]]) -> tuple[bytes, str]:
    import uuid
    boundary = "cf" + uuid.uuid4().hex
    parts = []
    for key, value in fields.items():
        parts.append(f"--{boundary}\r\nContent-Disposition: form-data; name=\"{key}\"\r\n\r\n"
                     f"{value}\r\n".encode("utf-8"))
    for key, filename, data in files:
        parts.append(f"--{boundary}\r\nContent-Disposition: form-data; name=\"{key}\"; "
                     f"filename=\"{filename}\"\r\nContent-Type: application/octet-stream"
                     f"\r\n\r\n".encode("utf-8") + data + b"\r\n")
    parts.append(f"--{boundary}--\r\n".encode("utf-8"))
    return b"".join(parts), f"multipart/form-data; boundary={boundary}"


def _http_raw(method: str, url: str, headers: dict, body: bytes | None,
              timeout: float = 120.0) -> tuple[int, bytes]:
    req = urllib.request.Request(url, data=body, method=method, headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:  # noqa: S310 — fester Host
            return resp.status, resp.read(1024 * 1024)
    except urllib.error.HTTPError as exc:
        return exc.code, exc.read(64 * 1024)


HTTP_RAW = _http_raw  # in Tests ersetzbar


class ElevenLabsCloneProvider(Provider):
    """Instant Voice Cloning bei ElevenLabs — nur mit dokumentierter Einwilligung."""

    id, kind, label = "elevenlabs_clone", "voice_clone", "ElevenLabs Voice Cloning"
    local, paid, live_verified = False, True, False
    env_keys = ("ELEVENLABS_API_KEY",)
    requires_flag = "studio_voice_cloning"
    setup_hint = ("ELEVENLABS_API_KEY setzen; Stimmklon braucht einen bezahlten "
                  "ElevenLabs-Tarif (laut ElevenLabs ab „Starter“).")

    def clone(self, name: str, samples: list[str], description: str) -> str:
        files = []
        for path in samples:
            with open(path, "rb") as fh:
                files.append(("files", os.path.basename(path), fh.read()))
        body, ctype = _multipart({"name": name, "description": description,
                                  "remove_background_noise": "false"}, files)
        try:
            code, raw = HTTP_RAW("POST", "https://api.elevenlabs.io/v1/voices/add",
                                 {"xi-api-key": (secret("ELEVENLABS_API_KEY") or ""),
                                  "Content-Type": ctype}, body)
        except Exception as exc:  # noqa: BLE001
            raise ProviderError(self.id, f"Anfrage fehlgeschlagen ({type(exc).__name__})") from None
        if code in (401, 403):
            raise ProviderError(self.id, "Schlüssel abgelehnt oder Tarif ohne Stimmklon")
        try:
            voice_id = json.loads(raw).get("voice_id")
        except ValueError:
            voice_id = None
        if code >= 400 or not isinstance(voice_id, str) or not voice_id.isalnum():
            raise ProviderError(self.id, f"Stimmklon fehlgeschlagen (HTTP {code})")
        return voice_id

    def delete(self, voice_id: str) -> None:
        try:
            code, _ = HTTP_RAW("DELETE", f"https://api.elevenlabs.io/v1/voices/{voice_id}",
                               {"xi-api-key": (secret("ELEVENLABS_API_KEY") or "")}, None)
        except Exception as exc:  # noqa: BLE001
            raise ProviderError(self.id, f"Anfrage fehlgeschlagen ({type(exc).__name__})") from None
        if code >= 400 and code != 404:
            raise ProviderError(self.id, f"Löschen fehlgeschlagen (HTTP {code})")
