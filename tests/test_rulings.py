"""The decision's rulings and the host's validity rules: what comes off a page is the model's ruling on an id the
listing printed; the host checks the decision is valid and refuses an invalid one with what to fix, and never
rewrites it. Steps are objects with exact kinds and the fields each kind declares."""
import json
import os
import subprocess
import sys
import textwrap

import pytest

from paperdaemon.pipeline.host import job as J
from paperdaemon.pipeline.host import rulings as RU
from paperdaemon.pipeline.host import steps as ST

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


@pytest.fixture
def page():
    """A page as the intake lists it: two typed paragraphs (a request and a note), a line of the user's ink, a
    mark of this system's, a picture of this system's and one of the user's; the request and the ink are new."""
    J.begin(doc="d", page=1)
    J.JOB.listing = {"para:1": {"owner": "user", "text": "Make a bar chart of my steps, 30 steps per picture."},
                     "para:2": {"owner": "user", "text": "Fix the sink before Friday."},
                     "line:1": {"owner": "user", "text": "tag this page finished"},
                     "mark:9": {"owner": "system", "text": ""},
                     "picture:1": {"owner": "system", "text": "calendar"},
                     "picture:2": {"owner": "user", "text": ""}}
    J.JOB.new_refs = ["para:1", "line:1"]
    J.JOB.sprompt = ""
    return J.JOB


def rule(i, is_="request", then="erase"):
    return {"id": i, "is": is_, "then": then}


def test_the_ids_are_the_listings_labels_in_a_static_range():
    ids = ST.ERASE_IDS
    assert ids[0] == "para:1" and "line:1" in ids and "mark:1" in ids and "picture:1" in ids
    for kind, top in ST.ERASE_RANGE.items():
        assert "%s:%d" % (kind, top) in ids and "%s:%d" % (kind, top + 1) not in ids
    assert len(ids) == sum(ST.ERASE_RANGE.values()) == len(set(ids))


def test_a_ruling_declares_only_required_keys_in_writing_order():
    item = RU.RULING_ITEM
    assert list(item["properties"]) == item["required"] == ["id", "is", "then"]
    assert item["additionalProperties"] is False
    assert item["properties"]["id"]["enum"] == list(ST.ERASE_IDS)
    assert item["properties"]["then"]["enum"] == ["erase", "keep"]


def test_rulings_say_what_comes_off_and_what_stays():
    rs = [rule("para:1"), rule("para:2", "note", "keep"), rule("picture:1", "stale_work"), rule("line:1", "asked_to_remove")]
    assert RU.erase_of(rs) == [{"id": "para:1", "because": "request"}, {"id": "picture:1", "because": "stale"},
                               {"id": "line:1", "because": "asked"}]
    assert RU.kept(rs) == {"para:2"}


def test_a_valid_plan_passes(page):
    steps = [{"do": "chart", "what": "my steps by day", "answers": ["para:1"]}]
    assert RU.problems("plan", {"steps": steps, "rulings": [rule("para:1"), rule("line:1", "note", "keep")]}) == []


def test_rule_1_every_id_is_on_this_page(page):
    p = RU.problems("plan", {"steps": [{"do": "write", "what": "x", "answers": ["para:7"]}],
                             "rulings": [rule("para:1"), rule("line:1", "note", "keep"), rule("mark:40")]})
    assert any("mark:40" in x and "not on this page" in x for x in p) and any("para:7" in x for x in p)


def test_rule_2_every_new_item_is_ruled(page):
    p = RU.problems("answer", {"answers": ["para:1"], "rulings": [rule("para:1")]})
    assert p == ["rule every item listed as NEW: line:1 has no ruling."]


def test_rule_3_rulings_agree_with_themselves(page):
    p = RU.problems("answer", {"answers": [], "rulings": [rule("para:1", "question", "erase"),
                                                          rule("line:1", "stale_work")]})
    assert any("question, which stays" in x for x in p)          # a question is never erased
    assert any("line:1 is the user's" in x for x in p)          # stale work is only this system's


