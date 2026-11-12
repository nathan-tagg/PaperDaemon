"""A picture taller than Windows' reader takes is read in overlapping bands: every line once, at its own place
(11-12: a long page's render failed whole with "Image dimensions are too large")."""
from PIL import Image, ImageDraw

from paperdaemon.reader import Line, Word
from paperdaemon.reader import render as RR
from paperdaemon.reader.winocr import WindowsOCR


def test_a_tall_picture_is_read_in_bands_each_line_once(monkeypatch):
    monkeypatch.setattr(RR, "MAX_SIDE", 1000)
    ys = list(range(50, 3000, 37))                       # a bar every 37 px, some inside every overlap
    im = Image.new("L", (300, 3000), 255)
    d = ImageDraw.Draw(im)
    for y in ys:
        d.rectangle((10, y, 200, y + 8), fill=0)
    seen = []

    def one(self, crop):
        assert crop.height <= 999
        px, out, y = crop.load(), [], 0
        while y < crop.height:
            if px[20, y] == 0 and (y == 0 or px[20, y - 1] != 0):
                bottom = y
                while bottom < crop.height and px[20, bottom] == 0:
                    bottom += 1
                if y > 0 and bottom < crop.height:          # a bar cut by the band's edge is not read
                    out.append(Line([Word("bar", (10, y, 200, bottom))]))
                y = bottom
            y += 1
        seen.append(crop.height)
        return out
    monkeypatch.setattr(WindowsOCR, "_read_one", one)
    lines = WindowsOCR().read_image(im)
    tops = sorted(round(ln.words[0].box[1]) for ln in lines)
    assert tops == ys and len(seen) > 1
