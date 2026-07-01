"""Tests für die persistente Job-Wiederherstellung nach Server-Neustart.

Baut synthetische Job-Ordner (ohne ffmpeg) und prüft, dass eine frische
JobRegistry sie korrekt und crashfrei wiederherstellt.
"""

from __future__ import annotations

import json
import os
import shutil
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import jobs as jobs_mod
from jobs import (
    STATUS_COMPLETED,
    STATUS_INCOMPLETE,
    STATUS_INTERRUPTED,
    STATUS_FAILED,
    Job,
    JobRegistry,
)


def _mkjob(base: str, job_id: str) -> str:
    d = os.path.join(base, job_id)
    os.makedirs(d, exist_ok=True)
    return d


def _write(path: str, obj) -> None:
    with open(path, "w", encoding="utf-8") as fh:
        if isinstance(obj, str):
            fh.write(obj)
        else:
            json.dump(obj, fh)


def _touch(path: str) -> None:
    with open(path, "wb") as fh:
        fh.write(b"\x00\x00")


def _job_json(job_id: str, d: str, status: str, with_result: bool = True) -> dict:
    data = {
        "id": job_id, "status": status, "filename": "sample.mp4",
        "job_dir": d, "top_n": 2,
        "created_at": "2026-07-01T00:00:00+00:00",
        "updated_at": "2026-07-01T00:01:00+00:00",
        "input_path": os.path.join(d, "input.mp4"),
        "transcript_path": None,
        "progress": ["…"], "error": None,
    }
    if with_result:
        data["result"] = {
            "clip_count": 1, "rendered_count": 1, "language": "de",
            "duration": 60.0,
            "clips": [{
                "index": 1, "score": 80.0, "start": 0.0, "end": 20.0,
                "duration": 20.0, "scorer": "heuristic",
                "output_file": "clip_01_score80.mp4", "downloadable": True,
            }],
        }
    return data


