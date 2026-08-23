# 04 · Parametrischer Aufgaben-Generator

Aus einer konkreten Aufgabe wird eine Vorlage mit Variablen; aus der Vorlage
werden Varianten, die nachweislich lösbar und sinnvoll sind.

## Warum das das gefährlichste Subsystem ist

Eine falsche Variante ist schlimmer als keine Variante. Der Nutzer rechnet
zwanzig Minuten, bekommt „falsch" gesagt und hat recht gehabt. Das zerstört
Vertrauen schneller als jeder andere Fehler im Produkt — und er merkt es oft
nicht einmal, sondern lernt etwas Falsches.

Deshalb: **keine Variante wird vorgelegt, die nicht alle drei Verifikations-
stufen bestanden hat.** Nicht verifizierte Varianten gehen in Quarantäne
(Invariante I7, I8).

## Von der Aufgabe zur Vorlage

Halbautomatisch. Vollautomatik ist hier eine Illusion.

**Schritt 1 — Kandidaten finden.** Zahlen mit Einheit im Aufgabentext sind
Variablenkandidaten: `R₁ = 100 Ω`, `U = 12 V`. Reine Zählwerte (`drei
Widerstände`) sind es nicht — Strukturzahlen dürfen nicht variieren, sonst
ändert sich die Aufgabe statt ihrer Werte.

**Schritt 2 — Größenart bestimmen.** Aus der Einheit folgt `quantityKind`
(Widerstand, Spannung, Länge, Fläche, Moment). Daran hängen die
Plausibilitätsgrenzen.

**Schritt 3 — Lösungsausdruck gewinnen.** Aus den `SolutionStep`s der
Musterlösung: der letzte Schritt liefert die Ergebnisformel, die vorherigen
die Zwischengrößen. Ohne Musterlösung kann eine Vorlage nur manuell oder per
LLM entstehen — und geht dann zwingend in Quarantäne.

**Schritt 4 — Nutzer bestätigt.** Er sieht Variablen, Bereiche und
Lösungsformel und kann jedes einzeln ändern. Die Vorlage wird erst mit seiner
Freigabe `draft`.

## Wertebereiche

Der 10-MΩ-Kabelwiderstand ist das Standardbeispiel für das, was hier schiefgeht.
Drei Ebenen halten das auf:

**1 · Größenart-Grenzen.** Eine Tabelle pro `quantityKind` mit technisch
üblichem Bereich — nicht physikalisch möglich, sondern *in Klausuren
vorkommend*.

| Größenart | üblicher Bereich | Begründung |
|---|---|---|
| Widerstand (Bauteil) | 1 Ω – 10 MΩ | Reihe E12 |
| Widerstand (Leitung) | 1 mΩ – 10 Ω | Kupfer, realistische Längen |
| Spannung (Kleinsignal) | 1 mV – 50 V | |
| Spannung (Netz) | 100 V – 1 kV | |
| Kapazität | 1 pF – 10 mF | |
| Biegemoment | 1 N·m – 1 MN·m | |

Entscheidend ist der **Kontext**, nicht nur die Einheit: derselbe Ohm-Wert hat
als Bauteil und als Leitungswiderstand verschiedene Bereiche. Der Kontext kommt
aus dem Aufgabentext und wird bei der Vorlagenerstellung festgelegt.

**2 · Ableitung aus dem Original.** Der Originalwert liegt per Definition im
sinnvollen Bereich. Standardbereich ist deshalb `[0.3·x₀, 3·x₀]`, gerastert auf
Normreihenwerte, geschnitten mit der Größenart-Grenze. Das ist konservativ und
richtig, wo die Tabelle zu grob ist.

**3 · Rasterung auf Normwerte.** Widerstände auf E12, Kapazitäten auf E6,
Längen auf glatte Millimeter. Eine Klausuraufgabe mit `R = 47,3194 Ω` ist als
Fälschung erkennbar und stört.

## Constraints

Zwei Sorten, beide als auswertbarer Ausdruck gespeichert:

**Relationen zwischen Variablen** — `R1 < R2`, `L > 2*d`. Nötig, wo die
Aufgabenstellung eine Ordnung voraussetzt (Spannungsteiler, Reihenfolge in
einer Kaskade).

