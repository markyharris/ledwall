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
