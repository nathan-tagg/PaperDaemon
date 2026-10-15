r"""Holidays and observances. The US's by rule (below); every other country's public holidays from the
`holidays` library, in English. No network, no key, no table of dates to go stale.

Two tiers, because the two calendars want different things:

    holiday   the big ones -- the federal holidays and the handful everyone keeps anyway
              (Valentine's, St Patrick's, Easter, Mother's and Father's Day, Halloween, NYE).
              These go on EVERY calendar, weather or not.
    national  observances worth a line on a what's-on calendar: Groundhog Day, Pi Day, Patriot
              Day, Constitution Day, Black Friday ... and the year's turning points as `season`
              (equinoxes, solstices, the clocks changing).

Every name here fits a tablet day cell -- about seventeen characters of this font -- because a
line in a day cell NEVER wraps; the tool cuts what does not fit and drops the icon first.

    >>> us(2026)[datetime.date(2026, 9, 7)]
    [('Labor Day', 'holiday', 'flag')]

`region="US-MA"` adds that state's own holiday, Patriots' Day: an example of how a region adds
holidays of its own on top of the national ones.
"""
import datetime as _dt
import math as _m
import time as _time

KINDS = ("holiday", "national", "season")


# ---------------------------------------------------------------- date rules
def _nth(year, month, weekday, n):
    """The n-th `weekday` (0 = Monday .. 6 = Sunday) of a month; n = -1 for the last one."""
    if n > 0:
        d = _dt.date(year, month, 1)
        d += _dt.timedelta(days=(weekday - d.weekday()) % 7)
        return d + _dt.timedelta(weeks=n - 1)
    d = _dt.date(year + (month == 12), month % 12 + 1, 1) - _dt.timedelta(days=1)
    return d - _dt.timedelta(days=(d.weekday() - weekday) % 7)


def easter(year):
    """Gregorian Easter Sunday (the anonymous algorithm)."""
    a = year % 19
    b, c = divmod(year, 100)
    d, e = divmod(b, 4)
    f = (b + 8) // 25
    g = (b - f + 1) // 3
    h = (19 * a + b - d - g + 15) % 30
    i, k = divmod(c, 4)
    l = (32 + 2 * e + 2 * i - h - k) % 7
    m = (a + 11 * h + 22 * l) // 451
    month = (h + l - 7 * m + 114) // 31
    day = (h + l - 7 * m + 114) % 31 + 1
    return _dt.date(year, month, day)


# Meeus, Astronomical Algorithms ch. 27: the instants of the equinoxes and solstices, good to
# a minute or so for 1000-3000, which is far more than a calendar needs.
_TERMS = [(485, 324.96, 1934.136), (203, 337.23, 32964.467), (199, 342.08, 20.186),
          (182, 27.85, 445267.112), (156, 73.14, 45036.886), (136, 171.52, 22518.443),
          (77, 222.54, 65928.934), (74, 296.72, 3034.906), (70, 243.58, 9037.513),
          (58, 119.81, 33718.147), (52, 297.17, 150.678), (50, 21.02, 2281.226),
          (45, 247.54, 29929.562), (44, 325.15, 31555.956), (29, 60.93, 4443.417),
          (18, 155.12, 67555.328), (17, 288.79, 4562.452), (16, 198.04, 62894.029),
          (14, 199.76, 31436.921), (12, 95.39, 14577.848), (12, 287.11, 31931.756),
          (12, 320.81, 34777.259), (9, 227.73, 1222.114), (8, 15.45, 16859.074)]
_MEAN = {3: (2451623.80984, 365242.37404, 0.05169, -0.00411, -0.00057),
         6: (2451716.56767, 365241.62603, 0.00325, 0.00888, -0.00030),
         9: (2451810.21715, 365242.01767, -0.11575, 0.00337, 0.00078),
         12: (2451900.05952, 365242.74049, -0.06223, -0.00823, 0.00032)}


def _season_instant(year, month):
    """UTC datetime of the March/June/September/December event."""
    y = (year - 2000) / 1000.0
    a, b, c, d, e = _MEAN[month]
    jde0 = a + b * y + c * y ** 2 + d * y ** 3 + e * y ** 4
    t = (jde0 - 2451545.0) / 36525.0
    w = _m.radians(35999.373 * t - 2.47)
    dl = 1 + 0.0334 * _m.cos(w) + 0.0007 * _m.cos(2 * w)
    s = sum(A * _m.cos(_m.radians(B + C * t)) for A, B, C in _TERMS)
    jde = jde0 + 0.00001 * s / dl
    # TT -> UTC: about 69 s this century; a date does not care about the rest
    return _dt.datetime(2000, 1, 1, 12) + _dt.timedelta(days=jde - 2451545.0, seconds=-69)


def standard_offset():
    """This machine's winter (standard-time) offset, in hours east of UTC."""
    return -_time.timezone / 3600.0


def _local_date(utc, month, utc_offset):
    """utc_offset: hours east of UTC in winter; US daylight time is added by rule."""
    off = utc_offset
    if _dst_us(utc.date(), utc_offset):
        off += 1
    return (utc + _dt.timedelta(hours=off)).date()


def _dst_us(day, utc_offset):
    if utc_offset is None or utc_offset >= 0:         # US daylight time only applies west of UTC
        return False
    start = _nth(day.year, 3, 6, 2)          # second Sunday in March
    end = _nth(day.year, 11, 6, 1)           # first Sunday in November
    return start <= day < end


