"""Mediathek: Upload, Duplikaterkennung, Suche/Tags, Herkunft/Lizenz, Verwendung im
Projekt (Kopie + Nutzungsprotokoll), sicheres Löschen, Benutzertrennung."""

import subprocess

from studio_helpers import make_client, make_click_wav, wait_task


def _png(path, color="red"):
    subprocess.run(["ffmpeg", "-y", "-v", "error", "-f", "lavfi", "-i", f"color=c={color}:s=64x64:d=1",
                    "-frames:v", "1", path], check=True)
    return path


def test_library_flow(tmp_path):
    client, _ = make_client(str(tmp_path))
    with open(_png(str(tmp_path / "logo.png")), "rb") as fh:
        r = client.post("/api/studio/library", files={"file": ("Logo Rot.png", fh, "image/png")},
                        data={"kind": "brand", "tags": "logo, Marke", "source": "upload"})
    assert r.status_code == 201, r.text
    logo = r.json()["item"]
    assert logo["kind"] == "brand" and logo["tags"] == ["logo", "marke"] and len(logo["sha256"]) == 64
    with open(tmp_path / "logo.png", "rb") as fh:                       # gleiche Datei erneut
        dup = client.post("/api/studio/library", files={"file": ("kopie.png", fh, "image/png")}).json()["item"]
    assert dup["duplicate"] is True and dup["id"] == logo["id"]
    with open(make_click_wav(str(tmp_path / "boom.wav"), 1.0), "rb") as fh:
        sfx = client.post("/api/studio/library", files={"file": ("boom.wav", fh, "audio/wav")},
                          data={"kind": "sfx", "tags": "effekt", "source": "stock", "author": "Anna",
                                "url": "https://example.org/boom", "license_name": "CC0",
                                "license_url": "https://creativecommons.org/publicdomain/zero/1.0/"}).json()["item"]
    assert sfx["duration"] == 1.0 and sfx["provenance"]["license"]["name"] == "CC0"
    assert client.post("/api/studio/library", files={"file": ("x.exe", b"MZ", "application/x")}).status_code == 415
    assert client.post("/api/studio/library", files={"file": ("y.png", b"kaputt", "image/png")},
                       data={"kind": "music"}).status_code == 400
    # Suche und Filter
    lst = client.get("/api/studio/library", params={"q": "logo"}).json()
    assert [i["id"] for i in lst["items"]] == [logo["id"]] and "effekt" in lst["tags"]
    assert [i["id"] for i in client.get("/api/studio/library", params={"kind": "sfx"}).json()["items"]] == [sfx["id"]]
    assert client.get(f"/api/studio/library/{logo['id']}/file").status_code == 200
    # Bearbeiten
    p = client.patch(f"/api/studio/library/{logo['id']}", json={"tags": ["Logo", "Neu"], "name": "Logo final.png"}).json()
    assert p["item"]["tags"] == ["logo", "neu"] and p["item"]["name"] == "Logo final.png"
    # In Projekt verwenden → Kopie + Herkunft + Nutzung
    r = client.post("/api/studio/projects", json={"workflow": "script", "script": "Hallo und willkommen. Heute zeige ich dir drei Tricks. Folge für mehr."})
    pid = r.json()["project"]["id"]
    wait_task(client, r.json()["task_id"])
    used = client.post(f"/api/studio/library/{sfx['id']}/use", json={"project_id": pid}).json()
    media = client.get(f"/api/studio/projects/{pid}/media").json()["media"]
    m = next(x for x in media if x["name"] == used["media"]["name"])
    assert m["kind"] == "audio" and m["origin"]["license"]["name"] == "CC0"
    # Löschen: in Benutzung → Bestätigung nötig; Projekt behält Kopie
    d = client.delete(f"/api/studio/library/{sfx['id']}")
    assert d.status_code == 409 and pid in d.text
    assert client.delete(f"/api/studio/library/{sfx['id']}", params={"force": True}).json()["projects_keep_copy"] == [pid]
    assert client.get(f"/api/studio/projects/{pid}/media/{used['media']['name']}").status_code == 200
    # Projektmedium in die Mediathek übernehmen
    item = client.post(f"/api/studio/projects/{pid}/media/{used['media']['name']}/to-library").json()["item"]
    assert item["provenance"]["source"] == "project"
    assert client.get("/api/studio/library/../../etc").status_code in (400, 404)


def test_library_is_per_user(tmp_path, monkeypatch):
    from clipforge.studio import library, workspace
    with workspace.use("anna"):
        a = library.add_file(_png(str(tmp_path / "a.png")), "a.png")
    with workspace.use("ben"):
        assert library.search() == []
    with workspace.use("anna"):
        assert [e["id"] for e in library.search()] == [a["id"]]
