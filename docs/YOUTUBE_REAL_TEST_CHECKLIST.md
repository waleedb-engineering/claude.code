# YouTube Real-Test Checklist — Private Upload (0.1.0-beta.1)

**Zweck:** Der echte, ausschließlich **private** YouTube-Upload-Pfad ist
implementiert und mit gemocktem Google-Client getestet (Idempotenz,
Retry/Backoff, Recovery, Reconciliation, Race-Schutz). Er wurde **noch nicht**
mit einem echten Google-Konto End-to-End verifiziert. Diese Checkliste ist der
Runbook für genau diesen einen manuellen Test.

**Diese Datei enthält keine echten Tokens, Client-Secrets oder Konto-Daten und
darf nie welche enthalten.** Die technischen Hintergründe (Zustandsmaschine,
Fehlercodes, Sicherheitsmodell) stehen in
[`docs/YOUTUBE_PUBLISHING.md`](YOUTUBE_PUBLISHING.md) — hier wird nur der
operative Ablauf beschrieben, nicht dupliziert.

> **Sicherheits-Invarianten (im Code erzwungen, nicht optional):**
> `ALLOWED_PRIVACY = "private"` in `api/clipforge/platforms/youtube_upload.py`.
> Es gibt **keinen** Code-Pfad für `public` oder `unlisted`. Ein anderer Wert
> als `private` wird mit `invalid_privacy_status` abgelehnt. Kein Auto-Posting,
> kein Scheduling-Daemon, keine automatische Löschung.

---

## 0. Wer sollte diesen Test durchführen?

Eine Person mit:

- einem **eigenen, nicht-produktiven** Google-/YouTube-Konto (Test-Konto
  empfohlen — **niemals** ein Konto mit wichtigen, öffentlichen Inhalten),
- einem eigenen Google-Cloud-Projekt mit aktivierter *YouTube Data API v3*,
- der Bereitschaft, **ein** kurzes, unwichtiges Testvideo privat hochzuladen.

Das hochgeladene Video bleibt **privat** (nur der Kontoinhaber sieht es) und
kann danach jederzeit manuell im YouTube Studio gelöscht werden.

---

## 1. Voraussetzungen

| # | Voraussetzung | Prüfen |
|---|---|---|
| 1 | ClipForge läuft lokal | `./scripts/start_local.sh` |
| 2 | Ein fertiger Job mit mindestens einem Clip | Web-UI: Upload → Job `completed` |
| 3 | Ein `youtube_shorts`-Publishing-Draft, validiert | Web-UI: „Publishing vorbereiten" → „Prüfen" (gültig) |
| 4 | Google-Cloud-Projekt mit *YouTube Data API v3* | Google Cloud Console |
| 5 | OAuth-Client-Secrets-Datei (Desktop-App-Typ) | lokal, **nie committen** |
| 6 | `keyring` verfügbar (OS-Keychain) | `python3 scripts/clipforge_doctor.py` |

---

## 2. Google-OAuth-Setup (einmalig)

1. Google Cloud Console → neues (oder Test-)Projekt.
2. *YouTube Data API v3* aktivieren.
3. OAuth-Consent-Screen konfigurieren (Nutzertyp *External*, im
   **Testing**-Modus reicht das eigene Konto als Testnutzer).
4. OAuth-Client-ID vom Typ **Desktop-App** erstellen → JSON herunterladen.
   Diese Datei ist das `client_secrets.json`.
5. Die Datei **außerhalb** des Repos ablegen (z. B. `~/clipforge-secrets/`).
   Sie ist per `.gitignore`-Konvention ohnehin nicht vorgesehen, aber lege sie
   sicherheitshalber nicht in den Projektordner.

**Erlaubter Scope:** ausschließlich
`https://www.googleapis.com/auth/youtube.upload` (minimal für `videos.insert`).
Keine breiteren Scopes anfordern.

> **Test-Konto-Hinweis:** Ein unverifiziertes OAuth-Projekt im Testing-Modus
> kann Uploads ohnehin auf `private` beschränken und die Token-Gültigkeit
> begrenzen — für diesen Test genau richtig.

---

## 3. Feature-Flags & Verbindung

