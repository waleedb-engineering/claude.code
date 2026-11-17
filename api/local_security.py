"""Local-App-Schutz: enge CORS-Origins + Session-Token für mutierende Requests.

Bedrohung: Eine fremde Webseite im Browser des Nutzers schickt Requests an
http://127.0.0.1:8000 (löschen, rendern, kostenpflichtig generieren, Keys
setzen). Schutz:
  1. CORS nur für die lokalen Frontend-Origins (+ CLIPFORGE_ALLOWED_ORIGINS).
     Kein Wildcard.
  2. Jede mutierende Anfrage (alles außer GET/HEAD/OPTIONS) unter /api/ braucht
     den Header `X-ClipForge-Token`. Fehlt er → 401, falsch → 403.
  3. Requests mit fremdem `Origin`-Header werden bei Mutationen immer
     abgewiesen (403), auch mit Token.
  4. Das Token gibt es über GET /api/session nur für erlaubte Origins und nur,
     wenn der Host-Header lokal ist (Schutz vor DNS-Rebinding).
Das Token wird beim Start erzeugt bzw. aus einer 0600-Datei geladen und nie
geloggt oder in Projektdateien geschrieben.

Entwicklung/Tests: `CLIPFORGE_API_AUTH=off` schaltet NUR die Token-Pflicht ab;
die Origin-Prüfung bleibt aktiv. Nie setzen, wenn das Backend aus dem Netz
erreichbar ist.
"""

from __future__ import annotations

import hmac
import os
import secrets
from urllib.parse import urlsplit

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

TOKEN_HEADER = "X-ClipForge-Token"
SAFE_METHODS = {"GET", "HEAD", "OPTIONS"}
DEFAULT_ORIGINS = ("http://127.0.0.1:3000", "http://localhost:3000")
LOCAL_HOSTS = {"127.0.0.1", "localhost", "[::1]", "::1", "testserver"}


def allowed_origins() -> list[str]:
    extra = [o.strip().rstrip("/") for o in
             os.environ.get("CLIPFORGE_ALLOWED_ORIGINS", "").split(",") if o.strip()]
    out = []
    for origin in (*DEFAULT_ORIGINS, *extra):
        parts = urlsplit(origin)
        # Wildcards und Nicht-HTTP-Origins werden ignoriert (nie "*")
        if parts.scheme in ("http", "https") and parts.netloc and "*" not in origin \
                and origin not in out:
            out.append(origin)
    return out


def auth_enabled() -> bool:
    return os.environ.get("CLIPFORGE_API_AUTH", "on").strip().lower() != "off"


def token_path() -> str:
    return os.environ.get("CLIPFORGE_API_TOKEN_FILE") or os.path.join(
        os.path.dirname(os.path.abspath(__file__)), ".clipforge_api_token")


def load_or_create_token() -> str:
    """Token aus ENV, sonst aus 0600-Datei, sonst neu erzeugen und ablegen."""
    env = os.environ.get("CLIPFORGE_API_TOKEN", "").strip()
    if len(env) >= 16:
        return env
    path = token_path()
    try:
        with open(path, "r", encoding="utf-8") as fh:
            token = fh.read().strip()
        if len(token) >= 32:
            return token
    except OSError:
        pass
    token = secrets.token_urlsafe(32)
    try:
        fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            fh.write(token)
        os.chmod(path, 0o600)
    except OSError:
        pass  # nicht schreibbar → Token gilt nur für diesen Prozess
    return token


def _host_is_local(request: Request) -> bool:
    host = (request.headers.get("host") or "").rsplit(":", 1)[0].lower()
    return host in LOCAL_HOSTS


def _deny(status: int, code: str, message: str) -> JSONResponse:
    return JSONResponse(status_code=status, content={"detail": {"code": code, "message": message}})


def install(app: FastAPI) -> None:
    token = load_or_create_token()
    app.state.api_token = token

    @app.middleware("http")
    async def _guard(request: Request, call_next):
        if request.method not in SAFE_METHODS and request.url.path.startswith("/api/"):
            origin = request.headers.get("origin")
            if origin is not None and origin.rstrip("/") not in allowed_origins():
                return _deny(403, "origin_not_allowed",
                             "Diese Herkunft darf die lokale ClipForge-API nicht verändern.")
            if auth_enabled():
                sent = request.headers.get(TOKEN_HEADER)
                if not sent:
                    return _deny(401, "token_missing",
                                 f"Für diese Aktion fehlt der Header {TOKEN_HEADER}.")
                if not hmac.compare_digest(sent.encode("utf-8"), token.encode("utf-8")):
                    return _deny(403, "token_invalid", "Das API-Token ist ungültig.")
        return await call_next(request)

    # CORS zuletzt hinzufügen → äußerste Schicht (auch Fehlantworten bekommen Header)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=allowed_origins(),
        allow_credentials=False,
        allow_methods=["GET", "POST", "PATCH", "PUT", "DELETE", "OPTIONS"],
        allow_headers=["Content-Type", "Idempotency-Key", TOKEN_HEADER],
    )

    @app.get("/api/session")
    def session(request: Request):
        """Liefert das Token an das lokale Frontend (nie an fremde Origins)."""
        origin = request.headers.get("origin")
        if origin is not None and origin.rstrip("/") not in allowed_origins():
            return _deny(403, "origin_not_allowed", "Herkunft nicht erlaubt.")
        if not _host_is_local(request):
            return _deny(403, "host_not_local", "Nur über die lokale Adresse erreichbar.")
        return JSONResponse(
            content={"token": token if auth_enabled() else None,
                     "auth_required": auth_enabled(), "header": TOKEN_HEADER},
            headers={"Cache-Control": "no-store"})
