"""Automationen: wiederkehrende Videoerstellung (täglich/wöchentlich/monatlich).

Persistent (eine JSON-Datei je Automation) und neustartfest:
  - `next_run_at` steht auf der Platte; verpasste Termine werden nach dem
    Start genau EINMAL nachgeholt (kein Nachhol-Sturm).
  - Läufe, die beim Absturz aktiv waren, werden als `interrupted` markiert und
    höchstens einmal automatisch wiederholt.
Sicherheit: Eine Automation erzeugt höchstens Publishing-DRAFTS. Sie
veröffentlicht nie und lädt nie etwas hoch. Budget- und Parallelitätsgrenzen
werden vor jedem Lauf geprüft. Die Uhr ist injizierbar (Tests).
"""

from __future__ import annotations

import calendar
import datetime
import os
import threading
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from ..publishing import PLATFORMS, create_draft, update_draft
from .costs import CostLedger
from .errors import StudioError
from .safe_fetch import validate_url
from .storage import new_id, now_iso, read_json, require_id, studio_dir, write_json_atomic

FREQUENCIES = ("daily", "weekly", "monthly")
AUTOMATABLE = ("prompt", "script", "article_url", "website_review", "social_url", "cinematic")
MAX_RUN_HISTORY = 50
MAX_AUTO_ATTEMPTS = 2
ACTIVE = ("queued", "running")
UTC = datetime.timezone.utc


def utc_now() -> datetime.datetime:
    return datetime.datetime.now(UTC)


def _tz(name: str) -> ZoneInfo:
    try:
        return ZoneInfo(name or "UTC")
    except (ZoneInfoNotFoundError, ValueError) as exc:
        raise StudioError("validation_error", f"Unbekannte Zeitzone '{name}'.") from exc


def compute_next(schedule: dict, after: datetime.datetime) -> datetime.datetime:
    """Nächster Termin STRIKT nach `after` (UTC-Rückgabe, DST-fest über zoneinfo)."""
    tz = _tz(schedule.get("timezone") or "UTC")
    hour, minute = (int(x) for x in schedule["time"].split(":"))
    local = after.astimezone(tz)
    freq = schedule["frequency"]

    def at(day: datetime.date) -> datetime.datetime:
        return datetime.datetime(day.year, day.month, day.day, hour, minute, tzinfo=tz)

    if freq == "daily":
        candidate = at(local.date())
        if candidate <= local:
            candidate = at(local.date() + datetime.timedelta(days=1))
    elif freq == "weekly":
        weekday = int(schedule.get("weekday", 0))
        day = local.date() + datetime.timedelta(days=(weekday - local.weekday()) % 7)
        candidate = at(day)
        if candidate <= local:
            candidate = at(day + datetime.timedelta(days=7))
    else:  # monthly
        dom = int(schedule.get("day", 1))
        year, month = local.year, local.month
        candidate = at(datetime.date(year, month, min(dom, calendar.monthrange(year, month)[1])))
        if candidate <= local:
            month += 1
            if month > 12:
                year, month = year + 1, 1
            candidate = at(datetime.date(year, month,
                                         min(dom, calendar.monthrange(year, month)[1])))
    return candidate.astimezone(UTC)


def _iso(dt: datetime.datetime) -> str:
    return dt.astimezone(UTC).isoformat(timespec="seconds")


def _parse(ts: str | None) -> datetime.datetime | None:
    if not ts:
        return None
    try:
        dt = datetime.datetime.fromisoformat(ts.replace("Z", "+00:00"))
    except ValueError:
        return None
    return dt if dt.tzinfo else dt.replace(tzinfo=UTC)


