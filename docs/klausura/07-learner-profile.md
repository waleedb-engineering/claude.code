# 07 · Lernprofil — zusammengeführtes Modell

Kein Klassifikator, keine Typologie. Additive Punktvergabe auf Achsen, jede
Achse mit nachlesbarer Herleitung und einzeln abschaltbaren Regeln.

## Die Zusammenführung

Das Design-Handoff fixiert **6 Achsen** mit vollständiger Beitragsmatrix,
Bändern, Hysterese und 10 Regeln — gerendert in Screen 14 und 15. Der
Planungsauftrag nennt **9 Dimensionen**, die teils dieselben sind, teils fehlen.

**Regel der Zusammenführung: die 6 Handoff-Achsen bleiben arithmetisch
unangetastet.** Die 12 Onboarding-Fragen bleiben 12. Die Beitragsmatrix bleibt
Zeile für Zeile bestehen. Das Beispielprofil muss weiterhin exakt
`82 / 54 / 28 / 60 / 71 / 34` ergeben — bricht die Zusammenführung diese Zahlen,
ist die Zusammenführung falsch.

### Abbildung der 9 Block-D-Dimensionen

| Block-D-Dimension | Wird zu |
|---|---|
| Prüfungsangst | Achse 1 — identisch |
| Tempo vs. Gründlichkeit | Achse 2 `Rechenweg-Sorgfalt` |
| — (Druckverhalten) | Achse 3 `Zeitdruck-Toleranz` |
| Tage bis Klausur · Zeit/Woche | Achse 4 `Vorbereitungszeit` (Fragen 03 + 04) |
| — (Hilfsmittel) | Achse 5 `Formelsammlung-Routine` |
| — (Selbstbild) | Achse 6 `Selbsteinschätzung` |
| **Vorwissen** | **Achse 7 — neu, rein gemessen** |
| **Darstellungspräferenz** | **Achse 8 — neu, Saat aus Frage 09** |
| **Feedback-Härte** | **Achse 9 — neu, Saat aus Achse 1 + 6** |
| **Arbeitsrhythmus** | **Achse 10 — neu, Saat aus Frage 04** |
| Motivationsstil | *keine eigene Achse* — siehe unten |

**Motivationsstil wird bewusst nicht zur Achse.** Frage 11 bleibt und beeinflusst
Achse 1 und 6 wie im Handoff, aber „Wettbewerb / Fortschritt / Ruhe" als eigene
Steuergröße würde genau das Gamification-Vokabular zurückholen, das Regel 6
ausschließt. Wer Vergleich will, bekommt ihn über die bestehende Regel
`Zeitdruck-Toleranz ≥ 66 → Kohorten-Perzentile`.

### Keine neuen Onboarding-Fragen

Die vier neuen Achsen bekommen **keine** zusätzlichen Fragen. Gründe:

- Screen 01 zeigt `FRAGE 04 VON 12`; die Fortschrittsskala hat 12 Teilstriche.
- „Wie gut ist dein Vorwissen?" misst Selbstbild, nicht Vorwissen — und das
  Handoff misstraut Selbstauskunft aus gutem Grund (Achse 6 existiert genau
  deswegen).
- Arbeitsrhythmus aus Zeitstempeln ist besser als aus einer Erinnerung.

Die neuen Achsen starten bei ihrer Saat und werden **durch Verhalten** bestimmt.

## Der gemessene Zwilling

Der eigentliche Zugewinn gegenüber dem Handoff: „Verhalten schlägt
Selbstauskunft" — als Arithmetik, nicht als Absichtserklärung.

### Formel

```
value = clamp(0, 50 + Σ Umfragebeiträge + Σ Verhaltensbeiträge, 100)
```

Der Verhaltensbeitrag ist ein **signierter Term wie jeder andere**. Damit bleibt
Invariante I14 unverändert gültig und Screen 14 rendert ihn als zusätzliche
Zeile in der Herleitung — mit eigener Kennzeichnung.

### Regeln für den Verhaltensterm

| Regel | Wert |
|---|---|
| Startwert | `0` — bei Abschluss des Onboardings trägt Verhalten nichts bei |
| Mindest-Stichprobe | Achsenspezifisch, nie unter 5 Beobachtungen |
| Betragsgrenze | `±20` — Verhalten kann ein Band kippen, nie die Achse übernehmen |
| Anpassung | gleitend, höchstens `±2` pro Tag — kein Sprung nach einer schlechten Sitzung |
| Bandwechsel | dieselbe 5-Punkte-Hysterese wie bei Umfragebeiträgen |
| Herkunft | `provenance` wird `measured`, sobald der Term ≠ 0 ist |

Weil der Startwert 0 ist, ergibt das Beispielprofil unmittelbar nach dem
Onboarding **exakt** `82 / 54 / 28 / 60 / 71 / 34`. Das ist Abnahmekriterium.

### Was je Achse gemessen wird

