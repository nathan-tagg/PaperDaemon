"""A game goes where it was asked for: its pages right after the page that asked, the pages behind moving down, and
nothing else in the document changing (a PDF's own pages keep their place in its file, so its links still land).
The pipeline reads where its files are when it is imported, so its modules run in a process of their own."""
import json
import os
import subprocess
import sys
import textwrap

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

SETUP = """
    import json, os, shutil, sys, uuid
    sys.path.insert(0, %r)
    import paperdaemon.pipeline  # noqa: F401
    from paperdaemon import paths
    from paperdaemon.pipeline import TEMPLATES
    M = paths.mirror_dir()

    def notebook(doc, n, pdf=False):
        os.makedirs(os.path.join(M, doc), exist_ok=True)
        ids, keys = [str(uuid.uuid4()) for _ in range(n)], ["ba", "bb", "bc", "bd", "be"][:n]
        for pid in ids:
            shutil.copyfile(os.path.join(TEMPLATES, "blank-page.rm"), os.path.join(M, doc, pid + ".rm"))
        pages = [dict({"id": pid, "idx": {"timestamp": "1:2", "value": k}, "template": {"timestamp": "1:1", "value": "Blank"}},
                      **({"redir": {"timestamp": "1:2", "value": i}} if pdf else {}))
                 for i, (pid, k) in enumerate(zip(ids, keys))]
        c = {"cPages": {"pages": pages, "lastOpened": {"timestamp": "1:1", "value": ids[0]}}, "pageCount": n,
             "fileType": "pdf" if pdf else "notebook", "formatVersion": 2, "sizeInBytes": "0", "tags": [], "pageTags": []}
        json.dump(c, open(os.path.join(M, doc + ".content"), "w"))
        json.dump({"visibleName": doc, "parent": "", "type": "DocumentType"}, open(os.path.join(M, doc + ".metadata"), "w"))
        return ids

    def order(doc):
        from paperdaemon.pipeline.page import render as R
        return [p["id"] for p in R.live_pages(doc)]
"""


def _run(tmp_path, body):
    code = textwrap.dedent(SETUP % ROOT) + textwrap.dedent(body)
    env = dict(os.environ, PAPERDAEMON_HOME=str(tmp_path / "home"), PYTHON_KEYRING_BACKEND="keyring.backends.null.Keyring",
               RM_HOST_DRY_DOCS="1")
    for k in ("RM_STATE", "RM_MIRROR", "RM_CACHE", "RM_RUN"):
        env.pop(k, None)
    out = subprocess.run([sys.executable, "-c", code], env=env, capture_output=True, text=True, timeout=600)
    assert out.returncode == 0, out.stderr[-3000:]
    return json.loads(out.stdout.strip().splitlines()[-1])


def test_pages_go_right_after_the_page_that_asked(tmp_path):
    d = _run(tmp_path, """
        from paperdaemon.remarkable import library as PG
        a, b, c = notebook("nb", 3)
        new = [pid for pid, _ in PG.insert_pages("nb", a, 2)]
        p, q, r = notebook("pdf", 3, pdf=True)
        before = {e["id"]: e for e in json.load(open(os.path.join(M, "pdf.content")))["cPages"]["pages"]}
        added = [pid for pid, _ in PG.insert_pages("pdf", q, 1)]
        after = {e["id"]: e for e in json.load(open(os.path.join(M, "pdf.content")))["cPages"]["pages"]}
        print(json.dumps({"nb": order("nb") == [a] + new + [b, c], "pdf": order("pdf") == [p, q] + added + [r],
                          "untouched": all(after[k] == v for k, v in before.items()),
                          "no_redir": "redir" not in after[added[0]],
                          "count": json.load(open(os.path.join(M, "nb.content")))["pageCount"]}))
    """)
    assert d == {"nb": True, "pdf": True, "untouched": True, "no_redir": True, "count": 5}


def test_an_ink_adventure_is_played_in_the_notebook_that_asked(tmp_path):
    d = _run(tmp_path, """
        from paperdaemon.pipeline.games import adventure as AD
        from paperdaemon.pipeline.games import chess as CH
        a, b = notebook("nb", 2)
        st, doc = AD.start("an ink adventure", None, doc="nb", after=a, workdir=os.path.join(M, "..", "work"))
        pages = order("nb")
        out = {"doc": doc, "inline": st["format"],
               "order": pages[0] == a and pages[-1] == b and pages[1:4] == [st["sheet"]["page_id"], st["page_id"], st["log_page"]],
               "journal": pages[4:-1] == st["journal_pages"] and len(st["journal_pages"]) > 0,
               "found": CH.load_state("nb", page_id=st["page_id"])["id"] == st["id"]}
        # a turn: the same pages, drawn again in place
        AD.read_action = lambda *a, **k: "I look around"
        res = AD.turn("nb", pages.index(st["page_id"]) + 1, st["page_id"], CH.load_state("nb", page_id=st["page_id"]),
                      lambda q: "{}", lambda q, png=None: "{}", workdir=os.path.join(M, "..", "work"))
        out["turn"] = res[0]
        out["same_pages"] = order("nb")[:4] == pages[:4] and order("nb")[-1] == b
        print(json.dumps(out))
    """)
    assert d == {"doc": "nb", "inline": "inline", "order": True, "journal": True, "found": True, "turn": "done",
                 "same_pages": True}
