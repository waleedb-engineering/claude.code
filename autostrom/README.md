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

## Nachtrag: Organigramm neu erzeugen ohne Datenverlust

`tools/regen_orga.py` richtet Textquellen und Boxenanordnung an der **aktuellen**
gepflegten Komponententabelle aus, statt die Mappe neu aufzubauen. Damit bleiben
alle Eintraege erhalten (Status, Erfuellungsdaten, Vergabeeinheiten).

```bash
python3 regen_orga.py <mappe.xlsx>   # Spalte M und Bauplan neu ausrichten
#   Mappe neu berechnen lassen
python3 inject_shapes.py <mappe.xlsx>
```

Die Gruppierung erfolgt logisch nach Vergabeeinheit → Partner → Art, also auch
dann korrekt, wenn gleiche Vergabeeinheiten in der Tabelle nicht untereinander
stehen.

## Nachtrag: Vertragsdokumente einpflegen

`tools/parse_docs.py` zerlegt Betreibervertrag sowie Vertragsanlagen 6, 10 und 13
in einzelne Anforderungen, `tools/add_docs.py` haengt sie an die gepflegte Mappe an.

```bash
python3 parse_docs.py                # PDFs -> vertragstexte.json
python3 add_docs.py <mappe.xlsx>     # anhaengen, Bereiche mitziehen
python3 regen_orga.py <mappe.xlsx>   # Organigramm nachfuehren
#   Mappe neu berechnen lassen
python3 inject_shapes.py <mappe.xlsx>
```

Erkannt werden zwei Dokumenttypen: Paragraphen (§ N -> Absatz -> Buchstabe) und
nummerierte Abschnitte (N.N -> Spiegelstrich). Querverweise im Fliesstext werden
ueber die laengste aufsteigende Nummernfolge von echten Ueberschriften getrennt.
Die Dublettenpruefung vergleicht den Anfang des Originaltextes, nicht die
Fundstelle - so werden bereits erfasste Anforderungen auch dann erkannt, wenn sie
unter einer aelteren Paragraphennummer im Register stehen.

## Nachtrag: Selektion und wiederhergestellte Bestandteile

`tools/select_tnz.py` setzt den Status "trifft nicht zu" nur dort, wo sich das
objektiv am Text nachweisen laesst, und traegt die Begruendung in
"Nachweis / Notiz" ein. Drei Gruppen:

| Gruppe | Nachweis am Text |
|---|---|
| Verweis | Antwort des AG verweist ausschliesslich auf eine andere Bieterfrage |
| Begriffsbestimmung | § 4 Betreibervertrag, Definitionsteil |
| Unterlagenanpassung | Die Antwort kuendigt nur eine Anpassung der Vergabeunterlagen an, und die Antwort ist kurz und ohne eigene Aussage |
| Vergabeverfahren | Themenfeld "Vergabeverfahren & Angebot" ohne Komponentenzuordnung |

Bestehende Eintraege werden nie ueberschrieben: geaendert wird nur, was auf
"erfasst" steht und noch keinen Nachweis traegt.

`tools/restore_parts.py` stellt zwei Dinge wieder her, die openpyxl beim
Speichern verliert: das Partner-Dropdown in Spalte I (Excel legt Listen mit
Bereichsbezug als x14-Datenpruefung ab) und die customXml-Teile mit den
SharePoint-Eigenschaften. Der Aufruf gehoert ans Ende jeder Bearbeitung:

```bash
python3 restore_parts.py <mappe.xlsx> <vorlage.xlsx> <letzte_zeile>
```

Beide Skripte sind wiederholbar: `select_tnz.py` fasst nur Zeilen mit Status
"erfasst" ohne eigene Notiz an, `inject_shapes.py` ueberschreibt ein bereits
vorhandenes Zeichnungsteil, statt ein zweites anzulegen, und entfernt verwaiste
Teile frueherer Laeufe.

### Nachpruefung der Selektion

Zwei Regeln wurden nach einer Kontrolle gegen die Originalantworten wieder
entfernt, weil sie der Pruefung nicht standhielten:

* **nur Auftraggeber** - ein Recht des Auftraggebers begruendet regelmaessig eine
  Umsetzungspflicht des Auftragnehmers. § 25 Abs. 3 (Anpassung der
  Mindestvoraussetzungen mit zwei Monaten Vorlauf) waere faelschlich
  ausgeschieden worden.
* **nicht Gegenstand** - die Kernaussage stand im Widerspruch zur Antwort des
  Auftraggebers, die eine Anbindungspflicht ueber OCPI festschreibt.

Die Gruppe **Unterlagenanpassung** wurde eingeschraenkt: sie greift nur, wenn die
Antwort hoechstens 200 Zeichen umfasst und keine eigene Aussage enthaelt.
`tools/revert_tnz.py` nimmt bereits gesetzte Faelle entsprechend zurueck.

## Nachtrag: eigener Reiter fuer das Organigramm

Das Organigramm schwebte bisher unterhalb der Tabelle im Reiter "Komponenten"
und war dort leicht zu uebersehen - Excel oeffnet das Blatt an der zuletzt
gespeicherten Bildlaufposition. `tools/build_orga_sheet.py` legt es jetzt auf
einem eigenen Reiter "Organigramm" ab:

* Zeichenflaeche mit den Boxen (Beschriftung ueber textlink verknuepft)
* Textquellen der Boxen in Spalte Z
* darunter dieselbe Struktur in Zellen, die sich automatisch einfaerbt

Der Reiter "Komponenten" enthaelt nur noch die Tabelle und einen Verweis.
`tools/regen_orga.py` ist damit abgeloest.

## Nachtrag: Eingrenzung auf den eigenen Leistungsumfang

`tools/select_topic.py` setzt alles auf "trifft nicht zu", was nicht Schranken,
Kennzeichenerfassung oder die dynamische Anzeige betrifft. Behalten wird eine
Zeile, wenn ihre Komponente dazu passt **oder** ihr Text ein einschlaegiges
Stichwort traegt (Schranke, Poller, Zufahrtsbeschraenkung, Kennzeichen, Kamera,
ANPR, dynamische Anzeige, LED, Anzeigetafel, Display). Das Stichwortnetz faengt
Zeilen ab, deren Komponentenzuordnung noch offen ist.
