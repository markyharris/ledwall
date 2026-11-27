"""Frame rendering: cached base maps + weather compositing, all in PIL.

The static geography (landmass + boundaries) is rendered once per region
and cached as a PNG; a weather frame is then just a copy of the base with
station dots composited on top. The finished frame is pushed to the
panels as one image.
"""
import json
import os
import time

from PIL import Image, ImageChops, ImageDraw, ImageFont

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
        if region.get("feature") and \
                feature["properties"].get("name") != region["feature"]:
            continue  # a state view draws only its own outline
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
        if region.get("feature") and \
                feature["properties"].get("name") != region["feature"]:
            continue
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


def draw_icons(img, stations, level=1.0, bolt_on=True, flash=None):
    """Draw icon glyphs centred on each (x, y, kind), with colours
    scaled by level for the fade animation (level may exceed 1: the
    peak of the fade runs hot, channels clamp at 255). Bolts are drawn
    last so they sit on top of any neighbouring icon, and are skipped
    entirely when bolt_on is False (blink mode's off phase).

    flash maps (x, y) -> stage for thunderstorm stations that have
    just appeared: stage 0 draws the bolt double-size in pure white,
    stage 1 single-size white - the entrance flash, before the bolt
    settles into its normal yellow fade."""
    d = ImageDraw.Draw(img)
    flash = flash or {}
    scaled = {k: tuple(min(255, int(c * level)) for c in rgb)
              for k, rgb in ICON_COLORS.items()}
    for x, y, kind in sorted(stations, key=lambda s: s[2] == "TS"):
        glyph = GLYPHS[kind]
        if kind == "TS" and (x, y) in flash:
            scale = 2 if flash[(x, y)] == 0 else 1
            ox = x - len(glyph[0]) * scale // 2
            oy = y - len(glyph) * scale // 2
            for r, row in enumerate(glyph):
                for c, ch in enumerate(row):
                    if ch == "#":
                        d.rectangle([ox + c * scale, oy + r * scale,
                                     ox + c * scale + scale - 1,
                                     oy + r * scale + scale - 1],
                                    fill=(255, 255, 255))
            continue
        if kind == "TS" and not bolt_on:
            continue
        color = scaled[kind]
        ox, oy = x - len(glyph[0]) // 2, y - len(glyph) // 2
        for r, row in enumerate(glyph):
            for c, ch in enumerate(row):
                if ch == "#":
                    d.point((ox + c, oy + r), fill=color)
    return img


_FONT = "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"
_FONT_BOLD = "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"
_LEGEND_LABELS = [
    ("TS", "Thunderstorm"),
    ("SN", "Snow"),
    ("RA", "Rain / drizzle"),
    ("FG", "Fog / mist"),
    ("GR", "Hail"),
]
_CAT_LABELS = [
    ("VFR", "VFR - visual"),
    ("MVFR", "MVFR - marginal"),
    ("IFR", "IFR - instrument"),
    ("LIFR", "LIFR - low instrument"),
    ("NONE", "No category reported"),
]


def _legend_font(path, size):
    try:
        return ImageFont.truetype(path, size)
    except Exception:
        return ImageFont.load_default()


def render_legend():
    """The admin page legend: flight-category colours + weather icons,
    drawn from the same glyphs and colours the wall uses, so the two
    can never drift apart."""
    img = Image.new("RGB", (500, 224), LAND_FILL)
    d = ImageDraw.Draw(img)
    head = _legend_font(_FONT_BOLD, 12)
    body = _legend_font(_FONT, 13)
    d.text((12, 8), "FLIGHT CATEGORY", font=head, fill=(150, 160, 170))
    d.text((262, 8), "WEATHER ICONS", font=head, fill=(150, 160, 170))
    for i, (cat, label) in enumerate(_CAT_LABELS):
        y = 34 + i * 38
        d.rectangle([14, y + 2, 28, y + 16], fill=CATEGORY_COLORS[cat])
        d.text((38, y + 2), label, font=body, fill=(220, 224, 230))
    for i, (kind, label) in enumerate(_LEGEND_LABELS):
        y = 34 + i * 38
        glyph = GLYPHS[kind]
        scale = 4
        ox, oy = 268, y + 16 - len(glyph) * scale // 2
        for r, row in enumerate(glyph):
            for c, ch in enumerate(row):
                if ch == "#":
                    d.rectangle([ox + c * scale, oy + r * scale,
                                 ox + c * scale + scale - 1,
                                 oy + r * scale + scale - 1],
                                fill=ICON_COLORS[kind])
        d.text((308, y + 2), label, font=body, fill=(220, 224, 230))
    return img


