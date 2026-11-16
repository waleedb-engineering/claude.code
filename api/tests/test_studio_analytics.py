"""Studio: Publishing-Safety, Planung, Analytics ohne erfundene Werte, Remix, Ideen."""

from __future__ import annotations

import shutil
import tempfile

from studio_helpers import clear_env, make_client, run_all, wait_task

SCRIPT = "Lokale Videotools sparen Zeit. Alles bleibt auf deinem Rechner. Folge für mehr."


def _err(resp) -> str:
    return resp.json()["detail"]["code"]


def _exported(client):
    r = client.post("/api/studio/projects", json={
        "workflow": "script", "script": SCRIPT, "voice": {"provider": "mock"},
        "resolution": "720p", "captions": {"style": "bold"}}).json()
    pid = r["project"]["id"]
    wait_task(client, r["task_id"])
    t = wait_task(client, client.post(f"/api/studio/projects/{pid}/render",
                                      json={"mode": "final"}).json()["task"]["id"])
    assert t["status"] == "succeeded", t
    return pid, client.post(f"/api/studio/projects/{pid}/export", json={}).json()["job_id"]


def _draft(client, job_id, platform="tiktok", **extra):
    r = client.post(f"/api/jobs/{job_id}/publishing", json={
        "platform": platform, "source_type": "auto_clip", "source_clip_index": 1, **extra})
    assert r.status_code == 200, r.text
    return r.json()["publishing_id"]


def test_mark_published_requires_explicit_confirmation():
    tmp = tempfile.mkdtemp(prefix="ana_")
    try:
        client, _ = make_client(tmp)
        _, job = _exported(client)
        pub = _draft(client, job)
        url = f"/api/studio/publishing/{job}/{pub}/mark-published"
        for body in ({}, {"confirm": False}, {"url": "https://tiktok.com/@me/video/1"}):
            r = client.post(url, json=body)
            assert r.status_code == 400 and _err(r) == "confirmation_required", body
        assert client.get(f"/api/jobs/{job}/publishing/{pub}").json()["status"] == "draft"
        assert _err(client.post(url, json={"confirm": True, "url": "javascript:alert(1)"})) == "url_invalid"
        assert _err(client.post(url, json={"confirm": True, "published_at": "gestern"})) == "validation_error"
        r = client.post(url, json={"confirm": True, "url": "https://tiktok.com/@me/video/1",
                                   "published_at": "2026-03-01T10:00:00+00:00"})
        d = r.json()["draft"]
        assert d["status"] == "published" and d["publish_source"] == "manual"
        assert d["published_at"] == "2026-03-01T10:00:00+00:00"
        assert d["external_post_id"] is None  # kein vorgetäuschter Plattform-Upload
        again = client.post(url, json={"confirm": True, "url": "https://example.com/other"}).json()["draft"]
        assert again["external_url"] == "https://tiktok.com/@me/video/1"  # idempotent
        # der normale Planner kann „published“ weiterhin NICHT direkt setzen
        r = client.patch(f"/api/jobs/{job}/publishing/{_draft(client, job)}", json={"status": "published"})
        assert r.status_code == 400
        assert client.post(f"/api/studio/publishing/{job}/ffffffffffff/mark-published",
                           json={"confirm": True}).status_code == 404
        assert client.post(f"/api/studio/publishing/nope/{pub}/mark-published",
                           json={"confirm": True}).status_code == 404
    finally:
        clear_env()
        shutil.rmtree(tmp, ignore_errors=True)


