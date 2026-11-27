"""Module 4: overhead aircraft (Skywatch).

A radar scope of the real sky over the wall, from the free
community ADS-B feed at adsb.lol - no antenna of your own and no
account: thousands of volunteers' receivers already cover the area,
and their aggregate is public. The feed is polled at the module's
own cadence (the loop honours fetch_s); between polls each aircraft
is dead-reckoned along its reported track and groundspeed, so the
dots glide instead of jumping every half minute.

Scope centred on the configured point (KFLG by default - the
precise home coordinates, if wanted, belong in the Pi's own
git-ignored config, not in this public repo). Dots are coloured by
altitude band; the nearest aircraft gets a detail line along the
bottom. The feed carries callsign, type, altitude, speed and
heading - not origin/destination; that remains FlightAware's
paid party trick.
"""
import json
import math
import time
import urllib.request

from PIL import Image, ImageDraw, ImageFont

from .base import Module

W, H = 256, 192
CX, CY, R = 128, 102, 80
FEED = "https://api.adsb.lol/v2/point/{lat}/{lon}/{nm}"

# altitude bands (ft MSL): local traffic, mid, cruise
BAND_COLORS = [(9000, (255, 176, 0)), (20000, (0, 220, 120)),
               (999999, (90, 170, 255))]


def _font(size):
    try:
        return ImageFont.truetype(
            "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
            size)
    except OSError:
        return ImageFont.load_default()


FONT_S = _font(9)
FONT_M = _font(11)


def _band_color(alt):
    if alt is None:
        return (150, 150, 150)
    for limit, color in BAND_COLORS:
        if alt < limit:
            return color
    return BAND_COLORS[-1][1]


def _bearing_dist(lat0, lon0, lat1, lon1):
    """(distance nm, bearing deg) from point 0 to point 1."""
    dx = (lon1 - lon0) * 60.0 * math.cos(math.radians(lat0))
    dy = (lat1 - lat0) * 60.0
    dist = math.hypot(dx, dy)
    bearing = (math.degrees(math.atan2(dx, dy)) + 360) % 360
    return dist, bearing


def _advance(lat, lon, track, gs, seconds):
    """Dead-reckon a position along track at gs knots."""
    dist = gs * seconds / 3600.0  # nm
    lat += dist * math.cos(math.radians(track)) / 60.0
    lon += dist * math.sin(math.radians(track)) / (
        60.0 * math.cos(math.radians(lat)))
    return lat, lon


