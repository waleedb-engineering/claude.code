# 09 · Roadmap

Neun Milestones. Jeder mit Definition of Done, demonstrierbarem Ergebnis,
Hauptrisiko und Ausweichplan.

**Grundregel:** Nach jedem Milestone ist die App benutzbar. Kein Milestone
hinterlässt einen Zustand, in dem etwas begonnen und unbrauchbar ist.

---

## M0 · Skeleton, Tokens, Navigation

**Inhalt** Monorepo nach ADR-0001. `core` mit Lint-Regel gegen IO-Importe.
Ports als Interfaces mit In-Memory-Attrappen. Token-System aus dem Handoff
(Farbrollen, Typo, Spacing, Radius, eine Elevation) als plattformneutrale
Tabelle, aus der beide UIs generieren. Navigation und leere Screens.
Migrationsmechanik mit Snapshot und `schema_version`.

**DoD** Beide Apps starten und navigieren. `pnpm test` läuft im Kern grün.
Eine Migration ist angelegt und wieder zurückrollbar. Kein Hex-Wert außerhalb
von `ui-tokens`.

**Demo** macOS und Simulator starten, durch leere Screens navigieren,
Fokus-Dunkel umschalten.

**Risiko** Zwei Build-Ketten gleichzeitig aufzusetzen frisst mehr Zeit als
geplant. **Ausweich** Mobile-Shell auf „startet und zeigt einen Screen"
reduzieren, Ausbau nach M2.

---

## M1 · Import, manuelle Segmentierung, Solve-View-Grundform — ohne KI

**Der wichtigste Milestone.** Er muss allein Wert liefern, auch wenn M3 nie kommt.

**Inhalt** Datei aufnehmen, `sha256`, Seitenmodell über pdf.js. Review-UI mit
allen sechs Operationen (Übernehmen, Anpassen, Teilen, Verbinden, Verwerfen,
Anlegen). Override-Persistenz. Punkte-Regex-Kaskade. Kreuzprobe der
Punktesumme. Atlas mit den entstandenen Karten.

Dazu die **Solve-View in Grundform** (aus M2 vorgezogen, s. u.): Aufgabe
anzeigen, Zeitbudget aus Punkten ableiten, Timer laufen lassen, Antwort als
Wert + Einheit erfassen, Versuch speichern.

**Umfang je Plattform.** Die Segmentierung — Rahmen ziehen — ist
**Desktop-only**. Rahmen pixelgenau auf 390 px zu ziehen ist schlechte
Bedienung und bräuchte ein eigenes Touch-Interaktionsmodell (Lupe,
Griffpunkte, Zoom); das ist ein eigener Milestone, kein Nebenprodukt.
Mobile bekommt in M1 Atlas und Solve-View.

**DoD** Eine echte Altklausur wird in unter 10 Minuten vollständig manuell
zerlegt. Punktesumme stimmt gegen die Klausursumme. Drei markierte Aufgaben
lassen sich unter Zeitdruck bearbeiten und der Versuch überlebt den Neustart.

**Demo** PDF hineinziehen, drei Aufgaben markieren, eine unter laufendem Timer
lösen, App neu starten, Versuch wiederfinden.

**Risiko** Die Review-UI wird mühsam zu bedienen und der Nutzer bricht ab.
**Ausweich** Tastaturbedienung priorisieren; Zerlegung an eigenen Klausuren
mit der Stoppuhr messen, bis 10 Minuten stehen.

---

## M2 · Solve-View vollständig, numerische Bewertung

