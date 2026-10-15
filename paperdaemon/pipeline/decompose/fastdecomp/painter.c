/* painter.c -- rm_paint.decompose's body from the quantized class masks to its last stroke, as the painter runs it
 * (SUBCELL_GEOMETRY, V70_TRUE_COLOR, ZONE_AT_ONCE without a color grow, no tone ramp): DECISION code -- which class owns
 * each pixel before anything is drawn, then the order the zones go down in; the drawing itself is the ring planner's
 * (store.c) and the ink pass's (inkpass.c).
 *
 * The class masks are an ordered list (the Python dict's insertion order, which is the draw order): "tone", "black",
 * "_ink" and the ("rgb", (r, g, b)) washes, each a 0/255 grid owned here. The Python's lines, in order:
 *   the light tone pockets: the components of the inverted color union (expanded by a pixel) that do not touch the
 *     outside, with at least half their area light tone (pockets.c rf_tone_pockets); each goes to the wash keyed
 *     ("rgb", _tc_key(round(mean color))) -- a key not yet present is added at the end -- and leaves tone;
 *   the pockets of paper or tone enclosed by color (more than one color): rm_paint._fill_holes of the expanded union
 *     (outline.c rf_fill_holes, small = (FILL_HOLE_PAGE / ppg) ** 2 with the C runtime's pow, as CPython's **),
 *     cropped, minus the union, times tone (SUBCELL_GEOMETRY), into the colors (pockets.c rf_pockets);
 *   the gap close: the union's closing by r (zero padded, rank.c), minus the union; the classes' anchor densities
 *     (blur.c rf_gap_density) and each gap pixel's class (owners.c rf_gap_assign) against the classes' Lab colors
 *     (lab.c, rm_paint._lab of the key's integers);
 *   the painterly share: the pixels of the washes whose Lab chroma (CPython's math.hypot) reaches CHROMA_MIN, over the
 *     grid;
 *   tonal_ink (tonal.c): the protected ink pixels go to washes of their ladder colors, new keys added at the end in
 *     palette order;
 *   rmb_resolution.coarsen_washes: below 0.425 page px per grid px, the washes vote per cell of max(1, floor(.85 /
 *     ppg)) grid px (the first of equal counts wins, as argmax), counted one row of cells at a time;
 *   the speck absorber (absorb.c) when the cell is one pixel;
 *   the gray halo: the gray washes' pieces lying within the skirt of black (owners.c rf_gray_halo);
 *   the zones: one fill per wash, planned as one batch on all threads (store.c rf_store_fill_batch);
 *   the ink section and the contour pass (inkpass.c).
 * The Python's report values come back in rep (rmfast.h) and the final keys in *keys_out.
 * Identity: each painter run through the twin's Python lines and through this (the strokes strictly, their order and
 * the report), and the strict check of the model's strokes against the pure-Python model's. */
#include <float.h>
#include <math.h>
#include <stdlib.h>
#include <string.h>
#include "rmfast.h"
#include "internal.h"

static int finite_d(double x) { return x >= -DBL_MAX && x <= DBL_MAX; }      /* false for NaN and both infinities */

/* the head's parameters: every float finite, TC_QUANT at least 2 (the ladder's step divides by TC_QUANT - 1) */
static int head_params_ok(const rf_head_params *Hp) {
    const double v[] = {Hp->pocket_l, Hp->gap_close_g, Hp->gap_close_page, Hp->paper_l, Hp->ink_l, Hp->hl_min_page, Hp->chroma_min,
                        Hp->painterly_chroma_share, Hp->black_l, Hp->black_mass_thick_paint, Hp->fill_hole_page, Hp->absorb_max_de,
                        Hp->gray_halo_open, Hp->gray_halo_share, Hp->tc_ink_l};
    for (size_t i = 0; i < sizeof(v) / sizeof(v[0]); i++) if (!finite_d(v[i])) return 0;
    return Hp->tc_quant >= 2 && Hp->absorb_max_area >= 0;
}

enum { K_TONE = 0, K_BLACK = 1, K_RGB = 2, K_INK = 3 };

typedef struct { int32_t kind, rgb[3]; uint8_t *m; } mkey;
typedef struct { mkey *k; int32_t n, cap; } mset;

