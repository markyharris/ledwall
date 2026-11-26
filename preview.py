"""Dev preview: build the base map, fetch live METARs, render frames.

Run from the ledwall folder:  python3 preview.py
Writes previews/base_3x.png, previews/weather_3x.png, previews/splash_3x.png
(plus native-size versions) - exactly what the panels would show.
"""
import json
import os
import sys
from collections import Counter

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from ledwall.core import render, metar, splash
from ledwall.core.display import FileDisplay
from ledwall.core.regions import get_region

HERE = os.path.dirname(os.path.abspath(__file__))


def main():
    region = get_region("CONUS")
    disp = FileDisplay()

    base = render.build_base(region)
    disp.show(base, "base")
    print("base map rendered")

    with open(os.path.join(HERE, "data", "us_stations.json")) as f:
        ids = json.load(f)
    print("fetching METARs for %d stations..." % len(ids))
    metars = metar.fetch_metars(ids)
    cats = Counter(r.get("fltCat") for r in metars.values())
    print("reports:", len(metars), dict(cats))

    frame, dots = render.plot_weather(base, metars, region)
    disp.show(frame, "weather")
    print("weather frame: %d dots after thinning" % dots)

    disp.show(splash.render_splash(base, "192.168.1.50"), "splash")
    print("splash rendered")


if __name__ == "__main__":
    main()
