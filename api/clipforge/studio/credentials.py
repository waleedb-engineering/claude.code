"""API-Schlüssel der optionalen Provider setzen, löschen, prüfen.

Ablage: `.env` im Repo-Root (wird von scripts/start_local.sh geladen), Pfad
änderbar über CLIPFORGE_ENV_FILE. Schreiben ist atomar (tmp + rename), die
Datei bekommt die Rechte 0600, andere Einträge bleiben unverändert.

Sofortige Wirkung: Nach Setzen/Löschen wird `os.environ` des laufenden
Prozesses aktualisiert. Die Provider halten keine eigenen Clients oder
Schlüsselkopien — sie lesen den Schlüssel bei jedem Aufruf frisch. Eine bereits
laufende Anfrage behält den Schlüssel, mit dem sie gestartet ist; die nächste
nutzt den neuen. Schlüsselwerte erscheinen nie in Antworten oder Logs.
"""

from __future__ import annotations

import os
import re
import tempfile
import threading
import urllib.error
import urllib.request

from .errors import StudioError

# Provider-ID → (Variable, Label, Prüf-URL, Header-Bauer)
KNOWN = {
    "elevenlabs": ("ELEVENLABS_API_KEY", "ElevenLabs",
                   "https://api.elevenlabs.io/v1/user", lambda k: {"xi-api-key": k}),
    "openai": ("OPENAI_API_KEY", "OpenAI (TTS, Bilder)",
               "https://api.openai.com/v1/models", lambda k: {"Authorization": "Bearer " + k}),
    "anthropic": ("ANTHROPIC_API_KEY", "Anthropic (Skripte, Analyse)",
                  "https://api.anthropic.com/v1/models",
                  lambda k: {"x-api-key": k, "anthropic-version": "2023-06-01"}),
}
_lock = threading.Lock()
_LINE = re.compile(r"^\s*(?:export\s+)?([A-Za-z_][A-Za-z0-9_]*)\s*=")


def env_file() -> str:
    root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(
        os.path.abspath(__file__)))))
    return os.environ.get("CLIPFORGE_ENV_FILE") or os.path.join(root, ".env")


def _spec(provider: str):
    if provider not in KNOWN:
        raise StudioError("provider_unknown", f"Unbekannter Provider '{provider}'.", 404)
    return KNOWN[provider]


def _quote(value: str) -> str:
    """Bash-sichere Single-Quotes (die Datei wird per `source` geladen)."""
    return "'" + value.replace("'", "'\\''") + "'"


def _rewrite(name: str, value: str | None) -> bool:
    """Setzt/entfernt GENAU die Variable `name`. Liefert, ob sie vorher existierte."""
    path = env_file()
    try:
        with open(path, "r", encoding="utf-8") as fh:
            lines = fh.read().splitlines()
    except FileNotFoundError:
        lines = []
    kept, existed = [], False
    for line in lines:
        m = _LINE.match(line)
        if m and m.group(1) == name:  # exakter Name, kein Präfix-Vergleich
            existed = True
            continue
        kept.append(line)
    if value is not None:
        kept.append(f"{name}={_quote(value)}")
    directory = os.path.dirname(path) or "."
    os.makedirs(directory, exist_ok=True)
    fd, tmp = tempfile.mkstemp(prefix=".env.", suffix=".tmp", dir=directory)
    try:
        if hasattr(os, "fchmod"):  # Windows kennt fchmod erst ab Python 3.13
            os.fchmod(fd, 0o600)
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            fh.write("\n".join(kept) + ("\n" if kept else ""))
            fh.flush()
            os.fsync(fh.fileno())
        from .storage import replace_file
        replace_file(tmp, path)
        os.chmod(path, 0o600)
    finally:
        if os.path.exists(tmp):
            os.remove(tmp)
    return existed


def status() -> list[dict]:
    """Zustand je Provider — bezogen auf den LAUFENDEN Prozess."""
    return [{"provider": pid, "label": label, "env": name,
             "configured": bool(os.environ.get(name))}
            for pid, (name, label, _url, _hdr) in KNOWN.items()]


def set_key(provider: str, value: str) -> dict:
    name, label, _url, _hdr = _spec(provider)
    value = (value or "").strip()
    if len(value) < 8 or len(value) > 500 or any(c in value for c in "\r\n\x00"):
        raise StudioError("validation_error", "Der Schlüssel hat ein ungültiges Format.")
    with _lock:
        try:
            _rewrite(name, value)
        except OSError as exc:
            raise StudioError("credentials_store_failed",
                              "Der Schlüssel konnte nicht gespeichert werden.", 500) from exc
        os.environ[name] = value  # sofort wirksam, ohne Neustart
    return {"provider": provider, "label": label, "env": name, "configured": True}


def delete_key(provider: str) -> dict:
    name, label, _url, _hdr = _spec(provider)
    with _lock:
        try:
            in_file = _rewrite(name, None)
        except OSError as exc:
            raise StudioError("credentials_store_failed",
                              "Der Schlüssel konnte nicht entfernt werden.", 500) from exc
        in_env = os.environ.pop(name, None) is not None
    if not in_file and not in_env:
        raise StudioError("credential_not_set",
                          f"Für {label} war kein Schlüssel hinterlegt.", 404)
    return {"provider": provider, "label": label, "env": name, "configured": False}


def _http_get(url: str, headers: dict, timeout: float = 15.0) -> int:
    req = urllib.request.Request(url, headers=headers, method="GET")
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:  # noqa: S310 — feste Hosts
            return resp.status
    except urllib.error.HTTPError as exc:
        return exc.code


HTTP_GET = _http_get  # in Tests ersetzbar


def test_key(provider: str) -> dict:
    """Explizite Prüfung gegen den Provider (kostenloser Lese-Endpunkt)."""
    name, label, url, headers = _spec(provider)
    key = os.environ.get(name)
    if not key:
        raise StudioError("credential_not_set", f"Für {label} ist kein Schlüssel hinterlegt.", 409)
    try:
        code = HTTP_GET(url, headers(key))
    except Exception as exc:  # noqa: BLE001 — nie den Schlüssel in die Meldung
        return {"provider": provider, "ok": False, "reason": "unreachable",
                "message": f"{label} ist nicht erreichbar ({type(exc).__name__})."}
    if code in (401, 403):
        return {"provider": provider, "ok": False, "reason": "rejected",
                "message": f"{label} hat den Schlüssel abgelehnt (HTTP {code})."}
    if 200 <= code < 300:
        return {"provider": provider, "ok": True, "reason": "accepted",
                "message": f"{label} hat den Schlüssel akzeptiert."}
    return {"provider": provider, "ok": False, "reason": "unexpected",
            "message": f"{label} antwortete mit HTTP {code}."}
