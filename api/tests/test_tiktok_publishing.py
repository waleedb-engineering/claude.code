"""TikTok: Kontoverbindung (OAuth + PKCE) und Upload in die TikTok-Entwürfe.
Gegen nachgebildete TikTok-Antworten — nie ein echter Aufruf."""

from __future__ import annotations

import base64
import hashlib
import json
import os
import shutil
import stat
import tempfile
import urllib.parse

from studio_helpers import clear_env, make_client, run_all, wait_task

from clipforge.studio import accounts

SCRIPT = "Lokale Videotools sparen Zeit. Alles bleibt auf deinem Rechner. Folge für mehr."
ENV = ("TIKTOK_CLIENT_KEY", "TIKTOK_CLIENT_SECRET", "CLIPFORGE_SECRET_KEY")


class FakeTikTok:
    def __init__(self, status="SEND_TO_USER_INBOX", put_failures=0):
        self.calls = []
        self.status = status
        self.put_failures = put_failures
        self.uploaded = 0
        self.ranges = []

    def http(self, method, url, headers, body=None, timeout=120.0):
        self.calls.append((method, url, headers, body))
        if url.endswith("/oauth/token/"):
            form = urllib.parse.parse_qs(body.decode())
            if form["grant_type"] == ["refresh_token"]:
                return 200, json.dumps({"access_token": "sentinel-at-2", "refresh_token": "sentinel-rt-2",
                                        "expires_in": 86400, "refresh_expires_in": 31536000}).encode()
            return 200, json.dumps({"access_token": "sentinel-at", "refresh_token": "sentinel-rt",
                                    "open_id": "user-123", "scope": "video.upload",
                                    "expires_in": 86400, "refresh_expires_in": 31536000}).encode()
        if url.endswith("/inbox/video/init/"):
            return 200, json.dumps({"data": {"publish_id": "v_inbox_1",
                                             "upload_url": "https://open-upload.tiktokapis.com/u/1"},
                                    "error": {"code": "ok"}}).encode()
        if method == "PUT":
            if self.put_failures:
                self.put_failures -= 1
                return 503, b""
            self.uploaded += len(body)
            self.ranges.append(headers["Content-Range"])
            return 201, b""
        if url.endswith("/status/fetch/"):
            return 200, json.dumps({"data": {"status": self.status}, "error": {"code": "ok"}}).encode()
        return 404, b""


def _connect(client, fake):
    r = client.post("/api/studio/accounts/tiktok/connect")
    assert r.status_code == 200, r.text
    q = urllib.parse.parse_qs(urllib.parse.urlsplit(r.json()["auth_url"]).query)
    r = client.get("/api/studio/accounts/tiktok/callback",
                   params={"code": "abc", "state": q["state"][0]}, follow_redirects=False)
    assert r.status_code == 303 and r.headers["location"].endswith("result=ok"), r.headers
    return q


def _exported_draft(client):
    r = client.post("/api/studio/projects", json={"workflow": "script", "script": SCRIPT,
                                                  "voice": {"provider": "mock"}, "resolution": "720p"}).json()
    pid = r["project"]["id"]
    wait_task(client, r["task_id"])
    wait_task(client, client.post(f"/api/studio/projects/{pid}/render", json={"mode": "final"}).json()["task"]["id"])
    job = client.post(f"/api/studio/projects/{pid}/export", json={}).json()["job_id"]
    pub = client.post(f"/api/jobs/{job}/publishing", json={
        "platform": "tiktok", "source_type": "auto_clip", "source_clip_index": 1}).json()["publishing_id"]
    return job, pub


