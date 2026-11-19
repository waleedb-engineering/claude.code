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

## Status

| Teil | Stand |
|---|---|
| Chat-Import (4 Formate) | real getestet |
| Signale, Scoring, Grenzen, Dedupe | real getestet (synthetischer Stream, echtes FFmpeg) |
| Render als Job (9:16, Captions) | real getestet |
| Live: IRC-Protokoll | gegen lokalen IRC-Testserver getestet, **nicht gegen Twitch live** |
| Live: Schnitt aus wachsender Aufnahme | real getestet |
| Transkript-Signale mit echtem Whisper | Logik getestet (Mock-Transkript); echtes Modell nicht in CI |
| Qualität auf echten Streams | **nicht verifiziert** — braucht echte VODs + Chat-Exporte |
