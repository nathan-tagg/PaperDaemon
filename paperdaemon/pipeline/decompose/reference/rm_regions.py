r"""Region budget -- "region dancing". Regions are discovered from the source, and each region is assigned a value:
how big is it; how unique is it compared to its peers; how well does it contrast; where on the canvas is it, how
dense is the detail in that area; how long is it. From there, there is a budget of regions. Less valuable regions
MUST merge into more valuable ones, until the picture is within budget. A decomposition that does not cross the
budget is untouched.

THE ENGINE IS NOT TOUCHED. This module runs the engine's own quantizer read-only (exactly as rm_paint.decompose
sets it up) to get the pieces the painter would fill, values them, merges the least valuable into the touching
neighbor nearest in color until the picture is within budget, and hands back the picture with the absorbed pixels
recolored to their new region's color, for the engine to draw the WASHES from. Ink (edges, black) and hatch are
taken from the engine's run on the ORIGINAL, so they never change with the budget (hatching must not change as
optimizations are found). A picture within budget returns None: nothing happens, bit for bit.

The value of a piece (log domain, one exponent per quality -- the knobs, untuned, round numbers):
  area       page px it covers
  contrast   mean Lab distance between its SOURCE pixels and the source pixels across its border -- a real yellow
             spot on a Van Gogh scores high; a cel the quantizer cut out of a smooth gradient (a purple dot
             that is not in the source) scores near zero, whatever its class color says
  rarity     how many pieces of the same class and size band the picture holds (a million alike: each cheap)
  density    pieces per DENSITY_CELL_PAGE square around it (busy area: each cheap)
  elongation bounding box over sqrt(area): strands and lines outrank blobs
Only the color classes are in the pool; black, tone and ink pieces are frozen (neither merged nor merged into),
mirroring the engine's own speck absorber. THE BUDGET COUNTS THE PIECES THAT WILL BE DRAWN: color pieces above the
engine's own absorb line (rmb_params.ABSORB_MAX_AREA grid px); the specks below it never become strokes and are
left to the engine. Merging goes in rounds (values recomputed each round), each round taking at most
ROUND_FRACTION of the drawable pool, the lowest values first, each into its nearest-color touching drawable color
neighbor; chains and mutual picks resolve by connected components.
"""
import math
import time

import numpy as np
from PIL import Image
from paperdaemon.pipeline.decompose.reference import _lazy

nd = _lazy.Module("scipy.ndimage")                   # SciPy loads on first use: the app reads this module, never runs it
coo_matrix = _lazy.function("scipy.sparse", "coo_matrix")
connected_components = _lazy.function("scipy.sparse.csgraph", "connected_components")

from paperdaemon.pipeline.decompose.reference import rm_paint as P
from paperdaemon.pipeline.decompose.reference import rmb_params as K

BUDGET = 100000           # color pieces at page size (100k regions at most)
KNOBS = dict(area=0.5, contrast=1.0, rarity=0.5, density=0.5, elong=0.5, contrast_floor=1.0)
DENSITY_CELL_PAGE = 50.0  # page px: the square in which "how busy is it here" is counted
ROUND_FRACTION = 0.3      # at most this share of the live pool merges in one round (then values are recomputed)
MAX_ROUNDS = 40


def engine_grid(src, w, h):
    """The engine's quantized class masks for this picture in this box, read-only: replicates the start of
    rm_paint.decompose (grid = source, the page upscale, white point, the per-picture gates) and resets the
    engine's per-picture globals exactly as decompose does. -> (small RGB at the grid, masks, ppg, (gw, gh))."""
    im = Image.open(src).convert("RGB")
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


