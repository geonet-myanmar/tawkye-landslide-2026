"""Stitch a KML super-overlay (quadtree of GroundOverlays) into one GeoTIFF.

Every leaf tile is 512x512 in plain lat/lon (EPSG:4326), and the quadtree is an
exact subdivision of the root box, so each tile lands on integer pixel offsets
of the deepest-level grid. Every leaf in both files is at the deepest level
(checked), so only those tiles are painted.
Written window-by-window - the 3.7 cm mosaic is ~1 Gpx and never sits in RAM.
"""
import io, sys, zipfile, xml.etree.ElementTree as ET
from pathlib import Path
import numpy as np, rasterio
from rasterio.transform import from_origin
from rasterio.windows import Window
from PIL import Image

NS = {"k": "http://www.opengis.net/kml/2.2"}
ROOT = Path(__file__).resolve().parents[1]
JOBS = {"TawKyel_Village_Landslide.kmz": "landslide", "TawKyel_Plan-2.kmz": "plan2"}


def overlays(z):
    kml = ET.fromstring(z.read("doc.kml"))
    out = []
    for go in kml.iter("{%s}GroundOverlay" % NS["k"]):
        b = go.find("k:LatLonBox", NS)
        box = {t: float(b.find("k:" + t, NS).text) for t in ("west", "east", "south", "north")}
        href = go.find("k:Icon/k:href", NS).text
        out.append((href, box))
    return out


def run(kmz, tag):
    z = zipfile.ZipFile(ROOT / kmz)
    ovs = overlays(z)
    root = next(b for h, b in ovs if h.startswith("a."))
    depth = max(ord(h[0]) - ord("a") for h, _ in ovs)
    n = 2 ** depth * 512
    dx = (root["east"] - root["west"]) / n
    dy = (root["north"] - root["south"]) / n
    print(f"{kmz}: depth {depth}, grid {n}x{n}, px {dx:.3e} x {dy:.3e} deg")
    out = ROOT / "data/ortho" / f"{tag}_4326.tif"
    prof = dict(driver="GTiff", width=n, height=n, count=4, dtype="uint8", crs="EPSG:4326",
                transform=from_origin(root["west"], root["north"], dx, dy), tiled=True,
                blockxsize=512, blockysize=512, compress="deflate", predictor=2, BIGTIFF="YES",
                photometric="RGB")
    ovs = [(h, b) for h, b in ovs if ord(h[0]) - ord("a") == depth]
    with rasterio.open(out, "w", **prof) as dst:
        for i, (href, b) in enumerate(ovs):
            c0 = round((b["west"] - root["west"]) / dx)
            r0 = round((root["north"] - b["north"]) / dy)
            im = Image.open(io.BytesIO(z.read(href))).convert("RGBA")
            a = np.asarray(im).transpose(2, 0, 1)
            dst.write(a, window=Window(c0, r0, 512, 512))
            if i % 200 == 0:
                print(f"  {i}/{len(ovs)}", flush=True)
    print("wrote", out)


if __name__ == "__main__":
    for kmz, tag in JOBS.items():
        if len(sys.argv) == 1 or tag in sys.argv[1:]:
            run(kmz, tag)
