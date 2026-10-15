/* The ring planner -- rmb_geometry.plan and fill, step for step, with the library algorithms the Python leans on
 * reproduced exactly:
 *   the precise Euclidean distance transform (OpenCV distransform.cpp trueDistTrans, float32),
 *   marching squares with the 'high' connectivity and its contour assembly (scikit-image _find_contours),
 *   the Douglas-Peucker simplifier for float points (OpenCV approx.cpp approxPolyDP_<float>),
 *   the contour area (OpenCV shapedescr.cpp contourArea),
 * and the Python's own arithmetic where it is float32 (the simplified loops, the corner rounding, the placement
 * onto the page) and double where it is double (the depth and width schedule, the distance field's level).
 * The diamond test is rmb_geometry's GEOS-free one (diamond_of / diamond_octagon / octagon_covers). GEOMETRY code.
 * Every allocation is checked: a failure raises this thread's oom flag (plan_oom; the EDT's helper threads report
 * through their job), the work in progress stops without touching the missing memory, and rf_plan returns -1 with
 * nothing left allocated. */
#include <float.h>
#include <math.h>
#include <stdatomic.h>
#include <stdlib.h>
#include <string.h>
#include "rmfast.h"
#include "internal.h"

/* ------------------------------------------------------------------ phase timers (a benchmark reads them) */
#define now_s rf_now
/* per thread: plans run side by side on the batch's threads (store.c rf_store_fill_batch); a benchmark reads the
 * calling thread's */
static _Thread_local double T_[8];      /* 0 setup+EDT, 1 segments, 2 assembly, 3 per-contour work, 4 calls, 5 levels */
static _Thread_local int plan_oom;       /* an allocation failed in the plan running on this thread */
RF_API void rf_plan_timers(double *out, int reset) { for (int i = 0; i < 8; i++) { out[i] = T_[i]; if (reset) T_[i] = 0.0; } }

/* ------------------------------------------------------------------ OpenCV's precise distance transform */
#define PRECISE_DIST_MAX (1 << 16)

/* The column stage for columns [c0, c1): dptr = (float)sqr_tab[dist], dist the vertical distance to the nearest
 * zero. Every column on its own, as OpenCV does it, but the columns of the range advanced together row by row (the
 * arithmetic is integer and per column, so neither their order nor their split changes anything); the downward
 * distances are kept in dst's own memory, each read just before its float result is written there. */
static void edt_cols(const uint8_t *src, float *dst, int32_t m, int32_t n, int32_t c0, int32_t c1, const unsigned int *sqr_tab, int32_t *dist) {
    int32_t *D = (int32_t *)dst;
    for (int32_t i = c0; i < c1; i++) dist[i - c0] = m - 1;
    for (int32_t j = m - 1; j >= 0; j--) {
        const uint8_t *S = src + (size_t)j * n;
        int32_t *Dj = D + (size_t)j * n;
        for (int32_t i = c0; i < c1; i++) { int32_t d = (dist[i - c0] + 1) & (S[i] == 0 ? 0 : -1); dist[i - c0] = d; Dj[i] = d; }
    }
    for (int32_t i = c0; i < c1; i++) dist[i - c0] = m - 1;
    for (int32_t j = 0; j < m; j++) {
        int32_t *Dj = D + (size_t)j * n;
        float *Fj = dst + (size_t)j * n;
        for (int32_t i = c0; i < c1; i++) {
            int32_t x = dist[i - c0] - Dj[i];              /* sat_tab[x]: 0 when x < -1, else x + 1 */
            int32_t sat = (x < -1) ? 0 : x + 1;
            int32_t dd = dist[i - c0] + 1 - sat;
            dist[i - c0] = dd;
            Fj[i] = (float)sqr_tab[dd];
        }
    }
}

/* The row stage for rows [r0, r1): the lower envelope of parabolas, in float, exactly as DTRowInvoker. Rows are
 * independent. f, z, v: n + 2 slots of scratch. */
static void edt_rows(float *dst, int32_t n, int32_t r0, int32_t r1, const unsigned int *sqr_tab, const float *inv_tab, float *f, float *z, int32_t *v) {
    const float inf = 1e15f;
    for (int32_t i = r0; i < r1; i++) {
        float *row = dst + (size_t)i * n;
        int32_t p, q, k;
        {   /* a row of zeros (no foreground pixel above or below in any column) is its own nearest zero everywhere:
               the envelope keeps every parabola and each pixel reads its own, 0 */
            int32_t t = 0;
            while (t < n && row[t] == 0.0f) t++;
            if (t == n) continue;
        }
        v[0] = 0; z[0] = -inf; z[1] = inf; f[0] = row[0];
        int32_t lim = n < PRECISE_DIST_MAX ? n : PRECISE_DIST_MAX;
        for (q = 1, k = 0; q < lim; q++) {
            float fq = row[q];
            f[q] = fq;
            for (;; k--) {
                p = v[k];
                float s = (fq - row[p] + (float)(sqr_tab[q] - sqr_tab[p])) * inv_tab[q - p];
                if (s > z[k]) { k++; v[k] = q; z[k] = s; z[k + 1] = inf; break; }
            }
        }
        for (; q < n; q++) {
            float fq = row[q];
            f[q] = fq;
            for (;; k--) {
                p = v[k];
                float s = (fq - row[p] + (float)(q + p) * (float)(q - p)) * inv_tab[q - p];
                if (s > z[k]) { k++; v[k] = q; z[k] = s; z[k + 1] = inf; break; }
            }
        }
        for (q = 0, k = 0; q < n; q++) {
            while (z[k + 1] < q) k++;
            p = v[k];
            row[q] = sqrtf((float)sqr_tab[abs(q - p)] + f[p]);
        }
    }
}

/* big transforms on all threads: column chunks, then row chunks, each a disjoint part of dst */
typedef struct { const uint8_t *src; float *dst; int32_t m, n; const unsigned int *sqr_tab; const float *inv_tab; atomic_int next; int rows; atomic_int oom; } edtjob;
#define EDT_COLS 256
#define EDT_ROWS 16

static void edt_worker(void *arg, int tid) {
    edtjob *J = (edtjob *)arg;
    if (!J->rows) {
        int32_t *dist = (int32_t *)malloc(sizeof(int32_t) * EDT_COLS);
        if (!dist) { atomic_store(&J->oom, 1); return; }
        for (;;) {
            int32_t c0 = atomic_fetch_add(&J->next, EDT_COLS);
            if (c0 >= J->n) break;
            edt_cols(J->src, J->dst, J->m, J->n, c0, c0 + EDT_COLS < J->n ? c0 + EDT_COLS : J->n, J->sqr_tab, dist);
        }
        free(dist);
    } else {
        float *f = (float *)malloc(sizeof(float) * (J->n + 2)), *z = (float *)malloc(sizeof(float) * (J->n + 2));
        int32_t *v = (int32_t *)malloc(sizeof(int32_t) * (J->n + 2));
        if (!f || !z || !v) { atomic_store(&J->oom, 1); free(f); free(z); free(v); return; }
        for (;;) {
            int32_t r0 = atomic_fetch_add(&J->next, EDT_ROWS);
            if (r0 >= J->m) break;
            edt_rows(J->dst, J->n, r0, r0 + EDT_ROWS < J->m ? r0 + EDT_ROWS : J->m, J->sqr_tab, J->inv_tab, f, z, v);
        }
        free(f); free(z); free(v);
    }
}

