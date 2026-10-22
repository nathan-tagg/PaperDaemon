"""The benchmark's fixtures and judging, and decompose-and-send's inbox handling (with the cloud stubbed:
nothing here reaches the tablet)."""
import json
import os
import subprocess
import sys
import textwrap

from paperdaemon import benchmark, studio
from paperdaemon.benchmark import fixtures

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def test_the_fixtures_match_the_case_list():
    cases = {c["id"]: c for c in benchmark.cases()}
    assert set(cases) == {c["id"] for c in fixtures.CASES}
    for c in fixtures.CASES:
        got = cases[c["id"]]
        doc, page = fixtures.ids(c["id"])
        assert (got["doc"], got["page"], got["request"]) == (doc, page, c["request"])
        mirror = os.path.join(benchmark.cases_dir(), c["id"], "mirror")
        with open(os.path.join(mirror, doc + ".content"), encoding="utf-8") as f:
            content = json.load(f)
        assert content["pageTags"] == [{"name": fixtures.TAG, "pageId": page, "timestamp": fixtures.WHEN + 1000}]
        assert os.path.isfile(os.path.join(mirror, doc, page + ".rm"))


def test_each_fixture_page_carries_its_request():
    for c in benchmark.cases():
        mirror = os.path.join(benchmark.cases_dir(), c["id"], "mirror")
        got = benchmark.page_content(mirror, c["doc"], c["page"])
        if c["kind"] == "typed":
            assert got["text"] == len(c["request"]) and got["strokes"] == 0
        else:
            assert got["strokes"] > 20 and got["text"] == 0


def test_a_run_starts_from_a_fresh_copy_of_the_fixtures(tmp_path):
    mirror = benchmark.prepare(str(tmp_path), benchmark.cases())
    for c in benchmark.cases():
        assert os.path.isfile(os.path.join(mirror, c["doc"], c["page"] + ".rm"))


def test_judging():
    case = {"expect": {"content": "picture"}}
    none = {"strokes": 0, "text": 10, "pictures": 0}
    ok, notes = benchmark.judge(case, none, {"strokes": 0, "text": 10, "pictures": 1}, {"status": "done"})
    assert ok and "1 pictures" in notes[0]
    ok, notes = benchmark.judge(case, none, none, {"status": "done"})
    assert not ok and notes[-1] == "expected a picture"
    ok, notes = benchmark.judge(case, none, none, {"status": "skipped", "note": "the model did not answer"})
    assert not ok and "skipped: the model did not answer" in notes[0]
    ok, _ = benchmark.judge({"expect": {"content": "text"}}, none, dict(none, text=40), {"status": "done"})
    assert ok
    # numbers lettered on the page are not a chart
    ok, notes = benchmark.judge({"expect": {"content": "chart"}}, none, dict(none, strokes=569), {"status": "done"})
    assert not ok and "a chart" in notes[-1]
    ok, _ = benchmark.judge({"expect": {"content": "drawing"}}, none, dict(none, strokes=4000), {"status": "done"})
    assert ok


def test_page_keys_and_boxes():
    assert studio._next_key([]) == "ba" and studio._next_key(["ba", "bz"]) == "ca"
    assert studio.box_for(5000) == 1600 and studio.box_for(10) == 200


def _book(mirror, doc, name, parent="", tags=(), kind="notebook", modified="1"):
    (mirror / (doc + ".metadata")).write_text(json.dumps({"visibleName": name, "parent": parent, "type": "DocumentType",
                                                          "lastModified": modified}), encoding="utf-8")
    (mirror / (doc + ".content")).write_text(json.dumps({"fileType": kind, "tags": [{"name": t} for t in tags]}),
                                             encoding="utf-8")


