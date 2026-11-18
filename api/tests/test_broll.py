"""B-Roll: Mediathek-Zuordnung (echt), Stock-Suche/-Import (nachgebildete API)."""

import os

import pytest

from clipforge.studio import broll
from clipforge.studio.errors import StudioError
from clipforge.studio.projects import migrate, new_project, normalize_scene


@pytest.fixture
def pdir(tmp_path, monkeypatch):
    monkeypatch.setenv("CLIPFORGE_STUDIO_DIR", str(tmp_path / "studio"))
    d = tmp_path / "p"
    (d / "media").mkdir(parents=True)
    for name in ("strand_sonnenuntergang_ab12cd.jpg", "kaffee_tasse_0a0a0a.png",
                 "IMG_0001_ffffff.jpg", "notizen.txt"):
        (d / "media" / name).write_bytes(b"x")
    return str(d)


def test_keywords_skip_stopwords():
    kw = broll.keywords("Der Kaffee am Morgen ist das Beste für den Tag")
    assert "kaffee" in kw and "der" not in kw and "ist" not in kw


def test_library_match_by_filename_and_tags(pdir):
    hits = broll.library_matches(pdir, "Ein Abend am Strand beim Sonnenuntergang")
    assert hits[0]["name"].startswith("strand_") and hits[0]["score"] == 2
    assert not broll.library_matches(pdir, "Programmieren lernen")
    broll.set_media_meta(pdir, "IMG_0001_ffffff.jpg", tags="laptop, programmieren")
    assert broll.library_matches(pdir, "Programmieren lernen")[0]["name"] == "IMG_0001_ffffff.jpg"


def test_auto_assign_respects_manual_visuals_and_uses_each_once(pdir):
    p = new_project(title="t", workflow="script")
    p["scenes"] = [normalize_scene(x) for x in (
        {"text": "Kaffee am Morgen"},
        {"text": "Noch mehr Kaffee aus der Tasse"},
        {"text": "Strand", "visual": {"mode": "ai_image"}},
        {"text": "Nichts Passendes hier"})]
    scenes, log = broll.auto_assign(migrate(p), pdir)
    assert scenes[0]["visual"]["media"] == "kaffee_tasse_0a0a0a.png"
    assert scenes[1]["visual"]["mode"] == "media"            # Fallback: Wiederverwendung erlaubt
    assert scenes[2]["visual"]["mode"] == "ai_image"         # manuelle Wahl bleibt
    assert scenes[3]["visual"]["mode"] == "motion"
    assert {e["scene"] for e in log} == {scenes[0]["id"], scenes[1]["id"]}


def test_stock_requires_key(monkeypatch):
    monkeypatch.delenv("PEXELS_API_KEY", raising=False)
    with pytest.raises(StudioError) as err:
        broll.search_stock("pexels", "kaffee")
    assert err.value.code == "credential_not_set"


def test_pexels_search_parses_and_import_records_license(pdir, monkeypatch):
    monkeypatch.setenv("PEXELS_API_KEY", "test-key")
    seen = {}

    def api(url, headers):
        seen["url"], seen["headers"] = url, headers
        return {"videos": [{"id": 7, "duration": 9, "image": "https://images.pexels.com/p.jpg",
                            "url": "https://www.pexels.com/video/7/", "user": {"name": "Ana"},
                            "video_files": [
                                {"link": "https://videos.pexels.com/a_sd.mp4", "file_type": "video/mp4",
                                 "width": 540, "height": 960},
                                {"link": "https://videos.pexels.com/a_hd.mp4", "file_type": "video/mp4",
                                 "width": 1080, "height": 1920}]}]}
    monkeypatch.setattr(broll, "API_GET", api)
    hits = broll.search_stock("pexels", "kaffee morgen", "9:16", "video")
    assert "orientation=portrait" in seen["url"] and seen["headers"]["Authorization"] == "test-key"
    assert hits[0]["download"].endswith("a_hd.mp4") and hits[0]["author"] == "Ana"

    class Res:
        body, content_type, status = b"\x00\x00\x00\x18ftypmp42", "video/mp4", 200
    monkeypatch.setattr(broll.safe_fetch, "fetch", lambda url, **kw: Res())
    name = broll.import_stock(pdir, hits[0], "kaffee morgen")
    assert os.path.isfile(os.path.join(pdir, "media", name))
    origin = broll.media_meta(pdir)[name]["origin"]
    assert origin["author"] == "Ana" and origin["license"]["name"] == "Pexels-Lizenz"
    with pytest.raises(StudioError):   # fremder Host wird abgelehnt
        broll.import_stock(pdir, {**hits[0], "download": "https://evil.example/x.mp4"}, "x")


def test_pixabay_image_search(monkeypatch):
    monkeypatch.setenv("PIXABAY_API_KEY", "k")
    monkeypatch.setattr(broll, "API_GET", lambda url, h: {"hits": [
        {"id": 1, "previewURL": "https://cdn.pixabay.com/p.jpg", "largeImageURL":
         "https://pixabay.com/get/x.jpg", "user": "bob", "pageURL": "https://pixabay.com/x"}]})
    hit = broll.search_stock("pixabay", "berg", "16:9", "image")[0]
    assert hit["license"]["commercial"] is True and hit["author"] == "bob"


def test_broll_routes(tmp_path):
    from studio_helpers import clear_env, make_client, wait_task
    client, _ = make_client(str(tmp_path))
    try:
        proj = client.post("/api/studio/projects", json={
            "workflow": "script", "script": "Kaffee am Morgen macht wach. Danach geht es an den Strand.",
            "auto_ingest": False}).json()["project"]
        pid = proj["id"]
        src = tmp_path / "kaffee.png"
        import cv2
        import numpy as np
        cv2.imwrite(str(src), np.zeros((32, 32, 3), np.uint8))
        with open(src, "rb") as fh:
            name = client.post(f"/api/studio/projects/{pid}/media",
                               files={"file": ("kaffee.png", fh, "image/png")}).json()["name"]
        ingest = client.post(f"/api/studio/projects/{pid}/ingest").json()["task"]
        wait_task(client, ingest["id"])
        proj = client.get(f"/api/studio/projects/{pid}").json()["project"]
        sid = proj["scenes"][0]["id"]
        sug = client.get(f"/api/studio/projects/{pid}/scenes/{sid}/broll").json()
        assert "kaffee" in sug["keywords"] and sug["library"][0]["name"] == name
        assert client.put(f"/api/studio/projects/{pid}/media/{name}/tags",
                          json={"tags": ["Tasse"]}).json()["tags"] == ["tasse"]
        t = client.post(f"/api/studio/projects/{pid}/broll/auto", json={}).json()["task"]
        done = wait_task(client, t["id"])
        assert done["status"] == "succeeded" and done["result"]["assigned"] >= 1
        scenes = client.get(f"/api/studio/projects/{pid}").json()["project"]["scenes"]
        assert any(s["visual"]["media"] == name for s in scenes)
        r = client.post(f"/api/studio/projects/{pid}/broll/auto", json={"stock": "pexels"})
        assert r.status_code == 409   # kein Schlüssel
    finally:
        clear_env()
