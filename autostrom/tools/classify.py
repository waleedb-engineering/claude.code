# -*- coding: utf-8 -*-
"""Klassifikation der Bieterfragen: Themenfeld, Komponenten, Partner, Kernaussage.

Grundsatz: enge Muster. Lieber "Zuordnung pruefen" als eine falsche Zuordnung.
Kaufmaennische Begriffe (Betreiberentgelt, Netzentgelt, Verguetung) fuehren
ausdruecklich NICHT zu einer technischen Komponente.
Alle Komponenten- und Partnernamen stammen aus der bestehenden Excel-Datei.
"""
import json, re

ROWS = json.load(open('pdf_rows.json'))

KOMPONENTEN = {
    'Kennzeichenerfassung': [
        r'kennzeichen(erfassung|erkennung|lesung)', r'\bkamera', r'nummernschild', r'\banpr\b',
    ],
    'Belegungsdetektion': [
        r'belegungs(detektion|status|erkennung|sensor)', r'detektierbarkeit',
        r'ladeplatzdetektion', r'detektion des belegungs', r'objektdetektion',
        r'detektionssensor', r'deckensensor',
    ],
    'Dynamische Anzeige': [
        r'dynamisch\w* anzeige', r'led[- ]?anzeige', r'anzeigetafel', r'\bdisplay\b',
        r'variable anzeige', r'\bled\b',
    ],
    'Beschilderung': [
        r'beschilderung', r'hinweisschild', r'beschilderungsplan', r'statische anzeige',
        r'kennzeichnung des ladeplatz',
    ],
    'Schrankenanlage': [
        r'schrankenanlage', r'schrankeninsel', r'\bpoller', r'physische zufahrtsbeschr',
        r'zufahrtsbeschr',
    ],
    'Schrankensteuerung': [
        r'schrankensteuerung', r'einfahrtsschranke', r'ausfahrtsschranke', r'\bschranke\b',
        r'\bschranken\b',
    ],
    'Authentifizierungskomponente': [
        r'authentifizier', r'\brfid\b', r'plug\s*&\s*charge', r'plug and charge',
        r'iso\s*15118', r'autocharge', r'bezahlterminal', r'kartenlese',
        r'ad[- ]?hoc[- ]?lad', r'freischaltung der',
    ],
    'OCPI Buchungskalender': [
        r'\bocpi\b', r'reservier', r'buchungskalender', r'\broaming', r'\bocpp\b',
    ],
    'Reservierungsplattform': [
        r'reservierungsplattform', r'reservierungssystem',
    ],
    'Anbindung': [
        r'anbindung (der|von) reservierungsplattform', r'anbindungsf',
    ],
    'Abrechnungskomponente': [
        r'blockadeentgelt', r'\beichrecht', r'mindestabnahmemenge',
        r'ad[- ]?hoc[- ]?(lade)?(preis|tarif)', r'ladetarif', r'preisanzeige',
        r'abrechnung des ladevorgang', r'abrechnung der ladevorg',
    ],
    'Pönalisierungssystem': [
        r'pönal', r'falschpark',
    ],
    'Monitoring': [
        r'\bmonitoring', r'monatsbericht', r'\breporting', r'statusmeldung',
        r'störungsmeldung', r'ladevorgangsdaten', r'\bdatenpunkt', r'verfügbarkeitsmeldung',
        r'status an das backend',
    ],
    'Ladeeinrichtung': [
        r'ladeeinrichtung', r'\bdispenser', r'\bladesäule', r'\bladekabel', r'\bladestecker',
        r'leistungseinheit', r'ladehardware', r'kühlung des',
    ],
}

# Begriffe, die eine technische Beruehrung nahelegen, aber keine eindeutige Komponente
UNSICHER = [r'telematisch\w* parken', r'\btelematik', r'\bbeleuchtung', r'schließsystem',
            r'zutrittskontrolle', r'videoüberwachung']

