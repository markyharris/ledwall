"""Region presets: a named view of the world on the canvas.

Each region carries its bounding box, the boundary dataset used to draw
its base map, and a density rule (minimum pixel separation between
station dots) tuned to how crowded that part of the world is.
"""

REGIONS = {
    "CONUS": {
        "title": "Continental US",
        "label": "CONUS",
        "bbox": (-125.5, 23.0, -66.0, 50.5),
        "boundaries": "us-states.json",
        "min_sep": 3,
    },
    # Phase 3 presets (boundary data lands with the world build):
    # "ALASKA":  {...}, "HAWAII": {...}, "EUROPE": {...},
    # "WORLD":   {...}, "JAPAN":  {...}, "AUSTRALIA": {...},
}


def get_region(name):
    r = dict(REGIONS[name])
    r["name"] = name
    return r
