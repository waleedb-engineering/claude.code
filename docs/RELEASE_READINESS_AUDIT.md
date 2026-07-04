# ClipForge AI — Release Readiness Audit

Stand: 2026-07-04 · Audit-Basis: Commit `1362d6b` (Prompt 29) · Fixes in diesem
Audit-Commit. Methode: beweisorientiert — jede Aussage ist durch einen Test,
ein Repro-Skript oder eine Code-Stelle belegt. Keine Schönfärberei.

## 1. Executive Summary

Das System ist ein **local-first** Werkzeug (eine Person, ein Rechner): Pipeline
(CLI) + FastAPI-Bridge + Next.js-UI. Kern-Pipeline, Job-Verwaltung, Publishing
Planner und der YouTube-Private-Upload-Pfad sind funktional vollständig und
durch **300 automatisierte Backend-Tests (20 Dateien, alle grün)** abgedeckt.
Im Audit wurden **6 reale Probleme gefunden und behoben** (Details §14/§15),
darunter zwei echte Race-/Integritätslücken (Draft-Delete während Upload,
Reconcile auf frischem aktivem Upload) und eine Token-Resurrection nach Logout.
Kein Critical-Fund. Verbleibende Risiken sind dokumentiert (§16).

**Einstufung: C — CLOSED BETA READY** (Begründung §17).

## 2. Architekturübersicht

**Entry Points:** CLI (`clipforge/cli.py` → `run_pipeline`) · HTTP
(`api/app.py`, FastAPI, ~45 Endpoints) · UI (`web/`, Next.js 16, ruft nur die
API).

**Module & Dependency-Richtung** (keine Zyklen; app.py importiert clipforge,
nie umgekehrt):

- Pipeline-Kern: `pipeline.py` → `transcribe/segmenter/analyzer/scoring/
  silence/reframe/captions/render/content/brand_kit`
- Jobs: `jobs.py` (Registry, ThreadPool max_workers=2, kooperatives Cancel,
  Restore beim Start)
- Publishing: `publishing.py` (Draft-CRUD, Validierung, Pack) →
  `platforms/` (youtube.py Dry-Run · youtube_auth.py Keychain-Store ·
  youtube_oauth.py OAuth/PKCE/Exchange · youtube_upload.py Upload+Retry ·
  youtube_state.py State-Machine · youtube_recovery.py Scanner/Reconcile)

