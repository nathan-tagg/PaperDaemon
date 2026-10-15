/* xdog.c -- the painter's ridge: rmb_lineart.xdog, mask and thin (GEOMETRY code: the ridge is what the contour pass
 * draws).
 *
 *   xdog   the source's L (Pillow's conversion), ImageOps.autocontrast(cutoff=1) (Pillow 12.3.0: the histogram, the
 *          integer cut n * 1 // 100 taken off each end, lut = int(ix * scale + offset) clamped), GaussianBlur(sigma)
 *          and GaussianBlur(sigma * k) (blur.c), response (g1 - tau * g2) / 255.0 in float64;
 *   mask   the darkest `ink` share: the element int(n * ink) (clamped) of the sorted response, as a selection;
 *   thin   rmb_npops.zhang_suen on the mask padded by one pixel: two sub-steps, each deciding every pixel from the
 *          current grid and then deleting together, until nothing changes. The decisions of a sub-step read the grid
 *          only, so rows are decided on all threads.
 * The caller guarantees the grid is the source at its own size (the painter's grid_max off, no upscale), so the resize
 * xdog does is the identity. Identity: a check of every call of real runs against rmb_lineart.
 *   rf_thin  rmb_lineart.thin alone (the contour pass's and the hatch bands' thinning), the same Zhang-Suen; identity:
 *          a check of every call of real runs against rmb_lineart.thin, and of random masks. */
#include <stdatomic.h>
#include <stdlib.h>
#include <string.h>
#include "rmfast.h"
#include "internal.h"

/* ImageOps.autocontrast(im, cutoff=1) on an L image: the 256-entry table */
static void autocontrast_lut(const uint8_t *L, size_t N, uint8_t *lut) {
    int64_t h[256] = {0};
    for (size_t i = 0; i < N; i++) h[L[i]]++;
    int64_t n = 0;
    for (int ix = 0; ix < 256; ix++) n += h[ix];
    int64_t cut = n * 1 / 100;                         /* int(n * cutoff // 100), n >= 0 */
    for (int lo = 0; lo < 256; lo++) {
        if (cut > h[lo]) { cut -= h[lo]; h[lo] = 0; }
        else { h[lo] -= cut; cut = 0; }
        if (cut <= 0) break;
    }
    cut = n * 1 / 100;
    for (int hi = 255; hi >= 0; hi--) {
        if (cut > h[hi]) { cut -= h[hi]; h[hi] = 0; }
        else { h[hi] -= cut; cut = 0; }
        if (cut <= 0) break;
    }
    int lo = 0, hi = 255;
    for (lo = 0; lo < 256; lo++) if (h[lo]) break;
    for (hi = 255; hi >= 0; hi--) if (h[hi]) break;
    /* the Python's loops leave lo = 255 and hi = 0 when the histogram is empty; hi <= lo is the identity either way */
    if (lo > 255) lo = 255;
    if (hi < 0) hi = 0;
    if (hi <= lo) { for (int ix = 0; ix < 256; ix++) lut[ix] = (uint8_t)ix; return; }
    double scale = 255.0 / (double)(hi - lo);
    double offset = (double)(-lo) * scale;
    for (int ix = 0; ix < 256; ix++) {
        double v = (double)ix * scale + offset;
        int iv = v < 0.0 ? -1 : (v > 255.0 ? 256 : (int)v);      /* int() truncates; v is within [-1, 256] */
        lut[ix] = (uint8_t)(iv < 0 ? 0 : (iv > 255 ? 255 : iv));
    }
}

typedef struct { uint8_t *f; uint8_t *drop; int32_t h, w; int step; atomic_int next; atomic_int changed; } zsjob;
#define ZS_ROWS 32

static void zs_worker(void *arg, int tid) {
    (void)tid;
    zsjob *J = (zsjob *)arg;
    const int32_t h = J->h, w = J->w;
    const uint8_t *f = J->f;
    for (;;) {
        int32_t y0 = atomic_fetch_add(&J->next, ZS_ROWS);
        if (y0 >= h - 1) break;
        int32_t y1 = y0 + ZS_ROWS < h - 1 ? y0 + ZS_ROWS : h - 1;
        for (int32_t y = y0 < 1 ? 1 : y0; y < y1; y++) {
            uint8_t *drow = J->drop + (size_t)y * w;
            for (int32_t x = 1; x < w - 1; x++) {
                drow[x] = 0;
                if (!f[(size_t)y * w + x]) continue;
                int n0 = f[(size_t)(y - 1) * w + x], n1 = f[(size_t)(y - 1) * w + x + 1], n2 = f[(size_t)y * w + x + 1];
                int n3 = f[(size_t)(y + 1) * w + x + 1], n4 = f[(size_t)(y + 1) * w + x], n5 = f[(size_t)(y + 1) * w + x - 1];
                int n6 = f[(size_t)y * w + x - 1], n7 = f[(size_t)(y - 1) * w + x - 1];
                int c = n0 + n1 + n2 + n3 + n4 + n5 + n6 + n7;
                if (c < 2 || c > 6) continue;
                int t = (!n0 && n1) + (!n1 && n2) + (!n2 && n3) + (!n3 && n4) + (!n4 && n5) + (!n5 && n6) + (!n6 && n7) + (!n7 && n0);
                if (t != 1) continue;
                if (J->step == 0) { if ((n0 && n2 && n4) || (n2 && n4 && n6)) continue; }
                else if ((n0 && n2 && n6) || (n0 && n4 && n6)) continue;
                drow[x] = 1;
            }
        }
    }
}

