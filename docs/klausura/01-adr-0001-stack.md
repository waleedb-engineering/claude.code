# ADR-0001 · Technologie-Stack

**Status:** akzeptiert · **Datum:** 2026-08 · **Entscheider:** Projektinhaber

## Kontext

Eine Codebase soll macOS, iOS und Android bedienen — alle drei ab v1. Local-First,
also SQLite mit Volltextsuche auf dem Gerät. PDF-Rendering und Canvas-Interaktion
für die Segmentierungs-UI. OCR für Scans und Fotos. Symbolische Äquivalenzprüfung
für den Formelvergleich. Signierte, notarisierte macOS-Auslieferung und
App-Store-Tauglichkeit auf iOS.

Skillbasis des Entwicklers: React Native/Expo, JavaScript/TypeScript, Python, Java,
SQL, Git. Kein Rust, kein Kotlin/Compose, kein Swift. Entwicklung allein.

> **Versionshinweis:** Reifegrad-Aussagen unten beziehen sich auf den Stand bei
> Abfassung. Vor M0 sind die aktuellen Versionen und der Mobile-Support von
> Tauri und Compose Multiplatform erneut zu prüfen — dieser ADR ist dann zu
> revidieren, nicht zu ignorieren.

## Optionen

### Option 1 — Tauri 2 (Rust-Core) + React/TypeScript

Rust-Kern, Systemwebview für die UI (WKWebView auf macOS/iOS, Android WebView),
seit Tauri 2 auch mobile Ziele.

| Kriterium | Bewertung |
|---|---|
| Reifegrad Desktop | sehr gut, produktionserprobt |
| Reifegrad Mobile | jung; deutlich weniger erprobt als der Desktop-Pfad |
| PDF & Canvas | pdf.js im Webview, gute Performance auf Desktop |
| OCR-Anbindung | über Rust-Commands bzw. Swift/Kotlin-Plugins möglich |
| SQLite + FTS | rusqlite / tauri-plugin-sql, voller Zugriff |
| Bundle-Größe | sehr klein (kein mitgeliefertes Chromium) |
| macOS-Signatur | gut unterstützt, Notarisierung dokumentiert |
| App-Store iOS | möglich, aber der am wenigsten begangene Pfad |
| Skillbasis | **schlecht** — Rust ist neu, und der Kern ist Rust |
| Wartbarkeit allein | mittel: zwei Sprachen, Rust-Fehler kosten dich am meisten Zeit |

### Option 2 — Expo/React Native, Desktop über eigene Shell

Expo für iOS/Android. Für macOS entweder React Native macOS (Microsoft) oder
eine getrennte Desktop-Shell (Tauri/Electron) mit React DOM.

| Kriterium | Bewertung |
|---|---|
| Reifegrad Mobile | sehr gut, der Referenzpfad |
| Reifegrad Desktop | RN-macOS hinkt RN-Versionen hinterher und wird von Expo nicht getragen |
| PDF & Canvas | mobil `react-native-pdf`; ein 1180-px-Dichtelayout in RN ist Arbeit *gegen* das Framework |
| OCR-Anbindung | ausgezeichnet über Expo-Module (Vision / ML Kit) |
| SQLite + FTS | `expo-sqlite`, FTS5 verfügbar |
| Bundle-Größe | mobil normal; Electron-Shell wäre groß, Tauri-Shell klein |
| macOS-Signatur | über die gewählte Shell, unproblematisch |
| App-Store iOS | **bester Pfad**, EAS Build deckt es ab |
| Skillbasis | **sehr gut** — genau dein Stack |
| Wartbarkeit allein | gut, solange man RN-macOS meidet |

### Option 3 — Kotlin / Compose Multiplatform

Ein Kotlin-Kern, Compose als UI auf allen Zielen.

| Kriterium | Bewertung |
|---|---|
| Reifegrad Mobile | Android exzellent, iOS inzwischen tragfähig |
| Reifegrad Desktop | JVM-Desktop stabil, aber macOS-untypisches Verhalten in Details |
| PDF & Canvas | Compose Canvas ist stark; PDF-Rendering pro Plattform verschieden |
| OCR-Anbindung | Android nativ; iOS über Interop; macOS/JVM am umständlichsten |
| SQLite + FTS | SQLDelight, sehr gut |
| Bundle-Größe | JVM-Desktop-Bundles sind schwer |
| macOS-Signatur | möglich, Toolchain umständlicher |
| App-Store iOS | machbar |
| Skillbasis | **schwach** — Java hilft der Syntax, nicht den Compose-Idiomen |
| Wartbarkeit allein | mittel bis schlecht ohne Kotlin-Routine |

