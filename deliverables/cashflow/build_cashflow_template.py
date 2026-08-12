#!/usr/bin/env python3
"""Erzeugt die Cashflow-Vorlage fuer SmartInfra / IoT-Buero.

Projekt : DusL Plus Autostrom
Zeitraum: Juli 2026 - Dezember 2027 (18 Monate, monatlich)

Aufruf:
    python build_cashflow_template.py                 # leere Vorlage
    python build_cashflow_template.py --source ALT.xlsx
        -> Positionsbezeichnungen und bereits erfasste Monatswerte werden
           aus ALT.xlsx uebernommen, das Zeilenraster wird neu aufgebaut.

Es werden keine Geschaefts- oder Planzahlen erfunden; Werte stammen
ausschliesslich aus der Quelldatei.
"""

import argparse
from pathlib import Path

from openpyxl import Workbook, load_workbook
from openpyxl.chart import BarChart, LineChart, Reference
from openpyxl.formatting.rule import CellIsRule
from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
from openpyxl.utils import get_column_letter
from openpyxl.worksheet.properties import PageSetupProperties

HERE = Path(__file__).resolve().parent
OUT = HERE / "Cashflow_SmartInfra_IoT_DusL_Plus_Autostrom_2026_2027.xlsx"

# ----------------------------------------------------------------------------
# Layout-Konstanten
# ----------------------------------------------------------------------------
FONT = "Arial"

# Zeilenkapazitaet der beiden Bloecke (inkl. bereits benannter Positionen)
N_INCOME_ROWS = 30
N_EXPENSE_ROWS = 30

MONTHS = [
    "Jul 26", "Aug 26", "Sep 26", "Okt 26", "Nov 26", "Dez 26",
    "Jan 27", "Feb 27", "Mär 27", "Apr 27", "Mai 27", "Jun 27",
    "Jul 27", "Aug 27", "Sep 27", "Okt 27", "Nov 27", "Dez 27",
]

COL_POS, COL_CAT = 1, 2          # A, B
COL_M1 = 3                       # C  = Jul 26
COL_H2_END = COL_M1 + 5          # H  = Dez 26
COL_Y27_START = COL_M1 + 6       # I  = Jan 27
COL_LAST_M = COL_M1 + 17         # T  = Dez 27
COL_SUM_H2 = COL_LAST_M + 1      # U
COL_SUM_27 = COL_LAST_M + 2      # V
COL_TOTAL = COL_LAST_M + 3       # W

L_M1 = get_column_letter(COL_M1)            # C
L_H2_END = get_column_letter(COL_H2_END)    # H
L_Y27 = get_column_letter(COL_Y27_START)    # I
L_LAST_M = get_column_letter(COL_LAST_M)    # T
L_SUM_H2 = get_column_letter(COL_SUM_H2)    # U
L_SUM_27 = get_column_letter(COL_SUM_27)    # V
L_TOTAL = get_column_letter(COL_TOTAL)      # W

# Zeilenraster (aus der Blockgroesse abgeleitet)
R_TITLE = 1
R_HEAD = 6
R_SEC_IN = R_HEAD + 1                              # 7
R_IN_FIRST = R_SEC_IN + 1                          # 8
R_IN_LAST = R_IN_FIRST + N_INCOME_ROWS - 1
R_SUM_IN = R_IN_LAST + 1
R_SEC_OUT = R_SUM_IN + 2
R_OUT_FIRST = R_SEC_OUT + 1
R_OUT_LAST = R_OUT_FIRST + N_EXPENSE_ROWS - 1
R_SUM_OUT = R_OUT_LAST + 1
R_SEC_KPI = R_SUM_OUT + 2
R_KPI_IN = R_SEC_KPI + 1
R_KPI_OUT = R_KPI_IN + 1
R_KPI_NET = R_KPI_OUT + 1
R_KPI_CUM = R_KPI_NET + 1
R_LEGEND = R_KPI_CUM + 3

META_DEFAULT = [
    "Cashflow-Planung",
    "Bereich:  SmartInfra / IoT-Büro",
    "Zeitraum:  Juli 2026 – Dezember 2027  (18 Monate, monatliche Granularität)",
    "Bitte ausschließlich die gelb hinterlegten Zellen befüllen. "
    "Graue und grüne Zellen sind formelbasiert.",
]

