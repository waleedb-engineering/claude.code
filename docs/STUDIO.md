# Creator Studio — Einrichtung und Bedienung

Das Studio führt von einer Quelle zum fertigen Video:
Quelle → Extraktion/Transkription → Skript → Szenen → Visuals → Stimme → Musik →
Captions → Editor → Qualitätsprüfung → Render → Publishing-Entwurf.

Was davon lokal läuft und was Zugangsdaten braucht, steht ehrlich in
[`REVID_PARITY_STATUS.md`](REVID_PARITY_STATUS.md).

## Starten

```bash
./scripts/setup_local.sh
```

```bash
./scripts/start_local.sh
```

Danach `http://127.0.0.1:3000/studio` öffnen. Voraussetzungen: Python 3.10+,
Node 20+, FFmpeg.

Prüfen, ob alles funktioniert (echtes Testvideo, kein Netz, keine Kosten):

```bash
python3 scripts/studio_smoke.py
```

## Daten

Alles liegt lokal unter `api/studio_data/` (Pfad änderbar mit
`CLIPFORGE_STUDIO_DIR`): Projekte, Quellen, Artefakte, Renders, Automationen,
Ideen, Metriken. Jede Projektänderung erhöht eine Versionsnummer; die letzten
25 Stände lassen sich im Editor wiederherstellen.

## Provider

Die Seite **Studio → Einrichtung** zeigt den Zustand jedes Providers. Schlüssel
stehen nur in `.env`; die Oberfläche und die API nennen ausschließlich die
Namen der benötigten Variablen, nie Werte.

| Provider | Art | Einrichtung |
|---|---|---|
| Ohne Stimme | lokal | immer verfügbar |
| macOS-Systemstimme | lokal | nur macOS (`say`), nichts zu konfigurieren |
| espeak-ng | lokal | `brew install espeak-ng` bzw. `apt-get install espeak-ng` |
| ElevenLabs | Cloud, kostenpflichtig | `ELEVENLABS_API_KEY` |
| OpenAI TTS / OpenAI Bilder | Cloud, kostenpflichtig | `OPENAI_API_KEY` |
| Claude (Skripte) | Cloud, kostenpflichtig | `ANTHROPIC_API_KEY` |

Regeln für kostenpflichtige Provider:

- Das **Budgetlimit** eines Projekts steht standardmäßig auf 0. Mit 0 wird nie
  ein kostenpflichtiger Provider aufgerufen.
- Vor dem Render wird geschätzt. Übersteigt die Schätzung das Budget, startet
  nichts. Reicht das Budget mitten im Lauf nicht mehr, bricht der Render ab,
  bevor der nächste kostenpflichtige Aufruf passiert.
- Preise sind Schätzwerte. Mit `CLIPFORGE_PROVIDER_PRICES` (JSON) lassen sie
  sich anpassen.
- Fällt ein Provider aus, wird die Szene lokal gerendert und der Vorfall im
  Render-Bericht vermerkt.

## Musik

ClipForge liefert keine Musik mit. Eigene, lizenzierte Dateien landen in
`api/studio_data/music/` (oder `CLIPFORGE_MUSIC_DIR`) oder werden im Editor ins
Projekt hochgeladen. „Unter der Stimme absenken“ regelt die Musik automatisch
herunter; „Schnitte auf den Beat legen“ verschiebt Szenenwechsel auf Beats.

## Plattformen

| Plattform | Zustand | Weg |
|---|---|---|
| YouTube Shorts | nicht verbunden, bis OAuth eingerichtet ist | privater Upload nach Bestätigung, siehe `YOUTUBE_PUBLISHING.md` |
| TikTok, Instagram Reels, X | nicht verbunden (kein Adapter) | Export-Pack herunterladen und manuell posten |

Zustände eines Entwurfs: nicht verbunden, bereit, geplant, fällig,
veröffentlicht, fehlgeschlagen. Ein geplanter Entwurf wird zum Termin als
**fällig** markiert. ClipForge postet nie von selbst. „Veröffentlicht“ entsteht
nur durch den YouTube-Pfad oder durch deine ausdrückliche Bestätigung unter
**Studio → Analytics**.

