# Verifizierte Funktionsmatrix — ClipForge 3.0 (Abnahme 20.11.2026)

**A** real getestet und funktionierend · **B** implementiert, externer Live-Test
fehlt · **C** teilweise implementiert · **D** nicht implementiert · **E** extern
blockiert oder bewusst ausgeschlossen.

„Real getestet“ = automatischer Test mit echtem FFmpeg, echten Dateien bzw. echtem
Protokoll; der geprüfte Teil ist nicht gemockt. „Nachgebildet“ = echter
HTTP-/IRC-Verkehr gegen einen lokalen Server mit vorgegebenen Antworten — das
belegt die Anbindung, **nicht** den Produktivbetrieb.

Pfade relativ zu `api/clipforge/` (Backend), `web/src/` (Frontend), Tests in `api/tests/`.

## Stream Intelligence

| Funktion | St. | Ort | Nachweis | Einschränkung | Nächster Schritt |
|---|---|---|---|---|---|
| Chat-Import TwitchDownloader / YouTube-Replay / JSON / CSV | A | `stream/chat.py` | `test_stream_intelligence::test_chat_formats` | Kick nur per generischem Export | – |
| Audio-/Video-Signale, robustes Scoring, Begründungen | A | `stream/signals.py`, `scoring.py` | `test_scoring_without_chat…`, API-Test | Heuristik „laut + hell“ statt echter Lach-Erkennung | YAMNet (s. u.) |
| Chat-Verzögerung per Kreuzkorrelation | A | `scoring.estimate_chat_delay` | API-Test | Standard 5 s bei schwacher Korrelation | an echten Streams prüfen |
| Satzgenaue Grenzen, Duplikat-Filter, Min/Max-Länge | A | `scoring.clip_bounds`, `dedupe` | `test_clip_bounds…`, `test_stream_evaluation` | Satzgrenzen nur mit Transkript | – |
| Clip-Varianten + Eignung (keine Prognose) | A | `scoring.clip_variants` | `test_variants…`, E2E Flow J | heuristische Gewichtung | an markierten Daten kalibrieren |
| Signal-Cache, schnelle Neuanalyse | A | `stream/service.py` (`signals.json`) | `test_missing_and_broken_data` | – | – |
| Evaluation P/R/F1/Zeitabweichung, Markieren in der UI | A | `stream/evaluate.py`, Stream-Seite | `test_stream_evaluation`, E2E Flow J | aussagekräftig nur bei vollständig markierter Aufnahme | Nutzer markiert 2–3 eigene Streams |
| Gewichts-Tuning mit Leave-one-out | A (Logik) | `evaluate.tune`, `/stream-weights/tune` | `test_tune…`, API-Test | nur auf synthetischen Daten ausgeführt | auf echten markierten Streams laufen lassen |
| Qualität auf echten Twitch/YouTube-VODs | E | – | – | keine eigenen VODs + Chat-Exporte verfügbar | Nutzer liefert VODs; Auswertung per CLI/UI |
| Pipeline auf langen Aufnahmen (60 min 720p) | A | – | `BENCHMARKS.md` (30,7× Echtzeit, ≤ 440 MB) | synthetisch | 3-h-Messung auf dem Mac |
| Fehlende/defekte Daten | A | `stream/service.py` | `test_missing_and_broken_data` | – | – |
| Transkript nur in Kandidaten-Fenstern | A (Logik) / B (Whisper) | `stream/analyze.py` | Mock-Whisper im API-Test | echtes faster-whisper nicht in CI (Modell-Download gesperrt) | Lauf mit echtem Modell auf dem Mac |
| YAMNet-Audioereignisse | E | – | – | Modell-Hosts (TF-Hub/Kaggle) gesperrt | ONNX-Export lokal, dann auswerten |
| Render der Highlights als Job (9:16, Captions, Reframe) | A | `stream/service._task_render` | API-Test (ffprobe) | – | – |
| Live: Twitch-IRC | B | `stream/live.TwitchChatReader` | lokaler IRC-Testserver | Twitch-Host hier nicht auflösbar | einmal live gegen öffentlichen Kanal |
| Live: YouTube Data API (liveChatMessages) | B | `stream/live.YouTubeLiveChatReader` | `test_stream_live_youtube` (nachgebildete API) | API-Schlüssel nötig, nur öffentliche Streams | Test mit eigenem Schlüssel + Live-Stream |
| Live: Spike-Erkennung, Schnitt aus wachsender MKV | A | `stream/live.py` | `test_stream_live` | nur lokale OBS-Aufnahme | – |
| Live: Warteschlange (1 Schnitt/Takt, Obergrenze, Status) | A | `LiveSession._enqueue/tick` | `test_only_one_cut_per_tick`, Grenz-Test | – | – |
| Kick-Live-Chat | E | – | – | keine offizielle stabile API | – |
| Download fremder Streams | E | – | – | bewusst ausgeschlossen (Nutzungsbedingungen) | – |