def test_a_send_lands_in_every_notebook_with_the_inbox_tag_else_in_quick_sheets(tmp_path):
    m = tmp_path / "m"
    m.mkdir()
    (m / "f1.metadata").write_text(json.dumps({"visibleName": "Old", "parent": "trash", "type": "CollectionType"}))
    _book(m, "qs", "Quick sheets", modified="5")
    _book(m, "qs-old", "Quick sheets", parent="trash", modified="9")           # in the trash: not the one
    _book(m, "qs-copy", "Quick sheets", parent="somewhere", modified="9")      # not at the root: not the one
    assert studio.inbox_docs(str(m), "inbox") == (["qs"], "quick sheets")
    _book(m, "a", "Pictures", tags=["Inbox"])
    _book(m, "b", "Drawings", tags=["inbox", "joi"])
    _book(m, "c", "Gone", parent="f1", tags=["inbox"])                         # in a trashed folder
    _book(m, "d", "A book", tags=["inbox"], kind="epub")                       # not a notebook
    assert studio.inbox_docs(str(m), "inbox") == (["b", "a"], "tag")          # by name
    for d in ("a", "b", "qs"):
        (m / (d + ".metadata")).unlink()
    assert studio.inbox_docs(str(m), "inbox") == ([], None)


SEND = textwrap.dedent("""
    import json, os, sys, uuid
    sys.path.insert(0, %(root)r)
    from paperdaemon import settings, studio
    import paperdaemon.pipeline  # noqa: F401
    from paperdaemon.pipeline import TEMPLATES
    from paperdaemon.pipeline import draw as A
    from paperdaemon.pipeline.page import render as R
    from paperdaemon.remarkable import sync as C
    pushed = []
    C.pull = lambda *a, **k: {}
    def push_pending():
        docs = [f[:-8] for f in os.listdir(R.RM) if f.endswith(".content")]
        pushed.append(sorted(docs))
        return {"pushed": [(d, {"root_put": 200}) for d in docs]}
    C.push_pending = push_pending
    line = ([(-100.0 + i, 400.0 + i) for i in range(30)], [4.0] * 30, A.Pen.FINELINER_2, A.PenColor.BLACK, None)
    studio.decompose = lambda image, width=None, preview=True: ({"strokes": 1}, [line])
    s = settings.load()
    out = {}
    try:
        studio.send("data:image/png;base64,AA==", 600, s)
    except ValueError as ex:
        out["none"] = str(ex)
    os.makedirs(R.RM, exist_ok=True)
    books = {}
    for name in ("Quick sheets", "Pictures", "Drawings"):
        books[name] = str(uuid.uuid4())
        studio._new_notebook(R.RM, os.path.dirname(TEMPLATES), books[name], name, "", 1)
    out["quick"] = studio.send("data:image/png;base64,AA==", 600, s)
    for name in ("Pictures", "Drawings"):
        p = os.path.join(R.RM, books[name] + ".content")
        c = json.load(open(p, encoding="utf-8")); c["tags"] = [{"name": "inbox", "timestamp": 1}]
        json.dump(c, open(p, "w", encoding="utf-8"))
    out["tagged"] = studio.send("data:image/png;base64,AA==", 600, s)
    out["pages"] = {n: len(R.live_pages(d)) for n, d in books.items()}
    print(json.dumps(out))
""")


def test_send_appends_a_page_to_every_inbox(tmp_path):
    home = tmp_path / "home"
    env = dict(os.environ, PAPERDAEMON_HOME=str(home), PYTHON_KEYRING_BACKEND="keyring.backends.null.Keyring")
    for k in ("RM_STATE", "RM_MIRROR", "RM_CACHE"):
        env.pop(k, None)
    out = subprocess.run([sys.executable, "-c", SEND % {"root": ROOT}], env=env, capture_output=True, text=True,
                         timeout=600)
    assert out.returncode == 0, out.stderr[-2000:]
    d = json.loads(out.stdout.strip().splitlines()[-1])
    assert "no notebook is tagged inbox" in d["none"]
    assert d["quick"]["notebooks"] == 1 and d["tagged"]["notebooks"] == 2
    assert d["pages"] == {"Quick sheets": 1, "Pictures": 1, "Drawings": 1}
