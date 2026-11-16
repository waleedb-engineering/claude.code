# Creator Studio — Stand gegenüber dem Ziel „lokale revid.ai-Alternative“

Stand: Branch `claude/creator-studio`. Dieses Dokument beschreibt, was
**tatsächlich** funktioniert. „Getestet“ heißt: automatisierter Test im Repo.
„Nicht verifiziert“ heißt: Code vorhanden, aber nie gegen den echten Dienst
bzw. das echte Betriebssystem gelaufen.

Viralität wird nirgends versprochen; der Score heißt durchgehend
„Performance-Potenzial“ und ist eine Schätzung.

## Feature-Matrix

Legende: **L** funktioniert lokal · **P** benötigt Provider/API-Key ·
**O** benötigt OAuth/Plattform-Freigabe · **–** noch nicht verfügbar

### Quellen und Import

| Funktion | Stand | Anmerkung |
|---|---|---|
| Skript → Video | L | getestet inkl. Render |
| Prompt → Video | L / P | ohne `ANTHROPIC_API_KEY` entsteht nur ein **Gerüst mit Platzhaltern** (als „bitte prüfen“ markiert); ausformulierte Skripte brauchen den Key |
| Artikel/Blog-URL, Website-Review, Social-URL → Video | L | SSRF-Schutz getestet; Text wird lokal extraktiv zusammengefasst. Seiten, die nur per JavaScript rendern oder hinter Login liegen, liefern keinen Text. Echter Netzabruf wurde nur gegen einen lokalen Testserver geprüft, nicht gegen das offene Internet. Kein Proxy-Support. |
| PDF → Video | L | Textextraktion mit `pypdf`; **kein OCR** für gescannte PDFs |
| Audio → Video | L | Original-Audio + wortgenaue Captions. Braucht `faster-whisper` **oder** ein mitgeliefertes Transkript-JSON |
| Musik → beat-synchrones Video | L | Beat-Erkennung ist eine Heuristik (getestet an Klick-Tracks mit 100/120/140 BPM); bei komplexer Musik kann das Tempo halb/doppelt erkannt werden |
| Podcast / Longform → Shorts | L | nutzt die bestehende Shorts-Pipeline (eigener Job) |
| Eigene Medien → Video | L | Bilder (Ken-Burns) und Videos |
| Bestehender Job als Quelle | L | nutzt das Job-Transkript |
| YouTube-Video → Shorts | – | bewusst nicht implementiert (rechtlich heikel, kein Downloader). Eigenes Video über „Longform → Shorts“ hochladen |

### Videoerstellung

| Funktion | Stand | Anmerkung |
|---|---|---|
| Skript, Szenenaufteilung | L | regelbasiert; optional Claude (P) |
| Motion-Hintergrund, Farbfläche, Einblendungen | L | FFmpeg + ASS |
| Eigene Bilder/Videos je Szene | L | |
| Split-Screen mit Gameplay-Video | L | Gameplay-Datei selbst hochladen |
| Cinematic-Look | L | Letterbox, Vignette, ruhigere Bewegung |
| Produkt-Ad | L | Struktur aus den eigenen Produktangaben, keine erfundenen Aussagen |
| KI-Bilder (mit Ken-Burns animiert) | P | OpenAI-Adapter; **nicht verifiziert** gegen die echte API |
| KI-Video (Text→Video) | – | kein Adapter |
| Stock-Medien-Bibliothek | – | nur eigene Uploads |
| Talking Avatar | – | Provider-Slot vorhanden, kein Adapter |
| Face Swap | – | bewusst kein Adapter (Einwilligung nötig) |
| Storyboard-Ansicht | teilweise | Szenenliste mit Visual-Prompt; keine Thumbnail-Vorschau je Szene außer nach „Szene neu generieren“ |
| 9:16, 16:9, 1:1, 4:5 | L | getestet |
| 720p, 1080p | L | getestet |
| 4K | L (ungetestet) | Abmessungen getestet, ein echter 4K-Render wurde nicht gemessen |
| Kostenabschätzung + hartes Budgetlimit | L | Preise sind Schätzwerte; Abbruch vor Mehrkosten getestet |

### Voice, Musik, Captions

| Funktion | Stand | Anmerkung |
|---|---|---|
| Ohne Stimme (nur Captions/Musik) | L | Standard, wenn kein Sprach-Provider da ist |
| macOS-Systemstimme (`say`), Deutsch + Englisch | L | **nicht verifiziert** (Entwicklung lief unter Linux) |
| espeak-ng | L | **nicht verifiziert** (nicht installiert in der Testumgebung) |
| ElevenLabs, OpenAI TTS | P | Adapter mit gemocktem HTTP getestet; **nicht verifiziert** gegen die echten APIs |
| Automatische Stimmenauswahl, Hörprobe | L | |
| Voice Cloning | – | bewusst kein Adapter |
| Eigene Musikdateien, Lautstärke, Ducking | L | Ducking messbar getestet. Es wird **keine Musik mitgeliefert** |
| Beat-Sync | L | siehe oben |
| Caption-Stile minimal, bold, karaoke, dynamic, none + Vorschau | L | Brand-Kit-Farben und -Schrift werden angewendet |
| Wortgenaue Captions | teilweise | wortgenau nur bei Audio→Video (Transkript). Bei TTS werden Wortzeiten **gleichmäßig geschätzt** |
| Weitere Sprachen | teilweise | Oberfläche und Skriptlogik: de/en. Cloud-Stimmen könnten mehr, sind aber nicht freigeschaltet |

