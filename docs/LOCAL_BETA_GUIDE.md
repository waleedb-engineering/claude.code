# ClipForge AI — Local Beta Guide

ClipForge läuft komplett lokal auf deinem Rechner: kein Account, keine Cloud,
keine Daten verlassen deine Maschine (außer du aktivierst bewusst optionale
Cloud-Features wie den KI-Analyzer oder einen echten YouTube-Upload).

Dieser Guide bringt dich in wenigen Minuten von "frisch geklont" zu "erster
Clip fertig".

---

## 1. Voraussetzungen

| Tool | Mindestversion | Prüfen |
|---|---|---|
| Python | 3.10+ | `python3 --version` |
| Node.js | 20.9+ | `node --version` |
| npm | (kommt mit Node) | `npm --version` |
| ffmpeg + ffprobe | beliebig aktuell | `ffmpeg -version` |

ffmpeg wird **nicht automatisch installiert** — ClipForge prüft nur, ob es da
ist. Fehlt es: `apt install ffmpeg` (Linux) / `brew install ffmpeg` (macOS) /
[ffmpeg.org/download.html](https://ffmpeg.org/download.html) (Windows).

Optional (nur für bestimmte Features, ClipForge läuft ohne sie):

- `ANTHROPIC_API_KEY` — KI-Analyzer-Modus (sonst regelbasiert, kein Fehler).
- YouTube-OAuth-Client-Secrets — nur für den optionalen privaten
  YouTube-Testupload (siehe Punkt 11).

---

## 2. Installation

```bash
./scripts/setup_local.sh
```

Das Skript:

1. legt ein Python-venv unter `api/.venv` an (falls noch keine aktive
   venv/conda-Umgebung erkannt wird) und installiert `api/requirements.txt`,
2. installiert die Frontend-Dependencies (`web/npm install`),
3. legt `api/jobs/` und `api/config/` an,
4. erzeugt `.env` und `web/.env.local` aus den `.env.example`-Vorlagen —
   **nur, falls diese Dateien noch nicht existieren** (nichts wird
   überschrieben),
5. prüft ffmpeg/ffprobe (installiert nichts systemweit),
6. führt den **Environment Doctor** aus und zeigt dir, was noch fehlt.

Erneutes Ausführen ist sicher (idempotent) — deine `.env` bleibt unangetastet.

---

## 3. Start

```bash
./scripts/start_local.sh
```

Startet Backend (`http://127.0.0.1:8000`) und Frontend
(`http://127.0.0.1:3000`) mit einem Befehl, wartet auf Healthchecks und zeigt
dir die URLs. Läuft ClipForge schon (z.B. in einem anderen Terminal), erkennt
das Skript das und meldet es, statt einen Konflikt zu erzeugen.

Browser öffnen: **http://127.0.0.1:3000/upload**

---

## 4. Stop

**Strg+C** im Terminal, in dem `start_local.sh` läuft. Beendet Backend und
Frontend zusammen — sauber, ohne Zombie-Prozesse.

---

## 5. Erster Test (kompletter Flow, kein echter Upload)

1. **http://127.0.0.1:3000/upload** öffnen.
2. Ein Video hochladen — ein eigenes MP4/MOV/MKV/WEBM/AVI/M4V (max. 500 MB),
   oder falls keins zur Hand ist, lokal eins erzeugen (ffmpeg nötig, wird
   nicht committet):
   ```bash
   ./scripts/make_sample_video.sh   # → api/testdata/sample.mp4 (60s)
   ```
   - Tipp für einen schnellen, deterministischen Testlauf **ohne** Whisper-
     Download: zusätzlich `api/testdata/transcript.json` als "Transkript
     (optional)" mitgeben.
3. **Job beobachten** — die Job-Seite pollt automatisch (alle 2s) und zeigt
   Live-Logs, bis der Job `completed` ist.
4. **Clips ansehen** — fertige Clips erscheinen als Karten mit eingebetteter
   Vorschau, Performance-Score und Aufschlüsselung.
5. **Preview abspielen** — Video direkt in der Clip-Karte abspielen.
6. **Content Package öffnen** — Titel-/Hashtag-/Hook-Vorschläge pro Clip
   (Klick auf den entsprechenden Bereich der Clip-Karte).
7. **Clip bearbeiten** — "Bearbeiten" auf einer Clip-Karte → Start/Ende,
   Caption-Style, Bildausrichtung anpassen.
8. **Re-Render testen** — "Neu rendern" im Editor → erzeugt einen neuen
   manuellen Export (echter ffmpeg-Lauf, dauert ein paar Sekunden).
9. **Publishing Draft erstellen** — "Publishing vorbereiten" auf einer
   Clip-Karte → legt einen **lokalen** Draft an (kein Upload, kein Login).
10. **Global Publishing öffnen** — **http://127.0.0.1:3000/publishing** zeigt
    alle Drafts über alle Jobs, mit Suche/Filter/Duplizieren.
11. **YouTube Dry-Run testen** — im Draft: "YouTube Dry-Run prüfen" zeigt,
    was hochgeladen **würde** (Titel, Beschreibung, Checks) — **kein** echter
    Upload, egal wie die Feature-Flags stehen.
12. **Ohne Credentials: Upload bleibt blockiert** — "Upload-Bereitschaft
    prüfen" zeigt bei fehlenden Credentials `blocked_reasons` und **keinen**
    aktivierbaren Upload-Button. Das ist der korrekte, sichere Default.

---

## 6. Typische Fehler

### ffmpeg fehlt

**Symptom:** Doctor zeigt `[✗ FAIL] ffmpeg` / `ffprobe`, oder Jobs schlagen
mit einem ffmpeg-Fehler fehl.
**Fix:** ffmpeg installieren (siehe Punkt 1), dann `./scripts/start_local.sh`
neu starten.

### Port belegt

**Symptom:** `start_local.sh` meldet `Backend-Port 8000 ist belegt, antwortet
aber NICHT wie ClipForge-Backend` (oder analog für Port 3000).
**Fix:** Den blockierenden Prozess beenden, oder ClipForge auf einen anderen
Port legen:

```bash
CLIPFORGE_API_PORT=8010 CLIPFORGE_WEB_PORT=3010 ./scripts/start_local.sh
```

Läuft dagegen bereits eine **eigene** ClipForge-Instanz auf dem Standardport,
erkennt das Skript das automatisch und meldet "wird wiederverwendet" — kein
Fehler.

### Backend nicht erreichbar

**Symptom:** Das Frontend zeigt "Backend nicht erreichbar unter
http://127.0.0.1:8000. Läuft FastAPI auf Port 8000?"
**Fix:** Prüfen, ob `start_local.sh` noch läuft bzw. `python3
scripts/clipforge_doctor.py` ausführen. Kein weißer Bildschirm, keine
kryptische Fehlermeldung — das Frontend bleibt bedienbar.

### Whisper-Download dauert

**Symptom:** Der erste Job ohne mitgeliefertes Transkript hängt lange in
"Analyse läuft".
**Grund:** Ohne `--transcript` transkribiert ClipForge lokal mit
faster-whisper; beim allerersten Lauf wird das Modell heruntergeladen
(~140 MB für `base`). Das ist einmalig.
**Schneller testen:** ein Transkript mitgeben (siehe Punkt 5.2) — überspringt
Whisper komplett.

### YouTube OAuth nicht konfiguriert

**Symptom:** Readiness-Panel zeigt `client_secrets_missing` /
`oauth_disabled`.
**Das ist der Standardzustand.** YouTube-OAuth ist optional und standardmäßig
deaktiviert (`CLIPFORGE_ENABLE_YOUTUBE_OAUTH=false`). Ohne Konfiguration
funktioniert der Rest der App normal — nur der YouTube-Teil bleibt inaktiv.

### Warum echter Upload standardmäßig deaktiviert ist

`CLIPFORGE_ENABLE_YOUTUBE_UPLOAD=false` ist bewusst der Default. ClipForge
lädt **nie** automatisch etwas hoch. Ein echter Upload ist **immer**:
PRIVATE-only (kein Public/Unlisted), erfordert eine explizite Bestätigung
(Checkbox + `UPLOAD_PRIVATE`-Eingabe) und läuft nur, wenn du das Feature-Flag
bewusst aktivierst UND YouTube-Credentials konfiguriert hast. Es gibt keinen
TikTok- oder Instagram-Upload — nur lokale Publishing-Packs zum manuellen
Hochladen.

---

## 7. Datenverzeichnis

Alle Job-Daten (Uploads, Clips, Transkripte, manuelle Exporte) liegen unter
**`api/jobs/`** (überschreibbar via `CLIPFORGE_JOBS_DIR`). Das lokale Brand
Kit liegt unter `api/config/brand_kit.json`. Beides ist `.gitignore`t — es
landet nie im Repository.

---

## 8. Jobs löschen

- **Einzeln:** auf der Job-Seite → "Job löschen" (fragt vorher nach, entfernt
  alle Clips/Exporte/Metadaten dieses Jobs).
- **Mehrere auf einmal:** auf `/jobs` → Storage-Übersicht → Bulk-Cleanup
  (nach Alter/Status filterbar).
- **Manuell:** den jeweiligen Ordner unter `api/jobs/<job_id>/` löschen, bei
  gestopptem Backend.

---

## 9. Alles lokal zurücksetzen

```bash
# Backend/Frontend stoppen (Strg+C im start_local.sh-Terminal), dann:
rm -rf api/jobs/*          # alle Jobs
rm -f api/config/brand_kit.json   # Brand Kit
rm -rf api/.venv           # Python-venv (setup_local.sh legt sie neu an)
rm -f .env web/.env.local  # eigene Konfiguration (Vorlagen bleiben erhalten)
```

Danach `./scripts/setup_local.sh` erneut ausführen, um wieder bei null zu
starten.

---

## Sicherheits-Defaults (unverändert, egal was du konfigurierst)

- Kein echter YouTube-Upload ohne explizite Bestätigung.
- YouTube-Upload ist **immer** PRIVATE-only — kein Public, kein Unlisted.
- Kein TikTok-, kein Instagram-Auto-Upload (nur lokale Publishing-Packs).
- Keine Tokens/Secrets werden je im Browser-DOM, in Logs oder API-Antworten
  ausgegeben.