| Achse | Beobachtung | Richtung |
|---|---|---|
| 1 Prüfungsangst | Abgaben in den letzten 10 % des Budgets; Abbrüche im Simulator; `E-BLANK`-Rate | häufig → höher |
| 2 Rechenweg-Sorgfalt | Zeilen im Rechenweg je Punkt; Anteil Aufgaben mit dokumentiertem Weg | mehr → höher |
| 3 Zeitdruck-Toleranz | Punktequote im Simulator ÷ Punktequote im Übungsmodus | Verhältnis ≥ 1 → höher |
| 4 Vorbereitungszeit | tatsächliche Lernminuten pro Woche gegen geplante | mehr → höher |
| 5 Formelsammlung-Routine | Nachschlagezeit je Aufgabe; Trefferquote beim ersten Nachschlagen | schneller → höher |
| 6 Selbsteinschätzung | Selbstprognose vor Abgabe gegen tatsächliche Punkte | überschätzt → höher |
| 7 Vorwissen | mittlere Beherrschung über bewertete Themen | direkt |
| 8 Darstellungspräferenz | Nutzung von Skizzenfläche, Herleitungs-Aufklappen, Beispiel-zuerst | direkt |
| 9 Feedback-Härte | Verweildauer in der Diff-Ansicht; Anteil weggeklickter Rückmeldungen | länger → verträgt mehr |
| 10 Arbeitsrhythmus | Tageszeit und Länge der Sitzungen | Blockdauer, Tageslage |

Achse 7 hat **keinen** Umfrageanteil: `50 + 0 + Verhalten`. Vor der ersten
Bewertung steht sie neutral bei 50 und löst keine Regel aus.

## Achsen, Bänder und Regeln

Achsen 1–6 mit Bändern und den 10 Regeln unverändert nach
`design_handoff_klausura/README.md` Abschnitt 8.1 und 8.4. Hier nur die vier
neuen Achsen.

| Achse | Skalenenden | Bänder |
|---|---|---|
| 7 Vorwissen | LÜCKENHAFT → GEFESTIGT | ≤ 40 lückenhaft · ≤ 70 gemischt · ≤ 100 gefestigt |
| 8 Darstellungspräferenz | ERGEBNIS-ZUERST → WEG-ZUERST | ≤ 40 Ergebnis · ≤ 65 gemischt · ≤ 100 Weg |
| 9 Feedback-Härte | SCHONEND → DIREKT | ≤ 40 schonend · ≤ 70 sachlich · ≤ 100 direkt |
| 10 Arbeitsrhythmus | KURZ & OFT → LANG & SELTEN | ≤ 40 kurz · ≤ 70 gemischt · ≤ 100 lang |

### Neue Regeln (11–16)

Ergänzen die 10 bestehenden. Jede einzeln abschaltbar, jede mit Herleitung,
alle in Screen 15 sichtbar.

| # | Achse | Schwelle | Bereich | Verhalten im UI |
|---|---|---|---|---|
| 11 | Vorwissen | ≤ 40 | START | Wissensgraph ist Startscreen statt Atlas |
| 12 | Vorwissen | ≥ 71 | SIMULATION | Simulator ohne Aufwärmaufgabe freigegeben |
| 13 | Darstellungspräferenz | ≥ 66 | HERLEITUNG | Herleitung standardmäßig aufgeklappt, Ergebnis eingeklappt |
| 14 | Feedback-Härte | ≤ 40 | FEEDBACK | Rückmeldung nennt zuerst das Richtige, dann die Abweichung |
| 15 | Feedback-Härte | ≥ 71 | FEEDBACK | Punktverlust und Fehlercode direkt im Kopfband, ohne Zwischenschritt |
| 16 | Arbeitsrhythmus | ≤ 40 | PLAN | Tagesplan in 25-Minuten-Blöcken statt Zweistundenblöcken |

Regel 14 und 15 stehen bewusst gegen die Handoff-Regel „Ort vor Wertung"
(Prüfungsangst ≥ 71). **Konfliktauflösung: Prüfungsangst gewinnt.** Bei
gleichzeitigem Greifen wird Regel 15 unterdrückt und in Screen 15 als
`ÜBERSTIMMT` markiert — mit Nennung der Regel, die sie überstimmt. Regeln
dürfen nie stillschweigend wirkungslos sein.

## Änderbarkeit und Umkehrbarkeit

- **Jede Antwort ist in Screen 14 änderbar.** Achsen, Bänder und Regeln rechnen
  live neu; gekippte und von der Hysterese gehaltene Regeln werden markiert.
- **Jede Regel ist in Screen 15 einzeln abschaltbar**, mit Herleitung
  („weil Prüfungsangst 82, Schwelle ≥ 71").
- **Der Verhaltensterm ist zurücksetzbar.** Eine Aktion „Verhaltensanteil
  zurücksetzen" setzt ihn auf 0 und lässt die Umfrageantworten stehen. Nötig
  nach einer Krankheitswoche oder einem Fachwechsel.
- **Abschalten ändert das Profil nicht** (Invariante I15). Achsenwert und
  Herleitung bleiben, nur das Verhalten entfällt.

## Teststrategie

- **Reproduktionstest (verpflichtend):** die 12 Beispielantworten des Handoffs
  ergeben `82 / 54 / 28 / 60 / 71 / 34` und die Bänder
  `hoch / mittel / niedrig / ausreichend / gut / zu streng`. Schlägt dieser
  Test fehl, ist die Zusammenführung zurückzunehmen.
- **Hysterese:** eine Antwortänderung, die den Achsenwert um 3 Punkte über eine
  Bandgrenze schiebt, ändert das Band **nicht**; um 6 Punkte schon.
- **Verhaltensdeckel:** synthetischer Verlauf mit extremem Verhalten über
  90 Tage verschiebt keine Achse um mehr als 20 Punkte.
- **Startneutralität:** direkt nach dem Onboarding ist jeder Verhaltensterm 0
  und jede `provenance` gleich `surveyed`.
- **Regelkonflikt:** greifen Regel 14 und 15 gleichzeitig, ist genau eine aktiv
  und die andere als `ÜBERSTIMMT` gekennzeichnet.
