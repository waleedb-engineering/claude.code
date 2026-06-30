# ClipForge AI

KI-gestütztes Tool, das aus **langen Videos automatisch starke Kurzclips** für
TikTok, Instagram Reels und YouTube Shorts erzeugt.

📄 **Produktdefinition:** [`docs/PRODUCT.md`](docs/PRODUCT.md) — Problem, Lösung,
MVP-Scope, Architektur, Risiken und Akzeptanzkriterien.
🌐 **Web-Plan:** [`docs/WEB_PLAN.md`](docs/WEB_PLAN.md) · **HTTP-API:**
[`docs/API.md`](docs/API.md) — FastAPI-Bridge über dem Pipeline-Kern ·
🖥️ **Web-App:** [`docs/WEB.md`](docs/WEB.md) — Next.js-UI lokal starten.

## Schnellstart Web-App

```bash
# Terminal A — Backend
cd api && export PYTHONPATH=$PWD && pip install -r requirements.txt
uvicorn app:app --reload --port 8000

# Terminal B — Frontend
cd web && npm install && cp .env.example .env.local
npm run dev      # http://127.0.0.1:3000
```

> **Ehrlicher Hinweis:** ClipForge garantiert **keine** Viralität. Es
> **maximiert die Wahrscheinlichkeit** für starke Performance durch messbare
> Signale: Hook-Erkennung, Retention-Optimierung, automatische Clip-Auswahl,
> Untertitel, schnelle Schnitte, einen transparenten **Performance-Potential-
> Score**, Plattform-Metadaten und Varianten-Testing.

---

## Status

| Stufe | Inhalt | Status |
|---|---|---|
| Schritt 1–2 | Lauffähiger **Pipeline-Kern als CLI** | ✅ fertig & verifiziert |
| Schritt 3 | **FastAPI-Layer** (Upload, Job-Status, Preview, Download, ZIP) | ✅ fertig & verifiziert |
| Schritt 4 | **Next.js + Tailwind Frontend** | ✅ fertig & verifiziert |
| Schritt 5 | **Schnelle Schnitte** (Silence-Removal) | ✅ fertig & verifiziert |
| später | Face-Tracking-Reframe, echtes A/B-Tracking, Direkt-Posten | 🔭 später |

### Was schon echt funktioniert
- **Transkription** lokal via `faster-whisper` (Wort-Level-Timestamps) — verifiziert
- **Clip-Auswahl** aus dem Transkript (erklärbarer Segmenter)
- **Performance-Potential-Score** als transparente Heuristik (Hook, Klarheit,
  Emotion, Tempo, Pointe) — **optional** durch Claude verstärkt
- **Rendering** zu 9:16-MP4 mit **eingebrannten Untertiteln** (FFmpeg) — verifiziert
- **Wortgenaue Karaoke-Captions** (ASS): aktuelles Wort hervorgehoben, 2 Styles
  (`clean`/`high_energy`), automatischer Umbruch in der Safe Area, Fallback auf
  Standard ohne Wort-Timestamps — verifiziert
- **Smart 9:16-Reframe**: richtet den Ausschnitt lokal (OpenCV) auf das Gesicht
  aus (Smart static crop v1), sauberer Center-Fallback — verifiziert
