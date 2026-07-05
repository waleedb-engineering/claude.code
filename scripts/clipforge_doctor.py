#!/usr/bin/env python3
"""ClipForge Environment Doctor.

Prüft, ob die lokale Umgebung für ClipForge bereit ist — ohne irgendetwas zu
verändern. Gibt für jede Prüfung PASS/WARN/FAIL aus und niemals Secret-Werte
(nur "configured: true/false").

Aufruf:
    python3 scripts/clipforge_doctor.py
"""

from __future__ import annotations

import importlib.util
import json
import os
import re
import shutil
import socket
import subprocess
import sys
from dataclasses import dataclass, field

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
API_DIR = os.path.join(REPO_ROOT, "api")
WEB_DIR = os.path.join(REPO_ROOT, "web")

MIN_PYTHON = (3, 10)
MIN_NODE_MAJOR = 20
MIN_NODE_MINOR = 9

PASS, WARN, FAIL = "PASS", "WARN", "FAIL"
ICON = {PASS: "✓", WARN: "!", FAIL: "✗"}


@dataclass
class Result:
    status: str
    label: str
    detail: str = ""


@dataclass
class Report:
    results: list[Result] = field(default_factory=list)

    def add(self, status: str, label: str, detail: str = "") -> None:
        self.results.append(Result(status, label, detail))

    @property
    def worst(self) -> str:
        statuses = {r.status for r in self.results}
        if FAIL in statuses:
            return FAIL
        if WARN in statuses:
            return WARN
        return PASS


def _run(cmd: list[str]) -> tuple[int, str]:
    try:
        p = subprocess.run(cmd, capture_output=True, text=True, timeout=10)
        return p.returncode, (p.stdout or p.stderr).strip()
    except (OSError, subprocess.TimeoutExpired):
        return 1, ""


def _port_in_use(port: int, host: str = "127.0.0.1") -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.settimeout(0.5)
        return s.connect_ex((host, port)) == 0


def check_python(report: Report) -> None:
    v = sys.version_info
    version_str = f"{v.major}.{v.minor}.{v.micro}"
    if (v.major, v.minor) >= MIN_PYTHON:
        report.add(PASS, "Python-Version", f"{version_str} (>= {'.'.join(map(str, MIN_PYTHON))})")
    else:
        report.add(
            FAIL,
            "Python-Version",
            f"{version_str} gefunden, mindestens {'.'.join(map(str, MIN_PYTHON))} erforderlich",
        )


def check_node(report: Report) -> None:
    node = shutil.which("node")
    if not node:
        report.add(FAIL, "Node.js", "nicht gefunden — https://nodejs.org installieren")
        return
    rc, out = _run([node, "--version"])
    m = re.match(r"v(\d+)\.(\d+)", out)
    if rc != 0 or not m:
        report.add(WARN, "Node.js", f"gefunden, Version nicht lesbar ({out!r})")
        return
    major, minor = int(m.group(1)), int(m.group(2))
    ok = (major, minor) >= (MIN_NODE_MAJOR, MIN_NODE_MINOR)
    report.add(
        PASS if ok else FAIL,
        "Node.js",
        f"{out} ({'>= ' if ok else '< '}{MIN_NODE_MAJOR}.{MIN_NODE_MINOR} erforderlich für Next.js 16)",
    )


def check_npm(report: Report) -> None:
    npm = shutil.which("npm")
    if not npm:
        report.add(FAIL, "npm", "nicht gefunden")
        return
    rc, out = _run([npm, "--version"])
    report.add(PASS if rc == 0 else WARN, "npm", out or "Version nicht lesbar")


def check_ffmpeg_tool(report: Report, name: str) -> None:
    path = shutil.which(name)
    if not path:
        report.add(FAIL, name, "nicht gefunden — Kernfunktion (Rendering) benötigt dies")
        return
    rc, out = _run([path, "-version"])
    first_line = out.splitlines()[0] if out else ""
    report.add(PASS if rc == 0 else WARN, name, first_line or path)


