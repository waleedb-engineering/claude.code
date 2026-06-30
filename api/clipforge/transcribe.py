"""Transkription mit lokalem faster-whisper (Wort-Level-Timestamps).

Zusätzlich kann ein bereits vorhandenes Transkript (JSON) geladen werden —
das macht die Pipeline ohne Modell-Download / ohne Audio testbar.
"""

from __future__ import annotations

import json
import os
import tempfile

from .config import Settings
from .ffmpeg_utils import extract_audio, probe
from .models import Transcript, TranscriptSegment, Word


def transcribe_video(video_path: str, settings: Settings) -> Transcript:
    """Transkribiert ein Video lokal mit faster-whisper.

    Erfordert das Paket `faster-whisper`. Beim ersten Lauf wird das Modell
    heruntergeladen (z.B. ~140 MB für 'base').
    """
    try:
        from faster_whisper import WhisperModel
    except ImportError as exc:  # pragma: no cover - abhängig von Umgebung
        raise RuntimeError(
            "faster-whisper ist nicht installiert. Bitte "
            "`pip install faster-whisper` ausführen oder ein Transkript via "
            "--transcript übergeben."
        ) from exc

    with tempfile.TemporaryDirectory() as tmp:
        wav_path = os.path.join(tmp, "audio.wav")
        extract_audio(video_path, wav_path)

        model = WhisperModel(
            settings.whisper_model,
            device=settings.whisper_device,
            compute_type=settings.whisper_compute_type,
        )
        seg_iter, info = model.transcribe(wav_path, word_timestamps=True)

        segments: list[TranscriptSegment] = []
        for seg in seg_iter:
            words: list[Word] = []
            for w in seg.words or []:
                words.append(
                    Word(text=w.word.strip(), start=float(w.start), end=float(w.end))
                )
            segments.append(
                TranscriptSegment(
                    text=seg.text.strip(),
                    start=float(seg.start),
                    end=float(seg.end),
                    words=words,
                )
            )

    media = probe(video_path)
    return Transcript(
        language=getattr(info, "language", "unknown"),
        duration=media.duration or (segments[-1].end if segments else 0.0),
        segments=segments,
    )


def load_transcript_json(path: str) -> Transcript:
    """Lädt ein Transkript aus JSON.

    Erwartetes Format (kompatibel zum dump von transcript_to_json):
        {
          "language": "de",
          "duration": 120.0,
          "segments": [
            {"text": "...", "start": 0.0, "end": 3.2,
             "words": [{"text": "Hallo", "start": 0.0, "end": 0.4}, ...]}
          ]
        }
    """
    with open(path, "r", encoding="utf-8") as fh:
        data = json.load(fh)

    segments: list[TranscriptSegment] = []
    for seg in data.get("segments", []):
        words = [
            Word(text=w["text"], start=float(w["start"]), end=float(w["end"]))
            for w in seg.get("words", [])
        ]
        segments.append(
            TranscriptSegment(
                text=seg.get("text", "").strip(),
                start=float(seg.get("start", words[0].start if words else 0.0)),
                end=float(seg.get("end", words[-1].end if words else 0.0)),
                words=words,
            )
        )
    duration = float(data.get("duration") or (segments[-1].end if segments else 0.0))
    return Transcript(
        language=data.get("language", "unknown"),
        duration=duration,
        segments=segments,
    )


def transcript_to_json(transcript: Transcript) -> dict:
    """Serialisiert ein Transkript nach JSON-fähigem dict."""
    return {
        "language": transcript.language,
        "duration": transcript.duration,
        "segments": [
            {
                "text": seg.text,
                "start": seg.start,
                "end": seg.end,
                "words": [
                    {"text": w.text, "start": w.start, "end": w.end}
                    for w in seg.words
                ],
            }
            for seg in transcript.segments
        ],
    }
