# ClipForge AI — Web-App (lokal starten)

Minimale Next.js-UI über der FastAPI-Bridge. Die UI ruft **nur** die API auf —
keine Pipeline-Logik im Frontend, keine Datenbank, keine Accounts.

```
Browser ──► Next.js (web/, Port 3000) ──HTTP──► FastAPI (api/, Port 8000) ──► clipforge.run_pipeline
```

---

## Voraussetzungen

- Python 3.11+, FFmpeg (`sudo apt-get install -y ffmpeg`)
- Node.js 18+ (getestet mit Node 22)

---

## 1. Backend starten (Terminal A)

```bash
cd api
export PYTHONPATH=$PWD
pip install -r requirements.txt          # einmalig
uvicorn app:app --reload --port 8000
```

Check: <http://127.0.0.1:8000/health> liefert `{"status":"ok","ffmpeg":true,...}`.

## 2. Frontend starten (Terminal B)

```bash
cd web
npm install                              # einmalig
cp .env.example .env.local               # API-URL (Default passt lokal)
npm run dev                              # Entwicklung (Hot Reload)
# ODER produktionsnah:
#   npm run build && npm run start -- --port 3000
```

App öffnen: <http://127.0.0.1:3000>

> `NEXT_PUBLIC_API_BASE_URL` in `web/.env.local` zeigt standardmäßig auf
> `http://127.0.0.1:8000`. Bei anderem Backend-Port hier anpassen.

---

## Seiten

| Pfad | Inhalt |
|---|---|
| `/` | Landing mit „Video hochladen" |
| `/upload` | Drop-Zone, Top-Clip-Anzahl, **Toggle „Stille Pausen entfernen"**, **Untertitel-Modus (Standard/Karaoke) + Caption-Style (Clean/High Energy)**, **Bildausrichtung (Smart/Face/Center)**, optionales Transkript-JSON |
| `/jobs` | Übersicht aller Jobs mit Live-Status |
| `/jobs/[jobId]` | Status + Export-Counts, Clip-Karten, ZIP-Downloads (Auto & alle), **Bearbeiten**, Bereich „Manuelle Exporte" |
| `/jobs/[jobId]/clips/[clipIndex]/edit` | **Clip-Editor**: Start/Ende feinjustieren, Optionen wählen, neu rendern |

---

## Im Browser testen

1. <http://127.0.0.1:3000> öffnen → **Video hochladen**.
2. Ein Video wählen. Für einen schnellen, deterministischen Durchlauf ohne
   Whisper-Modell-Download zusätzlich das mitgelieferte Transkript als
   „Transkript (optional)" anhängen:
   - Video: `api/testdata/sample.mp4`
   - Transkript: `api/testdata/transcript.json`
3. Optional den Toggle **„Stille Pausen automatisch entfernen"** lassen (Default
   an) oder ausschalten. **Analyse starten** → Weiterleitung zur Job-Seite;
   Fortschritt erscheint live (inkl. Anzahl entfernter Stellen und Dauer).
4. Nach „Fertig" erscheinen die Clip-Karten mit **eingebetteter `<video>`-
   Vorschau**, Score, Aufschlüsselung, Begründung und Transkript-Ausschnitt.
   Bei aktivem Silence-Removal zeigt jede Karte zusätzlich kompakt
   **Original- → Final-Dauer, entfernte Stille und „Schnitt-Optimierung
   aktiv/inaktiv"** (plus Warnhinweis bei Fallback) sowie den verwendeten
   **Caption-Modus + -Style** (mit Fallback-Hinweis, falls keine Wort-Timestamps
   vorhanden waren) sowie die **Bildausrichtung** („Bild: Smart/Center/Face",
   inkl. „auf Gesicht ausgerichtet" bzw. Center-Fallback-Hinweis). Die
   Statuszeile zeigt erkannte Clips, exportierte MP4s, Downloads-Status,
   „Stille-Schnitt", „Captions" und „Bildausrichtung".
   Jede Karte enthält außerdem ein **aufklappbares „📦 Content-Paket"** mit
   fertig formulierten Plattform-Texten: Primary Hook, 5 Hook-Varianten,
   YouTube-Shorts-Titel/-Beschreibung, TikTok & Instagram-Reels-Caption +
   Hashtags + Pinned Comment, Platform-Empfehlung, 3 Varianten A/B/C. Alle
   Textfelder haben einen **„Kopieren"-Button**; pro Plattform gibt es
   „Alles kopieren". Funktioniert ohne API-Key (regelbasiert, DE+EN).
5. Clip direkt im Player **abspielen**, einzeln per **MP4 herunterladen**, oder
   als ZIP-Paket. Die Statuszeile zeigt zusätzlich **Auto-Clips**, **Manuelle
   Exporte** und **Gesamt-Exporte**. Zwei ZIP-Buttons:
   - **„Alle Clips als ZIP"** → `exports.zip` (unverändert, **nur Auto-Clips**,
     flach + clips.json/transcript.json/metadata.json/content_packages.json).
   - **„Alle Exporte als ZIP"** → `all-exports.zip` (**vollständiges Paket**:
     `auto_clips/` + `manual_exports/` + `data/` mit u. a. `manual_exports.json`
     und `metadata.json`).
