"""Live-Modus: Highlights erkennen, während der Stream läuft.

Echtzeit-Verfügbarkeit (ehrlich):
- Twitch-Chat: Echtzeit über Twitch-IRC (offizielle Chat-Schnittstelle,
  anonymes Lesen ohne Konto erlaubt).
- YouTube-Chat: Echtzeit über die YouTube Data API (liveChatMessages,
  API-Schlüssel, Kontingent) — gegen die echte API ungetestet.
- Kick: keine stabile öffentliche Chat-Schnittstelle → nur VOD mit Chat-Export.
- Video: nur aus der eigenen, wachsenden OBS-Aufnahme (lokaler Modus). Fremde
  Streams werden nicht mitgeschnitten.

Ablauf: Chat-Nachrichten landen sofort in chat_live.jsonl (kein Datenverlust
bei Absturz). Alle 2 s: Rate der letzten 3 s gegen die Grundrate der letzten
5 min (robuster z-Wert mit Rausch-Untergrenze). Ausbruch → Ereigniszeit =
Beginn − Chat-Verzögerung → Clip-Auftrag in die Warteschlange; geschnitten
wird, sobald die Aufnahme weit genug ist.
"""

from __future__ import annotations

import json
import os
import random
import re
import socket
import ssl
import subprocess
import threading
import time

from .chat import ChatMessage, categorize

IRC_HOST, IRC_PORT = "irc.chat.twitch.tv", 6697
_CHANNEL = re.compile(r"^[a-z0-9_]{3,25}$")


class TwitchChatReader(threading.Thread):
    """Liest öffentlichen Twitch-Chat anonym (justinfan) über IRC/TLS."""

    def __init__(self, channel: str, on_message, host: str = IRC_HOST, port: int = IRC_PORT,
                 use_tls: bool = True) -> None:
        super().__init__(daemon=True)
        channel = channel.lower().lstrip("#")
        if not _CHANNEL.match(channel):
            raise ValueError("Ungültiger Twitch-Kanalname.")
        self.channel, self.on_message = channel, on_message
        self.host, self.port, self.use_tls = host, port, use_tls
        self.stop_event = threading.Event()
        self.connected = threading.Event()
        self.error: str | None = None

    def stop(self) -> None:
        self.stop_event.set()

    def _connect(self):
        sock = socket.create_connection((self.host, self.port), timeout=15)
        if self.use_tls:
            sock = ssl.create_default_context().wrap_socket(sock, server_hostname=self.host)
        sock.settimeout(1.0)
        nick = f"justinfan{random.randint(10000, 99999)}"
        for line in ("CAP REQ :twitch.tv/tags", "PASS SCHMOOPIIE", f"NICK {nick}",
                     f"JOIN #{self.channel}"):
            sock.sendall((line + "\r\n").encode())
        return sock

    @staticmethod
    def parse(line: str) -> tuple[str, str, list[str]] | None:
        """→ (Benutzer, Text, Emotes) für PRIVMSG-Zeilen."""
        tags = {}
        if line.startswith("@"):
            raw, line = line[1:].split(" ", 1)
            tags = dict(kv.split("=", 1) for kv in raw.split(";") if "=" in kv)
        m = re.match(r"^:(\w+)!\S+ PRIVMSG #\w+ :(.*)$", line)
        if not m:
            return None
        user, text = tags.get("display-name") or m.group(1), m.group(2)
        emotes = []
        for part in (tags.get("emotes") or "").split("/"):
            if ":" in part:
                for rng in part.split(":", 1)[1].split(","):
                    try:
                        a, b = (int(x) for x in rng.split("-"))
                        emotes.append(text[a:b + 1])
                    except ValueError:
                        continue
        return user[:40], text[:500], emotes[:20]

    def run(self) -> None:
        backoff = 1.0
        while not self.stop_event.is_set():
            try:
                sock = self._connect()
                self.connected.set()
                backoff, buf = 1.0, ""
                while not self.stop_event.is_set():
                    try:
                        chunk = sock.recv(65536).decode("utf-8", "replace")
                    except (socket.timeout, TimeoutError):
                        continue
                    if not chunk:
                        raise ConnectionError("Verbindung geschlossen")
                    buf += chunk
                    while "\r\n" in buf:
                        line, buf = buf.split("\r\n", 1)
                        if line.startswith("PING"):
                            sock.sendall(line.replace("PING", "PONG", 1).encode() + b"\r\n")
                            continue
                        msg = self.parse(line)
                        if msg:
                            self.on_message(*msg)
                sock.close()
            except Exception as exc:  # noqa: BLE001 — automatisch neu verbinden
                self.error = f"{type(exc).__name__}"
                self.connected.clear()
                self.stop_event.wait(backoff)
                backoff = min(30.0, backoff * 2)


