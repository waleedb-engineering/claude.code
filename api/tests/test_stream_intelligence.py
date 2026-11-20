"""Stream Intelligence: Chat-Formate, Scoring, Grenzen, API-Ablauf mit echtem
FFmpeg-Render (synthetischer Stream mit lautem Ereignis + Chat-Ausbruch)."""

import json
import os
import random
import subprocess

import pytest

from clipforge.models import Transcript, TranscriptSegment, Word
from clipforge.stream import scoring
from clipforge.stream.chat import categorize, parse_chat, per_second
from studio_helpers import clear_env, make_client, wait_task


def _stream(path):
    """120 s: ruhig, bei 60–70 s Bildwechsel + lauter heller Ton, dann wieder ruhig."""
    subprocess.run([
        "ffmpeg", "-v", "error", "-y",
        "-f", "lavfi", "-i", "color=c=0x334455:s=320x180:d=60:r=10",
        "-f", "lavfi", "-i", "testsrc=s=320x180:d=10:r=10",
        "-f", "lavfi", "-i", "color=c=0x334455:s=320x180:d=50:r=10",
        "-f", "lavfi", "-i", "anoisesrc=c=pink:a=0.02:d=60",
        "-f", "lavfi", "-i", "sine=f=1800:d=10,volume=6",
        "-f", "lavfi", "-i", "anoisesrc=c=pink:a=0.02:d=50",
        "-filter_complex", "[0:v][3:a][1:v][4:a][2:v][5:a]concat=n=3:v=1:a=1[v][a]",
        "-map", "[v]", "-map", "[a]", "-c:v", "libx264", "-preset", "ultrafast", "-c:a", "aac", path],
        check=True)
    return path


def _twitch_chat():
    random.seed(7)
    comments = []
    for t in range(120):
        for _ in range(random.randint(0, 2)):
            comments.append({"content_offset_seconds": t + random.random(),
                             "commenter": {"display_name": f"u{random.randint(1, 40)}"},
                             "message": {"body": "hallo", "fragments": [{"text": "hallo"}]}})
    for i in range(80):
        body = random.choice(["KEKW", "no way", "CLIP IT", "LUL LUL"])
        comments.append({"content_offset_seconds": 65 + random.random() * 4,
                         "commenter": {"display_name": f"fan{i}"},
                         "message": {"body": body, "fragments": [{"text": body, "emoticon": {"id": "1"}}]}})
    return json.dumps({"video": {"length": 120}, "comments": comments}).encode()


def test_chat_formats():
    msgs, fmt = parse_chat(_twitch_chat(), "chat.json")
    assert fmt == "twitchdownloader" and len(msgs) > 100 and msgs == sorted(msgs, key=lambda m: m.t)
    yt = "\n".join(json.dumps({"replayChatItemAction": {"videoOffsetTimeMsec": str(1000 * i), "actions": [
        {"addChatItemAction": {"item": {"liveChatTextMessageRenderer": {
            "message": {"runs": [{"text": "lol "}, {"emoji": {"shortcuts": [":joy:"]}}]},
            "authorName": {"simpleText": "anna"}}}}}]}}) for i in range(3))
    m2, f2 = parse_chat(yt.encode(), "live_chat.json")
    assert f2 == "youtube_live_chat" and m2[1].t == 1.0 and m2[0].emotes == [":joy:"]
    m3, f3 = parse_chat(b"t,user,text\n1.5,a,KEKW\n3,b,hi\n", "chat.csv")
    assert f3 == "csv" and m3[0].text == "KEKW"
    with pytest.raises(ValueError):
        parse_chat(b"kein chat", "x.txt")
    assert "laugh" in categorize("KEKW KEKW") and "clip" in categorize("clip it!!")
    assert "negative" in categorize("so boring")


def test_clip_bounds_snap_to_sentences():
    words = [Word("Hallo", 40.0, 40.4), Word("Leute.", 40.5, 41.0), Word("Jetzt", 42.0, 42.3),
             Word("passiert", 42.4, 42.9), Word("es", 43.0, 43.2), Word("gleich!", 43.3, 43.8),
             Word("Wahnsinn", 50.0, 50.6), Word("was", 50.7, 50.9), Word("war", 51.0, 51.2),
             Word("das.", 51.3, 51.8), Word("Weiter", 60.0, 60.5)]
    s, e, note = scoring.clip_bounds(52.0, 300, words, pre=10, post=0.5, min_len=5)
    assert s == pytest.approx(41.85, abs=0.01)     # Satzanfang „Jetzt“
    assert e == pytest.approx(52.1, abs=0.01)      # Satzende „das.“
    assert "Satz" in note


