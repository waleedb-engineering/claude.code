"""Betrieb: Speicherplatz-Prüfung vor schweren Aufgaben, Hardware-Encoder werden echt
getestet statt nur aufgelistet, Standard bleibt CPU."""

import collections

import pytest

from clipforge import hwaccel
from clipforge.studio.errors import StudioError
from clipforge.studio.tasks import check_disk_space
from studio_helpers import make_client, make_service


def test_disk_space_blocks_heavy_tasks(tmp_path, monkeypatch):
    svc, _ = make_service(str(tmp_path))
    Usage = collections.namedtuple("Usage", "total used free")
    monkeypatch.setattr("shutil.disk_usage", lambda p: Usage(10, 9, 200 * 1024 * 1024))
    monkeypatch.setenv("CLIPFORGE_MIN_FREE_MB", "500")
    with pytest.raises(StudioError) as e:
        svc.tasks.submit("render", None, {"mode": "preview"})
    assert e.value.code == "disk_space_low" and e.value.status == 507
    monkeypatch.setenv("CLIPFORGE_MIN_FREE_MB", "100")
    assert check_disk_space()["free_mb"] == 200


def test_listed_encoders_are_verified_and_default_is_cpu(monkeypatch):
    hwaccel.detect.cache_clear()
    monkeypatch.setattr(hwaccel, "_listed", lambda: {"h264_nvenc", "libx264"})
    monkeypatch.setattr(hwaccel, "_trial", lambda enc, *a, **k: (False, 0.0, "kein Gerät"))
    d = hwaccel.detect()
    assert d["working"] == [] and d["details"]["h264_nvenc"]["listed"] and not d["details"]["h264_nvenc"]["ok"]
    monkeypatch.setenv("CLIPFORGE_HWACCEL", "auto")
    assert hwaccel.selected_encoder() == "libx264"                      # Fallback, kein Absturz
    hwaccel.detect.cache_clear()
    monkeypatch.setattr(hwaccel, "_trial", lambda enc, *a, **k: (True, 0.1, ""))
    assert hwaccel.selected_encoder() == "h264_nvenc"
    assert hwaccel.encode_args("medium", 20)[:2] == ["-c:v", "h264_nvenc"]
    monkeypatch.delenv("CLIPFORGE_HWACCEL")
    assert hwaccel.encode_args("medium", 20) == ["-c:v", "libx264", "-preset", "medium", "-crf", "20"]
    hwaccel.detect.cache_clear()


def test_real_cpu_encode_and_system_endpoint(tmp_path):
    hwaccel.detect.cache_clear()
    ok, dt, err = hwaccel._trial("libx264", 1)
    assert ok and dt > 0 and not err
    client, _ = make_client(str(tmp_path))
    r = client.get("/api/studio/system/hwaccel").json()
    assert r["selected"] == "libx264" and "details" in r and "disk" in r
    hwaccel.detect.cache_clear()
