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
13. **Rotation is a map-only concern (fixed Nov 27).** The live-
    config path rebuilt the active module whenever the rotation
    advanced the region — including modules with no regions at
    all. For Skywatch each rebuild wiped the fetched traffic, so
    when a ~20-minute network stall stopped its fetches, the
    rotation quietly replaced the stale-but-visible picture with
    an empty "WAITING" scope, and planes were seen to melt away
    in the switch crossfade. The fix gates the region machinery
    to the weather map; other modules keep their state across
    rotation ticks, and a future stall now degrades to a STALE
    marker over the last picture instead of a blank scope.
14. **A splash nobody sees is not a splash (fixed Nov 27).** The
    boot splash rendered and the module loop overwrote it within
    a fraction of a second — the hold was never implemented, so
    the admin address the splash exists to announce was never
    readable on the wall. The entry point now holds the splash
    for `splash_hold_s` (default 3.5) with the admin already
    serving. When a display step is specified ("show X for N
    seconds"), verify the timing in the running loop, not just
    that the frame is drawn once.

15. **Module rotation is the outer loop; region rotation stays
    inside the map (Nov 27).** The wall learned to rotate through
    modules (admin → Module Rotation: pick the modules, set the
    dwell). `desired_module` mirrors `desired_region` exactly —
    the cycle leads with the "Show on the wall" module, each
    module gets its full dwell, a changed cycle adopts the current
    view when it can — and it keeps its state under separate
    `view` keys so the two rotations never disturb each other.
    `apply_live_config` asks the module question first and only
    consults region rotation when the map is the module that
    belongs up, which is what keeps lesson 13's gate intact. One
    carry-over refinement came with it: fetched METARs count as
    covering the new view when the view's station list is a
    subset of the fetched dict's keys, not only of the old
    module's station list — a non-map module can hold the dict
    between map visits, so rotating away and back now restores
    the map instantly instead of refetching every lap.

16. **The sky modules compute everything on the Pi (Nov 27).**
    Tonight's Sky and Sun and Moon share `core/astro.py` — NOAA
    solar series, Schlyter's lunar elements with the main
    perturbation terms, JPL's approximate Keplerian planet
    elements, a bright-star catalog, and a vector-based galactic
    conversion for the Milky Way band. Verified against published
    anchors before the modules were drawn: the full-moon instant
    for Nov 24, 2026 came out 9 minutes off the almanac's, and
    Flagstaff sunrise/sunset/noon altitude all land where they
    should. Two traps worth remembering: right after perigee the
    moon moves ~14 degrees a day, so illumination falls far
    faster than the mean-motion guess (an early test "failure"
    was the test's anchor, not the code); and a phase disc's
    bright limb must be aimed with exact tangent-plane dot
    products (`sun_screen_dir`), not a small-angle Δaz·cos(alt)
    shortcut — at wide sun-moon separations the shortcut bends
    the limb the wrong way. The moon disc itself is drawn
    scanline by scanline from the terminator's half-ellipse
    geometry at 3x and reduced. Both modules take the wall's
    location from the Skywatch center settings (sw_lat/sw_lon),
    so there is one place to correct the site's coordinates.

17. **Rotation controls are checkboxes, like the ticker's
    (Nov 27).** The first module-rotation admin used a
    multi-select list, with the "Show on the wall" module implied
    as the cycle's lead — Mark sent it back the same day: the LED
    ticker's pattern is one checkbox per rotating item, and he
    wanted a master checkbox deciding whether rotation happens
    at all. The model is now exactly that: `module_rotate_on`
    plus `rotate_modules` holding the checked keys, and the
    cycle is the checked set in admin list order. Switch off (or
    fewer than two checked) and the single module setting rules.
    When a control already exists on another of his projects,
    match its pattern instead of inventing a new one.

18. **The ISS propagator is deliberately not SGP4 (Nov 27).**
    `core/orbit.py` propagates the CelesTrak elements with the
    secular J2 rates for the node and perigee plus the TLE's own
    drag term — no third-party package on the Pi. Three
    refinements were tried against the wheretheiss.at live
    position from an 11-hour-old element set and measured, not
    argued: SGP4's Kozai recovery of the mean motion made the
    error worse (38 km vs 35), the textbook J2 term on the mean
    anomaly doubled it again when combined with the recovery,
    and dropping it entirely overshot the other way. The
    combination that won — raw mean motion, no extra mean-anomaly
    term — plus a geocentric-to-geodetic conversion on WGS84
    (worth ~17 km of latitude and ~6 km of altitude by itself,
    because the reference positions are geodetic) landed 3.8 km
    from the live fix: a third of a pixel on the wall, and pass
    times good to a few seconds. Altitude still reads ~7 km
    high, a known cosmetic bias from the raw semi-major axis.
    If the tracker ever needs better, the fix is a real SGP4
    port, not more terms bolted onto this one.

19. **Radar tiles are web-mercator; the wall is not (Nov 27).**
    The Live Radar module stitches RainViewer mosaic tiles
    (standard web-mercator, like every tile service) but draws
    its geography with the wall's equirectangular projection.
    Composited naively, echoes would sit several pixels off the
    state lines at the view's corners. The fix is a one-axis
    warp: longitude is linear in both projections, so only the
    rows need remapping — each output row samples the mercator
    row for its latitude. Nine zoom-5 tiles cover the Southwest
    view, and six frames loop for the animation. Two feed
    lessons ride along: SWPC's old solar-wind product URLs are
    gone (404) — the live data now comes from the RTSW 1-minute
    JSON files, whose rows arrive unsorted and from more than
    one spacecraft, so sort by time_tag and take the latest
    non-null reading; and the OVATION aurora grid is lon
    0..360, so wrap it before projecting.

20. **A module with no data must retry like it means it
    (Nov 27).** The ISS module's first fetch on the wall either
    failed or queued behind a weather fetch on a slow line, and
    because its fetch interval is six hours, one miss stranded
    it on "WAITING FOR ELEMENTS" with the next attempt hours
    away. The fetch interval is now a property on the data-fed
    modules: brisk (45-60 s) until the first data lands, then
    the normal cadence. The ISS fetch also falls back from
    CelesTrak to AMSAT's daily element file. Rule of thumb for
    new modules: the empty state is the one state that must
    never be patient.

21. **Honor the precision the data actually has (Nov 27).**
    Launch Library 2 dates many launches only to the day or
    the month. Counting down to that date's midnight would
    manufacture a T-0 nobody promised, so the Launch Board
    shows NET <date> for coarse entries and counts down only
    when the NET is precise to the hour or better. Same family
    of honesty as the METAR age cutoff: never let a tidy
    display imply more certainty than the feed carries. The
    feed also keeps just-flown launches in "upcoming" briefly
    with their status flipped to Success - filter on status,
    not on the clock alone. And its free tier throttles at 15
    requests/hour per address: poll like a guest (30 min),
    keep the last good list, and never retry-storm a 429.

22. **Don't offer views with nothing in them (Nov 27).** The
    region pickers listed all 232 regions, including the four
    whose own outline contains no reporting airport at all
    (Palestine, Djibouti, Western Sahara, French Southern &
    Antarctic Lands) - a view of those is an empty outline.
    `regions.station_counts()` counts the baked station
    directory inside each region's own outline (the same
    outline the map clips dots to, so the count is what the
    wall would actually show); run.py hands the empty set to
    the admin on the app state, and the pickers skip them -
    except a region the owner is currently using, which stays
    listed so saving the page can never silently drop a
    setting. The map machinery keeps every region; only the
    choices shrink. If counting ever fails, every region
    reports occupied - an error must hide nothing.

23. **One data set can wear two outfits (Nov 27).** Mark liked
    the info modules' whole-earth look (darkened world base,
    plain title, dots, facts strip) and asked for the METAR
    data in the same theme. World Weather is a separate module
    sharing the weather map's feed, age cutoff and category
    colors - not a restyle of the map, which keeps its own
    regional detail, icons and clock. At world scale the plot
    declutters onto the map's own 2 px separation with the
    worse category winning each cell. Strip text follows the
    all-or-nothing rule: a suffix that cannot fit whole
    ("16 WITH THUNDERSTORMS") is shortened by design ("16 TS")
    or dropped - never truncated into a stub that reads as a
    typo.

