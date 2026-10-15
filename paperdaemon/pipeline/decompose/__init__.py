r"""THE MODEL, as one call -- the reference the fast decomposer must match: the fast decomposer has to produce
identical results to this Python one. The only parameters are the source image, the width (height is derived from the
source aspect ratio applied to the width), and the region budget, which defaults to 10k. The ink rule used here is
superior in every way to the plain one, so it is the method.

    strokes, report = rm_model.decompose(source, width, budget=10000)                # the model's own call
    strokes, params, secs = rm_model.decompose_into(source, w, h, origin=(x, y))     # the suite's call (a box)

What it is, stage by stage (nothing new here: the existing pieces, in the order they run):
  1. the painter on the original with the ink rule on (rm_paint.decompose; rmb_params.INK_CORE_MIN = INK_RULE) -- its
     ink (fineliner, marker) and hatch (pencil) are the drawing's ink and hatch;
  2. the region budget (rm_regions.budgeted): the painter's own quantized pieces, the unrendered specks cut, the least
     valuable drawable regions merged into their nearest-color neighbor until `budget` remain, absorbed pixels
     recolored; None when the picture is within budget;
  3. when touched, the painter again on the recolored picture (ink rule on) for the WASHES; the seam between the two
     runs patched (a pixel the first run washed that the second left to a class it does not wash gets its wash back);
  4. the lossless pass (rm_lean.prune_join, exact under both device rules, 50-px join search).
The box is width x round(width * source_h / source_w); the painter keeps the aspect and insets its edge margin.

THE C STAGES (fastdecomp\). The ring planner (rmb_geometry.plan/fill), the wash footprints, the seam, the pass, the
quantizer's cel pass, the speck absorber, the shade-zone loop, the region budget's pieces and statistics, components,
outlines and hole filling run in C -- fastdecomp\rmfast.dll through fastdecomp\rmfast.py -- each proven bit-identical
to the Python it replaces, and the whole model checked against a reference corpus. They are swapped in for the run and
restored afterwards. RM_FAST=0 in the environment runs the Python stages instead: that is the reference, and what the
reference corpus is built with. RM_FAST_STAGES picks the C stages (see STAGES); RMFAST_THREADS caps the threads the C
stages use (1 = single-threaded; the output does not change). With the stroke store (stage "store") the planner's strokes
stay in C until the pass is done, and the quantizer, the Lab conversion, the picture gates, the shade zones, the tonal
ink, the blurs, the ridge, the median cut, the black pass's speck test and the region budget's merge rounds run in C as
well. With every stage on (stage "single"), decompose() is ONE C call from the source's bytes to the pass's strokes
(fastdecomp/model.c through fastdecomp/rmsingle.py); Python makes only the output's tuples and the report.
"""
import io
import os
import sys
import time

import numpy as np
from PIL import Image

from paperdaemon.pipeline.decompose.reference import rm_lean as LN
from paperdaemon.pipeline.decompose.reference import rm_paint as P
from paperdaemon.pipeline.decompose.reference import rm_regions as RG
from paperdaemon.pipeline.decompose.reference import rmb_params as K

BUDGET = 10000
INK_RULE = 0.30        # rmb_params.INK_CORE_MIN while the model runs (the painter's default is 0: the old rule)
PASS = dict(radius=50.0)

