"""Stream-/VOD-Analyse: Signale → Score → Kandidaten → Clip-Grenzen.

Ablauf (auch für mehrstündige Aufnahmen tragbar):
1. Audio- und Video-Signale über die ganze Aufnahme (FFmpeg-Pipes, günstig).
2. Optional Chat (vom Nutzer importiert).
3. Erstes Scoring ohne Transkript → vorläufige Kandidaten.
4. Transkription NUR der Kandidaten-Fenster (±40 s) statt der ganzen Aufnahme.
5. Zweites Scoring mit Transkript-Signalen, Satzgrenzen, Duplikat-Filter.
"""

from __future__ import annotations

import os
import subprocess
import tempfile

from ..ffmpeg_utils import probe
from ..models import Word
from . import scoring, signals
from .chat import ChatMessage, per_second


def _transcribe_window(path: str, start: float, end: float, transcriber, settings) -> list[Word]:
    with tempfile.TemporaryDirectory() as tmp:
        wav = os.path.join(tmp, "w.wav")
        subprocess.run(["ffmpeg", "-y", "-v", "error", "-ss", f"{start:.2f}", "-to", f"{end:.2f}",
                        "-i", path, "-vn", "-ac", "1", "-ar", "16000", wav],
                       check=True, timeout=600)
        tr = transcriber(wav, settings)
    return [Word(w.text, w.start + start, w.end + start) for w in tr.words]


def analyze(path: str, *, chat: list[ChatMessage] | None = None, transcriber=None, settings=None,
            keywords: list[str] | None = None, chat_delay: float | None = None,
            max_clips: int = 8, pre: float = 10.0, post: float = 8.0, max_len: float = 60.0,
            progress=None, should_cancel=None) -> dict:
    log = progress or (lambda _m: None)
    info = probe(path)
    duration = float(info.duration or 0)
    if duration <= 0:
        raise ValueError("Video-Dauer nicht lesbar.")
    log("Audio-Signale werden gemessen …")
    audio = signals.audio_features(path, should_cancel) if info.has_audio else None
    log("Video-Signale werden gemessen …")
    video = signals.video_features(path, should_cancel)
    chat_ps = per_second(chat, duration) if chat else None

    log("Erstes Scoring (Chat/Audio/Video) …")
    tl = scoring.score_timeline(duration, chat=chat_ps, audio=audio, video=video,
                                keywords=keywords, chat_delay=chat_delay)
    first = scoring.pick_candidates(tl, chat=chat_ps, max_count=max_clips * 2)

    words: list[Word] = []
    transcribed: list[list[float]] = []
    if transcriber is not None and first:
        windows = []
        for c in first:
            a, b = max(0.0, c.t - 40), min(duration, c.t + 40)
            if windows and a <= windows[-1][1]:
                windows[-1][1] = max(windows[-1][1], b)
            else:
                windows.append([a, b])
        windows.sort()
        for i, (a, b) in enumerate(windows):
            if should_cancel and should_cancel():
                raise signals.SignalError("abgebrochen")
            log(f"Transkription Fenster {i + 1}/{len(windows)} ({a:.0f}–{b:.0f} s) …")
            try:
                words.extend(_transcribe_window(path, a, b, transcriber, settings))
                transcribed.append([round(a, 1), round(b, 1)])
            except Exception as exc:  # noqa: BLE001 — Transkript ist optional
                log(f"  Transkription übersprungen ({type(exc).__name__})")
        words.sort(key=lambda w: w.start)
        if words:
            log("Zweites Scoring mit Transkript …")
            tl = scoring.score_timeline(duration, chat=chat_ps, audio=audio, video=video,
                                        words=words, keywords=keywords, chat_delay=tl["chat_delay"])
    cands = scoring.pick_candidates(tl, chat=chat_ps, max_count=max_clips * 2)
    clips = []
    for c in cands:
        start, end, note = scoring.clip_bounds(c.t, duration, words, pre=pre, post=post, max_len=max_len)
        text = " ".join(w.text for w in words if start <= w.start <= end).strip()
        clips.append({"t": c.t, "start": start, "end": end, "score": c.score,
                      "components": c.components, "reasons": c.reasons + [f"Schnitt: {note}"],
                      "chat_categories": c.chat_categories, "top_terms": c.top_terms,
                      "text": text[:600]})
    clips = scoring.dedupe(clips)[:max_clips]
    for i, c in enumerate(clips):
        c["id"] = f"h{i + 1:02d}"
    step = max(1, tl["n"] // 600)  # Heatmap höchstens ~600 Punkte
    return {
        "duration": round(duration, 2), "signals": tl["signals"], "weights":
            {k: round(v, 3) for k, v in tl["weights"].items()},
        "chat_delay": tl["chat_delay"], "chat_delay_note": tl["chat_delay_note"],
        "chat_messages": len(chat or []), "transcribed_windows": transcribed,
        "heatmap": {"step": step, "score": [round(float(x), 1) for x in tl["score"][::step]]},
        "highlights": clips,
        "disclaimer": "Rangfolge aus messbaren Signalen — keine Viralitäts-Vorhersage.",
        "_words": [{"text": w.text, "start": w.start, "end": w.end} for w in words],
    }
