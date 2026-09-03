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

**Bestätigt durch die handschriftlichen Notizen (Foto 1/2, Schritt 3):** dort steht
`1,38·10⁻²³ · 300 K = 4,14·10⁻²¹ J`, also k_B·T = **25,875 meV**. Damit ist belegt, dass
die Musterlösung mit dem vollen k_B·T rechnet, nicht mit dem gerundeten 25 meV.
Auf dem Blatt steht deshalb `k_B·T = 4,14·10⁻²¹ J` als expliziter Zwischenwert.

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
| 1 | J → eV mit `1,6·10⁻¹⁵` | **÷ 1,6·10⁻¹⁹** | S2 §2.1 Schritt 4 | **erledigt** |
| 2 | „p-Dotierung → Silizium" | **p-Dotanden: B, Al, In** (dreiwertig); Si = Grundmaterial | S1 §1.5 | **erledigt** |
| 3 | p₀ fehlt | n₀ ≈ 5·10¹⁷ cm⁻³, **p₀ = 4,5·10² cm⁻³** | S2 §2.1 Schritt 2 | **erledigt** |
| 4 | „σ nimmt mit fallender T zu" | Klausurwortlaut: **nimmt mit fallender T ab** | S1 §1.5 | **erledigt** |
| 5 | σ dotiert fehlte | **σ = 1,08·10⁴ S/m**, Faktor ~2,5·10⁷ | S2 §2.2 | **erledigt** |

---

## Seite 1 — Bau-Log

- Kompiliert mit `pdflatex` ×3. **1 Seite, 0 Fehler, 0 Overfull-Boxen.**
- Behobener LaTeX-Fehler: `tabularx` misst innerhalb von `multicols` falsch
  (reproduzierte Overfull-Box von exakt 15 pt, auch außerhalb von tcolorbox).
  Lösung: `parbox=true` im tcolorbox-Basisstil. Steht als Kommentar in `preamble.tex`.
- Der Widerspruch aus B-01 steht als roter Warnkasten in §1.1 — nicht still korrigiert.
- **Freier Platz:** unten rechts ca. 28 %, unten links ca. 13 % einer Spalte.
  Nichts gestrichen. Reserve für Ergänzungen nach dem Feedback.

---

## Seite 2 — Halbleiter dotiert · Fermi · pn-Übergang

Skript: `verify/s2_halbleiter.py`. Referenz sind die Zahlen aus Bauplan §8.2/§6 **und**
die handschriftliche Rechnung auf Foto 1/2 — beide stimmen mit Python überein.

| Größe | Referenz | Quelle | Python | Status |
|---|---|---|---|---|
| Typ bei N_D=5·10¹⁷, N_A=5·10¹⁵ | n-Halbleiter | Foto Schritt 1 | n | OK |
| n₀ (genähert) | 5·10¹⁷ cm⁻³ | Foto Schritt 2 | 4,95·10¹⁷ → 5·10¹⁷ | OK |
| p₀ = n_i²/n₀ | 4,5·10² cm⁻³ | Bauplan §6 | 450 cm⁻³ | OK |
| k_B·T bei 300 K | 4,14·10⁻²¹ J | Foto Schritt 3 | 4,140·10⁻²¹ J | OK |
| ln(n₀/n_i) | 17,322 | Foto Schritt 3 | 17,3221 | OK |
| W_F − W_i [J] | 7,17·10⁻²⁰ J | Foto Schritt 3 | 7,1713·10⁻²⁰ J | OK |
| W_F − W_i [eV] | 0,45 eV | Foto Schritt 4 + Bauplan §8 2.1 | 0,4482 eV | OK |
| σ dotiert | 1,08·10⁴ S/m | Bauplan §6 | 1,08·10⁴ S/m | OK |
| σ undotiert | 4,39·10⁻⁴ S/m | Bauplan §6 | 4,392·10⁻⁴ S/m | OK |
| σ-Verhältnis | ~2,5·10⁷ | Bauplan §6 | 2,46·10⁷ | OK |
| U_D (N_A=N_D=10¹⁵) | 575 mV | Bauplan §8 2.4 | 574,8 mV (mit 25,9 mV) | OK |
| λ_max(Si) = h·c/W_g | 1,13 µm | Bauplan §8 2.7 | 1,125 µm | OK |