INCOME_DEFAULT = [
    "Projektumsätze",
    "Dienstleistungen",
    "Hardware / IoT",
    "Sonstige Einnahmen",
]
EXPENSE_DEFAULT = [
    "Personalkosten",
    "Hardware / Sensorik",
    "Gateways / Kommunikationstechnik",
    "SIM / Mobilfunk / Connectivity",
    "Software / Lizenzen",
    "Cloud / Hosting",
    "Fremdleistungen",
    "Installation / Montage",
    "Dienstreisen / Fahrtkosten",
    "Büro / Betriebsmittel",
    "Sonstige Kosten",
]

# Farben (dezentes Controlling-Layout)
C_HEAD = "1F3864"        # dunkelblau
C_SECTION = "D9E2F3"     # helles blau
C_INPUT = "FFF9E1"       # helles gelb  -> Eingabezellen
C_CALC = "F2F2F2"        # hellgrau     -> berechnete Zellen
C_RESULT = "E2EFDA"      # helles gruen -> Ergebniszeilen
C_BORDER = "BFBFBF"

EUR = '#,##0.00\\ "€";[Red]-#,##0.00\\ "€";"–"'

thin = Side(style="thin", color=C_BORDER)
BORDER = Border(left=thin, right=thin, top=thin, bottom=thin)
TOP_LINE = Border(left=thin, right=thin, top=Side(style="medium", color="8EA9DB"),
                  bottom=thin)

FILL_INPUT = PatternFill("solid", fgColor=C_INPUT)
FILL_CALC = PatternFill("solid", fgColor=C_CALC)
FILL_RESULT = PatternFill("solid", fgColor=C_RESULT)
FILL_SECTION = PatternFill("solid", fgColor=C_SECTION)
FILL_HEAD = PatternFill("solid", fgColor=C_HEAD)
NO_FILL = PatternFill(fill_type=None)


def f(size=10, bold=False, color="000000", italic=False):
    return Font(name=FONT, size=size, bold=bold, color=color, italic=italic)


# ----------------------------------------------------------------------------
# Uebernahme aus einer bestehenden Datei
# ----------------------------------------------------------------------------
def read_source(path):
    """Liest Kopfzeilen, Positionsnamen und erfasste Monatswerte aus einer
    frueheren Fassung dieser Vorlage. Erkennt das Zeilenraster anhand der
    Abschnittsmarken, ist also gegen verschobene Zeilen robust."""
    ws = load_workbook(path, data_only=False)["Cashflow"]

    marks = {}
    for row in ws.iter_rows(min_col=1, max_col=1):
        v = row[0].value
        if isinstance(v, str):
            key = v.strip().lower()
            if key.startswith("1 ") or "einnahmen" == key:
                marks.setdefault("in", row[0].row)
            if key.startswith("2 "):
                marks.setdefault("out", row[0].row)
            if key.startswith("summe einnahmen"):
                marks.setdefault("sum_in", row[0].row)
            if key.startswith("summe ausgaben"):
                marks.setdefault("sum_out", row[0].row)
            if key.startswith("position"):
                marks.setdefault("head", row[0].row)
    required = {"in", "out", "sum_in", "sum_out", "head"}
    missing = required - marks.keys()
    if missing:
        raise SystemExit(f"Quelldatei: Abschnittsmarken nicht gefunden: {missing}")

    def block(first, last):
        out = []
        for r in range(first, last + 1):
            label = ws.cell(row=r, column=COL_POS).value
            values = {}
            for col in range(COL_M1, COL_LAST_M + 1):
                v = ws.cell(row=r, column=col).value
                if isinstance(v, (int, float)):
                    values[col] = v
            if label or values:
                out.append((label, values))
        return out

    meta = []
    for r in range(1, marks["head"]):
        v = ws.cell(row=r, column=COL_POS).value
        if isinstance(v, str) and v.strip():
            meta.append(v)

    return {
        "meta": meta or META_DEFAULT,
        "income": block(marks["in"] + 1, marks["sum_in"] - 1),
        "expense": block(marks["out"] + 1, marks["sum_out"] - 1),
    }


