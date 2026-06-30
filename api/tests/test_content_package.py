"""Tests für den Content-Package-Generator (regelbasiert, ohne API-Key)."""

from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from clipforge.config import Settings
from clipforge.content import (
    detect_language,
    generate_content_package,
    generate_rule_based,
)
from clipforge.models import ScoreBreakdown, ScoredClip

_REQUIRED_KEYS = (
    "primary_hook", "hook_variants", "youtube_shorts", "tiktok",
    "instagram_reels", "platform_recommendation", "variant_a", "variant_b",
    "variant_c", "safety_note",
)


def _settings(api_key: str | None = None) -> Settings:
    return Settings(anthropic_api_key=api_key, use_llm=True)


def _clip(text: str, score: float = 70.0) -> ScoredClip:
    b = ScoreBreakdown(hook=70, clarity=65, emotion=60, pacing=55, payoff=50)
    return ScoredClip(start=0.0, end=20.0, text=text, score=score, breakdown=b, reason="")


def test_detect_language_de_en():
    assert detect_language("Das ist ein Test und es funktioniert nicht schlecht") == "de"
    assert detect_language("This is a test and it works for the most part") == "en"


def test_rule_based_has_all_keys():
    b = ScoreBreakdown(hook=80, clarity=60, emotion=50, pacing=40, payoff=70)
    pkg = generate_rule_based(
        "Warum scheitern die meisten Leute am Anfang? Der Fehler ist simpel.",
        75.0, b, "de",
    )
    for key in _REQUIRED_KEYS:
        assert key in pkg, key
    assert set(pkg["hook_variants"].keys()) == {
        "provokant", "neugierig", "emotional", "edukativ", "direkt",
    }
    for platform in ("youtube_shorts", "tiktok", "instagram_reels"):
        assert pkg[platform]["hashtags"], platform


def test_works_without_api_key():
    settings = _settings(api_key=None)
    clip = _clip("Warum scheitern die meisten? Der Fehler ist simpel und klar.")
    pkg, used_llm = generate_content_package(clip, settings)
    assert used_llm is False
    for key in _REQUIRED_KEYS:
        assert key in pkg


def test_empty_transcript_does_not_crash():
    settings = _settings(api_key=None)
    for text in ("", "   ", "."):
        clip = _clip(text)
        pkg, used_llm = generate_content_package(clip, settings)
        assert used_llm is False
        for key in _REQUIRED_KEYS:
            assert key in pkg
        assert isinstance(pkg["primary_hook"], str)


def test_llm_unavailable_falls_back_even_with_use_llm_off():
    settings = Settings(anthropic_api_key="sk-fake-not-real", use_llm=False)
    clip = _clip("This is just a normal test sentence for the pipeline.")
    pkg, used_llm = generate_content_package(clip, settings)
    assert used_llm is False
    assert "primary_hook" in pkg


def test_safety_note_present_in_both_languages():
    b = ScoreBreakdown(hook=50, clarity=50, emotion=50, pacing=50, payoff=50)
    de = generate_rule_based("Das ist ein Test.", 50.0, b, "de")
    en = generate_rule_based("This is a test.", 50.0, b, "en")
    assert de["safety_note"]
    assert en["safety_note"]
    assert any("virality" in v.lower() or "viralität" in v.lower() for v in de["safety_note"].values())


def _run_all():
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for fn in fns:
        fn()
        print(f"  ✓ {fn.__name__}")
    print(f"\n{len(fns)} Tests bestanden.")


if __name__ == "__main__":
    _run_all()
