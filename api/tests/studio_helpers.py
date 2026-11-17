"""Gemeinsame Helfer der Studio-Tests (keine Tests in dieser Datei)."""

from __future__ import annotations

import math
import os
import struct
import subprocess
import sys
import time
import wave

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
# Tests laufen ohne Token-Pflicht; test_studio_hardening.py prüft sie gezielt.
os.environ.setdefault("CLIPFORGE_API_AUTH", "off")

ENV_KEYS = ("CLIPFORGE_JOBS_DIR", "CLIPFORGE_STUDIO_DIR", "CLIPFORGE_FLAG_STUDIO_MOCK_PROVIDERS",
            "CLIPFORGE_BRAND_KIT_PATH", "CLIPFORGE_STUDIO_WORKER")


def set_env(tmp: str, **extra) -> None:
    os.environ["CLIPFORGE_JOBS_DIR"] = os.path.join(tmp, "jobs")
    os.environ["CLIPFORGE_STUDIO_DIR"] = os.path.join(tmp, "studio")
    os.environ["CLIPFORGE_FLAG_STUDIO_MOCK_PROVIDERS"] = "true"
    os.environ["CLIPFORGE_STUDIO_WORKER"] = "off"
    for k, v in extra.items():
        os.environ[k] = str(v)


def clear_env(*extra) -> None:
    for k in (*ENV_KEYS, *extra):
        os.environ.pop(k, None)


def make_client(tmp: str, **extra):
    """Frische App-Instanz mit isolierten Ordnern + Mock-Providern."""
    set_env(tmp, **extra)
    for mod in ("app", "studio_routes"):
        sys.modules.pop(mod, None)
    from fastapi.testclient import TestClient
    import app as app_module
    return TestClient(app_module.app), app_module


def make_service(tmp: str, **extra):
    set_env(tmp, **extra)
    from clipforge.studio.service import StudioService
    from jobs import JobRegistry
    registry = JobRegistry(os.environ["CLIPFORGE_JOBS_DIR"])
    return StudioService(registry=registry), registry


def wait_task(client, task_id: str, timeout: float = 120.0) -> dict:
    deadline = time.time() + timeout
    while True:
        task = client.get(f"/api/studio/tasks/{task_id}").json()
        if task["status"] not in ("queued", "running"):
            return task
        assert time.time() < deadline, f"Task {task_id} hängt: {task}"
        time.sleep(0.05)


def make_click_wav(path: str, seconds: float = 8.0, bpm: float = 120.0) -> str:
    """Synthetischer Klick-Track mit exakt bekanntem Tempo."""
    rate = 22050
    period = 60.0 / bpm
    frames = bytearray()
    for n in range(int(rate * seconds)):
        t = n / rate
        phase = t % period
        amp = math.exp(-phase * 60.0) * math.sin(2 * math.pi * 1000 * t) if phase < 0.08 else 0.0
        frames += struct.pack("<h", int(20000 * amp))
    with wave.open(path, "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(rate)
        wf.writeframes(bytes(frames))
    return path


def make_tone_wav(path: str, seconds: float = 3.0) -> str:
    rate = 22050
    frames = bytearray()
    for n in range(int(rate * seconds)):
        frames += struct.pack("<h", int(8000 * math.sin(2 * math.pi * 300 * n / rate)))
    with wave.open(path, "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(rate)
        wf.writeframes(bytes(frames))
    return path


def make_video(path: str, seconds: float = 2.0, size: str = "320x240") -> str:
    subprocess.run(
        ["ffmpeg", "-y", "-v", "error", "-f", "lavfi", "-i",
         f"testsrc=s={size}:d={seconds}:r=15", "-f", "lavfi", "-i",
         f"sine=f=440:d={seconds}", "-shortest", "-c:v", "libx264", "-preset", "ultrafast",
         "-pix_fmt", "yuv420p", "-c:a", "aac", path], check=True)
    return path


def make_png(path: str, size: str = "320x480") -> str:
    subprocess.run(["ffmpeg", "-y", "-v", "error", "-f", "lavfi", "-i",
                    f"color=c=red:s={size}:d=1", "-frames:v", "1", path], check=True)
    return path


def make_pdf(lines: list[str]) -> bytes:
    """Minimal gültiges Text-PDF (ASCII), ohne Fremdbibliothek erzeugt."""
    def esc(s: str) -> str:
        return s.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")
    content = "BT /F1 12 Tf 72 720 Td 14 TL " + " ".join(
        f"({esc(line)}) Tj T*" for line in lines) + " ET"
    objs = [
        "<< /Type /Catalog /Pages 2 0 R >>",
        "<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
        "<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] /Contents 4 0 R "
        "/Resources << /Font << /F1 5 0 R >> >> >>",
        f"<< /Length {len(content)} >>\nstream\n{content}\nendstream",
        "<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>",
    ]
    out = b"%PDF-1.4\n"
    offsets = []
    for i, obj in enumerate(objs, start=1):
        offsets.append(len(out))
        out += f"{i} 0 obj\n{obj}\nendobj\n".encode("latin-1")
    xref = len(out)
    out += f"xref\n0 {len(objs) + 1}\n".encode()
    out += b"0000000000 65535 f \n"
    for off in offsets:
        out += f"{off:010d} 00000 n \n".encode()
    out += f"trailer\n<< /Size {len(objs) + 1} /Root 1 0 R >>\nstartxref\n{xref}\n%%EOF\n".encode()
    return out


def ffprobe(path: str) -> dict:
    import json
    out = subprocess.run(
        ["ffprobe", "-v", "error", "-print_format", "json", "-show_format", "-show_streams", path],
        capture_output=True, text=True, check=True)
    return json.loads(out.stdout)


def run_all(namespace: dict) -> None:
    fns = [v for k, v in sorted(namespace.items()) if k.startswith("test_") and callable(v)]
    for fn in fns:
        fn()
        print(f"  ✓ {fn.__name__}")
    print(f"\n{len(fns)} Tests bestanden.")
