# LEDWALL — install & operations

## Fresh install on the Pi

Prerequisites (all present on the v1 map Pi): Python 3 with `flask`
and `pillow`, and the rpi-rgb-led-matrix Python bindings (`rgbmatrix`)
built from the hzeller library.

```
cd /home/pi
git clone git@github.com:markyharris/ledwall.git
cd ledwall
python3 -c "import flask, PIL, rgbmatrix; print('deps ok')"
python3 run.py        # first run by hand: splash, then the map
```

Autostart is one line in `/etc/rc.local` (before `exit 0`):

```
python3 /home/pi/ledwall/run.py >> /home/pi/ledwall/ledwall.log 2>&1 &
```

Everything the app prints (including tracebacks from the guarded main
loop) lands in `ledwall.log`.

**Rollback to v1:** comment the ledwall line in `/etc/rc.local`,
uncomment the v1 `webapp.py` line, reboot. The v1 repo and its files
were never touched.

## Updating

Admin page → **Check for update**, then **Update now** (runs
`git pull --ff-only`), then **Reboot**. Code changes take effect at
the reboot; most settings apply live because the loop re-reads
`config.json` every tick.

Why the updater works even though the app runs as root and the GitHub
key belongs to `pi`: `core/updater.py` borrows the checkout owner's
SSH identity — it finds `id_ed25519`/`id_rsa` in the `.ssh` folder
beside the checkout and points `GIT_SSH_COMMAND` at it. Without that,
git run as root has no key and GitHub answers "Permission denied
(publickey)".

## Hard-won lessons (do not relearn these)

1. **The matrix library drops privileges.** hzeller's library demotes
   the process to the `daemon` user after GPIO setup
   (`options.drop_privileges`, on by default). ledwall runs the admin
   server in the same process, so the demotion silently removed its
   write access: config saves and the base-map cache failed with
   PermissionError *while `whoami` said root*. Fix, already in
   `core/display.py`: `options.drop_privileges = False`. (v1 never hit
   this because its webapp and its matrix driver were separate
   processes.)
2. **`hardware_mapping` is `"regular"`** — the value v1 proved with
   this HAT and wiring. Not `adafruit-hat-pwm`.
3. **`gpio_slowdown` is 4.** This library build errors above 5. If a
   longer ribbon run ever tears, this is the compensating knob.
4. **The weather API has sharp edges** (aviationweather.gov JSON):
   `hours` must be a whole number — `hours=2.5` is HTTP 400 — so the
   fetcher asks for 3 and applies the exact 2.5 h cutoff client-side
   by `obsTime`. More than ~300 station ids in one request is
   HTTP 414, so ids go in 300-station chunks, newest report per
   station wins.
5. **Power is a star, not a chain.** The v1 fault that started this
   rebuild was a resistive power leg: the far panels on that row
   starved and garbled their data, and the fault followed the *row*,
   not any panel. One fused home run per panel from the distribution
   block, crimped or screw-clamped joints only, no barrel connectors
   in the high-current path. Acceptance test: **≥ 4.9 V metered at the
   farthest panel with the bright splash up.**
6. **`config.json` is git-ignored on purpose** (v1's `data.txt` got
   clobbered by file copies). Saves are atomic (tmp file + replace)
   and failures surface on the admin page instead of failing silently.
7. **World data is built, not fetched at runtime.** Country
   boundaries (Natural Earth 110m) and the world station list (the
   METAR stations in aviationweather.gov's own published station
   cache — 7,746 of them) are baked into `data/` by
   `scripts/build_world_data.py`, run on a desktop. The Pi only ever
   asks the weather API for the current region's ids (a country is
   one chunk; the whole world is 26). Two traps the build already
   handles: AWC's CDN truncates urllib downloads, so the script
   prefers curl; and "Georgia" is both a state and a country — the
   country's region key is `GEORGIA_COUNTRY`, and the boundary
   polygon cache is keyed by dataset as well as name. Coverage is
   the API's coverage: dense over North America and Europe, honest
   dark patches where the world doesn't report METARs.
8. **Fetches run on a background thread.** `refresh_data` never runs
   in the draw loop, so a slow fetch (the API has multi-minute slow
   patches; a world fetch is 26 chunks) can't freeze the icon
   animation — new data swaps in when it lands. Data carries across
   a region switch only when the new view's stations were covered
   by the old fetch (a world view covers its countries; US views
   share one list); otherwise the switch fetches fresh at once.
