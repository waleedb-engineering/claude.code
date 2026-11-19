"""Auswertung der Highlight-Erkennung gegen manuell markierte Highlights.

Annotation (JSON, je Aufnahme):
    {"version": 1, "source": "eigener Twitch-VOD 2026-11-02", "synthetic": false,
     "highlights": [{"start": 812.0, "end": 829.5, "peak": 818.0, "label": "Clutch"}]}

Zuordnung: Ein erkanntes Highlight trifft ein markiertes, wenn sein
Ereigniszeitpunkt ``t`` in [start − Toleranz, end + Toleranz] liegt. Jede
Markierung wird höchstens einmal gezählt (gierig nach Score). Daraus:
Präzision, Recall, F1, Präzision@k, Zeitabweichung zum Höhepunkt und ob der
Clip das markierte Ereignis vollständig enthält (nichts abgeschnitten).

Gewichts-Tuning ist nur für echte, vom Nutzer markierte Daten gedacht; das
Ergebnis enthält immer eine Leave-one-out-Schätzung, damit Überanpassung an
einzelne Aufnahmen sichtbar wird.
"""

from __future__ import annotations

import itertools
import json
import os
import statistics

from . import scoring
from .chat import ChatMessage, per_second


def load_labels(raw) -> list[dict]:
    data = json.loads(raw) if isinstance(raw, (str, bytes)) else raw
    items = data.get("highlights") if isinstance(data, dict) else data
    if not isinstance(items, list):
        raise ValueError("Annotation braucht eine Liste 'highlights'.")
    out = []
    for i, h in enumerate(items):
        try:
            s, e = float(h["start"]), float(h["end"])
        except (KeyError, TypeError, ValueError) as exc:
            raise ValueError(f"Markierung {i + 1}: start/end fehlen.") from exc
        if not 0 <= s < e:
            raise ValueError(f"Markierung {i + 1}: ungültige Grenzen.")
        peak = float(h.get("peak", (s + e) / 2))
        item = {"start": s, "end": e, "peak": min(max(peak, s), e), "label": str(h.get("label", ""))[:80]}
        if isinstance(h.get("from"), str) and len(h["from"]) <= 8:
            item["from"] = h["from"]  # aus erkanntem Highlight bestätigt
        out.append(item)
    return sorted(out, key=lambda x: x["start"])


def match(predicted: list[dict], labels: list[dict], tolerance: float = 5.0) -> list[tuple[dict, dict | None]]:
    """Gierige 1:1-Zuordnung nach absteigendem Score."""
    free = list(range(len(labels)))
    pairs = []
    for p in sorted(predicted, key=lambda x: -float(x.get("score", 0))):
        best, best_d = None, None
        for j in free:
            g = labels[j]
            if g["start"] - tolerance <= p["t"] <= g["end"] + tolerance:
                d = abs(p["t"] - g["peak"])
                if best_d is None or d < best_d:
                    best, best_d = j, d
        if best is not None:
            free.remove(best)
        pairs.append((p, labels[best] if best is not None else None))
    return pairs


def evaluate(predicted: list[dict], labels: list[dict], tolerance: float = 5.0, ks=(1, 3, 5)) -> dict:
    pairs = match(predicted, labels, tolerance)
    tp = sum(1 for _, g in pairs if g)
    fp, fn = len(pairs) - tp, len(labels) - tp
    prec = tp / (tp + fp) if tp + fp else 0.0
    rec = tp / (tp + fn) if tp + fn else 0.0
    f1 = 2 * prec * rec / (prec + rec) if prec + rec else 0.0
    offsets = [abs(p["t"] - g["peak"]) for p, g in pairs if g]
    contained = [p["start"] <= g["start"] + 0.5 and p["end"] >= g["end"] - 0.5 for p, g in pairs if g]
    start_err = [p["start"] - g["start"] for p, g in pairs if g]
    end_err = [p["end"] - g["end"] for p, g in pairs if g]
    ranked = sorted(pairs, key=lambda x: -float(x[0].get("score", 0)))
    p_at = {f"p@{k}": round(sum(1 for _, g in ranked[:k] if g) / k, 3) for k in ks if len(ranked) >= k}
    return {
        "tp": tp, "fp": fp, "fn": fn, "precision": round(prec, 3), "recall": round(rec, 3), "f1": round(f1, 3),
        **p_at,
        "time_offset_mean_s": round(statistics.fmean(offsets), 2) if offsets else None,
        "time_offset_median_s": round(statistics.median(offsets), 2) if offsets else None,
        "event_fully_contained": round(sum(contained) / len(contained), 3) if contained else None,
        "start_error_mean_s": round(statistics.fmean(start_err), 2) if start_err else None,
        "end_error_mean_s": round(statistics.fmean(end_err), 2) if end_err else None,
        "tolerance_s": tolerance,
        "missed": [{"start": g["start"], "end": g["end"], "label": g["label"]}
                   for g in labels if all(g is not m for _, m in pairs)],
        "false_positives": [{"t": p["t"], "score": p.get("score")} for p, g in pairs if not g],
    }


