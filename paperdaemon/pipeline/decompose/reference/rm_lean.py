r"""Lighter decompositions: fewer strokes and points out of the decomposer, with no visible change on the
tablet. The decomposer produces too many strokes, so a limit has to be enforced without hurting image quality.

THE DECOMPOSER IS NOT TOUCHED. Everything here works on its output -- a list of
(points, widths, tool, color, rgba) -- under the device's own drawing model, as measured: every wash (highlighter)
first, in file order, as a per-channel MINIMUM over what is under it, so a same-color overlap never darkens;
and each wash painting exactly the pixels whose CENTERS lie inside
its footprint, with no anti-aliasing and no minimum width (rm_raster, measured against the app's own
render). Pens are drawn on top, opaque, and are never removed: the pen's rasterization has no model yet.

A PITFALL: "already drawn" must not be decided on PIL's fill with every width floored to one
pixel. Two thin washes that never touch would be counted as covering the same pixel, one would be removed, and the
device -- which draws neither of them there, or only one -- would show a pinhole. Measured at 2x, 200-px drawings
came out 1.3-7.3% lighter that way. A "0 pixels changed" figure measured on that same floored grid could only
ever be zero.

WHERE THE WEIGHT IS (a busy illustration): 136,319 strokes, 85% of them washes; 38% of all
strokes span under one pixel, 57% under two, each still carrying eight points or more.

  prune(strokes)     drops what is already drawn. A wash goes when, everywhere it touches, other washes
                     already give that color or darker in every channel, or ink hides it; an ink stroke
                     goes when other ink of the same color covers it entirely. Exact on a grid SS times
                     finer than the page, with every footprint drawn by the renderer's own _draw.
  simplify(strokes)  drops points within TOL page px of the line through the points kept around them
                     (position and half-width together), so no edge moves more than that.
  lean(strokes)      both, prune first.

render(strokes) draws a stroke list exactly as rm_render.render composites a page; it is how a lean
result is checked against the original, pixel by pixel.
"""
import math

import numpy as np
from PIL import Image, ImageChops, ImageDraw

from paperdaemon.pipeline.decompose.reference import rm_raster as RS
from paperdaemon.pipeline.page import render as R

# THE SCREEN'S OWN PIXELS: one sample a page px, on the screen's grid (the page's x = 0 is a pixel edge: the
# screen is 1620 wide). With the device's rule in rm_raster that grid IS the device; a finer one would sample
# centers the device never samples.
SS = 1
TOL = 0.5         # simplify: how far a dropped point may sit off the line -- and only if not one pixel moves
BYTES_STROKE, BYTES_POINT = 72, 14     # a v6 .rm, fitted to a 136,319-stroke page: 42,689,057 bytes


class _Pt:
    __slots__ = ("width", "pressure")

    def __init__(self, w):
        self.width = w
        self.pressure = 190           # what rm_art.write_rm gives every point; the pencil's grain reads it


class _Line:
    __slots__ = ("tool", "points", "color", "color_rgba")


def _fam(tool):
    return tool.name.split("_")[0]


def is_wash(s):
    return s[2].name.startswith("HIGHLIGHTER")


def is_grain(s):
    return _fam(s[2]) in R.PENCIL_FAMILY


def _line(s, widths):
    L = _Line()
    L.tool, L.color, L.color_rgba = s[2], s[3], s[4]
    L.points = [_Pt(w) for w in widths]
    return L


FLOOR_MODEL = False   # True: the old PIL-floored footprints (every width floored at one pixel). Controls only.
BLACK_POINT_L = None  # render(): when set, every wash darker than this L* is painted true black (0, 0, 0). The engine
                      # never fills a thick dark mass with black ink (BLACK_MASS_THICK: it becomes a wash of its own
                      # color plus hatch), so a picture meant for an OLED screen gets its blacks here, at render time,
                      # with the decomposition untouched (the decomposition behaves differently on an OLED screen).
                      # None = the colors as decomposed.
WASH_EPS = 0.35       # render(): how far outside the exact footprint a pixel center may lie and still be painted (px).
                      # 0 = the pixel-center rule as calibrated on lines (thumbnails). A 4.6x screen share of a
                      # painting showed the device filling
                      # the single-pixel gaps the exact rule leaves between tiny flecks: of 3,435 predicted holes the
                      # device showed none; 0.35 px leaves 8. FITTED ON THAT ONE VIEW -- a calibration page
                      # (width ladder, diamonds, four-corner flecks) zoomed is what pins the rule.


