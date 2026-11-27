"""Rocket Launch Board: the world's next launches, counted down.

Data is Launch Library 2 (The Space Devs, free, no key): the
next dozen scheduled launches worldwide. The header counts down
to the next one - big, local 24-hour, ticking every second -
with its vehicle, mission and pad, plus a thumbnail world map
with the upcoming pads dotted and the next pad ringed. The rows
below list what follows. All times are local, like the other
sky modules; only the weather map speaks Zulu.

NET precision is honored: when a launch is only dated to the
day or month, the board says NET <date> instead of counting
down to a midnight that nobody promised.

The free API throttles hard (15 requests/hour per address), so
the cadence is a polite 30 minutes once data is flowing, and a
failed fetch always keeps the last good list.
"""
import calendar
import json
import time
import urllib.request
from datetime import datetime

from PIL import Image, ImageDraw

from ledwall.core import render
from ledwall.core.geo import CANVAS_H, CANVAS_W, Projection
from ledwall.core.regions import get_region
from ledwall.modules.base import Module
from ledwall.modules.skywatch import _font

API = ("https://ll.thespacedevs.com/2.2.0/launch/upcoming/"
       "?limit=12")
ACCENT = (255, 169, 77)
LABEL = (140, 140, 150)
VALUE = (240, 240, 245)
DIM = (110, 112, 125)
BG = (7, 8, 14)
DONE = ("Success", "Failure", "Partial Failure")
STATUS_C = {"Go": (0, 220, 120), "TBD": (255, 190, 0),
            "TBC": (255, 190, 0), "Hold": (255, 92, 40),
            "In Flight": (80, 200, 255)}
MON = ("JAN", "FEB", "MAR", "APR", "MAY", "JUN", "JUL", "AUG",
       "SEP", "OCT", "NOV", "DEC")
DOW = ("MON", "TUE", "WED", "THU", "FRI", "SAT", "SUN")


def _parse_net(text):
    """LL2's ISO timestamps ('...Z', sometimes with an offset)
    to epoch seconds; None when unparseable."""
    if not text:
        return None
    try:
        dt = datetime.fromisoformat(text.replace("Z", "+00:00"))
        return dt.timestamp()
    except ValueError:
        pass
    for fmt in ("%Y-%m-%dT%H:%M:%SZ", "%Y-%m-%dT%H:%M:%S"):
        try:
            return calendar.timegm(time.strptime(text, fmt))
        except ValueError:
            continue
    return None


def _parse(data, now):
    """LL2 payload -> launch dicts, soonest first. Entries that
    already flew (the feed keeps them briefly) and stale NETs
    are dropped."""
    out = []
    for r in data.get("results", []):
        status = (r.get("status") or {}).get("abbrev") or ""
        if status in DONE:
            continue
        net = _parse_net(r.get("net"))
        if net is None or net < now - 3600:
            continue
        name = r.get("name") or ""
        vehicle = ((r.get("rocket") or {}).get(
            "configuration") or {}).get("name") or ""
        mission = (r.get("mission") or {}).get("name") or ""
        if not mission and "|" in name:
            mission = name.split("|", 1)[1].strip()
        if not vehicle and "|" in name:
            vehicle = name.split("|", 1)[0].strip()
        pad = r.get("pad") or {}
        loc = (pad.get("location") or {}).get("name") or ""
        try:
            lat = float(pad.get("latitude"))
            lon = float(pad.get("longitude"))
        except (TypeError, ValueError):
            lat = lon = None
        prec = ((r.get("net_precision") or {}).get("name")
                or "Hour")
        out.append({
            "net": net, "vehicle": vehicle, "mission": mission,
            "provider": (r.get("launch_service_provider")
                         or {}).get("name") or "",
            "pad": pad.get("name") or "", "loc": loc,
            "lat": lat, "lon": lon, "status": status,
            "precise": prec in ("Second", "Minute", "Hour"),
            "precision": prec})
    out.sort(key=lambda l: l["net"])
    return out


def _fit(d, text, font, maxw):
    while text and d.textlength(text, font) > maxw:
        text = text[:-1]
    return text


def _countdown(net, now):
    s = int(net - now)
    if s < 0:
        return "T+" + _hms(-s)
    return _hms(s)


def _hms(s):
    d, s = divmod(s, 86400)
    h, s = divmod(s, 3600)
    m, s = divmod(s, 60)
    if d:
        return "%dD %02d:%02d:%02d" % (d, h, m, s)
    return "%02d:%02d:%02d" % (h, m, s)


def _date_label(net):
    lt = time.localtime(net)
    return "%s %s %02d" % (DOW[lt.tm_wday], MON[lt.tm_mon - 1],
                           lt.tm_mday)


