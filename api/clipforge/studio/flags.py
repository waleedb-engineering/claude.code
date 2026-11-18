"""Feature Flags: `feature_flags.json` im Repo-Root + ENV-Override.

ENV `CLIPFORGE_FLAG_<NAME>=true|false` gewinnt über die Datei. Unbekannte
Flags gelten als aus. Die Datei enthält niemals Secrets.
"""

from __future__ import annotations

import json
import os

DEFAULT_FLAGS: dict[str, bool] = {
    "studio": True,
    "studio_url_import": True,
    "studio_external_providers": True,
    "studio_mock_providers": False,
    "studio_automation": True,
    "studio_analytics": True,
    "studio_ideas": True,
    # YouTube-Import nur für eigene/berechtigte Videos, Video-Datei lädt der Nutzer hoch.
    "studio_youtube_import": True,
    "studio_voice_cloning": False,
    "studio_face_swap": False,
}


def flags_path() -> str:
    root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(
        os.path.abspath(__file__)))))
    return os.environ.get("CLIPFORGE_FEATURE_FLAGS", os.path.join(root, "feature_flags.json"))


def load_flags() -> dict[str, bool]:
    flags = dict(DEFAULT_FLAGS)
    try:
        with open(flags_path(), "r", encoding="utf-8") as fh:
            data = json.load(fh)
        for key, value in (data.get("flags") or {}).items():
            if isinstance(value, bool):
                flags[key] = value
    except (OSError, ValueError, AttributeError):
        pass
    for key in list(flags):
        env = os.environ.get(f"CLIPFORGE_FLAG_{key.upper()}")
        if env is not None:
            flags[key] = env.strip().lower() in ("1", "true", "yes", "on")
    return flags


def is_enabled(name: str) -> bool:
    return bool(load_flags().get(name, False))
