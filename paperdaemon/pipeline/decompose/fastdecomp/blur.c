/* blur.c -- Pillow's box blur and Gaussian blur, and the painter's gap densities built on them (GEOMETRY code: the
 * blurred masks decide which class paints a pixel).
 *
 * Reproduces Pillow 12.3.0 src/libImaging/BoxBlur.c (HPND; see THIRD_PARTY_NOTICES.txt): ImagingBoxBlur (n passes of
 * ImagingHorizontalBoxBlur along the rows, then n along the columns, which Pillow runs on a transposed copy -- the
 * same arithmetic line by line) and ImagingGaussianBlur (_gaussian_blur_radius, 3 passes), for 8-bit images of 1 to 4
 * interleaved channels. The fixed-point weights and rounding are Pillow's: ww = 2^24 / (2 r + 1) computed in float,
 * fw the fractional edge weight, out = (acc * ww + (edge pixels) * fw + 2^23) >> 24 in 32-bit unsigned arithmetic.
 * Lines are independent, so rows (first pass) and column ranges (second pass) are split over the threads.
 *
 *   rf_box_blur     ImageFilter.BoxBlur(r) / ImageFilter.GaussianBlur(r) on an "L" or "RGB" image
 *   rf_gap_density  rm_paint.decompose's gap densities: per color class, the anchor (the class's 4-connected pieces
 *                   at least min_span wide or tall: rmb_npops.components(mask, min_span) pasted into a blank image)
 *                   and, when it has a pixel, its BoxBlur(r); classes on all threads, each into its own plane.
 * Identity: checked against the reference (random and real images, many radii, against Pillow) and the call-by-call painter
 * check of the gap densities; see the port's log. */
#include <math.h>
#include <stdatomic.h>
#include <stdlib.h>
#include <string.h>
#include "rmfast.h"
#include "internal.h"

typedef struct { int radius, edgeA, edgeB, last; uint32_t ww, fw; } boxp;

/* ImagingHorizontalBoxBlur's constants for a line of `size` pixels */
static boxp box_params(float fr, int size) {
    boxp p;
    p.radius = (int)fr;
    p.ww = (uint32_t)((float)(uint32_t)(1 << 24) / (fr * 2 + 1));
    p.fw = ((uint32_t)(1 << 24) - (uint32_t)(p.radius * 2 + 1) * p.ww) / 2;
    p.edgeA = p.radius + 1 < size ? p.radius + 1 : size;
    p.edgeB = size - p.radius - 1 > 0 ? size - p.radius - 1 : 0;
    p.last = size - 1;
    return p;
}

/* ImagingLineBoxBlur8 on one line whose k-th pixel is in[k * st]; out[k * st] gets the result */
static void line_blur(uint8_t *out, const uint8_t *in, ptrdiff_t st, const boxp *p) {
    const int r = p->radius, eA = p->edgeA, eB = p->edgeB, last = p->last;
    const uint32_t ww = p->ww, fw = p->fw;
#define IN(k) ((uint32_t)in[(ptrdiff_t)(k) * st])
#define MOVE(sub, add) acc += IN(add) - IN(sub)
#define SAVE(x, left, right) out[(ptrdiff_t)(x) * st] = (uint8_t)((acc * ww + (IN(left) + IN(right)) * fw + (1u << 23)) >> 24)
    uint32_t acc = IN(0) * (uint32_t)(r + 1);
    for (int x = 0; x < eA - 1; x++) acc += IN(x);
    acc += IN(last) * (uint32_t)(r - eA + 1);
    if (eA <= eB) {
        for (int x = 0; x < eA; x++) { MOVE(0, x + r); SAVE(x, 0, x + r + 1); }
        for (int x = eA; x < eB; x++) { MOVE(x - r - 1, x + r); SAVE(x, x - r - 1, x + r + 1); }
        for (int x = eB; x <= last; x++) { MOVE(x - r - 1, last); SAVE(x, x - r - 1, last); }
    } else {
        for (int x = 0; x < eB; x++) { MOVE(0, x + r); SAVE(x, 0, x + r + 1); }
        for (int x = eB; x < eA; x++) { MOVE(0, last); SAVE(x, 0, last); }
        for (int x = eA; x <= last; x++) { MOVE(x - r - 1, last); SAVE(x, x - r - 1, last); }
    }
#undef IN
#undef MOVE
#undef SAVE
}

