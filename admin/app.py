"""Admin web app - painter-clock v24 pattern (standing design rule):
sliders with live readouts for 0-100 values, project icon as favicon
and beside the header title, headed sections each with its own accent
color, and every action returning to the admin page itself (reboot via
an auto-refreshing interstitial back to admin).

Also serves /api/status: the Project Finder fingerprint - a JSON with
device-distinctive fields including the update state.
"""
import io
import os
import socket
import subprocess
import threading
import time

from flask import (Flask, jsonify, redirect, render_template_string,
                   request, send_file, url_for)

from ..core import config as config_mod
from ..core import updater

HERE = os.path.dirname(os.path.abspath(__file__))

ICON_KINDS = [("icon_ts", "Thunderstorm"), ("icon_sn", "Snow"),
              ("icon_ra", "Rain"), ("icon_fg", "Fog"), ("icon_gr", "Hail")]

PAGE = """<!DOCTYPE html>
<html><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>LEDWALL Admin</title>
<link rel="icon" type="image/png" href="/icon.png">
<style>
 body{font-family:sans-serif;background:#111;color:#ddd;margin:0;padding:16px}
 header{display:flex;align-items:center;gap:12px;margin-bottom:8px}
 header img{width:40px;height:30px;image-rendering:pixelated}
 h1{font-size:22px;margin:0}
 section{border:1px solid #333;border-radius:8px;padding:12px 16px;margin:12px 0}
 section h2{margin:0 0 10px;font-size:16px}
 .a-display h2{color:#ffb000}.a-module h2{color:#4da3ff}
 .a-pond h2{color:#4dd8c8}.a-aquarium h2{color:#ffa040}
 .a-sky h2{color:#ff8a5c}.a-rotate h2{color:#c792ff}
 .a-tonight h2{color:#9db4ff}.a-sunmoon h2{color:#ffd76a}
 .a-system h2{color:#7dd87d}.a-status h2{color:#ff7dd8}
 label{display:block;margin:8px 0 2px}
 input[type=range]{width:260px;vertical-align:middle}
 .val{display:inline-block;min-width:3em;text-align:right;font-weight:bold}
 button{background:#2a2a2a;color:#eee;border:1px solid #555;border-radius:6px;
        padding:6px 14px;cursor:pointer;margin-top:8px}
 .ok{color:#7dd87d}.warn{color:#ffb000}.dim{color:#999}
 img.frame{width:512px;max-width:100%;image-rendering:pixelated;border:1px solid #333}
</style></head><body>
<header><img src="/icon.png" alt=""><h1>LEDWALL Admin</h1></header>

<section class="a-status"><h2>Status</h2>
 {% if msg %}<div class="ok" style="margin-bottom:8px">{{ msg }}</div>{% endif %}
 <div>Module: <b>{{ state.module_name }}</b> &middot; Region: <b>{{ state.region }}</b></div>
 <div>Now showing: <b>{{ state.region }}</b></div>
 <div>Stations reporting: <b>{{ state.stations }}</b> &middot; Dots shown: <b>{{ state.dots }}</b></div>
 <div>Last data refresh: <b>{{ last_fetch }}</b></div>
 <div>Version: <b>{{ state.version }}</b> &middot;
 {% if state.update.available %}<span class="warn">Update available ({{ state.update.behind }} behind)</span>
 {% elif state.update.available == False %}<span class="ok">Up to date</span>
 {% else %}<span class="dim">Update state unknown</span>{% endif %}</div>
 <img class="frame" src="/frame.png" alt="current frame">
</section>

<form method="post" action="/save">
<section class="a-display"><h2>Display</h2>
 <label>Show on the wall
  <select name="module">{% for key, title in modules %}
   <option value="{{ key }}" {% if cfg.module == key %}selected{% endif %}>{{ title }}</option>{% endfor %}
  </select></label>
 <label>Brightness <span class="val" id="bv">{{ cfg.brightness }}</span></label>
 <input type="range" name="brightness" min="0" max="100" value="{{ cfg.brightness }}"
        oninput="document.getElementById('bv').textContent=this.value">
 <label>Night brightness <span class="val" id="nv">{{ cfg.night_brightness }}</span></label>
 <input type="range" name="night_brightness" min="0" max="100" value="{{ cfg.night_brightness }}"
        oninput="document.getElementById('nv').textContent=this.value">
 <label><input type="checkbox" name="night_mode" {% if cfg.night_mode %}checked{% endif %}>
        Night mode (dim to night brightness)</label>
 <label>Night hours
  <input type="text" name="night_start" value="{{ cfg.night_start }}" size="5"> to
  <input type="text" name="night_end" value="{{ cfg.night_end }}" size="5"> (24-hour)</label>
 <label><input type="checkbox" name="show_clock" {% if cfg.show_clock %}checked{% endif %}>
        Zulu clock (UTC, top-right corner)</label>
</section>

<section class="a-rotate"><h2>Module Rotation</h2>
 <label class="chk"><input type="checkbox" name="module_rotate_on" {% if cfg.module_rotate_on %}checked{% endif %}> Rotate modules</label>
 <div style="margin:6px 0 6px 18px">
  {% for key, title in modules %}
  <label style="display:block;margin:4px 0"><input type="checkbox" name="rotmod_{{ key }}" {% if key in cfg.rotate_modules %}checked{% endif %}> {{ title }}</label>{% endfor %}
 </div>
 <label>Show each module for
  <input type="number" name="module_rotate_s" min="10" max="3600" step="10" value="{{ cfg.module_rotate_s }}"> seconds</label>
 <div class="dim">With Rotate modules on, the wall cycles through the checked modules, each for the interval above. With it off (or fewer than two checked), the wall stays on the "Show on the wall" module. The weather map's own region rotation keeps working while the map is up.</div>
 <div><button type="submit">Save settings</button></div>
</section>

<section class="a-module"><h2>Weather Map</h2>
 <label>Region
  <select name="region">{% for r in regions %}
   <option value="{{ r }}" {% if cfg.region == r %}selected{% endif %}>{{ r }}</option>{% endfor %}
  </select></label>
 <label>Home airport (flag)
  <input type="text" name="home_airport" value="{{ cfg.home_airport }}" size="6" maxlength="6"></label>
 <label>Rotate through regions (after the overview)
  <select name="rotate_regions" multiple size="6">{% for r in regions %}
   <option value="{{ r }}" {% if r in cfg.rotate_regions %}selected{% endif %}>{{ r }}</option>{% endfor %}
  </select></label>
 <label>Show each region for
  <input type="number" name="rotate_s" min="10" max="3600" step="10" value="{{ cfg.rotate_s }}"> seconds</label>
 <div class="dim">The wall shows the Region above first - the whole picture, for context - then cycles through the picked regions, each for the interval below, and back to the overview.</div>
 <label>Station dot size
  <select name="dot_size">
   <option value="1" {% if cfg.dot_size == 1 %}selected{% endif %}>1 LED</option>
   <option value="2" {% if cfg.dot_size != 1 %}selected{% endif %}>2x2 block</option>
  </select></label>
 <label><input type="checkbox" name="show_icons" {% if cfg.show_icons %}checked{% endif %}>
        Weather icons</label>
 <label><input type="checkbox" name="show_label" {% if cfg.show_label %}checked{% endif %}>
        Region label (auto-placed in open space)</label>
 <div style="margin:2px 0 6px 18px">
  {% for key, label in icon_kinds %}
  <label style="display:inline-block;margin:0 10px 0 0"><input type="checkbox" name="{{ key }}" {% if cfg[key] %}checked{% endif %}> {{ label }}</label>{% endfor %}
 </div>
 <label>Icon animation
  <select name="icon_anim">
   <option value="fade" {% if cfg.icon_anim == "fade" %}selected{% endif %}>Fade in/out</option>
   <option value="blink" {% if cfg.icon_anim == "blink" %}selected{% endif %}>Blink (lightning)</option>
   <option value="steady" {% if cfg.icon_anim == "steady" %}selected{% endif %}>Steady</option>
  </select></label>
 <label>Data refresh (seconds) <span class="val" id="rv">{{ cfg.refresh_s }}</span></label>
 <input type="range" name="refresh_s" min="60" max="1800" step="60" value="{{ cfg.refresh_s }}"
        oninput="document.getElementById('rv').textContent=this.value">
 <div style="margin-top:10px"><img src="/legend.png" alt="Map legend"
      style="max-width:100%;border:1px solid #333;border-radius:6px"></div>
 <div><button type="submit">Save settings</button></div>
</section>

<section class="a-pond"><h2>Pond</h2>
 <label>Rain
  <select name="pond_drop_s">
   <option value="0" {% if cfg.pond_drop_s == 0 %}selected{% endif %}>Off</option>
   <option value="6" {% if cfg.pond_drop_s == 6 %}selected{% endif %}>Light (a drop every ~6 s)</option>
   <option value="2.5" {% if cfg.pond_drop_s == 2.5 %}selected{% endif %}>Steady (every ~2.5 s)</option>
   <option value="1" {% if cfg.pond_drop_s == 1 %}selected{% endif %}>Heavy (every second)</option>
  </select></label>
 <label>Pebble every
  <input type="number" name="pond_pebble_s" min="0" max="600" step="5" value="{{ cfg.pond_pebble_s }}"> seconds (0 = no pebbles)</label>
 <label>Relief strength <span class="val" id="pv">{{ cfg.pond_relief }}</span></label>
 <input type="range" name="pond_relief" min="0" max="100" value="{{ cfg.pond_relief }}"
        oninput="document.getElementById('pv').textContent=this.value">
 <div class="dim">How hard the ridges and troughs push out of the wall - the color-depth effect plus slope shading. Tune it to your eyes and your room.</div>
 <div><button type="submit">Save settings</button></div>
</section>

<section class="a-aquarium"><h2>Aquarium</h2>
 <label>Fish
  <select name="aq_fish">
   <option value="quiet" {% if cfg.aq_fish == "quiet" %}selected{% endif %}>Quiet (a few fish)</option>
   <option value="lively" {% if cfg.aq_fish == "lively" %}selected{% endif %}>Lively</option>
   <option value="full" {% if cfg.aq_fish == "full" %}selected{% endif %}>Reef-full</option>
  </select></label>
 <label>Turtle crosses every
  <input type="number" name="aq_turtle_s" min="0" max="600" step="10" value="{{ cfg.aq_turtle_s }}"> seconds (0 = never)</label>
 <label class="chk"><input type="checkbox" name="aq_rays" {% if cfg.aq_rays %}checked{% endif %}> Surface light rays</label>
 <div class="dim">The depth is layered: far fish swim bluer and slower behind the rocks, near fish run warm and large in front - the same color-depth effect as the pond, put to work.</div>
 <div><button type="submit">Save settings</button></div>
</section>

<section class="a-sky"><h2>Overhead Aircraft</h2>
 <label>Scope range
  <select name="sw_range_nm">
   <option value="25" {% if cfg.sw_range_nm == 25 %}selected{% endif %}>25 nm (local traffic)</option>
   <option value="50" {% if cfg.sw_range_nm == 50 %}selected{% endif %}>50 nm</option>
   <option value="100" {% if cfg.sw_range_nm == 100 %}selected{% endif %}>100 nm (the wide sky)</option>
  </select></label>
 <label>Feed refresh
  <select name="sw_refresh_s">
   <option value="15" {% if cfg.sw_refresh_s == 15 %}selected{% endif %}>Every 15 seconds</option>
   <option value="30" {% if cfg.sw_refresh_s == 30 %}selected{% endif %}>Every 30 seconds</option>
   <option value="60" {% if cfg.sw_refresh_s == 60 %}selected{% endif %}>Every minute</option>
  </select></label>
 <label>Center latitude <input type="text" name="sw_lat" value="{{ cfg.sw_lat }}" size="10"></label>
 <label>Center longitude <input type="text" name="sw_lon" value="{{ cfg.sw_lon }}" size="10"></label>
 <label>Center label <input type="text" name="sw_label" value="{{ cfg.sw_label }}" maxlength="6" size="8"></label>
 <div class="dim">Live traffic from the free community ADS-B feed (adsb.lol) - no antenna, no account. Defaults center on KFLG; the center point lives only in this Pi's own settings. Dots glide between polls on each aircraft's reported track and speed, colored by altitude from warm (low) to violet (high). The right-hand box follows the nearest aircraft: operator, full type, tail number, and - for scheduled flights, via the free adsbdb lookup - its departure and destination.</div>
 <div style="margin-top:8px">Target colors - altitude (MSL):</div>
 <div style="line-height:2">
  <span style="white-space:nowrap"><span style="display:inline-block;width:10px;height:10px;background:#FF6E28"></span> Below 8,000 ft</span> &nbsp;
  <span style="white-space:nowrap"><span style="display:inline-block;width:10px;height:10px;background:#FFBE00"></span> 8,000-14,000</span> &nbsp;
  <span style="white-space:nowrap"><span style="display:inline-block;width:10px;height:10px;background:#00DC78"></span> 14,000-20,000</span> &nbsp;
  <span style="white-space:nowrap"><span style="display:inline-block;width:10px;height:10px;background:#00D2C8"></span> 20,000-28,000</span> &nbsp;
  <span style="white-space:nowrap"><span style="display:inline-block;width:10px;height:10px;background:#50A0FF"></span> 28,000-36,000</span> &nbsp;
  <span style="white-space:nowrap"><span style="display:inline-block;width:10px;height:10px;background:#BE78FF"></span> Above 36,000</span> &nbsp;
  <span style="white-space:nowrap"><span style="display:inline-block;width:10px;height:10px;background:#787878"></span> Ground / no altitude</span>
 </div>
 <div><button type="submit">Save settings</button></div>
</section>

<section class="a-tonight"><h2>Tonight's Sky</h2>
 <label class="chk"><input type="checkbox" name="sky_labels" {% if cfg.sky_labels %}checked{% endif %}> Star and planet labels</label>
 <label class="chk"><input type="checkbox" name="sky_mw" {% if cfg.sky_mw %}checked{% endif %}> Milky Way band</label>
 <div class="dim">The sky over the wall's location (the Overhead Aircraft center point), computed on the Pi - no feed. By night the dome is live; by day it previews tonight as it will look when astronomical twilight ends. The column lists sunset, full dark, moonrise and phase, and the planets that are up.</div>
 <div><button type="submit">Save settings</button></div>
</section>

<section class="a-sunmoon"><h2>Sun and Moon</h2>
 <label class="chk"><input type="checkbox" name="sm_golden" {% if cfg.sm_golden %}checked{% endif %}> Golden-hour shading on the sun path</label>
 <label class="chk"><input type="checkbox" name="sm_twilight" {% if cfg.sm_twilight %}checked{% endif %}> Twilight ticks (civil and astronomical)</label>
 <div class="dim">Today's sun path with sunrise, sunset, day length and solar noon, and the moon at its true phase with its age and rise/set times - all computed on the Pi from the same location.</div>
 <div><button type="submit">Save settings</button></div>
</section>
</form>

<section class="a-system"><h2>System</h2>
 <form method="post" action="/update/check" style="display:inline">
   <button type="submit">Check for updates</button></form>
 <form method="post" action="/update/apply" style="display:inline">
   <button type="submit">Update now</button></form>
 <form method="post" action="/reboot" style="display:inline">
   <button type="submit">Reboot</button></form>
 <div class="dim">Admin address: http://{{ ip }}:{{ port }} &middot; Project Finder: /api/status</div>
</section>
</body></html>"""

