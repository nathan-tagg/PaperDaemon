/* The quantizer's cel pass -- rm_paint._mode_filter: the majority label in every (2r+1)^2 window, as an argmax over
 * each label's box-filtered indicator, first label winning ties.
 *
 * The box filter is scipy.ndimage.uniform_filter(indicator.astype(float32), size=k, mode="constant") reproduced
 * operation for operation (scipy 1.18.1, ni_filters.c NI_UniformFilter1D): axis 0 then axis 1, each line copied to a
 * double buffer with k//2 zeros on either side, a running sum (the first window summed left to right, then
 * `tmp += in[l + k - 1] - in[l - 1]`), each output `tmp / k` stored as float32 -- and the second pass reads the first
 * pass's float32 values. On a 0/1 indicator the first pass's sums are exact integers; the second pass's are not, and
 * its rounding residue is carried to the end of the row, so every row that holds a non-zero value is run in full.
 *
 * Every output pixel depends only on its own row's second pass and the first pass of the rows around it, and the
 * labels are taken in order per pixel, so the picture is cut into bands of rows that run on separate threads.
 * DECISION code. Every allocation is checked: a failure returns -1 (out then holds an unfinished result). */
#include <math.h>
#include <stdatomic.h>
#include <stdlib.h>
#include <string.h>
#include "rmfast.h"
#include "internal.h"

typedef struct {
    const int64_t *lab; int32_t h, w, n, r; int64_t *out;
    const int32_t *bx0, *bx1, *by0, *by1;
    float *best;
    atomic_int next;
    atomic_int oom;
} modejob;

#define MODE_BAND 32

static void mode_band(modejob *J, int32_t ys, int32_t ye, float *p1, int32_t *cnt, double *ext, float *row) {
    const int64_t *lab = J->lab;
    int32_t h = J->h, w = J->w, r = J->r, k = 2 * J->r + 1;
    double kd = (double)k;
    for (int32_t i = 0; i < J->n; i++) {
        if (J->bx1[i] < 0) continue;                       /* no pixels: its filtered indicator is exactly 0 */
        int32_t x0 = J->bx0[i], x1 = J->bx1[i];
        int32_t y0 = J->by0[i] - r < 0 ? 0 : J->by0[i] - r, y1 = J->by1[i] + r >= h ? h - 1 : J->by1[i] + r;
        int32_t a = y0 > ys ? y0 : ys, b = y1 < ye - 1 ? y1 : ye - 1;
        if (a > b) continue;
        /* pass 1, axis 0, rows a..b: the count of label pixels in rows y-r..y+r over k, as float32 (0 outside x0..x1) */
        for (int32_t x = x0; x <= x1; x++) cnt[x] = 0;
        for (int32_t yy = a - r; yy <= a + r; yy++) {
            if (yy < 0 || yy >= h) continue;
            const int64_t *L = lab + (size_t)yy * w;
            for (int32_t x = x0; x <= x1; x++) cnt[x] += (L[x] == i);
        }
        for (int32_t y = a; y <= b; y++) {
            if (y > a) {
                int32_t ya = y + r, yr = y - r - 1;
                if (ya < h) { const int64_t *L = lab + (size_t)ya * w; for (int32_t x = x0; x <= x1; x++) cnt[x] += (L[x] == i); }
                if (yr >= 0) { const int64_t *L = lab + (size_t)yr * w; for (int32_t x = x0; x <= x1; x++) cnt[x] -= (L[x] == i); }
            }
            float *P = p1 + (size_t)(y - ys) * w;
            memset(P, 0, sizeof(float) * w);
            for (int32_t x = x0; x <= x1; x++) P[x] = (float)((double)cnt[x] / kd);
        }
        /* pass 2, axis 1, on each of those rows; then the argmax update */
        for (int32_t y = a; y <= b; y++) {
            const float *P = p1 + (size_t)(y - ys) * w;
            for (int32_t t = 0; t < r; t++) ext[t] = 0.0;
            for (int32_t x = 0; x < w; x++) ext[r + x] = (double)P[x];
            for (int32_t t = 0; t < r + 1; t++) ext[r + w + t] = 0.0;
            double tmp = 0.0;
            for (int32_t t = 0; t < k; t++) tmp += ext[t];
            row[0] = (float)(tmp / kd);
            for (int32_t x = 1; x < w; x++) {
                tmp += ext[x + k - 1] - ext[x - 1];
                row[x] = (float)(tmp / kd);
            }
            float *B = J->best + (size_t)y * w;
            int64_t *O = J->out + (size_t)y * w;
            for (int32_t x = 0; x < w; x++) if (row[x] > B[x]) { B[x] = row[x]; O[x] = i; }
        }
    }
}

