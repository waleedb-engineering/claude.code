# verifikation.md

Jede Zahl, die aufs Blatt kommt, steht hier mit Quelle, Python-Ergebnis und Status.

**Quellenlage:** `BAUELEMENTE_KI_MASTER.zip` (71 MB) konnte nicht hochgeladen werden.
Referenz ist daher §8 des Bauplans, der die Musterlösungswerte bereits enthält.
Spalte *Quelle* nennt deshalb `Bauplan §x.y` statt `Skript S. NN`.
Ein Abgleich gegen die Original-PDFs steht noch aus.

Status-Legende: `OK` = Python bestätigt den Referenzwert · `ABW` = Abweichung, unten erklärt
· `UNGEPR` = kein Referenzwert vorhanden, nur Python.

---

## B-01 — Widerspruch im Bauplan: welcher U_T-Wert gilt?

Der Bauplan gibt in §8 2.1 den Shortcut *„k_B·T = 0,025 eV direkt einsetzen"* an und nennt
im selben Abschnitt das Ergebnis **W_F − W_i = 0,45 eV**. Beides zusammen geht nicht auf:

| eingesetztes k_B·T | W_F − W_i bei n₀ = 5·10¹⁷ cm⁻³ | U_D bei N_A = N_D = 10¹⁵ cm⁻³ |
|---|---|---|
| 25,0 meV (Klausurvorgabe) | 0,433 eV | 555,4 mV |
| **25,875 meV** (= k_B·T/e exakt, T = 300 K) | **0,448 eV** | **574,8 mV** |
| 26,0 meV (Übungen) | 0,450 eV | 577,6 mV |

Referenzwerte des Bauplans: 0,45 eV (§8 2.1) und 575 mV (§8 2.4).

**Befund:** Beide Musterlösungswerte entstehen mit **25,9 meV bzw. 26 meV**, nicht mit 25 meV.
Der Shortcut „0,025 eV einsetzen" liefert 0,433 eV und reproduziert die angegebenen
0,45 eV **nicht**.

**Umsetzung auf dem Blatt (nicht still korrigiert, sondern beides notiert):**
Der Shortcut bleibt drin, bekommt aber eine rote Warnung mit beiden Zahlen daneben.
Regel auf dem Blatt: *den in der Aufgabe vorgegebenen U_T-Wert verwenden* — die Klausur gibt
25 mV vor, die Übungsmusterlösungen rechnen mit 25,9/26 mV.

---

## B-02 — p₀ hängt davon ab, ob n₀ genähert wird

| n₀ | p₀ = n_i²/n₀ |
|---|---|
| 5·10¹⁷ cm⁻³ (Näherung, Musterlösung Ü02) | **450 cm⁻³** |
| 4,95·10¹⁷ cm⁻³ (exakt, N_D − N_A) | 454,5 cm⁻³ |

Bauplan §6 nennt **4,5·10² cm⁻³**. Das entspricht der Näherung. Auf dem Blatt steht die
Näherung, mit dem exakten Wert als Randbemerkung — Bauplan §6 sagt ausdrücklich, dass die
Musterlösung mit 5·10¹⁷ rechnet.

---

## Seite 1 — Konstanten, Einheiten, Mathe

Skript: `verify/s1_konstanten.py`

| Größe | Referenz | Quelle | Python | Status |
|---|---|---|---|---|
| U_T = k_B·T/e, T = 300 K | 25 mV | Bauplan §8 1.1 (Klausurvorgabe) | 25,875 mV | OK¹ |
| ħ = h/2π | 1,05·10⁻³⁴ Js | abgeleitet | 1,0504·10⁻³⁴ Js | OK |
| n_i: cm⁻³ → m⁻³ (×10⁶) | 1,5·10¹⁶ m⁻³ | Bauplan §8 1.1 | 1,5·10¹⁶ m⁻³ | OK |
| μ_n: m²/Vs → cm²/Vs (×10⁴) | 1350 cm²/Vs | Bauplan §6 | 1350 cm²/Vs | OK |
| λ_max(Si) = h·c/W_g | 1,13 µm | Bauplan §8 2.7 | 1,125 µm | OK |
| k_B·T bei 300 K | ≈ 25 meV | Bauplan §8 1.4 | 25,875 meV | OK¹ |
| σ dotiert = e·μ_n·n₀ | 1,08·10⁴ S/m | Bauplan §6 (Korrektur 5) | 1,08·10⁴ S/m | OK |
| σ undotiert = e·(μ_n+μ_p)·n_i | 4,39·10⁻⁴ S/m | Bauplan §6 / §8 2.2 | 4,392·10⁻⁴ S/m | OK |
| Verhältnis σ_dot/σ_undot | ~2,5·10⁷ | Bauplan §6 | 2,46·10⁷ | OK |
| √2 | 1,414 | Bauplan §8 1.3 | 1,41421 | OK |

¹ gerundeter Klausurwert, siehe B-01.

---

## Die fünf Fehler aus §6 des Bauplans — Übernahmestatus

| # | Fehler in den Notizen | Korrigierter Wert aufs Blatt | Seite | erledigt |
|---|---|---|---|---|
| 1 | J → eV mit `1,6·10⁻¹⁵` | **÷ 1,6·10⁻¹⁹** | S2 (Rezept Schritt 4) | offen |
| 2 | „p-Dotierung → Silizium" | **p-Dotanden: B, Al, In** (dreiwertig); Si = Grundmaterial | S1 §1.5 | **erledigt** |
| 3 | p₀ fehlt | n₀ ≈ 5·10¹⁷ cm⁻³, **p₀ = 4,5·10² cm⁻³** | S2 | offen |
| 4 | „σ nimmt mit fallender T zu" | Klausurwortlaut: **nimmt mit fallender T ab** | S1 §1.5 | **erledigt** |
| 5 | σ dotiert fehlte | **σ = 1,08·10⁴ S/m**, Faktor ~2,5·10⁷ | S2 | offen |

---

## Seite 1 — Bau-Log

- Kompiliert mit `pdflatex` ×3. **1 Seite, 0 Fehler, 0 Overfull-Boxen.**
- Behobener LaTeX-Fehler: `tabularx` misst innerhalb von `multicols` falsch
  (reproduzierte Overfull-Box von exakt 15 pt, auch außerhalb von tcolorbox).
  Lösung: `parbox=true` im tcolorbox-Basisstil. Steht als Kommentar in `preamble.tex`.
- Der Widerspruch aus B-01 steht als roter Warnkasten in §1.1 — nicht still korrigiert.
- **Freier Platz:** unten rechts ca. 28 %, unten links ca. 13 % einer Spalte.
  Nichts gestrichen. Reserve für Ergänzungen nach dem Feedback.
