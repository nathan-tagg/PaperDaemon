/* The lossless pass -- rm_lean.prune_join, decision for decision.
 *
 *   cover: every wash's SURE footprint (the pixel-center rule shrunk by EPS) and POSSIBLE footprint (widened by
 *          eps_out when given, else by EPS); per channel the darkest value every pixel surely gets and how many washes
 *          give it (m1, c1) -- and the same under the wide rule (m2, c2) when eps_out is given.
 *   drops: smallest footprint first, a wash goes when it is nowhere the sole provider of the darkest value (under each
 *          rule), and its edge ties are already that dark from the rest.
 *   join:  washes of one color, tool, pen color and width chain end to start, nearest first, wherever the joined
 *          piece leaves every pixel as it was under both rules.
 * Orders are the Python's: stable sorts, dict insertion order, (d, j, rev) candidate order. GEOMETRY code.
 * Every allocation is checked: a failure raises the context's oom flag, the work in progress continues on empty
 * sets (never a NULL dereference) and rf_prune_join returns -1 with nothing left allocated. */
#include <math.h>
#include <stdatomic.h>
#include <stdlib.h>
#include <string.h>
#include "rmfast.h"
#include "internal.h"

typedef struct { int32_t *idx; int32_t n; } iset;          /* a sorted unique pixel set */

typedef struct {
    const rf_strokes *in;
    int64_t *start;            /* first point index of each stroke */
    double ox, oy;
    int32_t W, H;
    int wide;
    double eo;
    uint8_t *m1, *m2;          /* 3 x W*H */
    uint16_t *c1, *c2;
    iset *sure, *poss;         /* per stroke (empty for non-washes) */
    uint8_t *drop;
    rf_scratch S;
    atomic_int *oom;           /* raised by any allocation that failed, on any thread */
} ctx;

static void iset_free(iset *s) { free(s->idx); s->idx = NULL; s->n = 0; }

static iset footprint_s(const ctx *C, rf_scratch *S, const double *xy, const double *w, int32_t npts, double eps) {
    iset s = {NULL, 0};
    s.n = rf_wash_pixels_into(xy, w, npts, C->ox, C->oy, C->W, C->H, eps, S, &s.idx);
    if (s.n < 0) { atomic_store(C->oom, 1); s.n = 0; s.idx = NULL; }
    return s;
}

/* a set operation's result; when it could not be allocated, the empty set and the oom flag raised */
static int32_t *setop(const ctx *C, int32_t *p, int32_t *n) {
    if (!p) { atomic_store(C->oom, 1); *n = 0; }
    return p;
}

static iset footprint_of(ctx *C, const double *xy, const double *w, int32_t npts, double eps) {
    return footprint_s(C, &C->S, xy, w, npts, eps);
}

static iset stroke_fp(ctx *C, int32_t i, double eps) {
    const rf_strokes *in = C->in;
    return footprint_of(C, in->xy + 2 * C->start[i], in->w + C->start[i], in->counts[i], eps);
}

static void rgb_of(const rf_strokes *in, int32_t i, int v[3]) { v[0] = in->rgb[3 * i]; v[1] = in->rgb[3 * i + 1]; v[2] = in->rgb[3 * i + 2]; }

static void darken(uint8_t *m, uint16_t *c, size_t N, const iset *f, const int col[3]) {
    for (int k = 0; k < 3; k++) {
        uint8_t v = (uint8_t)col[k];
        uint8_t *mk = m + k * N;
        uint16_t *ck = c + k * N;
        for (int32_t t = 0; t < f->n; t++) {
            int32_t p = f->idx[t];
            if (v < mk[p]) { mk[p] = v; ck[p] = 1; }
            else if (v == mk[p]) ck[p] += 1;
        }
    }
}

static int sole(const uint8_t *m, const uint16_t *c, size_t N, const iset *f, const int col[3]) {
    for (int k = 0; k < 3; k++) {
        uint8_t v = (uint8_t)col[k];
        const uint8_t *mk = m + k * N;
        const uint16_t *ck = c + k * N;
        for (int32_t t = 0; t < f->n; t++) if (mk[f->idx[t]] == v && ck[f->idx[t]] == 1) return 1;
    }
    return 0;
}

static void spend(uint8_t *m, uint16_t *c, size_t N, const iset *f, const int col[3]) {
    for (int k = 0; k < 3; k++) {
        uint8_t v = (uint8_t)col[k];
        uint8_t *mk = m + k * N;
        uint16_t *ck = c + k * N;
        for (int32_t t = 0; t < f->n; t++) if (mk[f->idx[t]] == v) ck[f->idx[t]] -= 1;
    }
}

/* any(m[k][pix] > col[k]) over k */
static int any_darker_needed(const uint8_t *m, size_t N, const int32_t *pix, int32_t n, const int col[3]) {
    for (int k = 0; k < 3; k++) {
        const uint8_t *mk = m + k * N;
        for (int32_t t = 0; t < n; t++) if (mk[pix[t]] > col[k]) return 1;
    }
    return 0;
}

/* rm_lean.free: all(m1[k][pix] <= col[k]) */
static int all_free(const uint8_t *m, size_t N, const int32_t *pix, int32_t n, const int col[3]) {
    return !any_darker_needed(m, N, pix, n, col);
}

/* ---- the grid (rm_lean._grid): all strokes' points, 40 px of margin, integer origin */
static void grid_of(ctx *C) {
    const rf_strokes *in = C->in;
    double xmin = 1e300, xmax = -1e300, ymin = 1e300, ymax = -1e300;
    int any = 0;
    for (int32_t i = 0; i < in->n; i++) {
        for (int32_t k = 0; k < in->counts[i]; k++) {
            double x = in->xy[2 * (C->start[i] + k)], y = in->xy[2 * (C->start[i] + k) + 1];
            if (x < xmin) xmin = x;
            if (x > xmax) xmax = x;
            if (y < ymin) ymin = y;
            if (y > ymax) ymax = y;
            any = 1;
        }
    }
    if (!any) { xmin = xmax = ymin = ymax = 0.0; }
    C->ox = floor(xmin - 40.0);
    C->oy = floor(ymin - 40.0);
    C->W = (int32_t)(xmax + 40.0 - C->ox) + 1;
    C->H = (int32_t)(ymax + 40.0 - C->oy) + 1;
}

