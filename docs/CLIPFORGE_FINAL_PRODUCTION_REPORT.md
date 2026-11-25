# ClipForge — Final Production Report

Stand 21.11.2026, **Quality-Sprint** (oben) und vorherige Production-Runde (unten,
unverändert als Verlauf). Detailmatrix je Funktion (A–E, Ort, Nachweis, real vs.
nachgebildet, Grenze, nächster Schritt): [`FEATURE_VERIFICATION.md`](FEATURE_VERIFICATION.md).

**Ergebnis in einem Satz:** Alle lokal prüfbaren Teile dieses Sprints sind umgesetzt
und real getestet; **produktionsreif ist ClipForge weiterhin nicht**, weil echte
Streams, echte LLM-Inferenz, Cloud-/Plattform-Anbindungen und der Lauf auf dem Mac
des Nutzers in dieser Umgebung nicht verifiziert werden konnten.

# Quality-Sprint

## 1. Commit

| | |
|---|---|
| Branch | `claude/clipforge-production` → Draft-PR waleedb-engineering/claude.code#2 (Basis `claude/clipforge-3`) |
| Commits | `2e151d0` Live-Vorschau · `374bdb5` Zuschnitt/Unschärfe-Keyframes · `73fdc63` Tracking 2D · `9d35392` Ausgabeprüfung/Review · `e432a3c` Evaluation/Rücksprung · `bc1f016` Agent-Schritte/Whisper/Ollama-Test · `efd5a26` macOS-CI/Kosten · `9b6a172` CI-Fixes · Doku-Commit |
| Umfang | 41 Dateien, +1 850 / −110 Zeilen (ohne Doku) |
| Merge / Deployment / Veröffentlichung / bezahlte Aufrufe | **keine** |

## 2. Änderungen

| Phase | Umgesetzt |
|---|---|
| 1 Real-World-Validierung | Evaluationsseite (Markierungen, P/R/F1, verpasst/Fehlalarm), Gewichtsvergleich aktuell vs. gespeichert, Gewichtshistorie + Rücksprung; Transkriptionsstatus, Ergebnis-Cache je Audio-Hash, Spracheinstellung, klare Fehlermeldung |
| 2 KI-Assistent | mehrstufige Befehle mit Schrittstatus ok/fehlgeschlagen/übersprungen, Wiederholen, Abbrechen, Undo; komplexere Sprachmuster (Zahlwörter, „Zoom aufs Gesicht“ → Tracking-Render); echter Ollama-Test, der ohne Ollama ehrlich übersprungen wird |
| 3 Editor | Live-Vorschau der Mehrspur-Timeline im Browser über Render-Basisebene; animierter Zuschnitt + Unschärfe; Keyframe-Marker; Tracking horizontal + vertikal mit Zoom, Hauptmotiv bei mehreren Gesichtern |
| 4 Generativ | Audit (Abschnitt 6/7): alle Cloud-Anbieter weiterhin nur nachgebildet getestet; Gemini-Beschriftung in der Anbieter-Matrix korrigiert |
| 5 UX | Qualitätskarte je Render, Review-Checkliste, Schrittstatus im Chat, Zoom-Auswahl beim Stream-Render |
| 6 Kosten | Kostenvorschau je Posten mit Anbieter, Modell, Schätzung, Budget-Rest, Abweichungshinweis, günstigerer Alternative; unbekannte Preise bleiben „?“ |
| 7 macOS/Betrieb | macOS-Runner (Apple Silicon) in CI (nicht blockierend), Startskript-Syntax + Hardware-Encoder-Probelauf auf macOS; FFmpeg-Fähigkeitsprüfung; Apple-Silicon-Abschnitt in `INSTALL.md`; Vercel-Entscheidungsvorlage in `DEPLOYMENT.md` |
| 8 Qualität | automatische Ausgabeprüfung (Format, Dauer je Plattform, Schwarz-/Standbild, Ton, Lautheit, True Peak, Pausen) + menschliche Review-Stufe |

