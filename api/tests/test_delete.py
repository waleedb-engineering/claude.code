"""Tests für sicheres Löschen von Jobs und manuellen Exporten (Prompt 14).

Die Sicherheits-/Logiktests laufen ohne ffmpeg (synthetische Ordner). Die
HTTP-/ZIP-Regressionstests rendern echt und überspringen sauber, wenn
ffmpeg/Fixtures fehlen.
"""

from __future__ import annotations

import io
import json
import os
import shutil
import sys
import tempfile
import zipfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import jobs as jobs_mod
from jobs import (
    STATUS_PROCESSING,
    JobBusy,
    JobNotFound,
    JobRegistry,
    UnsafeJobPath,
)
from clipforge.rerender import (
    ManualExportError,
    delete_manual_export,
    manual_dir,
)

_HERE = os.path.dirname(os.path.abspath(__file__))
_API_DIR = os.path.dirname(_HERE)
_SAMPLE = os.path.join(_API_DIR, "testdata", "sample.mp4")
_TRANSCRIPT = os.path.join(_API_DIR, "testdata", "transcript.json")


def _ready() -> bool:
    return (
        shutil.which("ffmpeg") is not None
        and os.path.exists(_SAMPLE)
        and os.path.exists(_TRANSCRIPT)
    )


def _touch(path: str, data: bytes = b"\x00\x00") -> None:
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "wb") as fh:
        fh.write(data)


# ---------------- Job-Delete: Logik & Sicherheit (ohne ffmpeg) -------------

def test_delete_completed_job_removes_dir():
    tmp = tempfile.mkdtemp(prefix="del_")
    try:
        base = os.path.join(tmp, "jobs")
        reg = JobRegistry(base)
        job = reg.create(filename="a.mp4", top_n=1)
        _touch(os.path.join(job.job_dir, "clip_01_score80.mp4"))
        _touch(os.path.join(job.job_dir, "clips.json"), b"{}")
        res = reg.delete(job.id)
        assert res["deleted"] is True
        assert res["job_id"] == job.id
        assert res["removed_files_count"] >= 2
        assert res["removed_bytes"] > 0
        assert not os.path.exists(job.job_dir)
        assert reg.get(job.id) is None
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def test_delete_nonexistent_job_raises_notfound():
    tmp = tempfile.mkdtemp(prefix="del_")
    try:
        reg = JobRegistry(os.path.join(tmp, "jobs"))
        try:
            reg.delete("deadbeef0000")
            assert False, "sollte JobNotFound werfen"
        except JobNotFound:
            pass
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def test_delete_processing_without_force_raises_busy():
    tmp = tempfile.mkdtemp(prefix="del_")
    try:
        reg = JobRegistry(os.path.join(tmp, "jobs"))
        job = reg.create(filename="p.mp4", top_n=1)
        job.status = STATUS_PROCESSING
        try:
            reg.delete(job.id)
            assert False, "sollte JobBusy werfen"
        except JobBusy:
            pass
        assert os.path.exists(job.job_dir)  # nichts gelöscht
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def test_delete_processing_with_force_deletes():
    tmp = tempfile.mkdtemp(prefix="del_")
    try:
        reg = JobRegistry(os.path.join(tmp, "jobs"))
        job = reg.create(filename="p.mp4", top_n=1)
        job.status = STATUS_PROCESSING
        res = reg.delete(job.id, force=True)
        assert res["deleted"] is True
        assert not os.path.exists(job.job_dir)
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def test_delete_job_id_traversal_blocked():
    tmp = tempfile.mkdtemp(prefix="del_")
    try:
        base = os.path.join(tmp, "jobs")
        reg = JobRegistry(base)
        # eine Datei außerhalb von jobs/, die NICHT gelöscht werden darf
        outside = os.path.join(tmp, "secret.txt")
        _touch(outside, b"keep me")
        for bad in ("..", "../", "../secret", "../../etc", "/etc/passwd",
                    "a/b", "..\\..", "."):
            try:
                reg.delete(bad)
                assert False, f"sollte UnsafeJobPath werfen für {bad!r}"
            except (UnsafeJobPath, JobNotFound):
                # UnsafeJobPath erwünscht; JobNotFound auch ok (nie gelöscht)
                pass
        assert os.path.exists(outside), "Datei außerhalb jobs/ wurde angetastet!"
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def test_safe_job_dir_valid_path():
    tmp = tempfile.mkdtemp(prefix="del_")
    try:
        base = os.path.join(tmp, "jobs")
        reg = JobRegistry(base)
        p = reg.safe_job_dir("abc123def456")
        assert p == os.path.realpath(os.path.join(base, "abc123def456"))
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


