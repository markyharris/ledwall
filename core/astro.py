"""Astronomy core for the wall - sun, moon, planets, bright stars.

Everything is computed on the Pi from the wall's location; there
are no feeds to stall (the Nov 27 lesson). The algorithms are the
standard low-precision ones (NOAA solar series, Schlyter's lunar
elements with the main perturbation terms, JPL's approximate
Keplerian planet elements): arcminute-to-fraction-of-a-degree
class, which on a 256x192 wall - about a degree per LED on the
sky dome - is far past what the display can show. Rise/set times
come from scanning the day and bisecting the horizon crossing,
one code path for sun, moon and the twilight angles.
"""
import math
import time

D2R = math.pi / 180.0
R2D = 180.0 / math.pi


def _jd(epoch):
    return epoch / 86400.0 + 2440587.5


def _gmst_deg(epoch):
    d = _jd(epoch) - 2451545.0
    return (280.46061837 + 360.98564736629 * d) % 360.0


def _wrap180(deg):
    return (deg + 180.0) % 360.0 - 180.0


def altaz(ra_h, dec_d, epoch, lat, lon):
    """Equatorial -> horizontal. Returns (alt, az) in degrees,
    az from north, eastward (90 = east, 180 = south)."""
    ha = _wrap180(_gmst_deg(epoch) + lon - ra_h * 15.0)
    ha_r, dec_r, lat_r = ha * D2R, dec_d * D2R, lat * D2R
    alt = math.asin(math.sin(dec_r) * math.sin(lat_r)
                    + math.cos(dec_r) * math.cos(lat_r)
                    * math.cos(ha_r))
    az = math.atan2(math.sin(ha_r),
                    math.cos(ha_r) * math.sin(lat_r)
                    - math.tan(dec_r) * math.cos(lat_r))
    return alt * R2D, (az * R2D + 180.0) % 360.0


def _ecl_to_radec(lon_d, lat_d, epoch):
    """Ecliptic (degrees) -> (ra hours, dec degrees)."""
    eps = (23.4392911 - 0.0000004 * (_jd(epoch) - 2451545.0)) * D2R
    lo, la = lon_d * D2R, lat_d * D2R
    ra = math.atan2(math.cos(eps) * math.sin(lo)
                    - math.sin(eps) * math.tan(la), math.cos(lo))
    dec = math.asin(math.sin(la) * math.cos(eps)
                    + math.cos(la) * math.sin(eps) * math.sin(lo))
    return (ra * R2D / 15.0) % 24.0, dec * R2D


# ---------------------------------------------------------------- sun

def sun_lon(epoch):
    """The sun's geocentric ecliptic longitude, degrees."""
    n = _jd(epoch) - 2451545.0
    mean_lon = (280.460 + 0.9856474 * n) % 360.0
    g = ((357.528 + 0.9856003 * n) % 360.0) * D2R
    return (mean_lon + 1.915 * math.sin(g)
            + 0.020 * math.sin(2 * g)) % 360.0


def sun_radec(epoch):
    return _ecl_to_radec(sun_lon(epoch), 0.0, epoch)


def sun_altaz(epoch, lat, lon):
    ra, dec = sun_radec(epoch)
    return altaz(ra, dec, epoch, lat, lon)


# --------------------------------------------------------------- moon

