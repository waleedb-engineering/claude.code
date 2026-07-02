"""Tests für den Publishing Planner (lokale Drafts — KEIN Upload/OAuth).

Modul-Tests laufen direkt gegen clipforge.publishing; API-Tests über den
FastAPI-TestClient mit einem fabrizierten Job-Ordner (Registry-Restore).
ffmpeg wird nur für die Mini-Fixture-MP4s gebraucht.
"""

from __future__ import annotations

import io
import json
import os
import shutil
import subprocess
import sys
import tempfile
import zipfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from clipforge.publishing import (
    PLATFORMS,
    PublishingError,
    create_draft,
    delete_draft,
    list_drafts,
    load_draft,
    pack_contents,
    update_draft,
    validate_draft,
)

_FFMPEG = shutil.which("ffmpeg") is not None


def _make_mp4(path: str, w: int = 108, h: int = 192) -> None:
    subprocess.run(
        ["ffmpeg", "-y", "-f", "lavfi", "-i", f"color=c=black:s={w}x{h}:d=0.4",
         "-pix_fmt", "yuv420p", path],
        capture_output=True, check=True,
    )


def _make_job_dir(with_mp4: bool = True) -> str:
    """Fabriziert einen Job-Ordner mit clips.json (+ 9:16-MP4 + Manual-Export)."""
    job_dir = tempfile.mkdtemp(prefix="pub_test_")
    mp4 = os.path.join(job_dir, "clip_01_score80.mp4")
    if with_mp4 and _FFMPEG:
        _make_mp4(mp4)
    clips = {
        "scorer": "rule_based",
        "analyzer_version": "v2",
        "disclaimer": "Score ist eine Einschätzung, keine Garantie.",
        "clips": [{
            "start": 0.0, "end": 20.0, "text": "Warum scheitern die meisten?",
            "score": 80.0, "output_path": mp4,
            "content_package": {
                "primary_hook": "Warum scheitern die meisten?",
                "youtube_shorts": {"title": "Warum die meisten scheitern",
                                   "description": "Der eine Fehler.",
                                   "hashtags": ["#shorts"]},
                "tiktok": {"caption": "Warum scheitern die meisten? 👀",
                           "hashtags": ["#fyp"], "pinned_comment": "Und du?"},
                "instagram_reels": {"caption": "Der eine Fehler.",
                                    "hashtags": ["#reels"], "pinned_comment": ""},
            },
        }],
    }
    with open(os.path.join(job_dir, "clips.json"), "w", encoding="utf-8") as fh:
        json.dump(clips, fh)
    # Manual-Export dazu
    med = os.path.join(job_dir, "manual_exports")
    os.makedirs(med, exist_ok=True)
    if with_mp4 and _FFMPEG:
        _make_mp4(os.path.join(med, "clip_1_20990101-000000.mp4"))
    with open(os.path.join(med, "clip_1_20990101-000000.json"), "w", encoding="utf-8") as fh:
        json.dump({"export_id": "clip_1_20990101-000000", "source_clip_index": 1,
                   "output_file": "clip_1_20990101-000000.mp4",
                   "created_at": "2099-01-01T00:00:00+00:00"}, fh)
    return job_dir


# ---------------------- Modul: CRUD ---------------------------------------

def test_create_draft_auto_clip_prefills_from_content_package():
    jd = _make_job_dir()
    d = create_draft(jd, "job1", platform="tiktok", source_type="auto_clip",
                     source_clip_index=1)
    assert d["status"] == "draft"
    assert d["caption"] == "Warum scheitern die meisten? 👀"
    assert d["hashtags"] == ["#fyp"]
    assert d["pinned_comment"] == "Und du?"
    assert d["source_type"] == "auto_clip"
    shutil.rmtree(jd)


def test_create_draft_youtube_prefills_title_description():
    jd = _make_job_dir()
    d = create_draft(jd, "job1", platform="youtube_shorts",
                     source_type="auto_clip", source_clip_index=1)
    assert d["title"] == "Warum die meisten scheitern"
    assert d["description"] == "Der eine Fehler."
    shutil.rmtree(jd)


