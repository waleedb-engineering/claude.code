"""YouTube-Import: Link, öffentliche Metadaten, Rechtebestätigung, Untertitel,
Shorts-Pipeline. Es wird nie etwas von YouTube heruntergeladen."""

from __future__ import annotations

import io
import json
import os
import shutil
import socket
import tempfile
import time

from studio_helpers import clear_env, make_client, make_video, run_all, wait_task

from clipforge.studio import youtube_import as yt
from clipforge.studio.errors import StudioError

VID = "dQw4w9WgXcQ"


def _code(fn) -> str:
    try:
        fn()
    except StudioError as exc:
        return exc.code
    return "no_error"


def _fake(status=200, body=None, ctype="application/json", calls=None):
    def resolver(host, port, type=None):
        return [(socket.AF_INET, socket.SOCK_STREAM, 6, "", ("142.250.0.1", port))]

    def transport(scheme, host, ip, port, path, headers, timeout, max_bytes, deadline):
        if calls is not None:
            calls.append((host, path))
        return status, {"content-type": ctype}, body if body is not None else json.dumps({
            "title": "Mein Vortrag", "author_name": "Walids Kanal",
            "thumbnail_url": f"https://i.ytimg.com/vi/{VID}/hqdefault.jpg"}).encode()
    return {"resolver": resolver, "transport": transport}


def test_video_id_from_all_link_forms():
    for url in (f"https://www.youtube.com/watch?v={VID}", f"https://youtube.com/watch?v={VID}&t=42s",
                f"https://m.youtube.com/watch?feature=share&v={VID}", f"https://youtu.be/{VID}?si=abc",
                f"https://www.youtube.com/shorts/{VID}", f"https://www.youtube.com/embed/{VID}",
                f"https://www.youtube.com/live/{VID}", f"https://www.youtube-nocookie.com/embed/{VID}"):
        assert yt.video_id(url) == VID, url
    for bad in ("", "https://vimeo.com/123", f"https://evil.com/watch?v={VID}",
                f"https://youtube.com.evil.com/watch?v={VID}", "https://youtube.com/watch?v=kurz",
                f"ftp://youtube.com/watch?v={VID}", "https://www.youtube.com/@kanal",
                f"javascript:alert('{VID}')"):
        assert _code(lambda b=bad: yt.video_id(b)) == "youtube_url_invalid", bad


def test_metadata_via_oembed_only_and_honest_failures():
    calls = []
    meta = yt.fetch_metadata(VID, _fake(calls=calls))
    assert meta["title"] == "Mein Vortrag" and meta["author"] == "Walids Kanal"
    assert meta["thumbnail"].startswith("https://i.ytimg.com/") and meta["metadata_error"] is None
    assert calls == [("www.youtube.com", f"/oembed?format=json&url=https://www.youtube.com/watch?v={VID}")]
    evil = json.dumps({"title": "x" * 999, "thumbnail_url": "https://evil.example/t.jpg"}).encode()
    meta = yt.fetch_metadata(VID, _fake(body=evil))
    assert len(meta["title"]) == 200 and meta["thumbnail"] is None
    assert _code(lambda: yt.fetch_metadata(VID, _fake(status=404))) == "youtube_unavailable"
    meta = yt.fetch_metadata(VID, _fake(body=b"kein json"))
    assert meta["title"] is None and meta["metadata_error"] == "invalid_response"

    def down(*a, **k):
        raise ConnectionResetError()
    meta = yt.fetch_metadata(VID, {**_fake(), "transport": down})
    assert meta["metadata_error"] == "url_unreachable" and meta["title"] is None


def test_srt_and_vtt_subtitles_become_a_transcript():
    srt = ("1\n00:00:01,000 --> 00:00:03,000\nHallo <i>und</i> willkommen\n\n"
           "2\n00:00:03,500 --> 00:00:05,000\nzweite Zeile\n\n"
           "3\n00:00:05,000 --> 00:00:06,000\nzweite Zeile\n\nkaputt\n")
    data = yt.subtitles_to_transcript(srt, "de")
    assert [s["text"] for s in data["segments"]] == ["Hallo und willkommen", "zweite Zeile"]
    w = data["segments"][0]["words"]
    assert [x["text"] for x in w] == ["Hallo", "und", "willkommen"]
    assert w[0]["start"] == 1.0 and abs(w[-1]["end"] - 3.0) < 1e-6 and data["estimated_words"]
    vtt = ("﻿WEBVTT\n\nNOTE x\n\n00:01:02.500 --> 00:01:04.000 align:start\n"
           "<c.colorE5E5E5>Zeile</c> eins\n\n1:00:00.000 --> 1:00:01.250\nSpät\n")
    data = yt.subtitles_to_transcript(vtt)
    assert data["segments"][0]["start"] == 62.5 and data["segments"][0]["text"] == "Zeile eins"
    assert data["segments"][1]["start"] == 3600.0 and data["duration"] == 3601.25
    assert _code(lambda: yt.subtitles_to_transcript("WEBVTT\n\n")) == "subtitles_empty"


