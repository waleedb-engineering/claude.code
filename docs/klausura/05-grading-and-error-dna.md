# 05 · Bewertungs- und Fehler-Engine

Bewertet wird der Rechenweg, nicht nur das Ergebnis. Ein Folgefehler kostet
einen Punkt, nicht die Aufgabe.

## Der Einheiten-Widerspruch — aufgelöst

Zwei Vorgaben stehen sich scheinbar entgegen:

- `CLAUDE.md` Regel 8: *„Einheiten werden nie stillschweigend umgerechnet.
  kΩ und Ω sind getrennte Eingaben."*
- Bewertungsauftrag: *„12 kΩ == 12000 Ω"*

**Auflösung: Die Eingabe rechnet nie um. Die Bewertung darf es — und
protokolliert dabei, dass sie es getan hat.**

| Schicht | Verhalten |
|---|---|
| Einheiten-Input | `kΩ` und `Ω` sind getrennte Felder. Kein Autokorrigieren, kein Normalisieren beim Tippen. Tab wechselt die Einheit ausdrücklich. |
| Bewertung | `12 kΩ` und `12000 Ω` gelten beide als richtig. |
| Fehler-DNA | Weicht die *Größenordnung* der Eingabe vom erwarteten Präfix ab, obwohl der Zahlenwert dimensional stimmt, wird `E-POT` vergeben — auch wenn volle Punkte fließen. |

