"""YouTube-OAuth-Flow-Skelett — Phase 2b (sicher, testbar, OHNE echten Upload).

Was dieses Modul tut:
  - Baut eine **echte, korrekte Consent-URL** für den OAuth-2.0-Authorization-
    Code-Flow einer Installed-/Desktop-App (Google), inkl. CSRF-`state` und PKCE.
  - Verwaltet kurzlebige `state`-Werte (consume-once, TTL, Wiederverwendungs-
    schutz) rein lokal im Prozess.
  - Verarbeitet den Callback: prüft `state`, ruft eine **austauschbare**
    `exchange_code_for_token`-Methode auf und speichert das Ergebnis NUR über
    den sicheren `YouTubeTokenStore` (Keychain, kein Plaintext).

Was dieses Modul bewusst NICHT tut:
  - KEIN echter Google-Netzwerk-Call (weder Consent noch Token-Exchange). Der
    reale Token-Exchange ist Phase 3 (offizielle Google-Library) und blockiert
    hier sauber. In Tests wird `exchange_code_for_token` gemockt.
  - KEIN echter Upload, KEIN `videos.insert`, KEIN automatisches Browser-Öffnen.
  - KEIN Token / KEIN client_secret in Rückgaben, Logs oder Exceptions.

Sicherheits-Invarianten (durch Tests abgesichert):
  - Consent-URL enthält nur den (nicht geheimen) `client_id`, NIE das
    `client_secret`. Das Secret wird aus der client_secrets-Datei NICHT gelesen.
  - `state` (CSRF) ist Pflicht, einmalig verwendbar und läuft ab.
  - PKCE-`code_verifier` bleibt serverseitig im State — er taucht NIE in einer
    Antwort auf.
  - Token-Payload wird vor der Speicherung validiert/sanitisiert.

Quellen (offizielle Google-Doku, abgerufen 2026-07-03):
  https://developers.google.com/identity/protocols/oauth2/native-app
  - Auth-Endpoint:  https://accounts.google.com/o/oauth2/v2/auth
  - Token-Endpoint: https://oauth2.googleapis.com/token
  - `response_type=code`, Loopback-Redirect `http://127.0.0.1:port`, `state`
    gegen CSRF, PKCE (`code_challenge`/`code_challenge_method`) empfohlen,
    Refresh-Tokens werden Installed-Apps immer ausgegeben (`access_type=offline`).
"""

from __future__ import annotations

import base64
import hashlib
import json
import os
import secrets
import time
from dataclasses import dataclass, field
from urllib.parse import urlencode

from .youtube_auth import REQUIRED_SCOPE, YouTubeTokenStore

# Offizielle Google-Endpoints (Fallbacks; die tatsächlichen Werte kommen — wenn
# vorhanden — aus der client_secrets-Datei, Feld `auth_uri`/`token_uri`).
GOOGLE_AUTH_ENDPOINT = "https://accounts.google.com/o/oauth2/v2/auth"
GOOGLE_TOKEN_ENDPOINT = "https://oauth2.googleapis.com/token"

# Nur Werte, die in einer sanitisierten Token-Payload behalten werden.
# (client_secret ist bewusst NICHT dabei — er gehört nicht in den Token-Store.)
_ALLOWED_TOKEN_FIELDS = (
    "access_token",
    "refresh_token",
    "token_type",
    "scope",
    "expiry",
    "expires_in",
    "id_token",
)


class OAuthError(Exception):
    """Basis für OAuth-Fehler. Nachrichten enthalten NIE Secrets/Codes/Tokens."""


class OAuthExchangeUnavailable(OAuthError):
    """Token-Exchange ist (noch) nicht verfügbar — z. B. Phase 3 nicht gebaut
    oder offizielle Google-Library fehlt. Blockiert sauber, ohne Secret-Leak."""


# --------------------------------------------------------------------------
# Konfiguration
# --------------------------------------------------------------------------

