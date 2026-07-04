"""Tests für die persistente Upload-State-Machine, Crash-Recovery,
Reconciliation und Race-Schutz (Phase 3c).

KEIN echter Google-Call, KEIN echter Upload: Sessions/Verifier werden gefaked,
keyring wird ersetzt. Getestet: State-Transitions, stale-Erkennung,
Reconciliation-Matrix (nur ID, keine Heuristik), Doppel-/Parallel-Requests
(genau EIN Upload) und die Mock-E2E-Szenarien A/B/C.

Läuft ohne pytest: `python tests/test_youtube_recovery.py` (braucht ffmpeg).
"""

from __future__ import annotations

import datetime
import json
import os
import shutil
import subprocess
import sys
import tempfile
import threading
import types

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from clipforge.config import Settings
from clipforge.platforms import youtube_state as st
from clipforge.platforms.youtube_state import InvalidTransition
from clipforge.platforms.youtube_upload import YouTubeUploadService
from clipforge.platforms.youtube_recovery import (
    RecoveryScanner,
    ReconciliationService,
)
from clipforge.publishing import (
    apply_publish_state,
    create_draft,
    load_draft,
    validate_draft,
)

_FFMPEG = shutil.which("ffmpeg") is not None

_SENTINEL_ACCESS = "ACCESS_SENTINEL_zzz"
_SENTINEL_REFRESH = "REFRESH_SENTINEL_zzz"
_SENTINEL_SECRET = "CLIENT_SECRET_SENTINEL_zzz"
_TOKEN = {
    "access_token": _SENTINEL_ACCESS, "refresh_token": _SENTINEL_REFRESH,
    "token_uri": "https://oauth2.googleapis.com/token", "client_id": "cid",
    "scopes": ["https://www.googleapis.com/auth/youtube.upload"],
    "expiry": "2999-01-01T00:00:00",
}


def _now_iso() -> str:
    return datetime.datetime.now(datetime.timezone.utc).isoformat()


def _old_iso() -> str:
    return "2020-01-01T00:00:00+00:00"


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
    json.dump({"installed": {"client_id": "cid", "client_secret": _SENTINEL_SECRET}}, fh)
    fh.close()
    return fh.name


def _make_jobs():
    root = tempfile.mkdtemp(prefix="rec_")
    jobs = os.path.join(root, "jobs")
    jd = os.path.join(jobs, "job1")
    os.makedirs(jd)
    mp4 = os.path.join(jd, "clip_01_score80.mp4")
    subprocess.run(
        ["ffmpeg", "-y", "-f", "lavfi", "-i", "color=c=black:s=108x192:d=0.4",
         "-pix_fmt", "yuv420p", mp4], capture_output=True, check=True)
    json.dump({"clips": [{"start": 0, "end": 20, "text": "x", "score": 80,
               "output_path": mp4, "content_package": {"primary_hook": "h",
               "youtube_shorts": {"title": "T", "description": "D",
                                  "hashtags": ["#s"]}}}]},
              open(os.path.join(jd, "clips.json"), "w"))
    d = create_draft(jd, "job1", platform="youtube_shorts",
                     source_type="auto_clip", source_clip_index=1)
    validate_draft(jd, d["publishing_id"])
    return root, jobs, jd, d["publishing_id"]


class _FakeCreds:
    def __init__(self, valid=True):
        self.valid = valid
        self.refresh_token = _SENTINEL_REFRESH
        self.token = _SENTINEL_ACCESS
        self.expiry = None


class _ScriptedSession:
    def __init__(self, steps):
        self._steps = list(steps)

    def next_chunk(self):
        step = self._steps.pop(0)
        if isinstance(step, BaseException):
            raise step
        return None, step


def _settings(stale=1, scan=True, **kw):
    return Settings(enable_youtube_upload=True, enable_youtube_oauth=True,
                    youtube_stale_upload_seconds=stale,
                    youtube_recovery_scan_enabled=scan, **kw)


