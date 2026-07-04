"""Tests für den echten PRIVATEN YouTube-Upload (Phase 3).

KEIN echter Google-Call, KEIN echter Upload: Credentials-Loader, Refresher und
Uploader werden injiziert/gemockt. keyring wird durch ein Fake-Modul ersetzt.
Getestet: Feature-Flag, Bestätigung, private-only, Idempotenz (inkl. uncertain),
Token-Refresh, Fehlerklassifikation und dass NIE Tokens/Secrets leaken.

Läuft ohne pytest: `python tests/test_youtube_upload.py` (braucht ffmpeg für die
Mini-MP4-Fixtures; ohne ffmpeg werden diese Tests übersprungen).
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import tempfile
import types

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from clipforge.config import Settings
from clipforge.platforms.youtube_upload import (
    YouTubeUploadService,
    YouTubeRetryPolicy,
    UploadUncertain,
    AUTH_REFRESHABLE,
    NON_RETRYABLE,
    RETRYABLE,
    UNCERTAIN,
    derive_idempotency_state,
)
from clipforge.publishing import create_draft, load_draft, validate_draft

_FFMPEG = shutil.which("ffmpeg") is not None

_SENTINEL_ACCESS = "ACCESS_SENTINEL_zzz"
_SENTINEL_REFRESH = "REFRESH_SENTINEL_zzz"
_SENTINEL_SECRET = "CLIENT_SECRET_SENTINEL_zzz"
_VALUE_MARKERS = ("access_token", "refresh_token", "bearer ")

_TOKEN = {
    "access_token": _SENTINEL_ACCESS, "refresh_token": _SENTINEL_REFRESH,
    "token_uri": "https://oauth2.googleapis.com/token", "client_id": "cid",
    "scopes": ["https://www.googleapis.com/auth/youtube.upload"],
    "expiry": "2999-01-01T00:00:00",
}


def _assert_no_secret_values(obj, *forbidden: str) -> None:
    blob = json.dumps(obj, ensure_ascii=False).lower()
    for m in _VALUE_MARKERS:
        assert m not in blob, f"möglicher Secret-Wert in Antwort: {m}"
    for f in forbidden:
        assert f.lower() not in blob, f"geleakter Wert in Antwort: {f}"


def _install_fake_keyring(payload: dict | None = _TOKEN):
    fake = types.ModuleType("keyring")
    store: dict = {}
    if payload is not None:
        store[("clipforge-youtube", "default")] = json.dumps(payload)

    class B:  # nicht das 'fail'-Backend
        pass

    fake.get_keyring = lambda: B()
    fake.get_password = lambda s, a: store.get((s, a))
    fake.set_password = lambda s, a, v: store.__setitem__((s, a), v)

    def _d(s, a):
        store.pop((s, a), None)

    fake.delete_password = _d
    sys.modules["keyring"] = fake
    return store


def _write_secrets() -> str:
    fh = tempfile.NamedTemporaryFile("w", suffix=".json", delete=False)
    json.dump({"installed": {"client_id": "cid", "client_secret": _SENTINEL_SECRET}}, fh)
    fh.close()
    return fh.name


def _make_job():
    jd = tempfile.mkdtemp(prefix="upl_")
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
    return jd, d["publishing_id"]


class _FakeCreds:
    def __init__(self, valid=True, refresh_token=_SENTINEL_REFRESH,
                 token=_SENTINEL_ACCESS):
        self.valid = valid
        self.refresh_token = refresh_token
        self.token = token
        self.expiry = None


def _settings(enabled=True, oauth=True, secrets=None):
    return Settings(enable_youtube_upload=enabled, enable_youtube_oauth=oauth,
                    youtube_client_secrets_file=secrets)


def _loader_ok(cfg, payload, secret):
    # Der client_secret MUSS frisch aus der Datei kommen (für Refresh).
    assert secret == _SENTINEL_SECRET
    return _FakeCreds(valid=True)


def _uploader_ok(creds, body, media):
    assert body["status"]["privacyStatus"] == "private"  # nie public/unlisted
    return {"id": "VIDEO_OK", "snippet": {"title": body["snippet"]["title"]},
            "status": {"privacyStatus": "private"}}


def _svc(settings, secrets, **kw):
    return YouTubeUploadService(
        settings,
        credentials_loader=kw.pop("loader", _loader_ok),
        refresher=kw.pop("refresher", None),
        uploader=kw.pop("uploader", None) if kw.get("session_factory") else kw.pop("uploader", _uploader_ok),
        session_factory=kw.pop("session_factory", None),
        retry_policy=kw.pop("retry_policy", None),
        sleep_fn=kw.pop("sleep_fn", lambda d: None),  # NIE real schlafen
    )


class _ScriptedSession:
    """Fake resumable Session: `steps` ist eine Liste von Callables/Werten.
    Jeder next_chunk()-Aufruf verarbeitet den nächsten Step: ein Exception-
    Objekt wird geworfen, ein dict → (None, dict) (Erfolg)."""

    def __init__(self, steps):
        self._steps = list(steps)

    def next_chunk(self):
        step = self._steps.pop(0)
        if isinstance(step, BaseException):
            raise step
        return None, step


def _http(status=None, reason=None):
    attrs = {}
    if status is not None:
        attrs["status_code"] = status
    if reason is not None:
        attrs["reason"] = reason
    return type("FakeHttpError", (Exception,), attrs)()


# ---------------------- Feature-Flag / Bestätigung / privacy --------------

def test_feature_flag_default_false():
    assert Settings().enable_youtube_upload is False


def test_upload_disabled_no_api_call():
    if not _FFMPEG:
        return
    jd, pid = _make_job(); _install_fake_keyring(); sec = _write_secrets()
    called = {"n": 0}

    def up(c, b, m):
        called["n"] += 1
        return {"id": "X"}
    try:
        svc = _svc(_settings(enabled=False, secrets=sec), sec, uploader=up)
        r = svc.upload_private(jd, pid, load_draft(jd, pid), confirm="UPLOAD_PRIVATE")
        assert r["error_code"] == "upload_disabled" and called["n"] == 0
        assert load_draft(jd, pid)["status"] in ("draft", "ready")
    finally:
        sys.modules.pop("keyring", None); os.unlink(sec); shutil.rmtree(jd)


def test_wrong_confirm_blocked():
    if not _FFMPEG:
        return
    jd, pid = _make_job(); _install_fake_keyring(); sec = _write_secrets()
    try:
        svc = _svc(_settings(secrets=sec), sec)
        r = svc.upload_private(jd, pid, load_draft(jd, pid), confirm="NOPE")
        assert r["error_code"] == "confirmation_required"
    finally:
        sys.modules.pop("keyring", None); os.unlink(sec); shutil.rmtree(jd)


def test_public_and_unlisted_blocked():
    if not _FFMPEG:
        return
    jd, pid = _make_job(); _install_fake_keyring(); sec = _write_secrets()
    try:
        svc = _svc(_settings(secrets=sec), sec)
        for bad in ("public", "unlisted"):
            r = svc.upload_private(jd, pid, load_draft(jd, pid),
                                   confirm="UPLOAD_PRIVATE", privacy_status=bad)
            assert r["error_code"] == "invalid_privacy_status", bad
            assert load_draft(jd, pid)["external_post_id"] is None
    finally:
        sys.modules.pop("keyring", None); os.unlink(sec); shutil.rmtree(jd)


# ---------------------- Preconditions -------------------------------------

def test_missing_mp4_blocked():
    if not _FFMPEG:
        return
    jd, pid = _make_job(); _install_fake_keyring(); sec = _write_secrets()
    try:
        # MP4 löschen (Draft bleibt sonst valide via gespeicherte Checks →
        # daher auch die Validierung zurücksetzen)
        d = load_draft(jd, pid); os.remove(d["mp4_path"])
        svc = _svc(_settings(secrets=sec), sec)
        r = svc.upload_private(jd, pid, load_draft(jd, pid), confirm="UPLOAD_PRIVATE")
        assert r["error_code"] in ("mp4_missing", "invalid_draft")
    finally:
        sys.modules.pop("keyring", None); os.unlink(sec); shutil.rmtree(jd)


def test_invalid_draft_blocked():
    if not _FFMPEG:
        return
    jd, pid = _make_job(); _install_fake_keyring(); sec = _write_secrets()
    try:
        d = load_draft(jd, pid)
        d["validation"]["checks"]["no_virality_claim"] = False  # inhaltlich invalid
        json.dump(d, open(os.path.join(jd, "publishing", pid + ".json"), "w"))
        svc = _svc(_settings(secrets=sec), sec)
        r = svc.upload_private(jd, pid, load_draft(jd, pid), confirm="UPLOAD_PRIVATE")
        assert r["error_code"] == "invalid_draft"
    finally:
        sys.modules.pop("keyring", None); os.unlink(sec); shutil.rmtree(jd)


def test_token_missing_blocked():
    if not _FFMPEG:
        return
    jd, pid = _make_job(); _install_fake_keyring(payload=None); sec = _write_secrets()
    try:
        svc = _svc(_settings(secrets=sec), sec)
        r = svc.upload_private(jd, pid, load_draft(jd, pid), confirm="UPLOAD_PRIVATE")
        assert r["error_code"] == "token_missing"
    finally:
        sys.modules.pop("keyring", None); os.unlink(sec); shutil.rmtree(jd)


# ---------------------- Token-Refresh -------------------------------------

def test_expired_without_refresh_token_reauth_required():
    if not _FFMPEG:
        return
    jd, pid = _make_job()
    _install_fake_keyring({**_TOKEN, "refresh_token": None}); sec = _write_secrets()
    try:
        loader = lambda c, p, s: _FakeCreds(valid=False, refresh_token=None)
        svc = _svc(_settings(secrets=sec), sec, loader=loader)
        r = svc.upload_private(jd, pid, load_draft(jd, pid), confirm="UPLOAD_PRIVATE")
        assert r["error_code"] == "reauth_required"
    finally:
        sys.modules.pop("keyring", None); os.unlink(sec); shutil.rmtree(jd)


def test_refresh_success_updates_tokenstore():
    if not _FFMPEG:
        return
    jd, pid = _make_job(); store = _install_fake_keyring(); sec = _write_secrets()
    try:
        loader = lambda c, p, s: _FakeCreds(valid=False)

        def refresher(creds):
            creds.valid = True
            creds.token = "NEW_ACCESS_zzz"
        svc = _svc(_settings(secrets=sec), sec, loader=loader, refresher=refresher)
        r = svc.upload_private(jd, pid, load_draft(jd, pid), confirm="UPLOAD_PRIVATE")
        assert r["success"] is True
        stored = json.loads(store[("clipforge-youtube", "default")])
        assert stored["access_token"] == "NEW_ACCESS_zzz"  # Keychain aktualisiert
        _assert_no_secret_values(r, "NEW_ACCESS_zzz", _SENTINEL_REFRESH)
    finally:
        sys.modules.pop("keyring", None); os.unlink(sec); shutil.rmtree(jd)


def test_no_unnecessary_refresh_when_valid():
    if not _FFMPEG:
        return
    jd, pid = _make_job(); _install_fake_keyring(); sec = _write_secrets()
    called = {"n": 0}
    try:
        def refresher(creds):
            called["n"] += 1
        svc = _svc(_settings(secrets=sec), sec,
                   loader=lambda c, p, s: _FakeCreds(valid=True), refresher=refresher)
        r = svc.upload_private(jd, pid, load_draft(jd, pid), confirm="UPLOAD_PRIVATE")
        assert r["success"] is True and called["n"] == 0
    finally:
        sys.modules.pop("keyring", None); os.unlink(sec); shutil.rmtree(jd)


# ---------------------- Erfolg + Idempotenz -------------------------------

def test_upload_success_sets_published_and_external_id():
    if not _FFMPEG:
        return
    jd, pid = _make_job(); _install_fake_keyring(); sec = _write_secrets()
    try:
        svc = _svc(_settings(secrets=sec), sec)
        r = svc.upload_private(jd, pid, load_draft(jd, pid), confirm="UPLOAD_PRIVATE")
        assert r["success"] is True and r["status"] == "published"
        assert r["external_post_id"] == "VIDEO_OK"
        assert r["privacy_status"] == "private"
        after = load_draft(jd, pid)
        assert after["status"] == "published"
        assert after["external_post_id"] == "VIDEO_OK"
        assert after["idempotency_state"] == "succeeded"
        assert after["publish_attempt_count"] == 1
        _assert_no_secret_values(r, _SENTINEL_ACCESS, _SENTINEL_REFRESH, _SENTINEL_SECRET)
    finally:
        sys.modules.pop("keyring", None); os.unlink(sec); shutil.rmtree(jd)


def test_no_external_id_never_published():
    if not _FFMPEG:
        return
    jd, pid = _make_job(); _install_fake_keyring(); sec = _write_secrets()
    try:
        # Uploader liefert Antwort OHNE id → uncertain, NIE published.
        svc = _svc(_settings(secrets=sec), sec, uploader=lambda c, b, m: {"foo": "bar"})
        r = svc.upload_private(jd, pid, load_draft(jd, pid), confirm="UPLOAD_PRIVATE")
        assert r["success"] is False
        assert r["error_code"] == "upload_result_uncertain"
        assert load_draft(jd, pid)["external_post_id"] is None
        assert load_draft(jd, pid)["status"] != "published"
    finally:
        sys.modules.pop("keyring", None); os.unlink(sec); shutil.rmtree(jd)


def test_second_upload_after_success_blocked():
    if not _FFMPEG:
        return
    jd, pid = _make_job(); _install_fake_keyring(); sec = _write_secrets()
    try:
        svc = _svc(_settings(secrets=sec), sec)
        assert svc.upload_private(jd, pid, load_draft(jd, pid),
                                  confirm="UPLOAD_PRIVATE")["success"] is True
        r2 = svc.upload_private(jd, pid, load_draft(jd, pid), confirm="UPLOAD_PRIVATE")
        assert r2["error_code"] == "already_uploaded"
    finally:
        sys.modules.pop("keyring", None); os.unlink(sec); shutil.rmtree(jd)


def test_upload_blocked_when_in_progress():
    if not _FFMPEG:
        return
    jd, pid = _make_job(); _install_fake_keyring(); sec = _write_secrets()
    try:
        from clipforge.publishing import apply_publish_state
        apply_publish_state(jd, pid, {"status": "publishing",
                                      "idempotency_state": "in_progress"})
        svc = _svc(_settings(secrets=sec), sec)
        r = svc.upload_private(jd, pid, load_draft(jd, pid), confirm="UPLOAD_PRIVATE")
        assert r["error_code"] == "upload_in_progress"
    finally:
        sys.modules.pop("keyring", None); os.unlink(sec); shutil.rmtree(jd)


def test_upload_blocked_when_uncertain():
    if not _FFMPEG:
        return
    jd, pid = _make_job(); _install_fake_keyring(); sec = _write_secrets()
    try:
        from clipforge.publishing import apply_publish_state
        apply_publish_state(jd, pid, {"status": "failed",
                                      "idempotency_state": "uncertain"})
        svc = _svc(_settings(secrets=sec), sec)
        r = svc.upload_private(jd, pid, load_draft(jd, pid), confirm="UPLOAD_PRIVATE")
        assert r["error_code"] == "upload_state_uncertain"
    finally:
        sys.modules.pop("keyring", None); os.unlink(sec); shutil.rmtree(jd)


def test_retry_allowed_after_clean_failure():
    if not _FFMPEG:
        return
    jd, pid = _make_job(); _install_fake_keyring(); sec = _write_secrets()

    class Http403(Exception):
        status_code = 403
        reason = "forbidden"
    try:
        svc_fail = _svc(_settings(secrets=sec), sec,
                        uploader=lambda c, b, m: (_ for _ in ()).throw(Http403()))
        r = svc_fail.upload_private(jd, pid, load_draft(jd, pid), confirm="UPLOAD_PRIVATE")
        assert r["error_code"] == "permission_denied"
        assert load_draft(jd, pid)["idempotency_state"] == "failed"
        # Retry nach eindeutigem failed → erlaubt → Erfolg
        svc_ok = _svc(_settings(secrets=sec), sec)
        r2 = svc_ok.upload_private(jd, pid, load_draft(jd, pid), confirm="UPLOAD_PRIVATE")
        assert r2["success"] is True
        assert load_draft(jd, pid)["publish_attempt_count"] == 2
    finally:
        sys.modules.pop("keyring", None); os.unlink(sec); shutil.rmtree(jd)


def test_network_uncertainty_marks_uncertain_not_failed():
    if not _FFMPEG:
        return
    jd, pid = _make_job(); _install_fake_keyring(); sec = _write_secrets()
    try:
        svc = _svc(_settings(secrets=sec), sec,
                   uploader=lambda c, b, m: (_ for _ in ()).throw(UploadUncertain()))
        r = svc.upload_private(jd, pid, load_draft(jd, pid), confirm="UPLOAD_PRIVATE")
        assert r["error_code"] == "upload_result_uncertain"
        assert r["idempotency_state"] == "uncertain"
        assert load_draft(jd, pid)["idempotency_state"] == "uncertain"
        assert load_draft(jd, pid)["external_post_id"] is None
    finally:
        sys.modules.pop("keyring", None); os.unlink(sec); shutil.rmtree(jd)


def test_attempt_count_increments():
    if not _FFMPEG:
        return
    jd, pid = _make_job(); _install_fake_keyring(); sec = _write_secrets()

    class Http403(Exception):
        status_code = 403
        reason = "forbidden"
    try:
        fail = _svc(_settings(secrets=sec), sec,
                    uploader=lambda c, b, m: (_ for _ in ()).throw(Http403()))
        fail.upload_private(jd, pid, load_draft(jd, pid), confirm="UPLOAD_PRIVATE")
        assert load_draft(jd, pid)["publish_attempt_count"] == 1
        fail.upload_private(jd, pid, load_draft(jd, pid), confirm="UPLOAD_PRIVATE")
        assert load_draft(jd, pid)["publish_attempt_count"] == 2
    finally:
        sys.modules.pop("keyring", None); os.unlink(sec); shutil.rmtree(jd)


# ---------------------- Fehlerklassifikation ------------------------------

def _svc_bare(sec):
    return YouTubeUploadService(_settings(secrets=sec))


def test_classify_error_codes():
    sec = _write_secrets(); _install_fake_keyring()
    try:
        svc = _svc_bare(sec)

        def E(**attrs):
            return type("E", (Exception,), attrs)()
        assert svc.classify_error(E(status_code=401)) == "invalid_credentials"
        assert svc.classify_error(E(status_code=403, reason="quotaExceeded")) == "quota_exceeded"
        assert svc.classify_error(E(status_code=403, reason="rateLimitExceeded")) == "rate_limited"
        assert svc.classify_error(E(status_code=403, reason="forbidden")) == "permission_denied"
        assert svc.classify_error(E(status_code=429)) == "rate_limited"
        assert svc.classify_error(E(status_code=503)) == "upload_result_uncertain"
        assert svc.classify_error(E(status_code=500)) == "upload_result_uncertain"
        assert svc.classify_error(TimeoutError("x")) == "upload_result_uncertain"
        assert svc.classify_error(ValueError("weird")) == "upload_failed"
        assert svc.classify_error(UploadUncertain()) == "upload_result_uncertain"
    finally:
        sys.modules.pop("keyring", None); os.unlink(sec)


def test_raw_google_error_is_sanitized():
    if not _FFMPEG:
        return
    jd, pid = _make_job(); _install_fake_keyring(); sec = _write_secrets()
    try:
        def boom(c, b, m):
            raise RuntimeError(f"leak {_SENTINEL_SECRET} {_SENTINEL_ACCESS}")
        svc = _svc(_settings(secrets=sec), sec, uploader=boom)
        r = svc.upload_private(jd, pid, load_draft(jd, pid), confirm="UPLOAD_PRIVATE")
        assert r["error_code"] == "upload_failed"
        _assert_no_secret_values(r, _SENTINEL_SECRET, _SENTINEL_ACCESS)
        _assert_no_secret_values(load_draft(jd, pid), _SENTINEL_SECRET, _SENTINEL_ACCESS)
    finally:
        sys.modules.pop("keyring", None); os.unlink(sec); shutil.rmtree(jd)


def test_readiness_no_secrets_and_gates():
    if not _FFMPEG:
        return
    jd, pid = _make_job(); _install_fake_keyring(); sec = _write_secrets()
    try:
        svc = _svc(_settings(secrets=sec), sec)
        rd = svc.readiness(load_draft(jd, pid))
        assert rd["can_attempt_private_upload"] is True
        assert rd["token_present"] is True
        assert rd["token_refresh_possible"] is True
        assert rd["idempotency_state"] == "never_attempted"
        assert rd["privacy_status"] == "private"
        _assert_no_secret_values(rd, _SENTINEL_ACCESS, _SENTINEL_REFRESH)
    finally:
        sys.modules.pop("keyring", None); os.unlink(sec); shutil.rmtree(jd)


def test_derive_idempotency_state_legacy():
    assert derive_idempotency_state({}) == "never_attempted"
    assert derive_idempotency_state({"external_post_id": "x"}) == "succeeded"
    assert derive_idempotency_state({"status": "published"}) == "succeeded"
    assert derive_idempotency_state({"status": "publishing"}) == "in_progress"
    assert derive_idempotency_state({"status": "failed"}) == "failed"
    assert derive_idempotency_state({"idempotency_state": "uncertain"}) == "uncertain"


def test_build_request_is_always_private():
    sec = _write_secrets()
    try:
        svc = _svc_bare(sec)
        body = svc.build_upload_request({"title": "T", "description": "D",
                                         "hashtags": ["#a"]})
        assert body["status"]["privacyStatus"] == "private"
        assert body["snippet"]["tags"] == ["a"]
    finally:
        os.unlink(sec)


# ---------------------- API (TestClient) ----------------------------------

def _make_client():
    tmp = tempfile.mkdtemp(prefix="upl_api_")
    jobs_dir = os.path.join(tmp, "jobs"); os.makedirs(jobs_dir)
    src, pid = _make_job()
    job_dir = os.path.join(jobs_dir, "upljob0001")
    shutil.move(src, job_dir)
    cp = os.path.join(job_dir, "clips.json")
    data = json.load(open(cp)); data["clips"][0]["output_path"] = os.path.join(
        job_dir, "clip_01_score80.mp4"); json.dump(data, open(cp, "w"))
    # mp4_path im Draft auf den neuen (verschobenen) Ort umbiegen.
    dpath = os.path.join(job_dir, "publishing", pid + ".json")
    dd = json.load(open(dpath))
    dd["mp4_path"] = os.path.join(job_dir, "clip_01_score80.mp4")
    json.dump(dd, open(dpath, "w"))
    os.environ["CLIPFORGE_JOBS_DIR"] = jobs_dir
    sys.modules.pop("app", None)
    from fastapi.testclient import TestClient
    import app as app_module
    return TestClient(app_module.app), tmp, app_module, pid


def test_api_upload_success_with_mock(monkeypatch=None):
    if not _FFMPEG:
        return
    sec = _write_secrets(); _install_fake_keyring()
    os.environ["CLIPFORGE_ENABLE_YOUTUBE_UPLOAD"] = "true"
    os.environ["CLIPFORGE_ENABLE_YOUTUBE_OAUTH"] = "true"
    os.environ["CLIPFORGE_YOUTUBE_CLIENT_SECRETS"] = sec
    client, tmp, app_module, pid = _make_client()
    app_module._youtube_upload_credentials_loader = lambda c, p, s: _FakeCreds(valid=True)
    app_module._youtube_upload_uploader = _uploader_ok
    try:
        # revalidate (mp4_path wurde umgezogen)
        client.post(f"/api/jobs/upljob0001/publishing/{pid}/validate")
        r = client.post(f"/api/jobs/upljob0001/publishing/{pid}/youtube/publish",
                        json={"confirm": "UPLOAD_PRIVATE", "privacy_status": "private"})
        assert r.status_code == 200, r.text
        body = r.json()
        assert body["success"] is True and body["status"] == "published"
        assert body["external_post_id"] == "VIDEO_OK"
        assert body["privacy_status"] == "private"
        _assert_no_secret_values(body, _SENTINEL_ACCESS, _SENTINEL_REFRESH, _SENTINEL_SECRET)
        # zweiter Versuch → already_uploaded
        r2 = client.post(f"/api/jobs/upljob0001/publishing/{pid}/youtube/publish",
                         json={"confirm": "UPLOAD_PRIVATE", "privacy_status": "private"})
        assert r2.json()["error_code"] == "already_uploaded"
    finally:
        for k in ("CLIPFORGE_ENABLE_YOUTUBE_UPLOAD", "CLIPFORGE_ENABLE_YOUTUBE_OAUTH",
                  "CLIPFORGE_YOUTUBE_CLIENT_SECRETS", "CLIPFORGE_JOBS_DIR"):
            os.environ.pop(k, None)
        os.unlink(sec); shutil.rmtree(tmp, ignore_errors=True)
        sys.modules.pop("keyring", None); sys.modules.pop("app", None)


def test_api_dry_run_has_idempotency_and_no_upload():
    if not _FFMPEG:
        return
    sec = _write_secrets(); _install_fake_keyring()
    os.environ["CLIPFORGE_ENABLE_YOUTUBE_UPLOAD"] = "true"
    os.environ["CLIPFORGE_ENABLE_YOUTUBE_OAUTH"] = "true"
    os.environ["CLIPFORGE_YOUTUBE_CLIENT_SECRETS"] = sec
    client, tmp, app_module, pid = _make_client()
    called = {"n": 0}
    app_module._youtube_upload_uploader = lambda c, b, m: called.__setitem__("n", called["n"] + 1) or {"id": "X"}
    app_module._youtube_upload_credentials_loader = lambda c, p, s: _FakeCreds(valid=True)
    try:
        client.post(f"/api/jobs/upljob0001/publishing/{pid}/validate")
        r = client.post(f"/api/jobs/upljob0001/publishing/{pid}/youtube/dry-run")
        assert r.status_code == 200, r.text
        ur = r.json()["upload_readiness"]
        assert "idempotency_state" in ur and ur["idempotency_state"] == "never_attempted"
        assert "can_attempt_private_upload" in ur
        assert called["n"] == 0  # Dry-Run löst KEINEN Upload aus
        assert load_draft(os.path.join(tmp, "jobs", "upljob0001"), pid)["external_post_id"] is None
    finally:
        for k in ("CLIPFORGE_ENABLE_YOUTUBE_UPLOAD", "CLIPFORGE_ENABLE_YOUTUBE_OAUTH",
                  "CLIPFORGE_YOUTUBE_CLIENT_SECRETS", "CLIPFORGE_JOBS_DIR"):
            os.environ.pop(k, None)
        os.unlink(sec); shutil.rmtree(tmp, ignore_errors=True)
        sys.modules.pop("keyring", None); sys.modules.pop("app", None)


def test_api_publish_path_traversal_blocked():
    if not _FFMPEG:
        return
    sec = _write_secrets(); _install_fake_keyring()
    client, tmp, app_module, pid = _make_client()
    try:
        r = client.post(
            "/api/jobs/upljob0001/publishing/..%2F..%2Fx/youtube/publish",
            json={"confirm": "UPLOAD_PRIVATE", "privacy_status": "private"})
        assert r.status_code in (400, 404), r.status_code
    finally:
        os.environ.pop("CLIPFORGE_JOBS_DIR", None)
        os.unlink(sec); shutil.rmtree(tmp, ignore_errors=True)
        sys.modules.pop("keyring", None); sys.modules.pop("app", None)


# ==========================================================================
# Prompt 28: Retry/Backoff, Attempt-History, upload-status, Real-Test-Gate
# ==========================================================================

# ---------------------- RetryPolicy ---------------------------------------

def test_retrypolicy_classifies_5xx_and_ratelimit_retryable():
    p = YouTubeRetryPolicy(jitter_enabled=False)
    for s in (500, 502, 503, 504, 429):
        assert p.classify_retryability(_http(status=s)) == RETRYABLE, s
    assert p.classify_retryability(_http(status=403, reason="rateLimitExceeded")) == RETRYABLE
    assert p.classify_retryability(TimeoutError("x")) == RETRYABLE


def test_retrypolicy_quota_and_permission_not_retryable():
    p = YouTubeRetryPolicy(jitter_enabled=False)
    assert p.classify_retryability(_http(status=403, reason="quotaExceeded")) == NON_RETRYABLE
    assert p.classify_retryability(_http(status=403, reason="forbidden")) == NON_RETRYABLE
    assert p.classify_retryability(_http(status=400)) == NON_RETRYABLE
    assert p.classify_retryability(ValueError("x")) == NON_RETRYABLE


def test_retrypolicy_401_auth_refreshable_and_uncertain():
    p = YouTubeRetryPolicy(jitter_enabled=False)
    assert p.classify_retryability(_http(status=401)) == AUTH_REFRESHABLE
    assert p.classify_retryability(UploadUncertain()) == UNCERTAIN


def test_retrypolicy_backoff_and_jitter_and_max_attempts():
    p = YouTubeRetryPolicy(max_attempts=4, initial_delay_seconds=1.0,
                           max_delay_seconds=8.0, multiplier=2.0, jitter_enabled=False)
    assert p.calculate_delay(1) == 1.0
    assert p.calculate_delay(2) == 2.0
    assert p.calculate_delay(3) == 4.0
    assert p.calculate_delay(10) == 8.0  # gedeckelt
    # Jitter injizierbar (deterministisch)
    pj = YouTubeRetryPolicy(jitter_enabled=True, jitter_fn=lambda: 0.25,
                            initial_delay_seconds=4.0, multiplier=1.0)
    assert pj.calculate_delay(1) == 1.0  # 0.25 * 4
    # should_retry respektiert max_attempts
    e = _http(status=503)
    assert p.should_retry(e, 1) is True
    assert p.should_retry(e, 4) is False
    assert p.should_retry(_http(status=403, reason="quotaExceeded"), 1) is False


# ---------------------- Retry-Loop im Upload ------------------------------

def test_retry_after_5xx_then_success():
    if not _FFMPEG:
        return
    jd, pid = _make_job(); _install_fake_keyring(); sec = _write_secrets()
    slept = []
    try:
        factory = lambda c, b, m: _ScriptedSession([
            _http(status=503), _http(status=503),
            {"id": "VID_R", "status": {"privacyStatus": "private"}},
        ])
        svc = _svc(_settings(secrets=sec), sec, session_factory=factory,
                   sleep_fn=lambda d: slept.append(d),
                   retry_policy=YouTubeRetryPolicy(max_attempts=5, jitter_enabled=False))
        r = svc.upload_private(jd, pid, load_draft(jd, pid), confirm="UPLOAD_PRIVATE")
        assert r["success"] is True and r["retry_count"] == 2
        assert slept == [1.0, 2.0]  # kontrolliertes Backoff (kein echtes Sleep)
        hist = load_draft(jd, pid)["publish_attempts"]
        assert hist[-1]["outcome"] == "succeeded" and hist[-1]["retry_count"] == 2
    finally:
        sys.modules.pop("keyring", None); os.unlink(sec); shutil.rmtree(jd)


def test_max_attempts_exhausted_is_uncertain():
    if not _FFMPEG:
        return
    jd, pid = _make_job(); _install_fake_keyring(); sec = _write_secrets()
    slept = []
    try:
        factory = lambda c, b, m: _ScriptedSession([_http(status=503)] * 10)
        svc = _svc(_settings(secrets=sec), sec, session_factory=factory,
                   sleep_fn=lambda d: slept.append(d),
                   retry_policy=YouTubeRetryPolicy(max_attempts=3, jitter_enabled=False))
        r = svc.upload_private(jd, pid, load_draft(jd, pid), confirm="UPLOAD_PRIVATE")
        assert r["error_code"] == "upload_result_uncertain"
        assert r["idempotency_state"] == "uncertain" and r["retry_count"] == 2
        assert len(slept) == 2  # attempt<max: 2 Retries
        assert load_draft(jd, pid)["external_post_id"] is None
    finally:
        sys.modules.pop("keyring", None); os.unlink(sec); shutil.rmtree(jd)


def test_quota_not_retried():
    if not _FFMPEG:
        return
    jd, pid = _make_job(); _install_fake_keyring(); sec = _write_secrets()
    slept = []
    try:
        factory = lambda c, b, m: _ScriptedSession(
            [_http(status=403, reason="quotaExceeded")] * 5)
        svc = _svc(_settings(secrets=sec), sec, session_factory=factory,
                   sleep_fn=lambda d: slept.append(d))
        r = svc.upload_private(jd, pid, load_draft(jd, pid), confirm="UPLOAD_PRIVATE")
        assert r["error_code"] == "quota_exceeded" and r["retry_count"] == 0
        assert slept == []  # kein aggressiver Retry
    finally:
        sys.modules.pop("keyring", None); os.unlink(sec); shutil.rmtree(jd)


def test_permission_not_retried():
    if not _FFMPEG:
        return
    jd, pid = _make_job(); _install_fake_keyring(); sec = _write_secrets()
    slept = []
    try:
        factory = lambda c, b, m: _ScriptedSession(
            [_http(status=403, reason="forbidden")] * 5)
        svc = _svc(_settings(secrets=sec), sec, session_factory=factory,
                   sleep_fn=lambda d: slept.append(d))
        r = svc.upload_private(jd, pid, load_draft(jd, pid), confirm="UPLOAD_PRIVATE")
        assert r["error_code"] == "permission_denied" and slept == []
    finally:
        sys.modules.pop("keyring", None); os.unlink(sec); shutil.rmtree(jd)


def test_401_triggers_single_refresh_then_success():
    if not _FFMPEG:
        return
    jd, pid = _make_job(); _install_fake_keyring(); sec = _write_secrets()
    refreshed = {"n": 0}
    # 2 Sessions: erste wirft 401, zweite (nach Refresh) liefert Erfolg.
    sessions = [
        _ScriptedSession([_http(status=401)]),
        _ScriptedSession([{"id": "VID_A", "status": {"privacyStatus": "private"}}]),
    ]
    try:
        def refresher(creds):
            refreshed["n"] += 1
            creds.valid = True
            creds.token = "NEW_ACCESS_zzz"
        svc = _svc(_settings(secrets=sec), sec,
                   loader=lambda c, p, s: _FakeCreds(valid=True),
                   refresher=refresher,
                   session_factory=lambda c, b, m: sessions.pop(0))
        r = svc.upload_private(jd, pid, load_draft(jd, pid), confirm="UPLOAD_PRIVATE")
        assert r["success"] is True and refreshed["n"] == 1
        _assert_no_secret_values(r, "NEW_ACCESS_zzz", _SENTINEL_REFRESH)
    finally:
        sys.modules.pop("keyring", None); os.unlink(sec); shutil.rmtree(jd)


def test_401_twice_is_invalid_credentials_single_refresh():
    if not _FFMPEG:
        return
    jd, pid = _make_job(); _install_fake_keyring(); sec = _write_secrets()
    refreshed = {"n": 0}
    sessions = [_ScriptedSession([_http(status=401)]),
                _ScriptedSession([_http(status=401)])]
    try:
        def refresher(creds):
            refreshed["n"] += 1
            creds.valid = True
        svc = _svc(_settings(secrets=sec), sec,
                   loader=lambda c, p, s: _FakeCreds(valid=True),
                   refresher=refresher,
                   session_factory=lambda c, b, m: sessions.pop(0))
        r = svc.upload_private(jd, pid, load_draft(jd, pid), confirm="UPLOAD_PRIVATE")
        assert r["error_code"] == "invalid_credentials" and refreshed["n"] == 1
        assert load_draft(jd, pid)["external_post_id"] is None
    finally:
        sys.modules.pop("keyring", None); os.unlink(sec); shutil.rmtree(jd)


def test_tests_never_sleep_for_real():
    """Guard: der Default-sleep_fn in Tests ist ein No-op (kein time.sleep)."""
    if not _FFMPEG:
        return
    jd, pid = _make_job(); _install_fake_keyring(); sec = _write_secrets()
    import time as _t
    try:
        factory = lambda c, b, m: _ScriptedSession([
            _http(status=503), {"id": "V", "status": {"privacyStatus": "private"}}])
        svc = _svc(_settings(secrets=sec), sec, session_factory=factory,
                   retry_policy=YouTubeRetryPolicy(initial_delay_seconds=5.0,
                                                   jitter_enabled=False))
        t0 = _t.time()
        r = svc.upload_private(jd, pid, load_draft(jd, pid), confirm="UPLOAD_PRIVATE")
        assert r["success"] is True
        assert _t.time() - t0 < 1.0  # trotz 5s-Delay: kein echtes Sleep
    finally:
        sys.modules.pop("keyring", None); os.unlink(sec); shutil.rmtree(jd)


# ---------------------- Attempt-History + upload-status -------------------

def test_attempt_history_records_and_no_secrets():
    if not _FFMPEG:
        return
    jd, pid = _make_job(); _install_fake_keyring(); sec = _write_secrets()
    try:
        # 1) eindeutiger Fehler (permission) → failed
        f1 = lambda c, b, m: _ScriptedSession([_http(status=403, reason="forbidden")])
        svc1 = _svc(_settings(secrets=sec), sec, session_factory=f1)
        svc1.upload_private(jd, pid, load_draft(jd, pid), confirm="UPLOAD_PRIVATE")
        # 2) Retry → Erfolg
        f2 = lambda c, b, m: _ScriptedSession([{"id": "VID", "status": {"privacyStatus": "private"}}])
        svc2 = _svc(_settings(secrets=sec), sec, session_factory=f2)
        svc2.upload_private(jd, pid, load_draft(jd, pid), confirm="UPLOAD_PRIVATE")
        d = load_draft(jd, pid)
        hist = d["publish_attempts"]
        assert len(hist) == 2
        assert hist[0]["outcome"] == "failed" and hist[0]["error_code"] == "permission_denied"
        assert hist[1]["outcome"] == "succeeded"
        for h in hist:
            assert set(h.keys()) <= {"attempt_id", "started_at", "completed_at",
                                     "outcome", "error_code", "retry_count"}
        _assert_no_secret_values(d, _SENTINEL_ACCESS, _SENTINEL_REFRESH, _SENTINEL_SECRET)
    finally:
        sys.modules.pop("keyring", None); os.unlink(sec); shutil.rmtree(jd)


def test_upload_status_reports_recovery_flags():
    if not _FFMPEG:
        return
    jd, pid = _make_job(); _install_fake_keyring(); sec = _write_secrets()
    try:
        svc = _svc(_settings(secrets=sec), sec)
        # frischer Draft
        st = svc.upload_status(load_draft(jd, pid))
        assert st["can_retry"] is True and st["requires_manual_check"] is False
        assert st["requires_reauth"] is False and st["no_secrets"] is True
        # uncertain → manual check, kein Retry
        from clipforge.publishing import apply_publish_state
        apply_publish_state(jd, pid, {"status": "failed", "idempotency_state": "uncertain",
                                      "last_publish_error": "upload_result_uncertain"})
        st = svc.upload_status(load_draft(jd, pid))
        assert st["requires_manual_check"] is True and st["can_retry"] is False
        # reauth-Fehler → requires_reauth
        apply_publish_state(jd, pid, {"status": "failed", "idempotency_state": "failed",
                                      "last_publish_error": "invalid_credentials"})
        st = svc.upload_status(load_draft(jd, pid))
        assert st["requires_reauth"] is True and st["can_retry"] is True
    finally:
        sys.modules.pop("keyring", None); os.unlink(sec); shutil.rmtree(jd)


def test_api_upload_status_endpoint():
    if not _FFMPEG:
        return
    sec = _write_secrets(); _install_fake_keyring()
    client, tmp, app_module, pid = _make_client()
    try:
        r = client.get(f"/api/jobs/upljob0001/publishing/{pid}/youtube/upload-status")
        assert r.status_code == 200, r.text
        body = r.json()
        assert body["idempotency_state"] == "never_attempted"
        assert body["can_retry"] is True and body["no_secrets"] is True
        assert "attempt_history_summary" in body
        _assert_no_secret_values(body)
    finally:
        os.environ.pop("CLIPFORGE_JOBS_DIR", None)
        os.unlink(sec); shutil.rmtree(tmp, ignore_errors=True)
        sys.modules.pop("keyring", None); sys.modules.pop("app", None)


# ---------------------- Real-Test-Gate ------------------------------------

def test_real_test_gate_requires_both_flags_and_prereqs():
    if not _FFMPEG:
        return
    jd, pid = _make_job(); _install_fake_keyring(); sec = _write_secrets()
    try:
        # ohne Real-Test-Flag → nicht ready (auch wenn Upload-Flag an)
        svc = _svc(_settings(enabled=True, secrets=sec), sec)
        ok, reasons = svc.real_test_ready(load_draft(jd, pid))
        assert ok is False and "real_test_flag_missing" in reasons
        # beide Flags an → ready
        s2 = Settings(enable_youtube_upload=True, enable_youtube_oauth=True,
                      enable_youtube_real_test=True, youtube_client_secrets_file=sec)
        svc2 = YouTubeUploadService(s2)
        ok2, reasons2 = svc2.real_test_ready(load_draft(jd, pid))
        assert ok2 is True and reasons2 == []
    finally:
        sys.modules.pop("keyring", None); os.unlink(sec); shutil.rmtree(jd)


def test_real_test_gate_without_token_not_ready():
    if not _FFMPEG:
        return
    jd, pid = _make_job(); _install_fake_keyring(payload=None); sec = _write_secrets()
    try:
        s = Settings(enable_youtube_upload=True, enable_youtube_oauth=True,
                     enable_youtube_real_test=True, youtube_client_secrets_file=sec)
        ok, reasons = YouTubeUploadService(s).real_test_ready(load_draft(jd, pid))
        assert ok is False and "token_missing" in reasons
    finally:
        sys.modules.pop("keyring", None); os.unlink(sec); shutil.rmtree(jd)


def test_real_test_gate_without_keyring_not_ready():
    if not _FFMPEG:
        return
    jd, pid = _make_job(); sys.modules.pop("keyring", None); sec = _write_secrets()
    try:
        s = Settings(enable_youtube_upload=True, enable_youtube_oauth=True,
                     enable_youtube_real_test=True, youtube_client_secrets_file=sec)
        ok, reasons = YouTubeUploadService(s).real_test_ready(load_draft(jd, pid))
        assert ok is False and ("token_missing" in reasons or "oauth_not_ready" in reasons)
    finally:
        os.unlink(sec); shutil.rmtree(jd)


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
