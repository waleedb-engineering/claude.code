"""Lokale Stimmen: eSpeak (pip, alle Systeme), Windows-SAPI, Piper, Sprechtempo."""

from __future__ import annotations

import os
import shutil
import subprocess
import tempfile
import wave

from studio_helpers import clear_env, ffprobe, make_service, run_all

from clipforge.studio.errors import ProviderError, StudioError
from clipforge.studio.providers import local, readiness, select_voice
from clipforge.studio.providers import espeak_lib

SCRIPT = "Lokale Videotools sparen Zeit und Geld. Alles bleibt auf deinem Rechner."


def _duration(path: str) -> float:
    with wave.open(path, "rb") as wf:
        return wf.getnframes() / wf.getframerate()


def test_bundled_espeak_speaks_german_and_english_with_word_timings():
    tmp = tempfile.mkdtemp(prefix="voice_")
    try:
        assert espeak_lib.available()
        prov = local.EspeakVoice()
        assert prov.status()[0] == "ready"
        for lang, text in (("de", "Guten Morgen, schöne Grüße aus Köln."),
                           ("en", "Good morning from the local studio.")):
            out = os.path.join(tmp, f"{lang}.wav")
            res = prov.synthesize(text, lang, prov.voices(lang)[1]["id"], out)
            assert _duration(out) > 1.0
            words = [w["text"] for w in res.words]
            assert words == [w.strip(",.") for w in text.split()], words
            starts = [w["start"] for w in res.words]
            assert starts == sorted(starts) and res.words[-1]["end"] <= _duration(out) + 0.01
        # Umlaute/Sonderzeichen kommen unbeschädigt an
        assert "schöne" in [w["text"] for w in prov.synthesize(
            "schöne Grüße", "de", "de", os.path.join(tmp, "u.wav")).words]
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def test_speech_rate_changes_real_duration_for_every_local_provider():
    tmp = tempfile.mkdtemp(prefix="voice_")
    try:
        prov = local.EspeakVoice()
        slow = _duration(prov.synthesize(SCRIPT, "de", "de", os.path.join(tmp, "s.wav"), speed=0.7).path)
        fast = _duration(prov.synthesize(SCRIPT, "de", "de", os.path.join(tmp, "f.wav"), speed=1.6).path)
        assert slow > fast * 1.6, (slow, fast)
        for cls in (local.SilentVoice, local.MockVoice):
            a = _duration(cls().synthesize(SCRIPT, "de", "x", os.path.join(tmp, "a.wav"), speed=1.0).path)
            b = _duration(cls().synthesize(SCRIPT, "de", "x", os.path.join(tmp, "b.wav"), speed=2.0).path)
            assert abs(a / b - 2.0) < 0.05
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def test_auto_selection_prefers_free_local_speech_over_silence_and_paid():
    os.environ["OPENAI_API_KEY"] = "test-key-not-real"
    try:
        # Windows: Systemstimmen (SAPI) gehen vor eSpeak — beides kostenlos und lokal
        local = ("espeak", "windows_sapi", "macos_say")
        for lang in ("de", "en"):
            auto = select_voice(lang, "friendly")
            assert auto["provider"] in local and auto["produces_speech"]
            if auto["provider"] == "espeak":
                assert auto["tone"] == "friendly"
        assert select_voice("de", "", allow_paid=True)["provider"] in local  # lokal vor Cloud
        states = {r["id"]: r["status"] for r in readiness()}
        assert states["espeak"] == "ready"
        if os.name != "nt":
            assert states["windows_sapi"] == "not_configured"     # Linux/macOS
        assert states["piper"] == "not_configured"            # kein Modell vorhanden
    finally:
        clear_env("OPENAI_API_KEY")


def test_render_uses_real_speech_and_word_accurate_captions():
    tmp = tempfile.mkdtemp(prefix="voice_")
    try:
        svc, _ = make_service(tmp)
        p = svc.create_project({"workflow": "script", "script": SCRIPT, "resolution": "720p",
                                "voice": {"provider": "auto", "speed": 1.2}})
        svc.tasks.submit("ingest", p["id"], {}, run_inline=True)
        t = svc.tasks.submit("render", p["id"], {"mode": "final"}, run_inline=True)
        assert t["status"] == "succeeded", t
        report = svc.get_render(p["id"], t["result"]["render_id"])
        assert report["voice"]["provider"] == "espeak"
        assert report["word_timing"] == ["tts"]               # nicht mehr geschätzt
        assert report["captions"]["applied_mode"] == "karaoke"
        assert report["captions"]["caption_blocks_count"] > 0
        path = svc.render_file(p["id"], report["render_id"])
        # Tonspur enthält wirklich Sprache (nicht Stille)
        out = subprocess.run(["ffmpeg", "-v", "info", "-i", path, "-af", "volumedetect", "-f",
                              "null", "-"], capture_output=True, text=True).stderr
        assert float(out.split("max_volume:")[1].split("dB")[0]) > -20.0
        assert any(s["codec_type"] == "audio" for s in ffprobe(path)["streams"])
        # abweichender Sprechtext → Caption-Timings werden ehrlich geschätzt
        p = svc.store.load(p["id"])
        scenes = [{**p["scenes"][0], "voice_text": "Ganz anderer gesprochener Text."}]
        p = svc.update_project(p["id"], {"scenes": scenes}, p["version"])
        t = svc.tasks.submit("render", p["id"], {"mode": "preview"}, run_inline=True)
        assert svc.get_render(p["id"], t["result"]["render_id"])["word_timing"] == ["estimated"]
        # Tempo ist Teil des Cache-Schlüssels: andere Geschwindigkeit → neue Synthese
        cache = os.path.join(svc.store.dir(p["id"]), "cache", "voice")
        before = len([f for f in os.listdir(cache) if f.endswith(".audio")])
        p = svc.update_project(p["id"], {"voice": {"provider": "espeak", "speed": 0.8}}, p["version"])
        svc.tasks.submit("render", p["id"], {"mode": "preview"}, run_inline=True)
        assert len([f for f in os.listdir(cache) if f.endswith(".audio")]) > before
        assert svc.store.load(p["id"])["voice"]["speed"] == 0.8
        p = svc.update_project(p["id"], {"voice": {"provider": "espeak", "speed": 9}}, p["version"])
        assert p["voice"]["speed"] == 2.0                     # begrenzt
    finally:
        clear_env()
        shutil.rmtree(tmp, ignore_errors=True)


