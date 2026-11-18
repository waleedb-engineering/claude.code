"""Studio-Härtung: Optionen bis in den Output, Gesamtbudget unter Last,
Credentials ohne Neustart, Local-API-Schutz, Cancel, Restart-Recovery."""

from __future__ import annotations

import io
import os
import shutil
import stat
import subprocess
import sys
import tempfile
import threading

from studio_helpers import (
    clear_env, ffprobe, make_client, make_pdf, make_png, make_service, make_tone_wav,
    run_all, wait_task,
)

from clipforge.studio import credentials
from clipforge.studio.costs import CostLedger
from clipforge.studio.errors import BudgetExceeded, StudioError
from clipforge.studio.options import ProductionOptions
from clipforge.studio.providers import remote

SCRIPT = ("Lokale Videotools sparen Zeit und Geld. Alles bleibt auf deinem Rechner. "
          "Jede Szene bleibt bearbeitbar. Folge für mehr.")
ALL_OPTIONS = {
    "platform": "x", "duration_target": 30, "goal": "Newsletter-Anmeldungen",
    "audience": "Solo-Creator", "cta": "Jetzt den Newsletter abonnieren.",
    "creative_instructions": "kurze Sätze", "forbidden_topics": ["Politik", "krypto"],
    "visual_style": "warmes Abendlicht", "media_type": "static", "image_animation": False,
    "voice_model": "tts-1-hd", "music_mode": "none",
}


def _code(fn) -> str:
    try:
        fn()
    except StudioError as exc:
        return exc.code
    return "no_error"


def _mp3(tmp: str) -> bytes:
    path = os.path.join(tmp, "v.mp3")
    subprocess.run(["ffmpeg", "-y", "-v", "error", "-f", "lavfi", "-i", "sine=f=300:d=1.0", path],
                   check=True)
    return open(path, "rb").read()


# ------------------------------------------------------------- Optionen (1, 4)

def test_all_options_survive_api_storage_and_reach_the_pipeline():
    tmp = tempfile.mkdtemp(prefix="hard_")
    posts = []
    original = remote.HTTP_POST
    try:
        client, app_module = make_client(tmp, OPENAI_API_KEY="test-key-not-real")
        blob = _mp3(tmp)
        remote.HTTP_POST = lambda url, headers, payload, timeout=120.0: posts.append(payload) or blob
        text = ("Gute Newsletter haben einen klaren Nutzen fuer Leser. "
                "Politik gehoert nicht in diesen Newsletter hinein. "
                "Ein fester Versandtag hilft den Lesern sehr. "
                "Krypto Tipps sind hier ebenfalls kein Thema. "
                "Kurze Betreffzeilen werden deutlich oefter geoeffnet.")
        r = client.post("/api/studio/projects", json={
            "workflow": "prompt", "prompt": text, "language": "de", "tone": "calm",
            "resolution": "720p", "captions": {"style": "bold"}, "budget_limit_usd": 2,
            "voice": {"provider": "openai_tts", "voice_id": "onyx"}, "options": ALL_OPTIONS})
        assert r.status_code == 201, r.text
        pid = r.json()["project"]["id"]
        assert wait_task(client, r.json()["task_id"])["status"] == "succeeded"
        p = client.get(f"/api/studio/projects/{pid}").json()["project"]
        # 1) gespeichert = angefragt (eine Source of Truth, nichts verloren)
        assert p["options"] == ProductionOptions.from_dict(ALL_OPTIONS).to_dict()
        assert p["aspect_ratio"] == "16:9"            # Plattform X bestimmt das Format
        assert (p["tone"], p["language"], p["workflow"]) == ("calm", "de", "prompt")
        # 2) im Skript sichtbar: verbotene Themen raus, CTA wörtlich, Stil im Prompt, Medientyp
        texts = [s["text"] for s in p["scenes"]]
        joined = " ".join(texts).lower()
        assert "politik" not in joined and "krypto" not in joined
        assert texts[-1] == "Jetzt den Newsletter abonnieren." and p["scenes"][-1]["kind"] == "cta"
        assert all("warmes Abendlicht" in s["visual_prompt"] for s in p["scenes"])
        assert {s["visual"]["mode"] for s in p["scenes"]} == {"static"}
        script = client.get(f"/api/studio/projects/{pid}/artifacts/script.json").json()
        assert script["options"]["goal"] == "Newsletter-Anmeldungen"
        assert any("ausgeschlossener Themen" in n for n in script["notes"])
        # 3) im Render sichtbar: Format, Provider, Stimme, Modell
        t = wait_task(client, client.post(f"/api/studio/projects/{pid}/render",
                                          json={"mode": "final"}).json()["task"]["id"])
        assert t["status"] == "succeeded", t
        report = client.get(f"/api/studio/projects/{pid}/renders").json()["renders"][0]
        assert (report["width"], report["height"]) == (1280, 720)
        assert report["voice"]["provider"] == "openai_tts" and report["voice"]["voice_id"] == "onyx"
        assert report["options"]["voice_model"] == "tts-1-hd"
        assert posts and all(x["model"] == "tts-1-hd" and x["voice"] == "onyx" for x in posts)
        assert report["captions"]["studio_style"] == "bold"
        assert {s["visual_mode"] for s in report["scenes"]} == {"static"}
        # 4) Optionen überleben Duplicate und Editor-Patch; Qualitätsprüfung nutzt sie
        dup = client.post(f"/api/studio/projects/{pid}/duplicate", json={}).json()["project"]
        assert dup["options"] == p["options"] and dup["id"] != pid
        scenes = p["scenes"]
        scenes[0] = {**scenes[0], "text": "Heute reden wir über Politik."}
        r = client.patch(f"/api/studio/projects/{pid}", json={
            "expected_version": p["version"], "scenes": scenes,
            "options": {"platform": "instagram_reels"}})
        assert r.status_code == 200
        saved = r.json()["project"]["options"]
        assert saved["platform"] == "instagram_reels" and saved["cta"] == ALL_OPTIONS["cta"]
        q = client.get(f"/api/studio/projects/{pid}/quality").json()
        assert q["blocking"] and any(c["id"] == "forbidden_topic" for c in q["checks"])
        r = client.post(f"/api/studio/projects/{pid}/render", json={"mode": "preview"})
        assert r.status_code == 409 and r.json()["detail"]["code"] == "quality_blocked"
    finally:
        remote.HTTP_POST = original
        clear_env("OPENAI_API_KEY")
        shutil.rmtree(tmp, ignore_errors=True)


