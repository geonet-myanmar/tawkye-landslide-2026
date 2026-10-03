"""Model rainfall at Taw Kye for context (Open-Meteo best-match model, NOT gauge data).

Shows the shape of the storm that preceded the landslides of the night of 26 Sep 2026.
Cached with the fetch time: forecast-hour values are later replaced by analysis values,
so a re-fetch will not return identical numbers.
"""
import datetime as dt, json, urllib.parse, urllib.request
from pathlib import Path

OUT = Path(__file__).resolve().parents[1] / "data/source/rainfall_openmeteo_tawkye.json"
LAT, LON = 13.7920, 98.1590  # Taw Kye, centre of the surveyed village


def get(params):
    url = "https://api.open-meteo.com/v1/forecast?" + urllib.parse.urlencode(params)
    with urllib.request.urlopen(url, timeout=60) as r:
        return json.loads(r.read())


def main():
    base = {"latitude": LAT, "longitude": LON, "timezone": "Asia/Yangon"}
    d = get({**base, "daily": "precipitation_sum", "start_date": "2026-09-01", "end_date": "2026-10-02"})
    h = get({**base, "hourly": "precipitation", "start_date": "2026-09-24", "end_date": "2026-09-29"})
    out = {"source": "Open-Meteo forecast API, best-match model (not gauge data)",
           "fetched_utc": dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%dT%H:%MZ"),
           "lat": LAT, "lon": LON, "grid_lat": d["latitude"], "grid_lon": d["longitude"],
           "daily": dict(zip(d["daily"]["time"], d["daily"]["precipitation_sum"])),
           "hourly": dict(zip(h["hourly"]["time"], h["hourly"]["precipitation"]))}
    OUT.write_text(json.dumps(out, indent=1))
    for k, v in out["daily"].items():
        if k >= "2026-09-20":
            print(k, v)
    print("Sep total", round(sum(v or 0 for k, v in out["daily"].items() if k < "2026-10-01"), 1))


if __name__ == "__main__":
    main()
