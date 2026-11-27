"""A small near-earth orbit propagator for the ISS module.

Parses a two-line element set and propagates it with the classic
secular J2 rates plus the TLE's own drag term on the mean motion.
That is deliberately not full SGP4: the error against SGP4 is a
few km in the first day from epoch and a pixel or two on the wall
after a week, in exchange for no third-party dependency on the Pi
(same reasoning as core/astro.py). Validated Nov 27, 2026 against
the wheretheiss.at live position from an 11-hour-old TLE.

Positions come out as (lat, lon, altitude km, speed km/h).
"""
import calendar
import math
import urllib.request

from ledwall.core import astro

MU = 398600.8            # km^3/s^2
RE = 6378.137            # equatorial radius, km
J2 = 1.08262668e-3
TLE_URL = ("https://celestrak.org/NORAD/elements/gp.php"
           "?CATNR=25544&FORMAT=TLE")


def parse_tle(text):
    """The ISS element set out of a CelesTrak TLE response."""
    lines = [ln.rstrip() for ln in text.strip().splitlines()
             if ln.strip()]
    l1 = next(ln for ln in lines if ln.startswith("1 "))
    l2 = next(ln for ln in lines if ln.startswith("2 "))
    year = int(l1[18:20])
    year += 2000 if year < 57 else 1900
    day = float(l1[20:32])
    epoch = calendar.timegm((year, 1, 1, 0, 0, 0, 0, 0, 0)) \
        + (day - 1.0) * 86400.0
    return {
        "epoch": epoch,
        "ndot2": float(l1[33:43]),        # d(mean motion)/dt / 2
        "incl": float(l2[8:16]),
        "raan": float(l2[17:25]),
        "ecc": float("0." + l2[26:33]),
        "argp": float(l2[34:42]),
        "manom": float(l2[43:51]),
        "nrev": float(l2[52:63]),         # rev/day
    }


AMSAT_URL = "https://www.amsat.org/tle/current/nasabare.txt"


def _get(url, timeout):
    req = urllib.request.Request(url, headers={
        "User-Agent": "ledwall (personal LED display)"})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return resp.read().decode("ascii", "replace")


def fetch_tle(url=TLE_URL, timeout=25):
    """The ISS element set, from CelesTrak with AMSAT's daily
    file as a fallback - the two occasionally have bad days
    independently, and a wall with no elements is just a sign
    saying so."""
    try:
        return parse_tle(_get(url, timeout))
    except Exception:
        text = _get(AMSAT_URL, timeout)
        lines = text.splitlines()
        for i, ln in enumerate(lines):
            if ln.startswith("1 25544") and i + 1 < len(lines):
                return parse_tle(ln + "\n" + lines[i + 1])
        raise ValueError("ISS elements not found at AMSAT")


