# Places

`cities.tsv.gz` lists every city of 15,000 people or more, for the Overview's Location control. It is built
from [GeoNames](https://www.geonames.org) data (cities15000, admin1CodesASCII, countryInfo) by
`tools/build_places.py`, and is licensed under the
[Creative Commons Attribution 4.0 License](https://creativecommons.org/licenses/by/4.0/). The fields were
selected and the coordinates rounded to four decimals; nothing else was changed.

Each row: name, ASCII name, region, country, country code, region code, latitude, longitude, population.
