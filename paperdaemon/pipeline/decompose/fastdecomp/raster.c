/* The device's wash rasterizer -- rm_raster.py's numba kernel, operation for operation.
 * A pixel is painted when its center lies inside the stroke's footprint (one rectangle per segment, flat ends, a
 * bevel triangle on the outer side of each interior corner), the footprint widened by eps > 0 or shrunk by eps < 0;
 * at eps == 0 a center exactly on an edge is painted on the top-left side only. Doubles; sqrt; the same clamps. */
#include <math.h>
#include <stdlib.h>
#include <string.h>
#include "rmfast.h"
#include "internal.h"

static inline int inside(double d, double nx, double ny, double eps) {
    if (eps > 0.0) return d <= eps;
    if (eps < 0.0) return d < eps;
    if (d < -1e-9) return 1;
    if (d > 1e-9) return 0;
    return ny < -1e-12 || (fabs(ny) <= 1e-12 && nx < 0.0);
}

static inline int imin(int a, int b) { return a < b ? a : b; }
static inline double dmin(double a, double b) { return a < b ? a : b; }
static inline double dmax(double a, double b) { return a > b ? a : b; }
/* a pixel bound from a coordinate: (int)v, clamped into [lo, hi] before the conversion, so no coordinate can make
 * an out-of-range index or an overflowing conversion; for v in range it is (int)v exactly */
static inline int clampi(double v, int lo, int hi) { return v < (double)lo ? lo : (v > (double)hi ? hi : (int)v); }

/* The columns of row `r` that can hold a pixel of the segment's rectangle: the row's center line cut by the
 * rectangle grown by a full pixel (far more than any eps), widened by one more column each side. Every pixel outside
 * fails the exact test anyway, so testing only these gives the same pixels. */
static inline int row_span(double ry, double x0, double ux, double uy, double L, double h, double ox, int c0, int c1, int *a, int *b) {
    const double m = 1.0;
    double lo = -1e300, hi = 1e300;
    /* t = rx * ux + ry * uy in [-m, L + m] */
    if (fabs(ux) > 1e-12) {
        double p = (-m - ry * uy) / ux, q = (L + m - ry * uy) / ux;
        if (p > q) { double t = p; p = q; q = t; }
        if (p > lo) lo = p;
        if (q < hi) hi = q;
    } else if (ry * uy < -m - 1e-9 || ry * uy > L + m + 1e-9) return 0;
    /* s = -rx * uy + ry * ux in [-h - m, h + m] */
    if (fabs(uy) > 1e-12) {
        double p = (-h - m - ry * ux) / -uy, q = (h + m - ry * ux) / -uy;
        if (p > q) { double t = p; p = q; q = t; }
        if (p > lo) lo = p;
        if (q < hi) hi = q;
    } else if (ry * ux < -h - m - 1e-9 || ry * ux > h + m + 1e-9) return 0;
    if (lo > hi) return 0;
    double ca = floor(x0 + lo - ox - 0.5) - 1.0, cb = ceil(x0 + hi - ox - 0.5) + 1.0;
    *a = clampi(ca, c0, c1 + 1);
    *b = clampi(cb, c0 - 1, c1);
    return *a <= *b;
}

/* rm_raster.paint for ne eps values at once: img is H x W, pixel (r, c) centered at (ox + c + .5, oy + r + .5); bit e
 * of a pixel is set when it is painted under eps[e]. The pixels visited do not depend on eps (the row spans and the
 * bevel boxes are eps-free), so each bit is exactly what one call with that eps paints. With smin/smax (one per row),
 * each row's visited column range is folded into them, so the caller can read back and clear only those spans. */