@dataclass
class YouTubeOAuthConfig:
    client_secrets_path: str | None
    redirect_uri: str
    scopes: tuple[str, ...]
    enabled: bool
    state_ttl_seconds: int

    @classmethod
    def from_settings(cls, settings) -> "YouTubeOAuthConfig":
        return cls(
            client_secrets_path=settings.youtube_client_secrets_file,
            redirect_uri=settings.youtube_oauth_redirect_uri,
            scopes=(REQUIRED_SCOPE,),  # minimal — bewusst NICHT erweitert
            enabled=bool(settings.enable_youtube_oauth),
            state_ttl_seconds=int(settings.youtube_oauth_state_ttl_seconds),
        )

    # -- sichere Metadaten (nie Dateiinhalt/Pfad-Leak) --------------------

    def client_secrets_configured(self) -> bool:
        """True nur, wenn ein Pfad gesetzt ist UND die Datei existiert. Der
        Inhalt wird für diesen Check NICHT gelesen."""
        p = self.client_secrets_path
        return bool(p) and os.path.exists(p)

    def client_secrets_basename(self) -> str | None:
        """Nur der Dateiname — nie der volle Pfad (Path-Traversal wird so
        neutralisiert: basename('../../x') == 'x')."""
        return os.path.basename(self.client_secrets_path) if self.client_secrets_path else None

    @property
    def scope_string(self) -> str:
        return " ".join(self.scopes)


# --------------------------------------------------------------------------
# State-Store (CSRF): kurzlebig, consume-once, kein Token
# --------------------------------------------------------------------------

@dataclass
class _StateEntry:
    expires_at: float
    code_verifier: str  # PKCE — bleibt serverseitig, NIE in Antworten
    used: bool = False


class OAuthStateStore:
    """Lokaler, kurzlebiger Speicher für OAuth-`state`-Werte.

    - Kein Token, kein Secret nach außen.
    - `create()` erzeugt einen zufälligen `state` + PKCE-`code_verifier`.
    - `consume()` gibt den Eintrag EINMALIG zurück und markiert ihn als
      benutzt → Wiederverwendung schlägt fehl; abgelaufene States ebenso.
    """

    def __init__(self) -> None:
        self._states: dict[str, _StateEntry] = {}

    def _now(self) -> float:
        return time.time()

    def _prune(self) -> None:
        now = self._now()
        for key in [k for k, e in self._states.items() if e.expires_at < now]:
            self._states.pop(key, None)

    def create(self, ttl_seconds: int) -> tuple[str, str, float]:
        """Erzeugt (state, code_challenge, expires_at). Der `code_verifier`
        bleibt intern; nach außen geht nur die (öffentliche) `code_challenge`."""
        self._prune()
        state = secrets.token_urlsafe(32)
        code_verifier = secrets.token_urlsafe(64)
        expires_at = self._now() + max(1, int(ttl_seconds))
        self._states[state] = _StateEntry(expires_at=expires_at, code_verifier=code_verifier)
        challenge = _pkce_challenge(code_verifier)
        return state, challenge, expires_at

    def consume(self, state: str | None) -> _StateEntry | None:
        """Gibt den Eintrag einmalig zurück (und entwertet ihn) — oder None,
        wenn unbekannt / abgelaufen / bereits verwendet."""
        if not state or not isinstance(state, str):
            return None
        self._prune()
        entry = self._states.get(state)
        if entry is None:
            return None
        if entry.used:
            return None
        if entry.expires_at < self._now():
            self._states.pop(state, None)
            return None
        entry.used = True  # consume-once → Wiederverwendung ab jetzt geblockt
        return entry

    def active_count(self) -> int:
        self._prune()
        return sum(1 for e in self._states.values() if not e.used)

    def clear(self) -> None:
        self._states.clear()


def _pkce_challenge(code_verifier: str) -> str:
    """S256-Code-Challenge aus dem Verifier (RFC 7636), base64url ohne Padding."""
    digest = hashlib.sha256(code_verifier.encode("ascii")).digest()
    return base64.urlsafe_b64encode(digest).decode("ascii").rstrip("=")


def _safe_error_code(error) -> str:
    """Reduziert einen (extern kontrollierten) OAuth-`error`-Wert auf eine
    kurze, harmlose Kennung — keine unkontrollierte Rückgabe an den Client."""
    if not isinstance(error, str):
        return "unknown"
    safe = "".join(ch for ch in error if ch.isalnum() or ch in "_-")[:40]
    return safe or "unknown"


