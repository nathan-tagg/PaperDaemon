/* The speck absorber -- rm_paint.absorb_specks with the picture given (the painter always gives it), decision for
 * decision (DECISION code). Identity: checked against the reference (every call of real runs through both) and the strict * model check.
 *
 *   prepare: per color key, in key order, its pixels set own_lab = key; its components (4-connected) at least
 *            `min_span` wide or tall and `min_area` big are KEPT and set lab_img = key; the rest of its pixels are
 *            WEAK. A later key overwrites an earlier one where masks overlap, as the Python's assignments do.
 *   run:     every zone's mean Lab (the source pixels where lab_img is that key, summed in raster order); then every
 *            4-connected component of the weak pixels: its own mean Lab (raster order), the zones within one pixel
 *            of it (3 x 3 dilation) as candidates in ascending key order, the nearest by squared Lab distance (the
 *            first on a tie). It joins that zone when it is at most `max_area` pixels or within `max_de`; a bigger
 *            component of more than one original key gives only the pixels within `max_de` of the zone.
 * The distance transform the Python computes before the loop is used only when no picture is given, so it is not
 * computed here. Components are independent (each writes only its own pixels), so their order does not matter. */
#include <math.h>
#include <stdatomic.h>
#include <stdlib.h>
#include <string.h>
#include "rmfast.h"
#include "internal.h"

/* prepare, on the keys' own grids (any non-zero byte set), the keys labeled on all threads: each key's weak pixels (its pieces under the span or area floor) go to a bitmap of its own, then the
 * grids are walked in row bands, keys in order within each pixel, so a later key overwrites an earlier one exactly
 * as the sequential version (and the Python's assignments) do. -> the weak pixel count, or -1 out of memory. */
typedef struct {
    const uint8_t *const *masks; int32_t nk, H, W, min_span; int64_t amin;
    uint8_t **weakbits;                       /* per key: N bits, set for its weak pixels (NULL: none) */
    int32_t *own_lab, *lab_img; uint8_t *weak;
    atomic_int next; atomic_int oom; int stage;
} prepjob;
#define PREP_ROWS 32

static void prep_worker(void *arg, int tid) {
    (void)tid;
    prepjob *J = (prepjob *)arg;
    size_t N = (size_t)J->H * J->W;
    if (J->stage == 0) {
        int32_t *lab = (int32_t *)malloc(sizeof(int32_t) * (N ? N : 1));
        uint8_t *keepc = NULL; size_t keep_cap = 0;
        if (!lab) { atomic_store(&J->oom, 1); return; }
        for (;;) {
            int32_t k = atomic_fetch_add(&J->next, 1);
            if (k >= J->nk) break;
            const uint8_t *m = J->masks[k];
            rf_comps C;
            int32_t n = rf_label4(m, J->H, J->W, lab, &C, 0);
            if (n < 0 || (n > 0 && (!C.x0 || !C.area))) { atomic_store(&J->oom, 1); rf_comps_free(&C); continue; }
            if ((size_t)n + 1 > keep_cap) {
                uint8_t *q = (uint8_t *)realloc(keepc, (size_t)n + 1);
                if (!q) { atomic_store(&J->oom, 1); rf_comps_free(&C); continue; }
                keepc = q; keep_cap = (size_t)n + 1;
            }
            int any = 0;
            for (int32_t c = 1; c <= n; c++) {
                int32_t span = C.y1[c] - C.y0[c] + 1, wspan = C.x1[c] - C.x0[c] + 1;
                if (wspan > span) span = wspan;
                keepc[c] = (span >= J->min_span) && (C.area[c] >= J->amin);
                any |= !keepc[c];
            }
            rf_comps_free(&C);
            if (!any) continue;
            uint8_t *bits = (uint8_t *)calloc((N + 7) / 8, 1);
            if (!bits) { atomic_store(&J->oom, 1); continue; }
            for (size_t i = 0; i < N; i++) if (m[i] && !keepc[lab[i]]) bits[i >> 3] |= (uint8_t)(1u << (i & 7));
            J->weakbits[k] = bits;
        }
        free(lab); free(keepc);
        return;
    }
    for (;;) {
        int32_t y0 = atomic_fetch_add(&J->next, PREP_ROWS);
        if (y0 >= J->H) break;
        int32_t y1 = y0 + PREP_ROWS < J->H ? y0 + PREP_ROWS : J->H;
        size_t i0 = (size_t)y0 * J->W, i1 = (size_t)y1 * J->W;
        for (size_t i = i0; i < i1; i++) { J->own_lab[i] = -1; J->lab_img[i] = -1; J->weak[i] = 0; }
        for (int32_t k = 0; k < J->nk; k++) {
            const uint8_t *m = J->masks[k];
            const uint8_t *bits = J->weakbits[k];
            for (size_t i = i0; i < i1; i++) {
                if (!m[i]) continue;
                J->own_lab[i] = k;
                if (bits && (bits[i >> 3] >> (i & 7)) & 1) J->weak[i] = 1;
                else J->lab_img[i] = k;
            }
        }
    }
}

