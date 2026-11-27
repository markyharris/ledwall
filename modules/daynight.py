"""Day & Night: the whole earth split by the sun.

The classic terminator map, in the info modules' house style:
the darkened whole-earth base, the night side shaded deeper,
and the terminator itself - the sunrise-and-sunset line -
drawn bright across the map, with a marker where the sun is
directly overhead. It is all computed on the Pi from the sun's
position (core/astro.py); there is no feed to fetch. The
geometry is rebuilt every two minutes, which is faster than
the line can cross a single pixel.

The cliché, done properly: the line is found column by column
from the sun's actual altitude, so it bends with the seasons
and stops at the polar caps exactly where the sun stops
rising and setting.
"""
import time

from PIL import Image, ImageDraw, ImageFilter

from ledwall.core import astro, render
from ledwall.core.geo import CANVAS_H, CANVAS_W, Projection
from ledwall.core.regions import get_region
from ledwall.modules.base import Module
from ledwall.modules.skywatch import _font

TITLE_C = (255, 207, 92)
STRIP_BG = (6, 4, 10)
LABEL = (140, 140, 150)
VALUE = (240, 240, 245)
TERM_C = (255, 235, 180)
SUN_C = (255, 210, 60)


class DayNightModule(Module):
    name = "daynight"
    title = "Day & Night"
    tick_s = 10
    # no fetch_s: nothing to fetch, the sun does the work

    def setup(self, config):
        self.cfg = config
        self.region = get_region("WORLD")
        self.proj = Projection(self.region["bbox"])
        self.dot_count = 0
        self._geom_at = 0.0
        self._term = []       # [(x, y) or None per column]
        self._sub = (0.0, 0.0)
        self._shade = None    # day-weight mask for the composite

    # -- geometry, rebuilt on a two-minute cache ----------------

    def _geometry(self, now):
        if self._shade is not None and now - self._geom_at < 120:
            return
        ra, dec = astro.sun_radec(now)
        self._sub = astro.subsolar(now)

        # terminator: per pixel column, the latitude where the
        # sun's altitude crosses zero (scan, then bisect)
        pts = []
        for gx in range(CANVAS_W):
            lon = self.proj.lon0 + (gx - self.proj.ox) / (
                self.proj.kx * self.proj.scale)
            prev_lat, prev_alt = 84.0, astro.altaz(
                ra, dec, now, 84.0, lon)[0]
            found = None
            lat = 82.0
            while lat >= -60.0:
                alt = astro.altaz(ra, dec, now, lat, lon)[0]
                if (prev_alt < 0) != (alt < 0):
                    lo, hi = lat, prev_lat
                    for _ in range(5):
                        mid = (lo + hi) / 2
                        malt = astro.altaz(
                            ra, dec, now, mid, lon)[0]
                        if (malt < 0) == (prev_alt < 0):
                            hi = mid
                        else:
                            lo = mid
                    found = (lo + hi) / 2
                    break
                prev_lat, prev_alt = lat, alt
                lat -= 2.0
            if found is None:
                pts.append(None)
            else:
                _x, y = self.proj.xy(lon, found)
                pts.append((gx, y))
        self._term = pts

        # day-weight mask on a 4 px grid: 255 where the sun is
        # up, 0 where it is down, ramping through twilight; a
        # blur smooths the steps. The base map is intrinsically
        # dark, so merely washing the night side (the ISS
        # recipe) barely reads here - the draw composites a
        # brightened day version against a deepened night
        # version through this mask instead.
        mask = Image.new("L", (CANVAS_W, CANVAS_H), 0)
        md = ImageDraw.Draw(mask)
        for gy in range(0, CANVAS_H, 4):
            for gx in range(0, CANVAS_W, 4):
                lon = self.proj.lon0 + (gx - self.proj.ox) / (
                    self.proj.kx * self.proj.scale)
                lat = self.proj.lat1 - (gy - self.proj.oy) / \
                    self.proj.scale
                if lat < -62 or lat > 86:
                    continue
                alt = astro.altaz(ra, dec, now, lat, lon)[0]
                t = min(1.0, max(0.0, (alt + 6.0) / 12.0))
                if t > 0:
                    md.rectangle((gx, gy, gx + 3, gy + 3),
                                 fill=int(t * 255))
        self._shade = mask.filter(ImageFilter.GaussianBlur(3))
        self._geom_at = now

    # -- frame ---------------------------------------------------

    def draw(self, ctx):
        now = time.time()
        self._geometry(now)
        base = render.build_base(self.region)
        if self.cfg.get("dn_shade", True):
            day = base.point(lambda v: min(255, int(v * 1.75)))
            black = Image.new("RGB", base.size, (0, 0, 0))
            night = Image.blend(base, black, 0.5)
            img = Image.composite(day, night, self._shade)
        else:
            img = base.copy()
        d = ImageDraw.Draw(img, "RGBA")
        f_t = _font(11)
        f_s = _font(9)
        d.text((5, 4), "DAY & NIGHT", font=f_t, fill=TITLE_C)

        # the terminator line, segment by segment where the
        # curve is continuous (it ends at the polar caps)
        drawn = 0
        prev = None
        for pt in self._term:
            if pt is not None and prev is not None and \
                    abs(pt[1] - prev[1]) < 40:
                d.line((prev[0], prev[1], pt[0], pt[1]),
                       fill=TERM_C, width=1)
                drawn += 1
            prev = pt
        self.dot_count = drawn

        if self.cfg.get("dn_sun", True):
            lat, lon = self._sub
            sx, sy = self.proj.xy(lon, lat)
            if self.proj.inside(sx, sy, -2):
                d.ellipse((sx - 5, sy - 5, sx + 5, sy + 5),
                          outline=SUN_C + (200,))
                d.ellipse((sx - 3, sy - 3, sx + 3, sy + 3),
                          fill=SUN_C)
                d.ellipse((sx - 1, sy - 1, sx + 1, sy + 1),
                          fill=(255, 250, 230))

        d.rectangle((0, CANVAS_H - 26, CANVAS_W, CANVAS_H),
                    fill=STRIP_BG + (238,))
        lat, lon = self._sub
        line1 = "SUN OVERHEAD %.1f°%s · %.1f°%s" % (
            abs(lat), "N" if lat >= 0 else "S",
            abs(lon), "E" if lon >= 0 else "W")
        d.text((5, CANVAS_H - 24), line1, font=f_s, fill=VALUE)
        right = time.strftime("%H%MZ", time.gmtime(now))
        d.text((CANVAS_W - 5 - d.textlength(right, font=f_s),
                CANVAS_H - 24), right, font=f_s, fill=LABEL)
        d.text((5, CANVAS_H - 12), "SUNRISE AND SUNSET LINE",
               font=f_s, fill=LABEL)
        return img
