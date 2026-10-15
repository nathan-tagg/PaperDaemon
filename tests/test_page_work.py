"""What the host's work leaves on a page, checked on the benchmark's fixture pages with scripted model replies (the
replay's runner, tools/replay.py): a chart goes on as a picture filling its box's width, and a chart redone goes in
the old one's place, which comes off; a mark-up lands on the words it names, typed or handwritten, and never on the
request being erased. A script is not a model: these guard what the host does with a decision, not the decision."""
import json
import os
import subprocess
import sys
import textwrap

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "tools"))
import replay  # noqa: E402

pytestmark = pytest.mark.filterwarnings("ignore::DeprecationWarning")


def _job(work, fixture, replies):
    return replay.run_case("page-work", {"fixture": fixture, "replies": replies}, work=str(work))


def _look(work, body):
    """Run `body` against the work folder's mirror and ledger in a process of its own (the pipeline reads where
    its files are when it is imported); its last printed line is JSON."""
    code = "import json, sys\nsys.path.insert(0, %r)\n" % ROOT + textwrap.dedent(body)
    env = dict(os.environ, RM_MIRROR=str(work / "mirror"), RM_CACHE=str(work / "mirror"), RM_STATE=str(work / "state"),
               PAPERDAEMON_HOME=str(work / "home"), PYTHON_KEYRING_BACKEND="keyring.backends.null.Keyring")
    out = subprocess.run([sys.executable, "-c", code], env=env, capture_output=True, text=True, timeout=300, cwd=ROOT)
    assert out.returncode == 0, out.stderr[-3000:]
    return json.loads(out.stdout.strip().splitlines()[-1])


PAGE = """
    from paperdaemon import ledger as S
    from paperdaemon.pipeline import page as P
    from paperdaemon.pipeline.page import images as IM
    import os
    led = S.load()["entries"]
    key = sorted(led)[0]
    doc = next(f[:-len(".metadata")] for f in os.listdir(os.environ["RM_MIRROR"]) if f.startswith(key.split("/")[0]) and f.endswith(".metadata"))
    page = led[key]["page"]
"""


@pytest.fixture
def work(tmp_path):
    return tmp_path / "work"          # tmp_path itself is the test's data folder


def test_a_chart_is_a_picture_as_wide_as_its_box(work):
    r = _job(work, "chart", replay.SCRIPTS["chart"]["replies"])
    assert r["status"] == "done", r["note"]
    d = _look(work, PAGE + """
    print(json.dumps({"items": [i["box"] for i in IM.items(doc, page)], "placed": IM.placements(doc, page),
                      "safe": list(P.SAFE_AREA)}))
    """)
    (box,), safe = d["items"], d["safe"]
    assert box[0] == safe[0] and box[2] == safe[2] and box[1] >= safe[1]           # the safe area's whole width
    (rec,) = d["placed"].values()
    assert rec["box"] == [round(v, 1) for v in box] and rec["spec"]["type"] == "bar"   # what a redo extends


def test_a_chart_redone_takes_the_old_ones_place_and_the_old_one_goes(work):
    _job(work, "chart", replay.SCRIPTS["chart"]["replies"])
    before = _look(work, PAGE + """
    from paperdaemon.pipeline.page import typed as TY
    TY.insert(doc, page, "Add Jupiter, 139,820 km, to the chart.")
    print(json.dumps([i["box"] for i in IM.items(doc, page)]))
    """)
    r = _job(work, "chart", [
        ("plan", {"steps": [{"do": "chart", "what": "add Jupiter", "replaces": "picture:1", "answers": replay.NEW}],
                  "rulings": replay.RULE("request", "erase")}),
        ("chart", {"spec": {"type": "bar", "title": "Inner planets and Jupiter (km)",
                            "categories": ["Mercury", "Venus", "Earth", "Mars", "Jupiter"],
                            "series": [{"name": "Diameter", "values": [4879, 12104, 12742, 6779, 139820]}]}})])
    assert r["status"] == "done", r["note"]
    d = _look(work, PAGE + """
    print(json.dumps({"items": [i["box"] for i in IM.items(doc, page)], "placed": IM.placements(doc, page)}))
    """)
    (old,), (new,) = before, d["items"]
    assert new[:3] == old[:3]                                  # the same place: left, top and width
    specs = [p["spec"]["categories"] for p in d["placed"].values() if p.get("spec")]
    assert ["Mercury", "Venus", "Earth", "Mars", "Jupiter"] in specs


MARKS = PAGE + """
    from paperdaemon.pipeline.page import typed as TY
    tb, ps = TY.paragraphs(doc, page)
    snap = P.snapshot(doc, page)
    out = {"marks": [s["bbox"] for s in snap["strokes"] if s["tool"].startswith("HIGHLIGHTER")], "paras": []}
    for p in ps:
        at = p["text"].find(WORD)
        out["paras"].append({"text": p["text"], "y": p["y"], "lh": p["lh"], "x": p["line_x"][0],
                             "word_at": TY.span_width(p["text"][:at], p["style_code"]) if at >= 0 else None,
                             "word_w": TY.span_width(WORD, p["style_code"])})
    print(json.dumps(out))
"""


def test_a_highlight_lands_on_the_typed_words_it_names(work):
    r = _job(work, "typed-question", replay.SCRIPTS["highlight"]["replies"])
    assert r["status"] == "done", r["note"]
    d = _look(work, MARKS.replace("WORD", repr("Mars")))
    (para,), (mark,) = d["paras"], d["marks"]
    left, right = para["x"] + para["word_at"], para["x"] + para["word_at"] + para["word_w"]
    assert abs(mark[0] - left) <= 8 and abs(mark[2] - right) <= 8          # the word, and a little either side
    assert para["y"] <= mark[1] <= para["y"] + para["lh"]                   # on its line