Der letzte Punkt ist der entscheidende. Ohne ihn verschluckt die tolerante
Bewertung genau die Fehlerklasse, die das Beispielprofil des Handoffs als
häufigste ausweist (Frage 07: „Einheiten, Zehnerpotenzen"). Punkte und
Diagnose sind zwei verschiedene Dinge.

## Numerische Bewertung

**Toleranz** relativ, nicht absolut: `|x_ist − x_soll| / |x_soll| ≤ τ`.
Voreinstellung `τ = 0.01` (1 %), pro Aufgabe überschreibbar. Absolute Toleranz
nur bei Sollwert nahe null.

**Signifikante Stellen** werden nicht erzwungen. Ein Ergebnis von `12,0 kΩ`
statt `12 kΩ` ist richtig. Rundungsdisziplin ist eine eigene Rückmeldung, kein
Punktabzug.

**Einheitenprüfung** dimensional über `mathjs`: `V/A` besteht gegen `Ω`.
Fehlt die Einheit ganz, gibt es Teilpunkte und `E-UNIT`.

**Vorzeichen** werden geprüft. Ein Vorzeichenfehler ist `E-SIGN` und kostet
typischerweise nicht die volle Aufgabe — bei Statik ist er allerdings
fachlich schwerer, was über `severity` pro Fach gesteuert wird.

## Symbolische Äquivalenz

Für Herleitungen, bei denen die Formel bewertet wird, nicht die Zahl.

Verfahren wie in ADR-0001: **numerische Probe.** Beide Ausdrücke werden an 64
zufälligen Punkten des gültigen Bereichs ausgewertet; Übereinstimmung überall
innerhalb `1e-9` bedeutet äquivalent. Das erkennt `R₁R₂/(R₁+R₂)` und
`1/(1/R₁+1/R₂)` als dasselbe, woran jeder Term-Vergleich scheitert.

Drei Urteile, nicht zwei: `equal`, `deviating`, `undecidable`. Bei
`undecidable` bekommt der Nutzer keine Bewertung, sondern den Hinweis, dass
der Vergleich nicht entscheidbar war — und die Zeile geht optional an die
LLM-Rubrik. Ein System, das im Zweifel „falsch" sagt, ist schlimmer als eines,
das „weiß ich nicht" sagt.

## Folgefehler-Erkennung

Der wichtigste Mechanismus für gerechte Teilpunkte.

**Verfahren:** Weicht `AttemptStep` *k* vom zugehörigen `SolutionStep` ab, wird
die Musterlösung ab *k+1* **mit dem falschen Wert des Studenten** nachgerechnet.
Stimmen die Folgeschritte damit überein, sind sie methodisch richtig.

```
Schritt 2:  I = U/R = 12V/100Ω = 0,12 A     ✗ Soll: 1200 Ω → 0,01 A
Schritt 3:  P = U·I = 12V · 0,12A = 1,44 W  ✓ korrekt gerechnet mit 0,12 A
            → Schritt 3 bekommt volle Punkte, Fehler nur bei Schritt 2
```

**Grenzen, ehrlich benannt:**
- Funktioniert nur bei vorhandener, in Schritte zerlegter Musterlösung.
- Bei mehreren Abweichungen wird ab der *ersten* propagiert; spätere
  unabhängige Fehler werden dadurch schwerer zuzuordnen.
- Wenn der Student einen anderen Lösungsweg wählt, greift die Zuordnung
  Schritt↔Schritt nicht. Dann fällt die Bewertung auf Ergebnis plus
  LLM-Rubrik zurück, und das wird dem Nutzer gesagt.

**Zuordnung Schritt↔Schritt** über: gesuchte Größe (linke Seite der Gleichung),
dann verwendete Formel, dann Reihenfolge. Unzuordenbare Zeilen bekommen
`verdict = unmatched` und kosten keine Punkte — Schmierzeilen sind kein Fehler.

## Freitext und Herleitungen

Nur wo Numerik nicht greift: Begründungen, Verfahrensbeschreibungen,
Diskussionen.

**LLM-Rubrik**, nicht Freitextnote. Die Rubrik kommt aus den `SolutionStep`s:
je Schritt ein Kriterium mit Punktwert. Das Modell bekommt Rubrik und Antwort
und gibt **je Kriterium** erfüllt/teilweise/nicht plus Begründung zurück —
keine Gesamtnote.

Absicherung:
- Punktsumme wird lokal gerechnet, nicht vom Modell übernommen.
- Das Ergebnis ist als LLM-bewertet gekennzeichnet und vom Nutzer korrigierbar.
- Ohne KI-Opt-in bleibt die Aufgabe unbewertet und wird als solche gezeigt —
  nicht als „0 Punkte".

## Die Fehler-DNA-Taxonomie

**Abgeschlossen.** Neue Codes sind eine Schemaänderung, keine Laufzeitfreiheit
(Invariante I9).

| Code | Klasse | Beispiel | Typische Ursache |
|---|---|---|---|
| `E-ANS` | Ansatz fehlt oder falsch | Maschensatz statt Knotensatz | Verständnislücke |
| `E-UNIT` | Einheit falsch oder fehlend | Ergebnis in `V` statt `A` | Flüchtigkeit / Verständnis |
| `E-POT` | Zehnerpotenz, Präfix | `12 Ω` statt `12 kΩ` | Umrechnung im Kopf |
| `E-SIGN` | Vorzeichen | Zählpfeilrichtung, Statik-Konvention | Konvention |
| `E-ALG` | Umformungsfehler | falsch aufgelöst | Algebra unter Druck |
| `E-NUM` | Rechenfehler | Tippfehler im Taschenrechner | Druck |
| `E-TRANS` | Übertragungsfehler | Wert falsch abgeschrieben | Flüchtigkeit |
| `E-ROUND` | Rundung zu früh | Zwischenwert gerundet, Ergebnis wandert | Methodik |
| `E-FOLLOW` | Folgefehler | korrekt mit falschem Vorwert | keine eigene Ursache |
| `E-TIME` | Zeit nicht gereicht | Aufgabe abgebrochen | Zeitmanagement |
| `E-BLANK` | Nicht bearbeitet | leer abgegeben | Priorisierung / Blockade |

Elf Codes. Mehr wären nicht mehr auswertbar, weniger nicht mehr diagnostisch.

### Zuweisung — Regel vor Modell

Die Reihenfolge ist entscheidend für Reproduzierbarkeit:

1. **Deterministische Regeln zuerst.** Dimensionsvergleich → `E-UNIT`.
   Verhältnis ist Zehnerpotenz → `E-POT`. Nur Vorzeichen unterscheidet sich
   → `E-SIGN`. Kein Eintrag → `E-BLANK`. Timer überzogen und unvollständig
   → `E-TIME`. Folgefehler-Prüfung bestanden → `E-FOLLOW`.
2. **LLM nur für den Rest**, und nur mit Opt-in. Es darf ausschließlich aus
   der obigen Liste wählen und muss die Zeile benennen, auf die es sich
   bezieht.
3. **Nutzer korrigiert.** Jede Zuweisung ist änderbar; `assignedBy` hält fest,
   woher sie kam. Nutzerkorrekturen sind Trainingsmaterial für die Regeln,
   nicht für ein Modell.

**Ein Fehler, ein Code.** Mehrfachzuweisung je Schritt ist ausgeschlossen —
sonst wird der 8-Wochen-Streifen in Screen 12 unlesbar. Bei Konkurrenz gewinnt
der spezifischere Code (`E-POT` vor `E-NUM`, `E-FOLLOW` vor allem anderen).

## Feedback-Reihenfolge

Aus dem Handoff, Regel 6: **Ort vor Wertung.** Bei hoher Prüfungsangst
(Achse ≥ 71) lautet die Rückmeldung zuerst „Abweichung in Schritt 2", dann
erst „6,5 von 8,5 Punkten". Bei niedriger Angst darf die Punktzahl zuerst
kommen. Das ist eine `ProfileRule`, keine feste Reihenfolge im Code.

## Teststrategie

- **Unit-Tests** je Regel der Taxonomie mit konstruierten Fällen — jeder Code
  braucht mindestens einen positiven und einen Abgrenzungsfall.
- **Der Einheiten-Testfall** ist verpflichtend: `12 kΩ` gegen Soll `12000 Ω`
  muss volle Punkte **und** keinen `E-POT` geben; `12 Ω` gegen `12 kΩ` muss
  Punktabzug **und** `E-POT` geben.
- **Folgefehler-Tests** mit dreistufigen Ketten: Fehler in Schritt 1, 2 und 3,
  jeweils geprüft, dass genau ein `E-*` und die übrigen `E-FOLLOW` entstehen.
- **Golden-File** über echte gelöste Aufgaben mit handvergebenen Punkten;
  Abweichung der Engine von der Handbewertung ist die Kennzahl.