- **Silence-Removal** („schnelle Schnitte"): entfernt stille Pausen synchron in
  Video/Audio und **mappt die Untertitel-Timings korrekt mit** — verifiziert
- **Web-App + API**: Upload, Live-Status, `<video>`-Vorschau, Einzel- & ZIP-Download
- **Plattform-Metadaten** (Titel/Beschreibung/Hashtags) + **Hook-Varianten**
  (nur mit gesetztem `ANTHROPIC_API_KEY`)

### Klar als TODO gekennzeichnet (noch nicht echt)
- Reframe ist **statischer** Smart-Crop (ein Fokuspunkt pro Clip) — **kein
  dynamisches Per-Frame-Tracking** (bewusste, stabile MVP-Wahl) — `reframe.py`
- **A/B-Performance-Messung** erzeugt Varianten, misst aber (noch) keine echten
  Plattform-Views — dafür bräuchte es Plattform-APIs

---

## Architektur

```
api/
  clipforge/
    config.py        # Einstellungen via ENV
    models.py        # Datenmodelle (Word, Clip, Score, Metadata)
    ffmpeg_utils.py  # probe, Audio-Extraktion, Stille-Erkennung
    transcribe.py    # faster-whisper + JSON-Transkript-Loader
    segmenter.py     # Transkript -> Kandidaten-Clips
    scoring.py       # Heuristik + Claude-Scoring (Kern-IP)
    captions.py      # Wort-Timestamps -> ASS-Untertitel
    render.py        # ffmpeg: 9:16-Crop + Untertitel einbrennen
    pipeline.py      # Orchestrierung
    cli.py           # Kommandozeile
  tests/             # abhängigkeitsfreie Regressionstests
web/                 # (Schritt 4) Next.js + Tailwind
```

**Stack:** Python/FastAPI (Backend), faster-whisper (lokal), Claude (Scoring),
FFmpeg (Schnitt/Untertitel), Next.js + TypeScript + TailwindCSS (Frontend, folgt).

---

## Setup

```bash
# Systemabhängigkeit
sudo apt-get install -y ffmpeg

# Python-Abhängigkeiten
cd api
pip install -r requirements.txt
```

Optional für Claude-Scoring/Metadaten:
```bash
export ANTHROPIC_API_KEY=sk-ant-...
# ohne Key läuft alles weiter — nur mit reiner Heuristik
```

---

## Nutzung (CLI)

```bash
cd api
export PYTHONPATH=$PWD

# Variante A: volle Pipeline mit lokaler Transkription
python -m clipforge.cli mein_video.mp4 --out ./out --top 5

# Variante B: ohne Modell-Download, mit vorhandenem Transkript
python -m clipforge.cli mein_video.mp4 --transcript transkript.json --out ./out

# Nur analysieren/scoren, nicht rendern
python -m clipforge.cli mein_video.mp4 --transcript transkript.json --no-render

# Mit Silence-Removal (schnelle Schnitte: entfernt stille Pausen)
python -m clipforge.cli mein_video.mp4 --transcript transkript.json --remove-silence

# Silence-Removal ohne Audio-Glättung an den Schnitten
python -m clipforge.cli mein_video.mp4 --transcript transkript.json --remove-silence --no-audio-smoothing

# Untertitel-Modus & -Style wählen (Default: karaoke / high_energy)
python -m clipforge.cli mein_video.mp4 --transcript transkript.json \
       --caption-mode karaoke --caption-style high_energy
python -m clipforge.cli mein_video.mp4 --transcript transkript.json \
       --caption-mode standard --caption-style clean

# Bildausrichtung wählen (Default: smart)
python -m clipforge.cli mein_video.mp4 --transcript transkript.json --reframe-mode smart
python -m clipforge.cli mein_video.mp4 --transcript transkript.json --reframe-mode center
```

> **Smart-Reframe (`--reframe-mode smart|face|center`, Default `smart`):**
> richtet den 9:16-Ausschnitt **lokal** (OpenCV Haar-Cascade, keine Cloud) auf
> das erkannte Gesicht aus — Sampling über den Clip, Median-Fokuspunkt, fester
> Crop-Offset (**Smart static crop v1**, robust statt wacklig). Ohne erkanntes
> Gesicht (oder ohne OpenCV) → automatischer **Center-Fallback**, der Export
> bricht nie ab. Metriken pro Clip in `clips.json` unter `reframe_info`.

> **Untertitel:** `--caption-mode karaoke` hebt das aktuell gesprochene Wort
> wortgenau hervor (Default; nutzt die Wort-Timestamps, auch nach
> Silence-Removal über die re-gemappten Zeiten). Ohne Wort-Timestamps wird
> automatisch auf `standard` zurückgefallen (Warnung im Log, Job läuft weiter).
> `--caption-style`: `high_energy` (groß, GROSSBUCHSTABEN, grünes Wort, Default)
> oder `clean` (schlicht, gelbes Wort). Pro Clip werden die Caption-Metriken in
> `clips.json` unter `caption_info` gespeichert.

> **`--remove-silence`** entfernt erkannte Stille (Standard: `silencedetect`
> bei −30 dB, ≥ 0,6 s) synchron aus Video **und** Audio und passt die
> Untertitel-Timings entsprechend an. Standardmäßig werden harte Audio-Schnitte
> mit **sehr kurzen Fades (15 ms)** geglättet (gegen Klick-Geräusche), ohne die
> Gesamtdauer zu verändern — abschaltbar mit `--no-audio-smoothing`. Ohne den
> Flag bleibt das Verhalten unverändert. Findet die Pipeline keine sinnvollen
> Pausen oder schlägt der Schnitt fehl, wird automatisch normal gerendert
> (gestufter Fallback). Pro Clip werden die Schnitt-Metriken in `clips.json`
> unter `silence_info` gespeichert (Original-/Final-Dauer, entfernte Stille,
> Audio-Smoothing, Fallback).

Ergebnis im `--out`-Verzeichnis:
- `clip_01_score81.mp4 …` — fertige 9:16-Clips mit Untertiteln
- `clips.json` — Scores, Aufschlüsselung, Metadaten, Hook-Varianten
- `transcript.json` — das verwendete Transkript

---

## Selbst testen / verifizieren

```bash
cd api && export PYTHONPATH=$PWD

# 1) Schnelle Regressionstests (keine Modelle/Keys/ffmpeg nötig)
python tests/test_pipeline_core.py

# 2) End-to-End mit dem mitgelieferten Test-Transkript:
ffmpeg -y -f lavfi -i testsrc=size=1280x720:rate=25:duration=60 \
       -f lavfi -i sine=frequency=320:duration=60 \
       -c:v libx264 -pix_fmt yuv420p -c:a aac -shortest testdata/sample.mp4
python -m clipforge.cli testdata/sample.mp4 \
       --transcript testdata/transcript.json --out testdata/out --top 4
```

Danach liegen abspielbare 9:16-MP4s in `testdata/out/`.

---

## Konfiguration (ENV)

| Variable | Default | Zweck |
|---|---|---|
| `CLIPFORGE_WHISPER_MODEL` | `base` | Whisper-Modellgröße (`tiny`…`large-v3`) |
| `CLIPFORGE_TARGET_CLIP_SECONDS` | `30` | Ziel-Cliplänge |
| `CLIPFORGE_MIN_CLIP_SECONDS` / `_MAX_` | `15` / `60` | Längen-Grenzen |
| `CLIPFORGE_OUT_WIDTH` / `_HEIGHT` | `1080` / `1920` | Ausgabeauflösung (9:16) |
| `ANTHROPIC_API_KEY` | – | aktiviert Claude-Scoring + Metadaten |
| `CLIPFORGE_LLM_MODEL` | `claude-sonnet-4-6` | Modell für Scoring |
| `CLIPFORGE_USE_LLM` | `auto` | `off` erzwingt reine Heuristik |
