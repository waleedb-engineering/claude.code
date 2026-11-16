"""Studio: Automation-Scheduling mit kontrollierter Uhr, Recovery, Budget, Safety."""

from __future__ import annotations

import datetime
import os
import shutil
import tempfile

from studio_helpers import clear_env, make_service, run_all

from clipforge.publishing import list_drafts
from clipforge.studio.automation import AutomationService, Worker, compute_next, normalize
from clipforge.studio.errors import StudioError
from clipforge.studio.service import StudioService
from clipforge.studio.tasks import TaskManager

UTC = datetime.timezone.utc
SCRIPT = "Automatisch erstelltes Video Nummer eins. Es bleibt lokal. Folge für mehr."


class Clock:
    def __init__(self, now: datetime.datetime) -> None:
        self.now = now

    def __call__(self) -> datetime.datetime:
        return self.now

    def advance(self, **kw) -> None:
        self.now += datetime.timedelta(**kw)


def _dt(*args) -> datetime.datetime:
    return datetime.datetime(*args, tzinfo=UTC)


def _auto(**extra) -> dict:
    return {"name": "Täglich", "workflow": "script", "items": [SCRIPT],
            "schedule": {"frequency": "daily", "time": "09:00", "timezone": "UTC"},
            "settings": {"voice": {"provider": "mock"}, "resolution": "720p"}, **extra}


def _setup(tmp, clock, **kw):
    svc, registry = make_service(tmp)
    autos = AutomationService(svc, registry=registry, clock=clock, inline=True, **kw)
    return svc, registry, autos


def _code(fn) -> str:
    try:
        fn()
    except StudioError as exc:
        return exc.code
    return "no_error"


def test_compute_next_daily_weekly_monthly():
    d = {"frequency": "daily", "time": "09:00", "timezone": "UTC"}
    assert compute_next(d, _dt(2026, 3, 10, 8, 0)) == _dt(2026, 3, 10, 9, 0)
    assert compute_next(d, _dt(2026, 3, 10, 9, 0)) == _dt(2026, 3, 11, 9, 0)  # strikt danach
    assert compute_next(d, _dt(2026, 12, 31, 23, 0)) == _dt(2027, 1, 1, 9, 0)
    w = {"frequency": "weekly", "time": "18:30", "timezone": "UTC", "weekday": 4}  # Freitag
    assert compute_next(w, _dt(2026, 3, 10, 8, 0)) == _dt(2026, 3, 13, 18, 30)
    assert compute_next(w, _dt(2026, 3, 13, 18, 30)) == _dt(2026, 3, 20, 18, 30)
    m = {"frequency": "monthly", "time": "07:15", "timezone": "UTC", "day": 31}
    assert compute_next(m, _dt(2026, 1, 31, 8, 0)) == _dt(2026, 2, 28, 7, 15)  # kurzer Monat
    assert compute_next(m, _dt(2026, 2, 28, 8, 0)) == _dt(2026, 3, 31, 7, 15)
    assert compute_next(m, _dt(2026, 12, 31, 8, 0)) == _dt(2027, 1, 31, 7, 15)


def test_compute_next_respects_timezone_and_dst():
    berlin = {"frequency": "daily", "time": "09:00", "timezone": "Europe/Berlin"}
    assert compute_next(berlin, _dt(2026, 1, 10, 0, 0)) == _dt(2026, 1, 10, 8, 0)   # Winter UTC+1
    assert compute_next(berlin, _dt(2026, 7, 10, 0, 0)) == _dt(2026, 7, 10, 7, 0)   # Sommer UTC+2
    # über die Zeitumstellung (29.03.2026) hinweg bleibt es 09:00 Ortszeit
    assert compute_next(berlin, _dt(2026, 3, 28, 12, 0)) == _dt(2026, 3, 29, 7, 0)


