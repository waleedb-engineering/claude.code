"""Tests für den Clip-Analyzer v2 (Kandidaten, Score, Dedup, Modi)."""

from __future__ import annotations

import os
import sys
import types

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from clipforge.analyzer import (
    HARD_MAX,
    HARD_MIN,
    RuleBasedClipAnalyzer,
    OptionalLLMClipAnalyzer,
    _WEIGHTS,
    analyze_clips,
    build_candidates_v2,
    score_components_v2,
)
from clipforge.config import Settings
from clipforge.models import Transcript, TranscriptSegment, Word


def _seg(text: str, start: float, end: float) -> TranscriptSegment:
    # grobe Wort-Timestamps gleichmäßig verteilen
    toks = text.split()
    words = []
    if toks:
        step = (end - start) / len(toks)
        for i, t in enumerate(toks):
            words.append(Word(text=t, start=start + i * step, end=start + (i + 1) * step))
    return TranscriptSegment(text=text, start=start, end=end, words=words)


def _german_transcript() -> Transcript:
    segs = [
        _seg("Warum scheitern die meisten Leute an ihrem ersten Geld?", 0.0, 6.0),
        _seg("Der Fehler ist simpel: Sie sparen, statt zu investieren.", 6.0, 12.0),
        _seg("Deshalb bleibt am Ende nichts übrig.", 12.0, 16.0),
        _seg("Stell dir vor, du verdoppelst deine Reichweite in dreißig Tagen.", 18.0, 24.0),
        _seg("Das Geheimnis ist ein starker Hook in den ersten drei Sekunden.", 24.0, 30.0),
        _seg("Niemand sagt dir das, aber Konsistenz schlägt Talent jedes Mal.", 31.0, 38.0),
        _seg("Also fang heute an und poste dein erstes Video.", 38.0, 44.0),
    ]
    return Transcript(language="de", duration=44.0, segments=segs)


def _english_transcript() -> Transcript:
    segs = [
        _seg("Why do most people fail at their first business?", 0.0, 6.0),
        _seg("The mistake is simple: they quit way too early.", 6.0, 12.0),
        _seg("Here is the secret nobody tells you about growth.", 13.0, 19.0),
        _seg("You must post every single day for ninety days.", 19.0, 25.0),
        _seg("That is how you build real momentum and win.", 25.0, 31.0),
    ]
    return Transcript(language="en", duration=31.0, segments=segs)


def _rule_settings() -> Settings:
    return Settings(anthropic_api_key=None, use_llm=False)


# ---------------------- Kandidaten ----------------------------------------

def test_finds_multiple_candidates():
    cands = build_candidates_v2(_german_transcript(), _rule_settings())
    assert len(cands) >= 2


def test_candidates_respect_length_bounds():
    cands = build_candidates_v2(_german_transcript(), _rule_settings())
    assert cands
    for c in cands:
        assert HARD_MIN - 0.01 <= c.duration <= HARD_MAX + 0.01, c.duration


def test_dedup_reduces_overlap():
    tr = _german_transcript()
    settings = _rule_settings()
    raw = build_candidates_v2(tr, settings)
    clips, meta = RuleBasedClipAnalyzer().analyze(tr, settings, 2)
    # nach Dedup weniger (oder gleich) viele wie Rohkandidaten
    assert meta["deduplicated_count"] <= meta["candidate_count"] == len(raw)
    # bei sinnvollem top_n überlappen die ausgewählten Clips sich nicht stark
    for i in range(len(clips)):
        for j in range(i + 1, len(clips)):
            a, b = clips[i], clips[j]
            lo, hi = max(a.start, b.start), min(a.end, b.end)
            overlap = max(0.0, hi - lo)
            shorter = min(a.duration, b.duration)
            assert overlap / shorter < 0.5, "zu starke Überlappung in Auswahl"


# ---------------------- Score ---------------------------------------------

def test_breakdown_has_all_components():
    comp = score_components_v2("Warum scheitern die meisten? Der Fehler ist simpel.", 20.0)
    assert set(comp.keys()) == set(_WEIGHTS.keys())
    assert len(comp) == 10


def test_scores_within_0_100():
    for text, dur in [("Warum scheitern die meisten Leute?", 20.0),
                      ("ähm halt irgendwie naja also", 40.0),
                      ("", 10.0)]:
        comp = score_components_v2(text, dur)
        for k, v in comp.items():
            assert 0.0 <= v <= 100.0, (k, v)


