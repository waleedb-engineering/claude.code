"""Audit-Fix-Tests (Release-Readiness-Audit).

Deterministische Tests für die im Audit gefundenen und behobenen Probleme:
  FIX-1  Draft-Delete während aktivem Upload → 409 (kein verwaistes Remote-Video)
  FIX-2  Logout während Token-Refresh → keine Token-Resurrection
  FIX-3  Korrupte Attempt-/Transition-History crasht keine Endpoints
  FIX-4  Atomare Draft-/job.json-Writes (kein korruptes JSON bei Crash im Write)
  FIX-6  Reconcile auf frischem aktivem Upload → 409 (keine Interferenz)
  plus:  ZIP-Arcname-Sicherheit, Scanner fasst terminale/ruhende Zustände nie an.

KEIN echter Google-Call, KEIN echter Upload. Läuft ohne pytest:
`python tests/test_audit_fixes.py` (braucht ffmpeg für Mini-MP4-Fixtures).
"""

from __future__ import annotations

import datetime
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

from clipforge.config import Settings
from clipforge.platforms import youtube_state as st
from clipforge.platforms.youtube_upload import YouTubeUploadService
from clipforge.platforms.youtube_recovery import RecoveryScanner
from clipforge.publishing import (
    apply_publish_state,
    create_draft,
    load_draft,
    update_draft,
    validate_draft,
)

_FFMPEG = shutil.which("ffmpeg") is not None

_TOKEN = {
    "access_token": "ACCESS_SENTINEL_zzz", "refresh_token": "REFRESH_SENTINEL_zzz",
    "token_uri": "https://oauth2.googleapis.com/token", "client_id": "cid",
    "scopes": ["https://www.googleapis.com/auth/youtube.upload"],
    "expiry": "2999-01-01T00:00:00",
}


def _install_fake_keyring(payload=_TOKEN):
    fake = types.ModuleType("keyring")
    store: dict = {}
    if payload is not None:
        store[("clipforge-youtube", "default")] = json.dumps(payload)

    class B:
        pass

    fake.get_keyring = lambda: B()
    fake.get_password = lambda s, a: store.get((s, a))
    fake.set_password = lambda s, a, v: store.__setitem__((s, a), v)
    fake.delete_password = lambda s, a: store.pop((s, a), None)
    sys.modules["keyring"] = fake
    return store


def _write_secrets() -> str:
    fh = tempfile.NamedTemporaryFile("w", suffix=".json", delete=False)
    json.dump({"installed": {"client_id": "cid", "client_secret": "SEC_SENTINEL"}}, fh)
    fh.close()
    return fh.name


def _make_job(root_jobs: str | None = None, job_id: str = "job1"):
    if root_jobs:
        jd = os.path.join(root_jobs, job_id)
        os.makedirs(jd)
    else:
        jd = tempfile.mkdtemp(prefix="audit_")
    mp4 = os.path.join(jd, "clip_01_score80.mp4")
    subprocess.run(
        ["ffmpeg", "-y", "-f", "lavfi", "-i", "color=c=black:s=108x192:d=0.4",
         "-pix_fmt", "yuv420p", mp4], capture_output=True, check=True)
    json.dump({"clips": [{"start": 0, "end": 20, "text": "x", "score": 80,
               "output_path": mp4, "content_package": {"primary_hook": "h",
               "youtube_shorts": {"title": "T", "description": "D",
                                  "hashtags": ["#s"]}}}]},
              open(os.path.join(jd, "clips.json"), "w"))
    d = create_draft(jd, job_id, platform="youtube_shorts",
                     source_type="auto_clip", source_clip_index=1)
    validate_draft(jd, d["publishing_id"])
    return jd, d["publishing_id"]


def _settings(sec):
    return Settings(enable_youtube_upload=True, enable_youtube_oauth=True,
                    youtube_client_secrets_file=sec,
                    youtube_stale_upload_seconds=1)


# ---------------------- FIX-3: korrupte Histories -------------------------

def test_corrupt_histories_do_not_crash_upload_status():
    if not _FFMPEG:
        return
    _install_fake_keyring()
    jd, pid = _make_job()
    sec = _write_secrets()
    try:
        apply_publish_state(jd, pid, {
            "state_transition_history": ["kaputt", 42, None],
            "publish_attempts": "gar-keine-liste",
        })
        svc = YouTubeUploadService(_settings(sec),
                                   credentials_loader=lambda c, p, s: None)
        us = svc.upload_status(load_draft(jd, pid))  # darf NICHT crashen
        assert us["no_secrets"] is True
        assert isinstance(us["attempt_history_summary"], list)
        assert isinstance(us["transition_history_summary"], list)
        # transition() auf korrupter History darf ebenfalls nicht crashen und
        # filtert die kaputten Einträge heraus.
        u = st.transition(load_draft(jd, pid), "preparing",
                          now="2026-01-01T00:00:00+00:00")
        assert all(isinstance(e, dict) for e in u["state_transition_history"])
    finally:
        sys.modules.pop("keyring", None); os.unlink(sec); shutil.rmtree(jd)


