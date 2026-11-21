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


def _cache_dir() -> str:
    path = os.environ.get("CLIPFORGE_TRANSCRIPT_CACHE")
    if not path:
        try:
            from .studio.storage import studio_dir
            path = os.path.join(studio_dir(), "cache", "transcripts")
        except Exception:  # noqa: BLE001
            path = os.path.join(tempfile.gettempdir(), "clipforge_transcripts")
    os.makedirs(path, exist_ok=True)
    return path


def _audio_hash(wav_path: str) -> str:
    import hashlib
    h = hashlib.sha256()
    with open(wav_path, "rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()[:24]


def _model_cached(name: str) -> bool:
    """Liegt das Modell lokal vor (eigener Ordner oder Hugging-Face-Cache)?"""
    if os.path.isdir(name):
        return os.path.isfile(os.path.join(name, "model.bin"))
    hub = os.environ.get("HF_HUB_CACHE") or os.path.join(
        os.environ.get("HF_HOME") or os.path.join(os.path.expanduser("~"), ".cache", "huggingface"), "hub")
    repo = name if "/" in name else f"Systran/faster-whisper-{name}"
    snap = os.path.join(hub, "models--" + repo.replace("/", "--"), "snapshots")
    return os.path.isdir(snap) and any(
        os.path.isfile(os.path.join(snap, d, "model.bin")) for d in os.listdir(snap))


def transcription_status(settings: Settings) -> dict:
    """Ehrlicher Status für die Oberfläche — lädt nichts herunter."""
    import platform
    out = {"package": False, "version": None, "model": settings.whisper_model,
           "model_available": _model_cached(settings.whisper_model), "device": settings.whisper_device,
           "compute_type": settings.whisper_compute_type,
           "language": os.environ.get("CLIPFORGE_WHISPER_LANGUAGE") or "auto",
           "sizes": {"tiny": "~75 MB", "base": "~140 MB", "small": "~460 MB", "medium": "~1,5 GB",
                     "large-v3": "~3 GB"}}
    try:
        import faster_whisper
        out.update(package=True, version=getattr(faster_whisper, "__version__", None))
    except ImportError:
        out["hint"] = "faster-whisper ist nicht installiert (pip install -r api/requirements.txt)."
        return out
    if platform.system() == "Darwin" and platform.machine() == "arm64":
        out["apple_silicon"] = ("Apple Silicon: faster-whisper (CTranslate2) rechnet auf der CPU — "
                                "empfohlen device=cpu, compute_type=int8; 'small' ist ein guter Kompromiss.")
    if not out["model_available"]:
        out["hint"] = (f"Modell '{settings.whisper_model}' liegt noch nicht lokal vor. Es wird beim ersten "
                       f"Transkribieren einmalig geladen ({out['sizes'].get(settings.whisper_model, 'Größe je Modell')}); "
                       "ohne Internet: Modellordner in CLIPFORGE_WHISPER_MODEL angeben.")
    return out


def transcribe_video(video_path: str, settings: Settings) -> Transcript:
    """Transkribiert ein Video lokal mit faster-whisper (Wort-Timestamps, Cache je Audio+Modell).

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

    language = os.environ.get("CLIPFORGE_WHISPER_LANGUAGE") or None
    with tempfile.TemporaryDirectory() as tmp:
        wav_path = os.path.join(tmp, "audio.wav")
        extract_audio(video_path, wav_path)
        key = f"{_audio_hash(wav_path)}_{os.path.basename(str(settings.whisper_model))}_{language or 'auto'}.json"
        cached = os.path.join(_cache_dir(), key)
        if os.path.isfile(cached):
            return load_transcript_json(cached)
        try:
            model = WhisperModel(
                settings.whisper_model,
                device=settings.whisper_device,
                compute_type=settings.whisper_compute_type,
            )
        except Exception as exc:  # noqa: BLE001 — z. B. kein Netz für den ersten Download
            raise RuntimeError(
                f"Whisper-Modell '{settings.whisper_model}' konnte nicht geladen werden "
                f"({type(exc).__name__}). Ohne Internet: Modell vorab laden oder einen lokalen "
                "Modellordner in CLIPFORGE_WHISPER_MODEL angeben."
            ) from exc
        seg_iter, info = model.transcribe(wav_path, word_timestamps=True, language=language)

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
    tr = Transcript(
        language=getattr(info, "language", "unknown"),
        duration=media.duration or (segments[-1].end if segments else 0.0),
        segments=segments,
    )
    try:
        with open(cached, "w", encoding="utf-8") as fh:
            json.dump({"language": tr.language, "duration": tr.duration,
                       "segments": [{"text": sg.text, "start": sg.start, "end": sg.end,
                                     "words": [{"text": w.text, "start": w.start, "end": w.end} for w in sg.words]}
                                    for sg in tr.segments]}, fh, ensure_ascii=False)
    except OSError:
        pass
    return tr


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
