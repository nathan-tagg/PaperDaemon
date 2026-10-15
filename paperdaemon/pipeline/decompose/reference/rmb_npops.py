r"""Exact numpy / scipy / numba replacements for the decomposer's per-pixel Python loops.

EVERY function here is bit-for-bit equivalent to the reference routine it replaces --
not "equivalent enough". The equivalences that are not obvious, in short:

  components      OpenCV (or scipy) labels the blobs, but neither library's numbering is
                  trusted: the order is rebuilt as a stable sort on (-area, first raster
                  index), which is exactly what `out.sort(key=lambda t: -t[0])` does to a
                  list built in flood-fill discovery order. That order is the DRAW order.
  chamfer34       the 3-4 chamfer is two sequential scans. Left-to-right inside a row is
                  a running minimum with a +3 ramp, i.e. 3x + minacc(v - 3x), so the whole
                  pass vectorizes per row; the numba kernel does the same recurrence
                  directly and is used when numba is available. (scipy's
                  distance_transform_cdt with a 3-4 metric is a DIFFERENT transform.)
  rank_ext        PIL's MinFilter / MaxFilter replicate the edge pixel (PIL expands the
                  image before its rank filter), so scipy's mode="nearest" matches them
                  exactly -- checked over random masks at k = 3, 5, 7, 9, 11, 13.
  contours        marching squares emits its segments in cell raster order, two for the
                  saddles; only the cells on a boundary are visited here, in the same
                  order, and the chaining uses the exact half-integer endpoint keys.
  simplify        Douglas-Peucker with the original's operand order kept, because the
                  comparison against eps is exact.
  zhang_suen      Zhang-Suen drops a whole sub-iteration's pixels at once, so it is a pure
                  stencil and vectorizes exactly.

Masks are PIL "L" images with values 0 and 255, exactly as in the reference -- the module
boundary is unchanged, so PIL keeps doing the compositing, blurring and pasting it
already does in C.
"""
import math
import os

import numpy as np
from PIL import Image

from paperdaemon.pipeline.decompose.reference import _lazy

ndimage = _lazy.Module("scipy.ndimage")              # loaded on first use: the app reads this module, never runs it
cv2 = _lazy.CV2                                      # connected components with stats in one C call
HAVE_CV2 = _lazy.available("cv2")

_S4 = np.array([[0, 1, 0], [1, 1, 1], [0, 1, 0]], np.uint8)

HAVE_NUMBA = _lazy.available("numba")                # an accelerator, never a dependency; compiled on first call
njit = _lazy.njit


# ---------------------------------------------------------------- PIL <-> numpy
# `np.asarray(pil_image)` copies the whole raster through tobytes(), and the masks cross
# that boundary thousands of times per decomposition. Every mask this module MAKES is
# remembered as the array it was made from, so reading it back is free. That is only
# sound because no such image is ever written to in place: every paste target in the
# decomposer is an Image.new() or a .copy(). Set RMB_VERIFY_CACHE=1 to check each cached
# read against the image's real bytes (used to prove the audit over the whole matrix).
_ATTR = "_rmb_arr"
VERIFY = os.environ.get("RMB_VERIFY_CACHE") == "1"


def _attach(image, a):
    try:
        setattr(image, _ATTR, a)
    except AttributeError:                           # pragma: no cover - not a PIL Image
        pass
    return image


def view(image):
    """An "L" image as a (h, w) uint8 array -- the array it was built from when we built it."""
    a = getattr(image, _ATTR, None)
    if a is not None:
        if VERIFY:
            real = np.asarray(image, dtype=np.uint8)
            if not np.array_equal(real, a):
                raise AssertionError("rmb array cache is stale: the image was written to in place")
        return a
    return np.asarray(image, dtype=np.uint8)


def arr(image):
    """A WRITABLE (h, w) uint8 copy of an "L" image."""
    a = getattr(image, _ATTR, None)
    return a.copy() if a is not None else np.array(image, dtype=np.uint8, copy=True)