def test_rule_4_a_step_the_lineup_does_with_its_own_fields(page):
    rs = [rule("para:1"), rule("line:1", "note", "keep")]
    p = RU.problems("plan", {"steps": [{"do": "image", "what": "a dragon", "answers": [], "site": "x.com"}],
                             "rulings": rs})
    assert any("has no field site" in x for x in p)
    p = RU.problems("plan", {"steps": [{"do": "image", "what": "a dragon", "answers": []}], "rulings": rs},
                    offered=["write", "chart"])
    assert any("not a step this lineup does" in x for x in p)


def test_c24_c25_a_step_is_an_object_of_an_exact_kind(page):
    rs = [rule("para:1"), rule("line:1", "note", "keep")]
    assert any("not an object" in x for x in RU.problems("plan", {"steps": ["write a poem"], "rulings": rs}))
    assert any("'picture' is not a step" in x for x in RU.problems(
        "plan", {"steps": [{"do": "picture", "what": "a dragon", "answers": []}], "rulings": rs}))
    with pytest.raises(ST.StepError):
        ST.build(["write a poem"])
    with pytest.raises(ST.StepError, match="no such step 'picture'"):
        ST.build([{"do": "picture", "what": "a dragon"}])


def test_c26_an_erase_step_is_ids_or_a_point_never_words():
    with pytest.raises(ST.StepError, match="not an id"):
        ST.build([{"do": "erase", "what": "the typed request 'Draw a sailboat on a calm lake at dawn.'"}])
    s = ST.build([{"do": "erase", "what": "the arrow", "at": "the arrow drawn from 'circle this'"}])[0]
    assert s["at"].startswith("the arrow")
    assert ST.erase_targets("para:2 mark:6..8 picture:1 at:2") == [("para", 2), ("mark", 6), ("mark", 7), ("mark", 8),
                                                                  ("picture", 1), ("at", 2)]
    assert ST.erase_targets("all ink") == [] and ST.erase_targets("the words 'pear'") == []


def test_c18_c19_a_quote_vouches_for_the_users_number_and_tag(page):
    rs = [rule("para:1"), rule("line:1", "command")]
    ok = RU.problems("plan", {"steps": [{"do": "image", "what": "steps", "answers": ["para:1"], "steps": 30,
                                         "quote": "30 steps per picture"},
                                        {"do": "tag", "what": "finished", "answers": ["line:1"],
                                         "quote": "tag this page finished"}], "rulings": rs})
    assert ok == []
    no_quote = RU.problems("plan", {"steps": [{"do": "image", "what": "x", "answers": [], "steps": 30}], "rulings": rs})
    assert any("needs quote" in x for x in no_quote)
    wrong = RU.problems("plan", {"steps": [{"do": "image", "what": "x", "answers": [], "steps": 40,
                                            "quote": "30 steps per picture"}], "rulings": rs})
    assert any("does not say 40" in x for x in wrong)
    made_up = RU.problems("plan", {"steps": [{"do": "tag", "what": "done", "answers": [], "quote": "tag it done"}],
                                   "rulings": rs})
    assert any("not on this page" in x for x in made_up)


def test_rule_8_replaces_is_a_picture_of_yours_and_once(page):
    rs = [rule("para:1"), rule("line:1", "note", "keep")]
    p = RU.problems("plan", {"steps": [{"do": "chart", "what": "a", "answers": [], "replaces": "picture:2"}],
                             "rulings": rs})
    assert any("not a picture you made" in x for x in p)
    p = RU.problems("plan", {"steps": [{"do": "calendar", "what": "2026-10", "answers": [], "replaces": "picture:1"},
                                       {"do": "chart", "what": "b", "answers": [], "replaces": "picture:1"}],
                             "rulings": rs})
    assert any("both replace picture:1" in x for x in p)
    s = ST.build([{"do": "calendar", "what": "2026-10", "replaces": "picture:1"}])[0]
    assert s["replaces"] == s["near"] == "picture:1"


def test_c22_a_calendars_what_is_a_month_or_week(page):
    assert ST.calendar_what("2026-10") == ("month", 2026, 10) and ST.calendar_what("week") == ("week",)
    assert ST.calendar_what("October") is None and ST.calendar_what("2026-13") is None
    rs = [rule("para:1"), rule("line:1", "note", "keep")]
    assert any("YYYY-MM" in x for x in RU.problems(
        "plan", {"steps": [{"do": "calendar", "what": "this October", "answers": []}], "rulings": rs}))