/* the second pass: every column of a W*nch-byte-wide image at once, row by row (each column's arithmetic is
 * line_blur's: the accumulator per column, the same pixel indices). Columns [c0, c1). acc: c1 - c0 slots. */
static void cols_blur(uint8_t *out, const uint8_t *in, size_t rowb, size_t c0, size_t c1, const boxp *p, uint32_t *acc) {
    const int r = p->radius, eA = p->edgeA, eB = p->edgeB, last = p->last;
    const uint32_t ww = p->ww, fw = p->fw;
    const size_t n = c1 - c0;
#define ROW(k) (in + (size_t)(k) * rowb + c0)
    {
        const uint8_t *r0 = ROW(0), *rl = ROW(last);
        for (size_t c = 0; c < n; c++) acc[c] = (uint32_t)r0[c] * (uint32_t)(r + 1);
        for (int k = 0; k < eA - 1; k++) { const uint8_t *rk = ROW(k); for (size_t c = 0; c < n; c++) acc[c] += rk[c]; }
        for (size_t c = 0; c < n; c++) acc[c] += (uint32_t)rl[c] * (uint32_t)(r - eA + 1);
    }
#define STEP(y, sub, add, left, right) do { \
        const uint8_t *rs = ROW(sub), *ra = ROW(add), *rL = ROW(left), *rR = ROW(right); \
        uint8_t *o = out + (size_t)(y) * rowb + c0; \
        for (size_t c = 0; c < n; c++) { \
            acc[c] += (uint32_t)ra[c] - (uint32_t)rs[c]; \
            o[c] = (uint8_t)((acc[c] * ww + ((uint32_t)rL[c] + (uint32_t)rR[c]) * fw + (1u << 23)) >> 24); \
        } } while (0)
    if (eA <= eB) {
        for (int y = 0; y < eA; y++) STEP(y, 0, y + r, 0, y + r + 1);
        for (int y = eA; y < eB; y++) STEP(y, y - r - 1, y + r, y - r - 1, y + r + 1);
        for (int y = eB; y <= last; y++) STEP(y, y - r - 1, last, y - r - 1, last);
    } else {
        for (int y = 0; y < eB; y++) STEP(y, 0, y + r, 0, y + r + 1);
        for (int y = eB; y < eA; y++) STEP(y, 0, last, 0, last);
        for (int y = eA; y <= last; y++) STEP(y, y - r - 1, last, y - r - 1, last);
    }
#undef STEP
#undef ROW
}

/* one blur job: the passes of one direction over a band of rows (dir 0) or of byte columns (dir 1) */
typedef struct {
    const uint8_t *src; uint8_t *dst; uint8_t *tmp;     /* tmp: a second image-sized buffer for the passes */
    int32_t H, W, nch, n;
    boxp ph, pv;
    int dir;
    atomic_int next;
    atomic_int oom;                                       /* set by any worker that ran out of memory */
} blurjob;

#define BAND_ROWS 64
#define BAND_COLS 4096

static void blur_worker(void *arg, int tid) {
    (void)tid;
    blurjob *J = (blurjob *)arg;
    size_t rowb = (size_t)J->W * J->nch;
    if (J->dir == 0) {
        uint8_t *line = (uint8_t *)malloc(rowb > 0 ? rowb : 1);
        if (!line) { atomic_store(&J->oom, 1); return; }
        for (;;) {
            int32_t y0 = atomic_fetch_add(&J->next, BAND_ROWS);
            if (y0 >= J->H) break;
            int32_t y1 = y0 + BAND_ROWS < J->H ? y0 + BAND_ROWS : J->H;
            for (int32_t y = y0; y < y1; y++) {
                /* pass 1 from src, passes 2..n in place through `line` (Pillow's lineOut + commit) */
                for (int ch = 0; ch < J->nch; ch++)
                    line_blur(J->dst + (size_t)y * rowb + ch, J->src + (size_t)y * rowb + ch, J->nch, &J->ph);
                for (int i = 1; i < J->n; i++) {
                    for (int ch = 0; ch < J->nch; ch++) line_blur(line + ch, J->dst + (size_t)y * rowb + ch, J->nch, &J->ph);
                    memcpy(J->dst + (size_t)y * rowb, line, rowb);
                }
            }
        }
        free(line);
    } else {
        uint32_t *acc = (uint32_t *)malloc(sizeof(uint32_t) * BAND_COLS);
        if (!acc) { atomic_store(&J->oom, 1); return; }
        for (;;) {
            size_t c0 = (size_t)atomic_fetch_add(&J->next, BAND_COLS);
            if (c0 >= rowb) break;
            size_t c1 = c0 + BAND_COLS < rowb ? c0 + BAND_COLS : rowb;
            /* pass i reads the previous pass's columns (in J->src for the first) and writes the other buffer;
               the passes alternate dst / tmp so the last lands in dst */
            const uint8_t *from = J->src;
            for (int i = 0; i < J->n; i++) {
                uint8_t *to = ((J->n - 1 - i) % 2 == 0) ? J->dst : J->tmp;
                cols_blur(to, from, rowb, c0, c1, &J->pv, acc);
                from = to;
            }
        }
        free(acc);
    }
}