def test_validation_rejects_unsafe_or_incomplete_automations():
    for bad in (
        {"name": ""}, {"workflow": "pdf"}, {"workflow": "longform"},
        {"schedule": {"frequency": "hourly", "time": "09:00"}},
        {"schedule": {"frequency": "daily", "time": "25:00"}},
        {"schedule": {"frequency": "daily", "time": "09:00", "timezone": "Mars/Olympus"}},
        {"schedule": {"frequency": "weekly", "time": "09:00", "weekday": 9}},
        {"schedule": {"frequency": "monthly", "time": "09:00", "day": 0}},
        {"items": []},
        {"workflow": "article_url", "items": ["http://127.0.0.1/x"]},
        {"workflow": "article_url", "items": ["file:///etc/passwd"]},
        {"publishing": {"mode": "draft", "platforms": []}},
    ):
        assert _code(lambda b=bad: normalize({**_auto(), **b})) in ("validation_error", "url_blocked", "url_invalid"), bad
    # „öffentlich posten“ gibt es als Modus schlicht nicht → fällt auf "none"
    assert normalize(_auto(publishing={"mode": "publish", "platforms": ["tiktok"]}))["publishing"]["mode"] == "none"
    assert normalize(_auto(publishing={"mode": "draft", "platforms": ["tiktok", "myspace"]}))["publishing"]["platforms"] == ["tiktok"]


def test_tick_runs_only_when_due_and_exactly_once():
    tmp = tempfile.mkdtemp(prefix="auto_")
    try:
        clock = Clock(_dt(2026, 3, 10, 8, 0))
        svc, registry, autos = _setup(tmp, clock)
        a = autos.create(_auto())
        assert a["next_run_at"] == "2026-03-10T09:00:00+00:00"
        assert autos.tick() == []                       # 08:00 → noch nichts
        clock.advance(minutes=59)
        assert autos.tick() == []                       # 08:59
        clock.advance(minutes=1)
        started = autos.tick()                          # 09:00 → genau ein Lauf
        assert len(started) == 1
        assert autos.tick() == [] and autos.tick() == []  # weitere Ticks: kein Doppellauf
        a = autos.get(a["id"])
        assert a["next_run_at"] == "2026-03-11T09:00:00+00:00"
        run = a["runs"][0]
        assert run["status"] == "succeeded" and run["trigger"] == "schedule"
        assert run["scheduled_for"] == "2026-03-10T09:00:00+00:00"
        project = svc.store.load(run["project_id"])
        assert project["lineage"]["automation_id"] == a["id"]
        assert len(svc.list_renders(run["project_id"])) == 1
        assert registry.get(run["job_id"]).status == "completed"
        clock.advance(days=1)
        assert len(autos.tick()) == 1
        assert len(autos.get(a["id"])["runs"]) == 2
        view = autos.view(autos.get(a["id"]))
        assert view["runs"][0]["created_at"] >= view["runs"][1]["created_at"] and not view["active"]
    finally:
        clear_env()
        shutil.rmtree(tmp, ignore_errors=True)


def test_pause_resume_and_item_rotation():
    tmp = tempfile.mkdtemp(prefix="auto_")
    try:
        clock = Clock(_dt(2026, 3, 10, 8, 0))
        svc, _, autos = _setup(tmp, clock)
        a = autos.create(_auto(items=[SCRIPT, SCRIPT.replace("eins", "zwei"),
                                      SCRIPT.replace("eins", "drei")]))
        paused = autos.set_enabled(a["id"], False)
        assert paused["next_run_at"] is None
        clock.advance(days=3)
        assert autos.tick() == []                        # pausiert → nichts, auch nichts nachgeholt
        resumed = autos.set_enabled(a["id"], True)
        assert resumed["next_run_at"] == "2026-03-13T09:00:00+00:00"
        assert autos.tick() == []
        texts = []
        for _ in range(4):
            clock.advance(days=1)
            autos.tick()
            run = autos.get(a["id"])["runs"][-1]
            texts.append(svc.store.load(run["project_id"])["scenes"][0]["text"])
        assert ["eins" in texts[0], "zwei" in texts[1], "drei" in texts[2], "eins" in texts[3]] == [True] * 4
    finally:
        clear_env()
        shutil.rmtree(tmp, ignore_errors=True)


