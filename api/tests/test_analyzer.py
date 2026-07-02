"""Tests für den Clip-Analyzer v2 (Kandidaten, Score, Dedup, Modi)."""

from __future__ import annotations

import os
import sys
import types

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from clipforge.analyzer import (
    HARD_MAX,
    HARD_MIN,
    IDEAL_MIN,
    RISK_FLAGS,
    RuleBasedClipAnalyzer,
    OptionalLLMClipAnalyzer,
    _WEIGHTS,
    _parse_llm_items,
    analyze_clips,
    build_candidates_v2,
    score_components_v2,
)
from clipforge.config import Settings
from clipforge.models import ScoredClip, ScoreBreakdown, Transcript, TranscriptSegment, Word

import transcripts_fixtures as FX


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


# ---------------------- Realistische Fixtures / Kalibrierung --------------

def _all_selected():
    """Alle ausgewählten Clips über alle Fixtures (rule_based)."""
    out = []
    for fn in FX.ALL_FIXTURES.values():
        clips, _ = RuleBasedClipAnalyzer().analyze(fn(), _rule_settings(), 8)
        out += clips
    return out


def test_de_podcast_yields_candidates_and_strong_clip():
    clips, meta = RuleBasedClipAnalyzer().analyze(FX.de_podcast(), _rule_settings(), 8)
    assert meta["candidate_count"] >= 5
    assert clips
    assert max(c.performance_score for c in clips) >= 85, "kein sehr starker Clip"


def test_en_education_yields_candidates_and_strong_clip():
    clips, meta = RuleBasedClipAnalyzer().analyze(FX.en_education(), _rule_settings(), 8)
    assert meta["candidate_count"] >= 5
    assert max(c.performance_score for c in clips) >= 85


def test_mixed_does_not_crash():
    clips, meta = RuleBasedClipAnalyzer().analyze(FX.mixed(), _rule_settings(), 5)
    assert isinstance(clips, list)
    assert meta["analyzer_version"] == "v2"


def test_mixed_flags_language_mixed():
    clips, _ = RuleBasedClipAnalyzer().analyze(FX.mixed(), _rule_settings(), 5)
    assert any("language_mixed" in c.risk_flags for c in clips)


def test_weak_scores_low():
    clips, _ = RuleBasedClipAnalyzer().analyze(FX.weak(), _rule_settings(), 5)
    assert clips
    assert max(c.performance_score for c in clips) < 60, "Smalltalk zu hoch bewertet"


def test_weak_below_strong():
    weak, _ = RuleBasedClipAnalyzer().analyze(FX.weak(), _rule_settings(), 5)
    strong, _ = RuleBasedClipAnalyzer().analyze(FX.de_podcast(), _rule_settings(), 5)
    assert max(c.performance_score for c in weak) < max(c.performance_score for c in strong)


def test_distribution_not_inflationary():
    scores = [c.performance_score for c in _all_selected()]
    assert scores
    # Nicht jeder Clip > 80, und es gibt auch schwache Clips.
    assert any(s < 60 for s in scores), "keine schwachen Clips — zu inflationär"
    assert not all(s > 80 for s in scores)
    frac_high = sum(1 for s in scores if s > 84) / len(scores)
    assert frac_high < 0.6, "zu viele Clips im Top-Band"


def test_95_plus_is_rare():
    scores = [c.performance_score for c in _all_selected()]
    assert sum(1 for s in scores if s >= 95) == 0


def test_dedup_reduces_candidate_count():
    _, meta = RuleBasedClipAnalyzer().analyze(FX.de_podcast(), _rule_settings(), 8)
    assert meta["deduplicated_count"] < meta["candidate_count"]


def test_duplicate_group_is_set_meaningfully():
    clips, _ = RuleBasedClipAnalyzer().analyze(FX.de_podcast(), _rule_settings(), 8)
    groups = [c.duplicate_group for c in clips if c.duplicate_group is not None]
    assert groups, "keine duplicate_group gesetzt"
    assert all(isinstance(g, int) and g >= 0 for g in groups)


def test_meta_counts_present():
    _, meta = RuleBasedClipAnalyzer().analyze(FX.de_podcast(), _rule_settings(), 5)
    for k in ("candidate_count", "deduplicated_count", "filled_up", "language"):
        assert k in meta, k


def test_risk_flags_use_english_keys():
    for c in _all_selected():
        for f in c.risk_flags:
            assert f in RISK_FLAGS, f


def test_weak_clip_has_risk_flags_and_suggestions():
    clips, _ = RuleBasedClipAnalyzer().analyze(FX.weak(), _rule_settings(), 5)
    worst = min(clips, key=lambda c: c.performance_score)
    assert worst.risk_flags, "schwacher Clip ohne Flags"
    assert worst.improvement_suggestions, "schwacher Clip ohne Vorschläge"


def test_too_short_flag_fires():
    tr = Transcript(language="de", duration=12.0, segments=[
        _seg("Warum ist das wichtig? Sehr kurz.", 0.0, 10.0)])
    clips, _ = RuleBasedClipAnalyzer().analyze(tr, _rule_settings(), 3)
    assert clips
    assert any("too_short" in c.risk_flags for c in clips)


def test_needs_context_flag_fires():
    comp = score_components_v2("Deshalb ist das der wichtigste Punkt überhaupt.", 20.0)
    from clipforge.analyzer import _risk_flags
    flags = _risk_flags(comp, "Deshalb ist das der wichtigste Punkt überhaupt.", 20.0, True)
    assert "needs_context" in flags


