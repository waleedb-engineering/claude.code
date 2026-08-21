# KLAUSURA — Motion-Prompt für Claude Design

Baue in Claude Design `KLAUSURA.dc.html` — eine Lern-App für Ingenieur-Altklausuren
(Aufgaben unter Zeitdruck lösen, Punkte, Timer, Fehleranalyse). Die Datei muss als
Artboard-Canvas funktionieren UND standalone im Browser lauffähig sein: eine Datei,
keine externen Abhängigkeiten außer Google Fonts.

Diese App lebt von Bewegung. Statische Screens sind hier ein Fehlschlag, kein
Zwischenstand. Ich will Animationen, die im Gedächtnis bleiben — aber jede einzelne
muss etwas ERKLÄREN, nicht dekorieren.

---

## ETAPPE 0 — Fundament

Existiert `KLAUSURA.dc.html` bereits im Projekt: lies sie vollständig und berichte
Screens, Styling-System, vorhandene Animationen. Existiert sie NICHT: sag mir das in
einem Satz und baue sie aus dieser Spezifikation neu — frag nicht nach.

Mindestumfang für die Animationen unten (nicht alle 14 Screens des Vollprodukts):

- **Import** — PDF-Seitenvorschau links (6 Aufgabenblöcke an festen Positionen:
  top `8, 92, 152, 212, 300, 386`, Höhe `78, 54, 54, 82, 80, 86`), Kartenraster rechts
- **Aufgaben-Atlas** — Kartenraster, 3 Spalten
- **Solve-View** — Kopfband mit Timer-Ring, links Aufgabenstellung, rechts Ergebnisfeld
  + Rechenweg, unten Aufgabenleiste als Chips. 5 Zustände: frisch · in Arbeit ·
  Warnung 70 % · überzogen · abgegeben
- **Rechenweg-Diff** — zwei Spalten „Dein Weg" | „Musterlösung", Zeile für Zeile
- **Simulator** — Fokus-Dunkel, Gesamtzeit-Ring, Aufgaben-Chipleiste
- **Ergebnis** — große Punktzahl, Aufgabenliste, Bestehensabstand
- **Fehler-DNA** — gestapelte Wochenbalken nach Fehlerklasse
- **Wissensgraph** — Knoten in 3 Spalten (x = 24/280/536), Kanten als 1-px-Linien

### Design-Tokens (setzen, nie Hex in Komponenten)

Rollen: `paper` `panel` `chrome` `grid` `rule` `ink` `ink60` `ink30` `track`
`signal` `warn` `over` `ok`

Hell: paper `#EFEFEC` · panel `#F7F7F4` · chrome `#FFFFFF` · grid `#FBFBF9` ·
rule `#E6E6E1` · ink `#14150F` · ink60 `#6B6B66` · ink30 `#B4B4AE` · track `#E6E6E1` ·
signal `#FF5A00` · warn `#B45309` · over `#C2280F` · ok `#2F6B3A`

Fokus-Dunkel: paper `#0B0C09` · panel `#111310` · chrome `#141612` · grid `#101209` ·
rule `#26281F` · ink `#F2F2EC` · ink60 `#8E9086` · ink30 `#4A4C44` · track `#26281F` ·
signal `#FF7A2E` · warn `#E0A64A` · over `#FF5240` · ok `#5FBF7A`

IBM Plex Sans + IBM Plex Mono. `radius: 2px`. Genau eine Elevationsstufe.
Karten werden durch 1-px-Hairlines getrennt, nicht durch Schatten.
`font-variant-numeric: tabular-nums` auf jedem veränderlichen Zahlenwert.
Labels in Mono, Großbuchstaben, `letter-spacing: .14em`.

Ästhetik: Laborgerät / Oszilloskop. Technisch, dicht, präzise. Kein Gamification-Look.

---

## ETAPPE 1 — Motion-System zuerst

Bevor eine einzige Animation entsteht, definiere ein System als CSS-Variablen:

- **Dauern**: instant 80 · quick 150 · base 250 · slow 400 · dramatic 800.
  Zwei begründete Ausnahmen, namentlich dokumentiert: Timer-Sekundentakt 1000,
  Bestanden-Moment 900.