## 3. Behobene Fehler

- **macOS:** Homebrew-`ffmpeg` 8+/9 enthält kein libass/freetype → jeder Export mit Untertiteln schlug fehl (68 Tests im ersten macOS-CI-Lauf). Jetzt: `ffmpeg-full` in CI und Anleitung, Doctor prüft die Filter, Fehlercode `ffmpeg_feature_missing` nennt Ursache und Lösung.
- **macOS-Stimmprobe:** Die Hörprobe mit der Systemstimme `say` schlug immer fehl, weil die Zwischendatei auf `.raw` endete (FFmpeg kann daraus kein Ausgabeformat ableiten). Jetzt `.src.wav`.
- **Tests mit festen Linux-Annahmen:** Ein Stimmentest erwartete bei „auto“ eSpeak (macOS wählt korrekt `say`) → eSpeak wird dort ausdrücklich gewählt. Der Unschärfe-Test misst jetzt in Vorschau-Auflösung statt 72 px (Linux 2 → 26 Zwischentöne, Schwelle ≤ 4 → ≥ 15).
- **Instabiler Test (macOS):** `test_rank_mode_prefers_quiet_laughter_over_loud_music` nahm an, ohne Ereignis-Ranking gewinne die laute Musik. Tatsächlich haben Musik und Lachen dort denselben Score (37,3), die Reihenfolge hing an der Gleitkomma-Rundung. Der Test prüft jetzt die eigentliche Aussage: gleichauf ohne Ranking, mit Ranking klarer Vorsprung für das Lachen (47,2 gegen 36,0). Rauschquellen haben einen festen Seed.
- **Windows-CI:** Test las kurzlebige `.tmp`-Dateien atomarer Schreibvorgänge, die Windows beim Schreiben sperrt (`PermissionError`). Die Zieldateien werden weiterhin vollständig auf das Token geprüft — keine Abschwächung der Prüfung.
- Planer: Musikname verschluckte den Rest des Satzes; Zahlwörter nach „Clip“ wurden nicht erkannt.
- Evaluations-Vergleich lieferte 404 ohne Markierungen (Browser-Konsolenfehler) → leeres Ergebnis.
- Gesichtserkennung: Entpackfehler nach Umstellung auf 4-Tupel (Fokus-Erkennung).
- Validierungstest prüfte versehentlich verschiedene Objekte → korrigiert (Test wurde strenger, nicht schwächer).

## 4. Ausgeführte Tests

| Suite | Ergebnis |
|---|---|
| Backend lokal (Linux, mit freien Testmodellen) | **585 bestanden**, 4 übersprungen (Ollama-Live: nicht erreichbar → ehrlich übersprungen) |
| Playwright E2E (Chromium) | alle bestanden, inkl. neuer Flows N (Live-Vorschau) und M (Evaluationsseite) |
| `tsc` + ESLint | sauber |
| GitHub Actions | `efd5a26` macOS 68 Fehler (libass) → `9b6a172` 3 → `58ee17c` ein Lauf komplett grün, ein zweiter Lauf 1 Fehler (instabiler Test, s. Abschnitt 3) → Ergebnis des Folgelaufs im PR. Linux, Windows, E2E, Docker, Frontend durchgehend grün |

## 5. Performance

Gleiche Hardware wie `BENCHMARKS.md` (4 vCPU, keine GPU). Die Ausgabeprüfung ist ein
zusätzlicher FFmpeg-Analyse-Durchgang je Render (decodiert einmal; bei Kurzvideos
im Bereich weniger Sekunden). Live-Vorschau rechnet im Browser, kein Server-Render.
Animierte Unschärfe nutzt `sendcmd` statt Neuberechnung der Filterkette. Keine neuen
Messungen auf dem Mac — VideoToolbox-Zahlen stehen aus.

## 6. Echte Integrationen (real geprüft)

