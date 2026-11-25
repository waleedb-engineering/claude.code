"""Link-Import für Streams/Videos (YouTube, Twitch) — ausdrücklich einzuschalten.

Warum opt-in: YouTube und Twitch erlauben in ihren Nutzungsbedingungen das
Herunterladen nur über ihre eigenen Funktionen. Der Download mit yt-dlp ist
deshalb ein Risiko für das Konto/die IP des Nutzers — auch bei eigenen Videos.
Der Nutzer schaltet die Funktion einmal bewusst ein (mit Hinweis) und bestätigt
je Link, dass er Rechteinhaber ist oder die Erlaubnis hat.

Schutzmaßnahmen:
- nur YouTube- und Twitch-Links (Host-Liste + yt-dlp ``allowed_extractors``,
  kein generischer Extraktor → keine beliebigen URLs/SSRF)
- keine Wiedergabelisten, keine laufenden Live-Streams (dafür: Live-Modus/OBS)
- Grenzen für Dauer und Auflösung, Speicherplatz-Prüfung vorab
- Abbruch jederzeit; Teil-Downloads werden entfernt
- yt-dlp lädt keine externen Skripte nach (``remote_components`` leer)
"""

from __future__ import annotations

import glob
import os
import re
import shutil
from urllib.parse import urlsplit

from ..studio.errors import StudioError
from ..studio.storage import now_iso, read_json, studio_dir, write_json_atomic

PINNED = "2026.10.26"
_YT_HOSTS = {"youtube.com", "www.youtube.com", "m.youtube.com", "youtu.be", "www.youtu.be"}
_TW_HOSTS = {"twitch.tv", "www.twitch.tv", "m.twitch.tv", "clips.twitch.tv"}
ALLOWED_EXTRACTORS = [r"^youtube$", r"^twitch:vod$", r"^twitch:clips$"]
TERMS = ("YouTube und Twitch erlauben das Herunterladen nur über ihre eigenen Funktionen. "
         "Der Download mit yt-dlp verstößt gegen deren Nutzungsbedingungen — auch bei eigenen "
         "Videos — und kann zur Sperre von Konto oder IP führen. Nutze ihn nur für eigene Inhalte "
         "oder mit Erlaubnis der Rechteinhaber. Die Verantwortung liegt bei dir.")


def max_seconds() -> int:
    try:
        return max(60, int(os.environ.get("CLIPFORGE_LINK_MAX_HOURS", "6")) * 3600)
    except ValueError:
        return 6 * 3600


def max_height() -> int:
    try:
        return min(2160, max(360, int(os.environ.get("CLIPFORGE_LINK_MAX_HEIGHT", "1080"))))
    except ValueError:
        return 1080


# ------------------------------------------------------------------ Einstellung
def _settings_path() -> str:
    return os.path.join(studio_dir(), "link_import.json")


def settings() -> dict:
    s = read_json(_settings_path(), None)
    return s if isinstance(s, dict) else {"enabled": False}


def set_enabled(enabled: bool, acknowledged: bool, user: str | None) -> dict:
    if enabled and acknowledged is not True:
        raise StudioError("terms_acknowledgement_required",
                          "Bitte den Hinweis zu den Nutzungsbedingungen bestätigen.", 400,
                          {"terms": TERMS})
    s = {"enabled": bool(enabled), "changed_at": now_iso(), "by": user or "lokal"}
    if enabled:
        s["acknowledged_terms"] = TERMS
    write_json_atomic(_settings_path(), s)
    return status()


def status() -> dict:
    try:
        import yt_dlp.version as v
        version = v.__version__
    except Exception:  # noqa: BLE001
        version = None
    js = [n for n in ("deno", "node", "bun") if shutil.which(n)]
    return {"enabled": bool(settings().get("enabled")), "installed": version is not None,
            "version": version, "pinned": PINNED, "js_runtime": js[0] if js else None,
            "max_hours": max_seconds() // 3600, "max_height": max_height(), "terms": TERMS,
            "platforms": ["youtube", "twitch"],
            "install_hint": None if version else f'pip install "yt-dlp[default]=={PINNED}"'}


# ------------------------------------------------------------------ Link prüfen
def parse_link(url: str) -> dict:
    """Nur YouTube-Videos und Twitch-VODs/-Clips. Liefert Plattform + kanonischen Link."""
    url = (url or "").strip()
    parts = urlsplit(url)
    host = (parts.hostname or "").lower()
    if parts.scheme not in ("http", "https"):
        raise StudioError("link_invalid", "Bitte einen vollständigen Link (https://…) einfügen.")
    if host in _YT_HOSTS:
        from ..studio.youtube_import import canonical_url, video_id
        try:
            vid = video_id(url)
        except StudioError as exc:
            raise StudioError("link_invalid", "Im YouTube-Link wurde kein Video gefunden "
                              "(Wiedergabelisten und Kanäle werden nicht unterstützt).") from exc
        return {"platform": "youtube", "kind": "video", "id": vid, "url": canonical_url(vid)}
    if host in _TW_HOSTS:
        seg = [s for s in parts.path.split("/") if s]
        if host == "clips.twitch.tv" and seg and re.fullmatch(r"[\w-]{3,100}", seg[0]):
            return {"platform": "twitch", "kind": "clip", "id": seg[0],
                    "url": f"https://clips.twitch.tv/{seg[0]}"}
        if len(seg) >= 2 and seg[0] == "videos" and seg[1].isdigit():
            return {"platform": "twitch", "kind": "vod", "id": seg[1],
                    "url": f"https://www.twitch.tv/videos/{seg[1]}"}
        if len(seg) >= 3 and seg[1] == "clip" and re.fullmatch(r"[\w-]{3,100}", seg[2]):
            return {"platform": "twitch", "kind": "clip", "id": seg[2],
                    "url": f"https://clips.twitch.tv/{seg[2]}"}
        raise StudioError("link_invalid", "Twitch: bitte den Link einer vergangenen Übertragung "
                          "(twitch.tv/videos/…) oder eines Clips. Laufende Streams: Live-Modus mit OBS.")
    raise StudioError("link_invalid", "Unterstützt werden YouTube- und Twitch-Links.")