def test_create_draft_manual_export():
    jd = _make_job_dir()
    d = create_draft(jd, "job1", platform="instagram_reels",
                     source_type="manual_export",
                     manual_export_id="clip_1_20990101-000000")
    assert d["manual_export_id"] == "clip_1_20990101-000000"
    # Texte kommen über source_clip_index=1 aus dem Content-Paket
    assert d["caption"] == "Der eine Fehler."
    shutil.rmtree(jd)


def test_invalid_platform_raises():
    jd = _make_job_dir()
    try:
        create_draft(jd, "job1", platform="myspace", source_type="auto_clip",
                     source_clip_index=1)
        assert False, "sollte werfen"
    except PublishingError:
        pass
    finally:
        shutil.rmtree(jd)


def test_list_and_load_and_delete():
    jd = _make_job_dir()
    a = create_draft(jd, "job1", platform="tiktok", source_type="auto_clip",
                     source_clip_index=1)
    b = create_draft(jd, "job1", platform="youtube_shorts",
                     source_type="auto_clip", source_clip_index=1)
    ids = {d["publishing_id"] for d in list_drafts(jd)}
    assert ids == {a["publishing_id"], b["publishing_id"]}
    assert load_draft(jd, a["publishing_id"])["platform"] == "tiktok"
    assert delete_draft(jd, a["publishing_id"]) is True
    assert delete_draft(jd, a["publishing_id"]) is False  # schon weg
    assert len(list_drafts(jd)) == 1
    shutil.rmtree(jd)


def test_update_draft_edits_texts_and_blocks_reserved_status():
    jd = _make_job_dir()
    d = create_draft(jd, "job1", platform="tiktok", source_type="auto_clip",
                     source_clip_index=1)
    u = update_draft(jd, d["publishing_id"],
                     {"caption": "Neu!", "hashtags": ["#neu"], "status": "canceled"})
    assert u["caption"] == "Neu!" and u["hashtags"] == ["#neu"]
    assert u["status"] == "canceled"
    for reserved in ("publishing", "published", "failed"):
        try:
            update_draft(jd, d["publishing_id"], {"status": reserved})
            assert False, f"Status {reserved} darf nicht manuell setzbar sein"
        except PublishingError:
            pass
    shutil.rmtree(jd)


def test_path_traversal_blocked():
    jd = _make_job_dir()
    for bad in ("../evil", "..%2Fevil", "a/b", "..", "x" * 12, "ABCDEF123456"):
        try:
            load_draft(jd, bad)
            assert False, f"unsichere ID akzeptiert: {bad!r}"
        except PublishingError:
            pass
    shutil.rmtree(jd)


# ---------------------- Modul: Validierung + Pack -------------------------

def test_validate_ok_sets_ready():
    if not _FFMPEG:
        print("  (übersprungen: ffmpeg fehlt)")
        return
    jd = _make_job_dir()
    d = create_draft(jd, "job1", platform="tiktok", source_type="auto_clip",
                     source_clip_index=1)
    v = validate_draft(jd, d["publishing_id"])
    assert v["validation"]["passed"] is True, v["validation"]
    assert v["validation"]["checks"]["mp4_exists"] is True
    assert v["validation"]["checks"]["format_9_16"] is True
    assert v["status"] == "ready"
    shutil.rmtree(jd)


def test_validate_missing_mp4_fails():
    jd = _make_job_dir(with_mp4=False)
    d = create_draft(jd, "job1", platform="tiktok", source_type="auto_clip",
                     source_clip_index=1)
    v = validate_draft(jd, d["publishing_id"])
    assert v["validation"]["passed"] is False
    assert v["validation"]["checks"]["mp4_exists"] is False
    assert v["status"] == "draft"
    shutil.rmtree(jd)


def test_validate_wrong_aspect_fails():
    if not _FFMPEG:
        print("  (übersprungen: ffmpeg fehlt)")
        return
    jd = _make_job_dir(with_mp4=False)
    _make_mp4(os.path.join(jd, "clip_01_score80.mp4"), w=192, h=108)  # 16:9
    d = create_draft(jd, "job1", platform="tiktok", source_type="auto_clip",
                     source_clip_index=1)
    v = validate_draft(jd, d["publishing_id"])
    assert v["validation"]["checks"]["format_9_16"] is False
    assert v["validation"]["passed"] is False
    shutil.rmtree(jd)