def pieces(masks, grid):
    """The engine's pieces: 4-connected components of each class mask (rm_paint.components is 4-neighbor).
    -> (labels HxW int32 with -1 for no class, class index per piece, class names, frozen flag per class)."""
    gw, gh = grid
    labels = np.full((gh, gw), -1, np.int32)
    cls_of, names, frozen = [], [], []
    cross = nd.generate_binary_structure(2, 1)
    n = 0
    for ci, (k, m) in enumerate(masks.items()):
        a = np.asarray(m) > 0
        if a.ndim == 3:
            a = a.any(axis=2)
        lab, cnt = nd.label(a, structure=cross)
        if cnt:
            sel = lab > 0
            labels[sel] = lab[sel] + (n - 1)
            cls_of.extend([ci] * cnt)
            n += cnt
        names.append(P._kname(k))
        frozen.append(not (isinstance(k, tuple) and k[0] == "rgb"))
    return labels, np.array(cls_of, np.int32), names, np.array(frozen, bool)


def _stats(labels, lab_img, n):
    flat = labels.ravel()
    ok = flat >= 0
    idx = flat[ok]
    H, W = labels.shape
    area = np.bincount(idx, minlength=n).astype(np.float64)
    labf = lab_img.reshape(-1, 3)[ok]
    sum_lab = np.stack([np.bincount(idx, weights=labf[:, c], minlength=n) for c in range(3)], 1)
    where = np.nonzero(ok)[0]
    yy, xx = np.divmod(where, W)
    safe = np.maximum(area, 1.0)
    cx = np.bincount(idx, weights=xx, minlength=n) / safe
    cy = np.bincount(idx, weights=yy, minlength=n) / safe
    x0 = np.full(n, W, np.int64); np.minimum.at(x0, idx, xx)
    x1 = np.full(n, -1, np.int64); np.maximum.at(x1, idx, xx)
    y0 = np.full(n, H, np.int64); np.minimum.at(y0, idx, yy)
    y1 = np.full(n, -1, np.int64); np.maximum.at(y1, idx, yy)
    return area, sum_lab, cx, cy, (x1 - x0 + 1).astype(np.float64), (y1 - y0 + 1).astype(np.float64)


def _edges(labels, lab_img, n):
    """Every adjacent pixel pair that crosses a piece border, summed per unordered pair of pieces:
    -> (a, b, count, summed source dE). The dE is between the two SOURCE pixels, not the classes."""
    keys, des = [], []
    for a, b, la, lb in ((labels[:, :-1], labels[:, 1:], lab_img[:, :-1], lab_img[:, 1:]),
                         (labels[:-1, :], labels[1:, :], lab_img[:-1, :], lab_img[1:, :])):
        sel = (a != b) & (a >= 0) & (b >= 0)
        pa, pb = a[sel].astype(np.int64), b[sel].astype(np.int64)
        de = np.sqrt(((la[sel] - lb[sel]) ** 2).sum(axis=1))
        keys.append(np.minimum(pa, pb) * n + np.maximum(pa, pb))
        des.append(de)
    key = np.concatenate(keys)
    de = np.concatenate(des)
    uk, inv = np.unique(key, return_inverse=True)
    cnt = np.bincount(inv, minlength=len(uk)).astype(np.float64)
    sde = np.bincount(inv, weights=de, minlength=len(uk))
    return uk // n, uk % n, cnt, sde


def value_of(area_page, contrast, rarity, density, elong, knobs=KNOBS):
    """log value: a sum of exponent * log(quality)."""
    return (knobs["area"] * np.log(np.maximum(area_page, 1e-3))
            + knobs["contrast"] * np.log(contrast + knobs["contrast_floor"])
            - knobs["rarity"] * np.log(np.maximum(rarity, 1.0))
            - knobs["density"] * np.log(np.maximum(density, 1.0))
            + knobs["elong"] * np.log(np.maximum(elong, 1.0)))


