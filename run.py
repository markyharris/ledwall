"""LEDWALL v2 entry point.

Boot sequence: splash (with the admin address) -> admin server up ->
module loop: fetch data, draw frame, push to panels, repeat on the
module's refresh interval. An hourly background thread checks git for
updates and only flags them in /api/status (Update now is the owner's
button press, per the standing build rules).
"""
import os
import sys
import threading
import time
import traceback

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from ledwall.admin.app import local_ip, serve
from ledwall.core import config as config_mod
from ledwall.core import splash, updater
from ledwall.core.display import open_display
from ledwall.core.regions import REGIONS
from ledwall.core.state import AppState
from ledwall.modules.metar_map import MetarMapModule

MODULES = {"metar_map": MetarMapModule}


def update_checker(state):
    while True:
        state.update = updater.check_update()
        time.sleep(3600)


def effective_brightness(cfg):
    """Admin brightness, with the night override when night mode is on
    (22:00-06:00 local). Read fresh each tick so slider changes apply
    live, without a restart."""
    if cfg.get("night_mode"):
        hour = time.localtime().tm_hour
        if hour >= 22 or hour < 6:
            return cfg.get("night_brightness", 25)
    return cfg.get("brightness", 60)


def main():
    cfg = config_mod.load()
    state = AppState()
    state.version = updater.current_version()
    display = open_display(cfg["brightness"])

    module = MODULES[cfg["module"]]()
    module.setup(cfg)
    state.module_name = module.name
    state.region = cfg["region"]

    display.show(splash.render_splash(module.base, local_ip()), "splash")

    threading.Thread(target=serve, args=(state, list(REGIONS.keys())),
                     daemon=True).start()
    threading.Thread(target=update_checker, args=(state,), daemon=True).start()

    next_fetch = 0.0
    tick = 0
    while True:
        try:
            if time.time() >= next_fetch:
                module.refresh_data()
                state.stations = len(module.metars)
                state.last_fetch = time.time()
                next_fetch = time.time() + cfg["refresh_s"]
            display.set_brightness(
                effective_brightness(config_mod.load()))
            frame = module.draw(tick)
            state.frame = frame
            state.dots = module.dot_count
            display.show(frame, "weather")
            delay = getattr(module, "tick_s", 0) or cfg["refresh_s"]
        except Exception:
            # A bad cycle must never wedge or kill the wall (the v1
            # failure Mark worked around with a nightly reboot): keep
            # the last good frame on the panels, log the cause, and
            # retry soon instead of waiting out the full interval.
            traceback.print_exc()
            delay = 30
        tick += 1
        time.sleep(delay)


if __name__ == "__main__":
    main()
