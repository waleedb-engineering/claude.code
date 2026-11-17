"""Persistente Hintergrund-Aufgaben des Studios.

Jede Aufgabe liegt als `tasks/<id>.json` auf der Platte. Nach einem Neustart:
  - `queued`  → wird erneut eingeplant (noch nichts passiert)
  - `running` → `interrupted` (nie blind fortsetzen; per Retry neu startbar)
Requests blockieren nie: `submit` kehrt sofort mit der Task-ID zurück.
Idempotenz: gleicher `idempotency_key` → dieselbe Aufgabe.
"""

from __future__ import annotations

import os
import threading
from concurrent.futures import ThreadPoolExecutor

from .errors import StudioError
from .storage import new_id, now_iso, read_json, require_id, studio_dir, write_json_atomic

ACTIVE = ("queued", "running")
FINAL = ("succeeded", "failed", "canceled", "interrupted")


class TaskCanceled(Exception):
    pass


class TaskManager:
    def __init__(self, base: str | None = None, max_workers: int | None = None) -> None:
        self.dir = os.path.join(base or studio_dir(), "tasks")
        os.makedirs(self.dir, exist_ok=True)
        if max_workers is None:
            try:
                max_workers = max(1, int(os.environ.get("CLIPFORGE_STUDIO_WORKERS", "2")))
            except ValueError:
                max_workers = 2
        self._pool = ThreadPoolExecutor(max_workers=max_workers,
                                        thread_name_prefix="studio-task")
        self._handlers: dict[str, callable] = {}
        self._lock = threading.RLock()
        self._cancel: set[str] = set()
        self._finish_hooks: list = []

    def on_finish(self, hook) -> None:
        """hook(task) läuft nach JEDEM Endzustand (auch Cancel/Recovery)."""
        self._finish_hooks.append(hook)

    def _finished(self, task: dict) -> None:
        for hook in self._finish_hooks:
            try:
                hook(task)
            except Exception:  # noqa: BLE001 — Hook darf den Worker nie stören
                pass

    def register(self, kind: str, handler) -> None:
        self._handlers[kind] = handler

    def _path(self, tid: str) -> str:
        return os.path.join(self.dir, f"{require_id(tid, 'Task-ID')}.json")

    def get(self, tid: str) -> dict:
        data = read_json(self._path(tid), None)
        if not isinstance(data, dict):
            raise StudioError("task_not_found", "Aufgabe nicht gefunden.", 404)
        return data

    def _save(self, task: dict) -> None:
        task["updated_at"] = now_iso()
        write_json_atomic(self._path(task["id"]), task)

    def list(self, project_id: str | None = None, limit: int = 50) -> list[dict]:
        out = []
        for name in os.listdir(self.dir):
            if not name.endswith(".json"):
                continue
            data = read_json(os.path.join(self.dir, name), None)
            if isinstance(data, dict) and (project_id is None or data.get("project_id") == project_id):
                out.append(data)
        out.sort(key=lambda t: t.get("created_at") or "", reverse=True)
        return out[:limit]

    def find_by_key(self, key: str) -> dict | None:
        for task in self.list(limit=10_000):
            if task.get("idempotency_key") == key:
                return task
        return None

    def submit(self, kind: str, project_id: str | None, params: dict | None = None,
               idempotency_key: str | None = None, run_inline: bool = False) -> dict:
        if kind not in self._handlers:
            raise StudioError("task_kind_unknown", f"Unbekannte Aufgabe '{kind}'.", 400)
        with self._lock:
            if idempotency_key:
                existing = self.find_by_key(idempotency_key)
                if existing:
                    return existing
            task = {
                "id": new_id(), "kind": kind, "project_id": project_id,
                "params": params or {}, "status": "queued", "progress": [],
                "result": None, "error": None, "attempts": 0,
                "idempotency_key": idempotency_key,
                "created_at": now_iso(), "started_at": None, "finished_at": None,
            }
            self._save(task)
        if run_inline:
            self._run(task["id"])
            return self.get(task["id"])
        self._pool.submit(self._run, task["id"])
        return task

    def retry(self, tid: str) -> dict:
        with self._lock:
            task = self.get(tid)
            if task["status"] in ACTIVE:
                raise StudioError("task_active", "Die Aufgabe läuft bereits.", 409)
            if task["status"] == "succeeded":
                raise StudioError("task_not_retryable", "Die Aufgabe war bereits erfolgreich.", 409)
            task.update(status="queued", error=None, finished_at=None)
            task["progress"].append("Erneut eingeplant.")
            self._save(task)
        self._pool.submit(self._run, tid)
        return task

    def cancel(self, tid: str) -> dict:
        with self._lock:
            task = self.get(tid)
            if task["status"] not in ACTIVE:
                raise StudioError("task_not_cancelable", "Die Aufgabe ist nicht mehr aktiv.", 409)
            self._cancel.add(tid)
            if task["status"] == "queued":
                task.update(status="canceled", finished_at=now_iso())
                self._save(task)
                self._finished(task)
            return task

    def is_cancel_requested(self, tid: str) -> bool:
        return tid in self._cancel

    def _progress(self, tid: str, message: str) -> None:
        with self._lock:
            task = self.get(tid)
            task["progress"] = (task["progress"] + [message])[-200:]
            self._save(task)

    def _run(self, tid: str) -> None:
        with self._lock:
            try:
                task = self.get(tid)
            except StudioError:
                return
            if task["status"] != "queued":
                return  # z. B. bereits abgebrochen → bleibt abgebrochen
            if tid in self._cancel:
                task.update(status="canceled", finished_at=now_iso())
                self._save(task)
                self._cancel.discard(tid)
                self._finished(task)
                return
            task.update(status="running", started_at=now_iso(),
                        attempts=int(task.get("attempts") or 0) + 1)
            self._save(task)
        handler = self._handlers[task["kind"]]
        try:
            result = handler(task, lambda m: self._progress(tid, m),
                             lambda: self.is_cancel_requested(tid))
            update = {"status": "succeeded", "result": result}
        except TaskCanceled:
            update = {"status": "canceled"}
        except StudioError as exc:
            update = {"status": "failed", "error": exc.to_dict()}
        except Exception as exc:  # noqa: BLE001 — nie den Worker killen
            if type(exc).__name__ == "RenderCanceled":
                update = {"status": "canceled"}
            else:
                update = {"status": "failed", "error": {
                    "code": "internal_error",
                    "message": f"Unerwarteter Fehler ({type(exc).__name__})."}}
        with self._lock:
            task = self.get(tid)
            if tid in self._cancel:
                # Cancel bleibt Cancel: ein spät fertig gewordener Handler
                # überschreibt den Abbruchwunsch nicht.
                update = {"status": "canceled"}
            task.update(update, finished_at=now_iso())
            self._save(task)
            self._cancel.discard(tid)
        self._finished(task)

    def recover(self) -> dict:
        """Nach (Neu-)Start aufrufen. Liefert Zähler für das Startlog."""
        requeued, interrupted = [], []
        for task in self.list(limit=10_000):
            if task["status"] == "running":
                task.update(status="interrupted", finished_at=now_iso(), error={
                    "code": "interrupted",
                    "message": "Beim Neustart unterbrochen. Über „Erneut versuchen“ neu starten."})
                self._save(task)
                self._finished(task)
                interrupted.append(task["id"])
            elif task["status"] == "queued" and task["kind"] in self._handlers:
                requeued.append(task["id"])
        for tid in requeued:
            self._pool.submit(self._run, tid)
        return {"requeued": requeued, "interrupted": interrupted}

    def shutdown(self) -> None:
        self._pool.shutdown(wait=False, cancel_futures=True)