def _svc(secrets, **kw):
    s = _settings(secrets_path=secrets) if False else Settings(
        enable_youtube_upload=True, enable_youtube_oauth=True,
        youtube_client_secrets_file=secrets, youtube_stale_upload_seconds=1)
    return YouTubeUploadService(
        s, credentials_loader=lambda c, p, sec: _FakeCreds(),
        session_factory=kw.get("session_factory"),
        sleep_fn=lambda d: None)


# ---------------------- State-Machine -------------------------------------

def test_state_valid_transition():
    u = st.transition({"upload_state": "idle"}, "preparing", now=_now_iso())
    assert u["upload_state"] == "preparing"
    assert u["status"] == "publishing" and u["idempotency_state"] == "in_progress"


def test_state_invalid_transition_rejected():
    try:
        st.transition({"upload_state": "idle"}, "uploading", now=_now_iso())
        assert False, "sollte InvalidTransition werfen"
    except InvalidTransition:
        pass


def test_state_terminal_protected():
    try:
        st.transition({"upload_state": "published"}, "preparing", now=_now_iso())
        assert False, "published ist terminal"
    except InvalidTransition:
        pass


def test_state_uncertain_no_direct_retry():
    # uncertain darf NICHT direkt zu preparing/uploading (nur reconciling).
    assert st.can_transition("uncertain", "reconciling") is True
    assert st.can_transition("uncertain", "preparing") is False
    assert st.can_transition("uncertain", "uploading") is False


def test_state_history_capped_and_no_secrets():
    draft = {"upload_state": "idle"}
    # simuliere viele Übergänge (Ping-Pong uploading<->retry_wait)
    now = _now_iso()
    draft.update(st.transition(draft, "preparing", now=now))
    draft.update(st.transition(draft, "uploading", now=now))
    for _ in range(40):
        draft.update(st.transition(draft, "retry_wait", now=now))
        draft.update(st.transition(draft, "uploading", now=now))
    hist = draft["state_transition_history"]
    assert len(hist) <= st.MAX_TRANSITION_HISTORY
    blob = json.dumps(hist).lower()
    assert "access_token" not in blob and "secret" not in blob


# ---------------------- Crash-Recovery (Scanner) --------------------------

def _set_active(jd, pid, state, *, activity, ext=None):
    up = {"upload_state": state, "last_upload_activity_at": activity,
          "status": "publishing", "idempotency_state": "in_progress"}
    if ext:
        up["external_post_id"] = ext
    apply_publish_state(jd, pid, up)


def test_recovery_stale_uploading_with_id_reconciles_published():
    """Szenario A: uploading → crash → stale → reconciling → remote bestätigt
    external_post_id → published."""
    if not _FFMPEG:
        return
    _install_fake_keyring()
    root, jobs, jd, pid = _make_jobs()
    try:
        _set_active(jd, pid, "uploading", activity=_old_iso(), ext="VID_A")
        verifier = lambda vid: ("found", {"id": vid, "status": {"privacyStatus": "private"}})
        scanner = RecoveryScanner(_settings(), reconciler=ReconciliationService(verifier=verifier))
        summ = scanner.scan(jobs)
        d = load_draft(jd, pid)
        assert summ["stale"] == 1 and summ["reconciled_published"] == 1
        assert d["upload_state"] == "published"
        assert d["external_post_id"] == "VID_A"
    finally:
        sys.modules.pop("keyring", None); shutil.rmtree(root)


def test_recovery_stale_uploading_without_id_is_uncertain():
    """Szenario B: uploading → crash → stale → keine eindeutige Remote-
    Verifikation möglich → uncertain, requires_manual_check, KEIN Re-Upload."""
    if not _FFMPEG:
        return
    _install_fake_keyring()
    root, jobs, jd, pid = _make_jobs()
    verifier_calls = {"n": 0}
    try:
        _set_active(jd, pid, "uploading", activity=_old_iso())  # kein ext id

        def verifier(vid):
            verifier_calls["n"] += 1
            return ("found", {"id": vid})
        scanner = RecoveryScanner(_settings(),
                                  reconciler=ReconciliationService(verifier=verifier))
        scanner.scan(jobs)
        d = load_draft(jd, pid)
        assert d["upload_state"] == "uncertain"
        assert d["requires_manual_check"] is True
        assert verifier_calls["n"] == 0  # keine ID → Verifier NIE aufgerufen
    finally:
        sys.modules.pop("keyring", None); shutil.rmtree(root)