def test_validate_blocks_virality_claim():
    if not _FFMPEG:
        print("  (übersprungen: ffmpeg fehlt)")
        return
    jd = _make_job_dir()
    d = create_draft(jd, "job1", platform="tiktok", source_type="auto_clip",
                     source_clip_index=1)
    update_draft(jd, d["publishing_id"], {"caption": "Dieser Clip geht GARANTIERT viral!"})
    v = validate_draft(jd, d["publishing_id"])
    assert v["validation"]["checks"]["no_virality_claim"] is False
    assert v["validation"]["passed"] is False
    shutil.rmtree(jd)


def test_pack_contents_structure():
    jd = _make_job_dir()
    d = create_draft(jd, "job1", platform="tiktok", source_type="auto_clip",
                     source_clip_index=1)
    mp4, texts, meta = pack_contents(d)
    names = [n for n, _ in texts]
    assert names == ["caption.txt", "description.txt", "platform_notes.txt"]
    caption_txt = dict(texts)["caption.txt"]
    assert "Warum scheitern die meisten? 👀" in caption_txt
    assert "#fyp" in caption_txt
    assert meta["platform"] == "tiktok"
    assert "Kein automatischer Upload" in meta["disclaimer"]
    shutil.rmtree(jd)


# ---------------------- API (TestClient, fabrizierter Job) ----------------

def _make_client():
    tmp = tempfile.mkdtemp(prefix="pub_api_")
    jobs_dir = os.path.join(tmp, "jobs")
    os.makedirs(jobs_dir)
    src = _make_job_dir()
    job_dir = os.path.join(jobs_dir, "pubjob0001")
    shutil.move(src, job_dir)
    # output_path in clips.json auf den neuen Ort umschreiben
    cp = os.path.join(job_dir, "clips.json")
    data = json.load(open(cp, encoding="utf-8"))
    data["clips"][0]["output_path"] = os.path.join(job_dir, "clip_01_score80.mp4")
    json.dump(data, open(cp, "w", encoding="utf-8"))

    os.environ["CLIPFORGE_JOBS_DIR"] = jobs_dir
    sys.modules.pop("app", None)
    from fastapi.testclient import TestClient
    import app as app_module

    return TestClient(app_module.app), tmp


def test_api_crud_validate_and_pack():
    if not _FFMPEG:
        print("  (übersprungen: ffmpeg fehlt)")
        return
    client, tmp = _make_client()
    try:
        # Create (auto_clip)
        r = client.post("/api/jobs/pubjob0001/publishing", json={
            "platform": "youtube_shorts", "source_type": "auto_clip",
            "source_clip_index": 1})
        assert r.status_code == 200, r.text
        pid = r.json()["publishing_id"]
        assert r.json()["title"] == "Warum die meisten scheitern"

        # Create (manual_export)
        r2 = client.post("/api/jobs/pubjob0001/publishing", json={
            "platform": "tiktok", "source_type": "manual_export",
            "manual_export_id": "clip_1_20990101-000000"})
        assert r2.status_code == 200, r2.text

        # List
        r = client.get("/api/jobs/pubjob0001/publishing")
        assert r.status_code == 200 and len(r.json()["drafts"]) == 2

        # Patch
        r = client.patch(f"/api/jobs/pubjob0001/publishing/{pid}",
                         json={"title": "Neuer Titel", "scheduled_at": "2099-01-01T10:00:00Z"})
        assert r.status_code == 200 and r.json()["title"] == "Neuer Titel"

        # Validate
        r = client.post(f"/api/jobs/pubjob0001/publishing/{pid}/validate")
        assert r.status_code == 200, r.text
        assert r.json()["validation"]["passed"] is True
        assert r.json()["status"] == "ready"

        # Pack
        r = client.get(f"/api/jobs/pubjob0001/publishing/{pid}/pack.zip")
        assert r.status_code == 200, r.text
        names = zipfile.ZipFile(io.BytesIO(r.content)).namelist()
        assert "clip_01_score80.mp4" in names
        for want in ("metadata.json", "caption.txt", "description.txt",
                     "platform_notes.txt"):
            assert want in names, names

        # Delete
        r = client.delete(f"/api/jobs/pubjob0001/publishing/{pid}")
        assert r.status_code == 200 and r.json()["deleted"] is True
        r = client.get(f"/api/jobs/pubjob0001/publishing/{pid}")
        assert r.status_code == 404
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
        os.environ.pop("CLIPFORGE_JOBS_DIR", None)
        sys.modules.pop("app", None)


