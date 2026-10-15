/* store.c -- the painter's strokes, held in C from the ring planner to the lossless pass (GEOMETRY code: it makes and
 * moves stroke points, widths and the extent).
 *
 * The planner's output used to become Python tuples of numpy scalars (11 M points on a painting), which the painter
 * then walked for its extent and rmfast.Packed walked again for the seam and the pass. Here the points stay in C and
 * Python objects are made once, for what the pass keeps. What each function reproduces, bit for bit:
 *   rf_store_fill(_batch) rmb_geometry.fill: the ring plan (plan.c rf_plan) placed onto the page (rm_trace.place),
 *                         float32 points where the Python's are numpy.float32 (a simplified loop), float64 otherwise;
 *                         the width field (rm_paint._hl_field / _field) and pen (FINELINER_2 when w <= the fineliner
 *                         maximum). The batch runs the zones' plans on all threads, each into its own slot, and appends
 *                         them in job order: the same strokes in the same order as one call per zone.
 *   rf_store_wash_first   the end of rm_paint.decompose (SUBCELL_GEOMETRY): washes grouped by tuple(rgba), groups in
 *                         first-appearance order and each in stroke order, then every other stroke in order.
 *   rf_store_extent       decompose's extent: Python's min() and max() over x -/+ half the pen width (and y), each
 *                         value and each comparison in the scalar type the Python holds -- NumPy 2 (NEP 50) adds a
 *                         Python float to a numpy.float32 in float32 and compares the two in float32, while a
 *                         numpy.float64 meets either in double. min() keeps the first item and replaces it with each
 *                         later one that compares smaller, which with mixed kinds is not order-free, so the scan is
 *                         the Python's own sequence.
 *   rf_store_select       rm_model.run's wash / rest split (rm_lean.is_wash).
 *   gather (rf_store_seam, rf_store_prune_join) rmfast.Packed: the contiguous stroke list rf_seam and rf_prune_join
 *                         read -- rgb (255, 237, 117 for no rgba), group keys numbered by first appearance of
 *                         (rgb, tool, pen color), the scalar kinds of each stroke's first and last point -- plus every
 *                         point's kinds, which the pass carries into its output.
 * Identity: checked against the reference (every coordinate's and width's Python type and value against the pure-Python model)
 * and the reference corpus check; the port's log has the runs. */
#include <stdatomic.h>
#include <stdlib.h>
#include <string.h>
#include "rmfast.h"
#include "internal.h"

typedef struct { int32_t tool, color, rgb[3], rgba_key; uint8_t wash, has_rgb; } style_t;

struct rf_store {
    int32_t n, cap;                 /* strokes */
    int64_t *start;                 /* each stroke's first point */
    int32_t *count, *style, *pyref;
    int64_t npts, cap_pts;          /* points */
    double *xy, *w;
    uint8_t *kind;                  /* two per point: the RF_KIND_* of x and of y */
    int32_t nst, cap_st;            /* styles */
    style_t *st;
    int32_t max_rgba_key;
    int32_t *by_style, *by_rgb;     /* open-addressed style ids of the styles with an rgba: by (tool, pen color, wash,
                                       rgb), and by rgb alone (the first style of each rgba, which holds its key) */
    size_t tab_cap;
};

RF_API rf_store *rf_store_new(void) {
    rf_store *S = (rf_store *)calloc(1, sizeof(rf_store));
    if (S) S->max_rgba_key = -1;
    return S;
}

RF_API void rf_store_free(rf_store *S) {
    if (!S) return;
    free(S->start); free(S->count); free(S->style); free(S->pyref);
    free(S->xy); free(S->w); free(S->kind); free(S->st); free(S->by_style); free(S->by_rgb);
    free(S);
}

RF_API int32_t rf_store_count(const rf_store *S) { return S->n; }

RF_API void rf_store_arrays(const rf_store *S, const int32_t **count, const int32_t **style, const int32_t **pyref) {
    *count = S->count; *style = S->style; *pyref = S->pyref;
}

/* room for `need` strokes / points. Each array is grown on its own; the shared capacity moves only when all have,
 * so a failure leaves the store as it was (an array that did grow just has spare room). */
