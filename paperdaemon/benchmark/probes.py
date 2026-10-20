"""The Test tab's own tests: what a lineup can do, measured directly, beside the page cases the pipeline runs.

Each test gives one entry: {"id", "name", "state": "pass" | "partly" | "fail" | "off", "metric", "detail", "m", "d"}
-- `metric` a figure ("Reddit 1.5 s · Hacker News 0.8 s", "92% of words"), `detail` a sentence of what came back.
Both are in English (from the window's own English strings) and also as `m` / `d`: the string's name and its
values, so the window shows them in the user's language. What the world said (an error, a search result's title,
a model's reading) stays as it came. The network tests reach the sites PaperDaemon itself calls (so they also tell
whether this computer has the internet); the handwriting test sends real handwriting to the lineup's text model.
"""
import base64
import io
import json
import os
import re
import time

from .. import paths
from .. import settings as S

SITE_NAMES = {"reddit": "Reddit", "hackernews": "Hacker News", "bluesky": "Bluesky", "4chan": "4chan",
              "mastodon": "Mastodon"}
# where each site's test reads: a quiet, work-safe corner of it
SITE_SOURCE = {"hackernews": "hn", "bluesky": "bsky", "4chan": "4chan/g", "mastodon": "mastodon/mastodon.social"}
HANDWRITING = ("handwriting",)                  # in the content folder (the app ships its own)
PASS_AT, PARTLY_AT = 0.85, 0.5          # the handwriting test: share of words read right

def say(key, params=None):
    """The window's English for string `key`, its {placeholders} filled (the row's English; the window shows the
    user's own language from the row's string names)."""
    from .. import i18n
    return i18n.say(key, params, lang="en")


def _entry(id_, name, state, metric, detail=""):
    return {"id": id_, "name": name, "state": state, "metric": metric, "detail": detail}


def row(id_, state, m, mp=None, d=None, dp=None, raw=None):
    """An entry from string names: `m` the metric's (with its values `mp`), `d` the detail's, or `raw` for a detail
    that is the world's own words."""
    e = _entry(id_, say("ts.row." + id_), state, say("ts.m." + m, mp),
               say("ts.d." + d, dp) if d else (raw or ""))
    e["m"] = ["ts.m." + m, mp or {}]
    if d:
        e["d"] = ["ts.d." + d, dp or {}]
    return e


def _secs(t0):
    return "%.1f" % (time.time() - t0)


def _network_on(s):
    return (s.get("network") or {}).get("allowed") is not False


# ---------------------------------------------------------------- the network

def web_search(s):
    sr = S.active(s).get("search") or {}
    if sr.get("kind") not in ("api", "local"):
        return row("search", "off", "not_set_up", d="search_setup")
    if not _network_on(s):
        return row("search", "off", "network_off", d="allow_network")
    from .. import search
    t0 = time.time()
    try:
        got = search.query("How many moons does Mars have", s=s) or []
    except Exception as ex:
        return row("search", "fail", "no_answer", raw="%s: %s" % (type(ex).__name__, str(ex)[:160]))
    if not got:
        return row("search", "fail", "no_results_in", {"s": _secs(t0)}, d="search_empty")
    top = got[0]
    return row("search", "pass", "results_in", {"n": len(got), "s": _secs(t0)},
               d="first", dp={"title": str(top.get("title") or top.get("url") or "")[:120]})


def social(s):
    from ..settings import SOCIAL_SITES
    sites = [x for x in SOCIAL_SITES if x in SITE_NAMES]          # every site, always
    if not _network_on(s):
        return row("social", "off", "network_off", d="allow_network")
    from ..pipeline.charts import reddit, social as so
    pieces, ok, bad = [], 0, []
    for site in sites:
        t0 = time.time()
        try:
            if site == "reddit":
                posts = reddit.posts("todayilearned", limit=3)
            else:
                posts, why = so.fetch(SITE_SOURCE[site], count=3)
                if posts is None:
                    raise RuntimeError(why)
            if not posts:
                raise RuntimeError("no posts")
            pieces.append(["ts.m.site_time", {"site": SITE_NAMES[site], "s": _secs(t0)}])
            ok += 1
        except Exception as ex:
            pieces.append(["ts.m.site_failed", {"site": SITE_NAMES[site]}])
            bad.append("%s: %s" % (SITE_NAMES[site], str(ex)[:80] or type(ex).__name__))
    state = "pass" if ok == len(sites) else "partly" if ok else "fail"
    e = row("social", state, "site_time", d=None if bad else "every_site", raw="; ".join(bad))
    e["metric"] = " · ".join(say(k, p) for k, p in pieces)
    e["m"] = ["list", pieces]                    # each site's piece, joined on screen
    return e


