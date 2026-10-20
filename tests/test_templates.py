"""The tablet's page templates (remarkable/templates.py): their formulas, their drawing, and the list of them. The
definitions here are written for the test; the real ones are read from the user's own desktop app."""
import json
import re

from paperdaemon.remarkable import templates as T


def test_formulas_read_as_the_definitions_write_them():
    env = {"templateWidth": 1620.0, "templateHeight": 2160.0, "mobileMaxWidth": 1000.0}
    f = lambda s: T.Formula(s).value(env)
    assert f("templateWidth / 2 - templateHeight / 2 + 469") == 199
    assert f("58.4 * 2") == 116.8
    assert f("templateWidth < mobileMaxWidth || templateHeight < mobileMaxWidth ? (templateWidth / 2 - 150) : 590") == 590
    assert f("-(3 + 4) * 2 % 5") == -4
    assert f("!0 && 2 >= 2") == 1


def test_a_grid_repeats_over_the_whole_page():
    grid = {"constants": [{"size": 100}], "items": [{"type": "group", "boundingBox": {"x": 0, "y": 0, "width": "size", "height": "size"},
                                                     "repeat": {"rows": "infinite", "columns": "infinite"},
                                                     "children": [{"type": "path", "data": ["M", 0, 0, "L", "parentWidth", 0]}]}]}
    out = T.svg(grid, 1000, 1000)
    starts = sorted({tuple(map(float, m)) for m in re.findall(r'd="M([-\d.]+) ([-\d.]+)', out)})
    assert len([s for s in starts if 0 <= s[0] < 1000 and 0 <= s[1] < 1000]) == 100       # every cell of the page
    assert out.startswith('<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 1000 1000"')


def test_counted_rows_and_text_and_the_apps_own_names():
    d = {"constants": [{"x0": "paperOriginX - 10"}],
         "items": [{"type": "group", "boundingBox": {"x": "x0", "y": 100, "width": 20, "height": 50}, "repeat": {"rows": 3},
                    "children": [{"type": "path", "data": ["M", 0, 0, "L", 20, 0], "strokeWidth": 2}]},
                   {"type": "text", "text": "Day:", "fontSize": 40, "position": {"x": "templateWidth - textWidth", "y": 5}}]}
    out = T.svg(d, 1620, 2160)
    assert re.findall(r'd="M([\d.]+) ([\d.]+)', out) == [("800.00", "100.00"), ("800.00", "150.00"), ("800.00", "200.00")]
    x = float(re.search(r'<text x="([\d.]+)"', out).group(1))
    assert 1500 < x < 1620 and ">Day:</text>" in out


def test_blank_has_no_definition_and_the_apps_own_drawings_are_paperdaemons(tmp_path, monkeypatch):
    monkeypatch.setattr(T, "folder", lambda: str(tmp_path))
    (tmp_path / "defs").mkdir()
    (tmp_path / "defs" / "P Grid medium.json").write_text(json.dumps({"name": "Grid medium", "items": []}))
    (tmp_path / "index.json").write_text(json.dumps({"templates": [
        {"name": "Grid medium", "file": "P Grid medium", "drawn": "definition"},
        {"name": "Hexagon large", "file": "P Hexagon large", "drawn": "app"},
        {"name": "Blank", "file": "Blank", "drawn": "blank"}]}))
    mirror = tmp_path / "mirror"
    mirror.mkdir()
    (mirror / "abc.template").write_text(json.dumps({"name": "Meeting minutes", "orientation": "portrait", "items": []}))
    (mirror / "def.template").write_text(json.dumps({"name": "Kanban board", "orientation": "landscape", "items": []}))
    cat = T.catalog(str(mirror))
    assert [t["name"] for t in cat] == ["Blank", "Grid medium", "Hexagon large", "Meeting minutes"]     # portrait only
    assert T.definition(cat[1]) == {"name": "Grid medium", "items": []}
    assert T.definition(cat[0]) is None
    # what the app draws in its own code, PaperDaemon draws itself, marked as an approximation
    assert T.definition(cat[2]) == {"paperdaemon": "Hexagon large"} and cat[2].get("approx") is True
    assert "<path" in T.svg(T.definition(cat[2]), 1620, 2160)
    assert T.definition(cat[3], str(mirror))["name"] == "Meeting minutes"
    assert T.svg(None, 100, 100) == '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 100 100" width="100" height="100"></svg>'
