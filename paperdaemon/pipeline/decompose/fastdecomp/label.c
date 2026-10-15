/* 4-connected component labeling of a binary mask, two passes with union-find.
 *
 * Provisional labels are handed out in raster order and every union keeps the smaller root, so a component's root is
 * the provisional label of its first pixel in raster order; final labels 1..n are numbered by that first pixel. The
 * caller gets, per component, its area, its bounding box and its first raster index -- what rmb_npops.components
 * sorts by -- and, on request, the pixels of every component in raster order. Every allocation is checked: a failure
 * returns -1 with nothing left allocated. */
#include <stdlib.h>
#include <string.h>
#include "rmfast.h"
#include "internal.h"

static int32_t find_root(int32_t *P, int32_t x) {
    int32_t r = x;
    while (P[r] != r) r = P[r];
    while (P[x] != r) { int32_t nx = P[x]; P[x] = r; x = nx; }
    return r;
}

static void unite(int32_t *P, int32_t a, int32_t b) {
    a = find_root(P, a); b = find_root(P, b);
    if (a < b) P[b] = a; else if (b < a) P[a] = b;
}

int32_t rf_label4(const uint8_t *m, int32_t H, int32_t W, int32_t *lab, rf_comps *C, int want_pixels) {
    size_t N = (size_t)H * W;
    memset(C, 0, sizeof(*C));
    int32_t cap = 1024, next = 1;
    int32_t *P = (int32_t *)malloc(sizeof(int32_t) * cap);
    if (!P) return -1;
    P[0] = 0;
    for (int32_t y = 0; y < H; y++) {
        const uint8_t *row = m + (size_t)y * W;
        int32_t *L = lab + (size_t)y * W, *U = y ? lab + (size_t)(y - 1) * W : NULL;
        for (int32_t x = 0; x < W; x++) {
            if (!row[x]) { L[x] = 0; continue; }
            int32_t a = x ? L[x - 1] : 0, b = U ? U[x] : 0;
            if (a && b) { L[x] = a < b ? a : b; if (a != b) unite(P, a, b); }
            else if (a) L[x] = a;
            else if (b) L[x] = b;
            else {
                if (next == cap) {
                    /* at most one provisional label per pixel: N < 2^31 keeps cap * 2 in range */
                    int32_t *Q = (int32_t *)realloc(P, sizeof(int32_t) * (size_t)cap * 2);
                    if (!Q) { free(P); return -1; }
                    P = Q; cap *= 2;
                }
                P[next] = next; L[x] = next++;
            }
        }
    }
    /* final labels: roots in increasing provisional order = first raster pixel order */
    int32_t *F = (int32_t *)malloc(sizeof(int32_t) * (size_t)next);
    if (!F) { free(P); return -1; }
    int32_t n = 0;
    F[0] = 0;
    for (int32_t i = 1; i < next; i++) {
        int32_t r = find_root(P, i);
        F[i] = (r == i) ? ++n : F[r];
    }
    free(P);
    C->n = n;
    C->area = (int64_t *)calloc((size_t)n + 1, sizeof(int64_t));
    C->x0 = (int32_t *)malloc(sizeof(int32_t) * (n + 1)); C->x1 = (int32_t *)malloc(sizeof(int32_t) * (n + 1));
    C->y0 = (int32_t *)malloc(sizeof(int32_t) * (n + 1)); C->y1 = (int32_t *)malloc(sizeof(int32_t) * (n + 1));
    C->first = (int64_t *)malloc(sizeof(int64_t) * (n + 1));
    if (!C->area || !C->x0 || !C->x1 || !C->y0 || !C->y1 || !C->first) { free(F); rf_comps_free(C); return -1; }
    for (int32_t i = 0; i <= n; i++) { C->x0[i] = W; C->x1[i] = -1; C->y0[i] = H; C->y1[i] = -1; C->first[i] = -1; }
    for (int32_t y = 0; y < H; y++) {
        int32_t *L = lab + (size_t)y * W;
        for (int32_t x = 0; x < W; x++) {
            if (!L[x]) continue;
            int32_t k = F[L[x]];
            L[x] = k;
            C->area[k]++;
            if (C->first[k] < 0) C->first[k] = (int64_t)y * W + x;
            if (x < C->x0[k]) C->x0[k] = x;
            if (x > C->x1[k]) C->x1[k] = x;
            if (y < C->y0[k]) C->y0[k] = y;
            if (y > C->y1[k]) C->y1[k] = y;
        }
    }
    free(F);
    if (want_pixels) {
        C->start = (int64_t *)malloc(sizeof(int64_t) * (n + 2));
        if (!C->start) { rf_comps_free(C); return -1; }
        C->start[0] = 0; C->start[1] = 0;
        for (int32_t k = 1; k <= n; k++) C->start[k + 1] = C->start[k] + C->area[k];
        C->pix = (int32_t *)malloc(sizeof(int32_t) * (size_t)(C->start[n + 1] ? C->start[n + 1] : 1));
        int64_t *fill = (int64_t *)malloc(sizeof(int64_t) * (n + 1));
        if (!C->pix || !fill) { free(fill); rf_comps_free(C); return -1; }
        for (int32_t k = 0; k <= n; k++) fill[k] = C->start[k];
        for (size_t i = 0; i < N; i++) if (lab[i]) C->pix[fill[lab[i]]++] = (int32_t)i;
        free(fill);
    }
    return n;
}