static void paint_multi(uint8_t *img, int32_t W, int32_t H, double ox, double oy, const double *xs, const double *ys, const double *hw, int32_t n,
                        const double *eps, int ne, int32_t *smin, int32_t *smax) {
    for (int32_t i = 0; i < n - 1; i++) {
        double x0 = xs[i], y0 = ys[i], x1 = xs[i + 1], y1 = ys[i + 1];
        double dx = x1 - x0, dy = y1 - y0;
        double L = sqrt(dx * dx + dy * dy);
        if (L < 1e-9) continue;
        double ux = dx / L, uy = dy / L;
        double h = hw[i];
        int c0 = clampi(floor(dmin(x0, x1) - h - ox - 1.0), 0, W), c1 = clampi(ceil(dmax(x0, x1) + h - ox + 1.0), -1, W - 1);
        int r0 = clampi(floor(dmin(y0, y1) - h - oy - 1.0), 0, H), r1 = clampi(ceil(dmax(y0, y1) + h - oy + 1.0), -1, H - 1);
        for (int r = r0; r <= r1; r++) {
            double ry = oy + r + 0.5 - y0;
            int ca, cb;
            if (!row_span(ry, x0, ux, uy, L, h, ox, c0, c1, &ca, &cb)) continue;
            if (smin) { if (ca < smin[r]) smin[r] = ca; if (cb > smax[r]) smax[r] = cb; }
            for (int c = ca; c <= cb; c++) {
                double rx = ox + c + 0.5 - x0;
                double t = rx * ux + ry * uy;
                double s = -rx * uy + ry * ux;
                for (int e = 0; e < ne; e++)
                    if (inside(-t, -ux, -uy, eps[e]) && inside(t - L, ux, uy, eps[e])
                            && inside(-s - h, uy, -ux, eps[e]) && inside(s - h, -uy, ux, eps[e]))
                        img[(size_t)r * W + c] |= (uint8_t)(1u << e);
            }
        }
    }
    for (int32_t i = 1; i < n - 1; i++) {
        double ax = xs[i] - xs[i - 1], ay = ys[i] - ys[i - 1];
        double bx = xs[i + 1] - xs[i], by = ys[i + 1] - ys[i];
        double la = sqrt(ax * ax + ay * ay), lb = sqrt(bx * bx + by * by);
        if (la < 1e-9 || lb < 1e-9) continue;
        double d1x = ax / la, d1y = ay / la, d2x = bx / lb, d2y = by / lb;
        double cross = d1x * d2y - d1y * d2x;
        if (fabs(cross) < 1e-6) continue;
        double sgn = cross > 0 ? -1.0 : 1.0;
        double vx = xs[i], vy = ys[i];
        double p1x = vx + sgn * (-d1y) * hw[i - 1], p1y = vy + sgn * d1x * hw[i - 1];
        double p2x = vx + sgn * (-d2y) * hw[i], p2y = vy + sgn * d2x * hw[i];
        double area = (p1x - vx) * (p2y - vy) - (p1y - vy) * (p2x - vx);
        if (fabs(area) < 1e-12) continue;
        double o = area > 0 ? 1.0 : -1.0;
        double e1 = sqrt((p1x - vx) * (p1x - vx) + (p1y - vy) * (p1y - vy));
        double e2 = sqrt((p2x - p1x) * (p2x - p1x) + (p2y - p1y) * (p2y - p1y));
        double e3 = sqrt((vx - p2x) * (vx - p2x) + (vy - p2y) * (vy - p2y));
        if (e1 < 1e-9 || e2 < 1e-9 || e3 < 1e-9) continue;
        int c0 = clampi(floor(dmin(vx, dmin(p1x, p2x)) - ox - 1.0), 0, W), c1 = clampi(ceil(dmax(vx, dmax(p1x, p2x)) - ox + 1.0), -1, W - 1);
        int r0 = clampi(floor(dmin(vy, dmin(p1y, p2y)) - oy - 1.0), 0, H), r1 = clampi(ceil(dmax(vy, dmax(p1y, p2y)) - oy + 1.0), -1, H - 1);
        for (int r = r0; r <= r1; r++) {
            double py = oy + r + 0.5;
            if (smin) { if (c0 < smin[r]) smin[r] = c0; if (c1 > smax[r]) smax[r] = c1; }
            for (int c = c0; c <= c1; c++) {
                double px = ox + c + 0.5;
                double dd1 = -o * ((p1x - vx) * (py - vy) - (p1y - vy) * (px - vx)) / e1;
                double dd2 = -o * ((p2x - p1x) * (py - p1y) - (p2y - p1y) * (px - p1x)) / e2;
                double dd3 = -o * ((vx - p2x) * (py - p2y) - (vy - p2y) * (px - p2x)) / e3;
                for (int e = 0; e < ne; e++)
                    if (inside(dd1, o * (p1y - vy) / e1, -o * (p1x - vx) / e1, eps[e])
                            && inside(dd2, o * (p2y - p1y) / e2, -o * (p2x - p1x) / e2, eps[e])
                            && inside(dd3, o * (vy - p2y) / e3, -o * (vx - p2x) / e3, eps[e]))
                        img[(size_t)r * W + c] |= (uint8_t)(1u << e);
            }
        }
    }
}

