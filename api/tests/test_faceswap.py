"""Face Swap: Einwilligung, lokale Gesichtsprüfung (echt, wenn Modelle +
Testbilder vorhanden), Kennzeichnung, Protokoll, Kosten; fal.ai nachgebildet."""

import io
import os
import shutil

import pytest

from clipforge.studio import faceswap
from clipforge.studio.errors import StudioError
from studio_helpers import clear_env, make_client, wait_task

REAL = os.environ.get("CLIPFORGE_TEST_MODELS_DIR") or ""
HAVE = all(os.path.isfile(os.path.join(REAL, f)) for f in (
    "face_detection_yunet_2023mar.onnx", "face_recognition_sface_2021dec.onnx",
    "lena.jpg", "messi5.jpg"))
needs = pytest.mark.skipif(not HAVE, reason="Gesichtsmodelle/Testbilder fehlen (CLIPFORGE_TEST_MODELS_DIR)")


def test_models_required(tmp_path, monkeypatch):
    monkeypatch.setenv("CLIPFORGE_MODELS_DIR", str(tmp_path))
    with pytest.raises(StudioError) as err:
        faceswap._models()
    assert err.value.code == "model_missing"


def test_online_mode_requires_operator_unlock(monkeypatch):
    monkeypatch.setenv("CLIPFORGE_AUTH", "accounts")
    monkeypatch.delenv("CLIPFORGE_FACE_SWAP_ONLINE", raising=False)
    assert faceswap.enabled()[0] is False
    monkeypatch.setenv("CLIPFORGE_FACE_SWAP_ONLINE", "1")
    assert faceswap.enabled()[0] is True


@needs
def test_reference_registration_and_verification(tmp_path, monkeypatch):
    monkeypatch.setenv("CLIPFORGE_STUDIO_DIR", str(tmp_path / "studio"))
    monkeypatch.setenv("CLIPFORGE_MODELS_DIR", REAL)
    lena = os.path.join(REAL, "lena.jpg")
    with pytest.raises(StudioError) as err:
        faceswap.register_face(lena, name="Ich", basis="own", person="", no_deception=False, user="u")
    assert err.value.code == "consent_required"
    with pytest.raises(StudioError):
        faceswap.register_face(lena, name="X", basis="permission", person="", no_deception=True, user="u")
    face = faceswap.register_face(lena, name="Ich", basis="own", person="", no_deception=True, user="u")
    assert "embedding" not in face and face["consent"]["confirmed_by"] == "u"
    assert faceswap.verify_reference(face["id"])["score"] > 0.9
    # ausgetauschte Referenzdatei (andere Person) wird erkannt
    shutil.copy(os.path.join(REAL, "messi5.jpg"), os.path.join(tmp_path / "studio" / "faces", face["file"]))
    with pytest.raises(StudioError) as err:
        faceswap.verify_reference(face["id"])
    assert err.value.code == "face_check_failed"
    # Bild ohne Gesicht wird als Referenz abgelehnt
    import cv2
    import numpy as np
    blank = str(tmp_path / "leer.png")
    cv2.imwrite(blank, np.full((300, 300, 3), 128, np.uint8))
    with pytest.raises(StudioError) as err:
        faceswap.register_face(blank, name="Leer", basis="own", person="", no_deception=True, user="u")
    assert err.value.code == "face_count"
    assert [e["event"] for e in faceswap.audit()] == ["face_registered"]


@needs
def test_face_swap_flow_with_mocked_engine(tmp_path, monkeypatch):
    from clipforge.studio import safe_fetch
    from clipforge.studio.providers import fal
    client, _ = make_client(str(tmp_path), CLIPFORGE_MODELS_DIR=REAL, FAL_KEY="fal-test-key")
    calls = []

    def fake_http(method, url, headers, payload=None):
        calls.append((method, url, payload))
        if method == "POST":
            return 200, {"status_url": "https://queue.fal.run/s", "response_url": "https://queue.fal.run/r"}
        if url.endswith("/s"):
            return 200, {"status": "COMPLETED"}
        return 200, {"image": {"url": "https://v3.fal.media/out.png"}}
    monkeypatch.setattr(fal, "FAL_HTTP", fake_http)
    monkeypatch.setattr(fal, "SLEEP", lambda s: None)
    swapped = open(os.path.join(REAL, "messi5.jpg"), "rb").read()

    class Res:
        body, content_type, status = swapped, "image/jpeg", 200
    monkeypatch.setattr(safe_fetch, "fetch", lambda url, **kw: Res())
    try:
        with open(os.path.join(REAL, "lena.jpg"), "rb") as fh:
            r = client.post("/api/studio/faces", files={"file": ("ich.jpg", fh, "image/jpeg")},
                            data={"name": "Ich", "basis": "own", "no_deception": "true"})
        assert r.status_code == 201, r.text
        fid = r.json()["face"]["id"]
        pid = client.post("/api/studio/projects", json={
            "workflow": "script", "script": "Ein kurzer Test mit Gesicht.", "auto_ingest": False,
            "budget_limit_usd": 1}).json()["project"]["id"]
        with open(os.path.join(REAL, "messi5.jpg"), "rb") as fh:
            name = client.post(f"/api/studio/projects/{pid}/media",
                               files={"file": ("szene.jpg", fh, "image/jpeg")}).json()["name"]
        r = client.post(f"/api/studio/projects/{pid}/media/{name}/faceswap", json={"face_id": fid})
        assert r.status_code == 402 and calls == []           # Kosten erst bestätigen
        r = client.post(f"/api/studio/projects/{pid}/media/{name}/faceswap",
                        json={"face_id": fid, "confirm_cost": True})
        assert r.status_code == 202, r.text
        task = wait_task(client, r.json()["task"]["id"])
        assert task["status"] == "succeeded", task
        out = task["result"]["media"]
        proj = client.get(f"/api/studio/projects/{pid}").json()["project"]
        assert faceswap.LABEL in proj["disclosure"]
        media = {m["name"]: m for m in client.get(f"/api/studio/projects/{pid}/media").json()["media"]}
        assert media[out]["origin"]["source"] == "face_swap"
        body = calls[0][2]
        assert body["face_image_0"].startswith("data:image/") and "target_image" in body
        events = [e["event"] for e in client.get("/api/studio/faces/audit").json()["entries"]]
        assert events == ["face_registered", "face_swap"]
        costs = client.get(f"/api/studio/projects/{pid}/estimate").json()
        assert costs  # Budget-Ledger existiert
    finally:
        clear_env("CLIPFORGE_MODELS_DIR", "FAL_KEY")
