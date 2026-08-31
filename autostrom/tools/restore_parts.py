# -*- coding: utf-8 -*-
"""Stellt Bestandteile wieder her, die openpyxl beim Speichern nicht kennt.

  1. Das Partner-Dropdown in "Anforderungen" (Liste aus Komponenten!$N$6:$N$29).
     Excel legt solche Listen als x14-Datenpruefung ab; openpyxl entfernt sie.
  2. Die customXml-Teile (SharePoint-Eigenschaften der Mappe).

Aufruf:  python3 restore_parts.py <mappe.xlsx> <vorlage.xlsx> <letzte_zeile>
"""
import re, shutil, sys, zipfile

X14 = ('<extLst><ext uri="{{CCE6A557-97BC-4b89-ADB6-D9C93CAAB3DF}}" '
       'xmlns:x14="http://schemas.microsoft.com/office/spreadsheetml/2009/9/main">'
       '<x14:dataValidations count="1" '
       'xmlns:xm="http://schemas.microsoft.com/office/excel/2006/main">'
       '<x14:dataValidation type="list" allowBlank="1" showInputMessage="1" '
       'showErrorMessage="1"><x14:formula1><xm:f>Komponenten!$N$6:$N$29</xm:f></x14:formula1>'
       '<xm:sqref>I7:I{ende}</xm:sqref></x14:dataValidation></x14:dataValidations></ext></extLst>')


def blattdatei(z, blattname):
    wbxml = z.read('xl/workbook.xml').decode()
    rels = z.read('xl/_rels/workbook.xml.rels').decode()
    namen = re.findall(r'<sheet[^>]*name="([^"]+)"[^>]*r:id="([^"]+)"', wbxml)
    rid = dict(namen)[blattname]
    ziel = re.search(rf'Id="{rid}"[^>]*Target="([^"]+)"', rels).group(1)
    return 'xl/' + ziel.lstrip('/')


def main():
    pfad, vorlage, ende = sys.argv[1], sys.argv[2], sys.argv[3]
    with zipfile.ZipFile(vorlage) as alt:
        custom = {n: alt.read(n) for n in alt.namelist() if n.startswith('customXml/')}

    tmp = pfad + '.tmp'
    with zipfile.ZipFile(pfad) as quelle:
        namen = quelle.namelist()
        blatt_name = blattdatei(quelle, 'Anforderungen')
        blatt = quelle.read(blatt_name).decode()
        if '<x14:dataValidation' in blatt:
            print('Dropdown bereits vorhanden')
        else:
            blatt = blatt.replace('</worksheet>', X14.format(ende=ende) + '</worksheet>')
            print(f'Partner-Dropdown wiederhergestellt (I7:I{ende})')

        rels = quelle.read('xl/_rels/workbook.xml.rels').decode()
        ct = quelle.read('[Content_Types].xml').decode()
        neue_teile = {}
        if custom and 'customXml/item1.xml' not in namen:
            zusatz = ''
            for i in (1, 2, 3):
                zusatz += (f'<Relationship Id="rIdCustom{i}" Type="http://schemas.openxmlformats.'
                           f'org/officeDocument/2006/relationships/customXml" '
                           f'Target="../customXml/item{i}.xml"/>')
                ct = ct.replace('</Types>', (
                    f'<Override PartName="/customXml/itemProps{i}.xml" ContentType="application/'
                    f'vnd.openxmlformats-officedocument.customXmlProperties+xml"/></Types>'))
            rels = rels.replace('</Relationships>', zusatz + '</Relationships>')
            neue_teile.update(custom)
            print(f'{len(custom)} customXml-Teile wiederhergestellt')

        ersetzt = {blatt_name: blatt.encode('utf-8'),
                   'xl/_rels/workbook.xml.rels': rels.encode('utf-8'),
                   '[Content_Types].xml': ct.encode('utf-8')}
        with zipfile.ZipFile(tmp, 'w', zipfile.ZIP_DEFLATED) as ziel:
            for eintrag in quelle.infolist():
                ziel.writestr(eintrag, ersetzt.get(eintrag.filename,
                                                   quelle.read(eintrag.filename)))
            for name, daten in neue_teile.items():
                ziel.writestr(name, daten)
    shutil.move(tmp, pfad)
    print('gespeichert:', pfad)


if __name__ == '__main__':
    main()