def test_recovery_stale_preparing_and_retry_wait_and_auth_refresh():
    if not _FFMPEG:
        return
    _install_fake_keyring()
    for state in ("preparing", "retry_wait", "auth_refresh", "reconciling"):
        root, jobs, jd, pid = _make_jobs()
        try:
            _set_active(jd, pid, state, activity=_old_iso())
            RecoveryScanner(_settings()).scan(jobs)
            d = load_draft(jd, pid)
            assert d["upload_state"] == "uncertain", state
        finally:
            shutil.rmtree(root)
    sys.modules.pop("keyring", None)


def test_recovery_fresh_uploading_untouched():
    if not _FFMPEG:
        return
    _install_fake_keyring()
    root, jobs, jd, pid = _make_jobs()
    try:
        _set_active(jd, pid, "uploading", activity=_now_iso())  # frisch
        summ = RecoveryScanner(_settings()).scan(jobs)
        d = load_draft(jd, pid)
        assert summ["stale"] == 0 and d["upload_state"] == "uploading"
    finally:
        sys.modules.pop("keyring", None); shutil.rmtree(root)


def test_recovery_scan_disabled_no_scan():
    if not _FFMPEG:
        return
    _install_fake_keyring()
    root, jobs, jd, pid = _make_jobs()
    try:
        _set_active(jd, pid, "uploading", activity=_old_iso())
        summ = RecoveryScanner(_settings(scan=False)).scan(jobs)
        d = load_draft(jd, pid)
        assert summ["enabled"] is False and d["upload_state"] == "uploading"
    finally:
        sys.modules.pop("keyring", None); shutil.rmtree(root)


def test_recovery_never_triggers_upload():
    """Der Scanner ruft NIE einen Uploader auf (kein Blind-Upload)."""
    if not _FFMPEG:
        return
    _install_fake_keyring()
    root, jobs, jd, pid = _make_jobs()
    upl = {"n": 0}
    try:
        _set_active(jd, pid, "uploading", activity=_old_iso())
        # Ein Reconciler, dessen Verifier zählt — er darf hier nie zum Upload führen.
        RecoveryScanner(_settings(),
                        reconciler=ReconciliationService(
                            verifier=lambda v: ("not_found", None))).scan(jobs)
        assert upl["n"] == 0
        # Zustand ist ein sicherer (kein publishing/uploading mehr).
        assert load_draft(jd, pid)["upload_state"] in ("uncertain", "failed", "reconciling")
    finally:
        sys.modules.pop("keyring", None); shutil.rmtree(root)


# ---------------------- Reconciliation-Matrix -----------------------------

def _reconcile(jd, pid, verifier):
    return ReconciliationService(verifier=verifier).reconcile(
        jd, pid, load_draft(jd, pid))


def test_reconcile_external_id_exists_published():
    if not _FFMPEG:
        return
    _install_fake_keyring()
    root, jobs, jd, pid = _make_jobs()
    try:
        apply_publish_state(jd, pid, {"upload_state": "reconciling",
                                      "external_post_id": "VIDX"})
        _reconcile(jd, pid, lambda v: ("found", {"id": v, "status": {"privacyStatus": "private"}}))
        assert load_draft(jd, pid)["upload_state"] == "published"
    finally:
        sys.modules.pop("keyring", None); shutil.rmtree(root)


def test_reconcile_remote_missing_safe_state():
    if not _FFMPEG:
        return
    _install_fake_keyring()
    root, jobs, jd, pid = _make_jobs()
    try:
        apply_publish_state(jd, pid, {"upload_state": "reconciling",
                                      "external_post_id": "VIDX"})
        _reconcile(jd, pid, lambda v: ("not_found", None))
        d = load_draft(jd, pid)
        assert d["upload_state"] == "failed" and d.get("external_post_id") is None
    finally:
        sys.modules.pop("keyring", None); shutil.rmtree(root)


