"""Live Radar: NEXRAD reflectivity over the Southwest.

Precipitation comes from the RainViewer mosaic (which republishes
the national NEXRAD composite as map tiles, no key). Every five
minutes the module pulls the last six mosaic frames for the
Southwest view, reprojects them from web-mercator onto the wall's
equirectangular view over the state outlines, and loops them -
weather moving across the map is the whole point. Range rings
around home and the region's cities keep the geography readable
under the echoes.
"""
import io
import json
import math
import time
import urllib.request

from PIL import Image, ImageDraw

from ledwall.core import render
from ledwall.core.geo import CANVAS_H, CANVAS_W, Projection
from ledwall.modules.base import Module
from ledwall.modules.skywatch import _font

BBOX = (-122.0, 27.0, -100.0, 45.0)  # the Southwest view
ZOOM = 5
TILE = 256
MAPS_URL = "https://api.rainviewer.com/public/weather-maps.json"
TILE_URL = "https://tilecache.rainviewer.com%s/256/%d/%d/%d/6/1_0.png"

TITLE_C = (126, 231, 135)
LAND = (10, 14, 22)
BORDER = (62, 78, 98)
CITY = (150, 160, 175)
HOME_C = (255, 190, 60)
RING = (90, 100, 115)
STRIP_BG = (4, 8, 6)
LABEL = (130, 145, 150)
VALUE = (235, 242, 238)

CITIES = [("PHOENIX", -112.07, 33.45), ("TUCSON", -110.97, 32.22),
          ("LAS VEGAS", -115.14, 36.17), ("ALBUQUERQUE", -106.65,
          35.08), ("DENVER", -104.99, 39.74),
          ("EL PASO", -106.49, 31.76),
          ("SALT LAKE", -111.89, 40.76)]


def _merc_x(lon, zoom=ZOOM):
    return (lon + 180.0) / 360.0 * (TILE << zoom)


def _merc_y(lat, zoom=ZOOM):
    phi = math.radians(lat)
    return (1 - math.log(math.tan(phi) + 1 / math.cos(phi))
            / math.pi) / 2 * (TILE << zoom)


def _fetch(url, timeout=25):
    req = urllib.request.Request(url, headers={
        "User-Agent": "ledwall (personal LED display)"})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return resp.read()


