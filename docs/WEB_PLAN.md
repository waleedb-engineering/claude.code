# ClipForge AI — Vom CLI-MVP zur Web-App

> Analyse des Ist-Zustands, klare technische Entscheidung und ein konkreter
> 5-Schritte-Umsetzungsplan. **Ziel: bestehenden Pipeline-Kern unangetastet
> webfähig machen — kein neues Feature, kein Overengineering.**

---

## Teil A — Analyse des aktuellen Codebestands

### 1. Welche Kernfunktionen funktionieren wirklich? ✅

End-to-end verifiziert (siehe `README.md` → „Selbst testen"):

| Funktion | Ort | Beweis |
|---|---|---|
| Medienanalyse (ffprobe) | `ffmpeg_utils.probe()` | `MediaInfo(duration=60.0, 1280x720, audio)` |
| Lokale Transkription, Wort-Timestamps | `transcribe.transcribe_video()` | espeak-Audio → korrektes Transkript mit Word-Timings |
| Transkript-Loader (ohne Whisper) | `transcribe.load_transcript_json()` | Fixture `testdata/transcript.json` |
| Clip-Auswahl | `segmenter.build_candidates()` | 4 Segmente → 2 Kandidaten in Längen-Grenzen |
| Performance-Score (Heuristik) | `scoring.heuristic_score()` | Hook/Klarheit/Emotion/Tempo/Pointe, sortiert |
| 9:16-Export (Center-Crop) | `render.render_clip()` | MP4 1080×1920 mit Audio |
| Eingebrannte Untertitel | `captions.build_ass()` + render | Frame-Beweis „Warum scheitern die" |
| Orchestrierung + JSON-Output | `pipeline.run_pipeline()` | `clips.json` + `transcript.json` |
| CLI | `cli.main()` | voller Lauf grün |

### 2. Welche Funktionen sind nur Mock/TODO? ⚠️

**Wichtig — ehrlich gekennzeichnet, nichts ist gefaked:**

| Punkt | Realität | Konsequenz für Web |
|---|---|---|
| **Reframe** | Nur **Center-Crop**, kein Face-Tracking (`render.py`) | OK fürs MVP, bleibt so |
| **„Schnelle Schnitte"** | `ffmpeg_utils.detect_silences()` **existiert, ist aber nicht im Render-Pfad verdrahtet** | Funktion ungenutzt — nicht web-relevant jetzt |
| **Metadaten + Hook-Varianten** | Nur aktiv mit `ANTHROPIC_API_KEY`; ohne Key sind `metadata`/`hook_variants` **leer** (kein Fake) | Web muss leere Felder sauber handhaben |
| **A/B-Testing** | Nur Varianten-**Generierung**, keine Messung | Nicht im Web-Scope |
| **YouTube-URL-Import** | Nicht vorhanden | Nicht im Web-Scope |

→ **Für die Web-App ist nichts davon ein Blocker.** Wir mappen nur das, was real läuft.

### 3. Wo liegt der Pipeline-Kern?

`api/clipforge/` — **framework-frei** (kein FastAPI/Flask import). Reine
Python-Logik + dataclasses. Genau dieser Kern bleibt unverändert.

### 4. Wie läuft Video → Transkript → Auswahl → Score → Export?

Alles über **eine** Funktion: `pipeline.run_pipeline()`:

```
run_pipeline(video_path, output_dir, *, settings, transcript_path,
             top_n=5, render=True, progress=<callback>)
  1) transcribe_video()  ODER  load_transcript_json()   → Transcript
     └─ schreibt output_dir/transcript.json
  2) build_candidates(transcript)                        → list[CandidateClip]
  3) score_clips(candidates)                             → list[ScoredClip] (sortiert)
     └─ score_llm() wenn Key sonst score_heuristic()
  4) für Top-N: render_clip(video, clip, out.mp4)        → 9:16-MP4 + Untertitel
  5) schreibt output_dir/clips.json
  → return PipelineResult(transcript, clips, output_dir, rendered)
```

**Wichtig für Web:** Der Lauf ist **synchron & blockierend** und dauert
(Transkription + Rendering) Minuten. Es gibt bereits einen
**`progress: Callable[[str], None]`-Callback** — ideal, um später Job-Status zu
füttern, ohne den Kern zu ändern.

### 5. Welche CLI-Befehle existieren?

Genau ein Entry-Point:

```bash
python -m clipforge.cli <video> [--out DIR] [--transcript JSON.json]
                                [--top N] [--no-render]
```

- `video` (positional, Pflicht)
- `--out` (Default `./clipforge_out`)
- `--transcript` (vorhandenes Transkript statt Whisper)
- `--top` (Default 5)
- `--no-render` (nur analysieren/scoren)

### 6. Welche Dateien sind zentral?

| Datei | Rolle | Web-Relevanz |
|---|---|---|
| `pipeline.py` | **Orchestrator** — der eine Einstiegspunkt | FastAPI ruft genau das auf |
| `models.py` | Datenstrukturen (dataclasses) | Quelle der API-Response-Form |
| `scoring.py` | Kern-IP (Heuristik + LLM) | bleibt unberührt |
| `cli.py` | CLI-Adapter über `run_pipeline` | **Vorlage** für den FastAPI-Adapter |
| `config.py` | `Settings` via ENV | FastAPI nutzt dieselben Settings |
| `render.py` / `transcribe.py` / `segmenter.py` / `captions.py` / `ffmpeg_utils.py` | Bausteine | unberührt |

### 7. Welche Datenstruktur wird verwendet?

Reine `@dataclass`-Modelle in `models.py`:

```
Word(text, start, end)
TranscriptSegment(text, start, end, words[])
Transcript(language, duration, segments[])
CandidateClip(start, end, text, words[])
ScoreBreakdown(hook, clarity, emotion, pacing, payoff, weights{}) .total()
PlatformMetadata(title, description, hashtags[])
HookVariant(label, text)
ScoredClip(start, end, text, score, breakdown, reason, metadata{},
           hook_variants[], words[], scorer, output_path) .to_dict()
PipelineResult(transcript, clips[], output_dir, rendered[])
```

`ScoredClip.to_dict()` ist bereits JSON-fähig (lässt `words` weg, ergänzt
`duration`). **Das ist die fertige Web-Response-Form** — keine neue DTO-Schicht
nötig.

`clips.json` (Ist-Format):
```json
{ "source": "...", "scorer": "Heuristik", "disclaimer": "...",
  "clips": [ { "start", "end", "duration", "text", "score",
               "breakdown", "reason", "metadata", "hook_variants",
               "scorer", "output_path" } ] }
```

### 8. Was fehlt für eine Web-App?

Nur **Infrastruktur um den Kern herum**, keine neue Produktlogik:

1. **HTTP-Layer** — es gibt keinen Server (nur CLI).
2. **Datei-Upload** — Kern erwartet einen lokalen Pfad; Web braucht Upload→Pfad.
3. **Asynchroner Job** — `run_pipeline` blockiert minutenlang; ein HTTP-Request
   darf nicht so lange hängen → Hintergrund-Ausführung + Job-ID.
4. **Status/Progress nach außen** — der `progress`-Callback schreibt heute nur
   nach stdout; Web braucht abrufbaren Status.
5. **Job-Registry** — `job_id → {state, progress[], result}`.
6. **Download/Serving** der erzeugten MP4s.
7. **CORS** für die Next.js-Herkunft.
8. **Frontend** — `web/` existiert noch nicht.

### 9. FastAPI zuerst oder direkt Next.js?

**Entscheidung: FastAPI zuerst.** Begründung (streng):

- Der Kern ist **Python** und **langlaufend/synchron**. Next.js (Node) könnte
  ihn nur ansprechen, indem es entweder die Logik **nachbaut** (verstößt gegen
  „keine doppelte Logik") oder pro Request einen Python-Prozess **shellt** (kein
  Job-/Status-Konzept, fragil).
- Ein dünner FastAPI-Layer ist der **einzige** Weg, den vorhandenen
  `run_pipeline` 1:1 und ohne Duplizierung übers Web verfügbar zu machen.
- Next.js wird dann ein **reiner Client** — exakt die gewünschte Zielarchitektur.

### 10. Minimale Web-Architektur (schnellster Weg zur nutzbaren App)

```
┌─────────────┐   HTTP/JSON    ┌──────────────────┐   Funktionsaufruf   ┌────────────────┐
│  Next.js UI │ ─────────────► │  FastAPI (dünn)  │ ──────────────────► │ clipforge.*    │
│  (web/)     │ ◄───────────── │  (api/app.py)    │ ◄────────────────── │ run_pipeline() │
└─────────────┘   Status/MP4   └──────────────────┘   PipelineResult    └────────────────┘
                                       │
                                 In-Memory Job-Registry (dict)
                                 + lokaler jobs/<id>/-Ordner
```

**Bewusst minimal (kein Overengineering):**
- **Job-Verarbeitung:** FastAPI `BackgroundTasks` / ein Worker-Thread.
  **Kein** Celery/Redis/Queue.
- **Job-Speicher:** ein `dict` im Prozess + Dateien unter `jobs/<id>/`.
  **Keine** DB.
- **Response-Form:** direkt aus `ScoredClip.to_dict()`. **Keine** neue DTO-Ebene.
- **Storage:** lokales Filesystem. **Keine** Cloud, **kein** S3.
- **Auth:** keine. **Kein** Account/Billing.

---

## Teil B — Entscheidung (final)

> **Wir bauen einen dünnen FastAPI-Layer (`api/app.py`), der ausschließlich
> `clipforge.pipeline.run_pipeline` aufruft, plus eine reine Next.js-Client-UI
> (`web/`). Der Pipeline-Kern in `api/clipforge/` bleibt unverändert. Keine
> doppelte Logik, kein neuer Persistenz-/Queue-Stack, keine neuen Produkt-
> Features.**

Zielarchitektur (deckungsgleich mit deiner Vorgabe):
- Python-Kern bleibt → ✅
- FastAPI als dünner Backend-Layer → ✅
- Next.js als Web-UI → ✅
- UI ruft nur FastAPI → ✅
- FastAPI ruft nur den Kern → ✅
- Keine doppelte Logik / keine neue Architektur → ✅

---

## Teil C — Umsetzungsplan (max. 5 Schritte)

> Jeder Schritt ist einzeln lauffähig und endet mit einem konkreten Test.
> Der Kern (`api/clipforge/`) wird in **keinem** Schritt verändert.

### Schritt 1 — FastAPI-Bridge
**Ziel:** HTTP-Hülle um `run_pipeline`, ohne Upload/UI.
- Neu: `api/app.py` (FastAPI-App), `api/jobs.py` (In-Memory-Registry + Worker-Thread),
  `api/requirements.txt` ergänzt (fastapi, uvicorn, python-multipart sind schon drin).
- Job-Modell: `{ id, state: queued|running|done|error, progress[], result, error }`.
  Der `progress`-Callback von `run_pipeline` schreibt in `job.progress`.
- Endpoints: `GET /api/health`, `POST /api/jobs` (vorerst Pfad/Testfile),
  `GET /api/jobs/{id}`.
- **Test:** `uvicorn app:app` starten, Job auf `testdata/sample.mp4` +
  `testdata/transcript.json` anstoßen, `GET /api/jobs/{id}` zeigt `done` + Clips.

### Schritt 2 — Upload über Web
**Ziel:** Echtes Video per HTTP hochladen.
- `POST /api/jobs` nimmt `multipart/form-data` (Videodatei + optional `top_n`),
  speichert nach `jobs/<id>/input.<ext>`, startet den Job darauf.
- **Test:** `curl -F file=@testdata/sample.mp4 .../api/jobs` → `job_id`;
  Datei liegt unter `jobs/<id>/`.

### Schritt 3 — Analyse starten & Status anzeigen
**Ziel:** Web-UI-Grundgerüst, das einen Job startet und Status pollt.
- Neu: `web/` (Next.js + TS + Tailwind, minimal). Eine Seite: Datei wählen →
  Upload → Poll `GET /api/jobs/{id}` alle ~2 s → Fortschritts-Log + Spinner.
- **Test:** Im Browser Video wählen, Live-Progress sehen, Endzustand `done`.

### Schritt 4 — Clip-Vorschläge anzeigen
**Ziel:** Ergebnis darstellen.
- UI rendert pro Clip eine Karte: Score, Aufschlüsselung (Hook/Klarheit/…),
  Begründung, Zeitbereich, Text; sortiert nach Score. Disclaimer sichtbar.
- Daten kommen unverändert aus `job.result` (= `ScoredClip.to_dict()`).
- **Test:** Nach `done` erscheinen die Clip-Karten mit echten Scores.

### Schritt 5 — Export + Download über Web
**Ziel:** Fertige MP4s aus dem Browser laden.
- `GET /api/jobs/{id}/clips/{n}` streamt die gerenderte MP4 (FileResponse);
  optional `GET /api/jobs/{id}/clips.json`.
- UI: pro Karte „Download"-Button + `<video>`-Vorschau.
- **Test:** Clip im Browser abspielen und herunterladen; Datei ist die echte
  9:16-MP4 mit Untertiteln.

---

## Nicht-Ziele dieses Vorhabens (Sperrzone)

❌ Accounts · ❌ Billing · ❌ Cloud/S3 · ❌ Face-Tracking · ❌ Direkt-Posten ·
❌ A/B-Messung · ❌ Queue/DB-Stack · ❌ neue Produkt-Features · ❌ SaaS-Beiwerk.

## Akzeptanzkriterium dieses Schritts (Doku/Plan)
✅ Es ist exakt dokumentiert, **wie** der bestehende CLI-MVP zur Web-App wird —
über einen dünnen FastAPI-Adapter auf `run_pipeline` und eine reine Next.js-UI —
**ohne den funktionierenden Kern zu verändern.**
