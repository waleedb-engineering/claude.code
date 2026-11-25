"""Transkription: Status ohne Download, klare Fehlermeldung, Cache je Audio+Modell.

Das Whisper-Modell selbst ist in der Testumgebung nicht ladbar (Hugging Face
gesperrt) — der Modellaufruf wird hier NACHGEBILDET; Cache, Audio-Extraktion
und Fehlerpfad laufen echt."""

import subprocess
import types

import pytest

from clipforge import transcribe as tr
from clipforge.config import get_settings


def _clip(path):
    subprocess.run(["ffmpeg", "-y", "-v", "error", "-f", "lavfi", "-i", "sine=f=300:d=2", "-f", "lavfi",
                    "-i", "color=s=64x64:d=2", "-shortest", "-c:v", "libx264", "-c:a", "aac", path], check=True)
    return path


def test_status_reports_missing_model_without_download(tmp_path, monkeypatch):
    monkeypatch.setenv("HF_HOME", str(tmp_path / "hf"))
    st = tr.transcription_status(get_settings())
    assert st["package"] is True and st["model_available"] is False and "einmalig" in st["hint"]


def test_cache_and_language(tmp_path, monkeypatch):
    monkeypatch.setenv("CLIPFORGE_TRANSCRIPT_CACHE", str(tmp_path / "cache"))
    monkeypatch.setenv("CLIPFORGE_WHISPER_LANGUAGE", "de")
    calls = []

    class FakeModel:
        def __init__(self, *a, **k):
            pass

        def transcribe(self, wav, word_timestamps, language):
            calls.append(language)
            w = types.SimpleNamespace(word=" Hallo", start=0.1, end=0.5)
            seg = types.SimpleNamespace(text="Hallo", start=0.1, end=0.5, words=[w])
            return iter([seg]), types.SimpleNamespace(language="de")
    import faster_whisper
    monkeypatch.setattr(faster_whisper, "WhisperModel", FakeModel)
    v = _clip(str(tmp_path / "a.mp4"))
    t1 = tr.transcribe_video(v, get_settings())
    t2 = tr.transcribe_video(v, get_settings())                  # aus dem Cache
    assert calls == ["de"] and t1.language == t2.language == "de"
    assert t2.segments[0].words[0].text == "Hallo" and t2.segments[0].words[0].start == 0.1


def test_clear_error_when_model_cannot_load(tmp_path, monkeypatch):
    monkeypatch.setenv("CLIPFORGE_TRANSCRIPT_CACHE", str(tmp_path / "cache"))
    import faster_whisper

    def broken(*a, **k):
        raise OSError("offline")
    monkeypatch.setattr(faster_whisper, "WhisperModel", broken)
    with pytest.raises(RuntimeError) as e:
        tr.transcribe_video(_clip(str(tmp_path / "b.mp4")), get_settings())
    assert "konnte nicht geladen werden" in str(e.value) and "CLIPFORGE_WHISPER_MODEL" in str(e.value)
