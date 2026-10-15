"""The reader's plumbing. Accuracy on real handwriting is measured on the handwriting test set and on
real pages, not here."""
import os
import sys

import pytest
from PIL import Image, ImageDraw, ImageFont

from paperdaemon import reader
from paperdaemon.reader import render


def test_boxes_map_back_to_the_page():
    stroke = {"points": [(100, 200), (300, 200), (300, 260), (100, 260), (100, 200)], "width": 2}
    img, tf = render.ink_image([stroke])
    ink = img.point(lambda v: 255 if v < 128 else 0).getbbox()        # the drawn ink, in image pixels
    x0, y0, x1, y1 = tf.to_page(ink)
    half = render.STROKE_PX / 2 / tf.scale + 1
    assert abs(x0 - 100) <= half and abs(y0 - 200) <= half and abs(x1 - 300) <= half and abs(y1 - 260) <= half


def test_no_ink_reads_as_nothing():
    class Never(reader.Engine):
        id, name = "never", "Never"

        def read_image(self, image):
            raise AssertionError("an empty page was sent to the engine")
    assert reader.read([], engine=Never()) == []


def test_lines_come_back_in_reading_order_in_page_coordinates():
    class Fake(reader.Engine):
        id, name = "fake", "Fake"

        def read_image(self, image):
            return [reader.Line([reader.Word("second", (10, 200, 90, 240))]),
                    reader.Line([reader.Word("b", (120, 10, 160, 50)), reader.Word("a", (10, 10, 90, 50))])]
    lines = reader.read([{"points": [(0, 0), (500, 400)], "width": 2}], engine=Fake())
    assert [ln.text for ln in lines] == ["a b", "second"]
    assert lines[0].words[0].box[0] == pytest.approx(0 - render.PAD + 10 / render.SCALE)


@pytest.mark.skipif(sys.platform != "win32", reason="Windows OCR runs only on Windows")
def test_windows_ocr_reads_in_process():
    engine = reader.pick("windows-ocr")
    assert engine is not None and engine.id == "windows-ocr", engine and engine.available()
    font = ImageFont.truetype(os.path.join(os.environ["WINDIR"], "Fonts", "Inkfree.ttf"), 64)
    im = Image.new("L", (1400, 240), 255)
    ImageDraw.Draw(im).text((40, 60), "meeting notes for the garden", fill=0, font=font)
    lines = engine.read_image(im)
    words = [w for ln in lines for w in ln.words]
    # plumbing only: five words found, each with a real box, left to right. What the letters come back
    # as is accuracy, measured on the handwriting test set (this script font reads poorly).
    assert len(words) == 5 and all(w.text for w in words)
    assert all(w.box[2] > w.box[0] and w.box[3] > w.box[1] for w in words)
    assert [w.box[0] for w in words] == sorted(w.box[0] for w in words)


def test_where_no_reader_runs_it_says_so(monkeypatch):
    import pytest
    from paperdaemon import reader
    monkeypatch.setattr(reader.sys, "platform", "linux")
    e = reader.engines()[0]
    ok, why = e.available()
    assert not ok and "runs only on win32" in why
    assert reader.pick() is None
    with pytest.raises(LookupError, match="no handwriting reader"):
        reader.read([{"points": [(0, 0), (10, 10)], "width": 2}])
