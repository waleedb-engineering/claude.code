# Analyzer-Kalibrierung (v2)

Kurzreferenz, wie der **Performance-Potential-Score** kalibriert ist und wie
er sich auf realistischen Transkripten verhält.

> **Ehrlich:** Der Score ist eine **Heuristik-Einschätzung**, keine
> Viralitätsgarantie. Er soll schwache, mittelmäßige und starke Clips
> **nachvollziehbar unterscheiden** — mehr nicht.

## Score-Bänder

| Band | Score | Bedeutung |
|------|-------|-----------|
| schwach | **35–59** | generisch, Kontext-abhängig, Füllwort-lastig, schwacher Hook |
| solide | **60–74** | brauchbar, aber ohne herausstechendes Signal |
| gut | **75–84** | klarer Hook + eigenständig + Substanz |
| sehr stark | **85–94** | starker Hook + hohe Retention + kontextfrei |
| extrem selten | **95+** | nur bei exzellenten Kern-Signalen (Deckel greift sonst bei 94) |

Die Aggregation ist eine lineare Spreizung der (naturgemäß engen) gewichteten
Rohverteilung: `score = raw * 1.52 − 16.9`, geclampt auf 0–100. Zusätzlich
verhindert ein Kern-Signal-Deckel (Ø aus Hook/Retention/Kontextfreiheit < 88),
dass Mittelmaß über 94 rutscht. Damit ist der Score **nicht inflationär**:
nicht jeder Clip landet über 80.

## Referenz-Transkripte

Kompakte, aber realistische Fixtures in `api/tests/transcripts_fixtures.py`:

| Fixture | Sprache | Segmente | Dauer | Zweck |
|---------|---------|----------|-------|-------|
| `de_podcast` | DE | 21 | ~137 s | Interview/Podcast, mehrere gute Clips + Füller |
| `en_education` | EN | 17 | ~112 s | Educational/Creator, how/why/hooks/takeaways |
| `mixed` | DE/EN | 5 | ~30 s | Sprachmix, darf nicht crashen |
| `weak` | DE | 6 | ~33 s | Smalltalk/Füller → niedrige Scores |

## Kandidaten & Top-Scores (rule_based, ohne API-Key)

**de_podcast** — 20 Kandidaten → 5 nach Dedup → 5 ausgewählt:

| Score | Hook | Flags | Auszug |
|------:|------|-------|--------|
| 90.9 | These | – | „Niemand sagt dir das, aber Konsistenz schlägt Talent …" |
| 88.2 | Frage | – | „Warum scheitern die meisten Gründer schon im ersten Jahr?" |
| 77.8 | These | – | „Ehrlich gesagt ist die beste Marketing-Strategie …" |
| 72.8 | Aussage | – | „Schritt eins: poste jeden Tag zur gleichen Zeit …" |
| 60.0 | Aussage | weak_hook | „Ich war kurz davor, alles hinzuwerfen …" |

**en_education** — 16 Kandidaten → 4 nach Dedup → 4 ausgewählt:

| Score | Hook | Flags | Auszug |
|------:|------|-------|--------|
| 89.8 | These | – | „Everyone chases more, but focus is the real unfair advantage …" |
| 79.6 | Frage | – | „Why do most people never actually finish what they start?" |
| 76.0 | Aussage | – | „Here is how you learn any skill twice as fast in ninety days." |
| 57.0 | Aussage | needs_context, slow_start, weak_hook | „So the takeaway is simple: start ugly …" |

**mixed** — 4 Kandidaten → 1 nach Dedup: 89.4, Frage-Hook, Flag `language_mixed`
(korrekt erkannt). Kein Crash.

**weak** — 5 Kandidaten → 2 nach Dedup: 52.1 und 41.7, beide mit
`slow_start`, `weak_hook`, `transcript_quality_low` (Smalltalk korrekt niedrig).

## Verteilung (alle Fixtures, 12 ausgewählte Clips)

