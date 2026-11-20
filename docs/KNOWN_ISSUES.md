# Known Issues — ClipForge AI 0.1.0-beta.1

Ehrliche, laufend gepflegte Liste bekannter Grenzen. Kein Punkt hier ist ein
Geheimnis — jeder ist bewusst dokumentiert, damit Beta-Tester und Entwickler
wissen, woran sie sind.

Für jeden Punkt: **Auswirkung**, **Workaround**, **Status**.

---

## 1. Echter YouTube-Private-Upload nicht mit echtem Google-Konto E2E-verifiziert

**Auswirkung:** Der Code-Pfad für den echten, privaten `videos.insert`-Upload
ist vollständig implementiert und durch Unit-/Integrationstests mit
gemocktem Google-Client abgesichert (Idempotenz, Retry/Backoff, Recovery,
Reconciliation, Race-Schutz — alle getestet). Ein **echter** Durchlauf gegen
ein reales Google-Konto ist in dieser Umgebung nicht erfolgt.
**Workaround:** Beim Dry-Run bleiben, sofern nicht ausdrücklich um einen
manuellen Real-Test gebeten wird (`CLIPFORGE_ENABLE_YOUTUBE_REAL_TEST`,
separates Flag, niemals von automatisierten Tests gesetzt).
**Status:** offen — echter manueller E2E-Lauf mit realem Konto steht aus.

## 2. Local-first — kein Multi-User-Betrieb

**Auswirkung:** ClipForge geht von genau einem Nutzer auf einem Rechner aus.
Mehrere Personen, die dieselbe Instanz gleichzeitig nutzen, teilen sich
Jobs/Drafts ohne Trennung.
**Workaround:** Pro Person eine eigene lokale Installation/Port.
**Status:** im Online-Modus gelöst (`CLIPFORGE_AUTH=accounts`, getrennte
Benutzerbereiche, Rollen). Lokal bleibt ClipForge bewusst Einzelbenutzer.

## 3. CORS/Auth nicht für Internet-Exposition gehärtet

**Auswirkung:** Das Backend ist für **lokalen** Betrieb (127.0.0.1) gedacht.
Es gibt kein Auth und eine offene CORS-Konfiguration — ein Deployment ins
offene Internet ohne zusätzliche Härtung wäre unsicher.
**Workaround:** Nicht ins offene Internet exponieren; nur lokal oder hinter
einem selbst konfigurierten, vertrauenswürdigen Reverse-Proxy mit Auth
betreiben.
**Status:** für den Online-Modus gelöst (Konten, CSRF, Ratenbegrenzung,
CORS-Allowlist); der lokale Modus bleibt nur für 127.0.0.1 gedacht.

## 4. Kein Public- oder Unlisted-YouTube-Upload

**Auswirkung:** Es gibt keine Möglichkeit, über ClipForge ein Video als
`public` oder `unlisted` hochzuladen — technisch nicht vorhanden, kein
Umgehen möglich.
**Workaround:** Keiner nötig — das ist Absicht (Sicherheits-Invariante).
**Status:** nicht geplant für diese Beta.

## 5. Kein TikTok-Auto-Upload

**Auswirkung:** TikTok wird als Zielplattform unterstützt (Planner, Content-
Package, Publishing-Pack), aber es gibt keine automatische Anbindung — nur
ein lokales ZIP zum manuellen Hochladen.
**Workaround:** Publishing-Pack herunterladen, manuell in der TikTok-App
hochladen.
**Status:** nicht geplant für diese Beta (siehe `docs/PUBLISHING_AGENT_PLAN.md`).

## 6. Kein Instagram-Auto-Upload

**Auswirkung:** Analog zu TikTok — Instagram Reels wird als Zielplattform
unterstützt, aber ohne automatischen Upload.
**Workaround:** Publishing-Pack manuell hochladen.
**Status:** nicht geplant für diese Beta.

## 7. Kein Scheduling-Daemon

**Auswirkung:** Ein „geplanter" Zeitpunkt (`scheduled_at`) an einem Draft ist
reine Metadatenverwaltung/Erinnerung — es läuft kein Hintergrunddienst, der
zur geplanten Zeit automatisch etwas veröffentlicht.
**Workaround:** Zeitpunkt manuell im Auge behalten, dann manuell
veröffentlichen.
**Status:** nicht geplant für diese Beta.

## 8. Kein dynamisches Reframe (nur statischer Crop pro Clip)

