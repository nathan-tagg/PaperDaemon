/* model.c -- rm_model.decompose(source, width, budget) as one call: from the source's bytes (or its RGB pixels), the
 * width and the budget to the strokes the lossless pass keeps (DECISION code: the order of the stages and what each
 * hands the next; every stage is its own file's).
 *
 * The Python's steps (rm_model.run with every C stage on, the painter as rm_paint.decompose with its defaults: detail
 * 1, chroma_min CHROMA_MIN, tone on, shade SHADE_BUDGET, no grid_max; and the parameters the painter runs with: no page
 * upscale, no white point, no white floor, the contour pass on the ink ridge):
 *   the source read as Pillow reads it (decode.c, jpeg.c); the box: width x max(1, round(width * H / W));
 *   the painter (painter_run below): the grid is the source; ppg0 = min(w / W, h / H), margin = max(EDGE_MARGIN_PAGE,
 *     2.5 ppg0), ppg = min((w - 2 margin) / W, (h - 2 margin) / H), the box inset by the margin at the origin; the dark
 *     field (stats.c) decides black_l; quantize (palette.c); Pillow's L; the ridge (xdog.c, sigma XDOG_SIGMA_REF * W /
 *     340 as float, k 1.6, tau 0.985); the body (painter.c); the end: washes grouped first, the extent (store.c).
 *     skin_cast_offset and the flow field's coherence feed only the painter's report (its hue offset is read by the soft
 *     edges and the flesh gate of classify, neither of which the painter runs) and are not computed;
 *   the region budget (rmbudget.budget_step): the first run's quantized masks (the budget's own engine_grid makes the
 *     same call), their pieces (regions.c), the drawable count; over the budget the merge rounds and the recolored
 *     picture (merge.c);
 *   when the budget touched the picture, the painter again on the recolored picture, then the seam (store.c
 *     rf_store_seam) in the frame of the first run's extent: each bound rounded to one decimal as the Python holds it
 *     (CPython's round for a Python float, numpy's x * 10, rint, / 10 for a numpy float64 or float32, in that type),
 *     floored or ceiled, 4 px out;
 *   the lossless pass (store.c rf_store_prune_join: radius 50, the wash eps, 4000 points).
 * Equal keys: the palette step sorts its colors as numpy.argsort does on this machine (npsort.c), and numpy orders
 * equal counts by the SIMD sort its dispatch picks for the CPU. The output is identical to the reference on the SAME
 * machine; two machines at different SIMD levels can order such ties differently, and so can the reference itself.
 * A single fixed tie order would make the output the same on every machine, once the Python reference is retired.
 * Inputs are validated here once: the picture's sides (decode.c's limits), the width (at least 1, at most 2^20), every
 * float of the parameters finite, the box wider and taller than its margins (ppg > 0; the reference raises later for
 * ppg 0 and has no meaning below it).
 * Identity: every corpus picture through this entry, each in its own process, against the reference corpus; the C
 * calls one picture makes, and the strokes strictly against the pure-Python model's; and sources the corpus lacks
 * (JPEG, palette, gray, alpha). */
#include <float.h>
#include <math.h>
#include <stdlib.h>
#include <string.h>
#include "rmfast.h"
#include "internal.h"

static int finite_d(double x) { return x >= -DBL_MAX && x <= DBL_MAX; }
static double py_min(double a, double b) { return b < a ? b : a; }
static double py_max(double a, double b) { return b > a ? b : a; }

/* CPython's round(x, 1) of a finite double: the double nearest the correctly rounded one-decimal value (ties to an
 * even last digit), by exact comparisons of x with k / 10 and (2k + 1) / 20 through fma */
