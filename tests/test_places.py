"""The Location control's city search: a few letters name a city, and its coordinates and holiday region come with it."""
from paperdaemon import places


def test_a_city_brings_its_coordinates_and_region():
    top = places.search("salt la")[0]
    assert top["label"] == "Salt Lake City, Utah, United States"
    assert abs(top["lat"] - 40.76) < 0.01 and abs(top["lon"] + 111.89) < 0.01
    assert top["holidays"] == "US-UT"


def test_region_or_country_after_a_comma_narrows_it():
    assert places.search("portland, or")[0]["label"] == "Portland, Oregon, United States"
    assert places.search("portland, me")[0]["label"] == "Portland, Maine, United States"
    assert places.search("new york, ny")[0]["holidays"] == "US-NY"
    assert all("United States" in p["label"] for p in places.search("paris, us"))


def test_accents_punctuation_and_saint():
    assert places.search("zurich")[0]["label"].startswith("Zürich")
    assert places.search("st george, ut")[0]["label"] == "Saint George, Utah, United States"
    assert places.search("st. louis")[0]["label"].startswith("St. Louis, Missouri")


def test_too_short_or_unknown_names_nothing():
    assert places.search("x") == []
    assert places.search("qqqzzz") == []
