"""KI-Video, Talking Avatar, Stimmklon — gegen nachgebildete Anbieter-Antworten.

Kein echter Netzaufruf: fal.ai-Warteschlange und Video-Download sowie die
ElevenLabs-API werden in jedem Test ersetzt.
"""

from __future__ import annotations

import io
import json
import os
import shutil
import socket
import tempfile

from studio_helpers import clear_env, ffprobe, make_client, make_png, make_service, make_tone_wav, make_video, run_all

from clipforge.studio.costs import CostLedger
from clipforge.studio.providers import fal, remote

SCRIPT = "Ein Satz für das KI-Video. Noch ein Satz mit Inhalt."


class FakeFal:
    """Nachbildung der fal-Warteschlange: submit → IN_QUEUE → IN_PROGRESS → COMPLETED."""

    def __init__(self, video_bytes: bytes, fail_with: str | None = None):
        self.video = video_bytes
        self.fail_with = fail_with
        self.submits: list[tuple[str, dict]] = []
        self.polls = 0
        self.auth: list[str] = []

    def http(self, method, url, headers, body=None, timeout=60.0):
        self.auth.append(headers.get("Authorization", ""))
        if method == "POST":
            self.submits.append((url, body))
            rid = f"req{len(self.submits)}"
            base = f"https://queue.fal.run/x/requests/{rid}"
            return 200, {"request_id": rid, "status_url": base + "/status",
                         "response_url": base, "cancel_url": base + "/cancel"}
        if url.endswith("/status"):
            self.polls += 1
            if self.fail_with:
                return 200, {"status": self.fail_with}
            return 200, {"status": ["IN_QUEUE", "IN_PROGRESS", "COMPLETED"][min(self.polls - 1, 2)]}
        if method == "PUT":
            return 200, {}
        return 200, {"video": {"url": "https://v3.fal.media/files/out.mp4"}}

    def download_kwargs(self):
        def resolver(host, port, type=None):
            return [(socket.AF_INET, socket.SOCK_STREAM, 6, "", ("151.101.1.1", port))]

        def transport(scheme, host, ip, port, path, headers, timeout, max_bytes, deadline):
            assert host == "v3.fal.media"
            return 200, {"content-type": "video/mp4"}, self.video
        return {"resolver": resolver, "transport": transport}


def _setup(tmp, fake, **env):
    fal.FAL_HTTP = fake.http
    fal.DOWNLOAD_KWARGS.clear()
    fal.DOWNLOAD_KWARGS.update(fake.download_kwargs())
    fal.SLEEP = lambda s: None  # nicht warten (nur im fal-Modul)
    return make_service(tmp, FAL_KEY="sentinel-fal-key", **env)


def _restore():
    fal.FAL_HTTP = fal._http
    fal.DOWNLOAD_KWARGS.clear()
    fal.SLEEP = fal.time.sleep
    clear_env("FAL_KEY", "ELEVENLABS_API_KEY", "CLIPFORGE_PROVIDER_PRICES")


def test_text_and_image_to_video_scene_with_budget_and_cache():
    tmp = tempfile.mkdtemp(prefix="ai_")
    try:
        clip = open(make_video(os.path.join(tmp, "clip.mp4"), 5.0, "640x360"), "rb").read()
        fake = FakeFal(clip)
        svc, _ = _setup(tmp, fake)
        p = svc.create_project({"workflow": "script", "script": SCRIPT, "resolution": "720p",
                                "voice": {"provider": "mock"}, "options": {"media_type": "ai_video"}})
        svc.tasks.submit("ingest", p["id"], {}, run_inline=True)
        p = svc.store.load(p["id"])
        assert {s["visual"]["mode"] for s in p["scenes"]} == {"ai_video"}
        make_png(os.path.join(svc.store.dir(p["id"]), "media", "produkt.png"))
        scenes = p["scenes"]
        scenes = scenes[:1] + [{"text": "Das Produkt in Bewegung.",
                                "visual": {"mode": "ai_video", "media": "produkt.png"}}]
        p = svc.update_project(p["id"], {"scenes": scenes}, p["version"])
        est = svc.estimate(p["id"])
        assert any("KI-Video" in i["what"] for i in est["items"]) and est["total_usd"] > 0
        # Budget 0 → nur kostenlose Provider: Start verweigert, kein Aufruf
        try:
            svc.start_render(p["id"], "preview")
            raise AssertionError("budget_exceeded erwartet")
        except Exception as exc:  # noqa: BLE001
            assert getattr(exc, "code", "") == "budget_exceeded"
        assert fake.submits == []
        p = svc.update_project(p["id"], {"budget_limit_usd": 5}, p["version"])
        t = svc.tasks.submit("render", p["id"], {"mode": "preview"}, run_inline=True)
        assert t["status"] == "succeeded", t
        report = svc.get_render(p["id"], t["result"]["render_id"])
        assert report["fallbacks"] == [] and report["has_audio"]
        t2v = [b for u, b in fake.submits if u.endswith("text-to-video")]
        i2v = [b for u, b in fake.submits if u.endswith("image-to-video")]
        assert len(t2v) == 1 and t2v[0]["aspect_ratio"] == "9:16" and t2v[0]["duration"] in ("5", "10")
        assert len(i2v) == 1 and i2v[0]["image_url"].startswith("data:image/png;base64,")
        assert all(a == "Key sentinel-fal-key" for a in fake.auth)
        spent = CostLedger(svc.store.dir(p["id"]), 5).spent
        assert abs(spent - 2 * 5 * 0.10) < 1e-6                     # 2 Clips × 5 s × 0,10 USD
        # erneuter Render: alles aus dem Cache, keine Mehrkosten
        svc.tasks.submit("render", p["id"], {"mode": "preview"}, run_inline=True)
        assert len(fake.submits) == 2 and CostLedger(svc.store.dir(p["id"]), 5).spent == spent
        assert "sentinel-fal-key" not in json.dumps(report)
    finally:
        _restore()
        shutil.rmtree(tmp, ignore_errors=True)