static int reserve_strokes(rf_store *S, int64_t need) {
    if (need <= S->cap) return 0;
    if (need > INT32_MAX) return -1;
    int64_t c = S->cap ? S->cap : 4096;
    while (c < need) c *= 2;
    if (c > INT32_MAX) c = INT32_MAX;
    void *p;
    if (!(p = realloc(S->start, (size_t)c * sizeof(int64_t)))) return -1;
    S->start = (int64_t *)p;
    if (!(p = realloc(S->count, (size_t)c * sizeof(int32_t)))) return -1;
    S->count = (int32_t *)p;
    if (!(p = realloc(S->style, (size_t)c * sizeof(int32_t)))) return -1;
    S->style = (int32_t *)p;
    if (!(p = realloc(S->pyref, (size_t)c * sizeof(int32_t)))) return -1;
    S->pyref = (int32_t *)p;
    S->cap = (int32_t)c;
    return 0;
}

static int reserve_points(rf_store *S, int64_t need) {
    if (need <= S->cap_pts) return 0;
    int64_t c = S->cap_pts ? S->cap_pts : 65536;
    while (c < need) c *= 2;
    void *p;
    if (!(p = realloc(S->xy, (size_t)c * 2 * sizeof(double)))) return -1;
    S->xy = (double *)p;
    if (!(p = realloc(S->w, (size_t)c * sizeof(double)))) return -1;
    S->w = (double *)p;
    if (!(p = realloc(S->kind, (size_t)c * 2))) return -1;
    S->kind = (uint8_t *)p;
    S->cap_pts = c;
    return 0;
}

static int32_t new_style(rf_store *S, int32_t tool, int32_t color, int32_t r, int32_t g, int32_t b, int32_t wash, int32_t rgba_key,
                         int has_rgb) {
    if (S->nst == S->cap_st) {
        if (S->cap_st > INT32_MAX / 2) return -1;
        int32_t c = S->cap_st ? S->cap_st * 2 : 256;
        style_t *p = (style_t *)realloc(S->st, (size_t)c * sizeof(style_t));
        if (!p) return -1;
        S->st = p; S->cap_st = c;
    }
    style_t *s = &S->st[S->nst];
    s->tool = tool; s->color = color; s->rgb[0] = r; s->rgb[1] = g; s->rgb[2] = b; s->rgba_key = rgba_key; s->wash = wash != 0;
    s->has_rgb = (uint8_t)(has_rgb != 0);
    if (rgba_key > S->max_rgba_key) S->max_rgba_key = rgba_key;
    return S->nst++;
}

/* a style without an rgba (the Python's None): registered as given, rgba_key -1 */
RF_API int32_t rf_store_style(rf_store *S, int32_t tool, int32_t color, int32_t r, int32_t g, int32_t b, int32_t wash, int32_t rgba_key) {
    return new_style(S, tool, color, r, g, b, wash, rgba_key, 0);
}

static uint64_t style_hash(int32_t tool, int32_t color, int32_t wash, const int32_t *rgb, int full) {
    uint64_t h = 1469598103934665603ULL;
    int32_t f[6] = {rgb[0], rgb[1], rgb[2], tool, color, wash};
    for (int i = 0; i < (full ? 6 : 3); i++) { h ^= (uint32_t)f[i]; h *= 1099511628211ULL; }
    return h;
}

static int same_rgb(const style_t *a, const int32_t *rgb) { return a->rgb[0] == rgb[0] && a->rgb[1] == rgb[1] && a->rgb[2] == rgb[2]; }

/* the slot of (tool, color, wash, rgb) in by_style (full) or of rgb in by_rgb: the matching entry, or the empty slot */
static size_t style_slot(const rf_store *S, const int32_t *tab, int32_t tool, int32_t color, int32_t wash, const int32_t *rgb, int full) {
    size_t m = S->tab_cap - 1, slot = (size_t)(style_hash(tool, color, wash, rgb, full) & m);
    for (;;) {
        int32_t o = tab[slot];
        if (o < 0) return slot;
        const style_t *a = &S->st[o];
        if (same_rgb(a, rgb) && (!full || (a->tool == tool && a->color == color && (int32_t)a->wash == wash))) return slot;
        slot = (slot + 1) & m;
    }
}