static double py_round1(double x) {
    double k = floor(x * 10.0);                               /* within one of floor(10 x): two corrections at most */
    for (int i = 0; i < 2 && fma(x, 10.0, -k) < 0.0; i++) k -= 1.0;                  /* k / 10 <= x exactly */
    for (int i = 0; i < 2 && fma(x, 10.0, -(k + 1.0)) >= 0.0; i++) k += 1.0;         /* x < (k + 1) / 10 exactly */
    double s = fma(x, 20.0, -(2.0 * k + 1.0));               /* the sign of x - (2k + 1) / 20, exactly */
    if (s > 0.0 || (s == 0.0 && fmod(k, 2.0) != 0.0)) k += 1.0;
    return k / 10.0;
}

/* round(v, 1) in the scalar type v has in the Python (store.c's kinds) */
static double round1_kind(double v, uint8_t kind) {
    if (kind == RF_KIND_F32) { float y = (float)v * 10.0f; y = rintf(y); return (double)(y / 10.0f); }
    if (kind == RF_KIND_F64) { double y = v * 10.0; y = rint(y); return y / 10.0; }
    return py_round1(v);
}

int rf_model_params_ok(const rf_model_params *M) {
    const double v[] = {M->edge_margin_page, M->black_l, M->black_l_field, M->dark_field_min_cover, M->dark_field_min_region,
                        M->xdog_sigma_ref, M->xdog_k, M->xdog_tau, M->xdog_ink, M->knobs[0], M->knobs[1], M->knobs[2], M->knobs[3],
                        M->knobs[4], M->knobs[5], M->absorb_max_area, M->density_cell_page, M->round_fraction, M->wash_eps,
                        M->pass_radius, M->pass_radius_w, M->origin_x, M->origin_y};
    for (size_t i = 0; i < sizeof(v) / sizeof(v[0]); i++) if (!finite_d(v[i])) return 0;
    return rf_ink_params_ok(&M->ink) && rf_quant_params_ok(&M->quant) && M->budget_max_rounds >= 0 && M->pass_max_points >= 1;
}

typedef struct {
    int32_t nk, *keys; uint8_t **planes; int64_t *counts;      /* the quantized masks (palette.c) */
    int32_t *order, n;                                          /* the run's strokes, washes first */
    double ext[4]; uint8_t kind[4]; int has_ext;
    double ppg;
    /* what the painter's params report: the dark field (as rm_paint.dark_field returns it), black_l, the ridge's
     * pixels, the body's report and its final class keys */
    int32_t dark_on, nf, *fkeys;
    double dark_share, dark_big, black_l, rep[RF_BODY_REP];
    int64_t ridge_px;
} run_t;

static void run_free(run_t *R) {
    if (R->planes) for (int32_t i = 0; i < R->nk; i++) rf_free(R->planes[i]);
    rf_free(R->planes); rf_free(R->keys); rf_free(R->counts); free(R->order); rf_free(R->fkeys);
    memset(R, 0, sizeof(*R));
}

/* progress, in thousandths of the whole decompose. The stages' shares follow where the time goes (measured on the
 * corpus: the painter run about half, the second painter run for the washes, when the budget asks for one, about a
 * third, the final pass the rest); within a run, rf_prog_at marks the painter's own stages. Reporting only: nothing
 * reads it back. */
static volatile int32_t g_prog = 0;
static double g_base = 0.0, g_span = 0.0;

static void prog_set(double whole) {
    int32_t v = (int32_t)(whole * 1000.0 + 0.5);
    if (v < 0) v = 0;
    if (v > 1000) v = 1000;
    if (v > g_prog) g_prog = v;                      /* never backwards */
}

static void prog_span(double base, double span) { g_base = base; g_span = span; prog_set(base); }

void rf_prog_at(double f) { prog_set(g_base + g_span * f); }

RF_API int32_t rf_progress(void) { return g_prog; }

RF_API void rf_progress_reset(void) { g_prog = 0; }

/* the painter on an H x W RGB picture into a w x h box -> 0, -1 out of memory, -2 refused by a stage, -4 the box no
 * wider or taller than its margins */