/* one eps: the painted pixels get 1 (they may already be 1: painting only sets) */
void rf_paint_spans(uint8_t *img, int32_t W, int32_t H, double ox, double oy, const double *xs, const double *ys, const double *hw, int32_t n, double eps,
                    int32_t *smin, int32_t *smax) {
    paint_multi(img, W, H, ox, oy, xs, ys, hw, n, &eps, 1, smin, smax);
}

void rf_paint(uint8_t *img, int32_t W, int32_t H, double ox, double oy, const double *xs, const double *ys, const double *hw, int32_t n, double eps) {
    paint_multi(img, W, H, ox, oy, xs, ys, hw, n, &eps, 1, NULL, NULL);
}

/* rm_raster.geometry: consecutive duplicates (both coordinates within 1e-6) dropped; half-widths per segment =
 * (w_i + w_{i+1}) * HL_SCALE / 4. Returns the point count after the drop (0 or 1 means nothing to paint). */
int32_t rf_geometry(const double *xy, const double *w, int32_t npts, double *xs, double *ys, double *hw) {
    int32_t m = 0;
    double *ws = hw;        /* scratch: the scaled widths, overwritten by the half-widths below (hw has npts slots) */
    for (int32_t k = 0; k < npts; k++) {
        double x = xy[2 * k], y = xy[2 * k + 1];
        if (m && fabs(x - xs[m - 1]) < 1e-6 && fabs(y - ys[m - 1]) < 1e-6) continue;
        xs[m] = x;
        ys[m] = y;
        ws[m] = w[k] * RF_HL_SCALE;
        m++;
    }
    if (m < 2) return m;
    for (int32_t i = 0; i < m - 1; i++) hw[i] = (ws[i] + ws[i + 1]) / 4.0;   /* in place: hw[i] reads ws[i], ws[i+1] before they move */
    return m;
}

/* rm_raster.wash_pixels: paint into the stroke's own bounding window, then list the painted pixels in row-major
 * order as flat indices of the W x H grid. The scratch buffers are the caller's (rf_scratch). The list goes to *out:
 * a new array of its exact size when cap is NULL, else the caller's buffer *out of *cap entries, grown when needed.
 * -> the count, or -1 when memory ran out. */