/* a blur's working buffers, kept by the caller across blurs: mid holds the row passes' result when column passes
 * follow, tmp every column pass but the last when there are several */
typedef struct { uint8_t *tmp, *mid; size_t cap_tmp, cap_mid; } blur_scratch;

static uint8_t *scratch_get(uint8_t **p, size_t *cap, size_t n) {
    if (*cap < n) {
        uint8_t *q = (uint8_t *)realloc(*p, n);
        if (!q) return NULL;
        *p = q; *cap = n;
    }
    return *p;
}

/* Pillow's ImagingBoxBlur(out, in, xr, yr, n) for an 8-bit image of nch interleaved channels (H x W pixels). in and
 * out may not overlap. Returns 0, or -1 when memory ran out. */
static int box_blur(const uint8_t *in, uint8_t *out, int32_t H, int32_t W, int32_t nch, float xr, float yr, int n, int threads,
                    blur_scratch *S) {
    size_t N = (size_t)H * W * nch;
    if (!H || !W) return 0;
    if (xr == 0 && yr == 0) { memcpy(out, in, N); return 0; }
    uint8_t *tmp = NULL, *mid = NULL;
    if (yr != 0 && n > 1 && !(tmp = scratch_get(&S->tmp, &S->cap_tmp, N))) return -1;
    if (yr != 0 && xr != 0 && !(mid = scratch_get(&S->mid, &S->cap_mid, N))) return -1;
    blurjob J;
    memset(&J, 0, sizeof(J));
    J.H = H; J.W = W; J.nch = nch; J.n = n;
    atomic_init(&J.oom, 0);
    int nt = threads;
    if (xr != 0) {
        J.src = in; J.dst = yr != 0 ? mid : out; J.dir = 0; J.ph = box_params(xr, W);
        atomic_init(&J.next, 0);
        int t = nt < (H + BAND_ROWS - 1) / BAND_ROWS ? nt : (H + BAND_ROWS - 1) / BAND_ROWS;
        rf_parallel(t > 0 ? t : 1, blur_worker, &J);
        if (atomic_load(&J.oom)) return -1;
    }
    if (yr != 0) {
        J.src = xr != 0 ? mid : in; J.dst = out; J.tmp = tmp; J.dir = 1; J.pv = box_params(yr, H);
        atomic_init(&J.next, 0);
        size_t rowb = (size_t)W * nch;
        size_t bands = (rowb + BAND_COLS - 1) / BAND_COLS;
        int t = (size_t)nt < bands ? nt : (int)bands;
        rf_parallel(t > 0 ? t : 1, blur_worker, &J);
        if (atomic_load(&J.oom)) return -1;
    }
    return 0;
}

/* ImagingGaussianBlur's box radius (Pillow's _gaussian_blur_radius, float with the double literals as written) */
static float gaussian_radius(float radius, int passes) {
    float sigma2, L, l, a;
    sigma2 = radius * radius / passes;
    L = (float)sqrt(12.0 * sigma2 + 1.0);
    l = (float)floor((L - 1.0) / 2.0);
    a = (2 * l + 1) * (l * (l + 1) - 3 * sigma2);
    a /= 6 * (sigma2 - (l + 1) * (l + 1));
    return l + a;
}