Der echte Upload braucht **zwei** unabhängige Flags plus einen verbundenen
Token. Ohne alle drei bleibt der Pfad blockiert.

```bash
export CLIPFORGE_ENABLE_YOUTUBE_OAUTH=true
export CLIPFORGE_ENABLE_YOUTUBE_UPLOAD=true
export CLIPFORGE_ENABLE_YOUTUBE_REAL_TEST=true
export CLIPFORGE_YOUTUBE_CLIENT_SECRETS=/pfad/zu/client_secrets.json
```

**YouTube verbinden (OAuth-Consent, manuell):**

1. In der Web-UI beim Draft → „YouTube-Readiness prüfen" → „YouTube verbinden
   vorbereiten". ClipForge erzeugt eine **Consent-URL** (öffnet **keinen**
   Browser automatisch, zeigt **kein** Token an).
2. Die URL manuell im Browser öffnen, mit dem Test-Konto anmelden, Zugriff für
   `youtube.upload` gewähren.
3. Google leitet auf den lokalen Callback zurück; ClipForge tauscht den Code
   über die offizielle Google-Library gegen ein Token und legt es **nur** im
   OS-Keychain ab (nie als Datei, nie im DOM, nie im Log).
4. Erneut „YouTube-Readiness prüfen" → `token_present: true`,
   `token_status: authenticated`.

---

## 4. Dry-Run ZUERST (Pflicht)

**Immer** vor dem echten Upload:

1. Beim Draft → „YouTube Dry-Run prüfen".
2. Erwartung: strukturierte Vorschau (Titel, Beschreibung, `privacy: private`,
   technische Checks). **Kein** Upload wird ausgelöst.
3. Sicherstellen: Titel/Beschreibung/Datei sind wie gewünscht, `privacy` zeigt
   `private`.

Erst wenn der Dry-Run plausibel ist, weiter zu Schritt 5.

---

## 5. Echten Upload bewusst auslösen

Der Upload läuft **nur** über das dedizierte manuelle Skript — die
automatisierte Testsuite ruft es nie auf und setzt die Flags nie.

```bash
# aus dem Repo-Root, mit den Flags aus Schritt 3 gesetzt:
python3 scripts/manual_youtube_private_upload.py <job_id> <publishing_id>
```

Das Skript:

1. prüft alle Flag-/OAuth-/Token-/Draft-/MP4-Voraussetzungen (sonst
   `REAL TEST NOT RUN`, Exit 2),
2. zeigt Draft, Datei, `privacy: private` und den Idempotenz-Zustand,
3. verlangt die **exakte** interaktive Eingabe `UPLOAD_PRIVATE`,
4. führt erst dann den echten, privaten `videos.insert`-Upload aus.

`job_id` und `publishing_id` findest du in der Web-UI-URL des Drafts bzw. über
`GET /api/publishing`.

---

## 6. Erwartetes Verhalten

| Situation | Erwartung |
|---|---|
| Erfolg | Skript: `✓ ECHTER UPLOAD ERFOLGREICH (privat)`, zeigt `external_post_id`, Exit 0 |
| Voraussetzung fehlt | `REAL TEST NOT RUN: <Grund>`, Exit 2, **kein** Upload |
| Bestätigung falsch | `REAL TEST NOT RUN`, Exit 2 |
| Bereits hochgeladen | Idempotenz greift: kein zweiter Upload |
| Google-Fehler (4xx/5xx) | interner Fehlercode (nie rohe Google-Exception), sauberer Abbruch |
| Ergebnis unklar | `idempotency_state: uncertain` → **kein** Auto-Retry, Studio-Prüfung nötig |

---

## 7. Retry / Recovery / Reconciliation / Race — was zu beobachten ist

- **Retry/Backoff:** Bei retriablen Fehlern (z. B. 5xx) wiederholt der Upload
  mit kontrolliertem Backoff; `publish_attempt_count`/`retry_count` in
  `GET …/youtube/upload-status` steigen nachvollziehbar.
- **Recovery nach Prozess-Absturz:** Stirbt das Backend **während** eines
  Uploads, wird der Zustand beim Neustart als *stale* erkannt und markiert —
  **kein** automatischer Blind-Retry. In der UI: „Upload-Status prüfen".