def test_option_validation_and_unavailable_choices_are_explicit():
    tmp = tempfile.mkdtemp(prefix="hard_")
    try:
        client, _ = make_client(tmp)
        post = lambda opts: client.post("/api/studio/projects", json={  # noqa: E731
            "workflow": "script", "script": SCRIPT, "options": opts})
        for bad in ({"platform": "myspace"}, {"media_type": "hologram"}, {"music_mode": "auto"},
                    {"duration_target": "lang"}):
            r = post(bad)
            assert r.status_code == 400 and r.json()["detail"]["code"] == "validation_error", bad
        r = post({"video_provider": "runway", "video_model": "gen-3"})
        assert r.status_code == 409 and r.json()["detail"]["code"] == "provider_unknown"
        assert "verfügbar: fal_video" in r.json()["detail"]["message"]
        assert client.get("/api/studio/projects").json()["projects"] == []
        r = client.post("/api/studio/projects", json={"workflow": "gibt_es_nicht", "prompt": "x y z"})
        assert r.json()["detail"]["code"] == "validation_error"  # kein stilles Prompt-to-Video
    finally:
        clear_env()
        shutil.rmtree(tmp, ignore_errors=True)


def test_script_workflow_keeps_user_text_verbatim_despite_options():
    tmp = tempfile.mkdtemp(prefix="hard_")
    try:
        svc, _ = make_service(tmp)
        text = "Erster Satz über Politik. Zweiter Satz bleibt genau so. Dritter Satz auch."
        p = svc.create_project({"workflow": "script", "script": text,
                                "options": {"forbidden_topics": ["politik"], "cta": "Abo!"}})
        svc.tasks.submit("ingest", p["id"], {}, run_inline=True)
        p = svc.store.load(p["id"])
        assert " ".join(s["text"] for s in p["scenes"]) == text
        assert svc.quality(p["id"])["blocking"]  # Verstoß wird gemeldet, nicht still umgeschrieben
    finally:
        clear_env()
        shutil.rmtree(tmp, ignore_errors=True)


def test_image_animation_and_music_mode_change_the_render():
    tmp = tempfile.mkdtemp(prefix="hard_")
    try:
        svc, _ = make_service(tmp)
        from clipforge.studio import audio
        subprocess.run(["ffmpeg", "-y", "-v", "error", "-f", "lavfi", "-i", "sine=f=2000:d=10",
                        os.path.join(audio.music_dir(), "bed.wav")], check=True)
        p = svc.create_project({"workflow": "script", "script": SCRIPT, "resolution": "720p",
                                "music": {"track": "library:bed.wav", "volume": 0.8},
                                "options": {"image_animation": False, "music_mode": "none"}})
        svc.tasks.submit("ingest", p["id"], {}, run_inline=True)
        p = svc.store.load(p["id"])
        make_png(os.path.join(svc.store.dir(p["id"]), "media", "bild.png"))
        scenes = [{**s, "visual": {"mode": "media", "media": "bild.png"}} for s in p["scenes"]]
        p = svc.update_project(p["id"], {"scenes": scenes}, p["version"])
        t = svc.tasks.submit("render", p["id"], {"mode": "preview"}, run_inline=True)
        assert t["status"] == "succeeded", t
        off = svc.list_renders(p["id"])[0]
        assert off["music"]["track"] is None and off["has_audio"]  # music_mode=none gewinnt
        p = svc.update_project(p["id"], {"options": {"music_mode": "track",
                                                     "image_animation": True}}, p["version"])
        svc.tasks.submit("render", p["id"], {"mode": "preview"}, run_inline=True)
        on = svc.list_renders(p["id"])[0]
        assert on["music"]["track"] == "library:bed.wav"
        assert on["options"]["image_animation"] is True and off["options"]["image_animation"] is False
        assert (on["width"], on["height"]) == (off["width"], off["height"]) == (360, 640)
    finally:
        clear_env()
        shutil.rmtree(tmp, ignore_errors=True)


# ------------------------------------------------------- Format (2, 3, 20, 21)

def test_aspect_ratio_and_quality_set_the_real_resolution():
    tmp = tempfile.mkdtemp(prefix="hard_")
    try:
        svc, _ = make_service(tmp)
        p = svc.create_project({"workflow": "script", "script": "Kurzer Test hier. Noch ein Satz."})
        svc.tasks.submit("ingest", p["id"], {}, run_inline=True)
        p = svc.store.load(p["id"])
        for ar, res, expected in (("9:16", "720p", (720, 1280)), ("16:9", "720p", (1280, 720)),
                                  ("1:1", "720p", (720, 720)), ("4:5", "720p", (720, 900)),
                                  ("4:5", "1080p", (1080, 1350)), ("16:9", "1080p", (1920, 1080))):
            p = svc.update_project(p["id"], {"aspect_ratio": ar, "resolution": res}, p["version"])
            t = svc.tasks.submit("render", p["id"], {"mode": "final"}, run_inline=True)
            assert t["status"] == "succeeded", t
            report = svc.list_renders(p["id"])[0]
            video = next(s for s in ffprobe(svc.render_file(p["id"], report["render_id"]))["streams"]
                         if s["codec_type"] == "video")
            assert (video["width"], video["height"]) == expected, (ar, res)
            assert abs(video["width"] / video["height"] - expected[0] / expected[1]) < 1e-6
        # 4:5 ist wirklich 4:5 und nicht 4:3
        assert abs(1080 / 1350 - 4 / 5) < 1e-9 and abs(1080 / 1350 - 4 / 3) > 0.5
    finally:
        clear_env()
        shutil.rmtree(tmp, ignore_errors=True)


