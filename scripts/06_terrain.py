"""Terrain metrics per landslide from the Copernicus GLO-30 DEM (pre-event surface, 30 m).

Per landslide:
  crown / toe     highest / lowest DEM point on the outline (bilinear, outline densified 2 m)
  H, L            crown-to-toe drop and horizontal distance; H/L = tan(reach angle)
  azimuth         crown -> toe bearing (direction of travel)
  zones           area on DEM slope >= 20 deg (source), 8-20 (transport), < 8 (valley-floor runout)
  ndvi_pre        mean Jan-Apr 2026 Sentinel-2 NDVI over the whole outline and its source zone
                  (was the ground vegetated before the event?)
Also writes slope / hillshade rasters for the page and terrain.json.
"""
import json
from pathlib import Path
import numpy as np, rasterio, geopandas as gpd
from rasterio import features
from shapely.geometry import Point, shape
from shapely.ops import unary_union
from scipy.ndimage import map_coordinates

ROOT = Path(__file__).resolve().parents[1]
INV = ROOT / "data/inventory"
ZONES = [("source", 20, 90), ("transport", 8, 20), ("runout", 0, 8)]


def main():
    with rasterio.open(ROOT / "data/ee/cop30_dem_utm.tif") as d:
        z = d.read(1).astype(np.float64)
        T = d.transform
        prof = d.profile
    res = T.a
    gy, gx = np.gradient(z, res)
    slope = np.degrees(np.arctan(np.hypot(gx, gy)))
    az = np.radians(315)
    alt = np.radians(45)
    aspect = np.arctan2(-gx, gy)
    hs = np.sin(alt) * np.cos(np.arctan(np.hypot(gx, gy))) + np.cos(alt) * np.sin(np.arctan(np.hypot(gx, gy))) * np.cos(az - aspect)
    prof.update(dtype="float32", count=1, compress="deflate")
    with rasterio.open(ROOT / "data/ee/slope_deg.tif", "w", **prof) as o:
        o.write(slope.astype("float32"), 1)
    with rasterio.open(ROOT / "data/ee/hillshade.tif", "w", **prof) as o:
        o.write(hs.astype("float32"), 1)

    inv = rasterio.transform.AffineTransformer(T)
    with rasterio.open(ROOT / "data/ee/s2_ndvi_pre_2026JanApr.tif") as d:
        ndvi = d.read(1).astype(np.float64)
        inv_n = rasterio.transform.AffineTransformer(d.transform)

    def sample(arr, xs, ys, tr=inv):
        r, c = tr.rowcol(xs, ys, op=lambda v: v)  # fractional
        # rowcol gives pixel-corner based coords; shift to pixel centres
        return map_coordinates(arr, [np.asarray(r) - 0.5, np.asarray(c) - 0.5], order=1, mode="nearest")

    zone_polys = {}
    for name, lo, hi in ZONES:
        m = ((slope >= lo) & (slope < hi)).astype(np.uint8)
        zone_polys[name] = unary_union([shape(g) for g, v in features.shapes(m, transform=T) if v == 1])

    g = gpd.read_file(INV / "landslides_utm.gpkg")
    out = []
    for _, r in g.iterrows():
        geom = r.geometry
        pts = []
        for p in getattr(geom, "geoms", [geom]):
            ring = p.exterior
            n = max(int(ring.length / 2), 4)
            pts += [ring.interpolate(i / n, normalized=True) for i in range(n)]
        xs = np.array([p.x for p in pts]); ys = np.array([p.y for p in pts])
        zz = sample(z, xs, ys)
        i_hi, i_lo = int(zz.argmax()), int(zz.argmin())
        crown, toe = Point(xs[i_hi], ys[i_hi]), Point(xs[i_lo], ys[i_lo])
        H = float(zz[i_hi] - zz[i_lo]); L = float(crown.distance(toe))
        azim = (np.degrees(np.arctan2(toe.x - crown.x, toe.y - crown.y)) + 360) % 360
        # slope statistics over the outline's interior on a 2 m lattice
        minx, miny, maxx, maxy = geom.bounds
        gxs, gys = np.meshgrid(np.arange(minx + 1, maxx, 2.0), np.arange(maxy - 1, miny, -2.0))
        inside = features.geometry_mask([geom], out_shape=gxs.shape, invert=True,
                                        transform=rasterio.transform.from_origin(minx, maxy, 2.0, 2.0))
        sl = sample(slope, gxs[inside], gys[inside])
        nd = sample(ndvi, gxs[inside], gys[inside], inv_n)
        zones = {k: round(geom.intersection(v).area, 1) for k, v in zone_polys.items()}
        out.append({"id": r["id"], "crown_z": round(float(zz[i_hi]), 1), "toe_z": round(float(zz[i_lo]), 1),
                    "H_m": round(H, 1), "L_m": round(L, 1), "H_over_L": round(H / L, 3) if L else None,
                    "reach_angle_deg": round(float(np.degrees(np.arctan2(H, L))), 1),
                    "azimuth_deg": round(float(azim)), "slope_mean_deg": round(float(sl.mean()), 1),
                    "slope_p90_deg": round(float(np.percentile(sl, 90)), 1),
                    "crown_lonlat": list(gpd.GeoSeries([crown], crs=32647).to_crs(4326).iloc[0].coords[0]),
                    "toe_lonlat": list(gpd.GeoSeries([toe], crs=32647).to_crs(4326).iloc[0].coords[0]),
                    "ndvi_pre_mean": round(float(np.nanmean(nd)), 2),
                    "ndvi_pre_source": round(float(np.nanmean(nd[sl >= 20])), 2) if (sl >= 20).any() else None,
                    "zone_m2": zones})
        print(out[-1]["id"], {k: out[-1][k] for k in ("crown_z", "toe_z", "H_m", "L_m", "reach_angle_deg", "slope_mean_deg", "ndvi_pre_mean", "ndvi_pre_source")}, zones)
    json.dump(out, open(INV / "terrain.json", "w"), indent=1)


if __name__ == "__main__":
    main()