def test_reconcile_network_error_uncertain_no_fake_success():
    if not _FFMPEG:
        return
    _install_fake_keyring()
    root, jobs, jd, pid = _make_jobs()
    try:
        apply_publish_state(jd, pid, {"upload_state": "reconciling",
                                      "external_post_id": "VIDX"})
        _reconcile(jd, pid, lambda v: (_ for _ in ()).throw(TimeoutError("net")))
        d = load_draft(jd, pid)
        assert d["upload_state"] == "uncertain" and d["requires_manual_check"] is True
    finally:
        sys.modules.pop("keyring", None); shutil.rmtree(root)


def test_reconcile_no_identifier_manual_check_no_heuristic():
    if not _FFMPEG:
        return
    _install_fake_keyring()
    root, jobs, jd, pid = _make_jobs()
    called = {"n": 0}
    try:
        apply_publish_state(jd, pid, {"upload_state": "uncertain",
                                      "status": "failed", "idempotency_state": "uncertain"})

        def verifier(v):
            called["n"] += 1
            return ("found", {"id": v})
        _reconcile(jd, pid, verifier)
        d = load_draft(jd, pid)
        # KEINE ID → Verifier nie aufgerufen (keine Titel-/Namens-Heuristik).
        assert called["n"] == 0
        assert d["upload_state"] == "uncertain"
        assert d["reconciliation_status"] == "no_unique_identifier"
    finally:
        sys.modules.pop("keyring", None); shutil.rmtree(root)


def test_reconcile_id_mismatch_is_uncertain():
    """Verifier liefert eine ANDERE ID → keine eindeutige Bestätigung."""
    if not _FFMPEG:
        return
    _install_fake_keyring()
    root, jobs, jd, pid = _make_jobs()
    try:
        apply_publish_state(jd, pid, {"upload_state": "reconciling",
                                      "external_post_id": "VIDX"})
        _reconcile(jd, pid, lambda v: ("found", {"id": "OTHER"}))
        assert load_draft(jd, pid)["upload_state"] == "uncertain"
    finally:
        sys.modules.pop("keyring", None); shutil.rmtree(root)


# ---------------------- Idempotenz / Race ---------------------------------

def test_double_click_one_upload():
    """Zwei sequentielle Publish-Requests → genau EIN Upload (2. blockiert)."""
    if not _FFMPEG:
        return
    _install_fake_keyring()
    root, jobs, jd, pid = _make_jobs()
    sec = _write_secrets()
    calls = {"n": 0}
    try:
        def factory(c, b, m):
            calls["n"] += 1
            return _ScriptedSession([{"id": "VID", "status": {"privacyStatus": "private"}}])
        svc = YouTubeUploadService(
            Settings(enable_youtube_upload=True, enable_youtube_oauth=True,
                     youtube_client_secrets_file=sec),
            credentials_loader=lambda c, p, s: _FakeCreds(),
            session_factory=factory, sleep_fn=lambda d: None)
        r1 = svc.upload_private(jd, pid, load_draft(jd, pid), confirm="UPLOAD_PRIVATE")
        r2 = svc.upload_private(jd, pid, load_draft(jd, pid), confirm="UPLOAD_PRIVATE")
        assert r1["success"] is True
        assert r2["success"] is False and r2["error_code"] == "already_uploaded"
        assert calls["n"] == 1
    finally:
        sys.modules.pop("keyring", None); os.unlink(sec); shutil.rmtree(root)


