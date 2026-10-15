/* rm_paint._outline: the marching-squares outline of a mask (rmb_npops.contours at level 128, chained), each chain of
 * six or more points simplified (rmb_npops.simplify, Douglas-Peucker at 0.7), its length summed, the chains at least
 * min_len long (and three points) kept, and the total length of all of them.
 *
 * Python's own arithmetic, reproduced: math.hypot is CPython 3.12's vector_norm (scaled squares as exact double-length
 * products, compensated sum, one differential correction); a chain's length is the builtin sum() of its segment
 * lengths, which since 3.12 is Neumaier's compensated summation; the total is a plain running sum.
 * NO NaN OR INFINITY: every value here is finite by construction -- grid coordinates, half-pixel offsets, chain
 * lengths of them, and (zones.c) means of finite Lab values -- so CPython's NaN and infinity branches of hypot and
 * sum() are left out. Every allocation is checked: a failure returns -1 with nothing left allocated. GEOMETRY code. */
#include <math.h>
#include <stdlib.h>
#include <string.h>
#include <float.h>
#include "rmfast.h"
#include "internal.h"

typedef struct { double hi, lo; } dlen;
static dlen dl_fast_sum(double a, double b) { double x = a + b; dlen r = {x, (a - x) + b}; return r; }
static dlen dl_mul(double x, double y) { double z = x * y; dlen r = {z, fma(x, y, -z)}; return r; }

static double vector_norm2(double *vec, double max) {
    if (max == 0.0) return max;
    int max_e;
    frexp(max, &max_e);
    if (max_e < -1023) {
        vec[0] /= DBL_MIN; vec[1] /= DBL_MIN;
        return DBL_MIN * vector_norm2(vec, max / DBL_MIN);
    }
    double scale = ldexp(1.0, -max_e), csum = 1.0, frac1 = 0.0, frac2 = 0.0, x, h;
    dlen pr, sm;
    for (int i = 0; i < 2; i++) {
        x = vec[i] * scale;
        pr = dl_mul(x, x);
        sm = dl_fast_sum(csum, pr.hi);
        csum = sm.hi;
        frac1 += pr.lo;
        frac2 += sm.lo;
    }
    h = sqrt(csum - 1.0 + (frac1 + frac2));
    pr = dl_mul(-h, h);
    sm = dl_fast_sum(csum, pr.hi);
    csum = sm.hi;
    frac1 += pr.lo;
    frac2 += sm.lo;
    x = csum - 1.0 + (frac1 + frac2);
    h += x / (2.0 * h);
    return h / scale;
}

/* math.hypot(x, y) as CPython 3.12 computes it, for finite x and y (see the top of the file) */
double rf_py_hypot(double x, double y) {
    double v[2] = {fabs(x), fabs(y)}, max = 0.0;
    if (v[0] > max) max = v[0];
    if (v[1] > max) max = v[1];
    return vector_norm2(v, max);
}

RF_API double rf_test_hypot(double x, double y) { return rf_py_hypot(x, y); }

/* sum(math.hypot(p[i+1] - p[i]) for i ...) over m points: 0 for fewer than two; else 0 + the first length, then
 * Neumaier's compensated sum, as CPython 3.12's builtin sum() takes floats */
double rf_py_sum_hypot(const double *xy, int32_t m) {
    if (m < 2) return 0.0;
    double f = rf_py_hypot(xy[2] - xy[0], xy[3] - xy[1]), c = 0.0;
    for (int32_t t = 1; t < m - 1; t++) {
        double x = rf_py_hypot(xy[2 * t + 2] - xy[2 * t], xy[2 * t + 3] - xy[2 * t + 1]);
        double s = f + x;
        if (fabs(f) >= fabs(x)) c += (f - s) + x;
        else c += (x - s) + f;
        f = s;
    }
    if (c != 0.0) f += c;                 /* CPython adds c when it is non-zero and finite: finite here */
    return f;
}

/* rmb_npops.simplify: Douglas-Peucker with an explicit stack, into the caller's keep[] (n) and stack[] (2 (n + 2))
 * -> the points kept */
