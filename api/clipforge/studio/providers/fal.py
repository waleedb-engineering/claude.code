"""fal.ai — KI-Video (Text→Video, Bild→Video) und sprechende Avatare.

Ein Schlüssel (FAL_KEY), viele Modelle. Ablauf über die Warteschlangen-API:
  POST https://queue.fal.run/<modell>        → request_id, status_url, response_url
  GET  status_url                            → IN_QUEUE | IN_PROGRESS | COMPLETED
  GET  response_url                          → {"video": {"url": ...}}
Das fertige Video wird über den SSRF-geschützten Abruf geladen (nur
öffentliche Adressen, Größen- und Zeitlimit, nur Videoformate).

UNGETESTET gegen den echten Dienst: Die API-Dokumentation war während der
Entwicklung nicht erreichbar; Feldnamen folgen dem bekannten fal-Schema.
Modelle und Preise sind über Umgebungsvariablen einstellbar.
"""

from __future__ import annotations

import base64
import json
import mimetypes
import os
import time
import urllib.error
import urllib.request

from ..errors import ProviderError
from .base import AvatarProvider, VideoProvider

QUEUE = "https://queue.fal.run"
MAX_INPUT_BYTES = 15 * 1024 * 1024
MAX_VIDEO_BYTES = 300 * 1024 * 1024


def _http(method: str, url: str, headers: dict, body: dict | None = None,
          timeout: float = 60.0) -> tuple[int, dict]:
    data = json.dumps(body).encode("utf-8") if body is not None else None
    req = urllib.request.Request(url, data=data, method=method,
                                 headers={"Content-Type": "application/json", **headers})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:  # noqa: S310 — fester Host
            return resp.status, json.loads(resp.read(5 * 1024 * 1024) or b"{}")
    except urllib.error.HTTPError as exc:
        try:
            return exc.code, json.loads(exc.read(64 * 1024) or b"{}")
        except ValueError:
            return exc.code, {}


FAL_HTTP = _http  # in Tests ersetzbar
SLEEP = time.sleep  # in Tests ersetzbar (nie time.sleep global überschreiben)


def _download(url: str, out_path: str) -> None:
    from ..errors import StudioError
    from ..safe_fetch import fetch
    try:
        res = fetch(url, allowed_types=("video/mp4", "video/quicktime", "video/webm",
                                        "application/octet-stream"),
                    max_bytes=MAX_VIDEO_BYTES, timeout=300, **DOWNLOAD_KWARGS)
    except StudioError as exc:
        raise ProviderError("fal", f"Video-Download fehlgeschlagen ({exc.code})") from None
    with open(out_path, "wb") as fh:
        fh.write(res.body)


DOWNLOAD_KWARGS: dict = {}  # Tests: Fake-Transport/-Resolver


def data_uri(path: str) -> str:
    size = os.path.getsize(path)
    if size > MAX_INPUT_BYTES:
        raise ProviderError("fal", "Eingabedatei zu groß für die Übertragung")
    mime = mimetypes.guess_type(path)[0] or "application/octet-stream"
    with open(path, "rb") as fh:
        return f"data:{mime};base64,{base64.b64encode(fh.read()).decode('ascii')}"


def _auth() -> dict:
    return {"Authorization": "Key " + os.environ.get("FAL_KEY", "")}


