"""Region presets: a named view of the world on the canvas.

Each region carries its bounding box, the boundary dataset used to draw
its base map, and a density rule (minimum pixel separation between
station dots) tuned to how crowded that part of the world is.

US states are generated from the boundaries file itself: each state
becomes a zoomed region showing only its own outline (the "feature"
key filters the base-map draw). The national station fetch is shared;
the projection simply plots only what falls inside the state.

Phase 3 (the world build) adds WORLD and EUROPE presets plus a
generated region per country from Natural Earth boundaries. World
regions carry "stations": "world" - their station ids come from the
AWC METAR station list, selected by bounding box (see
scripts/build_world_data.py); country views clip to their outline
exactly like states.
"""
import json
import os

_DATA = os.path.join(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__))), "data")


def _geom_bbox(geometry):
    lon_min = lat_min = float("inf")
    lon_max = lat_max = float("-inf")
    stack = [geometry["coordinates"]]
    while stack:
        node = stack.pop()
        if isinstance(node[0], (int, float)):
            lon, lat = node
            lon_min = min(lon_min, lon)
            lon_max = max(lon_max, lon)
            lat_min = min(lat_min, lat)
            lat_max = max(lat_max, lat)
        else:
            stack.extend(node)
    return lon_min, lat_min, lon_max, lat_max


def _state_regions():
    try:
        with open(os.path.join(_DATA, "us-states.json")) as f:
            geojson = json.load(f)
    except Exception:
        return {}
    out = {}
    for feature in geojson["features"]:
        name = feature["properties"].get("name")
        if not name:
            continue
        key = name.upper().replace(" ", "_")
        lon0, lat0, lon1, lat1 = _geom_bbox(feature["geometry"])
        out[key] = {
            "title": name,
            "label": key.replace("_", " "),
            "bbox": (lon0 - 0.6, max(-85.0, lat0 - 0.45),
                     lon1 + 0.6, min(85.0, lat1 + 0.45)),
            "boundaries": "us-states.json",
            "feature": name,
            "min_sep": 2,
        }
    return out


def _country_regions(taken):
    try:
        with open(os.path.join(_DATA, "world-countries.json")) as f:
            geojson = json.load(f)
    except Exception:
        return {}
    out = {}
    for feature in geojson["features"]:
        name = feature["properties"].get("name")
        if not name:
            continue
        key = "".join(ch if ch.isalnum() else "_"
                      for ch in name.upper()).strip("_")
        while "__" in key:
            key = key.replace("__", "_")
        if key in taken or key in out:
            key += "_COUNTRY"  # e.g. Georgia the country vs the state
        lon0, lat0, lon1, lat1 = _geom_bbox(feature["geometry"])
        out[key] = {
            "title": name,
            "label": name,
            "bbox": (lon0 - 0.6, max(-85.0, lat0 - 0.45),
                     lon1 + 0.6, min(85.0, lat1 + 0.45)),
            "boundaries": "world-countries.json",
            "feature": name,
            "min_sep": 2,
            "stations": "world",
        }
    return out


REGIONS = {
    "CONUS": {
        "title": "Continental US",
        "label": "CONUS",
        "bbox": (-125.5, 23.0, -66.0, 50.5),
        "boundaries": "us-states.json",
        "min_sep": 3,
    },
    "WORLD": {
        "title": "Whole world",
        "label": "WORLD",
        "bbox": (-180.0, -60.0, 180.0, 85.0),
        "boundaries": "world-countries.json",
        "min_sep": 2,
        "stations": "world",
    },
    "EUROPE": {
        "title": "Europe",
        "label": "EUROPE",
        "bbox": (-12.0, 35.0, 33.0, 71.0),
        "boundaries": "world-countries.json",
        "min_sep": 2,
        "stations": "world",
    },
}
REGIONS.update(_state_regions())
REGIONS.update(_country_regions(set(REGIONS)))


def get_region(name):
    r = dict(REGIONS[name])
    r["name"] = name
    return r