## KI-Videoeditor und Agent

| Funktion | St. | Ort | Nachweis | Einschränkung | Nächster Schritt |
|---|---|---|---|---|---|
| Regel-Planer (de/en), Validierung, Undo, Bestätigung | A | `agent/planner.py`, `tools.py`, `service.py` | `test_editor_agent`, `test_agent_tools_final`, E2E Flow K | feste Sprachmuster | – |
| Neue Werkzeuge: Zoom, Untertitel-Aussehen, Musik, SFX, Lautheit, Titel, Thumbnail, Clip-Varianten | A | `agent/tools.py` | `test_agent_tools_final` (+ Render) | Musik/SFX nur aus vorhandenen Dateien | – |
| Ollama: Status, Modellwahl, Hardware-Empfehlung, Probelauf, Fallback | B | `agent/ollama.py`, Einrichtung | nachgebildeter Ollama-Server | kein echtes Modell getestet | `ollama pull qwen2.5:7b`, Probelauf |
| Claude / OpenAI als Planer | B | `agent/planner.llm_plan` | nachgebildete Antworten | kostenpflichtig, nicht live getestet | nach Freigabe 1 Testnachricht |
| Objektverfolgung (Tracking), freie Keyframes | D | – | Chat antwortet ehrlich | – | eigener Ausbauschritt |
| Übersetzen per Chat | D (im Chat) / A (Workflow) | `studio/translate.py` | `test_translation` | nur über Workflow „Video übersetzen“ | – |

## Editor und Renderer

| Funktion | St. | Ort | Nachweis | Einschränkung | Nächster Schritt |
|---|---|---|---|---|---|
| Szenen-Editor, Autosave, Versionen, Undo/Redo, Konflikte | A | Editor-Seite, `studio/projects.py` | `test_studio_api`, E2E Flow I | – | – |
| Timeline (Spuransicht), Tastenkürzel | A (UI) | `components/studio/Timeline.tsx` | E2E-Suite | Bearbeitung szenenbasiert | – |
| Mehrspur-Bearbeitung (freie Spuren, Drag & Drop, Snapping) | C | – | – | Musik + SFX je Szene statt freier Spuren | größerer Editor-Umbau mit Schema-Migration |
| Punch-in-Zoom (statisch/einfahrend, Fokus) | A | `studio/render._zoom_chain` | `test_zoom_caption_layout…` (Pixelprüfung) | Fokus fest je Szene | – |
| Dynamischer Gesichts-Crop mit Glättung (Stream-Clips) | A | `reframe.py` (Smart-Reframe) | `test_reframe` | Haar-Kaskade, ein Fokus je Clip | YuNet-Tracking mit Glättung |
| Split-Screen (Gameplay unten) | A | `studio/render.render_segment` | `test_split_screen…` | – | – |
| Untertitel: Karaoke/Wort-Hervorhebung, Position, Schrift, Farben, Größe | A | `captions.py`, `render._caption_layout` | `test_render_effects`, `test_captions` | Schriften aus Whitelist | – |
| Musik, Ducking, Beat-Sync | A | `studio/render._final_pass` | `test_ducking…`, `test_music_video…` | – | – |
| Soundeffekte je Szene | A | `render._final_pass` | `test_sfx_is_audible_at_its_position` | ≤ 5 je Szene | – |
| Lautheitsnormalisierung (2 Durchgänge, True-Peak) | A | `render.normalize_loudness` | `test_render_effects` (± 2,5 LU / ± 1 LU) | opt-in | – |
| Übergänge, Vorlagen (14 eingebaut, wirken auf Render) | A | `studio/transitions.py`, `templates.py` | `test_transitions_templates`, `test_templates_final` | – | – |
| Thumbnail-Vorschläge | A | `studio/thumbnails.py` | `test_thumbnail_suggestions…` | keine Klickprognose | – |

