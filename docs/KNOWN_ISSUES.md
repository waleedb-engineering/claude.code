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
**Status:** geplant — kein Multi-User-Auth für diese Beta vorgesehen.

## 3. CORS/Auth nicht für Internet-Exposition gehärtet

**Auswirkung:** Das Backend ist für **lokalen** Betrieb (127.0.0.1) gedacht.
Es gibt kein Auth und eine offene CORS-Konfiguration — ein Deployment ins
offene Internet ohne zusätzliche Härtung wäre unsicher.
**Workaround:** Nicht ins offene Internet exponieren; nur lokal oder hinter
einem selbst konfigurierten, vertrauenswürdigen Reverse-Proxy mit Auth
betreiben.
**Status:** offen, bewusst — außerhalb des Beta-Scopes.

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
