# ClipForge AI — Release Notes 0.1.0-beta.1

**Release-Typ:** geschlossene Beta / Release Candidate · local-first ·
kein Account, keine Pflicht-Cloud.

## Kurzbeschreibung

ClipForge AI verwandelt ein langes Video (Podcast, Talk, Coaching-Call) lokal
in mehrere kurze, vertikale 9:16-Clips mit eingebrannten Untertiteln,
Performance-Potential-Score und publizierfertigen Plattform-Texten. Alles läuft
auf dem eigenen Rechner; nichts wird automatisch hochgeladen.

## Zielgruppe

Technische Beta-Tester und Content-Creator, die lokal Python + Node ausführen
können und den Clip-Vorschlag an eigenen Videos beurteilen wollen. **Nicht** für
produktive Kanäle, Multi-User-Setups oder Internet-Deployment.

## Hauptfunktionen

- Upload (einzeln + Batch), lokale Transkription (faster-whisper) oder
  mitgeliefertes Transkript
- Clip-Analyzer v2 mit nachvollziehbarem Score (regelbasiert, optional per
  Claude verstärkt), Deduplizierung, Risk-Flags
- Karaoke-Untertitel, Silence-Removal, Smart-Reframe (Gesichtserkennung,
  statischer Crop), Brand Kit
- Content-Package-Generator (Titel/Hashtags/Beschreibungen pro Plattform)
- Web-Clip-Editor + Re-Render, manuelle Exporte, ZIP-Exporte
- Publishing Planner (lokale Drafts), globale Übersicht, Draft-Duplizieren
- YouTube Dry-Run; echter **privater** Upload-Pfad (Feature-Flag, default aus)
- One-Command Setup/Start, Environment Doctor, Browser-E2E-Suite

## Was neu/fertig in dieser Version ist

- Zentrale Versionierung über eine `VERSION`-Datei (Single Source of Truth) —
  konsistent in Backend (`/health`, `/api/config`), CLI (`--version`),
  Frontend-Footer und `package.json`.
- `CHANGELOG.md`, automatisierter `release_check.sh`, reproduzierbarer
  `build_beta_package.sh`.
- Beta-Dokumentation: Tester-Guide, Known Issues, YouTube-Real-Test-Checkliste,
  Security-/Privacy-Review, Release-Decision.

## Qualitätsstand

Kern-Funktionalität vollständig und durch Tests belegt. Sicherheits-Invarianten
(kein Secret-Leak, PRIVATE-only, kein Fake-Success) sind durch Tests bewiesen;
Race-/Crash-Pfade des Upload-Systems sind deterministisch getestet. Einziger
offener Verifikationspunkt: der echte YouTube-Upload gegen ein reales Konto.

## Tests

Exakte Zahlen, Evidenz und ggf. SKIPPED/BLOCKED-Begründungen:
[`docs/FINAL_BETA_QA_0.1.0-beta.1.md`](FINAL_BETA_QA_0.1.0-beta.1.md).
Umfang: Backend-Suite (inkl. YouTube-OAuth/Upload/Recovery/Race), CLI-
Regression, TypeScript, ESLint, `next build`, Playwright-Browser-E2E, Secret-
Scan (Repo + Package), frische Package-Installation.

## Bekannte Einschränkungen

Vollständig mit Auswirkung/Workaround/Status:
[`docs/KNOWN_ISSUES.md`](KNOWN_ISSUES.md). Kern: echter YouTube-Upload noch
nicht mit realem Konto E2E-verifiziert; local-first (kein Multi-User/Auth,
keine CORS-Härtung für Internet-Exposition); kein Public/Unlisted; kein
TikTok/Instagram-Auto-Upload; kein Scheduling-Daemon; kein dynamisches
Reframe; kein Auto-Resume eines unterbrochenen Uploads nach Prozessneustart;
3 dokumentierte ESLint-Tech-Debt-Punkte.

## Sicherheits-/Privacy-Hinweise

Details: [`docs/SECURITY_PRIVACY_REVIEW.md`](SECURITY_PRIVACY_REVIEW.md).

- Kein Upload ohne explizite, mehrstufige Bestätigung (`UPLOAD_PRIVATE`).
- Tokens/Secrets erscheinen **nie** im DOM, in Logs oder API-Antworten.
- YouTube-Tokens liegen ausschließlich im OS-Keychain (kein Plaintext-Fallback).
- Betrieb ist für `127.0.0.1` gedacht — **nicht** ins offene Internet
  exponieren (kein Auth, offene CORS für lokale Entwicklung).

## YouTube-Status

Der private Upload-Pfad ist implementiert und mit gemocktem Google-Client
getestet, **aber noch nicht** mit einem echten Google-Konto End-to-End
verifiziert. Er ist standardmäßig deaktiviert und ausschließlich `private`
(kein Public/Unlisted). Vorgehen für den Real-Test:
[`docs/YOUTUBE_REAL_TEST_CHECKLIST.md`](YOUTUBE_REAL_TEST_CHECKLIST.md).

## Installationshinweis

```bash
tar -xzf clipforge-beta-0.1.0-beta.1.tar.gz
cd clipforge-beta-0.1.0-beta.1
./scripts/setup_local.sh    # venv, Deps, .env, Doctor
./scripts/start_local.sh    # Backend + Frontend
# Browser: http://127.0.0.1:3000/upload
```

Ausführlich: [`docs/BETA_TESTER_GUIDE.md`](BETA_TESTER_GUIDE.md).

## Upgrade-/Reset-Hinweis

Diese Beta hält keinen Zustand außerhalb von `api/jobs/` (und optional
`api/config/brand_kit.json` + einem YouTube-Token im Keychain). Ein „Upgrade"
auf ein späteres Beta-Package erfolgt durch Entpacken der neuen Version und
erneutes `setup_local.sh`; die Job-Daten sind nicht an eine Version gebunden,
sollten bei Beta-Wechseln aber als potenziell wegwerfbar betrachtet werden.
Zurücksetzen: `rm -rf api/jobs/*` (Details:
[`docs/LOCAL_BETA_GUIDE.md`](LOCAL_BETA_GUIDE.md)).

## Beta-Feedback

Fehler bitte mit Reproduktionsschritten und der Ausgabe von
`python3 scripts/clipforge_doctor.py` melden — welche Logs unbedenklich sind
und welche Daten **nie** geteilt werden dürfen, steht im
[`Beta-Tester-Guide`](BETA_TESTER_GUIDE.md). Kein Punkt in dieser Beta ist ein
Versprechen für Reichweite oder Erfolg — der Score ist eine Einschätzung,
keine Garantie.