def moon_lonlat(epoch):
    """Geocentric ecliptic (lon, lat) of the moon, degrees.
    Schlyter's elements plus the largest perturbation terms -
    good to roughly a tenth of a degree."""
    d = _jd(epoch) - 2451543.5  # days since 2000 Jan 0.0
    N = (125.1228 - 0.0529538083 * d) % 360.0
    w = (318.0634 + 0.1643573223 * d) % 360.0
    M = (115.3654 + 13.0649929509 * d) % 360.0
    a, e, incl = 60.2666, 0.054900, 5.1454
    # eccentric anomaly, a few Newton iterations (e is small)
    Mr = M * D2R
    E = Mr + e * math.sin(Mr) * (1 + e * math.cos(Mr))
    for _ in range(3):
        E = E - (E - e * math.sin(E) - Mr) / (1 - e * math.cos(E))
    xv = a * (math.cos(E) - e)
    yv = a * (math.sqrt(1 - e * e) * math.sin(E))
    v = math.atan2(yv, xv) * R2D
    # position in the orbital plane, rotated by node/inclination
    # into true ecliptic coordinates
    u = (v + w) * D2R
    xh = math.cos(N * D2R) * math.cos(u) \
        - math.sin(N * D2R) * math.sin(u) * math.cos(incl * D2R)
    yh = math.sin(N * D2R) * math.cos(u) \
        + math.cos(N * D2R) * math.sin(u) * math.cos(incl * D2R)
    zh = math.sin(u) * math.sin(incl * D2R)
    lon = math.atan2(yh, xh) * R2D % 360.0
    lat = math.atan2(zh, math.hypot(xh, yh)) * R2D
    # main perturbations (Schlyter): Ms = the sun's mean anomaly,
    # Ls its mean longitude, Lm the moon's mean longitude,
    # D = mean elongation, F = mean argument of latitude
    Ms = (356.0470 + 0.9856002585 * d) % 360.0
    Ls = (Ms + 282.9404 + 0.00000470935 * d) % 360.0
    Lm = (N + w + M) % 360.0
    D = (Lm - Ls) % 360.0
    F = (Lm - N) % 360.0
    s = math.sin
    lon += (-1.274 * s((M - 2 * D) * D2R) + 0.658 * s(2 * D * D2R)
            - 0.186 * s(Ms * D2R) - 0.059 * s((2 * M - 2 * D) * D2R)
            - 0.057 * s((M - 2 * D + Ms) * D2R)
            + 0.053 * s((M + 2 * D) * D2R)
            + 0.046 * s((2 * D - Ms) * D2R)
            + 0.041 * s((M - Ms) * D2R)
            - 0.035 * s(F * D2R) - 0.031 * s((M + Ms) * D2R)
            - 0.015 * s((2 * F - 2 * D) * D2R)
            + 0.011 * s((M - 4 * D) * D2R))
    lat += (-0.173 * s((F - 2 * D) * D2R)
            - 0.055 * s((M - F - 2 * D) * D2R)
            - 0.046 * s((M + F - 2 * D) * D2R)
            + 0.033 * s((F + 2 * D) * D2R)
            + 0.017 * s((2 * M + F) * D2R))
    return lon % 360.0, lat


def moon_radec(epoch):
    lon, lat = moon_lonlat(epoch)
    return _ecl_to_radec(lon, lat, epoch)


def moon_altaz(epoch, lat, lon):
    ra, dec = moon_radec(epoch)
    return altaz(ra, dec, epoch, lat, lon)


def moon_illum(epoch):
    """Illuminated fraction of the moon's disc, 0..1, from the
    sun-moon elongation (3-D unit vectors, so the moon's ecliptic
    latitude is accounted for)."""
    sra, sdec = sun_radec(epoch)
    mra, mdec = moon_radec(epoch)
    sv = (math.cos(sdec * D2R) * math.cos(sra * 15 * D2R),
          math.cos(sdec * D2R) * math.sin(sra * 15 * D2R),
          math.sin(sdec * D2R))
    mv = (math.cos(mdec * D2R) * math.cos(mra * 15 * D2R),
          math.cos(mdec * D2R) * math.sin(mra * 15 * D2R),
          math.sin(mdec * D2R))
    cos_e = sv[0] * mv[0] + sv[1] * mv[1] + sv[2] * mv[2]
    return (1.0 - cos_e) / 2.0


def moon_age(epoch):
    """(days since the last new moon, elongation degrees), from
    the ecliptic longitude difference - the moon laps the sun
    once per synodic month."""
    elong = (moon_lonlat(epoch)[0] - sun_lon(epoch)) % 360.0
    return elong / 360.0 * 29.53059, elong


