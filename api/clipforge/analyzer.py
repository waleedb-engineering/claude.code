"""Clip-Analyzer v2 — bessere Kandidaten-Erkennung + nachvollziehbarer Score.

Architektur (modular, mit sauberem Fallback):
  - RuleBasedClipAnalyzer   — Default, ohne API-Key, transparent & deterministisch.
  - OptionalLLMClipAnalyzer  — nur bei API-Key; re-rankt die schon per Timestamp
                               erzeugten Kandidaten (halluziniert KEINE neuen).
  - FallbackChain            — LLM → bei jedem Fehler zurück auf rule_based.

EHRLICH: Der Performance-Potential-Score ist eine Heuristik-Einschätzung,
KEINE Viralitätsgarantie. Qualität hängt vom Transkript ab.
"""

from __future__ import annotations

import json
import re

from .config import Settings
from .content import detect_language
from .models import (
    CandidateClip,
    ScoreBreakdown,
    ScoredClip,
    Transcript,
    TranscriptSegment,
)

ANALYZER_VERSION = "v2"

# Harte Grenzen (Sekunden) + idealer Bereich.
HARD_MIN = 8.0
HARD_MAX = 90.0
IDEAL_MIN = 15.0
IDEAL_MAX = 60.0
IDEAL_SWEET = 45.0  # bester Platform-Fit bis hier

# --- Signalwörter (DE + EN) ---------------------------------------------
_HOOK_OPENERS = {
    "warum", "wieso", "weshalb", "wie", "was", "wann", "wenn", "stell", "wusstest",
    "niemand", "jeder", "hör", "stopp", "achtung", "vergiss", "denk", "glaub",
    "why", "how", "what", "when", "if", "stop", "imagine", "never", "everyone",
    "nobody", "secret", "listen", "think",
}
_QUESTION_WORDS = {"warum", "wieso", "wie", "was", "wann", "wer", "why", "how",
                   "what", "when", "who"}
_EMOTION_WORDS = {
    "krass", "wahnsinn", "unglaublich", "schock", "fehler", "geheimnis",
    "gefährlich", "liebe", "hass", "angst", "wut", "erfolg", "scheitern",
    "verrückt", "schlimm", "endlich", "niemals", "brutal", "hammer",
    "crazy", "insane", "mistake", "danger", "love", "hate", "fear", "fail",
    "success", "shock", "amazing", "worst", "incredible", "wow",
}
_OPINION_WORDS = {
    "beste", "schlechteste", "wahrheit", "falsch", "richtig", "musst", "solltest",
    "niemand", "immer", "nie", "problem", "wichtig", "unpopulär", "ehrlich",
    "best", "worst", "truth", "wrong", "right", "must", "should", "always",
    "problem", "honest", "unpopular", "everyone", "nobody",
}
_PAYOFF_WORDS = {
    "deshalb", "darum", "also", "fazit", "ergebnis", "lösung", "deswegen",
    "merke", "am ende", "schluss", "pointe", "takeaway", "trick", "tipp",
    "so", "therefore", "result", "lesson", "takeaway", "finally", "solution",
}
_LOOP_WORDS = {
    "geheimnis", "grund", "wahrheit", "problem", "aber", "trick", "erst",
    "warte", "bis", "danach", "gleich", "reason", "secret", "truth", "but",
    "until", "then", "problem", "wait", "here's",
}
_CONTEXT_START = {
    "das", "dies", "deshalb", "darum", "deswegen", "also", "aber", "und", "oder",
    "denn", "trotzdem", "außerdem", "er", "sie", "es", "ihn", "ihm", "ihr",
    "this", "that", "it", "but", "and", "or", "so", "therefore", "however",
    "also", "he", "she", "they", "them",
}
_STORY_WORDS = {
    "damals", "früher", "gestern", "einmal", "plötzlich", "dann", "als", "story",
    "geschichte", "erlebt", "passiert", "once", "suddenly", "then", "story",
    "happened", "remember",
}
_HOWTO_WORDS = {
    "so", "schritt", "anleitung", "mach", "tu", "musst", "kannst", "tipp",
    "trick", "step", "how", "guide", "do", "learn", "way",
}
_GENERIC_FILLER = {
    "ähm", "äh", "halt", "eben", "irgendwie", "sozusagen", "quasi", "naja",
    "also", "genau", "joa", "hm", "hmm", "vielleicht", "eigentlich", "einfach",
    "mal", "ok", "okay", "ja", "nö", "ne",
    "like", "um", "uh", "kind", "sort", "basically", "actually", "really",
    "well", "yeah", "just", "stuff", "things", "guess", "gonna", "wanna",
}
_NUMBER_WORDS = {
    "null", "eins", "zwei", "drei", "vier", "fünf", "sechs", "sieben", "acht",
    "neun", "zehn", "elf", "zwölf", "zwanzig", "dreißig", "vierzig", "fünfzig",
    "hundert", "tausend", "millionen", "million", "dreihundert", "neunzig",
    "zero", "one", "two", "three", "four", "five", "six", "seven", "eight",
    "nine", "ten", "eleven", "twelve", "twenty", "thirty", "forty", "fifty",
    "ninety", "hundred", "thousand",
}
_STOPWORDS = {
    "der", "die", "das", "und", "oder", "ein", "eine", "ist", "sind", "war",
    "in", "im", "auf", "mit", "für", "von", "zu", "den", "dem", "des", "ich",
    "du", "er", "sie", "es", "wir", "the", "a", "an", "and", "or", "is", "are",
    "was", "in", "on", "with", "for", "of", "to", "i", "you", "he", "she", "it",
    "we", "they", "this", "that",
}


