"""Collect every product into one payload, export GIS deliverables, and render the page.

Outputs
  outputs/tawkye_landslide_2026.gpkg   landslides, buildings, reach zones, envelopes, crown/toe
  outputs/landslides.csv, outputs/buildings.csv, outputs/summary.json
  index.html                           standalone page (doctype + head) for GitHub Pages / local use
  dist/artifact-body.html              the same body fragment without the wrapper
src/template.html is the single source of truth for the page; never hand-edit index.html.
"""
import json, shutil
from pathlib import Path
import numpy as np, pandas as pd, geopandas as gpd
from shapely.geometry import Point, box

ROOT = Path(__file__).resolve().parents[1]
INV, HZ, RAW = ROOT / "data/inventory", ROOT / "data/hazard", ROOT / "data/raw"
OUTD = ROOT / "outputs"
SITE = "https://geonet-myanmar.github.io/tawkye-landslide-2026/"

REPORT = {  # Dawei Watch, 1 Oct 2026 (Burmese), via data/source of dawei-flood-dashboard-v6
    "source": "Dawei Watch, 1 Oct 2026",
    "deaths": 5, "missing_bodies": 3, "houses_destroyed": 42,
    "onset": "night of 26 Sep 2026",
    "note": "Two men, a nun and two women died; the bodies of three people had not been recovered on 1 Oct. "
            "Heavy-machinery crews clearing the blocked road reached the village on 1 Oct.",
}


def r1(x):
    return None if x is None else round(float(x), 1)