def img(a):
    """A (h, w) uint8 array as an "L" image."""
    a = np.ascontiguousarray(a, dtype=np.uint8)
    return _attach(Image.fromarray(a, "L"), a)


def bool_img(a):
    """A (h, w) boolean array as a 0/255 "L" image."""
    a = np.where(a, np.uint8(255), np.uint8(0))
    return _attach(Image.fromarray(a, "L"), a)


def count(img_or_arr):
    """Number of non-zero pixels -- `sum(1 for v in m.getdata() if v)`."""
    a = img_or_arr if isinstance(img_or_arr, np.ndarray) else view(img_or_arr)
    return int(np.count_nonzero(a))


def nonempty(image):
    """`any(v for v in m.getdata() if v)` without the Python loop."""
    return image.getbbox() is not None


# ---------------------------------------------------------------- components
def _label(a):
    """(labels, count, bboxes (n, 4) as y0 y1 x0 x1, areas (n,)) with 4-connectivity."""
    if HAVE_CV2:
        # keyword args: the positional ones after `image` are the output buffers
        n, lab, stats, _c = cv2.connectedComponentsWithStats(np.ascontiguousarray(a), connectivity=4, ltype=cv2.CV_32S)
        n -= 1                                       # label 0 is the background
        if n <= 0:
            return lab, 0, None, None
        x0 = stats[1:, cv2.CC_STAT_LEFT].astype(np.int64)
        y0 = stats[1:, cv2.CC_STAT_TOP].astype(np.int64)
        bb = np.stack([y0, y0 + stats[1:, cv2.CC_STAT_HEIGHT], x0, x0 + stats[1:, cv2.CC_STAT_WIDTH]], axis=1)
        return lab, n, bb, stats[1:, cv2.CC_STAT_AREA].astype(np.int64)
    lab, n = ndimage.label(a, structure=_S4)
    if n == 0:
        return lab, 0, None, None
    objs = ndimage.find_objects(lab)
    bb = np.array([[o[0].start, o[0].stop, o[1].start, o[1].stop] for o in objs], np.int64).reshape(-1, 4)
    return lab, n, bb, np.bincount(lab.ravel(), minlength=n + 1)[1:]


def components(mask, min_span, min_area=0):
    """Connected components (4-neighbor) at least min_span wide or tall (and at
    least min_area pixels), largest first -- the reference `components`.

    The library's own label numbering is never trusted: the order is rebuilt as a stable
    sort on (-area, first raster index), which is exactly what `out.sort(key=-area)` does
    to a list built in flood-fill discovery order. That order is the DRAW order."""
    a = view(mask)
    lab, n, bb, areas = _label(a)
    if n == 0:
        return []
    span = np.maximum(bb[:, 3] - bb[:, 2], bb[:, 1] - bb[:, 0])
    keep = np.flatnonzero((span >= min_span) & (areas >= max(min_area, 1)))
    if keep.size == 0:
        return []
    ar = areas[keep]
    if keep.size > 1 and np.unique(ar).size < ar.size:
        # areas tie, so discovery order decides: the first raster pixel of each label,
        # found by a reverse scatter so the earliest index wins
        flat = lab.ravel()
        nz = np.flatnonzero(flat)
        first = np.empty(n + 1, np.int64)
        first[flat[nz][::-1]] = nz[::-1]
        order = keep[np.lexsort((first[keep + 1], -ar))]
    else:
        order = keep[np.argsort(-ar, kind="stable")]
    out = []
    for k in order:
        y0, y1, x0, x1 = bb[k]
        sub = np.zeros((y1 - y0 + 2, x1 - x0 + 2), np.uint8)
        np.equal(lab[y0:y1, x0:x1], k + 1, out=sub[1:-1, 1:-1].view(bool))
        sub *= 255
        out.append((int(areas[k]), img(sub), (int(x0) - 1, int(y0) - 1)))
    return out


