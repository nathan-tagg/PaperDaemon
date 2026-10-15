"""The defaults a new user starts with, read from the computer's own region settings: the country (for holidays),
the temperature scale (from the measurement system), the clock and the first day of the week. Never a city, and
nothing from the network: where the user lives is theirs to say (Settings, Location)."""
import functools
import sys

FALLBACK = {"country": "US", "temperature": "fahrenheit", "clock": "12", "week_start": "sunday"}
_DAYS = {"0": "monday", "5": "saturday", "6": "sunday"}           # Windows' first-day numbers -> ours


@functools.lru_cache(maxsize=1)
def defaults():
    """{"country": ISO code, "temperature", "clock", "week_start"} from Windows' region settings; FALLBACK for
    anything the system does not say (and on other systems)."""
    out = dict(FALLBACK)
    if sys.platform != "win32":
        return out
    try:
        import ctypes
        k = ctypes.windll.kernel32
        buf = ctypes.create_unicode_buffer(85)

        def info(kind):                                   # the user's own locale (LOCALE_NAME_USER_DEFAULT)
            return buf.value if k.GetLocaleInfoEx(None, kind, buf, 85) else ""

        if k.GetGeoInfoW(k.GetUserGeoID(16), 4, buf, 85, 0):         # GEOCLASS_NATION, GEO_ISO2
            out["country"] = buf.value.upper() or out["country"]
        measure = info(0x0D)                              # LOCALE_IMEASURE: 0 metric, 1 US
        if measure in ("0", "1"):
            out["temperature"] = "fahrenheit" if measure == "1" else "celsius"
        clock = info(0x23)                                # LOCALE_ITIME: 0 12-hour, 1 24-hour
        if clock in ("0", "1"):
            out["clock"] = "24" if clock == "1" else "12"
        first = info(0x100C)                              # LOCALE_IFIRSTDAYOFWEEK: 0 Monday .. 6 Sunday
        if first in _DAYS:
            out["week_start"] = _DAYS[first]
    except Exception:
        pass
    return out