RF_API int64_t rf_absorb_prepare_masks(const uint8_t *const *masks, int32_t nk, int32_t H, int32_t W, int32_t min_span, int64_t min_area,
                                       int32_t *own_lab, int32_t *lab_img, uint8_t *weak) {
    size_t N = (size_t)H * W;
    prepjob J;
    memset(&J, 0, sizeof(J));
    J.masks = masks; J.nk = nk; J.H = H; J.W = W; J.min_span = min_span; J.amin = min_area > 1 ? min_area : 1;
    J.own_lab = own_lab; J.lab_img = lab_img; J.weak = weak;
    J.weakbits = (uint8_t **)calloc((size_t)(nk > 0 ? nk : 1), sizeof(uint8_t *));
    if (!J.weakbits) return -1;
    atomic_init(&J.oom, 0);
    int nt = rf_threads();
    /* each labeling worker holds an N-sized label grid: at most 8 of them */
    int nl = nt < 8 ? nt : 8;
    J.stage = 0; atomic_init(&J.next, 0);
    rf_parallel(nl < nk ? nl : (nk > 0 ? nk : 1), prep_worker, &J);
    int64_t nw = -1;
    if (!atomic_load(&J.oom)) {
        int bands = (H + PREP_ROWS - 1) / PREP_ROWS;
        J.stage = 1; atomic_init(&J.next, 0);
        rf_parallel(nt < bands ? nt : (bands > 0 ? bands : 1), prep_worker, &J);
        nw = 0;
        for (size_t i = 0; i < N; i++) nw += weak[i];
    }
    for (int32_t k = 0; k < nk; k++) free(J.weakbits[k]);
    free(J.weakbits);
    return nw;
}

/* the absorber's output as the keys' grids: outs[k][i] = 255 where out_lab[i] == k, else 0 (row bands on all threads) */
typedef struct { const int32_t *lab; uint8_t *const *outs; int32_t nk, H, W; atomic_int next; } splitjob;

static void split_worker(void *arg, int tid) {
    (void)tid;
    splitjob *J = (splitjob *)arg;
    for (;;) {
        int32_t y0 = atomic_fetch_add(&J->next, PREP_ROWS);
        if (y0 >= J->H) break;
        int32_t y1 = y0 + PREP_ROWS < J->H ? y0 + PREP_ROWS : J->H;
        size_t i0 = (size_t)y0 * J->W, i1 = (size_t)y1 * J->W;
        for (int32_t k = 0; k < J->nk; k++) memset(J->outs[k] + i0, 0, i1 - i0);
        for (size_t i = i0; i < i1; i++) { int32_t z = J->lab[i]; if (z >= 0 && z < J->nk) J->outs[z][i] = 255; }
    }
}

RF_API void rf_split_labels(const int32_t *lab, int32_t nk, int32_t H, int32_t W, uint8_t *const *outs) {
    splitjob J;
    J.lab = lab; J.outs = outs; J.nk = nk; J.H = H; J.W = W;
    atomic_init(&J.next, 0);
    int nt = rf_threads(), bands = (H + PREP_ROWS - 1) / PREP_ROWS;
    rf_parallel(nt < bands ? nt : (bands > 0 ? bands : 1), split_worker, &J);
}

/* stats[0] = pixels kept out by the color guard, stats[1] = pixels whose label changed. -> the weak components
 * handled, or -1 when memory ran out (out_lab is then incomplete) */