static int64_t round_i(double x) {         /* int(round(x)) of a finite x, clamped into int32's range */
    double r = rint(x);
    if (r > 2147483647.0) r = 2147483647.0;
    if (r < -2147483648.0) r = -2147483648.0;
    return (int64_t)r;
}
static int64_t max_i(int64_t a, int64_t b) { return a > b ? a : b; }
static int64_t min_i(int64_t a, int64_t b) { return a < b ? a : b; }

static void mset_free(mset *M) {
    for (int32_t i = 0; i < M->n; i++) free(M->k[i].m);
    free(M->k);
    memset(M, 0, sizeof(*M));
}

/* append a key owning plane m -> its index, -1 out of memory (m is then freed) */
static int32_t mset_add(mset *M, int32_t kind, const int32_t *rgb, uint8_t *m) {
    if (M->n == M->cap) {
        int32_t c = M->cap ? M->cap * 2 : 64;
        mkey *p = (mkey *)realloc(M->k, (size_t)c * sizeof(mkey));
        if (!p) { free(m); return -1; }
        M->k = p; M->cap = c;
    }
    mkey *k = &M->k[M->n];
    k->kind = kind; k->m = m;
    k->rgb[0] = rgb ? rgb[0] : 0; k->rgb[1] = rgb ? rgb[1] : 0; k->rgb[2] = rgb ? rgb[2] : 0;
    return M->n++;
}

static int32_t mset_kind(const mset *M, int32_t kind) {
    for (int32_t i = 0; i < M->n; i++) if (M->k[i].kind == kind) return i;
    return -1;
}

static int32_t mset_rgb(const mset *M, const int32_t *rgb) {
    for (int32_t i = 0; i < M->n; i++)
        if (M->k[i].kind == K_RGB && M->k[i].rgb[0] == rgb[0] && M->k[i].rgb[1] == rgb[1] && M->k[i].rgb[2] == rgb[2]) return i;
    return -1;
}

/* the washes' planes in key order (the Python's color_keys) -> their count; idx (if given) their key indices */
static int32_t colors_of(const mset *M, uint8_t **planes, int32_t *idx) {
    int32_t c = 0;
    for (int32_t i = 0; i < M->n; i++) if (M->k[i].kind == K_RGB) { if (idx) idx[c] = i; planes[c++] = M->k[i].m; }
    return c;
}

/* rm_paint._tc_key of one channel: round(round(c / step) * step), Python's half-to-even rounding */
static int32_t tc_chan(int64_t c, double step) { return (int32_t)round_i(rint((double)c / step) * step); }

/* the union of the washes as 0/255 */
static void union255(uint8_t *const *planes, int32_t n, int32_t H, int32_t W, uint8_t *out) {
    rf_any_nonzero((const uint8_t *const *)planes, n, H, W, out);
    size_t N = (size_t)H * (size_t)W;
    for (size_t i = 0; i < N; i++) out[i] = out[i] ? 255 : 0;
}

static int64_t count_set(const uint8_t *a, size_t n) {
    int64_t c = 0;
    for (size_t i = 0; i < n; i++) c += a[i] != 0;
    return c;
}

