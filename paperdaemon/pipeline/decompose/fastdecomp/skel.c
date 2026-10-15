/* skel.c -- rm_paint._skeleton(mask, ppg, min_len, method="thin") as the painter runs it (SUBCELL_GEOMETRY): the contour
 * pass's centerlines (GEOMETRY code: these are stroke points).
 *
 * Zhang-Suen of the mask (xdog.c rf_thin), then rmb_geometry.skeleton_paths step for step: the skeleton's pixels as
 * points (x, y) in sorted order; each one's neighbors in the order W, N, E, S, NW, NE, SE, SW, a diagonal left out
 * when one of the two orthogonal pixels between them is set; the starts sorted by (degree != 1, x, y); an isolated
 * pixel traced as [(x, y), (x + .01, y)]; from each start every edge not yet followed, and from there at each pixel
 * the neighbors over an unfollowed edge (in neighbor order) scored by ((p - here) . (here - q[max(0, len - 5)])) /
 * math.hypot(p - here), the first highest taken, until no edge is left or the line is back at its start. Each traced
 * line's length is the builtin sum() of math.hypot over its points (outline.c), the total their plain sum; a line at
 * least min_len long is simplified (rmb_npops.simplify, eps) and, when `smooth`, Chaikin-cut twice
 * (rmb_lineart.chaikin: 0.75 a + 0.25 b and 0.25 a + 0.75 b per segment, both ends kept, only with 3+ points).
 * Identity: a check of every call of real runs against rm_paint._skeleton, and of random masks. */
#include <stdlib.h>
#include <string.h>
#include "rmfast.h"
#include "internal.h"

static const int NDX[8] = {-1, 0, 1, 0, -1, 1, 1, -1}, NDY[8] = {0, -1, 0, 1, -1, -1, 1, 1};

typedef struct { double *xy, *L; int32_t *cnt; int64_t np, cap_p, n, cap_n; } skel_out;
typedef struct { double *p; int64_t cap; } dbuf;

/* room for n points (2 doubles each) in b; 0, or -1 out of memory */
static int room(dbuf *b, int64_t n) {
    if (n <= b->cap) return 0;
    int64_t c = b->cap ? b->cap : 256;
    while (c < n) c *= 2;
    double *q = (double *)realloc(b->p, sizeof(double) * 2 * (size_t)c);
    if (!q) return -1;
    b->p = q; b->cap = c;
    return 0;
}

static int out_add(skel_out *o, double L, const double *pts, int32_t c) {
    if (o->n == o->cap_n) {
        int64_t k = o->cap_n ? 2 * o->cap_n : 64;
        double *Ln = (double *)realloc(o->L, sizeof(double) * (size_t)k);
        if (!Ln) return -1;
        o->L = Ln;
        int32_t *cn = (int32_t *)realloc(o->cnt, sizeof(int32_t) * (size_t)k);
        if (!cn) return -1;
        o->cnt = cn; o->cap_n = k;
    }
    if (o->np + c > o->cap_p) {
        int64_t k = o->cap_p ? o->cap_p : 1024;
        while (o->np + c > k) k *= 2;
        double *x = (double *)realloc(o->xy, sizeof(double) * 2 * (size_t)k);
        if (!x) return -1;
        o->xy = x; o->cap_p = k;
    }
    memcpy(o->xy + 2 * o->np, pts, sizeof(double) * 2 * (size_t)c);
    o->L[o->n] = L; o->cnt[o->n] = c; o->n++; o->np += c;
    return 0;
}

