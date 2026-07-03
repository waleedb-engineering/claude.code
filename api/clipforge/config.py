"""Zentrale Konfiguration der Pipeline (über Umgebungsvariablen steuerbar)."""

from __future__ import annotations

import os
from dataclasses import dataclass, field


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
    # Timeout (Sekunden) für den optionalen LLM-Aufruf; danach → Fallback.
    llm_timeout_seconds: float = _get_float("CLIPFORGE_LLM_TIMEOUT", 30.0)

    # --- Rendering ---
    output_width: int = _get_int("CLIPFORGE_OUT_WIDTH", 1080)
    output_height: int = _get_int("CLIPFORGE_OUT_HEIGHT", 1920)
    # Stille-Schwelle für "schnelle Schnitte" (Jump-Cuts):
    silence_db: float = _get_float("CLIPFORGE_SILENCE_DB", -30.0)
    silence_min_seconds: float = _get_float("CLIPFORGE_SILENCE_MIN", 0.6)

    # --- YouTube Publishing (Phase 1: Dry-Run; echter Upload standardmäßig AUS) ---
    # Bewusst als default_factory, damit jedes get_settings() den ENV-Wert LIVE
    # liest (Feature-Flag lässt sich pro Prozessstart steuern; kein Frozen-Import).
    # Es werden hier KEINE Tokens gelesen oder gespeichert.
    enable_youtube_upload: bool = field(
        default_factory=lambda: os.environ.get(
            "CLIPFORGE_ENABLE_YOUTUBE_UPLOAD", "false"
        ).strip().lower() == "true"
    )
    # Pfad zu einer OAuth-Client-Secrets-Datei (NUR Existenzprüfung; nie geloggt,
    # nie in Responses ausgegeben). Ohne diese gilt: credentials nicht konfiguriert.
    youtube_client_secrets_file: str | None = field(
        default_factory=lambda: os.environ.get("CLIPFORGE_YOUTUBE_CLIENT_SECRETS") or None
    )
    # YouTube-Kategorie (Default 22 = "People & Blogs").
    youtube_category_id: str = field(
        default_factory=lambda: os.environ.get("CLIPFORGE_YOUTUBE_CATEGORY_ID", "22")
    )
    # OAuth-Readiness (Phase 2): separates Flag für Auth-Aktionen. Default AUS.
    # Der READ-ONLY Readiness-Check läuft immer; nur auth/start ist gegated.
    enable_youtube_oauth: bool = field(
        default_factory=lambda: os.environ.get(
            "CLIPFORGE_ENABLE_YOUTUBE_OAUTH", "false"
        ).strip().lower() == "true"
    )
    # Keyring-Koordinaten für die Token-Ablage (nie das Token selbst im ENV!).
    youtube_token_service_name: str = field(
        default_factory=lambda: os.environ.get(
            "CLIPFORGE_YOUTUBE_TOKEN_SERVICE_NAME", "clipforge-youtube"
        )
    )
    youtube_token_account: str = field(
        default_factory=lambda: os.environ.get(
            "CLIPFORGE_YOUTUBE_TOKEN_ACCOUNT", "default"
        )
    )
    # OAuth-Flow-Skelett (Phase 2b): Redirect-URI für den lokalen Installed-App-
    # Loopback-Callback. Default lokal & sicher; enthält KEIN Secret. Muss mit den
    # in der Google-Cloud-Console autorisierten Redirect-URIs übereinstimmen.
    youtube_oauth_redirect_uri: str = field(
        default_factory=lambda: os.environ.get(
            "CLIPFORGE_YOUTUBE_REDIRECT_URI",
            "http://127.0.0.1:8000/api/youtube/oauth/callback",
        )
    )
    # Lebensdauer eines kurzlebigen OAuth-State (CSRF-Schutz), in Sekunden.
    youtube_oauth_state_ttl_seconds: int = field(
        default_factory=lambda: _get_int(
            "CLIPFORGE_YOUTUBE_OAUTH_STATE_TTL_SECONDS", 600
        )
    )

    @property
    def llm_available(self) -> bool:
        return bool(self.anthropic_api_key) and self.use_llm

    @property
    def youtube_credentials_configured(self) -> bool:
        """True nur, wenn eine Client-Secrets-Datei gesetzt ist UND existiert.
        Es wird NICHTS aus der Datei gelesen — nur die Existenz geprüft."""
        path = self.youtube_client_secrets_file
        return bool(path) and os.path.exists(path)


def get_settings() -> Settings:
    return Settings()
