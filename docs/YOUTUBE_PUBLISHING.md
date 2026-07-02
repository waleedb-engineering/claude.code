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

### Token-Konzept — Entscheidung: Option B (umgesetzt in Phase 2)

- **Option A — keine Speicherung:** Nutzer authentifiziert pro Session manuell.
  Sicherer, aber unbequem. Kein Token liegt je auf der Platte.
- **Option B — lokale Speicherung (gewählt):** OS-Keychain via `keyring`.
  **Kein Plaintext-Fallback.** Ist `keyring` nicht installiert oder kein
  nutzbares Backend vorhanden, meldet die Readiness `token_store_available:
  false` / `token_status: "blocked"` — es wird **nichts** unverschlüsselt
  abgelegt.
- `keyring` steht als **optionale** Dependency in `api/requirements.txt`. Der
  Import ist defensiv: fehlt das Paket, crasht nichts — die Readiness meldet
  einfach „blocked". In dieser Umgebung ist `keyring` nicht installiert, daher
  ist der Token-Store hier korrekt nicht verfügbar.

## 7b. Phase 2 — OAuth-Readiness (umgesetzt)

Phase 2 baut **keinen** echten Upload und **keinen** interaktiven OAuth-Flow.
Sie prüft nur **sicher**, ob ein späterer OAuth/Upload möglich wäre, und
verwaltet die Token-Ablage über das Keychain.

- **`YouTubeTokenStore`** (`platforms/youtube_auth.py`): keyring-gestützt,
  `is_available()`, `has_token()`, `get_status()`, `save_token()` (für Phase 3),
  `delete_token()` (idempotent). Gibt **nie** Token-Werte zurück/loggt sie.
  Status: `blocked` (kein Keychain) · `not_authenticated` (kein Token) ·
  `authenticated` (Token da & lesbar) · `invalid_token` (defekt/korrupt).
- **`YouTubeAdapter.overall_readiness()`**: fasst Feature-Flag, Credentials-
  **Metadaten** (nur `configured`/`exists`/`basename`), Token-Store-Status,
  `required_scope`, `blocked_reasons`, `warnings`, `next_steps` zusammen.
  `can_attempt_upload` ist in Phase 2 **immer `false`**, `upload_status`
  immer `"not_implemented"`.
- **`start_auth()`**: startet **keinen** Browser und kontaktiert Google nicht.
  Bei OAuth-Flag aus → `oauth_disabled`; an → `not_implemented_auth_flow`.
- **`logout()`**: löscht ein evtl. gespeichertes Token über das Keychain
  (idempotent, ohne Leak).

**Was Readiness NICHT bedeutet:** kein „bereit zu veröffentlichen". Selbst bei
`authenticated` + Credentials bleibt der Upload deaktiviert (`not_implemented`).

## 8. Feature Flags & Konfiguration

| Variable | Zweck | Default |
|---|---|---|
| `CLIPFORGE_ENABLE_YOUTUBE_UPLOAD` | schaltet echte Uploads frei (`true`) | `false` |
| `CLIPFORGE_ENABLE_YOUTUBE_OAUTH` | schaltet OAuth-**Aktionen** frei (`auth/start`); der reine Readiness-Check läuft immer | `false` |
| `CLIPFORGE_YOUTUBE_CLIENT_SECRETS` | Pfad zur OAuth-Client-Secrets-Datei (nur Existenzprüfung, nie gelesen/geloggt) | leer |
| `CLIPFORGE_YOUTUBE_TOKEN_SERVICE_NAME` | Keyring-Service-Name für die Token-Ablage | `clipforge-youtube` |
| `CLIPFORGE_YOUTUBE_TOKEN_ACCOUNT` | Keyring-Account-Name | `default` |
| `CLIPFORGE_YOUTUBE_CATEGORY_ID` | YouTube-Kategorie | `22` |

`credentials_configured` ist genau dann `true`, wenn die Secrets-Datei gesetzt
ist **und** existiert. Der Inhalt wird nicht gelesen. **Es gibt keine
ENV-Variable für ein Token** — Tokens leben ausschließlich im Keychain.

### Lokales Entwickler-Setup (Phase 2)

