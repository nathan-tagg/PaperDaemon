r"""The Python face of rmfast (fastdecomp/*.c): the same arguments in and the same results out as the Python each
function replaces (rm_lean, rm_model._seam, rmb_geometry.fill, and the rm_paint / rm_regions / rmb_npops functions
that the make_* factories wrap for rm_model.run).

    import rmfast
    kept, info = rmfast.prune_join(strokes, eps_out=rm_lean.WASH_EPS, radius=50.0)     # == rm_lean.prune_join
    idx = rmfast.wash_pixels(pts, widths, ox, oy, W, H, eps)                         # == rm_raster.wash_pixels
    strokes, n = rmfast.seam(washes_m, rest, base_strokes, frame)                     # == rm_model._seam

The library is loaded from beside this file; fastdecomp/build.py makes it.
"""
import ctypes
import os
import sys
from itertools import chain as _chain

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
_LIB = None


class _Strokes(ctypes.Structure):
    _fields_ = [("n", ctypes.c_int32), ("counts", ctypes.POINTER(ctypes.c_int32)), ("xy", ctypes.POINTER(ctypes.c_double)),
                ("w", ctypes.POINTER(ctypes.c_double)), ("wash", ctypes.POINTER(ctypes.c_uint8)), ("rgb", ctypes.POINTER(ctypes.c_int32)),
                ("group", ctypes.POINTER(ctypes.c_int64)), ("kind", ctypes.POINTER(ctypes.c_uint8)), ("pkind", ctypes.POINTER(ctypes.c_uint8))]


class _Result(ctypes.Structure):
    _fields_ = [("n", ctypes.c_int32), ("counts", ctypes.POINTER(ctypes.c_int32)), ("xy", ctypes.POINTER(ctypes.c_double)),
                ("w", ctypes.POINTER(ctypes.c_double)), ("src", ctypes.POINTER(ctypes.c_int32)), ("pruned", ctypes.c_int32), ("joins", ctypes.c_int32),
                ("pkind", ctypes.POINTER(ctypes.c_uint8))]


def _view(image):
    """An "L" image as a uint8 array: rmb_npops.view (the array the image was built from, when the painter built it)
    when the painter's helpers are importable, else numpy's own conversion -- the same values either way."""
    global _VIEW
    if _VIEW is None:
        try:
            from paperdaemon.pipeline.decompose.reference import rmb_npops
            _VIEW = rmb_npops.view
        except Exception:
            _VIEW = lambda im: np.asarray(im, dtype=np.uint8)
    return _VIEW(image)


_VIEW = None


def lib():
    global _LIB
    if _LIB is None:
        name = "rmfast.dll" if sys.platform.startswith("win") else ("librmfast.dylib" if sys.platform == "darwin" else "librmfast.so")
        path = os.environ.get("RMFAST_LIB") or os.path.join(HERE, name)     # RMFAST_LIB: another build of the library
        if not os.path.exists(path):
            # never compiled on a user's machine: the app ships the library, and a checkout builds it with build.py
            raise OSError("the decomposer's C library is not there (%s); build it with fastdecomp/build.py" % path)
        L = ctypes.CDLL(path)
        L.rf_version.restype = ctypes.c_char_p
        L.rf_progress.restype = ctypes.c_int32
        L.rf_free.argtypes = [ctypes.c_void_p]
        # the one stroke renderer (render.c)
        L.rf_render.restype = ctypes.c_int32
        L.rf_render.argtypes = [ctypes.POINTER(ctypes.c_uint8), ctypes.c_int32, ctypes.c_int32, ctypes.c_int32,
                                ctypes.POINTER(ctypes.c_double), ctypes.POINTER(ctypes.c_double), ctypes.POINTER(ctypes.c_int32),
                                ctypes.POINTER(ctypes.c_int32), ctypes.POINTER(ctypes.c_uint8), ctypes.c_int32,
                                ctypes.POINTER(ctypes.c_double)]
        L.rf_wash_pixels.restype = ctypes.c_int32
        L.rf_wash_pixels.argtypes = [ctypes.POINTER(ctypes.c_double), ctypes.POINTER(ctypes.c_double), ctypes.c_int32, ctypes.c_double, ctypes.c_double,
                                     ctypes.c_int32, ctypes.c_int32, ctypes.c_double, ctypes.POINTER(ctypes.POINTER(ctypes.c_int32))]
        L.rf_prune_join.restype = ctypes.c_int
        L.rf_prune_join.argtypes = [ctypes.POINTER(_Strokes), ctypes.c_double, ctypes.c_double, ctypes.c_double, ctypes.c_int32, ctypes.POINTER(_Result)]
        L.rf_result_free.argtypes = [ctypes.POINTER(_Result)]
        L.rf_seam.restype = ctypes.c_int32
        L.rf_seam.argtypes = [ctypes.POINTER(_Strokes), ctypes.POINTER(_Strokes), ctypes.c_double, ctypes.c_double, ctypes.c_int32, ctypes.c_int32,
                              ctypes.c_double, ctypes.POINTER(ctypes.POINTER(ctypes.c_int32))]
        _LIB = L
    return _LIB


def progress():
    """How far the decompose running now has come, 0..1 (the C reports it at its stage boundaries; another thread
    may read it while the call runs)."""
    return lib().rf_progress() / 1000.0


def version():
    return lib().rf_version().decode()


class Packed:
    """A stroke list as the library takes it. Keeps the numpy arrays alive for as long as the struct is used."""

    def __init__(self, strokes, groups=None, light=False):
        """light: only what the seam reads (points, widths, which are washes) -- no colors, groups or scalar kinds."""
        n = len(strokes)
        self.counts = np.array([len(s[0]) for s in strokes], np.int32)
        total = int(self.counts.sum())
        # every coordinate and width converted to float64 once, in stroke order (exact for float32, float64 and int)
        self.xy = np.fromiter(_chain.from_iterable(_chain.from_iterable(s[0] for s in strokes)), np.float64, count=2 * total)
        self.w = np.fromiter(_chain.from_iterable(s[1] for s in strokes), np.float64, count=total)
        self.wash = np.array([1 if s[2].name.startswith("HIGHLIGHTER") else 0 for s in strokes], np.uint8)
        if light:
            self.rgb = np.zeros(3 * n, np.int32)
            self.group = np.zeros(n, np.int64)
            self.kind = np.zeros(4 * n, np.uint8)
            self._struct()
            return
        rgb = [tuple(int(v) for v in s[4][:3]) if s[4] else (255, 237, 117) for s in strokes]
        self.rgb = np.array(rgb, np.int32).reshape(-1)
        # the group key: one integer per distinct (rgb, tool, pen color), first appearance first -- an exact key, not a hash
        keys = groups if groups is not None else {}
        g = []
        for i, s in enumerate(strokes):
            k = (rgb[i], s[2], s[3])
            if k not in keys:
                keys[k] = len(keys)
            g.append(keys[k])
        self.group = np.array(g, np.int64).reshape(n)
        # the scalar type of each stroke's first and last point (x, y): NEP 50 makes the Python join's arithmetic
        # float32 where the points are numpy.float32
        kd, get = [], _KIND.get
        for s in strokes:
            pts = s[0]
            if len(pts):
                a, b = pts[0], pts[-1]
                kd.extend((get(type(a[0]), 0), get(type(a[1]), 0), get(type(b[0]), 0), get(type(b[1]), 0)))
            else:
                kd.extend((0, 0, 0, 0))
        self.kind = np.array(kd, np.uint8).reshape(4 * n)
        self._struct()

    def _struct(self):
        n = len(self.counts)
        self.struct = _Strokes(n, self.counts.ctypes.data_as(ctypes.POINTER(ctypes.c_int32)), self.xy.ctypes.data_as(ctypes.POINTER(ctypes.c_double)),
                               self.w.ctypes.data_as(ctypes.POINTER(ctypes.c_double)), self.wash.ctypes.data_as(ctypes.POINTER(ctypes.c_uint8)),
                               self.rgb.ctypes.data_as(ctypes.POINTER(ctypes.c_int32)), self.group.ctypes.data_as(ctypes.POINTER(ctypes.c_int64)),
                               self.kind.ctypes.data_as(ctypes.POINTER(ctypes.c_uint8)))


