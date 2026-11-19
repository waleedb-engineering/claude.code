# ClipForge 3.0 — Roadmap

## Erledigt (Branch `claude/clipforge-3`)

1. Bestandsaufnahme + GitHub-Recherche (20 Repos, Lizenzmatrix)
2. Stream Intelligence: Chat-Import, multimodales erklärbares Scoring,
   satzgenaue Clips, Render als Job, Live-Modus (Twitch-IRC + OBS)
3. KI-Assistent mit kontrolliertem Tool-Calling (Regeln/Ollama/Claude/OpenAI)
4. Skill-Registry (nur Markdown), Provider-Matrix
5. Editor: Timeline, Tastenkürzel, Thumbnail-Vorschläge

## Nächste Schritte (priorisiert)

| Prio | Aufgabe | Voraussetzung |
|---|---|---|
| 1 | Auswertung mit echten eigenen VODs + Chat-Exporten, Gewichte justieren | 2–3 echte Streams vom Nutzer |
| 2 | Ollama live testen (z. B. qwen2.5:7b) und Prompt/Tool-Schema nachschärfen | Ollama auf dem Mac |
| 3 | Twitch-IRC einmal live gegen einen echten Kanal | Netzzugang, öffentlicher Kanal |
| 4 | Punch-in-Zoom als Renderer-Effekt (dann auch per Chat steuerbar) | – |
| 5 | Audio-Ereignis-Klassifikation (YAMNet, Apache-2.0) für Lachen/Jubel/Schreie | ONNX-Export prüfen |
| 6 | YouTube-Live-Chat über die Data API (liveChatMessages) | API-Schlüssel, Kontingent |
| 7 | Mehrspur-Timeline (freie Audio-/B-Roll-Spuren) | größerer Editor-Umbau |
| 8 | Cloud-Anbieter live verifizieren (fal.ai, ElevenLabs, Claude, Plattformen) | Freigabe bezahlter Tests |
| 9 | Persistenz auf SQLite/PostgreSQL bei Mehrbenutzer-Last | Entscheidung Hosting |

## Bewusst nicht geplant

- Herunterladen fremder Streams (yt-dlp/streamlink) — Nutzungsbedingungen
- Ausführen von Skill-Skripten oder MCP-Servern aus dem Internet
- AGPL-Code (OpenChatCut) oder unlizenzierte Repos übernehmen
