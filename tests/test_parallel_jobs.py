"""Jobs in parallel (run-jobs-in-parallel): the engine answers each request for the lineup it names; a lineup is local
when its text model runs on this computer; the host starts one job per notebook and one local job at a time; a job's
push holds back what other jobs still work; the documents a job makes are its own, and Abandon removes only those."""
import json
import os

from fastapi.testclient import TestClient

import paperdaemon.pipeline.host as H
from paperdaemon import paths, server, settings
from paperdaemon.models import slots


def _lineups():
    return {"lineups": [
        {"name": "Cloud", "text": {"location": "https://api.example.com/v1", "api": "anthropic"}, "image": {}},
        {"name": "Cli", "text": {"location": "claude -p", "api": "cli"}, "image": {"location": "http://127.0.0.1:7860"}},
        {"name": "Llama", "text": {"location": "http://127.0.0.1:8080", "api": "openai"}, "image": {}},
        {"name": "Scripted", "text": {"location": "http://10.0.0.5:8080", "script": "start.bat"}, "image": {}},
    ]}


def test_a_lineup_is_local_when_its_text_model_runs_here(monkeypatch):
    s = _lineups()
    monkeypatch.setattr(settings, "lineup", lambda s_=None, name=None: next(
        (lu for lu in s["lineups"] if lu["name"] == name), None))
    got = {lu["name"]: slots.uses_card(s, lu["name"]) for lu in s["lineups"]}
    # a command line runs in parallel even with its pictures on the card; a cloud API too; a server here or a start
    # script is the card's
    assert got == {"Cloud": False, "Cli": False, "Llama": True, "Scripted": True}
    assert slots.uses_card(s, "nobody") is True                 # a lineup not known: taken as local


def test_each_request_is_answered_for_the_lineup_it_names(monkeypatch):
    names = [lu["name"] for lu in settings.load()["lineups"]]
    assert len(names) >= 1
    c = TestClient(server.app)
    c.headers["Authorization"] = "Bearer " + server.pairing_token()
    for n in names:
        r = c.get("/api/v1/status", headers={"X-PD-Lineup": n})
        assert r.status_code == 200 and r.json()["lineup"] == n, r.text
    assert settings.of_request() is None                          # (held for that request alone)


def _job(doc, lineup):
    return {"keys": [doc + "-p1"], "_doc": doc, "_lineup": lineup}


def test_the_host_starts_one_job_per_notebook_and_one_local_job_at_a_time(monkeypatch):
    host = H.Host()
    monkeypatch.setattr(H.Host, "doc_and_lineup", staticmethod(lambda job: (job["_doc"], job["_lineup"])))
    monkeypatch.setattr(H.Host, "is_local", staticmethod(lambda lineup: lineup == "Llama"))
    jobs = [_job("A", "Cloud"), _job("A", "Cloud"), _job("B", "Llama"), _job("C", "Llama"), _job("D", "Cli")]
    got = [(j["_doc"], j["_lineup"]) for j in host.choose(jobs, {})]
    assert got == [("A", "Cloud"), ("B", "Llama"), ("D", "Cli")]  # A's second page waits; C waits for B (local)
    running = {"B": {"local": True}, "A": {"local": False}}
    got = [(j["_doc"], j["_lineup"]) for j in host.choose(jobs, running)]
    assert got == [("D", "Cli")]                                  # A and B have theirs; C waits for the card


def test_a_jobs_push_holds_back_what_other_jobs_still_work(monkeypatch):
    from paperdaemon.remarkable import sync
    monkeypatch.setattr(sync.paths, "local_only", lambda: False)
    monkeypatch.delenv("RM_HOST_DRY_DOCS", raising=False)
    monkeypatch.setattr(sync, "unpushed", lambda: (["new-mine", "new-theirs"], {"A": {"p1"}, "B": {"p2"}}))
    sent = []
    monkeypatch.setattr(sync, "push_new_doc", lambda u, dry_run=True: sent.append(("new", u)) or {"root_put": 200})
    monkeypatch.setattr(sync, "push_doc", lambda u, dry_run=True: sent.append(("push", u)) or {"root_put": 200})
    monkeypatch.setattr(sync, "touch", lambda u, pages=None: {})
    sync.push_pending(hold={"B", "new-theirs"})
    assert sent == [("new", "new-mine"), ("push", "A")]


def test_the_documents_a_job_makes_are_its_own(tmp_path, monkeypatch):
    monkeypatch.setenv("RM_STATE", str(tmp_path))
    monkeypatch.setenv("PD_JOB", "job-1")
    lib = tmp_path / "lib"
    lib.mkdir()
    paths.write_json_atomic(str(lib / "made-1.metadata"), {"visibleName": "x"})
    paths.write_json_atomic(str(lib / "made-1.metadata"), {"visibleName": "y"})     # written again: still one
    paths.write_json_atomic(str(lib / "made-1.content"), {})
    monkeypatch.delenv("PD_JOB")
    paths.write_json_atomic(str(lib / "not-a-job.metadata"), {})                     # no job: nobody's
    assert paths.made_by("job-1") == ["made-1"] and paths.made_by("job-2") == []


def test_abandon_removes_only_what_that_job_made(tmp_path, monkeypatch):
    from paperdaemon.remarkable import sync
    monkeypatch.setattr(sync, "MIRROR", str(tmp_path))
    monkeypatch.setattr(sync, "_state", lambda: {"docs": {"in-cloud": "h"}, "files": {}})
    for u in ("mine", "theirs", "in-cloud"):
        (tmp_path / (u + ".metadata")).write_text("{}", encoding="utf-8")
        (tmp_path / (u + ".content")).write_text("{}", encoding="utf-8")
        (tmp_path / u).mkdir()
    assert sync.drop_docs(["mine", "in-cloud"]) == ["mine"]
    left = sorted(os.listdir(tmp_path))
    assert "mine.metadata" not in left and "mine" not in left
    assert "theirs.metadata" in left and "in-cloud.metadata" in left


def test_the_daemon_holds_back_the_other_flights(monkeypatch, tmp_path):
    import paperdaemon.pipeline.daemon as D
    monkeypatch.setenv("RM_STATE", str(tmp_path))
    monkeypatch.setattr(D, "FLIGHTS", {"A": {"keys": ["A-p1"], "key": "A-p1"}, "B": {"keys": ["B-p1"], "key": "B-p1"}})
    with open(os.path.join(paths.jobs_dir(), paths.job_id("B-p1") + ".made"), "w", encoding="utf-8") as f:
        f.write("journal-of-b\n")
    assert D.held_by_others("A") == {"B", "journal-of-b"}
    assert D.held_by_others(None) == {"A", "B", "journal-of-b"}
    assert D._doc_of({"doc_id": "A"}) == "A" and D._doc_of({"batch": [{"doc_id": "B"}]}) == "B"
    json.dumps(D.FLIGHTS)
