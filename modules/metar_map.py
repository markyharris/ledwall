"""Module 1: the METAR weather map.

Flight-category dots in the classic colours, weather icons overlaid for
significant weather, and thunderstorm bolts that blink on a 1 Hz tick.
Base geography is cached per region; the dot layer is re-plotted only
when the data refreshes, and each tick re-composites just the icons.
"""
import json
import os

from ..core import metar, render
from ..core.regions import get_region
from .base import Module

DATA_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data")


# Icon fade curve over one 2-second cycle at the 4 Hz tick: a gentle
# breathing pulse that never quite reaches invisible.
FADE_LEVELS = (0.30, 0.48, 0.65, 0.83, 1.0, 0.83, 0.65, 0.48)


class MetarMapModule(Module):
    name = "metar_map"
    title = "METAR Weather Map"
    refresh_s = 300
    tick_s = 0.25  # 4 Hz redraw for smooth icon fade / bolt blink

    def setup(self, config):
        super().setup(config)
        self.region = get_region(config.get("region", "CONUS"))
        self.base = render.build_base(self.region)
        with open(os.path.join(DATA_DIR, "us_stations.json")) as f:
            self.station_ids = json.load(f)
        self.metars = {}
        self.dot_count = 0
        self._dot_frame = None
        self._icon_stations = []
        self._dirty = True

    def refresh_data(self):
        self.metars = metar.fetch_metars(self.station_ids)
        self._dirty = True

    def draw(self, ctx):
        if self._dirty or self._dot_frame is None:
            region = dict(self.region)
            dot = int(self.config.get("dot_size", 2))
            region["dot"] = dot
            region["min_sep"] = 3 if dot >= 2 else 2
            self._dot_frame, self.dot_count, self._icon_stations = \
                render.plot_weather(self.base, self.metars, region)
            self._dirty = False
        frame = self._dot_frame.copy()
        if self.config.get("show_icons", True):
            enabled = {"TS": self.config.get("icon_ts", True),
                       "SN": self.config.get("icon_sn", True),
                       "RA": self.config.get("icon_ra", True),
                       "FG": self.config.get("icon_fg", True),
                       "GR": self.config.get("icon_gr", True)}
            stations = [s for s in self._icon_stations if enabled[s[2]]]
            tick = ctx or 0
            anim = self.config.get("icon_anim", "fade")
            if anim == "fade":
                level = FADE_LEVELS[tick % len(FADE_LEVELS)]
                bolt_on = True
            elif anim == "blink":
                level, bolt_on = 1.0, (tick % 8) < 4
            else:  # steady
                level, bolt_on = 1.0, True
            render.draw_icons(frame, stations, level=level,
                              bolt_on=bolt_on)
        return frame

    def admin_fields(self):
        return [
            {"key": "region", "label": "Region", "type": "select",
             "options": ["CONUS"]},
            {"key": "dot_size", "label": "Station dot size",
             "type": "select", "options": ["1", "2"]},
        ]
