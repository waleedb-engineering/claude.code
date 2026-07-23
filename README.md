# ClipForge AI

**Local-first AI video-shorts tool.** Aus einem langen Video (Podcast, Talk,
Coaching-Call) werden lokal automatisch mehrere kurze, vertikale 9:16-Clips mit
eingebrannten Untertiteln, einem transparenten Performance-Potential-Score und
publizierfertigen Plattform-Texten — für YouTube Shorts, TikTok und Instagram
Reels.

> *Turn one long video into several ready-to-post vertical shorts — entirely on
> your own machine. No account, no mandatory cloud.*

`Version 0.1.0-beta.1` · **Closed Beta / Release Candidate** · local-first ·
kein Account, keine Pflicht-Cloud · PRIVATE-only YouTube-Pfad (default aus) ·
kein Public/Unlisted, kein TikTok/Instagram-Auto-Upload.

> **Projektstatus (ehrlich):** Bereit für **lokales Beta-Testing**. Kein
> produktionsreifes SaaS, nicht für Internet-Exposition gehärtet. Der echte
> YouTube-Upload-Pfad ist implementiert und mit gemocktem Client getestet, aber
> **noch nicht** mit einem realen Google-Konto End-to-End verifiziert.

### Beta-Einstieg

- 🚀 **Beta-Tester:** [`docs/BETA_TESTER_GUIDE.md`](docs/BETA_TESTER_GUIDE.md)
- 📋 **Release Notes:** [`docs/RELEASE_NOTES_0.1.0-beta.1.md`](docs/RELEASE_NOTES_0.1.0-beta.1.md)
- ⚠️ **Bekannte Grenzen:** [`docs/KNOWN_ISSUES.md`](docs/KNOWN_ISSUES.md)
- 🔒 **Security & Privacy:** [`docs/SECURITY_PRIVACY_REVIEW.md`](docs/SECURITY_PRIVACY_REVIEW.md)

### Technische Dokumentation

- 📄 **Produktdefinition:** [`docs/PRODUCT.md`](docs/PRODUCT.md) — Problem, Lösung, MVP-Scope, Architektur, Risiken.
- 🌐 **Web-Plan:** [`docs/WEB_PLAN.md`](docs/WEB_PLAN.md) · **HTTP-API:** [`docs/API.md`](docs/API.md) — FastAPI-Bridge über dem Pipeline-Kern.
- 🖥️ **Web-App:** [`docs/WEB.md`](docs/WEB.md) — Next.js-UI lokal starten.
- 🎬 **YouTube-Konzept:** [`docs/YOUTUBE_PUBLISHING.md`](docs/YOUTUBE_PUBLISHING.md) · **Real-Test:** [`docs/YOUTUBE_REAL_TEST_CHECKLIST.md`](docs/YOUTUBE_REAL_TEST_CHECKLIST.md)

### Preview

> _Screenshots/GIFs folgen. Bis dahin: lokal starten (siehe Schnellstart) und
> `http://127.0.0.1:3000/upload` öffnen — die UI führt durch Upload → Job →
> Clips → Editor → Publishing Planner → YouTube Dry-Run._

## Schnellstart Web-App

```bash
./scripts/setup_local.sh    # 1) Setup: venv, Dependencies, .env, ffmpeg-Check
./scripts/start_local.sh    # 2) Start: Backend + Frontend, ein Befehl, Strg+C zum Stoppen
```

Danach im Browser öffnen: **http://127.0.0.1:3000/upload**

Umgebung prüfen (Python/Node/ffmpeg/Dependencies/Ports/optionale Features):

```bash
python3 scripts/clipforge_doctor.py
```

Tests laufen lassen:

```bash
cd api && python3 tests/test_pipeline_core.py   # Backend-Regressionstests
cd web && npm run test:e2e                       # Browser-E2E-Smoke-Suite
```

📘 **Ausführliche Anleitung (Voraussetzungen, erster Test, typische Fehler,
Reset):** [`docs/LOCAL_BETA_GUIDE.md`](docs/LOCAL_BETA_GUIDE.md)

> **Ehrlicher Hinweis:** ClipForge garantiert **keine** Viralität. Es
> **maximiert die Wahrscheinlichkeit** für starke Performance durch messbare
> Signale: Hook-Erkennung, Retention-Optimierung, automatische Clip-Auswahl,
> Untertitel, schnelle Schnitte, einen transparenten **Performance-Potential-
> Score**, Plattform-Metadaten und Varianten-Testing.

