# ClipForge online betreiben

Stand: vorbereitet, **noch nirgends live bereitgestellt**. Das Docker-Image
wurde in der Entwicklungsumgebung nicht gebaut (kein Docker-Dienst
verfügbar). Der Startablauf (`deploy/entrypoint.sh`) wurde ohne Docker mit
denselben Einstellungen durchgespielt: erstes Konto, Anmeldung, Rendern,
geschützter Download.

## Was online anders ist

| | Lokal | Online (`CLIPFORGE_AUTH=accounts`) |
|---|---|---|
| Zugang | jeder Prozess auf dem Rechner mit Token | nur angemeldete Konten |
| Anmeldung | keine | Benutzername + Passwort (scrypt), Sitzung im HttpOnly-Cookie, 14 Tage |
| Änderungen | Token im Header | CSRF-Token der Sitzung im Header |
| API-Schlüssel | `.env` (0600) | verschlüsselt mit `CLIPFORGE_SECRET_KEY` |
| Schutz vor Durchprobieren | – | 5 Login-Versuche je Konto / 20 je IP in 15 Min.; 600 Anfragen/Min. je Sitzung |

**Wichtige Einschränkung:** Alle Konten teilen **einen** Arbeitsbereich
(Projekte, Videos, Schlüssel, Budget). Die Konten sind für dich und Personen,
denen du voll vertraust — nicht für fremde Nutzer. Getrennte Bereiche je
Benutzer sind nicht umgesetzt.

ClipForge läuft als **eine** Instanz (Dateien als Speicher, Sperren und
Ratenbegrenzung im Prozess). Mehrere Instanzen parallel werden nicht
unterstützt.

## Bausteine

- `Dockerfile` — Oberfläche, Backend, FFmpeg in einem Container; läuft ohne Root.
- `deploy/entrypoint.sh` — startet beide Prozesse, legt beim ersten Start
  optional ein Konto an, beendet den Container, wenn ein Prozess abstürzt.
- `/data` — **muss** als dauerhaftes Volume eingehängt werden: Projekte,
  Videos, Konten, verschlüsselte Schlüssel.
- `docker-compose.yml` + `deploy/clipforge.env.example` — für einen eigenen Server.
- Healthcheck: `GET /health`.

Lange Renders laufen im Hintergrund des Containers. Startet der Container
neu, werden wartende Aufgaben fortgesetzt und laufende als „unterbrochen“
markiert; sie lassen sich mit „Erneut versuchen“ wiederholen.

## Pflicht-Einstellungen

| Variable | Zweck |
|---|---|
| `CLIPFORGE_SECRET_KEY` | mind. 32 Zeichen, verschlüsselt die API-Schlüssel. **Geht er verloren, sind gespeicherte API-Schlüssel unlesbar** (neu eingeben). |
| `CLIPFORGE_ALLOWED_ORIGINS` | die öffentliche Adresse, z. B. `https://clipforge.example.com` |
| `CLIPFORGE_ADMIN_USER`, `CLIPFORGE_ADMIN_PASSWORD` | nur für den ersten Start; danach entfernen |

Secrets nur in den Einstellungen des Anbieters bzw. in `deploy/clipforge.env`
(steht in `.gitignore`) — nie im Repository.

Weitere Konten / Passwort zurücksetzen (im Container):

```bash
cd /app/api && python -m clipforge.auth create-user name
```

```bash
cd /app/api && python -m clipforge.auth reset-password name
```

## Eigener Server mit Docker

```bash
cp deploy/clipforge.env.example deploy/clipforge.env
```

`deploy/clipforge.env` ausfüllen, dann:

```bash
docker compose up -d --build
```

Davor gehört ein HTTPS-Proxy (z. B. Caddy oder nginx), sonst funktionieren
die sicheren Cookies nicht. Nur für einen Test ohne HTTPS:
`CLIPFORGE_COOKIE_SECURE=0`.

## Anbieter im Vergleich

Preise sind Richtwerte nach meinem Kenntnisstand und ändern sich — vor der
Entscheidung beim Anbieter prüfen. Ich lege mich auf keinen fest.

| | Railway | Render | Fly.io |
|---|---|---|---|
| Dockerfile direkt aus GitHub | ja | ja | ja (über `fly launch`) |
| Dauerhafter Speicher | Volume | Persistent Disk, nur bezahlte Instanzen | Volume |
| Lange Hintergrundarbeit | ja | ja (Web Service, kein Free-Tier-Schlaf bei bezahlt) | ja |
| Richtwert für 2 GB RAM + 10 GB Speicher | ca. 10–20 USD/Monat (Grundgebühr + Verbrauch) | ca. 25 USD/Monat (Standard-Instanz) + Speicher | ca. 10–15 USD/Monat |
| HTTPS + eigene Domain | inklusive | inklusive | inklusive |
| Einschätzung | am einfachsten | solide, eher teurer für 2 GB RAM | günstig, etwas mehr Kommandozeile |

Empfehlung bei Unsicherheit: **Railway** (wenig Einrichtung). Gratis-Stufen
eignen sich nicht: zu wenig RAM für FFmpeg und kein dauerhafter Speicher.

## Ablauf bei Railway (Beispiel)

1. Neues Projekt → „Deploy from GitHub repo“ → Repository wählen, Branch
   `claude/creator-studio`. Railway erkennt das `Dockerfile`.
2. Volume hinzufügen, Mount-Pfad `/data`.
3. Variablen setzen: `CLIPFORGE_SECRET_KEY`, `CLIPFORGE_ADMIN_USER`,
   `CLIPFORGE_ADMIN_PASSWORD`, `CLIPFORGE_ALLOWED_ORIGINS` (= die von Railway
   vergebene `https://…`-Adresse).
4. Deploy. Danach `CLIPFORGE_ADMIN_PASSWORD` wieder entfernen.
5. Instanzgröße: mindestens 2 GB RAM.
