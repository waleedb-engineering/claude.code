"""Studio: HTTP-Routen (Uploads, Workflows, Editor, Render, Export, Fehlercodes)."""

from __future__ import annotations

import io
import os
import shutil
import socket
import tempfile

from studio_helpers import (
    clear_env, ffprobe, make_click_wav, make_client, make_pdf, make_png, make_tone_wav,
    make_video, run_all, wait_task,
)

from clipforge.models import Transcript, TranscriptSegment, Word

SCRIPT = "Lokale Videotools sparen Zeit. Alles bleibt auf deinem Rechner. Folge für mehr."


def _create(client, **body):
    r = client.post("/api/studio/projects", json=body)
    assert r.status_code == 201, r.text
    data = r.json()
    if data["task_id"]:
        task = wait_task(client, data["task_id"])
        assert task["status"] == "succeeded", task
    return data["project"]["id"]


def _project(client, pid):
    return client.get(f"/api/studio/projects/{pid}").json()["project"]


def _err(resp) -> str:
    return resp.json()["detail"]["code"]


def _upload(client, pid, name, data, kind=None, path="source"):
    form = {"kind": kind} if kind else {}
    return client.post(f"/api/studio/projects/{pid}/{path}",
                       files={"file": (name, io.BytesIO(data), "application/octet-stream")},
                       data=form)


def test_overview_workflows_and_readiness_have_no_secrets():
    tmp = tempfile.mkdtemp(prefix="api_")
    secret = "sentinel-elevenlabs-key"
    try:
        client, _ = make_client(tmp, ELEVENLABS_API_KEY=secret)
        ov = client.get("/api/studio/overview").json()
        assert ov["flags"]["studio"] and ov["project_count"] == 0
        wf = {w["id"]: w for w in client.get("/api/studio/workflows").json()["workflows"]}
        for wid in ("prompt", "script", "article_url", "website_review", "social_url", "pdf",
                    "audio", "music", "podcast", "longform", "media", "job", "product_ad",
                    "cinematic"):
            assert wf[wid]["available"], wid
        assert not wf["youtube"]["available"] and not wf["avatar"]["available"]
        prov = client.get("/api/studio/providers")
        assert secret not in prov.text and "ELEVENLABS_API_KEY" in prov.text
        states = {p["id"]: p["status"] for p in prov.json()["providers"]}
        assert states["elevenlabs"] == "ready" and states["openai_tts"] == "not_configured"
        plats = {p["platform"]: p for p in prov.json()["platforms"]}
        assert set(plats) == {"youtube_shorts", "tiktok", "instagram_reels", "x"}
        assert all(p["state"] == "not_connected" for p in plats.values())
        assert all(p["fallback"] == "export_pack" for p in plats.values())
        assert secret not in client.get("/api/studio/voices").text
    finally:
        clear_env("ELEVENLABS_API_KEY")
        shutil.rmtree(tmp, ignore_errors=True)


def test_feature_flags_disable_cleanly():
    tmp = tempfile.mkdtemp(prefix="api_")
    try:
        client, _ = make_client(tmp, CLIPFORGE_FLAG_STUDIO="false")
        r = client.get("/api/studio/overview")
        assert r.status_code == 403 and _err(r) == "feature_disabled"
        assert client.get("/health").status_code == 200  # Rest der App unberührt
        clear_env("CLIPFORGE_FLAG_STUDIO")
        client, _ = make_client(tmp, CLIPFORGE_FLAG_STUDIO_URL_IMPORT="false",
                                CLIPFORGE_FLAG_STUDIO_AUTOMATION="false")
        r = client.post("/api/studio/projects", json={"workflow": "article_url",
                                                      "url": "https://example.com/a"})
        assert r.status_code == 403 and _err(r) == "feature_disabled"
        assert client.get("/api/studio/automations").status_code == 403
        assert client.get("/api/studio/projects").status_code == 200
    finally:
        clear_env("CLIPFORGE_FLAG_STUDIO", "CLIPFORGE_FLAG_STUDIO_URL_IMPORT",
                  "CLIPFORGE_FLAG_STUDIO_AUTOMATION")
        shutil.rmtree(tmp, ignore_errors=True)