def test_scheduler_marks_due_but_never_uploads():
    import datetime
    from clipforge.studio import publish_ops
    tmp = tempfile.mkdtemp(prefix="ana_")
    try:
        client, app_module = make_client(tmp)
        _, job = _exported(client)
        soon = _draft(client, job, "youtube_shorts", scheduled_at="2026-05-01T10:00:00+00:00")
        later = _draft(client, job, "x", scheduled_at="2026-06-01T10:00:00+00:00")
        unscheduled = _draft(client, job, "tiktok")
        for pub in (soon, later):
            assert client.patch(f"/api/jobs/{job}/publishing/{pub}",
                                json={"status": "scheduled"}).status_code == 200
        registry = app_module.registry
        utc = datetime.timezone.utc
        assert publish_ops.scheduler_tick(registry, datetime.datetime(2026, 4, 30, tzinfo=utc)) == []
        due = publish_ops.scheduler_tick(registry, datetime.datetime(2026, 5, 1, 10, 0, tzinfo=utc))
        assert [d["publishing_id"] for d in due] == [soon]
        assert publish_ops.scheduler_tick(registry, datetime.datetime(2026, 5, 2, tzinfo=utc)) == []
        states = {d["publishing_id"]: d for d in client.get("/api/studio/publishing/drafts").json()["drafts"]}
        assert states[soon]["state"] == "due" and states[later]["state"] == "scheduled"
        assert states[unscheduled]["state"] == "not_connected"
        d = client.get(f"/api/jobs/{job}/publishing/{soon}").json()
        assert d["status"] == "scheduled" and d["published_at"] is None
        assert d["external_post_id"] is None and not d.get("upload_state")
        # Worker-Tick der App läuft denselben Pfad, ebenfalls ohne Upload
        app_module.studio.tick()
        assert client.get(f"/api/jobs/{job}/publishing/{later}").json()["published_at"] is None
        # YouTube-Upload bleibt abgesichert (Flag aus → kein Versuch)
        r = client.post(f"/api/jobs/{job}/publishing/{soon}/youtube/publish", json={"confirm": True})
        assert r.status_code in (400, 403, 409, 422)
        assert client.get(f"/api/jobs/{job}/publishing/{soon}").json()["published_at"] is None
        r = client.post(f"/api/jobs/{job}/publishing/{later}/youtube/publish", json={"confirm": True})
        assert r.status_code in (400, 409, 422)  # X-Draft kann nie über YouTube laufen
    finally:
        clear_env()
        shutil.rmtree(tmp, ignore_errors=True)


def test_analytics_has_no_invented_values():
    tmp = tempfile.mkdtemp(prefix="ana_")
    try:
        client, _ = make_client(tmp)
        _, job = _exported(client)
        pub = _draft(client, job)
        assert client.get("/api/studio/analytics").json()["rows"] == []  # Entwürfe zählen nicht
        r = client.post(f"/api/studio/analytics/{job}/{pub}/metrics", json={"views": 10})
        assert r.status_code == 409 and _err(r) == "draft_not_published"
        client.post(f"/api/studio/publishing/{job}/{pub}/mark-published", json={"confirm": True})
        row = client.get("/api/studio/analytics").json()["rows"][0]
        assert row["metrics"] is None and row["metric_entries"] == 0  # nichts erfunden, keine 0
        assert row["performance_potential"]["source"] == "estimated"
        assert isinstance(row["performance_potential"]["value"], (int, float))
        assert row["publish_source"] == "manual"
        base = f"/api/studio/analytics/{job}/{pub}"
        assert _err(client.post(f"{base}/metrics", json={})) == "validation_error"
        assert client.post(f"{base}/metrics", json={"views": -5}).status_code == 422
        assert client.post(f"{base}/metrics", json={"views": "viele"}).status_code == 422
        e = client.post(f"{base}/metrics", json={"views": 1200, "likes": 80}).json()["entry"]
        assert e == {**e, "views": 1200, "likes": 80, "comments": None, "source": "manual"}
        row = client.get("/api/studio/analytics").json()["rows"][0]
        assert row["metrics"]["views"] == 1200 and row["metrics"]["comments"] is None
        assert row["metrics"]["source"] == "manual" and row["metric_entries"] == 1
        client.post(f"{base}/metrics", json={"views": 1500, "likes": 95, "comments": 4})
        hist = client.get(base).json()["entries"]
        assert [h["views"] for h in hist] == [1200, 1500]
        legend = client.get("/api/studio/analytics").json()["legend"]
        assert set(legend) == {"manual", "synced", "estimated"}
    finally:
        clear_env()
        shutil.rmtree(tmp, ignore_errors=True)


