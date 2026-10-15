r"""Flow-guided strokes: hatch that follows the picture's own direction.

Details like hair lose a great deal when strokes do not follow the lines on the page and only
try to match colors.

The hatch has always been straight parallel lines at two fixed angles (38 deg, crossed with -34 in
the darkest band). It carries darkness correctly and says nothing about form, so hair, fur, drapery
and grain all come out as the same mechanical weave. An illustrator does the opposite: the strokes
run ALONG the thing, and their spacing carries the tone.

This computes the picture's edge-tangent flow -- the direction structure runs in, everywhere --
and draws the hatch as streamlines of that field:

    flow = field(gray, sigma)             # once per picture
    polys = hatch(region_mask, flow, angles, pitch_g, min_len_g)

The field is the structure tensor of the blurred luminance, smoothed: J = G_sigma * (grad grad^T),
whose smaller eigenvector is the direction along which the image varies least -- the edge tangent.
Coherence, ((l1 - l2) / (l1 + l2))^2, says how strongly the picture is pointing anywhere: high in
hair and folds, near zero in flat paint. Where it is low the field is noise, so those pixels fall
back to the fixed angle and the result is the hatch we already have.

Spacing comes from an occupancy grid at the hatch pitch: a streamline stops when it enters a cell
another line already owns, so lines are evenly spaced without a distance transform.
"""
import math

import numpy as np
from PIL import Image, ImageFilter


def _blur(a, sigma):
    """Gaussian blur of a float array. PIL's filter refuses mode "F", and the structure tensor is
    float by construction, so this goes through scipy -- which is already a dependency (rmb_npops
    labels components with it)."""
    if sigma <= 0:
        return a
    from scipy.ndimage import gaussian_filter
    return gaussian_filter(np.ascontiguousarray(a, np.float64), sigma, mode="nearest")


def field(gray, sigma=4.0, pre=1.2, min_coherence=0.05, fallback_deg=38.0):
    """(tx, ty, coherence) for a PIL 'L' image. tx/ty is a unit tangent per pixel.

    `pre` blurs before differentiating (noise is not structure); `sigma` smooths the tensor, which
    is what makes neighboring pixels agree -- it is the knob for how long a stroke can run before
    the field turns. Pixels under `min_coherence` are given the fallback angle, so a flat wall
    hatches exactly as it does today.
    """
    a = _blur(np.asarray(gray, np.float64) / 255.0, pre)
    gx = np.zeros_like(a)
    gy = np.zeros_like(a)
    gx[:, 1:-1] = (a[:, 2:] - a[:, :-2]) * 0.5
    gy[1:-1, :] = (a[2:, :] - a[:-2, :]) * 0.5
    Jxx, Jxy, Jyy = _blur(gx * gx, sigma), _blur(gx * gy, sigma), _blur(gy * gy, sigma)
    d = np.sqrt(np.maximum((Jxx - Jyy) ** 2 + 4.0 * Jxy * Jxy, 0.0))
    tr = Jxx + Jyy
    l1, l2 = 0.5 * (tr + d), 0.5 * (tr - d)
    coh = np.where(tr > 1e-12, ((l1 - l2) / (tr + 1e-12)) ** 2, 0.0)
    theta = 0.5 * np.arctan2(2.0 * Jxy, Jxx - Jyy)        # dominant GRADIENT orientation
    tx, ty = -np.sin(theta), np.cos(theta)                # the tangent is perpendicular to it
    weak = coh < min_coherence
    if weak.any():
        fx, fy = math.cos(math.radians(fallback_deg)), math.sin(math.radians(fallback_deg))
        tx = np.where(weak, fx, tx)
        ty = np.where(weak, fy, ty)
    n = np.hypot(tx, ty)
    n[n == 0] = 1.0
    return tx / n, ty / n, coh


def shape_field(mask_a, smooth=2.0):
    """(tx, ty) running PARALLEL TO THE BOUNDARY of `mask_a`, everywhere inside it.

    The distance transform's gradient points straight in from the nearest edge; its perpendicular
    is therefore the direction the edge runs. Streamlines of it are the shape's own contours --
    concentric in a blob, along the length of a strand. This is what a flat region's "form" is,
    and it is what the fixed fallback angle was standing in for.

    The gradient is unstable on the medial axis (a ridge, where the nearest edge switches sides),
    so the distance field is blurred first; that rounds the ridge without moving the boundary.
    """
    from scipy.ndimage import distance_transform_edt
    d = distance_transform_edt(mask_a)
    d = _blur(d, smooth)
    gy, gx = np.gradient(d)
    tx, ty = -gy, gx                       # perpendicular to the gradient
    n = np.hypot(tx, ty)
    flat = n < 1e-6
    if flat.any():                         # the medial axis itself: borrow the neighborhood
        tx = np.where(flat, _blur(np.where(flat, 0.0, tx), 2.0), tx)
        ty = np.where(flat, _blur(np.where(flat, 0.0, ty), 2.0), ty)
        n = np.hypot(tx, ty)
    n[n < 1e-9] = 1.0
    return tx / n, ty / n


