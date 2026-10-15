/* rank.c -- rmb_npops.rank_ext: a k x k maximum or minimum filter of a uint8 grid with the edge pixels replicated
 * (scipy.ndimage.maximum_filter / minimum_filter, size k, mode "nearest", origin 0 -- which is what Pillow's MaxFilter
 * and MinFilter give), DECISION code: it only grows and shrinks masks.
 *
 * Separable, as scipy computes it: along the rows, then along the columns of that result; the window of pixel i is
 * i - k/2 .. i - k/2 + k - 1 (centered for an odd k) with indices clamped to the grid. A maximum or minimum of integers
 * is exact, so the order of the comparisons cannot change a value. Up to k = 63 each pass is k vector maxima (minima)
 * over contiguous padded rows; past that (rm_paint._spiral_rings' thin rescue reach grows as the page scale shrinks, so
 * a large k is reachable) the van Herk / Gil-Werman scheme, three comparisons per pixel whatever k is: prefix and suffix
 * extremes within blocks of k, and out[i] = extreme(suffix[i], prefix[i + k - 1]). Rows (row pass) and columns
 * (column pass, k > 63) in fixed bands on all threads; every output pixel is its own.
 * Identity: checked against the reference -- random grids of many shapes, densities and k (odd and even, 1 to 301), both kinds, at
 * one thread and at the default, against rank_ext's scipy call; and the model's own calls on the corpus pictures. */
#include <stdlib.h>
#include <string.h>
#include "rmfast.h"
#include "internal.h"

#define RANK_DIRECT_MAX 63       /* up to this k the direct k-step passes; past it van Herk / Gil-Werman */

typedef struct {
    const uint8_t *src; uint8_t *dst; int32_t H, W, k; int ismax; int nt;
    uint8_t *buf; size_t per;    /* per thread: `per` bytes of scratch */
} rankjob;

static inline uint8_t ext_of(uint8_t a, uint8_t b, int ismax) { return ismax ? (a > b ? a : b) : (a < b ? a : b); }

/* o[i] = extreme of e[i .. i + k - 1], i < n; e holds n + k - 1 values; g, h scratch of n + k - 1 */
static void vhgw(const uint8_t *e, int32_t n, int32_t k, int ismax, uint8_t *g, uint8_t *h, uint8_t *o) {
    int64_t L = (int64_t)n + k - 1;
    for (int64_t j = 0; j < L; j++) g[j] = (j % k == 0) ? e[j] : ext_of(g[j - 1], e[j], ismax);
    for (int64_t j = L - 1; j >= 0; j--) h[j] = (j == L - 1 || (j + 1) % k == 0) ? e[j] : ext_of(h[j + 1], e[j], ismax);
    for (int64_t i = 0; i < n; i++) o[i] = ext_of(h[i], g[i + k - 1], ismax);
}

static void row_pass(void *arg, int tid) {
    rankjob *J = (rankjob *)arg;
    int32_t W = J->W, k = J->k, lo = k / 2;
    int32_t y0 = (int32_t)((int64_t)J->H * tid / J->nt), y1 = (int32_t)((int64_t)J->H * (tid + 1) / J->nt);
    size_t L = (size_t)W + (size_t)k - 1;
    uint8_t *ext = J->buf + (size_t)tid * J->per, *g = ext + L, *h = g + L;      /* g, h only for k > 63 */
    for (int32_t y = y0; y < y1; y++) {
        const uint8_t *s = J->src + (size_t)y * (size_t)W;
        uint8_t *o = J->dst + (size_t)y * (size_t)W;
        memset(ext, s[0], (size_t)lo);
        memcpy(ext + lo, s, (size_t)W);
        memset(ext + lo + W, s[W - 1], (size_t)(k - 1 - lo));
        if (k > RANK_DIRECT_MAX) { vhgw(ext, W, k, J->ismax, g, h, o); continue; }
        memcpy(o, ext, (size_t)W);
        if (J->ismax) {
            for (int32_t d = 1; d < k; d++) {
                const uint8_t *e = ext + d;
                for (int32_t x = 0; x < W; x++) o[x] = e[x] > o[x] ? e[x] : o[x];
            }
        } else {
            for (int32_t d = 1; d < k; d++) {
                const uint8_t *e = ext + d;
                for (int32_t x = 0; x < W; x++) o[x] = e[x] < o[x] ? e[x] : o[x];
            }
        }
    }
}