# --------------------------------------------------------------------------
# Token-Payload-Sanitizing (Validierung vor Speicherung)
# --------------------------------------------------------------------------

def sanitize_token_payload(payload) -> dict | None:
    """Validiert & säubert eine Token-Payload vor der Speicherung.

    - Muss ein nicht-leeres Dict sein.
    - Muss mindestens einen brauchbaren Token-Wert enthalten (`access_token`
      ODER `refresh_token`, nicht-leerer String).
    - Behält NUR bekannte Felder (Whitelist) mit primitivem Typ.
    - Fügt `stored_at` (Zeitstempel) hinzu.

    Gibt `None` zurück, wenn die Payload ungültig ist (→ nichts speichern).
    Loggt/druckt NIE Werte.
    """
    if not isinstance(payload, dict) or not payload:
        return None

    def _nonempty_str(v) -> bool:
        return isinstance(v, str) and v.strip() != ""

    if not (_nonempty_str(payload.get("access_token")) or _nonempty_str(payload.get("refresh_token"))):
        return None

    clean: dict = {}
    for key in _ALLOWED_TOKEN_FIELDS:
        if key in payload:
            val = payload[key]
            if isinstance(val, (str, int, float, bool)):
                clean[key] = val
    if not clean:
        return None
    clean["stored_at"] = int(time.time())
    return clean


# --------------------------------------------------------------------------
# Service
# --------------------------------------------------------------------------

# Reasons, die ein 400 auslösen (State/Eingabe-Probleme).
CALLBACK_BAD_REQUEST_REASONS = frozenset(
    {"missing_code", "missing_state", "invalid_state"}
)


