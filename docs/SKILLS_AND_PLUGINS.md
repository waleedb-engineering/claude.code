# Skills und Erweiterungen

## Fünf Arten — strikt getrennt

| Art | In ClipForge | Ausführung |
|---|---|---|
| 1. Skills (Anleitungen) | Skill-Registry (`api/clipforge/skills.py`) | **nie** — nur Text als Hinweis für den LLM-Planer |
| 2. Werkzeuge (Code) | nur eingebaute Agent-Werkzeuge (`api/clipforge/agent/tools.py`) | ja, nach Validierung + Bestätigung |
| 3. MCP-Server | nicht eingebunden | ClipForge startet keine externen Prozesse |
| 4. Externe APIs | Provider-Verwaltung / Provider-Matrix | nur mit Schlüssel, Budget, Bestätigung |
| 5. Lokale Modelle | Modell-Katalog (feste URLs, Prüfsummen) | lokal, nach Zustimmung zum Download |

Ein importierter Skill ist **keine** Softwarefunktion: Er beeinflusst nur,
welche der vorhandenen Werkzeuge der Planer vorschlägt und wie.

## Registry

- Quellen: ZIP-Upload oder `https://github.com/<owner>/<repo>` (+ Unterordner).
  Git-Klon mit `--depth 1`, `core.symlinks=false`, ohne LFS, ohne Ausführung.
- Übernommen: `SKILL.md`, weitere `.md`, Lizenzdatei (≤ 200 KB, ≤ 50 Dateien).
  Alles andere wird verworfen und unter „Nicht übernommen“ angezeigt.
- Metadaten: Name, Beschreibung, Version (Frontmatter oder Inhalts-Hash), Lizenz,
  Quelle + Commit, referenzierte Werkzeuge, Warnungen, Import-Zeitpunkt.
- Kompatibilität: `clipforge-api` in der Frontmatter (aktuell 1); Abweichung → Warnung.
- Berechtigungen: referenzierte Werkzeuge müssen eingebaut sein; sonst gesperrt.
- Lizenz: ohne Lizenz gesperrt; nicht permissive Lizenzen → Warnung.
- Neu importierte Skills sind deaktiviert; Aktivieren ist eine bewusste Entscheidung.
- Updates nur manuell: erneuter Import zeigt „geändert“ mit altem/neuem Hash.
- Online-Betrieb: Import nur für Administratoren; Skills je Benutzerbereich.

## Geprüfte Skill-Quellen

Siehe `GITHUB_REPOSITORY_RESEARCH.md`. Echt importiert und geprüft:
`iamaanahmad/agents-video-editing-skills` (MIT, 14 Skills, Skripte verworfen).
`remotion-dev/skills` bewusst nicht empfohlen (zielt auf Remotion als
Render-Engine; Remotion hat eigene Lizenzbedingungen).
