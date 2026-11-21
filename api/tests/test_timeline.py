"""Mehrspur-Timeline: Operationen, Keyframe-Ausdrücke (identisch zur Python-Kurve),
echtes Rendern (Pixel-/Tonprüfung), Kompatibilität alter Projekte."""

import re
import subprocess

import pytest

from clipforge.studio import timeline as T
from clipforge.studio.errors import StudioError
from clipforge.studio.projects import migrate
from studio_helpers import make_click_wav, make_service


def _tl():
    return T.normalize({"tracks": [
        {"id": "ddddddddddd1", "kind": "overlay", "items": [
            {"id": "aaaaaaaaaaa1", "src": "a.png", "start": 1.0, "duration": 4.0, "in": 0},
            {"id": "bbbbbbbbbbb1", "src": "b.mp4", "start": 6.0, "duration": 2.0, "in": 1.0}]},
        {"id": "eeeeeeeeeee1", "kind": "audio", "items": [
            {"id": "ccccccccccc1", "src": "m.wav", "start": 0.0, "duration": 3.0}]}]})


def test_normalize_and_migration_keep_old_projects_readable():
    p = migrate({"title": "alt", "scenes": [{"text": "a"}]})
    assert p["timeline"] == {"version": 1, "tracks": []}
    broken = migrate({"title": "x", "timeline": {"tracks": [{"kind": "laser"}]}})
    assert broken["timeline"]["tracks"] == [] and broken["timeline_backup"]
    with pytest.raises(StudioError):
        T.normalize({"tracks": [{"kind": "overlay", "items": [{"src": "../etc/passwd"}]}]})
    with pytest.raises(StudioError):
        T.normalize({"tracks": [{"kind": "audio", "items": [{"src": "x.exe"}]}]})


def test_move_snaps_and_moves_groups():
    tl = _tl()
    tl2 = T.move_item(tl, "bbbbbbbbbbb1", 5.1)                     # rastet an Ende von a (5.0) ein
    assert T._find(tl2, "bbbbbbbbbbb1")[1]["start"] == 5.0
    tl3 = T.move_item(tl, "bbbbbbbbbbb1", 5.6, snap=False)
    assert T._find(tl3, "bbbbbbbbbbb1")[1]["start"] == 5.6
    tl4, gid = T.group_items(tl, ["aaaaaaaaaaa1", "ccccccccccc1"])
    tl5 = T.move_item(tl4, "aaaaaaaaaaa1", 2.0, snap=False)
    assert T._find(tl5, "ccccccccccc1")[1]["start"] == 1.0        # Gruppe bewegt sich mit
    assert T._find(tl, "aaaaaaaaaaa1")[1]["start"] == 1.0          # Original unverändert (rein funktional)


def test_trim_split_slip_ripple_duplicate_and_locks():
    tl = _tl()
    tl = T.set_keyframe(tl, "bbbbbbbbbbb1", "opacity", 0.0, 0.0)
    tl = T.set_keyframe(tl, "bbbbbbbbbbb1", "opacity", 2.0, 1.0)
    t2 = T.trim_item(tl, "bbbbbbbbbbb1", "start", 6.5, snap=False)
    b = T._find(t2, "bbbbbbbbbbb1")[1]
    assert (b["start"], b["duration"], b["in"]) == (6.5, 1.5, 1.5)
    assert b["keyframes"]["opacity"][0] == {"t": 0.0, "v": 0.25, "ease": "linear"}   # Kurve erhalten
    t3, right = T.split_item(tl, "bbbbbbbbbbb1", 7.0)
    left = T._find(t3, "bbbbbbbbbbb1")[1]
    assert left["duration"] == 1.0 and right["start"] == 7.0 and right["in"] == 2.0
    assert T.value_at(left, "opacity", 1.0) == pytest.approx(T.value_at(right, "opacity", 0.0)) == pytest.approx(0.5)
    t4 = T.slip_item(tl, "bbbbbbbbbbb1", 0.5, source_duration=3.0)
    assert T._find(t4, "bbbbbbbbbbb1")[1]["in"] == 1.0              # max. Quelle 3 s − Dauer 2 s
    t5 = T.ripple_delete(tl, "aaaaaaaaaaa1")
    assert T._find(t5, "bbbbbbbbbbb1")[1]["start"] == 2.0
    t6, dup = T.duplicate_item(tl, "aaaaaaaaaaa1")
    assert dup["start"] == 5.0 and dup["id"] != "aaaaaaaaaaa1"
    locked = T.set_track(tl, "ddddddddddd1", locked=True)
    with pytest.raises(StudioError):
        T.move_item(locked, "aaaaaaaaaaa1", 3)
    with pytest.raises(StudioError):
        T.set_keyframe(tl, "ccccccccccc1", "rotation", 0, 10)       # Audio hat keine Drehung


