# KI-Assistent im Editor

Ein Chat im Projekt-Editor und auf der Stream-Seite. Code: `api/clipforge/agent/`,
Oberfläche: `web/src/components/studio/AgentChat.tsx`.

## Ablauf

```
Befehl → Planer (Regeln | Ollama | Claude | OpenAI) → Plan aus freigegebenen
Werkzeugen → Validierung (Schema, Bereiche, Kontext) → Anzeige → Nutzer klickt
„Ausführen“ (Render/Export zusätzlich bestätigen) → Werkzeuge ändern das Projekt
über denselben Speicherweg wie der Editor → Editor lädt neu → „Rückgängig“
stellt die Version vor der Ausführung wieder her
```

- **Ein Zustand:** Werkzeuge rufen `StudioService.update_project` (Versionsschutz,
  Snapshot) bzw. den Stream-Service — wie die Oberfläche. Vor dem Ausführen
  speichert der Editor offene Änderungen.
- **Keine Shell, kein freies FFmpeg:** nur Werkzeuge aus `tools.TOOLS`. Vom LLM
  vorgeschlagene unbekannte Werkzeuge oder ungültige Parameter werden verworfen
  und im Chat begründet.
- **Chatverlauf** je Projekt/Quelle (`<studio>/agent/<art>_<id>.json`, 200 Einträge).
- **Kosten:** Regeln und Ollama kostenlos; Claude/OpenAI nur mit Kostenbestätigung
  je Nachricht und Reservierung im Projektbudget (Budget 0 → abgelehnt).

## Werkzeuge

| Projekt | Stream |
|---|---|
| get_project_state, trim_scene, split_scene, merge_scenes, move_scene, delete_scene, set_scene_text, remove_silence, change_caption_style, add_transition, adjust_audio, generate_hook_variants, render_preview, export_video (Bestätigung) | find_highlights, list_highlights, trim_clip, render_clips (Bestätigung) |

Ehrlich **nicht** verfügbar (der Chat sagt das): Gesichts-Zoom auf Ereignisse,
Untertitel-Farben (kommen aus dem Brand-Kit), Übersetzen per Chat (dafür gibt
es den Workflow „Video übersetzen“).

## Planer

| Engine | Kosten | Stand |
|---|---|---|
| Regelbasiert (de/en) | 0 | real getestet mit den Beispielsätzen aus der Anforderung |
| Ollama (localhost, Tool-Calling) | 0 | Protokoll nachgebildet getestet; kein echtes Modell in der Testumgebung |
| Claude (Tool-Use) | ca. 0,01 USD/Nachricht | nur nachgebildet getestet |
| OpenAI (Function-Calling) | ca. 0,005 USD/Nachricht | nur nachgebildet getestet |

Ollama ist nur auf localhost erlaubt (`CLIPFORGE_OLLAMA_URL`, Modell
`CLIPFORGE_OLLAMA_MODEL`, Standard `qwen2.5:7b`).

## Tests

`api/tests/test_editor_agent.py` (Planer, Validierung, Ausführung, Undo,
Bestätigung, Kosten, LLM-Abwehr, Stream-Ablauf bis zum gerenderten Job),
`web/e2e/flow-k-editor-agent.spec.ts` (Browser: Befehl → Ausführen → Undo).
