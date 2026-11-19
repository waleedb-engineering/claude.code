"""Freigegebene Werkzeuge des Editor-Agenten.

Der Agent ruft ausschließlich diese Werkzeuge auf — keine Shell, keine freien
FFmpeg-Befehle. Jedes Werkzeug hat ein JSON-Schema, wird vor der Ausführung
validiert und ändert den Projektzustand über DIESELBEN Funktionen wie die
Oberfläche (StudioService.update_project mit Versionsschutz bzw.
StreamService). Dadurch gibt es nur einen Bearbeitungszustand, und jede
Änderung ist über die Versionsgeschichte rückgängig zu machen.
"""

from __future__ import annotations

import copy
from dataclasses import dataclass, field

from ..studio.errors import StudioError

CAPTION_STYLES = ("minimal", "bold", "karaoke", "dynamic", "none")
TRANSITIONS = ("cut", "fade", "fadeblack", "zoom", "slide", "slideup", "smooth", "wipe",
               "dissolve", "circle", "auto")


@dataclass
class Tool:
    name: str
    description: str
    context: str                 # "project" | "stream"
    params: dict                 # JSON-Schema (properties)
    required: tuple = ()
    mutating: bool = True
    confirm: bool = False        # vor Ausführung ausdrücklich bestätigen (Render/Export)
    run: object = None           # (ctx, args) -> dict
    cost_note: str = "kostenlos (lokal)"
    labels: dict = field(default_factory=dict)

    def schema(self) -> dict:
        return {"name": self.name, "description": self.description,
                "input_schema": {"type": "object", "properties": self.params,
                                 "required": list(self.required)}}


class Ctx:
    def __init__(self, svc, streams, kind: str, target: str) -> None:
        self.svc, self.streams, self.kind, self.target = svc, streams, kind, target


# ------------------------------------------------------------ Validierung
def validate(tool: Tool, args: dict) -> dict:
    if not isinstance(args, dict):
        raise StudioError("agent_invalid", f"{tool.name}: Parameter müssen ein Objekt sein.")
    out = {}
    for key in tool.required:
        if key not in args:
            raise StudioError("agent_invalid", f"{tool.name}: Parameter '{key}' fehlt.")
    for key, value in args.items():
        spec = tool.params.get(key)
        if spec is None:
            raise StudioError("agent_invalid", f"{tool.name}: unbekannter Parameter '{key}'.")
        typ = spec.get("type")
        if typ == "integer":
            if isinstance(value, bool) or not isinstance(value, (int, float)) or int(value) != value:
                raise StudioError("agent_invalid", f"{tool.name}.{key}: ganze Zahl erwartet.")
            value = int(value)
        elif typ == "number":
            if isinstance(value, bool) or not isinstance(value, (int, float)):
                raise StudioError("agent_invalid", f"{tool.name}.{key}: Zahl erwartet.")
            value = float(value)
        elif typ == "string":
            if not isinstance(value, str):
                raise StudioError("agent_invalid", f"{tool.name}.{key}: Text erwartet.")
            value = value[:2000]
        elif typ == "boolean":
            if not isinstance(value, bool):
                raise StudioError("agent_invalid", f"{tool.name}.{key}: ja/nein erwartet.")
        elif typ == "array":
            if not isinstance(value, list) or len(value) > 50:
                raise StudioError("agent_invalid", f"{tool.name}.{key}: Liste erwartet.")
        if "enum" in spec and value not in spec["enum"]:
            raise StudioError("agent_invalid",
                              f"{tool.name}.{key}: erlaubt sind {', '.join(map(str, spec['enum']))}.")
        if "minimum" in spec and value < spec["minimum"] or "maximum" in spec and value > spec["maximum"]:
            raise StudioError("agent_invalid", f"{tool.name}.{key}: Wert außerhalb des Bereichs.")
        out[key] = value
    return out


# ------------------------------------------------------- Projekt-Helfer
def _project(ctx: Ctx) -> dict:
    return ctx.svc.store.load(ctx.target)