def test_ai_video_failure_falls_back_for_free():
    tmp = tempfile.mkdtemp(prefix="ai_")
    try:
        fake = FakeFal(b"", fail_with="FAILED")
        svc, _ = _setup(tmp, fake)
        p = svc.create_project({"workflow": "script", "script": SCRIPT, "budget_limit_usd": 5,
                                "voice": {"provider": "mock"}, "options": {"media_type": "ai_video"}})
        svc.tasks.submit("ingest", p["id"], {}, run_inline=True)
        t = svc.tasks.submit("render", p["id"], {"mode": "preview"}, run_inline=True)
        assert t["status"] == "succeeded", t
        report = svc.get_render(p["id"], t["result"]["render_id"])
        assert {f["kind"] for f in report["fallbacks"]} == {"video"}
        assert {s["visual_mode"] for s in report["scenes"]} == {"ai_video"}
        s = CostLedger(svc.store.dir(p["id"]), 5).summary()
        assert s["spent_usd"] == 0 and s["reserved_usd"] == 0       # Fehler kostet nichts
    finally:
        _restore()
        shutil.rmtree(tmp, ignore_errors=True)


def test_without_key_no_call_and_honest_status():
    tmp = tempfile.mkdtemp(prefix="ai_")
    try:
        fake = FakeFal(b"")
        svc, _ = _setup(tmp, fake)
        os.environ.pop("FAL_KEY")
        p = svc.create_project({"workflow": "script", "script": SCRIPT, "budget_limit_usd": 5,
                                "voice": {"provider": "mock"}, "options": {"media_type": "ai_video"}})
        svc.tasks.submit("ingest", p["id"], {}, run_inline=True)
        t = svc.tasks.submit("render", p["id"], {"mode": "preview"}, run_inline=True)
        assert t["status"] == "succeeded" and fake.submits == []
        from clipforge.studio.providers import readiness
        info = {r["id"]: r for r in readiness()}
        assert info["fal_video"]["status"] == "not_configured"
        assert info["fal_video"]["live_verified"] is False and info["espeak"]["live_verified"] is True
    finally:
        _restore()
        shutil.rmtree(tmp, ignore_errors=True)


def test_talking_avatar_uses_scene_voice_and_avatar_image():
    tmp = tempfile.mkdtemp(prefix="ai_")
    try:
        clip = open(make_video(os.path.join(tmp, "talk.mp4"), 2.0, "512x512"), "rb").read()
        fake = FakeFal(clip)
        svc, _ = _setup(tmp, fake)
        p = svc.create_project({"workflow": "script", "script": SCRIPT, "resolution": "720p",
                                "budget_limit_usd": 5, "voice": {"provider": "espeak"},
                                "options": {"media_type": "avatar"}})
        svc.tasks.submit("ingest", p["id"], {}, run_inline=True)
        p = svc.store.load(p["id"])
        make_png(os.path.join(svc.store.dir(p["id"]), "media", "ich.png"), "512x512")
        # ohne Avatar-Bild: ehrlicher Hinweis, kein Aufruf
        t = svc.tasks.submit("render", p["id"], {"mode": "preview"}, run_inline=True)
        rep = svc.get_render(p["id"], t["result"]["render_id"])
        assert fake.submits == [] and any("kein Avatar-Bild" in f["reason"] for f in rep["fallbacks"])
        p = svc.update_project(p["id"], {"visuals": {**p["visuals"], "avatar_image": "ich.png"}},
                               p["version"])
        t = svc.tasks.submit("render", p["id"], {"mode": "final"}, run_inline=True)
        assert t["status"] == "succeeded", t
        rep = svc.get_render(p["id"], t["result"]["render_id"])
        assert rep["fallbacks"] == [] and len(fake.submits) == len(p["scenes"])
        body = fake.submits[0][1]
        assert fake.submits[0][0].endswith("fal-ai/sadtalker")
        assert body["source_image_url"].startswith("data:image/png;base64,")
        assert body["driven_audio_url"].startswith("data:audio/")     # echte Stimme der Szene
        info = ffprobe(svc.render_file(p["id"], rep["render_id"]))
        video = next(s for s in info["streams"] if s["codec_type"] == "video")
        assert (video["width"], video["height"]) == (720, 1280)
        assert abs(float(info["format"]["duration"]) - rep["expected"]["duration"]) < 0.3
        try:
            svc.update_project(p["id"], {"visuals": {**p["visuals"], "avatar_image": "fehlt.png"}},
                               svc.store.load(p["id"])["version"])
            raise AssertionError("media_not_found erwartet")
        except Exception as exc:  # noqa: BLE001
            assert getattr(exc, "code", "") == "media_not_found"
    finally:
        _restore()
        shutil.rmtree(tmp, ignore_errors=True)