static int32_t dp_simplify_into(const double *pts, int32_t n, double eps, double *out, uint8_t *keep, int32_t *stack) {
    if (n < 3) { memcpy(out, pts, sizeof(double) * 2 * (size_t)n); return n; }
    memset(keep, 0, (size_t)n);
    int32_t sp = 0;
    keep[0] = keep[n - 1] = 1;
    stack[sp++] = 0; stack[sp++] = n - 1;
    while (sp) {
        int32_t i1 = stack[--sp], i0 = stack[--sp];
        if (i1 - i0 < 2) continue;
        double x0 = pts[2 * i0], y0 = pts[2 * i0 + 1], x1 = pts[2 * i1], y1 = pts[2 * i1 + 1];
        double dx = x1 - x0, dy = y1 - y0;
        double ln = rf_py_hypot(dx, dy);
        double worst = -1.0; int32_t wi = 0;
        if (ln > 1e-9) {
            double c0 = x1 * y0, c1 = y1 * x0;
            for (int32_t i = i0 + 1; i < i1; i++) {
                double x = pts[2 * i], y = pts[2 * i + 1];
                double d = fabs(dy * x - dx * y + c0 - c1) / ln;
                if (d > worst) { worst = d; wi = i; }
            }
        } else {
            for (int32_t i = i0 + 1; i < i1; i++) {
                double d = rf_py_hypot(pts[2 * i] - x0, pts[2 * i + 1] - y0);
                if (d > worst) { worst = d; wi = i; }
            }
        }
        if (worst <= eps) continue;
        keep[wi] = 1;
        stack[sp++] = i0; stack[sp++] = wi;
        stack[sp++] = wi; stack[sp++] = i1;
    }
    int32_t m = 0;
    for (int32_t i = 0; i < n; i++) if (keep[i]) { out[2 * m] = pts[2 * i]; out[2 * m + 1] = pts[2 * i + 1]; m++; }
    return m;
}

/* the same with its own keep and stack -> the points kept, -1 when memory ran out */
int32_t rf_dp_simplify(const double *pts, int32_t n, double eps, double *out) {
    if (n < 3) { memcpy(out, pts, sizeof(double) * 2 * (size_t)n); return n; }
    uint8_t *keep = (uint8_t *)malloc((size_t)n);
    int32_t *stack = (int32_t *)malloc(sizeof(int32_t) * 2 * ((size_t)n + 2));
    if (!keep || !stack) { free(keep); free(stack); return -1; }
    int32_t m = dp_simplify_into(pts, n, eps, out, keep, stack);
    free(keep); free(stack);
    return m;
}

/* the cases of rmb_npops._CASES: per code, up to two (edge, edge) segments; edges 0 top, 1 right, 2 bottom, 3 left */
static const int CASE_N[16] = {0, 1, 1, 1, 1, 2, 1, 1, 1, 1, 2, 1, 1, 1, 1, 0};
static const int CASE_E[16][2][2] = {
    {{0, 0}, {0, 0}}, {{3, 0}, {0, 0}}, {{0, 1}, {0, 0}}, {{3, 1}, {0, 0}},
    {{1, 2}, {0, 0}}, {{3, 0}, {1, 2}}, {{0, 2}, {0, 0}}, {{3, 2}, {0, 0}},
    {{2, 3}, {0, 0}}, {{2, 0}, {0, 0}}, {{0, 1}, {2, 3}}, {{2, 1}, {0, 0}},
    {{1, 3}, {0, 0}}, {{1, 0}, {0, 0}}, {{0, 3}, {0, 0}}, {{0, 0}, {0, 0}}};
static const double EXT[4] = {0.5, 1.0, 0.5, 0.0}, EYT[4] = {0.0, 0.5, 1.0, 0.5};
static const int KXT[4] = {1, 2, 1, 0}, KYT[4] = {0, 1, 2, 1};

static uint64_t kh2(int64_t k) { uint64_t x = (uint64_t)k * 0x9E3779B97F4A7C15ULL; x ^= x >> 31; return x; }

void rf_outline_buf_free(rf_outline_buf *S) {
    free(S->ax); free(S->kk); free(S->ht); free(S->nxt); free(S->seg_of); free(S->used);
    free(S->fwd); free(S->back); free(S->chain); free(S->simp); free(S->keep); free(S->stack);
    memset(S, 0, sizeof(*S));
}

