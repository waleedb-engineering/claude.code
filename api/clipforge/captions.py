"""Erzeugt eingebrannte Untertitel im ASS-Format aus Wort-Timestamps.

Gruppiert Wörter zu kurzen, gut lesbaren Caption-Zeilen (max. ~3-4 Wörter),
zeitlich relativ zum Clip-Start. Stil: großer, fetter, zentrierter Text mit
Outline — typischer Short-Form-Look.
"""

from __future__ import annotations

from .models import Word


def _fmt_ts(seconds: float) -> str:
    """ASS-Zeitformat H:MM:SS.cs (Zentisekunden)."""
    seconds = max(0.0, seconds)
    h = int(seconds // 3600)
    m = int((seconds % 3600) // 60)
    s = int(seconds % 60)
    cs = int(round((seconds - int(seconds)) * 100))
    if cs == 100:
        cs = 0
        s += 1
    return f"{h}:{m:02d}:{s:02d}.{cs:02d}"


def _escape(text: str) -> str:
    return text.replace("\\", "\\\\").replace("{", "(").replace("}", ")")


def group_words(
    words: list[Word], clip_start: float, max_words: int = 3, max_gap: float = 0.8
) -> list[tuple[float, float, str]]:
    """Gruppiert Wörter zu Caption-Zeilen, Zeiten relativ zu clip_start."""
    lines: list[tuple[float, float, str]] = []
    bucket: list[Word] = []

    def flush() -> None:
        if not bucket:
            return
        start = bucket[0].start - clip_start
        end = bucket[-1].end - clip_start
        text = " ".join(w.text for w in bucket).strip()
        if text:
            lines.append((max(0.0, start), max(0.0, end), text))

    prev_end: float | None = None
    for w in words:
        gap = (w.start - prev_end) if prev_end is not None else 0.0
        if bucket and (len(bucket) >= max_words or gap >= max_gap):
            flush()
            bucket = []
        bucket.append(w)
        prev_end = w.end
    flush()
    return lines


def build_ass(
    words: list[Word],
    clip_start: float,
    clip_end: float,
    width: int = 1080,
    height: int = 1920,
    font_size: int = 96,
) -> str:
    """Baut ein komplettes ASS-Subtitle-Dokument für einen Clip."""
    duration = max(0.0, clip_end - clip_start)
    lines = group_words(words, clip_start)
    if not lines:
        lines = []  # Kein Text → leeres, aber valides ASS

    header = f"""[Script Info]
ScriptType: v4.00+
PlayResX: {width}
PlayResY: {height}
WrapStyle: 2
ScaledBorderAndShadow: yes

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, OutlineColour, BackColour, Bold, Italic, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Caption,Arial,{font_size},&H00FFFFFF,&H00000000,&H64000000,1,0,1,6,2,2,80,80,260,1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
"""

    events: list[str] = []
    for start, end, text in lines:
        # Clip-Grenzen respektieren
        start = min(max(0.0, start), duration)
        end = min(max(start, end), duration)
        events.append(
            f"Dialogue: 0,{_fmt_ts(start)},{_fmt_ts(end)},Caption,,0,0,0,,{_escape(text)}"
        )
    return header + "\n".join(events) + ("\n" if events else "")
