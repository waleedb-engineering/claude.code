# Stream Intelligence

Findet Highlights in Streams/VODs aus mehreren Signalen und macht daraus
vertikale Clips. Oberfläche: **Studio → Streams**. Code: `api/clipforge/stream/`.

## Quellen (rechtssicher)

| Quelle | VOD | Live | Wie |
|---|---|---|---|
| Twitch | ja | Chat: ja (IRC, Echtzeit) | Video: eigenes VOD aus dem Creator-Dashboard; Chat: TwitchDownloader-JSON |
| YouTube | ja | nein (Live-API noch nicht angebunden) | Video: YouTube Studio → Herunterladen; Chat: chat-downloader / yt-dlp-JSON |
| Kick | ja | nein | Video herunterladen; Chat als JSON/CSV (keine stabile öffentliche API) |
| OBS | ja | Video: ja (wachsende MKV, nur lokal) | Pfad zur Aufnahme |
| Upload | ja | – | beliebiges eigenes Video |

ClipForge lädt **keine** fremden Streams herunter (Nutzungsbedingungen) und
fragt vor jeder Analyse eine Rechtebestätigung ab.

## Signale (je Sekunde, alles lokal)

| Gruppe | Signal | Messung |
|---|---|---|
| Chat | Aktivität | Nachrichten/s, robuster z-Wert gegen gleitenden Median (±150 s) |
| Chat | verschiedene Chatter | eindeutige Absender/s |
| Chat | Reaktionen | Kategorien Lachen/Hype/Schock/„Clip it“ minus negativ (Emotes + Phrasen de/en) |
| Chat | Begriffe | häufigste Wörter im Ausbruchsfenster |
| Audio | Lautstärke | dBFS (16 kHz mono), z-Wert |
| Audio | Lautstärkesprung | Anstieg über 2 s |
| Audio | laut + hell | Lautstärke-z ∧ spektraler-Schwerpunkt-z (Schrei/Jubel-**Heuristik**) |
| Audio | Spannung | ≥ 3 s Stille direkt vor einem Sprung |
| Video | Bewegung | mittlere Bilddifferenz (2 fps, 64×36) |
| Video | Szenenwechsel | Bilddifferenz ≫ Median |
| Transkript | Aussagen | Reaktionsphrasen, Ausrufe, Frage→Antwort, eigene Stichwörter |

Nicht umgesetzt (zu unzuverlässig ohne zusätzliche Modelle): Gesichtsausdrücke,
spielspezifische Ereignisse, echte Lach-/Schrei-Klassifikation (YAMNet als
späterer Kandidat, siehe GITHUB_REPOSITORY_RESEARCH.md).

## Scoring

`score = Σ gewicht_i × min(max(z_i, 0), 4)/4 × 100` (über 3 s geglättet).
Standardgewichte: Chat 35 %, Audio 35 %, Video 15 %, Transkript 15 %. Fehlt
ein Signal, werden die übrigen neu normiert. Kandidaten = lokale Maxima mit
mindestens 30 s Abstand; jede Begründung nennt die beitragenden Signale mit
Punkten und z-Wert, Chat-Kennzahlen (Rate vs. Grundrate) und Transkript-Funde.
Der Score ist eine **Rangfolge**, keine Viralitäts-Wahrscheinlichkeit.

**Chat-Verzögerung:** Chat reagiert Sekunden nach dem Ereignis. Die
Verzögerung wird per Kreuzkorrelation zwischen Chat-Rate und Lautstärke
geschätzt (nur bei klarer Korrelation ≥ 0,2), sonst 5 s; manuell setzbar.

## Clipping

1. Ereigniszeit (Chat bereits verschoben) → Fenster `−pre … +post` (Standard 10/8 s).
2. Transkription nur der Kandidaten-Fenster (±40 s, faster-whisper lokal) —
   auch 3-Stunden-Streams bleiben schnell.
3. Start an Satzanfang/Pause, Ende an Satzende (kein abgeschnittener Satz);
   endet das Fenster in einer Pause, endet der Clip am Satzende.
