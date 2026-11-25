# Verifizierte Funktionsmatrix — ClipForge (Stand Quality-Sprint 21.11.2026)

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
| Audio-Ereignisse (Lachen, Jubel, Applaus, Schreien, Musik, Sprache, Stille) — akustische Heuristik | A (Funktion) / Qualität unbelegt | `stream/audio_events.py` | `test_audio_events` (synthetische Signale + eSpeak-Sprache; Ranking-Test) | nicht trainiert, an synthetischen Signalen abgestimmt; Standard nur „erklärend“, weil auf den Testsätzen keine F1-Verbesserung messbar war | Auswertung an markierten echten Streams (`--compare-audio-events`) |
| Trainiertes Audio-Modell (YAMNet/PANNs) | E | – | – | Modell-Hosts (TF-Hub, Kaggle, Zenodo, Hugging Face) gesperrt | ONNX-Export lokal + Prüfsumme |
| Render der Highlights als Job (9:16, Captions, Reframe) | A | `stream/service._task_render` | API-Test (ffprobe) | – | – |
| Live: Twitch-IRC | B | `stream/live.TwitchChatReader` | lokaler IRC-Testserver | Twitch-Host hier nicht auflösbar | einmal live gegen öffentlichen Kanal |
| Live: YouTube Data API (liveChatMessages) | B | `stream/live.YouTubeLiveChatReader` | `test_stream_live_youtube` (nachgebildete API) | API-Schlüssel nötig, nur öffentliche Streams | Test mit eigenem Schlüssel + Live-Stream |
| Live: Spike-Erkennung, Schnitt aus wachsender MKV | A | `stream/live.py` | `test_stream_live` | nur lokale OBS-Aufnahme | – |
| Live: Warteschlange (1 Schnitt/Takt, Obergrenze, Status) | A | `LiveSession._enqueue/tick` | `test_only_one_cut_per_tick`, Grenz-Test | – | – |
| Kick-Live-Chat | E | – | – | keine offizielle stabile API | – |
| Download fremder Streams | E | – | – | bewusst ausgeschlossen (Nutzungsbedingungen) | – |
| Link-Import YouTube/Twitch per yt-dlp (opt-in, Rechte je Link, Chat-Replay YouTube, danach Analyse) | B | `stream/link_import.py`, `StreamService.create_from_link`, `LinkImport.tsx` | `test_link_import` (nachgebildeter Downloader), E2E Flow O | verstößt gegen Plattform-AGB (Hinweis + Einschalten durch Nutzer); echter Download hier nicht ausgeführt; Twitch ohne Chat | erster echter Link auf dem Mac des Nutzers |

## KI-Videoeditor und Agent

| Funktion | St. | Ort | Nachweis | Einschränkung | Nächster Schritt |
|---|---|---|---|---|---|
| Regel-Planer (de/en), Validierung, Undo, Bestätigung | A | `agent/planner.py`, `tools.py`, `service.py` | `test_editor_agent`, `test_agent_tools_final`, E2E Flow K | feste Sprachmuster | – |
| Neue Werkzeuge: Zoom, Untertitel-Aussehen, Musik, SFX, Lautheit, Titel, Thumbnail, Clip-Varianten | A | `agent/tools.py` | `test_agent_tools_final` (+ Render) | Musik/SFX nur aus vorhandenen Dateien | – |
| Ollama: Status, Modellwahl, Hardware-Empfehlung, Probelauf, Fallback | B | `agent/ollama.py`, Einrichtung | nachgebildeter Ollama-Server | **kein echtes Modell getestet** (Registry gesperrt) | `ollama pull qwen2.5:7b`, Probelauf |
| Claude / OpenAI / Gemini als Planer | B | `agent/planner.llm_plan`, `_gemini` | nachgebildete Antworten | kostenpflichtig bzw. tarifabhängig, nicht live getestet; Gemini nie ohne Bestätigung | nach Freigabe je 1 Testnachricht |
| Gesprächsgedächtnis je Projekt + Zusammenfassung | A (Logik) / B (mit LLM) | `planner.memory_context` | `test_project_memory_and_gemini`, `test_memory_summarizes_long_history` | – | – |
| Timeline-, Split-Screen- und Übersetzungs-Werkzeuge im Agenten | A (Timeline/Split-Screen) / B (Übersetzung) | `agent/tools.py` | `test_timeline_tools_via_agent_and_ops_api` | Übersetzung legt Projekt an; Argos-Modell lokal nötig | Argos-Modell installieren, Lauf prüfen |
| Antwort-Streaming der LLMs | D | – | – | Planer liefern kurze JSON-Pläne vollständig; Fortschritt wird stattdessen je Schritt angezeigt | erst sinnvoll bei längeren Freitext-Antworten |

