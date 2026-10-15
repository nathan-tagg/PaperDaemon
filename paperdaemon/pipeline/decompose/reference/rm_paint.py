r"""Image -> reMarkable strokes AT A TARGET SIZE. The decomposer.

The per-pixel work is vectorized with numpy/scipy/numba rather than looped in Python.

The decomposer should not have a lot of "smarts", and it has no concept of a "mode". It is
focused on decomposing the image to strokes, and has to be fast and accurate
above all else. If the caller wants line art, it hands in a line art image.

So this has no modes and classifies nothing about the source. It reduces
whatever image it is handed into strokes as faithfully as the pen set allows,
and the caller controls the result by controlling the source.

WHAT IT DOES, in order (each kind of mark on the pen that makes it):

  1. Quantize to the device palette. The tablet has 14 colors; the source has
     millions. The image is reduced to a handful of dominant clusters and each
     cluster is mapped ONCE to paper / black / tone / a color pen, with a
     chroma gate so a cool gray can never become BLUE. Per-pixel mapping was
     tried first and turned a cream skull into confetti.
  2. Split every non-paper class into connected COMPONENTS and drop the specks.
  3. Draw each component by its measured THICKNESS (area / skeleton length):
        thin  -> a centerline stroke at that thickness. Fineliner if it is a
                 hairline, marker if bolder. This is what a line-art source
                 decomposes into, with no special case: its lines are thin
                 black components.
        thick -> marker scanline fill plus one outline in the same color.
  4. Achromatic mid-tones -> pencil HATCHING, density tracking darkness
     (rm_hatch, straight lines, no waver).

  There is deliberately no edge-detection pass. XDoG drew contours a photo
  does not contain and grain a photo does; the strokes here all correspond to
  ink that is actually in the source.

THE BOX COMES FIRST. Every length is in PAGE px and converted through the grid
actually used; the grid never exceeds the source (upsampling before tracing
manufactured fragment edges -- measured). Placement afterwards is translate +
rotate only; a materially different size re-decomposes from the cached source.

Fidelity has two numbers -- `color` (coarse per-channel) and `structure`
(edge-map correlation) -- to RANK variants. Judging is done by looking.

Colors: the PenColors `rm_render.ENUM` can render. PIL still loads, resamples and
quantizes; the per-pixel work is numpy / scipy / numba.
"""
import itertools
import math
import os
import sys
import time


import numpy as np
from PIL import Image, ImageChops, ImageDraw, ImageFilter, ImageOps
# OpenCV's IPP paths are switched off where OpenCV first loads (_lazy.CV2), for bit-identical runs
from rmscene.scene_items import Pen, PenColor

from paperdaemon.pipeline import draw as A
from paperdaemon.pipeline.draw import lab as _lab, preview as render, to_drawing
from paperdaemon.pipeline.page import render as R
from paperdaemon.pipeline.decompose.reference import rmb_lineart as LA
from paperdaemon.pipeline.decompose.reference import rmb_npops as N
from paperdaemon.pipeline.decompose.reference import rmb_params as K
from paperdaemon.pipeline.decompose.reference.rm_trace import place
from paperdaemon.pipeline.decompose.reference.rmb_npops import simplify
from paperdaemon.pipeline.decompose.reference.rmb_params import *              # noqa: F401,F403  every tuned constant, in one place

_W = R.WSCALE_DEFAULT


def _field(page_px):
    return max(2, int(round(page_px / _W)))


def _hl_field(page_px):
    return max(4, int(round(page_px / HL_SCALE)))


# ---------------------------------------------------------------- morphology
# PIL's rank filters replicate the edge pixel, which is what scipy's mode="nearest" does
# (verified over random masks at k = 3..13); scipy's are separable and O(n) in the kernel
# instead of O(k^2), which is why the wide closings stopped mattering. See rmb_npops.rank_ext.
def _dilate(mask, k):
    return N.img(N.rank_ext(N.view(mask), k, True))


def _erode(mask, k):
    return N.img(N.rank_ext(N.view(mask), k, False))


def _window(a, offx, offy, w, h):
    """A (h, w) window of an array whose top-left sits at (offx, offy) in it, zero
    outside -- PIL's crop semantics, which pad rather than clip."""
    out = np.zeros((h, w) + a.shape[2:], a.dtype)
    sy0, sx0 = max(0, offy), max(0, offx)
    sy1, sx1 = min(a.shape[0], offy + h), min(a.shape[1], offx + w)
    if sy1 > sy0 and sx1 > sx0:
        out[sy0 - offy:sy1 - offy, sx0 - offx:sx1 - offx] = a[sy0:sy1, sx0:sx1]
    return out


def _mean_lum(lum_a, m, off, default):
    """The mean luminance under a component mask, on the reference implementation's 0-100 scale."""
    a = N.view(m) != 0
    cnt = int(np.count_nonzero(a))
    if not cnt:
        return default
    tot = int(_window(lum_a, off[0], off[1], m.width, m.height)[a].sum())
    return (tot / cnt) * 100.0 / 255.0


def _global_px(sub, off, gw, gh):
    """Set pixels of a component-sized boolean array as (y, x) index arrays in grid
    coordinates, with anything off the grid dropped -- PIL's crop/paste clipping."""
    yy, xx = np.nonzero(sub)
    gy, gx = yy + off[1], xx + off[0]
    ok = (gx >= 0) & (gx < gw) & (gy >= 0) & (gy < gh)
    return gy[ok], gx[ok]


def _median(mask, k):
    """MedianFilter(k) on a 0/255 mask: the median of k*k binary values is the majority,
    so it is a box count against half the window -- exact, and O(n)."""
    a = N.view(mask) != 0
    r = k // 2
    p = np.pad(a, r, mode="edge").astype(np.int32)
    np.cumsum(p, axis=0, out=p)
    np.cumsum(p, axis=1, out=p)
    c = np.zeros((p.shape[0] + 1, p.shape[1] + 1), np.int32)
    c[1:, 1:] = p
    h, w = a.shape
    box = c[k:k + h, k:k + w] - c[0:h, k:k + w] - c[k:k + h, 0:w] + c[0:h, 0:w]
    return N.bool_img(2 * box > k * k)


# ---------------------------------------------------------------- color
def _hl_mix(combo):
    """The color of a stack of highlighter washes: per-channel minimum (measured)."""
    return tuple(min(HL_RGBA[k][i] for k in combo) for i in range(3))


def _tc_key(rgb):
    """A cluster's own color as a class key, rounded to TC_QUANT levels a channel so that two
    neighboring clusters of the same paint end up in the same class."""
    q = max(2, int(K.TC_QUANT))
    step = 255.0 / (q - 1)
    return tuple(int(round(round(c / step) * step)) for c in rgb)


def _fill_rgba(key):
    """The rgba a wash key paints with: a true-color ("rgb", (r,g,b)) key paints itself; a classic
    ("hl", letters) key is the min() of its letters, which is what the device composites."""
    if key[0] == "rgb":
        return tuple(key[1])
    return _hl_mix(key[1]) if len(key[1]) > 1 else HL_RGBA[key[1]]


def _hatch_pen(rgb_small, region):
    """The pen a hatch over `region` is drawn with: BLACK where the region is achromatic, and
    otherwise the nearest of the eleven enum pen colors to the region's own mean hue -- so the
    shading darkens the fill instead of obliterating it (see HATCH_IN_COLOR)."""
    sel = N.view(region) != 0
    if not sel.any():
        return PenColor.BLACK
    mean = rgb_small[sel].mean(axis=0)
    L_, a_, b_ = _lab(tuple(float(v) for v in mean))
    if math.hypot(a_, b_) < K.HATCH_COLOR_MIN_CHROMA:
        return PenColor.BLACK
    return min(_PEN_LAB, key=lambda e: (e[1][1] - a_) ** 2 + (e[1][2] - b_) ** 2)[0]


def _kname(k):
    """A color class as a string: 'pen:BLUE', 'hl:OM', or the achromatic names."""
    if isinstance(k, tuple):
        if k[0] == "rgb":
            return "rgb:%02x%02x%02x" % tuple(k[1])
        return "%s:%s" % (k[0], getattr(k[1], "name", k[1]))
    return getattr(k, "name", k)


# Every color a REGION can be painted: an opaque marker pen, or a wash of 1..HL_MAX_LAYERS
# highlighter colors. A chromatic cluster takes the nearest of these in Lab -- lightness
# included, because a wash and a pen of the same hue are different lightnesses on the page.
_FILL_ENTRIES = [(("pen", c), PEN_RGB[c]) for c in CHROMATIC]
for _n in range(1, HL_MAX_LAYERS + 1):
    for _combo in itertools.combinations("OYGBMK", _n):
        if _combo != ("K",):
            _FILL_ENTRIES.append((("hl", "".join(_combo)), _hl_mix(_combo)))
_FILL_RGB = dict(_FILL_ENTRIES)
_FILL_RGB[("hl", "K")] = HL_RGBA["K"]                    # paintable (UI mode: a black button under a black label), never classified
_FILL_LAB = [(key, _lab(rgb)) for key, rgb in _FILL_ENTRIES]
_PEN_LAB = [(c, _lab(PEN_RGB[c])) for c in CHROMATIC]


def _line_pen(color):
    """The pen a LINE of this class is drawn with: a pen class is itself; a wash class takes
    the nearest pen to the wash's color (lines cannot be washes)."""
    if not isinstance(color, tuple):
        return color
    if color[0] == "pen":
        return color[1]
    L, a, b = _lab(_FILL_RGB[color])
    return min(_PEN_LAB, key=lambda e: (e[1][0] - L) ** 2 + (e[1][1] - a) ** 2 + (e[1][2] - b) ** 2)[0]


_SKIN_HUE_OFFSET = 0.0      # degrees, set per picture by decompose() from skin_cast_offset(); 0 = no cast correction
_DARK_FIELD = False         # set per picture by dark_field(); False = dark is black
_FLOW = None                # (tx, ty, coherence) at grid resolution, set per picture; None = rows
_UP = 1.0                   # GRID PX PER SOURCE PX: the pre-decomp upscale (1.0 = grid is the source)


def _gu(v):
    """A length that was written in grid px when the grid WAS the source, in today's grid px.
    Everything geometric in this file is one of three kinds: a page length (divided by ppg, and
    already correct), a ratio (already correct), or one of these."""
    return v * _UP


def _ker(px=1.0):
    """An odd structuring-element size for a radius of `px` SOURCE px."""
    return 2 * max(1, int(round(px * _UP))) + 1


def _flow_window(offx, offy, w, h):
    """The flow field over a component's padded window, in the window's own coordinates. The window
    can start outside the grid (the fill painters pad their crops), so the edge is replicated."""
    tx, ty, coh = _FLOW
    gh, gw = tx.shape
    ys = np.clip(np.arange(offy, offy + h), 0, gh - 1)
    xs = np.clip(np.arange(offx, offx + w), 0, gw - 1)
    ix = np.ix_(ys, xs)
    return tx[ix], ty[ix], coh[ix]


def _flow_rows(core, offx, offy, pitch, min_len=None, cov_r=None):
    """The streamlines that replace a fill's horizontal rows: same spacing, along the form.
    Returns point lists in the CALLER's coordinates (i.e. already offset), or None to use rows.

    THE FORM PASS CANNOT GAP. Whatever the streamlines did not reach is painted with the rows
    they replaced, at the same pitch, so the caller's coverage bookkeeping stays true.
    `cov_r` is the stroke's half-width in grid px (default: the pitch, which is what the marker
    rows are); FLOW_COV_SLACK shrinks it so the repair errs towards overlap."""
    if _FLOW is None or not K.V69_FLOW_FILL:
        return None
    from paperdaemon.pipeline.decompose.reference import rm_flow as FL
    a = N.view(core) != 0
    if not a.any():
        return []
    tx, ty, coh = _flow_window(offx, offy, core.width, core.height)
    if K.FLOW_SHAPE_FALLBACK:
        # WHERE THE PICTURE SAYS NOTHING, THE SHAPE DOES. An incoherent pixel used to take a fixed
        # 38 degrees, which is the old hatch -- so a flat fill's "form strokes" were diagonals.
        sx, sy = FL.shape_field(a, K.FLOW_SHAPE_SMOOTH)
        weak = coh < K.FLOW_MIN_COHERENCE
        tx = np.where(weak, sx, tx)
        ty = np.where(weak, sy, ty)
    lines = FL.streamlines(a, tx, ty, float(pitch) * max(1.0, K.FLOW_FILL_OPEN),
                           float(min_len if min_len is not None else _gu(K.FLOW_FILL_MIN_LEN_G)))
    out = [[(x + offx, y + offy) for x, y in ln] for ln in lines]
    if not K.FLOW_FILL_REPAIR:
        return out
    h_, w_ = a.shape
    seen = np.zeros((h_, w_), bool)
    for ln in lines:
        for i in range(len(ln) - 1):
            x0, y0 = ln[i]
            x1, y1 = ln[i + 1]
            n_ = max(1, int(math.ceil(math.hypot(x1 - x0, y1 - y0) * 2.0)))
            for j in range(n_ + 1):
                u = j / float(n_)
                xi = int(round(x0 + (x1 - x0) * u))
                yi = int(round(y0 + (y1 - y0) * u))
                if 0 <= xi < w_ and 0 <= yi < h_:
                    seen[yi, xi] = True
    if seen.any():
        r_ = max(1, int(round(float(cov_r if cov_r is not None else pitch) * K.FLOW_COV_SLACK)))
        seen = N.view(_dilate(N.bool_img(seen), 2 * r_ + 1)) != 0
    miss = a & ~seen
    if miss.any():
        step_ = max(1, int(round(pitch)))
        out.extend(_row_lines(N.bool_img(miss), offx, offy, np.arange((-offy) % step_, h_, step_)))
    return out


_WHITE_FLOOR = None         # (L, a, b) of the picture's paper-colored ground, or None


def white_floor(small):
    """The picture's own GROUND, if it has a paper-colored one -> (L, a, b), else None.

    Read off a border ring: a white page that has been through a warm filter, a scan, or a
    generator's color cast still has that tint at all four edges, and uniformly. A painting with a
    dark or busy border fails the test and nothing is floored. This exists because color is the
    base layer now: without it a cream page paints cream from corner to corner.
    """
    if not K.WHITE_FLOOR_ON:
        return None
    a = np.asarray(small.convert("RGB"), np.uint8)
    h, w = a.shape[:2]
    r = max(2, int(round(min(h, w) * K.WHITE_FLOOR_RING)))
    edges = [a[:r], a[-r:], a[:, :r], a[:, -r:]]
    ring = np.concatenate([e.reshape(-1, 3) for e in edges])
    lab = _lab_rows(ring)
    L, A, B = lab[:, 0], lab[:, 1], lab[:, 2]
    L0, a0, b0 = float(np.median(L)), float(np.median(A)), float(np.median(B))
    # 1. near-neutral and light: a ground, not a color
    if L0 < K.WHITE_FLOOR_MIN_L or math.hypot(a0, b0) > K.WHITE_FLOOR_MAX_C:
        return None
    # 2. every edge agrees -- a sky at the top with land at the bottom is not a ground
    for e in edges:
        el = _lab_rows(e.reshape(-1, 3))
        d = math.sqrt((float(np.median(el[:, 0])) - L0) ** 2 + (float(np.median(el[:, 1])) - a0) ** 2
                      + (float(np.median(el[:, 2])) - b0) ** 2)
        if d > K.WHITE_FLOOR_EDGE_TOL:
            return None
    # 3. the ring is uniform, not a busy border that happens to average pale
    near = (np.abs(L - L0) <= K.WHITE_FLOOR_TOL_L * 2) & (np.hypot(A - a0, B - b0) <= K.WHITE_FLOOR_TOL_C)
    if float(near.mean()) < K.WHITE_FLOOR_UNIFORM:
        return None
    # 4. it is the lightest thing in the picture -- a pale subject color has highlights above it
    whole = _lab_rows(a.reshape(-1, 3))[:, 0]
    if L0 < float(np.percentile(whole, K.WHITE_FLOOR_TOP_PCT)) - K.WHITE_FLOOR_TOP_SLACK:
        return None
    # 5. something is actually drawn on it
    if float((whole < 45.0).mean()) < K.WHITE_FLOOR_MIN_INK:
        return None
    return (L0, a0, b0)


def white_point(small):
    """Optional white-point pass. Stretch the picture's own lightness range onto the page's, hue and
    chroma untouched -- because on paper the PAPER IS THE BRIGHTEST INK THERE IS.

    PAPER_L is an absolute 92 and a painting's brightest tone is often L* 80: measured over seven
    paintings, paper coverage is 0.0% and 61-73% of every picture classifies as "tone", which is why
    the hatch covers everything and why the whites of an eye (L* 78 there) come out as a flesh wash.
    Rated white-ground sources already reach 100 and 0, so for 30 of the 33 this is the identity.
    """
    rgb = np.asarray(small.convert("RGB"), np.uint8).reshape(-1, 3)
    lab = _lab_rows(rgb)
    L = lab[:, 0]
    lo, hi = float(np.percentile(L, K.WP_LO_PCT)), float(np.percentile(L, K.WP_HI_PCT))
    if hi >= 97.0 or hi < K.WP_MIN_SPAN:
        return small, dict(lo=round(lo, 1), hi=round(hi, 1), gain=1.0)
    # PURE GAIN: the picture's lightest tone lands on paper and black stays black. Subtracting the
    # picture's black point as well moved every mid-tone too, which corrected the space even in
    # non-white areas (a tonal chess picture showed it) and normalized some places out.
    gain = min(K.WP_MAX_GAIN, 100.0 / max(hi, 1e-6))
    off = 0.0
    if abs(gain - 1.0) < 0.02 and abs(off) < 1.0:
        return small, dict(lo=round(lo, 1), hi=round(hi, 1), gain=1.0)
    L2 = np.clip(L * gain + off, 0.0, 100.0)
    out = _lab_to_rgb8(L2, lab[:, 1], lab[:, 2]).reshape(small.height, small.width, 3)
    return Image.fromarray(out, "RGB"), dict(lo=round(lo, 1), hi=round(hi, 1), gain=round(gain, 3))


def _lab_to_rgb8(L, a, b):
    """Lab -> sRGB uint8, the inverse of _lab_rows (D65, same matrices)."""
    fy = (L + 16.0) / 116.0
    fx, fz = fy + a / 500.0, fy - b / 200.0
    def finv(f):
        f3 = f ** 3
        return np.where(f3 > 0.008856, f3, (f - 16.0 / 116.0) / 7.787)
    X, Y, Z = finv(fx) * 0.95047, finv(fy), finv(fz) * 1.08883
    r = 3.2404542 * X - 1.5371385 * Y - 0.4985314 * Z
    g = -0.9692660 * X + 1.8760108 * Y + 0.0415560 * Z
    bb = 0.0556434 * X - 0.2040259 * Y + 1.0572252 * Z
    v = np.clip(np.stack([r, g, bb], axis=-1), 0.0, 1.0)
    v = np.where(v <= 0.0031308, 12.92 * v, 1.055 * np.power(v, 1 / 2.4) - 0.055)
    return np.clip(v * 255.0 + 0.5, 0, 255).astype(np.uint8)


def dark_field(small):
    """Does this picture have a DARK FIELD -- a ground, a night, a black backdrop -- as opposed to
    dark OUTLINES on light paper? Read off the pixels, before anything is classified.

    This arms the dark-color rules. Without it they fire on a flat illustration's anti-aliased
    outlines, whose pixels are tinted by whatever they border, and a clean black outline becomes a
    hatched wash (measured on flat-cactus). Area is what separates the two cases, by two orders of
    magnitude, so the test is: enough of the picture is dark, and its largest dark mass is big.
    """
    L = _lab_rows(np.asarray(small.convert("RGB"), np.uint8).reshape(-1, 3))[:, 0]
    share = float((L < BLACK_L).mean())
    if share < K.DARK_FIELD_MIN_COVER:
        return False, share, 0.0
    mask = N.bool_img((L < BLACK_L).reshape(small.height, small.width))
    comps = components(mask, 2)
    big = (comps[0][0] / float(small.width * small.height)) if comps else 0.0
    return bool(big >= K.DARK_FIELD_MIN_REGION), share, big


def skin_cast_offset(small):
    """The hue offset (degrees) the flesh gate subtracts for THIS picture, and the cast it saw.

    The cast is the median (a*, b*) of the near-neutral pixels (chroma < 12, L* 25-92). Below
    SKIN_CAST_DEADBAND nothing happens -- that is where klein's pictures sit. Above it, the offset
    is the hue shift such a cast induces on a flesh pixel of the warm wedge's typical chroma, so a
    Qwen face at 70 deg is judged as the 55 deg it would be without the cast. Nothing about the
    picture itself changes: same washes, same lines, same ground.
    """
    if not K.SKIN_CAST_ON:
        return 0.0, (0.0, 0.0)
    rgb = np.asarray(small.convert("RGB"), np.uint8).reshape(-1, 3)
    lab = _lab_rows(rgb)
    L, a, b = lab[:, 0], lab[:, 1], lab[:, 2]
    C = np.hypot(a, b)
    neutral = (C < 12.0) & (L > 25.0) & (L < 92.0)
    if neutral.mean() < 0.005:
        neutral = (C < 25.0) & (L > 20.0)
    if not neutral.any():
        return 0.0, (0.0, 0.0)
    da, db = float(np.median(a[neutral])), float(np.median(b[neutral]))
    mag = math.hypot(da, db)
    if mag < K.SKIN_CAST_DEADBAND:
        return 0.0, (da, db)
    with np.errstate(divide="ignore", invalid="ignore"):
        h = np.degrees(np.arctan2(b, a)) % 360.0
    wedge = (h >= 15.0) & (h <= 95.0) & (C >= 10.0) & (C <= 50.0) & (L >= 30.0) & (L <= 88.0)
    c_ref = float(np.median(C[wedge])) if int(wedge.sum()) > 50 else 25.0
    theta, h_ref = math.atan2(db, da), math.radians(K.SKIN_CAST_REF_HUE)
    delta = math.degrees(math.atan2(mag * math.sin(theta - h_ref), c_ref + mag * math.cos(theta - h_ref)))
    return max(-K.SKIN_CAST_MAX_DEG, min(K.SKIN_CAST_MAX_DEG, delta)), (da, db)


def _skin_key(L, a, b, chroma):
    """Is this flesh, and if so which class? -> a class key, or None.

    A face is not one color, it is a family: the same warm hue running from a lit cheek to a shadowed
    jaw. The general classifier judges every patch on its own, so a single face came back as bands of
    RED, salmon, tan and gray, with colors all over the place. This puts the whole family
    on ONE wash and lets the hatch carry the modeling, which is the same principle the rest of the
    painter already follows: color is the base layer, shading is drawn over it.
    """
    if not SKIN_COHERENT:
        return None
    if L < SKIN_L_MIN or chroma < SKIN_CHROMA_MIN or chroma > SKIN_CHROMA_MAX:
        return None
    # the hue is judged with the picture's cast taken out (chroma is not touched)
    h = math.degrees(math.atan2(b, a)) - _SKIN_HUE_OFFSET
    if _SKIN_HUE_OFFSET:
        a, b = chroma * math.cos(math.radians(h)), chroma * math.sin(math.radians(h))
    if b <= 0.0 or not (SKIN_HUE_LO <= h <= SKIN_HUE_HI):
        return None
    if a / b < SKIN_AB_MIN or chroma / L > SKIN_CL_MAX:
        return None                                   # a warm OBJECT: wood, sand, stone, fur, brick, rust
    return SKIN_WASH if L >= SKIN_BASE_L else ("base", SKIN_WASH)


