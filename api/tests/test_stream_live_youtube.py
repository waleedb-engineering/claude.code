"""YouTube-Live-Chat über die Data API v3 — gegen einen lokalen Server, der die
API-Antworten NACHBILDET (Format laut Google-Doku). Ein Test gegen die echte API
braucht einen API-Schlüssel und einen laufenden öffentlichen Live-Stream.
Außerdem: Warteschlangen-Grenzen im Live-Modus."""

import json
import os
import subprocess
import threading
import time
from http.server import BaseHTTPRequestHandler, HTTPServer
from urllib.parse import parse_qs, urlparse

import pytest

from clipforge.stream.live import LiveSession, YouTubeLiveChatReader, youtube_video_id


class _FakeYT(BaseHTTPRequestHandler):
    pages: list = []
    calls: list = []
    fail: str | None = None

    def log_message(self, *a):
        pass

    def _send(self, code, obj):
        body = json.dumps(obj).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        u = urlparse(self.path)
        q = parse_qs(u.query)
        _FakeYT.calls.append((u.path, q))
        if q.get("key") != ["test-key"]:
            return self._send(400, {"error": {"errors": [{"reason": "keyInvalid"}]}})
        if u.path.endswith("/videos"):
            return self._send(200, {"items": [{"liveStreamingDetails": {"activeLiveChatId": "CHAT1"}}]})
        if u.path.endswith("/liveChat/messages"):
            if _FakeYT.fail:
                return self._send(403, {"error": {"errors": [{"reason": _FakeYT.fail}]}})
            idx = int(q.get("pageToken", ["0"])[0])
            items = _FakeYT.pages[idx] if idx < len(_FakeYT.pages) else []
            return self._send(200, {"items": items, "nextPageToken": str(idx + 1), "pollingIntervalMillis": 100})
        self._send(404, {})


def _msg(text, user, ts):
    iso = time.strftime("%Y-%m-%dT%H:%M:%S", time.gmtime(ts)) + f".{int((ts % 1) * 1000):03d}Z"
    return {"snippet": {"displayMessage": text, "publishedAt": iso}, "authorDetails": {"displayName": user}}


@pytest.fixture
def yt():
    srv = HTTPServer(("127.0.0.1", 0), _FakeYT)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    _FakeYT.calls, _FakeYT.fail = [], None
    yield f"http://127.0.0.1:{srv.server_port}/youtube/v3"
    srv.shutdown()


def test_video_id_parsing():
    assert youtube_video_id("https://www.youtube.com/watch?v=dQw4w9WgXcQ&t=3") == "dQw4w9WgXcQ"
    assert youtube_video_id("https://youtu.be/dQw4w9WgXcQ") == "dQw4w9WgXcQ"
    assert youtube_video_id("https://www.youtube.com/live/dQw4w9WgXcQ") == "dQw4w9WgXcQ"
    with pytest.raises(ValueError):
        youtube_video_id("https://evil.example/watch?v=dQw4w9WgXcQ")


def test_reader_polls_pages_with_timestamps(yt):
    now = time.time()
    _FakeYT.pages = [[_msg("hi", "a", now - 5), _msg("KEKW", "b", now - 4)], [_msg("no way", "c", now - 3)]]
    got = []
    r = YouTubeLiveChatReader("dQw4w9WgXcQ", lambda u, t, e, ts: got.append((u, t, ts)), "test-key",
                              api_base=yt, min_interval=1.0)
    r.start()
    deadline = time.time() + 10
    while len(got) < 3 and time.time() < deadline:
        time.sleep(0.1)
    r.stop()
    r.join(5)
    assert [g[1] for g in got] == ["hi", "KEKW", "no way"]
    assert abs(got[0][2] - (now - 5)) < 0.01                 # publishedAt, nicht Empfangszeit
    msgs = [c for c in _FakeYT.calls if c[0].endswith("/messages")]
    assert msgs[0][1]["liveChatId"] == ["CHAT1"] and msgs[1][1]["pageToken"] == ["1"]
    assert r.error is None and r.quota_estimate(1) == 18000   # 1 s Takt × 5 Einheiten


