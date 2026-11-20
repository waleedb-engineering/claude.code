# GitHub-Recherche für ClipForge 3.0

Stand: 19.11.2026. Methode: jedes Repository flach geklont (`git clone --depth 1`,
nur gelesen, **kein Code ausgeführt**, keine Installationsskripte gestartet).
Die GitHub-REST-API war für fremde Repos in der Entwicklungsumgebung gesperrt;
Sterne/Issues konnten daher nicht ausgewertet werden. Lizenz = Inhalt der
LICENSE-Datei im Repo-Wurzelverzeichnis.

## Vergleichsmatrix

| Repository | Lizenz | Letzter Commit | Umfang / Sprache | Ansatz | Entscheidung |
|---|---|---|---|---|---|
| guleriaakshit/clipper | MIT | 2026-11-17 | 47 Dateien, Python | Chat-Spikes (2× Durchschnitt), Reaktionsphrasen, Twitch/YouTube/Kick, VOD + live; lädt über yt-dlp, Chat über TwitchDownloader/inoffizielle Wege | **Ideen übernommen** (Reaktionskategorien, eindeutige Chatter, Spike-Dauer). Kein Code übernommen. Plattform-Downloads nicht übernommen (siehe unten) |
| st1fo/stream-clipper | **keine Lizenz** | 2026-11-18 | 62 Dateien, Python | Live-Ringpuffer (5 min), Chat-Spike-z-Score mit Poisson-Untergrenze, Chat-Verzögerung 6 s, Ollama-Bewertung | **Nicht verwendbar** (ohne Lizenz = alle Rechte vorbehalten). Allgemeine, nicht schützbare Ideen (Verzögerung abziehen, Rauschuntergrenze) unabhängig selbst umgesetzt |
| Blackwellcode/streamvault | MIT | 2026-11-14 | 204 Dateien, Python | Selbstgehosteter Rekorder/Archiv mit Chat-Replay über Twitch-IRC | Ansatz Twitch-IRC (offiziell, anonym lesbar) für den Live-Modus übernommen — eigene Implementierung |
| Aadi1659/liveclip | MIT | 2026-11-19 | 8 Dateien | Streamlink-Aufnahme + Live-Chat + FFmpeg + Whisper | Bestätigt das Live-Konzept; Streamlink-Aufnahme fremder Streams nicht übernommen |
| lavisansoi/spikeclip | **keine Lizenz** | 2026-11-16 | 5 Dateien | Chat-Replay → Spike → −20 s/+10 s | Nicht verwendbar; Fenster-Idee allgemein |
| Angel-Casas/Hypeline | MIT | 2026-09-25 | 313 Dateien, TS (Browser-PWA) | Twitch-Chat-Heatmap, TwitchDownloader-JSON, Lach-/Emote-Lexika | **Ideen übernommen**: Heatmap-Darstellung, TwitchDownloader-Chatformat als Import |
| sidgaikwad/stream-clipper | **keine Lizenz** | 2026-11-03 | 342 Dateien, TS | Twitch/Kick/YouTube, claude-CLI-Bewertung | Nicht verwendbar |
| Solacecash/AlphaNovaClip | MIT | 2026-09-01 | Rust/Axum + Frontend | Breites Toolkit, Gemini-lastig | Überschneidung groß, Architekturwechsel nötig → nicht integriert |
| artbyjazi/autoclip | MIT | 2026-08-01 | 100 Dateien, Python | Whisper + LLM-Ranking, Sprecher-Tracking (MediaPipe), Reframe | Konzept „LLM wählt Momente, regelbasierter Fallback“ deckt sich mit vorhandenem Analyzer; MediaPipe nicht nötig (YuNet vorhanden) |
| EtienneLescot/axcut | **keine Lizenz** | 2026-07-01 | 103 Dateien | Agentischer Schnitt | Nicht verwendbar |
| 0xsline/OpenChatCut | **AGPL-3.0** | 2026-11-12 | 2860 Dateien, TS | Chat-gesteuerter Editor | **Nicht integriert**: AGPL würde ClipForge im Online-Betrieb offenlegungspflichtig machen |
| MakeMyClip/editor | MIT | 2026-11-15 | 255 Dateien, TS | Browser-Editor | Zu groß/fremde Architektur; UI-Ideen (Timeline-Spuren) |
| PansaLegrand/dojo-video-agent | MIT | 2026-11-19 | 1182 Dateien, TS | Video-Agent mit Werkzeugen | Ideen für Tool-Katalog des Editor-Agenten |
| saranshhardaha/clipchat | MIT | 2026-03-30 | 162 Dateien, TS | Chat → FFmpeg-Befehle | **Bewusst anders**: wir lassen das Modell keine Shell-/FFmpeg-Befehle erzeugen, nur validierte Werkzeugaufrufe |
| anthropics/skills | Apache-2.0 je Skill (Repo ohne Wurzel-Lizenz) | 2026-11-16 | Skills (Markdown + Skripte) | Allgemeine Skills (Dokumente, MCP-Builder, Frontend) | Keine Video-Skills; als Format-Referenz für die Skill-Registry genutzt |
| remotion-dev/skills | keine Wurzel-Lizenz; Remotion selbst hat eine Firmenlizenz-Pflicht ab bestimmter Teamgröße | 2026-11-18 | Skills für Remotion | Programmatische Videos in React | **Nicht integriert**: zusätzliche Render-Engine + Lizenzfrage; FFmpeg-Pipeline bleibt |
| Melvynx/video-agent-skills | MIT | 2026-11-06 | Skills | Agenten-Anleitungen für Videoschnitt | Kandidat für die Skill-Registry (nur Anleitung, kein Code) |
| iamaanahmad/agents-video-editing-skills | MIT | 2026-11-11 | Skills | dto. | Kandidat für die Skill-Registry |
| clonn/awesome-agent-video-skills | MIT | 2026-10-10 | Linkliste | Übersicht | Quelle für weitere Recherche |
| public-apis/public-apis | MIT | 2026-11-19 | Linkliste | Kostenlose APIs | Quelle für Provider-Recherche |

