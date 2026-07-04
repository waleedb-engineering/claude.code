"""Sichere YouTube-OAuth-Token-Ablage — Phase 2 (nur Readiness, KEIN Upload).

Speichermodell (Option B aus docs/YOUTUBE_PUBLISHING.md):
  - Tokens NUR über das OS-Keychain via `keyring`.
  - KEIN Plaintext-Fallback, KEINE Datei mit Klartext-Token.
  - Ist `keyring` nicht installiert ODER kein nutzbares Backend vorhanden,
    gilt der Store als NICHT verfügbar → Readiness meldet „blocked".

Sicherheitsgarantien dieses Moduls:
  - Es werden NIE Token-Werte geloggt, gedruckt oder zurückgegeben.
  - `get_status()` / API-Antworten enthalten nur Status-Strings, keine Secrets.
  - `delete_token()` ist idempotent und leakt keine Token-Daten.

Der eigentliche OAuth-Flow (Browser/Google-Login) ist in dieser Phase NICHT
implementiert. `save_token()` existiert als sichere Schnittstelle für Phase 3,
wird aber vom API-Layer noch nicht mit echten Tokens aufgerufen.
"""

from __future__ import annotations

import json

# Minimaler benötigter Scope — bewusst NICHT erweitert.
REQUIRED_SCOPE = "https://www.googleapis.com/auth/youtube.upload"

# Token-Status-Werte (nach außen sichtbar, enthalten nie Secrets).
STATUS_BLOCKED = "blocked"                # kein nutzbares Keychain-Backend
STATUS_NOT_AUTHENTICATED = "not_authenticated"  # Store da, aber kein Token
STATUS_AUTHENTICATED = "authenticated"    # Token vorhanden & lesbar
STATUS_INVALID = "invalid_token"          # Token vorhanden, aber unbrauchbar


def _load_keyring():
    """Lazy-Import von keyring. Gibt das Modul oder None zurück (nie Fehler)."""
    try:
        import keyring  # type: ignore
        return keyring
    except Exception:  # noqa: BLE001 — Absenz/Defekt darf nie propagieren
        return None


class YouTubeTokenStore:
    """Keyring-gestützte, sichere Ablage für das YouTube-OAuth-Token."""

    def __init__(self, service_name: str, account: str):
        self.service_name = service_name
        self.account = account

    # ---- Verfügbarkeit ---------------------------------------------------

    def is_available(self) -> bool:
        """True nur, wenn keyring importierbar ist UND ein nutzbares Backend
        existiert (nicht das 'fail'-Backend)."""
        kr = _load_keyring()
        if kr is None:
            return False
        try:
            backend = kr.get_keyring()
        except Exception:  # noqa: BLE001
            return False
        module = (getattr(type(backend), "__module__", "") or "").lower()
        name = (getattr(type(backend), "__name__", "") or "").lower()
        # Das Fail-Backend signalisiert „kein Keychain vorhanden".
        if "fail" in module or name == "keyring":
            return False
        return True

    # ---- Lesen -----------------------------------------------------------

    def _read_raw(self) -> str | None:
        kr = _load_keyring()
        if kr is None:
            return None
        return kr.get_password(self.service_name, self.account)

    def has_token(self) -> bool:
        if not self.is_available():
            return False
        try:
            return self._read_raw() is not None
        except Exception:  # noqa: BLE001
            return False

    def read_token(self) -> dict | None:
        """Gibt die gespeicherte Token-Payload als Dict zurück (oder None).

        Für den Upload-/Refresh-Pfad nötig, um Credentials zu rekonstruieren.
        Loggt/druckt NIE den Inhalt. Bei fehlendem Store/kaputtem JSON → None."""
        if not self.is_available():
            return None
        try:
            raw = self._read_raw()
        except Exception:  # noqa: BLE001
            return None
        if raw is None:
            return None
        try:
            data = json.loads(raw)
        except (ValueError, TypeError):
            return None
        return data if isinstance(data, dict) and data else None

    def get_status(self) -> str:
        """blocked | not_authenticated | authenticated | invalid_token.
        Gibt NIE Token-Inhalte zurück — nur einen Status-String."""
        if not self.is_available():
            return STATUS_BLOCKED
        try:
            raw = self._read_raw()
        except Exception:  # noqa: BLE001 — unlesbares Backend
            return STATUS_INVALID
        if raw is None:
            return STATUS_NOT_AUTHENTICATED
        # Korruptions-Check: erwartetes Format ist ein nicht-leeres JSON-Objekt.
        try:
            data = json.loads(raw)
        except (ValueError, TypeError):
            return STATUS_INVALID
        if not isinstance(data, dict) or not data:
            return STATUS_INVALID
        return STATUS_AUTHENTICATED

    # ---- Schreiben / Löschen --------------------------------------------

    def save_token(self, token: dict) -> dict:
        """Speichert ein Token-Dict sicher (Phase 3). Gibt nur Status zurück,
        NIE das Token selbst. Kein Plaintext-Fallback."""
        if not self.is_available():
            return {"ok": False, "reason": "token_store_unavailable"}
        if not isinstance(token, dict) or not token:
            return {"ok": False, "reason": "invalid_token_payload"}
        kr = _load_keyring()
        try:
            kr.set_password(self.service_name, self.account, json.dumps(token))
        except Exception:  # noqa: BLE001
            return {"ok": False, "reason": "token_store_write_failed"}
        return {"ok": True}

    def delete_token(self) -> dict:
        """Löscht das Token idempotent. Leakt keine Token-Daten."""
        if not self.is_available():
            return {"deleted": False, "reason": "token_store_unavailable"}
        kr = _load_keyring()
        try:
            existed = self._read_raw() is not None
        except Exception:  # noqa: BLE001
            existed = True  # unlesbar → trotzdem Löschversuch
        try:
            kr.delete_password(self.service_name, self.account)
            return {"deleted": True}
        except Exception:  # noqa: BLE001 — z. B. PasswordDeleteError bei Absenz
            # Idempotent: war ohnehin nichts da → Erfolg ohne Leak.
            if not existed:
                return {"deleted": False, "reason": "no_token"}
            return {"deleted": False, "reason": "delete_failed"}

    # ---- Kompakter Status für Readiness ----------------------------------

    def get_summary(self) -> dict:
        status = self.get_status()
        return {
            "store_available": self.is_available(),
            "token_present": status == STATUS_AUTHENTICATED,
            "token_status": status,
        }
