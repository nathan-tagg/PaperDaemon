r"""rm_model.decompose and rm_model.decompose_into as ONE C call each (fastdecomp/model.c rf_decompose, rf_decompose_box):
from the source's bytes, the width (or the box) and the budget, the C reads the picture, runs the painter, the region
budget, the painter again on the recolored picture, the seam and the lossless pass, and hands back the pass's strokes
and the values the painter's params report. The Python here only builds the constants once (the
painter's own, read from rm_paint / rmb_params / rm_regions / rm_lean, so a tuned constant reaches the C unchanged),
registers the black pens' styles in the store, makes the output's Python tuples with the reference's scalar types
(rmstore.Session._materialize: the output's own form) and the report.

decompose_box() also builds the painter's params from the C's report, every key with the value and type the painter
gives it, except the two that only a report reads and that cost a pass over the picture each: the skin cast and the
flow field's coherence (rm_model.decompose_into(report=True) runs the stage-by-stage path, which computes them).

decompose() and decompose_box() return None when the painter is not in the case the C reproduces (a switch in rmb_params changed: see
case()); rm_model then runs its stage-by-stage path. A file the C readers refuse is read by Pillow and its RGB pixels
handed to the same C entry (rf_decompose_rgb).
"""
import ctypes
import inspect
import io
import os

import numpy as np

import rmfast
import rmstore
from rmpaint_fast import Fast, _HeadParams, _InkParams

_D = ctypes.c_double


class _ModelParams(ctypes.Structure):
    """rmfast.h rf_model_params, field for field."""
    _fields_ = ([("ink", _InkParams), ("head", _HeadParams), ("quant", rmfast._QuantParams)]
                + [(n, _D) for n in ("edge_margin_page", "black_l", "black_l_field", "dark_field_min_cover", "dark_field_min_region",
                                     "xdog_sigma_ref", "xdog_k", "xdog_tau", "xdog_ink")]
                + [("knobs", _D * 6)]
                + [(n, _D) for n in ("absorb_max_area", "density_cell_page", "round_fraction", "wash_eps", "pass_radius", "pass_radius_w",
                                     "origin_x", "origin_y")]
                + [("budget_max_rounds", ctypes.c_int32), ("pass_max_points", ctypes.c_int32)])


class _ModelOut(ctypes.Structure):
    """rmfast.h rf_model_out, field for field."""
    _fields_ = ([("res", rmfast._Result)] + [(n, ctypes.c_int64) for n in ("drawable", "final_drawable", "specks_cut")]
                + [(n, ctypes.c_int32) for n in ("touched", "engine_strokes", "seam_patches", "w", "h", "has_extent")]
                + [("extent", _D * 4), ("extent_kind", ctypes.c_uint8 * 4), ("secs", _D * 5), ("prof", _D * 16)]
                + [(n, _D) for n in ("ppg", "dark_share", "dark_big", "black_l")]
                + [(n, ctypes.c_int32) for n in ("dark_on", "nq", "nf", "grid_w", "grid_h")] + [("ridge_px", ctypes.c_int64)]
                + [("qkeys", ctypes.POINTER(ctypes.c_int32)), ("qcounts", ctypes.POINTER(ctypes.c_int64)),
                   ("fkeys", ctypes.POINTER(ctypes.c_int32)), ("body_rep", _D * 64)])


def case(P, K, LA):
    """Whether the painter runs the case model.c reproduces: every switch at the value the C implements."""
    sig = inspect.signature(LA.xdog).parameters
    return (K.SUBCELL_GEOMETRY and K.INK_AS_FILL and not K.V69_FLOW_HATCH and not K.FILL_BACKSTOP and not K.HATCH_IN_COLOR
            and not P.OUTLINE_SOFT and P.OUTLINE_XDOG == P.XDOG_INK and K.V70_TRUE_COLOR and K.ZONE_AT_ONCE and K.COLOR_GROW_G <= 0
            and not K.TONE_RAMP_TO_COLOR and not K.UPSCALE_TO_PAGE and not K.V69_WHITE_POINT and not K.WHITE_FLOOR_ON
            and not K.DEVICE_CHROMA_MAX and K.CEL_DE > 0.0 and sig["k"].default == 1.6 and sig["tau"].default == 0.985)


