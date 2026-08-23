# Handoff: KLAUSURA — Lern-Cockpit für Ingenieurstudiengänge

**Für Claude Code.** Dieses Bündel ist selbsttragend: Wer nicht am Entwurf beteiligt war, kann allein hiermit bauen.

## Was in diesem Ordner liegt

| Datei | Rolle |
|---|---|
| `PROMPT.md` | Text zum Einfügen in Claude Code — startet die Umsetzung |
| `CLAUDE.md` | Projektregeln, die für allen entstehenden Code gelten |
| `IMPLEMENTATION-PLAN.md` | Arbeitspakete P0–P5, ein Paket pro Commit |
| `README.md` | dieses Dokument — Tokens, Screens, Komponenten, Motion, State, vollständiger Profil-Algorithmus |
| `KLAUSURA.dc.html` | interaktiver Prototyp, 15 Screens in Desktop 1180 + Mobile 390×844, 3 Themes mit Fokus-Dunkel |
| `support.js` | Laufzeit des Prototyps (nur zum Öffnen der HTML-Datei nötig, **nicht** übernehmen) |
| `KLAUSURA Richtungen.dc.html` | frühe Richtungs-Exploration, nur historisch |

Prototyp lokal öffnen: `KLAUSURA.dc.html` im Browser. Navigation oben, Theme und Fokus-Dunkel oben rechts. Screen 14 ist interaktiv (Antwort ändern → Profil rechnet neu), Screen 15 ebenfalls (Regeln schalten).

## Auftrag

Die HTML-Dateien sind **Design-Referenz, kein Produktionscode**: Inline-Styles, hartcodierte Beispieldaten, eigene Template-Runtime. Die Designs sind in der Zielumgebung **neu zu bauen** — React, Vue, SwiftUI, Compose, nativ, was im Zielprojekt etabliert ist — mit dessen Patterns, Komponenten und Bibliotheken. Existiert noch keine Umgebung, das passendste Framework wählen. HTML nicht kopieren, sondern übersetzen.

**Fidelity: hoch.** Farben, Typografie, Abstände, Radien, Motion-Kurven und Copy sind final und unten exakt angegeben; die UI soll pixelgenau nachgebaut werden. Alle Zahlen im Prototyp sind erfundene, aber konsistente Beispieldaten eines fiktiven ET2-Studenten — Struktur übernehmen, Werte aus echten Daten speisen.

## Reihenfolge für die Umsetzung

Siehe Abschnitt 13 am Ende. Kurz: Tokens → Komponenten 1–8 → Screen 04 Solve-View → Import + Atlas → Onboarding und Profil-Arithmetik (Abschnitt 8) → restliche Screens → Screens 14/15 als Transparenz- und Kontrollschicht.

## Kein Verhandlungsspielraum

Abschnitt 4 listet die gesetzten Entscheidungen. Sie sind Teil des Produkts, nicht Geschmack: sichtbare Import-Zerlegung statt Spinner, Simulator immer in Fokus-Dunkel, Profil als Arithmetik statt Typologie, Zahlen immer Monospace mit `tabular-nums`, kein Gamification-Vokabular.

---

Diese Datei ist selbsttragend: Sie enthält alles, was zur Implementierung nötig ist — Tokens, Screens, Komponenten, Motion, State und den vollständigen Profil-Algorithmus. Wer nicht am Entwurf beteiligt war, kann allein hiermit bauen.

---

## 1. Überblick

KLAUSURA ist ein Lern-Cockpit für Ingenieurstudierende, das aus **Altklausur-PDFs** einen strukturierten Übungs- und Prüfungsplan macht. Kernidee: Eine PDF wird sichtbar in Aufgabenkarten zerlegt; jede Aufgabe wird unter Zeitbudget gelöst; Rechenwege werden mit der Musterlösung verglichen; aus wiederkehrenden Fehlern entsteht ein Fehlerprofil, das Lernplan und UI-Verhalten steuert.

**Local-First:** Alle Nutzerdaten (Klausuren, Antworten, Profil) liegen lokal. Kein Login-Zwang, kein Server als Voraussetzung für Kernfunktionen. Sync ist optional und nicht Teil dieses Entwurfs.

Zielplattformen im Entwurf: **Desktop 1180 px** (macOS-Fenster) und **Mobile 390×844** (iOS). Jeder der 15 Screens ist in beiden Breiten spezifiziert.

## 2. Über die Design-Dateien

Die HTML-Datei `KLAUSURA.dc.html` in diesem Projekt ist eine **Design-Referenz**, kein Produktionscode. Sie ist ein interaktiver Prototyp, der Aussehen und Verhalten zeigt — mit Inline-Styles, hartcodierten Beispieldaten und einer eigenen Template-Runtime.

**Aufgabe:** Diese Designs in der Zielumgebung **neu bauen** (React, Vue, SwiftUI, Compose, native — was auch immer im Zielprojekt etabliert ist), mit den dort vorhandenen Patterns, Komponenten und Bibliotheken. Existiert noch keine Umgebung, das für das Projekt am besten passende Framework wählen und dort implementieren. HTML nicht kopieren, sondern übersetzen.

## 3. Fidelity

**High-Fidelity.** Farben, Typografie, Abstände, Radien, Motion-Kurven und Copy sind final und in diesem Dokument exakt angegeben. Die UI soll pixelgenau nachgebaut werden, mit den Bausteinen des Zielsystems. Alle Zahlen in Screenshots/Prototyp sind erfundene, aber konsistente Beispieldaten eines fiktiven ET2-Studenten — Struktur übernehmen, Werte aus echten Daten speisen.

## 4. Gesetzte Entscheidungen (nicht neu verhandeln)

1. **Drei Darstellungs-Themes** statt drei separater Produkte: `Laborgerät`, `Schweizer Fahrplan`, `Cockpit HUD`. Jedes mit Hell- und Fokus-Dunkel-Variante. Umschaltbar zur Laufzeit. Das Zielprojekt darf sich auf **ein** Theme festlegen — dann `Laborgerät / hell` als Standard.
2. **Import-Zerlegung ist eine sichtbare Animation**, keine Fortschrittsanzeige mit Spinner. Der Nutzer sieht, wie die PDF in Karten zerfällt.
3. **Der Simulator läuft in Fokus-Dunkel**, immer, unabhängig vom gewählten Theme.
4. **Profil = Arithmetik, keine Typologie.** Keine „Lerntypen"-Labels; jede UI-Regel hängt an einer nachlesbaren Achsen-Schwelle und ist einzeln abschaltbar.
5. **Zahlen sind immer `tabular-nums`** und in Monospace. Punkte, Zeiten, Ohm-Werte, Prozente.
6. **Kein Gamification-Vokabular** (keine XP, Level, Konfetti). Feedback nennt zuerst den Ort eines Fehlers, dann die Wertung.

