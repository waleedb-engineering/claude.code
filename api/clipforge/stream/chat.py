"""Chat-Verläufe einlesen und in Sekunden-Signale verwandeln.

Unterstützte Formate (vom Nutzer exportiert, kein Abruf durch ClipForge):
- TwitchDownloader-JSON (`comments[].content_offset_seconds`, `message.body`,
  `message.fragments[].emoticon`)
- chat-downloader-JSON (Liste mit `time_in_seconds`, `message`, `author.name`)
- yt-dlp / YouTube-Live-Chat (JSON-Lines mit `replayChatItemAction` und
  `videoOffsetTimeMsec`)
- allgemeines JSON (Liste von {t|time|offset, user|author, text|message}),
  JSON-Lines mit denselben Feldern, CSV mit Kopfzeile (t,user,text)
"""

from __future__ import annotations

import csv
import io
import json
import re
from dataclasses import dataclass, field

MAX_MESSAGES = 2_000_000


@dataclass
class ChatMessage:
    t: float          # Sekunden ab Videostart
    user: str
    text: str
    emotes: list[str] = field(default_factory=list)


# Reaktionskategorien (Twitch-/YouTube-Emotes und Phrasen, de + en).
# Treffer sind Hinweise, keine Gewissheit — die Begründung nennt sie offen.
CATEGORIES = {
    "laugh": re.compile(
        r"\b(kekw|lul|lulw|omegalul|icant|lmao+|lmfao|rofl|lol+|xd+|haha+h*|hehe+|jaja+|"
        r"ahaha+|😂|🤣|💀)", re.I),
    "hype": re.compile(
        r"\b(pog(champ|gers|u)?|pogchamp|lets+ ?go+|let'?s go+|goat|insane|cracked|w+ |hype|"
        r"ez clap|clutch|sheesh+|geil|krass|wahnsinn|🔥)", re.I),
    "shock": re.compile(
        r"(\bwtf\b|\bomg\b|\bno+ ?way\b|\bwhat+\b|\bwas\b\?|\bmonka\w*|\bhuh+\b|\bbro+\b|\?{3,}|"
        r"😱|😳|\boh (my )?god\b|\bnicht dein ernst\b|\balter\b)", re.I),
    "clip": re.compile(r"\b(clip (it|that|das)|clipt?|klippen?|\+clip)\b", re.I),
    "negative": re.compile(
        r"\b(boring|langweilig|cringe|l+ |ratio|trash|mid|skip|resid\w*|fail)\b", re.I),
}


def _num(v) -> float | None:
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def _from_twitchdownloader(data: dict) -> list[ChatMessage]:
    out = []
    for c in data.get("comments") or []:
        t = _num(c.get("content_offset_seconds"))
        msg = c.get("message") or {}
        if t is None:
            continue
        emotes = [f.get("text", "") for f in (msg.get("fragments") or [])
                  if isinstance(f, dict) and f.get("emoticon")]
        user = ((c.get("commenter") or {}).get("display_name")
                or (c.get("commenter") or {}).get("name") or "?")
        out.append(ChatMessage(t, str(user)[:40], str(msg.get("body") or "")[:500], emotes[:20]))
    return out


def _from_list(items: list) -> list[ChatMessage]:
    out = []
    for it in items:
        if not isinstance(it, dict):
            continue
        t = _num(it.get("time_in_seconds", it.get("t", it.get("time", it.get("offset")))))
        if t is None:
            continue
        author = it.get("author")
        user = (author.get("name") if isinstance(author, dict) else author) or it.get("user") or "?"
        text = it.get("message", it.get("text", ""))
        emotes = [e.get("name", "") for e in (it.get("emotes") or []) if isinstance(e, dict)]
        out.append(ChatMessage(t, str(user)[:40], str(text or "")[:500], emotes[:20]))
    return out


