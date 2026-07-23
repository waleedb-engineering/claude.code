# ClipForge AI — Beta-Tester-Guide (0.1.0-beta.1)

Praktische Anleitung für technische Beta-Tester. Ziel: von „Paket erhalten" zu
„erster Clip erzeugt und geprüft" in wenigen Minuten, plus klare Kriterien,
was zu testen ist und was bewusst (noch) nicht funktioniert.

> **Status:** geschlossene Beta / Release Candidate `0.1.0-beta.1`.
> Local-first, keine Pflicht-Cloud, kein Account. Kein produktionsreifes SaaS.

---

## Was ist ClipForge?

Ein **lokales** Tool, das aus einem langen Video (Podcast, Talk,
Coaching-Call) automatisch mehrere kurze, vertikale Clips (9:16) mit
eingebrannten Untertiteln erzeugt — für YouTube Shorts, TikTok und Instagram
Reels gedacht. Alles läuft auf deinem Rechner; Videos verlassen die Maschine
nur, wenn du eine der optionalen Cloud-Funktionen bewusst aktivierst
(KI-Analyzer via API-Key, oder echter privater YouTube-Upload).

## Für wen ist die Beta gedacht?

- Technische Tester, die lokal Python + Node ausführen können.
- Content-Creator/Editoren, die den Clip-Vorschlag und die Textausgaben an
  echten eigenen Videos beurteilen wollen.
- Nicht gedacht für: nicht-technische Endnutzer ohne Terminal, produktive
  Kanäle, Multi-User-Setups, Server-/Internet-Deployment.

## Was kann getestet werden?

- Upload (einzeln + Batch), Analyse, Clip-Auswahl, Score-Plausibilität
- Untertitel (Karaoke), Silence-Removal, Smart-Reframe, Brand Kit
- Web-Clip-Editor + Re-Render
- Content-Package-Texte (Titel/Hashtags/Beschreibungen)
- ZIP-Exporte
- Publishing Planner (lokale Drafts) + globale Übersicht
- YouTube **Dry-Run** (Vorschau ohne Upload)
- Optional & bewusst: echter privater YouTube-Upload (siehe unten)
- Fehler-/Randfälle (kaputte Datei, Netzwerkausfall, Abbruch)

---

## Systemanforderungen

| Komponente | Version | Prüfen |
|---|---|---|
| Python | ≥ 3.10 | `python3 --version` |
| Node.js | ≥ 20.9 | `node --version` |
| npm | (mit Node) | `npm --version` |
| ffmpeg + ffprobe | aktuell | `ffmpeg -version` |