_KIND = {np.float32: 1, np.float64: 2}      # rmfast.h RF_KIND_*: anything else (a Python float or int) is 0


def wash_pixels(pts, widths, ox, oy, W, H, eps=0.0):
    xy = np.asarray(pts, np.float64).reshape(-1)
    w = np.asarray(widths, np.float64).reshape(-1)
    out = ctypes.POINTER(ctypes.c_int32)()
    n = lib().rf_wash_pixels(xy.ctypes.data_as(ctypes.POINTER(ctypes.c_double)), w.ctypes.data_as(ctypes.POINTER(ctypes.c_double)), len(w),
                             float(ox), float(oy), int(W), int(H), float(eps), ctypes.byref(out))
    if n < 0:
        raise MemoryError("rf_wash_pixels")
    if n == 0 or not out:
        if out:
            lib().rf_free(out)
        return np.empty(0, np.int32)
    idx = np.ctypeslib.as_array(out, shape=(n,)).copy()
    lib().rf_free(out)
    return idx


def _unpack(res, strokes):
    counts = np.ctypeslib.as_array(res.counts, shape=(res.n,)).copy() if res.n else np.zeros(0, np.int32)
    total = int(counts.sum())
    xy = np.ctypeslib.as_array(res.xy, shape=(2 * total,)).copy() if total else np.zeros(0)
    w = np.ctypeslib.as_array(res.w, shape=(total,)).copy() if total else np.zeros(0)
    src = np.ctypeslib.as_array(res.src, shape=(res.n,)).copy() if res.n else np.zeros(0, np.int32)
    xy2 = xy.reshape(-1, 2)
    out, k = [], 0
    for n, i in zip(counts.tolist(), src.tolist()):
        like = strokes[i]
        if n == len(like[0]):
            # a stroke the pass kept as it was (a chain of one): its own points and widths, as the Python's copy of it
            out.append((list(like[0]), list(like[1])) + tuple(like[2:5]))
        else:
            out.append((list(map(tuple, xy2[k:k + n].tolist())), w[k:k + n].tolist()) + tuple(like[2:5]))
        k += n
    return out


def prune_join(strokes, radius=6.0, max_points=4000, eps_out=None, radius_w=0.0):
    """rm_lean.prune_join, in C. -> (strokes, {"pruned": .., "joins": ..})"""
    if not len(strokes):
        return list(strokes), {"pruned": 0, "joins": 0}
    P = Packed(strokes)
    res = _Result()
    rc = lib().rf_prune_join(ctypes.byref(P.struct), -1.0 if eps_out is None else float(eps_out), float(radius), float(radius_w), int(max_points), ctypes.byref(res))
    if rc != 0:
        raise RuntimeError("rf_prune_join failed: %d" % rc)
    try:
        out = _unpack(res, strokes)
        info = {"pruned": int(res.pruned), "joins": int(res.joins)}
    finally:
        lib().rf_result_free(ctypes.byref(res))
    return out, info


def fill(mask, color, ppg, box, offset, grid, flat, api):
    """rmb_geometry.fill, in C: the ring plan of one zone mask placed onto the page. Same arguments, same strokes."""
    L = lib()
    if not hasattr(L, "_fill_ready"):
        L.rf_fill.restype = ctypes.c_int32
        L.rf_fill.argtypes = [ctypes.POINTER(ctypes.c_uint8), ctypes.c_int32, ctypes.c_int32, ctypes.c_double, ctypes.c_int, ctypes.c_double,
                              ctypes.c_double, ctypes.c_double, ctypes.c_double, ctypes.c_double, ctypes.c_int32, ctypes.c_int32, ctypes.c_int32, ctypes.c_int32,
                              ctypes.c_double, ctypes.c_double, ctypes.c_double,
                              ctypes.POINTER(ctypes.POINTER(ctypes.c_int32)), ctypes.POINTER(ctypes.POINTER(ctypes.c_double)),
                              ctypes.POINTER(ctypes.POINTER(ctypes.c_int32)), ctypes.POINTER(ctypes.POINTER(ctypes.c_int32)),
                              ctypes.POINTER(ctypes.POINTER(ctypes.c_int32))]
        L._fill_ready = True
    a = np.ascontiguousarray(_view(mask), dtype=np.uint8)        # the planner reads any non-zero byte as set
    h, w = a.shape
    gw, gh = grid if grid else (mask.size[0], mask.size[1])
    x0, y0, x1, y1 = box
    max_page = api.K.HL_WIDTHS_PAGE[0] if flat else api.K.MARKER_WIDTHS_PAGE[0]
    counts = ctypes.POINTER(ctypes.c_int32)(); xy = ctypes.POINTER(ctypes.c_double)()
    field = ctypes.POINTER(ctypes.c_int32)(); pen = ctypes.POINTER(ctypes.c_int32)(); f32 = ctypes.POINTER(ctypes.c_int32)()
    n = L.rf_fill(a.ctypes.data_as(ctypes.POINTER(ctypes.c_uint8)), h, w, float(ppg), 1 if flat else 0, float(max_page),
                  float(x0), float(y0), float(x1), float(y1), int(offset[0]), int(offset[1]), int(gw), int(gh),
                  float(api.HL_SCALE), float(api._W), float(api.K.FINELINER_MAX_PAGE),
                  ctypes.byref(counts), ctypes.byref(xy), ctypes.byref(field), ctypes.byref(pen), ctypes.byref(f32))
    if n < 0:
        raise MemoryError("rf_fill")
    out = []
    if n > 0:
        cnt = np.ctypeslib.as_array(counts, shape=(n,)).copy()
        total = int(cnt.sum())
        pts = np.ctypeslib.as_array(xy, shape=(2 * total,)).copy().reshape(-1, 2)
        fld = np.ctypeslib.as_array(field, shape=(n,)).copy().tolist()
        pn = np.ctypeslib.as_array(pen, shape=(n,)).copy().tolist()
        single = np.ctypeslib.as_array(f32, shape=(n,)).copy()
        # the Python's own scalar types: (numpy.float32, numpy.float32) tuples for a simplified loop, numpy.float64
        # pairs otherwise (iterating a 1-D array yields its numpy scalars)
        p32 = list(zip(*(lambda a: (a[:, 0], a[:, 1]))(pts.astype(np.float32)))) if single.any() else None
        p64 = list(zip(pts[:, 0], pts[:, 1])) if not single.all() else None
        k = 0
        for m, s32, f, pe in zip(cnt.tolist(), single.tolist(), fld, pn):
            p = (p32 if s32 else p64)[k:k + m]
            k += m
            if flat:
                out.append((p, [f] * m, api.Pen.HIGHLIGHTER_2, api.PenColor.HIGHLIGHT, color))
            else:
                out.append((p, [f] * m, api.Pen.FINELINER_2 if pe == 1 else api.Pen.MARKER_2, color, None))
    for ptr in (counts, xy, field, pen, f32):
        if ptr:
            L.rf_free(ptr)
    return out


def seam(washes_m, rest, base_strokes, frame, wash_eps):
    """rm_model._seam, in C: -> (washes_m + the base washes that came back + rest, how many came back)."""
    fx0, fy0, fx1, fy1 = frame
    W, H = int(round(fx1 - fx0)), int(round(fy1 - fy0))
    B = Packed(base_strokes, light=True)
    Cm = Packed(washes_m, light=True)
    out = ctypes.POINTER(ctypes.c_int32)()
    n = lib().rf_seam(ctypes.byref(B.struct), ctypes.byref(Cm.struct), float(fx0), float(fy0), W, H, float(wash_eps), ctypes.byref(out))
    if n < 0:
        raise MemoryError("rf_seam")
    add = np.ctypeslib.as_array(out, shape=(n,)).copy().tolist() if n > 0 else []
    if out:
        lib().rf_free(out)
    return list(washes_m) + [base_strokes[i] for i in add] + list(rest), len(add)


