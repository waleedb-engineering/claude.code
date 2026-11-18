"""YouTube-Import — regelkonform.

Was passiert:
  1. Link prüfen (youtube.com/watch, youtu.be, /shorts/, /embed/, /live/) →
     11-stellige Video-ID.
  2. Öffentliche Metadaten (Titel, Kanal, Vorschaubild) über YouTubes
     offizielle oEmbed-Schnittstelle — ohne Schlüssel, ohne Video-Download.
  3. Der Nutzer bestätigt, dass er Rechteinhaber ist bzw. die Erlaubnis hat;
     die Bestätigung wird mit Zeitpunkt im Projekt festgehalten.
  4. Das Video selbst lädt der Nutzer hoch (z. B. aus YouTube Studio →
     „Herunterladen“ für eigene Videos). ClipForge lädt NICHTS von YouTube
     herunter: das untersagen die Nutzungsbedingungen, und offizielle APIs
     bieten keinen Video-Download.
  5. Untertitel aus YouTube Studio (.srt/.vtt) werden übernommen; sonst wird
     lokal transkribiert. Danach: bestehende Shorts-Pipeline.
"""

from __future__ import annotations

import json
import re
from urllib.parse import parse_qs, urlsplit

from .errors import StudioError

_ID = re.compile(r"^[A-Za-z0-9_-]{11}$")
_HOSTS = {"youtube.com", "www.youtube.com", "m.youtube.com", "music.youtube.com",
          "youtu.be", "www.youtu.be", "youtube-nocookie.com", "www.youtube-nocookie.com"}


def video_id(url: str) -> str:
    """Video-ID aus einem YouTube-Link oder StudioError `youtube_url_invalid`."""
    parts = urlsplit((url or "").strip())
    host = (parts.hostname or "").lower()
    if parts.scheme not in ("http", "https") or host not in _HOSTS:
        raise StudioError("youtube_url_invalid", "Das ist kein YouTube-Link.")
    vid = ""
    if host.endswith("youtu.be"):
        vid = parts.path.strip("/").split("/")[0]
    elif parts.path == "/watch":
        vid = (parse_qs(parts.query).get("v") or [""])[0]
    else:
        seg = [s for s in parts.path.split("/") if s]
        if len(seg) >= 2 and seg[0] in ("shorts", "embed", "live", "v"):
            vid = seg[1]
    if not _ID.match(vid):
        raise StudioError("youtube_url_invalid",
                          "Im Link wurde keine gültige YouTube-Video-ID gefunden.")
    return vid


def canonical_url(vid: str) -> str:
    return f"https://www.youtube.com/watch?v={vid}"


def fetch_metadata(vid: str, fetch_kwargs: dict | None = None) -> dict:
    """Öffentliche Metadaten über oEmbed. Fehler sind nicht fatal (→ None-Felder)."""
    from .safe_fetch import fetch
    url = f"https://www.youtube.com/oembed?format=json&url={canonical_url(vid)}"
    try:
        res = fetch(url, allowed_types=("application/json", "text/json"),
                    max_bytes=256 * 1024, **(fetch_kwargs or {}))
        data = json.loads(res.body.decode("utf-8", "replace"))
    except StudioError as exc:
        if exc.code == "url_http_error" and exc.details.get("http_status") in (401, 403, 404):
            raise StudioError("youtube_unavailable",
                              "Das Video ist privat, gelöscht oder nicht einbettbar.", 422) from exc
        return {"video_id": vid, "url": canonical_url(vid), "title": None, "author": None,
                "thumbnail": None, "metadata_error": exc.code}
    except ValueError:
        return {"video_id": vid, "url": canonical_url(vid), "title": None, "author": None,
                "thumbnail": None, "metadata_error": "invalid_response"}
    clean = lambda v, n: str(v)[:n] if isinstance(v, (str, int)) else None  # noqa: E731
    thumb = clean(data.get("thumbnail_url"), 500)
    if thumb and not thumb.startswith("https://i.ytimg.com/"):
        thumb = None  # nur YouTubes eigenes Bild-CDN
    return {"video_id": vid, "url": canonical_url(vid),
            "title": clean(data.get("title"), 200), "author": clean(data.get("author_name"), 120),
            "thumbnail": thumb, "metadata_error": None}


# ------------------------------------------------------------- Untertitel

_TS = re.compile(r"(?:(\d+):)?(\d{1,2}):(\d{2})[.,](\d{1,3})")


def _seconds(ts: str) -> float:
    m = _TS.search(ts)
    if not m:
        raise ValueError(ts)
    h, mi, s, ms = m.groups()
    return int(h or 0) * 3600 + int(mi) * 60 + int(s) + int(ms.ljust(3, "0")) / 1000


def subtitles_to_transcript(text: str, language: str = "unknown") -> dict:
    """SRT/WebVTT → ClipForge-Transkript.

    Untertitel haben keine Wort-Zeitpunkte: Wörter werden innerhalb jedes
    Untertitels gleichmäßig verteilt (im Ergebnis als `estimated_words`
    gekennzeichnet).
    """
    text = text.replace("\r\n", "\n").replace("\r", "\n").lstrip("﻿")
    segments = []
    for block in re.split(r"\n\s*\n", text):
        lines = [ln for ln in block.split("\n") if ln.strip()]
        idx = next((i for i, ln in enumerate(lines) if "-->" in ln), None)
        if idx is None:
            continue
        start_s, _, end_s = lines[idx].partition("-->")
        try:
            start, end = _seconds(start_s), _seconds(end_s.split()[0] if end_s.split() else end_s)
        except ValueError:
            continue
        body = " ".join(lines[idx + 1:])
        body = re.sub(r"<[^>]+>", "", body)          # VTT-/HTML-Tags
        body = re.sub(r"\{\\[^}]*\}", "", body)       # SSA-Tags
        body = re.sub(r"\s+", " ", body).strip()
        if not body or end <= start:
            continue
        tokens = body.split()
        step = (end - start) / len(tokens)
        words = [{"text": t, "start": round(start + i * step, 3),
                  "end": round(start + (i + 1) * step, 3)} for i, t in enumerate(tokens)]
        if segments and segments[-1]["text"] == body:
            continue  # YouTube-Auto-Untertitel wiederholen Zeilen
        segments.append({"text": body, "start": round(start, 3), "end": round(end, 3),
                         "words": words})
    if not segments:
        raise StudioError("subtitles_empty", "In der Untertiteldatei wurde kein Text gefunden.", 422)
    return {"language": language, "duration": segments[-1]["end"], "segments": segments,
            "estimated_words": True}
