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


def test_a_table_entry_longer_than_its_column_goes_on_two_lines_in_its_cell(tmp_path):
    # DF110: eight columns at the smallest size, and "Set table, Recycling" was cut to "Set table, Recyclin"
    svg = tmp_path / "t.svg"
    spec = {"type": "table", "columns": ["Person", "Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"],
            "rows": [["Max", "Set table", "Set table", "Set table, Recycling", "Set table", "Set table", "", ""],
                     ["Ella", "Feed dog", "", "", "", "", "", ""]]}
    C.render(spec, png_path=str(tmp_path / "t.png"), svg_path=str(svg))
    shown = _texts(svg.read_text(encoding="utf-8"))
    assert "Set table," in shown and "Recycling" in shown and "Set table, Recycling" not in shown
    assert "Feed dog" in shown                            # what fits stays on one line


def test_a_line_charts_markers_and_dashes_follow_the_series_order_and_one_line_has_no_key():
    # "Mia" then "Liam": scales without a domain sorted the names, and Mia's dashed blue line ran through Liam's squares
    spec = {"type": "line", "title": "Reading", "categories": ["Mon", "Tue"],
            "series": [{"name": "Mia", "values": [20, 35]}, {"name": "Liam", "values": [10, 25]}]}
    vl = C.to_vegalite(spec)
    layers = [l for l in vl.get("layer") or [] if isinstance(l, dict)]
    domains = [ch["scale"]["domain"] for l in layers for ch in (l.get("encoding") or {}).values()
               if isinstance(ch, dict) and ch.get("field") in ("s", "m") and "scale" in ch]
    assert len(domains) >= 4 and all(d == ["Mia", "Liam"] for d in domains)
    one = C.to_vegalite(dict(spec, series=spec["series"][:1]))
    colors = [l["encoding"]["color"] for l in one.get("layer") or [] if "color" in (l.get("encoding") or {})]
    assert colors and colors[0]["legend"] is None          # a single line needs no key


def test_a_line_charts_key_is_its_lines_not_its_markers(tmp_path):
    # Liam's dashed line was keyed as a square with a dashed edge and a tail: the marker layer's shapes became the key
    svg = tmp_path / "k.svg"
    spec = {"type": "line", "title": "Reading", "categories": ["Mon", "Tue", "Wed"],
            "series": [{"name": "Mia", "values": [20, 35, 15]}, {"name": "Liam", "values": [10, 25, 30]}]}
    C.render(spec, png_path=str(tmp_path / "k.png"), svg_path=str(svg))
    text = svg.read_text(encoding="utf-8")
    legend = text[text.find("role-legend"):]
    symbols = re.findall(r'role-legend-symbol[^>]*>\s*<path[^>]*d="([^"]+)"', legend)
    assert symbols and all(s.startswith("M-") and "L" in s and "A" not in s and "h" not in s for s in symbols[:2])
