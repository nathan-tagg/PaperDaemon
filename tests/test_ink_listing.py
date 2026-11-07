"""A word of handwriting alone on its line is listed as a line of handwriting, like any other line: listed as a mark
with its stroke count ("mark:1 yours, 9 strokes, ... reads 'eggs'"), a grocery list's "eggs" was answered as
"Eggs (9)". A mark that reads as no word stays a mark."""
import uuid

from paperdaemon.pipeline import draw as A
from paperdaemon.pipeline import host as H
from paperdaemon.pipeline.host import intake as I
from paperdaemon.pipeline.host import job as J
from paperdaemon.pipeline.page import marks as MK
from paperdaemon.pipeline.page import typed as TY

DOC = str(uuid.uuid5(uuid.NAMESPACE_URL, "https://paperdaemon.invalid/ink-listing"))


def _mark(i, x0, y0, x1, y1, row, count=9):
    return {"id": i, "bbox": (x0, y0, x1, y1), "row": row, "owner": "yours", "count": count, "keys": ["k%d" % i]}


def test_a_word_alone_on_its_line_is_a_line_and_a_mark_that_reads_as_no_word_stays_a_mark(monkeypatch):
    ms = [_mark(1, -500, 200, -380, 260, 0), _mark(2, -500, 300, -420, 360, 1), _mark(3, -400, 300, -250, 360, 1),
          _mark(4, -100, 500, -60, 560, 3, count=1)]
    words = {1: "eggs", 2: "rye", 3: "bread", 4: "/"}
    monkeypatch.setattr(MK, "marks", lambda doc, page, gap, hide=None: ms)
    monkeypatch.setattr(H, "_mark_words", lambda doc, page, ms_: words)
    monkeypatch.setattr(TY, "paragraphs", lambda doc, page: (None, []))
    J.begin(doc=DOC, page=1, frame=(1620.0, 2160.0), draw=A.Drawing(), ops=[])
    listing = [l.strip() for l in I.job_context(DOC, 1, "Groceries").splitlines() if l.strip()[:5] in ("line:", "mark:")]
    assert listing[0].startswith("line:1  yours, one line of 1 word,") and "reads 'eggs'" in listing[0]
    assert "stroke" not in listing[0]
    assert listing[1].startswith("line:2  yours, one line of 2 words,") and "rye bread" in listing[1]
    assert listing[2].startswith("mark:4  yours, 1 stroke")          # a stroke that reads as no word