def test_api_invalid_platform_and_traversal():
    if not _FFMPEG:
        print("  (übersprungen: ffmpeg fehlt)")
        return
    client, tmp = _make_client()
    try:
        r = client.post("/api/jobs/pubjob0001/publishing", json={
            "platform": "myspace", "source_type": "auto_clip",
            "source_clip_index": 1})
        assert r.status_code == 400, r.text

        r = client.get("/api/jobs/pubjob0001/publishing/..%2F..%2Fetc")
        assert r.status_code in (400, 404), r.status_code

        r = client.post("/api/jobs/pubjob0001/publishing", json={
            "platform": "tiktok", "source_type": "auto_clip",
            "source_clip_index": 99})
        assert r.status_code == 400, r.text
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
        os.environ.pop("CLIPFORGE_JOBS_DIR", None)
        sys.modules.pop("app", None)


# ---------------------- API: globale Übersicht + Duplizieren --------------

def _make_multi_client(n_jobs: int = 2):
    """Baut eine App-Instanz mit `n_jobs` fabrizierten Job-Ordnern."""
    tmp = tempfile.mkdtemp(prefix="pub_multi_")
    jobs_dir = os.path.join(tmp, "jobs")
    os.makedirs(jobs_dir)
    job_ids = []
    for i in range(n_jobs):
        src = _make_job_dir()
        job_id = f"pubjob{i:04d}"
        job_dir = os.path.join(jobs_dir, job_id)
        shutil.move(src, job_dir)
        cp = os.path.join(job_dir, "clips.json")
        data = json.load(open(cp, encoding="utf-8"))
        data["clips"][0]["output_path"] = os.path.join(job_dir, "clip_01_score80.mp4")
        json.dump(data, open(cp, "w", encoding="utf-8"))
        job_ids.append(job_id)

    os.environ["CLIPFORGE_JOBS_DIR"] = jobs_dir
    sys.modules.pop("app", None)
    from fastapi.testclient import TestClient
    import app as app_module

    return TestClient(app_module.app), tmp, job_ids


def test_global_listing_spans_multiple_jobs():
    if not _FFMPEG:
        print("  (übersprungen: ffmpeg fehlt)")
        return
    client, tmp, job_ids = _make_multi_client(2)
    try:
        for jid in job_ids:
            client.post(f"/api/jobs/{jid}/publishing", json={
                "platform": "tiktok", "source_type": "auto_clip",
                "source_clip_index": 1})
        r = client.get("/api/publishing")
        assert r.status_code == 200, r.text
        data = r.json()
        assert data["total_drafts"] == 2
        assert {d["job_id"] for d in data["drafts"]} == set(job_ids)
        assert data["by_platform"].get("tiktok") == 2
        for d in data["drafts"]:
            assert d["pack_url"].endswith("/pack.zip")
            assert d["job_url"] == f"/jobs/{d['job_id']}"
            assert d["planner_url"] == f"/jobs/{d['job_id']}/publishing"
            assert "job_filename" in d
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
        os.environ.pop("CLIPFORGE_JOBS_DIR", None)
        sys.modules.pop("app", None)


