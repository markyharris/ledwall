"""Module 1: the METAR weather map.

Flight-category dots in the classic colours, weather icons overlaid for
significant weather, and thunderstorm bolts that blink on a 1 Hz tick.
Base geography is cached per region; the dot layer is re-plotted only
when the data refreshes, and each tick re-composites just the icons.
"""
import json
import os

from ..core import metar, render
from ..core.geo import Projection
from ..core.regions import get_region
from .base import Module

DATA_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data")

_WORLD_STATIONS = None


def _station_ids(region):
    """Station ids to fetch for a region. US views share the national
    list; world views select from the AWC METAR station list by the
    region's bounding box (country views then clip to the outline)."""
    global _WORLD_STATIONS
    if region.get("stations") == "world":
        if _WORLD_STATIONS is None:
            with open(os.path.join(DATA_DIR, "world_stations.json")) as f:
                _WORLD_STATIONS = json.load(f)
        lon0, lat0, lon1, lat1 = region["bbox"]
        return [s["id"] for s in _WORLD_STATIONS
                if lon0 <= s["lon"] <= lon1
                and lat0 <= s["lat"] <= lat1]
    with open(os.path.join(DATA_DIR, "us_stations.json")) as f:
        return json.load(f)


# Icon fade curve over one 4-second cycle at the 4 Hz tick: a gentle
# breathing pulse that never quite reaches invisible, and whose peak
# runs hot (1.25, channels clamp) so the brightest moment pops. (The
# original 2-second cycle felt hurried on the wall - Mark.)
FADE_LEVELS = (0.30, 0.41, 0.52, 0.63, 0.74, 0.86, 0.99, 1.12,
               1.25, 1.12, 0.99, 0.86, 0.74, 0.63, 0.52, 0.41)


class MetarMapModule(Module):
    name = "metar_map"
    title = "METAR Weather Map"
    refresh_s = 300
    tick_s = 0.25  # 4 Hz redraw for smooth icon fade / bolt blink

    def setup(self, config):
        super().setup(config)
        self.region = get_region(config.get("region", "CONUS"))
        self.base = render.build_base(self.region)
        self.station_ids = _station_ids(self.region)
        self.metars = {}
        self.dot_count = 0
        self._dot_frame = None
        self._icon_stations = []
        self._dirty = True
        self._ts_seen = set()  # bolt positions at the previous refresh
        self._flash = {}       # (x, y) -> tick a new bolt first painted
        self._proj = Projection(self.region["bbox"],
                                width=self.base.width,
                                height=self.base.height)
        self._home_cache = {}  # home airport id -> last-known (lon, lat)

    def refresh_data(self):
        self.metars = metar.fetch_metars(self.station_ids)
        self._dirty = True

    def draw(self, ctx):
        tick = ctx or 0
        if self._dirty or self._dot_frame is None:
            region = dict(self.region)
            dot = int(self.config.get("dot_size", 2))
            region["dot"] = dot
            region["min_sep"] = 3 if dot >= 2 else 2
            self._dot_frame, self.dot_count, self._icon_stations = \
                render.plot_weather(self.base, self.metars, region)
            if self.config.get("show_label", True):
                reserved = render.zulu_clock_box(self.base.width) \
                    if self.config.get("show_clock", True) else None
                render.draw_region_label(
                    self._dot_frame, self.base,
                    self.region.get("label") or self.region["name"],
                    self._icon_stations, reserved=reserved)
            self._dirty = False
            # A bolt that was not there at the previous refresh earns
            # the entrance flash; one that merely persists does not.
            ts_now = {(x, y) for x, y, k in self._icon_stations
                      if k == "TS"}
            for pos in ts_now - self._ts_seen:
                self._flash[pos] = tick
            self._ts_seen = ts_now
        frame = self._dot_frame.copy()
        if self.config.get("show_icons", True):
            enabled = {"TS": self.config.get("icon_ts", True),
                       "SN": self.config.get("icon_sn", True),
                       "RA": self.config.get("icon_ra", True),
                       "FG": self.config.get("icon_fg", True),
                       "GR": self.config.get("icon_gr", True)}
            stations = [s for s in self._icon_stations if enabled[s[2]]]
            anim = self.config.get("icon_anim", "fade")
            if anim == "fade":
                level = FADE_LEVELS[tick % len(FADE_LEVELS)]
                bolt_on = True
            elif anim == "blink":
                level, bolt_on = 1.0, (tick % 8) < 4
            else:  # steady
                level, bolt_on = 1.0, True
            # Entrance flash: double-size white for half a second,
            # single-size white for a beat, then the bolt settles
            # into the normal yellow fade with the other icons.
            flash = {}
            for pos, start in list(self._flash.items()):
                elapsed = tick - start
                if elapsed <= 1:
                    flash[pos] = 0
                elif elapsed == 2:
                    flash[pos] = 1
                else:
                    del self._flash[pos]
            render.draw_icons(frame, stations, level=level,
                              bolt_on=bolt_on, flash=flash)
        home = (self.config.get("home_airport") or "").strip().upper()
        if home:
            rep = self.metars.get(home)
            if rep:
                self._home_cache[home] = (rep["lon"], rep["lat"])
            if home in self._home_cache:
                lon, lat = self._home_cache[home]
                polys = render._feature_polys(self.region)
                if not polys or render._inside_polys(lon, lat, polys):
                    fx, fy = self._proj.xy(lon, lat)
                    fx, fy = int(fx), int(fy)
                    if 0 <= fx < frame.width - 6 and \
                            9 <= fy < frame.height:
                        pulse = 0.55 + 0.45 * (
                            (FADE_LEVELS[tick % len(FADE_LEVELS)] - 0.30)
                            / 0.95)
                        render.draw_home_flag(frame, fx, fy, level=pulse)
        if self.config.get("show_clock", True):
            render.draw_zulu_clock(frame)
        return frame

    def admin_fields(self):
        return [
            {"key": "region", "label": "Region", "type": "select",
             "options": ["CONUS"]},
            {"key": "dot_size", "label": "Station dot size",
             "type": "select", "options": ["1", "2"]},
        ]
