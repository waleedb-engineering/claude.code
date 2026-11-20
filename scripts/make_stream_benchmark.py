#!/usr/bin/env python3
"""Erzeugt einen reproduzierbaren, SYNTHETISCHEN Stream-Testsatz mit Annotation.

Alles wird lokal mit FFmpeg (lavfi) und Zufallszahlen mit festem Seed erzeugt —
keine Fremdinhalte, keine Lizenzfragen. Die Daten prüfen die Pipeline
(Laufzeit, Speicher, Zuordnung, Grenzen, Verhalten bei fehlenden Signalen),
sagen aber NICHTS über die Qualität auf echten Streams aus. Dafür eigene VODs +
Chat-Exporte markieren und `python -m clipforge.stream.evaluate` nutzen.

Pro Aufnahme:
  <name>.mp4          Grundrauschen (ständige Bewegung), rosa Rauschen als Ton
  <name>.chat.json    TwitchDownloader-Format, Grundrate ~1,5 Nachrichten/s
  <name>.labels.json  echte Ereignisse (synthetic: true)

Ereignistypen (alle als Highlight markiert):
  full        lauter Ausbruch + Bildwechsel + Chat-Reaktion (verzögert)
  audio_chat  lauter Ausbruch + Chat-Reaktion
  chat_only   nur Chat reagiert (z. B. lustiger Moment ohne Lautstärke)
  audio_video lauter Ausbruch + Bildwechsel, Chat ruhig (z. B. ohne Zuschauer)
Störer (NICHT markiert):
  music       60 s mittellaute Töne ohne Reaktion
  spam        Chat-Welle mit neutralem Text (Gewinnspiel-Befehl)

Aufruf:  python scripts/make_stream_benchmark.py OUT --minutes 10 --count 3 [--height 720]
"""

from __future__ import annotations

import argparse
import json
import os
import random
import subprocess

KINDS = ["full", "audio_chat", "chat_only", "audio_video"]
REACT = ["KEKW", "no way", "CLIP IT", "LUL LUL", "OMEGALUL", "WHAT", "Pog", "holy", "LETS GO"]
CALM = ["hallo", "gg", "wie gehts", "nice", "lol", "welches spiel", "hi chat", "ok", "true"]


def plan(duration: int, rng: random.Random) -> tuple[list[dict], list[dict]]:
    events, decoys = [], []
    t = 45.0
    while t < duration - 60:
        t += rng.uniform(70, 160)
        if t > duration - 40:
            break
        if rng.random() < 0.2:
            kind = rng.choice(["music", "spam"])
            decoys.append({"kind": kind, "t": round(t, 1), "dur": 60.0 if kind == "music" else 8.0})
            t += 60
            continue
        kind = KINDS[len(events) % len(KINDS)]
        d = rng.uniform(4, 9)
        events.append({"kind": kind, "t": round(t, 1), "dur": round(d, 1),
                       "chat_delay": round(rng.uniform(3, 7), 1)})
    return events, decoys


def between(intervals) -> str:
    return "+".join(f"between(t,{a:.1f},{b:.1f})" for a, b in intervals) or "0"