def aggregate(results: list[dict]) -> dict:
    tp = sum(r["tp"] for r in results)
    fp = sum(r["fp"] for r in results)
    fn = sum(r["fn"] for r in results)
    prec = tp / (tp + fp) if tp + fp else 0.0
    rec = tp / (tp + fn) if tp + fn else 0.0
    offs = [r["time_offset_mean_s"] for r in results if r["time_offset_mean_s"] is not None]
    cont = [r["event_fully_contained"] for r in results if r["event_fully_contained"] is not None]
    return {"cases": len(results), "tp": tp, "fp": fp, "fn": fn, "precision": round(prec, 3),
            "recall": round(rec, 3), "f1": round(2 * prec * rec / (prec + rec), 3) if prec + rec else 0.0,
            "time_offset_mean_s": round(statistics.fmean(offs), 2) if offs else None,
            "event_fully_contained": round(statistics.fmean(cont), 3) if cont else None}


# ------------------------------------------------------------- Detektion
def detect(measured: dict, chat: list[ChatMessage] | None, *, weights: dict | None = None,
           max_clips: int = 8, pre: float = 10.0, post: float = 8.0, min_len: float = 12.0,
           max_len: float = 60.0, chat_delay: float | None = None) -> list[dict]:
    """Nur Scoring + Grenzen auf gespeicherten Signalen (ohne Transkript) — schnell."""
    duration = float(measured["duration"])
    chat_ps = per_second(chat, duration) if chat else None
    tl = scoring.score_timeline(duration, chat=chat_ps, audio=measured.get("audio"),
                                video=measured.get("video"), chat_delay=chat_delay, weights=weights)
    cands = scoring.pick_candidates(tl, chat=chat_ps, max_count=max_clips * 2)
    clips = []
    for c in cands:
        s, e, _ = scoring.clip_bounds(c.t, duration, None, pre=pre, post=post, min_len=min_len, max_len=max_len)
        clips.append({"t": c.t, "start": s, "end": e, "score": c.score})
    return scoring.dedupe(clips)[:max_clips]


GROUPS = ("chat", "audio", "video")


def weights_from_groups(g: dict) -> dict:
    """Gruppenfaktoren (chat/audio/video) auf die Einzelgewichte anwenden."""
    return {k: v * g.get(scoring.GROUP[k], 1.0) for k, v in scoring.DEFAULT_WEIGHTS.items()}


def tune(cases: list[dict], *, grid=(0.5, 1.0, 1.5, 2.0), tolerance: float = 5.0, **kw) -> dict:
    """Rastersuche über Gruppenfaktoren. ``cases``: [{name, measured, chat, labels}].

    Liefert beste Faktoren, F1 mit Standard- und mit getunten Gewichten sowie
    eine Leave-one-out-Schätzung (für jede Aufnahme mit den auf den übrigen
    Aufnahmen getunten Gewichten ausgewertet)."""
    if not cases:
        raise ValueError("Keine markierten Aufnahmen vorhanden.")
    combos = [dict(zip(GROUPS, c)) for c in itertools.product(grid, repeat=len(GROUPS))]
    cache: dict[tuple, list[dict]] = {}

    def run(combo, idx):
        key = (tuple(combo.values()), idx)
        if key not in cache:
            c = cases[idx]
            pred = detect(c["measured"], c.get("chat"), weights=weights_from_groups(combo), **kw)
            cache[key] = evaluate(pred, c["labels"], tolerance)
        return cache[key]

    def score(combo, idxs):
        return aggregate([run(combo, i) for i in idxs])["f1"]

    all_idx = list(range(len(cases)))
    default = {g: 1.0 for g in GROUPS}
    best = max(combos, key=lambda c: (score(c, all_idx), c == default))
    loo = None
    if len(cases) >= 2:
        per = []
        for i in all_idx:
            rest = [j for j in all_idx if j != i]
            b = max(combos, key=lambda c: (score(c, rest), c == default))
            per.append(run(b, i))
        loo = aggregate(per)["f1"]
    return {"best_group_factors": best, "weights": {k: round(v, 4) for k, v in weights_from_groups(best).items()},
            "f1_default": score(default, all_idx), "f1_tuned": score(best, all_idx),
            "f1_leave_one_out": loo, "cases": len(cases), "combinations": len(combos),
            "note": "Mit wenigen Aufnahmen ist die Leave-one-out-Zahl die ehrlichere Schätzung."}