---

## Funktionsüberblick

| Bereich | Was es kann |
|---|---|
| **Analyse** | Lokale Transkription (faster-whisper) oder mitgeliefertes Transkript · Clip-Analyzer v2 mit nachvollziehbarem Score, Deduplizierung, Risk-Flags · optional per Claude verstärkt |
| **Rendering** | 9:16-Export (FFmpeg) · wortgenaue Karaoke-Untertitel · Silence-Removal · Smart-Reframe (lokale Gesichtserkennung) · Brand Kit |
| **Editor & Export** | Web-Clip-Editor mit Re-Render · manuelle Exporte · `exports.zip` / `all-exports.zip` |
| **Content** | Titel, Hook-Varianten, Hashtags, Plattform-Beschreibungen pro Clip (regelbasiert, optional KI) |
| **Publishing** | Lokaler Planner (Drafts, kein Auto-Upload) · globale Übersicht · YouTube **Dry-Run** · echter **privater** YouTube-Upload-Pfad (Flag, default aus) mit Retry/Recovery/Reconciliation/Race-Schutz |
| **DX / Release** | One-Command Setup/Start · Environment Doctor · Playwright-Browser-E2E · `release_check.sh` · reproduzierbares Beta-Package |

## Sichere Defaults

- **Local-first:** Videos/Clips/Drafts bleiben unter `api/jobs/`. Kein
  Cloud-Sync, kein Account. Cloud nur bei bewusst gesetzten optionalen Features
  (KI-Analyzer via `ANTHROPIC_API_KEY`, echter YouTube-Upload via Flags).
- **YouTube-Upload standardmäßig AUS** (`CLIPFORGE_ENABLE_YOUTUBE_UPLOAD=false`)
  und **ausschließlich `private`** — kein Public/Unlisted im Code vorhanden.
- **Kein Auto-Posting, kein Scheduling-Daemon, kein TikTok/Instagram-Upload.**
- **Keine Secrets im DOM/Log/Response**; YouTube-Tokens nur im OS-Keychain.
- **Nicht für Internet-Exposition** gedacht (kein Auth, offene CORS für lokale
  Entwicklung). Details: [`docs/SECURITY_PRIVACY_REVIEW.md`](docs/SECURITY_PRIVACY_REVIEW.md).

## YouTube-Status

Der private Upload-Pfad ist implementiert und mit gemocktem Google-Client
getestet, **aber noch nicht** mit einem echten Konto End-to-End verifiziert
(einziger offener Blocker). Standard-Testflow bleibt **Dry-Run**. Realer Test:
[`docs/YOUTUBE_REAL_TEST_CHECKLIST.md`](docs/YOUTUBE_REAL_TEST_CHECKLIST.md).

## Release-Package

Ein reproduzierbares, secret-freies Beta-Tarball wird lokal gebaut:

```bash
./scripts/build_beta_package.sh   # -> dist/clipforge-beta-0.1.0-beta.1.tar.gz
./scripts/release_check.sh        # Voll-QA-Gate: RELEASE CHECK PASSED/FAILED
```

