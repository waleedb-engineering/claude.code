"""Modell-Katalog (Download nur nach Zustimmung, Prüfsumme) und lokale
Hintergrundentfernung. Die echten Modelltests laufen, wenn
CLIPFORGE_TEST_MODELS_DIR auf einen Ordner mit u2netp.onnx zeigt
(CI lädt das Modell vorher herunter)."""

import hashlib
import io
import os

import numpy as np
import pytest

from clipforge.studio import models
from clipforge.studio.errors import StudioError

REAL = os.environ.get("CLIPFORGE_TEST_MODELS_DIR")
needs_model = pytest.mark.skipif(
    not (REAL and os.path.isfile(os.path.join(REAL, "u2netp.onnx"))),
    reason="u2netp.onnx nicht vorhanden (CLIPFORGE_TEST_MODELS_DIR)")


@pytest.fixture(autouse=True)
def _dirs(tmp_path, monkeypatch):
    monkeypatch.setenv("CLIPFORGE_STUDIO_DIR", str(tmp_path / "studio"))
    monkeypatch.setenv("CLIPFORGE_MODELS_DIR", REAL or str(tmp_path / "models"))
    monkeypatch.setattr(models, "OPEN_URL", None)


def _fake(payload: bytes, calls: list):
    def opener(url):
        calls.append(url)
        return io.BytesIO(payload)
    return opener


def test_download_requires_consent(tmp_path, monkeypatch):
    monkeypatch.setenv("CLIPFORGE_MODELS_DIR", str(tmp_path / "m"))
    calls = []
    monkeypatch.setattr(models, "OPEN_URL", _fake(b"x", calls))
    with pytest.raises(StudioError) as err:
        models.download("bg_fast", accept_license=False)
    assert err.value.code == "consent_required" and calls == []


def test_checksum_mismatch_discards_file(tmp_path, monkeypatch):
    monkeypatch.setenv("CLIPFORGE_MODELS_DIR", str(tmp_path / "m"))
    monkeypatch.setattr(models, "OPEN_URL", _fake(b"falscher inhalt", []))
    with pytest.raises(StudioError) as err:
        models.download("bg_fast", accept_license=True)
    assert err.value.code == "checksum_mismatch"
    assert os.listdir(tmp_path / "m") == []
    assert models.model_path("bg_fast") is None


def test_successful_download_and_delete(tmp_path, monkeypatch):
    monkeypatch.setenv("CLIPFORGE_MODELS_DIR", str(tmp_path / "m"))
    payload = b"onnx-bytes" * 1000
    spec = {**models.CATALOG["bg_fast"],
            "files": [{**models.CATALOG["bg_fast"]["files"][0],
                       "md5": hashlib.md5(payload).hexdigest()}]}
    monkeypatch.setitem(models.CATALOG, "bg_fast", spec)
    calls = []
    monkeypatch.setattr(models, "OPEN_URL", _fake(payload, calls))
    assert models.download("bg_fast", True)["installed"] is True
    assert calls == [spec["files"][0]["url"]]
    assert models.download("bg_fast", True)["already"] is True  # kein zweiter Download
    assert len(calls) == 1
    entry = next(m for m in models.status("background") if m["id"] == "bg_fast")
    assert entry["installed"] and entry["license"].startswith("Apache")
    models.delete("bg_fast")
    assert models.model_path("bg_fast") is None


def test_catalog_has_only_fixed_https_urls():
    for spec in models.CATALOG.values():
        for f in spec["files"]:
            assert f["url"].startswith(("https://github.com/", "https://media.githubusercontent.com/",
                                        "https://huggingface.co/"))
            assert "/" not in f["name"] and ".." not in f["name"]


def test_missing_model_gives_clear_error(tmp_path, monkeypatch):
    monkeypatch.setenv("CLIPFORGE_MODELS_DIR", str(tmp_path / "leer"))
    from clipforge.studio import bgremove
    import cv2
    img = str(tmp_path / "a.png")
    cv2.imwrite(img, np.zeros((10, 10, 3), np.uint8))
    with pytest.raises(StudioError) as err:
        bgremove.process_image(img, str(tmp_path / "b.png"), model_id="bg_quality")
    assert err.value.code == "model_missing" and err.value.status == 409


