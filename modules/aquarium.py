"""Module 3: the aquarium.

A saltwater scene built for depth on a flat wall. The static set
(water, far ridge, sand, mid rocks and their corals) is composed
once; every frame the living layers are drawn over it in strict
back-to-front order, which is where the 3D comes from:

- occlusion - near fish pass in front of the turtle and the rocks,
  far fish pass behind the mid rocks;
- motion parallax - each depth plane swims at its own speed;
- atmospheric shift - far fish are smaller, bluer and dimmer, the
  way real water eats colour with distance;
- chromostereopsis - the palette is authored in ChromaDepth order
  (saturated reds and oranges nearest, receding blues farthest),
  so the warm foreground genuinely seems to float off the
  panels;
- framing - dark rocks with warm coral intrude into the two near
  corners, so the scene reads as looking INTO a tank.

Light rays sway from the surface, caustics shimmer along the sand,
bubbles rise from the coral, and a turtle crosses the foreground
now and then. Nothing to fetch: refresh_data is the base no-op.
"""
import math
import random

from PIL import Image, ImageDraw

from .base import Module

W, H = 256, 192
WATER = (16, 58, 105)

# species: (body, tail/fin, white bands?)
CLOWN = ((255, 122, 24), (255, 150, 40), True)
TANG = ((34, 84, 225), (250, 214, 70), False)
YELLOW = ((250, 205, 40), (240, 180, 30), False)
RED = ((236, 62, 48), (220, 90, 60), False)
PURPLE = ((156, 84, 224), (190, 120, 240), False)
SILVER = ((168, 196, 220), (150, 180, 205), False)

PLANES = {  # sprite scale, blue blend, brightness, speed factor
    "far": (0.45, 0.55, 0.75, 0.35),
    "mid": (0.8, 0.25, 0.9, 0.7),
    "near": (1.35, 0.0, 1.05, 1.25),
}
BANDS = {  # vertical range a plane's fish wander in
    "far": (38, 100), "mid": (78, 138), "near": (52, 128),
}
DENSITIES = ("quiet", "lively", "full")


def _blend(c, target, f):
    return tuple(int(c[i] + (target[i] - c[i]) * f) for i in range(3))


def _dim(c, f):
    return tuple(min(255, int(v * f)) for v in c)


