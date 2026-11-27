"""Display output: the real matrix on the Pi, PNG previews elsewhere.

Frames are finished PIL images. On the Pi they are pushed to the panels
with SetImage; anywhere else (dev machine, bench) they are written to
previews/ so the exact frame the panels would show can be eyeballed.
"""
import os

from .geo import CANVAS_W, CANVAS_H

PREVIEW_DIR = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "previews")


class FileDisplay:
    """Dev display: saves each frame as a PNG (native size + 3x view)."""

    def __init__(self):
        os.makedirs(PREVIEW_DIR, exist_ok=True)
        self._n = 0

    def show(self, image, name=None):
        self._n += 1
        name = name or "frame_%03d" % self._n
        image.save(os.path.join(PREVIEW_DIR, name + ".png"))
        big = image.resize((CANVAS_W * 3, CANVAS_H * 3))
        big.save(os.path.join(PREVIEW_DIR, name + "_3x.png"))
        return name

    def set_brightness(self, pct):
        pass  # previews stay full-bright so they remain legible


class MatrixDisplay:
    """Pi display: Adafruit RGB Matrix HAT + RTC driving 4x3 64x64 panels."""

    def __init__(self, brightness=60, gpio_slowdown=4):
        from rgbmatrix import RGBMatrix, RGBMatrixOptions
        options = RGBMatrixOptions()
        options.rows = 64
        options.cols = 64
        options.chain_length = 4
        options.parallel = 3
        options.hardware_mapping = "regular"  # proven on Mark's HAT (v1 uses it)
        options.gpio_slowdown = gpio_slowdown
        options.brightness = brightness
        # The hzeller library drops the process to the 'daemon' user
        # after GPIO setup (that is why v1's map runs as daemon). In a
        # single-process app like this one the drop also disowns the
        # admin server and the module loop, which then cannot write
        # config.json or the base-map cache into the pi-owned checkout.
        # Keep root: this Pi runs only Mark's code. (Bench find,
        # Nov 2026 - 'sudo whoami' prints root, yet saves failed.)
        try:
            options.drop_privileges = False
        except Exception:
            pass
        self.matrix = RGBMatrix(options=options)

    def show(self, image, name=None):
        self.matrix.SetImage(image)

    def set_brightness(self, pct):
        try:
            self.matrix.brightness = int(pct)
        except Exception:
            pass


def open_display(brightness=60):
    try:
        return MatrixDisplay(brightness=brightness)
    except Exception:
        return FileDisplay()