def test_strong_beats_weak():
    strong = "Warum scheitern die meisten? Der Fehler ist ein teurer Denkfehler. Deshalb: investiere früh."
    weak = "ähm ja also irgendwie halt eben und dann und so weiter naja"
    clips, _ = RuleBasedClipAnalyzer().analyze(
        Transcript(language="de", duration=40.0, segments=[
            _seg(strong, 0.0, 20.0), _seg(weak, 22.0, 40.0),
        ]), _rule_settings(), 2)
    by_text = {("stark" if "scheitern" in c.text else "schwach"): c.performance_score
               for c in clips}
    assert by_text.get("stark", 0) > by_text.get("schwach", 100)


def test_german_and_english_work():
    for tr in (_german_transcript(), _english_transcript()):
        clips, meta = RuleBasedClipAnalyzer().analyze(tr, _rule_settings(), 3)
        assert clips, meta
        assert meta["language"] in ("de", "en")
        assert all(c.language in ("de", "en") for c in clips)


def test_empty_and_short_do_not_crash():
    for tr in (Transcript(language="de", duration=0.0, segments=[]),
               Transcript(language="de", duration=3.0, segments=[_seg("Kurz.", 0.0, 3.0)])):
        clips, meta = RuleBasedClipAnalyzer().analyze(tr, _rule_settings(), 3)
        assert isinstance(clips, list)
        assert meta["analyzer_version"] == "v2"


# ---------------------- Modi / Fallback -----------------------------------

def test_no_api_key_is_rule_based():
    clips, meta = analyze_clips(_german_transcript(), _rule_settings(), 3)
    assert meta["analyzer_mode"] == "rule_based"
    assert all(c.analyzer_mode == "rule_based" for c in clips)


def test_llm_error_falls_back(monkeypatch=None):
    """Fake-anthropic, dessen Aufruf fehlschlägt → analyzer_mode == 'fallback'."""
    fake = types.ModuleType("anthropic")

    class _Msgs:
        def create(self, **kwargs):
            raise RuntimeError("simulated rate limit")

    class _Client:
        def __init__(self, **kwargs):
            self.messages = _Msgs()

    fake.Anthropic = _Client
    sys.modules["anthropic"] = fake
    try:
        settings = Settings(anthropic_api_key="sk-fake-not-real", use_llm=True)
        clips, meta = OptionalLLMClipAnalyzer().analyze(_german_transcript(), settings, 3)
        assert meta["analyzer_mode"] == "fallback"
        assert meta.get("llm_error")
        assert clips and all(c.analyzer_mode == "fallback" for c in clips)
    finally:
        sys.modules.pop("anthropic", None)


def test_llm_success_reranks(monkeypatch=None):
    """Fake-anthropic mit gültigem JSON → analyzer_mode == 'llm', Score übernommen."""
    fake = types.ModuleType("anthropic")

    class _Block:
        type = "text"
        text = '{"clips":[{"index":0,"performance_score":91,"score_reason":"stark","best_platform":"TikTok"}]}'

    class _Resp:
        content = [_Block()]

    class _Msgs:
        def create(self, **kwargs):
            return _Resp()

    class _Client:
        def __init__(self, **kwargs):
            self.messages = _Msgs()

    fake.Anthropic = _Client
    sys.modules["anthropic"] = fake
    try:
        settings = Settings(anthropic_api_key="sk-fake", use_llm=True)
        clips, meta = OptionalLLMClipAnalyzer().analyze(_german_transcript(), settings, 3)
        assert meta["analyzer_mode"] == "llm"
        assert clips[0].analyzer_mode == "llm"
        assert clips[0].performance_score == 91.0
        assert clips[0].best_platform == "TikTok"
    finally:
        sys.modules.pop("anthropic", None)


def test_scored_clip_has_v2_fields_for_json():
    clips, _ = RuleBasedClipAnalyzer().analyze(_german_transcript(), _rule_settings(), 2)
    d = clips[0].to_dict()
    for k in ("analyzer_version", "analyzer_mode", "performance_score",
              "score_breakdown", "score_reason", "improvement_suggestions",
              "risk_flags", "best_platform", "platform_reason", "hook_type",
              "clip_type", "language", "transcript_excerpt"):
        assert k in d, k
    # Legacy-Felder für content.py / altes UI weiter vorhanden
    assert "breakdown" in d and "hook" in d["breakdown"]
    assert d["performance_score"] == d["score"]


def _run_all():
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for fn in fns:
        fn()
        print(f"  ✓ {fn.__name__}")
    print(f"\n{len(fns)} Tests bestanden.")


if __name__ == "__main__":
    _run_all()