def _footprint(s, ss, ox, oy, W, H, eps=0.0):
    """The flat indices of the grid pixels a stroke paints.

    WASHES: the device's own rule (rm_raster, measured): a pixel is painted when its center lies inside
    the exact footprint. `eps` widens (+) or shrinks (-) the footprint by that margin, so a decision can be made
    safe under either boundary convention.
    PENS: still PIL's fill with widths floored at one pixel. The pen's rasterization measured unlike the wash's
    (0.58 px drew at half darkness) and has no model yet; pens are never removed here, only drawn."""
    pts, widths, tool = s[0], s[1], s[2]
    if len(pts) < 2:
        return np.empty(0, np.int32)
    if is_wash(s) and not FLOOR_MODEL:
        return RS.wash_pixels(pts, widths, ox * ss, oy * ss, W, H, eps=eps, scale=ss)
    k = R.WSCALE.get(_fam(tool), R.WSCALE_WRITER)
    wf = [max(1.0, float(w) * k) * ss / k for w in widths]
    P = [((x - ox) * ss, (y - oy) * ss) for x, y in pts]
    pad = max(wf) * k + 3
    xs, ys = [p[0] for p in P], [p[1] for p in P]
    x0, y0 = max(0, int(min(xs) - pad)), max(0, int(min(ys) - pad))
    x1, y1 = min(W, int(max(xs) + pad) + 2), min(H, int(max(ys) + pad) + 2)
    if x1 <= x0 or y1 <= y0:
        return np.empty(0, np.int32)
    im = Image.new("L", (x1 - x0, y1 - y0), 0)
    R._draw(ImageDraw.Draw(im), _line(s, wf), 255, [(x - x0, y - y0) for x, y in P])
    yy, xx = np.nonzero(np.asarray(im))
    return ((yy + y0) * W + (xx + x0)).astype(np.int32)


def _rgb(s):
    return tuple(int(v) for v in (s[4][:3] if s[4] else (255, 237, 117)))


def _cover(strokes, ss=SS, eps_out=None):
    """What prune and join both need, computed once, for the WASHES only: each wash's SURE footprint (the pixels the
    device paints under either boundary rule) and POSSIBLE footprint (those plus any pixel whose center lies exactly
    on the footprint's edge -- or, with `eps_out`, within that many page px outside it), and per channel the darkest
    value every pixel surely gets and how many washes give it (the paper gives 255). Ink is not part of it: ink is
    never removed, and nothing counts as hidden under it, because the pen's rasterization is not modeled.

    eps_out: the exact pixel-center rule is what the pinhole calibration measured, but a zoomed screen view
    showed the device filling the one-pixel gaps that rule predicts, which render() models as WASH_EPS = 0.35 px of
    fill past every edge. A prune that only knows the exact rule removes washes whose 0.35-px band nothing else
    paints: measured as 17-105 lost pixels per small page, up to ~15,000 on a full painting. Passing
    eps_out=WASH_EPS makes the possible footprint the 0.35 band and keeps a SECOND darkest-value map (m2, c2) over
    those wide footprints, so a wash goes only when it changes no pixel under the exact rule AND no pixel under the
    wide one. (A stricter variant, demanding the band be covered by the others' EXACT
    footprints, is safe under every rule in between the two, but it throws away half the saving, because a ring's
    band is almost always painted by its neighbors' bands and only rarely by their exact footprints.)"""
    n = len(strokes)
    wash = [i for i in range(n) if is_wash(strokes[i]) and len(strokes[i][0]) >= 2]
    ox, oy, W, H = _grid(strokes)
    wide = eps_out is not None
    eo = max(RS.EPS, float(eps_out)) if wide else RS.EPS
    sure, poss = {}, {}
    m1 = np.full((3, W * H), 255, np.uint8)
    c1 = np.ones((3, W * H), np.uint16)
    m2 = np.full((3, W * H), 255, np.uint8) if wide else None     # the same two, under the wide rule
    c2 = np.ones((3, W * H), np.uint16) if wide else None
    for i in wash:
        f = sure[i] = _footprint(strokes[i], ss, ox, oy, W, H, eps=-RS.EPS)
        p = _footprint(strokes[i], ss, ox, oy, W, H, eps=eo)
        poss[i] = p if len(p) != len(f) else f
        col = _rgb(strokes[i])
        if len(f):
            _darken(m1, c1, f, col)
        if wide and len(p):
            _darken(m2, c2, p, col)
    return dict(wash=wash, sure=sure, poss=poss, m1=m1, c1=c1, m2=m2, c2=c2, wide=wide, eo=eo, ss=ss, ox=ox, oy=oy, W=W, H=H)


def _darken(m, c, pix, col):
    """A wash of color col over the pixels pix: per channel the darkest value so far and how many washes give it."""
    for k, v in enumerate(col):
        cur = m[k][pix]
        lt, eq = pix[v < cur], pix[v == cur]
        m[k][lt] = v
        c[k][lt] = 1
        c[k][eq] += 1


