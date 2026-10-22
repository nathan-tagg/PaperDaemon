"""One case per word-matching check the host used to make (C1-C30) and per host rewrite (S1-S7): what the host now
does with the model's decision instead. The model decides; the host checks validity and carries the decision out.
Rows whose replacement is a validity rule are in test_rulings.py (C18, C19, C22, C24-C26, rule 8); the incidents
that need a model's judgment are benchmark cases, run with the maintainer's go-ahead."""
import pytest

import paperdaemon.pipeline.host as H
from paperdaemon.pipeline.host import job as J
from paperdaemon.pipeline.host import rulings as RU
from paperdaemon.pipeline.host import steps as ST

GONE = ["_WEB_CUE", "_FACT_CUE", "_PIC_CUE", "_MARKUP_DRAW", "_CHART_CUE", "_reddit_ref", "_reddit_query",
        "_reddit_search", "_changes_picture", "_sweepable", "_is_request", "_carried_out", "_redoes",
        "_auto_erase_requests", "_is_question", "_keep_requests", "_unsweep", "_stale_assets", "_erase_ink_saying",
        "_site_in", "_MONTHS"]


@pytest.mark.parametrize("name", GONE)
def test_the_word_checks_are_gone(name):
    assert not hasattr(H, name)
    assert not hasattr(ST, "ALIASES") and not hasattr(ST, "LEGACY") and not hasattr(ST, "located_words")


@pytest.mark.parametrize("row,step", [
    # C1: a picture asked for from a site stays the model's kind; the web_picture step carries the site
    ("C1", {"do": "web_picture", "what": "the top picture of the day", "site": "reddit.com", "answers": []}),
    # C2: facts are a search step; the host never turns a web_picture into one
    ("C2", {"do": "search", "what": "events on September 14", "answers": []}),
    # C3: a mark round a word is a mark-up step with target and words, not a drawing to be rewritten
    ("C3", {"do": "circle", "what": "the word plum", "target": "para:1", "words": "plum", "answers": []}),
    # C4, C16: a subreddit's posts are one posts step with a count
    ("C4", {"do": "posts", "what": "", "source": "r/earthporn", "count": 3, "pictures": True, "answers": []}),
    # C5: a calendar is a calendar step, named by the model
    ("C5", {"do": "calendar", "what": "week", "answers": []}),
    # C14, C15: the posts step's own fields, not words taken apart
    ("C14", {"do": "posts", "what": "", "source": "reddit", "search": "rust", "sort": "top", "period": "week",
             "answers": []}),
    # C17: the site a picture is searched on is the step's field
    ("C17", {"do": "web_picture", "what": "a red fox", "site": "flickr.com", "answers": []}),
    # C23: each game is a step kind of its own
    ("C23", {"do": "adventure", "what": "a haunted lighthouse, with a fisherman for a hero", "answers": []}),
    # C27: the word inside a paragraph is target and words
    ("C27", {"do": "highlight", "what": "Friday", "target": "para:1", "words": "Friday", "answers": []}),
    # C28: chess setup from fields
    ("C28", {"do": "chess", "what": "a game", "color": "black", "strength": 1500, "answers": []}),
    # C29: a chat's members are named, not matched in the request's words
    ("C29", {"do": "messages", "what": "a chat", "members": ["a resident"], "answers": []}),
])
def test_the_models_step_is_carried_out_as_written(row, step):
    J.begin()
    J.JOB.listing = {"para:1": {"owner": "user", "text": "Circle plum and highlight Friday."}}
    J.JOB.new_refs = []
    assert RU.problems("plan", {"steps": [step], "rulings": []}) == [], row
    built = ST.build([step])[0]
    assert built["do"] == step["do"]                                   # never rewritten into another kind
    for k in set(step) - {"do", "what", "answers"}:
        assert k in built, (row, k)


def test_c6_c7_s1_a_change_to_a_picture_is_the_models_replaces():
    s = ST.build([{"do": "chart", "what": "add Thursday", "replaces": "picture:1"}])[0]
    assert s["near"] == "picture:1"
    s = ST.build([{"do": "calendar", "what": "2026-10"}])[0]
    assert "near" not in s                                             # no calendar is redone unless the model says


