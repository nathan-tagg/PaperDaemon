r"""The C stroke store's Python face (fastdecomp/store.c). While the model runs (rm_model.run, stage "store"), the
painter's planner output stays in C: rmb_geometry.fill hands back Blocks (runs of store strokes) instead of tuples,
the end of the painter (wash grouping, extent) runs in C, the seam and the pass read the store, and Python stroke tuples
are made once -- for what the pass keeps -- with the reference's own scalar types: numpy.float32 points for a
simplified loop, numpy.float64 otherwise, Python int width fields, the style objects the Python would have used.

Strokes the painter makes in Python (the hatch, the contour lines) are copied into the store with every coordinate's
type recorded; they reach the output as the very objects the painter made (the pass never changes a pen stroke). The
same strokes made in C (fastdecomp/inkpass.c) carry Python-float points and come out as tuples of Python floats; the
wash styles the C registers are read back (sync_styles) so their tool, pen color and rgba objects exist here too.
Anything outside the types the store models (a coordinate that is not a float32, float64, float or int; a width that
is not a float or int) raises instead of differing.
"""
import ctypes
from itertools import chain as _chain

import numpy as np

_KIND = {np.float32: 1, np.float64: 2, float: 0, int: 0}     # rmfast.h RF_KIND_*
_P8, _P32, _PD = ctypes.POINTER(ctypes.c_uint8), ctypes.POINTER(ctypes.c_int32), ctypes.POINTER(ctypes.c_double)


class _FillJob(ctypes.Structure):
    _fields_ = [("mask", _P8), ("h", ctypes.c_int32), ("w", ctypes.c_int32), ("offx", ctypes.c_int32), ("offy", ctypes.c_int32),
                ("flat", ctypes.c_int32), ("max_page", ctypes.c_double), ("st_wash", ctypes.c_int32), ("st_fine", ctypes.c_int32),
                ("st_marker", ctypes.c_int32)]


def _setup(L, Result):
    if getattr(L, "_store_ready", False):
        return
    vp = ctypes.c_void_p
    L.rf_store_new.restype = vp
    L.rf_store_free.argtypes = [vp]
    L.rf_store_style.restype = ctypes.c_int32
    L.rf_store_style.argtypes = [vp] + [ctypes.c_int32] * 7
    L.rf_store_count.restype = ctypes.c_int32
    L.rf_store_count.argtypes = [vp]
    L.rf_store_arrays.argtypes = [vp, ctypes.POINTER(_P32), ctypes.POINTER(_P32), ctypes.POINTER(_P32)]
    L.rf_store_fill.restype = ctypes.c_int32
    L.rf_store_fill.argtypes = [vp, _P8, ctypes.c_int32, ctypes.c_int32, ctypes.c_double, ctypes.c_int32, ctypes.c_double,
                                ctypes.c_double, ctypes.c_double, ctypes.c_double, ctypes.c_double, ctypes.c_int32, ctypes.c_int32,
                                ctypes.c_int32, ctypes.c_int32, ctypes.c_double, ctypes.c_double, ctypes.c_double,
                                ctypes.c_int32, ctypes.c_int32, ctypes.c_int32]
    L.rf_store_fill_batch.restype = ctypes.c_int32
    L.rf_store_fill_batch.argtypes = [vp, ctypes.POINTER(_FillJob), ctypes.c_int32, ctypes.c_double, ctypes.c_double, ctypes.c_double,
                                      ctypes.c_double, ctypes.c_double, ctypes.c_int32, ctypes.c_int32, ctypes.c_double, ctypes.c_double,
                                      ctypes.c_double, _P32]
    L.rf_store_add.restype = ctypes.c_int32
    L.rf_store_add.argtypes = [vp, ctypes.c_int32, _P32, _PD, _PD, _P8, _P32, _P32]
    L.rf_store_wash_first.restype = ctypes.c_int32
    L.rf_store_wash_first.argtypes = [vp, _P32, ctypes.c_int32, ctypes.c_int32, _P32]
    L.rf_store_extent.restype = ctypes.c_int32
    L.rf_store_extent.argtypes = [vp, _P32, ctypes.c_int32, ctypes.c_int32, ctypes.c_double, ctypes.c_double, _PD, _P8]
    L.rf_store_select.restype = ctypes.c_int32
    L.rf_store_select.argtypes = [vp, _P32, ctypes.c_int32, ctypes.c_int32, _P32]
    L.rf_store_seam.restype = ctypes.c_int32
    L.rf_store_seam.argtypes = [vp, _P32, ctypes.c_int32, _P32, ctypes.c_int32, ctypes.c_double, ctypes.c_double,
                                ctypes.c_int32, ctypes.c_int32, ctypes.c_double, ctypes.POINTER(_P32)]
    L.rf_store_style_rgb.restype = ctypes.c_int32
    L.rf_store_style_rgb.argtypes = [vp] + [ctypes.c_int32] * 6
    L.rf_store_styles.restype = ctypes.c_int32
    L.rf_store_styles.argtypes = [vp, ctypes.c_int32, _P32]
    L.rf_store_style_count.restype = ctypes.c_int32
    L.rf_store_style_count.argtypes = [vp]
    L.rf_store_prune_join.restype = ctypes.c_int32
    L.rf_store_prune_join.argtypes = [vp, _P32, ctypes.c_int32, ctypes.c_double, ctypes.c_double, ctypes.c_double, ctypes.c_int32,
                                      ctypes.POINTER(Result)]
    L._store_ready = True


