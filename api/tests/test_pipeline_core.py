"""Schnelle, abhängigkeitsfreie Regressionstests für den Pipeline-Kern.

Laufen ohne Whisper-Modell, ohne API-Key, ohne ffmpeg-Rendering
(nur Segmenter, Scoring, Captions). Aufruf:

    cd api && python -m pytest tests/ -q
    # oder ohne pytest:
    cd api && python tests/test_pipeline_core.py
"""

from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from clipforge.captions import build_ass, group_words
from clipforge.config import get_settings
from clipforge.models import Transcript, TranscriptSegment, Word
from clipforge.scoring import score_clips
from clipforge.segmenter import build_candidates


def _make_transcript() -> Transcript:
    segments = []
    t = 0.0
    blocks = [
        "Warum scheitern die meisten? Der Fehler ist simpel. Deshalb bleibt nichts.",
        "Heute ist ein ganz normaler Tag und es passiert eigentlich gar nichts.",
        "Stell dir vor du verdoppelst deine Reichweite. Das Geheimnis ist der Hook.",
    ]
    for text in blocks:
        words = text.split()
        per = 14.0 / len(words)
        wlist, start = [], t
        for w in words:
            wlist.append(Word(w, round(t, 3), round(t + per * 0.9, 3)))
            t += per
        segments.append(TranscriptSegment(text, start, t, wlist))
        t += 1.0
    return Transcript(language="de", duration=t, segments=segments)


def test_segmenter_respects_bounds():
    s = get_settings()
    tr = _make_transcript()
    clips = build_candidates(tr, s)
    assert clips, "Segmenter sollte mindestens einen Clip liefern"
    for c in clips:
        assert s.min_clip_seconds <= c.duration <= s.max_clip_seconds + 1
        assert c.text.strip()
        assert c.words


def test_scoring_is_sorted_and_bounded():
    s = get_settings()
    tr = _make_transcript()
    clips = build_candidates(tr, s)
    scored = score_clips(clips, s)
    assert scored
    scores = [c.score for c in scored]
    assert scores == sorted(scores, reverse=True), "Clips müssen absteigend sortiert sein"
    for c in scored:
        assert 0 <= c.score <= 100
        for v in (c.breakdown.hook, c.breakdown.clarity, c.breakdown.emotion,
                  c.breakdown.pacing, c.breakdown.payoff):
            assert 0 <= v <= 100


def test_hook_beats_filler():
    """Ein starker Hook-Clip sollte höher scoren als ein Fülltext-Clip."""
    s = get_settings()
    from clipforge.models import CandidateClip
    hook = CandidateClip(
        0, 20,
        "Warum scheitern die meisten an ihrem Geld? Der Fehler ist simpel. Deshalb verlierst du. Das ist die Pointe.",
        [Word("Warum", 0, 0.4)],
    )
    filler = CandidateClip(
        0, 20,
        "Also ja, ich sitze hier so rum und ähm, weiß auch nicht, naja, es ist halt so.",
        [Word("Also", 0, 0.4)],
    )
    from clipforge.scoring import score_heuristic
    assert score_heuristic(hook, s).score > score_heuristic(filler, s).score


def test_captions_timing_relative_and_bounded():
    words = [Word("Hallo", 10.0, 10.4), Word("Welt", 10.5, 11.0),
             Word("hier", 11.1, 11.5), Word("Test", 11.6, 12.0)]
    lines = group_words(words, clip_start=10.0, max_words=3)
    assert lines
    assert lines[0][0] == 0.0  # erstes Wort relativ zu clip_start
    ass = build_ass(words, clip_start=10.0, clip_end=12.0)
    assert "[Events]" in ass and "Dialogue:" in ass


def _run_all():
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for fn in fns:
        fn()
        print(f"  ✓ {fn.__name__}")
    print(f"\n{len(fns)} Tests bestanden.")


if __name__ == "__main__":
    _run_all()
