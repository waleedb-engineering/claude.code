"""Auswertung, Tuning, Clip-Varianten und Verhalten bei fehlenden/defekten Daten.

Die Medien sind synthetisch (FFmpeg lavfi) und als solche gekennzeichnet —
sie prüfen die Pipeline, nicht die Erkennungsqualität auf echten Streams."""

import os
import subprocess

import pytest

from clipforge.stream import evaluate as ev
from clipforge.stream import scoring
from clipforge.models import Word
from studio_helpers import make_client, wait_task
from test_stream_intelligence import _stream, _twitch_chat


def test_metrics_matching_and_offsets():
    labels = ev.load_labels({"highlights": [{"start": 60, "end": 70, "peak": 62},
                                            {"start": 200, "end": 210}]})
    pred = [{"t": 63, "start": 52, "end": 75, "score": 80},     # Treffer, vollständig
            {"t": 64, "start": 60, "end": 66, "score": 50},     # zweiter Treffer aufs selbe Ereignis → FP
            {"t": 400, "start": 390, "end": 410, "score": 30}]  # Fehlalarm
    r = ev.evaluate(pred, labels, tolerance=5)
    assert (r["tp"], r["fp"], r["fn"]) == (1, 2, 1)
    assert r["precision"] == pytest.approx(1 / 3, abs=1e-3) and r["recall"] == 0.5
    assert r["time_offset_mean_s"] == 1.0 and r["event_fully_contained"] == 1.0
    assert r["p@1"] == 1.0 and r["missed"][0]["start"] == 200
    with pytest.raises(ValueError):
        ev.load_labels({"highlights": [{"start": 5, "end": 2}]})


def test_variants_have_suitability_and_no_virality_claim():
    words = [Word("Achtung.", 48.0, 48.6), Word("Jetzt", 50.0, 50.3), Word("kommt", 50.4, 50.7),
             Word("es!", 50.8, 51.2), Word("Wahnsinn.", 62.0, 62.8)]
    c = {"t": 58, "start": 49.85, "end": 63.1, "score": 55}
    vs = scoring.clip_variants(c, 300, words, "an Satzanfang ausgerichtet, endet am Satzende",
                               pre=10, post=8, min_len=8, max_len=60)
    names = [v["variant"] for v in vs]
    assert "balanced" in names and len(vs) >= 2
    for v in vs:
        assert 0 <= v["suitability"] <= 100 and v["suitability_reasons"]
        assert not any("viral" in r.lower() for r in v["suitability_reasons"])
    ctx = next(v for v in vs if v["variant"] == "context")
    assert ctx["duration"] > next(v for v in vs if v["variant"] == "balanced")["duration"]


def test_tune_reports_leave_one_out(tmp_path):
    from clipforge.stream.analyze import measure
    from clipforge.stream.chat import parse_chat
    m = measure(_stream(str(tmp_path / "a.mp4")))
    chat, _ = parse_chat(_twitch_chat(), "c.json")
    labels = ev.load_labels({"highlights": [{"start": 60, "end": 70, "peak": 60}]})
    cases = [{"measured": m, "chat": chat, "labels": labels}, {"measured": m, "chat": None, "labels": labels}]
    res = ev.tune(cases, grid=(0.5, 1.0), max_clips=2)
    assert res["f1_tuned"] >= res["f1_default"] and res["f1_leave_one_out"] is not None
    assert set(res["best_group_factors"]) == {"chat", "audio", "video"}


def _silent_video(path):
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-f", "lavfi", "-i", "testsrc=s=160x90:d=40:r=5",
                    "-c:v", "libx264", "-preset", "ultrafast", path], check=True)
    return path


