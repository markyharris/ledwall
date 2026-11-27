"""Sun and Moon - the day's two clocks on one screen.

Left: today's sun path as an arc - sunrise and sunset on the
horizon line, golden hour shaded amber, twilight ticks at the
ends, and a bright dot riding the arc for right now. Right: the
moon as a big disc at its true phase (the same renderer as
Tonight's Sky), with its name, illumination, age, and rise/set
times. The bottom strip carries the dark window - end of
astronomical twilight tonight to its return tomorrow - and the
next full moon.

Everything comes from core/astro - computed on the Pi from the
wall's location (the Overhead Aircraft center point).
"""
import math
import time

from PIL import Image, ImageDraw, ImageFont

from ..core import astro
from ..core.geo import CANVAS_H, CANVAS_W
from .base import Module

# sun-path plot geometry: x = local hour 4..22, y = altitude
# -12..84 (84 clears the summer-solstice noon sun at this
# latitude, ~78 deg, with headroom)
PX0, PX1 = 18, 148
PY_TOP, PY_BOT = 30, 116
ALT_TOP, ALT_BOT = 84.0, -12.0

BG = (4, 4, 8)
AXIS = (90, 90, 100)
GRID = (34, 34, 44)
PATH = (255, 190, 80)
PATH_DIM = (130, 95, 45)
GOLD = (255, 150, 40)
TWILIGHT = (110, 140, 200)
LABEL = (125, 135, 155)
VALUE = (230, 235, 242)
TITLE = (255, 214, 120)
MOON_TITLE = (235, 232, 214)


def _font(size):
    try:
        return ImageFont.truetype(
            "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
            size)
    except OSError:
        return ImageFont.load_default()


FONT_T = _font(11)
FONT_S = _font(9)


def _hhmm(epoch):
    if epoch is None:
        return "--:--"
    t = time.localtime(epoch)
    return "%02d:%02d" % (t.tm_hour, t.tm_min)


def _sx(epoch):
    lt = time.localtime(epoch)
    hour = lt.tm_hour + lt.tm_min / 60.0 + lt.tm_sec / 3600.0
    return PX0 + (hour - 4.0) / 18.0 * (PX1 - PX0)


def _sy(alt):
    return PY_BOT - (alt - ALT_BOT) / (ALT_TOP - ALT_BOT) \
        * (PY_BOT - PY_TOP)