# ---------------- Manual-Export-Delete: Logik & Sicherheit -----------------

def _setup_manual(job_dir: str, export_id: str = "clip_1_20260101T000000Z"):
    md = manual_dir(job_dir)
    _touch(os.path.join(md, f"{export_id}.mp4"), b"\x00" * 100)
    _touch(os.path.join(md, f"{export_id}.json"),
           json.dumps({"export_id": export_id, "output_file": f"{export_id}.mp4"}).encode())
    return export_id


def test_delete_manual_export_removes_mp4_and_json():
    tmp = tempfile.mkdtemp(prefix="del_")
    try:
        job_dir = os.path.join(tmp, "job1")
        eid = _setup_manual(job_dir)
        res = delete_manual_export(job_dir, eid)
        assert res["deleted"] is True
        assert res["export_id"] == eid
        assert f"{eid}.mp4" in res["removed_files"]
        assert f"{eid}.json" in res["removed_files"]
        assert res["removed_bytes"] > 0
        md = manual_dir(job_dir)
        assert not os.path.exists(os.path.join(md, f"{eid}.mp4"))
        assert not os.path.exists(os.path.join(md, f"{eid}.json"))
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def test_delete_manual_export_keeps_auto_clips():
    tmp = tempfile.mkdtemp(prefix="del_")
    try:
        job_dir = os.path.join(tmp, "job1")
        eid = _setup_manual(job_dir)
        auto = os.path.join(job_dir, "clip_01_score80.mp4")
        _touch(auto, b"\x00" * 50)
        delete_manual_export(job_dir, eid)
        assert os.path.exists(auto), "Auto-Clip darf nicht gelöscht werden!"
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def test_delete_manual_export_missing_returns_none():
    tmp = tempfile.mkdtemp(prefix="del_")
    try:
        job_dir = os.path.join(tmp, "job1")
        os.makedirs(manual_dir(job_dir), exist_ok=True)
        assert delete_manual_export(job_dir, "nope_does_not_exist") is None
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def test_delete_manual_export_traversal_blocked():
    tmp = tempfile.mkdtemp(prefix="del_")
    try:
        job_dir = os.path.join(tmp, "job1")
        os.makedirs(manual_dir(job_dir), exist_ok=True)
        # Auto-Clip, den ein Traversal treffen könnte
        auto = os.path.join(job_dir, "clip_01_score80.mp4")
        _touch(auto, b"keep")
        for bad in ("../clip_01_score80", "../../secret", "a/b", "..\\x", "/etc/passwd"):
            try:
                delete_manual_export(job_dir, bad)
                # falls kein Fehler: darf trotzdem nichts außerhalb gelöscht haben
            except ManualExportError:
                pass
        assert os.path.exists(auto), "Traversal hat Auto-Clip getroffen!"
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


# ---------------- HTTP + ZIP-Regression (mit ffmpeg) -----------------------

def _make_client(tmp_jobs: str):
    os.environ["CLIPFORGE_JOBS_DIR"] = tmp_jobs
    sys.modules.pop("app", None)
    from fastapi.testclient import TestClient
    import app as app_module
    return TestClient(app_module.app), app_module


