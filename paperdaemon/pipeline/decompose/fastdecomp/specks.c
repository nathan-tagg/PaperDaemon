/* The black pass's covered-speck test (rm_paint.decompose, the loop over the components of black_left), DECISION code:
 * which black specks are left out because a color zone already paints them.
 *
 *   rf_any_nonzero:  covered_by_color -- zeros, then |= (mask != 0) for each color mask in turn: a pixel is 1 when any
 *                    mask is non-zero there (rows on all threads; an OR has no order).
 *   rf_speck_skip:   per component of rmb_npops.components (fastdecomp label.c rf_components: info = area, x0, y0,
 *                    width, height; each crop its box with a 1-pixel margin, 255 on its pixels, laid end to end), the
 *                    Python's test `span < draw_min and covered_by_color[box][sel_].mean() >= covered_min`. The
 *                    component's own span from np.nonzero of its crop is max(width, height) of its box; the mean of a
 *                    boolean selection is its count of covered pixels over its area, one float64 division (numpy's
 *                    float64 sum of zeros and ones is exact).
 *   rf_ink_density:  the ink density measured before that loop (see there).
 * Proven: a check compares every component's decision and the ink density on real runs with the
 * Python's. */
#include <stdlib.h>
#include "rmfast.h"
#include "internal.h"

typedef struct { const uint8_t *const *masks; int32_t n, H, W; uint8_t *out; int nt; } anyjob;

static void any_worker(void *arg, int tid) {
    anyjob *J = (anyjob *)arg;
    size_t W = (size_t)J->W;
    for (int32_t y = tid; y < J->H; y += J->nt) {
        uint8_t *o = J->out + (size_t)y * W;
        for (size_t x = 0; x < W; x++) o[x] = 0;
        for (int32_t k = 0; k < J->n; k++) {
            const uint8_t *m = J->masks[k] + (size_t)y * W;
            for (size_t x = 0; x < W; x++) o[x] |= (uint8_t)(m[x] != 0);
        }
    }
}

RF_API void rf_any_nonzero(const uint8_t *const *masks, int32_t n, int32_t H, int32_t W, uint8_t *out) {
    anyjob J = {masks, n, H, W, out, rf_threads()};
    rf_parallel(J.nt, any_worker, &J);
}

RF_API void rf_speck_skip(const int64_t *info, const uint8_t *crops, int32_t n, const uint8_t *covered, int32_t H, int32_t W,
                          int64_t draw_min, double covered_min, uint8_t *skip) {
    int64_t off = 0;
    for (int32_t t = 0; t < n; t++) {
        int64_t area = info[5 * t], x0 = info[5 * t + 1], y0 = info[5 * t + 2], w = info[5 * t + 3], h = info[5 * t + 4];
        int64_t span = w > h ? w : h, cw = w + 2;
        skip[t] = 0;
        if (span < draw_min && area > 0) {
            int64_t cnt = 0;
            for (int64_t y = 0; y < h; y++) {
                const uint8_t *row = crops + off + (y + 1) * cw + 1;
                int64_t gy = y0 + y;
                if (gy < 0 || gy >= H) continue;           /* never: a component's pixels lie in the grid */
                for (int64_t x = 0; x < w; x++) {
                    int64_t gx = x0 + x;
                    if (row[x] && gx >= 0 && gx < W) cnt += covered[(size_t)gy * (size_t)W + (size_t)gx] != 0;
                }
            }
            skip[t] = (double)cnt / (double)area >= covered_min;
        }
        off += (h + 2) * cw;
    }
}

/* The twin's ink density (rm_paint.decompose's lines before the black loop): black_left's 4-connected pieces
 * (scipy.ndimage.label's numbering), each one's area and black pixels (np.bincount: exact counts), a piece without a
 * core (black share < core_min, area * ppg * ppg > absorb_max_area) counted at its centroid's cell -- the centroid as
 * scipy.ndimage.center_of_mass makes it (the sums of y and of x over its pixels in raster order, exact integers, over
 * its count), the cell numpy's floor division by `cell` -- into hist (hh x hw, zeros in), then uniform_filter(3,
 * "nearest") on it. -> the piece count (0: the Python keeps ink_density None), or -1 when memory ran out. */
RF_API int32_t rf_ink_density(const uint8_t *black_left, const uint8_t *black, int32_t H, int32_t W, double ppg, double core_min,
                              double absorb_max_area, double cell, int32_t hh, int32_t hw, double *hist) {
    size_t N = (size_t)H * W;
    int32_t *lab = (int32_t *)malloc(sizeof(int32_t) * (N ? N : 1));
    if (!lab) return -1;
    rf_comps C;
    int32_t n = rf_label4(black_left, H, W, lab, &C, 0);
    if (n < 0) { free(lab); return -1; }
    int64_t *bp = (int64_t *)calloc((size_t)n + 1, sizeof(int64_t)), *sy = (int64_t *)calloc((size_t)n + 1, sizeof(int64_t));
    int64_t *sx = (int64_t *)calloc((size_t)n + 1, sizeof(int64_t));
    double *line = (double *)malloc(sizeof(double) * (size_t)((hh > hw ? hh : hw) + 2));
    if (!bp || !sy || !sx || !line) { free(bp); free(sy); free(sx); free(line); free(lab); rf_comps_free(&C); return -1; }
    for (int32_t y = 0; y < H; y++)
        for (int32_t x = 0; x < W; x++) {
            size_t p = (size_t)y * W + x;
            int32_t k = lab[p];
            if (!k) continue;
            bp[k] += black[p] != 0;
            sy[k] += y;
            sx[k] += x;
        }
    for (int32_t k = 1; k <= n; k++) {
        double area = (double)C.area[k];
        if (!((double)bp[k] / (area > 1.0 ? area : 1.0) < core_min && area * ppg * ppg > absorb_max_area)) continue;
        double gy = rf_py_floordiv((double)sy[k] / area, cell), gx = rf_py_floordiv((double)sx[k] / area, cell);
        /* the centroid lies in the grid and hist has int(H // cell) + 2 rows, int(W // cell) + 2 columns: the clamps
         * never bind */
        int64_t iy = gy < 0.0 ? 0 : (gy > (double)(hh - 1) ? hh - 1 : (int64_t)gy);
        int64_t ix = gx < 0.0 ? 0 : (gx > (double)(hw - 1) ? hw - 1 : (int64_t)gx);
        hist[(size_t)iy * (size_t)hw + (size_t)ix] += 1.0;
    }
    for (int32_t x = 0; x < hw; x++) rf_uniform3(hist + x, hh, hw, line);
    for (int32_t y = 0; y < hh; y++) rf_uniform3(hist + (size_t)y * (size_t)hw, hw, 1, line);
    free(bp); free(sy); free(sx); free(line); free(lab); rf_comps_free(&C);
    return n;
}