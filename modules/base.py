"""Module interface - the painter-clock 'face' pattern for the big map.

A module owns one full-screen behaviour. It gets:
  * draw(ctx)      -> a finished PIL frame (called when its data refreshes
                      and, for animated modules, on its animation tick)
  * refresh_s      -> how often its underlying data is re-fetched
  * admin_fields() -> config fields the admin page renders for it

The core owns the panels, the clock, the web admin and module rotation;
modules never touch hardware directly.
"""


class Module:
    name = "base"
    title = "Base module"
    refresh_s = 300
    fetch_s = None  # per-module fetch cadence; None = the config's
    #                 refresh_s (the weather map's setting) rules
    tick_s = 0  # >0: draw() is called every tick_s seconds with an
    # incrementing tick counter (animation); 0 = draw only on refresh
    dot_count = 0  # items plotted, for the admin status line; the
    # main loop reads it after every draw, so it must exist on
    # every module (the Launch Board shipped without it and
    # wedged the wall on its splash - Nov 27)

    def setup(self, config):
        self.config = config

    def refresh_data(self):
        """Fetch fresh data, on the loop's background thread. Modules
        with nothing to fetch (Day & Night) inherit this no-op."""

    def draw(self, ctx):
        raise NotImplementedError

    def admin_fields(self):
        return []