def test_metric_sync_adapter_fallback_and_failure():
    tmp = tempfile.mkdtemp(prefix="ana_")
    try:
        client, app_module = make_client(tmp)
        _, job = _exported(client)
        manual = _draft(client, job, "tiktok")
        client.post(f"/api/studio/publishing/{job}/{manual}/mark-published", json={"confirm": True})
        r = client.post(f"/api/studio/analytics/{job}/{manual}/sync")
        assert r.status_code == 409 and _err(r) == "metrics_unavailable"
        assert r.json()["detail"]["details"]["fallback"] == "manual"
        # YouTube-Draft, der (simuliert) über den Plattformpfad veröffentlicht wurde
        from clipforge.publishing import apply_publish_state
        yt = _draft(client, job, "youtube_shorts")
        job_dir = app_module.registry.get(job).job_dir
        apply_publish_state(job_dir, yt, {"status": "published", "external_post_id": "vid123",
                                          "published_at": "2026-03-01T10:00:00+00:00"})
        assert _err(client.post(f"/api/studio/analytics/{job}/{yt}/sync")) == "metrics_unavailable"

        def failing(video_id):
            raise ConnectionError("api down")
        app_module.studio.metric_fetchers = lambda: {"youtube_shorts": failing}
        r = client.post(f"/api/studio/analytics/{job}/{yt}/sync")
        assert r.status_code == 502 and _err(r) == "metrics_sync_failed"
        assert client.get(f"/api/studio/analytics/{job}/{yt}").json()["entries"] == []  # nichts gespeichert
        seen = []

        def working(video_id):
            seen.append(video_id)
            return {"views": "4321", "likes": "210", "comments": None}
        app_module.studio.metric_fetchers = lambda: {"youtube_shorts": working}
        e = client.post(f"/api/studio/analytics/{job}/{yt}/sync").json()["entry"]
        assert seen == ["vid123"] and e["source"] == "synced"
        assert (e["views"], e["likes"], e["comments"]) == (4321, 210, None)
        rows = {r["publishing_id"]: r for r in client.get("/api/studio/analytics").json()["rows"]}
        assert rows[yt]["metrics"]["source"] == "synced" and rows[yt]["publish_source"] == "platform"
        assert rows[manual]["metrics"] is None
    finally:
        clear_env()
        shutil.rmtree(tmp, ignore_errors=True)


def test_hook_comparison_potential_vs_actual_and_remix():
    tmp = tempfile.mkdtemp(prefix="ana_")
    try:
        client, _ = make_client(tmp)
        pid, job = _exported(client)
        pubs = []
        for title in ("Hook A: Frage?", "Hook B: Zahl 3", "Hook C: Story"):
            pub = _draft(client, job, "tiktok", title=title)
            client.post(f"/api/studio/publishing/{job}/{pub}/mark-published", json={"confirm": True})
            pubs.append(pub)
        ov = client.get("/api/studio/analytics").json()
        comp = ov["hook_comparisons"][0]
        assert len(comp["variants"]) == 3 and comp["best_publishing_id"] is None
        assert "Zu wenige Messwerte" in comp["note"]
        assert ov["potential_vs_actual"]["pairs"] == [] and ov["potential_vs_actual"]["rank_agreement"] is None
        client.post(f"/api/studio/analytics/{job}/{pubs[0]}/metrics", json={"views": 100})
        assert client.get("/api/studio/analytics").json()["hook_comparisons"][0]["best_publishing_id"] is None
        client.post(f"/api/studio/analytics/{job}/{pubs[1]}/metrics", json={"views": 900})
        ov = client.get("/api/studio/analytics").json()
        comp = ov["hook_comparisons"][0]
        assert comp["best_publishing_id"] == pubs[1]
        unmeasured = next(v for v in comp["variants"] if v["publishing_id"] == pubs[2])
        assert unmeasured["views"] is None and unmeasured["source"] is None
        assert len(ov["potential_vs_actual"]["pairs"]) == 2
        assert all(p["views_source"] == "manual" for p in ov["potential_vs_actual"]["pairs"])
        assert all(r["studio_project_id"] == pid for r in ov["rows"])
        # Remix: neues Projekt, Eigenschaften übernommen, Messwerte als Begründung
        r = client.post(f"/api/studio/projects/{pid}/remix", json={})
        assert r.status_code == 201
        remix = r.json()["project"]
        src = client.get(f"/api/studio/projects/{pid}").json()["project"]
        assert remix["id"] != pid and remix["title"].endswith("(Remix)")
        assert remix["lineage"]["remix_of"] == pid and remix["exports"] == []
        traits = remix["lineage"]["traits"]
        assert traits["caption_style"] == "bold" and traits["hook"] == src["scenes"][0]["text"]
        assert traits["based_on_metrics"]["source"] == "manual"
        assert remix["captions"] == src["captions"] and remix["voice"] == src["voice"]
        assert [s["text"] for s in remix["scenes"]] == [s["text"] for s in src["scenes"]]
        # Remix ohne Messwerte erfindet keine Begründung
        fresh = client.post("/api/studio/projects", json={"workflow": "script", "script": SCRIPT}).json()
        wait_task(client, fresh["task_id"])
        r2 = client.post(f"/api/studio/projects/{fresh['project']['id']}/remix", json={"title": "Neu"})
        assert r2.json()["project"]["lineage"]["traits"]["based_on_metrics"] is None
        assert r2.json()["project"]["title"] == "Neu"
    finally:
        clear_env()
        shutil.rmtree(tmp, ignore_errors=True)