def _i32(a):
    return a.ctypes.data_as(_P32)


class Block:
    """Strokes start .. start + n - 1 of the store: one planner call's output, standing in the painter's `out` list."""
    __slots__ = ("start", "n")

    def __init__(self, start, n):
        self.start, self.n = start, n


class Strokes:
    """The painter's strokes while they stay in C: store indices in draw order."""
    __slots__ = ("session", "order")

    def __init__(self, session, order):
        self.session, self.order = session, np.ascontiguousarray(order, np.int32)

    def __len__(self):
        return len(self.order)


def _scalar(v, k):
    return np.float32(v) if k == 1 else (np.float64(v) if k == 2 else float(v))


class Session:
    """One model run's store (both painter runs share it). close() frees it."""

    def __init__(self, rmfast):
        self.rmfast = rmfast
        self.L = rmfast.lib()
        _setup(self.L, rmfast._Result)
        self.S = self.L.rf_store_new()
        if not self.S:
            raise MemoryError("rf_store_new")
        self.styles, self._style_ids, self.py = [], {}, []
        self._deferred = None           # fill jobs waiting for the batch (defer())

    def close(self):
        if self.S:
            self.L.rf_store_free(self.S)
            self.S = None

    def count(self):
        return int(self.L.rf_store_count(self.S))

    def style(self, tool, color, rgba):
        """The style id of (tool, pen color, rgba), registered on first use. The C side gets what Packed computed:
        the wash flag (rm_lean.is_wash), rgb (255, 237, 117 for no rgba), and the key of tuple(rgba) that the painter
        groups washes by (numbered in C, store.c rf_store_style_rgb, for the styles registered here and there alike).
        An rgba other than None or a tuple of three Python ints 0..255 raises instead of differing."""
        key = (type(tool), tool, type(color), color, type(rgba), None if rgba is None else tuple(rgba))
        sid = self._style_ids.get(key)
        if sid is None:
            wash = 1 if tool.name.startswith("HIGHLIGHTER") else 0
            if rgba is None:
                sid = self.L.rf_store_style(self.S, int(tool), int(color), 255, 237, 117, wash, -1)
            else:
                rgb = tuple(rgba)
                if type(rgba) is not tuple or len(rgb) != 3 or any(type(v) is not int or not 0 <= v <= 255 for v in rgb):
                    raise NotImplementedError("an rgba the store does not model: %r" % (rgba,))
                sid = self.L.rf_store_style_rgb(self.S, int(tool), int(color), rgb[0], rgb[1], rgb[2], wash)
            if sid < 0:
                raise MemoryError("rf_store_style")
            if sid == len(self.styles):
                self.styles.append((tool, color, rgba))
            self._style_ids[key] = sid
        return sid

    def sync_styles(self, api):
        """The styles the C registered since the last call (rf_store_style_rgb from inkpass.c): their tool and pen
        color objects and their rgba as a tuple of Python ints, as the painter's own tuples hold them."""
        first = len(self.styles)
        n = int(self.L.rf_store_style_count(self.S)) - first
        if n <= 0:
            return
        info = np.empty(7 * n, np.int32)
        if self.L.rf_store_styles(self.S, first, _i32(info)) != n:
            raise ValueError("rf_store_styles")
        v = info.tolist()
        for k in range(n):
            tool, color = api.Pen(v[7 * k]), api.PenColor(v[7 * k + 1])
            rgba = (v[7 * k + 2], v[7 * k + 3], v[7 * k + 4]) if v[7 * k + 5] else None
            self.styles.append((tool, color, rgba))
            self._style_ids[(type(tool), tool, type(color), color, type(rgba), rgba)] = first + k

    def _styles_for(self, color, flat, api):
        if flat:
            return self.style(api.Pen.HIGHLIGHTER_2, api.PenColor.HIGHLIGHT, color), -1, -1
        return -1, self.style(api.Pen.FINELINER_2, color, None), self.style(api.Pen.MARKER_2, color, None)

    def defer(self):
        """From now until finish(), fill() records its job (a copy of the mask: the painter may change the mask after
        the call) and hands back a Block that finish() fills in: the jobs are then planned as batches on all threads
        (fill_batch itself still runs at once). The painter only ever extends its `out` list with
        a fill's result, so `out` holds the same runs of the same strokes in the same order; a job that plans nothing
        leaves an empty Block, which adds nothing, as the [] it stands for."""
        self._deferred = []

    def _flush(self):
        jobs, self._deferred = self._deferred, None
        if not jobs:
            return
        k = 0
        while k < len(jobs):                       # consecutive jobs on the same page frame go as one batch
            e = k
            while e < len(jobs) and jobs[e][0] == jobs[k][0]:
                e += 1
            (ppg, box, grid), api = jobs[k][0], jobs[k][6]
            res = self._batch([(j[1], j[2], j[3], j[4]) for j in jobs[k:e]], ppg, box, grid, api)
            for j, r in zip(jobs[k:e], res):
                if r:
                    j[5].start, j[5].n = r[0].start, r[0].n
                else:
                    j[5].start, j[5].n = 0, 0
            k = e

    def fill(self, mask, color, ppg, box, offset, grid, flat, api):
        """rmb_geometry.fill into the store (rm_model sets this as rmb_geometry.FAST for the run) -> [Block] or []."""
        if self._deferred is not None:
            a = np.array(self.rmfast._view(mask), dtype=np.uint8, order="C", copy=True)
            gw, gh = grid if grid else (mask.size[0], mask.size[1])
            blk = Block(0, 0)
            self._deferred.append(((float(ppg), tuple(float(v) for v in box), (int(gw), int(gh))), a, color,
                                   (int(offset[0]), int(offset[1])), bool(flat), blk, api))
            return [blk]
        a = np.ascontiguousarray(self.rmfast._view(mask), dtype=np.uint8)
        h, w = a.shape
        gw, gh = grid if grid else (mask.size[0], mask.size[1])
        x0, y0, x1, y1 = box
        max_page = api.K.HL_WIDTHS_PAGE[0] if flat else api.K.MARKER_WIDTHS_PAGE[0]
        sw, sf, sm = self._styles_for(color, flat, api)
        start = self.count()
        n = self.L.rf_store_fill(self.S, a.ctypes.data_as(_P8), h, w, float(ppg), 1 if flat else 0, float(max_page),
                                 float(x0), float(y0), float(x1), float(y1), int(offset[0]), int(offset[1]), int(gw), int(gh),
                                 float(api.HL_SCALE), float(api._W), float(api.K.FINELINER_MAX_PAGE), sw, sf, sm)
        if n < 0:
            raise MemoryError("rf_store_fill")
        return [Block(start, n)] if n else []

    def fill_batch(self, jobs, ppg, box, grid, api):
        """Several rmb_geometry.fill calls at once, planned on all threads: jobs = [(mask, color, offset, flat), ...]
        -> one result per job ([Block] or []), the same strokes in the same order as calling fill for each in turn."""
        if not jobs:
            return []
        return self._batch([(np.ascontiguousarray(self.rmfast._view(mask), dtype=np.uint8), color, offset, flat)
                            for mask, color, offset, flat in jobs], ppg, box, grid, api)

    def _batch(self, jobs, ppg, box, grid, api):
        """fill_batch on (uint8 array, color, offset, flat) jobs."""
        arrs, cj = [], (_FillJob * len(jobs))()
        for k, (a, color, offset, flat) in enumerate(jobs):
            arrs.append(a)
            sw, sf, sm = self._styles_for(color, flat, api)
            cj[k] = _FillJob(a.ctypes.data_as(_P8), a.shape[0], a.shape[1], int(offset[0]), int(offset[1]), 1 if flat else 0,
                             float(api.K.HL_WIDTHS_PAGE[0] if flat else api.K.MARKER_WIDTHS_PAGE[0]), sw, sf, sm)
        made = np.zeros(len(jobs), np.int32)
        gw, gh = grid
        x0, y0, x1, y1 = box
        start = self.count()
        n = self.L.rf_store_fill_batch(self.S, cj, len(jobs), float(ppg), float(x0), float(y0), float(x1), float(y1), int(gw), int(gh),
                                       float(api.HL_SCALE), float(api._W), float(api.K.FINELINER_MAX_PAGE), _i32(made))
        if n < 0:
            raise MemoryError("rf_store_fill_batch")
        out = []
        for m in made.tolist():
            out.append([Block(start, m)] if m else [])
            start += m
        return out

    def _add_py(self, strokes):
        """Copy strokes made in Python into the store, every coordinate's type recorded; they keep their objects."""
        counts, kinds, styles, refs = [], [], [], []
        for s in strokes:
            pts, wid = s[0], s[1]
            if len(pts) != len(wid) or any(len(p) != 2 for p in pts):
                raise NotImplementedError("a stroke whose points and widths do not pair up")
            ts = set(map(type, _chain.from_iterable(pts)))
            if not ts <= _KIND.keys() or not set(map(type, wid)) <= {int, float}:
                raise NotImplementedError("stroke scalars of types the store does not model: %s" % sorted(t.__name__ for t in ts))
            if len(ts) == 1:
                kinds.append(np.full(2 * len(pts), _KIND[next(iter(ts))], np.uint8))
            else:
                kinds.append(np.fromiter((_KIND[type(v)] for v in _chain.from_iterable(pts)), np.uint8, count=2 * len(pts)))
            counts.append(len(pts))
            styles.append(self.style(s[2], s[3], s[4]))
            refs.append(len(self.py))
            self.py.append(s)
        total = sum(counts)
        xy = np.fromiter(_chain.from_iterable(_chain.from_iterable(s[0] for s in strokes)), np.float64, count=2 * total)
        w = np.fromiter(_chain.from_iterable(s[1] for s in strokes), np.float64, count=total)
        kd = np.concatenate(kinds) if kinds else np.zeros(0, np.uint8)
        c, st, rf = np.array(counts, np.int32), np.array(styles, np.int32), np.array(refs, np.int32)
        if self.L.rf_store_add(self.S, len(strokes), _i32(c), xy.ctypes.data_as(_PD), w.ctypes.data_as(_PD), kd.ctypes.data_as(_P8),
                               _i32(st), _i32(rf)) < 0:
            raise MemoryError("rf_store_add")

    def finish(self, out, hl_tool, hl_scale, w_scale):
        """The end of rm_paint.decompose (SUBCELL_GEOMETRY) on `out` (Blocks and Python tuples): washes grouped by rgba
        first, then the pens; and the extent. -> (Strokes, extent or None when out is empty)."""
        self._flush()
        idx, pys = [], []
        base = self.count()
        for item in out:
            if type(item) is Block:
                idx.extend(range(item.start, item.start + item.n))
            else:
                idx.append(base + len(pys))
                pys.append(item)
        if pys:
            self._add_py(pys)
        order = np.array(idx, np.int32)
        n = len(order)
        res = np.empty(n, np.int32)
        rc = self.L.rf_store_wash_first(self.S, _i32(order), n, int(hl_tool), _i32(res))
        if rc == -2:
            raise TypeError("'NoneType' object is not iterable")      # tuple(None): a wash without rgba, as the Python fails
        if rc < 0:
            raise MemoryError("rf_store_wash_first")
        extent = None
        if out:
            val, kind = (ctypes.c_double * 4)(), (ctypes.c_uint8 * 4)()
            if not self.L.rf_store_extent(self.S, _i32(res), n, int(hl_tool), float(hl_scale), float(w_scale), val, kind):
                raise ValueError("min() iterable argument is empty")
            extent = [round(_scalar(val[i], kind[i]), 1) for i in range(4)]
        return Strokes(self, res), extent

    def select(self, strokes, wash):
        """[s for s in strokes if rm_lean.is_wash(s) == wash]"""
        o = strokes.order
        res = np.empty(len(o), np.int32)
        k = self.L.rf_store_select(self.S, _i32(o), len(o), 1 if wash else 0, _i32(res))
        return Strokes(self, res[:k])

    def seam(self, washes_m, rest, base, frame, wash_eps):
        """rmfast.seam on the store -> (washes_m + the base washes that came back + rest, how many came back)."""
        fx0, fy0, fx1, fy1 = frame
        W, H = int(round(fx1 - fx0)), int(round(fy1 - fy0))
        add = _P32()
        n = self.L.rf_store_seam(self.S, _i32(base.order), len(base.order), _i32(washes_m.order), len(washes_m.order),
                                 float(fx0), float(fy0), W, H, float(wash_eps), ctypes.byref(add))
        try:
            if n < 0:
                raise MemoryError("rf_store_seam")
            got = np.ctypeslib.as_array(add, shape=(n,)).copy() if n > 0 else np.zeros(0, np.int32)
        finally:
            if add:
                self.L.rf_free(add)
        return Strokes(self, np.concatenate([washes_m.order, got.astype(np.int32), rest.order])), int(n)

    def prune_join(self, strokes, radius=6.0, max_points=4000, eps_out=None, radius_w=0.0):
        """rmfast.prune_join on the store -> (Python strokes, {"pruned", "joins"})."""
        o = strokes.order
        if not len(o):
            return [], {"pruned": 0, "joins": 0}
        res = self.rmfast._Result()
        rc = self.L.rf_store_prune_join(self.S, _i32(o), len(o), -1.0 if eps_out is None else float(eps_out), float(radius),
                                        float(radius_w), int(max_points), ctypes.byref(res))
        if rc != 0:
            raise MemoryError("rf_store_prune_join")
        try:
            return self._materialize(res), {"pruned": int(res.pruned), "joins": int(res.joins)}
        finally:
            self.L.rf_result_free(ctypes.byref(res))

    def _materialize(self, res):
        """The pass's output as the Python's tuples: a stroke made in Python and kept whole is that object; every other
        stroke is built from the C arrays with each coordinate's recorded type and Python int width fields."""
        n = res.n
        if not n:
            return []
        counts = np.ctypeslib.as_array(res.counts, shape=(n,)).copy()
        src = np.ctypeslib.as_array(res.src, shape=(n,)).copy()
        total = int(counts.sum())
        xy = np.ctypeslib.as_array(res.xy, shape=(2 * total,)).copy() if total else np.zeros(0)
        w = np.ctypeslib.as_array(res.w, shape=(total,)).copy() if total else np.zeros(0)
        pk = np.ctypeslib.as_array(res.pkind, shape=(2 * total,)).copy() if total else np.zeros(0, np.uint8)
        cnt_p, sty_p, ref_p = _P32(), _P32(), _P32()
        self.L.rf_store_arrays(self.S, ctypes.byref(cnt_p), ctypes.byref(sty_p), ctypes.byref(ref_p))
        m = self.count()
        cnt_s = np.ctypeslib.as_array(cnt_p, shape=(m,))
        sty_s = np.ctypeslib.as_array(sty_p, shape=(m,)).copy()
        ref_s = np.ctypeslib.as_array(ref_p, shape=(m,)).copy()
        keep_py = (ref_s[src] >= 0) & (counts == cnt_s[src])
        if (ref_s[src[~keep_py]] >= 0).any():
            raise NotImplementedError("the pass changed a stroke made in Python")
        built = np.repeat(~keep_py, counts)
        kx, ky = pk[0::2], pk[1::2]
        if (built & (kx != ky)).any():
            raise NotImplementedError("a point whose x and y are of different kinds")
        x, y = xy[0::2], xy[1::2]
        objs = np.empty(total, dtype=object)
        for code, dt in ((1, np.float32), (2, np.float64)):
            sel = built & (kx == code)
            c = int(np.count_nonzero(sel))
            if c:
                objs[sel] = np.fromiter(zip(x[sel].astype(dt), y[sel].astype(dt)), dtype=object, count=c)
        sel = built & (kx == 0)                         # Python floats (strokes the C made where the Python makes them)
        if (sel & ~np.repeat(counts == cnt_s[src], counts)).any():
            raise NotImplementedError("the pass changed a stroke of Python-float points")
        c = int(np.count_nonzero(sel))
        if c:
            objs[sel] = np.fromiter(zip(x[sel].tolist(), y[sel].tolist()), dtype=object, count=c)
        wi = w.astype(np.int64)
        if (built & (wi != w)).any():
            raise NotImplementedError("a planner width that is not a whole field")
        olist, wlist = objs.tolist(), wi.tolist()
        styles, py = self.styles, self.py
        out, k = [], 0
        for c, s, keep in zip(counts.tolist(), src.tolist(), keep_py.tolist()):
            if keep:
                out.append(py[int(ref_s[s])])
            else:
                tool, color, rgba = styles[int(sty_s[s])]
                out.append((olist[k:k + c], wlist[k:k + c], tool, color, rgba))
            k += c
        return out
