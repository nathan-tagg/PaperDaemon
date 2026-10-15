"""PaperDaemon's own calls to the internet: the weather, social posts, Wikipedia, maps, web search, pictures from
the web. Each goes through `urlopen` here, so the "Allow network access" setting stops all of them in one place.
Calls to the models (through the engine) and to the reMarkable cloud are not these, and are never stopped here.
"""
import urllib.request


class Off(OSError):
    """Network access is switched off in the settings. An OSError, so a caller that already treats a failed
    fetch as "nothing came back" does the same here."""


def allowed():
    from paperdaemon import paths
    v = (paths._setting("network") or {}).get("allowed")
    return v is not False


def urlopen(req, timeout=None):
    """urllib.request.urlopen, unless network access is off in the settings (then Off)."""
    if not allowed():
        raise Off("network access is off in PaperDaemon's settings")
    return urllib.request.urlopen(req, timeout=timeout)
