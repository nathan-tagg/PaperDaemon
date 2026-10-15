"""Defaults come from the computer's region settings, and only until the user chooses."""
from paperdaemon import paths, region


def test_region_defaults_are_valid_choices():
    d = region.defaults()
    assert len(d["country"]) == 2 and d["country"].isupper()
    assert d["temperature"] in ("fahrenheit", "celsius") and d["clock"] in ("12", "24")
    assert d["week_start"] in ("sunday", "monday", "saturday")


def test_a_choice_beats_the_region(monkeypatch):
    monkeypatch.setattr(region, "defaults", lambda: {"country": "DE", "temperature": "celsius", "clock": "24",
                                                     "week_start": "monday"})
    monkeypatch.setattr(paths, "_setting", lambda key: {"prefs": {"clock": "12"}}.get(key))
    assert paths.prefs() == {"temperature": "celsius", "clock": "12", "week_start": "monday"}
    assert paths.home() == ("", None, None, "DE")          # no location: no place, the computer's country
