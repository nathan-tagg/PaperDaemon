r"""The twin of rm_paint.decompose, with its slowest loops in C (fastdecomp/pockets.c) or done once instead of per
component. rm_paint.py stays the untouched Python reference; rm_model.run calls this twin when the "engine" stage is
on (RM_FAST_STAGES), and RM_FAST=0 still runs the reference.

THE TWIN RUNS IN rm_paint's OWN NAMESPACE. Its code is compiled here and bound to rm_paint's globals (twin()), so every
helper, constant and per-picture module state (_UP, _SKIN_HUE_OFFSET, _DARK_FIELD, _FLOW, _WHITE_FLOOR) it reads or
sets is rm_paint's own, exactly as the reference's are, and any painter function rm_model swaps in for the run (the
other C stages) is the one it calls. The body is the reference's line for line except where marked "TWIN:":

  * the pocket loop (paper or tone enclosed by color takes the color owning most of its ring) is rf_pockets: the same
    components in the same order, the same k x k ring, the same first-maximum rule, the same sequential writes;
  * the light-tone pocket scan before it (enclosure, light tone, the half-area test, the color sums) is
    rf_tone_pockets; each passing pocket's color key is still the reference's code;
  * the full-grid `masks["black"] != 0` that the ink-core test rebuilt for every dark piece is built once (masks is
    not changed inside that loop);
  * the unions of many masks (ImageChops.lighter one mask at a time) are one numpy maximum over the same masks: the
    pixel-wise maximum is the same whatever the grouping;
  * rmb_resolution.tonal_ink is Fast.tonal_ink, in C (fastdecomp/tonal.c): the protected pixels, their ladder palette
    and every mask rebuilt in the reference's key order;
  * the gap densities (each class's anchor and its BoxBlur) and the two Gaussian blurs are Pillow's filters in C
    (fastdecomp/blur.c);
  * with a store session (rm_model's "store" stage): every color zone's fill is one batch planned on all cores, the
    painter's last lines (wash grouping, extent) run on the C stroke store and the strokes leave as store indices
    (fastdecomp/store.c, rmstore.py); the flow field is reduced to its coherence, the only part anything reads, and
    computed only when the caller asks for the report (fastdecomp/flow.c); the ridge (XDoG, its darkest share, Zhang-Suen) is fastdecomp/xdog.c.
  * the black pass's ink density, its covered grid (the union of the color masks) and its covered-speck test (for every component
    at once, from the components' own C arrays) run in C (fastdecomp/specks.c);
  * with a store session, every single fill after the zones' batch is recorded and planned in batches on all cores
    when the strokes are finished (rmstore.Session.defer); the source may arrive as the PIL RGB picture rm_model read
    (fastdecomp/decode.c) or recolored, instead of a file;
  * the hatch's bands and lines (fastdecomp/cel.c, hatch.c) and the contour pass's centerlines (fastdecomp/skel.c) are
    C, each with the reference's function as its fallback;
  * with a store session, everything from the quantized masks to the last stroke is one C call (fastdecomp/painter.c
    rf_painter_body: the pockets, the gap close, the painterly share, tonal_ink, coarsen_washes, the absorber, the gray
    halo, the zones' batch, then fastdecomp/inkpass.c for the ink section and the contour pass), the report values set in
    the reference's order (Fast.body_report); outside the case they reproduce, the reference's lines run (and the ink
    section alone may still be C: Fast.ink_pass). rm_model's single call (fastdecomp/model.c) runs this body without the
    twin.


Proven identical call by call on real painter runs and end to end on a reference corpus.
"""
import ctypes
import types

import numpy as np

_CODE = None

_INK_FIELDS = ([(n, ctypes.c_double) for n in ("ppg", "x0", "y0", "x1", "y1", "detail", "shade", "up")]
               + [(n, ctypes.c_int32) for n in ("tone", "painterly", "tone_region_wash", "shadow_hatch", "ink_speck_on_color",
                                                 "hatch_under_wash", "outline", "line_smooth", "cel_median", "tool_hl", "color_hl",
                                                 "st_fine", "st_marker", "st_tone", "st_outline")]
               + [("draw_min_area", ctypes.c_int64)]
               + [(n, ctypes.c_double) for n in (
                   "draw_min_page", "min_span_g", "min_len_page", "tone_region_open",
                   "shadow_edge_blur", "shadow_min_border", "shadow_l_step", "shadow_min_chroma", "shadow_hue_tol", "shadow_max_edge",
                   "shadow_min_internal_grad", "shadow_l_pct",
                   "ink_speck_covered", "ink_core_min", "absorb_max_area", "ink_density_cell_page", "black_mass_thick_paint",
                   "black_mass_thick_page", "ink_line_min_len_page", "ink_line_max_density",
                   "paper_l", "tone_line_l", "gray_field_cover", "gray_line_max_page", "gray_drop_g",
                   "cel_min_area", "tone_pitch_page", "tone_width_page", "cel_lo", "cel_hi", "cel_blur", "hatch_cross_at", "cel_speck_area",
                   "cel_field_cover", "hatch_under_min_g", "hatch_angle", "hatch_angle_2", "hatch_pitch_mul",
                   "outline_clear_g", "outline_min_len_page", "outline_width_page",
                   "hl_width_max", "marker_width_max", "hl_scale", "pen_scale", "fineliner_max")])


class _InkParams(ctypes.Structure):
    """rmfast.h rf_ink_params, field for field."""
    _fields_ = _INK_FIELDS


_HEAD_FIELDS = ([(n, ctypes.c_double) for n in ("pocket_l", "gap_close_g", "gap_close_page", "paper_l", "ink_l", "hl_min_page", "chroma_min",
                                                 "painterly_chroma_share", "black_l", "black_mass_thick_paint", "fill_hole_page",
                                                 "absorb_max_de", "gray_halo_open", "gray_halo_share", "tc_ink_l")]
                + [("tc_quant", ctypes.c_int32), ("absorb_max_area", ctypes.c_int32)])


class _HeadParams(ctypes.Structure):
    """rmfast.h rf_head_params, field for field."""
    _fields_ = _HEAD_FIELDS


def _struct(cls, fields, c):
    """cls(**c) with every float field a float and every integer field an int, or None when an integer field's value
    is not a whole number."""
    if any(t is not ctypes.c_double and int(c[k]) != c[k] for k, t in fields):
        return None
    return cls(**{k: (float(c[k]) if t is ctypes.c_double else int(c[k])) for k, t in fields})


def _union(N, Image, size, ims):
    """ImageChops.lighter folded over `ims` from a blank (size) image, as one maximum."""
    acc = np.zeros((size[1], size[0]), np.uint8)
    for im in ims:
        np.maximum(acc, N.view(im), out=acc)
    return N.img(acc)