static void mode_worker(void *arg, int tid) {
    modejob *J = (modejob *)arg;
    int32_t w = J->w, r = J->r;
    float *p1 = (float *)malloc(sizeof(float) * (size_t)MODE_BAND * (w > 0 ? w : 1));
    int32_t *cnt = (int32_t *)malloc(sizeof(int32_t) * (w > 0 ? w : 1));
    double *ext = (double *)malloc(sizeof(double) * ((size_t)w + 2 * r + 1));
    float *row = (float *)malloc(sizeof(float) * (w > 0 ? w : 1));
    if (!p1 || !cnt || !ext || !row) { atomic_store(&J->oom, 1); free(p1); free(cnt); free(ext); free(row); return; }
    for (;;) {
        int32_t ys = atomic_fetch_add(&J->next, MODE_BAND);
        if (ys >= J->h) break;
        mode_band(J, ys, ys + MODE_BAND < J->h ? ys + MODE_BAND : J->h, p1, cnt, ext, row);
    }
    free(p1); free(cnt); free(ext); free(row);
}

RF_API int32_t rf_mode_filter(const int64_t *lab, int32_t h, int32_t w, int32_t n, int32_t r, int64_t *out) {
    size_t N = (size_t)h * w;
    memcpy(out, lab, sizeof(int64_t) * N);
    if (N == 0 || n <= 0) return 0;
    int32_t *bx0 = (int32_t *)malloc(sizeof(int32_t) * n), *bx1 = (int32_t *)malloc(sizeof(int32_t) * n);
    int32_t *by0 = (int32_t *)malloc(sizeof(int32_t) * n), *by1 = (int32_t *)malloc(sizeof(int32_t) * n);
    float *best = (float *)calloc(N, sizeof(float));
    if (!bx0 || !bx1 || !by0 || !by1 || !best) { free(bx0); free(bx1); free(by0); free(by1); free(best); return -1; }
    for (int32_t i = 0; i < n; i++) { bx0[i] = w; bx1[i] = -1; by0[i] = h; by1[i] = -1; }
    for (int32_t y = 0; y < h; y++)
        for (int32_t x = 0; x < w; x++) {
            int64_t v = lab[(size_t)y * w + x];
            if (v < 0 || v >= n) continue;
            if (x < bx0[v]) bx0[v] = x;
            if (x > bx1[v]) bx1[v] = x;
            if (y < by0[v]) by0[v] = y;
            if (y > by1[v]) by1[v] = y;
        }
    modejob J;
    J.lab = lab; J.h = h; J.w = w; J.n = n; J.r = r; J.out = out;
    J.bx0 = bx0; J.bx1 = bx1; J.by0 = by0; J.by1 = by1;
    J.best = best;
    atomic_init(&J.next, 0);
    atomic_init(&J.oom, 0);
    int nt = rf_threads();
    int bands = (h + MODE_BAND - 1) / MODE_BAND;
    if (nt > bands) nt = bands;
    rf_parallel(nt, mode_worker, &J);
    free(bx0); free(bx1); free(by0); free(by1); free(best);
    return atomic_load(&J.oom) ? -1 : 0;
}

/* ------------------------------------------------------------------ the rest of rm_paint.quantize */
/* np.unique of the packed colors (r << 16 | g << 8 | b) of n RGB rows: the distinct codes ascending into codes (room
 * for up to cap), each row's index among them into inv. -> the count, -1 when there are more than cap or memory ran
 * out. */