def test_mixed_scenes_with_and_without_voice_keep_full_length_audio():
    tmp = tempfile.mkdtemp(prefix="hard_")
    try:
        svc, _ = make_service(tmp)
        p = svc.create_project({"workflow": "script", "script": SCRIPT, "resolution": "720p",
                                "voice": {"provider": "mock"}})
        svc.tasks.submit("ingest", p["id"], {}, run_inline=True)
        p = svc.store.load(p["id"])
        scenes = [p["scenes"][0],
                  {"text": "", "duration": 2.5, "visual": {"mode": "static", "color": "#223344"}},
                  p["scenes"][1],
                  {"text": "", "duration": 1.5, "visual": {"mode": "motion"}}]
        p = svc.update_project(p["id"], {"scenes": scenes}, p["version"])
        t = svc.tasks.submit("render", p["id"], {"mode": "final"}, run_inline=True)
        assert t["status"] == "succeeded", t
        report = svc.list_renders(p["id"])[0]
        info = ffprobe(svc.render_file(p["id"], report["render_id"]))
        video = next(s for s in info["streams"] if s["codec_type"] == "video")
        audio_s = next(s for s in info["streams"] if s["codec_type"] == "audio")
        planned = report["expected"]["duration"]
        assert abs(float(video["duration"]) - planned) < 0.2   # Audio verkürzt das Video nicht
        assert abs(float(audio_s["duration"]) - planned) < 0.2  # stille Szenen zerstören den Ton nicht
        durations = [s["duration"] for s in report["scenes"]]
        assert durations[1] == 2.5 and durations[3] == 1.5       # exakte Szenendauer
        assert [s["speech"] > 0 for s in report["scenes"]] == [True, False, True, False]
        assert report["quality"]["passed"]
    finally:
        clear_env()
        shutil.rmtree(tmp, ignore_errors=True)


# ----------------------------------------------------- Quellen (5, 6, 8, 9)

def test_pdf_source_is_used_survives_retry_and_duplicate():
    tmp = tempfile.mkdtemp(prefix="hard_")
    try:
        client, app_module = make_client(tmp)
        pid = client.post("/api/studio/projects", json={
            "workflow": "pdf", "options": {"cta": "Mehr im Handbuch."}}).json()["project"]["id"]
        pdf = make_pdf([f"The zebrafish handbook explains tank care in detail, part {i}."
                        for i in range(1, 10)])
        client.post(f"/api/studio/projects/{pid}/source", files={"file": ("h.pdf", io.BytesIO(pdf))})
        t1 = wait_task(client, client.post(f"/api/studio/projects/{pid}/ingest").json()["task"]["id"])
        assert t1["status"] == "succeeded", t1
        p = client.get(f"/api/studio/projects/{pid}").json()["project"]
        assert "zebrafish" in " ".join(s["text"] for s in p["scenes"]).lower()  # PDF-Text im Skript
        assert p["scenes"][-1]["text"] == "Mehr im Handbuch."
        assert p["id"] == pid                                                  # stabile ID
        # erneuter Ingest (Retry/Resume): Quelle noch da, idempotent, Optionen erhalten
        t2 = wait_task(client, client.post(f"/api/studio/projects/{pid}/ingest").json()["task"]["id"])
        assert t2["status"] == "succeeded" and t2["id"] != t1["id"]
        again = client.get(f"/api/studio/projects/{pid}").json()["project"]
        assert [s["text"] for s in again["scenes"]] == [s["text"] for s in p["scenes"]]
        assert again["options"] == p["options"] and again["source"]["file"] == "source.pdf"
        # Duplicate besitzt eine eigene, gültige Kopie der Quelle
        dup = client.post(f"/api/studio/projects/{pid}/duplicate", json={}).json()["project"]
        svc = app_module.studio.service
        src_a = os.path.join(svc.store.dir(pid), "source", "source.pdf")
        src_b = os.path.join(svc.store.dir(dup["id"]), "source", "source.pdf")
        assert os.path.isfile(src_b) and not os.path.samefile(src_a, src_b)
        client.delete(f"/api/studio/projects/{pid}")                           # Original weg …
        t3 = wait_task(client, client.post(f"/api/studio/projects/{dup['id']}/ingest").json()["task"]["id"])
        assert t3["status"] == "succeeded", t3                                 # … Kopie läuft weiter
    finally:
        clear_env()
        shutil.rmtree(tmp, ignore_errors=True)


def test_media_is_validated_by_content_duration_and_size():
    tmp = tempfile.mkdtemp(prefix="hard_")
    try:
        client, _ = make_client(tmp, CLIPFORGE_STUDIO_MAX_SOURCE_MINUTES=1,
                                CLIPFORGE_MAX_UPLOAD_MB=1)
        pid = client.post("/api/studio/projects", json={"workflow": "audio"}).json()["project"]["id"]
        up = lambda name, data: client.post(  # noqa: E731
            f"/api/studio/projects/{pid}/source", files={"file": (name, io.BytesIO(data))})
        r = up("fake.mp3", b"ID3" + b"\x00" * 2000)        # richtige Endung, kein Audio
        assert r.status_code == 415 and r.json()["detail"]["code"] == "file_unreadable"
        long_wav = open(make_tone_wav(os.path.join(tmp, "l.wav"), 20.0), "rb").read()
        os.environ["CLIPFORGE_STUDIO_MAX_SOURCE_MINUTES"] = "0"   # min. 1 Minute bleibt erlaubt
        assert up("ok.wav", long_wav).status_code == 200
        big = up("big.wav", b"RIFF" + b"\x00" * (2 * 1024 * 1024))
        assert big.status_code == 413 and big.json()["detail"]["code"] == "file_too_large"
        from clipforge.studio import service as service_mod
        orig = service_mod.probe

        class Info:
            duration, width, height, has_audio = 7200.0, 0, 0, True
        service_mod.probe = lambda path: Info()
        try:
            r = up("endlos.wav", long_wav)
            assert r.status_code == 413 and r.json()["detail"]["code"] == "file_too_long"
        finally:
            service_mod.probe = orig
    finally:
        clear_env("CLIPFORGE_STUDIO_MAX_SOURCE_MINUTES", "CLIPFORGE_MAX_UPLOAD_MB")
        shutil.rmtree(tmp, ignore_errors=True)


# ------------------------------------------------------------- Budget (10, 11)