def test_dedupe_keeps_best_of_overlapping():
    clips = [{"start": 10, "end": 30, "score": 50}, {"start": 12, "end": 32, "score": 70},
             {"start": 100, "end": 120, "score": 30}]
    kept = scoring.dedupe(clips)
    assert [c["score"] for c in kept] == [70, 30]


def test_scoring_without_chat_renormalizes_and_explains(tmp_path):
    from clipforge.stream.analyze import analyze
    r = analyze(_stream(str(tmp_path / "s.mp4")), max_clips=3)
    assert r["signals"] == ["audio", "video"] and abs(sum(r["weights"].values()) - 1) < 1e-3
    top = r["highlights"][0]
    assert 55 <= top["t"] <= 72 and any("Lautstärke" in x or "Bewegung" in x for x in top["reasons"])


def test_stream_api_end_to_end(tmp_path):
    client, app_module = make_client(str(tmp_path))

    def fake_whisper(path, settings):
        # Fenster-Transkript: relative Zeiten ab Fensteranfang
        words = [Word("Achtung", 15.0, 15.5), Word("jetzt", 15.6, 16.0), Word("kommt's.", 16.1, 16.6),
                 Word("No", 20.0, 20.3), Word("way!", 20.4, 20.9), Word("Unglaublich", 21.0, 21.8),
                 Word("Leute.", 21.9, 22.4)]
        return Transcript(language="de", duration=80, segments=[TranscriptSegment("x", 15, 23, words)])
    app_module.studio.streams.transcriber = fake_whisper
    try:
        r = client.post("/api/studio/streams", json={"title": "Mein Stream", "platform": "twitch"})
        assert r.status_code == 400   # Rechte nicht bestätigt
        sid = client.post("/api/studio/streams", json={"title": "Mein Stream", "platform": "twitch",
                                                       "rights_confirmed": True}).json()["stream"]["id"]
        assert client.post(f"/api/studio/streams/{sid}/analyze", json={}).status_code == 409
        with open(_stream(str(tmp_path / "v.mp4")), "rb") as fh:
            up = client.post(f"/api/studio/streams/{sid}/video", files={"file": ("vod.mp4", fh, "video/mp4")})
        assert up.status_code == 200 and up.json()["stream"]["video"]["duration"] > 100
        bad = client.post(f"/api/studio/streams/{sid}/video", files={"file": ("x.exe", b"MZ", "application/x")})
        assert bad.status_code == 415
        ch = client.post(f"/api/studio/streams/{sid}/chat", files={"file": ("chat.json", _twitch_chat(), "application/json")})
        assert ch.status_code == 200 and ch.json()["stream"]["chat"]["format"] == "twitchdownloader"
        task = wait_task(client, client.post(f"/api/studio/streams/{sid}/analyze",
                                             json={"max_clips": 3, "keywords": ["unglaublich"]}).json()["task"]["id"])
        assert task["status"] == "succeeded", task
        view = client.get(f"/api/studio/streams/{sid}").json()
        a = view["analysis"]
        assert set(a["signals"]) == {"audio", "chat", "video", "transcript"}
        h = a["highlights"][0]
        assert 55 <= h["t"] <= 72 and h["chat_categories"] and "_words" not in a
        assert any("Chat" in x for x in h["reasons"]) and len(a["heatmap"]["score"]) > 50
        # manuelle Korrektur
        p = client.patch(f"/api/studio/streams/{sid}/highlights/{h['id']}", json={"start": 55, "end": 72})
        assert p.status_code == 200 and p.json()["highlight"]["edited"]
        assert client.patch(f"/api/studio/streams/{sid}/highlights/{h['id']}", json={"start": 70, "end": 60}).status_code == 400
        # Vorschau
        t = wait_task(client, client.post(f"/api/studio/streams/{sid}/highlights/{h['id']}/preview").json()["task"]["id"])
        assert t["status"] == "succeeded"
        assert client.get(f"/api/studio/streams/{sid}/highlights/{h['id']}/preview").status_code == 200
        # Render → echter ClipForge-Job mit vertikalem Clip
        t = wait_task(client, client.post(f"/api/studio/streams/{sid}/render",
                                          json={"ids": [h["id"]], "remove_silence": False}).json()["task"]["id"], 300)
        assert t["status"] == "succeeded", t
        job = client.get(f"/api/jobs/{t['result']['job_id']}").json()
        assert job["status"] == "completed"
        clips = json.load(open(os.path.join(str(tmp_path), "jobs", t["result"]["job_id"], "clips.json")))
        c = clips["clips"][0]
        assert c["start"] == 55 and c["end"] == 72 and c["stream"]["highlight"] == h["id"]
        from clipforge.ffmpeg_utils import probe
        info = probe(c["output_path"])
        assert info.height > info.width and info.has_audio
    finally:
        clear_env()