/* room for ns segments in every per-segment array and hcap entries in the table -> 0, -1 out of memory */
static int buf_reserve(rf_outline_buf *S, int32_t ns, size_t hcap) {
    if (hcap > S->hcap) {
        rf_outline_kent *h2 = (rf_outline_kent *)realloc(S->ht, sizeof(rf_outline_kent) * hcap);
        if (!h2) return -1;
        S->ht = h2; S->hcap = hcap;
    }
    if (ns <= S->ncap) return 0;
    int32_t c = S->ncap > 0 ? S->ncap : 256;
    while (c < ns) c = c > INT32_MAX / 2 ? ns : 2 * c;
    size_t n = (size_t)c;
    int32_t *nxt = (int32_t *)realloc(S->nxt, sizeof(int32_t) * 2 * n);
    if (nxt) S->nxt = nxt;
    int32_t *seg = (int32_t *)realloc(S->seg_of, sizeof(int32_t) * 2 * n);
    if (seg) S->seg_of = seg;
    uint8_t *used = (uint8_t *)realloc(S->used, n);
    if (used) S->used = used;
    double *fwd = (double *)realloc(S->fwd, sizeof(double) * 2 * (n + 2));
    if (fwd) S->fwd = fwd;
    double *back = (double *)realloc(S->back, sizeof(double) * 2 * (n + 2));
    if (back) S->back = back;
    double *chain = (double *)realloc(S->chain, sizeof(double) * 2 * (n + 4));
    if (chain) S->chain = chain;
    double *simp = (double *)realloc(S->simp, sizeof(double) * 2 * (n + 4));
    if (simp) S->simp = simp;
    uint8_t *keep = (uint8_t *)realloc(S->keep, n + 4);
    if (keep) S->keep = keep;
    int32_t *stack = (int32_t *)realloc(S->stack, sizeof(int32_t) * 2 * (n + 6));
    if (stack) S->stack = stack;
    if (!nxt || !seg || !used || !fwd || !back || !chain || !simp || !keep || !stack) return -1;
    S->ncap = c;
    return 0;
}

/* the outline of the h x w crop of a (H x W) through the scratch S: total = the length of every chain; with want, the
 * chains at least min_len long (and three points) into *counts_out / *xy_out (malloc'd) and their count returned;
 * without, nothing is built and 0 returned. -1 when memory ran out (nothing handed out). */
