"""Plattform-Adapter für Publishing.

Aktuell nur YouTube. Dry-Run + OAuth-Readiness + OAuth-Flow (Consent-URL,
State/CSRF+PKCE, Callback, **echter** Google-Token-Exchange über die offizielle
Library, sichere Keychain-Token-Ablage) — aber weiterhin **kein Upload** und
**kein `videos.insert`**. Siehe docs/YOUTUBE_PUBLISHING.md.
"""

from .base import PlatformAdapter
from .youtube import YouTubeAdapter
from .youtube_oauth import (
    OAuthClientSecretsMissing,
    OAuthDependencyMissing,
    OAuthError,
    OAuthExchangeFailed,
    OAuthExchangeUnavailable,
    OAuthStateStore,
    YouTubeOAuthConfig,
    YouTubeOAuthService,
    real_google_token_exchange,
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
    "OAuthDependencyMissing",
    "OAuthClientSecretsMissing",
    "OAuthExchangeFailed",
    "real_google_token_exchange",
    "sanitize_token_payload",
]
