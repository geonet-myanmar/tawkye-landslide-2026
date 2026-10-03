# Taw Kye landslides, 26 Sep 2026

Analysis of the landslides at **Taw Kye (တောကျဲ) village, Launglon Township, Tanintharyi Region, Myanmar**
from two drone orthomosaics flown after the event (compiled by GSM/TSBM, 2 Oct 2026), with MIMU, Copernicus DEM,
Sentinel-2, OSM/Microsoft building footprints and Open-Meteo rainfall as supporting data.

Open `index.html` (it needs `tiles/` and `assets/` beside it).

## Results (from `outputs/summary.json`)
- 9 landslides, 20.6 ha of ground failed or buried; 9.8 ha of debris on the flat valley floor.
- 239 pre-event building footprints inside the survey: 36 destroyed, 12 damaged but standing, 21 standing at the edge.
  Dawei Watch (1 Oct 2026) reported 42 houses destroyed and 5 deaths.
- Reach angles 17.6-20.7 deg for the hillslope flows, 13.4 deg for the channelised LS-04.
- Runout-reach screening calibrated on those angles: 101 still-standing buildings lie in zone A.

## Pipeline (`scripts/`, run in order)
| step | script | does |
|---|---|---|
| 01 | `01_mosaic_kmz.py` | KML super-overlay -> GeoTIFF at native 3.75 / 5.68 cm |
| 02 | `02_download_mimu.py` | MIMU GeoServer WFS layers -> `data/raw/` |
| 03 | `03_fetch_ee.py` (set `EE_PROJECT`) | Earth Engine: GLO-30 DEM, Sentinel-2 pre-event NDVI, VIDA + OSM footprints |
| 04 | `04_classify.py` | per-pixel vegetation / soil / grey / shadow + 1 m majority bare mask, native resolution |
| 05 | `05_inventory.py` | landslide outlines = bare mask inside `data/inventory/envelopes.geojson` |
| 06 | `06_terrain.py` | crown, toe, H, L, reach angle, slope zones, pre-event NDVI |
| 07 | `07_buildings.py` | footprint shift, per-footprint native-pixel fractions, status (+ `building_overrides.csv`) |
| 08 | `08_runout.py` | energy-line runout reach (zones A/B) and calibration check |
| 09 | `09_rainfall.py` | Open-Meteo model rainfall (cached) |
| 10 | `10_tiles.py` | 512 px WebP XYZ tiles down to 3.6 cm/px |
| 11 | `11_media.py` | before/after frames from the video, web copy of the photo |
| 12 | `12_build_page.py` | `outputs/` (GeoPackage, CSV, summary) and `index.html` from `src/template.html` |

Never hand-edit `index.html`; edit `src/template.html` and re-run step 12.

The two hand-made inputs are `data/inventory/envelopes.geojson` (one interpreter-drawn envelope per landslide; the
outline itself is the native-resolution mask inside it) and `data/inventory/building_overrides.csv` (10 statuses
changed after checking image chips by eye, each with its reason).

## Not in this repository
The source deliveries (`*.kmz`, `IMG_4514.MOV`, the oblique photo) and the regenerable rasters built from them
(`data/ortho/`, 1.5 GB; `data/class/`) are kept out of git. Steps 06-09 and 12 run from what is committed;
steps 01, 04, 05, 07, 10 and 11 need the original files.

Live page: https://geonet-myanmar.github.io/tawkye-landslide-2026/