def classify(rgb, black_l=BLACK_L, chroma_min=CHROMA_MIN):
    """One cluster color -> its class. THE ONLY LADDER.

    A highlighter takes any rgba (measured on the tablet), so a region is painted its
    own color and there is no palette to search. Top to bottom:

        paper   the color the page already is, and nothing else
        black   the ink core: the only thing that may be FILLED with marker
        tone    a line's anti-aliased ramp: drawn as a line, never filled

    INK IS NEUTRAL. A fixed chroma cap cannot say that on its own, because chroma shrinks with
    lightness: an art nouveau panel's corners are a warm dark field at L* 12 with chroma 8 -- plainly a
    color -- and the same chroma at L* 70 is a gray. So the ink rungs also require the color to
    be unsaturated FOR ITS DARKNESS (chroma <= INK_SAT x L), or neutral outright (INK_NEUTRAL --
    without that floor pure black, at L* 0, fails any multiplicative test). Without it 83% of every corner of that
    painting was classed `tone`, which collapsed the field and the gold scrollwork inside it into
    one mass and washed the lot.
        base    a gray: washed its own color, and shaded over
        rgb     everything else: washed its own color
    """
    L, a, b = _lab(rgb)
    chroma = math.hypot(a, b)
    if _WHITE_FLOOR is not None:
        L0, a0, b0 = _WHITE_FLOOR
        if L >= L0 - K.WHITE_FLOOR_TOL_L and math.hypot(a - a0, b - b0) <= K.WHITE_FLOOR_TOL_C:
            return "paper"          # only when WHITE_FLOOR_ON, which is off
    if L >= K.TC_PAPER_L and chroma < K.TC_PAPER_CHROMA:
        return "paper"
    if chroma < K.TC_INK_CHROMA and (chroma <= K.INK_NEUTRAL or chroma <= K.INK_SAT * L):
        if L < black_l and chroma < K.BLACK_CHROMA:
            return "black"
        if L < K.TC_INK_L:
            # the ramp beside a line belongs to the line; a dark area that is a REGION is washed
            # by the tone-region pass, so washing all of it here would fatten every line by its
            # own halo (the violin came out three times as heavy)
            return ("base", ("rgb", _tc_key(rgb))) if K.DARK_GRAY_WASHED else "tone"
    if chroma < chroma_min:
        return ("base", ("rgb", _tc_key(rgb)))
    return ("rgb", _tc_key(rgb))


_SRGB_LUT = None


def _sq(x):
    """`x ** 2` as CPython computes it.

    CPython's `x ** 2` is `pow(x, 2.0)` from libm, and on this platform that is NOT always
    `x * x`: they differ by one ulp on about 1 value in 2000 (measured).
    numpy's `x ** 2`, `np.square` and `np.power(x, 2)` all multiply; `np.float_power(x, 2.0)`
    goes to libm and matches CPython exactly over 400k values. Every Lab distance the
    reference implementation writes with `** 2` therefore uses this, so a color can never be classified differently.
    """
    return np.float_power(x, 2.0)


def _lab_rows(rgb):
    """`_lab` over an (n, 3) uint8 array -> (n, 3) float64.

    The sRGB transfer function is tabulated over its 256 integer inputs with CPython's own
    arithmetic, so the only transcendental left is the cube root -- and numpy's agrees with
    Python's bit for bit here (400k values checked). CHROMA IS NOT DONE HERE: math.hypot is
    correctly rounded and np.hypot is not, and they differ in the last ulp on a sixth of all
    inputs -- which would reorder a `sort(key=-chroma)` and pick a different pen.
    """
    global _SRGB_LUT
    if _SRGB_LUT is None:
        def f(c):
            c /= 255.0
            return c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4
        _SRGB_LUT = np.array([f(float(v)) for v in range(256)], np.float64)
    v = _SRGB_LUT[np.asarray(rgb, np.uint8)]
    r, g, b = v[:, 0], v[:, 1], v[:, 2]
    x = (0.4124 * r + 0.3576 * g + 0.1805 * b) / 0.95047
    y = (0.2126 * r + 0.7152 * g + 0.0722 * b)
    z = (0.0193 * r + 0.1192 * g + 0.9505 * b) / 1.08883

    def g_(t):
        return np.where(t > 0.008856, np.abs(t) ** (1 / 3.0), 7.787 * t + 16 / 116.0)

    fx, fy, fz = g_(x), g_(y), g_(z)
    return np.stack([116 * fy - 16, 500 * (fx - fy), 200 * (fy - fz)], axis=1)


def _rgb_rows(lab):
    """The inverse of `_lab_rows`: (n, 3) Lab -> (n, 3) uint8 sRGB, clipped to the cube. Needed
    only to put a chroma-clamped palette entry back into a color the wash can be given."""
    L, a, b = lab[:, 0], lab[:, 1], lab[:, 2]
    fy = (L + 16.0) / 116.0
    fx, fz = fy + a / 500.0, fy - b / 200.0

    def inv(t):
        return np.where(t ** 3 > 0.008856, t ** 3, (t - 16 / 116.0) / 7.787)

    x, y, z = inv(fx) * 0.95047, inv(fy), inv(fz) * 1.08883
    r = 3.2406 * x - 1.5372 * y - 0.4986 * z
    g = -0.9689 * x + 1.8758 * y + 0.0415 * z
    bl = 0.0557 * x - 0.2040 * y + 1.0570 * z

    def enc(c):
        c = np.clip(c, 0.0, 1.0)
        return np.where(c <= 0.0031308, c * 12.92, 1.055 * np.power(c, 1 / 2.4) - 0.055)

    return np.clip(np.stack([enc(r), enc(g), enc(bl)], axis=1) * 255.0 + 0.5, 0, 255).astype(np.uint8)


def classify_many(rgb, black_l=BLACK_L, chroma_min=CHROMA_MIN):
    """`classify` over an (n, 3) uint8 array -> list of n class keys, same rules and the
    same first-wins tie-breaking (np.argmin takes the first minimum, as min() does)."""
    lab = _lab_rows(rgb)
    L, a, b = lab[:, 0], lab[:, 1], lab[:, 2]
    chroma = np.array([math.hypot(x, y) for x, y in zip(a.tolist(), b.tolist())], np.float64)
    # the nearest-of-29-fixed-washes search that used to live here is GONE: a region paints its
    # own color, so there is nothing to search and nothing to prefer.
    paper = (L >= K.TC_PAPER_L) & (chroma < K.TC_PAPER_CHROMA)
    out = []
    if _WHITE_FLOOR is not None:
        L0, a0, b0 = _WHITE_FLOOR
        ground = (L >= L0 - K.WHITE_FLOOR_TOL_L) & (np.hypot(a - a0, b - b0) <= K.WHITE_FLOOR_TOL_C)
    else:
        ground = np.zeros(len(L), bool)
    for i in range(len(L)):
        if paper[i] or ground[i]:
            out.append("paper")
        elif (chroma[i] < K.TC_INK_CHROMA and (chroma[i] <= K.INK_NEUTRAL or chroma[i] <= K.INK_SAT * L[i])
              and L[i] < black_l and chroma[i] < K.BLACK_CHROMA):
            out.append("black")
        elif (chroma[i] < K.TC_INK_CHROMA and (chroma[i] <= K.INK_NEUTRAL or chroma[i] <= K.INK_SAT * L[i])
              and L[i] < K.TC_INK_L):
            out.append(("base", ("rgb", _tc_key(tuple(int(v) for v in rgb[i]))))
                       if K.DARK_GRAY_WASHED else "tone")
        elif chroma[i] < chroma_min:
            out.append(("base", ("rgb", _tc_key(tuple(int(v) for v in rgb[i])))))
        else:
            out.append(("rgb", _tc_key(tuple(int(v) for v in rgb[i]))))
    return out, chroma


def _box_sum(a, r):
    """Sum over every (2r+1)^2 window, via a summed-area table."""
    h, w = a.shape
    s = np.zeros((h + 1, w + 1), np.float32)
    np.cumsum(np.cumsum(a, axis=0, dtype=np.float32), axis=1, out=s[1:, 1:])
    y0 = np.clip(np.arange(h) - r, 0, h)
    y1 = np.clip(np.arange(h) + r + 1, 0, h)
    x0 = np.clip(np.arange(w) - r, 0, w)
    x1 = np.clip(np.arange(w) + r + 1, 0, w)
    return (s[np.ix_(y1, x1)] - s[np.ix_(y0, x1)] - s[np.ix_(y1, x0)] + s[np.ix_(y0, x0)])


def _mode_filter(lab, n, r):
    """The majority label in each (2r+1)^2 window -- a CEL PASS FOR COLOR.

    A cel shader helps identify the fill zones. The hatch has one (cel_regions: blur, posterise,
    drop small components). Color needs one too: it is median-cut per pixel, so a textured area -- a beard, foliage, fabric --
    shatters into hundreds of slivers, each below the component floor, each then dropped. That is
    why a hatched beard had no fill behind it and why the wash came out as a mesh of thin lines.

    A mode filter is the right tool rather than dropping small components, because every pixel
    still ends up with a label: confetti is absorbed into the zone around it instead of becoming a
    hole. Computed as an argmax over each label's box-filtered indicator, so it costs one summed
    -area table per cluster and no per-pixel Python.
    """
    h, w = lab.shape
    best = np.zeros((h, w), np.float32)
    out = lab.copy()
    from scipy.ndimage import uniform_filter
    k = 2 * r + 1
    for i in range(n):
        # scipy's separable box filter rather than a summed-area table per label: same answer, and
        # on a painting this pass was 3.5 of 15 seconds
        c = uniform_filter((lab == i).astype(np.float32), size=k, mode="constant")
        m = c > best
        if m.any():
            best[m] = c[m]
            out[m] = i
    return out


def _device_lab(lab):
    """Source Lab -> roughly what the PANEL will show, for use as a distance only.

    The Paper Pro is reMarkable's "Canvas Color display (based on E Ink
    Gallery 3)" -- an ACeP panel, four pigments per pixel, no color filter array. The only
    measurement of it that exists is a public photographic one of its nine pen colors, and from
    those values: white sits at L* 69, black at L* 30, so the whole tonal range is 39 L* units, and
    the most saturated thing the panel produces is C* ~= 30, about a quarter to a third of the
    corresponding sRGB primary. Red renders as a dusty rose; deep blue and saturated red are simply
    not reachable.

    So two source colors that differ only above that ceiling are the SAME color on the page, and
    a lightness difference counts for less than the source says. Compressing into the panel's box
    before measuring the distance is what makes the merge agree with what is actually seen.
    """
    out = np.array(lab, np.float64, copy=True)
    # LIGHTNESS IS NOT COMPRESSED HERE, though the panel's range is only 39 L* wide. The eye adapts
    # to the panel's own white, so the range maps onto the whole of perception; squeezing it made a
    # 12 dE step worth 31 L* of source, which merged every dark gray into black and turned a
    # bicycle's background, a portrait's backdrop and a castle's ground into solid slabs.
    C = np.hypot(out[:, 1], out[:, 2])
    over = C > K.DEV_CHROMA_CEIL
    if over.any():
        k = np.ones_like(C)
        k[over] = K.DEV_CHROMA_CEIL / C[over]
        out[:, 1] *= k
        out[:, 2] *= k
    return out


def _cel_palette(ucols, inv, de, chroma_max=None):
    """CEL-SHADE TO WHAT THE DEVICE CAN ACTUALLY SHOW.

    Cel shade to the tablet's color accuracy, or slightly below it, and then use line art, edge
    detection, wash filling and hatch shading accordingly.

    Median cut gives 64 clusters chosen to minimize RGB error, and many of them are colors the
    panel cannot tell apart -- which is how a beard or a leaf canopy ends up as forty interleaved
    zones, each too small to paint, instead of three. This merges any cluster within `de` of a
    bigger one (leader clustering in Lab, biggest first, so the merged color is the one that
    actually covers area), and optionally pulls chroma down to what the display can reach.

    The result is FEWER, BIGGER ZONES, which is what every later stage wants: the wash gets regions
    worth a spiral, edge detection gets real boundaries, and the hatch gets something to shade.
    """
    counts = np.bincount(inv, minlength=len(ucols)).astype(np.int64)
    lab = _lab_rows(ucols)
    # the distance is measured in DEVICE space, not source space: two colors the panel renders the
    # same are the same zone however far apart sRGB thinks they are (see _device_lab)
    dlab = _device_lab(lab)
    if chroma_max:
        C = np.hypot(lab[:, 1], lab[:, 2])
        over = C > chroma_max
        if over.any():
            k = np.ones_like(C)
            k[over] = chroma_max / C[over]
            lab = lab.copy()
            lab[:, 1] *= k
            lab[:, 2] *= k
            ucols = _rgb_rows(lab)
    lead, remap = [], np.empty(len(ucols), np.int32)
    for i in np.argsort(-counts).tolist():
        if counts[i] == 0:
            remap[i] = lead[0] if lead else 0
            continue
        best, bd = -1, None
        for j in lead:
            d = math.sqrt(float((dlab[i, 0] - dlab[j, 0]) ** 2 + (dlab[i, 1] - dlab[j, 1]) ** 2
                                + (dlab[i, 2] - dlab[j, 2]) ** 2))
            if bd is None or d < bd:
                best, bd = j, d
        if bd is not None and bd <= de:
            remap[i] = best
        else:
            lead.append(i)
            remap[i] = i
    keep = sorted(set(remap.tolist()))
    idx = {k: n for n, k in enumerate(keep)}
    inv2 = np.array([idx[remap[v]] for v in range(len(ucols))], np.int32)[inv]
    return ucols[keep], inv2


def quantize(small, blur=0.0, clusters=CLUSTERS, black_l=BLACK_L, chroma_min=CHROMA_MIN, detail=1.0, exact=False, ppg=1.0):
    """-> ({class: L-mask}, coverage).

    Clusters decide only whether a pixel is CHROMATIC (and which pen). The
    black / tone split is made on each pixel's own L*, because a cluster's mean
    is not its members: on a dark portrait a cluster spanning L* 5-40 averaged
    to "black" and filled the whole face.

    The classes are built as boolean arrays rather than by a Python loop over the pixels,
    and the mask dict is then rebuilt in the reference INSERTION ORDER -- the order in which
    a raster scan first uses each class, with "tone" before the color at a `base` pixel,
    because that order becomes `color_keys` and therefore the draw order.
    """
    im = small.filter(ImageFilter.GaussianBlur(blur)) if blur else small
    # exact=True (UI mode): every pixel classified by its own color. Median cut over a mostly-white
    # screen lumped a 22-pixel yellow star into a blue cluster; flat UI color has no noise to average.
    q = im if exact else im.quantize(clusters, method=Image.Quantize.MEDIANCUT).convert("RGB")
    w, h = q.size
    rgb = np.asarray(q, np.uint8).reshape(-1, 3)
    code = (rgb[:, 0].astype(np.int32) << 16) | (rgb[:, 1].astype(np.int32) << 8) | rgb[:, 2]
    uniq, inv = np.unique(code, return_inverse=True)
    ucols = np.stack([(uniq >> 16) & 255, (uniq >> 8) & 255, uniq & 255], axis=1).astype(np.uint8)
    if K.CEL_DE > 0.0 and not exact:
        ucols, inv = _cel_palette(ucols, inv, K.CEL_DE, K.DEVICE_CHROMA_MAX)
        uniq = (ucols[:, 0].astype(np.int32) << 16) | (ucols[:, 1].astype(np.int32) << 8) | ucols[:, 2]
        rgb = ucols[inv]
    klass, uchroma = classify_many(ucols, black_l, chroma_min)
    chromatic = uchroma >= INK_CHROMA_MAX
    lum = np.asarray(small.convert("L"), np.uint8).reshape(-1).astype(np.int32)
    black_cut = int(round(black_l * 2.55))
    ink_cut = int(round(INK_L * 2.55))
    paper_cut = int(round(PAPER_L * 2.55))

    # per unique color: 0 paper, 1 base (tone + color), 2 achromatic, 3 color
    cat = np.empty(len(klass), np.int8)
    ckeys, ckey_of = [], {}
    kidx = np.full(len(klass), -1, np.int32)

    def color_slot(key):
        if key not in ckey_of:
            ckey_of[key] = len(ckeys)
            ckeys.append(key)
        return ckey_of[key]

    for i, k in enumerate(klass):
        if k == "paper":
            cat[i] = 0
        elif isinstance(k, tuple) and k[0] == "base":
            cat[i] = 1
            kidx[i] = color_slot(k[1])
        elif k in ("black", "tone"):
            cat[i] = 2
        else:
            cat[i] = 3
            kidx[i] = color_slot(k)

    # INK IS NEUTRAL FOR ITS DARKNESS -- the same test the ladder uses, needed twice below.
    uL = _lab_rows(ucols)[:, 0]
    neutral = (uchroma <= K.INK_NEUTRAL) | (uchroma <= K.INK_SAT * uL)

    if K.CEL_COLOR_R > 0:
        # CEL-SHADE THE COLOR (see _mode_filter). The cluster map is regularized, not the classes,
        # so everything downstream follows; and INK KEEPS ITS OWN CLUSTER, because a window wider
        # than a line would swallow the line.
        r_ = max(1, int(round(_gu(K.CEL_COLOR_R) / max(0.5, detail))))
        inv2 = _mode_filter(inv.reshape(h, w), len(uniq), r_).reshape(-1)
        # ...and it must not step ACROSS AN EDGE. A majority window straddling two thin dark shapes
        # fills the light gap between them with the dark majority, and a violin's tuning pegs fuse
        # into one lump. A pixel may only take a label of roughly its own lightness.
        ulum = (0.299 * ucols[:, 0] + 0.587 * ucols[:, 1] + 0.114 * ucols[:, 2])
        ok = np.abs(ulum[inv2] - lum) <= K.CEL_MODE_MAX_DL
        # "Ink keeps its own cluster" is about INK, not about darkness. Excluding every dark pixel
        # left a 200 px fox's navy outline as a DOTTED line of single pixels -- each one a slightly
        # different blend of navy into orange, so each landed in a different palette entry -- and a
        # dotted mask is drawn as a string of beads whatever the painter does with it.
        inv = np.where(((lum >= ink_cut) | ~neutral[inv]) & ok, inv2, inv)
    pcat = cat[inv]
    pkey = kidx[inv]
    under_paper = lum < paper_cut
    is_black = lum < black_cut
    m1 = (pcat == 1) & under_paper                        # base: tone AND its hue's class
    m2 = (pcat == 2) & under_paper
    m3 = pcat == 3
    tone_px = m1 | (m2 & ~is_black)
    # BLACK IS INK, AND INK IS NEUTRAL -- and this per-pixel rule is the one that decides it, not
    # the class ladder. Luminance alone is not enough: the dark brown corners of an art nouveau panel
    # (L* 7, chroma 7) came out 80% solid black marker and their color was thrown away. The device's
    # own black is L* 30; a dark brown is better served painted dark brown.
    black_px = m2 & is_black & (uchroma[inv] < K.BLACK_CHROMA)
    # a dark pixel is a line candidate whether or not it also carries a wash: `base` means BOTH.
    # SAME RULE AS THE LADDER: it is a line only if its color is neutral FOR ITS DARKNESS. A flat
    # chroma cap (INK_CHROMA_MAX) passes every dark color, because chroma shrinks with lightness --
    # which is how 15% of an art nouveau panel came to be drawn as solid black line work over a source that is
    # dark brown, rendering it (13,10,4) against (23,16,9).
    ink_px = (m2 | m1) & (lum < ink_cut) & (is_black | (~chromatic & neutral)[inv])

    def first(mask):
        i = np.argmax(mask)
        return int(i) if mask[i] else -1

    order = []                                            # (raster position * 2 + sub-order, key, pixels)
    ft, fb = first(tone_px), first(black_px)
    if ft >= 0:
        order.append((2 * ft, "tone", tone_px))
    if fb >= 0:
        order.append((2 * fb, "black", black_px))
    for j, key in enumerate(ckeys):
        sel = pkey == j
        a3, a1 = m3 & sel, m1 & sel
        f3, f1 = first(a3), first(a1)
        if f3 < 0 and f1 < 0:
            continue          # the cel pass can empty a cluster outright: it has no pixels to order by
        pos = min([p for p in (2 * f3 if f3 >= 0 else None, 2 * f1 + 1 if f1 >= 0 else None) if p is not None])
        order.append((pos, key, a3 | a1))
    order.sort(key=lambda t: t[0])

    # the 3x3 median despeckles a photograph's class masks -- and erases every line thinner than
    # 2 px: a chart's axes, a table's rules, the stems of 12-px text. At detail >= DETAIL_PRECISE
    # (the planner saying "this is a chart / a screen") keep the pixels as they are.
    # ...and it is for PHOTOGRAPHS. Above DESPECKLE_MAX_PPG one grid px is several page px, so a
    # 1-px source mark is a fat drawable stroke, not noise -- that is robot-cool's mouth, and it
    # is the whole reason the upscale appeared to "fix" it (see rmb_params).
    despeckle = detail < DETAIL_PRECISE and ppg <= K.DESPECKLE_MAX_PPG
    masks = {}
    for _pos, key, px in order:
        m = N.bool_img(px.reshape(h, w))
        masks[key] = _median(m, 3) if despeckle else m
    ink = N.bool_img(ink_px.reshape(h, w))                # ONE achromatic ink mask, decided per pixel
    masks["_ink"] = _median(ink, 3) if despeckle else ink
    area = float(w * h)
    cover = {_kname(k): round(N.count(m) / area, 3) for k, m in masks.items() if k != "_ink"}
    return masks, cover


