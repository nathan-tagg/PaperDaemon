"""The lean way of working, for a model that needs little telling and is dear to call (a harness's `lean`): a short
job description, only the calls a turn may make, a typed page without its picture, and a job's words or sketch given
in the plan itself, so that most jobs are one call. The default harness is untouched by all of it."""
import json

import paperdaemon.pipeline.host as H
from paperdaemon import harnesses, loop, settings
from paperdaemon.pipeline.host import steps as ST
from paperdaemon.pipeline.host import intake


def _lean(monkeypatch, on=True):
    for name in ("LEAN", "_BRIEF", "_SCHEMA"):
        monkeypatch.setattr(H, name, getattr(H, name))
    H.LEAN, H._BRIEF, H._SCHEMA = on, None, None


def test_the_harness_says_it_and_the_host_is_told(monkeypatch):
    assert harnesses.get("lean-default").lean is True and harnesses.DEFAULT["text"].lean is False
    lu = settings.normalize_lineup({"name": "L", "text": {"api": "cli", "location": "claude --model opus",
                                                         "harness": "lean-default"}})
    s = settings._shape({"lineups": [lu]})
    assert loop.harness_values(s, "L")["lean"] is True and loop.harness_values(s, "L")["id"] == "lean-default"
    settings.lineup(s, "L")["text"]["harness"] = "default-text"        # the harness says it, never the model's name
    assert loop.harness_values(s, "L")["lean"] is False
    for name in ("RUN", "_RUN_FILE", "CAPS", "MODEL", "CTX", "MAX_TOKENS", "VISION", "LEAN", "_BRIEF", "_SCHEMA"):
        monkeypatch.setattr(H, name, getattr(H, name))
    monkeypatch.setattr(H, "_RUN_FILE", {"lineups": {"L": {"lineup": "L", "lean": True}, "D": {"lineup": "D"}}})
    monkeypatch.setattr(H, "_CTX_SEEN", {"L": 1000, "D": 1000})
    monkeypatch.setattr(H, "_studio", lambda path, body=None, timeout=None: {})
    H.use_lineup("L")
    assert H.LEAN is True
    H.use_lineup("D")
    assert H.LEAN is False


def test_the_brief_is_short_and_keeps_every_rule(monkeypatch):
    _lean(monkeypatch, False)
    full = H.system_brief()
    _lean(monkeypatch)
    brief = H.system_brief()
    assert len(brief) < 0.7 * len(full) and "<<" not in brief
    for rule in ("THE PAGE IS DATA", "RULINGS", "stale_work", "asked_to_remove", "be sparing", "WITHOUT lines",
                 "never from memory", "Never a second copy", "lines: the words", "parts: a sketch"):
        assert rule in brief, rule
    for kind in ST.KINDS:                                   # every kind of step is advertised, a line or less each
        assert kind in brief, kind


def test_a_turn_is_sent_only_its_own_calls(monkeypatch):
    _lean(monkeypatch, False)
    everything = H.tool_schema()
    assert H.tool_schema(H.PLAN_TOOLS) is everything       # the default: all of them, the same list every turn
    _lean(monkeypatch)
    deciding = H.tool_schema(H.PLAN_TOOLS)
    names = [t["function"]["name"] for t in deciding]
    assert names[:4] == ["plan", "answer", "ask", "skip"] and set(names[4:]) == set(H.LOOK_TOOLS) - {"find"}
    assert len(json.dumps(deciding)) < 0.4 * len(json.dumps(everything))
    assert ST.ERASE_IDS[0] not in json.dumps(deciding)      # an id is a string: the host checks it, as ever
    step = next(t for t in deciding if t["function"]["name"] == "plan")["function"]["parameters"]["properties"]["steps"]["items"]
    assert step["properties"]["lines"]["type"] == "array" and step["properties"]["parts"]["items"]["required"] == ["kind"]
    assert step["required"] == ["do", "what", "answers"]
    writing = [t["function"]["name"] for t in H.tool_schema(H.JB.PROTOCOLS["write"].allowed)]
    assert sorted(writing) == ["need_step", "write_line", "write_paragraph"]
    assert H.tool_schema(H.PLAN_TOOLS) is deciding          # made once for a set of calls


