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
| get_project_state, trim_scene, split_scene, merge_scenes, move_scene, delete_scene, set_scene_text, remove_silence, change_caption_style, **set_caption_appearance** (Farbe, Hervorhebung, Schrift, Position, Größe), add_transition, adjust_audio (Lautstärken, Sprechtempo, Ducking), **zoom_scene** (Punch-in, Fokus Gesicht/Mitte/Seiten, statisch/einfahrend), **list_audio**, **add_background_music**, **add_sound_effect**, **normalize_loudness**, generate_hook_variants, **generate_title**, **generate_thumbnail**, render_preview, export_video (Bestätigung) | find_highlights, list_highlights, trim_clip, **list_clip_variants**, **set_clip_variant** (kurz/ausgewogen/mehr Kontext), render_clips (Bestätigung) |

**Mehrspur-Timeline** (Production-Runde): timeline_state, timeline_add_media,
timeline_add_text, timeline_edit (move/trim/split/slip/delete/ripple_delete/
duplicate), timeline_keyframe, timeline_track; außerdem create_split_screen und
translate_video (Bestätigung). Die Werkzeuge rufen dieselbe Funktion
(`timeline.apply_op`) wie die Editor-Oberfläche auf.

Jedes Werkzeug ändert echte Projektfelder, die der Renderer nutzt (Belege:
`test_render_effects.py` prüft Zoom-Bildausschnitt, Caption-Layout, Soundeffekt-
Position und Lautheit per FFmpeg).

Beispielbefehle (Regel-Planer, getestet):

| Befehl | Plan |
|---|---|
| „Zoom langsam 1.5x auf das Gesicht in Szene 1“ | zoom_scene(scene 1, 1.5, face, ramp) |
| „Mach die Untertitel gelb, oben und größer“ | set_caption_appearance(color, position, size) |
| „Aktuelles Wort rot hervorheben“ (+ Untertitel) | set_caption_appearance(highlight_color) |
| „Füge Hintergrundmusik hinzu“ / „ohne Musik“ | add_background_music |
| „Soundeffekt boom in Szene 2 bei 1.5 s“ | add_sound_effect |
| „Normalisiere die Lautheit“ | normalize_loudness |
| „Schlag mir einen Titel vor“ / „Erstelle ein Thumbnail“ | generate_title / generate_thumbnail |
| „Clip 3 mit mehr Kontext“ / „Clip 2 in der kürzeren Variante“ | set_clip_variant |
| „Use white captions and highlight important words in yellow.“ | set_caption_appearance(color white, highlight yellow) |
| „Leg das Logo oben rechts drüber und blende es ein“ | timeline_add_media(overlay, top_right, fade) |
| „Text „Abonnieren!“ von 2 bis 5 Sekunden oben in gelb“ | timeline_add_text |
| „Make a split-screen version with gameplay below the facecam.“ | create_split_screen |
| „Translate the video to German and generate a suitable voiceover.“ | translate_video(de, dub) |

Ehrlich **nicht** verfügbar (der Chat sagt das): Objektverfolgung im Editor-Chat
(Gesichts-Tracking gibt es als Render-Modus `track` für Clips), B-Roll per Chat
(im Editor über „B-Roll vorschlagen“), Zoom auf einen exakten Moment innerhalb
einer Szene (Zoom gilt je Szene; dafür Timeline-Keyframes).

**Gedächtnis:** LLM-Planer erhalten die letzten Wechsel wörtlich und ältere als
Zusammenfassung (ausgeführte Werkzeuge, frühere Wünsche), je Projekt.
**Gemini** ist als dritter Cloud-Planer angebunden (offizielle generateContent-
API); weil der Preis vom Google-Tarif abhängt, verlangt jede Nachricht eine
ausdrückliche Bestätigung — es wird kein Betrag erfunden.

## Planer

| Engine | Kosten | Stand |
|---|---|---|
| Regelbasiert (de/en) | 0 | real getestet mit den Beispielsätzen aus der Anforderung |
| Ollama (localhost, Tool-Calling) | 0 | gegen nachgebildeten Ollama-Server (echtes HTTP) getestet; **kein echtes Modell** in der Testumgebung |
| Claude (Tool-Use) | ca. 0,01 USD/Nachricht | nur nachgebildet getestet |
| OpenAI (Function-Calling) | ca. 0,005 USD/Nachricht | nur nachgebildet getestet |

### Ollama

- nur localhost (`CLIPFORGE_OLLAMA_URL`); Timeout `CLIPFORGE_OLLAMA_TIMEOUT` (120 s)
- Modellwahl: `CLIPFORGE_OLLAMA_MODEL` (muss installiert sein) → sonst bestes
  installiertes Modell mit Tool-Calling (qwen3/qwen2.5/llama3.x/mistral …)
- Hardware-Empfehlung nach RAM (≥ 32 GB qwen2.5:14b, ≥ 16 GB qwen2.5:7b,
  ≥ 8 GB qwen2.5:3b), Apple-Silicon/NVIDIA-Erkennung
- **kein Auto-Download**: ClipForge ruft nie `/api/pull` auf, sondern zeigt den
  Befehl `ollama pull …` an
- Einrichtung → „KI-Assistent lokal (Ollama)“: Status, Modelle, Probelauf mit
  echtem Werkzeugaufruf (`POST /api/studio/agent/ollama/test`)
- Fehler, Timeout oder nicht erreichbar → **Regel-Planer übernimmt**, keine Kosten,
  Hinweis im Chat
- Echter Test steht aus: auf dem Mac `ollama pull qwen2.5:7b`, dann Probelauf

## Tests

`api/tests/test_editor_agent.py` (Planer, Validierung, Ausführung, Undo,
Bestätigung, Kosten, LLM-Abwehr, Stream-Ablauf bis zum gerenderten Job),
`api/tests/test_agent_tools_final.py` (neue Werkzeuge über die API, Render mit
Zoom, Thumbnail, Ollama-Status/Probelauf/Fallback gegen nachgebildeten Server,
Stream-Varianten), `web/e2e/flow-k-editor-agent.spec.ts` (Browser: Befehl →
Ausführen → Undo).
