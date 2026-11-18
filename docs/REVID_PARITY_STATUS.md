# Creator Studio — Stand gegenüber dem Ziel „lokale revid.ai-Alternative“

Stand: Branch `claude/creator-studio`. Dieses Dokument beschreibt, was
**tatsächlich** funktioniert. „Getestet“ heißt: automatisierter Test im Repo.
„Nicht verifiziert“ heißt: Code vorhanden, aber nie gegen den echten Dienst
bzw. das echte Betriebssystem gelaufen.

Viralität wird nirgends versprochen; der Score heißt durchgehend
„Performance-Potenzial“ und ist eine Schätzung.

## ClipForge 2.0 (Stand dieses Branches)

Drei Stufen: **real getestet** (automatischer Test gegen echtes FFmpeg/echte
Modelle), **simuliert getestet** (Code fertig, Tests nur gegen nachgebildete
Anbieter-Antworten — gilt NICHT als funktionsfähig bestätigt), **nicht
verfügbar / extern blockiert**.

| Funktion | Stufe | Anmerkung |
|---|---|---|
| Szenenübergänge (Fade, Zoom, Slide, Smooth, Wipe, Dissolve, Kreis, auto, Beat) | real getestet | Dauer, Stimme, Untertitel bleiben synchron |
| Videovorlagen (10 eingebaut + eigene) | real getestet | |
| Stimmlautstärke, Drag-and-drop der Szenen | real getestet (Backend) / UI | |
| Hintergrundentfernung Bild + Video (U²-Net lokal) | real getestet | Video auf CPU langsam (wenige Bilder/s) |
| Lokale Modellverwaltung mit Zustimmung + Prüfsumme | real getestet (Prüflogik) | Downloads von Hugging Face/Argos hier nicht erreichbar |
| B-Roll aus der Mediathek | real getestet | Zuordnung über Dateiname + Schlagwörter |
| B-Roll von Pexels/Pixabay | simuliert getestet | kostenloser Schlüssel nötig |
| Videoübersetzung de↔en (Untertitel oder neue Stimme) | real getestet mit Mock-Übersetzer | Whisper + Übersetzungsengine echt nur mit Modellen |
| Übersetzung lokal (Argos/OPUS-MT) | simuliert getestet | Modell-Download hier blockiert |
| Übersetzung mit Claude | simuliert getestet | API-Key, kostenpflichtig |
| Piper-Stimmen über die Oberfläche laden, Piper bevorzugt | implementiert | Modelle hier nicht ladbar (Hugging Face blockiert) |
| Stimmklon: Browser-Aufnahme, Hörprobe | real getestet (Umwandlung) / simuliert (ElevenLabs) | |
| Avatar Bild-im-Bild / untere Hälfte, eigene Aufnahme je Szene | real getestet | Lippenbewegung nur mit fal.ai (simuliert) |
| Instagram Reels direkt | simuliert getestet | Meta-App + Business/Creator-Konto nötig |
| X direkt | simuliert getestet | kostenpflichtig je Post, Kostenbestätigung Pflicht |
| TikTok Direct Post + Entwürfe | simuliert getestet | `video.publish` + TikTok-Audit für öffentliche Posts |
| Geplante Veröffentlichung mit Freigabe | real getestet (Ablauf) / simuliert (Plattform) | ClipForge muss zum Zeitpunkt laufen |
| Analytics-Abruf Instagram/X/TikTok, Engagement | simuliert getestet | nur gelieferte Werte |
| Titel/Beschreibung/Hashtags je Plattform | real getestet (lokal) / simuliert (Claude) | |
| Trends YouTube (mostPopular) | simuliert getestet | kostenloser YouTube-API-Schlüssel |
| Trends TikTok/Instagram | nicht verfügbar | keine offizielle Schnittstelle |
| Getrennte Benutzerbereiche, Rollen, Registrierung, Sitzungen | real getestet | Migration des Altbestands per CLI |
| Face Swap: Einwilligung, Gesichtsprüfung, Kennzeichnung, Protokoll | real getestet (YuNet/SFace) | |
| Face Swap: eigentlicher Tausch (fal.ai) | simuliert getestet | Feldnamen der Modelle ungeprüft |
| Lokale KI-Videos (Wan, LTX-Video) | nicht verfügbar | nur Hardware-Prüfung; GPU nötig |
| CI (Linux/Windows), Docker-Build-Test | eingerichtet | Läufe auf GitHub noch nicht gesehen |
| Backups | real getestet (Skript) | |

Vorrunde (weiterhin gültig): eSpeak lokal, Windows-Skripte, Anmeldung,
Docker, YouTube-Import, KI-Video/Avatar/Stimmklon (simuliert), TikTok-Entwürfe
(simuliert).

Was du dafür bereitstellen oder entscheiden musst: [`WAS_ICH_BRAUCHE.md`](WAS_ICH_BRAUCHE.md).

## Härtungsrunde