/* both tables at least twice the styles with an rgba (rebuilt when they grow); 0, or -1 out of memory */
static int style_tables(rf_store *S, size_t need) {
    if (S->tab_cap >= 2 * need + 2) return 0;
    size_t cap = S->tab_cap ? S->tab_cap : 1024;
    while (cap < 2 * need + 2) cap *= 2;
    int32_t *a = (int32_t *)malloc(cap * sizeof(int32_t)), *b = (int32_t *)malloc(cap * sizeof(int32_t));
    if (!a || !b) { free(a); free(b); return -1; }
    for (size_t i = 0; i < cap; i++) a[i] = b[i] = -1;
    free(S->by_style); free(S->by_rgb);
    S->by_style = a; S->by_rgb = b; S->tab_cap = cap;
    for (int32_t s = 0; s < S->nst; s++) {
        const style_t *st = &S->st[s];
        if (!st->has_rgb) continue;
        size_t k = style_slot(S, S->by_style, st->tool, st->color, st->wash, st->rgb, 1);
        if (S->by_style[k] < 0) S->by_style[k] = s;
        k = style_slot(S, S->by_rgb, st->tool, st->color, st->wash, st->rgb, 0);
        if (S->by_rgb[k] < 0) S->by_rgb[k] = s;
    }
    return 0;
}

/* the style of (tool, pen color, wash) with the rgba (r, g, b) -- a tuple of three Python ints -- found or registered.
 * Its rgba key is the one every style with that rgba shares, numbered by first registration: the Python's dict of
 * tuple(rgba), which groups the washes. -> the style id, or -1 out of memory. */
RF_API int32_t rf_store_style_rgb(rf_store *S, int32_t tool, int32_t color, int32_t r, int32_t g, int32_t b, int32_t wash) {
    int32_t rgb[3] = {r, g, b};
    wash = wash != 0;
    if (style_tables(S, (size_t)S->nst + 1)) return -1;
    size_t ks = style_slot(S, S->by_style, tool, color, wash, rgb, 1);
    if (S->by_style[ks] >= 0) return S->by_style[ks];
    size_t kr = style_slot(S, S->by_rgb, tool, color, wash, rgb, 0);
    int32_t key = S->by_rgb[kr] >= 0 ? S->st[S->by_rgb[kr]].rgba_key : S->max_rgba_key + 1;
    int32_t sid = new_style(S, tool, color, r, g, b, wash, key, 1);
    if (sid < 0) return -1;
    S->by_style[ks] = sid;
    if (S->by_rgb[kr] < 0) S->by_rgb[kr] = sid;
    return sid;
}

/* styles first .. count - 1 as 7 ints each: tool, pen color, r, g, b, whether it has an rgba, the wash flag (the Python
 * face makes the objects of the styles registered here); out has room for 7 * (count - first) -> how many */
RF_API int32_t rf_store_styles(const rf_store *S, int32_t first, int32_t *out) {
    if (first < 0) return -1;
    for (int32_t s = first; s < S->nst; s++) {
        const style_t *st = &S->st[s];
        int32_t *o = out + 7 * (size_t)(s - first);
        o[0] = st->tool; o[1] = st->color; o[2] = st->rgb[0]; o[3] = st->rgb[1]; o[4] = st->rgb[2]; o[5] = st->has_rgb; o[6] = st->wash;
    }
    return S->nst > first ? S->nst - first : 0;
}

RF_API int32_t rf_store_style_count(const rf_store *S) { return S->nst; }

/* ------------------------------------------------------------------ the planner's strokes */
typedef struct {
    double ox, oy, scale, hl_scale, pen_scale, fineliner_max;
} placement;

/* append one plan's paths (rmb_geometry.fill's loop); frees the paths */
static int32_t append_paths(rf_store *S, rf_path *paths, int32_t np_, const placement *P, int32_t offx, int32_t offy, int flat,
                            int32_t st_wash, int32_t st_fine, int32_t st_marker) {
    int64_t total = 0;
    for (int32_t i = 0; i < np_; i++) total += paths[i].n;
    int bad = reserve_strokes(S, (int64_t)S->n + np_) || reserve_points(S, S->npts + total);
    for (int32_t i = 0; i < np_; i++) {
        rf_path *p = &paths[i];
        if (!bad) {
            int32_t s = S->n++;
            S->start[s] = S->npts; S->count[s] = p->n; S->pyref[s] = -1;
            rf_place_path(p, P->ox, P->oy, P->scale, offx, offy, S->xy + 2 * S->npts);
            memset(S->kind + 2 * S->npts, p->f32 ? RF_KIND_F32 : RF_KIND_F64, 2 * (size_t)p->n);
            int32_t field, pen;
            rf_path_field(p, flat, P->hl_scale, P->pen_scale, P->fineliner_max, &field, &pen);
            for (int32_t t = 0; t < p->n; t++) S->w[S->npts + t] = (double)field;
            S->style[s] = flat ? st_wash : (pen == 1 ? st_fine : st_marker);
            S->npts += p->n;
        }
        free(p->xy);
    }
    free(paths);
    return bad ? -1 : np_;
}

