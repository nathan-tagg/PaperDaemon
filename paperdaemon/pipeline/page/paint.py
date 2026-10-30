"""Strokes onto a picture, with PaperDaemon's one renderer (fastdecomp/render.c): the pages on the Tablet screen, the
page pictures cache, the Decompose preview, the host's drafts and what the model is shown of a page are all drawn
here, the way the tablet draws them (a pixel is inked when its center is inside the stroke's exact shape).

A stroke is (points, widths, kind, rgba[, densities]): points (x, y) in the picture's pixels, widths in pixels (one per
point), kind "pen", "highlighter" or "shader", its color (the shader's alpha in the fourth place), and for a pen a
density per point (0..1, the share of its pixels inked: the grain; 1 or left out is solid). `ss` > 1 draws at ss times
the size and averages down, for a screen; 1 is the tablet's own pixels.

HOW EACH PEN ANSWERS PRESSURE AND SPEED (`response`), measured on the pen-test pages (2026-10-19: strokes at known
pressures, speeds and directions, the tablet's screen captured beside them). The direction field changes nothing the
tablet draws, for any pen. Widths are the stored width at the scale render.py gives it (the fineliner's, measured
before), times WIDER for the pens the tablet draws wider than that.
  pencil, mechanical pencil  grain at every pressure: the inked share climbs from a few percent to about 0.8 (pencil)
                             and 0.5 (mechanical) at full pressure
  paintbrush                 nothing below pressure 40; full width by 64, sparse there, near solid from 96; drawn
                             fast (speed 200 and up) it narrows to 0.7 and is a third inked
  ballpoint                  narrower and a little broken when light (two thirds of its width at 16), full from 64
  marker                     a little broken when drawn very fast
  the rest                   solid
These were set on the pen pages and checked on pages not used to set them (the color pages and the user's own strokes).
"""
import ctypes

import numpy as np

KINDS = {"pen": 0, "highlighter": 1, "shader": 2}


def _lib():
    """The C library (the decomposer's, which holds the renderer too), loaded whatever the decomposer is set to use."""
    import os
    import sys
    here = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "decompose", "fastdecomp")
    if here not in sys.path:
        sys.path.insert(0, here)
    import rmfast
    return rmfast.lib()


class Flat:
    """A page's strokes in the form both renderers draw from: every point of every stroke in one run, in file order.
    xy (N, 2) and w (N,) float64, in the target's pixels; dens (N,) float64, each point's density (1 solid); counts (S,)
    each stroke's points; kinds (S,) int32 (KINDS); rgba (S, 4) uint8."""
    __slots__ = ("xy", "w", "dens", "counts", "kinds", "rgba")

    def __init__(self, xy, w, dens, counts, kinds, rgba):
        self.xy, self.w, self.dens, self.counts, self.kinds, self.rgba = xy, w, dens, counts, kinds, rgba


def flat_of(strokes):
    """paint()'s strokes (points, widths, kind, color[, densities]) -> their Flat; None when none has a point."""
    strokes = [s for s in strokes if len(s[0])]       # points and widths: lists or numpy arrays
    if not strokes:
        return None
    counts = np.array([len(s[0]) for s in strokes], np.int32)
    xy = np.ascontiguousarray(np.concatenate([np.asarray(s[0], np.float64).reshape(-1, 2) for s in strokes]))
    w = np.ascontiguousarray(np.concatenate([np.broadcast_to(np.asarray(s[1], np.float64), (len(s[0]),)) for s in strokes]))
    d = np.ascontiguousarray(np.concatenate([np.broadcast_to(np.asarray(s[4] if len(s) > 4 and s[4] is not None else 1.0,
                                                                        np.float64), (len(s[0]),)) for s in strokes]))
    kinds = np.array([KINDS[s[2]] for s in strokes], np.int32)
    rgba = np.array([(list(s[3]) + [255])[:4] for s in strokes], np.uint8).reshape(-1, 4)
    return Flat(xy, w, d, counts, kinds, rgba)


def paint(img, strokes, ss=1):
    """Draw `strokes` over `img` (a PIL RGB image), in their order -> the same image, drawn on."""
    return paint_flat(img, flat_of(strokes), ss)


def paint_flat(img, flat, ss=1):
    """Draw a Flat over `img` (a PIL RGB image) -> the same image, drawn on: ON THE GRAPHICS CARD (gpu.py: the page
    editor's own shaders, by the same rules), or by render.c when the card cannot be used."""
    if flat is None or not len(flat.counts):
        return img
    from paperdaemon.pipeline.page import gpu
    out = gpu.paint(np.ascontiguousarray(np.asarray(img.convert("RGB"), np.uint8)), flat, ss)
    if out is not None:
        from PIL import Image
        img.paste(Image.fromarray(out, "RGB"))
        return img
    return _cpu(img, flat, ss)