static int32_t painter_run(rf_store *S, const rf_model_params *M, const uint8_t *rgb, int32_t H, int32_t W, int32_t w, int32_t h,
                          run_t *R, double *prof) {
    memset(R, 0, sizeof(*R));
    size_t N = (size_t)H * (size_t)W;
    double ppg0 = py_min((double)w / W, (double)h / H);
    double margin = py_max(M->edge_margin_page, 2.5 * ppg0);
    double ppg = py_min(((double)w - 2 * margin) / W, ((double)h - 2 * margin) / H);
    if (!(ppg > 0.0)) return -4;
    R->ppg = ppg;
    int32_t on = 0; double share = 0.0, big = 0.0;
    double t = rf_now();
    if (rf_dark_field(rgb, H, W, M->black_l, M->dark_field_min_cover, M->dark_field_min_region, &on, &share, &big) != 0) return -1;
    int dark = share >= M->dark_field_min_cover && on;
    double black_l = dark ? M->black_l_field : M->black_l;
    R->dark_on = dark; R->dark_share = share; R->dark_big = share >= M->dark_field_min_cover ? big : 0.0; R->black_l = black_l;
    rf_quant_params Q = M->quant;
    Q.black_l = black_l; Q.ppg = ppg; Q.detail = M->ink.detail;
    prof[0] = rf_now() - t;
    rf_prog_at(0.01);
    t = rf_now();
    int32_t nk = rf_quantize(rgb, H, W, &Q, &R->keys, &R->planes, &R->counts);
    prof[1] = rf_now() - t;
    if (nk < 0) return nk;
    rf_prog_at(0.22);
    t = rf_now();
    R->nk = nk;
    int32_t rc = -1;
    uint8_t *lum = (uint8_t *)malloc(N ? N : 1), *ridge = (uint8_t *)malloc(N ? N : 1);
    int32_t *kinds = (int32_t *)malloc(sizeof(int32_t) * (size_t)nk), *rgbs = (int32_t *)malloc(sizeof(int32_t) * 3 * (size_t)nk);
    int32_t *order = NULL, n = 0, *fkeys = NULL, nf = 0;
    if (!lum || !ridge || !kinds || !rgbs) goto done;
    for (size_t p = 0; p < N; p++)                                     /* Pillow's L */
        lum[p] = (uint8_t)(((uint32_t)rgb[3 * p] * 19595u + (uint32_t)rgb[3 * p + 1] * 38470u + (uint32_t)rgb[3 * p + 2] * 7471u + 0x8000u) >> 16);
    double sigma = (M->xdog_sigma_ref * W) / 340.0;
    int64_t rcount = 0;
    if (rf_xdog_ridge(rgb, H, W, (float)sigma, (float)(sigma * M->xdog_k), M->xdog_tau, M->xdog_ink, ridge, &rcount) != 0) goto done;
    R->ridge_px = rcount;
    for (int32_t i = 0; i < nk; i++) {
        kinds[i] = R->keys[4 * i];
        rgbs[3 * i] = R->keys[4 * i + 1]; rgbs[3 * i + 1] = R->keys[4 * i + 2]; rgbs[3 * i + 2] = R->keys[4 * i + 3];
    }
    prof[2] = rf_now() - t;
    rf_prog_at(0.26);
    rf_ink_params I = M->ink;
    I.ppg = ppg;
    I.x0 = M->origin_x + margin; I.y0 = M->origin_y + margin;
    I.x1 = (M->origin_x + w) - margin; I.y1 = (M->origin_y + h) - margin;
    rf_head_params Hp = M->head;
    Hp.black_l = black_l;
    double *rep = R->rep;
    int32_t r = rf_painter_body(S, &I, &Hp, H, W, nk, kinds, rgbs, (const uint8_t *const *)R->planes, rgb, lum, ridge, &order, &n, &fkeys,
                               &nf, rep);
    if (r != 0) { rc = r; goto done; }
    R->fkeys = fkeys; R->nf = nf; fkeys = NULL;
    prof[3] = rep[19]; prof[4] = rep[20]; prof[5] = rep[21];
    t = rf_now();
    R->order = (int32_t *)malloc(sizeof(int32_t) * (size_t)(n > 0 ? n : 1));
    if (!R->order) goto done;
    int32_t g = rf_store_wash_first(S, order, n, M->ink.tool_hl, R->order);
    if (g == -2) { rc = -2; goto done; }
    if (g < 0) goto done;
    R->n = n;
    R->has_ext = n > 0 && rf_store_extent(S, R->order, n, M->ink.tool_hl, M->ink.hl_scale, M->ink.pen_scale, R->ext, R->kind);
    prof[6] = rf_now() - t;
    rf_prog_at(1.0);
    rc = 0;
done:
    free(lum); free(ridge); free(kinds); free(rgbs); rf_free(order); rf_free(fkeys);
    return rc;
}

