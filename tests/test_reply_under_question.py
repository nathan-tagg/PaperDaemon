"""A reply goes under what it answers when the free paper there holds it (DF107: the answer went below a note to
someone at the page's foot, a screen and a half under its own question); one that does not fit there still goes
below everything, and a question staged for erasing hands its place to the stack."""
from paperdaemon.pipeline import host as H
from paperdaemon.pipeline import draw as A
from paperdaemon.pipeline.host import job as J
from paperdaemon.pipeline.host.features import write as W
from paperdaemon.pipeline.page import typed as TY

QUESTION = {"text": "What are some gentle ways to get a toddler to eat more vegetables?", "y": 234.0, "lh": 35.748,
            "size": 30.0, "lines": ["What are some gentle ways to get a toddler to eat", "more vegetables?"]}


def _job(monkeypatch, staged=()):
    J.begin(doc="nodoc", page=1, frame=(1620.0, 2160.0), draw=A.Drawing(), ops=[])
    monkeypatch.setattr(TY, "paragraphs", lambda doc, page: (None, [dict(QUESTION)]))
    monkeypatch.setattr(H, "_reflow", lambda: {})
    H.JOB.hide_typed = list(staged)
    H.JOB.steps = [{"id": 1, "do": "write", "what": "the answer", "answers": ["para:1"], "place": "s1",
                    "status": "doing"}]
    note = (-300.0, 1900.0, 300.0, 1995.0)                       # "Jen - plumber Tue 9am" near the foot
    H.JOB.plan = {"places": {"s1": {"x0": -576.0, "y0": 2025.0, "x1": 576.0, "y1": 2150.0}},
                  "reflow": {"obstacles": [(-576.0, 239.0, 520.0, 312.0), note]}}


def test_a_reply_that_fits_goes_under_its_question(monkeypatch):
    _job(monkeypatch)
    top = W._under_answered(1393.0, -576.0, 576.0)
    bottom = H._line_ink(QUESTION, 1)[1]
    assert top is not None and abs(top - (bottom + 25)) < 1e-6 and top < 400


def test_one_too_tall_for_the_gap_still_goes_below_everything(monkeypatch):
    _job(monkeypatch)
    assert W._under_answered(1700.0, -576.0, 576.0) is None


def test_a_question_staged_for_erasing_hands_its_place_to_the_stack(monkeypatch):
    from paperdaemon.pipeline import page as ER
    _job(monkeypatch, staged=["What are some gentle ways"])
    monkeypatch.setattr(ER, "staged_paragraphs", lambda texts, passages: {0})
    assert W._under_answered(400.0, -576.0, 576.0) is None


def test_the_plans_box_moves_with_the_words_so_the_commit_finds_them(monkeypatch):
    # DF108: written under its question, the reply was reported "nothing landed in the box" -- the check looked where
    # the box had been planned, at the page's foot -- and the job was marked failed with its answer on the page
    from paperdaemon.pipeline.host import layout as PL
    _job(monkeypatch)
    got = W.t_write_paragraph(["A two-year-old turning down greens is very common.", "Keep offering, without pressure."])
    box = H.JOB.plan["places"]["s1"]
    assert got.get("ok"), got
    assert box["y0"] < 400 and PL.covered(box, H.JOB.draw.strokes)
