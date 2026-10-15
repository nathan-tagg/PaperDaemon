/* cel.c -- rm_paint.cel_regions: darkness posterised into bands, conservatively (DECISION code: which pixels shade).
 *
 * The Python's steps exactly: Pillow's GaussianBlur(blur) of the L picture (blur.c), d = 1.0 - g / 255.0 in float64,
 * per band the pixels inside the mask with lo <= d < hi, rm_paint._median (MedianFilter(k) on a binary mask: a k x k
 * box count over the edge-padded mask against half the window, 2 * count > k * k), the band's pixel count, the floor
 * int(speck_area * w * h) when that count is at least field_cover * w * h, else min_area, and every 4-connected piece
 * of at least max(floor, 1) pixels kept (rmb_npops.components with span 1: the pieces' union is what the paste
 * builds). Each band's result into outs[b] as 0 / 255.
 * Identity: a check of every call of real runs against rm_paint.cel_regions. */
#include <stdlib.h>
#include <string.h>
#include "rmfast.h"
#include "internal.h"

/* -> 0, or -1 when memory ran out */
RF_API int32_t rf_cel_regions(const uint8_t *lum, const uint8_t *mask, int32_t H, int32_t W, float blur, const double *lohi, int32_t nb,
                              int32_t k, double speck_area, double field_cover, int64_t min_area, uint8_t *const *outs) {
    size_t N = (size_t)H * W;
    int32_t r = k / 2, ph = H + 2 * r, pw = W + 2 * r;
    uint8_t *g = (uint8_t *)malloc(N ? N : 1), *m = (uint8_t *)malloc(N ? N : 1);
    int32_t *c = (int32_t *)malloc(sizeof(int32_t) * ((size_t)(ph + 1) * (size_t)(pw + 1)));
    int32_t *lab = (int32_t *)malloc(sizeof(int32_t) * (N ? N : 1));
    if (!g || !m || !c || !lab) { free(g); free(m); free(c); free(lab); return -1; }
    if (rf_box_blur(lum, g, H, W, 1, blur, 1)) { free(g); free(m); free(c); free(lab); return -1; }
    double dv[256];
    for (int v = 0; v < 256; v++) dv[v] = 1.0 - (double)v / 255.0;
    int32_t rc = 0;
    for (int32_t b = 0; b < nb && !rc; b++) {
        double lo = lohi[2 * b], hi = lohi[2 * b + 1];
        uint8_t *o = outs[b];
        /* the band (inside the mask) as 0/1, then its edge-padded summed-area table */
        for (size_t i = 0; i < N; i++) { double d = dv[g[i]]; m[i] = mask[i] != 0 && d >= lo && d < hi; }
        memset(c, 0, sizeof(int32_t) * (size_t)(pw + 1));
        for (int32_t y = 0; y < ph; y++) {
            int32_t sy = y - r < 0 ? 0 : (y - r >= H ? H - 1 : y - r), run = 0;
            int32_t *row = c + (size_t)(y + 1) * (pw + 1), *up = c + (size_t)y * (pw + 1);
            row[0] = 0;
            for (int32_t x = 0; x < pw; x++) {
                int32_t sx = x - r < 0 ? 0 : (x - r >= W ? W - 1 : x - r);
                run += m[(size_t)sy * W + sx];
                row[x + 1] = up[x + 1] + run;
            }
        }
        int64_t total = 0;
        for (int32_t y = 0; y < H; y++)
            for (int32_t x = 0; x < W; x++) {
                const int32_t *top = c + (size_t)y * (pw + 1), *bot = c + (size_t)(y + k) * (pw + 1);
                int32_t box = bot[x + k] - top[x + k] - bot[x] + top[x];
                uint8_t v = 2 * box > k * k;
                o[(size_t)y * W + x] = v;
                total += v;
            }
        /* the floor: Python's int(speck_area * w * h) when the band covers at least field_cover * w * h */
        int64_t floor_ = min_area;
        if ((double)total >= field_cover * W * H) {
            double f = speck_area * W * H;
            floor_ = (int64_t)f;
        }
        int64_t amin = floor_ > 1 ? floor_ : 1;
        rf_comps C;
        int32_t n = rf_label4(o, H, W, lab, &C, 0);
        if (n < 0) { rc = -1; break; }
        for (size_t i = 0; i < N; i++) o[i] = (lab[i] && C.area[lab[i]] >= amin) ? 255 : 0;
        rf_comps_free(&C);
    }
    free(g); free(m); free(c); free(lab);
    return rc;
}
