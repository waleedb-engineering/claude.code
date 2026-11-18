"""Direktveröffentlichung TikTok/Instagram/X, Planung mit Freigabe.
Nur gegen nachgebildete Plattform-Antworten — nie ein echter Aufruf."""

from __future__ import annotations

import datetime
import json
import urllib.parse

import pytest

from clipforge.publishing import apply_publish_state, load_draft
from clipforge.studio import accounts
from studio_helpers import clear_env, make_client, wait_task

SCRIPT = "Lokale Videotools sparen Zeit. Alles bleibt auf deinem Rechner. Folge für mehr."
ENV = ("TIKTOK_CLIENT_KEY", "TIKTOK_CLIENT_SECRET", "INSTAGRAM_APP_ID", "INSTAGRAM_APP_SECRET",
       "X_CLIENT_ID", "X_CLIENT_SECRET", "CLIPFORGE_TIKTOK_DIRECT_POST")


class Fake:
    def __init__(self):
        self.calls = []
        self.ig_status = ["IN_PROGRESS", "FINISHED"]
        self.fail_publish = False

    def http(self, method, url, headers, body=None, timeout=120.0):
        self.calls.append((method, url, headers, body))
        u = urllib.parse.urlsplit(url)
        j = lambda d, c=200: (c, json.dumps(d).encode())  # noqa: E731
        # --- OAuth
        if url == "https://open.tiktokapis.com/v2/oauth/token/":
            return j({"access_token": "tt-at", "refresh_token": "tt-rt", "open_id": "tt-user",
                      "scope": "user.info.basic,video.upload,video.publish", "expires_in": 86400,
                      "refresh_expires_in": 3e7})
        if url == "https://api.instagram.com/oauth/access_token":
            return j({"access_token": "ig-short", "user_id": 1789})
        if u.path == "/access_token" and u.netloc == "graph.instagram.com":
            assert "ig_exchange_token" in u.query
            return j({"access_token": "ig-long", "token_type": "bearer", "expires_in": 5184000})
        if url == "https://api.x.com/2/oauth2/token":
            assert headers["Authorization"].startswith("Basic ")
            return j({"access_token": "x-at", "refresh_token": "x-rt", "expires_in": 7200,
                      "scope": "tweet.write media.write offline.access"})
        # --- TikTok
        if url.endswith("/creator_info/query/"):
            return j({"data": {"creator_nickname": "me", "privacy_level_options":
                               ["SELF_ONLY", "MUTUAL_FOLLOW_FRIENDS"],
                               "max_video_post_duration_sec": 600}, "error": {"code": "ok"}})
        if url.endswith("/post/publish/video/init/"):
            return j({"data": {"publish_id": "p_direct_1",
                               "upload_url": "https://open-upload.tiktokapis.com/u/2"},
                      "error": {"code": "ok"}})
        if method == "PUT":
            return 201, b""
        if url.endswith("/status/fetch/"):
            return j({"data": {"status": "PUBLISH_COMPLETE", "publicaly_available_post_id": [7311]},
                      "error": {"code": "ok"}})
        # --- Instagram
        if u.netloc == "graph.instagram.com" and u.path.endswith("/1789/media"):
            q = urllib.parse.parse_qs(u.query)
            assert q["media_type"] == ["REELS"] and q["upload_type"] == ["resumable"]
            return j({"id": "c55", "uri": "https://rupload.facebook.com/ig-api-upload/v24.0/c55"})
        if u.netloc == "rupload.facebook.com":
            assert headers["Authorization"] == "OAuth ig-long" and headers["offset"] == "0"
            return j({"success": True})
        if u.path.endswith("/c55"):
            return j({"status_code": self.ig_status.pop(0) if self.ig_status else "FINISHED"})
        if u.path.endswith("/media_publish"):
            if self.fail_publish:
                return j({"error": {"message": "Rate limit", "code": 4}}, 400)
            return j({"id": "ig-media-9"})
        if u.path.endswith("/ig-media-9"):
            return j({"like_count": 3, "comments_count": 1, "permalink": "https://www.instagram.com/reel/x/"})
        # --- X
        if url == "https://api.x.com/2/media/upload/initialize":
            return j({"data": {"id": "m77"}})
        if url == "https://api.x.com/2/media/upload/m77/append":
            assert b'name="segment_index"' in body
            return 204, b""
        if url == "https://api.x.com/2/media/upload/m77/finalize":
            return j({"data": {"id": "m77", "processing_info": {"state": "pending", "check_after_secs": 1}}})
        if url.startswith("https://api.x.com/2/media/upload?command=STATUS"):
            return j({"data": {"processing_info": {"state": "succeeded"}}})
        if url == "https://api.x.com/2/tweets":
            data = json.loads(body)
            assert data["media"]["media_ids"] == ["m77"] and len(data["text"]) <= 280
            return j({"data": {"id": "1900", "text": data["text"]}}, 201)
        return 404, b"{}"