## Automationen

Unter **Studio → Automationen** legst du wiederkehrende Läufe an: Rhythmus
(täglich, wöchentlich, monatlich), Uhrzeit in deiner Zeitzone, Workflow, eine
Liste von Themen/Skripten/URLs (werden reihum verwendet), optional
Publishing-Entwürfe je Plattform, Budget pro Lauf und pro Monat.

- Der Worker läuft im Backend-Prozess und tickt alle 30 Sekunden. Läuft das
  Backend nicht, läuft nichts; ein verpasster Termin wird nach dem Start
  **einmal** nachgeholt.
- Ein Lauf, der beim Absturz aktiv war, wird als unterbrochen markiert und
  einmal automatisch wiederholt.
- Gleichzeitig läuft standardmäßig ein Lauf (`CLIPFORGE_AUTOMATION_MAX_CONCURRENT`).
- Automationen erzeugen höchstens Entwürfe. Einen Modus „veröffentlichen“ gibt
  es nicht.
- Automatisierbar sind nur Text- und URL-Workflows.

## CLI

Das Backend muss laufen.

```bash
cd api && python3 -m clipforge.studio.cli create --workflow script --script "Erster Satz. Zweiter Satz." --wait
```

```bash
cd api && python3 -m clipforge.studio.cli render <projekt-id> --wait
```

```bash
cd api && python3 -m clipforge.studio.cli export <projekt-id> --download video.mp4
```

```bash
cd api && python3 -m clipforge.studio.cli automation list
```

Ausgabe ist JSON. Exit-Code 1 bedeutet API- oder Aufgabenfehler, 2 bedeutet
Backend nicht erreichbar.

## Konfiguration

| Variable | Standard | Zweck |
|---|---|---|
| `CLIPFORGE_STUDIO_DIR` | `api/studio_data` | Datenordner |
| `CLIPFORGE_MUSIC_DIR` | `<studio>/music` | Musikbibliothek |
| `CLIPFORGE_STUDIO_WORKERS` | 2 | parallele Hintergrund-Aufgaben |
| `CLIPFORGE_STUDIO_WORKER` | `on` | `off` schaltet den Automation-Worker ab |
| `CLIPFORGE_AUTOMATION_MAX_CONCURRENT` | 1 | gleichzeitige Automationsläufe |
| `CLIPFORGE_STUDIO_MAX_FETCH_MB` | 5 | Größenlimit für URL-Abrufe |
| `CLIPFORGE_STUDIO_FETCH_TIMEOUT` | 15 | Zeitlimit für URL-Abrufe (Sekunden) |
| `CLIPFORGE_STUDIO_MAX_PDF_MB` | 50 | Größenlimit für PDFs |
| `CLIPFORGE_PROVIDER_PRICES` | – | JSON mit eigenen Preisschätzungen |
| `CLIPFORGE_FLAG_<NAME>` | – | überschreibt ein Flag aus `feature_flags.json` |

Feature Flags stehen in `feature_flags.json` im Repo-Root.

## Sicherheit beim URL-Import

Nur `http`/`https` auf den Ports 80, 443, 8080, 8443. Abgelehnt werden
`localhost`, private und Link-Local-Adressen (inklusive Cloud-Metadaten
`169.254.169.254`), URLs mit Zugangsdaten und Weiterleitungen auf solche Ziele.
Die Verbindung geht an genau die geprüfte IP-Adresse. Es gelten Größen- und
Zeitlimit sowie eine Content-Type-Liste (HTML, Text). Aus der Seite wird nur
Text gewonnen.

## Bekannte Einschränkungen

Siehe [`REVID_PARITY_STATUS.md`](REVID_PARITY_STATUS.md) und
[`KNOWN_ISSUES.md`](KNOWN_ISSUES.md).