def test_transition_summary_marks_corrupt_entries():
    out = st.transition_history_summary(
        {"state_transition_history": ["nicht-dict", {"from": "idle", "to": "preparing"}]})
    assert out[0]["to"] == "corrupt_entry"
    assert out[1]["to"] == "preparing"


# ---------------------- FIX-2: Logout während Refresh ---------------------

def test_logout_during_refresh_does_not_resurrect_token():
    if not _FFMPEG:
        return
    store = _install_fake_keyring()
    jd, pid = _make_job()
    sec = _write_secrets()
    try:
        class Creds:
            valid = False
            refresh_token = "REFRESH_SENTINEL_zzz"
            token = "ACCESS_SENTINEL_zzz"
            expiry = None

        def refresher(c):
            store.clear()  # Logout passiert WÄHREND des Refresh-Netzwerk-Calls
            c.valid = True
            c.token = "NEW_ACCESS_zzz"

        svc = YouTubeUploadService(
            _settings(sec), credentials_loader=lambda c, p, s: Creds(),
            refresher=refresher,
            uploader=lambda c, b, m: {"id": "V", "status": {"privacyStatus": "private"}},
            sleep_fn=lambda d: None)
        svc.upload_private(jd, pid, load_draft(jd, pid), confirm="UPLOAD_PRIVATE")
        # Token darf NICHT wieder im Store auftauchen (Resurrection).
        assert ("clipforge-youtube", "default") not in store
    finally:
        sys.modules.pop("keyring", None); os.unlink(sec); shutil.rmtree(jd)


# ---------------------- FIX-4: atomare Writes -----------------------------

def test_failed_draft_write_leaves_original_intact():
    """Crasht die Serialisierung mitten im Write (tmp), bleibt die
    Original-Draft-Datei unverändert und parsebar (tmp+rename)."""
    if not _FFMPEG:
        return
    jd, pid = _make_job()
    try:
        before = load_draft(jd, pid)
        assert before is not None
        # Nicht-serialisierbares Objekt → json.dump wirft mitten im tmp-Write.
        from clipforge.publishing import _write_draft_atomic
        bad = dict(before)
        bad["boom"] = object()  # nicht JSON-serialisierbar
        try:
            _write_draft_atomic(jd, pid, bad)
            assert False, "sollte TypeError werfen"
        except TypeError:
            pass
        after = load_draft(jd, pid)
        assert after == before  # Original unangetastet & valide
    finally:
        shutil.rmtree(jd)


def test_draft_updates_leave_no_tmp_files():
    if not _FFMPEG:
        return
    jd, pid = _make_job()
    try:
        update_draft(jd, pid, {"title": "Neu"})
        validate_draft(jd, pid)
        pdir = os.path.join(jd, "publishing")
        leftovers = [f for f in os.listdir(pdir) if f.endswith(".tmp")]
        assert leftovers == [], leftovers
    finally:
        shutil.rmtree(jd)


# ---------------------- Scanner: terminale/ruhende Zustände ---------------

def test_recovery_scanner_never_touches_terminal_or_resting_states():
    """Explizit: published (terminal), failed und uncertain (ruhend) werden vom
    Scanner auch bei uraltem Timestamp NIE verändert."""
    if not _FFMPEG:
        return
    _install_fake_keyring()
    root = tempfile.mkdtemp(prefix="audit_scan_")
    jobs = os.path.join(root, "jobs")
    os.makedirs(jobs)
    try:
        cases = {"published": "j1", "failed": "j2", "uncertain": "j3"}
        pids = {}
        for state, jid in cases.items():
            jd, pid = _make_job(jobs, jid)
            up = {"upload_state": state,
                  "last_upload_activity_at": "2020-01-01T00:00:00+00:00"}
            if state == "published":
                up["external_post_id"] = "VID"
            apply_publish_state(jd, pid, up)
            pids[state] = (jd, pid)
        s = Settings(youtube_recovery_scan_enabled=True,
                     youtube_stale_upload_seconds=1)
        summ = RecoveryScanner(s).scan(jobs)
        assert summ["stale"] == 0
        for state, (jd, pid) in pids.items():
            assert load_draft(jd, pid)["upload_state"] == state, state
    finally:
        sys.modules.pop("keyring", None); shutil.rmtree(root)


# ---------------------- HTTP: FIX-1 / FIX-6 / ZIP -------------------------

