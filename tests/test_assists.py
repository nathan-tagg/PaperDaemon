"""Keyword assists: data a harness may carry to help a weaker model, applied after its decision. A hint goes back
once and the model's next answer stands; an override is recorded; a file naming an unknown decision is refused;
the built-in harness runs none."""
import json
import os
import shutil

from paperdaemon import harnesses as HS
from paperdaemon.harnesses import schema
from paperdaemon.pipeline.host import assists as AS
from paperdaemon.pipeline.host import job as J

HINT = {"decision": "step.kind", "reads": "step.what", "when": "image", "keywords": ["the web"],
        "hint": "A picture from the web is a web_picture step."}
SET = {"decision": "item.ruling", "reads": "item.text", "when": "erase", "ends_with": "?",
       "set": {"is": "question", "then": "keep"}}


def test_a_hint_goes_back_once_and_the_models_answer_stands():
    J.begin()
    args = {"steps": [{"do": "image", "what": "a lighthouse from the web", "answers": []}], "rulings": []}
    _a, hint = AS.apply(args, [HINT])
    assert hint == HINT["hint"]
    _a, again = AS.apply(args, [HINT])               # the model kept its choice: it stands
    assert again is None and args["steps"][0]["do"] == "image"


def test_an_override_sets_the_value_and_the_record_names_it():
    J.begin()
    J.JOB.listing = {"para:1": {"owner": "user", "text": "What is the tallest mountain?"}}
    args = {"rulings": [{"id": "para:1", "is": "request", "then": "erase"}]}
    out, hint = AS.apply(args, [SET])
    assert hint is None and out["rulings"][0] == {"id": "para:1", "is": "question", "then": "keep"}
    assert J.JOB.assisted and "item.ruling" in J.JOB.assisted[0]


def test_an_assist_naming_an_unknown_decision_is_refused():
    assert schema.check("assists", [HINT, SET]) is None
    bad = dict(HINT, decision="step.color")
    assert schema.check("assists", [bad]).startswith("assists must be")
    assert schema.check("assists", [dict(HINT, set={"do": "web_picture"})]) is not None     # a hint or a set, not both


def test_the_built_in_harness_runs_none_and_the_example_loads(tmp_path):
    assert HS.DEFAULT["text"].assists == () and all(not getattr(h, "assists", ()) for h in HS.BUILT_IN)
    src = os.path.join(os.path.dirname(HS.__file__), "examples", "keyword-assists.json")
    shutil.copy(src, tmp_path / "keyword-assists.json")
    made, errors = HS.load(str(tmp_path), {h.id: h for h in HS.BUILT_IN}, kind="text")
    assert errors == [] and len(made[0].assists) == 5
    assert json.load(open(src, encoding="utf-8"))["notes"].startswith("AN EXAMPLE, NOT ACTIVE")
