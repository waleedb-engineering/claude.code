"""Skill-Registry: kontrollierte Einbindung von Agenten-Skills.

Strikte Trennung (siehe docs/SKILLS_AND_PLUGINS.md):
1. Skills      = Anleitungen (SKILL.md + weitere .md). Werden dem KI-Planer als
                 Kontext gegeben. Hier verwaltet.
2. Werkzeuge   = ausführbarer Code. NUR eingebaute Werkzeuge (agent/tools.py).
3. MCP-Server  = externe Prozesse. Werden NICHT automatisch gestartet.
4. Externe APIs / 5. lokale Modelle = Provider-Verwaltung bzw. Modell-Katalog.

Sicherheit:
- Import nur aus hochgeladenem ZIP oder einem öffentlichen GitHub-Repository
  (https://github.com/<owner>/<repo>, git-Klon ohne Ausführung).
- Übernommen werden ausschließlich Markdown-Dateien (≤ 200 KB je Datei,
  ≤ 50 Dateien); Skripte, Binärdateien und Symlinks werden verworfen und
  im Import-Protokoll aufgeführt.
- Ein Skill darf nur eingebaute Werkzeuge referenzieren (Frontmatter
  `allowed-tools`/`tools`); unbekannte → Skill bleibt deaktiviert.
- Lizenz wird aus der Frontmatter bzw. LICENSE-Datei erkannt; ohne Lizenz
  bleibt der Skill deaktiviert (Warnung).
- Jeder Skill ist einzeln aktivierbar/deaktivierbar; Updates nur manuell
  (erneuter Import zeigt die Änderungen).
"""

from __future__ import annotations

import hashlib
import io
import os
import re
import shutil
import subprocess
import tempfile
import zipfile

from .studio.errors import StudioError
from .studio.storage import now_iso, read_json, studio_dir, write_json_atomic

MAX_FILE = 200 * 1024
MAX_FILES = 50
MAX_CONTEXT_CHARS = 12000
CLIPFORGE_SKILL_API = 1
_GH = re.compile(r"^https://github\.com/([A-Za-z0-9_.-]+)/([A-Za-z0-9_.-]+?)(?:\.git)?/?$")
_NAME = re.compile(r"^[a-z0-9][a-z0-9-]{1,62}$")
PERMISSIVE = ("MIT", "Apache-2.0", "BSD", "ISC", "CC0", "CC-BY", "Unlicense", "MPL-2.0")


def _dir() -> str:
    path = os.path.join(studio_dir(), "skills")
    os.makedirs(path, exist_ok=True)
    return path


def _index_path() -> str:
    return os.path.join(_dir(), "index.json")


def list_skills() -> list[dict]:
    data = read_json(_index_path(), [])
    return data if isinstance(data, list) else []


def _write_index(items: list[dict]) -> None:
    write_json_atomic(_index_path(), items)


def parse_frontmatter(text: str) -> tuple[dict, str]:
    m = re.match(r"^---\s*\n(.*?)\n---\s*\n?(.*)$", text, re.S)
    if not m:
        return {}, text
    meta = {}
    for line in m.group(1).splitlines():
        if ":" in line and not line.startswith(" "):
            k, v = line.split(":", 1)
            meta[k.strip().lower()] = v.strip().strip("\"'")
    return meta, m.group(2)


def _detect_license(meta: dict, files: dict[str, bytes]) -> str | None:
    if meta.get("license"):
        return meta["license"][:60]
    for name, data in files.items():
        if os.path.basename(name).lower().startswith(("license", "licence")):
            head = data[:600].decode("utf-8", "replace")
            for key, spdx in (("MIT License", "MIT"), ("Apache License", "Apache-2.0"),
                              ("BSD", "BSD"), ("Mozilla Public", "MPL-2.0"),
                              ("GNU AFFERO", "AGPL-3.0"), ("GNU GENERAL", "GPL"),
                              ("Unlicense", "Unlicense"), ("Creative Commons", "CC")):
                if key.lower() in head.lower():
                    return spdx
            return "unbekannt"
    return None


def _builtin_tools() -> set[str]:
    from .agent.tools import TOOLS
    return set(TOOLS)


