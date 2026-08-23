# 10 · Risiken

Wahrscheinlichkeit und Auswirkung geschätzt für ein Solo-Projekt mit
Portfolio-Anspruch. Unbequem, wie bestellt.

| # | Risiko | W | A | Gegenmaßnahme |
|---|---|---|---|---|
| 1 | Drei Plattformen ab Tag 1 überdehnen die Kapazität | hoch | hoch | Kern teilen, UI bewusst doppeln; nach M2 ehrlich prüfen, ob Mobile pausiert |
| 2 | Segmentierung bleibt zu ungenau, Korrektur nervt | hoch | hoch | M1 ohne KI muss allein tragen; Zerlegezeit als Kennzahl messen |
| 3 | Vorlagenerstellung ist zu mühsam, Varianten entstehen nie | hoch | mittel | Auf einen Aufgabentyp beschränken; ohne Varianten degradiert der Scheduler zu Wiederholung derselben Aufgabe |
| 4 | Numerische Probe reicht für Formelvergleich nicht | mittel | hoch | Drittes Urteil `unentscheidbar`; Fallback auf LLM-Rubrik; CAS-WASM als Reserve |
| 5 | Motivation bricht vor M5 weg | hoch | hoch | Nach M2 ist die App für dich selbst nutzbar — eigener Gebrauch ist der einzige verlässliche Antrieb |
| 6 | Apple-Auslieferung kostet unvorhersehbar Zeit | mittel | mittel | Notarisierung einmal in M0 probeweise durchspielen |
| 7 | Datenverlust durch fehlerhafte Migration | mittel | sehr hoch | Snapshot vor jeder Migration, Golden-Migrationstest, Startverweigerung bei unbekannter Version |
| 8 | FSRS-Anpassung ist unvalidiert und plant schlecht | mittel | mittel | Als unvalidiert dokumentiert; Intervalle gedeckelt; synthetische Verläufe im Test |
| 9 | Prognose beruhigt fälschlich | mittel | hoch | Datenschwelle, unteres Intervallende als Leitwert, ungeübte Themen als 0 |
| 10 | Urheberrechtliche Beanstandung | niedrig | hoch | Kein Pool, kein Sharing, kein Upload; Architektur macht es unmöglich, nicht nur die Policy |

## Die drei Punkte, an denen das Projekt realistisch scheitert

Nicht „verzögert" — scheitert.

**Erstens: Risiko 5, und es ist das größte.** Nicht die Technik. Ein
Solo-Projekt dieser Größe stirbt zwischen M3 und M5, weil die schwierige
Arbeit dann hinter einem liegt und die sichtbare Belohnung noch vor einem.
Die einzige belastbare Gegenmaßnahme ist, dass du die App ab M2 in deiner
eigenen Klausurphase benutzt. Wird sie nicht benutzt, wird sie nicht fertig.

**Zweitens: Risiko 2 plus 3 zusammen.** Wenn die Zerlegung mühsam bleibt *und*
Varianten nicht entstehen, ist KLAUSURA ein aufwendiger PDF-Betrachter mit
Stoppuhr. Beide Subsysteme müssen mindestens mittelmäßig funktionieren, sonst
trägt das Produktversprechen nicht. Das ist die inhaltliche Sollbruchstelle.

**Drittens: Risiko 1.** Drei Plattformen ab Tag 1 war eine bewusste
Entscheidung, aber sie ist teuer. Jede der 13 Komponenten entsteht zweimal,
jede Build-Kette wird zweimal gepflegt, jeder OCR-Fehler dreimal debuggt.
Wenn nach M2 die Mobile-Seite systematisch hinterherhinkt, ist das kein
Rückstand, den man aufholt — dann ist die Entscheidung zu revidieren, und der
ADR sieht das ausdrücklich vor.

## Was ausdrücklich kein Risiko ist

- **Die UI.** Sie ist vollständig spezifiziert, pixelgenau, in zwei Breiten,
  mit Tokens und Motion. Das ist Fleißarbeit, keine Unsicherheit.
- **Die Profil-Arithmetik.** Vollständig definiert, mit Testfall und
  Sollergebnis. Sie kann falsch implementiert werden, aber nicht scheitern.
- **Local-First.** SQLite auf dem Gerät ist gelöste Technik.
