"""Avatar als Bild-im-Bild und eigene Sprachaufnahme je Szene (echtes FFmpeg)."""

import os

import pytest

from clipforge.studio.errors import StudioError
from clipforge.studio.projects import migrate, new_project, normalize_scene
from clipforge.studio.render import render_project
from studio_helpers import make_png, make_tone_wav


@pytest.fixture(autouse=True)
def _studio(tmp_path, monkeypatch):
    monkeypatch.setenv("CLIPFORGE_STUDIO_DIR", str(tmp_path / "studio"))


@pytest.mark.parametrize("layout", ["pip_br", "bottom_half"])
def test_avatar_layout_and_own_recording(tmp_path, layout):
    d = tmp_path / "p"
    (d / "media").mkdir(parents=True)
    make_png(str(d / "media" / "face.png"), "300x400")
    make_tone_wav(str(d / "media" / "rec.wav"), 2.0)
    p = new_project(title="t", workflow="script")
    p["visuals"] = {"avatar_image": "face.png", "avatar_layout": layout}
    p["scenes"] = [normalize_scene({"text": "Hallo.", "visual": {"mode": "avatar"},
                                    "voice_media": "rec.wav"}, str(d))]
    report = render_project(migrate(p), str(d), mode="preview")
    assert report["has_audio"]
    assert report["scenes"][0]["speech"] == pytest.approx(2.0, abs=0.1)   # Länge der Aufnahme
    assert abs(report["duration"] - report["expected"]["duration"]) < 0.15


def test_voice_media_validation(tmp_path):
    d = tmp_path / "p"
    (d / "media").mkdir(parents=True)
    with pytest.raises(StudioError):
        normalize_scene({"text": "x", "voice_media": "fehlt.wav"}, str(d))
    with pytest.raises(StudioError):
        normalize_scene({"text": "x", "voice_media": "bild.png"}, str(d))
    assert migrate({"visuals": {"avatar_layout": "kaputt"}})["visuals"]["avatar_layout"] == "full"