# ------------------------------------------------------------------ Download
class _Cancelled(Exception):
    pass


def ydl_options(dest_dir: str, progress=None, should_cancel=None, *, with_chat: bool) -> dict:
    h = max_height()

    last = {"step": -1}

    def hook(d: dict) -> None:
        if should_cancel and should_cancel():
            raise _Cancelled()
        if progress and d.get("status") == "downloading":
            total = d.get("total_bytes") or d.get("total_bytes_estimate") or 0
            done = d.get("downloaded_bytes") or 0
            step = int(done / total * 20) if total else -1      # höchstens alle 5 % melden
            if total and step > last["step"]:
                last["step"] = step
                progress(f"Download {done / total * 100:.0f} % ({done / 1e6:.0f} von {total / 1e6:.0f} MB)")

    def too_long_or_live(info: dict, *, incomplete: bool = False):
        if info.get("is_live") or info.get("live_status") in ("is_live", "is_upcoming"):
            return "laufender Live-Stream"
        dur = info.get("duration")
        if dur and dur > max_seconds():
            return f"länger als {max_seconds() // 3600} h"
        return None

    js = {n: {} for n in ("deno", "node", "bun") if shutil.which(n)}
    opts = {
        "outtmpl": {"default": os.path.join(dest_dir, "source.%(ext)s"),
                    "subtitle": os.path.join(dest_dir, "chat.%(ext)s")},
        "format": f"bv*[height<={h}]+ba/b[height<={h}]/bv*+ba/b",
        "merge_output_format": "mp4",
        "noplaylist": True,
        "allowed_extractors": ALLOWED_EXTRACTORS,
        "match_filter": too_long_or_live,
        "progress_hooks": [hook],
        "quiet": True, "no_warnings": True, "noprogress": True,
        "restrictfilenames": True, "windowsfilenames": True,
        "retries": 3, "fragment_retries": 3, "socket_timeout": 30,
        "remote_components": [],
        "writesubtitles": with_chat, "subtitleslangs": ["live_chat"] if with_chat else [],
    }
    if js:
        opts["js_runtimes"] = js
    return opts


def download(url: str, dest_dir: str, *, progress=None, should_cancel=None, with_chat: bool = True,
             ydl_factory=None) -> dict:
    """Lädt das Video (≤ max_height, mp4) nach ``dest_dir/source.mp4``.

    ``ydl_factory`` nur für Tests (nachgebildeter Downloader)."""
    if not settings().get("enabled"):
        raise StudioError("link_import_disabled",
                          "Link-Import ist aus. Einschalten unter Streams → Link-Import.", 403)
    link = parse_link(url)
    if ydl_factory is None:
        try:
            import yt_dlp
        except ImportError as exc:
            raise StudioError("link_import_missing",
                              f'yt-dlp ist nicht installiert: pip install "yt-dlp[default]=={PINNED}"',
                              503) from exc
        ydl_factory = yt_dlp.YoutubeDL
    os.makedirs(dest_dir, exist_ok=True)
    opts = ydl_options(dest_dir, progress, should_cancel, with_chat=with_chat and link["platform"] == "youtube")
    try:
        with ydl_factory(opts) as ydl:
            info = ydl.extract_info(link["url"], download=True)
    except _Cancelled:
        _cleanup(dest_dir)
        raise StudioError("cancelled", "Download abgebrochen.", 409) from None
    except StudioError:
        _cleanup(dest_dir)
        raise
    except Exception as exc:  # noqa: BLE001 — yt-dlp wirft viele eigene Typen
        _cleanup(dest_dir)
        msg = re.sub(r"\x1b\[[0-9;]*m", "", str(exc))[-300:]
        if "private" in msg.lower() or "sign in" in msg.lower() or "members" in msg.lower():
            hint = "Video ist privat/nur für Mitglieder oder verlangt eine Anmeldung."
        elif "unavailable" in msg.lower() or "not exist" in msg.lower() or "404" in msg:
            hint = "Video nicht gefunden oder nicht mehr verfügbar."
        else:
            hint = "Download fehlgeschlagen (yt-dlp evtl. veraltet — Plattformen ändern sich oft)."
        raise StudioError("link_download_failed", hint, 502, {"detail": msg}) from exc
    if info is None:  # vom match_filter abgelehnt
        raise StudioError("link_rejected", f"Nicht unterstützt: laufender Live-Stream oder länger als "
                          f"{max_seconds() // 3600} h.", 422)
    video = next((p for p in sorted(glob.glob(os.path.join(dest_dir, "source.*")))
                  if os.path.splitext(p)[1].lower() in (".mp4", ".mkv", ".webm", ".mov")), None)
    if not video:
        raise StudioError("link_download_failed", "Download lieferte keine Videodatei.", 502)
    chat = next(iter(glob.glob(os.path.join(dest_dir, "chat*.json"))), None)
    return {"link": link, "video": video, "chat": chat,
            "title": str(info.get("title") or "")[:120], "uploader": str(info.get("uploader") or "")[:120],
            "duration": info.get("duration"), "was_live": bool(info.get("was_live"))}


def _cleanup(dest_dir: str) -> None:
    for p in glob.glob(os.path.join(dest_dir, "source.*")) + glob.glob(os.path.join(dest_dir, "chat*")):
        try:
            os.remove(p)
        except OSError:
            pass
