"""Performance-Potential-Scoring der Kandidaten-Clips.

Zwei Ebenen:
  1) heuristic_score()  — immer verfügbar, ohne API, transparent & erklärbar.
  2) llm_score()        — optionale Verstärkung via Claude: bessere Begründung,
                          Plattform-Metadaten und Hook-Varianten.

WICHTIG / EHRLICH: Der Score ist eine WAHRSCHEINLICHKEITS-Einschätzung auf
Basis messbarer Signale (Hook, Klarheit, Emotion, Tempo, Pointe). Er ist
KEINE Garantie für Viralität und wird auch nie so kommuniziert.
"""

from __future__ import annotations

import json
import re

from .config import Settings
from .models import (
    CandidateClip,
    HookVariant,
    PlatformMetadata,
    ScoreBreakdown,
    ScoredClip,
)

# Signalwörter für die Heuristik (DE + EN, bewusst klein gehalten).
_HOOK_OPENERS = {
    "warum", "wieso", "weshalb", "wie", "was", "wenn", "stell", "wusstest",
    "niemand", "jeder", "hör", "stopp", "achtung", "vergiss", "das", "hier",
    "why", "how", "what", "if", "stop", "imagine", "never", "everyone",
    "nobody", "secret", "listen",
}
_EMOTION_WORDS = {
    "krass", "wahnsinn", "unglaublich", "schock", "fehler", "geheimnis",
    "gefährlich", "liebe", "hass", "angst", "wut", "geld", "erfolg", "scheitern",
    "verrückt", "schlimm", "best", "schlecht", "wichtig", "endlich", "niemals",
    "crazy", "insane", "mistake", "secret", "danger", "love", "money",
    "fail", "success", "shock", "amazing", "worst", "best", "never", "always",
}
_PAYOFF_WORDS = {
    "deshalb", "darum", "also", "fazit", "ergebnis", "lösung", "deswegen",
    "merke", "wichtig", "am ende", "schluss", "pointe",
    "so", "therefore", "result", "lesson", "takeaway", "finally", "bottom line",
}


def _clamp(v: float, lo: float = 0.0, hi: float = 100.0) -> float:
    return max(lo, min(hi, v))


def _tokens(text: str) -> list[str]:
    return [t for t in re.findall(r"[\wäöüÄÖÜß']+", text.lower()) if t]