FAST = os.environ.get("RM_FAST", "1") != "0"
_FAST = None            # the rmfast module once it loaded, False when it would not
# WHICH C STAGES (with FAST on): "all", or a comma list of
#   plan        the ring planner (rmb_geometry.plan/fill)
#   seam        the two-run seam (rm_model._seam)
#   pass        the lossless pass (rm_lean.prune_join)
#   mode        the quantizer's cel pass (rm_paint._mode_filter)
#   absorb      the speck absorber (rm_paint.absorb_specks)
#   zones       rm_paint.shadow_zones, all of it (fastdecomp\zones.c rf_shadow_zones; at first only its per-zone loop)
#   regions     rm_regions.pieces, _stats and _edges
#   components  rmb_npops.components
#   outline     rm_paint._outline
#   holes       rm_paint._fill_holes
#   reuse       one quantization per picture per run (fastdecomp\rmreuse.install)
#   rgbview     one shared array view of the painter's grid picture (fastdecomp\rmreuse.install_rgb_view)
#   engine      rm_paint.decompose's twin (fastdecomp\rmpaint_fast.py): its pocket loops in C, its mask unions as one
#               maximum; rm_paint.py itself is untouched and stays the reference
#   lab         rm_paint._lab_rows (sRGB -> Lab, every pixel) in C on all cores (fastdecomp\lab.c)
#   stats       rm_paint.skin_cast_offset and dark_field in C (fastdecomp\stats.c)
#   quant       rm_paint.quantize's per-pixel work in C (fastdecomp\quant.c); MEDIANCUT and the palette steps Python
#   budget      budget_step with engine_grid and the pieces computed once for the count and the merge
#               (fastdecomp\rmbudget.py; the same picture and report values)
#   store       (with plan, engine, seam and pass) the planner's strokes stay in C until the pass is done
#               (fastdecomp\store.c, rmstore.py): the zones' fills as one batch on all cores, the painter's wash
#               grouping and extent, the seam and the pass on the store; Python strokes made once, after the pass
#   merge       (with budget) the budget's merge rounds and recolor (rm_regions.merge_to_budget, recolored) in C
#               (fastdecomp\merge.c)
#   thin        rmb_lineart.thin (Zhang-Suen; the contour pass, the hatch bands) in C (fastdecomp\xdog.c rf_thin)
#   rank        rmb_npops.rank_ext (the masks' dilations, erosions, openings and closings) in C (fastdecomp\rank.c)
#   decode      (with store and engine) a PNG or JPEG source read in C (fastdecomp\decode.c, jpeg.c), Pillow's pixels; a file the
#               C reader refuses, or one Pillow does not read as RGB, is read by Pillow as before
#   single      decompose() as ONE C call (fastdecomp/model.c rf_decompose, fastdecomp/rmsingle.py): decode, the painter, budget,
#               the painter again, seam and pass all in C from the source's bytes; Python makes only the output's tuples and the
#               report. Outside the case the C reproduces (a switch in rmb_params changed) or with a log, run() below
# "plan,seam,pass" is the first hybrid: the planner, the seam and the pass only.
STAGES = os.environ.get("RM_FAST_STAGES", "all")


STAGE_NAMES = ("plan", "seam", "pass", "mode", "absorb", "zones", "regions", "components", "outline", "holes", "reuse", "rgbview", "engine",
               "store", "lab", "budget", "stats", "quant", "merge", "thin", "rank", "decode", "single")


def _stage(F, name):
    return bool(F) and (STAGES == "all" or name in [s.strip() for s in STAGES.split(",")])


def fast():
    """The C library's Python face (fastdecomp\rmfast.py) when it is wanted and loads, else None."""
    global _FAST
    if not FAST:
        return None
    if _FAST is None:
        try:
            here = os.path.join(os.path.dirname(os.path.abspath(__file__)), "fastdecomp")
            if here not in sys.path:
                sys.path.insert(0, here)
            import rmfast
            rmfast.lib()
            _FAST = rmfast
        except Exception as ex:
            import warnings
            warnings.warn("rmfast did not load (%s: %s); the Python stages run instead" % (type(ex).__name__, ex))
            _FAST = False
    return _FAST or None


def _frame(params, w, h, origin):
    x0, y0, x1, y1 = params.get("extent", (origin[0], origin[1], origin[0] + w, origin[1] + h))
    return (float(np.floor(x0)) - 4, float(np.floor(y0)) - 4, float(np.ceil(x1)) + 4, float(np.ceil(y1)) + 4)


def _seam(washes_m, rest, base_strokes, params, w, h, origin):
    """Every pixel the first run's washes paint (under the renderer's WASH_EPS fill) that the combined washes leave
    bare gets its first-run wash(es) back. -> (washes + patches + rest, how many came back).
    FOOTPRINT FORM: an earlier version rendered both drawings and read paper as L >= 250, which made the
    test depend on the pen rasterizer and the hatch; this one is the wash footprints alone, which is the question
    being asked and is what the C port (fastdecomp/seam.c) computes bit for bit."""
    from paperdaemon.pipeline.decompose.reference import rm_raster as RS
    fx0, fy0, fx1, fy1 = _frame(params, w, h, origin)
    W, H = int(round(fx1 - fx0)), int(round(fy1 - fy0))
    base_washes = [s for s in base_strokes if LN.is_wash(s) and len(s[0]) >= 2]
    A = np.zeros((H, W), np.uint8)
    for s in base_washes:
        RS.paint_wash(A, fx0, fy0, s[0], s[1], eps=LN.WASH_EPS)
    B = np.zeros((H, W), np.uint8)
    for s in washes_m:
        if LN.is_wash(s) and len(s[0]) >= 2:
            RS.paint_wash(B, fx0, fy0, s[0], s[1], eps=LN.WASH_EPS)
    gap = (A & ~B).ravel()
    if not gap.any():
        return list(washes_m) + list(rest), 0
    add = []
    for i, s in enumerate(base_washes):
        f = RS.wash_pixels(s[0], s[1], fx0, fy0, W, H, eps=LN.WASH_EPS)
        if len(f) and gap[f].any():
            add.append(i)
    return list(washes_m) + [base_washes[i] for i in add] + list(rest), len(add)