/* gaussian != 0: ImageFilter.GaussianBlur(radius) (3 passes); else ImageFilter.BoxBlur(radius) (1 pass). The radius
 * arrives as the float Pillow parses it ("(ff)"). A zero radius is the image's copy, as ImageFilter does. */
RF_API int32_t rf_box_blur(const uint8_t *in, uint8_t *out, int32_t H, int32_t W, int32_t nch, float radius, int32_t gaussian) {
    if (radius == 0) { memcpy(out, in, (size_t)H * W * nch); return 0; }
    blur_scratch S = {0};
    int rc;
    if (gaussian) {
        float r = gaussian_radius(radius, 3);
        rc = box_blur(in, out, H, W, nch, r, r, 3, rf_threads(), &S);
    } else rc = box_blur(in, out, H, W, nch, radius, radius, 1, rf_threads(), &S);
    free(S.tmp); free(S.mid);
    return rc;
}

/* ------------------------------------------------------------------ the gap densities */
typedef struct {
    const uint8_t *const *masks;
    uint8_t *const *dens;
    uint8_t *has;
    int32_t nk, H, W, min_span;
    float radius;
    atomic_int next;
    atomic_int oom;                                       /* set by any worker that ran out of memory */
} gapjob;

static void gap_worker(void *arg, int tid) {
    (void)tid;
    gapjob *G = (gapjob *)arg;
    size_t N = (size_t)G->H * G->W;
    int32_t *lab = (int32_t *)malloc(sizeof(int32_t) * (N ? N : 1));
    uint8_t *anchor = (uint8_t *)malloc(N ? N : 1);
    uint8_t *keep = NULL;
    size_t cap_keep = 0;
    blur_scratch S = {0};                                 /* this worker's blur buffers, reused class to class */
    if (!lab || !anchor) { atomic_store(&G->oom, 1); free(lab); free(anchor); return; }
    for (;;) {
        int32_t k = atomic_fetch_add(&G->next, 1);
        if (k >= G->nk) break;
        rf_comps C;
        int32_t n = rf_label4(G->masks[k], G->H, G->W, lab, &C, 0);
        if (n < 0 || (n > 0 && (!C.x0 || !C.x1 || !C.y0 || !C.y1))) { atomic_store(&G->oom, 1); rf_comps_free(&C); continue; }
        if ((size_t)n + 1 > cap_keep) {
            uint8_t *nk_ = (uint8_t *)realloc(keep, (size_t)n + 1);
            if (!nk_) { atomic_store(&G->oom, 1); rf_comps_free(&C); continue; }
            keep = nk_; cap_keep = (size_t)n + 1;
        }
        /* rmb_npops.components(mask, min_span): span = the bounding box's larger side; every piece has area >= 1 */
        keep[0] = 0;
        for (int32_t i = 1; i <= n; i++) {
            int32_t bw = C.x1[i] - C.x0[i] + 1, bh = C.y1[i] - C.y0[i] + 1;
            keep[i] = (bw > bh ? bw : bh) >= G->min_span;
        }
        rf_comps_free(&C);
        int any = 0;
        for (size_t i = 0; i < N; i++) { uint8_t v = keep[lab[i]] ? 255 : 0; anchor[i] = v; any |= v; }
        G->has[k] = any != 0;
        if (any && box_blur(anchor, G->dens[k], G->H, G->W, 1, G->radius, G->radius, 1, 1, &S)) atomic_store(&G->oom, 1);
    }
    free(lab); free(anchor); free(keep); free(S.tmp); free(S.mid);
}

RF_API int32_t rf_gap_density(const uint8_t *const *masks, int32_t nk, int32_t H, int32_t W, int32_t min_span, float radius,
                              uint8_t *const *dens, uint8_t *has) {
    gapjob G;
    memset(&G, 0, sizeof(G));
    G.masks = masks; G.dens = dens; G.has = has; G.nk = nk; G.H = H; G.W = W; G.min_span = min_span; G.radius = radius;
    atomic_init(&G.next, 0);
    atomic_init(&G.oom, 0);
    int nt = rf_threads();
    if (nt > nk) nt = nk;
    if (nt < 1) nt = 1;
    rf_parallel(nt, gap_worker, &G);
    return atomic_load(&G.oom) ? -1 : 0;
}
