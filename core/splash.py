"""Boot splash: project title over a dimmed map, admin address up front.

Shown from power-up until the first weather frame is ready, and the
admin IP stays on screen long enough to read (standing rule: a display
device announces its admin address after joining Wi-Fi).
"""
from PIL import Image, ImageDraw, ImageFont

from .geo import CANVAS_W, CANVAS_H

FONT_BOLD = "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"
FONT = "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"

TITLE = "LEDWALL"
SUBTITLE = "Live METAR Weather"
VERSION = "v2.0-dev"


def _font(path, size):
    try:
        return ImageFont.truetype(path, size)
    except Exception:
        return ImageFont.load_default()


def _centred(d, y, text, font, fill):
    w = d.textlength(text, font=font)
    d.text(((CANVAS_W - w) / 2, y), text, font=font, fill=fill)


def render_splash(base_img, ip, port=5000):
    img = base_img.point(lambda v: v // 6)  # dim the map to a backdrop
    d = ImageDraw.Draw(img)
    _centred(d, 34, TITLE, _font(FONT_BOLD, 40), (255, 176, 0))
    _centred(d, 84, SUBTITLE, _font(FONT, 14), (200, 210, 220))
    _centred(d, 128, "Admin page:", _font(FONT, 12), (140, 150, 160))
    _centred(d, 146, "http://%s:%d" % (ip, port), _font(FONT_BOLD, 15),
             (0, 255, 128))
    _centred(d, 172, VERSION, _font(FONT, 10), (110, 120, 130))
    return img
