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
import types
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
from clipforge.config import Settings
from clipforge.platforms import YouTubeAdapter

_FFMPEG = shutil.which("ffmpeg") is not None


def _yt_settings(enabled: bool = False, creds_path: str | None = None) -> Settings:
    return Settings(
        enable_youtube_upload=enabled, youtube_client_secrets_file=creds_path
    )


def _valid_yt_draft(mp4_path: str) -> dict:
    """Ein validierter YouTube-Draft-Dict (mit gespeicherten Checks)."""
    return {
        "publishing_id": "abcdef012345",
        "job_id": "job1",
        "platform": "youtube_shorts",
        "source_type": "auto_clip",
        "source_clip_index": 1,
        "manual_export_id": None,
        "mp4_path": mp4_path,
        "title": "Warum die meisten scheitern",
        "caption": "Ein Fehler.",
        "description": "Der eine Fehler, den fast alle machen.",
        "hashtags": ["#shorts", "#lernen"],
        "pinned_comment": "",
        "scheduled_at": None,
        "status": "ready",
        "external_post_id": None,
        "validation": {
            "checks": {
                "mp4_exists": True, "format_9_16": True, "title_present": True,
                "caption_present": True, "hashtags_present": True,
                "no_virality_claim": True,
            }
        },
    }


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


# ---------------------- YouTube Adapter (Modul, ohne echten Upload) -------

_SECRET_MARKERS = ("token", "access_token", "refresh_token", "client_secret",
                   "authorization", "bearer", "password", "api_key")


def _assert_no_secrets(obj):
    blob = json.dumps(obj, ensure_ascii=False).lower()
    for m in _SECRET_MARKERS:
        assert m not in blob, f"möglicher Secret-Marker in Antwort: {m}"


def test_youtube_dry_run_works_and_has_no_secrets():
    if not _FFMPEG:
        print("  (übersprungen: ffmpeg fehlt)")
        return
    mp4 = tempfile.NamedTemporaryFile(suffix=".mp4", delete=False)
    mp4.write(b"x"); mp4.close()
    try:
        adapter = YouTubeAdapter(_yt_settings(enabled=False))
        res = adapter.dry_run(_valid_yt_draft(mp4.name))
        assert res["platform"] == "youtube_shorts"
        assert res["enabled"] is False
        assert res["upload_implemented"] is False
        # video_file ist nur der Basename, nicht der volle Pfad
        assert res["video_file"] == os.path.basename(mp4.name)
        assert "/" not in (res["video_file"] or "")
        assert "metadata" in res["request_preview"]
        assert "video_body" in res["request_preview"]
        _assert_no_secrets(res)
    finally:
        os.unlink(mp4.name)


def test_youtube_dry_run_does_not_mutate_draft():
    """Dry-Run darf keinen Upload/Status-Effekt haben."""
    if not _FFMPEG:
        print("  (übersprungen: ffmpeg fehlt)")
        return
    jd = _make_job_dir()
    try:
        d = create_draft(jd, "job1", platform="youtube_shorts",
                         source_type="auto_clip", source_clip_index=1)
        before = load_draft(jd, d["publishing_id"])
        YouTubeAdapter(_yt_settings(enabled=True)).dry_run(before)
        after = load_draft(jd, d["publishing_id"])
        assert after["status"] == before["status"]
        assert after["external_post_id"] is None
    finally:
        shutil.rmtree(jd)


def test_youtube_dry_run_missing_mp4_is_blocked():
    adapter = YouTubeAdapter(_yt_settings(enabled=True))
    draft = _valid_yt_draft("/does/not/exist.mp4")
    res = adapter.dry_run(draft)
    assert res["checks"]["mp4_exists"] is False
    assert any("MP4" in r for r in res["blocked_reasons"])
    assert res["would_upload"] is False


def test_youtube_dry_run_flags_virality_guarantee():
    if not _FFMPEG:
        print("  (übersprungen: ffmpeg fehlt)")
        return
    mp4 = tempfile.NamedTemporaryFile(suffix=".mp4", delete=False)
    mp4.write(b"x"); mp4.close()
    try:
        draft = _valid_yt_draft(mp4.name)
        draft["title"] = "Dieser Clip geht GARANTIERT VIRAL"
        # gespeicherte Checks entsprechend: no_virality_claim False
        draft["validation"]["checks"]["no_virality_claim"] = False
        res = YouTubeAdapter(_yt_settings(enabled=True)).dry_run(draft)
        assert res["checks"]["no_viral_guarantee"] is False
        assert any("virality" in r.lower() for r in res["blocked_reasons"])
    finally:
        os.unlink(mp4.name)