@pytest.fixture
def env(tmp_path, monkeypatch):
    fake = Fake()
    monkeypatch.setattr(accounts, "HTTP", fake.http)
    monkeypatch.setattr(accounts, "SLEEP", lambda s: None)
    client, app_module = make_client(str(tmp_path), TIKTOK_CLIENT_KEY="k", TIKTOK_CLIENT_SECRET="s",
                                     INSTAGRAM_APP_ID="ig", INSTAGRAM_APP_SECRET="igs",
                                     X_CLIENT_ID="xid", X_CLIENT_SECRET="xs",
                                     CLIPFORGE_TIKTOK_DIRECT_POST="1")
    yield client, fake, app_module
    clear_env(*ENV)


def _connect(client, platform):
    r = client.post(f"/api/studio/accounts/{platform}/connect")
    assert r.status_code == 200, r.text
    q = urllib.parse.parse_qs(urllib.parse.urlsplit(r.json()["auth_url"]).query)
    cb = client.get(f"/api/studio/accounts/{platform}/callback",
                    params={"code": "c", "state": q["state"][0]}, follow_redirects=False)
    assert cb.status_code in (302, 303, 307), cb.text
    return q


def _draft(client, platform, **fields):
    r = client.post("/api/studio/projects", json={"workflow": "script", "script": SCRIPT,
                                                  "voice": {"provider": "mock"}, "resolution": "720p"}).json()
    pid = r["project"]["id"]
    wait_task(client, r["task_id"])
    wait_task(client, client.post(f"/api/studio/projects/{pid}/render", json={"mode": "final"}).json()["task"]["id"])
    job = client.post(f"/api/studio/projects/{pid}/export", json={}).json()["job_id"]
    pub = client.post(f"/api/jobs/{job}/publishing", json={
        "platform": platform, "source_type": "auto_clip", "source_clip_index": 1,
        "title": "Mein Titel", "hashtags": ["clipforge", "#lokal"], **fields}).json()["publishing_id"]
    return job, pub


def test_oauth_flavours(env):
    client, fake, _ = env
    q = _connect(client, "instagram")
    assert q["scope"] == ["instagram_business_basic,instagram_business_content_publish,"
                          "instagram_business_manage_insights"]
    assert "code_challenge" not in q and q["client_id"] == ["ig"]
    q = _connect(client, "x")
    assert q["scope"] == ["tweet.read tweet.write users.read media.write offline.access"]
    assert q["code_challenge_method"] == ["S256"]
    q = _connect(client, "tiktok")
    assert "video.publish" in q["scope"][0]
    accts = {a["platform"]: a for a in client.get("/api/studio/accounts").json()["accounts"]}
    assert accts["instagram"]["state"] == "connected" and accts["instagram"]["account"] == "1789"
    assert accts["x"]["state"] == "connected"
    assert "ig-long" not in json.dumps(accts) and "x-at" not in json.dumps(accts)


def test_instagram_publish_needs_confirm_and_publishes(env):
    client, fake, _ = env
    _connect(client, "instagram")
    job, pub = _draft(client, "instagram_reels")
    r = client.post(f"/api/studio/publishing/{job}/{pub}/publish", json={})
    assert r.status_code == 400 and r.json()["detail"]["code"] == "confirmation_required"
    assert not any("graph.instagram.com/v" in c[1] for c in fake.calls)
    r = client.post(f"/api/studio/publishing/{job}/{pub}/publish", json={"confirm": True})
    assert r.status_code == 202, r.text
    task = wait_task(client, r.json()["task"]["id"])
    assert task["status"] == "succeeded", task
    d = load_draft(_job_dir(env, job), pub)
    assert d["status"] == "published" and d["external_post_id"] == "ig-media-9"
    assert d["external_url"].startswith("https://www.instagram.com/")
    caption = urllib.parse.parse_qs(urllib.parse.urlsplit(
        next(c[1] for c in fake.calls if c[1].split("?")[0].endswith("/1789/media"))).query)["caption"][0]
    assert "Mein Titel" in caption and "#clipforge #lokal" in caption
    again = client.post(f"/api/studio/publishing/{job}/{pub}/publish", json={"confirm": True}).json()
    assert again["already"] is True                 # kein Doppel-Post


def _job_dir(env, job_id):
    return env[2].app.state.registry.get(job_id).job_dir if hasattr(env[2].app.state, "registry") \
        else env[2].studio.registry.get(job_id).job_dir


