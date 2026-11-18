"""Lokale KI-Modelle: Katalog, Download nur nach Zustimmung, Prüfsummen.

Alle Modelle stehen fest im Katalog (keine frei wählbaren URLs → kein SSRF).
Ein Download startet nur, wenn der Benutzer Lizenz und Größe ausdrücklich
bestätigt (`accept_license=True`). Dateien landen in
`CLIPFORGE_MODELS_DIR` bzw. `<studio>/models`, Piper-Stimmen im Piper-Ordner.
"""

from __future__ import annotations

import hashlib
import os
import threading
import urllib.request

from .errors import StudioError
from .storage import studio_dir

_GH = "https://github.com/danielgatis/rembg/releases/download/v0.0.0/"
_ZOO = "https://media.githubusercontent.com/media/opencv/opencv_zoo/main/models/"
_PIPER = "https://huggingface.co/rhasspy/piper-voices/resolve/v1.0.0/"

CATALOG: dict[str, dict] = {
    # --- Hintergrundentfernung (U²-Net-Familie, Apache-2.0)
    "bg_fast": {
        "label": "Hintergrund: schnell (U²-Net small)", "group": "background",
        "files": [{"name": "u2netp.onnx", "url": _GH + "u2netp.onnx",
                   "md5": "8e83ca70e441ab06c318d82300c84806"}],
        "mb": 4.6, "license": "Apache-2.0 (U²-Net)", "commercial": True,
    },
    "bg_quality": {
        "label": "Hintergrund: Qualität (Silueta)", "group": "background",
        "files": [{"name": "silueta.onnx", "url": _GH + "silueta.onnx",
                   "md5": "55e59e0d8062d2f5d013f4725ee84782"}],
        "mb": 43, "license": "Apache-2.0 (U²-Net, verkleinert von rembg)", "commercial": True,
    },
    "bg_person": {
        "label": "Hintergrund: Personen (U²-Net Human Seg)", "group": "background",
        "files": [{"name": "u2net_human_seg.onnx", "url": _GH + "u2net_human_seg.onnx",
                   "md5": "c09ddc2e0104f800e3e1bb4652583d1f"}],
        "mb": 168, "license": "Apache-2.0 (U²-Net)", "commercial": True,
    },
    # --- Gesichtserkennung für die Identitätsprüfung (OpenCV Zoo)
    "face_detect": {
        "label": "Gesichtserkennung (YuNet)", "group": "face",
        "files": [{"name": "face_detection_yunet_2023mar.onnx",
                   "url": _ZOO + "face_detection_yunet/face_detection_yunet_2023mar.onnx",
                   "sha256": "8f2383e4dd3cfbb4553ea8718107fc0423210dc964f9f4280604804ed2552fa4"}],
        "mb": 0.2, "license": "MIT (OpenCV Zoo YuNet)", "commercial": True,
    },
    "face_verify": {
        "label": "Gesichtsabgleich (SFace)", "group": "face",
        "files": [{"name": "face_recognition_sface_2021dec.onnx",
                   "url": _ZOO + "face_recognition_sface/face_recognition_sface_2021dec.onnx",
                   "sha256": "0ba9fbfa01b5270c96627c4ef784da859931e02f04419c829e83484087c34e79"}],
        "mb": 37, "license": "Apache-2.0 (OpenCV Zoo SFace)", "commercial": True,
    },
    # --- Übersetzung (Argos Translate, CTranslate2-Format)
    "translate_de_en": {
        "label": "Übersetzung Deutsch → Englisch (Argos)", "group": "translate",
        "files": [{"name": "translate-de_en-1_3.argosmodel",
                   "url": "https://argos-net.com/v1/translate-de_en-1_3.argosmodel"}],
        "mb": 100, "license": "Argos-Translate-Paket (Lizenz im Paket, OPUS-Daten) – prüfen",
        "commercial": None,
    },
    "translate_en_de": {
        "label": "Übersetzung Englisch → Deutsch (Argos)", "group": "translate",
        "files": [{"name": "translate-en_de-1_3.argosmodel",
                   "url": "https://argos-net.com/v1/translate-en_de-1_3.argosmodel"}],
        "mb": 100, "license": "Argos-Translate-Paket (Lizenz im Paket, OPUS-Daten) – prüfen",
        "commercial": None,
    },
    # --- Piper-Stimmen (Hugging Face rhasspy/piper-voices)
    "piper_de_thorsten": {
        "label": "Piper Deutsch – Thorsten (mittel)", "group": "piper", "language": "de",
        "files": [{"name": "de_DE-thorsten-medium.onnx",
                   "url": _PIPER + "de/de_DE/thorsten/medium/de_DE-thorsten-medium.onnx"},
                  {"name": "de_DE-thorsten-medium.onnx.json",
                   "url": _PIPER + "de/de_DE/thorsten/medium/de_DE-thorsten-medium.onnx.json"}],
        "mb": 63, "license": "CC0 (Thorsten-Datensatz) – Modellkarte prüfen", "commercial": True,
    },
    "piper_de_kerstin": {
        "label": "Piper Deutsch – Kerstin (tief)", "group": "piper", "language": "de",
        "files": [{"name": "de_DE-kerstin-low.onnx",
                   "url": _PIPER + "de/de_DE/kerstin/low/de_DE-kerstin-low.onnx"},
                  {"name": "de_DE-kerstin-low.onnx.json",
                   "url": _PIPER + "de/de_DE/kerstin/low/de_DE-kerstin-low.onnx.json"}],
        "mb": 63, "license": "CC0 – Modellkarte prüfen", "commercial": True,
    },
    "piper_en_amy": {
        "label": "Piper English – Amy (medium)", "group": "piper", "language": "en",
        "files": [{"name": "en_US-amy-medium.onnx",
                   "url": _PIPER + "en/en_US/amy/medium/en_US-amy-medium.onnx"},
                  {"name": "en_US-amy-medium.onnx.json",
                   "url": _PIPER + "en/en_US/amy/medium/en_US-amy-medium.onnx.json"}],
        "mb": 63, "license": "laut Modellkarte (vor kommerzieller Nutzung prüfen)",
        "commercial": None,
    },
    "piper_en_lessac": {
        "label": "Piper English – Lessac (medium)", "group": "piper", "language": "en",
        "files": [{"name": "en_US-lessac-medium.onnx",
                   "url": _PIPER + "en/en_US/lessac/medium/en_US-lessac-medium.onnx"},
                  {"name": "en_US-lessac-medium.onnx.json",
                   "url": _PIPER + "en/en_US/lessac/medium/en_US-lessac-medium.onnx.json"}],
        "mb": 63, "license": "Blizzard-Lessac-Datensatz: nur nicht-kommerziell",
        "commercial": False,
    },
}