- **Kurven**: `--ease-out` für Eintritt, `--ease-in` für Austritt, `--ease-inout` für
  Umschalten, `--ease-settle` (gedämpfter Overshoot ≤ 12 %) für Landungen,
  `--ease-spring` NUR für Belohnung, `linear` NUR für den Timer.
- **Stagger**: tight 40 · base 60 · cards 90 · cut 240, plus eine Kappungsgrenze
  (ab Element 12 kein weiterer Zuwachs, sonst wartet der Nutzer bei 30 Karten
  sieben Sekunden).
- **z-Ebenen**: lückenhaft nummeriert — base · raise · sticky · scanline · flyer ·
  overlay · modal · toast · euphoria.
- **Kombi-Tokens**: `--t-hover`, `--t-enter`, `--t-switch`, `--t-reward` usw., damit
  die Verwendungsstelle eine Zeile schreibt statt drei.

Danach: **keine einzige hartkodierte ms-Zahl und keine hartkodierte cubic-bezier im
gesamten Dokument.** Ich werde nach `ms)` und `cubic-bezier` greppen. Treffer außerhalb
des `:root`-Blocks gelten als Fehler.

Zeig mir das System, bevor du weiterbaust.

---

## ETAPPE 2 — Was „stark" heißt

Stark heißt **nicht** länger, nicht verspielter, nicht mehr Bounce. Stark heißt
Amplitude, Choreografie und Physik. Konkret — nutze diese sechs Hebel bewusst:

1. **Amplitude** — echte Distanzen. Eine Karte, die 400 px fliegt, ist stärker als
   eine, die 14 px faded. Skalensprünge ab `0.7`, Rotationen bis 10°, nicht 2°.
2. **Choreografie** — mehrere Elemente in einer Sequenz, überlappend, nicht
   gleichzeitig. Sekundärbewegung: was passiert mit den Nachbarn?
3. **Tiefe** — `perspective`, `rotateX/Y`, Parallaxe zwischen Ebenen, `clip-path`-
   Enthüllungen. Die Fläche darf räumlich werden.
4. **Kontinuität** — kein Cut, kein Fade zwischen verwandten Zuständen. Shared-Element-
   Transitions per FLIP: `getBoundingClientRect()` vorher/nachher, Differenz als
   `transform`. Ein Objekt, das an zwei Orten existiert, muss dazwischen fliegen.
5. **Masse** — Dinge haben Gewicht. Beschleunigung, Trägheit, Landing-Settle.
   Ein 600-px-Flug endet nicht abrupt.
6. **Kamera** — bei Modus- und Screenwechseln darf sich der Viewport selbst bewegen:
   Zoom, Verschiebung, Abdunklung.

Wenn eine Animation nur `opacity 0 → 1` ist, hast du den Hebel nicht benutzt.
Wenn sie wobbelt, hast du den falschen benutzt.

---

## ETAPPE 3 — Die Animationen

In dieser Prioritätsreihenfolge. Baue 1–3, lass mich gegenlesen, dann den Rest.

### 1. TIMER-RING — das Herzstück
SVG-Ring, r ≈ 21, Umfang 131.9, `stroke-dasharray` = Umfang,
`stroke-dashoffset` = Restanteil. **Muss echt laufen** — `requestAnimationFrame` mit
`performance.now()`, kein CSS-Fake, kein `setInterval`-Zähler. Start/Pause/Reset
steuerbar. Schwellen: bei 70 % Farbwechsel `signal → warn` mit kurzem Aufblitzen der
Zeitanzeige; bei 90 % ein subtiler Puls auf einer separaten Glow-Ebene (nie auf dem
Ring selbst — der Ring muss lesbar bleiben); bei Überschreitung `over` und die ganze
Ring-Baugruppe **kippt** sichtbar: `rotate(-3deg)` plus Absacken um 2 px, Ring bleibt
in dieser Schieflage. Alle Zustandswechsel über `--t-switch`.
*Abnahme:* die Sekundenzahl stimmt mit einer echten Stoppuhr überein.

