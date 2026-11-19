"""Live-Modus gegen einen lokalen IRC-Testserver (echtes Twitch-IRC-Protokoll,
kein Netz) und eine echte, wachsende MKV-Aufnahme."""

import os
import socket
import subprocess
import threading
import time

from clipforge.stream.live import LiveSession, SpikeDetector, TwitchChatReader


class FakeIRC(threading.Thread):
    def __init__(self):
        super().__init__(daemon=True)
        self.srv = socket.socket()
        self.srv.bind(("127.0.0.1", 0))
        self.srv.listen(1)
        self.port = self.srv.getsockname()[1]
        self.received, self.conn = [], None
        self.ready = threading.Event()

    def run(self):
        self.conn, _ = self.srv.accept()
        self.conn.settimeout(5)
        buf = ""
        while "JOIN" not in buf:
            buf += self.conn.recv(4096).decode()
        self.received = buf.split("\r\n")
        self.ready.set()

    def send(self, line):
        self.conn.sendall((line + "\r\n").encode())


def test_irc_reader_speaks_twitch_protocol():
    srv = FakeIRC()
    srv.start()
    got = []
    r = TwitchChatReader("Streamer_1", lambda u, t, e: got.append((u, t, e)),
                         host="127.0.0.1", port=srv.port, use_tls=False)
    r.start()
    assert srv.ready.wait(5)
    assert "JOIN #streamer_1" in srv.received and any(x.startswith("NICK justinfan") for x in srv.received)
    srv.send("PING :tmi.twitch.tv")
    srv.send("@display-name=Anna;emotes=25:0-4 :anna!anna@anna.tmi.twitch.tv PRIVMSG #streamer_1 :Kappa haha")
    srv.send(":bob!bob@bob.tmi.twitch.tv PRIVMSG #streamer_1 :no way")
    deadline = time.time() + 5
    while len(got) < 2 and time.time() < deadline:
        time.sleep(0.05)
    srv.conn.settimeout(2)
    pong = srv.conn.recv(1024).decode()
    r.stop()
    assert got[0] == ("Anna", "Kappa haha", ["Kappa"]) and got[1][1] == "no way"
    assert pong.startswith("PONG :tmi.twitch.tv")
    try:
        TwitchChatReader("böser kanal; DROP", lambda *a: None)
        raise AssertionError("ungültiger Kanal muss abgelehnt werden")
    except ValueError:
        pass


def test_spike_detector_baseline_and_cooldown():
    d = SpikeDetector(threshold=3.0, min_messages=8, cooldown=30)
    counts = {s: 1 for s in range(0, 300)}
    assert d.check(counts, 300) is None
    for s in range(301, 304):
        counts[s] = 15
    spike = d.check(counts, 303)
    assert spike and spike["messages"] == 45 and spike["baseline"] == 3
    assert d.check(counts, 304) is None  # Abklingzeit


def test_live_session_cuts_from_growing_recording(tmp_path):
    rec = str(tmp_path / "obs.mkv")
    # OBS-ähnliche Aufnahme, die während des Tests wächst (Echtzeit-Encoding)
    proc = subprocess.Popen(["ffmpeg", "-v", "error", "-y", "-re", "-f", "lavfi", "-i",
                             "testsrc=s=320x180:r=10:d=40", "-f", "lavfi", "-i", "sine=d=40",
                             "-c:v", "libx264", "-preset", "ultrafast", "-c:a", "aac", rec])
    t0 = time.time()
    fake_reader = {}

    def factory(ch, cb):
        class R:
            connected = threading.Event()
            error = None

            def start(self): self.connected.set()
            def stop(self): pass
        fake_reader["cb"] = cb
        return R()
    s = LiveSession(str(tmp_path / "live"), channel="streamer", recording=rec, recording_started_at=t0,
                    chat_delay=2, pre=3, post=2, reader_factory=factory)
    try:
        # Grundrate simulieren (über Zähler), dann echter Ausbruch über den Callback
        for sec in range(0, 4):
            s.counts[sec] = 1
        while time.time() - t0 < 6:
            time.sleep(0.2)
        for _ in range(30):
            fake_reader["cb"]("fan", "KEKW", [])
        now = time.time() - t0
        new = s.tick(now)
        assert s.events and s.events[0]["status"] in ("queued", "waiting_for_recording") and new == []
        deadline = time.time() + 30
        while not new and time.time() < deadline:
            time.sleep(1)
            new = s.tick()
        assert new and new[0]["status"] == "cut", s.events
        clip = os.path.join(str(tmp_path / "live"), "live_clips", new[0]["file"])
        assert os.path.getsize(clip) > 1000
        lines = open(os.path.join(str(tmp_path / "live"), "chat_live.jsonl")).read().splitlines()
        assert len(lines) == 30                       # jede Nachricht sofort gesichert
        assert os.path.exists(os.path.join(str(tmp_path / "live"), "live_state.json"))
    finally:
        s.close()
        proc.kill()


def test_live_api_start_stop_and_handover(tmp_path):
    from studio_helpers import clear_env, make_client, wait_task
    client, app_module = make_client(str(tmp_path))
    svc = app_module.studio.streams
    svc.live_interval = 0.2
    cbs = {}

    def factory(ch, cb):
        class R:
            connected = threading.Event()
            error = None
            def start(self): self.connected.set()
            def stop(self): pass
        cbs["cb"] = cb
        return R()
    svc.reader_factory = factory
    try:
        sid = client.post("/api/studio/streams", json={"title": "Live", "platform": "twitch",
                                                       "rights_confirmed": True}).json()["stream"]["id"]
        assert client.post(f"/api/studio/streams/{sid}/live", json={}).status_code == 400
        assert client.post(f"/api/studio/streams/{sid}/live", json={"channel": "a b"}).status_code == 400
        assert client.post(f"/api/studio/streams/{sid}/live",
                           json={"recording_path": "/nicht/da.mkv"}).status_code == 404
        task = client.post(f"/api/studio/streams/{sid}/live", json={"channel": "streamer"}).json()["task"]
        assert client.post(f"/api/studio/streams/{sid}/live", json={"channel": "streamer"}).status_code == 409
        deadline = time.time() + 5
        while "cb" not in cbs and time.time() < deadline:
            time.sleep(0.05)
        for i in range(5):
            cbs["cb"](f"u{i}", "hallo KEKW", [])
        time.sleep(0.6)
        st = client.get(f"/api/studio/streams/{sid}/live").json()
        assert st["state"]["messages"] == 5 and st["availability"]["twitch_chat"]["realtime"] is True
        client.post(f"/api/studio/tasks/{task['id']}/cancel")
        done = wait_task(client, task["id"])
        assert done["status"] == "canceled"
        meta = client.get(f"/api/studio/streams/{sid}").json()["stream"]
        assert meta["live"]["status"] == "stopped" and meta["chat"]["messages"] == 5
        assert meta["chat"]["format"] == "twitch_irc_live"
    finally:
        clear_env()