def test_missed_schedule_after_downtime_runs_once_not_many():
    tmp = tempfile.mkdtemp(prefix="auto_")
    try:
        clock = Clock(_dt(2026, 3, 10, 8, 0))
        _, _, autos = _setup(tmp, clock)
        a = autos.create(_auto())
        clock.advance(days=10)                           # Rechner war 10 Tage aus
        assert len(autos.tick()) == 1
        assert autos.tick() == []
        a = autos.get(a["id"])
        assert len(a["runs"]) == 1                       # kein Nachhol-Sturm
        assert a["next_run_at"] == "2026-03-20T09:00:00+00:00"  # nächster regulärer Termin
    finally:
        clear_env()
        shutil.rmtree(tmp, ignore_errors=True)


def test_concurrency_limit_defers_instead_of_dropping():
    tmp = tempfile.mkdtemp(prefix="auto_")
    try:
        clock = Clock(_dt(2026, 3, 10, 8, 0))
        svc, _, autos = _setup(tmp, clock, max_concurrent=1)
        a = autos.create(_auto(name="A"))
        b = autos.create(_auto(name="B"))
        # A hat einen noch aktiven Lauf (simuliert) → Kapazität belegt
        data = autos.get(a["id"])
        autos._new_run(data, None, "manual")
        autos._save(data)
        clock.advance(hours=2)
        assert autos.tick() == []                        # B wartet, A hat aktiven Lauf
        assert autos.get(b["id"])["next_run_at"] == "2026-03-10T09:00:00+00:00"  # bleibt fällig
        assert _code(lambda: autos.run_now(b["id"])) == "automation_capacity"
        assert _code(lambda: autos.run_now(a["id"])) == "automation_busy"
        assert _code(lambda: autos.delete(a["id"])) == "automation_busy"
        data = autos.get(a["id"])
        data["runs"][0]["status"] = "failed"
        autos._save(data)
        started = autos.tick()                           # Kapazität frei → einer nach dem anderen
        assert len(started) == 1
        assert len(autos.tick()) == 1
        assert autos.get(b["id"])["runs"][-1]["status"] == "succeeded"
    finally:
        clear_env()
        shutil.rmtree(tmp, ignore_errors=True)


def test_run_creates_drafts_only_and_never_publishes():
    tmp = tempfile.mkdtemp(prefix="auto_")
    try:
        clock = Clock(_dt(2026, 3, 10, 9, 0))
        svc, registry, autos = _setup(tmp, clock)
        a = autos.create(_auto(publishing={"mode": "draft",
                                           "platforms": ["youtube_shorts", "tiktok", "x"]}))
        res = autos.run_now(a["id"])
        run = next(r for r in autos.get(a["id"])["runs"] if r["id"] == res["run_id"])
        assert run["status"] == "succeeded" and len(run["draft_ids"]) == 3
        job = registry.get(run["job_id"])
        drafts = list_drafts(job.job_dir)
        assert {d["platform"] for d in drafts} == {"youtube_shorts", "tiktok", "x"}
        for d in drafts:
            assert d["status"] == "draft"
            assert d["published_at"] is None and d["external_post_id"] is None
            assert not d.get("upload_state") and not d.get("publish_attempts")
        # ohne Draft-Modus entstehen gar keine Publishing-Objekte
        b = autos.create(_auto(name="ohne"))
        res = autos.run_now(b["id"])
        run = autos.get(b["id"])["runs"][0]
        assert run["draft_ids"] == [] and list_drafts(registry.get(run["job_id"]).job_dir) == []
    finally:
        clear_env()
        shutil.rmtree(tmp, ignore_errors=True)


