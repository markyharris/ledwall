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


def desired_region(state, live, view, now):
    """Which region belongs on the wall right now. With 2+ regions in
    the rotation list, the wall cycles through them, each shown for
    rotate_s seconds; otherwise the single Region setting rules.
    `view` carries the rotation position between ticks."""
    rotation = [r for r in live.get("rotate_regions") or []
                if r in REGIONS]
    if len(rotation) < 2:
        view["rotation"] = None
        return live["region"]
    if view.get("rotation") != tuple(rotation):
        view["rotation"] = tuple(rotation)
        # A new list takes over from the current view when it can: if
        # this region is in the list it keeps its full interval;
        # otherwise the list starts at its first entry right away.
        view["deadline"] = now + max(10, int(live.get("rotate_s", 120))) \
            if state.region in rotation else 0.0
    if state.region in rotation and now < view["deadline"]:
        return state.region
    idx = (rotation.index(state.region) + 1) % len(rotation) \
        if state.region in rotation else 0
    view["deadline"] = now + max(10, int(live.get("rotate_s", 120)))
    return rotation[idx]


def apply_live_config(module, state, live, view, now):
    """Adopt a freshly loaded config in the running loop. Settings go
    straight to the module; a region change - the owner's edit, or the
    rotation arriving at its next region - rebuilds the module for the
    new view on the spot, no restart (Mark's ask). The fetched data is
    national and identical for every region, so it carries over and
    the new view is just a re-projection. Returns (module, switched).
    """
    want = desired_region(state, live, view, now)
    if live.get("module") != state.module_name or want != state.region:
        new_module = MODULES[live["module"]]()
        carried = getattr(module, "metars", None)
        setup_cfg = dict(live)
        setup_cfg["region"] = want
        new_module.setup(setup_cfg)
        if carried:
            new_module.metars = carried
            new_module._dirty = True
        state.module_name = new_module.name
        state.region = want
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
    view = {}
    while True:
        try:
            cfg = config_mod.load()
            module, switched = apply_live_config(
                module, state, cfg, view, time.time())
            if switched and not getattr(module, "metars", None):
                next_fetch = 0.0  # nothing carried over: fetch at once
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