REBOOT_PAGE = """<!DOCTYPE html><html><head><meta charset="utf-8">
<title>Rebooting</title><meta http-equiv="refresh" content="45;url=/">
<style>body{font-family:sans-serif;background:#111;color:#ddd;padding:16px}</style>
</head><body><h2>Rebooting&hellip;</h2>
<p>This page returns to the admin page automatically in about 45 seconds.</p>
</body></html>"""


def local_ip():
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))
        ip = s.getsockname()[0]
        s.close()
        return ip
    except Exception:
        return "127.0.0.1"


def create_app(state, regions, modules=None):
    if modules is None:
        modules = [("metar_map", "Weather map")]
    app = Flask(__name__)
    app.config["state"] = state
    app.config["regions"] = regions

    @app.route("/")
    def index():
        cfg = config_mod.load()
        last = ("never" if not state.last_fetch else
                time.strftime("%H:%M:%S", time.localtime(state.last_fetch)))
        return render_template_string(
            PAGE, cfg=cfg, state=state, regions=regions, modules=modules,
            last_fetch=last, ip=local_ip(), port=5000,
            msg=request.args.get("msg", ""), icon_kinds=ICON_KINDS)

    @app.route("/api/status")
    def api_status():
        return jsonify({
            "device": "ledwall",
            "title": "LEDWALL",
            "version": state.version,
            "module": state.module_name,
            "region": state.region,
            "stations": state.stations,
            "dots": state.dots,
            "last_fetch": state.last_fetch,
            "update_available": state.update.get("available"),
            "update_behind": state.update.get("behind"),
            "admin": "http://%s:5000" % local_ip(),
        })

    @app.route("/icon.png")
    def icon():
        # Generated fresh on each request (never kept in git or cached
        # to disk): a light-background miniature of the region map.
        from ..core import render
        from ..core.regions import get_region
        cfg = config_mod.load()
        img = render.render_icon(get_region(cfg["region"]))
        buf = io.BytesIO()
        img.save(buf, format="PNG")
        buf.seek(0)
        return send_file(buf, mimetype="image/png")

    @app.route("/legend.png")
    def legend():
        from ..core import render
        buf = io.BytesIO()
        render.render_legend().save(buf, format="PNG")
        buf.seek(0)
        return send_file(buf, mimetype="image/png")

    @app.route("/frame.png")
    def frame():
        if state.frame is None:
            return ("no frame yet", 503)
        buf = io.BytesIO()
        state.frame.save(buf, format="PNG")
        buf.seek(0)
        return send_file(buf, mimetype="image/png")

    @app.route("/save", methods=["POST"])
    def save():
        cfg = config_mod.load()
        mod = request.form.get("module", cfg.get("module", "metar_map"))
        if mod in dict(modules):
            cfg["module"] = mod  # an unknown module name is ignored
        cfg["module_rotate_on"] = "module_rotate_on" in request.form
        cfg["rotate_modules"] = [
            key for key, _title in modules
            if "rotmod_" + key in request.form]
        try:
            module_rotate_s = int(request.form.get(
                "module_rotate_s", cfg.get("module_rotate_s", 120)))
        except ValueError:
            module_rotate_s = cfg.get("module_rotate_s", 120)
        cfg["module_rotate_s"] = min(3600, max(10, module_rotate_s))
        try:
            cfg["pond_drop_s"] = min(60.0, max(0.0, float(
                request.form.get("pond_drop_s",
                                 cfg.get("pond_drop_s", 2.5)))))
        except ValueError:
            pass  # keep the previous value
        try:
            pebble = int(request.form.get(
                "pond_pebble_s", cfg.get("pond_pebble_s", 30)))
        except ValueError:
            pebble = cfg.get("pond_pebble_s", 30)
        cfg["pond_pebble_s"] = 0 if pebble == 0 else min(
            600, max(10, pebble))
        try:
            cfg["pond_relief"] = min(100, max(0, int(
                request.form.get("pond_relief",
                                 cfg.get("pond_relief", 70)))))
        except ValueError:
            pass
        aq_fish = request.form.get("aq_fish", cfg.get("aq_fish"))
        if aq_fish in ("quiet", "lively", "full"):
            cfg["aq_fish"] = aq_fish  # unknown densities are ignored
        try:
            turtle = int(request.form.get(
                "aq_turtle_s", cfg.get("aq_turtle_s", 90)))
        except ValueError:
            turtle = cfg.get("aq_turtle_s", 90)
        cfg["aq_turtle_s"] = 0 if turtle == 0 else min(
            600, max(20, turtle))
        cfg["aq_rays"] = "aq_rays" in request.form
        for key, allowed in (("sw_range_nm", (25, 50, 100)),
                             ("sw_refresh_s", (15, 30, 60))):
            try:
                v = int(request.form.get(key, cfg.get(key)))
                if v in allowed:
                    cfg[key] = v  # off-list values are ignored
            except (TypeError, ValueError):
                pass
        for key, lo, hi in (("sw_lat", -90.0, 90.0),
                            ("sw_lon", -180.0, 180.0)):
            try:
                v = float(request.form.get(key, cfg.get(key)))
                if lo <= v <= hi:
                    cfg[key] = v
            except (TypeError, ValueError):
                pass  # keep the previous coordinate
        sw_label = "".join(ch for ch in request.form.get(
            "sw_label", cfg.get("sw_label", "KFLG")) if ch.isalnum())
        if sw_label:
            cfg["sw_label"] = sw_label[:6].upper()
        for key in ("sky_labels", "sky_mw", "sm_golden", "sm_twilight"):
            cfg[key] = key in request.form
        cfg["brightness"] = int(request.form.get("brightness", cfg["brightness"]))
        cfg["night_brightness"] = int(request.form.get(
            "night_brightness", cfg["night_brightness"]))
        cfg["night_mode"] = "night_mode" in request.form
        for key in ("night_start", "night_end"):
            parsed = config_mod.parse_hhmm(request.form.get(key, ""))
            if parsed is not None:
                cfg[key] = config_mod.format_hhmm(parsed)
            # an unreadable time keeps the previous value, never junk
        cfg["show_clock"] = "show_clock" in request.form
        cfg["region"] = request.form.get("region", cfg["region"])
        home = request.form.get("home_airport",
                                cfg.get("home_airport", ""))
        cfg["home_airport"] = "".join(
            ch for ch in home.upper() if ch.isalnum())[:6]
        cfg["rotate_regions"] = [
            r for r in request.form.getlist("rotate_regions")
            if r in regions]
        try:
            rotate_s = int(request.form.get(
                "rotate_s", cfg.get("rotate_s", 120)))
        except ValueError:
            rotate_s = cfg.get("rotate_s", 120)
        cfg["rotate_s"] = min(3600, max(10, rotate_s))
        cfg["dot_size"] = int(request.form.get("dot_size",
                                               cfg.get("dot_size", 2)))
        if cfg["dot_size"] not in (1, 2):
            cfg["dot_size"] = 2
        cfg["show_icons"] = "show_icons" in request.form
        cfg["show_label"] = "show_label" in request.form
        for key in ("icon_ts", "icon_sn", "icon_ra", "icon_fg", "icon_gr"):
            cfg[key] = key in request.form
        anim = request.form.get("icon_anim", cfg.get("icon_anim", "fade"))
        cfg["icon_anim"] = anim if anim in ("fade", "blink", "steady") \
            else "fade"
        cfg["refresh_s"] = int(request.form.get("refresh_s", cfg["refresh_s"]))
        try:
            config_mod.save(cfg)
        except OSError:
            return redirect(url_for("index", msg="Could not write config.json (read-only location) - settings not saved."))
        return redirect(url_for("index", msg="Settings saved - changes apply live, no restart needed."))

    @app.route("/update/check", methods=["POST"])
    def update_check():
        state.update = updater.check_update()
        return redirect(url_for("index", msg="Update check complete."))

    @app.route("/update/apply", methods=["POST"])
    def update_apply():
        ok, message = updater.apply_update()
        if ok:
            state.update = updater.check_update()
            return redirect(url_for("index", msg="Updated: %s - reboot to run the new code." % message))
        return redirect(url_for("index", msg="Update failed: %s" % message))

    @app.route("/reboot", methods=["POST"])
    def reboot():
        def _later():
            time.sleep(2)
            subprocess.run(["sudo", "reboot"])
        threading.Thread(target=_later, daemon=True).start()
        return REBOOT_PAGE

    return app


def serve(state, regions, modules=None, port=5000):
    create_app(state, regions, modules).run(
        host="0.0.0.0", port=port, threaded=True)