def _rotate(tx, ty, deg):
    if not deg:
        return tx, ty
    c, s = math.cos(math.radians(deg)), math.sin(math.radians(deg))
    return tx * c - ty * s, tx * s + ty * c


def streamlines(mask_a, tx, ty, pitch, min_len, max_len=None, step=1.0):
    """Evenly spaced streamlines of (tx, ty) inside `mask_a` (a boolean array).

    Traced both ways from each seed, at `step` px, stopping at the mask edge, at `max_len`, or when
    the line enters a pitch-sized cell another line already owns -- which is what keeps the spacing
    even without a distance transform.
    """
    h, w = mask_a.shape
    cell = max(1, int(round(pitch)))
    ch, cw = h // cell + 1, w // cell + 1
    occ = np.zeros((ch, cw), np.int32)
    out = []
    max_len = max_len or max(24.0, 12.0 * pitch)
    max_steps = int(max_len / step)
    sid = 0
    # SEED EVERY CELL THE MASK TOUCHES, at a pixel that is actually in the mask. Sampling one
    # corner per cell (mask_a[::cell, ::cell]) misses a band narrower than the cell almost
    # everywhere, so most of it was never seeded and never drawn, leaving gaps in the strokes.
    pad = np.zeros((ch * cell, cw * cell), bool)
    pad[:h, :w] = mask_a
    blocks = pad.reshape(ch, cell, cw, cell)
    ys, xs = np.nonzero(blocks.any(axis=(1, 3)))
    for cy, cx in zip(ys.tolist(), xs.tolist()):
        if occ[cy, cx]:
            continue
        sid += 1
        blk = blocks[cy, :, cx, :]
        k_ = int(np.argmax(blk.reshape(-1)))
        yi, xi = cy * cell + k_ // cell, cx * cell + k_ % cell
        y0, x0 = yi + 0.5, xi + 0.5
        if not (0 <= yi < h and 0 <= xi < w and mask_a[yi, xi]):
            continue
        pts = []
        for sign in (1.0, -1.0):
            x, y = x0, y0
            dx, dy = tx[yi, xi] * sign, ty[yi, xi] * sign
            run = []
            for _ in range(max_steps // 2):
                xi_, yi_ = int(round(x)), int(round(y))
                if not (0 <= xi_ < w and 0 <= yi_ < h) or not mask_a[yi_, xi_]:
                    break
                cyy, cxx = yi_ // cell, xi_ // cell
                owner = occ[cyy, cxx]
                if owner and owner != sid:
                    break
                occ[cyy, cxx] = sid
                run.append((x, y))
                nx, ny = tx[yi_, xi_], ty[yi_, xi_]
                if nx * dx + ny * dy < 0:                 # the tangent has no sign; keep going the same way
                    nx, ny = -nx, -ny
                dx, dy = nx, ny
                x, y = x + dx * step, y + dy * step
            if sign > 0:
                pts = run
            else:
                pts = list(reversed(run[1:])) + pts
        if len(pts) < 2:
            continue
        L = sum(math.hypot(pts[i + 1][0] - pts[i][0], pts[i + 1][1] - pts[i][1]) for i in range(len(pts) - 1))
        if L >= min_len:
            out.append(_thin(pts))
    return out


def _thin(pts, tol=0.35):
    """Drop points that sit on the line between their neighbors: a streamline of 1-px steps is
    mostly collinear, and the device stores every point."""
    if len(pts) < 3:
        return pts
    out = [pts[0]]
    for i in range(1, len(pts) - 1):
        ax, ay = out[-1]
        bx, by = pts[i]
        cx, cy = pts[i + 1]
        vx, vy = cx - ax, cy - ay
        n = math.hypot(vx, vy)
        if n < 1e-9:
            continue
        if abs((bx - ax) * vy - (by - ay) * vx) / n > tol:
            out.append(pts[i])
    out.append(pts[-1])
    return out


def hatch(mask, flow, angles, pitch_g, min_len_g):
    """The uniform_hatch contract, flow-guided: one streamline set per angle in `angles`, each
    rotated off the flow by that angle's offset from the first, so a band that cross-hatched still
    cross-hatches -- across the form instead of across the page."""
    a = np.asarray(mask, np.uint8) != 0 if not isinstance(mask, np.ndarray) else mask
    tx, ty, _coh = flow
    base = angles[0] if angles else 0.0
    out = []
    for ang in (angles or (0.0,)):
        rx, ry = _rotate(tx, ty, ang - base)
        out.extend(streamlines(a, rx, ry, pitch_g, min_len_g))
    return out