## Editor und Renderer

| Funktion | St. | Ort | Nachweis | Einschränkung | Nächster Schritt |
|---|---|---|---|---|---|
| Szenen-Editor, Autosave, Versionen, Undo/Redo, Konflikte | A | Editor-Seite, `studio/projects.py` | `test_studio_api`, E2E Flow I | – | – |
| Szenen-Timeline (Reihenfolge), Tastenkürzel | A (UI) | `components/studio/Timeline.tsx` | E2E-Suite | – | – |
| Mehrspur-Timeline: Video-/Overlay-/Audio-/Text-Spuren, Ziehen, Einrasten, Trimmen, Teilen, Slip, Ripple-Löschen, Kopie, Gruppen, Stumm/Sperren/Ausblenden, Zoom, Abspielkopf, Undo/Redo | A | `studio/timeline.py`, `timeline_render.py`, `components/studio/TimelineEditor.tsx` | `test_timeline` (Ops + Pixel-/Ton-Render), E2E Flow L, Flow N (Live-Vorschau) | Browser-Vorschau ≈ FFmpeg-Ergebnis, nicht pixelgleich | – |
| Keyframes x/y/Skalierung/Drehung/Deckkraft/Lautstärke mit linear/ease-in/-out/-in-out | A | `timeline.keyframe_expr` | Ausdruck == Python-Kurve (alle Easings), Render-Pixeltest | Zuschnitt/Unschärfe: s. Quality-Sprint | – |
| Alte Projekte unverändert lesbar/renderbar | A | `projects.migrate` | `test_overlay_on_scene_project_and_old_projects_unchanged` | – | – |
| Punch-in-Zoom (statisch/einfahrend, Fokus) | A | `studio/render._zoom_chain` | `test_zoom_caption_layout…` (Pixelprüfung) | Fokus fest je Szene | – |
| Gesichts-Tracking mit Glättung (Totzone, Tempolimit, Lücken halten, Motivbindung), manuelle Fokuspunkte | A (synthetisch) | `reframe.track_faces/smooth_track/plan_tracking` | `test_tracking` (bewegtes Gesicht bleibt mittig, Haar + YuNet; Tracking + Pausenentfernung synchron) | Testgesichter synthetisch bewegt (2D + Hauptmotiv: s. Quality-Sprint) | Prüfung an echten Facecam-Aufnahmen |
| Fix OpenCV 5 (keine Haar-Kaskaden → Smart-Reframe fiel still auf Mitte) | A | `requirements.txt` (<5), Detektorkette | `test_tracking` | – | – |
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
| Docker, CI (Linux + Windows + macOS Apple Silicon), macOS-Start | A (Linux/Windows) / B (macOS) | `Dockerfile`, `.github/workflows/ci.yml`, `scripts/start_local.sh` | CI | macOS-Job nicht blockierend; deckte fehlendes libass im Homebrew-`ffmpeg` auf → `ffmpeg-full` | macOS-Job nach grünem Lauf blockierend schalten; Test auf dem M3 Pro |
| Hauptnavigation Dashboard · Erstellen · Streams · Editor · Mediathek · Clips · Publishing · Analytics · Einstellungen; Erste Schritte | A (Abläufe) / C (Design) | `components/Nav.tsx`, `Onboarding.tsx` | 24 Playwright-Tests | kein vollständiges visuelles Redesign | Design-Durchgang |
| Mediathek (Tags, Suche, Herkunft/Lizenz, Duplikate, Nutzung, sicheres Löschen, je Benutzer) | A | `studio/library.py`, `/studio/library` | `test_library`, E2E Flow M | keine Vorschaubilder für Videos (erstes Bild per Browser) | – |
| Speicherplatz-Prüfung vor schweren Aufgaben | A | `tasks.check_disk_space` | `test_operations` | – | – |
| Hardware-Kodierung (VideoToolbox/NVENC/QSV/VAAPI) | A (Erkennung/Fallback) / E (Kodierung) | `clipforge/hwaccel.py` | `test_operations`, echte Probeläufe | keine GPU in der Testumgebung; Standard CPU | Messung auf dem Mac (VideoToolbox) |
| Vercel-Preview | E | `docs/DEPLOYMENT.md` (Abschnitt Vercel) | – | Repo-Wurzel ist kein Next.js-Projekt; Backend (Python/FFmpeg, Dateispeicher) dort nicht lauffähig; Check scheitert schon auf der Basis | Eigentümer: Root Directory `web/` + `NEXT_PUBLIC_API_BASE_URL`, oder Preview abschalten |