# Test-Hook: (url) -> Datei-ähnliches Objekt mit read(n)
OPEN_URL = None
MAX_BYTES = 400 * 1024 * 1024
_locks: dict[str, threading.Lock] = {}
_guard = threading.Lock()


def models_dir() -> str:
    path = os.environ.get("CLIPFORGE_MODELS_DIR") or os.path.join(studio_dir(), "models")
    os.makedirs(path, exist_ok=True)
    return path


def _target_dir(model_id: str) -> str:
    if CATALOG[model_id]["group"] == "piper":
        from .providers.local import piper_dir
        path = piper_dir()
        os.makedirs(path, exist_ok=True)
        return path
    return models_dir()


def model_path(model_id: str, index: int = 0) -> str | None:
    """Pfad der (ersten) Modelldatei, wenn installiert."""
    spec = CATALOG.get(model_id)
    if not spec:
        return None
    paths = [os.path.join(_target_dir(model_id), f["name"]) for f in spec["files"]]
    if all(os.path.isfile(p) and os.path.getsize(p) > 0 for p in paths):
        return paths[index]
    return None


def status(group: str | None = None) -> list[dict]:
    out = []
    for mid, spec in CATALOG.items():
        if group and spec["group"] != group:
            continue
        out.append({"id": mid, "label": spec["label"], "group": spec["group"],
                    "language": spec.get("language"), "size_mb": spec["mb"],
                    "license": spec["license"], "commercial_use": spec["commercial"],
                    "installed": model_path(mid) is not None})
    return out


def _open(url: str):
    if OPEN_URL is not None:
        return OPEN_URL(url)
    req = urllib.request.Request(url, headers={"User-Agent": "ClipForge-ModelDownloader"})
    return urllib.request.urlopen(req, timeout=60)  # noqa: S310 — feste Katalog-URLs


def download(model_id: str, accept_license: bool, progress=None) -> dict:
    spec = CATALOG.get(model_id)
    if not spec:
        raise StudioError("model_unknown", "Unbekanntes Modell.", 404)
    if not accept_license:
        raise StudioError("consent_required",
                          f"Bitte Lizenz ({spec['license']}) und Download "
                          f"(~{spec['mb']} MB) ausdrücklich bestätigen.", 400)
    with _guard:
        lock = _locks.setdefault(model_id, threading.Lock())
    if not lock.acquire(blocking=False):
        raise StudioError("download_running", "Dieses Modell wird bereits geladen.", 409)
    try:
        if model_path(model_id):
            return {"id": model_id, "installed": True, "already": True}
        target = _target_dir(model_id)
        for f in spec["files"]:
            dest = os.path.join(target, f["name"])
            tmp = dest + ".part"
            md5, sha = hashlib.md5(), hashlib.sha256()  # noqa: S324 — nur Prüfsumme
            total = 0
            try:
                with _open(f["url"]) as resp, open(tmp, "wb") as out:
                    while True:
                        chunk = resp.read(1024 * 1024)
                        if not chunk:
                            break
                        total += len(chunk)
                        if total > MAX_BYTES:
                            raise StudioError("download_too_large", "Download größer als erwartet.", 502)
                        md5.update(chunk)
                        sha.update(chunk)
                        out.write(chunk)
                        if progress:
                            progress(f"{f['name']}: {total // (1024 * 1024)} MB")
            except StudioError:
                _rm(tmp)
                raise
            except OSError as exc:
                _rm(tmp)
                raise StudioError("download_failed",
                                  f"Download fehlgeschlagen ({type(exc).__name__}). "
                                  "Internetverbindung prüfen und erneut versuchen.", 502) from exc
            if (f.get("md5") and md5.hexdigest() != f["md5"]) or \
                    (f.get("sha256") and sha.hexdigest() != f["sha256"]):
                _rm(tmp)
                raise StudioError("checksum_mismatch",
                                  "Prüfsumme stimmt nicht — Datei verworfen.", 502)
            if total == 0:
                _rm(tmp)
                raise StudioError("download_failed", "Leere Datei erhalten.", 502)
            os.replace(tmp, dest)
        return {"id": model_id, "installed": True, "already": False}
    finally:
        lock.release()


def delete(model_id: str) -> None:
    spec = CATALOG.get(model_id)
    if not spec:
        raise StudioError("model_unknown", "Unbekanntes Modell.", 404)
    for f in spec["files"]:
        _rm(os.path.join(_target_dir(model_id), f["name"]))


def _rm(path: str) -> None:
    try:
        os.remove(path)
    except OSError:
        pass
