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


class LiveSession:
    """Eine laufende Live-Sitzung; Zustand und Chat landen fortlaufend auf Platte."""

    def __init__(self, folder: str, *, channel: str | None, recording: str | None,
                 recording_started_at: float, chat_delay: float = 5.0, pre: float = 20.0,
                 post: float = 10.0, threshold: float = 3.0, reader_factory=None) -> None:
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
        self.reader = None
        if channel:
            factory = reader_factory or (lambda ch, cb: TwitchChatReader(ch, cb))
            self.reader = factory(channel, self._on_message)

    def _on_message(self, user: str, text: str, emotes: list[str]) -> None:
        t = time.time() - self.t0
        with self.lock:
            self.counts[int(t)] = self.counts.get(int(t), 0) + 1
            self.chat_file.write(json.dumps({"t": round(t, 2), "user": user, "text": text,
                                             "emotes": emotes}, ensure_ascii=False) + "\n")
            self.chat_file.flush()  # sofort sichern

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
            self.events.append(item)
            self.queue.append(item)
        done = []
        if self.recording:
            have = recording_seconds(self.recording)
            if have <= 0 and os.path.exists(self.recording) and \
                    time.time() - os.path.getmtime(self.recording) < 5:
                # wachsende MKV hat noch keine Dauer im Kopf → verstrichene Zeit (−3 s Puffer)
                have = max(0.0, time.time() - self.t0 - 3)
            for item in list(self.queue):
                if have >= item["end"] + 1:
                    out = os.path.join(self.folder, "live_clips", f"{item['id']}.mp4")
                    try:
                        cut_from_recording(self.recording, item["start"], item["end"], out)
                        item.update(status="cut", file=os.path.basename(out))
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
            "chat_error": self.reader.error if self.reader else None})

    def close(self) -> None:
        if self.reader:
            self.reader.stop()
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


__all__ = ["TwitchChatReader", "SpikeDetector", "LiveSession", "categorize", "chat_from_jsonl"]
