"""Studio: Renderer, Beat-Erkennung, Budgetgrenze, Provider-Ausfall (echtes FFmpeg)."""

from __future__ import annotations

import os
import shutil
import subprocess
import tempfile

from studio_helpers import (
    clear_env, ffprobe, make_click_wav, make_png, make_service, make_video, run_all,
)

from clipforge.studio import audio
from clipforge.studio.costs import CostLedger, estimate_project
from clipforge.studio.errors import StudioError
from clipforge.studio.providers import remote, select_voice
from clipforge.studio.render import dimensions

SCRIPT = ("Lokale Videotools sparen Zeit und Geld. Alles bleibt auf deinem Rechner. "
          "Jede Szene bleibt bearbeitbar. Folge für mehr.")


def _ready(svc, **extra):
    p = svc.create_project({"workflow": "script", "title": "Render", "script": SCRIPT,
                            "voice": {"provider": "mock"}, "resolution": "720p", **extra})
    t = svc.tasks.submit("ingest", p["id"], {}, run_inline=True)
    assert t["status"] == "succeeded", t
    return svc.store.load(p["id"])


def _render(svc, pid, mode="preview"):
    t = svc.tasks.submit("render", pid, {"mode": mode}, run_inline=True)
    return t, (svc.list_renders(pid)[0] if t["status"] == "succeeded" else None)


def test_dimensions_for_all_aspect_ratios_and_resolutions():
    assert dimensions("9:16", "1080p") == (1080, 1920)
    assert dimensions("16:9", "1080p") == (1920, 1080)
    assert dimensions("1:1", "1080p") == (1080, 1080)
    assert dimensions("4:5", "1080p") == (1080, 1350)
    assert dimensions("9:16", "720p") == (720, 1280)
    assert dimensions("16:9", "4k") == (3840, 2160)
    assert dimensions("9:16", "4k") == (2160, 3840)
    assert dimensions("9:16", "1080p", preview=True) == (360, 640)
    assert all(v % 2 == 0 for ar in ("9:16", "16:9", "1:1", "4:5")
               for res in ("720p", "1080p", "4k") for v in dimensions(ar, res))


def test_final_render_is_a_real_video_checked_with_ffprobe():
    tmp = tempfile.mkdtemp(prefix="rend_")
    try:
        svc, _ = make_service(tmp)
        p = _ready(svc, captions={"style": "dynamic"})
        task, report = _render(svc, p["id"], "final")
        assert task["status"] == "succeeded", task
        path = svc.render_file(p["id"], report["render_id"])
        info = ffprobe(path)
        video = next(s for s in info["streams"] if s["codec_type"] == "video")
        audio_s = next(s for s in info["streams"] if s["codec_type"] == "audio")
        assert (video["width"], video["height"]) == (720, 1280)
        assert video["codec_name"] == "h264" and video["pix_fmt"] == "yuv420p"
        assert audio_s["codec_name"] == "aac"
        duration = float(info["format"]["duration"])
        assert abs(duration - report["expected"]["duration"]) < 0.5 and duration > 3
        assert report["quality"]["passed"] and report["captions"]["caption_blocks_count"] > 0
        assert report["captions"]["applied_mode"] == "karaoke"
        assert report["word_timing"] == ["estimated"]
        assert len(report["scenes"]) == len(p["scenes"])
        assert report["costs"]["spent_usd"] == 0
    finally:
        clear_env()
        shutil.rmtree(tmp, ignore_errors=True)


def test_aspect_ratios_caption_styles_and_cinematic_render():
    tmp = tempfile.mkdtemp(prefix="rend_")
    try:
        svc, _ = make_service(tmp)
        p = _ready(svc)
        for ar, style, look, size in (("16:9", "minimal", "clean", (640, 360)),
                                      ("1:1", "bold", "cinematic", (360, 360)),
                                      ("4:5", "none", "clean", (360, 450))):
            p = svc.update_project(p["id"], {"aspect_ratio": ar, "captions": {"style": style},
                                             "style": look}, p["version"])
            task, _ = _render(svc, p["id"])
            assert task["status"] == "succeeded", task
            report = svc.get_render(p["id"], task["result"]["render_id"])
            assert (report["width"], report["height"]) == size, (ar, report["width"])
            assert report["captions"]["studio_style"] == style
            if style == "none":
                assert report["captions"]["caption_blocks_count"] == 0
            else:
                assert report["captions"]["caption_blocks_count"] > 0
    finally:
        clear_env()
        shutil.rmtree(tmp, ignore_errors=True)


