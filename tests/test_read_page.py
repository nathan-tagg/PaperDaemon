"""Another page of the notebook can be read while the model rules and plans: its typed text, exact, and its handwriting
as read. A request on page 2 about "my budget on page 1" had the host ask the user to type the list again."""
import json


def _begin():
    from paperdaemon.pipeline import draw as A
    from paperdaemon.pipeline import host as H
    from paperdaemon.pipeline.host import job as J
    J.begin(doc="nodoc", page=2, frame=(1620.0, 2160.0), draw=A.Drawing(), ops=[])
    return H


def test_the_other_page_comes_back_in_words(monkeypatch, tmp_path):
    H = _begin()
    from paperdaemon import reader
    from paperdaemon.pipeline.host.features import find as F
    from paperdaemon.pipeline.page import render as R
    from paperdaemon.pipeline.page import typed as TY
    monkeypatch.setattr(R, "live_pages", lambda doc: [{"id": "a"}, {"id": "b"}, {"id": "c"}])
    monkeypatch.setattr(TY, "paragraphs", lambda doc, page: (None, [{"text": "Trip budget"}, {"text": "flights 420"}, {"text": " "}]))
    monkeypatch.setattr(R, "render", lambda *a, **k: (0, (1620, 2160), [], [], (0, 0)))
    monkeypatch.setattr(reader, "read_picture", lambda png, scale=2: [
        {"text": "hotel", "x": 10, "line": 0}, {"text": "610", "x": 90, "line": 0}, {"text": "food", "x": 10, "line": 1}])
    monkeypatch.setattr(H, "QUEUE", str(tmp_path))
    out = F._read_page({"page": 1}, "nodoc", 2)
    assert out == {"page": 1, "typed": ["Trip budget", "flights 420"], "written": ["hotel 610", "food"]}
    assert json.dumps(out)                                  # what the model is handed


def test_the_wrong_pages_are_refused_by_name(monkeypatch):
    H = _begin()
    from paperdaemon.pipeline.host.features import find as F
    from paperdaemon.pipeline.page import render as R
    monkeypatch.setattr(R, "live_pages", lambda doc: [{"id": "a"}, {"id": "b"}])
    assert "this page" in F._read_page({"page": 2}, "nodoc", 2)["error"]
    assert "2 pages" in F._read_page({"page": 5}, "nodoc", 2)["error"]
    assert "number" in F._read_page({}, "nodoc", 2)["error"]
    assert "read_page" in __import__("paperdaemon.pipeline.host.jobs", fromlist=["LOOK_TOOLS"]).LOOK_TOOLS
