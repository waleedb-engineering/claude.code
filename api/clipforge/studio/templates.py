"""Videovorlagen: gespeicherte Produktionseinstellungen.

Eine Vorlage legt Format, Stil, Untertitel, Musik-Verhalten, Übergänge,
Stimme (Tempo/Lautstärke) und die Szenenstruktur fest. Eingebaute Vorlagen
sind schreibgeschützt; eigene Vorlagen liegen in <studio>/templates.json und
können aus einem Projekt gespeichert, bearbeitet und gelöscht werden.

Die Szenenstruktur wird beim Anwenden als Aufbau-Anweisung in
`options.creative_instructions` übernommen (die Skripterzeugung nutzt sie)
und – falls das Projekt noch leer ist – als Szenengerüst angelegt.
"""

from __future__ import annotations

import os
import threading

from .errors import StudioError
from .projects import (ASPECT_RATIOS, CAPTION_STYLES, STYLES, TRANSITIONS, migrate,
                       normalize_scene)
from .storage import new_id, now_iso, read_json, studio_dir, write_json_atomic

_lock = threading.RLock()


def _t(tid, name_de, name_en, desc, *, aspect="9:16", style="clean", captions="karaoke",
       transition="cut", tdur=0.4, beat=False, music=0.25, speed=1.0, media="motion",
       duration=45, platform="generic", headlines=True, structure=(), cap_pos="bottom",
       cap_color=None, cap_hl=None, cap_size=1.0, loudnorm=False, hook_zoom=None):
    caps = {"style": captions, "position": cap_pos, "size": cap_size}
    if cap_color:
        caps["color"] = cap_color
    if cap_hl:
        caps["highlight_color"] = cap_hl
    return {
        "id": tid, "builtin": True, "name": name_de, "name_en": name_en, "description": desc,
        "settings": {
            "aspect_ratio": aspect, "style": style,
            "captions": caps,
            "audio": {"loudnorm": loudnorm},
            **({"hook_zoom": hook_zoom} if hook_zoom else {}),
            "transitions": {"style": transition, "duration": tdur},
            "music": {"volume": music, "ducking": True, "beat_sync": beat},
            "voice": {"speed": speed},
            "visuals": {"headlines": headlines},
            "options": {"media_type": media, "duration_target": duration, "platform": platform},
        },
        "structure": [{"kind": k, "hint": h} for k, h in structure],
    }