def budget_step(source, w, h, budget=BUDGET, log=None):
    """The region budget: a picture with `budget` or fewer drawable regions is UNTOUCHED
    (no speck round, no second run -- the painter's output after the pass); over it, rm_regions.budgeted.
    -> (recolored picture or None, report)."""
    _none, counts = RG.budgeted(source, w, h, budget=10 ** 9, cut_specks=False)
    if counts["drawable_pieces"] <= budget:
        counts["touched"] = False
        return None, counts
    return RG.budgeted(source, w, h, budget=budget, log=log)


def run(source, w, h, origin=(0.0, 0.0), budget=BUDGET, log=None, report=False, **engine):
    """The model on a w x h box at `origin` -> (strokes in rm_art's tuple form, in draw order; the first painter run's
    params; the report with the counts and the seconds of every stage).  `engine` keywords go to both painter runs
    (the suite passes none; the budget's grid assumes the painter's defaults). report=False: with the painter twin, the
    params values no stroke depends on (the flow field's coherence) are not computed."""
    from paperdaemon.pipeline.decompose.reference import rmb_geometry as G
    from paperdaemon.pipeline.decompose.reference import rmb_npops as N
    F = fast()
    rep = dict(width=int(w), height=int(h), budget=budget, ink_rule=INK_RULE, fast=bool(F),
               stages=[s for s in STAGE_NAMES if _stage(F, s)])
    old_ink, old_fill, old_mode, old_absorb, old_zones = K.INK_CORE_MIN, G.FAST, P._mode_filter, P.absorb_specks, P.shadow_zones
    K.INK_CORE_MIN = INK_RULE
    G.FAST = F.fill if _stage(F, "plan") else None
    # the C stages that replace a painter function do it here, for the run only (the painter's files are untouched)
    old_lab = P._lab_rows
    if _stage(F, "mode"):
        P._mode_filter = F.mode_filter
    if _stage(F, "lab"):
        P._lab_rows = F.make_lab_rows(P)
    old_quant = P.quantize
    if _stage(F, "quant"):              # before reuse, whose memo wraps the quantize it finds
        P.quantize = F.make_quantize(P, K, N)
    old_stats = None
    if _stage(F, "stats"):              # before rgbview, whose hook wraps the skin_cast_offset it finds
        fast_stats, old_stats = F.make_picture_stats(P, K)
        for k_, f_ in fast_stats.items():
            setattr(P, k_, f_)
    if _stage(F, "absorb"):
        P.absorb_specks = F.make_absorb_specks(P, K, N)
    if _stage(F, "zones"):
        P.shadow_zones = F.make_shadow_zones_c(P, K, N)
    old_components, old_outline, old_holes = N.components, P._outline, P._fill_holes
    if _stage(F, "components"):
        N.components = F.make_components(N)
    if _stage(F, "outline"):
        P._outline = F.make_outline(P, N)
    if _stage(F, "holes"):
        P._fill_holes = F.make_fill_holes(P, N, K)
    from paperdaemon.pipeline.decompose.reference import rmb_lineart as LA
    old_thin = LA.thin
    if _stage(F, "thin"):
        LA.thin = F.make_thin(LA)
    old_rank = N.rank_ext
    if _stage(F, "rank"):
        N.rank_ext = F.make_rank_ext(N)
    old_regions = None
    if _stage(F, "regions"):
        fast_regions, old_regions = F.make_region_stages(RG, P, N)
        for k_, f_ in fast_regions.items():
            setattr(RG, k_, f_)
    unreuse = unview = None
    engine_fn = P.decompose
    session = None
    if all(_stage(F, s) for s in ("store", "engine", "plan", "seam", "pass")) and K.SUBCELL_GEOMETRY:
        import rmstore
        session = rmstore.Session(F)
        G.FAST = session.fill
    if _stage(F, "engine"):
        import rmpaint_fast
        engine_fn = rmpaint_fast.twin(P, F, session, report)
    if _stage(F, "reuse"):
        import rmreuse
        unreuse = rmreuse.install(P, RG, N, K)
    if _stage(F, "rgbview"):
        import rmreuse
        unview = rmreuse.install_rgb_view(P, Image)
    try:
        t = time.time()
        # stage "decode": the source read in C (fastdecomp\decode.c, jpeg.c) when it is a PNG or JPEG the C readers take and the
        # painter is the twin with the store (it reads its source only as RGB pixels at their own size); the budget step
        # gets the same picture
        picture = None
        if _stage(F, "decode") and session is not None and P.OUTLINE_XDOG == P.XDOG_INK and not engine.get("grid_max"):
            got = F.make_decode()(source)
            # any mode whose L is the L of its RGB (Pillow's convert: L, P, 1, LA, RGBA and I;16 all are), as the twin's C
            # ridge takes L from the RGB picture where the reference's xdog converts the file to L
            if got is not None and got[1] in ("RGB", "L", "P", "1", "LA", "RGBA", "I;16"):
                picture = Image.fromarray(got[0])
        strokes, params, _s = engine_fn(source if picture is None else picture, w, h, origin=origin, **engine)
        rep["secs_engine"] = round(time.time() - t, 1)
        rep["engine_strokes"] = len(strokes)
        t = time.time()
        if _stage(F, "budget"):
            import rmbudget
            flat, rrep = rmbudget.budget_step(RG, P, K, source, w, h, budget, log, F.make_merge(RG, K) if _stage(F, "merge") else None, picture)
        else:
            flat, rrep = budget_step(source, w, h, budget=budget, log=log)
        rep["secs_budget"] = round(time.time() - t, 1)
        rep.update(drawable_regions=rrep["drawable_pieces"], regions_after=rrep.get("final_drawable_pieces", rrep["drawable_pieces"]),
                   specks_cut=rrep.get("specks_cut", 0), touched=flat is not None)
        if flat is not None:
            if session is not None and P.OUTLINE_XDOG == P.XDOG_INK and not engine.get("grid_max"):
                # the twin with the store takes the picture in memory: it reads the source only as RGB pixels at
                # their own size (its C ridge's case), and PNG is lossless -- the round trip below changes nothing
                src_m = flat
            else:
                src_m = io.BytesIO()
                flat.save(src_m, "PNG")
                src_m.seek(0)
            t = time.time()
            strokes_m, _pm, _s = engine_fn(src_m, w, h, origin=origin, **engine)
            rep["secs_engine_washes"] = round(time.time() - t, 1)
            t = time.time()
            if session is not None:
                combined, patches = session.seam(session.select(strokes_m, True), session.select(strokes, False), strokes,
                                                 _frame(params, w, h, origin), LN.WASH_EPS)
            else:
                washes = [s for s in strokes_m if LN.is_wash(s)]
                rest = [s for s in strokes if not LN.is_wash(s)]
                if _stage(F, "seam"):
                    combined, patches = F.seam(washes, rest, strokes, _frame(params, w, h, origin), LN.WASH_EPS)
                else:
                    combined, patches = _seam(washes, rest, strokes, params, w, h, origin)
            rep["secs_seam"], rep["seam_patches"] = round(time.time() - t, 1), patches
        else:
            combined = strokes
        t = time.time()
        if session is not None:
            kept, info = session.prune_join(combined, eps_out=LN.WASH_EPS, **PASS)
        else:
            kept, info = (F.prune_join if _stage(F, "pass") else LN.prune_join)(combined, eps_out=LN.WASH_EPS, **PASS)
        rep["secs_pass"] = round(time.time() - t, 1)
        rep.update(pruned=int(info["pruned"]), joins=int(info["joins"]), strokes=len(kept),
                   washes=sum(1 for s in kept if LN.is_wash(s)), hatch=sum(1 for s in kept if LN.is_grain(s)))
        rep["ink"] = rep["strokes"] - rep["washes"] - rep["hatch"]
        rep["secs"] = round(sum(v for k_, v in rep.items() if k_.startswith("secs_")), 1)
        rep["extent"] = [float(v) for v in params.get("extent", (origin[0], origin[1], origin[0] + w, origin[1] + h))]
        return kept, params, rep
    finally:
        K.INK_CORE_MIN = old_ink
        G.FAST = old_fill
        P._mode_filter, P.absorb_specks, P.shadow_zones = old_mode, old_absorb, old_zones
        P._lab_rows = old_lab
        N.components, P._outline, P._fill_holes = old_components, old_outline, old_holes
        LA.thin = old_thin
        N.rank_ext = old_rank
        if old_regions:
            for k_, f_ in old_regions.items():
                setattr(RG, k_, f_)
        if unreuse:
            unreuse()
        if unview:
            unview()
        if session is not None:
            session.close()
        P.quantize = old_quant          # after reuse's removal, which puts back the function it wrapped
        if old_stats:                   # after rgbview's removal, which puts back the function it wrapped
            for k_, f_ in old_stats.items():
                setattr(P, k_, f_)