FFmpeg (Render, Analyse, Filter), OpenCV (YuNet/Haar), eSpeak-Sprache, Chromium
(Playwright), Dateisystem/Persistenz, GitHub-Actions-Runner Linux/Windows/macOS.

## 7. Nicht verifizierte Funktionen

Ollama/Claude/OpenAI/Gemini-Planer (nur nachgebildet) · faster-whisper mit echtem
Modell · YAMNet/PANNs (nicht installiert) · Erkennungsqualität auf echten Streams ·
Tracking an echten Facecams · Cloud-Generierung (fal.ai Video/Avatar/Face Swap,
OpenAI Bilder/TTS, ElevenLabs inkl. Stimmklon) · Publishing an TikTok/Instagram/X/
YouTube · Hardware-Kodierung · Lauf auf dem MacBook M3 Pro · LLM-Antwort-Streaming (D).

## 8. Externe Blocker

| Blocker | Lösung |
|---|---|
| Modell-Hosts (Hugging Face, Ollama-Registry, TF-Hub, Kaggle, Zenodo) gesperrt | Modelle auf dem Mac laden (Freigabe, ≈ 0,5–5 GB) |
| Keine eigenen VODs + Chat-Exporte | Nutzer liefert 2–3 markierte Streams |
| Cloud-Schlüssel / Kostenfreigabe fehlen | je Anbieter 1 freigegebener Testaufruf |
| Plattform-App-Prüfungen (TikTok/Meta/X) | Entwickler-Apps + Testkonten |
| Vercel-Einstellung | Eigentümer, siehe `DEPLOYMENT.md` → Vercel |
| Kein GPU/kein Mac in dieser Umgebung | Lauf auf dem Gerät des Nutzers |

## 9. Sicherheitsrisiken

- Unverändert: Sprachmodelle rufen nur validierte Werkzeuge auf, **nie** Shell-Befehle; FFmpeg nur als Argumentliste.
- Neue Endpunkte (Review, Basisebene, Retry/Cancel, Gewichts-Rollback) nutzen denselben Token-/Origin-Schutz und Benutzerbereich wie die übrigen Routen; Projekt- und Render-IDs werden vor jedem Dateizugriff per `require_id` validiert (keine Pfadbestandteile aus Eingaben).
- Transkript-Cache liegt im Benutzerbereich und enthält Gesprächsinhalte → wird mit dem Projekt-Speicher gesichert/gelöscht; kein Upload.
- Offene Restrisiken wie zuvor: JSON-Persistenz ohne Mehrprozess-Transaktionen, Online-Betrieb nur mit HTTPS + Konten (`ONLINE_BETRIEB.md`).

## 10. Produktionsreife

| Kriterium | Stand |
|---|---|
| Lokale Kernabläufe funktionieren, real getestet | erfüllt |
| Messbare Qualitätsprüfung jedes Renders + menschliche Freigabe | erfüllt |
| Qualität auf echten Streams belegt | **nicht erfüllt** (keine Daten) |
| Echte KI-Planer/Cloud-Dienste belegt | **nicht erfüllt** (Mock ≠ Nachweis) |
| Lauf auf macOS Apple Silicon belegt | teilweise (CI-Runner), Gerät des Nutzers offen |
| Online-Betrieb | vorbereitet (Docker, Konten), nicht ausgerollt |

→ **Beta für lokale Nutzung durch den Eigentümer**, nicht produktionsreif.

## 11. Nächste Schritte (genau)