RF_API int32_t rf_absorb_run(const int32_t *own_lab, const int32_t *lab_img, const uint8_t *weak, const double *lab_all, int32_t nk,
                             int32_t H, int32_t W, int64_t max_area, double max_de, double max_de2, int32_t *out_lab, int64_t *stats) {
    size_t N = (size_t)H * W;
    for (size_t i = 0; i < N; i++) out_lab[i] = lab_img[i] >= 0 ? lab_img[i] : own_lab[i];
    /* zone means: lab_all[lab_img == i].mean(axis=0) -- a sequential sum per channel in raster order */
    size_t nks = (size_t)(nk > 0 ? nk : 1);
    double *zs = (double *)calloc(nks * 3, sizeof(double)), *zone = (double *)calloc(nks * 3, sizeof(double));
    int64_t *zc = (int64_t *)calloc(nks, sizeof(int64_t));
    int32_t *lab = (int32_t *)malloc(sizeof(int32_t) * (N ? N : 1));
    uint8_t *mark = (uint8_t *)calloc(nks, 1);
    int32_t *cand = (int32_t *)malloc(sizeof(int32_t) * nks);
    rf_comps C;
    memset(&C, 0, sizeof(C));
    int32_t n = -1;
    if (!zs || !zone || !zc || !lab || !mark || !cand) goto done;
    for (size_t i = 0; i < N; i++) {
        int32_t z = lab_img[i];
        if (z < 0) continue;
        zs[3 * z] += lab_all[3 * i]; zs[3 * z + 1] += lab_all[3 * i + 1]; zs[3 * z + 2] += lab_all[3 * i + 2];
        zc[z]++;
    }
    for (int32_t z = 0; z < nk; z++)
        if (zc[z]) for (int c = 0; c < 3; c++) zone[3 * z + c] = zs[3 * z + c] / (double)zc[z];
    n = rf_label4(weak, H, W, lab, &C, 1);
    if (n < 0 || (n > 0 && (!C.area || !C.start || !C.pix))) { n = -1; goto done; }
    int64_t guarded = 0;
    for (int32_t c = 1; c <= n; c++) {
        const int32_t *px = C.pix + C.start[c];
        int64_t area = C.area[c];
        double own[3] = {0.0, 0.0, 0.0};
        for (int64_t t = 0; t < area; t++) { size_t p = (size_t)px[t]; own[0] += lab_all[3 * p]; own[1] += lab_all[3 * p + 1]; own[2] += lab_all[3 * p + 2]; }
        own[0] /= (double)area; own[1] /= (double)area; own[2] /= (double)area;
        /* the zones within one pixel (3 x 3) of the component */
        for (int64_t t = 0; t < area; t++) {
            int32_t p = px[t], y = p / W, x = p % W;
            for (int dy = -1; dy <= 1; dy++) {
                int32_t yy = y + dy;
                if (yy < 0 || yy >= H) continue;
                for (int dx = -1; dx <= 1; dx++) {
                    int32_t xx = x + dx;
                    if (xx < 0 || xx >= W) continue;
                    int32_t z = lab_img[(size_t)yy * W + xx];
                    if (z >= 0) mark[z] = 1;
                }
            }
        }
        int32_t nc = 0;
        for (int32_t z = 0; z < nk; z++) if (mark[z]) { cand[nc++] = z; mark[z] = 0; }
        if (!nc) continue;
        int32_t j = 0; double bd = 0.0;
        for (int32_t u = 0; u < nc; u++) {
            const double *zl = zone + 3 * cand[u];
            double d0 = zl[0] - own[0], d1 = zl[1] - own[1], d2 = zl[2] - own[2];
            double d = (d0 * d0 + d1 * d1) + d2 * d2;
            if (u == 0 || d < bd) { bd = d; j = u; }
        }
        if (!(area <= max_area || sqrt(bd) <= max_de)) continue;
        int32_t choice = cand[j];
        int guard = 0;
        if (area > max_area) {
            int32_t first = own_lab[px[0]];
            for (int64_t t = 1; t < area; t++) if (own_lab[px[t]] != first) { guard = 1; break; }
        }
        const double *zl = zone + 3 * choice;
        for (int64_t t = 0; t < area; t++) {
            size_t p = (size_t)px[t];
            if (guard) {
                double d0 = lab_all[3 * p] - zl[0], d1 = lab_all[3 * p + 1] - zl[1], d2 = lab_all[3 * p + 2] - zl[2];
                if (!((d0 * d0 + d1 * d1) + d2 * d2 <= max_de2)) { guarded++; continue; }
            }
            out_lab[p] = choice;
        }
    }
    int64_t changed = 0;
    for (size_t i = 0; i < N; i++) changed += out_lab[i] != own_lab[i];
    stats[0] = guarded; stats[1] = changed;
done:
    rf_comps_free(&C);
    free(lab); free(mark); free(cand); free(zs); free(zone); free(zc);
    return n;
}
