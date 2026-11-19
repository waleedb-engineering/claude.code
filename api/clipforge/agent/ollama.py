"""Ollama (lokales LLM) für den Editor-Agenten: Erkennung, Empfehlung, Test.

Grundsätze:
- nur localhost (``planner.ollama_url``), kein Netzverkehr nach außen
- ClipForge lädt NIE selbst Modelle herunter (kein /api/pull) — der Nutzer
  entscheidet und führt ``ollama pull <modell>`` selbst aus
- Modellwahl: ``CLIPFORGE_OLLAMA_MODEL`` → sonst bestes installiertes Modell mit
  Tool-Calling → sonst Empfehlung nach Hardware (nur als Hinweis)
- Fehler/Zeitüberschreitung → der Agent fällt auf den Regel-Planer zurück
"""

from __future__ import annotations

import json
import os
import platform
import shutil
import subprocess
import time
import urllib.error
import urllib.request

# Modellfamilien, die laut Ollama-Bibliothek Tool-Calling unterstützen (Stand 11/2026).
TOOL_FAMILIES = ("qwen3", "qwen2.5", "llama3.3", "llama3.2", "llama3.1", "mistral-nemo", "mistral-small",
                 "mistral", "command-r", "granite3", "hermes3", "firefunction", "smollm2")
# Empfehlung nach verfügbarem Arbeitsspeicher (Download-Größe ≈ Q4-Quantisierung)
RECOMMEND = [
    (32, "qwen2.5:14b", 9.0, "sehr gute Werkzeugaufrufe, braucht ≥ 32 GB RAM"),
    (14, "qwen2.5:7b", 4.7, "guter Kompromiss für 16-GB-Rechner (Standard)"),
    (7, "qwen2.5:3b", 1.9, "für 8-GB-Rechner; einfache Befehle zuverlässig"),
    (0, "qwen2.5:1.5b", 1.0, "nur sehr einfache Befehle — Regel-Planer ist oft besser"),
]


def _get(url: str, timeout: float) -> dict:
    with urllib.request.urlopen(urllib.request.Request(url), timeout=timeout) as resp:  # noqa: S310 — localhost
        return json.loads(resp.read(2 * 1024 * 1024))


def hardware() -> dict:
    ram = None
    try:
        ram = os.sysconf("SC_PAGE_SIZE") * os.sysconf("SC_PHYS_PAGES") / 1024 ** 3
    except (ValueError, OSError, AttributeError):
        if platform.system() == "Darwin":
            try:
                ram = int(subprocess.run(["sysctl", "-n", "hw.memsize"], capture_output=True, text=True,
                                         timeout=3).stdout.strip()) / 1024 ** 3
            except (OSError, ValueError, subprocess.SubprocessError):
                ram = None
    if ram is None and platform.system() == "Windows":
        try:
            import ctypes

            class MS(ctypes.Structure):
                _fields_ = [("l", ctypes.c_ulong), ("load", ctypes.c_ulong), ("total", ctypes.c_ulonglong),
                            ("avail", ctypes.c_ulonglong), ("a", ctypes.c_ulonglong), ("b", ctypes.c_ulonglong),
                            ("c", ctypes.c_ulonglong), ("d", ctypes.c_ulonglong), ("e", ctypes.c_ulonglong)]
            ms = MS()
            ms.l = ctypes.sizeof(MS)
            ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(ms))  # type: ignore[attr-defined]
            ram = ms.total / 1024 ** 3
        except Exception:  # noqa: BLE001
            ram = None
    apple = platform.system() == "Darwin" and platform.machine() in ("arm64", "aarch64")
    return {"os": platform.system(), "arch": platform.machine(), "cpus": os.cpu_count(),
            "ram_gb": round(ram, 1) if ram else None, "apple_silicon": apple,
            "nvidia_gpu": shutil.which("nvidia-smi") is not None}


def recommend(hw: dict | None = None) -> dict:
    hw = hw or hardware()
    ram = hw.get("ram_gb") or 8
    for need, model, gb, why in RECOMMEND:
        if ram >= need:
            accel = ("Apple-Silicon-GPU (Metal)" if hw.get("apple_silicon") else
                     "NVIDIA-GPU" if hw.get("nvidia_gpu") else "nur CPU — Antworten dauern länger")
            return {"model": model, "download_gb": gb, "reason": why, "acceleration": accel,
                    "command": f"ollama pull {model}",
                    "note": "ClipForge lädt keine Modelle selbst herunter. Befehl bei Bedarf selbst ausführen."}
    return {}


def tool_capable(name: str) -> bool:
    base = name.split(":", 1)[0].lower()
    return any(base == f or base.startswith(f + "-") or base.startswith(f) for f in TOOL_FAMILIES)