/* -> 0, or -1 when memory ran out */
int rf_edt_precise(const uint8_t *src, int32_t m, int32_t n, float *dst) {
    const unsigned int inf_u = 0xFFFFFFFFu;
    unsigned int *sqr_tab = (unsigned int *)malloc(sizeof(unsigned int) * (size_t)(2 * m > n ? 2 * m : n));
    float *inv_tab = (float *)malloc(sizeof(float) * (n > 1 ? n : 1));
    if (!sqr_tab || !inv_tab) { free(sqr_tab); free(inv_tab); return -1; }
    for (int32_t i = 0; i < m; i++) sqr_tab[i] = i >= PRECISE_DIST_MAX ? inf_u : (unsigned int)i * (unsigned int)i;
    for (int32_t i = m; i < 2 * m; i++) sqr_tab[i] = inf_u;
    int nt = (size_t)m * n >= ((size_t)1 << 20) ? rf_threads() : 1;
    edtjob J; J.src = src; J.dst = dst; J.m = m; J.n = n; J.sqr_tab = sqr_tab; J.inv_tab = NULL; J.rows = 0;
    atomic_init(&J.next, 0);
    atomic_init(&J.oom, 0);
    if (nt > 1) rf_parallel(nt, edt_worker, &J);
    else {
        int32_t *dist = (int32_t *)malloc(sizeof(int32_t) * (n > 0 ? n : 1));
        if (!dist) atomic_store(&J.oom, 1);
        else { edt_cols(src, dst, m, n, 0, n, sqr_tab, dist); free(dist); }
    }
    if (atomic_load(&J.oom)) { free(inv_tab); free(sqr_tab); return -1; }
    /* the row stage's tables */
    inv_tab[0] = 0.f;
    sqr_tab[0] = 0;
    for (int32_t i = 1; i < n; i++) {
        inv_tab[i] = (float)(0.5 / i);
        sqr_tab[i] = i >= PRECISE_DIST_MAX ? inf_u : (unsigned int)i * (unsigned int)i;
    }
    J.inv_tab = inv_tab; J.rows = 1;
    atomic_init(&J.next, 0);
    if (nt > 1) rf_parallel(nt, edt_worker, &J);
    else {
        float *f = (float *)malloc(sizeof(float) * (n + 2)), *z = (float *)malloc(sizeof(float) * (n + 2));
        int32_t *v = (int32_t *)malloc(sizeof(int32_t) * (n + 2));
        if (!f || !z || !v) atomic_store(&J.oom, 1);
        else edt_rows(dst, n, 0, m, sqr_tab, inv_tab, f, z, v);
        free(f); free(z); free(v);
    }
    free(inv_tab); free(sqr_tab);
    return atomic_load(&J.oom) ? -1 : 0;
}

/* ------------------------------------------------------------------ scikit-image marching squares */
typedef struct pnode { double r, c; struct pnode *prev, *next; } pnode;
typedef struct { pnode *head, *tail; int64_t num; int alive; } cont_t;
typedef struct { double r, c; cont_t *ct; int state; } hcell;      /* state: 0 empty, 1 used, 2 deleted */
typedef struct { hcell *cells; size_t cap; } pmap;

static inline double zfix(double v) { return v == 0.0 ? 0.0 : v; }   /* -0.0 and 0.0 are one key, as in Python */

static uint64_t phash(double r, double c) {
    uint64_t a, b; r = zfix(r); c = zfix(c);
    memcpy(&a, &r, 8); memcpy(&b, &c, 8);
    uint64_t x = a * 0x9E3779B97F4A7C15ULL ^ (b + 0x7F4A7C15ULL);
    x ^= x >> 29; x *= 0xBF58476D1CE4E5B9ULL; x ^= x >> 32;
    return x;
}

static int pmap_init(pmap *M, size_t n) {
    size_t cap = 64;
    while (cap < 2 * n + 8) cap <<= 1;
    M->cap = cap;
    M->cells = (hcell *)calloc(cap, sizeof(hcell));
    return M->cells ? 0 : -1;
}

static hcell *pmap_find(pmap *M, double r, double c) {
    uint64_t h = phash(r, c) & (M->cap - 1);
    for (;;) {
        hcell *e = &M->cells[h];
        if (e->state == 0) return NULL;
        if (e->state == 1 && zfix(e->r) == zfix(r) && zfix(e->c) == zfix(c)) return e;
        h = (h + 1) & (M->cap - 1);
    }
}

static void pmap_set(pmap *M, double r, double c, cont_t *ct) {
    uint64_t h = phash(r, c) & (M->cap - 1);
    hcell *tomb = NULL;
    for (;;) {
        hcell *e = &M->cells[h];
        if (e->state == 0) { if (tomb) e = tomb; e->r = r; e->c = c; e->ct = ct; e->state = 1; return; }
        if (e->state == 2) { if (!tomb) tomb = e; }
        else if (zfix(e->r) == zfix(r) && zfix(e->c) == zfix(c)) { e->ct = ct; return; }
        h = (h + 1) & (M->cap - 1);
    }
}

static cont_t *pmap_pop(pmap *M, double r, double c) {
    hcell *e = pmap_find(M, r, c);
    if (!e) return NULL;
    cont_t *ct = e->ct;
    e->state = 2;
    return ct;
}

/* contour nodes come from a pool released in one go when the level's contours are copied out */
typedef struct pblock { struct pblock *next; int32_t used; pnode nodes[4096]; } pblock;
typedef struct { pblock *head; } ppool;
/* NULL when memory ran out */
static pnode *mkp(ppool *P, double r, double c) {
    if (!P->head || P->head->used == 4096) {
        pblock *b = (pblock *)malloc(sizeof(pblock));
        if (!b) return NULL;
        b->next = P->head; b->used = 0; P->head = b;
    }
    pnode *p = &P->head->nodes[P->head->used++];
    p->r = r; p->c = c; p->prev = p->next = NULL;
    return p;
}
static void ppool_free(ppool *P) { while (P->head) { pblock *n = P->head->next; free(P->head); P->head = n; } }

/* the segments of one level, in raster order (the Cython _get_contour_segments) */
typedef struct { double fr, fc, tr, tc; } seg;

static inline double frac(double from, double to, double level) {
    if (to == from) return 0.0;
    return (level - from) / (to - from);
}

