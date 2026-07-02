"""Kalibrierungs-Report: Kandidaten, Scores, Verteilung je Fixture.

Reproduziert die Zahlen in docs/ANALYZER_CALIBRATION.md:
    python api/tests/calibration_report.py
"""
import os, sys, statistics
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from clipforge.analyzer import RuleBasedClipAnalyzer, build_candidates_v2
from clipforge.config import Settings
import transcripts_fixtures as F

S = Settings(anthropic_api_key=None, use_llm=False)


def report():
    all_scores = []
    for name, fn in F.ALL_FIXTURES.items():
        tr = fn()
        raw = build_candidates_v2(tr, S)
        clips, meta = RuleBasedClipAnalyzer().analyze(tr, S, 8)
        scores = [c.performance_score for c in clips]
        all_scores += scores
        print(f"\n=== {name}  (dur~{tr.duration:.0f}s, segs={len(tr.segments)}) ===")
        print(f"  candidates={meta['candidate_count']} dedup={meta['deduplicated_count']} selected={len(clips)}")
        for c in sorted(clips, key=lambda x: x.performance_score, reverse=True)[:8]:
            flags = ",".join(c.risk_flags) or "-"
            dg = c.duplicate_group
            print(f"   {c.performance_score:5.1f} [{c.duration:4.0f}s] dg={dg} hook={c.hook_type:10s} "
                  f"flags={flags:30s} | {c.text[:52]}")
    if all_scores:
        print(f"\n=== GESAMT ({len(all_scores)} clips) ===")
        print(f"  min={min(all_scores):.1f} max={max(all_scores):.1f} "
              f"mean={statistics.mean(all_scores):.1f} median={statistics.median(all_scores):.1f}")
        bands = {"weak<60": 0, "solid60-74": 0, "good75-84": 0, "vstrong85-94": 0, "95+": 0}
        for s in all_scores:
            if s < 60: bands["weak<60"] += 1
            elif s < 75: bands["solid60-74"] += 1
            elif s < 85: bands["good75-84"] += 1
            elif s < 95: bands["vstrong85-94"] += 1
            else: bands["95+"] += 1
        print("  bands:", bands)


if __name__ == "__main__":
    report()
