"""An elsewhere step hands its request to another page: a page of this notebook, a new page after this one, or a new
notebook. The host makes what is new, tags a page no tag reaches, and files it as asked for; the daemon then runs it
though the page is blank, and the job there is told where its request came from (11-12: the Opus lineup could only
tell the user to write the request on the new page and tag it themselves)."""
import paperdaemon.pipeline.host as H
from paperdaemon import ledger as S
from paperdaemon.pipeline.host import steps as ST
from paperdaemon.pipeline.host.features import elsewhere as EW
from paperdaemon.pipeline.page import render as R

DOC = "resumedoc-for-the-test"
PAGES = [{"id": "p1-aaaaaaaa"}, {"id": "p2-bbbbbbbb"}, {"id": "p3-cccccccc"}, {"id": "p4-dddddddd"}]
SRC = {"doc": "Resume", "doc_id": DOC, "page_id": "p3-cccccccc", "page": 3, "tag": "Opus", "instruction": "",
       "tag_ts": 5, "status": "working"}


def _setup(monkeypatch, doc_tags=()):
    led = {"entries": {"resumedo/p3-ccccc": dict(SRC)}}
    tagged = []
    monkeypatch.setattr(S, "load", lambda: led)
    monkeypatch.setattr(S, "save", lambda l: None)
    monkeypatch.setattr(S, "content", lambda d: {"tags": [{"name": t} for t in doc_tags]})
    monkeypatch.setattr(S, "meta", lambda d: {"visibleName": "Resume", "parent": ""})
    pages = list(PAGES)
    monkeypatch.setattr(R, "live_pages", lambda d: pages)
    from paperdaemon.remarkable import library as PG
    monkeypatch.setattr(PG, "tag_page", lambda d, pid, name: tagged.append((pid, name)) or True)

    def insert(d, after, n):
        pages.insert([p["id"] for p in pages].index(after) + 1, {"id": "new-eeeeeeee"})
        return [("new-eeeeeeee", None)]
    monkeypatch.setattr(PG, "insert_pages", insert)
    monkeypatch.setattr(H, "log", lambda *a, **k: None)
    H.JOB.clear()
    H.JOB.doc, H.JOB.page, H.JOB.page_id, H.JOB.keys = DOC, 3, "p3-cccccccc", ["resumedo/p3-ccccc"]
    return led, tagged


def test_a_new_page_after_this_one_is_made_tagged_and_filed_as_asked(monkeypatch):
    led, tagged = _setup(monkeypatch)
    step = ST.build([{"do": "elsewhere", "page": "new", "what": "Rewrite page 2 with PaperDaemon first."}])[0]
    ok, note = EW.run(step)
    e = led["entries"]["resumedo/new-eeee"]
    assert ok and "page 4" in note and tagged == [("new-eeeeeeee", "Opus")]
    assert e["status"] == "pending" and e["why"] == "asked" and e["page"] == 4 and e["tag"] == "Opus"
    assert e["asked"] == {"from": "Resume, page 3", "what": "Rewrite page 2 with PaperDaemon first."}
    told = EW.asked_text(e["asked"])
    assert "FROM Resume, page 3" in told and told.endswith("Rewrite page 2 with PaperDaemon first.")


def test_a_page_of_this_notebook_is_handed_the_work_and_a_whole_notebook_tag_is_left_alone(monkeypatch):
    led, tagged = _setup(monkeypatch, doc_tags=("Opus",))
    ok, _ = EW.run(ST.build([{"do": "elsewhere", "page": 4, "what": "x"}])[0])
    assert ok and tagged == [] and led["entries"]["resumedo/p4-ddddd"]["asked"]["what"] == "x"
    assert EW.run(ST.build([{"do": "elsewhere", "page": 3, "what": "x"}])[0])[0] is False      # this page
    ok, why = EW.run(ST.build([{"do": "elsewhere", "page": 9, "what": "x"}])[0])
    assert not ok and "4 pages" in why


def test_a_new_notebook_is_made_beside_this_one_tagged_for_the_lineup(monkeypatch):
    led, _ = _setup(monkeypatch)
    from paperdaemon.remarkable import local
    made = []
    monkeypatch.setattr(local, "new_notebook", lambda name, parent="", tags=(), tablet=False: made.append(
        (name, parent, tags)) or "f00dcafe-0000")
    real = R.live_pages
    monkeypatch.setattr(R, "live_pages", lambda d: [{"id": "first-ffffffff"}] if d == "f00dcafe-0000" else real(d))
    ok, note = EW.run(ST.build([{"do": "elsewhere", "notebook": "Resume v2", "what": "The resume, rewritten."}])[0])
    e = led["entries"]["f00dcafe/first-ff"]
    assert ok and made == [("Resume v2", "", ("Opus",))] and e["doc"] == "Resume v2" and e["inherited"]
    assert "new notebook 'Resume v2'" in note


def test_a_blank_page_handed_work_is_a_job_not_waiting():
    led = {"entries": {"k": {"status": "pending", "why": "asked", "asked": {"what": "x"}, "tag": "Opus"}}}
    found = [{"key": "k", "doc": "d", "doc_id": "d", "page_id": "p", "page": 4, "tag": "Opus", "instruction": "",
              "state": {"empty": True, "sha": "s", "raw": "r"}}]
    assert S.classify(found, dict(led, watching_since=1))[0]["status"] == "PENDING"
    del led["entries"]["k"]["asked"]
    assert S.classify(found, dict(led, watching_since=1))[0]["status"] == "WAITING"