def normalize(data: dict, existing: dict | None = None) -> dict:
    """Validiert eine Automation (Anlegen/Ändern)."""
    base = dict(existing or {})
    merged = {**base, **{k: v for k, v in data.items() if v is not None}}
    name = str(merged.get("name") or "").strip()[:80]
    if not name:
        raise StudioError("validation_error", "Bitte einen Namen angeben.")
    workflow = merged.get("workflow")
    if workflow not in AUTOMATABLE:
        raise StudioError("validation_error",
                          f"Workflow nicht automatisierbar (erlaubt: {', '.join(AUTOMATABLE)}).")
    sched = merged.get("schedule") if isinstance(merged.get("schedule"), dict) else {}
    freq = sched.get("frequency")
    if freq not in FREQUENCIES:
        raise StudioError("validation_error", "frequency muss daily, weekly oder monthly sein.")
    time_s = str(sched.get("time") or "09:00")
    try:
        hh, mm = (int(x) for x in time_s.split(":"))
        assert 0 <= hh < 24 and 0 <= mm < 60
    except (ValueError, AssertionError) as exc:
        raise StudioError("validation_error", "time muss im Format HH:MM sein.") from exc
    schedule = {"frequency": freq, "time": f"{hh:02d}:{mm:02d}",
                "timezone": str(sched.get("timezone") or "UTC")}
    _tz(schedule["timezone"])
    if freq == "weekly":
        try:
            schedule["weekday"] = int(sched.get("weekday", 0))
            assert 0 <= schedule["weekday"] <= 6
        except (TypeError, ValueError, AssertionError) as exc:
            raise StudioError("validation_error", "weekday muss 0 (Mo) bis 6 (So) sein.") from exc
    if freq == "monthly":
        try:
            schedule["day"] = int(sched.get("day", 1))
            assert 1 <= schedule["day"] <= 31
        except (TypeError, ValueError, AssertionError) as exc:
            raise StudioError("validation_error", "day muss 1 bis 31 sein.") from exc
    items = merged.get("items") or []
    if isinstance(items, str):
        items = [ln for ln in items.split("\n")]
    items = [str(i).strip()[:20000] for i in items if str(i).strip()][:200]
    if not items:
        raise StudioError("validation_error",
                          "Bitte mindestens ein Thema, Skript oder eine URL angeben.")
    if workflow in ("article_url", "website_review", "social_url"):
        for url in items:
            validate_url(url)
    pub = merged.get("publishing") if isinstance(merged.get("publishing"), dict) else {}
    mode = pub.get("mode") if pub.get("mode") in ("none", "draft") else "none"
    platforms = [p for p in (pub.get("platforms") or []) if p in PLATFORMS]
    if mode == "draft" and not platforms:
        raise StudioError("validation_error", "Bitte mindestens eine Plattform für Drafts wählen.")
    settings = merged.get("settings") if isinstance(merged.get("settings"), dict) else {}

    def money(key: str, default: float) -> float:
        try:
            return max(0.0, min(10000.0, float(merged.get(key, default))))
        except (TypeError, ValueError):
            return default

    return {
        "id": base.get("id") or new_id(), "name": name, "workflow": workflow,
        "enabled": bool(merged.get("enabled", True)),
        "schedule": schedule, "items": items,
        "cursor": int(base.get("cursor") or 0),
        "language": merged.get("language") if merged.get("language") in ("de", "en") else "de",
        "settings": {k: settings[k] for k in (
            "aspect_ratio", "resolution", "captions", "voice", "music", "style")
            if settings.get(k) is not None},
        "use_brand_kit": bool(merged.get("use_brand_kit", True)),
        "publishing": {"mode": mode, "platforms": platforms},
        "budget_per_run_usd": money("budget_per_run_usd", 0.0),
        "monthly_budget_usd": money("monthly_budget_usd", 0.0),
        "next_run_at": base.get("next_run_at"),
        "last_run_at": base.get("last_run_at"),
        "runs": base.get("runs") or [],
        "created_at": base.get("created_at") or now_iso(),
        "updated_at": now_iso(),
    }