1. macOS-Job: nach 2–3 aufeinanderfolgenden grünen Läufen `continue-on-error` entfernen (Eigentümer).
2. Auf dem M3 Pro: `brew install ffmpeg-full`, `python scripts/clipforge_doctor.py`, `./scripts/start_local.sh`.
3. Mit Freigabe: `ollama pull qwen2.5:7b`, dann `cd api && python -m pytest tests/test_ollama_live.py -v -rs`.
4. Mit Freigabe: faster-whisper `small` laden, eine eigene Aufnahme transkribieren, Status unter Einstellungen prüfen.
5. 2–3 eigene Streams (Video + Chat-Export) importieren, Highlights in der Evaluationsseite markieren, `--tune` ausführen, Gewichte vergleichen, ggf. zurückspringen.
6. Tracking an einer eigenen Facecam-Aufnahme mit Zoom 1,4 rendern und in der Review-Stufe beurteilen.
7. Vercel: Option A oder B aus `DEPLOYMENT.md` wählen.
8. Je Cloud-Anbieter einen freigegebenen Testaufruf mit Budgetgrenze; Ergebnis in `FEATURE_VERIFICATION.md` von B auf A setzen.
9. PRs erst nach Durchsicht durch den Eigentümer zusammenführen (kein automatischer Merge).

---

# Production-Runde (vorher)

## 1. Commit und Branch

| | |
|---|---|
| Branch | `claude/clipforge-production` (abgeleitet von `claude/clipforge-3` @ `4205e07`) |
| Basis-PR | waleedb-engineering/claude.code#1 (`claude/clipforge-3` → `claude/creator-studio`, Draft) |
| Commits dieser Runde | `a79b373` Timeline · `a1020ad` Agent · `e2d989c` Audio-Ereignisse · `9780386` Tracking · `3ad6c80` Mediathek/UX · `6a1cbe8` Betrieb · Doku-Commit |
| Umfang | 46 Dateien, +3 900 / −136 Zeilen (ohne Doku) |
| Merge | **nicht** erfolgt; kein Deployment, keine Veröffentlichung, keine bezahlten Aufrufe |

## 2. Implementierte Funktionen (diese Runde)

| Bereich | Neu |
|---|---|
| **Mehrspur-Timeline** | versioniertes Schema (Video-/Overlay-/Audio-/Text-Spuren), Operationen move (Einrasten, Gruppen, Spurwechsel) · trim · split · slip · ripple-delete · Kopie · Gruppieren · stumm/gesperrt/ausgeblendet; ein FFmpeg-Compositing-Durchgang über das Szenenprogramm oder allein (Projekte ohne Szenen); Editor-UI mit Ziehen, Kanten, Abspielkopf, Zoom, Tastenkürzeln, Eigenschaften, Undo/Redo |
| **Keyframes** | x, y, Skalierung, Drehung, Deckkraft, Lautstärke; linear/ease-in/-out/-in-out; dieselben Daten aus UI und KI-Assistent; im Render als FFmpeg-Ausdrücke |
| **KI-Assistent** | Timeline-Werkzeuge, Split-Screen, Übersetzen/Synchronisieren (neues Projekt), Gesprächsgedächtnis je Projekt mit Zusammenfassung, Gemini-Planer (Bestätigung, kein erfundener Preis), Modellanzeige |
| **Stream-Qualität** | lokale Audio-Ereignis-Heuristik (Stille/Sprache/Musik/Lachen/Jubel/Applaus/Schreien), Modi off/explain/rank mit Musik-Dämpfung, Metriken Duplikate/Verpasst/Grenzfehler, synthetisch und echt getrennt, A/B-Vergleich |
| **Tracking** | Gesichts-Tracking (YuNet/Haar) mit Motivbindung, Lückenhalten, Median, Totzone, Tempolimit; manuelle Fokuspunkte; synchron mit Pausenentfernung |
| **Mediathek** | je Benutzer; Tags, Suche, Herkunft/Lizenz, SHA-256-Duplikate, Nutzungsprotokoll, sicheres Löschen, „In Projekt verwenden“ |
| **UX** | Hauptnavigation (Dashboard · Erstellen · Streams · Editor · Mediathek · Clips · Publishing · Analytics · Einstellungen), Editor-Übersicht, Erste-Schritte-Karte |
| **Betrieb** | Speicherplatz-Prüfung vor schweren Jobs (HTTP 507), Hardware-Encoder mit echtem Probelauf und CPU-Fallback, System-Endpunkt, Bereitstellungs-Doku |