def mode_filter(lab, n, r):
    """rm_paint._mode_filter, in C: the majority label in each (2r+1)^2 window, as scipy's box filter computes it."""
    L = lib()
    if not hasattr(L, "_mode_ready"):
        L.rf_mode_filter.restype = ctypes.c_int32
        L.rf_mode_filter.argtypes = [ctypes.POINTER(ctypes.c_int64), ctypes.c_int32, ctypes.c_int32, ctypes.c_int32, ctypes.c_int32,
                                     ctypes.POINTER(ctypes.c_int64)]
        L._mode_ready = True
    a = np.ascontiguousarray(lab, dtype=np.int64)
    h, w = a.shape
    out = np.empty_like(a)
    if L.rf_mode_filter(a.ctypes.data_as(ctypes.POINTER(ctypes.c_int64)), int(h), int(w), int(n), int(r), out.ctypes.data_as(ctypes.POINTER(ctypes.c_int64))) != 0:
        raise MemoryError("rf_mode_filter")
    return out if out.dtype == lab.dtype else out.astype(lab.dtype)


def make_lab_rows(P):
    """rm_paint._lab_rows in C (fastdecomp/lab.c, every one of the 2^24 colors checked): the same (n, 3) float64."""
    original = P._lab_rows
    L = lib()
    L.rf_lab_rows.restype = None
    L.rf_lab_rows.argtypes = [ctypes.POINTER(ctypes.c_uint8), ctypes.c_int64, ctypes.POINTER(ctypes.c_double)]

    def _lab_rows(rgb):
        a = np.ascontiguousarray(np.asarray(rgb, np.uint8))
        if a.ndim != 2 or a.shape[1] != 3:
            return original(rgb)
        out = np.empty((a.shape[0], 3), np.float64)
        L.rf_lab_rows(a.ctypes.data_as(ctypes.POINTER(ctypes.c_uint8)), a.shape[0], out.ctypes.data_as(ctypes.POINTER(ctypes.c_double)))
        return out
    _lab_rows.original = original
    return _lab_rows


class _QuantParams(ctypes.Structure):
    """rmfast.h rf_quant_params, field for field."""
    _fields_ = ([(n, ctypes.c_int32) for n in ("clusters", "tc_quant", "dark_gray_washed")]
                + [(n, ctypes.c_double) for n in ("black_l", "chroma_min", "detail", "ppg", "cel_de", "dev_chroma_ceil", "tc_paper_l",
                                                  "tc_paper_chroma", "tc_ink_chroma", "ink_neutral", "ink_sat", "black_chroma", "tc_ink_l",
                                                  "ink_chroma_max", "ink_l", "paper_l", "cel_color_r", "up", "cel_mode_max_dl",
                                                  "detail_precise", "despeckle_max_ppg")])


def quant_params(P, K, clusters, black_l, chroma_min, detail, ppg):
    """rf_quant_params for one quantize call, from the painter's constants."""
    return _QuantParams(clusters=int(clusters), tc_quant=max(2, int(K.TC_QUANT)), dark_gray_washed=1 if K.DARK_GRAY_WASHED else 0,
                        black_l=float(black_l), chroma_min=float(chroma_min), detail=float(detail), ppg=float(ppg), cel_de=float(K.CEL_DE),
                        dev_chroma_ceil=float(K.DEV_CHROMA_CEIL), tc_paper_l=float(K.TC_PAPER_L), tc_paper_chroma=float(K.TC_PAPER_CHROMA),
                        tc_ink_chroma=float(K.TC_INK_CHROMA), ink_neutral=float(K.INK_NEUTRAL), ink_sat=float(K.INK_SAT),
                        black_chroma=float(K.BLACK_CHROMA), tc_ink_l=float(K.TC_INK_L), ink_chroma_max=float(P.INK_CHROMA_MAX),
                        ink_l=float(P.INK_L), paper_l=float(P.PAPER_L), cel_color_r=float(K.CEL_COLOR_R), up=float(P._UP),
                        cel_mode_max_dl=float(K.CEL_MODE_MAX_DL), detail_precise=float(P.DETAIL_PRECISE),
                        despeckle_max_ppg=float(K.DESPECKLE_MAX_PPG))


