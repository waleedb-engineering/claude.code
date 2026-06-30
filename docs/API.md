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

---

## Endpoints

| Methode | Pfad | Zweck |
|---|---|---|
| `GET` | `/health` | Backend- & FFmpeg-Status |
| `POST` | `/api/jobs` | Video hochladen, Job starten → `job_id` |
| `GET` | `/api/jobs` | Alle Jobs (Kurzstatus) |
| `GET` | `/api/jobs/{job_id}` | Voller Status: Progress, Logs, Fehler, Ergebnis, `files`-Übersicht |
| `GET` | `/api/jobs/{job_id}/transcript` | `transcript.json` (falls vorhanden) |
| `GET` | `/api/jobs/{job_id}/clips` | `clips.json` (falls vorhanden) |
| `GET` | `/api/jobs/{job_id}/clips/{clip_index}/download` | Gerenderten Clip als MP4 (Attachment, 1-basiert) |
| `GET` | `/api/jobs/{job_id}/clips/{clip_index}/preview` | Clip inline streamen (video/mp4, Range/206 → Seeking) |
| `GET` | `/api/jobs/{job_id}/exports.zip` | Alle MP4-Clips + clips.json/transcript.json/metadata.json als ZIP |
| `GET` | `/api/jobs/{job_id}/files` | Alle Dateien im Job-Ordner |

### `files`-Übersicht in `GET /api/jobs/{job_id}`

```json
"files": {
  "clip_count": 2,          // erkannte/bewertete Clips
  "mp4_count": 2,           // tatsächlich gerenderte MP4-Exporte
  "has_transcript": true,   // transcript.json vorhanden
  "has_clips_json": true,   // clips.json vorhanden
  "exports_ready": true     // mp4_count > 0 (ZIP/Downloads verfügbar)
}
```

### `preview` vs. `download`

- **preview**: ohne `Content-Disposition: attachment` → Browser spielt inline
  ab; unterstützt `Range`-Requests (HTTP 206) fürs Seeken in `<video>`.
- **download**: mit `attachment; filename=…` → erzwingt Speichern.

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
| `transcript` | Datei | nein | – | Vorhandenes Transkript-JSON; überspringt Whisper (spiegelt CLI-Flag `--transcript`, ideal für schnelle Tests) |

Der gewählte `remove_silence`-Wert ist im Job-Status sichtbar (Feld
`remove_silence`) und im `progress`-Log (erkannte Stellen, entfernte Dauer,
ggf. Fallback). Werden keine sinnvollen Pausen gefunden, wird normal gerendert.

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
