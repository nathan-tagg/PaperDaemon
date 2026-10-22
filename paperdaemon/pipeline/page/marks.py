r"""Turn a page of strokes into numbered MARKS the model can point at.

The assistant has to know which of the user's written or drawn text should be erased, so it needs a way
of marking strokes visually.

The problem this solves: a page is hundreds of individual strokes, and a
handwritten instruction is maybe forty of them. "Erase the arrow" is not
expressible as a stroke index, and a bounding box tight enough to catch the
arrow also catches whatever it points at. But this model reads renders fast and
accurately -- so give it a picture with numbered boxes drawn round each mark,
let it say `erase_marks([3, 7])`, and the selection problem becomes a looking
problem, which is its strength.

Strokes are grouped by proximity: two strokes join the same mark when their
bounding boxes come within `gap` pixels. On handwriting that collects a word or
a line; on a drawing it collects the figure. It is deliberately not clever --
a stroke-level "understanding" of what a mark MEANS is the thing that does not
work, and it is not needed here, because the model is going to look at it.

Ownership comes from recorded provenance, never from a heuristic: a mark is
`mine` only if every stroke in it is signed, `yours` only if none are, and
`mixed` otherwise. Guessing by stroke width came one step from deleting the
user's own writing.
"""
import os
import sys
from paperdaemon.pipeline import page as P
from paperdaemon.pipeline.page import render as R
from PIL import Image, ImageDraw
import math

PAGE_W, PAGE_H = 1620, 2160      # a Paper Pro page, for a page whose frame cannot be read; x=0 is the CENTER
GAP = 55.0
COARSE_AT = 20000                 # above this many strokes, a page is a traced picture (see marks)


def _bbox(line):
    xs = [p.x for p in line.points]
    ys = [p.y for p in line.points]
    return [min(xs), min(ys), max(xs), max(ys)]


def _near(a, b, gap):
    return not (a[2] + gap < b[0] or b[2] + gap < a[0]
                or a[3] + gap < b[1] or b[3] + gap < a[1])


def _mine_sigs(doc, page_no):
    """Signatures this system has recorded as its own work -> {sig: {what, kind, at}}."""
    try:
        import io as _io
        import json as _json
        snap = P.snapshot(doc, page_no)
        d = P._hist_dir(snap)
        rec = _json.load(_io.open(os.path.join(d, "provenance.json"),
                                  encoding="utf-8"))
        return dict(rec.get("mine", {}))
    except Exception:
        return {}


def _lines(doc, page_no, hide=None):
    """The page's live strokes, minus any the current job has staged for erasing."""
    lines = R.strokes(doc, page_no)
    if hide:
        lines = [l for l in lines if P.skey(l) not in hide]
    return lines