def test_voice_clone_requires_consent_and_is_recorded():
    tmp = tempfile.mkdtemp(prefix="ai_")
    calls = []
    original = remote.HTTP_RAW
    try:
        client, _ = make_client(tmp, ELEVENLABS_API_KEY="sentinel-eleven-key")

        def fake_raw(method, url, headers, body, timeout=120.0):
            calls.append((method, url, headers, body))
            if method == "POST":
                return 200, json.dumps({"voice_id": "abcDEF123", "requires_verification": False}).encode()
            return 200, b"{}"
        remote.HTTP_RAW = fake_raw
        wav = open(make_tone_wav(os.path.join(tmp, "probe.wav"), 3.0), "rb").read()
        post = lambda data, files=None: client.post(  # noqa: E731
            "/api/studio/voices/clones", data=data,
            files=files if files is not None else [("files", ("probe.wav", io.BytesIO(wav)))])
        r = post({"name": "Meine Stimme", "basis": "own"})
        assert r.status_code == 400 and r.json()["detail"]["code"] == "consent_required"
        r = post({"name": "Fremd", "basis": "permission", "no_deception": "true"})
        assert r.json()["detail"]["code"] == "consent_required"       # Name der Person fehlt
        r = post({"name": "X", "basis": "irgendwas", "no_deception": "true"})
        assert r.json()["detail"]["code"] == "consent_required"
        r = post({"name": "X", "basis": "own", "no_deception": "true"},
                 [("files", ("x.txt", io.BytesIO(b"hallo")))])
        assert r.status_code == 415
        assert calls == []                                             # ohne Einwilligung nichts gesendet
        r = post({"name": "Meine Stimme", "basis": "own", "no_deception": "true"})
        assert r.status_code == 201, r.text
        clone = r.json()["clone"]
        assert clone["voice_id"] == "abcDEF123"
        c = clone["consent"]
        assert c["basis"] == "own" and c["confirmed_at"] and len(c["sample_sha256"]) == 1
        method, url, headers, body = calls[0]
        assert url == "https://api.elevenlabs.io/v1/voices/add" and headers["xi-api-key"] == "sentinel-eleven-key"
        assert b'name="files"; filename="probe_0.wav"' in body and b"Meine Stimme" in body
        listed = client.get("/api/studio/voices/clones").json()
        assert len(listed["clones"]) == 1 and "sentinel" not in json.dumps(listed)
        voices = client.get("/api/studio/voices?language=de").json()
        eleven = next(p for p in voices["providers"] if p["id"] == "elevenlabs")
        assert any(v["id"] == "abcDEF123" and "geklont" in v["label"] for v in eleven["voices"])
        assert client.delete(f"/api/studio/voices/clones/{clone['id']}").json() == {"deleted": True}
        assert calls[-1][0] == "DELETE" and calls[-1][1].endswith("/v1/voices/abcDEF123")
        assert client.get("/api/studio/voices/clones").json()["clones"] == []
        os.environ.pop("ELEVENLABS_API_KEY")
        r = post({"name": "Meine Stimme", "basis": "own", "no_deception": "true"})
        assert r.status_code == 409 and r.json()["detail"]["code"] == "provider_not_configured"
    finally:
        remote.HTTP_RAW = original
        clear_env("ELEVENLABS_API_KEY")
        shutil.rmtree(tmp, ignore_errors=True)


def test_fal_errors_never_leak_the_key():
    tmp = tempfile.mkdtemp(prefix="ai_")
    try:
        def boom(method, url, headers, body=None, timeout=60.0):
            raise ConnectionError(str(headers))
        fal.FAL_HTTP = boom
        os.environ["FAL_KEY"] = "sentinel-fal-key"
        try:
            fal.run("fal-ai/x", {"prompt": "p"})
            raise AssertionError("ProviderError erwartet")
        except Exception as exc:  # noqa: BLE001
            assert "sentinel" not in str(exc) and "ConnectionError" in str(exc)
        fal.FAL_HTTP = lambda *a, **k: (401, {"detail": "bad key sentinel-fal-key"})
        try:
            fal.run("fal-ai/x", {"prompt": "p"})
            raise AssertionError("ProviderError erwartet")
        except Exception as exc:  # noqa: BLE001
            assert str(exc) == "fal: Schlüssel abgelehnt"
    finally:
        _restore()
        shutil.rmtree(tmp, ignore_errors=True)


if __name__ == "__main__":
    run_all(globals())