def test_instagram_failure_is_not_retried(env):
    client, fake, _ = env
    fake.fail_publish = True
    _connect(client, "instagram")
    job, pub = _draft(client, "instagram_reels")
    task = wait_task(client, client.post(f"/api/studio/publishing/{job}/{pub}/publish",
                                         json={"confirm": True}).json()["task"]["id"])
    assert task["status"] == "failed" and "Rate limit" in task["error"]["message"]
    assert load_draft(_job_dir(env, job), pub)["status"] == "failed"
    r = client.post(f"/api/studio/tasks/{task['id']}/retry")
    assert r.status_code == 409 and r.json()["detail"]["code"] == "retry_not_allowed"


def test_x_requires_cost_confirmation(env):
    client, fake, _ = env
    _connect(client, "x")
    job, pub = _draft(client, "x")
    r = client.post(f"/api/studio/publishing/{job}/{pub}/publish", json={"confirm": True})
    assert r.status_code == 402 and r.json()["detail"]["details"]["estimated_usd"] > 0
    r = client.post(f"/api/studio/publishing/{job}/{pub}/publish",
                    json={"confirm": True, "confirm_cost": True})
    task = wait_task(client, r.json()["task"]["id"])
    assert task["status"] == "succeeded", task
    d = load_draft(_job_dir(env, job), pub)
    assert d["external_url"] == "https://x.com/i/status/1900"
    plat = {p["platform"]: p for p in client.get("/api/studio/publishing/platforms").json()["platforms"]}
    assert plat["x"]["state"] == "ready" and plat["x"]["cost_per_post_usd"] > 0


def test_tiktok_direct_post_respects_creator_privacy_options(env):
    client, fake, _ = env
    _connect(client, "tiktok")
    info = client.get("/api/studio/publishing/tiktok/creator-info").json()
    assert info["privacy_level_options"] == ["SELF_ONLY", "MUTUAL_FOLLOW_FRIENDS"]
    job, pub = _draft(client, "tiktok")
    r = client.post(f"/api/studio/publishing/{job}/{pub}/publish", json={"confirm": True})
    assert r.status_code == 400   # Sichtbarkeit fehlt
    r = client.post(f"/api/studio/publishing/{job}/{pub}/publish",
                    json={"confirm": True, "options": {"privacy_level": "PUBLIC_TO_EVERYONE"}})
    task = wait_task(client, r.json()["task"]["id"])
    assert task["status"] == "failed" and "erlaubt TikTok" in task["error"]["message"]
    apply_publish_state(_job_dir(env, job), pub, {"status": "draft"})
    r = client.post(f"/api/studio/publishing/{job}/{pub}/publish",
                    json={"confirm": True, "options": {"privacy_level": "SELF_ONLY"}})
    assert r.status_code == 202, r.text
    task = wait_task(client, r.json()["task"]["id"])
    assert task["status"] == "succeeded", task["error"]
    init = next(c for c in fake.calls if c[1].endswith("/post/publish/video/init/"))
    body = json.loads(init[3])
    assert body["post_info"]["privacy_level"] == "SELF_ONLY" and "#clipforge" in body["post_info"]["title"]
    d = load_draft(_job_dir(env, job), pub)
    assert d["status"] == "published" and d["external_post_id"] == "p_direct_1"


def test_schedule_requires_approval_and_fires_once(env):
    client, fake, app_module = env
    _connect(client, "instagram")
    job, pub = _draft(client, "instagram_reels")
    future = (datetime.datetime.now(datetime.timezone.utc) + datetime.timedelta(hours=1)).isoformat()
    r = client.post(f"/api/studio/publishing/{job}/{pub}/schedule", json={"at": future})
    assert r.status_code == 400
    r = client.post(f"/api/studio/publishing/{job}/{pub}/schedule", json={"at": future, "approve": True})
    assert r.status_code == 200 and r.json()["draft"]["auto_publish"]["approved_at"]
    studio = app_module.studio
    studio.tick()
    assert load_draft(_job_dir(env, job), pub)["status"] == "scheduled"   # noch nicht fällig
    apply_publish_state(_job_dir(env, job), pub, {"scheduled_at": "2000-01-01T00:00:00+00:00"})
    studio.tick()
    for t in studio.service.tasks.list(limit=50):
        if t["kind"] == "publish_direct":
            wait_task(client, t["id"])
    d = load_draft(_job_dir(env, job), pub)
    assert d["status"] == "published" and d["publish_approval"]["source"] == "zeitplan"
    studio.tick()   # erneuter Tick postet nicht noch einmal
    assert sum(1 for c in fake.calls if c[1].split("?")[0].endswith("/media_publish")) == 1