def test_restore_completed_from_job_json():
    tmp = tempfile.mkdtemp(prefix="restore_")
    try:
        base = os.path.join(tmp, "jobs")
        d = _mkjob(base, "job_ok")
        _write(os.path.join(d, "job.json"), _job_json("job_ok", d, STATUS_COMPLETED))
        _write(os.path.join(d, "clips.json"), {"clips": [{"score": 80}]})
        _write(os.path.join(d, "transcript.json"), {"language": "de", "duration": 60.0})
        _touch(os.path.join(d, "input.mp4"))
        _touch(os.path.join(d, "clip_01_score80.mp4"))

        reg = JobRegistry(base)
        warns = reg.restore()
        job = reg.get("job_ok")
        assert job is not None
        assert job.status == STATUS_COMPLETED
        assert job.restored is True
        assert job.restored_at is not None
        assert (job.result or {}).get("clips"), "result.clips muss vorhanden sein"
        assert warns == [] or all("job_ok" not in w for w in warns)
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def test_restore_processing_becomes_interrupted():
    tmp = tempfile.mkdtemp(prefix="restore_")
    try:
        base = os.path.join(tmp, "jobs")
        d = _mkjob(base, "job_proc")
        _write(os.path.join(d, "job.json"),
               _job_json("job_proc", d, "processing", with_result=False))
        _touch(os.path.join(d, "input.mp4"))  # keine clips.json / kein mp4

        reg = JobRegistry(base)
        reg.restore()
        job = reg.get("job_proc")
        assert job.status == STATUS_INTERRUPTED
        assert job.interrupted is True
        assert job.restore_warning and "unterbrochen" in job.restore_warning.lower()
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def test_restore_processing_with_full_output_becomes_completed():
    """War 'processing', aber Render war fertig → completed (nicht interrupted)."""
    tmp = tempfile.mkdtemp(prefix="restore_")
    try:
        base = os.path.join(tmp, "jobs")
        d = _mkjob(base, "job_proc2")
        _write(os.path.join(d, "job.json"),
               _job_json("job_proc2", d, "processing"))
        _write(os.path.join(d, "clips.json"), {"clips": [{"score": 80}]})
        _touch(os.path.join(d, "clip_01_score80.mp4"))

        reg = JobRegistry(base)
        reg.restore()
        job = reg.get("job_proc2")
        assert job.status == STATUS_COMPLETED
        assert job.interrupted is False
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def test_restore_completed_missing_mp4_is_incomplete():
    tmp = tempfile.mkdtemp(prefix="restore_")
    try:
        base = os.path.join(tmp, "jobs")
        d = _mkjob(base, "job_inc")
        _write(os.path.join(d, "job.json"), _job_json("job_inc", d, STATUS_COMPLETED))
        _write(os.path.join(d, "clips.json"), {"clips": [{"score": 80}]})
        # kein clip_*.mp4

        reg = JobRegistry(base)
        reg.restore()
        job = reg.get("job_inc")
        assert job.status == STATUS_INCOMPLETE
        assert job.restore_warning
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def test_restore_corrupt_job_json_does_not_crash():
    tmp = tempfile.mkdtemp(prefix="restore_")
    try:
        base = os.path.join(tmp, "jobs")
        d = _mkjob(base, "job_corrupt")
        _write(os.path.join(d, "job.json"), "{ this is : not json ]")
        _write(os.path.join(d, "clips.json"),
               {"clips": [{"score": 70, "start": 0, "end": 20,
                           "duration": 20, "scorer": "heuristic"}]})
        _write(os.path.join(d, "transcript.json"), {"language": "en", "duration": 30.0})
        _touch(os.path.join(d, "input.mp4"))
        _touch(os.path.join(d, "clip_01_score70.mp4"))

        reg = JobRegistry(base)
        warns = reg.restore()  # darf nicht werfen
        job = reg.get("job_corrupt")
        assert job is not None
        assert job.status == STATUS_COMPLETED  # aus Dateien rekonstruiert
        assert (job.result or {}).get("clips")
        assert job.result["clips"][0]["output_file"] == "clip_01_score70.mp4"
        assert any("job_corrupt" in w for w in warns)
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def test_restore_reconstruct_without_job_json():
    tmp = tempfile.mkdtemp(prefix="restore_")
    try:
        base = os.path.join(tmp, "jobs")
        d = _mkjob(base, "job_nojson")
        _write(os.path.join(d, "clips.json"),
               {"clips": [
                   {"score": 81, "start": 0, "end": 29, "duration": 29, "scorer": "heuristic"},
                   {"score": 74, "start": 30, "end": 59, "duration": 29, "scorer": "heuristic"},
               ]})
        _write(os.path.join(d, "transcript.json"), {"language": "de", "duration": 60.0})
        _touch(os.path.join(d, "input.mp4"))
        _touch(os.path.join(d, "clip_01_score81.mp4"))
        _touch(os.path.join(d, "clip_02_score74.mp4"))

        reg = JobRegistry(base)
        reg.restore()
        job = reg.get("job_nojson")
        assert job is not None
        assert job.status == STATUS_COMPLETED
        assert job.restored is True
        clips = (job.result or {}).get("clips")
        assert len(clips) == 2
        assert clips[1]["output_file"] == "clip_02_score74.mp4"
        assert job.result["language"] == "de"
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def test_restore_does_not_override_in_memory_job():
    tmp = tempfile.mkdtemp(prefix="restore_")
    try:
        base = os.path.join(tmp, "jobs")
        reg = JobRegistry(base)
        live = reg.create(filename="live.mp4", top_n=1)
        # job.json existiert jetzt für live; restore darf ihn nicht ersetzen
        reg.restore()
        again = reg.get(live.id)
        assert again is live  # dasselbe Objekt, nicht ersetzt
        assert again.restored is False
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def test_restore_empty_and_missing_dir_no_crash():
    tmp = tempfile.mkdtemp(prefix="restore_")
    try:
        base = os.path.join(tmp, "jobs")
        os.makedirs(base, exist_ok=True)
        # leerer Ordner + eine lose Datei (kein Verzeichnis)
        _touch(os.path.join(base, "not_a_job.txt"))
        reg = JobRegistry(base)
        warns = reg.restore()
        assert reg.list() == []
        assert isinstance(warns, list)
        # nicht existierender Basisordner
        reg2 = JobRegistry(os.path.join(tmp, "does_not_exist_yet"))
        shutil.rmtree(os.path.join(tmp, "does_not_exist_yet"), ignore_errors=True)
        assert reg2.restore() == [] or isinstance(reg2.restore(), list)
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def test_from_dict_ignores_unknown_and_defaults_missing():
    data = {"id": "x", "status": "completed", "filename": "a.mp4",
            "job_dir": "/tmp/x", "top_n": 1,
            "created_at": "t", "updated_at": "t",
            "totally_unknown_key": 123}
    job = Job.from_dict(data)
    assert job.id == "x"
    assert job.restored is False  # Default
    assert not hasattr(job, "totally_unknown_key")


def _run_all():
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for fn in fns:
        fn()
        print(f"  ✓ {fn.__name__}")
    print(f"\n{len(fns)} Tests bestanden.")


if __name__ == "__main__":
    _run_all()