def test_youtube_publish_blocked_when_feature_disabled():
    adapter = YouTubeAdapter(_yt_settings(enabled=False))
    res = adapter.publish(_valid_yt_draft("/x.mp4"), confirm="UPLOAD_PRIVATE",
                          privacy_status="private")
    assert res["outcome"] == "disabled"
    assert "disabled" in res["message"].lower()


def test_youtube_publish_blocked_without_credentials():
    adapter = YouTubeAdapter(_yt_settings(enabled=True, creds_path=None))
    res = adapter.publish(_valid_yt_draft("/x.mp4"), confirm="UPLOAD_PRIVATE",
                          privacy_status="private")
    assert res["outcome"] == "not_ready"
    assert "credentials_not_configured" in res["blocked_reasons"]


def test_youtube_publish_public_requires_public_phrase():
    sec = tempfile.NamedTemporaryFile(suffix=".json", delete=False)
    sec.write(b"{}"); sec.close()
    mp4 = tempfile.NamedTemporaryFile(suffix=".mp4", delete=False)
    mp4.write(b"x"); mp4.close()
    try:
        adapter = YouTubeAdapter(_yt_settings(enabled=True, creds_path=sec.name))
        draft = _valid_yt_draft(mp4.name)
        # public mit privater Phrase → blockiert
        res = adapter.publish(draft, confirm="UPLOAD_PRIVATE", privacy_status="public")
        assert res["outcome"] == "needs_confirmation"
        assert "confirmation_required" in res["blocked_reasons"]
        # public mit korrekter Phrase → not_implemented (kein Fake-Erfolg)
        res2 = adapter.publish(draft, confirm="UPLOAD_PUBLIC", privacy_status="public")
        assert res2["outcome"] == "not_implemented"
    finally:
        os.unlink(sec.name); os.unlink(mp4.name)


def test_youtube_publish_never_fakes_success():
    sec = tempfile.NamedTemporaryFile(suffix=".json", delete=False)
    sec.write(b"{}"); sec.close()
    mp4 = tempfile.NamedTemporaryFile(suffix=".mp4", delete=False)
    mp4.write(b"x"); mp4.close()
    try:
        adapter = YouTubeAdapter(_yt_settings(enabled=True, creds_path=sec.name))
        res = adapter.publish(_valid_yt_draft(mp4.name), confirm="UPLOAD_PRIVATE",
                              privacy_status="private")
        assert res["outcome"] == "not_implemented"
        assert res["external_post_id"] is None
        assert res["draft_status_changed"] is False
    finally:
        os.unlink(sec.name); os.unlink(mp4.name)


def test_youtube_publish_idempotency_guard():
    sec = tempfile.NamedTemporaryFile(suffix=".json", delete=False)
    sec.write(b"{}"); sec.close()
    mp4 = tempfile.NamedTemporaryFile(suffix=".mp4", delete=False)
    mp4.write(b"x"); mp4.close()
    try:
        adapter = YouTubeAdapter(_yt_settings(enabled=True, creds_path=sec.name))
        draft = _valid_yt_draft(mp4.name)
        draft["external_post_id"] = "already-there"
        res = adapter.publish(draft, confirm="UPLOAD_PRIVATE", privacy_status="private")
        assert res["outcome"] == "not_ready"
        assert "already_uploaded" in res["blocked_reasons"]
    finally:
        os.unlink(sec.name); os.unlink(mp4.name)


# ---------------------- YouTube API-Endpoints (TestClient) ----------------

def test_api_youtube_dry_run_and_publish_disabled():
    if not _FFMPEG:
        print("  (übersprungen: ffmpeg fehlt)")
        return
    # Sicherstellen, dass das Feature-Flag AUS ist (Default).
    os.environ.pop("CLIPFORGE_ENABLE_YOUTUBE_UPLOAD", None)
    os.environ.pop("CLIPFORGE_YOUTUBE_CLIENT_SECRETS", None)
    client, tmp = _make_client()
    try:
        r = client.post("/api/jobs/pubjob0001/publishing", json={
            "platform": "youtube_shorts", "source_type": "auto_clip",
            "source_clip_index": 1})
        pid = r.json()["publishing_id"]

        # Dry-Run funktioniert, keine Secrets, kein Upload
        r = client.post(f"/api/jobs/pubjob0001/publishing/{pid}/youtube/dry-run")
        assert r.status_code == 200, r.text
        body = r.json()
        assert body["platform"] == "youtube_shorts"
        assert body["enabled"] is False
        _assert_no_secrets(body)

        # Publish bei Feature-Flag aus → 403
        r = client.post(f"/api/jobs/pubjob0001/publishing/{pid}/youtube/publish",
                        json={"confirm": "UPLOAD_PRIVATE", "privacy_status": "private"})
        assert r.status_code == 403, r.text
        assert "disabled" in r.json()["detail"].lower()

        # Draft-Status ist unverändert (kein published)
        r = client.get(f"/api/jobs/pubjob0001/publishing/{pid}")
        assert r.json()["status"] in ("draft", "ready")
        assert r.json()["external_post_id"] is None
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
        os.environ.pop("CLIPFORGE_JOBS_DIR", None)
        sys.modules.pop("app", None)