def absorb_specks(masks, min_span_col, grid_w, gh, small=None):
    """NOTHING IS DROPPED, AND NOTHING CHANGES COLOR. A color component too small to draw is
    given to the ADJACENT ZONE WHOSE COLOR IS CLOSEST TO ITS OWN.

    The span floor was silently discarding 11.9% of a forest photograph, 9.4% of a 1024-px
    illustration and 3.9% of a large portrait -- every leaf, every hair of a beard -- and those pixels reached the page
    as bare paper. Absorbing is right; absorbing by PROXIMITY was not. A dark speck of beard next
    to a light zone took the light zone's color, so a beard whose source mean is (107, 74, 58)
    was painted at (158, 140, 132): washed out, which is the "cheapened" look. The match is made
    in Lab against the neighbors the speck actually touches, and only falls back to the nearest
    zone in space when it touches nothing.
    """
    keys = [k for k in masks if k not in ("black", "tone", "_ink")]
    if not keys:
        return {"absorbed": 0.0}
    lab_img = np.full((gh, grid_w), -1, np.int32)
    own_lab = np.full((gh, grid_w), -1, np.int32)
    weak = np.zeros((gh, grid_w), bool)
    for i, k in enumerate(keys):
        own_px = N.view(masks[k]) != 0
        own_lab[own_px] = i
        keep = np.zeros_like(own_px)
        for _area, cm, off in components(masks[k], min_span_col, K.ABSORB_MAX_AREA + 1):
            sub = N.view(cm) != 0
            y0, x0 = max(0, off[1]), max(0, off[0])
            y1, x1 = min(gh, off[1] + cm.height), min(grid_w, off[0] + cm.width)
            keep[y0:y1, x0:x1] |= sub[y0 - off[1]:y1 - off[1], x0 - off[0]:x1 - off[0]]
        lab_img[keep] = i
        weak |= own_px & ~keep
    n_weak = int(weak.sum())
    if not n_weak or not (lab_img >= 0).any():
        return {"absorbed": 0.0}
    rgb = np.asarray(small.convert("RGB"), np.uint8) if small is not None else None
    lab_all = _lab_rows(rgb.reshape(-1, 3)).reshape(gh, grid_w, 3) if rgb is not None else None
    zone_lab = np.zeros((len(keys), 3), np.float64)
    if lab_all is not None:
        for i in range(len(keys)):
            sel = lab_img == i
            if sel.any():
                zone_lab[i] = lab_all[sel].mean(axis=0)
    from scipy.ndimage import distance_transform_edt
    idx = distance_transform_edt(lab_img < 0, return_distances=False, return_indices=True)
    nearest = lab_img[tuple(idx)]
    # start from what each pixel ALREADY IS, so a speck that matches nothing keeps its own color.
    # Absorbing every small component into the nearest zone cost a portrait an eye.
    out_lab = np.where(lab_img >= 0, lab_img, own_lab)
    # per component, in ITS OWN WINDOW. Allocating a full-grid array and dilating it once per
    # speck cost minutes on a 1024-px picture with thousands of them.
    guarded_pixels = 0
    for _area, cm, off in components(N.bool_img(weak), 1, 0):
        sub = N.view(cm) != 0
        y0, x0 = max(0, off[1]), max(0, off[0])
        y1, x1 = min(gh, off[1] + cm.height), min(grid_w, off[0] + cm.width)
        if y1 <= y0 or x1 <= x0:
            continue
        w_sel = sub[y0 - off[1]:y1 - off[1], x0 - off[0]:x1 - off[0]]
        if not w_sel.any():
            continue
        py0, px0 = max(0, y0 - 2), max(0, x0 - 2)
        py1, px1 = min(gh, y1 + 2), min(grid_w, x1 + 2)
        pad_sel = np.zeros((py1 - py0, px1 - px0), bool)
        pad_sel[y0 - py0:y1 - py0, x0 - px0:x1 - px0] = w_sel
        choice = -1
        if lab_all is not None:
            own = lab_all[y0:y1, x0:x1][w_sel].mean(axis=0)
            ring = (N.view(_dilate(N.bool_img(pad_sel), 3)) != 0) & (lab_img[py0:py1, px0:px1] >= 0)
            if ring.any():
                cand = np.unique(lab_img[py0:py1, px0:px1][ring])
                d = ((zone_lab[cand] - own) ** 2).sum(axis=1)
                j = int(d.argmin())
                # SIZE decides, not color distance. Anti-aliasing between two flat zones is one to
                # three pixels wide whatever color it is; an eye is twenty across. Gating on color
                # kept the anti-aliasing as its own zone, the draw floor then skipped it, and flat
                # art came out speckled with paper -- 4.7% of a robot that is solid color in the
                # source. Anything this small IS the boundary between two zones and belongs to one
                # of them; anything bigger survives and gets drawn.
                if _area <= K.ABSORB_MAX_AREA or math.sqrt(float(d[j])) <= K.ABSORB_MAX_DE:
                    choice = int(cand[j])
        if choice < 0 and lab_all is None:
            vals = nearest[y0:y1, x0:x1][w_sel]
            vals = vals[vals >= 0]
            if vals.size:
                choice = int(np.bincount(vals).argmax())
        if choice >= 0:
            win = out_lab[y0:y1, x0:x1]
            selected = w_sel
            # Adjacent weak colors are connected for neighborhood lookup,
            # but their mean is not permission to recolor every brush mark.
            # Keep the existing tiny-speck rule. For a larger mixed-color
            # union, apply the EXISTING color-distance allowance to each
            # source sample as well as to the union mean. No new palette,
            # source smoothing, output-dependent repair, or stroke cap.
            if (_area > K.ABSORB_MAX_AREA and lab_all is not None
                    and np.unique(own_lab[y0:y1, x0:x1][w_sel]).size > 1):
                distance2 = ((lab_all[y0:y1, x0:x1] - zone_lab[choice]) ** 2).sum(axis=2)
                selected = w_sel & (distance2 <= K.ABSORB_MAX_DE ** 2)
                guarded_pixels += int((w_sel & ~selected).sum())
            win[selected] = choice
    for i, k in enumerate(keys):
        masks[k] = N.bool_img(out_lab == i)
    return {"absorbed": round(n_weak / float(grid_w * gh), 4),
            "mixed_color_pixels_preserved": guarded_pixels,
            "changed_pixels": int(np.count_nonzero(out_lab != own_lab))}


# ---------------------------------------------------------------- regions
def components(mask, min_span, min_area=0):
    """Connected components (4-neighbor) at least min_span wide or tall (and at
    least min_area pixels), largest first -- each cropped to its bbox with a 1-px
    margin, so every later pass is O(bbox) and not O(grid).

    scipy labels the blobs; the order is then forced to the reference order (a stable sort by
    -area over flood-fill discovery order, i.e. over the raster index of each blob's
    first pixel), because that order is the DRAW order. See rmb_npops.components."""
    return N.components(mask, min_span, min_area)


def _row_lines(m, offx, offy, ys=None):
    """Every horizontal run on rows `ys` as a page-bound segment in component coords:
    a single-pixel run is a 0.5-px stub at its center, a longer one spans center to
    center -- the reference `_runs` loop, hoisted out of Python."""
    a = N.view(m)
    if ys is None:
        ys = np.arange(a.shape[0])
    lines = []
    for y, x0, x1 in N.row_runs(a, ys).tolist():
        a_, b_ = (x0 + 0.25, x0 + 0.75) if x1 == x0 else (x0 + 0.5, x1 + 0.5)
        lines.append([(a_ + offx, y + 0.5 + offy), (b_ + offx, y + 0.5 + offy)])
    return lines


def _skin_px(small):
    """The flesh gate (_skin_key) over every pixel of the grid -> boolean (h, w)."""
    rgb = np.asarray(small.convert("RGB"), np.uint8).reshape(-1, 3)
    lab = _lab_rows(rgb)
    L, a, b = lab[:, 0], lab[:, 1], lab[:, 2]
    chroma = np.hypot(a, b)                       # a gate, not a sort key: the last ulp cannot matter here
    with np.errstate(divide="ignore", invalid="ignore"):
        h = np.degrees(np.arctan2(b, a)) - _SKIN_HUE_OFFSET     # the cast taken out of the hue only
        if _SKIN_HUE_OFFSET:
            a, b = chroma * np.cos(np.radians(h)), chroma * np.sin(np.radians(h))
        ok = ((L >= SKIN_L_MIN) & (chroma >= SKIN_CHROMA_MIN) & (chroma <= SKIN_CHROMA_MAX) & (b > 0.0)
              & (h >= SKIN_HUE_LO) & (h <= SKIN_HUE_HI)
              & (a / np.where(b == 0.0, 1e-9, b) >= SKIN_AB_MIN) & (chroma / np.maximum(L, 1e-9) <= SKIN_CL_MAX))
    return ok.reshape(small.height, small.width)


def _soft_edges(small, masks, gw, gh, ridge=None, clear=2):
    """Where a form turns away from the light, with no line there to find.

    The XDoG ridge is a LINE detector at one fine scale: it answers "is a dark stroke drawn
    here". A nose bridge, a cheekbone, a collarbone are none of those -- each is a broad,
    shallow ramp ten or twenty grid pixels wide, a few gray levels deep, and the ridge is blind
    to every one of them. Two changes make them visible:

      COARSE SCALE.  A difference of Gaussians at sigma ~5 (at grid width 340) responds to a
      ramp that wide; at sigma 1.6 it responds to nothing but pores and grain.

      ITS OWN NEIGHBORHOOD.  A picture-wide percentile is useless on a portrait, because the
      darkest one percent of any response is hair and clothing and the face never competes.
      Each classified region is thresholded against ITS OWN distribution instead, so the
      darkest tenth of the face is the nose shadow and the eye socket -- which is the point.

    What comes back is ONE LINE per shadow band -- the medial axis of each band-like patch -- and
    nothing at all for a patch wider than a band. Returning each patch's BOUNDARY instead made the
    contours all enclosed loops, with everything doubled. A
    boundary is a closed loop with two sides; a pencil stroke down a shadow is neither. Wide
    patches are regions, and the hatcher already shades regions.

    `ridge` is the fine XDoG skeleton: a soft line within `clear` grid px of it is dropped, because
    the ridge already has that edge and a second line beside it is the other half of "doubled".

    It runs on FLESH only. Measured per band, a nose bridge, a palm crease, a sky gradient and a
    bokeh backdrop have overlapping sharpness and depth -- no local number tells form from
    gradient -- and the sky and the backdrop were already acceptable without it. The target is the
    human form, so that is the region, decided per pixel by the flesh gate and intersected with
    the painted skin class. Every other region keeps only the fine ridge.
    """
    from scipy.ndimage import binary_dilation, binary_opening, gaussian_filter, label
    g = np.asarray(ImageOps.autocontrast(small.convert("L"), cutoff=1), np.float64)
    sig = OUTLINE_SOFT_SIGMA_G * gw / 340.0
    d = gaussian_filter(g, sig, mode="nearest") - gaussian_filter(g, sig * 1.6, mode="nearest")
    min_area = OUTLINE_SOFT_MIN_AREA * gw * gh
    acc = np.zeros(d.shape, bool)
    skin_cls = masks.get(SKIN_WASH)
    if skin_cls is None:
        return acc                        # no flesh painted, nothing for this channel to do
    a = (N.view(skin_cls) != 0) & _skin_px(small)
    n = int(a.sum())
    if n < min_area:
        return acc                        # too small for its own percentile to mean anything
    cut = np.sort(d[a])[max(0, min(n - 1, int(n * OUTLINE_SOFT_FRAC)))]
    # clamped, not gated: a region with real form keeps its own percentile, and a smooth one is held
    # to the depth floor -- where it has almost nothing. Gating on the percentile instead let the
    # fraction switch the region OFF (the face vanished at 0.30), which is absurd.
    acc = a & (d <= min(cut, -OUTLINE_SOFT_MIN_DEPTH))
    if not acc.any():
        return acc
    cross = np.ones((3, 3), bool)
    acc = binary_opening(acc, cross)      # a shading blob one pixel wide is grain
    lab, nlab = label(acc, cross)
    if nlab:
        big = np.zeros(nlab + 1, bool)
        cnt = np.bincount(lab.ravel(), minlength=nlab + 1)
        big[1:] = cnt[1:] >= max(4.0, OUTLINE_SOFT_MIN_BLOB * gw * gh)
        acc = big[lab]                    # a patch too small to be a form is noise in a smooth gradient
        if not acc.any():
            return acc
    # BAND vs REGION. An opening with a disc of radius r deletes everything narrower than 2r+1, so
    # what the opening removes is exactly the band-like part of every patch; what it keeps is the
    # wide body, which is a region and gets no line.
    r = max(1, int(round(OUTLINE_SOFT_BAND_G * gw / 340.0 / 2.0)))
    yy, xx = np.mgrid[-r:r + 1, -r:r + 1]
    disc = (xx * xx + yy * yy) <= r * r
    band = acc & ~binary_opening(acc, disc)
    if not band.any():
        return band
    line = LA.thin(band)                  # one stroke down each band
    if ridge is not None and ridge.any():
        k = 2 * max(1, int(clear)) + 1
        line &= ~binary_dilation(ridge != 0, np.ones((k, k), bool))   # the ridge has this edge already
    return line


def _skeleton(mask, ppg, min_len_g, ridge=None, offset=(0, 0), method="ridge"):
    """Centerline polylines of one component, in the component's own coordinates.

    method="ridge": the image-wide XDoG skeleton restricted to this mask -- clean,
    and the better choice on every fine-lined source (cat, rose, runner, violins).
    method="thin":  Zhang-Suen thinning of the mask itself -- complete, and the
    better choice on every bold-lined source (skull, ship, horse, teapot, lighthouse),
    where the ridge fragments and loses interior detail. The caller chooses by
    measured thickness. A union of both won neither: it added thin's
    junk to the ridge's lines.
    Returns ([(length, polyline)], skeleton_length).
    """
    a = N.view(mask) != 0
    h, w = a.shape
    offx, offy = offset
    fg = None
    if method == "ridge" and ridge is not None and ridge.any():
        fg = _window(ridge, offx, offy, w, h) & a
    if fg is None or int(np.count_nonzero(fg)) < 4:
        if not a.any():
            return [], 0.0, 0
        fg = LA.thin(a)
    if K.SUBCELL_GEOMETRY:
        from paperdaemon.pipeline.decompose.reference.rmb_geometry import skeleton_paths
        traced = skeleton_paths(fg)
    else:
        traced = LA.paths(fg)
    raw = [[(float(x), float(y)) for x, y in ln] for ln in traced]
    n_pieces = max(1, len(raw))
    if not K.SUBCELL_GEOMETRY:
        raw = LA.stitch(raw, gap=6.0 * PX_PER_GRID / ppg, max_turn=65.0)
    out, total = [], 0.0
    for ln in raw:
        L = sum(math.hypot(ln[i+1][0]-ln[i][0], ln[i+1][1]-ln[i][1]) for i in range(len(ln) - 1))
        total += L
        if L < min_len_g or len(ln) < 2:
            continue
        sm = LA.simplify(ln, 0.7 if K.LINE_SMOOTH else 0.35)
        if len(sm) >= 2:
            # two Chaikin passes make a sketch's centerlines read as drawn lines. UI mode
            # turns this off: on a chart frame the smoothing bent a right angle into a 300-px arc
            out.append((L, LA.chaikin(sm, 2) if K.LINE_SMOOTH else sm))
    return out, total, n_pieces


def _distance(mask):
    """Chamfer (3-4) distance to the nearest background pixel, per pixel.

    Two passes over the mask; gives the local half-thickness at every point of
    a component, which is what a centerline needs to carry a faithful width.
    Returns a FLAT int array indexed d[y * w + x], as the Python list did.
    """
    return N.chamfer34(mask)


def _outline(mask, gw, gh, min_len_g):
    """Marching-squares contours of a mask -> (chains at least min_len_g long, total length).
    Takes the mask itself now, not a PixelAccess."""
    a = mask if isinstance(mask, np.ndarray) else N.view(mask)
    chains = [simplify(c, 0.7) for c in N.contours(a, gw, gh, 128) if len(c) >= 6]
    out, total = [], 0.0
    for c in chains:
        L = sum(math.hypot(c[i+1][0]-c[i][0], c[i+1][1]-c[i][1]) for i in range(len(c)-1))
        total += L
        if len(c) >= 3 and L >= min_len_g:
            out.append(c)
    return out, total


def fill_solid(mask, color, ppg, box, offset=(0, 0), grid=None, thick_page=None):
    """True-black remnants after the lines are taken (hooves, beard shadows, wet rock):
    REGIONS. Measured (blob_diag): drawing these as strokes produced every fat
    wandering line."""
    # close=False: a drawn shape's gaps ARE the drawing (the violin's pegs)
    return _fill_region(mask, color, ppg, box, offset=offset, grid=grid, close=False)


def _close(mask, r):
    """Morphological closing by r grid px, padded so the crop border is not eroded."""
    if r <= 0:
        return mask
    k = 2 * r + 1
    a = np.pad(N.view(mask), r, mode="constant")
    a = N.rank_ext(N.rank_ext(a, k, True), k, False)
    return N.img(a[r:r + mask.height, r:r + mask.width])


def _fill_holes(mask, ppg):
    """Fill enclosed paper pockets that are small (FILL_HOLE_PAGE square) or thin (under
    1.5 grid px). A pen cannot leave them, anti-aliasing has half-filled them already,
    and a skeleton splits around them."""
    cw, ch = mask.size
    out = None
    small = (K.FILL_HOLE_PAGE / ppg) ** 2
    for area, m, off in components(ImageChops.invert(mask), 1, 0):
        if off[0] <= 0 or off[1] <= 0 or off[0] + m.width >= cw or off[1] + m.height >= ch:
            continue                                   # reaches the crop border: not enclosed
        if area > small:
            _, perim = _outline(m, m.width, m.height, 1.0)
            if not perim or 2.0 * area / perim > _gu(1.5):
                continue
        if out is None:
            out = mask.copy()
        out.paste(255, (off[0], off[1]), m)
    return mask if out is None else out


def _dab(cx, cy, size_g, ppg, color, gw, gh, box):
    (pts,) = place([[(cx - 0.25, cy), (cx + 0.25, cy)]], (gw, gh), box)
    return (pts, [_field((size_g + 2.0) * ppg)] * 2, Pen.MARKER_2, color, None)


def _round_jaggies(pts, max_seg=3.0):
    """Chaikin-round only the corners made by SHORT segments (pixel jaggies); a corner between
    two long straight runs is a real corner and stays sharp. Plain Chaikin cuts every corner
    by a quarter of its neighboring segments, so a region's straight edge ended in a 90-px
    chamfer at the image border and the row caps showed through (flat-skull)."""
    n = len(pts)
    if n < 4:
        return pts
    out = []
    for i in range(n):
        a, b, c = pts[i - 1], pts[i], pts[(i + 1) % n]
        la, lc = math.hypot(b[0] - a[0], b[1] - a[1]), math.hypot(c[0] - b[0], c[1] - b[1])
        if la <= max_seg and lc <= max_seg:
            out.append((0.75 * b[0] + 0.25 * a[0], 0.75 * b[1] + 0.25 * a[1]))
            out.append((0.75 * b[0] + 0.25 * c[0], 0.75 * b[1] + 0.25 * c[1]))
        else:
            out.append(b)
    out.append(out[0])
    return out


def _fine_rows(m, offx, offy, gw, gh, box, color, ppg, width_g=None):
    """Every run of every pixel row as one stroke 2 grid px wide, inset half a pixel: each
    pixel is covered exactly, with half a grid px of bloat all round. Exact for any shape;
    used where a shape is too small or thin for a ring and rows (its edge is then the
    pixel staircase, which at that size is the resolution anyway)."""
    width_g = _gu(2.0) if width_g is None else width_g
    lines = _row_lines(m, offx, offy)
    w2 = _field(width_g * ppg)
    # the picture path's 2-px rows keep the MARKER; thinner rows (UI glyphs) take the fineliner
    return [(pts, [w2] * 2, Pen.MARKER_2 if width_g >= _gu(2.0) else Pen.FINELINER_2, color, None) for pts in place(lines, (gw, gh), box)]


def _fill_region(mask, color, ppg, box, offset=(0, 0), grid=None, band_page=None, pitch_page=None,
                 close=True):
    """Paint a region with the MARKER, as spirals -- the same painter as the wash.

    There are no lawnmower paths left anywhere in the decomposer. Rows across a core are how a
    printer covers an area: they step at the edge, they leave a scallop between caps, and every
    time they missed something nothing noticed, because coverage was assumed. This walks the
    region's own distance transform from the edge inward, fine first and widening, and MEASURES
    what it painted (_spiral_rings / _ribbon_raster) before deciding anything is left.

    `close` is off for INK. Closing a mask by a pixel and filling its enclosed pockets is right for
    a color region, whose edge is a quantization boundary; it is wrong for a drawn shape, where
    the gaps are the drawing -- it is what welded a violin's tuning pegs to its neck.
    """
    if K.SUBCELL_GEOMETRY:
        from paperdaemon.pipeline.decompose.reference import rmb_geometry
        return rmb_geometry.fill(mask, color, ppg, box, offset, grid, False, sys.modules[__name__])
    cw, ch = mask.size
    gw, gh = grid if grid else (cw, ch)
    P_ = 3
    m = ImageOps.expand(mask, P_, 0)
    offx, offy = offset[0] - P_, offset[1] - P_
    if close:
        m = _fill_holes(_close(m, max(1, int(round(_gu(FILL_CLOSE_G))))), ppg)
    inside = N.view(m) != 0
    if not inside.any():
        return []
    out = []
    by_width = {}
    direct = []
    for pts_, w_ in _spiral_rings(m, ppg, K.MARKER_MIN_PAGE, w_max=K.MARKER_WIDTHS_PAGE[0], soften=False):
        if isinstance(w_, list):
            direct.append((pts_, w_))          # a medial stroke: per-point width, which a pen honors
        else:
            by_width.setdefault(round(w_, 2), []).append(list(pts_))
    for pts_, ws_ in direct:
        (pp,) = place([[(x + offx, y + offy) for x, y in pts_]], (gw, gh), box)
        out.append((pp, [_field(v) for v in ws_], Pen.MARKER_2, color, None))
    for w_ in sorted(by_width, reverse=True):          # widest first, so the fine edge pass lands last
        wf = _field(w_)
        for chain in _join_rings(by_width[w_], inside):
            (pts,) = place([[(x + offx, y + offy) for x, y in chain]], (gw, gh), box)
            out.append((pts, [wf] * len(pts), Pen.MARKER_2, color, None))
    return out


def _round_corners(pts, radius, max_turn=20.0, closed=False):
    """Replace every vertex whose turn exceeds `max_turn` degrees by an arc of radius <= `radius`
    (and <= a third of the adjacent segments), sampled so no step turns more than `max_turn`.
    The device draws a highlighter polyline as a ribbon that notches the inner side of every
    turn by (w/2)(1 - cos(turn/2)) and cuts the outer corner (measured on a calibration page): on a ring around
    a wash a sharp turn is a paper wedge in the fill. Gentle turns cost nothing."""
    n = len(pts)
    if n < 3:
        return list(pts)
    mt = math.radians(max_turn)
    out = []
    rng = range(n) if closed else range(1, n - 1)
    if not closed:
        out.append(pts[0])
    for i in rng:
        a_, v, b_ = pts[i - 1], pts[i], pts[(i + 1) % n]
        d1x, d1y = v[0] - a_[0], v[1] - a_[1]
        d2x, d2y = b_[0] - v[0], b_[1] - v[1]
        l1, l2 = math.hypot(d1x, d1y), math.hypot(d2x, d2y)
        if l1 < 1e-9 or l2 < 1e-9:
            out.append(v)
            continue
        d1x, d1y, d2x, d2y = d1x / l1, d1y / l1, d2x / l2, d2y / l2
        cos_t = max(-1.0, min(1.0, d1x * d2x + d1y * d2y))
        theta = math.acos(cos_t)
        if theta <= mt:
            out.append(v)
            continue
        if theta > math.radians(165.0):
            out.append(v)                                  # a hairpin: tan(theta/2) explodes; leave it (rare: a 1-px spur)
            continue
        rr = min(radius, l1 / 3.0, l2 / 3.0)
        # the arc is tangent to both segments at distance t = rr tan(theta/2) from the vertex,
        # never past the middle of either segment
        t = min(rr * math.tan(theta / 2.0), 0.45 * l1, 0.45 * l2)
        p0 = (v[0] - d1x * t, v[1] - d1y * t)
        p1 = (v[0] + d2x * t, v[1] + d2y * t)
        k = max(2, int(math.ceil(theta / mt)))
        # de Casteljau-ish: quadratic Bezier through p0, v, p1 approximates the tangent arc
        for j in range(k + 1):
            u = j / float(k)
            x = (1 - u) ** 2 * p0[0] + 2 * (1 - u) * u * v[0] + u ** 2 * p1[0]
            y = (1 - u) ** 2 * p0[1] + 2 * (1 - u) * u * v[1] + u ** 2 * p1[1]
            out.append((x, y))
    if not closed:
        out.append(pts[-1])
    return out