**Auswirkung:** Smart-Reframe ermittelt **einen** Fokuspunkt pro Clip
(Median über gesampelte Frames) und wendet einen **festen** Crop-Offset für
den gesamten Clip an. Bewegt sich das Gesicht stark innerhalb eines Clips,
folgt der Ausschnitt dem nicht dynamisch (bewusst — "Smart static crop v1",
robust statt wacklig).
**Workaround:** Bei starker Bewegung `--reframe-mode center` oder kürzere
Clip-Segmente wählen; im Web-Editor Start/Ende anpassen.
**Status:** bekannte Design-Entscheidung, kein Bug. Dynamisches Tracking
wäre ein größeres Feature, nicht Teil dieser Beta.

## 9. 3 dokumentierte ESLint-Tech-Debt-Funde

**Auswirkung:** `react-hooks/set-state-in-effect` in `web/src/app/jobs/page.tsx`
und `web/src/app/jobs/[jobId]/publishing/page.tsx` (3 Stellen) — ein
Load-on-Mount-Muster, das funktional korrekt ist (verifiziert durch
Playwright-E2E-Suite), aber vom neueren React-Lint-Regelsatz als potenziell
unerwünschtes Cascading-Render-Muster markiert wird.
**Workaround:** Keiner nötig — kein beobachtbares Fehlverhalten.
**Status:** bekannt, Refactor bewusst zurückgestellt (reines
Regressionsrisiko ohne Nutzerwert für diese Beta).

## 10. Kein Session-Resume über Prozessneustart (YouTube-Upload)

**Auswirkung:** Stirbt der Backend-Prozess **während** ein YouTube-Upload
aktiv läuft, wird dieser Zustand beim nächsten Start **nicht automatisch
fortgesetzt**. Der Startup-Recovery-Scanner erkennt den verwaisten Zustand
sicher und markiert ihn (kein Blind-Retry) — der Nutzer muss danach über
„Upload-Status prüfen" (Reconciliation) den echten Remote-Status abklären.
**Workaround:** Nach einem Absturz während eines Uploads: „Upload-Status
prüfen" im Draft verwenden, bevor ein neuer Versuch gestartet wird.
**Status:** bewusste Design-Entscheidung (kein Blind-Upload nach Neustart
ist sicherer als ein naives Auto-Resume) — siehe
`docs/YOUTUBE_PUBLISHING.md` §7f.

---

## Nicht auf dieser Liste?

