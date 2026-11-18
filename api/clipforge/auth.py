"""Benutzeranmeldung für den Online-Betrieb (`CLIPFORGE_AUTH=accounts`).

Ohne diese Einstellung bleibt alles wie bisher (lokaler Modus mit
Session-Token, siehe local_security.py).

- Passwörter: scrypt (n=2^15, r=8, p=1, 16-Byte-Salt), Vergleich zeitkonstant.
- Sitzungen: 32 zufällige Bytes im HttpOnly-Cookie; gespeichert wird nur der
  SHA-256-Hash. Jede Sitzung hat ein eigenes CSRF-Token für Änderungen.
- Ratenbegrenzung: Login je IP und je Benutzername; allgemeine Anfragen je
  Sitzung bzw. IP.
- Daten: ein gemeinsamer Arbeitsbereich für alle Konten (KEINE Trennung
  zwischen Benutzern) — gedacht für den privaten Online-Betrieb.
"""

from __future__ import annotations

import hashlib
import hmac
import os
import re
import secrets
import threading
import time

COOKIE = "cf_session"
SESSION_DAYS = 14
MIN_PASSWORD = 12
_USER_RE = re.compile(r"^[a-z0-9_.-]{3,40}$")
_lock = threading.RLock()


def accounts_mode() -> bool:
    return os.environ.get("CLIPFORGE_AUTH", "local").strip().lower() == "accounts"


def auth_dir() -> str:
    from .studio.storage import studio_dir
    path = os.environ.get("CLIPFORGE_AUTH_DIR") or os.path.join(studio_dir(), "auth")
    os.makedirs(path, exist_ok=True)
    try:
        os.chmod(path, 0o700)
    except OSError:
        pass
    return path


def _users_path() -> str:
    return os.path.join(auth_dir(), "users.json")


def _sessions_path() -> str:
    return os.path.join(auth_dir(), "sessions.json")


class AuthError(Exception):
    def __init__(self, code: str, message: str, status: int = 400) -> None:
        super().__init__(message)
        self.code, self.message, self.status = code, message, status


# ------------------------------------------------------------------ Passwörter

def hash_password(password: str) -> str:
    salt = secrets.token_bytes(16)
    digest = hashlib.scrypt(password.encode("utf-8"), salt=salt, n=2 ** 15, r=8, p=1,
                            maxmem=64 * 1024 * 1024, dklen=32)
    return f"scrypt$32768$8$1${salt.hex()}${digest.hex()}"


def verify_password(password: str, stored: str) -> bool:
    try:
        algo, n, r, p, salt, digest = stored.split("$")
        if algo != "scrypt":
            return False
        candidate = hashlib.scrypt(password.encode("utf-8"), salt=bytes.fromhex(salt),
                                   n=int(n), r=int(r), p=int(p),
                                   maxmem=64 * 1024 * 1024, dklen=len(bytes.fromhex(digest)))
    except (ValueError, TypeError):
        return False
    return hmac.compare_digest(candidate, bytes.fromhex(digest))


# Für Logins mit unbekanntem Namen: gleiche Rechenzeit wie bei echten Konten
_DUMMY_HASH = None


def _dummy_hash() -> str:
    global _DUMMY_HASH
    if _DUMMY_HASH is None:
        _DUMMY_HASH = hash_password(secrets.token_urlsafe(16))
    return _DUMMY_HASH


def _validate_password(password: str) -> None:
    if not isinstance(password, str) or len(password) < MIN_PASSWORD or len(password) > 256:
        raise AuthError("weak_password",
                        f"Das Passwort muss mindestens {MIN_PASSWORD} Zeichen lang sein.")


# ------------------------------------------------------------------ Benutzer

def _read(path: str) -> dict:
    from .studio.storage import read_json
    data = read_json(path, {})
    return data if isinstance(data, dict) else {}


def _write(path: str, data: dict) -> None:
    from .studio.storage import write_json_atomic
    write_json_atomic(path, data)
    try:
        os.chmod(path, 0o600)
    except OSError:
        pass


def list_users() -> list[dict]:
    return [{"username": u, "created_at": d.get("created_at")}
            for u, d in sorted(_read(_users_path()).items())]


