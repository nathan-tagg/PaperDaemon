"""A job's receipt (the line at the top of the page and in the Jobs list) says what was erased in a reader's words.
The plan names every id it erases, which the model needs; the receipt of a real job read "erase ink mark 1, ink mark
2, ink mark 3, ink mark 4, ink mark 5; erase ink mark 6, ..." before it got to what was drawn."""
from paperdaemon.pipeline.host import steps as ST


def _erase(what):
    return {"do": "erase", "what": what, "status": "done"}


def test_what_was_erased_is_counted_not_listed():
    assert ST.erased_words([_erase("mark:1..5"), _erase("mark:6..11")]) == "erase 11 ink marks"
    assert ST.erased_words([_erase("mark:4")]) == "erase an ink mark"
    assert ST.erased_words([_erase("para:1")]) == "erase typed paragraph 1"
    assert ST.erased_words([_erase("para:1 para:2"), _erase("line:3"), _erase("picture:1 picture:2")]) == \
        "erase 2 typed paragraphs, a line of handwriting and 2 pictures"
    assert ST.erased_words([_erase("at:1")]) == "erase the ink pointed at"
    assert ST.erased_words([_erase("mark:2"), _erase("mark:2")]) == "erase an ink mark"       # named twice, erased once
    assert ST.erased_words([{"do": "draw", "what": "a house", "status": "done"}]) == "" and ST.erased_words([]) == ""
    # the plan's own wording, for the model, still names each
    assert ST.describe(_erase("mark:1..3")) == "erase ink mark 1, ink mark 2, ink mark 3"


def test_checkboxes_made_are_counted_not_named_by_id():
    box = lambda targets, checked=False: {"do": "checkbox", "what": "", "targets": targets, "checked": checked, "status": "done"}
    # a real receipt read "make para:2, para:3, para:4, para:5 the tablet's checkboxes; make para:3 the tablet's ticked checkboxes"
    assert ST.checkbox_words([box(["para:2", "para:3", "para:4", "para:5"]), box(["para:3"], True)]) == "make 4 checkboxes, 1 of them ticked"
    assert ST.checkbox_words([box(["para:2"])]) == "make a checkbox"
    assert ST.checkbox_words([box(["para:2", "para:3"], True)]) == "make 2 ticked checkboxes"
    assert ST.checkbox_words([_erase("mark:1")]) == ""
