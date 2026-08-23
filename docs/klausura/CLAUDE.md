# CLAUDE.md — Projektregeln KLAUSURA

Gilt für allen Code dieses Projekts. Erweitert `design_handoff_klausura/CLAUDE.md`
um Kern-, Port- und Testregeln. Bei Widerspruch gewinnt das Design-Handoff in
UI-Fragen, dieses Dokument in Architekturfragen.

## Nicht verhandelbar — aus dem Design-Handoff

1. **Local-First.** Klausuren, Antworten, Zeiten, Profil und Overrides liegen
   lokal. Kein Login-Zwang, kein Server als Voraussetzung. Es gibt keine
   Cloud-Kopie — Migrationen entsprechend behandeln.
2. **Profil ist Arithmetik, keine Typologie.** Basis 50 plus signierte Beiträge.
   Keine „Lerntyp"-Labels in Code, UI oder Variablennamen.
3. **Jede UI-Regel hängt an einer nachlesbaren Schwelle** und ist einzeln
   abschaltbar. Eine Regel, die ohne Herleitung greift, ist ein Bug.
4. **Bandwechsel nur mit 5 Punkten Hysterese.**
5. **Zahlen immer Monospace mit `tabular-nums`.**
6. **Kein Gamification-Vokabular.** Kein XP, kein Level, keine Serien, kein
   Konfetti. Feedback nennt zuerst den Ort eines Fehlers, dann die Wertung.
7. **Import-Zerlegung ist eine sichtbare Animation**, kein Spinner. Der
   Simulator läuft immer in Fokus-Dunkel.
8. **Einheiten werden in der Eingabe nie stillschweigend umgerechnet.**
   `kΩ` und `Ω` sind getrennte Eingaben. Die *Bewertung* darf umrechnen und
   vergibt dabei `E-POT`, wenn die Größenordnung abweicht (`docs/klausura/05`).

## Architektur

- **`packages/core` importiert nur `ports` und `model`.** Kein `fetch`, kein
  `fs`, kein `Date.now()`, kein ungeseedetes `Math.random()`. Der Lint-Rule
  erzwingt das; wer ihn umgeht, bricht die Testbarkeit von Timer, Scheduler
  und Variantenziehung.
- **Zeit kommt aus `ClockPort`**, Zufall aus einem injizierten Seed.
- **Abgeleitetes nie speichern:** Achsenwerte, Bänder, aktive Regeln,
  Beherrschungsgrade, Tagesplan, Prognose. Persistiert werden Rohdaten und
  ausdrückliche Nutzerentscheidungen.
- **Nutzerkorrekturen sind Overrides.** Eine erneute Automatik darf sie nie
  überschreiben (Invariante I12).
- **Kein LLM-Aufruf ohne bestätigte `preview()`.** Jeder Aufruf wird lokal
  protokolliert. Assets gehen nie an ein LLM ohne ausdrückliche Bildfreigabe.
- **API-Keys nur über `KeychainPort`.** Nie in der Datenbank, nie in einer
  Konfigurationsdatei, nie im Log.
- **Logs enthalten keine Inhalte** — keine Aufgabentexte, keine Antworten,
  keine Dateinamen von Klausuren. Nur IDs.

## UI

- **Tokens statt Hex-Werte.** Farbrollen aus `ui-tokens`; nie eine Farbe direkt
  in eine Komponente. Ein Theme genügt zum Start: `Laborgerät / hell`.
- **Radius kommt aus dem Theme**, Elevation gibt es in genau einer Stufe.
  Karten trennen 1-px-Hairlines, keine Schatten.
- **Keine hartkodierten ms-Werte und keine hartkodierten `cubic-bezier`**
  außerhalb der Motion-Tokens.
- **Reduce-Motion für jede Animation** — als sofortiger Zustandswechsel, nicht
  als ersatzloses Streichen. Der Timer bleibt dort funktional.
- **Hit-Targets mobil nie unter 44 px**, Primäraktion in fixer Fußleiste.
- **Tastatur Desktop:** `⌘K` Command-Palette, `⌘⏎` abgeben, `Tab` wechselt die
  Einheit, `1–4` wählt eine Onboarding-Option. Hinweise stehen sichtbar in
  Mono-Fußzeilen.

## Tests

- **Domäne testet man dicht**, Adapter dünn, UI mit fünf E2E-Pfaden
  (`docs/klausura/08`).
- **Diese Tests sind verpflichtend und dürfen nie rot werden:**
  - Reproduktion des Beispielprofils: `82 / 54 / 28 / 60 / 71 / 34`
  - Einheitenfall: `12 kΩ` gegen `12000 Ω` → volle Punkte, kein `E-POT`
  - Override-Überleben nach erneuter Auto-Segmentierung
  - Golden-Migration über alle je ausgelieferten Schemaversionen
- **Golden-File-Korpus liegt außerhalb des Repos** (Urheberrecht). Im Repo
  nur die erwarteten Ergebnisse als JSON.
- **Beispieldaten aus dem Prototyp** sind Fixtures, nie Fallback in
  Produktionspfaden.

## Copy

Deutsch, nüchtern, ohne Ausrufezeichen und ohne Motivationssprache. Jede
Onboarding-Option nennt ihre Konsequenz für die App — das ist Teil der Copy,
nicht Beiwerk. Leerzustände nennen die Bedingung, unter der sie verschwinden.
Die Prognose nennt Unsicherheit, nie eine nackte Zahl.

## Arbeitsweise

- Ein Arbeitspaket pro Commit, entlang `docs/klausura/09-roadmap.md`.
- Vor jedem Screen die zugehörige Handoff-Sektion lesen; Maße nicht schätzen.
- Kollidiert eine Handoff-Regel mit einer Konvention dieses Repos: nachfragen,
  nicht entscheiden.
- Eine verletzte Invariante wird geloggt und sichtbar gemeldet — nie still
  korrigiert.

## Befehle

Werden in M0 festgelegt und hier ergänzt. Vorgesehen:

```
pnpm test           Kern-Unit-Tests (Node, schnell)
pnpm test:golden    Pipeline gegen den lokalen Klausurkorpus
pnpm lint           inkl. Regel „core importiert kein IO"
pnpm dev:desktop    Tauri im Entwicklungsmodus
pnpm dev:mobile     Expo im Entwicklungsmodus
pnpm migrate:test   Golden-Migration über alle Schemaversionen
```

## Do-Nots

- Keine Farbe, kein Radius, keine Dauer hartkodiert.
- Kein abgeleiteter Wert in der Datenbank.
- Kein Netzaufruf im Kern.
- Keine Variante ohne Verifikation vorlegen.
- Keine Prognosezahl unter der Datenschwelle.
- Kein Sharing-, Upload- oder Pool-Feature in v1.
- Keine Handschrifterkennung — Eingabe ist getippt.
- Kein Test übersprungen, deaktiviert oder in Quarantäne gestellt, um grün zu werden.