def _make_client():
    tmp = tempfile.mkdtemp(prefix="audit_api_")
    jobs_dir = os.path.join(tmp, "jobs")
    os.makedirs(jobs_dir)
    jd, pid = _make_job(jobs_dir, "auditjob01")
    os.environ["CLIPFORGE_JOBS_DIR"] = jobs_dir
    sys.modules.pop("app", None)
    from fastapi.testclient import TestClient
    import app as app_module
    return TestClient(app_module.app), tmp, jd, pid


def _now_iso():
    return datetime.datetime.now(datetime.timezone.utc).isoformat()


def test_delete_draft_with_active_upload_blocked_409():
    if not _FFMPEG:
        return
    _install_fake_keyring()
    client, tmp, jd, pid = _make_client()
    try:
        apply_publish_state(jd, pid, {"upload_state": "uploading",
                                      "last_upload_activity_at": _now_iso()})
        r = client.delete(f"/api/jobs/auditjob01/publishing/{pid}")
        assert r.status_code == 409, r.text
        assert load_draft(jd, pid) is not None  # nichts gelöscht
        # Ruhender Zustand → Löschen weiterhin möglich (Regression).
        apply_publish_state(jd, pid, {"upload_state": "failed"})
        r = client.delete(f"/api/jobs/auditjob01/publishing/{pid}")
        assert r.status_code == 200, r.text
    finally:
        os.environ.pop("CLIPFORGE_JOBS_DIR", None)
        shutil.rmtree(tmp, ignore_errors=True)
        sys.modules.pop("keyring", None); sys.modules.pop("app", None)


def test_reconcile_fresh_active_upload_blocked_409():
    if not _FFMPEG:
        return
    _install_fake_keyring()
    client, tmp, jd, pid = _make_client()
    try:
        # frischer aktiver Upload (nicht stale) → Reconcile geblockt
        apply_publish_state(jd, pid, {"upload_state": "uploading",
                                      "last_upload_activity_at": _now_iso()})
        r = client.post(f"/api/jobs/auditjob01/publishing/{pid}/youtube/reconcile")
        assert r.status_code == 409, r.text
        assert load_draft(jd, pid)["upload_state"] == "uploading"  # unangetastet
    finally:
        os.environ.pop("CLIPFORGE_JOBS_DIR", None)
        shutil.rmtree(tmp, ignore_errors=True)
        sys.modules.pop("keyring", None); sys.modules.pop("app", None)


def test_zip_exports_have_safe_arcnames():
    """ZIP-Sicherheit: keine absoluten Pfade, kein '..' in Arcnames, nur
    erwartete Ordner-Präfixe in all-exports.zip."""
    if not _FFMPEG:
        return
    client, tmp, jd, pid = _make_client()
    try:
        for endpoint in ("/api/jobs/auditjob01/exports.zip",
                         "/api/jobs/auditjob01/all-exports.zip"):
            r = client.get(endpoint)
            assert r.status_code == 200, (endpoint, r.text)
            names = zipfile.ZipFile(io.BytesIO(r.content)).namelist()
            for n in names:
                assert not n.startswith("/"), n
                assert ".." not in n, n
                assert not (len(n) > 1 and n[1] == ":"), n  # kein Win-Laufwerk
        # pack.zip des Drafts ebenfalls prüfen
        r = client.get(f"/api/jobs/auditjob01/publishing/{pid}/pack.zip")
        assert r.status_code == 200, r.text
        for n in zipfile.ZipFile(io.BytesIO(r.content)).namelist():
            assert not n.startswith("/") and ".." not in n, n
    finally:
        os.environ.pop("CLIPFORGE_JOBS_DIR", None)
        shutil.rmtree(tmp, ignore_errors=True)
        sys.modules.pop("app", None)


def test_corrupt_history_upload_status_endpoint_returns_200():
    """End-to-End: korrupter Draft → upload-status bleibt 200 (kein 500)."""
    if not _FFMPEG:
        return
    _install_fake_keyring()
    client, tmp, jd, pid = _make_client()
    try:
        apply_publish_state(jd, pid, {
            "state_transition_history": ["korrupt"],
            "publish_attempts": {"auch": "korrupt"},
        })
        r = client.get(f"/api/jobs/auditjob01/publishing/{pid}/youtube/upload-status")
        assert r.status_code == 200, r.text
        assert r.json()["no_secrets"] is True
    finally:
        os.environ.pop("CLIPFORGE_JOBS_DIR", None)
        shutil.rmtree(tmp, ignore_errors=True)
        sys.modules.pop("keyring", None); sys.modules.pop("app", None)


def _run_all():
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    passed = 0
    for fn in fns:
        fn()
        print(f"  ✓ {fn.__name__}")
        passed += 1
    print(f"\n{passed} Tests bestanden.")


if __name__ == "__main__":
    _run_all()
