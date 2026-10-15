/* rm_paint.shadow_zones (DECISION code: it picks which zones are shade), in two parts:
 *   rf_zone_interior  its per-zone flatness loop (below);
 *   rf_shadow_zones   the whole function: the zone map, the zones' mean Lab, the soft-edge gradient (Pillow's
 *                     GaussianBlur of Pillow's L conversion, numpy's gradient, np.hypot), the border pairs' counts and
 *                     gradient sums, the flatness, the lightness cut (numpy's linear percentile) and the pair rules
 *                     with CPython's math.hypot / math.atan2 / math.degrees / float %. Identity: checked against the reference
 *                     (every call of real model runs through both) and the strict model check.
 *
 * The shade test's flatness measure -- the per-zone loop of rm_paint.shadow_zones:
 *
 *     core = _erode(lab_img == i, 3)                       3 x 3 minimum, edge pixels replicated
 *     sel  = core if core has a pixel else (lab_img == i)
 *     interior[i] = grad[sel].mean()                         numpy's pairwise sum over sel in raster order, / count
 *
 * for every zone with pixels (others stay 0). A pixel is in its zone's core when every pixel of its 3 x 3 window,
 * clamped to the grid (the replicated edge), is in the zone. */
#include <stdlib.h>
#include "rmfast.h"
#include "internal.h"

/* -> 0, or -1 when memory ran out (interior is then left as it was) */
RF_API int32_t rf_zone_interior(const int32_t *lab, int32_t H, int32_t W, int32_t n, const double *grad, double *interior) {
    size_t N = (size_t)H * W;
    int64_t *nz = (int64_t *)calloc((size_t)n + 1, sizeof(int64_t)), *nc = (int64_t *)calloc((size_t)n + 1, sizeof(int64_t));
    uint8_t *core = (uint8_t *)calloc(N ? N : 1, 1);
    int64_t *cnt = (int64_t *)malloc(sizeof(int64_t) * ((size_t)n + 1)), *off = (int64_t *)malloc(sizeof(int64_t) * ((size_t)n + 2));
    int64_t *fill = (int64_t *)malloc(sizeof(int64_t) * ((size_t)n + 1));
    double *vals = NULL;
    if (!nz || !nc || !core || !cnt || !off || !fill) { free(nz); free(nc); free(core); free(cnt); free(off); free(fill); return -1; }
    for (int32_t y = 0; y < H; y++) {
        int32_t ya = y > 0 ? y - 1 : 0, yb = y < H - 1 ? y + 1 : H - 1;
        for (int32_t x = 0; x < W; x++) {
            int32_t z = lab[(size_t)y * W + x];
            if (z < 0 || z >= n) continue;
            nz[z]++;
            int32_t xa = x > 0 ? x - 1 : 0, xb = x < W - 1 ? x + 1 : W - 1;
            int in = 1;
            for (int32_t yy = ya; yy <= yb && in; yy++)
                for (int32_t xx = xa; xx <= xb; xx++)
                    if (lab[(size_t)yy * W + xx] != z) { in = 0; break; }
            if (in) { core[(size_t)y * W + x] = 1; nc[z]++; }
        }
    }
    /* each zone's selected values, gathered in raster order */
    for (int32_t z = 0; z < n; z++) cnt[z] = nc[z] ? nc[z] : nz[z];
    off[0] = 0;
    for (int32_t z = 0; z < n; z++) off[z + 1] = off[z] + cnt[z];
    vals = (double *)malloc(sizeof(double) * (size_t)(off[n] ? off[n] : 1));
    if (!vals) { free(nz); free(nc); free(core); free(cnt); free(off); free(fill); return -1; }
    for (int32_t z = 0; z < n; z++) fill[z] = off[z];
    for (size_t i = 0; i < N; i++) {
        int32_t z = lab[i];
        if (z < 0 || z >= n) continue;
        if (nc[z] ? core[i] : 1) vals[fill[z]++] = grad[i];
    }
    for (int32_t z = 0; z < n; z++)
        interior[z] = cnt[z] ? (0.0 + rf_pairwise_sum(vals + off[z], cnt[z])) / (double)cnt[z] : 0.0;
    free(nz); free(nc); free(core); free(cnt); free(off); free(vals); free(fill);
    return 0;
}

