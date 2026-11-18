#!/usr/bin/env python3
"""ClipForge Creator Studio — lokaler End-to-End-Smoke-Test.

Startet ein echtes Backend (uvicorn) mit Mock-Providern in einem temporären
Ordner und fährt den kompletten Weg über die CLI:

    create (Skript) → render (final) → export → Download → ffprobe
    + Automation anlegen → einmal ausführen → Entwurf prüfen (nie veröffentlicht)

Kein Netz, keine Zugangsdaten, keine Kosten. Exit-Code 0 = alles bestanden.

    python3 scripts/studio_smoke.py [--keep] [--out=/pfad/video.mp4]
"""

from __future__ import annotations

import json
import os
import shutil
import socket
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.request

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
API_DIR = os.path.join(ROOT, "api")
SCRIPT = ("Lokale Videotools sparen Zeit und Geld. Alles bleibt auf deinem Rechner. "
          "Jede Szene bleibt bearbeitbar. Folge für mehr.")


def free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def cli(base: str, *args: str) -> dict:
    proc = subprocess.run(
        [sys.executable, "-m", "clipforge.studio.cli", "--api", base, *args],
        cwd=API_DIR, capture_output=True, text=True, env={**os.environ, "PYTHONPATH": API_DIR})
    try:
        data = json.loads(proc.stdout)
    except ValueError:
        raise SystemExit(f"CLI lieferte kein JSON ({args}):\n{proc.stdout}\n{proc.stderr}")
    if proc.returncode != 0:
        raise SystemExit(f"CLI-Fehler ({args}): {json.dumps(data, ensure_ascii=False)}")
    return data


def get(base: str, path: str) -> dict:
    with urllib.request.urlopen(base + path, timeout=30) as resp:  # noqa: S310 — lokal
        return json.loads(resp.read().decode("utf-8"))


def check(label: str, ok: bool, detail: str = "") -> None:
    print(f"  {'✓' if ok else '✗'} {label}{' — ' + detail if detail else ''}")
    if not ok:
        raise SystemExit(f"SMOKE FEHLGESCHLAGEN: {label}")