RF_API int32_t rf_unique_rgb(const uint8_t *rgb, int64_t n, int32_t *codes, int32_t cap, int32_t *inv) {
    uint8_t *seen = (uint8_t *)calloc((size_t)1 << 21, 1);       /* a bit per 24-bit code */
    if (!seen) return -1;
    for (int64_t i = 0; i < n; i++) {
        uint32_t c = ((uint32_t)rgb[3 * i] << 16) | ((uint32_t)rgb[3 * i + 1] << 8) | rgb[3 * i + 2];
        seen[c >> 3] |= (uint8_t)(1u << (c & 7));
    }
    int32_t k = 0;
    for (uint32_t c = 0; c < (1u << 24); c++)
        if (seen[c >> 3] & (1u << (c & 7))) {
            if (k == cap) { free(seen); return -1; }
            codes[k++] = (int32_t)c;
        }
    free(seen);
    for (int64_t i = 0; i < n; i++) {
        int32_t c = (int32_t)(((uint32_t)rgb[3 * i] << 16) | ((uint32_t)rgb[3 * i + 1] << 8) | rgb[3 * i + 2]);
        int32_t lo = 0, hi = k - 1;
        while (lo < hi) { int32_t mid = lo + (hi - lo) / 2; if (codes[mid] < c) lo = mid + 1; else hi = mid; }
        inv[i] = lo;
    }
    return k;
}

/* rf_quant_tail's inputs and outputs for its row bands (see there) */
typedef struct {
    const int32_t *inv0; const double *ulum; const uint8_t *neutral, *chromatic; const double *uchroma; const int8_t *cat;
    const int32_t *kidx; int32_t nkeys; const uint8_t *rgb; int32_t H, W; const int64_t *o64; double mode_max_dl;
    int32_t black_cut, ink_cut, paper_cut; double black_chroma;
    uint8_t *tone, *black, *const *keys, *ink;
    int64_t *bfirst, *bcounts;          /* per band: 2 + 2 nkeys first positions, 3 + nkeys counts */
    int nt;
} tailjob;

static void tail_worker(void *arg, int tid) {
    tailjob *J = (tailjob *)arg;
    const int32_t nk = J->nkeys;
    int64_t *first = J->bfirst + (size_t)tid * (size_t)(2 + 2 * nk), *counts = J->bcounts + (size_t)tid * (size_t)(3 + nk);
    for (int32_t k = 0; k < 2 + 2 * nk; k++) first[k] = -1;
    for (int32_t k = 0; k < 3 + nk; k++) counts[k] = 0;
    size_t i0 = (size_t)((int64_t)J->H * tid / J->nt) * (size_t)J->W, i1 = (size_t)((int64_t)J->H * (tid + 1) / J->nt) * (size_t)J->W;
    for (int32_t j = 0; j < nk; j++) memset(J->keys[j] + i0, 0, i1 - i0);
    for (size_t i = i0; i < i1; i++) {
        const uint8_t *p = J->rgb + 3 * i;
        int32_t L = (int32_t)(((uint32_t)p[0] * 19595u + (uint32_t)p[1] * 38470u + (uint32_t)p[2] * 7471u + 0x8000u) >> 16);
        int32_t u = J->inv0[i];
        if (J->o64) {
            int32_t u2 = (int32_t)J->o64[i];
            int ok = fabs(J->ulum[u2] - (double)L) <= J->mode_max_dl;
            if ((L >= J->ink_cut || !J->neutral[u]) && ok) u = u2;
        }
        int c = J->cat[u];
        int up = L < J->paper_cut, isb = L < J->black_cut;
        int m1 = c == 1 && up, m2 = c == 2 && up, m3 = c == 3;
        int t = m1 || (m2 && !isb);
        int b = m2 && isb && J->uchroma[u] < J->black_chroma;
        int k_ = (m2 || m1) && L < J->ink_cut && (isb || (!J->chromatic[u] && J->neutral[u]));
        J->tone[i] = t ? 255 : 0; J->black[i] = b ? 255 : 0; J->ink[i] = k_ ? 255 : 0;
        counts[0] += t; counts[1] += b; counts[2] += k_;
        if (t && first[0] < 0) first[0] = (int64_t)i;
        if (b && first[1] < 0) first[1] = (int64_t)i;
        if (m3 || m1) {
            int32_t j = J->kidx[u];
            if (j >= 0 && j < nk) {
                J->keys[j][i] = 255;
                counts[3 + j]++;
                int64_t *f = first + 2 + 2 * j + (m3 ? 0 : 1);
                if (*f < 0) *f = (int64_t)i;
            }
        }
    }
}