# Reihenfolge = Prioritaet (erster Treffer gewinnt)
THEMENFELD = [
    ('Reservierung', [r'reservier', r'buchungskalender', r'\bocpi\b']),
    ('Belegungsdetektion', [r'belegungs(detektion|status|erkennung|sensor)',
                            r'detektierbarkeit', r'ladeplatzdetektion', r'deckensensor']),
    ('Zufahrt & Schranke', [r'\bschranke', r'\bpoller', r'zufahrtsbeschr', r'schrankeninsel']),
    ('Authentifizierung & Zugang', [r'authentifizier', r'\brfid\b', r'plug\s*&\s*charge',
                                    r'iso\s*15118', r'bezahlterminal', r'ad[- ]?hoc[- ]?lad',
                                    r'autocharge']),
    ('Anzeige & Beschilderung', [r'beschilderung', r'\bled\b', r'dynamisch\w* anzeige',
                                 r'anzeigetafel', r'hinweisschild', r'markierungsplan']),
    ('Monitoring & Reporting', [r'\bmonitoring', r'monatsbericht', r'statusmeldung',
                                r'\bdatenpunkt', r'verfügbarkeitsmeldung', r'ladevorgangsdaten']),
    ('Nutzungszeit & Entgelte', [r'blockadeentgelt', r'nutzungsdauer', r'nutzungszeit',
                                 r'mindestabnahmemenge', r'\beichrecht', r'ladetarif',
                                 r'ad[- ]?hoc[- ]?(lade)?(preis|tarif)']),
    ('Netzanschluss & Energie', [r'netzanschluss', r'netzbetreiber', r'\bnetzentgelt',
                                 r'mittelspannung', r'\btrafo', r'transformator', r'\bspeicher',
                                 r'photovoltaik', r'pv[- ]anlage', r'stromliefer',
                                 r'lastmanagement', r'anschlussleistung', r'\bumspann',
                                 r'netzverkn', r'verlustenergie', r'durchleitungsmodell',
                                 r'messstellenbetrieb', r'\bkva\b', r'\bdrossel']),
    ('Flächen & Genehmigungen', [r'grundstück', r'\bfläche', r'genehmigung', r'baurecht',
                                 r'planfeststell', r'naturschutz', r'\baltlast', r'kampfmittel',
                                 r'\brastanlage', r'pachtvertrag', r'\bvermessung', r'\bbaugrund',
                                 r'entwässerung', r'horizontalbohrung', r'standortübersicht',
                                 r'\bvorplanung', r'referenzlayout', r'referenzplanung',
                                 r'schleppkurve', r'\bparkstand']),
    ('Bau & Dokumentation', [r'\bbaufreigabe', r'as-built', r'bestandsunterlagen',
                             r'ausführungsplanung', r'\bbauablauf', r'\bbauzeit', r'\bbauleistung',
                             r'errichtungsfrist', r'\bterminplan', r'\bmontage', r'\btiefbau',
                             r'\bfundament', r'\bbauherr', r'\bbaustelle', r'verkehrsfreigabe',
                             r'betriebsfreigabe']),
    ('Betrieb & Auslastung', [r'betriebsführung', r'instandhaltung', r'\bwartung', r'\bstörung',
                              r'\bauslastung', r'\bverfügbarkeit', r'betriebskosten',
                              r'\breinigung', r'winterdienst', r'vandalismus',
                              r'sicherheitsdienst', r'entstörung']),
    ('Technik Ladeinfrastruktur', [r'ladeeinrichtung', r'\bdispenser', r'\bladesäule',
                                   r'\bladekabel', r'leistungseinheit', r'ladeleistung',
                                   r'\bmcs\b', r'\bccs\b', r'ladepunkt']),
    ('Vertrag & Recht', [r'\bvertrag', r'versicherung', r'\bhaftung', r'\bbürgschaft',
                         r'\bkündigung', r'nachunternehmer', r'betreiberentgelt',
                         r'infrastrukturentgelt', r'\bvergütung', r'\bindexierung', r'\bförder',
                         r'\bbeihilfe', r'\bsteuer', r'umsatzsteuer', r'§\s*\d']),
    ('Vergabeverfahren & Angebot', [r'verfahrensbrief', r'\bangebot', r'\bbieter', r'\bformblatt',
                                    r'\beignung', r'\bzuschlag', r'\bbindefrist', r'\blos\b',
                                    r'\blose\b', r'\bwertung', r'vergabeunterlage',
                                    r'fragenkatalog', r'\bverhandlung', r'frist zur abgabe']),
]

