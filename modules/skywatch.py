"""Module 4: overhead aircraft (Skywatch).

A radar scope of the real sky over the wall, from the free
community ADS-B feed at adsb.lol - no antenna of your own and no
account: thousands of volunteers' receivers already cover the area,
and their aggregate is public. The feed is polled at the module's
own cadence (the loop honours fetch_s); between polls each aircraft
is dead-reckoned along its reported track and groundspeed, so the
dots glide instead of jumping every half minute.

The scope sits on the left two-thirds; the right third is an info
box for the aircraft nearest the centre point (KFLG by default -
precise home coordinates, if wanted, belong in the Pi's own
git-ignored config, not in this public repo). The box shows what
the free data actually carries: full aircraft type, operator (the
airline, or the registered owner for GA), the tail number, and -
via the free adsbdb.com callsign lookup - the departure and
destination airports for scheduled flights. Dots are coloured by
altitude band, six steps from warm (low) to violet (high).
"""
import json
import math
import time
import urllib.request

from PIL import Image, ImageDraw, ImageFont

from .base import Module

W, H = 256, 192
CX, CY, R = 80, 104, 74
BOX_X = 162
FEED = "https://api.adsb.lol/v2/point/{lat}/{lon}/{nm}"
ROUTE = "https://api.adsbdb.com/v0/callsign/{call}"
ACINFO = "https://api.adsbdb.com/v0/aircraft/{hex}"

# altitude bands (ft MSL), warm low -> violet high
BANDS = [(8000, (255, 110, 40)), (14000, (255, 190, 0)),
         (20000, (0, 220, 120)), (28000, (0, 210, 200)),
         (36000, (80, 160, 255)), (999999, (190, 120, 255))]

TYPE_NAMES = {
    "B39M": "Boeing 737 MAX 9", "B38M": "Boeing 737 MAX 8",
    "B738": "Boeing 737-800", "B739": "Boeing 737-900",
    "B737": "Boeing 737-700", "B735": "Boeing 737-500",
    "A35K": "Airbus A350-1000", "A359": "Airbus A350-900",
    "A388": "Airbus A380", "A343": "Airbus A340",
    "A320": "Airbus A320", "A321": "Airbus A321",
    "A21N": "Airbus A321neo", "A20N": "Airbus A320neo",
    "A319": "Airbus A319", "A310": "Airbus A310",
    "B789": "Boeing 787-9", "B788": "Boeing 787-8",
    "B78X": "Boeing 787-10", "B77W": "Boeing 777-300ER",
    "B772": "Boeing 777-200", "B763": "Boeing 767-300",
    "B752": "Boeing 757-200", "B753": "Boeing 757-300",
    "B712": "Boeing 717", "MD11": "MD-11", "DC10": "DC-10",
    "E175": "Embraer E175", "E170": "Embraer E170",
    "E190": "Embraer E190", "E75L": "Embraer E175",
    "CRJ7": "CRJ-700", "CRJ9": "CRJ-900", "CRJ2": "CRJ-200",
    "BE60": "Beechcraft Duke", "BE36": "Beechcraft Bonanza",
    "BE58": "Beechcraft Baron", "BE20": "Beech King Air 200",
    "BE30": "Beech King Air 300", "C172": "Cessna 172 Skyhawk",
    "C182": "Cessna 182 Skylane", "C150": "Cessna 150",
    "C152": "Cessna 152", "C208": "Cessna Caravan",
    "P28A": "Piper Cherokee", "PA28": "Piper Cherokee",
    "P28R": "Piper Arrow", "SR22": "Cirrus SR22",
    "SR20": "Cirrus SR20", "PC12": "Pilatus PC-12",
    "TBM9": "Daher TBM 960", "TBM8": "Daher TBM 850",
    "H25B": "Hawker 800", "GLF5": "Gulfstream G500",
    "GLF4": "Gulfstream G400", "GLEX": "Bombardier Global",
    "C56X": "Citation Excel", "C680": "Citation Sovereign",
    "C25B": "Citation CJ3", "C525": "Citation CJ",
    "LJ45": "Learjet 45", "F2TH": "Falcon 2000",
    "A139": "AW139 Helicopter", "B06": "Bell 206 Helicopter",
    "R44": "Robinson R44", "EC35": "Airbus H135 Helicopter",
    "H60": "Sikorsky H-60", "V22": "V-22 Osprey",
    "C130": "C-130 Hercules", "K35R": "KC-135 Stratotanker",
    "F16": "F-16 Fighting Falcon", "A10": "A-10 Thunderbolt",
}