/* the region budget on the first run's masks -> 0, -1 out of memory, -2 the merge's ppg 0; *recolored (malloc'd, H x W
 * x 3) when it touched the picture */
static int32_t budget_step(const rf_model_params *M, const run_t *R, const uint8_t *rgb, int32_t H, int32_t W, int64_t budget,
                           uint8_t **recolored, rf_model_out *out) {
    *recolored = NULL;
    size_t N = (size_t)H * (size_t)W;
    int32_t rc = -1, nk = R->nk;
    int32_t *labels0 = (int32_t *)malloc(sizeof(int32_t) * (N ? N : 1)), *per = (int32_t *)calloc((size_t)(nk > 0 ? nk : 1), sizeof(int32_t));
    int32_t *cls_of = NULL, *labels = NULL, *cls = NULL, *r_kind = NULL;
    uint8_t *frozen_cls = (uint8_t *)malloc((size_t)(nk > 0 ? nk : 1)), *frozen = NULL;
    int64_t *area = NULL, *orig = NULL, *r_pool = NULL, *r_merged = NULL;
    double *lab = NULL, *r_cut = NULL, *r_secs = NULL;
    if (!labels0 || !per || !frozen_cls) goto done;
    if (rf_pieces((const uint8_t *const *)R->planes, nk, H, W, labels0, per) < 0) goto done;
    int64_t n = 0;
    for (int32_t c = 0; c < nk; c++) { n += per[c]; frozen_cls[c] = R->keys[4 * c] != 2; }
    if (n > INT32_MAX) goto done;
    cls_of = (int32_t *)malloc(sizeof(int32_t) * (size_t)(n > 0 ? n : 1));
    area = (int64_t *)calloc((size_t)(n > 0 ? n : 1), sizeof(int64_t));
    if (!cls_of || !area) goto done;
    { int64_t k = 0; for (int32_t c = 0; c < nk; c++) for (int32_t t = 0; t < per[c]; t++) cls_of[k++] = c; }
    for (size_t p = 0; p < N; p++) if (labels0[p] >= 0 && labels0[p] < n) area[labels0[p]]++;
    int64_t drawable = 0;
    for (int64_t p = 0; p < n; p++) drawable += !frozen_cls[cls_of[p]] && (double)area[p] > M->absorb_max_area;
    out->drawable = drawable; out->final_drawable = drawable; out->specks_cut = 0; out->touched = 0;
    if (drawable <= budget) { rc = 0; goto done; }
    int32_t R1 = M->budget_max_rounds + 1;
    labels = (int32_t *)malloc(sizeof(int32_t) * (N ? N : 1));
    orig = (int64_t *)malloc(sizeof(int64_t) * (size_t)(n + 1)); cls = (int32_t *)malloc(sizeof(int32_t) * (size_t)(n + 1));
    frozen = (uint8_t *)malloc((size_t)(n + 1)); r_kind = (int32_t *)calloc((size_t)R1, sizeof(int32_t));
    r_pool = (int64_t *)calloc((size_t)R1, sizeof(int64_t)); r_merged = (int64_t *)calloc((size_t)R1, sizeof(int64_t));
    r_cut = (double *)calloc((size_t)R1, sizeof(double)); r_secs = (double *)calloc((size_t)R1, sizeof(double));
    lab = (double *)malloc(sizeof(double) * 3 * (N ? N : 1));
    if (!labels || !orig || !cls || !frozen || !r_kind || !r_pool || !r_merged || !r_cut || !r_secs || !lab) goto done;
    rf_lab_rows(rgb, (int64_t)N, lab);
    int64_t counts[6] = {0};
    int32_t m = rf_merge_to_budget(labels0, H, W, cls_of, frozen_cls, (int32_t)n, lab, R->ppg, budget, M->knobs, M->absorb_max_area,
                                   M->density_cell_page, M->round_fraction, M->budget_max_rounds, 1, labels, orig, cls, frozen, r_kind,
                                   r_pool, r_merged, r_cut, r_secs, counts);
    if (m == -2) { rc = -2; goto done; }
    if (m < 0) goto done;
    out->drawable = counts[3]; out->specks_cut = counts[1]; out->final_drawable = counts[5];
    out->touched = counts[0] > 0;
    if (out->touched) {
        uint8_t *img = (uint8_t *)malloc(3 * (N ? N : 1));
        if (!img) goto done;
        if (rf_recolor(rgb, labels0, labels, H, W, orig, m, img) < 0) { free(img); goto done; }
        *recolored = img;
    }
    rc = 0;
done:
    free(labels0); free(per); free(cls_of); free(labels); free(cls); free(r_kind); free(frozen_cls); free(frozen); free(area); free(orig);
    free(r_pool); free(r_merged); free(lab); free(r_cut); free(r_secs);
    return rc;
}

