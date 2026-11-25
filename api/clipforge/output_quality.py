"""Automatische Qualitätsprüfung fertiger Videos (ein FFmpeg-Durchgang).

Messbar und geprüft:
- Format: Auflösung, Seitenverhältnis, Bildrate, Dauer je Zielplattform
- Bild: unbeabsichtigte Schwarzbilder (blackdetect), eingefrorenes Bild (freezedetect)
- Ton: vorhanden, integrierte Lautheit (EBU R128), True Peak, übersteuerte Spitzen,
  lange Pausen (silencedetect)

Nicht messbar (→ menschliche Review-Stufe, ``REVIEW_ITEMS``): ob die Pointe
vollständig ist, ob Anfang/Ende natürlich wirken, ob der Bildausschnitt das
Richtige zeigt, ob Untertitel inhaltlich passen.
"""

from __future__ import annotations

import re
import subprocess

from .ffmpeg_utils import probe

# Plattformprofile (Stand 11/2026, offizielle Hilfeseiten der Plattformen; Grenzen können sich ändern)
PLATFORMS = {
    "generic": {"aspect": None, "max_s": None},
    "tiktok": {"aspect": (9, 16), "max_s": 600},
    "youtube_shorts": {"aspect": (9, 16), "max_s": 180},
    "instagram_reels": {"aspect": (9, 16), "max_s": 180},
    "x": {"aspect": None, "max_s": 140},
}
REVIEW_ITEMS = {
    "punchline_complete": "Pointe/Aussage vollständig enthalten",
    "natural_start": "Natürlicher Einstieg (nicht mitten im Wort/Satz)",
    "clean_end": "Sinnvoller Abschluss",
    "framing_ok": "Bildausschnitt zeigt das Wesentliche",
    "captions_ok": "Untertitel inhaltlich und zeitlich passend",
    "audio_ok": "Sprache gut verständlich, Musik nicht zu laut",
}


def _check(cid: str, level: str, message: str, value=None) -> dict:
    out = {"id": cid, "level": level, "message": message}
    if value is not None:
        out["value"] = value
    return out


