# Release Decision — ClipForge AI 0.1.0-beta.1

Ehrliche Go/No-Go-Einschätzung pro Release-Stufe. Kein Marketing, keine
Produktionsclaims.

**Current status:** Release Candidate `0.1.0-beta.1` (geschlossene Beta).

---

## Is it ready for closed beta (local testers)? — **JA**

Begründung:

- Kern-Funktionalität vollständig und durch die Testsuite belegt
  (siehe [`FINAL_BETA_QA_0.1.0-beta.1.md`](FINAL_BETA_QA_0.1.0-beta.1.md)).
- One-Command Setup/Start, Environment Doctor und eine frische
  Package-Installation sind verifiziert — ein technischer Tester kann ohne
  Vorwissen starten.
- Sicherheits-Invarianten (kein Secret-Leak, PRIVATE-only, kein Fake-Success)
  sind durch Tests bewiesen; Race-/Crash-Pfade sind deterministisch getestet.
- Klare, ehrliche Dokumentation von Grenzen und Risiken.

Der offene YouTube-Real-Test blockiert die **lokale** Beta nicht, weil der
Upload standardmäßig deaktiviert ist und nicht Teil des Standard-Testflows ist.

## Is it ready for public release? — **NEIN**

Begründung:

- Local-first ohne Auth, mit offener CORS — **nicht** für Internet-Exposition
  gehärtet.
- Kein Multi-User, keine Mandantentrennung.
- Echter YouTube-Upload noch nicht mit realem Konto E2E-verifiziert.
- Ein öffentliches Release würde falsche Reife suggerieren.

## Is it ready for a GitHub Release? — **OPTIONAL**

Ein GitHub **Pre-Release** (als *Beta*/*Pre-release* markiert) wäre vertretbar,
um das Beta-Package geschlossenen Testern bereitzustellen — **nur** klar als
Beta gekennzeichnet, mit Link auf Known Issues und Release Notes. Kein
regulärer „Latest"-Release. Aktuell nicht ausgeführt (bewusst, keine Freigabe).

## Is it ready for tag `v0.1.0-beta.1`? — **OPTIONAL / EMPFOHLEN**

Ein annotiertes Tag `v0.1.0-beta.1` auf dem aktuellen, grünen Stand ist sinnvoll
und risikoarm (rein lokal/immutabler Marker). Es wird hier **nicht** erstellt;
die exakten Befehle liegen vorbereitet in
[`RELEASE_COMMANDS_OPTIONAL.md`](RELEASE_COMMANDS_OPTIONAL.md) und laufen nur
nach ausdrücklicher Freigabe.

---

## Remaining blocker

**Echter YouTube-Private-Upload-Test mit einem realen Google-Konto.** Solange
dieser nicht als PASS dokumentiert ist, gilt der Upload-Pfad als
„implementiert, aber real unverifiziert". Runbook:
[`YOUTUBE_REAL_TEST_CHECKLIST.md`](YOUTUBE_REAL_TEST_CHECKLIST.md).

Dieser Blocker betrifft ausschließlich die YouTube-Upload-Funktion, nicht den
restlichen (lokal vollständig nutzbaren) Funktionsumfang.

## Recommended next action

1. Geschlossene Beta mit lokalen Testern starten (Package + Tester-Guide
   verteilen).
2. Parallel den YouTube-Real-Test nach Checkliste mit einem Test-Konto
   durchführen und das Ergebnis (PASS/BLOCKED/FAIL) dokumentieren.
3. Optional: nach grünem Real-Test Tag `v0.1.0-beta.1` setzen und ggf. ein
   GitHub-Pre-Release erstellen — beides erst nach ausdrücklicher Freigabe.
