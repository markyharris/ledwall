"""Geographic projection for the LED canvas.

Simple equirectangular projection with a cos(latitude) correction on the
longitude axis, fitted into the panel grid with the map centred. Good
enough for LED art at 256x192 and honest about its limits: polar regions
stretch, which is why high-latitude regions get their own presets.
"""
import math

CANVAS_W = 256
CANVAS_H = 192


class Projection:
    def __init__(self, bbox, width=CANVAS_W, height=CANVAS_H):
        """bbox = (lon_min, lat_min, lon_max, lat_max) in degrees."""
        lon0, lat0, lon1, lat1 = bbox
        mid_lat = math.radians((lat0 + lat1) / 2.0)
        self.kx = math.cos(mid_lat)
        span_x = (lon1 - lon0) * self.kx
        span_y = lat1 - lat0
        self.scale = min(width / span_x, height / span_y)
        self.ox = (width - span_x * self.scale) / 2.0
        self.oy = (height - span_y * self.scale) / 2.0
        self.lon0 = lon0
        self.lat1 = lat1
        self.width = width
        self.height = height

    def xy(self, lon, lat):
        x = self.ox + (lon - self.lon0) * self.kx * self.scale
        y = self.oy + (self.lat1 - lat) * self.scale
        return (x, y)

    def inside(self, x, y, margin=0):
        return (-margin <= x < self.width + margin
                and -margin <= y < self.height + margin)
