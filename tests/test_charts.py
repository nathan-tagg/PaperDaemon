"""Charts keep the data's order (never alphabetized), and a month calendar draws with no location set (no weather,
no sunrise) as well as with one, offline."""
import re

from paperdaemon.pipeline import charts as C


def _texts(svg):
    return [t for t in re.findall(r">([^<>]+)</text>", svg)]


def test_categories_keep_their_order(tmp_path):
    svg = tmp_path / "c.svg"
    spec = {"type": "bar", "title": "Fruit", "categories": ["pear", "apple", "zucchini", "banana"],
            "series": [{"name": "kg", "values": [3, 5, 1, 4]}]}
    C.render(spec, png_path=str(tmp_path / "c.png"), svg_path=str(svg))
    shown = [t for t in _texts(svg.read_text(encoding="utf-8")) if t in spec["categories"]]
    assert shown == ["pear", "apple", "zucchini", "banana"]


def test_a_month_draws_with_and_without_a_location(tmp_path, monkeypatch):
    from paperdaemon import net
    monkeypatch.setattr(net, "allowed", lambda: False, raising=False)     # offline: nothing is fetched
    for loc in ({}, {"lat": 40.23, "lon": -111.66}):           # the host puts the user's place in the spec
        png = C.render(dict({"type": "calendar", "year": 2026, "month": 10}, **loc), png_path=str(tmp_path / "m.png"))
        assert png[:8] == b"\x89PNG\r\n\x1a\n" and len(png) > 5000

