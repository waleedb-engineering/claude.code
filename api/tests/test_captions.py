"""Deterministische Tests für Caption-Modi/-Styles (ohne ffmpeg)."""

from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from clipforge.captions import (
    STYLES,
    build_ass_karaoke,
    chunk_words,
    has_word_timestamps,
    make_captions,
)
from clipforge.models import Word


def _words(n=6, start=0.0, step=0.5):
    return [
        Word(text=f"w{i}", start=start + i * step, end=start + i * step + step * 0.9)
        for i in range(n)
    ]


def test_chunk_words_groups():
    chunks = chunk_words(_words(6), max_words=2)
    assert [len(c) for c in chunks] == [2, 2, 2]


def test_has_word_timestamps():
    assert has_word_timestamps(_words(3)) is True
    assert has_word_timestamps([]) is False
    # Wörter ohne Dauer zählen nicht als nutzbar
    assert has_word_timestamps([Word("a", 1.0, 1.0)]) is False


def test_karaoke_applied_with_words():
    ass, info = make_captions(
        _words(6), 0.0, 3.0, mode="karaoke", style="high_energy"
    )
    assert info["applied_mode"] == "karaoke"
    assert info["requested_mode"] == "karaoke"
    assert info["caption_style"] == "high_energy"
    assert info["word_level_available"] is True
    assert info["fallback"] is False
    assert info["caption_blocks_count"] >= 1
    # Per-Wort-Highlight-Override vorhanden
    assert "\\1c" in ass and "\\r" in ass
    assert "Dialogue:" in ass


def test_karaoke_falls_back_without_words():
    ass, info = make_captions([], 0.0, 3.0, mode="karaoke", style="clean")
    assert info["applied_mode"] == "standard"
    assert info["fallback"] is True
    assert "Wort-Timestamps" in (info["fallback_reason"] or "")


def test_unknown_style_falls_back_to_clean():
    _ass, info = make_captions(
        _words(3), 0.0, 3.0, mode="karaoke", style="does_not_exist"
    )
    assert info["caption_style"] == "clean"
    assert info["fallback"] is True


def test_standard_mode_no_highlight():
    ass, info = make_captions(_words(4), 0.0, 3.0, mode="standard", style="clean")
    assert info["applied_mode"] == "standard"
    assert "\\1c" not in ass  # kein Per-Wort-Highlight im Standard-Modus


def test_high_energy_uppercases():
    ass, _ = build_ass_karaoke(
        [Word("hallo", 0.0, 0.4)], 0.0, 1.0, 1080, 1920, STYLES["high_energy"]
    )
    assert "HALLO" in ass


def _run_all():
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for fn in fns:
        fn()
        print(f"  ✓ {fn.__name__}")
    print(f"\n{len(fns)} Tests bestanden.")


if __name__ == "__main__":
    _run_all()
