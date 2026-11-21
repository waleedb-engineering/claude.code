"""Planer: Nutzerbefehl → strukturierter Plan aus freigegebenen Werkzeugen.

Engines:
- rules     lokal, kostenlos, deterministisch (deutsche/englische Muster)
- ollama    lokales LLM über http://127.0.0.1:11434 (Tool-Calling), kostenlos
- anthropic Claude (Tool-Use), kostenpflichtig, Schlüssel nötig
- openai    OpenAI (Function-Calling), kostenpflichtig, Schlüssel nötig

LLMs dürfen nur Werkzeuge aus tools.for_context() vorschlagen; jeder Aufruf
wird anschließend validiert. Kein LLM erzeugt Shell- oder FFmpeg-Befehle.
"""

from __future__ import annotations

import json
import os
import re
import urllib.error
import urllib.request

from ..studio.errors import ProviderError, StudioError
from .tools import UNSUPPORTED, for_context

NUM = {"eins": 1, "ein": 1, "einen": 1, "eine": 1, "zwei": 2, "drei": 3, "vier": 4, "fünf": 5, "sechs": 6,
       "sieben": 7, "acht": 8, "neun": 9, "zehn": 10, "one": 1, "two": 2, "three": 3, "four": 4,
       "five": 5, "six": 6, "seven": 7, "eight": 8, "nine": 9, "ten": 10}
ORD = {"erste": 1, "ersten": 1, "zweite": 2, "zweiten": 2, "dritte": 3, "dritten": 3, "vierte": 4,
       "vierten": 4, "fünfte": 5, "fünften": 5, "letzte": -1, "letzten": -1, "first": 1,
       "second": 2, "third": 3, "last": -1}
COST = {"rules": 0.0, "ollama": 0.0, "anthropic": 0.01, "openai": 0.005, "gemini": 0.0}  # Richtwert je Nachricht
# Preis hängt vom Tarif ab (Gratis-Kontingent möglich) → nie ohne ausdrückliche Bestätigung,
# aber kein erfundener Betrag
PAID_UNKNOWN = {"gemini"}
MEMORY_RECENT = 6


def memory_context(history: list[dict]) -> str:
    """Gesprächsgedächtnis je Projekt: letzte Wechsel wörtlich, Älteres zusammengefasst."""
    turns = [h for h in history if h.get("role") in ("user", "assistant")]
    if not turns:
        return ""
    recent, older = turns[-MEMORY_RECENT * 2:], turns[:-MEMORY_RECENT * 2]
    lines = []
    if older:
        done: dict[str, int] = {}
        asks = []
        for h in older:
            if h["role"] == "user":
                asks.append(h.get("text", "")[:60])
            for st in ((h.get("plan") or {}).get("steps") or []):
                if (h.get("plan") or {}).get("status") == "executed":
                    done[st["tool"]] = done.get(st["tool"], 0) + 1
        lines.append(f"Zusammenfassung früherer Schritte ({len(older)} Nachrichten): "
                     + (", ".join(f"{k}×{v}" for k, v in done.items()) or "keine ausgeführten Änderungen")
                     + (f"; frühere Wünsche u. a.: {' | '.join(asks[-3:])}" if asks else ""))
    for h in recent:
        if h["role"] == "user":
            lines.append(f"Nutzer: {h.get('text', '')[:200]}")
        else:
            plan = h.get("plan") or {}
            steps = ", ".join(f"{st['tool']}({json.dumps(st.get('args', {}), ensure_ascii=False)[:80]})"
                              for st in plan.get("steps") or [])
            lines.append(f"Assistent: {steps or h.get('text', '')[:120]} [{plan.get('status', '')}"
                         f"{', rückgängig' if plan.get('undone') else ''}]")
    return "\n".join(lines)[-3000:]

# Test-Hook: (engine, system, message, tools) -> list[{"tool":…, "args":…}] | str
LLM_CALL = None


def _n(token: str) -> float | None:
    token = token.lower().replace(",", ".")
    if token in NUM:
        return float(NUM[token])
    try:
        return float(token)
    except ValueError:
        return None