### 2. EXAM SHREDDER — der Wow-Moment
Der Import. Hier steckt die meiste Sorgfalt.
- Eine **Scanlinie** (2 px `signal`, `box-shadow 0 0 14px signal@60%`) wandert über die
  PDF-Vorschau zur nächsten Blockposition, `--dur-dramatic`, `--ease-out`.
- Beim Erreichen eines Blocks wird der Block **sichtbar herausgeschnitten**:
  `clip-path` öffnet eine Schnittkante, der Block hebt sich um 4 px von der Seite ab.
- Ein **Klon** des Blocks entsteht an dessen exakter Bildschirmposition
  (`getBoundingClientRect`), `position: fixed`, `--z-flyer`.
- Der Klon fliegt zu seinem Zielslot im Raster — **auf einem Bogen, nicht auf einer
  Geraden.** Zwei überlagerte Transforms oder `offset-path`. Unterwegs: Rotation
  zwischen −8° und +8° (pro Karte deterministisch variiert), leichtes Anheben per
  Schatten, Skalierung von `0.82` auf `1`.
- **Landing-Settle** mit `--ease-settle`, Overshoot ≤ 12 %, danach übernimmt das echte
  Rasterelement und der Klon wird entfernt.
- Die Nachbarkarten im Raster **rücken sichtbar zur Seite**, wenn die neue landet.
- Stagger `--stagger-cut` zwischen den sechs Karten. Flug pro Karte ≤ `--dur-dramatic`.
- Fortschrittsbalken und Statuszeile (`SCHNEIDE A3 …`) laufen mit.

### 3. PUNKTE-ZÄHLER
Zahl zählt per `requestAnimationFrame` mit Ease-out hoch, nicht linear, nicht per
`setInterval`. Die Ziffer bekommt beim Stopp einen Scale-Impuls `1 → 1.18 → 1` mit
`--ease-spring`. Die erreichten Punkte **wandern sichtbar** vom Aufgabenfeld in den
Gesamtscore — fliegendes Badge auf `--z-flyer`, Bogenbahn, und der Gesamtscore
quittiert die Ankunft mit einem eigenen Impuls. Der Transfer muss die Kausalität
zeigen: diese Punkte kommen aus dieser Aufgabe.

### 4. RECHENWEG-DIFF
Lösungsschritte erscheinen nacheinander, `--stagger-base`, von unten einschwebend.
Die abweichende Zeile leuchtet **verzögert** auf — erst wenn alle Zeilen stehen,
dann `over@5%`-Hintergrund einwischend per `clip-path` von links. Danach schiebt sich
die Fehlerklassifikation von rechts ein, `--t-enter`. Reihenfolge ist die Botschaft:
erst der Weg, dann die Abweichung, dann ihr Name.

### 5. FEHLER-DNA
Der Fehler fliegt als Partikel aus der Diff-Zeile in seine Kategorie im Wochenstreifen.
Der Balken dieses Segments wächst währenddessen sichtbar — `scaleY` mit
`transform-origin: bottom`, niemals `height`. Ankunft und Wachstum überlappen zeitlich.

### 6. HEATMAP / WISSENSGRAPH
Knoten pulsieren nach Beherrschungsgrad — schwache Themen langsamer und schwächer,
nicht schneller (Unruhe wäre die falsche Botschaft). Verbindungslinien zeichnen sich
beim Laden progressiv per `stroke-dashoffset`, gestaffelt entlang der
Voraussetzungskette: Voraussetzung vor Folgethema. Heatmap-Zellen erscheinen als Welle
diagonal von links oben.

### 7. MODUSWECHSEL IN DEN SIMULATOR
Kein Fade. Ein **Schaltvorgang**. Die UI zieht sich physisch zusammen: alles
Nicht-Essenzielle fliegt nach außen aus dem Viewport (Richtung abhängig von der
Position — links raus nach links), das Grid kontrahiert auf die engere Simulator-
Spaltenaufteilung, der Hintergrund fährt auf Fokus-Dunkel, eine kurze Verdunklung
läuft als Blende darüber. Mehrphasig, gesamt ≤ `--dur-dramatic`. Muss sich anfühlen
wie ein Kippschalter, nicht wie ein Übergang.

