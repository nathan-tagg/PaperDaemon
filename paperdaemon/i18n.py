"""Words the engine puts in front of the user (on a page, in a record the window shows) in the user's language: the
window's own strings (ui/strings/strings-<code>.xml), so there is one place for every word and one translation."""
import os
import re

_HERE = os.path.dirname(os.path.abspath(__file__))
_STRINGS = {}


def strings(code):
    """{name: text} of one language, or {} when there is no such file."""
    if code not in _STRINGS:
        import xml.etree.ElementTree as ET
        path = os.path.join(_HERE, "ui", "strings", "strings-%s.xml" % code)
        try:
            _STRINGS[code] = {s.get("name"): s.text or "" for s in ET.parse(path).getroot().iter("string")}
        except (OSError, ET.ParseError):
            _STRINGS[code] = {}
    return _STRINGS[code]


def language():
    """The language the user chose for PaperDaemon (Settings), English when none is set."""
    try:
        from . import settings
        return str((settings.load().get("prefs") or {}).get("language") or "en")
    except Exception:
        return "en"


def clock(when=None):
    """A time of day as the user reads one: Settings' clock (12 or 24 hours), else the system's own format."""
    import time
    t = time.localtime(when)
    try:
        from . import settings
        pref = str((settings.load().get("prefs") or {}).get("clock") or "")
    except Exception:
        pref = ""
    if pref == "24":
        return time.strftime("%H:%M", t)
    if pref == "12":
        return time.strftime("%I:%M %p", t).lstrip("0")
    try:                                     # the system's short time (Windows: GetTimeFormatEx, no seconds)
        import ctypes
        from ctypes import wintypes

        class SYSTEMTIME(ctypes.Structure):
            _fields_ = [(n, wintypes.WORD) for n in ("wYear", "wMonth", "wDayOfWeek", "wDay", "wHour", "wMinute",
                                                     "wSecond", "wMilliseconds")]
        st = SYSTEMTIME(t.tm_year, t.tm_mon, (t.tm_wday + 1) % 7, t.tm_mday, t.tm_hour, t.tm_min, t.tm_sec, 0)
        buf = ctypes.create_unicode_buffer(64)
        if ctypes.windll.kernel32.GetTimeFormatEx(None, 2, ctypes.byref(st), None, buf, 64):     # 2: no seconds
            return buf.value
    except Exception:
        pass
    return time.strftime("%H:%M", t)


def say(key, params=None, lang=None):
    """String `key` in `lang` (the user's language by default), its {placeholders} filled; English when that language
    lacks it."""
    text = strings(lang or language()).get(key)
    if text is None:
        text = strings("en").get(key, key)
    p = params or {}
    return re.sub(r"\{(\w+)\}", lambda m: str(p[m.group(1)]) if m.group(1) in p else m.group(0), text)