/* one traced line: its length into the total; kept when long enough (simplified, smoothed). 0, or -1 out of memory */
static int finish_line(const double *line, int32_t n, double min_len, double eps, int smooth, double *tot, dbuf *simp, dbuf *c1, dbuf *c2,
                       skel_out *o) {
    double L = rf_py_sum_hypot(line, n);
    *tot += L;
    if (L < min_len || n < 2) return 0;
    if (room(simp, n)) return -1;
    int32_t m = rf_dp_simplify(line, n, eps, simp->p);
    if (m < 0) return -1;
    if (m < 2) return 0;
    const double *pts = simp->p;
    int32_t c = m;
    for (int it = 0; smooth && it < 2 && c >= 3; it++) {
        dbuf *d = it == 0 ? c1 : c2;
        if (room(d, 2 * (int64_t)c)) return -1;
        double *dst = d->p;
        int32_t k = 0;
        dst[0] = pts[0]; dst[1] = pts[1]; k = 1;
        for (int32_t t = 0; t + 1 < c; t++) {
            double ax = pts[2 * t], ay = pts[2 * t + 1], bx = pts[2 * t + 2], by = pts[2 * t + 3];
            dst[2 * k] = 0.75 * ax + 0.25 * bx; dst[2 * k + 1] = 0.75 * ay + 0.25 * by; k++;
            dst[2 * k] = 0.25 * ax + 0.75 * bx; dst[2 * k + 1] = 0.25 * ay + 0.75 * by; k++;
        }
        dst[2 * k] = pts[2 * c - 2]; dst[2 * k + 1] = pts[2 * c - 1]; k++;
        pts = dst; c = k;
    }
    return out_add(o, L, pts, c);
}

static void mark(uint8_t *seen, const int32_t *adj, const uint8_t *deg, int32_t a, int ka, int32_t b) {
    seen[a] |= (uint8_t)(1u << ka);
    for (int k = 0; k < deg[b]; k++) if (adj[8 * b + k] == a) { seen[b] |= (uint8_t)(1u << k); break; }
}

/* -> the lines kept (lengths *L_out, point counts *cnt_out, points *xy_out, each rf_free'd by the caller), the total
 * length *total, the traced lines' count *pieces (0 for an empty mask, as the Python); -1 out of memory */