def test_parallel_reservations_never_exceed_the_budget():
    tmp = tempfile.mkdtemp(prefix="hard_")
    try:
        ledger = CostLedger(tmp, 1.0)
        granted, denied = [], []
        barrier = threading.Barrier(40)

        def worker():
            mine = CostLedger(tmp, 1.0)      # eigener Ledger je Thread, gleiche Datei
            barrier.wait()
            try:
                granted.append(mine.reserve(0.3, "test"))
            except BudgetExceeded as exc:
                denied.append(exc.details)
        threads = [threading.Thread(target=worker) for _ in range(40)]
        [t.start() for t in threads]
        [t.join() for t in threads]
        assert len(granted) == 3 and len(denied) == 37      # 3 × 0,30 ≤ 1,00 < 4 × 0,30
        assert abs(ledger.summary()["reserved_usd"] - 0.9) < 1e-6 and ledger.spent == 0
        assert all(d["needed_usd"] == 0.3 and d["remaining_usd"] < 0.3 for d in denied)
        ledger.commit(granted[0], 0.25, "p", "ok")          # tatsächliche Kosten < Reservierung
        ledger.release(granted[1])                          # Fehler → frei
        ledger.release(granted[1])                          # doppelt freigeben ist harmlos
        s = ledger.summary()
        assert abs(s["spent_usd"] - 0.25) < 1e-6 and abs(s["reserved_usd"] - 0.3) < 1e-6
        assert abs(s["remaining_usd"] - 0.45) < 1e-6
        ledger.commit(granted[2], 0.3, "p", "ok")
        assert ledger.reserve(0.45, "passt genau") is not None
        assert _code(lambda: ledger.reserve(0.01, "zu viel")) == "budget_exceeded"
        assert CostLedger(tmp, 0.0).reserve(0.0, "kostenlos") is None   # Mock/lokal bleibt frei
        assert _code(lambda: CostLedger(tmp, 0.0).reserve(0.001, "bezahlt")) == "budget_exceeded"
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def test_project_budget_covers_voice_and_images_together_and_retry_resumes():
    tmp = tempfile.mkdtemp(prefix="hard_")
    calls = {"tts": 0, "image": 0}
    original = remote.HTTP_POST
    try:
        svc, _ = make_service(tmp, OPENAI_API_KEY="test-key-not-real")
        blob = _mp3(tmp)
        png = open(make_png(os.path.join(tmp, "i.png"), "64x64"), "rb").read()
        import base64
        import json

        def fake(url, headers, payload, timeout=120.0):
            if "images" in url:
                calls["image"] += 1
                return json.dumps({"data": [{"b64_json": base64.b64encode(png).decode()}]}).encode()
            calls["tts"] += 1
            return blob
        remote.HTTP_POST = fake
        os.environ["CLIPFORGE_PROVIDER_PRICES"] = json.dumps(
            {"openai_tts_per_1k_chars": 1.0, "openai_image_per_image": 0.10})
        # mehrere Szenen mit unterschiedlichem Text (gleicher Text käme aus dem Cache)
        text = " ".join(f"Punkt {i} bbbb cccc dddd eeee." for i in range(12))
        p = svc.create_project({"workflow": "script", "script": text, "resolution": "720p",
                                "voice": {"provider": "openai_tts"},
                                "options": {"media_type": "ai_image"}})
        svc.tasks.submit("ingest", p["id"], {}, run_inline=True)
        p = svc.store.load(p["id"])
        n = len(p["scenes"])
        assert n >= 3 and {s["visual"]["mode"] for s in p["scenes"]} == {"ai_image"}
        est = svc.estimate(p["id"])
        voice_total = sum(len(s["text"]) for s in p["scenes"]) / 1000.0
        assert abs(est["total_usd"] - (voice_total + 0.10 * n)) < 1e-3
        # Budget reicht für alle Stimmen, aber nur für EIN Bild
        budget = round(voice_total + 0.10 + 0.01, 4)
        p = svc.update_project(p["id"], {"budget_limit_usd": budget}, p["version"])
        assert _code(lambda: svc.start_render(p["id"], "preview")) == "budget_exceeded"  # Vorab
        t = svc.tasks.submit("render", p["id"], {"mode": "preview"}, run_inline=True)
        assert t["status"] == "failed" and t["error"]["code"] == "budget_exceeded"
        d = t["error"]["details"]
        assert d["needed_usd"] == 0.10 and d["remaining_usd"] < 0.10    # benötigt vs. übrig
        assert calls == {"tts": n, "image": 1}                           # danach KEIN Call mehr
        ledger = CostLedger(svc.store.dir(p["id"]), budget)
        assert ledger.spent <= budget + 1e-9 and ledger.summary()["reserved_usd"] == 0
        # Retry ohne mehr Budget: fertige Assets aus dem Cache, wieder Stopp, keine Mehrkosten
        spent = ledger.spent
        t2 = svc.tasks.retry(t["id"])
        svc.tasks._pool.shutdown(wait=True)
        assert svc.tasks.get(t["id"])["status"] == "failed"
        assert calls == {"tts": n, "image": 1} and CostLedger(svc.store.dir(p["id"]), budget).spent == spent
        # Budget erhöhen → Retry läuft durch, bezahlt nur die fehlenden Bilder
        from concurrent.futures import ThreadPoolExecutor
        svc.tasks._pool = ThreadPoolExecutor(max_workers=1)
        p = svc.update_project(p["id"], {"budget_limit_usd": 50}, p["version"])
        svc.tasks.retry(t["id"])
        svc.tasks._pool.shutdown(wait=True)
        done = svc.tasks.get(t["id"])
        assert done["status"] == "succeeded", done
        assert calls == {"tts": n, "image": n}
        assert abs(CostLedger(svc.store.dir(p["id"]), 50).spent - est["total_usd"]) < 1e-3
        assert t2["id"] == t["id"]
    finally:
        remote.HTTP_POST = original
        clear_env("OPENAI_API_KEY", "CLIPFORGE_PROVIDER_PRICES")
        shutil.rmtree(tmp, ignore_errors=True)


def test_provider_failure_releases_reservation_and_fallback_is_free():
    tmp = tempfile.mkdtemp(prefix="hard_")
    original = remote.HTTP_POST
    try:
        svc, _ = make_service(tmp, OPENAI_API_KEY="test-key-not-real")

        def down(*a, **k):
            raise TimeoutError()
        remote.HTTP_POST = down
        p = svc.create_project({"workflow": "script", "script": SCRIPT, "budget_limit_usd": 1,
                                "voice": {"provider": "openai_tts"}})
        svc.tasks.submit("ingest", p["id"], {}, run_inline=True)
        t = svc.tasks.submit("render", p["id"], {"mode": "preview"}, run_inline=True)
        assert t["status"] == "succeeded", t
        s = CostLedger(svc.store.dir(p["id"]), 1).summary()
        assert s["spent_usd"] == 0 and s["reserved_usd"] == 0 and s["remaining_usd"] == 1
    finally:
        remote.HTTP_POST = original
        clear_env("OPENAI_API_KEY")
        shutil.rmtree(tmp, ignore_errors=True)


# ---------------------------------------------------------- Credentials (12)