def test_editor_changes_change_the_render():
    """Dauer, Reihenfolge und eigene Medien wirken sich messbar auf das Video aus."""
    tmp = tempfile.mkdtemp(prefix="rend_")
    try:
        svc, _ = make_service(tmp)
        p = _ready(svc)
        _, before = _render(svc, p["id"])
        pdir = svc.store.dir(p["id"])
        make_png(os.path.join(pdir, "media", "bild.png"))
        make_video(os.path.join(pdir, "media", "clip.mp4"))
        scenes = [dict(s) for s in p["scenes"]]
        scenes[0] = {**scenes[0], "duration": 9.0, "visual": {"mode": "media", "media": "bild.png"}}
        scenes[1] = {**scenes[1], "visual": {"mode": "media", "media": "clip.mp4"}}
        scenes.append({"text": "Zusatzszene ganz am Ende", "visual": {"mode": "static",
                                                                       "color": "#112233"}})
        p = svc.update_project(p["id"], {"scenes": scenes}, p["version"])
        _, after = _render(svc, p["id"])
        assert after["scenes"][0]["duration"] == 9.0
        assert after["duration"] > before["duration"] + 3
        assert [s["visual_mode"] for s in after["scenes"]][:2] == ["media", "media"]
        assert after["scenes"][-1]["visual_mode"] == "static"
        assert after["project_version"] == p["version"]
    finally:
        clear_env()
        shutil.rmtree(tmp, ignore_errors=True)


def test_split_screen_with_and_without_gameplay():
    tmp = tempfile.mkdtemp(prefix="rend_")
    try:
        svc, _ = make_service(tmp)
        p = _ready(svc)
        scenes = [{**s, "visual": {"mode": "split"}} for s in p["scenes"]]
        p = svc.update_project(p["id"], {"scenes": scenes}, p["version"])
        assert any(c["id"] == "split_no_gameplay" for c in svc.quality(p["id"])["checks"])
        _, report = _render(svc, p["id"])
        assert any("Split-Screen ohne Gameplay" in w for w in report["warnings"])
        make_video(os.path.join(svc.store.dir(p["id"]), "media", "game.mp4"), 1.0)
        p = svc.update_project(p["id"], {"visuals": {"gameplay_media": "game.mp4"}}, p["version"])
        task, report = _render(svc, p["id"])
        assert task["status"] == "succeeded" and report["warnings"] == []
        assert (report["width"], report["height"]) == (360, 640)
    finally:
        clear_env()
        shutil.rmtree(tmp, ignore_errors=True)


def test_beat_detection_finds_known_tempo():
    tmp = tempfile.mkdtemp(prefix="beat_")
    try:
        for bpm in (100.0, 120.0, 140.0):
            info = audio.detect_beats(make_click_wav(os.path.join(tmp, f"c{bpm}.wav"), 10.0, bpm))
            assert info["bpm"] is not None and abs(info["bpm"] - bpm) < 3.0, (bpm, info["bpm"])
            period = 60.0 / bpm
            gaps = [b - a for a, b in zip(info["beats"], info["beats"][1:])]
            assert all(abs(g - period) < 0.03 for g in gaps)
            assert min(abs((info["beats"][0] % period) - x) for x in (0.0, period)) < 0.06
        silent = os.path.join(tmp, "silent.wav")
        subprocess.run(["ffmpeg", "-y", "-v", "error", "-f", "lavfi", "-i",
                        "anullsrc=r=22050:cl=mono", "-t", "4", silent], check=True)
        assert audio.detect_beats(silent) == {"bpm": None, "beats": [], "confidence": 0.0}
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def test_snap_durations_cuts_on_beats_and_respects_minimums():
    beats = [i * 0.5 for i in range(40)]
    out = audio.snap_durations([1.2, 2.3, 0.9], [0.0, 0.0, 0.0], beats)
    cuts = [sum(out[: i + 1]) for i in range(3)]
    assert all(abs(c / 0.5 - round(c / 0.5)) < 1e-6 for c in cuts)
    assert out == [1.0, 2.5, 1.0]
    assert audio.snap_durations([1.0], [2.2], beats) == [2.5]  # nie kürzer als die Stimme
    assert audio.snap_durations([3.0, 3.0], [0, 0], [0.0, 0.5, 1.0]) == [3.0, 3.0]  # Raster fortgesetzt
    assert audio.snap_durations([1.3], [0.0], []) == [1.3]