def draw_region_label(img, base, text, icon_stations=(), reserved=None):
    """Draw the region/state/country name into the emptiest space on
    the map (Mark's ask): candidate spots around the edges are scored
    by how much weather sits in them - pixels differing from the base
    map, plus a penalty per icon - and the quietest spot wins. The
    choice is remade at every data refresh, so the label moves if its
    spot fills with weather. `reserved` is an (x0, y0, x1, y1) box the
    label must not sit under (the Zulu clock's corner). Returns the
    (x, y) origin used."""
    font = _legend_font(_FONT_BOLD, 12)
    probe = ImageDraw.Draw(img)
    tw = probe.textlength(text, font=font)
    w, h = int(tw) + 10, 18
    W, H = img.size
    inset = 5
    candidates = [  # preference order breaks ties
        (inset, H - h - inset),            # bottom-left
        (W - w - inset, H - h - inset),    # bottom-right
        (inset, inset),                    # top-left
        (W - w - inset, inset),            # top-right
        ((W - w) // 2, H - h - inset),     # bottom-centre
        ((W - w) // 2, inset),             # top-centre
        (inset, (H - h) // 2),             # mid-left
        (W - w - inset, (H - h) // 2),     # mid-right
    ]
    diff = ImageChops.difference(img, base).convert("L")
    mask = diff.point(lambda v: 255 if v else 0)

    def score(x, y):
        box = mask.crop((x, y, x + w, y + h))
        s = sum(box.histogram()[1:])
        for ix, iy, _ in icon_stations:
            if x - 3 <= ix <= x + w + 3 and y - 3 <= iy <= y + h + 3:
                s += 60
        if reserved and not (x + w < reserved[0] or x > reserved[2]
                             or y + h < reserved[1] or y > reserved[3]):
            s += 100000  # never slide under the Zulu clock
        return s

    x, y = min(candidates, key=lambda p: score(*p))
    d = ImageDraw.Draw(img)
    d.text((x + 6, y + 4), text, font=font, fill=(0, 0, 0))
    d.text((x + 5, y + 3), text, font=font, fill=(128, 148, 172))
    return (x, y)


def zulu_clock_box(width):
    """The (x0, y0, x1, y1) box the Zulu clock occupies, top-right."""
    font = _legend_font(_FONT_BOLD, 13)
    probe = ImageDraw.Draw(Image.new("RGB", (8, 8)))
    w = int(probe.textlength("00:00Z", font=font)) + 4
    return (width - w - 5, 5, width - 5, 22)


def draw_home_flag(img, x, y, level=1.0):
    """Plant the home-airport flag at the station dot (x, y): a white
    pole rising from the dot and an amber pennant flying right, its
    colour scaled by level (the module pulses it gently). The dot
    itself stays visible - its colour is the weather at home."""
    d = ImageDraw.Draw(img)
    amber = tuple(int(c * level) for c in (255, 176, 0))
    for dy in range(1, 9):
        d.point((x, y - dy), fill=(240, 240, 240))
    for i, ln in enumerate((5, 4, 2)):
        for dx in range(1, 1 + ln):
            d.point((x + dx, y - 8 + i), fill=amber)
    return img


def draw_zulu_clock(img, now=None):
    """HH:MMZ in the top-right corner, redrawn every tick. `now` is a
    Unix timestamp (defaults to the current time) so tests can pin it."""
    font = _legend_font(_FONT_BOLD, 13)
    text = time.strftime("%H:%MZ", time.gmtime(now))
    d = ImageDraw.Draw(img)
    x = img.width - int(d.textlength(text, font=font)) - 7
    d.text((x + 1, 6), text, font=font, fill=(0, 0, 0))
    d.text((x, 5), text, font=font, fill=(205, 214, 224))
    return img


_FEATURE_POLYS = {}


def _feature_polys(region):
    """Outer rings of the region's own feature (a state), used to clip
    station plots to the outline on zoomed views - a state map shows
    its own airports, not the neighbours that share its bounding box.
    (The CONUS view has no single feature and stays unclipped.)"""
    name = region.get("feature")
    if not name:
        return None
    # Keyed by dataset as well as name: Georgia is both a US state and
    # a country, in different boundary files.
    cache_key = (region["boundaries"], name)
    if cache_key in _FEATURE_POLYS:
        return _FEATURE_POLYS[cache_key]
    polys = []
    try:
        with open(os.path.join(DATA_DIR, region["boundaries"])) as f:
            geojson = json.load(f)
        for feature in geojson["features"]:
            if feature["properties"].get("name") != name:
                continue
            g = feature["geometry"]
            if g["type"] == "Polygon":
                polys.append(g["coordinates"][0])
            elif g["type"] == "MultiPolygon":
                polys.extend(p[0] for p in g["coordinates"])
    except Exception:
        polys = []
    _FEATURE_POLYS[cache_key] = polys or None
    return _FEATURE_POLYS[cache_key]


def _inside_polys(lon, lat, polys):
    for ring in polys:
        ins = False
        j = len(ring) - 1
        for i in range(len(ring)):
            xi, yi = ring[i]
            xj, yj = ring[j]
            if ((yi > lat) != (yj > lat)) and \
                    (lon < (xj - xi) * (lat - yi) / (yj - yi) + xi):
                ins = not ins
            j = i
        if ins:
            return True
    return False


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
    polys = _feature_polys(region)
    placed = []
    icons = []
    for rep in reports:
        if rep.get("lat") is None or rep.get("lon") is None:
            continue  # no position: unplottable, and never fatal
        x, y = proj.xy(rep["lon"], rep["lat"])
        xi, yi = int(round(x)), int(round(y))
        if not proj.inside(xi, yi):
            continue
        # The outline test runs last on purpose: it ray-casts every
        # ring, and a complex outline (Alaska) made a switch into it
        # the slowest draw on the wall. The cheap canvas cull above
        # rejects nearly every foreign station first.
        if polys and not _inside_polys(rep["lon"], rep["lat"], polys):
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