## Quality-Sprint (21.11.2026) — neue und geänderte Funktionen

| Funktion | St. | Ort | Nachweis | Real / nachgebildet | Einschränkung | Nächster Schritt |
|---|---|---|---|---|---|---|
| Timeline-Live-Vorschau im Browser (Overlays, Text, Keyframes, Abspielkopf) über einer Render-Basisebene | A | `web/src/components/studio/TimelinePreview.tsx`, `lib/timeline.ts`, `studio/render.py` (`*.base.mp4`) | `test_timeline` (Basisebene), E2E `flow-n-timeline-preview` | real (Chromium, FFmpeg) | Basis-Szenen erst nach einem Vorschau-Render sichtbar; Browser ≈ FFmpeg, nicht pixelgleich | – |
| Animierter Zuschnitt (crop_l/r/t/b) und Unschärfe als Keyframes | A | `studio/timeline.py`, `timeline_render._visual_chain/_blur_commands` | `test_timeline` (Pixelmessung im Render) | real | Unschärfe wird je Bild per `sendcmd` gesetzt | – |
| Keyframe-Marker auf Clips, Klick springt zum Keyframe | A | `TimelineEditor.tsx` | E2E `flow-n` | real | – | – |
| Tracking horizontal + vertikal mit Zoom 1–2; Hauptmotiv bei mehreren Gesichtern (Fläche × Konfidenz, Motivbindung) | A (synthetisch) | `reframe.track_faces/plan_tracking`, Stream-Seite „Zoom“ | `test_tracking` (Ablenkgesicht, vertikal, realistische Bewegung) | real (OpenCV, FFmpeg); Bewegung synthetisch | keine echten Facecam-Aufnahmen getestet | an 2–3 eigenen Aufnahmen prüfen |
| Automatische Ausgabeprüfung (Format, Dauer je Plattform, Schwarzbild, Standbild, Ton, Lautheit, True Peak, Pausen) | A | `clipforge/output_quality.py`, Render-Bericht, `RenderQuality.tsx` | `test_output_quality` | real (FFmpeg-Analyse) | prüft nur Messbares | – |
| Menschliche Review-Stufe (6 Punkte; Freigabe nur, wenn alle erfüllt) | A | `PUT …/renders/{rid}/review` | `test_output_quality`, `test_timeline` | real | subjektiv, bewusst nicht automatisiert | – |
| Evaluationsansicht (P/R/F1, verpasst, Fehlalarme), Gewichtsvergleich, Historie, Rücksprung | A (Funktion) | `/studio/streams/evaluation`, `stream/service.compare_weights/rollback_weights` | `test_stream_evaluation`, E2E Flow M | real, aber nur synthetische Markierungen | ohne markierte echte Streams keine Qualitätsaussage | Nutzer markiert eigene Streams |
| Agent: mehrstufige Befehle mit Schrittstatus (ok/fehlgeschlagen/übersprungen), Wiederholen, Abbrechen, Undo | A (Regel-Planer) / B (LLM) | `agent/service._run_steps/retry/cancel`, `AgentChat.tsx` | `test_agent_tools_final` | real mit Regel-Planer; LLM nachgebildet | – | Ollama-Live-Test auf dem Mac |
| Ollama-Live-Test (echter Server + Modell) | E hier | `tests/test_ollama_live.py` | wird übersprungen, wenn Ollama fehlt | – | Registry gesperrt; **kein** großer Modell-Download ohne Freigabe | `ollama pull qwen2.5:7b`, dann `pytest tests/test_ollama_live.py -rs` |
| Transkription: Status (Paket, Modell im Cache, Gerät), Ergebnis-Cache je Audio-Hash, Sprache per Einstellung | A (Logik) / B (Whisper) | `transcribe.py`, `/system/transcription` | `test_transcription` | Whisper nachgebildet | Modell-Download gesperrt | echter Lauf auf dem Mac |
| Trainiertes Audio-Modell (YAMNet/PANNs) | E | `docs/STREAM_INTELLIGENCE.md` | – | – | Modell-Hosts gesperrt, nicht installiert | ONNX lokal + Prüfsumme, dann A/B mit `--compare-audio-events` |
| Kostenvorschau: Anbieter, Modell, Schätzung, Budget-Rest, Abweichungshinweis, günstigere Alternative | A (Logik) | `studio/costs.py`, `SettingsPanel.tsx` | `test_operations` | Richtwerte aus `provider_matrix` (keine erfundenen Preise; unbekannt → „?“) | Abrechnung des Anbieters maßgeblich | – |
| FFmpeg-Fähigkeitsprüfung (ass/drawtext) im Doctor; Fehlercode `ffmpeg_feature_missing` mit Lösung | A | `scripts/clipforge_doctor.py`, `studio/audio.run_ffmpeg` | `test_output_quality` | real | – | – |

