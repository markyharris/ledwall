"""Runtime configuration, kept OUTSIDE git's reach.

config.json lives beside the code but is listed in .gitignore, so a
git pull can never clobber the owner's settings (the ledmap v1 data.txt
lesson, and the LS Lite skip-worktree pattern, applied by design).
"""
import json
import os

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CONFIG_PATH = os.path.join(ROOT, "config.json")

DEFAULTS = {
    "module": "metar_map",
    "region": "CONUS",
    "rotate_regions": [],
    "rotate_s": 120,
    "home_airport": "KFLG",
    "dot_size": 2,
    "show_label": True,
    "show_clock": True,
    "show_icons": True,
    "icon_ts": True,
    "icon_sn": True,
    "icon_ra": True,
    "icon_fg": True,
    "icon_gr": True,
    "icon_anim": "fade",
    "brightness": 60,
    "refresh_s": 300,
    "splash_hold_s": 3.5,
    "night_mode": False,
    "night_brightness": 25,
    "night_start": "22:00",
    "night_end": "06:00",
    "pond_drop_s": 2.5,
    "pond_pebble_s": 30,
    "pond_relief": 70,
    "aq_fish": "lively",
    "aq_turtle_s": 90,
    "aq_rays": True,
    "sw_range_nm": 50,
    "sw_refresh_s": 30,
    "sw_lat": 35.1404,
    "sw_lon": -111.6694,
    "sw_label": "KFLG",
}


def parse_hhmm(value):
    """'22:00' (or '22') -> minutes since midnight, else None."""
    try:
        parts = str(value).strip().split(":")
        hour = int(parts[0])
        minute = int(parts[1]) if len(parts) > 1 else 0
        if 0 <= hour <= 23 and 0 <= minute <= 59:
            return hour * 60 + minute
    except (ValueError, IndexError):
        pass
    return None


def format_hhmm(minutes):
    return "%02d:%02d" % (minutes // 60, minutes % 60)


def load():
    cfg = dict(DEFAULTS)
    if os.path.exists(CONFIG_PATH):
        try:
            with open(CONFIG_PATH) as f:
                cfg.update(json.load(f))
        except Exception:
            pass  # a corrupt config must never stop the map booting
    return cfg


def save(cfg):
    tmp = CONFIG_PATH + ".tmp"
    with open(tmp, "w") as f:
        json.dump(cfg, f, indent=2, sort_keys=True)
    os.replace(tmp, CONFIG_PATH)