def _run_job(client) -> str:
    import time
    with open(_SAMPLE, "rb") as vf, open(_TRANSCRIPT, "rb") as tf:
        r = client.post("/api/jobs", files={
            "file": ("sample.mp4", vf, "video/mp4"),
            "transcript": ("transcript.json", tf, "application/json"),
        }, data={"top_n": "2"})
    jid = r.json()["job_id"]
    st = "processing"
    for _ in range(240):
        st = client.get(f"/api/jobs/{jid}").json()["status"]
        if st in ("completed", "failed"):
            break
        time.sleep(0.5)
    assert st == "completed", st
    return jid


def test_http_delete_job_then_404():
    if not _ready():
        print("  (übersprungen: ffmpeg/Fixtures fehlen)")
        return
    tmp = tempfile.mkdtemp(prefix="del_http_")
    try:
        client, _ = _make_client(os.path.join(tmp, "jobs"))
        jid = _run_job(client)
        d = client.request("DELETE", f"/api/jobs/{jid}")
        assert d.status_code == 200, d.text
        body = d.json()
        assert body["deleted"] is True and body["removed_files_count"] > 0
        assert client.get(f"/api/jobs/{jid}").status_code == 404
        assert client.get("/api/jobs").json()["jobs"] == []
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def test_http_delete_manual_updates_zip_and_counts():
    if not _ready():
        print("  (übersprungen: ffmpeg/Fixtures fehlen)")
        return
    tmp = tempfile.mkdtemp(prefix="del_http_")
    try:
        client, _ = _make_client(os.path.join(tmp, "jobs"))
        jid = _run_job(client)
        rr = client.post(f"/api/jobs/{jid}/clips/1/rerender", json={
            "start_time": 1.0, "end_time": 12.0, "remove_silence": False,
            "reframe_mode": "center",
        })
        assert rr.status_code == 200
        eid = rr.json()["export_id"]

        # vor Delete: 1 manueller Export, in all-exports.zip
        assert client.get(f"/api/jobs/{jid}").json()["files"]["manual_export_count"] == 1
        z1 = zipfile.ZipFile(io.BytesIO(client.get(f"/api/jobs/{jid}/all-exports.zip").content))
        assert any("manual_exports/" in n and n.endswith(".mp4") for n in z1.namelist())

        # löschen
        d = client.request("DELETE", f"/api/jobs/{jid}/manual-exports/{eid}")
        assert d.status_code == 200, d.text
        assert set(["removed_files", "removed_bytes", "deleted"]).issubset(d.json())

        # danach: Liste leer, Counts aktualisiert, ZIP ohne Manual, Auto-Clips da
        assert client.get(f"/api/jobs/{jid}/manual-exports").json()["exports"] == []
        f = client.get(f"/api/jobs/{jid}").json()["files"]
        assert f["manual_export_count"] == 0
        assert f["total_export_count"] == f["auto_export_count"]
        assert f["has_manual_exports"] is False
        z2 = zipfile.ZipFile(io.BytesIO(client.get(f"/api/jobs/{jid}/all-exports.zip").content))
        assert not any("manual_exports/" in n and n.endswith(".mp4") for n in z2.namelist())
        assert any(n.startswith("auto_clips/") for n in z2.namelist())
        # exports.zip (Auto) weiter ok
        assert client.get(f"/api/jobs/{jid}/exports.zip").status_code == 200
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def test_http_delete_manual_traversal_400_or_404():
    if not _ready():
        print("  (übersprungen: ffmpeg/Fixtures fehlen)")
        return
    tmp = tempfile.mkdtemp(prefix="del_http_")
    try:
        client, _ = _make_client(os.path.join(tmp, "jobs"))
        jid = _run_job(client)
        r = client.request("DELETE", f"/api/jobs/{jid}/manual-exports/..%2F..%2Fclips")
        assert r.status_code in (400, 404), r.status_code
        # Auto-Clips unversehrt
        assert client.get(f"/api/jobs/{jid}/clips/1/download").status_code == 200
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def _run_all():
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for fn in fns:
        fn()
        print(f"  ✓ {fn.__name__}")
    print(f"\n{len(fns)} Tests bestanden.")


if __name__ == "__main__":
    _run_all()