def label_masks(mask):
    """(label image, count) with the same 4-neighbor rule -- for callers that only
    need per-component bookkeeping and never the crops."""
    return ndimage.label(view(mask), structure=_S4)


# ---------------------------------------------------------------- chamfer 3-4
@njit(cache=True, nogil=True)
def _chamfer_nb(fg, out):                            # pragma: no cover - numba kernel
    h, w = fg.shape
    INF = 1000000
    for y in range(h):
        for x in range(w):
            out[y, x] = INF if fg[y, x] else 0
    for y in range(h):
        for x in range(w):
            v = out[y, x]
            if v == 0:
                continue
            if x > 0:
                t = out[y, x - 1] + 3
                if t < v:
                    v = t
            if y > 0:
                t = out[y - 1, x] + 3
                if t < v:
                    v = t
                if x > 0:
                    t = out[y - 1, x - 1] + 4
                    if t < v:
                        v = t
                if x < w - 1:
                    t = out[y - 1, x + 1] + 4
                    if t < v:
                        v = t
            out[y, x] = v
    for y in range(h - 1, -1, -1):
        for x in range(w - 1, -1, -1):
            v = out[y, x]
            if v == 0:
                continue
            if x < w - 1:
                t = out[y, x + 1] + 3
                if t < v:
                    v = t
            if y < h - 1:
                t = out[y + 1, x] + 3
                if t < v:
                    v = t
                if x < w - 1:
                    t = out[y + 1, x + 1] + 4
                    if t < v:
                        v = t
                if x > 0:
                    t = out[y + 1, x - 1] + 4
                    if t < v:
                        v = t
            out[y, x] = v
    return out


def _chamfer_np(fg):
    """The same two scans, vectorized: inside a row the recurrence d[x] = min(cand[x],
    d[x-1]+3) is d[x] = min over x' <= x of cand[x'] + 3(x - x'), i.e. a running minimum
    of cand - 3x with the ramp added back."""
    h, w = fg.shape
    d = np.where(fg, np.int64(1000000), np.int64(0))
    ramp = 3 * np.arange(w, dtype=np.int64)
    for y in range(h):
        row = d[y]
        if y > 0:
            up = d[y - 1]
            cand = up + 3
            np.minimum(cand[1:], up[:-1] + 4, out=cand[1:])
            np.minimum(cand[:-1], up[1:] + 4, out=cand[:-1])
            row = np.minimum(row, cand)
        row = np.minimum.accumulate(row - ramp) + ramp
        d[y] = np.where(fg[y], row, 0)
    for y in range(h - 1, -1, -1):
        row = d[y]
        if y < h - 1:
            dn = d[y + 1]
            cand = dn + 3
            np.minimum(cand[:-1], dn[1:] + 4, out=cand[:-1])
            np.minimum(cand[1:], dn[:-1] + 4, out=cand[1:])
            row = np.minimum(row, cand)
        rev = np.minimum.accumulate(row[::-1] - ramp) + ramp
        d[y] = np.where(fg[y], rev[::-1], 0)
    return d


def chamfer34(mask):
    """Chamfer (3-4) distance to the nearest background pixel -> (flat int array, w, h).

    Nothing outside the image constrains a border pixel, exactly as in the reference."""
    a = view(mask)
    h, w = a.shape
    if HAVE_NUMBA:
        d = np.empty((h, w), np.int64)
        _chamfer_nb(a.astype(np.bool_), d)
    else:
        d = _chamfer_np(a != 0)
    return d.reshape(-1), w, h