def test_youtube_project_needs_rights_and_own_upload_then_makes_shorts():
    tmp = tempfile.mkdtemp(prefix="yt_")
    try:
        client, app_module = make_client(tmp)
        calls = []
        app_module.studio.service.fetch_kwargs = _fake(calls=calls)
        post = lambda body: client.post("/api/studio/projects", json=body)  # noqa: E731
        r = post({"workflow": "youtube", "url": f"https://youtu.be/{VID}"})
        assert r.status_code == 400 and r.json()["detail"]["code"] == "rights_confirmation_required"
        r = post({"workflow": "youtube", "url": f"https://youtu.be/{VID}", "rights_confirmed": True})
        assert r.status_code == 201 and r.json()["needs_upload"] and r.json()["task_id"] is None
        p = r.json()["project"]
        pid = p["id"]
        assert p["source"]["url"] == f"https://www.youtube.com/watch?v={VID}"
        assert p["source"]["rights"]["confirmed"] and p["source"]["rights"]["verified"] is False
        assert client.post(f"/api/studio/projects/{pid}/ingest").json()["detail"]["code"] == "source_missing"
        assert calls == []                                           # vor dem Ingest kein Netzaufruf
        # eigenes Video + Untertitel aus YouTube Studio
        srt_lines = []
        for i in range(30):
            a, b = i * 2, i * 2 + 2
            srt_lines.append(f"{i+1}\n00:00:{a:02d},000 --> 00:00:{b:02d},000\n"
                             f"Das ist Satz Nummer {i} mit einer klaren Aussage.\n")
        video = make_video(os.path.join(tmp, "eigen.mp4"), 61, "320x180")
        up = lambda name, data, kind=None: client.post(  # noqa: E731
            f"/api/studio/projects/{pid}/source", files={"file": (name, io.BytesIO(data))},
            data={"kind": kind} if kind else {})
        assert up("x.pdf", b"%PDF-").status_code == 415                # nur Video
        assert up("eigen.mp4", open(video, "rb").read()).status_code == 200
        assert up("u.txt", b"x", "transcript").status_code == 415
        assert up("u.srt", "\n".join(srt_lines).encode(), "transcript").status_code == 200
        task = wait_task(client, client.post(f"/api/studio/projects/{pid}/ingest").json()["task"]["id"])
        assert task["status"] == "succeeded", task
        assert len(calls) == 1 and calls[0][1].startswith("/oembed")    # NUR Metadaten
        p = client.get(f"/api/studio/projects/{pid}").json()["project"]
        assert p["title"] == "Mein Vortrag" and p["source"]["meta"]["author"] == "Walids Kanal"
        art = client.get(f"/api/studio/projects/{pid}/artifacts/youtube.json").json()
        assert art["video_id"] == VID and art["rights"]["confirmed"]
        job_id = p["linked_job_id"]
        for _ in range(600):
            job = client.get(f"/api/jobs/{job_id}").json()
            if job["status"] not in ("queued", "processing"):
                break
            time.sleep(0.2)
        assert job["status"] == "completed", job.get("error")
        assert job["result"]["clip_count"] >= 1
        clips = client.get(f"/api/jobs/{job_id}/clips").json()["clips"]
        assert all(c.get("caption_info") for c in clips)             # Untertitel ergänzt
        assert "Satz Nummer" in clips[0]["text"]                     # aus den Untertiteln
    finally:
        clear_env()
        shutil.rmtree(tmp, ignore_errors=True)


def test_import_can_be_disabled_by_flag():
    tmp = tempfile.mkdtemp(prefix="yt_")
    try:
        client, _ = make_client(tmp, CLIPFORGE_FLAG_STUDIO_YOUTUBE_IMPORT="false")
        r = client.post("/api/studio/projects", json={
            "workflow": "youtube", "url": f"https://youtu.be/{VID}", "rights_confirmed": True})
        assert r.status_code == 403 and r.json()["detail"]["code"] == "feature_disabled"
    finally:
        clear_env("CLIPFORGE_FLAG_STUDIO_YOUTUBE_IMPORT")
        shutil.rmtree(tmp, ignore_errors=True)


if __name__ == "__main__":
    run_all(globals())
