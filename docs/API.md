# ClipForge AI — HTTP-API (FastAPI-Bridge)

Dünner HTTP-Layer über dem bestehenden Pipeline-Kern
(`clipforge.pipeline.run_pipeline`). **Keine** eigene Analyse-/Render-Logik,
keine Datenbank, kein Redis/Celery, kein Auth. Jeder Job liegt als Ordner unter
`api/jobs/<job_id>/`.

> Der Performance-Potential-Score ist eine Wahrscheinlichkeits-Einschätzung,
> **keine** Viralitäts-Garantie.

---

## Start

```bash
cd api
export PYTHONPATH=$PWD          # damit `import clipforge` gefunden wird
pip install -r requirements.txt # fastapi, uvicorn, python-multipart u.a.

uvicorn app:app --reload --port 8000
# alternativ vom Repo-Root:
#   uvicorn api.app:app --reload --port 8000
```

Standard-Job-Verzeichnis: `api/jobs/` (überschreibbar via `CLIPFORGE_JOBS_DIR`).
Mit gesetztem `ANTHROPIC_API_KEY` liefert die Pipeline zusätzlich Metadaten +
Hook-Varianten; ohne Key läuft reine Heuristik.

---

## Job-Status

| Status | Bedeutung |
|---|---|
| `queued` | Job angelegt, Datei gespeichert, noch nicht gestartet |
| `processing` | Pipeline läuft im Hintergrund (Transkription/Scoring/Render) |
| `completed` | Fertig — Ergebnis & Dateien verfügbar |
| `failed` | Abgebrochen — `error` enthält die Ursache |
| `interrupted` | War beim Server-Neustart aktiv (`processing`/`queued`) und wurde **nicht** fortgesetzt |
| `incomplete` | Nach Restore: Ergebnis-Dateien (clips.json / MP4s) fehlen |
| `canceled` | Vom Nutzer kooperativ abgebrochen (`POST …/cancel`) |

### Persistenz & Wiederherstellung (Restore)

Jobs werden lokal unter `jobs/<id>/` gespeichert (`job.json` + Dateien). Beim
**Start** des Backends scannt die Registry `jobs/` und lädt vorhandene Jobs
zurück (`job.json` als primäre Quelle; fehlt/defekt → Rekonstruktion aus
`clips.json` + `clip_*.mp4` + `transcript.json`). Robust: kaputte Ordner werden
übersprungen (kein Crash), Warnungen werden beim Start geloggt.

- Ein `processing`/`queued`-Job wird nach Neustart zu `interrupted` — **außer**
  die Ergebnis-Dateien sind bereits vollständig, dann `completed`.
- Ein `completed`-Job ohne MP4s/`clips.json` wird zu `incomplete`.
- Es wird **niemals** automatisch ein Job neu gestartet oder fortgesetzt.

Restore-Felder in `GET /api/jobs/{id}` und `GET /api/jobs` (Summary):
`restored` (bool), `restored_at`, `interrupted` (bool), `restore_warning`.
`files` enthält zusätzlich `input_file_exists`, `transcript_exists`,
`clips_json_exists` (für die Frage, ob ein Re-Render möglich ist).

**Grenzen:** keine Cloud-Persistenz, keine Nutzeraccounts, keine automatische
Wiederaufnahme laufender Renders nach Crash.

---

## Endpoints

