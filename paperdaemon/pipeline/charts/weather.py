r"""Daily weather for a calendar, from Open-Meteo.

No key, no account, and it covers both directions from today in one request: `past_days` reaches
back far enough to fill the start of the current month and `forecast_days` reaches sixteen days
forward, which is as far as anyone's forecast is worth printing.

Humidity is the awkward one -- Open-Meteo has no daily mean for it, so the hourly series comes
back alongside and is averaged per day here.

    days = daily(48.8566, 2.3522)         # {"YYYY-MM-DD": {...}, ...}

Cached under <geo cache>/wx (see paths.geo_dir) for a few hours, because a calendar gets
re-rendered far more often than the forecast changes, and re-fetching on every render is rude to
a free service.
"""
from __future__ import annotations
import io
import json
import os
import time
import urllib.parse
import urllib.request
from paperdaemon import paths
from paperdaemon import net as _net

CACHE = os.path.join(paths.geo_dir(), "wx")
TTL = 3 * 3600
API = "https://api.open-meteo.com/v1/forecast"

# WMO weather codes -> the icon names this drawing set has. Grouped the way a person reads a
# forecast, not the way the standard enumerates it: drizzle, freezing rain and showers are all
# "it will be wet", and nobody needs four different rain icons on a month view.
CODE_ICON = {
    0: "sun", 1: "sun", 2: "part", 3: "cloud",
    45: "fog", 48: "fog",
    51: "rain", 53: "rain", 55: "rain", 56: "rain", 57: "rain",
    61: "rain", 63: "rain", 65: "rain", 66: "rain", 67: "rain",
    71: "snow", 73: "snow", 75: "snow", 77: "snow",
    80: "rain", 81: "rain", 82: "rain", 85: "snow", 86: "snow",
    95: "storm", 96: "storm", 99: "storm",
}
CODE_TEXT = {
    0: "clear", 1: "mostly clear", 2: "partly cloudy", 3: "overcast",
    45: "fog", 48: "freezing fog", 51: "light drizzle", 53: "drizzle",
    55: "heavy drizzle", 56: "freezing drizzle", 57: "freezing drizzle",
    61: "light rain", 63: "rain", 65: "heavy rain", 66: "freezing rain",
    67: "freezing rain", 71: "light snow", 73: "snow", 75: "heavy snow",
    77: "snow grains", 80: "showers", 81: "showers", 82: "heavy showers",
    85: "snow showers", 86: "snow showers", 95: "thunderstorms",
    96: "thunderstorms, hail", 99: "thunderstorms, hail",
}


# WINDY IS A MODIFIER. WMO codes know nothing of wind, but a day with a Beaufort-6 maximum is a
# windy day before it is a sunny one, so the sky glyph gets the wind lines set beside it.
WINDY = {"fahrenheit": 22.0, "celsius": 35.0}      # mph, km/h


def _classify(code, wind, units):
    icon, text = CODE_ICON.get(code, "cloud"), CODE_TEXT.get(code, "")
    if wind is not None and wind >= WINDY.get(units, 22.0):
        if icon in ("sun", "part"):
            icon, text = "sun-wind", "sunny and windy"
        elif icon in ("cloud", "fog"):
            icon, text = "cloud-wind", "cloudy and windy"
    return icon, text


def _cached(url):
    if not os.path.isdir(CACHE):
        os.makedirs(CACHE)
    import hashlib
    key = os.path.join(CACHE, hashlib.sha1(url.encode("utf-8")).hexdigest()[:16] + ".json")   # stable across runs
    if os.path.exists(key) and time.time() - os.path.getmtime(key) < TTL:
        try:
            return json.load(io.open(key, encoding="utf-8"))
        except Exception:
            pass
    req = urllib.request.Request(url, headers={"User-Agent": "PaperDaemon/1.0 (reMarkable assistant)"})
    data = json.loads(_net.urlopen(req, timeout=30).read().decode("utf-8"))
    io.open(key, "w", encoding="utf-8").write(json.dumps(data))
    return data


def temperature_units():
    """The user's preference: "fahrenheit" (wind in mph) or "celsius" (wind in km/h)."""
    from paperdaemon import paths
    return paths.prefs()["temperature"]