def test_credentials_take_effect_without_restart_and_never_leak():
    tmp = tempfile.mkdtemp(prefix="hard_")
    env = os.path.join(tmp, ".env")
    key = "sk-sentinel$pecial'\"chars #x=y"
    try:
        with open(env, "w") as fh:
            fh.write("# Kommentar bleibt\nOPENAI_API_KEY_BACKUP=keep-me\nexport OTHER='a b'\n"
                     "ELEVENLABS_API_KEY=old-value-123\n")
        os.chmod(env, 0o644)
        os.environ.pop("ELEVENLABS_API_KEY", None)
        os.environ.pop("OPENAI_API_KEY", None)
        client, _ = make_client(tmp, CLIPFORGE_ENV_FILE=env)
        state = lambda: {p["id"]: p["status"] for p in client.get("/api/studio/providers").json()["providers"]}  # noqa: E731
        assert state()["openai_tts"] == "not_configured"
        r = client.put("/api/studio/credentials/openai", json={"api_key": key})
        assert r.status_code == 200 and r.json() == {
            "provider": "openai", "label": "OpenAI (TTS, Bilder)", "env": "OPENAI_API_KEY",
            "configured": True}
        assert key not in r.text
        # sofort wirksam im laufenden Prozess — Status UND echter Provider-Aufruf
        assert state()["openai_tts"] == "ready" and state()["openai_image"] == "ready"
        seen = []
        original = remote.HTTP_POST
        remote.HTTP_POST = lambda url, headers, payload, timeout=120.0: seen.append(headers) or _mp3(tmp)
        try:
            r = client.post("/api/studio/voices/preview",
                            json={"provider": "openai_tts", "confirm_cost": True})
            assert r.status_code == 200
            assert seen[0]["Authorization"] == "Bearer " + key
        finally:
            remote.HTTP_POST = original
        # Datei: atomar, 0600, exakter Name, andere Einträge unversehrt, bash-lesbar
        content = open(env).read()
        assert stat.S_IMODE(os.stat(env).st_mode) == 0o600
        assert "# Kommentar bleibt" in content and "OPENAI_API_KEY_BACKUP=keep-me" in content
        assert "export OTHER='a b'" in content and "ELEVENLABS_API_KEY=old-value-123" in content
        assert not [f for f in os.listdir(tmp) if f.startswith(".env.")]
        out = subprocess.run(["bash", "-c", f'source "{env}"; printf %s "$OPENAI_API_KEY"'],
                             capture_output=True, text=True).stdout
        assert out == key
        # überschreiben erzeugt keinen zweiten Eintrag
        client.put("/api/studio/credentials/openai", json={"api_key": "zweiter-wert-123"})
        assert open(env).read().count("OPENAI_API_KEY=") == 1
        assert os.environ["OPENAI_API_KEY"] == "zweiter-wert-123"
        # nirgends der Wert
        for path in ("/api/studio/credentials", "/api/studio/providers", "/api/studio/overview"):
            body = client.get(path).text
            assert key not in body and "zweiter-wert-123" not in body
        creds = {c["provider"]: c["configured"] for c in client.get("/api/studio/credentials").json()["credentials"]}
        # ELEVENLABS_API_KEY stand schon in der .env → das Backend lädt sie beim Start
        assert creds == {"elevenlabs": True, "openai": True, "anthropic": False}
        # löschen: sofort „nicht konfiguriert“, Backup-Variable bleibt
        r = client.delete("/api/studio/credentials/openai")
        assert r.status_code == 200 and r.json()["configured"] is False
        assert state()["openai_tts"] == "not_configured" and "OPENAI_API_KEY" not in os.environ
        assert "OPENAI_API_KEY_BACKUP=keep-me" in open(env).read()
        r = client.post("/api/studio/voices/preview", json={"provider": "openai_tts", "confirm_cost": True})
        assert r.status_code == 409 and r.json()["detail"]["code"] == "provider_not_configured"
        # Fehlerfälle
        r = client.delete("/api/studio/credentials/openai")
        assert r.status_code == 404 and r.json()["detail"]["code"] == "credential_not_set"
        for name, kw in (("put", {"json": {"api_key": "irgendein-wert"}}), ("delete", {})):
            r = getattr(client, name)("/api/studio/credentials/unbekannt", **kw)
            assert r.status_code == 404 and r.json()["detail"]["code"] == "provider_unknown"
        assert client.put("/api/studio/credentials/openai", json={"api_key": "kurz"}).status_code == 422
        r = client.put("/api/studio/credentials/openai", json={"api_key": "zeile1\nINJECT=1 zzz"})
        assert r.status_code == 400 and "INJECT" not in open(env).read()
        # Anthropic-Key wirkt ebenfalls ohne Neustart (Settings lesen live)
        from clipforge.config import get_settings
        assert not get_settings().llm_available
        client.put("/api/studio/credentials/anthropic", json={"api_key": "sk-sentinel-anthropic"})
        assert get_settings().llm_available
        client.delete("/api/studio/credentials/anthropic")
        assert not get_settings().llm_available
    finally:
        clear_env("CLIPFORGE_ENV_FILE", "OPENAI_API_KEY", "ANTHROPIC_API_KEY", "ELEVENLABS_API_KEY")
        shutil.rmtree(tmp, ignore_errors=True)


def test_credential_test_is_explicit_and_reports_honestly():
    tmp = tempfile.mkdtemp(prefix="hard_")
    original = credentials.HTTP_GET
    calls = []
    try:
        client, _ = make_client(tmp, CLIPFORGE_ENV_FILE=os.path.join(tmp, ".env"))
        os.environ.pop("ELEVENLABS_API_KEY", None)
        r = client.post("/api/studio/credentials/elevenlabs/test")
        assert r.status_code == 409 and r.json()["detail"]["code"] == "credential_not_set"
        credentials.HTTP_GET = lambda url, headers, timeout=15.0: calls.append((url, headers)) or 401
        client.put("/api/studio/credentials/elevenlabs", json={"api_key": "sentinel-eleven-key"})
        assert calls == []                      # Setzen allein löst KEINEN Netz-Call aus
        r = client.post("/api/studio/credentials/elevenlabs/test").json()
        assert r["ok"] is False and r["reason"] == "rejected" and "sentinel" not in str(r)
        assert calls[0][1] == {"xi-api-key": "sentinel-eleven-key"}
        credentials.HTTP_GET = lambda url, headers, timeout=15.0: 200
        assert client.post("/api/studio/credentials/elevenlabs/test").json()["ok"] is True

        def boom(url, headers, timeout=15.0):
            raise ConnectionError(str(headers))
        credentials.HTTP_GET = boom
        r = client.post("/api/studio/credentials/elevenlabs/test").json()
        assert r["reason"] == "unreachable" and "sentinel" not in str(r)
    finally:
        credentials.HTTP_GET = original
        clear_env("CLIPFORGE_ENV_FILE", "ELEVENLABS_API_KEY")
        shutil.rmtree(tmp, ignore_errors=True)


