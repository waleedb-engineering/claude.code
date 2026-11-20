# ClipForge 3.0 — Architektur

Grundsatz: bestehende Architektur (FastAPI + Next.js + FFmpeg + JSON-Speicher +
Task-Queue) beibehalten, neue Module klar getrennt daneben.

```
web/ (Next.js 16)                         api/ (FastAPI)
 studio/streams      ─────────────┐        clipforge/stream/      Import, Chat-Replay, Signale,
 studio/projects/[id] (Editor,    │          chat.py signals.py   Scoring, Clipping, Live
   Timeline, AgentChat)           │          scoring.py analyze.py live.py service.py
 studio/setup (Modelle, Skills,   ├─/api/──► clipforge/agent/       KI-Assistent (Planer, Werkzeuge)
   Provider-Matrix, Konten)       │          planner.py tools.py service.py
 studio/analytics, trends, …      │        clipforge/skills.py    Skill-Registry (nur Markdown)
                                  │        clipforge/studio/      Projekte, Render, Provider,
                                  │          provider_matrix.py   Publishing, Kosten, Workspaces …
                                  │          thumbnails.py
                                  │        clipforge/render.py    bestehender Shorts-Renderer
                                  └─────── jobs.py (Job-Registry) Clip-Editor, Publishing, Analytics
```

## Datenfluss Stream → Clips

```
Upload VOD/OBS + Chat-Export ──► stream/service (Rechtebestätigung, Typprüfung)
   └► Task stream_analyze: signals (FFmpeg-Pipes) + chat.per_second
        → scoring.score_timeline → pick_candidates
        → Transkription nur der Kandidaten-Fenster → zweites Scoring
        → clip_bounds (Satzgrenzen) → dedupe → analysis.json
   └► manuelle Korrektur / KI-Assistent (trim_clip) → analysis.json
   └► Task stream_render: render_clip (9:16, Smart-Reframe, Pausen, Captions)
        → registry.import_completed → normaler Job (Editor/Publishing/Analytics)
Live: Twitch-IRC → chat_live.jsonl → SpikeDetector → Warteschlange → Schnitt aus OBS-MKV
```

## Ein Bearbeitungszustand

Editor-Oberfläche und KI-Assistent schreiben über dieselben Funktionen
(`StudioService.update_project` mit `expected_version`, `StreamService.update_highlight`).
Der Assistent speichert vorher offene Editor-Änderungen; Rückgängig nutzt die
vorhandene Versionsgeschichte.

## Sicherheit (übergreifend)

| Thema | Umsetzung |
|---|---|
| SSRF | safe_fetch (öffentliche IPs, Redirect-Limit), feste API-Hosts, Ollama nur localhost, Skills nur github.com |
| Uploads | Typ- und Größenprüfung, ffprobe-Validierung, Zip-Slip-Schutz, Pfad-Normalisierung (`safe_child`) |
| Benutzer | getrennte Workspaces (ContextVar), Jobs mit Besitzer, Admin-Rollen für Skill-Import |
| Schlüssel | je Benutzer verschlüsselt, nie im Frontend, nie in Logs |
| Kosten | Reservierung im Projektbudget vor bezahlten Aufrufen, Kostenbestätigung je Aktion |
| Agent | nur freigegebene Werkzeuge, Schema-Validierung, Bestätigung für Render/Export |
| Fremdcode | Skills: nur Markdown; keine Ausführung, keine Installationsskripte |
| Hintergrund | persistente Tasks, Recovery, kooperativer Abbruch, Live-Chat sofort auf Platte |
