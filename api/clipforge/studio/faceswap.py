"""Autorisierter Face Swap für Bilder und Videos.

Schutzmaßnahmen (nicht abschaltbar):
1. Eingesetzt werden NUR Gesichter, die vorher als Referenz registriert
   wurden — mit Einwilligungserklärung (eigenes Gesicht oder schriftliche
   Erlaubnis der Person, deren Name gespeichert wird) und der Zusicherung,
   niemanden zu täuschen. Ein beliebiges Foto lässt sich nicht einsetzen.
2. Lokale Gesichtsprüfung (YuNet + SFace, OpenCV, MIT/Apache-2.0):
   Referenzfoto muss genau EIN Gesicht zeigen; vor jedem Swap wird geprüft,
   dass das Quellbild zur registrierten Referenz passt (Kosinus ≥ 0,363,
   Empfehlung der SFace-Autoren).
3. Jedes Ergebnis trägt sichtbar „KI-verändert (Face Swap)“; ein Projekt,
   das so ein Ergebnis nutzt, bekommt dieselbe dauerhafte Kennzeichnung.
4. Protokoll jeder Nutzung (Zeit, Benutzer, Referenz, Ziel, Prüfsummen).
5. Online-Betrieb: nur nach ausdrücklicher Freischaltung durch den Betreiber
   (CLIPFORGE_FACE_SWAP_ONLINE=1).

Grenzen (ehrlich): Ob ein Referenzgesicht wirklich dem Benutzer gehört,
kann Software nicht beweisen — die Erklärung wird protokolliert.

Swap-Engine: fal.ai (kostenpflichtig, Modell per Umgebungsvariable). Die
Feldnamen der Modelle konnten während der Entwicklung NICHT gegen die
Dokumentation geprüft werden → live ungetestet. Lokale Swap-Modelle
(z. B. inswapper) sind nicht kommerziell lizenziert und daher nicht eingebaut.
"""

from __future__ import annotations

import hashlib
import os
import subprocess

import numpy as np

from .errors import ProviderError, StudioError
from .models import model_path
from .storage import new_id, now_iso, read_json, studio_dir, write_json_atomic

MATCH_THRESHOLD = 0.363
LABEL = "KI-verändert (Face Swap)"
CONSENT_TEXT = {
    "own": "Das ist mein eigenes Gesicht.",
    "permission": "Ich habe die ausdrückliche Erlaubnis der abgebildeten Person.",
}
NO_DECEPTION = ("Ich verwende das Ergebnis nicht, um über die Identität einer Person zu "
                "täuschen, und kennzeichne es als KI-verändert.")
PRICE_IMAGE_USD = float(os.environ.get("CLIPFORGE_FACESWAP_IMAGE_USD", "0.05"))
PRICE_VIDEO_PER_S_USD = float(os.environ.get("CLIPFORGE_FACESWAP_VIDEO_USD_PER_S", "0.10"))


def enabled() -> tuple[bool, str]:
    from ..auth import accounts_mode
    if accounts_mode() and os.environ.get("CLIPFORGE_FACE_SWAP_ONLINE") != "1":
        return False, ("Face Swap ist im Online-Betrieb gesperrt, bis der Betreiber ihn "
                       "ausdrücklich freischaltet (CLIPFORGE_FACE_SWAP_ONLINE=1).")
    return True, ""


def _require_enabled() -> None:
    ok, why = enabled()
    if not ok:
        raise StudioError("feature_disabled", why, 403)


# ------------------------------------------------------- lokale Gesichtsprüfung
def _cv2():
    import cv2
    return cv2


def _models():
    det, rec = model_path("face_detect"), model_path("face_verify")
    if not det or not rec:
        raise StudioError("model_missing",
                          "Für die Gesichtsprüfung zuerst die Modelle „Gesichtserkennung“ und "
                          "„Gesichtsabgleich“ laden (Studio → Einrichtung → Lokale KI-Modelle).",
                          409, details={"models": ["face_detect", "face_verify"]})
    return det, rec


def faces_in(img) -> list:
    """→ YuNet-Treffer (Zeilen: Box, 5 Landmarken, Score)."""
    cv2 = _cv2()
    det, _ = _models()
    h, w = img.shape[:2]
    scale = min(1.0, 1280 / max(h, w))
    if scale < 1.0:
        img = cv2.resize(img, (int(w * scale), int(h * scale)))
    detector = cv2.FaceDetectorYN.create(det, "", (img.shape[1], img.shape[0]), 0.8, 0.3, 5000)
    _, found = detector.detect(img)
    if found is None:
        return []
    out = []
    for row in found:
        row = row.copy()
        row[:14] = row[:14] / scale
        out.append(row)
    return out


def embedding(img, face) -> np.ndarray:
    cv2 = _cv2()
    _, rec = _models()
    recognizer = cv2.FaceRecognizerSF.create(rec, "")
    aligned = recognizer.alignCrop(img, face)
    feat = recognizer.feature(aligned).flatten().astype(np.float32)
    return feat / (np.linalg.norm(feat) + 1e-9)


def similarity(a, b) -> float:
    return float(np.dot(np.asarray(a, np.float32), np.asarray(b, np.float32)))