class SpikeDetector:
    """Ausbruchs-Erkennung auf einem gleitenden Fenster (Sekunden-Raster)."""

    def __init__(self, threshold: float = 3.0, min_messages: int = 8, cooldown: float = 30.0) -> None:
        self.threshold, self.min_messages, self.cooldown = threshold, min_messages, cooldown
        self.last_spike = -1e9

    def check(self, counts: dict[int, int], now: float) -> dict | None:
        """counts: Sekunde → Nachrichten. → Ausbruch oder None."""
        cur_s = int(now)
        # die letzten 3 Sekunden einschließlich der laufenden
        recent = sum(counts.get(s, 0) for s in range(cur_s - 2, cur_s + 1))
        base = [sum(counts.get(s, 0) for s in range(b, b + 3)) for b in range(cur_s - 302, cur_s - 2, 3)]
        base = sorted(base) or [0]
        med = base[len(base) // 2]
        mad = sorted(abs(x - med) for x in base)[len(base) // 2]
        floor = max(1.0, med ** 0.5)  # Poisson-ähnliche Rausch-Untergrenze
        z = (recent - med) / (1.4826 * mad + floor)
        if recent >= self.min_messages and z >= self.threshold and now - self.last_spike >= self.cooldown:
            self.last_spike = now
            return {"t": now - 3, "z": round(z, 1), "messages": recent, "baseline": med}
        return None


def cut_from_recording(recording: str, start: float, end: float, out: str) -> None:
    """Schneidet aus der (evtl. noch wachsenden) Aufnahme; MKV verträgt das."""
    subprocess.run(["ffmpeg", "-y", "-v", "error", "-ss", f"{max(0.0, start):.2f}", "-i", recording,
                    "-t", f"{end - start:.2f}", "-c:v", "libx264", "-preset", "veryfast", "-crf", "20",
                    "-c:a", "aac", "-movflags", "+faststart", out], check=True, timeout=600)


def recording_seconds(recording: str) -> float:
    """Wie weit ist die Aufnahme? (ffprobe; bei wachsender MKV ggf. Dateigröße/Bitrate)."""
    try:
        out = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration",
                              "-of", "default=nw=1:nk=1", recording], capture_output=True, text=True,
                             timeout=20).stdout.strip()
        return float(out)
    except (ValueError, OSError, subprocess.SubprocessError):
        return 0.0


YT_API = "https://www.googleapis.com/youtube/v3"
_YT_ID = re.compile(r"^[A-Za-z0-9_-]{11}$")


def youtube_video_id(value: str) -> str:
    """Video-ID aus ID oder youtube.com/youtu.be-Link (nur diese Hosts)."""
    v = (value or "").strip()
    if _YT_ID.match(v):
        return v
    m = re.match(r"^https?://(?:www\.|m\.)?(?:youtube\.com/(?:watch\?(?:.*&)?v=|live/)|youtu\.be/)"
                 r"([A-Za-z0-9_-]{11})", v)
    if not m:
        raise ValueError("Ungültige YouTube-Video-ID oder -Link.")
    return m.group(1)