/* ------------------------------------------------------------------ the whole function */
#include <math.h>
#include <stdatomic.h>
#include <string.h>

/* Python's float % (floatobject.c float_rem; numpy's remainder is the same rule): the remainder takes the
 * divisor's sign */
double rf_py_mod(double vx, double wx) {
    double mod = fmod(vx, wx);
    if (mod != 0.0) { if ((wx < 0) != (mod < 0)) mod += wx; }
    else mod = copysign(0.0, wx);
    return mod;
}

/* CPython's math.atan2 (mathmodule.c m_atan2) on finite arguments -- the zones' mean Lab values are finite sums of
 * finite Lab values, so its NaN and infinity branches cannot be reached here */
double rf_py_atan2(rf_pow_fn at2, double y, double x) {
    if (y == 0.) return copysign(1., x) == 1. ? 0. * y : copysign(3.14159265358979323846, y);
    return at2(y, x);
}

static int cmp_double(const void *x, const void *y) {
    double a = *(const double *)x, b = *(const double *)y;
    return a < b ? -1 : (a > b);
}

/* the k-th smallest of a[0..n) (a is reordered): quickselect with the middle pivot; after 64 rounds the range left
 * is sorted instead, so the work stays O(n log n) whatever the data (the value is the same either way) */
double rf_kth(double *a, int64_t n, int64_t k) {
    int64_t lo = 0, hi = n - 1;
    for (int round = 0; lo < hi; round++) {
        if (round == 64) { qsort(a + lo, (size_t)(hi - lo + 1), sizeof(double), cmp_double); return a[k]; }
        double piv = a[lo + (hi - lo) / 2];
        int64_t i = lo, j = hi;
        while (i <= j) {
            while (a[i] < piv) i++;
            while (a[j] > piv) j--;
            if (i <= j) { double t = a[i]; a[i] = a[j]; a[j] = t; i++; j--; }
        }
        if (k <= j) hi = j;
        else if (k >= i) lo = i;
        else return a[k];
    }
    return a[k];
}

/* numpy.percentile(v, pct) with the default linear method (_quantile: virtual index (n - 1) * q, the neighbors by
 * partition, _lerp with its two-sided form); v is reordered */
double rf_np_percentile(double *v, int64_t n, double pct) {
    double q = pct / 100;
    double virt = (double)(n - 1) * q;
    double pf = floor(virt);
    int64_t prev, next;
    if (virt >= (double)(n - 1)) { prev = next = n - 1; pf = -1.0; }
    else if (virt < 0) { prev = next = 0; pf = 0.0; }
    else { prev = (int64_t)pf; next = prev + 1; }
    double a = rf_kth(v, n, prev);
    double b = next == prev ? a : rf_kth(v, n, next);
    double t = virt - pf;
    double diff = b - a;
    return t >= 0.5 ? b - diff * (1 - t) : a + diff * t;
}

/* numpy.median(v) (v reordered): the middle value, or the mean of the two middle ones, (a + b) / 2 */
double rf_np_median(double *v, int64_t n) {
    if (n % 2) return rf_kth(v, n, n / 2);
    double a = rf_kth(v, n, n / 2 - 1), b = rf_kth(v, n, n / 2);
    return (a + b) / 2.0;
}

/* the border pairs: per code min * n + max, the count and the gradient sums of each direction in raster order */
typedef struct { int64_t code, cnt; double s0, s1; uint8_t h0, h1; } pairacc;
typedef struct { pairacc *e; size_t cap, n; } pairmap;