/* From the cluster map on: inv0 (each pixel's palette entry after the cel palette), the palette's lightness (ulum),
 * neutral and chromatic flags, chroma, class (cat: 0 paper, 1 base, 2 achromatic, 3 color) and color slot (kidx).
 *   lum = Pillow's L of the grid picture;
 *   the cel pass when mode_r > 0: inv2 = _mode_filter(inv0, nu, mode_r) (rf_mode_filter), kept where
 *     (lum >= ink_cut or the entry is not neutral) and |ulum[inv2] - lum| <= mode_max_dl;
 *   then tone, black, the ink mask and each color slot's mask (m3 | m1 of its pixels) as 0/255 grids, the first raster
 *   position of tone, black and each slot's m3 and m1 pixels (first: -1 for none; 2 + 2 * nkeys values) and each
 *   mask's pixel count (tone, black, ink, then the slots).
 * Rows in fixed bands on all threads, each pixel decided on its own; the bands' counts are summed and each first
 * position is the first band's (bands are in raster order, so that is the smallest), which is what one raster scan
 * gives.
 * -> 0, or -1 when memory ran out. DECISION code; the order and the dict are the caller's (rmfast.make_quantize). */
RF_API int32_t rf_quant_tail(const int32_t *inv0, int32_t nu, const double *ulum, const uint8_t *neutral, const uint8_t *chromatic,
                             const double *uchroma, const int8_t *cat, const int32_t *kidx, int32_t nkeys, const uint8_t *rgb,
                             int32_t H, int32_t W, int32_t mode_r, double mode_max_dl, int32_t black_cut, int32_t ink_cut,
                             int32_t paper_cut, double black_chroma, uint8_t *tone, uint8_t *black, uint8_t *const *keys,
                             uint8_t *ink, int64_t *first, int64_t *counts) {
    size_t N = (size_t)H * W;
    int64_t *l64 = NULL, *o64 = NULL;
    if (mode_r > 0) {
        l64 = (int64_t *)malloc(sizeof(int64_t) * (N ? N : 1));
        o64 = (int64_t *)malloc(sizeof(int64_t) * (N ? N : 1));
        if (!l64 || !o64) { free(l64); free(o64); return -1; }
        for (size_t i = 0; i < N; i++) l64[i] = inv0[i];
        if (rf_mode_filter(l64, H, W, nu, mode_r, o64)) { free(l64); free(o64); return -1; }
        free(l64); l64 = NULL;
    }
    int nt = rf_threads();
    if (nt > H) nt = H;
    if (nt < 1) nt = 1;
    int64_t *bfirst = (int64_t *)malloc(sizeof(int64_t) * (size_t)nt * (size_t)(2 + 2 * nkeys));
    int64_t *bcounts = (int64_t *)malloc(sizeof(int64_t) * (size_t)nt * (size_t)(3 + nkeys));
    if (!bfirst || !bcounts) { free(bfirst); free(bcounts); free(o64); return -1; }
    tailjob J = {inv0, ulum, neutral, chromatic, uchroma, cat, kidx, nkeys, rgb, H, W, o64, mode_max_dl, black_cut, ink_cut, paper_cut,
                 black_chroma, tone, black, keys, ink, bfirst, bcounts, nt};
    rf_parallel(nt, tail_worker, &J);
    for (int32_t k = 0; k < 2 + 2 * nkeys; k++) {
        first[k] = -1;
        for (int t = 0; t < nt && first[k] < 0; t++) first[k] = bfirst[(size_t)t * (size_t)(2 + 2 * nkeys) + (size_t)k];
    }
    for (int32_t k = 0; k < 3 + nkeys; k++) {
        counts[k] = 0;
        for (int t = 0; t < nt; t++) counts[k] += bcounts[(size_t)t * (size_t)(3 + nkeys) + (size_t)k];
    }
    free(bfirst); free(bcounts); free(o64);
    return 0;
}