def test_idea_library_crud_search_and_inspiration():
    tmp = tempfile.mkdtemp(prefix="ana_")
    try:
        client, _ = make_client(tmp)
        empty = client.get("/api/studio/ideas").json()
        assert empty["ideas"] == [] and "keine Kopie" in empty["notice"]["de"]  # keine Fremddaten
        post = lambda body: client.post("/api/studio/ideas", json=body)  # noqa: E731
        assert _err(post({})) == "validation_error"
        assert _err(post({"title": "x", "url": "http://127.0.0.1/a"})) == "url_blocked"
        assert _err(post({"title": "x", "url": "ftp://example.com"})) == "url_invalid"
        assert _err(post({"title": "x", "metrics": {"views": -1}})) == "validation_error"
        a = post({"title": "3 Fehler beim Kaffee", "url": "https://www.youtube.com/watch?v=abc",
                  "niche": "Kaffee", "tags": ["Liste", "kaffee", "liste"], "hook_type": "number",
                  "format": "list", "platform": "youtube",
                  "metrics": {"views": 50000, "likes": 2100}}).json()["idea"]
        b = post({"title": "Mein Morgen", "niche": "lifestyle", "hook_type": "story",
                  "format": "vlog", "notes": "ruhiger Schnitt"}).json()["idea"]
        assert a["tags"] == ["liste", "kaffee"] and a["metrics"]["source"] == "manual"
        assert a["metrics"]["comments"] is None
        assert b["format"] == "other" and b["metrics"] == {"views": None, "likes": None,
                                                           "comments": None, "source": None}
        find = lambda qs: [i["id"] for i in client.get(f"/api/studio/ideas?{qs}").json()["ideas"]]  # noqa: E731
        assert find("q=kaffee") == [a["id"]] and find("q=schnitt") == [b["id"]]
        assert find("niche=lifestyle") == [b["id"]] and find("hook_type=number") == [a["id"]]
        assert find("tag=liste") == [a["id"]] and find("platform=youtube") == [a["id"]]
        assert find("format=list&niche=kaffee") == [a["id"]] and find("q=gibtsnicht") == []
        upd = client.patch(f"/api/studio/ideas/{a['id']}", json={"notes": "starker Einstieg"}).json()["idea"]
        assert upd["notes"] == "starker Einstieg" and upd["title"] == a["title"]
        assert upd["metrics"]["views"] == 50000
        # Als Inspiration: eigenes Thema Pflicht, nur Struktur-Merkmale werden übernommen
        use = f"/api/studio/ideas/{a['id']}/use"
        assert _err(client.post(use, json={"topic": " "})) == "validation_error"
        r = client.post(use, json={"topic": "Drei Fehler beim Tee kochen", "language": "de"})
        assert r.status_code == 201 and "keine Kopie" in r.json()["originality_notice"]
        wait_task(client, r.json()["task_id"])
        p = client.get(f"/api/studio/projects/{r.json()['project']['id']}").json()["project"]
        assert p["lineage"]["idea_id"] == a["id"]
        assert p["lineage"]["traits"] == {"hook_type": "number", "format": "list", "niche": "kaffee"}
        text = " ".join(s["text"] for s in p["scenes"])
        assert "Tee" in text and "Kaffee" not in text and "youtube.com" not in text
        assert client.delete(f"/api/studio/ideas/{b['id']}").json() == {"deleted": True}
        assert client.delete(f"/api/studio/ideas/{b['id']}").status_code == 404
        assert client.get("/api/studio/ideas/..%2Fx").status_code in (404, 405)
    finally:
        clear_env()
        shutil.rmtree(tmp, ignore_errors=True)


