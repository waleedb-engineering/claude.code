# Security & Privacy Review — ClipForge AI 0.1.0-beta.1

**Geprüft am:** 2026-07-23 · **Stand:** Commit der Release-Candidate-Doku
(Branch `claude/ai-video-shorts-tool-hjct7s`).

Diese Review dokumentiert die geprüften Bereiche, das Ergebnis und die
bewussten Sicherheits-Defaults. Sie ersetzt kein externes Security-Audit,
sondern hält den Ist-Stand für Beta-Tester und spätere Prüfer fest.

---

## Geprüfte Bereiche & Ergebnis

| Bereich | Methode | Ergebnis |
|---|---|---|
| Google-Token-Werte (`ya29.`, `1//`, `GOCSPX-`) | `git grep` über alle getrackten Dateien | **0 echte Treffer** |
| Anthropic-/Google-API-Keys (`sk-ant-…`, `AIza…`) | `git grep` | **0 echte Treffer** (nur `sk-ant-...`-Platzhalter in README-Doku) |
| `.env` / echte Credential-JSON getrackt | `git ls-files` | **NEIN** — nur `.env.example` + `web/.env.example` |
| `.env.example`-Inhalt | Sichtprüfung | nur Platzhalter/`127.0.0.1`, alle Secrets auskommentiert |
| Bearer-/Authorization-Werte | `git grep` | **0 echte Treffer** (nur Regex-Definitionen + Doku-Prosa) |
| Test-Sentinels (`_SENTINEL_*`) | `git grep` | bewusste, klar benannte Fake-Werte in Tests — kein Leak |
| Medien/Binärdateien getrackt (`*.mp4`, `*.zip`, …) | `git ls-files` | **0** — Video-Fixtures sind gitignored |
| Absolute lokale Pfade (`/home/…`, `/Users/…`) in Code | `git grep` (ohne Docs) | **0** |
| `dist/`-Beta-Package getrackt | `git ls-files` | **NEIN** (gitignored) |
| Beta-Package-Inhalt | entpacken + scannen | keine `.env`, keine Medien, keine Secret-Werte |
| Automatisierter Secret-Scan | `scripts/release_check.sh` §11 | **PASS** |

**Gesamtergebnis: keine echten Secrets, Tokens, Credentials oder
personenbezogenen Daten im Repository oder im gebauten Beta-Package gefunden.**

### Ehrliche Abgrenzung (Platzhalter ≠ Leak)

Ein naiver Substring-Scan „findet" die Marker `access_token`, `client_secret`
usw. an vielen Stellen — das sind **Feldnamen im Code**, **Regex-Definitionen
des Scanners selbst** (`scripts/release_check.sh`, `web/e2e/helpers/youtube.ts`),
**Doku-Prosa** über die Sicherheitszusagen, oder **Test-Sentinels** (bewusst
benannte Fake-Werte wie `ACCESS_SENTINEL_zzz`). Keiner davon ist ein echter
Secret-Wert. Der dokumentierte Scan zielt auf **Wert-tragende** Formen (z. B.
`"client_secret": "<echter-string>"`) und die bekannten Google-/Anthropic-
Token-Präfixe.

---

## Sichere Defaults (im Code verankert)

- **YouTube-Upload standardmäßig deaktiviert** —
  `CLIPFORGE_ENABLE_YOUTUBE_UPLOAD=false`. Der echte Real-Test braucht ein
  **zweites**, unabhängiges Flag (`CLIPFORGE_ENABLE_YOUTUBE_REAL_TEST`) plus
  eine interaktive `UPLOAD_PRIVATE`-Bestätigung.
- **PRIVATE-only** — `ALLOWED_PRIVACY = "private"` in
  `api/clipforge/platforms/youtube_upload.py`. Es existiert **kein** Code-Pfad
  für `public` oder `unlisted`; abweichende Werte werden mit
  `invalid_privacy_status` abgelehnt.