PARTNER_VON_KOMPONENTE = {
    'Ladeeinrichtung': 'Aplitronic',
    'Abrechnungskomponente': 'eRound',
    'Monitoring': 'eRound',
    'OCPI Buchungskalender': 'eRound',
    'Authentifizierungskomponente': 'eRound',
    'Anbindung': 'Reservierungsplattform',
    'Reservierungsplattform': 'Reservierungsplattform',
    'Belegungsdetektion': 'SCS',
    'Dynamische Anzeige': 'SCS',
    'Kennzeichenerfassung': 'SCS',
    'Pönalisierungssystem': 'SCS',
    'Schrankensteuerung': 'SCS',
    'Beschilderung': 'tbd',
    'Schrankenanlage': 'tbd',
}
PARTNER_REIHENFOLGE = ['Aplitronic', 'eRound', 'SCS', 'Reservierungsplattform', 'tbd']

NICHT_TECHNISCH = {'Vergabeverfahren & Angebot', 'Vertrag & Recht', 'Netzanschluss & Energie',
                   'Flächen & Genehmigungen', 'Bau & Dokumentation'}

KOMPONENTEN_REIHENFOLGE = list(KOMPONENTEN.keys())


def norm(t):
    t = (t or '').replace('­', '').replace('(cid:127)', '- ')
    return re.sub(r'\s+', ' ', t).strip()


def lower(t):
    return norm(t).lower()


def finde_komponenten(text):
    lt = lower(text)
    treffer = [k for k, muster in KOMPONENTEN.items() if any(re.search(m, lt) for m in muster)]
    if 'Anbindung' in treffer and 'Reservierungsplattform' not in treffer:
        treffer.append('Reservierungsplattform')
    treffer.sort(key=KOMPONENTEN_REIHENFOLGE.index)
    unsicher = any(re.search(m, lt) for m in UNSICHER)
    return treffer, unsicher


def finde_themenfeld(text):
    lt = lower(text)
    for thema, muster in THEMENFELD:
        if any(re.search(m, lt) for m in muster):
            return thema
    return 'Sonstiges / Zuordnung prüfen'


def finde_partner(komponenten):
    p = []
    for k in komponenten:
        v = PARTNER_VON_KOMPONENTE.get(k)
        if v and v not in p:
            p.append(v)
    p.sort(key=lambda x: PARTNER_REIHENFOLGE.index(x) if x in PARTNER_REIHENFOLGE else 99)
    return ' / '.join(p)


SATZ_ENDE = re.compile(r'(?<=[.!?])\s+(?=[A-ZÄÖÜ0-9„(])')


def saetze(text):
    t = norm(text)
    return [s.strip() for s in SATZ_ENDE.split(t) if s.strip()] if t else []


def kuerzen(text, maxlen=230):
    t = norm(text)
    if len(t) <= maxlen:
        return t
    schnitt = t[:maxlen]
    if ' ' in schnitt:
        schnitt = schnitt[:schnitt.rfind(' ')]
    return schnitt + ' …'


def antworttyp(antwort):
    a = norm(antwort)
    la = a.lower()
    if not la:
        return 'ohne Antwort', None
    m = re.search(r'siehe (?:hierzu )?(?:auch )?(?:die )?(?:antwort(?:en)? (?:auf|zu) )?'
                  r'(?:die )?(?:bieter)?frage[n]? (?:nr\.?\s*)?(\d+(?:\s*(?:,|und|bis|-)\s*\d+)*)',
                  la)
    verweis = m.group(1) if m else None
    if re.match(r'^ja\b|^ja[,.]', la):
        return 'Bestätigt', verweis
    if re.match(r'^nein\b|^nein[,.]', la):
        return 'Verneint', verweis
    if verweis and len(a) < 120:
        return 'Verweis', verweis
    if re.search(r'(wurde|werden|wird)\s+(entsprechend\s+)?(angepasst|aktualisiert|geändert|'
                 r'überarbeitet|ergänzt|korrigiert)', la):
        return 'Anpassung der Unterlagen', verweis
    if re.search(r'(es bleibt bei|bleibt es bei den vorgaben|keine änderung|wird nicht geändert|'
                 r'es gilt der vertrag|der vertrag gilt|die vorgaben gelten|'
                 r'sind die bieter an die vorgaben)', la):
        return 'Vorgaben bleiben unverändert', verweis
    if re.search(r'(beabsichtigt|wird zur verfügung|wird bereitgestellt|'
                 r'werden zur verfügung gestellt|wird der ag)', la):
        return 'Zusage / Ankündigung', verweis
    return 'Klarstellung', verweis


