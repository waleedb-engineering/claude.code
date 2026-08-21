"""Analyse-Ansicht mit Pillow auf einer durchsichtigen Ebene.

Nicht mit OpenCV: dessen Hershey-Schriften sind Balkenlettern und sehen nach
Debug-Ausgabe aus. Alle Groessen kommen ueber einen Massstab aus der
Bildbreite, damit das Overlay bei jeder Videogroesse sitzt.
"""
from __future__ import annotations
import os, numpy as np
from PIL import Image, ImageDraw, ImageFont
import chain, judge
from judge import GREEN, YELLOW, RED, GREY

WHITE = (255, 255, 255)
PANEL = (17, 18, 22, 208)
PANEL_S = (24, 26, 31, 190)
INK = (232, 234, 238)

# Schrift suchen statt einen Pfad setzen: erste Datei, die existiert, gewinnt.
SANS = ["/System/Library/Fonts/SFCompactDisplay.ttf",           # macOS
        "/System/Library/Fonts/SFNSDisplay.ttf",
        "/System/Library/Fonts/Helvetica.ttc",
        "/Library/Fonts/Arial.ttf",
        "C:/Windows/Fonts/segoeui.ttf",                          # Windows
        "C:/Windows/Fonts/arial.ttf",
        "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",       # Linux
        "/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf"]
SANS_B = ["/System/Library/Fonts/SFCompactDisplay.ttf",
          "/System/Library/Fonts/Helvetica.ttc",
          "/Library/Fonts/Arial Bold.ttf",
          "C:/Windows/Fonts/segoeuib.ttf",
          "C:/Windows/Fonts/arialbd.ttf",
          "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
          "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf"]
MONO = ["/System/Library/Fonts/SFNSMono.ttf",
        "/System/Library/Fonts/Menlo.ttc",
        "/Library/Fonts/Courier New.ttf",
        "C:/Windows/Fonts/consola.ttf",
        "C:/Windows/Fonts/cour.ttf",
        "/usr/share/fonts/truetype/dejavu/DejaVuSansMono.ttf",
        "/usr/share/fonts/truetype/liberation/LiberationMono-Regular.ttf"]
MONO_B = ["/System/Library/Fonts/SFNSMono.ttf",
          "/System/Library/Fonts/Menlo.ttc",
          "C:/Windows/Fonts/consolab.ttf",
          "/usr/share/fonts/truetype/dejavu/DejaVuSansMono-Bold.ttf",
          "/usr/share/fonts/truetype/liberation/LiberationMono-Bold.ttf"]


def _first(cands):
    for p in cands:
        if os.path.exists(p):
            return p
    return None


class Fonts:
    def __init__(self):
        self.files = {"sans": _first(SANS), "sansb": _first(SANS_B),
                      "mono": _first(MONO), "monob": _first(MONO_B)}
        self.gefunden = {k: (os.path.basename(v) if v else "Pillow-Standard")
                         for k, v in self.files.items()}
        self._c: dict = {}

    def __call__(self, kind: str, size: int):
        size = max(8, int(round(size)))
        k = (kind, size)
        if k not in self._c:
            p = self.files.get(kind)
            try:
                self._c[k] = ImageFont.truetype(p, size) if p else ImageFont.load_default(size=size)
            except Exception:
                self._c[k] = ImageFont.load_default(size=size)
        return self._c[k]


def _txt(d, xy, s, font, fill, anchor="la"):
    d.text(xy, s, font=font, fill=fill, anchor=anchor)