Das Package enthält nur Quellcode, Skripte, Docs und Test-Fixtures — **keine**
`node_modules`, `.venv`, `.env`, Videos, Tokens oder Build-Artefakte.

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
| Schritt 18 | **Caption-Styles (5) & Brand Kit** | ✅ fertig & verifiziert |
| Schritt 19 | **Clip-Analyzer v2 & Performance-Score v2** | ✅ fertig & verifiziert |
| Schritt 20 | **Score-Kalibrierung & Analyzer-Härtung** | ✅ fertig & verifiziert |
| Schritt 21 | **Publishing Planner (lokale Drafts + Pack-ZIP, kein Upload)** | ✅ fertig & verifiziert |
| Schritt 22 | **Globale Publishing-Übersicht & Draft-Duplizieren** | ✅ fertig & verifiziert |
| Schritt 23 | **YouTube Publishing Adapter (Dry-Run, kein echter Upload)** | ✅ fertig & verifiziert |
| Schritt 24 | **YouTube OAuth-Readiness & sichere Token-Ablage (keyring, kein Upload)** | ✅ fertig & verifiziert |
| Schritt 25 | **YouTube OAuth-Flow-Skelett (Consent-URL, State/CSRF+PKCE, Callback, sichere Token-Speicherung — kein echter Exchange/Upload)** | ✅ fertig & verifiziert |
| Schritt 26 | **YouTube OAuth echter Token-Exchange (offizielle Google-Library, PKCE) — Token nur im Keychain, weiterhin kein Upload** | ✅ fertig & verifiziert |
| Schritt 27 | **YouTube echter PRIVATER Upload (`videos.insert`, private-only) — Feature-Flag + `UPLOAD_PRIVATE`-Bestätigung + Idempotenz + Token-Refresh** | ✅ fertig & verifiziert |
| Schritt 28 | **Upload-Hardening: Retry/Backoff-Policy, Attempt-History, `upload-status` + Reauth-Flow, sicherer manueller E2E-Testmodus** | ✅ fertig & verifiziert |
| Schritt 29 | **Crash-sichere Upload-State-Machine + Startup-Recovery + ID-basierte Reconciliation + Race-Schutz (2 Requests → 1 Upload)** | ✅ fertig & verifiziert |
| später | Public/Unlisted-Upload, geplante Uploads (`publishAt`), Auto-Posting | 🔭 später |

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
- **Caption-Styles & Brand Kit**: 5 zentral definierte Caption-Styles
  (`clean`, `bold_creator`, `high_energy`, `podcast`, `minimal`) — wählbar in
  Upload & Editor mit Beschreibung/CSS-Vorschau (`GET /api/caption-styles`).
  Unbekannter Style fällt auf `clean` zurück; Timing bleibt synchron (auch mit
  Silence-Removal). Ein optionales **Brand Kit** (`api/config/brand_kit.json`,
  keine DB/Cloud) definiert Primary/Secondary-Farbe, Default-Style,
  Highlight-Keywords und Watermark — wird beim Rendern **stabil** angewandt
  (Farb-Overrides + Keyword-Highlight + optionale Watermark als **ein**
  zusätzliches ASS-Event, keine neue Filter-Kette). Ohne Brand-Kit-Datei bleibt
  die Ausgabe unverändert. Verwaltung unter `/settings/brand-kit`
  (`GET`/`POST /api/brand-kit`, validiert: Hex-Farben, bekannter Style,
  Watermark ≤ 40). Metadaten (`caption_style`, `brand_kit_used`,
  `brand_kit_name`) landen in `clips.json`, Manual-Export-Metadaten und ZIPs.
- **Clip-Analyzer v2 & Performance-Score v2** (`analyzer.py`): bessere
  Kandidaten-Erkennung (saubere Satz-/Startgrenzen, hook-orientierte Starts,
  ideale Länge 15–60 s, harte Grenzen 8–90 s), **stärkere Deduplizierung**
  ähnlicher/überlappender Clips (bevorzugt saubere Satzenden), **diverse**
  Top-N-Auswahl (nicht 5× dieselbe Stelle) und Auffüll-Markierung (`filled_up` +
  `duplicate_like`), wenn zu wenig Vielfalt da ist. Der **Performance-Potential-Score
  (0–100)** ist in **Bänder kalibriert** (schwach 35–59 · solide 60–74 · gut
  75–84 · sehr stark 85–94 · 95+ extrem selten; siehe
  [`docs/ANALYZER_CALIBRATION.md`](docs/ANALYZER_CALIBRATION.md)) und hat 10
  nachvollziehbare Komponenten plus pro Clip `score_reason`,
  `improvement_suggestions`, `risk_flags`, `best_platform`, `hook_type`,
  `clip_type`, `language`, `duplicate_group`. **Risk-Flags** haben stabile
  englische Keys (`needs_context`, `slow_start`, `too_generic`, `weak_hook`,
  `too_long`, `too_short`, `low_information_density`, `unclear_takeaway`,
  `duplicate_like`, `language_mixed`, `transcript_quality_low`) und steuern die
  Verbesserungsvorschläge. **Default regelbasiert** (DE+EN, kein API-Key nötig);
  mit `ANTHROPIC_API_KEY` optionaler LLM-Modus, der die **timestamp-basierten**
  Kandidaten per Index re-rankt (halluziniert keine neuen Zeitfenster), robust
  JSON-parst (Fences/Clamp/Schema), mit Timeout, und bei jedem Fehler sauberer
  **Fallback**. `analyzer_mode` ∈ `rule_based` / `llm` / `fallback`. Umschaltbar
  über den Upload-Toggle „Erweiterte Clip-Analyse verwenden" (Default an); alte
  Clips ohne v2-Felder bleiben voll anzeigbar. **Weiterhin keine
  Viralitätsgarantie** — der Score ist eine Heuristik-Einschätzung.
