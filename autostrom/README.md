# Autostrom / LKW-Deutschlandnetz – Anforderungsmanagement

Erweiterung der bestehenden Anforderungs-Excel um den vollständigen
Bieterfragenkatalog (Stand 13.05.2026) sowie um eine automatisierte
Komponenten- und Organigrammstruktur.

## Ergebnisdatei

`20260817_Autostrom_LKWLaden_Anforderungen_mit_Bieterfragenkatalog.xlsx`

Es wurde auf der bestehenden Mappe weitergearbeitet: dieselben fünf Reiter
(Cockpit, Anforderungen, Auswertung, Komponenten, Lesehilfe), dieselbe
Statuslogik, dieselbe Optik. Es wurde kein zusätzlicher Reiter angelegt.

## Was sich geändert hat

### Anforderungen
* 654 zusätzliche Datensätze aus dem Bieterfragenkatalog (ANF-053 … ANF-706),
  eine Bieterfrage je Zeile, angehängt an das bestehende Register.
  Die 9 bereits vorhandenen Bieterfragen wurden nicht dupliziert, sondern um
  Nummer und Originalantwort ergänzt.
* Zwei neue Spalten: `Bieterfrage-Nr.` (M) und `Antwort Auftraggeber (Original)` (N).
* Spalte F heißt jetzt `Anforderung / Frage (Originaltext)`.
* Dokumentwert `Bieterfrage` wurde auf `Bieterfragenkatalog` vereinheitlicht.
* Zwei verwaiste Restzeilen ohne ID (59, 60), die die Statuszählung verfälscht
  haben, wurden geleert.
* Dropdown, Datumsprüfung und bedingte Formatierung reichen jetzt bis Zeile 800.

### Komponenten
* Neue Spaltenreihenfolge: Vergabeeinheit | Partner | Art | Komponente |
  Anforderungen | erfasst | bewertet | erfüllt | trifft nicht zu | Status |
  Bemerkung / Schnittstelle.
* Zählung und Gesamtstatus rechnen über `SUMPRODUCT(ISNUMBER(SEARCH(...)))`
  und erfassen damit auch Mehrfachzuordnungen einer Anforderung.
* Darunter ein Organigramm aus echten Excel-Zeichenobjekten
  (SmartInfra → Vergabeeinheit → Partner → Art → Komponente). Die Beschriftung
  jeder Box ist über `textlink` mit einer Formelzelle in Spalte M verknüpft –
  dieselbe Verknüpfung, die Excel anlegt, wenn man bei einer markierten Form
  `=Zelle` in die Bearbeitungsleiste schreibt. Namen, Anzahlen und Status
  aktualisieren sich damit automatisch; die Boxenanordnung ist fest und wird
  bei struktureller Änderung neu erzeugt (`tools/inject_shapes.py`).
* Darunter zusätzlich eine zellbasierte Statusansicht derselben Hierarchie, die
  sich per bedingter Formatierung automatisch nach dem Status einfärbt und auch
  eine Umsortierung der Tabelle ohne Nacharbeit mitmacht.

### Auswertung / Cockpit
* Bezüge auf den erweiterten Datenbereich nachgezogen.
* Partner- und Komponentenauswertung zählt Kombinationswerte jetzt korrekt.
* Zwei zusätzliche Prüfzeilen für offene Zuordnungen.

## Bewusst offen gelassen

Die Vergabeeinheit ist weder in der bestehenden Datei noch im
Bieterfragenkatalog benannt. Sie steht deshalb durchgängig auf
`Zuordnung prüfen` statt auf einem geratenen Wert. Gleiches gilt für
Partner- und Komponentenzuordnungen, die sich aus Frage und Antwort nicht
eindeutig ableiten lassen.

## Pipeline

| Datei | Zweck |
|---|---|
| `tools/classify.py` | Liest die aus dem PDF extrahierten Tabellenzeilen, leitet Themenfeld, Komponenten, Partner und Kernaussage ab |
| `tools/build.py` | Lädt die bestehende Mappe, ergänzt sie gezielt und legt den Bauplan des Organigramms ab |
| `tools/inject_shapes.py` | Schreibt das Organigramm als Zeichenobjekte in die Mappe |
| `tools/verify.py` | Prüft die fertige Mappe nach dem Neuberechnen |

Ablauf:

```bash
pip install openpyxl pdfplumber
python3 extract_pdf.py       # Bieterfragenkatalog -> pdf_rows.json
python3 classify.py          # pdf_rows.json -> bieterfragen.json
python3 build.py             # original.xlsx + bieterfragen.json -> Ergebnisdatei
#   danach die Mappe neu berechnen lassen (Excel oder LibreOffice),
#   damit die Textquellen in Spalte M Werte haben
python3 inject_shapes.py <datei>   # Organigramm-Boxen einsetzen
python3 verify.py <datei>          # Kontrolle
```

Der Zwischenschritt „neu berechnen" ist nötig, weil die Boxen den berechneten
Zellwert als Anzeigetext mitbekommen, bis Excel die Verknüpfung selbst auffrischt.