| Methode | Pfad | Zweck |
|---|---|---|
| `GET` | `/health` | Backend- & FFmpeg-Status |
| `POST` | `/api/jobs` | **Ein** Video hochladen, Job starten → `job_id` (inkl. optionalem Transkript) |
| `POST` | `/api/jobs/batch` | **Mehrere** Videos hochladen → je Datei ein Job (per-Datei-Ergebnis) |
| `GET` | `/api/jobs` | Alle Jobs (Kurzstatus) |
| `GET` | `/api/jobs/{job_id}` | Voller Status: Progress, Logs, Fehler, Ergebnis, `files`-Übersicht |
| `POST` | `/api/jobs/{job_id}/cancel` | Job kooperativ abbrechen → `canceled` |
| `DELETE` | `/api/jobs/{job_id}` | Job-Ordner löschen (`?force=true` bei `processing`) |
| `POST` | `/api/jobs/bulk-delete` | Mehrere Jobs gesammelt löschen (`confirm:"DELETE"`) |
| `GET` | `/api/storage` | Lokale Speicher-Übersicht + Cleanup-Kandidaten |
| `GET` | `/api/config` | Frontend-Limits (Upload-MB, Batch-Dateien, Worker, Typen) |
| `GET` | `/api/caption-styles` | Verfügbare Caption-Styles (5) mit Beschreibung |
| `GET` | `/api/brand-kit` | Aktuelles Brand Kit (oder Defaults) |
| `POST` | `/api/brand-kit` | Brand Kit validieren + lokal speichern |
| `DELETE` | `/api/jobs/{job_id}/manual-exports/{export_id}` | Einen manuellen Export löschen (MP4 + Sidecar-JSON) |
| `GET` | `/api/jobs/{job_id}/transcript` | `transcript.json` (falls vorhanden) |
| `GET` | `/api/jobs/{job_id}/clips` | `clips.json` (falls vorhanden) |
| `GET` | `/api/jobs/{job_id}/clips/{clip_index}/download` | Gerenderten Clip als MP4 (Attachment, 1-basiert) |
| `GET` | `/api/jobs/{job_id}/clips/{clip_index}/preview` | Clip inline streamen (video/mp4, Range/206 → Seeking) |
| `POST` | `/api/jobs/{job_id}/clips/{clip_index}/rerender` | Clip mit manuellen Optionen neu rendern (Web-Clip-Editor) |
| `GET` | `/api/jobs/{job_id}/manual-exports` | Alle manuellen Exporte eines Jobs |
| `GET` | `/api/jobs/{job_id}/manual-exports/{export_id}/preview` | Manuellen Export inline streamen |
| `GET` | `/api/jobs/{job_id}/manual-exports/{export_id}/download` | Manuellen Export als MP4 (Attachment) |
| `GET` | `/api/jobs/{job_id}/exports.zip` | **Nur Auto**-Clips (flach) + clips.json/transcript.json/metadata.json/content_packages.json als ZIP |
| `GET` | `/api/jobs/{job_id}/all-exports.zip` | **Vollständiges Paket**: Auto-Clips + manuelle Exporte + alle JSONs (Ordnerstruktur) |
| `GET` | `/api/jobs/{job_id}/files` | Alle Dateien im Job-Ordner |

### `files`-Übersicht in `GET /api/jobs/{job_id}`

```json
"files": {
  "clip_count": 2,            // erkannte/bewertete Clips
  "mp4_count": 2,             // Auto-MP4-Exporte (== auto_export_count)
  "input_file_exists": true,  // input.* vorhanden (Re-Render möglich?)
  "transcript_exists": true,  // transcript.json vorhanden
  "clips_json_exists": true,  // clips.json vorhanden
  "has_transcript": true,     // Alias (rückwärtskompatibel)
  "has_clips_json": true,     // Alias (rückwärtskompatibel)
  "exports_ready": true,      // auto_export_count > 0 (exports.zip verfügbar)
  "auto_export_count": 2,     // automatische Clips im Job-Root
  "manual_export_count": 1,   // manuelle Re-Renders (manual_exports/)
  "total_export_count": 3,    // Auto + manuell
  "has_manual_exports": true, // manual_export_count > 0
  "all_exports_ready": true   // total_export_count > 0 (all-exports.zip verfügbar)
}
```

### `preview` vs. `download`

- **preview**: ohne `Content-Disposition: attachment` → Browser spielt inline
  ab; unterstützt `Range`-Requests (HTTP 206) fürs Seeken in `<video>`.
- **download**: mit `attachment; filename=…` → erzwingt Speichern.

### `exports.zip` vs. `all-exports.zip`

Zwei getrennte Endpoints — **`exports.zip` bleibt bewusst unverändert** (nur
Auto-Clips, flache Struktur; Rückwärtskompatibilität). `all-exports.zip` ist das
neue vollständige Paket inkl. manueller Re-Renders und geordneter Ordner.

| | `exports.zip` | `all-exports.zip` |
|---|---|---|
| Auto-Clips | ✅ (flach im Root) | ✅ (`auto_clips/`) |
| Manuelle Exporte | ❌ | ✅ (`manual_exports/`) |
| JSON-Dateien | im Root | in `data/` |
| `manual_exports.json` | ❌ | ✅ |
| Struktur | flach | `auto_clips/ manual_exports/ data/` |

### `exports.zip`

Enthält alle vorhandenen `clip_*.mp4`, dazu — falls vorhanden — `clips.json`,
`transcript.json`, immer eine generierte `metadata.json` und (sofern Clips
analysiert wurden) `content_packages.json`:

```json
// metadata.json
{
  "job_id": "…", "source_filename": "…",
  "export_created_at": "…", "exported_at": "…",
  "clip_count": 2, "mp4_count": 2, "scorer": "Heuristik",
  "remove_silence": true,
  "audio_smoothing": true,
  "total_removed_silence_seconds": 5.4,
  "content_generator": "Regelbasiert",
  "content_fallback_count": 0,
  "disclaimer": "… keine Garantie für Reichweite oder Viralität."
}
```

```json
// content_packages.json — publizierfertige Texte je Clip
{
  "job_id": "…",
  "export_created_at": "…",
  "clips": [
    {
      "clip_index": 1,
      "title": "Warum scheitern die meisten Leute?",
      "transcript_excerpt": "…",
      "content_package": { /* siehe unten */ }
    }
  ]
}
```

