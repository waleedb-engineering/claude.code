"""Erklärbares Highlight-Scoring aus Chat-, Audio-, Video- und Transkript-Signalen.

Jede Komponente ist ein robuster z-Wert (gleitender Median/MAD) einer
messbaren Größe, auf [0, 4] begrenzt und gewichtet. Fehlt ein Signal (z. B.
kein Chat), werden die Gewichte der vorhandenen Signale neu normiert — das
steht im Ergebnis. Der Score ist eine Rangfolge für Kandidaten, KEINE
Viralitäts-Wahrscheinlichkeit.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

import numpy as np

from .signals import robust_z, smooth

DEFAULT_WEIGHTS = {
    "chat_rate": 0.15, "chat_unique": 0.08, "chat_reaction": 0.12,
    "audio_loud": 0.12, "audio_rise": 0.10, "audio_bright": 0.08,
    "video_motion": 0.10, "video_scene": 0.05,
    "transcript": 0.15, "tension": 0.05,
}
GROUP = {"chat_rate": "chat", "chat_unique": "chat", "chat_reaction": "chat",
         "audio_loud": "audio", "audio_rise": "audio", "audio_bright": "audio", "tension": "audio",
         "video_motion": "video", "video_scene": "video", "transcript": "transcript"}
LABEL = {
    "chat_rate": "Chat-Aktivität", "chat_unique": "viele verschiedene Chatter",
    "chat_reaction": "Chat-Reaktionen", "audio_loud": "Lautstärke",
    "audio_rise": "plötzlicher Lautstärkesprung", "audio_bright": "laut und hell (Schrei/Jubel-Heuristik)",
    "video_motion": "starke Bewegung im Bild", "video_scene": "Szenenwechsel",
    "transcript": "Aussage im Transkript", "tension": "Stille vor dem Ausbruch",
}
REACTION_PHRASES = re.compile(
    r"\b(no way|oh my god|oh mein gott|let'?s go|was zum|what the|ich glaub(e)? es nicht|"
    r"unglaublich|krass|alter|digga|hahaha+|wow+|nein+|ja+ ?!|boah+|holy|insane|bro)\b", re.I)


@dataclass
class Candidate:
    t: float                      # Ereigniszeit (Chat-Verzögerung bereits abgezogen)
    score: float                  # 0–100
    components: dict = field(default_factory=dict)  # Komponente → Beitrag (Punkte)
    reasons: list[str] = field(default_factory=list)
    chat_categories: dict = field(default_factory=dict)
    top_terms: list[str] = field(default_factory=list)


def estimate_chat_delay(chat_rate: np.ndarray, audio_z: np.ndarray | None,
                        default: float = 5.0, max_lag: int = 15) -> tuple[float, str]:
    """Verzögerung Chat ↔ Ereignis per Kreuzkorrelation mit der Lautheit.

    Nur verwendet, wenn die Korrelation klar ist; sonst Standardwert."""
    if audio_z is None or chat_rate.size < 120:
        return default, "Standardwert (zu wenig Daten)"
    n = min(chat_rate.size, audio_z.size)
    c = robust_z(smooth(chat_rate[:n], 3))
    a = np.clip(audio_z[:n], 0, None)
    best, best_lag = 0.0, None
    for lag in range(0, max_lag + 1):
        x, y = a[:n - lag], c[lag:n]
        if x.std() < 1e-6 or y.std() < 1e-6:
            continue
        r = float(np.corrcoef(x, y)[0, 1])
        if r > best:
            best, best_lag = r, lag
    if best_lag is not None and best >= 0.2:
        return float(best_lag), f"aus Daten geschätzt (Korrelation {best:.2f})"
    return default, "Standardwert (keine klare Korrelation)"


def transcript_series(words: list, n: int, keywords: list[str] | None = None) -> tuple[np.ndarray, dict]:
    """Punkte je Sekunde aus Wörtern: Reaktionsphrasen, Ausrufe, Frage→Antwort, Stichwörter."""
    s = np.zeros(n, dtype=np.float32)
    notes: dict[int, list[str]] = {}
    kws = [k.lower() for k in (keywords or []) if k.strip()]
    for i, w in enumerate(words):
        t = int(w.start)
        if t >= n:
            continue
        text = w.text.strip()
        window = " ".join(x.text for x in words[max(0, i - 2): i + 3])
        if REACTION_PHRASES.search(window) and REACTION_PHRASES.search(text):
            s[t] += 1.5
            notes.setdefault(t, []).append(f"Reaktion „{text.strip(' ,.')}“")
        if text.endswith("!"):
            s[t] += 0.7
        if text.endswith("?"):
            nxt = words[i + 1] if i + 1 < len(words) else None
            if nxt and nxt.start - w.end < 2.0:
                s[t] += 0.5
                notes.setdefault(t, []).append("Frage mit direkter Antwort")
        if kws and any(k in text.lower() for k in kws):
            s[t] += 2.0
            notes.setdefault(t, []).append(f"Stichwort „{text.strip(' ,.!?')}“")
    return smooth(s, 3) * 2.0, notes  # 3-s-Fenster → z-ähnliche Größenordnung


def score_timeline(duration: float, *, chat: dict | None = None, audio: dict | None = None,
                   video: dict | None = None, words: list | None = None,
                   keywords: list[str] | None = None, chat_delay: float | None = None,
                   weights: dict | None = None) -> dict:
    n = max(1, int(duration) + 1)
    w = dict(DEFAULT_WEIGHTS, **(weights or {}))

    def fit(x) -> np.ndarray:
        x = np.asarray(x, dtype=np.float32)[:n]
        return np.pad(x, (0, n - x.size)) if x.size < n else x

    comp: dict[str, np.ndarray] = {}
    used, delay_note = set(), ""
    audio_z = None
    if audio:
        loud = fit(audio["loudness_db"])
        audio_z = robust_z(loud, floor=1.5)
        comp["audio_loud"] = audio_z
        rise = np.zeros(n, dtype=np.float32)
        rise[2:] = (loud[2:] - loud[:-2]) / 3.0  # ~3 dB pro z-Einheit
        comp["audio_rise"] = rise
        cent_z = robust_z(fit(audio["centroid_hz"]), floor=150.0)
        comp["audio_bright"] = np.minimum(audio_z, cent_z)
        quiet = (audio_z < -0.8).astype(np.float32)
        before = np.convolve(quiet, np.ones(4), mode="full")[:n]  # 4 s Stille davor
        tension = np.zeros(n, dtype=np.float32)
        tension[1:] = (before[:-1] >= 3) * np.clip(rise[1:], 0, None)
        comp["tension"] = tension
        used.add("audio")
    if chat:
        rate = fit(chat["rate"]).astype(np.float32)
        if chat_delay is None:
            chat_delay, delay_note = estimate_chat_delay(rate, audio_z)
        else:
            delay_note = "vom Nutzer gesetzt"
        d = int(round(chat_delay))
        shift = (lambda x: np.concatenate([x[d:], np.zeros(d, np.float32)])) if d > 0 else (lambda x: x)
        comp["chat_rate"] = shift(robust_z(smooth(rate, 3)))
        comp["chat_unique"] = shift(robust_z(smooth(fit(chat["unique"]), 3)))
        react = sum(fit(chat["categories"][k]) for k in ("laugh", "hype", "shock", "clip"))
        neg = fit(chat["categories"]["negative"])
        comp["chat_reaction"] = shift(robust_z(smooth(react - 0.5 * neg, 3)))
        used.add("chat")
    else:
        chat_delay = 0.0
    if video:
        comp["video_motion"] = robust_z(fit(video["motion"]), floor=0.5)
        sc = fit(video["scene"])
        comp["video_scene"] = (sc > max(12.0, float(np.median(sc)) * 4)).astype(np.float32) * 3.0
        used.add("video")
    t_notes: dict = {}
    if words:
        comp["transcript"], t_notes = transcript_series(words, n, keywords)
        used.add("transcript")

    active = {k: v for k, v in w.items() if GROUP[k] in used and k in comp}
    total_w = sum(active.values()) or 1.0
    norm = {k: v / total_w for k, v in active.items()}
    contrib = {k: np.clip(comp[k], 0, 4) / 4 * norm[k] * 100 for k in norm}
    score = smooth(sum(contrib.values()), 3) if contrib else np.zeros(n)
    return {"score": score, "contrib": contrib, "components": comp, "weights": norm,
            "signals": sorted(used), "chat_delay": chat_delay, "chat_delay_note": delay_note,
            "transcript_notes": t_notes, "n": n}


def pick_candidates(tl: dict, *, chat: dict | None = None, max_count: int = 10,
                    min_gap: float = 30.0, min_score: float = 12.0) -> list[Candidate]:
    """Lokale Maxima mit Mindestabstand (Non-Maximum-Suppression)."""
    score = tl["score"]
    order = np.argsort(-score)
    taken: list[int] = []
    for i in order:
        if score[i] < min_score or len(taken) >= max_count * 3:
            break
        if all(abs(int(i) - j) >= min_gap for j in taken):
            taken.append(int(i))
    out = []
    d = int(round(tl["chat_delay"]))
    for i in taken[:max_count]:
        parts = {k: float(v[i]) for k, v in tl["contrib"].items() if v[i] > 0.5}
        reasons = []
        for k, pts in sorted(parts.items(), key=lambda x: -x[1])[:4]:
            z = float(tl["components"][k][i])
            reasons.append(f"{LABEL[k]}: +{pts:.0f} Punkte (z={z:.1f})")
        for note in tl["transcript_notes"].get(i, [])[:2]:
            reasons.append(note)
        cats, terms = {}, []
        if chat:
            lo, hi = i + d, i + d + 6
            for k, series in chat["categories"].items():
                c = int(sum(series[lo:hi]))
                if c:
                    cats[k] = c
            bag: dict[str, int] = {}
            for wl in chat["words"][lo:hi]:
                for word in wl:
                    bag[word] = bag.get(word, 0) + 1
            terms = [w for w, c in sorted(bag.items(), key=lambda x: -x[1]) if c >= 3][:5]
            base = float(np.median(chat["rate"])) or 0.5
            peak = max(chat["rate"][lo:hi] or [0])
            if peak:
                reasons.append(f"Chat {peak} Nachrichten/s statt üblich {base:.1f} "
                               f"({peak / base:.1f}×), Verzögerung {d} s berücksichtigt")
        out.append(Candidate(t=float(i), score=round(float(score[i]), 1),
                             components={k: round(v, 1) for k, v in parts.items()},
                             reasons=reasons, chat_categories=cats, top_terms=terms))
    return out


# ------------------------------------------------------------ Clip-Grenzen
def clip_bounds(t: float, duration: float, words: list | None, *, pre: float = 10.0,
                post: float = 8.0, min_len: float = 12.0, max_len: float = 60.0) -> tuple[float, float, str]:
    """Fenster um das Ereignis; an Satzgrenzen ausgerichtet, wenn Wörter da sind."""
    start, end = max(0.0, t - pre), min(duration, t + post)
    note = "festes Fenster"
    if words:
        ws = [w for w in words if start - 6 <= w.start <= end + 12]
        # Start: Wortbeginn nach einer Satzgrenze/Pause, möglichst nah vor `start`
        best = None
        for i, w in enumerate(ws):
            prev = ws[i - 1] if i else None
            boundary = prev is None or prev.text.rstrip().endswith((".", "!", "?")) or w.start - prev.end > 0.6
            if boundary and w.start <= start + 1.5:
                best = w.start
        if best is not None:
            start = max(0.0, best - 0.15)
            note = "an Satzanfang ausgerichtet"
        # Ende in einer Pause nach einem Satzende → direkt nach dem Satz enden
        before = [w for w in ws if w.end <= end]
        after = [w for w in ws if w.start >= end]
        if before and before[-1].text.rstrip().endswith((".", "!", "?")) and \
                (not after or after[0].start > end):
            end = min(duration, before[-1].end + 0.3)
            ws = []  # fertig
            note += ", endet am Satzende"
        # Ende: erstes Satzende nach `end`, sonst letztes Wortende vor `end`
        for i, w in enumerate(ws):
            if w.end >= end and (w.text.rstrip().endswith((".", "!", "?")) or
                                 (i + 1 < len(ws) and ws[i + 1].start - w.end > 0.6)):
                end = min(duration, w.end + 0.3)
                note += ", Satz nicht abgeschnitten"
                break
    if end - start < min_len:
        end = min(duration, start + min_len)
        start = max(0.0, end - min_len)
    if end - start > max_len:
        end = start + max_len
    return round(start, 2), round(end, 2), note


def dedupe(clips: list[dict], max_overlap: float = 0.4) -> list[dict]:
    """Fast gleiche Clips entfernen (Überlappung relativ zum kürzeren)."""
    kept: list[dict] = []
    for c in sorted(clips, key=lambda x: -x["score"]):
        ok = True
        for k in kept:
            inter = max(0.0, min(c["end"], k["end"]) - max(c["start"], k["start"]))
            shorter = min(c["end"] - c["start"], k["end"] - k["start"]) or 1
            if inter / shorter > max_overlap:
                ok = False
                break
        if ok:
            kept.append(c)
    return kept


# ------------------------------------------------------------ Varianten
VARIANTS = {
    # Name → (Faktor Vorlauf, Faktor Nachlauf, Obergrenze Länge, Bezeichnung)
    "short": (0.5, 0.6, 30.0, "Kurz"),
    "balanced": (1.0, 1.0, None, "Ausgewogen"),
    "context": (2.0, 1.6, None, "Mehr Kontext"),
}


def suitability(c: dict, words: list | None, note: str, *, target: tuple[float, float] = (15.0, 45.0)) -> tuple[int, list[str]]:
    """Heuristische Eignung eines Clip-Fensters für Kurzvideo (0–100).

    Bewertet nur Prüfbares: Ereignis vollständig enthalten, Satzgrenzen,
    Länge im Zielbereich, Sprechanteil, Signalstärke. KEINE Reichweiten- oder
    Viralitätsprognose."""
    pts, why = 0.0, []
    start, end, t = c["start"], c["end"], c["t"]
    dur = end - start
    if start + 1.5 <= t <= end - 2.0:
        pts += 25
        why.append("Ereignis mit Vor- und Nachlauf enthalten")
    elif start <= t <= end:
        pts += 10
        why.append("Ereignis knapp am Rand")
    else:
        why.append("Ereignis liegt außerhalb des Fensters")
    if "Satzanfang" in note:
        pts += 10
        why.append("beginnt am Satzanfang")
    if "Satzende" in note or "nicht abgeschnitten" in note:
        pts += 10
        why.append("endet nach vollständigem Satz")
    lo, hi = target
    if lo <= dur <= hi:
        pts += 25
        why.append(f"Länge {dur:.0f} s im Zielbereich {lo:.0f}–{hi:.0f} s")
    else:
        off = (lo - dur) if dur < lo else (dur - hi)
        pts += max(0.0, 25 - off * 1.2)
        why.append(f"Länge {dur:.0f} s außerhalb {lo:.0f}–{hi:.0f} s")
    if words:
        spoken = sum(max(0.0, min(w.end, end) - max(w.start, start)) for w in words
                     if w.end > start and w.start < end)
        ratio = spoken / dur if dur > 0 else 0
        pts += 10 * min(1.0, ratio / 0.5)
        why.append(f"Sprechanteil {ratio * 100:.0f} %")
    else:
        pts += 5
    pts += 20 * min(1.0, float(c.get("score", 0)) / 60.0)
    return int(round(min(100.0, pts))), why


def clip_variants(c: dict, duration: float, words: list | None, note: str, *, pre: float, post: float,
                  min_len: float, max_len: float) -> list[dict]:
    out = []
    seen = set()
    order = ["balanced"] + [k for k in VARIANTS if k != "balanced"]
    for name in order:
        fp, fq, cap, label = VARIANTS[name]
        if name == "balanced":
            s, e, n = c["start"], c["end"], note
        else:
            ml = min(max_len, cap) if cap else max_len
            s, e, n = clip_bounds(c["t"], duration, words, pre=max(2.0, pre * fp), post=max(2.0, post * fq),
                                  min_len=min(min_len, ml), max_len=ml)
        if (s, e) in seen:
            continue
        seen.add((s, e))
        fit, why = suitability({"start": s, "end": e, "t": c["t"], "score": c["score"]}, words, n)
        out.append({"variant": name, "label": label, "start": s, "end": e, "duration": round(e - s, 2),
                    "suitability": fit, "suitability_reasons": why, "cut": n})
    return sorted(out, key=lambda v: list(VARIANTS).index(v["variant"]))
