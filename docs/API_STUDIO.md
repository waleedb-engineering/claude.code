# Creator-Studio-API (`/api/studio/*`)

Lokale REST-API des Studios. Die vollständigen, maschinenlesbaren Modelle
liefert das laufende Backend unter `http://127.0.0.1:8000/openapi.json`
(Swagger-UI: `/docs`). Die übrigen Endpunkte stehen in [`API.md`](API.md).

Die API hat **keine Authentifizierung** und ist nur für `127.0.0.1` gedacht.

## Grundregeln

**Fehlerformat** — jeder Studio-Fehler hat einen stabilen Code:

```json
{"detail": {"code": "version_conflict", "message": "…", "details": {"current_version": 7}}}
```

Eingaben, die schon am Schema scheitern, liefern FastAPI-üblich `422` mit einer
Liste in `detail`.

**Lange Arbeit blockiert nie.** Ingest und Render laufen als Aufgabe. Die
Antwort enthält eine Task-ID; den Zustand liefert `GET /tasks/{id}`
(`queued`, `running`, `succeeded`, `failed`, `canceled`, `interrupted`).
Aufgaben liegen auf der Platte: nach einem Neustart werden wartende Aufgaben
neu eingeplant, laufende als `interrupted` markiert und sind per
`POST /tasks/{id}/retry` wiederholbar.

**Idempotenz.** `POST /projects`, `/projects/{id}/ingest` und
`/projects/{id}/render` akzeptieren den Header `Idempotency-Key`. Derselbe Key
liefert dasselbe Projekt bzw. dieselbe Aufgabe. `POST /projects/{id}/export`
ist je Render von sich aus idempotent, `mark-published` ebenfalls.

**Versionierung.** Jede schreibende Editor-Route verlangt `expected_version`.
Stimmt sie nicht mit dem gespeicherten Stand überein, kommt `409
version_conflict` und nichts wird überschrieben.

**Pfade.** IDs sind 12 Hex-Zeichen. Dateinamen werden auf einen sicheren
Basisnamen reduziert; alles außerhalb des Projektordners wird abgelehnt.

**Secrets.** Keine Antwort enthält Schlüssel. Provider melden nur die Namen
der benötigten Umgebungsvariablen.

## Typischer Ablauf (für Skripte und Agenten)

1. `POST /projects` mit `{"workflow": "script", "script": "…"}` → `project.id`, `task_id`
2. `GET /tasks/{task_id}` bis `succeeded`
3. optional `PATCH /projects/{id}` oder `POST /projects/{id}/scenes`
4. `GET /projects/{id}/quality` und `/estimate`
5. `POST /projects/{id}/render` mit `{"mode": "final"}` → Task
6. `GET /projects/{id}/renders` → `render_id`, Datei unter `/renders/{render_id}/file`
7. `POST /projects/{id}/export` → `job_id` für den Publishing-Planner

Datei-Workflows (`pdf`, `audio`, `music`, `podcast`, `longform`, `media`):
erst `POST /projects`, dann Upload über `/source` bzw. `/media`, dann
`POST /projects/{id}/ingest`.

## Endpunkte

### Übersicht und Optionen

| Methode | Pfad | Zweck |
|---|---|---|
| GET | `/overview` | Flags, Workflows, Zähler, Worker-Status |
| GET | `/workflows` | Workflows mit Verfügbarkeit und Begründung |
| GET | `/providers` | Provider- und Plattform-Readiness |
| GET | `/voices?language=&tone=` | Stimmen je Provider + automatische Auswahl |
| POST | `/voices/preview` | Hörprobe (MP3). Kostenpflichtig nur mit `confirm_cost: true` |
| GET | `/caption-styles` | Caption-Stile |
| GET | `/caption-preview?style=&aspect_ratio=&text=` | Vorschaubild (PNG) |

### Musik

| Methode | Pfad | Zweck |
|---|---|---|
| GET | `/music` | Bibliothek |
| POST | `/music` | Audiodatei hochladen (multipart `file`) |
| GET | `/music/{id}/file` | Datei |
| GET | `/music/{id}/beats` | Tempo und Beat-Zeiten |
| DELETE | `/music/{id}` | löschen |

### Projekte

| Methode | Pfad | Zweck |
|---|---|---|
| GET | `/projects` | Liste |
| POST | `/projects` | anlegen (`workflow`, je nach Workflow `prompt`, `script`, `url`, `job_id`, `product`) |
| GET | `/projects/{id}` | Projekt, Aufgaben, Renders, Medien, Artefakte |
| PATCH | `/projects/{id}` | Editor-Speicherung (`expected_version` + geänderte Felder) |
| DELETE | `/projects/{id}` | löschen (nicht bei laufender Aufgabe) |
| POST | `/projects/{id}/duplicate` | kopieren |
| POST | `/projects/{id}/remix` | kopieren und übernommene Merkmale festhalten |
| POST | `/projects/{id}/source` | Quelldatei (multipart `file`, `kind` = `source` oder `transcript`) |
| POST | `/projects/{id}/ingest` | Quelle verarbeiten → Task |
| GET/POST | `/projects/{id}/media` | Medien auflisten / hochladen |
| GET/DELETE | `/projects/{id}/media/{name}` | Datei abrufen / löschen |
| POST | `/projects/{id}/scenes` | Szenen-Operation: `add`, `update`, `delete`, `duplicate`, `move`, `reorder` |
| POST | `/projects/{id}/scenes/{scene_id}/regenerate` | eine Szene neu erzeugen → Task mit Szenen-Vorschau |
| GET | `/projects/{id}/estimate` | Kostenschätzung und Verbrauch |
| GET | `/projects/{id}/quality` | inhaltliche Prüfung vor dem Render |
| POST | `/projects/{id}/render` | `{"mode": "final" \| "preview"}` → Task |
| GET | `/projects/{id}/renders` | Render-Berichte (ffprobe-Werte, Warnungen, Kosten) |
| GET | `/projects/{id}/renders/{render_id}` | ein Bericht |
| GET | `/projects/{id}/renders/{render_id}/file` | MP4 (`?download=true` für Download) |
| POST | `/projects/{id}/export` | finalen Render als Job an den Publishing-Planner geben |
| GET | `/projects/{id}/versions` | gespeicherte Stände |
| POST | `/projects/{id}/versions/{n}/restore` | Stand wiederherstellen |
| GET | `/projects/{id}/artifacts` | Extraktions-Artefakte |
| GET | `/projects/{id}/artifacts/{name}` | ein Artefakt (`fetch.json`, `extraction.json`, `transcript.json`, `script.json`, `beats.json`) |

