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
| `GET` | `/api/jobs/{job_id}` | Voller Status: Progress, Logs, Fehler, Ergebnis |
| `GET` | `/api/jobs/{job_id}/transcript` | `transcript.json` (falls vorhanden) |
| `GET` | `/api/jobs/{job_id}/clips` | `clips.json` (falls vorhanden) |
| `GET` | `/api/jobs/{job_id}/clips/{clip_index}/download` | Gerenderten Clip als MP4 (1-basiert) |
| `GET` | `/api/jobs/{job_id}/files` | Alle Dateien im Job-Ordner |

### `POST /api/jobs` — Felder (multipart/form-data)

| Feld | Typ | Pflicht | Default | Beschreibung |
|---|---|---|---|---|
| `file` | Datei | ja | – | Video (`.mp4 .mov .mkv .webm .avi .m4v`) |
| `top_n` | int | nein | `5` | Anzahl der Top-Clips |
| `transcript` | Datei | nein | – | Vorhandenes Transkript-JSON; überspringt Whisper (spiegelt CLI-Flag `--transcript`, ideal für schnelle Tests) |

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
