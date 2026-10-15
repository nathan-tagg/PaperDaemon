/* owners.c -- which class owns a pixel that lies between classes (rm_paint.decompose), DECISION code.
 *
 *   rf_gap_assign: the gap close. A gap pixel (gap != 0, lum < paper_cut, some class's density there > 0) goes, when it
 *                  is ink (lum < ink_cut), to the class of the highest density there, the first in class order on a tie
 *                  (numpy's argmax over the stacked densities); otherwise to the nearest class color among the classes
 *                  with density there, the first on a tie (argmin over the distances with the others set to infinity),
 *                  if that distance is below the pixel's distance to paper. The distances are the Python's, operation
 *                  for operation: (_sq(KL - L) + _sq(Ka - a)) + _sq(Kb - b) and (_sq(100 - L) + a * a) + b * b, _sq the
 *                  C runtime's pow(x, 2.0) (rm_paint._sq is np.float_power), the pixel's Lab rm_paint._lab_rows of the
 *                  smoothed color, row by row (lab.c rf_lab_px). The classes' own Lab colors come in from the caller.
 *                  Rows in fixed bands on all threads, one pass each: every pixel is decided on its own and written to
 *                  its own byte, so the split changes nothing; the bands' counts are summed and their touched flags
 *                  ORed afterwards.
 *   rf_gray_halo:  the gray halo. Per gray mask, every 4-connected piece (rmb_npops.components: all of them; their order
 *                  changes nothing here) whose share of pixels inside the skirt -- its count there over its area, one
 *                  float64 division, which is numpy's mean of a boolean selection -- is at least `share` is dropped and
 *                  counted, every other piece kept. Masks on all threads, each its own (an assignment to threads changes
 *                  no mask).
 *   rf_gray_sides: the gray-line pass's enclosure test, per component of rmb_npops.components (info = area, x0, y0,
 *                  width, height of its box; the crop the Python reads is the box with a 1-pixel margin): the non-paper
 *                  share of the four strips `pad` wide just outside the crop (left, right, above, below), each clipped
 *                  to the grid and left out when nothing of it is on the grid, from a summed-area table of nonpaper;
 *                  the piece is the texture of what surrounds it (skipped) when more than `cover` of at least
 *                  max(1, strips - 1) of the strips it has is non-paper. A share is the Python's int / float, one
 *                  float64 division of two exact counts. The side a strip shares with the crop always spans at least
 *                  the box (the box lies in the grid), so "nothing on the grid" -- the Python's clipped width times
 *                  height <= 0 -- is the other side <= 0. * Identity: checked against the reference -- the model run on the reference pictures, and at every call the masks,
 * counts and flags compared with the Python's own lines. */
#include <stdlib.h>
#include "rmfast.h"
#include "internal.h"

typedef struct {
    const uint8_t *const *dens; int32_t nk, H, W;
    const uint8_t *gap, *lum, *rgb; int32_t paper_cut, ink_cut;
    const double *KL; uint8_t *const *masks;
    rf_pow_fn pw; double lut[256];
    int nt; uint8_t *touched; int64_t *count;        /* nt x nk flags, nt counts: one row of each per band */
} gapjob;

