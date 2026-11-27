"""Tonight's Sky - a planisphere for the wall.

The whole sky over the house on one dome: bright stars sized by
magnitude with a gentle twinkle, the Milky Way as a soft wash,
the planets as colored dots with labels, and the moon drawn at
its true phase. By night the dome is live; by day it previews
tonight as it will look when astronomical twilight ends. The
right column carries the evening's facts: sunset, full dark,
moonrise and the phase, and which planets are up.

Everything comes from core/astro - computed on the Pi from the
wall's location (the Overhead Aircraft center point). No feed,
nothing to stall.
"""
import math
import time

from PIL import Image, ImageDraw, ImageFont

from ..core import astro
from ..core.geo import CANVAS_H, CANVAS_W
from .base import Module

CX, CY, R = 86, 97, 85
D2R = math.pi / 180.0

BG = (2, 3, 10)
RING = (58, 68, 100)
STAR = (216, 226, 255)
TITLE = (150, 175, 255)
LABEL = (120, 140, 170)
VALUE = (228, 234, 245)


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


def _project(alt, az):
    r = R * (90.0 - alt) / 90.0
    return (CX + r * math.sin(az * D2R), CY - r * math.cos(az * D2R))


class TonightModule(Module):
    name = "tonight"
    title = "Tonight's Sky"
    tick_s = 2

    def setup(self, config):
        super().setup(config)
        self.dot_count = 0
        try:
            self.lat = float(config.get("sw_lat", 35.1404))
            self.lon = float(config.get("sw_lon", -111.6694))
        except (TypeError, ValueError):
            self.lat, self.lon = 35.1404, -111.6694

    def _chart_time(self, now):
        """(epoch to draw, mode label). Live when the sun is down;
        otherwise tonight at the end of astronomical twilight."""
        alt, _ = astro.sun_altaz(now, self.lat, self.lon)
        if alt < -0.5:
            return now, "LIVE " + _hhmm(now)
        lt = time.localtime(now)
        ev = astro.sun_events(lt.tm_year, lt.tm_mon, lt.tm_mday,
                              self.lat, self.lon)
        for key in ("dusk_astro", "dusk_nautical", "dusk_civil"):
            if ev.get(key):
                return ev[key], "FROM " + _hhmm(ev[key])
        return now, "LIVE " + _hhmm(now)

    def draw(self, ctx):
        cfg = self.config
        now = time.time()
        chart_t, mode = self._chart_time(now)
        img = Image.new("RGB", (CANVAS_W, CANVAS_H), BG)
        d = ImageDraw.Draw(img, "RGBA")

        sun_alt, sun_az = astro.sun_altaz(chart_t, self.lat, self.lon)

        # twilight glow on the horizon toward the sun, while any
        # light is left in the sky at the chart time
        if -19 < sun_alt < 1:
            gx, gy = _project(-2, sun_az)
            glow = (255, 140, 60)
            strength = (sun_alt + 19) / 20.0
            for rad, a in ((46, 26), (30, 40), (17, 58)):
                d.ellipse((gx - rad, gy - rad * 0.6,
                           gx + rad, gy + rad * 0.6),
                          fill=glow + (int(a * strength),))

        # altitude rings and the horizon
        for frac in (1.0, 2.0 / 3, 1.0 / 3):
            r = R * frac
            box = (CX - r, CY - r, CX + r, CY + r)
            if frac == 1.0:
                d.ellipse(box, outline=RING + (255,), width=1)
            else:
                for start in range(0, 360, 14):
                    d.arc(box, start, start + 8, fill=RING + (200,))
        d.line((CX - 3, CY, CX + 3, CY), fill=RING + (255,))
        d.line((CX, CY - 3, CX, CY + 3), fill=RING + (255,))
        for txt, (tx, ty) in (("N", (CX - 3, 1)), ("S", (CX - 3, 181)),
                              ("E", (174, CY - 5)), ("W", (1, CY - 5))):
            d.text((tx, ty), txt, font=FONT_S, fill=LABEL + (255,))

        # the Milky Way: a soft wash along the galactic equator,
        # brighter toward the galactic center (the first samples).
        # Drawn on its own layer and blurred, so the samples melt
        # into a band instead of a chain of beads.
        if cfg.get("sky_mw", True):
            from PIL import ImageFilter
            wash = Image.new("RGBA", (CANVAS_W, CANVAS_H),
                             (0, 0, 0, 0))
            wd = ImageDraw.Draw(wash)
            pts = astro.milky_way(chart_t, self.lat, self.lon)
            for i, (alt, az) in enumerate(pts):
                if alt < -3:
                    continue
                x, y = _project(max(alt, 0.0), az)
                near_core = min(i, 72 - i) < 9  # l within ~40 of 0
                rad, a = (7, 64) if near_core else (6, 38)
                wd.ellipse((x - rad, y - rad, x + rad, y + rad),
                           fill=(110, 130, 180, a))
            wash = wash.filter(ImageFilter.GaussianBlur(2.5))
            img.paste(Image.alpha_composite(
                img.convert("RGBA"), wash).convert("RGB"))
            d = ImageDraw.Draw(img, "RGBA")

        labels = []  # (x0, y0, x1, y1) rects already spoken for

        def label(x, y, text, color):
            if not cfg.get("sky_labels", True):
                return
            w = d.textlength(text, font=FONT_S)
            lx = x + 4 if x < CX else x - 4 - w
            ly = y - 10 if y > CY - 40 else y + 4
            rect = (lx - 1, ly - 1, lx + w + 1, ly + 10)
            for r0 in labels:
                if not (rect[2] < r0[0] or rect[0] > r0[2]
                        or rect[3] < r0[1] or rect[1] > r0[3]):
                    return  # would collide; skip it
            labels.append(rect)
            d.rectangle(rect, fill=(2, 3, 10, 210))
            d.text((lx, ly), text, font=FONT_S, fill=color + (255,))

        # stars
        shown = 0
        for i, (name, ra, dec, mag) in enumerate(astro.STARS):
            alt, az = astro.altaz(ra, dec, chart_t, self.lat, self.lon)
            if alt < 0.5:
                continue
            shown += 1
            x, y = _project(alt, az)
            bright = 255 - (mag + 1.5) * 46
            if mag < 1.6:  # a gentle twinkle on the bright ones
                bright *= 0.85 + 0.15 * math.sin(ctx * 1.3 + i * 1.7)
            b = max(46, min(255, int(bright)))
            col = (b * STAR[0] // 255, b * STAR[1] // 255,
                   b * STAR[2] // 255)
            if mag < 0.2:
                d.line((x - 2, y, x + 2, y), fill=col)
                d.line((x, y - 2, x, y + 2), fill=col)
            elif mag < 1.3:
                d.rectangle((x - 1, y - 1, x, y), fill=col)
            else:
                d.point((x, y), fill=col)
            if name and mag <= 1.16:
                label(x, y, name.upper(), (170, 190, 235))
        self.dot_count = shown

        # planets
        up = []
        for name in astro.PLANET_NAMES:
            ra, dec, _ = astro.planet_radec(name, chart_t)
            alt, az = astro.altaz(ra, dec, chart_t, self.lat, self.lon)
            if alt < 0:
                continue
            up.append(name)
            x, y = _project(alt, az)
            col = astro.planet_color(name)
            d.ellipse((x - 2, y - 2, x + 2, y + 2), fill=col + (255,))
            d.point((x, y), fill=(255, 255, 255, 255))
            label(x, y, name.upper(), col)

        # the moon, at its true phase
        mra, mdec = astro.moon_radec(chart_t)
        malt, maz = astro.altaz(mra, mdec, chart_t, self.lat, self.lon)
        illum = astro.moon_illum(chart_t)
        if malt > 0:
            x, y = _project(malt, maz)
            sdx, sdy = astro.sun_screen_dir(sun_alt, sun_az, malt, maz)
            tile = astro.moon_disc(11, illum, sdx, sdy)
            img.paste(tile, (int(x - 5), int(y - 5)), tile)
            label(x, y, "MOON", (220, 220, 205))

        # the sun itself, if the chart time catches it up
        if sun_alt > -0.5:
            x, y = _project(max(sun_alt, 0.0), sun_az)
            d.ellipse((x - 3, y - 3, x + 3, y + 3),
                      fill=(255, 190, 70, 255))

        # ---- right column: the evening's facts
        lt = time.localtime(now)
        ev = astro.sun_events(lt.tm_year, lt.tm_mon, lt.tm_mday,
                              self.lat, self.lon)
        mev = astro.moon_events(lt.tm_year, lt.tm_mon, lt.tm_mday,
                                self.lat, self.lon)
        x0 = 182
        d.text((x0, 6), "TONIGHT", font=FONT_T, fill=TITLE + (255,))
        d.text((x0, 22), mode, font=FONT_S, fill=LABEL + (255,))
        rows = [("SET", _hhmm(ev["sunset"])),
                ("DARK", _hhmm(ev["dusk_astro"])),
                ("MOON", "%d%%" % round(illum * 100)),
                ("RISE", _hhmm(mev["moonrise"]))]
        y = 42
        for name, val in rows:
            d.text((x0, y), name, font=FONT_S, fill=LABEL + (255,))
            w = d.textlength(val, font=FONT_S)
            d.text((254 - w, y), val, font=FONT_S, fill=VALUE + (255,))
            y += 13
        y += 4
        d.text((x0, y), "UP:", font=FONT_S, fill=LABEL + (255,))
        y += 13
        for name in up:
            col = astro.planet_color(name)
            d.ellipse((x0 + 1, y + 3, x0 + 5, y + 7), fill=col + (255,))
            d.text((x0 + 9, y), name.upper(), font=FONT_S,
                   fill=VALUE + (255,))
            y += 13
        if not up:
            d.text((x0 + 9, y), "NONE", font=FONT_S, fill=LABEL + (255,))
        date = time.strftime("%a %b %d", lt).upper()
        w = d.textlength(date, font=FONT_S)
        d.text((254 - w, 178), date, font=FONT_S, fill=LABEL + (255,))
        return img
