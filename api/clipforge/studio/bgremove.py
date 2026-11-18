"""Lokale Hintergrundentfernung (Bild und Video) mit U²-Net über OpenCV-DNN.

Kein Cloud-Dienst, keine Kosten. Modelle kommen aus dem Modell-Katalog
(Download nur nach Zustimmung). Ergebnis ist immer eine NEUE Mediendatei;
das Original bleibt unverändert.

Hintergrund-Modi:
  transparent – PNG mit Alphakanal (nur Bilder)
  color       – Volltonfarbe
  image       – eigenes Bild aus der Mediathek
  video       – eigenes Video aus der Mediathek (wird geschleift)
  blur        – unscharfer Originalhintergrund
"""

from __future__ import annotations

import os
import subprocess

import numpy as np

from .errors import StudioError
from .models import model_path

MODES = ("transparent", "color", "image", "video", "blur")
MODEL_IDS = ("bg_fast", "bg_quality", "bg_person")
_SIZE = 320
_MEAN = np.array([0.485, 0.456, 0.406], dtype=np.float32)
_STD = np.array([0.229, 0.224, 0.225], dtype=np.float32)
_nets: dict[str, object] = {}


class Canceled(Exception):
    """Verarbeitung vom Benutzer abgebrochen."""


def _cv2():
    try:
        import cv2
    except ImportError as exc:  # pragma: no cover — in requirements.txt
        raise StudioError("dependency_missing", "OpenCV fehlt (pip install opencv-python-headless).",
                          503) from exc
    return cv2


def available_models() -> list[str]:
    return [m for m in MODEL_IDS if model_path(m)]


def _net(model_id: str):
    if model_id not in MODEL_IDS:
        raise StudioError("validation_error", "Unbekanntes Hintergrund-Modell.")
    path = model_path(model_id)
    if not path:
        raise StudioError("model_missing",
                          "Das Modell für die Hintergrundentfernung ist noch nicht geladen. "
                          "Studio → Einrichtung → Lokale Modelle.", 409,
                          details={"model": model_id})
    if path not in _nets:
        _nets[path] = _cv2().dnn.readNetFromONNX(path)
    return _nets[path]


def mask(frame_bgr: np.ndarray, model_id: str) -> np.ndarray:
    """→ Maske float32 0..1 in Bildgröße (1 = Vordergrund)."""
    cv2 = _cv2()
    h, w = frame_bgr.shape[:2]
    rgb = cv2.cvtColor(cv2.resize(frame_bgr, (_SIZE, _SIZE), interpolation=cv2.INTER_AREA),
                       cv2.COLOR_BGR2RGB).astype(np.float32)
    rgb = (rgb / max(1.0, float(rgb.max())) - _MEAN) / _STD
    blob = rgb.transpose(2, 0, 1)[None].astype(np.float32)
    net = _net(model_id)
    net.setInput(blob)
    out = net.forward()  # (1,1,320,320), erster Ausgang = feinste Maske
    m = out[0, 0]
    lo, hi = float(m.min()), float(m.max())
    m = (m - lo) / (hi - lo) if hi - lo > 1e-6 else np.zeros_like(m)
    return cv2.resize(m.astype(np.float32), (w, h), interpolation=cv2.INTER_LINEAR)


def _background(mode: str, shape, frame_bgr, color: str, bg_frame) -> np.ndarray:
    cv2 = _cv2()
    h, w = shape[:2]
    if mode == "color":
        c = color.lstrip("#")
        r, g, b = int(c[0:2], 16), int(c[2:4], 16), int(c[4:6], 16)
        return np.full((h, w, 3), (b, g, r), dtype=np.uint8)
    if mode == "blur":
        k = max(15, (min(h, w) // 12) | 1)
        return cv2.GaussianBlur(frame_bgr, (k, k), 0)
    # image/video: auf Bildgröße zuschneiden (cover)
    bh, bw = bg_frame.shape[:2]
    scale = max(w / bw, h / bh)
    rs = cv2.resize(bg_frame, (max(w, int(bw * scale + 0.5)), max(h, int(bh * scale + 0.5))))
    y0, x0 = (rs.shape[0] - h) // 2, (rs.shape[1] - w) // 2
    return rs[y0:y0 + h, x0:x0 + w]


def _composite(frame, m, bg) -> np.ndarray:
    a = m[..., None]
    return (frame.astype(np.float32) * a + bg.astype(np.float32) * (1 - a)).clip(0, 255).astype(np.uint8)


def _check_color(color: str) -> str:
    c = (color or "#00b140").strip()
    if len(c) != 7 or c[0] != "#" or any(ch not in "0123456789abcdefABCDEF" for ch in c[1:]):
        raise StudioError("validation_error", "Farbe bitte als #RRGGBB angeben.")
    return c


def process_image(src: str, out: str, *, mode: str = "transparent", model_id: str = "bg_fast",
                  color: str = "#00b140", background: str | None = None) -> dict:
    cv2 = _cv2()
    if mode not in MODES or mode == "video":
        raise StudioError("validation_error", "Für Bilder: transparent, color, image oder blur.")
    color = _check_color(color)
    img = cv2.imread(src, cv2.IMREAD_COLOR)
    if img is None:
        raise StudioError("file_unreadable", "Bild konnte nicht gelesen werden.", 415)
    m = mask(img, model_id)
    if mode == "transparent":
        rgba = cv2.cvtColor(img, cv2.COLOR_BGR2BGRA)
        rgba[..., 3] = (m * 255).clip(0, 255).astype(np.uint8)
        cv2.imwrite(out, rgba)
    else:
        bg_img = None
        if mode == "image":
            bg_img = cv2.imread(background or "", cv2.IMREAD_COLOR)
            if bg_img is None:
                raise StudioError("media_not_found", "Hintergrundbild nicht gefunden.", 404)
        cv2.imwrite(out, _composite(img, m, _background(mode, img.shape, img, color, bg_img)))
    return {"width": int(img.shape[1]), "height": int(img.shape[0]),
            "foreground_ratio": round(float((m > 0.5).mean()), 3)}


def _probe(path: str) -> tuple[int, int, float, float]:
    cv2 = _cv2()
    cap = cv2.VideoCapture(path)
    if not cap.isOpened():
        raise StudioError("file_unreadable", "Video konnte nicht gelesen werden.", 415)
    w, h = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH)), int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
    fps = cap.get(cv2.CAP_PROP_FPS) or 30.0
    frames = cap.get(cv2.CAP_PROP_FRAME_COUNT) or 0
    cap.release()
    return w, h, fps, frames


