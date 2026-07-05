"""ClipForge CLI — Pipeline-Kern ohne Web-UI.

Beispiele:
  # Mit lokaler Transkription (faster-whisper lädt beim 1. Lauf das Modell):
  python -m clipforge.cli input.mp4 --out ./out --top 5

  # Ohne Whisper/Modell-Download, mit vorhandenem Transkript (JSON):
  python -m clipforge.cli input.mp4 --transcript t.json --out ./out

  # Nur analysieren/scoren, NICHT rendern:
  python -m clipforge.cli input.mp4 --transcript t.json --no-render
"""

from __future__ import annotations

import argparse
import sys

from . import __version__
from .config import get_settings
from .ffmpeg_utils import FFmpegNotFound, ensure_ffmpeg
from .pipeline import run_pipeline


def _progress(msg: str) -> None:
    print(f"[clipforge] {msg}", flush=True)


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="clipforge",
        description="Erzeuge aus langen Videos automatisch Kurzclips (9:16) "
        "mit Untertiteln, Performance-Potential-Score und Plattform-Metadaten.",
    )
    p.add_argument(
        "--version",
        action="version",
        version=f"clipforge {__version__}",
    )
    p.add_argument("video", help="Pfad zum Quellvideo")
    p.add_argument("--out", default="./clipforge_out", help="Ausgabe-Verzeichnis")
    p.add_argument(
        "--transcript",
        default=None,
        help="Optional: vorhandenes Transkript (JSON) statt Whisper nutzen",
    )
    p.add_argument("--top", type=int, default=5, help="Anzahl der Top-Clips")
    p.add_argument(
        "--no-render",
        action="store_true",
        help="Nur analysieren/scoren, keine MP4s rendern",
    )
    p.add_argument(
        "--remove-silence",
        action="store_true",
        help="Stille Pausen automatisch entfernen (schnellere, dichtere Clips). "
        "Ohne dieses Flag bleibt das normale Verhalten erhalten.",
    )
    p.add_argument(
        "--no-audio-smoothing",
        action="store_true",
        help="Audio-Glättung (kurze Fades an Schnitten) deaktivieren. "
        "Nur relevant zusammen mit --remove-silence.",
    )
    p.add_argument(
        "--caption-mode",
        choices=("standard", "karaoke"),
        default="karaoke",
        help="Untertitel-Modus. 'karaoke' hebt das aktuelle Wort hervor "
        "(Default; fällt ohne Wort-Timestamps auf 'standard' zurück).",
    )
    p.add_argument(
        "--caption-style",
        choices=("clean", "high_energy"),
        default="high_energy",
        help="Caption-Style: 'clean' (schlicht) oder 'high_energy' (Default).",
    )
    p.add_argument(
        "--reframe-mode",
        choices=("center", "smart", "face"),
        default="smart",
        help="9:16-Ausschnitt: 'center' (mittig), 'smart'/'face' (auf Gesicht "
        "ausrichten, Default; Fallback auf center ohne Erkennung).",
    )
    return p


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    settings = get_settings()

    try:
        ensure_ffmpeg()
    except FFmpegNotFound as exc:
        print(f"FEHLER: {exc}", file=sys.stderr)
        return 2

    try:
        result = run_pipeline(
            video_path=args.video,
            output_dir=args.out,
            settings=settings,
            transcript_path=args.transcript,
            top_n=args.top,
            render=not args.no_render,
            remove_silence=args.remove_silence,
            audio_smoothing=not args.no_audio_smoothing,
            caption_mode=args.caption_mode,
            caption_style=args.caption_style,
            reframe_mode=args.reframe_mode,
            progress=_progress,
        )
    except FileNotFoundError as exc:
        print(f"FEHLER: Datei nicht gefunden: {exc}", file=sys.stderr)
        return 2
    except Exception as exc:  # noqa: BLE001
        print(f"FEHLER in der Pipeline: {exc}", file=sys.stderr)
        return 1

    print()
    print("=" * 64)
    print(f"Fertig. {len(result.clips)} Clips in: {result.output_dir}")
    print("=" * 64)
    for i, clip in enumerate(result.clips, start=1):
        b = clip.breakdown
        print(
            f"\n#{i}  Score {clip.score}  "
            f"({clip.start:.1f}-{clip.end:.1f}s, {clip.duration:.1f}s)  "
            f"[{clip.scorer}]"
        )
        print(
            f"    Hook {b.hook} | Klarheit {b.clarity} | Emotion {b.emotion} "
            f"| Tempo {b.pacing} | Pointe {b.payoff}"
        )
        print(f"    {clip.reason}")
        if clip.output_path:
            print(f"    → {clip.output_path}")
        text = clip.text if len(clip.text) <= 120 else clip.text[:117] + "…"
        print(f"    “{text}”")
    print()
    print(
        "Hinweis: Der Score ist eine Wahrscheinlichkeits-Einschätzung, "
        "KEINE Garantie für Viralität."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