**Ungeprüft (kein Referenzwert im Bauplan):** Potentialtopf §2.5 — nur Formel, kein
Zahlenbeispiel (Prio B). de-Broglie §2.6 — nur Formel. Beide ohne Zahlenwert aufs Blatt,
damit nichts Unbelegtes als geprüft erscheint.

---

## Platzkonflikt: „alles vollständig" gegen „exakt 6 Seiten"

Gemessen, nicht geschätzt:

| Schriftgröße | Ergebnis für S1+S2 |
|---|---|
| 7,0 pt | 3 Seiten — S2 lief um 22 % über |
| **6,7 pt** | **2 Seiten, S2 zu 98 % gefüllt** ← gewählt |
| 6,4 pt | 2 Seiten, 97 % |
| 6,1 pt | 2 Seiten, 94 % |

Zusätzlich global gespart, ohne Inhalt zu streichen:
`abovedisplayskip`/`belowdisplayskip` auf 1,1 mm, `jot` auf 1,6 pt, beide TikZ-Bilder
auf 82 % bzw. 86 % skaliert.

**Bis hierher wurde nichts gestrichen.** Ob 6,7 pt für die restlichen vier Seiten reicht,
steht erst fest, wenn S3–S6 gebaut sind.

---

## Vollständigkeitsgrenze

Ohne `BAUELEMENTE_KI_MASTER.zip` (71 MB, Upload-Limit) sind „alle Vorkommen" die,
die der Bauplan namentlich aufzählt (§2 Aufgabenlisten, §3 Häufigkeitstabellen,
§8 Inhaltsliste). Aufgaben, die in den PDFs stehen, aber im Bauplan nicht erwähnt sind,
können hier nicht erfasst sein. Die Häufigkeitsangaben in den Quellenkürzeln
(z. B. „6×") sind aus den Bauplan-Tabellen gezählt.

---

## Umbau auf Themen-Gruppierung (Vorgabe: alle Alternativen an einem Platz)

Gruppierungseinheit ist jetzt der **Aufgabentyp**, nicht das Bauelement. Alle Vorkommen
eines Typs aus allen Übungen und Klausuren stehen in einem Kasten nebeneinander.

Konkret zusammengezogen:

| Sammelblock | vorher verstreut auf | Quellen im Kasten |
|---|---|---|
| §1.5 Größenordnungsfragen | S1 Faktenblock (Teil) | Ü1 A3 · PK13 A2 · BA A1–A5 · Kl09 · Kl10 |
| §1.6 Licht & Wellenlängen | S1 Faktenblock (Teil) | PK-I A1 · PK13 A1 · Kl10 A24/25 |
| §2.3 Halbleiter/Dotierung/Leitung | S1 Faktenblock + S1 Definitionen | Ü1 A2 · Ü4 A3 · PK13 A1 · Kl09/10/11 |
| §2.4 Bauelemente in einem Satz | S1 Faktenblock | PK-I A1 · PK13 A1 · BA · Kl11 · Kl12 |
| §2.5 Gegenkopplung | war für S5 geplant | alle 6 Altklausuren · Ü8 A4 · BA B8 |

Antworten sind laut Entscheidung **ausformuliert** (ganze Sätze zum direkten Abschreiben),
nicht als Stichpunkte.

### Layout-Umbau: durchlaufender Spaltenfluss

Erzwungene Seitenumbrüche zwischen Themen erzeugten halbleere Seiten. Gemessen:

| Aufbau | Füllgrad je Seite |
|---|---|
| je Thema eine Seite (`\clearpage`) | 85 % · 54 % · 95 % = 3 Seiten |
| **ein Spaltenfluss, Abschnittsbanner** | **97 % · 97 % · 56 % = 2,5 Seiten** |

Gleicher Inhalt, **eine halbe Seite gespart**. Themen bleiben trotzdem zusammen, weil die
Rezeptkästen selbst nicht umbrechen (`breakable=false`); `\Needspace` verhindert, dass ein
Abschnittsbanner allein am Spaltenfuß stehenbleibt.

**Stand des Seitenbudgets:** Teil A + Halbleiter belegen 2,5 der 6 Seiten. Für Diode,
Diodenschaltungen, MOSFET/CMOS/OPV und Bipolartransistor bleiben 3,5 Seiten.
Der Bauplan hatte dafür 4 Seiten vorgesehen — es wird also knapp, aber noch nicht
entschieden. Gestrichen ist bis hier nichts.