# ---------------------------------------------------------------- Zhang-Suen thinning
@njit(cache=True, nogil=True)
def _thin_nb(f):                                     # pragma: no cover - numba kernel
    h, w = f.shape
    drop = np.empty((h, w), np.bool_)
    changed = True
    while changed:
        changed = False
        for step in range(2):
            for y in range(h):
                for x in range(w):
                    drop[y, x] = False
            for y in range(1, h - 1):
                for x in range(1, w - 1):
                    if not f[y, x]:
                        continue
                    n0 = f[y - 1, x]        # N  (0,-1)   p2
                    n1 = f[y - 1, x + 1]    # NE (1,-1)
                    n2 = f[y, x + 1]        # E  (1,0)    p4
                    n3 = f[y + 1, x + 1]    # SE (1,1)
                    n4 = f[y + 1, x]        # S  (0,1)    p6
                    n5 = f[y + 1, x - 1]    # SW (-1,1)
                    n6 = f[y, x - 1]        # W  (-1,0)   p8
                    n7 = f[y - 1, x - 1]    # NW (-1,-1)
                    c = n0 + n1 + n2 + n3 + n4 + n5 + n6 + n7
                    if c < 2 or c > 6:
                        continue
                    t = 0
                    if not n0 and n1:
                        t += 1
                    if not n1 and n2:
                        t += 1
                    if not n2 and n3:
                        t += 1
                    if not n3 and n4:
                        t += 1
                    if not n4 and n5:
                        t += 1
                    if not n5 and n6:
                        t += 1
                    if not n6 and n7:
                        t += 1
                    if not n7 and n0:
                        t += 1
                    if t != 1:
                        continue
                    if step == 0:
                        if (n0 and n2 and n4) or (n2 and n4 and n6):
                            continue
                    else:
                        if (n0 and n2 and n6) or (n0 and n4 and n6):
                            continue
                    drop[y, x] = True
            for y in range(1, h - 1):
                for x in range(1, w - 1):
                    if drop[y, x]:
                        f[y, x] = False
                        changed = True
    return f


def _thin_np(f):
    def sh(dy, dx):
        out = np.zeros_like(f)
        ys = slice(max(0, dy), f.shape[0] + min(0, dy))
        xs = slice(max(0, dx), f.shape[1] + min(0, dx))
        yd = slice(max(0, -dy), f.shape[0] + min(0, -dy))
        xd = slice(max(0, -dx), f.shape[1] + min(0, -dx))
        out[yd, xd] = f[ys, xs]
        return out
    changed = True
    while changed:
        changed = False
        for step in (0, 1):
            n = [sh(-1, 0), sh(-1, 1), sh(0, 1), sh(1, 1), sh(1, 0), sh(1, -1), sh(0, -1), sh(-1, -1)]
            c = sum(x.astype(np.int8) for x in n)
            t = sum((~n[i] & n[(i + 1) % 8]).astype(np.int8) for i in range(8))
            ok = f & (c >= 2) & (c <= 6) & (t == 1)
            if step == 0:
                ok &= ~((n[0] & n[2] & n[4]) | (n[2] & n[4] & n[6]))
            else:
                ok &= ~((n[0] & n[2] & n[6]) | (n[0] & n[4] & n[6]))
            if ok.any():
                f = f & ~ok
                changed = True
    return f


def zhang_suen(fg):
    """Zhang-Suen thinning of a boolean array; a 1-px border of False is assumed."""
    f = np.ascontiguousarray(fg, dtype=np.bool_)
    if not f.any():
        return f
    if HAVE_NUMBA:
        return _thin_nb(f)
    return _thin_np(f)


def thin_mask(mask):
    """Thin a 0/255 "L" image (or boolean array) -> boolean array of the same shape."""
    a = mask if isinstance(mask, np.ndarray) else view(mask)
    f = np.zeros((a.shape[0] + 2, a.shape[1] + 2), np.bool_)
    f[1:-1, 1:-1] = a != 0
    return zhang_suen(f)[1:-1, 1:-1]