Wenn du ein Verhalten findest, das nicht hier steht und nicht erwartet
wirkt: bitte melden (siehe
[`docs/BETA_TESTER_GUIDE.md`](BETA_TESTER_GUIDE.md#11-fehler-melden)).

## Creator Studio

Vollständige Matrix: [`REVID_PARITY_STATUS.md`](REVID_PARITY_STATUS.md). Die
wichtigsten Grenzen:

- **Ohne Sprach-Provider bleibt das Video stumm.** Lokale Sprache gibt es über
  macOS `say` oder `espeak-ng`; beide wurden in der Entwicklungsumgebung
  (Linux ohne espeak) nicht real geprüft.
- **Prompt → Video ohne `ANTHROPIC_API_KEY`** erzeugt nur ein Gerüst mit
  Platzhaltern, kein fertiges Skript.
- **Captions bei TTS sind zeitlich geschätzt**, wortgenau nur bei Audio → Video.
- **Cloud-Adapter (ElevenLabs, OpenAI)** sind nur mit gemocktem HTTP getestet.
- **Kein Upload zu TikTok, Instagram, X**; nur Export-Pack.
- **Geplante Entwürfe werden nicht automatisch gepostet**, nur als fällig markiert.
- **Beat-Erkennung ist heuristisch** und kann das Tempo halbieren/verdoppeln.
- **Gescannte PDFs** (ohne Textebene) werden abgelehnt, kein OCR.
- **JavaScript-only-Seiten und Login-Seiten** liefern beim URL-Import keinen Text.
- **Backend-Fehlermeldungen sind nur auf Deutsch**, auch bei englischer Oberfläche.
- **Der Automation-Worker läuft nur, solange das Backend läuft.**
- **`goal`, `audience` und `creative_instructions` wirken nur mit Skript-KI**
  (`ANTHROPIC_API_KEY`); ohne Key werden sie gespeichert, aber nicht umgesetzt.
- **Kostenbuch = Schätzung.** Verbucht wird der Listenpreis, nicht die echte
  Abrechnung des Anbieters.
- **Der Token-Schutz ist keine Benutzeranmeldung**; siehe
  [`LOCAL_API_SECURITY.md`](LOCAL_API_SECURITY.md).
- **API-Schlüssel liegen in `.env`** (Rechte 0600), nicht im OS-Schlüsselbund.
- **Cloud-Adapter ungetestet:** fal.ai (KI-Video, Avatar), ElevenLabs-Stimmklon
  und TikTok sind nur gegen nachgebildete Antworten getestet; die
  Anbieter-Dokumentation war während der Entwicklung nicht erreichbar.
- **Windows nicht auf echtem Windows getestet** (Skripte, SAPI-Stimmen).
- **Docker-Image nie gebaut** (kein Docker-Dienst in der Entwicklungsumgebung).
- **Online-Betrieb:** alle Konten teilen einen Arbeitsbereich; nur eine Instanz.
- **eSpeak klingt synthetisch**; für natürliche lokale Stimmen Piper verwenden.


---

## ClipForge 2.0 — neue bekannte Grenzen

### Cloud-Anbindungen nur gegen nachgebildete Antworten getestet
Instagram, X, TikTok (Direct Post), fal.ai (KI-Video, Avatar, Face Swap),
ElevenLabs-Stimmklon, Pexels/Pixabay, YouTube-Trends, Claude-Übersetzung und
-Texte folgen der offiziellen Dokumentation (soweit erreichbar), wurden aber
nie gegen den echten Dienst ausgeführt. Bei fal.ai-Face-Swap konnten die
Feldnamen nicht geprüft werden (per Umgebungsvariable anpassbar).
**Status:** Live-Tests nur mit deiner Freigabe und Budgetgrenze.

### Instagram braucht eine HTTPS-Weiterleitung und ein Business-/Creator-Konto
Meta erlaubt nur HTTPS-Redirect-URIs; lokal also über einen Tunnel oder im
Online-Betrieb. Für fremde Konten ist ein Meta-App-Review nötig.

### TikTok veröffentlicht ohne App-Audit nur privat
Bis TikTok die App geprüft hat, sind Direct Posts nur als „Nur ich“ möglich
(`CLIPFORGE_TIKTOK_AUDITED=1` erst nach bestandenem Audit setzen).

### Geplante Posts brauchen einen laufenden ClipForge
Der Zeitplan wird vom Hintergrund-Worker ausgeführt. Ist ClipForge zum
Zeitpunkt aus, wird der Post beim nächsten Start nachgeholt (Status „fällig“).

### Abgebrochene Veröffentlichungen werden nicht wiederholt
Nach einem Neustart mitten im Upload ist unklar, ob der Beitrag erschienen
ist. ClipForge markiert ihn als fehlgeschlagen und bittet um Prüfung auf der
Plattform — kein automatischer zweiter Post.

### Hintergrundentfernung für Videos ist auf der CPU langsam
Etwa 5 Bilder/s bei 360×480 auf 4 CPU-Kernen; 1080p deutlich langsamer.
Maximal 180 s Video je Auftrag.

### Lokale Übersetzung und Piper-Stimmen nicht real getestet
Die Modelle liegen auf Hugging Face bzw. argos-net.com, die aus der
Entwicklungsumgebung gesperrt waren. Die Logik ist getestet, die Modelle nicht.

### Lokale KI-Videos nicht eingebaut
Nur Hardware-Prüfung. Wan/LTX-Video brauchen eine NVIDIA-GPU (≥ 12 GB VRAM).

### Face Swap: Identität nicht beweisbar
ClipForge prüft, dass nur registrierte Referenzgesichter eingesetzt werden,
und protokolliert die Einwilligungserklärung. Ob das Gesicht wirklich dem
Benutzer gehört, kann Software nicht beweisen. Lokale Swap-Modelle
(inswapper u. a.) sind nicht kommerziell lizenziert und daher nicht enthalten.

### Datenhaltung in JSON-Dateien
Für eine Instanz mit wenigen Benutzern ausreichend. Viele gleichzeitige
Benutzer oder mehrere Instanzen bräuchten SQLite/PostgreSQL (nicht umgesetzt).

### Shorts-Pipeline nutzt den Server-Schlüssel für Claude
Die ältere Shorts-Analyse (Longform → Shorts) liest den Anthropic-Schlüssel
weiterhin aus der Server-Umgebung, nicht aus dem Benutzertresor. Im Online-
Betrieb mit getrennten Bereichen den Server-Schlüssel daher leer lassen oder
bewusst teilen.

### YouTube-Verbindung (privater Upload) ist instanzweit
Die bestehende YouTube-OAuth-Verbindung gilt für die ganze Instanz, nicht je
Benutzer.

### Budget ist eine Schätzung
Die lokale Budgetkontrolle reserviert geschätzte Kosten vor jedem bezahlten
Aufruf und blockiert darüber. Sie ist **keine** Ausgabengrenze beim Anbieter:
tatsächliche Abrechnungen können abweichen. Setze zusätzlich Limits in den
Konten der Anbieter (fal.ai, ElevenLabs, OpenAI, Anthropic, X).

---

## ClipForge 3.0 — neue bekannte Grenzen

### Highlight-Qualität auf echten Streams unbewiesen
Scoring und Grenzen sind mit synthetischen Streams real getestet, aber noch
nicht an echten mehrstündigen VODs mit echtem Chat justiert. Gewichte
(`DEFAULT_WEIGHTS`) sind Startwerte.

### Kein direkter Import von Twitch/YouTube/Kick
Bewusst: Videos und Chat-Exporte lädt der Nutzer selbst (eigene Inhalte).
Kick hat keine stabile öffentliche Chat-API.

### Live-Modus: nur Twitch-Chat, nur eigene OBS-Aufnahme
YouTube-/Kick-Live-Chat nicht angebunden; Live-Video nur aus lokaler Datei
(Online-Betrieb gesperrt). IRC nur gegen lokalen Testserver geprüft.

### Audio-„Schrei/Jubel“ ist eine Heuristik
Lautstärke + spektraler Schwerpunkt, keine trainierte Klassifikation.

### KI-Assistent: LLM-Engines nicht live getestet
Ollama/Claude/OpenAI nur gegen nachgebildete Antworten; der Regel-Planer
versteht nur die dokumentierten Satzmuster. Kein Gesichts-Zoom, keine
Untertitel-Farben, kein Übersetzen per Chat.

### Bezahlte KI im Stream-Kontext
Stream-Quellen haben kein eigenes Budget → dort nur Regeln/Ollama.

### Timeline ist eine Übersicht
Spuren werden angezeigt; bearbeitet wird weiterhin szenenbasiert (keine
freien Mehrspur-Schnitte).


## ClipForge 3.0 — Abnahmerunde (20.11.2026)

- **Stream-Qualität nur synthetisch gemessen** (`BENCHMARKS.md`); echte Streams fehlen.
- **„max. Clips“ begrenzt den Recall** bei langen Streams (Standard 8) — für mehrstündige
  Aufnahmen höher stellen.
- **Live-Chats nie gegen die echten Plattformen** getestet (Twitch-Host nicht auflösbar,
  kein YouTube-Schlüssel). YouTube-Live nur öffentliche Streams (kein OAuth).
- **Ollama/LLM-Planer** nur gegen nachgebildete Server; Fallback auf Regeln greift automatisch.
- **Zoom-Fokus** fest je Szene (Haar-Kaskade für „Gesicht“); kein Tracking, keine Keyframes.
- **Lautheitsnormalisierung** ist opt-in (bestehende Projekte klingen unverändert);
  zweiter Durchgang kostet ~15 % Renderzeit.
- **Untertitel-Vorschaubild** im Editor zeigt nur den Stil, nicht Farbe/Position
  (wirken beim Rendern; Render-Bericht listet sie unter `captions.layout`).
- **Mediathek** nur je Projekt; keine globale Mediathek-Seite.
- **JSON-Persistenz** ohne prozessübergreifende Transaktionen (`STORAGE_EVALUATION.md`).


## Production-Runde (21.11.2026)

- **Timeline-Vorschau** zeigt den letzten Render; neue Spuren/Keyframes sieht man erst nach „Vorschau rendern“.
- **Keyframes** für Zuschnitt und Unschärfe fehlen (beide nur statisch).
- **Audio-Ereignisse** sind eine Heuristik ohne Training; Standard „nur erklärend“.
- **Tracking** nur horizontal (Hochformat aus Querformat); kein Objekt-Tracking jenseits von Gesichtern.
- **OpenCV ≥ 5** hat keine Haar-Kaskaden: Abhängigkeit auf < 5 begrenzt; mit YuNet-Modell funktioniert die Gesichtserkennung auch ohne Haar.
- **Gemini/Claude/OpenAI/Ollama** nicht live getestet; LLM-Antworten werden nicht gestreamt.
- **Hardware-Kodierung** nur nach echtem Probelauf, hier ohne GPU nicht nutzbar; Standard CPU.
- **Übersetzung per Chat** legt ein neues Projekt an; Argos-Sprachmodell muss lokal installiert sein.
