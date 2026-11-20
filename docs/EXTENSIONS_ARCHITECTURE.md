# Ausführbare Erweiterungen — Architekturentwurf (nicht umgesetzt)

Stand: **Entwurf**. ClipForge führt heute **keinen** fremden Code aus. Skills sind
reiner Text (`SKILLS_AND_PLUGINS.md`). Dieser Entwurf beschreibt, wie ausführbare
Erweiterungen später kontrolliert möglich wären — getrennt von Skills.

## Grundsätze

1. **Getrennte Art**: „Extension“ ≠ „Skill“. Eigene Registry, eigene Oberfläche,
   eigener Warnhinweis. Ein Skill kann nie Code nachladen.
2. **Kein Netz-Import zur Laufzeit**: nur lokal vom Administrator installierte
   Pakete mit festgeschriebener Version und SHA-256-Prüfsumme.
3. **Prozess-Isolation**: jede Extension als eigener Prozess (kein Import in den
   API-Prozess), Kommunikation nur über JSON auf stdin/stdout (JSON-RPC 2.0).
4. **Sandbox**: Container/`bwrap`/macOS-`sandbox-exec` mit nur-lesbarem Zugriff auf
   den übergebenen Clip-Ausschnitt, Schreibzugriff nur auf ein Temp-Verzeichnis,
   **kein Netz** (außer ausdrücklich deklariert und vom Admin bestätigt),
   CPU-/RAM-/Zeitlimits.
5. **Deklarierte Fähigkeiten** im Manifest (`extension.json`): Eingaben
   (z. B. `video_segment`, `transcript`), Ausgaben (z. B. `overlay.png`,
   `subtitle_track`), benötigte Rechte. Was nicht deklariert ist, wird verweigert.
6. **Ergebnisse als Daten**: Eine Extension liefert Dateien/JSON, die ClipForge
   validiert und über die normalen Editor-Funktionen übernimmt (Versionsschutz,
   Undo). Sie verändert nie direkt Projektdateien.
7. **Agent-Anbindung** nur als zusätzliches Werkzeug mit JSON-Schema, immer mit
   Bestätigung, Kosten-/Zeitangabe und Protokoll.

## Ablauf

```
Admin installiert Paket (Prüfsumme) → Manifest-Prüfung → deaktiviert
→ Admin aktiviert (Rechte-Dialog) → Agent/Editor ruft Werkzeug auf
→ Sandbox-Prozess mit Eingabedateien → JSON-Ergebnis → Validierung → Übernahme als neue Projektversion
```

## Warum nicht jetzt

Der Nutzen ist ohne konkrete Erweiterung nicht belegt, das Risiko (fremder Code
auf dem Rechner des Nutzers) aber hoch. MCP-Server und GitHub-Skripte bleiben
daher bewusst ausgeschlossen (Status E), bis ein konkreter Bedarf besteht.
