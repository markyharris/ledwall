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
VERSION = "v2.0-dev"


def _font(path, size):
    try:
        return ImageFont.truetype(path, size)
    except Exception:
        return ImageFont.load_default()


def _centred(d, y, text, font, fill):
    w = d.textlength(text, font=font)
    d.text(((CANVAS_W - w) / 2, y), text, font=font, fill=fill)


def _fit_font(path, text, start, max_w):
    """Largest size <= start at which the text fits max_w pixels wide."""
    probe = ImageDraw.Draw(Image.new("RGB", (1, 1)))
    size = start
    while size > 10:
        f = _font(path, size)
        if probe.textlength(text, font=f) <= max_w:
            return f
        size -= 2
    return _font(path, size)


def render_splash(base_img, ip, port=5000):
    img = base_img.point(lambda v: v // 6)  # dim the map to a backdrop
    # Title: fitted to a comfortable width with a slight vertical
    # stretch. Full-width (248px) at 1.5x read as huge on the wall,
    # and 1.25x was not visibly smaller (Mark) - so the word now sits
    # narrower AND shorter, with margins on both sides.
    font = _fit_font(FONT_BOLD, TITLE, 64, 216)
    layer = Image.new("RGBA", (CANVAS_W, 84), (0, 0, 0, 0))
    ld = ImageDraw.Draw(layer)
    w = ld.textlength(TITLE, font=font)
    ld.text(((CANVAS_W - w) / 2, 0), TITLE, font=font,
            fill=(30, 144, 255, 255))
    layer = layer.crop(layer.getbbox())
    layer = layer.resize((layer.width, int(layer.height * 1.1)),
                         Image.LANCZOS)
    img.paste(layer, ((CANVAS_W - layer.width) // 2, 16), layer)
    d = ImageDraw.Draw(img)
    _centred(d, 108, "Admin page:", _font(FONT, 12), (140, 150, 160))
    _centred(d, 126, "http://%s:%d" % (ip, port), _font(FONT_BOLD, 16),
             (0, 255, 128))
    _centred(d, 152, VERSION, _font(FONT, 10), (110, 120, 130))
    return img
