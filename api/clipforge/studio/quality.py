"""Qualitätsprüfung: vor dem Render (Inhalt) und nach dem Render (Datei)."""

from __future__ import annotations

from ..publishing import _contains_forbidden_claim

WORDS_PER_SECOND = 2.5


def _check(cid: str, level: str, message: str, scene_id: str | None = None) -> dict:
    out = {"id": cid, "level": level, "message": message}
    if scene_id:
        out["scene_id"] = scene_id
    return out


def pre_render_checks(project: dict) -> dict:
    """Inhaltliche Prüfung. level: ok | warn | fail (fail blockiert den Render)."""
    from .options import options_of
    opt = options_of(project)
    checks = []
    scenes = project.get("scenes") or []
    if not scenes:
        checks.append(_check("no_scenes", "fail", "Das Projekt hat keine Szenen."))
    total_words = 0
    for i, s in enumerate(scenes, start=1):
        text = s.get("text") or ""
        words = len(text.split())
        total_words += words
        if not text.strip() and not s.get("audio_source") and s["visual"]["mode"] != "media":
            checks.append(_check("scene_empty", "warn", f"Szene {i} hat keinen Text.", s["id"]))
        if "[" in text and "]" in text:
            checks.append(_check("placeholder", "warn",
                                 f"Szene {i} enthält noch einen Platzhalter in [Klammern].", s["id"]))
        if words > 45:
            checks.append(_check("scene_long", "warn",
                                 f"Szene {i} ist sehr lang ({words} Wörter) — besser teilen.", s["id"]))
        hits = opt.find_forbidden(text + " " + (s.get("voice_text") or ""))
        if hits:
            checks.append(_check("forbidden_topic", "fail",
                                 f"Szene {i} berührt ein ausgeschlossenes Thema ({', '.join(hits)}).",
                                 s["id"]))
        if _contains_forbidden_claim(text):
            checks.append(_check("forbidden_claim", "fail",
                                 f"Szene {i} verspricht Viralität — bitte umformulieren.", s["id"]))
        if s["visual"]["mode"] == "split" and not (project.get("visuals") or {}).get("gameplay_media"):
            checks.append(_check("split_no_gameplay", "warn",
                                 f"Szene {i}: Split-Screen ohne Gameplay-Datei.", s["id"]))
    if scenes and scenes[0].get("kind") != "hook":
        checks.append(_check("no_hook", "warn", "Die erste Szene ist nicht als Hook markiert."))
    est = total_words / WORDS_PER_SECOND
    if est > opt.max_seconds():
        checks.append(_check("too_long", "warn",
                             f"Geschätzte Länge {est:.0f}s — für '{opt.platform}' sind höchstens "
                             f"{opt.max_seconds()}s empfohlen."))
    if (project.get("script") or {}).get("needs_review"):
        checks.append(_check("needs_review", "warn",
                             "Das Skript ist ein automatisch erzeugtes Gerüst und sollte geprüft werden."))
    if not checks:
        checks.append(_check("content_ok", "ok", "Keine inhaltlichen Auffälligkeiten."))
    return {"checks": checks, "estimated_seconds": round(est, 1),
            "blocking": any(c["level"] == "fail" for c in checks)}


def post_render_checks(report: dict) -> dict:
    """Technische Prüfung der gerenderten Datei (Werte stammen aus ffprobe)."""
    checks = []
    exp = report.get("expected") or {}
    if report.get("bytes", 0) <= 0:
        checks.append(_check("file_empty", "fail", "Die Ausgabedatei ist leer."))
    if (report.get("width"), report.get("height")) != (exp.get("width"), exp.get("height")):
        checks.append(_check("dimensions", "fail",
                             f"Auflösung {report.get('width')}x{report.get('height')} weicht ab "
                             f"(erwartet {exp.get('width')}x{exp.get('height')})."))
    else:
        checks.append(_check("dimensions", "ok",
                             f"Auflösung {report.get('width')}x{report.get('height')} korrekt."))
    drift = abs((report.get("duration") or 0) - (exp.get("duration") or 0))
    checks.append(_check("duration", "ok" if drift <= 0.5 else "warn",
                         f"Dauer {report.get('duration')}s (geplant {exp.get('duration')}s)."))
    checks.append(_check("audio", "ok" if report.get("has_audio") else "fail",
                         "Tonspur vorhanden." if report.get("has_audio") else "Keine Tonspur."))
    cap = report.get("captions") or {}
    if cap.get("studio_style") not in (None, "none"):
        blocks = cap.get("caption_blocks_count") or 0
        checks.append(_check("captions", "ok" if blocks else "warn",
                             f"{blocks} Caption-Blöcke eingebrannt."))
    for warning in report.get("warnings") or []:
        checks.append(_check("render_warning", "warn", warning))
    return {"checks": checks, "passed": not any(c["level"] == "fail" for c in checks)}