static int is_wash_i(const rf_strokes *in, int32_t i) { return in->wash[i] && in->counts[i] >= 2; }

/* ---- cover */
typedef struct { ctx *C; rf_scratch *S; atomic_int next; } coverjob;

static void cover_worker(void *arg, int tid) {
    coverjob *J = (coverjob *)arg;
    ctx *C = J->C;
    const rf_strokes *in = C->in;
    for (;;) {
        int32_t k0 = atomic_fetch_add(&J->next, 256);
        if (k0 >= in->n) break;
        int32_t k1 = k0 + 256 < in->n ? k0 + 256 : in->n;
        for (int32_t i = k0; i < k1; i++) {
            if (!is_wash_i(in, i)) continue;
            const double *xy = in->xy + 2 * C->start[i], *w = in->w + C->start[i];
            iset f = footprint_s(C, &J->S[tid], xy, w, in->counts[i], -RF_EPS);
            iset p = footprint_s(C, &J->S[tid], xy, w, in->counts[i], C->eo);
            C->sure[i] = f;
            if (p.n != f.n) C->poss[i] = p;
            else { iset_free(&p); C->poss[i] = f; }          /* the same set: share it (Python: poss[i] = f) */
        }
    }
}

static void cover(ctx *C) {
    const rf_strokes *in = C->in;
    size_t N = (size_t)C->W * C->H;
    C->m1 = (uint8_t *)malloc(3 * N);
    C->c1 = (uint16_t *)malloc(3 * N * sizeof(uint16_t));
    if (C->wide) {
        C->m2 = (uint8_t *)malloc(3 * N);
        C->c2 = (uint16_t *)malloc(3 * N * sizeof(uint16_t));
    }
    C->sure = (iset *)calloc((size_t)in->n, sizeof(iset));
    C->poss = (iset *)calloc((size_t)in->n, sizeof(iset));
    coverjob J; J.C = C; atomic_init(&J.next, 0);
    int nt = rf_threads();
    J.S = (rf_scratch *)calloc((size_t)nt, sizeof(rf_scratch));
    if (!C->m1 || !C->c1 || (C->wide && (!C->m2 || !C->c2)) || !C->sure || !C->poss || !J.S) { atomic_store(C->oom, 1); free(J.S); return; }
    memset(C->m1, 255, 3 * N);
    for (size_t t = 0; t < 3 * N; t++) C->c1[t] = 1;
    if (C->wide) {
        memset(C->m2, 255, 3 * N);
        for (size_t t = 0; t < 3 * N; t++) C->c2[t] = 1;
    }
    /* every wash's two footprints, on all threads, each into its stroke's slot; then the darkening in stroke order */
    rf_parallel(nt, cover_worker, &J);
    for (int t = 0; t < nt; t++) rf_scratch_free(&J.S[t]);
    free(J.S);
    for (int32_t i = 0; i < in->n; i++) {
        if (!is_wash_i(in, i)) continue;
        iset f = C->sure[i];
        int col[3]; rgb_of(in, i, col);
        if (f.n) darken(C->m1, C->c1, N, &f, col);
        if (C->wide && C->poss[i].n) darken(C->m2, C->c2, N, &C->poss[i], col);
    }
}

/* ---- drops: smallest sure footprint first (stable) */
typedef struct { int32_t i, n; } order_t;
static int cmp_order(const void *a, const void *b) {
    const order_t *x = (const order_t *)a, *y = (const order_t *)b;
    if (x->n != y->n) return x->n < y->n ? -1 : 1;
    return x->i < y->i ? -1 : (x->i > y->i);
}

static void drops(ctx *C) {
    const rf_strokes *in = C->in;
    size_t N = (size_t)C->W * C->H;
    C->drop = (uint8_t *)calloc((size_t)in->n, 1);
    int32_t nw = 0;
    for (int32_t i = 0; i < in->n; i++) if (is_wash_i(in, i)) nw++;
    order_t *ord = (order_t *)malloc(sizeof(order_t) * (nw ? nw : 1));
    if (!C->drop || !ord) { atomic_store(C->oom, 1); free(ord); return; }
    int32_t k = 0;
    for (int32_t i = 0; i < in->n; i++) if (is_wash_i(in, i)) { ord[k].i = i; ord[k].n = C->sure[i].n; k++; }
    qsort(ord, nw, sizeof(order_t), cmp_order);
    for (int32_t t = 0; t < nw; t++) {
        int32_t i = ord[t].i;
        iset *f = &C->sure[i], *p = &C->poss[i];
        int col[3]; rgb_of(in, i, col);
        if (!p->n) continue;
        if (f->n && sole(C->m1, C->c1, N, f, col)) continue;
        if (C->wide) {
            if (sole(C->m2, C->c2, N, p, col)) continue;
            iset tf = stroke_fp(C, i, RF_EPS);
            int32_t nt; int32_t *tie = setop(C, rf_setdiff(tf.idx, tf.n, f->idx, f->n, &nt), &nt);
            int bad = nt && any_darker_needed(C->m1, N, tie, nt, col);
            free(tie); iset_free(&tf);
            if (bad) continue;
        } else if (p->n > f->n) {
            int32_t ne; int32_t *extra = setop(C, rf_setdiff(p->idx, p->n, f->idx, f->n, &ne), &ne);
            int bad = any_darker_needed(C->m1, N, extra, ne, col);
            free(extra);
            if (bad) continue;
        }
        C->drop[i] = 1;
        if (f->n) spend(C->m1, C->c1, N, f, col);
        if (C->wide) spend(C->m2, C->c2, N, p, col);
    }
    free(ord);
}

/* ---- the join */
typedef struct { double x, y; } pt;

typedef struct {               /* a group: one color, tool, pen color and width */
    int64_t key; double w0;
    int32_t *idx, n, cap;
} grp;

typedef struct { int64_t cx, cy; int32_t *idx, n, cap; } bucket;

