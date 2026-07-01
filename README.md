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
| Schritt 6–9 | **Karaoke-Captions · Smart-Reframe · Audio-Smoothing** | ✅ fertig & verifiziert |
| Schritt 10 | **Content-Package-Generator** (TikTok / Reels / Shorts-Texte) | ✅ fertig & verifiziert |
| Schritt 11 | **Web-Clip-Editor** (Start/Ende feinjustieren + Re-Render) | ✅ fertig & verifiziert |
| Schritt 12 | **Export-Management** (all-exports.zip + Manual-Übersicht) | ✅ fertig & verifiziert |
| Schritt 13 | **Persistente Job-Registry** (Restore nach Server-Neustart) | ✅ fertig & verifiziert |
| Schritt 14 | **Cleanup** (Jobs & manuelle Exporte sicher löschen) | ✅ fertig & verifiziert |
| Schritt 15 | **Storage-Übersicht & Bulk-Cleanup** | ✅ fertig & verifiziert |
| Schritt 16 | **Batch-Upload & Queue-Ansicht** | ✅ fertig & verifiziert |
| Schritt 17 | **Job abbrechen (kooperativ) & Upload-Limits** | ✅ fertig & verifiziert |
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
- **Content-Package-Generator**: für jeden exportierten Clip werden automatisch
  publizierfertige Texte erzeugt — Primary Hook, 5 Hook-Varianten, YouTube-Shorts-
  Titel/-Beschreibung, TikTok- & Instagram-Reels-Caption + Hashtags + Pinned Comment,
  Platform-Empfehlung, 3 A/B/C-Varianten. **Funktioniert ohne API-Key** (regelbasiert,
  DE+EN) — mit gesetztem `ANTHROPIC_API_KEY` optional durch Claude verbessert.
  - ZIP enthält zusätzlich `content_packages.json` mit allen Texten je Clip
  - Frontend: aufklappbares „📦 Content-Paket"-Panel mit Copy-Buttons pro Text