def _index(text: str, word: str, count: int) -> int | None:
    m = re.search(rf"\b{word}\s*(?:nr\.?\s*)?(\d+)\b", text)
    if m:
        return int(m.group(1))
    m = re.search(rf"\b{word}\s+(eins|zwei|drei|vier|fünf|sechs|sieben|acht|neun|zehn|one|two|three|four|five)\b", text)
    if m:
        return NUM[m.group(1)]
    m = re.search(rf"\b(\w+)\s+{word}\b", text)
    if m and m.group(1) in ORD:
        v = ORD[m.group(1)]
        return count if v == -1 else v
    return None


def rule_plan(message: str, kind: str, count: int) -> tuple[list[dict], list[str]]:
    """→ (Schritte, Hinweise). Leere Schritte = nicht verstanden/nicht unterstützt."""
    t = " " + message.lower().strip() + " "
    steps, notes = [], []
    unit = "clip" if kind == "stream" else "szene"
    idx = _index(t, "clip", count) or _index(t, "szene", count) or _index(t, "scene", count)

    if re.search(r"verfolg|tracking|track the|folge dem", t):
        notes.append(UNSUPPORTED["track"])
    if re.search(r"b-roll|broll", t):
        notes.append(UNSUPPORTED["broll"])

    # Kürzen: "entferne die ersten 4 Sekunden", "kürze die letzten zwei Sekunden"
    for m in re.finditer(r"(ersten|first|letzten|last)\s+(\w+(?:[.,]\d+)?)\s+(sekunden|sek|s|seconds)\b", t):
        secs = _n(m.group(2))
        if secs is None:
            continue
        where = "cut_start" if m.group(1) in ("ersten", "first") else "cut_end"
        target = idx or (1 if count == 1 else None)
        if target is None:
            notes.append(f"Welche {'Clip' if kind == 'stream' else 'Szene'}? Bitte Nummer nennen.")
            continue
        steps.append({"tool": "trim_clip" if kind == "stream" else "trim_scene",
                      "args": {"clip" if kind == "stream" else "scene": target, where: secs}})

    if kind == "project":
        m = re.search(r"(szene|scene)\s*(\d+).{0,40}(an den anfang|nach vorne|to the start|als erstes)", t) or \
            re.search(r"(höhepunkt|highlight).{0,30}(an den anfang|nach vorne)", t)
        if m and m.group(1) in ("szene", "scene"):
            steps.append({"tool": "move_scene", "args": {"scene": int(m.group(2)), "to": 1}})
        elif m:
            notes.append("Welche Szene ist der Höhepunkt? Bitte Nummer nennen (z. B. „Szene 4 an den Anfang“).")
        m = re.search(r"(lösche|entferne|delete|remove)\s+(die\s+)?(szene|scene)\s*(\d+)", t)
        if m:
            steps.append({"tool": "delete_scene", "args": {"scene": int(m.group(4))}})
        m = re.search(r"(teile|split)\s+(die\s+)?(szene|scene)\s*(\d+)", t)
        if m:
            steps.append({"tool": "split_scene", "args": {"scene": int(m.group(4))}})
        m = re.search(r"(verbinde|führe|merge)\s+(die\s+)?(szene|scene)\s*(\d+)", t)
        if m:
            steps.append({"tool": "merge_scenes", "args": {"scene": int(m.group(4))}})
        if re.search(r"(animiert|karaoke|wort für wort|animated)\w*.{0,20}(untertitel|caption)|(untertitel|caption).{0,20}(animiert|karaoke)", t):
            steps.append({"tool": "change_caption_style", "args": {"style": "karaoke"}})
        elif re.search(r"(fett|groß|bold).{0,20}(untertitel|caption)", t):
            steps.append({"tool": "change_caption_style", "args": {"style": "bold"}})
        elif re.search(r"(keine|ohne|no).{0,10}(untertitel|caption)", t):
            steps.append({"tool": "change_caption_style", "args": {"style": "none"}})
        if re.search(r"pause|stille|silence", t) and re.search(r"entfern|raus|weg|remove|kürz", t):
            steps.append({"tool": "remove_silence", "args": {}})
        trans = [("fade", r"überblend|fade|weich"), ("zoom", r"zoom-übergang|zoom übergang"),
                 ("slide", r"slide|schieb"), ("wipe", r"wisch|wipe")]
        if re.search(r"übergang|übergänge|transition", t):
            kind_t = next((k for k, rx in trans if re.search(rx, t)), "auto")
            steps.append({"tool": "add_transition", "args": {"type": kind_t}})
        if re.search(r"dynamisch|dynamic|schneller|tempo", t):
            steps.append({"tool": "add_transition", "args": {"type": "smooth", "duration": 0.3}})
            steps.append({"tool": "adjust_audio", "args": {"voice_speed": 1.1}})
            notes.append("„Dynamischer“: kurze weiche Übergänge und etwas schnelleres Sprechtempo (1,1×) — "
                         "bewusst nicht hektisch.")
        m = re.search(r"musik\s+(leiser|lauter|quieter|louder)", t)
        if m:
            steps.append({"tool": "adjust_audio", "args": {"music_volume": 0.12 if m.group(1) in ("leiser", "quieter") else 0.4}})
        m = re.search(r"stimme\s+(leiser|lauter)", t)
        if m:
            steps.append({"tool": "adjust_audio", "args": {"voice_volume": 0.8 if m.group(1) == "leiser" else 1.3}})
        m = re.search(r"(\w+)\s+(versionen|varianten|variants).{0,30}(hook|einstieg)", t)
        if m:
            steps.append({"tool": "generate_hook_variants", "args": {"count": int(_n(m.group(1)) or 3)}})
        # Übersetzen / Synchronisieren
        if re.search(r"übersetz|translate|deutsche version|english version|synchronis|auf deutsch|in german|"
                     r"auf englisch|in english|ins deutsche|ins englische", t):
            target = "en" if re.search(r"englisch|english", t) else "de"
            mode = "dub" if re.search(r"stimme|voice|synchron|dub|vertonung|sprecher", t) else "subtitles"
            steps.append({"tool": "translate_video", "args": {"target": target, "mode": mode,
                                                              "engine": "argos"}})
            notes.append("Übersetzung lokal mit Argos (kostenlos, Sprachmodell muss installiert sein). "
                         "Für bessere Qualität „engine anthropic“ (kostenpflichtig) wählen.")
        # Split-Screen
        if re.search(r"split.?screen|geteilte?r? bildschirm|gameplay (unten|darunter|below)", t):
            gp = re.search(r"(?:gameplay|video)\s+[„\"']([^“\"']+)[“\"']", message, re.I)
            steps.append({"tool": "create_split_screen", "args": {**({"gameplay": gp.group(1)} if gp else {}),
                                                                   **({"scene": idx} if idx else {})}})
        # Text-Element: Text „Abonnieren!“ von 2 bis 5 Sekunden (oben)
        m = re.search(r"text\s+[„\"']([^“\"']{1,120})[“\"']", message, re.I)
        if m:
            rng = re.search(r"(?:von|from)\s+(\d+(?:[.,]\d+)?)\s*(?:s|sek\w*)?\s+(?:bis|to)\s+(\d+(?:[.,]\d+)?)", t)
            a0, a1 = (_n(rng.group(1)), _n(rng.group(2))) if rng else (0.0, 3.0)
            pos = re.search(r"\b(oben|mitte|unten|top|middle|bottom)\b", t)
            col = re.search(r"\b(weiß|white|gelb|yellow|rot|red|grün|green|blau|blue|orange|pink)\w*", t)
            steps.append({"tool": "timeline_add_text", "args": {
                "text": m.group(1), "start": a0 or 0.0, "duration": max(0.5, (a1 or 3.0) - (a0 or 0.0)),
                **({"position": {"oben": "top", "top": "top", "mitte": "middle", "middle": "middle"}.get(pos.group(1), "bottom")} if pos else {}),
                **({"color": col.group(1)} if col else {})}})
        # Logo/Bild als Overlay: „Leg das Logo oben rechts drüber“
        m = re.search(r"(logo|bild|grafik|sticker|overlay)\b", t)
        if m and re.search(r"leg|füg|setz|add|platzier|zeig|einblend", t):
            corner = next((v for k, v in (("oben rechts", "top_right"), ("oben links", "top_left"),
                                          ("unten rechts", "bottom_right"), ("unten links", "bottom_left"),
                                          ("top right", "top_right"), ("top left", "top_left"),
                                          ("mitte", "center")) if k in t), "top_right")
            name = re.search(r"[„\"']([^“\"']+\.(?:png|jpg|jpeg|webp|mp4|mov))[“\"']", message, re.I)
            steps.append({"tool": "timeline_add_media", "args": {
                "media": name.group(1) if name else (m.group(1) if m.group(1) == "logo" else ""),
                "track_kind": "overlay", "position": corner, "scale": 0.22,
                "duration": 5.0, "fade": 0.3 if re.search(r"einblend|blende\w*\b.*\bein\b|fade|weich", t) else 0.0}})
        if re.search(r"keyframe", t) and not steps:
            notes.append("Keyframes: z. B. „timeline_keyframe“ über Claude/Ollama oder im Editor im "
                         "Eigenschaften-Bereich setzen (Element, Eigenschaft, Zeit, Wert).")
        # Zoom: „zoom auf das Gesicht in Szene 2“, „zoom langsam rein“, „kein zoom“
        if re.search(r"zoom|heranzoom|ranzoom|reinzoom", t) and not re.search(r"zoom-übergang|zoom übergang", t):
            if re.search(r"(kein|ohne|entfern|remove|no)\w*\s+(den\s+)?zoom|zoom\s+(entfernen|weg|aus)", t):
                steps.append({"tool": "zoom_scene", "args": {**({"scene": idx} if idx else {}), "factor": 1.0}})
            else:
                focus = "face" if re.search(r"gesicht|face|person|streamer|facecam", t) else "center"
                for word, f in (("links", "left"), ("left", "left"), ("rechts", "right"), ("right", "right"),
                                ("oben", "top"), ("unten", "bottom")):
                    if re.search(rf"\b{word}\b", t):
                        focus = f
                m2 = re.search(r"(\d+(?:[.,]\d+)?)\s*(x|×|fach)", t)
                factor = min(2.5, max(1.05, _n(m2.group(1)) or 1.4)) if m2 else (1.6 if re.search(r"stark|nah|close", t) else 1.3)
                steps.append({"tool": "zoom_scene", "args": {**({"scene": idx} if idx else {}), "factor": factor,
                                                              "focus": focus,
                                                              "ramp": bool(re.search(r"langsam|einfahr|slow|ramp", t))}})
                if re.search(r"wenn|when|sobald|beim|während", t) and not idx:
                    notes.append("Zoom gilt je Szene. Für einen Moment-genauen Zoom die Szene nennen "
                                 "(z. B. „Szene 3“) oder im Stream-Clip den Gesichts-Reframe nutzen.")
        # Untertitel-Aussehen
        if re.search(r"untertitel|caption|subtitle", t):
            look = {}
            col_rx = r"\b(weiß|white|gelb|yellow|rot|red|grün|green|blau|blue|orange|pink|lila|purple|türkis|cyan|schwarz|black)\w*"
            hl = re.search(r"hervorheb|highlight|aktuelle wort|markier|wichtige wörter|important words", t)
            for cm in re.finditer(col_rx, t):
                # Farbe nach dem Hervorhebungs-Hinweis (oder direkt davor bei „rot hervorheben“) → Hervorhebung
                after_hl = hl and (cm.start() > hl.start() or 0 <= hl.start() - cm.end() <= 12)
                key = "highlight_color" if after_hl else "color"
                look.setdefault(key, cm.group(1))
            pos = re.search(r"\b(oben|top|mitte|middle|center|unten|bottom)\b", t)
            if pos:
                look["position"] = {"oben": "top", "top": "top", "mitte": "middle", "middle": "middle",
                                    "center": "middle", "unten": "bottom", "bottom": "bottom"}[pos.group(1)]
            if re.search(r"größer|bigger|larger", t):
                look["size"] = 1.25
            elif re.search(r"kleiner|smaller", t):
                look["size"] = 0.8
            for f in ("impact", "verdana", "arial", "georgia", "helvetica"):
                if f in t:
                    look["font"] = f.capitalize()
            if look:
                steps.append({"tool": "set_caption_appearance", "args": look})
        # Musik / Effekte / Lautheit
        m = re.search(r"(füge|leg|add|setz)\w*\s+(?:(?:eine?n?|die|some)\s+)?(?:hintergrund)?(musik|music)"
                      r"(?:\s+(?:[„\"']([^“\"']{1,60})[“\"']|([\w.-]+)))?", t)
        if m or re.search(r"(mit|with)\s+(hintergrund)?musik", t):
            name = ((m.group(3) or m.group(4) or "").strip()) if m else ""
            if name in ("hinzu", "ein", "unter", "dazu", "rein", "drunter", "und", "and", "an", "mit", "leiser",
                        "lauter", "bitte"):
                name = ""
            steps.append({"tool": "add_background_music", "args": {"track": name}})
        elif re.search(r"(keine|ohne|entfern\w*)\s+(die\s+)?musik|musik\s+(entfernen|weg|raus)", t):
            steps.append({"tool": "add_background_music", "args": {"remove": True}})
        if re.search(r"soundeffekt|sound effect|sfx|geräusch", t):
            at = re.search(r"(?:bei|at)\s+(\d+(?:[.,]\d+)?)\s*(?:s|sek)", t)
            name = re.search(r"(?:effekt|sfx|sound effect|geräusch)\s+[„\"']?([\w.-]+)", t)
            target = idx or 1
            steps.append({"tool": "add_sound_effect", "args": {
                "scene": target, "at": _n(at.group(1)) if at else 0.0,
                **({"track": name.group(1)} if name and name.group(1) not in ("in", "bei", "at", "zu") else {})}})
        if re.search(r"lautheit|loudness|lufs|normalisier|gleich laut|zu leise", t):
            steps.append({"tool": "normalize_loudness", "args": {"enabled": not re.search(r"(keine|ohne|aus)\s+\w*\s*normal", t)}})
        if re.search(r"titel|title|beschreibung|hashtag", t) and re.search(r"vorschl|schlag\w*\b.*\bvor\b|generier|schreib|ideen|suggest|generate", t):
            steps.append({"tool": "generate_title", "args": {}})
        if re.search(r"thumbnail|vorschaubild", t):
            steps.append({"tool": "generate_thumbnail", "args": {}})
        if re.search(r"vorschau|preview", t) and not re.search(r"vorschaubild", t):
            steps.append({"tool": "render_preview", "args": {}})
        if re.search(r"exportier|final render|export", t):
            steps.append({"tool": "export_video", "args": {}})
    else:
        nums = "|".join(NUM)
        m = re.search(rf"\b(\d+|{nums})\s+(?:[\wäöüß-]+\s+){{0,2}}(tiktoks?|clips?|shorts?|highlights?|momente?|szenen?|scenes?|stellen)", t)
        want = int(_n(m.group(1)) or 5) if m else 5
        if re.search(r"analysier|finde|find|suche|erstelle|create", t) and re.search(
                r"stream|moment|highlight|tiktok|clip|short|szene|stelle", t) and not re.search(r"clip\s*\d", t) \
                and not idx:
            focus = "funny" if re.search(r"lustig|funny|witzig|lach", t) else "any"
            steps.append({"tool": "find_highlights", "args": {"count": want, "focus": focus}})
            if re.search(r"erstelle|create|mach", t):
                notes.append("Nach der Analyse: „Rendere die Clips“ erzeugt die vertikalen Videos "
                             "(mit Bestätigung).")
        if re.search(r"render|exportier|erstelle die clips|mach die clips", t) and not steps:
            clips = [int(x) for x in re.findall(r"\b(\d+)\b", t) if 0 < int(x) <= 20] if "clip" in t else []
            steps.append({"tool": "render_clips", "args": {
                **({"clips": clips} if clips else {"count": min(count, 5) or 5}),
                "remove_pauses": not re.search(r"pausen behalten|keep pauses", t)}})
        var = re.search(r"\b(kürzer|kurze|short|ausgewogen|balanced|mehr kontext|more context|länger|kontext)", t)
        if var and idx and re.search(r"variante|version|fassung|clip", t):
            v = {"kürzer": "short", "kurze": "short", "short": "short", "ausgewogen": "balanced",
                 "balanced": "balanced"}.get(var.group(1), "context")
            steps.append({"tool": "set_clip_variant", "args": {"clip": idx, "variant": v}})
        elif re.search(r"variante|varianten|variants", t) and idx:
            steps.append({"tool": "list_clip_variants", "args": {"clip": idx}})
        # „… und zoome beim Höhepunkt auf mein Gesicht“ → mit Gesichts-Tracking (enger) rendern
        if idx and re.search(r"zoom|näher|nah ran", t) and re.search(r"gesicht|face|streamer|mich|facecam", t):
            steps.append({"tool": "render_clips", "args": {"clips": [idx], "framing": "track", "track_zoom": 1.4,
                                                            "remove_pauses": True}})
            notes.append("Zoom auf das Gesicht: Clip wird mit Gesichts-Tracking (1,4× enger) gerendert — "
                         "der Ausschnitt folgt dem Gesicht über den ganzen Clip.")
        if re.search(r"liste|zeig|show|list", t) and not steps:
            steps.append({"tool": "list_highlights", "args": {}})
    return steps, notes


