"""The daemon's page states (ledger.classify): new, waiting (nothing on the page yet), baseline (a page tagged at
the start, or one of a notebook that would start more than ten jobs at once), done, reopened (the page changed), retagged (the same page, its tag taken off and put
back), and a dead worker's claim given back."""
from paperdaemon import ledger


def found(key="aaaaaaaa/bbbbbbbb", sha="s1", empty=False, tag_ts="100", inherited=None, modifed="100", tag="paperdaemon"):
    return {"key": key, "doc": "Notes", "doc_id": "doc-" + key[:8], "page_id": key[9:], "page": 1, "tag": tag,
            "instruction": "", "tag_ts": tag_ts, "inherited": inherited, "modifed": modifed, "scope": "page",
            "state": {"sha": sha, "raw": "raw-" + sha, "empty": empty}}


def status(f, led):
    return ledger.classify([f], led)[0]["status"]


def test_a_page_goes_through_its_states():
    led = {"entries": {}, "watching_since": 0}
    assert status(found(empty=True), led) == "WAITING"        # tagged before its ink arrived
    assert status(found(), led) == "PENDING"                  # now it has something on it
    e = led["entries"]["aaaaaaaa/bbbbbbbb"]
    e.update(status="done", handled_sha="s1", handled_tag_ts="100")
    assert status(found(), led) == "DONE"                     # unchanged: nothing to do
    assert status(found(sha="s2"), led) == "REOPENED"         # the user wrote on it again
    e.update(status="done", handled_sha="s2", handled_tag_ts="100")
    assert status(found(sha="s2", tag_ts="200"), led) == "RETAGGED"   # the tag taken off and put back
    e.update(status="done", handled_sha="s2", handled_tag_ts="200")
    assert status(found(sha="s3", empty=True, tag_ts="200"), led) == "WAITING"   # cleared: wait for a request


def test_a_new_page_is_new_whatever_the_age_of_the_tag_that_reaches_it():
    # the user's rule: after the start, a page met for the first time is a new page -- a notebook tagged a month
    # ago gets a page today, and that page is a job, not "tagged before PaperDaemon was watching"
    assert status(found(), {"entries": {}, "watching_since": 0}) == "NEW"
    old_tag = found(inherited="document", tag_ts="1000", modifed=str(10 ** 12))
    led = {"entries": {}, "watching_since": 10 ** 9}
    assert status(old_tag, led) == "NEW" and led["entries"][old_tag["key"]]["why"] == "new"


def test_a_dead_workers_claim_is_given_back():
    led = {"entries": {}, "watching_since": 0}
    status(found(), led)
    led["entries"]["aaaaaaaa/bbbbbbbb"].update(status="working", claim_owner="host", claim_at=0)
    assert status(found(), led) == "PENDING"
    assert "claim_owner" not in led["entries"]["aaaaaaaa/bbbbbbbb"]


def test_pages_already_tagged_when_paperdaemon_starts_are_never_a_backlog():
    led = {"entries": {}}                                        # a new install's first look: the start
    assert status(found(tag_ts="1700000000000"), led) == "BASELINE"
    assert led["entries"]["aaaaaaaa/bbbbbbbb"]["status"] == "skipped"
    # after the start, a page met for the first time is a job, whatever its tag's age
    assert status(found(key="cccccccc/dddddddd", tag_ts="1700000000000"), led) == "NEW"
    # the page recorded at the start comes back when it is edited, and when its tag is put on again
    assert status(found(sha="s2", tag_ts="1700000000000"), led) == "REOPENED"
    assert led["entries"]["aaaaaaaa/bbbbbbbb"]["why"] == "changed"


def test_a_notebook_that_would_start_more_than_ten_jobs_starts_none():
    # a notebook created, uploaded or moved into a tagged folder arrives whole: eleven new pages in one look are
    # all recorded as they are, and none is a job; ten are ten jobs
    def pages(doc, n):
        return [dict(found(key="%s/p%07d" % (doc, i)), doc_id=doc) for i in range(n)]
    led = {"entries": {}, "watching_since": 0}
    q = ledger.classify(pages("eleven00", 11) + pages("tenpages", 10), led)
    by = lambda d: [f["status"] for f in q if f["doc_id"] == d]
    assert by("eleven00") == ["BASELINE"] * 11 and by("tenpages") == ["NEW"] * 10
    e = led["entries"]["eleven00/p0000000"]
    assert e["status"] == "skipped" and e["note"] == ledger.TOO_MANY and e["handled_sha"] == "s1"
    # an edit afterward brings one page back, on its own
    q = ledger.classify([dict(found(key="eleven00/p0000003", sha="s9"), doc_id="eleven00")], led)
    assert q[0]["status"] == "REOPENED"


def test_changed_pages_are_handed_over_before_new_ones():
    from paperdaemon.pipeline import daemon as DM
    rows = [dict(found(key="aaaaaaaa/p1"), page=1, status="NEW", why="new"),
            dict(found(key="aaaaaaaa/p2"), page=2, status="REOPENED", why="changed"),
            dict(found(key="bbbbbbbb/p1"), doc_id="b", page=1, status="PENDING", why="changed"),
            dict(found(key="bbbbbbbb/p2"), doc_id="b", page=2, status="PENDING", why="new")]
    assert [j["key"] for j in DM.batch(rows)] == ["aaaaaaaa/p2", "bbbbbbbb/p1", "aaaaaaaa/p1", "bbbbbbbb/p2"]


