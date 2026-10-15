/* flow.c -- the coherence of rm_flow.field, the only part of the flow field the painter's output reads (DECISION code:
 * it is a reported share; the tangents are never read while V69_FLOW_HATCH is off and _flow_rows has no caller).
 *
 * Reproduces, in float64 as numpy and scipy compute it:
 *   a = gaussian_filter(gray / 255.0, pre, mode="nearest")      scipy.ndimage: correlate1d along axis 0, then axis 1,
 *                                                                 each line extended by its edge values, the symmetric
 *                                                                 kernel summed as NI_Correlate1D does it (scipy 1.18.1
 *                                                                 ni_filters.c): in[0] * w[0], then for j = -r .. -1
 *                                                                 += (in[j] + in[-j]) * w[j];
 *   gx[:, 1:-1] = (a[:, 2:] - a[:, :-2]) * 0.5, gy likewise, zero on the border;
 *   Jxx, Jxy, Jyy = the same filter (sigma) of gx*gx, gx*gy, gy*gy;
 *   d = sqrt(max((Jxx - Jyy)^2 + 4 Jxy Jxy, 0)); tr = Jxx + Jyy; l1, l2 = 0.5 (tr +- d);
 *   coh = ((l1 - l2) / (tr + 1e-12))^2 where tr > 1e-12, else 0;
 * and counts coh >= min_coherence. The kernels' weights (scipy's _gaussian_kernel1d: numpy's exp and sum) are the
 * caller's, so the C sums exactly the weights scipy uses. Lines are independent: row bands and column bands run on
 * all threads. tr + 1e-12 > 0 always (tr is a sum of weighted squares), so no division here can meet a zero.
 * Identity: checked against the reference (every call of real runs against rm_flow.field's coherence). */
#include <math.h>
#include <stdatomic.h>
#include <stdlib.h>
#include <string.h>
#include "rmfast.h"
#include "internal.h"

typedef struct {
    const double *in; double *out; int32_t H, W;
    const double *w; int32_t r;                 /* the kernel's center weight at w[r]; w[r + j] = w[r - j] */
    int axis; atomic_int next;
} corrjob;
#define CORR_BAND 16

static inline int32_t clampi32(int64_t v, int32_t hi) { return v < 0 ? 0 : (v > hi ? hi : (int32_t)v); }

static void corr_worker(void *arg, int tid) {
    (void)tid;
    corrjob *J = (corrjob *)arg;
    const int32_t H = J->H, W = J->W, r = J->r;
    const double *fw = J->w + r;
    for (;;) {
        int32_t y0 = atomic_fetch_add(&J->next, CORR_BAND);
        if (y0 >= H) break;
        int32_t y1 = y0 + CORR_BAND < H ? y0 + CORR_BAND : H;
        for (int32_t y = y0; y < y1; y++) {
            double *o = J->out + (size_t)y * W;
            if (J->axis == 0) {
                /* along the columns: the rows y - r .. y + r, edge rows repeated */
                const double *c = J->in + (size_t)y * W;
                for (int32_t x = 0; x < W; x++) o[x] = c[x] * fw[0];
                for (int32_t j = -r; j < 0; j++) {
                    const double *lo = J->in + (size_t)clampi32((int64_t)y + j, H - 1) * W;
                    const double *hi = J->in + (size_t)clampi32((int64_t)y - j, H - 1) * W;
                    const double wj = fw[j];
                    for (int32_t x = 0; x < W; x++) o[x] += (lo[x] + hi[x]) * wj;
                }
            } else {
                const double *c = J->in + (size_t)y * W;
                for (int32_t x = 0; x < W; x++) {
                    double v = c[x] * fw[0];
                    for (int32_t j = -r; j < 0; j++) v += (c[clampi32((int64_t)x + j, W - 1)] + c[clampi32((int64_t)x - j, W - 1)]) * fw[j];
                    o[x] = v;
                }
            }
        }
    }
}