# ---------------------------------------------------------------- LLMs
SYSTEM = ("Du bist der Schnitt-Assistent von ClipForge. Antworte NUR mit Werkzeugaufrufen aus der "
          "Liste. Nummern sind 1-basiert. Wenn etwas nicht mit den Werkzeugen geht, rufe kein "
          "Werkzeug auf und erkläre kurz warum. Keine Shell-Befehle.")


def _http_json(url: str, body: dict, headers: dict, timeout: float = 60) -> dict:
    req = urllib.request.Request(url, data=json.dumps(body).encode(), method="POST",
                                 headers={"Content-Type": "application/json", **headers})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:  # noqa: S310 — feste Endpunkte
            return json.loads(resp.read(4 * 1024 * 1024))
    except urllib.error.HTTPError as exc:
        raise ProviderError("llm", f"HTTP {exc.code}") from None
    except (OSError, ValueError) as exc:
        raise ProviderError("llm", f"nicht erreichbar ({type(exc).__name__})") from None


def ollama_url() -> str:
    url = os.environ.get("CLIPFORGE_OLLAMA_URL", "http://127.0.0.1:11434").rstrip("/")
    host = url.split("//", 1)[-1].split("/", 1)[0].split(":")[0]
    if host not in ("127.0.0.1", "localhost", "::1", "host.docker.internal"):
        raise StudioError("validation_error", "Ollama nur auf diesem Rechner (localhost) erlaubt.")
    return url