Ohne gerenderte Clips → `404`.

### `all-exports.zip`

Vollständiges Paket eines Jobs. Ordnerstruktur:

```
auto_clips/
  clip_01_score81.mp4
  clip_02_score74.mp4
manual_exports/
  clip_1_20260701T040956Z.mp4
data/
  clips.json
  transcript.json
  content_packages.json
  manual_exports.json
  metadata.json
```

`data/metadata.json` (Counts + Kontext):

```json
{
  "job_id": "…", "source_filename": "…", "export_created_at": "…",
  "auto_clip_count": 2, "manual_export_count": 1, "total_mp4_count": 3,
  "remove_silence": true, "reframe_mode": "smart",
  "content_generator": "Regelbasiert",
  "warnings": [],
  "disclaimer": "Der Performance-Potential-Score … keine Garantie …"
}
```

`data/manual_exports.json` (alle manuellen Exporte mit Metadaten —
`source_clip_index`, `start_time`, `end_time`, `final_duration`, `title`,
`caption_style`, `remove_silence`, `reframe_mode`, `output_file`, …):

```json
{ "job_id": "…", "export_created_at": "…", "exports": [ { … }, … ] }
```

Fehler-/Robustheitsverhalten:
- Job nicht gefunden → `404`.
- Weder Auto-Clips noch manuelle Exporte → `404` („Keine Exporte vorhanden …").
- **Kaputte** manuelle Metadatei → übersprungen, Eintrag in `metadata.json`
  unter `warnings` (kein Crash).
- **Fehlende MP4** zu einer Metadatei → übersprungen + `warnings`-Eintrag.

### Schnitt-Metriken in `clips.json`

Top-Level: `remove_silence`, `audio_smoothing`, `total_removed_silence_seconds`,
`caption_mode`, `caption_style`, `caption_fallback_count`.
Pro Clip (`clips[i].silence_info`):

```json
"silence_info": {
  "remove_silence": true, "n_silences": 3, "removed_seconds": 5.4,
  "original_duration": 18.0, "final_duration": 12.6,
  "applied": true, "audio_smoothing": true, "fallback": false
}
```

Caption-Metriken pro Clip (`clips[i].caption_info`):

```json
"caption_info": {
  "requested_mode": "karaoke", "applied_mode": "karaoke",
  "caption_style": "high_energy", "word_level_available": true,
  "fallback": false, "fallback_reason": null, "caption_blocks_count": 7
}
```

Reframe-Metriken pro Clip (`clips[i].reframe_info`):

```json
"reframe_info": {
  "requested_mode": "smart", "applied_mode": "smart",
  "fallback": false, "fallback_reason": null,
  "detection_method": "opencv_haar_frontalface",
  "frames_analyzed": 26, "faces_detected_count": 26,
  "focus_x": 0.2766, "crop_x": 404,
  "crop_strategy": "static_smart", "smoothing_applied": true
}
```

Die ZIP-`metadata.json` enthält zusätzlich `caption_mode`, `caption_style`,
`caption_fallback_count`, `reframe_mode`, `reframe_fallback_count`,
`reframe_note` (Hinweis: Reframe läuft lokal, ohne Cloud), `content_generator`
(`"Regelbasiert"` oder `"Claude"`) und `content_fallback_count`.

### Content-Package pro Clip in `clips.json`

Jeder Clip enthält ein `content_package`-Feld mit publizierfertigem Text:

```json
"content_package": {
  "primary_hook": "…",
  "hook_variants": {
    "provokant": "…", "neugierig": "…", "emotional": "…",
    "edukativ": "…", "direkt": "…"
  },
  "youtube_shorts": {
    "title": "…", "description": "…", "hashtags": ["#shorts", "…"]
  },
  "tiktok": {
    "caption": "…", "hashtags": ["…"], "pinned_comment": "…"
  },
  "instagram_reels": {
    "caption": "…", "hashtags": ["…"], "pinned_comment": "…"
  },
  "platform_recommendation": {
    "best_platform": "TikTok", "reason": "…"
  },
  "variant_a": { "name": "Aggressiver Hook", "hook": "…", "caption": "…", "hashtags": ["…"] },
  "variant_b": { "name": "Emotional", "hook": "…", "caption": "…", "hashtags": ["…"] },
  "variant_c": { "name": "Edukativ", "hook": "…", "caption": "…", "hashtags": ["…"] },
  "safety_note": {
    "virality_guarantee": "Kein Clip garantiert Viralität …",
    "score_disclaimer": "Der Score ist eine Einschätzung …"
  }
}
```

`content_package` ist immer vorhanden (ab Pipeline-Version 10), auch ohne
`ANTHROPIC_API_KEY` — dann regelbasiert generiert (`content_generator =
"Regelbasiert"`). Ältere Jobs-Ordner ohne dieses Feld liefern `null`.

### `POST /api/jobs` — Felder (multipart/form-data)

| Feld | Typ | Pflicht | Default | Beschreibung |
|---|---|---|---|---|
| `file` | Datei | ja | – | Video (`.mp4 .mov .mkv .webm .avi .m4v`) |
| `top_n` | int | nein | `5` | Anzahl der Top-Clips |
| `remove_silence` | bool | nein | `true` | Stille Pausen automatisch entfernen (schnellere, dichtere Clips) |
| `caption_mode` | string | nein | `karaoke` | `karaoke` (wortgenaue Hervorhebung) oder `standard` |
| `caption_style` | string | nein | `high_energy` | `high_energy` oder `clean` |
| `reframe_mode` | string | nein | `smart` | `smart`/`face` (auf Gesicht ausrichten) oder `center` |
| `advanced_analysis` | bool | nein | `true` | Analyzer v2 (bessere Auswahl + Score); `false` = Legacy v1 |
| `transcript` | Datei | nein | – | Vorhandenes Transkript-JSON; überspringt Whisper (spiegelt CLI-Flag `--transcript`, ideal für schnelle Tests) |

Der gewählte `remove_silence`-Wert ist im Job-Status sichtbar (Feld
`remove_silence`) und im `progress`-Log (erkannte Stellen, entfernte Dauer,
ggf. Fallback). Werden keine sinnvollen Pausen gefunden, wird normal gerendert.

### `POST /api/jobs/batch` — Mehrere Videos (multipart/form-data)

Für **jede** Datei wird ein eigener Job angelegt (Speicherung wie beim
Einzel-Upload unter `jobs/<id>/` → Restore/Delete/Storage/Bulk-Cleanup
funktionieren identisch). Der Batch nutzt **kein** Transkript.

| Feld | Typ | Pflicht | Default | Beschreibung |
|---|---|---|---|---|
| `files` | Datei[] | ja | – | Mehrere Videos (gleiche erlaubten Endungen) |
| `top_n` | int | nein | `5` | Top-Clips je Video |
| `remove_silence` | bool | nein | `true` | Stille entfernen |
| `caption_mode` | string | nein | `karaoke` | `karaoke` / `standard` |
| `caption_style` | string | nein | `high_energy` | `high_energy` / `clean` |
| `reframe_mode` | string | nein | `smart` | `smart` / `face` / `center` |
| `advanced_analysis` | bool | nein | `true` | Analyzer v2 (bessere Auswahl + Score); `false` = Legacy v1 |

**Robust:** eine ungültige/fehlerhafte Datei bricht den Batch **nicht** ab —
jede Datei bekommt ein eigenes Ergebnis. `files` leer → `400`.

**Upload-Limits** (`GET /api/config` liefert die Werte):
- Zu **viele** Dateien (> `CLIPFORGE_MAX_BATCH_FILES`, Default 10) → **`400`**
  (ganze Anfrage abgelehnt).
- Eine zu **große** Datei (> `CLIPFORGE_MAX_UPLOAD_MB`, Default 500) → nur **diese**
  Datei wird abgelehnt (`accepted:false`, `error`), gültige laufen weiter.
- Einzel-Upload (`POST /api/jobs`) zu groß → **`413`** (Payload Too Large).

```json
// 200
{
  "accepted_count": 2, "rejected_count": 1,
  "results": [
    { "filename": "a.mp4", "accepted": true,  "job_id": "…",  "error": null },
    { "filename": "b.mov", "accepted": true,  "job_id": "…",  "error": null },
    { "filename": "bad.txt", "accepted": false, "job_id": null,
      "error": "Ungültiger Dateityp '.txt'. Erlaubt: …" }
  ]
}
```

**Einzel- vs. Batch-Upload:** `POST /api/jobs` bleibt der einfache Einzel-Weg
(inkl. optionalem Transkript, deterministisch). `POST /api/jobs/batch` ist für
mehrere Dateien und meldet pro Datei Erfolg/Fehler. Beide legen identische
Job-Ordner an.

### Queue-/Status-Anzeige

Es gibt **keinen** eigenen `/api/queue`-Endpoint — die Queue-Summary ist aus
vorhandenen Daten ableitbar: `GET /api/jobs` liefert je Job `status`, und
`GET /api/storage` liefert `by_status` (queued/processing/completed/failed/
interrupted/incomplete). Das Frontend berechnet daraus „verarbeitet gerade /
wartet / fertig / fehlgeschlagen".

### Parallelität (`CLIPFORGE_MAX_WORKERS`)

Jobs laufen in einem `ThreadPoolExecutor`. Die parallele Verarbeitung ist über
`CLIPFORGE_MAX_WORKERS` konfigurierbar (**Default 2**). Da jeder Job FFmpeg
(und ggf. Whisper) startet, gilt **Stabilität vor Geschwindigkeit**: `=1`
serialisiert strikt (ein Job nach dem anderen). Der Batch-Endpoint reiht nur
ein — die tatsächliche Nebenläufigkeit bestimmt der Pool.

### `GET /api/config`

Liefert die Frontend-relevanten Limits/Optionen, damit die UI keine Werte
doppelt pflegt: `{ max_upload_mb, max_batch_files, max_workers,
supported_video_types, analyzer_version, llm_analysis_available,
default_analyzer_mode, advanced_analysis_enabled }`. **Keine Secrets** —
`llm_analysis_available` sagt nur, *ob* ein API-Key vorhanden ist.

---

## Clip-Analyzer v2 & Performance-Score v2

Die automatische Clip-Auswahl läuft über einen modularen Analyzer
(`clipforge/analyzer.py`):

- **RuleBasedClipAnalyzer** (Default, ohne API-Key): erkennt Kandidaten aus
  `transcript.json` mit sauberen Satz-/Startgrenzen, hook-orientierten Starts
  (Frage/These/Zahl/Überraschung, DE+EN), idealer Länge 15–60 s (harte Grenzen
  8–90 s), **dedupliziert** ähnliche/überlappende Clips (Zeit-Overlap ODER
  Text-Jaccard) und wählt **diverse** Top-N.
- **OptionalLLMClipAnalyzer** (nur mit `ANTHROPIC_API_KEY`): re-rankt die bereits
  erzeugten **timestamp-basierten** Kandidaten (erfindet keine neuen), sendet nur
  die Kandidaten-Fenster (nicht das ganze Video), JSON-validiert.
- **FallbackChain**: LLM → bei jedem Fehler (Timeout, Rate-Limit, ungültiges
  JSON) zurück auf regelbasiert.

`analyzer_mode` ∈ `rule_based` | `llm` | `fallback`. Steuerbar per Upload-Feld
`advanced_analysis` (Default `true`; `false` = Legacy-Analyzer v1).

**Performance-Score (0–100)** mit 10 gewichteten Komponenten: `hook_strength`,
`context_independence`, `retention_potential`, `clarity`,
`emotional_intensity`, `information_density`, `share_comment_potential`,
`platform_fit`, `uniqueness`, `editability`. Kalibriert gegen Inflation
(gute Clips 70–85, sehr starke 85–95, schwache < 60).

`clips.json` (Top-Level): `analyzer_version`, `analyzer_mode`,
`candidate_count`, `deduplicated_count`. Pro Clip zusätzlich:
`performance_score`, `score_breakdown` (10 Komponenten), `score_reason`,
`improvement_suggestions[]`, `risk_flags[]`, `best_platform`, `platform_reason`,
`hook_type`, `clip_type`, `language`, `duplicate_group` (optional),
`transcript_excerpt`. Die Legacy-Felder `score`/`breakdown` bleiben erhalten
(Rückwärtskompatibilität) — alte Clips ohne v2-Felder werden weiter angezeigt.

> **Grenzen / ehrlich:** keine Viralitätsgarantie — der Score ist eine
> Heuristik-Einschätzung. Der LLM-Modus kann irren; die Qualität hängt stark vom
> Transkript ab.

---

## Caption-Styles & Brand Kit

### `GET /api/caption-styles`

5 zentral in `captions.STYLES` definierte Styles (keine Magic Values verstreut).
Ein unbekannter `caption_style` fällt beim Rendern auf `clean` zurück; das Timing
bleibt synchron (auch mit Silence-Removal).

```json
{ "default": "clean", "styles": [
  { "style_id": "clean", "name": "clean",
    "description": "Schlicht & professionell …",
    "recommended_for": "Business, Talking-Head, allgemein",
    "preview_label": "Clean weiß" },
  { "style_id": "bold_creator", … }, { "style_id": "high_energy", … },
  { "style_id": "podcast", … }, { "style_id": "minimal", … }
]}
```

### `GET /api/brand-kit` · `POST /api/brand-kit`

Optionales, lokales Brand Kit (Datei `api/config/brand_kit.json`, überschreibbar
via `CLIPFORGE_BRAND_KIT`). **Keine DB, kein Account, keine Cloud.** Fehlt die
Datei, gelten Defaults und es wird **kein** Brand-Effekt aufs Rendering
angewandt (`_exists: false`, Ausgabe unverändert).

Felder: `brand_name`, `primary_color` (Highlight), `secondary_color` (Outline),
`font_family` (optional), `caption_style_default`, `highlight_keywords[]`,
`watermark_text`, `watermark_enabled`.

`POST` validiert und speichert. Fehler → **`400`**:
- ungültige Hex-Farbe (`#RGB`/`#RRGGBB`), unbekannter `caption_style_default`,
  `watermark_text` > 40 Zeichen, > 20 Keywords bzw. Keyword > 30 Zeichen.

**Wirkung im Rendering** (stabil, keine instabile Filter-Kette):
- `primary_color` → Highlight-Farbe (aktuelles Karaoke-Wort + Keywords).
- `secondary_color` → Outline-Farbe.
- `highlight_keywords` → diese Wörter werden in den Captions eingefärbt.
- `watermark_text` (nur bei `watermark_enabled`) → **ein** kleines ASS-Event
  oben-mittig (Safe Area).

Metadaten `caption_style` / `brand_kit_used` / `brand_kit_name` landen in
`clips.json` (+ `caption_info` pro Clip), in manuellen Export-Metadaten und in
der `metadata.json` von `exports.zip` / `all-exports.zip` (dort als
`caption_style_default`).

> **Grenzen:** keine externen/mitgelieferten Fonts (System-/Standard-Font,
> FFmpeg-Fallback), die UI-Vorschau ist nur eine **CSS-Näherung** (die
> FFmpeg-Ausgabe ist maßgeblich), keine Cloud-Synchronisierung.

---

## Job abbrechen (`POST /api/jobs/{job_id}/cancel`)

**Ehrlich kooperativ — kein harter Prozess-Kill** (der würde halb-geschriebene
MP4s riskieren):

- `queued`-Job → **sofort** `canceled` (Worker bricht am Eintritt ab, keine
  Verarbeitung).
- `processing`-Job → `cancel_requested` wird gesetzt; die Pipeline stoppt am
  **nächsten sicheren Checkpoint** (vor/nach Transkription, vor/nach jedem
  Clip-Render). Ein bereits laufender FFmpeg-Schritt **läuft zu Ende**, danach
  greift der Abbruch → `canceled`. Praktisch heißt das: der Abbruch ist nicht
  zwingend sofort, sondern nach dem aktuellen Render-Schritt (kann Sekunden
  dauern).
- Endzustand (`completed`/`failed`/`interrupted`/`incomplete`/`canceled`) →
  **`409`**; unbekannter Job → **`404`**.

```json
// 200 (processing)
{ "canceled": true, "job_id": "…", "status": "processing",
  "message": "Abbruch angefordert — Job stoppt am nächsten sicheren Checkpoint …" }
```

Bereits fertig gerenderte MP4s **bleiben erhalten** (Auto-Clips/manuelle Exporte
werden nicht angefasst). `canceled`-Jobs werden nach Restart **restored** und
sind **löschbar**. Job-Felder: `cancel_requested`, `canceled_at`,
`cancel_reason`. In `GET /api/storage` erscheinen sie unter `by_status.canceled`
und als **eigene** Gruppe `cleanup_candidates.canceled` (bewusst **nicht** Teil
des Standard-Bulk-Cleanups → nicht versehentlich löschbar).

---

## Manuelle Re-Renders (Web-Clip-Editor)

Der Nutzer kann einen bestehenden Clip feinjustieren und neu exportieren. Das
Backend nutzt dafür das Quellvideo (`jobs/<id>/input.*`) und das gespeicherte
`transcript.json` und ruft die **bestehende** `render_clip()`-Funktion auf —
keine Render-Logik dupliziert. Ergebnisse landen strikt getrennt unter
`jobs/<id>/manual_exports/` und **überschreiben die Auto-Clips nie**.

### `POST /api/jobs/{job_id}/clips/{clip_index}/rerender`

JSON-Body:

| Feld | Typ | Pflicht | Default | Beschreibung |
|---|---|---|---|---|
| `start_time` | float | ja | – | Neue Startzeit (Sekunden, Quellvideo-Zeitachse) |
| `end_time` | float | ja | – | Neue Endzeit; muss `> start_time` sein |
| `title` | string | nein | – | Optionaler Titel |
| `caption_style` | string | nein | `high_energy` | `high_energy` / `clean` |
| `caption_mode` | string | nein | `karaoke` | `karaoke` / `standard` |
| `remove_silence` | bool | nein | `true` | Stille Pausen entfernen |
| `reframe_mode` | string | nein | `smart` | `smart` / `face` / `center` |
| `export_name` | string | nein | – | (reserviert; Dateiname wird intern vergeben) |

Validierung: `end_time > start_time`, Clip-Länge **5–90 s** (`400` bei Verstoß),
gültiger `clip_index` (`404`), vorhandenes Quellvideo/Transkript (`409`).
Antwort = das Metadaten-dict des neuen Exports (siehe unten) plus `log`.

Der neue Export wird als `manual_exports/clip_{clip_index}_{timestamp}.mp4`
gespeichert, dazu eine gleichnamige `.json` mit den Metadaten:

```json
{
  "export_id": "clip_1_20260701T034721Z",
  "source_clip_index": 1,
  "created_at": "…",
  "start_time": 1.0, "end_time": 13.0,
  "original_start_time": 0.0, "original_end_time": 29.0,
  "final_duration": 12.0,
  "title": "Editierter Clip",
  "caption_mode": "karaoke", "caption_style": "clean",
  "remove_silence": false, "reframe_mode": "center",
  "score": 59.8,
  "output_file": "clip_1_20260701T034721Z.mp4",
  "silence_info": { … }, "reframe_info": { … }, "caption_info": { … },
  "warning": null
}
```

### `GET /api/jobs/{job_id}/manual-exports`

`{ "job_id": "…", "exports": [ <metadata>, … ] }` — neueste zuerst, jeweils mit
zusätzlichem `available` (MP4 auf Platte vorhanden?).

### `GET …/manual-exports/{export_id}/preview` · `…/download`

Inline-Stream (Range-Support) bzw. Attachment-Download des manuellen Exports.
Ungültige/nicht existierende `export_id` → `404` (Path-Traversal wird geblockt).

> `exports.zip` enthält bewusst weiter **nur die Auto-Clips** (unverändert). Das
> kombinierte Paket (Auto + manuell, geordnete Ordner) liefert der Endpoint
> **`all-exports.zip`** (siehe oben).

---

## Löschen / Cleanup

Zwei getrennte Löschvorgänge — ein **ganzer Job** vs. ein **einzelner manueller
Export**. Beide löschen **ausschließlich** innerhalb von `jobs/` (siehe
Sicherheit unten).

### `DELETE /api/jobs/{job_id}`

Löscht den kompletten Ordner `jobs/<job_id>/` (Auto-Clips, `manual_exports/`,
alle JSONs) und entfernt den Job aus der Registry.

- `processing`-Job → **`409`** („Job wird gerade verarbeitet …"), außer
  `?force=true` wird gesetzt. Alle anderen Zustände (`completed`, `failed`,
  `interrupted`, `incomplete`, restored) sind normal löschbar.
- Unbekannter Job → **`404`**. Unsichere `job_id` → **`400`**.

```json
// 200
{ "deleted": true, "job_id": "…", "removed_files_count": 7, "removed_bytes": 6240166 }
```

### `DELETE /api/jobs/{job_id}/manual-exports/{export_id}`

Löscht **nur** die MP4 + die passende Sidecar-`{export_id}.json` eines manuellen
Exports. **Auto-Clips bleiben unberührt.** Danach zeigt
`GET …/manual-exports` die aktualisierte Liste, `all-exports.zip` enthält den
Export nicht mehr, und `manual_export_count` / `total_export_count` /
`has_manual_exports` / `all_exports_ready` stimmen wieder.

- Nicht vorhanden → **`404`**. Unsichere `export_id` → **`400`**.

```json
// 200
{ "deleted": true, "export_id": "…",
  "removed_files": ["….mp4", "….json"], "removed_bytes": 973603 }
```

### Sicherheit (Löschlogik)

- **Path-Traversal geblockt:** `job_id`/`export_id` mit `/`, `\`, `..` oder als
  absoluter Pfad werden abgewiesen.
- **Jobs-Root-Schutz:** vor dem Löschen wird der Zielpfad per `realpath`
  aufgelöst und geprüft, dass er **strikt unterhalb** von `jobs/` (bzw.
  `manual_exports/`) liegt — nie der Ordner selbst, nie darüber.
- **Processing-Schutz:** laufende Renders werden nicht still gelöscht (`409`).
- **Keine stillen Fehler:** kann nur teilweise gelöscht werden, meldet die API
  das klar (`deleted:false` + `error` bzw. HTTP `500`).

---

## Speicher-Übersicht & Bulk-Cleanup

### `GET /api/storage`

Lokale Speicher-Übersicht über **alle** Jobs (nutzt Registry + Dateisystem,
keine DB). Kaputte Job-Ordner ergeben 0 Bytes und crashen den Endpoint nicht.
`processing`-Jobs werden gezählt, aber **nie** als Cleanup-Kandidat gelistet.

```json
{
  "jobs_root": "…/jobs",
  "total_jobs": 21, "total_bytes": 73180160, "total_human": "69.8 MB",
  "by_status": { "completed": 19, "failed": 0, "interrupted": 0,
                 "incomplete": 2, "processing": 0, "queued": 0 },
  "counts": { "auto_exports": 28, "manual_exports": 3, "total_exports": 31 },
  "largest_jobs": [
    { "job_id": "…", "status": "completed", "filename": "sample.mp4",
      "bytes": 8283750, "human_size": "7.9 MB",
      "auto_export_count": 2, "manual_export_count": 1,
      "restored": true, "created_at": "…", "updated_at": "…" }
  ],
  "cleanup_candidates": {
    "failed": [], "interrupted": [], "incomplete": ["…","…"],
    "completed_without_exports": []
  }
}
```

**Cleanup-Kandidaten** sind Jobs mit Status `failed` / `interrupted` /
`incomplete` (plus separat `completed_without_exports` = fertige Jobs ganz ohne
MP4s). `?largest=N` steuert die Länge von `largest_jobs` (Default 10).

### `POST /api/jobs/bulk-delete`

```json
// Request
{ "job_ids": ["…","…"], "confirm": "DELETE", "force": false }
```

- `confirm` muss exakt `"DELETE"` sein (fehlend oder falsch → **`400`**).
- Leere `job_ids` → **`400`**.
- Nutzt **dieselbe sichere `registry.delete()`-Logik** wie Einzel-Delete →
  Path-Traversal geblockt, `jobs/`-Containment, `processing`-Schutz.
- **Teilweises Scheitern bricht nicht ab** — jedes Ergebnis wird einzeln
  berichtet.

```json
// 200
{
  "deleted_count": 2, "failed_count": 1,
  "removed_bytes": 123456, "removed_human": "120.6 KB",
  "results": [
    { "job_id": "…", "deleted": true, "removed_files_count": 10, "removed_bytes": 12345 },
    { "job_id": "…", "deleted": false, "error": "processing job cannot be deleted without force" }
  ]
}
```

> **Wichtig:** `completed`-Jobs werden **nur** gelöscht, wenn sie explizit in
> `job_ids` stehen — der UI-Button „Problematische Jobs aufräumen" nimmt sie
> bewusst **nicht** auf. `force` ist nur API-seitig, nicht in der UI. Kein
> Undo/Papierkorb, keine Cloud-Speicherverwaltung.

---

## curl-Testbefehle

```bash
BASE=http://127.0.0.1:8000

# 1) Health
curl -s $BASE/health | python3 -m json.tool

# 2) Job anlegen (deterministisch mit mitgeliefertem Test-Transkript)
curl -s -F "file=@testdata/sample.mp4" \
        -F "transcript=@testdata/transcript.json" \
        -F "top_n=3" \
        $BASE/api/jobs
# -> {"job_id":"<ID>","status":"processing"}

# Praktisch: job_id in Variable
JOB=$(curl -s -F "file=@testdata/sample.mp4" -F "transcript=@testdata/transcript.json" \
        $BASE/api/jobs | python3 -c "import sys,json;print(json.load(sys.stdin)['job_id'])")

# 3) Status / Progress pollen
curl -s $BASE/api/jobs/$JOB | python3 -m json.tool

# 4) Alle Jobs
curl -s $BASE/api/jobs | python3 -m json.tool

# 5) Ergebnis-JSONs
curl -s $BASE/api/jobs/$JOB/clips      | python3 -m json.tool
curl -s $BASE/api/jobs/$JOB/transcript | python3 -m json.tool

# 6) Clip 1 als MP4 herunterladen
curl -s -o clip1.mp4 $BASE/api/jobs/$JOB/clips/1/download
ffprobe clip1.mp4   # 1080x1920, mit Audio

# 7) Dateien im Job-Ordner
curl -s $BASE/api/jobs/$JOB/files | python3 -m json.tool
```

### Echtes Video ohne Transkript

```bash
# Pipeline transkribiert dann lokal mit faster-whisper.
# Hinweis: Beim 1. Lauf wird das Whisper-Modell geladen (~140 MB) -> dauert.
curl -s -F "file=@mein_video.mp4" -F "top_n=5" $BASE/api/jobs
```

---

## Fehlerantworten

| Fall | HTTP | `detail` |
|---|---|---|
| Ungültiger Dateityp | `400` | `Ungültiger Dateityp '.txt'. Erlaubt: …` |
| Job nicht gefunden | `404` | `Job nicht gefunden.` |
| Clip nicht gefunden | `404` | `Clip N nicht gefunden.` |
| Exportdatei fehlt | `404` | `Exportdatei fehlt …` |
| transcript/clips noch nicht da | `404` | `… noch nicht vorhanden …` |
| FFmpeg fehlt | Job → `failed` | `FFmpeg fehlt: …` |
| Pipeline-Fehler | Job → `failed` | `<ExceptionTyp>: <Meldung>` |
| Leeres Ergebnis (0 Clips) | Job → `completed` | `result.warning` gesetzt; Download → `404` |

---

## Architektur (Erinnerung)

```
Next.js (später)  ──HTTP──►  FastAPI (app.py)  ──Funktionsaufruf──►  clipforge.run_pipeline
                             jobs.py: dict + ThreadPool + jobs/<id>/
```

Kein Code in `api/clipforge/` wurde für die API verändert.
