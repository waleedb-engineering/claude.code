"""Audio-Ereignis-Heuristik: Klassen auf SYNTHETISCHEN Signalen, Wirkung im Ranking
(Modus 'rank' vs. 'explain'), neue Auswertungsmetriken. Kein Nachweis für echte Streams."""

import os
import subprocess

import pytest

from clipforge.stream import audio_events as ae
from clipforge.stream import evaluate as ev
from clipforge.stream import signals

BG = "anoisesrc=c=pink:a=0.02:r=16000"
EVENTS = {
    "music": "aevalsrc='0.15*sin(2*PI*220*t)+0.12*sin(2*PI*277*t)+0.1*sin(2*PI*330*t)':s=16000",
    "applause": "anoisesrc=c=white:a=0.5:r=16000,volume='if(lt(mod(t*9.3+0.37*sin(t*7),1),0.25),1,0.05)':eval=frame",
    "cheering": "anoisesrc=c=white:a=0.5:r=16000,highpass=f=300,lowpass=f=6000",
    "screaming": "aevalsrc='0.6*sin(2*PI*800*t+6*sin(2*PI*6*t))+0.3*sin(2*PI*1600*t+12*sin(2*PI*6*t))':s=16000",
    "laughter": "aevalsrc='0.5*(gt(sin(2*PI*5*t),0))*(sin(2*PI*260*t)+0.5*sin(2*PI*520*t)+0.3*sin(2*PI*780*t))':s=16000",
}


def _scene(path, parts):
    """parts: [(lavfi-quelle, sekunden)] → Mono-16-kHz-WAV."""
    args, chain = ["ffmpeg", "-y", "-v", "error"], ""
    for i, (src, sec) in enumerate(parts):
        args += ["-f", "lavfi", "-t", str(sec), "-i", src]
        chain += f"[{i}:a]aformat=sample_rates=16000:channel_layouts=mono[a{i}];"
    chain += "".join(f"[a{i}]" for i in range(len(parts))) + f"concat=n={len(parts)}:v=0:a=1"
    subprocess.run(args + ["-filter_complex", chain, "-ar", "16000", path], check=True)
    return path


@pytest.mark.parametrize("name", sorted(EVENTS))
def test_classes_on_synthetic_signals(tmp_path, name):
    a = signals.audio_features(_scene(str(tmp_path / "s.wav"), [(BG, 20), (EVENTS[name], 6), (BG, 4)]))
    p = ae.classify(a)
    mean = {k: sum(v[21:25]) / 4 for k, v in p.items()}
    assert max(mean, key=mean.get) == name, mean
    assert max(p["silence"][21:25]) < 0.1


def test_speech_from_local_tts(tmp_path):
    from clipforge.studio.providers.local import EspeakVoice
    path = str(tmp_path / "sp.wav")
    EspeakVoice().synthesize("Hallo zusammen, heute schauen wir uns gemeinsam an, wie man ein gutes Video "
                             "schneidet und worauf es ankommt.", "de", None, path)
    p = ae.classify(signals.audio_features(path))
    mean = {k: sum(v) / len(v) for k, v in p.items()}
    assert max(mean, key=mean.get) == "speech", mean


def _video_with_audio(tmp_path, wav):
    out = str(tmp_path / "v.mp4")
    subprocess.run(["ffmpeg", "-y", "-v", "error", "-f", "lavfi", "-i", "color=c=gray:s=160x90:r=5:d=70",
                    "-i", wav, "-shortest", "-c:v", "libx264", "-preset", "ultrafast", "-c:a", "aac", out], check=True)
    return out


def test_rank_mode_prefers_quiet_laughter_over_loud_music(tmp_path):
    """Laute Musik (bedeutungslos) gegen leiseres Lachen, ohne Chat."""
    from clipforge.stream.analyze import analyze
    loud_music = EVENTS["music"].replace("0.15*", "0.6*").replace("0.12*", "0.5*").replace("0.1*", "0.4*")
    wav = _scene(str(tmp_path / "mix.wav"), [(BG, 15), (loud_music, 12), (BG, 18), (EVENTS["laughter"], 6), (BG, 19)])
    video = _video_with_audio(tmp_path, wav)
    explain = analyze(video, max_clips=2, audio_events_mode="explain")
    rank = analyze(video, max_clips=2, audio_events_mode="rank")
    top_explain, top_rank = explain["highlights"][0], rank["highlights"][0]
    assert 13 <= top_explain["t"] <= 28                     # ohne Ereignisse gewinnt die laute Musik
    assert 44 <= top_rank["t"] <= 52                        # mit Ereignissen das Lachen
    assert any("Lachen" in r for r in top_rank["reasons"])
    assert rank["audio_events"]["mode"] == "rank" and "laughter" in rank["audio_events"]["heatmap"]
    off = analyze(video, max_clips=2, audio_events_mode="off")
    assert off["audio_events"] == {"used": False, "mode": "off"}


def test_metrics_duplicates_missed_and_boundaries():
    labels = ev.load_labels({"highlights": [{"start": 10, "end": 20, "peak": 12}, {"start": 50, "end": 55}]})
    pred = [{"t": 12, "start": 8, "end": 24, "score": 9}, {"t": 15, "start": 12, "end": 26, "score": 5}]
    r = ev.evaluate(pred, labels)
    assert r["duplicates"] == 1 and r["duplicate_rate"] == 0.5 and r["missed_rate"] == 0.5
    assert r["start_error_abs_mean_s"] == 2.0 and r["end_error_abs_mean_s"] == 4.0
    assert ev.aggregate([r])["duplicates"] == 1


def test_disable_switch(monkeypatch, tmp_path):
    monkeypatch.setenv("CLIPFORGE_AUDIO_EVENTS", "0")
    a = signals.audio_features(_scene(str(tmp_path / "s.wav"), [(BG, 3)]))
    assert "flatness" not in a and ae.classify(a) == {}
