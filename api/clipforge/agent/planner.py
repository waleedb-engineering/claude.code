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
COST = {"rules": 0.0, "ollama": 0.0, "anthropic": 0.01, "openai": 0.005}  # Richtwert je Nachricht

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

    if re.search(r"zoom|heranzoom|ranzoom", t):
        notes.append(UNSUPPORTED["zoom"])
    if re.search(r"übersetz|translate|deutsche version|english version|synchronisiert", t):
        notes.append(UNSUPPORTED["translate"])
    if re.search(r"\b(gelb|rot|blau|grün|weiß|yellow|red|blue|green)\w*\b.*untertitel|caption", t) and \
            re.search(r"gelb|rot|blau|grün|yellow|red|blue|green", t):
        notes.append(UNSUPPORTED["caption_color"])

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
        if re.search(r"vorschau|preview", t):
            steps.append({"tool": "render_preview", "args": {}})
        if re.search(r"exportier|final render|export", t):
            steps.append({"tool": "export_video", "args": {}})
    else:
        nums = "|".join(NUM)
        m = re.search(rf"\b(\d+|{nums})\s+(?:[\wäöüß-]+\s+){{0,2}}(tiktoks?|clips?|shorts?|highlights?|momente?)", t)
        want = int(_n(m.group(1)) or 5) if m else 5
        if re.search(r"analysier|finde|find|suche|erstelle|create", t) and re.search(
                r"stream|moment|highlight|tiktok|clip|short", t) and not re.search(r"clip\s*\d", t):
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


def llm_plan(engine: str, message: str, state: dict, kind: str) -> tuple[list[dict], str]:
    tools = [t.schema() for t in for_context(kind)]
    from ..skills import planner_context
    system = SYSTEM + ("\n\n" + planner_context() if planner_context() else "")
    user = f"Projektzustand:\n{json.dumps(state, ensure_ascii=False)[:6000]}\n\nBefehl: {message}"
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
        data = _http_json(f"{ollama_url()}/api/chat", {
            "model": os.environ.get("CLIPFORGE_OLLAMA_MODEL", "qwen2.5:7b"), "stream": False,
            "messages": msgs, "tools": fn_tools}, {}, timeout=180)
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


def engines() -> list[dict]:
    from ..studio.credentials import secret
    out = [{"id": "rules", "label": "Regelbasiert (lokal, kostenlos)", "ready": True, "paid": False,
            "live_verified": True}]
    try:
        url = ollama_url()
        req = urllib.request.Request(f"{url}/api/tags")
        with urllib.request.urlopen(req, timeout=1.5) as resp:  # noqa: S310 — localhost
            models = [m.get("name") for m in json.loads(resp.read()).get("models", [])]
        ready = True
    except Exception:  # noqa: BLE001 — Ollama läuft nicht
        models, ready = [], False
    out.append({"id": "ollama", "label": "Ollama (lokales LLM, kostenlos)", "ready": ready,
                "paid": False, "models": models, "live_verified": False,
                "hint": "" if ready else "Ollama installieren (ollama.com) und z. B. `ollama pull qwen2.5:7b`."})
    out.append({"id": "anthropic", "label": "Claude (kostenpflichtig)", "ready": bool(secret("ANTHROPIC_API_KEY")),
                "paid": True, "cost_per_message_usd": COST["anthropic"], "live_verified": False})
    out.append({"id": "openai", "label": "OpenAI (kostenpflichtig)", "ready": bool(secret("OPENAI_API_KEY")),
                "paid": True, "cost_per_message_usd": COST["openai"], "live_verified": False})
    return out