static uint64_t hash64(uint64_t x) { x ^= x >> 33; x *= 0xff51afd7ed558ccdULL; x ^= x >> 33; x *= 0xc4ceb9fe1a85ec53ULL; x ^= x >> 33; return x; }

typedef struct { bucket *b; size_t cap, n; } bmap;

/* the bucket of (cx, cy); NULL when it does not exist and create is 0, or when memory ran out */
static bucket *bmap_get(bmap *M, int64_t cx, int64_t cy, int create) {
    if (M->cap == 0) {
        if (!create) return NULL;
        bucket *b0 = (bucket *)calloc(1024, sizeof(bucket));
        if (!b0) return NULL;
        M->cap = 1024; M->b = b0;
        for (size_t t = 0; t < M->cap; t++) M->b[t].n = -1;
    }
    if (create && M->n * 2 >= M->cap) {               /* grow */
        bucket *nb0 = (bucket *)calloc(M->cap * 2, sizeof(bucket));
        if (!nb0) return NULL;
        bmap old = *M;
        M->cap = old.cap * 2; M->n = 0; M->b = nb0;
        for (size_t t = 0; t < M->cap; t++) M->b[t].n = -1;
        for (size_t t = 0; t < old.cap; t++) if (old.b[t].n >= 0) {
            bucket *nb = bmap_get(M, old.b[t].cx, old.b[t].cy, 1);     /* load under half: no growth, no failure */
            free(nb->idx); *nb = old.b[t];
        }
        free(old.b);
    }
    uint64_t h = hash64((uint64_t)cx * 0x9E3779B97F4A7C15ULL ^ (uint64_t)cy) & (M->cap - 1);
    for (;;) {
        bucket *b = &M->b[h];
        if (b->n < 0) {
            if (!create) return NULL;
            b->cx = cx; b->cy = cy; b->n = 0; b->cap = 0; b->idx = NULL; M->n++;
            return b;
        }
        if (b->cx == cx && b->cy == cy) return b;
        h = (h + 1) & (M->cap - 1);
    }
}

/* -> 0, or -1 when memory ran out (b NULL: its map could not grow) */
static int bucket_add(bucket *b, int32_t i) {
    if (!b) return -1;
    for (int32_t t = 0; t < b->n; t++) if (b->idx[t] == i) return 0;      /* a set */
    if (b->n == b->cap) {
        int32_t cap = b->cap ? b->cap * 2 : 4;
        int32_t *q = (int32_t *)realloc(b->idx, sizeof(int32_t) * (size_t)cap);
        if (!q) return -1;
        b->idx = q; b->cap = cap;
    }
    b->idx[b->n++] = i;
    return 0;
}

/* ---- NEP 50 scalar arithmetic. The Python join works on the stroke tuples' own scalars: numpy.float32 points (the
 * planner's simplified loops) give float32 arithmetic with Python floats and with each other, numpy.float64 wins over
 * float32, a Python float takes the other operand's type. */
static int kind_of(const rf_strokes *in, int32_t i, int tail, int axis) {
    return in->kind ? in->kind[4 * i + 2 * tail + axis] : RF_KIND_PY;
}

static int promote(int a, int b) {
    if (a == RF_KIND_F64 || b == RF_KIND_F64) return RF_KIND_F64;
    if (a == RF_KIND_F32 || b == RF_KIND_F32) return RF_KIND_F32;
    return RF_KIND_PY;
}

/* int(v // cell) for a coordinate of the given kind (cell is a Python float) */
static int64_t bucket_key(double v, int kind, double cell) {
    if (kind == RF_KIND_F32) return (int64_t)rf_np_floordivf((float)v, (float)cell);
    return (int64_t)rf_py_floordiv(v, cell);
}

/* a - b, then squared, in the promoted kind of the two operands; the value and its kind */
static double sq_diff(double a, int ka, double b, int kb, int *k) {
    *k = promote(ka, kb);
    if (*k == RF_KIND_F32) { float d = (float)a - (float)b; return (double)(d * d); }
    double d = a - b;
    return d * d;
}

/* math.sqrt((bx - ex) * (bx - ex) + (by - ey) * (by - ey)) with the operands' kinds */
static double join_dist(double bx, double by, int kbx, int kby, double ex, double ey, int kex, int key) {
    int kx, ky;
    double sx = sq_diff(bx, kbx, ex, kex, &kx), sy = sq_diff(by, kby, ey, key, &ky);
    if (promote(kx, ky) == RF_KIND_F32) {
        float s = (float)sx + (float)sy;      /* a double-kind term here is a Python float: cast to float32 (weak) */
        return sqrt((double)s);
    }
    return sqrt(sx + sy);
}

typedef struct { double d; int32_t j; int rev; } cand;
static int cmp_cand(const void *a, const void *b) {
    const cand *x = (const cand *)a, *y = (const cand *)b;
    if (x->d != y->d) return x->d < y->d ? -1 : 1;
    if (x->j != y->j) return x->j < y->j ? -1 : 1;
    return x->rev - y->rev;
}

typedef struct { int32_t i; double x, y; int32_t ord; } sortkey;
static int cmp_sortkey(const void *a, const void *b) {
    const sortkey *x = (const sortkey *)a, *y = (const sortkey *)b;
    if (x->y != y->y) return x->y < y->y ? -1 : 1;
    if (x->x != y->x) return x->x < y->x ? -1 : 1;
    return x->ord < y->ord ? -1 : (x->ord > y->ord);
}

/* end footprints, cached per (stroke, tail, which eps) */
enum { E_SURE = 0, E_TIE = 1, E_WIDE = 2 };
typedef struct { iset s[2][3]; uint8_t have[2][3]; } endcache;

/* an end's three footprints (sure -EPS, tie +EPS, wide eo) come from one painting, the first time any is asked for;
 * each list is an array of its own size, kept for the rest of the pass */