- **Web-Clip-Editor**: jeder vorgeschlagene Clip lässt sich in der Web-App öffnen
  („Bearbeiten"), **Start/Ende feinjustieren**, Caption-Style / Silence-Removal /
  Reframe-Modus / Titel wählen und als **neuer, separater Export** neu rendern —
  der ursprüngliche Auto-Clip bleibt unangetastet. Manuelle Exporte landen unter
  `jobs/<id>/manual_exports/` und sind einzeln als Vorschau/Download verfügbar.
- **Export-Management**: die Job-Seite zeigt **Auto-Clips / Manuelle Exporte /
  Gesamt-Exporte** und bietet zwei Downloads:
  - **`exports.zip`** (unverändert) — **nur Auto-Clips**, flach.
  - **`all-exports.zip`** (neu) — **vollständiges Paket** mit sauberer Struktur
    `auto_clips/` + `manual_exports/` + `data/` (clips.json, transcript.json,
    content_packages.json, `manual_exports.json`, metadata.json).
  Ein Bereich **„Manuelle Exporte"** listet alle Re-Renders clip-übergreifend
  mit Vorschau, Download und Link zurück zum Editor.
- **Persistente Job-Registry**: Jobs liegen lokal unter `api/jobs/<id>/` und
  werden beim FastAPI-Start **automatisch wiederhergestellt** — nach einem
  Neustart sind Jobliste, Clips, Previews/Downloads, manuelle Exporte und beide
  ZIPs sofort wieder nutzbar, **ohne erneute Analyse**. Zustände: `queued`,
  `processing`, `completed`, `failed` sowie (nach Restore) `interrupted` (war
  beim Neustart aktiv) und `incomplete` (Ergebnis-Dateien fehlen). Restored Jobs
  sind in der UI als „aus lokalem Speicher wiederhergestellt" markiert; kaputte
  Job-Ordner werden übersprungen und crashen das Backend nicht. **Keine
  automatische Wiederaufnahme** laufender Renders — bewusst.
- **Cleanup / sicheres Löschen**: Jobs und einzelne manuelle Exporte lassen sich
  über die Web-App entfernen (`DELETE /api/jobs/{id}` bzw.
  `DELETE /api/jobs/{id}/manual-exports/{export_id}`). Job löschen entfernt den
  **kompletten** Ordner `jobs/<id>/` (Auto-Clips, manuelle Exporte, JSONs);
  einen manuellen Export löschen entfernt nur dessen MP4 + Sidecar-JSON und lässt
  **Auto-Clips unberührt**. Sicherheit: strenge `job_id`/`export_id`-Validierung
  und realpath-Prüfung — es wird **nie** außerhalb von `jobs/` gelöscht; ein
  laufender `processing`-Job ist geschützt (`409`, außer `?force=true`). Jede
  Löschung verlangt in der UI eine Inline-Bestätigung.
- **Storage-Übersicht & Bulk-Cleanup**: `GET /api/storage` zeigt lokalen
  Speicherverbrauch, Status-Verteilung, Auto-/Manual-Export-Counts, die größten
  Jobs und Cleanup-Kandidaten. Die `/jobs`-Seite zeigt das als kompaktes Widget
  plus **„Problematische Jobs aufräumen"** — löscht per `POST /api/jobs/bulk-delete`
  (`confirm:"DELETE"`) gesammelt nur `failed`/`interrupted`/`incomplete`-Jobs.
  **`completed`-Jobs werden nie automatisch gelöscht**, `processing` ist
  geschützt. Bulk-Delete nutzt dieselbe sichere `delete()`-Logik wie
  Einzel-Delete (Traversal-Schutz, `jobs/`-Containment); Teil-Fehler werden je
  Job berichtet.
- **Batch-Upload & Queue**: mehrere Videos gleichzeitig hochladen
  (`POST /api/jobs/batch`) — jede Datei wird ein eigener Job, eine ungültige
  Datei blockiert die anderen nicht (per-Datei-Ergebnis: `accepted`/`job_id`/
  `error`). Die `/upload`-Seite unterstützt Mehrfachauswahl + Drag-and-drop mit
  Statusliste je Datei; `/jobs` zeigt eine **Queue-Summary** (verarbeitet gerade
  / wartet / fertig / fehlgeschlagen) und aktualisiert sich automatisch.
  Parallelität via `ThreadPoolExecutor`, konfigurierbar über
  **`CLIPFORGE_MAX_WORKERS`** (Default 2, `=1` für strikt seriell). Einzel-Upload
  (`POST /api/jobs`, inkl. Transkript) bleibt unverändert.
- **Job abbrechen (kooperativ)**: `POST /api/jobs/{id}/cancel` bricht einen
  `queued`/`processing`-Job ab → Status `canceled`. **Ehrlich kooperativ, kein
  harter Prozess-Kill**: ein `queued`-Job wird sofort abgebrochen; ein laufender
  `processing`-Job setzt ein Cancel-Flag und stoppt am **nächsten sicheren
  Checkpoint** (vor/nach Transkription, vor/nach jedem Clip-Render) — ein bereits
  laufender FFmpeg-Schritt läuft noch zu Ende, damit keine Datei beschädigt wird.
  Bereits fertige MP4s bleiben liegen; `canceled`-Jobs werden restored und sind
  löschbar. Endzustände → `409`, unbekannt → `404`.
- **Upload-Limits**: `CLIPFORGE_MAX_UPLOAD_MB` (Default 500) und
  `CLIPFORGE_MAX_BATCH_FILES` (Default 10). Einzel-Upload zu groß → `413`; Batch
  mit zu vielen Dateien → `400`; eine zu große Datei im Batch wird **einzeln**
  abgelehnt, gültige laufen weiter. `GET /api/config` liefert die Limits ans
  Frontend (keine doppelte Pflege).

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
    content.py       # Content-Package-Generator (regelbasiert + optional Claude)
    captions.py      # Wort-Timestamps -> ASS-Untertitel
    render.py        # ffmpeg: 9:16-Crop + Untertitel einbrennen
    rerender.py      # manuelles Re-Rendering einzelner Clips (Web-Editor)
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
- `clips.json` — Scores, Aufschlüsselung, Metriken + `content_package` je Clip
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
| `ANTHROPIC_API_KEY` | – | aktiviert Claude-Scoring + Content-Paket-Verbesserung (optional) |
| `CLIPFORGE_LLM_MODEL` | `claude-sonnet-4-6` | Modell für Scoring + Content-Pakete |
| `CLIPFORGE_USE_LLM` | `auto` | `off` erzwingt reine Heuristik + regelbasierte Pakete |
| `CLIPFORGE_MAX_WORKERS` | `2` | Parallel verarbeitete Jobs (`1` = strikt seriell, stabilster Modus) |
| `CLIPFORGE_MAX_UPLOAD_MB` | `500` | Maximale Dateigröße pro Upload |
| `CLIPFORGE_MAX_BATCH_FILES` | `10` | Maximale Dateien pro Batch-Upload |
| `CLIPFORGE_JOBS_DIR` | `api/jobs` | Speicherort der Job-Ordner |
