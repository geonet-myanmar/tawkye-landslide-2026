"""Runout-reach screening calibrated on the mapped landslides (energy-line / Fahrboeschung).

Every DEM cell on slope >= SRC_SLOPE (the slope class the mapped scars start in) is a
potential source. Debris spreads to all lower neighbours (multiple flow direction) in
order of decreasing elevation, carrying the height of an energy line of gradient
tan(alpha) above the ground:  h_next = h + (z - z_next) - tan(alpha) * step.
A cell is within reach while h >= 0 - the path-following form of the reach angle
H/L = tan(alpha) used to describe the mapped events (06_terrain.py).

Two runs, both from the observed reach angles:
  open     alpha = smallest reach angle of the unchannelised hillslope flows
  channel  alpha = reach angle of the channelised flow (LS-04), which travelled further
Pure screening on a 30 m pre-event DEM: no volume, no velocity cap, no obstacle effect.
Writes data/hazard/reach_{open,channel}.tif, reach_zones.geojson, and per-building flags.
"""
import json
from pathlib import Path
import numpy as np, rasterio, geopandas as gpd
from rasterio import features
from shapely.geometry import shape
from shapely.ops import unary_union

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "data/hazard"
SRC_SLOPE = 20.0
OPEN_IDS = ["LS-02", "LS-03", "LS-05", "LS-06", "LS-07", "LS-08", "LS-09"]
CHANNEL_IDS = ["LS-04"]


def reach(z, slope, res, alpha_deg):
    t = np.tan(np.radians(alpha_deg))
    H, W = z.shape
    h = np.full(z.shape, -np.inf)
    src = slope >= SRC_SLOPE
    h[src] = 0.0
    order = np.argsort(-z, axis=None)
    nb = [(-1, -1), (-1, 0), (-1, 1), (0, -1), (0, 1), (1, -1), (1, 0), (1, 1)]
    for idx in order:
        r, c = divmod(int(idx), W)
        hc = h[r, c]
        if hc < 0:
            continue
        zc = z[r, c]
        for dr, dc in nb:
            rr, cc = r + dr, c + dc
            if 0 <= rr < H and 0 <= cc < W and z[rr, cc] < zc:
                d = res * (1.4142135 if dr and dc else 1.0)
                hn = hc + (zc - z[rr, cc]) - t * d
                if hn > h[rr, cc]:
                    h[rr, cc] = hn
    return h


def main():
    OUT.mkdir(exist_ok=True)
    terr = {t["id"]: t for t in json.load(open(ROOT / "data/inventory/terrain.json"))}
    a_open = min(terr[i]["reach_angle_deg"] for i in OPEN_IDS)
    a_chan = min(terr[i]["reach_angle_deg"] for i in CHANNEL_IDS)
    with rasterio.open(ROOT / "data/ee/cop30_dem_utm.tif") as d:
        z = d.read(1).astype(np.float64); T = d.transform; prof = d.profile
    with rasterio.open(ROOT / "data/ee/slope_deg.tif") as d:
        slope = d.read(1)
    prof.update(dtype="float32", nodata=-9999, compress="deflate")
    zones = {}
    for name, a in (("open", a_open), ("channel", a_chan)):
        h = reach(z, slope, T.a, a)
        hh = np.where(np.isfinite(h), h, -9999).astype("float32")
        with rasterio.open(OUT / f"reach_{name}.tif", "w", **prof) as o:
            o.write(hh, 1)
        m = (h >= 0).astype(np.uint8)
        zones[name] = unary_union([shape(g) for g, v in features.shapes(m, transform=T) if v == 1])
        print(f"{name}: alpha {a} deg, reach area {zones[name].area / 1e4:.1f} ha")
    # zone B = reached only by a channelised-type flow
    zA = zones["open"]
    zB = zones["channel"].difference(zA)
    gz = gpd.GeoDataFrame({"zone": ["A", "B"], "alpha_deg": [a_open, a_chan],
                           "label": [f"Within reach of an open-slope debris flow (alpha {a_open} deg)",
                                     f"Within reach only of a channelised flow (alpha {a_chan} deg)"]},
                          geometry=[zA, zB], crs=32647)
    gz.to_crs(4326).to_file(OUT / "reach_zones.geojson", driver="GeoJSON")

    # calibration check: how much of each mapped landslide lies inside the modelled reach
    slides = gpd.read_file(ROOT / "data/inventory/landslides_utm.gpkg")
    calib = {}
    for _, r in slides.iterrows():
        zz = zones["channel"] if r["id"] in CHANNEL_IDS else zA
        calib[r["id"]] = round(r.geometry.intersection(zz).area / r.geometry.area, 3)
    print("share of each mapped landslide inside modelled reach:", calib)

    b = gpd.read_file(ROOT / "data/inventory/buildings_utm.gpkg")
    b["reach"] = np.where(b.geometry.intersects(zA), "A", np.where(b.geometry.intersects(zB), "B", ""))
    b.to_file(ROOT / "data/inventory/buildings_utm.gpkg", driver="GPKG")
    b.to_crs(4326).to_file(ROOT / "data/inventory/buildings.geojson", driver="GeoJSON")
    surv = b[b.status != "not_surveyed"]
    tab = surv.groupby(["status", "reach"]).size().unstack(fill_value=0)
    print(tab.to_string())
    json.dump({"alpha_open": a_open, "alpha_channel": a_chan, "src_slope": SRC_SLOPE,
               "zoneA_ha": round(zA.area / 1e4, 2), "zoneB_ha": round(zB.area / 1e4, 2),
               "calibration_share_inside": calib,
               "buildings_surveyed_by_status_reach": {s: {k: int(v) for k, v in row.items()} for s, row in tab.iterrows()}},
              open(OUT / "runout_summary.json", "w"), indent=1)


if __name__ == "__main__":
    main()
