"""Earth Engine inputs for the Taw Kye landslide analysis, each at its own native grid.

- Copernicus GLO-30 DEM, 2024_1 release (30 m, pre-event surface, acquired 2011-2015)
- VIDA combined Google+Microsoft building footprints (pre-event; Google Open
  Buildings v3 has none here, so these are Microsoft ML footprints)
- OpenStreetMap buildings (Overpass)
- Sentinel-2 L2A pre-event NDVI, dry-season 2026 median (10 m) - flags bare
  ground that already existed before 26 Sep 2026 (clearings, roads, quarries)
- Sentinel-2 post-event scenes after 26 Sep 2026 (listed; cloud permitting)
"""
import json, os, urllib.parse, urllib.request
from pathlib import Path
import ee

# Earth Engine needs an explicit Cloud project: set EE_PROJECT before running.
ee.Initialize(project=os.environ["EE_PROJECT"])
OUT = Path(__file__).resolve().parents[1] / "data/ee"
# AOI: both drone footprints plus a ~1.5 km margin so the DEM covers the hill crest
AOI = ee.Geometry.Rectangle([98.135, 13.772, 98.180, 13.818])


def download(img, name, scale, crs="EPSG:32647"):
    url = img.getDownloadURL({"region": AOI, "scale": scale, "crs": crs, "format": "GEO_TIFF"})
    urllib.request.urlretrieve(url, OUT / name)
    print("wrote", name)


dem = ee.ImageCollection("COPERNICUS/DEM/GLO30_2024_1").filterBounds(AOI).select("DEM").mosaic()
download(dem.toFloat(), "cop30_dem_utm.tif", 30)

bld = ee.FeatureCollection("projects/sat-io/open-datasets/VIDA_COMBINED/MMR").filterBounds(AOI)
gj = bld.getInfo()
print("VIDA buildings:", len(gj["features"]))
(OUT / "vida_buildings.geojson").write_text(json.dumps(gj))

q = ('[out:json][timeout:120];(way["building"](13.772,98.135,13.818,98.180);'
     'relation["building"](13.772,98.135,13.818,98.180););out geom;')
req = urllib.request.Request("https://overpass-api.de/api/interpreter",
                             data=urllib.parse.urlencode({"data": q}).encode(),
                             headers={"User-Agent": "tawkye-landslide/1.0"})
osm = json.load(urllib.request.urlopen(req, timeout=180))
feats = [{"type": "Feature", "properties": {"osm_id": e["id"], **e.get("tags", {})},
          "geometry": {"type": "Polygon", "coordinates": [[[p["lon"], p["lat"]] for p in e["geometry"]]]}}
         for e in osm["elements"] if e["type"] == "way" and len(e.get("geometry", [])) >= 4]
print("OSM buildings:", len(feats))
(OUT / "osm_buildings.geojson").write_text(json.dumps({"type": "FeatureCollection", "features": feats}))

s2 = ee.ImageCollection("COPERNICUS/S2_SR_HARMONIZED").filterBounds(AOI)
pre = (s2.filterDate("2026-01-01", "2026-05-01").filter(ee.Filter.lt("CLOUDY_PIXEL_PERCENTAGE", 30)))
print("pre-event S2 scenes:", pre.size().getInfo())


def mask(i):
    scl = i.select("SCL")
    return i.updateMask(scl.neq(3).And(scl.neq(8)).And(scl.neq(9)).And(scl.neq(10)))


ndvi_pre = pre.map(mask).map(lambda i: i.normalizedDifference(["B8", "B4"])).median().rename("ndvi")
download(ndvi_pre.toFloat(), "s2_ndvi_pre_2026JanApr.tif", 10)
rgb_pre = pre.map(mask).select(["B4", "B3", "B2"]).median()
download(rgb_pre.toUint16(), "s2_rgb_pre_2026JanApr.tif", 10)

post = s2.filterDate("2026-09-27", "2026-10-04")
info = post.aggregate_array("system:index").getInfo(), post.aggregate_array("CLOUDY_PIXEL_PERCENTAGE").getInfo()
print("post-event S2:", list(zip(*info)))
