"""Plattform-Adapter für Publishing.

Aktuell nur YouTube: Dry-Run + OAuth-Flow (Consent-URL, State/CSRF+PKCE, echter
Token-Exchange, Keychain-Ablage) + **echter privater Upload** (`videos.insert`,
PRIVATE-only, hinter Feature-Flag + expliziter Bestätigung + Idempotenz). **Kein
public/unlisted, kein Auto-Posting.** Siehe docs/YOUTUBE_PUBLISHING.md.
"""

from .base import PlatformAdapter
from .youtube import YouTubeAdapter
from .youtube_upload import YouTubeUploadService, derive_idempotency_state
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
    "YouTubeUploadService",
    "derive_idempotency_state",
]
