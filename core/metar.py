"""METAR fetching from the aviationweather.gov JSON API.

Carries the two hard-won lessons from the ledmap v1 repair (Nov 2026):
  * The JSON API accepts only WHOLE hours - hours=2.5 returns HTTP 400.
    We round the request up and apply the exact age cutoff client-side
    using each report's obsTime.
  * One request for ~3,000 station ids returns HTTP 414 (URL too long),
    so ids are fetched in chunks of 300.
On a 4xx the fetch returns what it has instead of retry-looping forever;
on a network error it retries (the router-boot race at power-up).
"""
import json
import math
import time
import urllib.request
import urllib.error

API = "https://aviationweather.gov/api/data/metar?format=json&hours={h}&ids={ids}"
CHUNK = 300


def _fetch_chunk(ids, hours, retries=4):
    url = API.format(h=hours, ids=",".join(ids))
    req = urllib.request.Request(url, headers={"User-Agent": "ledwall"})
    for attempt in range(retries):
        try:
            with urllib.request.urlopen(req, timeout=30) as resp:
                return json.loads(resp.read().decode("utf-8"))
        except urllib.error.HTTPError as e:
            if 400 <= e.code < 500:
                return []  # bad request will not fix itself; do not spin
            time.sleep(2 * (attempt + 1))
        except Exception:
            time.sleep(2 * (attempt + 1))
    return []


def fetch_metars(station_ids, max_age_h=2.5):
    """Return {icao: report} with the newest report per station, filtered
    to max_age_h. Report fields: lat, lon, fltCat, wxString, wdir, wspd,
    wgst, obsTime."""
    hours = int(math.ceil(max_age_h))
    cutoff = time.time() - max_age_h * 3600
    newest = {}
    ids = list(station_ids)
    for i in range(0, len(ids), CHUNK):
        for rep in _fetch_chunk(ids[i:i + CHUNK], hours):
            icao = rep.get("icaoId")
            if not icao or rep.get("obsTime", 0) < cutoff:
                continue
            if icao not in newest or rep["obsTime"] > newest[icao]["obsTime"]:
                newest[icao] = rep
    return newest