_PHASES = [(0.033, "New Moon"), (0.217, "Waxing Crescent"),
           (0.283, "First Quarter"), (0.467, "Waxing Gibbous"),
           (0.533, "Full Moon"), (0.717, "Waning Gibbous"),
           (0.783, "Last Quarter"), (0.967, "Waning Crescent"),
           (1.001, "New Moon")]


def phase_name(epoch):
    frac = moon_age(epoch)[0] / 29.53059
    for limit, name in _PHASES:
        if frac < limit:
            return name
    return "New Moon"


def next_phase(epoch, target_elong):
    """Epoch of the next time the moon's elongation from the sun
    reaches target_elong degrees (0 = new, 180 = full). Scans in
    3-hour steps up to 40 days and bisects the crossing; the
    wrapped difference is continuous at the target itself, so
    the sign change is real."""
    step = 3 * 3600
    prev_t = epoch
    prev = _wrap180(moon_age(epoch)[1] - target_elong)
    for k in range(1, 40 * 8 + 1):
        t = epoch + k * step
        cur = _wrap180(moon_age(t)[1] - target_elong)
        if prev < 0 <= cur:
            lo_t, hi_t = prev_t, t
            for _ in range(24):
                mid = (lo_t + hi_t) / 2
                if _wrap180(moon_age(mid)[1] - target_elong) < 0:
                    lo_t = mid
                else:
                    hi_t = mid
            return (lo_t + hi_t) / 2
        prev_t, prev = t, cur
    return None


# ------------------------------------------------------------ planets

# JPL approximate Keplerian elements + rates per Julian century
# (a AU, e, I deg, L deg, long. peri. deg, long. node deg)
_PLANETS = {
    "Mercury": ((0.38709927, 0.20563593, 7.00497902, 252.25032350,
                 77.45779628, 48.33076593),
                (0.00000037, 0.00001906, -0.00594749, 149472.67411175,
                 0.16047689, -0.12534081), (200, 200, 200), -0.4),
    "Venus": ((0.72333566, 0.00677672, 3.39467605, 181.97909950,
               131.60246718, 76.67984255),
              (0.00000390, -0.00004107, -0.00078890, 58517.81538729,
               0.00268329, -0.27769418), (255, 240, 200), -4.4),
    "Earth": ((1.00000261, 0.01671123, -0.00001531, 100.46457166,
               102.93768193, 0.0),
              (0.00000562, -0.00004392, -0.01294668, 35999.37244981,
               0.32327364, 0.0), (140, 180, 255), None),
    "Mars": ((1.52371034, 0.09339410, 1.84969142, -4.55343205,
              -23.94362959, 49.55953891),
             (0.00001847, 0.00007882, -0.00813131, 19140.30268499,
              0.44441088, -0.29257343), (255, 120, 60), 0.7),
    "Jupiter": ((5.20288700, 0.04838624, 1.30439695, 34.39644051,
                 14.72847983, 100.47390909),
                (-0.00011607, -0.00013253, -0.00183714, 3034.74612775,
                 0.21252668, 0.20469106), (235, 210, 170), -2.2),
    "Saturn": ((9.53667594, 0.05386179, 2.48599187, 49.95424423,
                92.59887831, 113.66242448),
               (-0.00125060, -0.00050991, 0.00193609, 1222.49362201,
                -0.41897216, -0.28867794), (230, 200, 140), 0.6),
}
PLANET_NAMES = ["Mercury", "Venus", "Mars", "Jupiter", "Saturn"]


def _helio(name, epoch):
    """Heliocentric ecliptic (x, y, z) in AU."""
    (a, e, incl, L, peri, node), rates, _, _ = _PLANETS[name]
    T = (_jd(epoch) - 2451545.0) / 36525.0
    a += rates[0] * T
    e += rates[1] * T
    incl += rates[2] * T
    L = (L + rates[3] * T) % 360.0
    peri += rates[4] * T
    node += rates[5] * T
    M = ((L - peri) % 360.0) * D2R
    w = (peri - node) * D2R
    E = M + e * math.sin(M)
    for _ in range(5):
        E = E - (E - e * math.sin(E) - M) / (1 - e * math.cos(E))
    xp = a * (math.cos(E) - e)
    yp = a * math.sqrt(1 - e * e) * math.sin(E)
    cw, sw = math.cos(w), math.sin(w)
    cn, sn = math.cos(node * D2R), math.sin(node * D2R)
    ci, si = math.cos(incl * D2R), math.sin(incl * D2R)
    x = (cw * cn - sw * sn * ci) * xp + (-sw * cn - cw * sn * ci) * yp
    y = (cw * sn + sw * cn * ci) * xp + (-sw * sn + cw * cn * ci) * yp
    z = (sw * si) * xp + (cw * si) * yp
    return x, y, z


