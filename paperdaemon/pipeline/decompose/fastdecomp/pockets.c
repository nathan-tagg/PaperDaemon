/* rm_paint.decompose's pocket loop in one pass: every pocket of paper or tone enclosed by color (a 4-connected
 * component of `pockets`, in rmb_npops.components' order: largest first, equal areas by first raster pixel) takes
 * the color key that owns most of its ring -- the pixels its k x k dilation adds, the edge replicated as PIL's
 * MaxFilter and scipy's mode="nearest" do, within the component's crop (its box with a 1-px margin), on the grid.
 * Ties go to the first key in the caller's order; a ring that touches no key leaves the pocket alone. The pockets
 * are taken one after the other and each writes 255 into its winner's array, so a later ring sees what an earlier
 * pocket was given -- the Python's order exactly.
 */
#include <stdlib.h>
#include <string.h>
#include "rmfast.h"

RF_API int32_t rf_components(const uint8_t *m, int32_t H, int32_t W, int32_t min_span, int64_t min_area, int64_t **info, uint8_t **crops, int64_t *crops_len);
RF_API void rf_free(void *p);

/* keys: nkeys writable (H, W) uint8 arrays, C order. Returns the number of pockets that took a color, -1 on no
 * memory. */
RF_API int32_t rf_pockets(const uint8_t *pockets, int32_t H, int32_t W, int32_t k, int32_t nkeys, uint8_t **keys) {
    int64_t *info = NULL, total = 0;
    uint8_t *crops = NULL;
    int32_t n = rf_components(pockets, H, W, 1, 0, &info, &crops, &total);
    if (n < 0) return -1;
    int32_t r = k / 2, given = 0;
    size_t cap = 0;
    uint8_t *hm = NULL, *dm = NULL;
    int64_t *cnt = (int64_t *)malloc(sizeof(int64_t) * (size_t)(nkeys > 0 ? nkeys : 1));
    if (!cnt) { rf_free(info); rf_free(crops); return -1; }
    int64_t off = 0;
    for (int32_t t = 0; t < n; t++) {
        int32_t x0 = (int32_t)info[5 * t + 1], y0 = (int32_t)info[5 * t + 2];
        int32_t cw = (int32_t)info[5 * t + 3] + 2, ch = (int32_t)info[5 * t + 4] + 2;
        const uint8_t *c = crops + off;
        size_t sz = (size_t)cw * ch;
        off += (int64_t)sz;
        if (sz > cap) {
            free(hm); free(dm);
            cap = sz;
            hm = (uint8_t *)malloc(cap);
            dm = (uint8_t *)malloc(cap);
            if (!hm || !dm) { free(hm); free(dm); free(cnt); rf_free(info); rf_free(crops); return -1; }
        }
        /* the k x k maximum, separable: rows then columns, each window clipped to the crop (= edge replicated) */
        for (int32_t i = 0; i < ch; i++) {
            const uint8_t *row = c + (size_t)i * cw;
            uint8_t *out = hm + (size_t)i * cw;
            for (int32_t j = 0; j < cw; j++) {
                int32_t a = j - r < 0 ? 0 : j - r, b = j + r > cw - 1 ? cw - 1 : j + r;
                uint8_t v = 0;
                for (int32_t q = a; q <= b; q++) if (row[q] > v) v = row[q];
                out[j] = v;
            }
        }
        for (int32_t i = 0; i < ch; i++) {
            int32_t a = i - r < 0 ? 0 : i - r, b = i + r > ch - 1 ? ch - 1 : i + r;
            uint8_t *out = dm + (size_t)i * cw;
            for (int32_t j = 0; j < cw; j++) {
                uint8_t v = 0;
                for (int32_t q = a; q <= b; q++) if (hm[(size_t)q * cw + j] > v) v = hm[(size_t)q * cw + j];
                out[j] = v;
            }
        }
        for (int32_t e = 0; e < nkeys; e++) cnt[e] = 0;
        for (int32_t i = 0; i < ch; i++) {
            int32_t gy = i + y0 - 1;
            if (gy < 0 || gy >= H) continue;
            for (int32_t j = 0; j < cw; j++) {
                size_t p = (size_t)i * cw + j;
                if (!dm[p] || c[p]) continue;                  /* the ring: dilated, not the pocket */
                int32_t gx = j + x0 - 1;
                if (gx < 0 || gx >= W) continue;
                size_t g = (size_t)gy * W + gx;
                for (int32_t e = 0; e < nkeys; e++) if (keys[e][g]) cnt[e]++;
            }
        }
        int32_t best = -1;
        int64_t best_n = 0;
        for (int32_t e = 0; e < nkeys; e++) if (cnt[e] > best_n) { best = e; best_n = cnt[e]; }
        if (best < 0) continue;
        given++;
        uint8_t *dst = keys[best];
        for (int32_t i = 0; i < ch; i++) {
            int32_t gy = i + y0 - 1;
            if (gy < 0 || gy >= H) continue;
            for (int32_t j = 0; j < cw; j++) {
                if (!c[(size_t)i * cw + j]) continue;
                int32_t gx = j + x0 - 1;
                if (gx < 0 || gx >= W) continue;
                dst[(size_t)gy * W + gx] = 255;
            }
        }
    }
    free(hm); free(dm); free(cnt);
    if (info) rf_free(info);
    if (crops) rf_free(crops);
    return given;
}