BUILTIN = [
    _t("motivation", "Motivation", "Motivation",
       "Emotionaler Hook, kurze kraftvolle Sätze, Beat-Schnitt.",
       style="cinematic", captions="bold", transition="fadeblack", tdur=0.5, beat=True,
       music=0.35, duration=35,
       structure=[("hook", "Provokante Frage oder starke Aussage"),
                  ("body", "Hindernis benennen"), ("body", "Wendepunkt / Erkenntnis"),
                  ("cta", "Aufforderung zum Handeln")]),
    _t("knowledge", "Wissen / Fakten", "Knowledge / facts",
       "Neugier-Hook, drei Fakten, klare Untertitel.",
       captions="karaoke", transition="smooth", tdur=0.3, duration=45, media="ai_image",
       structure=[("hook", "Überraschende Frage"), ("body", "Fakt 1"), ("body", "Fakt 2"),
                  ("body", "Fakt 3"), ("cta", "Folgen für mehr Wissen")]),
    _t("storytelling", "Storytelling", "Storytelling",
       "Spannungsbogen mit ruhigen Überblendungen.",
       style="cinematic", captions="minimal", transition="dissolve", tdur=0.6, duration=60,
       music=0.2, speed=0.95,
       structure=[("hook", "Mitten in der Szene starten"), ("body", "Ausgangslage"),
                  ("body", "Konflikt"), ("body", "Auflösung"), ("cta", "Pointe / Frage")]),
    _t("reddit_story", "Reddit-Story", "Reddit story",
       "Erzählstimme über Gameplay im Split-Screen, große Wort-Untertitel.",
       captions="dynamic", transition="cut", duration=60, speed=1.1, music=0.15,
       headlines=False,
       structure=[("hook", "Titel der Geschichte vorlesen"), ("body", "Vorgeschichte"),
                  ("body", "Eskalation"), ("cta", "Was hättet ihr getan?")]),
    _t("podcast_clip", "Podcast-Clip", "Podcast clip",
       "Ausschnitt mit Originalton, Wort-Untertitel, keine Musik.",
       captions="karaoke", transition="cut", music=0.0, duration=50, headlines=False,
       structure=[("hook", "Stärkste Aussage zuerst"), ("body", "Kontext"),
                  ("cta", "Ganze Folge anhören")]),
    _t("gaming", "Gaming-Clip", "Gaming clip",
       "Schnelle Schnitte, Zoom-Übergänge, laute Musik.",
       captions="bold", transition="zoom", tdur=0.25, beat=True, music=0.4, duration=30,
       speed=1.1, structure=[("hook", "Highlight-Moment"), ("body", "Aufbau"),
                             ("cta", "Folgen für mehr Clips")]),
    _t("product_ad", "Produktwerbung", "Product ad",
       "Problem → Lösung → Vorteile → Angebot.",
       captions="bold", transition="slide", tdur=0.35, music=0.3, duration=30,
       structure=[("hook", "Problem der Zielgruppe"), ("body", "Produkt als Lösung"),
                  ("body", "Zwei Vorteile"), ("cta", "Angebot / Link")]),
    _t("explainer", "Erklärvideo", "Explainer",
       "Ruhiges Tempo, Schritt für Schritt, 16:9 möglich.",
       captions="minimal", transition="fade", tdur=0.4, music=0.15, duration=90, speed=0.95,
       structure=[("hook", "Was lernst du?"), ("body", "Schritt 1"), ("body", "Schritt 2"),
                  ("body", "Schritt 3"), ("cta", "Zusammenfassung")]),
    _t("news", "Social-Media-News", "Social media news",
       "Schlagzeile, Fakten, Einordnung — mit Headlines.",
       captions="bold", transition="wipe", tdur=0.3, music=0.2, duration=40,
       structure=[("hook", "Schlagzeile"), ("body", "Was ist passiert?"),
                  ("body", "Warum ist es wichtig?"), ("cta", "Meinung in die Kommentare")]),
    _t("twitch_clip", "Twitch-Clip", "Twitch clip",
       "Stream-Highlight: Originalton, Gesichts-Zoom im Einstieg, große Untertitel oben, normalisierte Lautheit.",
       captions="bold", transition="cut", music=0.0, duration=30, headlines=False, platform="tiktok",
       cap_pos="top", cap_color="#ffffff", cap_hl="#9146ff", cap_size=1.15, loudnorm=True,
       hook_zoom={"factor": 1.3, "focus": "face", "ramp": True},
       structure=[("hook", "Reaktion / Höhepunkt zuerst"), ("body", "Was davor passiert ist"),
                  ("cta", "Live auf Twitch folgen")]),
    _t("youtube_shorts", "YouTube Shorts", "YouTube Shorts",
       "Unter 60 s, schneller Einstieg, Karaoke-Untertitel in der Mitte, −14 LUFS.",
       captions="karaoke", transition="smooth", tdur=0.25, music=0.2, duration=45, speed=1.05,
       platform="youtube_shorts", cap_pos="middle", cap_hl="#ff3030", loudnorm=True,
       structure=[("hook", "Ergebnis zuerst zeigen"), ("body", "Kurz erklären"), ("body", "Beweis/Beispiel"),
                  ("cta", "Abonnieren")]),
    _t("interview", "Interview", "Interview",
       "Ruhige Schnitte, Originalton, dezente Untertitel unten, Zoom auf die sprechende Person.",
       captions="minimal", transition="cut", music=0.0, duration=60, headlines=False, loudnorm=True,
       hook_zoom={"factor": 1.2, "focus": "face", "ramp": False},
       structure=[("hook", "Stärkstes Zitat"), ("body", "Frage"), ("body", "Antwort"),
                  ("cta", "Ganzes Interview")]),
    _t("cinematic", "Cinematic Edit", "Cinematic edit",
       "Breitwand-Balken, langsame Überblendungen, langsamer Zoom, Musik im Vordergrund.",
       style="cinematic", captions="minimal", transition="dissolve", tdur=0.8, music=0.45, beat=True,
       duration=40, speed=0.95, cap_size=0.9, loudnorm=True,
       hook_zoom={"factor": 1.15, "focus": "center", "ramp": True},
       structure=[("hook", "Stimmungsbild"), ("body", "Aufbau"), ("body", "Höhepunkt"), ("cta", "Ausklang")]),
    _t("faceless", "Ohne Sprecher (faceless)", "Faceless",
       "Stimme + Bilder/Motion, kein sichtbarer Sprecher.",
       captions="karaoke", transition="auto", tdur=0.4, music=0.25, duration=45,
       media="ai_image",
       structure=[("hook", "Hook"), ("body", "Hauptpunkt 1"), ("body", "Hauptpunkt 2"),
                  ("cta", "Call-to-Action")]),
]
_BUILTIN_IDS = {t["id"] for t in BUILTIN}


