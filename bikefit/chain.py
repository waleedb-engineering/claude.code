"""Messkette: aus Keypoint-Zeitreihen die Winkel am unteren Totpunkt.

Bewusst ohne Video- und Modellcode. Genau deshalb kann die synthetische
Pruefung (validate.py) exakt dieselbe Kette durchlaufen wie das echte Video --
sonst wuerde die Pruefung etwas anderes testen als das, was spaeter laeuft.

WICHTIG 1: Alle Koordinaten hier sind PIXEL. Normierte Koordinaten (xyn) sind
je Achse normiert; bei Hochformat ist 0.1 waagerecht eine andere Strecke als
0.1 senkrecht, und jeder Winkel daraus ist gestaucht. Wer doch xyn benutzt,
muss x vorher mit W/H multiplizieren -- dafuer gibt es xyn_to_isotropic().
"""
from __future__ import annotations
import numpy as np

# COCO-17 Reihenfolge, wie sie das Posenmodell liefert
NOSE = 0
L_SHOULDER, R_SHOULDER = 5, 6
L_ELBOW, R_ELBOW = 7, 8
L_WRIST, R_WRIST = 9, 10
L_HIP, R_HIP = 11, 12
L_KNEE, R_KNEE = 13, 14
L_ANKLE, R_ANKLE = 15, 16

SIDE_IDX = {
    "links": dict(shoulder=L_SHOULDER, elbow=L_ELBOW, wrist=L_WRIST,
                  hip=L_HIP, knee=L_KNEE, ankle=L_ANKLE),
    "rechts": dict(shoulder=R_SHOULDER, elbow=R_ELBOW, wrist=R_WRIST,
                   hip=R_HIP, knee=R_KNEE, ankle=R_ANKLE),
}


def xyn_to_isotropic(xyn: np.ndarray, width: int, height: int) -> np.ndarray:
    """Normierte Koordinaten in ein isotropes System bringen (WICHTIG 1).

    Nur als Notausgang vorhanden. Der reale Weg benutzt keypoints.xy in Pixeln.
    """
    out = np.array(xyn, dtype=float, copy=True)
    out[..., 0] *= width / height
    return out


# ---------------------------------------------------------------- Geometrie

def angle_at(a: np.ndarray, b: np.ndarray, c: np.ndarray) -> np.ndarray:
    """Innenwinkel am Punkt b im Dreieck a-b-c, in Grad. Arbeitet auf (...,2)."""
    u = np.asarray(a, float) - np.asarray(b, float)
    v = np.asarray(c, float) - np.asarray(b, float)
    nu = np.linalg.norm(u, axis=-1)
    nv = np.linalg.norm(v, axis=-1)
    with np.errstate(invalid="ignore", divide="ignore"):
        cos = np.sum(u * v, axis=-1) / (nu * nv)
    return np.degrees(np.arccos(np.clip(cos, -1.0, 1.0)))


def angle_to_horizontal(p: np.ndarray, q: np.ndarray) -> np.ndarray:
    """Neigung der Strecke p-q gegen die Waagerechte, 0..90 Grad.

    Vorzeichenfrei, damit ein Spiegeln des Bildes nichts aendert. Die
    y-Achse zeigt im Bild nach unten -- fuer den Betrag ist das egal.
    """
    d = np.asarray(q, float) - np.asarray(p, float)
    return np.degrees(np.arctan2(np.abs(d[..., 1]), np.abs(d[..., 0])))


def seg_len(a: np.ndarray, b: np.ndarray) -> np.ndarray:
    return np.linalg.norm(np.asarray(a, float) - np.asarray(b, float), axis=-1)


# ------------------------------------------------------------ Hilfsfunktionen

def moving_average(x: np.ndarray, win: int) -> np.ndarray:
    """Zentrierter gleitender Mittelwert, randstabil, nan-tolerant."""
    win = max(1, int(win) | 1)              # ungerade erzwingen
    if win == 1:
        return np.array(x, float)
    pad = win // 2
    xp = np.pad(np.asarray(x, float), pad, mode="edge")
    ok = np.isfinite(xp).astype(float)
    xz = np.where(np.isfinite(xp), xp, 0.0)
    k = np.ones(win)
    num = np.convolve(xz, k, mode="valid")
    den = np.convolve(ok, k, mode="valid")
    with np.errstate(invalid="ignore", divide="ignore"):
        return np.where(den > 0, num / den, np.nan)


