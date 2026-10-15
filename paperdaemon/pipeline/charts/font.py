r"""Build a real TrueType font out of the tablet's single-stroke lettering.

`rm_text.G` is a monoline font: each glyph is a set of open polylines on a unit grid, meant to be
drawn by a pen of some width. A renderer cannot use that -- Vega-Lite draws its own axis and
legend text, so "use our font everywhere" means there has to be a font FILE.

Stroking an open polyline into a filled outline normally wants an offsetting library. It does not
here, because TrueType fills by NON-ZERO winding: a pile of overlapping contours all wound the
same way fills as their union. So every segment becomes a rectangle and every vertex a circle,
all wound clockwise, and the union is the stroked letter with round caps and joins for free.

    python rm_font.py            # writes RemarkableMono-Regular.ttf to the generated-fonts folder

`rm_chart` registers that directory with vl-convert at import and uses the family by name.
"""
from __future__ import annotations
import math
import os
from paperdaemon import paths

FAMILY = "Remarkable Mono"
STYLE = "Regular"
OUT_DIR = paths.generated_fonts_dir()      # RM_FONTS overrides
UPM = 1000                 # units per em
CAP = 700                  # cap height in font units -- rm_text's y=1
BASE = 0                   # baseline
WEIGHT = 78                # pen width in font units: at the fineliner's 46/700 chart text was too fine and too
                           # light to read on the tablet
SIDE = 62                  # side bearing: the gap between letters as it was at the fine pen (46 + the half-width
                           # the heavier pen added), so the heavier letters do not run together


def _seg_quad(p0, p1, r):
    """A segment as a clockwise rectangle of half-width r."""
    (x0, y0), (x1, y1) = p0, p1
    dx, dy = x1 - x0, y1 - y0
    ln = math.hypot(dx, dy)
    if ln < 1e-9:
        return None
    nx, ny = -dy / ln * r, dx / ln * r
    return [(x0 + nx, y0 + ny), (x1 + nx, y1 + ny), (x1 - nx, y1 - ny), (x0 - nx, y0 - ny)]


def _circle(c, r, n=12):
    """A clockwise circle, for the caps and joins."""
    cx, cy = c
    return [(cx + r * math.cos(-2 * math.pi * i / n),
             cy + r * math.sin(-2 * math.pi * i / n)) for i in range(n)]


def _area(poly):
    a = 0.0
    for i in range(len(poly)):
        x0, y0 = poly[i]
        x1, y1 = poly[(i + 1) % len(poly)]
        a += x0 * y1 - x1 * y0
    return a / 2.0


def _cw(poly):
    return poly if _area(poly) < 0 else list(reversed(poly))


def glyph_contours(strokes, scale, r, dx=0.0):
    """Every polyline of one glyph -> a list of closed, identically wound contours.

    `dx` shifts the outline into its left side bearing. It has to be a real shift, not just a
    number in hmtx: TrueType takes the bearing from the glyph's own xMin, so setting lsb without
    moving the outline leaves the two disagreeing and the spacing comes out wrong.
    """
    out = []
    for poly in strokes:
        pts = [(x * scale + dx, y * scale) for x, y in poly]
        if len(pts) == 1:
            out.append(_cw(_circle(pts[0], r)))
            continue
        for a, b in zip(pts, pts[1:]):
            q = _seg_quad(a, b, r)
            if q:
                out.append(_cw(q))
        for p in pts:
            out.append(_cw(_circle(p, r)))
    return out


def build(path=None):
    from paperdaemon.pipeline.draw import lettering as rm_text
    from fontTools.fontBuilder import FontBuilder
    from fontTools.pens.ttGlyphPen import TTGlyphPen

    G = rm_text.G
    scale = float(CAP)
    r = WEIGHT / 2.0

    # a name for every character we carry, plus the ones a chart cannot do without
    import unicodedata
    order = [".notdef"]
    cmap = {}
    for ch in sorted(G):
        try:
            nm = "uni%04X" % ord(ch)
        except TypeError:
            continue
        if nm in order:
            continue
        order.append(nm)
        cmap[ord(ch)] = nm

    fb = FontBuilder(UPM, isTTF=True)
    fb.setupGlyphOrder(order)
    fb.setupCharacterMap(cmap)

    glyphs, metrics = {}, {}
    pen = TTGlyphPen(None)
    glyphs[".notdef"] = pen.glyph()
    metrics[".notdef"] = (int(0.5 * CAP), 0)

    for ch in sorted(G):
        adv, strokes = G[ch]
        nm = "uni%04X" % ord(ch)
        pen = TTGlyphPen(None)
        for contour in glyph_contours(strokes, scale, r, SIDE):
            pen.moveTo(contour[0])
            for p in contour[1:]:
                pen.lineTo(p)
            pen.closePath()
        glyphs[nm] = pen.glyph()
        metrics[nm] = (int(round(adv * scale)) + 2 * SIDE, SIDE - int(r))

    fb.setupGlyf(glyphs)
    fb.setupHorizontalMetrics(metrics)
    fb.setupHorizontalHeader(ascent=int(CAP * 1.05), descent=-int(CAP * 0.30))
    fb.setupNameTable({
        "familyName": FAMILY, "styleName": STYLE,
        "psName": FAMILY.replace(" ", "") + "-" + STYLE,
        "fullName": FAMILY + " " + STYLE,
        "version": "1.0",
        "copyright": "Generated from rm_text.G, the reMarkable single-stroke lettering.",
    })
    fb.setupOS2(sTypoAscender=int(CAP * 1.05), sTypoDescender=-int(CAP * 0.30),
                usWinAscent=int(CAP * 1.15), usWinDescent=int(CAP * 0.35),
                sCapHeight=CAP, sxHeight=int(CAP * rm_text.XH))
    fb.setupPost()
    if path is None:
        if not os.path.isdir(OUT_DIR):
            os.makedirs(OUT_DIR)
        path = os.path.join(OUT_DIR, "RemarkableMono-Regular.ttf")
    os.makedirs(os.path.dirname(path), exist_ok=True)
    fb.save(path)
    return path, len(cmap)