def test_create_validation_and_stable_error_codes():
    tmp = tempfile.mkdtemp(prefix="api_")
    try:
        client, _ = make_client(tmp)
        post = lambda body: client.post("/api/studio/projects", json=body)  # noqa: E731
        assert _err(post({"workflow": "nope"})) == "validation_error"
        assert _err(post({"workflow": "prompt", "prompt": " "})) == "validation_error"
        assert _err(post({"workflow": "script", "script": "zu kurz"})) == "validation_error"
        assert _err(post({"workflow": "product_ad", "product": {}})) == "validation_error"
        assert _err(post({"workflow": "job", "job_id": "gibtsnicht"})) == "job_not_found"
        r = post({"workflow": "youtube", "url": "https://youtube.com/watch?v=x"})
        assert r.status_code == 409 and _err(r) == "workflow_unavailable"
        assert _err(post({"workflow": "avatar", "prompt": "Hallo"})) == "workflow_unavailable"
        for url, code in (("http://127.0.0.1/admin", "url_blocked"),
                          ("http://localhost:8000/health", "url_blocked"),
                          ("file:///etc/passwd", "url_invalid"),
                          ("http://user:pw@example.com/", "url_blocked")):
            r = post({"workflow": "article_url", "url": url})
            assert r.status_code == 400 and _err(r) == code, (url, r.text)
        assert post({"workflow": "prompt"}).status_code in (400, 422)
        assert post({"workflow": "prompt", "prompt": "x y z", "target_seconds": 5}).status_code == 422
        for path in ("/api/studio/projects/ffffffffffff", "/api/studio/tasks/ffffffffffff"):
            r = client.get(path)
            assert r.status_code == 404 and _err(r) in ("project_not_found", "task_not_found")
        for bad in ("..%2F..%2Fetc", "ABC", "x" * 12):
            assert client.get(f"/api/studio/projects/{bad}").status_code in (400, 404)
        assert client.get("/api/studio/projects").json()["projects"] == []  # nichts angelegt
    finally:
        clear_env()
        shutil.rmtree(tmp, ignore_errors=True)


def test_idempotent_project_creation():
    tmp = tempfile.mkdtemp(prefix="api_")
    try:
        client, _ = make_client(tmp)
        body = {"workflow": "script", "script": SCRIPT}
        a = client.post("/api/studio/projects", json=body, headers={"Idempotency-Key": "k-1"}).json()
        b = client.post("/api/studio/projects", json=body, headers={"Idempotency-Key": "k-1"}).json()
        c = client.post("/api/studio/projects", json=body, headers={"Idempotency-Key": "k-2"}).json()
        assert a["project"]["id"] == b["project"]["id"] != c["project"]["id"]
        assert not a["replayed"] and b["replayed"] and a["task_id"] == b["task_id"]
        wait_task(client, a["task_id"])
        wait_task(client, c["task_id"])
        assert len(client.get("/api/studio/projects").json()["projects"]) == 2
    finally:
        clear_env()
        shutil.rmtree(tmp, ignore_errors=True)


def test_url_workflow_creates_project_with_traceable_artifacts():
    tmp = tempfile.mkdtemp(prefix="api_")
    try:
        client, app_module = make_client(tmp)
        html = ("<html><head><title>Kaffee Guide</title></head><body><article>"
                + "".join(f"<p>Guter Kaffee braucht frische Bohnen und Zeit, Punkt {i}. "
                          f"Die Mahlung entscheidet stark ueber den Geschmack beim Kaffee.</p>"
                          for i in range(8)) + "</article></body></html>").encode()

        def resolver(host, port, type=None):
            return [(socket.AF_INET, socket.SOCK_STREAM, 6, "", ("93.184.216.34", port))]

        def transport(scheme, host, ip, port, path, headers, timeout, max_bytes, deadline):
            return 200, {"content-type": "text/html; charset=utf-8"}, html
        app_module.studio.service.fetch_kwargs = {"resolver": resolver, "transport": transport}
        pid = _create(client, workflow="article_url", url="https://blog.example.com/kaffee")
        p = _project(client, pid)
        assert p["status"] == "ready" and p["title"] == "Kaffee Guide" and len(p["scenes"]) >= 3
        assert p["source"]["meta"]["word_count"] > 50
        names = {a["name"] for a in client.get(f"/api/studio/projects/{pid}/artifacts").json()["artifacts"]}
        assert {"fetch.json", "extraction.json", "script.json"} <= names
        fetch = client.get(f"/api/studio/projects/{pid}/artifacts/fetch.json").json()
        assert fetch["final_url"] == "https://blog.example.com/kaffee" and fetch["bytes"] == len(html)
        assert "Bohnen" in client.get(f"/api/studio/projects/{pid}/artifacts/extraction.json").json()["text"]
        r = client.get(f"/api/studio/projects/{pid}/artifacts/..%2Fproject.json")
        assert r.status_code in (400, 404)
        # Website-Review + Social nutzen denselben sicheren Pfad
        for wf in ("website_review", "social_url"):
            assert _project(client, _create(client, workflow=wf, url="https://example.com/x"))["status"] == "ready"
    finally:
        clear_env()
        shutil.rmtree(tmp, ignore_errors=True)