AIRLINES = {  # callsign prefix -> name, when adsbdb has no route
    "UAL": "United Airlines", "AAL": "American Airlines",
    "DAL": "Delta Air Lines", "SWA": "Southwest Airlines",
    "ASA": "Alaska Airlines", "JBU": "JetBlue",
    "FFT": "Frontier Airlines", "NKS": "Spirit Airlines",
    "BAW": "British Airways", "VIR": "Virgin Atlantic",
    "DLH": "Lufthansa", "AFR": "Air France", "KLM": "KLM",
    "FDX": "FedEx", "UPS": "UPS Airlines", "AAY": "Allegiant",
    "HAL": "Hawaiian Airlines", "WJA": "WestJet",
    "ACA": "Air Canada", "AMX": "Aeromexico",
}


def _font(size):
    try:
        return ImageFont.truetype(
            "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
            size)
    except OSError:
        return ImageFont.load_default()


FONT_S = _font(9)
FONT_M = _font(11)
LABEL = (120, 140, 160)
VALUE = (225, 232, 240)


def _band_color(alt):
    if alt is None:
        return (150, 150, 150)
    for limit, color in BANDS:
        if alt < limit:
            return color
    return BANDS[-1][1]


def _bearing_dist(lat0, lon0, lat1, lon1):
    dx = (lon1 - lon0) * 60.0 * math.cos(math.radians(lat0))
    dy = (lat1 - lat0) * 60.0
    return (math.hypot(dx, dy),
            (math.degrees(math.atan2(dx, dy)) + 360) % 360)


def _advance(lat, lon, track, gs, seconds):
    dist = gs * seconds / 3600.0
    lat += dist * math.cos(math.radians(track)) / 60.0
    lon += dist * math.sin(math.radians(track)) / (
        60.0 * math.cos(math.radians(lat)))
    return lat, lon