def test_windows_sapi_builds_a_safe_powershell_call():
    tmp = tempfile.mkdtemp(prefix="voice_")
    calls = []
    real_run, real_system, real_which = local.subprocess.run, local.platform.system, local.shutil.which

    def fake_run(cmd, **kw):
        calls.append((cmd, kw))
        if "GetInstalledVoices" in cmd[-1]:
            return subprocess.CompletedProcess(cmd, 0, "Microsoft Hedda Desktop|de-DE|Female\n"
                                               "Microsoft Zira Desktop|en-US|Female\n", "")
        with open(kw["env"]["CF_OUT"], "wb") as fh:
            fh.write(b"RIFF")
        return subprocess.CompletedProcess(cmd, 0, "", "")
    try:
        local.subprocess.run = fake_run
        local.platform.system = lambda: "Windows"
        local.shutil.which = lambda name: "C:\\Windows\\powershell.exe" if name == "powershell" else None
        local.WindowsSapiVoice._cache = None
        prov = local.WindowsSapiVoice()
        assert prov.status()[0] == "ready"
        assert [v["id"] for v in prov.voices("de")] == ["Microsoft Hedda Desktop"]
        evil = 'Hallo"; Remove-Item C:\\ -Recurse; "'
        out = os.path.join(tmp, "o.wav")
        prov.synthesize(evil, "de", "unbekannt", out, speed=2.0)
        cmd, kw = calls[-1]
        assert evil not in " ".join(cmd)                      # Text nie auf der Kommandozeile
        assert open(kw["env"]["CF_TEXT"], encoding="utf-8").read() if os.path.exists(kw["env"]["CF_TEXT"]) else True
        assert kw["env"]["CF_VOICE"] == "Microsoft Hedda Desktop" and kw["env"]["CF_RATE"] == "10"
        assert kw["timeout"] == 300 and "-NoProfile" in cmd
        try:
            prov.synthesize("Hi", "fr", None, out)
            raise AssertionError("ProviderError erwartet")
        except ProviderError as exc:
            assert "keine Windows-Stimme" in str(exc)
    finally:
        local.subprocess.run, local.platform.system, local.shutil.which = real_run, real_system, real_which
        local.WindowsSapiVoice._cache = None
        shutil.rmtree(tmp, ignore_errors=True)


def test_piper_lists_only_complete_models_and_fails_cleanly():
    import importlib.util
    if importlib.util.find_spec("piper") is None:
        import pytest
        pytest.skip("optionales Paket piper-tts nicht installiert")
    tmp = tempfile.mkdtemp(prefix="voice_")
    try:
        os.environ["CLIPFORGE_PIPER_VOICES"] = tmp
        prov = local.PiperVoice()
        assert prov.status()[0] == "not_configured" and "Lokale KI-Modelle" in prov.status()[1]
        open(os.path.join(tmp, "de_DE-test-medium.onnx"), "wb").close()      # ohne .json
        assert not prov.configured()
        with open(os.path.join(tmp, "de_DE-test-medium.onnx.json"), "w") as fh:
            fh.write("{}")
        assert prov.configured() and [v["id"] for v in prov.voices("de")] == ["de_DE-test-medium"]
        assert prov.voices("en") == [] and "path" not in prov.voices("de")[0]
        try:
            prov.synthesize("Hallo", "de", None, os.path.join(tmp, "o.wav"))
            raise AssertionError("ProviderError erwartet")
        except ProviderError as exc:
            assert "Piper-Fehler" in str(exc)                  # kaputtes Modell → sauberer Fehler
    finally:
        clear_env("CLIPFORGE_PIPER_VOICES")
        shutil.rmtree(tmp, ignore_errors=True)


def test_credentials_work_without_fchmod_like_on_old_windows_python():
    from clipforge.studio import credentials
    tmp = tempfile.mkdtemp(prefix="voice_")
    saved = getattr(os, "fchmod", None)
    try:
        os.environ["CLIPFORGE_ENV_FILE"] = os.path.join(tmp, ".env")
        del os.fchmod
        credentials.set_key("openai", "sentinel-windows-key")
        assert "OPENAI_API_KEY='sentinel-windows-key'" in open(os.environ["CLIPFORGE_ENV_FILE"]).read()
    finally:
        if saved is not None:
            os.fchmod = saved
        clear_env("CLIPFORGE_ENV_FILE", "OPENAI_API_KEY")
        shutil.rmtree(tmp, ignore_errors=True)


def test_voice_preview_uses_local_speech():
    tmp = tempfile.mkdtemp(prefix="voice_")
    try:
        svc, _ = make_service(tmp)
        path = svc.voice_preview("de", "auto", None)
        assert os.path.getsize(path) > 2000
        try:
            svc.voice_preview("fr", "auto", None)
            raise AssertionError("validation_error erwartet")
        except StudioError as exc:
            assert exc.code == "validation_error"
    finally:
        clear_env()
        shutil.rmtree(tmp, ignore_errors=True)


if __name__ == "__main__":
    run_all(globals())