def test_automation_routes_end_to_end():
    tmp = tempfile.mkdtemp(prefix="ana_")
    try:
        client, app_module = make_client(tmp)
        body = {"name": "Wöchentlich", "workflow": "script", "items": [SCRIPT],
                "schedule": {"frequency": "weekly", "time": "18:00", "weekday": 2,
                             "timezone": "Europe/Berlin"},
                "settings": {"voice": {"provider": "mock"}, "resolution": "720p"},
                "publishing": {"mode": "draft", "platforms": ["instagram_reels"]}}
        assert _err(client.post("/api/studio/automations", json={**body, "workflow": "pdf"})) == "validation_error"
        a = client.post("/api/studio/automations", json=body).json()["automation"]
        assert a["enabled"] and a["next_run_at"] and a["runs"] == []
        lst = client.get("/api/studio/automations").json()
        assert len(lst["automations"]) == 1 and "veröffentlichen nie" in lst["safety"]
        assert lst["worker"]["running"] is False  # im Test bewusst aus
        paused = client.post(f"/api/studio/automations/{a['id']}/pause").json()["automation"]
        assert not paused["enabled"] and paused["next_run_at"] is None
        resumed = client.post(f"/api/studio/automations/{a['id']}/resume").json()["automation"]
        assert resumed["enabled"] and resumed["next_run_at"] == a["next_run_at"]
        patched = client.patch(f"/api/studio/automations/{a['id']}",
                               json={"schedule": {"frequency": "daily", "time": "07:30"}}).json()["automation"]
        assert patched["schedule"]["frequency"] == "daily" and patched["name"] == "Wöchentlich"
        r = client.post(f"/api/studio/automations/{a['id']}/run")
        assert r.status_code == 202
        task = wait_task(client, r.json()["task_id"], timeout=180)
        assert task["status"] == "succeeded", task
        view = client.get(f"/api/studio/automations/{a['id']}").json()["automation"]
        run = view["runs"][0]
        assert run["status"] == "succeeded" and run["trigger"] == "manual" and len(run["draft_ids"]) == 1
        drafts = client.get("/api/studio/publishing/drafts").json()["drafts"]
        assert len(drafts) == 1 and drafts[0]["status"] == "draft" and drafts[0]["published_at"] is None
        assert _err(client.post(f"/api/studio/automations/{a['id']}/runs/{run['id']}/retry")) == "run_not_retryable"
        assert client.delete(f"/api/studio/automations/{a['id']}").json() == {"deleted": True}
        assert client.get(f"/api/studio/automations/{a['id']}").status_code == 404
    finally:
        clear_env()
        shutil.rmtree(tmp, ignore_errors=True)


def test_startup_recovery_hook_runs_on_server_start():
    tmp = tempfile.mkdtemp(prefix="ana_")
    try:
        client, app_module = make_client(tmp)
        svc = app_module.studio.service
        p = svc.create_project({"workflow": "script", "script": SCRIPT})
        svc.tasks._save({"id": "abcabcabcabc", "kind": "render", "project_id": p["id"],
                         "params": {"mode": "preview"}, "status": "running", "progress": [],
                         "result": None, "error": None, "attempts": 1, "idempotency_key": None,
                         "created_at": "x", "started_at": "x", "finished_at": None})
        with client:  # löst die startup-/shutdown-Events aus (wie ein echter Serverstart)
            t = client.get("/api/studio/tasks/abcabcabcabc").json()
            assert t["status"] == "interrupted" and t["error"]["code"] == "interrupted"
            view = client.get(f"/api/studio/projects/{p['id']}").json()
            assert view["tasks"][0]["status"] == "interrupted"
    finally:
        clear_env()
        shutil.rmtree(tmp, ignore_errors=True)


if __name__ == "__main__":
    run_all(globals())