# ------------------------------------------------------------------- CLI
def _load_case(folder: str, name: str, measure_fn) -> dict:
    from .chat import parse_chat
    base = os.path.join(folder, name)
    video = next((base + e for e in (".mp4", ".mkv", ".mov", ".webm", ".flv") if os.path.exists(base + e)), None)
    if not video:
        raise FileNotFoundError(f"Kein Video für {name}")
    cache = base + ".signals.json"
    measured = None
    if os.path.exists(cache):
        with open(cache, encoding="utf-8") as fh:
            measured = json.load(fh)
    timing = {"cached": True}
    if measured is None or measured.get("version") != _signal_version():
        import time
        t0 = time.perf_counter()
        measured = measure_fn(video)
        timing = {"cached": False, "measure_s": round(time.perf_counter() - t0, 2),
                  "realtime_factor": round(measured["duration"] / max(0.01, time.perf_counter() - t0), 1)}
        with open(cache, "w", encoding="utf-8") as fh:
            json.dump(measured, fh)
    chat = None
    for ext in (".chat.json", ".chat.jsonl", ".chat.csv"):
        if os.path.exists(base + ext):
            with open(base + ext, "rb") as fh:
                chat, _ = parse_chat(fh.read(), base + ext)
            break
    with open(base + ".labels.json", encoding="utf-8") as fh:
        raw = json.load(fh)
    return {"name": name, "measured": measured, "chat": chat, "labels": load_labels(raw), "timing": timing,
            "synthetic": bool(raw.get("synthetic")) if isinstance(raw, dict) else False}


def _peak_rss_mb() -> dict:
    try:
        import resource
    except ImportError:  # Windows
        return {}
    k = 1024 if os.uname().sysname != "Darwin" else 1024 * 1024
    return {"python": round(resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / k, 1),
            "ffmpeg_max": round(resource.getrusage(resource.RUSAGE_CHILDREN).ru_maxrss / k, 1)}


def _signal_version() -> int:
    from .analyze import SIGNAL_VERSION
    return SIGNAL_VERSION


def main(argv=None) -> int:
    import argparse
    from .analyze import measure
    ap = argparse.ArgumentParser(description="Highlight-Erkennung gegen markierte Highlights auswerten.")
    ap.add_argument("folder", help="Ordner mit <name>.mp4, optional <name>.chat.json, <name>.labels.json")
    ap.add_argument("--tolerance", type=float, default=5.0)
    ap.add_argument("--max-clips", type=int, default=8)
    ap.add_argument("--tune", action="store_true", help="Gruppengewichte per Rastersuche anpassen")
    ap.add_argument("--json", help="Ergebnis zusätzlich als JSON speichern")
    a = ap.parse_args(argv)
    names = sorted(f[: -len(".labels.json")] for f in os.listdir(a.folder) if f.endswith(".labels.json"))
    cases = [_load_case(a.folder, n, measure) for n in names]
    rows = []
    for c in cases:
        pred = detect(c["measured"], c["chat"], max_clips=a.max_clips)
        r = evaluate(pred, c["labels"], a.tolerance)
        rows.append(r)
        r["timing"] = c["timing"]
        r["duration_s"] = round(c["measured"]["duration"], 1)
        tag = " (synthetisch)" if c["synthetic"] else ""
        print(f"{c['name']}{tag}: P={r['precision']:.2f} R={r['recall']:.2f} F1={r['f1']:.2f} "
              f"Δt={r['time_offset_mean_s']} s vollständig={r['event_fully_contained']} {c['timing']}")
    out = {"per_case": dict(zip(names, rows)), "total": aggregate(rows), "peak_rss_mb": _peak_rss_mb()}
    print("Gesamt:", out["total"])
    if a.tune:
        out["tuning"] = tune(cases, tolerance=a.tolerance, max_clips=a.max_clips)
        print("Tuning:", out["tuning"])
        if any(c["synthetic"] for c in cases):
            print("Hinweis: synthetische Daten — Gewichte NICHT für den Produktivbetrieb übernehmen.")
    if a.json:
        with open(a.json, "w", encoding="utf-8") as fh:
            json.dump(out, fh, ensure_ascii=False, indent=2)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
