# LEDWALL

A from-scratch rebuild of the big LED METAR map: 12× 64×64 HUB75 panels
(4 chains × 3 parallel rows, 256×192) on a Raspberry Pi with the
Adafruit RGB Matrix HAT, driven by the hzeller rpi-rgb-led-matrix
library. The v1 map (`markyharris/ledmap`) is untouched and remains the
reference and the rollback.

## What it shows

- **Flight-category dots** in the classic colours — VFR green, MVFR
  blue, IFR red, LIFR magenta, no-category grey — plotted by priority
  thinning so the worst weather wins a crowded pixel.
- **Regions**: the whole CONUS, or any US state zoomed to fill the
  wall (states are generated from the boundary data; a state view
  clips to its own outline and shows only its own airports). Pick 2+
  regions in the admin and the wall **rotates** through them, each
  for a configurable number of seconds; every cycle leads with the
  main Region view (the whole picture, for context) before the
  picked zooms. Region changes — manual or rotating — apply live,
  no restart.
- **Weather icons** over the stations reporting them — thunderstorm,
  snow, rain/drizzle, fog/mist, hail — each kind individually
  toggleable, with a fade (4-second breathing cycle, hot peak), blink,
  or steady animation.
- **Lightning entrance flash**: a thunderstorm station that newly
  appears paints its bolt double-size in pure white for half a second,
  then settles into the normal yellow fade.
- **Home airport flag**: a gently pulsing amber pennant planted on
  the owner's home field (a station ID in the admin; KFLG ships as
  the default), drawn over its dot in any view that contains it.
- **Region switches melt**: a ~1-second crossfade replaces the jump
  cut, for manual changes and rotation steps alike.
- **Region label** (CONUS, ARIZONA, …) auto-placed into the emptiest
  space on the map at every refresh; it moves if weather fills its
  spot, and it never slides under the clock.
- **Zulu clock** (HH:MMZ, UTC) in the top-right corner.
- **Night mode**: dims to a separate brightness during the owner's
  chosen night hours (default 22:00–06:00).
- **Splash screen** at boot with the admin page address.

## Design

- **Everything renders in PIL** to a finished frame, pushed to the
  panels with `SetImage`. Geography (landmass + boundaries) is
  rendered once per region and cached; only the weather layer changes
  per refresh.
- **Modules, painter-clock style.** `modules/` holds one full-screen
  behaviour per file behind a small interface (setup / refresh_data /
  draw, tick-driven for animation). `metar_map` is module #1.
- **Settings live in `config.json`**, which is git-ignored so a pull
  can never clobber them (the v1 data.txt lesson).

```
run.py            entry point: splash, admin thread, update checker,
                  fetch/draw loop with a crash guard (last frame
                  stays up, retry in 30 s)
preview.py        render frames to PNG without hardware
core/
  geo.py          equirectangular projection (cos-lat corrected)
  regions.py      region presets: CONUS + every US state, generated
  metar.py        aviationweather.gov JSON fetcher (see HOWTO)
  render.py       base maps, dots, icons, label, clock, legend
  display.py      MatrixDisplay (hzeller) / FileDisplay (previews)
  config.py       config.json defaults, load, atomic save
  updater.py      git-based update check / apply
  state.py        shared status for the admin page
  splash.py       boot splash
modules/
  base.py         module contract
  metar_map.py    the weather map module
admin/
  app.py          Flask admin on :5000 (painter-clock v24 pattern)
data/
  us-states.json    state boundaries (PublicaMundi, public domain)
  us_stations.json  the ~2,950 US station ids fetched each cycle
```

## Admin page

`http://<pi>:5000` — live frame preview, status, and every setting:
region, dot size (1 LED or 2×2), weather icons per kind, icon
animation, region label, Zulu clock, brightness, night mode, refresh
interval, plus Check for update / Update now / Reboot. `/api/status`
serves the Project Finder fingerprint (`"device": "ledwall"`); the
recognizer lives in `project_finder.py`. A legend of the categories
and icons is served at `/legend.png` and shown on the admin page.

## Configuration

Defaults: region CONUS, 2×2 dots, icons on with fade animation, label
and clock on, brightness 60, refresh 300 s, night mode off at 25
(night hours 22:00–06:00 when enabled).

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
bindings):

    python3 run.py

Install and operations: see **HOWTO.md**.