/* rmb_resolution.coarsen_washes -> 0, -1 out of memory; rep[9..12] as rmfast.h says */
static int coarsen(mset *M, int32_t H, int32_t W, double ppg, double *rep) {
    double fl = floor(.85 / ppg);
    int64_t cell = fl >= 1.0 ? (fl < 1e9 ? (int64_t)fl : 1000000000) : 1;
    rep[9] = (double)cell; rep[10] = 0.0; rep[11] = -1.0; rep[12] = 0.0;
    if (cell < 2) { rep[9] = 1.0; return 0; }
    int32_t nk = 0;
    for (int32_t i = 0; i < M->n; i++) nk += M->k[i].kind == K_RGB;
    if (!nk) return 0;
    size_t N = (size_t)H * (size_t)W;
    int32_t *owner = (int32_t *)malloc(sizeof(int32_t) * (N ? N : 1)), *kidx = (int32_t *)malloc(sizeof(int32_t) * (size_t)nk);
    if (!owner || !kidx) { free(owner); free(kidx); return -1; }
    for (size_t p = 0; p < N; p++) owner[p] = -1;
    int32_t j = 0;
    for (int32_t i = 0; i < M->n; i++) {
        if (M->k[i].kind != K_RGB) continue;
        kidx[j] = i;
        const uint8_t *m = M->k[i].m;
        for (size_t p = 0; p < N; p++) if (m[p]) owner[p] = j;      /* the last key wins, as the Python's loop */
        j++;
    }
    int any = 0;
    for (size_t p = 0; p < N && !any; p++) any = owner[p] >= 0;
    if (!any) { free(owner); free(kidx); return 0; }
    int64_t nx = (W + cell - 1) / cell, changed = 0, occupied = 0;
    int64_t *cnt = (int64_t *)malloc(sizeof(int64_t) * (size_t)nx * (size_t)nk);
    int32_t *win = (int32_t *)malloc(sizeof(int32_t) * (size_t)nx);
    if (!cnt || !win) { free(owner); free(kidx); free(cnt); free(win); return -1; }
    for (int64_t by = 0; by * cell < H; by++) {         /* one row of cells at a time: the bincount of its blocks */
        int64_t y0 = by * cell, y1 = min_i(H, y0 + cell);
        memset(cnt, 0, sizeof(int64_t) * (size_t)nx * (size_t)nk);
        for (int64_t y = y0; y < y1; y++)
            for (int64_t x = 0; x < W; x++) { int32_t o = owner[(size_t)y * W + x]; if (o >= 0) cnt[(x / cell) * nk + o]++; }
        for (int64_t bx = 0; bx < nx; bx++) {
            const int64_t *c = cnt + bx * nk;
            int32_t best = 0; int64_t tot = c[0];
            for (int32_t k = 1; k < nk; k++) { tot += c[k]; if (c[k] > c[best]) best = k; }
            win[bx] = best;
            occupied += tot > 0;
        }
        for (int64_t y = y0; y < y1; y++)
            for (int64_t x = 0; x < W; x++) {
                int32_t *o = &owner[(size_t)y * W + x];
                if (*o < 0) continue;
                if (*o != win[x / cell]) changed++;
                *o = win[x / cell];
            }
    }
    for (int32_t k = 0; k < nk; k++) {
        uint8_t *m = M->k[kidx[k]].m;
        for (size_t p = 0; p < N; p++) m[p] = owner[p] == k ? 255 : 0;
    }
    free(owner); free(kidx); free(cnt); free(win);
    rep[10] = (double)changed; rep[11] = (double)occupied; rep[12] = 1.0;
    return 0;
}

/* -> 0; -1 out of memory; -2 refused (a step the Python must run: the ink pass's refusals). nk quantized keys: kinds
 * (0 tone, 1 black, 2 rgb, 3 _ink), rgbs (3 per key), planes (0/255, read only). rep: RF_BODY_REP doubles. *keys_out:
 * the final keys, 4 ints each (kind, r, g, b), rf_free'd by the caller. */
