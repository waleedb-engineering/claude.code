"""Tests für all-exports.zip (Struktur, Counts, Fehlerfälle).

Testet die App-Endpunkt-Logik über FastAPIs TestClient mit echten ffmpeg-
Renders (Auto-Clip via Pipeline + manueller Re-Render). Ohne ffmpeg/Fixtures
werden die Render-Tests sauber übersprungen.
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


def _make_client(tmp_jobs: str):
    """Baut eine frische App-Instanz mit isoliertem JOBS_DIR."""
    os.environ["CLIPFORGE_JOBS_DIR"] = tmp_jobs
    # app-Modul frisch importieren, damit es das ENV liest
    for mod in ("app",):
        sys.modules.pop(mod, None)
    from fastapi.testclient import TestClient
    import app as app_module

    return TestClient(app_module.app), app_module


def _run_job(client) -> str:
    with open(_SAMPLE, "rb") as vf, open(_TRANSCRIPT, "rb") as tf:
        resp = client.post(
            "/api/jobs",
            files={
                "file": ("sample.mp4", vf, "video/mp4"),
                "transcript": ("transcript.json", tf, "application/json"),
            },
            data={"top_n": "2"},
        )
    assert resp.status_code == 200, resp.text
    job_id = resp.json()["job_id"]
    # Job läuft synchron im ThreadPool — kurz warten bis completed
    import time
    st = "processing"
    for _ in range(240):
        st = client.get(f"/api/jobs/{job_id}").json()["status"]
        if st in ("completed", "failed"):
            break
        time.sleep(0.5)
    assert st == "completed", f"Job-Status={st}"
    return job_id


def test_all_exports_auto_only_and_structure():
    if not _ready():
        print("  (übersprungen: ffmpeg/Fixtures fehlen)")
        return
    tmp = tempfile.mkdtemp(prefix="allzip_")
    try:
        client, _ = _make_client(os.path.join(tmp, "jobs"))
        job_id = _run_job(client)

        r = client.get(f"/api/jobs/{job_id}/all-exports.zip")
        assert r.status_code == 200, r.text
        zf = zipfile.ZipFile(io.BytesIO(r.content))
        names = zf.namelist()
        # Ordnerstruktur
        assert any(n.startswith("auto_clips/") and n.endswith(".mp4") for n in names)
        assert "data/clips.json" in names
        assert "data/transcript.json" in names
        assert "data/metadata.json" in names
        assert "data/manual_exports.json" in names
        # metadata counts
        meta = json.loads(zf.read("data/metadata.json"))
        assert meta["auto_clip_count"] == 2
        assert meta["manual_export_count"] == 0
        assert meta["total_mp4_count"] == 2
        assert "Garantie" in meta["disclaimer"]
        # manual_exports.json leer aber valide
        mexp = json.loads(zf.read("data/manual_exports.json"))
        assert mexp["job_id"] == job_id
        assert mexp["exports"] == []
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def test_all_exports_with_manual():
    if not _ready():
        print("  (übersprungen: ffmpeg/Fixtures fehlen)")
        return
    tmp = tempfile.mkdtemp(prefix="allzip_")
    try:
        client, _ = _make_client(os.path.join(tmp, "jobs"))
        job_id = _run_job(client)
        # Manueller Re-Render
        rr = client.post(
            f"/api/jobs/{job_id}/clips/1/rerender",
            json={
                "start_time": 1.0, "end_time": 12.0, "title": "Manuell",
                "remove_silence": False, "reframe_mode": "center",
            },
        )
        assert rr.status_code == 200, rr.text

        r = client.get(f"/api/jobs/{job_id}/all-exports.zip")
        assert r.status_code == 200
        zf = zipfile.ZipFile(io.BytesIO(r.content))
        names = zf.namelist()
        assert any(n.startswith("manual_exports/") and n.endswith(".mp4") for n in names)
        meta = json.loads(zf.read("data/metadata.json"))
        assert meta["auto_clip_count"] == 2
        assert meta["manual_export_count"] == 1
        assert meta["total_mp4_count"] == 3
        mexp = json.loads(zf.read("data/manual_exports.json"))
        assert len(mexp["exports"]) == 1
        e = mexp["exports"][0]
        for key in ("source_clip_index", "start_time", "end_time",
                    "final_duration", "title", "caption_style",
                    "remove_silence", "reframe_mode", "output_file"):
            assert key in e, key
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def test_all_exports_no_exports_404():
    """Job ohne Clips/Exporte → 404 mit sauberer Meldung."""
    tmp = tempfile.mkdtemp(prefix="allzip_")
    try:
        client, app_module = _make_client(os.path.join(tmp, "jobs"))
        # leeren Job direkt in der Registry anlegen (kein Render)
        job = app_module.registry.create(filename="leer.mp4", top_n=1)
        r = client.get(f"/api/jobs/{job.id}/all-exports.zip")
        assert r.status_code == 404
        assert "Keine Exporte" in r.json()["detail"]
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def test_all_exports_job_not_found_404():
    tmp = tempfile.mkdtemp(prefix="allzip_")
    try:
        client, _ = _make_client(os.path.join(tmp, "jobs"))
        r = client.get("/api/jobs/doesnotexist/all-exports.zip")
        assert r.status_code == 404
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def test_broken_manual_metadata_does_not_crash():
    """Kaputte Metadatei → übersprungen + Warnung, kein Crash."""
    if not _ready():
        print("  (übersprungen: ffmpeg/Fixtures fehlen)")
        return
    tmp = tempfile.mkdtemp(prefix="allzip_")
    try:
        client, app_module = _make_client(os.path.join(tmp, "jobs"))
        job_id = _run_job(client)
        job = app_module.registry.get(job_id)
        mdir = os.path.join(job.job_dir, "manual_exports")
        os.makedirs(mdir, exist_ok=True)
        # kaputte JSON ohne passende MP4
        with open(os.path.join(mdir, "clip_9_broken.json"), "w") as fh:
            fh.write("{ this is not valid json ]")
        # gültige Metadata aber fehlende MP4
        with open(os.path.join(mdir, "clip_9_nomp4.json"), "w") as fh:
            json.dump({"export_id": "clip_9_nomp4", "output_file": "clip_9_nomp4.mp4"}, fh)

        r = client.get(f"/api/jobs/{job_id}/all-exports.zip")
        assert r.status_code == 200, r.text
        zf = zipfile.ZipFile(io.BytesIO(r.content))
        meta = json.loads(zf.read("data/metadata.json"))
        assert len(meta["warnings"]) >= 2
        assert meta["manual_export_count"] == 0  # keine gültigen manuellen
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def test_exports_zip_still_auto_only():
    """Regression: exports.zip enthält weiter NUR Auto-Clips (kein auto_clips/-Prefix)."""
    if not _ready():
        print("  (übersprungen: ffmpeg/Fixtures fehlen)")
        return
    tmp = tempfile.mkdtemp(prefix="allzip_")
    try:
        client, _ = _make_client(os.path.join(tmp, "jobs"))
        job_id = _run_job(client)
        client.post(
            f"/api/jobs/{job_id}/clips/1/rerender",
            json={"start_time": 1.0, "end_time": 12.0,
                  "remove_silence": False, "reframe_mode": "center"},
        )
        r = client.get(f"/api/jobs/{job_id}/exports.zip")
        assert r.status_code == 200
        names = zipfile.ZipFile(io.BytesIO(r.content)).namelist()
        # flache Struktur, keine manual_exports, kein auto_clips/-Prefix
        assert not any(n.startswith("auto_clips/") for n in names)
        assert not any("manual" in n for n in names)
        assert "clips.json" in names and "metadata.json" in names
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
