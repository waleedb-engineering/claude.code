# Changelog

Alle nennenswerten Änderungen an ClipForge AI. Format angelehnt an
[Keep a Changelog](https://keepachangelog.com/), Versionierung: einfaches
Semver mit Beta-Suffix (`MAJOR.MINOR.PATCH-beta.N`). Aktuelle Version: siehe
[`VERSION`](VERSION).

---

# Unveröffentlicht

## Creator Studio (neu)
- Quellen: Skript, Prompt, Artikel-/Website-/Social-URL (SSRF-geschützt), PDF,
  Audio, Musik (Beat-Sync), Podcast/Longform (bestehende Pipeline), eigene
  Medien, bestehender Job, Produkt-Ad
- Lokaler FFmpeg-Renderer: 9:16, 16:9, 1:1, 4:5 · 720p/1080p/4K · Captions
  (minimal, bold, karaoke, dynamic, none) · Musik mit Ducking · Split-Screen ·
  Cinematic-Look
- Provider-Gateway mit Kostenabschätzung und hartem Budgetlimit; lokale und
  optionale Cloud-Provider (ElevenLabs, OpenAI) — Cloud-Adapter nicht gegen
  echte APIs verifiziert
- Szenen-Editor mit Autosave, Undo/Redo, Versionskonflikt-Schutz, Vorschau-
  und Final-Render, Einzel-Szenen-Regeneration
- Persistente Hintergrund-Aufgaben und Automation-Worker (täglich,
  wöchentlich, monatlich) mit Wiederaufnahme nach Neustart
- Publishing: Plattform `x`, Readiness je Plattform, Planung markiert
  fällige Entwürfe, manuell bestätigte Veröffentlichung
- Analytics mit manuellen/synchronisierten Metriken, Hook-Vergleich, Remix
- Ideen-Bibliothek, Studio-CLI, `feature_flags.json`
- Härtung: Local-API-Schutz (Token für Mutationen, CORS nur lokal), atomare
  Budgetreservierung je Projekt, API-Schlüssel setzen/löschen ohne Neustart,
  typisierte Produktionsoptionen bis in den Render, Cancel bleibt Cancel,
  unterbrochene Projekte werden nach Neustart erkannt
- Funktionsrunde: lokale Stimme für Windows/macOS/Linux (eSpeak NG über pip,
  Windows-SAPI, Piper), Sprechtempo, Windows-Startskripte, Benutzeranmeldung
  für den Online-Betrieb, Docker, YouTube-Import für eigene Videos, KI-Video
  und Talking Avatar (fal.ai), Stimmklon mit Einwilligung (ElevenLabs),
  TikTok-Upload in die Entwürfe — Cloud-Adapter gegen echte APIs ungetestet
- Ursprünglich nicht enthalten: KI-Video, Talking Avatar, Face Swap, Voice Cloning,
  YouTube-Import, Upload zu TikTok/Instagram/X — siehe
  `docs/REVID_PARITY_STATUS.md`

---

# 0.1.0-beta.1

Erster geschlossener Beta-Stand. Lokales Tool, kein Account, keine Cloud
(außer bewusst aktivierte optionale Features). Läuft komplett auf dem eigenen
Rechner.

## Core
- Video-Upload (Einzel- und Batch-Upload, mehrere Formate)
- Batch-Verarbeitung mit Queue-Ansicht
- Persistente Job-Registry (Jobs überleben einen Server-Neustart)
- Job-Restore nach Neustart (inkl. `interrupted`/`incomplete`-Erkennung)
- Kooperatives Job-Abbrechen
- Sicheres Löschen (einzeln + Bulk-Cleanup) mit Storage-Übersicht

## Video Processing
- Silence-Removal („schnelle Schnitte") mit korrektem Untertitel-Remapping
- Audio-Smoothing an Schnittstellen (kurze Fades gegen Klick-Geräusche)
- Smart-Reframe (lokale Gesichtserkennung, OpenCV) mit Center-Fallback
- Wortgenaue Karaoke-Captions (2 Styles: `clean`, `high_energy`)
- Lokales Brand Kit (Farben/Watermark, optional)

## Intelligence
- Clip-Analyzer v2 (regelbasiert, optional durch Claude verstärkt)
- Performance-Potential-Score mit nachvollziehbarer Aufschlüsselung
- Score-Kalibrierung und Analyzer-Härtung
- Kandidaten-Deduplizierung
- Content-Package-Generator (Titel, Hook-Varianten, Hashtags, Plattform-Texte)

## Editor & Exports
- Web-Clip-Editor (Start/Ende feinjustieren, Re-Render als separater Export)
- Manuelle Exporte (clip-übergreifende Übersicht, einzeln abrufbar)
- ZIP-Exports (`exports.zip` nur Auto-Clips, `all-exports.zip` vollständig)

## Publishing
- Publishing Planner (lokale Drafts, kein Auto-Upload)
- Globale Publishing-Übersicht (Suche/Filter über alle Jobs)
- Draft-Duplizieren (plattformübergreifend)
- YouTube Dry-Run (zeigt, was hochgeladen würde — kein echter Upload)
- YouTube-OAuth (Consent-URL, PKCE+CSRF, Token nur im OS-Keychain)
- YouTube PRIVATE-Upload-Pfad (`videos.insert`, ausschließlich `private`,
  explizite Bestätigung erforderlich, Feature-Flag default aus)
- Retry/Backoff mit Attempt-History
- Crash-sichere Recovery (Startup-Scan für verwaiste Upload-Zustände)
- ID-basierte Reconciliation (Remote-Status-Abgleich ohne Blind-Retry)
- Race-Schutz (gleichzeitige Requests führen nie zu doppeltem Upload)

## Developer Experience
- Environment Doctor (`scripts/clipforge_doctor.py`)
- One-Command Setup (`scripts/setup_local.sh`)
- One-Command Start (`scripts/start_local.sh`)
- Browser-E2E-Smoke-Suite (Playwright, 13 Tests, 8 kritische Flows)
- Zentrale Versionierung (`VERSION`-Datei als Single Source of Truth)

## Known Limitations
- Echter YouTube-Upload ist implementiert, aber **nicht** mit einem echten
  Google-Konto End-to-End verifiziert (nur Mock-Pfad + manueller Testmodus)
- Local-first: kein Multi-User, kein Auth, kein CORS-Härtung für
  Internet-Exposition
- Kein Public- oder Unlisted-Upload — ausschließlich `private`
- Kein TikTok-, kein Instagram-Auto-Upload (nur lokale Publishing-Packs)
- Kein automatisches Scheduling/Posting (kein Daemon)
- 3 dokumentierte ESLint-Tech-Debt-Punkte (`react-hooks/set-state-in-effect`,
  funktional unkritisch)

Details zu Grenzen und Workarounds: [`docs/KNOWN_ISSUES.md`](docs/KNOWN_ISSUES.md).
