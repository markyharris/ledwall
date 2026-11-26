"""Frame rendering: cached base maps + weather compositing, all in PIL.

The static geography (landmass + boundaries) is rendered once per region
and cached as a PNG; a weather frame is then just a copy of the base with
station dots composited on top. The finished frame is pushed to the
panels as one image.
"""
import json
import os

from PIL import Image, ImageDraw

from .geo import Projection, CANVAS_W, CANVAS_H

DATA_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data")

LAND_FILL = (14, 18, 24)
BORDER = (64, 78, 94)
WATER = (0, 0, 0)

# Classic flight-category colours (unchanged from ledmap v1 / LiveSectional)
CATEGORY_COLORS = {
    "VFR": (0, 255, 0),
    "MVFR": (0, 0, 255),
    "IFR": (255, 0, 0),
    "LIFR": (255, 0, 255),
    "NONE": (90, 90, 90),
}
# When two stations land on the same pixels, the worse weather wins.
PRIORITY = {"LIFR": 0, "IFR": 1, "MVFR": 2, "VFR": 3, "NONE": 4}


def _rings(geometry):
    """Yield every polygon ring in a GeoJSON geometry as [(lon, lat), ...]."""
    gtype = geometry["type"]
    coords = geometry["coordinates"]
    if gtype == "Polygon":
        for ring in coords:
            yield ring
    elif gtype == "MultiPolygon":
        for poly in coords:
            for ring in poly:
                yield ring


def build_base(region):
    """Render (and cache) the base map for a region: filled landmass with
    boundary outlines, no weather."""
    cache = os.path.join(DATA_DIR, "cache_base_%s.png" % region["name"])
    if os.path.exists(cache):
        return Image.open(cache).convert("RGB")
    proj = Projection(region["bbox"])
    img = Image.new("RGB", (CANVAS_W, CANVAS_H), WATER)
    d = ImageDraw.Draw(img)
    with open(os.path.join(DATA_DIR, region["boundaries"])) as f:
        geojson = json.load(f)
    for feature in geojson["features"]:
        for ring in _rings(feature["geometry"]):
            pts = [proj.xy(lon, lat) for lon, lat in ring]
            if len(pts) >= 3:
                d.polygon(pts, fill=LAND_FILL, outline=BORDER)
    try:
        img.save(cache)
    except OSError:
        pass  # the cache is an optimisation; a read-only checkout must
        # never stop the map from drawing (bench find, Nov 2026: the Pi's
        # runtime user cannot write into the pi-owned clone)
    return img


def plot_weather(base, metars, region):
    """Composite flight-category station dots onto a base map image.
    Stations are density-thinned: worse weather is placed first and a
    station is skipped if it falls within min_sep pixels of one already
    placed."""
    proj = Projection(region["bbox"])
    img = base.copy()
    d = ImageDraw.Draw(img)
    min_sep = region.get("min_sep", 3)
    reports = list(metars.values())
    # Reports with no flight category from the API plot as NONE (grey).
    reports.sort(key=lambda r: PRIORITY[r.get("fltCat") or "NONE"])
    placed = []
    for rep in reports:
        x, y = proj.xy(rep["lon"], rep["lat"])
        xi, yi = int(round(x)), int(round(y))
        if not proj.inside(xi, yi):
            continue
        if any(abs(xi - px) < min_sep and abs(yi - py) < min_sep
               for px, py in placed):
            continue
        placed.append((xi, yi))
        cat = rep.get("fltCat") or "NONE"
        d.rectangle([xi - 1, yi - 1, xi, yi], fill=CATEGORY_COLORS[cat])
    return img, len(placed)