/* the first run's report values into out (the painter's params): copies of its quantized keys and counts, its final
 * keys (moved) -> 0, -1 out of memory */
static int32_t report_out(run_t *R, rf_model_out *out) {
    out->ppg = R->ppg; out->dark_on = R->dark_on; out->dark_share = R->dark_share; out->dark_big = R->dark_big;
    out->black_l = R->black_l; out->ridge_px = R->ridge_px;
    memcpy(out->body_rep, R->rep, sizeof(out->body_rep));
    out->qkeys = (int32_t *)malloc(sizeof(int32_t) * 4 * (size_t)(R->nk > 0 ? R->nk : 1));
    out->qcounts = (int64_t *)malloc(sizeof(int64_t) * (size_t)(R->nk > 0 ? R->nk : 1));
    if (!out->qkeys || !out->qcounts) return -1;
    memcpy(out->qkeys, R->keys, sizeof(int32_t) * 4 * (size_t)R->nk);
    memcpy(out->qcounts, R->counts, sizeof(int64_t) * (size_t)R->nk);
    out->nq = R->nk;
    out->fkeys = R->fkeys; out->nf = R->nf; R->fkeys = NULL; R->nf = 0;
    return 0;
}

/* everything after validation: the model on an H x W RGB picture into the w x h box at the parameters' origin */
static int32_t model_core(rf_store *S, const uint8_t *rgb, int32_t H, int32_t W, int32_t w, int32_t h, int64_t budget,
                          const rf_model_params *M, rf_model_out *out) {
    out->w = w; out->h = h; out->grid_w = W; out->grid_h = H;
    run_t R1, R2;
    memset(&R2, 0, sizeof(R2));
    uint8_t *recol = NULL;
    int32_t *washes = NULL, *rest = NULL, *add = NULL, *combined = NULL;
    g_prog = 0;
    prog_span(0.0, 0.42);
    double t = rf_now();
    int32_t rc = painter_run(S, M, rgb, H, W, w, h, &R1, out->prof);
    out->secs[0] = rf_now() - t;
    if (rc != 0) { run_free(&R1); return rc; }
    out->engine_strokes = R1.n;
    if (report_out(&R1, out) != 0) { run_free(&R1); return -1; }
    t = rf_now();
    rc = budget_step(M, &R1, rgb, H, W, budget, &recol, out);
    out->secs[1] = rf_now() - t;
    if (rc != 0) goto done;
    prog_set(0.5);
    int32_t *final = R1.order, nfinal = R1.n;
    if (recol) {
        prog_span(0.5, 0.38);
        t = rf_now();
        rc = painter_run(S, M, recol, H, W, w, h, &R2, out->prof + 8);
        out->secs[2] = rf_now() - t;
        if (rc != 0) goto done;
        t = rf_now();
        rc = -1;
        washes = (int32_t *)malloc(sizeof(int32_t) * (size_t)(R2.n > 0 ? R2.n : 1));
        rest = (int32_t *)malloc(sizeof(int32_t) * (size_t)(R1.n > 0 ? R1.n : 1));
        if (!washes || !rest) goto done;
        int32_t nw = rf_store_select(S, R2.order, R2.n, 1, washes), nr = rf_store_select(S, R1.order, R1.n, 0, rest);
        /* the frame: the first run's extent as the Python rounds and holds it, or the box when it drew nothing */
        double b[4] = {M->origin_x, M->origin_y, M->origin_x + w, M->origin_y + h};
        if (R1.has_ext) for (int i = 0; i < 4; i++) b[i] = round1_kind(R1.ext[i], R1.kind[i]);
        double fx0 = floor(b[0]) - 4, fy0 = floor(b[1]) - 4, fx1 = ceil(b[2]) + 4, fy1 = ceil(b[3]) + 4;
        double fw = rint(fx1 - fx0), fh = rint(fy1 - fy0);
        if (!(fw >= 1.0 && fw < 2147483647.0 && fh >= 1.0 && fh < 2147483647.0)) { rc = -2; goto done; }
        int32_t np_ = rf_store_seam(S, R1.order, R1.n, washes, nw, fx0, fy0, (int32_t)fw, (int32_t)fh, M->wash_eps, &add);
        if (np_ < 0) goto done;
        out->seam_patches = np_;
        combined = (int32_t *)malloc(sizeof(int32_t) * (size_t)(nw + np_ + nr > 0 ? nw + np_ + nr : 1));
        if (!combined) goto done;
        memcpy(combined, washes, sizeof(int32_t) * (size_t)nw);
        if (np_) memcpy(combined + nw, add, sizeof(int32_t) * (size_t)np_);
        memcpy(combined + nw + np_, rest, sizeof(int32_t) * (size_t)nr);
        final = combined; nfinal = nw + np_ + nr;
        out->secs[3] = rf_now() - t;
        prog_set(0.92);
    }
    out->has_extent = R1.has_ext;
    for (int i = 0; i < 4; i++) { out->extent[i] = R1.ext[i]; out->extent_kind[i] = R1.kind[i]; }
    t = rf_now();
    rc = 0;
    if (nfinal > 0 && rf_store_prune_join(S, final, nfinal, M->wash_eps, M->pass_radius, M->pass_radius_w, M->pass_max_points, &out->res) != 0)
        rc = -1;
    out->secs[4] = rf_now() - t;
    if (rc == 0) prog_set(1.0);
done:
    run_free(&R1); run_free(&R2);
    free(recol); free(washes); free(rest); rf_free(add); free(combined);
    return rc;
}

