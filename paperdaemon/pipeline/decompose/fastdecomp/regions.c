/* The region budget's per-pixel work (rm_regions): the pieces of every class mask, each round's per-piece statistics
 * and the piece-pair border statistics, with numpy's orders and sums.
 *
 *   rf_pieces:        rm_regions.pieces -- 4-connected components of each class mask (`mask > 0`: any non-zero byte,
 *                     each mask read in place) in class order, numbered in raster order of their first pixel
 *                     (scipy.ndimage.label's numbering), offset by the pieces before; a later class overwrites an
 *                     earlier one where masks overlap.
 *   rf_region_stats:  rm_regions._stats -- per piece: area, summed Lab, mean x and y, bounding box width and height;
 *                     every sum taken over the pixels in raster order (np.bincount's order).
 *   rf_region_edges:  rm_regions._edges -- every 4-neighbor pixel pair across two pieces (all horizontal pairs in raster
 *                     order, then all vertical ones), keyed min * n + max; per distinct key (ascending): the pair count
 *                     and the sum of the source dE in that order, dE = sqrt((d0*d0 + d1*d1) + d2*d2).
 * Every allocation is checked: a failure returns -1 with nothing left allocated (DECISION code). */
#include <math.h>
#include <stdatomic.h>
#include <stdlib.h>
#include <string.h>
#include "rmfast.h"
#include "internal.h"

/* rf_pieces: up to PIECE_BATCH classes are labeled at once on the threads, each into its own grid; then the batch is
 * written in class order, rows on all threads -- every pixel gets the same writes in the same order as with one class
 * after another. */
#define PIECE_BATCH 8
typedef struct {
    const uint8_t *const *masks; int32_t H, W, base, nb, stage; int nt;
    int32_t **lab; int32_t *cnt, *off, *labels;
    atomic_int next, oom;
} piecejob;

static void piece_worker(void *arg, int tid) {
    piecejob *J = (piecejob *)arg;
    if (J->stage == 0) {
        for (;;) {
            int k = atomic_fetch_add(&J->next, 1);
            if (k >= J->nb) break;
            rf_comps C;
            int32_t c = rf_label4(J->masks[J->base + k], J->H, J->W, J->lab[k], &C, 0);
            if (c < 0) { atomic_store(&J->oom, 1); J->cnt[k] = 0; continue; }
            rf_comps_free(&C);
            J->cnt[k] = c;
        }
        return;
    }
    size_t W = (size_t)J->W;
    for (int32_t y = tid; y < J->H; y += J->nt)
        for (int32_t k = 0; k < J->nb; k++) {
            if (!J->cnt[k]) continue;
            const int32_t *L = J->lab[k] + (size_t)y * W;
            int32_t *o = J->labels + (size_t)y * W, add = J->off[k] - 1;
            for (size_t x = 0; x < W; x++) if (L[x]) o[x] = L[x] + add;
        }
}

RF_API int32_t rf_pieces(const uint8_t *const *masks, int32_t nk, int32_t H, int32_t W, int32_t *labels, int32_t *count_per_class) {
    size_t N = (size_t)H * W;
    for (size_t i = 0; i < N; i++) labels[i] = -1;
    int nt = rf_threads();
    int32_t nbm = nt < PIECE_BATCH ? nt : PIECE_BATCH;
    if (nbm > nk) nbm = nk;
    if (nbm < 1) nbm = 1;
    piecejob J;
    memset(&J, 0, sizeof(J));
    int32_t cnt[PIECE_BATCH], off[PIECE_BATCH];
    J.lab = (int32_t **)calloc((size_t)nbm, sizeof(int32_t *));
    int ok = J.lab != NULL;
    for (int32_t k = 0; ok && k < nbm; k++) ok = (J.lab[k] = (int32_t *)malloc(sizeof(int32_t) * (N ? N : 1))) != NULL;
    int32_t n = 0;
    atomic_init(&J.oom, ok ? 0 : 1);
    J.masks = masks; J.H = H; J.W = W; J.labels = labels; J.cnt = cnt; J.off = off;
    J.nt = nt < H ? nt : (H > 0 ? H : 1);
    for (int32_t base = 0; ok && base < nk; base += nbm) {
        J.base = base; J.nb = nk - base < nbm ? nk - base : nbm;
        J.stage = 0;
        atomic_init(&J.next, 0);
        rf_parallel(J.nb, piece_worker, &J);
        if (atomic_load(&J.oom)) break;
        for (int32_t k = 0; k < J.nb; k++) { off[k] = n; count_per_class[base + k] = cnt[k]; n += cnt[k]; }
        J.stage = 1;
        rf_parallel(J.nt, piece_worker, &J);
    }
    if (J.lab) for (int32_t k = 0; k < nbm; k++) free(J.lab[k]);
    free(J.lab);
    return atomic_load(&J.oom) ? -1 : n;
}