- **Kein Auto-Posting, kein Scheduling-Daemon, kein TikTok/Instagram-Upload.**
- **Token-Speicherung nur im OS-Keychain** (`keyring`), **kein
  Plaintext-Fallback**. Fehlt das Keychain-Backend, meldet die Readiness sauber
  `token_store_available: false` — es wird nichts unverschlüsselt abgelegt.
- **Keine Secrets in Ausgaben:** Backend-Responses tragen `no_secrets: true`;
  Tokens/Client-Secrets/`id_token`/Session-URIs erscheinen nie in Response,
  Log, Exception oder Browser-DOM. Der resumable Session-URI wird bewusst nicht
  persistiert.
- **Idempotenz & Race-Schutz:** ein Draft mit `external_post_id` wird nicht
  erneut hochgeladen; gleichzeitige Anforderungen führen durch atomaren Claim
  zu genau einem Upload.

## YouTube: PRIVATE-only

Der einzige echte Upload-Pfad lädt ausschließlich **privat** hoch (nur der
Kontoinhaber sieht das Video). Public/Unlisted sind nicht implementiert und
nicht per Konfiguration erreichbar. Ablauf und Verifikation:
[`YOUTUBE_REAL_TEST_CHECKLIST.md`](YOUTUBE_REAL_TEST_CHECKLIST.md).

## Local-first / Datenfluss

- Videos, Clips, Transkripte und Publishing-Drafts liegen ausschließlich lokal
  unter `api/jobs/` (überschreibbar via `CLIPFORGE_JOBS_DIR`). Kein Cloud-Sync.
- **Zwei optionale, bewusst zu aktivierende** Ausnahmen, bei denen Daten den
  Rechner verlassen:
  1. **KI-Analyzer:** sendet **Transkript-Text** an die Anthropic-API — nur mit
     gesetztem `ANTHROPIC_API_KEY`. Ohne Key läuft alles regelbasiert & lokal.
  2. **Echter YouTube-Upload:** sendet das **Video** an Google — nur mit
     gesetzten Flags + Bestätigung.

## Deployment-Hinweis (wichtig)

ClipForge ist für **lokalen** Betrieb auf `127.0.0.1` gedacht. Das Backend hat
**kein Auth** und eine **offene CORS-Konfiguration** (für lokale Entwicklung).
**Nicht ins offene Internet exponieren.** Ein öffentliches Deployment würde
zusätzliche Härtung (Auth, CORS-Restriktion, TLS, Rate-Limiting,
Mandantentrennung) erfordern, die bewusst nicht Teil dieser Beta ist.

---

## Bekannte Risiken / offene Punkte

| Risiko | Schwere | Status |
|---|---|---|
| Echter YouTube-Upload nicht mit realem Konto E2E-verifiziert | mittel | offen — [Checkliste](YOUTUBE_REAL_TEST_CHECKLIST.md) |
| Kein Auth / offene CORS (nur lokal sicher) | hoch bei Fehlnutzung | bewusst, dokumentiert — nicht exponieren |
| Kein Multi-User / keine Mandantentrennung | mittel | bewusst, nicht Beta-Scope |
| Kein Auto-Resume unterbrochener Uploads nach Prozessneustart | niedrig | bewusst — sichere Recovery statt Blind-Retry |

Vollständige, laufend gepflegte Liste: [`KNOWN_ISSUES.md`](KNOWN_ISSUES.md).

## Reproduzierbarkeit dieser Review

```bash
# Automatisierter Secret-Scan als Teil des Release-Gates:
./scripts/release_check.sh        # Abschnitt 11–14

# Manuell (getrackte Dateien) — echte Token-Wertformate:
git grep -nIE "ya29\.[A-Za-z0-9_-]{20}|1//[0-9A-Za-z_-]{20}|GOCSPX-[A-Za-z0-9_-]{10}|sk-ant-[A-Za-z0-9]{20}|AIza[0-9A-Za-z_-]{30}" -- .

# .env / Credential-Dateien dürfen nicht getrackt sein:
git ls-files | grep -iE "\.env$|client_secret|credentials.*json|token.*json"
```
