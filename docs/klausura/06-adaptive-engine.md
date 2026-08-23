# 06 · Adaptive Lern-Engine

Was als nächstes zu tun ist, und wie es um das Bestehen steht.

## FSRS auf Aufgabentyp-Ebene — mit ehrlicher Einschränkung

**Was FSRS ist:** ein Scheduler, der Stabilität und Schwierigkeit eines
Gedächtnisinhalts schätzt und daraus den nächsten Wiederholungstermin ableitet.
Kalibriert wurde er auf **binäre Recall-Bewertungen von Karteikarten**, über
hunderte Millionen Reviews.

**Was hier davon abweicht:** Eine Klausuraufgabe ist keine Karteikarte. Sie
dauert zwanzig Minuten statt vier Sekunden, sie hat Teilpunkte statt
richtig/falsch, und der Nutzer löst sie zwei- bis dreimal, nicht dreißigmal.

**Konsequenz — das ist eine Anpassung, keine Übernahme.** Wir bauen einen
FSRS-*inspirierten* Scheduler. Die Parameter sind für diesen Anwendungsfall
**unvalidiert**, und das gehört dokumentiert, nicht kaschiert.

### Die Abbildung Punktequote → Rating

Der eigentliche Erfindungsakt. FSRS erwartet `again | hard | good | easy`:

| Bedingung | Rating |
|---|---|
| Quote < 0,4 **oder** `E-ANS` vergeben | `again` |
| 0,4 ≤ Quote < 0,7 | `hard` |
| Quote ≥ 0,7, Zeit über Budget | `hard` |
| Quote ≥ 0,7, Zeit im Budget | `good` |
| Quote ≥ 0,95, Zeit unter 70 % des Budgets | `easy` |

Ein Ansatzfehler wirft immer auf `again` zurück, unabhängig von der Punktzahl:
wer den falschen Ansatz wählt und zufällig nah am Ergebnis landet, hat nichts
gekonnt.

**Zeit geht in das Rating ein** — anders als bei Karteikarten, wo sie nur
Nebensignal ist. In einer Klausur ist zu langsam faktisch ungelöst.

### Einheit der Planung

Nicht die einzelne Aufgabe (die wird nach zweimal Lösen auswendig gekonnt),
sondern der **Aufgabentyp**: `(Topic, TaskType)`. Eine Wiederholung bedeutet
dann: eine *andere* Aufgabe desselben Typs, bevorzugt eine verifizierte
parametrische Variante.

Damit ist der Generator aus `04` keine Spielerei, sondern die Voraussetzung
dafür, dass der Scheduler überhaupt Material hat.

## Auswahl: was als nächstes

Drei Filter, in dieser Reihenfolge:

**1 · Voraussetzungen (harter Filter).** Ein Thema, dessen Voraussetzungen
unter 50 % Beherrschung liegen, wird nicht vorgelegt. Der Wissensgraph ist
ein DAG (Invariante I6); die Prüfung ist eine Tiefensuche über eingehende
Kanten. Ohne das übt der Nutzer Wechselstromleistung, während ihm die
komplexe Rechnung fehlt — und lernt nichts.

**2 · Fälligkeit (FSRS).** Unter den zulässigen Typen zuerst die überfälligen,
nach Überfälligkeit absteigend.

**3 · Profilgewichtung.** Das Handoff-Preset entscheidet die Sortierung
innerhalb gleicher Dringlichkeit:

| Preset | Sortierschlüssel |
|---|---|
| Lückenschließer | blockierte Klausurpunkte absteigend |
| Zeitoptimierer | Sekunden pro Punkt absteigend |
| Letzte 72 Stunden | nur Themen ≥ 50 % Beherrschung, rote ausgeblendet |
| Hohe Prüfungsangst | Aufwärmaufgabe vor jedem Simulationslauf |

„Blockierte Klausurpunkte" ist die nützlichste Kennzahl im ganzen System:
wie viele Punkte in echten Altklausuren hängen an einem Thema, das noch nicht
sitzt. Sie kommt aus dem Prüfungsradar (Screen 09) und beantwortet „was bringt
mir am meisten" mit Daten statt Gefühl.

## Zeitbudget-Kalibrierung