static int32_t wash_pixels_core(const double *xy, const double *w, int32_t npts, double ox, double oy, int32_t W, int32_t H, double eps,
                                rf_scratch *S, int32_t **out, size_t *cap) {
    if (!cap) *out = NULL;
    if (rf_scratch_reserve_pts(S, npts)) return -1;
    int32_t m = rf_geometry(xy, w, npts, S->xs, S->ys, S->hw);
    if (m < 2) return 0;
    double hmax = S->hw[0], xmin = S->xs[0], xmax = S->xs[0], ymin = S->ys[0], ymax = S->ys[0];
    for (int32_t i = 1; i < m - 1; i++) if (S->hw[i] > hmax) hmax = S->hw[i];
    for (int32_t i = 1; i < m; i++) {
        if (S->xs[i] < xmin) xmin = S->xs[i];
        if (S->xs[i] > xmax) xmax = S->xs[i];
        if (S->ys[i] < ymin) ymin = S->ys[i];
        if (S->ys[i] > ymax) ymax = S->ys[i];
    }
    double pad = hmax + 2.0;
    int c0 = clampi(floor(xmin - pad - ox), 0, W), c1 = imin(W, clampi(ceil(xmax + pad - ox), -1, W) + 1);
    int r0 = clampi(floor(ymin - pad - oy), 0, H), r1 = imin(H, clampi(ceil(ymax + pad - oy), -1, H) + 1);
    if (c1 <= c0 || r1 <= r0) return 0;
    int w_ = c1 - c0, h_ = r1 - r0;
    /* the window buffer is all zeros between calls: only the spans painted are read back and cleared */
    if (rf_scratch_reserve_img(S, (size_t)w_ * h_) || rf_scratch_reserve_rows(S, h_)) return -1;
    for (int r = 0; r < h_; r++) { S->smin[r] = w_; S->smax[r] = -1; }
    rf_paint_spans(S->img, w_, h_, ox + c0, oy + r0, S->xs, S->ys, S->hw, m, eps, S->smin, S->smax);
    int32_t cnt = 0;
    for (int r = 0; r < h_; r++) {
        const uint8_t *row = S->img + (size_t)r * w_;
        for (int c = S->smin[r]; c <= S->smax[r]; c++) cnt += row[c];
    }
    int32_t *o;
    if (!cap) o = (int32_t *)malloc(sizeof(int32_t) * (cnt ? cnt : 1));
    else if ((size_t)cnt > *cap) {
        o = (int32_t *)realloc(*out, sizeof(int32_t) * (size_t)cnt);
        if (o) { *out = o; *cap = (size_t)cnt; }
    } else o = *out;
    if (!o) {                                  /* leave the window buffer all zeros, as the next call expects */
        for (int r = 0; r < h_; r++) for (int c = S->smin[r]; c <= S->smax[r]; c++) S->img[(size_t)r * w_ + c] = 0;
        return -1;
    }
    int32_t j = 0;
    for (int r = 0; r < h_; r++) {
        uint8_t *row = S->img + (size_t)r * w_;
        for (int c = S->smin[r]; c <= S->smax[r]; c++)
            if (row[c]) { o[j++] = (int32_t)((r + r0) * (int64_t)W + (c + c0)); row[c] = 0; }
    }
    *out = o;
    return cnt;
}

int32_t rf_wash_pixels_into(const double *xy, const double *w, int32_t npts, double ox, double oy, int32_t W, int32_t H, double eps, rf_scratch *S, int32_t **out) {
    return wash_pixels_core(xy, w, npts, ox, oy, W, H, eps, S, out, NULL);
}

int32_t rf_wash_pixels_buf(const double *xy, const double *w, int32_t npts, double ox, double oy, int32_t W, int32_t H, double eps, rf_scratch *S,
                           int32_t **buf, size_t *cap) {
    return wash_pixels_core(xy, w, npts, ox, oy, W, H, eps, S, buf, cap);
}

/* the footprints of one stroke under ne (<= 8) eps values, from one painting: list e (rm_raster.wash_pixels with eps[e])
 * into the caller's buffer bufs[e] of caps[e] entries, grown when needed; counts[e] its length. -> 0, or -1 when
 * memory ran out. */
