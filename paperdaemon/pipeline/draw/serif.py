r"""A serif-like glyph set for rm_text, and the metrics that go with it.

rm_text's own font is geometric and monoline: round letters are near-circles,
stems are bare, and at reading size the shapes converge -- `l`, `I` and `1` are
the same stick, `a` is `o` with a tail, `r` reads as `n`. This set is slightly
more Times-like, so letters are more distinguishable at a glance.

A true Times cannot be had here -- these are single strokes, so there is no
thick and thin, and outlining a real face would draw hollow letters. What CAN be
had are the things that actually make a serif face quick to scan:

  * serifs on stems, so l, i, t, h, n, u stop being interchangeable sticks
  * a DOUBLE-STORY a, which no longer collides with o
  * an e with a real crossbar and an open lower terminal, distinct from c and o
  * proportional widths: i and l narrow, m and w wide
  * 1, I and l given three clearly different shapes

USE IT:

    install()                    # updates rm_text.G in place
    write(d, text, x, y, maxw)   # or lay it out yourself, see below

install() replaces the glyphs AND their advance widths, so rm_text.measure(),
wrap() and text() all follow automatically. It is idempotent.

METRICS. The shapes are only half of it. rm_text's defaults (track .11, leading
1.62) set this font too tight to scan, and its space glyph is far too narrow to
separate words. TRACK/LEAD/GAP below are the tuned values, and layout_words()
places each word itself to get a real gap -- which also means you know exactly
where every word sits, if you want to highlight or underline part of a line.

Same unit grid as rm_text: baseline y=0, cap height y=1.0, y UP, x-height 0.60,
descender -0.28.
"""
import os, sys
from paperdaemon.pipeline.draw import lettering as T
from paperdaemon.pipeline.draw.lettering import _arc, _cat, _dot

# ---- metrics ---------------------------------------------------------------
# Tuned on a page of body text; rm_text's own defaults are .11 / 1.62.
TRACK = 0.13          # letter spacing (0.17 was over-corrected)
LEAD  = 1.78          # line spacing, multiples of cap height
GAP   = 0.62          # word gap, as a fraction of cap height
SIZES = [32, 30, 28, 26, 24, 22]        # preferred sizes, largest first

XH, ASC, DSC = 0.60, 0.98, -0.28
SW = 0.011          # how far a serif oversteps the stem

def _foot(x, y=0.0, w=0.105):
    """A serif foot: the short horizontal tick that stops a stem dead."""
    return [(x - w, y), (x + w, y)]

def _flag(x, top, w=0.085):
    """The angled entry stroke at the top of a lowercase stem."""
    return [(x - w, top - 0.11), (x, top)]

G = {}

# ---- lowercase -------------------------------------------------------------
# The hook used to stop short of the stem and the stem used to end in a curl beside the bowl's
# return, so the letter read as three marks that nearly met. Two strokes now: the hook comes off
# the top of the stem and the stem runs to the baseline and ends in a foot; the bowl leaves the
# stem at the waist and comes back to the same point the stem ends at.
G["a"] = (0.54, [
    _cat(_arc(0.24, 0.47, 0.17, 0.15, 168, 10), [(0.41, 0.50), (0.41, 0.0), (0.51, 0.0)]),
    _cat([(0.41, 0.31)], _arc(0.23, 0.155, 0.18, 0.155, 90, 270), [(0.41, 0.0)]),
])
G["b"] = (0.56, [
    _cat([(0.13, ASC)], [(0.13, 0.0)]), _foot(0.13, ASC, 0.075),
    _cat([(0.13, 0.44)], _arc(0.32, 0.30, 0.19, 0.30, 90, -90), [(0.13, 0.0)]),
])
G["c"] = (0.50, [_arc(0.27, 0.30, 0.22, 0.30, 42, 318)])
G["d"] = (0.56, [
    _cat([(0.43, ASC)], [(0.43, 0.0)]), _foot(0.43, ASC, 0.075),
    _cat([(0.43, 0.44)], _arc(0.24, 0.30, 0.19, 0.30, 90, 270), [(0.43, 0.0)]),
])
G["e"] = (0.52, [_cat([(0.05, 0.30), (0.47, 0.30)],
                      _arc(0.26, 0.30, 0.21, 0.30, 0, 325))])