def _clamp(v: float, lo: float = 0.0, hi: float = 100.0) -> float:
    return max(lo, min(hi, v))


def _tokens(text: str) -> list[str]:
    return [t for t in re.findall(r"[\wäöüÄÖÜß']+", text.lower()) if t]


def _ends_sentence(text: str) -> bool:
    return text.strip().endswith((".", "!", "?", "…"))


# ==========================================================================
# Kandidaten-Erkennung v2
# ==========================================================================

def _clean_start_flags(segments: list[TranscriptSegment]) -> list[bool]:
    """Pro Segment: darf hier ein Clip 'sauber' starten (nicht mitten im Satz)?"""
    flags: list[bool] = []
    prev_end: float | None = None
    prev_text = ""
    for seg in segments:
        gap = (seg.start - prev_end) if prev_end is not None else 999.0
        opener = _tokens(seg.text)[:1]
        strong = bool(opener and opener[0] in _HOOK_OPENERS)
        clean = _ends_sentence(prev_text) or gap >= 0.45 or prev_end is None or strong
        flags.append(clean)
        prev_end = seg.end
        prev_text = seg.text
    return flags


def build_candidates_v2(
    transcript: Transcript, settings: Settings
) -> list[CandidateClip]:
    """Erzeugt überlappende Kandidaten mit sauberen Start-/Endgrenzen.

    Für jeden 'sauberen' Startpunkt wird ein Fenster bis zu einem sauberen
    Satzende im idealen Längenbereich gewachsen. Ergebnis wird später
    dedupliziert und divers ausgewählt.
    """
    segs = transcript.segments
    if not segs:
        return []
    clean = _clean_start_flags(segs)
    candidates: list[CandidateClip] = []
    n = len(segs)

    for i in range(n):
        if not clean[i]:
            continue
        start_t = segs[i].start
        best: CandidateClip | None = None
        for j in range(i, n):
            end_t = segs[j].end
            dur = end_t - start_t
            if dur < HARD_MIN:
                continue
            if dur > HARD_MAX:
                break
            words = []
            for k in range(i, j + 1):
                words.extend(segs[k].words)
            text = " ".join(segs[k].text.strip() for k in range(i, j + 1)).strip()
            cand = CandidateClip(start=start_t, end=end_t, text=text, words=words)
            clean_end = _ends_sentence(segs[j].text)
            # Idealfenster + sauberes Ende → sofort nehmen und Start-Loop weiter.
            if IDEAL_MIN <= dur <= IDEAL_MAX and clean_end:
                best = cand
                break
            # sonst bestes bisher gesehenes (mit sauberem Ende bevorzugt) merken
            if best is None:
                best = cand
            elif clean_end and not _ends_sentence(best.text):
                best = cand
        if best is not None:
            candidates.append(best)

    return candidates


def _jaccard(a: set[str], b: set[str]) -> float:
    if not a or not b:
        return 0.0
    inter = len(a & b)
    union = len(a | b)
    return inter / union if union else 0.0


def _time_overlap(a: CandidateClip | ScoredClip, b: CandidateClip | ScoredClip) -> float:
    lo = max(a.start, b.start)
    hi = min(a.end, b.end)
    if hi <= lo:
        return 0.0
    shorter = min(a.end - a.start, b.end - b.start)
    return (hi - lo) / shorter if shorter > 0 else 0.0


# ==========================================================================
# Score v2 (10 Komponenten)
# ==========================================================================