void rf_comps_free(rf_comps *C) {
    free(C->area); free(C->x0); free(C->x1); free(C->y0); free(C->y1); free(C->first); free(C->start); free(C->pix);
    memset(C, 0, sizeof(*C));
}

/* rmb_npops.components: the 4-connected components at least `min_span` wide or tall and `min_area` (at least 1) big,
 * largest first, equal areas in the order of their first raster pixel; each one's crop (its box with a 1-pixel margin,
 * 255 on its pixels) laid end to end in one buffer. info: 5 per component (area, x0, y0, width, height of the box
 * without the margin). Returns the count; *info and *crops are rf_free'd by the caller. */
typedef struct { int64_t area; int32_t k; } carea;
static int cmp_carea(const void *a, const void *b) {
    const carea *x = (const carea *)a, *y = (const carea *)b;
    if (x->area != y->area) return x->area > y->area ? -1 : 1;
    return x->k < y->k ? -1 : (x->k > y->k);
}

RF_API int32_t rf_components(const uint8_t *m, int32_t H, int32_t W, int32_t min_span, int64_t min_area, int64_t **info, uint8_t **crops, int64_t *crops_len) {
    size_t N = (size_t)H * W;
    *info = NULL; *crops = NULL; *crops_len = 0;
    int32_t *lab = (int32_t *)malloc(sizeof(int32_t) * (N ? N : 1));
    if (!lab) return -1;
    rf_comps C;
    int32_t n = rf_label4(m, H, W, lab, &C, 0);
    if (n < 0) { free(lab); return -1; }
    int64_t amin = min_area > 1 ? min_area : 1;
    carea *keep = (carea *)malloc(sizeof(carea) * (n ? n : 1));
    if (!keep) { free(lab); rf_comps_free(&C); return -1; }
    int32_t nk = 0;
    for (int32_t k = 1; k <= n; k++) {
        int32_t span = C.y1[k] - C.y0[k] + 1, ws = C.x1[k] - C.x0[k] + 1;
        if (ws > span) span = ws;
        if (span >= min_span && C.area[k] >= amin) { keep[nk].area = C.area[k]; keep[nk].k = k; nk++; }
    }
    qsort(keep, nk, sizeof(carea), cmp_carea);
    int64_t total = 0;
    for (int32_t t = 0; t < nk; t++) { int32_t k = keep[t].k; total += (int64_t)(C.y1[k] - C.y0[k] + 3) * (C.x1[k] - C.x0[k] + 3); }
    int64_t *inf = (int64_t *)malloc(sizeof(int64_t) * 5 * (nk ? nk : 1));
    uint8_t *buf = (uint8_t *)calloc((size_t)(total ? total : 1), 1);
    if (!inf || !buf) { free(inf); free(buf); free(keep); free(lab); rf_comps_free(&C); return -1; }
    int64_t off = 0;
    for (int32_t t = 0; t < nk; t++) {
        int32_t k = keep[t].k, x0 = C.x0[k], y0 = C.y0[k], w = C.x1[k] - x0 + 1, h = C.y1[k] - y0 + 1, cw = w + 2;
        inf[5 * t] = C.area[k]; inf[5 * t + 1] = x0; inf[5 * t + 2] = y0; inf[5 * t + 3] = w; inf[5 * t + 4] = h;
        for (int32_t y = 0; y < h; y++) {
            const int32_t *L = lab + (size_t)(y0 + y) * W + x0;
            uint8_t *row = buf + off + (int64_t)(y + 1) * cw + 1;
            for (int32_t x = 0; x < w; x++) if (L[x] == k) row[x] = 255;
        }
        off += (int64_t)(h + 2) * cw;
    }
    free(keep); free(lab); rf_comps_free(&C);
    *info = inf; *crops = buf; *crops_len = total;
    return nk;
}