int32_t rf_wash_pixels_multi(const double *xy, const double *w, int32_t npts, double ox, double oy, int32_t W, int32_t H, const double *eps,
                             int ne, rf_scratch *S, int32_t **bufs, size_t *caps, int32_t *counts) {
    for (int e = 0; e < ne; e++) counts[e] = 0;
    if (ne < 1 || ne > 8) return -1;
    if (rf_scratch_reserve_pts(S, npts)) return -1;
    int32_t m = rf_geometry(xy, w, npts, S->xs, S->ys, S->hw);
    if (m < 2) return 0;
    double hmax = S->hw[0], xmin = S->xs[0], xmax = S->xs[0], ymin = S->ys[0], ymax = S->ys[0];
    for (int32_t i = 1; i < m - 1; i++) if (S->hw[i] > hmax) hmax = S->hw[i];
    for (int32_t i = 1; i < m; i++) {
        if (S->xs[i] < xmin) xmin = S->xs[i];
        if (S->xs[i] > xmax) xmax = S->xs[i];
        if (S->ys[i] < ymin) ymin = S->ys[i];
        if (S->ys[i] > ymax) ymax = S->ys[i];
    }
    double pad = hmax + 2.0;
    int c0 = clampi(floor(xmin - pad - ox), 0, W), c1 = imin(W, clampi(ceil(xmax + pad - ox), -1, W) + 1);
    int r0 = clampi(floor(ymin - pad - oy), 0, H), r1 = imin(H, clampi(ceil(ymax + pad - oy), -1, H) + 1);
    if (c1 <= c0 || r1 <= r0) return 0;
    int w_ = c1 - c0, h_ = r1 - r0;
    if (rf_scratch_reserve_img(S, (size_t)w_ * h_) || rf_scratch_reserve_rows(S, h_)) return -1;
    for (int r = 0; r < h_; r++) { S->smin[r] = w_; S->smax[r] = -1; }
    paint_multi(S->img, w_, h_, ox + c0, oy + r0, S->xs, S->ys, S->hw, m, eps, ne, S->smin, S->smax);
    int32_t cnt[8] = {0};
    for (int r = 0; r < h_; r++) {
        const uint8_t *row = S->img + (size_t)r * w_;
        for (int c = S->smin[r]; c <= S->smax[r]; c++) for (int e = 0; e < ne; e++) cnt[e] += (row[c] >> e) & 1;
    }
    int bad = 0;
    for (int e = 0; e < ne; e++)
        if ((size_t)cnt[e] > caps[e]) {
            int32_t *q = (int32_t *)realloc(bufs[e], sizeof(int32_t) * (size_t)cnt[e]);
            if (q) { bufs[e] = q; caps[e] = (size_t)cnt[e]; } else bad = 1;
        }
    int32_t k[8] = {0};
    for (int r = 0; r < h_; r++) {
        uint8_t *row = S->img + (size_t)r * w_;
        for (int c = S->smin[r]; c <= S->smax[r]; c++) {
            if (!row[c]) continue;
            if (!bad) {
                int32_t idx = (int32_t)((r + r0) * (int64_t)W + (c + c0));
                for (int e = 0; e < ne; e++) if ((row[c] >> e) & 1) bufs[e][k[e]++] = idx;
            }
            row[c] = 0;                            /* the window buffer is left all zeros, as the next call expects */
        }
    }
    if (bad) return -1;
    for (int e = 0; e < ne; e++) counts[e] = cnt[e];
    return 0;
}

RF_API int32_t rf_wash_pixels(const double *xy, const double *w, int32_t npts, double ox, double oy, int32_t W, int32_t H, double eps, int32_t **out) {
    rf_scratch S = {0};
    int32_t n = rf_wash_pixels_into(xy, w, npts, ox, oy, W, H, eps, &S, out);
    rf_scratch_free(&S);
    return n;
}

/* the scratch buffers, grown on demand: 0, or -1 when memory ran out (the buffers then keep their old size) */
int rf_scratch_reserve_pts(rf_scratch *S, int32_t npts) {
    if (S->cap_pts >= npts + 1) return 0;
    size_t cap = (size_t)npts + 1;
    double *p;
    if (!(p = (double *)realloc(S->xs, sizeof(double) * cap))) return -1;
    S->xs = p;
    if (!(p = (double *)realloc(S->ys, sizeof(double) * cap))) return -1;
    S->ys = p;
    if (!(p = (double *)realloc(S->hw, sizeof(double) * cap))) return -1;
    S->hw = p;
    S->cap_pts = (int32_t)cap;
    return 0;
}

int rf_scratch_reserve_img(rf_scratch *S, size_t n) {
    if (S->cap_img >= n) return 0;
    uint8_t *p = (uint8_t *)calloc(n, 1);      /* zeros: rf_wash_pixels_into keeps it that way */
    if (!p) return -1;
    free(S->img);
    S->img = p; S->cap_img = n;
    return 0;
}

int rf_scratch_reserve_rows(rf_scratch *S, int32_t n) {
    if (S->cap_rows >= n) return 0;
    int32_t *p;
    if (!(p = (int32_t *)realloc(S->smin, sizeof(int32_t) * (size_t)n))) return -1;
    S->smin = p;
    if (!(p = (int32_t *)realloc(S->smax, sizeof(int32_t) * (size_t)n))) return -1;
    S->smax = p;
    S->cap_rows = n;
    return 0;
}

void rf_scratch_free(rf_scratch *S) {
    free(S->xs); free(S->ys); free(S->hw); free(S->img); free(S->smin); free(S->smax);
    memset(S, 0, sizeof(*S));
}

RF_API const char *rf_version(void) { return "rmfast 0.2 (raster, pass, seam, planner, cel pass, absorber, shade zones, region budget, components, outline, holes)"; }
RF_API void rf_free(void *p) { free(p); }