| Bereich | Stand |
|---|---|
| Studio-Optionen wirken bis in Skript, Qualitätsprüfung und Render | vollständig funktionsfähig, getestet. Ausnahme: `goal`, `audience`, `creative_instructions` wirken nur mit Skript-KI (benötigt API-Key); `video_provider`/`video_model` werden abgelehnt (noch nicht implementiert) |
| Eine Source of Truth (`project.json`, Projekt-Sperre, atomare Writes) | vollständig funktionsfähig |
| Quellen PDF, Audio, Podcast, Longform, eigene Medien | vollständig funktionsfähig lokal; Transkription braucht `faster-whisper` oder ein Transkript-JSON |
| Gesamtbudget je Projekt mit atomarer Reservierung | vollständig funktionsfähig, auch unter parallelen Anfragen getestet. Beträge sind Schätzungen |
| API-Schlüssel ohne Neustart setzen/löschen/prüfen | vollständig funktionsfähig; die Prüfung gegen den Anbieter ist nur mit gemocktem HTTP getestet |
| Local-API-Schutz (Token, CORS, Origin, Host) | vollständig funktionsfähig, in Backend-Tests und Browser-Suite geprüft |
| Cancel dauerhaft, Recovery nach Neustart, Retry idempotent | vollständig funktionsfähig, getestet |
| Seitenverhältnisse und 720p/1080p/4K real per ffprobe geprüft | vollständig funktionsfähig; kleinere Quellen werden hochskaliert und das wird im Render-Bericht gemeldet |
| Provider-Antworten begrenzt und inhaltlich geprüft, Timeouts für alle FFmpeg-/ffprobe-Aufrufe | vollständig funktionsfähig, getestet |

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
| YouTube-Link → Shorts | L | für eigene/berechtigte Videos: Link + öffentliche Metadaten (oEmbed) + Rechtebestätigung; die Videodatei lädst du selbst hoch, Untertitel (.srt/.vtt) werden übernommen. **Kein Download von YouTube** (Nutzungsbedingungen). oEmbed nur gegen nachgebildete Antworten getestet |

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
| KI-Video (Text→Video, Bild→Video) | P | fal.ai-Adapter (Kling), Szenen-Modus im Editor, Kosten/Budget/Cache/Ersatz; **ungetestet** gegen die echte API (Doku war nicht erreichbar). Kein lokaler Modus (bräuchte GPU) |
| Stock-Medien-Bibliothek | – | nur eigene Uploads |
| Talking Avatar | P | fal.ai-Adapter (Standard: SadTalker), nutzt die Stimme der Szene und ein Avatar-Bild; **ungetestet** live. Ohne Schlüssel: Standbild, klar als Ersatz gemeldet |
| Face Swap | – | nicht gebaut — Entscheidung offen, siehe `WAS_ICH_BRAUCHE.md` |
| Storyboard-Ansicht | teilweise | Szenenliste mit Visual-Prompt; keine Thumbnail-Vorschau je Szene außer nach „Szene neu generieren“ |
| 9:16, 16:9, 1:1, 4:5 | L | getestet |
| 720p, 1080p | L | getestet |
| 4K | L | echter 4K-Render per ffprobe geprüft; kleinere Quellen werden hochskaliert und gemeldet |
| Kostenabschätzung + hartes Budgetlimit | L | Preise sind Schätzwerte; Abbruch vor Mehrkosten getestet |

### Voice, Musik, Captions

| Funktion | Stand | Anmerkung |
|---|---|---|
| Ohne Stimme (nur Captions/Musik) | L | wählbar; nur noch Ersatz, wenn keine Stimme verfügbar ist |
| eSpeak NG über pip (Windows, macOS, Linux) | L | **getestet**, echte Wort-Zeitpunkte → wortgenaue Captions; klingt synthetisch |
| Windows-Systemstimmen (SAPI) | L | nur mit nachgebildetem PowerShell-Aufruf getestet, **nicht auf echtem Windows** |
| Piper (lokal, neuronal) | L | Modell muss geladen werden; ohne echtes Modell getestet |
| Sprechtempo 0,5–2,0 | L | alle Provider, getestet |
| macOS-Systemstimme (`say`), Deutsch + Englisch | L | **nicht verifiziert** (Entwicklung lief unter Linux) |
| ElevenLabs, OpenAI TTS | P | Adapter mit gemocktem HTTP getestet; **nicht verifiziert** gegen die echten APIs |
| Automatische Stimmenauswahl, Hörprobe | L | |
| Voice Cloning | P | ElevenLabs Instant Voice Cloning, nur mit festgehaltener Einwilligung; **ungetestet** live, braucht bezahlten ElevenLabs-Tarif |
| Eigene Musikdateien, Lautstärke, Ducking | L | Ducking messbar getestet. Es wird **keine Musik mitgeliefert** |
| Beat-Sync | L | siehe oben |
| Caption-Stile minimal, bold, karaoke, dynamic, none + Vorschau | L | Brand-Kit-Farben und -Schrift werden angewendet |
| Wortgenaue Captions | teilweise | wortgenau bei Audio→Video und bei eSpeak; bei anderen Stimmen geschätzt |
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
| Upload zu TikTok | O | in die TikTok-**Entwürfe** (du veröffentlichst in der App); OAuth+PKCE, Stück-Upload, Status; **ungetestet** live, braucht eigene TikTok-Entwickler-App |
| Upload zu Instagram, X | – | keine Adapter (Gründe in `WAS_ICH_BRAUCHE.md`); Export-Pack |
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