def test_c8_c9_c10_s2_s6_what_comes_off_is_the_rulings():
    rs = [{"id": "para:1", "is": "request", "then": "erase"}, {"id": "line:1", "is": "note", "then": "keep"},
          {"id": "picture:2", "is": "stale_work", "then": "erase"}]
    assert [e["id"] for e in RU.erase_of(rs)] == ["para:1", "picture:2"]


def test_c11_c12_a_question_or_conversation_stays_by_the_models_ruling():
    J.begin()
    J.JOB.listing = {"para:1": {"owner": "user", "text": "Not what I wanted. Look at the mess you've made."},
                     "para:2": {"owner": "user", "text": "Why is the sky blue?"}}
    J.JOB.new_refs = ["para:1", "para:2"]
    keep = [{"id": "para:1", "is": "conversation", "then": "keep"}, {"id": "para:2", "is": "question", "then": "keep"}]
    assert RU.problems("answer", {"answers": ["para:2"], "rulings": keep}) == [] and RU.erase_of(keep) == []
    bad = [{"id": "para:1", "is": "conversation", "then": "erase"}, {"id": "para:2", "is": "question", "then": "keep"}]
    assert any("conversation, which stays" in x for x in RU.problems("answer", {"answers": [], "rulings": bad}))


def test_c13_ink_comes_off_by_its_id_or_a_point_never_by_what_it_says():
    assert ST.erase_targets("the ink that says pear") == []
    assert ST.erase_targets("line:2 at:1") == [("line", 2), ("at", 1)]


def test_c30_a_residents_selfie_is_its_own_field():
    from paperdaemon.pipeline.games import messages as MS
    r = MS.parse_reply("SAY: Look at me!\nIMAGE: me on the pier at sunset\nIMAGE OF: self\nFEEL: happy 6")
    assert r["image_of"] == "self"
    r = MS.parse_reply("SAY: Here.\nIMAGE: a selfie stick on the pier\nFEEL: happy 6")
    assert r["image_of"] == "other"                                   # words never decide it


def test_s3_a_new_picture_takes_an_erased_pictures_place(monkeypatch):
    J.begin(doc="d", page=1)
    monkeypatch.setattr(H, "_pictures", lambda doc, page, hidden_too=False: [{"n": 2, "box": [0, 400, 100, 600]}])
    steps = ST.build(ST.erase_steps([{"id": "picture:2", "because": "stale"}]) + [{"do": "chart", "what": "a new one"}])
    # the rule runs inside _plan; reproduced on its data here
    gone = [v for q in steps if q["do"] == "erase" for k, v in ST.erase_targets(q["what"]) if k == "picture"]
    assert gone == [2]


def test_s5_rule_10_a_request_stays_when_the_step_that_answers_it_fails(monkeypatch):
    J.begin()
    undone = []
    monkeypatch.setattr(H, "_unstage", lambda op: undone.append(op))
    J.JOB.plan = {"erase_sigs": ["a", "b", "c"]}
    J.JOB.steps = [{"id": 1, "do": "erase", "what": "para:1", "because": "request", "status": "done", "ops": [4],
                    "sigs": []},
                   {"id": 2, "do": "erase", "what": "mark:3", "because": "request", "status": "done", "ops": [],
                    "sigs": ["b"]},
                   {"id": 3, "do": "erase", "what": "para:2", "because": "asked", "status": "done", "ops": [5]},
                   {"id": 4, "do": "chart", "what": "x", "answers": ["para:1", "mark:3"], "status": "failed"}]
    H._keep_unanswered()
    assert undone == [4] and J.JOB.plan["erase_sigs"] == ["a", "c"]
    assert [q["status"] for q in J.JOB.steps] == ["failed", "failed", "done", "failed"]   # what was asked to go, goes