def planet_radec(name, epoch):
    """Geocentric (ra hours, dec degrees, distance AU)."""
    px, py, pz = _helio(name, epoch)
    ex, ey, ez = _helio("Earth", epoch)
    x, y, z = px - ex, py - ey, pz - ez
    lon = math.atan2(y, x) * R2D % 360.0
    lat = math.atan2(z, math.hypot(x, y)) * R2D
    ra, dec = _ecl_to_radec(lon, lat, epoch)
    return ra, dec, math.sqrt(x * x + y * y + z * z)


def planet_color(name):
    return _PLANETS[name][2]


def planet_mag(name):
    """Nominal magnitude for chart sizing (planets vary; these are
    typical values, fine for dot size and list ordering)."""
    return _PLANETS[name][3]


# ------------------------------------------------------- rise / set

def _day_start_epoch(year, mon, day):
    """Epoch of local midnight for a local date."""
    return time.mktime((year, mon, day, 0, 0, 0, 0, 0, -1))


def _crossings(day0, fn, threshold):
    """All (epoch, rising) crossings of fn(epoch) == threshold in
    the 24 h from day0, fn sampled every 2 minutes and bisected."""
    out = []
    step = 120.0
    prev_t, prev_v = day0, fn(day0) - threshold
    for k in range(1, 721):
        t = day0 + k * step
        v = fn(t) - threshold
        if (prev_v < 0) != (v < 0):
            lo_t, hi_t, lo_v = prev_t, t, prev_v
            for _ in range(20):
                mid = (lo_t + hi_t) / 2
                mv = fn(mid) - threshold
                if (mv < 0) == (lo_v < 0):
                    lo_t, lo_v = mid, mv
                else:
                    hi_t = mid
            out.append(((lo_t + hi_t) / 2, prev_v < 0))
        prev_t, prev_v = t, v
    return out


_events_cache = {}


def sun_events(year, mon, day, lat, lon):
    """Sunrise/sunset, twilight ends, solar noon for a local date.
    Values are epochs or None (a crossing that never happens)."""
    key = ("sun", year, mon, day, round(lat, 3), round(lon, 3))
    if key in _events_cache:
        return _events_cache[key]
    day0 = _day_start_epoch(year, mon, day)

    def alt(t):
        return sun_altaz(t, lat, lon)[0]

    ev = {}
    for name, thr in (("sun", -0.583), ("civil", -6.0),
                      ("nautical", -12.0), ("astro", -18.0)):
        cr = _crossings(day0, alt, thr)
        rise = next((t for t, up in cr if up), None)
        fall = next((t for t, up in cr if not up), None)
        if name == "sun":
            ev["sunrise"], ev["sunset"] = rise, fall
        else:
            ev["dawn_" + name] = rise
            ev["dusk_" + name] = fall
    # solar noon: the day's highest sun (ternary search, 10:00-16:00)
    lo, hi = day0 + 10 * 3600, day0 + 16 * 3600
    for _ in range(40):
        m1 = lo + (hi - lo) / 3
        m2 = hi - (hi - lo) / 3
        if alt(m1) < alt(m2):
            lo = m1
        else:
            hi = m2
    ev["solar_noon"] = (lo + hi) / 2
    if ev["sunrise"] and ev["sunset"]:
        ev["day_length"] = ev["sunset"] - ev["sunrise"]
    _events_cache[key] = ev
    return ev


