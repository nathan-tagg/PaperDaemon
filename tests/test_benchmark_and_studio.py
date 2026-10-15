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


def test_inbox_paths():
    assert studio.split_inbox("PaperDaemon inbox") == ([], "PaperDaemon inbox")
    assert studio.split_inbox(" Projects / Pictures inbox ") == (["Projects"], "Pictures inbox")
    assert studio._next_key([]) == "ba" and studio._next_key(["ba", "bz"]) == "ca"
    assert studio.box_for(5000) == 1600 and studio.box_for(10) == 200


def test_the_inbox_is_found_by_its_folders(tmp_path):
    def meta(doc, **m):
        with open(os.path.join(tmp_path, doc + ".metadata"), "w", encoding="utf-8") as f:
            json.dump(m, f)
    meta("f1", visibleName="Projects", type="CollectionType", parent="")
    meta("n1", visibleName="Inbox", type="DocumentType", parent="")
    meta("n2", visibleName="Inbox", type="DocumentType", parent="f1")
    meta("n3", visibleName="Inbox", type="DocumentType", parent="trash")
    assert studio.find_inbox(str(tmp_path), "Inbox") == "n1"
    assert studio.find_inbox(str(tmp_path), "Projects/Inbox") == "n2"
    assert studio.find_inbox(str(tmp_path), "Other/Inbox") is None


SEND = textwrap.dedent("""
    import json, os, sys
    sys.path.insert(0, %(root)r)
    from paperdaemon import settings, studio
    import paperdaemon.pipeline  # noqa: F401
    from paperdaemon.pipeline import draw as A
    from paperdaemon.remarkable import sync as C
    pushed = []
    C.pull = lambda *a, **k: {}
    C.touch = lambda doc, pages=None, when=None: None
    C.push_new_doc = lambda doc, dry_run=True: pushed.append(("new", doc, dry_run)) or {"root_put": 200}
    C.push_doc = lambda doc, dry_run=True: pushed.append(("doc", doc, dry_run)) or {"root_put": 200}
    line = ([(-100.0 + i, 400.0 + i) for i in range(30)], [4.0] * 30, A.Pen.FINELINER_2, A.PenColor.BLACK, None)
    studio.decompose = lambda image, width=None, preview=True: ({"strokes": 1}, [line])
    s = settings.load()
    s["tablet"]["inbox"] = "Pictures inbox"
    first = studio.send("data:image/png;base64,AA==", 600, s)
    second = studio.send("data:image/png;base64,AA==", 600, s)
    print(json.dumps({"first": first, "second": second, "pushed": pushed}))
""")


def test_send_appends_a_page_to_the_inbox(tmp_path):
    home = tmp_path / "home"
    env = dict(os.environ, PAPERDAEMON_HOME=str(home), PYTHON_KEYRING_BACKEND="keyring.backends.null.Keyring")
    for k in ("RM_STATE", "RM_MIRROR", "RM_CACHE"):
        env.pop(k, None)
    out = subprocess.run([sys.executable, "-c", SEND % {"root": ROOT}], env=env, capture_output=True, text=True,
                         timeout=600)
    assert out.returncode == 0, out.stderr[-2000:]
    d = json.loads(out.stdout.strip().splitlines()[-1])
    first, second = d["first"], d["second"]
    assert first["created"] is True and second["created"] is False
    assert first["doc"] == second["doc"] and (first["page"], second["page"]) == (1, 2)
    assert d["pushed"] == [["new", first["doc"], False], ["doc", first["doc"], False]]
    mirror = home / "mirror"
    with open(mirror / (first["doc"] + ".content"), encoding="utf-8") as f:
        content = json.load(f)
    with open(mirror / (first["doc"] + ".metadata"), encoding="utf-8") as f:
        meta = json.load(f)
    assert meta["visibleName"] == "Pictures inbox" and meta["parent"] == ""
    assert content["tags"] == []           # no tag: the daemon leaves the inbox alone whatever it carries
    pages = content["cPages"]["pages"]
    assert len(pages) == 2 and all((mirror / first["doc"] / (p["id"] + ".rm")).is_file() for p in pages)
    got = benchmark.page_content(str(mirror), first["doc"], pages[1]["id"])
    assert got["strokes"] == 1


def test_two_notebooks_with_the_inboxs_name_send_to_the_first_made(tmp_path):
    import json as _j
    from paperdaemon import studio
    m = tmp_path / "m"
    m.mkdir()
    for doc, made in (("bbbb", "2000"), ("aaaa", "3000")):
        (m / (doc + ".metadata")).write_text(_j.dumps({"visibleName": "Inbox", "parent": "", "type": "DocumentType",
                                                       "createdTime": made}))
    assert studio.find_inbox(str(m), "Inbox") == "bbbb"