def test_global_listing_filters_status_platform_q_scheduled():
    if not _FFMPEG:
        print("  (übersprungen: ffmpeg fehlt)")
        return
    client, tmp, job_ids = _make_multi_client(1)
    jid = job_ids[0]
    try:
        r1 = client.post(f"/api/jobs/{jid}/publishing", json={
            "platform": "tiktok", "source_type": "auto_clip",
            "source_clip_index": 1})
        pid1 = r1.json()["publishing_id"]
        client.post(f"/api/jobs/{jid}/publishing", json={
            "platform": "youtube_shorts", "source_type": "auto_clip",
            "source_clip_index": 1})
        client.post(f"/api/jobs/{jid}/publishing/{pid1}/validate")
        client.patch(f"/api/jobs/{jid}/publishing/{pid1}",
                     json={"scheduled_at": "2099-05-01T10:00:00Z"})

        # status filter
        r = client.get("/api/publishing", params={"status": "ready"})
        assert all(d["status"] == "ready" for d in r.json()["drafts"])
        assert any(d["publishing_id"] == pid1 for d in r.json()["drafts"])

        # platform filter
        r = client.get("/api/publishing", params={"platform": "youtube_shorts"})
        assert all(d["platform"] == "youtube_shorts" for d in r.json()["drafts"])

        # search
        r = client.get("/api/publishing", params={"q": "warum"})
        assert len(r.json()["drafts"]) >= 1
        r = client.get("/api/publishing", params={"q": "xyz-not-present"})
        assert len(r.json()["drafts"]) == 0

        # scheduled_only
        r = client.get("/api/publishing", params={"scheduled_only": "true"})
        drafts = r.json()["drafts"]
        assert all(d.get("scheduled_at") for d in drafts)
        assert any(d["publishing_id"] == pid1 for d in drafts)
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
        os.environ.pop("CLIPFORGE_JOBS_DIR", None)
        sys.modules.pop("app", None)


def test_global_listing_survives_broken_draft_file():
    if not _FFMPEG:
        print("  (übersprungen: ffmpeg fehlt)")
        return
    client, tmp, job_ids = _make_multi_client(1)
    jid = job_ids[0]
    try:
        client.post(f"/api/jobs/{jid}/publishing", json={
            "platform": "tiktok", "source_type": "auto_clip",
            "source_clip_index": 1})
        # kaputte Draft-Datei direkt ins publishing/-Verzeichnis legen
        pdir = os.path.join(tmp, "jobs", jid, "publishing")
        with open(os.path.join(pdir, "deadbeef0000.json"), "w") as fh:
            fh.write("{not valid json::")
        r = client.get("/api/publishing")
        assert r.status_code == 200, r.text
        # kaputte Datei wird von list_drafts() selbst schon übersprungen
        assert r.json()["total_drafts"] == 1
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
        os.environ.pop("CLIPFORGE_JOBS_DIR", None)
        sys.modules.pop("app", None)


def test_duplicate_creates_new_draft_with_platform_switch():
    if not _FFMPEG:
        print("  (übersprungen: ffmpeg fehlt)")
        return
    client, tmp, job_ids = _make_multi_client(1)
    jid = job_ids[0]
    try:
        r = client.post(f"/api/jobs/{jid}/publishing", json={
            "platform": "tiktok", "source_type": "auto_clip",
            "source_clip_index": 1})
        original = r.json()
        pid = original["publishing_id"]

        r = client.post(f"/api/jobs/{jid}/publishing/{pid}/duplicate",
                        json={"platform": "youtube_shorts", "copy_schedule": False})
        assert r.status_code == 200, r.text
        dup = r.json()
        assert dup["publishing_id"] != pid
        assert dup["platform"] == "youtube_shorts"
        assert dup["duplicated_from"] == pid
        assert dup["status"] == "draft" or dup["status"] == "ready"
        # Content-Paket für youtube_shorts war vorhanden -> Titel übernommen
        assert dup["title"] == "Warum die meisten scheitern"
        assert "warning" not in dup or dup.get("warning") is None

        # Original unverändert
        r = client.get(f"/api/jobs/{jid}/publishing/{pid}")
        assert r.json()["platform"] == "tiktok"

        # beide Drafts jetzt vorhanden
        r = client.get(f"/api/jobs/{jid}/publishing")
        assert len(r.json()["drafts"]) == 2
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
        os.environ.pop("CLIPFORGE_JOBS_DIR", None)
        sys.modules.pop("app", None)


