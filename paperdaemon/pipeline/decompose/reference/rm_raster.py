r"""The device's rasterizer for highlighter strokes, as measured -- not as assumed.

MEASURED against the desktop app's own render of a calibration page (lines
of known width and controlled overlaps, read through registration marks): a pixel is painted when and only when its
CENTER lies inside the stroke's footprint. No anti-aliasing, no minimum width. A 0.75 px wash that misses every pixel
center draws nothing; a 1.5 px wash that catches two centers draws two pixels; sixteen 0.25 px washes with 0.25 px
gaps draw nothing at all. All 24 wash lines of the calibration page match this rule exactly. A center exactly on
the footprint's edge is painted on one side only: the TOP-LEFT rule, confirmed by a pinhole test (a center
on a stroke's top edge is painted, on its bottom edge not). A stroke whose width changes between two points is drawn
at the MEAN of the two widths along that segment (1 -> 4 px drew at 2.5), which is what geometry() computes.
(The pen behaved differently -- 0.58 px drew at about half darkness -- and has no model here yet.)

What this replaces: PIL's polygon fill with every width floored to one pixel (rm_render._draw / px_width). On thin
rectangles PIL agreed with center sampling in 1 of 400 cases and overpainted by 11 px a rectangle; the floor painted
every sub-pixel wash as a full pixel. Stroke removal built on that saw cover where the device leaves paper, which
shows up as pinholes on the page.

The footprint geometry is the one already calibrated (rm_render._draw): one rectangle per segment, flat ends,
and a bevel triangle on the outer side of each interior corner, half-width = the mean of the two end widths / 2.

    wash_pixels(pts, widths, ox, oy, W, H, eps)   -> flat indices of the painted pixels in a W x H grid at (ox, oy)
    paint_wash(img, ox, oy, pts, widths, eps)     -> paints 1s into a 2D uint8 array
`eps` (page px): 0 is the device's rule; +EPS paints every pixel the device MIGHT paint (edges included either way),
-EPS only those it SURELY paints (edges excluded). Decisions that must hold under either edge convention use both.
"""
import math

import numpy as np

HL_SCALE = 0.25          # highlighter width field -> page px (calibrated and confirmed against the device)
EPS = 1e-3               # page px: more than float32 rounding at page coordinates (~6e-5), far less than a pixel
TOP_LEFT = True          # a center exactly on an edge counts when the edge faces up (or left): the usual fill rule
_PAINT = None


