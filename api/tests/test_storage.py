"""Tests für Storage-Übersicht (/api/storage) und Bulk-Delete (Prompt 15).

Nutzt synthetische Job-Ordner + TestClient (kein ffmpeg nötig). Statuswerte
werden direkt gesetzt, Dateien mit bekannten Größen erzeugt.
"""

from __future__ import annotations

import os
import shutil
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from jobs import (
    STATUS_COMPLETED,
    STATUS_FAILED,
    STATUS_INCOMPLETE,
    STATUS_INTERRUPTED,
    STATUS_PROCESSING,
)


def _make_client(tmp_jobs: str):
    os.environ["CLIPFORGE_JOBS_DIR"] = tmp_jobs
    sys.modules.pop("app", None)
    from fastapi.testclient import TestClient
    import app as app_module
    return TestClient(app_module.app), app_module


def _touch(path: str, size: int) -> None:
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "wb") as fh:
        fh.write(b"\x00" * size)


def _job(app_module, status: str, *, auto=0, manual=0, filename="x.mp4",
         auto_size=1000, manual_size=500):
    job = app_module.registry.create(filename=filename, top_n=2)
    job.status = status
    for i in range(1, auto + 1):
        _touch(os.path.join(job.job_dir, f"clip_{i:02d}_score80.mp4"), auto_size)
    for i in range(manual):
        eid = f"clip_1_2026010{i}T000000Z"
        _touch(os.path.join(job.job_dir, "manual_exports", f"{eid}.mp4"), manual_size)
        _touch(os.path.join(job.job_dir, "manual_exports", f"{eid}.json"), 50)
    return job


# ------------------------------- Storage ----------------------------------

def test_storage_counts_jobs_and_bytes():
    tmp = tempfile.mkdtemp(prefix="stor_")
    try:
        client, app_module = _make_client(os.path.join(tmp, "jobs"))
        _job(app_module, STATUS_COMPLETED, auto=2, manual=1)  # 2000+500(+~150)
        _job(app_module, STATUS_FAILED)
        r = client.get("/api/storage")
        assert r.status_code == 200, r.text
        d = r.json()
        assert d["total_jobs"] == 2
        assert d["total_bytes"] > 2500
        assert d["total_human"].endswith(("B", "KB", "MB"))
        assert d["counts"]["auto_exports"] == 2
        assert d["counts"]["manual_exports"] == 1
        assert d["counts"]["total_exports"] == 3
        assert "jobs_root" in d
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def test_storage_status_distribution():
    tmp = tempfile.mkdtemp(prefix="stor_")
    try:
        client, app_module = _make_client(os.path.join(tmp, "jobs"))
        _job(app_module, STATUS_COMPLETED)
        _job(app_module, STATUS_FAILED)
        _job(app_module, STATUS_INTERRUPTED)
        _job(app_module, STATUS_INCOMPLETE)
        _job(app_module, STATUS_PROCESSING)
        d = client.get("/api/storage").json()
        bs = d["by_status"]
        assert bs[STATUS_COMPLETED] == 1
        assert bs[STATUS_FAILED] == 1
        assert bs[STATUS_INTERRUPTED] == 1
        assert bs[STATUS_INCOMPLETE] == 1
        assert bs[STATUS_PROCESSING] == 1
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def test_storage_largest_jobs_sorted():
    tmp = tempfile.mkdtemp(prefix="stor_")
    try:
        client, app_module = _make_client(os.path.join(tmp, "jobs"))
        small = _job(app_module, STATUS_COMPLETED, auto=1, auto_size=100)
        big = _job(app_module, STATUS_COMPLETED, auto=1, auto_size=999999)
        d = client.get("/api/storage").json()
        largest = d["largest_jobs"]
        assert largest[0]["job_id"] == big.id
        assert largest[0]["bytes"] > largest[-1]["bytes"]
        # Felder vorhanden
        for k in ("job_id", "status", "filename", "bytes", "human_size",
                  "auto_export_count", "manual_export_count", "restored",
                  "created_at", "updated_at"):
            assert k in largest[0], k
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def test_storage_cleanup_candidates():
    tmp = tempfile.mkdtemp(prefix="stor_")
    try:
        client, app_module = _make_client(os.path.join(tmp, "jobs"))
        jf = _job(app_module, STATUS_FAILED)
        ji = _job(app_module, STATUS_INTERRUPTED)
        jc = _job(app_module, STATUS_INCOMPLETE)
        jok = _job(app_module, STATUS_COMPLETED, auto=1)  # kein Kandidat
        jempty = _job(app_module, STATUS_COMPLETED)       # completed_without_exports
        cc = client.get("/api/storage").json()["cleanup_candidates"]
        assert jf.id in cc["failed"]
        assert ji.id in cc["interrupted"]
        assert jc.id in cc["incomplete"]
        assert jok.id not in cc["completed_without_exports"]
        assert jempty.id in cc["completed_without_exports"]
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def test_storage_broken_job_does_not_crash():
    tmp = tempfile.mkdtemp(prefix="stor_")
    try:
        client, app_module = _make_client(os.path.join(tmp, "jobs"))
        job = _job(app_module, STATUS_COMPLETED, auto=1)
        # Ordner unter dem Job entfernen, Registry-Eintrag bleibt (kaputt)
        shutil.rmtree(job.job_dir, ignore_errors=True)
        r = client.get("/api/storage")
        assert r.status_code == 200
        assert r.json()["total_jobs"] >= 1
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