def paint_cpu(img, strokes, ss=1):
    """paint() by render.c, on the processor: the fallback, and what the card's pictures are measured against."""
    flat = flat_of(strokes)
    return img if flat is None else _cpu(img, flat, ss)


def _cpu(img, flat, ss=1):
    xy, w, d = np.ascontiguousarray(flat.xy), np.ascontiguousarray(flat.w), np.ascontiguousarray(flat.dens)
    counts, kinds = np.ascontiguousarray(flat.counts, np.int32), np.ascontiguousarray(flat.kinds, np.int32)
    rgba = np.ascontiguousarray(flat.rgba, np.uint8).reshape(-1)
    px = np.ascontiguousarray(np.asarray(img.convert("RGB"), np.uint8))
    H, W = px.shape[:2]
    P = lambda a, t: a.ctypes.data_as(ctypes.POINTER(t))
    r = _lib().rf_render_grain(P(px, ctypes.c_uint8), W, H, int(ss), P(xy, ctypes.c_double), P(w, ctypes.c_double),
                               P(d, ctypes.c_double), P(counts, ctypes.c_int32), P(kinds, ctypes.c_int32),
                               P(rgba, ctypes.c_uint8), len(counts), None)
    if r != 0:
        raise MemoryError("the renderer ran out of memory")
    from PIL import Image
    out = Image.fromarray(px, "RGB")
    img.paste(out)
    return img


# the inked share at pressures 0, 16, 32, 64, 96, 128, 160, 208 and 255 (measured; see the module's note)
_AT = [0, 16, 32, 64, 96, 128, 160, 208, 255]
# the pencils' set on the calibration notebook through the tablet's screen share (patches at pressure 40, 128,
# 255 at three thicknesses, and single lines), with the paper's grain (shaders.js fsSeg)
GRAIN = {"PENCIL": [0.025, 0.034, 0.037, 0.125, 0.27, 0.478, 0.663, 0.866, 1.0],
         "MECHANICAL": [0.023, 0.034, 0.034, 0.161, 0.31, 0.469, 0.639, 0.869, 1.0],
         "PAINTBRUSH": [0, 0, 0, 0.12, 0.73, 0.87, 0.87, 0.87, 0.87],
         "BALLPOINT": [0.8, 0.83, 0.87, 1, 1, 1, 1, 1, 1]}


def drawn(widths, k):
    """The widths drawn: the stored widths (in pixels) times response()'s factor, never under a pixel unless the factor
    says the pen leaves nothing (the light paintbrush)."""
    w = np.asarray(widths, np.float64) * k
    return np.where(np.asarray(k) > 0, np.maximum(1.0, w), 0.0)


# how much wider than render.py's scale (field / 4) the tablet draws a pen: measured on the calibration
# notebook's widths page through the tablet's screen share (the pencils' with their grain counted out); the shader's is
# its wash, kept as it was
WIDER = {"PENCIL": 0.76, "MECHANICAL": 0.78, "PAINTBRUSH": 0.86, "CALIGRAPHY": 1.0, "MARKER": 0.8, "SHADER": 0.94}
_SPEED_AT = [0, 50, 200, 800]


def response(fam, pressure, speed=None):
    """How a pen draws at its pressures (0..255) and speeds (the speed field; None: slow) -> (width factor, density)
    arrays: the stored width at render.py's scale times the factor is the width drawn (see drawn()), the density the
    share of its pixels inked. `fam` is the pen's name before its first "_" ("PENCIL", "PAINTBRUSH", ...)."""
    p = np.clip(np.asarray(pressure, np.float64), 0, 255)
    sp = np.zeros_like(p) if speed is None else np.asarray(speed, np.float64) + np.zeros_like(p)
    k, d = np.full_like(p, WIDER.get(fam, 1.0)), np.ones_like(p)
    if fam in GRAIN:
        d = np.interp(p, _AT, GRAIN[fam])
    if fam == "PAINTBRUSH":
        k = k * np.clip((p - 40) / 24, 0, 1) * np.interp(sp, _SPEED_AT, [1, 1, 0.7, 0.7])
        d = d * np.interp(sp, _SPEED_AT, [1, 0.95, 0.37, 0.32])
    elif fam == "BALLPOINT":
        k = k * (0.55 + 0.45 * np.clip(p / 64, 0, 1))
    elif fam == "MARKER":
        d = np.interp(sp, _SPEED_AT, [1, 1, 0.97, 0.86])
    return k, d
