"""Bikefit-Analyse aus einem Seitenvideo auf der Rolle.

  python analyze.py pruefen  <video>            Schritt 2: Aufnahme beurteilen
  python analyze.py rechnen  <video> [--kurbel 172.5]   Schritte 3, 5, 5b, 6
"""
from __future__ import annotations
import argparse, os, sys, time
import numpy as np
import chain, judge, overlay, pose, videoio

SIDE_RATIO_LIMIT = 0.25     # darueber stand die Kamera schraeg
MIN_DURATION_S = 10.0
CHECK_SAMPLES = 40


def _fmt(v, nk=1):
    return f"{v:.{nk}f}" if v is not None and np.isfinite(v) else "nicht messbar"


# ------------------------------------------------------- Schritt 2: Vorpruefung

def seitlichkeit(xy, cf):
    """Waagerechter Schulterabstand geteilt durch Schulter-Huefte-Abstand.

    Bei sauberer Seitenansicht liegen linke und rechte Schulter im Bild fast
    uebereinander. Steht die Kamera schraeg, faellt JEDE Winkelmessung zu
    klein aus, weil die Gliedmassen verkuerzt abgebildet werden.
    """
    out = {}
    for name, (a, b, ref_a, ref_b) in {
        "schulter": (chain.L_SHOULDER, chain.R_SHOULDER, chain.R_SHOULDER, chain.R_HIP),
        "huefte": (chain.L_HIP, chain.R_HIP, chain.R_SHOULDER, chain.R_HIP),
    }.items():
        m = ((cf[:, a] >= chain.MIN_CONF) & (cf[:, b] >= chain.MIN_CONF) &
             (cf[:, ref_a] >= chain.MIN_CONF) & (cf[:, ref_b] >= chain.MIN_CONF))
        if m.sum() < 3:
            out[name] = float("nan"); continue
        dx = np.abs(xy[m, a, 0] - xy[m, b, 0])
        ref = np.linalg.norm(xy[m, ref_a, :] - xy[m, ref_b, :], axis=-1)
        with np.errstate(invalid="ignore", divide="ignore"):
            out[name] = float(np.median(dx / ref))
    return out