def choose_model(installed: list[str]) -> tuple[str | None, str]:
    env = os.environ.get("CLIPFORGE_OLLAMA_MODEL", "").strip()
    if env:
        if env in installed or any(m.split(":")[0] == env for m in installed):
            return env, "aus CLIPFORGE_OLLAMA_MODEL"
        return None, f"CLIPFORGE_OLLAMA_MODEL={env} ist nicht installiert"
    capable = [m for m in installed if tool_capable(m)]
    if not capable:
        return None, "kein installiertes Modell mit Tool-Calling"
    order = {f: i for i, f in enumerate(TOOL_FAMILIES)}
    capable.sort(key=lambda m: (order.get(next((f for f in TOOL_FAMILIES if m.lower().startswith(f)), ""), 99), m))
    return capable[0], "bestes installiertes Modell mit Tool-Calling"


def status(timeout: float = 1.5) -> dict:
    from .planner import ollama_url
    hw = hardware()
    out = {"reachable": False, "url": None, "version": None, "models": [], "model": None,
           "model_reason": "", "hardware": hw, "recommendation": recommend(hw), "live_verified": False}
    try:
        url = ollama_url()
        out["url"] = url
        out["version"] = _get(f"{url}/api/version", timeout).get("version")
        tags = _get(f"{url}/api/tags", timeout).get("models", [])
        out["reachable"] = True
        out["models"] = [{"name": m.get("name"), "size_gb": round((m.get("size") or 0) / 1024 ** 3, 1),
                          "tool_calling": tool_capable(m.get("name") or "")} for m in tags]
        out["model"], out["model_reason"] = choose_model([m["name"] for m in out["models"] if m["name"]])
    except Exception as exc:  # noqa: BLE001 — Ollama läuft nicht / falsche URL
        out["error"] = getattr(exc, "message", None) or type(exc).__name__
        out["hint"] = ("Ollama nicht erreichbar. Installieren (ollama.com), starten und z. B. "
                       f"`{out['recommendation'].get('command', 'ollama pull qwen2.5:7b')}` ausführen.")
    return out


TEST_TOOL = {"type": "function", "function": {
    "name": "set_caption_appearance", "description": "Untertitel-Position setzen.",
    "parameters": {"type": "object", "properties": {"position": {"type": "string", "enum": ["top", "middle", "bottom"]}},
                   "required": ["position"]}}}


def test(model: str | None = None, timeout: float | None = None) -> dict:
    """Echter Probelauf: ein Werkzeugaufruf mit einem Beispielbefehl. Kostenlos, lokal."""
    from .planner import ollama_url
    st = status()
    if not st["reachable"]:
        return {"ok": False, "stage": "connection", "message": st.get("hint")}
    model = model or st["model"]
    if not model:
        return {"ok": False, "stage": "model", "message": st["model_reason"] + ". Empfehlung: "
                + st["recommendation"].get("command", "")}
    if model not in [m["name"] for m in st["models"]] and not any(
            m["name"].split(":")[0] == model for m in st["models"]):
        return {"ok": False, "stage": "model", "message": f"Modell {model} ist nicht installiert (kein Auto-Download)."}
    timeout = timeout or float(os.environ.get("CLIPFORGE_OLLAMA_TIMEOUT", "120"))
    body = {"model": model, "stream": False, "tools": [TEST_TOOL], "options": {"temperature": 0},
            "messages": [{"role": "system", "content": "Antworte nur mit Werkzeugaufrufen."},
                         {"role": "user", "content": "Setze die Untertitel bitte nach oben."}]}
    t0 = time.perf_counter()
    req = urllib.request.Request(f"{ollama_url()}/api/chat", data=json.dumps(body).encode(), method="POST",
                                 headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:  # noqa: S310 — localhost
            data = json.loads(resp.read(2 * 1024 * 1024))
    except urllib.error.HTTPError as exc:
        return {"ok": False, "stage": "chat", "message": f"HTTP {exc.code} (Modell unterstützt evtl. keine Tools)"}
    except (OSError, ValueError) as exc:
        return {"ok": False, "stage": "chat", "message": f"keine Antwort ({type(exc).__name__}, Timeout {timeout:.0f} s)"}
    secs = round(time.perf_counter() - t0, 1)
    calls = (data.get("message") or {}).get("tool_calls") or []
    fn = (calls[0].get("function") if calls else {}) or {}
    args = fn.get("arguments") or {}
    if isinstance(args, str):
        try:
            args = json.loads(args)
        except ValueError:
            args = {}
    ok = fn.get("name") == "set_caption_appearance" and args.get("position") == "top"
    return {"ok": ok, "stage": "tool_call", "model": model, "seconds": secs,
            "tool_call": {"name": fn.get("name"), "args": args} if calls else None,
            "message": "Werkzeugaufruf korrekt" if ok else
            ("Modell antwortet, aber ohne korrekten Werkzeugaufruf — anderes Modell oder Regel-Planer nutzen"
             if calls or data.get("message") else "leere Antwort")}