static seg *segments_of(const double *a, int32_t m, int32_t n, double level, int32_t *count) {
    size_t cap = 1024, k = 0;
    seg *S = (seg *)malloc(sizeof(seg) * cap);
    *count = 0;
    if (!S) { plan_oom = 1; return NULL; }
#define ADD(FR, FC, TR, TC) do { if (k == cap) { seg *S2_ = (seg *)realloc(S, sizeof(seg) * cap * 2); if (S2_) { S = S2_; cap *= 2; } else plan_oom = 1; } if (k < cap) { S[k].fr = (FR); S[k].fc = (FC); S[k].tr = (TR); S[k].tc = (TC); k++; } } while (0)
    for (int32_t r0 = 0; r0 < m - 1; r0++) {
        const double *row0 = a + (size_t)r0 * n, *row1 = row0 + n;
        for (int32_t c0 = 0; c0 < n - 1; c0++) {
            double ul = row0[c0], ur = row0[c0 + 1], ll = row1[c0], lr = row1[c0 + 1];
            int sq = 0;
            if (ul > level) sq += 1;
            if (ur > level) sq += 2;
            if (ll > level) sq += 4;
            if (lr > level) sq += 8;
            if (sq == 0 || sq == 15) continue;
            double r1 = r0 + 1, c1 = c0 + 1;
            double top_r = r0, top_c = c0 + frac(ul, ur, level);
            double bot_r = r1, bot_c = c0 + frac(ll, lr, level);
            double lef_r = r0 + frac(ul, ll, level), lef_c = c0;
            double rig_r = r0 + frac(ur, lr, level), rig_c = c1;
            switch (sq) {
            case 1: ADD(top_r, top_c, lef_r, lef_c); break;
            case 2: ADD(rig_r, rig_c, top_r, top_c); break;
            case 3: ADD(rig_r, rig_c, lef_r, lef_c); break;
            case 4: ADD(lef_r, lef_c, bot_r, bot_c); break;
            case 5: ADD(top_r, top_c, bot_r, bot_c); break;
            case 6: ADD(lef_r, lef_c, top_r, top_c); ADD(rig_r, rig_c, bot_r, bot_c); break;        /* vertex_connect_high */
            case 7: ADD(rig_r, rig_c, bot_r, bot_c); break;
            case 8: ADD(bot_r, bot_c, rig_r, rig_c); break;
            case 9: ADD(top_r, top_c, rig_r, rig_c); ADD(bot_r, bot_c, lef_r, lef_c); break;        /* vertex_connect_high */
            case 10: ADD(bot_r, bot_c, top_r, top_c); break;
            case 11: ADD(bot_r, bot_c, lef_r, lef_c); break;
            case 12: ADD(lef_r, lef_c, rig_r, rig_c); break;
            case 13: ADD(top_r, top_c, rig_r, rig_c); break;
            case 14: ADD(lef_r, lef_c, top_r, top_c); break;
            }
        }
    }
#undef ADD
    *count = (int32_t)k;
    return S;
}

/* The same segments in the same order, visiting only the squares that touch a pixel above the level: a square whose
 * four corners are all at or below it yields nothing. `alive` lists those pixels (flat indices, ascending); `rowp`
 * (m + 1 entries) is scratch. */
static seg *segments_alive(const double *a, int32_t m, int32_t n, double level, const int32_t *alive, int32_t nalive, int32_t *rowp, int32_t *count) {
    size_t cap = 1024, k = 0;
    seg *S = (seg *)malloc(sizeof(seg) * cap);
    *count = 0;
    if (!S) { plan_oom = 1; return NULL; }
    if (!nalive || m < 2 || n < 2) return S;
    for (int32_t y = 0; y <= m; y++) rowp[y] = 0;
    for (int32_t t = 0; t < nalive; t++) rowp[alive[t] / n + 1]++;
    for (int32_t y = 0; y < m; y++) rowp[y + 1] += rowp[y];
    int32_t ylo = alive[0] / n - 1, yhi = alive[nalive - 1] / n;
    if (ylo < 0) ylo = 0;
    if (yhi > m - 2) yhi = m - 2;
#define ADD(FR, FC, TR, TC) do { if (k == cap) { seg *S2_ = (seg *)realloc(S, sizeof(seg) * cap * 2); if (S2_) { S = S2_; cap *= 2; } else plan_oom = 1; } if (k < cap) { S[k].fr = (FR); S[k].fc = (FC); S[k].tr = (TR); S[k].tc = (TC); k++; } } while (0)
    for (int32_t r0 = ylo; r0 <= yhi; r0++) {
        const int32_t *A = alive + rowp[r0], *B = alive + rowp[r0 + 1];
        int32_t na = rowp[r0 + 1] - rowp[r0], nb = rowp[r0 + 2] - rowp[r0 + 1];
        if (!na && !nb) continue;
        int32_t ia = 0, ib = 0, last = -1;
        int32_t ra = r0 * n, rb = (r0 + 1) * n;
        const double *row0 = a + (size_t)r0 * n, *row1 = row0 + n;
        while (ia < na || ib < nb) {
            int32_t c;
            if (ib >= nb || (ia < na && A[ia] - ra <= B[ib] - rb)) c = A[ia++] - ra;
            else c = B[ib++] - rb;
            for (int32_t c0 = c - 1; c0 <= c; c0++) {
                if (c0 <= last || c0 < 0 || c0 > n - 2) continue;
                last = c0;
                double ul = row0[c0], ur = row0[c0 + 1], ll = row1[c0], lr = row1[c0 + 1];
                int sq = 0;
                if (ul > level) sq += 1;
                if (ur > level) sq += 2;
                if (ll > level) sq += 4;
                if (lr > level) sq += 8;
                if (sq == 0 || sq == 15) continue;
                double r1 = r0 + 1, c1 = c0 + 1;
                double top_r = r0, top_c = c0 + frac(ul, ur, level);
                double bot_r = r1, bot_c = c0 + frac(ll, lr, level);
                double lef_r = r0 + frac(ul, ll, level), lef_c = c0;
                double rig_r = r0 + frac(ur, lr, level), rig_c = c1;
                switch (sq) {
                case 1: ADD(top_r, top_c, lef_r, lef_c); break;
                case 2: ADD(rig_r, rig_c, top_r, top_c); break;
                case 3: ADD(rig_r, rig_c, lef_r, lef_c); break;
                case 4: ADD(lef_r, lef_c, bot_r, bot_c); break;
                case 5: ADD(top_r, top_c, bot_r, bot_c); break;
                case 6: ADD(lef_r, lef_c, top_r, top_c); ADD(rig_r, rig_c, bot_r, bot_c); break;
                case 7: ADD(rig_r, rig_c, bot_r, bot_c); break;
                case 8: ADD(bot_r, bot_c, rig_r, rig_c); break;
                case 9: ADD(top_r, top_c, rig_r, rig_c); ADD(bot_r, bot_c, lef_r, lef_c); break;
                case 10: ADD(bot_r, bot_c, top_r, top_c); break;
                case 11: ADD(bot_r, bot_c, lef_r, lef_c); break;
                case 12: ADD(lef_r, lef_c, rig_r, rig_c); break;
                case 13: ADD(top_r, top_c, rig_r, rig_c); break;
                case 14: ADD(lef_r, lef_c, top_r, top_c); break;
                }
            }
        }
    }
#undef ADD
    *count = (int32_t)k;
    return S;
}

typedef struct { double *rc; int32_t n; } rf_contour;