def _module_available(mod_name: str) -> bool:
    try:
        return importlib.util.find_spec(mod_name) is not None
    except (ImportError, ValueError, ModuleNotFoundError):
        return False


def check_backend_deps(report: Report) -> None:
    required = {
        "fastapi": "fastapi",
        "uvicorn": "uvicorn",
        "multipart": "python-multipart",
        "pydantic": "pydantic",
    }
    for mod, pip_name in required.items():
        ok = _module_available(mod)
        report.add(
            PASS if ok else FAIL,
            f"Backend-Dependency: {pip_name}",
            "installiert" if ok else "fehlt — `pip install -r api/requirements.txt`",
        )

    recommended = {
        "faster_whisper": ("faster-whisper", "ohne dieses Paket muss jedes Upload ein Transkript mitliefern"),
        "cv2": ("opencv-python-headless", "ohne dieses Paket fällt Smart-Reframe auf Center zurück"),
        "anthropic": ("anthropic", "ohne dieses Paket läuft der Analyzer regelbasiert statt mit KI"),
    }
    for mod, (pip_name, note) in recommended.items():
        ok = _module_available(mod)
        report.add(PASS if ok else WARN, f"Backend-Dependency (optional): {pip_name}", "installiert" if ok else note)

    optional_youtube = {
        "keyring": ("keyring", "YouTube-Token-Speicher bleibt 'blocked' ohne dieses Paket"),
        "google.auth": ("google-auth", "YouTube-OAuth-Token-Exchange nicht möglich ohne dieses Paket"),
        "google_auth_oauthlib": ("google-auth-oauthlib", "YouTube-OAuth-Flow nicht möglich ohne dieses Paket"),
        "googleapiclient": ("google-api-python-client", "YouTube-Upload nicht möglich ohne dieses Paket"),
    }
    for mod, (pip_name, note) in optional_youtube.items():
        ok = _module_available(mod)
        report.add(
            PASS if ok else WARN,
            f"Backend-Dependency (YouTube, optional): {pip_name}",
            "installiert" if ok else note,
        )


def check_frontend_deps(report: Report) -> None:
    node_modules = os.path.join(WEB_DIR, "node_modules")
    if not os.path.isdir(node_modules):
        report.add(FAIL, "Frontend-Dependencies", "web/node_modules fehlt — `cd web && npm install`")
        return
    next_bin = os.path.join(node_modules, ".bin", "next")
    playwright_pkg = os.path.join(node_modules, "@playwright", "test")
    report.add(
        PASS if os.path.exists(next_bin) else FAIL,
        "Frontend-Dependencies (next)",
        "installiert" if os.path.exists(next_bin) else "next fehlt in node_modules",
    )
    report.add(
        PASS if os.path.isdir(playwright_pkg) else WARN,
        "Frontend-Dependencies (@playwright/test)",
        "installiert" if os.path.isdir(playwright_pkg) else "fehlt — Browser-E2E-Suite nicht lauffähig",
    )


def check_jobs_dir(report: Report) -> None:
    jobs_dir = os.environ.get("CLIPFORGE_JOBS_DIR", os.path.join(API_DIR, "jobs"))
    try:
        os.makedirs(jobs_dir, exist_ok=True)
        probe = os.path.join(jobs_dir, ".doctor_write_probe")
        with open(probe, "w") as fh:
            fh.write("ok")
        os.remove(probe)
        report.add(PASS, "Jobs-Verzeichnis schreibbar", jobs_dir)
    except OSError as exc:
        report.add(FAIL, "Jobs-Verzeichnis schreibbar", f"{jobs_dir}: {exc}")


def check_ports(report: Report) -> None:
    api_port = int(os.environ.get("CLIPFORGE_API_PORT", "8000"))
    web_port = int(os.environ.get("CLIPFORGE_WEB_PORT", "3000"))
    for label, port in (("Backend-Port", api_port), ("Frontend-Port", web_port)):
        busy = _port_in_use(port)
        report.add(
            WARN if busy else PASS,
            f"{label} {port}",
            "belegt (evtl. ClipForge läuft schon — start_local.sh erkennt das)" if busy else "frei",
        )


