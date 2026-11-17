# Local API Security

ClipForge läuft lokal: Backend auf `127.0.0.1:8000`, Oberfläche (Next.js) auf
`127.0.0.1:3000`. Ohne Schutz könnte jede Webseite, die du im selben Browser
öffnest, Requests an das Backend schicken — Projekte löschen, Renders starten,
kostenpflichtige Provider auslösen oder API-Schlüssel überschreiben.

## Was geschützt ist

1. **CORS nur für lokale Oberflächen.** Erlaubt sind
   `http://127.0.0.1:3000` und `http://localhost:3000`. Es gibt kein `*`.
2. **Token-Pflicht für jede Mutation.** Alle Requests außer `GET`, `HEAD`,
   `OPTIONS` unter `/api/` brauchen den Header `X-ClipForge-Token`.
   Fehlt er: `401 token_missing`. Ist er falsch: `403 token_invalid`. Der
   Vergleich ist timing-sicher.
3. **Fremde Herkunft wird immer abgewiesen.** Hat ein mutierender Request einen
   `Origin`-Header, der nicht erlaubt ist, kommt `403 origin_not_allowed` —
   auch mit gültigem Token.
4. **Token nur für die lokale Oberfläche.** `GET /api/session` gibt das Token
   nur heraus, wenn kein fremder `Origin` gesetzt ist und der `Host`-Header
   lokal ist (Schutz vor DNS-Rebinding).

Das betrifft unter anderem Uploads, Löschen, Rendern, Publishing, YouTube-OAuth
und -Upload, Brand Kit, Automationen und API-Schlüssel.

Lesende Endpunkte (`GET`) brauchen kein Token, damit `<video>`-Vorschauen und
Downloads funktionieren. Fremde Webseiten können deren Antworten wegen der
CORS-Regel nicht auslesen.

## Wo das Token herkommt

Beim Start lädt das Backend das Token in dieser Reihenfolge:

1. Umgebungsvariable `CLIPFORGE_API_TOKEN` (mindestens 16 Zeichen)
2. Datei `api/.clipforge_api_token` (Rechte `0600`, Pfad änderbar mit
   `CLIPFORGE_API_TOKEN_FILE`)
3. sonst wird ein neues Token erzeugt und in dieser Datei abgelegt

Das Token wird nie geloggt und steht in keiner Projektdatei. Die Datei ist in
`.gitignore` eingetragen.

- **Oberfläche:** holt das Token selbst über `GET /api/session` und hält es nur
  im Arbeitsspeicher. Du musst nichts einrichten.
- **CLI:** nutzt `CLIPFORGE_API_TOKEN` oder fragt das lokale Backend.
- **Eigene Skripte:** Token aus der Datei lesen und als Header mitsenden.

```bash
curl -X POST http://127.0.0.1:8000/api/studio/projects -H "Content-Type: application/json" -H "X-ClipForge-Token: $(cat api/.clipforge_api_token)" -d '{"workflow":"script","script":"Erster Satz. Zweiter Satz."}'
```

## Konfiguration

| Variable | Standard | Zweck |
|---|---|---|
| `CLIPFORGE_ALLOWED_ORIGINS` | – | weitere erlaubte Origins, Komma-getrennt (z. B. anderer Frontend-Port). Wildcards werden ignoriert |
| `CLIPFORGE_API_TOKEN` | – | festes Token statt Datei |
| `CLIPFORGE_API_TOKEN_FILE` | `api/.clipforge_api_token` | Ablageort |
| `CLIPFORGE_API_AUTH` | `on` | `off` schaltet nur die Token-Pflicht ab |

Läuft die Oberfläche auf einem anderen Port, diesen eintragen:

```bash
export CLIPFORGE_ALLOWED_ORIGINS=http://127.0.0.1:3001
```

## Entwicklungsoption

`CLIPFORGE_API_AUTH=off` schaltet die Token-Pflicht ab; die Origin-Prüfung
bleibt aktiv. Die automatisierten Backend-Tests laufen so, damit sie nicht in
jedem Aufruf ein Token brauchen; `test_studio_hardening.py`, die Browser-Suite
und `studio_smoke.py` laufen mit aktiver Token-Pflicht. Im normalen Betrieb
nicht setzen.

## Grenzen

- Das ist ein Schutz gegen fremde Webseiten, **keine Benutzeranmeldung**. Jedes
  Programm auf deinem Rechner, das die Token-Datei lesen darf, kann die API
  benutzen.
- Das Backend ist weiterhin nicht dafür gedacht, aus dem Netz erreichbar zu
  sein. Nicht auf `0.0.0.0` binden.
- `GET /api/youtube/oauth/callback` bleibt ohne Token erreichbar (Google ruft
  es per Redirect auf); es ist durch den kurzlebigen OAuth-State geschützt.