def _path() -> str:
    return os.path.join(studio_dir(), "templates.json")


def _custom() -> list[dict]:
    data = read_json(_path(), [])
    return data if isinstance(data, list) else []


def list_templates() -> list[dict]:
    return [*BUILTIN, *_custom()]


def get_template(tid: str) -> dict:
    for t in list_templates():
        if t["id"] == tid:
            return t
    raise StudioError("template_not_found", "Vorlage nicht gefunden.", 404)


def _clean_settings(raw: dict) -> dict:
    """Nur bekannte Felder mit gültigen Werten übernehmen."""
    raw = raw if isinstance(raw, dict) else {}
    out: dict = {}
    if raw.get("aspect_ratio") in ASPECT_RATIOS:
        out["aspect_ratio"] = raw["aspect_ratio"]
    if raw.get("style") in STYLES:
        out["style"] = raw["style"]
    cap = raw.get("captions") or {}
    if isinstance(cap, dict) and cap.get("style") in CAPTION_STYLES:
        from .projects import _HEX, CAPTION_FONTS, CAPTION_POSITIONS
        c = {"style": cap["style"]}
        if cap.get("position") in CAPTION_POSITIONS:
            c["position"] = cap["position"]
        if cap.get("font") in CAPTION_FONTS:
            c["font"] = cap["font"]
        for k in ("color", "highlight_color"):
            if _HEX.match(str(cap.get(k) or "")):
                c[k] = cap[k]
        try:
            c["size"] = min(1.6, max(0.6, float(cap.get("size", 1.0))))
        except (TypeError, ValueError):
            pass
        out["captions"] = c
    au = raw.get("audio") or {}
    if isinstance(au, dict) and "loudnorm" in au:
        out["audio"] = {"loudnorm": bool(au["loudnorm"])}
    hz = raw.get("hook_zoom")
    if isinstance(hz, dict):
        try:
            f = min(2.5, max(1.0, float(hz.get("factor", 1.0))))
        except (TypeError, ValueError):
            f = 1.0
        if f > 1.0:
            from .projects import ZOOM_FOCUS
            out["hook_zoom"] = {"factor": f, "focus": hz.get("focus") if hz.get("focus") in ZOOM_FOCUS else "center",
                                "ramp": bool(hz.get("ramp", False))}
    tr = raw.get("transitions") or {}
    if isinstance(tr, dict) and tr.get("style") in TRANSITIONS:
        try:
            d = min(1.5, max(0.1, float(tr.get("duration", 0.4))))
        except (TypeError, ValueError):
            d = 0.4
        out["transitions"] = {"style": tr["style"], "duration": d}
    mu = raw.get("music") or {}
    if isinstance(mu, dict):
        try:
            out["music"] = {"volume": min(1.0, max(0.0, float(mu.get("volume", 0.25)))),
                            "ducking": bool(mu.get("ducking", True)),
                            "beat_sync": bool(mu.get("beat_sync", False))}
        except (TypeError, ValueError):
            pass
    vo = raw.get("voice") or {}
    if isinstance(vo, dict):
        try:
            out["voice"] = {"speed": min(2.0, max(0.5, float(vo.get("speed", 1.0))))}
        except (TypeError, ValueError):
            pass
    vi = raw.get("visuals") or {}
    if isinstance(vi, dict) and "headlines" in vi:
        out["visuals"] = {"headlines": bool(vi["headlines"])}
    op = raw.get("options") or {}
    if isinstance(op, dict):
        from .options import ProductionOptions
        keep = {k: op[k] for k in ("media_type", "duration_target", "platform", "visual_style",
                                   "cta", "goal", "audience") if k in op}
        if keep:
            ProductionOptions.from_dict(keep, strict=True)  # validiert
            out["options"] = keep
    return out