def analyze(path: str, *, platform: str = "generic", min_pause: float = 1.5, timeout: int = 900) -> dict:
    info = probe(path)
    dur = float(info.duration or 0)
    checks = []
    prof = PLATFORMS.get(platform, PLATFORMS["generic"])
    # --- Format
    if prof["aspect"] and info.width and info.height:
        aw, ah = prof["aspect"]
        ok = abs(info.width * ah - info.height * aw) <= max(aw, ah) * 2
        checks.append(_check("aspect", "ok" if ok else "fail",
                             f"Format {info.width}×{info.height}" + ("" if ok else f" — erwartet {aw}:{ah}"),
                             f"{info.width}x{info.height}"))
    if prof["max_s"] and dur > prof["max_s"]:
        checks.append(_check("duration", "fail", f"{dur:.0f} s länger als erlaubt ({prof['max_s']} s)", round(dur, 2)))
    else:
        checks.append(_check("duration", "ok", f"Dauer {dur:.1f} s", round(dur, 2)))
    # --- ein Durchgang: Bild- und Tonanalyse
    cmd = ["ffmpeg", "-hide_banner", "-nostats", "-i", path,
           "-vf", "blackdetect=d=0.3:pic_th=0.98,freezedetect=n=0.003:d=2"]
    if info.has_audio:
        cmd += ["-af", f"ebur128=peak=true,silencedetect=noise=-45dB:d={min_pause},astats=metadata=0"]
    cmd += ["-f", "null", "-"]
    try:
        err = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout).stderr
    except subprocess.TimeoutExpired:
        checks.append(_check("analysis", "warn", "Analyse abgebrochen (Zeitlimit)"))
        return _result(checks, platform)
    blacks = [(float(a), float(b)) for a, b in re.findall(r"black_start:([\d.]+) black_end:([\d.]+)", err)]
    inner = [(a, b) for a, b in blacks if a > 0.15 and b < dur - 0.15]
    edge = [(a, b) for a, b in blacks if (a, b) not in inner]
    if inner:
        checks.append(_check("black_frames", "warn",
                             "Schwarzbild im Video: " + ", ".join(f"{a:.1f}–{b:.1f} s" for a, b in inner[:5]),
                             [[round(a, 2), round(b, 2)] for a, b in inner]))
    elif edge:
        checks.append(_check("black_frames", "warn" if any(b - a > 1.0 for a, b in edge) else "ok",
                             "Schwarzbild am Anfang/Ende: " + ", ".join(f"{a:.1f}–{b:.1f} s" for a, b in edge[:3])))
    else:
        checks.append(_check("black_frames", "ok", "keine Schwarzbilder"))
    freezes = re.findall(r"freeze_start: ([\d.]+)", err)
    checks.append(_check("frozen", "warn" if freezes else "ok",
                         f"Bild steht ≥ 2 s ab {', '.join(freezes[:3])} s (Standbild beabsichtigt?)" if freezes
                         else "kein eingefrorenes Bild"))
    if not info.has_audio:
        checks.append(_check("audio", "fail", "keine Tonspur"))
        return _result(checks, platform)
    m = re.findall(r"I:\s+(-?[\d.]+) LUFS", err)
    tp = re.findall(r"Peak:\s+(-?[\d.]+|-inf) dBFS", err)
    lufs = float(m[-1]) if m else None
    true_peak = float(tp[-1]) if tp and tp[-1] != "-inf" else None
    if lufs is None or lufs < -60:
        checks.append(_check("loudness", "fail", "Ton praktisch still", lufs))
    elif lufs < -20 or lufs > -9:
        checks.append(_check("loudness", "warn", f"Lautheit {lufs:.1f} LUFS (üblich −16…−12; Normalisierung möglich)", lufs))
    else:
        checks.append(_check("loudness", "ok", f"Lautheit {lufs:.1f} LUFS", lufs))
    if true_peak is not None:
        if true_peak > -0.1:
            checks.append(_check("clipping", "fail", f"übersteuert (True Peak {true_peak:.1f} dBTP)", true_peak))
        elif true_peak > -1.0:
            checks.append(_check("clipping", "warn", f"True Peak {true_peak:.1f} dBTP (Plattformen empfehlen ≤ −1)", true_peak))
        else:
            checks.append(_check("clipping", "ok", f"True Peak {true_peak:.1f} dBTP", true_peak))
    pauses = [(float(a), float(b)) for a, b in
              re.findall(r"silence_start: ([\d.]+)[\s\S]*?silence_end: ([\d.]+)", err)]
    long_p = [(a, b) for a, b in pauses if b - a >= min_pause and a > 0.3 and b < dur - 0.3]
    checks.append(_check("pauses", "warn" if long_p else "ok",
                         ("lange Pausen: " + ", ".join(f"{a:.1f}–{b:.1f} s" for a, b in long_p[:5])) if long_p
                         else f"keine Pausen ≥ {min_pause:.1f} s",
                         [[round(a, 2), round(b, 2)] for a, b in long_p] or None))
    return _result(checks, platform)


def _result(checks: list[dict], platform: str) -> dict:
    return {"platform": platform, "checks": checks,
            "passed": not any(c["level"] == "fail" for c in checks),
            "warnings": sum(1 for c in checks if c["level"] == "warn"),
            "review_items": REVIEW_ITEMS}


def review_entry(checklist: dict, verdict: str, note: str, user: str | None) -> dict:
    """Menschliche Freigabe je Render (subjektive Schnittqualität)."""
    from .studio.errors import StudioError
    from .studio.storage import now_iso
    if verdict not in ("approved", "changes_requested"):
        raise StudioError("validation_error", "verdict: approved oder changes_requested.")
    clean = {k: bool(checklist.get(k)) for k in REVIEW_ITEMS}
    if verdict == "approved" and not all(clean.values()):
        missing = [REVIEW_ITEMS[k] for k, v in clean.items() if not v]
        raise StudioError("validation_error", "Freigabe nur, wenn alle Punkte erfüllt sind: " + "; ".join(missing))
    return {"checklist": clean, "verdict": verdict, "note": str(note or "")[:500], "by": user or "lokal",
            "at": now_iso()}