def _join_rings(rings, inside):
    """Chain closed rings into as few strokes as possible: from the end of one, jump to the
    nearest point of another and carry on. The jump is only taken when it stays INSIDE the region
    -- a jump across a hole would paint the hole."""
    h_, w_ = inside.shape

    def ok(pt, q):
        n = max(1, int(math.hypot(q[0] - pt[0], q[1] - pt[1])))
        for i in range(n + 1):
            u = i / float(n)
            x, y = int(round(pt[0] + (q[0] - pt[0]) * u)), int(round(pt[1] + (q[1] - pt[1]) * u))
            if not (0 <= x < w_ and 0 <= y < h_) or not inside[y, x]:
                return False
        return True

    todo = [r for r in rings if len(r) >= 2]
    if len(todo) > 200:                      # pathological: emit as-is rather than pair them all
        return todo
    out = []
    while todo:
        chain = list(todo.pop(0))
        while todo:
            cx, cy = chain[-1]
            best = None
            for i, r in enumerate(todo):
                arr = np.asarray(r, np.float64)
                dd = (arr[:, 0] - cx) ** 2 + (arr[:, 1] - cy) ** 2
                j = int(dd.argmin())
                if best is None or dd[j] < best[0]:
                    best = (dd[j], i, j)
            if best is None or not ok(chain[-1], todo[best[1]][best[2]]):
                break
            r = todo.pop(best[1])
            j = best[2]
            chain.extend(r[j:] + r[:j + 1])
        out.append(chain)
    return out


def _ribbon_raster(size, chains, extra=0.0):
    """Which pixels a set of (points, width) strokes actually paints, drawn the way the DEVICE
    draws a highlighter: one rectangle per segment, flat ends, and no joint at a turn (the outer
    wedge stays paper -- measured on a calibration page). Deliberately the pessimistic model, so whatever
    this says is uncovered really is."""
    im = Image.new("L", size, 0)
    dr = ImageDraw.Draw(im)
    for pts, w in chains:
        hw = max(0.5, w / 2.0 + extra)
        q, dirs = [], []
        for pt in pts:                                  # drop repeats: a zero-length segment has no direction
            if not q or abs(pt[0] - q[-1][0]) > 1e-9 or abs(pt[1] - q[-1][1]) > 1e-9:
                q.append(pt)
        if len(q) < 2:
            if q:
                dr.ellipse([q[0][0] - hw, q[0][1] - hw, q[0][0] + hw, q[0][1] + hw], fill=255)
            continue
        for i in range(len(q) - 1):
            (x0, y0), (x1, y1) = q[i], q[i + 1]
            dx, dy = x1 - x0, y1 - y0
            L = math.hypot(dx, dy)
            dirs.append((dx / L, dy / L))
            nx, ny = -dy / L * hw, dx / L * hw
            dr.polygon([(x0 + nx, y0 + ny), (x1 + nx, y1 + ny), (x1 - nx, y1 - ny), (x0 - nx, y0 - ny)], fill=255)
        for i in range(1, len(q) - 1):                  # the app's bevel across the OUTER corner only
            (d1x, d1y), (d2x, d2y) = dirs[i - 1], dirs[i]
            cross = d1x * d2y - d1y * d2x
            if abs(cross) < 1e-9:
                continue
            sgn = -1.0 if cross > 0 else 1.0
            vx, vy = q[i]
            dr.polygon([(vx, vy),
                        (vx + sgn * (-d1y) * hw, vy + sgn * d1x * hw),
                        (vx + sgn * (-d2y) * hw, vy + sgn * d2x * hw)], fill=255)
    return np.asarray(im, np.uint8) != 0


def _across(pts):
    """A two-point stroke that TRAVERSES a small core, along its longest axis.

    The device draws a highlighter with flat ends, so a stroke half a pixel long is a bar half a
    pixel long and as wide as the pen -- it covers a sliver across the core and leaves the rest.
    That is what left a diamond of paper in the exact center of a filled disc. A stroke from one
    extreme of the core to the other covers it.
    """
    xs = [q[0] for q in pts]
    ys = [q[1] for q in pts]
    x0, x1, y0, y1 = min(xs), max(xs), min(ys), max(ys)
    if (x1 - x0) >= (y1 - y0):
        cy = (y0 + y1) / 2.0
        return [(x0 - 0.25, cy), (x1 + 0.25, cy)]
    cx = (x0 + x1) / 2.0
    return [(cx, y0 - 0.25), (cx, y1 + 0.25)]


def _chain_paths(pieces, tol=None, inside=None):
    """Join skeleton fragments that meet end to end into continuous paths.

    A skeleton comes back as one piece per graph edge, so a single drawn outline arrives as dozens
    of short segments -- the fox's outline was 115 of them for one component. Drawn separately each
    gets its own round cap and the line reads as a string of beads. Chained, it is one stroke.
    At a junction the continuation chosen is the STRAIGHTEST one, which is what the eye follows.
    """
    # MEASURED: the skeleton's pieces do not touch. Their endpoints sit 2-3 grid px apart (median
    # 3.0 on the fox's outline, never under 1.8), because the thinning prunes and simplifies at
    # every junction. A tolerance tight enough to be "touching" joins nothing at all.
    tol = K.CHAIN_TOL if tol is None else tol
    paths = [list(pt) for _L, pt in pieces if len(pt) >= 2]
    used = [False] * len(paths)
    out = []
    for i in range(len(paths)):
        if used[i]:
            continue
        used[i] = True
        cur = paths[i]
        for _side in (0, 1):
            while True:
                ex, ey = cur[-1]
                dx, dy = ex - cur[-2][0], ey - cur[-2][1]
                dl = math.hypot(dx, dy) or 1.0
                dx, dy = dx / dl, dy / dl
                best, bj, brev = None, -1, False
                for j, pj in enumerate(paths):
                    if used[j]:
                        continue
                    for rev in (False, True):
                        q = pj[::-1] if rev else pj
                        if math.hypot(q[0][0] - ex, q[0][1] - ey) > tol:
                            continue
                        nx, ny = q[1][0] - q[0][0], q[1][1] - q[0][1]
                        nl = math.hypot(nx, ny) or 1.0
                        turn = dx * nx / nl + dy * ny / nl        # 1 = straight on
                        if best is None or turn > best:
                            best, bj, brev = turn, j, rev
                if bj < 0 or best < K.CHAIN_MIN_COS:
                    break
                if inside is not None:
                    # the jump must stay INSIDE the ink. A generous tolerance is what actually
                    # joins anything (the gaps are 2-3 px), but an unchecked jump could bridge two
                    # separate lines that merely pass near each other.
                    q0 = (paths[bj][::-1] if brev else paths[bj])[0]
                    n_ = max(1, int(math.hypot(q0[0] - ex, q0[1] - ey)))
                    ok = True
                    for t_ in range(n_ + 1):
                        u = t_ / float(n_)
                        xi = int(round(ex + (q0[0] - ex) * u))
                        yi = int(round(ey + (q0[1] - ey) * u))
                        if not (0 <= yi < inside.shape[0] and 0 <= xi < inside.shape[1]) or not inside[yi, xi]:
                            ok = False
                            break
                    if not ok:
                        break
                used[bj] = True
                cur = cur + (paths[bj][::-1] if brev else paths[bj])[1:]
            cur = cur[::-1]                                        # then grow the other end
        out.append((0.0, cur))
    return out


def _cross_width(a, q, ppg, cap):
    """The width ACROSS a medial path at each of its points, in page px.

    The distance transform gives the biggest disc that fits, which at a junction is the distance
    out of the whole crossing and at a corner is the distance out of the corner -- both far wider
    than the line. Measured across the path's own normal it is the line's actual width, which is
    what a pen would lay down. Walking the normal is O(width) per point and needs no extra pass.
    """
    h, w = a.shape
    n = len(q)
    out = []
    lim = max(1, int(round(cap / ppg)) + 2)
    for i in range(n):
        j0, j1 = max(0, i - 1), min(n - 1, i + 1)
        dx, dy = q[j1][0] - q[j0][0], q[j1][1] - q[j0][1]
        L = math.hypot(dx, dy)
        if L < 1e-9:
            nx, ny = 0.0, 1.0
        else:
            nx, ny = -dy / L, dx / L
        x0, y0 = q[i]
        run = 1.0
        for sgn in (1.0, -1.0):
            for k in range(1, lim + 1):
                xi = int(round(x0 + nx * k * sgn))
                yi = int(round(y0 + ny * k * sgn))
                if not (0 <= xi < w and 0 <= yi < h) or not a[yi, xi]:
                    break
                run += 1.0
        # a run of n pixels IS n px of width -- no half-pixel correction here, unlike the distance
        # transform, which measures center to center and overstates by one (see EDGE_HALF_PX).
        out.append(min(cap, run * ppg))
    return out