RF_API int32_t rf_skeleton_thin(const uint8_t *mask, int32_t H, int32_t W, double min_len, double eps, int32_t smooth,
                                double **L_out, int32_t **cnt_out, double **xy_out, double *total, int32_t *pieces) {
    *L_out = NULL; *cnt_out = NULL; *xy_out = NULL; *total = 0.0; *pieces = 0;
    size_t N = (size_t)H * W;
    int any = 0;
    for (size_t i = 0; i < N && !any; i++) any = mask[i] != 0;
    if (!any) return 0;                                  /* the Python returns ([], 0.0, 0) */
    uint8_t *fg = (uint8_t *)malloc(N), *deg = NULL, *seen = NULL;
    int32_t *id = (int32_t *)malloc(sizeof(int32_t) * N), *px = NULL, *adj = NULL, *start = NULL, *q = NULL;
    dbuf line = {NULL, 0}, simp = {NULL, 0}, c1 = {NULL, 0}, c2 = {NULL, 0};
    skel_out o; memset(&o, 0, sizeof(o));
    int32_t rc = -1;
    if (!fg || !id || rf_thin(mask, H, W, fg)) goto done;
    int32_t np = 0;                                      /* the points, in sorted (x, y) order */
    for (int32_t x = 0; x < W; x++)
        for (int32_t y = 0; y < H; y++) {
            size_t p = (size_t)y * W + x;
            id[p] = fg[p] ? np++ : -1;
        }
    int64_t qcap = 4 * (int64_t)np + 2;                  /* a line follows each edge once: at most 4 np of them */
    px = (int32_t *)malloc(sizeof(int32_t) * 2 * ((size_t)np + 1));
    adj = (int32_t *)malloc(sizeof(int32_t) * 8 * ((size_t)np + 1));
    deg = (uint8_t *)calloc((size_t)np + 1, 1);
    seen = (uint8_t *)calloc((size_t)np + 1, 1);        /* bit k: the edge to adjacency slot k was followed */
    start = (int32_t *)malloc(sizeof(int32_t) * ((size_t)np + 1));
    q = (int32_t *)malloc(sizeof(int32_t) * (size_t)qcap);
    if (!px || !adj || !deg || !seen || !start || !q || room(&line, qcap)) goto done;
    for (int32_t x = 0; x < W; x++)
        for (int32_t y = 0; y < H; y++) {
            int32_t i = id[(size_t)y * W + x];
            if (i < 0) continue;
            px[2 * i] = x; px[2 * i + 1] = y;
            int d = 0;
            for (int k = 0; k < 8; k++) {
                int32_t nx = x + NDX[k], ny = y + NDY[k];
                if (nx < 0 || ny < 0 || nx >= W || ny >= H || id[(size_t)ny * W + nx] < 0) continue;
                if (NDX[k] && NDY[k] && (id[(size_t)y * W + nx] >= 0 || id[(size_t)ny * W + x] >= 0)) continue;
                adj[8 * i + d++] = id[(size_t)ny * W + nx];
            }
            deg[i] = (uint8_t)d;
        }
    int32_t ns = 0;
    for (int32_t i = 0; i < np; i++) if (deg[i] == 1) start[ns++] = i;
    for (int32_t i = 0; i < np; i++) if (deg[i] != 1) start[ns++] = i;
    const double rt2 = rf_py_hypot(1.0, 1.0);           /* math.hypot of a diagonal step */
    double tot = 0.0;
    int32_t ntraced = 0;
    for (int32_t si = 0; si < np; si++) {
        int32_t s0 = start[si];
        if (!deg[s0]) {
            line.p[0] = px[2 * s0]; line.p[1] = px[2 * s0 + 1];
            line.p[2] = (double)px[2 * s0] + .01; line.p[3] = px[2 * s0 + 1];
            ntraced++;
            if (finish_line(line.p, 2, min_len, eps, smooth, &tot, &simp, &c1, &c2, &o)) goto done;
            continue;
        }
        for (int k0 = 0; k0 < deg[s0]; k0++) {
            if (seen[s0] & (1u << k0)) continue;
            int64_t len = 0;
            int32_t nxt = adj[8 * s0 + k0];
            q[len++] = s0; q[len++] = nxt;
            mark(seen, adj, deg, s0, k0, nxt);
            while (len < qcap) {
                int32_t here = q[len - 1], prev = q[len - 5 > 0 ? len - 5 : 0];
                int32_t vx = px[2 * here] - px[2 * prev], vy = px[2 * here + 1] - px[2 * prev + 1];
                int best = -1;
                double bk = 0.0;
                for (int k = 0; k < deg[here]; k++) {
                    if (seen[here] & (1u << k)) continue;
                    int32_t p = adj[8 * here + k];
                    int32_t dx = px[2 * p] - px[2 * here], dy = px[2 * p + 1] - px[2 * here + 1];
                    double key = (double)(dx * vx + dy * vy) / ((dx && dy) ? rt2 : 1.0);
                    if (best < 0 || key > bk) { best = k; bk = key; }
                }
                if (best < 0) break;
                int32_t nx_ = adj[8 * here + best];
                mark(seen, adj, deg, here, best, nx_);
                q[len++] = nx_;
                if (nx_ == s0) break;
            }
            for (int64_t t = 0; t < len; t++) { line.p[2 * t] = px[2 * q[t]]; line.p[2 * t + 1] = px[2 * q[t] + 1]; }
            ntraced++;
            if (finish_line(line.p, (int32_t)len, min_len, eps, smooth, &tot, &simp, &c1, &c2, &o)) goto done;
        }
    }
    *total = tot;
    *pieces = ntraced > 1 ? ntraced : 1;
    *L_out = o.L; *cnt_out = o.cnt; *xy_out = o.xy;
    o.L = NULL; o.cnt = NULL; o.xy = NULL;
    rc = (int32_t)o.n;
done:
    free(fg); free(id); free(px); free(adj); free(deg); free(seen); free(start); free(q);
    free(line.p); free(simp.p); free(c1.p); free(c2.p); free(o.L); free(o.cnt); free(o.xy);
    return rc;
}