def test_a_highlight_never_lands_on_the_request_that_comes_off(work):
    # "satellites" is in the request (erased) and in a note below it (kept): the note's is marked
    replay.run_case("prep", {"fixture": "typed-question", "replies": [("skip", {"note": "first look"})]}, work=str(work))
    _look(work, PAGE + """
    from paperdaemon.pipeline.page import typed as TY
    TY.insert(doc, page, "Highlight the word satellites in my note.")
    TY.insert(doc, page, "Note: satellites orbit their planets.")
    print("{}")
    """)
    r = _job(work, "typed-question", [
        ("plan", {"steps": [{"do": "highlight", "what": "satellites", "words": "satellites", "answers": ["para:2"]}],
                  "rulings": [{"id": "para:1", "is": "question", "then": "keep"},
                              {"id": "para:2", "is": "request", "then": "erase"},
                              {"id": "para:3", "is": "note", "then": "keep"}]})])
    assert r["status"] == "done", r["note"]
    d = _look(work, MARKS.replace("WORD", repr("satellites")))
    texts = [p["text"] for p in d["paras"]]
    assert "Highlight the word satellites in my note." not in texts                # the request came off
    note = next(p for p in d["paras"] if p["text"].startswith("Note:"))
    (mark,) = d["marks"]
    assert note["y"] <= mark[1] <= note["y"] + note["lh"]                   # on the note, not where the request was


def test_a_reply_goes_right_under_what_stays_when_a_request_above_it_comes_off(work):
    replay.run_case("prep", {"fixture": "typed-question", "replies": [("skip", {"note": "first look"})]}, work=str(work))
    _look(work, PAGE + """
    from paperdaemon.pipeline.page import typed as TY
    TY.insert(doc, page, "Write me a line about Phobos under my note.")
    TY.insert(doc, page, "Note: Phobos is slowly falling toward Mars.")
    print("{}")
    """)
    r = _job(work, "typed-question", [
        ("plan", {"steps": [{"do": "write", "what": "a line about Phobos", "answers": ["para:2"]}],
                  "rulings": [{"id": "para:1", "is": "question", "then": "keep"},
                              {"id": "para:2", "is": "request", "then": "erase"},
                              {"id": "para:3", "is": "note", "then": "keep"}]}),
        ("write_paragraph", {"lines": ["Phobos circles Mars three times a day."]})])
    assert r["status"] == "done", r["note"]
    d = _look(work, PAGE + """
    from paperdaemon.pipeline.page import typed as TY
    tb, ps = TY.paragraphs(doc, page)
    ink = [s["bbox"] for s in P.snapshot(doc, page)["strokes"]]
    print(json.dumps({"paras": [[p["text"], p["y"], p["lh"] * len(p["lines"])] for p in ps if p["text"].strip()],
                      "ink_top": min(b[1] for b in ink)}))
    """)
    assert [p[0] for p in d["paras"]] == ["How many moons does Mars have, and what are they called?",
                                          "Note: Phobos is slowly falling toward Mars."]
    note_bottom = d["paras"][1][1] + d["paras"][1][2]
    # the gap a reply always leaves under the text (85 units on this page), from where the note WILL be: measured
    # where it is today, the reply sat a paragraph (45 units) lower
    assert note_bottom + 78 < d["ink_top"] < note_bottom + 92


def test_a_long_reply_runs_past_the_first_screen_whole(work):
    # a reply too long for the room left: the layout runs it below the first screen (the page scrolls), and every
    # line of it is written -- none cut off where the first screen ends
    replay.run_case("prep", {"fixture": "typed-question", "replies": [("skip", {"note": "first look"})]}, work=str(work))
    _look(work, PAGE + """
    from paperdaemon.pipeline.page import typed as TY
    for i in range(6):
        TY.insert(doc, page, "Note %d: " % i + "a long paragraph of the user's own notes that wraps over several lines. " * 6)
    print("{}")
    """)
    lines = ["This is line %d of a long answer that will not fit in the room left on the page." % i for i in range(14)]
    r = _job(work, "typed-question", [
        ("answer", {"answers": replay.NEW, "lines": lines, "rulings": replay.RULE("note", "keep")})])
    assert r["status"] == "done", r["note"]
    assert "outside" not in (r["note"] or "")
    d = _look(work, PAGE + """
    ink = [s["bbox"] for s in P.snapshot(doc, page)["strokes"]]
    print(json.dumps({"bottom": max(b[3] for b in ink), "safe": list(P.SAFE_AREA)}))
    """)
    assert d["bottom"] > d["safe"][3]                                  # it did run past the first screen ...


def test_an_erase_step_pointing_at_an_id_takes_that_off_and_the_job_is_done(work):
    # the plan's rulings already erase the request, and an extra erase step names it again by its id in `at` (as a
    # model wrote it): the id is read as an id, the second erase is the same one, and the job is done
    r = _job(work, "typed-question", [
        ("plan", {"steps": [{"do": "write", "what": "the moons of Mars", "answers": replay.NEW},
                            {"do": "erase", "what": "the request line", "at": "para:1", "answers": replay.NEW}],
                  "rulings": replay.RULE("request", "erase")}),
        ("write_paragraph", {"lines": ["Phobos is the larger and closer moon.", "Deimos is small and far out."]})])
    assert r["status"] == "done", r["note"]
    d = _look(work, PAGE + """
    from paperdaemon.pipeline.page import typed as TY
    print(json.dumps({"text": json.dumps(TY.paragraphs(doc, page), default=str)}))
    """)
    assert "Mars" not in d["text"]                                       # the request came off
