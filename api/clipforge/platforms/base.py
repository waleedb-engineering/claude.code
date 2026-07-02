"""Gemeinsames Interface für Publishing-Plattform-Adapter.

Sicherheitsprinzip (siehe docs/YOUTUBE_PUBLISHING.md):
  - Adapter führen NIE unkontrolliert echte Uploads aus.
  - `dry_run()` ist immer erlaubt und löst NIEMALS einen Upload aus.
  - `publish()` ist standardmäßig blockiert (Feature-Flag, Credentials,
    Validierung, explizite Bestätigung) und gibt in dieser Phase bewusst
    keinen Fake-Erfolg zurück.
"""

from __future__ import annotations

from abc import ABC, abstractmethod


class PlatformAdapter(ABC):
    """Basis-Interface für alle Plattform-Adapter."""

    platform: str = "base"

    @abstractmethod
    def validate_draft(self, draft: dict) -> dict:
        """Prüft einen Draft plattformspezifisch → Validation-Summary-Dict."""
        raise NotImplementedError

    @abstractmethod
    def dry_run(self, draft: dict) -> dict:
        """Plant den Upload und gibt eine Vorschau zurück — OHNE Upload,
        OHNE Secrets, OHNE Token, OHNE Binär-Body."""
        raise NotImplementedError

    @abstractmethod
    def publish(
        self, draft: dict, *, confirm: str | None, privacy_status: str
    ) -> dict:
        """Versucht eine echte Veröffentlichung — nur wenn alle Sicherheits-
        bedingungen erfüllt sind. In der aktuellen Phase kein echter Upload."""
        raise NotImplementedError