class Fast:
    """What the twin calls instead of the reference's loops."""

    def __init__(self, rmfast, N, Image, session=None, report=True):
        self.session = session          # fastdecomp/rmstore.Session: the planner's strokes stay in C (stage "store")
        self.report = report            # False: values only the report reads (no stroke depends on them) are skipped
        L = rmfast.lib()
        L.rf_pockets.restype = ctypes.c_int32
        L.rf_pockets.argtypes = [ctypes.POINTER(ctypes.c_uint8), ctypes.c_int32, ctypes.c_int32, ctypes.c_int32,
                                 ctypes.c_int32, ctypes.POINTER(ctypes.POINTER(ctypes.c_uint8))]
        P8, P64 = ctypes.POINTER(ctypes.c_uint8), ctypes.POINTER(ctypes.c_int64)
        L.rf_tone_pockets.restype = ctypes.c_int32
        L.rf_tone_pockets.argtypes = [P8, ctypes.c_int32, ctypes.c_int32, P8, P8, P8, ctypes.c_double,
                                      ctypes.POINTER(P64), ctypes.POINTER(P64)]
        L.rf_box_blur.restype = ctypes.c_int32
        L.rf_box_blur.argtypes = [P8, P8, ctypes.c_int32, ctypes.c_int32, ctypes.c_int32, ctypes.c_float, ctypes.c_int32]
        L.rf_xdog_ridge.restype = ctypes.c_int32
        L.rf_xdog_ridge.argtypes = [P8, ctypes.c_int32, ctypes.c_int32, ctypes.c_float, ctypes.c_float, ctypes.c_double, ctypes.c_double, P8,
                                    ctypes.POINTER(ctypes.c_int64)]
        L.rf_flow_coherence.restype = ctypes.c_int32
        L.rf_flow_coherence.argtypes = [P8, ctypes.c_int32, ctypes.c_int32, ctypes.POINTER(ctypes.c_double), ctypes.c_int32,
                                        ctypes.POINTER(ctypes.c_double), ctypes.c_int32, ctypes.c_double, ctypes.POINTER(ctypes.c_int64)]
        L.rf_tonal_protect.restype = ctypes.c_int64
        L.rf_tonal_protect.argtypes = [P8, P8, ctypes.c_int32, ctypes.c_int32, ctypes.c_double, ctypes.c_double, P8, P8,
                                       ctypes.POINTER(ctypes.c_int32), ctypes.POINTER(ctypes.c_int32), ctypes.POINTER(ctypes.c_int32)]
        L.rf_tonal_apply.restype = None
        L.rf_tonal_apply.argtypes = [ctypes.POINTER(P8), ctypes.c_int32, ctypes.POINTER(P8), ctypes.c_int32, P8,
                                     ctypes.POINTER(ctypes.c_int32), ctypes.POINTER(ctypes.c_int32), ctypes.c_int32, ctypes.c_int32]
        L.rf_gap_density.restype = ctypes.c_int32
        L.rf_gap_density.argtypes = [ctypes.POINTER(P8), ctypes.c_int32, ctypes.c_int32, ctypes.c_int32, ctypes.c_int32, ctypes.c_float,
                                     ctypes.POINTER(P8), P8]
        L.rf_any_nonzero.restype = None
        L.rf_any_nonzero.argtypes = [ctypes.POINTER(P8), ctypes.c_int32, ctypes.c_int32, ctypes.c_int32, P8]
        L.rf_speck_skip.restype = None
        L.rf_speck_skip.argtypes = [P64, P8, ctypes.c_int32, P8, ctypes.c_int32, ctypes.c_int32, ctypes.c_int64, ctypes.c_double, P8]
        L.rf_cel_regions.restype = ctypes.c_int32
        L.rf_cel_regions.argtypes = [P8, P8, ctypes.c_int32, ctypes.c_int32, ctypes.c_float, ctypes.POINTER(ctypes.c_double), ctypes.c_int32,
                                     ctypes.c_int32, ctypes.c_double, ctypes.c_double, ctypes.c_int64, ctypes.POINTER(P8)]
        L.rf_skeleton_thin.restype = ctypes.c_int32
        L.rf_skeleton_thin.argtypes = [P8, ctypes.c_int32, ctypes.c_int32, ctypes.c_double, ctypes.c_double, ctypes.c_int32,
                                       ctypes.POINTER(ctypes.POINTER(ctypes.c_double)), ctypes.POINTER(ctypes.POINTER(ctypes.c_int32)),
                                       ctypes.POINTER(ctypes.POINTER(ctypes.c_double)), ctypes.POINTER(ctypes.c_double), ctypes.POINTER(ctypes.c_int32)]
        L.rf_uniform_hatch.restype = ctypes.c_int64
        L.rf_uniform_hatch.argtypes = [P8, ctypes.c_int32, ctypes.c_int32, ctypes.POINTER(ctypes.c_double), ctypes.c_int32, ctypes.c_double,
                                       ctypes.c_double, ctypes.POINTER(ctypes.POINTER(ctypes.c_double))]
        L.rf_ink_density.restype = ctypes.c_int32
        L.rf_ink_density.argtypes = [P8, P8, ctypes.c_int32, ctypes.c_int32, ctypes.c_double, ctypes.c_double, ctypes.c_double, ctypes.c_double,
                                     ctypes.c_int32, ctypes.c_int32, ctypes.POINTER(ctypes.c_double)]
        L.rf_gap_assign.restype = ctypes.c_int64
        L.rf_gap_assign.argtypes = [ctypes.POINTER(P8), ctypes.c_int32, ctypes.c_int32, ctypes.c_int32, P8, P8, P8, ctypes.c_int32,
                                    ctypes.c_int32, ctypes.POINTER(ctypes.c_double), ctypes.POINTER(P8), P8]
        L.rf_gray_halo.restype = ctypes.c_int64
        L.rf_gray_halo.argtypes = [ctypes.POINTER(P8), ctypes.c_int32, ctypes.c_int32, ctypes.c_int32, P8, ctypes.c_double,
                                   ctypes.POINTER(P8)]
        L.rf_gray_sides.restype = ctypes.c_int32
        L.rf_gray_sides.argtypes = [P64, ctypes.c_int32, P8, ctypes.c_int32, ctypes.c_int32, ctypes.c_int64, ctypes.c_double, P8]
        PD = ctypes.POINTER(ctypes.c_double)
        L.rf_black_pieces.restype = ctypes.c_int32
        L.rf_black_pieces.argtypes = [P64, P8, ctypes.c_int32, P8, P8, P8, ctypes.c_int32, ctypes.c_int32, ctypes.c_double, ctypes.c_double, PD,
                                      ctypes.c_int32, ctypes.c_int32, ctypes.c_double, ctypes.c_double, ctypes.c_double, ctypes.c_double,
                                      ctypes.POINTER(ctypes.c_int8), ctypes.POINTER(ctypes.c_int32)]
        L.rf_painter_body.restype = ctypes.c_int32
        L.rf_painter_body.argtypes = [ctypes.c_void_p, ctypes.POINTER(_InkParams), ctypes.POINTER(_HeadParams), ctypes.c_int32, ctypes.c_int32,
                                     ctypes.c_int32, ctypes.POINTER(ctypes.c_int32), ctypes.POINTER(ctypes.c_int32), ctypes.POINTER(P8), P8, P8, P8,
                                     ctypes.POINTER(ctypes.POINTER(ctypes.c_int32)), ctypes.POINTER(ctypes.c_int32),
                                     ctypes.POINTER(ctypes.POINTER(ctypes.c_int32)), ctypes.POINTER(ctypes.c_int32), PD]
        L.rf_ink_pass.restype = ctypes.c_int32
        L.rf_ink_pass.argtypes = [ctypes.c_void_p, ctypes.POINTER(_InkParams), ctypes.c_int32, ctypes.c_int32, P8, P8, P8, ctypes.POINTER(P8),
                                  ctypes.c_int32, P8, P8, P8, ctypes.POINTER(ctypes.POINTER(ctypes.c_int32)), ctypes.POINTER(ctypes.c_int32), PD]
        self._L, self._N, self._Image = L, N, Image

    def ink_pass(self, masks, small, lumimg, ridge, ppg, box, detail, shade, tone, painterly, flow, size, api):
        """The painter's ink section and contour pass in one C call (fastdecomp/inkpass.c rf_ink_pass), its fills and pen
        strokes into the store -> (the Blocks standing for them in the painter's `out` order, the report), or None outside
        the painter's case (the twin's Python lines run): a store session, SUBCELL_GEOMETRY and INK_AS_FILL on, no flow
        hatch, no backstop, black hatch, the contour pass on the ink ridge without soft edges, masks at the grid size."""
        S = self.session
        if not self._ink_case(api, flow) or "_ink" not in masks:
            return None
        W, H = size
        N = self._N
        P8 = ctypes.POINTER(ctypes.c_uint8)

        def grid(m):
            a = np.ascontiguousarray(N.view(m), dtype=np.uint8)
            return a if a.shape == (H, W) else None
        ckeys = [k for k in masks if k not in ("black", "tone", "_ink")]
        black, tone_m, ink = (grid(masks[k]) if k in masks else None for k in ("black", "tone", "_ink"))
        cols = [grid(masks[k]) for k in ckeys]
        rgb = np.ascontiguousarray(np.asarray(small, np.uint8))
        lum = np.ascontiguousarray(np.asarray(lumimg, np.uint8))
        rid = np.ascontiguousarray(ridge, dtype=np.uint8)
        if (ink is None or ("black" in masks and black is None) or ("tone" in masks and tone_m is None) or any(c is None for c in cols)
                or rgb.shape != (H, W, 3) or lum.shape != (H, W) or rid.shape != (H, W)):
            return None
        prm = self._ink_params(api, ppg, box, detail, shade, tone, painterly)
        if prm is None:
            return None
        col_p = (P8 * max(1, len(cols)))(*[a.ctypes.data_as(P8) for a in cols])
        rep = (ctypes.c_double * 24)()
        order, n = ctypes.POINTER(ctypes.c_int32)(), ctypes.c_int32()
        rc = self._L.rf_ink_pass(S.S, ctypes.byref(prm), int(H), int(W), None if black is None else black.ctypes.data_as(P8),
                                 None if tone_m is None else tone_m.ctypes.data_as(P8), ink.ctypes.data_as(P8), col_p, len(cols),
                                 rgb.ctypes.data_as(P8), lum.ctypes.data_as(P8), rid.ctypes.data_as(P8), ctypes.byref(order), ctypes.byref(n), rep)
        o = self._take_order(rc, order, n, "rf_ink_pass")
        if o is None:
            return None
        S.sync_styles(api)
        return self._blocks(o), list(rep)

    def _ink_case(self, api, flow):
        """Whether the painter runs the case inkpass.c reproduces: a store session, SUBCELL_GEOMETRY and INK_AS_FILL on, no
        flow hatch, no backstop, black hatch, the contour pass on the ink ridge without soft edges."""
        K = api.K
        return not (self.session is None or not K.SUBCELL_GEOMETRY or not K.INK_AS_FILL or flow is not None or K.FILL_BACKSTOP
                    or K.HATCH_IN_COLOR or api.OUTLINE_SOFT or api.OUTLINE_XDOG != api.XDOG_INK)

    def _take_order(self, rc, order, n, name):
        """The store indices an entry returned (freed here) -> a list, or None when it refused (-2)."""
        try:
            if rc == -2:
                return None
            if rc != 0:
                raise MemoryError(name)
            return np.ctypeslib.as_array(order, shape=(n.value,)).tolist() if n.value else []
        finally:
            if order:
                self._L.rf_free(order)

    @staticmethod
    def _blocks(o):
        """Runs of consecutive store indices as rmstore.Blocks."""
        import rmstore
        blocks, k = [], 0
        while k < len(o):
            e = k + 1
            while e < len(o) and o[e] == o[e - 1] + 1:
                e += 1
            blocks.append(rmstore.Block(o[k], e - k))
            k = e
        return blocks

    def _ink_params(self, api, ppg, box, detail, shade, tone, painterly):
        """rf_ink_params from the painter's constants and the picture's frame (the style ids registered in the store)."""
        K, S = api.K, self.session
        Pen, PenColor = api.Pen, api.PenColor
        c = dict(ppg=ppg, x0=box[0], y0=box[1], x1=box[2], y1=box[3], detail=detail, shade=shade, up=api._UP,
                 tone=1 if tone else 0, painterly=1 if painterly else 0,
                 tone_region_wash=1 if K.TONE_REGION_WASH else 0, shadow_hatch=1 if K.SHADOW_HATCH else 0,
                 ink_speck_on_color=1 if K.INK_SPECK_ON_COLOR else 0, hatch_under_wash=1 if K.HATCH_UNDER_WASH else 0,
                 outline=1 if api.OUTLINE else 0, line_smooth=1 if K.LINE_SMOOTH else 0, cel_median=api.CEL_MEDIAN,
                 tool_hl=int(Pen.HIGHLIGHTER_2), color_hl=int(PenColor.HIGHLIGHT),
                 st_fine=S.style(Pen.FINELINER_2, PenColor.BLACK, None), st_marker=S.style(Pen.MARKER_2, PenColor.BLACK, None),
                 st_tone=S.style(api.TONE_PEN, PenColor.BLACK, None), st_outline=S.style(Pen.FINELINER_2, PenColor.BLACK, None),
                 draw_min_area=K.DRAW_MIN_AREA, draw_min_page=K.DRAW_MIN_PAGE, min_span_g=api.MIN_SPAN_G, min_len_page=api.MIN_LEN_PAGE,
                 tone_region_open=K.TONE_REGION_OPEN, shadow_edge_blur=K.SHADOW_EDGE_BLUR, shadow_min_border=K.SHADOW_MIN_BORDER,
                 shadow_l_step=K.SHADOW_L_STEP, shadow_min_chroma=K.SHADOW_MIN_CHROMA, shadow_hue_tol=K.SHADOW_HUE_TOL,
                 shadow_max_edge=K.SHADOW_MAX_EDGE, shadow_min_internal_grad=K.SHADOW_MIN_INTERNAL_GRAD, shadow_l_pct=K.SHADOW_L_PCT,
                 ink_speck_covered=K.INK_SPECK_COVERED, ink_core_min=K.INK_CORE_MIN, absorb_max_area=K.ABSORB_MAX_AREA,
                 ink_density_cell_page=K.INK_DENSITY_CELL_PAGE, black_mass_thick_paint=K.BLACK_MASS_THICK_PAINT,
                 black_mass_thick_page=K.BLACK_MASS_THICK_PAGE, ink_line_min_len_page=K.INK_LINE_MIN_LEN_PAGE,
                 ink_line_max_density=K.INK_LINE_MAX_DENSITY, paper_l=api.PAPER_L, tone_line_l=api.TONE_LINE_L,
                 gray_field_cover=api.GRAY_FIELD_COVER, gray_line_max_page=api.GRAY_LINE_MAX_PAGE, gray_drop_g=api.GRAY_DROP_G,
                 cel_min_area=api.CEL_MIN_AREA, tone_pitch_page=api.TONE_PITCH_PAGE, tone_width_page=api.TONE_WIDTH_PAGE,
                 cel_lo=api.CEL_BANDS[0][0], cel_hi=api.CEL_BANDS[-1][1], cel_blur=api.CEL_BLUR, hatch_cross_at=K.HATCH_CROSS_AT,
                 cel_speck_area=api.CEL_SPECK_AREA, cel_field_cover=api.CEL_FIELD_COVER, hatch_under_min_g=K.HATCH_UNDER_MIN_G,
                 hatch_angle=K.HATCH_ANGLE, hatch_angle_2=K.HATCH_ANGLE_2, hatch_pitch_mul=K.TC_HATCH_PITCH_MUL,
                 outline_clear_g=api.OUTLINE_CLEAR_G, outline_min_len_page=api.OUTLINE_MIN_LEN_PAGE,
                 outline_width_page=api.OUTLINE_WIDTH_PAGE, hl_width_max=K.HL_WIDTHS_PAGE[0], marker_width_max=K.MARKER_WIDTHS_PAGE[0],
                 hl_scale=api.HL_SCALE, pen_scale=api._W, fineliner_max=K.FINELINER_MAX_PAGE)
        return _struct(_InkParams, _INK_FIELDS, c)

    def painter_body(self, masks, small, lumimg, ridge, ppg, box, detail, shade, tone, flow, black_l, size, api):
        """The painter's body from the quantized masks to its last stroke in one C call (fastdecomp/painter.c
        rf_painter_body) -> (the Blocks of its strokes in the painter's `out` order, the report, the final class keys), or
        None outside the painter's case (the twin's lines run): the ink pass's case (_ink_case), V70_TRUE_COLOR, the zones
        at once without a color grow, no tone ramp, the keys "tone", "black", "_ink" and ("rgb", three ints) only, every
        mask at the grid size."""
        K, S = api.K, self.session
        if (not self._ink_case(api, flow) or not K.V70_TRUE_COLOR or not K.ZONE_AT_ONCE or K.COLOR_GROW_G > 0 or K.TONE_RAMP_TO_COLOR
                or "_ink" not in masks):
            return None
        W, H = size
        P8 = ctypes.POINTER(ctypes.c_uint8)
        kinds, rgbs, planes = [], [], []
        named = {"tone": 0, "black": 1, "_ink": 3}
        for k in masks:
            if isinstance(k, str) and k in named:
                kinds.append(named[k])
                rgbs.extend((0, 0, 0))
            elif (type(k) is tuple and len(k) == 2 and k[0] == "rgb" and type(k[1]) is tuple and len(k[1]) == 3
                  and all(type(v) is int and 0 <= v <= 255 for v in k[1])):
                kinds.append(2)
                rgbs.extend(k[1])
            else:
                return None
            a = np.ascontiguousarray(self._N.view(masks[k]), dtype=np.uint8)
            if a.shape != (H, W):
                return None
            planes.append(a)
        rgb = np.ascontiguousarray(np.asarray(small, np.uint8))
        lum = np.ascontiguousarray(np.asarray(lumimg, np.uint8))
        rid = np.ascontiguousarray(ridge, dtype=np.uint8)
        if rgb.shape != (H, W, 3) or lum.shape != (H, W) or rid.shape != (H, W):
            return None
        prm = self._ink_params(api, ppg, box, detail, shade, tone, False)
        hp = self._head_params(api, black_l)
        if prm is None or hp is None:
            return None
        kd = np.array(kinds, np.int32)
        rg = np.array(rgbs, np.int32)
        pp = (P8 * len(planes))(*[a.ctypes.data_as(P8) for a in planes])
        rep = (ctypes.c_double * 64)()
        order, n = ctypes.POINTER(ctypes.c_int32)(), ctypes.c_int32()
        keys, nkeys = ctypes.POINTER(ctypes.c_int32)(), ctypes.c_int32()
        rc = self._L.rf_painter_body(S.S, ctypes.byref(prm), ctypes.byref(hp), int(H), int(W), len(planes),
                                    kd.ctypes.data_as(ctypes.POINTER(ctypes.c_int32)), rg.ctypes.data_as(ctypes.POINTER(ctypes.c_int32)), pp,
                                    rgb.ctypes.data_as(P8), lum.ctypes.data_as(P8), rid.ctypes.data_as(P8), ctypes.byref(order), ctypes.byref(n),
                                    ctypes.byref(keys), ctypes.byref(nkeys), rep)
        try:
            kl = np.ctypeslib.as_array(keys, shape=(4 * nkeys.value,)).tolist() if (rc == 0 and nkeys.value) else []
        finally:
            if keys:
                self._L.rf_free(keys)
        o = self._take_order(rc, order, n, "rf_painter_body")
        if o is None:
            return None
        S.sync_styles(api)
        names = {0: "tone", 1: "black", 3: "_ink"}
        final = [names[kl[4 * i]] if kl[4 * i] != 2 else ("rgb", (kl[4 * i + 1], kl[4 * i + 2], kl[4 * i + 3])) for i in range(nkeys.value)]
        return self._blocks(o), list(rep), final

    @staticmethod
    def _head_params(api, black_l):
        """rf_head_params from the painter's constants (black_l: the picture's, after the dark-field gate)."""
        K = api.K
        return _struct(_HeadParams, _HEAD_FIELDS, dict(
            pocket_l=api.POCKET_L, gap_close_g=api.GAP_CLOSE_G, gap_close_page=api.GAP_CLOSE_PAGE, paper_l=api.PAPER_L, ink_l=api.INK_L,
            hl_min_page=K.HL_MIN_PAGE, chroma_min=K.CHROMA_MIN, painterly_chroma_share=K.PAINTERLY_CHROMA_SHARE, black_l=black_l,
            black_mass_thick_paint=K.BLACK_MASS_THICK_PAINT, fill_hole_page=K.FILL_HOLE_PAGE, absorb_max_de=K.ABSORB_MAX_DE,
            gray_halo_open=K.GRAY_HALO_OPEN, gray_halo_share=K.GRAY_HALO_SHARE, tc_ink_l=K.TC_INK_L, tc_quant=max(2, int(K.TC_QUANT)),
            absorb_max_area=K.ABSORB_MAX_AREA))

    @staticmethod
    def ink_report(p, r):
        """The params the ink section and the contour pass set, from inkpass.c's report, in the Python's order."""
        if r[0]:
            p["tone_wash"] = int(r[1])
        if r[2]:
            shr = {"zones": int(r[3]), "shadow": int(r[4]), "pairs": int(r[5])}
            if r[6]:
                shr["l_cut"] = round(r[7], 1)
            p["shadow"] = shr
        kinds = {"line": 0, "fill": int(r[8]), "dark_color": 0}
        for k in (("no_core", "mass") if r[11] == 1 else ("mass", "no_core")):
            if r[9 if k == "no_core" else 10]:
                kinds[k] = int(r[9 if k == "no_core" else 10])
        if r[12]:
            kinds["gray_line"] = 0
            if r[13]:
                kinds["gray_dropped"] = int(r[13])
        p["components"]["INK"] = kinds
        p["tone_lines"] = 0
        if r[14]:
            p["shade_cover"] = round(r[15], 3)
            p["shade_floor"] = round(r[16], 2)
            if r[20]:
                p["hatch_wash"] = int(r[20])
            p["cel_bands"] = {0: int(r[17]), 1: int(r[18])}
            p["tone_lines"] = int(r[19])

    @staticmethod
    def body_report(p, r, keys, ppg, black_l, kname, outline):
        """The params the painter's body sets, from painter.c's report, in the Python's order."""
        if r[0]:
            p["absorbed_tone_px"] = int(r[1])
        if r[2]:
            p["gap_px"], p["gap_r"] = int(r[3]), int(r[4])
        p["painterly"] = dict(on=bool(r[5]), chroma=round(r[6], 3))
        p["tonal_ink"] = {'pixels': int(r[7]), 'wash_colors': int(r[8]), 'black_l': black_l} if r[7] else {'pixels': 0}
        cell = int(r[9])
        if r[12]:
            p["page_label_plan"] = {'cell_source_px': cell, 'cell_page_px': round(cell * ppg, 4), 'changed_pixels': int(r[10]),
                                    'occupied_cells': int(r[11])}
        else:
            p["page_label_plan"] = {'cell_source_px': cell, 'changed_pixels': 0}
        if r[13] == 0:
            p["absorb"] = {"page_scale_labels": True}
        elif r[13] == 1:
            p["absorb"] = {"absorbed": 0.0}
        else:
            p["absorb"] = {"absorbed": round(r[14], 4), "mixed_color_pixels_preserved": int(r[15]), "changed_pixels": int(r[16])}
        if r[17]:
            p["gray_halo_px"] = int(r[18])
        for k in keys:
            if k not in ("black", "tone", "_ink"):
                p["components"][kname(k)] = {"line": 0, "fill": 1}
        p["tone_lines"] = 0
        Fast.ink_report(p, r[32:])
        p["outline_lines"] = int(r[32 + 21]) if outline else 0
        p["soft_px"] = 0

    def black_pieces(self, comps, skip, black, rgb, ppg, thick_min, ink_density, K):
        """The black pass's decision for every piece of `comps` (components()'s list) at once (fastdecomp/black.c
        rf_black_pieces): skip the reference's skip list (or None), black the 'black' mask (needed with an ink density),
        rgb the grid picture's (h, w, 3) array -> [(0 skipped / 1 no-core wash / 2 mass wash / 3 solid fill, (r, g, b))],
        or None when the list does not carry its C arrays or a grid does not match (the reference's lines run)."""
        info, buf = getattr(comps, "info", None), getattr(comps, "buf", None)
        if info is None or buf is None or len(info) != 5 * len(comps):
            return None
        a = np.ascontiguousarray(rgb, dtype=np.uint8)
        if a.ndim != 3 or a.shape[2] != 3:
            return None
        H, W = a.shape[:2]
        n = len(comps)
        if not n:
            return []
        P8, P64, PD = ctypes.POINTER(ctypes.c_uint8), ctypes.POINTER(ctypes.c_int64), ctypes.POINTER(ctypes.c_double)
        bk = hist = None
        hh = hw = 0
        cell = 0.0
        if ink_density is not None:
            if black is None:
                return None
            bk = np.ascontiguousarray(self._N.view(black), dtype=np.uint8)
            hist = np.ascontiguousarray(ink_density[0], dtype=np.float64)
            cell = float(ink_density[1])
            if bk.shape != (H, W) or hist.ndim != 2:
                return None
            hh, hw = hist.shape
        sk = None if skip is None else np.ascontiguousarray(np.asarray(skip, dtype=bool), dtype=np.uint8)
        if sk is not None and sk.shape != (n,):
            return None
        action = np.zeros(n, np.int8)
        mrgb = np.zeros(3 * n, np.int32)
        b = buf if buf.size else np.zeros(1, np.uint8)
        i = np.ascontiguousarray(info, dtype=np.int64)
        r = self._L.rf_black_pieces(i.ctypes.data_as(P64), b.ctypes.data_as(P8), n, None if sk is None else sk.ctypes.data_as(P8),
                                    None if bk is None else bk.ctypes.data_as(P8), a.ctypes.data_as(P8), int(H), int(W), float(ppg),
                                    float(thick_min), None if hist is None else hist.ctypes.data_as(PD), int(hh), int(hw), cell,
                                    float(K.INK_CORE_MIN), float(K.INK_LINE_MIN_LEN_PAGE), float(K.INK_LINE_MAX_DENSITY),
                                    action.ctypes.data_as(ctypes.POINTER(ctypes.c_int8)), mrgb.ctypes.data_as(ctypes.POINTER(ctypes.c_int32)))
        if r == -2:
            return None
        if r != 0:
            raise MemoryError("rf_black_pieces")
        m = mrgb.tolist()
        return [(int(act), (m[3 * t], m[3 * t + 1], m[3 * t + 2])) for t, act in enumerate(action.tolist())]

    def gray_sides(self, comps, nonpaper, pad, cover):
        """The gray-line pass's enclosure test for every component of `comps` (components()'s list) at once: the
        non-paper share of the four strips just outside each crop (fastdecomp/owners.c rf_gray_sides) -> a list of
        bools (True: skip the component), or None when the list does not carry its C arrays (the reference's lines
        run)."""
        info = getattr(comps, "info", None)
        npa = np.ascontiguousarray(self._N.view(nonpaper), dtype=np.uint8)
        if info is None or npa.ndim != 2 or len(info) != 5 * len(comps):
            return None
        if not len(comps):
            return []
        P8, P64 = ctypes.POINTER(ctypes.c_uint8), ctypes.POINTER(ctypes.c_int64)
        skip = np.zeros(len(comps), np.uint8)
        i = np.ascontiguousarray(info, dtype=np.int64)
        if self._L.rf_gray_sides(i.ctypes.data_as(P64), len(comps), npa.ctypes.data_as(P8), int(npa.shape[0]), int(npa.shape[1]), int(pad),
                                 float(cover), skip.ctypes.data_as(P8)) != 0:
            raise MemoryError("rf_gray_sides")
        return skip.astype(bool).tolist()

    def gap_assign(self, D, gap_a, lum_a, sp_, KL, arrs, paper_cut, ink_cut):
        """The gap close's classes (fastdecomp/owners.c rf_gap_assign): D the classes' densities (k, h, w) uint8 in class
        order, gap_a the gap, lum_a the luminance, sp_ the smoothed color, KL the classes' Lab colors (k, 3), arrs the
        classes' writable masks -> (the pixels given, [whether class j got one]), or None when a grid does not match
        (the reference's lines run)."""
        D = np.ascontiguousarray(D, dtype=np.uint8)
        if D.ndim != 3 or D.shape[0] != len(arrs) or not len(arrs):
            return None
        nk, H, W = D.shape
        g = np.ascontiguousarray(gap_a, dtype=np.uint8)
        lu = np.ascontiguousarray(lum_a, dtype=np.uint8)
        rgb = np.ascontiguousarray(sp_, dtype=np.uint8)
        kl = np.ascontiguousarray(KL, dtype=np.float64)
        if g.shape != (H, W) or lu.shape != (H, W) or rgb.shape != (H, W, 3) or kl.shape != (nk, 3):
            return None
        for x in arrs:
            if x.dtype != np.uint8 or not x.flags.c_contiguous or not x.flags.writeable or x.shape != (H, W):
                return None
        P8 = ctypes.POINTER(ctypes.c_uint8)
        touched = np.zeros(nk, np.uint8)
        n = self._L.rf_gap_assign((P8 * nk)(*[D[j].ctypes.data_as(P8) for j in range(nk)]), nk, H, W, g.ctypes.data_as(P8),
                                  lu.ctypes.data_as(P8), rgb.ctypes.data_as(P8), int(paper_cut), int(ink_cut),
                                  kl.ctypes.data_as(ctypes.POINTER(ctypes.c_double)), (P8 * nk)(*[x.ctypes.data_as(P8) for x in arrs]),
                                  touched.ctypes.data_as(P8))
        if n < 0:
            raise MemoryError("rf_gap_assign")
        return int(n), touched.astype(bool).tolist()

    def gray_halo(self, masks, skirt, share):
        """The gray halo test of every mask of `masks` (fastdecomp/owners.c rf_gray_halo) -> (the pixels dropped, [the
        kept pixels of each mask as a boolean array]), or None when a grid does not match (the reference's lines run)."""
        sk = np.ascontiguousarray(skirt, dtype=np.uint8)
        if sk.ndim != 2:
            return None
        H, W = sk.shape
        arrs = [np.ascontiguousarray(self._N.view(m), dtype=np.uint8) for m in masks]
        if any(a.shape != (H, W) for a in arrs):
            return None
        if not arrs:
            return 0, []
        keeps = [np.empty((H, W), np.uint8) for _ in arrs]
        P8 = ctypes.POINTER(ctypes.c_uint8)
        n = self._L.rf_gray_halo((P8 * len(arrs))(*[a.ctypes.data_as(P8) for a in arrs]), len(arrs), H, W, sk.ctypes.data_as(P8),
                                 float(share), (P8 * len(keeps))(*[k.ctypes.data_as(P8) for k in keeps]))
        if n < 0:
            raise MemoryError("rf_gray_halo")
        return int(n), [k.view(bool) for k in keeps]

    def cel_regions(self, gray, mask, min_area_px, bands, consts):
        """rm_paint.cel_regions(gray, mask, min_area_px, bands) in C (fastdecomp/cel.c); consts = (CEL_BLUR, CEL_MEDIAN,
        CEL_SPECK_AREA, CEL_FIELD_COVER) -> the same [(band index, "L" 0/255 image)], or None when the grids do not
        match (the reference's function runs)."""
        P8 = ctypes.POINTER(ctypes.c_uint8)
        g = np.ascontiguousarray(np.asarray(gray, np.uint8))
        m = np.ascontiguousarray(self._N.view(mask), dtype=np.uint8)
        if g.ndim != 2 or m.shape != g.shape or not bands:
            return None
        H, W = g.shape
        blur, k, speck, field = consts
        lohi = np.array([float(v) for lo_hi in bands for v in lo_hi], np.float64)
        outs = [np.empty((H, W), np.uint8) for _ in bands]
        if self._L.rf_cel_regions(g.ctypes.data_as(P8), m.ctypes.data_as(P8), int(H), int(W), ctypes.c_float(blur), lohi.ctypes.data_as(ctypes.POINTER(ctypes.c_double)),
                                  len(bands), int(k), float(speck), float(field), int(min_area_px), (P8 * len(outs))(*[o.ctypes.data_as(P8) for o in outs])) != 0:
            raise MemoryError("rf_cel_regions")
        return [(bi, self._N.img(o)) for bi, o in enumerate(outs)]

    def skeleton_thin(self, mask, min_len_g, K):
        """rm_paint._skeleton(mask, ppg, min_len_g, method="thin") in C (fastdecomp/skel.c) -> the same ([(length,
        [(x, y), ...])], total, pieces) with Python floats, or None outside the painter's case (SUBCELL_GEOMETRY: the
        reference's function runs)."""
        if not K.SUBCELL_GEOMETRY:
            return None
        a = np.ascontiguousarray(self._N.view(mask) != 0, dtype=np.uint8)
        if a.ndim != 2:
            return None
        H, W = a.shape
        PD, P32 = ctypes.POINTER(ctypes.c_double), ctypes.POINTER(ctypes.c_int32)
        Lp, cp, xp = PD(), P32(), PD()
        tot, pieces = ctypes.c_double(), ctypes.c_int32()
        n = self._L.rf_skeleton_thin(a.ctypes.data_as(ctypes.POINTER(ctypes.c_uint8)), int(H), int(W), float(min_len_g),
                                     0.7 if K.LINE_SMOOTH else 0.35, 1 if K.LINE_SMOOTH else 0, ctypes.byref(Lp), ctypes.byref(cp),
                                     ctypes.byref(xp), ctypes.byref(tot), ctypes.byref(pieces))
        if n < 0:
            raise MemoryError("rf_skeleton_thin")
        out = []
        try:
            if n:
                Ls = np.ctypeslib.as_array(Lp, shape=(n,)).tolist()
                cs = np.ctypeslib.as_array(cp, shape=(n,)).tolist()
                xy = np.ctypeslib.as_array(xp, shape=(2 * sum(cs),)).tolist()
                o = 0
                for L, c in zip(Ls, cs):
                    out.append((L, [(xy[2 * t], xy[2 * t + 1]) for t in range(o, o + c)]))
                    o += c
        finally:
            for p_ in (Lp, cp, xp):
                if p_:
                    self._L.rf_free(p_)
        return out, tot.value, pieces.value

    def uniform_hatch(self, mask, angles, pitch_g, min_len_g):
        """rm_paint.uniform_hatch in C (fastdecomp/hatch.c) -> the same [[(x0, y0), (x1, y1)], ...] of Python floats, or
        None when the C refuses the call (the reference's function runs)."""
        a = np.ascontiguousarray(self._N.view(mask), dtype=np.uint8)
        if a.ndim != 2:
            return None
        H, W = a.shape
        ang = np.array([float(v) for v in angles], np.float64)
        out = ctypes.POINTER(ctypes.c_double)()
        n = self._L.rf_uniform_hatch(a.ctypes.data_as(ctypes.POINTER(ctypes.c_uint8)), int(H), int(W), ang.ctypes.data_as(ctypes.POINTER(ctypes.c_double)),
                                     len(ang), float(pitch_g), float(min_len_g), ctypes.byref(out))
        if n == -2:
            return None
        if n < 0:
            raise MemoryError("rf_uniform_hatch")
        try:
            v = np.ctypeslib.as_array(out, shape=(4 * n,)).tolist() if n else []
        finally:
            if out:
                self._L.rf_free(out)
        return [[(v[4 * i], v[4 * i + 1]), (v[4 * i + 2], v[4 * i + 3])] for i in range(n)]

    def ink_density(self, black_left, black, ppg, size, core_min, absorb_max_area, cell_page):
        """The ink density of the black pass (fastdecomp/specks.c rf_ink_density) -> (True, (the smoothed counts,
        cell) or None when black_left has no piece), or (False, None) when a grid does not match (the reference's
        lines run)."""
        W, H = size
        P8 = ctypes.POINTER(ctypes.c_uint8)
        bl = np.ascontiguousarray(self._N.view(black_left), dtype=np.uint8)
        bk = np.ascontiguousarray(self._N.view(black), dtype=np.uint8)
        if bl.shape != (H, W) or bk.shape != (H, W):
            return False, None
        cell = max(4.0, cell_page / ppg)
        hist = np.zeros((int(H // cell) + 2, int(W // cell) + 2))
        n = self._L.rf_ink_density(bl.ctypes.data_as(P8), bk.ctypes.data_as(P8), int(H), int(W), float(ppg), float(core_min), float(absorb_max_area),
                                   float(cell), int(hist.shape[0]), int(hist.shape[1]), hist.ctypes.data_as(ctypes.POINTER(ctypes.c_double)))
        if n < 0:
            raise MemoryError("rf_ink_density")
        return True, ((hist, cell) if n else None)


    def covered(self, masks, size):
        """covered_by_color of the black pass: zeros, then |= (mask != 0) for each of `masks` (fastdecomp/specks.c)
        -> a boolean (h, w) array, or None when a mask does not match the grid (the reference's lines run)."""
        W, H = size
        P8 = ctypes.POINTER(ctypes.c_uint8)
        arrs = [np.ascontiguousarray(self._N.view(m), dtype=np.uint8) for m in masks]
        if any(a.shape != (H, W) for a in arrs):
            return None
        out = np.empty((H, W), np.uint8)
        src = (P8 * max(1, len(arrs)))(*[a.ctypes.data_as(P8) for a in arrs])
        self._L.rf_any_nonzero(src, len(arrs), int(H), int(W), out.ctypes.data_as(P8))
        return out.view(bool)

    def speck_skip(self, comps, covered, draw_min, covered_min):
        """The black pass's covered-speck test for every component of `comps` (components()'s list) at once: span <
        draw_min and the covered share of its pixels >= covered_min (fastdecomp/specks.c) -> a list of bools, or None
        when the list does not carry its C arrays (the reference's lines run)."""
        info, buf = getattr(comps, "info", None), getattr(comps, "buf", None)
        cov = np.ascontiguousarray(covered, dtype=np.uint8) if covered is not None else None
        if info is None or buf is None or cov is None or cov.ndim != 2 or len(info) != 5 * len(comps):
            return None
        P8, P64 = ctypes.POINTER(ctypes.c_uint8), ctypes.POINTER(ctypes.c_int64)
        skip = np.zeros(max(1, len(comps)), np.uint8)
        b = buf if buf.size else np.zeros(1, np.uint8)
        i = info if info.size else np.zeros(1, np.int64)
        self._L.rf_speck_skip(i.ctypes.data_as(P64), b.ctypes.data_as(P8), len(comps), cov.ctypes.data_as(P8), int(cov.shape[0]), int(cov.shape[1]),
                              int(draw_min), float(covered_min), skip.ctypes.data_as(P8))
        return skip[:len(comps)].astype(bool).tolist()

    def tone_pockets(self, inv, tone_a, lum_a, sm_a, thr):
        """The tone-pocket scan (rf_tone_pockets): for each enclosed pocket, in components order, with at least half
        its area light tone -> (area, n, sum r, sum g, sum b, gx, gy), gx/gy int64 arrays in raster order."""
        P8, P64 = ctypes.POINTER(ctypes.c_uint8), ctypes.POINTER(ctypes.c_int64)
        a = np.ascontiguousarray(self._N.view(inv), dtype=np.uint8)
        t = np.ascontiguousarray(tone_a, dtype=np.uint8)
        lu = np.ascontiguousarray(lum_a, dtype=np.uint8)
        rgb = np.ascontiguousarray(sm_a, dtype=np.uint8)
        Hi, Wi = a.shape
        if t.shape != (Hi - 2, Wi - 2) or lu.shape != t.shape or rgb.shape != t.shape + (3,):
            raise ValueError("tone pocket grids do not match")
        info, xy = P64(), P64()
        n = self._L.rf_tone_pockets(a.ctypes.data_as(P8), int(Hi), int(Wi), t.ctypes.data_as(P8), lu.ctypes.data_as(P8),
                                    rgb.ctypes.data_as(P8), float(thr), ctypes.byref(info), ctypes.byref(xy))
        if n < 0:
            raise MemoryError("rf_tone_pockets")
        out = []
        try:
            if n > 0:
                inf = np.ctypeslib.as_array(info, shape=(5 * n,)).tolist()
                tot = sum(inf[5 * i + 1] for i in range(n))
                pts = np.ctypeslib.as_array(xy, shape=(2 * tot,)).copy() if tot else np.zeros(0, np.int64)
                o = 0
                for i in range(n):
                    area, cnt, sr, sg, sb = inf[5 * i:5 * i + 5]
                    seg = pts[2 * o:2 * (o + cnt)]
                    out.append((area, cnt, sr, sg, sb, seg[0::2].copy(), seg[1::2].copy()))
                    o += cnt
        finally:
            if info:
                self._L.rf_free(info)
            if xy:
                self._L.rf_free(xy)
        return out

    def pockets(self, pockets, arrs, k):
        """The pocket loop over `pockets` (an "L" image) into `arrs` (the color keys' writable arrays, in order)."""
        a = np.ascontiguousarray(self._N.view(pockets), dtype=np.uint8)
        H, W = a.shape
        for x in arrs:
            if x.dtype != np.uint8 or not x.flags.c_contiguous or not x.flags.writeable or x.shape != (H, W):
                raise ValueError("pocket arrays must be writable C-order uint8 grids")
        ptrs = (ctypes.POINTER(ctypes.c_uint8) * max(1, len(arrs)))(*[x.ctypes.data_as(ctypes.POINTER(ctypes.c_uint8)) for x in arrs])
        n = self._L.rf_pockets(a.ctypes.data_as(ctypes.POINTER(ctypes.c_uint8)), int(H), int(W), int(k), len(arrs), ptrs)
        if n < 0:
            raise MemoryError("rf_pockets")
        return n

    def union(self, size, ims):
        return _union(self._N, self._Image, size, ims)

    def blur(self, a, radius, gaussian):
        """ImageFilter.GaussianBlur(radius) (gaussian) or BoxBlur(radius) of an "L" (h, w) or "RGB" (h, w, 3) uint8
        array, as Pillow computes it (fastdecomp/blur.c rf_box_blur) -> a new array."""
        a = np.ascontiguousarray(a, dtype=np.uint8)
        out = np.empty_like(a)
        P8 = ctypes.POINTER(ctypes.c_uint8)
        if self._L.rf_box_blur(a.ctypes.data_as(P8), out.ctypes.data_as(P8), a.shape[0], a.shape[1], 1 if a.ndim == 2 else a.shape[2],
                               ctypes.c_float(radius), 1 if gaussian else 0) != 0:
            raise MemoryError("rf_box_blur")
        return out

    def xdog_ridge(self, small, sigma, ink):
        """rmb_lineart.thin(rmb_lineart.mask(*rmb_lineart.xdog(src, width, sigma), ink)) for a source that is the grid
        picture at its own size (fastdecomp/xdog.c) -> boolean array. xdog's defaults: k 1.6, tau 0.985,
        autocontrast with cutoff 1."""
        a = np.ascontiguousarray(np.asarray(small, np.uint8))
        H, W = a.shape[:2]
        ridge = np.empty((H, W), np.uint8)
        cnt = ctypes.c_int64()
        if self._L.rf_xdog_ridge(a.ctypes.data_as(ctypes.POINTER(ctypes.c_uint8)), H, W, ctypes.c_float(sigma), ctypes.c_float(sigma * 1.6),
                                 0.985, float(ink), ridge.ctypes.data_as(ctypes.POINTER(ctypes.c_uint8)), ctypes.byref(cnt)) != 0:
            raise MemoryError("rf_xdog_ridge")
        return ridge.view(bool)

    def flow_coherent(self, lumimg, sigma, pre, min_coherence):
        """float((rm_flow.field(lumimg, sigma, pre)[2] >= min_coherence).mean()), the coherence in C (fastdecomp/flow.c)
        with scipy's own Gaussian kernels (_gaussian_kernel1d, as gaussian_filter1d builds them: radius
        int(4.0 * sigma + 0.5), reversed)."""
        from scipy.ndimage import _filters as SF

        def kernel(s):
            if s <= 1e-15:                       # rm_flow._blur (s <= 0) and gaussian_filter (s <= 1e-15): no filter
                return None, 0
            lw = int(4.0 * float(s) + 0.5)
            return np.ascontiguousarray(SF._gaussian_kernel1d(s, 0, lw)[::-1], np.float64), lw
        a = np.ascontiguousarray(np.asarray(lumimg, np.uint8))
        H, W = a.shape
        wp, rp = kernel(pre)
        ws, rs = kernel(sigma)
        PD = ctypes.POINTER(ctypes.c_double)
        cnt = ctypes.c_int64()
        if self._L.rf_flow_coherence(a.ctypes.data_as(ctypes.POINTER(ctypes.c_uint8)), H, W, wp.ctypes.data_as(PD) if wp is not None else None, rp,
                                     ws.ctypes.data_as(PD) if ws is not None else None, rs, float(min_coherence), ctypes.byref(cnt)) != 0:
            raise MemoryError("rf_flow_coherence")
        return float(np.float64(cnt.value) / np.float64(H * W))

    def gap_density(self, masks, keys, min_span, r, size):
        """The gap densities of decompose: {key: BoxBlur(r) of the key's anchor} for the keys whose anchor (its pieces
        at least min_span wide or tall) has a pixel, in `keys` order (fastdecomp/blur.c rf_gap_density)."""
        W, H = size
        if not keys:
            return {}
        P8 = ctypes.POINTER(ctypes.c_uint8)
        arrs = [np.ascontiguousarray(self._N.view(masks[k]), dtype=np.uint8) for k in keys]
        if any(a.shape != (H, W) for a in arrs):
            raise ValueError("gap density masks do not match the grid")
        D = np.empty((len(keys), H, W), np.uint8)
        has = np.zeros(len(keys), np.uint8)
        src = (P8 * len(keys))(*[a.ctypes.data_as(P8) for a in arrs])
        dst = (P8 * len(keys))(*[D[i].ctypes.data_as(P8) for i in range(len(keys))])
        if self._L.rf_gap_density(src, len(keys), H, W, int(min_span), ctypes.c_float(r), dst, has.ctypes.data_as(P8)) != 0:
            raise MemoryError("rf_gap_density")
        return {k: D[i] for i, k in enumerate(keys) if has[i]}

    def tonal_ink(self, masks, small, black_l, api):
        """rmb_resolution.tonal_ink in C (fastdecomp/tonal.c): the protected pixels (tonal_mask), their ladder
        palette, and every mask rebuilt -- the same keys in the same order with the same pixels. Masks that do not
        match the grid run the Python steps below."""
        if '_ink' not in masks:
            return {'pixels': 0}
        N = api.N
        P8, P32 = ctypes.POINTER(ctypes.c_uint8), ctypes.POINTER(ctypes.c_int32)
        rgb = np.ascontiguousarray(np.asarray(small.convert('RGB'), np.uint8))
        H, W = rgb.shape[:2]
        keys = list(masks)
        ins = [np.ascontiguousarray(N.view(masks[k]), dtype=np.uint8) for k in keys]
        if all(a.shape == (H, W) for a in ins):
            ladder = np.asarray([api._tc_key((v, v, v))[0] for v in range(256)], np.uint8)
            protect = np.empty((H, W), np.uint8)
            pidx = np.empty((H, W), np.int32)
            palette = np.empty(max(1, min(H * W, 1 << 24)), np.int32)
            npal = ctypes.c_int32()
            cnt = self._L.rf_tonal_protect(ins[keys.index('_ink')].ctypes.data_as(P8), rgb.ctypes.data_as(P8), H, W,
                                           float(black_l * 2.55), float(api.K.BLACK_MASS_THICK_PAINT), ladder.ctypes.data_as(P8),
                                           protect.ctypes.data_as(P8), pidx.ctypes.data_as(P32), palette.ctypes.data_as(P32),
                                           ctypes.byref(npal))
            if cnt < 0:
                raise MemoryError("rf_tonal_protect")
            if cnt == 0:
                return {'pixels': 0}
            pos = {k: i for i, k in enumerate(keys)}
            new = []
            slot = np.empty(max(1, npal.value), np.int32)
            for i, c in enumerate(palette[:npal.value].tolist()):
                key = ('rgb', (c >> 16, (c >> 8) & 255, c & 255))
                if key not in pos:
                    pos[key] = len(keys) + len(new)
                    new.append(key)
                slot[i] = pos[key]
            outs = [np.empty((H, W), np.uint8) for _ in range(len(keys) + len(new))]
            src = (P8 * len(ins))(*[a.ctypes.data_as(P8) for a in ins])
            dst = (P8 * len(outs))(*[a.ctypes.data_as(P8) for a in outs])
            self._L.rf_tonal_apply(src, len(ins), dst, len(outs), protect.ctypes.data_as(P8), pidx.ctypes.data_as(P32),
                                   slot.ctypes.data_as(P32), H, W)
            for i, k in enumerate(keys + new):
                masks[k] = N.img(outs[i])
            return {'pixels': int(cnt), 'wash_colors': int(npal.value), 'black_l': black_l}
        from paperdaemon.pipeline.decompose.reference import rmb_resolution as RES
        rgb = np.asarray(small.convert('RGB'), np.uint8)
        protect = RES.tonal_mask(masks, small, black_l, api.K.BLACK_MASS_THICK_PAINT)
        if not protect.any():
            return {'pixels': 0}
        keep = ~protect
        for key in list(masks):
            masks[key] = N.bool_img((N.view(masks[key]) != 0) & keep)
        ladder = np.asarray([api._tc_key((v, v, v))[0] for v in range(256)], np.uint8)
        mapped = ladder[rgb[protect]].astype(np.uint32)
        packed = (mapped[:, 0] << 16) | (mapped[:, 1] << 8) | mapped[:, 2]
        colors, index = np.unique(packed, return_inverse=True)
        palette = np.column_stack((colors >> 16, (colors >> 8) & 255, colors & 255))
        yy, xx = np.nonzero(protect)
        index = index.reshape(-1)
        order = np.argsort(index, kind="stable")
        bounds = np.searchsorted(index[order], np.arange(len(palette) + 1), side="left")
        for i, c in enumerate(palette):
            key = ('rgb', tuple(map(int, c)))
            arr = (N.view(masks[key]) != 0) if key in masks else np.zeros(protect.shape, bool)
            sel = order[bounds[i]:bounds[i + 1]]
            arr[yy[sel], xx[sel]] = True
            masks[key] = N.bool_img(arr)
        return {'pixels': int(protect.sum()), 'wash_colors': len(palette), 'black_l': black_l}


def twin(P, rmfast, session=None, report=True):
    """rm_paint.decompose's twin, bound to rm_paint's globals, its C helpers given. With a store session
    (fastdecomp/rmstore.py) the zones' fills run as one batch and the result is an rmstore.Strokes."""
    global _CODE
    if _CODE is None:
        _CODE = _decompose_twin.__code__
    fx = Fast(rmfast, P.N, P.Image, session, report)
    f = types.FunctionType(_CODE, vars(P), "decompose", P.decompose.__defaults__)
    f.__kwdefaults__ = {"_fx": fx}
    f.__doc__ = P.decompose.__doc__
    return f


def _decompose_twin(src, w, h, detail=None, origin=None, tone=None, shade=None, black_l=None, chroma_min=None, grid_max=None, *, _fx=None):   # defaults: rm_paint.decompose's (twin())
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
    # TWIN: the source's own mode and size (the C ridge's guard below); rm_model's second run hands its recolored picture
    # over in memory (a PIL RGB image) instead of as PNG bytes -- the same pixels, PNG being lossless
    _src_im = src if isinstance(src, Image.Image) else Image.open(src)
    _src_mode, _src_size = _src_im.mode, _src_im.size
    im = _src_im.convert("RGB")
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
    if _fx.session is not None and OUTLINE_XDOG == XDOG_INK and _src_mode == "RGB" and _src_size == small.size:
        # TWIN: the XDoG response, its darkest XDOG_INK share and the Zhang-Suen thinning in C (fastdecomp/xdog.c),
        # from the grid picture: LA.xdog re-reads the source as L at the grid's width, which here is the source's own
        # size (no resize) of the same RGB pixels. The response itself is only read again for an outline slice other
        # than XDOG_INK, which takes the Python path.
        ridge = _fx.xdog_ridge(small, XDOG_SIGMA_REF * grid_w / 340.0, XDOG_INK)
        resp = rsize = None
    else:
        resp, rsize = LA.xdog(src, width=grid_w, sigma=XDOG_SIGMA_REF * grid_w / 340.0)
        ridge = LA.thin(LA.mask(resp, rsize, XDOG_INK))
    p["ridge_px"] = int(np.count_nonzero(ridge))
    flow = None
    if K.V69_FLOW_FILL and not K.V69_FLOW_HATCH and _fx.session is not None:
        # TWIN: only the field's coherence is computed (fastdecomp/flow.c) -- the one part of it anything reads: the
        # tangents feed only the flow hatch (V69_FLOW_HATCH, off) and _flow_rows (no caller). _FLOW is set non-None
        # as before, and a reader of the tangents would fail instead of differing.
        _FLOW = (None, None, None)
        if _fx.report:                               # TWIN: only when the caller wants the report value
            p["flow_coherent"] = round(_fx.flow_coherent(lumimg_, K.FLOW_SIGMA, K.FLOW_PRE_BLUR, K.FLOW_MIN_COHERENCE), 3)
    elif K.V69_FLOW_HATCH or K.V69_FLOW_FILL:
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
    # TWIN: everything from here to the contour pass's last stroke in one C call (fastdecomp/painter.c rf_painter_body: the
    # pockets, the gap close, the painterly share, tonal_ink, coarsen_washes, the absorber, the gray halo, the zones' batch,
    # the ink section and the contour pass), its strokes into the store in the order the lines below make them and the
    # report values the same; outside the painter's case (see Fast.painter_body) the lines below run
    _body = _fx.painter_body(masks, small, lumimg_, ridge, ppg, box, detail, shade, tone, flow, black_l, (grid_w, gh),
                            sys.modules[__name__]) if _fx.session is not None else None
    if _body is not None:
        out.extend(_body[0])
        _fx.body_report(p, _body[1], _body[2], ppg, black_l, _kname, OUTLINE)
        out, _ext = _fx.session.finish(out, Pen.HIGHLIGHTER_2, HL_SCALE, _W)
        if _ext is not None:
            p["extent"] = _ext
        _SKIN_HUE_OFFSET, _DARK_FIELD, _FLOW, _WHITE_FLOOR, _UP = 0.0, False, None, None, 1.0   # per picture
        return out, p, round(time.perf_counter() - t0, 3)

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
        union = _fx.union((grid_w, gh), [masks[k] for k in color_keys])   # TWIN: one maximum
        inv = ImageChops.invert(ImageOps.expand(union, 1, 0))
        tone_a = N.view(masks["tone"]) != 0
        lum_a = np.asarray(lumimg_, np.uint8)
        sm_a = np.asarray(small, np.uint8)
        absorbed = {}
        # TWIN: the per-pocket scan (enclosure, light tone, the half-area test, the color sums) in one C pass
        # (fastdecomp/pockets.c rf_tone_pockets); the color key of each pocket that passes is the reference's code
        for a_, n_, s_r, s_g, s_b, gx, gy in _fx.tone_pockets(inv, tone_a, lum_a, sm_a, POCKET_L * 2.55):
            r_ = s_r / n_; g_ = s_g / n_; b_ = s_b / n_
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
        union = _fx.union((grid_w, gh), [masks[k] for k in color_keys])   # TWIN: one maximum
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
        if pockets.getbbox() is not None and _fx is not None:
            # TWIN: the loop below in one C pass (fastdecomp/pockets.c rf_pockets)
            key_arrs = {k: N.arr(masks[k]) for k in color_keys}
            _fx.pockets(pockets, [key_arrs[k] for k in color_keys], _ker())
            for k in color_keys:
                masks[k] = N.img(key_arrs[k])
        elif pockets.getbbox() is not None:
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
        union = _fx.union((grid_w, gh), [masks[k] for k in color_keys])   # TWIN: one maximum
        gap = ImageChops.subtract(_close(union, r_), union)
        gap_a = N.view(gap) != 0
        lum_a = np.asarray(lumimg_, np.uint8)
        sp_ = _fx.blur(np.asarray(small, np.uint8), 1.0, True)   # smoothed color: no speckle (TWIN: Pillow's GaussianBlur in C)
        paper_cut, ink_cut = int(round(PAPER_L * 2.55)), int(round(INK_L * 2.55))
        # a gap joins a class's REAL region: a fleck below the span floor is dropped later and must
        # not grow into a blob here (the teapot's shadow rim seeded gray dabs). Local density of the
        # anchors decides reach (BoxBlur(r) is non-zero within r) and, for dark pixels, ownership.
        # TWIN: the anchors and their BoxBlur(r_) for every class at once, on all cores (fastdecomp/blur.c
        # rf_gap_density: rmb_npops.components' span rule, Pillow's box blur)
        dens = _fx.gap_density(masks, color_keys, min_span_col, r_, (grid_w, gh))
        n_gap = 0
        if dens:
            dkeys = list(dens)                                    # class order = the draw order
            D = np.stack([dens[k] for k in dkeys])
            # TWIN: the class of every gap pixel in one C pass (fastdecomp/owners.c rf_gap_assign), into copies of the
            # classes' masks; a class that got a pixel takes its copy, as below. The classes' Lab colors are the lines'.
            _KL = np.array([_lab(_fill_rgba(k) if (isinstance(k, tuple) and k[0] == "rgb") else _FILL_RGB[k])
                            for k in dkeys], np.float64)
            _ka = [N.arr(masks[k]) for k in dkeys]
            _ga = _fx.gap_assign(D, gap_a, lum_a, sp_, _KL, _ka, paper_cut, ink_cut)
            if _ga is not None:
                n_gap = _ga[0]
                for k, ka, _t in zip(dkeys, _ka, _ga[1]):
                    if _t:
                        masks[k] = N.img(ka)
            else:
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
    p["tonal_ink"] = _fx.tonal_ink(masks, small, black_l, sys.modules[__name__])   # TWIN: rmb_resolution.tonal_ink, the scans done once
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
        _gray = []
        for k_ in [k for k in masks if isinstance(k, tuple) and k[0] == "rgb"]:
            r_, g_, b_ = k_[1]
            L_, a_, b2_ = _lab((float(r_), float(g_), float(b_)))
            if math.hypot(a_, b2_) >= K.CHROMA_MIN or L_ <= K.TC_INK_L:
                continue                       # a real color, or ink's own range: leave it alone
            _gray.append(k_)
        # TWIN: the per-component test below for every gray mask at once, in C (fastdecomp/owners.c rf_gray_halo)
        _gh = _fx.gray_halo([masks[k_] for k_ in _gray], skirt, K.GRAY_HALO_SHARE)
        if _gh is not None:
            n_halo = _gh[0]
            for k_, keep_a in zip(_gray, _gh[1]):
                masks[k_] = N.bool_img(keep_a)
        for k_ in ([] if _gh is not None else _gray):
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
    nonpaper = _fx.union((grid_w, gh), [masks[k_] for k_ in masks if k_ != "_ink"])   # TWIN: one maximum
    col_line_mask = Image.new("L", (grid_w, gh))
    if _fx.session is not None and K.SUBCELL_GEOMETRY:
        # TWIN: from here on every single fill (the black pass's fill_solid and _fill_region_hl, the washes after it;
        # the zones' batch below still runs at once) is recorded and planned in batches on all cores when the strokes
        # are finished (rmstore.Session.defer); `out` only ever gets a fill's result appended, so it holds the same
        # strokes in the same order
        _fx.session.defer()
    _zone_batch = _fx.session is not None and K.ZONE_AT_ONCE and K.COLOR_GROW_G <= 0 and K.SUBCELL_GEOMETRY
    if _zone_batch:
        # TWIN: every color zone's fill planned at once on all cores (fastdecomp/store.c rf_store_fill_batch). The
        # loop below calls draw_component once per zone (ZONE_AT_ONCE, no grow), which for color under SUBCELL_GEOMETRY
        # is one rmb_geometry.fill per wash color of the zone (one per letter of an "hl" pair, a marker fill for a pen
        # color) and kind "fill"; the batch makes the same fills, appended in the same order.
        _jobs = []
        for k in color_keys:
            kind_, val = k if isinstance(k, tuple) else ("pen", k)
            if kind_ == "rgb":
                _jobs.append((masks[k], tuple(val), (0, 0), True))
            elif kind_ == "hl":
                _jobs.extend((masks[k], HL_RGBA[letter], (0, 0), True) for letter in val)
            else:
                _jobs.append((masks[k], val, (0, 0), False))
            p["components"][_kname(k)] = {"line": 0, "fill": 1}
        for st in _fx.session.fill_batch(_jobs, ppg, box, (grid_w, gh), sys.modules[__name__]):
            out.extend(st)
    for k in ([] if _zone_batch else color_keys):
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
    # TWIN: the ink section below and the contour pass after it in one C pass (fastdecomp/inkpass.c rf_ink_pass): its fills
    # and pen strokes go into the store in the order the lines below make them, and the report values are the same; outside
    # the painter's case (see Fast.ink_pass) the lines below run
    _ink_c = _fx.ink_pass(masks, small, lumimg_, ridge, ppg, box, detail, shade, tone, painterly, flow, (grid_w, gh),
                          sys.modules[__name__]) if ink is not None else None
    if _ink_c is not None:
        out.extend(_ink_c[0])
        _fx.ink_report(p, _ink_c[1])
    # `is not None`, not "has ink". The hatch pass lives inside this block, and a picture with
    # tone but no achromatic ink -- a dark COLOR ground and colored ornament, nothing black --
    # was never shaded at all: its ground came out as a flat pale wash. components() of an empty
    # mask yields nothing, so the line and fill passes are unchanged when there is no ink.
    if ink is not None and _ink_c is None:
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
        colored = _fx.union(ink.size, [masks[k_] for k_ in masks if k_ not in ("black", "tone", "_ink")])   # TWIN: one maximum
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
                covered_by_color = _fx.covered([masks[k_] for k_ in color_keys], (grid_w, gh))   # TWIN: the union in C (fastdecomp/specks.c)
                if covered_by_color is None:
                    covered_by_color = np.zeros((gh, grid_w), bool)
                    for k_ in color_keys:
                        covered_by_color |= N.view(masks[k_]) != 0
            # WHICH DARK PIECES ARE INK (rmb_params.INK_CORE_MIN and the lines after it): the local density of the
            # core-less ink pieces is needed before any piece is judged, so it is measured here, once, over the whole
            # mask: pieces per INK_DENSITY_CELL_PAGE square, 3 x 3 cells smoothed, read at each piece's centroid
            ink_density = None
            if K.INK_CORE_MIN > 0 and "black" in masks:
                # TWIN: the lines below in C (fastdecomp/specks.c), unless a grid does not match
                _done, ink_density = _fx.ink_density(black_left, masks["black"], ppg, (grid_w, gh), K.INK_CORE_MIN, K.ABSORB_MAX_AREA,
                                                     K.INK_DENSITY_CELL_PAGE)
                if not _done:
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
            _black_nz = None
            _comps = components(black_left, 1, 0)
            # TWIN: the covered-speck test below for every component at once, in C (fastdecomp/specks.c)
            _skip = _fx.speck_skip(_comps, covered_by_color, draw_min, K.INK_SPECK_COVERED) if covered_by_color is not None else None
            # TWIN: each piece's no-core / mass decision and its mean color below, for every piece at once on all cores,
            # in C (fastdecomp/black.c rf_black_pieces)
            _bp = _fx.black_pieces(_comps, _skip, masks.get("black"), np.asarray(small.convert("RGB"), np.uint8), ppg,
                                   (K.BLACK_MASS_THICK_PAINT if painterly else K.BLACK_MASS_THICK_PAGE), ink_density, K)
            for _ci, (area, m, off) in enumerate(_comps):
                if _skip is not None:
                    if _skip[_ci]:
                        continue
                elif covered_by_color is not None:
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
                if _bp is not None:
                    # TWIN: the decision and the color made in C for this piece (the lines in the branch below)
                    _act, _mrgb = _bp[_ci]
                    if _act in (1, 2):
                        out.extend(_fill_region_hl(m, _mrgb, ppg, box, offset=off, grid=(grid_w, gh)))
                        kinds["no_core" if _act == 1 else "mass"] = kinds.get("no_core" if _act == 1 else "mass", 0) + 1
                        continue                      # stays in hatch_mask: the hatch carries it
                else:
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
                                # TWIN: the black mask's boolean grid is built once (masks is not changed in this loop)
                                if _black_nz is None:
                                    _black_nz = N.view(masks["black"]) != 0
                                core = float((sel & _black_nz[y0:y1, x0:x1]).sum()) / n_sel
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
            # everything that is not paper: tone, ink... and COLOR. A dark blob inside a wash is (TWIN: one maximum)
            nonpaper = _fx.union((grid_w, gh), [masks["tone"], ink] + [masks[k_] for k_ in masks if k_ not in ("black", "tone", "_ink")])
            # (if color counted as paper here, then once dark colors stopped being ink an oak's
            # canopy shading was "thin gray that is not a line" and was dropped -- 0 hatch lines)
            pad = max(3, int(round(10.0 / ppg)))
            _gcomps = components(gray, min_span)
            # TWIN: the four-strip test below for every component at once, in C (fastdecomp/owners.c rf_gray_sides,
            # which builds the summed-area table itself)
            _gskip = _fx.gray_sides(_gcomps, nonpaper, pad, GRAY_FIELD_COVER)
            if _gskip is None:
                # summed-area table: each strip's coverage is then four lookups instead of a scan
                npi = np.zeros((gh + 1, grid_w + 1), np.int32)
                np.cumsum(np.cumsum(N.view(nonpaper) != 0, axis=0, dtype=np.int32), axis=1, out=npi[1:, 1:])

            def _covered(x0, y0, x1, y1):
                x0, y0, x1, y1 = max(0, x0), max(0, y0), min(grid_w, x1), min(gh, y1)
                n_ = (x1 - x0) * (y1 - y0)
                if n_ <= 0:
                    return None                                        # off the grid: no evidence either way
                return int(npi[y1, x1] - npi[y0, x1] - npi[y1, x0] + npi[y0, x0]) / float(n_)
            for _gi, (area, m, off) in enumerate(_gcomps):
                if _gskip is not None:
                    if _gskip[_gi]:
                        continue
                else:
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
            gb = _fx.blur(np.asarray(lumimg, np.uint8), CEL_BLUR, True).astype(np.float64)   # TWIN: Pillow's GaussianBlur in C
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
            # TWIN: one maximum (the color classes, then black: already solid ink)
            painted = _fx.union((grid_w, gh), [masks[k_] for k_ in masks if k_ not in ("black", "tone", "_ink")]
                                + ([masks["black"]] if "black" in masks else []))
            # TWIN: the bands and the hatch lines in C (fastdecomp/cel.c, hatch.c), unless a grid does not match
            _cel = _fx.cel_regions(lumimg, hatch_mask, min_area_px, bands_lohi, (CEL_BLUR, CEL_MEDIAN, CEL_SPECK_AREA, CEL_FIELD_COVER))
            for bi, region in (_cel if _cel is not None else cel_regions(lumimg, hatch_mask, min_area_px, bands=bands_lohi)):
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
                    polys = _fx.uniform_hatch(region, angles, pitch_g * pmul, min_len_g)
                    if polys is None:
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
    if OUTLINE and _ink_c is not None:
        p["outline_lines"] = int(_ink_c[1][21])        # TWIN: drawn by the C pass above
    elif OUTLINE:
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
            _sk = _fx.skeleton_thin(N.bool_img(keep), min_len_out, K)   # TWIN: the thinning and the tracing in C (fastdecomp/skel.c)
            sk, _tot, _n = _sk if _sk is not None else _skeleton(N.bool_img(keep), ppg, min_len_out, method="thin")
            wf = _field(OUTLINE_WIDTH_PAGE)
            for _L, pts_g in sk:
                (pts,) = place([[(x, y) for x, y in pts_g]], (grid_w, gh), box)
                if len(pts) >= 2:
                    out.append((pts, [wf] * len(pts), Pen.FINELINER_2, PenColor.BLACK, None))
                    p["outline_lines"] += 1

    # the highlighter goes down before any pen: drawn later it would tint the pens (device model)
    if _fx.session is not None and K.SUBCELL_GEOMETRY:
        # TWIN: the grouping below and the extent run on the store (fastdecomp/store.c: rf_store_wash_first,
        # rf_store_extent -- the same order, the same values in the same scalar types); `out` leaves as store indices
        out, _ext = _fx.session.finish(out, Pen.HIGHLIGHTER_2, HL_SCALE, _W)
        if _ext is not None:
            p["extent"] = _ext
        _SKIN_HUE_OFFSET, _DARK_FIELD, _FLOW, _WHITE_FLOOR, _UP = 0.0, False, None, None, 1.0   # per picture
        return out, p, round(time.perf_counter() - t0, 3)
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


TWIN_CODE = _decompose_twin.__code__
