"""Gemeinsames Interface für Publishing-Plattform-Adapter.

Sicherheitsprinzip (siehe docs/YOUTUBE_PUBLISHING.md):
  - Adapter führen NIE unkontrolliert echte Uploads aus.
  - `dry_run()` ist immer erlaubt und löst NIEMALS einen Upload aus.
  - Der echte (private) Upload liegt bewusst NICHT im Adapter, sondern im
    dedizierten `YouTubeUploadService` (platforms/youtube_upload.py) — hinter
    Feature-Flag + expliziter Bestätigung + Idempotenz.
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