**Behobene Fehler** (durch neue Tests gefunden):
- `PATCH /projects` übernahm `audio`/`timeline` nicht — der Lautheits-Schalter im Editor war wirkungslos.
- OpenCV 5 hat keine Haar-Kaskaden — Smart-Reframe fiel unbemerkt auf die Bildmitte zurück (Abhängigkeit auf < 5 begrenzt, Detektorkette robust).
- Einrasten wählte die nicht eingerastete Kante.
- Gleiche Datei im Upload-Feld nicht erneut wählbar.
- Planer verwechselte Text- und Hervorhebungsfarbe.

## 3. Gegen echte Systeme getestet

„Echt“ = echtes FFmpeg, echte Dateien, echte Protokolle im Container; keine Mocks des geprüften Teils.

- Timeline-Render (Pixelposition aus Keyframes, Deckkraft-Einblendung, Ton an Position, Untertitel)
- Keyframe-Ausdrücke == Python-Kurve für alle Easings
- Gesichts-Tracking an bewegtem Gesicht (Haar und YuNet), Tracking + Pausenentfernung synchron
- Audio-Ereignis-Heuristik an synthetischen Signalen + lokaler eSpeak-Sprache; Ranking-Effekt
- Mediathek-Ablauf inkl. Benutzertrennung; UI-Abläufe in Chromium (Playwright, 24 Tests)
- Encoder-Probeläufe (CPU echt; NVENC/QSV/VAAPI echt fehlgeschlagen → korrekt verworfen)
- Lange Medien: 10 min ×3, 60 min (720p), 3 h (360p, siehe 9)

**Testsuite:** Backend 565 bestanden / 0 fehlgeschlagen / 0 übersprungen (mit Testmodellen aus `scripts/fetch_test_models.py`), Playwright 24/24, `tsc` + ESLint sauber.

## 4. Nur mit nachgebildeten Antworten getestet (kein Produktionsnachweis)

Ollama (Status, Probelauf, Fallback) · Claude/OpenAI/Gemini-Planer · YouTube-Live-Chat-API ·
Twitch-IRC (lokaler IRC-Server) · Cloud-Anbieter (fal.ai, ElevenLabs, OpenAI Images/TTS) ·
Publishing YouTube/TikTok/Instagram/X · Analytics-Abruf der Plattformen.

## 5. Unvollständig

| Funktion | Stand |
|---|---|
| Keyframes für Zuschnitt und Unschärfe | nur statisch |
| Live-Vorschau der Timeline im Browser | Vorschau = letzter Render |
| Objekt-Tracking jenseits von Gesichtern, vertikales Tracking | fehlt |
| Trainierte Audio-Klassifikation | blockiert (Modell-Hosts) |
| LLM-Antwort-Streaming | fehlt |
| Ausführbare Erweiterungen | bewusst deaktiviert, nur Entwurf (`EXTENSIONS_ARCHITECTURE.md`) |
| Visuelles Gesamt-Redesign | nur Navigation/Erste Schritte vereinheitlicht |
| Mehrinstanz-Betrieb (DB, Objektspeicher, Worker) | nicht implementiert (`STORAGE_EVALUATION.md`) |
| Generative Workflows | aus 2.0/3.0 vorhanden (`REVID_PARITY_STATUS.md`), in dieser Runde nicht erneut einzeln verifiziert; lokale Wege sind **Montage/Motion/TTS**, keine generative Videosynthese |

## 6. Externe Abhängigkeiten (offen)

