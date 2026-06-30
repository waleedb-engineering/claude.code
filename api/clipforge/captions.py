"""Erzeugt eingebrannte Untertitel im ASS-Format aus Wort-Timestamps.

Gruppiert Wörter zu kurzen, gut lesbaren Caption-Zeilen (max. ~3-4 Wörter),
zeitlich relativ zum Clip-Start. Stil: großer, fetter, zentrierter Text mit
Outline — typischer Short-Form-Look.
"""

from __future__ import annotations

from dataclasses import dataclass

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


# ==========================================================================
# Caption-Styles (erweiterbar) + Modi (standard / karaoke)
# ==========================================================================


@dataclass(frozen=True)
class CaptionStyle:
    """Visueller Stil für eingebrannte Untertitel.

    Farben für die Style-Zeile sind im 8-stelligen ASS-Format &HAABBGGRR,
    die Inline-Highlight-Farbe im 6-stelligen Override-Format &Hbbggrr&.
    """

    name: str
    fontsize: int
    outline: int
    shadow: int
    bold: int               # 1/0
    primary: str            # &HAABBGGRR (Style-Zeile)
    outline_color: str      # &HAABBGGRR
    highlight: str          # &Hbbggrr& (Inline-Override für aktuelles Wort)
    highlight_scale: int    # Prozent; 100 = keine Größenänderung
    uppercase: bool
    marginv: int            # Abstand von unten (Safe Area)


STYLES: dict[str, CaptionStyle] = {
    # Schlicht, professionell: weiß + schwarze Outline, gelbes aktuelles Wort,
    # keine Größenänderung (kein horizontales Springen).
    "clean": CaptionStyle(
        name="clean",
        fontsize=84,
        outline=4,
        shadow=1,
        bold=1,
        primary="&H00FFFFFF",
        outline_color="&H00000000",
        highlight="&H00FFFF&",      # gelb
        highlight_scale=100,
        uppercase=False,
        marginv=340,
    ),
    # Energiegeladen: größer, GROSSBUCHSTABEN, grünes aktuelles Wort,
    # leichtes „Pop" durch Skalierung.
    "high_energy": CaptionStyle(
        name="high_energy",
        fontsize=104,
        outline=6,
        shadow=2,
        bold=1,
        primary="&H00FFFFFF",
        outline_color="&H00000000",
        highlight="&H00FF00&",      # grün
        highlight_scale=118,
        uppercase=True,
        marginv=340,
    ),
}

DEFAULT_STYLE = "clean"
DEFAULT_MODE = "karaoke"


def _ass_header(style: CaptionStyle, width: int, height: int) -> str:
    # WrapStyle 0 = automatischer Zeilenumbruch innerhalb der Ränder
    # (verhindert Überlaufen bei großer Schrift / langen Wörtern).
    return f"""[Script Info]
ScriptType: v4.00+
PlayResX: {width}
PlayResY: {height}
WrapStyle: 0
ScaledBorderAndShadow: yes

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, OutlineColour, BackColour, Bold, Italic, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Caption,Arial,{style.fontsize},{style.primary},{style.outline_color},&H64000000,{style.bold},0,1,{style.outline},{style.shadow},2,120,120,{style.marginv},1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
"""


def chunk_words(
    words: list[Word], max_words: int = 3, max_gap: float = 0.7
) -> list[list[Word]]:
    """Gruppiert Wörter in kurze Blöcke (Default max. 3), an Pausen getrennt."""
    chunks: list[list[Word]] = []
    bucket: list[Word] = []
    prev_end: float | None = None
    for w in words:
        gap = (w.start - prev_end) if prev_end is not None else 0.0
        if bucket and (len(bucket) >= max_words or gap >= max_gap):
            chunks.append(bucket)
            bucket = []
        bucket.append(w)
        prev_end = w.end
    if bucket:
        chunks.append(bucket)
    return chunks


def has_word_timestamps(words: list[Word]) -> bool:
    """True, wenn nutzbare Wort-Timestamps vorhanden sind (für Karaoke)."""
    return bool(words) and any(w.end > w.start for w in words)


def _word_text(w: Word, style: CaptionStyle) -> str:
    t = _escape(w.text)
    return t.upper() if style.uppercase else t