def test_two_parallel_requests_exactly_one_uploader_call():
    """Szenario C: zwei GLEICHZEITIGE Publish-Requests → exakt 1 Uploader-Aufruf."""
    if not _FFMPEG:
        return
    _install_fake_keyring()
    root, jobs, jd, pid = _make_jobs()
    sec = _write_secrets()
    calls = {"n": 0}
    lock = threading.Lock()
    start = threading.Barrier(2)
    results = {}
    try:
        def factory(c, b, m):
            with lock:
                calls["n"] += 1
            # kleine Verzögerung, damit beide Threads sicher konkurrieren
            import time as _t
            _t.sleep(0.05)
            return _ScriptedSession([{"id": "VIDP", "status": {"privacyStatus": "private"}}])

        def worker(name):
            svc = YouTubeUploadService(
                Settings(enable_youtube_upload=True, enable_youtube_oauth=True,
                         youtube_client_secrets_file=sec),
                credentials_loader=lambda c, p, s: _FakeCreds(),
                session_factory=factory, sleep_fn=lambda d: None)
            start.wait()
            results[name] = svc.upload_private(
                jd, pid, load_draft(jd, pid), confirm="UPLOAD_PRIVATE")

        t1 = threading.Thread(target=worker, args=("a",))
        t2 = threading.Thread(target=worker, args=("b",))
        t1.start(); t2.start(); t1.join(); t2.join()
        successes = [r for r in results.values() if r.get("success")]
        # Genau ein echter Upload-Start.
        assert calls["n"] == 1, f"uploader invocations={calls['n']}"
        assert len(successes) == 1, results
        blocked = [r for r in results.values() if not r.get("success")]
        assert blocked and blocked[0]["error_code"] in (
            "upload_in_progress", "already_uploaded")
    finally:
        sys.modules.pop("keyring", None); os.unlink(sec); shutil.rmtree(root)


def test_published_blocks_further_upload():
    if not _FFMPEG:
        return
    _install_fake_keyring()
    root, jobs, jd, pid = _make_jobs()
    sec = _write_secrets()
    try:
        apply_publish_state(jd, pid, {"upload_state": "published",
                                      "external_post_id": "VID", "status": "published",
                                      "idempotency_state": "succeeded"})
        svc = YouTubeUploadService(
            Settings(enable_youtube_upload=True, enable_youtube_oauth=True,
                     youtube_client_secrets_file=sec),
            credentials_loader=lambda c, p, s: _FakeCreds(),
            session_factory=lambda c, b, m: _ScriptedSession([{"id": "X"}]),
            sleep_fn=lambda d: None)
        r = svc.upload_private(jd, pid, load_draft(jd, pid), confirm="UPLOAD_PRIVATE")
        assert r["error_code"] == "already_uploaded"
    finally:
        sys.modules.pop("keyring", None); os.unlink(sec); shutil.rmtree(root)


def test_uncertain_blocks_further_upload():
    if not _FFMPEG:
        return
    _install_fake_keyring()
    root, jobs, jd, pid = _make_jobs()
    sec = _write_secrets()
    try:
        apply_publish_state(jd, pid, {"upload_state": "uncertain",
                                      "status": "failed", "idempotency_state": "uncertain"})
        svc = YouTubeUploadService(
            Settings(enable_youtube_upload=True, enable_youtube_oauth=True,
                     youtube_client_secrets_file=sec),
            credentials_loader=lambda c, p, s: _FakeCreds(),
            session_factory=lambda c, b, m: _ScriptedSession([{"id": "X"}]),
            sleep_fn=lambda d: None)
        r = svc.upload_private(jd, pid, load_draft(jd, pid), confirm="UPLOAD_PRIVATE")
        assert r["error_code"] == "upload_state_uncertain"
    finally:
        sys.modules.pop("keyring", None); os.unlink(sec); shutil.rmtree(root)


# ---------------------- Security / No-Leak --------------------------------

_MARKERS = ("access_token", "refresh_token", "bearer ", "uploadlock",
            "resumable", "sessionuri", "session_uri")


def _assert_clean(obj, *forbidden):
    blob = json.dumps(obj, ensure_ascii=False).lower()
    for m in _MARKERS:
        assert m not in blob, f"Marker in Antwort: {m}"
    for f in forbidden:
        assert f.lower() not in blob, f"geleakt: {f}"


