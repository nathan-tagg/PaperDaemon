"""ask(): the model asks the user for what a request cannot be done without, and the request stays on the page."""
import paperdaemon.pipeline.host as H


def test_ask_is_a_decision_and_the_brief_says_when(monkeypatch):
    assert "ask" in H.PLAN_TOOLS and "ask" in [t[0] for t in H.TOOLS]
    monkeypatch.setattr(H, "HOME_PLACE", "")
    monkeypatch.setattr(H, "_BRIEF", None)
    brief = H.system_brief()
    assert "The user's place is not set." in brief and "ASKING." in brief
    assert "never ask" not in brief


def test_ask_writes_the_question_and_nothing_comes_off(monkeypatch):
    seen = {}

    def fake_reply(lines, answers=(), rulings=(), size=34, task=None):
        seen.update(task=task, lines=lines, answers=answers, rulings=rulings)
        return {"ok": True}
    monkeypatch.setattr(H, "_reply", fake_reply)
    H.JOB.clear()
    try:
        assert H.t_ask(["Which city should the weather calendar be for?"]) == {"ok": True}
        assert seen["rulings"] == () and seen["answers"] == ()       # nothing is ruled, so nothing comes off
        assert seen["lines"] == ["Which city should the weather calendar be for?"] and H.JOB.asking is True
    finally:
        H.JOB.clear()


def test_markdown_becomes_bold_and_italic_words_never_symbols():
    shown, words = H._md_words("## A **bold** word, an *italic* one and `code`")
    assert "*" not in shown and "#" not in shown and "`" not in shown
    by = {w.strip(",."): (b, i) for w, b, i in words}
    assert by["bold"] == (True, False) and by["italic"][1] is True and by["code"] == (by["code"][0], False)
    assert by["A"][0] is True                                   # a heading is drawn bold


def test_a_coloring_page_is_pure_black_lines_on_white(tmp_path):
    from PIL import Image, ImageDraw
    import numpy as np
    p = str(tmp_path / "c.png")
    im = Image.new("RGB", (120, 120), "white")
    d = ImageDraw.Draw(im)
    d.rectangle([20, 20, 100, 100], fill=(170, 170, 170), outline=(0, 0, 0), width=3)   # shaded inside a line
    d.ellipse([40, 40, 80, 80], fill=(90, 140, 200))                                    # a colored fill
    im.save(p)
    H._ink_only(p)
    a = np.asarray(Image.open(p).convert("RGB"))
    assert set(np.unique(a)) <= {0, 255}
    assert a[60, 30].tolist() == [255, 255, 255]          # the light gray shading is gone
    assert a[21, 60].tolist() == [0, 0, 0]                # the line stays