def cmd_pruefen(args):
    meta = videoio.probe(args.video)
    dev, devname = pose.pick_device()
    print("=" * 74)
    print("SCHRITT 2  --  die Aufnahme pruefen, bevor gerechnet wird")
    print("=" * 74)
    print(f"Datei      {os.path.basename(args.video)}  ({os.path.getsize(args.video)/1e6:.1f} MB)")
    print(f"Bild       {meta['width']} x {meta['height']} px, Codec {meta['codec']}, Drehung {meta['rotation']} Grad")
    print(f"Bildrate   {meta['fps']:.3f} fps  (aus der Datei gelesen, nicht geraten)")
    print(f"Laenge     {meta['duration']:.1f} s, {meta['n_frames']} Bilder")
    print(f"Rechenwerk {dev} ({devname})")
    step = max(1, meta["n_frames"] // CHECK_SAMPLES)
    print(f"\nStichprobe: jedes {step}. Bild, {meta['n_frames']//step} Bilder ...")
    idx, xy, cf, bx = pose.extract(args.video, meta, args.modell, step=step,
                                   device=dev, progress_every=0)

    side, scores = chain.pick_side(cf)
    r = seitlichkeit(xy, cf)
    beine = np.stack([cf[:, chain.SIDE_IDX[side]["hip"]],
                      cf[:, chain.SIDE_IDX[side]["knee"]],
                      cf[:, chain.SIDE_IDX[side]["ankle"]]])
    schwach = float(np.mean(beine.min(axis=0) < chain.MIN_CONF))
    person = float(np.mean(cf.mean(axis=1) > 0.3))

    print("\n--- Befund ---------------------------------------------------------")
    probleme = []
    worst = np.nanmax([r.get("schulter", np.nan), r.get("huefte", np.nan)])
    print(f"Seitenansicht    Schulterversatz {_fmt(r.get('schulter'),3)} , "
          f"Hueftversatz {_fmt(r.get('huefte'),3)}  (Grenze {SIDE_RATIO_LIMIT})")
    if np.isfinite(worst) and worst > SIDE_RATIO_LIMIT:
        probleme.append(f"die Kamera stand schraeg (Versatz {worst:.2f} statt unter {SIDE_RATIO_LIMIT}) "
                        f"-- dadurch faellt JEDE Winkelmessung zu klein aus")
    print(f"Sichtbarkeit     Bein in {schwach*100:.0f} % der Bilder unsicher, "
          f"Person in {person*100:.0f} % der Bilder erkannt")
    if schwach > 0.2:
        probleme.append(f"Huefte, Knie oder Knoechel sind in {schwach*100:.0f} % der Bilder unsicher "
                        f"-- zu dunkel, oder etwas steht im Weg")
    print(f"Laenge           {meta['duration']:.1f} s  (mindestens {MIN_DURATION_S:.0f} s noetig)")
    if meta["duration"] < MIN_DURATION_S:
        probleme.append(f"der Clip ist mit {meta['duration']:.1f} s zu kurz fuer mehrere Kurbelumdrehungen")
    print(f"Kameranahe Seite {side}  (Zuversicht links {scores['links']:.2f} / rechts {scores['rechts']:.2f})")

    print("\n--- Ergebnis in einem Satz -----------------------------------------")
    if probleme:
        print("Die Aufnahme taugt nur eingeschraenkt: " + "; ".join(probleme) + ".")
        print("\nEmpfehlung: neu filmen. Kamera genau seitlich, Stativhoehe etwa Tretlager-")
        print("bis Huefthoehe, drei bis vier Meter Abstand, gut ausgeleuchtet, mindestens")
        print("20 Sekunden gleichmaessig treten, nicht auf- oder absteigen im Bild.")
        return 1
    print(f"Die Aufnahme taugt: sauber von der Seite (Versatz {worst:.2f}), Bein durchgehend "
          f"sichtbar ({(1-schwach)*100:.0f} % der Bilder), {meta['duration']:.1f} s lang -- "
          f"ich kann damit rechnen.")
    return 0


# ---------------------------------------------------- Schritte 3, 5, 5b, 6

def cmd_rechnen(args):
    t_start = time.time()
    meta = videoio.probe(args.video)
    dev, devname = pose.pick_device()
    out_dir = args.aus or os.path.join(os.path.dirname(os.path.abspath(args.video)), "out")
    os.makedirs(out_dir, exist_ok=True)
    base = os.path.splitext(os.path.basename(args.video))[0]

    print("=" * 74)
    print("SCHRITT 3 und 5  --  messen")
    print("=" * 74)
    print(f"{meta['width']}x{meta['height']} @ {meta['fps']:.3f} fps, "
          f"{meta['n_frames']} Bilder, {meta['duration']:.1f} s  |  {dev}")
    idx, xy, cf, bx = pose.extract_cached(args.video, meta, args.modell, step=1, device=dev)

    res = chain.analyze_series(xy, cf, meta["fps"], crank_mm=args.kurbel)
    res["n_frames"] = len(xy)
    if "fehler" in res:
        print("\nMessung nicht moeglich: " + res["fehler"])
        return 2

    # Plausibilitaet des Massstabs -- er kommt aus dem Knoechelhub, nicht aus Annahmen
    warn = []
    for n, v in (("Oberschenkel", res["thigh_mm"]), ("Unterschenkel", res["shank_mm"])):
        if not np.isfinite(v) or not (300 <= v <= 560):
            warn.append(f"{n} rechnerisch {_fmt(v,0)} mm -- unplausibel, der Massstab ist unsicher")
    adv = judge.saddle_advice(res["knee_flexion_bdc"], res["mm_per_deg"])

    print(f"\nSeite {res['side']}, Trittfrequenz {res['cadence_rpm']:.1f} Umdr./min "
          f"(Trittdauer {res['period_frames']:.1f} Bilder)")
    print(f"Fensterbreite der Ausgleichsparabel: {res['fit_window_frames']} Bilder "
          f"(= ein Viertel der Trittdauer)")
    print(f"{res['n_bdc']} untere Totpunkte gefunden, Streuung zwischen ihnen "
          f"{res['knee_flexion_spread']:.2f} Grad")

    # ----- Video mit Overlay
    print(f"\nSCHRITT 5b -- Overlay zeichnen und mit {meta['fps']:.3f} fps schreiben ...")
    ren = overlay.Renderer(meta["width"], meta["height"], res, args.modell, adv)
    print(f"  Schriften: {', '.join(sorted(set(ren.F.gefunden.values())))}")
    vid_out = os.path.join(out_dir, f"{base}_bikefit.mp4")
    w = videoio.H264Writer(vid_out, meta["width"], meta["height"], meta["fps"])
    still = None
    t0 = time.time()
    for i, rgb in videoio.read_frames(args.video, meta["width"], meta["height"]):
        if i >= len(xy):
            break
        f = ren.frame(rgb, i, xy[i], cf[i], bx[i])
        w.write(f)
        if i == res["bdc_frame"]:
            still = f.copy()
        if (i + 1) % 200 == 0:
            el = time.time() - t0
            print(f"  {i+1}/{len(xy)}  {el:.0f}s  noch ~{el/(i+1)*(len(xy)-i-1):.0f}s", flush=True)
    w.close()
    if still is not None:
        from PIL import Image
        Image.fromarray(still).save(os.path.join(out_dir, f"{base}_totpunkt.png"))

    txt = bericht(res, adv, meta, args, warn, time.time() - t_start)
    with open(os.path.join(out_dir, f"{base}_bericht.txt"), "w") as fh:
        fh.write(txt)
    print(txt)
    print(f"\nGeschrieben nach {out_dir}/:")
    for f in sorted(os.listdir(out_dir)):
        print(f"  {f}  ({os.path.getsize(os.path.join(out_dir,f))/1e6:.1f} MB)")
    return 0


def bericht(res, adv, meta, args, warn, dauer) -> str:
    L = []
    A = L.append
    A("=" * 74)
    A("SCHRITT 6  --  Ergebnis")
    A("=" * 74)
    A("")
    A(f"  KNIEBEUGUNG AM UNTEREN TOTPUNKT:  {res['knee_flexion_bdc']:.1f} GRAD")
    A("")
    A(f"  {adv['satz']}")
    A("")
    A("-" * 74)
    A("Messwerte am unteren Totpunkt")
    A("-" * 74)
    rows = [("knee", "Kniebeugung", res["knee_flexion_bdc"]),
            ("trunk", "Rumpfneigung zur Waagerechten", res["trunk_bdc"]),
            ("elbow", "Ellbogenbeugung", res["elbow_bdc"]),
            ("shoulder", "Schulterwinkel", res["shoulder_bdc"]),
            ("hip", "Hueftwinkel", res["hip_bdc"])]
    for key, name, v in rows:
        sp = judge.SPECS[key]
        wort, _ = judge.judge(key, v)
        band = sp.band if sp.bewerten else "---"
        A(f"  {name:32s} {_fmt(v):>7s} Grad   {band:>18s}   {wort}")
    A("")
    A("  Rumpf und Ellbogen sind Erfahrungswerte aus der Praxis, keine belegte Norm.")
    A("  Schulter und Huefte werden gemessen und angezeigt, aber NICHT bewertet:")
    A("  die gern zitierte Studie nennt 112 Grad an der Schulter und 77 an der Huefte,")
    A("  Bike-Fit-Anleitungen dagegen 80-95 und 85-110. Das passt nicht zusammen, weil")
    A("  die Studie den Gelenkpunkt anders setzt als ein Posenmodell. Eine Farbe waere")
    A("  dort eine Behauptung, keine Messung.")
    A("")
    A("-" * 74)
    A("Wie die Millimeter zustande kommen")
    A("-" * 74)
    A(f"  Massstab aus dem Knoechelhub: {res.get('ankle_travel_px', float('nan')):.0f} px "
      f"entsprechen {2*args.kurbel:.0f} mm (zwei Kurbellaengen)")
    A(f"    -> {res['scale_mm_per_px']:.3f} mm je Pixel")
    A(f"  Oberschenkel  {res['thigh_px']:.0f} px = {_fmt(res['thigh_mm'],0)} mm")
    A(f"  Unterschenkel {res['shank_px']:.0f} px = {_fmt(res['shank_mm'],0)} mm")
    A(f"  Kosinussatz nach dem Kniewinkel abgeleitet, bei DEINEN Massen und "
      f"{180-res['knee_flexion_bdc']:.1f} Grad Kniewinkel:")
    A(f"    -> {res['mm_per_deg']:.2f} mm Sattelhoehe je Grad Kniebeugung")
    if adv["mm"]:
        A(f"  {abs(res['knee_flexion_bdc']-judge.KNEE_TARGET):.1f} Grad bis zur Bandmitte "
          f"({judge.KNEE_TARGET:.0f} Grad) x {res['mm_per_deg']:.2f} mm/Grad = {adv['mm']:.0f} mm")
    A("")
    A("-" * 74)
    A("Verlaesslichkeit")
    A("-" * 74)
    A(f"  {res['n_bdc']} Kurbelumdrehungen ausgewertet, Streuung zwischen den Totpunkten "
      f"{res['knee_flexion_spread']:.2f} Grad")
    A(f"  Messkette am kuenstlichen Zyklus geprueft: mittlerer Fehler unter 0,5 Grad")
    A(f"  Aufloesung eines Handyvideos: rund 2-3 Grad. Deshalb {judge.TOL:.1f} Grad Toleranz.")
    A(f"  Der Massstab kommt aus dem Knoechelhub und traegt rund 5 % Unsicherheit,")
    A(f"  weil der Fuss im Sprunggelenk mitarbeitet. Auf die Millimeter wirkt das direkt.")
    if args.kurbel_unbekannt:
        A(f"  Kurbellaenge nicht bekannt, gerechnet mit {args.kurbel:.1f} mm. Steht innen auf")
        A(f"  der Kurbel -- mit der echten Zahl rechne ich jederzeit neu.")
    for w in warn + res.get("warnungen", []):
        A(f"  ACHTUNG: {w}")
    A("")
    A("-" * 74)
    A("Wo diese Messung aufhoert")
    A("-" * 74)
    A("  Ein Video von der Seite kann die Sattelhoehe und die Oberkoerperhaltung")
    A("  einordnen. Es kann NICHT sehen, ob deine Knie beim Treten nach innen oder")
    A("  aussen wandern, und es kann nichts ueber die Stellung deiner Schuhplatten")
    A("  sagen. Dafuer braeuchte es eine Aufnahme von vorn.")
    A("  Wenn dir beim Fahren etwas weh tut, ersetzt das hier keinen Menschen, der")
    A("  dich anschaut.")
    A("")
    A("  Aendere immer nur EINE Sache und filme danach neu. Wer Sattelhoehe und")
    A("  Sitzposition gleichzeitig verstellt, weiss hinterher nicht, was gewirkt hat.")
    A("")
    A(f"({dauer/60:.1f} Minuten Rechenzeit)")
    return "\n".join(L)


def main():
    p = argparse.ArgumentParser(description=__doc__)
    sub = p.add_subparsers(dest="cmd", required=True)
    for name, fn in (("pruefen", cmd_pruefen), ("rechnen", cmd_rechnen)):
        s = sub.add_parser(name)
        s.add_argument("video")
        s.add_argument("--modell", default=pose.MODEL_DEFAULT)
        s.add_argument("--kurbel", type=float, default=chain.CRANK_MM_DEFAULT)
        s.add_argument("--kurbel-unbekannt", action="store_true")
        s.add_argument("--aus", default=None)
        s.set_defaults(fn=fn)
    a = p.parse_args()
    if not os.path.exists(a.video):
        print(f"Datei nicht gefunden: {a.video}"); return 2
    return a.fn(a)


if __name__ == "__main__":
    sys.exit(main())