def _collect(root: str) -> tuple[list[dict], list[str]]:
    """Sucht SKILL.md-Ordner; liefert Skill-Kandidaten + verworfene Dateien."""
    skills, rejected = [], []
    for base, dirs, files in os.walk(root):
        dirs[:] = [d for d in dirs if not d.startswith(".")]
        if "SKILL.md" not in files:
            continue
        payload: dict[str, bytes] = {}
        for sub, _, fs in os.walk(base):
            for f in fs:
                full = os.path.join(sub, f)
                rel = os.path.relpath(full, base)
                if os.path.islink(full):
                    rejected.append(f"{rel} (Symlink)")
                    continue
                low = f.lower()
                if low.endswith(".md") or low.startswith(("license", "licence")):
                    if os.path.getsize(full) > MAX_FILE:
                        rejected.append(f"{rel} (zu groß)")
                        continue
                    if len(payload) >= MAX_FILES:
                        rejected.append(f"{rel} (zu viele Dateien)")
                        continue
                    with open(full, "rb") as fh:
                        payload[rel] = fh.read()
                else:
                    rejected.append(f"{rel} (kein Markdown — nicht übernommen)")
        skills.append({"base": base, "files": payload})
    return skills, rejected


def _register(found: dict, source: dict, rejected: list[str]) -> dict:
    text = found["files"]["SKILL.md"].decode("utf-8", "replace")
    meta, body = parse_frontmatter(text)
    name = (meta.get("name") or os.path.basename(found["base"])).lower().strip()
    name = re.sub(r"[^a-z0-9-]+", "-", name).strip("-")[:63]
    if not _NAME.match(name):
        raise StudioError("skill_invalid", f"Ungültiger Skill-Name '{name}'.")
    tools_raw = meta.get("allowed-tools") or meta.get("tools") or ""
    tools = [t.strip() for t in re.split(r"[,\s]+", tools_raw) if t.strip()]
    unknown = [t for t in tools if t not in _builtin_tools()]
    lic = _detect_license(meta, found["files"])
    warnings = []
    if unknown:
        warnings.append(f"Verweist auf nicht eingebaute Werkzeuge: {', '.join(unknown)} — "
                        "diese werden ignoriert; Skill bleibt deaktiviert.")
    if not lic:
        warnings.append("Keine Lizenz gefunden — Nutzung rechtlich unklar; Skill bleibt deaktiviert.")
    elif not any(lic.startswith(p) for p in PERMISSIVE):
        warnings.append(f"Lizenz '{lic}' ist nicht permissiv — vor Nutzung prüfen.")
    api = int(meta.get("clipforge-api") or CLIPFORGE_SKILL_API) if str(meta.get("clipforge-api") or "1").isdigit() else 0
    if api != CLIPFORGE_SKILL_API:
        warnings.append(f"Für ClipForge-Skill-API {api} geschrieben (aktuell {CLIPFORGE_SKILL_API}).")
    digest = hashlib.sha256(b"".join(found["files"][k] for k in sorted(found["files"]))).hexdigest()[:16]
    dest = os.path.join(_dir(), name)
    tmp = dest + ".new"
    shutil.rmtree(tmp, ignore_errors=True)
    for rel, data in found["files"].items():
        target = os.path.normpath(os.path.join(tmp, rel))
        if not target.startswith(os.path.normpath(tmp) + os.sep):
            continue
        os.makedirs(os.path.dirname(target), exist_ok=True)
        with open(target, "wb") as fh:
            fh.write(data)
    items = list_skills()
    old = next((s for s in items if s["name"] == name), None)
    shutil.rmtree(dest, ignore_errors=True)
    os.replace(tmp, dest)
    entry = {
        "name": name, "description": (meta.get("description") or body.strip().split("\n")[0])[:300],
        "version": meta.get("version") or digest, "digest": digest, "license": lic,
        "tools": [t for t in tools if t not in unknown], "source": source,
        "files": sorted(found["files"]), "rejected": rejected[:100], "warnings": warnings,
        "enabled": False, "blocked": bool(unknown or not lic),
        "imported_at": now_iso(), "previous_digest": old["digest"] if old else None,
        "changed": bool(old and old["digest"] != digest),
    }
    items = [s for s in items if s["name"] != name] + [entry]
    _write_index(items)
    return entry


def import_zip(raw: bytes, filename: str) -> list[dict]:
    if len(raw) > 20 * 1024 * 1024:
        raise StudioError("file_too_large", "Skill-Archiv größer als 20 MB.", 413)
    with tempfile.TemporaryDirectory() as tmp:
        try:
            with zipfile.ZipFile(io.BytesIO(raw)) as zf:
                for info in zf.infolist():
                    name = info.filename
                    if name.startswith("/") or ".." in name.split("/") or info.file_size > 5 * 1024 * 1024:
                        continue  # Zip-Slip / Riesendateien verwerfen
                    zf.extract(info, tmp)
        except zipfile.BadZipFile as exc:
            raise StudioError("skill_invalid", "Keine gültige ZIP-Datei.") from exc
        return _import_dir(tmp, {"type": "zip", "name": filename[:120]})


