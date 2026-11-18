"""Dateiablage des Studios: sichere IDs/Pfade + atomare JSON-Schreibvorgänge."""

from __future__ import annotations

import datetime
import json
import os
import re
import threading
import uuid

from .errors import StudioError

_ID_RE = re.compile(r"^[a-f0-9]{12}$")
_NAME_RE = re.compile(r"[^A-Za-z0-9._-]+")
_write_lock = threading.Lock()


def studio_dir() -> str:
    """Wurzel der Studio-Daten (ENV live gelesen → testbar)."""
    default = os.path.join(
        os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
        "studio_data",
    )
    path = os.path.abspath(os.environ.get("CLIPFORGE_STUDIO_DIR", default))
    from .workspace import current
    user = current()
    if user:  # getrennter Benutzerbereich (Online-Betrieb)
        if not re.fullmatch(r"[a-z0-9_.-]{3,40}", user) or user.startswith("."):
            raise ValueError("ungültiger Benutzerbereich")
        path = os.path.join(path, "users", user)
    os.makedirs(path, exist_ok=True)
    return path


def studio_root() -> str:
    """Gemeinsame Wurzel (Anmeldung, lokale Modelle) — unabhängig vom Benutzer."""
    default = os.path.join(
        os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
        "studio_data",
    )
    path = os.path.abspath(os.environ.get("CLIPFORGE_STUDIO_DIR", default))
    os.makedirs(path, exist_ok=True)
    return path


def now_iso() -> str:
    return datetime.datetime.now(datetime.timezone.utc).isoformat(timespec="seconds")


def new_id() -> str:
    return uuid.uuid4().hex[:12]


def is_safe_id(value) -> bool:
    return isinstance(value, str) and bool(_ID_RE.match(value))


def require_id(value, what: str = "ID") -> str:
    if not is_safe_id(value):
        raise StudioError("invalid_id", f"Ungültige {what}.", 400)
    return value


def safe_child(base: str, *parts: str) -> str:
    """Pfad strikt unterhalb von `base` (blockt Traversal/absolute Pfade/Symlinks)."""
    for p in parts:
        if not p or os.path.isabs(p) or "\x00" in p:
            raise StudioError("unsafe_path", "Ungültiger Pfad.", 400)
    root = os.path.realpath(base)
    target = os.path.realpath(os.path.join(root, *parts))
    if target == root or os.path.commonpath([root, target]) != root:
        raise StudioError("unsafe_path", "Pfad außerhalb des erlaubten Ordners.", 400)
    return target


def safe_filename(name: str, default: str = "datei") -> str:
    """Reduziert einen Upload-Namen auf einen harmlosen Basename."""
    base = os.path.basename((name or "").replace("\\", "/"))
    stem, ext = os.path.splitext(base)
    stem = _NAME_RE.sub("_", stem).strip("._") or default
    ext = _NAME_RE.sub("", ext.lower())[:8]
    return f"{stem[:60]}{ext}"


def replace_file(src: str, dst: str, attempts: int = 8) -> None:
    """os.replace mit kurzer Wiederholung.

    Windows verweigert das Ersetzen, solange ein anderer Prozess/Thread die
    Zieldatei gerade liest (PermissionError). Unter macOS/Linux greift das nie.
    """
    import time
    for i in range(attempts):
        try:
            os.replace(src, dst)
            return
        except PermissionError:
            if i == attempts - 1:
                raise
            time.sleep(0.05 * (i + 1))


def write_json_atomic(path: str, data) -> None:
    os.makedirs(os.path.dirname(path), exist_ok=True)
    tmp = f"{path}.{uuid.uuid4().hex[:8]}.tmp"
    with _write_lock:
        try:
            with open(tmp, "w", encoding="utf-8") as fh:
                json.dump(data, fh, ensure_ascii=False, indent=2)
                fh.flush()
                os.fsync(fh.fileno())
            replace_file(tmp, path)
        finally:
            if os.path.exists(tmp):  # Abbruch mitten im Schreiben → keine Reste
                os.remove(tmp)


def read_json(path: str, default=None):
    try:
        with open(path, "r", encoding="utf-8") as fh:
            return json.load(fh)
    except (OSError, ValueError):
        return default
