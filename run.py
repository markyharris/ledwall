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

from PIL import Image

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from ledwall.admin.app import local_ip, serve
from ledwall.core import config as config_mod
from ledwall.core import splash, updater
from ledwall.core.display import open_display
from ledwall.core.geo import CANVAS_H, CANVAS_W
from ledwall.core.regions import REGIONS, station_counts
from ledwall.core.state import AppState
from ledwall.modules.aquarium import AquariumModule
from ledwall.modules.base import Module
from ledwall.modules.aurora import AuroraModule
from ledwall.modules.daynight import DayNightModule
from ledwall.modules.iss import IssModule
from ledwall.modules.launches import LaunchesModule
from ledwall.modules.metar_map import MetarMapModule
from ledwall.modules.metar_world import MetarWorldModule
from ledwall.modules.quakes import QuakesModule
from ledwall.modules.radar import RadarModule
from ledwall.modules.skywatch import SkywatchModule
from ledwall.modules.sunmoon import SunMoonModule
from ledwall.modules.tonight import TonightModule

MODULES = {"metar_map": MetarMapModule,
           "aquarium": AquariumModule, "skywatch": SkywatchModule,
           "tonight": TonightModule, "sunmoon": SunMoonModule,
           "iss": IssModule, "quakes": QuakesModule,
           "radar": RadarModule, "aurora": AuroraModule,
           "launches": LaunchesModule,
           "metar_world": MetarWorldModule,
           "daynight": DayNightModule}


def update_checker(state):
    while True:
        state.update = updater.check_update()
        time.sleep(3600)


def _run_fetch(module, state, flag):
    """Fetch worker: refresh_data runs on its own thread so a slow
    fetch (a world view pulls thousands of stations) never freezes
    the wall's animation; the new data swaps in when it lands. Errors
    are logged, never raised into the loop."""
    try:
        module.refresh_data()
        state.stations = len(getattr(module, "metars", {}))
        state.last_fetch = time.time()
    except Exception:
        traceback.print_exc()
    finally:
        flag["busy"] = False


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
    """Which region belongs on the wall right now. With regions picked
    for rotation, the cycle always leads with the single Region
    setting - the whole-region overview, for context (Mark's ask) -
    then the picked regions, each shown for rotate_s seconds. With
    nothing picked, the single Region setting rules. `view` carries
    the rotation position between ticks."""
    picks = [r for r in live.get("rotate_regions") or []
             if r in REGIONS]
    if not picks:
        view["rotation"] = None
        return live["region"]
    sequence = [live["region"]] + [r for r in picks
                                    if r != live["region"]]
    if len(sequence) < 2:
        view["rotation"] = None
        return live["region"]
    if view.get("rotation") != tuple(sequence):
        view["rotation"] = tuple(sequence)
        # A new cycle takes over from the current view when it can: if
        # this region is in the cycle it keeps its full interval;
        # otherwise the cycle starts at the overview right away.
        view["deadline"] = now + max(10, int(live.get("rotate_s", 120))) \
            if state.region in sequence else 0.0
    if state.region in sequence and now < view["deadline"]:
        return state.region
    idx = (sequence.index(state.region) + 1) % len(sequence) \
        if state.region in sequence else 0
    view["deadline"] = now + max(10, int(live.get("rotate_s", 120)))
    return sequence[idx]


def desired_module(state, live, view, now):
    """Which module belongs on the wall right now. Module rotation
    is a plain checkbox affair, like the LED ticker's subjects
    (Mark's call): a master "Rotate modules" switch plus one
    checkbox per module, and the cycle is exactly the checked
    set, in admin list order, each module shown for
    module_rotate_s seconds. With the switch off - or fewer than
    two modules checked - the "Show on the wall" module rules.
    `view` carries the rotation position between ticks, under
    its own keys so the region rotation's state is never
    disturbed."""
    base = live.get("module", "metar_map")
    if base not in MODULES:
        base = "metar_map"
    picks = [m for m in MODULES
             if m in (live.get("rotate_modules") or [])]
    if not live.get("module_rotate_on") or len(picks) < 2:
        view["mod_rotation"] = None
        return base
    sequence = picks
    dwell = max(10, int(live.get("module_rotate_s", 120)))
    if view.get("mod_rotation") != tuple(sequence):
        view["mod_rotation"] = tuple(sequence)
        # A new cycle takes over from the current view when it can:
        # if this module is in the cycle it keeps its full interval;
        # otherwise the cycle starts at the first checked module.
        view["mod_deadline"] = now + dwell \
            if state.module_name in sequence else 0.0
    if state.module_name in sequence and now < view["mod_deadline"]:
        return state.module_name
    idx = (sequence.index(state.module_name) + 1) % len(sequence) \
        if state.module_name in sequence else 0
    view["mod_deadline"] = now + dwell
    return sequence[idx]