/* _assemble_contours: the deque-and-dict join, order of creation kept. NULL (and plan_oom) when memory ran out. */
static rf_contour *assemble(const seg *S, int32_t ns, int32_t *n_out) {
    pmap starts = {NULL, 0}, ends = {NULL, 0};
    ppool pool = {NULL};
    rf_contour *out = NULL;
    int32_t k = 0;
    int64_t ncont = 0;
    *n_out = 0;
    cont_t **all = (cont_t **)malloc(sizeof(cont_t *) * (ns ? ns : 1));
    if (!all || pmap_init(&starts, (size_t)ns) || pmap_init(&ends, (size_t)ns)) goto fail;
    for (int32_t s = 0; s < ns; s++) {
        double fr = S[s].fr, fc = S[s].fc, tr = S[s].tr, tc = S[s].tc;
        if (zfix(fr) == zfix(tr) && zfix(fc) == zfix(tc)) continue;
        cont_t *tail = pmap_pop(&starts, tr, tc);
        cont_t *head = pmap_pop(&ends, fr, fc);
        if (tail && head) {
            if (tail == head) {
                pnode *p = mkp(&pool, tr, tc);
                if (!p) goto fail;
                p->prev = head->tail; head->tail->next = p; head->tail = p;
            } else if (tail->num > head->num) {
                head->tail->next = tail->head; tail->head->prev = head->tail; head->tail = tail->tail;
                tail->alive = 0; tail->head = tail->tail = NULL;      /* its nodes now belong to head */
                pmap_set(&starts, head->head->r, head->head->c, head);
                pmap_set(&ends, head->tail->r, head->tail->c, head);
            } else {
                pmap_pop(&starts, head->head->r, head->head->c);
                head->tail->next = tail->head; tail->head->prev = head->tail; tail->head = head->head;
                head->alive = 0; head->head = head->tail = NULL;      /* its nodes now belong to tail */
                pmap_set(&starts, tail->head->r, tail->head->c, tail);
                pmap_set(&ends, tail->tail->r, tail->tail->c, tail);
            }
        } else if (!tail && !head) {
            cont_t *ct = (cont_t *)malloc(sizeof(cont_t));
            if (!ct) goto fail;
            ct->head = mkp(&pool, fr, fc); ct->tail = mkp(&pool, tr, tc);
            if (!ct->head || !ct->tail) { free(ct); goto fail; }
            ct->head->next = ct->tail; ct->tail->prev = ct->head;
            ct->num = ncont; ct->alive = 1;
            all[ncont++] = ct;
            pmap_set(&starts, fr, fc, ct);
            pmap_set(&ends, tr, tc, ct);
        } else if (!head) {
            pnode *p = mkp(&pool, fr, fc);
            if (!p) goto fail;
            p->next = tail->head; tail->head->prev = p; tail->head = p;
            pmap_set(&starts, fr, fc, tail);
        } else {
            pnode *p = mkp(&pool, tr, tc);
            if (!p) goto fail;
            p->prev = head->tail; head->tail->next = p; head->tail = p;
            pmap_set(&ends, tr, tc, head);
        }
    }
    int32_t live = 0;
    for (int64_t i = 0; i < ncont; i++) live += all[i]->alive;
    out = (rf_contour *)calloc((size_t)(live ? live : 1), sizeof(rf_contour));
    if (!out) goto fail;
    for (int64_t i = 0; i < ncont; i++) {
        cont_t *ct = all[i];
        if (ct->alive) {
            int32_t cnt = 0;
            for (pnode *p = ct->head; p; p = p->next) cnt++;
            out[k].rc = (double *)malloc(sizeof(double) * 2 * (size_t)cnt); out[k].n = cnt;
            if (!out[k].rc) goto fail;
            int32_t t = 0;
            for (pnode *p = ct->head; p; p = p->next) { out[k].rc[2 * t] = p->r; out[k].rc[2 * t + 1] = p->c; t++; }
            k++;
        }
    }
    for (int64_t i = 0; i < ncont; i++) free(all[i]);
    ppool_free(&pool);
    free(all); free(starts.cells); free(ends.cells);
    *n_out = live;
    return out;
fail:
    plan_oom = 1;
    if (out) for (int32_t t = 0; t < k; t++) free(out[t].rc);
    free(out);
    if (all) for (int64_t i = 0; i < ncont; i++) free(all[i]);
    ppool_free(&pool);
    free(all); free(starts.cells); free(ends.cells);
    *n_out = 0;
    return NULL;
}

static rf_contour *assemble(const seg *S, int32_t ns, int32_t *n_out);

static rf_contour *find_contours_alive(const double *a, int32_t m, int32_t n, double level, const int32_t *alive, int32_t nalive, int32_t *rowp, int32_t *n_out) {
    int32_t ns;
    double t0 = now_s();
    seg *S = segments_alive(a, m, n, level, alive, nalive, rowp, &ns);
    double t1 = now_s();
    *n_out = 0;
    if (!S || plan_oom) { free(S); plan_oom = 1; return NULL; }
    rf_contour *out = assemble(S, ns, n_out);
    T_[1] += t1 - t0; T_[2] += now_s() - t1; T_[5] += 1;
    free(S);
    return out;
}

static rf_contour *find_contours(const double *a, int32_t m, int32_t n, double level, int32_t *n_out) {
    int32_t ns;
    double t0 = now_s();
    seg *S = segments_of(a, m, n, level, &ns);
    double t1 = now_s();
    *n_out = 0;
    if (!S || plan_oom) { free(S); plan_oom = 1; return NULL; }
    rf_contour *out = assemble(S, ns, n_out);
    T_[1] += t1 - t0; T_[2] += now_s() - t1; T_[5] += 1;
    free(S);
    return out;
}

/* ------------------------------------------------------------------ OpenCV approxPolyDP, float points, closed */
typedef struct { int start, end; } rrange;