def process_video(src: str, out: str, *, mode: str = "color", model_id: str = "bg_person",
                  color: str = "#00b140", background: str | None = None,
                  max_seconds: float = 180.0, progress=None, should_cancel=None) -> dict:
    """Bild für Bild maskieren, Maske zeitlich glätten (kein Flackern),
    neu zusammensetzen und den Originalton übernehmen."""
    cv2 = _cv2()
    if mode not in ("color", "image", "video", "blur"):
        raise StudioError("validation_error",
                          "Für Videos: color, image, video oder blur (kein transparentes MP4).")
    color = _check_color(color)
    w, h, fps, frames = _probe(src)
    if frames and frames / fps > max_seconds:
        raise StudioError("video_too_long",
                          f"Video ist zu lang für die lokale Verarbeitung (max. {int(max_seconds)} s).",
                          413)
    bg_img, bg_cap = None, None
    if mode == "image":
        bg_img = cv2.imread(background or "", cv2.IMREAD_COLOR)
        if bg_img is None:
            raise StudioError("media_not_found", "Hintergrundbild nicht gefunden.", 404)
    if mode == "video":
        bg_cap = cv2.VideoCapture(background or "")
        if not bg_cap.isOpened():
            raise StudioError("media_not_found", "Hintergrundvideo nicht gefunden.", 404)
    w2, h2 = w - w % 2, h - h % 2
    tmp = out + ".part.mp4"
    enc = subprocess.Popen(
        ["ffmpeg", "-y", "-loglevel", "error", "-f", "rawvideo", "-pix_fmt", "bgr24",
         "-s", f"{w2}x{h2}", "-r", f"{fps:.3f}", "-i", "-", "-i", src,
         "-map", "0:v", "-map", "1:a?", "-c:v", "libx264", "-preset", "veryfast", "-crf", "20",
         "-pix_fmt", "yuv420p", "-c:a", "aac", "-shortest", "-movflags", "+faststart", tmp],
        stdin=subprocess.PIPE, stderr=subprocess.PIPE)
    cap = cv2.VideoCapture(src)
    prev = None
    n = 0
    try:
        while True:
            if should_cancel and should_cancel():
                raise Canceled()
            ok, frame = cap.read()
            if not ok:
                break
            frame = frame[:h2, :w2]
            m = mask(frame, model_id)
            m = m if prev is None else 0.6 * m + 0.4 * prev  # zeitliche Glättung
            prev = m
            bg_frame = bg_img
            if bg_cap is not None:
                ok_bg, bg_frame = bg_cap.read()
                if not ok_bg:
                    bg_cap.set(cv2.CAP_PROP_POS_FRAMES, 0)
                    ok_bg, bg_frame = bg_cap.read()
                if not ok_bg:
                    raise StudioError("file_unreadable", "Hintergrundvideo nicht lesbar.", 415)
            enc.stdin.write(_composite(frame, m, _background(mode, frame.shape, frame, color,
                                                             bg_frame)).tobytes())
            n += 1
            if progress and n % 15 == 0:
                progress(f"Hintergrund entfernen: Bild {n}" + (f"/{int(frames)}" if frames else ""))
        enc.stdin.close()
        err = enc.stderr.read().decode("utf-8", "replace")
        if enc.wait() != 0 or n == 0:
            raise StudioError("render_failed", "Video konnte nicht geschrieben werden: "
                              + (err.strip().splitlines() or ["leer"])[-1][:200], 500)
        os.replace(tmp, out)
    except BaseException:
        try:
            enc.kill()
        except OSError:
            pass
        if os.path.exists(tmp):
            os.remove(tmp)
        raise
    finally:
        cap.release()
        if bg_cap is not None:
            bg_cap.release()
    return {"width": w2, "height": h2, "frames": n, "fps": round(fps, 3)}