def test_url_failure_is_user_friendly_and_retryable():
    tmp = tempfile.mkdtemp(prefix="api_")
    try:
        client, app_module = make_client(tmp)
        state = {"fail": True}

        def resolver(host, port, type=None):
            return [(socket.AF_INET, socket.SOCK_STREAM, 6, "", ("93.184.216.34", port))]

        def transport(scheme, host, ip, port, path, headers, timeout, max_bytes, deadline):
            if state["fail"]:
                raise ConnectionResetError()
            return 200, {"content-type": "text/html"}, (
                b"<p>Erster Satz der Seite mit Inhalt. Zweiter Satz der Seite mit Inhalt. "
                b"Dritter Satz der Seite mit Inhalt.</p>")
        app_module.studio.service.fetch_kwargs = {"resolver": resolver, "transport": transport}
        r = client.post("/api/studio/projects", json={"workflow": "article_url",
                                                      "url": "https://example.com/a"}).json()
        task = wait_task(client, r["task_id"])
        assert task["status"] == "failed" and task["error"]["code"] == "url_unreachable"
        p = _project(client, r["project"]["id"])
        assert p["status"] == "failed" and p["status_error"]["code"] == "url_unreachable"
        assert "abgerufen" in p["status_error"]["message"]
        state["fail"] = False
        rr = client.post(f"/api/studio/tasks/{r['task_id']}/retry")
        assert rr.status_code == 202
        task = wait_task(client, r["task_id"])
        assert task["status"] == "succeeded" and task["attempts"] == 2
        assert _project(client, r["project"]["id"])["status"] == "ready"
        assert _err(client.post(f"/api/studio/tasks/{r['task_id']}/retry")) == "task_not_retryable"
    finally:
        clear_env()
        shutil.rmtree(tmp, ignore_errors=True)


def test_pdf_upload_types_limits_and_workflow():
    tmp = tempfile.mkdtemp(prefix="api_")
    try:
        client, _ = make_client(tmp, CLIPFORGE_STUDIO_MAX_PDF_MB=1)
        r = client.post("/api/studio/projects", json={"workflow": "pdf"}).json()
        pid = r["project"]["id"]
        assert r["needs_upload"] and r["task_id"] is None
        assert _err(client.post(f"/api/studio/projects/{pid}/ingest")) == "source_missing"
        up = _upload(client, pid, "evil.exe", b"MZ")
        assert up.status_code == 415 and _err(up) == "file_type_not_allowed"
        assert _err(_upload(client, pid, "clip.mp4", b"x")) == "file_type_not_allowed"
        fake = _upload(client, pid, "fake.pdf", b"<html>not a pdf</html>")
        assert fake.status_code == 415 and _err(fake) == "file_unreadable"
        big = _upload(client, pid, "big.pdf", b"%PDF-" + b"0" * (2 * 1024 * 1024))
        assert big.status_code == 413 and _err(big) == "file_too_large"
        assert _err(_upload(client, pid, "leer.pdf", b"")) == "file_empty"
        assert os.listdir(os.path.join(tmp, "studio", "projects", pid, "source")) == []
        pdf = make_pdf([f"Local video tools keep every file on your machine, point {i}."
                        for i in range(1, 12)] + ["Why does that matter for small teams?"])
        ok = _upload(client, pid, "../../../Report Q3.pdf", pdf)
        assert ok.status_code == 200 and ok.json()["file"] == "source.pdf"
        assert ok.json()["original_name"] == "Report_Q3.pdf"
        assert os.listdir(os.path.join(tmp, "studio", "projects", pid, "source")) == ["source.pdf"]
        task = wait_task(client, client.post(f"/api/studio/projects/{pid}/ingest").json()["task"]["id"])
        assert task["status"] == "succeeded", task
        p = _project(client, pid)
        assert p["status"] == "ready" and len(p["scenes"]) >= 3 and p["source"]["meta"]["pages"] == 1
        ext = client.get(f"/api/studio/projects/{pid}/artifacts/extraction.json").json()
        assert ext["source"] == "pdf" and "your machine" in ext["text"]
        # textloses PDF → klarer Fehler am Projekt
        from pypdf import PdfWriter
        buf = io.BytesIO()
        w = PdfWriter()
        w.add_blank_page(width=100, height=100)
        w.write(buf)
        pid2 = client.post("/api/studio/projects", json={"workflow": "pdf"}).json()["project"]["id"]
        _upload(client, pid2, "scan.pdf", buf.getvalue())
        task = wait_task(client, client.post(f"/api/studio/projects/{pid2}/ingest").json()["task"]["id"])
        assert task["status"] == "failed" and task["error"]["code"] == "pdf_no_text"
        assert _project(client, pid2)["status_error"]["code"] == "pdf_no_text"
    finally:
        clear_env("CLIPFORGE_STUDIO_MAX_PDF_MB")
        shutil.rmtree(tmp, ignore_errors=True)


