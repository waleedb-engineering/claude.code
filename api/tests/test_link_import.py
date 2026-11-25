"""Link-Import (YouTube/Twitch) — Regeln, Schutz und Ablauf.

Der Download selbst wird hier NACHGEBILDET (``ydl_factory``): Diese Umgebung
lädt bewusst keine fremden Videos von YouTube/Twitch. Belegt ist damit die
Anbindung (Optionen, Grenzen, Abbruch, Chat-Übernahme, Analyse danach), nicht,
dass yt-dlp gegen die echten Plattformen funktioniert.
"""

from __future__ import annotations

import json
import os
import shutil

import pytest

from clipforge.studio.errors import StudioError
from studio_helpers import make_client, wait_task
from test_stream_intelligence import _stream


def _yt_chat() -> str:
    lines = []
    for i in range(120):
        n = 6 if 64 <= i <= 69 else 1
        for k in range(n):
            text = "KEKW no way" if n > 1 else "hallo"
            lines.append(json.dumps({"replayChatItemAction": {"videoOffsetTimeMsec": str(i * 1000 + k * 100),
                                                              "actions": [{"addChatItemAction": {"item": {
                                                                  "liveChatTextMessageRenderer": {
                                                                      "message": {"runs": [{"text": text}]},
                                                                      "authorName": {"simpleText": f"u{k}{i}"}}}}}]}}))
    return "\n".join(lines)


class FakeYDL:
    """Verhält sich wie yt_dlp.YoutubeDL an den Stellen, die ClipForge nutzt."""
    calls: list = []
    video: str = ""
    info: dict = {}
    with_chat = True
    fail: str | None = None
    cancel_after_hook = False

    def __init__(self, opts):
        self.opts = opts
        FakeYDL.calls.append(opts)

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False

    def extract_info(self, url, download=True):
        if FakeYDL.fail:
            raise RuntimeError(FakeYDL.fail)
        info = {"title": "Mein Stream", "uploader": "ich", "duration": 120, "was_live": True,
                **FakeYDL.info}
        reason = self.opts["match_filter"](info)
        if reason:
            return None
        dest = os.path.dirname(self.opts["outtmpl"]["default"])
        for hook in self.opts["progress_hooks"]:
            hook({"status": "downloading", "downloaded_bytes": 50, "total_bytes": 100})
        shutil.copyfile(FakeYDL.video, os.path.join(dest, "source.mp4"))
        if self.opts.get("writesubtitles") and FakeYDL.with_chat:
            with open(os.path.join(dest, "chat.live_chat.json"), "w") as fh:
                fh.write(_yt_chat())
        return info


@pytest.fixture()
def fake(tmp_path):
    FakeYDL.calls, FakeYDL.info, FakeYDL.fail, FakeYDL.with_chat = [], {}, None, True
    FakeYDL.video = _stream(str(tmp_path / "src.mp4"))
    return FakeYDL


def test_parse_link_accepts_only_youtube_and_twitch_videos():
    from clipforge.stream.link_import import parse_link
    assert parse_link("https://youtu.be/dQw4w9WgXcQ?t=5")["url"] == "https://www.youtube.com/watch?v=dQw4w9WgXcQ"
    assert parse_link("https://www.youtube.com/live/dQw4w9WgXcQ")["platform"] == "youtube"
    assert parse_link("https://www.twitch.tv/videos/2233445566")["kind"] == "vod"
    assert parse_link("https://www.twitch.tv/somechan/clip/FunnyClip-abc_123")["url"] == \
        "https://clips.twitch.tv/FunnyClip-abc_123"
    for bad in ("https://www.youtube.com/playlist?list=PL123", "https://www.twitch.tv/somechan",
                "http://127.0.0.1:8000/video.mp4", "file:///etc/passwd", "https://evil.example/watch?v=x",
                "https://www.youtube.com.evil.example/watch?v=dQw4w9WgXcQ", "javascript:alert(1)"):
        with pytest.raises(StudioError) as e:
            parse_link(bad)
        assert e.value.code == "link_invalid", bad


def test_ydl_options_are_locked_down(tmp_path):
    from clipforge.stream.link_import import ALLOWED_EXTRACTORS, ydl_options
    o = ydl_options(str(tmp_path), with_chat=True)
    assert o["allowed_extractors"] == ALLOWED_EXTRACTORS and "generic" not in str(o["allowed_extractors"])
    assert o["noplaylist"] is True and o["remote_components"] == []
    assert "height<=1080" in o["format"] and o["merge_output_format"] == "mp4"
    assert o["subtitleslangs"] == ["live_chat"]
    assert o["match_filter"]({"is_live": True}) and o["match_filter"]({"duration": 7 * 3600})
    assert o["match_filter"]({"duration": 3600}) is None