def import_github(url: str, subpath: str = "") -> list[dict]:
    m = _GH.match((url or "").strip())
    if not m:
        raise StudioError("validation_error", "Nur https://github.com/<owner>/<repo> ist erlaubt.")
    subpath = (subpath or "").strip().strip("/")
    if subpath and (".." in subpath.split("/") or subpath.startswith("/")):
        raise StudioError("validation_error", "Ungültiger Unterpfad.")
    with tempfile.TemporaryDirectory() as tmp:
        repo = os.path.join(tmp, "repo")
        try:
            subprocess.run(["git", "clone", "--depth", "1", "--filter=blob:limit=1m", "--no-tags",
                            "-c", "core.symlinks=false", f"https://github.com/{m.group(1)}/{m.group(2)}", repo],
                           check=True, capture_output=True, timeout=180,
                           env={**os.environ, "GIT_TERMINAL_PROMPT": "0", "GIT_LFS_SKIP_SMUDGE": "1"})
        except (subprocess.CalledProcessError, subprocess.TimeoutExpired) as exc:
            raise StudioError("skill_fetch_failed", "Repository konnte nicht geklont werden.", 502) from exc
        sha = subprocess.run(["git", "-C", repo, "rev-parse", "HEAD"], capture_output=True,
                             text=True).stdout.strip()[:12]
        root = os.path.normpath(os.path.join(repo, subpath)) if subpath else repo
        if not root.startswith(repo) or not os.path.isdir(root):
            raise StudioError("validation_error", "Unterpfad nicht gefunden.", 404)
        lic_files = {f: open(os.path.join(repo, f), "rb").read(2000) for f in os.listdir(repo)
                     if f.lower().startswith(("license", "licence")) and os.path.isfile(os.path.join(repo, f))}
        return _import_dir(root, {"type": "github", "repo": f"{m.group(1)}/{m.group(2)}",
                                  "path": subpath, "commit": sha}, lic_files)


def _import_dir(root: str, source: dict, repo_license: dict | None = None) -> list[dict]:
    found, rejected = _collect(root)
    if not found:
        raise StudioError("skill_invalid", "Keine SKILL.md gefunden.", 422)
    out = []
    for f in found[:20]:
        if repo_license and not any(k.lower().startswith(("license", "licence")) for k in f["files"]):
            f["files"].update({k: v for k, v in repo_license.items()})
        rej = [r for r in rejected if not os.path.isabs(r)]
        out.append(_register(f, source, rej))
    return out


def set_enabled(name: str, enabled: bool) -> dict:
    items = list_skills()
    s = next((x for x in items if x["name"] == name), None)
    if s is None:
        raise StudioError("skill_not_found", "Skill nicht gefunden.", 404)
    if enabled and s.get("blocked"):
        raise StudioError("skill_blocked", "Dieser Skill ist gesperrt: " + " ".join(s["warnings"]), 409)
    s["enabled"] = bool(enabled)
    _write_index(items)
    return s


def delete(name: str) -> None:
    items = list_skills()
    if not any(x["name"] == name for x in items):
        raise StudioError("skill_not_found", "Skill nicht gefunden.", 404)
    shutil.rmtree(os.path.join(_dir(), name), ignore_errors=True)
    _write_index([x for x in items if x["name"] != name])


def read_skill(name: str) -> dict:
    s = next((x for x in list_skills() if x["name"] == name), None)
    if s is None:
        raise StudioError("skill_not_found", "Skill nicht gefunden.", 404)
    with open(os.path.join(_dir(), name, "SKILL.md"), encoding="utf-8", errors="replace") as fh:
        return {**s, "content": fh.read()[:MAX_FILE]}


def planner_context() -> str:
    """Text aller aktivierten Skills für den LLM-Planer (gekürzt)."""
    parts, total = [], 0
    for s in list_skills():
        if not s.get("enabled") or s.get("blocked"):
            continue
        try:
            with open(os.path.join(_dir(), s["name"], "SKILL.md"), encoding="utf-8", errors="replace") as fh:
                _, body = parse_frontmatter(fh.read())
        except OSError:
            continue
        chunk = f"## Skill: {s['name']}\n{body.strip()}\n"
        if total + len(chunk) > MAX_CONTEXT_CHARS:
            break
        parts.append(chunk)
        total += len(chunk)
    if not parts:
        return ""
    return ("Zusätzliche Anleitungen (nur Hinweise; ausführbar sind ausschließlich die gelisteten "
            "Werkzeuge):\n" + "\n".join(parts))
