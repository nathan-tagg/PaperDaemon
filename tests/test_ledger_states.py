"""The daemon's page states (ledger.classify): new, waiting (nothing on the page yet), baseline (an old page an
inherited tag reached), done, reopened (the page changed), retagged (the same page, its tag taken off and put
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


def test_a_new_page_is_new_and_an_old_page_under_an_inherited_tag_is_a_baseline():
    assert status(found(), {"entries": {}, "watching_since": 0}) == "NEW"
    old = found(inherited="collection", tag_ts=str(10 ** 12), modifed="1000")    # written long before the tag
    led = {"entries": {}, "watching_since": 0}
    assert status(old, led) == "BASELINE" and led["entries"][old["key"]]["status"] == "skipped"


def test_a_dead_workers_claim_is_given_back():
    led = {"entries": {}, "watching_since": 0}
    status(found(), led)
    led["entries"]["aaaaaaaa/bbbbbbbb"].update(status="working", claim_owner="host", claim_at=0)
    assert status(found(), led) == "PENDING"
    assert "claim_owner" not in led["entries"]["aaaaaaaa/bbbbbbbb"]


def test_pages_already_tagged_when_paperdaemon_starts_are_never_a_backlog():
    led = {"entries": {}}                                        # a new install's first look
    assert status(found(tag_ts="1700000000000"), led) == "BASELINE"
    assert led["entries"]["aaaaaaaa/bbbbbbbb"]["status"] == "skipped"
    since = led["watching_since"]
    # a page met later whose tag is older than the watch: still not a job
    assert status(found(key="cccccccc/dddddddd", tag_ts=str((since - 60) * 1000)), led) == "BASELINE"
    # a tag put on after PaperDaemon began watching: a job
    assert status(found(key="eeeeeeee/ffffffff", tag_ts=str((since + 5) * 1000)), led) == "NEW"
    # the old page comes back once its tag is put on again
    assert status(found(tag_ts=str((since + 9) * 1000)), led) == "RETAGGED"


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
