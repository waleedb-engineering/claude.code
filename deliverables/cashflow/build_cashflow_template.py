#!/usr/bin/env python3
"""Erzeugt die Cashflow-Mappe fuer SmartInfra / IoT-Buero.

Projekt : DusL Plus Autostrom
Zeitraum: Juli 2026 - Dezember 2027 (18 Monate, monatlich)

Datenfluss:  Auftraege  ->  Cashflow  ->  Uebersicht

    Auftraege  zentrale Eingabe (echte Excel-Tabelle "tblAuftraege")
    Cashflow   monatliche Aggregation per SUMIFS ueber echte Datumsgrenzen
    Uebersicht Management-Zusammenfassung, zieht aus dem Cashflow

Aufruf:
    python build_cashflow_template.py                  # leere Vorlage
    python build_cashflow_template.py --source ALT.xlsx
        -> Positionsbezeichnungen (Kostenstellen-Zeilen) werden aus ALT.xlsx
           uebernommen. Betraege werden bewusst NICHT uebernommen: der
           Cashflow wird nicht mehr manuell gepflegt, alle Betraege stammen
           ab sofort aus dem Reiter "Auftraege".

Es werden keine Auftraege, Umsaetze oder Kosten erfunden.
"""

import argparse
from datetime import date
from pathlib import Path

from openpyxl import Workbook, load_workbook
from openpyxl.chart import BarChart, LineChart, Reference
from openpyxl.formatting.rule import CellIsRule
from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
from openpyxl.utils import get_column_letter
from openpyxl.worksheet.datavalidation import DataValidation
from openpyxl.worksheet.properties import PageSetupProperties
from openpyxl.worksheet.table import Table, TableStyleInfo

HERE = Path(__file__).resolve().parent
OUT = HERE / "Cashflow_SmartInfra_IoT_DusL_Plus_Autostrom_2026_2027.xlsx"

# ----------------------------------------------------------------------------
# Layout-Konstanten
# ----------------------------------------------------------------------------
FONT = "Arial"

N_INCOME_ROWS = 30          # Kostenstellen-Zeilen im Einnahmenblock
N_EXPENSE_ROWS = 30         # Kostenstellen-Zeilen im Ausgabenblock
N_ORDER_ROWS = 150          # vorbereitete Zeilen der Auftragstabelle

MONTH_STARTS = [date(2026, 7, 1)]
for _ in range(17):
    _y, _m = MONTH_STARTS[-1].year, MONTH_STARTS[-1].month + 1
    MONTH_STARTS.append(date(_y + (_m > 12), 1 if _m > 12 else _m, 1))

MONTHS = [
    "Jul 26", "Aug 26", "Sep 26", "Okt 26", "Nov 26", "Dez 26",
    "Jan 27", "Feb 27", "Mär 27", "Apr 27", "Mai 27", "Jun 27",
    "Jul 27", "Aug 27", "Sep 27", "Okt 27", "Nov 27", "Dez 27",
]
assert len(MONTHS) == len(MONTH_STARTS) == 18

THEMENFELDER = ["IoT", "EDM", "Parking", "LLM"]
KATEGORIEN = ["Hardware", "Hardware + Dienstleistung", "Lizenzen", "Dienstleistung"]

COL_POS, COL_KST = 1, 2          # A = Position, B = Kostenstelle (Filterschlüssel)
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

# Zeilenraster des Cashflow-Blatts (aus den Blockgrößen abgeleitet)
R_TITLE = 1
R_MONTHKEY = 5                                     # ausgeblendet: echte Monatsanfänge
R_HEAD = 6
R_SEC_IN = R_HEAD + 1
R_IN_FIRST = R_SEC_IN + 1
R_IN_LAST = R_IN_FIRST + N_INCOME_ROWS - 1
R_IN_REST = R_IN_LAST + 1                          # ohne Kostenstellen-Zuordnung
R_SUM_IN = R_IN_REST + 1
R_SEC_OUT = R_SUM_IN + 2
R_OUT_FIRST = R_SEC_OUT + 1
R_OUT_LAST = R_OUT_FIRST + N_EXPENSE_ROWS - 1
R_OUT_REST = R_OUT_LAST + 1
R_SUM_OUT = R_OUT_REST + 1
R_SEC_KPI = R_SUM_OUT + 2
R_KPI_IN = R_SEC_KPI + 1
R_KPI_OUT = R_KPI_IN + 1
R_KPI_NET = R_KPI_OUT + 1
R_KPI_CUM = R_KPI_NET + 1
R_SEC_TF = R_KPI_CUM + 2                           # Auswertung nach Themenfeld
R_TF_FIRST = R_SEC_TF + 1
R_SEC_KAT = R_TF_FIRST + 2 * len(THEMENFELDER) + 1  # Auswertung nach Kategorie
R_KAT_FIRST = R_SEC_KAT + 1
R_LEGEND = R_KAT_FIRST + 2 * len(KATEGORIEN) + 2