def llm_plan(engine: str, message: str, state: dict, kind: str, memory: str = "") -> tuple[list[dict], str]:
    tools = [t.schema() for t in for_context(kind)]
    from ..skills import planner_context
    system = SYSTEM + ("\n\n" + planner_context() if planner_context() else "")
    user = (f"Projektzustand:\n{json.dumps(state, ensure_ascii=False)[:6000]}\n\n"
            + (f"Bisheriger Verlauf in diesem Projekt:\n{memory}\n\n" if memory else "")
            + f"Befehl: {message}")
    if LLM_CALL is not None:
        out = LLM_CALL(engine, system, user, tools)
        return (out, "") if isinstance(out, list) else ([], str(out))
    from ..studio.credentials import secret
    if engine == "anthropic":
        key = secret("ANTHROPIC_API_KEY")
        if not key:
            raise StudioError("credential_not_set", "Kein Anthropic-Schlüssel hinterlegt.", 409)
        from ..config import get_settings
        data = _http_json("https://api.anthropic.com/v1/messages", {
            "model": get_settings().llm_model, "max_tokens": 1024, "system": system,
            "tools": tools, "messages": [{"role": "user", "content": user}]},
            {"x-api-key": key, "anthropic-version": "2023-06-01"})
        calls = [{"tool": b["name"], "args": b.get("input") or {}} for b in data.get("content", [])
                 if b.get("type") == "tool_use"]
        text = " ".join(b.get("text", "") for b in data.get("content", []) if b.get("type") == "text")
        return calls, text.strip()
    if engine == "gemini":
        return _gemini(system, user, tools)
    fn_tools = [{"type": "function", "function": {"name": t["name"], "description": t["description"],
                                                  "parameters": t["input_schema"]}} for t in tools]
    msgs = [{"role": "system", "content": system}, {"role": "user", "content": user}]
    if engine == "openai":
        key = secret("OPENAI_API_KEY")
        if not key:
            raise StudioError("credential_not_set", "Kein OpenAI-Schlüssel hinterlegt.", 409)
        data = _http_json("https://api.openai.com/v1/chat/completions", {
            "model": os.environ.get("CLIPFORGE_OPENAI_AGENT_MODEL", "gpt-4o-mini"),
            "messages": msgs, "tools": fn_tools}, {"Authorization": f"Bearer {key}"})
        msg = (data.get("choices") or [{}])[0].get("message") or {}
    elif engine == "ollama":
        from . import ollama as ol
        st = ol.status()
        if not st["reachable"]:
            raise ProviderError("ollama", "nicht erreichbar")
        if not st["model"]:
            raise ProviderError("ollama", st["model_reason"])
        data = _http_json(f"{ollama_url()}/api/chat", {
            "model": st["model"], "stream": False, "options": {"temperature": 0},
            "messages": msgs, "tools": fn_tools}, {},
            timeout=float(os.environ.get("CLIPFORGE_OLLAMA_TIMEOUT", "120")))
        msg = data.get("message") or {}
    else:
        raise StudioError("validation_error", "Unbekannte KI-Engine.")
    calls = []
    for c in msg.get("tool_calls") or []:
        fn = c.get("function") or {}
        args = fn.get("arguments") or {}
        if isinstance(args, str):
            try:
                args = json.loads(args)
            except ValueError:
                args = {}
        calls.append({"tool": fn.get("name"), "args": args})
    return calls, str(msg.get("content") or "").strip()


