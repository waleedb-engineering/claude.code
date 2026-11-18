"""Provider-Abstraktion des Studios (Voice, Bild; Slots für Video/Avatar).

Ein Provider meldet seinen Zustand selbst:
  ready           – nutzbar
  not_configured  – Zugangsdaten/Programm fehlen (setup_hint erklärt die Einrichtung)
  disabled        – per Feature Flag aus
  unavailable     – in dieser Version kein Adapter vorhanden
Secrets werden nur aus ENV gelesen und NIE zurückgegeben oder geloggt.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field


@dataclass
class VoiceResult:
    path: str
    cost_usd: float = 0.0
    # optionale echte Wort-Timings [(text, start, end)] relativ zum Audio
    words: list = field(default_factory=list)


class Provider:
    id = ""
    kind = ""            # voice | image | video | avatar | face_swap | voice_clone
    label = ""
    local = True
    paid = False
    env_keys: tuple[str, ...] = ()
    setup_hint = ""
    requires_flag: str | None = None

    def configured(self) -> bool:
        return all(os.environ.get(k) for k in self.env_keys)

    def status(self) -> tuple[str, str]:
        from ..flags import is_enabled
        if self.requires_flag and not is_enabled(self.requires_flag):
            return "disabled", f"Feature Flag '{self.requires_flag}' ist aus."
        if not self.configured():
            return "not_configured", self.setup_hint
        return "ready", ""

    def info(self) -> dict:
        state, hint = self.status()
        return {
            "id": self.id, "kind": self.kind, "label": self.label,
            "local": self.local, "paid": self.paid, "status": state,
            "hint": hint,
            # nur die NAMEN der benötigten Variablen — niemals Werte
            "requires_env": list(self.env_keys),
        }


class VoiceProvider(Provider):
    kind = "voice"
    languages: tuple[str, ...] = ("de", "en")
    produces_speech = True

    def voices(self, language: str) -> list[dict]:
        return []

    def estimate_cost(self, chars: int) -> float:
        return 0.0

    def synthesize(self, text: str, language: str, voice_id: str, out_path: str,
                   model: str | None = None, speed: float = 1.0) -> VoiceResult:
        raise NotImplementedError


class ImageProvider(Provider):
    kind = "image"

    def estimate_cost(self, images: int) -> float:
        return 0.0

    def generate(self, prompt: str, width: int, height: int, out_path: str) -> float:
        """Erzeugt ein Bild nach out_path, liefert die Kosten in USD."""
        raise NotImplementedError


class PlaceholderProvider(Provider):
    """Dokumentierter Slot ohne Adapter — ehrlich als 'unavailable' gemeldet."""

    def __init__(self, pid: str, kind: str, label: str, hint: str,
                 flag: str | None = None) -> None:
        self.id, self.kind, self.label, self.setup_hint = pid, kind, label, hint
        self.requires_flag = flag
        self.local = False

    def status(self) -> tuple[str, str]:
        return "unavailable", self.setup_hint
