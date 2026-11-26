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


def main():
    cfg = config_mod.load()
    state = AppState()
    state.version = updater.current_version()
    display = open_display()

    module = MODULES[cfg["module"]]()
    module.setup(cfg)
    state.module_name = module.name
    state.region = cfg["region"]

    display.show(splash.render_splash(module.base, local_ip()), "splash")

    threading.Thread(target=serve, args=(state, list(REGIONS.keys())),
                     daemon=True).start()
    threading.Thread(target=update_checker, args=(state,), daemon=True).start()

    while True:
        try:
            module.refresh_data()
            frame = module.draw(None)
            state.frame = frame
            state.stations = len(module.metars)
            state.dots = module.dot_count
            state.last_fetch = time.time()
            display.show(frame, "weather")
            delay = cfg["refresh_s"]
        except Exception:
            # A bad cycle must never wedge or kill the wall (the v1
            # failure Mark worked around with a nightly reboot): keep
            # the last good frame on the panels, log the cause, and
            # retry soon instead of waiting out the full interval.
            traceback.print_exc()
            delay = 30
        time.sleep(delay)


if __name__ == "__main__":
    main()