def test_media_upload_types_sniffing_and_path_traversal():
    tmp = tempfile.mkdtemp(prefix="api_")
    try:
        client, _ = make_client(tmp)
        pid = _create(client, workflow="script", script=SCRIPT)
        png = open(make_png(os.path.join(tmp, "a.png")), "rb").read()
        mp4 = open(make_video(os.path.join(tmp, "a.mp4"), 1.0), "rb").read()
        ok = _upload(client, pid, "../../Mein Bild.png", png, path="media")
        assert ok.status_code == 201 and ok.json()["kind"] == "image"
        name = ok.json()["name"]
        assert "/" not in name and ".." not in name and name.endswith(".png")
        vid = _upload(client, pid, "clip.mp4", mp4, path="media").json()
        assert vid["kind"] == "video" and vid["duration"] > 0.5
        assert _err(_upload(client, pid, "x.svg", b"<svg/>", path="media")) == "file_type_not_allowed"
        assert _err(_upload(client, pid, "x.html", b"<html>", path="media")) == "file_type_not_allowed"
        assert _err(_upload(client, pid, "fake.png", b"GIF89a....", path="media")) == "file_unreadable"
        assert _err(_upload(client, pid, "fake.mp4", b"not a video", path="media")) == "file_unreadable"
        listed = {m["name"] for m in client.get(f"/api/studio/projects/{pid}/media").json()["media"]}
        assert listed == {name, vid["name"]}  # abgelehnte Dateien wurden entfernt
        assert client.get(f"/api/studio/projects/{pid}/media/{name}").status_code == 200
        for evil in ("..%2Fproject.json", "%2e%2e%2f%2e%2e%2fidempotency.json", "nope.png"):
            assert client.get(f"/api/studio/projects/{pid}/media/{evil}").status_code in (400, 404)
        # Medien pro Szene ersetzen → gespeichert; verwendete Datei nicht löschbar
        p = _project(client, pid)
        scenes = p["scenes"]
        scenes[0]["visual"] = {"mode": "media", "media": name}
        r = client.patch(f"/api/studio/projects/{pid}", json={"expected_version": p["version"],
                                                              "scenes": scenes})
        assert r.status_code == 200 and r.json()["project"]["scenes"][0]["visual"]["media"] == name
        assert _err(client.delete(f"/api/studio/projects/{pid}/media/{name}")) == "media_in_use"
        assert client.delete(f"/api/studio/projects/{pid}/media/{vid['name']}").status_code == 200
    finally:
        clear_env()
        shutil.rmtree(tmp, ignore_errors=True)


