"""The world's cities, for the one Location control: type a few letters, pick the city, and PaperDaemon knows the
place's name, latitude and longitude (weather, sunrise) and its holiday region, without the user ever entering any
of them.

The list is every city of 15,000 people or more, from GeoNames (CC BY 4.0), built by tools/build_places.py into
content/places/cities.tsv.gz.
"""

import gzip
import threading
import unicodedata

from . import paths

_ROWS = None
_LOCK = threading.Lock()


_SHORT = {"saint": "st", "sainte": "ste", "mount": "mt", "fort": "ft"}


def _fold(s):
    """What the search compares: lower case, accents and punctuation gone, "Saint" and "St." alike."""
    s = unicodedata.normalize("NFKD", str(s or "")).casefold()
    s = "".join(c if c.isalnum() else " " for c in s if not unicodedata.combining(c))
    return " ".join(_SHORT.get(w, w) for w in s.split())


def _rows():
    global _ROWS
    with _LOCK:
        if _ROWS is None:
            path = paths.content_path("places", "cities.tsv.gz")
            rows = []
            with gzip.open(path, "rt", encoding="utf-8") as f:
                for line in f:
                    p = line.rstrip("\n").split("\t")
                    if len(p) == 9:
                        rows.append((p, _fold(p[0]), _fold(p[1]), _fold(p[2]), _fold(p[3]), p[4].casefold(), p[5].casefold()))
            _ROWS = rows
    return _ROWS


def label(p):
    """"Salt Lake City, Utah, United States" (the region left out when it repeats the city's or the country's name)."""
    parts = [p[0]] + ([p[2]] if p[2] and _fold(p[2]) not in (_fold(p[0]), _fold(p[3])) else []) + [p[3]]
    return ", ".join(x for x in parts if x)


def _place(p):
    return {"label": label(p), "lat": float(p[6]), "lon": float(p[7]),
            "holidays": p[4] + ("-" + p[5] if p[5] and not p[5].isdigit() else "")}


def search(q, limit=8):
    """The cities that `q` names, best first -> [{label, lat, lon, holidays}]. `q` is the start of a city's name,
    optionally followed by a comma and the start of its region or country ("portland, or", "paris, fr")."""
    parts = [_fold(x).strip() for x in str(q or "").split(",")]
    city, rest = parts[0], [x for x in parts[1:] if x]
    if len(city) < 2:
        return []
    exact, starts, inside = [], [], []
    for p, name, ascii_, region, country, cc, a1 in _rows():
        if rest and not all(region.startswith(r) or country.startswith(r) or r in (cc, a1) for r in rest):
            continue
        if name == city or ascii_ == city:
            exact.append(p)
        elif name.startswith(city) or ascii_.startswith(city):
            starts.append(p)
        elif len(city) >= 3 and (" " + city in " " + name or " " + city in " " + ascii_):
            inside.append(p)
        if len(exact) >= limit:
            break
    return [_place(p) for p in (exact + starts + inside)[:limit]]       # rows are biggest first