### Editor

| Funktion | Stand |
|---|---|
| Szenenliste, Text/Sprechtext/Visual-Prompt/Dauer/Pause je Szene | L, getestet |
| Skript als Text bearbeiten | L |
| Umordnen, Duplizieren, Löschen | L, getestet |
| Medien je Szene ersetzen | L, getestet |
| Einzelne Szene neu generieren (mit Szenen-Vorschau) | L, getestet |
| Caption-Stil, Musik, Lautstärke | L |
| Vorschau-Render, finaler Render, Neustart | L, getestet |
| Undo/Redo, Autosave | L, getestet (Browser-E2E) |
| Konfliktsichere Versionierung + Wiederherstellen | L, getestet |
| Zeitleiste mit Drag-and-drop | – (Reihenfolge über Pfeil-Buttons) |

### Publishing

| Funktion | Stand | Anmerkung |
|---|---|---|
| Entwürfe für YouTube, TikTok, Instagram, X | L | Texte je Plattform |
| Zeitplanung | L | fällige Entwürfe werden als „fällig“ markiert — es wird **nicht** automatisch gepostet |
| Export-Pack (ZIP) | L | Fallback für alle Plattformen |
| Privater YouTube-Upload | O | unverändert abgesichert; weiterhin nicht mit echtem Konto verifiziert |
| Upload zu TikTok, Instagram, X | – | keine Adapter |
| „Als veröffentlicht markieren“ | L | nur mit ausdrücklicher Bestätigung |

### Automation, Analytics, Ideen, API

| Funktion | Stand | Anmerkung |
|---|---|---|
| Automationen täglich/wöchentlich/monatlich | L | nur Text-/URL-Workflows; erzeugen höchstens Entwürfe |
| Pause/Fortsetzen, Verlauf, Retry, Budget, Parallelität | L | mit kontrollierter Uhr getestet |
| Wiederaufnahme nach Neustart | L | getestet |
| Metriken manuell eintragen | L | |
| Metriken von YouTube abrufen | O | **nicht verifiziert**; der vorhandene OAuth-Scope reicht dafür womöglich nicht |
| Metriken von TikTok/Instagram/X | – | |
| Hook-Vergleich, Potenzial vs. Ergebnis, Remix | L | |
| Ideen-Bibliothek | L | nur eigene Einträge; Engagement-Zahlen manuell |
| REST-API, stabile Fehlercodes, Idempotenz | L | `docs/API_STUDIO.md` |
| CLI | L | braucht laufendes Backend |
| MCP-Server | – | die REST-API ist dafür geeignet, ein Server existiert nicht |

### UX

| Funktion | Stand |
|---|---|
| Dashboard, Create, Editor, Automationen, Analytics, Ideen, Einrichtung | L |
| Deutsch/Englisch | Oberfläche des Studios zweisprachig; **Fehlermeldungen des Backends nur Deutsch**; bestehende Seiten (Upload, Jobs, Publishing) nur Deutsch |
| Barrierefreiheit | Labels, Fokus-Ringe, Tastaturbedienung, Live-Regionen vorhanden; **kein formales WCAG-Audit** |

## Blockiert durch externe Zugangsdaten

1. Echte Cloud-Stimmen und KI-Bilder (ElevenLabs-/OpenAI-Key) — Adapter ungeprüft gegen echte APIs.
2. Privater YouTube-Upload und Metrik-Abruf (Google-OAuth-Client).
3. Ausformulierte Prompt-Skripte (Anthropic-Key).

## Noch offen (priorisiert)

1. Lokale Stimme auf macOS und mit espeak-ng real prüfen.
2. Cloud-Adapter gegen echte APIs prüfen (kleines Budget).
3. Wortgenaue Captions für TTS (Alignment per Whisper nach der Synthese).
4. KI-Video-Adapter und Stock-Medien.
5. Upload-Adapter TikTok/Instagram/X (jeweils Plattform-Freigabe nötig).
6. Zeitleiste mit Drag-and-drop, Szenen-Thumbnails.
7. MCP-Server über der REST-API.
8. Englische Backend-Fehlermeldungen, Übersetzung der Alt-Seiten.

## Nächster konkreter Schritt

`scripts/studio_smoke.py` auf dem Mac ausführen, danach im Editor als Stimme
„macOS Systemstimme“ wählen und einen Render anhören. Schlägt `say` fehl,
liegt der Fehler in `api/clipforge/studio/providers/local.py` (`MacSayVoice`).
