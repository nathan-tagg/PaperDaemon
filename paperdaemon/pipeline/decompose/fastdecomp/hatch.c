/* hatch.c -- rm_paint.uniform_hatch: straight parallel lines at one pitch, clipped to a mask, for each angle
 * (GEOMETRY code: these are stroke points).
 *
 * The Python's arithmetic exactly: diag = math.hypot(w, h) (CPython's correctly rounded hypot, outline.c), the
 * sample positions t and the line offsets d built by REPEATED ADDITION from -diag / 2 while <= diag / 2 (a float sum is
 * not its closed form), math.radians(a) = a * (pi / 180), cos and sin the C runtime's (the functions math.cos and
 * math.sin call), X = (cx + nx * d) + ux * t and Y = (cy + ny * d) + uy * t per sample, int64 truncation toward zero
 * for the pixel, a sample inside when its pixel is in the grid and set; a run of inside samples ends at a gap of four
 * or more in their indices; a run is kept when math.hypot of its end points' difference is at least min_len. Output in
 * the Python's order: angle, then line, then run, as (x0, y0, x1, y1) doubles.
 * Identity: a check of every call of real runs against rm_paint.uniform_hatch, and of random masks. */
#include <math.h>
#include <stdlib.h>
#include "rmfast.h"
#include "internal.h"

#define HATCH_MAX_STEPS (1 << 24)       /* samples or lines per angle: far past any grid; a call over it is refused */

/* -> the segment count with *out (4 doubles each, rf_free'd by the caller), -1 out of memory, -2 refused (a pitch
 * that is not positive, or more samples than HATCH_MAX_STEPS: the Python runs) */
RF_API int64_t rf_uniform_hatch(const uint8_t *mask, int32_t H, int32_t W, const double *angles, int32_t na, double pitch, double min_len,
                                double **out) {
    *out = NULL;
    if (!(pitch > 0.0) || H <= 0 || W <= 0) return -2;
    double diag = rf_py_hypot((double)W, (double)H);
    double cx = W / 2.0, cy = H / 2.0, half = diag / 2.0;
    /* the counts first, by the same additions */
    int64_t nt = 0, nd = 0;
    for (double t = -half; t <= half; t += 0.6) if (++nt > HATCH_MAX_STEPS) return -2;
    for (double d = -half; d <= half; d += pitch) if (++nd > HATCH_MAX_STEPS) return -2;
    if (!nt || !nd) return 0;
    double *T = (double *)malloc(sizeof(double) * (size_t)nt), *D = (double *)malloc(sizeof(double) * (size_t)nd);
    double *X = (double *)malloc(sizeof(double) * (size_t)nt), *Y = (double *)malloc(sizeof(double) * (size_t)nt);
    int64_t *idx = (int64_t *)malloc(sizeof(int64_t) * (size_t)nt);
    size_t cap = 1024, n = 0;
    double *o = (double *)malloc(sizeof(double) * 4 * cap);
    if (!T || !D || !X || !Y || !idx || !o) { free(T); free(D); free(X); free(Y); free(idx); free(o); return -1; }
    { double t = -half; for (int64_t k = 0; k < nt; k++) { T[k] = t; t += 0.6; } }
    { double d = -half; for (int64_t k = 0; k < nd; k++) { D[k] = d; d += pitch; } }
    rf_fn1 COS = rf_crt_cos(), SIN = rf_crt_sin();
    const double deg2rad = 3.141592653589793 / 180.0;          /* CPython's degToRad: Py_MATH_PI / 180.0 */
    for (int32_t ai = 0; ai < na; ai++) {
        double a = angles[ai] * deg2rad;
        double ux = COS(a), uy = SIN(a), nx = -uy, ny = ux;
        for (int64_t i = 0; i < nd; i++) {
            double bx = cx + nx * D[i], by = cy + ny * D[i];
            int64_t ni = 0;
            for (int64_t j = 0; j < nt; j++) {
                double x = bx + ux * T[j], y = by + uy * T[j];
                X[j] = x; Y[j] = y;
                /* int64 truncation; the coordinates lie within the grid's diagonal of it, far inside int64 */
                int64_t xi = (int64_t)x, yi = (int64_t)y;
                if (xi >= 0 && xi < W && yi >= 0 && yi < H && mask[(size_t)yi * (size_t)W + (size_t)xi]) idx[ni++] = j;
            }
            for (int64_t s = 0; s < ni;) {
                int64_t e = s;
                while (e + 1 < ni && idx[e + 1] - idx[e] < 4) e++;
                double x0 = X[idx[s]], y0 = Y[idx[s]], x1 = X[idx[e]], y1 = Y[idx[e]];
                if (rf_py_hypot(x1 - x0, y1 - y0) >= min_len) {
                    if (n == cap) {
                        double *q = (double *)realloc(o, sizeof(double) * 4 * cap * 2);
                        if (!q) { free(T); free(D); free(X); free(Y); free(idx); free(o); return -1; }
                        o = q; cap *= 2;
                    }
                    o[4 * n] = x0; o[4 * n + 1] = y0; o[4 * n + 2] = x1; o[4 * n + 3] = y1;
                    n++;
                }
                s = e + 1;
            }
        }
    }
    free(T); free(D); free(X); free(Y); free(idx);
    *out = o;
    return (int64_t)n;
}

/* rm_trace.place of points the Python holds as Python floats (the hatch's lines, the contour pass's centerlines): each
 * (ox + x * scale, oy + y * scale) in double, the frame from rf_place_frame; n points from xy into dst */
void rf_place_points(const double *xy, int64_t n, double ox, double oy, double scale, double *dst) {
    for (int64_t t = 0; t < n; t++) {
        dst[2 * t] = ox + xy[2 * t] * scale;
        dst[2 * t + 1] = oy + xy[2 * t + 1] * scale;
    }
}
