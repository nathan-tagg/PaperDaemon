"""The text harness as an interface: the built-in default reads replies and asks its small questions exactly as
the host did before (the formulas are checked against the old ones), and a harness overrides only what it
changes."""
import json
import re

from paperdaemon import harnesses
from paperdaemon.harnesses import text as HT

H = harnesses.DEFAULT["text"]()


class Host:
    MODEL = "m"
    PLAN_TOOLS = ("plan", "answer", "ask", "skip")
    DECIDE_TEMP = 0.3


def _old_located(reply, whats, uw, uh):
    """The host's reading before the move, kept here as the reference."""
    got = {}
    for k, obj in enumerate(re.findall(r"\{[^{}]*\}", reply)):
        n = re.search(r'"n"\s*:\s*(\d+)', obj)
        i = int(n.group(1)) - 1 if n else k
        if not (0 <= i < len(whats)) or "not_found" in obj:
            continue
        b = re.search(r'"bbox(?:_2d)?"\s*:\s*\[([^\]]+)\]', obj)
        p = re.search(r'"point(?:_2d)?"\s*:\s*\[([^\]]+)\]', obj)
        v = [float(x) for x in re.findall(r"-?\d+(?:\.\d+)?", (b or p).group(1))] if (b or p) else []
        px = lambda x: x / 1000.0 * uw - uw / 2.0
        py = lambda y: y / 1000.0 * uh
        if b and len(v) == 4:
            got[whats[i]] = ("box", (min(px(v[0]), px(v[2])), min(py(v[1]), py(v[3])),
                                     max(px(v[0]), px(v[2])), max(py(v[1]), py(v[3]))))
        elif p and len(v) == 2:
            got[whats[i]] = ("point", (px(v[0]), py(v[1])))
    return got


def _new_located(reply, whats, uw, uh):
    got = {}
    px = lambda f: f * uw - uw / 2.0
    py = lambda f: f * uh
    for w, hit in zip(whats, H.read_located(reply, len(whats))):
        if hit is None:
            continue
        kind, v = hit
        if kind == "box":
            got[w] = ("box", (min(px(v[0]), px(v[2])), min(py(v[1]), py(v[3])),
                              max(px(v[0]), px(v[2])), max(py(v[1]), py(v[3]))))
        else:
            got[w] = ("point", (px(v[0]), py(v[1])))
    return got


def test_locating_reads_as_it_did_before_the_move():
    whats = ["the arrow's head", "empty paper", "the word pear"]
    for reply in ('[{"n": 1, "bbox_2d": [100, 200, 300, 400]}, {"n": 2, "point_2d": [512, 640]}, {"n": 3, "not_found": true}]',
                  '{"bbox": [7, 8.5, 990, 3]} {"point_2d": [1, 2]}',
                  'no json at all'):
        assert _new_located(reply, whats, 1620.0, 2160.0) == _old_located(reply, whats, 1620.0, 2160.0)


def test_the_locate_questions_are_the_same_words():
    body = H.locate_many(Host, ["a", "b"], b"png")
    text = body["messages"][0]["content"][0]["text"]
    assert text.startswith("This is a page from a tablet notebook. Locate each of these on it:\n1. a\n2. b\n")
    assert body["max_tokens"] == 180 and body["temperature"] == 0.2 and body["model"] == "m"
    one = H.locate_one(Host, "the sun", b"png")
    assert one["messages"][0]["content"][0]["text"] == (
        'Locate the the sun in this image. Output its bounding box in JSON, like '
        '[{"bbox_2d": [x1, y1, x2, y2], "label": "the sun"}]. If it is not in the image, say NOT FOUND.')
    assert H.read_located_one("NOT FOUND", 1300, 1700) is None
    assert H.read_located_one('[{"bbox_2d": [100, 100, 500, 500]}]', 1300, 1700) == [(130.0, 170.0, 650.0, 850.0)]
    assert H.read_located_one("(10, 20, 30, 40)", 900, 900) == [(10.0, 20.0, 30.0, 40.0)]


def test_calls_and_outcomes():
    c = H.read_call({"id": "1", "function": {"name": "plan", "arguments": '{"steps": []}'}}, False)
    assert c.name == "plan" and c.args == {"steps": []} and c.error is None
    bad = H.read_call({"id": "2", "function": {"name": "plan", "arguments": '{"steps": ['}}, True)
    assert bad.args is None and "CUT OFF" in bad.error
    assert isinstance(H.outcome(None, None, {"error": "x"}), HT.Skip) and "x" in H.outcome(None, None, {"error": "x"}).why
    assert H.outcome("skip", {}, {}).why is None
    assert isinstance(H.outcome("plan", {}, {}), HT.Jobs)
    t = H.decision(Host, [{"role": "system", "content": "s"}])
    assert t.allowed == Host.PLAN_TOOLS and t.tries == 3 and t.temperature == 0.3 and t.choice == "required"
    assert H.nudge_refused(("a", "b")) == {"error": "not now. Right now the call is one of: a, b."}
    assert H.nudge_no_call("x" * 500, ("plan",))[0]["content"].endswith(" ...")