## 5. Design-Tokens

### 5.1 Farbe

Semantische Rollen, pro Theme und Modus. Zielprojekt sollte diese als Tokens/Variablen anlegen und **nie** direkte Hex-Werte in Komponenten schreiben.

| Rolle | Bedeutung |
|---|---|
| `paper` | App-Grund, außerhalb der Flächen |
| `panel` | ruhige Flächen, Kopf-/Fußleisten |
| `chrome` | Karten, Eingabeflächen, Vordergrund |
| `head` | Kopfleiste (kann invertiert sein, s. Fahrplan) |
| `grid` | Platzhalter-/Rasterflächen (Skizzen, Schmierblatt) |
| `rule` | 1-px-Hairlines, alle Trenner |
| `ink` | Text, Werte, aktive Zustände |
| `ink60` | Labels, sekundärer Text |
| `ink30` | deaktiviert, leere Zellen |
| `track` | Hintergrundbahn von Ringen/Balken |
| `signal` | Aktion, laufende Zeit, aktueller Fokus |
| `warn` | Zeitwarnung ab 70 % Budget |
| `over` | überzogen, Abweichung, Fehler |
| `ok` | abgegeben, bestanden, beherrscht |

**Laborgerät / Oszilloskop** — Schriften: IBM Plex Sans + IBM Plex Mono, `radius: 2px`

| Rolle | hell | dunkel (Fokus) |
|---|---|---|
| paper | `#EFEFEC` | `#0B0C09` |
| panel | `#F7F7F4` | `#111310` |
| chrome | `#FFFFFF` | `#141612` |
| head | `#FFFFFF` | `#141612` |
| grid | `#FBFBF9` | `#101209` |
| rule | `#E6E6E1` | `#26281F` |
| ink | `#14150F` | `#F2F2EC` |
| ink60 | `#6B6B66` | `#8E9086` |
| ink30 | `#B4B4AE` | `#4A4C44` |
| track | `#E6E6E1` | `#26281F` |
| signal | `#FF5A00` | `#FF7A2E` |
| warn | `#B45309` | `#E0A64A` |
| over | `#C2280F` | `#FF5240` |
| ok | `#2F6B3A` | `#5FBF7A` |
| elev | `0 1px 2px rgba(20,21,15,.08)` | `0 2px 10px rgba(0,0,0,.5)` |

**Schweizer Fahrplan** — Helvetica Neue + JetBrains Mono, `radius: 0px`

| Rolle | hell | dunkel |
|---|---|---|
| paper | `#EDEDED` | `#000000` |
| panel | `#F2F2F2` | `#0B0B0B` |
| chrome | `#FFFFFF` | `#111111` |
| head | `#0B0B0B` (invertiert) | `#000000` |
| grid | `#F7F7F7` | `#0E0E0E` |
| rule | `#DCDCDC` | `#242424` |
| ink | `#0B0B0B` | `#FFFFFF` |
| ink60 | `#767676` | `#8A8A8A` |
| ink30 | `#B0B0B0` | `#4A4A4A` |
| track | `#D2D2D2` | `#242424` |
| signal | `#F26A1B` | `#FF8A2B` |
| warn | `#A85B10` | `#E2A93E` |
| over | `#CC1F0F` | `#FF4B36` |
| ok | `#186A32` | `#4FC06E` |
| elev | `0 2px 0 rgba(11,11,11,.10)` | `0 2px 0 rgba(0,0,0,.6)` |

**Cockpit HUD** — Space Grotesk + Space Mono, `radius: 4px`

| Rolle | hell | dunkel |
|---|---|---|
| paper | `#E9EBEE` | `#07080A` |
| panel | `#F1F2F4` | `#0E1013` |
| chrome | `#FFFFFF` | `#14171B` |
| head | `#FFFFFF` | `#0E1013` |
| grid | `#F6F7F9` | `#101317` |
| rule | `#DDE0E5` | `#23262C` |
| ink | `#0E1013` | `#F4F6F8` |
| ink60 | `#71757E` | `#8B9099` |
| ink30 | `#AFB3BB` | `#4C515A` |
| track | `#DDE0E5` | `#23262C` |
| signal | `#FF6B2C` | `#FF6B2C` |
| warn | `#B05616` | `#E7A84D` |
| over | `#C42B12` | `#FF5340` |
| ok | `#1F6B4A` | `#4FC58E` |
| elev | `0 2px 8px rgba(14,16,19,.10)` | `0 4px 16px rgba(0,0,0,.6)` |

**Textfarbe auf `signal`-Flächen:** `#FFFFFF`, außer im HUD-Theme: `#0E1013`.

**Getönte Flächen:** Auswahl-/Aktivzustände sind `signal` mit Alpha `0.05` (hell) bzw. `0.10–0.12` (dunkel), plus `inset 3px 0 0 signal` als linke Kante. Fehler-Hintergründe: `over` mit Alpha `0.05` hell / `0.12` dunkel.

### 5.2 Typografie

Zwei Familien pro Theme: eine Sans für Prosa und Überschriften, eine Mono für **alle Zahlen, Labels, Codes und Formeln**. Labels sind durchgehend Großbuchstaben mit weitem Sperrsatz.

| Token | Größe / Zeile | Weight | Letter-spacing | Verwendung |
|---|---|---|---|---|
| `display-34` | 34 / 1.18 | 600 | `-.025em` | Onboarding-Fragen |
| `display-32` | 32 / 1.1 | 600 | `-.02em` | Ergebniswerte |
| `num-26` (mono) | 26 / 1.05 | 600 | `-.02em` | Timer, tabular-nums |
| `title-24` | 24 / 1.2 | 600 | `-.02em` | Screen-Titel im Produkt |
| `num-22` (mono) | 22 | 400 | — | Antwortfeld, tabular-nums |
| `title-19/18` | 19–18 / 1.3 | 600 | `-.01em` | Kartentitel, Sektionstitel |
| `body-16` | 16 / 1.4 | 500 | — | Optionstitel |
| `body-15` | 15 / 1.6 | 400 | — | Hinweistexte |
| `body-14` | 14 / 1.65 | 400 | — | Aufgabentext, Prosa |
| `body-13` | 13 / 1.5 | 400/500 | — | Tabellenzellen, Nebentext |
| `body-12` | 12 / 1.4 | 400 | — | Metazeilen |
| `label-11` (mono) | 11 | 400 | `.14em`, caps | Sektionslabels |
| `label-10` (mono) | 10 | 400 | `.14em`, caps | Kartenköpfe, Nav |
| `label-9` (mono) | 9 | 400 | `.10–.12em`, caps | Tabellenköpfe, Bänder |
| `num-13` (mono) | 13 | 400 | — | Punkte, Werte, tabular-nums |