# Auftragsblatt
A_TITLE = 1
A_HEAD = 6
A_FIRST = A_HEAD + 1
A_LAST = A_HEAD + N_ORDER_ROWS
TBL = "tblAuftraege"
ORDER_COLS = ["Themenfeld", "Kategorie", "Auftrag", "Kostenstelle",
              "Datum Einnahmen", "Datum Ausgaben", "Einnahmen", "Ausgaben",
              "Auftragswahrscheinlichkeit"]
C_EINNAHMEN = f"{TBL}[Einnahmen]"
C_AUSGABEN = f"{TBL}[Ausgaben]"
C_DAT_EIN = f"{TBL}[Datum Einnahmen]"
C_DAT_AUS = f"{TBL}[Datum Ausgaben]"
C_KST = f"{TBL}[Kostenstelle]"
C_TF = f"{TBL}[Themenfeld]"
C_KAT = f"{TBL}[Kategorie]"

META_DEFAULT = [
    "Cashflow-Planung",
    "Bereich:  SmartInfra / IoT-Büro",
    "Zeitraum:  Juli 2026 – Dezember 2027  (18 Monate, monatliche Granularität)",
]
META_HINT = ("Alle Beträge werden automatisch aus dem Reiter „Aufträge“ berechnet – "
             "im Cashflow werden nur Position und Kostenstelle (gelb) gepflegt.")

INCOME_DEFAULT = ["Projektumsätze", "Dienstleistungen", "Hardware / IoT",
                  "Sonstige Einnahmen"]
EXPENSE_DEFAULT = ["Personalkosten", "Hardware / Sensorik",
                   "Gateways / Kommunikationstechnik",
                   "SIM / Mobilfunk / Connectivity", "Software / Lizenzen",
                   "Cloud / Hosting", "Fremdleistungen", "Installation / Montage",
                   "Dienstreisen / Fahrtkosten", "Büro / Betriebsmittel",
                   "Sonstige Kosten"]

# Farben (dezentes Controlling-Layout)
C_HEAD = "1F3864"        # dunkelblau
C_SECTION = "D9E2F3"     # helles blau
C_INPUT = "FFF9E1"       # helles gelb  -> Eingabezellen
C_CALC = "F2F2F2"        # hellgrau     -> berechnete Zellen
C_RESULT = "E2EFDA"      # helles gruen -> Ergebniszeilen
C_BORDER = "BFBFBF"

EUR = '#,##0.00\\ "€";[Red]-#,##0.00\\ "€";"–"'
DATE_FMT = "DD.MM.YYYY"
PCT = "0 %"

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


def period_sum(col, row):
    """Formel der Summenspalten U/V/W für eine Zeile."""
    if col == COL_SUM_H2:
        return f"=SUM({L_M1}{row}:{L_H2_END}{row})"
    if col == COL_SUM_27:
        return f"=SUM({L_Y27}{row}:{L_LAST_M}{row})"
    return f"=SUM({L_M1}{row}:{L_LAST_M}{row})"


def month_window(col):
    """Datumsgrenzen des Monats einer Spalte: >= Monatsanfang, < Folgemonat.
    Die Monatsanfänge stehen als echte Datumswerte in der ausgeblendeten
    Zeile 5, verglichen wird also nie mit Text wie "Okt 26"."""
    letter = get_column_letter(col)
    return (f'">="&{letter}${R_MONTHKEY}',
            f'"<"&EDATE({letter}${R_MONTHKEY},1)')