def test_music_video_is_beat_synced_and_ducking_filter_is_used():
    tmp = tempfile.mkdtemp(prefix="rend_")
    try:
        svc, _ = make_service(tmp)
        p = svc.create_project({"workflow": "music", "title": "Beat", "resolution": "720p"})
        pdir = svc.store.dir(p["id"])
        click = make_click_wav(os.path.join(tmp, "click.wav"), 12.0, 120.0)
        with open(click, "rb") as fh:
            svc.upload_source(p["id"], "click.wav", fh)
        t = svc.tasks.submit("ingest", p["id"], {}, run_inline=True)
        assert t["status"] == "succeeded", t
        p = svc.store.load(p["id"])
        assert p["music"]["track"] == "project:track.wav" and p["music"]["beat_sync"]
        assert len(p["scenes"]) == 8
        beats = svc.get_artifact(p["id"], "beats.json")
        assert abs(beats["bpm"] - 120.0) < 3
        task, report = _render(svc, p["id"])
        assert task["status"] == "succeeded", task
        assert report["music"]["beat_synced"] and abs(report["music"]["bpm"] - 120) < 3
        for scene in report["scenes"]:  # jeder Schnitt liegt auf dem 0,5-s-Beatraster
            end = scene["start"] + scene["duration"]
            offset = (end - beats["beats"][0]) / 0.5
            assert abs(offset - round(offset)) < 0.08, (scene, offset)
        assert report["has_audio"]
        assert os.path.isfile(os.path.join(pdir, "media", "track.wav"))
    finally:
        clear_env()
        shutil.rmtree(tmp, ignore_errors=True)


def test_ducking_lowers_music_under_voice():
    """Mit Ducking ist die Musik unter dem Voice-over messbar leiser als ohne."""
    tmp = tempfile.mkdtemp(prefix="rend_")
    try:
        svc, _ = make_service(tmp)
        os.makedirs(audio.music_dir(), exist_ok=True)
        subprocess.run(["ffmpeg", "-y", "-v", "error", "-f", "lavfi", "-i", "sine=f=2000:d=20",
                        os.path.join(audio.music_dir(), "bed.wav")], check=True)
        p = _ready(svc)

        def band_level(ducking: bool) -> float:
            nonlocal p
            p = svc.update_project(p["id"], {"music": {"track": "library:bed.wav", "volume": 0.5,
                                                       "ducking": ducking}}, p["version"])
            _, report = _render(svc, p["id"])
            path = svc.render_file(p["id"], report["render_id"])
            out = subprocess.run(
                ["ffmpeg", "-v", "info", "-i", path, "-af",
                 "bandpass=f=2000:width_type=h:w=200,volumedetect", "-f", "null", "-"],
                capture_output=True, text=True).stderr
            return float(out.split("mean_volume:")[1].split("dB")[0])
        assert band_level(False) - band_level(True) > 3.0
    finally:
        clear_env()
        shutil.rmtree(tmp, ignore_errors=True)


