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

# Admin icon palette: light background, so the browser tab shows a map
# instead of a black box (the wall palette is near-black on black).
ICON_BG = (233, 231, 224)
ICON_LAND = (148, 168, 196)
ICON_BORDER = (74, 92, 112)

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


def render_icon(region, width=96, height=72):
    """A light-background miniature of the region map for the admin
    page's favicon and header (Mark, Nov 2026: the dark thumbnail read
    as a plain black box in the browser tab)."""
    proj = Projection(region["bbox"], width=width, height=height)
    img = Image.new("RGB", (width, height), ICON_BG)
    d = ImageDraw.Draw(img)
    with open(os.path.join(DATA_DIR, region["boundaries"])) as f:
        geojson = json.load(f)
    for feature in geojson["features"]:
        for ring in _rings(feature["geometry"]):
            pts = [proj.xy(lon, lat) for lon, lat in ring]
            if len(pts) >= 3:
                d.polygon(pts, fill=ICON_LAND, outline=ICON_BORDER)
    return img


# --- Weather icons (phase 2) -------------------------------------------
# Tiny pixel glyphs overlaid on stations reporting significant weather,
# parsed from each METAR's wxString. One icon per station: the most
# significant phenomenon wins (thunder > hail > snow > rain > fog).
GLYPHS = {
    "TS": ["....#",
           "...#.",
           "..#..",
           ".####",
           "...#.",
           "..#..",
           ".#..."],
    "SN": ["#..#..#",
           ".#.#.#.",
           "..###..",
           ".#####.",
           "..###..",
           ".#.#.#.",
           "#..#..#"],
    "RA": ["#..#..#",
           "#..#..#",
           ".......",
           ".#..#..",
           "..#..#.",
           "...#..#"],
    "FG": ["#####..",
           "..#####",
           "#####..",
           "..#####"],
    "GR": [".#...#.",
           "..#.#..",
           "#..#..#",
           "..#.#..",
           ".#...#."],
}
ICON_COLORS = {
    "TS": (255, 220, 0),
    "SN": (190, 220, 255),
    "RA": (150, 190, 255),
    "FG": (235, 235, 235),
    "GR": (235, 235, 235),
}
# Icons get their own density thinning, separate from the dots: a 7px
# glyph on every reporting station merges into a solid smear in a rain
# shield and buries the category dots (first live render, Nov 2026).
# Most significant phenomenon wins the space.
ICON_PRIORITY = {"TS": 0, "GR": 1, "SN": 2, "RA": 3, "FG": 4}
ICON_MIN_SEP = 9


def wx_kind(wx):
    """Most significant icon kind in a METAR wxString, or None."""
    if not wx:
        return None
    codes = set()
    for group in wx.split():
        g = group
        while g[:1] in ("-", "+"):
            g = g[1:]
        if g.startswith("VC"):
            g = g[2:]
        for i in range(0, len(g) - 1, 2):
            codes.add(g[i:i + 2])
    if "TS" in codes:
        return "TS"
    if "GR" in codes or "GS" in codes:
        return "GR"
    if "SN" in codes or "PL" in codes or "SG" in codes:
        return "SN"
    if "RA" in codes or "DZ" in codes:
        return "RA"
    if "FG" in codes or "BR" in codes:
        return "FG"
    return None


def draw_icons(img, stations, phase=0):
    """Draw icon glyphs centred on each (x, y, kind). Thunderstorm
    bolts blink: shown on even phases, hidden on odd ones. Bolts are
    drawn last so they sit on top of any neighbouring icon."""
    d = ImageDraw.Draw(img)
    for x, y, kind in sorted(stations, key=lambda s: s[2] == "TS"):
        if kind == "TS" and phase % 2 == 1:
            continue
        glyph = GLYPHS[kind]
        color = ICON_COLORS[kind]
        ox, oy = x - len(glyph[0]) // 2, y - len(glyph) // 2
        for r, row in enumerate(glyph):
            for c, ch in enumerate(row):
                if ch == "#":
                    d.point((ox + c, oy + r), fill=color)
    return img


def plot_weather(base, metars, region):
    """Composite flight-category station dots onto a base map image.
    Stations are density-thinned: worse weather is placed first and a
    station is skipped if it falls within min_sep pixels of one already
    placed. Returns (image, dots placed, icon stations)."""
    proj = Projection(region["bbox"])
    img = base.copy()
    d = ImageDraw.Draw(img)
    min_sep = region.get("min_sep", 3)
    dot = region.get("dot", 2)  # station dot size in LEDs (2 = a 2x2 block)
    half = dot // 2
    reports = list(metars.values())
    # Reports with no flight category from the API plot as NONE (grey).
    reports.sort(key=lambda r: PRIORITY[r.get("fltCat") or "NONE"])
    placed = []
    icons = []
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
        d.rectangle([xi - half, yi - half, xi - half + dot - 1,
                     yi - half + dot - 1], fill=CATEGORY_COLORS[cat])
        kind = wx_kind(rep.get("wxString"))
        if kind:
            icons.append((xi, yi, kind))
    icons.sort(key=lambda s: ICON_PRIORITY[s[2]])
    kept = []
    for x, y, kind in icons:
        if any(abs(x - kx) < ICON_MIN_SEP and abs(y - ky) < ICON_MIN_SEP
               for kx, ky, _ in kept):
            continue
        kept.append((x, y, kind))
    return img, len(placed), kept
