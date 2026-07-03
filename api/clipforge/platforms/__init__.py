"""Plattform-Adapter für Publishing.

Aktuell nur YouTube. Dry-Run + OAuth-Readiness + OAuth-Flow-Skelett (Consent-URL,
State/CSRF, Callback, sichere Token-Ablage) — aber weiterhin **kein echter
Upload** und **kein echter Google-Token-Exchange**. Siehe docs/YOUTUBE_PUBLISHING.md.
"""

from .base import PlatformAdapter
from .youtube import YouTubeAdapter
from .youtube_oauth import (
    OAuthError,
    OAuthExchangeUnavailable,
    OAuthStateStore,
    YouTubeOAuthConfig,
    YouTubeOAuthService,
    sanitize_token_payload,
)

__all__ = [
    "PlatformAdapter",
    "YouTubeAdapter",
    "YouTubeOAuthConfig",
    "YouTubeOAuthService",
    "OAuthStateStore",
    "OAuthError",
    "OAuthExchangeUnavailable",
    "sanitize_token_payload",
]