/* rm_model.decompose: the box is `width` wide and as tall as the picture's aspect makes it. -> 0; -1 out of memory; -2
 * refused by a stage; -4 the box no wider or taller than its margins; -5 parameters out of range */
RF_API int32_t rf_decompose_rgb(rf_store *S, const uint8_t *rgb, int32_t H, int32_t W, int32_t width, int64_t budget,
                                const rf_model_params *M, rf_model_out *out) {
    memset(out, 0, sizeof(*out));
    if (H <= 0 || W <= 0 || H > (1 << 20) || W > (1 << 20) || width < 1 || width > (1 << 20) || budget < 0 || !rf_model_params_ok(M))
        return -5;
    double hh = rint(((double)width * H) / (double)W);       /* max(1, int(round(w * H / float(W)))) */
    int32_t h = hh < 1.0 ? 1 : (hh > (double)(1 << 30) ? (1 << 30) : (int32_t)hh);
    return model_core(S, rgb, H, W, width, h, budget, M, out);
}

/* rm_model.decompose_into: the w x h box at the parameters' origin, given (the painter keeps the picture's aspect and
 * centers it in the box). The same returns. */
RF_API int32_t rf_decompose_box_rgb(rf_store *S, const uint8_t *rgb, int32_t H, int32_t W, int32_t w, int32_t h, int64_t budget,
                                    const rf_model_params *M, rf_model_out *out) {
    memset(out, 0, sizeof(*out));
    if (H <= 0 || W <= 0 || H > (1 << 20) || W > (1 << 20) || w < 1 || w > (1 << 20) || h < 1 || h > (1 << 20) || budget < 0 ||
        !rf_model_params_ok(M))
        return -5;
    return model_core(S, rgb, H, W, w, h, budget, M, out);
}

