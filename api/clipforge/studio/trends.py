"""Trendübersicht — nur aus tatsächlich verfügbaren, zulässigen Quellen.

- YouTube: offizielle YouTube Data API v3, `videos.list?chart=mostPopular`
  (kostenloser API-Schlüssel, Kontingent). Liefert die aktuell beliebtesten
  Videos je Land/Kategorie; daraus werden Themen und Schlagwörter abgeleitet.
- TikTok, Instagram: bieten für normale Entwickler KEINE offizielle Trend-API
  (TikTok Research API nur für Forschung, Creative Center ohne API). ClipForge
  zeigt das offen an; Trends können manuell als Idee erfasst werden.
Es werden keine Trendwerte erfunden oder geschätzt.
"""

from __future__ import annotations

import json
import os
import re
import urllib.error
import urllib.parse
import urllib.request
from collections import Counter

from .broll import keywords as _kw
from .errors import StudioError

CATEGORIES = {  # YouTube-Kategorie-IDs (Auswahl)
    "": "Alle", "10": "Musik", "17": "Sport", "20": "Gaming", "22": "Menschen & Blogs",
    "23": "Comedy", "24": "Unterhaltung", "25": "Nachrichten", "26": "Praktische Tipps & Stil",
    "27": "Bildung", "28": "Wissenschaft & Technik",
}
API_GET = None  # Test-Hook (url) -> dict
PLATFORM_STATUS = {
    "youtube": "Offizielle YouTube Data API (mostPopular) — braucht kostenlosen YOUTUBE_API_KEY.",
    "tiktok": "Keine offizielle Trend-API für Creator-Apps verfügbar — bitte manuell erfassen.",
    "instagram": "Keine offizielle Trend-API verfügbar — bitte manuell erfassen.",
}


def _get(url: str) -> dict:
    if API_GET is not None:
        return API_GET(url)
    req = urllib.request.Request(url, headers={"User-Agent": "ClipForge"})
    try:
        with urllib.request.urlopen(req, timeout=20) as resp:  # noqa: S310 — fester Host
            return json.loads(resp.read(4 * 1024 * 1024))
    except urllib.error.HTTPError as exc:
        if exc.code in (400, 403):
            raise StudioError("credential_rejected",
                              "YouTube hat den Schlüssel/Abruf abgelehnt (Kontingent oder Schlüssel prüfen).",
                              502) from None
        raise StudioError("provider_failed", f"YouTube-Abruf fehlgeschlagen (HTTP {exc.code}).", 502) from None
    except OSError as exc:
        raise StudioError("provider_unreachable", "YouTube nicht erreichbar.", 502) from exc


def youtube_trends(region: str = "DE", category: str = "", limit: int = 25) -> dict:
    key = os.environ.get("YOUTUBE_API_KEY")
    if not key:
        raise StudioError("credential_not_set",
                          "Für YouTube-Trends einen kostenlosen YOUTUBE_API_KEY unter Einrichtung "
                          "eintragen (Google Cloud → YouTube Data API v3).", 409)
    if not re.fullmatch(r"[A-Z]{2}", region or ""):
        raise StudioError("validation_error", "Region als Ländercode, z. B. DE oder US.")
    if category not in CATEGORIES:
        raise StudioError("validation_error", "Unbekannte Kategorie.")
    params = {"part": "snippet,statistics", "chart": "mostPopular", "regionCode": region,
              "maxResults": max(1, min(50, limit)), "key": key}
    if category:
        params["videoCategoryId"] = category
    data = _get("https://www.googleapis.com/youtube/v3/videos?" + urllib.parse.urlencode(params))
    videos, words = [], Counter()
    for item in data.get("items") or []:
        sn, st = item.get("snippet") or {}, item.get("statistics") or {}
        title = str(sn.get("title") or "")
        videos.append({"id": item.get("id"), "title": title, "channel": sn.get("channelTitle"),
                       "published_at": sn.get("publishedAt"),
                       "views": int(st["viewCount"]) if str(st.get("viewCount", "")).isdigit() else None,
                       "tags": (sn.get("tags") or [])[:8],
                       "url": f"https://www.youtube.com/watch?v={item.get('id')}"})
        for w in _kw(title + " " + " ".join(sn.get("tags") or []), 12):
            words[w] += 1
    return {"platform": "youtube", "source": "YouTube Data API v3 (chart=mostPopular)",
            "region": region, "category": CATEGORIES[category], "videos": videos,
            "keywords": [{"keyword": w, "count": c} for w, c in words.most_common(20)],
            "note": "Beliebteste Videos laut YouTube — kein Erfolgsversprechen für eigene Inhalte."}


def status() -> dict:
    return {"platforms": {p: {"available": p == "youtube" and bool(os.environ.get("YOUTUBE_API_KEY")),
                              "note": n} for p, n in PLATFORM_STATUS.items()},
            "categories": CATEGORIES}