def _setup(L):
    if getattr(L, "_single_ready", False):
        return
    vp, P8 = ctypes.c_void_p, ctypes.POINTER(ctypes.c_uint8)
    i32, i64, MP, MO = ctypes.c_int32, ctypes.c_int64, ctypes.POINTER(_ModelParams), ctypes.POINTER(_ModelOut)
    for f in (L.rf_decompose, L.rf_decompose_rgb, L.rf_decompose_box, L.rf_decompose_box_rgb):
        f.restype = i32
    L.rf_decompose.argtypes = [vp, P8, i64, i32, i64, MP, MO]
    L.rf_decompose_rgb.argtypes = [vp, P8, i32, i32, i32, i64, MP, MO]
    L.rf_decompose_box.argtypes = [vp, P8, i64, i32, i32, i64, MP, MO]
    L.rf_decompose_box_rgb.argtypes = [vp, P8, i32, i32, i32, i32, i64, MP, MO]
    L.rf_model_out_free.restype = None
    L.rf_model_out_free.argtypes = [MO]
    L._single_ready = True


def params(session, P, K, RG, LN, ink_rule, pass_radius, origin):
    """rf_model_params from the painter's constants: the decompose defaults (detail, tone, shade, black_l, chroma_min),
    the ink rule rm_model runs the painter with, the pass's radius, the box's origin."""
    d = {k: v.default for k, v in inspect.signature(P.decompose).parameters.items() if v.default is not inspect.Parameter.empty}
    fx = Fast(rmfast, P.N, P.Image, session, report=False)
    old = K.INK_CORE_MIN
    K.INK_CORE_MIN = ink_rule
    try:
        ink = fx._ink_params(P, 1.0, (0.0, 0.0, 1.0, 1.0), d["detail"], d["shade"], d["tone"], False)
    finally:
        K.INK_CORE_MIN = old
    head = Fast._head_params(P, d["black_l"])
    quant = rmfast.quant_params(P, K, P.CLUSTERS, d["black_l"], d["chroma_min"], d["detail"], 1.0)
    if ink is None or head is None:
        return None
    pi = inspect.signature(LN.prune_join).parameters
    M = _ModelParams(ink=ink, head=head, quant=quant, edge_margin_page=float(P.EDGE_MARGIN_PAGE), black_l=float(P.BLACK_L),
                     black_l_field=float(K.BLACK_L_FIELD), dark_field_min_cover=float(K.DARK_FIELD_MIN_COVER),
                     dark_field_min_region=float(K.DARK_FIELD_MIN_REGION), xdog_sigma_ref=float(P.XDOG_SIGMA_REF), xdog_k=1.6, xdog_tau=0.985,
                     xdog_ink=float(P.XDOG_INK), absorb_max_area=float(K.ABSORB_MAX_AREA), density_cell_page=float(RG.DENSITY_CELL_PAGE),
                     round_fraction=float(RG.ROUND_FRACTION), wash_eps=float(LN.WASH_EPS), pass_radius=float(pass_radius),
                     pass_radius_w=float(pi["radius_w"].default), origin_x=float(origin[0]), origin_y=float(origin[1]),
                     budget_max_rounds=max(0, int(RG.MAX_ROUNDS)), pass_max_points=int(pi["max_points"].default))
    for i, k in enumerate(("area", "contrast", "rarity", "density", "elong", "contrast_floor")):
        M.knobs[i] = float(RG.KNOBS[k])
    return M


