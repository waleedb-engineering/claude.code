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


class CostLedger:
    """Persistentes Kostenbuch eines Projekts (`costs.json`)."""

    def __init__(self, project_dir: str, budget_limit_usd: float) -> None:
        self.path = os.path.join(project_dir, "costs.json")
        self.limit = max(0.0, float(budget_limit_usd or 0.0))

    def _load(self) -> dict:
        data = read_json(self.path, None)
        if not isinstance(data, dict):
            data = {"spent_usd": 0.0, "entries": []}
        return data

    @property
    def spent(self) -> float:
        return float(self._load().get("spent_usd") or 0.0)

    def ensure_can_spend(self, amount: float, what: str) -> None:
        if amount <= 0:
            return
        spent = self.spent
        if spent + amount > self.limit + 1e-9:
            raise BudgetExceeded(
                f"Budgetlimit erreicht: {what} würde ca. {amount:.2f} USD kosten, "
                f"verbraucht sind {spent:.2f} von {self.limit:.2f} USD. Es wurden keine "
                f"weiteren Kosten ausgelöst.",
                {"needed_usd": round(amount, 4), "spent_usd": round(spent, 4),
                 "budget_limit_usd": self.limit})

    def charge(self, amount: float, provider: str, what: str) -> None:
        if amount <= 0:
            return
        with _lock:
            data = self._load()
            data["spent_usd"] = round(float(data.get("spent_usd") or 0.0) + amount, 6)
            data.setdefault("entries", []).append({
                "at": now_iso(), "provider": provider, "what": what,
                "amount_usd": round(amount, 6), "estimated": True})
            write_json_atomic(self.path, data)

    def summary(self) -> dict:
        data = self._load()
        return {"spent_usd": round(float(data.get("spent_usd") or 0.0), 4),
                "budget_limit_usd": self.limit, "entries": data.get("entries") or [],
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