`ffmpeg` wird **nicht** automatisch installiert (nur geprüft). Fehlt es:
`apt install ffmpeg` (Linux) / `brew install ffmpeg` (macOS) /
[ffmpeg.org](https://ffmpeg.org/download.html) (Windows).

Optional (ohne läuft ClipForge vollständig): `ANTHROPIC_API_KEY` für den
KI-Analyzer-Modus; ein Google-Cloud-Projekt nur für den optionalen
YouTube-Real-Test.

---

## Installation aus dem Beta-Package

Du hast ein Tarball erhalten, z. B. `clipforge-beta-0.1.0-beta.1.tar.gz`.

```bash
tar -xzf clipforge-beta-0.1.0-beta.1.tar.gz
cd clipforge-beta-0.1.0-beta.1
```

Das entpackte Verzeichnis ist **kein** Git-Repository und enthält keine
`node_modules`, kein `.venv`, keine `.env`, keine Videos, keine Secrets — nur
Quellcode, Skripte, Docs und die eingecheckten Test-Fixtures.

## Setup

```bash
./scripts/setup_local.sh
```

Legt ein Python-venv an, installiert Backend- und Frontend-Abhängigkeiten,
erzeugt `.env`/`web/.env.local` aus den `*.example`-Vorlagen (überschreibt
vorhandene nicht), prüft ffmpeg und führt am Ende den **Environment Doctor**
aus. Erneutes Ausführen ist sicher (idempotent).

## Start

```bash
./scripts/start_local.sh
```

Startet Backend (`:8000`) und Frontend (`:3000`) mit einem Befehl. Beenden:
**Strg+C** (beendet beide sauber). Ports belegt? Mit
`CLIPFORGE_API_PORT` / `CLIPFORGE_WEB_PORT` überschreiben.

Danach im Browser öffnen: **http://127.0.0.1:3000/upload**

## Healthcheck

```bash
# Umgebung prüfen (PASS/WARN/FAIL):
python3 scripts/clipforge_doctor.py

# Backend-Health direkt:
curl -s http://127.0.0.1:8000/health
# -> {"status":"ok", ..., "version":"0.1.0-beta.1", "ffmpeg":true, ...}
```

Die Version steht auch in der Fußzeile der Web-App.

---

## Erstes Video verarbeiten

1. **http://127.0.0.1:3000/upload** öffnen.
2. Video wählen (MP4/MOV/MKV/WEBM/AVI/M4V, max. 500 MB) → **„Videos
   analysieren"**.
3. Auf der Job-Seite läuft die Analyse live (Polling alle 2 s).
   - **Erster Lauf ohne Transkript** lädt einmalig das Whisper-Modell
     (~140 MB) — dauert entsprechend länger.
   - **Schneller/deterministisch:** kein Video zur Hand? Mit ffmpeg eins
     erzeugen und das mitgelieferte Transkript anhängen:
     ```bash
     ./scripts/make_sample_video.sh   # -> api/testdata/sample.mp4 (60s)
     ```
     Beim Upload zusätzlich `api/testdata/transcript.json` als „Transkript
     (optional)" anhängen → überspringt Whisper.
4. Nach `completed` erscheinen die Clip-Karten mit Score, Aufschlüsselung und
   eingebetteter Vorschau.

## Export testen

- Auf einer Clip-Karte **„MP4 herunterladen"** → fertiger 9:16-Clip lokal.
- Job-Seite: **„Alle Clips als ZIP"** (nur Auto-Clips) und **„Alle Exporte als
  ZIP"** (Auto-Clips + manuelle Exporte + `data/`-Metadaten).

## Editor testen

1. Clip-Karte → **„Bearbeiten"**.
2. Start-/Endzeit anpassen, Caption-Style/Reframe/Titel wählen.
3. **„Neu rendern"** → erzeugt einen neuen manuellen Export (echter
   ffmpeg-Lauf), der ursprüngliche Auto-Clip bleibt erhalten.

## Content Package prüfen

Auf einer Clip-Karte das **„📦 Content-Paket"**-Panel aufklappen: Primary
Hook, Hook-Varianten, YouTube-Shorts-Titel/-Beschreibung, TikTok-/Reels-Caption
+ Hashtags + Pinned Comment, Plattform-Empfehlung, A/B/C-Varianten. Jeder Text
hat einen Copy-Button. **Ohne API-Key** entstehen die Texte regelbasiert
(DE+EN); mit `ANTHROPIC_API_KEY` optional durch Claude verbessert.

## ZIP-Download prüfen

`all-exports.zip` öffnen und Struktur prüfen: `auto_clips/`, `manual_exports/`,
`data/` (u. a. `clips.json`, `transcript.json`, `content_packages.json`,
`manual_exports.json`, `metadata.json`). Videos abspielbar, JSON valide.

## YouTube Dry-Run testen

Bei einem YouTube-Shorts-Draft → **„YouTube Dry-Run prüfen"**. Zeigt exakt,
**was hochgeladen würde** (Titel, Beschreibung, `privacy: private`, technische
Checks) — **ohne** Upload. Ohne konfigurierte Credentials zeigt die
Upload-Bereitschaft `blocked_reasons` und **keinen** aktivierbaren
Upload-Button (korrekter, sicherer Default).

## YouTube Real Upload — nur optional und bewusst

Ein echter Upload ist **nicht** Teil des Standard-Beta-Testflows. Falls du
ausdrücklich darum gebeten wirst, ihn beizutragen: folge Schritt für Schritt
[`docs/YOUTUBE_REAL_TEST_CHECKLIST.md`](YOUTUBE_REAL_TEST_CHECKLIST.md). Er
erfordert ein eigenes Google-Cloud-Projekt, ein **Test-Konto**, zwei bewusst
gesetzte Feature-Flags und eine interaktive `UPLOAD_PRIVATE`-Bestätigung.

### Private-only Upload-Hinweis