def make_quantize(P, K, N):
    """rm_paint.quantize in C: in the painter's case (an RGB grid picture, at most 256 colors, no device chroma clamp, no
    white floor) the whole of it, the palette steps included (fastdecomp/palette.c rf_quantize: the median cut, _cel_palette
    with numpy's own argsort order, classify_many, the per-pixel work); otherwise the per-pixel work in C (quant.c
    rf_unique_rgb, rf_quant_tail) around the painter's own palette steps. Returns the same masks in the same order and
    the same cover. A blur, exact mode, the despeckle median (DESPECKLE_MAX_PPG is 0 in the painter, so it never runs) or
    CEL_DE 0 run the Python instead."""
    from PIL import Image
    L = lib()
    P8, P32, P64, PD = ctypes.POINTER(ctypes.c_uint8), ctypes.POINTER(ctypes.c_int32), ctypes.POINTER(ctypes.c_int64), ctypes.POINTER(ctypes.c_double)
    L.rf_mediancut.restype = ctypes.c_int32
    L.rf_mediancut.argtypes = [P8, ctypes.c_int64, ctypes.c_int32, P8]
    L.rf_unique_rgb.restype = ctypes.c_int32
    L.rf_unique_rgb.argtypes = [P8, ctypes.c_int64, P32, ctypes.c_int32, P32]
    L.rf_quant_tail.restype = ctypes.c_int32
    L.rf_quant_tail.argtypes = [P32, ctypes.c_int32, PD, P8, P8, PD, ctypes.POINTER(ctypes.c_int8), P32, ctypes.c_int32, P8,
                                ctypes.c_int32, ctypes.c_int32, ctypes.c_int32, ctypes.c_double, ctypes.c_int32, ctypes.c_int32,
                                ctypes.c_int32, ctypes.c_double, P8, P8, ctypes.POINTER(P8), P8, P64, P64]
    original = P.quantize
    L.rf_quantize.restype = ctypes.c_int32
    L.rf_quantize.argtypes = [P8, ctypes.c_int32, ctypes.c_int32, ctypes.POINTER(_QuantParams), ctypes.POINTER(P32), ctypes.POINTER(ctypes.POINTER(P8)),
                              ctypes.POINTER(P64)]

    def whole(small, clusters, black_l, chroma_min, detail, ppg):
        """The whole quantizer in C (fastdecomp/palette.c rf_quantize, the palette steps included) -> (masks, cover), or
        None when the C refuses the call."""
        src = np.ascontiguousarray(np.asarray(small, np.uint8))
        h, w = src.shape[:2]
        q = quant_params(P, K, clusters, black_l, chroma_min, detail, ppg)
        keys, planes, counts = P32(), ctypes.POINTER(P8)(), P64()
        n = L.rf_quantize(src.ctypes.data_as(P8), int(h), int(w), ctypes.byref(q), ctypes.byref(keys), ctypes.byref(planes), ctypes.byref(counts))
        if n == -2:
            return None
        if n < 0:
            raise MemoryError("rf_quantize")
        try:
            kl = np.ctypeslib.as_array(keys, shape=(4 * n,)).tolist()
            cn = np.ctypeslib.as_array(counts, shape=(n,)).tolist()
            masks, cover, area = {}, {}, float(w * h)
            for i in range(n):
                kind = kl[4 * i]
                key = ("tone", "black", None, "_ink")[kind] if kind != 2 else ("rgb", (kl[4 * i + 1], kl[4 * i + 2], kl[4 * i + 3]))
                masks[key] = N.img(np.ctypeslib.as_array(planes[i], shape=(h, w)).copy())
            for i in range(n - 1):
                cover[P._kname(list(masks)[i])] = round(cn[i] / area, 3)
        finally:
            for i in range(n):
                L.rf_free(planes[i])
            for ptr in (planes, keys, counts):
                L.rf_free(ptr)
        return masks, cover

    def quantize(small, blur=0.0, clusters=P.CLUSTERS, black_l=P.BLACK_L, chroma_min=P.CHROMA_MIN, detail=1.0, exact=False, ppg=1.0):
        despeckle = detail < P.DETAIL_PRECISE and ppg <= K.DESPECKLE_MAX_PPG
        if blur or exact or despeckle or not K.CEL_DE > 0.0:
            return original(small, blur, clusters, black_l, chroma_min, detail, exact, ppg)
        w, h = small.size
        if small.mode == "RGB" and 1 <= clusters <= 256 and not K.DEVICE_CHROMA_MAX and P._WHITE_FLOOR is None:
            got = whole(small, clusters, black_l, chroma_min, detail, ppg)
            if got is not None:
                return got
        if small.mode == "RGB" and 1 <= clusters <= 256:
            # Pillow's median cut, vendored (fastdecomp/mediancut.c + vendor/pillow): the picture as convert("RGB")
            # of quantize(clusters, MEDIANCUT) gives it
            src = np.ascontiguousarray(np.asarray(small, np.uint8))
            qa = np.empty_like(src)
            if L.rf_mediancut(src.ctypes.data_as(P8), w * h, int(clusters), qa.ctypes.data_as(P8)) < 0:
                raise MemoryError("rf_mediancut")
        else:
            q = small.quantize(clusters, method=Image.Quantize.MEDIANCUT).convert("RGB")
            qa = np.ascontiguousarray(np.asarray(q, np.uint8))
        codes = np.empty(1 << 16, np.int32)
        inv = np.empty(w * h, np.int32)
        nu = L.rf_unique_rgb(qa.ctypes.data_as(P8), w * h, codes.ctypes.data_as(P32), len(codes), inv.ctypes.data_as(P32))
        if nu < 0:
            raise MemoryError("rf_unique_rgb")
        uniq = codes[:nu].astype(np.int64)
        ucols = np.stack([(uniq >> 16) & 255, (uniq >> 8) & 255, uniq & 255], axis=1).astype(np.uint8)
        ucols, inv = P._cel_palette(ucols, inv, K.CEL_DE, K.DEVICE_CHROMA_MAX)
        klass, uchroma = P.classify_many(ucols, black_l, chroma_min)
        chromatic = uchroma >= P.INK_CHROMA_MAX
        black_cut = int(round(black_l * 2.55))
        ink_cut = int(round(P.INK_L * 2.55))
        paper_cut = int(round(P.PAPER_L * 2.55))
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
        uL = P._lab_rows(ucols)[:, 0]
        neutral = (uchroma <= K.INK_NEUTRAL) | (uchroma <= K.INK_SAT * uL)
        r_ = max(1, int(round(P._gu(K.CEL_COLOR_R) / max(0.5, detail)))) if K.CEL_COLOR_R > 0 else 0
        ulum = np.ascontiguousarray(0.299 * ucols[:, 0] + 0.587 * ucols[:, 1] + 0.114 * ucols[:, 2], np.float64)
        rgb = np.ascontiguousarray(np.asarray(small.convert("RGB"), np.uint8))
        nk = len(ckeys)
        tone, black, ink = (np.empty((h, w), np.uint8) for _ in range(3))
        karr = [np.empty((h, w), np.uint8) for _ in range(nk)]
        first = np.empty(2 + 2 * nk, np.int64)
        counts = np.empty(3 + nk, np.int64)
        inv32 = np.ascontiguousarray(inv, np.int32)
        nflag, cflag = np.ascontiguousarray(neutral, np.uint8), np.ascontiguousarray(chromatic, np.uint8)
        uch = np.ascontiguousarray(uchroma, np.float64)
        if L.rf_quant_tail(inv32.ctypes.data_as(P32), len(ucols), ulum.ctypes.data_as(PD), nflag.ctypes.data_as(P8), cflag.ctypes.data_as(P8),
                           uch.ctypes.data_as(PD), cat.ctypes.data_as(ctypes.POINTER(ctypes.c_int8)), kidx.ctypes.data_as(P32), nk,
                           rgb.ctypes.data_as(P8), h, w, r_, float(K.CEL_MODE_MAX_DL), black_cut, ink_cut, paper_cut, float(K.BLACK_CHROMA),
                           tone.ctypes.data_as(P8), black.ctypes.data_as(P8), (P8 * max(1, nk))(*[a.ctypes.data_as(P8) for a in karr]),
                           ink.ctypes.data_as(P8), first.ctypes.data_as(P64), counts.ctypes.data_as(P64)) != 0:
            raise MemoryError("rf_quant_tail")
        fl = first.tolist()
        cn = counts.tolist()
        order = []
        if fl[0] >= 0:
            order.append((2 * fl[0], "tone", tone, cn[0]))
        if fl[1] >= 0:
            order.append((2 * fl[1], "black", black, cn[1]))
        for j, key in enumerate(ckeys):
            f3, f1 = fl[2 + 2 * j], fl[3 + 2 * j]
            if f3 < 0 and f1 < 0:
                continue
            pos = min([p for p in (2 * f3 if f3 >= 0 else None, 2 * f1 + 1 if f1 >= 0 else None) if p is not None])
            order.append((pos, key, karr[j], cn[3 + j]))
        order.sort(key=lambda t: t[0])
        masks, area = {}, float(w * h)
        cover = {}
        for _pos, key, arr, c in order:
            masks[key] = N.img(arr)
        masks["_ink"] = N.img(ink)
        for _pos, key, arr, c in order:
            cover[P._kname(key)] = round(c / area, 3)
        return masks, cover
    quantize.original = original
    quantize.whole = whole
    return quantize


def make_picture_stats(P, K):
    """rm_paint.skin_cast_offset and rm_paint.dark_field in C (fastdecomp/stats.c): the same values, the same types.
    -> {name: function} to set on rm_paint for a run."""
    L = lib()
    P8, PD, P32 = ctypes.POINTER(ctypes.c_uint8), ctypes.POINTER(ctypes.c_double), ctypes.POINTER(ctypes.c_int32)
    L.rf_skin_cast.restype = ctypes.c_int32
    L.rf_skin_cast.argtypes = [P8, ctypes.c_int32, ctypes.c_int32, ctypes.c_double, ctypes.c_double, ctypes.c_double, PD, PD, PD]
    L.rf_dark_field.restype = ctypes.c_int32
    L.rf_dark_field.argtypes = [P8, ctypes.c_int32, ctypes.c_int32, ctypes.c_double, ctypes.c_double, ctypes.c_double, P32, PD, PD]
    original = dict(skin_cast_offset=P.skin_cast_offset, dark_field=P.dark_field)

    def _rgb(small):
        return np.ascontiguousarray(np.asarray(small.convert("RGB"), np.uint8))

    def skin_cast_offset(small):
        if not K.SKIN_CAST_ON:
            return 0.0, (0.0, 0.0)
        a = _rgb(small)
        off, da, db = ctypes.c_double(), ctypes.c_double(), ctypes.c_double()
        if L.rf_skin_cast(a.ctypes.data_as(P8), a.shape[0], a.shape[1], float(K.SKIN_CAST_DEADBAND), float(K.SKIN_CAST_REF_HUE),
                          float(K.SKIN_CAST_MAX_DEG), ctypes.byref(off), ctypes.byref(da), ctypes.byref(db)) != 0:
            raise MemoryError("rf_skin_cast")
        return off.value, (da.value, db.value)

    def dark_field(small):
        a = _rgb(small)
        on, share, big = ctypes.c_int32(), ctypes.c_double(), ctypes.c_double()
        if L.rf_dark_field(a.ctypes.data_as(P8), a.shape[0], a.shape[1], float(P.BLACK_L), float(K.DARK_FIELD_MIN_COVER),
                           float(K.DARK_FIELD_MIN_REGION), ctypes.byref(on), ctypes.byref(share), ctypes.byref(big)) != 0:
            raise MemoryError("rf_dark_field")
        if share.value < K.DARK_FIELD_MIN_COVER:
            return False, share.value, 0.0
        return bool(on.value), share.value, big.value
    return dict(skin_cast_offset=skin_cast_offset, dark_field=dark_field), original