/* a PNG or JPEG file's bytes read as Pillow reads them -> 0 with *rgb (malloc'd) and its size, -1 out of memory, -3 a
 * file the readers refuse */
static int32_t read_picture(const uint8_t *data, int64_t n, uint8_t **rgb, int32_t *H, int32_t *W) {
    *rgb = NULL;
    if (!data || n < 8) return -3;
    int32_t info[3] = {0, 0, 0};
    int png = memcmp(data, "\x89PNG\r\n\x1a\n", 8) == 0, jpg = data[0] == 0xff && data[1] == 0xd8;
    if (!png && !jpg) return -3;
    int32_t r = png ? rf_png_info(data, n, info) : rf_jpeg_info(data, n, info);
    if (r == -1) return -1;
    if (r != 0) return -3;
    if (info[0] <= 0 || info[1] <= 0 || info[0] > (1 << 20) || info[1] > (1 << 20)) return -3;
    size_t N = (size_t)info[0] * (size_t)info[1];
    uint8_t *px = (uint8_t *)malloc(3 * N);
    if (!px) return -1;
    r = png ? rf_png_rgb(data, n, px) : rf_jpeg_rgb(data, n, px);
    if (r != 0) { free(px); return r == -1 ? -1 : -3; }
    *rgb = px; *H = info[1]; *W = info[0];
    return 0;
}

/* the two entries from a PNG or JPEG file's bytes; -3 a file the readers refuse (the caller may read it with Pillow and
 * call the _rgb entry) */
RF_API int32_t rf_decompose(rf_store *S, const uint8_t *data, int64_t n, int32_t width, int64_t budget, const rf_model_params *M,
                            rf_model_out *out) {
    memset(out, 0, sizeof(*out));
    uint8_t *rgb; int32_t H = 0, W = 0;
    int32_t r = read_picture(data, n, &rgb, &H, &W);
    if (r != 0) return r;
    r = rf_decompose_rgb(S, rgb, H, W, width, budget, M, out);
    free(rgb);
    return r;
}

RF_API int32_t rf_decompose_box(rf_store *S, const uint8_t *data, int64_t n, int32_t w, int32_t h, int64_t budget, const rf_model_params *M,
                                rf_model_out *out) {
    memset(out, 0, sizeof(*out));
    uint8_t *rgb; int32_t H = 0, W = 0;
    int32_t r = read_picture(data, n, &rgb, &H, &W);
    if (r != 0) return r;
    r = rf_decompose_box_rgb(S, rgb, H, W, w, h, budget, M, out);
    free(rgb);
    return r;
}

/* everything an entry left in out: the pass's result and the report's arrays */
RF_API void rf_model_out_free(rf_model_out *out) {
    rf_result_free(&out->res);
    free(out->qkeys); free(out->qcounts); rf_free(out->fkeys);
    out->qkeys = NULL; out->qcounts = NULL; out->fkeys = NULL; out->nq = out->nf = 0;
}