def _fish_sprite(body, tail, band, flip, tail_dy):
    """A 48x22 fish facing right, as RGBA."""
    img = Image.new("RGBA", (48, 22), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    d.polygon([(14, 11), (2, 4 + tail_dy), (2, 18 + tail_dy)],
              fill=tail + (255,))
    d.ellipse([10, 4, 44, 18], fill=body + (255,))
    d.polygon([(28, 5), (37, 5), (33, 1)], fill=tail + (220,))
    if band:
        for bx in (20, 33):
            d.polygon([(bx, 5), (bx + 4, 5), (bx + 3, 17),
                       (bx - 1, 17)], fill=(245, 245, 245, 255))
    d.ellipse([38, 8, 41, 11], fill=(8, 8, 12, 255))
    if flip:
        img = img.transpose(Image.FLIP_LEFT_RIGHT)
    return img


def _plane_sprite(species, plane, flip, tail_dy):
    body, tail, band = species
    sc, bf, br, _ = PLANES[plane]
    sp = _fish_sprite(_dim(_blend(body, WATER, bf), br),
                      _dim(_blend(tail, WATER, bf), br),
                      band, flip, tail_dy)
    return sp.resize((max(8, int(48 * sc)), max(5, int(22 * sc))),
                     Image.NEAREST)


class _Fish:
    def __init__(self, species, plane, x, y, direc, speed, bob=2.0):
        self.species, self.plane = species, plane
        self.x, self.y0 = float(x), float(y)
        self.dir, self.speed, self.bob = direc, speed, bob
        self.phase = random.uniform(0, 6.28)
        self.sprites = {(wig, fl): _plane_sprite(species, plane, fl, wig)
                        for wig in (-2, 2) for fl in (False, True)}

    def draw(self, img, tick):
        wig = -2 if (tick // 3) % 2 == 0 else 2
        sp = self.sprites[(wig, self.dir < 0)]
        y = self.y0 + math.sin(tick * 0.15 + self.phase) * self.bob
        img.paste(sp, (int(self.x), int(y)), sp)
        self.x += self.speed * self.dir * PLANES[self.plane][3] * 2.2
        lo, hi = BANDS[self.plane]
        if self.dir > 0 and self.x > W + 12:
            self.x = -72
            self.y0 = random.uniform(lo, hi)
        elif self.dir < 0 and self.x < -72:
            self.x = W + 12
            self.y0 = random.uniform(lo, hi)


def _coral(d, x, y, s, colors, rnd):
    for dx, dy, r in [(-6, 0, 5), (0, -4, 6), (6, 0, 5), (-3, -8, 4),
                      (4, -9, 4)]:
        d.ellipse([x + (dx - r) * s, y + (dy - r) * s,
                   x + (dx + r) * s, y + (dy + r) * s],
                  fill=rnd.choice(colors) + (255,))


def _rock_layer(shapes, base, hi):
    img = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    for pts in shapes:
        d.polygon(pts, fill=base + (255,))
        top = min(p[1] for p in pts)
        xs = [p[0] for p in pts if p[1] == top]
        if xs:
            d.line([(min(xs), top), (max(xs), top)],
                   fill=hi + (255,), width=2)
    return img


def _turtle_sprite():
    img = Image.new("RGBA", (96, 44), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    c = (18, 66, 74, 255)
    d.ellipse([18, 10, 74, 34], fill=c)
    d.ellipse([26, 14, 66, 30], fill=(26, 84, 92, 255))
    d.ellipse([72, 17, 86, 26], fill=c)
    d.polygon([(20, 12), (6, 4), (14, 16)], fill=c)
    d.polygon([(22, 32), (8, 40), (16, 28)], fill=c)
    d.polygon([(64, 10), (76, 2), (72, 14)], fill=c)
    d.polygon([(64, 34), (78, 42), (70, 30)], fill=c)
    return img


class AquariumModule(Module):
    name = "aquarium"
    title = "Aquarium"
    tick_s = 0.1

    def setup(self, config):
        super().setup(config)
        rnd = random.Random(20261126)  # the set never changes shape
        self._base = self._build_base(rnd)
        self._rays = self._build_rays()
        self._fg = self._build_foreground(rnd)
        self._turtle = _turtle_sprite()
        self._tick = 0
        self._density = None
        self._build_fish(config.get("aq_fish", "lively"))
        self._bubbles = [[118, 168, 2], [122, 176, 1], [196, 172, 1]]
        self._turtle_x = None
        self._next_turtle = 60  # first crossing ~6 s in

    # -- the set ---------------------------------------------------
    @staticmethod
    def _build_base(rnd):
        img = Image.new("RGB", (W, H))
        px = img.load()
        top, bot = (10, 62, 112), (3, 16, 44)
        for y in range(H):
            c = _blend(top, bot, y / H)
            for x in range(W):
                px[x, y] = c
        far = _rock_layer(
            [[(0, 150), (40, 128), (90, 142), (140, 124), (190, 140),
              (256, 130), (256, 192), (0, 192)]],
            (9, 32, 64), (20, 58, 96))
        img = Image.alpha_composite(img.convert("RGBA"), far)
        d = ImageDraw.Draw(img)
        d.rectangle([0, 172, W, H], fill=(64, 58, 34, 255))
        d.line([(0, 172), (W, 172)], fill=(96, 88, 52, 255), width=2)
        mid = _rock_layer(
            [[(18, 192), (30, 148), (66, 138), (96, 152), (104, 192)],
             [(150, 192), (164, 156), (196, 146), (224, 160),
              (230, 192)]],
            (14, 44, 52), (30, 76, 80))
        dm = ImageDraw.Draw(mid)
        _coral(dm, 62, 148, 1.0, [(214, 90, 160), (240, 130, 190),
                                 (170, 80, 220)], rnd)
        _coral(dm, 192, 158, 0.85, [(240, 140, 40), (250, 180, 60),
                                   (220, 90, 60)], rnd)
        _coral(dm, 40, 168, 0.8, [(90, 200, 160), (60, 170, 200)],
               rnd)
        img = Image.alpha_composite(img, mid)
        return img.convert("RGB")

    @staticmethod
    def _build_rays():
        img = Image.new("RGBA", (W + 16, H), (0, 0, 0, 0))
        d = ImageDraw.Draw(img)
        for x0, wdt in [(38, 16), (94, 26), (158, 13), (213, 20)]:
            d.polygon([(x0, 0), (x0 + wdt, 0), (x0 + wdt + 42, H),
                       (x0 + 30, H)], fill=(140, 200, 235, 26))
        return img

    @staticmethod
    def _build_foreground(rnd):
        fg = _rock_layer(
            [[(0, 192), (0, 132), (26, 142), (44, 166), (52, 192)],
             [(256, 192), (256, 150), (232, 158), (218, 178),
              (212, 192)]],
            (26, 16, 12), (58, 34, 22))
        d = ImageDraw.Draw(fg)
        _coral(d, 16, 140, 0.9, [(255, 90, 40), (255, 140, 30),
                                (230, 60, 90)], rnd)
        _coral(d, 240, 158, 0.8, [(255, 110, 60), (240, 80, 120)],
               rnd)
        return fg

    # -- the life --------------------------------------------------
    def _build_fish(self, density):
        if density not in DENSITIES:
            density = "lively"
        self._density = density
        school_n = {"quiet": 4, "lively": 6, "full": 9}[density]
        far_extra = {"quiet": 1, "lively": 2, "full": 3}[density]
        mid_sp = [YELLOW, RED, TANG, CLOWN, PURPLE, YELLOW]
        near_sp = [CLOWN, TANG, RED]
        mid_n = {"quiet": 2, "lively": 4, "full": 6}[density]
        near_n = {"quiet": 1, "lively": 2, "full": 3}[density]
        self._fish = {"far": [], "mid": [], "near": []}
        for i in range(school_n):
            self._fish["far"].append(_Fish(
                SILVER, "far", 16 + i * 15, 50 + (i % 3) * 7, 1, 0.9,
                1.2))
        far_cycle = [TANG, PURPLE, YELLOW]
        for i in range(far_extra):
            self._fish["far"].append(_Fish(
                far_cycle[i % 3], "far", 60 + i * 70,
                random.uniform(*BANDS["far"]), -1 if i % 2 else 1,
                0.75))
        for i in range(mid_n):
            self._fish["mid"].append(_Fish(
                mid_sp[i % len(mid_sp)], "mid", 24 + i * 38,
                random.uniform(*BANDS["mid"]), -1 if i % 2 else 1,
                0.85))
        for i in range(near_n):
            self._fish["near"].append(_Fish(
                near_sp[i % len(near_sp)], "near", 36 + i * 84,
                random.uniform(*BANDS["near"]), -1 if i % 2 else 1,
                0.82, 3.0))
        self.dot_count = sum(len(v) for v in self._fish.values())

    def _update_turtle(self):
        every = int(self.config.get("aq_turtle_s", 90))
        if self._turtle_x is None:
            if every > 0 and self._tick >= self._next_turtle:
                self._turtle_x = -100.0
            return
        self._turtle_x += 1.4
        if self._turtle_x > W + 4:
            self._turtle_x = None
            if every > 0:
                self._next_turtle = self._tick + int(
                    every / self.tick_s)

    def draw(self, ctx):
        self._tick += 1
        density = self.config.get("aq_fish", "lively")
        if density != self._density:
            self._build_fish(density)  # density edits apply live
        img = self._base.copy()
        if self.config.get("aq_rays", True):
            sway = int(4 * math.sin(self._tick * 0.01))
            rays = self._rays.crop((8 - sway, 0, 8 - sway + W, H))
            img = Image.alpha_composite(img.convert("RGBA"),
                                        rays).convert("RGB")
        d = ImageDraw.Draw(img)
        rnd = random.Random(1000 + self._tick // 3)
        for _ in range(46):  # caustic shimmer along the sand
            x = rnd.randint(4, W - 4)
            y = rnd.choice([170, 171, 173, 176, 180, 185])
            d.line([(x, y), (x + rnd.randint(2, 5), y)],
                   fill=(110, 160, 150), width=1)
        for f in self._fish["far"]:
            f.draw(img, self._tick)
        for f in self._fish["mid"]:
            f.draw(img, self._tick)
        self._update_turtle()
        if self._turtle_x is not None:
            ty = 44 + int(3 * math.sin(self._tick * 0.1))
            img.paste(self._turtle, (int(self._turtle_x), ty),
                      self._turtle)
        d = ImageDraw.Draw(img)
        for b in self._bubbles:
            b[1] -= 1 + b[2]
            if b[1] < 12:
                b[1] = 168 + random.randint(0, 10)
            bx = b[0] + int(2 * math.sin(self._tick * 0.3 + b[0]))
            r = b[2] + 1
            d.ellipse([bx - r, b[1] - r, bx + r, b[1] + r],
                      outline=(185, 225, 255))
            d.point((bx - 1, b[1] - 1), fill=(240, 250, 255))
        for f in self._fish["near"]:
            f.draw(img, self._tick)
        return Image.alpha_composite(img.convert("RGBA"),
                                     self._fg).convert("RGB")

    def admin_fields(self):
        return [
            {"key": "aq_fish", "label": "Fish", "type": "select",
             "options": list(DENSITIES)},
            {"key": "aq_turtle_s", "label": "Turtle (seconds "
             "between crossings)", "type": "number"},
            {"key": "aq_rays", "label": "Surface light rays",
             "type": "checkbox"},
        ]
