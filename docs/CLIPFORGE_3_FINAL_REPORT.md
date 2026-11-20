# ClipForge 3.0 — Abschlussbericht

Stand 20.11.2026 · Branch `claude/clipforge-3` (Draft-PR #1 → `claude/creator-studio`) ·
kein Merge, keine Veröffentlichung, keine kostenpflichtigen Aktionen ausgelöst.

Detailmatrix mit Ort, Nachweis, Grenze und nächstem Schritt je Funktion:
[`FEATURE_VERIFICATION.md`](FEATURE_VERIFICATION.md).

## 1. Tatsächlicher Entwicklungsstand

ClipForge ist eine lokal laufende Creator-Plattform (FastAPI + Next.js + FFmpeg)
mit drei tragenden Abläufen, die **real** und automatisiert getestet sind:

1. **Stream → Clips**: eigenes VOD/OBS-Video + Chat-Export → multimodale,
   erklärbare Highlight-Erkennung → Varianten mit Eignung → Korrektur/Markieren →
   vertikale Clips als Job → Clip-Editor/Publishing.
2. **Erstellen → Bearbeiten → Export**: Skript/Prompt/PDF/URL/Audio/Medien →
   Szenen-Editor mit Timeline, Untertiteln, Musik, Zoom, Effekten, Vorlagen → Render.
3. **KI-Assistent**: Befehle in natürlicher Sprache → validierte Werkzeugaufrufe →
   Bestätigung → Ausführung über dieselben Funktionen wie der Editor → Undo.

**Nicht** nachgewiesen: Erkennungsqualität auf echten Streams, Live-Chats gegen die
echten Plattformen, echte LLM-Planer (Ollama/Claude/OpenAI) und alle Cloud-Anbieter.
Bewertung: **merge-bereit als Entwicklungsstand**, nicht „verifizierter Produktivbetrieb“.

## 2. Neue Funktionen (diese Abnahmerunde)

| Bereich | Neu |
|---|---|
| Stream-Auswertung | Annotationen, Präzision/Recall/F1/P@k, Zeitabweichung, Ereignis-Vollständigkeit; Markieren in der UI („✓/✗“, verpasste Highlights); CLI `python -m clipforge.stream.evaluate`; Gewichts-Tuning mit Leave-one-out (Übernahme nur bei belegter Verbesserung) |
| Testumgebung | `scripts/make_stream_benchmark.py`: reproduzierbarer, als synthetisch gekennzeichneter Testsatz mit Ereignistypen und Störern |
| Analyse | Signal-Cache (`signals.json`), einstellbare Min-/Max-Länge, Clip-Varianten kurz/ausgewogen/Kontext mit heuristischer Eignung |
| Renderer | Punch-in-Zoom (statisch/einfahrend, Fokus Gesicht/Mitte/Seiten), Untertitel-Position/Schrift/Farben/Größe, Soundeffekte je Szene, zweistufige Lautheitsnormalisierung (EBU R128, True-Peak-Limiter) |
| Agent | 10 neue Werkzeuge (zoom_scene, set_caption_appearance, list_audio, add_background_music, add_sound_effect, normalize_loudness, generate_title, generate_thumbnail, list_clip_variants, set_clip_variant), erweiterte Regel-Befehle |
| Ollama | Status, Modelle mit Tool-Calling-Erkennung, Hardware-Empfehlung, Probelauf, Timeout, Fallback auf Regeln, nie Auto-Download; Einrichtungs-Panel |
| Live | YouTube-Live-Chat über die offizielle Data API (Kontingent-Anzeige, verständliche Fehler); Warteschlange mit max. einem Schnitt pro Takt, Obergrenze, Statusanzeige |
| Vorlagen | Twitch-Clip, YouTube Shorts, Interview, Cinematic (jetzt 14); Vorlagen setzen Untertitel-Layout, Lautheit und Hook-Zoom |
| Skills | Abhängigkeiten (`requires`), Autor, API-Version, Importeur; Prüfung beim (De-)Aktivieren |
| Doku | BENCHMARKS, STORAGE_EVALUATION, EXTENSIONS_ARCHITECTURE, aktualisierte Stream-/Agent-Doku, Funktionsmatrix |

## 3. Behobene Fehler

| Fehler | Ursache | Behebung / Nachweis |
|---|---|---|
| Variante „Ausgewogen“ fehlte, wenn „Kurz“ identisch war | Duplikat-Filter in falscher Reihenfolge | ausgewogen zuerst; `test_variants…` |
| Lautheit verfehlte −14 LUFS bei kurzen Clips (−21 LUFS) | einstufiges `loudnorm` | zweistufig mit Messwerten; `test_render_effects` |
| Lautheit −19,6 statt −14 bei spitzem Signal | `linear=true` fällt bei True-Peak-Überschreitung auf dynamisch zurück | Verstärkung + True-Peak-Limiter; Test ± 2,5 LU |
| „Füge Hintergrundmusik hinzu“ suchte Titel „hinzu“ | Regex fing Füllwort | Füllwörter gefiltert |
| „Schlag mir einen Titel vor“ / „kürzeren Variante“ nicht erkannt | trennbares Verb / Wortende | Regex erweitert |
| Recall 0,38 auf 60-min-Stream | „max. Clips = 8“ begrenzt, nicht die Erkennung | dokumentiert (BENCHMARKS), UI erlaubt bis 20 |
| Vercel-Check rot | Vercel kann das Python/FFmpeg-Backend nicht bauen; besteht schon auf der Basis | dokumentiert, Eigentümer-Entscheidung |

Zwei bestehende Test-Erwartungen wurden **begründet** angepasst: Untertitel-Farbe
und Zoom sind jetzt echte Funktionen (vorher ehrlich „nicht verfügbar“); das
Captions-Objekt enthält neue Standardfelder; Live-Status „waiting_for_recording“
statt „queued“ für bessere Fortschrittsanzeige.

## 4. Getestete Funktionen

| Suite | Ergebnis |
|---|---|
| Backend (pytest, echtes FFmpeg) | **528 bestanden, 0 fehlgeschlagen**, 5 übersprungen (Modelle/OS-spezifisch) |
| Playwright-E2E (Chromium, echtes Backend) | **22/22 grün** (Flow J erweitert um Varianten/Markieren/Auswerten) |
| Frontend | `tsc`, ESLint sauber |
| CI (GitHub Actions) | Backend Ubuntu + Windows, E2E, Frontend-Build, Docker-Build + Healthcheck |

Abgedeckte Fehlerfälle: beschädigtes Video, leerer/kaputter Chat, Video ohne Ton,
Chat außerhalb der Videozeit, ungültige Grenzen, Ollama nicht erreichbar/falsches
Modell/Textantwort statt Werkzeugaufruf, nicht freigegebene Werkzeuge vom LLM,
YouTube-Kontingent/Schlüsselfehler, Warteschlangen-Überlauf, Abbruch und Neustart
(bestehende `test_cancel`, `test_restore`, `test_studio_hardening`), parallele
Bearbeitung (Versionskonflikt 409).

## 5. Nicht verifizierte Funktionen

| Funktion | Grund | Was gebraucht wird |
|---|---|---|
| Erkennungsqualität auf echten Streams | keine eigenen VODs + Chat-Exporte | 2–3 eigene Streams, im UI markieren, `--tune` |
| Twitch-IRC live | Twitch-Host in der Umgebung nicht auflösbar | einmal auf dem Mac gegen einen öffentlichen Kanal |
| YouTube-Live-Chat live | kein API-Schlüssel, kein eigener Live-Stream | Schlüssel in der Einrichtung, laufender öffentlicher Stream |
| Ollama mit echtem Modell | Modell-Registry gesperrt, keine GPU | `ollama pull qwen2.5:7b` auf dem Mac, Probelauf |
| faster-whisper-Transkription | Modell-Download gesperrt | Lauf auf dem Mac |
| YAMNet | Modell-Hosts gesperrt | ONNX-Export lokal |
| Claude/OpenAI-Planer, fal.ai, ElevenLabs, OpenAI Images/TTS | kostenpflichtig, keine Freigabe | ausdrückliche Freigabe + Budget |
| Publishing (echte Uploads) | keine Freigabe zur Veröffentlichung | Freigabe + eigener Testkanal (privat) |
| macOS automatisiert | kein macOS-Runner | macOS-Job in CI oder manueller Lauf |

## 6. Verwendete Open-Source-Repositories

Recherche: 20 Repositories read-only geklont (`GITHUB_REPOSITORY_RESEARCH.md`).
**Kein fremder Code übernommen**; übernommen wurden nur allgemeine Ideen aus
MIT-lizenzierten Projekten (u. a. guleriaakshit/clipper, Angel-Casas/Hypeline,
Blackwellcode/streamvault, PansaLegrand/dojo-video-agent). Repos ohne Lizenz
(st1fo/stream-clipper, lavisansoi/spikeclip, sidgaikwad/stream-clipper,
EtienneLescot/axcut) und AGPL (0xsline/OpenChatCut) wurden nicht verwendet.
Als Skill-Inhalt (nur Text) importiert und geprüft:
iamaanahmad/agents-video-editing-skills (MIT, 14 Skills, Skripte verworfen).

## 7. Lizenznachweise

| Abhängigkeit | Lizenz | Nutzung |
|---|---|---|
| FFmpeg (System) | LGPL/GPL je Build | externer Prozess |
| FastAPI, Uvicorn, Pydantic | MIT / BSD | Backend |
| faster-whisper / CTranslate2 | MIT | Transkription (optional) |
| OpenCV (headless) | Apache-2.0 | Gesichtserkennung, Reframe |
| YuNet / SFace (OpenCV Zoo) | MIT / Apache-2.0 | Modelle per Katalog mit Prüfsumme |
| NumPy | BSD-3 | Signale |
| eSpeak NG (über espeakng-loader) | GPL-3.0 | lokale Stimme, externer Aufruf |
| cryptography | Apache-2.0/BSD | Schlüssel-Tresor |
| Next.js, React | MIT | Frontend |
| Playwright | Apache-2.0 | Tests |
| Skills (importiert) | je Skill geprüft; ohne Lizenz gesperrt | nur Text |

## 8. API-Abhängigkeiten

Alle optional; ohne Schlüssel bleibt ClipForge lokal voll nutzbar.
Siehe `API_PROVIDER_MATRIX.md`. Neu in dieser Runde: **YouTube Data API v3**
(`liveChatMessages`, kostenlos mit Tageskontingent 10 000 Einheiten, ~5 je
Abfrage). Kostenpflichtig (nur nach Bestätigung + Budget): Anthropic, OpenAI,
fal.ai, ElevenLabs. Lokal: Ollama (localhost), Argos, Piper, eSpeak.

## 9. Hardwareanforderungen

| Nutzung | Minimum | Empfohlen |
|---|---|---|
| Studio, Editor, Stream-Analyse ohne Transkript | 4 Kerne, 8 GB RAM | 8 Kerne, 16 GB |
| + faster-whisper (small/medium) | 8 GB | 16 GB, Apple Silicon / NVIDIA |
| + Ollama-Agent | 8 GB (qwen2.5:3b) | 16 GB (qwen2.5:7b), 32 GB (14b) |
| Speicher | Quelle + ca. 1 MB/h Signale + Renders | SSD |

## 10. Performance-Ergebnisse

Gemessen auf 4 vCPU / 15 GB RAM ohne GPU (`BENCHMARKS.md`): Stream-Messung
**81×** Echtzeit (360p) bzw. **30,7×** (720p, 60 min in 117 s), FFmpeg ≤ 440 MB RAM;
Neuanalyse aus Cache < 1 s; Studio-Final 1080p 38 s Video in 24 s (+15 % mit
Zoom und Lautheit); Stream-Clip 30 s in 9,4 s. Synthetischer Testsatz: F1 0,83
(3 × 10 min) bzw. 0,91 (60 min, 25 Clips), Ø Zeitabweichung 1–1,5 s,
Ereignis immer vollständig im Clip — **Pipeline-Nachweis, kein Qualitätsnachweis**.

## 11. Sicherheitsprüfung

| Risiko | Maßnahme | Nachweis |
|---|---|---|
| Fremdcode/Agent | nur eingebaute Werkzeuge, JSON-Schema-Validierung, unbekannte Werkzeuge verworfen, Render/Export mit Bestätigung | Test: LLM schlägt `run_shell` vor → abgewiesen |
| SSRF | Ollama nur localhost; YouTube nur fester API-Host, Video-ID per Regex; Skills nur github.com | `test_ollama_only_localhost`, `test_video_id_parsing` |
| FFmpeg-/ASS-Injection | Schriften nur aus Whitelist, Farben nur `#RRGGBB`, Zoom/Lautheit nur Zahlen, Effekt-Dateien nur über `library:`/`project:` mit `safe_filename`/`safe_child` | `test_schema_validates_new_fields` |
| Pfade | `safe_child`, Zip-Slip-Schutz, lokale Aufnahmepfade im Online-Betrieb gesperrt | bestehende Tests |
| Schlüssel | verschlüsselt je Benutzer, nie im Frontend/Log; YouTube-Fehlermeldungen enthalten keine URL mit Schlüssel | Tests „Wert erscheint nie“ |
| Kosten | Reservierung vor bezahlten Aufrufen, Freigabe; Fallback auf Regeln kostet nichts | Agent-/Budget-Tests |
| Downloads | keine Auto-Downloads großer Modelle (Ollama-Pull nie aufgerufen) | Test prüft: kein `/api/pull` |
| Rechte | Rechtebestätigung je Quelle, keine fremden Streams | API-Test |

Bekannte Restgrenze: keine Transaktionen über Prozessgrenzen (JSON) — siehe 12.

## 12. Bekannte Einschränkungen

- Erkennungsqualität nur synthetisch gemessen; Gewichte sind Startwerte.
- Keine echte Lach-/Jubel-Klassifikation (YAMNet ausstehend).
- Timeline zeigt Spuren, bearbeitet aber szenenbasiert; keine freien Keyframes,
  kein Objekt-Tracking (Zoom-Fokus fest je Szene).
- Keine eigene Mediathek-Seite (Medien je Projekt); kein vollständiges UI-Redesign.
- JSON-Persistenz ohne prozessübergreifende Transaktionen (Einzelplatz unkritisch).
- YouTube-Live nur öffentliche Streams (kein OAuth für Live-Chat).
- Kick: kein Live-Chat (keine offizielle API).
- Hardware-Decoding/-Encoding (VideoToolbox/NVENC) nicht genutzt.
- Vercel-Preview kann das Backend nicht hosten.
- Details: `KNOWN_ISSUES.md`.

## 13. Empfohlene nächste Schritte

1. **Echte Daten** (Nutzer): 2–3 eigene VODs + Chat-Exporte importieren, im UI
   markieren, „Auswerten“ und „Gewichte schätzen“ — erst danach Qualität beurteilen.
2. **Mac-Prüfung**: `ollama pull qwen2.5:7b` + Probelauf; faster-whisper-Lauf;
   Twitch-IRC gegen einen öffentlichen Kanal; 3-h-Benchmark.
3. **YouTube-Live** mit eigenem API-Schlüssel an einem eigenen öffentlichen Stream.
4. YAMNet als ONNX (Prüfsumme im Modell-Katalog) und gegen markierte Daten auswerten.
5. Mediathek-Seite und Design-Durchgang über alle Bereiche.
6. Mehrspur-Timeline mit Schema-Migration (freie Audio-/Overlay-Spuren).
7. Hardware-Beschleunigung nach Messung auf dem Zielrechner.
8. Nach Freigabe: je ein bezahlter Minimaltest pro Cloud-Anbieter; privater
   Test-Upload je Plattform.
9. Bei Online-Mehrbenutzerbetrieb: SQLite/PostgreSQL (`STORAGE_EVALUATION.md`).
10. Vercel: Root auf `web/` setzen oder Preview deaktivieren (Eigentümer).

## Merge-Bereitschaft

Alle lokalen Qualitätsprüfungen sind grün (Backend-Suite, 22 E2E-Tests, tsc,
ESLint); CI-Ergebnis des letzten Commits siehe PR. Aus technischer Sicht ist der
Branch **bereit zum Review und Merge nach `claude/creator-studio`**, sobald der
Eigentümer zustimmt. Kein automatischer Merge.