def test_audio_workflow_uses_transcript_with_real_word_timings():
    tmp = tempfile.mkdtemp(prefix="api_")
    try:
        client, app_module = make_client(tmp)
        calls = []

        def fake_whisper(path, settings):
            calls.append(path)
            segs = []
            for i in range(4):
                t = i * 0.7
                segs.append(TranscriptSegment(
                    text=f"Satz Nummer {i}", start=t, end=t + 0.6,
                    words=[Word("Satz", t, t + 0.2), Word("Nummer", t + 0.2, t + 0.4),
                           Word(str(i), t + 0.4, t + 0.6)]))
            return Transcript(language="de", duration=3.0, segments=segs)
        app_module.studio.service.transcriber = fake_whisper
        pid = client.post("/api/studio/projects", json={"workflow": "audio"}).json()["project"]["id"]
        wav = open(make_tone_wav(os.path.join(tmp, "talk.wav"), 3.0), "rb").read()
        assert _err(_upload(client, pid, "talk.txt", b"hi")) == "file_type_not_allowed"
        assert _err(_upload(client, pid, "talk.wav", b"RIFFbroken")) == "file_unreadable"
        up = _upload(client, pid, "talk.wav", wav)
        assert up.status_code == 200 and up.json()["duration"] > 2.5
        task = wait_task(client, client.post(f"/api/studio/projects/{pid}/ingest").json()["task"]["id"])
        assert task["status"] == "succeeded", task
        assert len(calls) == 1 and calls[0].endswith("source.wav")
        p = _project(client, pid)
        assert p["source"]["audio_file"] == "source.wav"
        assert all("audio_source" in s and s["words"] for s in p["scenes"])
        assert p["scenes"][0]["words"][0] == {"text": "Satz", "start": 0.0, "end": 0.2}
        tr = client.get(f"/api/studio/projects/{pid}/artifacts/transcript.json").json()
        assert len(tr["segments"]) == 4
        task = wait_task(client, client.post(f"/api/studio/projects/{pid}/render",
                                             json={"mode": "preview"}).json()["task"]["id"])
        assert task["status"] == "succeeded", task
        report = client.get(f"/api/studio/projects/{pid}/renders").json()["renders"][0]
        assert report["word_timing"] == ["transcribed"] and report["has_audio"]
        assert report["captions"]["applied_mode"] == "karaoke"
        # ohne Whisper: verständlicher Fehler statt Crash; Transkript-Upload als Ausweg
        def no_whisper(path, settings):
            raise RuntimeError("faster-whisper ist nicht installiert")
        app_module.studio.service.transcriber = no_whisper
        pid2 = client.post("/api/studio/projects", json={"workflow": "audio"}).json()["project"]["id"]
        _upload(client, pid2, "talk.wav", wav)
        task = wait_task(client, client.post(f"/api/studio/projects/{pid2}/ingest").json()["task"]["id"])
        assert task["error"]["code"] == "transcription_unavailable"
        assert _err(_upload(client, pid2, "t.json", b"{kaputt", kind="transcript")) == "file_unreadable"
        import json
        good = json.dumps({"language": "de", "duration": 2, "segments": [
            {"text": "Hallo zusammen", "start": 0, "end": 1.0,
             "words": [{"text": "Hallo", "start": 0, "end": 0.5},
                       {"text": "zusammen", "start": 0.5, "end": 1.0}]}]}).encode()
        assert _upload(client, pid2, "t.json", good, kind="transcript").status_code == 200
        task = wait_task(client, client.post(f"/api/studio/projects/{pid2}/ingest").json()["task"]["id"])
        assert task["status"] == "succeeded", task
        assert _project(client, pid2)["scenes"][0]["text"] == "Hallo zusammen"
    finally:
        clear_env()
        shutil.rmtree(tmp, ignore_errors=True)