def test_a_harness_overrides_only_what_it_changes():
    class ProseCalls(harnesses.DEFAULT["text"]):
        """A model that writes its calls as JSON in prose."""
        def calls(self, message):
            m = re.search(r"\{.*\}", message.get("content") or "", re.S)
            if not m:
                return []
            d = json.loads(m.group(0))
            return [{"id": "p", "function": {"name": d["call"], "arguments": json.dumps(d["args"])}}]
    h = ProseCalls()
    got = h.calls({"content": 'Here: {"call": "skip", "args": {"note": "empty"}}'})
    assert h.read_call(got[0], False).args == {"note": "empty"}
    assert h.locate_many(Host, ["a"], b"x") == H.locate_many(Host, ["a"], b"x")          # inherited unchanged
    assert h.declare() == {"kinds": None, "provides": []}


def test_skills_come_from_the_harness_folder(tmp_path):
    (tmp_path / "write.md").write_text("Write in short sentences.", encoding="utf-8")

    class Mine(harnesses.DEFAULT["text"]):
        skills_dir = str(tmp_path)
    assert Mine().skill("write", "the default") == "Write in short sentences."
    assert Mine().skill("chart", "the default") == "the default"
    assert H.skill("write", "the default") == "the default"


def test_a_finished_page_is_an_edit_set():
    fp = HT.FinishedPage(strokes=[{"points": [[0, 300], [100, 300]], "width": 20}],
                         erase=[{"id": "para:1", "because": "request"}], note="answered")
    assert fp.pictures == [] and fp.erase[0]["id"] == "para:1"


def test_every_step_kind_has_a_protocol_and_most_need_no_model():
    from paperdaemon.pipeline.host import jobs as JB, steps as ST
    assert len(JB.JobKind) == 21
    for k, who in ST.KINDS.items():
        assert JB.PROTOCOLS[k].model_turn == (who == ST.MODEL)
    turns = {k.name for k in JB.JobKind if JB.PROTOCOLS.get(k.value, JB._HOST).model_turn}
    assert turns == {"WRITE", "CHART", "CALENDAR", "DRAW", "GAME_TURN", "CONFLICT"}
    assert JB.kind_of({"do": "image", "source": "picture:1"}) == JB.JobKind.PICTURE_EDIT
    assert JB.kind_of({"do": "chess"}) == JB.kind_of({"do": "messages"}) == JB.JobKind.GAME_START
    assert JB.kind_of({"do": "posts"}) == JB.JobKind.POSTS

    class Own(harnesses.DEFAULT["text"]):
        protocols = {"draw": JB.JobProtocol(True, ("draw_figure",), ("draw_figure",))}
    assert JB.protocol("draw", Own()).allowed == ("draw_figure",)
    assert JB.protocol("draw", H) is JB.PROTOCOLS["draw"]


def test_skills_reach_the_model(tmp_path):
    (tmp_path / "brief.md").write_text("A shorter brief.", encoding="utf-8")
    (tmp_path / "chart.md").write_text("Prefer bar charts.", encoding="utf-8")

    class Mine(harnesses.DEFAULT["text"]):
        skills_dir = str(tmp_path)

    class FakeHost:
        system_brief = staticmethod(lambda: "THE BRIEF")
        memories_system = staticmethod(lambda: "")
        notebook_system = staticmethod(lambda doc: "")
    assert Mine().system(FakeHost, "d") == "A shorter brief."
    assert H.system(FakeHost, "d") == "THE BRIEF"
    assert Mine().step_skill("chart") == "Prefer bar charts." and H.step_skill("chart") == ""


def test_validate_refuses_the_toolbar_and_moves_what_overflows(tmp_path):
    import os
    import subprocess
    import sys
    import textwrap
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    code = textwrap.dedent("""
        import json, sys
        sys.path.insert(0, %r)
        import paperdaemon.pipeline  # noqa: F401
        from paperdaemon.pipeline import host as H
        from paperdaemon.pipeline import draw as A
        H.JOB.clear()
        H.JOB.update(doc="nodoc", page=1, frame=(1620.0, 2160.0), draw=A.Drawing(), ops=[])
        d = H.JOB.draw
        for y in (400, 500, 600, 700, 800):
            d.stroke([(0, y), (100, y)])
        d.stroke([(0, 50), (100, 50)])                      # under the toolbar
        H.PAGE_STROKE_LIMIT = 3
        over = H._validate_draft("nodoc", 1)
        print(json.dumps({"kept": [s[0][0][1] for s in d.strokes], "over": [s[0][0][1] for s in over],
                          "warn": H.JOB.warnings}))
    """) % root
    env = dict(os.environ, PAPERDAEMON_HOME=str(tmp_path / "home"), PYTHON_KEYRING_BACKEND="keyring.backends.null.Keyring")
    for k in ("RM_STATE", "RM_MIRROR", "RM_CACHE", "RM_RUN"):
        env.pop(k, None)
    out = subprocess.run([sys.executable, "-c", code], env=env, capture_output=True, text=True, timeout=300)
    assert out.returncode == 0, out.stderr[-2000:]
    d = json.loads(out.stdout.strip().splitlines()[-1])
    assert d["kept"] == [400, 500, 600] and d["over"] == [700, 800]
    assert "1 stroke(s) outside the page's safe area" in d["warn"][0]
