"""Renderer-Effekte: Punch-in-Zoom, Caption-Layout, Soundeffekte, Lautheit (echtes FFmpeg)."""

from __future__ import annotations

import json
import re
import subprocess

from studio_helpers import ffprobe, make_click_wav, make_service

from clipforge.studio.projects import migrate, normalize_scene


def _split_png(path):
    """Linke Hälfte rot, rechte Hälfte blau."""
    subprocess.run(["ffmpeg", "-y", "-v", "error", "-f", "lavfi", "-i", "color=c=red:s=360x640:d=1",
                    "-f", "lavfi", "-i", "color=c=blue:s=360x640:d=1", "-filter_complex", "hstack",
                    "-frames:v", "1", path], check=True)
    return path


def _frame_rgb(video, t, w=36, h=64):
    raw = subprocess.run(["ffmpeg", "-v", "error", "-ss", str(t), "-i", video, "-frames:v", "1",
                          "-vf", f"scale={w}:{h}", "-f", "rawvideo", "-pix_fmt", "rgb24", "-"],
                         capture_output=True, check=True).stdout
    return raw


def _loudness(path):
    err = subprocess.run(["ffmpeg", "-v", "info", "-i", path, "-af", "ebur128", "-f", "null", "-"],
                         capture_output=True, text=True).stderr
    return float(re.findall(r"I:\s+(-?[\d.]+) LUFS", err)[-1])


def test_schema_validates_new_fields():
    s = normalize_scene({"text": "x", "zoom": {"factor": 9, "focus": "nope"}, "sfx": [{"track": "/etc/passwd"}]})
    assert s["zoom"] == {"factor": 2.5, "focus": "center", "ramp": False} and "sfx" not in s
    assert "zoom" not in normalize_scene({"text": "x", "zoom": {"factor": 1}})
    p = migrate({"captions": {"style": "bold", "position": "top", "font": "Comic; rm", "color": "#ff0000"}})
    assert p["captions"]["position"] == "top" and p["captions"]["font"] is None
    assert p["captions"]["color"] == "#ff0000" and p["audio"] == {"loudnorm": False, "target_lufs": -14.0}


def test_zoom_caption_layout_sfx_and_loudnorm(tmp_path):
    svc, _ = make_service(str(tmp_path))
    p = svc.create_project({"workflow": "script", "title": "FX", "script": "Eins zwei drei. Vier fünf sechs.",
                            "voice": {"provider": "mock"}, "resolution": "720p"})
    t = svc.tasks.submit("ingest", p["id"], {}, run_inline=True)
    assert t["status"] == "succeeded", t
    with open(_split_png(str(tmp_path / "split.png")), "rb") as fh:
        img = svc.upload_media(p["id"], "split.png", fh)["name"]
    with open(make_click_wav(str(tmp_path / "boom.wav"), 1.0), "rb") as fh:
        fx = svc.upload_media(p["id"], "boom.wav", fh)["name"]
    p = svc.store.load(p["id"])
    scenes = p["scenes"]
    scenes[0].update(visual={"mode": "media", "media": img}, zoom={"factor": 2.0, "focus": "left"},
                     sfx=[{"track": f"project:{fx}", "at": 0.2, "volume": 1.5}])
    svc.update_project(p["id"], {"scenes": scenes, "captions": {"style": "bold", "position": "top",
                                                                "color": "#ffcc00", "font": "Verdana", "size": 1.2},
                                 "audio": {"loudnorm": True, "target_lufs": -14}, "options": {"image_animation": False}},
                       p["version"])
    t = svc.tasks.submit("render", p["id"], {"mode": "final"}, run_inline=True)
    assert t["status"] == "succeeded", t
    rep = svc.list_renders(p["id"])[0]
    path = svc.render_file(p["id"], rep["render_id"])
    # Zoom ×2 auf die linke Hälfte → Bildmitte (ohne Captions-Bereich) komplett rot
    rgb = _frame_rgb(path, 0.3)
    mid = [rgb[i:i + 3] for i in range(0, len(rgb), 3)][36 * 30: 36 * 34]
    assert all(px[0] > 180 and px[2] < 80 for px in mid), "Zoom-Fokus links greift nicht"
    assert rep["captions"]["layout"] == {"font": "Verdana", "size": 1.2, "color": "#ffcc00", "position": "top"}
    # Lautheit nahe −14 LUFS
    assert rep["loudness"] and rep["loudness"]["applied"], rep["loudness"]
    assert abs(_loudness(path) - (-14)) < 2.5, (_loudness(path), rep["loudness"])
    info = ffprobe(path)
    assert any(s["codec_type"] == "audio" for s in info["streams"])


def test_sfx_is_audible_at_its_position(tmp_path):
    svc, _ = make_service(str(tmp_path))
    p = svc.create_project({"workflow": "script", "title": "FX2", "script": "Kurz. Noch ein Satz hier.",
                            "voice": {"provider": "none"}, "resolution": "720p"})
    svc.tasks.submit("ingest", p["id"], {}, run_inline=True)
    with open(make_click_wav(str(tmp_path / "c.wav"), 0.5), "rb") as fh:
        fx = svc.upload_media(p["id"], "c.wav", fh)["name"]
    p = svc.store.load(p["id"])
    sc = p["scenes"]
    sc[0].update(duration=3.0, sfx=[{"track": f"project:{fx}", "at": 1.5, "volume": 1.0}])
    svc.update_project(p["id"], {"scenes": sc}, p["version"])
    t = svc.tasks.submit("render", p["id"], {"mode": "preview"}, run_inline=True)
    assert t["status"] == "succeeded", t
    path = svc.render_file(p["id"], svc.list_renders(p["id"])[0]["render_id"])
    err = subprocess.run(["ffmpeg", "-v", "info", "-i", path, "-af",
                          "astats=metadata=1:reset=1,ametadata=print:key=lavfi.astats.Overall.Peak_level",
                          "-f", "null", "-"], capture_output=True, text=True).stderr
    times = [float(x) for x in re.findall(r"pts_time:([\d.]+)", err)]
    peaks = [float(x) if x != "-inf" else -200 for x in re.findall(r"Peak_level=(-?[\w.]+)", err)]
    loud = [t for t, pk in zip(times, peaks) if pk > -20]
    assert loud and 1.3 <= min(loud) <= 1.7, (loud[:5], json.dumps(peaks[:10]))


def test_normalize_loudness_linear_path(tmp_path):
    from clipforge.studio.render import normalize_loudness
    path = str(tmp_path / "q.mp4")
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-f", "lavfi", "-i", "color=s=64x64:d=6", "-f", "lavfi",
                    "-i", "sine=f=300:d=6,volume=0.05", "-shortest", "-c:v", "libx264", "-c:a", "aac", path], check=True)
    before = _loudness(path)
    r = normalize_loudness(path, -16.0)
    assert r["applied"] and r["method"] == "loudnorm linear"
    assert before < -25 and abs(_loudness(path) + 16) < 1.0
