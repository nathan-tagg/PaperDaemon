"""The text layer of a PDF page for the page editor (pipeline/page/pdf.py page_text, GET .../page/{page}/text): every
character with its box in page units, on the frame _paste_source draws the page in. A small PDF is made here and staged in
the test's own temporary mirror; the user's library is never read."""
import os
import uuid

import numpy as np
import pytest
from fastapi.testclient import TestClient

from paperdaemon import server
from paperdaemon.pipeline.page import pdf as pagepdf, render as R

LINES = [("Hello world", 72, 700), ("Second line here", 72, 650)]


def make_pdf(path, rotate=0, w=300, h=400, lines=None):
    """One page, Helvetica 24 pt, one text line per entry of (text, x, y); /Rotate if asked."""
    stream = "".join("BT /F1 24 Tf %d %d Td (%s) Tj ET\n" % (x, y - (792 - h), t)
                     for t, x, y in (lines if lines is not None else LINES)).encode("latin-1")
    objs = [b"<< /Type /Catalog /Pages 2 0 R >>",
            b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
            ("<< /Type /Page /Parent 2 0 R /MediaBox [0 0 %d %d] /Rotate %d /Contents 4 0 R "
             "/Resources << /Font << /F1 5 0 R >> >> >>" % (w, h, rotate)).encode(),
            b"<< /Length %d >>\nstream\n" % len(stream) + stream + b"endstream",
            b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>"]
    out, offs = bytearray(b"%PDF-1.4\n"), []
    for i, o in enumerate(objs, 1):
        offs.append(len(out))
        out += b"%d 0 obj\n" % i + o + b"\nendobj\n"
    x = len(out)
    out += b"xref\n0 %d\n0000000000 65535 f \n" % (len(objs) + 1)
    for o in offs:
        out += b"%010d 00000 n \n" % o
    out += b"trailer\n<< /Size %d /Root 1 0 R >>\nstartxref\n%d\n%%%%EOF\n" % (len(objs) + 1, x)
    with open(path, "wb") as f:
        f.write(out)


def staged(tmp_path, **kw):
    src = str(tmp_path / ("%s.pdf" % uuid.uuid4()))
    make_pdf(src, **kw)
    doc, _ = pagepdf.stage("Text test", src)
    return doc


def client():
    c = TestClient(server.app)
    c.headers["Authorization"] = "Bearer " + server.pairing_token()
    return c


def drawn_box(doc, rows):
    """The ink of the page as _paste_source draws it, in page units: the bounding box of the dark pixels in the
    given pixel rows (x from the page's left, so minus half the width)."""
    im = np.asarray(R.source_image(doc, 1).convert("L"))
    pw = R.page_frame(doc, 1)[0]
    r0, r1 = rows
    ys, xs = np.nonzero(im[r0:r1] < 128)
    return (xs.min() - pw / 2.0, ys.min() + r0, xs.max() + 1 - pw / 2.0, ys.max() + 1 + r0)


def test_the_text_boxes_and_lines_of_a_pdf_page(tmp_path):
    doc = staged(tmp_path)
    got = pagepdf.page_text(doc, 1)
    text, boxes = got["text"], got["boxes"]
    assert len(text) == len(boxes)
    assert "Hello world" in text and "Second line here" in text
    pw, ph = R.page_frame(doc, 1)
    for x0, y0, x1, y1 in boxes:
        assert x0 < x1 and y0 < y1
        assert -pw / 2 <= x0 and x1 <= pw / 2 and 0 <= y0 and y1 <= ph
    shown = [text[a:b].strip() for a, b in got["lines"]]
    assert shown == ["Hello world", "Second line here"]
    a = text.index("Hello")
    # the word's boxes sit where the word is in the page: x from 72 pt, baseline 700 of 792 on a 400 pt page -> 92 pt up
    first = boxes[a]
    assert abs(first[0] - (72 * R.PDF_SCALE - pw / 2)) < 2.0
    assert boxes[a][2] <= boxes[a + 1][0] + 0.5 and boxes[a + 4][2] < boxes[text.index("world")][0]
    top = min(b[1] for b in boxes[a:a + 5])
    assert top < min(b[1] for b in boxes[text.index("Second"):text.index("Second") + 6])   # the first line is higher


@pytest.mark.parametrize("rotate", [0, 90, 180, 270])
def test_the_boxes_land_on_the_characters_the_page_draws(tmp_path, rotate):
    doc = staged(tmp_path, rotate=rotate, lines=[("HHHH", 72, 700)])
    got = pagepdf.page_text(doc, 1)
    word = [b for b, c in zip(got["boxes"], got["text"]) if c == "H"]
    x0, y0, x1, y1 = (min(b[0] for b in word), min(b[1] for b in word), max(b[2] for b in word), max(b[3] for b in word))
    ink = drawn_box(doc, (0, int(R.page_frame(doc, 1)[1])))
    # the loose char boxes hold the glyphs with their side bearings and line gap: the ink lies inside, close to them
    assert x0 - 1 <= ink[0] and ink[2] <= x1 + 1 and y0 - 1 <= ink[1] and ink[3] <= y1 + 1
    assert (x1 - x0) - (ink[2] - ink[0]) < 0.35 * (x1 - x0) + 12 and (y1 - y0) - (ink[3] - ink[1]) < 1.6 * (ink[3] - ink[1])


def test_a_page_without_text_or_pdf_has_none(tmp_path):
    doc = staged(tmp_path, lines=[])
    assert pagepdf.page_text(doc, 1) is None
    assert pagepdf.page_text(str(uuid.uuid4()), 1) is None


def test_the_endpoint(tmp_path):
    doc = staged(tmp_path)
    c = client()
    r = c.get("/api/v1/library/%s/page/1/text" % doc)
    assert r.status_code == 200
    j = r.json()
    assert set(j) == {"text", "boxes", "lines"} and len(j["text"]) == len(j["boxes"])
    assert j == pagepdf.page_text(doc, 1)
    assert c.get("/api/v1/library/%s/page/1/text" % uuid.uuid4()).status_code == 404
    assert c.get("/api/v1/library/%s/page/9/text" % doc).status_code == 404
    assert c.get("/api/v1/library/nope/page/1/text").status_code == 400
