"""Content-Package-Generator: bereit-zum-Posten-Texte je Clip.

Zwei Ebenen wie beim Scoring (scoring.py):
  1) generate_rule_based() — immer verfügbar, ohne API, rein aus dem
                              Clip-Transkript abgeleitet.
  2) generate_llm()        — optionale Verstärkung via Claude; schlägt der
                              Aufruf fehl (kein Key, Netzwerkfehler, Parsing),
                              wird automatisch auf die Regel-Variante
                              zurückgefallen. Niemals eine harte Abhängigkeit
                              von ANTHROPIC_API_KEY.

WICHTIG / EHRLICH: Keine Viralitätsgarantie, keine erfundenen Fakten. Alle
Texte werden ausschließlich aus dem tatsächlichen Clip-Transkript abgeleitet.
"""

from __future__ import annotations

import json
import re

from .config import Settings
from .models import ScoreBreakdown, ScoredClip

_DE_STOPWORDS = {
    "der", "die", "das", "und", "ist", "nicht", "ich", "du", "wir", "ein",
    "eine", "für", "mit", "auf", "im", "zu", "den", "des", "dem", "aber",
    "oder", "wenn", "weil", "von", "es", "sich", "auch", "so", "man", "war",
    "sind", "hat", "haben", "wird", "werden", "noch", "nur", "schon", "kann",
}
_EN_STOPWORDS = {
    "the", "and", "is", "not", "i", "you", "we", "a", "an", "for", "with",
    "on", "in", "to", "of", "but", "or", "if", "because", "this", "that",
    "it", "are", "was", "were", "have", "has", "will", "can", "just", "so",
}

_BASE_HASHTAGS = ["#shorts", "#viral", "#fyp", "#reels", "#contentcreator"]


def detect_language(text: str, fallback: str = "de") -> str:
    """Sehr einfache Stopwort-Heuristik (DE/EN). Kein NLP, kein API-Call."""
    tokens = re.findall(r"[a-zA-ZäöüÄÖÜß']+", text.lower())
    if not tokens:
        return fallback
    de_hits = sum(1 for t in tokens if t in _DE_STOPWORDS)
    en_hits = sum(1 for t in tokens if t in _EN_STOPWORDS)
    if de_hits == 0 and en_hits == 0:
        return fallback
    return "de" if de_hits >= en_hits else "en"


def _snippet(text: str, max_words: int = 8) -> str:
    words = text.strip().split()
    if not words:
        return ""
    cut = words[:max_words]
    out = " ".join(cut).strip(" .,;:!?\"'")
    if len(words) > max_words:
        out += "…"
    return out


def _keywords(text: str, language: str, limit: int = 3) -> list[str]:
    stop = _DE_STOPWORDS if language == "de" else _EN_STOPWORDS
    tokens = [t for t in re.findall(r"[a-zA-ZäöüÄÖÜß']{4,}", text.lower()) if t not in stop]
    counts: dict[str, int] = {}
    for t in tokens:
        counts[t] = counts.get(t, 0) + 1
    ranked = sorted(counts.items(), key=lambda kv: (-kv[1], tokens.index(kv[0])))
    return [w for w, _ in ranked[:limit]]


def _hashtags(keywords: list[str], extra: list[str]) -> list[str]:
    tags = list(_BASE_HASHTAGS) + list(extra)
    for kw in keywords:
        tag = "#" + re.sub(r"[^a-zA-Z0-9äöüÄÖÜß]", "", kw)
        if len(tag) > 1 and tag not in tags:
            tags.append(tag)
    # dedupe, max 8
    seen: list[str] = []
    for t in tags:
        if t not in seen:
            seen.append(t)
    return seen[:8]


_TEMPLATES = {
    "de": {
        "provokant": 'Niemand redet über das hier: "{snip}"',
        "neugierig": 'Was steckt wirklich hinter "{snip}"?',
        "emotional": 'Das hier hat mich überrascht: "{snip}"',
        "edukativ": 'Das lernst du in diesem Clip: "{snip}"',
        "direkt": '"{snip}" — hier ist der Clip.',
        "cta": "Folge für mehr.",
        "comment": "Was denkst du darüber? 👇",
        "yt_title": "{snip}",
        "yt_desc": "{excerpt} {cta}",
        "tiktok_caption": "{hook} {cta}",
        "reels_caption": "{hook} {cta}",
    },
    "en": {
        "provokant": 'Nobody talks about this: "{snip}"',
        "neugierig": 'What\'s really behind "{snip}"?',
        "emotional": 'This caught me off guard: "{snip}"',
        "edukativ": "Here's what you'll learn: \"{snip}\"",
        "direkt": '"{snip}" — watch the clip.',
        "cta": "Follow for more.",
        "comment": "What do you think? 👇",
        "yt_title": "{snip}",
        "yt_desc": "{excerpt} {cta}",
        "tiktok_caption": "{hook} {cta}",
        "reels_caption": "{hook} {cta}",
    },
}