def kernaussage(frage, antwort):
    """Kurze fachliche Kernaussage aus Frage + Antwort.

    Gibt ausschliesslich die Aussage des Auftraggebers wieder; sie wird nicht
    verstaerkt und nicht um eigene Anforderungen ergaenzt.
    """
    a = norm(antwort)
    typ, verweis = antworttyp(a)
    if typ == 'ohne Antwort':
        return 'Keine Antwort des Auftraggebers im Katalog hinterlegt – Klärung offen.'
    s = saetze(a)
    if typ in ('Bestätigt', 'Verneint'):
        kern = ' '.join(s[:2]) if len(s[0]) < 60 else s[0]
        kern = re.sub(r'^(ja|nein)[,.:\s]+', '', kern, flags=re.I)
        praefix = 'Bestätigt' if typ == 'Bestätigt' else 'Verneint'
        return f'{praefix}: {kuerzen(kern)}' if kern else f'{praefix} durch den Auftraggeber.'
    if typ == 'Verweis' and verweis:
        return f'Verweis des Auftraggebers auf die Antwort zu Bieterfrage {verweis}.'
    kern = ' '.join(s[:2]) if s and len(s[0]) < 90 else (s[0] if s else a)
    return f'{typ}: {kuerzen(kern)}'


def baue():
    ergebnis = []
    for r in ROWS:
        nr_roh = norm(r['cells'][0])
        if nr_roh.startswith('Vergabeverfahren'):
            continue  # Seitenkopf, keine Frage
        datum, bezug = norm(r['cells'][1]), norm(r['cells'][2])
        frage, antwort = norm(r['cells'][3]), norm(r['cells'][4])
        if re.fullmatch(r'\d+', nr_roh):
            nr, art = nr_roh, 'Frage'
        elif nr_roh.startswith('Korre'):
            nr, art = 'Korrektur 252', 'Korrektur'
        elif nr_roh.startswith('Hinwe'):
            nr, art = 'Hinweis zu 506', 'Hinweis AG'
        else:
            nr, art = 'Hinweis des AG', 'Hinweis AG'
        volltext = f'{bezug} {frage} {antwort}'
        komps, unsicher = finde_komponenten(volltext)
        thema = finde_themenfeld(volltext)
        if komps:
            komp_str = ' / '.join(komps)
            partner = finde_partner(komps) or 'Zuordnung prüfen'
        elif unsicher:
            komp_str, partner = 'Zuordnung prüfen', 'Zuordnung prüfen'
        elif thema in NICHT_TECHNISCH:
            komp_str, partner = '–', 'offen'
        else:
            komp_str, partner = 'Zuordnung prüfen', 'Zuordnung prüfen'
        ergebnis.append({
            'nr': nr, 'art': art, 'seite': r['page'], 'datum': datum, 'bezug': bezug,
            'frage': frage, 'antwort': antwort, 'themenfeld': thema,
            'komponenten': komp_str, 'partner': partner,
            'kernaussage': kernaussage(frage, antwort),
        })
    return ergebnis


if __name__ == '__main__':
    daten = baue()
    json.dump(daten, open('bieterfragen.json', 'w'), ensure_ascii=False, indent=1)
    from collections import Counter
    print('Datensätze:', len(daten))
    for titel, key in [('Themenfeld', 'themenfeld'), ('Komponente(n)', 'komponenten'),
                       ('Partner', 'partner')]:
        print(f'\n-- {titel} --')
        for k, v in Counter(d[key] for d in daten).most_common(20):
            print(f'{v:5d}  {k}')
    print('\nmit Komponentenzuordnung:',
          sum(1 for d in daten if d['komponenten'] not in ('–', 'Zuordnung prüfen')))
    print('Zuordnung prüfen:', sum(1 for d in daten if d['komponenten'] == 'Zuordnung prüfen'))