def weather(s):
    if not _network_on(s):
        return row("weather", "off", "network_off", d="allow_network")
    loc = s.get("location") or {}
    lat, lon, place = loc.get("lat"), loc.get("lon"), loc.get("name") or ""
    london = lat is None or lon is None              # no location yet: the test still asks, for somewhere
    if london:
        lat, lon, place = 51.5072, -0.1276, "London"
    from ..pipeline.charts import weather as wx
    t0 = time.time()
    days = wx.daily(lat, lon, past=0, ahead=1)
    if not days:
        return row("weather", "fail", "no_forecast", d="no_forecast")
    today = days[sorted(days)[0]]
    unit = "°F" if wx.temperature_units() == "fahrenheit" else "°C"
    hi, lo = round(today.get("hi", 0)), round(today.get("lo", 0))
    return row("weather", "pass", "weather", {"t": hi, "unit": unit, "sky": str(today.get("text") or "clear").lower(),
                                               "s": _secs(t0)},
               d="weather_london" if london else "weather",
               dp={"place": place.split(",")[0], "hi": hi, "lo": lo, "unit": unit})


def _norm(w):
    return re.sub(r"[^a-z0-9']", "", w.lower())


def word_score(said, words):
    """How many of the page's words the reading has, each counted once -> (right, total)."""
    from collections import Counter
    got = Counter(_norm(w) for w in re.split(r"\s+", said or "") if _norm(w))
    want = [_norm(w) for w in words if _norm(w)]
    right = 0
    for w in want:
        if got[w] > 0:
            got[w] -= 1
            right += 1
    return right, len(want)


def handwriting(s, cancel=None):
    from ..models import adapters, slots
    from .. import card
    folder = paths.content_path(*HANDWRITING)
    try:
        with open(os.path.join(folder, "samples.json"), encoding="utf-8") as f:
            samples = json.load(f)["samples"]
    except (OSError, ValueError, KeyError):
        return row("handwriting", "fail", "no_samples", d="samples_missing")
    caps, harness = slots.caps("text", s), slots.harness("text", s)
    if not caps.get("vision"):
        return row("handwriting", "off", "cannot_see", d="cannot_see")
    a = adapters.for_slot("text", s)
    right = total = 0
    secs, regions = [], {}
    for smp in samples:
        if cancel is not None and cancel.is_set():
            break
        with open(os.path.join(folder, smp["file"]), "rb") as f:
            jpg = f.read()
        t0 = time.time()
        try:
            with card.call("text"):
                r = a.chat("You read handwriting exactly as written.",
                           [{"role": "user", "text": "Transcribe all the handwriting in this picture, word for word, in "
                                                     "reading order. Reply with the text only.", "images": [jpg]}],
                           caps=dict(caps, vision=True), harness=harness, temperature=0)
            said = r.get("text") or ""
        except Exception as ex:
            return row("handwriting", "fail", "no_reading", raw="%s: %s" % (type(ex).__name__, str(ex)[:160]))
        secs.append(time.time() - t0)
        k, n = word_score(said, smp["words"])
        right, total = right + k, total + n
        reg = regions.setdefault(smp["region"], [0, 0])
        reg[0] += k
        reg[1] += n
    if not total:
        return row("handwriting", "fail", "nothing_read")
    share = right / float(total)
    state = "pass" if share >= PASS_AT else "partly" if share >= PARTLY_AT else "fail"
    per = ", ".join("%s %d%%" % (r, round(100.0 * a_ / b)) for r, (a_, b) in sorted(regions.items()) if b)
    return row("handwriting", state, "words", {"pct": round(100 * share), "s": "%.0f" % (sum(secs) / len(secs))},
               d="words", dp={"right": right, "total": total, "pages": len(secs), "regions": per})


