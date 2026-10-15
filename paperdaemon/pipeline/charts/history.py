r"""On-this-day facts from Wikipedia, for a calendar's history lines.

Wikimedia's feed API. No key, one request per day of the month, cached for good under
<geo cache>/history (see paths.geo_dir) because history does not change. What comes back is
the raw material:

    >>> month(9)[23]
    [(1846, 'Astronomers Johann Gottfried Galle and Heinrich Louis d\'Arrest discovered Neptune ...'), ...]

A tablet day cell holds about TWELVE characters and never wraps. This module does not try to
squeeze a sentence into that -- a program cutting at twelve characters produces gibberish, a
model reading the sentence produces a headline ("1846 Neptune"). So: fetch with this, read,
write the short form into the spec as an event with kind="history".

`kind` is Wikimedia's list: "selected" (a curated dozen or two), "events" (everything), "births",
"deaths", "holidays".
"""
import io
import json
import os
import urllib.request
from paperdaemon import paths
from paperdaemon import net as _net

CACHE = os.path.join(paths.geo_dir(), "history")
URL = "https://api.wikimedia.org/feed/v1/wikipedia/en/onthisday/%s/%02d/%02d"
UA = "PaperDaemon/1.0 (reMarkable assistant)"


def day(mo, d, kind="selected"):
    """[(year, text), ...] for one date, newest first as Wikimedia sends them."""
    os.makedirs(CACHE, exist_ok=True)
    f = os.path.join(CACHE, "%02d-%02d-%s.json" % (mo, d, kind))
    if os.path.exists(f):
        data = json.load(io.open(f, encoding="utf-8"))
    else:
        req = urllib.request.Request(URL % (kind, mo, d), headers={"User-Agent": UA})
        with _net.urlopen(req, timeout=30) as r:
            data = json.loads(r.read().decode("utf-8"))
        io.open(f, "w", encoding="utf-8").write(json.dumps(data))
    seen, out = set(), []
    for e in data.get(kind, []):
        key = (e.get("year"), (e.get("text") or "")[:60])
        if key in seen:                       # the feed repeats entries
            continue
        seen.add(key)
        out.append((e.get("year"), e.get("text") or ""))
    return out


def month(mo, kind="selected", year=2026):
    """{day: [(year, text), ...]} for every day of the month. {} on network failure."""
    import calendar
    out = {}
    for d in range(1, calendar.monthrange(year, mo)[1] + 1):
        try:
            out[d] = day(mo, d, kind)
        except Exception:
            pass
    return out


def find(mo, words, kind="events", year=2026):
    """The (day, year, text) entries whose text mentions any of `words`. For checking a fact."""
    hits = []
    for d, items in month(mo, kind, year).items():
        for y, t in items:
            low = t.lower()
            if any(w.lower() in low for w in words):
                hits.append((d, y, t))
    return hits