def _kernel():
    """The compiled painter, built once."""
    global _PAINT
    if _PAINT is not None:
        return _PAINT
    import numba as nb
    top_left = TOP_LEFT

    @nb.njit(cache=True, inline="always")
    def inside(d, nx, ny, eps):
        """d: the point's distance outside one edge (negative inside); (nx, ny): the edge's outward normal."""
        if eps > 0.0:
            return d <= eps
        if eps < 0.0:
            return d < eps
        if d < -1e-9:
            return True
        if d > 1e-9:
            return False
        if top_left:
            return ny < -1e-12 or (abs(ny) <= 1e-12 and nx < 0.0)
        return ny > 1e-12 or (abs(ny) <= 1e-12 and nx > 0.0)

    @nb.njit(cache=True, nogil=True)
    def paint(img, ox, oy, xs, ys, hw, eps):
        H, W = img.shape
        n = xs.shape[0]
        for i in range(n - 1):
            x0 = xs[i]; y0 = ys[i]; x1 = xs[i + 1]; y1 = ys[i + 1]
            dx = x1 - x0; dy = y1 - y0
            L = math.sqrt(dx * dx + dy * dy)             # sqrt, not ** 0.5: correctly rounded on every platform, so the
            if L < 1e-9:                                 # C port (fastdecomp) paints the same pixels bit for bit
                continue
            ux = dx / L; uy = dy / L                      # along; the left-hand perpendicular is (-uy, ux)
            h = hw[i]
            c0 = int(np.floor(min(x0, x1) - h - ox - 1.0)); c1 = int(np.ceil(max(x0, x1) + h - ox + 1.0))
            r0 = int(np.floor(min(y0, y1) - h - oy - 1.0)); r1 = int(np.ceil(max(y0, y1) + h - oy + 1.0))
            if c0 < 0: c0 = 0
            if r0 < 0: r0 = 0
            if c1 > W - 1: c1 = W - 1
            if r1 > H - 1: r1 = H - 1
            for r in range(r0, r1 + 1):
                ry = oy + r + 0.5 - y0
                for c in range(c0, c1 + 1):
                    rx = ox + c + 0.5 - x0
                    t = rx * ux + ry * uy
                    s = -rx * uy + ry * ux
                    if (inside(-t, -ux, -uy, eps) and inside(t - L, ux, uy, eps)
                            and inside(-s - h, uy, -ux, eps) and inside(s - h, -uy, ux, eps)):
                        img[r, c] = 1
        for i in range(1, n - 1):
            ax = xs[i] - xs[i - 1]; ay = ys[i] - ys[i - 1]
            bx = xs[i + 1] - xs[i]; by = ys[i + 1] - ys[i]
            la = math.sqrt(ax * ax + ay * ay); lb = math.sqrt(bx * bx + by * by)
            if la < 1e-9 or lb < 1e-9:
                continue
            d1x = ax / la; d1y = ay / la; d2x = bx / lb; d2y = by / lb
            cross = d1x * d2y - d1y * d2x
            if abs(cross) < 1e-6:
                continue
            sgn = -1.0 if cross > 0 else 1.0
            vx = xs[i]; vy = ys[i]
            p1x = vx + sgn * (-d1y) * hw[i - 1]; p1y = vy + sgn * d1x * hw[i - 1]
            p2x = vx + sgn * (-d2y) * hw[i]; p2y = vy + sgn * d2x * hw[i]
            area = (p1x - vx) * (p2y - vy) - (p1y - vy) * (p2x - vx)
            if abs(area) < 1e-12:
                continue
            o = 1.0 if area > 0 else -1.0                 # +1: the corners run counterclockwise
            e1 = math.sqrt((p1x - vx) * (p1x - vx) + (p1y - vy) * (p1y - vy))
            e2 = math.sqrt((p2x - p1x) * (p2x - p1x) + (p2y - p1y) * (p2y - p1y))
            e3 = math.sqrt((vx - p2x) * (vx - p2x) + (vy - p2y) * (vy - p2y))
            if e1 < 1e-9 or e2 < 1e-9 or e3 < 1e-9:
                continue
            c0 = int(np.floor(min(vx, p1x, p2x) - ox - 1.0)); c1 = int(np.ceil(max(vx, p1x, p2x) - ox + 1.0))
            r0 = int(np.floor(min(vy, p1y, p2y) - oy - 1.0)); r1 = int(np.ceil(max(vy, p1y, p2y) - oy + 1.0))
            if c0 < 0: c0 = 0
            if r0 < 0: r0 = 0
            if c1 > W - 1: c1 = W - 1
            if r1 > H - 1: r1 = H - 1
            for r in range(r0, r1 + 1):
                py = oy + r + 0.5
                for c in range(c0, c1 + 1):
                    px = ox + c + 0.5
                    # distance outside each edge, and that edge's outward normal
                    d1 = -o * ((p1x - vx) * (py - vy) - (p1y - vy) * (px - vx)) / e1
                    d2 = -o * ((p2x - p1x) * (py - p1y) - (p2y - p1y) * (px - p1x)) / e2
                    d3 = -o * ((vx - p2x) * (py - p2y) - (vy - p2y) * (px - p2x)) / e3
                    if (inside(d1, o * (p1y - vy) / e1, -o * (p1x - vx) / e1, eps)
                            and inside(d2, o * (p2y - p1y) / e2, -o * (p2x - p1x) / e2, eps)
                            and inside(d3, o * (vy - p2y) / e3, -o * (vx - p2x) / e3, eps)):
                        img[r, c] = 1
    _PAINT = paint
    return _PAINT