class SkywatchModule(Module):
    name = "skywatch"
    title = "Overhead aircraft"
    tick_s = 0.5
    fetch_s = 30

    def setup(self, config):
        super().setup(config)
        self.aircraft = []
        self._fetched_at = 0.0
        self.dot_count = 0
        self._sync_fetch_s()

    def _sync_fetch_s(self):
        try:
            self.fetch_s = int(self.config.get("sw_refresh_s", 30))
        except (TypeError, ValueError):
            self.fetch_s = 30

    def _center(self):
        try:
            return (float(self.config.get("sw_lat", 35.1404)),
                    float(self.config.get("sw_lon", -111.6694)))
        except (TypeError, ValueError):
            return 35.1404, -111.6694

    # -- data ------------------------------------------------------
    def refresh_data(self):
        lat0, lon0 = self._center()
        nm = int(self.config.get("sw_range_nm", 50))
        url = FEED.format(lat=lat0, lon=lon0, nm=nm)
        try:
            req = urllib.request.Request(
                url, headers={"User-Agent": "ledwall-skywatch"})
            with urllib.request.urlopen(req, timeout=20) as resp:
                data = json.loads(resp.read().decode("utf-8"))
        except Exception:
            return  # keep the last good picture; never raise
        out = []
        for a in data.get("ac", []):
            if a.get("lat") is None or a.get("lon") is None:
                continue
            alt = a.get("alt_baro")
            if not isinstance(alt, (int, float)):
                alt = None  # "ground" or missing
            dist, brg = _bearing_dist(lat0, lon0, a["lat"], a["lon"])
            out.append({
                "hex": a.get("hex", ""), "lat": a["lat"],
                "lon": a["lon"],
                "call": (a.get("flight") or "").strip(),
                "type": a.get("t") or "",
                "alt": alt, "gs": a.get("gs"),
                "track": a.get("track"), "dist": dist, "brg": brg,
            })
        out.sort(key=lambda a: a["dist"])
        self.aircraft = out
        self._fetched_at = time.time()
        self.dot_count = len(out)

    # -- drawing ---------------------------------------------------
    def draw(self, ctx):
        self._sync_fetch_s()
        lat0, lon0 = self._center()
        nm = int(self.config.get("sw_range_nm", 50))
        label = (self.config.get("sw_label") or "KFLG")[:6].upper()
        now = time.time()
        age = now - self._fetched_at if self._fetched_at else None
        img = Image.new("RGB", (W, H), (2, 6, 12))
        d = ImageDraw.Draw(img)
        # scope: rings at thirds, cross hairs, range figures
        for frac in (1 / 3, 2 / 3, 1.0):
            r = R * frac
            d.ellipse([CX - r, CY - r, CX + r, CY + r],
                      outline=(24, 48, 66))
            d.text((CX + 2, CY - r - 4), "%d" % round(nm * frac),
                   font=FONT_S, fill=(70, 100, 120))
        d.line([(CX - R, CY), (CX + R, CY)], fill=(18, 36, 50))
        d.line([(CX, CY - R), (CX, CY + R)], fill=(18, 36, 50))
        d.text((CX - 4, CY - R - 13), "N", font=FONT_S,
               fill=(70, 100, 120))
        # centre marker + label
        d.rectangle([CX - 2, CY - 2, CX + 2, CY + 2],
                    fill=(240, 240, 240))
        d.text((CX + 5, CY + 3), label, font=FONT_S,
               fill=(200, 210, 220))
        # header
        if age is None:
            head = "OVERHEAD - WAITING FOR FEED"
        else:
            head = "OVERHEAD - %d IN %d NM" % (len(self.aircraft),
                                               nm)
        d.text((6, 4), head, font=FONT_M, fill=(205, 214, 224))
        if age is not None and age > 180:
            d.text((W - 62, 4), "STALE", font=FONT_M,
                   fill=(255, 176, 0))
        # aircraft, farthest first so the nearest paint on top
        shown = []
        for a in reversed(self.aircraft):
            lat, lon = a["lat"], a["lon"]
            if a["gs"] and a["track"] is not None and age is not None:
                lat, lon = _advance(lat, lon, a["track"], a["gs"],
                                    min(age, 90))
            dist, _ = _bearing_dist(lat0, lon0, lat, lon)
            if dist > nm:
                continue
            x = CX + (lon - lon0) * 60.0 * math.cos(
                math.radians(lat0)) / nm * R
            y = CY - (lat - lat0) * 60.0 / nm * R
            shown.append((a, dist, x, y))
        shown.reverse()
        for i, (a, dist, x, y) in enumerate(shown):
            color = _band_color(a["alt"])
            if a["track"] is not None and a["gs"]:
                ln = max(5, min(14, a["gs"] / 40.0))
                rad = math.radians(a["track"])
                d.line([(x, y), (x + ln * math.sin(rad),
                                 y - ln * math.cos(rad))], fill=color)
            s = 3 if i == 0 else 2
            d.ellipse([x - s, y - s, x + s, y + s], fill=color)
            if i < 3 and a["call"]:
                d.text((x + 6, y - 5), a["call"], font=FONT_S,
                       fill=color)
        # footer: the nearest aircraft in detail, or the quiet sky;
        # shrink the font, then shed words, until the line fits
        if shown:
            a, dist, _, _ = shown[0]
            alt = ("%s FT" % format(int(a["alt"]), ",")
                   if a["alt"] is not None else "GND")
            gs = (" %d KT" % a["gs"]) if a["gs"] else ""
            who = a["call"] or a["hex"].upper()
            variants = ["%s %s - %s%s - %.0f NM" % (
                            who, a["type"], alt, gs, dist),
                        "%s - %s%s - %.0f NM" % (who, alt, gs, dist),
                        "%s - %s - %.0f NM" % (who, alt, dist)]
        elif age is not None:
            variants = ["NO AIRCRAFT WITHIN %d NM" % nm]
        else:
            variants = []
        for line in variants:
            for font in (FONT_M, FONT_S):
                if d.textlength(line, font=font) <= W - 6:
                    d.text(((W - d.textlength(line, font=font)) / 2,
                            H - 14), line, font=font,
                           fill=(205, 214, 224))
                    return img
        return img

    def admin_fields(self):
        return [
            {"key": "sw_range_nm", "label": "Scope range (nm)",
             "type": "select", "options": ["25", "50", "100"]},
            {"key": "sw_refresh_s", "label": "Feed refresh (s)",
             "type": "select", "options": ["15", "30", "60"]},
            {"key": "sw_label", "label": "Centre label",
             "type": "text"},
        ]