static iset *end_fp(const ctx *C, rf_scratch *S, endcache *E, int32_t i, int tail, int which) {
    if (!E[i].have[tail][which]) {
        const rf_strokes *in = C->in;
        int32_t n = in->counts[i];
        int32_t a = tail ? n - 2 : 0;
        const double ee[3] = {-RF_EPS, RF_EPS, C->eo};             /* E_SURE, E_TIE, E_WIDE */
        int32_t *bufs[3] = {NULL, NULL, NULL}, cn[3];
        size_t caps[3] = {0, 0, 0};
        if (rf_wash_pixels_multi(in->xy + 2 * (C->start[i] + a), in->w + C->start[i] + a, 2, C->ox, C->oy, C->W, C->H, ee, 3, S, bufs, caps, cn)) {
            atomic_store(C->oom, 1);
            free(bufs[0]); free(bufs[1]); free(bufs[2]);
            bufs[0] = bufs[1] = bufs[2] = NULL;
            cn[0] = cn[1] = cn[2] = 0;
        }
        for (int e = 0; e < 3; e++) {
            if (E[i].have[tail][e]) { free(bufs[e]); continue; }    /* one asked for before: keep it */
            E[i].s[tail][e].idx = bufs[e]; E[i].s[tail][e].n = cn[e];
            E[i].have[tail][e] = 1;
        }
    }
    return &E[i].s[tail][which];
}

/* A chain being built: its points, widths and the scalar kinds of each point's x and y (k, two per point: what the
 * stroke store hands back as each coordinate's Python type). oom: memory ran out; the pass then fails as a whole. */
typedef struct { double *xy, *w; uint8_t *k; int32_t n, cap; int oom; } chain_t;
static void chain_push(chain_t *c, double x, double y, double w, const uint8_t *k) {
    if (c->oom) return;
    if (c->n == c->cap) {
        int32_t cap = c->cap ? c->cap * 2 : 64;
        double *nxy = (double *)realloc(c->xy, sizeof(double) * 2 * (size_t)cap);
        if (!nxy) { c->oom = 1; return; }
        c->xy = nxy;
        double *nw = (double *)realloc(c->w, sizeof(double) * (size_t)cap);
        if (!nw) { c->oom = 1; return; }
        c->w = nw;
        uint8_t *nk = (uint8_t *)realloc(c->k, 2 * (size_t)cap);
        if (!nk) { c->oom = 1; return; }
        c->k = nk;
        c->cap = cap;
    }
    c->xy[2 * c->n] = x; c->xy[2 * c->n + 1] = y; c->w[c->n] = w;
    c->k[2 * c->n] = k ? k[0] : 0; c->k[2 * c->n + 1] = k ? k[1] : 0;
    c->n++;
}

/* the pass's output; k: the points' scalar kinds (zeros when the input carried none) */
typedef struct { int32_t *counts, *src; double *xy, *w; uint8_t *k; int32_t n, cap; int64_t npts, cap_pts; int oom; } outbuf;
static void out_add(outbuf *o, const double *xy, const double *w, const uint8_t *k, int32_t n, int32_t src) {
    if (o->oom) return;
    if (o->n == o->cap) {
        int32_t cap = o->cap ? o->cap * 2 : 1024;
        int32_t *nc = (int32_t *)realloc(o->counts, sizeof(int32_t) * (size_t)cap);
        if (!nc) { o->oom = 1; return; }
        o->counts = nc;
        int32_t *ns = (int32_t *)realloc(o->src, sizeof(int32_t) * (size_t)cap);
        if (!ns) { o->oom = 1; return; }
        o->src = ns;
        o->cap = cap;
    }
    if (o->npts + n > o->cap_pts) {
        int64_t cap = o->cap_pts ? o->cap_pts : 65536;
        while (o->npts + n > cap) cap *= 2;
        double *nxy = (double *)realloc(o->xy, sizeof(double) * 2 * (size_t)cap);
        if (!nxy) { o->oom = 1; return; }
        o->xy = nxy;
        double *nw = (double *)realloc(o->w, sizeof(double) * (size_t)cap);
        if (!nw) { o->oom = 1; return; }
        o->w = nw;
        uint8_t *nk = (uint8_t *)realloc(o->k, 2 * (size_t)cap);
        if (!nk) { o->oom = 1; return; }
        o->k = nk;
        o->cap_pts = cap;
    }
    memcpy(o->xy + 2 * o->npts, xy, sizeof(double) * 2 * (size_t)n);
    memcpy(o->w + o->npts, w, sizeof(double) * (size_t)n);
    if (k) memcpy(o->k + 2 * o->npts, k, 2 * (size_t)n);
    else memset(o->k + 2 * o->npts, 0, 2 * (size_t)n);
    o->counts[o->n] = n; o->src[o->n] = src; o->n++; o->npts += n;
}

/* the kinds of point t of stroke i, or NULL when the input carries none */
static const uint8_t *pkind_of(const ctx *C, int32_t i, int32_t t) {
    return C->in->pkind ? C->in->pkind + 2 * (C->start[i] + t) : NULL;
}

/* ---- the join of one group (one color, tool, pen color and width): its chains in the Python's order. Groups share
 * nothing they write (a stroke is in one group; the cover is read-only by now), so groups run on any thread and each
 * keeps its chains in its own buffer until they are concatenated in group order. */
/* a growable int32 buffer, kept by a worker from candidate to candidate */
typedef struct { int32_t *p; size_t cap; } ibuf;
#define NBUF 10
typedef struct {
    rf_scratch S; chain_t ch; cand *best; int32_t cbest; int32_t *near; int32_t cnear;
    ibuf b[NBUF];                    /* the candidate test's sets: no allocation per candidate once grown */
    uint16_t *mine; size_t cap_mine;
} worker;

/* room for n entries in b; NULL (and the oom flag) when memory ran out */
static int32_t *ibuf_room(const ctx *C, ibuf *b, size_t n) {
    if (n > b->cap) {
        size_t c2 = n > 2 * b->cap ? n : 2 * b->cap;
        int32_t *q = (int32_t *)realloc(b->p, sizeof(int32_t) * (c2 ? c2 : 1));
        if (!q) { atomic_store(C->oom, 1); return NULL; }
        b->p = q; b->cap = c2;
    }
    return b->p;
}

