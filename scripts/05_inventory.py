"""Landslide inventory: native-resolution outlines inside the interpreter envelopes.

For every envelope (data/inventory/envelopes.geojson, priority order - an earlier
envelope keeps any overlap) and every drone flight it touches:
  1. read the 1 m-majority bare-ground mask and the class raster at native resolution
  2. keep bare pixels inside the envelope; in the Plan-2 flight, drop pixels the
     (finer, 3.7 cm) landslide flight also covers so the 3 ha overlap is counted once
  3. drop bare specks < 10 m2 and fill holes < 10 m2 (roof-sized gaps, shadows)
  4. count soil/debris vs grey (scoured rock, roofs, grey mud) pixels -> areas
  5. vectorise, union across flights, simplify 0.1 m
Writes data/inventory/landslides.geojson (EPSG:4326) and landslides_utm.gpkg.
"""
import json
from pathlib import Path
import numpy as np, rasterio, geopandas as gpd
from rasterio import features
from rasterio.windows import from_bounds, Window
from rasterio.enums import Resampling
from scipy import ndimage as ndi
from shapely.geometry import shape, box
from shapely.ops import unary_union
from pyproj import Geod

ROOT = Path(__file__).resolve().parents[1]
INV = ROOT / "data/inventory"
FLIGHTS = ["landslide", "plan2"]  # landslide flight first: it wins the overlap
MIN_PART_M2 = 10.0
MIN_HOLE_M2 = 10.0
GEOD = Geod(ellps="WGS84")


def pixel_area(ds):
    lat = (ds.bounds.top + ds.bounds.bottom) / 2
    lon = (ds.bounds.left + ds.bounds.right) / 2
    _, _, dx = GEOD.inv(lon, lat, lon + ds.res[0], lat)
    _, _, dy = GEOD.inv(lon, lat, lon, lat + ds.res[1])
    return dx * dy


def footprint(tag):
    """Data footprint of a flight (alpha > 0) from its 1/16 overview, EPSG:4326."""
    with rasterio.open(ROOT / f"data/ortho/{tag}_4326.tif") as d:
        f = 16
        a = d.read(4, out_shape=(d.height // f, d.width // f), resampling=Resampling.nearest)
        t = d.transform * d.transform.scale(d.width / a.shape[1], d.height / a.shape[0])
    polys = [shape(g) for g, v in features.shapes((a > 0).astype(np.uint8), transform=t) if v == 1]
    return unary_union(polys)


def clean(mask, px_area):
    lab, n = ndi.label(mask)
    if n:
        sizes = ndi.sum_labels(np.ones_like(lab, np.uint8), lab, index=np.arange(1, n + 1))
        keep = np.zeros(n + 1, bool)
        keep[1:] = sizes * px_area >= MIN_PART_M2
        mask = keep[lab]
    holes = ~mask
    lab, n = ndi.label(holes)
    if n:
        sizes = ndi.sum_labels(np.ones_like(lab, np.uint8), lab, index=np.arange(1, n + 1))
        # a hole touching the window edge is outside, not a hole
        edge = np.unique(np.concatenate([lab[0], lab[-1], lab[:, 0], lab[:, -1]]))
        fill = np.zeros(n + 1, bool)
        fill[1:] = sizes * px_area < MIN_HOLE_M2
        fill[edge] = False
        mask = mask | fill[lab]
    return mask


def main():
    env = gpd.read_file(INV / "envelopes.geojson").sort_values("priority")
    env_ll = env.to_crs(4326)
    fp_ls = footprint("landslide")
    taken = None
    rows = []
    for (_, e), (_, e_ll) in zip(env.iterrows(), env_ll.iterrows()):
        geom = e_ll.geometry if taken is None else e_ll.geometry.difference(taken)
        taken = e_ll.geometry if taken is None else taken.union(e_ll.geometry)
        parts, n_soil, n_grey, area = [], 0.0, 0.0, 0.0
        for tag in FLIGHTS:
            g = geom if tag == "landslide" else geom.difference(fp_ls)
            if g.is_empty:
                continue
            with rasterio.open(ROOT / f"data/class/{tag}_bare.tif") as db, \
                 rasterio.open(ROOT / f"data/class/{tag}_class.tif") as dc:
                if not box(*db.bounds).intersects(g):
                    continue
                pa = pixel_area(db)
                w = from_bounds(*g.bounds, transform=db.transform).round_offsets().round_lengths()
                w = w.intersection(Window(0, 0, db.width, db.height))
                wt = db.window_transform(w)
                inside = features.rasterize([g], out_shape=(w.height, w.width), transform=wt,
                                            fill=0, default_value=1, dtype="uint8").astype(bool)
                mask = (db.read(1, window=w) == 1) & inside
                if not mask.any():
                    continue
                mask = clean(mask, pa) & inside
                cls = dc.read(1, window=w)
                n_soil += (mask & (cls == 2)).sum() * pa
                n_grey += (mask & (cls == 3)).sum() * pa
                area += mask.sum() * pa
                parts += [shape(s) for s, v in features.shapes(mask.astype(np.uint8), mask=mask, transform=wt) if v == 1]
                print(f"  {e['id']} {tag}: window {w.width}x{w.height}, {mask.sum() * pa:,.0f} m2", flush=True)
        poly = gpd.GeoSeries([unary_union(parts)], crs=4326).to_crs(32647).iloc[0].simplify(0.1)
        rows.append({"id": e["id"], "name": e["name"], "description": e["description"],
                     "area_m2": round(area, 1), "soil_m2": round(n_soil, 1), "grey_m2": round(n_grey, 1),
                     "geometry": poly})
        print(f"{e['id']}: {area:,.0f} m2 (vector {poly.area:,.0f} m2)", flush=True)
    out = gpd.GeoDataFrame(rows, crs=32647)
    out.to_file(INV / "landslides_utm.gpkg", driver="GPKG")
    out.to_crs(4326).to_file(INV / "landslides.geojson", driver="GeoJSON")
    gpd.GeoDataFrame({"flight": ["landslide"]}, geometry=[fp_ls], crs=4326).to_file(INV / "footprint_landslide_flight.geojson")
    gpd.GeoDataFrame({"flight": ["plan2"]}, geometry=[footprint("plan2")], crs=4326).to_file(INV / "footprint_plan2_flight.geojson")
    print("total mapped", round(out.area_m2.sum()), "m2")


if __name__ == "__main__":
    main()
