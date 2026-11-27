"""World Weather: the whole-earth METAR view, in the house style.

The info modules (ISS, Earthquakes, Aurora) all share a look -
the darkened whole-earth base, a plain title, dots for data and
a facts strip along the bottom. This module gives the METAR
data the same treatment: every reporting airport on Earth as a
flight-category dot in the classic LiveSectional colors, the
home airport ringed in amber, a category legend, and a strip
with the reporting count and tallies.

It is a companion to the METAR Weather Map, not a replacement:
same feed (aviationweather.gov, newest report per station,
2.5-hour age cutoff), same category colors - just drawn at
world scale in the info modules' theme. The full fetch is the
heavy one (some 7,700 stations in chunks), every 15 minutes.
"""
import json
import os
import time

from PIL import Image, ImageDraw

from ledwall.core import metar, render
from ledwall.core.geo import CANVAS_H, CANVAS_W, Projection
from ledwall.core.regions import get_region
from ledwall.modules.base import Module
from ledwall.modules.skywatch import _font

DATA_DIR = os.path.join(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__))), "data")
TITLE_C = (110, 190, 255)
STRIP_BG = (6, 4, 10)
LABEL = (140, 140, 150)
VALUE = (240, 240, 245)
HOME_C = (255, 176, 0)
CATS = ("VFR", "MVFR", "IFR", "LIFR")


def _darken(img, factor=0.72):
    black = Image.new("RGB", img.size, (0, 0, 0))
    return Image.blend(img, black, 1 - factor)


class MetarWorldModule(Module):
    name = "metar_world"
    title = "World Weather"
    tick_s = 5
    PERSIST = ("metars",)

    @property
    def fetch_s(self):
        # 15 minutes once data is flowing; retry briskly until
        # the first world fetch lands (see the ISS module).
        return 900 if self.metars else 60

    def setup(self, config):
        self.cfg = config
        self.region = get_region("WORLD")
        self.proj = Projection(self.region["bbox"])
        with open(os.path.join(DATA_DIR,
                               "world_stations.json")) as f:
            stations = json.load(f)
        self.station_ids = [s["id"] for s in stations]
        self.coords = {s["id"]: (s["lon"], s["lat"])
                       for s in stations}
        self.metars = {}
        self.dot_count = 0

    def refresh_data(self):
        try:
            reps = metar.fetch_metars(self.station_ids)
        except Exception:
            return  # keep the last good set
        # Some reports arrive without coordinates; the station
        # directory knows where they are (same patch as the map).
        for icao, rep in reps.items():
            if rep.get("lat") is None or rep.get("lon") is None:
                coords = self.coords.get(icao)
                if coords:
                    rep["lon"], rep["lat"] = coords
        if reps:
            self.metars = reps

    def _cells(self):
        """Declutter to a 2 px grid (the weather map's own world
        separation), worst weather winning each cell - at world
        scale thousands of stations share pixels, and the worse
        report is the one worth seeing."""
        cells = {}
        for icao, rep in self.metars.items():
            if rep.get("lat") is None or rep.get("lon") is None:
                continue
            x, y = self.proj.xy(rep["lon"], rep["lat"])
            if not self.proj.inside(x, y, -2) or y > CANVAS_H - 30:
                continue
            cat = rep.get("fltCat") or "NONE"
            key = (int(x // 2), int(y // 2))
            cur = cells.get(key)
            if cur is None or render.PRIORITY.get(
                    cat, 4) < render.PRIORITY.get(cur[2], 4):
                cells[key] = (x, y, cat)
        return cells

    def draw(self, ctx):
        img = _darken(render.build_base(self.region))
        d = ImageDraw.Draw(img, "RGBA")
        f_t = _font(11)
        f_s = _font(9)
        d.text((5, 4), "WORLD WEATHER", font=f_t, fill=TITLE_C)

        if not self.metars:
            msg = "WAITING FOR WEATHER DATA"
            d.text(((CANVAS_W - d.textlength(msg, font=f_t)) / 2,
                    88), msg, font=f_t, fill=VALUE)
            return img

        cells = self._cells()
        self.dot_count = len(cells)
        for x, y, cat in cells.values():
            col = render.CATEGORY_COLORS.get(cat,
                                             (90, 90, 90))
            # one station, one LED - anything fatter turns the
            # dense regions into a solid smear (Mark, Nov 27)
            d.point((int(x), int(y)), fill=col)

        if self.cfg.get("mw_home", True):
            home = (self.cfg.get("home_airport") or "") \
                .strip().upper()
            coords = self.coords.get(home)
            if coords:
                hx, hy = self.proj.xy(coords[0], coords[1])
                if self.proj.inside(hx, hy, -2):
                    r = 3 + (ctx % 3)
                    d.ellipse((hx - r, hy - r, hx + r, hy + r),
                              outline=HOME_C)
                    d.ellipse((hx - 1, hy - 1, hx + 1, hy + 1),
                              fill=HOME_C)

        if self.cfg.get("mw_legend", True):
            tally = {c: 0 for c in CATS}
            for rep in self.metars.values():
                if rep.get("fltCat") in tally:
                    tally[rep["fltCat"]] += 1
            lx, ly = CANVAS_W - 57, 4
            d.rectangle((lx - 4, ly - 1, CANVAS_W - 3, ly + 47),
                        fill=(4, 6, 12, 205))
            for i, cat in enumerate(CATS):
                cy = ly + 5 + i * 11
                d.rectangle((lx + 1, cy + 1, lx + 3, cy + 3),
                            fill=render.CATEGORY_COLORS[cat])
                d.text((lx + 9, cy - 2), cat, font=f_s,
                       fill=VALUE)

        tally = {c: 0 for c in CATS}
        storms = 0
        newest = 0
        for rep in self.metars.values():
            if rep.get("fltCat") in tally:
                tally[rep["fltCat"]] += 1
            if "TS" in (rep.get("wxString") or ""):
                storms += 1
            newest = max(newest, rep.get("obsTime") or 0)

        d.rectangle((0, CANVAS_H - 26, CANVAS_W, CANVAS_H),
                    fill=STRIP_BG + (238,))
        right = ""
        if newest:
            right = "NEWEST " + time.strftime(
                "%H%MZ", time.gmtime(newest))
            d.text((CANVAS_W - 5 - d.textlength(right, font=f_s),
                    CANVAS_H - 24), right, font=f_s, fill=LABEL)
        # the headline gets whatever width the NEWEST block
        # leaves; the thunderstorm suffix is all-or-nothing -
        # a stub like "16 WITH T" reads as a typo, not a fact
        avail = CANVAS_W - 10 \
            - (d.textlength(right, font=f_s) + 8 if right else 0)
        line1 = "%s REPORTING" % format(len(self.metars), ",")
        if storms:
            full = line1 + "  ·  %d TS" % storms
            if d.textlength(full, font=f_s) <= avail:
                line1 = full
        while line1 and d.textlength(line1, font=f_s) > avail:
            line1 = line1[:-1]
        d.text((5, CANVAS_H - 24), line1.rstrip(" ·"), font=f_s,
               fill=VALUE)
        line2 = "  ·  ".join(
            "%s %s" % (c, format(tally[c], ",")) for c in CATS)
        d.text((5, CANVAS_H - 12), line2, font=f_s, fill=LABEL)
        return img
