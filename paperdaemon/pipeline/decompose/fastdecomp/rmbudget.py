r"""rm_model.budget_step with the work done once (stage "budget" of rm_model.run).

The reference calls rm_regions.budgeted twice: once with an unreachable budget and no speck round, only to count the
drawable pieces, and then -- when the picture is over budget -- again for the merge. Both calls run the same
engine_grid and the same pieces(); the counting call also runs a full merge round's statistics and borders before
its loop sees the pool within budget and stops. Here engine_grid and pieces() run once, the count is the counting
call's own arithmetic (the drawable pieces of the first round: color pieces above rmb_params.ABSORB_MAX_AREA, which is
also its final count, as no round runs), and the merge, when needed, is rm_regions.budgeted's own code on those
pieces -- with rm_regions' merge_to_budget and recolored, or (stage "merge") their C versions from rmfast.make_merge
(fastdecomp/merge.c). With the source already read (stage "decode": the C reader's RGB picture), engine_grid is
engine_grid_of below, rm_regions.engine_grid's own lines after its read. The picture handed back and the report values
rm_model.run reads (drawable_pieces, final_drawable_pieces, specks_cut, touched) are the reference's.
"""
import math
import time

import numpy as np
from PIL import Image


def engine_grid_of(P, K, im, w, h):
    r"""rm_regions.engine_grid on a picture already read as RGB (`im`, what its Image.open(src).convert("RGB") gives):
    its lines after that read, unchanged (a check compares the two functions' code)."""
    gw, gh = im.width, im.height
    up = 1.0
    if K.UPSCALE_TO_PAGE:
        f = min(float(w) / gw, float(h) / gh)
        f = min(f, K.UPSCALE_MAX, math.sqrt(K.UPSCALE_MAX_PX / float(gw * gh)))
        if f >= K.UPSCALE_MIN:
            up = f
            gw, gh = int(round(gw * f)), int(round(gh * f))
    ppg0 = min(float(w) / gw, float(h) / gh)
    margin = max(P.EDGE_MARGIN_PAGE, 2.5 * ppg0)
    ppg = min((w - 2 * margin) / gw, (h - 2 * margin) / gh)
    small = im.resize((gw, gh), Image.LANCZOS)
    if K.V69_WHITE_POINT:
        small, _wp = P.white_point(small)
    P._UP = up
    P._SKIN_HUE_OFFSET, _cast = P.skin_cast_offset(small)
    P._WHITE_FLOOR = P.white_floor(small)
    P._DARK_FIELD, _share, _big = P.dark_field(small)
    black_l = K.BLACK_L_FIELD if P._DARK_FIELD else P.BLACK_L
    try:
        masks, _cover = P.quantize(small, black_l=black_l, chroma_min=P.CHROMA_MIN, detail=1.0, ppg=ppg)
    finally:
        P._SKIN_HUE_OFFSET, P._DARK_FIELD, P._FLOW, P._WHITE_FLOOR, P._UP = 0.0, False, None, None, 1.0
    return small, masks, ppg, (gw, gh)


def budget_step(RG, P, K, source, w, h, budget, log=None, merge=None, picture=None):
    """-> (recolored picture or None, report), as rm_model.budget_step. merge: (merge_to_budget, recolored) to use in
    place of rm_regions' own; picture: the source already read as an RGB PIL image."""
    t = time.time()
    merge_fn, recolor_fn = merge or (RG.merge_to_budget, RG.recolored)
    if picture is not None:
        small, masks, ppg, grid = engine_grid_of(P, K, picture, w, h)
    else:
        small, masks, ppg, grid = RG.engine_grid(source, w, h)
    labels0, cls_of, names, frozen_cls = RG.pieces(masks, grid)
    n = cls_of.size
    frozen = frozen_cls[cls_of]
    flat = labels0.ravel()
    area0 = np.bincount(flat[flat >= 0], minlength=n).astype(np.float64)
    drawable = int(((~frozen) & (area0 > K.ABSORB_MAX_AREA)).sum())
    if drawable <= budget:
        return None, dict(pieces=n, color_pieces=int((~frozen).sum()), drawable_pieces=drawable, rounds=[], touched=False,
                          specks_cut=0, final_drawable_pieces=drawable)
    # rm_regions.budgeted, from its pieces on
    lab_img = P._lab_rows(np.asarray(small, np.uint8).reshape(-1, 3)).reshape(grid[1], grid[0], 3)
    t_q = time.time() - t
    labels, rep = merge_fn(labels0, cls_of, frozen_cls, lab_img, ppg, budget, RG.KNOBS, log, True)
    rep.update(grid=list(grid), ppg=round(ppg, 3), classes=len(names), secs_quantize=round(t_q, 1), secs=round(time.time() - t, 1))
    if not rep["touched"]:
        return None, rep
    img = recolor_fn(small, labels0, labels, rep)
    rep["secs"] = round(time.time() - t, 1)
    return img, rep