def _eval_expr(expr: str, t: float) -> float:
    py = expr.replace("if(", "IF(").replace("lt(", "LT(")
    return eval(py, {"IF": lambda c, a, b: a if c else b, "LT": lambda a, b: a < b, "t": t})  # noqa: S307


@pytest.mark.parametrize("ease", T.EASES)
def test_keyframe_expression_matches_python_curve(ease):
    item = {"keyframes": {"x": [{"t": 0.5, "v": 0.2, "ease": ease}, {"t": 2.0, "v": 0.8, "ease": ease},
                                 {"t": 3.0, "v": 0.4, "ease": "linear"}]}}
    expr = T.keyframe_expr(item, "x", "t", 0.5)
    for t in (0.0, 0.5, 0.9, 1.25, 1.99, 2.0, 2.5, 3.0, 4.0):
        assert _eval_expr(expr, t) == pytest.approx(T.value_at(item, "x", t), abs=1e-4), (ease, t)


def _png(path, color, size="200x200"):
    subprocess.run(["ffmpeg", "-y", "-v", "error", "-f", "lavfi", "-i", f"color=c={color}:s={size}:d=1",
                    "-frames:v", "1", path], check=True)
    return path


def _rgb_at(video, t, w=72, h=128):
    raw = subprocess.run(["ffmpeg", "-v", "error", "-ss", str(t), "-i", video, "-frames:v", "1", "-vf",
                          f"scale={w}:{h}", "-f", "rawvideo", "-pix_fmt", "rgb24", "-"],
                         capture_output=True, check=True).stdout
    return lambda x, y: tuple(raw[(y * w + x) * 3:(y * w + x) * 3 + 3])


def _peaks(path):
    err = subprocess.run(["ffmpeg", "-v", "info", "-i", path, "-af",
                          "astats=metadata=1:reset=1,ametadata=print:key=lavfi.astats.Overall.Peak_level",
                          "-f", "null", "-"], capture_output=True, text=True).stderr
    times = [float(x) for x in re.findall(r"pts_time:([\d.]+)", err)]
    peaks = [float(x) if x != "-inf" else -200 for x in re.findall(r"Peak_level=(-?[\w.]+)", err)]
    return [t for t, p in zip(times, peaks) if p > -20]


def test_timeline_only_render_with_keyframes_audio_and_captions(tmp_path):
    svc, _ = make_service(str(tmp_path))
    p = svc.create_project({"workflow": "media", "title": "TL", "resolution": "720p"})
    with open(_png(str(tmp_path / "red.png"), "red"), "rb") as fh:
        red = svc.upload_media(p["id"], "red.png", fh)["name"]
    with open(make_click_wav(str(tmp_path / "c.wav"), 0.5), "rb") as fh:
        click = svc.upload_media(p["id"], "c.wav", fh)["name"]
    p = svc.store.load(p["id"])
    tl = {"tracks": [
        {"kind": "overlay", "name": "Grafik", "items": [{
            "src": red, "start": 0.0, "duration": 3.0, "scale": 0.25, "y": 0.5,
            "keyframes": {"x": [{"t": 0, "v": 0.2}, {"t": 2.0, "v": 0.8, "ease": "ease_in_out"}],
                          "rotation": [{"t": 0, "v": 0}, {"t": 3, "v": 45}]}}]},
        {"kind": "audio", "name": "SFX", "items": [{"src": click, "start": 1.5, "duration": 0.5}]},
        {"kind": "caption", "name": "Text", "items": [{"text": "HALLO", "start": 0.5, "duration": 2.0,
                                                       "color": "#ffff00", "position": "top"}]}]}
    svc.update_project(p["id"], {"timeline": tl, "scenes": []}, p["version"])
    t = svc.tasks.submit("render", p["id"], {"mode": "preview"}, run_inline=True)
    assert t["status"] == "succeeded", t
    rep = svc.list_renders(p["id"])[0]
    assert rep["timeline"]["visual_items"] == 1 and rep["timeline"]["audio_items"] == 1
    assert rep["timeline"]["caption_items"] == 1 and abs(rep["duration"] - 3.0) < 0.15
    path = svc.render_file(p["id"], rep["render_id"])
    early, late = _rgb_at(path, 0.05), _rgb_at(path, 2.5)
    assert early(14, 64)[0] > 150 and early(57, 64)[0] < 60        # links rot, rechts schwarz
    assert late(57, 64)[0] > 150 and late(14, 64)[0] < 60          # Keyframe hat bewegt
    loud = _peaks(path)
    assert loud and 1.3 <= min(loud) <= 1.7                        # Effekt an seiner Position