- **Reconciliation:** Ist eine `external_post_id` bekannt, gleicht
  „Upload-Status prüfen" nur den **Remote-Status** ab (kein neuer Upload) und
  korrigiert den lokalen Zustand.
- **Race-Schutz:** Zwei gleichzeitige Upload-Anforderungen führen durch den
  atomaren Claim zu **genau einem** echten Upload (im Mock-Test 2→1
  verifiziert; hier real gegenprüfen, falls provozierbar).

---

## 8. Nach einem abgebrochenen / unklaren Upload

**Zuerst YouTube Studio prüfen, bevor irgendetwas erneut versucht wird.**

1. https://studio.youtube.com → „Inhalte".
2. Prüfen, ob bereits ein Video (mit dem Test-Titel) angelegt wurde.
3. Falls ja: **nicht** erneut hochladen (Duplikat-Gefahr) — den lokalen
   Zustand per „Upload-Status prüfen"/Reconciliation abgleichen.
4. Falls nein: Ursache (Fehlercode/`message`) beheben, dann erneut.

---

## 9. Verifizieren, dass das Video privat ist

1. https://studio.youtube.com → „Inhalte" → das hochgeladene Video suchen.
2. Sichtbarkeits-Spalte muss **„Privat"** zeigen.
3. Optional: in einem **abgemeldeten** Browser / Inkognito die
   `watch?v=<external_post_id>`-URL öffnen → darf **nicht** abspielbar sein
   („Video ist privat").

---

## 10. Logs sammeln (für einen Bug-Report)

Unbedenklich zu teilen (enthalten per Design **keine** Secrets):

- Terminal-Ausgabe des Skripts (`manual_youtube_private_upload.py`).
- `GET …/youtube/upload-status`-Antwort (`no_secrets: true`).
- Backend-Log `./.clipforge-backend.log` (der Adapter loggt keine
  Tokens/Header/Session-URIs).

**Niemals teilen:** `client_secrets.json`, den Keychain-Eintrag, irgendetwas
mit `ya29.` / `1//` / `GOCSPX-` / `Bearer `.

---

## 11. Bewertung: PASS / BLOCKED / FAIL

**PASS** — alle folgenden Punkte erfüllt:

- Skript meldet echten Erfolg (Exit 0) mit `external_post_id`.
- Video erscheint im Studio als **Privat**.
- Ein zweiter Aufruf lädt **nicht** erneut hoch (Idempotenz).
- `upload-status` enthält keine Secrets/Session-URI.
- Kein Video wurde öffentlich/unlisted geschaltet.

**BLOCKED** — Test konnte nicht bis zum echten Upload durchgeführt werden:

- Eine Voraussetzung fehlt (Flags, OAuth, Token, Keyring, gültiger Draft) →
  `REAL TEST NOT RUN`. Kein Fehler des Upload-Pfads, sondern fehlende
  Umgebung. Ursache dokumentieren.

**FAIL** — echter Fehler im Upload-Pfad:

- Upload behauptet Erfolg, aber im Studio ist kein privates Video, **oder**
- Video ist **nicht** privat (öffentlich/unlisted), **oder**
- Idempotenz greift nicht (Doppel-Upload), **oder**
- Secrets/Token/Session-URI erscheinen in Response/Log/DOM, **oder**
- Absturz ohne sauberen Fehlercode.

Jeder FAIL ist ein Release-Blocker und gehört als Issue mit den Logs aus
§10 gemeldet.

---

## 12. Ergebnis-Vorlage

```
YOUTUBE REAL-TEST — 0.1.0-beta.1
Datum:            ____
Tester:           ____
Konto-Typ:        Test-Konto (nicht produktiv)  [ ]
Dry-Run zuerst:   [ ]
Ergebnis:         PASS / BLOCKED / FAIL
external_post_id: ____ (falls Upload lief)
Privat verifiziert im Studio: [ ]
Idempotenz (2. Aufruf kein Re-Upload): [ ]
Keine Secrets in Logs/DOM: [ ]
Notizen / Fehlercode:  ____
```
