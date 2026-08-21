"""Kuenstlicher Tretzyklus mit bekanntem wahren Kniewinkel.

Tretlager im Ursprung, y zeigt nach oben. Das Pedal laeuft auf einem Kreis mit
Kurbelradius um das Tretlager, das Knie ist der Schnittpunkt zweier Kreise:
einer um die Huefte mit Oberschenkellaenge, einer um das Pedal mit
Unterschenkellaenge. Die Huefthoehe kommt aus dem Kosinussatz, nicht aus
Probieren.
"""
from __future__ import annotations
import numpy as np
import chain

THIGH_MM = 430.0
SHANK_MM = 440.0
CRANK_MM = 172.5
SETBACK_MM = 80.0          # Huefte liegt leicht hinter dem Tretlager
TARGET_FLEX = 35.0         # Sollbeugung am Pedal-Tiefpunkt

# Oberkoerper: starr, dient nur dazu, dass die Kette vollstaendige Bilder sieht
TRUNK_MM, UPPERARM_MM, FOREARM_MM = 550.0, 320.0, 270.0


def hip_xy() -> np.ndarray:
    h = chain.hip_height_for_flexion(THIGH_MM, SHANK_MM, CRANK_MM,
                                     SETBACK_MM, TARGET_FLEX)
    return np.array([-SETBACK_MM, h])


def pedal_xy(alpha: np.ndarray) -> np.ndarray:
    """alpha = 0 heisst Pedal ganz unten."""
    alpha = np.atleast_1d(np.asarray(alpha, float))
    return np.stack([CRANK_MM * np.sin(alpha), -CRANK_MM * np.cos(alpha)], axis=-1)


def circle_intersect(c1, r1, c2, r2, forward=True):
    """Schnittpunkt zweier Kreise; 'forward' waehlt das nach vorn zeigende Knie."""
    c1 = np.asarray(c1, float); c2 = np.asarray(c2, float)
    d = np.linalg.norm(c2 - c1, axis=-1)
    if np.any(d > r1 + r2) or np.any(d < abs(r1 - r2)) or np.any(d == 0):
        raise ValueError("Bein erreicht das Pedal nicht -- Geometrie pruefen")
    ex = (c2 - c1) / d[..., None]
    a = (d ** 2 + r1 ** 2 - r2 ** 2) / (2 * d)
    hgt = np.sqrt(np.maximum(r1 ** 2 - a ** 2, 0.0))
    base = c1 + a[..., None] * ex
    perp = np.stack([-ex[..., 1], ex[..., 0]], axis=-1)
    s1 = base + hgt[..., None] * perp
    s2 = base - hgt[..., None] * perp
    take = (s1[..., 0] > s2[..., 0]) if forward else (s1[..., 0] < s2[..., 0])
    return np.where(take[..., None], s1, s2)


def true_flexion(alpha: np.ndarray) -> np.ndarray:
    """Wahre Kniebeugung als Funktion des Kurbelwinkels (analytisch)."""
    H = hip_xy()
    P = pedal_xy(alpha)
    d = np.linalg.norm(P - H, axis=-1)
    cos_th = (THIGH_MM ** 2 + SHANK_MM ** 2 - d ** 2) / (2 * THIGH_MM * SHANK_MM)
    return 180.0 - np.degrees(np.arccos(np.clip(cos_th, -1, 1)))


def true_minimum_flexion() -> tuple[float, float]:
    """Kleinste Beugung im Zyklus und der Kurbelwinkel dazu.

    Weil die Huefte hinter dem Tretlager sitzt, ist das Bein NICHT exakt am
    Pedal-Tiefpunkt am laengsten, sondern ein Stueck davor. Diesen Wert muss
    jede Minimumssuche finden -- nicht den Wert am Pedal-Tiefpunkt.
    """
    a = np.linspace(-np.pi / 2, np.pi / 2, 2_000_001)
    f = true_flexion(a)
    i = int(np.argmin(f))
    return float(f[i]), float(a[i])