**Plausibilität am Ergebnis** — `0.001 < I < 10`, `sigma < R_e`. Verhindert
Varianten, deren Werte einzeln plausibel sind, deren *Ergebnis* aber Unsinn
ist: ein Strom von 4 kA aus zwei harmlosen Werten.

Die Ziehung ist Rejection Sampling: Werte ziehen, Constraints prüfen,
verwerfen und neu ziehen. Nach `N` Fehlversuchen (Vorschlag: 200) gilt der
Constraint-Satz als **überbestimmt** und die Vorlage wandert in Quarantäne mit
dieser Begründung — statt endlos zu ziehen.

## Verifikation — drei Stufen

Jede Variante durchläuft alle drei. Eine reicht nicht.

### Stufe 1 · Einheitenprüfung

Der Lösungsausdruck wird mit Einheiten ausgewertet (`mathjs` Units). Die
Ergebnis­einheit muss der erwarteten Einheit **dimensional** entsprechen.
`V/A → Ω` besteht; `V·A → Ω` fällt durch. Das fängt den häufigsten Fehler beim
Formelübertrag, und es kostet nichts.

### Stufe 2 · Numerische Probe gegen die Referenz

Die Kernprüfung (siehe ADR-0001). Der Lösungsausdruck der Vorlage wird gegen
die aus der Musterlösung gewonnene Referenzrechnung getestet:

- `N = 64` Stichproben aus dem Variablenraum, Constraints erfüllt
- beide Ausdrücke auswerten
- relative Abweichung `≤ 1e-9` an **allen** Punkten → äquivalent
- Abweichung an einzelnen Punkten → Polstelle oder Definitionslücke vermuten,
  Punkt neu ziehen, höchstens dreimal
- weiterhin instabil → Urteil `unentscheidbar`, **Quarantäne**, nicht `falsch`

Der Unterschied zwischen `falsch` und `unentscheidbar` ist wichtig: Ersteres
ist ein Vorlagenfehler, Letzteres oft eine legitime Funktion mit Polstelle,
deren Bereich zu weit gewählt ist. Die Quarantänemeldung sagt, welches davon.

### Stufe 3 · Plausibilitätsgrenzen am Ergebnis

Das Ergebnis jeder Stichprobe muss innerhalb der Ergebnis-Plausibilitätsgrenzen
liegen. Fällt eine Stichprobe durch, ist nicht die Variante schuld, sondern der
Wertebereich zu weit — die UI schlägt eine Bereichsverengung vor.

## Quarantäne

Ein eigener, sichtbarer Zustand — kein stilles Verwerfen.

`ParametricTemplate.status`:

| Status | Bedeutung | Wird vorgelegt? |
|---|---|---|
| `draft` | erstellt, noch nicht geprüft | nein |
| `quarantined` | mindestens eine Stufe nicht bestanden | **nein** |
| `verified` | alle drei Stufen bestanden | ja |

`verificationReport` hält fest: welche Stufe, welche Stichprobe, welcher Wert,
welche Erwartung. Der Nutzer sieht in einer eigenen Ansicht seine Quarantäne
und kann Bereiche korrigieren und neu prüfen lassen. Nichts verschwindet
kommentarlos.

**Quarantäne ist kein Randfall.** Bei LLM-erzeugten Vorlagen ohne Musterlösung
ist sie der Normalzustand. Die UI muss das aushalten, ohne wie ein Fehler
auszusehen.

## Teststrategie

- **Property-Tests** über den Ziehungsmechanismus: für jede Vorlage im
  Testkorpus gilt bei 1000 Ziehungen, dass alle Constraints erfüllt und alle
  Ergebnisse im Plausibilitätsband liegen.
- **Bekannte Fallen** als Fixtures: Vorlagen mit Polstelle, mit
  überbestimmtem Constraint-Satz, mit dimensional falscher Formel. Jede muss
  in Quarantäne landen — und mit der *richtigen* Begründung.
- **Regression:** eine verifizierte Vorlage darf durch keine Änderung
  unverifiziert werden, ohne dass der Test es meldet.
