"""Plattform-Adapter für Publishing.

Aktuell nur YouTube und ausschließlich als **Dry-Run**-Gerüst — es gibt
keinen echten Upload, kein OAuth und keine Token-Speicherung in dieser Phase.
Siehe docs/YOUTUBE_PUBLISHING.md.
"""

from .base import PlatformAdapter
from .youtube import YouTubeAdapter

__all__ = ["PlatformAdapter", "YouTubeAdapter"]
