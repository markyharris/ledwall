"""Module 1: the METAR weather map.

Flight-category dots in the classic colours, weather icons overlaid for
significant weather (phase 2), lightning flash on thunderstorm stations
(phase 2). Base geography is cached per region; only the weather layer
changes between refreshes.
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

    def setup(self, config):
        super().setup(config)
        self.region = get_region(config.get("region", "CONUS"))
        self.base = render.build_base(self.region)
        with open(os.path.join(DATA_DIR, "us_stations.json")) as f:
            self.station_ids = json.load(f)
        self.metars = {}
        self.dot_count = 0

    def refresh_data(self):
        self.metars = metar.fetch_metars(self.station_ids)

    def draw(self, ctx):
        frame, self.dot_count = render.plot_weather(
            self.base, self.metars, self.region)
        return frame

    def admin_fields(self):
        return [
            {"key": "region", "label": "Region", "type": "select",
             "options": ["CONUS"]},
        ]
