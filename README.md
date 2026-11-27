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
- **Regions**: 232 of them. The whole CONUS, any US state, the whole
  WORLD, EUROPE, or any country on Earth zoomed to fill the wall —
  states and countries are generated from the boundary data, and a
  zoomed view clips to its own outline and shows only its own
  airports. World stations are the ~7,750 METAR reporters
  aviationweather.gov itself carries, selected per region. Pick
  regions in the admin and the wall **rotates** through them, each
  for a configurable number of seconds; every cycle leads with the
  main Region view (the whole picture, for context) before the
  picked zooms — a world tour is CONUS, then Europe, then Japan…
  Region changes — manual or rotating — apply live, no restart.
  Fetches run on a background thread, so even a world fetch (26 API
  chunks) never freezes the wall's animation.
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
- **Second module — the Pond**: an ambient water simulation for when
  the wall isn't on weather duty. A two-buffer wave sim (half
  resolution, 2×2 LEDs per cell) takes rain drops and occasional
  pebbles; the height field is coloured by a chromostereoptic ramp —
  troughs in receding blues, crests in advancing ambers and reds —
  with slope shading over it, so the ripples read as real ridges and
  troughs standing out of the wall. Rain rate, pebble interval and
  relief strength are all in the admin; pick the module itself from
  Display → "Show on the wall".
- **Third module — the Aquarium**: a saltwater scene built for depth.
  The set (water, rock ridge, sand, corals) is static; the life is
  drawn back-to-front in three depth planes — far fish small, blue
  and slow behind the rocks, near fish large and warm in front —
  stacking occlusion, motion parallax, atmospheric blue shift and
  the same ChromaDepth-ordered palette as the pond (reds nearest,
  blues farthest). Swaying surface rays, caustic shimmer, rising
  bubbles and a turtle that crosses every so often. Fish density,
  turtle interval and the rays are all in the admin.
- **Fourth module — Overhead Aircraft**: a radar scope of the real
  sky, from the free community ADS-B feed (adsb.lol) — no antenna
  and no account; the area is already covered by volunteers'
  receivers. Aircraft within the chosen range (25/50/100 nm of the
  centre point, KFLG by default) plot on range rings coloured by
  altitude band — six steps from orange-red low to violet high.
  The right third of the wall is an info box for the nearest
  aircraft: operator (the airline, or a GA aircraft's registered
  owner), the full aircraft type, the tail number, altitude,
  speed, heading, vertical speed and distance — and, for scheduled
  flights, the departure and destination airports from the free
  adsbdb.com callsign lookup. An aircraft that slows to taxi
  speed over the field is treated as landed and the box hands off
  to the next nearest; a "seen today" tally of unique aircraft
  sits at the bottom of the box whenever there is room for it.
  The feed polls every 15–60 s (its
  own cadence, independent of the weather refresh) and each
  aircraft is dead-reckoned along its reported track and speed
  between polls, so the dots glide. Each dot trails a Garmin-style
  trend vector: its tip is where the aircraft will be in one
  minute at its current groundspeed.
- **Module rotation**: the admin's Module Rotation section has a
  master "Rotate modules" checkbox plus one checkbox per module
  (the LED ticker's pattern); with rotation on, the wall cycles
  the checked modules, each for a chosen dwell, crossfading
  between them. The weather map's region rotation keeps working
  while the map is up.
- **Fifth module — Tonight's Sky**: a planisphere of the sky over
  the house. Bright stars sized by magnitude (the brightest
  twinkle), the Milky Way as a soft blurred wash along the
  galactic equator, the planets as coloured dots with labels, and
  the moon at its true phase. By night the dome is live; by day
  it previews tonight at the end of astronomical twilight. The
  side column lists sunset, full dark, moonrise and phase, and
  the planets that are up.
- **Sixth module — Sun and Moon**: the day's two clocks. Today's
  sun path as an arc with sunrise/sunset, golden-hour shading,
  twilight ticks, day length and solar noon, beside a big moon
  disc at its true phase with its name, illumination, age and
  rise/set times; the bottom strip shows tonight's dark window
  and the next full moon. Both sky modules are computed on the
  Pi by `core/astro.py` from the wall's location — no feeds.
- **Seventh module — ISS Tracker**: the space station on the
  world map — ground track for the last and next 45 minutes,
  its visible-horizon footprint circle, the night side of the
  Earth shaded from the sun's computed position, and a marker
  for home. The strip shows altitude, speed and position, and
  the next pass over the house (or a live elevation during a
  pass). Elements come from CelesTrak every six hours and are
  propagated on the Pi by `core/orbit.py`, a small J2
  propagator validated against the live position.
- **Eighth module — Earthquake Map**: every M4.5+ earthquake of
  the past 24 hours or 7 days from the USGS feed, sized by
  magnitude and fading with age; M6+ events get a ring and the
  largest three are labelled. The strip gives the count, the
  largest event and the most recent one.
- **Ninth module — Live Radar**: NEXRAD reflectivity over the
  Southwest from the RainViewer mosaic (no key), refreshed
  every five minutes and animated as a loop of the last six
  frames, reprojected onto the wall's state outlines. Range
  rings at 50/100/150 miles around home and the region's
  cities stay readable on top of the echoes.
- **Tenth module — Aurora & Space Weather**: NOAA SWPC's
  OVATION aurora probability plotted over the night-shaded
  world map, with the planetary K index and the live solar
  wind (speed and Bz from the L1 monitors) in the strip, plus
  where the current Kp is visible from.
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
  regions.py      CONUS/WORLD/EUROPE presets + every US state and
                  every country, generated from the boundary data
  metar.py        aviationweather.gov JSON fetcher (see HOWTO)
  astro.py        sun/moon/planet/star computation (no feeds)
  orbit.py        TLE parsing + J2 orbit propagation (ISS)
  render.py       base maps, dots, icons, label, clock, legend
  display.py      MatrixDisplay (hzeller) / FileDisplay (previews)
  config.py       config.json defaults, load, atomic save
  updater.py      git-based update check / apply
  state.py        shared status for the admin page
  splash.py       boot splash
modules/
  base.py         module contract
  metar_map.py    the weather map module
  pond.py         the pond module: wave sim + relief shading
  aquarium.py     the aquarium module: layered depth-plane scene
  skywatch.py     the overhead-aircraft module: ADS-B scope
  tonight.py      Tonight's Sky: planisphere dome + evening facts
  sunmoon.py      Sun and Moon: sun-path arc + true-phase moon
  iss.py          ISS Tracker: station, track and next pass
  quakes.py       Earthquake Map: USGS M4.5+ events on the world
  radar.py        Live Radar: RainViewer mosaic over the Southwest
  aurora.py       Aurora & Space Weather: OVATION oval + Kp + wind
admin/
  app.py          Flask admin on :5000 (painter-clock v24 pattern)
data/
  us-states.json    state boundaries (PublicaMundi, public domain)
  us_stations.json  the ~2,950 US station ids fetched each cycle
  world-countries.json  country boundaries (Natural Earth 110m,
                  public domain, slimmed by scripts/build_world_data.py)
  world_stations.json   the ~7,750 METAR stations AWC carries,
                  selected per region by bounding box
scripts/
  build_world_data.py   rebuilds the two world data files from their
                  public sources (desktop only, never on the Pi)
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
