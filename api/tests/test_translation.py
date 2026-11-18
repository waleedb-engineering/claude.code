"""Videoübersetzung: Ablauf mit nachgebildetem Whisper/Übersetzer, echtes Rendering."""

import os

import pytest

from clipforge.models import Transcript, TranscriptSegment, Word
from clipforge.studio import translate as tr
from clipforge.studio.errors import StudioError
from studio_helpers import clear_env, make_client, make_video, wait_task


def _whisper(lang="de"):
    def fake(path, settings):
        segs = []
        for i, text in enumerate(["Hallo und willkommen.", "Heute lernen wir etwas Neues."]):
            t = i * 1.5
            segs.append(TranscriptSegment(text=text, start=t, end=t + 1.2,
                                          words=[Word(w, t, t + 0.3) for w in text.split()]))
        return Transcript(language=lang, duration=3.0, segments=segs)
    return fake


def test_unsupported_pair_and_engine():
    with pytest.raises(StudioError):
        tr.translate(["x"], "de", "fr", "manual")
    with pytest.raises(StudioError):
        tr.translate(["x"], "de", "en", "deepl")
    assert tr.translate(["Hallo"], "de", "en", "manual") == ["Hallo"]


def test_anthropic_engine_parses_and_validates(monkeypatch):
    monkeypatch.setattr(tr, "LLM_CALL", lambda system, prompt: 'Hier: ["Hello", "World"]')
    assert tr.translate(["Hallo", "Welt"], "de", "en", "anthropic") == ["Hello", "World"]
    monkeypatch.setattr(tr, "LLM_CALL", lambda system, prompt: '["nur eins"]')
    from clipforge.studio.errors import ProviderError
    with pytest.raises(ProviderError):
        tr.translate(["a", "b"], "de", "en", "anthropic")
    assert tr.estimate_cost("anthropic", ["x" * 1000]) > 0
    assert tr.estimate_cost("argos", ["x" * 1000]) == 0


def test_argos_without_model_gives_setup_hint(tmp_path, monkeypatch):
    monkeypatch.setenv("CLIPFORGE_MODELS_DIR", str(tmp_path))
    with pytest.raises(StudioError) as err:
        tr.translate(["Hallo"], "de", "en", "argos")
    assert err.value.code == "model_missing" and "Einrichtung" in err.value.message


@pytest.mark.parametrize("mode", ["subtitles", "dub"])
def test_translate_workflow_end_to_end(tmp_path, mode):
    client, app_module = make_client(str(tmp_path))
    try:
        app_module.studio.service.transcriber = _whisper()
        bad = client.post("/api/studio/projects", json={
            "workflow": "translate", "translation": {"target": "en", "engine": "mock"}})
        assert bad.status_code == 400   # Rechte nicht bestätigt
        pid = client.post("/api/studio/projects", json={
            "workflow": "translate", "rights_confirmed": True,
            "translation": {"target": "en", "engine": "mock", "mode": mode}}).json()["project"]["id"]
        video = make_video(str(tmp_path / "talk.mp4"), seconds=3.0)
        with open(video, "rb") as fh:
            up = client.post(f"/api/studio/projects/{pid}/source",
                             files={"file": ("talk.mp4", fh, "video/mp4")})
        assert up.status_code == 200, up.text
        task = wait_task(client, client.post(f"/api/studio/projects/{pid}/ingest").json()["task"]["id"])
        assert task["status"] == "succeeded", task
        p = client.get(f"/api/studio/projects/{pid}").json()["project"]
        assert p["language"] == "en"
        assert p["scenes"][0]["text"] == "[en] Hallo und willkommen."
        assert p["scenes"][0]["source_text"] == "Hallo und willkommen."
        assert p["scenes"][1]["visual"] == {**p["scenes"][1]["visual"], "mode": "media", "start": 1.5}
        assert p["disclosure"][0] == "AI-translated"
        if mode == "dub":
            assert p["scenes"][0]["fit_speech"] and "audio_source" not in p["scenes"][0]
            assert "synthetic voice" in p["disclosure"]
        else:
            assert p["scenes"][0]["audio_source"] == {"start": 0.0, "end": 1.2}
        art = client.get(f"/api/studio/projects/{pid}/artifacts/translation.json").json()
        assert art["detected_language"] == "de" and len(art["segments"]) == 2
        # Kennzeichnung lässt sich per Patch nicht entfernen
        r = client.patch(f"/api/studio/projects/{pid}",
                         json={"expected_version": p["version"], "disclosure": []})
        assert client.get(f"/api/studio/projects/{pid}").json()["project"]["disclosure"]
        rt = wait_task(client, client.post(f"/api/studio/projects/{pid}/render",
                                           json={"mode": "preview"}).json()["task"]["id"])
        assert rt["status"] == "succeeded", rt
        report = client.get(f"/api/studio/projects/{pid}/renders").json()["renders"][0]
        assert report["captions"].get("disclosure")
        assert report["has_audio"]
        assert r.status_code in (200, 422)
    finally:
        clear_env()


def test_same_language_is_rejected(tmp_path):
    client, app_module = make_client(str(tmp_path))
    try:
        app_module.studio.service.transcriber = _whisper("en")
        pid = client.post("/api/studio/projects", json={
            "workflow": "translate", "rights_confirmed": True,
            "translation": {"target": "en", "engine": "mock"}}).json()["project"]["id"]
        with open(make_video(str(tmp_path / "v.mp4"), seconds=2.0), "rb") as fh:
            client.post(f"/api/studio/projects/{pid}/source", files={"file": ("v.mp4", fh, "video/mp4")})
        task = wait_task(client, client.post(f"/api/studio/projects/{pid}/ingest").json()["task"]["id"])
        assert task["status"] == "failed" and task["error"]["code"] == "validation_error"
    finally:
        clear_env()