RF_API int32_t rf_store_fill(rf_store *S, const uint8_t *mask, int32_t h, int32_t w, double ppg, int32_t flat, double max_page,
                             double x0, double y0, double x1, double y1, int32_t offx, int32_t offy, int32_t gw, int32_t gh,
                             double hl_scale, double pen_scale, double fineliner_max, int32_t st_wash, int32_t st_fine, int32_t st_marker) {
    rf_path *paths;
    int32_t np_ = rf_plan(mask, h, w, ppg, flat, max_page, &paths);
    if (np_ <= 0) return np_;
    placement P;
    rf_place_frame(x0, y0, x1, y1, gw, gh, &P.ox, &P.oy, &P.scale);
    P.hl_scale = hl_scale; P.pen_scale = pen_scale; P.fineliner_max = fineliner_max;
    return append_paths(S, paths, np_, &P, offx, offy, flat, st_wash, st_fine, st_marker);
}

/* the batch: every job planned on its own thread share (biggest mask first, a fixed order decided by the masks), each
 * plan in its job's slot; appended in job order afterwards */
typedef struct {
    const rf_fill_job *jobs;
    const int32_t *order;
    int32_t n;
    double ppg;
    rf_path **paths;
    int32_t *np;
    atomic_int next;
} batchjob;

static void batch_worker(void *arg, int tid) {
    (void)tid;
    batchjob *B = (batchjob *)arg;
    for (;;) {
        int32_t k = atomic_fetch_add(&B->next, 1);
        if (k >= B->n) break;
        const rf_fill_job *J = &B->jobs[B->order[k]];
        B->np[B->order[k]] = rf_plan(J->mask, J->h, J->w, B->ppg, J->flat, J->max_page, &B->paths[B->order[k]]);
    }
}

typedef struct { int64_t area; int32_t i; } jobsize;
static int cmp_jobsize(const void *a, const void *b) {
    const jobsize *x = (const jobsize *)a, *y = (const jobsize *)b;
    if (x->area != y->area) return x->area > y->area ? -1 : 1;
    return x->i < y->i ? -1 : (x->i > y->i);
}

RF_API int32_t rf_store_fill_batch(rf_store *S, const rf_fill_job *jobs, int32_t njobs, double ppg,
                                   double x0, double y0, double x1, double y1, int32_t gw, int32_t gh,
                                   double hl_scale, double pen_scale, double fineliner_max, int32_t *made) {
    if (njobs <= 0) return 0;
    placement P;
    rf_place_frame(x0, y0, x1, y1, gw, gh, &P.ox, &P.oy, &P.scale);
    P.hl_scale = hl_scale; P.pen_scale = pen_scale; P.fineliner_max = fineliner_max;
    rf_path **paths = (rf_path **)calloc((size_t)njobs, sizeof(rf_path *));
    int32_t *np = (int32_t *)calloc((size_t)njobs, sizeof(int32_t));
    jobsize *js = (jobsize *)malloc((size_t)njobs * sizeof(jobsize));
    int32_t *order = (int32_t *)malloc((size_t)njobs * sizeof(int32_t));
    if (!paths || !np || !js || !order) { free(paths); free(np); free(js); free(order); return -1; }
    for (int32_t k = 0; k < njobs; k++) { js[k].area = (int64_t)jobs[k].h * jobs[k].w; js[k].i = k; }
    qsort(js, (size_t)njobs, sizeof(jobsize), cmp_jobsize);
    for (int32_t k = 0; k < njobs; k++) order[k] = js[k].i;
    free(js);
    batchjob B;
    B.jobs = jobs; B.order = order; B.n = njobs; B.ppg = ppg; B.paths = paths; B.np = np;
    atomic_init(&B.next, 0);
    int nt = rf_threads();
    if (nt > njobs) nt = njobs;
    if (nt <= 1) batch_worker(&B, 0);          /* one job, or one thread: the plan keeps its own threads */
    else rf_parallel(nt, batch_worker, &B);
    int32_t total = 0, bad = 0;
    for (int32_t k = 0; k < njobs; k++) {
        const rf_fill_job *J = &jobs[k];
        made[k] = 0;
        if (np[k] < 0) bad = 1;                 /* this plan ran out of memory: the batch fails */
        if (np[k] <= 0) continue;
        if (bad) {                              /* the store is being discarded: only release this job's paths */
            for (int32_t i = 0; i < np[k]; i++) free(paths[k][i].xy);
            free(paths[k]);
            continue;
        }
        int32_t r = append_paths(S, paths[k], np[k], &P, J->offx, J->offy, J->flat, J->st_wash, J->st_fine, J->st_marker);
        if (r < 0) bad = 1;
        else { made[k] = r; total += r; }
    }
    free(paths); free(np); free(order);
    return bad ? -1 : total;
}

