# -*- coding: utf-8 -*-
"""Zerlegt die Vertragsdokumente in einzelne Anforderungen.

Zwei Dokumenttypen:
  Paragraphen (Betreibervertrag, Vertragsanlage 13): § N -> Absatz N. -> Buchstabe a.
  Abschnitte  (Vertragsanlage 6 und 10):             N.N Titel -> Spiegelstrich / Absatz

Die Fundstellen folgen der bereits in der Mappe verwendeten Schreibweise:
  "§ 25 (2) c"   bzw.   "§ 3.1 (2)"
"""
import json, re, sys, warnings
import pdfplumber

warnings.filterwarnings('ignore')
U = '/root/.claude/uploads/eaf865a5-2b1e-5249-aa6b-f7be9a8c980d'

DOKUMENTE = [
    ('Betreibervertrag', f'{U}/45a3d80a-20260323_Anlage_1_zum_Verfahrensbrief_Betreibervertrag.pdf',
     'paragraphen'),
    ('Vertragsanlage 6',
     f'{U}/02e1fcf9-20251204_Vertragsanlage_06_Anforderungen_an_die_Ladeinfrastruktur.pdf',
     'abschnitte'),
    ('Vertragsanlage 10',
     f'{U}/7df78190-20251204_Vertragsanlage_10_Leistungsbeschreibung_Betrieb_1.pdf', 'abschnitte'),
    ('Vertragsanlage 13',
     f'{U}/2e8c892d-20251204_Vertragsanlage_13_Bilanzierung_Durchleitungsmodell.pdf',
     'paragraphen'),
]

MUELL = re.compile(r'^(Seite \d+|Az\.: [\d-]+|Vertrag LKW-Schnellladenetz.*|Stand: [\d.]+|'
                   r'Vertragsanlage \d+|\d+|[\d]+ / [\d]+|06913-23 / \d+.*)$')
INHALTSVERZEICHNIS = re.compile(r'\.{4,}\s*\d*\s*$')


def seiten_text(pfad):
    """Liefert (Seitennummer, Text) je Seite ohne Kopf- und Fusszeilen."""
    with pdfplumber.open(pfad) as pdf:
        for nr, seite in enumerate(pdf.pages, start=1):
            roh = seite.extract_text() or ''
            zeilen = [z for z in roh.split('\n') if not MUELL.match(z.strip())]
            yield nr, '\n'.join(zeilen)


def entsilben(text):
    """Trennstriche am Zeilenende aufloesen, Zeilenumbrueche zu Leerzeichen."""
    text = re.sub(r'(\w)-\n([a-zäöüß])', r'\1\2', text)      # Nennla-\ndeleistung
    text = re.sub(r'(\w)-\n([A-ZÄÖÜ])', r'\1-\2', text)      # MCS-\nLadepunkte
    text = re.sub(r'\n+', ' ', text)
    return re.sub(r'\s{2,}', ' ', text).strip()


def volltext_mit_seiten(pfad):
    """Gesamttext ab Ende des Inhaltsverzeichnisses plus Zuordnung Position -> Seite."""
    teile, marken, pos = [], [], 0
    for nr, text in seiten_text(pfad):
        teile.append(text)
        marken.append((pos, nr))
        pos += len(text) + 1
    gesamt = '\n'.join(teile)
    # Das Inhaltsverzeichnis endet mit der letzten Zeile der Form "... Titel ...... 23"
    letzte = None
    for treffer in re.finditer(r'(?m)^.*\.{4,}\s*\d+\s*$', gesamt):
        letzte = treffer
    if letzte:
        schnitt = letzte.end()
        gesamt = ' ' * schnitt + gesamt[schnitt:]      # Positionen bleiben erhalten
    return gesamt, marken


def seite_zu(position, marken):
    treffer = 1
    for start, nr in marken:
        if start <= position:
            treffer = nr
        else:
            break
    return treffer


def teile_absaetze(block):
    """Absaetze '1. ' und Buchstaben 'a. ' innerhalb eines Paragraphen."""
    stuecke = re.split(r'(?m)^(\d{1,2})\.\s+', block)
    if len(stuecke) < 3:
        return [(None, block)]
    ergebnis = []
    for i in range(1, len(stuecke), 2):
        ergebnis.append((stuecke[i], stuecke[i + 1]))
    return ergebnis


def teile_buchstaben(text):
    stuecke = re.split(r'(?m)^([a-z])\.\s+', text)
    if len(stuecke) < 3:
        return [(None, text)]
    kopf = stuecke[0].strip()
    ergebnis = [(None, kopf)] if kopf else []
    for i in range(1, len(stuecke), 2):
        ergebnis.append((stuecke[i], stuecke[i + 1]))
    return ergebnis