Regel: `font-variant-numeric: tabular-nums` auf **jedem** Element, das Zahlen zeigt, die sich ändern können.

### 5.3 Spacing

4-pt-Skala: **4, 8, 12, 16, 24, 32, 48**. Häufige Muster: Kartenpolster `16px` mobil / `20–24px` Desktop; Zeilenpolster in Tabellen `11–13px` vertikal, `16–20px` horizontal; Sektionsabstand `20px`; Spaltenabstand `20px` innerhalb eines Screens, `36px` zwischen Desktop- und Mobile-Rahmen im Prototyp (nur Präsentation).

### 5.4 Radius & Elevation

Radius kommt aus dem Theme (`2px` / `0px` / `4px`) — nie hartcodieren. Mobile-Gerätrahmen im Prototyp: `22px` (nur Darstellung). Elevation: genau **eine** Stufe pro Theme (`elev`, s. Tabellen). Karten liegen sonst flach und werden durch 1-px-Hairlines getrennt, nicht durch Schatten.

## 6. Komponenten-Inventar (13)

Jede Komponente wird im Prototyp im Screen „Komponenten" in allen Zuständen gezeigt.

1. **Timer-Ring** — SVG-Ring, Umfang 131.9 (r ≈ 21), `stroke-dasharray` = Umfang, `stroke-dashoffset` = Restanteil. 4 Zustände: `frisch` (Bahn `track`, voller Offset), `in Arbeit` (`signal`), `Warnung ≥ 70 %` (`warn`), `überzogen` (`over`, Offset 0). Daneben die Zeit in `num-26`, darunter ein Label in `label-10`. Bei hoher Prüfungsangst ersetzt ein **Balken** den Ring und die Zahl erscheint erst ab 70 %.
2. **Punkte-Badge** — Monospace `num-13` in 1-px-Rahmen, `3px 8px` Polster, tabular-nums, Format `8,5 P`. Varianten: neutral (`rule`), erreicht (`ok`), verloren (`over`).
3. **Aufgabenkarte** — 1-px-Rahmen, oben eine 3-px-Kante in der Beherrschungsfarbe (`over` < 30, `warn` 30–59, `ok` ≥ 60). Inhalt: Aufgaben-ID (mono, 600), Titel, Themen-Label, Punkte-Badge, Zeitbudget, Beherrschungsbalken mit Prozentwert, Schwierigkeit als 3 aufsteigende Striche, Variantenzahl.
4. **Einheiten-Input** — Zweigeteiltes Feld: Zahlenteil (`num-22`, tabular-nums, links) | 1-px-Trenner | Einheitenteil (mono 15, `ink60`, rechts). Fokus: Rahmen `ink` + `0 0 0 3px signal@16%`. Einheit per Tab wechselbar. **Rechnet Präfixe nie stillschweigend um** — kΩ und Ω sind getrennte Eingaben (Regel aus dem Fehlerprofil).
5. **Formel-Input** — Monospace 14, `line-height: 2`, mit Sonderzeichenleiste (`∥ √ π ω ∫ Σ ^`) als 30×30-Tasten, 1-px-Rahmen, mono 13.
6. **Diff-Zeile** — Grid `44px 1fr 1fr`: Marke (`=` in `ink30` / `≠` in `over`), links eigener Rechenweg, rechts Musterlösung, beide mono 13/1.6, mit 1-px-Trenner. Abweichende Zeilen bekommen `over@5%` Hintergrund und eine erklärende Notiz in `over`, 13/1.5, unter beiden Spalten.
7. **Graph-Knoten** — 1-px-Rahmen in Beherrschungsfarbe, Füllung als horizontaler Fortschritt (Beherrschung in %), Titel 13/500, Voraussetzungs-Label in `label-9`. Kanten: 1-px-Linien, gestrichelt wenn Voraussetzung nicht erfüllt.
8. **Heatmap-Zelle** — quadratische Zelle, Hintergrund `signal` mit Alpha `0.10 + (Wert/Max)·0.6`, Zahl mono 13 tabular-nums in `ink`; Wert 0 zeigt `·` in `ink30` auf transparentem Grund. Zellen trennen sich durch `border-left: 1px rule`, nicht durch Gaps.
9. **Simulator-Leiste** — Reihe aus Aufgaben-Chips (min. 26 px breit, mono 10): aktuell = `signal`-Fläche, bearbeitet = `rule`-Fläche, offen = transparent mit `rule`-Rahmen. Mobil: `flex: 1 1 0` pro Chip, damit die Leiste immer die Breite füllt.
10. **Toast** — `ink`-Fläche, `chrome`-Text, `elev`, 12–14 px Polster, mono-Label + Prosa; Varianten neutral / `ok` / `over`. Erscheint unten, 250 ms ease-out, kein Bounce.
11. **Modal „Abgabe erzwingen"** — `chrome`-Fläche, oben 3-px-Kante in `over`, `elev`, Titel 18/600, Prosa 14/1.6, zwei Aktionen rechts unten (primär `signal`, sekundär nur Rahmen). Erscheint bei Budget + 30 s.
12. **Segmented Control** — 1-px-Rahmen, `overflow: hidden`, Segmente mono 10–11, aktiv = `ink`-Fläche mit `chrome`-Text, inaktiv = transparent mit `ink60`. Übergang 150 ms ease-out. Für Themes, Zustände, Achsen, Frageschritte.
13. **Command-Palette (Desktop)** — `ink`-Rahmen, `chrome`-Fläche, `elev`. Eingabezeile mono 14, darunter Treffer in Zeilen mit Typ-Label (`FORMEL`, `AUFGABE`, `THEMA`, `AKTION`), Titel und Tastenkürzel rechts. Erster Treffer auf `signal@6%`. Öffnet mit `⌘K`; `⌘⏎` gibt ab.

## 7. Screens

Alle Screens existieren in Desktop (1180) und Mobile (390×844). Wo nichts anderes steht: Kopfleiste 52 px hoch, `panel`-Grund, 1-px-Untertrennung, links Wortmarke `KLAUSURA` (mono 13/600, `.16em`), daneben Kontextzeile (mono 11, `ink60`, Format `ET2 · WS 2023 · Altklausur 03`).

