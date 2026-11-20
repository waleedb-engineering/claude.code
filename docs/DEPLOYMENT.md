# Bereitstellung — Architektur und Optionen

Kurzfassung: **Frontend und Backend gehören zusammen auf einen Server/Container mit
FFmpeg und dauerhaftem Speicher.** Vercel (o. ä. Serverless) kann nur das Next.js-
Frontend hosten; Python-Rendering, Hintergrundjobs und Mediendateien laufen dort
nicht. Details zu Konten, TLS und Sicherung: [`ONLINE_BETRIEB.md`](ONLINE_BETRIEB.md).

## Bausteine

| Baustein | Lokal (Mac/Windows/Linux) | Server (empfohlen) | Hinweise |
|---|---|---|---|
| Frontend (Next.js) | `npm run dev` / `scripts/start_local.sh` | im selben Container (`Dockerfile`) oder statisch hinter dem Proxy | Vercel nur, wenn das Backend separat erreichbar ist |
| Backend (FastAPI) | `uvicorn app:app` | Container mit FFmpeg | braucht dauerhaftes Volume |
| Job-Worker | im Backend-Prozess (ThreadPool, `CLIPFORGE_STUDIO_WORKERS`, Standard 2) | dito; bei mehr Last: mehrere Container erst nach DB-Wechsel | Recovery nach Neustart vorhanden |
| Medien/Projekte | Ordner `CLIPFORGE_STUDIO_DIR`, `CLIPFORGE_JOBS_DIR` | Volume `/data` | Plattenplatz-Prüfung `CLIPFORGE_MIN_FREE_MB` |
| Datenbank | JSON-Dateien (atomar) | JSON bei **einer** Instanz; SQLite/PostgreSQL erst bei mehreren Instanzen | `STORAGE_EVALUATION.md` |
| Anmeldung | lokal ohne Konto (Token) | `CLIPFORGE_AUTH=accounts` + HTTPS | Rollen, getrennte Arbeitsbereiche |
| Schlüssel | `.env` (nie im Repo) | Hosting-Secrets bzw. verschlüsselter Tresor je Benutzer | nie im Frontend/Log |
| HTTPS | – | Reverse-Proxy (Caddy/nginx) vor Port 3000/8000 | `deploy/` |
| Logs | Konsole/Logdateien | Container-Logs; keine Schlüssel/Tokens im Log | – |
| Backups | Ordner kopieren | Volume-Snapshot täglich; Restore = Ordner zurückspielen | Projektversionen bleiben erhalten |
| Hardware-Kodierung | optional `CLIPFORGE_HWACCEL=auto` (VideoToolbox/NVENC/QSV/VAAPI nach echtem Probelauf) | nur mit GPU im Container | Standard CPU (libx264) |

## Empfohlene Varianten

1. **Lokal (Standard, kostenlos):** Mac/PC, `scripts/start_local.sh` bzw. Windows-Skript.
   Alles bleibt auf dem Rechner; Ollama optional für den KI-Assistenten.
2. **Ein Server mit Docker:** `docker compose up -d` (Frontend + Backend + FFmpeg in
   einem Image, Volume `/data`), davor Caddy für HTTPS. Passt für einzelne Creator
   oder kleine Teams. Kosten: ein VPS mit ≥ 4 Kernen/8 GB (Preis je Anbieter).
3. **Skalierung (später):** getrennte Worker-Container, gemeinsamer Objektspeicher
   (S3-kompatibel), PostgreSQL. **Noch nicht implementiert** — Voraussetzung ist der
   Wechsel der Persistenz.

## Was ausdrücklich nicht getan wurde

- Keine bezahlten Server, Domains oder Speicher angelegt.
- Keine Vercel-Einstellungen geändert (Eigentümer-Entscheidung: Root `web/` setzen
  oder Preview abschalten).

## Checkliste vor dem Online-Betrieb

- [ ] `CLIPFORGE_AUTH=accounts`, starkes Admin-Passwort, HTTPS aktiv
- [ ] `CLIPFORGE_SECRET_KEY` gesetzt (Verschlüsselung der Benutzer-Schlüssel)
- [ ] Volume gesichert, Restore einmal geprobt
- [ ] `CLIPFORGE_MIN_FREE_MB` passend zur Plattengröße
- [ ] Upload-Grenzen (`CLIPFORGE_MAX_UPLOAD_MB`, `CLIPFORGE_MAX_STREAM_UPLOAD_MB`)
- [ ] Publishing-Apps bei den Plattformen geprüft/freigegeben, bevor echte Uploads erlaubt werden