def decompose(source, width, budget=BUDGET, origin=(0.0, 0.0), log=None):
    """The model's own call: the box is `width` wide and as tall as the picture's aspect makes it.
    -> (strokes in rm_art's tuple form, in draw order; report with the counts and the seconds of every stage)."""
    F = fast()
    if _stage(F, "single") and log is None and all(_stage(F, s) for s in STAGE_NAMES):
        # stage "single": the whole model in one C call (fastdecomp/model.c); None outside the case the C reproduces
        from paperdaemon.pipeline.decompose.reference import rmb_lineart as LA
        import rmsingle
        got = rmsingle.decompose(source, width, budget, origin, P, K, RG, LN, LA, INK_RULE, PASS["radius"],
                                 [s for s in STAGE_NAMES if _stage(F, s)])
        if got is not None:
            return got
    size = F.make_decode().size(source) if _stage(F, "decode") else None      # the PNG or JPEG header, read in C
    if size is None:
        im = Image.open(source).convert("RGB")
        size = im.size
    w = int(width)
    h = max(1, int(round(w * size[1] / float(size[0]))))
    kept, _params, rep = run(source, w, h, origin=origin, budget=budget, log=log)
    return kept, rep


def decompose_into(source, w, h, origin=(0.0, 0.0), budget=BUDGET, report=False, **engine):
    """The suite's call, in rm_paint.decompose's shape: a picture fitted into a w x h box whose top-left is `origin`
    -> (strokes, params, seconds).  `params` is the painter's (extent, drawn, ...) plus `params["model"]`, the report.
    With every stage on and no painter keywords this is ONE C call (stage "single": fastdecomp/model.c
    rf_decompose_box), its params built from the C's report without the two report-only values that cost a pass over
    the picture each (skin_cast, flow_coherent); report=True, painter keywords or other stages run run() below, which
    computes them."""
    t0 = time.perf_counter()
    F = fast()
    if _stage(F, "single") and not report and not engine and all(_stage(F, s) for s in STAGE_NAMES):
        from paperdaemon.pipeline.decompose.reference import rmb_lineart as LA
        import rmsingle
        got = rmsingle.decompose_box(source, int(w), int(h), budget, origin, P, K, RG, LN, LA, INK_RULE, PASS["radius"],
                                     [s for s in STAGE_NAMES if _stage(F, s)])
        if got is not None:
            kept, params, rep = got
            params["model"] = rep
            return kept, params, round(time.perf_counter() - t0, 3)
    kept, params, rep = run(source, int(w), int(h), origin=origin, budget=budget, report=True, **engine)
    params = dict(params)
    params["model"] = rep
    return kept, params, round(time.perf_counter() - t0, 3)