def aufsteigende_folge(kandidaten, schluessel):
    """Laengste aufsteigende Teilfolge - verwirft Ausreisser wie Querverweise.

    Ueberschriften sind im Dokument durchnummeriert. Alles, was diese Reihenfolge
    durchbricht (Querverweise im Fliesstext, Tabellenzellen), faellt heraus.
    """
    if not kandidaten:
        return []
    laenge = [1] * len(kandidaten)
    vorher = [-1] * len(kandidaten)
    for i in range(len(kandidaten)):
        for j in range(i):
            if schluessel(kandidaten[j]) < schluessel(kandidaten[i]) and laenge[j] + 1 > laenge[i]:
                laenge[i], vorher[i] = laenge[j] + 1, j
    i = laenge.index(max(laenge))
    kette = []
    while i != -1:
        kette.append(kandidaten[i])
        i = vorher[i]
    return kette[::-1]


def echte_paragraphen(text):
    """Ueberschriften "§ N Titel" - ohne Querverweise aus dem Fliesstext."""
    kandidaten = []
    for treffer in re.finditer(r'(?m)^§ *(\d+)([a-z]?) +([^\n]{3,120})$', text):
        titel = treffer.group(3).strip()
        if not titel[:1].isupper() or titel.startswith('Abs.') or ' Abs. ' in titel[:20]:
            continue
        kandidaten.append(treffer)
    return aufsteigende_folge(kandidaten, lambda t: (int(t.group(1)), t.group(2)))


def lies_paragraphen(dokument, pfad):
    text, marken = volltext_mit_seiten(pfad)
    kopfzeilen = echte_paragraphen(text)
    saetze = []
    for i, kopf in enumerate(kopfzeilen):
        nummer, titel = kopf.group(1) + kopf.group(2), kopf.group(3).strip()
        ende = kopfzeilen[i + 1].start() if i + 1 < len(kopfzeilen) else len(text)
        block = text[kopf.end():ende]
        seite = seite_zu(kopf.start(), marken)
        for absatz, inhalt in teile_absaetze(block):
            for buchstabe, stueck in teile_buchstaben(inhalt):
                roh = entsilben(stueck)
                if len(roh) < 25:
                    continue
                fundstelle = f'§ {nummer}'
                if absatz:
                    fundstelle += f' ({absatz})'
                if buchstabe:
                    fundstelle += f' {buchstabe}'
                saetze.append(dict(dokument=dokument, fundstelle=fundstelle, kapitel=titel,
                                   seite=seite, text=roh))
    return saetze


def lies_abschnitte(dokument, pfad):
    text, marken = volltext_mit_seiten(pfad)
    kandidaten = []
    for treffer in re.finditer(r'(?m)^(\d+(?:\.\d+)*) +([A-ZÄÖÜ][^\n]{2,80})$', text):
        stufen = tuple(int(x) for x in treffer.group(1).split('.'))
        titel = treffer.group(2).strip()
        if any(s > 40 for s in stufen) or titel.endswith('.'):
            continue                          # Messwerte und Fliesstext ausschliessen
        kandidaten.append(treffer)
    kopfzeilen = aufsteigende_folge(
        kandidaten, lambda t: tuple(int(x) for x in t.group(1).split('.')))
    saetze = []
    for i, kopf in enumerate(kopfzeilen):
        nummer, titel = kopf.group(1), kopf.group(2).strip()
        ende = kopfzeilen[i + 1].start() if i + 1 < len(kopfzeilen) else len(text)
        block = text[kopf.end():ende]
        seite = seite_zu(kopf.start(), marken)
        if '▪' in block:
            stuecke = [s for s in block.split('▪') if s.strip()]
        else:
            stuecke = re.split(r'\n(?=[A-ZÄÖÜ])', block)
        nummeriert = [s for s in stuecke if len(entsilben(s)) >= 25]
        for platz, stueck in enumerate(nummeriert, start=1):
            fundstelle = f'§ {nummer}'
            if len(nummeriert) > 1:
                fundstelle += f' ({platz})'
            saetze.append(dict(dokument=dokument, fundstelle=fundstelle, kapitel=titel,
                               seite=seite, text=entsilben(stueck)))
    return saetze


def main():
    alles = []
    for dokument, pfad, art in DOKUMENTE:
        saetze = (lies_paragraphen if art == 'paragraphen' else lies_abschnitte)(dokument, pfad)
        print(f'{dokument:20s} {len(saetze):4d} Anforderungen')
        alles.extend(saetze)
    json.dump(alles, open('vertragstexte.json', 'w'), ensure_ascii=False, indent=1)
    print('gesamt:', len(alles))


if __name__ == '__main__':
    main()