## Entscheidung

**TypeScript-Monorepo mit reinem Domain-Core und zwei Präsentationsschichten.**

```
packages/core          reines TS · kein IO · kein Framework · in Node testbar
packages/ports         StoragePort OcrPort LlmPort CasPort PdfPort ClockPort
packages/adapters-web  Implementierungen für den Tauri-Kontext
packages/adapters-rn   Implementierungen für den Expo-Kontext
apps/desktop           Tauri 2 + React DOM      → macOS, Layout 1180
apps/mobile            Expo / React Native      → iOS + Android, Layout 390
```

Also: Option 2 für Mobile, Option 1 als Desktop-Shell, verbunden durch einen
Domain-Kern, der von beidem nichts weiß.

## Begründung

**Warum nicht Compose:** die Skillbasis trägt nicht. Ein Solo-Projekt, dessen
schwierigste Teile (Ingest, Verifikation, Bewertung) in einer Sprache entstehen,
die du parallel lernst, scheitert an der Kombination — nicht an einem der beiden.

**Warum nicht reines Tauri:** der Kern wäre Rust, und Rust ist genau die Stelle,
an der du am langsamsten bist. Tauri **als Shell** ist etwas anderes: dort
schreibst du fast keinen Rust, nur ein paar Commands für OCR und Dateizugriff.

**Warum nicht reines Expo mit RN-macOS:** RN-macOS wird von Expo nicht getragen
und hängt Versionen hinterher. Und das Handoff verlangt auf Desktop ein dichtes
1180-px-Raster mit Tabellen, Heatmap-Matrix und Command-Palette — das ist
React-DOM-Arbeit, kein React-Native-Layout.

**Warum der geteilte Kern trotzdem lohnt:** Profil-Arithmetik, Bewertung,
Fehlerklassifikation, FSRS-Scheduling, Wissensgraph und Verifikation sind
zusammen der überwiegende Teil der schwierigen Logik — und alles davon ist
reine Funktion über Daten. Genau das lässt sich zu 100 % teilen und in Node
testen, ohne Simulator und ohne Gerät.

## Konsequenzen — auch die unangenehmen

**Was leichter wird**
- Der schwierige Teil (Domäne) wird einmal geschrieben und einmal getestet.
- Tests laufen in Node, in Millisekunden, ohne Emulator.
- Die Ports erzwingen, dass Plattformdetails nie in die Domäne sickern.
- macOS bekommt kleine, schnell startende Bundles und saubere Notarisierung.

**Was schwerer wird — ehrlich**
- **Die UI-Komponenten werden nicht geteilt.** React DOM und React Native haben
  getrennte Komponentenbäume. Jede der 13 Komponenten entsteht zweimal.
  Abgemildert dadurch, dass das Handoff Desktop und Mobile ohnehin als zwei
  getrennte Layouts spezifiziert — aber es bleibt doppelte Arbeit.
- **Zwei Build- und Release-Ketten.** Tauri-Signatur/Notarisierung *und* EAS
  Build. Zwei CI-Pfade, zwei Zertifikatsverwaltungen.
- **Drei OCR-Adapter** statt einem.
- **Kein Python.** SymPy, OpenCV und scikit-image stehen nicht zur Verfügung.
  Alles, was du dort gewohnt bist, muss in TS/WASM nachgebaut oder ersetzt werden.
- **Tauri-Mobile bleibt ungenutzt** — der Mobile-Pfad läuft über Expo. Falls du
  Tauri später auch mobil willst, ist das eine neue Entscheidung.

## Die drei plattformkritischen Bausteine

### OCR — drei native Adapter, alle kostenlos und on-device

| Ziel | Backend |
|---|---|
| macOS | Vision (`VNRecognizeTextRequest`) über Tauri-Command |
| iOS | dieselbe Vision-API über ein Expo-Modul |
| Android | ML Kit Text Recognition |

