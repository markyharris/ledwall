"""Earthquake Map: the world's M4.5+ earthquakes on the map.

Data is the USGS earthquake feed (GeoJSON, no key): every M4.5+
event of the past day or past 7 days, chosen in the admin. Dots
are sized by magnitude and fade with age; M6+ events get a ring,
and the largest few are labelled. The bottom strip gives the
count, the largest event and the most recent one. The feed
refreshes every 15 minutes.
"""
import json
import time
import urllib.request

from PIL import Image, ImageDraw

from ledwall.core import render
from ledwall.core.geo import CANVAS_H, CANVAS_W, Projection
from ledwall.core.regions import get_region
from ledwall.modules.base import Module
from ledwall.modules.skywatch import _font

TITLE_C = (255, 190, 120)
STRIP_BG = (6, 4, 10)
LABEL = (140, 140, 150)
VALUE = (240, 240, 245)
FEED = ("https://earthquake.usgs.gov/earthquakes/feed/v1.0/"
        "summary/4.5_%s.geojson")


def _darken(img, factor=0.72):
    black = Image.new("RGB", img.size, (0, 0, 0))
    return Image.blend(img, black, 1 - factor)


def _age_color(age_h):
    """(rgb, alpha): fresh events burn orange, then cool and
    fade as they age."""
    if age_h < 6:
        return (255, 92, 40), 255
    if age_h < 24:
        return (255, 140, 30), 235
    if age_h < 72:
        return (240, 110, 40), 190
    return (210, 90, 50), 140


def _ago(t, now):
    mins = max(0, int((now - t) // 60))
    if mins < 60:
        return "%d MIN AGO" % mins
    if mins < 1440:
        return "%dH %02dM AGO" % (mins // 60, mins % 60)
    return "%dD %dH AGO" % (mins // 1440, (mins % 1440) // 60)


class QuakesModule(Module):
    name = "quakes"
    title = "Earthquake Map"
    tick_s = 10
    fetch_s = 900

    def setup(self, config):
        self.cfg = config
        self.proj = Projection(get_region("WORLD")["bbox"])
        self.events = []  # (epoch, mag, lat, lon, place)
        self.dot_count = 0

    def refresh_data(self):
        period = self.cfg.get("quake_period", "week")
        if period not in ("day", "week"):
            period = "week"
        try:
            req = urllib.request.Request(FEED % period, headers={
                "User-Agent": "ledwall (personal LED display)"})
            with urllib.request.urlopen(req, timeout=25) as resp:
                data = json.loads(resp.read().decode("utf-8",
                                                     "replace"))
            events = []
            for feat in data.get("features", []):
                props = feat.get("properties", {})
                coords = feat.get("geometry", {}).get(
                    "coordinates") or []
                if props.get("mag") is None or len(coords) < 2:
                    continue
                events.append((props["time"] / 1000.0,
                               float(props["mag"]),
                               float(coords[1]), float(coords[0]),
                               props.get("place") or ""))
            events.sort(reverse=True)
            self.events = events
        except Exception:
            pass  # keep the last good set

    def draw(self, ctx):
        cfg = self.cfg
        img = _darken(render.build_base(get_region("WORLD")))
        now = time.time()
        ov = Image.new("RGBA", (CANVAS_W, CANVAS_H), (0, 0, 0, 0))
        od = ImageDraw.Draw(ov)
        f_t = _font(11)
        f_s = _font(9)
        placed = []
        for t, mag, lat, lon, place in reversed(self.events):
            x, y = self.proj.xy(lon, lat)
            if not self.proj.inside(x, y, -4) or y > CANVAS_H - 30:
                continue
            r = max(1.6, (mag - 4.0) * 2.0)
            col, alpha = _age_color((now - t) / 3600.0)
            od.ellipse((x - r, y - r, x + r, y + r),
                       fill=col + (alpha,))
            if mag >= 6.0:
                od.ellipse((x - r - 3, y - r - 3, x + r + 3,
                            y + r + 3), outline=(255, 200, 120, 220))
            placed.append((mag, x, y, place))
        img = Image.alpha_composite(img.convert("RGBA"),
                                    ov).convert("RGB")
        d = ImageDraw.Draw(img, "RGBA")
        d.text((5, 4), "EARTHQUAKES", font=f_t, fill=TITLE_C)

        # labels for the three largest
        if cfg.get("quake_labels", True):
            for mag, x, y, place in sorted(placed, reverse=True)[:3]:
                lab = "M%.1f" % mag
                w = d.textlength(lab, font=f_s)
                lx = x + 7 if x < CANVAS_W - 48 else x - 7 - w
                lx = min(max(lx, 2), CANVAS_W - w - 2)
                ly = min(max(y - 5, 16), CANVAS_H - 44)
                d.text((lx, ly), lab, font=f_s,
                       fill=(255, 220, 170))
        self.dot_count = len(placed)

        period = self.cfg.get("quake_period", "week")
        span = "PAST 24H" if period == "day" else "PAST 7 DAYS"
        d.rectangle((0, CANVAS_H - 26, CANVAS_W, CANVAS_H),
                    fill=STRIP_BG + (238,))
        line1 = "%s  -  M4.5+  -  %d EVENTS" % (span,
                                               len(self.events))
        d.text((5, CANVAS_H - 24), line1, font=f_s, fill=VALUE)
        if self.events:
            big = max(self.events, key=lambda ev: ev[1])
            latest = self.events[0]
            right = "LATEST M%.1f %s" % (latest[1],
                                         _ago(latest[0], now))
            d.text((CANVAS_W - 5 - d.textlength(right, font=f_s),
                    CANVAS_H - 12), right, font=f_s, fill=LABEL)
            # the largest event's place gets whatever width the
            # latest block leaves, truncated to fit exactly
            avail = CANVAS_W - 10 \
                - d.textlength(right, font=f_s) - 8
            head = "LARGEST M%.1f " % big[1]
            place = big[4].upper()
            while place and d.textlength(head + place,
                                         font=f_s) > avail:
                place = place[:-1]
            place = place.rstrip(" ,")
            if len(place) < 12:
                # too little room to say anything useful - a
                # stub like "105 K" reads as a typo; drop it
                place = ""
            d.text((5, CANVAS_H - 12), head + place,
                   font=f_s, fill=VALUE)
        return img