# ----------------------------------------------------------------------------
# Aufbau der Arbeitsmappe
# ----------------------------------------------------------------------------
def build(meta, income, expense):
    if len(income) > N_INCOME_ROWS or len(expense) > N_EXPENSE_ROWS:
        raise SystemExit("Quelldatei enthält mehr Positionen als das neue Raster "
                         "vorsieht – N_INCOME_ROWS / N_EXPENSE_ROWS erhöhen.")

    wb = Workbook()
    ws = wb.active
    ws.title = "Cashflow"

    # ---- Kopfbereich --------------------------------------------------------
    for i, text in enumerate(meta[:R_HEAD - 1]):
        c = ws.cell(row=R_TITLE + i, column=COL_POS, value=text)
        if i == 0:
            c.font = f(16, True, C_HEAD)
        elif i == len(meta[:R_HEAD - 1]) - 1:
            c.font = f(9, italic=True, color="808080")
        else:
            c.font = f(10)
        c.alignment = Alignment(vertical="center")

    # ---- Tabellenkopf -------------------------------------------------------
    headers = ["Position", "Kategorie"] + MONTHS + [
        "Summe H2 2026", "Summe 2027", "Gesamt"]
    for i, text in enumerate(headers, start=1):
        c = ws.cell(row=R_HEAD, column=i, value=text)
        c.font = f(10, True, "FFFFFF")
        c.fill = FILL_HEAD
        c.border = BORDER
        c.alignment = Alignment(
            horizontal="left" if i <= 2 else "center",
            vertical="center",
            wrap_text=i > 2,
        )
    ws.row_dimensions[R_HEAD].height = 30

    def section(row, title):
        for col in range(COL_POS, COL_TOTAL + 1):
            c = ws.cell(row=row, column=col)
            c.fill = FILL_SECTION
            c.border = BORDER
        c = ws.cell(row=row, column=COL_POS, value=title)
        c.font = f(11, True, C_HEAD)
        ws.row_dimensions[row].height = 20

    def data_row(row, position, kategorie, values=None):
        """Eingabezeile: 18 Monatszellen + 3 Summenformeln."""
        p = ws.cell(row=row, column=COL_POS, value=position)
        p.font = f(10)
        p.fill = NO_FILL if position else FILL_INPUT
        p.border = BORDER
        p.alignment = Alignment(indent=1)

        k = ws.cell(row=row, column=COL_CAT, value=kategorie)
        k.font = f(10, color="595959")
        k.border = BORDER

        for col in range(COL_M1, COL_LAST_M + 1):
            c = ws.cell(row=row, column=col, value=(values or {}).get(col))
            c.fill = FILL_INPUT
            c.border = BORDER
            c.number_format = EUR
            c.font = f(10, color="0000FF")   # blau = manuelle Eingabe

        for col, formula in (
            (COL_SUM_H2, f"=SUM({L_M1}{row}:{L_H2_END}{row})"),
            (COL_SUM_27, f"=SUM({L_Y27}{row}:{L_LAST_M}{row})"),
            (COL_TOTAL, f"=SUM({L_M1}{row}:{L_LAST_M}{row})"),
        ):
            c = ws.cell(row=row, column=col, value=formula)
            c.fill = FILL_CALC
            c.border = BORDER
            c.number_format = EUR
            c.font = f(10, bold=(col == COL_TOTAL))

    def total_row(row, label, kategorie, first, last):
        p = ws.cell(row=row, column=COL_POS, value=label)
        p.font = f(10, True, C_HEAD)
        p.fill = FILL_RESULT
        p.border = TOP_LINE

        k = ws.cell(row=row, column=COL_CAT, value=kategorie)
        k.font = f(10, color="595959")
        k.fill = FILL_RESULT
        k.border = TOP_LINE

        for col in range(COL_M1, COL_TOTAL + 1):
            letter = get_column_letter(col)
            c = ws.cell(row=row, column=col,
                        value=f"=SUM({letter}{first}:{letter}{last})")
            c.font = f(10, True)
            c.fill = FILL_RESULT
            c.border = TOP_LINE
            c.number_format = EUR

    # ---- 1. Einnahmen -------------------------------------------------------
    section(R_SEC_IN, "1  EINNAHMEN")
    for i in range(N_INCOME_ROWS):
        label, values = income[i] if i < len(income) else (None, {})
        data_row(R_IN_FIRST + i, label, "Einnahmen", values)
    total_row(R_SUM_IN, "Summe Einnahmen", "Einnahmen", R_IN_FIRST, R_IN_LAST)

    # ---- 2. Ausgaben --------------------------------------------------------
    section(R_SEC_OUT, "2  AUSGABEN")
    for i in range(N_EXPENSE_ROWS):
        label, values = expense[i] if i < len(expense) else (None, {})
        data_row(R_OUT_FIRST + i, label, "Ausgaben", values)
    total_row(R_SUM_OUT, "Summe Ausgaben", "Ausgaben", R_OUT_FIRST, R_OUT_LAST)

    # ---- 3. Kennzahlen ------------------------------------------------------
    section(R_SEC_KPI, "3  KENNZAHLEN (automatisch berechnet)")

    def kpi_row(row, label, formula_for_col, bold=False, fill=FILL_CALC):
        p = ws.cell(row=row, column=COL_POS, value=label)
        p.font = f(10, bold, C_HEAD)
        p.fill = fill
        p.border = BORDER

        k = ws.cell(row=row, column=COL_CAT, value="Kennzahl")
        k.font = f(10, color="595959")
        k.fill = fill
        k.border = BORDER

        for col in range(COL_M1, COL_TOTAL + 1):
            c = ws.cell(row=row, column=col, value=formula_for_col(col))
            c.font = f(10, bold)
            c.fill = fill
            c.border = BORDER
            c.number_format = EUR

    kpi_row(R_KPI_IN, "Summe Einnahmen",
            lambda col: f"={get_column_letter(col)}{R_SUM_IN}")
    kpi_row(R_KPI_OUT, "Summe Ausgaben",
            lambda col: f"={get_column_letter(col)}{R_SUM_OUT}")
    kpi_row(R_KPI_NET, "Netto-Cashflow (Monat)",
            lambda col: (f"={get_column_letter(col)}{R_KPI_IN}"
                         f"-{get_column_letter(col)}{R_KPI_OUT}"),
            bold=True, fill=FILL_RESULT)

    def cum_formula(col):
        """Kumulierter Cashflow: fortlaufend ueber die Monate,
        in den Summenspalten der jeweilige Periodenendstand."""
        if col == COL_M1:
            return f"={L_M1}{R_KPI_NET}"
        if col <= COL_LAST_M:
            prev = get_column_letter(col - 1)
            return f"={prev}{R_KPI_CUM}+{get_column_letter(col)}{R_KPI_NET}"
        if col == COL_SUM_H2:
            return f"={L_H2_END}{R_KPI_CUM}"          # Stand 31.12.2026
        return f"={L_LAST_M}{R_KPI_CUM}"              # Stand 31.12.2027

    kpi_row(R_KPI_CUM, "Kumulierter Cashflow", cum_formula, bold=True,
            fill=FILL_RESULT)

    # ---- Legende ------------------------------------------------------------
    legend = [
        ("Legende", None, f(10, True, C_HEAD)),
        ("Eingabezelle – bitte manuell befüllen (Plan- bzw. Ist-Werte, blaue Schrift)",
         C_INPUT, f(9)),
        ("Automatisch berechnet – nicht überschreiben", C_CALC, f(9)),
        ("Ergebniszeile – automatisch berechnet", C_RESULT, f(9)),
        ("Beispielformat einer Eingabe:  1234,50  →  Anzeige 1.234,50 €   "
         "(Ausgaben werden als positive Beträge erfasst)",
         None, f(9, italic=True, color="808080")),
        (f"Freie Projektzeilen: Einnahmen Zeile {R_IN_FIRST}–{R_IN_LAST}, "
         f"Ausgaben Zeile {R_OUT_FIRST}–{R_OUT_LAST}. Werden noch mehr Zeilen "
         "benötigt, innerhalb dieser Blöcke einfügen – alle Summen erweitern "
         "sich automatisch.", None, f(9, italic=True, color="808080")),
    ]
    for i, (text, fill, font) in enumerate(legend):
        r = R_LEGEND + i
        if fill:
            marker = ws.cell(row=r, column=COL_POS)
            marker.fill = PatternFill("solid", fgColor=fill)
            marker.border = BORDER
            c = ws.cell(row=r, column=COL_CAT, value=text)
        else:
            c = ws.cell(row=r, column=COL_POS, value=text)
        c.font = font

    # ---- Bedingte Formatierung ---------------------------------------------
    ws.conditional_formatting.add(
        f"{L_M1}{R_IN_FIRST}:{L_TOTAL}{R_KPI_CUM}",
        CellIsRule(operator="lessThan", formula=["0"],
                   font=Font(name=FONT, size=10, color="9C0006"),
                   fill=PatternFill("solid", bgColor="FFC7CE")))
    result_range = f"{L_M1}{R_KPI_NET}:{L_TOTAL}{R_KPI_CUM}"
    ws.conditional_formatting.add(
        result_range, CellIsRule(operator="greaterThan", formula=["0"],
                                 font=Font(name=FONT, size=10, bold=True,
                                           color="006100"),
                                 fill=PatternFill("solid", bgColor="C6EFCE")))
    ws.conditional_formatting.add(
        result_range, CellIsRule(operator="lessThan", formula=["0"],
                                 font=Font(name=FONT, size=10, bold=True,
                                           color="9C0006"),
                                 fill=PatternFill("solid", bgColor="FFC7CE")))

    # ---- Spaltenbreiten / Fixierung / Druck ---------------------------------
    ws.column_dimensions["A"].width = 36
    ws.column_dimensions["B"].width = 14
    for col in range(COL_M1, COL_LAST_M + 1):
        ws.column_dimensions[get_column_letter(col)].width = 13
    for col in (COL_SUM_H2, COL_SUM_27, COL_TOTAL):
        ws.column_dimensions[get_column_letter(col)].width = 16

    ws.freeze_panes = f"{L_M1}{R_HEAD + 1}"        # Kopfzeile + Spalten A/B
    ws.sheet_view.showGridLines = False

    ws.print_area = f"A1:{L_TOTAL}{R_LEGEND + len(legend) - 1}"
    ws.print_title_rows = f"{R_HEAD}:{R_HEAD}"
    ws.print_title_cols = "$A:$B"
    ws.page_setup.orientation = "landscape"
    ws.page_setup.paperSize = ws.PAPERSIZE_A4
    ws.page_setup.fitToWidth = 1
    ws.page_setup.fitToHeight = 0
    ws.sheet_properties.pageSetUpPr = PageSetupProperties(fitToPage=True)
    ws.page_margins.left = ws.page_margins.right = 0.4
    ws.page_margins.top = ws.page_margins.bottom = 0.5
    ws.oddFooter.center.text = "DusL Plus Autostrom – Cashflow  |  Seite &P von &N"
    ws.oddFooter.center.size = 8

    # ========================================================================
    # Blatt 2: Übersicht
    # ========================================================================
    ov = wb.create_sheet("Übersicht")

    ov["A1"] = "Übersicht Cashflow – DusL Plus Autostrom"
    ov["A1"].font = f(16, True, C_HEAD)
    ov["A2"] = "SmartInfra / IoT-Büro  ·  Juli 2026 – Dezember 2027"
    ov["A2"].font = f(10, color="595959")
    ov["A3"] = "Alle Werte werden automatisch aus dem Blatt „Cashflow“ übernommen."
    ov["A3"].font = f(9, italic=True, color="808080")

    kpis = [
        ("H2 2026 (Jul – Dez 2026)", None, None),
        ("Einnahmen H2 2026", f"=Cashflow!{L_SUM_H2}{R_KPI_IN}", False),
        ("Ausgaben H2 2026", f"=Cashflow!{L_SUM_H2}{R_KPI_OUT}", False),
        ("Netto-Cashflow H2 2026", f"=Cashflow!{L_SUM_H2}{R_KPI_NET}", True),
        ("Geschäftsjahr 2027", None, None),
        ("Einnahmen 2027", f"=Cashflow!{L_SUM_27}{R_KPI_IN}", False),
        ("Ausgaben 2027", f"=Cashflow!{L_SUM_27}{R_KPI_OUT}", False),
        ("Netto-Cashflow 2027", f"=Cashflow!{L_SUM_27}{R_KPI_NET}", True),
        ("Gesamtzeitraum (18 Monate)", None, None),
        ("Gesamteinnahmen", f"=Cashflow!{L_TOTAL}{R_KPI_IN}", False),
        ("Gesamtausgaben", f"=Cashflow!{L_TOTAL}{R_KPI_OUT}", False),
        ("Gesamt-Netto-Cashflow", f"=Cashflow!{L_TOTAL}{R_KPI_NET}", True),
    ]

    start = 5
    ov.cell(row=start, column=1, value="Kennzahl").font = f(10, True, "FFFFFF")
    ov.cell(row=start, column=2, value="Betrag").font = f(10, True, "FFFFFF")
    for col in (1, 2):
        c = ov.cell(row=start, column=col)
        c.fill = FILL_HEAD
        c.border = BORDER
        c.alignment = Alignment(horizontal="left" if col == 1 else "center")

    r = start + 1
    for label, formula, bold in kpis:
        if formula is None:                       # Zwischenüberschrift
            c = ov.cell(row=r, column=1, value=label)
            c.font = f(10, True, C_HEAD)
            c.fill = FILL_SECTION
            c.border = BORDER
            c2 = ov.cell(row=r, column=2)
            c2.fill = FILL_SECTION
            c2.border = BORDER
        else:
            c = ov.cell(row=r, column=1, value=label)
            c.font = f(10, bold)
            c.border = BORDER
            c.alignment = Alignment(indent=1)
            v = ov.cell(row=r, column=2, value=formula)
            v.font = f(10, bold)
            v.fill = FILL_RESULT if bold else FILL_CALC
            v.border = BORDER
            v.number_format = EUR
        r += 1
    last_kpi_row = r - 1

    ov.conditional_formatting.add(
        f"B{start + 1}:B{last_kpi_row}",
        CellIsRule(operator="lessThan", formula=["0"],
                   font=Font(name=FONT, size=10, bold=True, color="9C0006"),
                   fill=PatternFill("solid", bgColor="FFC7CE")))
    ov.conditional_formatting.add(
        f"B{start + 1}:B{last_kpi_row}",
        CellIsRule(operator="greaterThan", formula=["0"],
                   font=Font(name=FONT, size=10, bold=True, color="006100"),
                   fill=PatternFill("solid", bgColor="C6EFCE")))

    ov.column_dimensions["A"].width = 34
    ov.column_dimensions["B"].width = 20
    ov.sheet_view.showGridLines = False
    ov.page_setup.orientation = "portrait"
    ov.page_setup.paperSize = ov.PAPERSIZE_A4
    ov.page_setup.fitToWidth = 1
    ov.page_setup.fitToHeight = 0
    ov.sheet_properties.pageSetUpPr = PageSetupProperties(fitToPage=True)

    # ---- Diagramme ----------------------------------------------------------
    cats = Reference(ws, min_col=COL_M1, max_col=COL_LAST_M,
                     min_row=R_HEAD, max_row=R_HEAD)

    bar = BarChart()
    bar.type = "col"
    bar.grouping = "clustered"
    bar.title = "Einnahmen vs. Ausgaben (monatlich)"
    bar.y_axis.title = "EUR"
    bar.y_axis.numFmt = '#,##0'
    bar.height, bar.width = 8, 26
    bar.gapWidth = 40
    bar.add_data(Reference(ws, min_col=COL_POS, max_col=COL_LAST_M,
                           min_row=R_KPI_IN, max_row=R_KPI_OUT),
                 titles_from_data=True, from_rows=True)
    bar.set_categories(cats)
    bar.series[0].graphicalProperties.solidFill = "4472C4"
    bar.series[1].graphicalProperties.solidFill = "C00000"
    ov.add_chart(bar, "D5")

    line = LineChart()
    line.title = "Netto-Cashflow und kumulierter Cashflow (monatlich)"
    line.y_axis.title = "EUR"
    line.y_axis.numFmt = '#,##0'
    line.height, line.width = 8, 26
    line.add_data(Reference(ws, min_col=COL_POS, max_col=COL_LAST_M,
                            min_row=R_KPI_NET, max_row=R_KPI_CUM),
                  titles_from_data=True, from_rows=True)
    line.set_categories(cats)
    line.series[0].graphicalProperties.line.solidFill = "1F3864"
    line.series[1].graphicalProperties.line.solidFill = "70AD47"
    line.series[1].graphicalProperties.line.dashStyle = "dash"
    ov.add_chart(line, "D22")

    return wb


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--source", help="bestehende Datei, deren Positionen und "
                                     "Werte übernommen werden")
    ap.add_argument("--out", default=str(OUT))
    args = ap.parse_args()

    if args.source:
        src = read_source(args.source)
        meta, income, expense = src["meta"], src["income"], src["expense"]
        print(f"übernommen: {len(income)} Einnahmen-, {len(expense)} Ausgabenzeilen")
    else:
        meta = META_DEFAULT
        income = [(n, {}) for n in INCOME_DEFAULT]
        expense = [(n, {}) for n in EXPENSE_DEFAULT]

    build(meta, income, expense).save(args.out)
    print(f"geschrieben: {args.out}")


if __name__ == "__main__":
    main()
