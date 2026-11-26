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


class MatrixDisplay:
    """Pi display: Adafruit RGB Matrix HAT + RTC driving 4x3 64x64 panels."""

    def __init__(self, brightness=60, gpio_slowdown=4):
        from rgbmatrix import RGBMatrix, RGBMatrixOptions
        options = RGBMatrixOptions()
        options.rows = 64
        options.cols = 64
        options.chain_length = 4
        options.parallel = 3
        options.hardware_mapping = "adafruit-hat-pwm"
        options.gpio_slowdown = gpio_slowdown
        options.brightness = brightness
        self.matrix = RGBMatrix(options=options)

    def show(self, image, name=None):
        self.matrix.SetImage(image)


def open_display():
    try:
        return MatrixDisplay()
    except Exception:
        return FileDisplay()