def _read(path: str):
    img = _cv2().imread(path, _cv2().IMREAD_COLOR)
    if img is None:
        raise StudioError("file_unreadable", "Bild konnte nicht gelesen werden.", 415)
    return img


# --------------------------------------------------------- Referenzgesichter
def _dir() -> str:
    path = os.path.join(studio_dir(), "faces")
    os.makedirs(path, exist_ok=True)
    return path


def list_faces() -> list[dict]:
    data = read_json(os.path.join(_dir(), "faces.json"), [])
    return [{k: v for k, v in f.items() if k != "embedding"} for f in data] if isinstance(data, list) else []


def _all() -> list[dict]:
    data = read_json(os.path.join(_dir(), "faces.json"), [])
    return data if isinstance(data, list) else []


def register_face(image_path: str, *, name: str, basis: str, person: str,
                  no_deception: bool, user: str | None) -> dict:
    _require_enabled()
    name = " ".join((name or "").split())[:60]
    person = " ".join((person or "").split())[:80]
    if not name:
        raise StudioError("validation_error", "Bitte einen Namen für das Referenzgesicht angeben.")
    if basis not in CONSENT_TEXT:
        raise StudioError("consent_required", "Bitte angeben: eigenes Gesicht oder Erlaubnis der Person.")
    if basis == "permission" and len(person) < 3:
        raise StudioError("consent_required", "Bitte den Namen der Person angeben, die zugestimmt hat.")
    if not no_deception:
        raise StudioError("consent_required", "Bitte die Erklärung zur Nicht-Täuschung bestätigen.")
    img = _read(image_path)
    found = faces_in(img)
    if len(found) != 1:
        raise StudioError("face_count",
                          "Das Referenzfoto muss genau ein deutlich erkennbares Gesicht zeigen "
                          f"(gefunden: {len(found)}).", 422)
    fid = new_id()
    with open(image_path, "rb") as fh:
        digest = hashlib.sha256(fh.read()).hexdigest()
    dest = os.path.join(_dir(), f"{fid}.png")
    _cv2().imwrite(dest, img)
    record = {"id": fid, "name": name, "created_at": now_iso(), "file": f"{fid}.png",
              "embedding": embedding(img, found[0]).round(6).tolist(),
              "consent": {"basis": basis, "person": person if basis == "permission" else "eigenes Gesicht",
                          "statement": CONSENT_TEXT[basis], "no_deception": NO_DECEPTION,
                          "confirmed_at": now_iso(), "confirmed_by": user or "lokal",
                          "image_sha256": digest}}
    faces = _all()
    faces.append(record)
    write_json_atomic(os.path.join(_dir(), "faces.json"), faces)
    _log({"event": "face_registered", "face": fid, "user": user, "basis": basis})
    return {k: v for k, v in record.items() if k != "embedding"}


def delete_face(fid: str) -> None:
    faces = _all()
    kept = [f for f in faces if f["id"] != fid]
    if len(kept) == len(faces):
        raise StudioError("face_not_found", "Referenzgesicht nicht gefunden.", 404)
    write_json_atomic(os.path.join(_dir(), "faces.json"), kept)
    try:
        os.remove(os.path.join(_dir(), f"{fid}.png"))
    except OSError:
        pass
    _log({"event": "face_deleted", "face": fid})


def get_face(fid: str) -> dict:
    for f in _all():
        if f["id"] == fid:
            return f
    raise StudioError("face_not_found", "Referenzgesicht nicht gefunden.", 404)


def verify_reference(fid: str) -> dict:
    """Prüft vor jedem Swap erneut: Referenzdatei unverändert und genau ein
    passendes Gesicht (verhindert ausgetauschte Dateien)."""
    face = get_face(fid)
    path = os.path.join(_dir(), face["file"])
    img = _read(path)
    found = faces_in(img)
    if len(found) != 1:
        raise StudioError("face_check_failed", "Referenzbild ist nicht mehr eindeutig.", 409)
    score = similarity(embedding(img, found[0]), face["embedding"])
    if score < MATCH_THRESHOLD:
        raise StudioError("face_check_failed", "Referenzbild passt nicht zur registrierten Person.", 409)
    return {"face": face, "path": path, "score": round(score, 3)}


def target_faces(path: str, is_video: bool) -> int:
    """Anzahl Gesichter im Ziel (bei Videos: erstes Bild)."""
    cv2 = _cv2()
    if is_video:
        cap = cv2.VideoCapture(path)
        ok, frame = cap.read()
        cap.release()
        if not ok:
            raise StudioError("file_unreadable", "Video konnte nicht gelesen werden.", 415)
        return len(faces_in(frame))
    return len(faces_in(_read(path)))


# ------------------------------------------------------------- Protokoll
def _log(entry: dict) -> None:
    path = os.path.join(_dir(), "audit.jsonl")
    import json
    with open(path, "a", encoding="utf-8") as fh:
        fh.write(json.dumps({"at": now_iso(), **entry}, ensure_ascii=False) + "\n")