FADE_S = 0.9  # seconds for a region-switch crossfade


def fade_frame(old, new, t):
    """Crossfade between two frames, t in [0, 1], smoothstep-eased so
    a region switch melts instead of jumping (Mark's ask)."""
    t = min(1.0, max(0.0, t))
    return Image.blend(old, new, t * t * (3 - 2 * t))


def apply_live_config(module, state, live, view, now):
    """Adopt a freshly loaded config in the running loop. Settings go
    straight to the module; a region change - the owner's edit, or the
    rotation arriving at its next region - rebuilds the module for the
    new view on the spot, no restart (Mark's ask). Already-fetched
    data carries over when the new view's station list is covered by
    the old fetch (US views share one national list; a world view
    covers its countries) - then the switch is a pure re-projection.
    Otherwise the data is dropped and the loop fetches for the new
    view at once. Returns (module, switched).
    """
    # Module rotation is the outer loop: it decides which module
    # is up at all. Region rotation is a weather-map concern only,
    # consulted when the map is the module that belongs up. Other
    # modules have no regions, and rebuilding one on a region tick
    # wipes its live state - Skywatch lost its whole traffic
    # picture to a rotation rebuild during a network stall
    # (Nov 27): the stale picture it should have kept became an
    # empty WAITING scope.
    want_module = desired_module(state, live, view, now)
    want = state.region
    if want_module == "metar_map":
        want = desired_region(state, live, view, now)
    if want_module != state.module_name or want != state.region:
        # A rotating wall revisits every module all day, so a
        # module's fetched data survives the switch: snapshot
        # the outgoing module's PERSIST attributes, and restore
        # the incoming one's from its last visit. Without this,
        # every visit started from an empty module and a fresh
        # fetch - the long blank delay on every rotation lap.
        saved = view.setdefault("saved", {})
        if getattr(module, "PERSIST", None):
            saved[state.module_name] = {
                a: getattr(module, a) for a in module.PERSIST
                if hasattr(module, a)}
        new_module = MODULES.get(want_module, MetarMapModule)()
        setup_cfg = dict(live)
        setup_cfg["region"] = want
        new_module.setup(setup_cfg)
        carried = getattr(module, "metars", None)
        if carried:
            want_ids = set(getattr(new_module, "station_ids", []))
            covered = want_ids <= set(getattr(module, "station_ids",
                                              [])) or \
                want_ids <= set(carried.keys())
            if not covered:
                carried = None  # the old fetch never asked for these
        if carried:
            new_module.metars = carried
            new_module._dirty = True
        if new_module.name in saved:
            for attr, value in saved[new_module.name].items():
                setattr(new_module, attr, value)
        state.module_name = new_module.name
        state.region = want
        return new_module, True
    module.config = live
    return module, False


def _next_fetch_after_switch(view, module, cfg, now):
    """When the module that just came up should next fetch. Its
    restored data is already on screen, so the fetch falls due
    one cadence after its last one; a module with nothing
    restored (first visit since boot) - or data older than its
    cadence - fetches at once, as switches always did."""
    last = view.get("fetch_at", {}).get(module.name, 0.0)
    cadence = getattr(module, "fetch_s", None) or cfg["refresh_s"]
    restored = bool(view.get("saved", {}).get(module.name)) \
        or getattr(module, "metars", None)
    if restored and last and now - last < cadence:
        return last + cadence
    return 0.0


def _warm_up_rotation(cfg, view, fetching, state):
    """Boot warm-up: while the first module displays, fetch the
    other rotation modules' data in the background, in cycle
    order starting with the next one up, and bank it in the
    persistence store - so each module's first turn opens with
    data in hand instead of a fetch (the one slow case the
    persistence fix could not cover). Yields to the loop's own
    fetches: the module on the wall always has the network
    first. Computed modules (nothing to fetch) are skipped."""
    try:
        picks = [m for m in MODULES
                 if m in (cfg.get("rotate_modules") or [])]
        if not cfg.get("module_rotate_on") or len(picks) < 2:
            return
        cur = state.module_name
        if cur in picks:
            i = picks.index(cur)
            picks = picks[i + 1:] + picks[:i]
        for key in picks:
            cls = MODULES.get(key)
            if cls is None or \
                    cls.refresh_data is Module.refresh_data:
                continue
            while fetching["busy"]:
                time.sleep(0.5)
            mod = cls()
            mod.setup(dict(cfg))
            try:
                mod.refresh_data()
            except Exception:
                traceback.print_exc()
                continue
            entry = {a: getattr(mod, a)
                     for a in getattr(mod, "PERSIST", ())
                     if hasattr(mod, a)}
            if getattr(mod, "metars", None):
                entry["metars"] = mod.metars
            if entry:
                view.setdefault("saved", {})[key] = entry
                view.setdefault("fetch_at", {})[key] = time.time()
    except Exception:
        traceback.print_exc()