def create_user(username: str, password: str) -> dict:
    username = (username or "").strip().lower()
    if not _USER_RE.match(username):
        raise AuthError("invalid_username",
                        "Benutzername: 3–40 Zeichen, nur a–z, 0–9, Punkt, Strich, Unterstrich.")
    _validate_password(password)
    with _lock:
        users = _read(_users_path())
        if username in users:
            raise AuthError("user_exists", "Diesen Benutzer gibt es schon.", 409)
        users[username] = {"password": hash_password(password),
                           "created_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())}
        _write(_users_path(), users)
    return {"username": username}


def change_password(username: str, old: str, new: str) -> None:
    with _lock:
        users = _read(_users_path())
        user = users.get(username)
        if not user or not verify_password(old, user["password"]):
            raise AuthError("invalid_credentials", "Das bisherige Passwort stimmt nicht.", 403)
        _validate_password(new)
        user["password"] = hash_password(new)
        _write(_users_path(), users)
    revoke_user_sessions(username)  # überall abmelden


# ------------------------------------------------------------------ Sitzungen

def _token_hash(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def login(username: str, password: str) -> tuple[str, dict]:
    username = (username or "").strip().lower()
    users = _read(_users_path())
    user = users.get(username)
    ok = verify_password(password or "", user["password"] if user else _dummy_hash())
    if not user or not ok:
        raise AuthError("invalid_credentials", "Benutzername oder Passwort ist falsch.", 401)
    token = secrets.token_urlsafe(32)
    session = {"username": username, "csrf": secrets.token_urlsafe(32),
               "created": time.time(), "expires": time.time() + SESSION_DAYS * 86400}
    with _lock:
        sessions = {k: v for k, v in _read(_sessions_path()).items()
                    if v.get("expires", 0) > time.time()}
        sessions[_token_hash(token)] = session
        _write(_sessions_path(), sessions)
    return token, session


def session_for(token: str | None) -> dict | None:
    if not token or len(token) > 200:
        return None
    session = _read(_sessions_path()).get(_token_hash(token))
    if not session or session.get("expires", 0) <= time.time():
        return None
    if session.get("username") not in _read(_users_path()):
        return None  # Konto gelöscht → Sitzung ungültig
    return session


def logout(token: str | None) -> None:
    if not token:
        return
    with _lock:
        sessions = _read(_sessions_path())
        if sessions.pop(_token_hash(token), None) is not None:
            _write(_sessions_path(), sessions)


def revoke_user_sessions(username: str) -> None:
    with _lock:
        sessions = _read(_sessions_path())
        kept = {k: v for k, v in sessions.items() if v.get("username") != username}
        if len(kept) != len(sessions):
            _write(_sessions_path(), kept)


# ------------------------------------------------------------ Ratenbegrenzung

class RateLimiter:
    """Gleitendes Fenster im Speicher (pro Prozess)."""

    def __init__(self) -> None:
        self._hits: dict[str, list[float]] = {}
        self._guard = threading.Lock()

    def allow(self, key: str, limit: int, window: float) -> bool:
        now = time.monotonic()
        with self._guard:
            hits = [t for t in self._hits.get(key, []) if now - t < window]
            if len(hits) >= limit:
                self._hits[key] = hits
                return False
            hits.append(now)
            self._hits[key] = hits
            if len(self._hits) > 50_000:  # Speicher begrenzen
                self._hits = {k: v for k, v in self._hits.items() if v and now - v[-1] < window}
            return True

    def reset(self) -> None:
        with self._guard:
            self._hits.clear()


limiter = RateLimiter()


def _env_int(name: str, default: int) -> int:
    try:
        return max(1, int(os.environ.get(name, default)))
    except ValueError:
        return default


def login_allowed(ip: str, username: str) -> bool:
    """Max. 5 Versuche je Benutzername und 20 je IP in 15 Minuten."""
    name = (username or "").strip().lower()[:60]
    return (limiter.allow(f"login-ip:{ip}", 20, 900)
            and limiter.allow(f"login-user:{name}", 5, 900))


def request_allowed(key: str) -> bool:
    return limiter.allow(f"req:{key}", _env_int("CLIPFORGE_RATE_LIMIT_PER_MIN", 600), 60)


def client_ip(headers, peer: str | None) -> str:
    """Hinter einem vertrauenswürdigen Proxy (CLIPFORGE_TRUST_PROXY=1) zählt
    X-Forwarded-For, sonst die direkte Gegenstelle."""
    if os.environ.get("CLIPFORGE_TRUST_PROXY") == "1":
        fwd = (headers.get("x-forwarded-for") or "").split(",")[0].strip()
        if fwd:
            return fwd[:64]
    return (peer or "unknown")[:64]


def cookie_secure() -> bool:
    return os.environ.get("CLIPFORGE_COOKIE_SECURE", "1") != "0"


# ------------------------------------------------------------------- CLI

def _cli(argv: list[str] | None = None) -> int:
    import argparse
    import getpass
    parser = argparse.ArgumentParser(prog="python -m clipforge.auth",
                                     description="Konten für den Online-Betrieb verwalten.")
    sub = parser.add_subparsers(dest="cmd", required=True)
    c = sub.add_parser("create-user", help="Konto anlegen (Passwort wird abgefragt)")
    c.add_argument("username")
    sub.add_parser("list-users")
    r = sub.add_parser("reset-password", help="Passwort neu setzen (meldet überall ab)")
    r.add_argument("username")
    args = parser.parse_args(argv)
    try:
        if args.cmd == "list-users":
            for user in list_users():
                print(user["username"], user["created_at"])
            return 0
        password = os.environ.get("CLIPFORGE_NEW_PASSWORD") or getpass.getpass("Passwort: ")
        if not os.environ.get("CLIPFORGE_NEW_PASSWORD") and getpass.getpass("Wiederholen: ") != password:
            print("Die Passwörter stimmen nicht überein.")
            return 1
        if args.cmd == "create-user":
            create_user(args.username, password)
            print(f"Konto '{args.username.lower()}' angelegt.")
        else:
            _validate_password(password)
            with _lock:
                users = _read(_users_path())
                if args.username.lower() not in users:
                    print("Unbekannter Benutzer.")
                    return 1
                users[args.username.lower()]["password"] = hash_password(password)
                _write(_users_path(), users)
            revoke_user_sessions(args.username.lower())
            print("Passwort gesetzt, alle Sitzungen beendet.")
        return 0
    except AuthError as exc:
        print(exc.message)
        return 1


if __name__ == "__main__":
    raise SystemExit(_cli())