static void correlate(const double *in, double *out, int32_t H, int32_t W, const double *w, int32_t r, int axis) {
    corrjob J;
    J.in = in; J.out = out; J.H = H; J.W = W; J.w = w; J.r = r; J.axis = axis;
    atomic_init(&J.next, 0);
    int nt = rf_threads(), bands = (H + CORR_BAND - 1) / CORR_BAND;
    rf_parallel(nt < bands ? nt : (bands > 0 ? bands : 1), corr_worker, &J);
}

/* gaussian_filter(src) into dst with tmp as the axis-0 result; w NULL: a copy (sigma <= 0) */
static void gauss2(const double *src, double *dst, double *tmp, int32_t H, int32_t W, const double *w, int32_t r) {
    if (!w) { memcpy(dst, src, sizeof(double) * (size_t)H * W); return; }
    correlate(src, tmp, H, W, w, r, 0);
    correlate(tmp, dst, H, W, w, r, 1);
}

/* -> 0 and *count = the pixels with coherence >= min_coh; -1 when memory ran out */
RF_API int32_t rf_flow_coherence(const uint8_t *gray, int32_t H, int32_t W, const double *wpre, int32_t rpre, const double *wsig,
                                 int32_t rsig, double min_coh, int64_t *count) {
    size_t N = (size_t)H * W;
    *count = 0;
    double *a = (double *)malloc(sizeof(double) * (N ? N : 1)), *t = (double *)malloc(sizeof(double) * (N ? N : 1));
    double *gx = (double *)calloc(N ? N : 1, sizeof(double)), *gy = (double *)calloc(N ? N : 1, sizeof(double));
    double *jxx = (double *)malloc(sizeof(double) * (N ? N : 1)), *jxy = (double *)malloc(sizeof(double) * (N ? N : 1));
    double *jyy = (double *)malloc(sizeof(double) * (N ? N : 1));
    int32_t rc = -1;
    if (!a || !t || !gx || !gy || !jxx || !jxy || !jyy) goto done;
    for (size_t i = 0; i < N; i++) jxx[i] = (double)gray[i] / 255.0;
    gauss2(jxx, a, t, H, W, wpre, rpre);
    for (int32_t y = 0; y < H; y++)
        for (int32_t x = 1; x < W - 1; x++) gx[(size_t)y * W + x] = (a[(size_t)y * W + x + 1] - a[(size_t)y * W + x - 1]) * 0.5;
    for (int32_t y = 1; y < H - 1; y++)
        for (int32_t x = 0; x < W; x++) gy[(size_t)y * W + x] = (a[(size_t)(y + 1) * W + x] - a[(size_t)(y - 1) * W + x]) * 0.5;
    /* the three products, each filtered (a holds the product before its filter) */
    for (size_t i = 0; i < N; i++) a[i] = gx[i] * gx[i];
    gauss2(a, jxx, t, H, W, wsig, rsig);
    for (size_t i = 0; i < N; i++) a[i] = gx[i] * gy[i];
    gauss2(a, jxy, t, H, W, wsig, rsig);
    for (size_t i = 0; i < N; i++) a[i] = gy[i] * gy[i];
    gauss2(a, jyy, t, H, W, wsig, rsig);
    int64_t n = 0;
    for (size_t i = 0; i < N; i++) {
        double dd = jxx[i] - jyy[i];
        double q = dd * dd + 4.0 * jxy[i] * jxy[i];
        double d = sqrt(q > 0.0 ? q : 0.0);
        double tr = jxx[i] + jyy[i];
        double l1 = 0.5 * (tr + d), l2 = 0.5 * (tr - d);
        double coh = 0.0;
        if (tr > 1e-12) { double e = (l1 - l2) / (tr + 1e-12); coh = e * e; }
        n += coh >= min_coh;
    }
    *count = n;
    rc = 0;
done:
    free(a); free(t); free(gx); free(gy); free(jxx); free(jxy); free(jyy);
    return rc;
}