class Renderer:
    """Baut die feststehenden Teile einmal und legt je Bild nur das Bewegte drauf."""

    def __init__(self, W, H, res, modell, advice, fonts: Fonts | None = None):
        self.W, self.H = W, H
        self.S = W / 1080.0                     # Massstab aus der Bildbreite
        self.res, self.advice, self.modell = res, advice, modell
        self.F = fonts or Fonts()
        S = self.S
        self.h_head = 92 * S
        self.tile_w = 336 * S
        self.tile_h = 94 * S
        self.tile_x = W - self.tile_w - 20 * S
        self.rb_h = 68 * S
        self.ch_h = 212 * S
        self.ch_y = H - self.rb_h - self.ch_h - 12 * S
        self.static = self._build_static()

    # ------------------------------------------------------------- statisch
    def _build_static(self):
        S, W, H = self.S, self.W, self.H
        L = Image.new("RGBA", (W, H), (0, 0, 0, 0))
        d = ImageDraw.Draw(L)
        F, res, adv = self.F, self.res, self.advice

        # Kopfleiste
        d.rectangle([0, 0, W, self.h_head], fill=(10, 11, 14, 214))
        d.line([0, self.h_head, W, self.h_head], fill=(255, 255, 255, 40), width=max(1, int(2 * S)))
        _txt(d, (24 * S, 16 * S), "BIKEFIT", F("sansb", 40 * S), INK)
        _txt(d, (26 * S, 62 * S), f"Posenmodell {self.modell}  |  Seite: {res.get('side','?')}",
             F("sans", 17 * S), GREY)

        # Kacheln -- die Werte am Totpunkt aendern sich im Clip nicht
        y = self.h_head + 22 * S
        self.tile_top = y
        for key in ("knee", "trunk", "elbow", "shoulder", "hip"):
            sp = judge.SPECS[key]
            val = res.get(f"{key}_bdc") if key != "knee" else res.get("knee_flexion_bdc")
            wort, col = judge.judge(key, val)
            x0, x1 = self.tile_x, self.tile_x + self.tile_w
            d.rounded_rectangle([x0, y, x1, y + self.tile_h], radius=10 * S,
                                fill=PANEL, outline=col + (235,), width=max(2, int(2.5 * S)))
            _txt(d, (x0 + 14 * S, y + 11 * S), sp.label, F("sans", 16 * S), INK)
            _txt(d, (x1 - 14 * S, y + 11 * S), wort, F("sansb", 15 * S), col, anchor="ra")
            s = f"{val:.1f}" if (val is not None and np.isfinite(val)) else "--,-"
            _txt(d, (x0 + 14 * S, y + 36 * S), s, F("monob", 36 * S), col if sp.bewerten else INK)
            wx = d.textlength(s, font=F("monob", 36 * S))
            _txt(d, (x0 + 18 * S + wx, y + 52 * S), "Grad", F("sans", 16 * S), GREY)
            hint = sp.band if sp.bewerten else "wird nicht bewertet"
            _txt(d, (x1 - 14 * S, y + 58 * S), hint, F("sans", 14 * S), GREY, anchor="ra")
            y += self.tile_h + 10 * S

        # Hinweis unter den Kacheln
        _txt(d, (self.tile_x + 2 * S, y + 4 * S),
             "Rumpf und Ellbogen: Erfahrungswerte,", F("sans", 13 * S), GREY)
        _txt(d, (self.tile_x + 2 * S, y + 20 * S),
             "keine belegte Norm.", F("sans", 13 * S), GREY)

        # Guete-Beschriftung links (Zahl und Balken kommen je Bild dazu)
        gx, gy = 22 * S, self.h_head + 22 * S
        self.gq = (gx, gy)
        d.rounded_rectangle([gx - 6 * S, gy - 6 * S, gx + 232 * S, gy + 96 * S],
                            radius=10 * S, fill=PANEL_S)
        _txt(d, (gx + 8 * S, gy + 6 * S), "ERKENNUNGSGUETE", F("sans", 15 * S), INK)
        _txt(d, (gx + 8 * S, gy + 78 * S), "Huefte, Knie, Knoechel", F("sans", 13 * S), GREY)

        self._chart_static(d, L)
        self._result_bar(d)
        return L

    # --------------------------------------------------------------- Diagramm
    def _chart_static(self, d, L):
        S, W = self.S, self.W
        res, F = self.res, self.F
        x0, x1 = 20 * S, W - 20 * S
        y0, y1 = self.ch_y, self.ch_y + self.ch_h
        d.rounded_rectangle([x0, y0, x1, y1], radius=10 * S, fill=PANEL)
        _txt(d, (x0 + 14 * S, y0 + 8 * S), "KNIEBEUGUNG UEBER DIE ZEIT",
             F("sans", 15 * S), INK)

        fl = np.asarray(res.get("flexion"), float)
        n = len(fl)
        px0, px1 = x0 + 52 * S, x1 - 14 * S
        py0, py1 = y0 + 32 * S, y1 - 22 * S
        self.plot = (px0, px1, py0, py1, n)
        good = fl[np.isfinite(fl)]
        if not len(good):
            return
        sp = judge.SPECS["knee"]
        # Luft UNTER dem Zielband lassen: kleben die Totpunkte am Boden, sieht
        # man nicht mehr, ob sie im Band liegen oder darunter -- und genau das
        # ist die Aussage des Diagramms.
        lo = min(np.percentile(good, 1) - 8, sp.lo - 12)
        hi = max(np.percentile(good, 99) + 4, sp.hi + 8)
        self.ylim = (lo, hi)
        yv = lambda v: py1 - (v - lo) / (hi - lo) * (py1 - py0)
        xv = lambda i: px0 + i / max(1, n - 1) * (px1 - px0)
        self.xv, self.yv = xv, yv

        # Zielband als getoente Flaeche
        d.rectangle([px0, yv(sp.hi), px1, yv(sp.lo)], fill=GREEN + (46,))
        for v, lbl in ((sp.lo, f"{sp.lo:.0f}"), (sp.hi, f"{sp.hi:.0f}")):
            d.line([px0, yv(v), px1, yv(v)], fill=GREEN + (120,), width=max(1, int(1.5 * S)))
            _txt(d, (px0 - 8 * S, yv(v)), lbl, F("mono", 14 * S), GREEN, anchor="rm")
        # Nur die Bandgrenzen beschriften -- mehr Zahlen an der Achse verdecken
        # sich gegenseitig und sagen nichts, was das Band nicht schon sagt.
        _txt(d, (px0 - 8 * S, py0 + 6 * S), "Grad", F("sans", 12 * S), GREY, anchor="rm")

        # Kurve -- Luecken bleiben Luecken
        seg = []
        for i, v in enumerate(fl):
            if np.isfinite(v):
                seg.append((xv(i), yv(v)))
            else:
                if len(seg) > 1:
                    d.line(seg, fill=INK + (235,), width=max(2, int(2.2 * S)), joint="curve")
                seg = []
        if len(seg) > 1:
            d.line(seg, fill=INK + (235,), width=max(2, int(2.2 * S)), joint="curve")

        # gefundene Totpunkte
        col = judge.judge("knee", res.get("knee_flexion_bdc"))[1]
        r = 5.5 * S
        for b in res.get("bdcs", []):
            cx, cy = xv(b["t"]), yv(b["flexion"])
            d.ellipse([cx - r - 1.5 * S, cy - r - 1.5 * S, cx + r + 1.5 * S, cy + r + 1.5 * S],
                      fill=(0, 0, 0, 190))
            d.ellipse([cx - r, cy - r, cx + r, cy + r], fill=col + (255,))
        _txt(d, (px1, y0 + 10 * S),
             f"{len(res.get('bdcs', []))} Totpunkte  |  {res.get('cadence_rpm', float('nan')):.0f} Umdr./min",
             F("mono", 14 * S), GREY, anchor="ra")

    def _result_bar(self, d):
        S, W, H = self.S, self.W, self.H
        col = self.advice["farbe"]
        y0, y1 = H - self.rb_h - 4 * S, H - 4 * S
        d.rounded_rectangle([20 * S, y0, W - 20 * S, y1], radius=10 * S,
                            fill=(12, 13, 16, 224), outline=col + (235,), width=max(2, int(2.5 * S)))
        d.rounded_rectangle([20 * S, y0, 20 * S + 9 * S, y1], radius=4 * S, fill=col + (255,))
        f = self.F("sansb", 21 * S)
        s = self.advice["satz"]
        while d.textlength(s, font=f) > (W - 90 * S) and f.size > 11:
            f = self.F("sansb", f.size - 1)
        _txt(d, (40 * S, (y0 + y1) / 2), s, f, INK, anchor="lm")

    # --------------------------------------------------------------- je Bild
    def frame(self, rgb, i, xy, cf, box):
        S, W, H = self.S, self.W, self.H
        F, res = self.F, self.res
        img = Image.fromarray(rgb).convert("RGBA")
        # Zwei Ebenen: der Koerper liegt UNTER den Tafeln, damit Skelett und
        # Eckmarken nicht ins Diagramm oder in die Kacheln hineinzeichnen.
        # Bildzaehler, Guete und Zeitmarke gehoeren darueber.
        L = Image.new("RGBA", (W, H), (0, 0, 0, 0))
        d = ImageDraw.Draw(L)
        Lh = Image.new("RGBA", (W, H), (0, 0, 0, 0))
        dh = ImageDraw.Draw(Lh)
        idx = chain.SIDE_IDX[res["side"]]
        P = {k: xy[v] for k, v in idx.items()}
        C = {k: cf[v] for k, v in idx.items()}
        ok = lambda *ks: all(np.isfinite(P[k]).all() and C[k] >= chain.MIN_CONF for k in ks)

        # Ecken statt Kasten
        if np.isfinite(box).all():
            bx0, by0, bx1, by1 = box
            ln, wd = 36 * S, max(3, int(3.5 * S))
            ecken = ((bx0, by0, 1, 1), (bx1, by0, -1, 1),
                     (bx0, by1, 1, -1), (bx1, by1, -1, -1))
            for col, extra in ((( 0, 0, 0, 195), int(4 * S)), (INK + (235,), 0)):
                for cx, cy, sx, sy in ecken:
                    d.line([cx, cy, cx + sx * ln, cy], fill=col, width=wd + extra)
                    d.line([cx, cy, cx, cy + sy * ln], fill=col, width=wd + extra)
            s_pts = f"{int((cf >= chain.MIN_CONF).sum())}/17 Punkte verfolgt"
            fp = F("mono", 14 * S)
            tw = d.textlength(s_pts, font=fp)
            d.rounded_rectangle([bx0 - 5 * S, by0 - 25 * S, bx0 + tw + 7 * S, by0 - 3 * S],
                                radius=5 * S, fill=(10, 11, 14, 190))
            _txt(d, (bx0, by0 - 23 * S), s_pts, fp, INK)

        # Skelett: fuenf Striche, jeder in der Farbe seines Winkels
        live = np.nan
        if ok("hip", "knee", "ankle"):
            live = 180.0 - chain.angle_at(P["hip"], P["knee"], P["ankle"])
        c_knee = judge.judge("knee", res.get("knee_flexion_bdc"))[1]
        c_trunk = judge.judge("trunk", res.get("trunk_bdc"))[1]
        c_elbow = judge.judge("elbow", res.get("elbow_bdc"))[1]
        bones = [("hip", "knee", c_knee), ("knee", "ankle", c_knee),
                 ("shoulder", "hip", c_trunk),
                 ("shoulder", "elbow", c_elbow), ("elbow", "wrist", c_elbow)]
        for a, b, col in bones:                       # erst schwarz, dann Farbe
            if not ok(a, b):
                continue
            pa, pb = tuple(P[a]), tuple(P[b])
            d.line([pa, pb], fill=(0, 0, 0, 210), width=max(6, int(15 * S)))
        for a, b, col in bones:
            if not ok(a, b):
                continue
            d.line([tuple(P[a]), tuple(P[b])], fill=col + (255,), width=max(3, int(8.5 * S)))
        for k in ("shoulder", "elbow", "wrist", "hip", "knee", "ankle"):
            if not ok(k):
                continue
            x, y = P[k]
            r = 8.0 * S
            d.ellipse([x - r - 2.5 * S, y - r - 2.5 * S, x + r + 2.5 * S, y + r + 2.5 * S], fill=(0, 0, 0, 220))
            d.ellipse([x - r, y - r, x + r, y + r], fill=WHITE + (255,))

        # Kreisbogen am Knie plus der LIVE-Wert dieses Bildes
        if ok("hip", "knee", "ankle"):
            kx, ky = P["knee"]
            R = 46 * S
            a1 = np.degrees(np.arctan2(P["hip"][1] - ky, P["hip"][0] - kx))
            a2 = np.degrees(np.arctan2(P["ankle"][1] - ky, P["ankle"][0] - kx))
            if (a2 - a1) % 360 > 180:
                a1, a2 = a2, a1
            bb = [kx - R, ky - R, kx + R, ky + R]
            d.arc(bb, a1, a2, fill=(0, 0, 0, 205), width=max(4, int(10 * S)))
            d.arc(bb, a1, a2, fill=c_knee + (255,), width=max(3, int(5 * S)))
            mid = np.radians(a1 + ((a2 - a1) % 360) / 2.0)
            lx, ly = kx + np.cos(mid) * (R + 34 * S), ky + np.sin(mid) * (R + 34 * S)
            s = f"{live:.1f} Grad"
            fnt, fs = F("monob", 25 * S), F("sans", 15 * S)
            tw = max(d.textlength(s, font=fnt), d.textlength("live", font=fs))
            lx = float(np.clip(lx, 8 * S, self.tile_x - tw - 26 * S))
            ly = float(np.clip(ly, self.h_head + 8 * S, self.ch_y - 58 * S))
            d.rounded_rectangle([lx - 8 * S, ly - 6 * S, lx + tw + 10 * S, ly + 46 * S],
                                radius=7 * S, fill=(10, 11, 14, 200))
            _txt(d, (lx, ly - 2 * S), s, fnt, c_knee)
            _txt(d, (lx, ly + 27 * S), "live", fs, GREY)

        # Erkennungsguete
        gx, gy = self.gq
        q = float(np.nanmean([C["hip"], C["knee"], C["ankle"]]))
        q = 0.0 if not np.isfinite(q) else q
        qc = GREEN if q >= 0.7 else (YELLOW if q >= 0.5 else RED)
        _txt(dh, (gx + 8 * S, gy + 26 * S), f"{q*100:4.0f} %", F("monob", 32 * S), qc)
        bx, by, bw, bh = gx + 8 * S, gy + 66 * S, 210 * S, 9 * S
        dh.rounded_rectangle([bx, by, bx + bw, by + bh], radius=4 * S, fill=(255, 255, 255, 46))
        dh.rounded_rectangle([bx, by, bx + bw * min(1.0, q), by + bh], radius=4 * S, fill=qc + (255,))

        # Kopfleiste rechts: Bild, Sekunde, Bildrate
        fps = res["fps"]
        _txt(dh, (W - 24 * S, 18 * S), f"BILD {i+1:>5d} / {res['n_frames']}",
             F("mono", 19 * S), INK, anchor="ra")
        _txt(dh, (W - 24 * S, 46 * S), f"{i/fps:6.2f} s   {fps:.2f} fps",
             F("mono", 19 * S), GREY, anchor="ra")

        # Zeitmarke im Diagramm
        px0, px1, py0, py1, n = self.plot
        cx = self.xv(min(i, n - 1))
        dh.line([cx, py0 - 4 * S, cx, py1 + 4 * S], fill=(255, 255, 255, 210), width=max(1, int(2 * S)))
        if np.isfinite(live) and hasattr(self, "ylim"):
            lo, hi = self.ylim
            if lo <= live <= hi:
                cy = self.yv(live)
                r = 5.0 * S
                dh.ellipse([cx - r - 1.5 * S, cy - r - 1.5 * S, cx + r + 1.5 * S, cy + r + 1.5 * S],
                           fill=(0, 0, 0, 200))
                dh.ellipse([cx - r, cy - r, cx + r, cy + r], fill=WHITE + (255,))

        img.alpha_composite(L)            # Koerper zuerst
        img.alpha_composite(self.static)  # Tafeln darueber -- sie gewinnen immer
        img.alpha_composite(Lh)           # Zaehler, Guete, Zeitmarke ganz oben
        return np.asarray(img.convert("RGB"))
