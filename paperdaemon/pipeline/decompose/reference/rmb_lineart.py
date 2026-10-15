r"""The parts of rm_lineart the decomposer uses, vectorized.

Same results, different data type: the XDoG response is a (h, w) float64 array instead
of a dict keyed by (x, y), and an edge/skeleton mask is a (h, w) boolean array instead
of a set of points. Nothing else changes -- `paths`, `stitch`, `chaikin` and `simplify`
are the reference routines, and the walk order (`sorted(fg)`, i.e. x then y) and the
neighbor order (_N8) are preserved exactly, because they decide which fragments become
which polylines.

The arithmetic is identical too: (g1 - tau*g2)/255.0 per pixel is the same IEEE
expression whether it runs in a Python loop or a numpy one, and the percentile cut is
the same element of the same sorted list.
"""
import math

import numpy as np
from PIL import Image, ImageFilter, ImageOps

from paperdaemon.pipeline.decompose.reference.rmb_npops import simplify, zhang_suen

_N8 = ((-1, -1), (0, -1), (1, -1), (1, 0), (1, 1), (0, 1), (-1, 1), (-1, 0))


def xdog(path, width=260, sigma=1.0, k=1.6, tau=0.985, crop=0.0, autocontrast=True):
    """Extended difference-of-Gaussians -> (response array (h, w), (width, h))."""
    im = Image.open(path).convert("L")
    if crop:
        cw, ch = int(im.width * crop), int(im.height * crop)
        im = im.crop((cw, ch, im.width - cw, im.height - ch))
    h = max(1, int(round(width * im.height / im.width)))
    im = im.resize((width, h), Image.LANCZOS)
    if autocontrast:
        im = ImageOps.autocontrast(im, cutoff=1)
    g1 = np.asarray(im.filter(ImageFilter.GaussianBlur(sigma)), np.float64)
    g2 = np.asarray(im.filter(ImageFilter.GaussianBlur(sigma * k)), np.float64)
    return (g1 - tau * g2) / 255.0, (width, h)


def mask(resp, size, ink=0.06):
    """The darkest `ink` fraction of the response -> boolean array."""
    flat = np.sort(resp, axis=None)
    cut = flat[max(0, min(flat.size - 1, int(flat.size * ink)))]
    return resp <= cut


def thin(fg):
    """Zhang-Suen thinning of a boolean array (padded so the border has no neighbors)."""
    f = np.zeros((fg.shape[0] + 2, fg.shape[1] + 2), np.bool_)
    f[1:-1, 1:-1] = fg
    return zhang_suen(f)[1:-1, 1:-1]


def _degrees(fg):
    """8-neighbor count per pixel, as one stencil."""
    p = np.zeros((fg.shape[0] + 2, fg.shape[1] + 2), np.int8)
    p[1:-1, 1:-1] = fg
    d = np.zeros_like(p)
    for dy in (-1, 0, 1):
        for dx in (-1, 0, 1):
            if dx or dy:
                d[1:-1, 1:-1] += p[1 + dy:p.shape[0] - 1 + dy, 1 + dx:p.shape[1] - 1 + dx]
    return d[1:-1, 1:-1]


def paths(fg, straightness=True):
    """Walk a skeleton into polylines, running straight through junctions.

    `fg` is a boolean array. Points are visited in `sorted(set_of_(x, y))` order --
    x then y -- and neighbors in _N8 order, exactly as the set-based original."""
    deg_a = _degrees(fg)
    pts = set()
    xs, ys = np.nonzero(fg.T)                    # fg.T scans x-major: sorted((x, y))
    order = [(int(x), int(y)) for x, y in zip(xs, ys)]
    pts.update(order)
    if not pts:
        return []
    deg = {p: int(deg_a[p[1], p[0]]) for p in order}
    used_edge = set()

    def nbrs(p):
        x, y = p
        return [q for q in ((x - 1, y - 1), (x, y - 1), (x + 1, y - 1), (x + 1, y),
                            (x + 1, y + 1), (x, y + 1), (x - 1, y + 1), (x - 1, y)) if q in pts]

    def edge(a, b):
        return (a, b) if a < b else (b, a)

    def walk(start, first):
        line = [start, first]
        used_edge.add(edge(start, first))
        cur, prev = first, start
        while True:
            cand = [q for q in nbrs(cur) if q != prev and edge(cur, q) not in used_edge]
            if not cand:
                break
            if len(cand) > 1 and straightness:
                vx, vy = cur[0] - prev[0], cur[1] - prev[1]
                cand.sort(key=lambda q: -((q[0] - cur[0]) * vx + (q[1] - cur[1]) * vy))
            nxt = cand[0]
            used_edge.add(edge(cur, nxt))
            line.append(nxt)
            prev, cur = cur, nxt
            if deg.get(cur, 0) == 1:
                break
        return line

    out = []
    for p in order:                              # endpoints first: open curves
        if deg.get(p, 0) == 1:
            for q in nbrs(p):
                if edge(p, q) not in used_edge:
                    out.append(walk(p, q))
    for p in order:                              # then junctions and leftovers
        for q in nbrs(p):
            if edge(p, q) not in used_edge:
                out.append(walk(p, q))
    return out