class SunMoonModule(Module):
    name = "sunmoon"
    title = "Sun and Moon"
    tick_s = 5

    def setup(self, config):
        super().setup(config)
        self.dot_count = 2
        try:
            self.lat = float(config.get("sw_lat", 35.1404))
            self.lon = float(config.get("sw_lon", -111.6694))
        except (TypeError, ValueError):
            self.lat, self.lon = 35.1404, -111.6694

    def draw(self, ctx):
        cfg = self.config
        now = time.time()
        lt = time.localtime(now)
        ev = astro.sun_events(lt.tm_year, lt.tm_mon, lt.tm_mday,
                              self.lat, self.lon)
        mev = astro.moon_events(lt.tm_year, lt.tm_mon, lt.tm_mday,
                                self.lat, self.lon)
        img = Image.new("RGB", (CANVAS_W, CANVAS_H), BG)
        d = ImageDraw.Draw(img)

        d.text((6, 4), "SUN & MOON", font=FONT_T, fill=TITLE)
        date = time.strftime("%a %b %d", lt).upper()
        d.text((254 - d.textlength(date, font=FONT_S), 6), date,
               font=FONT_S, fill=LABEL)

        # ---- sun path
        day0 = astro._day_start_epoch(lt.tm_year, lt.tm_mon,
                                      lt.tm_mday)
        pts = []
        for k in range(0, 18 * 10 + 1):  # 4:00 to 22:00, 6-min steps
            t = day0 + 4 * 3600 + k * 360
            alt, _ = astro.sun_altaz(t, self.lat, self.lon)
            pts.append((t, alt, _sx(t), _sy(alt)))
        horizon_y = _sy(0.0)
        d.rectangle((PX0, horizon_y, PX1, PY_BOT), fill=(8, 8, 14))
        for hr in (6, 9, 12, 15, 18, 21):
            x = PX0 + (hr - 4) / 18.0 * (PX1 - PX0)
            d.line((x, PY_TOP, x, PY_BOT), fill=GRID)
            lab = "%02d" % hr
            d.text((x - d.textlength(lab, font=FONT_S) / 2, PY_TOP - 11),
                   lab, font=FONT_S, fill=LABEL)
        d.line((PX0, horizon_y, PX1, horizon_y), fill=AXIS)
        # the path itself: dim below the horizon, bright above,
        # golden while the sun is in the golden band (0..6.5 deg)
        for (t0, a0, x0, y0), (t1, a1, x1, y1) in zip(pts, pts[1:]):
            amid = (a0 + a1) / 2
            if amid < 0:
                col = PATH_DIM
            elif amid < 6.5 and cfg.get("sm_golden", True):
                col = GOLD
            else:
                col = PATH
            d.line((x0, y0, x1, y1), fill=col, width=2)
        # twilight ticks on the horizon: civil (-6) and astro (-18)
        if cfg.get("sm_twilight", True):
            for key in ("dawn_civil", "dusk_civil",
                        "dawn_astro", "dusk_astro"):
                if ev.get(key):
                    x = _sx(ev[key])
                    d.line((x, horizon_y - 4, x, horizon_y + 4),
                           fill=TWILIGHT, width=1)
        # sunrise / sunset markers and times
        for key in ("sunrise", "sunset"):
            if ev.get(key):
                x = _sx(ev[key])
                d.ellipse((x - 2, horizon_y - 2, x + 2, horizon_y + 2),
                          fill=PATH)
                lab = _hhmm(ev[key])
                lx = min(max(x - d.textlength(lab, font=FONT_S) / 2,
                             PX0), PX1 - d.textlength(lab, font=FONT_S))
                d.text((lx, horizon_y + 5), lab, font=FONT_S, fill=VALUE)
        # right now, riding the arc
        alt_now, _ = astro.sun_altaz(now, self.lat, self.lon)
        if 4 <= lt.tm_hour + lt.tm_min / 60.0 <= 22:
            x, y = _sx(now), _sy(alt_now)
            pulse = 3 + (1 if ctx % 2 else 0)
            d.ellipse((x - pulse, y - pulse, x + pulse, y + pulse),
                      fill=(255, 240, 200))
        dl = ev.get("day_length")
        day_txt = "DAY %dH %02dM" % (int(dl // 3600),
                                     int(dl % 3600 // 60)) if dl else ""
        d.text((PX0, 146), day_txt, font=FONT_S, fill=VALUE)
        noon_txt = "NOON " + _hhmm(ev["solar_noon"])
        d.text((PX0, 159), noon_txt, font=FONT_S, fill=LABEL)

        # ---- the moon
        mcx, mcy, mdia = 203, 64, 62
        illum = astro.moon_illum(now)
        age, _ = astro.moon_age(now)
        sun_alt, sun_az = astro.sun_altaz(now, self.lat, self.lon)
        mra, mdec = astro.moon_radec(now)
        malt, maz = astro.altaz(mra, mdec, now, self.lat, self.lon)
        sdx, sdy = astro.sun_screen_dir(sun_alt, sun_az, malt, maz)
        tile = astro.moon_disc(mdia, illum, sdx, sdy)
        img.paste(tile, (mcx - mdia // 2, mcy - mdia // 2), tile)
        name = astro.phase_name(now).upper()
        nfont = FONT_T if d.textlength(name, font=FONT_T) <= 100 \
            else FONT_S
        nx = min(max(mcx - d.textlength(name, font=nfont) / 2, 154),
                 254 - d.textlength(name, font=nfont))
        d.text((nx, 100), name, font=nfont, fill=MOON_TITLE)
        lines = [("ILLUM", "%d%%" % round(illum * 100)),
                 ("AGE", "%.1f D" % age),
                 ("RISE", _hhmm(mev["moonrise"])),
                 ("SET", _hhmm(mev["moonset"]))]
        y = 120
        for lab, val in lines:
            d.text((168, y), lab, font=FONT_S, fill=LABEL)
            d.text((238 - d.textlength(val, font=FONT_S), y), val,
                   font=FONT_S, fill=VALUE)
            y += 12

        # ---- bottom strip: the dark window and the next full moon
        d.line((6, 170, 250, 170), fill=GRID)
        nxt = time.localtime(now + 86400)
        ev2 = astro.sun_events(nxt.tm_year, nxt.tm_mon, nxt.tm_mday,
                               self.lat, self.lon)
        dark = "DARK %s - %s" % (_hhmm(ev["dusk_astro"]),
                                 _hhmm(ev2["dawn_astro"]))
        d.text((6, 176), dark, font=FONT_S, fill=TWILIGHT)
        full = astro.next_phase(now, 180)
        if full:
            ft = time.localtime(full)
            ftxt = "FULL " + time.strftime("%b %d", ft).upper()
            d.text((254 - d.textlength(ftxt, font=FONT_S), 176), ftxt,
                   font=FONT_S, fill=MOON_TITLE)
        return img