def test_fill_up_marks_duplicate_like():
    # Kurzes Transkript, aber top_n groß → Auffüllen erzwingen.
    tr = FX.mixed()
    clips, meta = RuleBasedClipAnalyzer().analyze(tr, _rule_settings(), 6)
    if meta["filled_up"] > 0:
        assert any("duplicate_like" in c.risk_flags for c in clips)
    else:
        # akzeptabel, falls genügend Vielfalt vorhanden war
        assert meta["deduplicated_count"] <= len(clips) + meta["filled_up"]


# ---------------------- LLM-Härtung (Fake-Client) -------------------------

def _install_fake_anthropic(text):
    fake = types.ModuleType("anthropic")

    class _Block:
        type = "text"

    _Block.text = text

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


def _llm_settings():
    return Settings(anthropic_api_key="sk-fake", use_llm=True)


def test_llm_markdown_fenced_json_parses():
    _install_fake_anthropic(
        "Hier meine Bewertung:\n```json\n"
        '{"clips":[{"index":0,"performance_score":88,"best_platform":"TikTok"}]}\n```\n'
    )
    try:
        clips, meta = OptionalLLMClipAnalyzer().analyze(
            FX.de_podcast(), _llm_settings(), 3)
        assert meta["analyzer_mode"] == "llm"
        assert any(c.performance_score == 88.0 for c in clips)
    finally:
        sys.modules.pop("anthropic", None)


def test_llm_broken_json_falls_back():
    _install_fake_anthropic("das ist definitiv kein json {kaputt")
    try:
        clips, meta = OptionalLLMClipAnalyzer().analyze(
            FX.de_podcast(), _llm_settings(), 3)
        assert meta["analyzer_mode"] == "fallback"
        assert all(c.analyzer_mode == "fallback" for c in clips)
    finally:
        sys.modules.pop("anthropic", None)


def test_llm_invented_candidate_only_falls_back():
    # Nur erfundener Index → nichts anwendbar → Fallback.
    _install_fake_anthropic('{"clips":[{"index":99,"performance_score":99}]}')
    try:
        clips, meta = OptionalLLMClipAnalyzer().analyze(
            FX.de_podcast(), _llm_settings(), 3)
        assert meta["analyzer_mode"] == "fallback"
    finally:
        sys.modules.pop("anthropic", None)


def test_llm_ignores_invented_but_applies_valid():
    _install_fake_anthropic(
        '{"clips":[{"index":0,"performance_score":93},'
        '{"index":99,"performance_score":10}]}'
    )
    try:
        clips, meta = OptionalLLMClipAnalyzer().analyze(
            FX.de_podcast(), _llm_settings(), 3)
        assert meta["analyzer_mode"] == "llm"
        assert meta["llm_applied"] == 1
        assert any(c.performance_score == 93.0 for c in clips)
    finally:
        sys.modules.pop("anthropic", None)


def test_llm_latency_recorded_on_success_and_fallback():
    _install_fake_anthropic('{"clips":[{"index":0,"performance_score":80}]}')
    try:
        _, meta = OptionalLLMClipAnalyzer().analyze(FX.de_podcast(), _llm_settings(), 3)
        assert "llm_latency_ms" in meta
    finally:
        sys.modules.pop("anthropic", None)


def test_parse_llm_items_clamps_and_validates():
    # 200 → auf 100 geklemmt (clamp); fehlender Score → verworfen; Index-Cast.
    items = _parse_llm_items(
        '{"clips":[{"index":"0","performance_score":200},'
        '{"index":1},'
        '{"index":2,"performance_score":-5,"best_platform":"Nonsense"},'
        '{"index":3,"performance_score":50,"best_platform":"TikTok"}]}'
    )
    by = {it["index"]: it for it in items}
    assert by[0]["performance_score"] == 100.0
    assert 1 not in by  # ohne Score verworfen
    assert by[2]["performance_score"] == 0.0
    assert "best_platform" not in by[2]  # ungültige Plattform verworfen
    assert by[3]["best_platform"] == "TikTok"


def test_parse_llm_items_handles_garbage():
    assert _parse_llm_items("kein json") == []
    assert _parse_llm_items("") == []
    assert _parse_llm_items('{"foo":"bar"}') == []


def test_real_llm_run_if_key_present():
    """Echter Lauf nur mit gesetztem ANTHROPIC_API_KEY — sonst dokumentiert
    übersprungen (kein Key in dieser Umgebung)."""
    key = os.environ.get("ANTHROPIC_API_KEY")
    if not key:
        print("    (real LLM übersprungen: kein ANTHROPIC_API_KEY)")
        return
    settings = Settings()  # nimmt echten Key/Modell aus Env
    clips, meta = OptionalLLMClipAnalyzer().analyze(FX.de_podcast(), settings, 3)
    assert meta["analyzer_mode"] in ("llm", "fallback")
    assert "llm_latency_ms" in meta
    assert clips


# ---------------------- Rückwärtskompatibilität ---------------------------

def test_old_clip_without_risk_flags_is_stable():
    """Ein 'alter' Clip (keine v2-Felder gesetzt) darf nicht crashen."""
    clip = ScoredClip(
        start=0.0, end=20.0, text="Alt.", score=50.0,
        breakdown=ScoreBreakdown(hook=50, clarity=50, emotion=50, pacing=50, payoff=50),
        reason="legacy",
    )
    d = clip.to_dict()
    assert d["risk_flags"] == []
    assert d["analyzer_version"] is None


def test_run_all_fixtures_end_to_end():
    for name, fn in FX.ALL_FIXTURES.items():
        clips, meta = analyze_clips(fn(), _rule_settings(), 5)
        assert isinstance(clips, list), name
        assert meta["analyzer_mode"] == "rule_based", name


def _run_all():
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for fn in fns:
        fn()
        print(f"  ✓ {fn.__name__}")
    print(f"\n{len(fns)} Tests bestanden.")


if __name__ == "__main__":
    _run_all()