- **Publishing Planner** (`publishing.py`, `/jobs/{id}/publishing`): plant
  Veröffentlichungen als **lokale Drafts** (Plattform-Auswahl, Texte aus dem
  Content-Paket, Checkliste inkl. 9:16-Prüfung, Publishing-Pack-ZIP für den
  manuellen Upload). **Kein echter Upload, kein OAuth, keine Tokens** — der
  komplette Plan für die spätere Plattform-Anbindung steht in
  [`docs/PUBLISHING_AGENT_PLAN.md`](docs/PUBLISHING_AGENT_PLAN.md).
- **Globale Publishing-Übersicht** (`GET /api/publishing`, Seite `/publishing`):
  alle Drafts über alle Jobs zentral filterbar (Plattform/Status/Suche/nur
  geplante), mit Summary-Cards und **Draft-Duplizieren** (auch für eine andere
  Plattform, mit Texten aus dem Content-Paket neu abgeleitet). Job-Detailseite
  zeigt dazu passende Publishing-Badges. Weiterhin **kein Upload, keine Tokens**.
- **YouTube Publishing Adapter — Phase 1: Dry-Run** (`platforms/youtube.py`):
  zeigt pro YouTube-Draft, was an die offizielle YouTube Data API
  (`videos.insert`) gehen *würde* (Metadaten-Vorschau, Checks, Blocker) —
  **löst nie einen Upload aus**. Der Publish-Endpoint ist sicher blockiert:
  ohne `CLIPFORGE_ENABLE_YOUTUBE_UPLOAD=true` → `403`, `public` nur mit
  Extra-Bestätigung, ohne Credentials → `409`; selbst bei grünem Licht
  `not_implemented` (kein Fake-Erfolg, kein Statuswechsel).
- **YouTube OAuth-Readiness — Phase 2** (`platforms/youtube_auth.py`): prüft
  **sicher**, ob ein späterer OAuth/Upload möglich *wäre* (Feature-Flag,
  Credentials-Metadaten — nur `basename`, nie Inhalt/Pfad — und Token-Store-
  Status). Token-Ablage **ausschließlich über OS-Keychain (`keyring`), kein
  Plaintext-Fallback**; fehlt keyring/Backend → `token_status: blocked`.
  Endpoints: `…/youtube/readiness`, `…/auth/start`, `…/auth/logout` (idempotent).
- **YouTube OAuth-Flow + echter Token-Exchange — Phase 2b/2c**
  (`platforms/youtube_oauth.py`): vollständiger, sicherer OAuth-Flow — **aber
  weiterhin ohne Upload und ohne `videos.insert`**.
  `POST /api/youtube/oauth/start` baut eine **echte Consent-URL** (Google
  Installed-App-Flow: `response_type=code`, `access_type=offline`, `state` für
  CSRF **und PKCE `S256`**) — liest dafür nur den `client_id` aus der
  Secrets-Datei, **nie das `client_secret`**, und öffnet **keinen** Browser.
  `GET /api/youtube/oauth/callback` prüft den `state` (einmalig, ablaufend,
  wiederverwendungssicher) und tauscht den Code **echt** über die offizielle
  Google-Library (`google-auth-oauthlib`, inkl. PKCE) gegen ein Token — das
  **nur** über den Keychain gespeichert wird. Fehlt die Library/Secrets oder
  scheitert Google, degradiert es sauber (`exchange_dependency_missing`/
  `client_secrets_missing`/`exchange_failed`) — **kein Token, kein Leak**. Der
  Token-Payload wird validiert (Scope muss `youtube.upload` abdecken;
  `client_secret`/`id_token` werden **verworfen**; fehlt `refresh_token` →
  Warnung). `GET /api/youtube/oauth/status` liefert `can_start_auth`/
  `token_present` etc. **Kein Endpoint gibt je Token/Secrets zurück.** Tests
  nutzen ausschließlich Fakes — **kein echter Google-Call**. Offizielle
  Grundlagen + Sicherheitsmodell in
  [`docs/YOUTUBE_PUBLISHING.md`](docs/YOUTUBE_PUBLISHING.md).
