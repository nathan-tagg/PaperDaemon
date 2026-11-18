"""A job's own strokes are recorded as its own by their place in the file, not by their shape (11-17, Blue Origin:
lettered dashes shaped like the daemon note's dashes went unrecorded, read as the user's, and survived the erase of
the stale replies they belonged to as "::" marks)."""
import json
import os

from paperdaemon.pipeline import page as PG


def _stroke(parent, item, sig):
    return {"parent": parent, "item_id": item, "sig": sig}


def test_a_new_stroke_shaped_like_an_old_one_is_recorded(monkeypatch, tmp_path):
    before = {"strokes": [_stroke("CrdtId(3, 249)", "CrdtId(3, 10)", "dash"),       # the note's dash
                          _stroke("CrdtId(0, 11)", "CrdtId(2, 1)", "users-word")]}
    after = {"strokes": before["strokes"] + [_stroke("CrdtId(0, 11)", "CrdtId(2, 50)", "dash"),   # the reply's dash
                                             _stroke("CrdtId(0, 11)", "CrdtId(2, 51)", "letter")]}
    monkeypatch.setattr(PG, "snapshot", lambda doc, page: after)
    monkeypatch.setattr(PG, "_hist_dir", lambda snap: str(tmp_path))
    assert PG.record_provenance("doc-id-1", 1, since=before) == 2
    mine = json.load(open(os.path.join(str(tmp_path), "provenance.json"), encoding="utf-8"))["mine"]
    assert set(mine) == {"dash", "letter"}