def test_oauth_uses_pkce_and_stores_tokens_safely():
    tmp = tempfile.mkdtemp(prefix="tt_")
    fake = FakeTikTok()
    try:
        accounts.HTTP = fake.http
        client, _ = make_client(tmp)
        st = client.get("/api/studio/accounts").json()
        assert st["accounts"][0]["state"] == "not_configured"
        assert {a["platform"] for a in st["accounts"]} == {"tiktok", "instagram", "x"}
        r = client.post("/api/studio/accounts/tiktok/connect")
        assert r.status_code == 409 and r.json()["detail"]["code"] == "platform_not_configured"
        os.environ.update(TIKTOK_CLIENT_KEY="ck-test", TIKTOK_CLIENT_SECRET="sentinel-secret")
        q = _connect(client, fake)
        assert q["scope"] == ["user.info.basic,video.upload"] and q["code_challenge_method"] == ["S256"]
        token_call = next(c for c in fake.calls if c[1].endswith("/oauth/token/"))
        form = urllib.parse.parse_qs(token_call[3].decode())
        verifier = form["code_verifier"][0]
        expected = base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest()).decode().rstrip("=")
        assert q["code_challenge"] == [expected]                   # PKCE stimmt
        st = client.get("/api/studio/accounts").json()["accounts"][0]
        assert st["state"] == "connected" and st["account"] == "user-123"
        assert "sentinel" not in json.dumps(st)
        path = os.path.join(tmp, "studio", "accounts", "tiktok.json")
        assert stat.S_IMODE(os.stat(path).st_mode) == 0o600
        # derselbe state darf nicht zweimal funktionieren
        r = client.get("/api/studio/accounts/tiktok/callback",
                       params={"code": "abc", "state": q["state"][0]}, follow_redirects=False)
        assert r.headers["location"].endswith("result=oauth_state_invalid")
        r = client.get("/api/studio/accounts/tiktok/callback", params={"error": "access_denied"},
                       follow_redirects=False)
        assert "oauth_denied" in r.headers["location"]
        # verschlüsselt, sobald ein Server-Schlüssel gesetzt ist
        os.environ["CLIPFORGE_SECRET_KEY"] = "z" * 40
        _connect(client, fake)
        assert b"sentinel" not in open(path, "rb").read()
        assert accounts.access_token("tiktok") == "sentinel-at"
        assert client.delete("/api/studio/accounts/tiktok").json() == {"disconnected": True}
        assert client.get("/api/studio/accounts").json()["accounts"][0]["state"] == "not_connected"
        assert client.post("/api/studio/accounts/myspace/connect").status_code == 404
    finally:
        accounts.HTTP = accounts._http
        clear_env(*ENV)
        shutil.rmtree(tmp, ignore_errors=True)


def test_upload_needs_confirmation_and_lands_in_tiktok_drafts():
    tmp = tempfile.mkdtemp(prefix="tt_")
    fake = FakeTikTok(put_failures=1)
    try:
        accounts.HTTP = fake.http
        accounts.SLEEP = lambda s: None
        client, _ = make_client(tmp, TIKTOK_CLIENT_KEY="ck-test", TIKTOK_CLIENT_SECRET="sentinel-secret")
        job, pub = _exported_draft(client)
        base = f"/api/studio/publishing/{job}/{pub}/tiktok"
        r = client.post(base, json={"confirm": True})
        assert r.status_code == 409 and r.json()["detail"]["code"] == "platform_not_connected"
        _connect(client, fake)
        r = client.post(base, json={})
        assert r.status_code == 400 and r.json()["detail"]["code"] == "confirmation_required"
        assert not any("/inbox/" in c[1] for c in fake.calls)       # ohne Bestätigung nichts
        r = client.post(base, json={"confirm": True})
        assert r.status_code == 202
        task = wait_task(client, r.json()["task"]["id"])
        assert task["status"] == "succeeded", task
        assert task["result"] == {"state": "in_tiktok_drafts", "publish_id": "v_inbox_1"}
        size = os.path.getsize(client.get(f"/api/jobs/{job}/publishing/{pub}").json()["mp4_path"])
        assert fake.uploaded == size and fake.ranges == [f"bytes 0-{size - 1}/{size}"]  # 1 Retry
        init = next(c for c in fake.calls if c[1].endswith("/inbox/video/init/"))
        body = json.loads(init[3])
        assert body["source_info"]["video_size"] == size and body["source_info"]["total_chunk_count"] == 1
        assert init[2]["Authorization"] == "Bearer sentinel-at"
        d = client.get(f"/api/jobs/{job}/publishing/{pub}").json()
        assert d["status"] == "publishing" and d["upload_state"] == "in_tiktok_drafts"
        assert d["published_at"] is None                            # NICHT als veröffentlicht gemeldet
        states = {x["publishing_id"]: x["state"] for x in client.get("/api/studio/publishing/drafts").json()["drafts"]}
        assert states[pub] == "in_platform_drafts"
        # zweiter Klick: kein zweiter Upload (idempotent)
        before = len(fake.calls)
        r = client.post(base, json={"confirm": True}).json()
        assert r["already"] and r["task"] is None and len(fake.calls) == before
        # erst wenn TikTok „veröffentlicht“ meldet, wird es so angezeigt
        fake.status = "PUBLISH_COMPLETE"
        res = client.post(f"{base}/status").json()
        assert res["draft"]["status"] == "published" and res["draft"]["publish_source"] == "tiktok"
        assert "sentinel" not in json.dumps(res)
    finally:
        accounts.HTTP = accounts._http
        accounts.SLEEP = __import__("time").sleep
        clear_env(*ENV)
        shutil.rmtree(tmp, ignore_errors=True)