def test_disabled_by_default_and_enabling_needs_acknowledgement(tmp_path):
    client, _ = make_client(str(tmp_path))
    s = client.get("/api/studio/stream-link-import").json()
    assert s["enabled"] is False and "Nutzungsbedingungen" in s["terms"]
    r = client.post("/api/studio/stream-link-import/start",
                    json={"url": "https://youtu.be/dQw4w9WgXcQ", "rights_confirmed": True})
    assert r.status_code == 403 and r.json()["detail"]["code"] == "link_import_disabled"
    r = client.put("/api/studio/stream-link-import", json={"enabled": True})
    assert r.status_code == 400 and r.json()["detail"]["code"] == "terms_acknowledgement_required"
    s = client.put("/api/studio/stream-link-import", json={"enabled": True, "acknowledged": True}).json()
    assert s["enabled"] is True
    assert client.get("/api/studio/stream-link-import").json()["enabled"] is True
    assert client.put("/api/studio/stream-link-import", json={"enabled": False}).json()["enabled"] is False


def test_link_to_highlights_end_to_end_with_youtube_chat(tmp_path, fake):
    client, app_module = make_client(str(tmp_path))
    app_module.studio.streams.ydl_factory = fake
    client.put("/api/studio/stream-link-import", json={"enabled": True, "acknowledged": True})
    r = client.post("/api/studio/stream-link-import/start",
                    json={"url": "https://youtu.be/dQw4w9WgXcQ", "rights_confirmed": False})
    assert r.status_code == 400 and r.json()["detail"]["code"] == "rights_confirmation_required"
    r = client.post("/api/studio/stream-link-import/start",
                    json={"url": "https://youtu.be/dQw4w9WgXcQ", "rights_confirmed": True,
                          "analyze": {"transcribe": False, "max_clips": 3, "min_len": 8}})
    assert r.status_code == 202
    sid, tid = r.json()["stream"]["id"], r.json()["task"]["id"]
    t = wait_task(client, tid)
    assert t["status"] == "succeeded", t
    assert any("Download 50 %" in m for m in t["progress"])
    assert "Chat-Replay übernommen" in t["result"]["chat"]
    got = client.get(f"/api/studio/streams/{sid}").json()
    meta, analysis = got["stream"], got["analysis"]
    assert meta["title"] == "Mein Stream" and meta["status"] == "analyzed"
    assert meta["source_link"]["platform"] == "youtube" and meta["source_link"]["imported_at"]
    assert meta["rights"]["confirmed"] is True and meta["rights"]["verified"] is False
    assert meta["chat"]["format"] == "youtube_live_chat" and meta["video"]["duration"] > 100
    # das Ereignis bei 60–70 s (Bildwechsel, lauter Ton, Chat-Welle) wird gefunden
    assert any(55 <= h["t"] <= 75 for h in analysis["highlights"]), analysis["highlights"]
    assert not any(n.startswith("chat") for n in os.listdir(os.path.join(
        str(tmp_path), "studio", "streams", sid)) if n != "chat.json")   # Rohdatei aufgeräumt
    # Optionen an yt-dlp: nur erlaubte Extraktoren, Chat nur bei YouTube
    assert fake.calls[-1]["writesubtitles"] is True


def test_rejections_failures_and_twitch_without_chat(tmp_path, fake):
    client, app_module = make_client(str(tmp_path))
    app_module.studio.streams.ydl_factory = fake
    client.put("/api/studio/stream-link-import", json={"enabled": True, "acknowledged": True})

    def start(url, **kw):
        r = client.post("/api/studio/stream-link-import/start",
                        json={"url": url, "rights_confirmed": True, "analyze": None, **kw})
        assert r.status_code == 202, r.text
        return r.json()["stream"]["id"], wait_task(client, r.json()["task"]["id"])

    sid, t = start("https://www.twitch.tv/videos/123456789")
    assert t["status"] == "succeeded" and t["result"]["chat"] == "kein Chat-Replay"
    assert fake.calls[-1]["writesubtitles"] is False
    assert client.get(f"/api/studio/streams/{sid}").json()["stream"]["status"] == "ready"
    # laufender Live-Stream → abgelehnt, keine Datei
    fake.info = {"is_live": True}
    sid, t = start("https://youtu.be/dQw4w9WgXcQ")
    assert t["status"] == "failed" and t["error"]["code"] == "link_rejected"
    meta = client.get(f"/api/studio/streams/{sid}").json()["stream"]
    assert meta["status"] == "failed" and meta["video"] is None
    # privates Video → verständliche Meldung
    fake.info, fake.fail = {}, "ERROR: [youtube] x: Private video. Sign in if you've been granted access"
    sid, t = start("https://youtu.be/dQw4w9WgXcQ")
    assert t["error"]["code"] == "link_download_failed" and "privat" in t["error"]["message"]


def test_cancel_removes_partial_download(tmp_path, fake):
    from clipforge.stream import link_import
    os.environ["CLIPFORGE_STUDIO_DIR"] = str(tmp_path / "studio")
    os.makedirs(tmp_path / "studio", exist_ok=True)
    link_import.set_enabled(True, True, None)
    dest = tmp_path / "dl"
    with pytest.raises(StudioError) as e:
        link_import.download("https://youtu.be/dQw4w9WgXcQ", str(dest), should_cancel=lambda: True,
                             ydl_factory=fake)
    assert e.value.code == "cancelled" and not list(dest.glob("source.*"))
    os.environ.pop("CLIPFORGE_STUDIO_DIR", None)
