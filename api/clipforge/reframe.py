"""Smart 9:16 Reframe — statischer Smart-Crop v1.

Idee (bewusst stabil statt spektakulär): Statt jeden Frame dynamisch zu croppen
(was mit dem Silence-`select/setpts` kollidiert und zittern kann), wird der Clip
**sampling-basiert** auf Gesichter analysiert, daraus ein **stabiler Fokuspunkt**
(Median der erkannten Gesichts-Mittelpunkte) abgeleitet und ein **fester
horizontaler Crop-Offset** gesetzt. Das ist robust, komponiert mit Silence-
Removal/Captions/Audio und bricht den Export nie.

Detection: OpenCV Haar-Cascade (lokal, kostenlos, keine Cloud). Fehlt OpenCV
oder wird kein Gesicht gefunden → sauberer Fallback auf Center-Crop.
"""

from __future__ import annotations

import math
import os

CASCADE_NAME = "haarcascade_frontalface_default.xml"


def center_crop_filter(out_w: int, out_h: int) -> str:
    """Unveränderter Center-Crop (Scale-to-cover + mittiger Crop)."""
    return (
        f"scale={out_w}:{out_h}:force_original_aspect_ratio=increase,"
        f"crop={out_w}:{out_h}"
    )


def _even(n: float) -> int:
    i = int(round(n))
    return i if i % 2 == 0 else i + 1


def compute_scaled_and_crop(
    in_w: int, in_h: int, out_w: int, out_h: int, focus_frac: float
) -> tuple[int, int, int, int]:
    """Exakte Scale-Dims (cover) + horizontaler Crop-x für einen Fokuspunkt.

    focus_frac ist die x-Position des Fokus als Anteil [0,1] der Quellbreite
    (skalierungs-invariant). Vertikal wird mittig gecroppt.
    """
    scale = max(out_w / in_w, out_h / in_h)
    sw = max(out_w, _even(math.ceil(in_w * scale)))
    sh = max(out_h, _even(math.ceil(in_h * scale)))
    focus_px = max(0.0, min(1.0, focus_frac)) * sw
    x = int(round(focus_px - out_w / 2))
    x = max(0, min(sw - out_w, x))
    y = max(0, (sh - out_h) // 2)
    return sw, sh, x, y


def detect_focus(
    video_path: str,
    start: float,
    end: float,
    *,
    sample_step: float = 0.6,
    max_samples: int = 40,
    min_face: int = 60,
) -> dict:
    """Sampling-basierte Gesichtserkennung im Clip-Bereich [start, end].

    Liefert ein dict mit detection_method, frames_analyzed,
    faces_detected_count, focus_frac (Median, oder None), samples_with_face.
    Wirft nie — bei jedem Problem wird focus_frac=None zurückgegeben.
    """
    info = {
        "detection_method": "unavailable",
        "frames_analyzed": 0,
        "faces_detected_count": 0,
        "focus_frac": None,
        "samples_with_face": 0,
    }
    try:
        import cv2  # lokal importiert -> kein harter Pflicht-Import
    except Exception:
        return info

    try:
        cascade = cv2.CascadeClassifier(
            os.path.join(cv2.data.haarcascades, CASCADE_NAME)
        )
        if cascade.empty():
            return info
        cap = cv2.VideoCapture(video_path)
        if not cap.isOpened():
            return info
        info["detection_method"] = "opencv_haar_frontalface"

        duration = max(0.0, end - start)
        n = max(1, min(max_samples, int(duration / sample_step) + 1))
        fracs: list[float] = []
        analyzed = 0
        faces_total = 0
        for k in range(n):
            t = start + (k + 0.5) * (duration / n)
            cap.set(cv2.CAP_PROP_POS_MSEC, t * 1000.0)
            ok, frame = cap.read()
            if not ok or frame is None:
                continue
            analyzed += 1
            h, w = frame.shape[:2]
            scale = 640.0 / w if w > 640 else 1.0
            small = (
                cv2.resize(frame, (int(w * scale), int(h * scale)))
                if scale != 1.0
                else frame
            )
            gray = cv2.cvtColor(small, cv2.COLOR_BGR2GRAY)
            ms = max(20, int(min_face * scale))
            faces = cascade.detectMultiScale(
                gray, scaleFactor=1.1, minNeighbors=5, minSize=(ms, ms)
            )
            if len(faces) > 0:
                faces_total += len(faces)
                # Entscheidung: größtes Gesicht = i.d.R. der/die Hauptsprecher:in.
                x, _y, fw, _fh = max(faces, key=lambda f: f[2] * f[3])
                fracs.append((x + fw / 2.0) / small.shape[1])
        cap.release()

        info["frames_analyzed"] = analyzed
        info["faces_detected_count"] = faces_total
        if fracs:
            fracs.sort()
            info["focus_frac"] = round(fracs[len(fracs) // 2], 4)  # Median
            info["samples_with_face"] = len(fracs)
    except Exception:
        # Jeder Detection-Fehler -> als „kein Fokus" behandeln (Fallback center)
        info["focus_frac"] = None
    return info


def plan_reframe(
    video_path: str,
    clip_start: float,
    clip_end: float,
    in_w: int,
    in_h: int,
    out_w: int,
    out_h: int,
    mode: str,
) -> tuple[str, dict]:
    """Plant den Crop. Gibt (video_crop_filter, reframe_info) zurück.

    mode: 'center' | 'smart' | 'face'. 'face' nutzt in v1 dieselbe
    Gesichtserkennung wie 'smart'. Bei jedem Problem → Center-Fallback.
    """
    requested = mode if mode in ("center", "smart", "face") else "smart"
    info = {
        "requested_mode": requested,
        "applied_mode": "center",
        "fallback": False,
        "fallback_reason": None,
        "detection_method": None,
        "frames_analyzed": 0,
        "faces_detected_count": 0,
        "focus_x": None,
        "crop_x": None,
        "crop_strategy": "center",
        "smoothing_applied": False,
    }

    if requested == "center":
        return center_crop_filter(out_w, out_h), info

    if not in_w or not in_h:
        info["fallback"] = True
        info["fallback_reason"] = "Quellauflösung unbekannt"
        return center_crop_filter(out_w, out_h), info

    det = detect_focus(video_path, clip_start, clip_end)
    info["detection_method"] = det["detection_method"]
    info["frames_analyzed"] = det["frames_analyzed"]
    info["faces_detected_count"] = det["faces_detected_count"]

    focus = det.get("focus_frac")
    if focus is None:
        info["fallback"] = True
        info["fallback_reason"] = (
            "OpenCV nicht verfügbar"
            if det["detection_method"] == "unavailable"
            else "kein Gesicht erkannt"
        )
        return center_crop_filter(out_w, out_h), info

    sw, sh, x, y = compute_scaled_and_crop(in_w, in_h, out_w, out_h, focus)
    if sw <= out_w:
        # Quelle bereits 9:16 oder schmaler -> kein horizontaler Spielraum
        info["fallback"] = True
        info["fallback_reason"] = "kein horizontaler Spielraum (Quelle nicht breit)"
        return center_crop_filter(out_w, out_h), info

    info["applied_mode"] = requested
    info["focus_x"] = focus
    info["crop_x"] = x
    info["crop_strategy"] = "static_smart"
    info["smoothing_applied"] = det.get("samples_with_face", 0) >= 2
    crop = f"scale={sw}:{sh},crop={out_w}:{out_h}:x={x}:y={y}"
    return crop, info
