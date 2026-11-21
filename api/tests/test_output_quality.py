"""Ausgabe-Qualitätsprüfung an echten FFmpeg-Dateien mit bekannten Fehlern."""

import subprocess

import pytest

from clipforge import output_quality as oq
from clipforge.studio.errors import StudioError


def _make(path, vsrc, asrc=None, size="360x640", dur=6):
    sep = ":" if "=" in vsrc else "="
    args = ["ffmpeg", "-y", "-v", "error", "-f", "lavfi", "-i", f"{vsrc}{sep}s={size}:r=25:d={dur}"]
    if asrc:
        args += ["-f", "lavfi", "-i", asrc, "-shortest", "-c:a", "aac"]
    subprocess.run(args + ["-c:v", "libx264", "-preset", "ultrafast", "-pix_fmt", "yuv420p", path], check=True)
    return path


def _levels(r):
    return {c["id"]: c["level"] for c in r["checks"]}


def test_good_clip_passes(tmp_path):
    p = _make(str(tmp_path / "ok.mp4"), "testsrc2", "sine=f=440:d=6,volume=0.25")
    r = oq.analyze(p, platform="tiktok")
    lv = _levels(r)
    assert r["passed"] and lv["aspect"] == "ok" and lv["black_frames"] == "ok" and lv["pauses"] == "ok"
    assert lv["clipping"] == "ok" and lv["loudness"] in ("ok", "warn")


def test_detects_black_frames_clipping_pauses_wrong_format(tmp_path):
    # Schwarzbild in der Mitte, übersteuerter Ton mit 2,5-s-Pause, Querformat für TikTok
    p = str(tmp_path / "bad.mp4")
    subprocess.run(["ffmpeg", "-y", "-v", "error",
                    "-f", "lavfi", "-i", "testsrc2=s=640x360:r=25:d=6",
                    "-f", "lavfi", "-i", "aevalsrc='1.6*sin(2*PI*300*t)*not(between(t,2,4.5))':s=44100:d=6",
                    "-vf", "drawbox=c=black:t=fill:enable='between(t,2.5,3.5)'", "-c:v", "libx264",
                    "-preset", "ultrafast", "-pix_fmt", "yuv420p", "-c:a", "aac", "-shortest", p], check=True)
    r = oq.analyze(p, platform="tiktok")
    lv = _levels(r)
    assert lv["aspect"] == "fail" and not r["passed"]
    assert lv["black_frames"] == "warn" and lv["pauses"] == "warn"
    assert lv["clipping"] in ("fail", "warn")


def test_no_audio_and_platform_duration(tmp_path):
    p = _make(str(tmp_path / "silent.mp4"), "testsrc2")
    r = oq.analyze(p, platform="x")
    assert _levels(r)["audio"] == "fail"
    long = _make(str(tmp_path / "long.mp4"), "color=c=gray", "sine=f=300:d=150", size="320x180", dur=150)
    assert _levels(oq.analyze(long, platform="x"))["duration"] == "fail"


def test_review_requires_full_checklist():
    with pytest.raises(StudioError):
        oq.review_entry({"punchline_complete": True}, "approved", "", "u")
    ok = oq.review_entry({k: True for k in oq.REVIEW_ITEMS}, "approved", "gut", "u")
    assert ok["verdict"] == "approved" and all(ok["checklist"].values())
    ch = oq.review_entry({"framing_ok": False}, "changes_requested", "Gesicht abgeschnitten", "u")
    assert ch["checklist"]["framing_ok"] is False


def test_render_report_has_output_checks_and_review(tmp_path):
    from studio_helpers import make_client, wait_task
    client, _ = make_client(str(tmp_path))
    r = client.post("/api/studio/projects", json={"workflow": "script", "voice": {"provider": "mock"},
                                                  "script": "Hallo und willkommen. Heute zeige ich dir drei Tricks."})
    pid = r.json()["project"]["id"]
    wait_task(client, r.json()["task_id"])
    t = wait_task(client, client.post(f"/api/studio/projects/{pid}/render", json={"mode": "preview"}).json()["task"]["id"], 300)
    rid = t["result"]["render_id"]
    rep = client.get(f"/api/studio/projects/{pid}").json()["renders"][0]
    ids = {c["id"] for c in rep["output_checks"]["checks"]}
    assert {"black_frames", "loudness", "clipping", "pauses", "duration"} <= ids
    bad = client.put(f"/api/studio/projects/{pid}/renders/{rid}/review", json={"verdict": "approved", "checklist": {}})
    assert bad.status_code == 400
    ok = client.put(f"/api/studio/projects/{pid}/renders/{rid}/review",
                    json={"verdict": "changes_requested", "checklist": {"audio_ok": True}, "note": "Musik zu laut"})
    assert ok.status_code == 200
    assert client.get(f"/api/studio/projects/{pid}").json()["renders"][0]["review"]["note"] == "Musik zu laut"


def test_missing_ffmpeg_filter_gives_actionable_error(tmp_path):
    """Fehlt einem FFmpeg-Build ein Filter (z. B. Homebrew ohne libass), nennt der Fehler die Ursache."""
    import pytest
    from clipforge.studio.audio import run_ffmpeg
    from clipforge.studio.errors import StudioError
    with pytest.raises(StudioError) as exc:
        run_ffmpeg(["ffmpeg", "-hide_banner", "-f", "lavfi", "-i", "color=c=black:s=32x32:d=0.1",
                    "-vf", "gibtesnicht_xyz", "-f", "null", "-"], "Test")
    assert exc.value.code == "ffmpeg_feature_missing"
    assert "gibtesnicht_xyz" in exc.value.message and "ffmpeg-full" in exc.value.message