_SAFETY_NOTE = {
    "de": {
        "virality_guarantee": (
            "Keine Garantie für Viralität oder Reichweite — alle Texte sind "
            "Vorschläge auf Basis des Transkripts."
        ),
        "score_disclaimer": (
            "Der Performance-Potential-Score ist nur eine Wahrscheinlichkeits-"
            "Einschätzung, keine Erfolgsgarantie."
        ),
    },
    "en": {
        "virality_guarantee": (
            "No guarantee of virality or reach — all texts are suggestions "
            "derived from the transcript."
        ),
        "score_disclaimer": (
            "The performance-potential score is only a probability estimate, "
            "not a guarantee of success."
        ),
    },
}


def _platform_recommendation(breakdown: ScoreBreakdown, language: str) -> dict:
    signals = {
        "hook": breakdown.hook,
        "emotion": breakdown.emotion,
        "clarity": breakdown.clarity,
        "payoff": breakdown.payoff,
    }
    top_signal = max(signals, key=lambda k: signals[k])
    mapping = {
        "hook": ("tiktok", {
            "de": "Stärkstes Signal ist der Hook — TikTok belohnt starke erste Sekunden.",
            "en": "Strongest signal is the hook — TikTok rewards a strong first few seconds.",
        }),
        "emotion": ("instagram_reels", {
            "de": "Stärkstes Signal ist Emotion — passt gut zu Instagram Reels.",
            "en": "Strongest signal is emotion — fits well with Instagram Reels.",
        }),
        "clarity": ("youtube_shorts", {
            "de": "Stärkstes Signal ist Klarheit — eignet sich gut für YouTube Shorts.",
            "en": "Strongest signal is clarity — works well for YouTube Shorts.",
        }),
        "payoff": ("youtube_shorts", {
            "de": "Starke Pointe — eignet sich gut für YouTube Shorts.",
            "en": "Strong payoff — works well for YouTube Shorts.",
        }),
    }
    platform, reasons = mapping[top_signal]
    return {
        "best_platform": platform,
        "reason": reasons[language],
    }


def generate_rule_based(
    text: str, score: float, breakdown: ScoreBreakdown, language: str
) -> dict:
    lang = language if language in _TEMPLATES else "de"
    tpl = _TEMPLATES[lang]
    snip = _snippet(text) or ("Clip" if lang == "en" else "Clip")
    excerpt = text.strip()[:200]
    keywords = _keywords(text, lang)

    hook_variants = {
        "provokant": tpl["provokant"].format(snip=snip),
        "neugierig": tpl["neugierig"].format(snip=snip),
        "emotional": tpl["emotional"].format(snip=snip),
        "edukativ": tpl["edukativ"].format(snip=snip),
        "direkt": tpl["direkt"].format(snip=snip),
    }
    primary_hook = snip[:1].upper() + snip[1:] if snip else hook_variants["neugierig"]

    yt_hashtags = _hashtags(keywords, ["#youtubeshorts"])
    tiktok_hashtags = _hashtags(keywords, ["#tiktok", "#foryou"])
    reels_hashtags = _hashtags(keywords, ["#instagram", "#explore"])

    youtube_shorts = {
        "title": tpl["yt_title"].format(snip=snip)[:100],
        "description": tpl["yt_desc"].format(excerpt=excerpt, cta=tpl["cta"]).strip(),
        "hashtags": yt_hashtags,
    }
    tiktok = {
        "caption": tpl["tiktok_caption"].format(hook=primary_hook, cta=tpl["cta"]),
        "hashtags": tiktok_hashtags,
        "pinned_comment": tpl["comment"],
    }
    instagram_reels = {
        "caption": tpl["reels_caption"].format(hook=primary_hook, cta=tpl["cta"]),
        "hashtags": reels_hashtags,
        "pinned_comment": tpl["comment"],
    }
    platform_recommendation = _platform_recommendation(breakdown, lang)

    variant_a = {
        "name": "Aggressiver Hook" if lang == "de" else "Aggressive Hook",
        "hook": hook_variants["provokant"],
        "caption": tpl["tiktok_caption"].format(hook=hook_variants["provokant"], cta=tpl["cta"]),
        "hashtags": tiktok_hashtags,
    }
    variant_b = {
        "name": "Emotional",
        "hook": hook_variants["emotional"],
        "caption": tpl["reels_caption"].format(hook=hook_variants["emotional"], cta=tpl["cta"]),
        "hashtags": reels_hashtags,
    }
    variant_c = {
        "name": "Edukativ" if lang == "de" else "Educational",
        "hook": hook_variants["edukativ"],
        "caption": tpl["yt_desc"].format(excerpt=hook_variants["edukativ"], cta=tpl["cta"]),
        "hashtags": yt_hashtags,
    }

    return {
        "primary_hook": primary_hook,
        "hook_variants": hook_variants,
        "youtube_shorts": youtube_shorts,
        "tiktok": tiktok,
        "instagram_reels": instagram_reels,
        "platform_recommendation": platform_recommendation,
        "variant_a": variant_a,
        "variant_b": variant_b,
        "variant_c": variant_c,
        "safety_note": _SAFETY_NOTE[lang],
    }


