# Changelog

Alle nennenswerten Änderungen an ClipForge AI. Format angelehnt an
[Keep a Changelog](https://keepachangelog.com/), Versionierung: einfaches
Semver mit Beta-Suffix (`MAJOR.MINOR.PATCH-beta.N`). Aktuelle Version: siehe
[`VERSION`](VERSION).

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