/* ------------------------------------------------------------------ strokes made in Python */
RF_API int32_t rf_store_add(rf_store *S, int32_t n, const int32_t *counts, const double *xy, const double *w, const uint8_t *kinds,
                            const int32_t *style, const int32_t *pyref) {
    int64_t total = 0;
    for (int32_t i = 0; i < n; i++) total += counts[i];
    if (reserve_strokes(S, (int64_t)S->n + n) || reserve_points(S, S->npts + total)) return -1;
    memcpy(S->xy + 2 * S->npts, xy, (size_t)total * 2 * sizeof(double));
    memcpy(S->w + S->npts, w, (size_t)total * sizeof(double));
    memcpy(S->kind + 2 * S->npts, kinds, (size_t)total * 2);
    for (int32_t i = 0; i < n; i++) {
        int32_t s = S->n++;
        S->start[s] = S->npts; S->count[s] = counts[i]; S->style[s] = style[i]; S->pyref[s] = pyref[i];
        S->npts += counts[i];
    }
    return n;
}

/* ------------------------------------------------------------------ decompose's last lines */
RF_API int32_t rf_store_wash_first(const rf_store *S, const int32_t *order, int32_t n, int32_t hl_tool, int32_t *out) {
    int32_t nk = S->max_rgba_key + 1;
    int32_t *gid = (int32_t *)malloc((size_t)(nk > 0 ? nk : 1) * sizeof(int32_t));
    int32_t *gcount = (int32_t *)calloc((size_t)(n > 0 ? n : 1) + 1, sizeof(int32_t));
    if (!gid || !gcount) { free(gid); free(gcount); return -1; }
    for (int32_t k = 0; k < nk; k++) gid[k] = -1;
    int32_t ng = 0, nw = 0;
    for (int32_t t = 0; t < n; t++) {
        const style_t *st = &S->st[S->style[order[t]]];
        if (st->tool != hl_tool) continue;
        if (st->rgba_key < 0) { free(gid); free(gcount); return -2; }     /* tuple(None): the Python raises */
        if (gid[st->rgba_key] < 0) gid[st->rgba_key] = ng++;
        gcount[gid[st->rgba_key] + 1]++;
        nw++;
    }
    for (int32_t g = 0; g < ng; g++) gcount[g + 1] += gcount[g];     /* each group's first slot */
    int32_t pen = nw;
    for (int32_t t = 0; t < n; t++) {
        const style_t *st = &S->st[S->style[order[t]]];
        if (st->tool == hl_tool) out[gcount[gid[st->rgba_key]]++] = order[t];
        else out[pen++] = order[t];
    }
    free(gid); free(gcount);
    return n;
}

/* a < b as Python evaluates `<` between two scalars of these kinds (NEP 50: numpy.float32 against a Python float is
 * compared in float32; every other pairing is exact in double) */
static int py_lt(double a, uint8_t ka, double b, uint8_t kb) {
    if ((ka == RF_KIND_F32 && kb == RF_KIND_PY) || (ka == RF_KIND_PY && kb == RF_KIND_F32)) return (float)a < (float)b;
    return a < b;
}

/* x + d with x of kind k and d a Python float: float32 arithmetic for a numpy.float32 x, double otherwise; the
 * result keeps x's kind */
static double add_kind(double x, uint8_t k, double d) {
    if (k == RF_KIND_F32) {
        float v = (float)x + (float)d;
        return (double)v;
    }
    return x + d;
}