/* a footprint into the worker's buffer b (valid until b is used again) */
static iset fp_buf(const ctx *C, rf_scratch *S, ibuf *b, const double *xy, const double *w, int32_t npts, double eps) {
    iset s = {NULL, 0};
    int32_t n = rf_wash_pixels_buf(xy, w, npts, C->ox, C->oy, C->W, C->H, eps, S, &b->p, &b->cap);
    if (n < 0) { atomic_store(C->oom, 1); return s; }
    s.idx = b->p; s.n = n;
    return s;
}

/* rm_lean._others_dark, with the worker's count buffer */
static int others_dark_w(const ctx *C, worker *T, const uint8_t *m, const uint16_t *c, size_t N, const int32_t *pix, int32_t n, const int col[3],
                         const iset *own1, const iset *own2) {
    if (!n) return 1;
    if ((size_t)n > T->cap_mine) {
        uint16_t *q = (uint16_t *)realloc(T->mine, sizeof(uint16_t) * (size_t)n);
        if (!q) { atomic_store(C->oom, 1); return 0; }
        T->mine = q; T->cap_mine = (size_t)n;
    }
    uint16_t *mine = T->mine;
    memset(mine, 0, sizeof(uint16_t) * (size_t)n);
    rf_isin_add(pix, n, own1->idx, own1->n, mine);
    rf_isin_add(pix, n, own2->idx, own2->n, mine);
    for (int k = 0; k < 3; k++) {
        const uint8_t *mk = m + k * N;
        const uint16_t *ck = c + k * N;
        uint8_t v = (uint8_t)col[k];
        for (int32_t t = 0; t < n; t++) {
            uint8_t mv = mk[pix[t]];
            if (mv > v || (mv == v && ck[pix[t]] <= mine[t])) return 0;
        }
    }
    return 1;
}

typedef struct {
    ctx *C; grp *groups; int32_t ng; int32_t *order;
    double radius, radius_w; int32_t max_points;
    endcache *E; uint8_t *left, *innear;
    outbuf *outs; int32_t *joins;
    double *gsecs;                   /* each group's join time (bench: the longest bounds the join) */
    worker *W; atomic_int next;
} joinjob;

/* The candidate test: may the chain (its last two points in ch, ending at cur's tail end `cur_tail`) take j, entered
 * from its end `rev`? The joined piece must leave every pixel as it was under both rules. Reads the cover, the chain
 * and the end footprints; writes the worker's buffers and the two end footprints the first time they are asked for. */
static int join_ok(const ctx *C, worker *T, endcache *E, const chain_t *ch, int32_t cur, int cur_tail, int32_t j, int rev, const int col[3]) {
    const rf_strokes *in = C->in;
    size_t N = (size_t)C->W * C->H;
    const double *sj = in->xy + 2 * C->start[j]; const double *wj = in->w + C->start[j];
    int32_t nj = in->counts[j];
    /* the joined piece: the chain's last two points, then j's first two (in j's chosen direction) */
    double jx[8], jw[4];
    jx[0] = ch->xy[2 * (ch->n - 2)]; jx[1] = ch->xy[2 * (ch->n - 2) + 1]; jw[0] = ch->w[ch->n - 2];
    jx[2] = ch->xy[2 * (ch->n - 1)]; jx[3] = ch->xy[2 * (ch->n - 1) + 1]; jw[1] = ch->w[ch->n - 1];
    int32_t b0 = rev ? nj - 1 : 0, b1 = rev ? nj - 2 : 1;
    jx[4] = sj[2 * b0]; jx[5] = sj[2 * b0 + 1]; jw[2] = wj[b0];
    jx[6] = sj[2 * b1]; jx[7] = sj[2 * b1 + 1]; jw[3] = wj[b1];
    /* the sets of this test live in the worker's buffers b[0..9] (one buffer each); under both rules the joined
       piece's three footprints (eo, -EPS, +EPS) come from one painting */
    iset nw_ = {NULL, 0}, j_sure = {NULL, 0}, j_tie = {NULL, 0};
    if (C->wide) {
        const double ee[3] = {C->eo, -RF_EPS, RF_EPS};
        int32_t *bufs[3] = {T->b[0].p, T->b[2].p, T->b[4].p}, cn[3];
        size_t caps[3] = {T->b[0].cap, T->b[2].cap, T->b[4].cap};
        if (rf_wash_pixels_multi(jx, jw, 4, C->ox, C->oy, C->W, C->H, ee, 3, &T->S, bufs, caps, cn)) {
            atomic_store(C->oom, 1);
            cn[0] = cn[1] = cn[2] = 0;
        }
        T->b[0].p = bufs[0]; T->b[0].cap = caps[0]; T->b[2].p = bufs[1]; T->b[2].cap = caps[1]; T->b[4].p = bufs[2]; T->b[4].cap = caps[2];
        nw_.idx = bufs[0]; nw_.n = cn[0]; j_sure.idx = bufs[1]; j_sure.n = cn[1]; j_tie.idx = bufs[2]; j_tie.n = cn[2];
    } else nw_ = fp_buf(C, &T->S, &T->b[0], jx, jw, 4, C->eo);
    iset *es1 = end_fp(C, &T->S, E, cur, cur_tail, E_SURE), *es2 = end_fp(C, &T->S, E, j, rev, E_SURE);
    int32_t *e_sure = ibuf_room(C, &T->b[1], (size_t)es1->n + es2->n);
    int32_t ne = e_sure ? rf_union_to(es1->idx, es1->n, es2->idx, es2->n, e_sure) : 0;
    if (!C->wide) {
        iset *ep1 = end_fp(C, &T->S, E, cur, cur_tail, E_WIDE), *ep2 = end_fp(C, &T->S, E, j, rev, E_WIDE);
        int32_t *e_poss = ibuf_room(C, &T->b[2], (size_t)ep1->n + ep2->n);
        int32_t np_ = e_poss ? rf_union_to(ep1->idx, ep1->n, ep2->idx, ep2->n, e_poss) : 0;
        int32_t *miss = ibuf_room(C, &T->b[3], (size_t)np_);
        int32_t nm = miss ? rf_setdiff_to(e_poss, np_, nw_.idx, nw_.n, miss) : 0;
        if (nm) return 0;
        int32_t *extra = ibuf_room(C, &T->b[4], (size_t)nw_.n);
        int32_t nx = extra ? rf_setdiff_to(nw_.idx, nw_.n, e_sure, ne, extra) : 0;
        return all_free(C->m1, N, extra, nx, col);
    }
    iset *et1 = end_fp(C, &T->S, E, cur, cur_tail, E_TIE), *et2 = end_fp(C, &T->S, E, j, rev, E_TIE);
    int32_t *e_tie = ibuf_room(C, &T->b[3], (size_t)et1->n + et2->n);
    int32_t nt = e_tie ? rf_union_to(et1->idx, et1->n, et2->idx, et2->n, e_tie) : 0;
    int32_t *u1 = ibuf_room(C, &T->b[5], (size_t)nt + j_tie.n);
    int32_t nu1 = u1 ? rf_union_to(e_tie, nt, j_tie.idx, j_tie.n, u1) : 0;
    int32_t *both = ibuf_room(C, &T->b[6], (size_t)(ne < j_sure.n ? ne : j_sure.n));
    int32_t ni = both ? rf_intersect_to(e_sure, ne, j_sure.idx, j_sure.n, both) : 0;
    int32_t *u_exact = ibuf_room(C, &T->b[7], (size_t)nu1);
    int32_t nue = u_exact ? rf_setdiff_to(u1, nu1, both, ni, u_exact) : 0;
    if (!others_dark_w(C, T, C->m1, C->c1, N, u_exact, nue, col, es1, es2)) return 0;
    iset *ew1 = end_fp(C, &T->S, E, cur, cur_tail, E_WIDE), *ew2 = end_fp(C, &T->S, E, j, rev, E_WIDE);
    int32_t *e_wide = ibuf_room(C, &T->b[8], (size_t)ew1->n + ew2->n);
    int32_t nwd = e_wide ? rf_union_to(ew1->idx, ew1->n, ew2->idx, ew2->n, e_wide) : 0;
    int32_t *xr = ibuf_room(C, &T->b[9], (size_t)nwd + nw_.n);
    int32_t nx = xr ? rf_setxor_to(e_wide, nwd, nw_.idx, nw_.n, xr) : 0;
    return others_dark_w(C, T, C->m2, C->c2, N, xr, nx, col, ew1, ew2);
}