# ------------------------------------------------- Local API Security (13–15)

def test_mutations_require_token_and_foreign_origins_are_rejected():
    tmp = tempfile.mkdtemp(prefix="hard_")
    try:
        os.environ["CLIPFORGE_API_AUTH"] = "on"
        token_file = os.path.join(tmp, "token")
        client, app_module = make_client(tmp, CLIPFORGE_API_AUTH="on",
                                         CLIPFORGE_API_TOKEN_FILE=token_file)
        token = open(token_file).read()
        assert len(token) >= 32 and stat.S_IMODE(os.stat(token_file).st_mode) == 0o600
        body = {"workflow": "script", "script": SCRIPT}
        good = {"X-ClipForge-Token": token}
        local = {"Origin": "http://127.0.0.1:3000"}
        evil = {"Origin": "https://evil.example"}
        # 13) ohne/mit falschem Token: Studio, Credentials, Löschen, Upload, Publishing, Brand Kit
        for method, path, kw in (
            ("post", "/api/studio/projects", {"json": body}),
            ("put", "/api/studio/credentials/openai", {"json": {"api_key": "sentinel-value-1"}}),
            ("delete", "/api/studio/projects/ffffffffffff", {}),
            ("post", "/api/jobs", {"files": {"file": ("a.mp4", io.BytesIO(b"x"))}}),
            ("delete", "/api/jobs/ffffffffffff", {}),
            ("post", "/api/jobs/bulk-delete", {"json": {"job_ids": []}}),
            ("post", "/api/jobs/x/publishing/y/youtube/publish", {"json": {"confirm": True}}),
            ("post", "/api/youtube/oauth/start", {}),
            ("post", "/api/brand-kit", {"json": {}}),
            ("post", "/api/studio/automations", {"json": {}}),
        ):
            r = getattr(client, method)(path, **kw)
            assert r.status_code == 401 and r.json()["detail"]["code"] == "token_missing", path
            r = getattr(client, method)(path, headers={"X-ClipForge-Token": "falsch" * 8}, **kw)
            assert r.status_code == 403 and r.json()["detail"]["code"] == "token_invalid", path
        assert client.get("/api/studio/projects").json()["projects"] == []   # nichts passiert
        assert "OPENAI_API_KEY" not in os.environ
        # Lesen bleibt ohne Token möglich
        assert client.get("/health").status_code == 200
        assert client.get("/api/studio/overview").status_code == 200
        # 14) erlaubter lokaler Origin + Token funktioniert, inkl. Preflight
        pre = client.options("/api/studio/projects", headers={
            **local, "Access-Control-Request-Method": "POST",
            "Access-Control-Request-Headers": "content-type,x-clipforge-token"})
        assert pre.status_code == 200
        assert pre.headers["access-control-allow-origin"] == "http://127.0.0.1:3000"
        assert "x-clipforge-token" in pre.headers["access-control-allow-headers"].lower()
        r = client.post("/api/studio/projects", json=body, headers={**good, **local})
        assert r.status_code == 201
        assert r.headers["access-control-allow-origin"] == "http://127.0.0.1:3000"
        wait_task(client, r.json()["task_id"])
        r = client.post("/api/studio/projects", json=body,
                        headers={**good, "Origin": "http://localhost:3000"})
        assert r.status_code == 201
        wait_task(client, r.json()["task_id"])
        assert client.post("/api/studio/projects", json=body, headers=good).status_code == 201  # CLI
        # 15) fremder Origin: kein CORS-Header, keine Mutation — selbst MIT gültigem Token
        r = client.post("/api/studio/projects", json=body, headers={**good, **evil})
        assert r.status_code == 403 and r.json()["detail"]["code"] == "origin_not_allowed"
        assert "access-control-allow-origin" not in r.headers
        pre = client.options("/api/studio/projects", headers={
            **evil, "Access-Control-Request-Method": "POST"})
        assert pre.status_code == 400 and "access-control-allow-origin" not in pre.headers
        r = client.get("/api/studio/projects", headers=evil)
        assert "access-control-allow-origin" not in r.headers          # Browser gibt nichts heraus
        assert len(r.json()["projects"]) == 3
        # Token-Ausgabe: nur lokal, nie an fremde Origins, nie bei fremdem Host (DNS-Rebinding)
        assert client.get("/api/session", headers=local).json()["token"] == token
        assert client.get("/api/session").json()["auth_required"] is True
        assert client.get("/api/session", headers=evil).status_code == 403
        r = client.get("/api/session", headers={"Host": "evil.example"})
        assert r.status_code == 403 and token not in r.text
        # Token steht in keiner Projektdatei und keiner API-Antwort
        for root, _, files in os.walk(tmp):
            for name in files:
                full = os.path.join(root, name)
                if full != token_file and os.path.getsize(full) < 2_000_000:
                    assert token.encode() not in open(full, "rb").read(), full
        assert token not in client.get("/api/studio/overview").text
        # Neustart lädt dasselbe Token (Frontend bleibt angemeldet)
        client2, _ = make_client(tmp, CLIPFORGE_API_AUTH="on", CLIPFORGE_API_TOKEN_FILE=token_file)
        assert client2.get("/api/session").json()["token"] == token
    finally:
        os.environ["CLIPFORGE_API_AUTH"] = "off"
        clear_env("CLIPFORGE_API_TOKEN_FILE")
        shutil.rmtree(tmp, ignore_errors=True)


def test_cors_origin_configuration_never_allows_wildcards():
    import local_security
    try:
        os.environ["CLIPFORGE_ALLOWED_ORIGINS"] = "*, http://192.168.1.5:3000/ ,ftp://x, https://*.evil.com, "
        assert local_security.allowed_origins() == [
            "http://127.0.0.1:3000", "http://localhost:3000", "http://192.168.1.5:3000"]
        tmp = tempfile.mkdtemp(prefix="hard_")
        client, _ = make_client(tmp)
        r = client.get("/health", headers={"Origin": "http://192.168.1.5:3000"})
        assert r.headers["access-control-allow-origin"] == "http://192.168.1.5:3000"
        r = client.get("/health", headers={"Origin": "https://a.evil.com"})
        assert "access-control-allow-origin" not in r.headers
        # Auth aus (Entwicklung): Origin-Prüfung bleibt trotzdem aktiv
        r = client.post("/api/studio/projects", json={"workflow": "script", "script": SCRIPT},
                        headers={"Origin": "https://a.evil.com"})
        assert r.status_code == 403
        shutil.rmtree(tmp, ignore_errors=True)
    finally:
        clear_env("CLIPFORGE_ALLOWED_ORIGINS")