def _medial_strokes(cmask, a, dist, ppg, w_max, cw_, ch_, maxd):
    """The medial strokes for ONE mask, with the widths taken from `a`/`dist` -- which may
    be a LARGER mask this one was cut out of, so a hairline keeps its true thickness even
    when it is being painted as the thin remainder of something bigger.

    A shape is exactly the union of discs centered on its medial axis with radius the
    distance transform, so a stroke along that axis carrying 2x the local distance
    reproduces it exactly -- for a hairline, an outline or a blob alike.
    """
    out = []
    # the width is the LOCAL thickness at each point, not the component's greatest: a stroke
    # carrying the thickest part of a shape along its whole length is the fat, even line that
    # took the ship to 1.78 of its source's ink.
    dist_l = dist
    sk, _sl, _np_ = _skeleton(cmask, ppg, 0.0, method="thin")
    if K.CHAIN_SKELETON:
        sk = _chain_paths(sk, inside=a)
    ext = max(0.5, maxd)          # carry each end on by the shape's own half-thickness
    drawn_any = np.zeros((ch_, cw_), bool)
    for _L, pts_ in sk:
        if len(pts_) < 2:
            # a branch too short to be a path is still a mark -- the ship's finest rigging and
            # every tick and serif lives here, and skipping them left 2.2% of that drawing blank
            if len(pts_) == 1:
                x_, y_ = pts_[0]
                xi = min(cw_ - 1, max(0, int(round(x_))))
                yi = min(ch_ - 1, max(0, int(round(y_))))
                wv = max(K.HL_MIN_PAGE, 2.0 * max(0.25, float(dist_l[yi, xi]) / 3.0 - K.EDGE_HALF_PX) * ppg)
                out.append(([(x_ - 0.25, y_), (x_ + 0.25, y_)], [wv, wv]))
            continue
        q = list(pts_)
        # the width ACROSS the line, not the biggest disc that fits (see _cross_width) -- but
        # never more than the disc allows. Where the normal happens to run along another branch
        # the walk over-reads, and the distance transform is a hard ceiling on the half-width.
        cw_meas = _cross_width(a, q, ppg, w_max)
        ws = []
        for (x_, y_), wc in zip(q, cw_meas):
            xi = min(cw_ - 1, max(0, int(round(x_))))
            yi = min(ch_ - 1, max(0, int(round(y_))))
            ceil_ = 2.0 * max(0.25, float(dist_l[yi, xi]) / 3.0 - K.EDGE_HALF_PX) * ppg
            ws.append(min(wc, ceil_))
        # SMOOTH THE PATH AND THE WIDTH, or the stroke boils. A medial axis follows the
        # pixel staircase of the mask and the width is measured afresh at every point, so the
        # stroke wanders and pulses along its length -- that is the wobble, and no area
        # measurement can see it. A single centerline is safe to smooth (unlike a traced
        # outline, where the two sides would wander apart).
        n_ = len(ws)
        r_ = K.MEDIAL_SMOOTH
        ws = [sum(ws[max(0, i - r_):min(n_, i + r_ + 1)]) / len(ws[max(0, i - r_):min(n_, i + r_ + 1)])
              for i in range(n_)]
        if n_ >= 5:
            q = [q[0]] + [((q[i - 1][0] + 2.0 * q[i][0] + q[i + 1][0]) / 4.0,
                           (q[i - 1][1] + 2.0 * q[i][1] + q[i + 1][1]) / 4.0)
                          for i in range(1, n_ - 1)] + [q[-1]]
        med = sorted(ws)[n_ // 2]
        lim = max(K.HL_MIN_PAGE, med * K.LINE_WIDTH_SPIKE)
        ws = [max(K.HL_MIN_PAGE, min(v, lim, w_max)) for v in ws]
        # the medial axis RETRACTS from the ends of a shape by about its own half-width, so a
        # bar's tip and every stroke end went unpainted. Carry each end on along its own
        # direction, AT THE WIDTH IT ALREADY HAS -- sampling the distance transform out there
        # reads nearly zero and the stroke tapered away to nothing instead.
        (x0, y0), (x1, y1) = q[1], q[0]
        d0 = math.hypot(x1 - x0, y1 - y0)
        if d0 > 1e-9:
            e0 = max(0.4, ws[0] / (2.0 * ppg))     # its OWN half-width, not the shape's widest
            q.insert(0, (x1 + (x1 - x0) / d0 * e0, y1 + (y1 - y0) / d0 * e0))
            ws.insert(0, ws[0])
        (x0, y0), (x1, y1) = q[-2], q[-1]
        d1 = math.hypot(x1 - x0, y1 - y0)
        if d1 > 1e-9:
            e1 = max(0.4, ws[-1] / (2.0 * ppg))
            q.append((x1 + (x1 - x0) / d1 * e1, y1 + (y1 - y0) / d1 * e1))
            ws.append(ws[-1])
        out.append((q, ws))
    return out

def _spiral_rings(cmask, ppg, w_page, level=0, w_max=None, soften=True, base_depth=0.0):
    """One CONNECTED mask -> [(closed loop, width in page px)] covering it.

      * a SUPER FINE pass around the border, its outer edge exactly on the zone's boundary, so the
        neighboring zone's border pass meets it and neither crosses the line. Two highlighter
        colors that overlap composite to a third, so this has to be exact, not approximate;
      * then loops inward, each re-painting HALF of the one before it (50% coverage over the
        previous stroke in each wash loop, not just marginally), so nothing can fall
        between two loops even where the geometry is a pixel out;
      * and a loop only WIDENS when the wider stroke still fits inside what is left: it only gets
        bigger when the radius of the sharpest turn can be buried in the existing wash. What is left is
        measured (2*area/perimeter), and a stroke wider than that would spill over the edge or
        bowtie in the corners;
      * the last one is a line down the middle of the final gap.

    Iterative, one pass per width. The recursive version this replaces walked every connected part
    separately and was the reason a decomposition took minutes.
    """
    if cmask.getbbox() is None:
        return []
    w_max = HL_WIDTHS_PAGE[0] if w_max is None else w_max
    ch_, cw_ = cmask.height, cmask.width
    a = N.view(cmask) != 0
    if not a.any():
        return []
    dist, _dw, _dh = _distance(cmask)
    dist = np.asarray(dist, np.int32).reshape(ch_, cw_)
    maxd = float(dist.max()) / 3.0                    # chamfer 3-4: an orthogonal step counts 3
    if maxd <= 0.0:
        return []
    out = []
    # A THIN SHAPE IS DRAWN ALONG ITS MIDDLE, NOT AROUND ITS EDGE. Tracing the contour of a two or
    # three pixel line means tracing up one side and back down the other, and marching squares is
    # unstable at that width: measured on a plain ring, 2 px wide left 75% of itself unpainted in
    # 24 strokes, 3 px took 2 strokes, 5 px took 114. That instability is the dashed outline and
    # the boiling. The medial axis is one path that follows the curve, and one stroke as wide as
    # the shape covers it exactly.
    # THE MEDIAL AXIS IS THE SHAPE. A shape is exactly the union of discs centered on its medial
    # axis with radius the distance transform, so a stroke along that axis carrying 2x the local
    # distance reproduces it exactly -- for a hairline, an outline or a blob alike. The only limit
    # is the pen: past its widest stroke the discs cannot be drawn, and only then do the loops take
    # over. That limit, not an arbitrary thinness, is where the two methods should part.
    # ...up to a LINE's width, not the pen's. A medial stroke carries the width point by point, so
    # on a wide shape its edges ripple with every change -- a cat's eye came out as a lumpy blob.
    # A line is drawn along its middle; a SHAPE is drawn by its edge, which the loops do exactly.
    # MEDIAL OR LOOPS IS THE PEN'S QUESTION, and there is only one criterion: can a stroke of the
    # pen's own width be inset far enough to keep its outer edge on the boundary? Where it cannot,
    # nothing else will do and the shape is drawn along its middle. Where it can, the loops do it,
    # because a thinned skeleton is NOT the medial axis of a two-dimensional region: it drops the
    # short branches that reach into corners, and the discs along what is left miss them. Measured
    # on one zone of an art nouveau panel, 11,273 px of filaments and lobes: the medial left 10% of it
    # unpainted -- blobs up to 120 px -- and those are the pinholes. A fixed thickness threshold
    # (INK_THIN_PAGE, 20 page px) called that region a line; it survives only as the width cap on
    # a rescue stroke.
    w_first = max(K.HL_MIN_PAGE, min(w_page, w_max))
    t_first = max(1, int(math.ceil(3.0 * (w_first / (2.0 * ppg) + 2.0 * K.EDGE_HALF_PX) - 1e-9)))
    core = dist >= t_first
    if K.THIN_AS_MEDIAL and not core.any():
        out = _medial_strokes(cmask, a, dist, ppg, w_max, cw_, ch_, maxd)
        if out:
            return out
    # A MASK IS NOT ALL ONE THICKNESS, AND THE CHOICE OF PAINTER IS PER PIXEL. The cat's ink is a
    # single mask carrying a 9 px outline and a thousand 1 px fur strokes; deciding by the mask's
    # greatest depth sends the lot to the loops, and the loops cannot inset a border pass into a
    # line thinner than the pen -- their first contour does not even select it, and every fur
    # stroke came out dashed (false-white 0.24% -> 4.98%). So whatever the loops cannot reach is
    # painted along its middle instead, at its own local width, the two overlapping by a pixel.
    # Painting the same color twice costs nothing: a highlighter composites as a minimum.
    w = max(K.HL_MIN_PAGE, min(w_page, w_max))
    # WHICH PARTS OF THIS MASK CAN THE PEN PAINT WITHOUT SPILLING? Exactly the ones a stroke of its
    # own width fits inside -- the morphological OPENING of the mask by the pen's half-width. What
    # is left over is thinner than the pen, and there a ring cannot be inset at all: the contour it
    # would trace fragments at every narrow spot, which is how a fox's outline came back dashed and
    # 4% of the cat's fur went missing. Those parts are painted along their middles instead.
    # Deciding this by the mask's greatest depth (or by proximity to a deep core) cannot work: one
    # mask carries a 9 px outline and a thousand 1 px fur strokes, and the answer differs per pixel.
    # WHAT THE LOOPS CANNOT REACH IS PAINTED ALONG ITS MIDDLE. The border pass rides the contour
    # of `dist >= t0` and paints half its width either side of it; nothing further out than that
    # gets any paint at all, and on a line thinner than the pen the contour does not even exist.
    # One mask carries a 9 px outline and a thousand 1 px fur strokes, so this is decided per
    # PIXEL: by the mask's greatest depth the lot went to the loops and every fur stroke came back
    # dashed (false-white 0.24% -> 4.98%). Painting the same color twice costs nothing -- a
    # highlighter composites as a minimum -- so the two are free to overlap.
    t0 = t_first
    if K.THIN_AS_MEDIAL and core.any() and not core.all():
        w_e0 = max(K.HL_MIN_PAGE, min(2.0 * (t0 / 3.0 - 2.0 * K.EDGE_HALF_PX) * ppg, w_max))
        reach = max(1, int(round(w_e0 / (2.0 * ppg))) - K.THIN_RESCUE_SLACK)
        near = N.rank_ext(core.astype(np.uint8), 2 * reach + 1, True) != 0
        thin = a & ~near
        if thin.any():
            # ...and it is given the WHOLE mask, not just the part the loops miss. A shape's medial
            # axis is one continuous path; cutting it into the pieces the loops cannot reach makes
            # a fox's outline a string of beads, because each piece is drawn on its own and the
            # loops take the gaps between them. Capped at a line's width, the stroke that runs on
            # through the thick parts is buried inside what the loops paint there.
            out.extend(_medial_strokes(cmask if K.THIN_RESCUE_WHOLE else N.bool_img(thin), a, dist,
                                       ppg, min(w_max, K.INK_THIN_PAGE), cw_, ch_, maxd))
    covered = 0.0
    # DEPTH IS MEASURED FROM THE SHAPE'S EDGE, NOT FROM THE OUTERMOST PIXEL'S CENTER. The chamfer
    # transform counts pixel to pixel: the outermost pixel of a mask reads 1.0, but its center is
    # only HALF a pixel inside the boundary the eye sees -- and a contour is not traced through
    # those centers either, but along the EDGE between the selected pixels and the rest, another
    # half pixel out. So a ring on the contour of `dist >= t` sits at depth t/3 - 2*EDGE_HALF_PX.
    # Measured on a plain rectangle: paint reached 0.73 px past a mask edge before this. Treating that 1.0 as the distance to the
    # edge put every border pass half a pixel out, and the highlighter composites as a per-channel
    # MINIMUM -- so that half pixel can only ever darken the neighbor it spills onto. Measured on
    # a test panel: every zone rendered 15-20% darker than the color it was given. So the geometric
    # depth of the contour at chamfer level t is t/3 - 0.5, and every line below uses that.
    maxd_geo = maxd - K.EDGE_HALF_PX
    t_prev = 0
    for _ in range(K.SPIRAL_MAX_PASSES):
        hw = w / (2.0 * ppg)
        d = covered + hw if covered <= 0.0 else covered - (w / ppg) * K.LOOP_OVERLAP_FRAC + hw
        if d > maxd_geo:
            d = maxd_geo
        # The BORDER pass is the one that has to be exact, so it is chosen the other way round:
        # take the first contour DEEP enough to carry a stroke of the pen's minimum width, then
        # let its own depth set the width (w_eff = 2*d_eff*ppg) so the outer edge lands exactly on
        # the boundary -- neither over it nor short of it. Inner passes floor instead, and are
        # capped at the same 2*d_eff so a wide one cannot reach back out through the edge.
        if covered <= 0.0:
            t = max(1, int(math.ceil(3.0 * (d + 2.0 * K.EDGE_HALF_PX) - 1e-9)))
        else:
            t = max(t_prev + 1, int(math.floor(3.0 * (d + 2.0 * K.EDGE_HALF_PX) + 1e-9)))
        sel = dist >= t
        if not sel.any():
            break
        d_eff = t / 3.0 - 2.0 * K.EDGE_HALF_PX
        w_eff = (max(K.HL_MIN_PAGE, min(2.0 * d_eff * ppg, w_max)) if covered <= 0.0 else
                 max(K.HL_MIN_PAGE, min(w, 2.0 * d_eff * ppg, w_max)))
        t_prev = t
        drew = False
        for c in N.contours(N.view(N.bool_img(sel)), cw_, ch_, 128):
            # A THIN SHAPE IS NOT SMOOTHED. Simplifying and corner-rounding the outline of a one-
            # to three-pixel line lets its two sides wander independently, and the stroke that
            # results shimmers -- a "boiling" seen on a ship's rigging, an oak's
            # leaves, a rose and a robot's outline.
            # THE BORDER PASS IS NOT SIMPLIFIED. Its outer edge is meant to land exactly on the
            # zone's boundary, so every corner the simplifier cuts is paper left at the seam and
            # every one it bulges is one color painted over another. Inner passes are free to be
            # smoothed: they are buried in what is already there.
            # THE BORDER PASS IS NOT SIMPLIFIED -- its outer edge is meant to land exactly on the
            # zone's boundary, and every corner the simplifier cuts is paper left at the seam. It
            # IS still de-staircased and corner-rounded, because the device draws a polyline as a
            # ribbon that notches the inner side of every turn: a raw marching-squares contour
            # turns 90 degrees at every pixel, and those notches are the pinholes along the edge.
            # THE BORDER PASS IS NEITHER SIMPLIFIED NOR SMOOTHED. Its outer edge is meant to land
            # exactly on the zone's boundary; measured, putting _round_jaggies and _round_corners
            # back on it threw paint 17-19% outside the shape (taper, crescent) to recover 6% of
            # the pinholes, which is the wrong trade under a minimum blend.
            thin_shape = maxd <= K.INK_NO_SMOOTH_DEPTH or covered <= 0.0
            sm = list(c) if thin_shape else simplify(c, min(_gu(0.5), max(0.2, w_eff / ppg / 4.0)))
            if len(sm) >= 3:
                if math.hypot(sm[-1][0] - sm[0][0], sm[-1][1] - sm[0][1]) < 1e-6:
                    sm = sm[:-1]
                r_pts = list(sm) if thin_shape else _round_jaggies(sm, _gu(3.0))[:-1]
                if soften and not thin_shape:
                    r_pts = _round_corners(r_pts, radius=w_eff / ppg / 2.0 + 1.0,
                                           max_turn=HL_MAX_TURN, closed=True)
                if len(r_pts) > 2:
                    out.append((r_pts + [r_pts[0], r_pts[1]], w_eff))
                    drew = True
                    continue
            if len(sm) >= 1:
                out.append((_across(sm), w_eff))
                drew = True
        if not drew:
            ys, xs = np.nonzero(sel)
            if xs.size:
                out.append((_across([(float(x), float(y)) for x, y in zip(xs.tolist(), ys.tolist())]), w_eff))
        covered = d_eff + w_eff / (2.0 * ppg)
        if covered >= maxd_geo - 1e-6:
            break
        rest = dist >= max(t + 1, int(math.floor(3.0 * (covered + 2.0 * K.EDGE_HALF_PX))))
        if not rest.any():
            break
        # how wide a stroke the remainder can bury: its own mean thickness
        _cs, per_r = _outline(N.bool_img(rest), cw_, ch_, 0.0)
        room = (2.0 * float(rest.sum()) / per_r * ppg) if per_r > 0 else w_max
        w = max(K.HL_MIN_PAGE, min(w_max, room, w * K.HL_SPIRAL_GROWTH))
    return out


def _join_rings(rings, inside):
    """Chain rings of the same width into as few strokes as possible: from the end of one, jump to
    the nearest point of another and carry on. The jump is taken only where it stays INSIDE the
    region -- a jump across a hole would paint the hole."""
    h_, w_ = inside.shape

    def ok(pt, q):
        n = max(1, int(math.hypot(q[0] - pt[0], q[1] - pt[1])))
        for i in range(n + 1):
            u = i / float(n)
            x, y = int(round(pt[0] + (q[0] - pt[0]) * u)), int(round(pt[1] + (q[1] - pt[1]) * u))
            if not (0 <= x < w_ and 0 <= y < h_) or not inside[y, x]:
                return False
        return True

    todo = [r for r in rings if len(r) >= 2]
    if len(todo) > 120:                      # pathological: emit as-is rather than pair them all
        return todo
    out = []
    while todo:
        chain = list(todo.pop(0))
        while todo:
            cx, cy = chain[-1]
            best = None
            for i, r in enumerate(todo):
                arr = np.asarray(r, np.float64)
                dd = (arr[:, 0] - cx) ** 2 + (arr[:, 1] - cy) ** 2
                j = int(dd.argmin())
                if best is None or dd[j] < best[0]:
                    best = (dd[j], i, j)
            if best is None or not ok(chain[-1], todo[best[1]][best[2]]):
                break
            r = todo.pop(best[1])
            j = best[2]
            chain.extend(r[j:] + r[:j + 1])
        out.append(chain)
    return out


def _fill_region_hl(mask, rgba, ppg, box, offset=(0, 0), grid=None):
    """Paint a region as SPIRALS, not rows.

    The highlighter stroke for a fill is one stroke, spiraling around the edge finely at first,
    and then using thicker and thicker ones until it fills in the space.

    Each pass is the iso-contour of the region's own distance transform at the depth its width
    reaches. The first sits at half the FINEST width the pen has, so its outer edge lands on the
    region's edge and the shape is exact; each pass after it starts exactly where the last one
    ended and is one step wider, where only coverage matters. Nothing can be left over: every
    pixel is within half a width of some pass, by construction (_spiral_rings).

    Rings of the same width are joined end to start into one stroke, so a region costs a handful
    of strokes instead of hundreds of rows. Width is constant within a stroke -- the device honors
    one width per highlighter stroke for certain, per-point widths are unverified.
    """
    if K.SUBCELL_GEOMETRY:
        from paperdaemon.pipeline.decompose.reference import rmb_geometry
        return rmb_geometry.fill(mask, rgba, ppg, box, offset, grid, True, sys.modules[__name__])
    cw, ch = mask.size
    gw, gh = grid if grid else (cw, ch)
    P_ = int(math.ceil(HL_WIDTHS_PAGE[0] / 2.0 / ppg)) + 2
    m = ImageOps.expand(mask, P_, 0)
    offx, offy = offset[0] - P_, offset[1] - P_
    m = _fill_holes(_close(m, max(1, int(round(_gu(FILL_CLOSE_G))))), ppg)
    inside = N.view(m) != 0
    if not inside.any():
        return []
    out = []
    by_width = {}
    # ONE CALL for the whole mask: the loop builder traces every contour it finds at each depth, so
    # splitting the mask into connected pieces first only multiplies the distance transforms. On
    # a painting this was 4,559 calls for 619 zones.
    for pts_, w_ in _spiral_rings(m, ppg, K.HL_MIN_PAGE, w_max=HL_WIDTHS_PAGE[0]):
        if isinstance(w_, list):
            # the device honors ONE width per highlighter stroke for certain; per-point widths on
            # a wash are unverified, so a medial wash takes its own mean
            w_ = sum(w_) / len(w_)
        by_width.setdefault(round(w_, 2), []).append(list(pts_))
    for w_ in sorted(by_width, reverse=True):          # widest first: the fine edge pass lands last
        wf = _hl_field(w_)
        for chain in _join_rings(by_width[w_], inside):
            (pts,) = place([[(x + offx, y + offy) for x, y in chain]], (gw, gh), box)
            out.append((pts, [wf] * len(pts), Pen.HIGHLIGHTER_2, PenColor.HIGHLIGHT, rgba))
    return out


def draw_component(area, mask, color, ppg, box, min_len_g, tone=False, offset=(0, 0), grid=None, lum=None, ridge=None, gray=False, lines=False,
                   line_regions_pen=None, line_regions_max_g=0, lines_min_frac=0.0):
    """One component -> (strokes, kind, drawn).

    The component is split by WIDTH, not judged as a whole. Parts wider than
    FILL_THICK_PAGE (and bigger than FILL_ZONE_MIN_PAGE square) are REGIONS; everything
    else is LINE: a centerline carrying the local thickness as per-sample width (the
    format stores width per point and the device honors it). A bold line, a
    foliage clump or a junction blob drawn as skeleton strokes made spaghetti in
    the thick areas (oak, lighthouse, ship).

    Color: regions are painted here (_fill_region) and lines stroked in the color.
    Ink (tone=True): lines are stroked; regions are NOT painted here -- the true-black
    pixel mask decides what fills and the rest hatches (a coat at L*5 joined to a face
    at L*35 must not fill the face). `drawn` is the mask of what these strokes
    cover, for the caller to take out of its hatch/fill masks.
    kind: "line" if a line was drawn, "fill" if only regions were, else "tone".
    """
    cw, ch = mask.size
    gw, gh = grid if grid else (cw, ch)
    offx, offy = offset
    if K.SUBCELL_GEOMETRY and tone and K.INK_AS_FILL:
        # The later whole-ink fill owns this mask. Computing an opening,
        # component statistics and a thin/thick split here cannot emit a line.
        return [], "tone", Image.new("L", (cw, ch))
    if K.SUBCELL_GEOMETRY and not tone and not lines:
        # Color is filled as a whole zone. The former morphological split was
        # discarded unconditionally (line_ok=False); do not calculate it.
        if mask.getbbox() is None:
            return [], "fill", mask.copy()
        kind_, val = color if isinstance(color, tuple) else ("pen", color)
        if kind_ == "rgb":
            st = _fill_region_hl(mask, tuple(val), ppg, box, offset=offset, grid=(gw, gh))
        elif kind_ == "hl":
            st = [s for letter in val for s in _fill_region_hl(mask, HL_RGBA[letter], ppg, box, offset=offset, grid=(gw, gh))]
        else:
            st = _fill_region(mask, val, ppg, box, offset=offset, grid=(gw, gh))
        return st, "fill", mask.copy()
    if not K.SUBCELL_GEOMETRY:
        mask = _fill_holes(mask, ppg)
    r_t = max(1, int(round(FILL_THICK_PAGE / 2.0 / ppg)))
    # an OPENING by an (2 r_t + 1) square. Repeated 3x3 erosions compose into one square
    # erosion, and the zero pad makes PIL's edge replication indistinguishable from a zero
    # extension there, so the one-shot separable filter is exact and O(n) instead of O(n r).
    pad = r_t + 1
    k = 2 * r_t + 1
    a = np.pad(N.view(mask), pad, mode="constant")
    a = N.rank_ext(N.rank_ext(a, k, False), k, True)
    zone = N.img(a[pad:pad + ch, pad:pad + cw])
    # THE WHOLE COMPONENT IS EITHER A LINE OR A SHAPE. Splitting one outline into thin parts (drawn
    # as centerlines) and thick parts (filled) breaks it: the centerline fragments at every place
    # the line happens to swell, the short pieces fall under the length floor, and what reaches the
    # page is a dotted line -- the ship's rigging and the robot's outline. Decide once, by the
    # component's own greatest half-thickness, and use one method for all of it.
    if tone and K.INK_ONE_METHOD:
        _dd, _ddw, _ddh = _distance(mask)
        comp_thick_page = 2.0 * (float(np.asarray(_dd, np.int32).max()) / 3.0) * ppg
        if comp_thick_page <= K.INK_THIN_PAGE:
            zone = Image.new("L", (cw, ch))          # all of it is a line
        else:
            zone = mask                               # all of it is a shape
    thick = Image.new("L", (cw, ch))
    min_zone = (FILL_ZONE_MIN_PAGE / ppg) ** 2
    ribbon = False
    for a_, zm, zoff in components(zone, 1, 0):
        if a_ < min_zone:
            continue
        if tone and K.RIBBON_LINES:
            # A RIBBON IS A LINE, however bold (see rmb_params). Mean thickness against the
            # bounding box's diagonal: a band scores in the tens, a blob under three.
            _, per_ = _outline(zm, zm.width, zm.height, 1.0)
            t_ = (2.0 * a_ / per_) if per_ else float("inf")
            if (t_ > 0 and math.hypot(zm.width, zm.height) >= K.RIBBON_ASPECT * t_
                    and t_ * ppg <= K.RIBBON_MAX_PAGE):
                ribbon = True
                continue                      # left in thin_part: drawn as a centerline
        thick.paste(zm, (zoff[0], zoff[1]), zm)
    has_thick = thick.getbbox() is not None
    thin_part = ImageChops.subtract(mask, thick)
    if has_thick:
        thin_part = ImageChops.multiply(_dilate(thin_part, _ker()), mask)   # overlap the region by 1 px
    thin_area = N.count(thin_part)
    out = []
    drawn = Image.new("L", (cw, ch))
    kind = "tone"
    line_ok = False
    # COLOR is painted entirely as regions. Its thin parts used to go down the line path as
    # skeleton strokes, and those leak: pieces under the length floor, pruned spurs and the
    # medial axis of a ragged fleck left 30-50 % of a thin color part unpainted (measured on
    # water-oak / flat-rose classes). The region painters cover thin parts with fine rows,
    # exactly, and a solid tube of rows looks the same as one stroke. Ink keeps its line path.
    # (`lines` -- UI mode -- lets a COLOR component's thin parts be lines too: a chart's series)
    # (`lines_min_frac` -- UI mode -- a component with thick parts makes lines of its thin parts only if they
    # are that fraction of it: the corner slivers of an eroded pill are the fill's, not lines)
    # INK IS A SHAPE, NOT A SKELETON. Line work with spaghetti needs a different
    # way of doing thick black lines, one that is elegant and fills properly. A centerline carrying
    # a measured width wanders, lumps at junctions (where the distance transform is the distance
    # out of the COMBINED shape) and turns a clean dark mass into a blob with wavy edges. Traced
    # and filled with the same loops the wash uses, a black shape is exactly its own outline.
    line_part = (tone and not K.INK_AS_FILL) or (lines and (not has_thick or thin_area >= lines_min_frac * area))
    if line_part and thin_area and thin_area < 0.25 * gw * gh:
        _, perim = _outline(thin_part, cw, ch, min_len_g)
        est_page = (2.0 * thin_area / perim if perim > 0 else float("inf")) * ppg
        method = "ridge" if est_page <= K.RIDGE_MAX_PAGE else "thin"
        sk, sk_len, n_pieces = _skeleton(thin_part, ppg, min_len_g, ridge=ridge, offset=offset, method=method)
        thick_g = (thin_area / sk_len) if sk_len > 0 else float("inf")
        thick_page = thick_g * ppg
        mean_piece_g = sk_len / n_pieces if n_pieces else 0.0
        texture = thick_page > 4.0 and n_pieces >= 4 and mean_piece_g < TEXTURE_PIECES * thick_g
        line_ok = bool(sk) and not texture
        if gray and line_ok:
            # GRAY ink is a line only when hairline-thin, line-like and long
            line_ok = (thick_page <= GRAY_LINE_MAX_PAGE and mean_piece_g >= GRAY_LINE_PIECES * thick_g
                       and sk_len * ppg >= GRAY_LINE_MIN_LEN_PAGE)
        if line_ok:
            dist, dw, dh = _distance(mask)               # the whole component's distances: true at a junction
            # a recovered ribbon must be drawn at the width it MEASURES; the ordinary cap would
            # clip a bold outline straight back to the thin lines it is meant to be distinct from
            cap = K.RIBBON_CAP_PAGE if ribbon else FILL_THICK_PAGE * 1.2
            def local_w(x, y):
                xi, yi = min(dw - 1, max(0, int(round(x)))), min(dh - 1, max(0, int(round(y))))
                return max(1.2, min(cap, 2.0 * int(dist[yi * dw + xi]) / 3.0 * ppg)) * K.LINE_SCALE
            for L, pts_g in sk:
                raw_w = [local_w(x, y) for x, y in pts_g]
                n = len(raw_w)
                # moving average so the integer chamfer steps do not read as lumps
                widths_page = [sum(raw_w[max(0, i - 2):min(n, i + 3)]) / len(raw_w[max(0, i - 2):min(n, i + 3)]) for i in range(n)]
                if gray:
                    # a gray line's footprint is its blur, not its ink: draw it thin
                    widths_page = [max(GRAY_LINE_MIN_PAGE, wp * GRAY_LINE_SCALE) for wp in widths_page]
                # A JUNCTION IS NOT A WIDTH. `dist` is the whole component's distance transform, so
                # where a peg meets a violin's neck the distance is the distance out of the COMBINED
                # shape -- large -- and the stroke drawn that wide welds the two together and closes
                # the gap between them (the pegs got merged). A branch
                # may taper, but it may not spike: every point is capped at a multiple of the
                # branch's own median width.
                if n >= 3 and K.LINE_WIDTH_SPIKE > 0:
                    med = sorted(widths_page)[n // 2]
                    lim = max(1.2, med * K.LINE_WIDTH_SPIKE)
                    widths_page = [min(wp, lim) for wp in widths_page]
                mean = sum(widths_page) / n
                pen = Pen.FINELINER_2 if mean <= FINELINER_MAX_PAGE else Pen.MARKER_2
                col = _line_pen(color)
                if tone:
                    # a thin gray stroke is a drawn line: gray pen if it is light, black if dark
                    col = PenColor.GRAY if (lum is not None and lum > GRAY_LINE_L) else PenColor.BLACK
                (pts,) = place([[(x + offx, y + offy) for x, y in pts_g]], (gw, gh), box)
                out.append((pts, [_field(wp) for wp in widths_page], pen, col, None))
            drawn.paste(thin_part, (0, 0), thin_part)
            kind = "line"
    if tone:
        return out, kind, drawn
    # color: everything that is not a drawn line is a region and is painted
    regions = thick if line_ok else mask
    if regions.getbbox() is not None:
        kind_, val = color if isinstance(color, tuple) else ("pen", color)
        # THE WHOLE ZONE AT ONCE, not one call per connected blob. The painter already traces every
        # contour it finds at each depth, so a mask with two hundred scattered pieces costs one
        # distance transform instead of two hundred. Measured on the ship: 8,039 calls into this
        # for one picture, and draw_component was 5.3 of its 7.3 seconds. This is the slowness --
        # not anti-aliasing, not resampling, just doing the same work once per speck.
        if kind_ == "rgb":
            out.extend(_fill_region_hl(regions, tuple(val), ppg, box, offset=(offx, offy), grid=(gw, gh)))
        elif kind_ == "hl":
            for letter in val:                              # a pair is two washes; min() is order-free
                out.extend(_fill_region_hl(regions, HL_RGBA[letter], ppg, box, offset=(offx, offy), grid=(gw, gh)))
        else:
            out.extend(_fill_region(regions, val, ppg, box, offset=(offx, offy), grid=(gw, gh)))
        drawn.paste(regions, (0, 0), regions)
        if kind != "line":
            kind = "fill"
    return out, kind, drawn


def shadow_zones(masks, small, grid_w, gh, keys=None):
    """WHICH ZONES ARE SHADING, AND WHICH ARE THINGS.

    The decomposer cannot recognize a shadow, and it does not have to. A SHADOW IS A DARKER
    VERSION OF ITS NEIGHBOR'S COLOR: paint that falls into shade keeps its hue and loses
    lightness, while a different object arrives with a different hue. So for every pair of zones
    that share a border:

        same hue, one darker   -> the darker one is that paint in shade. Hatch it.
        different hue          -> two different things meeting. Hatch neither.

    A second signal separates a shadow's edge from a drawn one, and costs a single blur: a
    shadow's boundary is SOFT, an object's is sharp. A zone counts as shade only if its border
    with the lighter zone is soft.

    That is what replaces "hatch everything achromatic", which put hatch over light and dark
    alike. -> (boolean mask of the shading zones, report dict)
    """
    keys = [k for k in masks if k not in ("black", "tone", "_ink")] if keys is None else keys
    rep = {"zones": len(keys), "shadow": 0, "pairs": 0}
    if len(keys) < 2:
        return np.zeros((gh, grid_w), bool), rep
    lab_img = np.full((gh, grid_w), -1, np.int32)
    for i, k in enumerate(keys):
        lab_img[N.view(masks[k]) != 0] = i
    rgb = np.asarray(small.convert("RGB"), np.uint8).reshape(-1, 3)
    lab_all = _lab_rows(rgb)
    n = len(keys)
    means = np.zeros((n, 3), np.float64)
    sizes = np.zeros(n, np.int64)
    flat_lab = lab_img.reshape(-1)
    for i in range(n):
        sel = flat_lab == i
        sizes[i] = int(sel.sum())
        if sizes[i]:
            means[i] = lab_all[sel].mean(axis=0)
    # how sharp the source is, at the scale a shadow's edge lives at
    g = np.asarray(small.convert("L").filter(ImageFilter.GaussianBlur(K.SHADOW_EDGE_BLUR)), np.float64)
    gy, gx = np.gradient(g)
    grad = np.hypot(gx, gy)
    counts, soft_sum = {}, {}
    for dy, dx in ((0, 1), (1, 0)):
        A = lab_img[:gh - dy, :grid_w - dx]
        B = lab_img[dy:, dx:]
        sel = (A >= 0) & (B >= 0) & (A != B)
        if not sel.any():
            continue
        a_, b_ = A[sel], B[sel]
        code = np.minimum(a_, b_).astype(np.int64) * n + np.maximum(a_, b_)
        gsel = grad[:gh - dy, :grid_w - dx][sel]
        u, first = np.unique(code, return_inverse=True)
        cnt = np.bincount(first, minlength=len(u))
        gsum = np.bincount(first, weights=gsel, minlength=len(u))
        for idx, cd in enumerate(u.tolist()):
            counts[cd] = counts.get(cd, 0) + int(cnt[idx])
            soft_sum[cd] = soft_sum.get(cd, 0.0) + float(gsum[idx])
    # ...and a shadow is on the DARK SIDE. Every tonal step in a painting borders a lighter one of
    # its own hue, so the pair test alone called four zones in five shade and the hatch went back
    # over everything, killing what should be behind it. Only zones below
    # this percentile of the picture's own lightness may be shade; a step on the lit side is a
    # gradient, and the wash already carries it.
    # A FLAT FIELD IS NOT A SHADOW, however dark it is. Shade is a tonal step within something that
    # is modeled; a plain background is a color. Without this, an art nouveau panel's dark blue
    # ground passed every other test and came out under a black cross-hatch net (too much
    # hatching in general). Measured as the mean gradient INSIDE the
    # zone, away from its edges: a modeled cheek has one, a flat ground does not.
    interior = np.zeros(n, np.float64)
    for i in range(n):
        if sizes[i]:
            zi = N.bool_img(lab_img == i)
            core = _erode(zi, 3)
            sel_i = (N.view(core) != 0) if N.count(core) else (lab_img == i)
            interior[i] = float(grad[sel_i].mean()) if sel_i.any() else 0.0
    # THE CUT IS TAKEN OVER THE ZONES THAT CAN BE SHADE, not over every painted pixel. Over every
    # pixel, a flat dark field covering most of a picture dragged the percentile inside itself -- a
    # koi pond with 62% near-black water put the cut at L* 17, the water was then excluded as a flat
    # field, and the picture came out with ZERO hatch lines. Over the modeled zones the same picture
    # cut at L* 60 and drew 332. Measured on 21 pictures: flat and line art unchanged; the Klein
    # look unchanged (713 -> 715); dark-dominated and tonal pictures gain hatch (chess 63 -> 641,
    # portrait 47 -> 302); two paintings lose some (rhino 250 -> 0, wave 338 -> 149).
    live = flat_lab >= 0
    modeled = np.flatnonzero(interior >= K.SHADOW_MIN_INTERNAL_GRAD)
    pop = (live & np.isin(flat_lab, modeled)) if len(modeled) else live
    if not pop.any():
        pop = live
    l_cut = float(np.percentile(lab_all[pop][:, 0], K.SHADOW_L_PCT)) if pop.any() else 50.0
    rep["l_cut"] = round(l_cut, 1)
    shade = np.zeros(n, bool)
    for cd, c in counts.items():
        if c < K.SHADOW_MIN_BORDER:
            continue
        rep["pairs"] += 1
        i, j = cd // n, cd % n
        if not sizes[i] or not sizes[j]:
            continue
        dark, light = (i, j) if means[i][0] < means[j][0] else (j, i)
        if means[light][0] - means[dark][0] < K.SHADOW_L_STEP:
            continue                                   # not a lightness step at all
        ca = math.hypot(means[dark][1], means[dark][2])
        cb = math.hypot(means[light][1], means[light][2])
        if min(ca, cb) >= K.SHADOW_MIN_CHROMA:
            ha = math.degrees(math.atan2(means[dark][2], means[dark][1]))
            hb = math.degrees(math.atan2(means[light][2], means[light][1]))
            if abs((ha - hb + 180.0) % 360.0 - 180.0) > K.SHADOW_HUE_TOL:
                continue                               # two different paints meeting: not shade
        if soft_sum[cd] / c > K.SHADOW_MAX_EDGE:
            continue                                   # a hard edge: drawn, not shaded
        if means[dark][0] > l_cut:
            continue                                   # on the lit side: a gradient, not a shadow
        if interior[dark] < K.SHADOW_MIN_INTERNAL_GRAD:
            continue                                   # a flat field: a color, not a shadow
        shade[dark] = True
    rep["shadow"] = int(shade.sum())
    out = np.zeros((gh, grid_w), bool)
    for i in np.flatnonzero(shade).tolist():
        out |= lab_img == i
    return out, rep


def cel_regions(gray, mask, min_area_px, bands=None):
    """Posterise darkness into CEL_BANDS, conservatively -> [(band_idx, L-mask)].

    Blur first (shading is smooth; texture and grain are not), threshold each
    band, median-filter, then keep only components at least min_area_px. Pixels
    outside `mask` (paper, color fills, ink lines) never shade.
    """
    g = gray.filter(ImageFilter.GaussianBlur(CEL_BLUR))
    w, h = g.size
    d = 1.0 - np.asarray(g, np.float64) / 255.0
    inside = N.view(mask) != 0
    out = []
    bands = bands or [(lo, hi) for lo, hi, _, _ in CEL_BANDS]
    for bi, (lo, hi) in enumerate(bands):
        m = N.bool_img(inside & (d >= lo) & (d < hi))
        m = _median(m, CEL_MEDIAN)
        total = N.count(m)
        floor = int(CEL_SPECK_AREA * w * h) if total >= CEL_FIELD_COVER * w * h else min_area_px
        keep = Image.new("L", (w, h))
        for area, cm, off in components(m, 1, floor):
            keep.paste(cm, (off[0], off[1]), cm)
        out.append((bi, keep))
    return out


def uniform_hatch(mask, angles, pitch_g, min_len_g):
    """Straight parallel lines at ONE pitch, clipped to `mask`, for each angle.

    Sampled exactly as the original: the `t` and `d` sequences are still built by
    repeated addition (a float sum is not its closed form, and the last sample of a
    scan line would move), but they are built ONCE and the samples are then tested
    against the mask in one array. A run ends after three samples outside -- what
    `gap * 0.6 > HATCH_BRIDGE_G` counts -- so a run boundary is a gap of >= 4 in the
    indices of the samples that are inside.
    """
    w, h = mask.size
    mp = N.view(mask) != 0
    diag = math.hypot(w, h)
    cx, cy = w / 2.0, h / 2.0
    half = diag / 2.0
    ts, t = [], -half
    while t <= half:
        ts.append(t)
        t += 0.6
    ds, d = [], -half
    while d <= half:
        ds.append(d)
        d += pitch_g
    if not ts or not ds:
        return []
    T = np.array(ts, np.float64)
    D = np.array(ds, np.float64)
    out = []
    for ang in angles:
        a = math.radians(ang)
        ux, uy = math.cos(a), math.sin(a)
        nx, ny = -uy, ux
        X = (cx + nx * D)[:, None] + ux * T[None, :]
        Y = (cy + ny * D)[:, None] + uy * T[None, :]
        xi = X.astype(np.int64)                      # int() truncates toward zero, as astype does
        yi = Y.astype(np.int64)
        ok = (xi >= 0) & (xi < w) & (yi >= 0) & (yi < h)
        inside = np.zeros(ok.shape, np.bool_)
        inside[ok] = mp[yi[ok], xi[ok]]
        for i in range(D.size):
            idx = np.flatnonzero(inside[i])
            if idx.size == 0:
                continue
            cut = np.flatnonzero(np.diff(idx) >= 4)   # 3 samples outside ends a run
            starts = np.concatenate(([0], cut + 1))
            ends = np.concatenate((cut, [idx.size - 1]))
            for s, e in zip(starts.tolist(), ends.tolist()):
                p0 = (float(X[i, idx[s]]), float(Y[i, idx[s]]))
                p1 = (float(X[i, idx[e]]), float(Y[i, idx[e]]))
                if math.hypot(p1[0] - p0[0], p1[1] - p0[1]) >= min_len_g:
                    out.append([p0, p1])
    return out


# ---------------------------------------------------------------- decompose
def decompose(src, w, h, detail=1.0, origin=(0.0, 0.0), tone=True, shade=SHADE_BUDGET, black_l=BLACK_L, chroma_min=CHROMA_MIN, grid_max=None):
    """Image -> strokes fitted into a w x h box whose top-left is `origin`.

    The box is a maximum: the source's aspect is kept and the drawing is centered in the box
    (`params["drawn"]` is its size, `params["extent"]` the ink's bounding box with pen widths).
    A smaller box means a coarser drawing -- pens have a minimum width and hatch a fixed pitch.

    Returns (strokes, params, seconds). Each stroke is the rm_art tuple
    `(pts, widths, tool, color, rgba)` in PAGE px, ready for `Drawing.strokes`
    or a rigid place_asset() -- never for rescaling. List order is draw order:
    highlighter fills first, then color lines and marker fills (large to small), black
    components, tone hatching.
    THERE IS ONE PATH. UI mode -- the pixel-exact one, with OCR lettering and no hatch -- was
    removed: `rm_images.insert` puts the real picture on the page, so a screen or a
    chart that has to be exact is not drawn at all. `detail` > 1 keeps smaller components and
    hatches finer. `shade` caps the hatched
    fraction of the box; the lightest tones are dropped first. `black_l` is the L* below
    which achromatic ink fills solid instead of hatching (see BLACK_L). `chroma_min` is the
    Lab chroma a cluster needs before it may use a color pen (see CHROMA_MIN).
    """
    t0 = time.perf_counter()
    im = Image.open(src).convert("RGB")
    # the grid is the SOURCE's resolution (capped at GRID_MAX, never upsampled): the planner chose
    # the source, so its pixels are the detail on offer. Tying the grid to the box (box/2.2)
    # threw away half of a 512-px source at an 800-px box and dropped a cartoon's
    # outlines at 400 px (hold-out set: motorcycle spokes, robot outlines)
    # `grid_max` (default GRID_MAX 720) caps the grid for cost; a chart or a screen needs its
    # source resolution -- downsampling a 1024-px chart to 720 turned 1-px lines and 12-px text
    # into gray that every thin-gray rule then dropped (66 strokes for a whole line chart)
    # THE GRID IS THE SOURCE, EXACTLY (see rmb_params). `grid_max` only when asked for.
    if grid_max:
        grid_w = int(min(grid_max, im.width))
        gh = max(1, int(round(grid_w * im.height / im.width)))
    else:
        grid_w, gh = int(im.width), int(im.height)
    # UPSCALE TO THE PAGE, once, before anything is measured (see rmb_params). The grid is still
    # the source: it is resampled up -- by the LANCZOS below, which is the high-quality AA -- so
    # that one grid px is at most one PAGE px, and every grid-px length moves with it (_UP).
    global _UP
    _UP = 1.0
    if K.UPSCALE_TO_PAGE and not grid_max:
        f = min(float(w) / grid_w, float(h) / gh)
        f = min(f, K.UPSCALE_MAX, math.sqrt(K.UPSCALE_MAX_PX / float(grid_w * gh)))
        if f >= K.UPSCALE_MIN:
            _UP = f
            grid_w, gh = int(round(grid_w * f)), int(round(gh * f))
    # the box is a MAXIMUM: the drawing keeps the source's aspect and is centered in it (place()),
    # so page px per grid px is the binding side's scale. Taking w/grid_w drew a square
    # source in a 1404x400 strip with widths and thresholds sized for 1404 px.
    ppg0 = min(float(w) / grid_w, float(h) / gh)
    # the box bounds the INK, not the centerlines: a stroke on the drawing's edge bleeds half its
    # width (the fill band is 4 grid px, the ring bloats half a grid px) -- measured 1-3 page px
    # outside the box before this. Fit the drawing into the box inset by that margin.
    margin = max(EDGE_MARGIN_PAGE, 2.5 * ppg0)
    ppg = min((w - 2 * margin) / grid_w, (h - 2 * margin) / gh)
    small = im.resize((grid_w, gh), Image.LANCZOS)
    p_wp = None
    if K.V69_WHITE_POINT:
        small, p_wp = white_point(small)
    ox, oy = origin
    box = (ox + margin, oy + margin, ox + w - margin, oy + h - margin)
    p = dict(grid=[grid_w, gh], ppg=round(ppg, 3), detail=detail, white_point=p_wp,
             upscale=round(_UP, 2),
             drawn=[round(grid_w * ppg, 1), round(gh * ppg, 1)])          # the ink's box inside w x h

    # the flesh gate is told this picture's cast BEFORE anything is classified, and forgets it
    # after -- the offset is module state read by _skin_key/_skin_px inside quantize() and the
    # soft-edge pass. The pixels are not changed.
    global _SKIN_HUE_OFFSET, _DARK_FIELD, _FLOW, _WHITE_FLOOR
    _SKIN_HUE_OFFSET, _cast = skin_cast_offset(small)
    p["skin_cast"] = dict(ab=[round(_cast[0], 2), round(_cast[1], 2)], offset_deg=round(_SKIN_HUE_OFFSET, 1))
    _WHITE_FLOOR = white_floor(small)
    p["white_floor"] = None if _WHITE_FLOOR is None else [round(v, 1) for v in _WHITE_FLOOR]
    _DARK_FIELD, _df_share, _df_big = dark_field(small)
    p["dark_field"] = dict(on=_DARK_FIELD, dark=round(_df_share, 3), biggest=round(_df_big, 3))
    # WHAT "DARK" MEANS DEPENDS ON THE PICTURE, and the decomposer already measures which kind it
    # is looking at. In LINE ART dark is ink: a black outline is black and must be filled solid.
    # In a PAINTING OR PHOTOGRAPH dark is color in shadow -- the corners of an art nouveau panel
    # are gold scrollwork on teal at L* 7, and calling that ink painted 80% of it solid black and
    # threw the picture away. The panel's own black is L* 30, so it can show that color; we just
    # have to stop discarding it. Measured either way: at 12 the panel's corners render (5,3,1)
    # against a source of (31,21,11); at 3 they render (18,11,5) and the whole image's error
    # falls from -12 to -4. On flat art the same change costs a quarter of the line weight, which
    # is why it is conditional and not a new default.
    if _DARK_FIELD:
        black_l = K.BLACK_L_FIELD
    p["black_l"] = black_l
    try:
        masks, cover = quantize(small, black_l=black_l, chroma_min=chroma_min, detail=detail, ppg=ppg)
    except BaseException:
        _SKIN_HUE_OFFSET, _DARK_FIELD, _FLOW, _UP = 0.0, False, None, 1.0
        raise
    lumimg_ = small.convert("L")
    p["cover"] = cover
    p["black_l"], p["chroma_min"] = black_l, chroma_min
    # one image-wide XDoG ridge skeleton, the proven centerline source
    resp, rsize = LA.xdog(src, width=grid_w, sigma=XDOG_SIGMA_REF * grid_w / 340.0)
    ridge = LA.thin(LA.mask(resp, rsize, XDOG_INK))
    p["ridge_px"] = int(np.count_nonzero(ridge))
    flow = None
    if K.V69_FLOW_HATCH or K.V69_FLOW_FILL:
        from paperdaemon.pipeline.decompose.reference import rm_flow as FL
        _FLOW = FL.field(lumimg_, sigma=K.FLOW_SIGMA, pre=K.FLOW_PRE_BLUR,
                         min_coherence=K.FLOW_MIN_COHERENCE, fallback_deg=CEL_BANDS[0][2][0])
        p["flow_coherent"] = round(float((_FLOW[2] >= K.FLOW_MIN_COHERENCE).mean()), 3)
        if K.V69_FLOW_HATCH:
            flow = _FLOW
    min_span = max(2, int(round(_gu(MIN_SPAN_G) / detail)))
    # A COLOR FLECK IS TOO SMALL WHEN THE PEN CANNOT DRAW IT -- a page question, like draw_min,
    # not a fixed count of source pixels. At 8 grid px a third of a test panel (34.4%) fell below the
    # floor and was absorbed into whatever zone it touched, which on a dark painting means the
    # darker one: petals, veins and highlights went into the hair and the picture came back muddy.
    # The pen's finest stroke is HL_MIN_PAGE, and anything that wide can be drawn.
    min_span_col = max(2, int(round(K.HL_MIN_PAGE / ppg / detail)))
    # WHAT IS TOO SMALL TO DRAW IS A PAGE QUESTION, NOT A SOURCE QUESTION. A two-pixel feature in a
    # 200-px source is twelve page pixels and plainly visible; the same two pixels in a 1024-px
    # source are two page pixels and are noise. The old floor was in source pixels and deleted a
    # portrait's eye at one end while making photographic grain into strokes at the other.
    draw_min = max(2, int(round(K.DRAW_MIN_PAGE / ppg)))
    min_len_g = max(_gu(3.0) / detail, MIN_LEN_PAGE / ppg / detail)   # detail > 1 keeps shorter pieces: a glyph's crossbar
    out = []
    p["components"] = {}

    # color: per component, largest first so small regions paint over big ones.
    # Flecks are judged by AREA: a chromatic component must cover a real patch.
    # the anti-aliased fringe between a color and its outline belongs to the color: grow each
    # color region one grid px into ACHROMATIC non-paper (never onto paper, never into another
    # color) and let the line be drawn on top. Without this a white halo ran between every
    # fill and its outline (flat-skull: 'the edge of the fill').
    ach = Image.new("L", (grid_w, gh))
    for k in ("black", "tone", "_ink"):
        if masks.get(k) is not None:
            ach = ImageChops.lighter(ach, masks[k])
    color_keys = [k for k in masks if k not in ("black", "tone", "_ink")]
    if color_keys and masks.get("tone") is not None:
        # light TONE pockets enclosed by color become the nearest wash of their own color
        union = Image.new("L", (grid_w, gh))
        for k in color_keys:
            union = ImageChops.lighter(union, masks[k])
        inv = ImageChops.invert(ImageOps.expand(union, 1, 0))
        tone_a = N.view(masks["tone"]) != 0
        lum_a = np.asarray(lumimg_, np.uint8)
        sm_a = np.asarray(small, np.uint8)
        absorbed = {}
        for a_, pm, poff in components(inv, 1, 0):
            if poff[0] <= 0 or poff[1] <= 0 or poff[0] + pm.width >= grid_w + 2 or poff[1] + pm.height >= gh + 2:
                continue                                   # touches the outside: not enclosed
            yy, xx = np.nonzero(N.view(pm))
            gx, gy = xx + poff[0] - 1, yy + poff[1] - 1
            ok = (gx >= 0) & (gx < grid_w) & (gy >= 0) & (gy < gh)
            gx, gy = gx[ok], gy[ok]
            sel = tone_a[gy, gx] & (lum_a[gy, gx] >= POCKET_L * 2.55)
            gx, gy = gx[sel], gy[sel]
            n_ = gx.size
            if n_ < 0.5 * a_:
                continue                                   # mostly paper or dark: leave it
            cols = sm_a[gy, gx]
            r_ = int(cols[:, 0].sum()) / n_; g_ = int(cols[:, 1].sum()) / n_; b_ = int(cols[:, 2].sum()) / n_
            L, a, b = _lab((r_, g_, b_))
            if K.V70_TRUE_COLOR:
                key = ("rgb", _tc_key((int(round(r_)), int(round(g_)), int(round(b_)))))
            else:
                key = min(_FILL_LAB, key=lambda e: math.sqrt((e[1][0] - L) ** 2 + (e[1][1] - a) ** 2 + (e[1][2] - b) ** 2) - (HL_PREFERENCE if e[0][0] == "hl" else 0.0))[0]
            absorbed.setdefault(key, []).append((gx, gy))
        if absorbed:
            tone_arr = N.arr(masks["tone"])
            for key, chunks in absorbed.items():
                if key not in masks:
                    masks[key] = Image.new("L", (grid_w, gh))
                ka = N.arr(masks[key])
                for gx, gy in chunks:
                    ka[gy, gx] = 255
                    tone_arr[gy, gx] = 0
                masks[key] = N.img(ka)
            masks["tone"] = N.img(tone_arr)
            p["absorbed_tone_px"] = sum(int(gx.size) for v in absorbed.values() for gx, _gy in v)
        color_keys = [k for k in masks if k not in ("black", "tone", "_ink")]
    if len(color_keys) > 1:
        # pockets of paper or tone enclosed by color take the color of their surroundings: a
        # canopy split across several device colors would otherwise show paper between them
        union = Image.new("L", (grid_w, gh))
        for k in color_keys:
            union = ImageChops.lighter(union, masks[k])
        pockets = ImageChops.subtract(_fill_holes(ImageOps.expand(union, 1, 0), ppg).crop((1, 1, grid_w + 1, gh + 1)), union)
        if K.SUBCELL_GEOMETRY:
            # Enclosure and output size do not turn PAPER into a color.
            # The legacy pocket filler swallowed white muzzle gaps, glyph
            # counters and highlights when their area fell below its floor.
            # Only already-classified tone remains eligible for this rule;
            # preserve paper and ink ownership before any stroke is planned.
            tone_m = masks.get("tone")
            if tone_m is None:
                # NO TONE ANYWHERE ON THIS PAGE -- a flat, fully saturated picture, which is
                # exactly what a chart or a coloring page is. Then no pocket is already-
                # classified tone and the rule excludes all of them. Indexing masks['tone']
                # here instead took the entire decomposition down with a KeyError; every other
                # reader in this block already asks with .get().
                pockets = Image.new("L", (grid_w, gh))
            else:
                pockets = ImageChops.multiply(pockets, tone_m)
        if pockets.getbbox() is not None:
            key_arrs = {k: N.arr(masks[k]) for k in color_keys}
            for a_, pm, poff in components(pockets, 1, 0):
                pa = N.view(pm) != 0
                ring_ = (N.view(_dilate(pm, _ker())) != 0) & ~pa
                gy, gx = _global_px(ring_, poff, grid_w, gh)
                best, best_n = None, 0
                for k in color_keys:
                    n_ = int(np.count_nonzero(key_arrs[k][gy, gx])) if gy.size else 0
                    if n_ > best_n:
                        best, best_n = k, n_
                if best is not None:
                    py, px_ = _global_px(pa, poff, grid_w, gh)
                    key_arrs[best][py, px_] = 255
            for k in color_keys:
                masks[k] = N.img(key_arrs[k])
    if color_keys and GAP_CLOSE_G > 0:
        # GAPS: tone (or ink, never paper) squeezed between color regions -- see GAP_CLOSE_G
        r_ = max(1, min(int(_gu(GAP_CLOSE_G)), int(round(GAP_CLOSE_PAGE / ppg))))
        union = Image.new("L", (grid_w, gh))
        for k in color_keys:
            union = ImageChops.lighter(union, masks[k])
        gap = ImageChops.subtract(_close(union, r_), union)
        gap_a = N.view(gap) != 0
        lum_a = np.asarray(lumimg_, np.uint8)
        sp_ = np.asarray(small.filter(ImageFilter.GaussianBlur(1.0)), np.uint8)   # smoothed color: no speckle
        paper_cut, ink_cut = int(round(PAPER_L * 2.55)), int(round(INK_L * 2.55))
        # a gap joins a class's REAL region: a fleck below the span floor is dropped later and must
        # not grow into a blob here (the teapot's shadow rim seeded gray dabs). Local density of the
        # anchors decides reach (BoxBlur(r) is non-zero within r) and, for dark pixels, ownership.
        dens = {}
        for k in color_keys:
            anchor = Image.new("L", (grid_w, gh))
            for a_, m_, off_ in components(masks[k], min_span_col):
                anchor.paste(255, (off_[0], off_[1]), m_)
            if anchor.getbbox():
                dens[k] = np.asarray(anchor.filter(ImageFilter.BoxBlur(r_)), np.uint8)
        n_gap = 0
        if dens:
            dkeys = list(dens)                                    # class order = the draw order
            D = np.stack([dens[k] for k in dkeys])
            active = gap_a & (lum_a < paper_cut) & (D.max(axis=0) > 0)
            ys_, xs_ = np.nonzero(active)
            if ys_.size:
                dcol = D[:, ys_, xs_]
                is_ink = lum_a[ys_, xs_] < ink_cut
                best_idx = np.full(ys_.size, -1, np.int64)
                if is_ink.any():
                    # ink: whoever surrounds it (the ink covers it). argmax takes the first
                    # maximum, as max(cands, key=...) does over the same class order
                    best_idx[is_ink] = np.argmax(dcol[:, is_ink], axis=0)
                nonink = ~is_ink
                if nonink.any():
                    # the nearest class color -- if it beats PAPER, which is what this pixel would
                    # otherwise be (a near-white bay of background must stay paper: flat-bicycle)
                    lab = _lab_rows(sp_[ys_[nonink], xs_[nonink]])
                    L, a, b = lab[:, 0], lab[:, 1], lab[:, 2]
                    bd = _sq(100.0 - L) + a * a + b * b          # reference: (100.0 - L) ** 2 + a * a + b * b
                    KL = np.array([_lab(_fill_rgba(k) if (isinstance(k, tuple) and k[0] == "rgb") else _FILL_RGB[k])
                           for k in dkeys], np.float64)
                    dd = (_sq(KL[:, 0:1] - L) + _sq(KL[:, 1:2] - a)) + _sq(KL[:, 2:3] - b)
                    dd = np.where(dcol[:, nonink] > 0, dd, np.inf)
                    am = np.argmin(dd, axis=0)
                    win = dd[am, np.arange(am.size)] < bd
                    idx = np.flatnonzero(nonink)
                    best_idx[idx[win]] = am[win]
                have = best_idx >= 0
                n_gap = int(np.count_nonzero(have))
                for j, k in enumerate(dkeys):
                    sel = have & (best_idx == j)
                    if sel.any():
                        ka = N.arr(masks[k])
                        ka[ys_[sel], xs_[sel]] = 255
                        masks[k] = N.img(ka)
        p["gap_px"], p["gap_r"] = n_gap, r_
    # IS THIS PICTURE MADE OF COLOR? That, not "does it have a dark field", is what separates a
    # painting from a pen drawing. `_DARK_FIELD` is true of the oak and the skull as well, because
    # they have big black masses, so gating on it cost them their ink. A painting's dark areas are
    # shadow and must be washed; a drawing's are ink and must be filled.
    _chroma_px = 0
    for k_ in masks:
        if isinstance(k_, tuple) and k_[0] == "rgb":
            r_, g_, b_ = k_[1]
            L_, a2_, b2_ = _lab((float(r_), float(g_), float(b_)))
            if math.hypot(a2_, b2_) >= K.CHROMA_MIN:
                _chroma_px += N.count(masks[k_])
    painterly = (_chroma_px / float(grid_w * gh)) >= K.PAINTERLY_CHROMA_SHARE
    p["painterly"] = dict(on=painterly, chroma=round(_chroma_px / float(grid_w * gh), 3))
    from paperdaemon.pipeline.decompose.reference import rmb_resolution as RES
    p["tonal_ink"] = RES.tonal_ink(masks, small, black_l, sys.modules[__name__])
    color_keys = [k for k in masks if k not in ("black", "tone", "_ink")]
    p["page_label_plan"] = RES.coarsen_washes(masks, ppg, sys.modules[__name__])
    # The old whole-weak-union absorber can reject a giant mixed-color
    # component and leave tens of thousands of subpixel islands. Tiny targets
    # already have a complete page-scale label plan; do not reassign it again.
    p["absorb"] = (absorb_specks(masks, min_span_col, grid_w, gh, small)
                   if p["page_label_plan"]["cell_source_px"] == 1 else {"page_scale_labels": True})
    # A LINE'S HALO IS NOT A WASH. Every drawn line has an anti-aliased gray skirt, and under the
    # color ladder that skirt is a near-neutral zone like any other -- so a black-and-white line
    # drawing came back with 17,850 wash strokes laid over it, which is the gray haze that made
    # the line work look blurry. A gray that is a REGION is real tone and is painted; a gray that
    # does not survive an opening is the skirt of a line, and belongs to the line.
    if K.GRAY_HALO_OPEN > 0 and "black" in masks:
        # the halo is the band WITHIN a pixel or two OF THE INK, not "any thin gray". Judging it by
        # thinness deleted a pencil drawing, which is nothing but thin gray -- tonal-hand went to
        # 34% blank. A gray inside this band beside a black line is that line's anti-aliasing; the
        # same gray anywhere else is somebody's shading and gets painted.
        skirt = N.view(_dilate(masks["black"], _ker(K.GRAY_HALO_OPEN))) != 0
        n_halo = 0
        for k_ in [k for k in masks if isinstance(k, tuple) and k[0] == "rgb"]:
            r_, g_, b_ = k_[1]
            L_, a_, b2_ = _lab((float(r_), float(g_), float(b_)))
            if math.hypot(a_, b2_) >= K.CHROMA_MIN or L_ <= K.TC_INK_L:
                continue                       # a real color, or ink's own range: leave it alone
            m_ = masks[k_]
            # PER COMPONENT, not per pixel. A line's skirt lies ENTIRELY beside its line; a real
            # thin gray line only touches ink where it meets one, and the rest of it runs away
            # across the picture. Cutting every gray pixel that happens to sit beside ink took the
            # ship's rigging with it.
            keep_a = np.zeros((gh, grid_w), bool)
            for _a3, cm3, off3 in components(m_, 1, 0):
                sub = N.view(cm3) != 0
                y0, x0 = max(0, off3[1]), max(0, off3[0])
                y1, x1 = min(gh, off3[1] + cm3.height), min(grid_w, off3[0] + cm3.width)
                sel3 = sub[y0 - off3[1]:y1 - off3[1], x0 - off3[0]:x1 - off3[0]]
                if not sel3.any():
                    continue
                inside = skirt[y0:y1, x0:x1][sel3].mean()
                if inside >= K.GRAY_HALO_SHARE:
                    n_halo += int(sel3.sum())          # all of it sits beside ink: it is a skirt
                else:
                    keep_a[y0:y1, x0:x1] |= sel3       # it goes somewhere: it is a line
            masks[k_] = N.bool_img(keep_a)
        p["gray_halo_px"] = n_halo
    # A DARK COLOR CASTS A RAMP TOO. The rule above gives a gray band beside BLACK INK back to the
    # line it belongs to; the same band beside a dark COLOR was left in `tone` and drawn as black
    # line work. On a 200 px fox the navy outline's own anti-aliasing (a 20% blend toward white is
    # L* 30, chroma 9: neutral for its darkness, and under INK_L) came out as a string of black
    # beads threaded along a navy line. A ramp belongs to what it ramps from, whatever color that
    # is, so it is handed to the nearest such zone instead of being drawn.
    if K.TONE_RAMP_TO_COLOR and masks.get("tone") is not None:
        dark_keys = [k for k in masks if isinstance(k, tuple) and k[0] == "rgb"
                     and _lab([float(v) for v in k[1]])[0] < K.TONE_RAMP_L]
        tone_a = N.view(masks["tone"]) != 0
        if dark_keys and tone_a.any():
            from scipy import ndimage as _nd
            dark = np.zeros((gh, grid_w), bool)
            for k_ in dark_keys:
                dark |= N.view(masks[k_]) != 0
            skirt = N.rank_ext(dark.astype(np.uint8), 3, True) != 0
            lb, n_ = _nd.label(tone_a, structure=np.ones((3, 3), np.uint8))
            if n_:
                tot = np.bincount(lb.reshape(-1), minlength=n_ + 1)
                hit = np.bincount(lb[tone_a & skirt], minlength=n_ + 1)
                ramp_lbl = np.zeros(n_ + 1, bool)
                ramp_lbl[1:] = (hit[1:] / np.maximum(1, tot[1:])) >= K.GRAY_HALO_SHARE
                ramp = ramp_lbl[lb] & tone_a
                if ramp.any():
                    idx = _nd.distance_transform_edt(~dark, return_distances=False, return_indices=True)
                    owner = np.full((gh, grid_w), -1, np.int32)
                    for i_, k_ in enumerate(dark_keys):
                        owner[N.view(masks[k_]) != 0] = i_
                    give = owner[tuple(idx)]
                    masks["tone"] = N.bool_img(tone_a & ~ramp)
                    for i_, k_ in enumerate(dark_keys):
                        add = ramp & (give == i_)
                        if add.any():
                            masks[k_] = N.bool_img((N.view(masks[k_]) != 0) | add)
                    p["tone_ramp_px"] = int(ramp.sum())
    # EVERY ZONE GROWS INTO ITS NEIGHBOR. Painted edge-exact, two adjacent zones leave the pixel on
    # the boundary to neither, and the page shows a hairline of paper along every edge in the
    # picture -- measured on a painting, 2.3% of the box white, most of it in filaments. Two
    # colors overlapping by a pixel is invisible; a white line between them is not. The grow used
    # to reach only into the achromatic mask; it reaches into ANYTHING THAT IS NOT PAPER now.
    nonpaper = Image.new("L", (grid_w, gh))
    for k_ in masks:
        if k_ != "_ink":
            nonpaper = ImageChops.lighter(nonpaper, masks[k_])
    col_line_mask = Image.new("L", (grid_w, gh))
    for k in color_keys:
        kinds = {"line": 0, "fill": 0}
        # ONE CALL FOR THE WHOLE ZONE. The painter traces every contour it finds at each depth, so
        # a class with two hundred scattered pieces costs one distance transform instead of two
        # hundred. Measured on the ship: this loop ran 8,039 times for one picture and accounted
        # for 5.3 of its 7.3 seconds. (No floor either: absorb_specks has already handed every
        # sub-threshold piece to a neighbor, so what is left is a zone or a feature.)
        for area, m, off in ([(N.count(masks[k]), masks[k], (0, 0))] if K.ZONE_AT_ONCE
                             else components(masks[k], 1, 0)):
            if K.COLOR_GROW_G > 0:
                grow = ImageChops.multiply(_dilate(m, _ker(K.COLOR_GROW_G)),
                                           nonpaper.crop((off[0], off[1], off[0] + m.width, off[1] + m.height)))
                m = ImageChops.lighter(m, grow)
            st, kind, dr_ = draw_component(area, m, k, ppg, box, min_len_g, offset=off, grid=(grid_w, gh), ridge=ridge)
            out.extend(st)
            if kind == "line":
                col_line_mask.paste(dr_, (off[0], off[1]), dr_)     # a color LINE is ink: do not contour it twice
            kinds[kind] = kinds.get(kind, 0) + 1
        p["components"][_kname(k)] = kinds

    # achromatic INK, three passes:
    #   lines  -- thin components of black UNION gray, so an anti-aliased line is one
    #             component; colored by its own mean luminance
    #   fills  -- thick components of the TRUE-BLACK pixel mask only. A connected dark
    #             region's mean is not its content: a coat at L*5 joined to a face at
    #             L*35 must not fill the face
    #   hatch  -- everything achromatic left over, specks included, density by darkness
    ink = masks.get("_ink")
    p["tone_lines"] = 0
    # `is not None`, not "has ink". The hatch pass lives inside this block, and a picture with
    # tone but no achromatic ink -- a dark COLOR ground and colored ornament, nothing black --
    # was never shaded at all: its ground came out as a flat pale wash. components() of an empty
    # mask yields nothing, so the line and fill passes are unchanged when there is no ink.
    if ink is not None:
        lumimg = small.convert("L")
        lum_a = np.asarray(lumimg, np.uint8)
        hatch_mask = None
        # SHADING GOES OVER COLOR. Hatch confined to the achromatic classes looks like
        # scratching on bare paper; every painted class is shadeable and the darkness bands decide
        # where it actually lands.
        # tone already carries the base pixels (quantize puts a ("base", key) pixel in BOTH), so
        # this is "the achromatic classes and the grays", and never a color fill
        # HATCH IS SHADING, AND SHADING IS WHAT THE ZONES SAY IS SHADED (see shadow_zones).
        # Before this the mask was "everything achromatic", which is why hatch ended up over
        # everything light and dark alike. What hatches now is: solid black, the achromatic tone
        # that belongs to no color zone, and every color zone that is the same hue as a lighter
        # neighbor across a soft border.
        colored = Image.new("L", ink.size)
        for k_ in masks:
            if k_ not in ("black", "tone", "_ink"):
                colored = ImageChops.lighter(colored, masks[k_])
        hatch_mask = masks["black"].copy() if "black" in masks else Image.new("L", ink.size)
        # ON A PHOTOGRAPH OR PAINTING, ONLY WHAT THE ZONES SAY IS SHADE GETS HATCHED. The
        # achromatic leftovers are hatched too on LINE ART, where they are the whole picture and
        # hatching is the only tone available -- but on a picture made of color zones they are
        # scraps between zones, and hatching them put a mark over 46% of a portrait and 61% of a
        # chess board: hatching was overused on photoreal pictures.
        if "tone" in masks:
            hatch_mask = ImageChops.lighter(hatch_mask, ImageChops.subtract(masks["tone"], colored))
        # DARK GRAY THAT IS A REGION GETS PAINT. The achromatic range between the ink core and
        # mid-gray is a LINE class: it is drawn where it is line-shaped and otherwise not at all,
        # so a tonal picture came out as hatch over bare paper. Washing all of it instead fattened
        # every line by its own anti-aliased halo (the violin). The difference is shape: what
        # survives an opening is a REGION and is washed in its own color; what does not is the
        # ramp beside a line and belongs to the line.
        if K.TONE_REGION_WASH and "tone" in masks:
            body = ImageChops.subtract(_erode(masks["tone"], _ker(K.TONE_REGION_OPEN)), Image.new("L", ink.size))
            body = ImageChops.multiply(_dilate(body, _ker(K.TONE_REGION_OPEN)), masks["tone"])
            body = ImageChops.subtract(body, colored)
            if "black" in masks:
                body = ImageChops.subtract(body, masks["black"])
            n_tw = 0
            if body.getbbox() is not None:
                rgb_g = np.asarray(small.convert("RGB"), np.uint8)
                for _a, bm, boff in components(body, draw_min, K.DRAW_MIN_AREA):
                    y0, x0 = max(0, boff[1]), max(0, boff[0])
                    y1, x1 = min(gh, boff[1] + bm.height), min(grid_w, boff[0] + bm.width)
                    sel_ = (N.view(bm) != 0)[y0 - boff[1]:y1 - boff[1], x0 - boff[0]:x1 - boff[0]]
                    if not sel_.any():
                        continue
                    mrgb = tuple(int(v) for v in rgb_g[y0:y1, x0:x1][sel_].mean(axis=0))
                    out.extend(_fill_region_hl(bm, mrgb, ppg, box, offset=boff, grid=(grid_w, gh)))
                    n_tw += 1
            p["tone_wash"] = n_tw
        if K.SHADOW_HATCH:
            sh, sh_rep = shadow_zones(masks, small, grid_w, gh)
            p["shadow"] = sh_rep
            hatch_mask = ImageChops.lighter(hatch_mask, N.bool_img(sh))
        # WHAT GETS FILLED IS THE WHOLE INK MASK, not just its black core. With the line path off,
        # `tone` -- a line's anti-aliased body, which on a low-resolution source IS most of the
        # line -- was never drawn by anything: measured, the ink strokes covered only 74.6% of the
        # ink mask, and the quarter that was missing is what reaches the page as a dashed outline.
        # ...BUT ONLY ON LINE ART. On a picture with a dark field the ink mask is not line work, it
        # is the shadows: filling all of it with marker blacked out the corners of a panel and
        # a woman's hair. There, only the true black core fills and the rest is washed as tone.
        # THE WHOLE INK MASK, ALWAYS. Thin ink is line work in any picture -- a car's A-pillar, an
        # eyelash, a rigging line -- and leaving it to the wash loses it. What must NOT happen on a
        # painting is filling a thick dark MASS with black marker, and that is handled below by
        # thickness (BLACK_MASS_THICK_PAGE), which is the real distinction: a mass is shadow, a
        # thin run is a line, and that is true whatever kind of picture it is.
        black_left = (ink.copy() if K.INK_AS_FILL and ink is not None
                      else (masks["black"].copy() if "black" in masks else None))
        kinds = {"line": 0, "fill": 0}
        line_mask = Image.new("L", (grid_w, gh))
        fill_mask = Image.new("L", (grid_w, gh))     # black regions actually filled, for the contour pass
        for area, m, off in components(ink, min_span):
            lum = _mean_lum(lum_a, m, off, 50.0)
            st, kind, drawn = draw_component(area, m, PenColor.BLACK, ppg, box, min_len_g, tone=True,
                                             offset=off, grid=(grid_w, gh), lum=lum, ridge=ridge)
            if kind == "line":
                # only the LINE parts leave the fill/hatch masks; a thick part stays for them
                out.extend(st)
                hatch_mask.paste(0, (off[0], off[1]), drawn)
                line_mask.paste(drawn, (off[0], off[1]), drawn)
                if black_left is not None:
                    black_left.paste(0, (off[0], off[1]), drawn)
                kinds["line"] += 1
        if black_left is not None:
            lab_small = None
            kinds["dark_color"] = 0
            # NOTHING IS DROPPED HERE EITHER. A black speck under the span floor was simply
            # discarded, and in a painting those specks are eyes, nostrils and detail -- measured
            # as dark unpainted pixels scattered through every render.
            # ...but a speck the pen cannot draw AT ITS TRUE SIZE, on a pixel some color zone is
            # already painting, is that color's edge and not a mark. At a 200 px source one page
            # pixel is six, so the anti-aliasing of a navy outline came out as 245 black dots
            # threaded along it. The test is both halves: too small to draw (draw_min, the page
            # question) AND already covered, so nothing can be left as paper by dropping it. A
            # speck on bare paper -- an eye, a nostril, the ship's finest rigging -- still stands.
            covered_by_color = None
            if K.INK_SPECK_ON_COLOR:
                covered_by_color = np.zeros((gh, grid_w), bool)
                for k_ in color_keys:
                    covered_by_color |= N.view(masks[k_]) != 0
            # WHICH DARK PIECES ARE INK (rmb_params.INK_CORE_MIN and the lines after it): the local density of the
            # core-less ink pieces is needed before any piece is judged, so it is measured here, once, over the whole
            # mask: pieces per INK_DENSITY_CELL_PAGE square, 3 x 3 cells smoothed, read at each piece's centroid
            ink_density = None
            if K.INK_CORE_MIN > 0 and "black" in masks:
                from scipy import ndimage as _ndi
                _bl = N.view(black_left) != 0
                _lbl, _n = _ndi.label(_bl, structure=_ndi.generate_binary_structure(2, 1))   # (not `_lab`: that is the Lab function)
                if _n:
                    _ids = np.arange(1, _n + 1)
                    _area = np.bincount(_lbl.ravel())[1:].astype(float)
                    _blackpx = np.bincount(_lbl.ravel(), weights=(N.view(masks["black"]) != 0).ravel())[1:]
                    _nocore = (_blackpx / np.maximum(_area, 1.0) < K.INK_CORE_MIN) & (_area * ppg * ppg > K.ABSORB_MAX_AREA)
                    _cell = max(4.0, K.INK_DENSITY_CELL_PAGE / ppg)
                    _hist = np.zeros((int(gh // _cell) + 2, int(grid_w // _cell) + 2))
                    if _nocore.any():
                        _cy, _cx = zip(*_ndi.center_of_mass(_bl, _lbl, _ids[_nocore]))
                        np.add.at(_hist, ((np.array(_cy) // _cell).astype(int), (np.array(_cx) // _cell).astype(int)), 1.0)
                    ink_density = (_ndi.uniform_filter(_hist, 3, mode="nearest"), _cell)
            for area, m, off in components(black_left, 1, 0):
                if covered_by_color is not None:
                    y0, x0 = max(0, off[1]), max(0, off[0])
                    y1, x1 = min(gh, off[1] + m.height), min(grid_w, off[0] + m.width)
                    sel_ = (N.view(m) != 0)[y0 - off[1]:y1 - off[1], x0 - off[0]:x1 - off[0]]
                    ys_, xs_ = np.nonzero(sel_)          # the component's OWN span: components()
                    if ys_.size:                          # crops carry a 1-px margin
                        span = max(int(ys_.max() - ys_.min()), int(xs_.max() - xs_.min())) + 1
                        if (span < draw_min
                                and covered_by_color[y0:y1, x0:x1][sel_].mean() >= K.INK_SPECK_COVERED):
                            continue
                # A BLACK REGION WITH A CONSISTENT FAINT TINT IS A DARK COLOR. Its mean
                # (a*, b*) over every source pixel it covers is measured; a faint olive or blue
                # that median-cut averaged out of the cluster means survives the average over
                # thousands of pixels. Such a region is painted as the wash of its hue and LEFT IN
                # the hatch mask, so the dense band cross-hatches it -- just blue with hatch
                # shading -- instead of one slab of black marker.
                # NOT UNDER TRUE COLOR. The rule disabled below takes a dark region's mean
                # tint and paints it with the NEAREST OF 29 FIXED WASH COLORS. On an art nouveau
                # panel that put rgb(190,234,254) -- the palette's pale blue -- across a third of
                # the picture, in 2818 strokes, under all the hatching. Under true color this
                # branch is never taken: the mass-as-its-own-color rule below runs after it, not
                # before. A region is painted ITS OWN COLOR.
                if False:   # the nearest-of-29-fixed-washes rule: gone, a region paints its own color
                    if lab_small is None:
                        lab_small = _lab_rows(np.asarray(small.convert("RGB"), np.uint8).reshape(-1, 3)).reshape(gh, grid_w, 3)
                    # components() crops carry a 1-px margin that can run past the grid edge:
                    # clip both the Lab window and the mask to the grid before pairing them
                    x0, y0 = max(0, off[0]), max(0, off[1])
                    x1, y1 = min(grid_w, off[0] + m.width), min(gh, off[1] + m.height)
                    sub = lab_small[y0:y1, x0:x1]
                    sel = (N.view(m) != 0)[y0 - off[1]:y1 - off[1], x0 - off[0]:x1 - off[0]]
                    if sel.any():
                        ma, mb = float(sub[..., 1][sel].mean()), float(sub[..., 2][sel].mean())
                        # judged AGAINST THE PICTURE'S CAST when there is one: under Qwen's yellow
                        # cast a ground at (0.6, 3.0) is neutral to the numbers and dark BLUE to the
                        # eye (simultaneous contrast) -- those areas should be seen as dark blue --
                        # and blue is what the cast-relative tint says it is.
                        # ...but a region with NO tint of its own is black under any cast: a pure
                        # (0, 0) block in a yellow-cast picture stays a black fill
                        if (K.DARK_REGION_CAST_RELATIVE and math.hypot(ma, mb) >= K.DARK_REGION_CHROMA_ABS
                                and math.hypot(*_cast) >= K.SKIN_CAST_DEADBAND):
                            ma, mb = ma - _cast[0], mb - _cast[1]
                        if math.hypot(ma, mb) >= K.DARK_REGION_CHROMA:
                            key = min((e for e in _FILL_LAB if e[0][0] == "hl"),
                                      key=lambda e: (e[1][1] - ma) ** 2 + (e[1][2] - mb) ** 2)[0]
                            for letter in key[1]:
                                out.extend(_fill_region_hl(m, HL_RGBA[letter], ppg, box, offset=off, grid=(grid_w, gh)))
                            # (true color does not reach here: a dark color is simply painted as itself)
                            kinds["dark_color"] += 1
                            p.setdefault("dark_colors", []).append([key[1], round(ma, 1), round(mb, 1), int(area)])
                            continue                       # stays in hatch_mask: the hatch carries the darkness
                # what is left of true black after the lines were taken is a REGION: fill it,
                # with rows sized to its thickness (measured; see fill_solid)
                # the reference implementation measures a `thick_page` here (a whole marching-squares
                # pass per black region) and hands it to fill_solid, which discards it. The
                # measurement is dropped; the strokes are bit-identical because the value was
                # never read.
                # A MASS IS NOT INK. A line's core is thin; a photograph's shadow is thick, and
                # filling it with solid marker is what turned a forest floor, a portrait's backdrop
                # and a castle's ground into black slabs. Measured on photo-forest: 37% of the
                # picture classified black, one component 29% of the grid. Anything thicker than
                # BLACK_MASS_THICK_PAGE is painted as a wash of ITS OWN color -- which for a
                # forest shadow is a dark brown, not black -- and left in the hatch mask so the
                # shading still carries its darkness.
                _c, per_ = _outline(m, m.width, m.height, 1.0)
                thick_page = (2.0 * area / per_ * ppg) if per_ else 0.0
                # A DARK PIECE WITHOUT A BLACK CORE IS NOT INK EITHER, unless it is a long line standing on its own
                # (see rmb_params.INK_CORE_MIN and the lines after it): the ink mask is every dark neutral pixel, and
                # on a painting that is the dark paint between brush marks, not a drawn line. The share of the piece
                # that is truly black (the 'black' class) decides first; a core-less piece is still ink when it is at
                # least INK_LINE_MIN_LEN_PAGE long and the core-less pieces around it are sparse. Otherwise it takes
                # the same path as a mass, a wash of its own color.
                no_core = False
                if ink_density is not None:
                    x0, y0 = max(0, off[0]), max(0, off[1])
                    x1, y1 = min(grid_w, off[0] + m.width), min(gh, off[1] + m.height)
                    if x1 > x0 and y1 > y0:
                        sel = (N.view(m) != 0)[y0 - off[1]:y1 - off[1], x0 - off[0]:x1 - off[0]]
                        n_sel = int(sel.sum())
                        if n_sel:
                            core = float((sel & (N.view(masks["black"]) != 0)[y0:y1, x0:x1]).sum()) / n_sel
                            if core < K.INK_CORE_MIN:
                                length_page = (per_ / 2.0 * ppg) if per_ else 0.0      # half the outline: the line's length
                                ys_, xs_ = np.nonzero(sel)
                                _h, _cell = ink_density
                                dens = _h[min(_h.shape[0] - 1, int((y0 + ys_.mean()) // _cell)), min(_h.shape[1] - 1, int((x0 + xs_.mean()) // _cell))]
                                no_core = not (length_page >= K.INK_LINE_MIN_LEN_PAGE and dens <= K.INK_LINE_MAX_DENSITY)
                if no_core or thick_page >= (K.BLACK_MASS_THICK_PAINT if painterly else K.BLACK_MASS_THICK_PAGE):
                    x0, y0 = max(0, off[0]), max(0, off[1])
                    x1, y1 = min(grid_w, off[0] + m.width), min(gh, off[1] + m.height)
                    sub = np.asarray(small.convert("RGB"), np.uint8)[y0:y1, x0:x1]
                    sel = (N.view(m) != 0)[y0 - off[1]:y1 - off[1], x0 - off[0]:x1 - off[0]]
                    if sel.any():
                        mrgb = tuple(int(v) for v in sub[sel].mean(axis=0))
                        out.extend(_fill_region_hl(m, mrgb, ppg, box, offset=off, grid=(grid_w, gh)))
                        kinds["no_core" if no_core else "mass"] = kinds.get("no_core" if no_core else "mass", 0) + 1
                        continue                      # stays in hatch_mask: the hatch carries it
                out.extend(fill_solid(m, PenColor.BLACK, ppg, box, offset=off, grid=(grid_w, gh)))
                hatch_mask.paste(0, (off[0], off[1]), m)
                fill_mask.paste(m, (off[0], off[1]), m)
                kinds["fill"] += 1
        # thin GRAY components are drawn lines too -- with the GRAY pen when light.
        # Without this, anything lighter than the ink core can only shade: a bicycle's
        # spokes and a skull's light sutures vanished.
        if "tone" in masks:
            halo0 = _dilate(line_mask, _ker())
            gray = ImageChops.subtract(masks["tone"], halo0)
            # detail > 1 admits fainter lines: a chart's grid and a table's rules sit at L* 80-90
            tl_cut = int(round(min(PAPER_L, TONE_LINE_L + 12.0 * (detail - 1.0)) * 2.55))
            gray = N.bool_img((N.view(gray) != 0) & (lum_a < tl_cut))
            kinds["gray_line"] = 0
            nonpaper = ImageChops.lighter(masks["tone"], ink)          # everything that is not paper: tone, ink...
            for k_ in masks:
                if k_ not in ("black", "tone", "_ink"):
                    nonpaper = ImageChops.lighter(nonpaper, masks[k_])   # ...and COLOR. A dark blob inside a wash is
            # (if color counted as paper here, then once dark colors stopped being ink an oak's
            # canopy shading was "thin gray that is not a line" and was dropped -- 0 hatch lines)
            # summed-area table: each strip's coverage is then four lookups instead of a scan
            npi = np.zeros((gh + 1, grid_w + 1), np.int32)
            np.cumsum(np.cumsum(N.view(nonpaper) != 0, axis=0, dtype=np.int32), axis=1, out=npi[1:, 1:])
            pad = max(3, int(round(10.0 / ppg)))

            def _covered(x0, y0, x1, y1):
                x0, y0, x1, y1 = max(0, x0), max(0, y0), min(grid_w, x1), min(gh, y1)
                n_ = (x1 - x0) * (y1 - y0)
                if n_ <= 0:
                    return None                                        # off the grid: no evidence either way
                return int(npi[y1, x1] - npi[y0, x1] - npi[y1, x0] + npi[y0, x0]) / float(n_)
            for area, m, off in components(gray, min_span):
                # context: the four strips just outside the component's box. Non-paper on three or
                # more sides -> enclosed -> texture of the surrounding region, not a line
                x0, y0, x1, y1 = off[0], off[1], off[0] + m.width, off[1] + m.height
                sides = [_covered(x0 - pad, y0, x0, y1), _covered(x1, y0, x1 + pad, y1),
                         _covered(x0, y0 - pad, x1, y0), _covered(x0, y1, x1, y1 + pad)]
                sides = [c for c in sides if c is not None]
                if sides and sum(1 for c in sides if c > GRAY_FIELD_COVER) >= max(1, len(sides) - 1):
                    continue
                lum = _mean_lum(lum_a, m, off, 60.0)
                st, kind, drawn = draw_component(area, m, PenColor.BLACK, ppg, box, min_len_g, tone=True,
                                                 offset=off, grid=(grid_w, gh), lum=lum, ridge=ridge, gray=True)
                if kind == "line":
                    out.extend(st)
                    hatch_mask.paste(0, (off[0], off[1]), drawn)
                    line_mask.paste(drawn, (off[0], off[1]), drawn)
                    kinds["gray_line"] += 1
                else:
                    # thin gray that is NOT a line is anti-aliasing or faint detail: drop it.
                    # Shading it turned a skull's sutures into hatch specks (264 -> 506
                    # strokes). Only thick gray is shading.
                    cw_, ch_ = m.size
                    _, perim_ = _outline(m, cw_, ch_, min_len_g)
                    est_g = 2.0 * area / perim_ if perim_ else 99.0
                    if est_g * ppg <= 1.6 * GRAY_LINE_MAX_PAGE and est_g <= _gu(GRAY_DROP_G):
                        hatch_mask.paste(0, (off[0], off[1]), m)
                        kinds["gray_dropped"] = kinds.get("gray_dropped", 0) + 1
        p["components"]["INK"] = kinds
        # the gray halo hugging a DRAWN LINE is anti-aliasing, not shading. Strip it from the hatch
        # mask around lines only -- doing this globally erased most of a photograph's
        # mid-tones, because there every mid-tone sits next to something dark.
        halo = _dilate(line_mask, _ker())
        fringe_cut = int(round(FRINGE_L * 2.55))
        hatch_mask = N.bool_img((N.view(hatch_mask) != 0) & ~((N.view(halo) != 0) & (lum_a < fringe_cut)))
        # CEL-SHADE what is left: posterise into bands, keep only deliberate regions,
        # hatch each region uniformly. Hatching never carries the drawing's body.
        p["tone_lines"] = 0
        if tone and hatch_mask.getbbox() is not None:
            min_area_px = int(CEL_MIN_AREA * grid_w * gh / detail)
            pitch_g = max(1.2, TONE_PITCH_PAGE / ppg)
            tf = _field(TONE_WIDTH_PAGE)
            bands = {}
            # the budget: if more of the box would shade than `shade` allows, raise the darkness
            # floor until only the darkest budget's worth remains. Uniform density per band is kept.
            d_min = CEL_BANDS[0][0]
            budget = shade * grid_w * gh
            gb = np.asarray(lumimg.filter(ImageFilter.GaussianBlur(CEL_BLUR)), np.float64)
            d_ = 1.0 - gb / 255.0
            # the budget is ACCOUNTED over the hatch range only, darkness < 0.88. Darker
            # pixels are black fills and hatch nothing; a dark COLOR there is a wash
            # that the dense band must shade -- and a ground covering most of the picture must not
            # spend the whole budget and leave every face and fold lighter than it as paper. So
            # the darkest range is always shaded and never counted; the budget still turns a
            # photograph's light mid-tones into paper.
            HI_V67 = 0.88
            in_band = (N.view(hatch_mask) != 0) & (d_ >= CEL_BANDS[0][0]) & (d_ < HI_V67)
            hist = np.bincount((d_[in_band] * 100).astype(np.int64), minlength=101).tolist()
            shaded = sum(hist)
            p["shade_cover"] = round(shaded / float(grid_w * gh), 3)
            if shaded > budget:
                acc = 0
                for i in range(100, -1, -1):
                    acc += hist[i]
                    if acc > budget:
                        d_min = max(d_min, (i + 1) / 100.0)
                        break
                # THE DARKEST TONE ALWAYS SHADES. A dark ground covering most of the picture
                # sits in one darkness bin; raising the floor past it to meet the budget dropped
                # every hatch line and left the ground as a flat wash. The budget exists to turn
                # photographs' light mid-tones into paper (more negative space), never
                # to un-shade the darkest thing on the page.
                top = max((i for i in range(101) if hist[i]), default=None)
                if top is not None:
                    d_min = min(d_min, top / 100.0)
            p["shade_floor"] = round(d_min, 2)
            # a hard floor alone would leave a picture two-tone -- one cross-hatch and paper;
            # the dark band runs on to CEL_BANDS[-1][1] so everything darker than 0.88 cross-hatches
            # TWO DENSITIES, AND ONLY TWO: single and double hatching.
            # Three bands at three pitches was a GRADIENT, and the gradient is how
            # hatch used to manufacture tone. The pitch is identical in both bands here; the
            # only difference is whether the shade is crossed. Shade, and deep shade.
            hi_ = CEL_BANDS[-1][1]
            # the split is a QUANTILE of what is actually being shaded, not a fraction of a range.
            # A fixed fraction put every shaded pixel in the deep band on a test painting, so only the
            # crossed density ever appeared; the quantile guarantees both show up, in proportion.
            shade_d = d_[(N.view(hatch_mask) != 0) & (d_ >= d_min) & (d_ < hi_)]
            mid_ = float(np.quantile(shade_d, K.HATCH_CROSS_AT)) if shade_d.size else (d_min + hi_) / 2.0
            bands_lohi = [(d_min, mid_), (mid_, hi_)]
            rgb_small = np.asarray(small.convert("RGB"), np.uint8)
            # everything a COLOR class painted. What the hatch covers outside this has no body
            # behind it, and black hatch on bare paper is a defect.
            painted = Image.new("L", (grid_w, gh))
            for k_ in masks:
                if k_ not in ("black", "tone", "_ink"):
                    painted = ImageChops.lighter(painted, masks[k_])
            if "black" in masks:
                painted = ImageChops.lighter(painted, masks["black"])   # already solid ink
            for bi, region in cel_regions(lumimg, hatch_mask, min_area_px, bands=bands_lohi):
                if K.HATCH_UNDER_WASH:
                    need = ImageChops.subtract(region, painted)
                    if need.getbbox() is not None:
                        for a_, nm_, noff in components(need, max(2, int(round(_gu(K.HATCH_UNDER_MIN_G))))):
                            sel_ = N.view(nm_) != 0
                            y0, x0 = max(0, noff[1]), max(0, noff[0])
                            y1, x1 = min(gh, noff[1] + nm_.height), min(grid_w, noff[0] + nm_.width)
                            sub = rgb_small[y0:y1, x0:x1]
                            ss_ = sel_[y0 - noff[1]:y1 - noff[1], x0 - noff[0]:x1 - noff[0]]
                            if not ss_.any():
                                continue
                            mrgb = tuple(int(v) for v in sub[ss_].mean(axis=0))
                            out.extend(_fill_region_hl(nm_, mrgb, ppg, box, offset=noff, grid=(grid_w, gh)))
                            p["hatch_wash"] = p.get("hatch_wash", 0) + 1
                # THE HATCH IS TEXTURE, NOT DARKNESS. With a wash under it the hatch no longer has
                # to manufacture tone, and the settings that did are what killed the fill: the dense
                # band crosses two families at a pitch of ~5 grid px with lines ~1.5 wide, which is
                # over half the area black -- a dot screen, not shading, and it kills what should be
                # behind it. One direction, and the
                # pitch opened up, so the fill shows between the strokes.
                # ONE HATCH, everywhere it is used. Three bands at three pitches IS a density
                # gradient, and the gradient was how hatch used to carry tone. The wash carries
                # tone now, so a hatch mark means one thing -- this part is in shade -- and it
                # looks the same wherever it means it.
                # band 0 is shade: one direction. band 1 is deep shade: the same lines, crossed.
                angles = (K.HATCH_ANGLE,) if bi == 0 else (K.HATCH_ANGLE, K.HATCH_ANGLE_2)
                pmul = K.TC_HATCH_PITCH_MUL        # the SAME pitch in both: only the crossing differs
                if flow is not None:
                    from paperdaemon.pipeline.decompose.reference import rm_flow as FL
                    polys = FL.hatch(region, flow, angles, pitch_g * pmul, min_len_g)
                else:
                    polys = uniform_hatch(region, angles, pitch_g * pmul, min_len_g)
                hcol = _hatch_pen(rgb_small, region) if K.HATCH_IN_COLOR else PenColor.BLACK
                for pts in place(polys, (grid_w, gh), box):
                    out.append((pts, [tf] * len(pts), TONE_PEN, hcol, None))
                bands[bi] = len(polys)
                p["tone_lines"] += len(polys)
            p["cel_bands"] = bands

    # ---------------------------------------------------------------- the backstop
    # NOTHING NON-PAPER REACHES THE PAGE UNPAINTED, and this is the line that makes that true
    # rather than hoped for. Every pass above covers what it believes it covers; the belief has
    # been wrong at more than one stage (rows that stepped at an edge, rings that
    # assumed their own width, size floors that silently discarded a tenth of a picture). So the
    # strokes are rasterized back onto the grid with the device's own ribbon, compared against
    # everything the classifier called non-paper, and whatever is left is painted in its own
    # color. If this ever paints a lot, something upstream is broken -- p["backstop"] says how
    # much, and it should be a fraction of a percent.
    if K.FILL_BACKSTOP:
        scale = min((box[2] - box[0]) / grid_w, (box[3] - box[1]) / gh)
        ox = box[0] + ((box[2] - box[0]) - grid_w * scale) / 2.0
        oy = box[1] + ((box[3] - box[1]) - gh * scale) / 2.0
        chains = []
        for pts_, widths_, tool_, _col, _rgba in out:
            # the NARROWEST point, not the first: an ink line tapers, and crediting it with its
            # fat end along its whole length hides the gap beside its thin end
            wpage = float(min(widths_)) * (HL_SCALE if tool_ == Pen.HIGHLIGHTER_2 else _W)
            chains.append(([((x - ox) / scale, (y - oy) / scale) for x, y in pts_], wpage / scale))
        got = _ribbon_raster((grid_w, gh), chains, extra=K.COVER_GRACE)
        want = np.zeros((gh, grid_w), bool)
        for k_ in masks:
            if k_ != "_ink":
                want |= N.view(masks[k_]) != 0
        miss = want & ~got
        p["backstop"] = round(float(miss.mean()), 4)
        if miss.any():
            rgb_g = np.asarray(small.convert("RGB"), np.uint8)
            n_fix = 0
            for _a, mm, moff in components(N.bool_img(miss), 1, 0):
                y0, x0 = max(0, moff[1]), max(0, moff[0])
                y1, x1 = min(gh, moff[1] + mm.height), min(grid_w, moff[0] + mm.width)
                sel_ = (N.view(mm) != 0)[y0 - moff[1]:y1 - moff[1], x0 - moff[0]:x1 - moff[0]]
                if not sel_.any():
                    continue
                mrgb = tuple(int(v) for v in rgb_g[y0:y1, x0:x1][sel_].mean(axis=0))
                out.extend(_fill_region_hl(mm, mrgb, ppg, box, offset=moff, grid=(grid_w, gh)))
                n_fix += 1
            p["backstop_patches"] = n_fix

    # CONTOUR PASS. A photograph has no line anywhere in it, so the painter fills regions and the result
    # reads as blobs -- photoreal human faces have no line art, so they often come out as blobs.
    # The XDoG ridge is already computed here for centerlines; whatever is left of it once
    # everything already inked is removed IS the form's contour, and nobody is drawing it.
    p["outline_lines"] = 0
    p["soft_px"] = 0
    if OUTLINE:
        # SUBTRACT WHAT WAS DRAWN, NOT WHAT WAS CLASSIFIED. Until now this removed the whole `_ink`
        # and `black` masks -- every pixel dark enough to be CALLED ink, whether a stroke was put
        # there or not. On a portrait that is the eyes, the nostrils and the lips: classified dark,
        # handed to the hatcher because the component is too small to draw as a line, and then
        # fenced off from the one pass that WOULD have drawn them. Measured on the front portrait:
        # 1589 ridge pixels in, 405 left: eyes were only hatch shaded and the nose was missing outright.
        inked = Image.new("L", (grid_w, gh))
        for m_ in (locals().get("line_mask"), locals().get("fill_mask"), locals().get("col_line_mask")):
            if m_ is not None:
                inked = ImageChops.lighter(inked, m_)
        clear = max(1, int(round(_gu(OUTLINE_CLEAR_G))))
        # the shared ridge is thresholded for INK. A nose bridge and a collarbone are soft edges and never
        # reach it, so the contour pass takes its own, more generous slice of the SAME response.
        cr = LA.thin(LA.mask(resp, rsize, OUTLINE_XDOG)) if OUTLINE_XDOG != XDOG_INK else ridge
        cr = cr != 0
        if OUTLINE_SOFT:
            soft = _soft_edges(small, masks, grid_w, gh, ridge=cr, clear=clear)
            p["soft_px"] = int(np.count_nonzero(soft))
            cr = cr | soft
        keep = cr & ~(N.view(_dilate(inked, 2 * clear + 1)) != 0)
        if keep.any():
            min_len_out = max(min_len_g, OUTLINE_MIN_LEN_PAGE / ppg)
            sk, _tot, _n = _skeleton(N.bool_img(keep), ppg, min_len_out, method="thin")
            wf = _field(OUTLINE_WIDTH_PAGE)
            for _L, pts_g in sk:
                (pts,) = place([[(x, y) for x, y in pts_g]], (grid_w, gh), box)
                if len(pts) >= 2:
                    out.append((pts, [wf] * len(pts), Pen.FINELINER_2, PenColor.BLACK, None))
                    p["outline_lines"] += 1

    # the highlighter goes down before any pen: drawn later it would tint the pens (device model)
    if K.SUBCELL_GEOMETRY:
        # Minimum blending commutes among washes. Stable color grouping
        # avoids repeated full-canvas flushes without changing any footprint
        # or moving a wash past opaque ink.
        washes = {}
        pens = []
        for s_ in out:
            if s_[2] == Pen.HIGHLIGHTER_2:
                washes.setdefault(tuple(s_[4]), []).append(s_)
            else:
                pens.append(s_)
        out = [s_ for group in washes.values() for s_ in group] + pens
    else:
        out = [s_ for s_ in out if s_[2] == Pen.HIGHLIGHTER_2] + [s_ for s_ in out if s_[2] != Pen.HIGHLIGHTER_2]
    if out:
        # extent of the ink including half the pen width, in page px, for the caller's layout
        # Highlighter width fields use .25 px, not the opaque pens' .144.
        xs = [x + sign * wd * (HL_SCALE if tool == Pen.HIGHLIGHTER_2 else _W) / 2
              for pts, ws, tool, *_ in out for (x, _y), wd in zip(pts, ws) for sign in (-1, 1)]
        ys = [y + sign * wd * (HL_SCALE if tool == Pen.HIGHLIGHTER_2 else _W) / 2
              for pts, ws, tool, *_ in out for (_x, y), wd in zip(pts, ws) for sign in (-1, 1)]
        p["extent"] = [round(min(xs), 1), round(min(ys), 1), round(max(xs), 1), round(max(ys), 1)]
    _SKIN_HUE_OFFSET, _DARK_FIELD, _FLOW, _WHITE_FLOOR, _UP = 0.0, False, None, None, 1.0   # per picture
    return out, p, round(time.perf_counter() - t0, 3)


# ---------------------------------------------------------------- preview
def fit_box(src_size, w, h):
    """Where decompose() puts a source of `src_size` inside a w x h box: (x, y, drawn_w, drawn_h)
    in page px -- the same grid, margin and centering decompose uses."""
    sw, sh = src_size
    grid_w, gh = int(sw), int(sh)                     # the grid is the source
    if K.UPSCALE_TO_PAGE:                             # ...resampled up to the page (see decompose)
        f = min(float(w) / grid_w, float(h) / gh)
        f = min(f, K.UPSCALE_MAX, math.sqrt(K.UPSCALE_MAX_PX / float(grid_w * gh)))
        if f >= K.UPSCALE_MIN:
            grid_w, gh = int(round(grid_w * f)), int(round(gh * f))
    ppg0 = min(float(w) / grid_w, float(h) / gh)
    margin = max(EDGE_MARGIN_PAGE, 2.5 * ppg0)
    ppg = min((w - 2 * margin) / grid_w, (h - 2 * margin) / gh)
    dw, dh = grid_w * ppg, gh * ppg
    return (w - dw) / 2.0, (h - dh) / 2.0, dw, dh


def fidelity(src, strokes, w, h, n=64):
    """color: coarse per-channel similarity. structure: edge-map correlation. The source is
    letterboxed exactly as decompose() places the drawing, so the two line up."""
    tmp = "_fid_%d.png" % os.getpid()
    render(strokes, w, h, tmp, pad=0, ss=2)
    S_ = Image.open(src).convert("RGB")
    x, y, dw, dh = fit_box(S_.size, w, h)
    A_ = Image.new("RGB", (w, h), (255, 255, 255))
    A_.paste(S_.resize((max(1, int(round(dw))), max(1, int(round(dh)))), Image.LANCZOS), (int(round(x)), int(round(y))))
    B_ = Image.open(tmp).convert("RGB")
    os.remove(tmp)
    a = A_.resize((n, n), Image.LANCZOS).getdata()
    b = B_.resize((n, n), Image.LANCZOS).getdata()
    diff = sum(abs(x[0] - y[0]) + abs(x[1] - y[1]) + abs(x[2] - y[2]) for x, y in zip(a, b)) / (3.0 * n * n)
    m = 96
    ea = A_.convert("L").resize((m, m), Image.LANCZOS).filter(ImageFilter.GaussianBlur(0.8)).filter(ImageFilter.FIND_EDGES).getdata()
    eb = B_.convert("L").resize((m, m), Image.LANCZOS).filter(ImageFilter.GaussianBlur(0.8)).filter(ImageFilter.FIND_EDGES).getdata()
    ma, mb = sum(ea) / float(m * m), sum(eb) / float(m * m)
    num = sum((x - ma) * (y - mb) for x, y in zip(ea, eb))
    den = math.sqrt(sum((x - ma) ** 2 for x in ea) * sum((y - mb) ** 2 for y in eb)) or 1.0
    return dict(color=round(100.0 - diff / 2.55, 1), structure=round(50.0 + 50.0 * num / den, 1))


def stats(strokes):
    n = len(strokes)
    pts = sum(len(s[0]) for s in strokes)
    lens = [sum(math.hypot(P[i+1][0]-P[i][0], P[i+1][1]-P[i][1]) for i in range(len(P) - 1))
            for P in (s[0] for s in strokes)]
    pens = {}
    for s in strokes:
        pens[s[2].name] = pens.get(s[2].name, 0) + 1
    return dict(strokes=n, points=pts, pts_per_stroke=round(pts / n, 1) if n else 0.0,
                mean_len=round(sum(lens) / n, 1) if n else 0.0, pens=pens)


if __name__ == "__main__":
    src = sys.argv[1]
    h = int(sys.argv[2]) if len(sys.argv) > 2 else 800
    out = sys.argv[3] if len(sys.argv) > 3 else "rm-paint.png"
    strokes, p, dt = decompose(src, h, h)
    render(strokes, h, h, out)
    print("%s  %s  %s  %.2fs\n%s" % (out, stats(strokes), fidelity(src, strokes, h, h), dt, p))