static int approx_poly_dp_f(const float *src, int count0, float *dst, int is_closed0, double eps) {
    int init_iters = 3;
    rrange slice = {0, 0}, right_slice = {0, 0};
    float sx = -1000000.f, sy = -1000000.f, ex = 0.f, ey = 0.f, px = 0.f, py = 0.f;
    int i = 0, j, pos = 0, wpos, count = count0, new_count = 0;
    int is_closed = is_closed0;
    int le_eps = 0;
    size_t top = 0, stacksz = (size_t)(count0 > 0 ? count0 : 1);
    rrange *stack = (rrange *)malloc(sizeof(rrange) * stacksz);
    if (!stack) { plan_oom = 1; return 0; }
    if (count == 0) { free(stack); return 0; }
    eps *= eps;
#define PUSH(S) do { if (top >= stacksz) { size_t sz2_ = stacksz * 3 / 2 + 1; rrange *st2_ = (rrange *)realloc(stack, sizeof(rrange) * sz2_); if (st2_) { stack = st2_; stacksz = sz2_; } else plan_oom = 1; } if (top < stacksz) stack[top++] = (S); } while (0)
#define READ_PT(X, Y, POS) do { X = src[2 * (POS)]; Y = src[2 * (POS) + 1]; if (++(POS) >= count) (POS) = 0; } while (0)
#define READ_DST(X, Y, POS) do { X = dst[2 * (POS)]; Y = dst[2 * (POS) + 1]; if (++(POS) >= count) (POS) = 0; } while (0)
#define WRITE_PT(X, Y) do { dst[2 * new_count] = (X); dst[2 * new_count + 1] = (Y); new_count++; } while (0)
    if (!is_closed) {
        right_slice.start = count;
        ex = src[0]; ey = src[1];
        sx = src[2 * (count - 1)]; sy = src[2 * (count - 1) + 1];
        if (sx != ex || sy != ey) { slice.start = 0; slice.end = count - 1; PUSH(slice); }
        else { is_closed = 1; init_iters = 1; }
    }
    if (is_closed) {
        right_slice.start = 0;
        for (i = 0; i < init_iters; i++) {
            double dist, max_dist = 0;
            pos = (pos + right_slice.start) % count;
            READ_PT(sx, sy, pos);
            for (j = 1; j < count; j++) {
                double dx, dy;
                READ_PT(px, py, pos);
                dx = (double)(px - sx);                    /* float subtraction, then double */
                dy = (double)(py - sy);
                dist = dx * dx + dy * dy;
                if (dist > max_dist) { max_dist = dist; right_slice.start = j; }
            }
            le_eps = max_dist <= eps;
        }
        if (!le_eps) {
            right_slice.end = slice.start = pos % count;
            slice.end = right_slice.start = (right_slice.start + slice.start) % count;
            PUSH(right_slice);
            PUSH(slice);
        } else {
            WRITE_PT(sx, sy);
        }
    }
    while (top > 0) {
        slice = stack[--top];
        ex = src[2 * slice.end]; ey = src[2 * slice.end + 1];
        pos = slice.start;
        READ_PT(sx, sy, pos);
        if (pos != slice.end) {
            /* OpenCV 5.0.0 (modules/geometry/src/approx.cpp): the distance to the SEGMENT, clamped to its end
               points, not to the infinite line as in 4.x.  Float differences, double products, as the template
               instantiates for Point2f. */
            double dx, dy, max_d2l2 = 0;
            dx = (double)(ex - sx);
            dy = (double)(ey - sy);
            double seg2 = dx * dx + dy * dy;
            while (pos != slice.end) {
                READ_PT(px, py, pos);
                double proj = (double)(px - sx) * dx + (double)(py - sy) * dy;
                double d2l2;
                if (proj < 0) {
                    float q = (px - sx) * (px - sx) + (py - sy) * (py - sy);      /* float products and sum */
                    d2l2 = (double)q * seg2;
                } else if (proj > seg2) {
                    float q = (px - ex) * (px - ex) + (py - ey) * (py - ey);
                    d2l2 = (double)q * seg2;
                } else {
                    double dist = (double)(py - sy) * dx - (double)(px - sx) * dy;
                    d2l2 = dist * dist;
                }
                if (d2l2 > max_d2l2) { max_d2l2 = d2l2; right_slice.start = (pos + count - 1) % count; }
            }
            le_eps = max_d2l2 <= eps * seg2;
        } else {
            le_eps = 1;
            sx = src[2 * slice.start]; sy = src[2 * slice.start + 1];
        }
        if (le_eps) WRITE_PT(sx, sy);
        else { right_slice.end = slice.end; slice.end = right_slice.start; PUSH(right_slice); PUSH(slice); }
    }
    if (!is_closed) WRITE_PT(src[2 * (count - 1)], src[2 * (count - 1) + 1]);
    /* final clean-up of [almost] straight lines */
    is_closed = is_closed0;
    count = new_count;
    pos = is_closed ? count - 1 : 0;
    READ_DST(sx, sy, pos);
    wpos = pos;
    READ_DST(px, py, pos);
    for (i = !is_closed; i < count - !is_closed && new_count > 2; i++) {
        double dx, dy, dist, sip;
        READ_DST(ex, ey, pos);
        dx = (double)(ex - sx);
        dy = (double)(ey - sy);
        dist = fabs((double)(px - sx) * dy - (double)(py - sy) * dx);
        sip = (double)((px - sx) * (ex - px) + (py - sy) * (ey - py));      /* OpenCV: float products and sum, then double */
        if (dist * dist <= 0.5 * eps * (dx * dx + dy * dy) && dx != 0 && dy != 0 && sip >= 0) {
            new_count--;
            dst[2 * wpos] = sx = ex; dst[2 * wpos + 1] = sy = ey;
            if (++wpos >= count) wpos = 0;
            READ_DST(px, py, pos);
            i++;
            continue;
        }
        dst[2 * wpos] = sx = px; dst[2 * wpos + 1] = sy = py;
        if (++wpos >= count) wpos = 0;
        px = ex; py = ey;
    }
    if (!is_closed) { dst[2 * wpos] = px; dst[2 * wpos + 1] = py; }
#undef PUSH
#undef READ_PT
#undef READ_DST
#undef WRITE_PT
    free(stack);
    return new_count;
}

/* OpenCV contourArea on float points, oriented=false */
static double contour_area_f(const float *pts, int n) {
    if (n == 0) return 0.0;
    double a00 = 0;
    float prevx = pts[2 * (n - 1)], prevy = pts[2 * (n - 1) + 1];
    for (int i = 0; i < n; i++) {
        float x = pts[2 * i], y = pts[2 * i + 1];
        a00 += (double)prevx * y - (double)prevy * x;
        prevx = x; prevy = y;
    }
    a00 *= 0.5;
    return fabs(a00);
}

/* ------------------------------------------------------------------ the diamond test (rmb_geometry, GEOS-free) */
#define DIAMOND_TOL 1e-9

static int diamond_of(const float *rel, int n, double *a, double *b) {
    /* rel: n points about the center, all on an axis -> the half-extents of a proper diamond */
    double xs[16], ys[16]; int nx = 0, ny = 0;
    double ux[16], uy[16]; int nu = 0;
    for (int i = 0; i < n; i++) {
        double x = rel[2 * i], y = rel[2 * i + 1];
        int dup = 0;
        for (int k = 0; k < nu; k++) if (ux[k] == x && uy[k] == y) { dup = 1; break; }
        if (!dup && nu < 16) { ux[nu] = x; uy[nu] = y; nu++; }
        if (y == 0.0 && nx < 16) { int d = 0; for (int k = 0; k < nx; k++) if (xs[k] == x) d = 1; if (!d) xs[nx++] = x; }
        if (x == 0.0 && ny < 16) { int d = 0; for (int k = 0; k < ny; k++) if (ys[k] == y) d = 1; if (!d) ys[ny++] = y; }
    }
    if (nu != 4 || nx < 2 || ny < 2) return 0;
    double xmin = xs[0], xmax = xs[0], ymin = ys[0], ymax = ys[0];
    for (int k = 1; k < nx; k++) { if (xs[k] < xmin) xmin = xs[k]; if (xs[k] > xmax) xmax = xs[k]; }
    for (int k = 1; k < ny; k++) { if (ys[k] < ymin) ymin = ys[k]; if (ys[k] > ymax) ymax = ys[k]; }
    double A = fabs(xmin) > fabs(xmax) ? fabs(xmin) : fabs(xmax);
    double B = fabs(ymin) > fabs(ymax) ? fabs(ymin) : fabs(ymax);
    if (A <= 0 || B <= 0) return 0;
    /* the four points must be exactly (+-A, 0), (0, +-B) */
    int seen[4] = {0, 0, 0, 0};
    for (int k = 0; k < nu; k++) {
        if (ux[k] == A && uy[k] == 0.0) seen[0] = 1;
        else if (ux[k] == -A && uy[k] == 0.0) seen[1] = 1;
        else if (ux[k] == 0.0 && uy[k] == B) seen[2] = 1;
        else if (ux[k] == 0.0 && uy[k] == -B) seen[3] = 1;
        else return 0;
    }
    if (!(seen[0] && seen[1] && seen[2] && seen[3])) return 0;
    *a = A; *b = B;
    return 1;
}

static void diamond_octagon(double a, double b, double r, double poly[16]) {
    double h = sqrt(a * a + b * b);
    double nx = b / h, ny = a / h;
    int k = 0;
    const int sgn[4][2] = {{1, 1}, {-1, 1}, {-1, -1}, {1, -1}};
    for (int q = 0; q < 4; q++) {
        double sx = sgn[q][0], sy = sgn[q][1];
        double px = sx * nx * r, py = sy * ny * r;
        double e0x = sx * a + px, e0y = py, e1x = px, e1y = sy * b + py;
        if (sx * sy > 0) { poly[k++] = e0x; poly[k++] = e0y; poly[k++] = e1x; poly[k++] = e1y; }
        else { poly[k++] = e1x; poly[k++] = e1y; poly[k++] = e0x; poly[k++] = e0y; }
    }
}

static int diamond_solid(double a, double b, double r) { return a * b / sqrt(a * a + b * b) <= r + DIAMOND_TOL; }