def build_clip(duration_s=14.0, fps=30.0, cadence_rpm=80.0, phase0=0.0,
               noise_px=0.0, scale=1.0, origin=(300.0, 1750.0),
               stand_s=0.0, seed=0):
    """Gibt (xy, conf, fps) zurueck -- exakt das Format der echten Messkette.

    stand_s > 0 stellt dem Treten ein Stueck Danebenstehen voran: Fuss am Boden,
    Bein fast gestreckt. Damit laesst sich pruefen, ob die Trittmaske solche
    Bilder wirklich aussortiert -- sie wuerden die Minimumssuche sonst gewinnen.
    """
    rng = np.random.default_rng(seed)
    n_stand = int(round(stand_s * fps))
    n_ride = int(round(duration_s * fps))
    F = n_stand + n_ride
    ox, oy = origin

    H = hip_xy()
    T_s = 60.0 / cadence_rpm
    t = np.arange(n_ride) / fps
    alpha = 2 * np.pi * t / T_s + phase0
    P = pedal_xy(alpha)
    K = circle_intersect(np.broadcast_to(H, P.shape), THIGH_MM, P, SHANK_MM)
    hips = np.broadcast_to(H, P.shape).copy()

    # starrer Oberkoerper
    sh = H + TRUNK_MM * np.array([np.cos(np.radians(45)), np.sin(np.radians(45))])
    hand = sh + 581.1 * np.array([np.cos(np.radians(-25)), np.sin(np.radians(-25))])
    el = circle_intersect(sh[None, :], UPPERARM_MM, hand[None, :], FOREARM_MM,
                          forward=False)[0]

    if n_stand:
        # Danebenstehen: Huefte tiefer und vorn, Fuss am Boden, Bein fast gerade
        Hs = np.array([120.0, 620.0])
        foot = np.array([120.0, 620.0 - (THIGH_MM + SHANK_MM) * 0.985])
        Ks = circle_intersect(Hs[None, :], THIGH_MM, foot[None, :], SHANK_MM)[0]
        hips = np.vstack([np.broadcast_to(Hs, (n_stand, 2)), hips])
        K = np.vstack([np.broadcast_to(Ks, (n_stand, 2)), K])
        P = np.vstack([np.broadcast_to(foot, (n_stand, 2)), P])
        sh_off = Hs - H
        sh_all = np.vstack([np.broadcast_to(sh + sh_off, (n_stand, 2)),
                            np.broadcast_to(sh, (n_ride, 2))])
        el_all = np.vstack([np.broadcast_to(el + sh_off, (n_stand, 2)),
                            np.broadcast_to(el, (n_ride, 2))])
        hd_all = np.vstack([np.broadcast_to(hand + sh_off, (n_stand, 2)),
                            np.broadcast_to(hand, (n_ride, 2))])
    else:
        sh_all = np.broadcast_to(sh, (F, 2))
        el_all = np.broadcast_to(el, (F, 2))
        hd_all = np.broadcast_to(hand, (F, 2))

    xy = np.zeros((F, 17, 2))
    conf = np.full((F, 17), 0.92)
    put = lambda i, arr: xy.__setitem__((slice(None), i, slice(None)), arr)
    # Modellkoordinaten -> Bildkoordinaten (y im Bild zeigt nach unten)
    to_img = lambda a: np.stack([ox + scale * a[:, 0], oy - scale * a[:, 1]], axis=-1)
    for i, arr in ((chain.R_HIP, hips), (chain.R_KNEE, K), (chain.R_ANKLE, P),
                   (chain.R_SHOULDER, sh_all), (chain.R_ELBOW, el_all),
                   (chain.R_WRIST, hd_all)):
        put(i, to_img(np.asarray(arr, float)))
    # linke (kameraferne) Seite: leicht versetzt und deutlich unsicherer
    for l, r in ((chain.L_HIP, chain.R_HIP), (chain.L_KNEE, chain.R_KNEE),
                 (chain.L_ANKLE, chain.R_ANKLE), (chain.L_SHOULDER, chain.R_SHOULDER),
                 (chain.L_ELBOW, chain.R_ELBOW), (chain.L_WRIST, chain.R_WRIST)):
        xy[:, l, :] = xy[:, r, :] + np.array([6.0, 0.0])
        conf[:, l] = 0.45
    xy[:, chain.NOSE, :] = xy[:, chain.R_SHOULDER, :] + np.array([90.0, -110.0])

    if noise_px:
        xy = xy + rng.normal(0.0, noise_px, xy.shape)
    return xy, conf, fps