def make_absorb_specks(P, K, N):
    """rm_paint.absorb_specks, in C (fastdecomp/absorb.c), with the same signature and the same effect on `masks`.
    The painter always passes the picture; without it the Python runs (its nearest-zone fallback needs the distance
    transform's indices, which the C does not compute)."""
    original = P.absorb_specks
    I32, U8, F64, I64 = ctypes.POINTER(ctypes.c_int32), ctypes.POINTER(ctypes.c_uint8), ctypes.POINTER(ctypes.c_double), ctypes.POINTER(ctypes.c_int64)
    L = lib()
    L.rf_absorb_prepare_masks.restype = ctypes.c_int64
    L.rf_absorb_prepare_masks.argtypes = [ctypes.POINTER(U8), ctypes.c_int32, ctypes.c_int32, ctypes.c_int32, ctypes.c_int32, ctypes.c_int64, I32, I32, U8]
    L.rf_split_labels.restype = None
    L.rf_split_labels.argtypes = [I32, ctypes.c_int32, ctypes.c_int32, ctypes.c_int32, ctypes.POINTER(U8)]
    L.rf_absorb_run.restype = ctypes.c_int32
    L.rf_absorb_run.argtypes = [I32, I32, U8, F64, ctypes.c_int32, ctypes.c_int32, ctypes.c_int32, ctypes.c_int64, ctypes.c_double, ctypes.c_double, I32, I64]

    def absorb_specks(masks, min_span_col, grid_w, gh, small=None):
        keys = [k for k in masks if k not in ("black", "tone", "_ink")]
        if small is None or not keys:
            return original(masks, min_span_col, grid_w, gh, small)
        views = [np.ascontiguousarray(N.view(masks[k]), dtype=np.uint8) for k in keys]
        if any(v.shape != (gh, grid_w) for v in views):
            return original(masks, min_span_col, grid_w, gh, small)
        ptrs = (U8 * len(views))(*[v.ctypes.data_as(U8) for v in views])
        own_lab = np.empty((gh, grid_w), np.int32)
        lab_img = np.empty((gh, grid_w), np.int32)
        weak = np.empty((gh, grid_w), np.uint8)
        n_weak = int(L.rf_absorb_prepare_masks(ptrs, len(keys), int(gh), int(grid_w), int(min_span_col), int(K.ABSORB_MAX_AREA + 1),
                                               own_lab.ctypes.data_as(I32), lab_img.ctypes.data_as(I32), weak.ctypes.data_as(U8)))
        if n_weak < 0:
            raise MemoryError("rf_absorb_prepare_masks")
        if not n_weak or not (lab_img >= 0).any():
            return {"absorbed": 0.0}
        rgb = np.asarray(small.convert("RGB"), np.uint8)
        lab_all = np.ascontiguousarray(P._lab_rows(rgb.reshape(-1, 3)).reshape(gh, grid_w, 3), np.float64)
        out_lab = np.empty((gh, grid_w), np.int32)
        stats = np.zeros(2, np.int64)
        if L.rf_absorb_run(own_lab.ctypes.data_as(I32), lab_img.ctypes.data_as(I32), weak.ctypes.data_as(U8), lab_all.ctypes.data_as(F64), len(keys),
                           int(gh), int(grid_w), int(K.ABSORB_MAX_AREA), float(K.ABSORB_MAX_DE), float(K.ABSORB_MAX_DE ** 2),
                           out_lab.ctypes.data_as(I32), stats.ctypes.data_as(I64)) < 0:
            raise MemoryError("rf_absorb_run")
        outs = [np.empty((gh, grid_w), np.uint8) for _ in keys]
        L.rf_split_labels(out_lab.ctypes.data_as(I32), len(keys), int(gh), int(grid_w), (U8 * len(outs))(*[o.ctypes.data_as(U8) for o in outs]))
        for i, k in enumerate(keys):
            masks[k] = N.img(outs[i])
        return {"absorbed": round(n_weak / float(grid_w * gh), 4),
                "mixed_color_pixels_preserved": int(stats[0]),
                "changed_pixels": int(stats[1])}
    absorb_specks.original = original
    return absorb_specks


def make_shadow_zones(P, K, N):
    """rm_paint.shadow_zones with its per-zone loop (an erosion of each zone over the whole grid and a mean of the
    gradient under it) in C (fastdecomp/zones.c). Every other line is the painter's own, in its order; the result and
    the report are the same."""
    import math
    from PIL import ImageFilter
    L = lib()
    L.rf_zone_interior.restype = ctypes.c_int32
    L.rf_zone_interior.argtypes = [ctypes.POINTER(ctypes.c_int32), ctypes.c_int32, ctypes.c_int32, ctypes.c_int32,
                                   ctypes.POINTER(ctypes.c_double), ctypes.POINTER(ctypes.c_double)]

    def shadow_zones(masks, small, grid_w, gh, keys=None):
        keys = [k for k in masks if k not in ("black", "tone", "_ink")] if keys is None else keys
        rep = {"zones": len(keys), "shadow": 0, "pairs": 0}
        if len(keys) < 2:
            return np.zeros((gh, grid_w), bool), rep
        lab_img = np.full((gh, grid_w), -1, np.int32)
        for i, k in enumerate(keys):
            lab_img[N.view(masks[k]) != 0] = i
        rgb = np.asarray(small.convert("RGB"), np.uint8).reshape(-1, 3)
        lab_all = P._lab_rows(rgb)
        n = len(keys)
        means = np.zeros((n, 3), np.float64)
        sizes = np.zeros(n, np.int64)
        flat_lab = lab_img.reshape(-1)
        for i in range(n):
            sel = flat_lab == i
            sizes[i] = int(sel.sum())
            if sizes[i]:
                means[i] = lab_all[sel].mean(axis=0)
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
        # the per-zone flatness, in C
        interior = np.zeros(n, np.float64)
        lab_c = np.ascontiguousarray(lab_img, np.int32)
        grad_c = np.ascontiguousarray(grad, np.float64)
        if L.rf_zone_interior(lab_c.ctypes.data_as(ctypes.POINTER(ctypes.c_int32)), int(gh), int(grid_w), int(n),
                           grad_c.ctypes.data_as(ctypes.POINTER(ctypes.c_double)), interior.ctypes.data_as(ctypes.POINTER(ctypes.c_double))) != 0:
            raise MemoryError("rf_zone_interior")
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
                continue
            ca = math.hypot(means[dark][1], means[dark][2])
            cb = math.hypot(means[light][1], means[light][2])
            if min(ca, cb) >= K.SHADOW_MIN_CHROMA:
                ha = math.degrees(math.atan2(means[dark][2], means[dark][1]))
                hb = math.degrees(math.atan2(means[light][2], means[light][1]))
                if abs((ha - hb + 180.0) % 360.0 - 180.0) > K.SHADOW_HUE_TOL:
                    continue
            if soft_sum[cd] / c > K.SHADOW_MAX_EDGE:
                continue
            if means[dark][0] > l_cut:
                continue
            if interior[dark] < K.SHADOW_MIN_INTERNAL_GRAD:
                continue
            shade[dark] = True
        rep["shadow"] = int(shade.sum())
        out = np.zeros((gh, grid_w), bool)
        for i in np.flatnonzero(shade).tolist():
            out |= lab_img == i
        return out, rep
    shadow_zones.original = P.shadow_zones
    return shadow_zones


