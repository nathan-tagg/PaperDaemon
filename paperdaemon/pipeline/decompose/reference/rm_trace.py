"""Trace a photograph into pen strokes — actual contours, not hand-drawn curves.

Hand-drawn art built from hand-placed bezier/Catmull-Rom control points comes out
smooth and boneless ("rubbery"). No amount of care fixes that, because the cause is
structural: the geometry has to come from the SOURCE IMAGE instead of from
hand-placed points, so that famous art can be recreated in lines by literally
tracing it.

So: marching squares on the luminance field. For each of several brightness
levels the image is thresholded and the boundary between light and dark is
traced, giving nested iso-contours — the same idea as a topographic map. The
result reads as a real line drawing because every line is a genuine edge in the
picture, and the density of lines is the tonal information.

Pure PIL, no numpy/OpenCV, so everything is plain Python over a
downsampled grid (~200px wide ⇒ ~50k cells, well under a second).
"""
import math
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

# Marching-squares segment table. Corner bits: 1=TL 2=TR 4=BR 8=BL, set when the
# corner is BELOW the threshold (i.e. darker). Values are pairs of edges, where
# edges are T,R,B,L midpoints. Saddles (5, 10) are split consistently so the
# contours never cross.
_T, _R, _B, _L = "T", "R", "B", "L"
_CASES = {
    1:  [(_L, _T)], 2:  [(_T, _R)], 3:  [(_L, _R)],
    4:  [(_R, _B)], 6:  [(_T, _B)], 7:  [(_L, _B)],
    8:  [(_B, _L)], 9:  [(_B, _T)], 11: [(_B, _R)],
    12: [(_R, _L)], 13: [(_R, _T)], 14: [(_T, _L)],
    5:  [(_L, _T), (_R, _B)], 10: [(_T, _R), (_B, _L)],
}


def _edge_point(edge, x, y):
    """Midpoint of a cell edge, in grid coordinates."""
    if edge == _T:
        return (x + 0.5, float(y))
    if edge == _B:
        return (x + 0.5, y + 1.0)
    if edge == _L:
        return (float(x), y + 0.5)
    return (x + 1.0, y + 0.5)


def iso_segments(px, w, h, level):
    """All marching-squares segments for one luminance level."""
    segs = []
    for y in range(h - 1):
        for x in range(w - 1):
            code = 0
            if px[x, y] < level:
                code |= 1
            if px[x + 1, y] < level:
                code |= 2
            if px[x + 1, y + 1] < level:
                code |= 4
            if px[x, y + 1] < level:
                code |= 8
            if code == 0 or code == 15:
                continue
            for a, b in _CASES.get(code, ()):
                segs.append((_edge_point(a, x, y), _edge_point(b, x, y)))
    return segs


def join(segs, tol=0.26):
    """Chain loose segments into polylines.

    Marching squares emits segments in scan order with no connectivity, so they
    have to be stitched. Endpoints are exact midpoints, so a coarse hash key is
    both safe and fast.
    """
    def key(p):
        return (round(p[0] * 2), round(p[1] * 2))

    ends = {}
    for s in segs:
        ends.setdefault(key(s[0]), []).append(s)
        ends.setdefault(key(s[1]), []).append(s)
    used = set()
    out = []
    for i, s in enumerate(segs):
        if id(s) in used:
            continue
        used.add(id(s))
        chain = [s[0], s[1]]
        # walk forward, then backward
        for direction in (0, 1):
            while True:
                tip = chain[-1] if direction == 0 else chain[0]
                nxt = None
                for cand in ends.get(key(tip), ()):
                    if id(cand) in used:
                        continue
                    if abs(cand[0][0] - tip[0]) < tol and abs(cand[0][1] - tip[1]) < tol:
                        nxt, other = cand, cand[1]
                    elif abs(cand[1][0] - tip[0]) < tol and abs(cand[1][1] - tip[1]) < tol:
                        nxt, other = cand, cand[0]
                    else:
                        continue
                    break
                if nxt is None:
                    break
                used.add(id(nxt))
                if direction == 0:
                    chain.append(other)
                else:
                    chain.insert(0, other)
        out.append(chain)
    return out


def simplify(pts, eps):
    """Douglas-Peucker. Keeps corners, throws away the samples between them."""
    if len(pts) < 3:
        return pts
    x0, y0 = pts[0]
    x1, y1 = pts[-1]
    dx, dy = x1 - x0, y1 - y0
    n = math.hypot(dx, dy)
    worst, wi = -1.0, 0
    for i in range(1, len(pts) - 1):
        x, y = pts[i]
        d = (abs(dy * x - dx * y + x1 * y0 - y1 * x0) / n) if n > 1e-9 \
            else math.hypot(x - x0, y - y0)
        if d > worst:
            worst, wi = d, i
    if worst <= eps:
        return [pts[0], pts[-1]]
    return simplify(pts[:wi + 1], eps)[:-1] + simplify(pts[wi:], eps)


def trace(path, levels=(70, 105, 140, 175), width=200, blur=1.2,
          eps=0.55, min_pts=4, min_len=3.0, autocontrast=True, crop=0.0):
    """Image file -> list of polylines in GRID coordinates, plus the grid size.

    `crop` trims that fraction off every side FIRST. A photograph of a painting
    carries its own border, and the very first contour traced is otherwise the
    rectangle of the photo edge -- a hard frame around the drawing that is not
    in the artwork at all.

    `min_len` is the speckle filter. Background texture generates a swarm of
    tiny closed contours that add noise and stroke count without adding
    legibility; raising this is the single most effective clean-up.
    """
    from PIL import Image, ImageFilter, ImageOps
    im = Image.open(path).convert("L")
    if crop:
        cw, ch = int(im.width * crop), int(im.height * crop)
        im = im.crop((cw, ch, im.width - cw, im.height - ch))
    h = max(1, int(round(width * im.height / im.width)))
    im = im.resize((width, h), Image.LANCZOS)
    if autocontrast:
        im = ImageOps.autocontrast(im, cutoff=1)
    if blur:
        im = im.filter(ImageFilter.GaussianBlur(blur))
    px = im.load()
    polys = []
    for lv in levels:
        for chain in join(iso_segments(px, im.width, im.height, lv)):
            if len(chain) < min_pts:
                continue
            length = sum(math.hypot(b[0] - a[0], b[1] - a[1])
                         for a, b in zip(chain, chain[1:]))
            if length < min_len:
                continue
            s = simplify(chain, eps)
            if len(s) >= 2:
                polys.append(s)
    return polys, (im.width, im.height)


def place(polys, grid, box):
    """Fit grid-space polylines into a page-space box, preserving aspect."""
    gw, gh = grid
    x0, y0, x1, y1 = box
    scale = min((x1 - x0) / gw, (y1 - y0) / gh)
    ox = x0 + ((x1 - x0) - gw * scale) / 2.0
    oy = y0 + ((y1 - y0) - gh * scale) / 2.0
    return [[(ox + x * scale, oy + y * scale) for x, y in p] for p in polys]


if __name__ == "__main__":
    src = sys.argv[1]
    polys, grid = trace(src)
    n = sum(len(p) for p in polys)
    print("%d polylines, %d points, grid %dx%d" % (len(polys), n, grid[0], grid[1]))