def test_editor_persistence_conflicts_and_render_restart():
    tmp = tempfile.mkdtemp(prefix="api_")
    try:
        client, _ = make_client(tmp)
        pid = _create(client, workflow="script", script=SCRIPT, voice={"provider": "mock"},
                      resolution="720p")
        p = _project(client, pid)
        v = p["version"]
        scenes = list(reversed(p["scenes"]))
        scenes[0] = {**scenes[0], "text": "Neuer Hook Text", "voice_text": "Anders gesprochen",
                     "visual_prompt": "Kaffeetasse im Morgenlicht", "duration": 5.5}
        patch = {"expected_version": v, "scenes": scenes, "title": "Editiert",
                 "captions": {"style": "bold", "use_brand": False},
                 "music": {"track": None, "volume": 0.4, "ducking": False}}
        r = client.patch(f"/api/studio/projects/{pid}", json=patch)
        assert r.status_code == 200, r.text
        saved = _project(client, pid)  # frisch vom Backend geladen
        assert saved["version"] == v + 1 and saved["title"] == "Editiert"
        assert [s["id"] for s in saved["scenes"]] == [s["id"] for s in scenes]
        assert saved["scenes"][0]["text"] == "Neuer Hook Text"
        assert saved["scenes"][0]["voice_text"] == "Anders gesprochen"
        assert saved["scenes"][0]["visual_prompt"] == "Kaffeetasse im Morgenlicht"
        assert saved["scenes"][0]["duration"] == 5.5
        assert saved["captions"] == {"style": "bold", "use_brand": False}
        assert saved["music"]["volume"] == 0.4 and saved["music"]["ducking"] is False
        stale = client.patch(f"/api/studio/projects/{pid}", json={"expected_version": v, "title": "Alt"})
        assert stale.status_code == 409 and _err(stale) == "version_conflict"
        assert stale.json()["detail"]["details"]["current_version"] == v + 1
        assert client.patch(f"/api/studio/projects/{pid}", json={"title": "x"}).status_code == 422
        # Szenen-API (Agenten/CLI): Reihenfolge + Duplizieren + Löschen
        order = [s["id"] for s in saved["scenes"]][::-1]
        r = client.post(f"/api/studio/projects/{pid}/scenes",
                        json={"expected_version": v + 1, "op": "reorder", "payload": {"order": order}})
        assert [s["id"] for s in r.json()["project"]["scenes"]] == order
        r = client.post(f"/api/studio/projects/{pid}/scenes",
                        json={"expected_version": v + 2, "op": "duplicate", "scene_id": order[0]})
        assert len(r.json()["project"]["scenes"]) == len(order) + 1
        r = client.post(f"/api/studio/projects/{pid}/scenes",
                        json={"expected_version": v + 3, "op": "delete", "scene_id": order[0]})
        assert r.status_code == 200
        # Preview + finaler Render; Render lässt sich neu starten
        est = client.get(f"/api/studio/projects/{pid}/estimate").json()
        assert est["total_usd"] == 0 and est["is_estimate"]
        t1 = wait_task(client, client.post(f"/api/studio/projects/{pid}/render",
                                           json={"mode": "preview"}).json()["task"]["id"])
        t2 = wait_task(client, client.post(f"/api/studio/projects/{pid}/render",
                                           json={"mode": "final"}).json()["task"]["id"])
        t3 = wait_task(client, client.post(f"/api/studio/projects/{pid}/render",
                                           json={"mode": "final"}).json()["task"]["id"])
        assert t1["status"] == t2["status"] == t3["status"] == "succeeded"
        assert t2["id"] != t3["id"]
        renders = client.get(f"/api/studio/projects/{pid}/renders").json()["renders"]
        assert [r["mode"] for r in renders].count("final") == 2
        final = next(r for r in renders if r["mode"] == "final")
        resp = client.get(f"/api/studio/projects/{pid}/renders/{final['render_id']}/file")
        assert resp.status_code == 200 and resp.headers["content-type"] == "video/mp4"
        out = os.path.join(tmp, "dl.mp4")
        open(out, "wb").write(resp.content)
        video = next(s for s in ffprobe(out)["streams"] if s["codec_type"] == "video")
        assert (video["width"], video["height"]) == (720, 1280)
        assert client.get(f"/api/studio/projects/{pid}/renders/ffffffffffff/file").status_code == 404
        assert client.get(f"/api/studio/projects/{pid}/renders/..%2F..%2Fx/file").status_code in (400, 404)
        # Versionen + Wiederherstellen
        versions = client.get(f"/api/studio/projects/{pid}/versions").json()["versions"]
        assert len(versions) >= 4
        r = client.post(f"/api/studio/projects/{pid}/versions/{v}/restore")
        assert r.status_code == 200 and r.json()["project"]["title"] != "Editiert"
    finally:
        clear_env()
        shutil.rmtree(tmp, ignore_errors=True)