_PENCIL = None
PEN_SCALE = 0.144        # pen/pencil width field -> page px (rm_render.WSCALE_DEFAULT)
PENCIL_SOFT = 1.4        # page px over which the pencil's edge goes from solid to nothing
PENCIL_RAGGED = 0.8      # how far the grain pushes the edge in and out, as a share of PENCIL_SOFT
PENCIL_CORE = 0.86       # the pencil's opacity at its core (device, 4.6x screen capture: core L 5-11 on any dark wash)
# Fitted to a zoomed capture's cross-profile (device darkness 212 -> 238 -> 212 over +/- 8 capture px at 3.59 per
# page px; grain std 9.9 L after the capture's 0.78 resampling). The first guess (1.0 / 0.5 / 0.92) gave a core 11 L
# too dark, an edge half a page px too tight and grain of 4.5; these values are the refit.


def _pencil_kernel():
    """The pencil, as a 4.6x screen capture showed it (a painting's page, 8,594 samples on 1,837 hatch
    strokes of width field 13 = 1.87 px): an OPAQUE BLACK band at its core whatever lies under it (core L 5.4 / 8.7 /
    11.2 over washes of L 15 / 48 / 80), a soft, grainy edge (at the nominal half-width the device is about half way
    between core and background), placed exactly where the file says. Not the light scatter rm_render._stipple draws.
    The kernel accumulates OPACITY (0..1) into a float32 canvas: a capsule per segment (so joins and ends are round),
    opacity falling linearly across PENCIL_SOFT around the half-width, the edge made ragged by a per-pixel hash grain,
    and overlapping strokes combining as 1 - (1 - a)(1 - b)."""
    global _PENCIL
    if _PENCIL is not None:
        return _PENCIL
    import numba as nb

    @nb.njit(cache=True, inline="always")
    def grain(r, c, seed):
        h = (c * 73856093) ^ (r * 19349663) ^ (seed * 83492791)
        h = (h ^ (h >> 13)) * 1274126177
        h = h ^ (h >> 16)
        return (h & 0xFFFFFF) / 16777215.0

    @nb.njit(cache=True, nogil=True)
    def pencil(alpha, ox, oy, xs, ys, hw, soft, ragged, core, seed):
        H, W = alpha.shape
        n = xs.shape[0]
        for i in range(n - 1):
            x0 = xs[i]; y0 = ys[i]; x1 = xs[i + 1]; y1 = ys[i + 1]
            dx = x1 - x0; dy = y1 - y0
            L2 = dx * dx + dy * dy
            h = hw[i]
            pad = h + soft + 1.0
            c0 = int(np.floor(min(x0, x1) - pad - ox)); c1 = int(np.ceil(max(x0, x1) + pad - ox))
            r0 = int(np.floor(min(y0, y1) - pad - oy)); r1 = int(np.ceil(max(y0, y1) + pad - oy))
            if c0 < 0: c0 = 0
            if r0 < 0: r0 = 0
            if c1 > W - 1: c1 = W - 1
            if r1 > H - 1: r1 = H - 1
            for r in range(r0, r1 + 1):
                py = oy + r + 0.5
                for c in range(c0, c1 + 1):
                    px = ox + c + 0.5
                    if L2 < 1e-12:
                        t = 0.0
                    else:
                        t = ((px - x0) * dx + (py - y0) * dy) / L2
                        if t < 0.0: t = 0.0
                        if t > 1.0: t = 1.0
                    ex = px - (x0 + t * dx); ey = py - (y0 + t * dy)
                    d = (ex * ex + ey * ey) ** 0.5
                    g = grain(r, c, seed)
                    a = (h + 0.5 * soft - d) / soft + ragged * (g - 0.5)
                    if a <= 0.0:
                        continue
                    if a > 1.0: a = 1.0
                    a = a * core * (0.8 + 0.2 * g)
                    alpha[r, c] = 1.0 - (1.0 - alpha[r, c]) * (1.0 - a)
    _PENCIL = pencil
    return _PENCIL


