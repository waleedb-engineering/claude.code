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

## Produktionsoptionen

Jedes Projekt trägt ein typisiertes Optionsmodell (`options` in
`project.json`). Dieselben Werte gehen von der API über die Speicherung bis in
Skript, Qualitätsprüfung und Render.

| Option | Wirkung |
|---|---|
| `platform` | Standard-Seitenverhältnis (X: 16:9, sonst 9:16) und empfohlene Maximaldauer in der Qualitätsprüfung |
| `duration_target` | Ziellänge des Skripts |
| `cta` | wird wörtlich die letzte Szene |
| `forbidden_topics` | Sätze dazu werden aus der Quelle ausgelassen; eine Szene, die ein Thema berührt, blockiert den Render |
| `visual_style` | wird an jeden Visual-Prompt angehängt (wirkt bei KI-Bildern) |
| `media_type` | Standard-Visual neuer Szenen: `motion`, `static`, `ai_image` |
| `image_animation` | Ken-Burns für Bilder an/aus |
| `voice_model` | Modell des Cloud-Sprachproviders |
| `music_mode` | `none` rendert ohne Musik, auch wenn ein Titel gewählt ist |
| `goal`, `audience`, `creative_instructions` | gehen in den Auftrag an die Skript-KI. **Ohne `ANTHROPIC_API_KEY` haben sie keine Wirkung** und werden nur gespeichert |
| `video_provider`, `video_model` | werden abgelehnt: es gibt keinen KI-Video-Adapter |

Bei „Skript → Video“ bleibt dein Text wörtlich erhalten; Verstöße gegen
`forbidden_topics` werden dort gemeldet, nicht umgeschrieben.

## API-Schlüssel

Unter **Studio → Einrichtung** lassen sich Schlüssel für ElevenLabs, OpenAI
und Anthropic setzen, prüfen und entfernen. Sie werden in `.env` im Repo-Root
geschrieben (atomar, Rechte `0600`, andere Einträge bleiben unverändert) und
wirken **sofort im laufenden Backend**, ohne Neustart. „Schlüssel prüfen“ ist
eine ausdrückliche Aktion und der einzige Moment, in dem dafür ein Netzaufruf
passiert. Werte werden nie angezeigt oder zurückgegeben.

## KI-Video und Talking Avatar

Im Editor hat jede Szene zwei zusätzliche Visual-Modi:

- **KI-Video** — erzeugt einen 5- oder 10-Sekunden-Clip aus dem Visual-Prompt
  (Text→Video). Ist als Medium ein Bild gewählt, wird daraus ein Video
  (Bild→Video).
- **Sprechender Avatar** — nimmt das unter „Avatar-Bild“ gewählte Foto und
  die Stimme der Szene und erzeugt ein Video mit Lippenbewegungen.

Beides läuft über fal.ai (`FAL_KEY`) und kostet Geld: Die Schätzung steht vor
dem Render im Editor, das Projektbudget gilt hart. Fällt der Dienst aus,
wird die Szene kostenlos mit einem Ersatz gerendert (KI-Bild oder
Motion-Hintergrund bzw. Standbild) und das im Render-Bericht vermerkt.
Modelle und Preise: `CLIPFORGE_FAL_T2V_MODEL`, `CLIPFORGE_FAL_I2V_MODEL`,
`CLIPFORGE_FAL_AVATAR_MODEL`, `CLIPFORGE_PROVIDER_PRICES`
(`fal_video_per_second`, `fal_avatar_per_second`).
**Gegen den echten Dienst noch ungetestet.**

## Stimmklon

Unter **Studio → Einrichtung → Eigene Stimme klonen**: 1–5 Sprachproben,
Erklärung „eigene Stimme“ oder „Erlaubnis der Person (Name)“ und die
Nicht-Täuschungs-Erklärung sind Pflicht. Die Erklärung wird mit Zeitpunkt,
Konto und Prüfsummen der Proben gespeichert. Die Stimme erscheint danach in
der ElevenLabs-Stimmauswahl. Braucht `ELEVENLABS_API_KEY` und einen
ElevenLabs-Tarif mit Stimmklon. **Ungetestet gegen den echten Dienst.**

## YouTube-Import

Workflow „YouTube → Shorts“: Link einfügen, bestätigen, dass du Rechteinhaber
bist (oder die Erlaubnis hast), Videodatei hochladen (eigene Videos: YouTube
Studio → Herunterladen), optional Untertitel aus YouTube Studio
(`.srt`/`.vtt`). ClipForge holt nur Titel und Kanal über YouTubes öffentliche
oEmbed-Schnittstelle und lädt **nichts** von YouTube herunter.