static void join_group(joinjob *J, worker *T, int32_t g) {
    ctx *C = J->C;
    const rf_strokes *in = C->in;
    endcache *E = J->E;
    uint8_t *left = J->left, *innear = J->innear;
    grp *G = &J->groups[g];
    double cell = J->radius; { double rw = J->radius_w * G->w0; if (rw > cell) cell = rw; }
    bmap M; memset(&M, 0, sizeof(M));
    for (int32_t t = 0; t < G->n; t++) {
        int32_t i = G->idx[t];
        const double *p0 = in->xy + 2 * C->start[i], *p1 = in->xy + 2 * (C->start[i] + in->counts[i] - 1);
        if (bucket_add(bmap_get(&M, bucket_key(p0[0], kind_of(in, i, 0, 0), cell), bucket_key(p0[1], kind_of(in, i, 0, 1), cell), 1), i)
                || bucket_add(bmap_get(&M, bucket_key(p1[0], kind_of(in, i, 1, 0), cell), bucket_key(p1[1], kind_of(in, i, 1, 1), cell), 1), i))
            atomic_store(C->oom, 1);
        left[i] = 1;
    }
    sortkey *order = (sortkey *)malloc(sizeof(sortkey) * (G->n ? G->n : 1));
    if (!order || atomic_load(C->oom)) {
        atomic_store(C->oom, 1);
        free(order);
        for (size_t t = 0; t < M.cap; t++) if (M.b[t].n >= 0) free(M.b[t].idx);
        free(M.b);
        return;
    }
    for (int32_t t = 0; t < G->n; t++) { int32_t i = G->idx[t]; order[t].i = i; order[t].x = in->xy[2 * C->start[i]]; order[t].y = in->xy[2 * C->start[i] + 1]; order[t].ord = t; }
    qsort(order, G->n, sizeof(sortkey), cmp_sortkey);
    chain_t *ch = &T->ch;
    for (int32_t t = 0; t < G->n; t++) {
        int32_t i = order[t].i;
        if (!left[i]) continue;
        left[i] = 0;
        int col[3]; rgb_of(in, i, col);
        ch->n = 0;
        for (int32_t k = 0; k < in->counts[i]; k++) chain_push(ch, in->xy[2 * (C->start[i] + k)], in->xy[2 * (C->start[i] + k) + 1], in->w[C->start[i] + k], pkind_of(C, i, k));
        int32_t cur = i; int cur_tail = 1;
        while (ch->n < J->max_points) {
            double ex = ch->xy[2 * (ch->n - 1)], ey = ch->xy[2 * (ch->n - 1) + 1];
            /* the chain ends with cur's last point (cur_tail) or its first (cur appended reversed) */
            int kex = kind_of(in, cur, cur_tail, 0), key = kind_of(in, cur, cur_tail, 1);
            int64_t cx = bucket_key(ex, kex, cell), cy = bucket_key(ey, key, cell);
            int32_t nn = 0;
            for (int dx = -1; dx <= 1; dx++) for (int dy = -1; dy <= 1; dy++) {
                bucket *b = bmap_get(&M, cx + dx, cy + dy, 0);
                if (!b) continue;
                for (int32_t u = 0; u < b->n; u++) {
                    int32_t j = b->idx[u];
                    if (!left[j] || innear[j]) continue;
                    innear[j] = 1;
                    if (nn == T->cnear) {
                        int32_t cap = T->cnear ? T->cnear * 2 : 64;
                        int32_t *q = (int32_t *)realloc(T->near, sizeof(int32_t) * (size_t)cap);
                        if (!q) { atomic_store(C->oom, 1); innear[j] = 0; continue; }
                        T->near = q; T->cnear = cap;
                    }
                    T->near[nn++] = j;
                }
            }
            int32_t nb = 0;
            for (int32_t u = 0; u < nn; u++) {
                int32_t j = T->near[u];
                innear[j] = 0;
                const double *sj = in->xy + 2 * C->start[j];
                int32_t nj = in->counts[j];
                for (int rev = 0; rev < 2; rev++) {
                    double bx = rev ? sj[2 * (nj - 1)] : sj[0], by = rev ? sj[2 * (nj - 1) + 1] : sj[1];
                    double d = join_dist(bx, by, kind_of(in, j, rev, 0), kind_of(in, j, rev, 1), ex, ey, kex, key);
                    if (d <= cell) {
                        if (nb == T->cbest) {
                            int32_t cap = T->cbest ? T->cbest * 2 : 64;
                            cand *q = (cand *)realloc(T->best, sizeof(cand) * (size_t)cap);
                            if (!q) { atomic_store(C->oom, 1); continue; }
                            T->best = q; T->cbest = cap;
                        }
                        T->best[nb].d = d; T->best[nb].j = j; T->best[nb].rev = rev; nb++;
                    }
                }
            }
            qsort(T->best, nb, sizeof(cand), cmp_cand);
            int32_t pick = -1;
            for (int32_t u = 0; u < nb; u++) if (join_ok(C, T, E, ch, cur, cur_tail, T->best[u].j, T->best[u].rev, col)) { pick = u; break; }
            if (pick < 0) break;
            int32_t j = T->best[pick].j; int rev = T->best[pick].rev;
            const double *sj = in->xy + 2 * C->start[j]; const double *wj = in->w + C->start[j];
            int32_t nj = in->counts[j];
            if (rev) for (int32_t k = nj - 1; k >= 0; k--) chain_push(ch, sj[2 * k], sj[2 * k + 1], wj[k], pkind_of(C, j, k));
            else for (int32_t k = 0; k < nj; k++) chain_push(ch, sj[2 * k], sj[2 * k + 1], wj[k], pkind_of(C, j, k));
            left[j] = 0;
            J->joins[g]++;
            cur = j; cur_tail = !rev;
        }
        if (ch->oom) J->outs[g].oom = 1;
        out_add(&J->outs[g], ch->xy, ch->w, ch->k, ch->n, i);
    }
    free(order);
    for (size_t t = 0; t < M.cap; t++) if (M.b[t].n >= 0) free(M.b[t].idx);
    free(M.b);
}

