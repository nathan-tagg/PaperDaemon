"""Strokes onto a picture, with PaperDaemon's one renderer (fastdecomp/render.c): the pages on the Tablet screen, the
page pictures cache, the Decompose preview, the host's drafts and what the model is shown of a page are all drawn
here, the way the tablet draws them (a pixel is inked when its center is inside the stroke's exact shape).

A stroke is (points, widths, kind, rgba): points (x, y) in the picture's pixels, widths in pixels (one per point),
kind "pen", "highlighter" or "shader", and its color (the shader's alpha in the fourth place). `ss` > 1 draws at ss
times the size and averages down, for a screen; 1 is the tablet's own pixels.
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
    kinds = np.array([KINDS[s[2]] for s in strokes], np.int32)
    rgba = np.array([(list(s[3]) + [255])[:4] for s in strokes], np.uint8).reshape(-1)
    px = np.ascontiguousarray(np.asarray(img.convert("RGB"), np.uint8))
    H, W = px.shape[:2]
    P = lambda a, t: a.ctypes.data_as(ctypes.POINTER(t))
    r = _lib().rf_render(P(px, ctypes.c_uint8), W, H, int(ss), P(xy, ctypes.c_double), P(w, ctypes.c_double),
                         P(counts, ctypes.c_int32), P(kinds, ctypes.c_int32), P(rgba, ctypes.c_uint8), len(strokes), None)
    if r != 0:
        raise MemoryError("the renderer ran out of memory")
    from PIL import Image
    out = Image.fromarray(px, "RGB")
    img.paste(out)
    return img


def pencil_tone(rgb, pressure):
    """A pencil's color at a pressure (0..1): the tablet's grain is not in the file, so a pencil reads as its color
    lightened where it was pressed lightly, as the pencil reads at normal size."""
    k = 0.6 + 0.4 * min(1.0, max(0.0, pressure))
    return tuple(int(255 - (255 - c) * k) for c in rgb)