/* Zhang-Suen on f, a ph x pw grid of 0/1 whose border rows and columns are 0 (the padding); drop is a ph x pw
 * scratch grid of zeros. Each pass removes pixels, so at most (ph - 2) * (pw - 2) passes can change anything. */
static void zs_thin(uint8_t *f, uint8_t *drop, int32_t ph, int32_t pw) {
    size_t npx = (size_t)(ph - 2) * (size_t)(pw - 2);
    zsjob J;
    J.f = f; J.drop = drop; J.h = ph; J.w = pw;
    int nt = rf_threads(), bands = (ph + ZS_ROWS - 1) / ZS_ROWS;
    if (nt > bands) nt = bands;
    for (size_t pass = 0; pass <= npx; pass++) {
        int changed = 0;
        for (int step = 0; step < 2; step++) {
            J.step = step;
            atomic_init(&J.next, 0);
            rf_parallel(nt > 0 ? nt : 1, zs_worker, &J);
            for (int32_t y = 1; y < ph - 1; y++)
                for (int32_t x = 1; x < pw - 1; x++)
                    if (drop[(size_t)y * pw + x]) { f[(size_t)y * pw + x] = 0; changed = 1; }
        }
        if (!changed) break;
    }
}

/* rmb_lineart.thin: Zhang-Suen of an H x W mask (any non-zero byte set) padded by one pixel, into out (0/1).
 * 0, or -1 when memory ran out */
RF_API int32_t rf_thin(const uint8_t *fg, int32_t H, int32_t W, uint8_t *out) {
    if (H <= 0 || W <= 0) return 0;
    int32_t ph = H + 2, pw = W + 2;
    uint8_t *f = (uint8_t *)calloc((size_t)ph * pw, 1), *drop = (uint8_t *)calloc((size_t)ph * pw, 1);
    if (!f || !drop) { free(f); free(drop); return -1; }
    for (int32_t y = 0; y < H; y++)
        for (int32_t x = 0; x < W; x++) f[(size_t)(y + 1) * pw + x + 1] = fg[(size_t)y * W + x] != 0;
    zs_thin(f, drop, ph, pw);
    for (int32_t y = 0; y < H; y++)
        for (int32_t x = 0; x < W; x++) out[(size_t)y * W + x] = f[(size_t)(y + 1) * pw + x + 1];
    free(f); free(drop);
    return 0;
}

/* -> 0 and ridge (H x W, 0/1) with *count its pixels; -1 when memory ran out */
RF_API int32_t rf_xdog_ridge(const uint8_t *rgb, int32_t H, int32_t W, float sigma, float sigma_k, double tau, double ink,
                             uint8_t *ridge, int64_t *count) {
    size_t N = (size_t)H * W;
    int32_t ph = H + 2, pw = W + 2;
    *count = 0;
    uint8_t *L = (uint8_t *)malloc(N ? N : 1), *g1 = (uint8_t *)malloc(N ? N : 1), *g2 = (uint8_t *)malloc(N ? N : 1);
    double *resp = (double *)malloc(sizeof(double) * (N ? N : 1)), *srt = (double *)malloc(sizeof(double) * (N ? N : 1));
    uint8_t *f = (uint8_t *)calloc((size_t)ph * pw, 1), *drop = (uint8_t *)calloc((size_t)ph * pw, 1);
    int32_t rc = -1;
    if (!L || !g1 || !g2 || !resp || !srt || !f || !drop || N == 0) goto done;
    for (size_t i = 0; i < N; i++) {
        const uint8_t *p = rgb + 3 * i;
        L[i] = (uint8_t)(((uint32_t)p[0] * 19595u + (uint32_t)p[1] * 38470u + (uint32_t)p[2] * 7471u + 0x8000u) >> 16);
    }
    uint8_t lut[256];
    autocontrast_lut(L, N, lut);
    for (size_t i = 0; i < N; i++) L[i] = lut[L[i]];
    if (rf_box_blur(L, g1, H, W, 1, sigma, 1) || rf_box_blur(L, g2, H, W, 1, sigma_k, 1)) goto done;
    for (size_t i = 0; i < N; i++) { resp[i] = ((double)g1[i] - tau * (double)g2[i]) / 255.0; srt[i] = resp[i]; }
    /* the cut: flat[max(0, min(n - 1, int(n * ink)))] of the sorted response */
    double kf = (double)N * ink;
    int64_t k = kf < 0.0 ? 0 : (kf > (double)(N - 1) ? (int64_t)(N - 1) : (int64_t)kf);
    double cut = rf_kth(srt, (int64_t)N, k);
    for (int32_t y = 0; y < H; y++)
        for (int32_t x = 0; x < W; x++) f[(size_t)(y + 1) * pw + x + 1] = resp[(size_t)y * W + x] <= cut;
    zs_thin(f, drop, ph, pw);
    int64_t cnt = 0;
    for (int32_t y = 0; y < H; y++)
        for (int32_t x = 0; x < W; x++) { uint8_t v = f[(size_t)(y + 1) * pw + x + 1]; ridge[(size_t)y * W + x] = v; cnt += v; }
    *count = cnt;
    rc = 0;
done:
    free(L); free(g1); free(g2); free(resp); free(srt); free(f); free(drop);
    return rc;
}
