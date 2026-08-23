# 08 · Architektur

## Module und Grenzen

Hexagonal: eine reine Domäne, Ports als Verträge, Adapter je Plattform.

```
packages/core            reines TS · kein IO · kein Framework · kein Datum aus Date.now()
  profile/               Achsen, Bänder, Hysterese, Regeln, Verhaltensterm
  grading/               Toleranz, Einheiten, Äquivalenz, Folgefehler, Taxonomie
  parametric/            Ziehung, Constraints, Verifikation, Quarantäne
  scheduling/            FSRS-Variante, Auswahl, Zeitkalibrierung, Prognose
  ingest/                Segmentierungsheuristik, Punkte-Regex, Lösungsbezug
  graph/                 Wissensgraph, Voraussetzungen, blockierte Punkte
  model/                 Entitäten, Invarianten-Prüfungen

packages/ports           Interfaces, keine Implementierung
  StoragePort  OcrPort  LlmPort  CasPort  PdfPort  ClockPort  BlobPort  KeychainPort

packages/adapters-web    Tauri-Kontext
packages/adapters-rn     Expo-Kontext

apps/desktop             Tauri 2 + React DOM   → macOS, Layout 1180
apps/mobile              Expo / React Native   → iOS + Android, Layout 390

packages/ui-tokens       Farbrollen, Typo-Skala, Spacing, Radius, Motion
                         als plattformneutrale Wertetabelle
```

**Die Kernregel:** `packages/core` importiert nichts außer `packages/ports` und
`packages/model`. Kein `fetch`, kein `fs`, kein `Date.now()`, kein `Math.random()`
ohne injizierten Seed. Ein Lint-Rule erzwingt das — nicht die Disziplin.

`ClockPort` und die Seed-Injektion sind kein Purismus: Timer, FSRS-Fälligkeiten
und die Variantenziehung sind sonst nicht testbar.

## Ports

| Port | Verantwortung | Desktop | Mobile |
|---|---|---|---|
| `StoragePort` | SQL, Transaktionen, Migrationen | rusqlite via Tauri | expo-sqlite |
| `BlobPort` | Rasterbilder, Assets, Originaldateien | Dateisystem | Dateisystem |
| `OcrPort` | Bild → Blöcke mit BBox und Konfidenz | Vision (macOS) | Vision (iOS) / ML Kit |
| `PdfPort` | Textlayer, Seitenrasterung, Anzeige | pdf.js | pdf.js + react-native-pdf |
| `LlmPort` | Anfrage, **Vorschau**, Protokoll | HTTP | HTTP |
| `CasPort` | Parsen, Auswerten, Äquivalenz, Einheiten | mathjs | mathjs |
| `ClockPort` | Jetzt, Monotone Zeit für den Timer | — | — |
| `KeychainPort` | API-Keys | macOS-Schlüsselbund | Keychain / Keystore |

`LlmPort.preview(request)` gibt zurück, was gesendet würde, ohne zu senden.
Die Zustimmungs-UI aus `00` ruft ausschließlich diese Methode auf. Ein
`send()` ohne vorheriges bestätigtes `preview()` ist ein Fehler, kein Feature.

## Datenfluss

```
Datei
  └→ IngestService (core)
       ├→ PdfPort / OcrPort            Seitenmodell
       ├→ core/ingest                  Segmentierung, Punkte
       ├→ LlmPort (opt-in)             Vorschlagsverfeinerung
       └→ StoragePort                  Artefakte + Overrides
              ↓
         Review-UI  →  Overrides  →  ExamPaper: draft → ready
              ↓
         Atlas → SolveView → Attempt
              ├→ core/grading          Punkte, Fehlercodes
              ├→ core/scheduling       MasteryState, nächste Fälligkeit
              └→ core/profile          Verhaltensterm
                       ↓
              abgeleitet: Bänder, Regeln, Plan, Prognose
```