# ------------------------------------------------- Cancel / Restart (16, 17)

def test_cancel_stays_canceled_and_project_leaves_processing():
    tmp = tempfile.mkdtemp(prefix="hard_")
    try:
        svc, _ = make_service(tmp)
        p = svc.create_project({"workflow": "script", "script": SCRIPT})
        started, release = threading.Event(), threading.Event()
        real = svc._ingest

        def slow(pid, progress, should_cancel):
            started.set()
            release.wait(10)
            return real(pid, progress, should_cancel)
        svc._ingest = slow
        task = svc.start_ingest(p["id"])
        assert started.wait(10) and svc.store.load(p["id"])["status"] == "ingesting"
        svc.tasks.cancel(task["id"])
        release.set()
        svc.tasks._pool.shutdown(wait=True)
        done = svc.tasks.get(task["id"])
        assert done["status"] == "canceled"                     # Hintergrund-Thread überschreibt nicht
        proj = svc.store.load(p["id"])
        assert proj["status"] == "draft" and proj["status_error"]["code"] == "canceled"
        assert proj["scenes"] == []                             # nach Cancel nichts mehr geschrieben
        assert _code(lambda: svc.tasks.cancel(task["id"])) == "task_not_cancelable"
        assert svc.tasks.get(task["id"])["status"] == "canceled"
        # wartende Aufgabe abbrechen: läuft nie an
        from concurrent.futures import ThreadPoolExecutor
        svc.tasks._pool = ThreadPoolExecutor(max_workers=1)
        gate = threading.Event()
        svc.tasks._pool.submit(gate.wait, 10)                   # Worker belegt
        svc._ingest = real
        queued = svc.start_ingest(p["id"])
        svc.tasks.cancel(queued["id"])
        gate.set()
        svc.tasks._pool.shutdown(wait=True)
        assert svc.tasks.get(queued["id"])["status"] == "canceled"
        assert svc.tasks.get(queued["id"])["attempts"] == 0
        assert svc.store.load(p["id"])["status"] == "draft"
        # danach ganz normal neu startbar
        svc.tasks._pool = ThreadPoolExecutor(max_workers=1)
        t = svc.tasks.submit("ingest", p["id"], {}, run_inline=True)
        assert t["status"] == "succeeded" and svc.store.load(p["id"])["status"] == "ready"
    finally:
        clear_env()
        shutil.rmtree(tmp, ignore_errors=True)


def test_restart_marks_orphaned_processing_projects_as_interrupted():
    tmp = tempfile.mkdtemp(prefix="hard_")
    try:
        svc, registry = make_service(tmp)
        p = svc.create_project({"workflow": "script", "script": SCRIPT})
        svc.store.mutate(p["id"], lambda x: x.update(status="ingesting"))
        svc.tasks._save({"id": "abababababab", "kind": "ingest", "project_id": p["id"],
                         "params": {}, "status": "running", "progress": ["x"] * 500,
                         "result": None, "error": None, "attempts": 1, "idempotency_key": None,
                         "created_at": "x", "started_at": "x", "finished_at": None})
        from clipforge.studio.service import StudioService
        from clipforge.studio.tasks import TaskManager
        tasks2 = TaskManager(max_workers=1)
        svc2 = StudioService(registry=registry, tasks=tasks2)   # „neuer Prozess“
        info = tasks2.recover()
        assert info["interrupted"] == ["abababababab"]
        proj = svc2.store.load(p["id"])
        assert proj["status"] == "failed" and proj["status_error"]["code"] == "interrupted"
        assert proj["id"] == p["id"] and proj["source"]["text"] == SCRIPT   # nichts verloren
        tasks2.retry("abababababab")
        tasks2._pool.shutdown(wait=True)
        t = tasks2.get("abababababab")
        assert t["status"] == "succeeded" and len(t["progress"]) <= 200   # Liste bleibt begrenzt
        assert svc2.store.load(p["id"])["status"] == "ready"
    finally:
        clear_env()
        shutil.rmtree(tmp, ignore_errors=True)


def test_old_project_without_options_gets_defaults_and_keeps_duration():
    tmp = tempfile.mkdtemp(prefix="hard_")
    try:
        svc, _ = make_service(tmp)
        import json
        pid = "0a0a0a0a0a0a"
        os.makedirs(os.path.join(svc.store.base, pid))
        with open(os.path.join(svc.store.base, pid, "project.json"), "w") as fh:
            json.dump({"title": "Alt", "workflow": "script", "version": 4,
                       "source": {"type": "script", "text": SCRIPT, "target_seconds": 75},
                       "scenes": [{"text": "Hallo Welt"}]}, fh)
        p = svc.store.load(pid)
        assert p["options"] == {**ProductionOptions().to_dict(), "duration_target": 75}
        garbage = ProductionOptions.from_dict({"platform": 7, "forbidden_topics": "a, b\nc",
                                               "duration_target": "x", "media_type": None})
        assert garbage.platform == "generic" and garbage.forbidden_topics == ["a", "b", "c"]
        t = svc.tasks.submit("render", pid, {"mode": "preview"}, run_inline=True)
        assert t["status"] == "succeeded", t
    finally:
        clear_env()
        shutil.rmtree(tmp, ignore_errors=True)


# ------------------------------------------------- 4K, Provider-Antworten (19)

