"""Plattform-Unabhängigkeit: Windows-Pfade für FFmpeg, .env ohne Bash,
gesperrte Dateien beim Ersetzen."""

from __future__ import annotations

import os
import shutil
import subprocess
import tempfile

from studio_helpers import run_all

from clipforge import envfile
from clipforge.ffmpeg_utils import concat_entry, filter_path
from clipforge.studio import storage

ASS = """[Script Info]
ScriptType: v4.00+
PlayResX: 320
PlayResY: 240
[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, OutlineColour, BackColour, Bold, Italic, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Default,Arial,40,&H00FFFFFF,&H00000000,&H00000000,0,0,1,2,0,2,10,10,10,1
[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
Dialogue: 0,0:00:00.00,0:00:01.00,Default,,0,0,0,,Hallo
"""


def test_windows_paths_are_converted_for_ffmpeg():
    assert filter_path(r"C:\Users\walid.butt\AppData\Local\Temp\a.ass") == \
        r"C\\:/Users/walid.butt/AppData/Local/Temp/a.ass"
    assert concat_entry(r"C:\Users\o'neil\seg 1.mp4") == "file 'C:/Users/o'\\''neil/seg 1.mp4'"


def test_hostile_paths_work_with_real_ffmpeg():
    base = tempfile.mkdtemp(prefix="plat_")
    try:
        d = os.path.join(base, "O'Neil [x]: a,b;c")
        os.makedirs(d)
        ass, seg = os.path.join(d, "c.ass"), os.path.join(d, "seg.mp4")
        with open(ass, "w") as fh:
            fh.write(ASS)
        r = subprocess.run(["ffmpeg", "-y", "-v", "error", "-f", "lavfi", "-i",
                            "color=c=blue:s=320x240:d=1", "-vf", f"ass={filter_path(ass)}", seg],
                           capture_output=True, text=True)
        assert r.returncode == 0, r.stderr
        lst, out = os.path.join(d, "l.txt"), os.path.join(d, "o.mp4")
        with open(lst, "w") as fh:
            fh.write(concat_entry(seg) + "\n" + concat_entry(seg) + "\n")
        r = subprocess.run(["ffmpeg", "-y", "-v", "error", "-f", "concat", "-safe", "0", "-i", lst,
                            "-c", "copy", out], capture_output=True, text=True)
        assert r.returncode == 0 and os.path.getsize(out) > 0, r.stderr
    finally:
        shutil.rmtree(base, ignore_errors=True)


def test_env_file_is_parsed_without_bash_and_never_overrides():
    text = ("# Kommentar\nexport A='a b'\nB=\"x\\\"y\"\nC=plain # Kommentar\n"
            "D='it'\\''s'\nE=\nkaputt ohne gleich\nF=sk-sentinel$pecial'\"chars #x=y\n"
            "G='sk-sentinel$pecial'\\''\"chars #x=y'\n")
    v = envfile.parse(text)
    assert v["A"] == "a b" and v["B"] == 'x"y' and v["C"] == "plain"
    assert v["D"] == "it's" and v["E"] == "" and "kaputt" not in " ".join(v)
    assert v["G"] == "sk-sentinel$pecial'\"chars #x=y"      # Format, das ClipForge schreibt
    tmp = tempfile.mkdtemp(prefix="plat_")
    try:
        path = os.path.join(tmp, ".env")
        with open(path, "w") as fh:
            fh.write("CF_TEST_NEW='neu'\nCF_TEST_SET='aus-datei'\n")
        os.environ["CF_TEST_SET"] = "aus-umgebung"
        assert envfile.load(path) == ["CF_TEST_NEW"]
        assert os.environ["CF_TEST_NEW"] == "neu" and os.environ["CF_TEST_SET"] == "aus-umgebung"
        assert envfile.load(os.path.join(tmp, "fehlt")) == []
    finally:
        for k in ("CF_TEST_NEW", "CF_TEST_SET"):
            os.environ.pop(k, None)
        shutil.rmtree(tmp, ignore_errors=True)


def test_credentials_written_by_clipforge_round_trip_through_the_parser():
    from clipforge.studio import credentials
    tmp = tempfile.mkdtemp(prefix="plat_")
    key = "sk-sentinel$pecial'\"chars #x=y"
    try:
        os.environ["CLIPFORGE_ENV_FILE"] = os.path.join(tmp, ".env")
        credentials.set_key("openai", key)
        os.environ.pop("OPENAI_API_KEY")
        envfile.load(os.environ["CLIPFORGE_ENV_FILE"])     # wie beim Windows-Neustart
        assert os.environ["OPENAI_API_KEY"] == key
    finally:
        for k in ("CLIPFORGE_ENV_FILE", "OPENAI_API_KEY"):
            os.environ.pop(k, None)
        shutil.rmtree(tmp, ignore_errors=True)


def test_replace_retries_while_windows_holds_the_file():
    tmp = tempfile.mkdtemp(prefix="plat_")
    real = os.replace
    attempts = []

    def flaky(src, dst):
        attempts.append(1)
        if len(attempts) < 3:
            raise PermissionError("Datei wird von einem anderen Prozess verwendet")
        return real(src, dst)
    try:
        storage.os.replace = flaky
        path = os.path.join(tmp, "p.json")
        storage.write_json_atomic(path, {"ok": True})
        assert storage.read_json(path) == {"ok": True} and len(attempts) == 3
        attempts.clear()
        storage.os.replace = lambda s, d: (_ for _ in ()).throw(PermissionError("dauerhaft"))
        try:
            storage.write_json_atomic(path, {"ok": False})
            raise AssertionError("PermissionError erwartet")
        except PermissionError:
            pass
        assert storage.read_json(path) == {"ok": True}              # alte Datei intakt
        assert [f for f in os.listdir(tmp) if f.endswith(".tmp")] == []
    finally:
        storage.os.replace = real
        shutil.rmtree(tmp, ignore_errors=True)


def test_powershell_scripts_exist_and_never_inline_secrets():
    root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    for name in ("setup_windows.ps1", "start_windows.ps1"):
        text = open(os.path.join(root, "scripts", name), encoding="utf-8").read()
        assert "API_KEY" not in text and "Invoke-Expression" not in text
    start = open(os.path.join(root, "scripts", "start_windows.ps1"), encoding="utf-8").read()
    assert "127.0.0.1" in start and "0.0.0.0" not in start         # nie ins Netz binden


if __name__ == "__main__":
    run_all(globals())