def test_budget_hard_stop_before_any_paid_call():
    tmp = tempfile.mkdtemp(prefix="rend_")
    calls = []
    original = remote.HTTP_POST
    try:
        svc, _ = make_service(tmp, OPENAI_API_KEY="test-key-not-real")
        mp3 = os.path.join(tmp, "v.mp3")
        subprocess.run(["ffmpeg", "-y", "-v", "error", "-f", "lavfi", "-i", "sine=f=300:d=1.2",
                        mp3], check=True)
        blob = open(mp3, "rb").read()

        def fake_post(url, headers, payload, timeout=120.0):
            calls.append(url)
            return blob
        remote.HTTP_POST = fake_post
        p = _ready(svc, voice={"provider": "openai_tts"})
        est = svc.estimate(p["id"])
        assert est["total_usd"] > 0 and est["is_estimate"] and not est["within_budget"]
        # 1) Budget 0 → Vorab-Prüfung verweigert den Start, kein Call
        try:
            svc.start_render(p["id"], "preview")
            raise AssertionError("budget_exceeded erwartet")
        except StudioError as exc:
            assert exc.code == "budget_exceeded" and exc.status == 409
        assert calls == []
        # 2) Budget reicht nur für die erste Szene → harter Abbruch mitten im Lauf
        first = len(p["scenes"][0]["text"])
        tight = first / 1000.0 * 0.015 * 1.01
        p = svc.update_project(p["id"], {"budget_limit_usd": tight}, p["version"])
        task = svc.tasks.submit("render", p["id"], {"mode": "preview"}, run_inline=True)
        assert task["status"] == "failed" and task["error"]["code"] == "budget_exceeded"
        assert len(calls) == 1  # genau EIN bezahlter Call, danach Stopp
        ledger = CostLedger(svc.store.dir(p["id"]), tight)
        assert 0 < ledger.spent <= tight
        assert svc.list_renders(p["id"]) == []  # kein halbes Video
        # 3) genug Budget → läuft durch; bereits bezahlte Szene wird NICHT erneut berechnet
        p = svc.update_project(p["id"], {"budget_limit_usd": 1.0}, p["version"])
        task = svc.tasks.submit("render", p["id"], {"mode": "preview"}, run_inline=True)
        assert task["status"] == "succeeded", task
        assert len(calls) == len(p["scenes"])
        spent = CostLedger(svc.store.dir(p["id"]), 1.0).spent
        assert abs(spent - est["total_usd"]) < 1e-3
        # 4) erneuter Render: alles aus dem Cache, keine neuen Kosten
        svc.tasks.submit("render", p["id"], {"mode": "preview"}, run_inline=True)
        assert len(calls) == len(p["scenes"])
        assert CostLedger(svc.store.dir(p["id"]), 1.0).spent == spent
    finally:
        remote.HTTP_POST = original
        clear_env("OPENAI_API_KEY")
        shutil.rmtree(tmp, ignore_errors=True)


def test_provider_outage_falls_back_and_never_leaks_key():
    tmp = tempfile.mkdtemp(prefix="rend_")
    original = remote.HTTP_POST
    secret = "sentinel-secret-key-value"
    try:
        svc, _ = make_service(tmp, OPENAI_API_KEY=secret)

        def down(url, headers, payload, timeout=120.0):
            raise ConnectionError(f"boom {headers}")
        remote.HTTP_POST = down
        p = _ready(svc, voice={"provider": "openai_tts"}, budget_limit_usd=5)
        scenes = [{**s, "visual": {"mode": "ai_image"}} for s in p["scenes"]]
        p = svc.update_project(p["id"], {"scenes": scenes}, p["version"])
        task, report = _render(svc, p["id"])
        assert task["status"] == "succeeded", task
        kinds = {f["kind"] for f in report["fallbacks"]}
        assert kinds == {"voice", "image"}
        assert report["costs"]["spent_usd"] == 0  # Ausfall kostet nichts
        assert report["has_audio"] and report["quality"]["passed"]
        blob = str(report) + str(task) + str(svc.project_view(p["id"]))
        assert secret not in blob
        from clipforge.studio.providers import readiness
        info = str(readiness())
        assert secret not in info and "OPENAI_API_KEY" in info
    finally:
        remote.HTTP_POST = original
        clear_env("OPENAI_API_KEY")
        shutil.rmtree(tmp, ignore_errors=True)


