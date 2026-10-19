r"""Lay books of the mirror out with PaperDaemon's engine and compare them with the tablet's own PDFs, glyph by glyph.

    uv run python tools/check_books.py DOC [DOC ...]       (document ids of books that have the tablet's PDF)

For each book: the page counts, and per page how many glyphs PaperDaemon put somewhere the tablet did not (bold glyphs
counted apart: the weight-700 kerning is a known difference, openspec add-epub-reading D2). Both PDFs are Qt's: a page
is drawn in 1404 x 1872 units scaled by 72/227, and each glyph is placed with a Td after the text matrix, which this
reads back. Run it when the tablet's software (and with it its Qt) changes.
"""
import json
import os
import re
import sys
import zlib

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


class QtPdf:
    """The glyphs of a PDF written by Qt's PDF engine: (font, size, x, y) per glyph, in page units, y down."""

    def __init__(self, path):
        raw = open(path, "rb").read()
        self.objs = {int(n): b for n, b in re.findall(rb"(\d+) 0 obj(.*?)endobj", raw, re.S)}
        cat = next(b for b in self.objs.values() if re.search(rb"/Type\s*/Catalog", b))
        self.pages = []
        self._walk(int(re.search(rb"/Pages\s+(\d+) 0 R", cat).group(1)))

    def _walk(self, n):
        b = self.objs[n]
        if re.search(rb"/Type\s*/Pages", b):
            for k in re.findall(rb"(\d+) 0 R", re.search(rb"/Kids\s*\[(.*?)\]", b, re.S).group(1)):
                self._walk(int(k))
        else:
            self.pages.append(n)

    def _stream(self, n):
        b = self.objs[n]
        s = b.split(b"stream", 1)[1].lstrip(b"\r\n").rsplit(b"endstream", 1)[0]
        return zlib.decompress(s) if b"FlateDecode" in b else s

    def glyphs(self, i):
        b = self.objs[self.pages[i]]
        res = self.objs[int(re.search(rb"/Resources\s+(\d+) 0 R", b).group(1))]
        fonts = {}
        for name, ref in re.findall(rb"/(F\d+)\s+(\d+) 0 R", res):
            m = re.search(rb"/BaseFont\s*/([^\s/>]+)", self.objs[int(ref)])
            fonts[name.decode()] = m.group(1).decode().split("+")[-1] if m else "?"
        st = self._stream(int(re.search(rb"/Contents\s+(\d+) 0 R", b).group(1))).decode("latin1")
        out, stack, cur, args, x, y = [], [(0.0, 0.0)], ("?", 0.0), [], 0.0, 0.0
        for t in re.findall(r"<[0-9A-Fa-f]*>|[-\d.]+|/\w+|[A-Za-z*']+", st):
            if t[0] in "-.0123456789</":
                args.append(t)
                continue
            if t == "q":
                stack.append(stack[-1])
            elif t == "Q":
                if len(stack) > 1:
                    stack.pop()
            elif t == "cm" and len(args) >= 6:
                a = [float(v) for v in args[-6:]]
                if a[0] == 1 and a[3] == 1:
                    stack[-1] = (stack[-1][0] + a[4], stack[-1][1] + a[5])
            elif t == "Tf":
                cur = (fonts.get(args[-2][1:], args[-2]), float(args[-1]))
            elif t == "BT":
                x = y = 0.0
            elif t == "Td":
                x += float(args[-2])
                y += float(args[-1])
            elif t == "Tj":
                out.append((cur[0], cur[1], round(x + stack[-1][0], 3), round(-y + stack[-1][1], 2)))
            args = []
        return out


def compare(ours, tablet):
    a, b = QtPdf(ours), QtPdf(tablet)
    rows = []
    for i in range(min(len(a.pages), len(b.pages))):
        A, B = a.glyphs(i), set(b.glyphs(i))
        off = [g for g in A if g not in B]
        rows.append((len(A), sum(1 for g in off if "Bold" not in g[0]), sum(1 for g in off if "Bold" in g[0])))
    return len(a.pages), len(b.pages), rows


def main(docs):
    from paperdaemon import paths
    from paperdaemon.remarkable import books
    mirror = os.environ.get("RM_MIRROR") or paths.mirror_dir()
    for doc in docs:
        with open(os.path.join(mirror, doc + ".content"), encoding="utf-8") as f:
            content = json.load(f)
        with open(os.path.join(mirror, doc + ".metadata"), encoding="utf-8") as f:
            name = json.load(f).get("visibleName", doc)
        ours, _ = books.lay_out(os.path.join(mirror, doc + ".epub"), books.settings_of(content))
        na, nb, rows = compare(ours, os.path.join(mirror, doc + ".pdf"))
        exact = sum(1 for _, o, _b in rows if o == 0)
        print("%-34s pages %d/%d | pages exact %d/%d | glyphs off %d (+%d bold)" % (
            name[:34], na, nb, exact, len(rows), sum(r[1] for r in rows), sum(r[2] for r in rows)))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