| Benötigt | Wofür |
|---|---|
| 2–3 eigene VODs mit Chat-Export, im UI markiert | echte Erkennungsqualität, Gewichts-Tuning, Audio-Ereignis-A/B |
| Mac mit Ollama (`ollama pull qwen2.5:7b`) | echte lokale Inferenz + Probelauf |
| YouTube-API-Schlüssel + eigener Live-Stream | Live-Chat gegen echte API |
| Netzzugang zu Twitch | IRC live |
| Freigabe + Budget | je 1 Testnachricht Claude/OpenAI/Gemini, je 1 Minimalaufruf Cloud-Medien |
| Freigabe + eigener Testkanal (privat) | Publishing-Test je Plattform |
| GPU / Apple Silicon | Hardware-Kodierung messen |
| Vercel-Entscheidung | Root `web/` oder Preview aus |

## 7. Sicherheitsrisiken

| Risiko | Stand |
|---|---|
| LLM steuert Werkzeuge | nur freigegebene Werkzeuge, Schema-Prüfung, Bestätigung bei Render/Export/Übersetzung, Versionsschutz, Undo; Test: `run_shell` vom Modell abgewiesen |
| FFmpeg-Filter-Injection über Timeline | nur Zahlen/Enums/geprüfte Dateinamen gelangen in Ausdrücke; Texte nur escaped in ASS |
| Pfade | Medien nur aus dem Projektordner (`safe_filename`/`safe_child`); Mediathek speichert unter IDs |
| Kosten | Gemini ohne Preisangabe → Bestätigung Pflicht; Fallback auf Regeln kostet nichts |
| Fremdcode | Skills nur Markdown; keine ausführbaren Erweiterungen |
| Plattenplatz | Jobs starten nicht unter Mindestfreiraum |
| Restrisiko | JSON ohne prozessübergreifende Transaktionen (nur Mehrinstanz relevant); LLM-Pläne können inhaltlich falsch sein (deshalb Prüfung vor Ausführung) |

## 8. Lizenzprüfung

Keine neue Fremdbibliothek in dieser Runde; Änderung nur der OpenCV-Obergrenze
(Apache-2.0). Testmedien: synthetisch (FFmpeg lavfi), `lena.jpg`/YuNet aus dem
OpenCV-Repository (nur Tests). Kein fremder Code übernommen. Vollständige Liste:
`CLIPFORGE_3_FINAL_REPORT.md` §7.

## 9. Performance

Gemessen auf 4 vCPU, 15 GB RAM, ohne GPU (`BENCHMARKS.md`):

| Szenario | Ergebnis |
|---|---|
| 10-min-Stream 360p (×3) | 7,5 s Messung je Datei (80×), F1 0,833 synthetisch |
| 60-min-Stream 720p | 94–117 s (31–38×), F1 0,913 (25 Clips) |
| 3-h-Stream 360p | 133 s Messung (**81×** Echtzeit), RAM Python 70 MB / FFmpeg 148 MB; 66 Ereignisse: F1 0,904 ohne Obergrenze (siehe Nachtrag) |
| Stream ohne Chat | im 10-min-Satz enthalten (Recall 1,0) |
| verzögerter Chat | im Satz enthalten (3–7 s); Verzögerung per Kreuzkorrelation |
| beschädigte Eingaben | Tests (Video, Chat) |
| Render 1080p, 38 s | 24 s; + Zoom + Lautheit 28 s |
| Timeline-Compositing | Teil der Render-Tests (Sekundenbereich) |
| CPU-Kodierung 1080p | 2,27× Echtzeit |

Nicht gemessen: Podcast mit mehreren Sprechern (keine Sprechertrennung), schwache
Audioqualität an echten Aufnahmen, Transkription (Modell-Download gesperrt).

## 10. Betriebssystem-Kompatibilität

| System | Stand |
|---|---|
| Linux | CI + diese Umgebung |
| Windows | CI-Backend-Tests (blockierend) |
| macOS | Startskript für bash 3.2 angepasst; **nicht in CI**, Nutzerprüfung ausstehend; VideoToolbox-Pfad implementiert, ungetestet |
| Docker | CI baut Image + Healthcheck |

