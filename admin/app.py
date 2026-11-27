"""Admin web app - painter-clock v24 pattern (standing design rule):
sliders with live readouts for 0-100 values, project icon as favicon
and beside the header title, headed sections each with its own accent
colour, and every action returning to the admin page itself (reboot via
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
 <label>Brightness <span class="val" id="bv">{{ cfg.brightness }}</span></label>
 <input type="range" name="brightness" min="0" max="100" value="{{ cfg.brightness }}"
        oninput="document.getElementById('bv').textContent=this.value">
 <label>Night brightness <span class="val" id="nv">{{ cfg.night_brightness }}</span></label>
 <input type="range" name="night_brightness" min="0" max="100" value="{{ cfg.night_brightness }}"
        oninput="document.getElementById('nv').textContent=this.value">
 <label><input type="checkbox" name="night_mode" {% if cfg.night_mode %}checked{% endif %}>
        Night mode (dim 22:00-06:00)</label>
</section>

<section class="a-module"><h2>Weather Map</h2>
 <label>Region
  <select name="region">{% for r in regions %}
   <option value="{{ r }}" {% if cfg.region == r %}selected{% endif %}>{{ r }}</option>{% endfor %}
  </select></label>
 <label>Station dot size
  <select name="dot_size">
   <option value="1" {% if cfg.dot_size == 1 %}selected{% endif %}>1 LED</option>
   <option value="2" {% if cfg.dot_size != 1 %}selected{% endif %}>2x2 block</option>
  </select></label>
 <label><input type="checkbox" name="show_icons" {% if cfg.show_icons %}checked{% endif %}>
        Weather icons</label>
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


def create_app(state, regions):
    app = Flask(__name__)
    app.config["state"] = state
    app.config["regions"] = regions

    @app.route("/")
    def index():
        cfg = config_mod.load()
        last = ("never" if not state.last_fetch else
                time.strftime("%H:%M:%S", time.localtime(state.last_fetch)))
        return render_template_string(
            PAGE, cfg=cfg, state=state, regions=regions, last_fetch=last,
            ip=local_ip(), port=5000, msg=request.args.get("msg", ""),
            icon_kinds=ICON_KINDS)

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
        cfg["brightness"] = int(request.form.get("brightness", cfg["brightness"]))
        cfg["night_brightness"] = int(request.form.get(
            "night_brightness", cfg["night_brightness"]))
        cfg["night_mode"] = "night_mode" in request.form
        cfg["region"] = request.form.get("region", cfg["region"])
        cfg["dot_size"] = int(request.form.get("dot_size",
                                               cfg.get("dot_size", 2)))
        if cfg["dot_size"] not in (1, 2):
            cfg["dot_size"] = 2
        cfg["show_icons"] = "show_icons" in request.form
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
        return redirect(url_for("index", msg="Settings saved - restart the map to apply changes."))

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


def serve(state, regions, port=5000):
    create_app(state, regions).run(host="0.0.0.0", port=port, threaded=True)