def _sole(m, c, pix, col):
    """Is a wash of color col, somewhere in pix, the only wash giving the darkest value (in some channel)?"""
    return any(np.any((m[k][pix] == v) & (c[k][pix] == 1)) for k, v in enumerate(col))


def _spend(m, c, pix, col):
    """A wash of color col leaves: wherever it gave the darkest value it no longer counts among the providers."""
    for k, v in enumerate(col):
        c[k][pix[m[k][pix] == v]] -= 1


def _others_dark(m, c, pix, col, own):
    """Do the washes OTHER than `own` paint every pixel of pix at least as dark as col? m/c hold the darkest value
    and its provider count over every wash still present; `own` lists the footprints (under m's rule) of the washes
    to leave out, each of which counts as one provider wherever its footprint holds the pixel and the darkest value
    is its own color."""
    if not len(pix):
        return True
    mine = np.zeros(len(pix), np.uint16)
    for fp in own:
        mine += np.isin(pix, fp, assume_unique=True)
    for k, v in enumerate(col):
        mk, ck = m[k][pix], c[k][pix]
        if np.any(mk > v) or np.any((mk == v) & (ck <= mine)):
            return False
    return True


def _drops(strokes, C):
    """The washes that change no pixel on the device: every pixel one MIGHT paint is SURELY painted at least as dark
    by the others. Spends C's counts as it goes, so m1 (and m2) stay the darkest value the remaining washes give."""
    sure, poss, m1, c1 = C["sure"], C["poss"], C["m1"], C["c1"]
    wide, m2, c2 = C["wide"], C["m2"], C["c2"]
    drop = set()
    # smallest first: the specks are both the most numerous and the most often already drawn
    for i in sorted(C["wash"], key=lambda i: len(sure[i])):
        f, p, col = sure[i], poss[i], _rgb(strokes[i])
        if not len(p):
            continue                                  # paints nothing even on the boundary: left alone
        if len(f) and _sole(m1, c1, f, col):
            continue                                  # exact rule: somewhere the only wash giving the darkest value
        if wide:
            if _sole(m2, c2, p, col):
                continue                              # wide rule: the same, over everything it might paint
            # the exact rule's edge ties (a center within EPS of the footprint's edge): the wash may or may not paint
            # them, so the rest must already be that dark there
            tie = np.setdiff1d(_footprint(strokes[i], C["ss"], C["ox"], C["oy"], C["W"], C["H"], eps=RS.EPS), f, assume_unique=True)
            if len(tie) and any(np.any(m1[k][tie] > v) for k, v in enumerate(col)):
                continue
        elif len(p) > len(f):
            extra = np.setdiff1d(p, f, assume_unique=True)
            if any(np.any(m1[k][extra] > v) for k, v in enumerate(col)):
                continue                              # a boundary pixel it might paint that nothing else surely does
        drop.add(i)
        if len(f):
            _spend(m1, c1, f, col)
        if wide:
            _spend(m2, c2, p, col)
    return drop


def prune(strokes, ss=SS, eps_out=None):
    """-> (the strokes still needed, in their order; how many went). Washes only: ink is never removed.
    eps_out: see _cover (None = the exact rule only; WASH_EPS = safe under the renderer's edge fill as well)."""
    if not len(strokes):
        return list(strokes), {"washes": 0, "ink": 0}
    drop = _drops(strokes, _cover(strokes, ss, eps_out))
    kept = [s for i, s in enumerate(strokes) if i not in drop]
    return kept, {"washes": len(drop), "ink": 0}


