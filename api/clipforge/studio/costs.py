"""Kostenabschätzung + hartes Budgetlimit.

Preise sind SCHÄTZWERTE (Listenpreise ändern sich) und per ENV
`CLIPFORGE_PROVIDER_PRICES` (JSON) überschreibbar. Lokale Verarbeitung kostet 0.
Das Budget gilt pro Projekt kumulativ; vor JEDEM kostenpflichtigen Aufruf wird
geprüft — reicht es nicht, wird abgebrochen, BEVOR Kosten entstehen.
"""

from __future__ import annotations

import json
import os
import threading
import time
import uuid

from .errors import BudgetExceeded
from .storage import now_iso, read_json, write_json_atomic

DEFAULT_PRICES = {
    "elevenlabs_per_1k_chars": 0.30,
    "openai_tts_per_1k_chars": 0.015,
    "openai_image_per_image": 0.05,
}
_lock = threading.Lock()


def price(key: str) -> float:
    prices = dict(DEFAULT_PRICES)
    try:
        override = json.loads(os.environ.get("CLIPFORGE_PROVIDER_PRICES") or "{}")
        for k, v in override.items():
            if k in prices and isinstance(v, (int, float)) and v >= 0:
                prices[k] = float(v)
    except ValueError:
        pass
    return prices[key]


RESERVATION_TTL_SECONDS = 1800
_ledger_locks: dict[str, threading.Lock] = {}


def _ledger_lock(path: str) -> threading.Lock:
    with _lock:
        return _ledger_locks.setdefault(os.path.realpath(path), threading.Lock())


class CostLedger:
    """Persistentes Kostenbuch EINES Projekts (`costs.json`).

    Ablauf je kostenpflichtigem Aufruf — atomar unter einer Projekt-Sperre:
      reserve(erwartet)  → prüft verbraucht + reserviert + erwartet ≤ Limit
      commit(id, real)   → nach Erfolg: Reservierung → Verbrauch
      release(id)        → nach Fehler/Abbruch: Reservierung verfällt
    Gleichzeitige Requests können das Limit so nicht gemeinsam überschreiten.
    `budget_limit_usd = 0` bedeutet: nur kostenlose Provider.
    Reservierungen eines abgestürzten Prozesses verfallen nach 30 Minuten.
    """

    def __init__(self, project_dir: str, budget_limit_usd: float) -> None:
        self.path = os.path.join(project_dir, "costs.json")
        self.limit = max(0.0, float(budget_limit_usd or 0.0))
        self._guard = _ledger_lock(self.path)

    def _load(self) -> dict:
        data = read_json(self.path, None)
        if not isinstance(data, dict):
            data = {}
        data.setdefault("spent_usd", 0.0)
        data.setdefault("entries", [])
        data.setdefault("reservations", {})
        now = time.time()
        data["reservations"] = {
            rid: r for rid, r in data["reservations"].items()
            if isinstance(r, dict) and now - float(r.get("ts") or 0) < RESERVATION_TTL_SECONDS}
        return data

    @staticmethod
    def _reserved(data: dict) -> float:
        return sum(float(r.get("amount_usd") or 0.0) for r in data["reservations"].values())

    @property
    def spent(self) -> float:
        return float(self._load().get("spent_usd") or 0.0)

    @property
    def remaining(self) -> float:
        data = self._load()
        return max(0.0, self.limit - float(data["spent_usd"]) - self._reserved(data))

    def reserve(self, amount: float, what: str) -> str | None:
        """Reserviert `amount` oder wirft BudgetExceeded. None = kostenlos."""
        if amount <= 0:
            return None
        with self._guard:
            data = self._load()
            spent, reserved = float(data["spent_usd"]), self._reserved(data)
            if spent + reserved + amount > self.limit + 1e-9:
                remaining = max(0.0, self.limit - spent - reserved)
                raise BudgetExceeded(
                    f"Budgetlimit erreicht: {what} würde ca. {amount:.2f} USD kosten, "
                    f"verfügbar sind noch {remaining:.2f} von {self.limit:.2f} USD. Es "
                    f"wurde keine Anfrage gesendet.",
                    {"needed_usd": round(amount, 4), "remaining_usd": round(remaining, 4),
                     "spent_usd": round(spent, 4), "reserved_usd": round(reserved, 4),
                     "budget_limit_usd": self.limit})
            rid = uuid.uuid4().hex[:12]
            data["reservations"][rid] = {"amount_usd": round(amount, 6), "what": what,
                                         "ts": time.time()}
            write_json_atomic(self.path, data)
            return rid

    def commit(self, rid: str | None, actual: float, provider: str, what: str) -> None:
        """Verbucht die tatsächlichen Kosten und löst die Reservierung auf."""
        if rid is None:
            return
        with self._guard:
            data = self._load()
            reserved = data["reservations"].pop(rid, None)
            amount = max(0.0, float(actual or 0.0))
            if reserved is None and amount <= 0:
                return
            data["spent_usd"] = round(float(data["spent_usd"]) + amount, 6)
            data["entries"].append({
                "at": now_iso(), "provider": provider, "what": what,
                "amount_usd": round(amount, 6), "estimated": True})
            data["entries"] = data["entries"][-500:]
            write_json_atomic(self.path, data)

    def release(self, rid: str | None) -> None:
        if rid is None:
            return
        with self._guard:
            data = self._load()
            if data["reservations"].pop(rid, None) is not None:
                write_json_atomic(self.path, data)

    def summary(self) -> dict:
        data = self._load()
        spent, reserved = float(data["spent_usd"]), self._reserved(data)
        return {"spent_usd": round(spent, 4), "reserved_usd": round(reserved, 4),
                "remaining_usd": round(max(0.0, self.limit - spent - reserved), 4),
                "budget_limit_usd": self.limit, "entries": data["entries"],
                "note": "Beträge sind Schätzungen auf Basis von Listenpreisen."}


def estimate_project(project: dict) -> dict:
    """Schätzt die Kosten eines vollständigen Renders (ohne Cache-Treffer)."""
    from .providers import get_image, get_voice

    items = []
    scenes = project.get("scenes") or []
    voice = project.get("voice") or {}
    try:
        vp = get_voice(voice.get("provider") or "none")
    except Exception:  # noqa: BLE001
        vp = None
    if vp is not None and vp.paid:
        chars = sum(len(s.get("voice_text") or s.get("text") or "") for s in scenes
                    if not s.get("audio_source"))
        items.append({"provider": vp.id, "what": f"Voice-over ({chars} Zeichen)",
                      "amount_usd": round(vp.estimate_cost(chars), 4)})
    ai_scenes = [s for s in scenes if (s.get("visual") or {}).get("mode") == "ai_image"]
    if ai_scenes:
        pid = (project.get("visuals") or {}).get("image_provider") or "openai_image"
        try:
            ip = get_image(pid)
            if ip.paid:
                items.append({"provider": ip.id, "what": f"KI-Bilder ({len(ai_scenes)})",
                              "amount_usd": round(ip.estimate_cost(len(ai_scenes)), 4)})
        except Exception:  # noqa: BLE001
            pass
    total = round(sum(i["amount_usd"] for i in items), 4)
    limit = float(project.get("budget_limit_usd") or 0.0)
    return {
        "currency": "USD", "is_estimate": True, "items": items, "total_usd": total,
        "budget_limit_usd": limit, "within_budget": total <= limit + 1e-9,
        "note": ("Schätzung auf Basis von Listenpreisen; lokale Verarbeitung ist "
                 "kostenlos. Bereits erzeugte Assets werden wiederverwendet."),
    }