Ein echter Upload ist **immer** `private` (nur du siehst das Video). Es gibt
**keinen** Code-Pfad für `public` oder `unlisted` — das ist keine Einstellung,
sondern eine Grenze im Code (`ALLOWED_PRIVACY = "private"`). Kein Auto-Posting,
kein Scheduling.

---

## Was Tester NICHT erwarten sollten

- Kein öffentlicher/Unlisted-YouTube-Upload.
- Kein automatischer TikTok-/Instagram-Upload (nur lokale Pakete zum manuellen
  Hochladen).
- Kein automatisches Planen/Posten (kein Hintergrunddienst).
- Kein Mehrbenutzer-Betrieb, kein Login, keine Cloud-Sync.
- Keine Garantie für Reichweite/Viralität — der Score ist eine Einschätzung.
- Kein produktionsreifes, internet-exponierbares Deployment.

## Bekannte Einschränkungen

Vollständig mit Auswirkung/Workaround/Status:
[`docs/KNOWN_ISSUES.md`](KNOWN_ISSUES.md). Kern: echter YouTube-Upload noch
nicht mit realem Konto E2E-verifiziert; local-first (kein Multi-User/CORS-
Härtung); kein dynamisches Reframe; kein Auto-Resume eines unterbrochenen
Uploads nach Prozess-Neustart (dafür sichere Recovery); 3 dokumentierte
ESLint-Tech-Debt-Punkte.

---

## Wie man Fehler meldet

Am hilfreichsten:

1. **Was** hast du getan? (konkrete Schritte zum Nachstellen)
2. **Was** ist passiert? (genaue Fehlermeldung / Screenshot)
3. **Was** hast du erwartet?
4. Umgebung: Ausgabe von `python3 scripts/clipforge_doctor.py` und
   `curl -s http://127.0.0.1:8000/health`.

## Welche Logs/Infos bei Bug-Reports hilfreich sind

Unbedenklich zu teilen (enthalten per Design keine Secrets):

- Terminal-Ausgabe von `start_local.sh` / `clipforge_doctor.py`
- Backend-Log `./.clipforge-backend.log`
- Im Browser angezeigte Fehlermeldungen, Screenshots der UI
- API-Antworten wie `GET /api/config`, `GET …/youtube/upload-status`
  (`no_secrets: true`)

**Niemals teilen:** Inhalt von `.env`, `client_secrets.json`,
Keychain-Einträge, oder irgendetwas mit `ya29.` / `1//` / `GOCSPX-` /
`Bearer ` / `sk-…`.

## Wie man lokale Daten löscht

```bash
# ClipForge stoppen (Strg+C), dann:
rm -rf api/jobs/*            # alle Jobs, Uploads, Clips, Exporte
rm -f  api/config/brand_kit.json   # Brand Kit (optional)
```

Vollständiges Zurücksetzen inkl. venv/Config: siehe
[`docs/LOCAL_BETA_GUIDE.md`](LOCAL_BETA_GUIDE.md) („Alles lokal zurücksetzen").
Uninstall = ClipForge stoppen und den Ordner löschen (nichts wird systemweit
installiert; einzige Ausnahme: ein evtl. angelegter YouTube-Token im
OS-Keychain — dafür gibt es in der App „YouTube-Token löschen").

## Datenschutz / Local-first-Hinweis

Deine Videos, Clips, Transkripte und Publishing-Drafts liegen ausschließlich
lokal unter `api/jobs/`. Es gibt keinen Cloud-Sync. Zwei optionale, bewusst
von dir zu aktivierende Ausnahmen: der KI-Analyzer sendet Transkript-Text an
die Anthropic-API (nur mit `ANTHROPIC_API_KEY`), und der echte
YouTube-Upload sendet das Video an Google (nur mit gesetzten Flags +
Bestätigung). ClipForge gibt **nie** Tokens/Secrets im DOM, in Logs oder in
API-Antworten aus. Betrieb ist für `127.0.0.1` gedacht — **nicht** ins offene
Internet exponieren (kein Auth, offene CORS für lokale Entwicklung).

---

Danke fürs Testen. Technische Tiefe zu einzelnen Themen:
[`README.md`](../README.md), [`docs/WEB.md`](WEB.md),
[`docs/LOCAL_BETA_GUIDE.md`](LOCAL_BETA_GUIDE.md).