def test_reader_explains_quota_and_key_errors(yt):
    _FakeYT.fail = "quotaExceeded"
    r = YouTubeLiveChatReader("dQw4w9WgXcQ", lambda *a: None, "test-key", api_base=yt)
    r.run()
    assert "Kontingent" in r.error
    r = YouTubeLiveChatReader("dQw4w9WgXcQ", lambda *a: None, "wrong", api_base=yt)
    r.run()
    assert "Schlüssel" in r.error


def test_live_session_with_youtube_and_queue_limits(tmp_path, yt):
    t0 = time.time() - 400
    _FakeYT.pages = [[_msg("hallo", f"u{i}", t0 + 300 + i * 0.5) for i in range(60)] +
                     [_msg("KEKW", f"f{i}", t0 + 395 + i * 0.03) for i in range(60)]]
    s = LiveSession(str(tmp_path / "live"), channel=None, recording=None, recording_started_at=t0,
                    chat_delay=2, youtube="dQw4w9WgXcQ", max_pending=2,
                    yt_factory=lambda vid, cb: YouTubeLiveChatReader(vid, cb, "test-key", api_base=yt, min_interval=1))
    for r in s.readers():
        r.start()
    deadline = time.time() + 10
    while sum(s.counts.values()) < 120 and time.time() < deadline:
        time.sleep(0.1)
    s.tick(now=397)
    s.close()
    st = json.load(open(tmp_path / "live" / "live_state.json"))
    assert st["youtube"]["connected"] in (True, False) and st["youtube"]["polls"] >= 1
    assert st["events"] and st["events"][0]["status"] == "marked"
    # Warteschlangengrenze: mehr Ereignisse als Plätze → älteste übersprungen, nicht verloren
    s2 = LiveSession(str(tmp_path / "l2"), channel=None, recording=str(tmp_path / "rec.mkv"),
                     recording_started_at=time.time(), max_pending=2)
    for i in range(4):
        s2._enqueue({"id": f"l{i + 1:02d}", "start": 0, "end": 999, "status": "queued"})
    assert len(s2.queue) == 2 and len(s2.events) == 4
    assert s2.skipped == 2 and [e["status"] for e in s2.events[:2]] == ["skipped", "skipped"]
    s2.close()


def test_only_one_cut_per_tick(tmp_path):
    rec = str(tmp_path / "rec.mkv")
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-f", "lavfi", "-i", "testsrc=s=160x90:d=30:r=10",
                    "-c:v", "libx264", "-preset", "ultrafast", rec], check=True)
    s = LiveSession(str(tmp_path / "live"), channel=None, recording=rec, recording_started_at=time.time() - 60)
    for i in range(3):
        s._enqueue({"id": f"l{i + 1:02d}", "event": 5 + i, "start": 2 + i, "end": 6 + i, "status": "queued"})
    done = s.tick(now=60)
    assert len(done) == 1 and done[0]["status"] == "cut" and len(s.queue) == 2
    assert os.path.exists(tmp_path / "live" / "live_clips" / "l01.mp4")
    s.tick(now=62)
    s.tick(now=64)
    assert all(e["status"] == "cut" for e in s.events)
    s.close()


def test_api_requires_youtube_key(tmp_path):
    from studio_helpers import make_client
    client, _ = make_client(str(tmp_path))
    sid = client.post("/api/studio/streams", json={"title": "Y", "platform": "youtube",
                                                   "rights_confirmed": True}).json()["stream"]["id"]
    r = client.post(f"/api/studio/streams/{sid}/live", json={"youtube_video": "dQw4w9WgXcQ"})
    assert r.status_code == 409 and "API-Schlüssel" in r.text
    r = client.post(f"/api/studio/streams/{sid}/live", json={"youtube_video": "https://evil.example/x"})
    assert r.status_code in (400, 409)
