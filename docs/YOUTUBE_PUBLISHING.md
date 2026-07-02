# YouTube Publishing — Sicherheitskonzept & Dry-Run (Phase 1)

Stand: 2026-07-02. Dieses Dokument beschreibt, wie ClipForge AI YouTube als
**erste** echte Publishing-Plattform vorbereitet. **In dieser Phase gibt es
keinen echten Upload, kein OAuth und keine Token-Speicherung** — nur einen
Dry-Run, der zeigt, was hochgeladen *würde*.

## 1. Ziel

Fertige Clips sollen später über die **offizielle YouTube Data API** als
YouTube Shorts veröffentlicht werden können — kontrolliert, hinter einem
Feature-Flag, standardmäßig privat und nur mit expliziter Bestätigung. Kein
Auto-Posting, kein Scraping, keine Plattformregel-Umgehung.

## 2. Offizielle API-Realität

Geprüft am 2026-07-02 gegen die offizielle Google-Doku
[`youtube/v3/docs/videos/insert`](https://developers.google.com/youtube/v3/docs/videos/insert)
(abgerufen). Bestätigte Fakten:

- **Upload offiziell möglich:** ja, über `videos.insert` (resumable upload).
- **Setzbare `snippet`-Felder:** `snippet.title`, `snippet.description`,
  `snippet.tags[]`, `snippet.categoryId`.
- **`status.privacyStatus`:** in Code-Beispielen der Doku genannt: `private`,
  `unlisted`, `public`.
- **`status.publishAt`:** existiert; die Doku nennt den Fehler
  `invalidPublishAt` bei ungültiger geplanter Zeit.
- **Quota:** „A call to this method has a quota cost of 1 unit in the Video
  Uploads quota bucket" mit „100 calls per day".
- **Wichtige Einschränkung (unverified apps):** „All videos uploaded via the
  `videos.insert` endpoint from unverified API projects created after
  28 July 2020 will be restricted to private viewing mode" — bis das Projekt
  ein Audit durchläuft.

### Offene Punkte (TODO — vor echtem Upload final gegen offizielle Doku prüfen)

- **`publishAt` erfordert `privacyStatus=private`** — allgemein so dokumentiert,
  hier aber im abgerufenen Doku-Ausschnitt **nicht** explizit bestätigt →
  **TODO verifizieren**, bevor Scheduling gebaut wird.
- **Description-Limit** (Zeichen vs. Bytes, üblicher Wert ~5000) — im
  abgerufenen Ausschnitt nicht genannt → **TODO verifizieren**.
- **Title-Limit** (üblich 100 Zeichen) — hier als `TITLE_MAX=100` im Code
  angenommen → **TODO offiziell bestätigen**.
- **`categoryId`-Gültigkeit** ist regionsabhängig (via `videoCategories.list`)
  → **TODO** dynamisch abfragen statt Default `22` hart zu setzen.
- **Shorts-Erkennung** (Hochformat/Länge/#Shorts) ist nicht Teil von
  `videos.insert` und **nicht offiziell als API-Parameter dokumentiert** →
  keine erfundenen Annahmen.

## 3. Benötigte OAuth-Scopes

Laut Doku für `videos.insert` einer der folgenden Scopes:

- `https://www.googleapis.com/auth/youtube.upload` (minimal für Upload)
- `https://www.googleapis.com/auth/youtube`
- `https://www.googleapis.com/auth/youtube.force-ssl`
- `https://www.googleapis.com/auth/youtubepartner`

ClipForge würde den **minimalen** Scope `youtube.upload` anstreben. OAuth ist
in dieser Phase **nicht** implementiert.

## 4. Privacy-Status

- Erlaubt: `private`, `unlisted`, `public`.
- **Default in ClipForge: `private`.**
- `public` erfordert eine zusätzliche, strengere Bestätigungs-Phrase (s. u.).
- Unverifizierte API-Projekte sind ohnehin auf `private` beschränkt (s. §2).

## 5. Scheduling / `publishAt`

`status.publishAt` existiert offiziell. ClipForge würde `scheduled_at` eines
Drafts als `publishAt` mitgeben. **Bedingung (privacyStatus=private) ist als
TODO markiert** und muss vor dem Bau bestätigt werden. Kein Hintergrund-
Scheduler in ClipForge — `publishAt` überlässt das Timing YouTube selbst.

## 6. Quota-/Limit-TODOs

- Video-Uploads-Bucket: „100 calls per day" (offiziell). **TODO:** prüfen, ob
  das dem Projekt-Default entspricht oder projektspezifisch abweicht.
- Rate-Limit-/Backoff-Verhalten bei `403`/`429` → **TODO** definieren, bevor
  echte Uploads laufen.

## 7. Sicherheitsmodell

Umgesetzt im Adapter `api/clipforge/platforms/youtube.py`:

1. **Default immer Dry-Run.** `dry_run()` löst nie einen Upload aus.
2. **Echte Uploads nur, wenn `CLIPFORGE_ENABLE_YOUTUBE_UPLOAD=true`.**
3. **Default `privacyStatus`: `private`.**
4. **Public nur mit expliziter Bestätigung** (`UPLOAD_PUBLIC`), sonst genügt
   `UPLOAD_PRIVATE` für private/unlisted.
5. **Keine Tokens ins Git-Repo.** (Es werden gar keine Tokens erzeugt.)
6. **Keine Tokens in Logs.** Der Adapter loggt nichts und gibt keine Secrets
   in Responses zurück (nur Dateiname, nie Pfad/Token).
7. **Token-Speicherung nur lokal & dokumentiert** — noch nicht implementiert.
8. **Ohne sicheres Token-Konzept: kein echter Upload.** Genau der Ist-Zustand.
9. **Idempotenz:** hat ein Draft bereits eine `external_post_id`, verweigert
   `publish()` einen erneuten Upload (kein Doppel-Post).
10. **Nachvollziehbarer Draft-Status:** `draft → ready → publishing →
    published | failed`. Solange kein echter Upload passiert, bleibt der
    Status `draft`/`ready` (kein vorgetäuschtes `published`).
11. **`external_post_id` nur bei echtem Erfolg** — heute nie gesetzt.
12. **Fehler sauber, ohne Secrets** (`blocked_reasons`, `message`).

### Token-Konzept (geplant, NICHT implementiert)

- **Option A — keine Speicherung:** Nutzer authentifiziert pro Session manuell.
  Sicherer, aber unbequem. Kein Token liegt je auf der Platte.
- **Option B — lokale Speicherung:** OS-Keychain via `keyring` (falls
  verfügbar); Fallback: keine Speicherung oder verschlüsselte Datei mit
  Passphrase. **Nie Plaintext-Tokens.**
- `keyring` ist **noch keine Dependency** und wird **nicht ungefragt
  installiert**. Entscheidung + Sicherheitsreview stehen vor Phase 2 an.

## 8. Feature Flags & Konfiguration

| Variable | Zweck | Default |
|---|---|---|
| `CLIPFORGE_ENABLE_YOUTUBE_UPLOAD` | schaltet echte Uploads frei (`true`) | `false` |
| `CLIPFORGE_YOUTUBE_CLIENT_SECRETS` | Pfad zur OAuth-Client-Secrets-Datei (nur Existenzprüfung, nie gelesen/geloggt) | leer |
| `CLIPFORGE_YOUTUBE_CATEGORY_ID` | YouTube-Kategorie | `22` |

`credentials_configured` ist genau dann `true`, wenn die Secrets-Datei gesetzt
ist **und** existiert. Der Inhalt wird nicht gelesen.

## 9. Dry-Run Workflow

1. YouTube-Draft im Publishing Planner öffnen → **„YouTube Dry-Run prüfen"**.
2. `POST /api/jobs/{job_id}/publishing/{publishing_id}/youtube/dry-run`.
3. Antwort zeigt: `enabled`, `would_upload`, `video_file` (nur Dateiname),
   `title`, `description`, `hashtags`, `privacy_status`, `scheduled_at`,
   `checks`, `warnings`, `blocked_reasons`, `request_preview` (Metadaten, die
   an `videos.insert` gingen — **ohne** Token, Secrets, Binär-Body).
4. Es passiert **kein** Upload.

## 10. Warum echte Uploads noch deaktiviert sind

- Kein sicheres, reviewtes **Token-Speicher-Konzept** vorhanden (§7).
- OAuth-Flow ist noch nicht gebaut.
- Quota-/Verifizierungs-Themen und mehrere API-Details sind **TODO** (§2, §6).
- Sicherheit vor Bequemlichkeit: ein versehentlicher (ggf. öffentlicher)
  Upload wäre schwer rückgängig zu machen.

Der Publish-Endpoint existiert, ist aber **sicher blockiert**: bei
`CLIPFORGE_ENABLE_YOUTUBE_UPLOAD=false` → `403`; selbst mit Flag+Credentials
+ Bestätigung liefert er `not_implemented` und ändert den Draft-Status nicht.

## 11. Roadmap

| Phase | Inhalt | Status |
|---|---|---|
| 1 | Dry-Run + sicher blockierter Publish-Endpoint | ✅ jetzt |
| 2 | OAuth lokal (Scope `youtube.upload`) + Token-Konzept (Option A/B) | geplant |
| 3 | Privater Upload (`privacyStatus=private`) hinter Flag + Bestätigung | geplant |
| 4 | Geplante Uploads via `publishAt` (nach TODO-Verifizierung) | geplant |
| 5 | Public Upload mit extra Bestätigung (`UPLOAD_PUBLIC`) + Verifizierung | geplant |

## 12. API-Endpoints (Phase 1)

| Endpoint | Zweck |
|---|---|
| `POST /api/jobs/{job_id}/publishing/{publishing_id}/youtube/dry-run` | Upload-Vorschau, kein Upload, keine Secrets |
| `POST /api/jobs/{job_id}/publishing/{publishing_id}/youtube/publish` | sicher blockiert: `403` (Flag aus), `400` (fehlende/falsche Bestätigung), `409` (keine Credentials / nicht validiert), sonst `200 not_implemented` |

Beide Endpoints gelten nur für `platform = youtube_shorts` (sonst `400`) und
sind path-traversal-sicher (unbekannte ID → `404`).
