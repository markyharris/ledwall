"""ISS Tracker: the space station on a world map.

The station's orbit comes from its CelesTrak element set,
refreshed every six hours and propagated on the Pi by
core/orbit.py (no per-frame fetching; the map redraws from the
elements). The map is the weather map's WORLD base with the
night side shaded from the sun's computed position. The bottom
strip carries altitude, speed and position, and the next pass
over the house - rise time and peak elevation, or a live
elevation while a pass is in progress.
"""
import math
import time

from PIL import Image, ImageDraw

from ledwall.core import astro, orbit, render
from ledwall.core.geo import CANVAS_H, CANVAS_W, Projection
from ledwall.core.regions import get_region
from ledwall.modules.base import Module
from ledwall.modules.skywatch import _font

TITLE_C = (150, 225, 255)
TRACK_PAST = (70, 110, 150)
TRACK_NEXT = (120, 200, 255)
FOOTPRINT = (70, 140, 170)
HOME_C = (255, 190, 60)
STRIP_BG = (4, 6, 12)
LABEL = (130, 145, 165)
VALUE = (235, 240, 248)
PASS_OK = (120, 255, 170)

KM_MI = 0.621371


def _darken(img, factor=0.72):
    black = Image.new("RGB", img.size, (0, 0, 0))
    return Image.blend(img, black, 1 - factor)