def _compass(brg):
    return ["N", "NE", "E", "SE", "S", "SW", "W", "NW"][
        int((brg + 22.5) % 360 // 45)]


def _wrap(d, text, font, max_w):
    lines, cur = [], ""
    for word in text.split():
        while d.textlength(word, font=font) > max_w and len(word) > 1:
            # a single word wider than the box: hard-split it
            cut = len(word) - 1
            while d.textlength(word[:cut], font=font) > max_w:
                cut -= 1
            lines.append(word[:cut])
            word = word[cut:]
        trial = (cur + " " + word).strip()
        if d.textlength(trial, font=font) <= max_w or not cur:
            cur = trial
        else:
            lines.append(cur)
            cur = word
    if cur:
        lines.append(cur)
    return lines


def _vector_px(gs, nm):
    """Trend-vector length in pixels: where the aircraft will be
    in one minute at its groundspeed, at the scope's scale - the
    Garmin convention."""
    return gs / 60.0 / nm * R


def _get_json(url, timeout=8):
    req = urllib.request.Request(
        url, headers={"User-Agent": "ledwall-skywatch"})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read().decode("utf-8"))


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
        self._routes = {}   # callsign -> route dict or None
        self._acinfo = {}   # hex -> adsbdb aircraft dict or None
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
        try:
            data = _get_json(FEED.format(lat=lat0, lon=lon0, nm=nm),
                             timeout=20)
        except Exception:
            return  # keep the last good picture; never raise
        out = []
        for a in data.get("ac", []):
            if a.get("lat") is None or a.get("lon") is None:
                continue
            alt = a.get("alt_baro")
            if not isinstance(alt, (int, float)):
                alt = None  # "ground" or missing
            vs = a.get("baro_rate")
            if not isinstance(vs, (int, float)):
                vs = a.get("geom_rate")
            if not isinstance(vs, (int, float)):
                vs = None
            dist, brg = _bearing_dist(lat0, lon0, a["lat"], a["lon"])
            out.append({
                "hex": a.get("hex", ""), "lat": a["lat"],
                "lon": a["lon"],
                "call": (a.get("flight") or "").strip(),
                "reg": a.get("r") or "",
                "type": a.get("t") or "",
                "alt": alt, "gs": a.get("gs"), "vs": vs,
                "track": a.get("track"),
                "squawk": a.get("squawk") or "",
                "dist": dist, "brg": brg,
            })
        out.sort(key=lambda a: a["dist"])
        self.aircraft = out
        self._fetched_at = time.time()
        self.dot_count = len(out)
        self._enrich(out)

    def _enrich(self, aircraft):
        """Free adsbdb lookups for the nearest few, cached for the
        session: routes by callsign, owner/type detail by hex."""
        if len(self._routes) > 300 or len(self._acinfo) > 300:
            self._routes.clear()
            self._acinfo.clear()
        for a in aircraft[:4]:
            call = a["call"]
            if call and call not in self._routes:
                try:
                    resp = _get_json(ROUTE.format(call=call))
                    self._routes[call] = (
                        resp.get("response") or {}).get(
                        "flightroute")
                except Exception:
                    self._routes[call] = None
        for a in aircraft[:2]:
            hx = a["hex"].upper()
            if hx and hx not in self._acinfo:
                try:
                    resp = _get_json(ACINFO.format(hex=hx))
                    self._acinfo[hx] = (
                        resp.get("response") or {}).get("aircraft")
                except Exception:
                    self._acinfo[hx] = None

    # -- drawing ---------------------------------------------------
    def _box(self, d, a):
        """The info box for the nearest aircraft (or its absence)."""
        x0, y0, x1, y1 = BOX_X, 20, W - 4, H - 4
        d.rectangle([x0, y0, x1, y1], outline=(34, 54, 72))
        inner = x1 - x0 - 8
        y = y0 + 5
        if a is None:
            d.text((x0 + 4, y), "NO TRAFFIC", font=FONT_M,
                   fill=LABEL)
            return
        ga = not a["call"] or a["call"] == a["reg"]
        title = a["reg"] if ga else a["call"]
        color = _band_color(a["alt"])
        d.text((x0 + 4, y), title[:12], font=FONT_M, fill=color)
        y += 15
        d.line([(x0 + 3, y), (x1 - 3, y)], fill=(34, 54, 72))
        y += 4
        route = self._routes.get(a["call"]) if a["call"] else None
        info = self._acinfo.get(a["hex"].upper())
        # operator: airline on the route, else the registered owner,
        # else a known callsign prefix, else GA/plain
        operator = None
        if route:
            operator = (route.get("airline") or {}).get("name")
        if not operator and info:
            operator = info.get("registered_owner")
        if not operator and not ga:
            operator = AIRLINES.get(a["call"][:3])
        if operator:
            for ln in _wrap(d, operator.upper(), FONT_S, inner)[:2]:
                d.text((x0 + 4, y), ln, font=FONT_S, fill=VALUE)
                y += 11
        # aircraft type in full, when known
        tname = TYPE_NAMES.get(a["type"])
        if not tname and info:
            tname = ("%s %s" % (info.get("manufacturer", ""),
                                info.get("type", ""))).strip()
        if not tname:
            tname = a["type"]
        if tname:
            for ln in _wrap(d, tname, FONT_S, inner)[:2]:
                d.text((x0 + 4, y), ln, font=FONT_S, fill=LABEL)
                y += 11
        if a["reg"] and not ga:
            d.text((x0 + 4, y), "REG " + a["reg"], font=FONT_S,
                   fill=LABEL)
            y += 11
        y += 3
        if route:
            org, dst = route.get("origin") or {}, \
                route.get("destination") or {}
            codes = "%s > %s" % (org.get("iata_code", "???"),
                                 dst.get("iata_code", "???"))
            d.text((x0 + 4, y), codes, font=FONT_M,
                   fill=(0, 210, 200))
            y += 14
            for apt in (org, dst):
                name = apt.get("municipality") or apt.get(
                    "name", "")
                for ln in _wrap(d, name, FONT_S, inner)[:1]:
                    d.text((x0 + 4, y), ln, font=FONT_S, fill=VALUE)
                    y += 11
        elif ga:
            d.text((x0 + 4, y), "GA", font=FONT_S, fill=LABEL)
            y += 11
            if a["squawk"] == "1200":
                d.text((x0 + 4, y), "VFR - SQK 1200", font=FONT_S,
                       fill=LABEL)
                y += 11
        y += 3
        rows = []
        if a["alt"] is not None:
            rows.append(("ALT", format(int(a["alt"]), ",") + " FT"))
        if a["gs"]:
            rows.append(("SPD", "%d KT" % a["gs"]))
        if a["track"] is not None:
            rows.append(("HDG", "%03d" % a["track"]))
        if a["vs"]:
            rows.append(("V/S", "%+d FPM" % int(a["vs"])))
        rows.append(("DST", "%.0f NM %s" % (
            a["dist"], _compass(a["brg"]))))
        for k, v in rows:
            if y > y1 - 12:
                break
            d.text((x0 + 4, y), k, font=FONT_S, fill=LABEL)
            d.text((x0 + 32, y), v, font=FONT_S, fill=VALUE)
            y += 11

    def draw(self, ctx):
        self._sync_fetch_s()
        lat0, lon0 = self._center()
        nm = int(self.config.get("sw_range_nm", 50))
        label = (self.config.get("sw_label") or "KFLG")[:6].upper()
        now = time.time()
        age = now - self._fetched_at if self._fetched_at else None
        img = Image.new("RGB", (W, H), (2, 6, 12))
        d = ImageDraw.Draw(img)
        for frac in (1 / 3, 2 / 3, 1.0):
            r = R * frac
            d.ellipse([CX - r, CY - r, CX + r, CY + r],
                      outline=(26, 50, 70))
            d.text((CX + 2, CY - r - 4), "%d" % round(nm * frac),
                   font=FONT_S, fill=(70, 100, 120))
        d.line([(CX - R, CY), (CX + R, CY)], fill=(18, 36, 50))
        d.line([(CX, CY - R), (CX, CY + R)], fill=(18, 36, 50))
        d.text((CX - 4, CY - R - 13), "N", font=FONT_S,
               fill=(70, 100, 120))
        d.rectangle([CX - 2, CY - 2, CX + 2, CY + 2],
                    fill=(240, 240, 240))
        # the centre label lives under the scope: beside the marker
        # it garbles the label of any aircraft passing close overhead
        tw = d.textlength(label, font=FONT_S)
        d.text((CX - tw / 2, CY + R + 3), label, font=FONT_S,
               fill=(200, 210, 220))
        if age is None:
            head = "OVERHEAD - WAITING"
        else:
            head = "OVERHEAD - %d IN %d NM" % (len(self.aircraft),
                                               nm)
        d.text((6, 4), head, font=FONT_M, fill=(205, 214, 224))
        if age is not None and age > 180:
            d.text((W - 40, 4), "STALE", font=FONT_M,
                   fill=(255, 176, 0))
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
            shown.append((a, x, y))
        shown.reverse()
        label_spots = []
        for i, (a, x, y) in enumerate(shown):
            color = _band_color(a["alt"])
            if a["track"] is not None and a["gs"] and a["gs"] > 20:
                ln = min(R, _vector_px(a["gs"], nm))
                rad = math.radians(a["track"])
                d.line([(x, y), (x + ln * math.sin(rad),
                                 y - ln * math.cos(rad))],
                       fill=color)
            if i == 0:  # the nearest: white heart, band-colour ring
                d.ellipse([x - 4, y - 4, x + 4, y + 4], outline=color,
                          width=2)
                d.ellipse([x - 1, y - 1, x + 1, y + 1],
                          fill=(255, 255, 255))
            else:
                d.ellipse([x - 2, y - 2, x + 2, y + 2], fill=color)
            if i < 2 and a["call"]:
                # label beside the dot, on the side the trend vector
                # is NOT pointing (else the vector's tip hides
                # behind the label); fall back to the other side on
                # a collision, else skip the label
                tw = d.textlength(a["call"], font=FONT_S)
                sides = (x + 6, x - 6 - tw)
                if a["track"] is not None and math.sin(
                        math.radians(a["track"])) > 0.3:
                    sides = sides[::-1]
                for lx in sides:
                    if lx < 2 or lx + tw > BOX_X - 2:
                        continue
                    if any(abs(lx - ox) < 44 and abs(y - oy) < 12
                           for ox, oy in label_spots):
                        continue
                    # knock out a backing patch so a trend vector
                    # passing behind the label doesn't strike
                    # through the text
                    d.rectangle([lx - 1, y - 6, lx + tw + 1, y + 5],
                                fill=(2, 6, 12))
                    d.text((lx, y - 5), a["call"], font=FONT_S,
                           fill=color)
                    label_spots.append((lx, y))
                    break
        if not shown and age is not None:
            msg = "NO AIRCRAFT IN %d NM" % nm
            tw = d.textlength(msg, font=FONT_S)
            d.text((CX - tw / 2, CY - 5), msg, font=FONT_S,
                   fill=LABEL)
        self._box(d, self.aircraft[0] if self.aircraft else None)
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