def test_s4_two_steps_replacing_one_picture_are_refused_not_folded():
    J.begin()
    J.JOB.listing = {"picture:1": {"owner": "system", "text": "calendar"}}
    p = RU.problems("plan", {"steps": [{"do": "calendar", "what": "week", "answers": [], "replaces": "picture:1"},
                                       {"do": "write", "what": "facts", "answers": [], "replaces": "picture:1"}],
                             "rulings": []})
    assert any("both replace picture:1" in x for x in p)


def test_s7_this_systems_ink_on_its_own_picture_goes_with_it():
    assert hasattr(H, "_ink_on")                                        # kept: placement and cleanup are the host's


def test_an_erase_pointing_at_nothing_goes_back_to_the_model(monkeypatch):
    # the frog page: the rulings take the prompt off (mark:1..2), and the model added an erase step pointing at "all
    # the handwriting marks" that grounding found nowhere. Run, it failed and rule 10 put the prompt back; now the plan
    # is refused before anything is done, and the model is told why
    J.begin(doc="d", page=1)
    monkeypatch.setattr(H, "_at_ground", lambda whats: {})
    monkeypatch.setattr(H, "_off_steps", lambda steps: None)
    monkeypatch.setattr(H, "_resolve_lines", lambda what: what)
    monkeypatch.setattr(H, "_pictures", lambda doc, page, hidden_too=False: [])
    steps = ST.build(ST.erase_steps([{"id": "mark:1", "because": "request"}, {"id": "mark:2", "because": "request"}])
                     + [{"do": "erase", "what": "the prompt", "answers": ["mark:1", "mark:2"],
                         "at": "all the handwriting marks on the page"},
                        {"do": "coloring", "what": "a frog", "answers": ["mark:1"], "size": "full"}])
    out = H._plan(steps, [{"id": "mark:1", "is": "request", "then": "erase"},
                          {"id": "mark:2", "is": "request", "then": "erase"}])
    assert "all the handwriting marks on the page" in out["error"] and "drop this step" in out["error"]


def test_a_picture_after_a_short_reply_goes_right_below_it():
    """The layout is planned before anything is written: a reply's box is a share of the free page. A picture that the
    host makes after the reply must be placed below what the reply really took, not below its planned box (it went
    half a page down)."""
    from paperdaemon.pipeline import draw as A
    from paperdaemon.pipeline import host as H
    from paperdaemon.pipeline.host import job as J
    from paperdaemon.pipeline.host import layout as PL
    J.begin(doc="nodoc", page=1, frame=(1620.0, 2160.0), draw=A.Drawing(), ops=[])
    specs = [{"id": "p1", "kind": "text", "size": "medium", "near": "stack"},
             {"id": "p2", "kind": "image", "size": "medium", "near": "stack"}]
    boxes = PL.solve([dict(p) for p in specs], first_free_y=600)
    planned = dict(boxes["p2"])
    H.JOB.plan = {"places": boxes, "reflow": {"specs": specs, "first_free_y": 600, "marks": None, "obstacles": None,
                                               "text_col": None}}
    H.JOB.draw.stroke([(-500, 650), (300, 650)])               # the reply: one short line at the top of its box
    H.JOB.draw.stroke([(-500, 690), (100, 690)])
    H.JOB.steps = [{"id": 1, "do": "write", "what": "a reply", "place": "p1", "status": "done", "draw_from": 0, "draw_to": 2},
                   {"id": 2, "do": "image", "what": "a photo", "place": "p2", "status": "todo"}]
    seen = {}

    def run_images(batch):
        seen["box"] = dict(H.JOB.plan["places"]["p2"])
        for q in batch:
            q["status"] = "done"
    real = H._run_images
    H._run_images = run_images
    try:
        H._drain_host_steps()
    finally:
        H._run_images = real
    assert seen["box"]["y0"] < planned["y0"] and seen["box"]["y0"] <= 690 + PL.GAP + 1
    # a traced picture's points are numpy's: what the model is told about its box must still be JSON
    import json
    import numpy as np
    H.JOB.draw.stroke([(np.float32(-200), np.float32(800)), (np.float32(200), np.float32(900))])
    H.JOB.steps[1].update(status="done", draw_from=2, draw_to=3)
    json.dumps(H._landed_box(H.JOB.steps[1]))
