"""Thumbnail-Vorschläge aus einem fertigen Video (lokal, kostenlos).

Bewertet 16 gleichmäßig verteilte Bilder nach Schärfe (Laplace-Varianz),
Belichtung (Abstand zur mittleren Helligkeit) und — wenn das YuNet-Modell
geladen ist — einem gut sichtbaren Gesicht. Liefert die 3 besten als JPEG,
mit Begründung. Keine Klick-Vorhersage."""

from __future__ import annotations

import os
import subprocess

import numpy as np

from .errors import StudioError


def suggest(video: str, out_dir: str, count: int = 3) -> list[dict]:
    import cv2
    from ..ffmpeg_utils import probe
    info = probe(video)
    dur = float(info.duration or 0)
    if dur <= 0:
        raise StudioError("file_unreadable", "Video ohne Dauer.", 415)
    os.makedirs(out_dir, exist_ok=True)
    face_ok = True
    try:
        from .faceswap import faces_in
    except Exception:  # noqa: BLE001
        face_ok = False
    cands = []
    for k in range(16):
        t = dur * (0.05 + 0.9 * k / 15)
        res = subprocess.run(["ffmpeg", "-v", "error", "-ss", f"{t:.2f}", "-i", video, "-frames:v", "1",
                              "-f", "image2pipe", "-vcodec", "png", "-"], capture_output=True, timeout=60)
        img = cv2.imdecode(np.frombuffer(res.stdout, np.uint8), cv2.IMREAD_COLOR) if res.stdout else None
        if img is None:
            continue
        gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
        sharp = float(cv2.Laplacian(gray, cv2.CV_64F).var())
        bright = float(gray.mean())
        exposure = 1 - min(1.0, abs(bright - 128) / 128)
        face = 0.0
        reasons = []
        if face_ok:
            try:
                found = faces_in(img)
                if found:
                    area = max(f[2] * f[3] for f in found) / (img.shape[0] * img.shape[1])
                    face = min(1.0, area * 12)
                    reasons.append("Gesicht gut sichtbar" if face > 0.3 else "Gesicht klein")
            except StudioError:
                face_ok = False
        cands.append({"t": round(t, 2), "img": img, "sharp": sharp, "exposure": exposure,
                      "face": face, "reasons": reasons})
    if not cands:
        raise StudioError("file_unreadable", "Keine Bilder lesbar.", 415)
    smax = max(c["sharp"] for c in cands) or 1.0
    for c in cands:
        c["score"] = round(100 * (0.5 * c["sharp"] / smax + 0.25 * c["exposure"] + 0.25 * c["face"]), 1)
        c["reasons"] = [f"Schärfe {c['sharp'] / smax:.0%} des besten Bildes",
                        f"Belichtung {c['exposure']:.0%}"] + c["reasons"]
    picked: list[dict] = []
    for c in sorted(cands, key=lambda x: -x["score"]):
        if all(abs(c["t"] - p["t"]) > dur * 0.1 for p in picked):
            picked.append(c)
        if len(picked) == count:
            break
    out = []
    for i, c in enumerate(picked, start=1):
        name = f"thumb_{i}.jpg"
        cv2.imwrite(os.path.join(out_dir, name), c["img"], [cv2.IMWRITE_JPEG_QUALITY, 90])
        out.append({"file": name, "t": c["t"], "score": c["score"], "reasons": c["reasons"],
                    "face_check": face_ok})
    return out
