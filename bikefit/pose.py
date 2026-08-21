"""Posenerkennung: 17 Koerperpunkte je Bild, in Pixeln.

Alles danach ist Geometrie auf diesen Punkten -- kein weiteres Modell.
"""
from __future__ import annotations
import os, time, numpy as np
import videoio

MODEL_DEFAULT = "yolo11x-pose.pt"


def pick_device() -> tuple[str, str]:
    import torch
    if torch.cuda.is_available():
        return "cuda", torch.cuda.get_device_name(0)
    mps = getattr(torch.backends, "mps", None)
    if mps is not None and mps.is_available():
        return "mps", "Apple-Chip"
    return "cpu", f"CPU, {os.cpu_count()} Kerne"


def extract(path: str, meta: dict, model_name: str = MODEL_DEFAULT,
            step: int = 1, device: str | None = None, imgsz: int = 640,
            progress_every: int = 50):
    """Gibt (frame_idx, xy(F,17,2) in Pixeln, conf(F,17), box(F,4)) zurueck.

    WICHTIG 1: keypoints.xy sind Pixel. .xyn waeren je Achse normiert und
    wuerden bei Hochformat jeden Winkel stauchen -- wir fassen sie nicht an.
    """
    from ultralytics import YOLO
    import torch
    torch.set_num_threads(os.cpu_count() or 4)
    dev = device or pick_device()[0]
    model = YOLO(model_name)

    idxs, XY, CF, BX = [], [], [], []
    t0 = time.time()
    n_expect = max(1, meta["n_frames"] // step)
    for k, (i, rgb) in enumerate(videoio.read_frames(path, meta["width"], meta["height"], step=step)):
        r = model.predict(rgb[:, :, ::-1], imgsz=imgsz, device=dev,
                          verbose=False, max_det=10)[0]
        xy = np.full((17, 2), np.nan)
        cf = np.zeros(17)
        bx = np.full(4, np.nan)
        if r.keypoints is not None and len(r.keypoints) > 0 and r.keypoints.conf is not None:
            kc = r.keypoints.conf.cpu().numpy()          # (n,17)
            kxy = r.keypoints.xy.cpu().numpy()           # (n,17,2) PIXEL
            j = int(np.argmax(kc.mean(axis=1)))          # hoechste mittlere Zuversicht
            xy, cf = kxy[j], kc[j]
            if r.boxes is not None and len(r.boxes) > j:
                bx = r.boxes.xyxy.cpu().numpy()[j]
        idxs.append(i); XY.append(xy); CF.append(cf); BX.append(bx)
        if progress_every and (k + 1) % progress_every == 0:
            el = time.time() - t0
            print(f"  {k+1}/{n_expect} Bilder  {el:.0f}s  "
                  f"noch ~{el/(k+1)*(n_expect-k-1):.0f}s", flush=True)
    return (np.array(idxs), np.array(XY), np.array(CF), np.array(BX))


def cache_path(video: str, model_name: str, step: int) -> str:
    base = os.path.splitext(os.path.basename(video))[0]
    return os.path.join(os.path.dirname(os.path.abspath(video)) or ".",
                        f".{base}.{os.path.splitext(model_name)[0]}.s{step}.npz")


def extract_cached(path, meta, model_name=MODEL_DEFAULT, step=1, device=None):
    cp = cache_path(path, model_name, step)
    if os.path.exists(cp):
        z = np.load(cp)
        print(f"  (Punkte aus dem Zwischenspeicher: {os.path.basename(cp)})")
        return z["idx"], z["xy"], z["cf"], z["bx"]
    out = extract(path, meta, model_name, step=step, device=device)
    np.savez_compressed(cp, idx=out[0], xy=out[1], cf=out[2], bx=out[3])
    return out