def test_api_youtube_publish_enabled_but_blocked_paths():
    if not _FFMPEG:
        print("  (übersprungen: ffmpeg fehlt)")
        return
    sec = tempfile.NamedTemporaryFile(suffix=".json", delete=False)
    sec.write(b"{}"); sec.close()
    os.environ["CLIPFORGE_ENABLE_YOUTUBE_UPLOAD"] = "true"
    client, tmp = _make_client()
    try:
        r = client.post("/api/jobs/pubjob0001/publishing", json={
            "platform": "youtube_shorts", "source_type": "auto_clip",
            "source_clip_index": 1})
        pid = r.json()["publishing_id"]
        client.post(f"/api/jobs/pubjob0001/publishing/{pid}/validate")

        # Ohne Credentials → 409
        os.environ.pop("CLIPFORGE_YOUTUBE_CLIENT_SECRETS", None)
        r = client.post(f"/api/jobs/pubjob0001/publishing/{pid}/youtube/publish",
                        json={"confirm": "UPLOAD_PRIVATE", "privacy_status": "private"})
        assert r.status_code == 409, r.text

        # Mit Credentials, aber public ohne UPLOAD_PUBLIC → 400
        os.environ["CLIPFORGE_YOUTUBE_CLIENT_SECRETS"] = sec.name
        r = client.post(f"/api/jobs/pubjob0001/publishing/{pid}/youtube/publish",
                        json={"confirm": "UPLOAD_PRIVATE", "privacy_status": "public"})
        assert r.status_code == 400, r.text

        # Mit Credentials + korrekter Phrase → 200 not_implemented (kein Fake)
        r = client.post(f"/api/jobs/pubjob0001/publishing/{pid}/youtube/publish",
                        json={"confirm": "UPLOAD_PRIVATE", "privacy_status": "private"})
        assert r.status_code == 200, r.text
        assert r.json()["status"] == "not_implemented"

        # Status weiterhin nicht published
        r = client.get(f"/api/jobs/pubjob0001/publishing/{pid}")
        assert r.json()["status"] in ("draft", "ready")
        assert r.json()["external_post_id"] is None
    finally:
        os.environ.pop("CLIPFORGE_ENABLE_YOUTUBE_UPLOAD", None)
        os.environ.pop("CLIPFORGE_YOUTUBE_CLIENT_SECRETS", None)
        os.unlink(sec.name)
        shutil.rmtree(tmp, ignore_errors=True)
        os.environ.pop("CLIPFORGE_JOBS_DIR", None)
        sys.modules.pop("app", None)


def test_api_youtube_rejects_non_youtube_draft_and_traversal():
    if not _FFMPEG:
        print("  (übersprungen: ffmpeg fehlt)")
        return
    client, tmp = _make_client()
    try:
        r = client.post("/api/jobs/pubjob0001/publishing", json={
            "platform": "tiktok", "source_type": "auto_clip",
            "source_clip_index": 1})
        pid = r.json()["publishing_id"]
        # TikTok-Draft am YouTube-Endpoint → 400
        r = client.post(f"/api/jobs/pubjob0001/publishing/{pid}/youtube/dry-run")
        assert r.status_code == 400, r.text
        # Path-Traversal bleibt geblockt
        r = client.post(
            "/api/jobs/pubjob0001/publishing/..%2F..%2Fx/youtube/dry-run")
        assert r.status_code in (400, 404), r.status_code
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
        os.environ.pop("CLIPFORGE_JOBS_DIR", None)
        sys.modules.pop("app", None)


# ---------------------- YouTube OAuth Readiness (Phase 2) -----------------

from clipforge.platforms.youtube_auth import YouTubeTokenStore