4. Duplikate (Überlappung > 40 % des kürzeren Clips) entfernt.
5. Manuelle Korrektur der Grenzen, Schnellvorschau (360p).
6. Render über den bestehenden Shorts-Renderer: 9:16 mit Smart-Reframe
   (Gesicht/Bewegung), Pausen entfernen, Karaoke-Captions → normaler Job
   (Clip-Editor, Publishing, Analytics gelten unverändert).

## Live-Modus

- Twitch-Chat über IRC (anonym, `justinfan`), Neuverbindung mit Backoff.
- Jede Nachricht sofort in `chat_live.jsonl` (kein Verlust bei Absturz).
- Alle 2 s: Rate der letzten 3 s gegen die Grundrate der letzten 5 min
  (z ≥ 3, mind. 8 Nachrichten, 30 s Abklingzeit).
- Clip-Warteschlange: geschnitten wird, sobald die OBS-Aufnahme weit genug ist
  (wachsende MKV ohne Dauer im Kopf → verstrichene Zeit − 3 s Puffer).
- Stoppen übernimmt Chat und Aufnahme als Quelle → volle VOD-Analyse mit
  allen Signalen danach möglich.
- **YouTube-Live-Chat** über die offizielle Data API v3 (`videos.list` →
  `activeLiveChatId`, dann `liveChat/messages` im Server-Takt, mind. 5 s,
  Standard 10 s). Zeitstempel = `publishedAt`. Kontingent: ~5 Einheiten je
  Abfrage → bei 10 s Takt ≈ 1 800 Einheiten/Stunde (Tageskontingent 10 000).
  Braucht `YOUTUBE_API_KEY`; nur öffentliche Streams (private brauchen OAuth —
  nicht angebunden). Fehler (Kontingent, Chat beendet, Schlüssel) erscheinen im
  Live-Status, Twitch/OBS laufen weiter.
- Warteschlange: höchstens **ein** Schnitt pro Takt (nie mehrere FFmpeg parallel),
  Obergrenze 20 wartende Clips; Überlauf → Status `skipped` (Marke bleibt erhalten,
  später aus der VOD-Analyse schneiden). Status je Clip:
  `waiting_for_recording` (mit Platz), `cut`, `failed`, `marked`.

## Auswertung und Tuning (echte Daten)

1. Analyse laufen lassen, dann je Highlight **„✓ echtes Highlight“ / „✗ kein
   Highlight“** klicken und verpasste Momente mit Start/Ende ergänzen
   (`labels.json`).
2. **„Auswerten“** zeigt Präzision, Recall, F1, Ø Zeitabweichung und ob der Clip
   das Ereignis vollständig enthält (Toleranz 5 s).
3. Ab zwei markierten Streams: **„Gewichte schätzen“** (Rastersuche über die
   Gruppen Chat/Audio/Video). Übernehmen nur, wenn die Leave-one-out-Kreuzprüfung
   besser als der Standard ist; zurücksetzen mit `DELETE /api/studio/stream-weights`.
4. Offline/CLI: `python -m clipforge.stream.evaluate <ordner> [--tune]` mit
   `<name>.mp4`, `<name>.chat.json`, `<name>.labels.json`.

Die Audio-/Videomessung wird je Stream in `signals.json` gespeichert; erneute
Analysen sind dadurch sofort fertig.

## Clip-Varianten

Je Highlight drei Fenster: **Kurz** (≤ 30 s), **Ausgewogen** (Standard), **Mehr
Kontext** (doppelter Vorlauf). Jede mit **Eignung 0–100** aus prüfbaren Kriterien
(Ereignis mit Vor-/Nachlauf enthalten, Satzanfang/-ende, Länge im Zielbereich
15–45 s, Sprechanteil, Signalstärke) — ausdrücklich **keine** Reichweiten- oder
Viralitätsprognose. Mindest- und Maximallänge sind je Analyse einstellbar.

## Audio-Ereignisse (lokale Heuristik)

