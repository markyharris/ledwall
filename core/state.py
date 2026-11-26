"""Shared runtime state between the display loop and the admin server."""


class AppState:
    def __init__(self):
        self.frame = None          # latest PIL frame shown on the panels
        self.module_name = ""
        self.region = ""
        self.stations = 0          # reports in the current frame
        self.dots = 0              # dots placed after thinning
        self.last_fetch = None     # epoch seconds of last data refresh
        self.update = {"available": None, "behind": None, "error": "not checked"}
        self.version = "dev"
