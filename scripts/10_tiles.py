"""Web-map tiles of both drone orthos at native resolution.

512 px WebP tiles in the XYZ scheme (Leaflet: tileSize 512, zoomOffset -1). The deepest
level, z21 in 512 px tiles, is 3.6 cm/px at 13.8 N - the landslide flight's native
3.7 cm (the Plan-2 flight's 5.7 cm is upsampled slightly, never reduced). Lower levels
are built by 2x2 averaging of their children. The landslide flight is drawn over Plan-2
where the two overlap (3 ha), matching the inventory's choice. Blank tiles are skipped.
"""
import math
from pathlib import Path
import numpy as np, rasterio
from rasterio.vrt import WarpedVRT
from rasterio.enums import Resampling
from rasterio.transform import Affine
from rasterio.windows import Window
from PIL import Image

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "tiles"
ZMAX, ZMIN, TS = 21, 13, 512
R = 20037508.342789244


def tile_range(z, bounds_ll):
    w, s, e, n = bounds_ll
    def xy(lon, lat):
        x = (lon + 180) / 360 * 2 ** z
        y = (1 - math.log(math.tan(math.radians(lat)) + 1 / math.cos(math.radians(lat))) / math.pi) / 2 * 2 ** z
        return x, y
    x0, y0 = xy(w, n); x1, y1 = xy(e, s)
    return int(x0), int(x1), int(y0), int(y1)


def main():
    res = 2 * R / (2 ** ZMAX * TS)
    grid = Affine(res, 0, -R, 0, -res, R)
    srcs = [rasterio.open(ROOT / f"data/ortho/{t}_4326.tif") for t in ("plan2", "landslide")]
    W = H = 2 ** ZMAX * TS
    vrts = [WarpedVRT(s, crs="EPSG:3857", transform=grid, width=W, height=H, resampling=Resampling.bilinear)
            for s in srcs]
    b = [min(s.bounds.left for s in srcs), min(s.bounds.bottom for s in srcs),
         max(s.bounds.right for s in srcs), max(s.bounds.top for s in srcs)]
    x0, x1, y0, y1 = tile_range(ZMAX, b)
    n = 0
    have = set()
    for ty in range(y0, y1 + 1):
        for tx in range(x0, x1 + 1):
            win = Window(tx * TS, ty * TS, TS, TS)
            out = np.zeros((4, TS, TS), np.uint8)
            for v in vrts:  # plan2 first, landslide on top
                a = v.read(window=win)
                m = a[3] > 0
                out[:, m] = a[:, m]
            if out[3].max() == 0:
                continue
            p = OUT / str(ZMAX) / str(tx) / f"{ty}.webp"
            p.parent.mkdir(parents=True, exist_ok=True)
            Image.fromarray(out.transpose(1, 2, 0), "RGBA").save(p, "WEBP", quality=82, method=4)
            have.add((tx, ty)); n += 1
        print(f"z{ZMAX} row {ty - y0 + 1}/{y1 - y0 + 1}  tiles {n}", flush=True)
    for z in range(ZMAX - 1, ZMIN - 1, -1):
        parents = {(x // 2, y // 2) for x, y in have}
        nxt = set()
        for px, py in parents:
            canvas = Image.new("RGBA", (2 * TS, 2 * TS))
            for dx in (0, 1):
                for dy in (0, 1):
                    c = OUT / str(z + 1) / str(2 * px + dx) / f"{2 * py + dy}.webp"
                    if c.exists():
                        canvas.paste(Image.open(c).convert("RGBA"), (dx * TS, dy * TS))
            img = canvas.resize((TS, TS), Image.BOX)
            p = OUT / str(z) / str(px) / f"{py}.webp"
            p.parent.mkdir(parents=True, exist_ok=True)
            img.save(p, "WEBP", quality=82, method=4)
            nxt.add((px, py))
        have = nxt
        print(f"z{z}: {len(nxt)} tiles", flush=True)


if __name__ == "__main__":
    main()