`stream/audio_events.py` berechnet je Sekunde aus derselben FFmpeg-Pipe zusätzliche
Merkmale (spektrale Flachheit, Silbenmodulation 2–8 Hz, Regelmäßigkeit,
Periodizität/Tonhöhe, Onsets, Gleichmaß) und daraus heuristische
Wahrscheinlichkeiten für **Stille, Sprache, Musik, Lachen, Jubel, Applaus,
Schreien**. Kein Mehraufwand messbar (weiterhin ~80× Echtzeit bei 360p).

| Modus (`audio_events`) | Wirkung |
|---|---|
| `explain` (Standard) | Ereignisse erscheinen in den Begründungen und als Heatmap; Ranking unverändert |
| `rank` | Ereignisse zählen im Score (Gewicht 0,10), laute **Musik** wird gedämpft (×0,3) — leiser, aber bedeutsamer Moment schlägt laute Musik (Test) |
| `off` | aus (auch `CLIPFORGE_AUDIO_EVENTS=0`) |

Warum `explain` Standard ist: Auf den synthetischen Testsätzen (10 min ×3, 60 min)
war mit `rank` **keine** F1-Verbesserung messbar (0,833 bzw. 0,913 in beiden
Modi). Ohne Nachweis auf echten Daten wird das Ranking nicht verändert. Prüfen:
`python -m clipforge.stream.evaluate <ordner> --audio-events rank --compare-audio-events`.

Grenzen: nicht trainiert, an synthetischen Signalen (und eSpeak-Sprache)
abgestimmt; echte Lacher, Publikum und Musik können anders aussehen. Ein
trainiertes Modell (YAMNet/PANNs als ONNX) ließ sich nicht prüfen, weil alle
Modell-Hosts (TF-Hub, Kaggle, Zenodo, Hugging Face) in der Umgebung gesperrt sind.

## Gesichts-Tracking

Render-Modus `track` (Upload, Stream-Render): Gesicht alle 0,5 s erkennen (YuNet,
sonst OpenCV-Haar), Motivbindung an die letzte Position, Lücken bis 2 s halten,
Median gegen Ausreißer, Totzone 3 %, Tempolimit 0,35 Bildbreiten/s → stückweise
lineare Kamerafahrt. Bewegt sich das Motiv kaum (< 6 % der Breite), bleibt es beim
ruhigen statischen Zuschnitt. `manual` nimmt eigene Fokuspunkte. Der Crop liegt im
Filtergraphen vor der Pausenentfernung (Quellzeit) — Bild, Ton und Untertitel
bleiben synchron (Test).

## Status

| Teil | Stand |
|---|---|
| Chat-Import (4 Formate) | real getestet |
| Signale, Scoring, Grenzen, Dedupe | real getestet (synthetischer Stream, echtes FFmpeg) |
| Render als Job (9:16, Captions) | real getestet |
| Live: IRC-Protokoll | gegen lokalen IRC-Testserver getestet, **nicht gegen Twitch live** (Host in der Testumgebung nicht auflösbar) |
| Live: YouTube Data API | gegen nachgebildeten API-Server getestet; **echte API nicht** (kein Schlüssel, kein eigener Live-Stream) |
| Live: Warteschlange/Grenzen | real getestet (`test_stream_live_youtube.py`) |
| Auswertung/Tuning/Varianten | real getestet; Qualität nur auf **synthetischem** Testsatz gemessen (`BENCHMARKS.md`) |
| Fehlende/defekte Daten | real getestet: kaputtes Video, leerer/kaputter Chat, Video ohne Ton, Chat außerhalb der Videozeit |
| Audio-Ereignisse | Funktion real getestet (synthetisch); Qualität auf echten Streams unbelegt |
| Gesichts-Tracking | real getestet mit synthetisch bewegtem Gesicht (Haar und YuNet) |
| Live: Schnitt aus wachsender Aufnahme | real getestet |
| Transkript-Signale mit echtem Whisper | Logik getestet (Mock-Transkript); echtes Modell nicht in CI |
| Qualität auf echten Streams | **nicht verifiziert** — braucht echte VODs + Chat-Exporte |