def build_ass_standard(
    words: list[Word],
    clip_start: float,
    clip_end: float,
    width: int,
    height: int,
    style: CaptionStyle,
) -> tuple[str, int]:
    """Standard-Captions: ein Event pro Wortblock (kein Per-Wort-Highlight)."""
    duration = max(0.0, clip_end - clip_start)
    chunks = chunk_words(words)
    events: list[str] = []
    for ch in chunks:
        start = min(max(0.0, ch[0].start - clip_start), duration)
        end = min(max(start, ch[-1].end - clip_start), duration)
        if end <= start:
            continue
        text = " ".join(_word_text(w, style) for w in ch)
        events.append(
            f"Dialogue: 0,{_fmt_ts(start)},{_fmt_ts(end)},Caption,,0,0,0,,{text}"
        )
    ass = _ass_header(style, width, height) + "\n".join(events) + ("\n" if events else "")
    return ass, len(chunks)


def build_ass_karaoke(
    words: list[Word],
    clip_start: float,
    clip_end: float,
    width: int,
    height: int,
    style: CaptionStyle,
) -> tuple[str, int]:
    """Karaoke-Captions: pro Wort ein Event, das den ganzen Block zeigt und
    genau das aktuelle Wort hervorhebt (Farbe + optionale Skalierung)."""
    duration = max(0.0, clip_end - clip_start)
    chunks = chunk_words(words)
    scale_tag = (
        f"\\fscx{style.highlight_scale}\\fscy{style.highlight_scale}"
        if style.highlight_scale != 100
        else ""
    )
    events: list[str] = []
    for ch in chunks:
        n = len(ch)
        for j, w in enumerate(ch):
            ev_start = max(0.0, w.start - clip_start)
            # Block bleibt durchgehend sichtbar: bis zum nächsten Wort,
            # beim letzten Wort bis dessen Ende.
            if j < n - 1:
                ev_end = max(0.0, ch[j + 1].start - clip_start)
            else:
                ev_end = max(0.0, w.end - clip_start)
            ev_start = min(ev_start, duration)
            ev_end = min(max(ev_start, ev_end), duration)
            if ev_end <= ev_start:
                continue
            parts: list[str] = []
            for i, ww in enumerate(ch):
                t = _word_text(ww, style)
                if i == j:
                    parts.append(f"{{\\1c{style.highlight}{scale_tag}}}{t}{{\\r}}")
                else:
                    parts.append(t)
            line = " ".join(parts)
            events.append(
                f"Dialogue: 0,{_fmt_ts(ev_start)},{_fmt_ts(ev_end)},Caption,,0,0,0,,{line}"
            )
    ass = _ass_header(style, width, height) + "\n".join(events) + ("\n" if events else "")
    return ass, len(chunks)


def make_captions(
    words: list[Word],
    clip_start: float,
    clip_end: float,
    *,
    mode: str,
    style: str,
    width: int = 1080,
    height: int = 1920,
) -> tuple[str, dict]:
    """Zentraler Entscheidungspunkt: baut das ASS und liefert caption_info.

    Robuste Fallbacks:
      - Karaoke ohne Wort-Timestamps  → Standard (fallback, Grund geloggt).
      - unbekannter Style             → DEFAULT_STYLE.
      - unbekannter Modus             → Karaoke.
    """
    requested_mode = mode if mode in ("standard", "karaoke") else DEFAULT_MODE

    style_known = style in STYLES
    style_obj = STYLES.get(style, STYLES[DEFAULT_STYLE])
    resolved_style = style_obj.name

    word_level = has_word_timestamps(words)
    applied_mode = requested_mode
    fallback = False
    reasons: list[str] = []

    if requested_mode == "karaoke" and not word_level:
        applied_mode = "standard"
        fallback = True
        reasons.append("keine Wort-Timestamps verfügbar")
    if not style_known:
        fallback = True
        reasons.append(f"unbekannter Style → {resolved_style}")

    if applied_mode == "karaoke":
        ass, blocks = build_ass_karaoke(
            words, clip_start, clip_end, width, height, style_obj
        )
    else:
        ass, blocks = build_ass_standard(
            words, clip_start, clip_end, width, height, style_obj
        )

    info = {
        "requested_mode": requested_mode,
        "applied_mode": applied_mode,
        "caption_style": resolved_style,
        "word_level_available": word_level,
        "fallback": fallback,
        "fallback_reason": "; ".join(reasons) if reasons else None,
        "caption_blocks_count": blocks,
    }
    return ass, info