def test_missing_and_broken_data(tmp_path):
    client, app_module = make_client(str(tmp_path))
    sid = client.post("/api/studio/streams", json={"title": "x", "platform": "obs",
                                                   "rights_confirmed": True}).json()["stream"]["id"]
    # defektes Video (abgeschnittene Datei) → 415, nichts bleibt liegen
    _stream(str(tmp_path / "g.mp4"))
    r = client.post(f"/api/studio/streams/{sid}/video", files={"file": ("cut.mp4", b"\x00\x00\x00\x18ftypmp42" + b"x" * 500, "video/mp4")})
    assert r.status_code == 415
    # leerer / kaputter Chat
    assert client.post(f"/api/studio/streams/{sid}/chat", files={"file": ("c.json", b"{}", "application/json")}).status_code == 422
    assert client.post(f"/api/studio/streams/{sid}/chat", files={"file": ("c.json", b"[{\"t\":", "application/json")}).status_code == 422
    # Video ohne Tonspur → Analyse nur mit Bildsignal
    with open(_silent_video(str(tmp_path / "s.mp4")), "rb") as fh:
        assert client.post(f"/api/studio/streams/{sid}/video", files={"file": ("s.mp4", fh, "video/mp4")}).status_code == 200
    t = wait_task(client, client.post(f"/api/studio/streams/{sid}/analyze", json={"transcribe": False}).json()["task"]["id"])
    assert t["status"] == "succeeded", t
    a = client.get(f"/api/studio/streams/{sid}").json()["analysis"]
    assert a["signals"] == ["video"]
    # min > max wird abgelehnt
    assert client.post(f"/api/studio/streams/{sid}/analyze", json={"min_len": 50, "max_len": 20}).status_code == 400
    # Chat passt zeitlich nicht zum Video (alles nach dem Ende) → Analyse läuft trotzdem
    late = b"t,user,text\n500,a,KEKW\n501,b,KEKW\n"
    assert client.post(f"/api/studio/streams/{sid}/chat", files={"file": ("c.csv", late, "text/csv")}).status_code == 200
    t = wait_task(client, client.post(f"/api/studio/streams/{sid}/analyze", json={"transcribe": False}).json()["task"]["id"])
    assert t["status"] == "succeeded", t
    # neues Video verwirft den Signal-Cache
    from clipforge.studio.storage import studio_dir
    cache = os.path.join(studio_dir(), "streams", sid, "signals.json")
    assert os.path.exists(cache)
    with open(str(tmp_path / "g.mp4"), "rb") as fh:
        assert client.post(f"/api/studio/streams/{sid}/video", files={"file": ("g.mp4", fh, "video/mp4")}).status_code == 200
    assert not os.path.exists(cache)


def test_labels_evaluation_variants_and_tuning_api(tmp_path):
    client, _ = make_client(str(tmp_path))
    ids = []
    for i in range(2):
        sid = client.post("/api/studio/streams", json={"title": f"S{i}", "platform": "twitch",
                                                       "rights_confirmed": True}).json()["stream"]["id"]
        with open(_stream(str(tmp_path / f"v{i}.mp4")), "rb") as fh:
            client.post(f"/api/studio/streams/{sid}/video", files={"file": ("v.mp4", fh, "video/mp4")})
        client.post(f"/api/studio/streams/{sid}/chat", files={"file": ("chat.json", _twitch_chat(), "application/json")})
        t = wait_task(client, client.post(f"/api/studio/streams/{sid}/analyze",
                                          json={"transcribe": False, "max_clips": 3, "min_len": 8}).json()["task"]["id"])
        assert t["status"] == "succeeded", t
        ids.append(sid)
    sid = ids[0]
    a = client.get(f"/api/studio/streams/{sid}").json()["analysis"]
    h = a["highlights"][0]
    assert a["clip_limits"]["min_len"] == 8 and h["variants"]
    assert client.get(f"/api/studio/streams/{sid}/evaluation").status_code == 404   # noch keine Markierung
    # Variante wählen
    v = next(x for x in h["variants"] if x["variant"] == "context")
    p = client.patch(f"/api/studio/streams/{sid}/highlights/{h['id']}", json={"variant": "context"}).json()["highlight"]
    assert (p["start"], p["end"], p["variant"]) == (v["start"], v["end"], "context")
    # bestätigen + verpasstes Highlight ergänzen
    lab = client.post(f"/api/studio/streams/{sid}/highlights/{h['id']}/judge", json={"verdict": "hit"}).json()["labels"]
    assert lab["highlights"][0]["from"] == h["id"]
    items = lab["highlights"] + [{"start": 100, "end": 105, "label": "verpasst"}]
    assert client.put(f"/api/studio/streams/{sid}/labels", json={"highlights": items}).status_code == 200
    assert client.put(f"/api/studio/streams/{sid}/labels", json={"highlights": [{"start": 1, "end": 999}]}).status_code == 400
    e = client.get(f"/api/studio/streams/{sid}/evaluation").json()
    assert e["tp"] >= 1 and e["fn"] >= 1 and e["labels"] == 2
    # Tuning: eine Aufnahme → Übernehmen verweigert; zwei → Ergebnis mit Kreuzprüfung
    r = client.post("/api/studio/stream-weights/tune", json={"apply": True})
    assert r.status_code == 400
    client.post(f"/api/studio/streams/{ids[1]}/highlights/h01/judge", json={"verdict": "hit"})
    r = client.post("/api/studio/stream-weights/tune", json={}).json()
    assert r["cases"] == 2 and r["f1_leave_one_out"] is not None and r["applied"] is False
    assert client.get("/api/studio/stream-weights").json()["tuned"] is None