static int octagon_covers(const double *outer, const double *inner) {
    int n = 8;
    double sign = 0.0;
    for (int i = 0; i < n; i++) {
        double x0 = outer[2 * i], y0 = outer[2 * i + 1];
        double x1 = outer[2 * ((i + 1) % n)], y1 = outer[2 * ((i + 1) % n) + 1];
        double x2 = outer[2 * ((i + 2) % n)], y2 = outer[2 * ((i + 2) % n) + 1];
        double c = (x1 - x0) * (y2 - y1) - (y1 - y0) * (x2 - x1);
        if (fabs(c) > DIAMOND_TOL) { sign = c > 0 ? 1.0 : -1.0; break; }
    }
    if (sign == 0.0) return 0;
    for (int p = 0; p < 8; p++) {
        double px = inner[2 * p], py = inner[2 * p + 1];
        for (int i = 0; i < n; i++) {
            double x0 = outer[2 * i], y0 = outer[2 * i + 1];
            double x1 = outer[2 * ((i + 1) % n)], y1 = outer[2 * ((i + 1) % n) + 1];
            if (sign * ((x1 - x0) * (py - y0) - (y1 - y0) * (px - x0)) < -DIAMOND_TOL) return 0;
        }
    }
    return 1;
}

typedef struct { float cx, cy; double w; double poly[16]; int used; } sfoot;

/* ------------------------------------------------------------------ plan (rf_path: internal.h) */
/* -> 0, or -1 when memory ran out (p is then not stored) */
static int path_push(rf_path **P, int32_t *n, int32_t *cap, rf_path p) {
    if (*n == *cap) {
        int32_t c2 = *cap ? *cap * 2 : 256;
        rf_path *q = (rf_path *)realloc(*P, sizeof(rf_path) * (size_t)c2);
        if (!q) return -1;
        *P = q; *cap = c2;
    }
    (*P)[(*n)++] = p;
    return 0;
}

static double py_round_half_even(double x) { return rint(x); }   /* Python's round(): ties to even; rint under the default mode */

/* the depth loop's iteration cap: depth grows by at least min(.42 * .432 / ppg, .01) a level and stops at the field's
 * maximum (at most the grid's diagonal), so a real plan takes far fewer levels than this; the cap only guarantees an
 * end on an integer bound */
#define LEVEL_CAP ((int64_t)1 << 26)