def main():
    OUTD.mkdir(exist_ok=True)
    sl = gpd.read_file(INV / "landslides_utm.gpkg")
    terr = {t["id"]: t for t in json.load(open(INV / "terrain.json"))}
    b = gpd.read_file(INV / "buildings_utm.gpkg")
    zones = gpd.read_file(HZ / "reach_zones.geojson")
    runout = json.load(open(HZ / "runout_summary.json"))
    shifts = json.load(open(INV / "footprint_shifts.json"))
    env = gpd.read_file(INV / "envelopes.geojson")
    fps = {t: gpd.read_file(INV / f"footprint_{t}_flight.geojson") for t in ("landslide", "plan2")}
    rain = json.load(open(ROOT / "data/source/rainfall_openmeteo_tawkye.json"))

    surv = b[b.status != "not_surveyed"].copy()
    # ---- per-landslide table
    rows = []
    for _, r in sl.iterrows():
        t = terr[r["id"]]
        hit = surv[surv["landslide"].fillna("").str.split(",").apply(lambda L: r["id"] in L)]
        rows.append({
            "id": r["id"], "name": r["name"], "description": r["description"],
            "area_m2": round(r["area_m2"]), "soil_m2": round(r["soil_m2"]), "grey_m2": round(r["grey_m2"]),
            "crown_z": t["crown_z"], "toe_z": t["toe_z"], "H_m": t["H_m"], "L_m": t["L_m"],
            "reach_angle_deg": t["reach_angle_deg"], "azimuth_deg": t["azimuth_deg"],
            "slope_mean_deg": t["slope_mean_deg"], "ndvi_pre_mean": t["ndvi_pre_mean"], "ndvi_pre_source": t["ndvi_pre_source"],
            "source_m2": round(t["zone_m2"]["source"]), "transport_m2": round(t["zone_m2"]["transport"]),
            "runout_m2": round(t["zone_m2"]["runout"]),
            "destroyed": int((hit.status == "destroyed").sum()), "damaged": int((hit.status == "damaged").sum()),
            "edge": int((hit.status == "edge").sum()),
            "crown": t["crown_lonlat"], "toe": t["toe_lonlat"],
            "label": list(gpd.GeoSeries([max(getattr(r.geometry, "geoms", [r.geometry]), key=lambda p: p.area)
                                         .representative_point()], crs=32647).to_crs(4326).iloc[0].coords[0]),
        })
    tab = pd.DataFrame(rows)
    tab.drop(columns=["crown", "toe", "label"]).to_csv(OUTD / "landslides.csv", index=False)

    # ---- buildings
    bcols = ["bid", "source", "src_id", "area_m2", "flight", "status", "status_auto", "landslide", "overlap",
             "dist_m", "f_veg", "f_soil", "f_grey", "f_dark", "reach", "note"]
    for c in bcols:
        if c not in surv:
            surv[c] = None
    surv[bcols].to_csv(OUTD / "buildings.csv", index=False)
    counts = surv.status.value_counts().to_dict()
    reach_counts = {
        "standing_in_A": int((surv.status.isin(["clear", "edge"]) & (surv.reach == "A")).sum()),
        "standing_in_B": int((surv.status.isin(["clear", "edge"]) & (surv.reach == "B")).sum()),
        "standing_outside": int((surv.status.isin(["clear", "edge"]) & (surv.reach.fillna("") == "")).sum()),
        "affected": int(surv.status.isin(["destroyed", "damaged"]).sum()),
        "affected_in_A": int((surv.status.isin(["destroyed", "damaged"]) & (surv.reach == "A")).sum()),
    }

    # ---- rain
    hourly = rain["hourly"]
    def hsum(a, z):
        return round(sum(v or 0 for k, v in hourly.items() if a <= k < z), 1)
    rain_s = {
        "daily": [{"date": k, "mm": v} for k, v in rain["daily"].items()],
        "hourly": [{"t": k, "mm": v} for k, v in hourly.items() if "2026-09-25T00" <= k < "2026-09-29T00"],
        "night_26_27": hsum("2026-09-26T20", "2026-09-27T06"),
        "d25_28": round(sum(v for k, v in rain["daily"].items() if "2026-09-25" <= k <= "2026-09-28"), 1),
        "sep_total": round(sum(v for k, v in rain["daily"].items() if k < "2026-10-01"), 1),
        "fetched": rain["fetched_utc"], "grid": [rain["grid_lat"], rain["grid_lon"]],
    }

    # ---- MIMU context
    aoi_ll = box(98.10, 13.74, 98.22, 13.85)
    vil = gpd.read_file(RAW / "village_points_tni.geojson")
    vil = vil[vil.intersects(aoi_ll)][["VILLAGE", "VLG_MMR", "VLG_PCODE", "VT", "VT_PCODE", "TS", "geometry"]]
    vt = gpd.read_file(RAW / "adm4_vt_tanintharyi.geojson")
    vt = vt[vt.intersects(aoi_ll)][["VT", "VT_MMR", "VT_PCODE", "TS", "geometry"]]
    vt["geometry"] = vt.geometry.simplify(0.0002)
    ts = gpd.read_file(RAW / "adm3_townships.geojson")
    ts = ts[ts.TS == "Launglon"][["TS", "TS_MMR", "TS_PCODE", "geometry"]]
    ts["geometry"] = ts.geometry.simplify(0.0005)
    roads = gpd.read_file(RAW / "roads.geojson").clip(aoi_ll)[["Road_Type", "geometry"]]
    sch = gpd.read_file(RAW / "schools_lower.geojson")
    sch = sch[sch.intersects(aoi_ll)][["schoolname", "geometry"]]
    tk = vil[vil.VLG_PCODE.astype(str) == "177208"].iloc[0]

    # ---- GIS export
    gpkg = OUTD / "tawkye_landslide_2026.gpkg"
    if gpkg.exists():
        gpkg.unlink()
    sl.to_file(gpkg, layer="landslides", driver="GPKG")
    surv.to_file(gpkg, layer="buildings_surveyed", driver="GPKG")
    zones.to_crs(32647).to_file(gpkg, layer="runout_reach_zones", driver="GPKG")
    env.to_file(gpkg, layer="interpretation_envelopes", driver="GPKG")
    pts = gpd.GeoDataFrame(
        [{"id": r["id"], "kind": k, "z_m": r["crown_z"] if k == "crown" else r["toe_z"], "geometry": Point(r[k])}
         for r in rows for k in ("crown", "toe")], crs=4326)
    pts.to_crs(32647).to_file(gpkg, layer="crown_toe_points", driver="GPKG")

    total = float(tab.area_m2.sum())
    summary = {
        "n_landslides": len(tab), "area_total_m2": round(total),
        "area_runout_flat_m2": int(tab.runout_m2.sum()),
        "area_hillslope_m2": int(tab.source_m2.sum() + tab.transport_m2.sum()),
        "buildings_surveyed": int(len(surv)), "buildings_status": {k: int(v) for k, v in counts.items()},
        "reach": reach_counts, "runout": runout, "footprint_shifts": shifts,
        "flight_offset_m": {"dE": -1.29, "dN": -2.49, "n_blocks": 11,
                            "note": "Plan-2 flight minus landslide flight, phase correlation in the 3.15 ha overlap"},
        "report": REPORT, "rain": {k: v for k, v in rain_s.items() if k not in ("daily", "hourly")},
        "village": {"name": "Taw Kye", "mmr": tk.VLG_MMR, "pcode": str(tk.VLG_PCODE), "vt": tk.VT,
                    "vt_pcode": tk.VT_PCODE, "ts": tk.TS, "lon": tk.geometry.x, "lat": tk.geometry.y},
        "flights": {"landslide": {"gsd_cm": 3.75, "file": "TawKyel_Village_Landslide.kmz",
                                  "area_ha": round(fps["landslide"].to_crs(32647).area.iloc[0] / 1e4, 1)},
                    "plan2": {"gsd_cm": 5.68, "file": "TawKyel_Plan-2.kmz",
                              "area_ha": round(fps["plan2"].to_crs(32647).area.iloc[0] / 1e4, 1)}},
    }
    json.dump(summary, open(OUTD / "summary.json", "w"), indent=1, default=str)

    def gj(g, prec=7):
        d = json.loads(g.to_crs(4326).to_json(drop_id=True))
        def rnd(c):
            return [rnd(x) for x in c] if isinstance(c[0], (list, tuple)) else [round(c[0], prec), round(c[1], prec)]
        for f in d["features"]:
            f["geometry"]["coordinates"] = rnd(f["geometry"]["coordinates"])
        return d

    bweb = surv[["bid", "source", "status", "landslide", "overlap", "f_grey", "f_soil", "f_veg", "reach", "note", "geometry"]].copy()
    bweb["note"] = bweb["note"].fillna("")
    payload = {
        "summary": summary, "landslides": rows, "rain": rain_s,
        "geo": {
            "landslides": gj(sl[["id", "name", "area_m2", "geometry"]]),
            "buildings": gj(bweb),
            "zones": gj(zones[["zone", "alpha_deg", "label", "geometry"]], 6),
            "flights": gj(pd.concat([fps["landslide"], fps["plan2"]], ignore_index=True).pipe(gpd.GeoDataFrame, crs=4326)),
            "villages": gj(vil, 6), "vt": gj(vt, 6), "township": gj(ts, 5), "roads": gj(roads, 6),
            "schools": gj(sch, 6),
        },
    }
    tpl = (ROOT / "src/template.html").read_text(encoding="utf-8")
    body = tpl.replace("/*__DATA__*/null", json.dumps(payload, ensure_ascii=False, separators=(",", ":")))
    (ROOT / "dist").mkdir(exist_ok=True)
    (ROOT / "dist/artifact-body.html").write_text(body, encoding="utf-8")
    head = f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Taw Kye Landslides</title>
<meta name="description" content="Drone-orthomosaic analysis of the 26 Sep 2026 landslides at Taw Kye village, Launglon Township, Tanintharyi Region, Myanmar.">
<link rel="canonical" href="{SITE}">
<meta property="og:url" content="{SITE}">
<meta property="og:title" content="Taw Kye Landslides, 26 Sep 2026">
<link rel="icon" href="data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 32 32'%3E%3Cpath d='M2 28 L13 8 L19 18 L23 13 L30 28 Z' fill='%23b8742a'/%3E%3C/svg%3E">
</head>
<body>
"""
    (ROOT / "index.html").write_text(head + body + "\n</body>\n</html>\n", encoding="utf-8")
    print("index.html", round((ROOT / "index.html").stat().st_size / 1e6, 2), "MB")
    print(json.dumps({k: summary[k] for k in ("n_landslides", "area_total_m2", "area_runout_flat_m2", "buildings_surveyed",
                                              "buildings_status", "reach")}, indent=1))


if __name__ == "__main__":
    main()
