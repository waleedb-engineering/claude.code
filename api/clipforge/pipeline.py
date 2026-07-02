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

from .analyzer import analyze_clips
from .config import Settings, get_settings
from .content import generate_content_package
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
CancelFn = Callable[[], bool]


class PipelineCanceled(Exception):
    """Wird geworfen, wenn `should_cancel()` an einem Checkpoint True liefert.

    Kooperativer Abbruch: ein bereits laufender FFmpeg-Schritt läuft zu Ende,
    danach greift der nächste Checkpoint. Kein harter Prozess-Kill.
    """


def _checkpoint(should_cancel: CancelFn | None, progress: ProgressFn) -> None:
    if should_cancel is not None and should_cancel():
        progress("Abbruch erkannt — Pipeline stoppt am Checkpoint.")
        raise PipelineCanceled()


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
    audio_smoothing: bool = True,
    caption_mode: str = "karaoke",
    caption_style: str = "high_energy",
    reframe_mode: str = "smart",
    brand_overrides: dict | None = None,
    advanced_analysis: bool = True,
    progress: ProgressFn = _noop,
    should_cancel: CancelFn | None = None,
) -> PipelineResult:
    settings = settings or get_settings()
    os.makedirs(output_dir, exist_ok=True)

    # Checkpoint: vor Transkription
    _checkpoint(should_cancel, progress)

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

    # Checkpoint: nach Transkription
    _checkpoint(should_cancel, progress)

    # 2+3) Kandidaten-Erkennung + Scoring
    if advanced_analysis:
        top, analysis_meta = analyze_clips(transcript, settings, max(0, top_n))
        scorer = analysis_meta["analyzer_mode"]
        progress(
            f"Analyzer {analysis_meta['analyzer_version']} "
            f"({analysis_meta['analyzer_mode']}): "
            f"{analysis_meta['candidate_count']} Kandidaten → "
            f"{analysis_meta['deduplicated_count']} nach Dedup → "
            f"{len(top)} ausgewählt"
        )
    else:
        candidates = build_candidates(transcript, settings)
        progress(f"{len(candidates)} Kandidaten-Clips gebildet")
        scorer = "Claude" if settings.llm_available else "Heuristik"
        progress(f"Bewerte Clips ({scorer}) …")
        scored = score_clips(candidates, settings)
        top = scored[: max(0, top_n)]
        analysis_meta = {
            "analyzer_version": "v1",
            "analyzer_mode": scorer,
            "candidate_count": len(candidates),
            "deduplicated_count": len(candidates),
        }

    # Checkpoint: vor Content-Paketen
    _checkpoint(should_cancel, progress)

    # 3b) Content-Pakete (Text-only, unabhängig vom Rendering)
    content_mode = "Claude" if settings.llm_available else "Regelbasiert"
    progress(f"Erzeuge Content-Pakete ({content_mode}) …")
    content_llm_used = 0
    for clip in top:
        package, used_llm = generate_content_package(clip, settings, language=transcript.language)
        clip.content_package = package
        if used_llm:
            content_llm_used += 1
    content_fallback_count = (
        (len(top) - content_llm_used) if settings.llm_available else 0
    )

    # 4) Rendering
    rendered: list[str] = []
    if render and top:
        progress(
            f"Silence-Removal: {'aktiviert' if remove_silence else 'deaktiviert'}"
        )
        progress(f"Caption-Modus: {caption_mode}, Style: {caption_style}")
        progress(f"Reframe-Modus: {reframe_mode}")
        for i, clip in enumerate(top, start=1):
            # Checkpoint: vor jedem Clip-Render
            _checkpoint(should_cancel, progress)
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
                    audio_smoothing=audio_smoothing,
                    caption_mode=caption_mode,
                    caption_style=caption_style,
                    reframe_mode=reframe_mode,
                    brand_overrides=brand_overrides,
                    progress=progress,
                )
                rendered.append(out_path)
            except Exception as exc:  # noqa: BLE001
                progress(f"  ⚠ Rendering fehlgeschlagen: {exc}")
            # Checkpoint: nach jedem Clip-Render (fertige MP4s bleiben erhalten)
            _checkpoint(should_cancel, progress)

    # 5) clips.json
    total_removed = round(
        sum((c.silence_info or {}).get("removed_seconds", 0.0) for c in top), 2
    )
    any_smoothing = any((c.silence_info or {}).get("audio_smoothing") for c in top)
    caption_fallback_count = sum(
        1 for c in top if (c.caption_info or {}).get("fallback")
    )
    reframe_fallback_count = sum(
        1 for c in top if (c.reframe_info or {}).get("fallback")
    )
    clips_json = {
        "source": os.path.abspath(video_path),
        "scorer": scorer,
        "analyzer_version": analysis_meta.get("analyzer_version"),
        "analyzer_mode": analysis_meta.get("analyzer_mode"),
        "candidate_count": analysis_meta.get("candidate_count"),
        "deduplicated_count": analysis_meta.get("deduplicated_count"),
        "filled_up": analysis_meta.get("filled_up"),
        "llm_latency_ms": analysis_meta.get("llm_latency_ms"),
        "remove_silence": remove_silence,
        "audio_smoothing": any_smoothing,
        "total_removed_silence_seconds": total_removed,
        "caption_mode": caption_mode,
        "caption_style": caption_style,
        "caption_fallback_count": caption_fallback_count,
        "reframe_mode": reframe_mode,
        "reframe_fallback_count": reframe_fallback_count,
        "content_generator": content_mode,
        "content_fallback_count": content_fallback_count,
        "brand_kit_used": bool((brand_overrides or {}).get("brand_kit_used")),
        "brand_kit_name": (brand_overrides or {}).get("brand_kit_name"),
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