def save_strokes(path, strokes):
    """The reference corpus format: one .npz with the points (float32, n x 2), the per-stroke point counts, widths
    (float32), tools and colors as small integer codes -- everything the fast decomposer must reproduce."""
    from paperdaemon.pipeline.draw import Pen, PenColor
    counts = np.array([len(s[0]) for s in strokes], np.int32)
    pts = np.concatenate([np.asarray(s[0], np.float32).reshape(-1, 2) for s in strokes]) if strokes else np.zeros((0, 2), np.float32)
    widths = np.concatenate([np.asarray(s[1], np.float32) for s in strokes]) if strokes else np.zeros(0, np.float32)
    tools = np.array([int(s[2].value) for s in strokes], np.int16)
    colors = np.array([int(s[3].value) if hasattr(s[3], "value") else int(s[3]) for s in strokes], np.int16)
    rgba = np.array([list(s[4][:3]) if s[4] else [-1, -1, -1] for s in strokes], np.int16).reshape(-1, 3)
    np.savez_compressed(path, counts=counts, points=pts, widths=widths, tools=tools, colors=colors, rgba=rgba)


def load_strokes(path):
    z = np.load(path)
    from paperdaemon.pipeline.draw import Pen, PenColor
    out, i = [], 0
    for n, tool, color, rgb, k in zip(z["counts"].tolist(), z["tools"].tolist(), z["colors"].tolist(), z["rgba"].tolist(), range(len(z["counts"]))):
        pts = [tuple(p) for p in z["points"][i:i + n].tolist()]
        wid = z["widths"][i:i + n].tolist()
        out.append((pts, wid, Pen(tool), PenColor(color), (None if rgb[0] < 0 else tuple(rgb))))
        i += n
    return out
