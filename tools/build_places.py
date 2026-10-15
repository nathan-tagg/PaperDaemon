"""Build the city list behind the Overview's Location control: paperdaemon/content/places/cities.tsv.gz.

The source is GeoNames (https://www.geonames.org), CC BY 4.0: every city of 15,000 people or more
(cities15000.zip), with the names of the regions (admin1CodesASCII.txt) and the countries (countryInfo.txt).
Download those three into a folder and run:

    .venv/Scripts/python.exe tools/build_places.py <that folder>

Each row: name, ASCII name, region, country, country code, region code, latitude, longitude, population.
"""

import gzip
import io
import os
import sys
import zipfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT = os.path.join(ROOT, "paperdaemon", "content", "places", "cities.tsv.gz")


def _lines(path):
    with open(path, encoding="utf-8") as f:
        for line in f:
            if line.strip() and not line.startswith("#"):
                yield line.rstrip("\n").split("\t")


def build(src):
    countries = {r[0]: r[4] for r in _lines(os.path.join(src, "countryInfo.txt")) if len(r) > 4}
    regions = {r[0]: r[1] for r in _lines(os.path.join(src, "admin1CodesASCII.txt")) if len(r) > 1}
    cities = os.path.join(src, "cities15000.txt")
    if not os.path.isfile(cities):
        with zipfile.ZipFile(os.path.join(src, "cities15000.zip")) as z:
            z.extract("cities15000.txt", src)
    rows = []
    for r in _lines(cities):
        if len(r) < 15:
            continue
        name, ascii_, lat, lon, cc, a1, pop = r[1], r[2], r[4], r[5], r[8], r[10], r[14]
        clean = lambda s: s.replace("\t", " ").strip()
        rows.append((clean(name), clean(ascii_), clean(regions.get(cc + "." + a1, "")), clean(countries.get(cc, cc)),
                     cc, a1, "%.4f" % float(lat), "%.4f" % float(lon), str(int(pop or 0))))
    rows.sort(key=lambda x: -int(x[8]))                       # the biggest first: the search's tie-break
    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    buf = io.StringIO()
    for row in rows:
        buf.write("\t".join(row) + "\n")
    with gzip.GzipFile(OUT, "wb", mtime=0) as g:              # mtime 0: the same input builds the same file
        g.write(buf.getvalue().encode("utf-8"))
    return len(rows)


if __name__ == "__main__":
    if len(sys.argv) != 2:
        sys.exit(__doc__)
    print("%d cities -> %s" % (build(sys.argv[1]), OUT))