## Erstellung (generativ)

| Funktion | St. | Ort | Nachweis | Einschränkung |
|---|---|---|---|---|
| Lokal: Skript/Prompt/PDF/URL/Audio/Medien → Video (Montage, Motion, TTS) | A | `studio/service.py`, `extract.py`, `render.py` | `test_studio_*` | **keine generative KI** — lokale Montage und Ken-Burns/Motion |
| Lokale Stimmen (eSpeak; Piper/say/SAPI je OS) | A (eSpeak) / B | `studio/providers/local.py` | `test_studio_voices` | Piper-Modelle nicht in CI |
| KI-Bilder (OpenAI), KI-Video (fal.ai Kling), Avatar (fal.ai), Face Swap (fal.ai) | B | `studio/providers/remote.py`, `faceswap.py` | nachgebildete Antworten, Budget-Tests | kostenpflichtig; ohne Freigabe nicht live getestet; in der UI als Cloud/Kosten gekennzeichnet |
| Stimmklon (ElevenLabs) | B | `studio/providers` | nachgebildet | nur mit Einwilligung |

## Plattform, Skills, Publishing, Betrieb

| Funktion | St. | Ort | Nachweis | Einschränkung | Nächster Schritt |
|---|---|---|---|---|---|
| Skill-Registry (nur Markdown, Lizenz, Version, Herkunft, Abhängigkeiten, Kompatibilität) | A | `skills.py`, Einrichtung | `test_skills` + echter GitHub-Import (14 MIT-Skills) | Skills sind nur Planer-Hinweise | – |
| Ausführbare Erweiterungen / MCP | E | `docs/EXTENSIONS_ARCHITECTURE.md` (Entwurf) | – | bewusst nicht ausgeführt | erst bei konkretem Bedarf |
| Provider-Matrix, Kostenreservierung, Bestätigung | A | `studio/provider_matrix.py`, `costs.py` | Budget-Tests | Kosten sind Schätzungen | – |
| Publishing YouTube/TikTok/Instagram/X (Export, Entwurf, privat, geplant) | B | `platforms/`, `studio/publish_ops.py` | Dry-Run-/Mock-Tests, E2E C/D/E | keine echte Veröffentlichung ohne Freigabe; App-Prüfungen der Plattformen nötig | Freigabe + eigener Testkanal |
| Konten, getrennte Arbeitsbereiche, Admin-Rollen | A | `auth`, `studio/workspace.py` | `test_auth_accounts` | – | – |
| Persistenz JSON (atomar, Versionen, Recovery) | A | `studio/storage.py`, `tasks.py` | `test_storage`, `test_restore`, `test_cancel` | keine Transaktionen über Prozesse | SQLite bei Mehrprozess-Betrieb (`STORAGE_EVALUATION.md`) |
| Docker, CI (Linux + Windows), macOS-Start | A (CI) / B (macOS) | `Dockerfile`, `.github/workflows/ci.yml`, `scripts/start_local.sh` | CI grün | macOS nur vom Nutzer geprüft, nicht in CI | macOS-Runner in CI |
| Oberfläche: Dashboard, Create, Streams, Editor, Publishing, Analytics, Einrichtung | A (Abläufe) / C (Design) | `web/src/app/` | 22 Playwright-Tests | keine eigene Mediathek-Seite (Medien je Projekt); kein vollständiges Redesign | Mediathek-Seite, Design-Durchgang |
| Vercel-Preview | E | – | – | Backend (Python/FFmpeg) dort nicht lauffähig; Check scheitert schon auf der Basis | Eigentümer-Entscheidung |

## Gesamturteil

Die lokalen, selbst bereitgestellten Abläufe (VOD + Chat → Highlights → Varianten
→ Clips → Editor/Agent → Export) sind real getestet und funktionieren. **Nicht
nachgewiesen** sind Erkennungsqualität auf echten Streams, Live-Chats gegen die
echten Plattformen, echte LLM-Planer und alle Cloud-Anbieter. ClipForge 3.0 ist
damit **merge-bereit als Entwicklungsstand**, aber **nicht** als „verifizierter
Produktivbetrieb“ abgeschlossen.