RF_API int32_t rf_painter_body(rf_store *S, const rf_ink_params *P, const rf_head_params *Hp, int32_t H, int32_t W, int32_t nk,
                              const int32_t *kinds, const int32_t *rgbs, const uint8_t *const *planes, const uint8_t *rgb,
                              const uint8_t *lum, const uint8_t *ridge, int32_t **order_out, int32_t *norder, int32_t **keys_out,
                              int32_t *nkeys_out, double *rep) {
    *order_out = NULL; *norder = 0; *keys_out = NULL; *nkeys_out = 0;
    for (int i = 0; i < RF_BODY_REP; i++) rep[i] = 0.0;
    if (H <= 0 || W <= 0 || !rf_ink_params_ok(P) || !head_params_ok(Hp)) return -2;
    /* from here ppg, detail and up are finite and positive and TC_QUANT - 1 >= 1: every division below by them has a
     * non-zero divisor; every other divisor is a count of at least one */
    size_t N = (size_t)H * (size_t)W;
    const size_t Ne = ((size_t)H + 2) * ((size_t)W + 2);
    int32_t rc = -1;
    mset M = {0};
    uint8_t **cols = NULL, *u = NULL, *a = NULL, *b = NULL, *e = NULL, *sp = NULL, *D = NULL, *has = NULL;
    int32_t *cidx = NULL, *zmade = NULL, *iorder = NULL, *korder = NULL;
    int64_t *pinfo = NULL, *pxy = NULL;
    rf_fill_job *zj = NULL;
    rf_ink_params IP = *P;
    rf_pow_fn pw = rf_crt_pow();
    double lut[256];
    rf_lab_lut(pw, lut);
    const double ppg = P->ppg, up = P->up;
    const double step = 255.0 / (double)(Hp->tc_quant - 1);
    const int64_t min_span_col = max_i(2, round_i((Hp->hl_min_page / ppg) / P->detail));
    double t_start = rf_now();

    for (int32_t i = 0; i < nk; i++) {
        uint8_t *m = (uint8_t *)malloc(N ? N : 1);
        if (!m) goto done;
        memcpy(m, planes[i], N);
        if (mset_add(&M, kinds[i], rgbs + 3 * (size_t)i, m) < 0) goto done;
    }
    u = (uint8_t *)malloc(N ? N : 1); a = (uint8_t *)malloc(Ne); b = (uint8_t *)malloc(Ne);
    if (!u || !a || !b) goto done;
#define COLS() (free(cols), free(cidx), cols = (uint8_t **)malloc(sizeof(uint8_t *) * (size_t)(M.n + 1)), \
                cidx = (int32_t *)malloc(sizeof(int32_t) * (size_t)(M.n + 1)), (cols && cidx) ? colors_of(&M, cols, cidx) : -1)
    int32_t ncol = COLS();
    if (ncol < 0) goto done;

    /* the light tone pockets */
    int32_t it = mset_kind(&M, K_TONE);
    if (ncol > 0 && it >= 0) {
        union255(cols, ncol, H, W, u);
        for (size_t i = 0; i < Ne; i++) a[i] = 255;
        for (int32_t y = 0; y < H; y++)
            for (int32_t x = 0; x < W; x++) a[(size_t)(y + 1) * (W + 2) + x + 1] = u[(size_t)y * W + x] ? 0 : 255;
        int32_t np_ = rf_tone_pockets(a, H + 2, W + 2, M.k[it].m, lum, rgb, Hp->pocket_l * 2.55, &pinfo, &pxy);
        if (np_ < 0) goto done;
        if (np_ > 0) {
            /* each pocket's key, then the keys in first-appearance order with their pockets */
            int32_t *pk = (int32_t *)malloc(sizeof(int32_t) * 3 * (size_t)np_), *done_ = (int32_t *)calloc((size_t)np_, sizeof(int32_t));
            int64_t *start = (int64_t *)malloc(sizeof(int64_t) * (size_t)np_);
            if (!pk || !done_ || !start) { free(pk); free(done_); free(start); goto done; }
            int64_t o = 0, total = 0;
            for (int32_t t = 0; t < np_; t++) {
                const int64_t *f = pinfo + 5 * (size_t)t;
                double n = (double)f[1];
                for (int c = 0; c < 3; c++) pk[3 * t + c] = tc_chan(round_i((double)f[2 + c] / n), step);
                start[t] = o; o += f[1]; total += f[1];
            }
            int bad = 0;
            for (int32_t t = 0; t < np_ && !bad; t++) {
                if (done_[t]) continue;
                int32_t ki = mset_rgb(&M, pk + 3 * t);
                if (ki < 0) {
                    uint8_t *m = (uint8_t *)calloc(N ? N : 1, 1);
                    if (!m || (ki = mset_add(&M, K_RGB, pk + 3 * t, m)) < 0) { bad = 1; break; }
                }
                uint8_t *km = M.k[ki].m, *tm = M.k[mset_kind(&M, K_TONE)].m;
                for (int32_t s = t; s < np_; s++) {
                    if (done_[s] || pk[3 * s] != pk[3 * t] || pk[3 * s + 1] != pk[3 * t + 1] || pk[3 * s + 2] != pk[3 * t + 2]) continue;
                    done_[s] = 1;
                    const int64_t *xy = pxy + 2 * start[s];
                    for (int64_t q = 0; q < pinfo[5 * (size_t)s + 1]; q++) {
                        size_t p = (size_t)xy[2 * q + 1] * (size_t)W + (size_t)xy[2 * q];
                        km[p] = 255; tm[p] = 0;
                    }
                }
            }
            free(pk); free(done_); free(start);
            if (bad) goto done;
            rep[0] = 1.0; rep[1] = (double)total;
        }
        rf_free(pinfo); rf_free(pxy); pinfo = NULL; pxy = NULL;
        if ((ncol = COLS()) < 0) goto done;
    }

    /* the pockets enclosed by color */
    if (ncol > 1) {
        union255(cols, ncol, H, W, u);
        memset(a, 0, Ne);
        for (int32_t y = 0; y < H; y++) memcpy(a + (size_t)(y + 1) * (W + 2) + 1, u + (size_t)y * W, (size_t)W);
        double small = pw(Hp->fill_hole_page / ppg, 2.0);
        if (rf_fill_holes(a, H + 2, W + 2, small, 1.5 * up, b) < 0) goto done;
        it = mset_kind(&M, K_TONE);
        const uint8_t *tm = it >= 0 ? M.k[it].m : NULL;
        int any = 0;
        for (int32_t y = 0; y < H; y++)
            for (int32_t x = 0; x < W; x++) {
                size_t p = (size_t)y * W + x;
                uint8_t v = (uint8_t)(b[(size_t)(y + 1) * (W + 2) + x + 1] && !u[p] && tm && tm[p]);
                a[p] = v ? 255 : 0;
                any |= v;
            }
        if (any && rf_pockets(a, H, W, (int32_t)(2 * max_i(1, round_i(1.0 * up)) + 1), ncol, cols) < 0) goto done;
    }

    /* the gap close */
    if (ncol > 0 && Hp->gap_close_g > 0) {
        double gg = Hp->gap_close_g * up;
        int64_t r = max_i(1, min_i(gg < 1e9 ? (int64_t)gg : 1000000000, round_i(Hp->gap_close_page / ppg)));
        union255(cols, ncol, H, W, u);
        /* _close: the union zero-padded by r, the maximum then the minimum over 2r + 1, cropped */
        int64_t ph = H + 2 * r, pwid = W + 2 * r;
        e = (uint8_t *)calloc((size_t)ph * (size_t)pwid, 1);
        uint8_t *e2 = (uint8_t *)malloc((size_t)ph * (size_t)pwid);
        if (!e || !e2) { free(e2); goto done; }
        for (int32_t y = 0; y < H; y++) memcpy(e + (size_t)(y + r) * pwid + r, u + (size_t)y * W, (size_t)W);
        int k = (int)(2 * r + 1);
        if (rf_rank_ext(e, (int32_t)ph, (int32_t)pwid, k, 1, e2) || rf_rank_ext(e2, (int32_t)ph, (int32_t)pwid, k, 0, e)) { free(e2); goto done; }
        free(e2);
        for (int32_t y = 0; y < H; y++)
            for (int32_t x = 0; x < W; x++) { size_t p = (size_t)y * W + x; a[p] = (uint8_t)(e[(size_t)(y + r) * pwid + x + r] && !u[p]); }
        free(e); e = NULL;
        sp = (uint8_t *)malloc(3 * (N ? N : 1));
        D = (uint8_t *)malloc((size_t)ncol * (N ? N : 1));
        has = (uint8_t *)calloc((size_t)ncol, 1);
        uint8_t **dp = (uint8_t **)malloc(sizeof(uint8_t *) * (size_t)ncol), **dm = (uint8_t **)malloc(sizeof(uint8_t *) * (size_t)ncol);
        double *KL = (double *)malloc(sizeof(double) * 3 * (size_t)ncol);
        uint8_t *touched = (uint8_t *)calloc((size_t)ncol, 1);
        int bad = !sp || !D || !has || !dp || !dm || !KL || !touched;
        if (!bad) bad = rf_box_blur(rgb, sp, H, W, 3, 1.0f, 1) != 0;
        if (!bad) {
            for (int32_t j = 0; j < ncol; j++) dp[j] = D + (size_t)j * N;
            bad = rf_gap_density((const uint8_t *const *)cols, ncol, H, W, (int32_t)min_span_col, (float)r, dp, has) != 0;
        }
        int64_t n_gap = 0;
        if (!bad) {
            int32_t nd = 0;
            for (int32_t j = 0; j < ncol; j++) {
                if (!has[j]) continue;
                const int32_t *c = M.k[cidx[j]].rgb;
                uint8_t px[3] = {(uint8_t)c[0], (uint8_t)c[1], (uint8_t)c[2]};
                rf_lab_px(lut, pw, px, KL + 3 * nd);
                dp[nd] = D + (size_t)j * N; dm[nd] = cols[j]; nd++;
            }
            if (nd) {
                n_gap = rf_gap_assign((const uint8_t *const *)dp, nd, H, W, a, lum, sp, (int32_t)round_i(Hp->paper_l * 2.55),
                                      (int32_t)round_i(Hp->ink_l * 2.55), KL, dm, touched);
                if (n_gap < 0) bad = 1;
            }
        }
        free(dp); free(dm); free(KL); free(touched); free(sp); free(D); free(has); sp = NULL; D = NULL; has = NULL;
        if (bad) goto done;
        rep[2] = 1.0; rep[3] = (double)n_gap; rep[4] = (double)r;
    }

    /* the painterly share */
    {
        int64_t chroma_px = 0;
        for (int32_t i = 0; i < M.n; i++) {
            if (M.k[i].kind != K_RGB) continue;
            uint8_t px[3] = {(uint8_t)M.k[i].rgb[0], (uint8_t)M.k[i].rgb[1], (uint8_t)M.k[i].rgb[2]};
            double lab[3];
            rf_lab_px(lut, pw, px, lab);
            if (rf_py_hypot(lab[1], lab[2]) >= Hp->chroma_min) chroma_px += count_set(M.k[i].m, N);
        }
        double share = (double)chroma_px / (double)((int64_t)W * H);
        rep[5] = share >= Hp->painterly_chroma_share ? 1.0 : 0.0; rep[6] = share;
        IP.painterly = share >= Hp->painterly_chroma_share;
    }

    /* tonal_ink */
    {
        int32_t ii = mset_kind(&M, K_INK);
        if (ii >= 0) {
            uint8_t ladder[256], *protect = (uint8_t *)malloc(N ? N : 1);
            int32_t *pidx = (int32_t *)malloc(sizeof(int32_t) * (N ? N : 1));
            size_t pcap = N < ((size_t)1 << 24) ? (N ? N : 1) : ((size_t)1 << 24);
            int32_t *pal = (int32_t *)malloc(sizeof(int32_t) * pcap), npal = 0;
            if (!protect || !pidx || !pal) { free(protect); free(pidx); free(pal); goto done; }
            for (int v = 0; v < 256; v++) ladder[v] = (uint8_t)tc_chan(v, step);
            int64_t cnt = rf_tonal_protect(M.k[ii].m, rgb, H, W, Hp->black_l * 2.55, Hp->black_mass_thick_paint, ladder, protect, pidx,
                                           pal, &npal);
            int bad = cnt < 0;
            if (!bad && cnt > 0) {
                int32_t nin = M.n;
                int32_t *slot = (int32_t *)malloc(sizeof(int32_t) * (size_t)(npal > 0 ? npal : 1));
                const uint8_t **ins = (const uint8_t **)malloc(sizeof(uint8_t *) * (size_t)nin);
                bad = !slot || !ins;
                for (int32_t i = 0; !bad && i < npal; i++) {
                    int32_t c[3] = {(pal[i] >> 16) & 255, (pal[i] >> 8) & 255, pal[i] & 255};
                    int32_t ki = mset_rgb(&M, c);
                    if (ki < 0) {
                        uint8_t *m = (uint8_t *)malloc(N ? N : 1);
                        if (!m || (ki = mset_add(&M, K_RGB, c, m)) < 0) bad = 1;
                    }
                    slot[i] = ki;
                }
                uint8_t **outs = bad ? NULL : (uint8_t **)malloc(sizeof(uint8_t *) * (size_t)M.n);
                if (!bad && !outs) bad = 1;
                if (!bad) {
                    for (int32_t i = 0; i < nin; i++) ins[i] = M.k[i].m;
                    for (int32_t i = 0; i < M.n; i++) { outs[i] = (uint8_t *)malloc(N ? N : 1); if (!outs[i]) bad = 1; }
                    if (!bad) {
                        rf_tonal_apply(ins, nin, outs, M.n, protect, pidx, slot, H, W);
                        for (int32_t i = 0; i < M.n; i++) { free(M.k[i].m); M.k[i].m = outs[i]; outs[i] = NULL; }
                    }
                    for (int32_t i = 0; i < M.n; i++) free(outs[i]);
                }
                free(outs); free(slot); free(ins);
            }
            free(protect); free(pidx); free(pal);
            if (bad) goto done;
            rep[7] = (double)cnt; rep[8] = (double)npal;
        }
        if ((ncol = COLS()) < 0) goto done;
    }

    /* coarsen_washes, then the speck absorber at one pixel per cell */
    if (coarsen(&M, H, W, ppg, rep)) goto done;
    if (rep[9] == 1.0) {
        rep[13] = 1.0;
        if (ncol > 0) {
            int32_t *own = (int32_t *)malloc(sizeof(int32_t) * (N ? N : 1)), *lab_img = (int32_t *)malloc(sizeof(int32_t) * (N ? N : 1));
            int32_t *out_lab = (int32_t *)malloc(sizeof(int32_t) * (N ? N : 1));
            uint8_t *weak = (uint8_t *)malloc(N ? N : 1);
            double *lab_all = NULL;
            int64_t stats[2] = {0, 0};
            int bad = !own || !lab_img || !out_lab || !weak;
            int64_t n_weak = bad ? -1 : rf_absorb_prepare_masks((const uint8_t *const *)cols, ncol, H, W, (int32_t)min_span_col,
                                                                (int64_t)Hp->absorb_max_area + 1, own, lab_img, weak);
            if (n_weak < 0) bad = 1;
            int anyl = 0;
            for (size_t p = 0; !bad && p < N && !anyl; p++) anyl = lab_img[p] >= 0;
            if (!bad && n_weak && anyl) {
                lab_all = (double *)malloc(sizeof(double) * 3 * (N ? N : 1));
                if (!lab_all) bad = 1;
                else {
                    rf_lab_rows(rgb, (int64_t)N, lab_all);
                    if (rf_absorb_run(own, lab_img, weak, lab_all, ncol, H, W, (int64_t)Hp->absorb_max_area, Hp->absorb_max_de,
                                      pw(Hp->absorb_max_de, 2.0), out_lab, stats) < 0) bad = 1;
                }
                if (!bad) {
                    uint8_t **outs = (uint8_t **)calloc((size_t)ncol, sizeof(uint8_t *));
                    if (!outs) bad = 1;
                    for (int32_t j = 0; !bad && j < ncol; j++) if (!(outs[j] = (uint8_t *)malloc(N ? N : 1))) bad = 1;
                    if (!bad) {
                        rf_split_labels(out_lab, ncol, H, W, outs);
                        for (int32_t j = 0; j < ncol; j++) { free(M.k[cidx[j]].m); M.k[cidx[j]].m = outs[j]; outs[j] = NULL; }
                    }
                    if (outs) for (int32_t j = 0; j < ncol; j++) free(outs[j]);
                    free(outs);
                }
                if (!bad) { rep[13] = 2.0; rep[14] = (double)n_weak / (double)((int64_t)W * H); rep[15] = (double)stats[0]; rep[16] = (double)stats[1]; }
            }
            free(own); free(lab_img); free(out_lab); free(weak); free(lab_all);
            if (bad) goto done;
            if ((ncol = COLS()) < 0) goto done;
        }
    }

    /* the gray halo */
    {
        int32_t ib = mset_kind(&M, K_BLACK);
        if (Hp->gray_halo_open > 0 && ib >= 0) {
            int32_t k = (int32_t)(2 * max_i(1, round_i(Hp->gray_halo_open * up)) + 1);
            if (rf_rank_ext(M.k[ib].m, H, W, k, 1, u)) goto done;
            uint8_t **gm = (uint8_t **)malloc(sizeof(uint8_t *) * (size_t)(M.n + 1)), **keeps = (uint8_t **)calloc((size_t)(M.n + 1), sizeof(uint8_t *));
            int32_t *gi = (int32_t *)malloc(sizeof(int32_t) * (size_t)(M.n + 1)), ng = 0;
            int bad = !gm || !keeps || !gi;
            for (int32_t i = 0; !bad && i < M.n; i++) {
                if (M.k[i].kind != K_RGB) continue;
                uint8_t px[3] = {(uint8_t)M.k[i].rgb[0], (uint8_t)M.k[i].rgb[1], (uint8_t)M.k[i].rgb[2]};
                double lab[3];
                rf_lab_px(lut, pw, px, lab);
                if (rf_py_hypot(lab[1], lab[2]) >= Hp->chroma_min || lab[0] <= Hp->tc_ink_l) continue;
                gm[ng] = M.k[i].m; gi[ng] = i;
                if (!(keeps[ng] = (uint8_t *)malloc(N ? N : 1))) bad = 1;
                ng++;
            }
            int64_t n_halo = 0;
            if (!bad && ng) {
                n_halo = rf_gray_halo((const uint8_t *const *)gm, ng, H, W, u, Hp->gray_halo_share, keeps);
                if (n_halo < 0) bad = 1;
                for (int32_t j = 0; !bad && j < ng; j++) {
                    for (size_t p = 0; p < N; p++) keeps[j][p] = keeps[j][p] ? 255 : 0;
                    free(M.k[gi[j]].m); M.k[gi[j]].m = keeps[j]; keeps[j] = NULL;
                }
            }
            if (keeps) for (int32_t j = 0; j < ng; j++) free(keeps[j]);
            free(gm); free(keeps); free(gi);
            if (bad) goto done;
            rep[17] = 1.0; rep[18] = (double)n_halo;
            if ((ncol = COLS()) < 0) goto done;
        }
    }

    /* the zones: one wash fill per color key, as one batch */
    rep[19] = rf_now() - t_start;
    rf_prog_at(0.5);
    double t_zones = rf_now();
    int32_t zbase = rf_store_count(S), ztotal = 0;
    if (ncol > 0) {
        zj = (rf_fill_job *)malloc(sizeof(rf_fill_job) * (size_t)ncol);
        zmade = (int32_t *)calloc((size_t)ncol, sizeof(int32_t));
        if (!zj || !zmade) goto done;
        for (int32_t j = 0; j < ncol; j++) {
            const int32_t *c = M.k[cidx[j]].rgb;
            int32_t st = rf_store_style_rgb(S, P->tool_hl, P->color_hl, c[0], c[1], c[2], 1);
            if (st < 0) goto done;
            rf_fill_job job = {cols[j], H, W, 0, 0, 1, P->hl_width_max, st, -1, -1};
            zj[j] = job;
        }
        ztotal = rf_store_fill_batch(S, zj, ncol, ppg, P->x0, P->y0, P->x1, P->y1, W, H, P->hl_scale, P->pen_scale, P->fineliner_max, zmade);
        if (ztotal < 0) goto done;
    }

    /* the ink section and the contour pass */
    rep[20] = rf_now() - t_zones;
    rf_prog_at(0.85);
    double t_ink = rf_now();
    {
        int32_t ib = mset_kind(&M, K_BLACK), it2 = mset_kind(&M, K_TONE), ii = mset_kind(&M, K_INK), ni = 0;
        if (ii < 0) { rc = -2; goto done; }                 /* quantize always makes _ink: anything else is not the painter's */
        int32_t r = rf_ink_pass(S, &IP, H, W, ib >= 0 ? M.k[ib].m : NULL, it2 >= 0 ? M.k[it2].m : NULL, M.k[ii].m,
                                (const uint8_t *const *)cols, ncol, rgb, lum, ridge, &iorder, &ni, rep + 32);
        if (r != 0) { rc = r; goto done; }
        rep[21] = rf_now() - t_ink;
        int64_t total = (int64_t)ztotal + ni;
        int32_t *order = (int32_t *)malloc(sizeof(int32_t) * (size_t)(total > 0 ? total : 1));
        korder = (int32_t *)malloc(sizeof(int32_t) * 4 * (size_t)(M.n > 0 ? M.n : 1));
        if (!order || !korder) { free(order); goto done; }
        for (int32_t s = 0; s < ztotal; s++) order[s] = zbase + s;
        if (ni) memcpy(order + ztotal, iorder, sizeof(int32_t) * (size_t)ni);
        for (int32_t i = 0; i < M.n; i++) {
            korder[4 * i] = M.k[i].kind;
            korder[4 * i + 1] = M.k[i].rgb[0]; korder[4 * i + 2] = M.k[i].rgb[1]; korder[4 * i + 3] = M.k[i].rgb[2];
        }
        *order_out = order; *norder = (int32_t)total;
        *keys_out = korder; *nkeys_out = M.n; korder = NULL;
        rc = 0;
    }
#undef COLS

done:
    rf_free(pinfo); rf_free(pxy); rf_free(iorder);
    free(cols); free(cidx); free(u); free(a); free(b); free(e); free(sp); free(D); free(has); free(zj); free(zmade); free(korder);
    mset_free(&M);
    return rc;
}
