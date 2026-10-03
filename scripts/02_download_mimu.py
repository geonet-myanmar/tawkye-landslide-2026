"""
Download MIMU GIS layers around Taw Kye village, Launglon Township (Tanintharyi Region) from the MIMU
GeoNode (geonode.themimu.info) via its GeoServer WFS endpoint.

Source: Myanmar Information Management Unit (MIMU). Boundaries are MIMU v9.4
(1:250,000); village points are the MIMU PCode village-location set.

Every layer comes back as GeoJSON in EPSG:4326. National layers that are large
are cut server-side to a bounding box around Launglon Township; the regional
(Tanintharyi) layers are small enough to take whole.
"""

import json
import os
import sys
import time
import urllib.parse
import urllib.request

WFS = "https://geonode.themimu.info/geoserver/wfs"
RAW = os.path.join(os.path.dirname(__file__), "..", "data", "raw")

# Box around Launglon Township and its neighbours (minx, miny, maxx, maxy, EPSG:4326).
BBOX = "97.85,13.45,98.45,14.15"

LAYERS = [
    # (output file,                   GeoServer layer,                                        bbox)
    ("adm3_townships.geojson",         "geonode:mmr_polbnda_adm3_250k_mimu_1",                  BBOX),
    ("adm4_vt_tanintharyi.geojson",    "geonode:mmr_tni_polbnda_adm4_unhcr_mimu_250k",          None),
    ("town_points.geojson",            "geonode:mmr_pplp1_mimu250k",                            BBOX),
    ("village_points_tni.geojson",     "geonode:mmr_tni_pplp2_250k_mimu",                       None),
    ("rivers_detail.geojson",          "geonode:myanmar_river_network",                         BBOX),
    ("roads.geojson",                  "geonode:mmr_rdsl_mimu_250k",                            BBOX),
    ("health_facilities.geojson",      "geonode:health_facilities_myanmar2020_v20241016",       BBOX),
    ("schools_lower.geojson",          "geonode:formal_sector_school_location_lowermyanmar_2019", BBOX),
    ("land_use.geojson",               "geonode:myanmar_land_use",                              BBOX),
]


def build_url(layer, bbox=None):
    params = {
        "service": "WFS",
        "version": "1.0.0",
        "request": "GetFeature",
        "typeName": layer,
        "outputFormat": "application/json",
        "srsName": "EPSG:4326",
    }
    if bbox:
        params["bbox"] = bbox + ",EPSG:4326"
    return WFS + "?" + urllib.parse.urlencode(params)


def fetch(url, dest, tries=3):
    for attempt in range(1, tries + 1):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "tawkye-landslide/1.0"})
            with urllib.request.urlopen(req, timeout=600) as r:
                data = r.read()
            # A GeoServer error comes back as XML with a 200 -- make sure this parses
            obj = json.loads(data)
            n = len(obj.get("features", []))
            with open(dest, "wb") as f:
                f.write(data)
            return n, len(data)
        except Exception as e:  # noqa: BLE001
            if attempt == tries:
                raise
            print(f"    retry {attempt} after error: {e}", flush=True)
            time.sleep(4)
    return 0, 0


def main():
    os.makedirs(RAW, exist_ok=True)
    failures = []
    for name, layer, bbox in LAYERS:
        dest = os.path.join(RAW, name)
        if os.path.exists(dest) and os.path.getsize(dest) > 0:
            print(f"[skip] {name} already present", flush=True)
            continue
        print(f"[get ] {name}  <- {layer}", flush=True)
        try:
            n, size = fetch(build_url(layer, bbox), dest)
            print(f"       {n:,} features, {size/1_048_576:.2f} MB", flush=True)
        except Exception as e:  # noqa: BLE001
            print(f"       FAILED: {e}", flush=True)
            failures.append((name, layer, str(e)))
    if failures:
        print("\nFAILURES:")
        for f in failures:
            print("  ", f)
        sys.exit(1)
    print("\nAll layers downloaded.")


if __name__ == "__main__":
    main()