def test_overlay_on_scene_project_and_old_projects_unchanged(tmp_path):
    svc, _ = make_service(str(tmp_path))
    p = svc.create_project({"workflow": "script", "title": "S", "script": "Eins zwei drei. Vier fünf.",
                            "voice": {"provider": "mock"}, "resolution": "720p"})
    svc.tasks.submit("ingest", p["id"], {}, run_inline=True)
    t = svc.tasks.submit("render", p["id"], {"mode": "preview"}, run_inline=True)
    assert t["status"] == "succeeded" and "timeline" not in svc.list_renders(p["id"])[0]
    with open(_png(str(tmp_path / "g.png"), "lime"), "rb") as fh:
        g = svc.upload_media(p["id"], "g.png", fh)["name"]
    p = svc.store.load(p["id"])
    tl = {"tracks": [{"kind": "overlay", "items": [{"src": g, "start": 0.2, "duration": 1.5, "x": 0.85,
                                                     "y": 0.15, "scale": 0.2,
                                                     "keyframes": {"opacity": [{"t": 0, "v": 0}, {"t": 0.5, "v": 1}]}}]}]}
    svc.update_project(p["id"], {"timeline": tl}, p["version"])
    t = svc.tasks.submit("render", p["id"], {"mode": "preview"}, run_inline=True)
    assert t["status"] == "succeeded", t
    rep = svc.list_renders(p["id"])[0]
    path = svc.render_file(p["id"], rep["render_id"])
    px = _rgb_at(path, 1.2)(61, 19)
    assert px[1] > 180 and px[0] < 100                              # grünes Logo oben rechts
    assert _rgb_at(path, 0.21)(61, 19)[1] < 150                     # noch eingeblendet (Deckkraft-Keyframe)
    assert rep["timeline"]["keyframed_props"] == 1


def test_patch_api_accepts_timeline_and_audio(tmp_path):
    """Regression: PATCH /projects ignorierte 'audio' und 'timeline' (UI-Speichern wirkungslos)."""
    from studio_helpers import make_client, wait_task
    client, _ = make_client(str(tmp_path))
    r = client.post("/api/studio/projects", json={"workflow": "script", "script": "Eins. Zwei. Drei."})
    pid = r.json()["project"]["id"]
    wait_task(client, r.json()["task_id"])
    v = client.get(f"/api/studio/projects/{pid}").json()["project"]["version"]
    tl = {"tracks": [{"kind": "caption", "locked": True, "items": [{"text": "x", "start": 0, "duration": 1}]}]}
    r = client.patch(f"/api/studio/projects/{pid}", json={"expected_version": v, "audio": {"loudnorm": True},
                                                            "timeline": tl})
    assert r.status_code == 200, r.text
    p = r.json()["project"]
    assert p["audio"]["loudnorm"] is True and p["timeline"]["tracks"][0]["locked"] is True


def test_preview_keeps_base_layer_without_overlays(tmp_path):
    """Live-Vorschau braucht die Grundebene OHNE Timeline-Spuren (sonst doppelte Overlays)."""
    from studio_helpers import make_client, wait_task
    client, app_module = make_client(str(tmp_path))
    r = client.post("/api/studio/projects", json={"workflow": "script", "voice": {"provider": "mock"},
                                                  "script": "Hallo und willkommen. Heute zeige ich dir drei Tricks."})
    pid = r.json()["project"]["id"]
    wait_task(client, r.json()["task_id"])
    with open(_png(str(tmp_path / "g.png"), "lime"), "rb") as fh:
        name = client.post(f"/api/studio/projects/{pid}/media", files={"file": ("g.png", fh, "image/png")}).json()["name"]
    v = client.get(f"/api/studio/projects/{pid}").json()["project"]["version"]
    client.post(f"/api/studio/projects/{pid}/timeline/ops", json={"expected_version": v, "ops": [
        {"op": "add_item", "track_kind": "overlay", "item": {"src": name, "start": 0, "duration": 2, "x": 0.85,
                                                              "y": 0.15, "scale": 0.2}}]})
    t = wait_task(client, client.post(f"/api/studio/projects/{pid}/render", json={"mode": "preview"}).json()["task"]["id"], 300)
    assert t["status"] == "succeeded", t
    rid = t["result"]["render_id"]
    rep = client.get(f"/api/studio/projects/{pid}").json()["renders"][0]
    assert rep["base_file"] == f"{rid}.base.mp4"
    base = client.get(f"/api/studio/projects/{pid}/renders/{rid}/base")
    assert base.status_code == 200
    path = str(tmp_path / "base.mp4")
    open(path, "wb").write(base.content)
    assert _rgb_at(path, 0.5, 36, 64)(30, 9)[1] < 150          # kein grünes Overlay in der Grundebene
    final = app_module.studio.service.render_file(pid, rid)
    assert _rgb_at(final, 0.5, 36, 64)(30, 9)[1] > 180          # im Render schon