def _save(ctx: Ctx, project: dict, keys: tuple) -> dict:
    """Speichert über denselben Weg wie der Editor (Patch + Versionsprüfung)."""
    patch = {k: project[k] for k in keys}
    saved = ctx.svc.update_project(ctx.target, patch, project["version"])
    return {"version": saved["version"]}


def _scene(project: dict, index: int) -> dict:
    scenes = project["scenes"]
    if not 1 <= index <= len(scenes):
        raise StudioError("agent_invalid", f"Szene {index} gibt es nicht (1–{len(scenes)}).")
    return scenes[index - 1]


# ------------------------------------------------------ Projekt-Werkzeuge
def t_state(ctx, a):
    p = _project(ctx)
    return {"title": p["title"], "aspect_ratio": p["aspect_ratio"], "style": p["style"],
            "captions": p["captions"]["style"], "transitions": p.get("transitions"),
            "voice": {k: p["voice"].get(k) for k in ("provider", "speed", "volume")},
            "music": {k: p["music"].get(k) for k in ("track", "volume", "ducking")},
            "scenes": [{"index": i + 1, "kind": s["kind"], "text": s["text"][:160],
                        "duration": s.get("duration"), "visual": s["visual"]["mode"],
                        "transition": s.get("transition")} for i, s in enumerate(p["scenes"])]}


def t_trim_scene(ctx, a):
    p = copy.deepcopy(_project(ctx))
    s = _scene(p, a["scene"])
    cut_start, cut_end = a.get("cut_start", 0.0), a.get("cut_end", 0.0)
    if s.get("audio_source"):
        src = s["audio_source"]
        new = {"start": round(src["start"] + cut_start, 3), "end": round(src["end"] - cut_end, 3)}
        if new["end"] - new["start"] < 0.5:
            raise StudioError("agent_invalid", "Nach dem Kürzen bliebe weniger als 0,5 s übrig.")
        s["audio_source"] = new
        s.pop("words", None)
        note = f"Originalton jetzt {new['start']:.1f}–{new['end']:.1f} s"
    else:
        base = s.get("duration") or 5.0
        dur = base - cut_start - cut_end
        if dur < 0.8:
            raise StudioError("agent_invalid", "Szene wäre kürzer als 0,8 s.")
        s["duration"] = round(dur, 2)
        if s["visual"].get("start") is not None or cut_start:
            s["visual"]["start"] = round(float(s["visual"].get("start") or 0) + cut_start, 2)
        note = f"Szenendauer {dur:.1f} s"
    return {**_save(ctx, p, ("scenes",)), "change": f"Szene {a['scene']} gekürzt — {note}"}


