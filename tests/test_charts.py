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



def test_trend_and_average_lines_are_worked_out_by_the_host(tmp_path):
    # the dogfood's bills: a model's own trend ran "down, 132 to 90"; the least-squares fit runs 119.2 to 123.2, up
    bills = [142, 131, 118, 96, 88, 104, 139, 151, 122]
    spec = {"type": "line", "title": "Electric bills", "categories": ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul",
            "Aug", "Sep"], "series": [{"name": "Bills", "values": bills}], "trend": True, "average": True}
    C.validate(spec)
    lines = {d["kind"]: d for d in C.derived_lines(spec)}
    trend, avg = lines["trend"]["values"], lines["average"]["values"]
    assert round(trend[0], 1) == 119.2 and round(trend[-1], 1) == 123.2 and len(trend) == 9
    assert all(abs(v - sum(bills) / 9.0) < 1e-9 for v in avg)
    svg = tmp_path / "c.svg"
    for t in ("line", "step", "bar"):
        C.render(dict(spec, type=t), png_path=str(tmp_path / "c.png"), svg_path=str(svg))
        assert {"Trend", "Average"} <= set(_texts(svg.read_text(encoding="utf-8")))
    for bad in (dict(spec, trend="yes"), dict(spec, type="pie", categories=["a", "b"],
                                                series=[{"name": "s", "values": [1, 2]}])):
        try:
            C.validate(bad)
            raise AssertionError("accepted %r" % bad)
        except C.SpecError:
            pass