def test_export_to_publishing_drafts_for_all_platforms_never_publishes():
    tmp = tempfile.mkdtemp(prefix="api_")
    try:
        client, _ = make_client(tmp)
        pid = _create(client, workflow="script", script=SCRIPT, voice={"provider": "mock"},
                      resolution="720p")
        assert _err(client.post(f"/api/studio/projects/{pid}/export", json={})) == "render_missing"
        prev = wait_task(client, client.post(f"/api/studio/projects/{pid}/render",
                                             json={"mode": "preview"}).json()["task"]["id"])
        r = client.post(f"/api/studio/projects/{pid}/export",
                        json={"render_id": prev["result"]["render_id"]})
        assert r.status_code == 409 and _err(r) == "render_not_final"
        wait_task(client, client.post(f"/api/studio/projects/{pid}/render",
                                      json={"mode": "final"}).json()["task"]["id"])
        exp = client.post(f"/api/studio/projects/{pid}/export", json={}).json()
        again = client.post(f"/api/studio/projects/{pid}/export", json={}).json()
        assert exp["job_id"] == again["job_id"] and again["already_exported"]  # idempotent
        job = client.get(f"/api/jobs/{exp['job_id']}").json()
        assert job["status"] == "completed"
        assert len([j for j in client.get("/api/jobs").json()["jobs"]]) == 1
        clips = client.get(f"/api/jobs/{exp['job_id']}/clips").json()
        assert clips["studio"]["project_id"] == pid and "KEINE Garantie" in clips["disclaimer"]
        assert client.get(f"/api/jobs/{exp['job_id']}/clips/1/preview").status_code == 200
        for platform in ("youtube_shorts", "tiktok", "instagram_reels", "x"):
            d = client.post(f"/api/jobs/{exp['job_id']}/publishing",
                            json={"platform": platform, "source_type": "auto_clip",
                                  "source_clip_index": 1,
                                  "scheduled_at": "2030-01-01T10:00:00+00:00"})
            assert d.status_code == 200, d.text
            draft = d.json()
            assert draft["status"] == "draft" and draft["published_at"] is None
            assert draft["external_post_id"] is None
            if platform == "x":
                assert len(draft["caption"]) <= 280
            pack = client.get(f"/api/jobs/{exp['job_id']}/publishing/{draft['publishing_id']}/pack.zip")
            assert pack.status_code == 200 and pack.content[:2] == b"PK"  # Export-Fallback
        bad = client.post(f"/api/jobs/{exp['job_id']}/publishing",
                          json={"platform": "facebook", "source_type": "auto_clip",
                                "source_clip_index": 1})
        assert bad.status_code == 400
        states = client.get("/api/studio/publishing/drafts").json()["drafts"]
        assert len(states) == 4 and {s["state"] for s in states} == {"not_connected"}
        assert all(s["published_at"] is None for s in states)
        assert _project(client, pid)["exports"][0]["job_id"] == exp["job_id"]
    finally:
        clear_env()
        shutil.rmtree(tmp, ignore_errors=True)


def test_longform_and_podcast_reuse_shorts_pipeline_and_job_as_source():
    tmp = tempfile.mkdtemp(prefix="api_")
    try:
        client, _ = make_client(tmp)
        here = os.path.dirname(os.path.abspath(__file__))
        transcript = open(os.path.join(here, "..", "testdata", "transcript.json"), "rb").read()
        import json
        total = json.loads(transcript)["duration"]
        video = make_video(os.path.join(tmp, "long.mp4"), min(float(total) + 1, 200), "320x180")
        pid = client.post("/api/studio/projects", json={"workflow": "longform"}).json()["project"]["id"]
        assert _err(_upload(client, pid, "a.wav", b"RIFF")) == "file_type_not_allowed"
        assert _upload(client, pid, "long.mp4", open(video, "rb").read()).status_code == 200
        assert _upload(client, pid, "t.json", transcript, kind="transcript").status_code == 200
        task = wait_task(client, client.post(f"/api/studio/projects/{pid}/ingest").json()["task"]["id"])
        assert task["status"] == "succeeded", task
        job_id = _project(client, pid)["linked_job_id"]
        assert job_id == task["result"]["linked_job_id"]
        import time
        for _ in range(600):
            job = client.get(f"/api/jobs/{job_id}").json()
            if job["status"] not in ("queued", "processing"):
                break
            time.sleep(0.2)
        assert job["status"] == "completed", job.get("error")
        assert job["result"]["clip_count"] >= 1
        r = client.post(f"/api/studio/projects/{pid}/render", json={"mode": "final"})
        assert r.status_code == 409 and _err(r) == "render_not_applicable"
        # Podcast als reines Audio → wird für die Pipeline in ein Video gewandelt
        pid2 = client.post("/api/studio/projects", json={"workflow": "podcast"}).json()["project"]["id"]
        wav = make_tone_wav(os.path.join(tmp, "pod.wav"), min(float(total) + 1, 200))
        assert _upload(client, pid2, "pod.wav", open(wav, "rb").read()).status_code == 200
        _upload(client, pid2, "t.json", transcript, kind="transcript")
        task = wait_task(client, client.post(f"/api/studio/projects/{pid2}/ingest").json()["task"]["id"])
        assert task["status"] == "succeeded", task
        job2 = _project(client, pid2)["linked_job_id"]
        for _ in range(600):
            j2 = client.get(f"/api/jobs/{job2}").json()
            if j2["status"] not in ("queued", "processing"):
                break
            time.sleep(0.2)
        assert j2["status"] == "completed", j2.get("error")
        # bestehender Job als Studio-Quelle
        pid3 = _create(client, workflow="job", job_id=job_id)
        p3 = _project(client, pid3)
        assert p3["status"] == "ready" and len(p3["scenes"]) >= 2
        ext = client.get(f"/api/studio/projects/{pid3}/artifacts/extraction.json").json()
        assert ext["source"] == "job" and ext["job_id"] == job_id
    finally:
        clear_env()
        shutil.rmtree(tmp, ignore_errors=True)