def _gemini_schema(schema: dict) -> dict:
    """Gemini verlangt bei Arrays ein 'items'-Schema."""
    props = {}
    for name, spec in (schema.get("properties") or {}).items():
        spec = dict(spec)
        if spec.get("type") == "array" and "items" not in spec:
            spec["items"] = {"type": "integer" if name == "clips" else "string"}
        props[name] = spec
    out = {"type": "object", "properties": props}
    if schema.get("required"):
        out["required"] = schema["required"]
    return out


def gemini_model() -> str:
    return os.environ.get("CLIPFORGE_GEMINI_MODEL", "gemini-2.0-flash")


def _gemini(system: str, user: str, tools: list[dict]) -> tuple[list[dict], str]:
    from ..studio.credentials import secret
    key = secret("GEMINI_API_KEY")
    if not key:
        raise StudioError("credential_not_set", "Kein Gemini-Schlüssel hinterlegt.", 409)
    decls = [{"name": t["name"], "description": t["description"],
              "parameters": _gemini_schema(t["input_schema"])} for t in tools]
    data = _http_json(f"https://generativelanguage.googleapis.com/v1beta/models/{gemini_model()}:generateContent", {
        "systemInstruction": {"parts": [{"text": system}]},
        "contents": [{"role": "user", "parts": [{"text": user}]}],
        "tools": [{"functionDeclarations": decls}],
        "generationConfig": {"temperature": 0}}, {"x-goog-api-key": key})
    parts = ((data.get("candidates") or [{}])[0].get("content") or {}).get("parts") or []
    calls = [{"tool": p["functionCall"].get("name"), "args": p["functionCall"].get("args") or {}}
             for p in parts if isinstance(p.get("functionCall"), dict)]
    text = " ".join(p.get("text", "") for p in parts if p.get("text"))
    return calls, text.strip()


