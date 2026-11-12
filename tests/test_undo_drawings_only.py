"""undo_last takes back only what was drawn: an erase staged before the drawing (the request taken off the page) stays,
however many parts the model asks for (11-11: undo_last(5) after a one-op scarf brought the typed request back)."""
import types

from paperdaemon.pipeline import host as H
from paperdaemon.pipeline.host import commit as C


def _job(monkeypatch, ops, marks, strokes):
    job = types.SimpleNamespace(ops=list(ops), marks=list(marks), draw=types.SimpleNamespace(strokes=list(strokes)))
    monkeypatch.setattr(C, "JOB", job)
    unstaged = []
    monkeypatch.setattr(H, "_unstage", lambda idx: unstaged.append(idx))
    monkeypatch.setattr(H, "_did", lambda: {})
    return job, unstaged


def test_undo_stops_at_the_erase_of_the_request(monkeypatch):
    job, unstaged = _job(monkeypatch, ["typed text erased: 'Now give him a scarf please :)'", "figure of 5 part(s)"],
                         [0, 0], ["s1", "s2", "s3", "s4", "s5"])
    r = C.t_undo_last(5)
    assert r["ok"] and job.ops == ["typed text erased: 'Now give him a scarf please :)'"]
    assert job.draw.strokes == [] and unstaged == [2]
    r = C.t_undo_last(1)
    assert "error" in r and job.ops == ["typed text erased: 'Now give him a scarf please :)'"]


def test_undo_takes_several_drawings_back(monkeypatch):
    job, _ = _job(monkeypatch, ["figure of 2 part(s)", "element star at (10,10)"], [0, 2], ["a", "b", "c"])
    assert C.t_undo_last(2)["ok"] and job.ops == [] and job.draw.strokes == []