def interp_gaps(x: np.ndarray, max_gap: int) -> np.ndarray:
    """Kurze Luecken linear fuellen, lange als nan stehen lassen."""
    x = np.array(x, float)
    n = len(x)
    good = np.isfinite(x)
    if good.sum() < 2:
        return x
    idx = np.arange(n)
    filled = np.interp(idx, idx[good], x[good])
    out = np.where(good, x, np.nan)
    # Luecken einzeln pruefen
    i = 0
    while i < n:
        if good[i]:
            i += 1
            continue
        j = i
        while j < n and not good[j]:
            j += 1
        # Rand-Luecken nie fuellen (dort ist die Interpolation nur Fortschreibung)
        if i > 0 and j < n and (j - i) <= max_gap:
            out[i:j] = filled[i:j]
        i = j
    return out


def estimate_period_frames(sig: np.ndarray, fps: float,
                           lo_rpm: float = 40.0, hi_rpm: float = 130.0) -> float:
    """Trittdauer in Bildern aus der Schwingung der Knoechelhoehe.

    Autokorrelation im plausiblen Trittfrequenzband, Scheitel parabolisch
    verfeinert -- eine ganzzahlige Periode waere bei 30 fps schon 2 rpm daneben.
    """
    x = np.asarray(sig, float)
    x = x[np.isfinite(x)]
    if len(x) < int(2 * fps):
        return float("nan")
    x = x - moving_average(x, int(round(fps * 1.5)))   # Drift raus
    x = x[np.isfinite(x)]
    x = x - x.mean()
    if not np.any(x):
        return float("nan")
    n = len(x)
    ac = np.correlate(x, x, mode="full")[n - 1:]
    ac = ac / ac[0]
    lo = max(2, int(np.floor(fps * 60.0 / hi_rpm)))
    hi = min(n - 2, int(np.ceil(fps * 60.0 / lo_rpm)))
    if hi <= lo:
        return float("nan")
    k = lo + int(np.argmax(ac[lo:hi + 1]))
    if 0 < k < len(ac) - 1:                            # Scheitel verfeinern
        y0, y1, y2 = ac[k - 1], ac[k], ac[k + 1]
        den = y0 - 2 * y1 + y2
        if den != 0:
            k = k + 0.5 * (y0 - y2) / den
    return float(k)


