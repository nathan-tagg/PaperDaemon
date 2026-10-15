/* black.c -- the black pass's decision for each piece of black_left (rm_paint.decompose, the loop over
 * components(black_left, 1, 0) after the covered-speck test), DECISION code: whether a piece is filled solid as ink,
 * or painted as a wash of its own mean color because it has no black core or because it is a mass.
 *
 * Per component of rmb_npops.components (label.c rf_components: info = area, x0, y0, width, height of its box; each
 * crop its box with a 1-pixel margin, 255 on its pixels, laid end to end), the Python's lines:
 *   per = rm_paint._outline(crop, crop width, crop height, 1.0)'s total length (outline.c: rf_outline's arithmetic,
 *     through rf_outline_length and a scratch per thread, so no chain is built and nothing allocated per piece);
 *   thick = ((2.0 * area) / per) * ppg, or 0.0 when per is 0;
 *   with the ink density (hist, cell): the crop's pixels inside the grid window (the crop clipped to the grid); core =
 *     their black count / their count (one float64 division); when core < core_min: length = (per / 2.0) * ppg (0.0
 *     when per is 0), the density read at the cell of (y0 + mean row, x0 + mean column) -- numpy's mean of the
 *     window-relative indices is their exact integer sum over the count, the cell Python's float // (rf_py_floordiv)
 *     truncated, at most the last row and column of hist -- and the piece has no core unless length >= line_min_len
 *     and density <= line_max_density;
 *   no core, or thick >= thick_min, with any pixel in the window: a wash of the mean color, each channel its exact sum
 *     over the count truncated (int() of numpy's float64 mean);
 *   otherwise a solid fill.
 * Pieces on all threads, each its own (every output is its piece's).
 * Identity: checked against the reference -- the model run on the reference pictures, every piece's decision and
 * color compared with the Python's own lines. */
#include <stdlib.h>
#include "rmfast.h"
#include "internal.h"

typedef struct {
    const int64_t *info; const uint8_t *crops; const int64_t *at; int32_t n; const uint8_t *skip;
    const uint8_t *black; const uint8_t *rgb; int32_t H, W;
    double ppg, thick_min; const double *hist; int32_t hh, hw; double cell, core_min, line_min_len, line_max_density;
    int8_t *action; int32_t *mrgb; int nt; int8_t *failed;     /* failed: one flag per thread */
    rf_outline_buf *ob;                                          /* one outline scratch per thread */
} blackjob;

