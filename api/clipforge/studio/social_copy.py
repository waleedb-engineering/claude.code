"""Titel, Beschreibung, Hashtags, Keywords und Call-to-Action je Plattform.

- local: aus dem Videotext (Schlagwörter nach Häufigkeit/Länge), kostenlos.
- anthropic: Claude formuliert Varianten (kostenpflichtig, Budget/Bestätigung).
Vorschläge werden NICHT automatisch gespeichert; der Nutzer übernimmt und
bearbeitet sie im Publishing-Entwurf. Keine Reichweiten-Versprechen.
"""

from __future__ import annotations

import json
import re
from collections import Counter

from .broll import keywords as _kw
from .errors import ProviderError, StudioError
from .credentials import secret

LIMITS = {  # Titel, Beschreibung/Caption, max. Hashtags
    "youtube_shorts": (100, 5000, 5),
    "tiktok": (150, 2200, 5),
    "instagram_reels": (150, 2200, 8),
    "x": (100, 280, 2),
}
CTA = {
    "de": {"youtube_shorts": "Abonnieren für mehr.", "tiktok": "Folge für Teil 2!",
           "instagram_reels": "Speichern & teilen, wenn es hilft.", "x": "Was meint ihr?"},
    "en": {"youtube_shorts": "Subscribe for more.", "tiktok": "Follow for part 2!",
           "instagram_reels": "Save & share if this helps.", "x": "What do you think?"},
}
LLM_CALL = None  # Test-Hook (system, prompt) -> str
USD_PER_CALL = 0.01  # Richtwert für einen Claude-Aufruf dieser Größe


def _text(project: dict) -> tuple[str, str]:
    scenes = project.get("scenes") or []
    hook = next((s["text"] for s in scenes if s.get("kind") == "hook" and s.get("text")), "")
    body = " ".join(s.get("text") or "" for s in scenes)
    return (hook or (scenes[0]["text"] if scenes else "")), body


def _first_sentence(text: str, limit: int) -> str:
    sent = re.split(r"(?<=[.!?])\s+", text.strip())[0] if text.strip() else ""
    if len(sent) <= limit:
        return sent
    cut = sent[:limit].rsplit(" ", 1)[0]
    return cut.rstrip(",;:") + "…"


def keywords(project: dict, limit: int = 10) -> list[str]:
    _, body = _text(project)
    words = _kw(body, 50)
    counts = Counter(w for w in re.findall(r"[a-zäöüß]{4,}", body.lower()) if w in words)
    return [w for w, _ in sorted(counts.items(), key=lambda x: (-x[1], -len(x[0])))][:limit]


def local(project: dict) -> dict:
    lang = project.get("language") or "de"
    hook, body = _text(project)
    kws = keywords(project)
    out = {}
    for platform, (tmax, dmax, hmax) in LIMITS.items():
        tags = [k.replace(" ", "") for k in kws[:hmax]]
        if platform == "youtube_shorts" and "shorts" not in tags:
            tags = tags[:hmax - 1] + ["shorts"]
        title = _first_sentence(project.get("title") if project.get("title") not in (
            None, "", "Neues Video", "New video") else hook, tmax)
        summary = _first_sentence(body[len(hook):].strip() or body, 220)
        cta = CTA.get(lang, CTA["de"])[platform]
        desc = " ".join(x for x in (summary, cta) if x)
        if platform == "x":
            tag_str = " ".join("#" + t for t in tags)
            room = dmax - len(tag_str) - 2
            desc = _first_sentence(title + " " + cta, max(40, room))
        out[platform] = {"title": title, "description": desc[:dmax], "hashtags": tags,
                         "cta": cta}
    return {"engine": "local", "keywords": kws, "platforms": out, "cost_usd": 0.0}


_SYSTEM = ("Du schreibst Social-Media-Texte für Kurzvideos. Antworte NUR mit JSON: "
           '{"keywords":[...],"platforms":{"youtube_shorts":{"title":"","description":"",'
           '"hashtags":[],"cta":""},"tiktok":{...},"instagram_reels":{...},"x":{...}}}. '
           "Keine Reichweiten-Versprechen, keine irreführenden Aussagen, Sprache wie das Video.")


def with_llm(project: dict) -> dict:
    hook, body = _text(project)
    prompt = json.dumps({"language": project.get("language"), "title": project.get("title"),
                         "hook": hook, "text": body[:4000], "limits": LIMITS},
                        ensure_ascii=False)
    if LLM_CALL is not None:
        raw = LLM_CALL(_SYSTEM, prompt)
    else:
        from ..config import get_settings
        settings = get_settings()
        if not secret("ANTHROPIC_API_KEY"):
            raise StudioError("credential_not_set", "Kein Anthropic-Schlüssel hinterlegt.", 409)
        try:
            import anthropic
            client = anthropic.Anthropic(api_key=secret("ANTHROPIC_API_KEY"),
                                         timeout=settings.llm_timeout_seconds)
            resp = client.messages.create(model=settings.llm_model, max_tokens=2000,
                                          system=_SYSTEM,
                                          messages=[{"role": "user", "content": prompt}])
            raw = "".join(getattr(b, "text", "") for b in resp.content)
        except Exception as exc:  # noqa: BLE001
            raise ProviderError("anthropic", f"Textvorschläge fehlgeschlagen ({type(exc).__name__})") from exc
    m = re.search(r"\{.*\}", raw, re.S)
    try:
        data = json.loads(m.group(0) if m else raw)
    except (ValueError, AttributeError):
        raise ProviderError("anthropic", "Antwort war kein JSON") from None
    base = local(project)
    for platform, (tmax, dmax, hmax) in LIMITS.items():
        got = (data.get("platforms") or {}).get(platform) or {}
        cur = base["platforms"][platform]
        cur.update({
            "title": str(got.get("title") or cur["title"])[:tmax],
            "description": str(got.get("description") or cur["description"])[:dmax],
            "hashtags": [str(h).lstrip("#").replace(" ", "")[:40] for h in
                         (got.get("hashtags") or cur["hashtags"])][:hmax],
            "cta": str(got.get("cta") or cur["cta"])[:120]})
    base["keywords"] = [str(k)[:40] for k in (data.get("keywords") or base["keywords"])][:15]
    base["engine"], base["cost_usd"] = "anthropic", USD_PER_CALL
    return base
