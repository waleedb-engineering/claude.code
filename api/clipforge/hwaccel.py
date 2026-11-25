"""Hardware-Videoencoder: erkennen, wirklich testen, messen — und nur nutzen, wenn erlaubt.

Dass FFmpeg einen Encoder *kennt* (z. B. h264_nvenc), heißt nicht, dass eine
passende GPU da ist. Deshalb wird jeder Kandidat mit einem kurzen echten
Kodierlauf geprüft. Genutzt wird Hardware-Kodierung nur, wenn
``CLIPFORGE_HWACCEL`` ausdrücklich gesetzt ist (``auto`` oder ein Encoder-Name);
Standard ist CPU (libx264) — gleiche Qualität auf allen Systemen.

Qualitäts-Abbildung: CRF (libx264) → konstante Qualität des jeweiligen Encoders
(NVENC ``-cq``, QSV ``-global_quality``, VideoToolbox ``-q:v``, VAAPI ``-qp``).
"""

from __future__ import annotations

import os
import subprocess
import tempfile
import time
from functools import lru_cache

CANDIDATES = [
    ("h264_videotoolbox", "Apple VideoToolbox"),
    ("h264_nvenc", "NVIDIA NVENC"),
    ("h264_qsv", "Intel Quick Sync"),
    ("h264_vaapi", "VAAPI (Linux)"),
]


def _listed() -> set[str]:
    try:
        out = subprocess.run(["ffmpeg", "-hide_banner", "-encoders"], capture_output=True, text=True,
                             timeout=20).stdout
    except (OSError, subprocess.SubprocessError):
        return set()
    return {line.split()[1] for line in out.splitlines() if len(line.split()) > 1 and line.startswith(" V")}


def quality_args(encoder: str, crf: str | int) -> list[str]:
    q = str(crf)
    if encoder == "h264_nvenc":
        return ["-c:v", encoder, "-preset", "p5", "-rc", "vbr", "-cq", q, "-b:v", "0"]
    if encoder == "h264_qsv":
        return ["-c:v", encoder, "-global_quality", q]
    if encoder == "h264_videotoolbox":
        # VideoToolbox: -q:v 1–100 (höher = besser); CRF 18–30 grob abbilden
        return ["-c:v", encoder, "-q:v", str(max(30, min(85, 115 - int(q) * 2)))]
    if encoder == "h264_vaapi":
        return ["-c:v", encoder, "-qp", q]
    return ["-c:v", "libx264", "-crf", q]


def input_args(encoder: str) -> list[str]:
    """Globale Optionen, die VOR den Eingaben stehen müssen."""
    return ["-vaapi_device", "/dev/dri/renderD128"] if encoder == "h264_vaapi" else []


def encode_args(preset: str, crf: str | int) -> list[str]:
    """Video-Encoder-Argumente für Renderer: CPU wie bisher, sonst gewählte Hardware."""
    enc = selected_encoder()
    if enc == "libx264":
        return ["-c:v", "libx264", "-preset", preset, "-crf", str(crf)]
    return quality_args(enc, crf)


def _trial(encoder: str, seconds: int = 1, size: str = "640x360") -> tuple[bool, float, str]:
    with tempfile.TemporaryDirectory() as tmp:
        out = os.path.join(tmp, "t.mp4")
        vf = ["-vf", "format=nv12,hwupload"] if encoder == "h264_vaapi" else []
        pix = [] if encoder == "h264_vaapi" else ["-pix_fmt", "yuv420p"]
        cmd = ["ffmpeg", "-y", "-v", "error", *input_args(encoder), "-f", "lavfi", "-i",
               f"testsrc2=s={size}:r=30:d={seconds}", *vf, *quality_args(encoder, 23), *pix, out]
        t0 = time.perf_counter()
        try:
            r = subprocess.run(cmd, capture_output=True, text=True, timeout=60)
        except (OSError, subprocess.SubprocessError) as exc:
            return False, 0.0, type(exc).__name__
        dt = time.perf_counter() - t0
        ok = r.returncode == 0 and os.path.exists(out) and os.path.getsize(out) > 1000
        return ok, dt, "" if ok else (r.stderr.strip().splitlines() or ["Fehler"])[-1][:160]


@lru_cache(maxsize=1)
def detect() -> dict:
    """→ {listed, working: [..], details: {encoder: {ok, error}}} — einmal je Prozess."""
    listed = _listed()
    details, working = {}, []
    for enc, label in CANDIDATES:
        if enc not in listed:
            details[enc] = {"label": label, "listed": False, "ok": False, "error": "nicht im FFmpeg-Build"}
            continue
        ok, _, err = _trial(enc)
        details[enc] = {"label": label, "listed": True, "ok": ok, "error": err or None}
        if ok:
            working.append(enc)
    return {"working": working, "details": details, "cpu": "libx264"}


def selected_encoder() -> str:
    """Encoder laut CLIPFORGE_HWACCEL (Standard: CPU). Nicht funktionierende Wahl → CPU."""
    want = os.environ.get("CLIPFORGE_HWACCEL", "off").strip().lower()
    if want in ("", "off", "cpu", "libx264", "0", "false"):
        return "libx264"
    working = detect()["working"]
    if want == "auto":
        return working[0] if working else "libx264"
    return want if want in working else "libx264"


def benchmark(seconds: int = 10, size: str = "1920x1080") -> list[dict]:
    """Echte Messung: CPU gegen jeden funktionierenden Hardware-Encoder."""
    out = []
    for enc in ["libx264", *detect()["working"]]:
        ok, dt, err = _trial(enc, seconds, size)
        out.append({"encoder": enc, "ok": ok, "seconds": round(dt, 2),
                    "realtime_factor": round(seconds / dt, 2) if ok and dt else None, "error": err or None})
    return out