def check_brand_kit(report: Report) -> None:
    default_path = os.path.join(API_DIR, "config", "brand_kit.json")
    path = os.environ.get("CLIPFORGE_BRAND_KIT", default_path)
    exists = os.path.exists(path)
    report.add(
        PASS,
        "Brand Kit",
        f"aktiv ({os.path.basename(path)})" if exists else "kein Brand Kit gesetzt (optional, Default-Rendering)",
    )


def _bool_env(name: str) -> bool:
    return os.environ.get(name, "false").strip().lower() == "true"


def check_optional_config(report: Report) -> None:
    anthropic_configured = bool(os.environ.get("ANTHROPIC_API_KEY"))
    report.add(
        PASS,
        "Anthropic API Key",
        f"configured: {str(anthropic_configured).lower()} (optional — sonst regelbasierter Analyzer)",
    )

    client_secrets = os.environ.get("CLIPFORGE_YOUTUBE_CLIENT_SECRETS")
    creds_configured = bool(client_secrets) and os.path.exists(client_secrets)
    report.add(
        PASS,
        "YouTube OAuth Client Secrets",
        f"configured: {str(creds_configured).lower()}",
    )

    oauth_enabled = _bool_env("CLIPFORGE_ENABLE_YOUTUBE_OAUTH")
    report.add(PASS, "YouTube OAuth Feature Flag", f"configured: {str(oauth_enabled).lower()} (Default: false)")

    upload_enabled = _bool_env("CLIPFORGE_ENABLE_YOUTUBE_UPLOAD")
    report.add(
        PASS if not upload_enabled else WARN,
        "YouTube Upload Feature Flag",
        f"configured: {str(upload_enabled).lower()} (Default: false — PRIVATE-only, kein Public/Unlisted)",
    )

    real_test = _bool_env("CLIPFORGE_ENABLE_YOUTUBE_REAL_TEST")
    report.add(
        PASS if not real_test else WARN,
        "YouTube Real-Test-Modus",
        f"configured: {str(real_test).lower()} (Default: false — nur für bewussten manuellen E2E-Testlauf)",
    )

    recovery_scan = os.environ.get("CLIPFORGE_YOUTUBE_RECOVERY_SCAN_ENABLED", "true").strip().lower() == "true"
    report.add(PASS, "YouTube Recovery-Scan", f"configured: {str(recovery_scan).lower()} (Default: true)")


def print_report(report: Report) -> None:
    width = max((len(r.label) for r in report.results), default=0)
    for r in report.results:
        print(f"[{ICON[r.status]} {r.status:4}] {r.label.ljust(width)}  {r.detail}")
    print()
    n_pass = sum(1 for r in report.results if r.status == PASS)
    n_warn = sum(1 for r in report.results if r.status == WARN)
    n_fail = sum(1 for r in report.results if r.status == FAIL)
    print(f"Zusammenfassung: {n_pass} PASS, {n_warn} WARN, {n_fail} FAIL")
    if report.worst == FAIL:
        print("→ Mindestens eine Kernvoraussetzung fehlt. ClipForge kann so nicht zuverlässig starten.")
    elif report.worst == WARN:
        print("→ Kernvoraussetzungen erfüllt. Einzelne optionale Features sind eingeschränkt (siehe oben).")
    else:
        print("→ Alles bereit.")


def main() -> int:
    as_json = "--json" in sys.argv
    report = Report()
    check_python(report)
    check_node(report)
    check_npm(report)
    check_ffmpeg_tool(report, "ffmpeg")
    check_ffmpeg_tool(report, "ffprobe")
    check_backend_deps(report)
    check_frontend_deps(report)
    check_jobs_dir(report)
    check_ports(report)
    check_brand_kit(report)
    check_optional_config(report)

    if as_json:
        print(json.dumps(
            {
                "summary": report.worst,
                "results": [r.__dict__ for r in report.results],
            },
            indent=2,
        ))
    else:
        print_report(report)

    return 1 if report.worst == FAIL else 0


if __name__ == "__main__":
    sys.exit(main())