/* -> 0, or -1 when memory ran out */
RF_API int32_t rf_region_stats(const int32_t *labels, const double *lab_img, int32_t H, int32_t W, int32_t n,
                               double *area, double *sum_lab, double *cx, double *cy, double *bw, double *bh) {
    int64_t *cnt = (int64_t *)calloc((size_t)n + 1, sizeof(int64_t));
    double *sx = (double *)calloc((size_t)n + 1, sizeof(double)), *sy = (double *)calloc((size_t)n + 1, sizeof(double));
    int64_t *x0 = (int64_t *)malloc(sizeof(int64_t) * ((size_t)n + 1)), *x1 = (int64_t *)malloc(sizeof(int64_t) * ((size_t)n + 1));
    int64_t *y0 = (int64_t *)malloc(sizeof(int64_t) * ((size_t)n + 1)), *y1 = (int64_t *)malloc(sizeof(int64_t) * ((size_t)n + 1));
    if (!cnt || !sx || !sy || !x0 || !x1 || !y0 || !y1) { free(cnt); free(sx); free(sy); free(x0); free(x1); free(y0); free(y1); return -1; }
    for (int32_t i = 0; i < n; i++) { x0[i] = W; x1[i] = -1; y0[i] = H; y1[i] = -1; sum_lab[3 * i] = sum_lab[3 * i + 1] = sum_lab[3 * i + 2] = 0.0; }
    for (int32_t y = 0; y < H; y++)
        for (int32_t x = 0; x < W; x++) {
            size_t p = (size_t)y * W + x;
            int32_t k = labels[p];
            if (k < 0) continue;
            cnt[k]++;
            sum_lab[3 * k] += lab_img[3 * p]; sum_lab[3 * k + 1] += lab_img[3 * p + 1]; sum_lab[3 * k + 2] += lab_img[3 * p + 2];
            sx[k] += (double)x; sy[k] += (double)y;
            if (x < x0[k]) x0[k] = x;
            if (x > x1[k]) x1[k] = x;
            if (y < y0[k]) y0[k] = y;
            if (y > y1[k]) y1[k] = y;
        }
    for (int32_t i = 0; i < n; i++) {
        area[i] = (double)cnt[i];
        double safe = area[i] > 1.0 ? area[i] : 1.0;
        cx[i] = sx[i] / safe; cy[i] = sy[i] / safe;
        bw[i] = (double)(x1[i] - x0[i] + 1); bh[i] = (double)(y1[i] - y0[i] + 1);
    }
    free(cnt); free(sx); free(sy); free(x0); free(x1); free(y0); free(y1);
    return 0;
}

/* pair key -> slot, open addressing; slots keep their first-seen order, the keys are sorted at the end */
typedef struct { int64_t *keys; int32_t *slot; size_t cap; } kmap;

static uint64_t kh(int64_t k) { uint64_t x = (uint64_t)k; x ^= x >> 33; x *= 0xff51afd7ed558ccdULL; x ^= x >> 33; x *= 0xc4ceb9fe1a85ec53ULL; x ^= x >> 33; return x; }

typedef struct { int64_t key; int32_t slot; } kslot;
static int cmp_kslot(const void *a, const void *b) { int64_t x = ((const kslot *)a)->key, y = ((const kslot *)b)->key; return x < y ? -1 : (x > y); }