def _from_ytdlp_line(obj: dict) -> ChatMessage | None:
    action = obj.get("replayChatItemAction") or {}
    t = _num(action.get("videoOffsetTimeMsec"))
    for a in action.get("actions") or []:
        item = ((a.get("addChatItemAction") or {}).get("item") or {})
        r = item.get("liveChatTextMessageRenderer") or item.get("liveChatPaidMessageRenderer")
        if not r or t is None:
            continue
        runs = (r.get("message") or {}).get("runs") or []
        text, emotes = [], []
        for run in runs:
            if "text" in run:
                text.append(run["text"])
            elif "emoji" in run:
                sc = (run["emoji"].get("shortcuts") or [""])[0]
                text.append(sc)
                emotes.append(sc)
        user = ((r.get("authorName") or {}).get("simpleText")) or "?"
        return ChatMessage(t / 1000.0, str(user)[:40], "".join(text)[:500], emotes[:20])
    return None


def parse_chat(raw: bytes, filename: str = "") -> tuple[list[ChatMessage], str]:
    """→ (Nachrichten sortiert, erkanntes Format). Fehler → ValueError mit Klartext."""
    text = raw.decode("utf-8-sig", errors="replace")
    stripped = text.lstrip()
    msgs: list[ChatMessage] = []
    fmt = "unbekannt"
    if filename.lower().endswith(".csv") or (stripped[:1] not in "{[" and "," in stripped[:200]):
        reader = csv.DictReader(io.StringIO(text))
        msgs = _from_list(list(reader))
        fmt = "csv"
    elif stripped.startswith("{") and "\n{" in stripped:  # JSON-Lines
        for line in text.splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                obj = json.loads(line)
            except ValueError:
                continue
            if "replayChatItemAction" in obj:
                m = _from_ytdlp_line(obj)
                if m:
                    msgs.append(m)
                fmt = "youtube_live_chat"
            else:
                msgs.extend(_from_list([obj]))
                fmt = fmt if fmt != "unbekannt" else "jsonl"
    else:
        try:
            data = json.loads(text)
        except ValueError as exc:
            raise ValueError("Chat-Datei ist weder JSON, JSON-Lines noch CSV.") from exc
        if isinstance(data, dict) and "comments" in data:
            msgs, fmt = _from_twitchdownloader(data), "twitchdownloader"
        elif isinstance(data, dict) and "replayChatItemAction" in data:
            m = _from_ytdlp_line(data)
            msgs, fmt = ([m] if m else []), "youtube_live_chat"
        elif isinstance(data, list):
            msgs, fmt = _from_list(data), "json_list"
        elif isinstance(data, dict) and isinstance(data.get("messages"), list):
            msgs, fmt = _from_list(data["messages"]), "json_messages"
    msgs = [m for m in msgs if m.t >= 0][:MAX_MESSAGES]
    if not msgs:
        raise ValueError("Keine Chat-Nachrichten mit Zeitangabe gefunden.")
    msgs.sort(key=lambda m: m.t)
    return msgs, fmt


def categorize(text: str) -> list[str]:
    return [name for name, rx in CATEGORIES.items() if rx.search(text)]


def per_second(msgs: list[ChatMessage], duration: float) -> dict:
    """Sekunden-Reihen: Nachrichten, eindeutige Chatter, Kategorien, Emotes."""
    n = max(1, int(duration) + 1)
    rate = [0] * n
    users: list[set] = [set() for _ in range(n)]
    cats = {k: [0] * n for k in CATEGORIES}
    emotes = [0] * n
    words: list[list[str]] = [[] for _ in range(n)]
    for m in msgs:
        i = int(m.t)
        if i >= n:
            continue
        rate[i] += 1
        users[i].add(m.user)
        emotes[i] += len(m.emotes)
        for c in categorize(m.text + " " + " ".join(m.emotes)):
            cats[c][i] += 1
        words[i].extend(w.lower() for w in re.findall(r"[\wäöüß?!]{2,}", m.text)[:12])
    return {"rate": rate, "unique": [len(u) for u in users], "categories": cats,
            "emotes": emotes, "words": words}