def moon_events(year, mon, day, lat, lon):
    """Moonrise/moonset for a local date (either may be None - the
    moon does not cross the horizon every calendar day)."""
    key = ("moon", year, mon, day, round(lat, 3), round(lon, 3))
    if key in _events_cache:
        return _events_cache[key]
    day0 = _day_start_epoch(year, mon, day)

    def alt(t):
        return moon_altaz(t, lat, lon)[0]

    cr = _crossings(day0, alt, 0.125)
    ev = {"moonrise": next((t for t, up in cr if up), None),
          "moonset": next((t for t, up in cr if not up), None)}
    _events_cache[key] = ev
    return ev


# -------------------------------------------------------------- stars

# (name or None, ra hours, dec degrees, magnitude) - J2000, the
# brightest stars; names only where a chart label earns its space.
STARS = [
    ("Sirius", 6.752, -16.716, -1.46), ("Canopus", 6.399, -52.696, -0.74),
    ("Arcturus", 14.261, 19.182, -0.05), ("Vega", 18.616, 38.784, 0.03),
    ("Capella", 5.278, 45.998, 0.08), ("Rigel", 5.242, -8.202, 0.13),
    ("Procyon", 7.655, 5.225, 0.34), ("Betelgeuse", 5.919, 7.407, 0.42),
    ("Achernar", 1.629, -57.237, 0.46), ("Hadar", 14.064, -60.373, 0.61),
    ("Altair", 19.846, 8.868, 0.76), ("Acrux", 12.443, -63.099, 0.76),
    ("Aldebaran", 4.599, 16.509, 0.86), ("Antares", 16.490, -26.432, 0.96),
    ("Spica", 13.420, -11.161, 0.97), ("Pollux", 7.755, 28.026, 1.14),
    ("Fomalhaut", 22.961, -29.622, 1.16), ("Mimosa", 12.795, -59.689, 1.25),
    ("Deneb", 20.690, 45.280, 1.25), ("Regulus", 10.139, 11.967, 1.39),
    ("Adhara", 6.977, -28.972, 1.50), ("Castor", 7.577, 31.888, 1.58),
    ("Shaula", 17.560, -37.104, 1.62), ("Bellatrix", 5.419, 6.350, 1.64),
    ("Gacrux", 12.519, -57.113, 1.63), ("Elnath", 5.438, 28.608, 1.68),
    ("Miaplacidus", 9.220, -69.717, 1.69), ("Alnilam", 5.604, -1.202, 1.69),
    ("Alnitak", 5.679, -1.943, 1.74), ("Alna'ir", 22.137, -46.961, 1.74),
    ("Alioth", 12.901, 55.960, 1.77), ("Dubhe", 11.062, 61.751, 1.79),
    ("Mirfak", 3.405, 49.861, 1.80), (None, 7.140, -26.393, 1.84),
    (None, 17.622, -42.998, 1.86), (None, 18.403, -34.385, 1.85),
    (None, 8.375, -59.509, 1.86), ("Alkaid", 13.792, 49.313, 1.86),
    (None, 5.992, 44.947, 1.90), (None, 16.810, -69.027, 1.91),
    ("Alhena", 6.571, 16.399, 1.92), (None, 20.428, -56.735, 1.94),
    ("Alsephina", 8.745, -54.708, 1.96), (None, 6.378, -17.956, 1.98),
    ("Alphard", 9.460, -8.659, 1.98), ("Polaris", 2.530, 89.264, 1.98),
    ("Hamal", 2.119, 23.462, 2.00), ("Nunki", 18.921, -26.297, 2.02),
    ("Mizar", 13.399, 54.925, 2.04), ("Alpheratz", 0.139, 29.091, 2.06),
    ("Kochab", 14.845, 74.156, 2.08), ("Rasalhague", 17.588, 12.560, 2.08),
    ("Denebola", 11.817, 14.572, 2.11), ("Algol", 3.136, 40.956, 2.12),
    ("Mintaka", 5.533, -0.299, 2.23),
    (None, 20.612, -18.213, 2.40), ("Markab", 23.079, 15.205, 2.48),
]