9. **Some world reports arrive without coordinates.** US reports
   always carry lat/lon; a few international ones omit them, and the
   first completed world fetch (2,834 reports) crashed the draw on
   exactly that. `refresh_data` backfills positions from the station
   directory, and `plot_weather` skips any report still missing
   them — one bad record can never take the wall down.
10. **Modules are interchangeable, and the core must not assume the
    map.** The pond (module 2) has no stations, no fetch and no base
    map: `refresh_data` is a base-class no-op, the fetch worker
    tolerates a module with no `metars`, the splash falls back to a
    black backdrop, and a switch into any module tolerates it having
    no `station_ids`. The pond simulates at half resolution (128×96,
    each cell a 2×2 block) — a full-res pure-Python wave sim would
    not hold 10 fps on the Pi — and schedules its drops on its own
    tick count, never the wall clock.
11. **The aquarium (module 3) gets its depth from draw order, not
    computation.** The static set is composed once; each frame is
    base → rays → far fish → mid fish → turtle → bubbles → near
    fish → foreground rocks, so nearer things simply paint over
    farther ones (occlusion), each plane swims at its own speed
    (parallax) with its own blue blend (atmospheric shift), and the
    palette runs in ChromaDepth order — warm saturated colours near,
    cool far — so the chromostereopsis works with the geometry
    instead of against it. Sprites are pre-rendered per plane at
    setup; a frame costs ~1 ms of compositing, leaving the Pi idle.
12. **A module can poll faster than the weather (module 4,
    Skywatch).** The loop's fetch interval is the config's
    `refresh_s` — right for METARs, useless for aircraft. A module
    that sets `fetch_s` (seconds) overrides it for its own fetches;
    Skywatch syncs it from its own setting (15/30/60 s) and
    dead-reckons each aircraft along its reported track/speed
    between polls, capped at 90 s, so 30-second polls still glide.
    The trend vector is a true one-minute vector (groundspeed ÷ 60
    at the scope's scale, the Garmin convention), so its pixel
    length changes with the range setting; labels are placed on
    the side the vector is not pointing, with a knocked-out
    backing patch so a vector passing behind a label never strikes
    through its text.
    Its data is the free adsb.lol community feed — no key, no
    antenna — and a failed poll keeps the last picture rather than
    raising. The scope's centre defaults to KFLG's public
    coordinates on purpose: precise home coordinates belong in the
    Pi's git-ignored config.json, never in this public repo. The
    info box's routes and owners come from a second free source,
    adsbdb.com (callsign → airline + origin/destination; hex →
    registered owner), looked up only for the nearest few aircraft
    and cached for the session — a GA tail simply has no route,
    which the box treats as normal, not as an error. The box
    target is the nearest aircraft that has not landed: within
    2 nm of the centre at under 40 knots counts as on the ground,
    and the box (and the scope's ring marker) move to the next
    one. The day's tally of unique aircraft is kept in
    skywatch_tally.json beside the config (git-ignored, best-
    effort writes), resets at local midnight, and prints at the
    box's bottom only when the content above leaves room.

## Troubleshooting

| Symptom | Likely cause | Fix |
| --- | --- | --- |
| Admin says settings can't be saved | privilege-drop regression (lesson 1) | check `drop_privileges = False` survived any display.py edit |
| Update check: "Permission denied (publickey)" | updater lost the owner-key borrow (lesson: updater) | check `~/.ssh/id_ed25519` exists beside the checkout |
| Splash shows, weather never does | API unreachable or fetcher error | `tail ledwall.log`; the loop retries every 30 s and keeps the last frame |
| Confetti / tearing on far panels | power sag (lesson 5) or ribbon too long | meter the far panel under load; then `gpio_slowdown` |
| Map dark after a settings save | brightness / night mode | admin → Display; night mode dims 22:00–06:00 to night brightness |

## Finding the wall on the network

Project Finder recognizes LEDWALL by its `/api/status` fingerprint
(`"device": "ledwall"`, port 5000) and links straight to the admin
page — the answer to DHCP moving the Pi.