/* -> the paths (rf_free each path's xy and the array), 0 for none, -1 when memory ran out (nothing left allocated) */
int32_t rf_plan(const uint8_t *mask, int32_t h, int32_t w_, double ppg, int flat, double max_page, rf_path **paths_out) {
    /* a = mask != 0; cells = repeat(a, factor) both axes; padded = pad(cells, 1) */
    int any = 0;
    double t_start = now_s();
    T_[4] += 1;
    plan_oom = 0;
    for (size_t i = 0; i < (size_t)h * w_ && !any; i++) any = mask[i] != 0;
    *paths_out = NULL;
    if (!any) return 0;
    double unit = flat ? .25 : .144;
    double minimum = flat ? 1.0 : .432;
    int factor = ppg > 3. ? 4 : ((ppg > 1. || !flat) ? 2 : 1);
    double wdt;
    {   /* Python's round() is ties-to-even; fmin(...)/unit lands on .5 only when the ratio is a half-integer */
        double v = fmin(3., ppg * (flat ? .70 : .60)) / unit;
        wdt = py_round_half_even(v) * unit;
    }
    double wv = minimum > wdt ? minimum : wdt;
    double first_peak = factor == 1 ? .49 : .49 - .5 / factor;
    double depth = fmax(.01, fmin(first_peak, wv / (2 * ppg) - (flat ? .16 : .02)));
    double first_depth = depth, first_width = wv;
    int32_t H = h * factor + 2, W = w_ * factor + 2;
    size_t HW = (size_t)H * W;
    rf_path *paths = NULL; int32_t np_ = 0, cap = 0;
    sfoot *small = NULL; int32_t nsmall = 0, csmall = 0;
    float *fbuf = NULL, *dbuf = NULL, *rounded = NULL; int32_t fcap = 0;
    double *q = NULL;
    int32_t *alive = NULL, *rowp = NULL;
    double *field = NULL;
    float *dist = NULL;
    uint8_t *padded = (uint8_t *)calloc(HW, 1);
    dist = (float *)malloc(sizeof(float) * HW);
    field = (double *)malloc(sizeof(double) * HW);
    alive = (int32_t *)malloc(sizeof(int32_t) * (HW ? HW : 1));
    rowp = (int32_t *)malloc(sizeof(int32_t) * ((size_t)H + 2));
    if (!padded || !dist || !field || !alive || !rowp) goto fail;
    for (int32_t r = 0; r < h; r++)
        for (int32_t c = 0; c < w_; c++)
            if (mask[(size_t)r * w_ + c])
                for (int dr = 0; dr < factor; dr++)
                    for (int dc = 0; dc < factor; dc++)
                        padded[(size_t)(1 + r * factor + dr) * W + (1 + c * factor + dc)] = 1;
    if (rf_edt_precise(padded, H, W, dist)) goto fail;
    /* field = where(padded, (dist - .5) / factor, -.5 / factor) in float32, then the level search in double */
    float fneg = (float)(-.5 / factor);               /* a Python float cast to the array's float32 */
    float limit_f = -FLT_MAX;
    for (size_t i = 0; i < HW; i++) {
        float v = padded[i] ? (dist[i] - 0.5f) / (float)factor : fneg;
        field[i] = (double)v;
        if (v > limit_f) limit_f = v;
    }
    double limit = (double)limit_f;
    free(dist); dist = NULL;
    free(padded); padded = NULL;
    /* the pixels above the level: every padded pixel above the field's floor to start with, filtered per level */
    int32_t nalive = 0;
    for (size_t i = 0; i < HW; i++) if (field[i] > (double)fneg) alive[nalive++] = (int32_t)i;
    T_[0] += now_s() - t_start;
    double t_loop = now_s(), t_fc = T_[1] + T_[2];
    int outer = 1;
    for (int64_t level = 0; depth < limit && level < LEVEL_CAP; level++) {
        int32_t nc;
        { int32_t k2 = 0; for (int32_t t = 0; t < nalive; t++) if (field[alive[t]] > depth) alive[k2++] = alive[t]; nalive = k2; }
        rf_contour *cs = find_contours_alive(field, H, W, depth, alive, nalive, rowp, &nc);
        if (plan_oom) goto fail;
        for (int32_t ci = 0; ci < nc; ci++) {
            rf_contour *ct = &cs[ci];
            if (ct->n < 4) continue;
            int32_t n = ct->n;
            /* the per-contour buffers, kept from contour to contour */
            if (fcap < n) {
                double *q2 = (double *)realloc(q, sizeof(double) * 2 * (size_t)n);
                if (q2) q = q2;
                float *f2 = q2 ? (float *)realloc(fbuf, sizeof(float) * 2 * (size_t)n) : NULL;
                if (f2) fbuf = f2;
                float *d2 = f2 ? (float *)realloc(dbuf, sizeof(float) * 4 * (size_t)n) : NULL;
                if (d2) dbuf = d2;
                float *r2 = d2 ? (float *)realloc(rounded, sizeof(float) * 4 * (size_t)n) : NULL;
                if (r2) rounded = r2;
                if (!r2) { for (int32_t t = 0; t < nc; t++) free(cs[t].rc); free(cs); goto fail; }
                fcap = n;
            }
            /* q = (contour[:, ::-1] - 1 + .5) / factor - .5  (double) */
            double xmin = DBL_MAX, xmax = -DBL_MAX, ymin = DBL_MAX, ymax = -DBL_MAX;
            for (int32_t i = 0; i < n; i++) {
                double x = ((ct->rc[2 * i + 1] - 1) + .5) / factor - .5;
                double y = ((ct->rc[2 * i] - 1) + .5) / factor - .5;
                q[2 * i] = x; q[2 * i + 1] = y;
                if (x < xmin) xmin = x;
                if (x > xmax) xmax = x;
                if (y < ymin) ymin = y;
                if (y > ymax) ymax = y;
            }
            double span = fmax(xmax - xmin, ymax - ymin);
            for (int32_t i = 0; i < 2 * n; i++) fbuf[i] = (float)q[i];
            int smooth = (!flat) && n > 12 && span > 6 && contour_area_f(fbuf, n) > 6;
            double eps = smooth ? .32 : (outer ? fmin(.18, .22 / ppg) : fmin(.4, fmin(.60 / ppg, .10 * wv / ppg)));
            int nco = approx_poly_dp_f(fbuf, n, dbuf, 1, eps);
            if (plan_oom) { for (int32_t t = 0; t < nc; t++) free(cs[t].rc); free(cs); goto fail; }
            float *compact = dbuf; int32_t ncomp = nco;
            if (smooth && ncomp >= 4) {
                /* the rounded corners: 2 points per simplified point, nco <= n so 4 * n floats hold them */
                for (int32_t i = 0; i < ncomp; i++) {
                    int32_t ip = (i - 1 + ncomp) % ncomp, in_ = (i + 1) % ncomp;
                    float vx = compact[2 * ip] - compact[2 * i], vy = compact[2 * ip + 1] - compact[2 * i + 1];
                    float ux = compact[2 * in_] - compact[2 * i], uy = compact[2 * in_ + 1] - compact[2 * i + 1];
                    float nv = sqrtf(vx * vx + vy * vy), nu = sqrtf(ux * ux + uy * uy);
                    float fv = fminf(0.22f / fmaxf(nv, 1e-9f), 0.20f), fu = fminf(0.22f / fmaxf(nu, 1e-9f), 0.20f);
                    vx *= fv; vy *= fv; ux *= fu; uy *= fu;
                    rounded[4 * i] = compact[2 * i] + vx; rounded[4 * i + 1] = compact[2 * i + 1] + vy;
                    rounded[4 * i + 2] = compact[2 * i] + ux; rounded[4 * i + 3] = compact[2 * i + 1] + uy;
                }
                compact = rounded; ncomp = 2 * nco;
            }
            rf_path path; path.w = wv;
            if (ncomp >= 3) {
                /* q = vstack((compact, compact[0])) -- float32 points */
                path.n = ncomp + 1; path.f32 = 1;
                path.xy = (double *)malloc(sizeof(double) * 2 * ((size_t)path.n + 1));
                if (!path.xy) { for (int32_t t = 0; t < nc; t++) free(cs[t].rc); free(cs); goto fail; }
                for (int32_t i = 0; i < ncomp; i++) { path.xy[2 * i] = compact[2 * i]; path.xy[2 * i + 1] = compact[2 * i + 1]; }
                path.xy[2 * ncomp] = compact[0]; path.xy[2 * ncomp + 1] = compact[1];
                int skip = 0;
                if (flat && path.n == 5) {
                    float fx[10]; for (int32_t i = 0; i < 10; i++) fx[i] = (float)path.xy[i];
                    float qxmin = fx[0], qxmax = fx[0], qymin = fx[1], qymax = fx[1];
                    for (int32_t i = 1; i < 5; i++) { if (fx[2 * i] < qxmin) qxmin = fx[2 * i]; if (fx[2 * i] > qxmax) qxmax = fx[2 * i]; if (fx[2 * i + 1] < qymin) qymin = fx[2 * i + 1]; if (fx[2 * i + 1] > qymax) qymax = fx[2 * i + 1]; }
                    float cx = (qxmin + qxmax) * 0.5f, cy = (qymin + qymax) * 0.5f;
                    float rel[10]; int axis = 1;
                    for (int32_t i = 0; i < 5; i++) { rel[2 * i] = fx[2 * i] - cx; rel[2 * i + 1] = fx[2 * i + 1] - cy; if (!(rel[2 * i] == 0.0f || rel[2 * i + 1] == 0.0f)) axis = 0; }
                    if (axis) {
                        double a, b;
                        if (diamond_of(rel, 5, &a, &b)) {
                            double r = (wv / ppg) / 2;
                            double shape[16]; diamond_octagon(a, b, r, shape);
                            sfoot *prev = NULL;
                            for (int32_t k = 0; k < nsmall; k++) if (small[k].cx == cx && small[k].cy == cy) { prev = &small[k]; break; }
                            if (prev && prev->w == wv && octagon_covers(prev->poly, shape)) skip = 1;
                            else if (diamond_solid(a, b, r)) {
                                if (!prev || octagon_covers(shape, prev->poly)) {
                                    if (!prev) {
                                        if (nsmall == csmall) {
                                            int32_t c2 = csmall ? csmall * 2 : 256;
                                            sfoot *s2 = (sfoot *)realloc(small, sizeof(sfoot) * (size_t)c2);
                                            if (!s2) { free(path.xy); for (int32_t t = 0; t < nc; t++) free(cs[t].rc); free(cs); goto fail; }
                                            small = s2; csmall = c2;
                                        }
                                        prev = &small[nsmall++]; prev->cx = cx; prev->cy = cy;
                                    }
                                    prev->w = wv; memcpy(prev->poly, shape, sizeof(shape));
                                }
                            }
                        }
                    }
                }
                if (skip) { free(path.xy); continue; }
            } else {
                path.n = n; path.f32 = 0;
                path.xy = (double *)malloc(sizeof(double) * 2 * ((size_t)n + 1));
                if (!path.xy) { for (int32_t t = 0; t < nc; t++) free(cs[t].rc); free(cs); goto fail; }
                memcpy(path.xy, q, sizeof(double) * 2 * (size_t)n);
            }
            /* paths.append((pts + [pts[1]], w)): the first segment repeated */
            path.xy[2 * path.n] = path.xy[2]; path.xy[2 * path.n + 1] = path.xy[3];
            path.n += 1;
            if (path_push(&paths, &np_, &cap, path)) { free(path.xy); for (int32_t t = 0; t < nc; t++) free(cs[t].rc); free(cs); goto fail; }
        }
        for (int32_t ci = 0; ci < nc; ci++) free(cs[ci].rc);
        free(cs);
        double step = fmin(.42 * wv / ppg, fmax(.04 / factor, wv / (2 * ppg) - .50 / factor));
        depth += step;
        double next_w = fmin(max_page, fmin(wv * 1.6, first_width + 2 * (depth - first_depth) * ppg));
        double wq = floor((next_w + 1e-8) / unit) * unit;
        wv = minimum > wq ? minimum : wq;
        outer = 0;
    }
    free(q); free(fbuf); free(dbuf); free(rounded); free(small); free(field); free(alive); free(rowp);
    T_[3] += (now_s() - t_loop) - ((T_[1] + T_[2]) - t_fc);
    *paths_out = paths;
    return np_;
fail:
    plan_oom = 1;
    for (int32_t i = 0; i < np_; i++) free(paths[i].xy);
    free(paths);
    free(q); free(fbuf); free(dbuf); free(rounded); free(small); free(field); free(alive); free(rowp); free(dist); free(padded);
    return -1;
}
/* ------------------------------------------------------------------ the stages on their own, for the identity tests */
RF_API int32_t rf_test_edt(const uint8_t *src, int32_t m, int32_t n, float *dst) { return rf_edt_precise(src, m, n, dst); }

