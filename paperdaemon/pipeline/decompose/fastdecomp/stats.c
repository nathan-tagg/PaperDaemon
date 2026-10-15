/* stats.c -- the per-picture gates the painter reads before it classifies anything (DECISION code):
 *
 *   rf_skin_cast   rm_paint.skin_cast_offset (SKIN_CAST_ON): the picture's Lab (lab.c), chroma by np.hypot (the
 *                  runtime's _hypot), the near-neutral pixels (C < 12, 25 < L < 92; when under half a percent of the
 *                  picture, C < 25 and L > 20), the cast = numpy's median of their a* and b*, its size by CPython's
 *                  math.hypot; past the deadband, the warm wedge (hue = np.degrees(np.arctan2(b, a)) % 360 in
 *                  15..95, C in 10..50, L in 30..88), its median chroma when it holds more than 50 pixels, and the
 *                  offset math.degrees(math.atan2(mag sin(theta - h_ref), c_ref + mag cos(theta - h_ref))) clamped
 *                  to +-SKIN_CAST_MAX_DEG -- CPython's atan2 rule for y == 0, the runtime's atan2, sin and cos.
 *   rf_dark_field  rm_paint.dark_field: the share of pixels with L < black_l, and when it reaches DARK_FIELD_MIN_COVER
 *                  the area of the largest 4-connected dark piece at least 2 wide or tall (rmb_npops.components'
 *                  first) over the picture's area.
 * Identity: checked against the reference (every call of real model runs through the Python and the C). */
#include <math.h>
#include <stdlib.h>
#include <string.h>
#include "rmfast.h"
#include "internal.h"

/* -> 0, or -1 when memory ran out. offset, da, db: the Python's return values (0.0, (0.0, 0.0) when no pixel is
 * near-neutral; 0.0, (da, db) under the deadband) */
RF_API int32_t rf_skin_cast(const uint8_t *rgb, int32_t H, int32_t W, double deadband, double ref_hue, double max_deg,
                            double *offset, double *da_out, double *db_out) {
    size_t N = (size_t)H * W;
    *offset = 0.0; *da_out = 0.0; *db_out = 0.0;
    double *lab = (double *)malloc(sizeof(double) * 3 * (N ? N : 1));
    double *C = (double *)malloc(sizeof(double) * (N ? N : 1));
    double *va = (double *)malloc(sizeof(double) * (N ? N : 1)), *vb = (double *)malloc(sizeof(double) * (N ? N : 1));
    int32_t rc = -1;
    if (!lab || !C || !va || !vb) goto done;
    rf_lab_rows(rgb, (int64_t)N, lab);
    rf_pow_fn hyp = rf_crt_hypot(), at2 = rf_crt_atan2();
    for (size_t i = 0; i < N; i++) C[i] = hyp(lab[3 * i + 1], lab[3 * i + 2]);
    int64_t nn = 0;
    for (size_t i = 0; i < N; i++) nn += (C[i] < 12.0) & (lab[3 * i] > 25.0) & (lab[3 * i] < 92.0);
    int wide = (double)nn / (double)N < 0.005;            /* neutral.mean() < 0.005 */
    int64_t k = 0;
    for (size_t i = 0; i < N; i++) {
        double L = lab[3 * i];
        int sel = wide ? (C[i] < 25.0 && L > 20.0) : (C[i] < 12.0 && L > 25.0 && L < 92.0);
        if (sel) { va[k] = lab[3 * i + 1]; vb[k] = lab[3 * i + 2]; k++; }
    }
    if (!k) { rc = 0; goto done; }
    double da = rf_np_median(va, k), db = rf_np_median(vb, k);
    *da_out = da; *db_out = db;
    double mag = rf_py_hypot(da, db);
    if (mag < deadband) { rc = 0; goto done; }
    /* the warm wedge's chroma values, in raster order (va is free again) */
    const double rad_to_deg = 180.0 / 3.14159265358979323846, deg_to_rad = 3.14159265358979323846 / 180.0;
    int64_t nw = 0;
    for (size_t i = 0; i < N; i++) {
        double L = lab[3 * i], c = C[i];
        double h = rf_py_mod(at2(lab[3 * i + 2], lab[3 * i + 1]) * rad_to_deg, 360.0);
        if (h >= 15.0 && h <= 95.0 && c >= 10.0 && c <= 50.0 && L >= 30.0 && L <= 88.0) va[nw++] = c;
    }
    double c_ref = nw > 50 ? rf_np_median(va, nw) : 25.0;
    rf_fn1 sn = rf_crt_sin(), cs = rf_crt_cos();
    double theta = rf_py_atan2(at2, db, da), h_ref = ref_hue * deg_to_rad;
    double delta = rf_py_atan2(at2, mag * sn(theta - h_ref), c_ref + mag * cs(theta - h_ref)) * rad_to_deg;
    double lo = -max_deg;
    double m = delta < max_deg ? delta : max_deg;             /* min(max_deg, delta) */
    *offset = m > lo ? m : lo;                                 /* max(-max_deg, that) */
    rc = 0;
done:
    free(lab); free(C); free(va); free(vb);
    return rc;
}

/* -> 0, or -1 when memory ran out */
RF_API int32_t rf_dark_field(const uint8_t *rgb, int32_t H, int32_t W, double black_l, double min_cover, double min_region,
                             int32_t *on, double *share_out, double *big_out) {
    size_t N = (size_t)H * W;
    *on = 0; *share_out = 0.0; *big_out = 0.0;
    double *L = (double *)malloc(sizeof(double) * (N ? N : 1));
    uint8_t *m = (uint8_t *)malloc(N ? N : 1);
    int32_t *lab = NULL;
    rf_comps Cc;
    memset(&Cc, 0, sizeof(Cc));
    int32_t rc = -1;
    if (!L || !m) goto done;
    rf_l_rows(rgb, (int64_t)N, L);
    int64_t cnt = 0;
    for (size_t i = 0; i < N; i++) { m[i] = L[i] < black_l; cnt += m[i]; }
    double share = (double)cnt / (double)N;
    *share_out = share;
    if (share < min_cover) { rc = 0; goto done; }
    lab = (int32_t *)malloc(sizeof(int32_t) * (N ? N : 1));
    if (!lab) goto done;
    int32_t n = rf_label4(m, H, W, lab, &Cc, 0);
    if (n < 0) goto done;
    int64_t best = 0;
    for (int32_t c = 1; c <= n; c++) {
        int32_t bw = Cc.x1[c] - Cc.x0[c] + 1, bh = Cc.y1[c] - Cc.y0[c] + 1;
        if ((bw > bh ? bw : bh) >= 2 && Cc.area[c] > best) best = Cc.area[c];
    }
    double big = best ? (double)best / (double)N : 0.0;   /* comps[0][0] / (w * h), or 0.0 with no component */
    *big_out = big;
    *on = big >= min_region;
    rc = 0;
done:
    free(L); free(m); free(lab);
    rf_comps_free(&Cc);
    return rc;
}