G["f"] = (0.34, [
    _cat(_arc(0.25, 0.86, 0.12, 0.12, 180, 80), [(0.13, 0.86)], [(0.13, 0.0)]),
    [(0.02, 0.60), (0.30, 0.60)], _foot(0.13),
])
G["g"] = (0.54, [
    _arc(0.25, 0.30, 0.19, 0.30, 0, 360),
    _cat([(0.44, 0.60)], [(0.44, -0.12)], _arc(0.30, -0.12, 0.14, 0.14, 0, -140)),
])
G["h"] = (0.56, [
    [(0.13, ASC), (0.13, 0.0)], _foot(0.13, ASC, 0.075), _foot(0.13), _foot(0.45),
    _cat([(0.13, 0.44)], _arc(0.29, 0.44, 0.16, 0.16, 180, 0), [(0.45, 0.0)]),
])
G["i"] = (0.28, [[(0.14, XH), (0.14, 0.0)], _flag(0.14, XH), _foot(0.14),
                 _dot(0.14, 0.79)])
G["j"] = (0.28, [
    _cat([(0.15, XH)], [(0.15, -0.12)], _arc(0.02, -0.12, 0.13, 0.13, 0, -120)),
    _flag(0.15, XH), _dot(0.15, 0.79),
])
G["k"] = (0.54, [
    [(0.13, ASC), (0.13, 0.0)], _foot(0.13, ASC, 0.075), _foot(0.13),
    [(0.50, XH), (0.15, 0.23)], [(0.27, 0.33), (0.52, 0.0)], _foot(0.50),
])
G["l"] = (0.28, [[(0.14, ASC), (0.14, 0.0)], _flag(0.14, ASC), _foot(0.14)])
G["m"] = (0.86, [
    [(0.12, XH), (0.12, 0.0)], _flag(0.12, XH), _foot(0.12), _foot(0.43), _foot(0.74),
    _cat([(0.12, 0.44)], _arc(0.275, 0.44, 0.155, 0.16, 180, 0), [(0.43, 0.0)]),
    _cat([(0.43, 0.44)], _arc(0.585, 0.44, 0.155, 0.16, 180, 0), [(0.74, 0.0)]),
])
G["n"] = (0.56, [
    [(0.13, XH), (0.13, 0.0)], _flag(0.13, XH), _foot(0.13), _foot(0.45),
    _cat([(0.13, 0.44)], _arc(0.29, 0.44, 0.16, 0.16, 180, 0), [(0.45, 0.0)]),
])
G["o"] = (0.56, [_arc(0.28, 0.30, 0.23, 0.30, 0, 360)])
G["p"] = (0.56, [
    [(0.13, XH), (0.13, DSC)], _flag(0.13, XH), _foot(0.13, DSC, 0.08),
    _cat([(0.13, 0.44)], _arc(0.32, 0.30, 0.19, 0.30, 90, -90), [(0.13, 0.0)]),
])
G["q"] = (0.56, [
    [(0.43, XH), (0.43, DSC)], _foot(0.43, DSC, 0.08),
    _cat([(0.43, 0.44)], _arc(0.24, 0.30, 0.19, 0.30, 90, 270), [(0.43, 0.0)]),
])
G["r"] = (0.40, [
    [(0.13, XH), (0.13, 0.0)], _flag(0.13, XH), _foot(0.13),
    _cat([(0.13, 0.42)], _arc(0.26, 0.42, 0.13, 0.15, 180, 55)),
])
G["s"] = (0.44, [T._ess(0.22, 0.30, 0.155, 0.145)])
G["t"] = (0.34, [
    _cat([(0.14, 0.84)], [(0.14, 0.11)], _arc(0.26, 0.11, 0.12, 0.11, 180, 290)),
    [(0.02, XH), (0.31, XH)],
])
G["u"] = (0.56, [
    _cat([(0.13, XH)], [(0.13, 0.16)], _arc(0.29, 0.16, 0.16, 0.16, 180, 360),
         [(0.45, XH)]),
    _flag(0.13, XH), [(0.45, XH), (0.45, 0.0)], _foot(0.45),
])
G["v"] = (0.52, [[(0.02, XH), (0.26, 0.0), (0.50, XH)],
                 _foot(0.02, XH, 0.075), _foot(0.50, XH, 0.075)])
G["w"] = (0.78, [[(0.02, XH), (0.20, 0.0), (0.39, 0.44), (0.58, 0.0), (0.76, XH)],
                 _foot(0.02, XH, 0.075), _foot(0.76, XH, 0.075)])