Der `OcrPort` normalisiert auf ein gemeinsames Ergebnis: Textblöcke mit Bounding
Box, Zeilen, Konfidenz. Cloud-OCR nur als Opt-in-Fallback für schlechte Vorlagen.

### PDF — Textlayer geteilt, Anzeige getrennt

**pdf.js läuft auf allen drei Zielen**, weil es reines JavaScript ist. Es liefert
Textlayer mit Positionen und die Seitenrasterung — also genau das, worauf die
gesamte Ingest-Pipeline arbeitet. Nur die *Anzeige* großer Dokumente nutzt
plattformnative Renderer. Damit ist die Pipeline plattformunabhängig, obwohl
das Rendern es nicht ist.

### Symbolische Äquivalenz — numerische Probe statt CAS

Dies ist die Stelle, an der die Drei-Plattform-Entscheidung technisch weh tut:
SymPy als Sidecar-Prozess ist auf iOS und Android nicht möglich.

**Lösung: numerische Probe.** Zwei Ausdrücke gelten als äquivalent, wenn sie an
`N` zufällig gezogenen Punkten des gültigen Definitionsbereichs innerhalb einer
relativen Toleranz übereinstimmen.

- Robuster als Term-Matching gegen algebraisch verschiedene, gleichwertige
  Umformungen — `R₁R₂/(R₁+R₂)` und `1/(1/R₁+1/R₂)` bestehen sie.
- Läuft in reinem JS, identisch auf allen drei Zielen.
- `mathjs` liefert Parser, Auswertung und Einheitenrechnung; symbolisches
  Simplify nur als **Zweitsignal**, nie als alleiniges Urteil.
- Definitionslücken und Polstellen werden durch erneutes Ziehen umgangen;
  bleibt es instabil, lautet das Urteil `unentscheidbar` — nicht `falsch`.

Der `CasPort` kapselt das. Wer später doch ein echtes CAS als WASM einbindet,
tauscht den Adapter, nicht die Domäne.

## Nachtrag 1 · Web als Verifikations-Target (M0/M1)

**Beobachtung.** Ein Tauri-Frontend ist eine gewöhnliche Vite-React-Anwendung;
Tauri ist die Hülle, nicht das Programmiermodell. Solange jeder
Plattformzugriff über einen Port läuft, ist dieselbe UI im Browser lauffähig.

**Entscheidung.** `apps/desktop` wird so gebaut, dass es **in beiden Umgebungen**
startet. Der `StoragePort` bekommt zwei Adapter statt einem:

| Adapter | Umgebung | Zweck |
|---|---|---|
| `adapter-sqljs` | Browser, Node | Entwicklung, Tests, headless E2E |
| `adapter-tauri` | macOS | Auslieferung |

Beide fahren **dieselben** Migrationsdateien und werden gegen **denselben**
Vertragstest geprüft.

**Begründung.** Ohne einen browser-lauffähigen Pfad lässt sich kein UI-Fluss
automatisiert abnehmen — weder in CI noch in einer Umgebung ohne macOS. Der
E2E-Pfad aus `08-architecture.md` wäre dann reine Handarbeit auf einem Gerät.

**Konsequenzen.**
- Ein zusätzlicher Adapter ist zu pflegen.
- Der `StoragePort` wird von Anfang an gegen zwei echte Implementierungen
  gehärtet statt gegen eine — das deckt Vertragslücken früh auf.
- Die UI darf keine Tauri-API direkt aufrufen. Verstöße fängt die
  ESLint-Grenzregel.
- Der sql.js-Pfad ist **kein Auslieferungsziel**. Es gibt keine Web-Version
  des Produkts; die Datenhaltung im Browser dient Entwicklung und Test.

## Revision

Dieser ADR ist zu überarbeiten, wenn eines eintritt:
- Der Mobile-Pfad von Tauri wird so reif, dass eine einzige Shell beide Welten trägt.
- Die numerische Probe erweist sich in M4 als unzureichend für den Formelvergleich.
- Die doppelte Komponentenarbeit erweist sich in M1/M2 als der dominierende
  Zeitfresser — dann ist „macOS zuerst, Mobile in v2" erneut zu diskutieren.