## TikTok

Unter **Studio → Einrichtung → Plattform-Konten** das TikTok-Konto verbinden
(braucht eine eigene TikTok-Entwickler-App: `TIKTOK_CLIENT_KEY`,
`TIKTOK_CLIENT_SECRET`, Redirect-URI
`http://127.0.0.1:8000/api/studio/accounts/tiktok/callback`). Danach in
**Analytics → Entwürfe** „In TikTok-Entwürfe hochladen“. Das Video landet in
den Entwürfen deines Kontos; veröffentlichen tust du es in der TikTok-App.
**Ungetestet gegen die echte API.**

## Lokale Stimmen

| Stimme | System | Einrichtung |
|---|---|---|
| eSpeak NG | Windows, macOS, Linux | automatisch (pip-Paket `espeakng-loader`) |
| Windows-Systemstimmen | Windows | automatisch; weitere Sprachen über Windows-Sprachpakete |
| macOS `say` | macOS | automatisch |
| Piper | alle | `pip install piper-tts` und Stimmmodell laden, siehe `INSTALL.md` |

Das Sprechtempo (0,5–2,0) steht im Editor unter „Stimme“.

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

- Das **Budgetlimit** gehört zum einzelnen Projekt und gilt für Stimme und
  Bilder zusammen, über alle Renders und Wiederholungen hinweg. Es steht
  standardmäßig auf 0; mit 0 wird nie ein kostenpflichtiger Provider aufgerufen.
- Vor **jedem** kostenpflichtigen Aufruf wird der erwartete Betrag unter einer
  Projekt-Sperre reserviert. Passt er nicht mehr ins Budget, wird keine Anfrage
  gesendet und der Render endet mit `budget_exceeded` samt benötigtem und
  verbleibendem Betrag. Nach Erfolg werden die Kosten verbucht, nach einem
  Fehler wird die Reservierung freigegeben.
- Fertige Szenen bleiben im Cache. Nach einer Budgeterhöhung zahlt „Erneut
  versuchen“ nur noch die fehlenden Teile.
- Die verbuchten Beträge sind Schätzungen nach Listenpreis, keine
  Abrechnungsdaten des Anbieters.
- Preise sind Schätzwerte. Mit `CLIPFORGE_PROVIDER_PRICES` (JSON) lassen sie
  sich anpassen.
- Fällt ein Provider aus, wird die Szene lokal gerendert und der Vorfall im
  Render-Bericht vermerkt.

## Auflösung und 4K

720p, 1080p und 4K werden lokal in der echten Zielauflösung gerendert
(9:16 → 2160×3840, 16:9 → 3840×2160, 1:1 → 2160×2160, 4:5 → 2160×2700).
Ist ein eigenes Medium, ein Gameplay-Video oder ein KI-Bild kleiner als die
Zielauflösung, wird es **kontrolliert hochskaliert**, und der finale
Render-Bericht nennt Datei, Ausgangsgröße und Faktor. OpenAI-Bilder kommen mit
höchstens 1536 Pixeln Kantenlänge und werden bei 4K daher immer hochskaliert.
Vorschau-Renders sind bewusst klein und melden das nicht.

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
| `CLIPFORGE_STUDIO_MAX_SOURCE_MINUTES` | 180 | maximale Dauer von Audio-/Video-Quellen |
| `CLIPFORGE_PROVIDER_MAX_RESPONSE_MB` | 50 | Größenlimit für Antworten von Cloud-Providern; größere Antworten werden verworfen, nicht abgeschnitten |
| `CLIPFORGE_RENDER_TIMEOUT` | 1800 | Zeitlimit je FFmpeg-Lauf der Shorts-Pipeline (Sekunden, min. 60) |
| `CLIPFORGE_ENV_FILE` | `.env` im Repo-Root | Ablage der API-Schlüssel |
| `CLIPFORGE_PROVIDER_PRICES` | – | JSON mit eigenen Preisschätzungen |
| `CLIPFORGE_FLAG_<NAME>` | – | überschreibt ein Flag aus `feature_flags.json` |

Feature Flags stehen in `feature_flags.json` im Repo-Root.

## Schutz der lokalen API

Mutierende Requests brauchen ein Token, fremde Webseiten werden abgewiesen.
Details und Konfiguration: [`LOCAL_API_SECURITY.md`](LOCAL_API_SECURITY.md).

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