# ---------------------------------------------------------------- morphology
def rank_ext(a, k, ismax):
    """A k x k maximum (ismax) or minimum filter with the edge pixel REPLICATED.

    That is exactly what PIL's MaxFilter / MinFilter do -- PIL expands the image before
    its rank filter -- and what scipy's mode="nearest" does; checked against PIL over
    random masks at k = 3, 5, 7, 9, 11, 13. scipy's kernel is separable and O(n) in k,
    where PIL's is O(n k^2), which is what made the big closings cheap. (A hand-written
    numba kernel was tried and is slower on the real mask sizes: scipy wins.)
    """
    f = ndimage.maximum_filter if ismax else ndimage.minimum_filter
    return f(np.ascontiguousarray(a, dtype=np.uint8), size=k, mode="nearest")


# ---------------------------------------------------------------- runs
@njit(cache=True, nogil=True)
def _runs_nb(a, ys, out):                            # pragma: no cover - numba kernel
    k = 0
    w = a.shape[1]
    for i in range(ys.shape[0]):
        y = ys[i]
        x = 0
        while x < w:
            if a[y, x]:
                x0 = x
                while x < w and a[y, x]:
                    x += 1
                out[k, 0] = y
                out[k, 1] = x0
                out[k, 2] = x - 1
                k += 1
            else:
                x += 1
    return k


def row_runs(a, ys):
    """All horizontal runs of non-zero pixels on rows `ys` -> (n, 3) array of
    (y, x0, x1) in row then x order -- the reference `_runs` over the same rows."""
    a = np.ascontiguousarray(a != 0)
    ys = np.ascontiguousarray(np.asarray(ys, np.int64))
    if ys.size == 0 or a.size == 0:
        return np.zeros((0, 3), np.int64)
    if HAVE_NUMBA:
        cap = int(a[ys].sum()) + 1
        out = np.empty((cap, 3), np.int64)
        k = _runs_nb(a, ys, out)
        return out[:k]
    rows = a[ys]
    pad = np.zeros((rows.shape[0], 1), bool)
    p = np.hstack([pad, rows, pad])
    d = np.diff(p.astype(np.int8), axis=1)
    sy, sx = np.nonzero(d == 1)
    _ey, ex = np.nonzero(d == -1)
    return np.stack([ys[sy], sx, ex - 1], axis=1)


# ---------------------------------------------------------------- marching squares
# Corner bits: 1=TL 2=TR 4=BR 8=BL, set when the corner is BELOW the threshold. Edge ids
# are T=0 R=1 B=2 L=3. Saddles (5, 10) emit two segments, in this order.
_CASES = {
    1: ((3, 0),), 2: ((0, 1),), 3: ((3, 1),),
    4: ((1, 2),), 6: ((0, 2),), 7: ((3, 2),),
    8: ((2, 3),), 9: ((2, 0),), 11: ((2, 1),),
    12: ((1, 3),), 13: ((1, 0),), 14: ((0, 3),),
    5: ((3, 0), (1, 2)), 10: ((0, 1), (2, 3)),
}
_NSEG = np.zeros(16, np.int64)
_EDGE = np.zeros((16, 2, 2), np.int64)               # [code][which segment][end] -> edge id
for _c, _prs in _CASES.items():
    _NSEG[_c] = len(_prs)
    for _i, _pr in enumerate(_prs):
        _EDGE[_c, _i] = _pr
# midpoint of edge e of cell (x, y), and the exact integer key round(2*coord) of it
_EX = np.array([0.5, 1.0, 0.5, 0.0])
_EY = np.array([0.0, 0.5, 1.0, 0.5])
_KX = np.array([1, 2, 1, 0], np.int64)
_KY = np.array([0, 1, 2, 1], np.int64)