## Gesamturteil (Quality-Sprint)

Neu real belegt: Browser-Live-Vorschau, animierter Zuschnitt/Unschärfe, 2D-Tracking
mit Hauptmotiv, automatische Ausgabeprüfung + Review, Evaluations-UI mit Rücksprung,
Agent-Schrittsteuerung. Weiterhin **nicht** belegt: Qualität auf echten Streams,
echte LLM-/Cloud-/Plattform-Anbindungen, trainierte Audio-Modelle, Hardware-Kodierung,
Lauf auf dem Mac des Nutzers. → nicht produktionsreif im Sinne der Abnahmekriterien.

## Gesamturteil (Production-Runde)

Neu real belegt: Mehrspur-Timeline mit Keyframes (UI, Agent, Render), Gesichts-
Tracking, Mediathek, Speicherplatz-Schutz, Encoder-Prüfung. Weiterhin **nicht**
belegt: Qualität auf echten Streams, echte LLM-/Cloud-/Plattform-Anbindungen,
trainierte Audio-Modelle, Hardware-Kodierung. → nicht „produktionsreif“ im Sinne
der Abnahmekriterien; siehe `CLIPFORGE_FINAL_PRODUCTION_REPORT.md`.

## Gesamturteil (3.0)

Die lokalen, selbst bereitgestellten Abläufe (VOD + Chat → Highlights → Varianten
→ Clips → Editor/Agent → Export) sind real getestet und funktionieren. **Nicht
nachgewiesen** sind Erkennungsqualität auf echten Streams, Live-Chats gegen die
echten Plattformen, echte LLM-Planer und alle Cloud-Anbieter. ClipForge 3.0 ist
damit **merge-bereit als Entwicklungsstand**, aber **nicht** als „verifizierter
Produktivbetrieb“ abgeschlossen.