- **YouTube echter PRIVATER Upload — Phase 3** (`platforms/youtube_upload.py`):
  ein validierter Draft kann nach **expliziter Bestätigung** (`UPLOAD_PRIVATE`)
  als **privates** Video über die offizielle YouTube Data API (`videos.insert`,
  resumable) hochgeladen werden — hinter `CLIPFORGE_ENABLE_YOUTUBE_UPLOAD=true`.
  **Nur private** (kein public/unlisted), **kein Auto-Posting**. Mit
  **Token-Refresh** (neuer Stand nur ins Keychain), **Idempotenz**
  (`external_post_id`/`succeeded`/`in_progress`/`uncertain` blocken Doppel-
  Uploads; Retry nur nach eindeutigem `failed`) und **transaktionalen**
  Statusübergängen (`published` **nur** bei eindeutigem API-Erfolg). Ein
  **Netzabbruch nach möglichem Remote-Erfolg** wird als **`uncertain`** markiert
  (blockiert blindes Retry — Konto prüfen). Stabile Fehlercodes statt roher
  Google-Exceptions; **keine Tokens/Secrets** in Responses/Logs. Die
  Google-Interaktion ist injizierbar → **Tests laufen ohne echten Upload**.
  Fehlt `google-api-python-client` → `upload_dependency_missing` (sauberer
  Fallback). Details in
  [`docs/YOUTUBE_PUBLISHING.md`](docs/YOUTUBE_PUBLISHING.md) §7d.
- **YouTube Upload-Hardening — Phase 3b** (`platforms/youtube_upload.py`):
  kontrolliertes **Retry/Backoff** (`YouTubeRetryPolicy`) — retriable
  `5xx`/`429`/`rateLimitExceeded`/Netzwerk mit Exponential-Backoff+Jitter auf
  **derselben** resumable Session (kein Duplikat), `quotaExceeded`/permission
  **nicht** retriable, `401` → **maximal ein** erzwungener Token-Refresh. Sleep
  und Jitter sind injizierbar → **Tests schlafen nie real**. **Attempt-History**
  (`publish_attempts`, gekappt, ohne Secrets), ein **`upload-status`**-Endpoint
  (`can_retry`/`requires_manual_check`/`requires_reauth`/Verlauf) und ein
  **Reauth-Flow** in der UI. Ein sicherer **manueller** E2E-Testmodus
  (`scripts/manual_youtube_private_upload.py`) lädt nur bei **zwei** Flags
  (`…_ENABLE_YOUTUBE_UPLOAD` + `…_ENABLE_YOUTUBE_REAL_TEST`) und voller
  Konfiguration echt hoch; sonst **`REAL TEST NOT RUN`** (nie ein vorgetäuschter
  Erfolg). Automatische Tests aktivieren diesen Modus **nie**. Nach `uncertain`:
  **zuerst YouTube Studio prüfen**. Details in
  [`docs/YOUTUBE_PUBLISHING.md`](docs/YOUTUBE_PUBLISHING.md) §7e.
- **YouTube Crash-Safety — Phase 3c** (`platforms/youtube_state.py` +
  `youtube_recovery.py`): eine **persistente State-Machine** (idle/preparing/
  uploading/retry_wait/auth_refresh/reconciling/published/failed/uncertain/
  reauth_required) mit zentral validierten Übergängen (`published` terminal),
  Checkpoint-Feldern und gekappter **Transition-History**. Ein **Startup-Recovery-
  Scanner** erkennt verwaiste (stale) Zustände nach einem Crash und verschiebt
  sie **sicher** — nie ein Blind-Upload: mit `external_post_id` → `reconciling`,
  ohne → `uncertain` + manuelle Prüfung; frische Uploads bleiben unberührt. Die
  **Reconciliation** bestätigt `published` **nur** über die **exakte**
  `external_post_id` (`videos().list(id=…)`) — **keine** Titel-/Namens-Heuristik,
  keine Fake-Bestätigung; Netzwerk/uneindeutig → `uncertain`. Ein **atomarer
  Claim** (`O_EXCL`-Lock + Re-Check nach dem Claim) garantiert bei parallelen
  Publish-Requests **genau einen** tatsächlichen Upload (deterministisch
  getestet: 2 Threads → 1 Uploader-Aufruf). Neuer `POST …/youtube/reconcile`-
  Endpoint prüft nur Remote-Status, startet **nie** einen Upload. Prozessneustart-
  „Resume" wird **nicht** vorgetäuscht (Session-URI wird nicht persistiert; kein
  Lock-URI/Secret in API/DOM/Logs). Details in
  [`docs/YOUTUBE_PUBLISHING.md`](docs/YOUTUBE_PUBLISHING.md) §7f.

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