class RadarModule(Module):
    name = "radar"
    title = "Live Radar"
    tick_s = 1
    PERSIST = ("frames",)

    @property
    def fetch_s(self):
        return 300 if self.frames else 60

    def setup(self, config):
        self.cfg = config
        self.lat = float(config.get("sw_lat", 35.1404))
        self.lon = float(config.get("sw_lon", -111.6694))
        self.proj = Projection(BBOX)
        self.frames = []  # (epoch, RGBA image in canvas geometry)
        self.base = self._build_base()
        self.dot_count = 0

    def _build_base(self):
        img = Image.new("RGB", (CANVAS_W, CANVAS_H), LAND)
        d = ImageDraw.Draw(img)
        import os
        data_dir = os.path.join(os.path.dirname(
            os.path.dirname(os.path.abspath(__file__))), "data")
        for fname in ("us-states.json", "world-countries.json"):
            try:
                with open(os.path.join(data_dir, fname)) as f:
                    gj = json.load(f)
            except OSError:
                continue
            for feat in gj["features"]:
                for ring in render._rings(feat["geometry"]):
                    pts = [self.proj.xy(lon, lat)
                           for lon, lat in ring
                           if BBOX[0] - 6 <= lon <= BBOX[2] + 6
                           and BBOX[1] - 6 <= lat <= BBOX[3] + 6]
                    if len(pts) >= 3:
                        d.polygon(pts, outline=BORDER)
        return img

    def _frame_image(self, path):
        """Stitch one mosaic frame's tiles and reproject it onto
        the canvas (web-mercator rows onto equirectangular rows:
        only the vertical axis needs remapping)."""
        x0 = int(_merc_x(BBOX[0]) // TILE)
        x1 = int(_merc_x(BBOX[2]) // TILE)
        y0 = int(_merc_y(BBOX[3]) // TILE)
        y1 = int(_merc_y(BBOX[1]) // TILE)
        stitch = Image.new("RGBA",
                           ((x1 - x0 + 1) * TILE, (y1 - y0 + 1) * TILE))
        for tx in range(x0, x1 + 1):
            for ty in range(y0, y1 + 1):
                raw = _fetch(TILE_URL % (path, ZOOM, tx, ty))
                tile = Image.open(io.BytesIO(raw)).convert("RGBA")
                stitch.paste(tile, ((tx - x0) * TILE, (ty - y0) * TILE))
        cx0 = _merc_x(BBOX[0]) - x0 * TILE
        cx1 = _merc_x(BBOX[2]) - x0 * TILE
        cy0 = _merc_y(BBOX[3]) - y0 * TILE
        cy1 = _merc_y(BBOX[1]) - y0 * TILE
        crop = stitch.crop((int(cx0), int(cy0), int(cx1), int(cy1)))
        out = Image.new("RGBA", (CANVAS_W, CANVAS_H))
        span_y = cy1 - cy0
        for row in range(CANVAS_H):
            lat = BBOX[3] - (row + 0.5) / CANVAS_H * (BBOX[3]
                                                      - BBOX[1])
            sy = int((_merc_y(lat) - y0 * TILE - cy0) / span_y
                     * crop.height)
            sy = min(max(sy, 0), crop.height - 1)
            line = crop.crop((0, sy, crop.width, sy + 1))
            out.paste(line.resize((CANVAS_W, 1)), (0, row))
        return out

    def refresh_data(self):
        try:
            data = json.loads(_fetch(MAPS_URL).decode("utf-8",
                                                      "replace"))
            past = data["radar"]["past"][-6:]
        except Exception:
            return  # keep the last good frames
        frames = []
        for fr in past:
            try:
                frames.append((fr["time"],
                               self._frame_image(fr["path"])))
            except Exception:
                continue
        if frames:
            self.frames = frames

    def draw(self, ctx):
        cfg = self.cfg
        img = self.base.copy()
        d = ImageDraw.Draw(img, "RGBA")
        f_t = _font(11)
        f_s = _font(9)
        if self.frames:
            if cfg.get("radar_animate", True):
                idx = (ctx // 2) % len(self.frames)
            else:
                idx = len(self.frames) - 1
            epoch, frame = self.frames[idx]
            img = Image.alpha_composite(img.convert("RGBA"),
                                        frame).convert("RGB")
            d = ImageDraw.Draw(img, "RGBA")
        else:
            epoch = None

        # range rings around home: 50 / 100 / 150 miles
        hx, hy = self.proj.xy(self.lon, self.lat)
        if cfg.get("radar_rings", True):
            for miles in (50, 100, 150):
                reach = math.degrees(miles / 3959.0)
                pts = []
                for brg in range(0, 361, 6):
                    b = math.radians(brg)
                    la = math.degrees(math.asin(
                        math.sin(math.radians(self.lat))
                        * math.cos(math.radians(reach))
                        + math.cos(math.radians(self.lat))
                        * math.sin(math.radians(reach))
                        * math.cos(b)))
                    lo = self.lon + math.degrees(math.atan2(
                        math.sin(b) * math.sin(math.radians(reach))
                        * math.cos(math.radians(self.lat)),
                        math.cos(math.radians(reach))
                        - math.sin(math.radians(self.lat))
                        * math.sin(math.radians(la))))
                    pts.append(self.proj.xy(lo, la))
                d.line(pts, fill=RING + (150,), width=1)

        # cities (labels haloed so they read over echoes)
        for name, clon, clat in CITIES:
            x, y = self.proj.xy(clon, clat)
            d.ellipse((x - 1, y - 1, x + 1, y + 1), fill=CITY)
            for dx, dy in ((1, 0), (-1, 0), (0, 1), (0, -1)):
                d.text((x + 4 + dx, y - 4 + dy), name, font=f_s,
                       fill=(0, 0, 0))
            d.text((x + 4, y - 4), name, font=f_s, fill=CITY)
        d.ellipse((hx - 2, hy - 2, hx + 2, hy + 2), fill=HOME_C)
        d.ellipse((hx - 4, hy - 4, hx + 4, hy + 4),
                  outline=HOME_C)

        d.text((5, 4), "LIVE RADAR", font=f_t, fill=TITLE_C)
        d.rectangle((0, CANVAS_H - 16, CANVAS_W, CANVAS_H),
                    fill=STRIP_BG + (235,))
        if epoch:
            left = "RADAR FRAME %s" % time.strftime(
                "%H:%M", time.localtime(epoch))
        else:
            left = "WAITING FOR DATA"
        d.text((5, CANVAS_H - 12), left, font=f_s, fill=VALUE)
        # legend: light / moderate / heavy
        lx = CANVAS_W - 5
        for word, col in (("HVY", (240, 60, 50)),
                          ("MOD", (245, 200, 60)),
                          ("LIGHT", (70, 200, 90))):
            w = d.textlength(word, font=f_s)
            lx -= w
            d.text((lx, CANVAS_H - 12), word, font=f_s, fill=col)
            lx -= 12
            d.rectangle((lx + 3, CANVAS_H - 11, lx + 9,
                         CANVAS_H - 5), fill=col)
            lx -= 4
        self.dot_count = len(self.frames)
        return img
