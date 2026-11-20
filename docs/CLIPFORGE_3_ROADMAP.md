# ClipForge 3.0 — Roadmap

## Erledigt (Branch `claude/clipforge-3`)

1. Bestandsaufnahme + GitHub-Recherche (20 Repos, Lizenzmatrix)
2. Stream Intelligence: Chat-Import, multimodales erklärbares Scoring,
   satzgenaue Clips, Render als Job, Live-Modus (Twitch-IRC + OBS)
3. KI-Assistent mit kontrolliertem Tool-Calling (Regeln/Ollama/Claude/OpenAI)
4. Skill-Registry (nur Markdown), Provider-Matrix
5. Editor: Timeline, Tastenkürzel, Thumbnail-Vorschläge

## Abnahmerunde (erledigt)

Auswertung/Tuning, synthetischer Testsatz, Varianten, Signal-Cache, Zoom,
Untertitel-Aussehen, Soundeffekte, Lautheit, 10 neue Agent-Werkzeuge,
Ollama-Status/Fallback, YouTube-Live-Chat (Data API), Live-Warteschlange,
4 neue Vorlagen, Skill-Abhängigkeiten — siehe `CLIPFORGE_3_FINAL_REPORT.md`.

## Nächste Schritte (priorisiert)

| Prio | Aufgabe | Voraussetzung |
|---|---|---|
| 1 | Echte VODs markieren, auswerten, Gewichte schätzen | 2–3 eigene Streams + Chat-Exporte |
| 2 | Ollama, faster-whisper, Twitch-IRC auf dem Mac prüfen | Mac, Netz |
| 3 | YouTube-Live-Chat gegen echte API | API-Schlüssel, eigener öffentlicher Stream |
| 4 | YAMNet als ONNX | lokaler Export, Prüfsumme |
| 5 | Mediathek-Seite, Design-Durchgang | – |
| 6 | Mehrspur-Timeline (freie Spuren, Keyframes) | Schema-Migration |
| 7 | Hardware-Beschleunigung | Messung auf Zielrechner |
| 8 | Cloud-Anbieter + Publishing live | Freigabe bezahlter Tests / Veröffentlichung |
| 9 | SQLite/PostgreSQL | Mehrbenutzer-Hosting |

## Bewusst nicht geplant

- Herunterladen fremder Streams (yt-dlp/streamlink) — Nutzungsbedingungen
- Ausführen von Skill-Skripten oder MCP-Servern aus dem Internet
- AGPL-Code (OpenChatCut) oder unlizenzierte Repos übernehmen
