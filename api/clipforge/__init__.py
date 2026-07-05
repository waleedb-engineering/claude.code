"""ClipForge — KI-gestützte Long-form → Shorts Pipeline.

Wandelt lange Videos in fertige 9:16-Kurzclips mit Untertiteln,
Performance-Potential-Score und Plattform-Metadaten um.
"""

import os


def _read_version() -> str:
    """Liest die Repo-weite VERSION-Datei (Single Source of Truth).

    Fällt defensiv auf einen Platzhalter zurück, falls die Datei fehlt (z.B.
    ungewöhnliches Deployment) — kein harter Crash beim Import.
    """
    path = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(
        os.path.abspath(__file__)))), "VERSION")
    try:
        with open(path, encoding="utf-8") as fh:
            return fh.read().strip()
    except OSError:
        return "0.0.0-unknown"


__version__ = _read_version()