class YouTubeLiveChatReader(threading.Thread):
    """Liest den Live-Chat über die offizielle YouTube Data API v3.

    - videos.list(liveStreamingDetails) → activeLiveChatId (1 Einheit)
    - liveChatMessages.list im vom Server vorgegebenen Takt (pollingIntervalMillis),
      nie schneller als ``min_interval`` (Kontingent: Standard 10 000 Einheiten/Tag;
      jede Abfrage kostet laut Google 5 Einheiten — Schätzung wird angezeigt)
    - Zeitstempel = publishedAt der Nachricht (nicht Empfangszeit)
    Fehler (Kontingent, Chat beendet, Schlüssel ungültig) beenden den Leser mit
    verständlicher Meldung; Twitch/OBS laufen unabhängig weiter.
    """

    UNITS_PER_POLL = 5

    def __init__(self, video: str, on_message, api_key: str, *, api_base: str = YT_API,
                 min_interval: float = 5.0, t0: float | None = None) -> None:
        super().__init__(daemon=True)
        self.video_id = youtube_video_id(video)
        self.on_message, self.key, self.api = on_message, api_key, api_base.rstrip("/")
        self.min_interval = max(1.0, float(min_interval))
        self.t0 = t0
        self.stop_event = threading.Event()
        self.connected = threading.Event()
        self.error: str | None = None
        self.polls = 0
        self.chat_id: str | None = None

    def stop(self) -> None:
        self.stop_event.set()

    def _get(self, path: str, params: dict) -> dict:
        import urllib.error
        import urllib.parse
        import urllib.request
        q = urllib.parse.urlencode({**params, "key": self.key})
        try:
            with urllib.request.urlopen(f"{self.api}/{path}?{q}", timeout=20) as resp:  # noqa: S310 — fester Host
                return json.loads(resp.read(4 * 1024 * 1024))
        except urllib.error.HTTPError as exc:
            reason = ""
            try:
                reason = json.loads(exc.read(65536))["error"]["errors"][0]["reason"]
            except Exception:  # noqa: BLE001
                pass
            raise RuntimeError(f"HTTP {exc.code} {reason}".strip()) from None

    @staticmethod
    def explain(err: str) -> str:
        if "quotaExceeded" in err or "rateLimitExceeded" in err:
            return "YouTube-API-Kontingent erschöpft — morgen wieder oder Kontingent erhöhen."
        if "liveChatEnded" in err or "liveChatNotFound" in err:
            return "Der Live-Chat ist beendet oder nicht vorhanden."
        if "liveChatDisabled" in err:
            return "Der Live-Chat ist für dieses Video deaktiviert."
        if "401" in err or "403" in err or "forbidden" in err.lower():
            return ("Zugriff verweigert — API-Schlüssel prüfen; private/nicht gelistete Streams "
                    "brauchen OAuth (noch nicht angebunden).")
        if "400" in err and "key" in err.lower():
            return "API-Schlüssel ungültig."
        return f"YouTube-API-Fehler ({err[:80]})."

    def run(self) -> None:
        from datetime import datetime
        try:
            data = self._get("videos", {"part": "liveStreamingDetails", "id": self.video_id})
            items = data.get("items") or []
            if not items:
                raise RuntimeError("liveChatNotFound (Video nicht gefunden)")
            self.chat_id = (items[0].get("liveStreamingDetails") or {}).get("activeLiveChatId")
            if not self.chat_id:
                raise RuntimeError("liveChatNotFound (kein aktiver Live-Chat)")
            self.connected.set()
            token = None
            while not self.stop_event.is_set():
                params = {"liveChatId": self.chat_id, "part": "snippet,authorDetails", "maxResults": 2000}
                if token:
                    params["pageToken"] = token
                data = self._get("liveChat/messages", params)
                self.polls += 1
                for it in data.get("items") or []:
                    sn, au = it.get("snippet") or {}, it.get("authorDetails") or {}
                    text = sn.get("displayMessage") or (sn.get("textMessageDetails") or {}).get("messageText") or ""
                    if not text:
                        continue
                    ts = None
                    try:
                        ts = datetime.fromisoformat(sn["publishedAt"].replace("Z", "+00:00")).timestamp()
                    except (KeyError, ValueError):
                        pass
                    self.on_message(str(au.get("displayName") or "?")[:40], text[:500], [], ts)
                token = data.get("nextPageToken")
                wait = max(self.min_interval, float(data.get("pollingIntervalMillis") or 0) / 1000.0)
                if data.get("offlineAt"):
                    raise RuntimeError("liveChatEnded")
                self.stop_event.wait(wait)
        except Exception as exc:  # noqa: BLE001
            self.error = self.explain(str(exc))
        finally:
            self.connected.clear()

    def quota_estimate(self, hours: float = 1.0) -> int:
        return int(hours * 3600 / self.min_interval * self.UNITS_PER_POLL)