1. `pip install keyring` und ein OS-Keychain-Backend bereitstellen.
2. Google-Cloud-Projekt anlegen, „YouTube Data API v3" aktivieren, OAuth-
   Client (Typ „Desktop/Installed App") erstellen, `client_secrets.json`
   herunterladen.
3. `export CLIPFORGE_YOUTUBE_CLIENT_SECRETS=/pfad/zu/client_secrets.json`.
4. Readiness prüfen (UI-Button oder `GET …/youtube/readiness`).
5. **Token löschen:** UI „YouTube-Token löschen" oder
   `POST …/youtube/auth/logout` (idempotent).

## 9. Dry-Run Workflow

1. YouTube-Draft im Publishing Planner öffnen → **„YouTube Dry-Run prüfen"**.
2. `POST /api/jobs/{job_id}/publishing/{publishing_id}/youtube/dry-run`.
3. Antwort zeigt: `enabled`, `would_upload`, `video_file` (nur Dateiname),
   `title`, `description`, `hashtags`, `privacy_status`, `scheduled_at`,
   `checks`, `warnings`, `blocked_reasons`, `request_preview` (Metadaten, die
   an `videos.insert` gingen — **ohne** Token, Secrets, Binär-Body).
4. Es passiert **kein** Upload.

## 10. Warum echte Uploads noch deaktiviert sind

- Der interaktive **OAuth-Flow ist bewusst nicht gebaut** (Phase 2 = nur
  Readiness + Token-Ablage/-Löschung).
- Quota-/Verifizierungs-Themen und mehrere API-Details sind **TODO** (§2, §6).
- Sicherheit vor Bequemlichkeit: ein versehentlicher (ggf. öffentlicher)
  Upload wäre schwer rückgängig zu machen.

Der Publish-Endpoint existiert, ist aber **sicher blockiert**: bei
`CLIPFORGE_ENABLE_YOUTUBE_UPLOAD=false` → `403`; selbst mit Flag+Credentials
+ Bestätigung liefert er `not_implemented` und ändert den Draft-Status nicht.

### Voraussetzungen für Phase 3 (echter privater Upload)

1. Interaktiver **OAuth-Installed-App-Flow** (Scope `youtube.upload`), Token
   **nur** ins Keychain (`YouTubeTokenStore.save_token`).
2. Token-**Refresh**-Logik + Behandlung von `invalid_token`.
3. Verifizierung der TODO-API-Details aus §2 (u. a. `publishAt`-Bedingung,
   Description-Limit, `categoryId`).
4. Resumable-Upload-Client (`google-api-python-client`/`google-auth`) —
   neue Dependencies, vor Installation begründen.
5. `videos.insert` real aufrufen, `external_post_id` **nur bei Erfolg** setzen,
   Status `publishing → published`/`failed` transaktional, Idempotenz-Guard.
6. Backoff/Retry für `403`/`429`.

## 11. Roadmap

| Phase | Inhalt | Status |
|---|---|---|
| 1 | Dry-Run + sicher blockierter Publish-Endpoint | ✅ fertig |
| 2 | OAuth-**Readiness** + keyring-Token-Ablage/-Löschung (Scope `youtube.upload`, Option B) — **kein echter Upload, kein interaktiver Flow** | ✅ fertig |
| 3 | Interaktiver OAuth-Flow + privater Upload (`privacyStatus=private`) hinter Flag + Bestätigung | geplant |
| 4 | Geplante Uploads via `publishAt` (nach TODO-Verifizierung) | geplant |
| 5 | Public Upload mit extra Bestätigung (`UPLOAD_PUBLIC`) + Verifizierung | geplant |

## 12. API-Endpoints (Phase 1 + 2)

| Endpoint | Zweck |
|---|---|
| `POST …/youtube/dry-run` | Upload-Vorschau, kein Upload, keine Secrets |
| `POST …/youtube/publish` | sicher blockiert: `403` (Flag aus), `400` (fehlende/falsche Bestätigung), `409` (keine Credentials / nicht validiert / bereits hochgeladen), sonst `200 not_implemented` |
| `GET …/youtube/readiness` | sichere Readiness (Flag, Credentials-Metadaten, Token-Store-Status, Scope) — **nie Token/Secrets**, `upload_status: not_implemented` |
| `POST …/youtube/auth/start` | OAuth starten — `oauth_disabled` (Flag aus) bzw. `not_implemented_auth_flow`; kein Browser, kein Token |
| `POST …/youtube/auth/logout` | löscht Token über Keychain (idempotent, ohne Leak) |

(Pfad-Präfix: `/api/jobs/{job_id}/publishing/{publishing_id}`.) Alle Endpoints
gelten nur für `platform = youtube_shorts` (sonst `400`) und sind
path-traversal-sicher (unbekannte ID → `404`). **Kein Endpoint gibt jemals
`access_token`, `refresh_token`, `client_secret` oder Bearer-Werte zurück.**