/* the column pass up to k = 63: output rows in bands, each the extreme of its k clamped source rows */
static void col_pass(void *arg, int tid) {
    rankjob *J = (rankjob *)arg;
    int32_t H = J->H, W = J->W, k = J->k, lo = k / 2;
    int32_t y0 = (int32_t)((int64_t)H * tid / J->nt), y1 = (int32_t)((int64_t)H * (tid + 1) / J->nt);
    for (int32_t y = y0; y < y1; y++) {
        uint8_t *o = J->dst + (size_t)y * (size_t)W;
        int32_t a = y - lo < 0 ? 0 : y - lo;
        memcpy(o, J->src + (size_t)a * (size_t)W, (size_t)W);
        for (int32_t d = 1; d < k; d++) {
            int32_t yy = y - lo + d < 0 ? 0 : (y - lo + d >= H ? H - 1 : y - lo + d);
            const uint8_t *e = J->src + (size_t)yy * (size_t)W;
            if (J->ismax) for (int32_t x = 0; x < W; x++) o[x] = e[x] > o[x] ? e[x] : o[x];
            else for (int32_t x = 0; x < W; x++) o[x] = e[x] < o[x] ? e[x] : o[x];
        }
    }
}

/* the column pass past k = 63: van Herk / Gil-Werman down each column of a band of columns, through one column of
 * scratch at a time */
static void col_pass_vhgw(void *arg, int tid) {
    rankjob *J = (rankjob *)arg;
    int32_t H = J->H, W = J->W, k = J->k, lo = k / 2;
    int32_t x0 = (int32_t)((int64_t)W * tid / J->nt), x1 = (int32_t)((int64_t)W * (tid + 1) / J->nt);
    size_t L = (size_t)H + (size_t)k - 1;
    uint8_t *e = J->buf + (size_t)tid * J->per, *g = e + L, *h = g + L, *o = h + L;
    for (int32_t x = x0; x < x1; x++) {
        for (size_t j = 0; j < L; j++) {
            int64_t yy = (int64_t)j - lo;
            yy = yy < 0 ? 0 : (yy >= H ? H - 1 : yy);
            e[j] = J->src[(size_t)yy * (size_t)W + (size_t)x];
        }
        vhgw(e, H, k, J->ismax, g, h, o);
        for (int32_t y = 0; y < H; y++) J->dst[(size_t)y * (size_t)W + (size_t)x] = o[y];
    }
}

/* src (H x W) -> dst (H x W, not src); 0, -1 out of memory, -2 refused (k < 1: scipy raises there; every k the painter
 * makes is 2 r + 1 with r >= 1) */
RF_API int32_t rf_rank_ext(const uint8_t *src, int32_t H, int32_t W, int32_t k, int32_t ismax, uint8_t *dst) {
    if (k < 1) return -2;
    if (H <= 0 || W <= 0) return 0;
    if (k == 1) { memcpy(dst, src, (size_t)H * (size_t)W); return 0; }
    int nt = rf_threads();
    int big = k > RANK_DIRECT_MAX;
    int ntr = nt > H ? H : nt, ntc = big ? (nt > W ? W : nt) : ntr;
    if (ntr < 1) ntr = 1;
    if (ntc < 1) ntc = 1;
    size_t per_row = ((size_t)W + (size_t)k - 1) * (big ? 3 : 1);
    size_t per_col = big ? ((size_t)H + (size_t)k - 1) * 3 + (size_t)H : 0;
    size_t per = per_row > per_col ? per_row : per_col;
    int nbuf = ntr > ntc ? ntr : ntc;
    uint8_t *tmp = (uint8_t *)malloc((size_t)H * (size_t)W);
    uint8_t *buf = (uint8_t *)malloc((size_t)nbuf * per);
    if (!tmp || !buf) { free(tmp); free(buf); return -1; }
    rankjob A = {src, tmp, H, W, k, ismax != 0, ntr, buf, per};
    rf_parallel(ntr, row_pass, &A);
    rankjob B = {tmp, dst, H, W, k, ismax != 0, ntc, buf, per};
    rf_parallel(ntc, big ? col_pass_vhgw : col_pass, &B);
    free(tmp); free(buf);
    return 0;
}