def engines() -> list[dict]:
    from ..studio.credentials import secret
    out = [{"id": "rules", "label": "Regelbasiert (lokal, kostenlos)", "ready": True, "paid": False,
            "live_verified": True}]
    from . import ollama as ol
    st = ol.status()
    out.append({"id": "ollama", "label": "Ollama (lokales LLM, kostenlos)",
                "ready": bool(st["reachable"] and st["model"]), "paid": False,
                "models": [m["name"] for m in st["models"]], "model": st["model"], "live_verified": False,
                "hint": "" if st["reachable"] and st["model"] else
                (st.get("hint") or st["model_reason"] + ". " + st["recommendation"].get("command", ""))})
    from ..config import get_settings
    out.append({"id": "anthropic", "label": "Claude (kostenpflichtig)", "ready": bool(secret("ANTHROPIC_API_KEY")),
                "paid": True, "cost_per_message_usd": COST["anthropic"], "live_verified": False,
                "model": get_settings().llm_model})
    out.append({"id": "openai", "label": "OpenAI (kostenpflichtig)", "ready": bool(secret("OPENAI_API_KEY")),
                "paid": True, "cost_per_message_usd": COST["openai"], "live_verified": False,
                "model": os.environ.get("CLIPFORGE_OPENAI_AGENT_MODEL", "gpt-4o-mini")})
    out.append({"id": "gemini", "label": "Gemini (Kosten je nach Google-Tarif)", "ready": bool(secret("GEMINI_API_KEY")),
                "paid": True, "cost_per_message_usd": None, "live_verified": False, "model": gemini_model(),
                "note": "Preis abhängig vom Tarif (Gratis-Kontingent möglich) — jede Nachricht braucht Bestätigung."})
    return out
