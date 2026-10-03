"""Per-pixel land-cover classes on the drone orthos at native resolution (3.7 / 5.7 cm).

Rules (thresholds picked from the bimodal ExG histogram of the landslide flight):
  1 vegetation   ExG = 2g - r - b (chromatic coords) >= 0.05
  4 shadow       not vegetation, brightness (R+G+B)/3 < 50
  2 soil/debris  bare, R > 1.12 B and saturation >= 0.16  (orange-brown earth)
  3 grey         bare otherwise (scoured rock in scars, roofs, concrete, grey mud)
  0 no data      alpha < 250
Also writes `*_bare.tif`: bare ground (2|3) after a 1 m x 1 m majority filter
(shadow pixels excluded from the vote), the mask that is vectorised later.
Processed in 4096 px windows with a one-filter-width halo so nothing is held whole in RAM.
"""
import sys
from pathlib import Path
import numpy as np, rasterio
from rasterio.windows import Window
from scipy.ndimage import uniform_filter

ROOT = Path(__file__).resolve().parents[1]
STEP = 4096


def classify(a):
    R, G, B, A = (x.astype(np.float32) for x in a)
    s = R + G + B + 1e-6
    exg = (2 * G - R - B) / s
    br = s / 3
    mx = np.maximum(np.maximum(R, G), B)
    mn = np.minimum(np.minimum(R, G), B)
    sat = (mx - mn) / (mx + 1e-6)
    cls = np.full(R.shape, 3, np.uint8)
    veg = exg >= 0.05
    dark = ~veg & (br < 50)
    soil = ~veg & ~dark & (R > 1.12 * B) & (sat >= 0.16)
    cls[soil] = 2
    cls[veg] = 1
    cls[dark] = 4
    cls[A < 250] = 0
    return cls


def run(tag):
    src_p = ROOT / f"data/ortho/{tag}_4326.tif"
    with rasterio.open(src_p) as src:
        prof = src.profile.copy()
        prof.update(count=1, dtype="uint8", predictor=1)
        prof.pop("photometric", None)
        W, H = src.width, src.height
        with rasterio.open(ROOT / f"data/class/{tag}_class.tif", "w", **prof) as dc, \
             rasterio.open(ROOT / f"data/class/{tag}_bare.tif", "w", **prof) as db:
            res_m = src.res[1] * 110_600
            k = int(round(1.0 / res_m)) | 1  # odd window ~1 m
            for r in range(0, H, STEP):
                for c in range(0, W, STEP):
                    r0, c0 = max(r - k, 0), max(c - k, 0)
                    r1, c1 = min(r + STEP + k, H), min(c + STEP + k, W)
                    a = src.read(window=Window(c0, r0, c1 - c0, r1 - r0))
                    if a[3].max() == 0:
                        continue
                    cls = classify(a)
                    bare = ((cls == 2) | (cls == 3)).astype(np.float32)
                    vote = ((cls != 0) & (cls != 4)).astype(np.float32)
                    fb = uniform_filter(bare, k, mode="nearest")
                    fv = uniform_filter(vote, k, mode="nearest")
                    bm = ((fb > 0.5 * fv) & (fv > 0) & (cls != 0)).astype(np.uint8)
                    ir, ic = r - r0, c - c0
                    h, w = min(STEP, H - r), min(STEP, W - c)
                    dc.write(cls[ir:ir + h, ic:ic + w], 1, window=Window(c, r, w, h))
                    db.write(bm[ir:ir + h, ic:ic + w], 1, window=Window(c, r, w, h))
                print(f"  {tag} row {r}/{H}", flush=True)
    print("done", tag, "majority window", k, "px")


if __name__ == "__main__":
    for t in (sys.argv[1:] or ["landslide", "plan2"]):
        run(t)
