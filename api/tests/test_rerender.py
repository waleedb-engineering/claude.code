"""Tests für das manuelle Re-Rendering (Web-Clip-Editor).

Rendert echt mit ffmpeg (nutzt das mitgelieferte Test-Video/-Transkript).
Wird ffmpeg oder das Sample-Video nicht gefunden, überspringen die
Render-Tests sauber; die Validierungstests laufen immer.
"""

from __future__ import annotations

import os
import shutil
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from clipforge.config import Settings
from clipforge.rerender import (
    MAX_MANUAL_SECONDS,
    MIN_MANUAL_SECONDS,
    RerenderError,
    list_manual_exports,
    manual_export_path,
    rerender_clip,
    validate_times,
)

_HERE = os.path.dirname(os.path.abspath(__file__))
_API_DIR = os.path.dirname(_HERE)
_SAMPLE = os.path.join(_API_DIR, "testdata", "sample.mp4")
_TRANSCRIPT = os.path.join(_API_DIR, "testdata", "transcript.json")


def _ffmpeg_available() -> bool:
    return shutil.which("ffmpeg") is not None


def _have_fixtures() -> bool:
    return os.path.exists(_SAMPLE) and os.path.exists(_TRANSCRIPT)


def _make_job_dir() -> str:
    """Baut einen temporären Job-Ordner mit input.mp4 + transcript.json."""
    job_dir = tempfile.mkdtemp(prefix="rerender_test_")
    shutil.copy(_SAMPLE, os.path.join(job_dir, "input.mp4"))
    shutil.copy(_TRANSCRIPT, os.path.join(job_dir, "transcript.json"))
    return job_dir


# --- Validierung (immer, ohne ffmpeg) ------------------------------------

def test_validate_end_before_start_raises():
    try:
        validate_times(10.0, 5.0)
        assert False, "sollte werfen"
    except RerenderError:
        pass


def test_validate_end_equals_start_raises():
    try:
        validate_times(5.0, 5.0)
        assert False, "sollte werfen"
    except RerenderError:
        pass


def test_validate_too_short_raises():
    try:
        validate_times(0.0, MIN_MANUAL_SECONDS - 1.0)
        assert False, "sollte werfen"
    except RerenderError:
        pass


def test_validate_too_long_raises():
    try:
        validate_times(0.0, MAX_MANUAL_SECONDS + 5.0)
        assert False, "sollte werfen"
    except RerenderError:
        pass


def test_validate_ok_returns_clamped():
    start, end = validate_times(2.0, 20.0)
    assert start == 2.0 and end == 20.0


def test_manual_export_path_rejects_traversal():
    d = tempfile.mkdtemp(prefix="rerender_sec_")
    try:
        assert manual_export_path(d, "../secret") is None
        assert manual_export_path(d, "a/b") is None
        assert manual_export_path(d, "nonexistent") is None
    finally:
        shutil.rmtree(d, ignore_errors=True)


# --- Echtes Re-Rendering (nur mit ffmpeg + Fixtures) ---------------------

def test_rerender_produces_manual_export():
    if not (_ffmpeg_available() and _have_fixtures()):
        print("  (übersprungen: ffmpeg/Fixtures fehlen)")
        return
    job_dir = _make_job_dir()
    try:
        settings = Settings(anthropic_api_key=None, use_llm=False)
        meta = rerender_clip(
            job_dir, 1,
            start_time=1.0, end_time=12.0,
            title="Mein Schnitt",
            caption_style="clean",
            remove_silence=False,
            reframe_mode="center",
            settings=settings,
        )
        assert meta["export_id"].startswith("clip_1_")
        assert meta["title"] == "Mein Schnitt"
        assert meta["start_time"] == 1.0
        assert meta["end_time"] == 12.0
        out = os.path.join(job_dir, "manual_exports", meta["output_file"])
        assert os.path.exists(out), "MP4 sollte existieren"
        # Auto-Clips im Root dürfen nicht angefasst worden sein.
        assert not os.path.exists(os.path.join(job_dir, meta["output_file"]))
        # Metadaten-JSON persistiert
        assert os.path.exists(os.path.join(job_dir, "manual_exports", meta["export_id"] + ".json"))
    finally:
        shutil.rmtree(job_dir, ignore_errors=True)


def test_rerender_with_silence_and_smart_reframe():
    if not (_ffmpeg_available() and _have_fixtures()):
        print("  (übersprungen: ffmpeg/Fixtures fehlen)")
        return
    job_dir = _make_job_dir()
    try:
        settings = Settings(anthropic_api_key=None, use_llm=False)
        meta = rerender_clip(
            job_dir, 2,
            start_time=5.0, end_time=25.0,
            remove_silence=True,
            reframe_mode="smart",
            settings=settings,
        )
        assert meta["remove_silence"] is True
        assert meta["reframe_mode"] == "smart"
        assert meta["silence_info"] is not None
        assert meta["reframe_info"] is not None
        out = os.path.join(job_dir, "manual_exports", meta["output_file"])
        assert os.path.exists(out)
    finally:
        shutil.rmtree(job_dir, ignore_errors=True)


def test_list_manual_exports_after_two_renders():
    if not (_ffmpeg_available() and _have_fixtures()):
        print("  (übersprungen: ffmpeg/Fixtures fehlen)")
        return
    job_dir = _make_job_dir()
    try:
        settings = Settings(anthropic_api_key=None, use_llm=False)
        rerender_clip(job_dir, 1, start_time=0.0, end_time=10.0,
                      remove_silence=False, reframe_mode="center", settings=settings)
        rerender_clip(job_dir, 1, start_time=2.0, end_time=14.0,
                      remove_silence=False, reframe_mode="center", settings=settings)
        exports = list_manual_exports(job_dir)
        assert len(exports) == 2
        assert all(e["available"] for e in exports)
        # neueste zuerst
        assert exports[0]["created_at"] >= exports[1]["created_at"]
    finally:
        shutil.rmtree(job_dir, ignore_errors=True)


def _run_all():
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for fn in fns:
        fn()
        print(f"  ✓ {fn.__name__}")
    print(f"\n{len(fns)} Tests bestanden.")


if __name__ == "__main__":
    _run_all()
