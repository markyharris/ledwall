#!/usr/bin/env python3
"""Build the phase-3 world data files in ../data/:

  world-countries.json  Natural Earth 110m country boundaries, slimmed
                        to a name property and 2-decimal coordinates
                        (plenty at 256x192, and a third the size).
  world_stations.json   The METAR stations aviationweather.gov itself
                        carries (its published station cache, filtered
                        to icaoId + METAR siteType): [{id, lat, lon}].

Sources are public data, downloaded fresh when this runs:
  https://raw.githubusercontent.com/nvkelso/natural-earth-vector/master/geojson/ne_110m_admin_0_countries.geojson
  https://aviationweather.gov/data/cache/stations.cache.json.gz

Run on a desktop, never on the Pi; commit the outputs.
"""
import gzip
import io
import json
import os
import urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
DATA = os.path.join(HERE, "..", "data")
NE_URL = ("https://raw.githubusercontent.com/nvkelso/natural-earth-"
          "vector/master/geojson/ne_110m_admin_0_countries.geojson")
AWC_URL = "https://aviationweather.gov/data/cache/stations.cache.json.gz"


def fetch(url, tries=4):
    # aviationweather.gov's CDN truncates urllib downloads (an
    # IncompleteRead a few hundred KB in, every time from some
    # networks) while curl gets the whole file - so prefer curl.
    import shutil
    import subprocess
    if shutil.which("curl"):
        out = subprocess.run(
            ["curl", "-sL", "--max-time", "120", url],
            capture_output=True)
        if out.returncode == 0 and out.stdout:
            return out.stdout
    last = None
    for _ in range(tries):
        try:
            req = urllib.request.Request(
                url, headers={"User-Agent": "ledwall-data-build"})
            with urllib.request.urlopen(req, timeout=120) as r:
                return r.read()
        except Exception as e:
            last = e
    raise last


def slim(geojson):
    def rnd(coords):
        if isinstance(coords[0], (int, float)):
            return [round(coords[0], 2), round(coords[1], 2)]
        return [rnd(c) for c in coords]

    out = []
    for f in geojson["features"]:
        name = f["properties"].get("NAME")
        if not name:
            continue
        out.append({"type": "Feature",
                    "properties": {"name": name},
                    "geometry": {"type": f["geometry"]["type"],
                                 "coordinates": rnd(
                                     f["geometry"]["coordinates"])}})
    return {"type": "FeatureCollection", "features": out}


def main():
    countries = slim(json.loads(fetch(NE_URL)))
    with open(os.path.join(DATA, "world-countries.json"), "w") as f:
        json.dump(countries, f, separators=(",", ":"))
    print("countries:", len(countries["features"]))

    raw = json.load(io.BytesIO(gzip.decompress(fetch(AWC_URL))))
    stations = [{"id": s["icaoId"], "lat": s["lat"], "lon": s["lon"]}
                for s in raw
                if s.get("icaoId") and "METAR" in (s.get("siteType") or [])]
    stations.sort(key=lambda s: s["id"])
    with open(os.path.join(DATA, "world_stations.json"), "w") as f:
        json.dump(stations, f, separators=(",", ":"))
    print("METAR stations:", len(stations))

    def in_bbox(lon, lat, bbox):
        return bbox[0] <= lon <= bbox[2] and bbox[1] <= lat <= bbox[3]

    for label, bbox in (("EUROPE", (-12, 35, 33, 71)),
                        ("WORLD", (-180, -60, 180, 85))):
        n = sum(1 for s in stations if in_bbox(s["lon"], s["lat"], bbox))
        print("%s candidates: %d" % (label, n))


if __name__ == "__main__":
    main()