## 11. Bereitstellungsreife

Lokal und als Einzel-Server mit Docker: bereit (`DEPLOYMENT.md`, `ONLINE_BETRIEB.md`).
Mehrinstanz/Skalierung: nicht bereit. Vercel: nur Frontend möglich.

## 12. Produktionsreife — Abnahmekriterien

| # | Kriterium | Status |
|---|---|---|
| 1 | Import echter Medien | A (lokale Dateien) |
| 2 | Zuverlässige multimodale Analyse | C — nur synthetisch belegt |
| 3 | Erklärbares Ranking | A |
| 4 | Automatischer vertikaler Schnitt | A |
| 5 | Untertitel synchron | A (Pausen, Trim, Tracking, Timeline) |
| 6 | Manuelle Bearbeitung | A |
| 7 | Mehrspur-Bearbeitung | A |
| 8 | KI-Bearbeitungsbefehle | A (Regeln) / B (LLMs) |
| 9 | Lokale KI-Inferenz verifiziert | **E — blockiert** |
| 10 | Video-Erstellung | A lokal (Montage) / B generativ (Cloud) |
| 11 | Sichere Anbieter-Anbindung | A (Kontrollen) / B (live) |
| 12 | Zuverlässiger Export | A |
| 13 | Kontrolliertes Publishing | B |
| 14 | Stabile Persistenz | A (Einzelinstanz) |
| 15 | Regressionstests bestehen | A |
| 16 | Installation/Doku | A (lokal), macOS ungeprüft |

**Offen: 2, 9, 13 sowie die B-Anteile von 8, 10, 11.** Damit ist die Produktionsreife
nach Abschnitt 39 der Anforderung **nicht erreicht**.

## 13. Nächste konkrete Schritte

1. Echte VODs + Chat importieren, Highlights markieren, `--compare-audio-events` und
   „Gewichte schätzen“ laufen lassen; nur bei messbarer Verbesserung übernehmen.
2. Auf dem Mac: `ollama pull qwen2.5:7b`, Einrichtung → Ollama → „Probelauf“;
   Twitch-Kanal im Live-Modus; `CLIPFORGE_HWACCEL=auto` + `/api/studio/system/hwaccel?benchmark=true`.
3. YouTube-API-Schlüssel hinterlegen, eigenen Live-Stream öffnen, Live-Modus starten.
4. Freigaben für je eine bezahlte Testnachricht/-generierung erteilen (oder ablehnen).
5. Privaten Testkanal je Plattform verbinden und einen **privaten** Upload freigeben.
6. Keyframes für Zuschnitt/Unschärfe, Browser-Vorschau der Timeline.
7. Mehrinstanz-Betrieb erst bei Bedarf (DB + Objektspeicher + Worker).
8. Vercel-Einstellung entscheiden.

---

### Nachtrag: 3-h-Benchmark (synthetisch, 360p, 66 Ereignisse, 17 Störer)

| | Ergebnis |
|---|---|
| Erzeugung des Testvideos | 21 min (nur Testaufbau) |
| Signal-Messung | 132,8 s = 81× Echtzeit; Spitzen-RAM Python 70 MB, FFmpeg 148 MB |
| max. 20 Highlights (bisherige Obergrenze) | P 1,00 · R 0,30 · F1 0,47 — die **Obergrenze** begrenzt, nicht die Erkennung |
| max. 80 Highlights (nur CLI) | P 0,83 · R 1,00 · F1 0,90 · Ø Abweichung 1,8 s · Ereignis immer vollständig |
| `explain` vs. `rank` | identisch (F1 0,465 bei 20) |

Folge: Obergrenze für Highlights je Analyse von 20 auf **60** angehoben (API, UI,
Test `test_long_streams_allow_more_highlights`). Gerendert werden weiterhin höchstens
20 Clips je Auftrag. Alles synthetisch — kein Qualitätsnachweis für echte Streams.