def sumifs(value_col, date_col, col, extra=None):
    lo, hi = month_window(col)
    parts = [value_col, date_col, lo, date_col, hi]
    if extra:
        parts += list(extra)
    return "=SUMIFS(" + ",".join(parts) + ")"


# ----------------------------------------------------------------------------
# Uebernahme aus einer bestehenden Datei
# ----------------------------------------------------------------------------
def read_source(path):
    """Liest Kopfzeilen und Positionsbezeichnungen aus einer frueheren Fassung.
    Das Zeilenraster wird ueber die Abschnittsmarken erkannt."""
    ws = load_workbook(path, data_only=False)["Cashflow"]

    marks = {}
    for row in ws.iter_rows(min_col=1, max_col=1):
        v = row[0].value
        if isinstance(v, str):
            key = v.strip().lower()
            if key.startswith("1 "):
                marks.setdefault("in", row[0].row)
            if key.startswith("2 "):
                marks.setdefault("out", row[0].row)
            if key.startswith("summe einnahmen"):
                marks.setdefault("sum_in", row[0].row)
            if key.startswith("summe ausgaben"):
                marks.setdefault("sum_out", row[0].row)
            if key.startswith("position"):
                marks.setdefault("head", row[0].row)
    missing = {"in", "out", "sum_in", "sum_out", "head"} - marks.keys()
    if missing:
        raise SystemExit(f"Quelldatei: Abschnittsmarken nicht gefunden: {missing}")

    def labels(first, last):
        out = []
        for r in range(first, last + 1):
            v = ws.cell(row=r, column=COL_POS).value
            if isinstance(v, str) and v.strip() and not v.lower().startswith(
                    ("summe", "nicht zugeordnet")):
                out.append(v.strip())
        return out

    meta = []
    for r in range(1, marks["head"]):
        v = ws.cell(row=r, column=COL_POS).value
        if isinstance(v, str) and v.strip() and not v.startswith("Alle Beträge"):
            meta.append(v.strip())

    return {
        "meta": meta[:3] or META_DEFAULT,
        "income": labels(marks["in"] + 1, marks["sum_in"] - 1),
        "expense": labels(marks["out"] + 1, marks["sum_out"] - 1),
    }