def test_unconfigured_providers_are_reported_not_used():
    tmp = tempfile.mkdtemp(prefix="rend_")
    try:
        svc, _ = make_service(tmp)
        clear_env("OPENAI_API_KEY", "ELEVENLABS_API_KEY")
        os.environ["CLIPFORGE_STUDIO_DIR"] = os.path.join(tmp, "studio")
        os.environ["CLIPFORGE_FLAG_STUDIO_MOCK_PROVIDERS"] = "true"
        from clipforge.studio.providers import readiness
        states = {r["id"]: r["status"] for r in readiness()}
        assert states["elevenlabs"] == "not_configured" and states["openai_tts"] == "not_configured"
        # Adapter vorhanden, aber ohne FAL_KEY bzw. ELEVENLABS_API_KEY nicht nutzbar
        assert states["fal_video"] == "not_configured" and states["fal_avatar"] == "not_configured"
        assert states["elevenlabs_clone"] == "not_configured"
        assert states["face_swap"] == "unavailable"
        assert states["none"] == "ready"
        # Auto-Auswahl nimmt nie einen bezahlten/Mock-Provider ungefragt
        auto = select_voice("de", "calm")
        assert auto["provider"] in ("none", "macos_say", "espeak")
        try:
            select_voice("de", "", "elevenlabs")
            raise AssertionError("provider_not_configured erwartet")
        except StudioError as exc:
            assert exc.code == "provider_not_configured" and "ELEVENLABS_API_KEY" in exc.message
        p = _ready(svc)
        assert estimate_project(p)["total_usd"] == 0
    finally:
        clear_env()
        shutil.rmtree(tmp, ignore_errors=True)


def test_single_scene_regeneration_only_touches_that_scene():
    tmp = tempfile.mkdtemp(prefix="rend_")
    try:
        svc, _ = make_service(tmp)
        p = _ready(svc)
        target, other = p["scenes"][1], p["scenes"][0]
        svc.tasks._pool.shutdown(wait=True)  # deterministisch: Task inline nachziehen
        from concurrent.futures import ThreadPoolExecutor
        svc.tasks._pool = ThreadPoolExecutor(max_workers=1)
        res = svc.regenerate_scene(p["id"], target["id"], p["version"], "neuer Bildprompt")
        svc.tasks._pool.shutdown(wait=True)
        after = svc.store.load(p["id"])
        new_target = next(s for s in after["scenes"] if s["id"] == target["id"])
        assert new_target["visual"]["seed"] == target["visual"]["seed"] + 1
        assert new_target["visual_prompt"] == "neuer Bildprompt"
        assert next(s for s in after["scenes"] if s["id"] == other["id"]) == other
        task = svc.tasks.get(res["task"]["id"])
        assert task["status"] == "succeeded", task
        assert task["result"]["mode"] == "scene" and task["result"]["scene_id"] == target["id"]
        report = svc.get_render(p["id"], task["result"]["render_id"])
        assert len(report["scenes"]) == 1 and report["scenes"][0]["id"] == target["id"]
        assert os.path.isfile(svc.render_file(p["id"], task["result"]["render_id"]))
        try:
            svc.regenerate_scene(p["id"], target["id"], p["version"])  # veraltete Version
            raise AssertionError("version_conflict erwartet")
        except StudioError as exc:
            assert exc.code == "version_conflict"
    finally:
        clear_env()
        shutil.rmtree(tmp, ignore_errors=True)


def test_quality_blocks_forbidden_claims_and_empty_projects():
    tmp = tempfile.mkdtemp(prefix="rend_")
    try:
        svc, _ = make_service(tmp)
        p = _ready(svc)
        scenes = [{**p["scenes"][0], "text": "Dieses Video geht garantiert viral!"}]
        p = svc.update_project(p["id"], {"scenes": scenes}, p["version"])
        q = svc.quality(p["id"])
        assert q["blocking"] and any(c["id"] == "forbidden_claim" for c in q["checks"])
        try:
            svc.start_render(p["id"], "preview")
            raise AssertionError("quality_blocked erwartet")
        except StudioError as exc:
            assert exc.code == "quality_blocked"
        p = svc.update_project(p["id"], {"scenes": []}, p["version"])
        assert svc.quality(p["id"])["blocking"]
    finally:
        clear_env()
        shutil.rmtree(tmp, ignore_errors=True)


if __name__ == "__main__":
    run_all(globals())