/* rm_paint.decompose's TONE pockets: every component of `inv` (the inverted color union, expanded by 1 px: Hi x Wi =
 * (H + 2) x (W + 2)), in rmb_npops.components' order, that does not touch the outside (its crop's offset <= 0 or its
 * crop reaching the far edge) gives its pixels on the grid that are tone and at least `thr` light (the Python's
 * float64 comparison), in raster order. A pocket with at least half its area so selected is reported: info gets
 * (area, n, sum r, sum g, sum b) and xy its n (gx, gy) pairs. Returns the number reported, -1 on no memory; *info
 * and *xy are rf_free'd by the caller. */
RF_API int32_t rf_tone_pockets(const uint8_t *inv, int32_t Hi, int32_t Wi, const uint8_t *tone, const uint8_t *lum,
                               const uint8_t *rgb, double thr, int64_t **info_out, int64_t **xy_out) {
    int64_t *info = NULL, total = 0;
    uint8_t *crops = NULL;
    int32_t H = Hi - 2, W = Wi - 2;
    int32_t n = rf_components(inv, Hi, Wi, 1, 0, &info, &crops, &total);
    *info_out = NULL; *xy_out = NULL;
    if (n < 0) return -1;
    int64_t *oi = (int64_t *)malloc(sizeof(int64_t) * 5 * (size_t)(n > 0 ? n : 1));
    size_t cap = 1024, used = 0;
    int64_t *xy = (int64_t *)malloc(sizeof(int64_t) * cap);
    *info_out = NULL; *xy_out = NULL;
    if (!oi || !xy) { free(oi); free(xy); if (info) rf_free(info); if (crops) rf_free(crops); return -1; }
    int32_t got = 0;
    int64_t off = 0;
    for (int32_t t = 0; t < n; t++) {
        int64_t area = info[5 * t];
        int32_t x0 = (int32_t)info[5 * t + 1], y0 = (int32_t)info[5 * t + 2];
        int32_t cw = (int32_t)info[5 * t + 3] + 2, ch = (int32_t)info[5 * t + 4] + 2;
        const uint8_t *c = crops + off;
        off += (int64_t)cw * ch;
        int32_t px = x0 - 1, py = y0 - 1;                     /* the crop's offset in inv */
        if (px <= 0 || py <= 0 || px + cw >= W + 2 || py + ch >= H + 2) continue;
        size_t start = used;
        int64_t sr = 0, sg = 0, sb = 0, cnt = 0;
        for (int32_t i = 0; i < ch; i++) {
            int32_t gy = i + py - 1;
            for (int32_t j = 0; j < cw; j++) {
                if (!c[(size_t)i * cw + j]) continue;
                int32_t gx = j + px - 1;
                if (gx < 0 || gx >= W || gy < 0 || gy >= H) continue;
                size_t g = (size_t)gy * W + gx;
                if (!tone[g] || !((double)lum[g] >= thr)) continue;
                if (used + 2 > cap) {
                    size_t nc = cap * 2;
                    int64_t *nx = (int64_t *)realloc(xy, sizeof(int64_t) * nc);
                    if (!nx) { free(oi); free(xy); rf_free(info); rf_free(crops); return -1; }
                    xy = nx; cap = nc;
                }
                xy[used++] = gx; xy[used++] = gy;
                sr += rgb[3 * g]; sg += rgb[3 * g + 1]; sb += rgb[3 * g + 2];
                cnt++;
            }
        }
        if ((double)cnt < 0.5 * (double)area) { used = start; continue; }
        oi[5 * got] = area; oi[5 * got + 1] = cnt; oi[5 * got + 2] = sr; oi[5 * got + 3] = sg; oi[5 * got + 4] = sb;
        got++;
    }
    if (info) rf_free(info);
    if (crops) rf_free(crops);
    *info_out = oi; *xy_out = xy;
    return got;
}
