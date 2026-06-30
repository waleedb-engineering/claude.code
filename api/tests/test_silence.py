"""Deterministische Tests für die Silence-Removal-Logik (ohne ffmpeg)."""

from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from clipforge.models import Word
from clipforge.silence import (
    audio_smoothing_filter,
    keep_intervals,
    kept_seconds,
    remap_time,
    remap_words,
    removed_seconds,
    select_expr,
)


def test_keep_intervals_complement():
    # Clip 0..10, Stille [4,6]. Pad 0.0 -> Keeps [0,4] und [6,10].
    keeps = keep_intervals([(4.0, 6.0)], duration=10.0, pad=0.0)
    assert keeps == [(0.0, 4.0), (6.0, 10.0)]
    assert round(removed_seconds(keeps, 10.0), 3) == 2.0
    assert round(kept_seconds(keeps), 3) == 8.0


def test_keep_intervals_padding_keeps_speech():
    # Pad verkleinert den Schnitt -> weniger entfernt, schützt Wortgrenzen.
    keeps = keep_intervals([(4.0, 6.0)], duration=10.0, pad=0.1)
    # Schnitt nur [4.1, 5.9] -> entfernt 1.8s
    assert round(removed_seconds(keeps, 10.0), 3) == 1.8


def test_keep_intervals_merges_overlaps():
    keeps = keep_intervals([(2.0, 4.0), (3.5, 6.0)], duration=10.0, pad=0.0)
    assert keeps == [(0.0, 2.0), (6.0, 10.0)]


def test_no_silence_returns_full():
    keeps = keep_intervals([], duration=10.0, pad=0.1)
    assert keeps == [(0.0, 10.0)]
    assert removed_seconds(keeps, 10.0) == 0.0


def test_remap_time_compresses_after_cut():
    keeps = [(0.0, 4.0), (6.0, 10.0)]  # 2s in der Mitte entfernt
    assert remap_time(2.0, keeps) == 2.0       # vor dem Schnitt unverändert
    assert remap_time(7.0, keeps) == 5.0       # nach Schnitt um 2s nach vorn
    assert remap_time(5.0, keeps) == 4.0       # in der Stille -> auf Grenze
    assert remap_time(10.0, keeps) == 8.0      # Ende = neue Gesamtlänge


def test_remap_words_relative_and_monotonic():
    # clip_start=100 (absolut). Stille zwischen den Wörtern entfernt.
    keeps = [(0.0, 4.0), (6.0, 10.0)]
    words = [
        Word("a", 100.0, 101.0),   # rel 0..1 -> 0..1
        Word("b", 103.0, 104.0),   # rel 3..4 -> 3..4
        Word("c", 106.0, 107.0),   # rel 6..7 -> 4..5 (um 2s gestaucht)
    ]
    out = remap_words(words, clip_start=100.0, keeps=keeps)
    assert [round(w.start, 3) for w in out] == [0.0, 3.0, 4.0]
    assert [round(w.end, 3) for w in out] == [1.0, 4.0, 5.0]
    # monoton steigend
    times = [w.start for w in out] + [out[-1].end]
    assert times == sorted(times)


def test_select_expr_format():
    expr = select_expr([(0.0, 4.0), (6.0, 10.0)])
    assert expr == "between(t,0.000,4.000)+between(t,6.000,10.000)"
    assert select_expr([]) == "1"


def test_audio_smoothing_filter_multi_segment():
    keeps = [(0.0, 4.0), (6.0, 10.0)]
    f = audio_smoothing_filter(keeps, fade=0.015)
    # zwei getrimmte Segmente + concat zu [a]
    assert f.count("atrim=") == 2
    assert "afade=t=in" in f and "afade=t=out" in f
    assert "concat=n=2:v=0:a=1[a]" in f
    # Trim-Grenzen entsprechen den Keep-Intervallen (Dauer bleibt erhalten)
    assert "atrim=0.000:4.000" in f and "atrim=6.000:10.000" in f


def test_audio_smoothing_filter_single_segment():
    f = audio_smoothing_filter([(0.0, 5.0)], fade=0.015)
    assert "concat" not in f          # ein Segment -> direkt [a]
    assert f.endswith("[a]")
    assert "atrim=0.000:5.000" in f


def test_audio_smoothing_tiny_segment_skips_fade():
    # Sehr kurzes Segment (< 8 ms) -> keine Fades, aber gültiger Trim.
    f = audio_smoothing_filter([(0.0, 0.004)], fade=0.015)
    assert "atrim=0.000:0.004" in f
    assert "afade" not in f


def _run_all():
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for fn in fns:
        fn()
        print(f"  ✓ {fn.__name__}")
    print(f"\n{len(fns)} Tests bestanden.")


if __name__ == "__main__":
    _run_all()