def test_upload_failure_is_recorded_and_wrong_platform_rejected():
    tmp = tempfile.mkdtemp(prefix="tt_")
    fake = FakeTikTok(put_failures=10)
    try:
        accounts.HTTP = fake.http
        accounts.SLEEP = lambda s: None
        client, _ = make_client(tmp, TIKTOK_CLIENT_KEY="ck-test", TIKTOK_CLIENT_SECRET="sentinel-secret")
        job, pub = _exported_draft(client)
        _connect(client, fake)
        task = wait_task(client, client.post(f"/api/studio/publishing/{job}/{pub}/tiktok",
                                             json={"confirm": True}).json()["task"]["id"])
        assert task["status"] == "failed" and task["error"]["code"] == "tiktok_upload_failed"
        d = client.get(f"/api/jobs/{job}/publishing/{pub}").json()
        assert d["status"] == "failed" and d["upload_state"] == "failed"
        assert len([c for c in fake.calls if c[0] == "PUT"]) == 4    # begrenzte Wiederholungen
        yt = client.post(f"/api/jobs/{job}/publishing", json={
            "platform": "youtube_shorts", "source_type": "auto_clip", "source_clip_index": 1}).json()
        r = client.post(f"/api/studio/publishing/{job}/{yt['publishing_id']}/tiktok", json={"confirm": True})
        assert r.status_code == 409 and r.json()["detail"]["code"] == "wrong_platform"
    finally:
        accounts.HTTP = accounts._http
        accounts.SLEEP = __import__("time").sleep
        clear_env(*ENV)
        shutil.rmtree(tmp, ignore_errors=True)


def test_chunk_plan_follows_tiktok_rules():
    mb = 1024 * 1024
    assert accounts.chunk_plan(3 * mb) == [(0, 3 * mb - 1)]
    plan = accounts.chunk_plan(25 * mb)
    assert len(plan) == 2 and plan[0] == (0, 10 * mb - 1) and plan[-1] == (10 * mb, 25 * mb - 1)
    assert plan[-1][1] - plan[-1][0] + 1 == 15 * mb                  # Rest im letzten Stück
    plan = accounts.chunk_plan(30 * mb)
    assert len(plan) == 3 and all(e - s + 1 == 10 * mb for s, e in plan)
    for bad in (0, -1, 5 * 1024 * mb):
        try:
            accounts.chunk_plan(bad)
            raise AssertionError(bad)
        except Exception as exc:  # noqa: BLE001
            assert getattr(exc, "code", "") == "video_size_invalid"


if __name__ == "__main__":
    run_all(globals())