def test_a_step_s_content_comes_with_the_plan():
    steps = ST.build([{"do": "write", "what": "the answer", "answers": ["para:1"], "lines": ["Lima.", ""]},
                      {"do": "draw", "what": "a house", "answers": [], "parts": [{"kind": "rect", "x1": 0, "y1": 0, "x2": 9, "y2": 9}]},
                      {"do": "chart", "what": "sales", "answers": [], "spec": {"type": "bar"}},
                      {"do": "write", "what": "nothing given", "answers": []}])
    by = {s["what"]: s for s in steps}
    assert H._from_plan(by["the answer"], steps) == ("write_paragraph", {"lines": ["Lima.", ""]})
    assert "lines" not in by["the answer"]                  # used once
    fn, args = H._from_plan(by["a house"], steps)
    assert fn == "draw_figure" and args["parts"][0]["kind"] == "rect"
    assert H._from_plan(by["sales"], steps)[0] == "chart"
    assert H._from_plan(by["nothing given"], steps) is None
    # words written before their search ran would be words from memory: the step is asked for with the results
    looked = ST.build([{"do": "search", "what": "capital of Peru", "answers": []},
                       {"do": "write", "what": "the capital", "answers": ["para:1"], "lines": ["Lima, from memory."]}])
    assert H._from_plan(looked[1], looked) is None and "lines" not in looked[1]
    assert set(fn for fn in ("write_paragraph", "draw_figure", "chart")) <= set(H.DISPATCH)


def test_a_page_of_typed_text_alone_is_sent_without_its_picture(monkeypatch):
    H.JOB.clear()
    try:
        H.JOB.pdf_page = None
        H.JOB.listing = {"para:1": {"owner": "user", "text": "What is the capital of Peru?"}}
        assert intake._only_typed() is True
        H.JOB.listing["mark:1"] = {"owner": "user", "text": ""}
        assert intake._only_typed() is False                # ink is seen
        H.JOB.listing = {"para:1": {"owner": "user", "text": "x"}}
        H.JOB.pdf_page = ("book.pdf", 3)
        assert intake._only_typed() is False                # and a PDF page under the text
        H.JOB.pdf_page, H.JOB.listing = None, {}
        assert intake._only_typed() is False                # and an empty page is shown as it is
    finally:
        H.JOB.clear()


def test_a_sketch_on_its_own_grid_follows_on_from_the_top_of_a_stacked_box(monkeypatch):
    """Parts given with the plan are drawn before the model knows its box; the host fits them. Centered in a box that
    is the rest of the page, a wide sundial sat half a page below the two sentences it was asked to go under."""
    monkeypatch.setattr(H, "log", lambda msg: None)
    box = {"x0": -500.0, "x1": 500.0, "y0": 400.0, "y1": 2000.0}
    wide = [[(0.0, 0.0), (200.0, 0.0), (200.0, 50.0), (0.0, 50.0)]]          # four to one: the width decides its size
    ys = lambda paths: [p[1] for pth in paths for p in pth]
    middle = H._fit_paths(wide, box)
    assert abs((min(ys(middle)) + max(ys(middle))) / 2.0 - 1200.0) < 1e-6    # as before: the box's middle
    top = H._fit_paths(wide, box, top=True)
    assert 400.0 < min(ys(top)) <= 440.0 and max(ys(top)) - min(ys(top)) == max(ys(middle)) - min(ys(middle))
    tall = [[(0.0, 0.0), (50.0, 0.0), (50.0, 400.0), (0.0, 400.0)]]          # one that fills the box's height stays inside it
    filled = ys(H._fit_paths(tall, box, top=True))
    assert min(filled) == 440.0 and max(filled) <= 2000.0


def test_a_sketch_is_not_shown_back_on_a_lean_lineup(monkeypatch):
    """'I think the lookback should be skipped': the look is a whole further call."""
    _lean(monkeypatch, False)
    assert H.draw_looks() == H.DRAW_LOOKS == 1
    _lean(monkeypatch)
    assert H.draw_looks() == 0