def _call(source, box, budget, origin, P, K, RG, LN, LA, ink_rule, pass_radius, stages):
    """One C call: box ("width", width) is rm_model.decompose's, ("box", w, h) decompose_into's -> (strokes, report,
    the painter's report values), or None outside the C's case."""
    if not case(P, K, LA):
        return None
    S = rmstore.Session(rmfast)
    try:
        L = S.L
        _setup(L)
        M = params(S, P, K, RG, LN, ink_rule, pass_radius, origin)
        if M is None:
            return None
        out = _ModelOut()
        data = None
        if isinstance(source, (bytes, bytearray, memoryview)):
            data = bytes(source)
        elif isinstance(source, (str, os.PathLike)):
            with open(source, "rb") as f:
                data = f.read()
        P8 = ctypes.POINTER(ctypes.c_uint8)
        rc = -3
        if data is not None:
            buf = np.frombuffer(data, np.uint8)
            if box[0] == "width":
                rc = L.rf_decompose(S.S, buf.ctypes.data_as(P8), len(buf), int(box[1]), int(budget), ctypes.byref(M), ctypes.byref(out))
            else:
                rc = L.rf_decompose_box(S.S, buf.ctypes.data_as(P8), len(buf), int(box[1]), int(box[2]), int(budget), ctypes.byref(M),
                                        ctypes.byref(out))
        if rc == -3:                                          # a file the C readers refuse: Pillow reads it
            from PIL import Image
            rgb = np.ascontiguousarray(np.asarray(Image.open(source if data is None else io.BytesIO(data)).convert("RGB"), np.uint8))
            H, W = int(rgb.shape[0]), int(rgb.shape[1])
            if box[0] == "width":
                rc = L.rf_decompose_rgb(S.S, rgb.ctypes.data_as(P8), H, W, int(box[1]), int(budget), ctypes.byref(M), ctypes.byref(out))
            else:
                rc = L.rf_decompose_box_rgb(S.S, rgb.ctypes.data_as(P8), H, W, int(box[1]), int(box[2]), int(budget), ctypes.byref(M),
                                            ctypes.byref(out))
        try:
            if rc == -4:
                raise ValueError("the box is no wider or taller than its margins (%s)" % (box[1:],))
            if rc == -5:
                raise ValueError("a parameter of the model is out of range")
            if rc == -2:
                raise NotImplementedError("a stage refused the picture")
            if rc != 0:
                raise MemoryError("rf_decompose")
            S.sync_styles(P)
            kept = S._materialize(out.res)
            info = {"pruned": int(out.res.pruned), "joins": int(out.res.joins)}
            nq, nf = int(out.nq), int(out.nf)
            painted = dict(ppg=float(out.ppg), dark_on=bool(out.dark_on), dark_share=float(out.dark_share), dark_big=float(out.dark_big),
                           black_l=float(out.black_l), ridge_px=int(out.ridge_px), body_rep=list(out.body_rep), grid=(int(out.grid_w), int(out.grid_h)),
                           qkeys=np.ctypeslib.as_array(out.qkeys, shape=(4 * nq,)).tolist() if nq else [],
                           qcounts=np.ctypeslib.as_array(out.qcounts, shape=(nq,)).tolist() if nq else [],
                           fkeys=np.ctypeslib.as_array(out.fkeys, shape=(4 * nf,)).tolist() if nf else [])
        finally:
            L.rf_model_out_free(ctypes.byref(out))
    finally:
        S.close()
    secs = list(out.secs)
    w, h = int(out.w), int(out.h)
    rep = dict(width=w, height=h, budget=budget, ink_rule=ink_rule, fast=True, stages=stages, single_call=True)
    rep["secs_engine"] = round(secs[0], 1)
    rep["engine_strokes"] = int(out.engine_strokes)
    rep["secs_budget"] = round(secs[1], 1)
    rep.update(drawable_regions=int(out.drawable), regions_after=int(out.final_drawable), specks_cut=int(out.specks_cut),
               touched=bool(out.touched))
    if out.touched:
        rep["secs_engine_washes"] = round(secs[2], 1)
        rep["secs_seam"], rep["seam_patches"] = round(secs[3], 1), int(out.seam_patches)
    rep["secs_pass"] = round(secs[4], 1)
    rep.update(pruned=info["pruned"], joins=info["joins"], strokes=len(kept), washes=sum(1 for s in kept if LN.is_wash(s)),
               hatch=sum(1 for s in kept if LN.is_grain(s)))
    rep["ink"] = rep["strokes"] - rep["washes"] - rep["hatch"]
    rep["secs"] = round(sum(v for k_, v in rep.items() if k_.startswith("secs_")), 1)
    names = ("dark_field", "quantize", "ridge", "head", "zones", "ink_pass", "end")
    rep["c_profile"] = {"painter": dict(zip(names, (round(v, 3) for v in out.prof[0:7])))}
    if out.touched:
        rep["c_profile"]["painter_again"] = dict(zip(names, (round(v, 3) for v in out.prof[8:15])))
    painted["extent"] = ([round(rmstore._scalar(out.extent[i], out.extent_kind[i]), 1) for i in range(4)] if out.has_extent else None)
    if out.has_extent:
        rep["extent"] = [float(v) for v in painted["extent"]]
    else:
        rep["extent"] = [float(v) for v in (origin[0], origin[1], origin[0] + w, origin[1] + h)]
    return kept, rep, painted