24. **Test the loop's contract, not just the module (Nov 27).**
    The Launch Board drew perfect frames in its own tests, then
    wedged the real wall on its splash: the main loop reads
    `module.dot_count` after every draw, the Launch Board never
    set one, and the loop's keep-last-frame rule held the
    splash forever, logging the AttributeError every 30 s.
    Three-layer fix: the base Module class now defaults
    `dot_count = 0`, the loop reads it with getattr, and
    `test_all_modules.py` walks every registered module
    through setup + draw + the loop's own attribute accesses.
    A module test that never touches the framework's contract
    proves the picture, not the module.

25. **An address lookup needs a fallback and a fuse (Nov 27).**
    The splash started showing 127.0.0.1: `local_ip()` asked
    the kernel for the outbound source address and took any
    exception - or a loopback answer, when the service started
    before the network had a route - as final. Now it falls
    back to enumerating the machine's interfaces (Linux ioctl,
    wireless first), and the splash call waits up to 30 s for a
    real address before giving up, so a boot race costs seconds
    instead of printing a useless address. The admin page's own
    address line calls the same lookup live, which makes it the
    quick check for whether the lookup or the moment was at
    fault.

26. **Shade both directions when the base is dark (Nov 27).**
    The Day & Night terminator map first reused the ISS
    recipe - full base, black wash over the night side - and
    the split barely read: the world base is intrinsically
    dark, so darkening the night half only sank dark into
    darker. The fix composites two versions of the base
    through a sun-altitude mask (ramping through twilight,
    blurred): a brightened one on the day side, a deepened one
    on the night side. When a display's raw material sits near
    one end of the range, contrast has to be manufactured on
    both ends. The terminator line itself is found column by
    column from the sun's computed altitude (scan + bisect,
    one declination/RA computation per rebuild), so it bends
    with the seasons and ends at the polar caps on its own.

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