def test_duplicate_copy_schedule_true_false():
    if not _FFMPEG:
        print("  (übersprungen: ffmpeg fehlt)")
        return
    client, tmp, job_ids = _make_multi_client(1)
    jid = job_ids[0]
    try:
        r = client.post(f"/api/jobs/{jid}/publishing", json={
            "platform": "tiktok", "source_type": "auto_clip",
            "source_clip_index": 1})
        pid = r.json()["publishing_id"]
        client.patch(f"/api/jobs/{jid}/publishing/{pid}",
                     json={"scheduled_at": "2099-06-01T12:00:00Z"})

        r = client.post(f"/api/jobs/{jid}/publishing/{pid}/duplicate",
                        json={"copy_schedule": False})
        assert r.json()["scheduled_at"] is None

        r = client.post(f"/api/jobs/{jid}/publishing/{pid}/duplicate",
                        json={"copy_schedule": True})
        assert r.json()["scheduled_at"] == "2099-06-01T12:00:00Z"
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
        os.environ.pop("CLIPFORGE_JOBS_DIR", None)
        sys.modules.pop("app", None)


def test_duplicate_invalid_platform_and_missing_draft():
    if not _FFMPEG:
        print("  (übersprungen: ffmpeg fehlt)")
        return
    client, tmp, job_ids = _make_multi_client(1)
    jid = job_ids[0]
    try:
        r = client.post(f"/api/jobs/{jid}/publishing", json={
            "platform": "tiktok", "source_type": "auto_clip",
            "source_clip_index": 1})
        pid = r.json()["publishing_id"]

        r = client.post(f"/api/jobs/{jid}/publishing/{pid}/duplicate",
                        json={"platform": "myspace"})
        assert r.status_code == 400, r.text

        r = client.post(f"/api/jobs/{jid}/publishing/deadbeef0000/duplicate",
                        json={"platform": "tiktok"})
        assert r.status_code == 404, r.status_code
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
        os.environ.pop("CLIPFORGE_JOBS_DIR", None)
        sys.modules.pop("app", None)


def test_validation_summary_has_blocking_warnings_checklist_hints():
    if not _FFMPEG:
        print("  (übersprungen: ffmpeg fehlt)")
        return
    client, tmp, job_ids = _make_multi_client(1)
    jid = job_ids[0]
    try:
        r = client.post(f"/api/jobs/{jid}/publishing", json={
            "platform": "tiktok", "source_type": "auto_clip",
            "source_clip_index": 1})
        pid = r.json()["publishing_id"]
        client.patch(f"/api/jobs/{jid}/publishing/{pid}", json={
            "title": "x" * 150,  # -> title_too_long hint
            "scheduled_at": "2000-01-01T00:00:00Z",  # -> scheduled_in_past
        })
        r = client.post(f"/api/jobs/{jid}/publishing/{pid}/validate")
        summary = r.json()["validation"]["summary"]
        assert set(summary.keys()) >= {
            "is_valid", "blocking_issues_count", "warnings_count",
            "checklist", "quality_hints",
        }
        for key in ("mp4_exists", "format_9_16", "title_present",
                    "caption_present", "hashtags_present", "platform_selected",
                    "no_viral_guarantee", "safe_status"):
            assert key in summary["checklist"], key
        assert "title_too_long" in summary["quality_hints"]
        assert "scheduled_in_past" in summary["quality_hints"]
        assert summary["warnings_count"] >= 2

        # globale Liste liefert dieselbe Struktur ohne erneute Validierung nötig
        r = client.get("/api/publishing")
        row = next(d for d in r.json()["drafts"] if d["publishing_id"] == pid)
        assert "title_too_long" in row["validation_summary"]["quality_hints"]
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
        os.environ.pop("CLIPFORGE_JOBS_DIR", None)
        sys.modules.pop("app", None)


def _run_all():
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for fn in fns:
        fn()
        print(f"  ✓ {fn.__name__}")
    print(f"\n{len(fns)} Tests bestanden.")


if __name__ == "__main__":
    _run_all()