class LaunchesModule(Module):
    name = "launches"
    title = "Rocket Launch Board"
    tick_s = 1  # the countdown ticks every second
    PERSIST = ("launches", "fetched")

    @property
    def fetch_s(self):
        # 30 minutes once data is flowing (the free API allows
        # 15 requests an hour; two is plenty). Until the first
        # list lands, retry every two minutes - brisk, but not
        # hammering a throttled API (see the ISS module's note).
        return 1800 if self.launches else 120

    def setup(self, config):
        self.cfg = config
        self.proj = Projection(get_region("WORLD")["bbox"])
        self.launches = []
        self.fetched = 0.0
        self.dot_count = 0

    def refresh_data(self):
        try:
            req = urllib.request.Request(API, headers={
                "User-Agent": "ledwall (personal LED display)"})
            with urllib.request.urlopen(req, timeout=30) as resp:
                data = json.loads(resp.read().decode("utf-8",
                                                     "replace"))
            parsed = _parse(data, time.time())
            if parsed:
                self.launches = parsed
                self.fetched = time.time()
                self.dot_count = len(parsed)
        except Exception:
            pass  # throttled or down: keep the last good list

    def _thumb(self, tick):
        """The world, thumbnail-sized, with the upcoming pads
        dotted and the next pad ringed (the ring breathes with
        the tick)."""
        tw, th = 74, 54
        base = render.build_base(get_region("WORLD"))
        img = base.resize((tw, th)).convert("RGBA")
        black = Image.new("RGBA", (tw, th), (0, 0, 0, 255))
        img = Image.blend(img, black, 0.25)
        d = ImageDraw.Draw(img)
        for i, l in enumerate(self.launches):
            if l["lat"] is None:
                continue
            x, y = self.proj.xy(l["lon"], l["lat"])
            tx, ty = x * tw / CANVAS_W, y * th / CANVAS_H
            if i == 0:
                r = 3 + (tick % 3)
                d.ellipse((tx - r, ty - r, tx + r, ty + r),
                          outline=(255, 170, 60, 255))
                d.ellipse((tx - 1, ty - 1, tx + 1, ty + 1),
                          fill=(255, 200, 90, 255))
            else:
                d.ellipse((tx - 1, ty - 1, tx + 1, ty + 1),
                          fill=(200, 170, 120, 200))
        return img

    def draw(self, ctx):
        img = Image.new("RGB", (CANVAS_W, CANVAS_H), BG)
        d = ImageDraw.Draw(img)
        now = time.time()
        f_lab = _font(9)
        f_big = _font(25)
        f_mid = _font(11)
        f_row = _font(10)
        f_s = _font(9)

        if not self.launches:
            d.text((5, 4), "ROCKET LAUNCHES", font=_font(11),
                   fill=ACCENT)
            msg = "WAITING FOR LAUNCH DATA"
            d.text(((CANVAS_W - d.textlength(msg, font=f_mid)) / 2,
                    84), msg, font=f_mid, fill=VALUE)
            return img

        nxt = self.launches[0]
        show_map = self.cfg.get("launch_sites", True)
        text_w = 172 if show_map else CANVAS_W - 10

        d.text((5, 4), "NEXT LAUNCH", font=f_lab, fill=ACCENT)
        if nxt["precise"]:
            big = _countdown(nxt["net"], now)
            if nxt["net"] >= now:
                big = "T-" + big
        elif nxt["precision"] == "Day":
            big = "NET " + _date_label(nxt["net"]).split(" ", 1)[1]
        else:
            lt = time.localtime(nxt["net"])
            big = "NET %s %d" % (MON[lt.tm_mon - 1], lt.tm_year)
        while d.textlength(big, font=f_big) > text_w and \
                f_big.size > 13:
            f_big = _font(f_big.size - 2)
        d.text((5, 15), big, font=f_big, fill=VALUE)

        head = nxt["vehicle"].upper()
        if nxt["mission"]:
            head += "  ·  " + nxt["mission"].upper()
        if self.cfg.get("launch_provider", True) and \
                nxt["provider"]:
            with_prov = nxt["provider"].upper() + "  ·  " + head
            if d.textlength(with_prov, font=f_mid) <= text_w:
                head = with_prov  # provider only when it fits
        d.text((5, 45), _fit(d, head, f_mid, text_w), font=f_mid,
               fill=VALUE)
        lt = time.localtime(nxt["net"])
        when = "%s %02d:%02d" % (_date_label(nxt["net"]),
                                 lt.tm_hour, lt.tm_min)
        if not nxt["precise"]:
            when = "%s — DATE ONLY, NO SET TIME" % \
                _date_label(nxt["net"])
        sub = when
        place = nxt["pad"] or nxt["loc"]
        if place:
            sub += "  ·  " + place.upper()
        st = nxt["status"].upper()
        stw = d.textlength(st, font=f_s) + 8 if st else 0
        sub = _fit(d, sub, f_s, text_w - stw)
        d.text((5, 59), sub, font=f_s, fill=LABEL)
        if st:
            d.text((5 + d.textlength(sub, font=f_s) + 8, 59), st,
                   font=f_s,
                   fill=STATUS_C.get(nxt["status"], LABEL))
        if show_map:
            img.paste(self._thumb(ctx), (178, 6))

        d.line((4, 74, CANVAS_W - 4, 74), fill=(52, 54, 68))

        # the body column starts past the widest possible stamp
        body_x = 5 + d.textlength("WED NOV 30 14:03", font=f_s) + 8
        y = 80
        for l in self.launches[1:6]:
            lt = time.localtime(l["net"])
            stamp = "%s %02d:%02d" % (_date_label(l["net"]),
                                      lt.tm_hour, lt.tm_min)
            d.text((5, y), stamp, font=f_s, fill=DIM)
            body = l["vehicle"].upper()
            if l["mission"]:
                body += " · " + l["mission"].upper()
            st = l["status"]
            stw = d.textlength(st.upper(), font=f_s) if st else 0
            avail = CANVAS_W - 5 - body_x - (stw + 8 if st else 0)
            d.text((body_x, y), _fit(d, body, f_row, avail),
                   font=f_row, fill=VALUE)
            if st:
                d.text((CANVAS_W - 5 - stw, y), st.upper(),
                       font=f_s,
                       fill=STATUS_C.get(st, LABEL))
            y += 20
            if y > CANVAS_H - 24:
                break

        foot = "%d UPCOMING · LAUNCH LIBRARY 2" % len(self.launches)
        if self.fetched:
            ft = time.localtime(self.fetched)
            foot += " · UPDATED %02d:%02d" % (ft.tm_hour, ft.tm_min)
        d.text((5, CANVAS_H - 11), foot, font=_font(8), fill=DIM)
        return img
