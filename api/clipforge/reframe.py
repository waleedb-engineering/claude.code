"""Smart 9:16 Reframe — statischer Fokus oder dynamisches Gesichts-Tracking.

Modi: center · smart/face (fester Fokus = Median der Gesichtsmitten) ·
track (Gesicht über die Zeit verfolgen, Ausreißer/Totzone/Tempolimit, Crop
als stückweise lineare Kamerafahrt) · manual (eigene Fokuspunkte).
Detektor: YuNet (falls installiert), sonst OpenCV-Haar; OpenCV 5 hat keine
Haar-Kaskaden mehr (requirements: <5). Ältere Beschreibung des statischen Wegs:

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

    Nutzt dieselbe Detektorkette wie das Tracking (YuNet, falls installiert,
    sonst OpenCV-Haar). Liefert detection_method, frames_analyzed,
    faces_detected_count, focus_frac (Median der Gesichtsmitten oder None),
    samples_with_face. Wirft nie — bei jedem Problem focus_frac=None.
    """
    info = {"detection_method": "unavailable", "frames_analyzed": 0, "faces_detected_count": 0,
            "focus_frac": None, "samples_with_face": 0}
    try:
        tr = track_faces(video_path, start, end, step=sample_step, max_samples=max_samples)
    except Exception:  # noqa: BLE001
        return info
    info["detection_method"] = tr["method"]
    info["frames_analyzed"] = len(tr["samples"])
    fracs = sorted(x for _, x, _ in tr["samples"] if x is not None)
    info["faces_detected_count"] = len(fracs)
    if fracs:
        info["focus_frac"] = round(fracs[len(fracs) // 2], 4)
        info["samples_with_face"] = len(fracs)
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
    manual_points: list | None = None,
) -> tuple[str, dict]:
    """Plant den Crop. Gibt (video_crop_filter, reframe_info) zurück.

    mode: 'center' | 'smart' | 'face' (statischer Fokus) | 'track' (Gesicht
    verfolgen, geglättet) | 'manual' (eigene Fokuspunkte [(t, x)]). Bei jedem
    Problem → statischer Smart-Crop bzw. Center-Fallback.
    """
    requested = mode if mode in ("center", "smart", "face", "track", "manual") else "smart"
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

    if requested in ("track", "manual"):
        if requested == "manual" and not manual_points:
            info["fallback"] = True
            info["fallback_reason"] = "keine Fokuspunkte angegeben"
            return center_crop_filter(out_w, out_h), info
        flt, tinfo = plan_tracking(video_path, clip_start, clip_end, in_w, in_h, out_w, out_h,
                                   manual_points if requested == "manual" else None)
        info.update(tinfo)
        if flt:
            info.update(applied_mode=requested, crop_strategy="dynamic_track" if requested == "track"
                        else "manual_keyframes", smoothing_applied=requested == "track",
                        detection_method=tinfo.get("track_method"))
            return flt, info
        requested = "smart"  # Fallback: statischer Fokus (oder Mitte)
        info["fallback"] = True
        info["fallback_reason"] = tinfo.get("track_reason")

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


# ------------------------------------------------------------------ Tracking
# Dynamischer Zuschnitt: Gesicht über die Zeit verfolgen, glätten, Kamerafahrt
# als stückweise lineare Crop-Position. Der Crop sitzt im Filtergraphen VOR der
# Pausenentfernung (select/setpts) und rechnet in Quellzeit — Bild, Ton und
# Captions bleiben dadurch synchron.

TRACK_STEP = 0.5          # Abtastabstand (s)
MAX_PAN = 0.35            # max. Kamerafahrt in Bildbreiten je Sekunde (gegen Sprünge)
DEADZONE = 0.03           # kleinere Bewegungen werden ignoriert (kein Zittern)
HOLD = 2.0                # so lange wird bei verlorenem Gesicht die letzte Position gehalten
MIN_SPREAD = 0.06         # Tracking nur, wenn sich das Motiv merklich bewegt


def _yunet_path() -> str | None:
    env = os.environ.get("CLIPFORGE_YUNET_PATH")
    if env and os.path.isfile(env):
        return env
    try:
        from .studio.models import model_path
        return model_path("face_detect")
    except Exception:  # noqa: BLE001
        return None


def _detector():
    """→ (methode, detect(frame_bgr) -> [(cx_frac, cy_frac, fläche, konfidenz)]) oder (None, None)."""
    try:
        import cv2
    except Exception:  # noqa: BLE001
        return None, None
    yunet = _yunet_path()
    if yunet and hasattr(cv2, "FaceDetectorYN"):
        det = cv2.FaceDetectorYN.create(yunet, "", (320, 320), 0.7, 0.3, 50)

        def run(frame):
            h, w = frame.shape[:2]
            s = 640.0 / w if w > 640 else 1.0
            img = cv2.resize(frame, (int(w * s), int(h * s))) if s != 1.0 else frame
            det.setInputSize((img.shape[1], img.shape[0]))
            _, found = det.detect(img)
            out = []
            for r in (found if found is not None else []):
                x, y, fw, fh, conf = float(r[0]), float(r[1]), float(r[2]), float(r[3]), float(r[-1])
                out.append(((x + fw / 2) / img.shape[1], (y + fh / 2) / img.shape[0], fw * fh, conf))
            return out
        return "yunet", run
    if not hasattr(cv2, "CascadeClassifier") or not hasattr(cv2, "data"):
        return None, None  # z. B. OpenCV 5 ohne Haar-Kaskaden und ohne YuNet-Modell
    cascade = cv2.CascadeClassifier(os.path.join(cv2.data.haarcascades, CASCADE_NAME))
    if cascade.empty():
        return None, None

    def run_haar(frame):
        h, w = frame.shape[:2]
        s = 640.0 / w if w > 640 else 1.0
        small = cv2.resize(frame, (int(w * s), int(h * s))) if s != 1.0 else frame
        gray = cv2.cvtColor(small, cv2.COLOR_BGR2GRAY)
        faces = cascade.detectMultiScale(gray, scaleFactor=1.1, minNeighbors=5, minSize=(24, 24))
        return [((x + fw / 2) / small.shape[1], (y + fh / 2) / small.shape[0], float(fw * fh), 1.0)
                for x, y, fw, fh in faces]
    return "opencv_haar_frontalface", run_haar


def track_faces(video_path: str, start: float, end: float, *, step: float = TRACK_STEP,
                max_samples: int = 240) -> dict:
    """Gesichtsposition über die Zeit. → {method, samples: [(t_lokal, x_frac|None, konfidenz)]}.

    Motivbindung: nach dem ersten Treffer wird das Gesicht gewählt, das der
    letzten Position am nächsten liegt (bei gleicher Nähe das größere)."""
    method, detect = _detector()
    if detect is None:
        return {"method": "unavailable", "samples": []}
    import cv2
    cap = cv2.VideoCapture(video_path)
    if not cap.isOpened():
        return {"method": method, "samples": []}
    dur = max(0.0, end - start)
    n = max(1, min(max_samples, int(dur / step) + 1))
    samples, last = [], None
    try:
        for k in range(n):
            t = k * (dur / max(1, n - 1)) if n > 1 else 0.0
            cap.set(cv2.CAP_PROP_POS_MSEC, (start + t) * 1000.0)
            ok, frame = cap.read()
            if not ok or frame is None:
                samples.append((round(t, 3), None, 0.0))
                continue
            faces = detect(frame)
            if not faces:
                samples.append((round(t, 3), None, 0.0))
                continue
            if last is None:
                pick = max(faces, key=lambda f: f[2] * f[3])
            else:
                pick = min(faces, key=lambda f: (abs(f[0] - last) - 1e-9 * f[2]))
            last = pick[0]
            samples.append((round(t, 3), round(pick[0], 4), round(pick[3], 3)))
    finally:
        cap.release()
    return {"method": method, "samples": samples}


def smooth_track(samples: list[tuple], dur: float) -> list[tuple[float, float]]:
    """Lücken füllen (Halten, dann Mitte), Ausreißer per Median, Totzone, Tempolimit.

    → Stützpunkte [(t, x_frac)] für eine ruhige Kamerafahrt."""
    if not samples or all(x is None for _, x, _ in samples):
        return []
    filled, last, last_t = [], None, None
    for t, x, _ in samples:
        if x is not None:
            last, last_t = x, t
            filled.append((t, x))
        elif last is not None and t - last_t <= HOLD:
            filled.append((t, last))
        elif last is not None:
            filled.append((t, last))  # länger verloren: Position halten statt springen
    first = next(x for _, x, _ in samples if x is not None)
    if filled and filled[0][0] > 0:
        filled.insert(0, (0.0, first))
    xs = [x for _, x in filled]
    med = [sorted(xs[max(0, i - 2):i + 3])[len(xs[max(0, i - 2):i + 3]) // 2] for i in range(len(xs))]
    out = [(filled[0][0], med[0])]
    for (t, _), x in zip(filled[1:], med[1:]):
        pt, px = out[-1]
        if abs(x - px) < DEADZONE:
            x = px
        limit = MAX_PAN * max(1e-3, t - pt)
        x = px + max(-limit, min(limit, x - px))
        out.append((t, round(x, 4)))
    if out[-1][0] < dur:
        out.append((round(dur, 3), out[-1][1]))
    # Stützpunkte ausdünnen: nur Richtungswechsel/Knicke behalten (max. 40)
    keep = [out[0]]
    for i in range(1, len(out) - 1):
        a, b, c = keep[-1], out[i], out[i + 1]
        if c[0] - a[0] <= 0:
            continue
        lin = a[1] + (c[1] - a[1]) * (b[0] - a[0]) / (c[0] - a[0])
        if abs(lin - b[1]) > 0.004:
            keep.append(b)
    keep.append(out[-1])
    while len(keep) > 40:
        keep = keep[::2] + ([keep[-1]] if keep[-1] != keep[::2][-1] else [])
    return keep


def crop_x_expr(points: list[tuple[float, float]], sw: int, out_w: int) -> str:
    """Stückweise lineare Crop-x-Position (Quellzeit t) in Pixeln, begrenzt auf das Bild."""
    def px(f):
        return max(0, min(sw - out_w, f * sw - out_w / 2))
    expr = f"{px(points[-1][1]):.1f}"
    for (t0, x0), (t1, x1) in reversed(list(zip(points, points[1:]))):
        span = max(1e-3, t1 - t0)
        seg = f"({px(x0):.1f}+({px(x1) - px(x0):.1f})*(t-{t0:.3f})/{span:.3f})"
        expr = f"if(lt(t,{t1:.3f}),{seg},{expr})"
    return expr


def plan_tracking(video_path: str, clip_start: float, clip_end: float, in_w: int, in_h: int,
                  out_w: int, out_h: int, manual_points: list | None = None) -> tuple[str | None, dict]:
    """Dynamischer Crop. → (Filter oder None für statischen Fallback, Info)."""
    scale = max(out_w / in_w, out_h / in_h)
    sw, sh = max(out_w, _even(math.ceil(in_w * scale))), max(out_h, _even(math.ceil(in_h * scale)))
    y = max(0, (sh - out_h) // 2)
    dur = max(0.0, clip_end - clip_start)
    info = {"track_applied": False, "track_method": None, "track_points": 0, "track_confidence": None,
            "track_reason": None}
    if sw <= out_w:
        info["track_reason"] = "kein horizontaler Spielraum"
        return None, info
    if manual_points:
        pts = sorted((max(0.0, min(dur, float(t))), max(0.0, min(1.0, float(x)))) for t, x in manual_points)
        if pts[0][0] > 0:
            pts.insert(0, (0.0, pts[0][1]))
        if pts[-1][0] < dur:
            pts.append((dur, pts[-1][1]))
        info.update(track_applied=True, track_method="manual", track_points=len(pts))
        return f"scale={sw}:{sh},crop={out_w}:{out_h}:x='{crop_x_expr(pts, sw, out_w)}':y={y}", info
    tr = track_faces(video_path, clip_start, clip_end)
    info["track_method"] = tr["method"]
    found = [s for s in tr["samples"] if s[1] is not None]
    if not found:
        info["track_reason"] = "kein Gesicht verfolgt"
        return None, info
    info["track_confidence"] = round(sum(s[2] for s in found) / len(found), 3)
    info["track_coverage"] = round(len(found) / max(1, len(tr["samples"])), 3)
    pts = smooth_track(tr["samples"], dur)
    xs = [x for _, x in pts]
    if max(xs) - min(xs) < MIN_SPREAD:
        info["track_reason"] = "Motiv bewegt sich kaum — statischer Zuschnitt ist ruhiger"
        return None, info
    info.update(track_applied=True, track_points=len(pts))
    return f"scale={sw}:{sh},crop={out_w}:{out_h}:x='{crop_x_expr(pts, sw, out_w)}':y={y}", info