def test_the_steps_fields_travel_and_erases_come_first():
    steps = ST.build(ST.erase_steps([{"id": "para:1", "because": "request"}]) +
                     [{"do": "posts", "what": "", "source": "r/Pics", "search": "dogs", "sort": "top", "count": 3,
                       "pictures": True},
                      {"do": "chess", "what": "a game", "color": "black", "strength": 1500, "moves": "1. e4 e5"},
                      {"do": "highlight", "what": "the date", "target": "para:2", "words": "Friday"}])
    assert [s["do"] for s in steps] == ["erase", "posts", "chess", "highlight"]
    assert steps[1]["source"] == "r/pics" and steps[1]["search"] == "dogs" and steps[1]["count"] == 3
    assert steps[2]["color"] == "black" and steps[2]["strength"] == 1500 and steps[2]["moves"] == ["e4", "e5"]
    assert steps[3]["target"] == "para:2" and steps[3]["words"] == "Friday"
    assert ST.describe(steps[3]) == "highlight 'Friday' in para:2"


# the host's half, run in a process of its own (the pipeline reads where its files are when imported)
HOST = textwrap.dedent("""
    import json, sys
    sys.path.insert(0, %(root)r)
    from paperdaemon.pipeline import host as H
    from paperdaemon.pipeline.host import rulings as RU, steps as ST
    tools = {t["function"]["name"]: t["function"]["parameters"] for t in H.tool_schema()}
    out = {"plan": tools["plan"], "answer": tools["answer"]}
    bad = []
    def walk(name, sch, path):
        if isinstance(sch, dict):
            if sch.get("type") == "object" and sch.get("properties") and path:
                if list(sch["properties"]) != list(sch.get("required") or [])[:len(sch["properties"])] \\
                        or set(sch["properties"]) - set(sch.get("required") or []):
                    bad.append("%%s %%s" %% (name, path))
            for k, v in sch.items():
                if k == "properties":
                    for p, s2 in v.items():
                        walk(name, s2, path + "." + p)
                elif isinstance(v, (dict, list)):
                    walk(name, v, path)
        elif isinstance(sch, list):
            for v in sch:
                walk(name, v, path)
    for name, params in tools.items():
        for p, sch in params["properties"].items():
            walk(name, sch, p)
    out["bad"] = bad
    out["ruling"] = RU.RULING_ITEM
    out["kinds"] = sorted(ST.KINDS)
    H.JOB.ink_lines = {1: (6, 12, (0, 100, 300, 140)), 2: (13, 13, (0, 200, 50, 240))}
    out["lines"] = [H._resolve_lines("line:1"), H._resolve_lines("line:2"), H._resolve_lines("line:3 para:1")]
    print(json.dumps(out))
""")


def test_the_host_offers_steps_and_rulings_and_resolves_lines(tmp_path):
    env = dict(os.environ, PAPERDAEMON_HOME=str(tmp_path / "home"), PYTHON_KEYRING_BACKEND="keyring.backends.null.Keyring")
    for k in ("RM_STATE", "RM_MIRROR", "RM_CACHE", "RM_RUN"):
        env.pop(k, None)
    out = subprocess.run([sys.executable, "-c", HOST % {"root": ROOT}], env=env, capture_output=True, text=True,
                         timeout=300)
    assert out.returncode == 0, out.stderr[-2000:]
    d = json.loads(out.stdout.strip().splitlines()[-1])
    assert d["plan"]["required"] == ["steps", "rulings"] and d["answer"]["required"] == ["answers", "lines", "rulings"]
    assert d["plan"]["properties"]["rulings"]["items"] == d["ruling"]
    step = d["plan"]["properties"]["steps"]["items"]
    assert step["required"] == ["do", "what", "answers"] and sorted(step["properties"]["do"]["enum"]) == d["kinds"]
    assert d["bad"] == []
    assert d["lines"][0] == "mark:6..12" and d["lines"][1] == "mark:13"