static void join_worker(void *arg, int tid) {
    joinjob *J = (joinjob *)arg;
    for (;;) {
        int32_t k = atomic_fetch_add(&J->next, 1);
        if (k >= J->ng) break;
        double t0 = rf_now();
        join_group(J, &J->W[tid], J->order[k]);
        J->gsecs[J->order[k]] = rf_now() - t0;
    }
}

typedef struct { int32_t g, n; } gsize;
static int cmp_gsize(const void *a, const void *b) {         /* biggest group first, then group order */
    const gsize *x = (const gsize *)a, *y = (const gsize *)b;
    if (x->n != y->n) return x->n > y->n ? -1 : 1;
    return x->g < y->g ? -1 : (x->g > y->g);
}

static double PT_[4];      /* cover, drops, join, the longest group's join (bench timers) */
RF_API void rf_pass_timers(double *out, int reset) { for (int i = 0; i < 4; i++) { out[i] = PT_[i]; if (reset) PT_[i] = 0.0; } }

RF_API int rf_prune_join(const rf_strokes *in, double eps_out, double radius, double radius_w, int32_t max_points, rf_result *out) {
    memset(out, 0, sizeof(*out));
    if (in->n <= 0) return 0;
    atomic_int oom;
    atomic_init(&oom, 0);
    ctx C; memset(&C, 0, sizeof(C));
    C.in = in;
    C.oom = &oom;
    outbuf O; memset(&O, 0, sizeof(O));
    int32_t *wash = NULL, *single = NULL, *pens = NULL, nwash = 0, nsingle = 0, npens = 0;
    int32_t joins = 0, npruned = 0;
    C.start = (int64_t *)malloc(sizeof(int64_t) * ((size_t)in->n + 1));
    if (!C.start) { atomic_store(&oom, 1); goto release; }
    C.start[0] = 0;
    for (int32_t i = 0; i < in->n; i++) C.start[i + 1] = C.start[i] + in->counts[i];
    C.wide = eps_out >= 0.0;
    C.eo = C.wide ? (eps_out > RF_EPS ? eps_out : RF_EPS) : RF_EPS;
    grid_of(&C);
    double t0 = rf_now();
    cover(&C);
    if (atomic_load(&oom)) goto release;
    double t1 = rf_now();
    drops(&C);
    if (atomic_load(&oom)) goto release;
    double t2 = rf_now();
    PT_[0] += t1 - t0; PT_[1] += t2 - t1;
    for (int32_t i = 0; i < in->n; i++) npruned += C.drop[i];
    /* keep, in order: joinable washes (>= 2 points, one width), the other washes, the pens */
    wash = (int32_t *)malloc(sizeof(int32_t) * (size_t)in->n);
    single = (int32_t *)malloc(sizeof(int32_t) * (size_t)in->n);
    pens = (int32_t *)malloc(sizeof(int32_t) * (size_t)in->n);
    if (!wash || !single || !pens) { atomic_store(&oom, 1); goto release; }
    for (int32_t i = 0; i < in->n; i++) {
        if (C.drop[i]) continue;
        if (!in->wash[i]) { pens[npens++] = i; continue; }
        int one = in->counts[i] >= 2;
        if (one) {
            double lo = in->w[C.start[i]], hi = lo;
            for (int32_t k = 1; k < in->counts[i]; k++) { double v = in->w[C.start[i] + k]; if (v < lo) lo = v; if (v > hi) hi = v; }
            one = (lo == hi);
        }
        if (one) wash[nwash++] = i; else single[nsingle++] = i;
    }
    if (nwash) {
        /* groups in first-appearance order */
        grp *groups = NULL; int32_t ng = 0, cg = 0;
        for (int32_t t = 0; t < nwash && !atomic_load(&oom); t++) {
            int32_t i = wash[t];
            int64_t key = in->group[i]; double w0 = in->w[C.start[i]];
            int32_t g = -1;
            for (int32_t u = ng - 1; u >= 0; u--) if (groups[u].key == key && groups[u].w0 == w0) { g = u; break; }
            if (g < 0) {
                if (ng == cg) {
                    int32_t cap = cg ? cg * 2 : 64;
                    grp *q = (grp *)realloc(groups, sizeof(grp) * (size_t)cap);
                    if (!q) { atomic_store(&oom, 1); break; }
                    groups = q; cg = cap;
                }
                groups[ng].key = key; groups[ng].w0 = w0; groups[ng].idx = NULL; groups[ng].n = 0; groups[ng].cap = 0;
                g = ng++;
            }
            grp *G = &groups[g];
            if (G->n == G->cap) {
                int32_t cap = G->cap ? G->cap * 2 : 16;
                int32_t *q = (int32_t *)realloc(G->idx, sizeof(int32_t) * (size_t)cap);
                if (!q) { atomic_store(&oom, 1); break; }
                G->idx = q; G->cap = cap;
            }
            G->idx[G->n++] = i;
        }
        endcache *E = (endcache *)calloc((size_t)in->n, sizeof(endcache));
        uint8_t *left = (uint8_t *)calloc((size_t)in->n, 1);
        uint8_t *innear = (uint8_t *)calloc((size_t)in->n, 1);
        /* the groups on all threads, biggest first; each group's chains in its own buffer, joined in group order */
        joinjob J; memset(&J, 0, sizeof(J));
        J.C = &C; J.groups = groups; J.ng = ng; J.radius = radius; J.radius_w = radius_w; J.max_points = max_points;
        J.E = E; J.left = left; J.innear = innear;
        J.outs = (outbuf *)calloc((size_t)(ng ? ng : 1), sizeof(outbuf));
        J.joins = (int32_t *)calloc((size_t)(ng ? ng : 1), sizeof(int32_t));
        J.gsecs = (double *)calloc((size_t)(ng ? ng : 1), sizeof(double));
        gsize *gs = (gsize *)malloc(sizeof(gsize) * (size_t)(ng ? ng : 1));
        J.order = (int32_t *)malloc(sizeof(int32_t) * (size_t)(ng ? ng : 1));
        int nt = rf_threads();
        if (nt > ng) nt = ng;
        if (nt < 1) nt = 1;
        J.W = (worker *)calloc((size_t)nt, sizeof(worker));
        if (!E || !left || !innear || !J.outs || !J.joins || !J.gsecs || !gs || !J.order || !J.W) atomic_store(&oom, 1);
        if (!atomic_load(&oom)) {
            for (int32_t g = 0; g < ng; g++) { gs[g].g = g; gs[g].n = groups[g].n; }
            qsort(gs, ng, sizeof(gsize), cmp_gsize);
            for (int32_t g = 0; g < ng; g++) J.order[g] = gs[g].g;
            atomic_init(&J.next, 0);
            rf_parallel(nt, join_worker, &J);
            double longest = 0.0;
            for (int32_t g = 0; g < ng; g++) if (J.gsecs[g] > longest) longest = J.gsecs[g];
            PT_[3] += longest;
            for (int32_t g = 0; g < ng; g++) {
                outbuf *B = &J.outs[g];
                int64_t k = 0;
                if (B->oom) O.oom = 1;
                for (int32_t t = 0; t < B->n; t++) { out_add(&O, B->xy + 2 * k, B->w + k, B->k + 2 * k, B->counts[t], B->src[t]); k += B->counts[t]; }
                joins += J.joins[g];
            }
        }
        free(gs);
        if (J.outs) for (int32_t g = 0; g < ng; g++) { outbuf *B = &J.outs[g]; free(B->counts); free(B->src); free(B->xy); free(B->w); free(B->k); }
        if (J.W) for (int t = 0; t < nt; t++) {
            rf_scratch_free(&J.W[t].S); free(J.W[t].ch.xy); free(J.W[t].ch.w); free(J.W[t].ch.k); free(J.W[t].best); free(J.W[t].near);
            for (int b = 0; b < NBUF; b++) free(J.W[t].b[b].p);
            free(J.W[t].mine);
        }
        free(J.W); free(J.outs); free(J.joins); free(J.order); free(J.gsecs);
        if (E) for (int32_t i = 0; i < in->n; i++) for (int a = 0; a < 2; a++) for (int b = 0; b < 3; b++) if (E[i].have[a][b]) iset_free(&E[i].s[a][b]);
        free(E); free(left); free(innear);
        for (int32_t g = 0; g < ng; g++) free(groups[g].idx);
        free(groups);
        if (atomic_load(&oom)) goto release;
    }
    PT_[2] += rf_now() - t2;
    for (int32_t t = 0; t < nsingle; t++) { int32_t i = single[t]; out_add(&O, in->xy + 2 * C.start[i], in->w + C.start[i], pkind_of(&C, i, 0), in->counts[i], i); }
    for (int32_t t = 0; t < npens; t++) { int32_t i = pens[t]; out_add(&O, in->xy + 2 * C.start[i], in->w + C.start[i], pkind_of(&C, i, 0), in->counts[i], i); }
release:
    out->n = O.n; out->counts = O.counts; out->xy = O.xy; out->w = O.w; out->src = O.src; out->pkind = O.k; out->pruned = npruned; out->joins = joins;
    free(wash); free(single); free(pens);
    if (C.sure && C.poss) for (int32_t i = 0; i < in->n; i++) { if (C.poss[i].idx != C.sure[i].idx) iset_free(&C.poss[i]); iset_free(&C.sure[i]); }
    free(C.sure); free(C.poss); free(C.drop); free(C.m1); free(C.c1); free(C.m2); free(C.c2); free(C.start);
    rf_scratch_free(&C.S);
    if (O.oom || atomic_load(&oom)) { rf_result_free(out); return -1; }
    return 0;
}
RF_API void rf_result_free(rf_result *r) {
    free(r->counts); free(r->xy); free(r->w); free(r->src); free(r->pkind);
    memset(r, 0, sizeof(*r));
}