def _key(code):
    """A class key of the C's lists (kind, r, g, b) as the painter's dict holds it."""
    return ("tone", "black", None, "_ink")[code[0]] if code[0] != 2 else ("rgb", (code[1], code[2], code[3]))


def painter_params(painted, P):
    """The painter's params dict (rm_paint.decompose's p, in its key order) from the C's report: every key with the
    painter's value and type, without skin_cast and flow_coherent (see the module's docstring)."""
    d = {k: v.default for k, v in inspect.signature(P.decompose).parameters.items() if v.default is not inspect.Parameter.empty}
    W, H = painted["grid"]
    ppg = painted["ppg"]
    # no page upscale and no white point in the C's case: _UP is 1.0, the white point None
    p = dict(grid=[W, H], ppg=round(ppg, 3), detail=d["detail"], white_point=None, upscale=round(1.0, 2),
             drawn=[round(W * ppg, 1), round(H * ppg, 1)])
    p["white_floor"] = None
    p["dark_field"] = dict(on=painted["dark_on"], dark=round(painted["dark_share"], 3), biggest=round(painted["dark_big"], 3))
    black_l = painted["black_l"]
    p["black_l"] = black_l
    q, c = painted["qkeys"], painted["qcounts"]
    keys = [_key(q[4 * i:4 * i + 4]) for i in range(len(c))]
    area = float(W * H)
    p["cover"] = {P._kname(k): round(c[i] / area, 3) for i, k in enumerate(keys) if k != "_ink"}
    p["black_l"], p["chroma_min"] = black_l, d["chroma_min"]
    p["ridge_px"] = painted["ridge_px"]
    p["components"] = {}
    f = painted["fkeys"]
    Fast.body_report(p, painted["body_rep"], [_key(f[4 * i:4 * i + 4]) for i in range(len(f) // 4)], ppg, black_l, P._kname, P.OUTLINE)
    if painted["extent"] is not None:
        p["extent"] = painted["extent"]
    return p


def decompose(source, width, budget, origin, P, K, RG, LN, LA, ink_rule, pass_radius, stages):
    """rm_model.decompose through rf_decompose -> (strokes, report), or None outside the C's case."""
    got = _call(source, ("width", width), budget, origin, P, K, RG, LN, LA, ink_rule, pass_radius, stages)
    return None if got is None else got[:2]


def decompose_box(source, w, h, budget, origin, P, K, RG, LN, LA, ink_rule, pass_radius, stages):
    """rm_model.decompose_into through rf_decompose_box -> (strokes, the painter's params, report), or None outside the
    C's case."""
    got = _call(source, ("box", w, h), budget, origin, P, K, RG, LN, LA, ink_rule, pass_radius, stages)
    if got is None:
        return None
    kept, rep, painted = got
    return kept, painter_params(painted, P), rep