6. Über **„Bearbeiten"** auf jeder Clip-Karte öffnet sich der **Clip-Editor**
   (`/jobs/[jobId]/clips/[clipIndex]/edit`): Vorschau des Auto-Clips, Felder für
   **Start-/Endzeit** (mit Live-Längenanzeige + Warnung bei <5s/>90s), **Titel**,
   **Caption-Style**, **Untertitel-Modus**, **Bildausrichtung** und **Stille-
   Pausen-Toggle**. **„Neu rendern"** erzeugt einen **separaten** manuellen Export
   (der Auto-Clip bleibt unangetastet); danach erscheinen neue Vorschau,
   Export-Metadaten und ein **Download-Button**. Bestehende manuelle Exporte des
   Clips werden darunter aufgelistet. Auf der Job-Seite zeigt die Clip-Karte
   zusätzlich einen Hinweis, wenn manuelle Exporte existieren.
7. Unter den Clip-Karten fasst der Bereich **„Manuelle Exporte"** alle
   manuellen Re-Renders **clip-übergreifend** zusammen: Titel, Quell-Clip,
   Start/Ende, finale Dauer, Caption-Style, Silence-Removal, Reframe-Modus,
   eine ein-/ausblendbare **Vorschau**, **Download** und ein **„Zum Editor"**-
   Link zum jeweiligen Clip.

> Echtes Video **ohne** angehängtes Transkript: Die Pipeline transkribiert dann
> lokal mit faster-whisper. Beim ersten Lauf wird das Modell geladen (~140 MB),
> daher dauert der erste Durchlauf länger.

---

## Zustände in der UI

- **Loading:** Spinner auf Job- und Übersichtsseiten.
- **Processing:** Live-Log + automatisches Polling (alle 2 s).
- **Empty:** „Noch keine Jobs" bzw. Hinweis bei leerem Ergebnis (0 Clips).
- **Error:** Verständliche Meldung bei Backend-Ausfall, ungültigem Dateityp,
  fehlgeschlagener Analyse (`job.error`) oder nicht gefundenem Job.
- **Wiederhergestellt (Restore):** Jobs überleben einen FastAPI-Neustart. Sie
  werden aus `jobs/` neu geladen und in Liste + Detailseite mit dem Hinweis
  **„↻ Aus lokalem Speicher wiederhergestellt"** markiert. Voll nutzbar bleiben
  Clips, Previews/Downloads, manuelle Exporte und beide ZIPs — ohne erneute
  Analyse.
- **Unterbrochen / Unvollständig:** War ein Job beim Neustart aktiv, wird er als
  **„Unterbrochen"** (`interrupted`) angezeigt — mit klarer Erklärung und
  **ohne** irreführende Download-Buttons. Fehlen einem fertigen Job die
  Ergebnis-Dateien, erscheint **„Unvollständig"** (`incomplete`) mit Warnhinweis.

---

## Nicht enthalten (bewusst)

❌ Accounts · ❌ Billing · ❌ Cloud · ❌ Face-Tracking · ❌ Direkt-Posten auf
TikTok/Instagram/YouTube · ❌ neue Backend-Logik · ❌ Datenbank ·
❌ Cloud-Persistenz · ❌ automatische Wiederaufnahme laufender Renders nach Crash.