# ----------------------------------------------------------------------------
# Blatt "Aufträge"
# ----------------------------------------------------------------------------
def build_orders(wb):
    ws = wb.create_sheet("Aufträge")

    ws.cell(row=A_TITLE, column=1, value="Aufträge – zentrale Datenerfassung"
            ).font = f(16, True, C_HEAD)
    ws.cell(row=2, column=1,
            value="SmartInfra / IoT-Büro  ·  DusL Plus Autostrom").font = f(10)
    ws.cell(row=3, column=1,
            value="Jeder Auftrag bzw. finanzielle Vorgang wird hier einmalig erfasst. "
                  "Der Reiter „Cashflow“ aggregiert daraus automatisch nach Monat."
            ).font = f(9, italic=True, color="808080")
    ws.cell(row=4, column=1,
            value="Datum Einnahmen und Datum Ausgaben sind unabhängig – ein Auftrag "
                  "kann z. B. im September Ausgaben und erst im November Einnahmen haben. "
                  "LLM = Lastmanagement."
            ).font = f(9, italic=True, color="808080")

    for i, name in enumerate(ORDER_COLS, start=1):
        c = ws.cell(row=A_HEAD, column=i, value=name)
        c.font = f(10, True, "FFFFFF")
        c.fill = FILL_HEAD
        c.border = BORDER
        c.alignment = Alignment(horizontal="center", vertical="center",
                                wrap_text=True)
    ws.row_dimensions[A_HEAD].height = 30

    fmt = {5: DATE_FMT, 6: DATE_FMT, 7: EUR, 8: EUR, 9: PCT}
    for r in range(A_FIRST, A_LAST + 1):
        for col in range(1, len(ORDER_COLS) + 1):
            c = ws.cell(row=r, column=col)
            c.fill = FILL_INPUT
            c.border = BORDER
            c.font = f(10, color="0000FF")      # blau = manuelle Eingabe
            if col in fmt:
                c.number_format = fmt[col]
            if col <= 4:
                c.alignment = Alignment(horizontal="left")

    tab = Table(displayName=TBL, ref=f"A{A_HEAD}:I{A_LAST}")
    tab.tableStyleInfo = TableStyleInfo(name="TableStyleLight8", showRowStripes=False,
                                        showColumnStripes=False,
                                        showFirstColumn=False, showLastColumn=False)
    ws.add_table(tab)

    # Dropdowns / Wertebereiche – bewusst etwas über die Tabelle hinaus, damit
    # sie auch beim Erweitern der Tabelle nach unten sofort greifen.
    extra = A_LAST + 200
    dv_tf = DataValidation(type="list", formula1=f'"{",".join(THEMENFELDER)}"',
                           allow_blank=True, showDropDown=False)
    dv_tf.error = "Bitte IoT, EDM, Parking oder LLM auswählen."
    dv_tf.errorTitle = "Ungültiges Themenfeld"
    dv_kat = DataValidation(type="list", formula1=f'"{",".join(KATEGORIEN)}"',
                            allow_blank=True, showDropDown=False)
    dv_kat.error = ("Bitte Hardware, Hardware + Dienstleistung, Lizenzen "
                    "oder Dienstleistung auswählen.")
    dv_kat.errorTitle = "Ungültige Kategorie"
    dv_pct = DataValidation(type="decimal", operator="between",
                            formula1="0", formula2="1", allow_blank=True)
    dv_pct.errorTitle = "Ungültige Wahrscheinlichkeit"
    dv_pct.error = ("Zulässig sind 0 % bis 100 %. Eingabe z. B. als 20% "
                    "oder als 0,2.")
    dv_dat = DataValidation(type="date", operator="between",
                            formula1="DATE(2020,1,1)", formula2="DATE(2040,12,31)",
                            allow_blank=True)
    dv_dat.errorTitle = "Ungültiges Datum"
    dv_dat.error = "Bitte ein Datum im Format TT.MM.JJJJ eintragen."

    for dv, rng in ((dv_tf, f"A{A_FIRST}:A{extra}"),
                    (dv_kat, f"B{A_FIRST}:B{extra}"),
                    (dv_dat, f"E{A_FIRST}:F{extra}"),
                    (dv_pct, f"I{A_FIRST}:I{extra}")):
        ws.add_data_validation(dv)
        dv.add(rng)

    for col, width in zip("ABCDEFGHI",
                          (14, 26, 20, 18, 17, 17, 16, 16, 22)):
        ws.column_dimensions[col].width = width

    ws.freeze_panes = f"A{A_FIRST}"
    ws.sheet_view.showGridLines = False
    ws.print_area = f"A1:I{A_LAST}"
    ws.print_title_rows = f"{A_HEAD}:{A_HEAD}"
    ws.page_setup.orientation = "landscape"
    ws.page_setup.paperSize = ws.PAPERSIZE_A4
    ws.page_setup.fitToWidth = 1
    ws.page_setup.fitToHeight = 0
    ws.sheet_properties.pageSetUpPr = PageSetupProperties(fitToPage=True)
    ws.oddFooter.center.text = "DusL Plus Autostrom – Aufträge  |  Seite &P von &N"
    ws.oddFooter.center.size = 8
    return ws