def test_real_4k_render_and_controlled_upscaling_is_reported():
    tmp = tempfile.mkdtemp(prefix="hard_")
    try:
        svc, _ = make_service(tmp)
        p = svc.create_project({"workflow": "script", "script": "Ein kurzer Satz in 4K.",
                                "resolution": "4k", "voice": {"provider": "mock"}})
        svc.tasks.submit("ingest", p["id"], {}, run_inline=True)
        p = svc.store.load(p["id"])
        make_png(os.path.join(svc.store.dir(p["id"]), "media", "klein.png"), "320x480")
        scenes = [{**p["scenes"][0], "visual": {"mode": "media", "media": "klein.png"}},
                  {"text": "", "duration": 1.0, "visual": {"mode": "static", "color": "#102030"}}]
        p = svc.update_project(p["id"], {"scenes": scenes}, p["version"])
        t = svc.tasks.submit("render", p["id"], {"mode": "final"}, run_inline=True)
        assert t["status"] == "succeeded", t
        report = svc.list_renders(p["id"])[0]
        info = ffprobe(svc.render_file(p["id"], report["render_id"]))
        video = next(s for s in info["streams"] if s["codec_type"] == "video")
        assert (video["width"], video["height"]) == (2160, 3840)
        assert any(s["codec_type"] == "audio" for s in info["streams"])
        ups = [w for w in report["warnings"] if "hochskaliert" in w]
        assert len(ups) == 1 and "klein.png" in ups[0] and "320×480" in ups[0]
        assert any(c["level"] == "warn" and "hochskaliert" in c["message"]
                   for c in report["quality"]["checks"])
        assert report["quality"]["passed"]                 # Hinweis, kein Abbruch
        # Vorschau ist bewusst klein → kein Upscaling-Hinweis
        prev = svc.tasks.submit("render", p["id"], {"mode": "preview"}, run_inline=True)
        prev_report = svc.get_render(p["id"], prev["result"]["render_id"])
        assert prev_report["mode"] == "preview"
        assert not [w for w in prev_report["warnings"] if "hochskaliert" in w]
    finally:
        clear_env()
        shutil.rmtree(tmp, ignore_errors=True)


def test_provider_response_size_limit_and_content_check():
    import http.server

    class Handler(http.server.BaseHTTPRequestHandler):
        def do_POST(self):  # noqa: N802
            self.rfile.read(int(self.headers.get("Content-Length") or 0))
            self.send_response(200)
            self.send_header("Content-Type", "audio/mpeg")
            if self.path == "/declared":
                self.send_header("Content-Length", str(3 * 1024 * 1024))
            self.end_headers()
            try:
                for _ in range(48):            # 3 MB, gestreamt
                    self.wfile.write(b"\xff\xfb" + b"\x00" * 65534)
            except OSError:
                pass

        def log_message(self, *a):
            pass
    srv = http.server.HTTPServer(("127.0.0.1", 0), Handler)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    base = f"http://127.0.0.1:{srv.server_address[1]}"
    try:
        os.environ["CLIPFORGE_PROVIDER_MAX_RESPONSE_MB"] = "1"
        for path in ("/declared", "/streamed"):
            try:
                remote._http_post(base + path, {}, {"x": 1}, timeout=10)
                raise AssertionError("Größenlimit erwartet")
            except remote.ResponseTooLarge:
                pass
        os.environ["CLIPFORGE_PROVIDER_MAX_RESPONSE_MB"] = "5"
        body = remote._http_post(base + "/streamed", {}, {"x": 1}, timeout=10)
        assert len(body) == 3 * 1024 * 1024                    # nichts abgeschnitten
        assert remote.looks_like_audio(body)
        for bad in (b"<html>Fehlerseite</html>" * 10, b"{\"error\": \"quota\"}" + b" " * 100):
            assert not remote.looks_like_audio(bad)
    finally:
        srv.shutdown()
        srv.server_close()
        clear_env("CLIPFORGE_PROVIDER_MAX_RESPONSE_MB")


def test_oversized_or_non_audio_provider_answer_costs_nothing():
    tmp = tempfile.mkdtemp(prefix="hard_")
    original = remote.HTTP_POST
    try:
        svc, _ = make_service(tmp, OPENAI_API_KEY="test-key-not-real")
        answers = iter([remote.ResponseTooLarge(), b"<html>Fehlerseite</html>" * 20])

        def fake(*a, **k):
            nxt = next(answers, b"<html>x</html>" * 20)
            if isinstance(nxt, Exception):
                raise nxt
            return nxt
        remote.HTTP_POST = fake
        p = svc.create_project({"workflow": "script", "script": SCRIPT, "budget_limit_usd": 1,
                                "voice": {"provider": "openai_tts"}})
        svc.tasks.submit("ingest", p["id"], {}, run_inline=True)
        t = svc.tasks.submit("render", p["id"], {"mode": "preview"}, run_inline=True)
        assert t["status"] == "succeeded", t
        report = svc.list_renders(p["id"])[0]
        reasons = [f["reason"] for f in report["fallbacks"]]
        assert any("Größenlimit" in r for r in reasons) and any("kein Audio" in r for r in reasons)
        s = CostLedger(svc.store.dir(p["id"]), 1).summary()
        assert s["spent_usd"] == 0 and s["reserved_usd"] == 0
        cache = os.path.join(svc.store.dir(p["id"]), "cache", "voice")
        assert os.listdir(cache) == []                         # nichts Kaputtes im Cache
    finally:
        remote.HTTP_POST = original
        clear_env("OPENAI_API_KEY")
        shutil.rmtree(tmp, ignore_errors=True)


def test_shorts_renderer_and_silence_detection_have_timeouts():
    import inspect
    from clipforge import ffmpeg_utils
    from clipforge import render as shorts_render
    assert "timeout=_render_timeout()" in inspect.getsource(shorts_render._run_ffmpeg)
    assert "timeout=" in inspect.getsource(ffmpeg_utils.detect_silences)
    assert "timeout=" in inspect.getsource(ffmpeg_utils.probe)
    os.environ["CLIPFORGE_RENDER_TIMEOUT"] = "5"
    try:
        assert shorts_render._render_timeout() == 60           # Untergrenze
    finally:
        clear_env("CLIPFORGE_RENDER_TIMEOUT")


def test_newest_render_is_unambiguous_within_the_same_second():
    import json
    import time
    tmp = tempfile.mkdtemp(prefix="hard_")
    try:
        svc, _ = make_service(tmp)
        p = svc.create_project({"workflow": "script", "script": SCRIPT})
        rdir = os.path.join(svc.store.dir(p["id"]), "renders")
        for rid in ("aaaaaaaaaaaa", "bbbbbbbbbbbb", "cccccccccccc"):
            open(os.path.join(rdir, f"{rid}.mp4"), "wb").close()
            with open(os.path.join(rdir, f"{rid}.json"), "w") as fh:
                json.dump({"render_id": rid, "file": f"{rid}.mp4", "mode": "final",
                           "rendered_at": "2026-01-01T10:00:00+00:00"}, fh)
            time.sleep(0.01)
        assert [r["render_id"] for r in svc.list_renders(p["id"])] == [
            "cccccccccccc", "bbbbbbbbbbbb", "aaaaaaaaaaaa"]
    finally:
        clear_env()
        shutil.rmtree(tmp, ignore_errors=True)


if __name__ == "__main__":
    run_all(globals())
