"""Stabile Fehlercodes des Studios (API-Vertrag, siehe docs/API_STUDIO.md)."""

from __future__ import annotations


class StudioError(Exception):
    """Nutzer-/Zustandsfehler mit stabilem `code` und HTTP-Status."""

    def __init__(self, code: str, message: str, status: int = 400,
                 details: dict | None = None) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.status = status
        self.details = details or {}

    def to_dict(self) -> dict:
        out = {"code": self.code, "message": self.message}
        if self.details:
            out["details"] = self.details
        return out


class BudgetExceeded(StudioError):
    def __init__(self, message: str, details: dict | None = None) -> None:
        super().__init__("budget_exceeded", message, 409, details)


class ProviderError(Exception):
    """Technischer Provider-Ausfall (→ Fallback, nie Secrets im Text)."""

    def __init__(self, provider: str, message: str) -> None:
        super().__init__(f"{provider}: {message}")
        self.provider = provider