_WEIGHTS = {
    "hook_strength": 0.18,
    "retention_potential": 0.15,
    "context_independence": 0.12,
    "clarity": 0.10,
    "emotional_intensity": 0.10,
    "information_density": 0.10,
    "share_comment_potential": 0.09,
    "platform_fit": 0.08,
    "uniqueness": 0.05,
    "editability": 0.03,
}


def _content_words(tokens: list[str]) -> list[str]:
    return [t for t in tokens if t not in _STOPWORDS and len(t) > 2]


def score_components_v2(text: str, dur: float) -> dict[str, float]:
    """Berechnet die 10 Score-Komponenten (0–100) aus Transkript + Dauer.

    Die Floors sind bewusst niedrig gehalten: schwacher/generischer Inhalt
    soll klar unter starkem landen (siehe docs/ANALYZER_CALIBRATION.md).
    """
    tokens = _tokens(text)
    n = max(1, len(tokens))
    dur = max(0.001, dur)
    opener = tokens[:8]
    first = tokens[0] if tokens else ""
    head = text[: max(24, len(text) // 4)]

    # Globale Qualitätssignale (Füllwörter, generischer Einstieg)
    filler = sum(1 for t in tokens if t in _GENERIC_FILLER)
    filler_ratio = filler / n
    generic_start = bool(first) and (first in _GENERIC_FILLER or first in _CONTEXT_START)
    starts_hook = bool(first) and first in _HOOK_OPENERS
    starts_question = bool(first) and first in _QUESTION_WORDS

    # 1) hook_strength — starker, kontextfreier Einstieg
    hook = 33.0
    if starts_hook:
        hook += 30.0
    elif any(t in _HOOK_OPENERS or t in _HOWTO_WORDS for t in opener[:4]):
        hook += 15.0
    if "?" in head:
        hook += 18.0
    if any(ch.isdigit() for ch in " ".join(opener)) or any(
        t in _NUMBER_WORDS for t in opener[:5]
    ):
        hook += 10.0
    if any(t in _EMOTION_WORDS or t in _OPINION_WORDS for t in opener[:4]):
        hook += 9.0
    if generic_start:
        hook -= 18.0
    hook -= filler_ratio * 45.0
    hook = _clamp(hook)

    # 2) context_independence — Strafe für Kontext-Referenzen am Anfang
    ctx = 68.0
    if first in _CONTEXT_START:
        ctx -= 40.0
    if len(opener) > 1 and opener[1] in _CONTEXT_START:
        ctx -= 8.0
    if starts_question or starts_hook:
        ctx += 16.0
    ctx = _clamp(ctx)

    # 3) retention_potential — offene Schleife, Spannung, Problem→Lösung
    ret = 34.0
    if any(t in _LOOP_WORDS for t in tokens):
        ret += 18.0
    if "?" in head and any(w in text.lower() for w in _PAYOFF_WORDS):
        ret += 16.0
    if any(t in _OPINION_WORDS for t in tokens):
        ret += 8.0
    tail = " ".join(tokens[int(n * 0.6):])
    if any(w in tail for w in _PAYOFF_WORDS):
        ret += 12.0
    ret -= filler_ratio * 30.0
    ret = _clamp(ret)

    # 4) clarity — verständlich, abgeschlossen, wenig Füller
    sentences = [s for s in re.split(r"[.!?]+", text) if s.strip()]
    avg_sent = n / max(1, len(sentences))
    clarity = 46.0
    if 6 <= avg_sent <= 24:
        clarity += 24.0
    if _ends_sentence(text):
        clarity += 12.0
    clarity -= filler_ratio * 150.0
    clarity = _clamp(clarity)

    # 5) emotional_intensity
    emo_hits = sum(1 for t in tokens if t in _EMOTION_WORDS)
    emotion = _clamp(26.0 + (emo_hits / n) * 380.0 + text.count("!") * 7.0)

    # 6) information_density — Content-Wörter/Anteil + Zahlen
    content = _content_words(tokens)
    cw_ratio = len(content) / n
    numbers = sum(1 for t in tokens if any(ch.isdigit() for ch in t)
                  or t in _NUMBER_WORDS)
    density = _clamp(20.0 + cw_ratio * 80.0 + min(numbers, 4) * 6.0
                     - filler_ratio * 60.0)

    # 7) share_comment_potential — Meinung/Kontroverse
    op_hits = sum(1 for t in tokens if t in _OPINION_WORDS)
    share = _clamp(30.0 + (op_hits / n) * 320.0 + ("?" in text) * 8.0)

    # 8) platform_fit — Dauer + Tempo
    wps = n / dur
    fit = 92.0
    if dur < IDEAL_MIN:
        fit -= (IDEAL_MIN - dur) * 3.0
    elif dur > IDEAL_SWEET:
        fit -= (dur - IDEAL_SWEET) * 1.6
    fit -= abs(wps - 2.6) * 12.0
    fit = _clamp(fit)

    # 9) uniqueness — spezifisch vs. generisch
    uniq_tokens = len(set(content))
    uniqueness = _clamp(26.0 + (uniq_tokens / n) * 95.0 + min(numbers, 3) * 5.0
                        - filler_ratio * 110.0)

    # 10) editability — selbst-abgeschlossen, sauberer Rand
    edit = 54.0
    if _ends_sentence(text):
        edit += 20.0
    if first in _CONTEXT_START:
        edit -= 22.0
    if dur > 75.0:
        edit -= 15.0
    edit = _clamp(edit)

    return {
        "hook_strength": round(hook, 1),
        "context_independence": round(ctx, 1),
        "retention_potential": round(ret, 1),
        "clarity": round(clarity, 1),
        "emotional_intensity": round(emotion, 1),
        "information_density": round(density, 1),
        "share_comment_potential": round(share, 1),
        "platform_fit": round(fit, 1),
        "uniqueness": round(uniqueness, 1),
        "editability": round(edit, 1),
    }


def _aggregate_score(comp: dict[str, float]) -> float:
    """Aggregiert die 10 Komponenten zu einem kalibrierten 0–100-Score.

    Zielbänder (siehe docs/ANALYZER_CALIBRATION.md):
      schwach 35–59 · solide 60–74 · gut 75–84 · sehr stark 85–94 · 95+ selten.
    Die Kalibrierung ist bewusst leicht S-förmig um einen Pivot (~63), damit
    Mittelmaß nicht inflationär nach oben rutscht und nur Clips mit hohen
    Kern-Signalen (Hook/Retention/Kontextfreiheit) die oberen Bänder erreichen.
    """
    raw = sum(comp[k] * w for k, w in _WEIGHTS.items())
    # Lineare Spreizung (Zwei-Punkt-gefittet auf Referenz-Transkripte):
    # enge Rohverteilung (~40–70) → Zielbänder (~44–90).
    calibrated = raw * 1.52 - 16.9
    # 95+ nur, wenn die Kern-Signale wirklich exzellent sind (Deckel sonst 94).
    core = (comp["hook_strength"] + comp["retention_potential"]
            + comp["context_independence"]) / 3.0
    if core < 88.0 and calibrated > 94.0:
        calibrated = 94.0 + (calibrated - 94.0) * 0.15
    return round(_clamp(calibrated), 1)


def _hook_type(text: str) -> str:
    tokens = _tokens(text)
    first = tokens[0] if tokens else ""
    head = text[:40]
    if "?" in head or first in _QUESTION_WORDS:
        return "question"
    if any(ch.isdigit() for ch in " ".join(tokens[:8])):
        return "number"
    if first in _OPINION_WORDS or any(t in _OPINION_WORDS for t in tokens[:6]):
        return "bold_claim"
    if any(t in _STORY_WORDS for t in tokens[:6]):
        return "story"
    return "statement"


def _clip_type(text: str) -> str:
    tl = text.lower()
    tokens = _tokens(text)
    if any(t in _HOWTO_WORDS for t in tokens) and ("?" not in text[:30]):
        return "how_to"
    if any(t in _STORY_WORDS for t in tokens):
        return "story"
    if "problem" in tl and any(w in tl for w in _PAYOFF_WORDS):
        return "problem_solution"
    if any(t in _OPINION_WORDS for t in tokens):
        return "opinion"
    if any(ch.isdigit() for ch in text):
        return "insight_number"
    return "insight"


def _best_platform(comp: dict[str, float], language: str) -> tuple[str, str]:
    hook = comp["hook_strength"]
    emo = comp["emotional_intensity"]
    dens = comp["information_density"]
    share = comp["share_comment_potential"]
    clar = comp["clarity"]
    if hook >= 70 and emo >= 55:
        return ("TikTok", "Starker Hook + Emotion — ideal für schnelle TikTok-Feeds.")
    if dens >= 65 and clar >= 60:
        return ("YouTube Shorts", "Hohe Informationsdichte + Klarheit — gut für Shorts-Retention.")
    if share >= 62:
        return ("Instagram Reels", "Diskussions-/Teilen-Potenzial — passt zu Reels.")
    return ("TikTok", "Solide Kurzform-Eignung; TikTok als breiter Startpunkt.")


# Risiko-Flags: stabile ENGLISCHE Keys (frontend übersetzt sie in Labels).
RISK_FLAGS = (
    "needs_context",
    "slow_start",
    "too_generic",
    "weak_hook",
    "too_long",
    "too_short",
    "low_information_density",
    "unclear_takeaway",
    "duplicate_like",
    "language_mixed",
    "transcript_quality_low",
)

# Vorschläge pro Flag (DE-UI). Bewusst konkret & handlungsorientiert.
_FLAG_SUGGESTIONS = {
    "needs_context": "Clip später starten — der Anfang setzt Vorwissen voraus.",
    "slow_start": "Vorlauf/Füllwörter am Anfang wegschneiden, direkt zur Aussage.",
    "too_generic": "Konkreter werden — Beispiel, Zahl oder klare These einbauen.",
    "weak_hook": "Stärkeren Einstieg wählen (Frage, These oder Zahl in den ersten 2 s).",
    "too_long": "Kürzen — unter ~60 s hält die Aufmerksamkeit besser.",
    "too_short": "Etwas mehr Kontext geben — der Clip ist sehr kurz.",
    "low_information_density": "Dichter erzählen — weniger Leerlauf, mehr Substanz pro Sekunde.",
    "unclear_takeaway": "Klaren Payoff/Abschluss ergänzen, damit die Aussage sitzt.",
    "duplicate_like": "Ähnelt einem anderen Clip — nur die stärkere Variante behalten.",
    "language_mixed": "Sprache vereinheitlichen — Sprachmix kann Reichweite kosten.",
    "transcript_quality_low": "Sauberere Passage wählen — hier ist viel Füllwort/Rauschen.",
}


def _language_mixed(tokens: list[str]) -> bool:
    de = {"und", "der", "die", "das", "ist", "nicht", "du", "ich", "warum",
          "wie", "mit", "auf", "eine", "dein", "musst"}
    en = {"the", "and", "you", "is", "why", "how", "what", "to", "of", "your",
          "every", "day", "when"}
    de_hits = sum(1 for t in tokens if t in de)
    en_hits = sum(1 for t in tokens if t in en)
    return de_hits >= 2 and en_hits >= 2


def _risk_flags(
    comp: dict[str, float], text: str, dur: float, clean_start: bool
) -> list[str]:
    tokens = _tokens(text)
    n = max(1, len(tokens))
    first = tokens[0] if tokens else ""
    filler_ratio = sum(1 for t in tokens if t in _GENERIC_FILLER) / n
    content_ratio = len(_content_words(tokens)) / n
    generic_start = bool(first) and (first in _GENERIC_FILLER or first in _CONTEXT_START)

    flags: list[str] = []
    if comp["context_independence"] < 50:
        flags.append("needs_context")
    if not clean_start or generic_start or comp["editability"] < 45:
        flags.append("slow_start")
    if comp["uniqueness"] < 45:
        flags.append("too_generic")
    if comp["hook_strength"] < 38:
        flags.append("weak_hook")
    if dur > 78:
        flags.append("too_long")
    if dur < IDEAL_MIN:
        flags.append("too_short")
    if comp["information_density"] < 45:
        flags.append("low_information_density")
    if comp["retention_potential"] < 42 and not _ends_sentence(text):
        flags.append("unclear_takeaway")
    if filler_ratio > 0.18 or content_ratio < 0.35:
        flags.append("transcript_quality_low")
    if _language_mixed(tokens):
        flags.append("language_mixed")
    # Reihenfolge stabil nach RISK_FLAGS-Definition, keine Duplikate.
    seen = set()
    return [f for f in RISK_FLAGS if f in flags and not (f in seen or seen.add(f))]


def _improvement_suggestions(
    comp: dict[str, float], dur: float, flags: list[str]
) -> list[str]:
    """Konkrete Verbesserungsvorschläge — primär aus den Risk-Flags abgeleitet."""
    out: list[str] = []
    for f in flags:
        if f in _FLAG_SUGGESTIONS:
            out.append(_FLAG_SUGGESTIONS[f])
    # Ergänzende Hinweise, falls (fast) keine Flags, aber Schwächen sichtbar.
    if comp["retention_potential"] < 50 and "unclear_takeaway" not in flags:
        out.append("Spannung/offene Schleife einbauen, damit Zuschauer dranbleiben.")
    if comp["clarity"] < 55 and "transcript_quality_low" not in flags:
        out.append("Aussage straffen — weniger Füllwörter, klarere Sätze.")
    # Duplikate entfernen, Reihenfolge erhalten, auf 4 begrenzen.
    seen = set()
    uniq = [s for s in out if not (s in seen or seen.add(s))]
    return uniq[:4]


def _legacy_breakdown(comp: dict[str, float]) -> ScoreBreakdown:
    """Mappt v2-Komponenten auf die 5 Legacy-Werte (für content.py + altes UI)."""
    return ScoreBreakdown(
        hook=comp["hook_strength"],
        clarity=comp["clarity"],
        emotion=comp["emotional_intensity"],
        pacing=comp["platform_fit"],
        payoff=comp["retention_potential"],
    )


def _excerpt(text: str, limit: int = 200) -> str:
    t = " ".join(text.split())
    return t[:limit] + ("…" if len(t) > limit else "")


def _build_scored(cand: CandidateClip, language: str, clean_start: bool = True) -> ScoredClip:
    comp = score_components_v2(cand.text, cand.duration)
    score = _aggregate_score(comp)
    hook_type = _hook_type(cand.text)
    clip_type = _clip_type(cand.text)
    best_pf, pf_reason = _best_platform(comp, language)
    flags = _risk_flags(comp, cand.text, cand.duration, clean_start)
    suggestions = _improvement_suggestions(comp, cand.duration, flags)
    reason = (
        f"Analyzer v2: stärkstes Signal '{max(comp, key=comp.get)}', "
        f"schwächstes '{min(comp, key=comp.get)}'. "
        f"Score ist eine Einschätzung, keine Garantie."
    )
    return ScoredClip(
        start=cand.start,
        end=cand.end,
        text=cand.text,
        score=score,
        breakdown=_legacy_breakdown(comp),
        reason=reason,
        words=cand.words,
        scorer="heuristic",
        analyzer_version=ANALYZER_VERSION,
        analyzer_mode="rule_based",
        performance_score=score,
        score_breakdown=comp,
        score_reason=reason,
        improvement_suggestions=suggestions,
        risk_flags=flags,
        best_platform=best_pf,
        platform_reason=pf_reason,
        hook_type=hook_type,
        clip_type=clip_type,
        language=language,
        transcript_excerpt=_excerpt(cand.text),
    )


# ==========================================================================
# Dedup + diverse Auswahl
# ==========================================================================

# Dedup-/Diversitäts-Schwellen (strenger = weniger Redundanz).
_DEDUP_TIME = 0.5    # Zeitüberlappung, ab der zwei Clips als „gleich" gelten
_DEDUP_TEXT = 0.55   # Text-Jaccard (Content-Wörter) für Ähnlichkeit
_DIVERSE_TIME = 0.35  # max. erlaubte Überlappung zwischen ausgewählten Clips


def _dedup_and_select(
    scored: list[ScoredClip], top_n: int
) -> tuple[list[ScoredClip], int, int, int]:
    """Dedupliziert ähnliche/überlappende Clips und wählt diverse Top-N.

    - Gruppiert per Zeitüberlappung ODER Text-Ähnlichkeit (Content-Wörter).
    - Bevorzugt pro Gruppe die Variante mit sauberem Satzende bei gleichem Score.
    - Wählt greedy nach Score, meidet räumliche Nähe (andere Video-Stellen).
    - Füllt bei zu wenig Vielfalt auf und markiert diese Clips als duplicate_like.

    Rückgabe: (ausgewählte Clips, n_kandidaten, n_nach_dedup, n_aufgefüllt).
    """
    n_candidates = len(scored)
    if not scored:
        return [], 0, 0, 0

    # Reihenfolge: bester Score zuerst, bei Gleichstand sauberes Ende bevorzugen.
    def _rank(c: ScoredClip) -> tuple:
        return (c.score, 1 if _ends_sentence(c.text) else 0)

    ordered = sorted(scored, key=_rank, reverse=True)

    # Gruppieren (Zeitüberlappung ODER Textähnlichkeit gegen alle Gruppenmitglieder)
    groups: list[list[ScoredClip]] = []
    token_sets: list[list[set[str]]] = []
    for c in ordered:
        toks = set(_content_words(_tokens(c.text)))
        placed = False
        for gi, g in enumerate(groups):
            if any(_time_overlap(c, m) >= _DEDUP_TIME for m in g) or any(
                _jaccard(toks, ts) >= _DEDUP_TEXT for ts in token_sets[gi]
            ):
                g.append(c)
                token_sets[gi].append(toks)
                placed = True
                break
        if not placed:
            groups.append([c])
            token_sets.append([toks])

    # Repräsentant je Gruppe (bester = erster nach Rang); Gruppen-ID nur bei >1.
    reps: list[ScoredClip] = []
    for gid, g in enumerate(groups):
        rep = g[0]
        if len(g) > 1:
            rep.duplicate_group = gid
        reps.append(rep)
    n_after_dedup = len(reps)

    reps.sort(key=_rank, reverse=True)

    # Diverse Auswahl: Zeitüberlappung mit bereits Gewählten vermeiden.
    selected: list[ScoredClip] = []
    for c in reps:
        if any(_time_overlap(c, s) >= _DIVERSE_TIME for s in selected):
            continue
        selected.append(c)
        if len(selected) >= top_n:
            break

    # Auffüllen, falls zu wenig Vielfalt vorhanden: nächstbeste, aber markiert.
    filled = 0
    if len(selected) < top_n:
        chosen = set(id(c) for c in selected)
        for c in reps:
            if id(c) in chosen:
                continue
            if "duplicate_like" not in c.risk_flags:
                c.risk_flags = [*c.risk_flags, "duplicate_like"]
            selected.append(c)
            filled += 1
            if len(selected) >= top_n:
                break

    return selected, n_candidates, n_after_dedup, filled


# ==========================================================================
# Analyzer-Klassen + Fallback-Chain
# ==========================================================================

class RuleBasedClipAnalyzer:
    """Regelbasierter Analyzer — Default, ohne API-Key, deterministisch."""

    mode = "rule_based"

    def analyze(
        self, transcript: Transcript, settings: Settings, top_n: int
    ) -> tuple[list[ScoredClip], dict]:
        language = transcript.language if transcript.language in ("de", "en") else \
            detect_language(transcript.full_text or "")
        candidates = build_candidates_v2(transcript, settings)
        scored = [_build_scored(c, language) for c in candidates]
        selected, n_cand, n_dedup, filled = _dedup_and_select(scored, top_n)
        meta = {
            "analyzer_version": ANALYZER_VERSION,
            "analyzer_mode": self.mode,
            "candidate_count": n_cand,
            "deduplicated_count": n_dedup,
            "filled_up": filled,
            "language": language,
        }
        return selected, meta


_LLM_SYSTEM = (
    "Du bist ein erfahrener Short-Form-Editor. Du bewertest VORGEGEBENE "
    "Transkript-Ausschnitte nach Performance-Potenzial. Du erfindest KEINE "
    "neuen Clips und wählst NUR aus den nummerierten Kandidaten. Du "
    "garantierst niemals Viralität. Antworte AUSSCHLIESSLICH mit gültigem JSON."
)


def _llm_prompt(candidates: list[ScoredClip]) -> str:
    lines = ["Bewerte jeden Kandidaten (nur diese, keine neuen erfinden).",
             "Gib JSON: {\"clips\":[{\"index\":N,\"performance_score\":0-100,",
             "\"score_reason\":\"...\",\"best_platform\":\"TikTok|YouTube Shorts|Instagram Reels\"}]}",
             ""]
    for i, c in enumerate(candidates):
        lines.append(f"[{i}] ({c.duration:.0f}s) {c.text[:300]}")
    return "\n".join(lines)


class OptionalLLMClipAnalyzer:
    """Optionaler LLM-Analyzer: re-rankt die regelbasierten Kandidaten.

    Sendet NUR die Kandidaten-Fenster (nicht das ganze Video). Bei jedem
    Fehler (kein Key, Timeout, Rate-Limit, ungültiges JSON) → Fallback.
    """

    mode = "llm"

    def analyze(
        self, transcript: Transcript, settings: Settings, top_n: int
    ) -> tuple[list[ScoredClip], dict]:
        # 1) immer erst regelbasiert (liefert Kandidaten + Fallback-Basis)
        base_selected, meta = RuleBasedClipAnalyzer().analyze(
            transcript, settings, max(top_n * 2, top_n)
        )
        if not settings.llm_available or not base_selected:
            meta["analyzer_mode"] = "rule_based"
            return base_selected[:top_n], meta

        import time as _time

        started = _time.monotonic()
        try:
            import anthropic

            client = anthropic.Anthropic(
                api_key=settings.anthropic_api_key,
                timeout=settings.llm_timeout_seconds,
                max_retries=1,
            )
            resp = client.messages.create(
                model=settings.llm_model,
                max_tokens=1024,
                system=_LLM_SYSTEM,
                messages=[{"role": "user", "content": _llm_prompt(base_selected)}],
            )
            raw = "".join(
                b.text for b in resp.content if getattr(b, "type", "") == "text"
            )
            items = _parse_llm_items(raw)
            if not items:
                raise ValueError("LLM-Antwort enthielt keine gültigen Clip-Bewertungen")
            # LLM darf NUR bestehende Kandidaten (per Index) re-ranken — keine
            # neuen Zeitfenster. Unbekannte/erfundene Indizes werden ignoriert.
            n = len(base_selected)
            applied = 0
            for item in items:
                idx = item["index"]
                if not (0 <= idx < n):
                    continue  # erfundener Kandidat → verwerfen
                clip = base_selected[idx]
                clip.performance_score = item["performance_score"]
                clip.score = item["performance_score"]
                clip.analyzer_mode = "llm"
                if item.get("score_reason"):
                    clip.score_reason = item["score_reason"]
                    clip.reason = item["score_reason"]
                if item.get("best_platform"):
                    clip.best_platform = item["best_platform"]
                applied += 1
            if applied == 0:
                raise ValueError("LLM lieferte nur unbekannte Kandidaten-Indizes")
            for clip in base_selected:
                clip.analyzer_mode = "llm"
            base_selected.sort(key=lambda c: c.score, reverse=True)
            meta["analyzer_mode"] = "llm"
            meta["llm_model"] = settings.llm_model
            meta["llm_latency_ms"] = round((_time.monotonic() - started) * 1000.0, 1)
            meta["llm_applied"] = applied
            return base_selected[:top_n], meta
        except Exception as exc:  # noqa: BLE001 — nie die Pipeline killen
            for clip in base_selected:
                clip.analyzer_mode = "fallback"
            meta["analyzer_mode"] = "fallback"
            meta["llm_error"] = type(exc).__name__
            meta["llm_latency_ms"] = round((_time.monotonic() - started) * 1000.0, 1)
            return base_selected[:top_n], meta


_ALLOWED_PLATFORMS = {"TikTok", "YouTube Shorts", "Instagram Reels"}


def _parse_llm_json(raw: str) -> dict:
    """Robustes JSON-Parsing: Markdown-Fences weg, Text vor/nach JSON ignorieren."""
    raw = (raw or "").strip()
    if raw.startswith("```"):
        raw = re.sub(r"^```[a-zA-Z]*\n?", "", raw)
        raw = re.sub(r"\n?```$", "", raw).strip()
    try:
        return json.loads(raw)
    except (json.JSONDecodeError, ValueError):
        m = re.search(r"\{.*\}", raw, re.DOTALL)
        if not m:
            return {}
        try:
            return json.loads(m.group(0))
        except (json.JSONDecodeError, ValueError):
            return {}


def _parse_llm_items(raw: str) -> list[dict]:
    """Validiert die LLM-Antwort zu sauberen, geklemmten Items.

    Jedes Item braucht einen ganzzahligen `index`; `performance_score` wird auf
    0–100 geklemmt; kaputte/fehlende Felder werden ignoriert statt zu crashen.
    """
    data = _parse_llm_json(raw)
    if not isinstance(data, dict):
        return []
    clips = data.get("clips")
    if not isinstance(clips, list):
        return []
    out: list[dict] = []
    for entry in clips:
        if not isinstance(entry, dict) or "index" not in entry:
            continue
        try:
            idx = int(entry["index"])
        except (TypeError, ValueError):
            continue
        item: dict = {"index": idx}
        try:
            item["performance_score"] = round(_clamp(float(entry["performance_score"])), 1)
        except (TypeError, ValueError, KeyError):
            item["performance_score"] = None
        reason = entry.get("score_reason")
        if isinstance(reason, str) and reason.strip():
            item["score_reason"] = reason.strip()[:400]
        plat = entry.get("best_platform")
        if isinstance(plat, str) and plat.strip() in _ALLOWED_PLATFORMS:
            item["best_platform"] = plat.strip()
        # Ohne verwertbaren Score bringt das Item nichts.
        if item["performance_score"] is None:
            continue
        out.append(item)
    return out


def analyze_clips(
    transcript: Transcript, settings: Settings, top_n: int
) -> tuple[list[ScoredClip], dict]:
    """Fallback-Chain: LLM (falls Key) → sonst/immer regelbasiert."""
    if settings.llm_available:
        return OptionalLLMClipAnalyzer().analyze(transcript, settings, top_n)
    return RuleBasedClipAnalyzer().analyze(transcript, settings, top_n)