static int32_t outline_run(const uint8_t *a, int32_t H, int32_t W, int32_t w, int32_t h, double min_len, rf_outline_buf *S, int want,
                           double *total_out, int32_t **counts_out, double **xy_out) {
    *total_out = 0.0;
    if (want) { *counts_out = NULL; *xy_out = NULL; }
    if (w > W) w = W;
    if (h > H) h = H;
    if (w < 2 || h < 2) return 0;
    /* segments in raster order of their cells */
    int32_t ns = 0, rc = -1;
    int32_t *counts = NULL;
    double *xy = NULL;
    if (!S->ax) {
        S->ax = (double *)malloc(sizeof(double) * 4 * 1024);       /* ax, ay, bx, by per segment */
        S->kk = (int64_t *)malloc(sizeof(int64_t) * 2 * 1024);     /* ka, kb */
        if (!S->ax || !S->kk) { free(S->ax); free(S->kk); S->ax = NULL; S->kk = NULL; return -1; }
        S->cap = 1024;
    }
    int64_t kmul = 2 * (int64_t)w + 4;
    for (int32_t cy = 0; cy < h - 1; cy++) {
        const uint8_t *r0 = a + (size_t)cy * W, *r1 = r0 + W;
        for (int32_t cx = 0; cx < w - 1; cx++) {
            int code = (r0[cx] < 128) | ((r0[cx + 1] < 128) << 1) | ((r1[cx + 1] < 128) << 2) | ((r1[cx] < 128) << 3);
            if (code == 0 || code == 15) continue;
            for (int s = 0; s < CASE_N[code]; s++) {
                int e0 = CASE_E[code][s][0], e1 = CASE_E[code][s][1];
                if (ns == S->cap) {
                    double *ax2 = (double *)realloc(S->ax, sizeof(double) * 4 * (size_t)S->cap * 2);
                    if (!ax2) return -1;
                    S->ax = ax2;
                    int64_t *kk2 = (int64_t *)realloc(S->kk, sizeof(int64_t) * 2 * (size_t)S->cap * 2);
                    if (!kk2) return -1;
                    S->kk = kk2;
                    S->cap *= 2;
                }
                double *ax = S->ax + 4 * (size_t)ns;
                int64_t *kk = S->kk + 2 * (size_t)ns;
                ax[0] = cx + EXT[e0]; ax[1] = cy + EYT[e0];
                ax[2] = cx + EXT[e1]; ax[3] = cy + EYT[e1];
                kk[0] = (2 * (int64_t)cy + KYT[e0]) * kmul + 2 * (int64_t)cx + KXT[e0];
                kk[1] = (2 * (int64_t)cy + KYT[e1]) * kmul + 2 * (int64_t)cx + KXT[e1];
                ns++;
            }
        }
    }
    if (!ns) return 0;
    /* ends: key -> segment indices in insertion order (i ascending, ka before kb) */
    size_t hcap = 64;
    while (hcap < (size_t)ns * 4) hcap <<= 1;
    if (buf_reserve(S, ns, hcap) != 0) return -1;
    const double *ax = S->ax;
    const int64_t *kk = S->kk;
    rf_outline_kent *ht = S->ht;
    int32_t *nxt = S->nxt, *seg_of = S->seg_of;
    uint8_t *used = S->used;
    double *fwd = S->fwd, *back = S->back, *chain = S->chain, *simp = S->simp;
    int32_t nout = 0, ccap = 64; int64_t pcap = 1024, npts = 0;
    if (want) {
        counts = (int32_t *)malloc(sizeof(int32_t) * ccap);
        xy = (double *)malloc(sizeof(double) * 2 * pcap);
        if (!counts || !xy) goto done;
    }
    memset(used, 0, (size_t)ns);
    for (size_t t = 0; t < hcap; t++) ht[t].head = -1;
    for (int32_t e = 0; e < 2 * ns; e++) {
        int64_t key = kk[e];
        size_t g = kh2(key) & (hcap - 1);
        while (ht[g].head >= 0 && ht[g].key != key) g = (g + 1) & (hcap - 1);
        seg_of[e] = e / 2; nxt[e] = -1;
        if (ht[g].head < 0) { ht[g].key = key; ht[g].head = ht[g].tail = e; }
        else { nxt[ht[g].tail] = e; ht[g].tail = e; }
    }
    double total = 0.0;
    for (int32_t i = 0; i < ns; i++) {
        if (used[i]) continue;
        used[i] = 1;
        int32_t nf = 0, nb = 0;
        fwd[0] = ax[4 * i]; fwd[1] = ax[4 * i + 1]; fwd[2] = ax[4 * i + 2]; fwd[3] = ax[4 * i + 3]; nf = 2;
        for (int dir = 0; dir < 2; dir++) {
            int64_t tip = dir == 0 ? kk[2 * i + 1] : kk[2 * i];
            for (;;) {
                size_t g = kh2(tip) & (hcap - 1);
                while (ht[g].head >= 0 && ht[g].key != tip) g = (g + 1) & (hcap - 1);
                int32_t j = -1;
                if (ht[g].head >= 0)
                    for (int32_t e = ht[g].head; e >= 0; e = nxt[e]) if (!used[seg_of[e]]) { j = seg_of[e]; break; }
                if (j < 0) break;
                used[j] = 1;
                double px, py;
                if (kk[2 * j] == tip) { px = ax[4 * j + 2]; py = ax[4 * j + 3]; tip = kk[2 * j + 1]; }
                else { px = ax[4 * j]; py = ax[4 * j + 1]; tip = kk[2 * j]; }
                if (dir == 0) { fwd[2 * nf] = px; fwd[2 * nf + 1] = py; nf++; }
                else { back[2 * nb] = px; back[2 * nb + 1] = py; nb++; }
            }
        }
        int32_t nc = 0;
        for (int32_t t = nb - 1; t >= 0; t--) { chain[2 * nc] = back[2 * t]; chain[2 * nc + 1] = back[2 * t + 1]; nc++; }
        for (int32_t t = 0; t < nf; t++) { chain[2 * nc] = fwd[2 * t]; chain[2 * nc + 1] = fwd[2 * t + 1]; nc++; }
        if (nc < 6) continue;
        int32_t m = dp_simplify_into(chain, nc, 0.7, simp, S->keep, S->stack);
        double L = rf_py_sum_hypot(simp, m);
        total += L;
        if (want && m >= 3 && L >= min_len) {
            if (nout == ccap) {
                int32_t *c2 = (int32_t *)realloc(counts, sizeof(int32_t) * (size_t)ccap * 2);
                if (!c2) goto done;
                counts = c2; ccap *= 2;
            }
            if (npts + m > pcap) {
                int64_t pc = pcap;
                while (npts + m > pc) pc *= 2;
                double *x2 = (double *)realloc(xy, sizeof(double) * 2 * (size_t)pc);
                if (!x2) goto done;
                xy = x2; pcap = pc;
            }
            memcpy(xy + 2 * npts, simp, sizeof(double) * 2 * m);
            counts[nout++] = m; npts += m;
        }
    }
    *total_out = total;
    if (want) { *counts_out = counts; *xy_out = xy; counts = NULL; xy = NULL; }
    rc = nout;
done:
    free(counts); free(xy);
    return rc;
}

