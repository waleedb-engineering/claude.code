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