typedef struct { double v; uint8_t k; int set; } run_t;
static void run_min(run_t *r, double v, uint8_t k) { if (!r->set || py_lt(v, k, r->v, r->k)) { r->v = v; r->k = k; r->set = 1; } }
static void run_max(run_t *r, double v, uint8_t k) { if (!r->set || py_lt(r->v, r->k, v, k)) { r->v = v; r->k = k; r->set = 1; } }

RF_API int32_t rf_store_extent(const rf_store *S, const int32_t *order, int32_t n, int32_t hl_tool, double hl_scale, double pen_scale,
                               double *val, uint8_t *kind) {
    run_t mnx = {0}, mny = {0}, mxx = {0}, mxy = {0};
    for (int32_t t = 0; t < n; t++) {
        int32_t s = order[t];
        double scale = S->st[S->style[s]].tool == hl_tool ? hl_scale : pen_scale;
        const double *xy = S->xy + 2 * S->start[s], *w = S->w + S->start[s];
        const uint8_t *kd = S->kind + 2 * S->start[s];
        for (int32_t p = 0; p < S->count[s]; p++) {
            for (int sign = -1; sign <= 1; sign += 2) {
                double d = ((double)sign * w[p]) * scale / 2.0;      /* sign * wd * scale / 2, left to right */
                double vx = add_kind(xy[2 * p], kd[2 * p], d), vy = add_kind(xy[2 * p + 1], kd[2 * p + 1], d);
                run_min(&mnx, vx, kd[2 * p]); run_max(&mxx, vx, kd[2 * p]);
                run_min(&mny, vy, kd[2 * p + 1]); run_max(&mxy, vy, kd[2 * p + 1]);
            }
        }
    }
    if (!mnx.set) return 0;
    val[0] = mnx.v; kind[0] = mnx.k; val[1] = mny.v; kind[1] = mny.k;
    val[2] = mxx.v; kind[2] = mxx.k; val[3] = mxy.v; kind[3] = mxy.k;
    return 1;
}

RF_API int32_t rf_store_select(const rf_store *S, const int32_t *order, int32_t n, int32_t want_wash, int32_t *out) {
    int32_t k = 0;
    for (int32_t t = 0; t < n; t++) if ((int32_t)S->st[S->style[order[t]]].wash == (want_wash != 0)) out[k++] = order[t];
    return k;
}

/* ------------------------------------------------------------------ the seam's and the pass's input (rmfast.Packed) */
typedef struct {
    rf_strokes v;
    int32_t *counts, *rgb;
    double *xy, *w;
    uint8_t *wash, *kind, *pkind;
    int64_t *group;
} view_t;

static void view_free(view_t *V) {
    free(V->counts); free(V->rgb); free(V->xy); free(V->w); free(V->wash); free(V->kind); free(V->pkind); free(V->group);
    memset(V, 0, sizeof(*V));
}

/* the group key's identity per style: equal (rgb, tool, pen color) -> one id (an open-addressed table over styles) */
static int32_t *style_keys(const rf_store *S) {
    int32_t *key_of = (int32_t *)malloc((size_t)(S->nst > 0 ? S->nst : 1) * sizeof(int32_t));
    size_t cap = 16;
    while (cap < (size_t)S->nst * 2) cap *= 2;
    int32_t *tab = (int32_t *)malloc(cap * sizeof(int32_t));
    if (!key_of || !tab) { free(key_of); free(tab); return NULL; }
    for (size_t i = 0; i < cap; i++) tab[i] = -1;
    for (int32_t s = 0; s < S->nst; s++) {
        const style_t *a = &S->st[s];
        uint64_t h = 1469598103934665603ULL;
        int32_t f[5] = {a->rgb[0], a->rgb[1], a->rgb[2], a->tool, a->color};
        for (int i = 0; i < 5; i++) { h ^= (uint32_t)f[i]; h *= 1099511628211ULL; }
        size_t slot = (size_t)(h & (cap - 1));
        for (;;) {
            int32_t o = tab[slot];
            if (o < 0) { tab[slot] = s; key_of[s] = s; break; }
            const style_t *b = &S->st[o];
            if (b->rgb[0] == a->rgb[0] && b->rgb[1] == a->rgb[1] && b->rgb[2] == a->rgb[2] && b->tool == a->tool && b->color == a->color) {
                key_of[s] = key_of[o];
                break;
            }
            slot = (slot + 1) & (cap - 1);
        }
    }
    free(tab);
    return key_of;
}