def _scene_image(path):
    import cv2
    img = np.full((320, 240, 3), (200, 180, 160), np.uint8)
    cv2.circle(img, (120, 160), 60, (20, 40, 220), -1)
    cv2.imwrite(path, img)


@needs_model
def test_real_image_transparent_and_color(tmp_path):
    import cv2
    from clipforge.studio import bgremove
    src = str(tmp_path / "in.png")
    _scene_image(src)
    info = bgremove.process_image(src, str(tmp_path / "t.png"), model_id="bg_fast")
    out = cv2.imread(str(tmp_path / "t.png"), cv2.IMREAD_UNCHANGED)
    assert out.shape[2] == 4
    assert out[160, 120, 3] > 200 and out[5, 5, 3] < 40     # Objekt bleibt, Rand verschwindet
    assert 0.05 < info["foreground_ratio"] < 0.5
    bgremove.process_image(src, str(tmp_path / "c.png"), mode="color", color="#00ff00",
                           model_id="bg_fast")
    col = cv2.imread(str(tmp_path / "c.png"))
    assert col[5, 5, 1] > 200 and col[5, 5, 0] < 60
    with pytest.raises(StudioError):
        bgremove.process_image(src, str(tmp_path / "x.png"), mode="color", color="red",
                               model_id="bg_fast")


@needs_model
def test_real_video_background_replace_keeps_audio(tmp_path):
    import subprocess
    import cv2
    from clipforge.ffmpeg_utils import probe
    from clipforge.studio import bgremove
    src = str(tmp_path / "v.mp4")
    subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-f", "lavfi", "-i",
                    "color=c=0xa0b4c8:s=240x320:d=1:r=10", "-f", "lavfi", "-i",
                    "sine=frequency=440:duration=1", "-vf",
                    "drawbox=x=80:y=100:w=80:h=120:color=red:t=fill",
                    "-c:v", "libx264", "-pix_fmt", "yuv420p", "-c:a", "aac", "-shortest", src],
                   check=True)
    out = str(tmp_path / "o.mp4")
    calls = []
    info = bgremove.process_video(src, out, mode="color", color="#0000ff", model_id="bg_fast",
                                  progress=calls.append)
    assert info["frames"] >= 9
    pr = probe(out)
    assert pr.has_audio and (pr.width, pr.height) == (240, 320)
    cap = cv2.VideoCapture(out)
    ok, frame = cap.read()
    assert ok and frame[5, 5, 0] > 180   # Hintergrund jetzt blau
    with pytest.raises(bgremove.Canceled):
        bgremove.process_video(src, str(tmp_path / "c.mp4"), model_id="bg_fast",
                               should_cancel=lambda: True)
    assert not os.path.exists(str(tmp_path / "c.mp4.part.mp4"))


@needs_model
def test_background_task_and_preview_routes(tmp_path):
    from studio_helpers import clear_env, make_client, wait_task
    client, _ = make_client(str(tmp_path), CLIPFORGE_MODELS_DIR=REAL)
    try:
        pid = client.post("/api/studio/projects", json={
            "workflow": "script", "script": "Hallo Welt, kurzer Test.", "auto_ingest": False}).json()["project"]["id"]
        src = str(tmp_path / "foto.png")
        _scene_image(src)
        with open(src, "rb") as fh:
            name = client.post(f"/api/studio/projects/{pid}/media",
                               files={"file": ("foto.png", fh, "image/png")}).json()["name"]
        prev = client.post(f"/api/studio/projects/{pid}/media/{name}/background/preview",
                           json={"model": "bg_fast"})
        assert prev.status_code == 200 and prev.content[:4] == b"\x89PNG"
        task = client.post(f"/api/studio/projects/{pid}/media/{name}/background",
                           json={"model": "bg_fast", "mode": "transparent"}).json()["task"]
        done = wait_task(client, task["id"])
        assert done["status"] == "succeeded", done
        names = [m["name"] for m in client.get(f"/api/studio/projects/{pid}/media").json()["media"]]
        assert done["result"]["media"] in names and name in names   # Original bleibt
        bad = client.post(f"/api/studio/projects/{pid}/media/../x/background", json={})
        assert bad.status_code in (400, 404)
        assert client.post("/api/studio/models/bg_fast/download", json={}).status_code == 400
    finally:
        clear_env("CLIPFORGE_MODELS_DIR")
