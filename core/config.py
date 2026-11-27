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
    "dot_size": 2,
    "show_icons": True,
    "icon_ts": True,
    "icon_sn": True,
    "icon_ra": True,
    "icon_fg": True,
    "icon_gr": True,
    "icon_anim": "fade",
    "brightness": 60,
    "refresh_s": 300,
    "night_mode": False,
    "night_brightness": 25,
}


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
