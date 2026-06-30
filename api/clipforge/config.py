"""Zentrale Konfiguration der Pipeline (über Umgebungsvariablen steuerbar)."""

from __future__ import annotations

import os
from dataclasses import dataclass


def _get_float(name: str, default: float) -> float:
    try:
        return float(os.environ.get(name, default))
    except (TypeError, ValueError):
        return default


def _get_int(name: str, default: int) -> int:
    try:
        return int(os.environ.get(name, default))
    except (TypeError, ValueError):
        return default


@dataclass
class Settings:
    # --- Transkription (lokales faster-whisper) ---
    whisper_model: str = os.environ.get("CLIPFORGE_WHISPER_MODEL", "base")
    whisper_device: str = os.environ.get("CLIPFORGE_WHISPER_DEVICE", "cpu")
    whisper_compute_type: str = os.environ.get("CLIPFORGE_WHISPER_COMPUTE", "int8")

    # --- Clip-Auswahl ---
    min_clip_seconds: float = _get_float("CLIPFORGE_MIN_CLIP_SECONDS", 15.0)
    max_clip_seconds: float = _get_float("CLIPFORGE_MAX_CLIP_SECONDS", 60.0)
    target_clip_seconds: float = _get_float("CLIPFORGE_TARGET_CLIP_SECONDS", 30.0)
    # Pause (Sekunden) zwischen Wörtern, ab der ein Clip getrennt werden darf:
    segment_gap_seconds: float = _get_float("CLIPFORGE_SEGMENT_GAP", 0.6)

    # --- Scoring (Claude) ---
    anthropic_api_key: str | None = os.environ.get("ANTHROPIC_API_KEY")
    llm_model: str = os.environ.get("CLIPFORGE_LLM_MODEL", "claude-sonnet-4-6")
    use_llm: bool = os.environ.get("CLIPFORGE_USE_LLM", "auto") != "off"

    # --- Rendering ---
    output_width: int = _get_int("CLIPFORGE_OUT_WIDTH", 1080)
    output_height: int = _get_int("CLIPFORGE_OUT_HEIGHT", 1920)
    # Stille-Schwelle für "schnelle Schnitte" (Jump-Cuts):
    silence_db: float = _get_float("CLIPFORGE_SILENCE_DB", -30.0)
    silence_min_seconds: float = _get_float("CLIPFORGE_SILENCE_MIN", 0.6)

    @property
    def llm_available(self) -> bool:
        return bool(self.anthropic_api_key) and self.use_llm


def get_settings() -> Settings:
    return Settings()