def marks(doc, page_no, gap=GAP, hide=None):
    """Group the page's strokes into marks. Returns a list of dicts."""
    lines = _lines(doc, page_no, hide)
    if not lines:
        return []
    boxes = [_bbox(l) for l in lines]

    parent = list(range(len(lines)))

    def find(i):
        while parent[i] != i:
            parent[i] = parent[parent[i]]
            i = parent[i]
        return i

    def union(i, j):
        a, b = find(i), find(j)
        if a != b:
            parent[a] = b

    # PAIRS BY GRID, not every stroke against every other. All-against-all was fine for a page of
    # handwriting and hopeless for a traced photo: 364,629 strokes is 66 billion comparisons, and a
    # job on such a page never finished grouping its ink. Each stroke is
    # filed in every cell its box, grown by `gap`, touches; two strokes within `gap` of each other
    # always share a cell, so comparing only cell-mates finds exactly the same pairs.
    cell = max(2.0 * gap, 60.0)
    grid = {}
    for i, (x0, y0, x1, y1) in enumerate(boxes):
        for gx in range(int((x0 - gap) // cell), int((x1 + gap) // cell) + 1):
            for gy in range(int((y0 - gap) // cell), int((y1 + gap) // cell) + 1):
                grid.setdefault((gx, gy), []).append(i)
    coarse = len(lines) > COARSE_AT
    for members in grid.values():
        if coarse:
            # a traced PICTURE: its strokes are one thing, and splitting it into thousands of
            # exact marks is worth nothing to anyone -- cell-mates simply join
            for j in members[1:]:
                union(members[0], j)
            continue
        for a_ in range(len(members)):
            i = members[a_]
            for b_ in range(a_ + 1, len(members)):
                j = members[b_]
                if _near(boxes[i], boxes[j], gap):
                    union(i, j)

    groups = {}
    for i in range(len(lines)):
        groups.setdefault(find(i), []).append(i)

    mine = _mine_sigs(doc, page_no)
    out = []
    for idxs in groups.values():
        sigs_all = [P._sig(lines[i]) for i in idxs]
        # A cluster that holds BOTH the user's ink and the model's own is split by owner. Proximity
        # is how a cat drawn at an arrow's tip and the arrow itself became ONE mark, and erasing
        # "the arrow" erased the cat. Provenance is exact; use it.
        parts = [idxs]
        if 0 < sum(1 for g in sigs_all if g in mine) < len(sigs_all):
            parts = [[i for i, g in zip(idxs, sigs_all) if g in mine],
                     [i for i, g in zip(idxs, sigs_all) if g not in mine]]
        for sub in parts:
            bx = [min(boxes[i][0] for i in sub), min(boxes[i][1] for i in sub),
                  max(boxes[i][2] for i in sub), max(boxes[i][3] for i in sub)]
            sigs = [P._sig(lines[i]) for i in sub]
            keys = [P.skey(lines[i]) for i in sub]       # for erasing: signature + position
            n_mine = sum(1 for g in sigs if g in mine)
            owner = ("mine" if n_mine == len(sigs)
                     else "yours" if n_mine == 0 else "mixed")
            m = {"strokes": sub, "bbox": [round(v) for v in bx],
                 "count": len(sub), "owner": owner, "sigs": sigs, "keys": keys}
            # WHAT IT IS, for this system's own ink: the description most of its strokes were
            # recorded with, and when -- so a later job can see which of its old things a new
            # request makes obsolete
            if n_mine:
                whats = {}
                for g in sigs:
                    r = mine.get(g)
                    if isinstance(r, dict) and r.get("what"):
                        w = whats.setdefault(r["what"], [0, 0])
                        w[0] += 1
                        w[1] = max(w[1], int(r.get("at") or 0))
                if whats:
                    what, (_n, at) = max(whats.items(), key=lambda kv: kv[1][0])
                    m["made"] = {"what": what, "at": at}
            out.append(m)
    # READING ORDER: rows top to bottom, each row left to right. Sorted by top edge alone, the words
    # of one handwritten line came out scrambled -- "Highlight the firgt thig sentence page on" for
    # "Highlight the first sentence on this page" (a tall capital starts
    # higher than an "o") -- and the model, erasing that request by its numbers, left a word of it
    # on the page. A mark joins a row when it spans half of the row's first mark's height, or that
    # mark half of its own, and is no more than 3x taller or shorter: a word beside a tall drawing
    # is not in the drawing's row.
    out.sort(key=lambda m: (m["bbox"][1], m["bbox"][0]))
    rows = []
    for m in out:
        y0, y1 = m["bbox"][1], m["bbox"][3]
        h = max(1.0, y1 - y0)
        row = None
        for r in reversed(rows[-8:]):
            ov = min(y1, r["y1"]) - max(y0, r["y0"])
            if max(h, r["h"]) <= 3.0 * min(h, r["h"]) and ov >= 0.5 * min(h, r["h"]):
                row = r
                break
        if row is None:
            rows.append({"y0": y0, "y1": y1, "h": h, "m": [m]})
        else:
            row["m"].append(m)
    out = []
    for i, r in enumerate(rows):
        for m in sorted(r["m"], key=lambda m: m["bbox"][0]):
            m["row"] = i
            out.append(m)
    for n, m in enumerate(out, 1):
        m["id"] = n
    return out


PALETTE = [(214, 39, 40), (31, 119, 180), (44, 160, 44), (255, 127, 14),
           (148, 103, 189), (23, 190, 207), (227, 119, 194), (140, 86, 75),
           (188, 189, 34), (127, 127, 127)]


def overlay(doc, page_no, out_png, gap=GAP, hide=None):
    """The page with every mark in its own color and number. Returns (png, marks).

    COLOR THE STROKES, do not just box them. The first version drew a
    rectangle round each mark, which is unusable the moment marks overlap: on a
    real page the outer frame and the central figure both produce a box the
    size of the sheet, and every other box sits inside them. Coloring the ink
    itself says which strokes belong to which mark even when the extents are
    nested -- and this model reads color reliably (measured 6/6 and 7/7 under
    the q4_0 KV cache), so color is a channel it can actually use.

    Drawn on a FIXED full-page canvas rather than through rm_render, because
    that renderer frames to its content -- its pixels do not map to page
    coordinates by any constant, so boxes placed at page coordinates would
    land in the wrong place.
    """
    ms = marks(doc, page_no, gap, hide)
    lines = _lines(doc, page_no, hide)
    try:                                   # the page's own frame: each tablet writes its own (tablets.TABLETS)
        W, H = (int(round(v)) for v in R.page_frame(doc, page_no))
    except Exception:
        W, H = PAGE_W, PAGE_H
    OX = W / 2.0
    im = Image.new("RGB", (W, H), "white")
    dr = ImageDraw.Draw(im)

    try:                                   # typed text, so nothing is invisible
        from paperdaemon.pipeline.page import typed as TY
        TY.draw(dr, doc, page_no, ox=OX, oy=0)
    except Exception:
        pass

    for m in ms:
        col = PALETTE[(m["id"] - 1) % len(PALETTE)]
        m["color"] = "#%02x%02x%02x" % col
        for i in m["strokes"]:
            pts = [(p.x + OX, p.y) for p in lines[i].points]
            if len(pts) > 1:
                dr.line(pts, fill=col, width=4)

    for m in ms:                           # badges last, so nothing covers them
        col = PALETTE[(m["id"] - 1) % len(PALETTE)]
        x0, y0, x1, y1 = m["bbox"]
        cx = min(max((x0 + x1) / 2.0 + OX, 20), W - 60)
        cy = min(max((y0 + y1) / 2.0, 20), H - 40)
        tag = str(m["id"])
        w = 15 * len(tag) + 12
        dr.rectangle((cx - w / 2, cy - 18, cx + w / 2, cy + 18),
                     fill=col, outline=(255, 255, 255), width=3)
        dr.text((cx - 4 * len(tag), cy - 6), tag, fill=(255, 255, 255))

    im.save(out_png)
    return out_png, ms


# ==================================================================================================
# Find arrows on a page, work out where they POINT, and what they point AT.
#
# A job that erases a label but not its target, or draws an item nowhere near the arrow that said where
# to put it, has the same hole: an arrow was just another cluster of strokes.
# Nothing computed a tip, a direction, or a target, so "do it here" and "remove
# this" had no referent and the model fell back on guessing a position.
#
# THE TIP IS WHERE THE INK PILES UP. An arrowhead is barbs doubling back over the
# shaft, so the pointing end carries far more points per unit length than the
# tail. That is cheap, orientation-free, and does not care whether the head was
# drawn as one stroke, two, or in the same stroke as the shaft -- all three occur
# in one person's handwriting on one page.
#
# What it deliberately does NOT do: classify meaning. Whether an arrow means
# "draw here" or "delete that" is on the page in words, and the model reads words
# well. This only answers "where does it point, and is something there".
# ==================================================================================================

# An arrowhead's barbs sit within roughly this fraction of the mark's diagonal
# from the tip. Generous: hand-drawn heads vary a lot in size.
HEAD_FRAC = 0.18
# The pointing end must carry at least this many times the ink of the tail end.
TIP_RATIO = 1.8
# A mark has to be at least this long to be a deliberate arrow at all.
MIN_SPAN = 120.0
# span / total path length. An arrow goes SOMEWHERE -- even a bent one spends
# most of its ink getting there. Handwriting doubles back constantly. Measured
# on a real page: the arrow scored 0.77, a single letter mistaken for one 0.50,
# blocks of handwriting 0.11-0.27. 0.60 separates them with room either side.
MIN_STRAIGHT = 0.60
# How far past the tip to look for what is being pointed at.
REACH = 900.0
# Half-angle of the cone searched from the tip.
CONE_DEG = 38.0


def _pts(lines, idxs):
    return [(p.x, p.y) for i in idxs for p in lines[i].points]


def _path_len(pts):
    return sum(math.hypot(pts[i + 1][0] - pts[i][0], pts[i + 1][1] - pts[i][1])
               for i in range(len(pts) - 1))


def _ends(lines, idxs):
    """Candidate tip/tail: the two most distant endpoints in the mark."""
    ends = []
    for i in idxs:
        p = lines[i].points
        ends.append((p[0].x, p[0].y))
        ends.append((p[-1].x, p[-1].y))
    # THE TWO FARTHEST POINTS LIE ON THE CONVEX HULL: only its corners are compared, in the ends' own order (the
    # same pair as comparing every two). Every pair of a traced picture's 26,000 ends was 96 s of reading a page.
    corners = _hull(ends)
    cand = [e for e in ends if e in corners]
    best, far = None, -1.0
    for a in cand:
        for b in cand:
            d = math.hypot(a[0] - b[0], a[1] - b[1])
            if d > far:
                far, best = d, (a, b)
    return best, far


def _hull(pts):
    """The corners of the convex hull of `pts` (Andrew's monotone chain) -> a set of points."""
    u = sorted(set(pts))
    if len(u) <= 2:
        return set(u)

    def cross(o, a, b):
        return (a[0] - o[0]) * (b[1] - o[1]) - (a[1] - o[1]) * (b[0] - o[0])
    lo, hi = [], []
    for q in u:
        while len(lo) >= 2 and cross(lo[-2], lo[-1], q) <= 0:
            lo.pop()
        lo.append(q)
    for q in reversed(u):
        while len(hi) >= 2 and cross(hi[-2], hi[-1], q) <= 0:
            hi.pop()
        hi.append(q)
    return set(lo + hi)


def _ink_near(pts, at, r):
    return sum(1 for x, y in pts if math.hypot(x - at[0], y - at[1]) <= r)


def analyze(lines, mark):
    """Is this mark an arrow? If so, where is its tip and which way does it go."""
    idxs = mark["strokes"]
    pts = _pts(lines, idxs)
    if len(pts) < 8:
        return None
    (a, b), span = _ends(lines, idxs)
    if span < MIN_SPAN:
        return None
    path = sum(_path_len([(q.x, q.y) for q in lines[i].points]) for i in idxs)
    straight = span / path if path else 0.0
    if straight < MIN_STRAIGHT:
        return None                      # doubles back too much: handwriting

    r = span * HEAD_FRAC
    ia, ib = _ink_near(pts, a, r), _ink_near(pts, b, r)
    if max(ia, ib) < TIP_RATIO * max(1, min(ia, ib)):
        return None                      # no clear head: a line, not an arrow
    tip, tail = (a, b) if ia > ib else (b, a)

    # Heading from the shaft NEAR the tip, not tip-minus-tail: these are often
    # bent (run right, then turn and drop), and the last leg is what
    # actually aims.
    near = [p for p in pts if r < math.hypot(p[0] - tip[0], p[1] - tip[1]) <= r * 3.0]
    if near:
        cx = sum(p[0] for p in near) / len(near)
        cy = sum(p[1] for p in near) / len(near)
        heading = math.degrees(math.atan2(tip[1] - cy, tip[0] - cx))
    else:
        heading = math.degrees(math.atan2(tip[1] - tail[1], tip[0] - tail[0]))
    return {"id": mark["id"], "tip": [round(tip[0]), round(tip[1])],
            "tail": [round(tail[0]), round(tail[1])],
            "heading_deg": round(heading), "span": round(span),
            "straightness": round(straight, 2),
            "ink_ratio": round(max(ia, ib) / max(1.0, min(ia, ib)), 1)}


def _hits(arrow, mark):
    """Is `mark` inside the cone in front of the arrow, and how far away."""
    tx, ty = arrow["tip"]
    h = math.radians(arrow["heading_deg"])
    x0, y0, x1, y1 = mark["bbox"]
    best = None
    for cx, cy in ((x0, y0), (x1, y0), (x0, y1), (x1, y1),
                   ((x0 + x1) / 2.0, (y0 + y1) / 2.0)):
        dx, dy = cx - tx, cy - ty
        d = math.hypot(dx, dy)
        if d < 1.0 or d > REACH:
            continue
        off = abs((math.degrees(math.atan2(dy, dx)) - arrow["heading_deg"] + 180)
                  % 360 - 180)
        if off <= CONE_DEG and (best is None or d < best):
            best = d
    return best


def arrows(doc, page_no, gap=8.0, hide=None):
    """Every arrow on the page, with what it points at.

    `points_at` is the mark id the arrow indicates, or None when it points at
    empty paper -- which is itself the answer to "do it here": use `tip`.
    """
    from paperdaemon.pipeline.page import render as R
    ms = marks(doc, page_no, gap, hide)
    lines = _lines(doc, page_no, hide)
    found = []
    for m in ms:
        # AN ARROW IS THE USER'S INK. This system's own marks are never analyzed: a traced picture is one
        # mark of 57,886 strokes, and reading it for an arrowhead ran over 18 minutes and stalled
        # the tablet. They stay targets an arrow points at.
        if m.get("owner") == "mine":
            continue
        a = analyze(lines, m)
        if a:
            found.append(a)
    for a in found:
        target, dist = None, None
        for m in ms:
            if m["id"] == a["id"]:
                continue
            d = _hits(a, m)
            if d is not None and (dist is None or d < dist):
                target, dist = m["id"], d
        a["points_at"] = target
        a["distance"] = round(dist) if dist is not None else None
    return found
