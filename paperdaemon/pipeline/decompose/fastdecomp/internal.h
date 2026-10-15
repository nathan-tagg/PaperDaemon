#ifndef RMFAST_INTERNAL_H
#define RMFAST_INTERNAL_H
#include <stdint.h>
#include <stddef.h>

#define RF_HL_SCALE 0.25        /* rm_raster.HL_SCALE: highlighter width field -> page px */
#define RF_EPS 1e-3             /* rm_raster.EPS */

typedef struct {
    double *xs, *ys, *hw;
    int32_t cap_pts;
    uint8_t *img;               /* all zeros between uses */
    size_t cap_img;
    int32_t *smin, *smax, cap_rows;
} rf_scratch;

void rf_paint(uint8_t *img, int32_t W, int32_t H, double ox, double oy, const double *xs, const double *ys, const double *hw, int32_t n, double eps);
int32_t rf_geometry(const double *xy, const double *w, int32_t npts, double *xs, double *ys, double *hw);
int32_t rf_wash_pixels_into(const double *xy, const double *w, int32_t npts, double ox, double oy, int32_t W, int32_t H, double eps, rf_scratch *S, int32_t **out);
/* the footprints under ne (<= 8) eps values from one painting, each into the caller's buffer bufs[e] (caps[e]
 * entries, grown when needed), counts[e] long. 0, or -1 when memory ran out. */
int32_t rf_wash_pixels_multi(const double *xy, const double *w, int32_t npts, double ox, double oy, int32_t W, int32_t H, const double *eps,
                             int ne, rf_scratch *S, int32_t **bufs, size_t *caps, int32_t *counts);
/* the same list into the caller's buffer *buf of *cap entries, grown when needed (no allocation per call) */
int32_t rf_wash_pixels_buf(const double *xy, const double *w, int32_t npts, double ox, double oy, int32_t W, int32_t H, double eps, rf_scratch *S,
                           int32_t **buf, size_t *cap);
/* 0, or -1 when memory ran out */
int rf_scratch_reserve_pts(rf_scratch *S, int32_t npts);
int rf_scratch_reserve_img(rf_scratch *S, size_t n);
int rf_scratch_reserve_rows(rf_scratch *S, int32_t n);
void rf_paint_spans(uint8_t *img, int32_t W, int32_t H, double ox, double oy, const double *xs, const double *ys, const double *hw, int32_t n, double eps,
                    int32_t *smin, int32_t *smax);
void rf_scratch_free(rf_scratch *S);

/* sorted, unique int32 sets (numpy's assume_unique=True arrays). Results are malloc'd; *n_out set. */
int32_t *rf_union(const int32_t *a, int32_t na, const int32_t *b, int32_t nb, int32_t *n_out);
int32_t *rf_setdiff(const int32_t *a, int32_t na, const int32_t *b, int32_t nb, int32_t *n_out);
int32_t *rf_intersect(const int32_t *a, int32_t na, const int32_t *b, int32_t nb, int32_t *n_out);
int32_t *rf_setxor(const int32_t *a, int32_t na, const int32_t *b, int32_t nb, int32_t *n_out);
/* the same four into the caller's array o (room for na + nb, na, min(na, nb), na + nb): -> the count */
int32_t rf_union_to(const int32_t *a, int32_t na, const int32_t *b, int32_t nb, int32_t *o);
int32_t rf_setdiff_to(const int32_t *a, int32_t na, const int32_t *b, int32_t nb, int32_t *o);
int32_t rf_intersect_to(const int32_t *a, int32_t na, const int32_t *b, int32_t nb, int32_t *o);
int32_t rf_setxor_to(const int32_t *a, int32_t na, const int32_t *b, int32_t nb, int32_t *o);
/* mine[k] += 1 where a[k] is in b */
void rf_isin_add(const int32_t *a, int32_t na, const int32_t *b, int32_t nb, uint16_t *mine);

/* Python's float floor division a // b, as CPython computes it */
double rf_py_floordiv(double a, double b);
/* numpy float32 floor division, as np.float32 // a Python float computes it */
float rf_np_floordivf(float a, float b);

/* 4-connected components (label.c): labels 1..n numbered by each component's first raster pixel. Arrays are
 * indexed by label (entry 0 unused); `start`/`pix` (when asked for) list each component's pixels in raster order:
 * pix[start[k] .. start[k + 1]) for label k. */
typedef struct {
    int32_t n;
    int64_t *area, *first, *start;
    int32_t *x0, *x1, *y0, *y1, *pix;
} rf_comps;
double rf_now(void);
/* model.c: how far the running decompose has come, for rf_progress. rf_prog_at(f) marks fraction f (0..1) of the
 * current painter run done; the run's share of the whole is set by model.c around each run. Reporting only. */