RF_API int32_t rf_test_contours(const double *field, int32_t m, int32_t n, double level, int32_t **counts, double **rc) {
    int32_t nc;
    plan_oom = 0;
    *counts = NULL; *rc = NULL;
    rf_contour *cs = find_contours(field, m, n, level, &nc);
    if (plan_oom) return -1;
    int64_t total = 0;
    for (int32_t i = 0; i < nc; i++) total += cs[i].n;
    *counts = (int32_t *)malloc(sizeof(int32_t) * (nc ? nc : 1));
    *rc = (double *)malloc(sizeof(double) * 2 * (size_t)(total ? total : 1));
    if (!*counts || !*rc) {
        free(*counts); free(*rc); *counts = NULL; *rc = NULL;
        for (int32_t i = 0; i < nc; i++) free(cs[i].rc);
        free(cs);
        return -1;
    }
    int64_t k = 0;
    for (int32_t i = 0; i < nc; i++) { (*counts)[i] = cs[i].n; memcpy(*rc + 2 * k, cs[i].rc, sizeof(double) * 2 * cs[i].n); k += cs[i].n; free(cs[i].rc); }
    free(cs);
    return nc;
}

RF_API int32_t rf_test_approx(const float *pts, int32_t n, double eps, float *dst) {
    plan_oom = 0;
    int32_t m = approx_poly_dp_f(pts, n, dst, 1, eps);
    return plan_oom ? -1 : m;
}

/* the plan itself, before placement: paths as (counts, xy in grid coordinates, w, f32 flag) */
RF_API int32_t rf_test_plan(const uint8_t *mask, int32_t h, int32_t w_, double ppg, int flat, double max_page, int32_t **counts, double **xy, double **wout, int32_t **f32) {
    rf_path *paths; int32_t np_ = rf_plan(mask, h, w_, ppg, flat, max_page, &paths);
    *counts = NULL; *xy = NULL; *wout = NULL; *f32 = NULL;
    if (np_ <= 0) return np_;
    int64_t total = 0;
    for (int32_t i = 0; i < np_; i++) total += paths[i].n;
    *counts = (int32_t *)malloc(sizeof(int32_t) * np_); *wout = (double *)malloc(sizeof(double) * np_); *f32 = (int32_t *)malloc(sizeof(int32_t) * np_);
    *xy = (double *)malloc(sizeof(double) * 2 * (size_t)total);
    if (!*counts || !*wout || !*f32 || !*xy) {
        free(*counts); free(*wout); free(*f32); free(*xy); *counts = NULL; *wout = NULL; *f32 = NULL; *xy = NULL;
        for (int32_t i = 0; i < np_; i++) free(paths[i].xy);
        free(paths);
        return -1;
    }
    int64_t k = 0;
    for (int32_t i = 0; i < np_; i++) {
        (*counts)[i] = paths[i].n; (*wout)[i] = paths[i].w; (*f32)[i] = paths[i].f32;
        memcpy(*xy + 2 * k, paths[i].xy, sizeof(double) * 2 * paths[i].n); k += paths[i].n;
        free(paths[i].xy);
    }
    free(paths);
    return np_;
}
RF_API double rf_test_area(const float *pts, int32_t n) { return contour_area_f(pts, n); }

/* ------------------------------------------------------------------ fill: placement onto the page */
/* rm_trace.place's frame: the scale and origin that fit the gw x gh grid into the box (x0, y0, x1, y1) */
void rf_place_frame(double x0, double y0, double x1, double y1, int32_t gw, int32_t gh, double *ox, double *oy, double *scale) {
    double s = fmin((x1 - x0) / gw, (y1 - y0) / gh);
    *scale = s;
    *ox = x0 + ((x1 - x0) - gw * s) / 2.0;
    *oy = y0 + ((y1 - y0) - gh * s) / 2.0;
}

/* one path placed: (x + offset) then ox + x * scale, in float32 for a float32 path (numpy.float32 points meeting
 * Python floats and ints, NEP 50) and in double otherwise; dst gets 2 * p->n values */
void rf_place_path(const rf_path *p, double ox, double oy, double scale, int32_t offx, int32_t offy, double *dst) {
    if (p->f32) {
        float fs = (float)scale, fox = (float)ox, foy = (float)oy;
        for (int32_t t = 0; t < p->n; t++) {
            float x = (float)p->xy[2 * t] + (float)offx, y = (float)p->xy[2 * t + 1] + (float)offy;
            dst[2 * t] = (double)(fox + x * fs);
            dst[2 * t + 1] = (double)(foy + y * fs);
        }
    } else {
        for (int32_t t = 0; t < p->n; t++) {
            double x = p->xy[2 * t] + offx, y = p->xy[2 * t + 1] + offy;
            dst[2 * t] = ox + x * scale;
            dst[2 * t + 1] = oy + y * scale;
        }
    }
}

/* the path's width field (rm_paint._hl_field / _field) and pen: 0 highlighter, 1 FINELINER_2, 2 MARKER_2 */
void rf_path_field(const rf_path *p, int flat, double hl_scale, double pen_scale, double fineliner_max, int32_t *field, int32_t *pen) {
    if (flat) { int f = (int)rint(p->w / hl_scale); *field = f > 4 ? f : 4; *pen = 0; }
    else { int f = (int)rint(p->w / pen_scale); *field = f > 2 ? f : 2; *pen = p->w <= fineliner_max ? 1 : 2; }
}

RF_API int32_t rf_fill(const uint8_t *mask, int32_t h, int32_t w_, double ppg, int flat, double max_page,
                       double x0, double y0, double x1, double y1, int32_t offx, int32_t offy, int32_t gw, int32_t gh,
                       double hl_scale, double pen_scale, double fineliner_max,
                       int32_t **counts, double **xy, int32_t **field, int32_t **pen, int32_t **f32) {
    rf_path *paths; int32_t np_ = rf_plan(mask, h, w_, ppg, flat, max_page, &paths);
    *counts = NULL; *xy = NULL; *field = NULL; *pen = NULL; *f32 = NULL;
    if (np_ <= 0) return np_;
    double scale, ox, oy;
    rf_place_frame(x0, y0, x1, y1, gw, gh, &ox, &oy, &scale);
    int64_t total = 0;
    for (int32_t i = 0; i < np_; i++) total += paths[i].n;
    *counts = (int32_t *)malloc(sizeof(int32_t) * np_);
    *field = (int32_t *)malloc(sizeof(int32_t) * np_);
    *pen = (int32_t *)malloc(sizeof(int32_t) * np_);
    *f32 = (int32_t *)malloc(sizeof(int32_t) * np_);     /* 1: the path's points are numpy.float32 in the Python */
    *xy = (double *)malloc(sizeof(double) * 2 * (size_t)total);
    if (!*counts || !*field || !*pen || !*f32 || !*xy) {
        free(*counts); free(*field); free(*pen); free(*f32); free(*xy);
        *counts = NULL; *xy = NULL; *field = NULL; *pen = NULL; *f32 = NULL;
        for (int32_t i = 0; i < np_; i++) free(paths[i].xy);
        free(paths);
        return -1;
    }
    int64_t k = 0;
    for (int32_t i = 0; i < np_; i++) {
        rf_path *p = &paths[i];
        (*counts)[i] = p->n;
        (*f32)[i] = p->f32;
        rf_place_path(p, ox, oy, scale, offx, offy, *xy + 2 * k);
        k += p->n;
        rf_path_field(p, flat, hl_scale, pen_scale, fineliner_max, &(*field)[i], &(*pen)[i]);
        free(p->xy);
    }
    free(paths);
    return np_;
}
