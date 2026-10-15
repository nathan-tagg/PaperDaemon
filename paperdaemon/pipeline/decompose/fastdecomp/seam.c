/* The two-run seam -- rm_model._seam, footprint form: a pixel the first run's washes paint (under the renderer's
 * WASH_EPS fill) that the combined washes leave bare gets its first-run wash(es) back. The frame is the caller's
 * (integer page origin, W x H). Returns the base washes to add, ascending (GEOMETRY code). Every allocation is
 * checked: a failure returns -1 with nothing left allocated. */
#include <stdatomic.h>
#include <stdlib.h>
#include <string.h>
#include "rmfast.h"
#include "internal.h"

static int64_t *starts(const rf_strokes *s) {
    int64_t *st = (int64_t *)malloc(sizeof(int64_t) * ((size_t)s->n + 1));
    if (!st) return NULL;
    st[0] = 0;
    for (int32_t i = 0; i < s->n; i++) st[i + 1] = st[i] + s->counts[i];
    return st;
}

/* the work on all threads: each thread paints its share of the strokes into its own canvas (painting only sets
 * pixels, so the union of the canvases is the canvas one thread would paint), and the gap test of each base wash
 * lands in that wash's own slot */
typedef struct {
    const rf_strokes *s; const int64_t *start; uint8_t **canvas; int32_t W, H; double fx0, fy0, eps;
    rf_scratch *S; const uint8_t *gap; uint8_t *hit; atomic_int next; atomic_int oom;
} seamjob;

static void paint_worker(void *arg, int tid) {
    seamjob *J = (seamjob *)arg;
    const rf_strokes *s = J->s;
    for (;;) {
        int32_t k0 = atomic_fetch_add(&J->next, 64);
        if (k0 >= s->n) break;
        int32_t k1 = k0 + 64 < s->n ? k0 + 64 : s->n;
        for (int32_t i = k0; i < k1; i++) {
            if (!s->wash[i] || s->counts[i] < 2) continue;
            rf_scratch *S = &J->S[tid];
            if (rf_scratch_reserve_pts(S, s->counts[i])) { atomic_store(&J->oom, 1); return; }
            int32_t m = rf_geometry(s->xy + 2 * J->start[i], s->w + J->start[i], s->counts[i], S->xs, S->ys, S->hw);
            if (m < 2) continue;
            rf_paint(J->canvas[tid], J->W, J->H, J->fx0, J->fy0, S->xs, S->ys, S->hw, m, J->eps);
        }
    }
}

static void gap_worker(void *arg, int tid) {
    seamjob *J = (seamjob *)arg;
    const rf_strokes *s = J->s;
    for (;;) {
        int32_t k0 = atomic_fetch_add(&J->next, 64);
        if (k0 >= s->n) break;
        int32_t k1 = k0 + 64 < s->n ? k0 + 64 : s->n;
        for (int32_t i = k0; i < k1; i++) {
            if (!s->wash[i] || s->counts[i] < 2) continue;
            int32_t *fp = NULL;
            int32_t k = rf_wash_pixels_into(s->xy + 2 * J->start[i], s->w + J->start[i], s->counts[i], J->fx0, J->fy0, J->W, J->H, J->eps, &J->S[tid], &fp);
            if (k < 0) { atomic_store(&J->oom, 1); return; }
            int h = 0;
            for (int32_t t = 0; t < k && !h; t++) h = J->gap[fp[t]];
            free(fp);
            J->hit[i] = (uint8_t)h;
        }
    }
}

/* every wash of `s` painted into `out` (W x H), on nt threads. 0, or -1 when memory ran out. */
static int paint_parallel(const rf_strokes *s, const int64_t *start, uint8_t *out, int32_t W, int32_t H, double fx0, double fy0, double eps, int nt, rf_scratch *S) {
    size_t N = (size_t)W * H;
    seamjob J; memset(&J, 0, sizeof(J));
    J.s = s; J.start = start; J.W = W; J.H = H; J.fx0 = fx0; J.fy0 = fy0; J.eps = eps; J.S = S;
    J.canvas = (uint8_t **)calloc((size_t)nt, sizeof(uint8_t *));
    if (!J.canvas) return -1;
    J.canvas[0] = out;
    int bad = 0;
    for (int t = 1; t < nt; t++) if (!(J.canvas[t] = (uint8_t *)calloc(N, 1))) bad = 1;
    atomic_init(&J.next, 0);
    atomic_init(&J.oom, 0);
    if (!bad) rf_parallel(nt, paint_worker, &J);
    for (int t = 1; t < nt; t++) { if (!bad) for (size_t i = 0; i < N; i++) out[i] |= J.canvas[t][i]; free(J.canvas[t]); }
    free(J.canvas);
    return (bad || atomic_load(&J.oom)) ? -1 : 0;
}

RF_API int32_t rf_seam(const rf_strokes *base, const rf_strokes *combined, double fx0, double fy0, int32_t W, int32_t H, double wash_eps, int32_t **out) {
    *out = NULL;
    size_t N = (size_t)W * H;
    uint8_t *A = (uint8_t *)calloc(N ? N : 1, 1), *B = (uint8_t *)calloc(N ? N : 1, 1);
    int64_t *sb = starts(base), *sc = starts(combined);
    int nt = rf_threads();
    if (nt > 16) nt = 16;                       /* one canvas per thread: keep the memory bounded */
    rf_scratch *S = (rf_scratch *)calloc((size_t)nt, sizeof(rf_scratch));
    int32_t n = -1; int32_t *add = NULL;
    uint8_t *hit = NULL;
    if (!A || !B || !sb || !sc || !S) goto done;
    if (paint_parallel(base, sb, A, W, H, fx0, fy0, wash_eps, nt, S) || paint_parallel(combined, sc, B, W, H, fx0, fy0, wash_eps, nt, S)) goto done;
    int any = 0;
    for (size_t t = 0; t < N; t++) { A[t] = A[t] & !B[t]; any |= A[t]; }      /* A becomes the gap */
    n = 0;
    if (any) {
        seamjob J; memset(&J, 0, sizeof(J));
        J.s = base; J.start = sb; J.W = W; J.H = H; J.fx0 = fx0; J.fy0 = fy0; J.eps = wash_eps; J.S = S; J.gap = A;
        J.hit = hit = (uint8_t *)calloc((size_t)(base->n ? base->n : 1), 1);
        if (!hit) { n = -1; goto done; }
        atomic_init(&J.next, 0);
        atomic_init(&J.oom, 0);
        rf_parallel(nt, gap_worker, &J);
        if (atomic_load(&J.oom)) { n = -1; goto done; }
        for (int32_t i = 0; i < base->n; i++) n += hit[i];
        add = (int32_t *)malloc(sizeof(int32_t) * (n ? n : 1));
        if (!add) { n = -1; goto done; }
        int32_t k = 0;
        for (int32_t i = 0; i < base->n; i++) if (hit[i]) add[k++] = i;
    }
    *out = add;
done:
    if (S) for (int t = 0; t < nt; t++) rf_scratch_free(&S[t]);
    free(S); free(hit);
    free(A); free(B); free(sb); free(sc);
    return n;
}