**Persistenz:** `jobs/<id>/` (job.json, clips.json, transcript.json, input.*,
clip_*.mp4, manual_exports/, publishing/*.json inkl. attempt-/transition-
history), `config/brand_kit.json`, Tokens **nur** im OS-Keychain.

**Background Execution:** ThreadPool (2 Worker, env-konfigurierbar), Cancel
kooperativ an Checkpoints, kein Auto-Resume nach Neustart (bewusst), Job-Restore
+ YouTube-Recovery-Scanner beim Start (beide crash-fest, überspringen Defektes).

**Externe Grenzen:** ffmpeg/ffprobe (Pflicht für Render, degradiert bei ffprobe-
Absenz), faster-whisper (lokal), Anthropic (optional, Fallback regelbasiert),
Google OAuth/YouTube API (optional, defensive Imports, in Tests immer gemockt),
OS-Keychain (optional, ohne → „blocked", kein Plaintext-Fallback).

## 3. Risk Matrix

| Bereich | Risiko | Schwere | Wahrsch. | geschützt | Handlungsbedarf |
|---|---|---|---|---|---|
| Publishing | Doppel-Upload (parallel/sequentiell) | Hoch | mittel | ✅ O_EXCL-Claim + Idempotenz (Race-Test: 2 Threads → 1 Upload) | keiner |
| Publishing | Draft-Delete während Upload → verwaistes Remote-Video | Hoch | niedrig | ❌ war offen | **FIX-1 (409-Guard)** |
| Publishing | Reconcile markiert frischen aktiven Upload als uncertain | Mittel | niedrig | ❌ war offen | **FIX-6 (409-Guard)** |
| OAuth | Logout während Refresh → Token-Resurrection | Mittel | niedrig | ❌ war offen (Repro) | **FIX-2** |
| Persistenz | Korrupte History crasht Status-Endpoint (500) | Mittel | niedrig | ❌ war offen (Repro: AttributeError) | **FIX-3** |
| Persistenz | Crash mitten im JSON-Write → korrupte Draft-/job.json | Mittel | niedrig | teilw. (nur apply_publish_state atomar) | **FIX-4 (tmp+rename)** |
| Security | Path Traversal (IDs/Downloads/Delete) | Hoch | — | ✅ Regex-IDs + realpath-Checks, getestet (publishing/oauth/upload/delete-Suiten) | keiner |
| Security | Secret-Leak in Responses/Logs/Repo | Hoch | — | ✅ Sentinel-Tests in 4 Suiten + Repo-Scan 0 Treffer | keiner |
| Security | CORS `*` | Niedrig (local-first, kein Auth) | — | ⚠ bewusster Dev-Default | dokumentiert (§16) |
| Jobs | Delete/Cancel-Races | Mittel | mittel | ✅ processing-Schutz, kooperatives Cancel, getestet | keiner |
| Jobs | Job-Delete (force) während Draft-Upload | Mittel | sehr niedrig | teilw. (Draft-Guard greift beim Draft-Endpoint, nicht bei Job-force-delete) | dokumentiert (§16) |
| Pipeline | A/V-/Caption-Drift bei Silence-Removal | Hoch | — | ✅ Remap getestet (test_silence: 10) | keiner |
| Analyzer | Bounds/Score-Verletzungen | Mittel | — | ✅ Property-Check: 12 Clips, 0 Verletzungen; 38 Tests | keiner |

## 4. Security Audit

- **Path Traversal:** `job_id` (Registry-`UnsafeJobPath` + realpath),
  `publishing_id` (`^[a-f0-9]{12}$` + realpath-Prefix-Check),
  `manual_export_id` (Whitelist-Pfadauflösung). HTTP-Traversal-Tests existieren
  in test_delete/test_publishing/test_youtube_upload/test_youtube_recovery.
  Client-Secrets-Pfad: nur Existenzprüfung + Basename nach außen (getestet).
  Brand-Kit-Pfad: fester Ort, env-übersteuerbar, kein User-Input im Pfad.
- **Secret Leakage:** Repo-Scan (Muster: ya29., AIza…, sk-ant-, GOCSPX-,
  PRIVATE KEY, Bearer-Werte): **0 echte Treffer** (einziger Match:
  `sk-ant-...`-Platzhalter in README-Doku). Session-URI wird nirgends
  persistiert/ausgegeben (Code-Scan leer). Sentinel-No-Leak-Tests in
  oauth/upload/recovery/audit-Suiten. `client_secret` wird nur für den Refresh
  aus der Datei gelesen, nie gespeichert/geloggt; `id_token` wird verworfen.
- **Input Validation:** Upload-Endung-Whitelist + Größen-/Batch-Limits (413,
  getestet), Plattform-/Status-/Caption-Style-/Reframe-Whitelists,
  privacy_status hart auf `private`, Confirm-Phrase exakt.
- **ZIP:** Erzeugungsseite nutzt ausschließlich `os.path.basename`-Arcnames
  bzw. feste Präfixe (`auto_clips/`, `manual_exports/`, `data/`) — neuer Test
  `test_zip_exports_have_safe_arcnames` beweist: keine absoluten Pfade, kein
  `..`, keine Laufwerksnamen (exports.zip, all-exports.zip, pack.zip).
- **HTTP:** Fehlerdetails sind kuratierte Strings (keine Stacktraces/Secrets);
  CORS `*` als bewusster local-first-Default (kein Auth, kein Cookie) —
  Restrisiko dokumentiert.

## 5. Race/Concurrency Audit (14 Szenarien)

| # | Szenario | Befund |
|---|---|---|
| 1 | 2 parallele Uploads gleicher Datei | 2 getrennte Jobs by design — kein Konflikt |
| 2 | Batch-Upload | pro Datei eigener Job, per-Datei-Fehler (getestet) |
| 3 | Cancel während Processing | kooperativ an Checkpoints (9 Tests) |
| 4/5 | Delete/Force-Delete während Processing | 409 bzw. explizit force (13 Tests) |
| 6 | Re-render parallel | getrennte Export-IDs (Zeitstempel), Auto-Clips unangetastet |
| 7 | Manual-Export-Delete während Pack-ZIP | ZIP liest einmalig; fehlende Datei → Fehler statt Teil-ZIP; kein Integritätsschaden |
| 8 | Draft-Edit während Validation | letzter Write gewinnt (Draft-JSON), kein reservierter Status setzbar — akzeptiert |
| 9 | **Draft-Delete während Upload** | **war offen → FIX-1**: 409 solange upload_state aktiv |
| 10 | 2 Publish-Requests | O_EXCL-Claim + Re-Check: deterministischer Thread-Test → exakt 1 Uploader-Call |
| 11 | Recovery-Scanner während Publish | Scanner fasst nur STALE aktive Zustände an; frische unberührt (getestet) |
| 12 | **Reconcile während Upload** | **war offen → FIX-6**: 409 auf frischem aktivem Upload |
| 13 | **Logout während Refresh** | **war offen → FIX-2**: kein Persist mehr, wenn Store leer |
| 14 | Job-Restore beim Start | idempotent, überspringt Defektes (9 Tests) |

## 6. Crash/Persistence Audit

- **Atomare Writes:** vor dem Audit nur `apply_publish_state` (tmp+rename).
  **FIX-4**: jetzt auch alle 4 Draft-Writer (create/update/duplicate/validate
  via `_write_draft_atomic`) und `jobs.py:_persist` (job.json). Beweis-Test:
  fehlgeschlagene Serialisierung lässt Original intakt; keine .tmp-Reste.
  clips.json/Sidecars bleiben plain (Crash dort ⇒ Job failed/Export fehlt —
  Leser überspringen korrupte Dateien, kein Crash; akzeptiertes Restrisiko).
- Explizite Fragen: (1) job.json↔FS-Drift → Restore rekonstruiert aus Dateien,
  degradiert zu interrupted/incomplete. (2) clips.json→fehlende MP4s →
  `_resolve_auto_clip`-Fallbacks + mp4_exists-Checks. (3) Sidecar ohne MP4 →
  `available:false`, kein Crash. (4) Draft-Quelle weg → Validation blockt.
  (5) published ohne external_post_id → unmöglich (Code + Tests: „no id → nie
  published"). (6) external_post_id ohne published → möglich als
  reconciling-Checkpoint/uncertain — gewollt (Fenster E), Reconcile löst auf.
  (7) Scanner + terminale/ruhende Zustände → **neuer Beweis-Test**: published/
  failed/uncertain bleiben auch bei uraltem Timestamp unberührt.
  (8) korrupte History → **war Crash (Repro AttributeError) → FIX-3**, jetzt
  200 + `corrupt_entry`-Marker (End-to-End-Test).

## 7. Video Pipeline Audit

Silence-Remap inkl. Caption-Timing-Remap getestet (10 Tests); Captions: ASS-
Escaping (Braces/Backslash), Unicode/Emoji, WrapStyle-Safe-Area (7 Tests);
Reframe: kein Gesicht → Center-Fallback, Portrait/Landscape/9:16 (6 Tests);
kein ffprobe → `format_9_16: null` (nicht blockierend); kein ffmpeg →
`FFmpegNotFound` sauber; No-Speech/Gaps-Fixtures vorhanden (nowords.json,
gaps_transcript.json). Kein A/V-Drift-Befund in den Remap-Tests. Grenzen:
statischer Smart-Crop (dokumentiert), sehr lange Videos nur durch Upload-Limit
begrenzt. Keine kritischen Funde → keine Änderungen.

## 8. Analyzer Audit

Property-Check über alle 4 Fixtures (de/en/mixed/weak): **12 Clips, 0
Verletzungen** (0≤start<end≤duration, Scores 0–100, keine Duplikate in Top-N).
LLM-Pfad: Re-Rank nur per Index, unbekannte Indizes verworfen, Markdown-/
Broken-JSON-Parsing, Timeout→Fallback — alles in test_analyzer (38) abgedeckt.
Kalibrierung dokumentiert (ANALYZER_CALIBRATION.md). Keine Fixes nötig.

## 9. Publishing Audit

Kette Planner→Draft→Validation→Overview→Duplication→Dry-Run→OAuth→Exchange→
Refresh→Upload→Retry→State-Machine→Recovery→Reconcile vollständig getestet
(38+38+43+23 Tests). Double-Publish ✅ · uncertain-Retry blockiert ✅ ·
publish-after-delete → 404 ✅ · **Draft-Delete während Upload → FIX-1** ·
**Logout während Upload/Refresh → FIX-2** · stale Lock wird vom Scanner
entfernt ✅ · Scanner-Interferenz ausgeschlossen (nur stale) ✅ ·
**Reconcile während frischem Upload → FIX-6** · published ohne ID unmöglich ✅ ·
external_post_id ist eine öffentliche Video-ID (kein Secret; Video ist privat)
· Attempt-/Transition-History gekappt, feld-gewhitelistet, **FIX-3** macht sie
korruptionsfest. PRIVATE-only unverändert.

## 10. API Audit (Matrix, Kurzform)

| Endpoint(-Gruppe) | Happy | Validation | Conflict | NotFound | Security |
|---|---|---|---|---|---|
| POST /api/jobs, /batch | 200 | 400 Typ / 413 Größe+Batch | — | — | Endungs-Whitelist |
| GET jobs/{id}, clips, transcript, files | 200 | — | — | 404 | ID-validiert |
| POST cancel · DELETE job · bulk-delete | 200 | 400 confirm | 409 processing | 404 | realpath, nie außerhalb jobs/ |
| downloads/previews/ZIPs | 200/206 | — | — | 404 | Basename-Arcnames (Test) |
| rerender · manual-exports | 200 | 400 | — | 404 | export_id-Whitelist |
| publishing CRUD/validate/pack/duplicate | 200 | 400 | **409 aktiver Upload (neu)** | 404 | ID-Regex+realpath |
| youtube dry-run/readiness/auth | 200 | 400 non-yt | — | 404 | keine Secrets (Sentinel-Tests) |
| oauth start/callback/status | 200 | 400 state | — | — | state consume-once, PKCE |
| youtube publish | 200 strukturiert (`success`/`error_code`, bewusst kein Fehler-HTTP — dokumentierter Contract, kein Fake-Success da `success:false`) | — | via error_code | 404 | nie Token |
| upload-status · reconcile | 200 | — | **409 frischer aktiver Upload (neu)** | 404 | nie Session-URI |

Keine Fake-200-Erfolge: `success:false` + stabiler `error_code` ist explizit.

## 11. Frontend Audit

Code-Audit aller 19 Flows: Loading-/Busy-States und Doppelklick-Sperren in
Upload/Editor/Publish-Panels vorhanden; Polling 2–4s mit cleanup; uncertain-
Warnung exakt und ohne Retry-Button; Reauth-Button ohne Auto-Browser; keine
Tokens/Session-URIs im DOM (Backend liefert sie nie); alte Clips ohne
analyzer-v2-Felder kompatibel (optionale Typen). Behoben: 3 unescapte
JSX-Anführungszeichen (Lint-Fehler). Bekannte Schuld: 3×
`react-hooks/set-state-in-effect` (Load-on-Mount-Muster; funktional korrekt,
Build grün — Refactor wäre reines Regressionsrisiko). **Kein Playwright-Setup
vorhanden** — es gibt keine Browser-E2E-Tests; verifiziert wird über tsc,
ESLint, `next build` und die HTTP-Testsuite (ehrliche Lücke, §16).

## 12. Dependency Audit

Python (11 Pakete): alle begründet; optional-degradierend verifiziert durch
Tests: keyring fehlt→`blocked`, google-auth-oauthlib fehlt→
`exchange_dependency_missing`, google-api-python-client fehlt→
`upload_dependency_missing`, opencv fehlt→Center-Fallback, anthropic ohne
Key→regelbasiert. Frontend: 3 Runtime- + 8 Dev-Pakete, keine ungenutzten,
Build ohne Warnungen. Keine Upgrades vorgenommen (bewusst).

## 13. Test Coverage Matrix

| Bereich | Unit | Integr. | HTTP | Race | Recovery | Security | Browser-E2E |
|---|---|---|---|---|---|---|---|
| Pipeline/Silence/Captions/Reframe | ✅ | ✅ | — | — | — | — | ❌ |
| Jobs/Restore/Cancel/Delete/Storage | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ Traversal | ❌ |
| Analyzer | ✅ | ✅ | — | — | — | — | ❌ |
| Publishing Planner | ✅ | ✅ | ✅ | — | — | ✅ | ❌ |
| OAuth/Token | ✅ | ✅ | ✅ | — | — | ✅ Sentinel | ❌ |
| Upload/Retry/StateMachine | ✅ | ✅ | ✅ | ✅ 2→1 | ✅ | ✅ | ❌ |
| Recovery/Reconcile | ✅ | ✅ | ✅ | ✅ | ✅ A/B/C | ✅ | ❌ |
| Audit-Fixes | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ ZIP | ❌ |

**Exakte Zahlen: 20 Testdateien, 300 Einzeltests, 0 Failures** (davon neu in
diesem Audit: test_audit_fixes.py mit 10).

## 14. Gefundene Probleme

| ID | Schwere | Problem (Beleg) |
|---|---|---|
| F1 | High | DELETE eines Drafts mit aktivem Upload erlaubt → Remote-Video würde verwaisen (Repro: ext_post_id ohne persistierbaren Zustand) |
| F2 | Medium | Logout während Token-Refresh: `_persist_refreshed` schrieb Access-Token zurück (Repro: Resurrection JA) |
| F3 | Medium | Nicht-Dict-Einträge in publish_attempts/transition_history → AttributeError → HTTP 500 (Repro) |
| F4 | Medium | Draft-CRUD + job.json nicht atomar geschrieben (Crash-Fenster → korruptes JSON) |
| F5 | Low | Dead Code: wirkungslose Schleife in `_http_reason` |
| F6 | Medium | POST /reconcile auf frischem aktivem Upload markiert laufenden Upload als uncertain |
| F7 | Low | 6 ESLint-Fehler (3 unescapte Entities, 3 set-state-in-effect) |

## 15. Behobene Probleme

F1 (409-Guard im Delete-Endpoint) · F2 (kein Persist bei leerem Store) ·
F3 (korruptionsfeste History-Sanitizer + List-Guards) · F4 (`_write_draft_atomic`
+ atomares job.json) · F5 (entfernt) · F6 (409-Guard im Reconcile-Endpoint) ·
F7 teilweise (3 Entities gefixt). Jeder Fix hat einen Test in
`api/tests/test_audit_fixes.py` (10 Tests).

## 16. Nicht behobene Risiken (bewusst, dokumentiert)

1. **CORS `*` / kein Auth** — local-first-Design; vor jedem Netz-Deployment
   zwingend zu ändern.
2. **Job-force-delete während aktivem Draft-Upload** — Guard existiert nur am
   Draft-Endpoint; force-Job-Delete löscht den Ordner trotzdem (erfordert
   bewusstes force + zeitgleichen Upload; Cross-Modul-Guard wäre Kopplung
   jobs↔publishing).
3. **Keine Browser-E2E (Playwright)** — UI nur durch tsc/ESLint/Build + HTTP-
   Tests abgesichert.
4. **3× `set-state-in-effect`-Lint** — funktional unkritisch, Refactor vertagt.
5. **clips.json/Sidecar-Writes nicht atomar** — Leser sind korruptionstolerant;
   Restrisiko: Verlust einzelner Metadaten bei Crash im Write.
6. **Kein Session-Resume über Prozessneustart** (bewusst, §7f
   YOUTUBE_PUBLISHING.md) — Recovery = Reconcile oder uncertain.

## 17. Beta Readiness Decision

**Einstufung: C — CLOSED BETA READY.**

Begründung: Kern-Funktionalität vollständig und mit 300 grünen Tests belegt;
Sicherheits-Invarianten (kein Secret-Leak, Traversal-fest, PRIVATE-only,
kein Fake-Success) sind durch Tests bewiesen; Race-/Crash-Pfade des
Upload-Systems sind deterministisch getestet (2→1-Race, Recovery A/B/C).
**Nicht D (PUBLIC BETA)**, weil: kein Auth/CORS-Härtung (Netz-Exposition
unzulässig), keine Browser-E2E-Abdeckung, und der echte YouTube-Upload bisher
nur über den Mock-Pfad + manuellen Real-Testmodus verifiziert ist (ein echter
manueller E2E-Lauf mit realem Google-Konto steht aus — `REAL TEST NOT RUN`
in dieser Umgebung, ehrlich dokumentiert). **Mehr als B**, weil alle für eine
geschlossene, lokal installierende Testgruppe relevanten Integritäts- und
Sicherheitspfade getestet sind und Datenverlust-Szenarien behandelt werden.