def render(path: str, duration: int, events: list[dict], decoys: list[dict], height: int, fps: int) -> None:
    w = int(height * 16 / 9) // 2 * 2
    vis = [(e["t"], e["t"] + e["dur"]) for e in events if e["kind"] in ("full", "audio_video")]
    loud = [(e["t"], e["t"] + e["dur"]) for e in events if e["kind"] != "chat_only"]
    music = [(d["t"], d["t"] + d["dur"]) for d in decoys if d["kind"] == "music"]
    fc = (
        f"[0:v]noise=alls=14:allf=t[base];"
        f"[1:v]scale={w}:{height}[ts];"
        f"[base][ts]overlay=enable='{between(vis)}'[v];"
        f"[3:a]volume='if({between(loud)},1,0)':eval=frame[burst];"
        f"[4:a]volume='if({between(music)},1,0)':eval=frame[mus];"
        f"[2:a][burst][mus]amix=inputs=3:normalize=0[a]"
    )
    subprocess.run([
        "ffmpeg", "-v", "error", "-y",
        "-f", "lavfi", "-i", f"color=c=0x203040:s={w}x{height}:r={fps}:d={duration}",
        "-f", "lavfi", "-i", f"testsrc2=s=320x180:r={fps}:d={duration}",
        "-f", "lavfi", "-i", f"anoisesrc=c=pink:a=0.03:d={duration}",
        "-f", "lavfi", "-i", f"anoisesrc=c=white:a=0.6:d={duration}",
        "-f", "lavfi", "-i", f"sine=f=440:d={duration},volume=0.25",
        "-filter_complex", fc, "-map", "[v]", "-map", "[a]",
        "-c:v", "libx264", "-preset", "veryfast", "-crf", "28", "-g", str(fps * 4),
        "-c:a", "aac", "-b:a", "96k", path], check=True)


def chat(duration: int, events: list[dict], decoys: list[dict], rng: random.Random) -> list[dict]:
    out = []

    def add(t, user, body):
        out.append({"content_offset_seconds": round(t, 2), "commenter": {"display_name": user},
                    "message": {"body": body, "fragments": [{"text": body}]}})
    t = 0.0
    while t < duration:
        t += rng.expovariate(1.5)
        add(t, f"viewer{rng.randint(1, 150)}", rng.choice(CALM))
    for e in events:
        if e["kind"] == "audio_video":
            continue
        start = e["t"] + e["chat_delay"]
        for _ in range(rng.randint(35, 70)):
            add(start + rng.uniform(0, 7), f"fan{rng.randint(1, 400)}", rng.choice(REACT))
    for d in decoys:
        if d["kind"] == "spam":
            for _ in range(rng.randint(40, 60)):
                add(d["t"] + rng.uniform(0, d["dur"]), f"viewer{rng.randint(1, 150)}", "!giveaway")
    out.sort(key=lambda m: m["content_offset_seconds"])
    return [m for m in out if m["content_offset_seconds"] < duration]


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("out")
    ap.add_argument("--minutes", type=float, default=10)
    ap.add_argument("--count", type=int, default=3)
    ap.add_argument("--height", type=int, default=360)
    ap.add_argument("--fps", type=int, default=30)
    ap.add_argument("--seed", type=int, default=2026)
    ap.add_argument("--no-chat-every", type=int, default=0,
                    help="jede n-te Aufnahme ohne Chat-Export (fehlende Daten testen)")
    a = ap.parse_args()
    os.makedirs(a.out, exist_ok=True)
    duration = int(a.minutes * 60)
    for i in range(a.count):
        rng = random.Random(a.seed + i)
        name = f"synth_{int(a.minutes)}min_{i + 1:02d}"
        events, decoys = plan(duration, rng)
        render(os.path.join(a.out, name + ".mp4"), duration, events, decoys, a.height, a.fps)
        with_chat = not (a.no_chat_every and (i + 1) % a.no_chat_every == 0)
        if with_chat:
            with open(os.path.join(a.out, name + ".chat.json"), "w", encoding="utf-8") as fh:
                json.dump({"video": {"length": duration}, "comments": chat(duration, events, decoys, rng)}, fh)
        labels = [{"start": e["t"], "end": round(e["t"] + e["dur"], 1), "peak": e["t"], "label": e["kind"]}
                  for e in events if with_chat or e["kind"] != "chat_only"]
        with open(os.path.join(a.out, name + ".labels.json"), "w", encoding="utf-8") as fh:
            json.dump({"version": 1, "synthetic": True,
                       "source": "synthetisch erzeugt (FFmpeg lavfi, Seed %d) — keine Fremdinhalte" % (a.seed + i),
                       "has_chat": with_chat, "decoys": decoys, "highlights": labels}, fh, indent=1)
        print(f"{name}: {len(labels)} Ereignisse, {len(decoys)} Störer, Chat={'ja' if with_chat else 'nein'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