# Galactic -> equatorial, done with basis vectors so there is no
# formula-sign roulette: x_g points at the galactic center, z_g at
# the north galactic pole, y_g = z_g x x_g completes the triad.
def _eq_vec(ra_deg, dec_deg):
    return (math.cos(dec_deg * D2R) * math.cos(ra_deg * D2R),
            math.cos(dec_deg * D2R) * math.sin(ra_deg * D2R),
            math.sin(dec_deg * D2R))


_XG = _eq_vec(266.405, -28.936)   # galactic center (l=0, b=0)
_ZG = _eq_vec(192.860, 27.128)    # north galactic pole
_YG = (_ZG[1] * _XG[2] - _ZG[2] * _XG[1],
       _ZG[2] * _XG[0] - _ZG[0] * _XG[2],
       _ZG[0] * _XG[1] - _ZG[1] * _XG[0])


def gal_to_radec(gl_deg, gb_deg):
    """Galactic (l, b) -> (ra hours, dec degrees), J2000."""
    cb = math.cos(gb_deg * D2R)
    v = tuple(cb * math.cos(gl_deg * D2R) * _XG[i]
              + cb * math.sin(gl_deg * D2R) * _YG[i]
              + math.sin(gb_deg * D2R) * _ZG[i] for i in range(3))
    ra = math.atan2(v[1], v[0]) * R2D % 360.0
    dec = math.asin(max(-1.0, min(1.0, v[2]))) * R2D
    return ra / 15.0, dec


def milky_way(epoch, lat, lon):
    """(alt, az) samples along the galactic equator - the bright
    band of the Milky Way - for the chart's soft background wash."""
    pts = []
    for k in range(72):
        ra, dec = gal_to_radec(k * 5.0, 0.0)
        pts.append(altaz(ra, dec, epoch, lat, lon))
    return pts


def sun_screen_dir(sun_alt, sun_az, alt, az):
    """Direction toward the sun in the tangent plane at an object
    sitting at (alt, az), in screen coordinates: (dx, dy) with dx
    positive in the direction of increasing azimuth and dy
    positive DOWN (a sun below the object gives positive dy).
    Exact dot products with the local azimuth/altitude basis
    vectors - for shading the moon, whose bright limb faces this
    way, at any sun-moon separation."""
    daz = (sun_az - az) * D2R
    sa = sun_alt * D2R
    dx = math.cos(sa) * math.sin(daz)
    up = -math.sin(alt * D2R) * math.cos(sa) * math.cos(daz) \
        + math.sin(sa) * math.cos(alt * D2R)
    return dx, -up


# --------------------------------------------------------- moon disc

def moon_disc(diameter, illum, sun_dx, sun_dy,
              lit=(233, 230, 216), dark=(26, 30, 42)):
    """A PIL tile (square, transparent outside the disc) of the
    moon at the given illuminated fraction, the bright limb facing
    the sun's direction in screen space: (sun_dx, sun_dy) is the
    direction toward the sun in image coordinates (x right, y
    down). Drawn at 3x and reduced, so the terminator - a
    half-ellipse whose offset is -(2k-1) of each chord - lands
    smooth on the LEDs. The dark side stays faintly visible:
    earthshine."""
    from PIL import Image, ImageDraw
    S = 3
    R = diameter * S // 2
    size = R * 2 + 2
    img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    cx = cy = size // 2
    d.ellipse((cx - R, cy - R, cx + R, cy + R), fill=dark + (255,))
    k = max(0.0, min(1.0, illum))
    xt = -(2 * k - 1)  # terminator offset, in units of the chord
    for row in range(-R, R + 1):
        w = math.sqrt(max(0.0, R * R - row * row))
        d.line((cx + xt * w, cy + row, cx + w, cy + row),
               fill=lit + (255,))
    if sun_dx or sun_dy:
        ang = math.degrees(math.atan2(-sun_dy, sun_dx))
        img = img.rotate(ang, resample=Image.BILINEAR)
    return img.resize((diameter, diameter), Image.LANCZOS)
