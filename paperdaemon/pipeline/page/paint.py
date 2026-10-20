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


def paint(img, strokes, ss=1):
    """Draw `strokes` over `img` (a PIL RGB image), in their order -> the same image, drawn on."""
    strokes = [s for s in strokes if len(s[0])]       # points and widths: lists or numpy arrays
    if not strokes:
        return img
    counts = np.array([len(s[0]) for s in strokes], np.int32)
    xy = np.ascontiguousarray(np.concatenate([np.asarray(s[0], np.float64).reshape(-1, 2) for s in strokes]))
    w = np.ascontiguousarray(np.concatenate([np.broadcast_to(np.asarray(s[1], np.float64), (len(s[0]),)) for s in strokes]))
    d = np.ascontiguousarray(np.concatenate([np.broadcast_to(np.asarray(s[4] if len(s) > 4 and s[4] is not None else 1.0,
                                                                        np.float64), (len(s[0]),)) for s in strokes]))
    kinds = np.array([KINDS[s[2]] for s in strokes], np.int32)
    rgba = np.array([(list(s[3]) + [255])[:4] for s in strokes], np.uint8).reshape(-1)
    px = np.ascontiguousarray(np.asarray(img.convert("RGB"), np.uint8))
    H, W = px.shape[:2]
    P = lambda a, t: a.ctypes.data_as(ctypes.POINTER(t))
    r = _lib().rf_render_grain(P(px, ctypes.c_uint8), W, H, int(ss), P(xy, ctypes.c_double), P(w, ctypes.c_double),
                               P(d, ctypes.c_double), P(counts, ctypes.c_int32), P(kinds, ctypes.c_int32),
                               P(rgba, ctypes.c_uint8), len(strokes), None)
    if r != 0:
        raise MemoryError("the renderer ran out of memory")
    from PIL import Image
    out = Image.fromarray(px, "RGB")
    img.paste(out)
    return img


# the inked share at pressures 0, 16, 32, 64, 96, 128, 160, 208 and 255 (measured; see the module's note)
_AT = [0, 16, 32, 64, 96, 128, 160, 208, 255]
GRAIN = {"PENCIL": [0.02, 0.027, 0.03, 0.096, 0.19, 0.32, 0.48, 0.66, 0.81],
         "MECHANICAL": [0.02, 0.03, 0.03, 0.12, 0.21, 0.29, 0.35, 0.42, 0.52],
         "PAINTBRUSH": [0, 0, 0, 0.12, 0.73, 0.87, 0.87, 0.87, 0.87],
         "BALLPOINT": [0.8, 0.83, 0.87, 1, 1, 1, 1, 1, 1]}


def drawn(widths, k):
    """The widths drawn: the stored widths (in pixels) times response()'s factor, never under a pixel unless the factor
    says the pen leaves nothing (the light paintbrush)."""
    w = np.asarray(widths, np.float64) * k
    return np.where(np.asarray(k) > 0, np.maximum(1.0, w), 0.0)


# how much wider than render.py's scale the tablet draws a pen (the shader's is its wash)
WIDER = {"PENCIL": 1.25, "MECHANICAL": 1.3, "PAINTBRUSH": 1.25, "CALIGRAPHY": 1.37, "MARKER": 1.1, "SHADER": 1.63}
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
