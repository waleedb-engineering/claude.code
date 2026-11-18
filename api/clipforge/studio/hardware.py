"""Hardware-Prüfung für lokale KI-Modelle (KI-Video, Lippensynchronisation).

Lokale Videomodelle wie Wan 2.x oder LTX-Video brauchen eine starke GPU
(Richtwerte aus den Modellkarten: LTX-Video ab ~12 GB VRAM, Wan 2.x 1.3B ab
~8 GB, 14B ab ~24 GB). ClipForge führt sie (noch) nicht selbst aus; diese
Prüfung sagt ehrlich, ob der Rechner dafür in Frage käme, und nennt die
kostenlose Alternative, damit die Videoerzeugung nie blockiert.
"""

from __future__ import annotations

import os
import platform
import shutil
import subprocess


def _nvidia() -> list[dict]:
    exe = shutil.which("nvidia-smi")
    if not exe:
        return []
    try:
        out = subprocess.run([exe, "--query-gpu=name,memory.total", "--format=csv,noheader,nounits"],
                             capture_output=True, text=True, timeout=10).stdout
    except (OSError, subprocess.SubprocessError):
        return []
    gpus = []
    for line in out.strip().splitlines():
        parts = [p.strip() for p in line.split(",")]
        if len(parts) == 2 and parts[1].isdigit():
            gpus.append({"name": parts[0], "vram_gb": round(int(parts[1]) / 1024, 1)})
    return gpus


def _ram_gb() -> float | None:
    try:
        return round(os.sysconf("SC_PAGE_SIZE") * os.sysconf("SC_PHYS_PAGES") / 1024 ** 3, 1)
    except (ValueError, OSError, AttributeError):
        return None  # Windows: nicht über sysconf


def check() -> dict:
    system, machine = platform.system(), platform.machine().lower()
    gpus = _nvidia()
    apple = system == "Darwin" and machine in ("arm64", "aarch64")
    vram = max((g["vram_gb"] for g in gpus), default=0.0)
    if vram >= 24:
        verdict, note = "strong", "Geeignet für große lokale Videomodelle (z. B. Wan 14B)."
    elif vram >= 12:
        verdict, note = "ok", "Geeignet für kleinere lokale Videomodelle (z. B. LTX-Video, Wan 1.3B)."
    elif vram >= 8:
        verdict, note = "limited", "Nur kleinste Videomodelle, sehr langsam."
    elif apple:
        verdict, note = "limited", ("Apple Silicon: einige Modelle laufen über MPS, deutlich langsamer "
                                    "als mit NVIDIA-GPU.")
    else:
        verdict, note = "unsuitable", "Ohne passende GPU sind lokale KI-Videos nicht praktikabel."
    return {
        "system": system, "machine": machine, "cpu_count": os.cpu_count(), "ram_gb": _ram_gb(),
        "nvidia_gpus": gpus, "apple_silicon": apple, "local_ai_video": verdict, "note": note,
        "local_video_supported_in_clipforge": False,
        "free_alternatives": ["Motion-Hintergründe", "eigene Videos/B-Roll", "Ken-Burns-Bilder",
                              "Stock-Videos (Pexels/Pixabay, kostenloser Schlüssel)"],
        "paid_alternative": "KI-Video über fal.ai (FAL_KEY, Projektbudget)",
    }