# ------------------------------ Bulk-Delete -------------------------------

def test_bulk_delete_removes_problem_jobs():
    tmp = tempfile.mkdtemp(prefix="stor_")
    try:
        client, app_module = _make_client(os.path.join(tmp, "jobs"))
        jf = _job(app_module, STATUS_FAILED, auto=1)
        ji = _job(app_module, STATUS_INTERRUPTED)
        jok = _job(app_module, STATUS_COMPLETED, auto=2)
        r = client.post("/api/jobs/bulk-delete",
                        json={"job_ids": [jf.id, ji.id], "confirm": "DELETE"})
        assert r.status_code == 200, r.text
        d = r.json()
        assert d["deleted_count"] == 2
        assert d["failed_count"] == 0
        assert d["removed_bytes"] >= 0
        assert not os.path.isdir(jf.job_dir)
        assert not os.path.isdir(ji.job_dir)
        # completed unberührt
        assert os.path.isdir(jok.job_dir)
        assert client.get(f"/api/jobs/{jok.id}").status_code == 200
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def test_bulk_delete_wrong_confirm_400():
    tmp = tempfile.mkdtemp(prefix="stor_")
    try:
        client, app_module = _make_client(os.path.join(tmp, "jobs"))
        j = _job(app_module, STATUS_FAILED)
        assert client.post("/api/jobs/bulk-delete",
                           json={"job_ids": [j.id], "confirm": "yes"}).status_code == 400
        # confirm fehlt
        assert client.post("/api/jobs/bulk-delete",
                           json={"job_ids": [j.id]}).status_code == 400
        assert os.path.isdir(j.job_dir)  # nichts gelöscht
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def test_bulk_delete_empty_ids_400():
    tmp = tempfile.mkdtemp(prefix="stor_")
    try:
        client, _ = _make_client(os.path.join(tmp, "jobs"))
        assert client.post("/api/jobs/bulk-delete",
                           json={"job_ids": [], "confirm": "DELETE"}).status_code == 400
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def test_bulk_delete_processing_without_force_reported():
    tmp = tempfile.mkdtemp(prefix="stor_")
    try:
        client, app_module = _make_client(os.path.join(tmp, "jobs"))
        jp = _job(app_module, STATUS_PROCESSING)
        jf = _job(app_module, STATUS_FAILED)
        d = client.post("/api/jobs/bulk-delete",
                        json={"job_ids": [jp.id, jf.id], "confirm": "DELETE"}).json()
        assert d["deleted_count"] == 1
        assert d["failed_count"] == 1
        by_id = {r["job_id"]: r for r in d["results"]}
        assert by_id[jp.id]["deleted"] is False
        assert "force" in by_id[jp.id]["error"]
        assert os.path.isdir(jp.job_dir)      # processing geschützt
        assert not os.path.isdir(jf.job_dir)  # failed gelöscht
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def test_bulk_delete_traversal_blocked_and_partial():
    tmp = tempfile.mkdtemp(prefix="stor_")
    try:
        client, app_module = _make_client(os.path.join(tmp, "jobs"))
        outside = os.path.join(tmp, "keep.txt")
        _touch(outside, 10)
        jf = _job(app_module, STATUS_FAILED)
        d = client.post("/api/jobs/bulk-delete", json={
            "job_ids": ["../keep", "../../etc", jf.id], "confirm": "DELETE",
        }).json()
        assert d["deleted_count"] == 1
        assert d["failed_count"] == 2
        assert os.path.exists(outside), "Datei außerhalb jobs/ angetastet!"
        assert not os.path.isdir(jf.job_dir)
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def test_bulk_delete_completed_only_when_explicit():
    tmp = tempfile.mkdtemp(prefix="stor_")
    try:
        client, app_module = _make_client(os.path.join(tmp, "jobs"))
        jc = _job(app_module, STATUS_COMPLETED, auto=1)
        # explizit angegeben → wird gelöscht (API erlaubt es; UI tut es nicht)
        d = client.post("/api/jobs/bulk-delete",
                        json={"job_ids": [jc.id], "confirm": "DELETE"}).json()
        assert d["deleted_count"] == 1
        assert not os.path.isdir(jc.job_dir)
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
