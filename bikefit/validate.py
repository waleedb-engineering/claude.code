"""Schritt 4: die Messkette gegen einen Zyklus mit bekanntem Ergebnis pruefen.

Ein sauberer Durchlauf beweist nichts. Deshalb: Rauschen auf jedem Koerperpunkt,
verschiedene Phasenlagen, verschiedene Bildraten und Trittfrequenzen.
"""
from __future__ import annotations
import numpy as np
import chain, synth

TRUE_MIN, ALPHA_MIN = synth.true_minimum_flexion()
TRUE_AT_BOTTOM = float(synth.true_flexion(np.array([0.0]))[0])


def one_run(fps, rpm, aligned, noise_px, stand_s=0.0, seed=0):
    T_frames = 60.0 * fps / rpm
    if aligned:
        phase0 = ALPHA_MIN                      # Totpunkt genau auf einem Bild
    else:
        phase0 = ALPHA_MIN - np.pi / T_frames   # Totpunkt genau zwischen zwei Bildern
    xy, cf, _ = synth.build_clip(duration_s=14.0, fps=fps, cadence_rpm=rpm,
                                 phase0=phase0, noise_px=noise_px,
                                 stand_s=stand_s, seed=seed)
    r = chain.analyze_series(xy, cf, fps, crank_mm=synth.CRANK_MM)
    if "fehler" in r:
        return None, r
    return r["knee_flexion_bdc"], r


def run_case(name, noise_px, aligned, n=24, stand_s=0.0, seed0=1000):
    rng = np.random.default_rng(seed0)
    errs, errs_bottom, extra = [], [], []
    fails = 0
    for k in range(n):
        fps = float(rng.choice([30.0, 60.0]))
        if aligned:
            Tf = int(rng.integers(int(round(60 * fps / 100)), int(round(60 * fps / 60)) + 1))
            rpm = 60.0 * fps / Tf
        else:
            rpm = float(rng.uniform(60.0, 100.0))
            if abs(round(60 * fps / rpm) - 60 * fps / rpm) < 1e-6:
                rpm += 0.37
        val, r = one_run(fps, rpm, aligned, noise_px, stand_s=stand_s, seed=seed0 + k)
        if val is None:
            fails += 1
            continue
        errs.append(abs(val - TRUE_MIN))
        errs_bottom.append(abs(val - TRUE_AT_BOTTOM))
        extra.append((fps, rpm, r.get("cadence_rpm"), r.get("n_bdc"),
                      r.get("fit_window_frames"), val))
    e = np.array(errs)
    return dict(name=name, n=len(e), fails=fails,
                mean=float(e.mean()) if len(e) else np.nan,
                worst=float(e.max()) if len(e) else np.nan,
                mean_bottom=float(np.mean(errs_bottom)) if errs_bottom else np.nan,
                detail=extra)


def gegenprobe(fps=30.0, rpm=80.0, noise_px=2.0, n=24, seed0=7000):
    """Zeigt, was die beiden naheliegenden falschen Ableseverfahren liefern."""
    rng = np.random.default_rng(seed0)
    med_band, argmin_, vertex = [], [], []
    for k in range(n):
        xy, cf, _ = synth.build_clip(fps=fps, cadence_rpm=rpm,
                                     phase0=ALPHA_MIN - np.pi * rng.random(),
                                     noise_px=noise_px, seed=seed0 + k)
        r = chain.analyze_series(xy, cf, fps, crank_mm=synth.CRANK_MM)
        if "fehler" in r:
            continue
        fl, T = r["flexion"], r["period_frames"]
        half = max(2, int(round(T / 8)))
        mb, am = [], []
        for b in r["bdcs"]:
            i0 = b["i_coarse"]
            seg = fl[max(0, i0 - half): i0 + half + 1]
            seg = seg[np.isfinite(seg)]
            if len(seg):
                mb.append(np.median(seg)); am.append(seg.min())
        if mb:
            med_band.append(np.median(mb)); argmin_.append(np.median(am))
            vertex.append(r["knee_flexion_bdc"])
    f = lambda a: (float(np.mean(a)), float(np.mean(a) - TRUE_MIN))
    return dict(median_band=f(med_band), kleinstes_bild=f(argmin_), scheitel=f(vertex))


if __name__ == "__main__":
    print("=" * 74)
    print("SCHRITT 4  --  Pruefung der Messkette am kuenstlichen Tretzyklus")
    print("=" * 74)
    print(f"Geometrie: Oberschenkel {synth.THIGH_MM:.0f} mm, Unterschenkel {synth.SHANK_MM:.0f} mm,")
    print(f"           Kurbel {synth.CRANK_MM:.1f} mm, Huefte {synth.SETBACK_MM:.0f} mm hinter dem Tretlager,")
    print(f"           Huefthoehe {synth.hip_xy()[1]:.2f} mm (aus dem Kosinussatz)")
    print()
    print(f"Beugung am PEDAL-TIEFPUNKT (hineingesteckt): {TRUE_AT_BOTTOM:.3f} Grad")
    print(f"Kleinste Beugung im ZYKLUS (analytisch):     {TRUE_MIN:.3f} Grad"
          f"  bei Kurbelwinkel {np.degrees(ALPHA_MIN):.2f} Grad")
    print(f"  -> Das Bein ist {TRUE_AT_BOTTOM - TRUE_MIN:.3f} Grad VOR dem Pedal-Tiefpunkt am laengsten,")
    print(f"     weil die Huefte hinter dem Tretlager sitzt. Die Kette sucht das Minimum,")
    print(f"     also ist {TRUE_MIN:.3f} Grad der richtige Vergleichswert.")
    print()

    cases = [
        ("1  sauber, Totpunkt auf einem Bild",     0.0, True),
        ("2  sauber, Totpunkt zwischen Bildern",   0.0, False),
        ("3  verrauscht (2 px), auf einem Bild",   2.0, True),
        ("4  verrauscht (2 px), zwischen Bildern", 2.0, False),
    ]
    rows = [run_case(n_, np_, al) for n_, np_, al in cases]
    rows.append(run_case("5  hartes Rauschen (5 px), gemischt", 5.0, False))
    rows.append(run_case("6  mit 4 s Danebenstehen davor (2 px)", 2.0, False, stand_s=4.0))

    print(f"{'Fall':40s} {'n':>3s} {'mittl.Fehler':>13s} {'schlechtester':>14s}")
    print("-" * 74)
    ok = True
    for r in rows:
        flag = "" if r["mean"] < 1.0 else "   <-- ZU GROSS"
        if r["mean"] >= 1.0:
            ok = False
        print(f"{r['name']:40s} {r['n']:>3d} {r['mean']:>11.3f} G {r['worst']:>12.3f} G{flag}")
        if r["fails"]:
            print(f"{'':40s}     ({r['fails']} Durchlaeufe ohne Ergebnis)")
    print("-" * 74)
    print("Vergleich derselben Werte gegen die 35,000 Grad am Pedal-Tiefpunkt:")
    for r in rows[:4]:
        print(f"  {r['name']:40s} {r['mean_bottom']:.3f} Grad"
              f"  (= Messfehler + {TRUE_AT_BOTTOM-TRUE_MIN:.3f} Grad Geometrieversatz)")

    print()
    print("Gegenprobe -- was die beiden naheliegenden falschen Verfahren liefern:")
    g = gegenprobe()
    for k, (v, d) in g.items():
        print(f"  {k:16s} {v:7.3f} Grad   Abweichung {d:+.3f} Grad")
    print()
    print("URTEIL:", "Kette in Ordnung." if ok else "Kette FEHLERHAFT -- nicht weiterverwenden.")