static void gap_worker(void *arg, int tid) {
    gapjob *J = (gapjob *)arg;
    const int32_t nk = J->nk;
    const rf_pow_fn pw = J->pw;
    uint8_t *touched = J->touched + (size_t)tid * (size_t)nk;
    int64_t n = 0;
    int32_t y0 = (int32_t)((int64_t)J->H * tid / J->nt), y1 = (int32_t)((int64_t)J->H * (tid + 1) / J->nt);
    for (size_t i = (size_t)y0 * (size_t)J->W, end = (size_t)y1 * (size_t)J->W; i < end; i++) {
        if (!J->gap[i] || J->lum[i] >= J->paper_cut) continue;
        int32_t best = -1;
        uint8_t bv = 0;
        for (int32_t j = 0; j < nk; j++)
            if (J->dens[j][i] > bv) { bv = J->dens[j][i]; best = j; }
        if (best < 0) continue;                                  /* no class's density here: not a gap pixel */
        if (J->lum[i] >= J->ink_cut) {
            double lab[3];
            rf_lab_px(J->lut, pw, J->rgb + 3 * i, lab);
            double L = lab[0], a = lab[1], b = lab[2];
            double bd = (pw(100.0 - L, 2.0) + a * a) + b * b;
            double bdd = 0.0;
            best = -1;
            for (int32_t j = 0; j < nk; j++) {
                if (!J->dens[j][i]) continue;
                double dd = (pw(J->KL[3 * j] - L, 2.0) + pw(J->KL[3 * j + 1] - a, 2.0)) + pw(J->KL[3 * j + 2] - b, 2.0);
                if (best < 0 || dd < bdd) { best = j; bdd = dd; }
            }
            if (best < 0 || !(bdd < bd)) continue;               /* paper is nearer: the pixel stays as it is */
        }
        J->masks[best][i] = 255;
        touched[best] = 1;
        n++;
    }
    J->count[tid] = n;
}

RF_API int64_t rf_gap_assign(const uint8_t *const *dens, int32_t nk, int32_t H, int32_t W, const uint8_t *gap, const uint8_t *lum,
                             const uint8_t *rgb, int32_t paper_cut, int32_t ink_cut, const double *KL, uint8_t *const *masks,
                             uint8_t *touched) {
    for (int32_t j = 0; j < nk; j++) touched[j] = 0;
    if (nk <= 0 || H <= 0 || W <= 0) return 0;
    int nt = rf_threads();
    if (nt > H) nt = H;
    if (nt < 1) nt = 1;
    gapjob J = {dens, nk, H, W, gap, lum, rgb, paper_cut, ink_cut, KL, masks, rf_crt_pow(), {0}, nt, NULL, NULL};
    J.touched = (uint8_t *)calloc((size_t)nt * (size_t)nk, 1);
    J.count = (int64_t *)calloc((size_t)nt, sizeof(int64_t));
    if (!J.touched || !J.count) { free(J.touched); free(J.count); return -1; }
    rf_lab_lut(J.pw, J.lut);
    rf_parallel(nt, gap_worker, &J);
    int64_t n_gap = 0;
    for (int t = 0; t < nt; t++) {
        n_gap += J.count[t];
        for (int32_t j = 0; j < nk; j++) touched[j] |= J.touched[(size_t)t * (size_t)nk + (size_t)j];
    }
    free(J.touched); free(J.count);
    return n_gap;
}

typedef struct {
    const uint8_t *const *masks; uint8_t *const *keeps;
    int32_t n, H, W; const uint8_t *skirt; double share;
    int64_t *halo; int nt;
} halojob;

static void halo_worker(void *arg, int tid) {
    halojob *J = (halojob *)arg;
    size_t N = (size_t)J->H * (size_t)J->W;
    int32_t *lab = (int32_t *)malloc(sizeof(int32_t) * N);
    if (!lab) { for (int32_t k = tid; k < J->n; k += J->nt) J->halo[k] = -1; return; }
    for (int32_t k = tid; k < J->n; k += J->nt) {
        rf_comps C;
        if (rf_label4(J->masks[k], J->H, J->W, lab, &C, 0) < 0) { J->halo[k] = -1; continue; }
        int64_t *hit = (int64_t *)calloc((size_t)C.n + 1, sizeof(int64_t));
        uint8_t *drop = (uint8_t *)calloc((size_t)C.n + 1, 1);
        if (!hit || !drop) { free(hit); free(drop); rf_comps_free(&C); J->halo[k] = -1; continue; }
        for (size_t i = 0; i < N; i++)
            if (lab[i] > 0 && J->skirt[i]) hit[lab[i]]++;
        int64_t nh = 0;
        for (int32_t l = 1; l <= C.n; l++) {
            if (C.area[l] > 0 && (double)hit[l] / (double)C.area[l] >= J->share) { drop[l] = 1; nh += C.area[l]; }
        }
        uint8_t *o = J->keeps[k];
        for (size_t i = 0; i < N; i++) o[i] = (uint8_t)(lab[i] > 0 && !drop[lab[i]]);
        J->halo[k] = nh;
        free(hit); free(drop);
        rf_comps_free(&C);
    }
    free(lab);
}