def merge_to_budget(labels, cls_of, frozen_cls, lab_img, ppg, budget=BUDGET, knobs=KNOBS, log=None, cut_specks=True):
    """Rounds of merging. ROUND ONE, always: every color piece that will not be rendered -- at or below the engine's
    absorb line, rmb_params.ABSORB_MAX_AREA grid px -- is cut into its nearest-color touching drawable neighbor (if a heuristic says a region will not be
    rendered, it should be cut anyway). Then, while the DRAWABLE pool is over budget, the least valuable drawable pieces merge the same way.
    -> (final labels, report). The final labels are compressed (0..m-1); report["orig_of"] maps each final region to
    the original piece it is named after (its biggest member that was not itself absorbed, or its biggest member),
    report["frozen"] flags the final regions that are not color."""
    n = cls_of.size
    frozen = frozen_cls[cls_of]
    area0 = np.bincount(labels.ravel()[labels.ravel() >= 0], minlength=n).astype(np.float64)
    drawable0 = (~frozen) & (area0 > K.ABSORB_MAX_AREA)
    rep = dict(pieces=n, color_pieces=int((~frozen).sum()), drawable_pieces=int(drawable0.sum()), budget=budget, rounds=[], touched=False, specks_cut=0)
    cur, cur_cls, cur_frozen = labels, cls_of, frozen
    orig_of = np.arange(n)                       # final region -> the original piece it is named after
    for rnd in range(MAX_ROUNDS):
        t = time.time()
        m = cur_cls.size
        area, sum_lab, cx, cy, bw, bh = _stats(cur, lab_img, m)
        drawable = (~cur_frozen) & (area > K.ABSORB_MAX_AREA)
        pool = int(drawable.sum())
        a, b, cnt, sde = _edges(cur, lab_img, m)
        # the nearest-color touching DRAWABLE color neighbor of every color piece
        mean_lab = sum_lab / np.maximum(area, 1.0)[:, None]
        src = np.concatenate([a, b])
        dst = np.concatenate([b, a])
        ok = (~cur_frozen[src]) & drawable[dst]
        src, dst = src[ok], dst[ok]
        dcol = np.sqrt(((mean_lab[src] - mean_lab[dst]) ** 2).sum(axis=1))
        order = np.lexsort((dcol, src))
        src_s, dst_s = src[order], dst[order]
        first = np.ones(len(src_s), bool)
        first[1:] = src_s[1:] != src_s[:-1]
        target = np.full(m, -1, np.int64)
        target[src_s[first]] = dst_s[first]
        specks = (~cur_frozen) & (~drawable) & (target >= 0)
        if rnd == 0 and cut_specks and specks.any():
            pick = np.nonzero(specks)[0]             # round one: what will not be rendered goes, budget or not
            kind, cut = "specks", None
            rep["specks_cut"] = int(len(pick))
        else:
            if pool <= budget:
                break
            csum = np.bincount(a, weights=sde, minlength=m) + np.bincount(b, weights=sde, minlength=m)
            ccnt = np.bincount(a, weights=cnt, minlength=m) + np.bincount(b, weights=cnt, minlength=m)
            contrast = csum / np.maximum(ccnt, 1.0)
            # rarity and density are judged among the drawable pieces: a speck is not a dab's peer
            band = np.floor(np.log2(np.maximum(area, 1.0))).astype(np.int64)
            key2 = np.stack([cur_cls.astype(np.int64), band], 1)
            key2[~drawable] = -1
            _u, inv, counts = np.unique(key2, axis=0, return_inverse=True, return_counts=True)
            rarity = counts[inv.ravel()].astype(np.float64)
            cell = max(4.0, DENSITY_CELL_PAGE / ppg)
            gx, gy = (cx // cell).astype(np.int64), (cy // cell).astype(np.int64)
            hist = np.zeros((int(gy.max()) + 1, int(gx.max()) + 1))
            np.add.at(hist, (gy[drawable], gx[drawable]), 1.0)
            hist = nd.uniform_filter(hist, 3, mode="nearest")
            density = hist[gy, gx]
            elong = np.maximum(bw, bh) / np.sqrt(np.maximum(area, 1.0))
            value = value_of(area * ppg * ppg, contrast, rarity, density, elong, knobs)
            cand = np.nonzero((target >= 0) & drawable)[0]
            if not len(cand):
                break
            k = int(min(pool - budget, max(1, ROUND_FRACTION * pool)))
            pick = cand[np.argsort(value[cand], kind="stable")[:k]]
            kind, cut = "budget", round(float(value[pick].max()), 2)
        # resolve this round's merges: every node connected through a picked edge becomes one region
        g = coo_matrix((np.ones(len(pick)), (pick, target[pick])), shape=(m, m))
        ncomp, comp = connected_components(g, directed=False)
        picked = np.zeros(m, bool)
        picked[pick] = True
        # the region each component is named after: its biggest member that was not picked (there is one unless
        # the component is a cycle of picks), else its biggest member
        order2 = np.lexsort((-area, picked, comp))
        firstc = np.ones(m, bool)
        firstc[1:] = comp[order2][1:] != comp[order2][:-1]
        rep_node = np.empty(ncomp, np.int64)
        rep_node[comp[order2][firstc]] = order2[firstc]
        cur = np.where(cur >= 0, comp[np.maximum(cur, 0)], -1).astype(np.int32)
        cur_cls, cur_frozen, orig_of = cur_cls[rep_node], cur_frozen[rep_node], orig_of[rep_node]
        rep["rounds"].append(dict(kind=kind, drawable=pool, merged=int(len(pick)), secs=round(time.time() - t, 1), value_cut=cut))
        if log:
            log("  round %d (%s): %s drawable pieces, merged %s (%.1f s%s)" % (rnd + 1, kind, format(pool, ","), format(len(pick), ","), time.time() - t,
                                                                              "" if cut is None else "; value cut %.2f" % cut))
    m = cur_cls.size
    area_f = np.bincount(cur.ravel()[cur.ravel() >= 0], minlength=m).astype(np.float64)
    rep.update(touched=bool(rep["rounds"]), final_color_pieces=int((~cur_frozen).sum()),
               final_drawable_pieces=int(((~cur_frozen) & (area_f > K.ABSORB_MAX_AREA)).sum()), orig_of=orig_of, frozen=cur_frozen, cls=cur_cls)
    return cur, rep


def recolored(small, labels0, labels, rep):
    """The picture for the wash run: every pixel that was absorbed into another region takes that region's own
    color -- the mean SOURCE color of the pixels the region is named after (its original piece), so the region's
    class in the engine's eyes stays what it was. Every other pixel is the source pixel. -> PIL RGB."""
    rgb = np.asarray(small, np.uint8)
    out = rgb.copy()
    m = rep["cls"].size
    orig_of = rep["orig_of"]
    flat_final, flat_orig = labels.ravel(), labels0.ravel()
    ok = flat_final >= 0
    own = ok.copy()
    own[ok] = flat_orig[ok] == orig_of[flat_final[ok]]           # pixels of the piece each region is named after
    idx = flat_final[own]
    cnt = np.bincount(idx, minlength=m).astype(np.float64)
    rgbf = rgb.reshape(-1, 3)[own].astype(np.float64)
    mean = np.stack([np.bincount(idx, weights=rgbf[:, c], minlength=m) for c in range(3)], 1) / np.maximum(cnt, 1.0)[:, None]
    moved = ok & ~own
    out.reshape(-1, 3)[moved] = np.clip(mean[flat_final[moved]] + 0.5, 0, 255).astype(np.uint8)
    rep["recolored_px"] = int(moved.sum())
    return Image.fromarray(out)


def budgeted(src, w, h, budget=BUDGET, knobs=KNOBS, log=None, cut_specks=True):
    """The whole step: -> (picture for the wash run as PIL RGB, or None when no round ran; report). With
    cut_specks=False and a huge budget it only counts: the report carries pieces, color_pieces, drawable_pieces."""
    t = time.time()
    small, masks, ppg, grid = engine_grid(src, w, h)
    labels0, cls_of, names, frozen_cls = pieces(masks, grid)
    lab_img = P._lab_rows(np.asarray(small, np.uint8).reshape(-1, 3)).reshape(grid[1], grid[0], 3)
    t_q = time.time() - t
    labels, rep = merge_to_budget(labels0, cls_of, frozen_cls, lab_img, ppg, budget, knobs, log, cut_specks)
    rep.update(grid=list(grid), ppg=round(ppg, 3), classes=len(names), secs_quantize=round(t_q, 1), secs=round(time.time() - t, 1))
    if not rep["touched"]:
        return None, rep
    img = recolored(small, labels0, labels, rep)
    rep["secs"] = round(time.time() - t, 1)
    return img, rep