void rf_prog_at(double f);
/* numpy's pairwise float64 sum of a contiguous array (npsum.c) */
double rf_pairwise_sum(const double *a, int64_t n);
/* threads.c: the worker count (RMFAST_THREADS, else every logical processor) and a run of fn on n threads */
int rf_threads(void);
void rf_parallel(int n, void (*fn)(void *arg, int tid), void *arg);
int32_t rf_label4(const uint8_t *m, int32_t H, int32_t W, int32_t *lab, rf_comps *C, int want_pixels);
void rf_comps_free(rf_comps *C);

/* lab.c: the C runtime's pow -- on Windows ucrtbase.dll's, the function CPython's float ** and numpy's float64 power
 * call */
typedef double (*rf_pow_fn)(double, double);
rf_pow_fn rf_crt_pow(void);
rf_pow_fn rf_crt_hypot(void);       /* np.hypot's function */
rf_pow_fn rf_crt_atan2(void);       /* math.atan2's and np.arctan2's function */
typedef double (*rf_fn1)(double);
rf_fn1 rf_crt_sin(void);            /* math.sin's function */
rf_fn1 rf_crt_cos(void);            /* math.cos's function */
rf_fn1 rf_crt_log(void);            /* np.log's function (float64, this build's numpy: no SIMD log) */
rf_fn1 rf_crt_log2(void);           /* np.log2's function */
/* lab.c: the L column of rm_paint._lab_rows alone, n rows on all threads */
void rf_l_rows(const uint8_t *rgb, int64_t n, double *out);
/* lab.c: rm_paint._SRGB_LUT built with pw (rf_crt_pow), and one row of rm_paint._lab_rows with it */
void rf_lab_lut(rf_pow_fn pw, double *lut);
void rf_lab_px(const double *lut, rf_pow_fn pw, const uint8_t *p, double *o);
/* outline.c: CPython 3.12's math.hypot (correctly rounded); the builtin sum() of the hypot lengths along m points;
 * rmb_npops.simplify (Douglas-Peucker) of n points into out (room for n) -> the points kept, -1 out of memory */
double rf_py_hypot(double x, double y);
double rf_py_sum_hypot(const double *xy, int32_t m);
int32_t rf_dp_simplify(const double *pts, int32_t n, double eps, double *out);
/* outline.c: the outline's scratch, grown when needed and kept between calls (start it zeroed; rf_outline_buf_free
 * releases it), and rf_outline's total length alone through it (no chain is built, nothing allocated once the scratch
 * is big enough) -> 0, -1 out of memory */
typedef struct { int64_t key; int32_t head, tail; } rf_outline_kent;
typedef struct {
    double *ax; int64_t *kk; int32_t cap;                  /* the segments (cap of them) */
    rf_outline_kent *ht; size_t hcap;                      /* segment ends by key */
    int32_t *nxt, *seg_of; uint8_t *used;
    double *fwd, *back, *chain, *simp;
    uint8_t *keep; int32_t *stack;                         /* Douglas-Peucker */
    int32_t ncap;                                          /* the per-segment arrays' room, in segments */
} rf_outline_buf;
void rf_outline_buf_free(rf_outline_buf *S);
int32_t rf_outline_length(const uint8_t *a, int32_t H, int32_t W, int32_t w, int32_t h, rf_outline_buf *S, double *total);
/* zones.c: Python's float % (and numpy's remainder); CPython's math.atan2 on finite arguments; numpy's median and
 * linear percentile of a double array (reordered); the k-th smallest */
double rf_py_mod(double vx, double wx);
double rf_py_atan2(rf_pow_fn at2, double y, double x);
double rf_np_median(double *v, int64_t n);
double rf_np_percentile(double *v, int64_t n, double pct);
/* hatch.c: rm_trace.place of n Python-float points (ox + x * scale, oy + y * scale) into dst */
void rf_place_points(const double *xy, int64_t n, double ox, double oy, double scale, double *dst);
double rf_kth(double *a, int64_t n, int64_t k);

/* merge.c: scipy.ndimage's uniform filter of size 3, mode "nearest", along one line of n values (stride st), in place;
 * buf holds n + 2 values */
void rf_uniform3(double *a, int64_t n, int64_t st, double *buf);

/* plan.c: one ring of the plan, in grid coordinates (xy holds n + 1 points of room); f32 = the Python's points are
 * numpy.float32 (a simplified loop); w its pen width in page px */
typedef struct { double *xy; int32_t n; int f32; double w; } rf_path;
int32_t rf_plan(const uint8_t *mask, int32_t h, int32_t w_, double ppg, int flat, double max_page, rf_path **paths_out);
void rf_place_frame(double x0, double y0, double x1, double y1, int32_t gw, int32_t gh, double *ox, double *oy, double *scale);
void rf_place_path(const rf_path *p, double ox, double oy, double scale, int32_t offx, int32_t offy, double *dst);
void rf_path_field(const rf_path *p, int flat, double hl_scale, double pen_scale, double fineliner_max, int32_t *field, int32_t *pen);

#endif
