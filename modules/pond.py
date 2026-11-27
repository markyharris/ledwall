"""Module 2: the pond.

Pebbles and rain on still water, drawn as relief. A two-buffer wave
simulation (the classic ripple algorithm) runs at half resolution -
each cell is a 2x2 LED block, which suits the wall - and every frame
the height field is coloured by the chromostereoptic ramp Mark
noticed on the map itself: crests in advancing reds and ambers,
mid-slopes green, troughs in receding blues. Slope shading (a fixed
light from the upper left) backs the colour cue up, so the ridges
and troughs read as real relief even for viewers whose eyes don't
do the colour-depth effect.

Drops are scheduled on the module's own tick count, never the wall
clock, so the pace is exactly the tick rate whatever the loop is
doing. There is nothing to fetch: refresh_data is the base no-op.
"""
import random

from PIL import Image

from .base import Module

W, H = 128, 96          # simulation grid (2x2 LEDs per cell)
DAMPING = 0.986         # energy kept per substep
SUBSTEPS = 2            # wave steps per draw
RAIN_AMP = 120.0
PEBBLE_AMP = 340.0
RENDER_GAIN = 1.0 / 55.0  # sim units -> [-1, 1] picture height

# Height -> colour, trough to crest: blues recede, reds advance.
_STOPS = [(-1.0, (0, 0, 170)), (-0.45, (0, 60, 220)),
          (0.0, (0, 150, 60)), (0.45, (230, 160, 0)),
          (1.0, (255, 30, 0))]


def _build_lut():
    lut = []
    for i in range(257):
        v = i / 128.0 - 1.0
        for j in range(len(_STOPS) - 1):
            h0, c0 = _STOPS[j]
            h1, c1 = _STOPS[j + 1]
            if h0 <= v <= h1:
                f = (v - h0) / (h1 - h0)
                lut.append(tuple(int(c0[k] + (c1[k] - c0[k]) * f)
                                 for k in range(3)))
                break
        else:
            lut.append(_STOPS[-1][1])
    return lut


LUT = _build_lut()
REST = (0, 0, 10)  # still water


class PondModule(Module):
    name = "pond"
    title = "Pond ripples"
    tick_s = 0.1

    def setup(self, config):
        super().setup(config)
        self.cur = [0.0] * (W * H)
        self.prev = [0.0] * (W * H)
        self._tick = 0
        self._next_rain = 15          # first drop ~1.5 s in
        self._next_pebble = 25        # first pebble ~2.5 s in
        self._recent_drops = []       # ticks of drops still rippling
        self.dot_count = 0

    # -- simulation ------------------------------------------------
    def _drop(self, x, y, amp, spread=False):
        cells = [(x, y, 1.0), (x - 1, y, 0.5), (x + 1, y, 0.5),
                 (x, y - 1, 0.5), (x, y + 1, 0.5)]
        if spread:  # a pebble displaces a patch, not a point
            cells += [(x - 1, y - 1, 0.6), (x + 1, y - 1, 0.6),
                      (x - 1, y + 1, 0.6), (x + 1, y + 1, 0.6),
                      (x - 2, y, 0.3), (x + 2, y, 0.3),
                      (x, y - 2, 0.3), (x, y + 2, 0.3)]
        for cx, cy, f in cells:
            if 0 < cx < W - 1 and 0 < cy < H - 1:
                self.cur[cy * W + cx] += amp * f
        self._recent_drops.append(self._tick)

    def _step(self):
        cur, prev = self.cur, self.prev
        new = prev  # the old buffer becomes the next frame's canvas
        for y in range(1, H - 1):
            row = y * W
            for i in range(row + 1, row + W - 1):
                new[i] = ((cur[i - 1] + cur[i + 1] + cur[i - W]
                           + cur[i + W]) * 0.5 - prev[i]) * DAMPING
        self.prev = cur
        self.cur = new

    def _schedule(self):
        drop_s = float(self.config.get("pond_drop_s", 2.5))
        if drop_s > 0 and self._tick >= self._next_rain:
            self._drop(random.randint(4, W - 5),
                       random.randint(4, H - 5), RAIN_AMP)
            mean = max(1, int(drop_s / self.tick_s))
            self._next_rain = self._tick + max(
                1, int(random.gauss(mean, mean * 0.45)))
        pebble_s = int(self.config.get("pond_pebble_s", 30))
        if pebble_s > 0 and self._tick >= self._next_pebble:
            self._drop(random.randint(W // 4, 3 * W // 4),
                       random.randint(H // 4, 3 * H // 4),
                       PEBBLE_AMP, spread=True)
            self._next_pebble = self._tick + int(pebble_s / self.tick_s)
        self._recent_drops = [t for t in self._recent_drops
                              if self._tick - t < 30]
        self.dot_count = len(self._recent_drops)

    # -- drawing ---------------------------------------------------
    def draw(self, ctx):
        self._tick += 1
        self._schedule()
        for _ in range(SUBSTEPS):
            self._step()
        relief = max(0, min(100, int(
            self.config.get("pond_relief", 70)))) / 100.0
        gain = RENDER_GAIN * (0.35 + 0.65 * relief)
        slope = 0.011 * relief  # light contrast per sim unit of slope
        cur = self.cur
        pixels = []
        append = pixels.append
        for y in range(H):
            row = y * W
            for x in range(W):
                i = row + x
                v = cur[i] * gain
                if -0.04 < v < 0.04:
                    append(REST)
                    continue
                if v > 1.0:
                    v = 1.0
                elif v < -1.0:
                    v = -1.0
                dx = cur[i + 1] - cur[i - 1] if 0 < x < W - 1 else 0.0
                dy = cur[i + W] - cur[i - W] if 0 < y < H - 1 else 0.0
                light = 1.0 + (dx + dy) * slope
                if light < 0.35:
                    light = 0.35
                elif light > 1.45:
                    light = 1.45
                r, g, b = LUT[int((v + 1.0) * 128)]
                append((min(255, int(r * light)),
                        min(255, int(g * light)),
                        min(255, int(b * light))))
        img = Image.new("RGB", (W, H))
        img.putdata(pixels)
        return img.resize((W * 2, H * 2), Image.NEAREST)

    def admin_fields(self):
        return [
            {"key": "pond_drop_s", "label": "Rain (seconds between "
             "drops)", "type": "number"},
            {"key": "pond_pebble_s", "label": "Pebbles (seconds "
             "between)", "type": "number"},
            {"key": "pond_relief", "label": "Relief strength",
             "type": "range"},
        ]