Alles Abgeleitete wird bei Bedarf gerechnet, nie gespeichert (`02`, Abschnitt
„Abgeleitet, nie gespeichert").

## Offline-Verhalten

**Ohne Netz voll funktionsfähig:** Import von Textlayer-PDFs, OCR (on-device),
manuelle und heuristische Segmentierung, Lösen, Timer, numerische Bewertung,
Rechenweg-Diff, Fehler-DNA, Wissensgraph, Plan, Simulator, Auswertung.

**Nur mit Netz:** LLM-gestützte Segmentierungsverfeinerung, Freitext-Rubrik,
Vorlagenerzeugung ohne Musterlösung.

**Verhalten bei fehlendem Netz:** die betreffende Aktion ist sichtbar deaktiviert
mit Begründung. Keine Warteschlange, kein stiller Rückstau, kein Spinner, der
auf Verbindung wartet. Was offline geht, geht sofort.

## Migrationen

Es gibt keine Cloud-Kopie. Eine kaputte Migration ist Datenverlust.

- **Nummerierte, vorwärtsgerichtete SQL-Migrationen**, dieselben Dateien auf
  beiden Plattformen. Kein ORM-Autosync.
- **Vor jeder Migration ein Snapshot** der Datenbankdatei, mindestens die
  letzten drei aufbewahrt. Schlägt die Migration fehl, wird zurückgerollt und
  die App startet in der alten Version mit Hinweis.
- **`schema_version`** in einer eigenen Tabelle; die App verweigert den Start
  bei höherer Version als sie kennt, statt zu raten.
- **Rohdaten sind heilig.** Migrationen dürfen abgeleitete Tabellen jederzeit
  neu aufbauen, aber nie Antworten, Zeiten, Onboarding-Antworten oder Overrides
  verändern.
- **Golden-Migrationstest:** eine Fixture-Datenbank jeder je ausgelieferten
  Version wird bei jedem Build durch alle Migrationen gefahren.

## Fehler und Logging

**Drei Fehlerklassen**, unterschiedlich behandelt:

| Klasse | Beispiel | Verhalten |
|---|---|---|
| Erwartet | OCR-Konfidenz zu niedrig, Netz fehlt | Teil des Modells, in der UI benannt, kein Log-Eintrag als Fehler |
| Behandelbar | Migration schlägt fehl, Datei nicht lesbar | Rollback, Nutzerhinweis mit konkreter Handlungsoption |
| Unerwartet | Invariantenverletzung, Nullzugriff | Log mit Kontext, Fehlerbild in der UI, kein stiller Weiterlauf |

**Eine verletzte Invariante ist immer unerwartet.** Sie wird geprüft, geloggt
und führt zu einem sichtbaren Fehler — nie zu einer stillen Korrektur.

**Logs bleiben lokal.** Rotierende Datei, keine Telemetrie, kein Crash-Reporter,
der Inhalte überträgt. Ein Log darf niemals Aufgabentext, Antworten oder
Dateinamen von Klausuren enthalten — nur IDs.

## Teststrategie

| Ebene | Werkzeug | Umfang |
|---|---|---|
| Domäne | Vitest in Node | hoch — alle Regeln, alle Invarianten, alle Grenzfälle |
| Pipeline | Golden-File gegen echten Klausurkorpus | Präzision/Trefferquote je Stufe, Regression |
| Adapter | Integrationstest je Plattform | dünn — nur der Vertrag des Ports |
| UI | Playwright (Desktop), Maestro (Mobile) | **wenige** E2E-Pfade |

**Die fünf E2E-Pfade, mehr nicht:**
1. Import eines Textlayer-PDFs bis zur fertigen Kartenliste
2. Falsche Segmentierung korrigieren, erneut auto-segmentieren, Korrektur überlebt
3. Aufgabe lösen mit Timer bis Überschreitung und erzwungener Abgabe
4. Rechenweg-Diff mit Folgefehler: Teilpunkte werden korrekt vergeben
5. Onboarding vollständig → Beispielprofil → eine Regel abschalten → Wirkung weg

Der Korpus für Golden-Files liegt außerhalb des Repos (Urheberrecht, `00`).
Im Repo liegen nur die erwarteten Ergebnisse als JSON und ein Skript, das
den lokalen Korpuspfad einliest.