def t_split_scene(ctx, a):
    p = copy.deepcopy(_project(ctx))
    s = _scene(p, a["scene"])
    words = s["text"].split()
    at = a.get("after_word") or max(1, len(words) // 2)
    if not 1 <= at < len(words):
        raise StudioError("agent_invalid", "Teilen nur innerhalb des Textes möglich.")
    first = {**s, "text": " ".join(words[:at]), "words": None}
    second = {**copy.deepcopy(s), "id": None, "text": " ".join(words[at:]), "kind": "body",
              "headline": "", "words": None}
    from ..studio.projects import normalize_scene
    i = a["scene"] - 1
    p["scenes"][i:i + 1] = [normalize_scene(first), normalize_scene(second)]
    return {**_save(ctx, p, ("scenes",)), "change": f"Szene {a['scene']} nach Wort {at} geteilt"}


def t_merge_scenes(ctx, a):
    p = copy.deepcopy(_project(ctx))
    s1 = _scene(p, a["scene"])
    s2 = _scene(p, a["scene"] + 1)
    if s1.get("audio_source") or s2.get("audio_source"):
        raise StudioError("agent_invalid", "Szenen mit Originalton können nicht zusammengeführt werden.")
    s1["text"] = (s1["text"] + " " + s2["text"]).strip()
    if s1.get("duration") and s2.get("duration"):
        s1["duration"] = round(s1["duration"] + s2["duration"], 2)
    p["scenes"].pop(a["scene"])
    return {**_save(ctx, p, ("scenes",)), "change": f"Szenen {a['scene']} und {a['scene'] + 1} zusammengeführt"}


def t_move_scene(ctx, a):
    p = copy.deepcopy(_project(ctx))
    _scene(p, a["scene"])
    to = max(1, min(len(p["scenes"]), a["to"]))
    p["scenes"].insert(to - 1, p["scenes"].pop(a["scene"] - 1))
    return {**_save(ctx, p, ("scenes",)), "change": f"Szene {a['scene']} an Position {to}"}


def t_delete_scene(ctx, a):
    p = copy.deepcopy(_project(ctx))
    _scene(p, a["scene"])
    if len(p["scenes"]) == 1:
        raise StudioError("agent_invalid", "Die letzte Szene kann nicht gelöscht werden.")
    p["scenes"].pop(a["scene"] - 1)
    return {**_save(ctx, p, ("scenes",)), "change": f"Szene {a['scene']} gelöscht"}


def t_set_text(ctx, a):
    p = copy.deepcopy(_project(ctx))
    s = _scene(p, a["scene"])
    s["text"] = a["text"].strip()[:1200]
    if s.get("audio_source"):
        s.pop("words", None)
    return {**_save(ctx, p, ("scenes",)), "change": f"Text von Szene {a['scene']} geändert"}


def t_remove_pauses(ctx, a):
    p = copy.deepcopy(_project(ctx))
    n = 0
    for s in p["scenes"]:
        if s.get("pause_after"):
            s["pause_after"] = 0.0
            n += 1
    return {**_save(ctx, p, ("scenes",)), "change": f"Pausen nach {n} Szenen entfernt"}


def t_caption_style(ctx, a):
    p = copy.deepcopy(_project(ctx))
    p["captions"] = {**p["captions"], "style": a["style"]}
    return {**_save(ctx, p, ("captions",)), "change": f"Untertitel-Stil: {a['style']}"}


def t_transition(ctx, a):
    p = copy.deepcopy(_project(ctx))
    if a.get("scene"):
        _scene(p, a["scene"])["transition"] = a["type"]
        keys, note = ("scenes",), f"Übergang in Szene {a['scene']}: {a['type']}"
    else:
        p["transitions"] = {"style": a["type"], "duration": a.get("duration", (p.get("transitions") or {}).get("duration", 0.4))}
        for s in p["scenes"]:
            s["transition"] = "auto"
        keys, note = ("transitions", "scenes"), f"Übergänge überall: {a['type']}"
    return {**_save(ctx, p, keys), "change": note}


def t_adjust_audio(ctx, a):
    p = copy.deepcopy(_project(ctx))
    parts = []
    if "music_volume" in a:
        p["music"] = {**p["music"], "volume": a["music_volume"]}
        parts.append(f"Musik {a['music_volume']:.0%}")
    if "voice_volume" in a:
        p["voice"] = {**p["voice"], "volume": a["voice_volume"]}
        parts.append(f"Stimme {a['voice_volume']:.0%}")
    if "voice_speed" in a:
        p["voice"] = {**p["voice"], "speed": a["voice_speed"]}
        parts.append(f"Sprechtempo {a['voice_speed']:.2f}×")
    if "ducking" in a:
        p["music"] = {**p["music"], "ducking": a["ducking"]}
        parts.append("Ducking " + ("an" if a["ducking"] else "aus"))
    if not parts:
        raise StudioError("agent_invalid", "Keine Audio-Änderung angegeben.")
    return {**_save(ctx, p, ("music", "voice")), "change": ", ".join(parts)}


def t_hook_variants(ctx, a):
    """Erzeugt Projekt-Kopien mit anderen Einstiegs-Sätzen (lokal, regelbasiert)."""
    p = _project(ctx)
    hook = next((s for s in p["scenes"] if s["kind"] == "hook"), p["scenes"][0])
    base = hook["text"].rstrip(".!?")
    patterns = [("Frage", f"Wusstest du das? {base}."), ("Zahl", f"In 30 Sekunden: {base}."),
                ("Neugier", f"Das hat mich überrascht: {base}."), ("Direkt", f"{base}!")]
    out = []
    for label, text in patterns[: a.get("count", 3)]:
        copy_ = ctx.svc.store.duplicate(ctx.target, f"{p['title']} – Hook {label}",
                                        {"agent_hook_variant": label, "source": ctx.target})
        c = copy.deepcopy(copy_)
        idx = next(i for i, s in enumerate(c["scenes"]) if s["text"] == hook["text"])
        c["scenes"][idx]["text"] = text
        ctx.svc.update_project(c["id"], {"scenes": c["scenes"]}, c["version"])
        out.append({"project_id": c["id"], "label": label, "hook": text})
    return {"variants": out, "change": f"{len(out)} Hook-Varianten als neue Projekte angelegt"}


def t_render_preview(ctx, a):
    task = ctx.svc.start_render(ctx.target, "preview")
    return {"task_id": task["id"], "change": "Vorschau-Render gestartet"}


def t_export(ctx, a):
    task = ctx.svc.start_render(ctx.target, "final")
    return {"task_id": task["id"], "change": "Finaler Render gestartet"}


# ------------------------------------------------------- Stream-Werkzeuge
def t_find_highlights(ctx, a):
    kws = list(a.get("keywords") or [])
    if a.get("focus") == "funny":
        kws += ["haha", "lustig", "witzig", "funny"]
    task = ctx.streams.start_analyze(ctx.target, {"max_clips": a.get("count", 5), "keywords": kws})
    return {"task_id": task["id"], "change": f"Highlight-Suche gestartet (max. {a.get('count', 5)})"}


def t_list_highlights(ctx, a):
    data = ctx.streams.analysis(ctx.target)
    return {"highlights": [{"index": i + 1, "id": h["id"], "start": h["start"], "end": h["end"],
                            "score": h["score"], "reasons": h["reasons"][:2],
                            "chat": h.get("chat_categories")} for i, h in enumerate(data["highlights"])]}


def _hl(ctx, index: int) -> dict:
    hs = ctx.streams.analysis(ctx.target)["highlights"]
    if not 1 <= index <= len(hs):
        raise StudioError("agent_invalid", f"Clip {index} gibt es nicht (1–{len(hs)}).")
    return hs[index - 1]


def t_trim_highlight(ctx, a):
    h = _hl(ctx, a["clip"])
    start = h["start"] + a.get("cut_start", 0.0)
    end = h["end"] - a.get("cut_end", 0.0)
    new = ctx.streams.update_highlight(ctx.target, h["id"], start, end, None)
    return {"change": f"Clip {a['clip']} jetzt {new['start']:.1f}–{new['end']:.1f} s"}


def t_render_highlights(ctx, a):
    hs = ctx.streams.analysis(ctx.target)["highlights"]
    picks = a.get("clips") or list(range(1, min(len(hs), a.get("count", 5)) + 1))
    ids = []
    for i in picks:
        if not isinstance(i, int) or not 1 <= i <= len(hs):
            raise StudioError("agent_invalid", f"Clip {i} gibt es nicht.")
        ids.append(hs[i - 1]["id"])
    task = ctx.streams.start_render(ctx.target, ids, {
        "reframe_mode": "smart", "remove_silence": a.get("remove_pauses", True),
        "caption_style": "high_energy" if a.get("animated_captions", True) else "clean"})
    return {"task_id": task["id"], "change": f"{len(ids)} vertikale Clips werden gerendert"}


# --------------------------------------------- Darstellung, Audio, Effekte
FOCUS = ("center", "face", "top", "bottom", "left", "right")
FONTS = ("Arial", "Helvetica", "Verdana", "Impact", "Georgia", "DejaVu Sans", "Liberation Sans")
COLOR_NAMES = {"weiß": "#ffffff", "white": "#ffffff", "gelb": "#ffd400", "yellow": "#ffd400",
               "rot": "#ff3030", "red": "#ff3030", "grün": "#20d060", "green": "#20d060",
               "blau": "#3080ff", "blue": "#3080ff", "orange": "#ff8c00", "pink": "#ff4fa0",
               "lila": "#9b5cff", "purple": "#9b5cff", "schwarz": "#000000", "black": "#000000",
               "türkis": "#00d0d0", "cyan": "#00d0d0"}


def _color(value: str) -> str:
    v = value.strip().lower()
    v = COLOR_NAMES.get(v, v)
    import re as _re
    if not _re.fullmatch(r"#[0-9a-f]{6}", v):
        raise StudioError("agent_invalid", f"Farbe '{value}' unbekannt (#RRGGBB oder z. B. gelb, rot, weiß).")
    return v


def _scene_range(p: dict, a: dict) -> list[dict]:
    if a.get("scene"):
        return [_scene(p, a["scene"])]
    return p["scenes"]


def t_zoom(ctx, a):
    p = copy.deepcopy(_project(ctx))
    targets = _scene_range(p, a)
    factor = a.get("factor", 1.4)
    for s in targets:
        if factor <= 1.0:
            s.pop("zoom", None)
        else:
            s["zoom"] = {"factor": factor, "focus": a.get("focus", "face"), "ramp": a.get("ramp", False)}
    where = f"Szene {a['scene']}" if a.get("scene") else "alle Szenen"
    if factor <= 1.0:
        return {**_save(ctx, p, ("scenes",)), "change": f"Zoom entfernt ({where})"}
    note = "" if a.get("focus", "face") != "face" else " — Fokus aus Gesichtserkennung (Mitte, falls keins gefunden)"
    return {**_save(ctx, p, ("scenes",)),
            "change": f"Zoom ×{factor:.2f} ({a.get('focus', 'face')}{', einfahrend' if a.get('ramp') else ''}) "
                      f"für {where}{note}"}


def t_caption_look(ctx, a):
    p = copy.deepcopy(_project(ctx))
    caps = dict(p["captions"])
    parts = []
    if "color" in a:
        caps["color"] = _color(a["color"])
        parts.append(f"Textfarbe {caps['color']}")
    if "highlight_color" in a:
        caps["highlight_color"] = _color(a["highlight_color"])
        parts.append(f"Hervorhebung {caps['highlight_color']}")
    if "font" in a:
        caps["font"] = a["font"]
        parts.append(f"Schrift {a['font']}")
    if "position" in a:
        caps["position"] = a["position"]
        parts.append({"top": "oben", "middle": "Mitte", "bottom": "unten"}[a["position"]])
    if "size" in a:
        caps["size"] = a["size"]
        parts.append(f"Größe {a['size']:.0%}")
    if not parts:
        raise StudioError("agent_invalid", "Keine Untertitel-Änderung angegeben.")
    p["captions"] = caps
    return {**_save(ctx, p, ("captions",)), "change": "Untertitel: " + ", ".join(parts)}


def _audio_files(ctx) -> list[dict]:
    from ..studio.audio import AUDIO_EXT, list_music
    out = [{"track": f"library:{m['id']}", "name": m["name"], "duration": m["duration"], "source": "Bibliothek"}
           for m in list_music()]
    import os
    media = os.path.join(ctx.svc.store.dir(ctx.target), "media")
    if os.path.isdir(media):
        for n in sorted(os.listdir(media)):
            if os.path.splitext(n)[1].lower() in AUDIO_EXT:
                out.append({"track": f"project:{n}", "name": n, "source": "Projekt"})
    return out


def t_list_audio(ctx, a):
    files = _audio_files(ctx)
    return {"audio": files, "note": "" if files else
            "Keine Musik/Effekte vorhanden — Audiodatei in die Mediathek oder ins Projekt hochladen."}


def _pick_track(ctx, wanted: str) -> str:
    files = _audio_files(ctx)
    if not files:
        raise StudioError("agent_invalid", "Keine Audiodateien vorhanden — bitte zuerst Musik/Effekt hochladen.")
    w = (wanted or "").lower()
    for f in files:
        if w and (w == f["track"].lower() or w in f["name"].lower()):
            return f["track"]
    if not w:
        return files[0]["track"]
    raise StudioError("agent_invalid", f"Audio '{wanted}' nicht gefunden. Vorhanden: "
                      + ", ".join(f["name"] for f in files[:8]))


def t_music(ctx, a):
    p = copy.deepcopy(_project(ctx))
    if a.get("remove"):
        p["music"] = {**p["music"], "track": None}
        return {**_save(ctx, p, ("music",)), "change": "Hintergrundmusik entfernt"}
    track = _pick_track(ctx, a.get("track", ""))
    p["music"] = {**p["music"], "track": track, "volume": a.get("volume", p["music"].get("volume", 0.25)),
                  "ducking": a.get("ducking", True)}
    return {**_save(ctx, p, ("music",)),
            "change": f"Musik {track.split(':', 1)[1]} ({p['music']['volume']:.0%}, Ducking "
                      f"{'an' if p['music']['ducking'] else 'aus'})"}


def t_sfx(ctx, a):
    p = copy.deepcopy(_project(ctx))
    s = _scene(p, a["scene"])
    track = _pick_track(ctx, a.get("track", ""))
    fx = list(s.get("sfx") or [])
    if len(fx) >= 5:
        raise StudioError("agent_invalid", "Höchstens 5 Effekte pro Szene.")
    fx.append({"track": track, "at": a.get("at", 0.0), "volume": a.get("volume", 0.8)})
    s["sfx"] = fx
    return {**_save(ctx, p, ("scenes",)),
            "change": f"Soundeffekt {track.split(':', 1)[1]} in Szene {a['scene']} bei {a.get('at', 0.0):.1f} s"}


def t_loudness(ctx, a):
    p = copy.deepcopy(_project(ctx))
    p["audio"] = {"loudnorm": a.get("enabled", True), "target_lufs": a.get("target_lufs", -14.0)}
    return {**_save(ctx, p, ("audio",)),
            "change": (f"Lautheit wird auf {p['audio']['target_lufs']:.0f} LUFS normalisiert"
                       if p["audio"]["loudnorm"] else "Lautheitsnormalisierung aus")}


def t_title(ctx, a):
    from ..studio import social_copy
    data = social_copy.local(_project(ctx))
    return {"suggestions": data, "change": "Titel/Beschreibung lokal vorgeschlagen (nicht gespeichert)",
            "note": "Regelbasierte Vorschläge aus dem Skript — keine Reichweitenprognose."}


def t_thumbnails(ctx, a):
    import os
    from ..studio import thumbnails
    renders = ctx.svc.list_renders(ctx.target)
    if not renders:
        raise StudioError("agent_invalid", "Noch kein Render vorhanden — zuerst Vorschau oder Export rendern.")
    rid = renders[0]["render_id"]
    out = os.path.join(ctx.svc.store.dir(ctx.target), "renders", f"{rid}_thumbs")
    thumbs = thumbnails.suggest(ctx.svc.render_file(ctx.target, rid), out)
    return {"render_id": rid, "thumbnails": thumbs,
            "change": f"{len(thumbs)} Thumbnail-Vorschläge aus dem letzten Render (Bildqualität, keine Klickprognose)"}


def t_clip_variant(ctx, a):
    h = _hl(ctx, a["clip"])
    new = ctx.streams.update_highlight(ctx.target, h["id"], None, None, None, a["variant"])
    return {"change": f"Clip {a['clip']}: Variante {a['variant']} ({new['start']:.1f}–{new['end']:.1f} s)"}


def t_list_variants(ctx, a):
    h = _hl(ctx, a["clip"])
    return {"variants": h.get("variants") or [],
            "note": "Eignung ist eine prüfbare Heuristik (Ereignis enthalten, Satzgrenzen, Länge), keine Viralitätsprognose."}


N = {"type": "number"}
I = {"type": "integer", "minimum": 1}
TOOLS: dict[str, Tool] = {t.name: t for t in [
    Tool("get_project_state", "Aktuellen Projektzustand (Szenen, Einstellungen) lesen.", "project",
         {}, mutating=False, run=t_state),
    Tool("trim_scene", "Szene kürzen: Sekunden vorne (cut_start) und/oder hinten (cut_end) entfernen.",
         "project", {"scene": I, "cut_start": {**N, "minimum": 0, "maximum": 60},
                     "cut_end": {**N, "minimum": 0, "maximum": 60}}, ("scene",), run=t_trim_scene),
    Tool("split_scene", "Szene nach einem Wort teilen.", "project",
         {"scene": I, "after_word": I}, ("scene",), run=t_split_scene),
    Tool("merge_scenes", "Szene mit der folgenden zusammenführen.", "project", {"scene": I},
         ("scene",), run=t_merge_scenes),
    Tool("move_scene", "Szene an eine Position verschieben (1 = Anfang).", "project",
         {"scene": I, "to": I}, ("scene", "to"), run=t_move_scene),
    Tool("delete_scene", "Szene löschen.", "project", {"scene": I}, ("scene",), run=t_delete_scene),
    Tool("set_scene_text", "Text einer Szene ersetzen.", "project",
         {"scene": I, "text": {"type": "string"}}, ("scene", "text"), run=t_set_text),
    Tool("remove_silence", "Pausen zwischen Szenen entfernen.", "project", {}, run=t_remove_pauses),
    Tool("change_caption_style", "Untertitel-Stil ändern.", "project",
         {"style": {"type": "string", "enum": list(CAPTION_STYLES)}}, ("style",), run=t_caption_style),
    Tool("add_transition", "Übergang setzen (eine Szene oder alle).", "project",
         {"type": {"type": "string", "enum": list(TRANSITIONS)}, "scene": I,
          "duration": {**N, "minimum": 0.1, "maximum": 1.5}}, ("type",), run=t_transition),
    Tool("adjust_audio", "Musik-/Stimmlautstärke (0–2), Sprechtempo (0,5–2), Ducking.", "project",
         {"music_volume": {**N, "minimum": 0, "maximum": 1}, "voice_volume": {**N, "minimum": 0, "maximum": 2},
          "voice_speed": {**N, "minimum": 0.5, "maximum": 2}, "ducking": {"type": "boolean"}},
         run=t_adjust_audio),
    Tool("generate_hook_variants", "Projekt-Kopien mit unterschiedlichen Hooks anlegen.", "project",
         {"count": {"type": "integer", "minimum": 1, "maximum": 4}}, run=t_hook_variants),
    Tool("zoom_scene", "Punch-in-Zoom auf eine Szene (oder alle): Faktor 1–2,5, Fokus (face = Gesichtserkennung), "
         "optional langsam einfahrend. factor 1 entfernt den Zoom.", "project",
         {"scene": I, "factor": {**N, "minimum": 1, "maximum": 2.5},
          "focus": {"type": "string", "enum": list(FOCUS)}, "ramp": {"type": "boolean"}}, run=t_zoom),
    Tool("set_caption_appearance", "Untertitel-Farbe, Hervorhebungsfarbe, Schrift, Position, Größe.", "project",
         {"color": {"type": "string"}, "highlight_color": {"type": "string"},
          "font": {"type": "string", "enum": list(FONTS)},
          "position": {"type": "string", "enum": ["bottom", "middle", "top"]},
          "size": {**N, "minimum": 0.6, "maximum": 1.6}}, run=t_caption_look),
    Tool("list_audio", "Verfügbare Musik/Soundeffekte (Bibliothek + Projekt) auflisten.", "project", {},
         mutating=False, run=t_list_audio),
    Tool("add_background_music", "Hintergrundmusik setzen (Name aus list_audio) oder entfernen.", "project",
         {"track": {"type": "string"}, "volume": {**N, "minimum": 0, "maximum": 1},
          "ducking": {"type": "boolean"}, "remove": {"type": "boolean"}}, run=t_music),
    Tool("add_sound_effect", "Soundeffekt in eine Szene legen (Sekunde ab Szenenbeginn).", "project",
         {"scene": I, "track": {"type": "string"}, "at": {**N, "minimum": 0, "maximum": 120},
          "volume": {**N, "minimum": 0, "maximum": 2}}, ("scene",), run=t_sfx),
    Tool("normalize_loudness", "Lautheit beim Export normalisieren (EBU R128, Standard −14 LUFS).", "project",
         {"enabled": {"type": "boolean"}, "target_lufs": {**N, "minimum": -24, "maximum": -9}},
         run=t_loudness),
    Tool("generate_title", "Titel, Beschreibung und Hashtags lokal vorschlagen (nichts wird gespeichert).",
         "project", {}, mutating=False, run=t_title),
    Tool("generate_thumbnail", "Thumbnail-Vorschläge aus dem letzten Render erzeugen.", "project", {},
         mutating=False, run=t_thumbnails),
    Tool("render_preview", "Schnelle Vorschau rendern.", "project", {}, run=t_render_preview),
    Tool("export_video", "Finales Video rendern.", "project", {}, confirm=True, run=t_export,
         cost_note="kostenlos, außer das Projekt nutzt bezahlte Anbieter (Budget greift)"),
    Tool("find_highlights", "Highlights im Stream finden.", "stream",
         {"count": {"type": "integer", "minimum": 1, "maximum": 20},
          "keywords": {"type": "array"}, "focus": {"type": "string", "enum": ["any", "funny"]}},
         run=t_find_highlights),
    Tool("list_highlights", "Gefundene Highlights auflisten.", "stream", {}, mutating=False,
         run=t_list_highlights),
    Tool("trim_clip", "Highlight-Clip kürzen (Sekunden vorne/hinten).", "stream",
         {"clip": I, "cut_start": {**N, "minimum": 0, "maximum": 60},
          "cut_end": {**N, "minimum": 0, "maximum": 60}}, ("clip",), run=t_trim_highlight),
    Tool("list_clip_variants", "Varianten (kurz/ausgewogen/mehr Kontext) eines Clips mit Eignung zeigen.",
         "stream", {"clip": I}, ("clip",), mutating=False, run=t_list_variants),
    Tool("set_clip_variant", "Variante eines Clips wählen: short, balanced oder context.", "stream",
         {"clip": I, "variant": {"type": "string", "enum": ["short", "balanced", "context"]}},
         ("clip", "variant"), run=t_clip_variant),
    Tool("render_clips", "Highlights als vertikale Clips rendern.", "stream",
         {"clips": {"type": "array"}, "count": {"type": "integer", "minimum": 1, "maximum": 20},
          "remove_pauses": {"type": "boolean"}, "animated_captions": {"type": "boolean"}},
         confirm=True, run=t_render_highlights),
]}

# Bewusst NICHT verfügbar (ehrliche Antwort statt Scheinfunktion)
UNSUPPORTED = {
    "translate": "Übersetzen geht über den Workflow „Video übersetzen“ (eigenes Projekt aus dem Video).",
    "track": "Durchgehende Objektverfolgung (Tracking) gibt es nicht; Zoom nutzt einen festen Fokus je "
             "Szene, Stream-Clips folgen Gesichtern per Smart-Reframe.",
    "keyframe": "Freie Keyframes gibt es nicht; Zoom kann statisch oder einfahrend sein.",
    "broll": "B-Roll per Chat ist nicht angebunden — im Editor über „B-Roll vorschlagen“ (Pexels/Pixabay/Mediathek).",
}


def for_context(kind: str) -> list[Tool]:
    return [t for t in TOOLS.values() if t.context == kind]
