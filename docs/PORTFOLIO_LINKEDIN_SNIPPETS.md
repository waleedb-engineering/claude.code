# Portfolio / LinkedIn / CV — ClipForge AI

Fertige, ehrliche Textbausteine, um ClipForge AI professionell zu beschreiben.
Alle Formulierungen sind bewusst **nicht** übertrieben und vermeiden falsche
Produktions-/Marktreife-Claims (siehe letzter Abschnitt). Version zum Stand
`0.1.0-beta.1` (geschlossene Beta).

> Platzhalter `[Repo-Link]` / `[Name]` vor Verwendung ersetzen.

---

## 1. Kurze Projektbeschreibung — DE (3–4 Sätze)

> ClipForge AI ist ein local-first Tool, das lange Videos automatisch in kurze,
> vertikale 9:16-Clips mit Untertiteln, einem transparenten Performance-Score
> und publizierfertigen Plattform-Texten verwandelt. Backend (FastAPI/Python),
> Web-App (Next.js/TypeScript) und eine FFmpeg-Rendering-Pipeline laufen
> vollständig lokal — ohne Account und ohne Pflicht-Cloud. Der Fokus liegt auf
> nachvollziehbaren Entscheidungen, sicheren Defaults (PRIVATE-only
> YouTube-Pfad, standardmäßig deaktiviert) und einer testbaren, reproduzierbaren
> Release-Struktur. Aktueller Stand: geschlossene Beta.

## 2. Short project description — EN (3–4 sentences)

> ClipForge AI is a local-first tool that turns long videos into short vertical
> 9:16 clips with burned-in captions, a transparent performance score, and
> ready-to-post platform copy. A FastAPI/Python backend, a Next.js/TypeScript
> web app, and an FFmpeg rendering pipeline run entirely on the user's machine —
> no account, no mandatory cloud. It emphasizes explainable decisions, safe
> defaults (a private-only YouTube path, disabled by default), and a testable,
> reproducible release process. Current status: closed beta.

---

## 3. LinkedIn Project Description — EN

> **ClipForge AI — local-first AI video-shorts tool (closed beta)**
>
> A tool that automatically turns long-form video (podcasts, talks) into short
> vertical shorts with captions and publish-ready metadata — running entirely
> on the user's own machine.
>
> What I built:
> • Video-to-shorts pipeline in Python/FFmpeg: local transcription, explainable
>   clip selection, a transparent performance-potential score, karaoke captions,
>   and local face-aware reframing.
> • FastAPI backend + Next.js/TypeScript web app (upload, live job status,
>   editor with re-render, publishing planner).
> • A private-only YouTube upload path built on the official Google API with a
>   crash-safe state machine (idempotency, retry/backoff, recovery,
>   reconciliation, race protection) — disabled by default and gated behind
>   explicit confirmation.
> • Engineering for testability and release: a browser E2E suite (Playwright),
>   a backend test suite, an environment doctor, one-command setup/start, an
>   automated release check, and a reproducible, secret-free package build.
>
> Deliberately scoped as a local-first beta: no auto-publishing, no
> public/unlisted uploads, no multi-user auth. The real-account YouTube upload
> is implemented but pending end-to-end verification.
>
> Stack: Python, FastAPI, FFmpeg, faster-whisper, Next.js, TypeScript, React,
> Tailwind, Playwright. [Repo-Link]

## 4. LinkedIn Project Description — DE

> **ClipForge AI — local-first AI-Video-Shorts-Tool (geschlossene Beta)**
>
> Ein Tool, das lange Videos (Podcasts, Talks) automatisch in kurze,
> vertikale Shorts mit Untertiteln und publizierfertigen Metadaten verwandelt —
> vollständig lokal auf dem eigenen Rechner.
>
> Was ich gebaut habe:
> • Video-zu-Shorts-Pipeline in Python/FFmpeg: lokale Transkription,
>   nachvollziehbare Clip-Auswahl, transparenter Performance-Score,
>   Karaoke-Untertitel, lokales gesichtsbewusstes Reframing.
> • FastAPI-Backend + Next.js/TypeScript-Web-App (Upload, Live-Job-Status,
>   Editor mit Re-Render, Publishing-Planner).
> • Ein PRIVATE-only YouTube-Upload-Pfad auf Basis der offiziellen Google-API
>   mit crash-sicherer Zustandsmaschine (Idempotenz, Retry/Backoff, Recovery,
>   Reconciliation, Race-Schutz) — standardmäßig deaktiviert und hinter
>   expliziter Bestätigung.
> • Engineering für Testbarkeit und Release: Browser-E2E-Suite (Playwright),
>   Backend-Testsuite, Environment Doctor, One-Command Setup/Start,
>   automatisierter Release-Check, reproduzierbares secret-freies Package.
>
> Bewusst als local-first Beta abgegrenzt: kein Auto-Publishing, keine
> Public/Unlisted-Uploads, kein Multi-User-Auth. Der Upload gegen ein echtes
> YouTube-Konto ist implementiert, aber noch nicht End-to-End verifiziert.
>
> Stack: Python, FastAPI, FFmpeg, faster-whisper, Next.js, TypeScript, React,
> Tailwind, Playwright. [Repo-Link]

---

## 5. CV Bullet Points — DE (max. 5)

