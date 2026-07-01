"""Tests für Batch-Upload (Prompt 16).

Deterministisch über TestClient. Der Batch-Endpoint legt pro Datei einen Job an;
die eigentliche Verarbeitung (Whisper/FFmpeg) wird hier NICHT abgewartet — das
Anlegen/Einreihen + die Fehlerisolation je Datei sind die neue Logik. Real
verarbeitete Batch-Jobs werden separat per curl gegen den Live-Server geprüft.
"""

from __future__ import annotations

import io
import os
import shutil
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

_HERE = os.path.dirname(os.path.abspath(__file__))
_API_DIR = os.path.dirname(_HERE)
_SAMPLE = os.path.join(_API_DIR, "testdata", "sample.mp4")
_TRANSCRIPT = os.path.join(_API_DIR, "testdata", "transcript.json")


def _make_client(tmp_jobs: str):
    os.environ["CLIPFORGE_JOBS_DIR"] = tmp_jobs
    sys.modules.pop("app", None)
    from fastapi.testclient import TestClient
    import app as app_module
    return TestClient(app_module.app), app_module


def _mp4_bytes() -> bytes:
    if os.path.exists(_SAMPLE):
        with open(_SAMPLE, "rb") as fh:
            return fh.read()
    return b"\x00" * 1024  # Endung entscheidet, Inhalt egal fürs Anlegen


def test_batch_two_valid_one_invalid():
    tmp = tempfile.mkdtemp(prefix="batch_")
    try:
        client, _ = _make_client(os.path.join(tmp, "jobs"))
        data = _mp4_bytes()
        files = [
            ("files", ("a.mp4", io.BytesIO(data), "video/mp4")),
            ("files", ("b.mov", io.BytesIO(data), "video/quicktime")),
            ("files", ("bad.txt", io.BytesIO(b"nope"), "text/plain")),
        ]
        r = client.post("/api/jobs/batch", files=files, data={"top_n": "2"})
        assert r.status_code == 200, r.text
        d = r.json()
        assert d["accepted_count"] == 2
        assert d["rejected_count"] == 1
        by_name = {x["filename"]: x for x in d["results"]}
        assert by_name["a.mp4"]["accepted"] is True and by_name["a.mp4"]["job_id"]
        assert by_name["b.mov"]["accepted"] is True
        assert by_name["bad.txt"]["accepted"] is False
        assert "Ungültiger Dateityp" in by_name["bad.txt"]["error"]
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def test_batch_jobs_appear_in_list_and_storage():
    tmp = tempfile.mkdtemp(prefix="batch_")
    try:
        client, _ = _make_client(os.path.join(tmp, "jobs"))
        data = _mp4_bytes()
        files = [
            ("files", ("one.mp4", io.BytesIO(data), "video/mp4")),
            ("files", ("two.mp4", io.BytesIO(data), "video/mp4")),
        ]
        d = client.post("/api/jobs/batch", files=files).json()
        job_ids = [x["job_id"] for x in d["results"] if x["accepted"]]
        assert len(job_ids) == 2

        listed = {j["id"] for j in client.get("/api/jobs").json()["jobs"]}
        for jid in job_ids:
            assert jid in listed, jid

        stor = client.get("/api/storage").json()
        assert stor["total_jobs"] >= 2
        # Batch-Jobs starten sofort (ThreadPool) → laufender Job ist geschützt
        # (409 ohne force). Mit force greift dieselbe sichere Delete-Logik.
        dd = client.request("DELETE", f"/api/jobs/{job_ids[0]}?force=true")
        assert dd.status_code == 200 and dd.json()["deleted"] is True
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def test_batch_all_invalid_no_500():
    tmp = tempfile.mkdtemp(prefix="batch_")
    try:
        client, _ = _make_client(os.path.join(tmp, "jobs"))
        files = [
            ("files", ("x.txt", io.BytesIO(b"a"), "text/plain")),
            ("files", ("y.csv", io.BytesIO(b"b"), "text/csv")),
        ]
        r = client.post("/api/jobs/batch", files=files)
        assert r.status_code == 200
        d = r.json()
        assert d["accepted_count"] == 0
        assert d["rejected_count"] == 2
        assert all(x["accepted"] is False for x in d["results"])
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def test_single_upload_still_works():
    """Regression: Einzel-Upload (mit Transkript) bleibt unverändert und completed."""
    if not (shutil.which("ffmpeg") and os.path.exists(_SAMPLE) and os.path.exists(_TRANSCRIPT)):
        print("  (übersprungen: ffmpeg/Fixtures fehlen)")
        return
    tmp = tempfile.mkdtemp(prefix="batch_")
    try:
        client, _ = _make_client(os.path.join(tmp, "jobs"))
        import time
        with open(_SAMPLE, "rb") as vf, open(_TRANSCRIPT, "rb") as tf:
            r = client.post("/api/jobs", files={
                "file": ("sample.mp4", vf, "video/mp4"),
                "transcript": ("transcript.json", tf, "application/json"),
            }, data={"top_n": "2"})
        assert r.status_code == 200, r.text
        jid = r.json()["job_id"]
        st = "processing"
        for _ in range(240):
            st = client.get(f"/api/jobs/{jid}").json()["status"]
            if st in ("completed", "failed"):
                break
            time.sleep(0.5)
        assert st == "completed", st
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
