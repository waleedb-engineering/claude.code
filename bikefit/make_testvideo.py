"""Rendert den kuenstlichen Tretzyklus als echtes Video.

Dient nur dazu, die vollstaendige Kette einmal durchlaufen zu lassen --
Videolesen, Posenerkennung, Messung, Overlay, H.264 -- bevor ein echter Clip
angefasst wird.
"""
import numpy as np
from PIL import Image, ImageDraw
import synth, videoio, chain

W, H, FPS, DUR = 1080, 1920, 30.0, 12.0
SCALE, ORIGIN = 0.8, (260.0, 1560.0)
SKIN, KIT, BIKE = (222, 184, 152), (38, 92, 168), (60, 62, 68)


def capsule(d, a, b, r, fill):
    d.line([tuple(a), tuple(b)], fill=fill, width=int(2 * r))
    for p in (a, b):
        d.ellipse([p[0] - r, p[1] - r, p[0] + r, p[1] + r], fill=fill)


def draw(xy):
    img = Image.new("RGB", (W, H), (206, 203, 197))
    d = ImageDraw.Draw(img)
    d.rectangle([0, 1620, W, H], fill=(150, 143, 132))           # Boden
    d.rectangle([0, 1600, W, 1626], fill=(120, 114, 105))
    g = lambda i: xy[i]
    bb = np.array(ORIGIN)
    hip, knee, ank = g(chain.R_HIP), g(chain.R_KNEE), g(chain.R_ANKLE)
    sh, el, wr = g(chain.R_SHOULDER), g(chain.R_ELBOW), g(chain.R_WRIST)
    # Rad
    d.ellipse([bb[0] - 700, bb[1] - 300, bb[0] - 20, bb[1] + 380], outline=BIKE, width=9)
    saddle = hip + np.array([18, 46])
    capsule(d, bb, saddle, 7, BIKE)                                # Sitzrohr
    capsule(d, bb, wr + np.array([16, 66]), 7, BIKE)               # Unterrohr
    d.rounded_rectangle([saddle[0] - 78, saddle[1] - 14, saddle[0] + 46, saddle[1] + 12],
                        radius=12, fill=(28, 28, 30))
    capsule(d, bb, ank, 6, (150, 152, 158))                        # Kurbel
    d.rounded_rectangle([ank[0] - 30, ank[1] - 7, ank[0] + 30, ank[1] + 7], radius=5, fill=(30, 30, 32))
    d.rounded_rectangle([wr[0] - 60, wr[1] - 12, wr[0] + 34, wr[1] + 12], radius=11, fill=(24, 24, 26))
    # Koerper
    capsule(d, hip, knee, 30, KIT)
    capsule(d, knee, ank, 21, SKIN)
    d.polygon([tuple(sh + [-30, -18]), tuple(sh + [34, -4]),
               tuple(hip + [30, 6]), tuple(hip + [-34, -8])], fill=KIT)
    capsule(d, sh, el, 20, KIT)
    capsule(d, el, wr, 15, SKIN)
    head = sh + np.array([88, -104])
    capsule(d, sh + [24, -22], head, 15, SKIN)
    d.ellipse([head[0] - 46, head[1] - 46, head[0] + 46, head[1] + 46], fill=SKIN)
    d.chord([head[0] - 50, head[1] - 54, head[0] + 50, head[1] + 40], 168, 372, fill=(230, 232, 236))
    d.ellipse([head[0] + 26, head[1] - 8, head[0] + 40, head[1] + 6], fill=(40, 40, 44))
    return np.asarray(img)


if __name__ == "__main__":
    xy, cf, _ = synth.build_clip(duration_s=DUR, fps=FPS, cadence_rpm=82.0,
                                 phase0=0.4, scale=SCALE, origin=ORIGIN, seed=3)
    w = videoio.H264Writer("testclip.mp4", W, H, FPS)
    for i in range(len(xy)):
        w.write(draw(xy[i]))
    w.close()
    np.savez_compressed("testclip_wahrheit.npz", xy=xy, cf=cf)
    print(f"testclip.mp4 geschrieben: {len(xy)} Bilder @ {FPS} fps")