### 8. AUFGABE ABGEGEBEN
Karte kippt weg: `perspective` auf dem Container, `rotateX` nach hinten, Absinken und
Ausblenden. Die nächste Karte rückt nach — echte Nachrück-Bewegung der Nachbarn per
`transform`, nicht per Layout-Reflow.

### 9. HOVER / PRESS
Auf **allen** interaktiven Elementen: Karten, Chips, Buttons, Segmente, Tabellenzeilen,
Graph-Knoten. 80–150 ms. Spürbar, aber nicht verspielt: Press drückt auf `0.97`,
Hover hebt minimal und verstärkt die Rahmenfarbe. Konsistent über alle Typen.

### 10. BESTANDEN-MOMENT
Der EINZIGE euphorische Moment im Produkt. Darf groß sein, 900 ms, mehrphasig.
**Kein Konfetti.** Bau etwas aus der Messtechnik-Bildsprache — z. B. eine
Oszilloskop-Spur, die über den Screen läuft und als gedämpfte Sprungantwort mit
Überschwingen auf dem Ergebniswert einrastet; oder ein Zeigerausschlag über eine
Skala, der über der Bestehensgrenze zur Ruhe kommt; oder eine Lissajous-Figur, die
sich zum geschlossenen Kreis auflöst. Entscheide dich für **eine** Idee und führe sie
konsequent aus. Das Rasterraster darf dabei kurz aufleuchten.

---

## VERBOTEN

- Bounce oder Wobble auf normalen UI-Elementen. Overshoot nur bei Landung
  (≤ 12 %) und Belohnung.
- Animationen über 800 ms — außer dem Bestanden-Moment.
- Dauerbewegung im Hintergrund, während der Nutzer eine Aufgabe rechnet.
  Der Solve-View ist still bis auf den Timer.
- Konfetti. Überhaupt.
- Alles, was den Blick vom Timer wegzieht, solange die Zeit läuft.
- Gamification-Vokabular: keine XP, keine Level, keine Streaks.

## TECHNISCHE REGELN

- Animiere `transform` und `opacity`. Drei benannte Ausnahmen, weil sie unvermeidbar
  und billig sind: `stroke-dashoffset` (Timer-Ring, Graph-Kanten), `clip-path`
  (Schnittkante, Diff-Wisch), `background-color`/`color` bei Zustandswechseln.
  Niemals `width`, `height`, `top`, `left`, `margin`.
- `will-change` gezielt vor dem Start setzen und im `animationend`/`transitionend`
  wieder entfernen. Nie dauerhaft im Stylesheet.
- 60 fps ist die Abnahmebedingung. Schafft eine Animation das nicht, vereinfache sie,
  statt sie zu behalten. Maximal ~20 gleichzeitig fliegende Elemente.
- `@media (prefers-reduced-motion: reduce)` für **jede** Animation: nicht ersatzlos
  streichen, sondern durch einen sofortigen Zustandswechsel ersetzen. Kein pauschales
  „alle Dauern auf 1 ms" — der Zielzustand muss ohne Bewegung vollständig lesbar sein.
  **Der Timer bleibt auch dort funktional und läuft weiter**; nur sein Puls entfällt.
- Vanilla CSS/JS. Keine Library. Brauchst du doch eine, nenne vorher Grund und
  Bundle-Kosten und warte auf mein OK.
- Web Animations API ist erlaubt, wo sie sauberer ist als Keyframes.
- Die Datei bleibt standalone lauffähig.

## TRIGGER-PANEL (Pflicht)

Baue ein ausklappbares Debug-Panel unten rechts, das jede der zehn Animationen einzeln
per Knopfdruck auslöst und wiederholbar macht — plus einen Schalter „Reduced Motion
simulieren". Ohne das kann ich nichts abnehmen.

## LIEFERUNG

1. `KLAUSURA.dc.html` — vollständig, standalone, mit Trigger-Panel
2. `MOTION.md` — jede Animation mit Trigger, Dauer, Kurve, Zweck und
   Reduced-Motion-Fallback, als Tabelle
3. Zum Schluss: konkret, welcher Klick in welcher Reihenfolge jede Animation im
   Browser auslöst

Arbeite in Etappen. Zeig mir das Motion-System, dann Animation 1–3, dann warte auf
mein Gegenlesen.