def run(model: str, payload: dict, should_cancel=None, timeout: float = 900.0,
        poll_interval: float = 3.0) -> dict:
    """Auftrag einreichen, warten, Ergebnis holen. Fehler → ProviderError (ohne Schlüssel)."""
    try:
        code, sub = FAL_HTTP("POST", f"{QUEUE}/{model}", _auth(), payload)
    except Exception as exc:  # noqa: BLE001
        raise ProviderError("fal", f"Anfrage fehlgeschlagen ({type(exc).__name__})") from None
    if code in (401, 403):
        raise ProviderError("fal", "Schlüssel abgelehnt")
    if code >= 400 or not sub.get("status_url") or not sub.get("response_url"):
        raise ProviderError("fal", f"Auftrag nicht angenommen (HTTP {code})")
    deadline = time.monotonic() + timeout
    while True:
        if should_cancel and should_cancel():
            try:
                if sub.get("cancel_url"):
                    FAL_HTTP("PUT", sub["cancel_url"], _auth(), None)
            except Exception:  # noqa: BLE001
                pass
            raise ProviderError("fal", "abgebrochen")
        try:
            code, st = FAL_HTTP("GET", sub["status_url"], _auth(), None)
        except Exception as exc:  # noqa: BLE001
            raise ProviderError("fal", f"Statusabfrage fehlgeschlagen ({type(exc).__name__})") from None
        status = st.get("status")
        if status == "COMPLETED":
            break
        if code >= 400 or status not in ("IN_QUEUE", "IN_PROGRESS"):
            raise ProviderError("fal", f"Auftrag fehlgeschlagen ({status or code})")
        if time.monotonic() > deadline:
            raise ProviderError("fal", "Zeitlimit überschritten")
        SLEEP(poll_interval)
    code, result = FAL_HTTP("GET", sub["response_url"], _auth(), None)
    if code >= 400:
        detail = result.get("detail")
        raise ProviderError("fal", f"Ergebnis nicht verfügbar ({str(detail)[:120] or code})")
    return result


def _video_url(result: dict) -> str:
    video = result.get("video")
    url = video.get("url") if isinstance(video, dict) else None
    if not isinstance(url, str) or not url.startswith("https://"):
        raise ProviderError("fal", "Antwort enthält kein Video")
    return url


class FalVideo(VideoProvider):
    id, label = "fal_video", "fal.ai KI-Video (Kling)"
    local, paid, live_verified = False, True, False
    env_keys = ("FAL_KEY",)
    requires_flag = "studio_external_providers"
    setup_hint = "FAL_KEY setzen (fal.ai → Dashboard → Keys). Abrechnung pro Videosekunde."
    durations = (5, 10)

    def models(self) -> tuple[str, str]:
        return (os.environ.get("CLIPFORGE_FAL_T2V_MODEL",
                               "fal-ai/kling-video/v2.1/master/text-to-video"),
                os.environ.get("CLIPFORGE_FAL_I2V_MODEL",
                               "fal-ai/kling-video/v2.1/standard/image-to-video"))

    def estimate_cost(self, seconds: float) -> float:
        from ..costs import price
        return float(seconds) * price("fal_video_per_second")

    def generate(self, prompt, image_path, seconds, aspect_ratio, out_path, should_cancel=None):
        t2v, i2v = self.models()
        duration = str(self.clip_seconds(seconds))
        payload = {"prompt": prompt[:2500], "duration": duration,
                   "negative_prompt": "blur, distortion, low quality, watermark, text"}
        if image_path:
            payload["image_url"] = data_uri(image_path)
            model = i2v
        else:
            # Kling kennt 16:9, 9:16, 1:1 — 4:5 wird als 9:16 erzeugt und zugeschnitten
            payload["aspect_ratio"] = aspect_ratio if aspect_ratio in ("16:9", "9:16", "1:1") else "9:16"
            model = t2v
        result = run(model, payload, should_cancel)
        _download(_video_url(result), out_path)
        return self.estimate_cost(int(duration))


class FalAvatar(AvatarProvider):
    id, label = "fal_avatar", "fal.ai Talking Avatar"
    local, paid, live_verified = False, True, False
    env_keys = ("FAL_KEY",)
    requires_flag = "studio_external_providers"
    setup_hint = "FAL_KEY setzen (fal.ai). Abrechnung pro Video bzw. Sekunde, je nach Modell."

    def model(self) -> str:
        return os.environ.get("CLIPFORGE_FAL_AVATAR_MODEL", "fal-ai/sadtalker")

    def estimate_cost(self, seconds: float) -> float:
        from ..costs import price
        return max(1.0, float(seconds)) * price("fal_avatar_per_second")

    def generate(self, image_path, audio_path, out_path, should_cancel=None):
        payload = {"source_image_url": data_uri(image_path),
                   "driven_audio_url": data_uri(audio_path)}
        result = run(self.model(), payload, should_cancel)
        _download(_video_url(result), out_path)
        from ..audio import media_duration
        return self.estimate_cost(media_duration(audio_path))
