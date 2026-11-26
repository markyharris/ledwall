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

    def setup(self, config):
        self.config = config

    def draw(self, ctx):
        raise NotImplementedError

    def admin_fields(self):
        return []
