"""Aurora & Space Weather: the aurora forecast and the solar
wind, from NOAA's Space Weather Prediction Center (no key).

The map is the weather map's world base with the night side
shaded and the OVATION model's aurora probability plotted over
it - the glowing oval around the pole (and its southern twin).
The strip carries the planetary K index, the live solar wind
speed and Bz from the L1 monitors, and where the current Kp can
be seen from. Everything refreshes every 15 minutes.
"""
import json
import time
import urllib.request

from PIL import Image, ImageDraw

from ledwall.core import astro, render
from ledwall.core.geo import CANVAS_H, CANVAS_W, Projection
from ledwall.core.regions import get_region
from ledwall.modules.base import Module
from ledwall.modules.skywatch import _font

KP_URL = ("https://services.swpc.noaa.gov/products/"
          "noaa-planetary-k-index.json")
OVATION_URL = ("https://services.swpc.noaa.gov/json/"
               "ovation_aurora_latest.json")
MAG_URL = ("https://services.swpc.noaa.gov/json/rtsw/"
           "rtsw_mag_1m.json")
WIND_URL = ("https://services.swpc.noaa.gov/json/rtsw/"
            "rtsw_wind_1m.json")

TITLE_C = (209, 138, 255)
HOME_C = (255, 190, 60)
STRIP_BG = (8, 4, 14)
LABEL = (135, 140, 160)
VALUE = (238, 240, 248)


def _darken(img, factor=0.72):
    black = Image.new("RGB", img.size, (0, 0, 0))
    return Image.blend(img, black, 1 - factor)


def _fetch_json(url, timeout=25):
    req = urllib.request.Request(url, headers={
        "User-Agent": "ledwall (personal LED display)"})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read().decode("utf-8", "replace"))


def _kp_color(kp):
    if kp < 3:
        return (110, 230, 130)
    if kp < 5:
        return (245, 210, 90)
    if kp < 6:
        return (255, 160, 70)
    return (255, 90, 70)


def _oval_color(v):
    if v < 15:
        return (38, 110, 58)
    if v < 30:
        return (52, 190, 84)
    if v < 50:
        return (130, 240, 120)
    return (230, 255, 170)


class AuroraModule(Module):
    name = "aurora"
    title = "Aurora & Space Weather"
    tick_s = 10

    @property
    def fetch_s(self):
        return 900 if self.kp is not None else 60

    def setup(self, config):
        self.cfg = config
        self.lat = float(config.get("sw_lat", 35.1404))
        self.lon = float(config.get("sw_lon", -111.6694))
        self.proj = Projection(get_region("WORLD")["bbox"])
        self.kp = None
        self.oval = []       # (lon, lat, probability)
        self.wind = None     # km/s
        self.bz = None       # nT, GSM
        self._night = None
        self._night_at = 0.0
        self.dot_count = 0

    def refresh_data(self):
        try:
            rows = _fetch_json(KP_URL)
            last = rows[-1]
            self.kp = float(last["Kp"] if isinstance(last, dict)
                            else last[1])
        except Exception:
            pass
        try:
            data = _fetch_json(OVATION_URL)
            self.oval = [(c[0] - 360.0 if c[0] > 180 else c[0],
                          c[1], c[2])
                         for c in data["coordinates"] if c[2] >= 5]
        except Exception:
            pass
        try:
            rows = [r for r in _fetch_json(MAG_URL)
                    if r.get("bz_gsm") is not None]
            rows.sort(key=lambda r: r["time_tag"])
            self.bz = float(rows[-1]["bz_gsm"])
        except Exception:
            pass
        try:
            rows = [r for r in _fetch_json(WIND_URL)
                    if r.get("proton_speed") is not None]
            rows.sort(key=lambda r: r["time_tag"])
            self.wind = float(rows[-1]["proton_speed"])
        except Exception:
            pass

    def _night_overlay(self, now):
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

    def draw(self, ctx):
        cfg = self.cfg
        img = _darken(render.build_base(get_region("WORLD")))
        now = time.time()
        img = Image.alpha_composite(
            img.convert("RGBA"), self._night_overlay(now)
        ).convert("RGB")
        d = ImageDraw.Draw(img, "RGBA")
        f_t = _font(11)
        f_s = _font(9)
        d.text((5, 4), "AURORA & SPACE WEATHER", font=f_t,
               fill=TITLE_C)

        placed = 0
        if cfg.get("aurora_oval", True):
            ov = Image.new("RGBA", (CANVAS_W, CANVAS_H),
                           (0, 0, 0, 0))
            od = ImageDraw.Draw(ov)
            for lon, lat, v in self.oval:
                x, y = self.proj.xy(lon, lat)
                if not self.proj.inside(x, y, -2) \
                        or y > CANVAS_H - 30:
                    continue
                r = 1.5 if v < 30 else 2.2
                od.ellipse((x - r, y - r, x + r, y + r),
                           fill=_oval_color(v) + (205,))
                placed += 1
            img = Image.alpha_composite(img.convert("RGBA"),
                                        ov).convert("RGB")
            d = ImageDraw.Draw(img, "RGBA")
        hx, hy = self.proj.xy(self.lon, self.lat)
        d.ellipse((hx - 2, hy - 2, hx + 2, hy + 2), fill=HOME_C)
        self.dot_count = placed

        d.rectangle((0, CANVAS_H - 26, CANVAS_W, CANVAS_H),
                    fill=STRIP_BG + (238,))
        if self.kp is None:
            d.text((5, CANVAS_H - 24), "WAITING FOR SWPC DATA",
                   font=f_s, fill=LABEL)
            return img
        kp_txt = "KP %.1f" % self.kp
        d.text((5, CANVAS_H - 25), kp_txt, font=f_t,
               fill=_kp_color(self.kp))
        kx = 5 + d.textlength(kp_txt, font=f_t) + 8
        d.text((kx, CANVAS_H - 24), "NOAA SWPC", font=f_s,
               fill=LABEL)
        if self.kp >= 7:
            verdict = "MAY REACH N HORIZON HERE"
        elif self.kp >= 5:
            verdict = "VISIBLE: NORTHERN US"
        else:
            verdict = "VISIBLE: POLAR REGIONS"
        d.text((CANVAS_W - 5 - d.textlength(verdict, font=f_s),
                CANVAS_H - 24), verdict, font=f_s,
               fill=_kp_color(self.kp))
        if cfg.get("aurora_wind", True) \
                and self.wind is not None and self.bz is not None:
            line2 = "SOLAR WIND %d KM/S   BZ %+.1f NT" % (
                round(self.wind), self.bz)
            d.text((5, CANVAS_H - 12), line2, font=f_s, fill=VALUE)
        return img