static uint64_t pm_hash(int64_t k) { uint64_t x = (uint64_t)k * 0x9E3779B97F4A7C15ULL; return x ^ (x >> 29); }

static pairacc *pm_get(pairmap *M, int64_t code) {
    if (2 * (M->n + 1) > M->cap) {
        size_t cap = M->cap ? 2 * M->cap : 4096;
        pairacc *e = (pairacc *)calloc(cap, sizeof(pairacc));
        if (!e) return NULL;
        for (size_t i = 0; i < cap; i++) e[i].code = -1;
        for (size_t i = 0; i < M->cap; i++) if (M->e[i].code >= 0) {
            size_t s = (size_t)(pm_hash(M->e[i].code) & (cap - 1));
            while (e[s].code >= 0) s = (s + 1) & (cap - 1);
            e[s] = M->e[i];
        }
        free(M->e); M->e = e; M->cap = cap;
    }
    size_t s = (size_t)(pm_hash(code) & (M->cap - 1));
    while (M->e[s].code >= 0 && M->e[s].code != code) s = (s + 1) & (M->cap - 1);
    if (M->e[s].code < 0) { M->e[s].code = code; M->n++; }
    return &M->e[s];
}

typedef struct {
    const uint8_t *const *masks; int32_t n, H, W;
    int32_t *lab; const double *g; double *grad; rf_pow_fn hyp;
    atomic_int next; int stage;
} zjob;
#define Z_ROWS 32

static void z_worker(void *arg, int tid) {
    (void)tid;
    zjob *J = (zjob *)arg;
    const int32_t H = J->H, W = J->W;
    for (;;) {
        int32_t y0 = atomic_fetch_add(&J->next, Z_ROWS);
        if (y0 >= H) break;
        int32_t y1 = y0 + Z_ROWS < H ? y0 + Z_ROWS : H;
        if (J->stage == 0) {
            /* lab_img[mask_i != 0] = i, keys in order: the last key holding a pixel wins */
            for (int32_t y = y0; y < y1; y++) {
                int32_t *L = J->lab + (size_t)y * W;
                for (int32_t x = 0; x < W; x++) L[x] = -1;
                for (int32_t i = 0; i < J->n; i++) {
                    const uint8_t *m = J->masks[i] + (size_t)y * W;
                    for (int32_t x = 0; x < W; x++) if (m[x]) L[x] = i;
                }
            }
        } else {
            /* gy, gx = np.gradient(g) (central differences inside, one-sided at the edges); grad = np.hypot(gx, gy) */
            for (int32_t y = y0; y < y1; y++) {
                const double *g = J->g;
                for (int32_t x = 0; x < W; x++) {
                    double gy = y == 0 ? (g[(size_t)W + x] - g[x]) / 1.0
                              : (y == H - 1 ? (g[(size_t)(H - 1) * W + x] - g[(size_t)(H - 2) * W + x]) / 1.0
                                            : (g[(size_t)(y + 1) * W + x] - g[(size_t)(y - 1) * W + x]) / (2. * 1.0));
                    const double *r = g + (size_t)y * W;
                    double gx = x == 0 ? (r[1] - r[0]) / 1.0 : (x == W - 1 ? (r[W - 1] - r[W - 2]) / 1.0 : (r[x + 1] - r[x - 1]) / (2. * 1.0));
                    J->grad[(size_t)y * W + x] = J->hyp(gx, gy);
                }
            }
        }
    }
}

static void z_run(zjob *J, int stage) {
    J->stage = stage;
    atomic_init(&J->next, 0);
    int nt = rf_threads(), bands = (J->H + Z_ROWS - 1) / Z_ROWS;
    rf_parallel(nt < bands ? nt : bands, z_worker, J);
}

/* masks: the n color zones' grids (any non-zero byte set), in key order; rgb: the grid picture (H x W x 3).
 * out: 1 where the pixel's zone is shade. -> 0; -1 out of memory; -2 the grid is under 2 x 2 (np.gradient raises:
 * the caller runs the Python). */