RF_API int32_t rf_region_edges(const int32_t *labels, const double *lab_img, int32_t H, int32_t W, int32_t n,
                               int64_t **a_out, int64_t **b_out, double **cnt_out, double **sde_out) {
    size_t cap = 1024;
    while (cap < (size_t)4 * ((size_t)H * W / 8 + 64)) cap <<= 1;
    *a_out = NULL; *b_out = NULL; *cnt_out = NULL; *sde_out = NULL;
    kmap M; M.cap = cap; M.keys = (int64_t *)malloc(sizeof(int64_t) * cap); M.slot = (int32_t *)malloc(sizeof(int32_t) * cap);
    int32_t ns = 0, scap = 4096;
    int64_t *skey = (int64_t *)malloc(sizeof(int64_t) * scap);
    double *scnt = (double *)malloc(sizeof(double) * scap), *ssde = (double *)malloc(sizeof(double) * scap);
    kslot *ord = NULL;
    int64_t *A = NULL, *B = NULL;
    double *C = NULL, *D = NULL;
    int32_t rc = -1;
    if (!M.keys || !M.slot || !skey || !scnt || !ssde) goto done;
    for (size_t t = 0; t < cap; t++) M.slot[t] = -1;
    for (int dir = 0; dir < 2; dir++) {
        int32_t dy = dir, dx = 1 - dir;
        for (int32_t y = 0; y < H - dy; y++)
            for (int32_t x = 0; x < W - dx; x++) {
                size_t p = (size_t)y * W + x, q = (size_t)(y + dy) * W + (x + dx);
                int32_t a = labels[p], b = labels[q];
                if (a == b || a < 0 || b < 0) continue;
                double d0 = lab_img[3 * p] - lab_img[3 * q], d1 = lab_img[3 * p + 1] - lab_img[3 * q + 1], d2 = lab_img[3 * p + 2] - lab_img[3 * q + 2];
                double de = sqrt((d0 * d0 + d1 * d1) + d2 * d2);
                int64_t key = (int64_t)(a < b ? a : b) * n + (a < b ? b : a);
                size_t h = kh(key) & (M.cap - 1);
                for (;;) {
                    if (M.slot[h] < 0) {
                        if (ns == scap) {
                            int64_t *k2 = (int64_t *)realloc(skey, sizeof(int64_t) * (size_t)scap * 2);
                            if (!k2) goto done;
                            skey = k2;
                            double *c2 = (double *)realloc(scnt, sizeof(double) * (size_t)scap * 2);
                            if (!c2) goto done;
                            scnt = c2;
                            double *d2_ = (double *)realloc(ssde, sizeof(double) * (size_t)scap * 2);
                            if (!d2_) goto done;
                            ssde = d2_;
                            scap *= 2;
                        }
                        M.keys[h] = key; M.slot[h] = ns; skey[ns] = key; scnt[ns] = 0.0; ssde[ns] = 0.0; ns++;
                        if ((size_t)ns * 2 > M.cap) {          /* grow */
                            size_t nc = M.cap * 2;
                            int64_t *nk = (int64_t *)malloc(sizeof(int64_t) * nc); int32_t *nsl = (int32_t *)malloc(sizeof(int32_t) * nc);
                            if (!nk || !nsl) { free(nk); free(nsl); goto done; }
                            for (size_t t = 0; t < nc; t++) nsl[t] = -1;
                            for (size_t t = 0; t < M.cap; t++) if (M.slot[t] >= 0) {
                                size_t g = kh(M.keys[t]) & (nc - 1);
                                while (nsl[g] >= 0) g = (g + 1) & (nc - 1);
                                nk[g] = M.keys[t]; nsl[g] = M.slot[t];
                            }
                            free(M.keys); free(M.slot); M.keys = nk; M.slot = nsl; M.cap = nc;
                        }
                        h = (size_t)-1;
                        break;
                    }
                    if (M.keys[h] == key) break;
                    h = (h + 1) & (M.cap - 1);
                }
                int32_t s = (h == (size_t)-1) ? ns - 1 : M.slot[h];
                scnt[s] += 1.0; ssde[s] += de;
            }
    }
    ord = (kslot *)malloc(sizeof(kslot) * (ns ? ns : 1));
    A = (int64_t *)malloc(sizeof(int64_t) * (ns ? ns : 1)); B = (int64_t *)malloc(sizeof(int64_t) * (ns ? ns : 1));
    C = (double *)malloc(sizeof(double) * (ns ? ns : 1)); D = (double *)malloc(sizeof(double) * (ns ? ns : 1));
    if (!ord || !A || !B || !C || !D) { free(A); free(B); free(C); free(D); goto done; }
    for (int32_t s = 0; s < ns; s++) { ord[s].key = skey[s]; ord[s].slot = s; }
    qsort(ord, ns, sizeof(kslot), cmp_kslot);
    for (int32_t t = 0; t < ns; t++) { int64_t k = ord[t].key; A[t] = k / n; B[t] = k % n; C[t] = scnt[ord[t].slot]; D[t] = ssde[ord[t].slot]; }
    *a_out = A; *b_out = B; *cnt_out = C; *sde_out = D;
    rc = ns;
done:
    free(ord); free(skey); free(scnt); free(ssde); free(M.keys); free(M.slot);
    return rc;
}
