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


class MetarMapModule(Module):
    name = "metar_map"
    title = "METAR Weather Map"
    refresh_s = 300
    tick_s = 1.0  # 1 Hz redraw so the thunderstorm bolts can blink

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
        render.draw_icons(frame, self._icon_stations, (ctx or 0) % 2)
        return frame

    def admin_fields(self):
        return [
            {"key": "region", "label": "Region", "type": "select",
             "options": ["CONUS"]},
            {"key": "dot_size", "label": "Station dot size",
             "type": "select", "options": ["1", "2"]},
        ]
