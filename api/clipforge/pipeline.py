"""Orchestriert die komplette Pipeline: Video → fertige Clips.

Schritte:
  1) Transkribieren (oder vorhandenes Transkript laden)
  2) Kandidaten-Clips bilden
  3) Bewerten (Heuristik / Claude) + sortieren
  4) Top-N rendern (9:16 + Untertitel)
  5) clips.json mit allen Metadaten schreiben
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass, field
from typing import Callable

from .config import Settings, get_settings
from .models import ScoredClip, Transcript
from .render import render_clip
from .scoring import score_clips
from .segmenter import build_candidates
from .transcribe import (
    load_transcript_json,
    transcribe_video,
    transcript_to_json,
)

ProgressFn = Callable[[str], None]


@dataclass
class PipelineResult:
    transcript: Transcript
    clips: list[ScoredClip]
    output_dir: str
    rendered: list[str] = field(default_factory=list)


def _noop(_msg: str) -> None:
    pass


def run_pipeline(
    video_path: str,
    output_dir: str,
    *,
    settings: Settings | None = None,
    transcript_path: str | None = None,
    top_n: int = 5,
    render: bool = True,
    remove_silence: bool = False,
    progress: ProgressFn = _noop,
) -> PipelineResult:
    settings = settings or get_settings()
    os.makedirs(output_dir, exist_ok=True)

    # 1) Transkript
    if transcript_path:
        progress(f"Lade Transkript aus {transcript_path} …")
        transcript = load_transcript_json(transcript_path)
    else:
        progress("Transkribiere Video (faster-whisper) …")
        transcript = transcribe_video(video_path, settings)

    # Transkript immer mitschreiben (Debug/Reuse)
    with open(os.path.join(output_dir, "transcript.json"), "w", encoding="utf-8") as fh:
        json.dump(transcript_to_json(transcript), fh, ensure_ascii=False, indent=2)
    progress(
        f"Transkript: {len(transcript.segments)} Segmente, "
        f"{transcript.duration:.1f}s, Sprache={transcript.language}"
    )

    # 2) Kandidaten
    candidates = build_candidates(transcript, settings)
    progress(f"{len(candidates)} Kandidaten-Clips gebildet")

    # 3) Scoring
    scorer = "Claude" if settings.llm_available else "Heuristik"
    progress(f"Bewerte Clips ({scorer}) …")
    scored = score_clips(candidates, settings)

    # Top-N auswählen
    top = scored[: max(0, top_n)]

    # 4) Rendering
    rendered: list[str] = []
    if render and top:
        progress(
            f"Silence-Removal: {'aktiviert' if remove_silence else 'deaktiviert'}"
        )
        for i, clip in enumerate(top, start=1):
            out_path = os.path.join(output_dir, f"clip_{i:02d}_score{int(clip.score)}.mp4")
            progress(
                f"Rendere Clip {i}/{len(top)} "
                f"({clip.start:.1f}-{clip.end:.1f}s, Score {clip.score}) …"
            )
            try:
                render_clip(
                    video_path,
                    clip,
                    out_path,
                    settings,
                    remove_silence=remove_silence,
                    progress=progress,
                )
                rendered.append(out_path)
            except Exception as exc:  # noqa: BLE001
                progress(f"  ⚠ Rendering fehlgeschlagen: {exc}")

    # 5) clips.json
    clips_json = {
        "source": os.path.abspath(video_path),
        "scorer": scorer,
        "remove_silence": remove_silence,
        "disclaimer": (
            "Der Performance-Potential-Score ist eine Wahrscheinlichkeits-"
            "Einschätzung auf Basis messbarer Signale und KEINE Garantie für "
            "Reichweite oder Viralität."
        ),
        "clips": [c.to_dict() for c in top],
    }
    with open(os.path.join(output_dir, "clips.json"), "w", encoding="utf-8") as fh:
        json.dump(clips_json, fh, ensure_ascii=False, indent=2)
    progress(f"clips.json geschrieben ({len(top)} Clips)")

    return PipelineResult(
        transcript=transcript,
        clips=top,
        output_dir=output_dir,
        rendered=rendered,
    )
