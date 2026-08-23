# 03 · Ingest-Pipeline

Aus einer Datei werden Aufgaben. Dies ist das Subsystem mit der höchsten
Absprungwahrscheinlichkeit: eine falsch zerlegte Klausur ist schlimmer als
gar keine, weil der Nutzer den Fehler erst beim Lösen bemerkt.

## Grundsatz

**Jede Stufe schreibt ein persistiertes Artefakt und ist einzeln wiederholbar.**
Kein Schritt hält Zwischenergebnisse nur im Speicher. Wer Stufe 5 neu rechnen
will, braucht Stufe 1–4 nicht erneut.

**Nutzerkorrekturen sind Overrides, keine Ergebnisse.** Sie liegen in einer
eigenen Tabelle und werden bei jedem Durchlauf *über* das Automatikergebnis
gelegt. Ein erneuter Lauf kann eine Korrektur nie überschreiben (Invariante I12).
Das ist die wichtigste Zusage der ganzen Pipeline.

## Die acht Stufen

```
1 Aufnahme      Datei → SourceDocument (sha256, Typ, Seitenzahl, Textlayer ja/nein)
2 Normalisierung  Entzerrung, Rotation, Kontrast → deskewAngle, qualityScore
3 Seitenmodell  Rasterung + Textextraktion → PageArtifact (rasterRef, textLayer)
4 Blockerkennung  Textblöcke mit Bounding Box → Blockliste je Seite
5 Segmentierung  Blöcke → SegmentCandidate (Aufgabengrenzen)
6 Punkte        Regex-Kaskade, dann LLM → proposedPoints je Kandidat
7 Lösungsbezug  Musterlösung ↔ Aufgabe zuordnen
8 Assets        Bildbereiche ausschneiden → TaskAsset
                    ↓
              Review-UI (immer, nie überspringbar)
```

### 1 · Aufnahme

Drei Quellen mit unterschiedlichem Schicksal:

| Quelle | Erkennung | Weg |
|---|---|---|
| PDF mit Textlayer | pdf.js findet Textitems | Stufe 2 übersprungen, direkt zu 3 |
| PDF aus Scan | kein Textlayer, aber Seitenformat sauber | Entzerrung leicht, OCR nötig |
| Handyfoto | Bilddatei, perspektivisch verzerrt | volle Entzerrung, OCR, niedrigste Qualität |

`sha256` verhindert Doppelimporte. Ein zweiter Import derselben Datei bietet an,
den vorhandenen `ExamPaper` zu öffnen, statt ihn zu duplizieren.

### 2 · Normalisierung

Nur für Scan und Foto. Ohne OpenCV (siehe ADR-0001) läuft das über:

- **Kantenerkennung** zur Seitenbegrenzung, Vier-Punkt-Perspektivkorrektur
  über eine Homographie — als reine Matrixrechnung in TS, auf Canvas angewendet.
- **Schräglage** aus der dominanten Textzeilenrichtung; Rotation über Canvas.
- **Kontrastnormalisierung** vor OCR.
- `qualityScore` aus Auflösung, Kontrastspanne und Kantenschärfe. Unter einem
  Schwellwert **warnt die UI vor dem Import**, statt hinterher schlechte
  Ergebnisse zu erklären.

### 3 · Seitenmodell

`PageArtifact` je Seite: Rasterbild und Textlayer mit Positionen.

- **Mit Textlayer:** pdf.js liefert Textitems samt Koordinaten. Kein OCR.
  Das ist der Goldpfad und muss vollständig offline funktionieren.
- **Ohne Textlayer:** `OcrPort` liefert Blöcke, Zeilen, Konfidenz, Bounding Box.
  Drei native Backends (macOS/iOS Vision, Android ML Kit).

Beide Wege münden in **dasselbe Format**. Alle folgenden Stufen wissen nicht,
ob der Text aus einem Textlayer oder aus OCR stammt — nur die Konfidenz
unterscheidet sich.

### 4 · Blockerkennung

Gruppierung der Textitems zu Absätzen und Spalten: vertikale Lücken,
Einrückungstiefe, Schriftgrößenwechsel. Rein geometrisch, kein Modell.

### 5 · Segmentierung — wo es bricht

Drei Strategien, in dieser Reihenfolge:

**a · Heuristik (offline, immer).** Aufgabenköpfe folgen in Klausuren wenigen
Mustern: `Aufgabe 3`, `A3`, `3.`, `3)`, oft fett oder größer, oft nach
Seitenumbruch oder Trennlinie. Kombiniert mit dem Punktemuster aus Stufe 6
ergibt das eine belastbare erste Zerlegung.

**b · LLM (Opt-in).** Bekommt den Textlayer *einer Seite* plus die
Heuristik-Kandidaten und wird gefragt, ob Grenzen fehlen oder falsch liegen.
Es bekommt **kein Bild**, solange Bildanalyse nicht ausdrücklich aktiviert ist.
Sein Ergebnis ist ein Vorschlag mit Konfidenz — nie eine Festlegung.

**c · Manuell (immer verfügbar).** Der Nutzer zieht Grenzen selbst. M1 liefert
genau das und muss ohne a und b Wert haben.

Jeder Kandidat trägt `confidence`. Unter 0.7 wird er in der Review-UI
**markiert**, nicht verworfen.