- Konzipiert und entwickelt: **ClipForge AI**, ein local-first Tool, das lange
  Videos automatisch in bewertete 9:16-Shorts mit Untertiteln umwandelt
  (Python/FastAPI-Backend, Next.js/TypeScript-Frontend, FFmpeg-Pipeline).
- Erklärbare **Clip-Analyse & Scoring**: lokale Transkription (faster-whisper),
  regelbasierter Analyzer mit transparentem Performance-Score, optional durch
  ein LLM verstärkt.
- **Sicherer YouTube-Upload-Pfad** (PRIVATE-only, default deaktiviert) mit
  crash-sicherer State-Machine: Idempotenz, Retry/Backoff, Recovery,
  Reconciliation und Race-Schutz.
- **Test- & Release-Engineering:** Backend-Testsuite (20 Dateien) + Playwright-
  Browser-E2E (13 Flows), Environment Doctor, automatisierter Release-Check,
  reproduzierbares Beta-Package.
- **Security-aware Design:** sichere Defaults, keine Secrets in Logs/DOM/
  Responses, Token nur im OS-Keychain, dokumentierte Grenzen (nur lokal, kein
  Multi-User).

## 6. CV Bullet Points — EN (max. 5)

- Designed and built **ClipForge AI**, a local-first tool that turns long
  videos into scored 9:16 shorts with captions (Python/FastAPI backend,
  Next.js/TypeScript frontend, FFmpeg pipeline).
- Explainable **clip analysis & scoring**: local transcription
  (faster-whisper), a rule-based analyzer with a transparent performance score,
  optionally enhanced by an LLM.
- **Safe YouTube upload path** (private-only, disabled by default) with a
  crash-safe state machine: idempotency, retry/backoff, recovery,
  reconciliation, and race protection.
- **Test & release engineering:** backend test suite (20 files) + Playwright
  browser E2E (13 flows), an environment doctor, an automated release check,
  and a reproducible beta package.
- **Security-aware design:** safe defaults, no secrets in logs/DOM/responses,
  tokens stored only in the OS keychain, clearly documented limitations
  (local-only, no multi-user).

---

## 7. GitHub README Kurzpitch

> **Local-first AI video-shorts tool.** Turn one long video into several
> ready-to-post vertical shorts — captions, a transparent performance score, and
> platform-ready copy — entirely on your own machine. No account, no mandatory
> cloud. Closed beta.

## 8. Recruiter-freundliche Erklärung

> ClipForge ist ein Nebenprojekt, an dem ich einen kompletten,
> produktnahen KI-Workflow eigenständig umgesetzt habe: von der Video-Analyse
> über die Aufbereitung bis zur Web-Oberfläche und einer sauberen
> Release-Struktur. Es zeigt, dass ich nicht nur einzelne Modelle anbinde,
> sondern ein Gesamtsystem baue — mit Tests, Dokumentation, sicheren
> Voreinstellungen und ehrlicher Kommunikation darüber, was fertig ist und was
> noch nicht. Es ist bewusst als lokale Beta positioniert, kein fertiges
> kommerzielles Produkt.

## 9. Technische Erklärung für Entwickler

> Monorepo mit klarer Trennung: `api/clipforge/` (reiner Pipeline-Kern:
> Transkription, Segmentierung, Scoring, Content-Generierung, FFmpeg-Rendering),
> `api/app.py` (dünne FastAPI-Bridge, keine Produktlogik), `web/` (Next.js-App
> mit TypeScript, Server- und Client-Komponenten). Der YouTube-Upload ist als
> eigene, persistente Zustandsmaschine modelliert (`platforms/youtube_*`) mit
> atomarem Claim gegen Races, Startup-Recovery für verwaiste Zustände und
> ID-basierter Reconciliation statt Heuristik. Qualität wird über eine
> abhängigkeitsarme Python-Testsuite, eine Playwright-Browser-E2E-Suite und ein
> aggregierendes `release_check.sh`-Gate abgesichert; das Beta-Package wird
> deterministisch aus dem getrackten Dateistand gebaut. Sicherheit ist
> defensiv: optionale Dependencies degradieren sauber, Secrets landen nie in
> Logs/DOM/Responses, Tokens nur im OS-Keychain.

---

## 10. Was NICHT behauptet werden darf

Diese Aussagen sind **falsch** und dürfen nirgends stehen:

- ❌ „production-ready" / „produktionsreif" / „enterprise-ready"
- ❌ „fully verified YouTube publishing" / „getesteter Live-YouTube-Upload"
  (der echte Upload ist implementiert, aber **nicht** real E2E-verifiziert)
- ❌ „supports all platforms" / „auto-posts to TikTok & Instagram"
- ❌ „public/unlisted YouTube uploads"
- ❌ „viral guarantee" / „garantiert virale Clips" / „AI picks the best clips"
  (der Score ist eine Einschätzung, keine Garantie)
- ❌ „secure for internet exposure" / „multi-user ready"
- ❌ „fertiges kommerzielles SaaS-Produkt"

Korrekte Formulierungen stattdessen: *local-first*, *closed beta*,
*release candidate*, *ready for local beta testing*, *private-only upload path
(disabled by default)*, *implemented but pending real-account E2E verification*,
*no cloud account required*.