def test_pages_tagged_before_watching_are_not_listed_as_jobs(monkeypatch):
    led = {"entries": {}}
    status(found(tag_ts="1700000000000"), led)
    monkeypatch.setattr(ledger, "entries", lambda state=None: led["entries"])
    assert ledger.jobs() == []


def test_a_dead_claim_on_a_page_no_longer_found_is_given_back():
    # the page lost its tag (or was deleted) while a job that then died held it: the claim still expires
    led = {"entries": {}, "watching_since": 0}
    status(found(), led)
    led["entries"]["aaaaaaaa/bbbbbbbb"].update(status="working", claim_owner="daemon", claim_at=0)
    ledger.classify([], led)
    e = led["entries"]["aaaaaaaa/bbbbbbbb"]
    assert e["status"] == "pending" and "claim_owner" not in e


def test_a_claim_older_than_the_running_host_is_released(tmp_path, monkeypatch):
    # an update restarts the daemon and the host together: a job the old host had is handed over again at once,
    # and a job the running host took is left alone
    import time
    monkeypatch.setattr(ledger, "LEDGER", str(tmp_path / "ledger.json"), raising=False)
    led = {"entries": {"a/old": {"status": "working", "claim_owner": "daemon", "claim_at": 100},
                       "a/new": {"status": "working", "claim_owner": "daemon", "claim_at": int(time.time())},
                       "a/done": {"status": "done"}}, "watching_since": 0}
    monkeypatch.setattr(ledger, "load", lambda: led)
    monkeypatch.setattr(ledger, "save", lambda l: None)
    assert ledger.release_dead_claims(1000) == ["a/old"]
    assert led["entries"]["a/old"]["status"] == "pending" and "claim_owner" not in led["entries"]["a/old"]
    assert led["entries"]["a/new"]["status"] == "working"


def test_a_waiting_job_on_a_deleted_page_is_dropped(tmp_path, monkeypatch):
    # the page was deleted from its notebook: its job can never run, so it leaves the ledger (and Jobs) -- but only
    # when the Mirror is complete and the notebook says so; a page merely not found this scan is kept
    import json
    from paperdaemon.remarkable import sync
    monkeypatch.setattr(ledger, "RM", str(tmp_path))
    (tmp_path / "doc1.content").write_text(json.dumps({"cPages": {"pages": [
        {"id": "live", "idx": {"value": "ba"}}, {"id": "gone", "idx": {"value": "bb"}, "deleted": {"value": 1}}]}}))
    led = {"watching_since": 0, "entries": {
        "doc1/gone": {"status": "pending", "doc_id": "doc1", "page_id": "gone"},
        "doc1/live": {"status": "pending", "doc_id": "doc1", "page_id": "live"},
        "doc1/busy": {"status": "working", "doc_id": "doc1", "page_id": "gone", "claim_owner": "daemon",
                      "claim_at": int(__import__("time").time())}}}
    monkeypatch.setattr(sync, "mirrored", lambda: False)
    ledger.classify([], led)
    assert "doc1/gone" in led["entries"]                      # a Mirror still filling proves nothing
    monkeypatch.setattr(sync, "mirrored", lambda: True)
    ledger.classify([], led)
    assert "doc1/gone" not in led["entries"]                  # deleted page: dropped
    assert "doc1/live" in led["entries"]                      # the page is there (its tag may come back)
    assert led["entries"]["doc1/busy"]["status"] == "working"  # a job being worked is not pulled out from under it


def test_tags_of_two_lineups_in_a_pages_path_are_flagged_and_one_lineups_are_not(monkeypatch):
    # a page tag of one lineup under a folder tag of another: nobody's job (the daemon notes it on the page);
    # two tags of the same lineup: the most specific wins, as ever
    monkeypatch.setattr(ledger, "TRIGGERS", ["qwen", "claude", "fast"])
    monkeypatch.setattr(ledger, "LINEUP_OF", {"qwen": "Local", "fast": "Local", "claude": "Cloud"})
    meta = {"visibleName": "Notes", "type": "DocumentType"}
    content = {"cPages": {"pages": [{"id": "p1", "idx": {"value": "ba"}}]},
               "pageTags": [{"name": "qwen", "pageId": "p1", "timestamp": 1}]}
    mixed = ledger._extract("doc1", meta, content, ("claude", "", 1))
    assert mixed[0]["lineups"] == ["Cloud", "Local"]
    same = ledger._extract("doc1", meta, content, ("fast", "", 1))
    assert "lineups" not in same[0] and same[0]["tag"] == "qwen"


def test_a_page_skipped_for_two_lineups_is_worked_once_its_tags_are_one_lineups():
    led = {"entries": {}, "watching_since": 0}
    status(found(), led)
    led["entries"]["aaaaaaaa/bbbbbbbb"].update(status="skipped", handled_sha="s1", handled_tag_ts="100",
                                              tag_conflict=True)
    f = dict(found(), lineups=["Cloud", "Local"])
    assert status(f, led) == "SKIPPED"                         # still two lineups: left alone, no second note
    assert status(found(), led) == "PENDING"                   # one lineup's now: worked, though nothing changed
    assert "tag_conflict" not in led["entries"]["aaaaaaaa/bbbbbbbb"]