class AutomationService:
    @property
    def dir(self) -> str:
        path = os.path.join(studio_dir(), "automations")  # je Benutzerbereich
        os.makedirs(path, exist_ok=True)
        return path

    def __init__(self, studio, registry=None, clock=utc_now, max_concurrent: int | None = None,
                 inline: bool = False) -> None:
        self.studio = studio
        self.registry = registry
        self.clock = clock
        self.inline = inline  # Tests: Läufe synchron ausführen
        if max_concurrent is None:
            try:
                max_concurrent = max(1, int(os.environ.get("CLIPFORGE_AUTOMATION_MAX_CONCURRENT", "1")))
            except ValueError:
                max_concurrent = 1
        self.max_concurrent = max_concurrent
        os.makedirs(self.dir, exist_ok=True)
        self._lock = threading.RLock()
        studio.tasks.register("automation_run", self._task_run)

    # -------------------------------------------------------------- CRUD
    def _path(self, aid: str) -> str:
        return os.path.join(self.dir, f"{require_id(aid, 'Automations-ID')}.json")

    def get(self, aid: str) -> dict:
        data = read_json(self._path(aid), None)
        if not isinstance(data, dict):
            raise StudioError("automation_not_found", "Automation nicht gefunden.", 404)
        return data

    def _save(self, auto: dict) -> dict:
        auto["runs"] = auto["runs"][-MAX_RUN_HISTORY:]
        write_json_atomic(self._path(auto["id"]), auto)
        return auto

    def list(self) -> list[dict]:
        out = []
        for name in os.listdir(self.dir):
            if name.endswith(".json"):
                data = read_json(os.path.join(self.dir, name), None)
                if isinstance(data, dict):
                    out.append(data)
        return sorted(out, key=lambda a: a.get("created_at") or "")

    def create(self, data: dict) -> dict:
        auto = normalize(data)
        auto["next_run_at"] = _iso(compute_next(auto["schedule"], self.clock())) \
            if auto["enabled"] else None
        return self._save(auto)

    def update(self, aid: str, data: dict) -> dict:
        with self._lock:
            auto = normalize(data, self.get(aid))
            auto["next_run_at"] = _iso(compute_next(auto["schedule"], self.clock())) \
                if auto["enabled"] else None
            return self._save(auto)

    def set_enabled(self, aid: str, enabled: bool) -> dict:
        with self._lock:
            auto = self.get(aid)
            auto["enabled"] = bool(enabled)
            auto["next_run_at"] = _iso(compute_next(auto["schedule"], self.clock())) \
                if enabled else None
            auto["updated_at"] = now_iso()
            return self._save(auto)

    def delete(self, aid: str) -> None:
        auto = self.get(aid)
        if any(r["status"] in ACTIVE for r in auto["runs"]):
            raise StudioError("automation_busy", "Für diese Automation läuft noch ein Lauf.", 409)
        os.remove(self._path(aid))

    # ---------------------------------------------------------- Scheduling
    def _active_runs(self) -> int:
        return sum(1 for a in self.list() for r in a["runs"] if r["status"] in ACTIVE)

    def _month_spend(self, auto: dict, now: datetime.datetime) -> float:
        prefix = now.strftime("%Y-%m")
        return round(sum(float(r.get("cost_usd") or 0.0) for r in auto["runs"]
                         if (r.get("started_at") or "").startswith(prefix)), 4)

    def tick(self) -> list[dict]:
        """Startet fällige Läufe. Idempotent pro Termin (next_run_at wandert vor Start)."""
        pending: list[tuple[str, str]] = []
        now = self.clock()
        with self._lock:
            for auto in self.list():
                if not auto["enabled"]:
                    continue
                due_at = _parse(auto.get("next_run_at"))
                if due_at is None:
                    auto["next_run_at"] = _iso(compute_next(auto["schedule"], now))
                    self._save(auto)
                    continue
                if due_at > now:
                    continue
                if any(r["status"] in ACTIVE for r in auto["runs"]):
                    continue  # vorheriger Lauf noch aktiv → Termin bleibt fällig
                if self._active_runs() >= self.max_concurrent:
                    continue  # Parallelitätsgrenze → nächster Tick
                run = self._new_run(auto, scheduled_for=_iso(due_at), trigger="schedule")
                auto["next_run_at"] = _iso(compute_next(auto["schedule"], now))
                self._save(auto)
                pending.append((auto["id"], run["id"]))
        # Start außerhalb der Sperre; eingeplante Läufe zählen bereits als aktiv
        return [self._launch(aid, run_id) for aid, run_id in pending]

    def _new_run(self, auto: dict, scheduled_for: str | None, trigger: str,
                 item_index: int | None = None, attempt: int = 1) -> dict:
        if item_index is None:
            item_index = auto["cursor"] % len(auto["items"])
            auto["cursor"] = auto["cursor"] + 1
        run = {"id": new_id(), "status": "queued", "trigger": trigger,
               "scheduled_for": scheduled_for, "item_index": item_index, "attempt": attempt,
               "created_at": now_iso(), "started_at": None, "finished_at": None,
               "project_id": None, "job_id": None, "draft_ids": [], "task_id": None,
               "cost_usd": 0.0, "error": None}
        auto["runs"].append(run)
        return run

    def _launch(self, aid: str, run_id: str) -> dict:
        task = self.studio.tasks.submit(
            "automation_run", None, {"automation_id": aid, "run_id": run_id},
            idempotency_key=f"automation:{aid}:{run_id}", run_inline=self.inline)
        with self._lock:
            auto = self.get(aid)
            for run in auto["runs"]:
                if run["id"] == run_id:
                    run["task_id"] = task["id"]
            self._save(auto)
        return {"automation_id": aid, "run_id": run_id, "task_id": task["id"]}

    def run_now(self, aid: str) -> dict:
        with self._lock:
            auto = self.get(aid)
            if any(r["status"] in ACTIVE for r in auto["runs"]):
                raise StudioError("automation_busy", "Es läuft bereits ein Lauf.", 409)
            if self._active_runs() >= self.max_concurrent:
                raise StudioError("automation_capacity",
                                  "Parallelitätsgrenze erreicht — bitte später erneut versuchen.", 409)
            run = self._new_run(auto, scheduled_for=None, trigger="manual")
            self._save(auto)
        return self._launch(aid, run["id"])

    def retry_run(self, aid: str, run_id: str) -> dict:
        with self._lock:
            auto = self.get(aid)
            old = next((r for r in auto["runs"] if r["id"] == run_id), None)
            if old is None:
                raise StudioError("run_not_found", "Lauf nicht gefunden.", 404)
            if old["status"] not in ("failed", "interrupted"):
                raise StudioError("run_not_retryable",
                                  "Nur fehlgeschlagene oder unterbrochene Läufe sind wiederholbar.", 409)
            if any(r["status"] in ACTIVE for r in auto["runs"]):
                raise StudioError("automation_busy", "Es läuft bereits ein Lauf.", 409)
            old["retried"] = True
            run = self._new_run(auto, old.get("scheduled_for"), "retry",
                                item_index=old["item_index"], attempt=old["attempt"] + 1)
            self._save(auto)
        return self._launch(aid, run["id"])

    def _update_run(self, aid: str, run_id: str, **changes) -> dict:
        with self._lock:
            auto = self.get(aid)
            for run in auto["runs"]:
                if run["id"] == run_id:
                    run.update(changes)
            if changes.get("status") in ("succeeded", "failed"):
                auto["last_run_at"] = now_iso()
            return self._save(auto)

    # --------------------------------------------------------------- Lauf
    def _task_run(self, task: dict, progress, should_cancel) -> dict:
        aid, run_id = task["params"]["automation_id"], task["params"]["run_id"]
        auto = self.get(aid)
        run = next((r for r in auto["runs"] if r["id"] == run_id), None)
        if run is None:
            raise StudioError("run_not_found", "Lauf nicht gefunden.", 404)
        self._update_run(aid, run_id, status="running", started_at=now_iso())
        pid = None
        try:
            now = self.clock()
            if auto["monthly_budget_usd"] > 0 and \
                    self._month_spend(auto, now) >= auto["monthly_budget_usd"]:
                raise StudioError("budget_exceeded",
                                  "Monatsbudget der Automation ist ausgeschöpft.", 409)
            item = auto["items"][run["item_index"] % len(auto["items"])]
            req = {"workflow": auto["workflow"], "language": auto["language"],
                   "budget_limit_usd": auto["budget_per_run_usd"],
                   "lineage": {"automation_id": aid, "run_id": run_id},
                   **auto["settings"]}
            if not auto["use_brand_kit"]:
                caps = dict(req.get("captions") or {"style": "karaoke"})
                caps["use_brand"] = False
                req["captions"] = caps
            if auto["workflow"] in ("prompt", "cinematic"):
                req["prompt"] = item
            elif auto["workflow"] == "script":
                req["script"] = item
            else:
                req["url"] = item
            project = self.studio.create_project(req)
            pid = project["id"]
            self._update_run(aid, run_id, project_id=pid)
            progress("Quelle wird verarbeitet …")
            self.studio._ingest(pid, progress, should_cancel)
            progress("Video wird gerendert …")
            render_task = self.studio.start_render(pid, "final", inline=True)
            if render_task["status"] != "succeeded":
                err = render_task.get("error") or {"code": "render_failed",
                                                   "message": "Render fehlgeschlagen."}
                raise StudioError(err["code"], err["message"], 500)
            result: dict = {"project_id": pid, "render_id": render_task["result"]["render_id"]}
            draft_ids: list[str] = []
            job_id = None
            if self.registry is not None:
                export = self.studio.export_to_job(pid, result["render_id"])
                job_id = export["job_id"]
                if auto["publishing"]["mode"] == "draft":
                    job = self.registry.get(job_id)
                    for platform in auto["publishing"]["platforms"]:
                        # NUR ein Entwurf — nie veröffentlichen, nie hochladen.
                        draft = create_draft(job.job_dir, job.id, platform=platform,
                                             source_type="auto_clip", source_clip_index=1)
                        update_draft(job.job_dir, draft["publishing_id"], {"status": "draft"})
                        draft_ids.append(draft["publishing_id"])
            cost = CostLedger(self.studio.store.dir(pid), 0).spent
            self._update_run(aid, run_id, status="succeeded", finished_at=now_iso(),
                             job_id=job_id, draft_ids=draft_ids, cost_usd=cost)
            return {**result, "job_id": job_id, "draft_ids": draft_ids}
        except Exception as exc:  # noqa: BLE001 — Fehlerstatus sauber festhalten
            error = exc.to_dict() if isinstance(exc, StudioError) else {
                "code": "internal_error", "message": f"Unerwarteter Fehler ({type(exc).__name__})."}
            cost = CostLedger(self.studio.store.dir(pid), 0).spent if pid else 0.0
            self._update_run(aid, run_id, status="failed", finished_at=now_iso(),
                             error=error, cost_usd=cost)
            raise

    # ------------------------------------------------------------ Recovery
    def recover(self) -> dict:
        """Nach tasks.recover(): hängende Läufe bereinigen + einmal wiederholen."""
        interrupted, retried = [], []
        with self._lock:
            for auto in self.list():
                changed = False
                for run in list(auto["runs"]):
                    if run["status"] not in ACTIVE:
                        continue
                    task_status = None
                    if run.get("task_id"):
                        try:
                            task_status = self.studio.tasks.get(run["task_id"])["status"]
                        except StudioError:
                            task_status = None
                    if task_status == "queued":
                        continue  # wurde vom TaskManager neu eingeplant
                    run.update(status="interrupted", finished_at=now_iso(), error={
                        "code": "interrupted", "message": "Beim Neustart unterbrochen."})
                    interrupted.append(run["id"])
                    changed = True
                    if run["attempt"] < MAX_AUTO_ATTEMPTS and auto["enabled"]:
                        run["retried"] = True
                        new = self._new_run(auto, run.get("scheduled_for"), "recovery",
                                            item_index=run["item_index"],
                                            attempt=run["attempt"] + 1)
                        retried.append((auto["id"], new["id"]))
                if changed:
                    self._save(auto)
        for aid, run_id in retried:
            self._launch(aid, run_id)
        return {"interrupted": interrupted, "retried": [r for _, r in retried]}

    def view(self, auto: dict) -> dict:
        now = self.clock()
        return {**auto, "runs": list(reversed(auto["runs"])),
                "month_spend_usd": self._month_spend(auto, now),
                "active": any(r["status"] in ACTIVE for r in auto["runs"])}


class Worker:
    """Hintergrund-Thread: tickt Automationen + Publishing-Planung."""

    def __init__(self, tick, interval: float = 30.0) -> None:
        self._tick = tick
        self._interval = interval
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None
        self.last_tick_at: str | None = None
        self.last_error: str | None = None

    def start(self) -> None:
        if self._thread and self._thread.is_alive():
            return
        self._stop.clear()
        self._thread = threading.Thread(target=self._loop, name="studio-worker", daemon=True)
        self._thread.start()

    def _loop(self) -> None:
        while not self._stop.is_set():
            try:
                self._tick()
                self.last_error = None
            except Exception as exc:  # noqa: BLE001 — Worker darf nie sterben
                self.last_error = type(exc).__name__
            self.last_tick_at = now_iso()
            self._stop.wait(self._interval)

    def stop(self) -> None:
        self._stop.set()

    def status(self) -> dict:
        return {"running": bool(self._thread and self._thread.is_alive()),
                "interval_seconds": self._interval, "last_tick_at": self.last_tick_at,
                "last_error": self.last_error}
