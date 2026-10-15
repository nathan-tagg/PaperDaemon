"""The two fixed tag names. "ignore" stops every job at whatever level it is written (a folder, a notebook, a
page); "sprompt" counts only as a page tag: that page is never a job, and on a notebook or folder the tag
means nothing. Both are matched without regard to case."""
import json
import os
import subprocess
import sys
import textwrap

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

SCAN = textwrap.dedent("""
    import json, os, sys
    sys.path.insert(0, %(pipeline)r)
    from paperdaemon import ledger as S
    out = {}
    for doc in sorted(n[:-8] for n in os.listdir(S.RM) if n.endswith(".content") and not n.startswith("f-")):
        m = S.meta(doc)
        if S.muted(doc, m):
            out[doc] = "muted"
            continue
        inh, _ = S.inherited_tag(m)
        out[doc] = sorted(it["page_id"] for it in S._extract(doc, m, S.content(doc), inh))
    out["names"] = [S.IGNORE_TAG, S.SPROMPT_TAG]
    print(json.dumps(out))
""")


def _write(mirror, doc, name, parent="", tags=(), page_tags=(), pages=(), folder=False):
    with open(os.path.join(mirror, doc + ".metadata"), "w", encoding="utf-8") as f:
        json.dump({"visibleName": name, "parent": parent,
                   "type": "CollectionType" if folder else "DocumentType"}, f)
    with open(os.path.join(mirror, doc + ".content"), "w", encoding="utf-8") as f:
        json.dump({"tags": [{"name": t, "timestamp": 1} for t in tags],
                   "pageTags": [{"name": t, "pageId": p, "timestamp": 1} for p, t in page_tags],
                   "cPages": {"pages": [{"id": p} for p in pages]}}, f)


def test_ignore_at_every_level_and_sprompt_only_on_a_page(tmp_path):
    mirror = tmp_path / "mirror"
    mirror.mkdir(exist_ok=True)
    m = str(mirror)
    _write(m, "f-watched", "Watched", tags=["PaperDaemon"], folder=True)
    _write(m, "f-quiet", "Quiet", tags=["IGNORE"], folder=True)
    # in a watched folder: one page left alone by ignore, one page that holds the notebook's prompt
    _write(m, "nb-a", "A", parent="f-watched", pages=["p1", "p2", "p3"],
           page_tags=[("p2", "Ignore"), ("p3", "SPROMPT")])
    # a notebook tagged ignore, inside the watched folder: nothing
    _write(m, "nb-b", "B", parent="f-watched", tags=["ignore"], pages=["p1"])
    # a notebook tagged for PaperDaemon inside an ignored folder: nothing
    _write(m, "nb-c", "C", parent="f-quiet", tags=["PaperDaemon"], pages=["p1"])
    # sprompt on a NOTEBOOK means nothing: its triggered page is still a job, and it mutes nothing
    _write(m, "nb-d", "D", tags=["sprompt"], pages=["p1", "p2"], page_tags=[("p1", "PaperDaemon")])
    # an sprompt page carrying the trigger tag too is still never a job
    _write(m, "nb-e", "E", tags=["PaperDaemon"], pages=["p1", "p2"],
           page_tags=[("p1", "sprompt"), ("p1", "PaperDaemon")])
    # the decompose inbox is never worked, whatever it is tagged with; a notebook of the same name elsewhere is
    _write(m, "f-inbox", "Pictures", folder=True)
    _write(m, "nb-inbox", "Inbox", parent="f-inbox", tags=["PaperDaemon"], pages=["p1"])
    _write(m, "nb-other", "Inbox", tags=["PaperDaemon"], pages=["p1"])
    # every lineup's tags are watched at once
    _write(m, "nb-draw", "Draw", tags=["Draw: a cat"], pages=["p1"])
    env = dict(os.environ, RM_CACHE=m, RM_MIRROR=m, RM_STATE=str(tmp_path), RM_TRIGGERS='["PaperDaemon", "Draw"]',
               RM_INBOX="Pictures/Inbox", RM_MUTE_TAG="quiet")        # an old setting changes nothing; the lineup names them (RM_IGNORE_TAG, RM_SPROMPT_TAG)
    out = subprocess.run([sys.executable, "-c", SCAN % {"pipeline": os.path.join(ROOT, "paperdaemon", "pipeline")}],
                         env=env, capture_output=True, text=True, timeout=300)
    assert out.returncode == 0, out.stderr[-2000:]
    d = json.loads(out.stdout.strip().splitlines()[-1])
    assert d["names"] == ["ignore", "sprompt"]
    assert d["nb-a"] == ["p1"]                  # p2 ignored, p3 the notebook's prompt
    assert d["nb-b"] == "muted" and d["nb-c"] == "muted"
    assert d["nb-d"] == ["p1"]
    assert d["nb-e"] == ["p2"]
    assert d["nb-inbox"] == "muted" and d["nb-other"] == ["p1"]
    assert d["nb-draw"] == ["p1"]
