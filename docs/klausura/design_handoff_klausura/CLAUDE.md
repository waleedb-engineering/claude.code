# CLAUDE.md — Projektregeln KLAUSURA

Diese Regeln gelten für allen Code, der aus `design_handoff_klausura/README.md` entsteht.

## Nicht verhandelbar
1. **Local-First.** Klausuren, Antworten, Zeiten, Profil und Regel-Overrides liegen lokal. Kein Login-Zwang, kein Server als Voraussetzung für Kernfunktionen. Schema-Migrationen einplanen — es gibt keine Cloud-Kopie.
2. **Profil ist Arithmetik, keine Typologie.** Basis 50 plus signierte Beiträge (README 8). Keine „Lerntyp"-Labels im Code, in der UI oder in Variablennamen.
3. **Jede UI-Regel hängt an einer nachlesbaren Schwelle** und ist einzeln abschaltbar (README 8.4, Screen 15). Eine Regel, die ohne Herleitung greift, ist ein Bug.
4. **Bandwechsel nur mit 5 Punkten Hysterese.** Ohne das kippt das UI bei einer einzigen geänderten Antwort.
5. **Zahlen immer Monospace mit `tabular-nums`** — Punkte, Zeiten, Ohm-Werte, Prozente.
6. **Kein Gamification-Vokabular.** Keine XP, Level, Konfetti. Feedback nennt zuerst den Ort eines Fehlers, dann die Wertung.
7. **Import-Zerlegung ist eine sichtbare Animation**, kein Spinner. Der Simulator läuft immer in Fokus-Dunkel.
8. **Einheiten werden nie stillschweigend umgerechnet.** kΩ und Ω sind getrennte Eingaben.

## Technische Leitplanken
- **Tokens statt Hex-Werte.** Die Farbrollen aus README 5.1 als Tokens/Variablen anlegen; nie eine Farbe direkt in eine Komponente schreiben. Ein Theme genügt zum Start: `Laborgerät / hell`.
- **Radius kommt aus dem Theme** (2 / 0 / 4 px), Elevation gibt es in genau einer Stufe. Karten werden durch 1-px-Hairlines getrennt, nicht durch Schatten.
- **Abgeleitetes nie speichern:** Achsenwerte, Bänder, aktive Regeln, Beherrschungsgrade und Tagesplan werden gerechnet (README 10). Persistiert werden nur Rohdaten und Overrides.
- **Reduce-Motion** ist Pflicht: `prefers-reduced-motion` setzt alle Dauern auf 1 ms, jeder Zielzustand muss ohne Bewegung vollständig lesbar sein (README 9).
- **Hit-Targets mobil nie unter 44 px**, Primäraktion in fixer Fußleiste.
- **Tastatur Desktop:** ⌘K Command-Palette, ⌘⏎ abgeben, Tab wechselt die Einheit, 1–4 wählt eine Onboarding-Option. Hinweise stehen sichtbar in Mono-Fußzeilen.

## Copy
Deutsch, nüchtern, ohne Ausrufezeichen und ohne Motivationssprache. Jede Onboarding-Option nennt ihre Konsequenz für die App — das ist Teil der Copy, nicht Beiwerk. Leerzustände nennen die Bedingung, unter der sie verschwinden.

## Arbeitsweise
- Ein Arbeitspaket aus `IMPLEMENTATION-PLAN.md` pro Commit.
- Vor jedem Screen die zugehörige README-Sektion lesen; Maße nicht schätzen.
- Beispieldaten aus dem Prototyp nur als Fixture, nie als Fallback in Produktionspfaden.