def contours(a, w, h, level):
    """Marching squares at one level, chained into polylines -- rm_trace's
    `join(iso_segments(...))` in one pass.

    Only the cells on a boundary are visited, and in the same raster order, so the
    segment list -- and therefore which chain each segment lands in -- is the reference's.
    The endpoints are exact half-integers, so `round(2 * coord)` is an exact integer key
    and two endpoints share a key only when they are the SAME point: the original's 0.26
    tolerance test can never fail for a same-key candidate, and is a key comparison here.
    """
    if w < 2 or h < 2:
        return []
    b = a[:h, :w] < level
    code = (b[:-1, :-1].astype(np.uint8) | (b[:-1, 1:].astype(np.uint8) << 1)
            | (b[1:, 1:].astype(np.uint8) << 2) | (b[1:, :-1].astype(np.uint8) << 3))
    flat = code.ravel()
    sel = np.flatnonzero((flat != 0) & (flat != 15))
    if sel.size == 0:
        return []
    codes = flat[sel].astype(np.int64)
    nseg = _NSEG[codes]
    rep = np.repeat(np.arange(sel.size), nseg)                 # cell of each segment
    sub = np.arange(int(nseg.sum())) - np.repeat(np.cumsum(nseg) - nseg, nseg)
    cy, cx = np.divmod(sel[rep], w - 1)
    e0 = _EDGE[codes[rep], sub, 0]
    e1 = _EDGE[codes[rep], sub, 1]
    ax = (cx + _EX[e0]).tolist()
    ay = (cy + _EY[e0]).tolist()
    bx = (cx + _EX[e1]).tolist()
    by = (cy + _EY[e1]).tolist()
    kk = 2 * w + 4
    ka = ((2 * cy + _KY[e0]) * kk + 2 * cx + _KX[e0]).tolist()
    kb = ((2 * cy + _KY[e1]) * kk + 2 * cx + _KX[e1]).tolist()

    n = len(ka)
    ends = {}
    for i in range(n):
        ends.setdefault(ka[i], []).append(i)
        ends.setdefault(kb[i], []).append(i)
    used = bytearray(n)
    out = []
    for i in range(n):
        if used[i]:
            continue
        used[i] = 1
        fwd = [(ax[i], ay[i]), (bx[i], by[i])]
        back = []
        for direction in (0, 1):
            tip = kb[i] if direction == 0 else ka[i]
            chain = fwd if direction == 0 else back
            while True:
                nxt = -1
                for j in ends.get(tip, ()):
                    if not used[j]:
                        nxt = j
                        break
                if nxt < 0:
                    break
                used[nxt] = 1
                if ka[nxt] == tip:
                    chain.append((bx[nxt], by[nxt]))
                    tip = kb[nxt]
                else:
                    chain.append((ax[nxt], ay[nxt]))
                    tip = ka[nxt]
        out.append(back[::-1] + fwd if back else fwd)
    return out


# ---------------------------------------------------------------- Douglas-Peucker
def simplify(pts, eps):
    """Douglas-Peucker -- rm_trace.simplify with its recursion turned into a stack.

    The distance expression is kept in the original's operand order (only the two
    constant products are hoisted, and they are the same two multiplications), because a
    different association is a different float and the comparison against `eps` is exact.
    A closed contour arrives with its two ends on the same point, so the degenerate
    branch is the common case, not a rarity -- it uses math.hypot, as the original does.
    """
    n = len(pts)
    if n < 3:
        return pts
    keep = bytearray(n)
    keep[0] = keep[n - 1] = 1
    stack = [(0, n - 1)]
    while stack:
        i0, i1 = stack.pop()
        if i1 - i0 < 2:
            continue
        x0, y0 = pts[i0]
        x1, y1 = pts[i1]
        dx, dy = x1 - x0, y1 - y0
        ln = math.hypot(dx, dy)
        worst, wi = -1.0, 0
        if ln > 1e-9:
            c0, c1 = x1 * y0, y1 * x0
            for i in range(i0 + 1, i1):
                x, y = pts[i]
                d = abs(dy * x - dx * y + c0 - c1) / ln
                if d > worst:
                    worst, wi = d, i
        else:
            for i in range(i0 + 1, i1):
                x, y = pts[i]
                d = math.hypot(x - x0, y - y0)
                if d > worst:
                    worst, wi = d, i
        if worst <= eps:
            continue
        keep[wi] = 1
        stack.append((i0, wi))
        stack.append((wi, i1))
    return [pts[i] for i in range(n) if keep[i]]
