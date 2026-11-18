"""`.env` einlesen — ohne Bash und ohne Zusatzpaket (wichtig für Windows).

Unter macOS/Linux lädt `scripts/start_local.sh` die Datei per `source`. Unter
Windows gibt es das nicht; deshalb lädt das Backend sie beim Start selbst.
Bereits gesetzte Umgebungsvariablen haben IMMER Vorrang (nichts wird
überschrieben). Versteht das Format, das ClipForge selbst schreibt
(`NAME='wert'` mit Bash-Quoting) sowie `export`, Kommentare und "…".
"""

from __future__ import annotations

import os
import re

_LINE = re.compile(r"^\s*(?:export\s+)?([A-Za-z_][A-Za-z0-9_]*)\s*=\s*(.*)$")


def _unquote(raw: str) -> str:
    raw = raw.strip()
    out, i = [], 0
    while i < len(raw):
        c = raw[i]
        if c == "'":
            j = raw.find("'", i + 1)
            if j == -1:
                return raw  # kaputtes Quoting → Rohwert
            out.append(raw[i + 1:j])
            i = j + 1
        elif c == '"':
            j = i + 1
            buf = []
            while j < len(raw) and raw[j] != '"':
                if raw[j] == "\\" and j + 1 < len(raw):
                    j += 1
                buf.append(raw[j])
                j += 1
            out.append("".join(buf))
            i = j + 1
        elif c == "\\" and i + 1 < len(raw):
            out.append(raw[i + 1])
            i += 2
        elif c == "#" and (i == 0 or raw[i - 1].isspace()):
            break  # Kommentar am Zeilenende
        elif c.isspace() and not out and not raw[:i].strip():
            i += 1
        else:
            out.append(c)
            i += 1
    return "".join(out).strip() if not raw.startswith(("'", '"')) else "".join(out)


def parse(text: str) -> dict[str, str]:
    values: dict[str, str] = {}
    for line in text.splitlines():
        if not line.strip() or line.lstrip().startswith("#"):
            continue
        m = _LINE.match(line)
        if m:
            values[m.group(1)] = _unquote(m.group(2))
    return values


def load(path: str) -> list[str]:
    """Setzt fehlende Variablen aus `path`. Liefert die NAMEN der gesetzten."""
    try:
        with open(path, "r", encoding="utf-8") as fh:
            values = parse(fh.read())
    except OSError:
        return []
    applied = []
    for key, value in values.items():
        if key not in os.environ:
            os.environ[key] = value
            applied.append(key)
    return applied