### 01 Onboarding „Lernprofil"
**Zweck:** 12 Fragen, danach steht das Profil und damit das UI-Verhalten.
**Layout Desktop:** Fortschritt als **Skala mit Teilstrichen** (12 Striche, jeder dritte 18 px hoch, sonst 11 px; erledigt = `ink`, aktuell = `signal`, offen = `rule`), 20 px Innenabstand oben, 40 px seitlich. Darunter Zeile: Zähler links (`FRAGE 04 VON 12`), Gruppe rechts (`STUDIUM`, `ZEIT`, `DRUCK`, `FEHLER`, `ARBEITSWEISE`, `MOTIVATION`), beide `label-11`. Frage in `display-34` (max. 760 px), Hinweis 15/1.6 in `ink60`, Abstand 14 px. Antworten: Grid `repeat(2, minmax(0,420px))`, Gap 14 px, Abstand nach oben 36 px. Jede Option: Auswahlkästchen 20×20 (1-px-Rahmen, gefüllt `ink` wenn gewählt) + Titel 16/500 + **Wirkungssatz** 13/1.5 in `ink60` („was sich dadurch in der App ändert"). Gewählt: `ink`-Rahmen, `signal@6%`, `inset 3px 0 0 signal`. Fußzeile: „Zurück" (nur Rahmen) links, Tastenhinweis `⏎ WEITER · 1–4 AUSWÄHLEN` mono 11, „Weiter" (`signal`) rechts.
**Schritt 13 = Profil:** Sechs Achsenbalken (Label, Wert in Worten, Balken mit Skalenenden in `label-9`, Warnachsen in `warn`), daneben die Liste der konkreten UI-Änderungen (Tag + Titel + Begründung). Kein „dein Typ", sondern: was verhält sich jetzt anders.
**Mobile:** Eine Frage pro Screen, Optionen gestapelt, Fortschrittsskala oben, Aktion fix unten (Hit-Target ≥ 44 px).

### 02 Import (mit Live-Zerlege-Animation)
**Zweck:** Aus einer PDF werden Aufgabenkarten.
**Drei Zustände:** `Drop` → `Zerlegen` → `Fertig`, im Prototyp per Segmented Control umschaltbar, im Produkt zeitlich.
**Drop:** gestrichelter Rahmen (2 px `rule`), zentriert Prosa + Aktion, darunter „Zuletzt importiert" (3 Zeilen: Fach-Tag, Titel, Meta `6 Aufgaben · 90 P · 120 min`).
**Zerlegen:** Links Seitenvorschau (Höhe 480 px Desktop / 150 px mobil) mit sechs Aufgabenblöcken an festen Positionen (top `8, 92, 152, 212, 300, 386`, Höhe `78, 54, 54, 82, 80, 86`): offen = gestrichelt `rule`, aktiv = gestrichelt `warn`, erkannt = durchgezogen `signal`, Deckkraft 0.45. Eine **Scanlinie** (2 px `signal`, `box-shadow 0 0 14px signal@60%`) wandert in 800 ms `cubic-bezier(.2,.7,.3,1)` zur nächsten Position. Rechts erscheinen die Karten einzeln, je 240 ms, Keyframe `k-cut`: `opacity 0 → 1`, `translateX(-14px) → 0`, `scale(.97) → 1`. Kopf zeigt Dokumentname, Meta (`8 Seiten · Musterlösung erkannt · Zerlegung läuft`), Fortschrittsbalken (Breite = erkannt/gesamt, 800 ms), Statuszeile (`SCHNEIDE A3 …`), Seitenzähler, Punktesumme.
**Fertig:** Balken in `ok`, Status `FERTIG · 6 KARTEN`, Aktionen „Zum Atlas" / „Erneut abspielen".

### 03 Aufgaben-Atlas
Kartenraster aller Aufgaben, sortiert nach Beherrschung aufsteigend (schwächste zuerst) — Sortierung je Profil abweichend (s. Presets). Desktop: 3 Spalten, Gap 16 px. Mobile: eine Spalte, kompaktere Karte ohne Variantenzeile. Kopfzeile mit Filter-Segmenten (Fach, Thema, Beherrschung) und Zähler.

### 04 Solve-View — 5 Zustände
**Zweck:** eine Teilaufgabe lösen.
**Aufbau Desktop:** Kopfband 74 px: Timer-Ring + Zeit + Label | 1-px-Trenner | Aufgaben-ID (mono 12/600) + Titel (15/600) + Metazeile (Punkte-Badge, Thema, Zeitbudget) | rechts Statuschip (Punkt + Label, Rahmen und Text in Statusfarbe, Fläche = Farbe@8 %). Optionales Banner unter dem Kopf (Fläche = Statusfarbe@10 % hell / 16 % dunkel) mit Text links und Zähler rechts. Hauptfläche Grid `1fr 1fr`, min. 520 px: **links** Aufgabenstellung (Label, Prosa 14/1.65, Formelzeichen in Mono, Skizzenfläche 230 px auf `grid`-Grund mit Mono-Platzhalter, darunter drei Chips „Formelsammlung", „Original-PDF", „Varianten"); **rechts** Ergebnisfeld (Einheiten-Input), Rechenweg-Feld (mono 13, zeilenweise, Caret), Schmierblatt-Fläche (gestrichelt, min. 120 px), Fußzeile mit Abgabe-Button. Unten Aufgabenleiste: alle Aufgaben als Chips + `44 / 90 P bearbeitet`.
**Die 5 Zustände** (Timer, Status, Feld, Banner, Button ändern sich gemeinsam):
1. **Frisch** — Ring `track`, Status `OFFEN`, Feld leer mit `rule`-Rahmen, kein Banner, Button inaktiv (`rule`-Fläche, `ink60`).
2. **In Arbeit** — Ring `signal`, Status `IN ARBEIT`, Feld fokussiert (`ink`-Rahmen + `signal@16%`-Ring), Rechenweg wächst zeilenweise, Button `signal` „Abgeben".
3. **Warnung 70 %** — Ring und Zeit in `warn`, Status `ZEIT 70 %`, Banner `warn` mit Resthinweis, sonst wie 2.
4. **Überzogen** — Ring `over`, Zeit `over`, Status `ÜBERZOGEN`, Banner `over` mit Zähler `+2:14`, Button `over` „Jetzt abgeben"; nach + 30 s Modal „Abgabe erzwingen".
5. **Abgegeben** — Ring voll `ok`, Status `ABGEGEBEN`, Feld gesperrt (Rahmen `rule`, Wert in `ink`), Banner `ok` mit Punktzahl, Button `ok` „Rechenweg vergleichen" → Screen 05.
**Mobile:** Kopf mit kleinerem Ring (num-20), Aufgabenstellung und Antwort als zwei Karten untereinander, Aufgabenleiste als volle Chipreihe, Aktion fix unten.

### 05 Rechenweg-Diff
Zwei Spalten „Dein Weg" | „Musterlösung", Zeile für Zeile über Diff-Zeilen-Komponente. Kopf mit Punktbilanz (`6,5 / 8,5 P`) und Sprungmarken zu Abweichungen (`≠ 2`). Notizen erklären den Fehler in Worten, nie nur „falsch". Mobile: Zeilen gestapelt, eigener Weg oben, Musterlösung darunter eingerückt, Abweichung mit `over@5%` markiert.

### 06 Simulator (Fokus-Dunkel)
Immer im Dunkelmodus des aktiven Themes. Kopf: Gesamtzeit als Ring + verbleibende Aufgaben + Simulator-Leiste. Grid `1fr 1fr 280px` mit ausklappbarem **Hilfsmittel-Panel** rechts (Formelsammlung, erlaubte Hilfsmittel, Nachschlagezeit); geschlossen wird das Grid `1fr 1fr`, Umschalter im Kopf (aktiv = `ink`-Fläche). Keine Auswertung bis zum Ende. Mobile: Hilfsmittel als Sheet über die volle Höhe.

### 07 Ergebnis
Große Punktzahl (`display-32`), Bestehensabstand statt Note als Standardaussage, Zeit-pro-Punkt-Kurve, Aufgabenliste mit erreichten/möglichen Punkten und Fehlerklassen-Tags, Verlaufsliste früherer Läufe (`04. AUG · 44 % · 39,5 P`) mit Delta in `ok`/`over`.

### 08 Wissensgraph / Themen-Heatmap
Knoten in 3 Spalten (x-Positionen 24 / 280 / 536, y-Abstand 110–120 px), Kanten als 1-px-Linien, gestrichelt bei unerfüllter Voraussetzung. Knotenfarbe nach Beherrschung. Rechts Detailspalte: gewähltes Thema, Voraussetzungskette, blockierte Klausurpunkte, „Diese Sitzung schließt die Lücke". Mobile: Liste statt Graph, gruppiert nach Voraussetzungsebene.

### 09 Prüfungsradar
Matrix Thema × Prüfungsjahr, Zellen = Heatmap-Zelle mit Punktzahl (`·` wenn nicht geprüft). Zeilensumme rechts, Jahresspalten mit Kopf `WS 23`, `WS 22` … Aussage: welches Thema wiederkehrt und mit wie vielen Punkten. Braucht mindestens 3 Klausuren (sonst Leerzustand 09).

### 10 Tagesplan
18-Tage-Skala oben (Teilstriche: heute 24 px `signal`, Simulationstage 18 px `ink`, sonst 10 px `rule`). Darunter Blöcke des heutigen Tages: Zeit, Dauer, Titel, **Begründung** („warum heute"), Tag-Chips, Aktion rechts; aktueller Block mit `signal`-Rahmen und `signal@5%`. Darunter Wochenausblick als Zeilen (`MI · Biegespannung, 3 Varianten · 2 h`). Rückwärtsplanung von der Klausur, mit Pufferabenden.

### 11 Formelsammlung
Linke Liste: Formel in Mono (`σ_b = M_b / W_b`), Name, Beherrschungs-Badge in Beherrschungsfarbe; gewählte Zeile `signal@5%` + `inset 3px 0 0 signal`. Rechts: Einheitenzerlegung in 3 Spalten (Symbol, Einheit, Bedeutung; getrennt durch `border-left`), darunter „Verwendet in" mit Aufgaben-ID, Titel, Punkten, Jahr.

### 12 Fehler-DNA-Profil
Oben 8-Wochen-Streifen: pro Woche ein gestapelter Balken, Segmenthöhe = Vorkommen × 5 px (mobil × 2.2), Segmentfarbe = Fehlerklasse. Darunter Tabelle `60px 1fr 90px 110px 120px`: Code (mono 12/600, Klassenfarbe), Klasse + Beispiel, Anzahl, verlorene Punkte, Trend (`▲ +12 %` in `over` / `▼ −19 %` in `ok`). Darunter „Was daraus folgt": drei Regeln mit Code, Titel, Begründung.

### 13 Leerzustände (für 01, 03, 08, 09)
Jeder Leerzustand zeigt ein **Skelett des künftigen Inhalts** auf `grid`-Grund (Skala / Karten / Graph / Matrix), darüber Nummer + Screenname in `label-10`, Titel 18–24/600, Prosa 13–14/1.6 in `ink60`, eine primäre Aktion und eine Mono-Fußnote (`0 VON 14 THEMEN BEWERTET`). Kein Illustrationsschmuck, keine leeren Sprüche — jeder Leerzustand nennt die Bedingung, unter der er verschwindet.

### 14 Profil-Logik („Von 12 Fragen zum Profil")
**Zweck:** Der Algorithmus als Screen — nachlesbar, statt Blackbox. Drei gestapelte Karten (Desktop 1180, Gap 20 px), Achsenwahl über Segmented Control im Kopf.
1. **Beitragsmatrix** — Grid `300px repeat(6, 1fr)`. Zeilen: 12 Fragen (Nummer mono 11, Kurztitel 13/500, gewählte Antwort 12 in `ink60`). Spalten: 6 Achsen (Kopf `label-9`, zentriert, gewählte Spalte `signal@6%`). Zellen: signierte Punktverschiebung (`+22`, `−12`, `·`), Hintergrund = Achsenfarbe mit Alpha `0.08 + |p|/22 · 0.42` (`signal` für positiv, `ink` für negativ), Text immer `ink` (Kontrast!), tabular-nums. Fußzeile: Achsenwert (mono 17/600, `warn` bei kritischen Bändern) + Bandname; Hinweiszeile: „Frage 01 vergibt keine Punkte."
2. **Herleitung** (Grid `1fr 420px`) — links die beitragenden Antworten der gewählten Achse, nach Betrag sortiert: Nummer, Antwort 14/500, Frage-Kurztitel 12 in `ink60`, Betragsbalken (6 px, Breite = |p|/22), Punktwert rechts (mono 14, `signal` positiv / `ink60` negativ); stärkster Beitrag auf `signal@5%`. Fuß: `BASIS 50 · SUMME +32` und Achsenwert in mono 22/600. Darunter die Bänder als Zeilen (Bereich mono 11, Name 13; aktives Band mit `ink`-Rahmen, `signal@6%`, `inset 3px 0 0 signal`) plus Hinweis auf 5 Punkte **Hysterese**. Rechts: alle sechs Achsen als klickbare Liste mit Balken, Bandname und Wert; Kopf zeigt `n REGELN AKTIV`.
3. **Schwellenwerk** — Grid `170px 78px 108px 1fr 74px`, Kopfzeile in `label-9`: Achse (+ `IST 82`), Schwelle (`≥ 71`, `≤ 35`, `36 – 65`), Bereich-Tag (`TIMER`, `FEEDBACK`, …), Verhalten im UI (13/1.45), Status-Chip `GREIFT` (`ok`-Rahmen) / `INAKTIV` (`rule`-Rahmen, `ink30`-Text; ganze Zeile transparent statt `chrome`).
**Rückwärts-Ansicht (interaktiv):** Über der Matrix steht eine Leiste mit sechs Achsenkacheln: aktueller Wert (mono 20/600, `signal` sobald abweichend), Delta zum Ausgangsprofil (`+7`, `±0`), Balken mit einem 1-px-Strich in `ink` an der Position des Ausgangswerts, Bandname und ggf. `BAND GEWECHSELT` (`signal`) / `BAND GEHALTEN` (`warn`, Hysterese). Kopf der Leiste zeigt `n ANTWORTEN GEÄNDERT · n REGELN KIPPEN · n VON HYSTERESE GEHALTEN` und die Aktion `ZURÜCKSETZEN`.
Jede Matrixzeile ist anklickbar und klappt die vier Antwortoptionen der Frage auf (Auswahlkästchen 14×14, Titel 13/500, rechts die Wirkung als Mono-Kette `+22 ANGST · −16 TOL`, gewählte Option `signal@5%`). Eine Auswahl rechnet Achsenwerte, Bänder, Herleitung und Schwellenwerk sofort neu; die geänderte Antwort steht in der Zeile in `signal`. Im Schwellenwerk bekommen gekippte Regeln `inset 3px 0 0 signal` und eine Notiz „Kippt an / Fällt weg durch die geänderte Antwort", von der Hysterese gehaltene Regeln den Status `HÄLT` (`warn`) mit dem Abstand zur Schwelle. Damit ist die Arithmetik nicht nur nachlesbar, sondern prüfbar.
**Mobile:** Achsenliste, darunter Herleitung der gewählten Achse (Grid `34px 1fr 52px`) — jede Herleitungszeile ist antippbar und klappt dieselben Antwortoptionen auf. Summenzeile, fixe Fußleiste mit `n REGELN AKTIV` + Aktion „Regeln ansehen" (führt zu Screen 15).

### 15 Einstellungen · Regelwerk
**Zweck:** Die Umkehrbarkeit aus Abschnitt 8.4 als Screen. Jede der 10 Regeln einzeln abschaltbar, jede mit ihrer Herleitung.
**Desktop 1180:** Grid `1fr 340px`. Links Regelliste, Zeile = Grid `104px 1fr 132px 44px`: Bereichs-Tag (mono 10, `signal` wenn greifend, sonst `ink30`), Regeltitel (14/500; durchgestrichen wenn abgeschaltet) + Herleitung in Mono 11 („weil Prüfungsangst 82, Schwelle ≥ 71"; `warn`, wenn die Hysterese sie hält) + Wirkungsort (12, `ink30`, „Wirkt in: Solve-View, Simulator"), Status-Chip `GREIFT` (`ok`) / `UNTER SCHWELLE` (`rule`/`ink30`) / `ABGESCHALTET` (`over`), Schalter 40×22 (Bahn `ink` wenn an, Knopf 16×16, 150 ms ease-out; Regeln unter Schwelle bei `opacity .45` und nicht schaltbar). Aktive Zeilen liegen auf `chrome`, inaktive transparent.
Rechte Spalte: **Bilanz** (greifen / abgeschaltet / unter Schwelle, Werte mono 20/600), **Abgeschaltet** (Liste oder der Satz „Keine Regel abgeschaltet."), **Was der Schalter nicht tut** — eine abgeschaltete Regel ändert das Profil nicht; Achsenwert und Herleitung bleiben, nur das Verhalten entfällt. Wer das Profil verschieben will, ändert in Screen 14 eine Antwort.
**Mobile:** Kopf, Liste als Grid `1fr 44px` (Tag, Titel, Herleitung, Schalter), fixe Fußleiste mit `n VON 10 REGELN AKTIV` und Aktion „Herleitung" (führt zu Screen 14).
**Persistenz:** Overrides gehören zu den lokal gespeicherten Daten (Abschnitt 10) und überleben jede Neuberechnung des Profils.

## 8. Der Profil-Algorithmus (vollständig)

Kein Klassifikator, sondern additive Punktvergabe. **Basis jeder Achse: 50.** Jede Antwort verschiebt eine oder mehrere Achsen um einen festen Betrag. Achsenwert = `clamp(0, 50 + Σ Beiträge, 100)`.

### 8.1 Achsen und Bänder

| Achse | Skalenenden | Bänder (oberste Grenze → Name) |
|---|---|---|
| Prüfungsangst | GELASSEN → HOCH | ≤ 40 gelassen · ≤ 70 mittel · ≤ 100 hoch |
| Rechenweg-Sorgfalt | FLÜCHTIG → SORGFÄLTIG | ≤ 35 flüchtig · ≤ 65 mittel · ≤ 100 sorgfältig |
| Zeitdruck-Toleranz | NIEDRIG → HOCH | ≤ 35 niedrig · ≤ 65 mittel · ≤ 100 hoch |
| Vorbereitungszeit | UNTER 7 TAGE → ÜBER 28 T. | ≤ 35 knapp · ≤ 70 ausreichend · ≤ 100 komfortabel |
| Formelsammlung-Routine | UNGEÜBT → ROUTINIERT | ≤ 40 ungeübt · ≤ 75 gut · ≤ 100 routiniert |
| Selbsteinschätzung | ZU STRENG → ZU MILDE | ≤ 40 zu streng · ≤ 65 realistisch · ≤ 100 zu milde |

„Prüfungsangst" und „Zeitdruck-Toleranz" sind **Warnachsen**: Werte in den Extrembändern werden in `warn` gesetzt, weil sie mehrere UI-Regeln auslösen.

### 8.2 Die 12 Fragen, ihre Antwortoptionen und Wirkungen

Jede Option nennt im UI ihre Konsequenz — das ist Teil der Copy, nicht Beiwerk.

| # | Gruppe | Frage | Optionen (Wirkung) |
|---|---|---|---|
| 01 | STUDIUM | Welchen Studiengang schreibst du? | Elektrotechnik (j statt i) · Maschinenbau (Vorzeichenkonvention Statik) · Wirtschaftsing. (gemischte Last) · Informatik (diskrete Mathematik) |
| 02 | STUDIUM | Wie viele harte Klausuren stehen an? | 1–2 (Tiefe vor Breite) · 3 (zwei Fächer/Tag) · 4–5 (Rotation, kurze Blöcke) · 6+ (nur Klausurrelevantes) |
| 03 | ZEIT | Wie viele Tage bis zur ersten Klausur? | unter 7 (nur Simulationen) · 8–21 (Aufbau, dann Simulationen) · 22–35 (vollständiger Aufbau) · über 35 (Wiederholungszyklen) |
| 04 | ZEIT | Stunden pro Tag, realistisch? | bis 2 h · 2–4 h · 4–6 h · mehr als 6 h (Pausen erzwungen) |
| 05 | DRUCK | Was passiert kurz vor der Klausur? | Ich blockiere (Timer als Balken) · hektisch (Warnung früher) · fokussiert (harte Zeitkanten) · kein Unterschied |
| 06 | DRUCK | Wie wirkt eine ablaufende Uhr? | treibt an (Zahl groß) · macht nervös (Ring ohne Zahl) · ignoriere sie (Ton bei 70 %) · schaue ständig hin (Zeit nur an Schwellen) |
| 07 | FEHLER | Woran scheitern Rechnungen? | Ansatz fehlt · Einheiten/Zehnerpotenzen · Rechenfehler unter Druck · Zeit reicht nicht |
| 08 | FEHLER | Umgang mit falschen Ergebnissen? | sofort Lösung · nochmal rechnen · Rechenweg vergleichen · meist gar nicht |
| 09 | ARBEITSWEISE | Wie rechnest du am liebsten? | Papier, dann eintippen · digital Schritt für Schritt · im Kopf · Tablet + Stift |
| 10 | ARBEITSWEISE | Formelsammlung souverän? | blind · langsam · finde nichts · keine erlaubt |
| 11 | MOTIVATION | Was hilft dranzubleiben? | Serien · Punktprognose · nur nächste Aufgabe · Vergleich mit anderen |
| 12 | MOTIVATION | Was wäre ein guter Ausgang? | Bestehen egal wie · solide Note · Bestnote · weiß nicht |

### 8.3 Beitragsmatrix (Beispielprofil des Prototyps)

Die Beträge gehören zur **gewählten Option**, nicht zur Frage. Unten die Belegung des im Prototyp gezeigten fiktiven Profils; die vollständige Tabelle Beitrag(Frage, Option) → Achsen liegt im Prototyp als `LOGIC_Q` (12 Fragen × 4 Optionen) und ist die Referenzbelegung für das Produkt.

| # | gewählte Antwort | angst | sorg | tol | zeit | form | selbst |
|---|---|---|---|---|---|---|---|
| 01 | Elektrotechnik | · | · | · | · | · | · |
| 02 | 4–5 Klausuren | · | · | · | −6 | · | · |
| 03 | 8–21 Tage | · | · | +4 | +14 | · | · |
| 04 | 2–4 h | · | +2 | · | +2 | · | · |
| 05 | Ich blockiere, Kopf leer | +22 | · | −16 | · | · | · |
| 06 | Macht mich nervös | +10 | · | −12 | · | · | · |
| 07 | Einheiten, Zehnerpotenzen | +2 | +6 | · | · | · | · |
| 08 | Rechenweg vergleichen | −4 | +10 | · | · | · | −6 |
| 09 | Papier, dann eintippen | · | −8 | · | · | +3 | · |
| 10 | Meistens, aber langsam | · | · | +2 | · | +18 | · |
| 11 | Nur die nächste Aufgabe | +2 | · | · | · | · | +2 |
| 12 | Bestehen, egal wie | · | −6 | · | · | · | −12 |
| **Wert** | Basis 50 + Summe | **82** | **54** | **28** | **60** | **71** | **34** |
| **Band** | | hoch | mittel | niedrig | ausreichend | gut | zu streng |

Frage 01 vergibt bewusst keine Punkte: sie setzt Fachkonventionen (j statt i, Vorzeichen in der Statik) und darf das Verhaltensprofil nicht verfälschen.

### 8.4 Schwellenwerk: Achse → UI-Regel

| Achse | Schwelle | Bereich | Verhalten im UI | im Beispiel |
|---|---|---|---|---|
| Prüfungsangst | ≥ 71 | TIMER | Zeit als Balken, Countdown-Zahl erst bei 70 % | greift |
| Prüfungsangst | ≥ 71 | FEEDBACK | Fehler zuerst als Ort, dann als Wertung | greift |
| Prüfungsangst | ≤ 40 | TIMER | Voller Countdown, harte Zeitkanten | inaktiv |
| Zeitdruck-Toleranz | ≤ 35 | DRUCK | Kein Streak, keine Serien-Erinnerung | greift |
| Zeitdruck-Toleranz | ≥ 66 | VERGLEICH | Anonyme Kohorten-Perzentile sichtbar | inaktiv |
| Rechenweg-Sorgfalt | 36 – 65 | SCHRITT | Zwischenergebnis-Check je Rechenschritt | greift |
| Rechenweg-Sorgfalt | ≥ 66 | DIFF | Diff-Ansicht ist Standard nach Abgabe | inaktiv |
| Formelsammlung-Routine | ≥ 70 | HILFSMITTEL | Panel startet geschlossen, Nachschlagezeit wird gemessen | greift |
| Vorbereitungszeit | 36 – 70 | PLAN | 18 Tage rückwärts geplant, 2 Pufferabende | greift |
| Selbsteinschätzung | ≤ 40 | PROGNOSE | Abstand zur 4,0 statt Notenband | greift |

**Hysterese:** Ein Bandwechsel wird erst wirksam, wenn der Achsenwert die Schwelle um 5 Punkte überschreitet. Ohne das kippt das UI bei einer einzigen geänderten Antwort hin und her.

**Umkehrbarkeit:** Jede Regel ist in den Einstellungen einzeln abschaltbar und nennt dort ihre Herleitung („weil Prüfungsangst 82, Schwelle 71"). Regeln dürfen nie stillschweigend greifen.

### 8.5 Profil-Presets (vier Bündel als Referenz)

**Hohe Prüfungsangst** — blockiert kurz vor Klausuren, nervös bei laufenden Uhren, zu strenge Selbsteinschätzung:
Balken statt Countdown-Zahl · Ort vor Wertung im Feedback · kein Streak, keine Serien-Push · Aufwärmaufgabe vor jedem Simulationslauf · Prognose als Abstand zur Bestehensgrenze, nicht als Note.

**Zeitoptimierer** — fokussiert unter Druck, Zeit reicht selten, will Bestnote:
Countdown groß mit Teilaufgaben-Budget (Punkte × Sekunden/Punkt) · harte Zeitkante (überzogene Aufgabe wird grau und wandert nach hinten) · Auswertung beginnt mit Sekunden-pro-Punkt · Simulationen doppelt gewichtet · Vollpunktzahl-Analyse je Aufgabe.

**Lückenschließer** — vier Wochen Zeit, viele rote Themen, Ansatzfehler dominieren:
Atlas sortiert nach blockierten Punkten (nicht nach schwächster Beherrschung) · Teilschritt-Hinweise nach 3 Minuten Stillstand, Verfahren statt Ergebnis · Wissensgraph ist Startscreen · Simulation erst ab 40 % Gesamtbeherrschung · Herleitung immer aufgeklappt.

**Letzte 72 Stunden** — unter 3 Tage, alles auf Bestehen, hoher Druck akzeptiert:
Nur Simulationen und Wiederholung, kein neues Thema · Atlas zeigt Themen ab 50 Beherrschung zuerst, rote werden ausgeblendet (nicht gelöscht) · Fokus-Dunkel ist Standard, volle Klausurdauer, keine Auswertung bis zum Ende.

## 9. Interaktionen & Motion

| Element | Auslöser | Dauer | Kurve | Reduce-Motion-Fallback |
|---|---|---|---|---|
| Timer-Ring | jede Sekunde | 1000 ms | linear (Zeit lügt nicht) | Ring statisch, Zahl springt sekündlich |
| Schwelle 70 % | Budget 70 % verbraucht | 180 ms | ease-out | Farbe + Wortmarke sofort, kein Puls |
| Aufgabe einsortieren (Import) | Zerlegung erkennt Aufgabe | 240 ms | `cubic-bezier(.2,.7,.3,1)` | Karte erscheint an Zielposition |
| Scanlinie (Import) | nächste Aufgabe | 800 ms | `cubic-bezier(.2,.7,.3,1)` | Linie springt |
| Diff-Zeile aufklappen | Klick auf Abweichung | 200 ms | ease-out | sofort offen |
| Abgabe erzwingen | Budget + 30 s | 250 ms | ease-out, kein Bounce | Overlay ohne Bewegung |
| Fokus-Dunkel-Wechsel | Simulator-Start | 220 ms | ease-out | harter Themewechsel |
| Bestanden-Moment | Simulation bestanden | 900 ms, einmalig | Spring, gedämpft | Ergebniswert erscheint groß, statisch |
| Segment-/Tab-Wechsel | Klick | 150 ms | ease-out | sofort |
| Fokusring Eingabefeld | Fokus | 180 ms | ease-out | sofort |

`@media (prefers-reduced-motion: reduce)` setzt alle Dauern auf 1 ms; die Zielzustände müssen ohne Bewegung vollständig lesbar sein.

**Tastatur (Desktop):** `⌘K` Command-Palette · `⌘⏎` abgeben · `Tab` wechselt Einheit im Ergebnisfeld · `1–4` wählt Onboarding-Option · `⏎` weiter. Alle Hinweise stehen sichtbar in Mono-Fußzeilen.

**Hit-Targets Mobile:** nie unter 44 px. Primäraktion in fixer Fußleiste, `chrome`-Fläche mit 1-px-Oberkante.

## 10. State

| State | Typ | Bedeutung |
|---|---|---|
| `theme` | `'labor' \| 'fahrplan' \| 'hud'` | Darstellung; im Produkt Einstellung, kein Screen-State |
| `dark` | boolean | Fokus-Dunkel; im Simulator erzwungen |
| `solveState` | 0–4 | frisch · in Arbeit · Warnung 70 % · überzogen · abgegeben |
| `importPhase` | 0–2 | Drop · Zerlegen · Fertig |
| `cutCount` | 0–6 | erkannte Aufgaben während der Zerlegung (treibt Animation) |
| `aidOpen` | boolean | Hilfsmittel-Panel im Simulator |
| `onbStep` | 1–13 | Frageschritt, 13 = Profilergebnis |
| `axis` | Achsen-Key | gewählte Achse in Screen 14 |
| `sels` | `number[12]` \| null | gewählte Antwortoption je Frage; `null` = Ausgangsprofil aus dem Onboarding |
| `openQ` | Index \| null | aufgeklappte Frage in der Beitragsmatrix |
| `off` | `Record<ruleId, true>` | in Screen 15 abgeschaltete Regeln (persistiert) |

**Abgeleitet, nicht gespeichert:** Achsenwerte (aus Antworten), Bänder (aus Achsenwerten), aktive Regeln (aus Bändern + Hysterese), Beherrschungsgrade (aus Antwortverlauf), Tagesplan (aus Klausurdatum, Achsen, Wissensgraph).

**Daten, die persistiert werden müssen:** importierte Klausuren + Aufgabenzerlegung, Antworten und Rechenwege je Versuch, Zeitverbrauch je Teilaufgabe, Onboarding-Antworten, Regel-Overrides (abgeschaltete Regeln), Fehlerklassen-Verlauf. Alles lokal; Schema-Migrationen einplanen, da der Nutzer keine Cloud-Kopie hat.

## 11. Assets

Keine Bild- oder Icon-Assets. Der Entwurf arbeitet ausschließlich mit Typografie, 1-px-Linien, Flächen und SVG-Primitiven (Ring, Balken, Linien). Schaltungsskizzen und Schmierblatt sind **Platzhalterflächen** auf `grid`-Grund mit Mono-Beschriftung — hier gehören später gerenderte Schaltbilder bzw. eine Canvas-/Stift-Fläche hin. Symbole in der Formeltastatur (`∥ √ π ω ∫ Σ ^`) sind Textzeichen, keine Icons.

Schriften: IBM Plex Sans / IBM Plex Mono, Helvetica Neue / JetBrains Mono, Space Grotesk / Space Mono (Google Fonts, Gewichte 400/500/600 bzw. 400/700). Bei nur einem Theme genügt ein Paar.

## 12. Dateien

- `KLAUSURA.dc.html` — vollständiger interaktiver Prototyp: 15 Screens (Desktop + Mobile), 3 Themes mit Dunkelvariante, Token-Screen, Komponenten-Inventar, Motion-Spezifikation, Profil-Presets. Navigation über die Leiste oben; Theme und Fokus-Dunkel oben rechts. Screen 14 und 15 sind interaktiv. **Design-Referenz, kein Produktionscode.**
- `support.js` — Laufzeit des Prototyps. Nur nötig, um die HTML-Datei zu öffnen; nicht Teil der Umsetzung.
- `KLAUSURA Richtungen.dc.html` — frühere Richtungs-Exploration, nur historisch relevant.
- `README.md` — dieses Dokument.

## 13. Empfohlene Umsetzungsreihenfolge

1. Tokens + Typo-Skala im Zielsystem anlegen (ein Theme genügt zum Start).
2. Komponenten 1–8 bauen (Timer-Ring, Badge, Aufgabenkarte, Einheiten-Input, Diff-Zeile, Graph-Knoten, Heatmap-Zelle, Simulator-Leiste).
3. Screen 04 Solve-View mit allen 5 Zuständen — hier hängt das Produkt.
4. Screen 02 Import inkl. Zerlege-Animation, dann 03 Atlas.
5. Screen 01 Onboarding + Profil-Arithmetik (Abschnitt 8) + Regel-Overrides.
6. Screens 05–07, dann 08–12, Leerzustände parallel zu jedem Screen.
7. Screen 14 als Transparenz-Ansicht, sobald die Arithmetik steht — inklusive Rückwärts-Ansicht (Antwort ändern → Achsen und Regeln rechnen live neu).
8. Screen 15 Regelwerk mit Overrides; erst danach dürfen Regeln im Produkt greifen.