def make_shadow_zones_c(P, K, N):
    """rm_paint.shadow_zones entirely in C (fastdecomp/zones.c rf_shadow_zones): the same mask and the same report.
    A grid under 2 x 2 (where np.gradient raises) runs the Python."""
    original = P.shadow_zones
    L = lib()
    P8 = ctypes.POINTER(ctypes.c_uint8)
    L.rf_shadow_zones.restype = ctypes.c_int32
    L.rf_shadow_zones.argtypes = [ctypes.POINTER(P8), ctypes.c_int32, ctypes.c_int32, ctypes.c_int32, P8, ctypes.c_float] + \
        [ctypes.c_double] * 7 + [P8, ctypes.POINTER(ctypes.c_double), ctypes.POINTER(ctypes.c_int32), ctypes.POINTER(ctypes.c_int32)]

    def shadow_zones(masks, small, grid_w, gh, keys=None):
        keys = [k for k in masks if k not in ("black", "tone", "_ink")] if keys is None else keys
        rep = {"zones": len(keys), "shadow": 0, "pairs": 0}
        if len(keys) < 2:
            return np.zeros((gh, grid_w), bool), rep
        views = [np.ascontiguousarray(N.view(masks[k]), dtype=np.uint8) for k in keys]
        rgb = np.ascontiguousarray(np.asarray(small.convert("RGB"), np.uint8))
        if any(v.shape != (gh, grid_w) for v in views) or rgb.shape != (gh, grid_w, 3):
            return original(masks, small, grid_w, gh, keys)
        out = np.empty((gh, grid_w), np.uint8)
        l_cut, pairs, shadow = ctypes.c_double(), ctypes.c_int32(), ctypes.c_int32()
        ptrs = (P8 * len(views))(*[v.ctypes.data_as(P8) for v in views])
        rc = L.rf_shadow_zones(ptrs, len(views), int(gh), int(grid_w), rgb.ctypes.data_as(P8), ctypes.c_float(K.SHADOW_EDGE_BLUR),
                               float(K.SHADOW_MIN_BORDER), float(K.SHADOW_L_STEP), float(K.SHADOW_MIN_CHROMA), float(K.SHADOW_HUE_TOL),
                               float(K.SHADOW_MAX_EDGE), float(K.SHADOW_MIN_INTERNAL_GRAD), float(K.SHADOW_L_PCT),
                               out.ctypes.data_as(P8), ctypes.byref(l_cut), ctypes.byref(pairs), ctypes.byref(shadow))
        if rc == -2:
            return original(masks, small, grid_w, gh, keys)
        if rc != 0:
            raise MemoryError("rf_shadow_zones")
        rep["l_cut"] = round(l_cut.value, 1)
        rep["pairs"] = int(pairs.value)
        rep["shadow"] = int(shadow.value)
        return out.view(bool), rep
    shadow_zones.original = original
    return shadow_zones


def make_region_stages(RG, P, N):
    """rm_regions.pieces, _stats and _edges in C (fastdecomp/regions.c), same arguments and results.
    -> {name: function} to set on rm_regions for a run."""
    L = lib()
    I32, U8, F64, I64 = ctypes.POINTER(ctypes.c_int32), ctypes.POINTER(ctypes.c_uint8), ctypes.POINTER(ctypes.c_double), ctypes.POINTER(ctypes.c_int64)
    L.rf_pieces.restype = ctypes.c_int32
    L.rf_pieces.argtypes = [ctypes.POINTER(U8), ctypes.c_int32, ctypes.c_int32, ctypes.c_int32, I32, I32]
    L.rf_region_stats.restype = ctypes.c_int32
    L.rf_region_stats.argtypes = [I32, F64, ctypes.c_int32, ctypes.c_int32, ctypes.c_int32, F64, F64, F64, F64, F64, F64]
    L.rf_region_edges.restype = ctypes.c_int32
    L.rf_region_edges.argtypes = [I32, F64, ctypes.c_int32, ctypes.c_int32, ctypes.c_int32,
                                  ctypes.POINTER(I64), ctypes.POINTER(I64), ctypes.POINTER(F64), ctypes.POINTER(F64)]
    original = dict(pieces=RG.pieces, _stats=RG._stats, _edges=RG._edges)

    def pieces(masks, grid):
        gw, gh = grid
        views = [N.view(m) for m in masks.values()]
        if any(v.ndim != 2 or v.shape != (gh, gw) for v in views):
            return original["pieces"](masks, grid)
        # each uint8 mask read in place (> 0 is non-zero there); any other dtype as its 0/1 test
        arrs = [np.ascontiguousarray(v) if v.dtype == np.uint8 else np.ascontiguousarray(v > 0, dtype=np.uint8) for v in views]
        ptrs = (U8 * max(1, len(arrs)))(*[a.ctypes.data_as(U8) for a in arrs])
        labels = np.empty((gh, gw), np.int32)
        per = np.zeros(max(1, len(views)), np.int32)
        if L.rf_pieces(ptrs, len(views), int(gh), int(gw), labels.ctypes.data_as(I32), per.ctypes.data_as(I32)) < 0:
            raise MemoryError("rf_pieces")
        cls_of, names, frozen = [], [], []
        for ci, k in enumerate(masks):
            cls_of.extend([ci] * int(per[ci]))
            names.append(P._kname(k))
            frozen.append(not (isinstance(k, tuple) and k[0] == "rgb"))
        return labels, np.array(cls_of, np.int32), names, np.array(frozen, bool)

    def _stats(labels, lab_img, n):
        lab = np.ascontiguousarray(labels, np.int32)
        li = np.ascontiguousarray(lab_img, np.float64)
        H, W = lab.shape
        area, cx, cy, bw, bh = (np.empty(n, np.float64) for _ in range(5))
        sum_lab = np.empty((n, 3), np.float64)
        if L.rf_region_stats(lab.ctypes.data_as(I32), li.ctypes.data_as(F64), int(H), int(W), int(n), area.ctypes.data_as(F64), sum_lab.ctypes.data_as(F64),
                             cx.ctypes.data_as(F64), cy.ctypes.data_as(F64), bw.ctypes.data_as(F64), bh.ctypes.data_as(F64)) != 0:
            raise MemoryError("rf_region_stats")
        return area, sum_lab, cx, cy, bw, bh

    def _edges(labels, lab_img, n):
        lab = np.ascontiguousarray(labels, np.int32)
        li = np.ascontiguousarray(lab_img, np.float64)
        H, W = lab.shape
        pa, pb, pc, pd = I64(), I64(), F64(), F64()
        m = L.rf_region_edges(lab.ctypes.data_as(I32), li.ctypes.data_as(F64), int(H), int(W), int(n), ctypes.byref(pa), ctypes.byref(pb), ctypes.byref(pc), ctypes.byref(pd))
        if m < 0:
            raise MemoryError("rf_region_edges")
        out = [np.ctypeslib.as_array(p, shape=(m,)).copy() if m else np.zeros(0, t) for p, t in ((pa, np.int64), (pb, np.int64), (pc, np.float64), (pd, np.float64))]
        for p in (pa, pb, pc, pd):
            L.rf_free(p)
        return tuple(out)
    return dict(pieces=pieces, _stats=_stats, _edges=_edges), original