# ----------------------------------------------------------------------------
# Blatt "Cashflow"
# ----------------------------------------------------------------------------
def build_cashflow(wb, meta, income, expense):
    if len(income) > N_INCOME_ROWS or len(expense) > N_EXPENSE_ROWS:
        raise SystemExit("Mehr Positionen als Zeilen – N_INCOME_ROWS / "
                         "N_EXPENSE_ROWS erhöhen.")

    ws = wb.active
    ws.title = "Cashflow"

    for i, text in enumerate(meta[:3]):
        c = ws.cell(row=R_TITLE + i, column=COL_POS, value=text)
        c.font = f(16, True, C_HEAD) if i == 0 else f(10)
        c.alignment = Alignment(vertical="center")
    ws.cell(row=4, column=COL_POS, value=META_HINT).font = f(
        9, italic=True, color="808080")

    # ---- technische Monatsgrenzen (ausgeblendet) ----------------------------
    for i, start in enumerate(MONTH_STARTS):
        c = ws.cell(row=R_MONTHKEY, column=COL_M1 + i, value=start)
        c.number_format = DATE_FMT
        c.font = f(8, color="808080")
    ws.row_dimensions[R_MONTHKEY].hidden = True

    # ---- Tabellenkopf -------------------------------------------------------
    headers = ["Position", "Kostenstelle"] + MONTHS + [
        "Summe H2 2026", "Summe 2027", "Gesamt"]
    for i, text in enumerate(headers, start=1):
        c = ws.cell(row=R_HEAD, column=i, value=text)
        c.font = f(10, True, "FFFFFF")
        c.fill = FILL_HEAD
        c.border = BORDER
        c.alignment = Alignment(horizontal="left" if i <= 2 else "center",
                                vertical="center", wrap_text=i > 2)
    ws.row_dimensions[R_HEAD].height = 30

    def section(row, title):
        for col in range(COL_POS, COL_TOTAL + 1):
            c = ws.cell(row=row, column=col)
            c.fill = FILL_SECTION
            c.border = BORDER
        c = ws.cell(row=row, column=COL_POS, value=title)
        c.font = f(11, True, C_HEAD)
        ws.row_dimensions[row].height = 20

    def detail_row(row, position, value_col, date_col):
        """Kostenstellen-Zeile: A und B sind Eingabe, alle Beträge sind Formeln."""
        p = ws.cell(row=row, column=COL_POS, value=position)
        p.font = f(10)
        p.fill = FILL_INPUT
        p.border = BORDER
        p.alignment = Alignment(indent=1)

        k = ws.cell(row=row, column=COL_KST)
        k.font = f(10, color="0000FF")
        k.fill = FILL_INPUT
        k.border = BORDER

        for col in range(COL_M1, COL_LAST_M + 1):
            formula = sumifs(value_col, date_col, col,
                             extra=[C_KST, f"${get_column_letter(COL_KST)}{row}"])
            # ohne Kostenstellen-Schlüssel bleibt die Zeile bei 0
            c = ws.cell(row=row, column=col,
                        value=f'=IF(${get_column_letter(COL_KST)}{row}="",0,'
                              f'{formula[1:]})')
            c.fill = FILL_CALC
            c.border = BORDER
            c.number_format = EUR
            c.font = f(10)

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

    def calc_row(row, label, formula_for_col, fill, bold=False, border=BORDER,
                 note=None):
        p = ws.cell(row=row, column=COL_POS, value=label)
        p.font = f(10, bold, C_HEAD)
        p.fill = fill
        p.border = border
        n = ws.cell(row=row, column=COL_KST, value=note)
        n.font = f(9, color="808080")
        n.fill = fill
        n.border = border
        for col in range(COL_M1, COL_TOTAL + 1):
            c = ws.cell(row=row, column=col, value=formula_for_col(col))
            c.font = f(10, bold)
            c.fill = fill
            c.border = border
            c.number_format = EUR

    # ---- 1. Einnahmen -------------------------------------------------------
    section(R_SEC_IN, "1  EINNAHMEN  (Quelle: Reiter „Aufträge“)")
    for i in range(N_INCOME_ROWS):
        detail_row(R_IN_FIRST + i, income[i] if i < len(income) else None,
                   C_EINNAHMEN, C_DAT_EIN)
    calc_row(R_IN_REST, "Aufträge ohne Kostenstellen-Zuordnung",
             lambda col: (f"={get_column_letter(col)}{R_SUM_IN}"
                          f"-SUM({get_column_letter(col)}{R_IN_FIRST}:"
                          f"{get_column_letter(col)}{R_IN_LAST})"),
             FILL_CALC, note="Differenz")
    calc_row(R_SUM_IN, "Summe Einnahmen",
             lambda col: (sumifs(C_EINNAHMEN, C_DAT_EIN, col)
                          if col <= COL_LAST_M else period_sum(col, R_SUM_IN)),
             FILL_RESULT, bold=True, border=TOP_LINE)

    # ---- 2. Ausgaben --------------------------------------------------------
    section(R_SEC_OUT, "2  AUSGABEN  (Quelle: Reiter „Aufträge“)")
    for i in range(N_EXPENSE_ROWS):
        detail_row(R_OUT_FIRST + i, expense[i] if i < len(expense) else None,
                   C_AUSGABEN, C_DAT_AUS)
    calc_row(R_OUT_REST, "Aufträge ohne Kostenstellen-Zuordnung",
             lambda col: (f"={get_column_letter(col)}{R_SUM_OUT}"
                          f"-SUM({get_column_letter(col)}{R_OUT_FIRST}:"
                          f"{get_column_letter(col)}{R_OUT_LAST})"),
             FILL_CALC, note="Differenz")
    calc_row(R_SUM_OUT, "Summe Ausgaben",
             lambda col: (sumifs(C_AUSGABEN, C_DAT_AUS, col)
                          if col <= COL_LAST_M else period_sum(col, R_SUM_OUT)),
             FILL_RESULT, bold=True, border=TOP_LINE)

    # ---- 3. Kennzahlen ------------------------------------------------------
    section(R_SEC_KPI, "3  KENNZAHLEN (automatisch berechnet)")
    calc_row(R_KPI_IN, "Summe Einnahmen",
             lambda col: f"={get_column_letter(col)}{R_SUM_IN}", FILL_CALC)
    calc_row(R_KPI_OUT, "Summe Ausgaben",
             lambda col: f"={get_column_letter(col)}{R_SUM_OUT}", FILL_CALC)
    calc_row(R_KPI_NET, "Netto-Cashflow (Monat)",
             lambda col: (f"={get_column_letter(col)}{R_KPI_IN}"
                          f"-{get_column_letter(col)}{R_KPI_OUT}"),
             FILL_RESULT, bold=True)

    def cum_formula(col):
        """Kumuliert über die Monate; in den Summenspalten der Periodenendstand."""
        if col == COL_M1:
            return f"={L_M1}{R_KPI_NET}"
        if col <= COL_LAST_M:
            return (f"={get_column_letter(col - 1)}{R_KPI_CUM}"
                    f"+{get_column_letter(col)}{R_KPI_NET}")
        if col == COL_SUM_H2:
            return f"={L_H2_END}{R_KPI_CUM}"          # Stand 31.12.2026
        return f"={L_LAST_M}{R_KPI_CUM}"              # Stand 31.12.2027

    calc_row(R_KPI_CUM, "Kumulierter Cashflow", cum_formula, FILL_RESULT, bold=True)

    # ---- 4./5. Auswertung nach Themenfeld und Kategorie (nachrichtlich) -----
    def dimension_block(sec_row, first_row, title, field, values):
        section(sec_row, title)
        r = first_row
        for value in values:
            for label, vcol, dcol in (("Einnahmen", C_EINNAHMEN, C_DAT_EIN),
                                      ("Ausgaben", C_AUSGABEN, C_DAT_AUS)):
                calc_row(r, f"{value} – {label}",
                         lambda col, v=value, vc=vcol, dc=dcol, rr=r: (
                             sumifs(vc, dc, col, extra=[field, f'"{v}"'])
                             if col <= COL_LAST_M else period_sum(col, rr)),
                         FILL_CALC, note="nachrichtlich")
                r += 1

    dimension_block(R_SEC_TF, R_TF_FIRST,
                    "4  AUSWERTUNG NACH THEMENFELD (nachrichtlich, nicht in der "
                    "Cashflow-Summe enthalten)", C_TF, THEMENFELDER)
    dimension_block(R_SEC_KAT, R_KAT_FIRST,
                    "5  AUSWERTUNG NACH KATEGORIE (nachrichtlich, nicht in der "
                    "Cashflow-Summe enthalten)", C_KAT, KATEGORIEN)

    # ---- Legende ------------------------------------------------------------
    legend = [
        ("Legende", None, f(10, True, C_HEAD)),
        ("Eingabezelle – nur Position und Kostenstelle werden hier gepflegt",
         C_INPUT, f(9)),
        ("Automatisch aus dem Reiter „Aufträge“ berechnet – nicht überschreiben",
         C_CALC, f(9)),
        ("Ergebniszeile – automatisch berechnet", C_RESULT, f(9)),
        ("Datenfluss:  Aufträge  →  Cashflow  →  Übersicht. Alle Beträge werden "
         "ausschließlich im Reiter „Aufträge“ erfasst.",
         None, f(9, italic=True, color="808080")),
        (f"Die Zuordnung erfolgt über die Kostenstelle in Spalte B: Der Eintrag "
         f"muss mit der Kostenstelle im Reiter „Aufträge“ übereinstimmen. Nicht "
         f"zugeordnete Aufträge erscheinen in Zeile {R_IN_REST} bzw. {R_OUT_REST} "
         f"und sind in den Summen trotzdem enthalten.",
         None, f(9, italic=True, color="808080")),
        (f"Zeile {R_MONTHKEY} ist ausgeblendet und enthält die echten Monatsanfänge "
         "(Datumswerte), mit denen die SUMMEWENNS-Formeln die Monatsgrenzen bilden.",
         None, f(9, italic=True, color="808080")),
        ("Die Auftragswahrscheinlichkeit wird im Reiter „Aufträge“ nur gespeichert "
         "und nicht eingerechnet. Ein gewichteter Forecast lässt sich später über "
         "SUMMENPRODUKT bzw. eine zusätzliche Kennzahlenzeile ergänzen.",
         None, f(9, italic=True, color="808080")),
    ]
    for i, (text, fill, font) in enumerate(legend):
        r = R_LEGEND + i
        if fill:
            marker = ws.cell(row=r, column=COL_POS)
            marker.fill = PatternFill("solid", fgColor=fill)
            marker.border = BORDER
            c = ws.cell(row=r, column=COL_KST, value=text)
        else:
            c = ws.cell(row=r, column=COL_POS, value=text)
        c.font = font

    # ---- Bedingte Formatierung ---------------------------------------------
    ws.conditional_formatting.add(
        f"{L_M1}{R_IN_FIRST}:{L_TOTAL}{R_KAT_FIRST + 2 * len(KATEGORIEN) - 1}",
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
    ws.column_dimensions["A"].width = 38
    ws.column_dimensions["B"].width = 16
    for col in range(COL_M1, COL_LAST_M + 1):
        ws.column_dimensions[get_column_letter(col)].width = 13
    for col in (COL_SUM_H2, COL_SUM_27, COL_TOTAL):
        ws.column_dimensions[get_column_letter(col)].width = 16

    ws.freeze_panes = f"{L_M1}{R_HEAD + 1}"
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
    return ws


# ----------------------------------------------------------------------------
# Blatt "Übersicht"
# ----------------------------------------------------------------------------
def build_overview(wb, ws_cf):
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
        if formula is None:
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

    cats = Reference(ws_cf, min_col=COL_M1, max_col=COL_LAST_M,
                     min_row=R_HEAD, max_row=R_HEAD)

    bar = BarChart()
    bar.type = "col"
    bar.grouping = "clustered"
    bar.title = "Einnahmen vs. Ausgaben (monatlich)"
    bar.y_axis.title = "EUR"
    bar.y_axis.numFmt = '#,##0'
    bar.height, bar.width = 8, 26
    bar.gapWidth = 40
    bar.add_data(Reference(ws_cf, min_col=COL_POS, max_col=COL_LAST_M,
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
    line.add_data(Reference(ws_cf, min_col=COL_POS, max_col=COL_LAST_M,
                            min_row=R_KPI_NET, max_row=R_KPI_CUM),
                  titles_from_data=True, from_rows=True)
    line.set_categories(cats)
    line.series[0].graphicalProperties.line.solidFill = "1F3864"
    line.series[1].graphicalProperties.line.solidFill = "70AD47"
    line.series[1].graphicalProperties.line.dashStyle = "dash"
    ov.add_chart(line, "D22")
    return ov


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--source", help="bestehende Datei, deren Positionen "
                                     "übernommen werden")
    ap.add_argument("--out", default=str(OUT))
    args = ap.parse_args()

    if args.source:
        src = read_source(args.source)
        meta, income, expense = src["meta"], src["income"], src["expense"]
        print(f"übernommen: {len(income)} Einnahmen-, {len(expense)} Ausgabenzeilen")
    else:
        meta, income, expense = META_DEFAULT, INCOME_DEFAULT, EXPENSE_DEFAULT

    wb = Workbook()
    ws_cf = build_cashflow(wb, meta, income, expense)
    build_orders(wb)                       # direkt nach "Cashflow"
    build_overview(wb, ws_cf)
    wb.save(args.out)
    print(f"geschrieben: {args.out}  |  Reiter: {wb.sheetnames}")


if __name__ == "__main__":
    main()