def audit() -> list[dict]:
    import json
    path = os.path.join(_dir(), "audit.jsonl")
    if not os.path.exists(path):
        return []
    with open(path, encoding="utf-8") as fh:
        return [json.loads(line) for line in fh if line.strip()][-200:]


# --------------------------------------------------------- Kennzeichnung
def label_image(path: str) -> None:
    cv2 = _cv2()
    img = _read(path)
    h, w = img.shape[:2]
    scale = max(0.5, w / 1400)
    (tw, th), base = cv2.getTextSize(LABEL.replace("ä", "ae"), cv2.FONT_HERSHEY_SIMPLEX, scale, 2)
    x, y = w - tw - int(16 * scale), int(16 * scale) + th
    cv2.rectangle(img, (x - 8, y - th - 8), (x + tw + 8, y + base + 4), (0, 0, 0), -1)
    cv2.putText(img, LABEL.replace("ä", "ae"), (x, y), cv2.FONT_HERSHEY_SIMPLEX, scale,
                (255, 255, 255), 2, cv2.LINE_AA)
    cv2.imwrite(path, img)


def label_video(src: str, out: str) -> None:
    from ..ffmpeg_utils import filter_path
    import tempfile
    with tempfile.TemporaryDirectory() as tmp:
        ass = os.path.join(tmp, "label.ass")
        with open(ass, "w", encoding="utf-8") as fh:
            fh.write("[Script Info]\nScriptType: v4.00+\nPlayResX: 1080\nPlayResY: 1920\n\n"
                     "[V4+ Styles]\nFormat: Name, Fontname, Fontsize, PrimaryColour, BackColour, "
                     "BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV\n"
                     "Style: L,Arial,44,&H00FFFFFF,&H80000000,3,2,0,9,30,30,40\n\n"
                     "[Events]\nFormat: Layer, Start, End, Style, Text\n"
                     f"Dialogue: 0,0:00:00.00,9:59:59.00,L,{LABEL}\n")
        cmd = ["ffmpeg", "-y", "-v", "error", "-i", src, "-vf", f"ass={filter_path(ass)}",
               "-c:v", "libx264", "-preset", "veryfast", "-crf", "20", "-pix_fmt", "yuv420p",
               "-c:a", "copy", "-movflags", "+faststart", out]
        res = subprocess.run(cmd, capture_output=True, text=True, timeout=1800)
        if res.returncode != 0:
            raise StudioError("render_failed", "Kennzeichnung konnte nicht eingebrannt werden.", 500)


# ---------------------------------------------------------------- Engine
def _engine_model(is_video: bool) -> str:
    return os.environ.get("CLIPFORGE_FAL_FACESWAP_VIDEO_MODEL" if is_video else
                          "CLIPFORGE_FAL_FACESWAP_IMAGE_MODEL",
                          "fal-ai/pixverse/swap" if is_video else "easel-ai/advanced-face-swap")


def _fields(is_video: bool) -> tuple[str, str]:
    """(Feld fürs Ziel, Feld fürs Gesicht) — per Umgebung anpassbar, da die
    Modell-Schemata nicht verifiziert werden konnten."""
    if is_video:
        return (os.environ.get("CLIPFORGE_FAL_FACESWAP_VIDEO_TARGET_FIELD", "video_url"),
                os.environ.get("CLIPFORGE_FAL_FACESWAP_VIDEO_FACE_FIELD", "image_url"))
    return (os.environ.get("CLIPFORGE_FAL_FACESWAP_IMAGE_TARGET_FIELD", "target_image"),
            os.environ.get("CLIPFORGE_FAL_FACESWAP_IMAGE_FACE_FIELD", "face_image_0"))


def estimate(is_video: bool, seconds: float = 0.0) -> float:
    return round(PRICE_VIDEO_PER_S_USD * max(1.0, seconds), 2) if is_video else PRICE_IMAGE_USD


def run_swap(face_path: str, target_path: str, out_path: str, is_video: bool,
             should_cancel=None) -> None:
    from .credentials import secret
    from .providers import fal
    if not secret("FAL_KEY"):
        raise StudioError("credential_not_set", "Für Face Swap wird ein FAL_KEY benötigt.", 409)
    target_field, face_field = _fields(is_video)
    payload = {target_field: fal.data_uri(target_path), face_field: fal.data_uri(face_path)}
    try:
        result = fal.run(_engine_model(is_video), payload, should_cancel=should_cancel)
    except ProviderError as exc:
        raise StudioError("provider_failed", f"Face Swap fehlgeschlagen: {exc}", 502) from exc
    key = "video" if is_video else "image"
    item = result.get(key) or (result.get("images") or [None])[0]
    url = item.get("url") if isinstance(item, dict) else None
    if not isinstance(url, str) or not url.startswith("https://"):
        raise StudioError("provider_failed", "Antwort enthält kein Ergebnis.", 502)
    from .safe_fetch import fetch
    res = fetch(url, allowed_types=("video/mp4", "image/png", "image/jpeg", "image/webp",
                                    "application/octet-stream"),
                max_bytes=500 * 1024 * 1024, timeout=300, **fal.DOWNLOAD_KWARGS)
    with open(out_path, "wb") as fh:
        fh.write(res.body)