### 6 · Punkte-Extraktion

Regex-Kaskade **vor** jedem Modell — billig, deterministisch, gut testbar:

```
(4 P.)   (4 Punkte)   [4]   /4   4 P   (4P)   – 4 Punkte –
4 BE     (4 Pkt.)     max. 4 Punkte
```

Dezimaltrennzeichen ist das Komma (`8,5 P`). Die Kaskade läuft je Kandidat
zuerst am Kopf, dann am Fuß, dann irgendwo im Block.

**Kreuzprobe:** Ergibt `Σ Aufgabenpunkte` nicht die Gesamtpunktzahl der Klausur,
markiert die UI die Differenz und zeigt, welche Aufgaben unsicher sind. Das
findet Segmentierungsfehler zuverlässiger als jede Konfidenzzahl — deshalb ist
Invariante I2 nicht nur Datenhygiene, sondern ein Diagnosewerkzeug.

### 7 · Lösungsbezug

Liegt die Musterlösung als eigenes Dokument vor, wird zugeordnet über:
Aufgabennummern-Übereinstimmung, dann Reihenfolge, dann Textähnlichkeit der
Formelzeichen. Bei Unklarheit **fragt die UI**, statt zu raten — eine falsch
zugeordnete Musterlösung erzeugt lauter Falschbewertungen und untergräbt das
Vertrauen dauerhaft.

Die Zerlegung der Musterlösung in `SolutionStep` läuft über Zeilenstruktur und
Gleichheitszeichen; jeder Schritt bekommt Formeltext, Zwischenwert und Einheit.
Das ist die Voraussetzung für Rechenweg-Diff und Folgefehler-Erkennung.

### 8 · Assets

Bildbereiche — Schaltbilder, Diagramme, Tabellen — werden als Ausschnitt aus dem
Seitenraster gespeichert, nicht neu gezeichnet. Erkennung über Flächen ohne
Textitems oberhalb einer Mindestgröße. Jedes Asset wird im Review sichtbar der
Aufgabe zugeordnet und ist dort verschiebbar.

## Die Korrektur-UI

Dies ist kein Nachgedanke, sondern das Produkt.

**Ansicht:** links die Seite mit eingezeichneten Grenzen, rechts die entstehende
Kartenliste. Beide gekoppelt — Auswahl links markiert rechts und umgekehrt.

**Sechs Operationen**, alle mit Tastaturkürzel:

| Operation | Wirkung |
|---|---|
| Übernehmen | Kandidat wird Aufgabe |
| Anpassen | Grenze ziehen, Punkte oder Nummer ändern |
| Teilen | ein Kandidat wird zwei Aufgaben |
| Verbinden | zwei Kandidaten werden eine |
| Verwerfen | kein Aufgabeninhalt (Deckblatt, Hinweisseite) |
| Anlegen | Bereich markieren, den die Automatik übersehen hat |

**Was die UI zeigt, ohne dass man danach sucht:**
- Punktesumme gegen Klausursumme, mit farbiger Differenz
- Anzahl Kandidaten unter Konfidenzschwelle
- Seiten ohne jeden Kandidaten
- Aufgaben ohne zugeordnete Musterlösung

**Fortschritt ist erhaltbar.** Der Review kann abgebrochen und später
fortgesetzt werden; der `ExamPaper` bleibt bis zur Freigabe im Zustand
`draft` und taucht nicht im Atlas auf.

## Wenn die Segmentierung falsch liegt

Die vier realistischen Fehlerbilder und ihre Antwort:

| Fehlerbild | Erkennung | Antwort |
|---|---|---|
| Zwei Aufgaben als eine | Punktesumme zu klein, Block auffällig lang | „Teilen" mit Vorschlagsgrenze am erkannten zweiten Kopf |
| Eine Aufgabe als zwei | Punktesumme zu groß, zweiter Teil ohne Punkteangabe | „Verbinden", Kandidaten benachbart markiert |
| Aufgabe übersehen | Lücke in der Nummernfolge | Seitenbereich hervorgehoben, „Anlegen" vorgeschlagen |
| Deckblatt als Aufgabe | keine Punkte, keine Nummer | vorab als `reject` vorgeschlagen |

**Wiederholbarkeit:** Der Nutzer kann jederzeit „Auto-Segmentierung erneut
laufen lassen" — mit anderer Strategie, etwa erst heuristisch, dann mit LLM.
Seine bisherigen Korrekturen bleiben. Die UI zeigt vor dem Lauf an, wie viele
Overrides bestehen und dass sie erhalten bleiben.

## Teststrategie

**Golden-File-Tests** sind hier die einzige aussagekräftige Methode. Ein Korpus
echter Klausuren (mindestens je fünf: Textlayer-PDF, sauberer Scan, Foto) mit
handgeprüfter Soll-Zerlegung. Gemessen wird pro Stufe:

- Segmentierung: Präzision und Trefferquote der Aufgabengrenzen
- Punkte: Anteil korrekt extrahierter Punktzahlen
- Lösungsbezug: Anteil korrekter Zuordnungen

Regression heißt: eine Änderung darf keine dieser Zahlen senken. Der Korpus
liegt außerhalb des Repos (Urheberrecht, siehe `00`), die erwarteten Ergebnisse
liegen als JSON darin.
