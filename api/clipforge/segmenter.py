"""Erzeugt Kandidaten-Clips aus einem Transkript.

Strategie (MVP, deterministisch & erklärbar):
  - Wir gehen die Transkript-Segmente der Reihe nach durch.
  - Wir hängen Segmente an den aktuellen Clip an, bis die Ziel-Länge erreicht
    ist ODER eine größere Sprechpause auftritt.
  - Clips, die kürzer als min_clip_seconds sind, werden verworfen.
  - Clips, die länger als max_clip_seconds sind, werden an Segmentgrenzen
    geschnitten.

Das ist bewusst keine ML-Magie, sondern eine nachvollziehbare Heuristik.
Die eigentliche Qualitäts-Bewertung passiert danach im Scoring.
"""

from __future__ import annotations

from .config import Settings
from .models import CandidateClip, Transcript, TranscriptSegment, Word


def _flush(
    buffer: list[TranscriptSegment], settings: Settings
) -> CandidateClip | None:
    if not buffer:
        return None
    start = buffer[0].start
    end = buffer[-1].end
    if end - start < settings.min_clip_seconds:
        return None
    words: list[Word] = []
    for seg in buffer:
        words.extend(seg.words)
    text = " ".join(seg.text.strip() for seg in buffer).strip()
    return CandidateClip(start=start, end=end, text=text, words=words)


def build_candidates(
    transcript: Transcript, settings: Settings
) -> list[CandidateClip]:
    """Gruppiert Transkript-Segmente zu Kandidaten-Clips."""
    candidates: list[CandidateClip] = []
    buffer: list[TranscriptSegment] = []
    prev_end: float | None = None

    for seg in transcript.segments:
        gap = (seg.start - prev_end) if prev_end is not None else 0.0
        cur_len = (seg.end - buffer[0].start) if buffer else 0.0

        # Trennen, wenn die Ziel-Länge erreicht ist und eine Pause vorliegt,
        # oder wenn die Maximal-Länge überschritten würde.
        if buffer and (
            (cur_len >= settings.target_clip_seconds and gap >= settings.segment_gap_seconds)
            or (cur_len >= settings.max_clip_seconds)
        ):
            clip = _flush(buffer, settings)
            if clip:
                candidates.append(clip)
            buffer = []

        buffer.append(seg)
        prev_end = seg.end

        # Harte Obergrenze: falls ein einzelner Block schon zu lang ist.
        if buffer and (buffer[-1].end - buffer[0].start) >= settings.max_clip_seconds:
            clip = _flush(buffer, settings)
            if clip:
                candidates.append(clip)
            buffer = []
            prev_end = None

    clip = _flush(buffer, settings)
    if clip:
        candidates.append(clip)

    return candidates