# --------------------------------------------------------------------------
# LLM-Verstärkung (Claude) — optional, fällt bei jedem Fehler zurück
# --------------------------------------------------------------------------

_LLM_SYSTEM = (
    "Du bist ein erfahrener Short-Form-Content-Stratege (TikTok, Reels, "
    "Shorts). Du erzeugst publizierfertige Texte AUSSCHLIESSLICH aus dem "
    "gegebenen Transkript-Ausschnitt. Du erfindest KEINE Fakten und "
    "versprichst NIEMALS Viralität oder garantierte Reichweite. Antworte "
    "ausschließlich mit gültigem JSON, keine Erklärtexte davor/danach."
)

_LLM_INSTRUCTIONS = """\
Erzeuge ein Content-Paket für den folgenden Clip (Sprache: %s, Score: %.1f).

Gib JSON in EXAKT diesem Schema zurück:
{
  "primary_hook": "...",
  "hook_variants": {"provokant": "...", "neugierig": "...", "emotional": "...", "edukativ": "...", "direkt": "..."},
  "youtube_shorts": {"title": "...", "description": "...", "hashtags": ["#..", ".."]},
  "tiktok": {"caption": "...", "hashtags": ["#..", ".."], "pinned_comment": "..."},
  "instagram_reels": {"caption": "...", "hashtags": ["#..", ".."], "pinned_comment": "..."},
  "platform_recommendation": {"best_platform": "tiktok|instagram_reels|youtube_shorts", "reason": "..."},
  "variant_a": {"name": "Aggressiver Hook", "hook": "...", "caption": "...", "hashtags": ["#.."]},
  "variant_b": {"name": "Emotional", "hook": "...", "caption": "...", "hashtags": ["#.."]},
  "variant_c": {"name": "Edukativ", "hook": "...", "caption": "...", "hashtags": ["#.."]},
  "safety_note": {"virality_guarantee": "...", "score_disclaimer": "..."}
}

Transkript-Ausschnitt:
\"\"\"%s\"\"\"
"""

_REQUIRED_KEYS = (
    "primary_hook", "hook_variants", "youtube_shorts", "tiktok",
    "instagram_reels", "platform_recommendation", "variant_a", "variant_b",
    "variant_c", "safety_note",
)


def _extract_json(raw: str) -> dict:
    raw = raw.strip()
    if raw.startswith("```"):
        raw = re.sub(r"^```[a-zA-Z]*\n?", "", raw)
        raw = re.sub(r"\n?```$", "", raw).strip()
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        match = re.search(r"\{.*\}", raw, re.DOTALL)
        if not match:
            raise
        return json.loads(match.group(0))


def generate_llm(text: str, score: float, language: str, settings: Settings) -> dict | None:
    """Erzeugt ein Content-Paket via Claude. Gibt bei jedem Fehler None zurück."""
    try:
        import anthropic

        client = anthropic.Anthropic(api_key=settings.anthropic_api_key)
        prompt = _LLM_INSTRUCTIONS % (language, score, text)
        resp = client.messages.create(
            model=settings.llm_model,
            max_tokens=1536,
            system=_LLM_SYSTEM,
            messages=[{"role": "user", "content": prompt}],
        )
        raw = "".join(
            block.text for block in resp.content if getattr(block, "type", "") == "text"
        )
        data = _extract_json(raw)
        if not all(k in data for k in _REQUIRED_KEYS):
            return None
        return data
    except Exception:  # noqa: BLE001 — bewusst: nie die Pipeline killen
        return None


def generate_content_package(
    clip: ScoredClip, settings: Settings, language: str | None = None
) -> tuple[dict, bool]:
    """Liefert (content_package, used_llm). Funktioniert immer ohne API-Key."""
    lang = language if language in ("de", "en") else detect_language(clip.text)
    base = generate_rule_based(clip.text, clip.score, clip.breakdown, lang)
    if not settings.llm_available:
        return base, False
    enhanced = generate_llm(clip.text, clip.score, lang, settings)
    if enhanced:
        return enhanced, True
    return base, False
