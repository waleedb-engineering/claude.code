# -*- coding: utf-8 -*-
"""Liest den Bieterfragenkatalog (PDF) aus und legt die Tabellenzeilen als JSON ab."""
import json, sys
import pdfplumber

pdf_pfad = sys.argv[1] if len(sys.argv) > 1 else 'Bieterfragenkatalog.pdf'
zeilen = []
with pdfplumber.open(pdf_pfad) as pdf:
    for seite, p in enumerate(pdf.pages, start=1):
        for tabelle in p.find_tables():
            for reihe in tabelle.extract():
                zellen = [(c or '').replace('\n', ' ').strip() for c in reihe]
                if zellen[:1] == ['Nr.']:
                    continue                       # Spaltenkopf der Folgeseiten
                zeilen.append({'page': seite, 'cells': zellen})
json.dump(zeilen, open('pdf_rows.json', 'w'), ensure_ascii=False)
print('Tabellenzeilen:', len(zeilen))