def make_merge(RG, K):
    """rm_regions.merge_to_budget and rm_regions.recolored in C (fastdecomp/merge.c): the same arguments, the same
    labels, report (each round's seconds measured in C; the log lines are written after the rounds) and picture.
    -> (merge_to_budget, recolored)."""
    L = lib()
    I32, U8, F64, I64 = (ctypes.POINTER(t) for t in (ctypes.c_int32, ctypes.c_uint8, ctypes.c_double, ctypes.c_int64))
    c32, c64, cd = ctypes.c_int32, ctypes.c_int64, ctypes.c_double
    L.rf_merge_to_budget.restype = c32
    L.rf_merge_to_budget.argtypes = [I32, c32, c32, I32, U8, c32, F64, cd, c64, F64, cd, cd, cd, c32, c32,
                                     I32, I64, I32, U8, I32, I64, I64, F64, F64, I64]
    L.rf_recolor.restype = c64
    L.rf_recolor.argtypes = [U8, I32, I32, c32, c32, I64, c32, U8]
    original = RG.recolored

    def ptr(a, t):
        return a.ctypes.data_as(t)

    def merge_to_budget(labels, cls_of, frozen_cls, lab_img, ppg, budget=RG.BUDGET, knobs=RG.KNOBS, log=None, cut_specks=True):
        lab0 = np.ascontiguousarray(labels, np.int32)
        H, W = lab0.shape
        cls_in = np.ascontiguousarray(cls_of, np.int32)
        n = int(cls_in.size)
        fz = np.ascontiguousarray(frozen_cls, np.uint8)
        li = np.ascontiguousarray(lab_img, np.float64)
        kn = np.array([knobs[k] for k in ("area", "contrast", "rarity", "density", "elong", "contrast_floor")], np.float64)
        R = max(0, int(RG.MAX_ROUNDS))
        out = np.empty((H, W), np.int32)
        orig, cls, fr = np.empty(n + 1, np.int64), np.empty(n + 1, np.int32), np.empty(n + 1, np.uint8)
        kind, pool, merged = np.zeros(R + 1, np.int32), np.zeros(R + 1, np.int64), np.zeros(R + 1, np.int64)
        cut, secs, counts = np.zeros(R + 1), np.zeros(R + 1), np.zeros(6, np.int64)
        m = L.rf_merge_to_budget(ptr(lab0, I32), int(H), int(W), ptr(cls_in, I32), ptr(fz, U8), n, ptr(li, F64), float(ppg), int(budget),
                                 ptr(kn, F64), float(K.ABSORB_MAX_AREA), float(RG.DENSITY_CELL_PAGE), float(RG.ROUND_FRACTION), R,
                                 int(bool(cut_specks)), ptr(out, I32), ptr(orig, I64), ptr(cls, I32), ptr(fr, U8), ptr(kind, I32),
                                 ptr(pool, I64), ptr(merged, I64), ptr(cut, F64), ptr(secs, F64), ptr(counts, I64))
        if m == -2:
            raise ZeroDivisionError("float division by zero")     # the reference's DENSITY_CELL_PAGE / ppg with ppg 0
        if m < 0:
            raise MemoryError("rf_merge_to_budget")
        rep = dict(pieces=n, color_pieces=int(counts[2]), drawable_pieces=int(counts[3]), budget=budget, rounds=[], touched=False,
                   specks_cut=int(counts[1]))
        for r in range(int(counts[0])):
            name = "specks" if kind[r] == 0 else "budget"
            value_cut = None if kind[r] == 0 else round(float(cut[r]), 2)
            rep["rounds"].append(dict(kind=name, drawable=int(pool[r]), merged=int(merged[r]), secs=round(float(secs[r]), 1), value_cut=value_cut))
            if log:
                log("  round %d (%s): %s drawable pieces, merged %s (%.1f s%s)" % (r + 1, name, format(int(pool[r]), ","), format(int(merged[r]), ","),
                                                                                  float(secs[r]), "" if value_cut is None else "; value cut %.2f" % value_cut))
        rep.update(touched=bool(rep["rounds"]), final_color_pieces=int(counts[4]), final_drawable_pieces=int(counts[5]),
                   orig_of=orig[:m].copy(), frozen=fr[:m].astype(bool), cls=cls[:m].copy())
        return out, rep

    def recolored(small, labels0, labels, rep):
        rgb = np.ascontiguousarray(np.asarray(small, np.uint8))
        lab0 = np.ascontiguousarray(labels0, np.int32)
        lab = np.ascontiguousarray(labels, np.int32)
        H, W = lab.shape
        if rgb.shape != (H, W, 3) or lab0.shape != (H, W):
            return original(small, labels0, labels, rep)
        orig = np.ascontiguousarray(rep["orig_of"], np.int64)
        out = np.empty_like(rgb)
        moved = L.rf_recolor(ptr(rgb, U8), ptr(lab0, I32), ptr(lab, I32), int(H), int(W), ptr(orig, I64), int(rep["cls"].size), ptr(out, U8))
        if moved < 0:
            raise MemoryError("rf_recolor")
        rep["recolored_px"] = int(moved)
        from PIL import Image
        return Image.fromarray(out)
    return merge_to_budget, recolored


def _lazy_image_class():
    """An "L" image over a numpy array whose PIL core is made the first time anything asks for it (the `im`
    property): what Image.fromarray(a, "L") makes -- the same read-only buffer mapping -- minus the work for the many
    crops that are only ever read back as arrays (rmb_npops.view reads the array it was made from)."""
    from PIL import Image

    class LazyL(Image.Image):
        @property
        def im(self):
            if self._im is None:
                self._im = Image.core.map_buffer(self._rm_buf, self._size, "raw", 0, ("L", 0, 1))
            return self._im

        @im.setter
        def im(self, value):
            self._im = value
    return LazyL


_LAZY = None


def lazy_l_image(a, attr):
    """An "L" image of the contiguous uint8 array a, with the array attached under `attr` (rmb_npops' cache)."""
    global _LAZY
    if _LAZY is None:
        _LAZY = _lazy_image_class()
    im = _LAZY()
    im._mode = "L"
    im._size = (a.shape[1], a.shape[0])
    im.readonly = 1
    im._rm_buf = a
    setattr(im, attr, a)
    return im


class Components(list):
    """The list rmb_npops.components returns, carrying the C arrays it was made from for the C stages that read the
    components again: info (5 per component: area, x0, y0, width, height) and buf (the crops end to end)."""
    __slots__ = ("info", "buf")


def make_components(N):
    """rmb_npops.components in C (fastdecomp/label.c rf_components): the same list of (area, crop image, offset), in
    the same order (largest first, equal areas by first raster pixel). The crops are made lazily (lazy_l_image)."""
    L = lib()
    L.rf_components.restype = ctypes.c_int32
    L.rf_components.argtypes = [ctypes.POINTER(ctypes.c_uint8), ctypes.c_int32, ctypes.c_int32, ctypes.c_int32, ctypes.c_int64,
                                ctypes.POINTER(ctypes.POINTER(ctypes.c_int64)), ctypes.POINTER(ctypes.POINTER(ctypes.c_uint8)), ctypes.POINTER(ctypes.c_int64)]

    def components(mask, min_span, min_area=0):
        a = np.ascontiguousarray(N.view(mask), dtype=np.uint8)
        if a.ndim != 2:
            return components.original(mask, min_span, min_area)
        H, W = a.shape
        info, crops, total = ctypes.POINTER(ctypes.c_int64)(), ctypes.POINTER(ctypes.c_uint8)(), ctypes.c_int64()
        n = L.rf_components(a.ctypes.data_as(ctypes.POINTER(ctypes.c_uint8)), int(H), int(W), int(min_span), int(min_area),
                            ctypes.byref(info), ctypes.byref(crops), ctypes.byref(total))
        if n < 0:
            raise MemoryError("rf_components")
        out = Components()
        out.info, out.buf = np.zeros(0, np.int64), np.zeros(0, np.uint8)
        if n > 0:
            out.info = np.ctypeslib.as_array(info, shape=(5 * n,)).copy()
            inf = out.info.tolist()
            buf = out.buf = np.ctypeslib.as_array(crops, shape=(int(total.value),)).copy()
            off = 0
            for t in range(n):
                area, x0, y0, w, h = inf[5 * t:5 * t + 5]
                size = (h + 2) * (w + 2)
                out.append((area, lazy_l_image(buf[off:off + size].reshape(h + 2, w + 2), N._ATTR), (x0 - 1, y0 - 1)))
                off += size
        if info:
            L.rf_free(info)
        if crops:
            L.rf_free(crops)
        return out
    components.original = N.components
    return components