class IssModule(Module):
    name = "iss"
    title = "ISS Tracker"
    tick_s = 5

    @property
    def fetch_s(self):
        # Element sets update a few times a day - but until the
        # first set lands the module has nothing to show, so poll
        # briskly rather than leaving a "waiting" sign up for
        # hours after one failed fetch (first-run find, Nov 27:
        # a stalled first fetch on a slow line stranded it).
        return 6 * 3600 if self.tle is not None else 45

    def setup(self, config):
        self.cfg = config
        self.lat = float(config.get("sw_lat", 35.1404))
        self.lon = float(config.get("sw_lon", -111.6694))
        self.proj = Projection(get_region("WORLD")["bbox"])
        self.tle = None
        self._pass = None
        self._pass_at = 0.0
        self._night = None
        self._night_at = 0.0
        self.dot_count = 0

    def refresh_data(self):
        try:
            self.tle = orbit.fetch_tle()
        except Exception:
            pass  # keep the last good elements

    def _night_overlay(self, now):
        """A translucent black wash over the night side, computed
        on a 4 px grid from the sun's position and cached for two
        minutes - the terminator moves slowly."""
        if self._night is not None and now - self._night_at < 120:
            return self._night
        ov = Image.new("RGBA", (CANVAS_W, CANVAS_H), (0, 0, 0, 0))
        od = ImageDraw.Draw(ov)
        proj = self.proj
        for gy in range(0, CANVAS_H, 4):
            for gx in range(0, CANVAS_W, 4):
                lon = proj.lon0 + (gx - proj.ox) / (proj.kx
                                                    * proj.scale)
                lat = proj.lat1 - (gy - proj.oy) / proj.scale
                if lat < -62 or lat > 86:
                    continue
                alt, _az = astro.sun_altaz(now, lat, lon)
                if alt < 0:
                    a = int(min(1.0, -alt / 12.0) * 88)
                    od.rectangle((gx, gy, gx + 3, gy + 3),
                                 fill=(0, 0, 5, a))
        self._night = ov
        self._night_at = now
        return ov

    def _next_pass(self, now):
        if self._pass is not None and now - self._pass_at < 300:
            return self._pass
        try:
            self._pass = orbit.next_pass(self.tle, self.lat,
                                         self.lon, now,
                                         horizon_h=24.0)
        except Exception:
            self._pass = None
        self._pass_at = now
        return self._pass

    def draw(self, ctx):
        cfg = self.cfg
        img = _darken(render.build_base(get_region("WORLD")))
        now = time.time()
        if cfg.get("iss_night", True):
            img = Image.alpha_composite(
                img.convert("RGBA"),
                self._night_overlay(now)).convert("RGB")
        d = ImageDraw.Draw(img, "RGBA")
        f_t = _font(11)
        f_s = _font(9)
        d.text((5, 4), "ISS TRACKER", font=f_t, fill=TITLE_C)

        if self.tle is None:
            d.text((5, 100), "WAITING FOR ELEMENTS",
                   font=f_s, fill=LABEL)
            self.dot_count = 0
            return img

        lat, lon, alt_km, spd = orbit.propagate(self.tle, now)
        proj = self.proj

        # ground track: the last and next 45 minutes
        if cfg.get("iss_track", True):
            for span, col in (((-2700, 0, 20), TRACK_PAST),
                              ((0, 2700, 20), TRACK_NEXT)):
                prev = None
                for dt in range(span[0], span[1] + 1, span[2]):
                    la, lo, _a, _s = orbit.propagate(
                        self.tle, now + dt)
                    x, y = proj.xy(lo, la)
                    if prev is not None \
                            and abs(x - prev[0]) < CANVAS_W / 2:
                        d.line((prev[0], prev[1], x, y), fill=col,
                               width=1)
                    prev = (x, y)

        # the visible-horizon footprint around the subpoint
        if cfg.get("iss_footprint", True):
            reach = math.degrees(math.acos(
                orbit.RE / (orbit.RE + alt_km)))
            prev = None
            for brg in range(0, 361, 6):
                b = math.radians(brg)
                la = math.degrees(math.asin(
                    math.sin(math.radians(lat))
                    * math.cos(math.radians(reach))
                    + math.cos(math.radians(lat))
                    * math.sin(math.radians(reach))
                    * math.cos(b)))
                lo = lon + math.degrees(math.atan2(
                    math.sin(b) * math.sin(math.radians(reach))
                    * math.cos(math.radians(lat)),
                    math.cos(math.radians(reach))
                    - math.sin(math.radians(lat))
                    * math.sin(math.radians(la))))
                x, y = proj.xy(lo, la)
                if prev is not None \
                        and abs(x - prev[0]) < CANVAS_W / 2:
                    d.line((prev[0], prev[1], x, y), fill=FOOTPRINT)
                prev = (x, y)

        # home
        hx, hy = proj.xy(self.lon, self.lat)
        d.ellipse((hx - 2, hy - 2, hx + 2, hy + 2), fill=HOME_C)

        # the station: a bright dot with a soft halo
        x, y = proj.xy(lon, lat)
        pulse = 5 + (ctx % 2)
        d.ellipse((x - pulse, y - pulse, x + pulse, y + pulse),
                  fill=(140, 210, 255, 70))
        d.ellipse((x - 2.5, y - 2.5, x + 2.5, y + 2.5),
                  fill=(255, 255, 255))
        self.dot_count = 1

        # bottom strip
        d.rectangle((0, CANVAS_H - 26, CANVAS_W, CANVAS_H),
                    fill=STRIP_BG + (235,))
        pos = "%.1f %s  %.1f %s" % (
            abs(lat), "N" if lat >= 0 else "S",
            abs(lon), "E" if lon >= 0 else "W")
        left = "ALT %d MI  %s MPH" % (
            round(alt_km * KM_MI), format(int(round(spd * KM_MI)),
                                          ","))
        d.text((5, CANVAS_H - 24), left, font=f_s, fill=VALUE)
        d.text((5, CANVAS_H - 12), pos, font=f_s, fill=LABEL)

        el, az, _r = orbit.look_angles(self.tle, now, self.lat,
                                       self.lon)
        if el > 0:
            r1 = "OVERHEAD NOW"
            r2 = "EL %d  AZ %d" % (round(el), round(az))
            col = PASS_OK
        else:
            p = self._next_pass(now)
            if p is None:
                r1, r2, col = "NO PASS", "IN 24H", LABEL
            else:
                r1 = "NEXT PASS %s" % time.strftime(
                    "%H:%M", time.localtime(p["start"]))
                r2 = "MAX EL %d" % round(p["max_el"])
                col = VALUE
        d.text((CANVAS_W - 5 - d.textlength(r1, font=f_s),
                CANVAS_H - 24), r1, font=f_s, fill=col)
        d.text((CANVAS_W - 5 - d.textlength(r2, font=f_s),
                CANVAS_H - 12), r2, font=f_s, fill=col)
        return img