static int gather(const rf_store *S, const int32_t *order, int32_t n, view_t *V) {
    memset(V, 0, sizeof(*V));
    int64_t total = 0;
    for (int32_t t = 0; t < n; t++) total += S->count[order[t]];
    size_t ns = (size_t)(n > 0 ? n : 1), np_ = (size_t)(total > 0 ? total : 1);
    V->counts = (int32_t *)malloc(ns * sizeof(int32_t));
    V->rgb = (int32_t *)malloc(ns * 3 * sizeof(int32_t));
    V->wash = (uint8_t *)malloc(ns);
    V->kind = (uint8_t *)malloc(ns * 4);
    V->group = (int64_t *)malloc(ns * sizeof(int64_t));
    V->xy = (double *)malloc(np_ * 2 * sizeof(double));
    V->w = (double *)malloc(np_ * sizeof(double));
    V->pkind = (uint8_t *)malloc(np_ * 2);
    int32_t *key_of = style_keys(S);
    int32_t *first = (int32_t *)malloc((size_t)(S->nst > 0 ? S->nst : 1) * sizeof(int32_t));
    if (!V->counts || !V->rgb || !V->wash || !V->kind || !V->group || !V->xy || !V->w || !V->pkind || !key_of || !first) {
        view_free(V); free(key_of); free(first);
        return -1;
    }
    for (int32_t s = 0; s < S->nst; s++) first[s] = -1;
    int64_t ng = 0, k = 0;
    for (int32_t t = 0; t < n; t++) {
        int32_t s = order[t], c = S->count[s];
        const style_t *st = &S->st[S->style[s]];
        V->counts[t] = c;
        V->rgb[3 * t] = st->rgb[0]; V->rgb[3 * t + 1] = st->rgb[1]; V->rgb[3 * t + 2] = st->rgb[2];
        V->wash[t] = st->wash;
        int32_t key = key_of[S->style[s]];
        if (first[key] < 0) first[key] = (int32_t)ng++;
        V->group[t] = first[key];
        const uint8_t *kd = S->kind + 2 * S->start[s];
        if (c > 0) {
            V->kind[4 * t] = kd[0]; V->kind[4 * t + 1] = kd[1];
            V->kind[4 * t + 2] = kd[2 * (c - 1)]; V->kind[4 * t + 3] = kd[2 * (c - 1) + 1];
        } else memset(V->kind + 4 * t, 0, 4);
        memcpy(V->xy + 2 * k, S->xy + 2 * S->start[s], (size_t)c * 2 * sizeof(double));
        memcpy(V->w + k, S->w + S->start[s], (size_t)c * sizeof(double));
        memcpy(V->pkind + 2 * k, kd, (size_t)c * 2);
        k += c;
    }
    free(key_of); free(first);
    V->v.n = n; V->v.counts = V->counts; V->v.xy = V->xy; V->v.w = V->w; V->v.wash = V->wash; V->v.rgb = V->rgb;
    V->v.group = V->group; V->v.kind = V->kind; V->v.pkind = V->pkind;
    return 0;
}

RF_API int32_t rf_store_seam(const rf_store *S, const int32_t *base, int32_t nbase, const int32_t *washes, int32_t nwashes,
                             double fx0, double fy0, int32_t W, int32_t H, double wash_eps, int32_t **add) {
    *add = NULL;
    view_t B, Cm;
    if (gather(S, base, nbase, &B)) return -1;
    if (gather(S, washes, nwashes, &Cm)) { view_free(&B); return -1; }
    int32_t n = rf_seam(&B.v, &Cm.v, fx0, fy0, W, H, wash_eps, add);
    view_free(&B); view_free(&Cm);
    if (n > 0 && *add) for (int32_t i = 0; i < n; i++) (*add)[i] = base[(*add)[i]];
    return n;
}

RF_API int32_t rf_store_prune_join(const rf_store *S, const int32_t *order, int32_t n, double eps_out, double radius, double radius_w,
                                   int32_t max_points, rf_result *out) {
    memset(out, 0, sizeof(*out));
    view_t V;
    if (gather(S, order, n, &V)) return -1;
    int rc = rf_prune_join(&V.v, eps_out, radius, radius_w, max_points, out);
    view_free(&V);
    if (rc != 0) return -1;
    for (int32_t i = 0; i < out->n; i++) out->src[i] = order[out->src[i]];
    return 0;
}