def _clean_structure(raw) -> list[dict]:
    out = []
    for item in (raw if isinstance(raw, list) else [])[:20]:
        if isinstance(item, dict):
            kind = item.get("kind") if item.get("kind") in ("hook", "body", "cta") else "body"
            out.append({"kind": kind, "hint": " ".join(str(item.get("hint") or "").split())[:120]})
    return out


def save_template(data: dict, tid: str | None = None) -> dict:
    name = " ".join(str((data or {}).get("name") or "").split())[:60]
    if not name:
        raise StudioError("validation_error", "Die Vorlage braucht einen Namen.")
    if tid in _BUILTIN_IDS:
        raise StudioError("template_readonly",
                          "Eingebaute Vorlagen sind schreibgeschützt — speichere eine Kopie.", 409)
    entry = {"id": tid or new_id(), "builtin": False, "name": name,
             "name_en": name, "description": str(data.get("description") or "")[:200],
             "settings": _clean_settings(data.get("settings")),
             "structure": _clean_structure(data.get("structure")),
             "updated_at": now_iso()}
    with _lock:
        items = _custom()
        if tid:
            if not any(t["id"] == tid for t in items):
                raise StudioError("template_not_found", "Vorlage nicht gefunden.", 404)
            items = [entry if t["id"] == tid else t for t in items]
        else:
            if len(items) >= 100:
                raise StudioError("validation_error", "Maximal 100 eigene Vorlagen.")
            items.append(entry)
        write_json_atomic(_path(), items)
    return entry


def delete_template(tid: str) -> None:
    if tid in _BUILTIN_IDS:
        raise StudioError("template_readonly", "Eingebaute Vorlagen können nicht gelöscht werden.", 409)
    with _lock:
        items = _custom()
        kept = [t for t in items if t["id"] != tid]
        if len(kept) == len(items):
            raise StudioError("template_not_found", "Vorlage nicht gefunden.", 404)
        write_json_atomic(_path(), kept)


def from_project(project: dict) -> dict:
    """Einstellungen eines Projekts als Vorlagen-Entwurf (zum Speichern)."""
    return {
        "settings": _clean_settings({
            "aspect_ratio": project.get("aspect_ratio"), "style": project.get("style"),
            "captions": project.get("captions"), "transitions": project.get("transitions"),
            "music": project.get("music"), "voice": project.get("voice"),
            "visuals": project.get("visuals"), "audio": project.get("audio"),
            "hook_zoom": next((sc.get("zoom") for sc in project.get("scenes", []) if sc.get("kind") == "hook"), None),
            "options": {k: (project.get("options") or {}).get(k)
                        for k in ("media_type", "duration_target", "platform")},
        }),
        "structure": [{"kind": s.get("kind", "body"), "hint": (s.get("headline") or "")}
                      for s in project.get("scenes", [])][:20],
    }


def apply_template(project: dict, template: dict) -> dict:
    """Wendet eine Vorlage auf ein Projekt an (Inhalte bleiben erhalten)."""
    p = dict(project)
    s = _clean_settings(template.get("settings"))
    for key in ("aspect_ratio", "style"):
        if key in s:
            p[key] = s[key]
    for key in ("captions", "transitions", "music", "voice", "visuals", "audio"):
        if key in s:
            p[key] = {**(p.get(key) or {}), **s[key]}
    opts = {**(p.get("options") or {}), **s.get("options", {})}
    structure = _clean_structure(template.get("structure"))
    if structure:
        plan = "; ".join(f"{i + 1}. {x['hint'] or x['kind']}" for i, x in enumerate(structure))
        note = f"Aufbau ({template.get('name')}): {plan}"
        prev = str(opts.get("creative_instructions") or "")
        prev = prev.split("Aufbau (")[0].strip()  # alte Vorlagen-Anweisung ersetzen
        opts["creative_instructions"] = (prev + " " + note).strip()[:2000]
        if not p.get("scenes"):
            p["scenes"] = [normalize_scene({"kind": x["kind"], "text": x["hint"],
                                            "headline": x["hint"][:60]}) for x in structure]
    if s.get("hook_zoom") and p.get("scenes"):
        scenes = [dict(x) for x in p["scenes"]]
        hook = next((x for x in scenes if x.get("kind") == "hook"), scenes[0])
        hook["zoom"] = dict(s["hook_zoom"])
        p["scenes"] = scenes
    p["options"] = opts
    p["template_id"] = template["id"]
    return migrate(p)