def test_upload_status_no_secrets_or_session_uri():
    if not _FFMPEG:
        return
    _install_fake_keyring()
    root, jobs, jd, pid = _make_jobs()
    sec = _write_secrets()
    try:
        svc = YouTubeUploadService(
            Settings(enable_youtube_upload=True, enable_youtube_oauth=True,
                     youtube_client_secrets_file=sec),
            credentials_loader=lambda c, p, s: _FakeCreds(),
            session_factory=lambda c, b, m: _ScriptedSession(
                [{"id": "VID", "status": {"privacyStatus": "private"}}]),
            sleep_fn=lambda d: None)
        svc.upload_private(jd, pid, load_draft(jd, pid), confirm="UPLOAD_PRIVATE")
        us = svc.upload_status(load_draft(jd, pid))
        assert us["state"] == "published"
        _assert_clean(us, _SENTINEL_ACCESS, _SENTINEL_REFRESH, _SENTINEL_SECRET)
        # Transition-/Attempt-History ebenfalls sauber.
        _assert_clean(load_draft(jd, pid).get("state_transition_history"))
        _assert_clean(load_draft(jd, pid).get("publish_attempts"))
    finally:
        sys.modules.pop("keyring", None); os.unlink(sec); shutil.rmtree(root)


# ---------------------- API (TestClient) ----------------------------------

def _make_client():
    tmp = tempfile.mkdtemp(prefix="rec_api_")
    jobs_dir = os.path.join(tmp, "jobs")
    os.makedirs(jobs_dir)
    src_root, _, src_jd, pid = _make_jobs()
    job_dir = os.path.join(jobs_dir, "recjob01")
    shutil.move(src_jd, job_dir)
    cp = os.path.join(job_dir, "clips.json")
    data = json.load(open(cp)); data["clips"][0]["output_path"] = os.path.join(
        job_dir, "clip_01_score80.mp4"); json.dump(data, open(cp, "w"))
    dpath = os.path.join(job_dir, "publishing", pid + ".json")
    dd = json.load(open(dpath)); dd["mp4_path"] = os.path.join(job_dir, "clip_01_score80.mp4")
    json.dump(dd, open(dpath, "w"))
    shutil.rmtree(src_root, ignore_errors=True)
    os.environ["CLIPFORGE_JOBS_DIR"] = jobs_dir
    sys.modules.pop("app", None)
    from fastapi.testclient import TestClient
    import app as app_module
    return TestClient(app_module.app), tmp, app_module, pid


def test_api_reconcile_endpoint_never_uploads():
    if not _FFMPEG:
        return
    sec = _write_secrets(); _install_fake_keyring()
    client, tmp, app_module, pid = _make_client()
    upl = {"n": 0}
    app_module._youtube_upload_session_factory = (
        lambda c, b, m: (_ for _ in ()).throw(AssertionError("no upload in reconcile")))
    # Fake-Verifier (kein echter Google-Call): bestätigt eine bekannte ID.
    app_module._youtube_remote_verifier = lambda vid: ("found", {"id": vid, "status": {}})
    try:
        # Draft in reconciling mit bekannter external_post_id versetzen.
        from clipforge.publishing import apply_publish_state as aps
        jd = os.path.join(tmp, "jobs", "recjob01")
        aps(jd, pid, {"upload_state": "reconciling", "external_post_id": "VIDR"})
        r = client.post(f"/api/jobs/recjob01/publishing/{pid}/youtube/reconcile")
        assert r.status_code == 200, r.text
        body = r.json()
        assert body["state"] == "published"
        assert body["no_secrets"] is True
        _assert_clean(body, _SENTINEL_ACCESS, _SENTINEL_REFRESH, _SENTINEL_SECRET)
    finally:
        os.environ.pop("CLIPFORGE_JOBS_DIR", None)
        os.unlink(sec); shutil.rmtree(tmp, ignore_errors=True)
        sys.modules.pop("keyring", None); sys.modules.pop("app", None)


def test_api_upload_status_has_state_and_recovery_fields():
    if not _FFMPEG:
        return
    sec = _write_secrets(); _install_fake_keyring()
    client, tmp, app_module, pid = _make_client()
    try:
        r = client.get(f"/api/jobs/recjob01/publishing/{pid}/youtube/upload-status")
        assert r.status_code == 200, r.text
        body = r.json()
        for key in ("state", "is_stale", "can_reconcile", "can_retry",
                    "last_error_category", "reconciliation_status",
                    "transition_history_summary"):
            assert key in body, key
        assert body["state"] == "idle"
        _assert_clean(body)
    finally:
        os.environ.pop("CLIPFORGE_JOBS_DIR", None)
        os.unlink(sec); shutil.rmtree(tmp, ignore_errors=True)
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
