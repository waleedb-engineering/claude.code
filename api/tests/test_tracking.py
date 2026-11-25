"""Dynamischer Zuschnitt: Gesicht wandert durchs Bild → Tracking-Crop hält es mittig,
statischer Crop nicht. Braucht lena.jpg (scripts/fetch_test_models.py)."""

import os
import subprocess

import pytest

from clipforge import reframe

MODELS = os.environ.get("CLIPFORGE_TEST_MODELS_DIR")
LENA = os.path.join(MODELS or "", "lena.jpg")
pytestmark = pytest.mark.skipif(not (MODELS and os.path.isfile(LENA)),
                                reason="lena.jpg nicht vorhanden (CLIPFORGE_TEST_MODELS_DIR)")


def _moving_face(path, dur=8):
    subprocess.run(["ffmpeg", "-y", "-v", "error", "-f", "lavfi", "-i", f"color=c=0x707070:s=640x360:r=15:d={dur}",
                    "-loop", "1", "-i", LENA, "-filter_complex",
                    "[1:v]scale=130:130[f];[0:v][f]overlay=x='40+55*t':y=110:shortest=1",
                    "-t", str(dur), "-c:v", "libx264", "-preset", "ultrafast", "-pix_fmt", "yuv420p", path], check=True)
    return path


def _face_x_in_output(src, flt, t, out=(202, 360)):
    import cv2
    tmp = src + f".{t}.png"
    subprocess.run(["ffmpeg", "-y", "-v", "error", "-i", src, "-vf", flt, "-ss", str(t), "-frames:v", "1", tmp],
                   check=True)
    img = cv2.imread(tmp)
    _, det = reframe._detector()
    faces = det(img)
    return max(faces, key=lambda f: f[2])[0] if faces else None


@pytest.mark.parametrize("yunet", [False, True])
def test_track_keeps_moving_face_centered(tmp_path, monkeypatch, yunet):
    yp = os.path.join(MODELS, "face_detection_yunet_2023mar.onnx")
    if yunet:
        if not os.path.isfile(yp):
            pytest.skip("YuNet fehlt")
        monkeypatch.setenv("CLIPFORGE_YUNET_PATH", yp)
    else:
        monkeypatch.setenv("CLIPFORGE_YUNET_PATH", "/nonexistent")
        monkeypatch.setattr(reframe, "_yunet_path", lambda: None)
    src = _moving_face(str(tmp_path / "m.mp4"))
    flt, info = reframe.plan_reframe(src, 0, 8, 640, 360, 202, 360, "track")
    assert info["applied_mode"] == "track" and info["track_applied"], info
    assert info["track_method"] == ("yunet" if yunet else "opencv_haar_frontalface")
    static, sinfo = reframe.plan_reframe(src, 0, 8, 640, 360, 202, 360, "smart")
    for t in (1.0, 6.5):
        xt = _face_x_in_output(src, flt, t)
        assert xt is not None and abs(xt - 0.5) < 0.2, (t, xt)
    # statischer Crop verliert das Gesicht an mindestens einem Ende
    ends = [_face_x_in_output(src, static, t) for t in (1.0, 6.5)]
    assert any(x is None or abs(x - 0.5) > 0.25 for x in ends), ends


def test_static_subject_stays_static_and_manual_points(tmp_path):
    src = str(tmp_path / "s.mp4")
    subprocess.run(["ffmpeg", "-y", "-v", "error", "-f", "lavfi", "-i", "color=c=0x707070:s=640x360:r=10:d=4",
                    "-loop", "1", "-i", LENA, "-filter_complex", "[1:v]scale=130:130[f];[0:v][f]overlay=x=400:y=110:shortest=1",
                    "-t", "4", "-c:v", "libx264", "-preset", "ultrafast", "-pix_fmt", "yuv420p", src], check=True)
    _, info = reframe.plan_reframe(src, 0, 4, 640, 360, 202, 360, "track")
    assert info["applied_mode"] == "smart" and "kaum" in info["fallback_reason"]   # ruhiger statischer Crop
    flt, minfo = reframe.plan_reframe(src, 0, 4, 640, 360, 202, 360, "manual", [(0, 0.2), (4, 0.8)])
    assert minfo["applied_mode"] == "manual" and "if(lt(t," in flt


def test_smoothing_limits_pan_speed_and_fills_gaps():
    samples = [(0.0, 0.2, 1), (0.5, None, 0), (1.0, 0.9, 1), (1.5, 0.21, 1), (2.0, 0.22, 1), (2.5, 0.23, 1)]
    pts = reframe.smooth_track(samples, 3.0)
    for (t0, x0), (t1, x1) in zip(pts, pts[1:]):
        assert abs(x1 - x0) <= reframe.MAX_PAN * (t1 - t0) + 1e-6       # keine Sprünge
    assert max(x for _, x in pts) < 0.5                                   # Ausreißer 0.9 weggefiltert
    assert pts[-1][0] == 3.0