def paint_pencil(alpha, ox, oy, pts, widths, scale=1.0, seed=0):
    """Accumulate one pencil stroke's opacity into `alpha` (2D float32, pixel (r, c) centered at (ox + c + .5, oy + r + .5))."""
    xs, ys, ws = [], [], []
    for (x, y), w in zip(pts, widths):
        if xs and abs(x - xs[-1]) < 1e-6 and abs(y - ys[-1]) < 1e-6:
            continue
        xs.append(float(x) * scale); ys.append(float(y) * scale); ws.append(float(w) * PEN_SCALE * scale)
    if len(xs) < 2:
        if len(xs) == 1:
            xs.append(xs[0] + 1e-3); ys.append(ys[0]); ws.append(ws[0])
        else:
            return
    hw = np.asarray([(ws[i] + ws[i + 1]) / 4.0 for i in range(len(ws) - 1)])
    _pencil_kernel()(alpha, float(ox), float(oy), np.asarray(xs), np.asarray(ys), hw,
                     float(PENCIL_SOFT * scale), float(PENCIL_RAGGED), float(PENCIL_CORE), int(seed) & 0x7FFFFFFF)


def geometry(pts, widths, scale=1.0):
    """The stroke as the kernel takes it: consecutive duplicate points dropped (as rm_render._draw drops them),
    coordinates and half-widths per segment in page px at `scale`."""
    xs, ys, ws = [], [], []
    for (x, y), w in zip(pts, widths):
        if xs and abs(x - xs[-1]) < 1e-6 and abs(y - ys[-1]) < 1e-6:
            continue
        xs.append(float(x) * scale); ys.append(float(y) * scale); ws.append(float(w) * HL_SCALE * scale)
    if len(xs) < 2:
        return None
    hw = [(ws[i] + ws[i + 1]) / 4.0 for i in range(len(ws) - 1)]
    return np.asarray(xs), np.asarray(ys), np.asarray(hw)


def paint_wash(img, ox, oy, pts, widths, eps=0.0, scale=1.0):
    """Paint one highlighter stroke into `img` (2D uint8, pixel (r, c) centered at (ox + c + .5, oy + r + .5))."""
    g = geometry(pts, widths, scale)
    if g is None:
        return
    _kernel()(img, float(ox), float(oy), g[0], g[1], g[2], float(eps))


def wash_pixels(pts, widths, ox, oy, W, H, eps=0.0, scale=1.0):
    """Flat indices (row * W + col, int32) of the pixels one highlighter stroke paints in a W x H grid whose pixel
    (0, 0) is centered at (ox + .5, oy + .5)."""
    g = geometry(pts, widths, scale)
    if g is None:
        return np.empty(0, np.int32)
    xs, ys, hw = g
    pad = float(hw.max()) + 2.0
    c0, c1 = max(0, int(np.floor(xs.min() - pad - ox))), min(W, int(np.ceil(xs.max() + pad - ox)) + 1)
    r0, r1 = max(0, int(np.floor(ys.min() - pad - oy))), min(H, int(np.ceil(ys.max() + pad - oy)) + 1)
    if c1 <= c0 or r1 <= r0:
        return np.empty(0, np.int32)
    img = np.zeros((r1 - r0, c1 - c0), np.uint8)
    _kernel()(img, float(ox + c0), float(oy + r0), xs, ys, hw, float(eps))
    rr, cc = np.nonzero(img)
    return ((rr + r0) * W + (cc + c0)).astype(np.int32)