def prune_join(strokes, radius=6.0, max_points=4000, eps_out=None, radius_w=0.0):
    """prune, then join washes of one color, tool and width end to start wherever the connecting piece lands only on
    pixels already surely that dark; one coverage pass serves both. Washes stay before the pens in the result, as
    the decomposer orders them (a wash drawn after ink would tint it). -> (strokes, {"pruned": .., "joins": ..})

    eps_out: None = exact under the pixel-center rule only; WASH_EPS = also exact under the
    renderer's 0.35-px edge fill (see _cover). With eps_out a join must leave every pixel as it was under BOTH
    rules: under each, the pixels the two ends and the joined piece paint differently must be painted at least as
    dark by the other washes (_others_dark).
    radius / radius_w: a join looks for a next stroke starting within max(radius, radius_w * width) page px of the
    current end. The planner's rings lie .42 widths apart, so on a full page (widths to 19 px) a fixed 6 px misses
    most ring-to-ring hops: Girl with a Pearl Earring joined 2,430 strokes at 6 px and 20,874 at 50 px, every one
    still pixel-exact. The search is what the radius bounds; exactness is the tests'."""
    if not len(strokes):
        return list(strokes), {"pruned": 0, "joins": 0}
    C = _cover(strokes, SS, eps_out)
    wide, eo = C["wide"], C["eo"]
    drop = _drops(strokes, C)
    keep = [i for i in range(len(strokes)) if i not in drop]
    ss, ox, oy, W, H, m1 = C["ss"], C["ox"], C["oy"], C["W"], C["H"], C["m1"]
    sure, poss, m2, c1, c2 = C["sure"], C["poss"], C["m2"], C["c1"], C["c2"]
    pens = [i for i in keep if not is_wash(strokes[i])]
    # joinable: at least two points and ONE width throughout -- a width change inside one stroke is unverified on
    # the device (the decomposer never writes one); other washes pass through untouched
    wash, single = [], []
    for i in keep:
        if is_wash(strokes[i]):
            (wash if len(strokes[i][0]) >= 2 and min(strokes[i][1]) == max(strokes[i][1]) else single).append(i)
    if not wash:
        return [strokes[i] for i in keep], {"pruned": len(drop), "joins": 0}
    rest = single + pens

    def free(pix, col):
        return bool(np.all((m1[0][pix] <= col[0]) & (m1[1][pix] <= col[1]) & (m1[2][pix] <= col[2])))

    def piece(pts, wid, like):
        return (list(pts), list(wid)) + tuple(like[2:])

    ends = {}

    def end_fp(i, tail, eps):
        """The footprint of stroke i's last (tail) or first two points, possible (+eps) or sure (-eps): the same
        either way round."""
        f = ends.get((i, tail, eps))
        if f is None:
            s = strokes[i]
            sl = slice(-2, None) if tail else slice(0, 2)
            f = ends[(i, tail, eps)] = _footprint(piece(s[0][sl], s[1][sl], s), ss, ox, oy, W, H, eps=eps)
        return f

    groups = {}
    for i in wash:
        groups.setdefault((_rgb(strokes[i]), strokes[i][2], strokes[i][3], strokes[i][1][0]), []).append(i)
    out, joins = [], 0
    for (col, _t, _c, _w), idxs in groups.items():
        cell = max(float(radius), float(radius_w) * float(_w))
        key = lambda p: (int(p[0] // cell), int(p[1] // cell))
        buckets = {}
        for i in idxs:
            for p in (strokes[i][0][0], strokes[i][0][-1]):
                buckets.setdefault(key(p), set()).add(i)
        left = set(idxs)
        for i in sorted(idxs, key=lambda i: (strokes[i][0][0][1], strokes[i][0][0][0])):
            if i not in left:
                continue
            left.discard(i)
            like = strokes[i]
            pts, wid = list(like[0]), list(like[1])
            cur, cur_tail = i, True                   # the stroke whose end the chain currently ends with, and which end
            while len(pts) < max_points:
                ex, ey = pts[-1]
                cx, cy = key(pts[-1])
                near = set()
                for dx in (-1, 0, 1):
                    for dy in (-1, 0, 1):
                        near |= buckets.get((cx + dx, cy + dy), set())
                near &= left
                best = []
                for j in near:
                    sj = strokes[j][0]
                    for rev in (False, True):
                        bx, by = sj[-1] if rev else sj[0]
                        d = math.sqrt((bx - ex) * (bx - ex) + (by - ey) * (by - ey))   # sqrt: bit-identical in the C port
                        if d <= cell:
                            best.append((d, j, rev))
                took = False
                for d, j, rev in sorted(best):
                    bp = strokes[j][0][::-1] if rev else strokes[j][0]
                    bw = strokes[j][1][::-1] if rev else strokes[j][1]
                    joined = piece(pts[-2:] + list(bp[:2]), wid[-2:] + list(bw[:2]), like)
                    new = _footprint(joined, ss, ox, oy, W, H, eps=eo)
                    e_sure = np.union1d(end_fp(cur, cur_tail, -RS.EPS), end_fp(j, rev, -RS.EPS))
                    if not wide:
                        e_poss = np.union1d(end_fp(cur, cur_tail, eo), end_fp(j, rev, eo))
                        if len(np.setdiff1d(e_poss, new, assume_unique=True)):
                            continue                      # the joined piece would miss a pixel the two might paint
                        # EVERYTHING THE JOINED PIECE MIGHT PAINT THAT THE TWO DID NOT SURELY PAINT must already be
                        # that dark -- not just what lay outside their possible footprints: a pixel on a stroke's edge,
                        # unpainted by the device's tie rule, can be painted outright once the join's bevel covers it
                        # (found as the one changed pixel on a full page)
                        if not free(np.setdiff1d(new, e_sure, assume_unique=True), col):
                            continue
                    else:
                        # BOTH RULES, exactly. Exact rule: every pixel either the two ends or the joined piece might
                        # paint (footprints with their edge ties), less what both surely paint, must be at least as
                        # dark from the OTHER washes. Wide rule: the same over the symmetric difference of the two
                        # wide footprints. "Others" leaves out what the two END PIECES provide (_others_dark): the
                        # joined stroke still contains both strokes' every segment, only the caps at the seam change,
                        # so a pixel the body of either stroke paints elsewhere is rightly still counted. (Leaving
                        # out the whole strokes was correct but needlessly strict: 2,693 joins instead of 5,668 on
                        # the 200-px self-portrait.)
                        j_sure = _footprint(joined, ss, ox, oy, W, H, eps=-RS.EPS)
                        e_tie = np.union1d(end_fp(cur, cur_tail, RS.EPS), end_fp(j, rev, RS.EPS))
                        j_tie = _footprint(joined, ss, ox, oy, W, H, eps=RS.EPS)
                        u_exact = np.setdiff1d(np.union1d(e_tie, j_tie), np.intersect1d(e_sure, j_sure, assume_unique=True), assume_unique=True)
                        if not _others_dark(m1, c1, u_exact, col, (end_fp(cur, cur_tail, -RS.EPS), end_fp(j, rev, -RS.EPS))):
                            continue
                        e_wide = np.union1d(end_fp(cur, cur_tail, eo), end_fp(j, rev, eo))
                        if not _others_dark(m2, c2, np.setxor1d(e_wide, new, assume_unique=True), col, (end_fp(cur, cur_tail, eo), end_fp(j, rev, eo))):
                            continue
                    pts += list(bp)
                    wid += list(bw)
                    left.discard(j)
                    joins += 1
                    cur, cur_tail = j, not rev            # it ends with j's other end now
                    took = True
                    break
                if not took:
                    break
            out.append(piece(pts, wid, like))
    return out + [strokes[i] for i in rest], {"pruned": len(drop), "joins": joins}


def _keep(P, tol):
    """Ramer-Douglas-Peucker on (x, y, half-width): the indices to keep."""
    n = len(P)
    if n < 3:
        return np.arange(n)
    keep = np.zeros(n, bool)
    keep[0] = keep[-1] = True
    stack = [(0, n - 1)]
    while stack:
        lo, hi = stack.pop()
        if hi - lo < 2:
            continue
        seg, mid = P[hi] - P[lo], P[lo + 1:hi] - P[lo]
        L2 = float(seg @ seg)
        t = np.clip(mid @ seg / L2, 0.0, 1.0) if L2 > 1e-12 else np.zeros(len(mid))
        d = np.sqrt(((mid - t[:, None] * seg) ** 2).sum(axis=1))
        j = int(np.argmax(d))
        if d[j] > tol:
            m = lo + 1 + j
            keep[m] = True
            stack += [(lo, m), (m, hi)]
    return np.nonzero(keep)[0]


def _same_pixels(a, b):
    """Do two versions of one stroke cover exactly the same screen pixels?"""
    xs = [p[0] for p in a[0]] + [p[0] for p in b[0]]
    ys = [p[1] for p in a[0]] + [p[1] for p in b[0]]
    ox, oy = np.floor(min(xs) - 40.0), np.floor(min(ys) - 40.0)
    W, H = int(max(xs) + 40.0 - ox) + 1, int(max(ys) + 40.0 - oy) + 1
    fa, fb = _footprint(a, 1, ox, oy, W, H), _footprint(b, 1, ox, oy, W, H)
    return len(fa) == len(fb) and bool(np.array_equal(np.sort(fa), np.sort(fb)))


def simplify(strokes, tol=TOL):
    """-> (the strokes with fewer points, how many points went). A stroke is thinned only when it then
    covers exactly the same screen pixels; otherwise it keeps every point. Pencil keeps its points: its
    grain is laid out from them."""
    out, gone = [], 0
    for s in strokes:
        pts, widths, tool = s[0], s[1], s[2]
        if len(pts) < 3 or is_grain(s):
            out.append(s)
            continue
        k = R.WSCALE.get(_fam(tool), R.WSCALE_WRITER)
        P = np.column_stack([np.asarray(pts, float).reshape(-1, 2),
                             np.maximum(1.0, np.asarray(widths, float) * k) / 2.0])
        done = s
        for t in (tol, tol / 2.0):
            idx = _keep(P, t)
            if len(idx) == len(pts):
                break
            cand = ([pts[i] for i in idx], [widths[i] for i in idx]) + tuple(s[2:])
            if _same_pixels(s, cand):
                done = cand
                break
        gone += len(pts) - len(done[0])
        out.append(done)
    return out, gone


def _grid(strokes):
    a = np.concatenate([np.asarray(s[0], float).reshape(-1, 2) for s in strokes if len(s[0])])
    ox, oy = np.floor(a[:, 0].min() - 40.0), np.floor(a[:, 1].min() - 40.0)
    return ox, oy, int(a[:, 0].max() + 40.0 - ox) + 1, int(a[:, 1].max() + 40.0 - oy) + 1


def chain(strokes, radius=6.0, max_points=4000):
    """Same-color washes joined into fewer strokes. -> (strokes, how many joins).

    A same-color overlap never darkens, so two washes of one color can be one stroke whenever the bit that
    joins them -- the connecting segment and the bevels at the two new corners -- lands only on pixels
    that are already that color or darker in every channel, or under ink; and the join must not lose a
    pixel either stroke covered. Checked at every join, on the screen's pixels. Washes of different
    colors commute (a minimum), so grouping them by color changes nothing; ink stays last."""
    n = len(strokes)
    wash = [i for i in range(n) if is_wash(strokes[i]) and len(strokes[i][0]) >= 2]
    rest = [i for i in range(n) if i not in set(wash)]
    if not wash or any(not is_wash(strokes[i]) and i < max(wash) for i in rest):
        return list(strokes), 0                        # only when every wash comes before the ink
    ox, oy, W, H = _grid(strokes)
    hidden = np.zeros(W * H, bool)
    for i in rest:
        if not is_wash(strokes[i]) and not is_grain(strokes[i]):
            hidden[_footprint(strokes[i], 1, ox, oy, W, H)] = True
    m1 = np.full((3, W * H), 255, np.uint8)
    for i in wash:
        f = _footprint(strokes[i], 1, ox, oy, W, H)
        for k, v in enumerate(_rgb(strokes[i])):
            m1[k][f] = np.minimum(m1[k][f], v)

    def free(pix, col):
        return bool(np.all(hidden[pix] | ((m1[0][pix] <= col[0]) & (m1[1][pix] <= col[1]) & (m1[2][pix] <= col[2]))))

    def piece(pts, wid, like):
        return (list(pts), list(wid)) + tuple(like[2:])

    def joins_cleanly(a, b, like, col):
        """a = the chain's last two points and widths, b = the next stroke's first two: does one polyline
        through them draw only already-drawn pixels beyond what the two drew apart, and lose none?"""
        old = np.union1d(_footprint(piece(a[0], a[1], like), 1, ox, oy, W, H),
                         _footprint(piece(b[0], b[1], like), 1, ox, oy, W, H))
        new = _footprint(piece(a[0] + b[0], a[1] + b[1], like), 1, ox, oy, W, H)
        if len(np.setdiff1d(old, new, assume_unique=True)):
            return False
        return free(np.setdiff1d(new, old, assume_unique=True), col)

    groups = {}
    for i in wash:
        groups.setdefault((_rgb(strokes[i]), strokes[i][2], strokes[i][3]), []).append(i)
    out, joins, cell = [], 0, float(radius)
    key = lambda p: (int(p[0] // cell), int(p[1] // cell))
    for (col, _t, _c), idxs in groups.items():
        buckets = {}
        for i in idxs:
            for p in (strokes[i][0][0], strokes[i][0][-1]):
                buckets.setdefault(key(p), set()).add(i)
        todo = sorted(idxs, key=lambda i: (strokes[i][0][0][1], strokes[i][0][0][0]))
        left = set(idxs)
        for i in todo:
            if i not in left:
                continue
            left.discard(i)
            like = strokes[i]
            pts, wid = list(like[0]), list(like[1])
            while len(pts) < max_points:
                ex, ey = pts[-1]
                cx, cy = key(pts[-1])
                near = set()
                for dx in (-1, 0, 1):
                    for dy in (-1, 0, 1):
                        near |= buckets.get((cx + dx, cy + dy), set())
                near &= left
                best = []
                for j in near:
                    for rev in (False, True):
                        bp = strokes[j][0][::-1] if rev else strokes[j][0]
                        d = ((bp[0][0] - ex) ** 2 + (bp[0][1] - ey) ** 2) ** 0.5
                        if d <= radius:
                            best.append((d, j, rev))
                took = False
                for d, j, rev in sorted(best):
                    bp = list(strokes[j][0][::-1] if rev else strokes[j][0])
                    bw = list(strokes[j][1][::-1] if rev else strokes[j][1])
                    if joins_cleanly((pts[-2:], wid[-2:]), (bp[:2], bw[:2]), like, col):
                        pts += bp
                        wid += bw
                        left.discard(j)
                        joins += 1
                        took = True
                        break
                if not took:
                    break
            out.append(piece(pts, wid, like))
    return out + [strokes[i] for i in rest], joins


def lean(strokes, ss=SS, tol=TOL):
    """prune, chain, then simplify. -> (strokes, stats)."""
    kept, cut = prune(strokes, ss)
    joined, joins = chain(kept)
    slim, gone = simplify(joined, tol)
    return slim, dict(stats(strokes), after=stats(slim), pruned=cut, joins=joins, points_simplified=gone)


def stats(strokes):
    pts = sum(len(s[0]) for s in strokes)
    return {"strokes": len(strokes), "points": pts,
            "bytes": BYTES_STROKE * len(strokes) + BYTES_POINT * pts}


# ---------------------------------------------------------------- the worst case: a budget
MAX_STROKES = 50000   # the hard cap on strokes in one decomposition


def _lab(img):
    from paperdaemon.pipeline.decompose.reference._lazy import CV2 as cv2
    lab = cv2.cvtColor(img, cv2.COLOR_RGB2LAB).astype(np.float32)
    lab[..., 0] *= 100.0 / 255.0
    lab[..., 1:] -= 128.0
    return lab


def importance(rgb, fine=1.5, around=12.0):
    """THE RANKING: per pixel, how much the small detail there matters (small details on a large
    otherwise unbusy picture still come through, but a picture with MANY small details begins
    to average smaller details out).

        detail      how far the pixel's color is from its surroundings at the `fine` scale (Lab, about dE)
        busy        the typical detail in its neighborhood, `around` px
        importance  detail * detail / busy: strong, AND standing out from what is around it

    A lone window in a calm wall: high detail, low busy, so high. One dab among thousands: detail about
    equal to busy, so no more than its own strength. A spire through brushwork: far stronger than the
    brushwork, so high. -> (importance, busy), float32 arrays the size of the picture."""
    from paperdaemon.pipeline.decompose.reference._lazy import CV2 as cv2
    lab = _lab(np.asarray(rgb, np.uint8))
    d = np.sqrt(((lab - cv2.GaussianBlur(lab, (0, 0), fine)) ** 2).sum(axis=2))
    d = cv2.GaussianBlur(d, (0, 0), 1.0)                       # a detail, not a pixel
    busy = cv2.GaussianBlur(d, (0, 0), around)
    return d * d / (busy + 1.0), busy


def average(rgb, strength, ranked=True, imp=None):
    """The picture with its small details averaged into their surroundings; `strength` 0..1.

    The averaged version is a mean-shift flattening -- flat patches with crisp borders, which is what the
    decomposer draws in the fewest strokes -- wider and more tolerant as `strength` rises.
      ranked=True   it replaces the original only where the ranking says: importance under the cut, in a
                    neighborhood busy enough to have details to spare. Whatever ranks above the cut is
                    kept as it is, with a 2 px margin, so a thin line is never thinned by its neighbors.
      ranked=False  everywhere alike: the comparison, not the rule.
    strength 0 returns the picture as it is. -> uint8 RGB array."""
    from paperdaemon.pipeline.decompose.reference._lazy import CV2 as cv2
    img = np.asarray(rgb, np.uint8)
    if strength <= 0:
        return img.copy()
    sp, sr = 4 + 16 * strength, 8 + 40 * strength
    flat = cv2.pyrMeanShiftFiltering(img, sp, sr, maxLevel=1)
    if not ranked:
        return flat
    imp, busy = importance(img) if imp is None else imp
    cut = 2.0 + 400.0 * strength ** 2
    go = 1.0 - np.clip((imp - 0.5 * cut) / cut, 0.0, 1.0)     # all of it under cut/2, none over 1.5 cut
    go *= np.clip((busy - 1.5) / 3.0, 0.0, 1.0)               # a calm neighborhood has nothing to spare
    keep = cv2.dilate((1.0 - go).astype(np.float32), cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (5, 5)))
    w = (1.0 - cv2.GaussianBlur(keep, (0, 0), 1.0))[..., None]
    return np.clip(img * (1.0 - w) + flat * w, 0, 255).astype(np.uint8)


def _lstar(rgb):
    """CIE L* of an sRGB color (0-255 per channel)."""
    lin = [((c / 255.0 + 0.055) / 1.055) ** 2.4 if c / 255.0 > 0.04045 else (c / 255.0) / 12.92 for c in rgb[:3]]
    y = 0.2126 * lin[0] + 0.7152 * lin[1] + 0.0722 * lin[2]
    return 116.0 * (y ** (1.0 / 3.0) if y > 0.008856 else 7.787 * y + 16.0 / 116.0) - 16.0


def render(strokes, box, scale=1.0):
    """A stroke list drawn as rm_render.render composites a page (file order; pens opaque; each run of a
    wash color one per-channel-minimum layer), cropped to `box` = (x0, y0, x1, y1) in page px."""
    x0, y0, x1, y1 = box
    W, H = int(round((x1 - x0) * scale)), int(round((y1 - y0) * scale))
    canvas = Image.new("RGB", (W, H), "white")
    st = {"canvas": canvas, "d": ImageDraw.Draw(canvas), "pending": None}

    def flush():
        """One run of a wash color onto the canvas, as a per-channel minimum where its mask says."""
        if st["pending"] is None:
            return
        rgb, mask = st["pending"][0], st["pending"][1]
        if isinstance(rgb, tuple) and rgb and rgb[0] == "pencil":
            # opacity toward the pencil's color: canvas * (1 - a) + color * a
            a = mask[..., None]
            base = np.asarray(st["canvas"]).astype(np.float32)
            colr = np.asarray(rgb[1], np.float32).reshape(1, 1, 3)
            st["canvas"] = Image.fromarray(np.clip(base * (1.0 - a) + colr * a + 0.5, 0, 255).astype(np.uint8))
            st["d"] = ImageDraw.Draw(st["canvas"])
            st["pending"] = None
            return
        if isinstance(mask, np.ndarray):
            mask = Image.fromarray(mask * np.uint8(255))
        if BLACK_POINT_L is not None and _lstar(rgb) < BLACK_POINT_L:
            rgb = (0, 0, 0)
        dark = ImageChops.darker(st["canvas"], Image.new("RGB", st["canvas"].size, rgb))
        st["canvas"] = Image.composite(dark, st["canvas"], mask)
        st["d"] = ImageDraw.Draw(st["canvas"])
        st["pending"] = None

    for s in strokes:
        if len(s[0]) < 2:
            continue
        if is_wash(s):
            rgb = _rgb(s)
            if st["pending"] is None or st["pending"][0] != rgb:
                flush()
                if FLOOR_MODEL:
                    mask = Image.new("L", (W, H), 0)
                    st["pending"] = (rgb, mask, ImageDraw.Draw(mask))
                else:
                    st["pending"] = (rgb, np.zeros((H, W), np.uint8))
            if FLOOR_MODEL:
                k = R.WSCALE["HIGHLIGHTER"]
                R._draw(st["pending"][2], _line(s, [max(1.0, float(w) * k) * scale / k for w in s[1]]), 255,
                        [((x - x0) * scale, (y - y0) * scale) for x, y in s[0]])
            else:
                # THE DEVICE'S RULE (rm_raster): pixel centers inside the exact footprint, no floor
                RS.paint_wash(st["pending"][1], x0 * scale, y0 * scale, s[0], s[1], eps=WASH_EPS, scale=scale)
        elif is_grain(s):
            # THE PENCIL, as the device draws it (rm_raster.paint_pencil): an opaque, soft-edged, grainy band that
            # DARKENS whatever is under it. rm_render._stipple scattered light dots over the wash instead, which
            # rendered the hatch shading badly: it looks right on the tablet and wrong in the renders.
            # One opacity canvas per run of pencil color, composited at the flush.
            col = R.ENUM_WRITER.get(getattr(s[3], "value", 0), (0, 0, 0))
            if st["pending"] is None or st["pending"][0] != ("pencil", col):
                flush()
                st["pending"] = (("pencil", col), np.zeros((H, W), np.float32))
            RS.paint_pencil(st["pending"][1], x0 * scale, y0 * scale, s[0], s[1], scale=scale,
                            seed=int(abs(s[0][0][0]) * 7919 + abs(s[0][0][1])))
        else:
            flush()
            k = R.WSCALE.get(_fam(s[2]), R.WSCALE_WRITER)
            widths = [max(1.0, float(w) * k) * scale / k for w in s[1]]       # pens: PIL, floored -- not modeled yet
            pts = [((x - x0) * scale, (y - y0) * scale) for x, y in s[0]]
            R._draw(st["d"], _line(s, widths), R.ENUM_WRITER.get(getattr(s[3], "value", 0), (0, 0, 0)), pts)
    flush()
    return st["canvas"]


def compare(a, b):
    """Two renders -> how far apart: share of pixels changed at all, share changed visibly (> 24 of 255
    in a channel), and the largest change."""
    d = np.abs(np.asarray(a, np.int16) - np.asarray(b, np.int16)).max(axis=2)
    return {"changed": float((d > 0).mean()), "visible": float((d > 24).mean()), "max": int(d.max())}