def test_failure_status_and_retry():
    tmp = tempfile.mkdtemp(prefix="auto_")
    try:
        clock = Clock(_dt(2026, 3, 10, 9, 0))
        svc, _, autos = _setup(tmp, clock)
        a = autos.create(_auto(workflow="article_url", items=["https://example.com/a"]))

        def broken(*args, **kwargs):
            raise ConnectionResetError()
        import socket
        svc.fetch_kwargs = {"transport": broken, "resolver": lambda h, p, type=None: [
            (socket.AF_INET, socket.SOCK_STREAM, 6, "", ("93.184.216.34", p))]}
        res = autos.run_now(a["id"])
        run = autos.get(a["id"])["runs"][0]
        assert run["status"] == "failed" and run["error"]["code"] == "url_unreachable"
        assert run["finished_at"] and run["project_id"]
        assert svc.tasks.get(res["task_id"])["status"] == "failed"
        assert _code(lambda: autos.retry_run(a["id"], "ffffffffffff")) == "run_not_found"
        svc.fetch_kwargs["transport"] = lambda *args, **kw: (
            200, {"content-type": "text/html"},
            b"<p>Erster Satz der Seite mit Inhalt. Zweiter Satz der Seite mit Inhalt. "
            b"Dritter Satz der Seite mit Inhalt hier.</p>")
        autos.retry_run(a["id"], run["id"])
        runs = autos.get(a["id"])["runs"]
        assert len(runs) == 2 and runs[0]["retried"] is True
        assert runs[1]["status"] == "succeeded" and runs[1]["attempt"] == 2
        assert runs[1]["trigger"] == "retry" and runs[1]["item_index"] == runs[0]["item_index"]
        assert _code(lambda: autos.retry_run(a["id"], runs[1]["id"])) == "run_not_retryable"
    finally:
        clear_env()
        shutil.rmtree(tmp, ignore_errors=True)


def test_monthly_budget_blocks_before_any_work():
    tmp = tempfile.mkdtemp(prefix="auto_")
    try:
        clock = Clock(_dt(2026, 3, 10, 9, 0))
        svc, _, autos = _setup(tmp, clock)
        a = autos.create(_auto(monthly_budget_usd=1.0))
        data = autos.get(a["id"])
        data["runs"].append({"id": "aaaaaaaaaaaa", "status": "succeeded", "attempt": 1,
                             "item_index": 0, "started_at": "2026-03-02T09:00:00+00:00",
                             "cost_usd": 1.2})
        autos._save(data)
        before = len(svc.list_projects())
        autos.run_now(a["id"])
        run = autos.get(a["id"])["runs"][-1]
        assert run["status"] == "failed" and run["error"]["code"] == "budget_exceeded"
        assert run["project_id"] is None and len(svc.list_projects()) == before
        assert autos.view(autos.get(a["id"]))["month_spend_usd"] == 1.2
        clock.advance(days=30)                           # neuer Monat → wieder erlaubt
        autos.run_now(a["id"])
        assert autos.get(a["id"])["runs"][-1]["status"] == "succeeded"
    finally:
        clear_env()
        shutil.rmtree(tmp, ignore_errors=True)


def test_per_run_budget_is_a_hard_stop_for_paid_providers():
    from clipforge.studio.providers import remote
    tmp = tempfile.mkdtemp(prefix="auto_")
    calls = []
    original = remote.HTTP_POST
    try:
        clock = Clock(_dt(2026, 3, 10, 9, 0))
        svc, _, autos = _setup(tmp, clock)
        os.environ["OPENAI_API_KEY"] = "test-key-not-real"
        remote.HTTP_POST = lambda *a, **k: calls.append(1) or b""
        a = autos.create(_auto(settings={"voice": {"provider": "openai_tts"}},
                               budget_per_run_usd=0.0))
        autos.run_now(a["id"])
        run = autos.get(a["id"])["runs"][0]
        assert run["status"] == "failed" and run["error"]["code"] == "budget_exceeded"
        assert calls == [] and run["cost_usd"] == 0.0
    finally:
        remote.HTTP_POST = original
        clear_env("OPENAI_API_KEY")
        shutil.rmtree(tmp, ignore_errors=True)


