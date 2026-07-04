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

## 7c. Phase 2b/2c — OAuth-Flow + echter Token-Exchange (umgesetzt)

Phase 2b macht den OAuth-Flow zu einer **sicheren, testbaren Struktur**
(Consent-URL, State/CSRF, PKCE, Callback). **Phase 2c** ergänzt den **echten
Token-Exchange** über die offizielle Google-Library — **weiterhin ohne jeden
Upload und ohne `videos.insert`**.

### Offizielle OAuth-Grundlagen (Google, abgerufen 2026-07-03)

Geprüft gegen
[`identity/protocols/oauth2/native-app`](https://developers.google.com/identity/protocols/oauth2/native-app):

- **Flow für Desktop/Installed-Apps:** Authorization-Code-Flow
  (`response_type=code`).
- **Auth-Endpoint:** `https://accounts.google.com/o/oauth2/v2/auth`
  (bzw. `auth_uri` aus der client_secrets-Datei).
- **Token-Endpoint:** `https://oauth2.googleapis.com/token` (Phase 2c: der
  echte Exchange läuft hierüber).
- **Redirect-URI für Desktop:** **Loopback-IP** `http://127.0.0.1:port`
  (OOB `urn:ietf:wg:oauth:2.0:oob` ist **deprecated**; Custom-URI-Schemes
  werden für Impersonation-Risiko nicht empfohlen). ClipForge nutzt daher die
  Loopback-Redirect-URI.
- **CSRF:** über den `state`-Parameter (Pflicht) abzusichern.
- **PKCE:** `code_challenge` / `code_challenge_method` sind **empfohlen** —
  ClipForge setzt PKCE mit `S256`.
- **Refresh-Token:** wird Installed-Apps laut Doku **immer** ausgegeben;
  `access_type=offline` wird gesetzt, Speicherung „in a secure, long-lived
  location" → hier ausschließlich das Keychain.

### Echter Token-Exchange (Phase 2c, Google-Library)

Geprüft gegen die offizielle Referenz von **`google-auth-oauthlib`**
([`flow`](https://google-auth-oauthlib.readthedocs.io/en/latest/reference/google_auth_oauthlib.flow.html),
abgerufen 2026-07-03):

- **Library:** `google-auth-oauthlib` stellt die `Flow`-Klasse bereit
  (zusätzlich `google-auth` für die `Credentials`).
- **Ablauf:** `Flow.from_client_secrets_file(path, scopes, redirect_uri=…,
  code_verifier=…)` → `flow.fetch_token(code=…)` → `flow.credentials`
  (`google.oauth2.credentials.Credentials`).
- **PKCE:** der `code_verifier` (aus dem konsumierten `state`) wird an den
  `Flow` übergeben.
- **Refresh-Token:** wird Installed-Apps immer ausgegeben (`access_type=offline`);
  fehlt es dennoch, wird gespeichert **mit** Warnung `no_refresh_token`.
- `google-api-python-client` (für `videos.insert`) wird **bewusst NICHT**
  ergänzt — in dieser Phase findet kein Upload statt.

Der Exchange gibt eine **rohe** Token-Payload zurück, die der Service
sanitisiert/validiert und **nur** über das Keychain speichert. Bei fehlender
Library → `exchange_dependency_missing`; fehlen Secrets → `client_secrets_missing`;
Google-/Netzwerkfehler → `exchange_failed` (**nie** die rohe Exception).

### Modul `platforms/youtube_oauth.py`

- **`YouTubeOAuthConfig`** — `client_secrets_path`, `redirect_uri`, `scopes`
  (nur `youtube.upload`), `enabled`, `state_ttl_seconds`. Nach außen nur
  **Basename** der Secrets-Datei, nie Pfad/Inhalt.
- **`OAuthStateStore`** — lokaler, kurzlebiger `state`-Speicher: TTL,
  **consume-once**, Wiederverwendungs-/Ablauf-Schutz. Enthält **kein Token**;
  hält serverseitig den PKCE-`code_verifier` (taucht **nie** in einer Antwort auf).
- **`YouTubeOAuthService`** —
  - `readiness()` — sicherer Status (siehe `/oauth/status`).
  - `start_auth()` — baut eine **echte Consent-URL** (mit `client_id`, `state`,
    PKCE, `access_type=offline`) und legt einen `state` an. Liest aus der
    client_secrets-Datei **nur `client_id`/`auth_uri`** — **nie das
    `client_secret`**. Öffnet **keinen** Browser, macht **keinen** Netzwerk-Call.
  - `handle_callback(code, state, error)` — prüft `error` → Pflichtfelder →
    `state` (consume-once) → `exchange_code_for_token` → `sanitize` →
    `token_store.save_token`. Speichert bei jedem Fehler **nichts**.
  - `exchange_code_for_token(code, verifier)` — **austauschbar/mockbar** über
    einen injizierten `exchanger`. Produktion: `real_google_token_exchange`
    (offizielle Library). Tests injizieren ein Fake — **nie** ein echter
    Google-Call. Ohne Exchanger blockiert es sauber (`exchange_unavailable`).
  - `save_token()` / `sanitize_token_payload()` — validiert die Payload und
    speichert **nur** über den Keychain-`YouTubeTokenStore` (kein
    Plaintext-Fallback). Regeln: `access_token` ist Pflicht; der Scope muss
    `youtube.upload` (oder kompatibel) enthalten (sonst `invalid_scope`); fehlt
    `refresh_token` → Warnung `no_refresh_token`. **Verworfen werden**
    `client_secret` und `id_token`; behalten werden u. a. `access_token`,
    `refresh_token`, `token_uri`, `client_id`, `scopes`. Unbekannte Felder
    werden verworfen.
- **`real_google_token_exchange(config, code, verifier)`** — der echte
  Google-Exchange (siehe oben). Liest **nie** `client_secret` in die Payload,
  loggt nichts, propagiert **nie** die rohe Exception.

**Auth-Code im Access-Log (Hardening-TODO):** Der OAuth-`code` kommt per
Redirect als **Query-Parameter** an `/api/youtube/oauth/callback` und landet
dadurch in der Request-Zeile des **Webserver-Access-Logs** (z. B. uvicorn).
Die **Anwendung** loggt den Code/das Token nie selbst; dennoch sollte in
Produktion der Access-Log den `code`-Query-Parameter redigieren (Reverse-Proxy/
Log-Filter) — als TODO dokumentiert. Der `code` ist kurzlebig und einmalig.

**Sicherheits-Invarianten (durch Tests abgesichert):** keine `access_token`/
`refresh_token`/`client_secret`/`Bearer`-Werte in Responses/Logs/Exceptions;
`state` ist Pflicht, einmalig, ablaufend; ungültiger/abgelaufener/
wiederverwendeter `state` **speichert nichts**; ungültige Token-Payload
speichert nichts; Path-Traversal im Secrets-Pfad leakt nicht (nur Basename).

## 7d. Phase 3 — Echter PRIVATER Upload (umgesetzt, private-only)

Phase 3 baut den **ersten echten Uploadpfad**: ein validierter YouTube-Draft
kann nach **expliziter Bestätigung** als **privates** Video über die offizielle
YouTube Data API v3 (`videos.insert`, resumable) hochgeladen werden.

**Hart ausgeschlossen:** kein `public`/`unlisted`, kein Auto-Posting, kein
Scheduling, kein TikTok/Instagram. **In Tests passiert nie ein echter Upload**
(Google-Interaktion injiziert/gemockt).

### Offizielle Upload-Grundlagen (Google, abgerufen 2026-07-03)

Geprüft gegen
[`youtube/v3/guides/uploading_a_video`](https://developers.google.com/youtube/v3/guides/uploading_a_video):

- **Methode:** `youtube.videos().insert(part="snippet,status", body={snippet,
  status}, media_body=MediaFileUpload(file, chunksize=-1, resumable=True))`.
- **Resumable-Loop:** `status, response = request.next_chunk()`; **Erfolg** wenn
  `'id' in response` (→ die neue Video-ID).
- **Retriable-Status:** `[500, 502, 503, 504]`; Exponential-Backoff mit Jitter.
- **Library:** `google-api-python-client` (`googleapiclient.discovery.build`,
  `googleapiclient.http.MediaFileUpload`) — defensiv importiert (fehlt sie →
  `upload_dependency_missing`).
- **Fehlerklassen:** `401` (Credentials), `403 quotaExceeded`/`rateLimitExceeded`
  bzw. sonstiges `403` (permission), `429` (Rate-Limit). Unverifizierte Projekte
  laden ohnehin nur **privat** hoch (§2).

### Voraussetzungen für einen echten Upload (ALLE nötig)

`CLIPFORGE_ENABLE_YOUTUBE_UPLOAD=true` · OAuth aktiv · Client-Secrets vorhanden ·
Token-Store (keyring) verfügbar · Token vorhanden & verwendbar · Draft valide ·
MP4 existiert · `platform=youtube_shorts` · `privacy_status=private` ·
exakte Bestätigung `UPLOAD_PRIVATE`. Fehlt eines → sauber blockiert, **kein**
Upload. Standard: Upload **aus**.

### Modul `platforms/youtube_upload.py` — `YouTubeUploadService`

Alle Google-Interaktionen sind **injizierbar** (`credentials_loader`,
`refresher`, `uploader`) → Tests laufen ohne echte Verbindung.

- `readiness(draft)` — alle Gates + Idempotenz (siehe Dry-Run §9-Felder).
- `prepare_credentials()` / `refresh_credentials_if_needed()` — Token aus dem
  Keychain rekonstruieren; **kein** unnötiger Refresh, wenn das Access-Token
  gültig ist; abgelaufen + `refresh_token` → offizieller Refresh, neuer Stand
  **nur** ins Keychain; kein `refresh_token` → `reauth_required`; Refresh-Fehler
  → `token_refresh_failed`. Access-/Refresh-Token werden **nie** geloggt. Das
  `client_secret` wird für den Refresh **frisch aus der Datei** gelesen (nie
  gespeichert/geloggt).
- `build_upload_request(draft)` — `snippet`+`status`, `privacyStatus` **immer**
  `private`.
- `upload_private(...)` — die sichere Transaktion (siehe Idempotenz unten).
- `classify_error(error)` / `sanitize_result(result)` — stabile interne
  Fehlercodes bzw. auf `video_id`/Status reduzierte Antwort. **Nie** rohe
  Google-Exceptions/Secrets.

### Idempotenz (kein Doppel-Upload)

Draft-Felder: `idempotency_state` (`never_attempted`/`in_progress`/`succeeded`/
`failed`/`uncertain`), `external_post_id`, `publish_attempt_id`,
`publish_started_at`/`publish_completed_at`, `publish_attempt_count`,
`last_publish_error`, `publish_platform`.

Regeln: `external_post_id`/`succeeded`/`in_progress`/`uncertain` **blockieren**
einen (weiteren) Upload; nur `never_attempted`/`failed` erlauben (Retry). Jeder
Versuch bekommt eine neue `publish_attempt_id` und erhöht `publish_attempt_count`.
**Kein Fake-Erfolg:** `external_post_id`/`published` werden **nur** bei
eindeutigem API-Erfolg (`'id'` vorhanden) gesetzt.

**`uncertain` ist zentral:** Netzwerkabbruch/Timeout/5xx **nach** möglichem
Remote-Erfolg — oder eine erfolgreiche Antwort, die lokal nicht gespeichert
werden konnte — wird als `uncertain` markiert (nicht blind `failed`) und
**blockiert** ein automatisches Retry. Der Nutzer muss sein YouTube-Konto prüfen.

### Sichere Statusübergänge (transaktional)

`ready → publishing` (Idempotenz `in_progress`, **vor** dem Call geschrieben, damit
ein Absturz mittendrin als `in_progress` geblockt bleibt) → bei eindeutigem
Erfolg `publishing → published` (`external_post_id` Pflicht) · bei eindeutigem
Fehler `publishing → failed` · bei unklarem Ergebnis `failed` **mit**
`idempotency_state=uncertain`. Der Trusted Writer `publishing.apply_publish_state`
schreibt atomar (tmp+rename) und ist der einzige Weg, die reservierten Status zu
setzen.

### Interne Fehlercodes (nie rohe Google-Exceptions)

`upload_disabled`, `oauth_not_ready`, `token_missing`, `reauth_required`,
`token_refresh_failed`, `upload_dependency_missing`, `invalid_draft`,
`mp4_missing`, `already_uploaded`, `upload_in_progress`, `upload_state_uncertain`,
`invalid_privacy_status`, `confirmation_required`, `quota_exceeded`,
`rate_limited`, `permission_denied`, `invalid_credentials`, `upload_failed`,
`upload_result_uncertain`.

## 7e. Phase 3b — Hardening: Retry/Backoff, Recovery, Real-Testmodus

### Retry-Policy (`YouTubeRetryPolicy`, testbar)

Kontrolliertes, **injizierbares** Retry (kein `time.sleep` in Unit-Tests, Jitter
injizierbar). Kategorien: `retryable` · `non_retryable` · `auth_refreshable` ·
`uncertain`.

| Fehler | Kategorie | Verhalten |
|---|---|---|
| `500/502/503/504`, Netzwerk/Timeout | retryable | Backoff + `next_chunk()` auf **derselben** resumable Session |
| `403 rateLimitExceeded`, `429` | retryable | Backoff (gemäß Policy) |
| `403 quotaExceeded` | non_retryable | **kein** aggressiver Retry → `quota_exceeded` (failed) |
| `403 forbidden` (permission), `400`, `404` | non_retryable | sofort abbrechen |
| `401` | auth_refreshable | **maximal ein** erzwungener Token-Refresh + neue Session; danach `invalid_credentials`/`reauth_required` |
| Netzabbruch **nach** möglichem Commit / Retries erschöpft | uncertain | `uncertain` — **kein** blindes Retry |

**Backoff:** exponentiell `initial · multiplier^(n−1)`, gedeckelt auf `max_delay`,
mit optionalem Full-Jitter (`random()·delay`) — offizielle Empfehlung
(Resumable-Upload-Guide, Prompt 27 §7d). `max_attempts` begrenzt die Retries.

**Quellen/TODO:** `[500,502,503,504]`+Netzwerk-Retry und Backoff/Jitter sind
offiziell (Guide). `quotaExceeded`/`badRequest`/`forbidden`/`notFound` = permanent
(docs/errors). `rateLimitExceeded`/`429`-Retry und `401`-Refresh-once sind
**Policy** (in der Fehler-Referenz nicht explizit → als TODO markiert, Standard-
Praxis).

### Resumable-Recovery — Grenzen (ehrlich)

- **Innerhalb** eines Versuchs: retriable Fehler → erneuter `next_chunk()` auf
  **derselben** Session (die google-Library kennt den Offset → **kein Duplikat**).
- Bei `401` wird die Session **einmal** mit frischen Credentials neu gebaut
  (bis dahin wurden keine Chunks akzeptiert → sicher).
- **Prozessneustart-Recovery ist NICHT implementiert** und wird **nicht
  vorgetäuscht**: ein Draft in `in_progress` bleibt nach Neustart geblockt und
  verlangt manuelle Prüfung. Der (sensible) resumable Session-URI wird **nicht**
  persistiert/zurückgegeben.
- **Fortschritt** (`bytes_uploaded`/`total_bytes`/`progress_percent`) wird
  best-effort im Draft (`upload_progress`) erfasst — sichtbar nur bei granularem
  Chunking (`CLIPFORGE_YOUTUBE_UPLOAD_CHUNK_BYTES` > 0) und paralleler Abfrage
  von `upload-status`. Mit Default `-1` (ein Request) gibt es keinen
  Zwischenfortschritt.

### Attempt-History (`publish_attempts`, additiv)

Jeder `upload_private`-Aufruf hängt einen Eintrag an (gekappt auf die letzten
20): `attempt_id`, `started_at`, `completed_at`, `outcome`
(`succeeded`/`failed`/`uncertain`), `error_code`, `retry_count`. **Keine**
Tokens/Header/rohe Exceptions/Session-URIs. Die bestehenden Felder
(`publish_attempt_count`, `publish_attempt_id`, `last_publish_error`,
`idempotency_state`) bleiben kompatibel.

### Reauth-Flow

Bei `token_missing`/`reauth_required`/`invalid_credentials` meldet
`upload-status` `requires_reauth: true`; die UI zeigt „YouTube erneut verbinden"
(Link zu `oauth/start`), lädt Readiness neu — **kein** Token im Browser, **kein**
automatischer Browser-Login.

### Sicherer manueller Real-Testmodus

`scripts/manual_youtube_private_upload.py` ist der **einzige** Weg, einen echten
Upload auszulösen — und nur, wenn **beide** Flags an sind
(`CLIPFORGE_ENABLE_YOUTUBE_UPLOAD=true` **und**
`CLIPFORGE_ENABLE_YOUTUBE_REAL_TEST=true`) sowie OAuth/Token/Keyring/Draft/MP4
bereit. Ablauf: Voraussetzungen prüfen → Draft anzeigen → interaktive
`UPLOAD_PRIVATE`-Bestätigung → **nur privat** hochladen → `external_post_id`
anzeigen → Anleitung zur manuellen Studio-Prüfung. **Kein** Auto-Löschen, **kein**
Public-Schalten. Fehlen Voraussetzungen/echte Credentials → Ausgabe
**`REAL TEST NOT RUN`** (Exit 2, **nie** als Erfolg). **Automatische Tests setzen
das Real-Test-Flag nie und lösen nie einen echten Upload aus.**

### Nach `uncertain`: ZUERST YouTube Studio prüfen

Ein `uncertain`-Zustand blockiert jedes automatische Retry. **Bevor** erneut
hochgeladen wird, im YouTube Studio prüfen, ob bereits ein (privates) Video
angelegt wurde — sonst droht ein Duplikat.

## 7f. Phase 3c — Persistente State-Machine, Crash-Recovery & Race-Schutz

### Zustände & Übergänge (`platforms/youtube_state.py`)

Zentrale, persistente Upload-State-Machine (kein verstreuter String-Vergleich):

`idle · preparing · uploading · retry_wait · auth_refresh · reconciling ·
published · failed · uncertain · reauth_required`.

`published` ist **terminal** (geschützt). Erlaubte Übergänge sind zentral in
`ALLOWED_TRANSITIONS` definiert; `transition()` validiert, setzt Checkpoint-
Felder und schreibt eine **gekappte** `state_transition_history` (ohne Secrets).
**`uncertain` erlaubt KEINEN direkten Re-Upload** — nur `→ reconciling`. Legacy-
Felder (`status`/`idempotency_state`) werden weiter konsistent gepflegt.

Persistente Checkpoints (additiv, rückwärtskompatibel, ohne Secrets):
`upload_state`, `upload_started_at`, `last_upload_activity_at`,
`last_transition_at`, `retry_count`, `current_attempt`, `last_error_category`,
`last_error_code`, `requires_manual_check`, `requires_reauth`,
`reconciliation_status`, `reconciliation_checked_at`, `state_transition_history`.

### Crash-Fenster-Modell (Phase 1 — pro Fenster begründet)

| Fenster | Lage | Bewertung |
|---|---|---|
| A | vor Session-Erstellung (`preparing`) | kein Remote-Effekt → **auto restart safe** (nach Recovery `uncertain`, konservativ; Nutzer kann neu starten) |
| B | Session erstellt, kein Chunk | kein finalisiertes Video → **reconciliation** (ohne ID → `uncertain`) |
| C | während Chunk (`uploading`) | resumable, aber Commit-Status unklar → **reconciliation required**; ohne eindeutige ID → `uncertain` |
| D | Remote fertig, lokal nicht `published` | **reconciliation required** über die (evtl. bereits als Checkpoint gespeicherte) `external_post_id` |
| E | `external_post_id` lokal gespeichert (`reconciling`), Publish nicht finalisiert | **reconciliation** bestätigt die ID → `published` |
| F | Credential-Refresh (`auth_refresh`) | kein akzeptierter Chunk → nach Recovery `uncertain`/Reauth (**manual/ reauth**) |
| G | Retry-Wait (`retry_wait`) | kein Remote-Commit → **reconciliation**/`uncertain` |
| H | Neustart bei `uncertain` | **manual check required** — nie automatischer Re-Upload |

**Kein Fenster** wird als „auto resume über Prozessneustart" behauptet: eine
laufende resumable Session wird **nicht** über den Neustart hinweg fortgesetzt
(der Session-URI wird bewusst **nicht** persistiert). Recovery bedeutet
**reconcile oder uncertain**, nie Blind-Upload.

### Startup-Recovery-Scanner (`platforms/youtube_recovery.py`)

Beim Backend-Start (`run_youtube_startup_recovery`, gated per
`CLIPFORGE_YOUTUBE_RECOVERY_SCAN_ENABLED`) werden **verwaiste** (stale) aktive
Zustände erkannt (`ACTIVE_STATES` + Inaktivität >
`CLIPFORGE_YOUTUBE_STALE_UPLOAD_SECONDS`) und **sicher** verschoben:

- stale **mit** `external_post_id` → `reconciling` (+ optional sofort reconcile),
- stale **ohne** `external_post_id` → `uncertain` + `requires_manual_check`,
- **frische** Uploads bleiben unberührt,
- stale Lock-Dateien werden entfernt.

Der Scanner startet **NIE** einen Upload.

### Reconciliation (nur eindeutige ID, keine Heuristik)

Der `ReconciliationService` prüft **ausschließlich** die exakte
`external_post_id` über einen injizierbaren Verifier
(`videos().list(id=…)`):

- Video mit **exakt** dieser ID vorhanden → `published`.
- Remote **eindeutig** nicht vorhanden → `failed` (Retry sicher, ID verworfen).
- Netzwerk/uneindeutig/kein Verifier → `uncertain` + `requires_manual_check`.
- **Keine** `external_post_id` → `uncertain` (Verifier wird gar nicht gerufen).

**Verboten & nicht implementiert:** Titel-/Caption-/Dateinamen-Suche, „ähnliche
Videos", Fake-Reconciliation. `published` **nur** bei eindeutiger Bestätigung.

### Atomarer Claim / Race-Schutz

Der Publish-Start setzt eine **atomare Lock-Datei** (`O_CREAT|O_EXCL`,
`<publishing_id>.uploadlock`). Genau **ein** Request gewinnt; parallele Requests
werden sofort mit `upload_in_progress` geblockt. Nach dem Claim wird der Draft
**frisch** nachgeladen und die Idempotenz erneut geprüft (schließt das
sequentielle Race-Fenster). Ergebnis (getestet, deterministisch): **zwei
gleichzeitige Requests → genau ein tatsächlicher Uploader-Aufruf.** Der Lock-Pfad
erscheint **nie** in API/Response/Frontend.

## 8. Feature Flags & Konfiguration

| Variable | Zweck | Default |
|---|---|---|
| `CLIPFORGE_ENABLE_YOUTUBE_UPLOAD` | schaltet echte Uploads frei (`true`) | `false` |
| `CLIPFORGE_ENABLE_YOUTUBE_OAUTH` | schaltet OAuth-**Aktionen** frei (`auth/start`); der reine Readiness-Check läuft immer | `false` |
| `CLIPFORGE_YOUTUBE_CLIENT_SECRETS` | Pfad zur OAuth-Client-Secrets-Datei (nur Existenzprüfung, nie gelesen/geloggt) | leer |
| `CLIPFORGE_YOUTUBE_TOKEN_SERVICE_NAME` | Keyring-Service-Name für die Token-Ablage | `clipforge-youtube` |
| `CLIPFORGE_YOUTUBE_TOKEN_ACCOUNT` | Keyring-Account-Name | `default` |
| `CLIPFORGE_YOUTUBE_CATEGORY_ID` | YouTube-Kategorie | `22` |
| `CLIPFORGE_YOUTUBE_REDIRECT_URI` | Loopback-Redirect-URI des lokalen OAuth-Callbacks (kein Secret) | `http://127.0.0.1:8000/api/youtube/oauth/callback` |
| `CLIPFORGE_YOUTUBE_OAUTH_STATE_TTL_SECONDS` | Lebensdauer eines kurzlebigen OAuth-`state` (CSRF), Sekunden | `600` |
| `CLIPFORGE_ENABLE_YOUTUBE_REAL_TEST` | **zweites** Flag; nur mit ihm **und** dem Upload-Flag darf das manuelle Skript echt hochladen. Automatische Tests setzen es nie. | `false` |
| `CLIPFORGE_YOUTUBE_UPLOAD_MAX_ATTEMPTS` | max. Upload-Versuche (Retry-Policy) | `5` |
| `CLIPFORGE_YOUTUBE_UPLOAD_INITIAL_DELAY` | Backoff-Startverzögerung (Sekunden) | `1.0` |
| `CLIPFORGE_YOUTUBE_UPLOAD_MAX_DELAY` | Backoff-Deckel (Sekunden) | `32.0` |
| `CLIPFORGE_YOUTUBE_UPLOAD_CHUNK_BYTES` | resumable Chunk-Größe (`-1` = ein Request; >0 für Fortschritt/Resume, Vielfaches von 256 KB) | `-1` |
| `CLIPFORGE_YOUTUBE_RECOVERY_SCAN_ENABLED` | Startup-Recovery-Scanner an/aus (verschiebt stale Zustände sicher, nie Upload) | `true` |
| `CLIPFORGE_YOUTUBE_STALE_UPLOAD_SECONDS` | ab wann ein aktiver Upload-Zustand als verwaist gilt | `900` |
| `CLIPFORGE_YOUTUBE_RECONCILIATION_TIMEOUT_SECONDS` | Timeout eines Reconcile-Remote-Checks | `60` |

`credentials_configured` ist genau dann `true`, wenn die Secrets-Datei gesetzt
ist **und** existiert. Der Inhalt wird nur für den `client_id`/Token-Exchange
gelesen — **nie** das `client_secret` in Responses/Logs. **Es gibt keine
ENV-Variable für ein Token** — Tokens leben ausschließlich im Keychain.

**Dependencies für den Token-Exchange:** `google-auth` + `google-auth-oauthlib`
(in `api/requirements.txt`, OPTIONAL & defensiv importiert). Fehlen sie, meldet
der Callback sauber `exchange_dependency_missing` (kein Crash, kein Token).
`google-api-python-client` wird **nicht** benötigt (kein Upload).

### Lokales Entwickler-Setup

1. `pip install keyring google-auth google-auth-oauthlib google-api-python-client`
   und ein OS-Keychain-Backend bereitstellen.
2. Google-Cloud-Projekt anlegen, „YouTube Data API v3" aktivieren, OAuth-
   Client (Typ „Desktop/Installed App") erstellen, `client_secrets.json`
   herunterladen. Redirect-URI = `CLIPFORGE_YOUTUBE_REDIRECT_URI` autorisieren.
3. `export CLIPFORGE_YOUTUBE_CLIENT_SECRETS=/pfad/zu/client_secrets.json` und
   `export CLIPFORGE_ENABLE_YOUTUBE_OAUTH=true`.
4. Readiness prüfen (UI-Button oder `GET …/youtube/readiness` / `GET
   /api/youtube/oauth/status`).
5. **Verbinden:** UI „YouTube verbinden vorbereiten" oder
   `POST /api/youtube/oauth/start` → liefert eine **Consent-URL**. Diese
   **manuell** im Browser öffnen (es wird kein Browser automatisch geöffnet).
   Nach dem Login leitet Google **automatisch** auf
   `GET /api/youtube/oauth/callback` zurück, der den Code **echt** gegen ein
   Token tauscht und es **nur** im Keychain speichert (`token_stored: true`).
6. **Echter privater Test-Upload (Phase 3):** einen **validierten** Draft
   wählen, `export CLIPFORGE_ENABLE_YOUTUBE_UPLOAD=true` setzen, in der UI die
   Checkbox bestätigen, `UPLOAD_PRIVATE` eintippen und „Privat zu YouTube
   hochladen" klicken (oder `POST …/youtube/publish` mit
   `{confirm:"UPLOAD_PRIVATE", privacy_status:"private"}`). Das Video ist
   danach **privat** in deinem Konto. Bei `uncertain` **erst das Konto prüfen**,
   bevor erneut versucht wird.
7. **Token löschen:** UI „YouTube-Token löschen" oder
   `POST …/youtube/auth/logout` (idempotent).

## 9. Dry-Run Workflow

1. YouTube-Draft im Publishing Planner öffnen → **„YouTube Dry-Run prüfen"**.
2. `POST /api/jobs/{job_id}/publishing/{publishing_id}/youtube/dry-run`.
3. Antwort zeigt: `enabled`, `would_upload`, `video_file` (nur Dateiname),
   `title`, `description`, `hashtags`, `privacy_status`, `scheduled_at`,
   `checks`, `warnings`, `blocked_reasons`, `request_preview` (Metadaten, die
   an `videos.insert` gingen — **ohne** Token, Secrets, Binär-Body).
4. Es passiert **kein** Upload.

## 10. Was echt geht — und was bewusst (noch) NICHT

- **Echter privater Upload (Phase 3): gebaut.** `videos.insert`, `privacy
  Status=private`, hinter Feature-Flag + `UPLOAD_PRIVATE`-Bestätigung +
  Idempotenz + Token-Refresh (§7d).
- **Bewusst NICHT:** `public`/`unlisted` (→ `invalid_privacy_status`), Auto-
  Posting, Scheduling-Daemon, TikTok/Instagram.
- Standard bleibt **Upload aus** (`CLIPFORGE_ENABLE_YOUTUBE_UPLOAD=false`) —
  Sicherheit vor Bequemlichkeit.
- Quota-/Verifizierungs-Themen und mehrere API-Details bleiben **TODO** (§2, §6).

Der Publish-Endpoint gibt **immer HTTP 200** mit strukturiertem Ergebnis zurück
(`success`/`error_code`/`idempotency_state`); bei fehlenden Voraussetzungen
passiert **kein** Upload und der Draft-Status bleibt unverändert.

### Nächste Phasen (nach dem privaten Upload)

Der private Upload inkl. Token-Refresh, Idempotenz (`uncertain`-Schutz) und
transaktionalen Statusübergängen ist gebaut. Offen bleibt:

1. **Aktiver Backoff/Retry** bei retriablen 5xx/429 (aktuell werden diese als
   `uncertain`/`rate_limited` klassifiziert und **nicht** blind wiederholt).
2. Verifizierung der TODO-API-Details aus §2 (u. a. `publishAt`-Bedingung,
   Description-Limit, `categoryId`) → geplante Uploads via `publishAt`.
3. Behandlung von `invalid_token`/Reauth-Flows in der UI.
4. Public/Unlisted mit zusätzlicher Bestätigung + ggf. API-Audit.
5. Access-Log-Hardening: `code`-Query-Parameter am Callback redigieren (§7c);
   analog sollte der Reverse-Proxy Upload-Requests nicht mitloggen.

## 11. Roadmap

| Phase | Inhalt | Status |
|---|---|---|
| 1 | Dry-Run + sicher blockierter Publish-Endpoint | ✅ fertig |
| 2 | OAuth-**Readiness** + keyring-Token-Ablage/-Löschung (Scope `youtube.upload`, Option B) — **kein echter Upload, kein interaktiver Flow** | ✅ fertig |
| 2b | OAuth-**Flow-Skelett**: Consent-URL (State/CSRF + PKCE), Callback, sichere Token-Speicherung über Keychain | ✅ fertig |
| 2c | **Echter** Google-Token-Exchange (offizielle Library `google-auth-oauthlib`, PKCE), Token nur im Keychain — **weiterhin kein Upload** | ✅ fertig |
| 3 | **Echter PRIVATER Upload** (`videos.insert`, `privacyStatus=private`) hinter Flag + `UPLOAD_PRIVATE`-Bestätigung + Token-Refresh + Idempotenz (`uncertain`-Schutz) — **nur private, kein public/unlisted, kein Auto-Posting** | ✅ fertig |
| 3b | **Hardening**: kontrolliertes Retry/Backoff (`YouTubeRetryPolicy`), 401→ein Refresh, Attempt-History, `upload-status`-Endpoint, Reauth-Flow, sicherer manueller Real-Testmodus (`REAL TEST NOT RUN` ohne Credentials) | ✅ fertig |
| 3c | **Crash-Safety**: persistente State-Machine (10 Zustände + Transitions), Startup-Recovery-Scanner, ID-basierte Reconciliation (keine Heuristik), atomarer Claim/Race-Schutz (2 Requests → 1 Upload), Transition-History, `reconcile`-Endpoint | ✅ fertig |
| 4 | Geplante Uploads via `publishAt` (nach TODO-Verifizierung) | geplant |
| 5 | Public/Unlisted Upload mit extra Bestätigung + Verifizierung | geplant |

## 12. API-Endpoints (Phase 1 + 2)

| Endpoint | Zweck |
|---|---|
| `POST …/youtube/dry-run` | Upload-Vorschau **inkl. `upload_readiness`** (Gates + Idempotenz), kein Upload, keine Secrets |
| `POST …/youtube/publish` | **Echter PRIVATER Upload** (mit Retry/Backoff). Body `{confirm:"UPLOAD_PRIVATE", privacy_status:"private"}`. Immer **HTTP 200** mit `success`, `error_code`, `status`, `external_post_id`, `privacy_status:"private"`, `idempotency_state`, `retry_count`, `published_at`, `message`, `no_secrets:true`. `published`/`external_post_id` **nur** bei eindeutigem Erfolg; public/unlisted → `invalid_privacy_status`; Flag aus → `upload_disabled`. **Nie Token/Secrets.** |
| `GET …/youtube/upload-status` | Status/Recovery: `state`, `is_stale`, `idempotency_state`, `publish_attempt_count`, `current_attempt`, `retry_count`, `last_publish_error`, `last_error_category`, `external_post_id_present`, `can_retry`, `can_reconcile`, `requires_manual_check`, `requires_reauth`, `last_activity_at`, `reconciliation_status`, `upload_progress`, `attempt_history_summary`, `transition_history_summary`, `no_secrets:true`. Löst nichts aus. **Nie Token/Secrets/Session-URIs.** |
| `POST …/youtube/reconcile` | Prüft NUR den Remote-Status einer bekannten `external_post_id` (exakte ID, keine Heuristik) und korrigiert den lokalen Zustand → `published` (eindeutig bestätigt) / `failed` (eindeutig fehlend) / `uncertain` (sonst). **Startet NIE einen Upload.** Antwort = aktualisierter upload-status. |
| `GET …/youtube/readiness` | sichere OAuth-Readiness (Flag, Credentials-Metadaten, Token-Store-Status, Scope) — **nie Token/Secrets** |
| `POST …/youtube/auth/start` | Draft-Legacy: `oauth_disabled` (Flag aus) bzw. `not_implemented_auth_flow`; kein Browser, kein Token |
| `POST …/youtube/auth/logout` | löscht Token über Keychain (idempotent, ohne Leak) |

(Pfad-Präfix: `/api/jobs/{job_id}/publishing/{publishing_id}`.) Diese Endpoints
gelten nur für `platform = youtube_shorts` (sonst `400`) und sind
path-traversal-sicher (unbekannte ID → `404`). Die Draft-Readiness nutzt
denselben OAuth-Status wie das Flow-Skelett (siehe unten).

### OAuth-Flow (Phase 2b/2c, app-global — nicht draft-gebunden)

| Endpoint | Zweck |
|---|---|
| `GET /api/youtube/oauth/status` | Sicherer OAuth-Status: `oauth_enabled`, `client_secrets_configured`, `client_secrets_basename`, `redirect_uri`, `scopes`, `token_store_available`, `token_present`, `token_status`, `can_start_auth`, `can_attempt_upload:false`, `blocked_reasons`, `warnings`, `no_secrets:true`. **Nie** Token/Secrets. |
| `POST /api/youtube/oauth/start` | Erzeugt Consent-URL + kurzlebigen `state`: `enabled`, `auth_url` (optional), `state_created`, `expires_at`, `blocked_reasons`, `warnings`, `no_secrets:true`. Kein Browser, kein Netzwerk-Call. Bei fehlenden Voraussetzungen (`oauth_disabled` / `client_secrets_missing` / `token_store_unavailable` / `client_secrets_unreadable`) → **kein** `auth_url`, klare `blocked_reasons`. |
| `GET /api/youtube/oauth/callback?code&state&error` | Verarbeitet den Callback: `success`, `token_stored`, `token_status`, `message`, `next_step`, `reason`, `warnings`, `no_secrets:true`. `error` → sichere 200; fehlender/ungültiger/abgelaufener/wiederverwendeter `state` → **400**, nichts gespeichert; gültiger `state` → **echter** Token-Exchange (Google-Library) → Token **nur** über Keychain. Degrade-Reasons (sichere 200, kein Token): `exchange_dependency_missing` (Library fehlt), `client_secrets_missing`, `exchange_failed` (Google-Fehler), `invalid_scope` (kein Upload-Scope), `invalid_token_payload`. Fehlt `refresh_token` → gespeichert **mit** `warnings:["no_refresh_token"]`. |

**Kein Endpoint gibt jemals `access_token`, `refresh_token`, `client_secret`,
`id_token` oder Bearer-Werte zurück.** Der `client_id` erscheint (per
OAuth-Design) in der `auth_url`; das `client_secret` wird **nie** in eine
Response/Payload/ein Log gelesen. Der OAuth-`code` kommt als Query-Parameter am
Callback an (Access-Log-Hardening-TODO, siehe §7c).