# Marker, die auf ein geleaktes Secret HINWEISEN (Werte, keine Var-Namen).
_VALUE_MARKERS = ("access_token", "refresh_token", "bearer ")


def _assert_no_secret_values(obj, *forbidden: str):
    blob = json.dumps(obj, ensure_ascii=False).lower()
    for m in _VALUE_MARKERS:
        assert m not in blob, f"möglicher Secret-Wert in Antwort: {m}"
    for f in forbidden:
        assert f.lower() not in blob, f"geleakter Wert in Antwort: {f}"


def _install_fake_keyring(token: dict | None = None, corrupt: bool = False,
                          service: str = "clipforge-youtube",
                          account: str = "default"):
    """Injiziert ein Fake-`keyring`-Modul (kein echtes OS-Keychain, kein Netz)."""
    fake = types.ModuleType("keyring")
    store: dict = {}
    if corrupt:
        store[(service, account)] = "not-json{"
    elif token is not None:
        store[(service, account)] = json.dumps(token)

    class _Backend:  # nicht das 'fail'-Backend → gilt als verfügbar
        pass

    fake.get_keyring = lambda: _Backend()
    fake.get_password = lambda s, a: store.get((s, a))
    fake.set_password = lambda s, a, v: store.__setitem__((s, a), v)

    def _del(s, a):
        if (s, a) in store:
            del store[(s, a)]
        else:
            raise RuntimeError("no password")

    fake.delete_password = _del
    sys.modules["keyring"] = fake
    return store


def test_token_store_unavailable_without_keyring():
    sys.modules.pop("keyring", None)
    ts = YouTubeTokenStore("svc", "acct")
    assert ts.is_available() is False
    assert ts.has_token() is False
    assert ts.get_status() == "blocked"
    assert ts.delete_token()["deleted"] is False


def test_token_store_states_with_fake_keyring():
    _install_fake_keyring(service="svc", account="acct")
    try:
        ts = YouTubeTokenStore("svc", "acct")
        assert ts.is_available() is True
        assert ts.get_status() == "not_authenticated"
        ts.save_token({"refresh_token": "SENTINEL_TOKEN_VALUE"})
        assert ts.get_status() == "authenticated"
        assert ts.has_token() is True
        assert ts.delete_token() == {"deleted": True}
        # idempotent
        assert ts.delete_token()["deleted"] is False
    finally:
        sys.modules.pop("keyring", None)


def test_token_store_corrupt_is_invalid():
    _install_fake_keyring(corrupt=True, service="svc", account="acct")
    try:
        ts = YouTubeTokenStore("svc", "acct")
        assert ts.get_status() == "invalid_token"
    finally:
        sys.modules.pop("keyring", None)


def test_readiness_default_blocked_and_safe():
    sys.modules.pop("keyring", None)
    adapter = YouTubeAdapter(_yt_settings(enabled=False))
    r = adapter.overall_readiness()
    assert r["enabled"] is False
    assert r["credentials_configured"] is False
    assert r["token_store_available"] is False
    assert r["token_status"] == "blocked"
    assert r["can_attempt_upload"] is False
    assert r["upload_status"] == "not_implemented"
    assert r["required_scope"].endswith("youtube.upload")
    assert "credentials_not_configured" in r["blocked_reasons"]
    assert "token_store_unavailable" in r["blocked_reasons"]
    _assert_no_secret_values(r)


def test_readiness_reports_basename_only_not_full_path():
    d = tempfile.mkdtemp(prefix="yt_creds_")
    secret_path = os.path.join(d, "my_client_secrets.json")
    with open(secret_path, "w") as fh:
        fh.write('{"installed": {"client_id": "SENTINEL_CONTENT_XYZ"}}')
    try:
        adapter = YouTubeAdapter(
            Settings(enable_youtube_upload=True,
                     youtube_client_secrets_file=secret_path))
        r = adapter.overall_readiness()
        assert r["credentials_configured"] is True
        assert r["credentials_file_exists"] is True
        assert r["credentials_file_basename"] == "my_client_secrets.json"
        # weder voller Pfad noch Dateiinhalt dürfen auftauchen
        blob = json.dumps(r)
        assert d not in blob
        _assert_no_secret_values(r, "SENTINEL_CONTENT_XYZ")
    finally:
        shutil.rmtree(d, ignore_errors=True)