RF_API int32_t rf_outline(const uint8_t *a, int32_t H, int32_t W, int32_t w, int32_t h, double min_len, double *total_out,
                          int32_t **counts_out, double **xy_out) {
    rf_outline_buf S;
    memset(&S, 0, sizeof(S));
    int32_t rc = outline_run(a, H, W, w, h, min_len, &S, 1, total_out, counts_out, xy_out);
    rf_outline_buf_free(&S);
    if (rc < 0) *total_out = 0.0;
    return rc;
}

int32_t rf_outline_length(const uint8_t *a, int32_t H, int32_t W, int32_t w, int32_t h, rf_outline_buf *S, double *total) {
    int32_t rc = outline_run(a, H, W, w, h, 0.0, S, 0, total, NULL, NULL);
    if (rc < 0) { *total = 0.0; return -1; }
    return 0;
}
/* rm_paint._fill_holes: every 4-connected component of the pixels that are not 255 (ImageChops.invert's non-zero
 * pixels) whose box, with its 1-pixel margin, stays inside the mask is filled with 255 -- unless it is bigger than
 * `small` and its outline (the crop's _outline total) says it is thicker than `thin` (2 * area / perimeter). Returns
 * how many were filled; `out` (H x W) gets the result (a copy of the mask when none). */
RF_API int32_t rf_fill_holes(const uint8_t *mask, int32_t H, int32_t W, double small, double thin, uint8_t *out) {
    size_t N = (size_t)H * W;
    memcpy(out, mask, N);
    uint8_t *inv = (uint8_t *)malloc(N ? N : 1);
    int32_t *lab = (int32_t *)malloc(sizeof(int32_t) * (N ? N : 1));
    rf_comps C;
    memset(&C, 0, sizeof(C));
    if (!inv || !lab) { free(inv); free(lab); return -1; }
    for (size_t i = 0; i < N; i++) inv[i] = mask[i] != 255;
    int32_t n = rf_label4(inv, H, W, lab, &C, 1);
    if (n < 0) { free(inv); free(lab); return -1; }
    int32_t filled = 0;
    uint8_t *crop = NULL; size_t crop_cap = 0;
    rf_outline_buf OB;                       /* the outline's scratch, reused by every hole */
    memset(&OB, 0, sizeof(OB));
    for (int32_t k = 1; k <= n; k++) {
        int32_t x0 = C.x0[k], y0 = C.y0[k], w = C.x1[k] - x0 + 1, h = C.y1[k] - y0 + 1;
        int32_t ox = x0 - 1, oy = y0 - 1, cw = w + 2, chh = h + 2;
        if (ox <= 0 || oy <= 0 || ox + cw >= W || oy + chh >= H) continue;      /* reaches the border: not enclosed */
        int64_t area = C.area[k];
        if ((double)area > small) {
            size_t need = (size_t)cw * chh;
            if (need > crop_cap) {
                uint8_t *c2 = (uint8_t *)realloc(crop, need);
                if (!c2) { filled = -1; break; }
                crop = c2; crop_cap = need;
            }
            memset(crop, 0, need);
            for (int64_t t = C.start[k]; t < C.start[k + 1]; t++) {
                int32_t p = C.pix[t], py = p / W, px = p % W;
                crop[(size_t)(py - oy) * cw + (px - ox)] = 255;
            }
            double perim;
            if (rf_outline_length(crop, chh, cw, cw, chh, &OB, &perim) < 0) { filled = -1; break; }
            if (perim == 0.0 || 2.0 * (double)area / perim > thin) continue;
        }
        for (int64_t t = C.start[k]; t < C.start[k + 1]; t++) out[C.pix[t]] = 255;
        filled++;
    }
    free(crop); free(inv); free(lab); rf_comps_free(&C);
    rf_outline_buf_free(&OB);
    return filled;
}