def daily(lat, lon, past=31, ahead=16, units=None, tz="auto"):
    """One entry per date: hi, lo, uv, humidity, rain chance, an icon name and a description.

    Returns {} rather than raising if the network is down -- a calendar with no weather on it is
    still a calendar, and a page that refuses to draw because a forecast service is unreachable
    is worse than one that quietly leaves the numbers off.
    """
    units = units or temperature_units()
    q = urllib.parse.urlencode({
        "latitude": "%.4f" % float(lat), "longitude": "%.4f" % float(lon),
        "daily": ("weather_code,temperature_2m_max,temperature_2m_min,uv_index_max,"
                  "precipitation_probability_max,wind_speed_10m_max,"
                  "wind_direction_10m_dominant,sunrise,sunset"),
        "hourly": "relative_humidity_2m",
        "temperature_unit": units,
        "wind_speed_unit": "mph" if units == "fahrenheit" else "kmh",
        "timezone": tz,
        "past_days": int(max(0, min(92, past))),
        "forecast_days": int(max(1, min(16, ahead))),
    })
    try:
        d = _cached(API + "?" + q)
    except Exception:
        return {}
    dd = d.get("daily") or {}
    # hourly humidity -> a daily mean
    hum, hrs = {}, d.get("hourly") or {}
    for t, h in zip(hrs.get("time") or [], hrs.get("relative_humidity_2m") or []):
        if h is None:
            continue
        hum.setdefault(t[:10], []).append(h)
    out = {}
    for i, date in enumerate(dd.get("time") or []):
        def g(k):
            v = (dd.get(k) or [None] * (i + 1))
            return v[i] if i < len(v) else None
        code = g("weather_code")
        vals = hum.get(date) or []
        out[date] = {
            "hi": g("temperature_2m_max"), "lo": g("temperature_2m_min"),
            "uv": g("uv_index_max"), "pop": g("precipitation_probability_max"),
            "wind": g("wind_speed_10m_max"), "wind_dir": g("wind_direction_10m_dominant"),
            "sunrise": (g("sunrise") or "")[11:16], "sunset": (g("sunset") or "")[11:16],
            "humidity": (sum(vals) / len(vals)) if vals else None,
            "code": code,
            "icon": _classify(code, g("wind_speed_10m_max"), units)[0],
            "text": _classify(code, g("wind_speed_10m_max"), units)[1],
        }
    return out


def month(lat, lon, year, mo, **kw):
    """Just the days of one month, keyed by day NUMBER -- the shape a calendar spec wants."""
    import calendar as _cal
    import datetime as _dt
    first = _dt.date(year, mo, 1)
    back = max(0, (_dt.date.today() - first).days + 1)
    ahead = max(1, (first + _dt.timedelta(days=_cal.monthrange(year, mo)[1])
                    - _dt.date.today()).days + 1)
    got = daily(lat, lon, past=min(92, back), ahead=min(16, ahead), **kw)
    out = {}
    for date, v in got.items():
        y, m, d = (int(x) for x in date.split("-"))
        if (y, m) == (year, mo):
            out[d] = v
    return out


def hourly(lat, lon, past=2, ahead=8, units=None, tz="auto"):
    """Per date: everything daily() gives, plus sunrise, sunset, the wind's direction and the
    HOURS -- temperature, chance and amount of precipitation and the weather code for each one.

    This is what a weather week is drawn from: a month cell says "rain, 60%", a week column has
    the room to say WHEN. {} if the network is down, like daily().
    """
    units = units or temperature_units()
    q = urllib.parse.urlencode({
        "latitude": "%.4f" % float(lat), "longitude": "%.4f" % float(lon),
        "daily": ("weather_code,temperature_2m_max,temperature_2m_min,uv_index_max,"
                  "precipitation_probability_max,wind_speed_10m_max,"
                  "wind_direction_10m_dominant,sunrise,sunset"),
        "hourly": ("temperature_2m,precipitation_probability,precipitation,weather_code,"
                   "relative_humidity_2m"),
        "temperature_unit": units,
        "wind_speed_unit": "mph" if units == "fahrenheit" else "kmh",
        "timezone": tz,
        "past_days": int(max(0, min(92, past))),
        "forecast_days": int(max(1, min(16, ahead))),
    })
    try:
        d = _cached(API + "?" + q)
    except Exception:
        return {}
    dd, hh = d.get("daily") or {}, d.get("hourly") or {}
    hours = {}
    times = hh.get("time") or []
    for i, t in enumerate(times):
        def hv(k):
            v = hh.get(k) or []
            return v[i] if i < len(v) else None
        hours.setdefault(t[:10], []).append({
            "h": int(t[11:13]), "temp": hv("temperature_2m"),
            "pop": hv("precipitation_probability"), "precip": hv("precipitation"),
            "code": hv("weather_code"), "humidity": hv("relative_humidity_2m")})
    out = {}
    for i, date in enumerate(dd.get("time") or []):
        def g(k):
            v = dd.get(k) or []
            return v[i] if i < len(v) else None
        code = g("weather_code")
        hs = hours.get(date) or []
        hum = [h["humidity"] for h in hs if h["humidity"] is not None]
        out[date] = {
            "hi": g("temperature_2m_max"), "lo": g("temperature_2m_min"),
            "uv": g("uv_index_max"), "pop": g("precipitation_probability_max"),
            "wind": g("wind_speed_10m_max"), "wind_dir": g("wind_direction_10m_dominant"),
            "sunrise": (g("sunrise") or "")[11:16], "sunset": (g("sunset") or "")[11:16],
            "humidity": (sum(hum) / len(hum)) if hum else None,
            "code": code, "icon": _classify(code, g("wind_speed_10m_max"), units)[0],
            "text": _classify(code, g("wind_speed_10m_max"), units)[1],
            "hours": hs,
        }
    return out


def week(lat, lon, start, **kw):
    """The seven days from `start` (a date or 'YYYY-MM-DD'), keyed by ISO date."""
    import datetime as _dt
    if not isinstance(start, _dt.date):
        start = _dt.date.fromisoformat(str(start))
    today = _dt.date.today()
    back = max(0, (today - start).days + 1)
    ahead = max(1, (start + _dt.timedelta(days=7) - today).days + 1)
    got = hourly(lat, lon, past=min(92, back), ahead=min(16, ahead), **kw)
    want = set((start + _dt.timedelta(days=i)).isoformat() for i in range(7))
    return dict((k, v) for k, v in got.items() if k in want)
