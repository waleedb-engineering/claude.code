"""Schwellen und Urteile -- die EINZIGE Stelle, an der bewertet wird.

WICHTIG 4: Farbe und Text muessen dieselbe Schwelle benutzen. Deshalb kommen
Kachelrand, Skelettfarbe, Urteilswort und die Sattelempfehlung alle aus
judge() bzw. saddle_advice(). Wer bei 42 Grad gruen faerbt, darf daneben nicht
'verstell den Sattel' schreiben -- hier ist das baulich ausgeschlossen.
"""
from __future__ import annotations
from dataclasses import dataclass
import numpy as np

GREEN = (46, 204, 113)
YELLOW = (241, 196, 15)
RED = (231, 76, 60)
GREY = (145, 148, 155)

IM_BEREICH, GRENZWERTIG, AUSSERHALB, UNBEKANNT = "im Bereich", "grenzwertig", "ausserhalb", "nicht messbar"


@dataclass(frozen=True)
class Spec:
    key: str
    label: str
    lo: float                 # Sollband unten
    hi: float                 # Sollband oben
    act_lo: float             # darunter: Handlungsbedarf
    act_hi: float             # darueber: Handlungsbedarf
    grundlage: str            # woher die Zahlen kommen
    bewerten: bool = True

    @property
    def band(self) -> str:
        return f"Soll {self.lo:.0f}-{self.hi:.0f} Grad"


TOL = 2.5   # Aufloesung eines Handyvideos: rund 2-3 Grad. Das ist die Toleranz.

SPECS = {
    "knee": Spec("knee", "KNIEBEUGUNG UTP", 30, 40, 28, 42,
                 "gaengiger Bike-Fit-Bereich fuer die Sattelhoehe"),
    "trunk": Spec("trunk", "RUMPFNEIGUNG", 40, 50, 40 - TOL, 50 + TOL,
                  "Erfahrungswert aus der Praxis, keine belegte Norm"),
    "elbow": Spec("elbow", "ELLBOGENBEUGUNG", 15, 30, 15 - TOL, 30 + TOL,
                  "Erfahrungswert aus der Praxis, keine belegte Norm"),
    # Schulter und Huefte werden gemessen und angezeigt, aber NICHT bewertet.
    # Grund: die gern zitierte Studie misst 112 Grad an der Schulter und 77 an
    # der Huefte, waehrend Bike-Fit-Anleitungen 80-95 und 85-110 nennen. Das
    # passt nicht zusammen, weil die Studie den Gelenkpunkt anders definiert
    # als ein Posenmodell ihn setzt. Solange das offen ist, waere eine Farbe
    # eine Behauptung und keine Messung.
    "shoulder": Spec("shoulder", "SCHULTERWINKEL", 0, 0, 0, 0,
                     "Quellen widersprechen sich -- nicht bewertet", bewerten=False),
    "hip": Spec("hip", "HUEFTWINKEL", 0, 0, 0, 0,
                "Quellen widersprechen sich -- nicht bewertet", bewerten=False),
}

KNEE_TARGET = 35.0     # Mitte des Sollbands -- Ziel jeder Verstellempfehlung


def judge(key: str, value: float) -> tuple[str, tuple[int, int, int]]:
    """Urteilswort und Farbe. Einzige Bewertungsstelle im ganzen Programm."""
    s = SPECS[key]
    if not s.bewerten:
        return "ohne Bewertung", GREY
    if value is None or not np.isfinite(value):
        return UNBEKANNT, GREY
    if s.lo <= value <= s.hi:
        return IM_BEREICH, GREEN
    if s.act_lo <= value < s.lo or s.hi < value <= s.act_hi:
        return GRENZWERTIG, YELLOW
    return AUSSERHALB, RED


def saddle_advice(knee_flexion: float, mm_per_deg: float) -> dict:
    """Sattelempfehlung -- an dieselbe Schwelle gekoppelt wie die Farbe.

    Empfohlen wird nur, wenn das Urteil ROT ist. Bei GELB liegt der Wert
    innerhalb der Messgenauigkeit am Rand des Bands; dann waere eine
    Millimeterangabe eine Scheingenauigkeit.
    """
    wort, farbe = judge("knee", knee_flexion)
    out = {"urteil": wort, "farbe": farbe, "mm": 0.0, "richtung": None}
    if farbe is GREY:
        out["satz"] = "Der Kniewinkel war nicht sauber messbar -- keine Empfehlung."
        return out
    if farbe is GREEN:
        out["satz"] = (f"Kniebeugung {knee_flexion:.1f} Grad -- im Sollband "
                       f"{SPECS['knee'].lo:.0f}-{SPECS['knee'].hi:.0f}. Sattel so lassen.")
        return out
    if farbe is YELLOW:
        seite = "knapp unter" if knee_flexion < SPECS["knee"].lo else "knapp ueber"
        out["satz"] = (f"Kniebeugung {knee_flexion:.1f} Grad -- {seite} dem Sollband, "
                       f"aber innerhalb der Messgenauigkeit von {TOL:.1f} Grad. "
                       f"Sattel so lassen.")
        return out
    d = knee_flexion - KNEE_TARGET
    mm = abs(d) * mm_per_deg
    out["mm"] = mm
    if d > 0:
        out["richtung"] = "hoeher"
        out["satz"] = (f"Kniebeugung {knee_flexion:.1f} Grad -- zu viel, der Sattel steht zu tief. "
                       f"Sattel um {mm:.0f} mm HOEHER stellen.")
    else:
        out["richtung"] = "tiefer"
        out["satz"] = (f"Kniebeugung {knee_flexion:.1f} Grad -- zu wenig, der Sattel steht zu hoch. "
                       f"Sattel um {mm:.0f} mm TIEFER stellen.")
    return out
