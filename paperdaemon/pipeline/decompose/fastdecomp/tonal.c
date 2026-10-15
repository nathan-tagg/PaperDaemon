/* tonal.c -- rmb_resolution.tonal_ink / tonal_mask (DECISION code: which dark pixels stay ink and which become
 * washes of their ladder color).
 *
 *   rf_tonal_protect  tonal_mask: ink = (_ink != 0) & (L > black_l * 2.55) (Pillow's L conversion; the uint8 values
 *                     compared with the Python float in float64, as numpy does), its 4-connected pieces
 *                     (scipy.ndimage.label's default cross), the Euclidean distance of every ink pixel to the nearest
 *                     non-ink pixel of the zero-padded grid (scipy's distance_transform_edt is exact: sqrt of the
 *                     integer squared distance, which Meijster's algorithm computes here in integers), and a piece is
 *                     fine when 2 * its largest distance <= max_ink_diameter; protect = ink outside the fine pieces.
 *                     Then the protected pixels' ladder colors (ladder[r], ladder[g], ladder[b]) packed as the
 *                     Python packs them, the palette = their sorted distinct values, and each pixel's palette index.
 *   rf_tonal_apply    the masks rebuilt as tonal_ink rebuilds them: every mask loses the protected pixels, then each
 *                     protected pixel is added to the mask of its palette color (an existing key or a new one).
 * Identity: checked against the reference (every call of real model runs through rmb_resolution.tonal_ink and the C; masks,
 * key order and report compared). */
#include <math.h>
#include <stdatomic.h>
#include <stdlib.h>
#include <string.h>
#include "rmfast.h"
#include "internal.h"

static int64_t floordiv64(int64_t a, int64_t b) {          /* b > 0 */
    int64_t q = a / b, r = a % b;
    return (r != 0 && (r < 0)) ? q - 1 : q;
}

typedef struct {
    const uint8_t *fg; int32_t m, n;                        /* the padded grid: m rows, n columns; fg = ink */
    int64_t *g;                                             /* column distances, then the squared distances */
    atomic_int next; int stage; atomic_int oom;
} edtjob;
#define EDT_BAND 64

/* Meijster, Roerdink, Hesselink (2000): exact squared Euclidean distances to the nearest background pixel */
static void edt_worker(void *arg, int tid) {
    (void)tid;
    edtjob *J = (edtjob *)arg;
    const int32_t m = J->m, n = J->n;
    const int64_t inf = (int64_t)m + n;
    if (J->stage == 0) {
        for (;;) {
            int32_t x0 = atomic_fetch_add(&J->next, EDT_BAND);
            if (x0 >= n) break;
            int32_t x1 = x0 + EDT_BAND < n ? x0 + EDT_BAND : n;
            for (int32_t x = x0; x < x1; x++) {
                int64_t *g = J->g;
                g[x] = J->fg[x] ? inf : 0;
                for (int32_t y = 1; y < m; y++) g[(size_t)y * n + x] = J->fg[(size_t)y * n + x] ? g[(size_t)(y - 1) * n + x] + 1 : 0;
                for (int32_t y = m - 2; y >= 0; y--)
                    if (g[(size_t)(y + 1) * n + x] < g[(size_t)y * n + x]) g[(size_t)y * n + x] = g[(size_t)(y + 1) * n + x] + 1;
            }
        }
        return;
    }
    int32_t *s = (int32_t *)malloc(sizeof(int32_t) * (size_t)n), *t = (int32_t *)malloc(sizeof(int32_t) * (size_t)n);
    int64_t *row = (int64_t *)malloc(sizeof(int64_t) * (size_t)n);
    if (!s || !t || !row) { atomic_store(&J->oom, 1); free(s); free(t); free(row); return; }
    for (;;) {
        int32_t y0 = atomic_fetch_add(&J->next, EDT_BAND);
        if (y0 >= m) break;
        int32_t y1 = y0 + EDT_BAND < m ? y0 + EDT_BAND : m;
        for (int32_t y = y0; y < y1; y++) {
            int64_t *G = J->g + (size_t)y * n;
            memcpy(row, G, sizeof(int64_t) * (size_t)n);
#define F(x, i) ((int64_t)((x) - (i)) * ((x) - (i)) + row[i] * row[i])
            int32_t q = 0;
            s[0] = 0; t[0] = 0;
            for (int32_t u = 1; u < n; u++) {
                while (q >= 0 && F(t[q], s[q]) > F(t[q], u)) q--;
                if (q < 0) { q = 0; s[0] = u; }
                else {
                    int32_t i = s[q];
                    int64_t w = 1 + floordiv64((int64_t)u * u - (int64_t)i * i + row[u] * row[u] - row[i] * row[i], 2 * (int64_t)(u - i));
                    if (w < n) { q++; s[q] = u; t[q] = (int32_t)w; }
                }
            }
            for (int32_t u = n - 1; u >= 0; u--) {
                G[u] = F(u, s[q]);
                if (u == t[q]) q--;
            }
#undef F
        }
    }
    free(s); free(t); free(row);
}

static int edt_squared(const uint8_t *fg, int32_t m, int32_t n, int64_t *g) {
    edtjob J;
    memset(&J, 0, sizeof(J));
    J.fg = fg; J.m = m; J.n = n; J.g = g;
    atomic_init(&J.oom, 0);
    int nt = rf_threads();
    for (int stage = 0; stage < 2; stage++) {
        J.stage = stage;
        atomic_init(&J.next, 0);
        int32_t units = stage == 0 ? n : m;
        int bands = (units + EDT_BAND - 1) / EDT_BAND;
        rf_parallel(nt < bands ? nt : bands, edt_worker, &J);
    }
    return atomic_load(&J.oom) ? -1 : 0;
}

