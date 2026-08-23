# Umsetzungsplan — Arbeitspakete

Ein Paket pro Commit. Jede Referenz zeigt in `README.md`.

## P0 · Fundament
- **P0.1 Tokens & Typo-Skala** (README 5) — Farbrollen, Typo-Token, 4-pt-Spacing, Radius, eine Elevation-Stufe. Nur Theme `Laborgerät / hell` + Fokus-Dunkel.
- **P0.2 Persistenz-Layer** (README 10) — lokales Schema für Klausuren, Aufgaben, Antworten, Zeiten, Onboarding-Antworten, Regel-Overrides, Fehlerklassen; Migrationspfad.
- **P0.3 Profil-Engine** (README 8) — Beitragstabelle Frage×Option → Achsen, `clamp(0, 50 + Σ, 100)`, Bänder, Hysterese, Schwellenwerk, Overrides. Reine Funktionen, unit-getestet: Beispielprofil muss 82 / 54 / 28 / 60 / 71 / 34 ergeben.

## P1 · Komponenten (README 6)
- **P1.1** Timer-Ring (4 Zustände + Balken-Variante bei hoher Prüfungsangst), Punkte-Badge, Aufgabenkarte.
- **P1.2** Einheiten-Input (getrennte Präfixe, Tab wechselt Einheit), Formel-Input mit Sonderzeichenleiste.
- **P1.3** Diff-Zeile, Graph-Knoten, Heatmap-Zelle, Simulator-Leiste.
- **P1.4** Toast, Modal „Abgabe erzwingen", Segmented Control, Command-Palette (⌘K).

## P2 · Kernfluss
- **P2.1 Screen 04 Solve-View** mit allen 5 Zuständen (README 7.04) — hier hängt das Produkt.
- **P2.2 Screen 02 Import** inkl. Zerlege-Animation (Scanlinie 800 ms, Karten 240 ms).
- **P2.3 Screen 03 Atlas** mit profilabhängiger Sortierung.
- **P2.4 Screen 05 Rechenweg-Diff.**

## P3 · Profil sichtbar machen
- **P3.1 Screen 01 Onboarding**, 12 Fragen + Schritt 13 Profilergebnis; jede Option nennt ihre Wirkung.
- **P3.2 Screen 14 Profil-Logik** inkl. Rückwärts-Ansicht: Antwort ändern → Achsen, Bänder, Schwellenwerk rechnen live neu, gekippte und von der Hysterese gehaltene Regeln sind markiert.
- **P3.3 Screen 15 Regelwerk** — jede Regel einzeln abschaltbar, mit Herleitung; Overrides persistiert. Erst danach dürfen Regeln im Produkt greifen.

## P4 · Auswertung und Planung
- **P4.1 Screen 06 Simulator** (Fokus-Dunkel, Hilfsmittel-Panel) und **07 Ergebnis**.
- **P4.2 Screen 08 Wissensgraph**, **09 Prüfungsradar** (braucht ≥ 3 Klausuren).
- **P4.3 Screen 10 Tagesplan**, **11 Formelsammlung**, **12 Fehler-DNA.**
- **P4.4 Leerzustände** (README 7.13) — parallel zu jedem Screen, nicht nachgelagert.

## P5 · Abschluss
- **P5.1 Motion-Durchlauf** gegen README 9, inkl. Reduce-Motion-Fallbacks.
- **P5.2 Tastatur- und Fokusreihenfolge**, Screenreader-Labels für Ring, Balken, Heatmap.
- **P5.3 Mobile-Durchlauf** 390×844: Hit-Targets, fixe Fußleisten, Sheet-Verhalten.
- **P5.4 Optional:** zweites und drittes Theme aktivieren (README 5.1).