# ---------------------------------------------------------------- the table
def us(year, region="US", utc_offset=None):
    """{date: [(name, kind, icon), ...]} for one year.

    `utc_offset` is the region's standard-time offset in hours east of UTC (US Mountain time is
    -7); it only decides which local DATE an equinox or solstice falls on. None, the default,
    is this machine's own standard-time offset.
    """
    if utc_offset is None:
        utc_offset = standard_offset()
    out = {}

    def add(day, name, kind, icon=None):
        out.setdefault(day, []).append((name, kind, icon))

    D = lambda m, d: _dt.date(year, m, d)
    E = easter(year)

    # -- the big ones
    add(D(1, 1), "New Year's Day", "holiday", "sparkle")
    add(_nth(year, 1, 0, 3), "MLK Day", "holiday", "flag")
    add(D(2, 14), "Valentine's Day", "holiday", "heart")
    add(_nth(year, 2, 0, 3), "Presidents' Day", "holiday", "flag")
    add(D(3, 17), "St Patrick's Day", "holiday", "leaf")
    add(E, "Easter", "holiday", "egg")
    add(_nth(year, 5, 6, 2), "Mother's Day", "holiday", "flower")
    add(_nth(year, 5, 0, -1), "Memorial Day", "holiday", "flag")
    add(_nth(year, 6, 6, 3), "Father's Day", "holiday", "heart")
    add(D(6, 19), "Juneteenth", "holiday", "flag")
    add(D(7, 4), "Independence Day", "holiday", "sparkle")
    add(_nth(year, 9, 0, 1), "Labor Day", "holiday", "flag")
    add(_nth(year, 10, 0, 2), "Columbus Day", "holiday", "flag")
    add(D(10, 31), "Halloween", "holiday", "pumpkin")
    add(D(11, 11), "Veterans Day", "holiday", "flag")
    add(_nth(year, 11, 3, 4), "Thanksgiving", "holiday", "utensils")
    add(D(12, 24), "Christmas Eve", "holiday", "tree")
    add(D(12, 25), "Christmas", "holiday", "gift")
    add(D(12, 31), "New Year's Eve", "holiday", "sparkle")
    if region.upper() in ("US-MA", "MA"):
        add(_nth(year, 4, 0, 3), "Patriots' Day", "holiday", "flag")

    # -- observances
    add(D(2, 2), "Groundhog Day", "national", None)
    add(E - _dt.timedelta(days=47), "Mardi Gras", "national", "party")
    add(D(3, 14), "Pi Day", "national", None)
    add(E - _dt.timedelta(days=2), "Good Friday", "national", None)
    add(D(4, 1), "April Fools' Day", "national", "smile")
    add(D(4, 15), "Tax Day", "national", None)
    add(D(4, 22), "Earth Day", "national", "globe")
    add(_nth(year, 4, 4, -1), "Arbor Day", "national", "tree")
    add(D(5, 1), "May Day", "national", "flower")
    add(_nth(year, 5, 5, 3), "Armed Forces Day", "national", "flag")
    add(D(6, 14), "Flag Day", "national", "flag")
    add(D(9, 11), "Patriot Day", "national", "flag")
    add(_nth(year, 9, 0, 1) + _dt.timedelta(days=6), "Grandparents Day", "national", "heart")
    add(D(9, 17), "Constitution Day", "national", "book")
    add(D(9, 19), "Pirate Day", "national", None)
    add(D(9, 21), "Peace Day", "national", None)
    add(D(9, 29), "Coffee Day", "national", "coffee")
    if year % 2 == 0:
        add(_nth(year, 11, 0, 1) + _dt.timedelta(days=1), "Election Day", "national", "check")
    add(_nth(year, 11, 3, 4) + _dt.timedelta(days=1), "Black Friday", "national", "cart")
    add(D(12, 7), "Pearl Harbor Day", "national", None)
    if year % 4 == 0 and (year % 100 or year % 400 == 0):
        add(D(2, 29), "Leap Day", "season", None)

    # -- the year turning
    for m, name in ((3, "Equinox"), (6, "Solstice"), (9, "Equinox"), (12, "Solstice")):
        add(_local_date(_season_instant(year, m), m, utc_offset), name, "season",
            "sunrise" if m in (3, 6) else "sunset")
    add(_nth(year, 3, 6, 2), "DST starts", "season", "clock")
    add(_nth(year, 11, 6, 1), "DST ends", "season", "clock")
    return out


def table(year, region="US", utc_offset=None):
    """{date: [(name, kind, icon), ...]} for one year in `region` ("US", "US-MA", "GB-ENG", "DE"): the US list
    above for the US; elsewhere the country's public holidays (and its subdivision's, when the library knows the
    code), each a `holiday` with no icon. A country the library does not cover has none."""
    country, _, sub = str(region or "US").upper().partition("-")
    if country == "US":
        return us(year, region, utc_offset)
    import holidays as _lib
    try:
        kind = type(_lib.country_holidays(country))
    except NotImplementedError:
        return {}
    langs = getattr(kind, "supported_languages", ()) or ()
    lang = next((l for l in ("en_US", "en_GB") if l in langs), None)       # None: the country's names are English
    subdiv = sub if sub in (getattr(kind, "subdivisions", ()) or ()) else None
    found = _lib.country_holidays(country, subdiv=subdiv, years=year, language=lang)
    return {day: [(name, "holiday", None) for name in found.get_list(day)] for day in sorted(found)}


def month(year, mo, region="US", kinds=("holiday",), utc_offset=None):
    """{day: [(name, kind, icon), ...]} for one month, only the `kinds` asked for."""
    out = {}
    for day, items in table(year, region, utc_offset).items():
        if day.month != mo:
            continue
        keep = [it for it in items if it[1] in kinds]
        if keep:
            out[day.day] = keep
    return out