/* -> protected pixel count (>= 0), or -1 out of memory. protect: 0/1 per pixel; pidx: the palette index of each
 * protected pixel (-1 elsewhere); palette: up to H * W packed colors, ascending; *npal their count. */
RF_API int64_t rf_tonal_protect(const uint8_t *ink_mask, const uint8_t *rgb, int32_t H, int32_t W, double thr, double max_diam,
                                const uint8_t *ladder, uint8_t *protect, int32_t *pidx, int32_t *palette, int32_t *npal) {
    size_t N = (size_t)H * W;
    int32_t m = H + 2, n = W + 2;
    int64_t result = -1;
    uint8_t *fg = (uint8_t *)calloc((size_t)m * n, 1);
    int64_t *g = (int64_t *)malloc(sizeof(int64_t) * (size_t)m * n);
    int32_t *lab = (int32_t *)malloc(sizeof(int32_t) * (N ? N : 1));
    uint8_t *ink = (uint8_t *)malloc(N ? N : 1);
    int64_t *maxd = NULL;
    uint8_t *seen = NULL;
    rf_comps C;
    memset(&C, 0, sizeof(C));
    *npal = 0;
    if (!fg || !g || !lab || !ink) goto done;
    for (size_t i = 0; i < N; i++) {
        const uint8_t *p = rgb + 3 * i;
        uint8_t L = (uint8_t)(((uint32_t)p[0] * 19595u + (uint32_t)p[1] * 38470u + (uint32_t)p[2] * 7471u + 0x8000u) >> 16);
        ink[i] = ink_mask[i] != 0 && (double)L > thr;
    }
    for (int32_t y = 0; y < H; y++) memcpy(fg + (size_t)(y + 1) * n + 1, ink + (size_t)y * W, (size_t)W);
    if (edt_squared(fg, m, n, g)) goto done;
    int32_t nl = rf_label4(ink, H, W, lab, &C, 0);
    if (nl < 0) goto done;
    maxd = (int64_t *)calloc((size_t)nl + 1, sizeof(int64_t));
    if (!maxd) goto done;
    for (int32_t y = 0; y < H; y++)
        for (int32_t x = 0; x < W; x++) {
            int32_t l = lab[(size_t)y * W + x];
            int64_t d = g[(size_t)(y + 1) * n + x + 1];
            if (l > 0 && d > maxd[l]) maxd[l] = d;
        }
    /* fine: 2 * the piece's largest distance <= max_diam, the distance being sqrt of the squared integer distance */
    int64_t count = 0;
    for (size_t i = 0; i < N; i++) {
        int32_t l = lab[i];
        int fine = l > 0 && 2.0 * sqrt((double)maxd[l]) <= max_diam;
        protect[i] = l > 0 && !fine;
        count += protect[i];
    }
    /* the ladder colors of the protected pixels: their distinct packed values ascending, and each pixel's index */
    seen = (uint8_t *)calloc((size_t)1 << 21, 1);         /* a bit per packed 24-bit color */
    if (!seen) goto done;
    for (size_t i = 0; i < N; i++) if (protect[i]) {
        const uint8_t *p = rgb + 3 * i;
        uint32_t c = ((uint32_t)ladder[p[0]] << 16) | ((uint32_t)ladder[p[1]] << 8) | ladder[p[2]];
        seen[c >> 3] |= (uint8_t)(1u << (c & 7));
    }
    int32_t k = 0;
    for (uint32_t c = 0; c < (1u << 24); c++) if (seen[c >> 3] & (1u << (c & 7))) palette[k++] = (int32_t)c;
    *npal = k;
    for (size_t i = 0; i < N; i++) {
        if (!protect[i]) { pidx[i] = -1; continue; }
        const uint8_t *p = rgb + 3 * i;
        int32_t c = (int32_t)(((uint32_t)ladder[p[0]] << 16) | ((uint32_t)ladder[p[1]] << 8) | ladder[p[2]]);
        int32_t lo = 0, hi = k - 1;
        while (lo < hi) { int32_t mid = lo + (hi - lo) / 2; if (palette[mid] < c) lo = mid + 1; else hi = mid; }
        pidx[i] = lo;
    }
    result = count;
done:
    free(fg); free(g); free(lab); free(ink); free(maxd); free(seen);
    rf_comps_free(&C);
    return result;
}

/* masks_in[0..nin): the current masks; out[0..nout): their new grids (nout >= nin: the first nin rebuild the inputs,
 * the rest are the new palette keys' grids); slot[i]: the output each palette color goes to */
RF_API void rf_tonal_apply(const uint8_t *const *masks_in, int32_t nin, uint8_t *const *out, int32_t nout, const uint8_t *protect,
                           const int32_t *pidx, const int32_t *slot, int32_t H, int32_t W) {
    size_t N = (size_t)H * W;
    for (int32_t k = 0; k < nin; k++) {
        const uint8_t *a = masks_in[k];
        uint8_t *o = out[k];
        for (size_t i = 0; i < N; i++) o[i] = (a[i] != 0 && !protect[i]) ? 255 : 0;
    }
    for (int32_t k = nin; k < nout; k++) memset(out[k], 0, N);
    for (size_t i = 0; i < N; i++) if (protect[i]) out[slot[pidx[i]]][i] = 255;
}