def test_restart_recovery_marks_interrupted_and_retries_once():
    tmp = tempfile.mkdtemp(prefix="auto_")
    try:
        clock = Clock(_dt(2026, 3, 10, 9, 0))
        svc, registry, autos = _setup(tmp, clock)
        a = autos.create(_auto())
        # Zustand „Absturz mitten im Lauf“ auf die Platte schreiben
        data = autos.get(a["id"])
        run = autos._new_run(data, "2026-03-10T09:00:00+00:00", "schedule")
        task = {"id": "bbbbbbbbbbbb", "kind": "automation_run", "project_id": None,
                "params": {"automation_id": a["id"], "run_id": run["id"]}, "status": "running",
                "progress": [], "result": None, "error": None, "attempts": 1,
                "idempotency_key": None, "created_at": "x", "started_at": "x", "finished_at": None}
        svc.tasks._save(task)
        run.update(status="running", task_id=task["id"], started_at="2026-03-10T09:00:01+00:00")
        autos._save(data)
        next_before = autos.get(a["id"])["next_run_at"]

        # „Neustart“: komplett neue Service-Objekte über denselben Ordnern
        tasks2 = TaskManager()
        svc2 = StudioService(registry=registry, tasks=tasks2)
        autos2 = AutomationService(svc2, registry=registry, clock=clock, inline=True)
        info = tasks2.recover()
        assert info["interrupted"] == ["bbbbbbbbbbbb"] and info["requeued"] == []
        assert tasks2.get("bbbbbbbbbbbb")["status"] == "interrupted"
        rec = autos2.recover()
        assert rec["interrupted"] == [run["id"]] and len(rec["retried"]) == 1
        runs = autos2.get(a["id"])["runs"]
        assert runs[0]["status"] == "interrupted" and runs[0]["retried"] is True
        assert runs[1]["status"] == "succeeded" and runs[1]["trigger"] == "recovery"
        assert runs[1]["attempt"] == 2 and runs[1]["scheduled_for"] == runs[0]["scheduled_for"]
        assert autos2.get(a["id"])["next_run_at"] == next_before   # Zeitplan unverändert
        assert autos2.recover() == {"interrupted": [], "retried": []}  # idempotent
        # zweiter Absturz desselben Termins → NICHT endlos wiederholen
        data = autos2.get(a["id"])
        data["runs"][1].update(status="running", task_id="cccccccccccc")
        autos2._save(data)
        rec = autos2.recover()
        assert rec["retried"] == [] and autos2.get(a["id"])["runs"][1]["status"] == "interrupted"
        assert len(autos2.get(a["id"])["runs"]) == 2
    finally:
        clear_env()
        shutil.rmtree(tmp, ignore_errors=True)


def test_task_manager_recovery_requeues_queued_and_is_idempotent():
    tmp = tempfile.mkdtemp(prefix="auto_")
    try:
        svc, _ = make_service(tmp)
        p = svc.create_project({"workflow": "script", "script": SCRIPT})
        queued = {"id": "dddddddddddd", "kind": "ingest", "project_id": p["id"], "params": {},
                  "status": "queued", "progress": [], "result": None, "error": None,
                  "attempts": 0, "idempotency_key": "key-1", "created_at": "x",
                  "started_at": None, "finished_at": None}
        running = {**queued, "id": "eeeeeeeeeeee", "status": "running", "idempotency_key": None}
        svc.tasks._save(queued)
        svc.tasks._save(running)
        tasks2 = TaskManager(max_workers=1)
        StudioService(tasks=tasks2)
        info = tasks2.recover()
        assert info == {"requeued": ["dddddddddddd"], "interrupted": ["eeeeeeeeeeee"]}
        tasks2._pool.shutdown(wait=True)
        assert tasks2.get("dddddddddddd")["status"] == "succeeded"
        assert tasks2.get("eeeeeeeeeeee")["error"]["code"] == "interrupted"
        assert svc.store.load(p["id"])["status"] == "ready"
        # Idempotency-Key: dieselbe Aufgabe, kein zweiter Lauf
        tasks3 = TaskManager(max_workers=1)
        StudioService(tasks=tasks3)
        same = tasks3.submit("ingest", p["id"], {}, idempotency_key="key-1")
        assert same["id"] == "dddddddddddd"
        retried = tasks3.retry("eeeeeeeeeeee")
        assert retried["status"] == "queued"
        tasks3._pool.shutdown(wait=True)
        assert tasks3.get("eeeeeeeeeeee")["status"] == "succeeded"
        assert _code(lambda: tasks3.retry("dddddddddddd")) == "task_not_retryable"
    finally:
        clear_env()
        shutil.rmtree(tmp, ignore_errors=True)


def test_worker_survives_tick_errors():
    ticks = []

    def tick():
        ticks.append(1)
        if len(ticks) == 1:
            raise RuntimeError("boom")
    w = Worker(tick, interval=0.02)
    w.start()
    import time
    time.sleep(0.3)
    w.stop()
    assert len(ticks) >= 3 and w.status()["last_tick_at"]


if __name__ == "__main__":
    run_all(globals())