RF_API int32_t rf_shadow_zones(const uint8_t *const *masks, int32_t n, int32_t H, int32_t W, const uint8_t *rgb,
                               float edge_blur, double min_border, double l_step, double min_chroma, double hue_tol,
                               double max_edge, double min_internal_grad, double l_pct,
                               uint8_t *out, double *l_cut_out, int32_t *pairs_out, int32_t *shadow_out) {
    if (H < 2 || W < 2) return -2;
    size_t N = (size_t)H * W;
    int32_t rc = -1;
    int32_t *lab = (int32_t *)malloc(N * sizeof(int32_t));
    double *lab_all = (double *)malloc(N * 3 * sizeof(double));
    uint8_t *lum = (uint8_t *)malloc(N), *glum = (uint8_t *)malloc(N);
    double *g = (double *)malloc(N * sizeof(double)), *grad = (double *)malloc(N * sizeof(double));
    double *msum = (double *)calloc((size_t)n * 3, sizeof(double)), *means = (double *)calloc((size_t)n * 3, sizeof(double));
    int64_t *sizes = (int64_t *)calloc((size_t)n, sizeof(int64_t));
    double *interior = (double *)calloc((size_t)n, sizeof(double));
    uint8_t *shade = (uint8_t *)calloc((size_t)n, 1), *modeled = (uint8_t *)calloc((size_t)n, 1);
    double *pop = NULL;
    pairmap M = {0};
    if (!lab || !lab_all || !lum || !glum || !g || !grad || !msum || !means || !sizes || !interior || !shade || !modeled) goto done;
    zjob J;
    memset(&J, 0, sizeof(J));
    J.masks = masks; J.n = n; J.H = H; J.W = W; J.lab = lab; J.g = g; J.grad = grad; J.hyp = rf_crt_hypot();
    z_run(&J, 0);
    rf_lab_rows(rgb, (int64_t)N, lab_all);
    /* the zones' sizes and mean Lab: lab_all[sel].mean(axis=0), a sequential sum per channel in raster order */
    for (size_t i = 0; i < N; i++) {
        int32_t z = lab[i];
        if (z < 0) continue;
        double *s = msum + 3 * (size_t)z;
        if (sizes[z]) { s[0] += lab_all[3 * i]; s[1] += lab_all[3 * i + 1]; s[2] += lab_all[3 * i + 2]; }
        else { s[0] = lab_all[3 * i]; s[1] = lab_all[3 * i + 1]; s[2] = lab_all[3 * i + 2]; }
        sizes[z]++;
    }
    for (int32_t z = 0; z < n; z++) if (sizes[z]) for (int c = 0; c < 3; c++) means[3 * z + c] = msum[3 * z + c] / (double)sizes[z];
    /* small.convert("L") (Pillow's rgb2l), GaussianBlur(edge_blur), as float64 */
    for (size_t i = 0; i < N; i++) {
        const uint8_t *p = rgb + 3 * i;
        lum[i] = (uint8_t)(((uint32_t)p[0] * 19595u + (uint32_t)p[1] * 38470u + (uint32_t)p[2] * 7471u + 0x8000u) >> 16);
    }
    if (rf_box_blur(lum, glum, H, W, 1, edge_blur, 1) != 0) goto done;
    for (size_t i = 0; i < N; i++) g[i] = (double)glum[i];
    z_run(&J, 1);
    /* the border pairs, horizontal neighbors then vertical, each in raster order */
    for (int dir = 0; dir < 2; dir++) {
        int32_t dy = dir, dx = 1 - dir;
        for (int32_t y = 0; y < H - dy; y++) {
            const int32_t *A = lab + (size_t)y * W, *B = lab + (size_t)(y + dy) * W + dx;
            const double *gr = grad + (size_t)y * W;
            for (int32_t x = 0; x < W - dx; x++) {
                int32_t a = A[x], b = B[x];
                if (a < 0 || b < 0 || a == b) continue;
                int64_t code = (int64_t)(a < b ? a : b) * n + (a < b ? b : a);
                pairacc *e = pm_get(&M, code);
                if (!e) goto done;
                e->cnt++;
                if (dir == 0) { e->s0 = e->h0 ? e->s0 + gr[x] : 0.0 + gr[x]; e->h0 = 1; }
                else { e->s1 = e->h1 ? e->s1 + gr[x] : 0.0 + gr[x]; e->h1 = 1; }
            }
        }
    }
    if (rf_zone_interior(lab, H, W, n, grad, interior) != 0) goto done;
    /* the lightness cut over the modeled zones (all live pixels when none is modeled or they hold none) */
    int any_modeled = 0;
    for (int32_t z = 0; z < n; z++) if (interior[z] >= min_internal_grad) { modeled[z] = 1; any_modeled = 1; }
    int64_t npop = 0, nlive = 0;
    for (size_t i = 0; i < N; i++) if (lab[i] >= 0) { nlive++; if (!any_modeled || modeled[lab[i]]) npop++; }
    int all_live = !any_modeled || npop == 0;
    if (all_live) npop = nlive;
    double l_cut = 50.0;
    if (npop > 0) {
        pop = (double *)malloc((size_t)npop * sizeof(double));
        if (!pop) goto done;
        int64_t k = 0;
        for (size_t i = 0; i < N; i++) if (lab[i] >= 0 && (all_live || modeled[lab[i]])) pop[k++] = lab_all[3 * i];
        l_cut = rf_np_percentile(pop, npop, l_pct);
    }
    /* the pair rules */
    rf_pow_fn at2 = rf_crt_atan2();
    const double rad_to_deg = 180.0 / 3.14159265358979323846;       /* CPython's math.degrees factor */
    int32_t pairs = 0;
    for (size_t s = 0; s < M.cap; s++) {
        const pairacc *e = &M.e[s];
        if (e->code < 0) continue;
        if ((double)e->cnt < min_border) continue;
        pairs++;
        int32_t i = (int32_t)(e->code / n), j = (int32_t)(e->code % n);
        if (!sizes[i] || !sizes[j]) continue;
        int32_t dark = means[3 * i] < means[3 * j] ? i : j, light = dark == i ? j : i;
        const double *md = means + 3 * (size_t)dark, *ml = means + 3 * (size_t)light;
        if (ml[0] - md[0] < l_step) continue;
        double ca = rf_py_hypot(md[1], md[2]), cb = rf_py_hypot(ml[1], ml[2]);
        if ((cb < ca ? cb : ca) >= min_chroma) {
            double ha = rf_py_atan2(at2, md[2], md[1]) * rad_to_deg, hb = rf_py_atan2(at2, ml[2], ml[1]) * rad_to_deg;
            if (fabs(rf_py_mod(ha - hb + 180.0, 360.0) - 180.0) > hue_tol) continue;
        }
        double soft = 0.0;
        if (e->h0) soft = soft + e->s0;
        if (e->h1) soft = soft + e->s1;
        if (soft / (double)e->cnt > max_edge) continue;
        if (md[0] > l_cut) continue;
        if (interior[dark] < min_internal_grad) continue;
        shade[dark] = 1;
    }
    int32_t nshade = 0;
    for (int32_t z = 0; z < n; z++) nshade += shade[z];
    for (size_t i = 0; i < N; i++) out[i] = lab[i] >= 0 && shade[lab[i]];
    *l_cut_out = l_cut; *pairs_out = pairs; *shadow_out = nshade;
    rc = 0;
done:
    free(lab); free(lab_all); free(lum); free(glum); free(g); free(grad); free(msum); free(means); free(sizes);
    free(interior); free(shade); free(modeled); free(pop); free(M.e);
    return rc;
}