class YouTubeOAuthService:
    """Isolierter OAuth-Service. Alle Netzwerk-relevanten Schritte sind
    austauschbar/mockbar; ohne Mock passiert KEIN echter Google-Call."""

    def __init__(
        self,
        config: YouTubeOAuthConfig,
        token_store: YouTubeTokenStore,
        state_store: OAuthStateStore,
        exchanger=None,
    ) -> None:
        self.config = config
        self.token_store = token_store
        self.state_store = state_store
        # `exchanger(config, code, code_verifier) -> dict` — injizierbar.
        # None → exchange blockiert sauber (Phase 3 / keine Google-Library).
        self._exchanger = exchanger

    # -- Readiness --------------------------------------------------------

    def readiness(self) -> dict:
        """Sichere OAuth-Status-Übersicht — NIE Token/Secrets."""
        store_available = self.token_store.is_available()
        summary = self.token_store.get_summary()
        creds = self.config.client_secrets_configured()

        blocked_reasons: list[str] = []
        warnings: list[str] = []
        if not self.config.enabled:
            blocked_reasons.append("oauth_disabled")
        if not creds:
            blocked_reasons.append("client_secrets_missing")
        if not store_available:
            blocked_reasons.append("token_store_unavailable")

        if store_available and summary["token_status"] == "invalid_token":
            warnings.append("stored_token_unreadable_or_corrupt")

        can_start_auth = bool(self.config.enabled and creds and store_available)

        return {
            "oauth_enabled": self.config.enabled,
            "client_secrets_configured": creds,
            "client_secrets_basename": self.config.client_secrets_basename(),
            "redirect_uri": self.config.redirect_uri,  # kein Secret (Loopback-URL)
            "scopes": list(self.config.scopes),
            "required_scope": REQUIRED_SCOPE,
            "state_ttl_seconds": self.config.state_ttl_seconds,
            "token_store_available": store_available,
            "token_present": summary["token_present"],
            "token_status": summary["token_status"],
            "can_start_auth": can_start_auth,
            "can_attempt_upload": False,  # bleibt in dieser Phase IMMER False
            "blocked_reasons": blocked_reasons,
            "warnings": warnings,
            "no_secrets": True,
        }

    # -- Auth-Start (Consent-URL) ----------------------------------------

    def start_auth(self) -> dict:
        """Erzeugt eine Consent-URL (kein Browser, kein Netzwerk-Call).

        Blockiert sauber, wenn OAuth aus, Credentials fehlen oder der
        Token-Store nicht verfügbar ist. Antwort enthält NIE Secrets."""
        rd = self.readiness()
        result: dict = {
            "enabled": self.config.enabled,
            "state_created": False,
            "auth_url": None,
            "expires_at": None,
            "blocked_reasons": [],
            "warnings": list(rd["warnings"]),
            "message": "",
            "no_secrets": True,
        }

        if not self.config.enabled:
            result["blocked_reasons"] = ["oauth_disabled"]
            result["message"] = (
                "YouTube-OAuth ist deaktiviert. Setze CLIPFORGE_ENABLE_YOUTUBE_OAUTH=true."
            )
            return result
        if not self.config.client_secrets_configured():
            result["blocked_reasons"] = ["client_secrets_missing"]
            result["message"] = (
                "OAuth-Client-Secrets fehlen. Setze CLIPFORGE_YOUTUBE_CLIENT_SECRETS "
                "auf den Pfad deiner client_secrets.json."
            )
            return result
        if not self.token_store.is_available():
            # Ohne sichere Ablage kein Auth-Start (Token dürfte nirgends landen).
            result["blocked_reasons"] = ["token_store_unavailable"]
            result["message"] = (
                "Kein sicherer Token-Store (Keychain) verfügbar — installiere "
                "'keyring'. Kein Plaintext-Fallback."
            )
            return result

        client = self._read_client_info()
        if client is None:
            result["blocked_reasons"] = ["client_secrets_unreadable"]
            result["message"] = (
                "client_secrets-Datei ist unlesbar oder unvollständig "
                "(kein client_id/auth_uri gefunden)."
            )
            return result

        client_id, auth_uri = client
        state, challenge, expires_at = self.state_store.create(self.config.state_ttl_seconds)
        auth_url = self._build_consent_url(auth_uri, client_id, state, challenge)

        result.update(
            state_created=True,
            auth_url=auth_url,
            expires_at=expires_at,
            message=(
                "Öffne diese URL manuell im Browser, melde dich bei Google an "
                "und kehre über den Callback zurück. Es wird KEIN Browser "
                "automatisch geöffnet und KEIN Upload durchgeführt."
            ),
        )
        return result

    def _read_client_info(self) -> tuple[str, str] | None:
        """Liest NUR client_id + auth_uri aus der client_secrets-Datei.

        Das `client_secret` wird bewusst NICHT ausgelesen. Bei jedem Fehler
        (Datei fehlt, kaputtes JSON, fehlende Felder) → None, ohne Leak."""
        path = self.config.client_secrets_path
        if not path:
            return None
        try:
            with open(path, "r", encoding="utf-8") as fh:
                data = json.load(fh)
        except Exception:  # noqa: BLE001 — nie Details/Pfad propagieren
            return None
        # Google-Format: {"installed": {...}} (Desktop) oder {"web": {...}}.
        section = None
        if isinstance(data, dict):
            section = data.get("installed") or data.get("web")
        if not isinstance(section, dict):
            return None
        client_id = section.get("client_id")
        if not isinstance(client_id, str) or not client_id.strip():
            return None
        auth_uri = section.get("auth_uri")
        if not isinstance(auth_uri, str) or not auth_uri.startswith("https://"):
            auth_uri = GOOGLE_AUTH_ENDPOINT
        return client_id, auth_uri

    def _build_consent_url(self, auth_uri: str, client_id: str, state: str, challenge: str) -> str:
        params = {
            "client_id": client_id,          # NICHT geheim (gehört per Design in die URL)
            "redirect_uri": self.config.redirect_uri,
            "response_type": "code",
            "scope": self.config.scope_string,
            "state": state,                  # CSRF-Schutz
            "code_challenge": challenge,      # PKCE (S256)
            "code_challenge_method": "S256",
            "access_type": "offline",        # Refresh-Token anfordern
            "prompt": "consent",
            "include_granted_scopes": "true",
        }
        return f"{auth_uri}?{urlencode(params)}"

    # -- Callback ---------------------------------------------------------

    def handle_callback(self, code: str | None, state: str | None, error: str | None = None) -> dict:
        """Verarbeitet den OAuth-Callback sicher.

        Reihenfolge: `error` → Pflichtfelder → `state` (consume-once) →
        `exchange_code_for_token` → sanitize → `token_store.save_token`.
        Speichert bei JEDEM Fehler NICHTS und gibt NIE Token/Secrets zurück."""
        base = {
            "success": False,
            "token_stored": False,
            "message": "",
            "next_step": "",
            "reason": "",
            "no_secrets": True,
        }

        if error:
            return {
                **base,
                "reason": "oauth_error",
                "message": f"OAuth wurde nicht abgeschlossen (Grund: {_safe_error_code(error)}).",
                "next_step": "Starte den OAuth-Vorgang erneut.",
            }
        if not code or not isinstance(code, str):
            return {**base, "reason": "missing_code",
                    "message": "Kein Autorisierungscode übergeben."}
        if not state or not isinstance(state, str):
            return {**base, "reason": "missing_state",
                    "message": "Kein state übergeben (CSRF-Schutz)."}

        entry = self.state_store.consume(state)
        if entry is None:
            return {
                **base,
                "reason": "invalid_state",
                "message": "state ist ungültig, abgelaufen oder wurde bereits verwendet.",
                "next_step": "Starte den OAuth-Vorgang erneut.",
            }

        # Token-Exchange (austauschbar/mockbar). Ohne Mock → sauber blockiert.
        try:
            raw = self.exchange_code_for_token(code, entry.code_verifier)
        except OAuthExchangeUnavailable:
            return {
                **base,
                "reason": "exchange_unavailable",
                "message": (
                    "Token-Austausch ist in dieser Phase nicht implementiert "
                    "(Phase 3: echter Google-Exchange mit offizieller Library)."
                ),
                "next_step": "Kein Token gespeichert. Upload bleibt deaktiviert.",
            }
        except Exception:  # noqa: BLE001 — nie Details/Secret nach außen
            return {**base, "reason": "exchange_failed",
                    "message": "Token-Austausch fehlgeschlagen."}

        saved = self.save_token(raw)
        if not saved.get("ok"):
            return {
                **base,
                "reason": saved.get("reason", "invalid_token_payload"),
                "message": "Token-Payload ungültig oder Speicherung fehlgeschlagen — nichts gespeichert.",
            }

        return {
            "success": True,
            "token_stored": True,
            "message": "YouTube-Token wurde sicher im Keychain gespeichert.",
            "next_step": "Upload bleibt in dieser Phase deaktiviert (not_implemented).",
            "reason": "",
            "no_secrets": True,
        }

    # -- austauschbarer Token-Exchange (Phase 3 / Tests mocken das) -------

    def exchange_code_for_token(self, code: str, code_verifier: str) -> dict:
        """Tauscht einen Authorization-Code gegen ein Token.

        In dieser Phase gibt es KEINE eingebaute reale Implementierung: ohne
        injizierten `exchanger` wird sauber blockiert (kein Netzwerk-Call).
        Der reale Exchange (offizielle Google-Library, Token-Endpoint
        `https://oauth2.googleapis.com/token`) ist Phase 3.

        Tests injizieren einen `exchanger`, der ein Fake-Token liefert."""
        if self._exchanger is None:
            raise OAuthExchangeUnavailable("token_exchange_not_implemented")
        return self._exchanger(self.config, code, code_verifier)

    # -- sichere Token-Speicherung ---------------------------------------

    def save_token(self, token_payload) -> dict:
        """Sanitisiert die Payload und speichert sie NUR über den sicheren
        Token-Store. Kein Plaintext-Fallback. Gibt nie das Token zurück."""
        clean = self.sanitize_token_payload(token_payload)
        if clean is None:
            return {"ok": False, "reason": "invalid_token_payload"}
        return self.token_store.save_token(clean)

    def sanitize_token_payload(self, token_payload) -> dict | None:
        return sanitize_token_payload(token_payload)