**Vorgezogen nach M1:** Aufgabenanzeige, Zeitbudget aus Punkten, laufender
Timer, Wert-und-Einheit-Erfassung, Versuch speichern. Begründung: ohne diese
Grundform ist die M1-DoD („unter Zeitdruck bearbeiten") nicht erfüllbar, und
ein Import ohne Lösen liefert keinen Nutzen, an dem sich die Zerlegung messen
lässt. Was hier bleibt, ist alles Weitere.

**Inhalt** Screen 04 mit allen fünf Zuständen. Einheiten-Input mit getrennten
Präfixen und Tab-Wechsel. Bewertung numerisch mit Toleranz und dimensionaler
Einheitenprüfung.
Erste Fehlercodes (`E-UNIT`, `E-POT`, `E-SIGN`, `E-BLANK`, `E-TIME`).
Aufgabenleiste, Abgabe, Modal „Abgabe erzwingen".

**DoD** Alle fünf Zustände erreichbar. Der Einheiten-Testfall besteht:
`12 kΩ` gegen Soll `12000 Ω` gibt volle Punkte und kein `E-POT`; `12 Ω` gibt
Abzug und `E-POT`. Timer stimmt gegen eine echte Stoppuhr über 20 Minuten.

**Demo** Aufgabe lösen, in die 70-%-Warnung und in die Überschreitung laufen,
abgeben, Punkte sehen.

**Risiko** Die Einheitenlogik wird an zwei Stellen verschieden implementiert.
**Ausweich** Genau eine Funktion im Kern; die UI ruft sie, statt zu prüfen.

---

## M3 · Auto-Segmentierung und Lösungs-Extraktion

**Inhalt** Heuristische Segmentierung offline. OCR-Adapter für alle drei
Plattformen. Entzerrung für Scan und Foto. LLM-Verfeinerung mit Opt-in,
Vorschau und Protokoll. Lösungsbezug bei getrenntem Dokument. Zerlegung der
Musterlösung in `SolutionStep`. Golden-File-Testkorpus.

**DoD** Auf dem Korpus: ≥ 80 % korrekte Aufgabengrenzen bei Textlayer-PDFs,
≥ 60 % bei Scans. Overrides überleben jeden erneuten Lauf (E2E-Pfad 2).
Kein LLM-Aufruf ohne bestätigte Vorschau.

**Demo** Dieselbe Klausur wie in M1 automatisch zerlegen lassen, dann eine
Grenze korrigieren, dann erneut laufen lassen — die Korrektur bleibt.

**Risiko** Die Trefferquote bleibt unter 50 % und die Automatik nervt mehr als
sie hilft. **Ausweich** Auto-Segmentierung als abschaltbarer Vorschlagsmodus
ausliefern; M1 trägt weiterhin allein.

---

## M4 · Parametrische Varianten und Verifikation

**Inhalt** Vorlagenerstellung halbautomatisch aus Musterlösung. Wertebereiche
aus Größenart plus Ableitung vom Original, Rasterung auf Normreihen.
Constraints mit Rejection Sampling. Dreistufige Verifikation. Quarantäne-Ansicht.

**DoD** Für zehn Aufgaben aus dem Korpus existieren verifizierte Vorlagen.
Alle Fallen-Fixtures (Polstelle, überbestimmt, dimensional falsch) landen in
Quarantäne mit der richtigen Begründung. Keine unverifizierte Variante
erreicht die UI.

**Demo** Aufgabe öffnen, „Variante erzeugen", andere Zahlen, Verifikations-
bericht zeigen.

**Risiko** Die Vorlagenerstellung braucht so viel Handarbeit, dass niemand sie
macht. **Ausweich** Auf einen Aufgabentyp beschränken (Netzwerkberechnung),
dort gut machen, Breite später.

---

## M5 · Adaptive Engine, Heatmap, Prüfungsradar

**Inhalt** FSRS-Variante mit der Rating-Abbildung aus `06`. Wissensgraph mit
Voraussetzungsfilter. Zeitbudget-Kalibrierung. Screens 08, 09, 12.
Blockierte Klausurpunkte als Kennzahl.

**DoD** Voraussetzungsfilter hält im Property-Test. Prüfungsradar zeigt bei
≥ 3 Klausuren die Wiederkehr-Matrix, darunter den Leerzustand mit Bedingung.
Fehler-DNA-Streifen über 8 Wochen aus echten Versuchen.

**Demo** Nach zwanzig gelösten Aufgaben: Graph mit Farben, Radar mit Matrix,
Fehlerprofil mit Trend.

**Risiko** Zu wenig eigene Daten, um zu erkennen, ob die Auswahl sinnvoll ist.
**Ausweich** Synthetische Lernverläufe zur Prüfung des Schedulers; die echte
Bewertung kommt aus der eigenen Klausurphase.

---

## M6 · Simulator und Prognose

**Inhalt** Screen 06 in Fokus-Dunkel mit Hilfsmittel-Panel, volle Klausurdauer,
keine Auswertung bis zum Ende. Screen 07 Ergebnis. Bestehensprognose mit
Intervall, Datenschwelle und konservativer Verzerrung.

**DoD** Ein vollständiger Simulationslauf über die echte Klausurdauer ist
durchführbar und wird korrekt ausgewertet. Unter der Datenschwelle rendert die
Prognose **keine Zahl**. Kalibrierungstest auf synthetischen Daten besteht.

**Demo** 90-Minuten-Lauf starten, abbrechen, wieder aufnehmen, auswerten.

**Risiko** Die Prognose wirkt trotz aller Vorsicht beruhigend und der Nutzer
lernt zu wenig. **Ausweich** Prognose hinter eine ausdrückliche Aktion legen
statt sie auf dem Ergebnisscreen zu zeigen.

---

## M7 · Politur: Motion, Onboarding, Leerzustände

**Inhalt** Screens 01, 14, 15. Profil-Arithmetik mit Verhaltensterm.
Motion-Durchlauf gegen Handoff Abschnitt 9 samt Reduce-Motion-Fallbacks —
Grundlage ist das bereits vorliegende Motion-Token-System. Import-Zerlege-
Animation. Alle Leerzustände. Tastatur- und Fokusreihenfolge, Screenreader-
Labels für Ring, Balken und Heatmap.

**DoD** Reproduktionstest ergibt `82 / 54 / 28 / 60 / 71 / 34`. Jede Regel in
Screen 15 abschaltbar mit Herleitung. Keine hartkodierte ms-Zahl außerhalb der
Motion-Tokens. Reduce-Motion für jede Animation.

**Demo** Onboarding durchspielen, Profil sehen, eine Antwort ändern, Regel
kippen sehen, Regel abschalten, Wirkung im Solve-View verschwinden sehen.

**Risiko** Politur dehnt sich unbegrenzt. **Ausweich** Zeitkasten von zwei
Wochen; was nicht hineinpasst, wandert hinter M8.

---

## M8 · Packaging

**Inhalt** macOS-Signatur und Notarisierung, DMG. iOS-Build über EAS,
TestFlight. Android-Build. Update-Mechanismus Desktop. Backup und
Wiederherstellung der lokalen Datenbank.

**DoD** Auf einem fremden Mac ohne Entwicklerwerkzeuge installierbar und
startfähig. TestFlight-Build auf einem fremden Gerät. Backup wiederhergestellt,
Datenbestand vollständig.

**Demo** DMG an jemanden schicken, der es öffnet.

**Risiko** Apple-Zertifikate und Notarisierung kosten unvorhersehbar Zeit.
**Ausweich** Notarisierung früh in M0 einmal probeweise durchspielen, nicht
erst am Ende — der erste Durchlauf ist immer der teure.

---

## Reihenfolge-Logik

M1 vor M3, weil manuelle Zerlegung ohne Automatik nutzbar ist, Automatik ohne
Korrektur aber nicht. M2 vor M4, weil Varianten ohne Bewertung sinnlos sind.
M4 vor M5, weil der Scheduler Wiederholungsmaterial braucht. M7 spät, weil
Politur an unfertiger Struktur zweimal gemacht werden muss.

**Nach M2 ist das Produkt benutzbar.** Alles danach macht es besser, nicht
erst brauchbar. Wenn die Zeit knapp wird, ist das die Linie, hinter der
gekürzt wird.