def test_media_workflow_voice_preview_captions_and_music_library():
    tmp = tempfile.mkdtemp(prefix="api_")
    try:
        client, _ = make_client(tmp)
        pid = client.post("/api/studio/projects", json={
            "workflow": "media", "prompt": "Erstes Bild\nZweites Bild"}).json()["project"]["id"]
        assert _err(client.post(f"/api/studio/projects/{pid}/ingest")) == "source_missing"
        png = open(make_png(os.path.join(tmp, "a.png")), "rb").read()
        for n in ("eins.png", "zwei.png"):
            _upload(client, pid, n, png, path="media")
        task = wait_task(client, client.post(f"/api/studio/projects/{pid}/ingest").json()["task"]["id"])
        assert task["status"] == "succeeded", task
        p = _project(client, pid)
        assert [s["visual"]["mode"] for s in p["scenes"]] == ["media", "media"]
        assert [s["text"] for s in p["scenes"]] == ["Erstes Bild", "Zweites Bild"]
        # Voice Preview: Mock lokal; unbekannter/unkonfigurierter Provider sauber abgelehnt
        r = client.post("/api/studio/voices/preview", json={"language": "en", "provider": "mock"})
        assert r.status_code == 200 and r.headers["content-type"] == "audio/mpeg" and len(r.content) > 500
        r = client.post("/api/studio/voices/preview", json={"provider": "elevenlabs"})
        assert r.status_code == 409 and _err(r) == "provider_not_configured"
        assert _err(client.post("/api/studio/voices/preview", json={"provider": "nope"})) == "provider_unknown"
        voices = client.get("/api/studio/voices?language=en&tone=calm").json()
        assert voices["language"] == "en" and voices["auto_selection"]["provider"]
        # Caption-Vorschau für alle Stile
        styles = [s["id"] for s in client.get("/api/studio/caption-styles").json()["styles"]]
        assert styles == ["minimal", "bold", "karaoke", "dynamic", "none"]
        for style in styles:
            r = client.get(f"/api/studio/caption-preview?style={style}&aspect_ratio=16:9&text=Hallo%20Welt")
            assert r.status_code == 200 and r.content[:8] == b"\x89PNG\r\n\x1a\n", style
        assert _err(client.get("/api/studio/caption-preview?style=comic")) == "validation_error"
        # Musikbibliothek
        click = open(make_click_wav(os.path.join(tmp, "c.wav"), 6.0, 120.0), "rb").read()
        up = client.post("/api/studio/music", files={"file": ("../Beat 120.wav", io.BytesIO(click))})
        assert up.status_code == 200 and up.json()["id"] == "Beat_120.wav"
        assert _err(client.post("/api/studio/music", files={"file": ("x.exe", io.BytesIO(b"MZ"))})) == "file_type_not_allowed"
        assert _err(client.post("/api/studio/music", files={"file": ("x.mp3", io.BytesIO(b"nope"))})) == "file_unreadable"
        assert [t["id"] for t in client.get("/api/studio/music").json()["tracks"]] == ["Beat_120.wav"]
        assert abs(client.get("/api/studio/music/Beat_120.wav/beats").json()["bpm"] - 120) < 3
        assert client.get("/api/studio/music/..%2F..%2Fidempotency.json/file").status_code in (400, 404)
        r = client.patch(f"/api/studio/projects/{pid}", json={
            "expected_version": p["version"],
            "music": {"track": "library:Beat_120.wav", "volume": 0.3, "ducking": True,
                      "beat_sync": True}})
        assert r.status_code == 200
        r = client.patch(f"/api/studio/projects/{pid}", json={
            "expected_version": p["version"] + 1, "music": {"track": "library:nope.wav"}})
        assert r.status_code == 404 and _err(r) == "music_not_found"
        # Duplizieren + Löschen
        dup = client.post(f"/api/studio/projects/{pid}/duplicate", json={}).json()["project"]
        assert dup["id"] != pid and dup["lineage"]["parent_id"] == pid
        assert client.delete(f"/api/studio/projects/{dup['id']}").json() == {"deleted": True}
        assert client.get(f"/api/studio/projects/{dup['id']}").status_code == 404
    finally:
        clear_env()
        shutil.rmtree(tmp, ignore_errors=True)


if __name__ == "__main__":
    run_all(globals())
