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

`credentials_configured` ist genau dann `true`, wenn die Secrets-Datei gesetzt
ist **und** existiert. Der Inhalt wird nur für den `client_id`/Token-Exchange
gelesen — **nie** das `client_secret` in Responses/Logs. **Es gibt keine
ENV-Variable für ein Token** — Tokens leben ausschließlich im Keychain.

**Dependencies für den Token-Exchange:** `google-auth` + `google-auth-oauthlib`
(in `api/requirements.txt`, OPTIONAL & defensiv importiert). Fehlen sie, meldet
der Callback sauber `exchange_dependency_missing` (kein Crash, kein Token).
`google-api-python-client` wird **nicht** benötigt (kein Upload).

### Lokales Entwickler-Setup

1. `pip install keyring google-auth google-auth-oauthlib` und ein
   OS-Keychain-Backend bereitstellen.
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
   **Upload bleibt trotzdem deaktiviert.**
6. **Token löschen:** UI „YouTube-Token löschen" oder
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

- Der **OAuth-Flow inklusive echtem Token-Exchange** existiert (Phase 2b/2c:
  Consent-URL, State/CSRF+PKCE, Callback, echter Google-Exchange, sichere
  Keychain-Ablage). Ein gültiges Token kann also im Keychain liegen — **der
  Upload (`videos.insert`) ist trotzdem bewusst NICHT gebaut** (Phase 3).
- Quota-/Verifizierungs-Themen und mehrere API-Details sind **TODO** (§2, §6).
- Sicherheit vor Bequemlichkeit: ein versehentlicher (ggf. öffentlicher)
  Upload wäre schwer rückgängig zu machen.

Der Publish-Endpoint existiert, ist aber **sicher blockiert**: bei
`CLIPFORGE_ENABLE_YOUTUBE_UPLOAD=false` → `403`; selbst mit Flag+Credentials
+ Bestätigung liefert er `not_implemented` und ändert den Draft-Status nicht.

### Voraussetzungen für Phase 3 (echter privater Upload)

Der **echte Token-Exchange** (offizielle Library gegen
`https://oauth2.googleapis.com/token`, inkl. PKCE + Keychain-Ablage) ist **seit
Phase 2c erledigt**. Für einen echten Upload fehlen noch:

1. Token-**Refresh**-Logik + Behandlung von `invalid_token`.
2. Verifizierung der TODO-API-Details aus §2 (u. a. `publishAt`-Bedingung,
   Description-Limit, `categoryId`).
3. Resumable-Upload-Client (`google-api-python-client`) — **neue** Dependency,
   vor Installation begründen (bewusst NICHT in dieser Phase ergänzt).
4. `videos.insert` real aufrufen, `external_post_id` **nur bei Erfolg** setzen,
   Status `publishing → published`/`failed` transaktional, Idempotenz-Guard.
5. Backoff/Retry für `403`/`429`, Quota-/Rate-Limit-Verhalten.
6. Access-Log-Hardening: `code`-Query-Parameter am Callback redigieren (§7c).

## 11. Roadmap

| Phase | Inhalt | Status |
|---|---|---|
| 1 | Dry-Run + sicher blockierter Publish-Endpoint | ✅ fertig |
| 2 | OAuth-**Readiness** + keyring-Token-Ablage/-Löschung (Scope `youtube.upload`, Option B) — **kein echter Upload, kein interaktiver Flow** | ✅ fertig |
| 2b | OAuth-**Flow-Skelett**: Consent-URL (State/CSRF + PKCE), Callback, sichere Token-Speicherung über Keychain | ✅ fertig |
| 2c | **Echter** Google-Token-Exchange (offizielle Library `google-auth-oauthlib`, PKCE), Token nur im Keychain — **weiterhin kein Upload, kein `videos.insert`** | ✅ fertig |
| 3 | Privater Upload (`videos.insert`, `privacyStatus=private`) hinter Flag + Bestätigung + Token-Refresh + Idempotenz | geplant |
| 4 | Geplante Uploads via `publishAt` (nach TODO-Verifizierung) | geplant |
| 5 | Public Upload mit extra Bestätigung (`UPLOAD_PUBLIC`) + Verifizierung | geplant |

## 12. API-Endpoints (Phase 1 + 2)

| Endpoint | Zweck |
|---|---|
| `POST …/youtube/dry-run` | Upload-Vorschau, kein Upload, keine Secrets |
| `POST …/youtube/publish` | sicher blockiert: `403` (Flag aus), `400` (fehlende/falsche Bestätigung), `409` (keine Credentials / nicht validiert / bereits hochgeladen), sonst `200 not_implemented` |
| `GET …/youtube/readiness` | sichere Readiness (Flag, Credentials-Metadaten, Token-Store-Status, Scope) — **nie Token/Secrets**, `upload_status: not_implemented` |
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
