# -*- coding: utf-8 -*-
"""Setzt den Status "trifft nicht zu" fuer eindeutig nicht einschlaegige Zeilen.

Nur drei Gruppen, die sich objektiv am Text nachweisen lassen:
  A  Antwort des Auftraggebers ist ein reiner Verweis auf eine andere Bieterfrage
  B  Begriffsbestimmungen aus § 4 des Betreibervertrags
  C  Regelungen, die ausschliesslich den Auftraggeber betreffen

Bestehende Eintraege werden nie ueberschrieben: geaendert wird nur, was auf
"erfasst" steht und noch keinen Nachweis traegt.

Aufruf:  python3 select_tnz.py <mappe.xlsx>
"""
import re, sys
import openpyxl

SP = dict(id=2, dokument=3, fundstelle=4, kernaussage=6, text=7, status=11, datum=12, nachweis=13)
VERMERK = 'Automatisch ausgewertet: '


def gruppe(dokument, fundstelle, kernaussage, text):
    """Liefert (Kurzname, Begruendung) oder None."""
    treffer = re.match(r'Verweis des Auftraggebers auf die Antwort zu Bieterfrage ([\d,\s.und-]+)',
                       kernaussage)
    if treffer:
        nummer = treffer.group(1).strip().rstrip('.')
        return ('Verweis', f'{VERMERK}Die Antwort des Auftraggebers verweist ausschließlich auf '
                           f'Bieterfrage {nummer}. Keine eigenständige Anforderung – der Inhalt '
                           f'ist unter der dort erfassten Zeile nachzuhalten.')
    if dokument == 'Betreibervertrag' and fundstelle.startswith('§ 4 ('):
        return ('Begriffsbestimmung',
                f'{VERMERK}Begriffsbestimmung aus § 4 des Betreibervertrags. Definition ohne '
                f'eigene Leistungspflicht des Auftragnehmers.')
    if re.match(r'^(Der Auftraggeber|Die Auftraggeber|Auftraggeber [12])\b', text) \
            and 'uftragnehmer' not in text:
        return ('nur Auftraggeber',
                f'{VERMERK}Die Regelung richtet sich ausschließlich an den Auftraggeber; der '
                f'Auftragnehmer wird im Text nicht verpflichtet.')
    return None


def main():
    pfad = sys.argv[1]
    wb = openpyxl.load_workbook(pfad)
    ws = wb['Anforderungen']
    gezaehlt, uebergangen = {}, 0
    for r in range(7, 2100):
        if not ws.cell(r, SP['id']).value:
            continue
        if ws.cell(r, SP['status']).value != 'erfasst':
            continue
        if ws.cell(r, SP['nachweis']).value:              # eigene Notiz nicht anfassen
            uebergangen += 1
            continue
        werte = [str(ws.cell(r, SP[k]).value or '')
                 for k in ('dokument', 'fundstelle', 'kernaussage', 'text')]
        ergebnis = gruppe(*werte)
        if not ergebnis:
            continue
        name, begruendung = ergebnis
        ws.cell(r, SP['status']).value = 'trifft nicht zu'
        ws.cell(r, SP['nachweis']).value = begruendung
        gezaehlt[name] = gezaehlt.get(name, 0) + 1
    print('auf „trifft nicht zu" gesetzt:', sum(gezaehlt.values()), gezaehlt)
    print('wegen vorhandener Notiz übergangen:', uebergangen)
    wb.save(pfad)
    print('gespeichert:', pfad)


if __name__ == '__main__':
    main()