class LiveSession:
    """Eine laufende Live-Sitzung; Zustand und Chat landen fortlaufend auf Platte."""

    def __init__(self, folder: str, *, channel: str | None, recording: str | None,
                 recording_started_at: float, chat_delay: float = 5.0, pre: float = 20.0,
                 post: float = 10.0, threshold: float = 3.0, reader_factory=None,
                 youtube: str | None = None, youtube_key: str | None = None, yt_factory=None,
                 max_pending: int = 20) -> None:
        self.folder = folder
        os.makedirs(os.path.join(folder, "live_clips"), exist_ok=True)
        self.channel, self.recording = channel, recording
        self.t0 = recording_started_at
        self.chat_delay, self.pre, self.post = chat_delay, pre, post
        self.detector = SpikeDetector(threshold=threshold)
        self.counts: dict[int, int] = {}
        self.lock = threading.Lock()
        self.chat_file = open(os.path.join(folder, "chat_live.jsonl"), "a", encoding="utf-8")
        self.queue: list[dict] = []
        self.events: list[dict] = []
        self.max_pending = max_pending
        self.skipped = 0
        self.reader = None
        self.yt_reader = None
        if channel:
            factory = reader_factory or (lambda ch, cb: TwitchChatReader(ch, cb))
            self.reader = factory(channel, self._on_message)
        if youtube:
            yf = yt_factory or (lambda vid, cb: YouTubeLiveChatReader(vid, cb, youtube_key or ""))
            self.yt_reader = yf(youtube, self._on_message)

    def readers(self) -> list:
        return [r for r in (self.reader, self.yt_reader) if r is not None]

    def _on_message(self, user: str, text: str, emotes: list[str], ts: float | None = None) -> None:
        t = (ts if ts is not None else time.time()) - self.t0
        if t < 0:
            return  # Nachricht vor Beginn der Aufnahme (z. B. Rückstand beim ersten Abruf)
        with self.lock:
            self.counts[int(t)] = self.counts.get(int(t), 0) + 1
            self.chat_file.write(json.dumps({"t": round(t, 2), "user": user, "text": text,
                                             "emotes": emotes}, ensure_ascii=False) + "\n")
            self.chat_file.flush()  # sofort sichern

    def _enqueue(self, item: dict) -> None:
        self.events.append(item)
        if len(self.queue) >= self.max_pending:
            # Schutz vor Render-Stau: älteste wartende Marke nicht schneiden, aber behalten
            old = self.queue.pop(0)
            old.update(status="skipped", note="Warteschlange voll — später aus der VOD-Analyse schneiden")
            old.pop("queue_position", None)
            self.skipped += 1
        self.queue.append(item)

    def tick(self, now: float | None = None) -> list[dict]:
        """Einmal prüfen: Ausbrüche erkennen, fällige Clips schneiden. → neue Clips."""
        now = (time.time() - self.t0) if now is None else now
        with self.lock:
            spike = self.detector.check(dict(self.counts), now)
        if spike:
            event = spike["t"] - self.chat_delay
            item = {"id": f"l{len(self.events) + 1:02d}", "event": round(event, 2),
                    "start": round(max(0.0, event - self.pre), 2), "end": round(event + self.post, 2),
                    "reason": f"Chat-Ausbruch: {spike['messages']} Nachrichten in 3 s "
                              f"(üblich {spike['baseline']}), z={spike['z']}, Verzögerung "
                              f"{self.chat_delay:.0f} s abgezogen", "status": "queued"}
            self._enqueue(item)
        done = []
        if self.recording:
            have = recording_seconds(self.recording)
            if have <= 0 and os.path.exists(self.recording) and \
                    time.time() - os.path.getmtime(self.recording) < 5:
                # wachsende MKV hat noch keine Dauer im Kopf → verstrichene Zeit (−3 s Puffer)
                have = max(0.0, time.time() - self.t0 - 3)
            cut_now = 0
            for pos, item in enumerate(list(self.queue)):
                item["queue_position"] = pos + 1
                if have < item["end"] + 1:
                    item["status"] = "waiting_for_recording"
                    continue
                if cut_now >= 1:  # höchstens ein Schnitt pro Takt → nie mehrere FFmpeg parallel
                    continue
                cut_now += 1
                out = os.path.join(self.folder, "live_clips", f"{item['id']}.mp4")
                try:
                    cut_from_recording(self.recording, item["start"], item["end"], out)
                    item.update(status="cut", file=os.path.basename(out))
                    item.pop("queue_position", None)
                except Exception as exc:  # noqa: BLE001
                    item.update(status="failed", error=type(exc).__name__)
                self.queue.remove(item)
                done.append(item)
        else:
            for item in list(self.queue):
                item["status"] = "marked"  # ohne Aufnahme: nur Zeitmarke
                self.queue.remove(item)
                done.append(item)
        self.save_state(now)
        return done

    def save_state(self, now: float) -> None:
        from ..studio.storage import write_json_atomic
        write_json_atomic(os.path.join(self.folder, "live_state.json"), {
            "channel": self.channel, "recording": bool(self.recording), "elapsed": round(now, 1),
            "messages": sum(self.counts.values()), "events": self.events,
            "chat_connected": bool(self.reader and self.reader.connected.is_set()),
            "chat_error": self.reader.error if self.reader else None,
            "youtube": ({"connected": self.yt_reader.connected.is_set(), "error": self.yt_reader.error,
                         "polls": self.yt_reader.polls,
                         "quota_units_used": self.yt_reader.polls * YouTubeLiveChatReader.UNITS_PER_POLL}
                        if self.yt_reader else None),
            "pending": len(self.queue), "skipped": self.skipped})

    def close(self) -> None:
        for r in self.readers():
            r.stop()
        self.chat_file.close()


def chat_from_jsonl(path: str) -> list[ChatMessage]:
    out = []
    if os.path.exists(path):
        with open(path, encoding="utf-8") as fh:
            for line in fh:
                try:
                    d = json.loads(line)
                    out.append(ChatMessage(float(d["t"]), d["user"], d["text"], d.get("emotes") or []))
                except (ValueError, KeyError):
                    continue
    return out


__all__ = ["TwitchChatReader", "YouTubeLiveChatReader", "SpikeDetector", "LiveSession", "categorize", "chat_from_jsonl"]