def main() -> int:
    keep = "--keep" in sys.argv
    tmp = tempfile.mkdtemp(prefix="clipforge_smoke_")
    port = free_port()
    base = f"http://127.0.0.1:{port}"
    env = {**os.environ, "PYTHONPATH": API_DIR,
           "CLIPFORGE_JOBS_DIR": os.path.join(tmp, "jobs"),
           "CLIPFORGE_STUDIO_DIR": os.path.join(tmp, "studio"),
           "CLIPFORGE_BRAND_KIT_PATH": os.path.join(tmp, "brand_kit.json"),
           "CLIPFORGE_FLAG_STUDIO_MOCK_PROVIDERS": "true",
           "CLIPFORGE_ENV_FILE": os.path.join(tmp, "smoke.env"),
           "CLIPFORGE_API_TOKEN_FILE": os.path.join(tmp, "api_token"),
           "CLIPFORGE_API_AUTH": "on",
           "CLIPFORGE_ENABLE_YOUTUBE_UPLOAD": "false"}
    env.pop("CLIPFORGE_API_TOKEN", None)
    log = open(os.path.join(tmp, "backend.log"), "w")
    server = subprocess.Popen(
        [sys.executable, "-m", "uvicorn", "app:app", "--host", "127.0.0.1", "--port", str(port)],
        cwd=API_DIR, env=env, stdout=log, stderr=subprocess.STDOUT)
    try:
        for _ in range(100):
            try:
                get(base, "/health")
                break
            except OSError:
                time.sleep(0.2)
        else:
            raise SystemExit("Backend startet nicht (siehe backend.log).")
        print(f"Backend läuft auf {base} (Daten: {tmp})")

        print("\n1) Projekt aus Skript")
        created = cli(base, "create", "--workflow", "script", "--title", "Smoke", "--script", SCRIPT,
                      "--voice", "auto", "--captions", "dynamic", "--resolution", "720p", "--wait")
        pid = created["project_id"]
        check("Projekt angelegt + Szenen erzeugt", created["ingest"]["status"] == "succeeded", pid)
        status = cli(base, "status", pid)
        check("Status bereit", status["status"] == "ready" and status["scenes"] >= 2,
              f"{status['scenes']} Szenen")

        print("\n2) Finaler Render (echtes FFmpeg, lokale Stimme)")
        render = cli(base, "render", pid, "--wait")
        check("Render erfolgreich", render["task"]["status"] == "succeeded")
        check("Qualitätsprüfung bestanden", render["task"]["result"]["quality_passed"] is True)

        print("\n3) Export + ffprobe")
        out = os.path.join(tmp, "smoke.mp4")
        export = cli(base, "export", pid, "--download", out)
        check("Export an Publishing-Planner", bool(export["job_id"]), export["job_id"])
        probe = json.loads(subprocess.run(
            ["ffprobe", "-v", "error", "-print_format", "json", "-show_format", "-show_streams", out],
            capture_output=True, text=True, check=True).stdout)
        video = next(s for s in probe["streams"] if s["codec_type"] == "video")
        audio = next((s for s in probe["streams"] if s["codec_type"] == "audio"), None)
        duration = float(probe["format"]["duration"])
        check("Video 720x1280 H.264 yuv420p",
              (video["width"], video["height"], video["codec_name"], video["pix_fmt"])
              == (720, 1280, "h264", "yuv420p"))
        check("Tonspur AAC vorhanden", audio is not None and audio["codec_name"] == "aac")
        check("Dauer plausibel", 4.0 < duration < 60.0, f"{duration:.1f}s")
        check("Datei nicht leer", os.path.getsize(out) > 20_000, f"{os.path.getsize(out)} Bytes")
        again = cli(base, "export", pid)
        check("Export ist idempotent", again["job_id"] == export["job_id"] and again["already_exported"])

        print("\n4) Automation (einmaliger Lauf, nur Entwurf)")
        auto = cli(base, "automation", "create", "--name", "Smoke-Automation", "--workflow", "script",
                   "--item", SCRIPT, "--frequency", "daily", "--time", "09:00",
                   "--draft-platform", "tiktok")
        check("Automation mit nächstem Lauf", bool(auto["next_run_at"]), auto["next_run_at"])
        run = cli(base, "automation", "run", auto["id"])
        for _ in range(240):
            task = get(base, f"/api/studio/tasks/{run['task_id']}")
            if task["status"] not in ("queued", "running"):
                break
            time.sleep(0.5)
        check("Automationslauf erfolgreich", task["status"] == "succeeded", str(task.get("error") or ""))
        drafts = get(base, "/api/studio/publishing/drafts")["drafts"]
        check("Genau ein Entwurf, nichts veröffentlicht",
              len(drafts) == 1 and drafts[0]["status"] == "draft" and drafts[0]["published_at"] is None)
        analytics = get(base, "/api/studio/analytics")
        check("Analytics ohne erfundene Werte", analytics["rows"] == [])

        noauth = urllib.request.Request(
            base + "/api/studio/projects", method="POST",
            data=json.dumps({"workflow": "script", "script": SCRIPT}).encode(),
            headers={"Content-Type": "application/json"})
        try:
            urllib.request.urlopen(noauth, timeout=10)  # noqa: S310 — lokal
            status_code = 200
        except urllib.error.HTTPError as exc:
            status_code = exc.code
        check("Mutation ohne API-Token wird abgewiesen", status_code == 401, f"HTTP {status_code}")

        print("\nSTUDIO SMOKE PASSED")
        target = next((a.split("=", 1)[1] for a in sys.argv if a.startswith("--out=")), None)
        if target:
            shutil.copyfile(out, target)
            print(f"Testvideo: {os.path.abspath(target)}")
        elif keep:
            print(f"Testvideo: {out}")
        return 0
    finally:
        server.terminate()
        try:
            server.wait(timeout=10)
        except subprocess.TimeoutExpired:
            server.kill()
        log.close()
        if not keep:
            shutil.rmtree(tmp, ignore_errors=True)


if __name__ == "__main__":
    sys.exit(main())