### Browser-E2E-Smoke-Suite (Playwright)

Kritische UI-Flows werden zusätzlich im **echten Browser** gegen laufendes
Frontend **und** Backend geprüft (Upload → Job → Clip, Re-Render, Publishing
Planner, globale Publishing-Übersicht, YouTube-Readiness/Dry-Run, Recovery- &
Reauth-UI, Negativfälle). Deterministisch/offline: **keine** echten
Google-Calls, **keine** echten Uploads, **keine** Tokens. Jeder Test scheitert
automatisch bei unerwarteten `console.error`/`pageerror`; ein DOM-Secret-Scan
stellt sicher, dass keine Tokens im DOM landen.

```bash
cd web
npm install                    # installiert @playwright/test (Browser nicht neu laden)
npm run test:e2e               # ganze Smoke-Suite (startet Server bei Bedarf selbst)
npm run test:e2e:headed        # mit sichtbarem Browser
npm run test:e2e:smoke         # gleiche Suite, kompakter Report
```

Testdaten sind isoliert (eindeutiges `e2e-smoke`-Präfix, Cleanup am Ende) —
echte/fremde Jobs werden nie angefasst. Details in `docs/WEB.md`.

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
| `CLIPFORGE_BRAND_KIT` | `api/config/brand_kit.json` | Speicherort des lokalen Brand Kits |

> YouTube-/OAuth-/Upload-Flags (alle default sicher/aus) und alle weiteren
> Variablen sind vollständig in [`.env.example`](.env.example) dokumentiert.

---

## Entwicklung

```bash
cd api && export PYTHONPATH=$PWD
python3 tests/test_pipeline_core.py     # schnelle Regressionstests (keine Modelle/Keys nötig)

cd web
npm run test:e2e      # Playwright-Browser-E2E
npx tsc --noEmit      # TypeScript
npm run lint          # ESLint
npm run build         # Produktions-Build

# Voll-QA-Gate vor einem Release:
./scripts/release_check.sh
```

Codeüberblick: `api/clipforge/` (Pipeline-Kern), `api/app.py` (FastAPI-Bridge),
`web/src/` (Next.js-UI), `web/e2e/` (Playwright), `scripts/` (Setup/Start/
Doctor/Release), `docs/` (Konzept + Beta-Dokumentation).

## Bekannte Grenzen

Ehrlich und vollständig mit Auswirkung/Workaround/Status:
[`docs/KNOWN_ISSUES.md`](docs/KNOWN_ISSUES.md). Kurz: echter YouTube-Upload
noch nicht mit realem Konto E2E-verifiziert · local-first (kein Multi-User/Auth,
keine CORS-Härtung für Internet) · kein Public/Unlisted · kein
TikTok/Instagram-Auto-Upload · kein Scheduling-Daemon · kein dynamisches
Reframe · kein Auto-Resume unterbrochener Uploads nach Prozessneustart
(sichere Recovery statt Blind-Retry) · 3 dokumentierte ESLint-Tech-Debt-Punkte.

## Projektstatus (ehrlich)

**Geschlossene Beta / Release Candidate `0.1.0-beta.1`** — bereit für lokales
Beta-Testing. **Kein** produktionsreifes SaaS, **nicht** für Internet-Exposition
gehärtet, **kein** verifizierter Live-YouTube-Upload gegen ein reales Konto.
Der Score ist eine Einschätzung, **keine** Garantie für Reichweite oder Erfolg.
Positionierung/Formulierungen für Portfolio & LinkedIn:
[`docs/PORTFOLIO_LINKEDIN_SNIPPETS.md`](docs/PORTFOLIO_LINKEDIN_SNIPPETS.md).
