"""Editor-Agent: Plan → Prüfung → Bestätigung → Ausführung → Rückgängig.

Chatverlauf je Projekt/Quelle in <studio>/agent/<art>_<id>.json. Vor jeder
ausgeführten Änderung wird die Projektversion gemerkt; „Rückgängig“ stellt
sie über die normale Versionsgeschichte wieder her (wie im Editor).
"""

from __future__ import annotations

import os

from ..studio.costs import CostLedger
from ..studio.errors import StudioError
from ..studio.storage import new_id, now_iso, read_json, studio_dir, write_json_atomic
from . import planner
from .tools import TOOLS, Ctx, validate


class AgentService:
    def __init__(self, svc, streams) -> None:
        self.svc, self.streams = svc, streams

    def _path(self, kind: str, target: str) -> str:
        if kind not in ("project", "stream"):
            raise StudioError("validation_error", "Kontext: project oder stream.")
        if kind == "project":
            self.svc.store.load(target)
        else:
            self.streams.load(target)
        d = os.path.join(studio_dir(), "agent")
        os.makedirs(d, exist_ok=True)
        return os.path.join(d, f"{kind}_{target}.json")

    def history(self, kind: str, target: str) -> list[dict]:
        data = read_json(self._path(kind, target), [])
        return data if isinstance(data, list) else []

    def _append(self, kind: str, target: str, entry: dict) -> dict:
        items = self.history(kind, target)
        items.append({"id": new_id(), "at": now_iso(), **entry})
        write_json_atomic(self._path(kind, target), items[-200:])
        return items[-1]

    def _replace(self, kind: str, target: str, entry: dict) -> None:
        items = [entry if x["id"] == entry["id"] else x for x in self.history(kind, target)]
        write_json_atomic(self._path(kind, target), items)

    def _state(self, ctx: Ctx) -> dict:
        try:
            tool = TOOLS["get_project_state" if ctx.kind == "project" else "list_highlights"]
            return tool.run(ctx, {})
        except StudioError:
            return {}

    # --------------------------------------------------------------- Plan
    def plan(self, kind: str, target: str, message: str, engine: str = "rules",
             confirm_cost: bool = False) -> dict:
        message = (message or "").strip()[:2000]
        if not message:
            raise StudioError("validation_error", "Bitte einen Befehl eingeben.")
        self._path(kind, target)
        ctx = Ctx(self.svc, self.streams, kind, target)
        self._append(kind, target, {"role": "user", "text": message})
        state = self._state(ctx)
        cost = planner.COST.get(engine)
        if cost is None:
            raise StudioError("validation_error", "Unbekannte KI-Engine.")
        notes: list[str] = []
        if engine == "rules":
            count = len(state.get("scenes") or state.get("highlights") or [])
            calls, notes = planner.rule_plan(message, kind, count)
            text = ""
        else:
            rid = None
            if cost > 0:
                if not confirm_cost:
                    raise StudioError("cost_confirmation_required",
                                      f"Diese Nachricht kostet ca. {cost:.3f} USD ({engine}). Bitte bestätigen.",
                                      402, {"estimated_usd": cost})
                if kind != "project":
                    raise StudioError("validation_error",
                                      "Bezahlte KI im Stream-Kontext: bitte im Projekt arbeiten oder "
                                      "„Regelbasiert“/Ollama wählen (kein Projektbudget).", 409)
                pdir = self.svc.store.dir(target)
                ledger = CostLedger(pdir, self.svc.store.load(target).get("budget_limit_usd") or 0.0)
                rid = ledger.reserve(cost, f"Editor-Agent ({engine})")
            try:
                calls, text = planner.llm_plan(engine, message, state, kind)
                if rid:
                    ledger.commit(rid, cost, engine, "agent")
            except BaseException:
                if rid:
                    ledger.release(rid)
                raise
        steps, problems = [], []
        for c in calls:
            tool = TOOLS.get(str(c.get("tool")))
            if tool is None or tool.context != kind:
                problems.append(f"Werkzeug „{c.get('tool')}“ ist nicht freigegeben.")
                continue
            try:
                args = validate(tool, c.get("args") or {})
            except StudioError as exc:
                problems.append(exc.message)
                continue
            steps.append({"tool": tool.name, "args": args, "label": tool.description,
                          "mutating": tool.mutating, "confirm": tool.confirm, "cost": tool.cost_note})
        reply = text or ("Ich würde Folgendes tun:" if steps else
                         "Das habe ich nicht verstanden oder es ist (noch) nicht möglich.")
        entry = self._append(kind, target, {
            "role": "assistant", "text": reply, "engine": engine, "notes": notes + problems,
            "plan": {"steps": steps, "status": "pending" if steps else "empty",
                     "needs_confirmation": any(s["confirm"] for s in steps)},
            "cost_usd": cost if engine != "rules" else 0.0})
        return entry

    # ----------------------------------------------------------- Ausführen
    def execute(self, kind: str, target: str, entry_id: str, confirm: bool = False) -> dict:
        items = self.history(kind, target)
        entry = next((x for x in items if x["id"] == entry_id), None)
        if entry is None or "plan" not in entry:
            raise StudioError("plan_not_found", "Plan nicht gefunden.", 404)
        plan = entry["plan"]
        if plan["status"] != "pending":
            raise StudioError("plan_done", "Dieser Plan wurde bereits ausgeführt oder verworfen.", 409)
        if plan.get("needs_confirmation") and not confirm:
            raise StudioError("confirmation_required",
                              "Dieser Plan startet einen Render/Export — bitte bestätigen.", 400)
        ctx = Ctx(self.svc, self.streams, kind, target)
        before = self.svc.store.load(target)["version"] if kind == "project" else None
        results = []
        for step in plan["steps"]:
            tool = TOOLS[step["tool"]]
            try:
                res = tool.run(ctx, validate(tool, step["args"]))
                results.append({"tool": tool.name, "ok": True, **res})
            except StudioError as exc:
                results.append({"tool": tool.name, "ok": False, "error": exc.message})
                break
        plan["status"] = "done" if all(r["ok"] for r in results) else "partial"
        plan["results"] = results
        plan["version_before"] = before
        self._replace(kind, target, entry)
        return entry

    def discard(self, kind: str, target: str, entry_id: str) -> dict:
        entry = next((x for x in self.history(kind, target) if x["id"] == entry_id), None)
        if entry is None or "plan" not in entry or entry["plan"]["status"] != "pending":
            raise StudioError("plan_not_found", "Offener Plan nicht gefunden.", 404)
        entry["plan"]["status"] = "discarded"
        self._replace(kind, target, entry)
        return entry

    def undo(self, kind: str, target: str) -> dict:
        """Letzte ausgeführte Projekt-Änderung des Agenten zurücknehmen."""
        if kind != "project":
            raise StudioError("validation_error", "Rückgängig ist für Projekte verfügbar; "
                              "Highlight-Grenzen lassen sich direkt korrigieren.", 409)
        for entry in reversed(self.history(kind, target)):
            plan = entry.get("plan") or {}
            if plan.get("status") in ("done", "partial") and plan.get("version_before") is not None \
                    and not plan.get("undone"):
                restored = self.svc.store.restore_version(target, plan["version_before"])
                plan["undone"] = True
                self._replace(kind, target, entry)
                self._append(kind, target, {"role": "assistant",
                                            "text": f"Rückgängig: Stand von Version {plan['version_before']} "
                                                    f"wiederhergestellt (jetzt v{restored['version']})."})
                return restored
        raise StudioError("nothing_to_undo", "Keine Agent-Änderung zum Rückgängigmachen.", 409)