### Aufgaben

| Methode | Pfad | Zweck |
|---|---|---|
| GET | `/tasks/{id}` | Zustand, Fortschritt, Ergebnis, Fehler |
| POST | `/tasks/{id}/retry` | fehlgeschlagene/unterbrochene Aufgabe neu starten |
| POST | `/tasks/{id}/cancel` | abbrechen |

### Automationen

| Methode | Pfad | Zweck |
|---|---|---|
| GET/POST | `/automations` | Liste / anlegen |
| GET/PATCH/DELETE | `/automations/{id}` | lesen / ändern / löschen |
| POST | `/automations/{id}/pause`, `/resume` | pausieren / fortsetzen |
| POST | `/automations/{id}/run` | sofort einmal ausführen → Task |
| POST | `/automations/{id}/runs/{run_id}/retry` | Lauf wiederholen |

`publishing.mode` kennt nur `none` und `draft`.

### Publishing, Analytics, Ideen

| Methode | Pfad | Zweck |
|---|---|---|
| GET | `/publishing/platforms` | Readiness je Plattform |
| GET | `/publishing/drafts` | alle Entwürfe mit Anzeigezustand |
| POST | `/publishing/{job_id}/{publishing_id}/mark-published` | manuelle Veröffentlichung bestätigen (`confirm: true` Pflicht) |
| GET | `/analytics` | veröffentlichte Entwürfe, Hook-Vergleich, Potenzial vs. Ergebnis |
| GET | `/analytics/{job_id}/{publishing_id}` | Messverlauf |
| POST | `/analytics/{job_id}/{publishing_id}/metrics` | Werte manuell eintragen |
| POST | `/analytics/{job_id}/{publishing_id}/sync` | Werte über den Plattform-Adapter abrufen |
| GET/POST | `/ideas` | suchen (`q`, `niche`, `hook_type`, `format`, `tag`, `platform`) / speichern |
| PATCH/DELETE | `/ideas/{id}` | ändern / löschen |
| POST | `/ideas/{id}/use` | Projekt aus eigenem Thema, inspiriert von der Idee |

Entwürfe selbst (anlegen, bearbeiten, Export-Pack, YouTube) bleiben unter
`/api/jobs/{job_id}/publishing…`, siehe [`API.md`](API.md). Neu ist dort die
Plattform `x`.

Metriken tragen ihre Herkunft: `manual`, `synced`; das Performance-Potenzial
ist als `estimated` gekennzeichnet. Fehlende Werte sind `null`.

## Fehlercodes

| Bereich | Codes |
|---|---|
| Allgemein | `validation_error`, `invalid_id`, `unsafe_path`, `feature_disabled`, `internal_error` |
| Projekt | `project_not_found`, `project_busy`, `project_empty`, `version_required`, `version_conflict`, `version_not_found`, `scene_invalid`, `scene_not_found`, `workflow_unavailable` |
| URL | `url_invalid`, `url_blocked`, `url_unreachable`, `url_timeout`, `url_too_large`, `url_too_many_redirects`, `url_http_error`, `url_unsupported_type` |
| Dateien | `file_empty`, `file_too_large`, `file_type_not_allowed`, `file_unreadable`, `upload_not_expected`, `source_missing`, `media_not_found`, `media_in_use`, `media_unsupported`, `music_not_found`, `artifact_not_found` |
| Extraktion | `extraction_empty`, `extraction_failed`, `pdf_invalid`, `pdf_encrypted`, `pdf_no_text`, `pdf_dependency_missing`, `transcription_unavailable`, `transcription_failed`, `transcription_empty`, `script_empty`, `job_not_found`, `job_no_transcript`, `jobs_unavailable` |
| Render | `quality_blocked`, `budget_exceeded`, `render_missing`, `render_not_final`, `render_not_found`, `render_not_applicable`, `render_timeout`, `ffmpeg_failed`, `ffmpeg_missing`, `beat_detection_failed` |
| Provider | `provider_unknown`, `provider_not_configured`, `provider_failed`, `confirmation_required` |
| Aufgaben | `task_not_found`, `task_active`, `task_not_retryable`, `task_not_cancelable`, `task_kind_unknown`, `interrupted` |
| Automation | `automation_not_found`, `automation_busy`, `automation_capacity`, `run_not_found`, `run_not_retryable` |
| Publishing/Analytics | `draft_not_found`, `draft_not_published`, `metrics_unavailable`, `metrics_sync_failed`, `idea_not_found` |

## Agenten und MCP

Die API ist bewusst so geschnitten, dass ein Agent sie direkt bedienen kann:
JSON rein und raus, stabile Fehlercodes, idempotente Mutationen, Aufgaben mit
abfragbarem Zustand. Ein MCP-Server existiert **nicht**; wer einen baut, kann
die Operationen aus `openapi.json` übernehmen.