static void black_worker(void *arg, int tid) {
    blackjob *J = (blackjob *)arg;
    for (int32_t t = tid; t < J->n; t += J->nt) {
        J->action[t] = 0;
        J->mrgb[3 * t] = J->mrgb[3 * t + 1] = J->mrgb[3 * t + 2] = 0;
        if (J->skip && J->skip[t]) continue;
        const int64_t *f = J->info + 5 * (size_t)t;
        int64_t area = f[0], bx = f[1], by = f[2], w = f[3], h = f[4], cw = w + 2, ch = h + 2;
        const uint8_t *crop = J->crops + J->at[t];
        double per = 0.0;
        if (rf_outline_length(crop, (int32_t)ch, (int32_t)cw, (int32_t)cw, (int32_t)ch, J->ob + tid, &per) < 0) { J->failed[tid] = 1; return; }
        double thick = per != 0.0 ? ((2.0 * (double)area) / per) * J->ppg : 0.0;
        /* the window: the crop clipped to the grid */
        int64_t x0 = bx - 1 > 0 ? bx - 1 : 0, y0 = by - 1 > 0 ? by - 1 : 0;
        int64_t x1 = bx - 1 + cw < J->W ? bx - 1 + cw : J->W, y1 = by - 1 + ch < J->H ? by - 1 + ch : J->H;
        int64_t nsel = 0, ncore = 0, sy = 0, sx = 0, s0 = 0, s1 = 0, s2 = 0;
        for (int64_t gy = y0; gy < y1; gy++) {
            const uint8_t *row = crop + (gy - (by - 1)) * cw;
            for (int64_t gx = x0; gx < x1; gx++) {
                if (!row[gx - (bx - 1)]) continue;
                size_t p = (size_t)gy * (size_t)J->W + (size_t)gx;
                nsel++;
                if (J->black) ncore += J->black[p] != 0;
                sy += gy - y0; sx += gx - x0;
                s0 += J->rgb[3 * p]; s1 += J->rgb[3 * p + 1]; s2 += J->rgb[3 * p + 2];
            }
        }
        int no_core = 0;
        if (J->hist && x1 > x0 && y1 > y0 && nsel) {
            double core = (double)ncore / (double)nsel;
            if (core < J->core_min) {
                double length = per != 0.0 ? (per / 2.0) * J->ppg : 0.0;
                double fy = rf_py_floordiv((double)y0 + (double)sy / (double)nsel, J->cell);
                double fx = rf_py_floordiv((double)x0 + (double)sx / (double)nsel, J->cell);
                /* both are >= 0 (a window start plus a mean index, over a cell >= 4); int() truncates */
                int64_t iy = fy < 0.0 ? 0 : (fy > (double)J->hh ? (int64_t)J->hh : (int64_t)fy);
                int64_t ix = fx < 0.0 ? 0 : (fx > (double)J->hw ? (int64_t)J->hw : (int64_t)fx);
                if (iy > J->hh - 1) iy = J->hh - 1;
                if (ix > J->hw - 1) ix = J->hw - 1;
                double dens = J->hist[(size_t)iy * (size_t)J->hw + (size_t)ix];
                no_core = !(length >= J->line_min_len && dens <= J->line_max_density);
            }
        }
        if ((no_core || thick >= J->thick_min) && nsel) {
            J->action[t] = no_core ? 1 : 2;
            J->mrgb[3 * t] = (int32_t)((double)s0 / (double)nsel);
            J->mrgb[3 * t + 1] = (int32_t)((double)s1 / (double)nsel);
            J->mrgb[3 * t + 2] = (int32_t)((double)s2 / (double)nsel);
        } else {
            J->action[t] = 3;
        }
    }
}

/* -> 0, -1 out of memory, -2 a density grid with no cells. action per piece: 0 skipped (skip[t]), 1 a no-core wash, 2 a
 * mass wash (mrgb its color), 3 a solid fill. black and hist may be NULL (no ink density: no core test). */
RF_API int32_t rf_black_pieces(const int64_t *info, const uint8_t *crops, int32_t n, const uint8_t *skip, const uint8_t *black,
                               const uint8_t *rgb, int32_t H, int32_t W, double ppg, double thick_min, const double *hist, int32_t hh,
                               int32_t hw, double cell, double core_min, double line_min_len, double line_max_density, int8_t *action,
                               int32_t *mrgb) {
    if (n <= 0) return 0;
    if (hist && (hh <= 0 || hw <= 0 || !(cell > 0.0))) return -2;     /* not an ink density the painter makes */
    int64_t *at = (int64_t *)malloc(sizeof(int64_t) * (size_t)n);
    int nt = rf_threads();
    if (nt > n) nt = n;
    if (nt < 1) nt = 1;
    int8_t *failed = (int8_t *)calloc((size_t)nt, 1);
    rf_outline_buf *ob = (rf_outline_buf *)calloc((size_t)nt, sizeof(rf_outline_buf));
    if (!at || !failed || !ob) { free(at); free(failed); free(ob); return -1; }
    int64_t off = 0;
    for (int32_t t = 0; t < n; t++) { at[t] = off; off += (info[5 * (size_t)t + 4] + 2) * (info[5 * (size_t)t + 3] + 2); }
    blackjob J = {info, crops, at, n, skip, black, rgb, H, W, ppg, thick_min, hist, hh, hw, cell, core_min, line_min_len, line_max_density,
                  action, mrgb, nt, failed, ob};
    rf_parallel(nt, black_worker, &J);
    int bad = 0;
    for (int k = 0; k < nt; k++) { bad |= failed[k]; rf_outline_buf_free(ob + k); }
    free(at); free(failed); free(ob);
    return bad ? -1 : 0;
}