def test_readiness_token_missing_then_present_no_leak():
    # kein Token
    store = _install_fake_keyring()
    try:
        adapter = YouTubeAdapter(_yt_settings(enabled=True))
        r = adapter.overall_readiness()
        assert r["token_store_available"] is True
        assert r["token_present"] is False
        assert r["token_status"] == "not_authenticated"
    finally:
        sys.modules.pop("keyring", None)
    # Token vorhanden (Wert darf nie leaken)
    _install_fake_keyring(token={"refresh_token": "SENTINEL_TOKEN_VALUE"})
    try:
        adapter = YouTubeAdapter(_yt_settings(enabled=True))
        r = adapter.overall_readiness()
        assert r["token_present"] is True
        assert r["token_status"] == "authenticated"
        _assert_no_secret_values(r, "SENTINEL_TOKEN_VALUE")
    finally:
        sys.modules.pop("keyring", None)


def test_adapter_logout_idempotent():
    _install_fake_keyring(token={"refresh_token": "x"})
    try:
        adapter = YouTubeAdapter(_yt_settings(enabled=True))
        assert adapter.logout() == {"deleted": True}
        assert adapter.logout()["deleted"] is False
    finally:
        sys.modules.pop("keyring", None)


def test_start_auth_never_runs_real_flow():
    sys.modules.pop("keyring", None)
    # OAuth aus → oauth_disabled
    a_off = YouTubeAdapter(Settings(enable_youtube_oauth=False))
    r = a_off.start_auth()
    assert r["started"] is False
    assert r["status"] == "oauth_disabled"
    # OAuth an → not_implemented_auth_flow (kein Browser, kein Token)
    a_on = YouTubeAdapter(Settings(enable_youtube_oauth=True))
    r = a_on.start_auth()
    assert r["started"] is False
    assert r["status"] == "not_implemented_auth_flow"
    _assert_no_secret_values(r)


# ---------------------- YouTube Readiness API (TestClient) ----------------

def test_api_youtube_readiness_logout_and_guards():
    if not _FFMPEG:
        print("  (übersprungen: ffmpeg fehlt)")
        return
    sys.modules.pop("keyring", None)
    client, tmp = _make_client()
    try:
        r = client.post("/api/jobs/pubjob0001/publishing", json={
            "platform": "youtube_shorts", "source_type": "auto_clip",
            "source_clip_index": 1})
        pid = r.json()["publishing_id"]

        # Readiness: sicher, kein Secret, upload_status not_implemented
        r = client.get(f"/api/jobs/pubjob0001/publishing/{pid}/youtube/readiness")
        assert r.status_code == 200, r.text
        body = r.json()
        assert body["upload_status"] == "not_implemented"
        assert body["can_attempt_upload"] is False
        assert body["token_store_available"] is False  # kein keyring
        _assert_no_secret_values(body)

        # Logout: idempotent, kein Fehler, kein Secret
        r = client.post(f"/api/jobs/pubjob0001/publishing/{pid}/youtube/auth/logout")
        assert r.status_code == 200, r.text
        _assert_no_secret_values(r.json())

        # auth/start: OAuth aus (Default) → oauth_disabled, kein Upload
        r = client.post(f"/api/jobs/pubjob0001/publishing/{pid}/youtube/auth/start")
        assert r.status_code == 200, r.text
        assert r.json()["status"] in ("oauth_disabled", "not_implemented_auth_flow")
        assert r.json()["started"] is False

        # Publish weiterhin sicher blockiert, Status unverändert
        r = client.post(f"/api/jobs/pubjob0001/publishing/{pid}/youtube/publish",
                        json={"confirm": "UPLOAD_PRIVATE", "privacy_status": "private"})
        assert r.status_code == 403
        r = client.get(f"/api/jobs/pubjob0001/publishing/{pid}")
        assert r.json()["status"] in ("draft", "ready")
        assert r.json()["external_post_id"] is None
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
        os.environ.pop("CLIPFORGE_JOBS_DIR", None)
        sys.modules.pop("app", None)


def test_api_youtube_readiness_rejects_non_youtube_and_traversal():
    if not _FFMPEG:
        print("  (übersprungen: ffmpeg fehlt)")
        return
    client, tmp = _make_client()
    try:
        r = client.post("/api/jobs/pubjob0001/publishing", json={
            "platform": "tiktok", "source_type": "auto_clip",
            "source_clip_index": 1})
        pid = r.json()["publishing_id"]
        r = client.get(f"/api/jobs/pubjob0001/publishing/{pid}/youtube/readiness")
        assert r.status_code == 400, r.text
        r = client.post(
            "/api/jobs/pubjob0001/publishing/..%2F..%2Fx/youtube/auth/logout")
        assert r.status_code in (400, 404), r.status_code
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
