"""The host's loop: jobs taken from the queue oldest first, an unreadable one dropped, and a job that crashes
recorded as skipped with its error rather than left "working"."""
import json
import os

import paperdaemon.pipeline.host as H


def test_the_queue_is_read_oldest_first_and_junk_is_dropped(tmp_path, monkeypatch):
    monkeypatch.setattr(H, "QUEUE", str(tmp_path))
    (tmp_path / "0-junk.json").write_text("{not json", encoding="utf-8")
    (tmp_path / "1-a.json").write_text(json.dumps({"keys": ["a"]}), encoding="utf-8")
    (tmp_path / "2-b.json").write_text(json.dumps({"keys": ["b"]}), encoding="utf-8")
    job = H.Host().next_job()
    assert job["keys"] == ["a"] and not os.path.exists(tmp_path / "0-junk.json")


def test_a_crash_is_recorded_not_left_working(tmp_path, monkeypatch):
    marked = []
    monkeypatch.setattr(H, "ensure_server", lambda: True)
    monkeypatch.setattr(H, "run_job", lambda job: 1 / 0)
    monkeypatch.setattr(H.S, "load", lambda: {"entries": {"k1": {"status": "working"}, "k2": {"status": "done"}}})
    monkeypatch.setattr(H.S, "mark", lambda k, status, failed=False, note="": marked.append((k, status, failed, note)))
    p = tmp_path / "job.json"
    p.write_text("{}", encoding="utf-8")
    H.Host().work({"keys": ["k1", "k2"], "_path": str(p)})
    assert [(k, s, f) for k, s, f, _ in marked] == [("k1", "skipped", True)] and "ZeroDivisionError" in marked[0][3]
    assert not p.exists()