def make_outline(P, N):
    """rm_paint._outline in C (fastdecomp/outline.c): (the chains at least min_len_g long, simplified, as lists of
    (x, y) tuples; the total length), with CPython's own hypot and sum."""
    L = lib()
    L.rf_outline.restype = ctypes.c_int32
    L.rf_outline.argtypes = [ctypes.POINTER(ctypes.c_uint8), ctypes.c_int32, ctypes.c_int32, ctypes.c_int32, ctypes.c_int32, ctypes.c_double,
                             ctypes.POINTER(ctypes.c_double), ctypes.POINTER(ctypes.POINTER(ctypes.c_int32)), ctypes.POINTER(ctypes.POINTER(ctypes.c_double))]
    original = P._outline

    def _outline(mask, gw, gh, min_len_g):
        a = mask if isinstance(mask, np.ndarray) else N.view(mask)
        if a.ndim != 2 or a.dtype not in (np.uint8, np.bool_):
            return original(mask, gw, gh, min_len_g)
        a = np.ascontiguousarray(a, dtype=np.uint8)
        H, W = a.shape
        total = ctypes.c_double()
        counts, xy = ctypes.POINTER(ctypes.c_int32)(), ctypes.POINTER(ctypes.c_double)()
        n = L.rf_outline(a.ctypes.data_as(ctypes.POINTER(ctypes.c_uint8)), int(H), int(W), int(gw), int(gh), float(min_len_g),
                         ctypes.byref(total), ctypes.byref(counts), ctypes.byref(xy))
        if n < 0:
            raise MemoryError("rf_outline")
        out = []
        if n > 0:
            cnt = np.ctypeslib.as_array(counts, shape=(n,)).tolist()
            pts = np.ctypeslib.as_array(xy, shape=(2 * sum(cnt),)).reshape(-1, 2).tolist()
            k = 0
            for m in cnt:
                out.append(list(map(tuple, pts[k:k + m])))
                k += m
        for p in (counts, xy):
            if p:
                L.rf_free(p)
        return out, total.value
    _outline.original = original
    return _outline


def make_fill_holes(P, N, K):
    """rm_paint._fill_holes in C (fastdecomp/outline.c rf_fill_holes): the same enclosed pockets filled, the same mask
    object back when none is."""
    L = lib()
    L.rf_fill_holes.restype = ctypes.c_int32
    L.rf_fill_holes.argtypes = [ctypes.POINTER(ctypes.c_uint8), ctypes.c_int32, ctypes.c_int32, ctypes.c_double, ctypes.c_double, ctypes.POINTER(ctypes.c_uint8)]
    original = P._fill_holes

    def _fill_holes(mask, ppg):
        a = np.ascontiguousarray(N.view(mask), dtype=np.uint8)
        if a.ndim != 2 or getattr(mask, "mode", "L") != "L":
            return original(mask, ppg)
        H, W = a.shape
        small = (K.FILL_HOLE_PAGE / ppg) ** 2              # Python's own power, as the painter computes it
        thin = P._gu(1.5)
        out = np.empty_like(a)
        n = L.rf_fill_holes(a.ctypes.data_as(ctypes.POINTER(ctypes.c_uint8)), int(H), int(W), float(small), float(thin),
                            out.ctypes.data_as(ctypes.POINTER(ctypes.c_uint8)))
        if n < 0:
            raise MemoryError("rf_fill_holes")
        return mask if n == 0 else N.img(out)
    _fill_holes.original = original
    return _fill_holes

def make_thin(LA):
    """rmb_lineart.thin in C (fastdecomp/xdog.c rf_thin): Zhang-Suen of the mask padded by one pixel -> the same
    boolean grid (the contour pass's and the hatch bands' thinning)."""
    L = lib()
    L.rf_thin.restype = ctypes.c_int32
    L.rf_thin.argtypes = [ctypes.POINTER(ctypes.c_uint8), ctypes.c_int32, ctypes.c_int32, ctypes.POINTER(ctypes.c_uint8)]
    original = LA.thin

    def thin(fg):
        a = np.asarray(fg)
        if a.ndim != 2 or a.size == 0:
            return original(fg)
        a = np.ascontiguousarray(a, dtype=np.bool_).view(np.uint8)       # as the Python's bool grid holds it
        H, W = a.shape
        out = np.empty((H, W), np.uint8)
        if L.rf_thin(a.ctypes.data_as(ctypes.POINTER(ctypes.c_uint8)), int(H), int(W), out.ctypes.data_as(ctypes.POINTER(ctypes.c_uint8))) != 0:
            raise MemoryError("rf_thin")
        return out.view(np.bool_)
    thin.original = original
    return thin


def make_rank_ext(N):
    """rmb_npops.rank_ext in C (fastdecomp/rank.c rf_rank_ext): the k x k maximum or minimum with the edge replicated
    -> the same new uint8 grid, for any k >= 1 (scipy raises below that, and runs for a grid that is not 2-D)."""
    L = lib()
    P8 = ctypes.POINTER(ctypes.c_uint8)
    L.rf_rank_ext.restype = ctypes.c_int32
    L.rf_rank_ext.argtypes = [P8, ctypes.c_int32, ctypes.c_int32, ctypes.c_int32, ctypes.c_int32, P8]
    original = N.rank_ext

    def rank_ext(a, k, ismax):
        a = np.ascontiguousarray(a, dtype=np.uint8)
        if a.ndim != 2 or type(k) is not int or not 1 <= k < 2 ** 31:
            return original(a, k, ismax)
        H, W = a.shape
        out = np.empty((H, W), np.uint8)
        r = L.rf_rank_ext(a.ctypes.data_as(P8), int(H), int(W), int(k), 1 if ismax else 0, out.ctypes.data_as(P8))
        if r == -2:
            return original(a, k, ismax)
        if r != 0:
            raise MemoryError("rf_rank_ext")
        return out
    rank_ext.original = original
    return rank_ext


PIL_MODES = ("1", "L", "I;16", "RGB", "P", "LA", "RGBA")      # decode.c's and jpeg.c's mode codes


def make_decode():
    """The source read in C: a PNG (fastdecomp/decode.c) or JPEG (fastdecomp/jpeg.c) file as Pillow 12.3.0 reads it --
    the pixels of Image.open(...).convert("RGB") and Image.open(...)'s mode. -> read(source) -> (H x W x 3 uint8 array,
    mode) or None when the source is not a path or bytes, neither format, or a file the C readers refuse (the caller
    then reads it with Pillow); read.size(source) -> (width, height) from the header alone, or None alike."""
    L = lib()
    P8, P32 = ctypes.POINTER(ctypes.c_uint8), ctypes.POINTER(ctypes.c_int32)
    for name in ("rf_png_info", "rf_png_rgb", "rf_jpeg_info", "rf_jpeg_rgb"):
        getattr(L, name).restype = ctypes.c_int32
    L.rf_png_info.argtypes = L.rf_jpeg_info.argtypes = [P8, ctypes.c_int64, P32]
    L.rf_png_rgb.argtypes = L.rf_jpeg_rgb.argtypes = [P8, ctypes.c_int64, P8]

    def _bytes(source):
        if isinstance(source, (bytes, bytearray, memoryview)):
            return bytes(source)
        if isinstance(source, (str, os.PathLike)):
            try:
                with open(source, "rb") as f:
                    return f.read()
            except OSError:
                return None
        return None

    def _reader(data):
        if data[:8] == b"\x89PNG\r\n\x1a\n":
            return L.rf_png_info, L.rf_png_rgb
        if data[:2] == b"\xff\xd8":
            return L.rf_jpeg_info, L.rf_jpeg_rgb
        return None, None

    def _info(data):
        info_fn, rgb_fn = _reader(data)
        if info_fn is None:
            return None, None, None
        buf = np.frombuffer(data, np.uint8)
        info = np.zeros(3, np.int32)
        if info_fn(buf.ctypes.data_as(P8), len(buf), info.ctypes.data_as(P32)) != 0:
            return None, None, None
        return buf, info.tolist(), rgb_fn

    def read(source):
        data = _bytes(source)
        if data is None:
            return None
        buf, info, rgb_fn = _info(data)
        if buf is None:
            return None
        w, h, mode = info
        rgb = np.empty((h, w, 3), np.uint8)
        r = rgb_fn(buf.ctypes.data_as(P8), len(buf), rgb.ctypes.data_as(P8))
        if r == -1:
            raise MemoryError("the C reader")
        return (rgb, PIL_MODES[mode]) if r == 0 else None

    def size(source):
        data = _bytes(source)
        if data is None:
            return None
        buf, info, _rgb_fn = _info(data)
        return None if buf is None else (info[0], info[1])
    read.size = size
    return read