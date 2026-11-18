"""Getrennte Benutzerbereiche im Online-Betrieb (`CLIPFORGE_AUTH=accounts`).

Der aktuelle Benutzer steckt in einer ContextVar, die die Anmelde-Middleware
je Anfrage setzt und die Hintergrundaufgaben mitnehmen. Davon hängt ab:
- `storage.studio_dir()` → `<studio>/users/<name>` (Projekte, Aufgaben,
  Vorlagen, Ideen, Analytics, Konten, Stimmen, Automationen, Musik)
- `jobs.JobRegistry.get/list` → nur eigene Jobs (Publishing-Entwürfe)
- `credentials.secret()` → eigene API-Schlüssel (verschlüsselt je Benutzer)

Ohne Benutzer (lokaler Einzelbetrieb, Systemaufgaben) bleibt alles wie bisher.
Gemeinsam bleiben nur Anmeldedaten, lokale KI-Modelle und Piper-Stimmen.
"""

from __future__ import annotations

import contextlib
import contextvars

_current: contextvars.ContextVar[tuple[str, str] | None] = contextvars.ContextVar(
    "clipforge_workspace", default=None)


def current() -> str | None:
    value = _current.get()
    return value[0] if value else None


def role() -> str | None:
    value = _current.get()
    return value[1] if value else None


def is_admin() -> bool:
    return role() == "admin"


def set_current(user: str | None, user_role: str = "user"):
    return _current.set((user, user_role) if user else None)


def reset(token) -> None:
    _current.reset(token)


@contextlib.contextmanager
def use(user: str | None, user_role: str = "user"):
    token = set_current(user, user_role)
    try:
        yield
    finally:
        reset(token)


def snapshot() -> tuple[str, str] | None:
    return _current.get()


def all_workspaces() -> list[tuple[str, str] | None]:
    """Gemeinsamer Bereich (None) + alle Benutzerbereiche — für Systemaufgaben
    wie Wiederherstellung nach Neustart und Automationen."""
    import os
    from .storage import studio_root
    out: list[tuple[str, str] | None] = [None]
    try:
        from ..auth import accounts_mode, user_role, workspaces_mode
        if not (accounts_mode() and workspaces_mode() == "per_user"):
            return out
        base = os.path.join(studio_root(), "users")
        for name in sorted(os.listdir(base)) if os.path.isdir(base) else []:
            out.append((name, user_role(name)))
    except Exception:  # noqa: BLE001 — nie den Start blockieren
        pass
    return out


def visible(owner: str | None) -> bool:
    """Darf der aktuelle Benutzer ein Objekt mit diesem Besitzer sehen?

    Kein Benutzer gesetzt (lokal/System) → alles. Altbestand ohne Besitzer
    gehört Administratoren (bis zur Migration)."""
    user = current()
    if user is None:
        return True
    if owner is None:
        return is_admin()
    return owner == user


# Bestandteile, die je Benutzer getrennt liegen (Rest bleibt gemeinsam)
PER_USER_ITEMS = ("projects", "tasks", "templates.json", "ideas", "analytics", "accounts",
                  "voices", "automations", "music", "previews")


def migrate_shared(user: str, jobs_dir: str | None = None) -> dict:
    """Überführt den bisherigen gemeinsamen Bestand in den Bereich von `user`.

    Verschiebt (nicht kopiert) die Studio-Daten aus der Wurzel nach
    users/<user>/ und trägt `user` als Besitzer aller Jobs ohne Besitzer ein.
    Bricht ab, wenn im Zielbereich schon dieselben Daten liegen (nichts wird
    überschrieben)."""
    import json
    import os
    import shutil
    from .storage import studio_root
    root = studio_root()
    target = os.path.join(root, "users", user)
    os.makedirs(target, exist_ok=True)
    moved, skipped = [], []
    for item in PER_USER_ITEMS:
        src = os.path.join(root, item)
        if not os.path.exists(src):
            continue
        dst = os.path.join(target, item)
        if os.path.exists(dst) and (not os.path.isdir(dst) or os.listdir(dst)):
            skipped.append(item)
            continue
        if os.path.isdir(dst):
            os.rmdir(dst)
        shutil.move(src, dst)
        moved.append(item)
    owned = 0
    jobs_dir = jobs_dir or os.environ.get("CLIPFORGE_JOBS_DIR")
    if jobs_dir and os.path.isdir(jobs_dir):
        for name in os.listdir(jobs_dir):
            path = os.path.join(jobs_dir, name, "job.json")
            try:
                with open(path, encoding="utf-8") as fh:
                    data = json.load(fh)
            except (OSError, ValueError):
                continue
            if isinstance(data, dict) and not data.get("owner"):
                data["owner"] = user
                tmp = path + ".tmp"
                with open(tmp, "w", encoding="utf-8") as fh:
                    json.dump(data, fh, ensure_ascii=False, indent=2)
                os.replace(tmp, path)
                owned += 1
    return {"moved": moved, "skipped": skipped, "jobs_assigned": owned}
