"""Reine, ffmpeg-unabhängige Logik für Silence-Removal ("schnelle Schnitte").

Kernidee: Aus erkannten Stille-Intervallen werden **Keep-Intervalle** (die zu
behaltenden Abschnitte) berechnet. Genau dieselben Keep-Intervalle werden
verwendet für
  1) den FFmpeg-select/aselect-Filter (Video + Audio bleiben synchron) und
  2) das Re-Mapping der Wort-Timestamps für die Untertitel.

Dadurch bleiben Bild, Ton und Captions nach dem Entfernen der Pausen synchron.

Alle Zeiten hier sind **clip-relativ** (0 = Clip-Anfang).
"""

from __future__ import annotations

from .models import Word

Interval = tuple[float, float]


def keep_intervals(
    silences: list[Interval], duration: float, pad: float = 0.10
) -> list[Interval]:
    """Berechnet die zu behaltenden Abschnitte innerhalb [0, duration].

    `silences` sind clip-relative Stille-Intervalle. Jede Stille wird um `pad`
    Sekunden auf beiden Seiten verkleinert, damit Wort-Anfänge/-Enden nicht
    abgeschnitten werden. Überlappende Schnitte werden zusammengeführt.
    """
    duration = max(0.0, duration)
    cuts: list[Interval] = []
    for s, e in silences:
        s2 = max(0.0, s + pad)
        e2 = min(duration, e - pad)
        if e2 - s2 > 0.05:  # nur sinnvoll lange Stille schneiden
            cuts.append((s2, e2))

    cuts.sort()
    merged: list[Interval] = []
    for s, e in cuts:
        if merged and s <= merged[-1][1]:
            merged[-1] = (merged[-1][0], max(merged[-1][1], e))
        else:
            merged.append((s, e))

    keeps: list[Interval] = []
    cur = 0.0
    for s, e in merged:
        if s > cur:
            keeps.append((cur, s))
        cur = max(cur, e)
    if cur < duration:
        keeps.append((cur, duration))

    # Falls nichts geschnitten wurde, ist das ganze Intervall ein Keep.
    if not keeps and duration > 0:
        keeps.append((0.0, duration))
    return keeps


def kept_seconds(keeps: list[Interval]) -> float:
    return sum(max(0.0, b - a) for a, b in keeps)


def removed_seconds(keeps: list[Interval], duration: float) -> float:
    return max(0.0, duration - kept_seconds(keeps))


def remap_time(t: float, keeps: list[Interval]) -> float:
    """Bildet eine clip-relative Originalzeit auf die gestauchte Zeit ab.

    Zeiten innerhalb entfernter Bereiche werden auf die nächste Keep-Grenze
    gemappt (Wörter liegen per Definition nicht in der Stille).
    """
    acc = 0.0
    for a, b in keeps:
        if t < a:
            return acc
        if t <= b:
            return acc + (t - a)
        acc += b - a
    return acc


def remap_words(words: list[Word], clip_start: float, keeps: list[Interval]) -> list[Word]:
    """Erzeugt clip-relative (0-basierte) Wörter auf der gestauchten Zeitachse."""
    out: list[Word] = []
    for w in words:
        rs = w.start - clip_start
        re = w.end - clip_start
        ns = remap_time(rs, keeps)
        ne = remap_time(re, keeps)
        if ne < ns:
            ne = ns
        out.append(Word(text=w.text, start=ns, end=ne))
    return out


def select_expr(keeps: list[Interval]) -> str:
    """FFmpeg-Ausdruck für select/aselect: behalte nur die Keep-Intervalle."""
    parts = [f"between(t,{a:.3f},{b:.3f})" for a, b in keeps]
    return "+".join(parts) if parts else "1"


def audio_smoothing_filter(keeps: list[Interval], fade: float = 0.015) -> str:
    """Baut die Audio-Seite eines filter_complex mit kurzen Fades je Segment.

    Jedes Keep-Intervall wird einzeln aus `[0:a]` getrimmt, auf 0 zurückgesetzt
    und mit einem sehr kurzen Fade-in/-out (Default 15 ms) an seinen Rändern
    versehen; danach werden alle Segmente per `concat` aneinandergehängt → `[a]`.

    Wichtig: Die Fades liegen INNERHALB der behaltenen Samples — die
    Gesamtdauer (Summe der Keep-Längen) bleibt identisch zum Video-`select`,
    daher kein A/V- oder Caption-Versatz. Die kurzen Pegel-Dips an den Nähten
    entschärfen hörbare Klick-Geräusche an harten Schnitten.
    """
    parts: list[str] = []
    labels: list[str] = []
    n = len(keeps)
    for i, (a, b) in enumerate(keeps):
        length = max(0.0, b - a)
        d = min(fade, length / 4.0)
        out_lbl = "[a]" if n == 1 else f"[as{i}]"
        chain = f"[0:a]atrim={a:.3f}:{b:.3f},asetpts=PTS-STARTPTS"
        if d > 0.002:
            chain += (
                f",afade=t=in:st=0:d={d:.3f}"
                f",afade=t=out:st={max(0.0, length - d):.3f}:d={d:.3f}"
            )
        chain += out_lbl
        parts.append(chain)
        labels.append(out_lbl)
    if n == 1:
        return parts[0]
    concat = "".join(labels) + f"concat=n={n}:v=0:a=1[a]"
    return ";".join(parts + [concat])