G["x"] = (0.52, [[(0.03, XH), (0.49, 0.0)], [(0.49, XH), (0.03, 0.0)],
                 _foot(0.03, XH, 0.07), _foot(0.49, XH, 0.07),
                 _foot(0.03, 0.0, 0.07), _foot(0.49, 0.0, 0.07)])
G["y"] = (0.52, [[(0.02, XH), (0.27, 0.06)],
                 _cat([(0.50, XH)], [(0.22, -0.16)], _arc(0.09, -0.16, 0.13, 0.12, 0, -130)),
                 _foot(0.02, XH, 0.075), _foot(0.50, XH, 0.075)])
G["z"] = (0.48, [[(0.04, XH), (0.44, XH), (0.04, 0.0), (0.44, 0.0)]])

# ---- the three that used to be one stick ----------------------------------
G["1"] = (0.54, [[(0.27, 1.0), (0.27, 0.0)], [(0.10, 0.82), (0.27, 1.0)],
                 _foot(0.27, 0.0, 0.16)])
G["I"] = (0.38, [[(0.19, 1.0), (0.19, 0.0)], _foot(0.19, 1.0, 0.15),
                 _foot(0.19, 0.0, 0.15)])
G["J"] = (0.46, [_cat([(0.36, 1.0)], [(0.36, 0.20)],
                      _arc(0.21, 0.20, 0.15, 0.20, 0, -170)),
                 _foot(0.36, 1.0, 0.13)])

def install():
    """Put these glyphs into rm_text's table, and the metrics into its defaults.

    Widths travel with the glyphs, so measure() and wrap() stay in step with what is drawn.

    THE SPACE is set to GAP - TRACK rather than GAP. Every character in `advance` contributes its
    width plus one track, so a space drawn inside a string yields
        track (after the previous letter) + space + track (after the space)
    while layout_words yields
        track (after the previous letter) + GAP
    and GAP - TRACK is what makes those identical. Without it, handing `text()` a whole string gives
    a different word gap from placing the words yourself, which is exactly the kind of quiet
    inconsistency that shows up later as a line that does not fit.
    """
    T.G.update(G)
    T.G[" "] = (GAP - TRACK, [])
    return sorted(G)



def layout_words(text, size, maxw):
    """Greedy wrap that places every word itself.

    Returns lines of (word, x, src_start, src_end). Placing words rather than
    handing the font a string is what buys a real word gap -- the font's own
    space glyph is far too narrow at this size.
    """
    gap = GAP * size
    lines, cur, x, pos = [], [], 0.0, 0
    for w in text.split():
        i = text.find(w, pos)
        pos = i + len(w)
        adv = T.measure(w, size, TRACK)
        if cur and x + adv > maxw:
            lines.append(cur)
            cur, x = [], 0.0
        cur.append((w, x, i, pos))
        x += adv + gap
    if cur:
        lines.append(cur)
    return lines

def block_height(lines, size):
    return (len(lines) - 1) * size * LEAD + size

def fit(text, box_w, box_h):
    """Largest size whose block fits, with its laid-out lines."""
    for size in SIZES:
        lines = layout_words(text, size, box_w)
        if block_height(lines, size) <= box_h:
            return size, lines
    return None, None


def write(d, text, x, y, maxw, size=None, width=None, **kw):
    """Lay out and draw a block, returning (size, lines).

    Words are placed individually, so `lines` tells you where every word ended
    up -- (word, x offset, source start, source end) -- which is what you need
    if something has to be drawn on top of part of the text.
    """
    if size is None:
        size, lines = fit(text, maxw, kw.pop("maxh", 1e9))
        if size is None:
            raise ValueError("text does not fit %sx%s" % (maxw, kw.get("maxh")))
    else:
        lines = layout_words(text, size, maxw)
    for li, line in enumerate(lines):
        yb = y + li * size * LEAD
        for (w_, x_, _, _) in line:
            T.text(d, w_, x + x_, yb, size=size,
                   width=width or max(7, int(round(size / 3.0))), track=TRACK, **kw)
    return size, lines



# Installed on import. rm_text imports this at its own bottom, so every path that draws
# text -- including the scripts the model writes fresh for each job -- gets these shapes and
# these metrics without having to know they exist.
install()