- min **41.7** · max **90.9** · mean **72.9** · median **76.9**
- Bänder: schwach<60 = 3 · solide 60–74 = 2 · gut 75–84 = 3 · sehr stark 85–94 = 4 · 95+ = **0**

Reproduzierbar über `python api/tests/calibration_report.py` bzw. die Tests in
`api/tests/test_analyzer.py`.

## Starke vs. schwache Beispiele — warum

- **Stark (88–91):** Frage-/These-Hook in den ersten Sekunden, kontextfreier
  Einstieg (kein „das/deshalb/it/but"), klare Aussage mit Payoff, wenig Füller.
- **Schwach (35–52):** generischer/Füllwort-Einstieg („naja", „also", „ja"),
  niedrige Content-Wort-Dichte, kein greifbarer Payoff → mehrere Risk-Flags.

## Risk-Flags (stabile englische Keys)

`needs_context`, `slow_start`, `too_generic`, `weak_hook`, `too_long`,
`too_short`, `low_information_density`, `unclear_takeaway`, `duplicate_like`,
`language_mixed`, `transcript_quality_low`.

Die Flags steuern die Verbesserungsvorschläge und werden im Frontend als
lesbare deutsche Labels dargestellt. Alte Clips ohne `risk_flags` bleiben
stabil (leere Liste).

## Dedup & Diversität

- Gruppierung per **Zeitüberlappung ≥ 0.5** ODER **Text-Jaccard ≥ 0.55**
  (Content-Wörter).
- Pro Gruppe gewinnt bei Score-Gleichstand die Variante mit **sauberem
  Satzende**; `duplicate_group` markiert Gruppen mit >1 Fundstelle.
- Auswahl greedy nach Score, meidet Clips mit **Zeitüberlappung ≥ 0.35** zu
  bereits gewählten (andere Video-Stellen bevorzugt).
- Bei zu wenig Vielfalt wird **aufgefüllt** und der Clip mit `duplicate_like`
  markiert; `filled_up` im `clips.json` zeigt an, wie viele.

## LLM-Modus (optional, härtefest)

- **Ohne `ANTHROPIC_API_KEY` → immer `rule_based`.** Der Key ist nie Pflicht.
- Der LLM **re-rankt nur** die per Timestamp erzeugten Kandidaten (Index-basiert)
  und erfindet **keine** neuen Zeitfenster. Unbekannte Indizes werden verworfen.
- Robustes JSON-Parsing: Markdown-Fences entfernen, Text vor/nach dem JSON
  ignorieren, Schema prüfen, kaputte Werte clampen.
- Timeout/Fehler/Rate-Limit → **Fallback** auf die regelbasierten Scores
  (`analyzer_mode = "fallback"`, `llm_error`/`llm_latency_ms` im Meta).
- **Realer LLM-Lauf: in dieser Umgebung nicht ausgeführt (kein Key gesetzt).**
  Verifiziert über Fake-Client-Tests (valide/kaputte/markdown/erfundene JSON).
  Latenz wird bei echtem Lauf gemessen und in `clips.json` dokumentiert.

## Bekannte Grenzen & Tuning-Empfehlungen

- Rein lexikalische Heuristik (Signalwort-Listen, DE+EN) — kein semantisches
  Verständnis; Ironie/Kontext jenseits der ersten Sekunden wird nicht erkannt.
- Kalibrierung ist auf die o. g. Fixtures gefittet; sehr fachspezifische oder
  sehr lange Transkripte können abweichen.
- Tuning-Hebel: `_WEIGHTS` (Komponentengewichte), die Aggregations-Konstanten
  in `_aggregate_score` und die Flag-Schwellen in `_risk_flags`. Nach Änderungen
  `api/tests/calibration_report.py` erneut prüfen, damit die Bänder erhalten bleiben.
- Der Score misst **Kurzform-Eignung**, keine tatsächliche Performance. Keine
  Viralitätsgarantie.