def rolling_p2p(x: np.ndarray, win: int) -> np.ndarray:
    """Spannweite in einem gleitenden Fenster -- Mass fuer 'schwingt es hier?'."""
    x = np.asarray(x, float)
    n = len(x)
    half = max(1, win // 2)
    out = np.full(n, np.nan)
    for i in range(n):
        a, b = max(0, i - half), min(n, i + half + 1)
        seg = x[a:b]
        seg = seg[np.isfinite(seg)]
        if len(seg) >= 3:
            out[i] = seg.max() - seg.min()
    return out


def find_local_minima(y: np.ndarray, min_dist: float) -> list[int]:
    """Lokale Minima mit Mindestabstand; bei Konflikt gewinnt das tiefere."""
    y = np.asarray(y, float)
    n = len(y)
    cand = [i for i in range(1, n - 1)
            if np.isfinite(y[i - 1:i + 2]).all()
            and y[i] <= y[i - 1] and y[i] < y[i + 1]]
    keep: list[int] = []
    for i in sorted(cand, key=lambda j: y[j]):
        if all(abs(i - k) >= min_dist for k in keep):
            keep.append(i)
    return sorted(keep)


def parabola_vertex(ts: np.ndarray, ys: np.ndarray):
    """Ausgleichsparabel durch (ts, ys), Scheitel zurueck.

    WICHTIG 2: Weder Median ueber ein Band (liegt systematisch ~5 Grad ueber
    dem Minimum) noch das einzelne kleinste Bild (faengt das Rauschen nach
    unten ab). Der Scheitel der Ausgleichsparabel mittelt das Rauschen weg,
    ohne den Wert nach oben zu ziehen.
    """
    ts = np.asarray(ts, float)
    ys = np.asarray(ys, float)
    ok = np.isfinite(ts) & np.isfinite(ys)
    if ok.sum() < 4:
        return None
    ts, ys = ts[ok], ys[ok]
    t0 = ts.mean()
    tc = ts - t0                                # zentrieren: bessere Kondition
    A = np.vstack([tc ** 2, tc, np.ones_like(tc)]).T
    coef, *_ = np.linalg.lstsq(A, ys, rcond=None)
    a, b, c = coef
    if a <= 0:                                  # nach unten offen -> kein Minimum
        return None
    t_star = -b / (2 * a)
    y_star = c - b * b / (4 * a)
    return float(t_star + t0), float(y_star), float(a)


def mm_per_degree(thigh_mm: float, shank_mm: float, knee_angle_deg: float) -> float:
    """Wieviel mm Huefte-Pedal-Abstand ein Grad Kniewinkel wert ist.

    Kosinussatz  d^2 = a^2 + b^2 - 2ab cos(theta),  abgeleitet nach theta:
        dd/dtheta = a*b*sin(theta)/d      [mm pro Radiant]
    Mit 430/440 mm und 145 Grad kommen ~2,28 mm/Grad heraus.
    """
    a, b = float(thigh_mm), float(shank_mm)
    th = np.radians(float(knee_angle_deg))
    d = np.sqrt(a * a + b * b - 2 * a * b * np.cos(th))
    if d <= 0:
        return float("nan")
    return float(a * b * np.sin(th) / d * np.pi / 180.0)


def hip_height_for_flexion(thigh_mm: float, shank_mm: float, crank_mm: float,
                           hip_setback_mm: float, flexion_deg: float) -> float:
    """Huefthoehe ueber dem Tretlager, damit am Pedal-Tiefpunkt genau
    flexion_deg Kniebeugung herauskommt. Geschlossen ueber den Kosinussatz,
    nicht durch Probieren."""
    th = np.radians(180.0 - flexion_deg)                  # Innenwinkel am Knie
    d2 = thigh_mm ** 2 + shank_mm ** 2 - 2 * thigh_mm * shank_mm * np.cos(th)
    rest = d2 - hip_setback_mm ** 2
    if rest <= 0:
        raise ValueError("Geometrie unmoeglich")
    return float(np.sqrt(rest) - crank_mm)


# --------------------------------------------------------------- Messkette

MIN_CONF = 0.5          # unter dieser Zuversicht gilt ein Punkt als unbrauchbar
CRANK_MM_DEFAULT = 172.5


def pick_side(conf: np.ndarray) -> tuple[str, dict]:
    """Einmal fuer den ganzen Clip entscheiden, welche Seite zur Kamera zeigt.

    Nicht je Bild -- ein Wechsel mitten im Clip wuerde einen Sprung in jede
    Winkelreihe schreiben, den hinterher niemand mehr als Artefakt erkennt.
    """
    scores = {}
    for side, idx in SIDE_IDX.items():
        cols = [conf[:, i] for i in idx.values()]
        scores[side] = float(np.nanmean(np.stack(cols)))
    best = max(scores, key=scores.get)
    return best, scores


def analyze_series(xy: np.ndarray, conf: np.ndarray, fps: float,
                   crank_mm: float = CRANK_MM_DEFAULT,
                   min_conf: float = MIN_CONF,
                   trim_s: float = 1.0,
                   side: str | None = None) -> dict:
    """xy: (F,17,2) in PIXELN, conf: (F,17), fps aus der Datei gelesen.

    Liefert alle Messwerte am unteren Totpunkt plus die Reihen fuer das Overlay.
    """
    xy = np.asarray(xy, float)
    conf = np.asarray(conf, float)
    F = len(xy)
    fps = float(fps)
    res: dict = {"fps": fps, "n_frames": F, "warnungen": []}

    if side is None:
        side, side_scores = pick_side(conf)
    else:
        _, side_scores = pick_side(conf)
    idx = SIDE_IDX[side]
    res["side"] = side
    res["side_scores"] = side_scores

    P = {name: xy[:, i, :] for name, i in idx.items()}
    C = {name: conf[:, i] for name, i in idx.items()}

    # --- Rohreihen ueber alle Bilder -------------------------------------
    leg_ok = (C["hip"] >= min_conf) & (C["knee"] >= min_conf) & (C["ankle"] >= min_conf)
    arm_ok = (C["shoulder"] >= min_conf) & (C["elbow"] >= min_conf) & (C["wrist"] >= min_conf)
    trunk_ok = (C["shoulder"] >= min_conf) & (C["hip"] >= min_conf)

    knee_ang = angle_at(P["hip"], P["knee"], P["ankle"])
    flexion = np.where(leg_ok, 180.0 - knee_ang, np.nan)
    trunk = np.where(trunk_ok, angle_to_horizontal(P["shoulder"], P["hip"]), np.nan)
    elbow = np.where(arm_ok, 180.0 - angle_at(P["shoulder"], P["elbow"], P["wrist"]), np.nan)
    shoulder = np.where(arm_ok & trunk_ok,
                        angle_at(P["hip"], P["shoulder"], P["elbow"]), np.nan)
    hipang = np.where(leg_ok & trunk_ok,
                      angle_at(P["shoulder"], P["hip"], P["knee"]), np.nan)
    ankle_y = np.where(C["ankle"] >= min_conf, P["ankle"][:, 1], np.nan)
    det_q = np.nanmean(np.stack([C["hip"], C["knee"], C["ankle"]]), axis=0)

    res.update(flexion=flexion, trunk=trunk, elbow=elbow, shoulder=shoulder,
               hip=hipang, ankle_y=ankle_y, det_quality=det_q, leg_ok=leg_ok)

    max_gap = max(1, int(round(0.2 * fps)))
    ank = interp_gaps(ankle_y, max_gap)
    flex_i = interp_gaps(flexion, max_gap)

    # --- Trittdauer aus der Knoechelschwingung ---------------------------
    trim = int(round(trim_s * fps))
    core = np.zeros(F, bool)
    core[trim:F - trim if trim else F] = True          # erste/letzte Sekunde weg
    if core.sum() < 3 * fps:
        res["warnungen"].append("Clip zu kurz fuer eine belastbare Auswertung.")
        core[:] = True

    T = estimate_period_frames(np.where(core, ank, np.nan), fps)
    if not np.isfinite(T):
        res["fehler"] = "Keine regelmaessige Trittbewegung gefunden."
        return res

    # --- Trittmaske: nur Bilder zaehlen, in denen wirklich getreten wird --
    # Beim Auf-/Absteigen und Danebenstehen ist das Bein gestreckter als bei
    # jedem echten Tritt. Solche Bilder wuerden die Minimumssuche gewinnen.
    p2p = rolling_p2p(ank, int(round(T)))
    ref = np.nanmedian(p2p[core])
    pedaling = core & np.isfinite(ank) & (p2p >= 0.5 * ref)
    if pedaling.sum() < 2 * T:
        res["fehler"] = "Zu wenige Bilder mit echter Tretbewegung."
        return res

    T = estimate_period_frames(np.where(pedaling, ank, np.nan), fps) or T
    if not np.isfinite(T):
        res["fehler"] = "Trittdauer nicht bestimmbar."
        return res
    res.update(period_frames=float(T), cadence_rpm=60.0 * fps / T, pedaling=pedaling)

    # --- Untere Totpunkte: Ort grob, Wert ueber den Parabelscheitel -------
    # Ort auf der GEGLAETTETEN Reihe suchen, Wert auf der UNGEGLAETTETEN
    # ablesen -- Glaetten verschiebt den Scheitel um bis zu zwei Bilder.
    search = np.where(pedaling, flex_i, np.nan)
    smooth = moving_average(search, max(3, int(round(T / 8))))
    smooth = np.where(pedaling, smooth, np.nan)
    coarse = find_local_minima(smooth, min_dist=0.6 * T)

    # Fensterbreite = ein Viertel der TRITTDAUER, keine feste Bildzahl.
    half = max(2, int(round(T / 8.0)))
    res["fit_window_frames"] = 2 * half + 1

    bdcs = []
    for i0 in coarse:
        a, b = i0 - half, i0 + half + 1
        if a < 0 or b > F:
            continue
        if not pedaling[a:b].all():
            continue
        ts = np.arange(a, b, dtype=float)
        ys = flex_i[a:b]                       # ungeglaettet!
        if not np.isfinite(ys).all():
            continue
        v = parabola_vertex(ts, ys)
        if v is None:
            continue
        t_star, y_star, _ = v
        if abs(t_star - i0) > half:            # Scheitel ausserhalb -> unbrauchbar
            continue
        bdcs.append({"i_coarse": int(i0), "t": t_star, "flexion": y_star})

    if len(bdcs) < 2:
        res["fehler"] = f"Nur {len(bdcs)} verwertbare Totpunkte gefunden (mindestens 2 noetig)."
        res["bdcs"] = bdcs
        return res

    vals = np.array([b["flexion"] for b in bdcs])
    res["bdcs"] = bdcs
    res["n_bdc"] = len(bdcs)
    res["knee_flexion_bdc"] = float(np.median(vals))
    res["knee_flexion_spread"] = float(np.percentile(vals, 75) - np.percentile(vals, 25))
    res["knee_flexion_all"] = vals

    # --- Uebrige Winkel am Totpunkt --------------------------------------
    # Diese Groessen liegen dort nicht auf einem Extremum, deshalb ist lineares
    # Ablesen an der Scheitelzeit unverzerrt (anders als beim Knie).
    ts = np.array([b["t"] for b in bdcs])
    fr = np.arange(F, dtype=float)

    def at_bdc(series):
        s = interp_gaps(series, max_gap)
        good = np.isfinite(s)
        if good.sum() < 2:
            return float("nan"), np.array([])
        v = np.interp(ts, fr[good], s[good], left=np.nan, right=np.nan)
        v = v[np.isfinite(v)]
        return (float(np.median(v)), v) if len(v) else (float("nan"), v)

    for key, series in (("trunk", trunk), ("elbow", elbow),
                        ("shoulder", shoulder), ("hip", hipang)):
        m, allv = at_bdc(series)
        res[f"{key}_bdc"] = m
        res[f"{key}_bdc_all"] = allv

    res["bdc_frame"] = int(np.clip(round(bdcs[len(bdcs) // 2]["t"]), 0, F - 1))

    # --- Massstab aus dem Knoechelhub ------------------------------------
    # Der Knoechel folgt dem Pedal; sein senkrechter Hub ueber eine Umdrehung
    # ist rund zwei Kurbellaengen. Das ist eine Messung, keine Annahme -- aber
    # eine mit ~5 % Unsicherheit, weil der Fuss im Sprunggelenk mitarbeitet.
    hubs = []
    for b in bdcs:
        a0 = int(round(b["t"] - T / 2)); b0 = int(round(b["t"] + T / 2))
        if a0 < 0 or b0 >= F:
            continue
        seg = ank[a0:b0 + 1]
        seg = seg[np.isfinite(seg)]
        if len(seg) > 5:
            hubs.append(seg.max() - seg.min())
    if hubs:
        hub_px = float(np.median(hubs))
        res["ankle_travel_px"] = hub_px
        res["scale_mm_per_px"] = (2.0 * crank_mm) / hub_px if hub_px > 0 else float("nan")
    else:
        res["scale_mm_per_px"] = float("nan")

    ped = pedaling & leg_ok
    thigh_px = float(np.nanmedian(seg_len(P["hip"], P["knee"])[ped]))
    shank_px = float(np.nanmedian(seg_len(P["knee"], P["ankle"])[ped]))
    res["thigh_px"], res["shank_px"] = thigh_px, shank_px
    s = res["scale_mm_per_px"]
    res["thigh_mm"] = thigh_px * s
    res["shank_mm"] = shank_px * s
    res["crank_mm"] = crank_mm
    if np.isfinite(res["thigh_mm"]):
        res["mm_per_deg"] = mm_per_degree(res["thigh_mm"], res["shank_mm"],
                                          180.0 - res["knee_flexion_bdc"])
    else:
        res["mm_per_deg"] = float("nan")
    return res