## Grundsatzentscheidung: Kein Herunterladen fremder Streams

Fast alle Stream-Clipper laden Videos über `yt-dlp`/`streamlink` und Chat-
Verläufe über inoffizielle Endpunkte (Twitch-GQL, YouTube-Innertube). Das
widerspricht den Nutzungsbedingungen von YouTube/Twitch, wenn man nicht
Rechteinhaber ist, und die Endpunkte brechen ohne Vorwarnung. ClipForge 3.0
geht deshalb so vor:

- **Video:** eigener Upload (VOD-Download aus dem eigenen Twitch-/YouTube-
  Dashboard, OBS-Aufnahme) mit Rechtebestätigung — wie der bestehende
  YouTube-Import.
- **Chat (VOD):** Import der vom Nutzer exportierten Datei. Unterstützt:
  TwitchDownloader-JSON (MIT-Tool, das der Nutzer selbst ausführt),
  chat-downloader/yt-dlp-Live-Chat-JSON, allgemeines JSON/CSV/JSON-Lines.
- **Chat (live):** Twitch-IRC (offizielle, dokumentierte Schnittstelle,
  anonymes Lesen erlaubt); YouTube Data API `liveChatMessages` (API-Schlüssel,
  Kontingent); Kick: keine stabile öffentliche Chat-API → Datei-Import.
- **Video (live):** wachsende lokale OBS-Aufnahme (MKV) als Ringpuffer.

## Weitere geprüfte Bausteine (nicht integriert, nur bewertet)

| Baustein | Lizenz | Bewertung |
|---|---|---|
| TwitchDownloader (CLI) | MIT | Nutzer exportiert damit eigene Chat-Replays; ClipForge liest das JSON |
| chat-downloader | MIT | dto. für YouTube-Chat-Replays (Nutzer führt es selbst aus) |
| yt-dlp | Unlicense | nicht eingebunden (ToS-Gründe, s. o.) |
| streamlink | BSD-2 | nicht eingebunden (ToS-Gründe) |
| PySceneDetect | BSD-3 | nicht nötig: FFmpeg-`scdet` liefert Szenenwechsel ohne neue Abhängigkeit |
| YAMNet (Audio-Ereignisse inkl. Lachen/Jubel) | Apache-2.0 | sinnvolle spätere Ergänzung; kein vertrauenswürdiger ONNX-Export ohne zusätzliche Abhängigkeit gefunden → vorerst Heuristik, als solche gekennzeichnet |
| Ollama | MIT | lokale LLMs für den Editor-Agenten (optional, über HTTP auf localhost) |
