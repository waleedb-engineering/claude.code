# ClipForge AI

KI-gestütztes Tool, das aus **langen Videos automatisch starke Kurzclips** für
TikTok, Instagram Reels und YouTube Shorts erzeugt.

📄 **Produktdefinition:** [`docs/PRODUCT.md`](docs/PRODUCT.md) — Problem, Lösung,
MVP-Scope, Architektur, Risiken und Akzeptanzkriterien.
🌐 **Web-Plan:** [`docs/WEB_PLAN.md`](docs/WEB_PLAN.md) · **HTTP-API:**
[`docs/API.md`](docs/API.md) — FastAPI-Bridge über dem Pipeline-Kern.

> **Ehrlicher Hinweis:** ClipForge garantiert **keine** Viralität. Es
> **maximiert die Wahrscheinlichkeit** für starke Performance durch messbare
> Signale: Hook-Erkennung, Retention-Optimierung, automatische Clip-Auswahl,
> Untertitel, schnelle Schnitte, einen transparenten **Performance-Potential-
> Score**, Plattform-Metadaten und Varianten-Testing.

---

## Status

| Stufe | Inhalt | Status |
|---|---|---|
| **Schritt 1–2 (dieser Stand)** | Lauffähiger **Pipeline-Kern als CLI** | ✅ fertig & verifiziert |
| Schritt 3 | FastAPI-Layer (Upload, Job-Status, Download) | ⏳ geplant |
| Schritt 4 | Next.js + Tailwind Frontend | ⏳ geplant |
| Schritt 5 | Face-Tracking-Reframe, echtes A/B-Tracking, Direkt-Posten | 🔭 später |

### Was schon echt funktioniert
- **Transkription** lokal via `faster-whisper` (Wort-Level-Timestamps) — verifiziert
- **Clip-Auswahl** aus dem Transkript (erklärbarer Segmenter)
- **Performance-Potential-Score** als transparente Heuristik (Hook, Klarheit,
  Emotion, Tempo, Pointe) — **optional** durch Claude verstärkt
- **Rendering** zu 9:16-MP4 mit **eingebrannten Untertiteln** (FFmpeg) — verifiziert
- **Plattform-Metadaten** (Titel/Beschreibung/Hashtags) + **Hook-Varianten**
  (nur mit gesetztem `ANTHROPIC_API_KEY`)

### Klar als TODO gekennzeichnet (noch nicht echt)
- Reframe = **Center-Crop** (kein Speaker/Face-Tracking) — `render.py`
- „Schnelle Schnitte" (Stille-Erkennung) ist implementiert (`detect_silences`),
  aber im Render-Pfad noch nicht angewandt — `render.py` TODO
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
```

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
