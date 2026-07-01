"""Tests für Upload-Limits (Einzel & Batch) und /api/config (Prompt 17)."""

from __future__ import annotations

import io
import os
import shutil
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def _make_client(tmp_jobs: str, **env):
    os.environ["CLIPFORGE_JOBS_DIR"] = tmp_jobs
    for k, v in env.items():
        os.environ[k] = str(v)
    sys.modules.pop("app", None)
    from fastapi.testclient import TestClient
    import app as app_module
    return TestClient(app_module.app), app_module


def _cleanup_env(*keys):
    for k in keys:
        os.environ.pop(k, None)


def test_config_endpoint():
    tmp = tempfile.mkdtemp(prefix="lim_")
    try:
        client, _ = _make_client(os.path.join(tmp, "jobs"),
                                 CLIPFORGE_MAX_UPLOAD_MB=250,
                                 CLIPFORGE_MAX_BATCH_FILES=5)
        d = client.get("/api/config").json()
        assert d["max_upload_mb"] == 250
        assert d["max_batch_files"] == 5
        assert ".mp4" in d["supported_video_types"]
        assert "max_workers" in d
    finally:
        _cleanup_env("CLIPFORGE_MAX_UPLOAD_MB", "CLIPFORGE_MAX_BATCH_FILES")
        shutil.rmtree(tmp, ignore_errors=True)


def test_single_upload_too_large_413():
    tmp = tempfile.mkdtemp(prefix="lim_")
    try:
        client, _ = _make_client(os.path.join(tmp, "jobs"), CLIPFORGE_MAX_UPLOAD_MB=1)
        big = io.BytesIO(b"\x00" * (2 * 1024 * 1024))  # 2 MB > 1 MB Limit
        r = client.post("/api/jobs", files={"file": ("big.mp4", big, "video/mp4")})
        assert r.status_code == 413, r.text
        assert "zu groß" in r.json()["detail"].lower()
    finally:
        _cleanup_env("CLIPFORGE_MAX_UPLOAD_MB")
        shutil.rmtree(tmp, ignore_errors=True)


def test_batch_too_many_files_400():
    tmp = tempfile.mkdtemp(prefix="lim_")
    try:
        client, _ = _make_client(os.path.join(tmp, "jobs"), CLIPFORGE_MAX_BATCH_FILES=2)
        files = [
            ("files", (f"v{i}.mp4", io.BytesIO(b"\x00" * 100), "video/mp4"))
            for i in range(3)
        ]
        r = client.post("/api/jobs/batch", files=files)
        assert r.status_code == 400
        assert "Zu viele Dateien" in r.json()["detail"]
    finally:
        _cleanup_env("CLIPFORGE_MAX_BATCH_FILES")
        shutil.rmtree(tmp, ignore_errors=True)


def test_batch_one_too_large_one_ok():
    """Große Datei rejected, gültige accepted — Batch bricht nicht ab."""
    tmp = tempfile.mkdtemp(prefix="lim_")
    try:
        client, _ = _make_client(os.path.join(tmp, "jobs"),
                                 CLIPFORGE_MAX_UPLOAD_MB=1, CLIPFORGE_MAX_BATCH_FILES=10)
        small = io.BytesIO(b"\x00" * 1024)                     # 1 KB ok
        big = io.BytesIO(b"\x00" * (2 * 1024 * 1024))          # 2 MB zu groß
        files = [
            ("files", ("ok.mp4", small, "video/mp4")),
            ("files", ("big.mp4", big, "video/mp4")),
        ]
        d = client.post("/api/jobs/batch", files=files).json()
        assert d["accepted_count"] == 1
        assert d["rejected_count"] == 1
        by = {x["filename"]: x for x in d["results"]}
        assert by["ok.mp4"]["accepted"] is True
        assert by["big.mp4"]["accepted"] is False
        assert "zu groß" in by["big.mp4"]["error"].lower()
    finally:
        _cleanup_env("CLIPFORGE_MAX_UPLOAD_MB", "CLIPFORGE_MAX_BATCH_FILES")
        shutil.rmtree(tmp, ignore_errors=True)


def test_cancel_completed_409_and_missing_404_over_http():
    tmp = tempfile.mkdtemp(prefix="lim_")
    try:
        client, app_module = _make_client(os.path.join(tmp, "jobs"))
        # nicht existierend → 404
        assert client.post("/api/jobs/nope/cancel").status_code == 404
        # completed → 409
        from jobs import STATUS_COMPLETED
        job = app_module.registry.create(filename="c.mp4", top_n=1)
        job.status = STATUS_COMPLETED
        assert client.post(f"/api/jobs/{job.id}/cancel").status_code == 409
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def test_storage_counts_canceled():
    tmp = tempfile.mkdtemp(prefix="lim_")
    try:
        client, app_module = _make_client(os.path.join(tmp, "jobs"))
        job = app_module.registry.create(filename="q.mp4", top_n=1)
        app_module.registry.request_cancel(job.id)  # queued → canceled
        d = client.get("/api/storage").json()
        assert d["by_status"]["canceled"] == 1
        # canceled ist eigene Cleanup-Gruppe, NICHT in failed/interrupted/incomplete
        cc = d["cleanup_candidates"]
        assert job.id in cc["canceled"]
        assert job.id not in cc["failed"]
        assert job.id not in cc["interrupted"]
        assert job.id not in cc["incomplete"]
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
