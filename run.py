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


def effective_brightness(cfg, now=None):
    """Admin brightness, with the night override when night mode is on.
    The night window is the owner's night_start/night_end (local time,
    default 22:00-06:00; a window may wrap midnight or sit inside one
    day, and start == end disables it). Read fresh each tick so slider
    and window changes apply live, without a restart."""
    if cfg.get("night_mode"):
        t = time.localtime(now)
        mins = t.tm_hour * 60 + t.tm_min
        start = config_mod.parse_hhmm(cfg.get("night_start"))
        end = config_mod.parse_hhmm(cfg.get("night_end"))
        if start is None:
            start = 22 * 60
        if end is None:
            end = 6 * 60
        if start < end:
            night = start <= mins < end
        elif start > end:
            night = mins >= start or mins < end
        else:
            night = False
        if night:
            return cfg.get("night_brightness", 25)
    return cfg.get("brightness", 60)


def apply_live_config(module, state, live):
    """Adopt a freshly loaded config in the running loop. Settings go
    straight to the module; a region (or module) change rebuilds the
    module for the new view on the spot - no restart, the wall just
    switches (Mark's ask). Returns (module, switched)."""
    if live.get("region") != state.region or \
            live.get("module") != state.module_name:
        new_module = MODULES[live["module"]]()
        new_module.setup(live)
        state.module_name = new_module.name
        state.region = live["region"]
        return new_module, True
    module.config = live
    return module, False


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
            cfg = config_mod.load()
            module, switched = apply_live_config(module, state, cfg)
            if switched:
                next_fetch = 0.0  # fetch for the new view right away
            if time.time() >= next_fetch:
                module.refresh_data()
                state.stations = len(module.metars)
                state.last_fetch = time.time()
                next_fetch = time.time() + cfg["refresh_s"]
            display.set_brightness(effective_brightness(cfg))
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
