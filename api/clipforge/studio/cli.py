"""ClipForge-Studio-CLI — dünner HTTP-Client der lokalen Studio-API.

Voraussetzung: das Backend läuft (Standard http://127.0.0.1:8000).

    python -m clipforge.studio.cli create --workflow script --script "…" --wait
    python -m clipforge.studio.cli status <projekt-id>
    python -m clipforge.studio.cli render <projekt-id> --wait
    python -m clipforge.studio.cli export <projekt-id> --download out.mp4
    python -m clipforge.studio.cli automation list|create|run|pause|resume …

Ausgabe ist JSON (maschinenlesbar, für Skripte/Agenten). Exit-Code 0 = Erfolg,
1 = API-/Aufgabenfehler (Fehlercode steht im JSON), 2 = Verbindungsfehler.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
import urllib.error
import urllib.request


class ApiError(Exception):
    def __init__(self, status: int, detail) -> None:
        super().__init__(str(detail))
        self.status, self.detail = status, detail


class Client:
    def __init__(self, base: str) -> None:
        self.base = base.rstrip("/")
        self._token: str | None = None

    def token(self) -> str | None:
        """Local-API-Token: aus CLIPFORGE_API_TOKEN, sonst vom lokalen Backend."""
        if self._token is None:
            self._token = os.environ.get("CLIPFORGE_API_TOKEN") or ""
            if not self._token:
                try:
                    with urllib.request.urlopen(self.base + "/api/session", timeout=10) as resp:  # noqa: S310
                        self._token = json.loads(resp.read().decode("utf-8")).get("token") or ""
                except (OSError, ValueError):
                    self._token = ""
        return self._token or None

    def call(self, method: str, path: str, body: dict | None = None, raw: bool = False):
        data = json.dumps(body).encode("utf-8") if body is not None else None
        headers = {"Content-Type": "application/json"} if data is not None else {}
        if method not in ("GET", "HEAD") and self.token():
            headers["X-ClipForge-Token"] = self.token()
        req = urllib.request.Request(self.base + path, data=data, method=method, headers=headers)
        try:
            with urllib.request.urlopen(req, timeout=120) as resp:  # noqa: S310 — lokale API
                payload = resp.read()
        except urllib.error.HTTPError as exc:
            try:
                detail = json.loads(exc.read().decode("utf-8")).get("detail")
            except ValueError:
                detail = {"code": "http_error", "message": f"HTTP {exc.code}"}
            raise ApiError(exc.code, detail) from None
        return payload if raw else json.loads(payload.decode("utf-8"))

    def wait_task(self, task_id: str, timeout: float) -> dict:
        deadline = time.monotonic() + timeout
        while True:
            task = self.call("GET", f"/api/studio/tasks/{task_id}")
            if task["status"] not in ("queued", "running"):
                return task
            if time.monotonic() > deadline:
                raise ApiError(504, {"code": "timeout", "message": "Aufgabe läuft noch.",
                                     "task_id": task_id})
            time.sleep(1.0)


def _out(data) -> None:
    print(json.dumps(data, ensure_ascii=False, indent=2))


def _finish(task: dict) -> int:
    _out({"task": {k: task.get(k) for k in ("id", "kind", "status", "result", "error")}})
    return 0 if task["status"] == "succeeded" else 1


def cmd_create(c: Client, a) -> int:
    body = {"workflow": a.workflow, "language": a.language, "title": a.title or ""}
    for key in ("prompt", "script", "url", "job_id", "aspect_ratio", "resolution"):
        if getattr(a, key, None):
            body[key] = getattr(a, key)
    if a.script_file:
        with open(a.script_file, "r", encoding="utf-8") as fh:
            body["script"] = fh.read()
    if a.captions:
        body["captions"] = {"style": a.captions}
    if a.voice:
        body["voice"] = {"provider": a.voice}
    if a.budget is not None:
        body["budget_limit_usd"] = a.budget
    res = c.call("POST", "/api/studio/projects", body)
    out = {"project_id": res["project"]["id"], "task_id": res["task_id"],
           "needs_upload": res["needs_upload"]}
    if a.wait and res["task_id"]:
        task = c.wait_task(res["task_id"], a.timeout)
        out["ingest"] = {"status": task["status"], "error": task.get("error")}
        _out(out)
        return 0 if task["status"] == "succeeded" else 1
    _out(out)
    return 0


def cmd_status(c: Client, a) -> int:
    view = c.call("GET", f"/api/studio/projects/{a.project_id}")
    p = view["project"]
    _out({"id": p["id"], "title": p["title"], "status": p["status"],
          "status_error": p.get("status_error"), "version": p["version"],
          "scenes": len(p["scenes"]), "linked_job_id": p.get("linked_job_id"),
          "tasks": [{k: t.get(k) for k in ("id", "kind", "status", "error")}
                    for t in view["tasks"]],
          "renders": [{k: r.get(k) for k in ("render_id", "mode", "duration", "width", "height")}
                      for r in view["renders"]]})
    return 0


def cmd_render(c: Client, a) -> int:
    res = c.call("POST", f"/api/studio/projects/{a.project_id}/render",
                 {"mode": "preview" if a.preview else "final"})
    task = res["task"]
    if not a.wait:
        _out({"task_id": task["id"], "status": task["status"]})
        return 0
    return _finish(c.wait_task(task["id"], a.timeout))


def cmd_export(c: Client, a) -> int:
    body = {"render_id": a.render_id} if a.render_id else {}
    res = c.call("POST", f"/api/studio/projects/{a.project_id}/export", body)
    if a.download:
        data = c.call("GET", f"/api/studio/projects/{a.project_id}/renders/"
                             f"{res['render_id']}/file?download=true", raw=True)
        with open(a.download, "wb") as fh:
            fh.write(data)
        res["downloaded_to"] = os.path.abspath(a.download)
    _out(res)
    return 0


def cmd_automation(c: Client, a) -> int:
    if a.action == "list":
        res = c.call("GET", "/api/studio/automations")
        _out([{k: x.get(k) for k in ("id", "name", "enabled", "workflow", "next_run_at",
                                     "last_run_at", "active")} for x in res["automations"]])
    elif a.action == "create":
        schedule = {"frequency": a.frequency, "time": a.time, "timezone": a.timezone}
        if a.weekday is not None:
            schedule["weekday"] = a.weekday
        if a.day is not None:
            schedule["day"] = a.day
        _out(c.call("POST", "/api/studio/automations", {
            "name": a.name, "workflow": a.workflow, "schedule": schedule,
            "items": a.item or [], "language": a.language,
            "publishing": {"mode": "draft" if a.draft_platform else "none",
                           "platforms": a.draft_platform or []}})["automation"])
    elif a.action in ("pause", "resume", "run"):
        _out(c.call("POST", f"/api/studio/automations/{a.id}/{a.action}"))
    elif a.action == "show":
        _out(c.call("GET", f"/api/studio/automations/{a.id}")["automation"])
    return 0


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="clipforge-studio", description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--api", default=os.environ.get("CLIPFORGE_API", "http://127.0.0.1:8000"))
    sub = p.add_subparsers(dest="command", required=True)

    cr = sub.add_parser("create", help="Projekt anlegen (Text-/URL-Workflows)")
    cr.add_argument("--workflow", required=True)
    cr.add_argument("--title")
    cr.add_argument("--language", default="de", choices=["de", "en"])
    cr.add_argument("--prompt")
    cr.add_argument("--script")
    cr.add_argument("--script-file")
    cr.add_argument("--url")
    cr.add_argument("--job-id", dest="job_id")
    cr.add_argument("--aspect-ratio", dest="aspect_ratio")
    cr.add_argument("--resolution")
    cr.add_argument("--captions")
    cr.add_argument("--voice")
    cr.add_argument("--budget", type=float)
    cr.add_argument("--wait", action="store_true")
    cr.add_argument("--timeout", type=float, default=600)
    cr.set_defaults(fn=cmd_create)

    st = sub.add_parser("status", help="Projektstatus")
    st.add_argument("project_id")
    st.set_defaults(fn=cmd_status)

    rd = sub.add_parser("render", help="Render starten")
    rd.add_argument("project_id")
    rd.add_argument("--preview", action="store_true")
    rd.add_argument("--wait", action="store_true")
    rd.add_argument("--timeout", type=float, default=3600)
    rd.set_defaults(fn=cmd_render)

    ex = sub.add_parser("export", help="Finalen Render an den Publishing-Planner übergeben")
    ex.add_argument("project_id")
    ex.add_argument("--render-id", dest="render_id")
    ex.add_argument("--download", help="MP4 zusätzlich in diese Datei speichern")
    ex.set_defaults(fn=cmd_export)

    au = sub.add_parser("automation", help="Automationen verwalten")
    au.add_argument("action", choices=["list", "create", "show", "run", "pause", "resume"])
    au.add_argument("id", nargs="?")
    au.add_argument("--name")
    au.add_argument("--workflow", default="prompt")
    au.add_argument("--frequency", default="daily", choices=["daily", "weekly", "monthly"])
    au.add_argument("--time", default="09:00")
    au.add_argument("--timezone", default="UTC")
    au.add_argument("--weekday", type=int)
    au.add_argument("--day", type=int)
    au.add_argument("--item", action="append", help="Thema/Skript/URL (mehrfach möglich)")
    au.add_argument("--language", default="de", choices=["de", "en"])
    au.add_argument("--draft-platform", dest="draft_platform", action="append",
                    help="Publishing-ENTWURF für diese Plattform anlegen (nie veröffentlichen)")
    au.set_defaults(fn=cmd_automation)
    return p


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if args.command == "automation" and args.action in ("show", "run", "pause", "resume") \
            and not args.id:
        print("Automations-ID fehlt.", file=sys.stderr)
        return 1
    try:
        return args.fn(Client(args.api), args)
    except ApiError as exc:
        _out({"error": exc.detail, "http_status": exc.status})
        return 1
    except (urllib.error.URLError, OSError) as exc:
        _out({"error": {"code": "api_unreachable",
                        "message": f"Backend unter {args.api} nicht erreichbar ({exc})."}})
        return 2


if __name__ == "__main__":
    sys.exit(main())