def propagate(tle, t):
    """(lat, lon, alt_km, speed_kmh) at unix time t."""
    dt = t - tle["epoch"]                       # seconds
    dd = dt / 86400.0                           # days
    e = tle["ecc"]
    incl = math.radians(tle["incl"])
    # The TLE's mean motion is used as-is. Two refinements were
    # tried against the live position and measured WORSE, so they
    # stay out: SGP4's Kozai recovery of n and a, and the
    # textbook J2 secular term on the mean anomaly (the fitted
    # mean motion already carries that effect over the fit span).
    n0 = tle["nrev"] * 2 * math.pi / 86400.0    # rad/s
    a = (MU / n0 ** 2) ** (1.0 / 3.0)
    p = a * (1 - e * e)
    j2f = J2 * (RE / p) ** 2 * n0
    raan = math.radians(tle["raan"]) \
        - 1.5 * j2f * math.cos(incl) * dt
    argp = math.radians(tle["argp"]) + 0.75 * j2f \
        * (5 * math.cos(incl) ** 2 - 1) * dt
    # drag: the TLE field is half the first derivative of the
    # mean motion (rev/day^2), so the mean anomaly gains
    # ndot2 * dd^2 revolutions.
    m = math.radians(tle["manom"]) \
        + n0 * dt \
        + tle["ndot2"] * dd * dd * 2 * math.pi
    # Kepler's equation by Newton iteration
    E = m
    for _ in range(8):
        E -= (E - e * math.sin(E) - m) / (1 - e * math.cos(E))
    nu = 2 * math.atan2(math.sqrt(1 + e) * math.sin(E / 2),
                        math.sqrt(1 - e) * math.cos(E / 2))
    r = a * (1 - e * math.cos(E))
    xp = r * math.cos(nu)
    yp = r * math.sin(nu)
    cw, sw = math.cos(argp), math.sin(argp)
    cn, sn = math.cos(raan), math.sin(raan)
    ci, si = math.cos(incl), math.sin(incl)
    x = (cn * cw - sn * sw * ci) * xp + (-cn * sw - sn * cw * ci) * yp
    y = (sn * cw + cn * sw * ci) * xp + (-sn * sw + cn * cw * ci) * yp
    z = (sw * si) * xp + (cw * si) * yp
    rho = math.hypot(x, y)
    lon = astro._wrap180(math.degrees(math.atan2(y, x))
                         - astro._gmst_deg(t))
    # Geocentric -> geodetic on WGS84: the reference positions
    # this is checked against (and every map reader's intuition)
    # are geodetic, and at ISS latitudes the difference is worth
    # ~17 km of latitude and ~6 km of altitude.
    f = 1.0 / 298.257223563
    e2 = f * (2 - f)
    phi = math.atan2(z, rho)
    for _ in range(3):
        n_ = RE / math.sqrt(1 - e2 * math.sin(phi) ** 2)
        phi = math.atan2(z + e2 * n_ * math.sin(phi), rho)
    n_ = RE / math.sqrt(1 - e2 * math.sin(phi) ** 2)
    alt = rho / math.cos(phi) - n_
    speed = math.sqrt(MU * (2 / r - 1 / a)) * 3600.0
    return math.degrees(phi), lon, alt, speed


def look_angles(tle, t, obs_lat, obs_lon):
    """(elevation deg, azimuth deg, range km) of the satellite
    from an observer on the ground."""
    lat, lon, alt, _ = propagate(tle, t)
    phi = math.radians(obs_lat)
    lam = math.radians(obs_lon)
    sp, cp = math.sin(phi), math.cos(phi)
    # observer and satellite in earth-fixed coordinates
    ox, oy, oz = RE * cp * math.cos(lam), RE * cp * math.sin(lam), \
        RE * sp
    slat = math.radians(lat)
    slon = math.radians(lon)
    sr = RE + alt
    sx = sr * math.cos(slat) * math.cos(slon)
    sy = sr * math.cos(slat) * math.sin(slon)
    sz = sr * math.sin(slat)
    dx, dy, dz = sx - ox, sy - oy, sz - oz
    # rotate into the local east/north/up frame
    sl, cl = math.sin(lam), math.cos(lam)
    east = -sl * dx + cl * dy
    north = -sp * cl * dx - sp * sl * dy + cp * dz
    up = cp * cl * dx + cp * sl * dy + sp * dz
    rng = math.sqrt(east ** 2 + north ** 2 + up ** 2)
    el = math.degrees(math.asin(up / rng))
    az = astro._wrap180(math.degrees(math.atan2(east, north))) % 360
    return el, az, rng


def next_pass(tle, obs_lat, obs_lon, t0, horizon_h=30.0,
              min_el=0.0):
    """The next pass over the observer: dict with start, end,
    max elevation and its time, or None within the horizon.
    Scans at 10-second steps - the ISS crosses the sky in
    minutes, so that resolution loses nothing on a wall."""
    step = 10.0
    end = t0 + horizon_h * 3600.0
    t = t0
    inside = None
    while t <= end:
        el, _az, _r = look_angles(tle, t, obs_lat, obs_lon)
        if el >= min_el:
            if inside is None:
                inside = {"start": t, "max_el": el, "t_max": t}
            elif el > inside["max_el"]:
                inside["max_el"] = el
                inside["t_max"] = t
        elif inside is not None:
            inside["end"] = t
            return inside
        t += step
    if inside is not None:
        inside["end"] = end
        return inside
    return None
