# LEDWALL v2

A from-scratch rebuild of the big LED METAR map (12x 64x64 HUB75 panels,
256x192, Raspberry Pi + Adafruit RGB Matrix HAT + RTC). The v1 code in
the `ledmap` repo is untouched and remains the documentation of the
original build.

## Design

- **Everything renders in PIL** to a finished frame, pushed to the panels
  with `SetImage`. Geography (landmass + boundaries) is rendered once per
  region and cached; only the weather layer changes per refresh.
- **Modules, painter-clock style.** `modules/` holds one full-screen
  behaviour per file behind a small interface (draw / refresh_s /
  admin_fields). `metar_map` is module #1. The core owns the panels, the
  clock, the admin server and module rotation.
- **Classic flight-category colours**, with weather icons overlaid for
  significant weather (phase 2) and a lightning flash on thunderstorm
  stations (phase 2).
- **Regions** are presets (bounding box + boundary dataset + density
  rule) in `core/regions.py`. CONUS ships in phase 1; world regions land
  in phase 3 with Natural Earth boundary data and the OurAirports list.
- **Settings live in `config.json`**, which is git-ignored so a pull can
  never clobber them (the v1 data.txt lesson).

## Standing build rules honoured

- Admin page in the painter-clock v24 pattern: sliders with live
  readouts, project icon as favicon and beside the title, colour-coded
  sections, every action returns to the admin page.
- Splash screen shows the admin IP after boot.
- Hourly git update *check* that only flags; "Update now" is a button.
- `/api/status` JSON fingerprint for Project Finder.
- Rehoming on the Pi via Comitup (installed at deploy time).

## Run it

Dev (renders PNG previews into `previews/`):

    python3 preview.py

On the Pi (needs `flask`, `pillow`, and the rpi-rgb-led-matrix Python
bindings; runs as a systemd service in production):

    python3 run.py

Admin page: http://<pi-ip>:5000 - Status, Display, Weather Map and
System sections; Check for updates / Update now / Reboot included.