def heuristic_score(clip: CandidateClip, settings: Settings) -> ScoreBreakdown:
    """Transparente, regelbasierte Bewertung eines Clips."""
    text = clip.text
    tokens = _tokens(text)
    n = max(1, len(tokens))
    dur = max(0.001, clip.duration)

    # --- Hook: erste ~8 Wörter ---
    opener = tokens[:8]
    hook = 35.0
    if opener and opener[0] in _HOOK_OPENERS:
        hook += 30.0
    if any(t in _HOOK_OPENERS for t in opener):
        hook += 10.0
    if "?" in text[: max(20, len(text) // 4)]:
        hook += 15.0
    if any(ch.isdigit() for ch in " ".join(opener)):
        hook += 10.0
    hook = _clamp(hook)

    # --- Emotion: Dichte emotionaler Signalwörter + Ausrufezeichen ---
    emo_hits = sum(1 for t in tokens if t in _EMOTION_WORDS)
    emotion = _clamp(30.0 + (emo_hits / n) * 400.0 + text.count("!") * 6.0)

    # --- Pacing: Wörter pro Sekunde, ideal ~2.2–3.0 wps ---
    wps = n / dur
    ideal = 2.6
    pacing = _clamp(100.0 - abs(wps - ideal) * 28.0)

    # --- Clarity: vollständige Sätze, nicht zu lang/kurz, Satzzeichen ---
    sentences = [s for s in re.split(r"[.!?]+", text) if s.strip()]
    avg_sent = n / max(1, len(sentences))
    clarity = 60.0
    if 6 <= avg_sent <= 22:
        clarity += 25.0
    if text.strip().endswith((".", "!", "?")):
        clarity += 10.0
    clarity = _clamp(clarity)

    # --- Payoff: Abschluss-/Schlusssignale im letzten Drittel ---
    tail = " ".join(tokens[int(n * 0.6):])
    payoff = 40.0
    if any(w in tail for w in _PAYOFF_WORDS):
        payoff += 30.0
    if text.strip().endswith((".", "!")):
        payoff += 15.0
    payoff = _clamp(payoff)

    return ScoreBreakdown(
        hook=round(hook, 1),
        clarity=round(clarity, 1),
        emotion=round(emotion, 1),
        pacing=round(pacing, 1),
        payoff=round(payoff, 1),
    )


def _heuristic_reason(b: ScoreBreakdown) -> str:
    ranked = sorted(
        {"Hook": b.hook, "Klarheit": b.clarity, "Emotion": b.emotion,
         "Tempo": b.pacing, "Pointe": b.payoff}.items(),
        key=lambda kv: kv[1],
        reverse=True,
    )
    strong = ranked[0][0]
    weak = ranked[-1][0]
    return (
        f"Heuristik: stärkstes Signal ist '{strong}', schwächstes '{weak}'. "
        f"Score ist eine Wahrscheinlichkeits-Einschätzung, keine Garantie."
    )


def score_heuristic(clip: CandidateClip, settings: Settings) -> ScoredClip:
    b = heuristic_score(clip, settings)
    return ScoredClip(
        start=clip.start,
        end=clip.end,
        text=clip.text,
        score=b.total(),
        breakdown=b,
        reason=_heuristic_reason(b),
        words=clip.words,
        scorer="heuristic",
    )


# --------------------------------------------------------------------------
# LLM-Verstärkung (Claude)
# --------------------------------------------------------------------------

_LLM_SYSTEM = (
    "Du bist ein erfahrener Short-Form-Video-Editor (TikTok, Reels, Shorts). "
    "Du bewertest Transkript-Ausschnitte nach ihrem PERFORMANCE-POTENZIAL. "
    "Du garantierst niemals Viralität — du schätzt Wahrscheinlichkeiten auf "
    "Basis von Hook, Klarheit, Emotion, Tempo und Pointe ein. "
    "Antworte AUSSCHLIESSLICH mit gültigem JSON, keine Erklärtexte davor/danach."
)

_LLM_INSTRUCTIONS = """\
Bewerte den folgenden Clip-Transkript-Ausschnitt.

Gib JSON in EXAKT diesem Schema zurück:
{
  "hook": <0-100>,
  "clarity": <0-100>,
  "emotion": <0-100>,
  "pacing": <0-100>,
  "payoff": <0-100>,
  "reason": "<1-2 Sätze, warum dieser Clip stark/schwach ist>",
  "metadata": {
    "tiktok":    {"title": "...", "description": "...", "hashtags": ["#..", ".."]},
    "reels":     {"title": "...", "description": "...", "hashtags": ["#..", ".."]},
    "shorts":    {"title": "...", "description": "...", "hashtags": ["#..", ".."]}
  },
  "hook_variants": [
    {"label": "Frage",       "text": "<alternative Hook-Zeile>"},
    {"label": "Bold Claim",  "text": "<alternative Hook-Zeile>"},
    {"label": "Zahl/Liste",  "text": "<alternative Hook-Zeile>"}
  ]
}

Transkript-Ausschnitt (Dauer: %.1fs):
\"\"\"%s\"\"\"
"""


def _extract_json(raw: str) -> dict:
    """Robustes Parsen: nimmt das erste {...}-JSON-Objekt aus der Antwort."""
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


def score_llm(clip: CandidateClip, settings: Settings) -> ScoredClip:
    """Bewertet einen Clip mit Claude. Fällt bei Fehlern auf die Heuristik zurück."""
    base = score_heuristic(clip, settings)
    if not settings.llm_available:
        return base

    try:
        import anthropic

        client = anthropic.Anthropic(api_key=settings.anthropic_api_key)
        prompt = _LLM_INSTRUCTIONS % (clip.duration, clip.text)
        resp = client.messages.create(
            model=settings.llm_model,
            max_tokens=1024,
            system=_LLM_SYSTEM,
            messages=[{"role": "user", "content": prompt}],
        )
        raw = "".join(
            block.text for block in resp.content if getattr(block, "type", "") == "text"
        )
        data = _extract_json(raw)

        b = ScoreBreakdown(
            hook=_clamp(float(data["hook"])),
            clarity=_clamp(float(data["clarity"])),
            emotion=_clamp(float(data["emotion"])),
            pacing=_clamp(float(data["pacing"])),
            payoff=_clamp(float(data["payoff"])),
        )
        meta: dict[str, PlatformMetadata] = {}
        for key, md in (data.get("metadata") or {}).items():
            meta[key] = PlatformMetadata(
                title=md.get("title", ""),
                description=md.get("description", ""),
                hashtags=list(md.get("hashtags", [])),
            )
        variants = [
            HookVariant(label=v.get("label", "Variante"), text=v.get("text", ""))
            for v in (data.get("hook_variants") or [])
        ]
        return ScoredClip(
            start=clip.start,
            end=clip.end,
            text=clip.text,
            score=b.total(),
            breakdown=b,
            reason=data.get("reason", base.reason),
            metadata=meta,
            hook_variants=variants,
            words=clip.words,
            scorer="llm",
        )
    except Exception as exc:  # noqa: BLE001 — bewusst: nie die Pipeline killen
        base.reason = f"{base.reason} (LLM-Fallback: {type(exc).__name__})"
        return base


def score_clips(
    clips: list[CandidateClip], settings: Settings
) -> list[ScoredClip]:
    """Bewertet alle Kandidaten und sortiert nach Score (absteigend)."""
    scorer = score_llm if settings.llm_available else score_heuristic
    scored = [scorer(c, settings) for c in clips]
    scored.sort(key=lambda c: c.score, reverse=True)
    return scored