def test_track_with_silence_removal_in_clip_render(tmp_path):
    """Crop vor select: Tracking + Pausenentfernung rendern synchron (Dauer = behaltene Teile)."""
    from clipforge.config import get_settings
    from clipforge.ffmpeg_utils import probe
    from clipforge.models import ScoreBreakdown, ScoredClip
    from clipforge.render import render_clip
    v = _moving_face(str(tmp_path / "m.mp4"))
    av = str(tmp_path / "av.mp4")
    subprocess.run(["ffmpeg", "-y", "-v", "error", "-i", v, "-f", "lavfi", "-i",
                    "aevalsrc='0.4*sin(2*PI*300*t)*(lt(t,3)+gt(t,5.5))':s=44100:d=8", "-shortest",
                    "-c:v", "copy", "-c:a", "aac", av], check=True)
    clip = ScoredClip(start=0, end=8, text="x", score=50, breakdown=ScoreBreakdown(50, 50, 50, 50, 50),
                      reason="t", words=[])
    out = str(tmp_path / "c.mp4")
    render_clip(av, clip, out, get_settings(), remove_silence=True, caption_mode="standard",
                caption_style="clean", reframe_mode="track")
    info = probe(out)
    assert clip.reframe_info["applied_mode"] == "track" and clip.reframe_info["track_applied"]
    assert info.width * 16 == info.height * 9 and 5.0 < info.duration < 7.6, info.duration


def _scene_video(path, overlays, dur=8, size="640x360"):
    """overlays: [(scale, x_expr, y_expr, enable_expr|None)] — Gesichter auf grauem Grund."""
    args = ["ffmpeg", "-y", "-v", "error", "-f", "lavfi", "-i", f"color=c=0x707070:s={size}:r=15:d={dur}"]
    chain, prev = [], "[0:v]"
    for i, (sc, x, y, en) in enumerate(overlays):
        args += ["-loop", "1", "-i", LENA]
        chain.append(f"[{i + 1}:v]scale={sc}:{sc}[f{i}]")
        en_s = f":enable='{en}'" if en else ""
        chain.append(f"{prev}[f{i}]overlay=x='{x}':y='{y}':shortest=1{en_s}[v{i}]")
        prev = f"[v{i}]"
    args += ["-filter_complex", ";".join(chain), "-map", prev, "-t", str(dur), "-c:v", "libx264",
             "-preset", "ultrafast", "-pix_fmt", "yuv420p", path]
    subprocess.run(args, check=True)
    return path


def _face_xy(src, flt, t):
    import cv2
    tmp = src + f".{t}.png"
    subprocess.run(["ffmpeg", "-y", "-v", "error", "-i", src, "-vf", flt, "-ss", str(t), "-frames:v", "1", tmp],
                   check=True)
    faces = reframe._detector()[1](cv2.imread(tmp))
    f = max(faces, key=lambda f: f[2]) if faces else None
    return (f[0], f[1]) if f else None


def test_main_subject_beats_brief_large_decoy(tmp_path):
    # großes Gesicht nur 0–1,5 s oben rechts, Hauptmotiv bewegt sich die ganze Zeit
    src = _scene_video(str(tmp_path / "two.mp4"), [
        (110, "40+50*t", "140", None),
        (170, "450", "20", "lt(t,1.5)")])
    flt, info = reframe.plan_reframe(src, 0, 8, 640, 360, 202, 360, "track")
    assert info["track_applied"] and info["track_candidates"] >= 2, info
    for t in (0.5, 5.0, 7.0):
        xy = _face_xy(src, flt, t)
        assert xy and abs(xy[0] - 0.5) < 0.22, (t, xy)


def test_vertical_tracking_with_zoom(tmp_path):
    # Gesicht wandert von oben nach unten; mit Zoom 1,6 entsteht vertikaler Spielraum
    src = _scene_video(str(tmp_path / "vert.mp4"), [(90, "275", "10+28*t", None)])
    flt, info = reframe.plan_reframe(src, 0, 8, 640, 360, 202, 360, "track", track_zoom=1.6)
    assert info["track_applied"] and info["track_vertical"], info
    for t in (1.0, 7.0):
        xy = _face_xy(src, flt, t)
        assert xy and abs(xy[1] - 0.5) < 0.22, (t, xy)
    static, _ = reframe.plan_reframe(src, 0, 8, 640, 360, 202, 360, "smart")
    ends = [_face_xy(src, static, t) for t in (1.0, 7.0)]
    assert any(e is None or abs(e[1] - 0.5) > 0.25 for e in ends), ends


def test_realistic_motion_is_smooth(tmp_path):
    # Beschleunigung, Stillstand, Zittern: sin-Bahn mit Pause und 3-px-Wackeln
    src = _scene_video(str(tmp_path / "real.mp4"), [
        (120, "260+200*sin(t*0.9)*gt(t,2)+3*sin(t*37)", "120+4*sin(t*29)", None)], dur=9)
    flt, info = reframe.plan_reframe(src, 0, 9, 640, 360, 202, 360, "track")
    assert info["track_applied"], info
    pts = reframe.smooth_track([(t, x, c) for t, x, c, _ in reframe.track_faces(src, 0, 9)["samples"]], 9)
    for (t0, x0), (t1, x1) in zip(pts, pts[1:]):
        assert abs(x1 - x0) <= reframe.MAX_PAN * (t1 - t0) + 1e-6
    hits = [_face_xy(src, flt, t) for t in (1.0, 3.5, 6.0, 8.5)]
    assert sum(1 for h in hits if h and abs(h[0] - 0.5) < 0.3) >= 3, hits