def main():
    cfg = config_mod.load()
    state = AppState()
    state.version = updater.current_version()
    display = open_display(cfg["brightness"])

    module = MODULES.get(cfg.get("module"), MetarMapModule)()
    module.setup(cfg)
    state.module_name = module.name
    state.region = cfg["region"]

    base = getattr(module, "base", None)
    if base is None:  # a module with no map of its own
        base = Image.new("RGB", (CANVAS_W, CANVAS_H))
    display.show(splash.render_splash(base, local_ip(wait_s=30)),
                 "splash")

    # Regions with no reporting airports of their own (Palestine,
    # Western Sahara...) are left off the admin's region pickers;
    # the map machinery itself is untouched.
    try:
        state.empty_regions = {
            k for k, n in station_counts().items() if n == 0}
    except Exception:
        state.empty_regions = set()

    threading.Thread(target=serve,
                     args=(state, list(REGIONS.keys()),
                           [(key, m.title) for key, m in
                            MODULES.items()]),
                     daemon=True).start()
    threading.Thread(target=update_checker, args=(state,), daemon=True).start()

    # Hold the splash before the loop's first frame overwrites it:
    # it carries the admin address, and the standing rule is that
    # the owner can read where to manage the device off the wall
    # after a boot. The admin is already serving during the hold,
    # and the first fetch fires the moment the loop starts. (The
    # hold was missing until Nov 27 - the splash rendered and was
    # replaced within a blink, so no boot ever visibly showed it.)
    try:
        hold = float(cfg.get("splash_hold_s", 10))
    except (TypeError, ValueError):
        hold = 10
    if hold > 0:
        time.sleep(hold)

    next_fetch = 0.0
    tick = 0
    view = {}
    last_frame = None
    fade_from = None
    fade_start = 0.0
    fade_pending = None
    fetching = {"busy": False}
    threading.Thread(target=_warm_up_rotation,
                     args=(cfg, view, fetching, state),
                     daemon=True).start()
    while True:
        try:
            cfg = config_mod.load()
            module, switched = apply_live_config(
                module, state, cfg, view, time.time())
            if switched and last_frame is not None:
                fade_pending = last_frame
            if switched:
                next_fetch = _next_fetch_after_switch(
                    view, module, cfg, time.time())
            if time.time() >= next_fetch and not fetching["busy"]:
                fetching["busy"] = True
                view.setdefault("fetch_at", {})[module.name] = \
                    time.time()
                threading.Thread(target=_run_fetch,
                                 args=(module, state, fetching),
                                 daemon=True).start()
                # A module with its own data cadence (Skywatch polls
                # its feed every few seconds) sets fetch_s; the rest
                # follow the config's refresh interval.
                next_fetch = time.time() + (
                    getattr(module, "fetch_s", None)
                    or cfg["refresh_s"])
            display.set_brightness(effective_brightness(cfg))
            frame = module.draw(tick)
            if fade_pending is not None:
                # Start the fade clock only now that the new frame
                # exists. Arming it at the switch decision let a slow
                # first draw (Alaska's outline is the priciest rebuild
                # on the wall) burn the whole 0.9 s window before the
                # first blend was ever evaluated - the melt became a
                # jump cut on that one transition.
                fade_from, fade_start = fade_pending, time.time()
                fade_pending = None
            if fade_from is not None:
                t = (time.time() - fade_start) / FADE_S
                if t >= 1.0:
                    fade_from = None
                else:
                    frame = fade_frame(fade_from, frame, t)
            state.frame = frame
            state.dots = getattr(module, "dot_count", 0)
            display.show(frame, "weather")
            last_frame = frame
            delay = 0.1 if fade_from is not None else \
                (getattr(module, "tick_s", 0) or cfg["refresh_s"])
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