def _tangent(pts, end, n=4):
    if end == 0:
        a, b = pts[min(n, len(pts) - 1)], pts[0]
    else:
        a, b = pts[-min(n + 1, len(pts))], pts[-1]
    dx, dy = b[0] - a[0], b[1] - a[1]
    L = math.hypot(dx, dy) or 1.0
    return dx / L, dy / L


def stitch(lines, gap=6.0, max_turn=65.0, snap=1.6, tangent=4, rounds=3):
    """Join polylines whose ends nearly meet and want to continue each other
    (rm_lineart.stitch, unchanged: it is already endpoint work, not pixel work)."""
    lines = [list(p) for p in lines if len(p) >= 2]
    cos_max = math.cos(math.radians(max_turn))
    cell = max(gap, 1e-6)

    for _ in range(max(1, rounds)):
        ends, bucket = [], {}
        for i, p in enumerate(lines):
            for e, pt in ((0, p[0]), (1, p[-1])):
                ends.append((i, e, pt, _tangent(p, e, tangent)))
                bucket.setdefault((int(pt[0] // cell), int(pt[1] // cell)), []).append(len(ends) - 1)
        cands = []
        for m, (i, ei, a, ta) in enumerate(ends):
            cx, cy = int(a[0] // cell), int(a[1] // cell)
            for dx in (-1, 0, 1):
                for dy in (-1, 0, 1):
                    for n in bucket.get((cx + dx, cy + dy), ()):
                        if n <= m:
                            continue
                        j, ej, b, tb = ends[n]
                        if i == j:
                            continue
                        d = math.hypot(b[0] - a[0], b[1] - a[1])
                        if d > gap:
                            continue
                        if d > snap:
                            ux, uy = (b[0] - a[0]) / d, (b[1] - a[1]) / d
                            if (ta[0] * ux + ta[1] * uy) < cos_max:
                                continue
                            if (tb[0] * -ux + tb[1] * -uy) < cos_max:
                                continue
                        cands.append((d, m, n))
        if not cands:
            break
        cands.sort()
        parent = list(range(len(lines)))

        def find(i):
            while parent[i] != i:
                parent[i] = parent[parent[i]]
                i = parent[i]
            return i

        link, taken, joins = {}, set(), 0
        for d, m, n in cands:
            if m in taken or n in taken:
                continue
            i, ei = ends[m][0], ends[m][1]
            j, ej = ends[n][0], ends[n][1]
            ri, rj = find(i), find(j)
            if ri == rj:
                continue
            parent[rj] = ri
            link[(i, ei)] = (j, ej)
            link[(j, ej)] = (i, ei)
            taken.add(m)
            taken.add(n)
            joins += 1
        if not joins:
            break

        out, seen = [], set()
        for i in range(len(lines)):
            if i in seen:
                continue
            enter = 0 if (i, 0) not in link else (1 if (i, 1) not in link else 0)
            chain, cur = [], (i, enter)
            while cur is not None and cur[0] not in seen:
                k, e = cur
                seen.add(k)
                chain += lines[k] if e == 0 else lines[k][::-1]
                cur = link.get((k, 1 - e))
            out.append(chain)
        lines = [p for p in out if len(p) >= 2]
    return lines


def chaikin(pts, iters=2):
    """Corner-cutting: replace every vertex with two points 1/4 in from it."""
    for _ in range(iters):
        if len(pts) < 3:
            break
        out = [pts[0]]
        for a, b in zip(pts, pts[1:]):
            out.append((0.75 * a[0] + 0.25 * b[0], 0.75 * a[1] + 0.25 * b[1]))
            out.append((0.25 * a[0] + 0.75 * b[0], 0.25 * a[1] + 0.75 * b[1]))
        out.append(pts[-1])
        pts = out
    return pts