Das Zeitbudget der Klausur (`Punkte × Sekunden/Punkt`) ist der Sollwert. Der
Nutzer hat einen eigenen Faktor.

**Verfahren:** je `(Topic, TaskType)` der Median aus `elapsedSeconds /
timeBudgetSeconds` der letzten fünf Versuche. Median, nicht Mittel — ein
einzelner Abbruch soll den Faktor nicht kippen.

- Faktor > 1: der Nutzer ist langsamer als das Budget. Angezeigt wird das als
  **Zeitbedarf**, nicht als Defizit.
- Erst ab drei Versuchen wird der Faktor überhaupt benutzt.
- Er fließt in die Bestehensprognose und in die Tagesplanung ein, **nicht** in
  den Timer: der Timer zeigt immer das echte Klausurbudget. Die Prüfung
  verlängert sich nicht, weil man langsam ist.

## Bestehensprognose

### Das Modell

Erwartete Gesamtpunktzahl als Summe über die Aufgaben einer typischen Klausur:

```
E[Punkte] = Σ_Aufgaben  maxPoints(a) · p̂(Typ(a)) · t̂(Typ(a))

p̂  erwartete Punktequote des Typs, aus den letzten Versuchen
t̂  Zeitfaktor-Malus: Anteil, der bei Zeitüberschreitung wegfällt
```

`p̂` ist ein Beta-Posterior aus erreichten und möglichen Punkten je Typ, mit
schwachem Prior. Das liefert nicht nur einen Wert, sondern eine **Verteilung** —
und damit die Unsicherheit direkt mit.

### Wie die Unsicherheit dargestellt wird

Nie eine Zahl allein. Immer ein Intervall, und immer der Abstand zur
Bestehensgrenze:

> `39,5 – 52,0 von 90 P · Bestehensgrenze 45 · Datenbasis: 23 Versuche in 8 von 14 Themen`

### Die drei Ehrlichkeitsregeln

**1 · Unter der Datenschwelle: keine Aussage.** Weniger als drei absolvierte
Klausuren oder unter 40 % der Themen mit mindestens einem Versuch → die
Prognose zeigt nichts außer der Bedingung, unter der sie erscheint. Das ist
die Leerzustand-Logik aus dem Handoff, angewandt auf ein Modell.

**2 · Systematisch konservativ.** Berichtet wird das **untere** Ende des
80-%-Intervalls als Leitwert. Eine Prognose, die zu optimistisch ist, kostet
den Nutzer die Klausur; eine zu pessimistische kostet ihn einen Abend mehr
Lernen. Die Asymmetrie ist real und wird eingebaut, nicht wegdiskutiert.

**3 · Ungeprüfte Themen zählen als nicht gekonnt, nicht als Durchschnitt.**
Wer neun von vierzehn Themen nie geübt hat, bekommt keine Prognose, die so
tut, als liefen die fünf ungeübten wie die geübten. Sie gehen mit `p̂ = 0`
ein, und die Anzeige nennt die Zahl der ungeprüften Themen.

### Was das Modell nicht kann

- Es kennt die kommende Klausur nicht. Es extrapoliert von Altklausuren.
- Es kennt die Tagesform nicht.
- Bei Prüferwechsel ist die Grundlage hinfällig — das steht als Hinweis an
  der Anzeige, wenn die Altklausuren von einem anderen Prüfer stammen.
- Es sagt nichts über die Note. Standardaussage ist der Bestehensabstand.

## Teststrategie

- **Scheduler:** Simulation über synthetische Lernverläufe (100 Nutzer, 60 Tage).
  Geprüft wird, dass Intervalle wachsen, wenn Ratings gut sind, und
  zusammenbrechen, wenn sie schlecht sind.
- **Voraussetzungsfilter:** Property-Test, dass nie ein Thema vorgelegt wird,
  dessen Voraussetzung unter Schwelle liegt.
- **Prognose:** Kalibrierungstest auf synthetischen Daten — bei bekanntem
  wahrem `p` muss das 80-%-Intervall in ~80 % der Läufe den wahren Wert
  enthalten. Fällt das durch, ist der Prior falsch.
- **Datenschwelle:** Test, dass unter der Schwelle *keine* Zahl gerendert wird.