RF_API int64_t rf_gray_halo(const uint8_t *const *masks, int32_t n, int32_t H, int32_t W, const uint8_t *skirt, double share,
                            uint8_t *const *keeps) {
    if (n <= 0 || H <= 0 || W <= 0) return 0;
    int64_t *halo = (int64_t *)calloc((size_t)n, sizeof(int64_t));
    if (!halo) return -1;
    int nt = rf_threads();
    if (nt > n) nt = n;
    if (nt < 1) nt = 1;
    halojob J = {masks, keeps, n, H, W, skirt, share, halo, nt};
    rf_parallel(nt, halo_worker, &J);
    int64_t tot = 0;
    int failed = 0;
    for (int32_t k = 0; k < n; k++) { if (halo[k] < 0) failed = 1; else tot += halo[k]; }
    free(halo);
    return failed ? -1 : tot;
}

/* the non-paper share of one strip, clipped to the grid -> 1 and *c, or 0 when nothing of it is on the grid */
static int strip_share(const int64_t *S, int32_t H, int32_t W, int64_t x0, int64_t y0, int64_t x1, int64_t y1, double *c) {
    if (x0 < 0) x0 = 0;
    if (y0 < 0) y0 = 0;
    if (x1 > W) x1 = W;
    if (y1 > H) y1 = H;
    if (x1 <= x0 || y1 <= y0) return 0;
    size_t W1 = (size_t)W + 1;
    int64_t s = S[(size_t)y1 * W1 + (size_t)x1] - S[(size_t)y0 * W1 + (size_t)x1] - S[(size_t)y1 * W1 + (size_t)x0] + S[(size_t)y0 * W1 + (size_t)x0];
    *c = (double)s / (double)((x1 - x0) * (y1 - y0));
    return 1;
}

RF_API int32_t rf_gray_sides(const int64_t *info, int32_t n, const uint8_t *nonpaper, int32_t H, int32_t W, int64_t pad, double cover,
                             uint8_t *skip) {
    if (n <= 0) return 0;
    if (H <= 0 || W <= 0) { for (int32_t t = 0; t < n; t++) skip[t] = 0; return 0; }
    size_t W1 = (size_t)W + 1;
    int64_t *S = (int64_t *)malloc(sizeof(int64_t) * W1 * ((size_t)H + 1));
    if (!S) return -1;
    for (size_t x = 0; x < W1; x++) S[x] = 0;
    for (int32_t y = 0; y < H; y++) {
        const uint8_t *row = nonpaper + (size_t)y * (size_t)W;
        int64_t *up = S + (size_t)y * W1, *o = S + ((size_t)y + 1) * W1;
        int64_t run = 0;
        o[0] = 0;
        for (int32_t x = 0; x < W; x++) { run += row[x] != 0; o[x + 1] = up[x + 1] + run; }
    }
    for (int32_t t = 0; t < n; t++) {
        const int64_t *f = info + 5 * (size_t)t;
        int64_t x0 = f[1] - 1, y0 = f[2] - 1, x1 = f[1] + f[3] + 1, y1 = f[2] + f[4] + 1;     /* the crop */
        double c[4];
        int ns = 0, hits = 0;
        if (strip_share(S, H, W, x0 - pad, y0, x0, y1, &c[ns])) ns++;      /* left, right, above, below */
        if (strip_share(S, H, W, x1, y0, x1 + pad, y1, &c[ns])) ns++;
        if (strip_share(S, H, W, x0, y0 - pad, x1, y0, &c[ns])) ns++;
        if (strip_share(S, H, W, x0, y1, x1, y1 + pad, &c[ns])) ns++;
        for (int k = 0; k < ns; k++) hits += c[k] > cover;
        skip[t] = (uint8_t)(ns > 0 && hits >= (ns - 1 > 1 ? ns - 1 : 1));
    }
    free(S);
    return 0;
}