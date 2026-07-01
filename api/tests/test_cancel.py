"""Tests für Job-Cancel (kooperativ) und Cancel-bezogene Zustände (Prompt 17)."""

from __future__ import annotations

import os
import shutil
import sys
import tempfile
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from clipforge.pipeline import PipelineCanceled, run_pipeline
from clipforge.config import Settings
from jobs import (
    STATUS_CANCELED,
    STATUS_COMPLETED,
    STATUS_PROCESSING,
    STATUS_QUEUED,
    JobNotCancelable,
    JobNotFound,
    JobRegistry,
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


# ---------------- Pipeline-Checkpoints (ohne Registry) --------------------

def test_pipeline_cancels_before_transcription():
    if not _ready():
        print("  (übersprungen: ffmpeg/Fixtures fehlen)")
        return
    out = tempfile.mkdtemp(prefix="cancel_")
    try:
        # should_cancel liefert sofort True → Abbruch am ersten Checkpoint,
        # bevor überhaupt transkribiert/gerendert wird.
        try:
            run_pipeline(
                _SAMPLE, out,
                settings=Settings(anthropic_api_key=None, use_llm=False),
                transcript_path=_TRANSCRIPT, top_n=2, render=True,
                should_cancel=lambda: True,
            )
            assert False, "sollte PipelineCanceled werfen"
        except PipelineCanceled:
            pass
        # Kein clips.json geschrieben (Abbruch vor dem Schreiben).
        assert not os.path.exists(os.path.join(out, "clips.json"))
    finally:
        shutil.rmtree(out, ignore_errors=True)


def test_pipeline_cancels_after_transcription():
    if not _ready():
        print("  (übersprungen: ffmpeg/Fixtures fehlen)")
        return
    out = tempfile.mkdtemp(prefix="cancel_")
    try:
        calls = {"n": 0}

        def cancel_on_second_checkpoint() -> bool:
            calls["n"] += 1
            return calls["n"] >= 2  # erster Checkpoint False, danach True

        try:
            run_pipeline(
                _SAMPLE, out,
                settings=Settings(anthropic_api_key=None, use_llm=False),
                transcript_path=_TRANSCRIPT, top_n=2, render=True,
                should_cancel=cancel_on_second_checkpoint,
            )
            assert False, "sollte PipelineCanceled werfen"
        except PipelineCanceled:
            pass
        # transcript.json wurde geschrieben (Transkription lief), clips.json nicht.
        assert os.path.exists(os.path.join(out, "transcript.json"))
        assert not os.path.exists(os.path.join(out, "clips.json"))
    finally:
        shutil.rmtree(out, ignore_errors=True)


def test_pipeline_without_cancel_completes():
    if not _ready():
        print("  (übersprungen: ffmpeg/Fixtures fehlen)")
        return
    out = tempfile.mkdtemp(prefix="cancel_")
    try:
        pr = run_pipeline(
            _SAMPLE, out,
            settings=Settings(anthropic_api_key=None, use_llm=False),
            transcript_path=_TRANSCRIPT, top_n=2, render=True,
            should_cancel=lambda: False,
        )
        assert os.path.exists(os.path.join(out, "clips.json"))
        assert len(pr.clips) >= 1
    finally:
        shutil.rmtree(out, ignore_errors=True)


# ---------------- Registry request_cancel ---------------------------------

def test_request_cancel_queued_becomes_canceled_immediately():
    tmp = tempfile.mkdtemp(prefix="cancel_")
    try:
        reg = JobRegistry(os.path.join(tmp, "jobs"))
        job = reg.create(filename="q.mp4", top_n=1)  # status = queued
        assert job.status == STATUS_QUEUED
        res = reg.request_cancel(job.id)
        assert res["canceled"] is True
        assert res["status"] == STATUS_CANCELED
        assert job.status == STATUS_CANCELED
        assert job.cancel_requested is True
        assert job.canceled_at
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def test_request_cancel_processing_sets_flag():
    tmp = tempfile.mkdtemp(prefix="cancel_")
    try:
        reg = JobRegistry(os.path.join(tmp, "jobs"))
        job = reg.create(filename="p.mp4", top_n=1)
        job.status = STATUS_PROCESSING
        res = reg.request_cancel(job.id)
        assert res["canceled"] is True
        assert res["status"] == STATUS_PROCESSING  # noch nicht am Checkpoint
        assert job.cancel_requested is True
        assert reg.is_cancel_requested(job.id) is True
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def test_request_cancel_completed_raises_409():
    tmp = tempfile.mkdtemp(prefix="cancel_")
    try:
        reg = JobRegistry(os.path.join(tmp, "jobs"))
        job = reg.create(filename="c.mp4", top_n=1)
        job.status = STATUS_COMPLETED
        try:
            reg.request_cancel(job.id)
            assert False, "sollte JobNotCancelable werfen"
        except JobNotCancelable:
            pass
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def test_request_cancel_nonexistent_raises_404():
    tmp = tempfile.mkdtemp(prefix="cancel_")
    try:
        reg = JobRegistry(os.path.join(tmp, "jobs"))
        try:
            reg.request_cancel("deadbeef0000")
            assert False, "sollte JobNotFound werfen"
        except JobNotFound:
            pass
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def test_canceled_job_is_restored_and_deletable():
    tmp = tempfile.mkdtemp(prefix="cancel_")
    try:
        base = os.path.join(tmp, "jobs")
        reg = JobRegistry(base)
        job = reg.create(filename="q.mp4", top_n=1)
        reg.request_cancel(job.id)
        assert job.status == STATUS_CANCELED

        # Restore in frischer Registry → bleibt canceled
        reg2 = JobRegistry(base)
        reg2.restore()
        r = reg2.get(job.id)
        assert r is not None
        assert r.status == STATUS_CANCELED
        assert r.restored is True

        # canceled Job ist löschbar (nicht processing)
        res = reg2.delete(job.id)
        assert res["deleted"] is True
        assert not os.path.isdir(job.job_dir)
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def test_run_cancels_queued_before_processing():
    """End-to-End über den Worker: cancel_requested vor _run → canceled ohne Arbeit."""
    if not _ready():
        print("  (übersprungen: ffmpeg/Fixtures fehlen)")
        return
    tmp = tempfile.mkdtemp(prefix="cancel_")
    try:
        base = os.path.join(tmp, "jobs")
        reg = JobRegistry(base, max_workers=1)
        job = reg.create(filename="sample.mp4", top_n=2)
        shutil.copy(_SAMPLE, os.path.join(job.job_dir, "input.mp4"))
        shutil.copy(_TRANSCRIPT, os.path.join(job.job_dir, "source_transcript.json"))
        job.input_path = os.path.join(job.job_dir, "input.mp4")
        job.transcript_path = os.path.join(job.job_dir, "source_transcript.json")
        # Cancel setzen BEVOR gestartet wird → Worker bricht am Eintritt ab.
        reg.request_cancel(job.id)
        reg.start(job)
        for _ in range(40):
            if job.status in (STATUS_CANCELED, STATUS_COMPLETED):
                break
            time.sleep(0.25)
        assert job.status == STATUS_CANCELED
        assert not os.path.exists(os.path.join(job.job_dir, "clips.json"))
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
