/* lab.c -- rm_paint._lab_rows: sRGB uint8 rows to CIE Lab (float64), bit for bit as numpy computes it (DECISION code:
 * Lab values only classify, compare and rank colors; no stroke point is made from them).
 *
 * The Python: v = _SRGB_LUT[rgb] (the transfer function tabulated with CPython's float arithmetic, c / 12.92 or
 * ((c + 0.055) / 1.055) ** 2.4), then elementwise numpy float64 operations in the written order --
 * x = (0.4124 r + 0.3576 g + 0.1805 b) / 0.95047, y = 0.2126 r + 0.7152 g + 0.0722 b,
 * z = (0.0193 r + 0.1192 g + 0.9505 b) / 1.08883, f(t) = |t| ** (1/3) when t > 0.008856 else 7.787 t + 16/116,
 * L = 116 fy - 16, a = 500 (fx - fy), b = 200 (fy - fz). Every product and sum is its own rounding (numpy's loops do
 * not fuse; built with -ffp-contract=off). The power is the C runtime's pow: CPython's float ** and numpy's float64
 * power (no SIMD power without SVML, which Windows builds of numpy do not link) both call ucrtbase.dll's pow, so on
 * Windows that very function is called here; elsewhere the platform's pow.
 * Identity: checked against the reference -- all 2^24 RGB values against rm_paint._lab_rows, at one thread and at the default. */
#include <math.h>
#include <stdatomic.h>
#include <stdlib.h>
#include "rmfast.h"
#include "internal.h"
#ifdef _WIN32
#include <windows.h>
#endif

/* a two-argument function of the C runtime by name (ucrtbase.dll on Windows: the one CPython and numpy call), else
 * the given fallback */
static rf_pow_fn crt_fn(const char *name, rf_pow_fn fallback) {
#ifdef _WIN32
    HMODULE m = GetModuleHandleW(L"ucrtbase.dll");
    if (!m) m = LoadLibraryW(L"ucrtbase.dll");
    rf_pow_fn f = m ? (rf_pow_fn)(void (*)(void))GetProcAddress(m, name) : NULL;
    return f ? f : fallback;
#else
    (void)name;
    return fallback;
#endif
}

rf_pow_fn rf_crt_pow(void) { return crt_fn("pow", pow); }
/* numpy's np.hypot (npy_hypot -> the runtime's _hypot) and atan2 (CPython's math.atan2 and np.arctan2 call it):
 * a check compares them on random values */
rf_pow_fn rf_crt_hypot(void) { return crt_fn("_hypot", hypot); }
rf_pow_fn rf_crt_atan2(void) { return crt_fn("atan2", atan2); }

/* one-argument functions of the C runtime by name, as crt_fn */
static rf_fn1 crt_fn1(const char *name, rf_fn1 fallback) {
#ifdef _WIN32
    HMODULE m = GetModuleHandleW(L"ucrtbase.dll");
    if (!m) m = LoadLibraryW(L"ucrtbase.dll");
    rf_fn1 f = m ? (rf_fn1)(void (*)(void))GetProcAddress(m, name) : NULL;
    return f ? f : fallback;
#else
    (void)name;
    return fallback;
#endif
}

rf_fn1 rf_crt_sin(void) { return crt_fn1("sin", sin); }
rf_fn1 rf_crt_cos(void) { return crt_fn1("cos", cos); }
/* np.log and np.log2 on float64 (this numpy's dispatch has no SIMD log for them: they call the runtime's);
 * a check compares them on random values and on every power of two and its neighbors */
rf_fn1 rf_crt_log(void) { return crt_fn1("log", log); }
rf_fn1 rf_crt_log2(void) { return crt_fn1("log2", log2); }

/* rm_paint._SRGB_LUT */
static void make_lut(rf_pow_fn pw, double *lut) {
    for (int v = 0; v < 256; v++) {
        double c = (double)v / 255.0;
        lut[v] = c <= 0.04045 ? c / 12.92 : pw((c + 0.055) / 1.055, 2.4);
    }
}

void rf_lab_lut(rf_pow_fn pw, double *lut) { make_lut(pw, lut); }

/* one row: (r, g, b) at p -> (L, a, b) at o, with the table and the pow of rf_lab_lut */
void rf_lab_px(const double *lut, rf_pow_fn pw, const uint8_t *p, double *o) {
    double r = lut[p[0]], g = lut[p[1]], b = lut[p[2]];
    double x = (0.4124 * r + 0.3576 * g + 0.1805 * b) / 0.95047;
    double y = (0.2126 * r + 0.7152 * g + 0.0722 * b);
    double z = (0.0193 * r + 0.1192 * g + 0.9505 * b) / 1.08883;
    double fx = x > 0.008856 ? pw(fabs(x), 1 / 3.0) : 7.787 * x + 16 / 116.0;
    double fy = y > 0.008856 ? pw(fabs(y), 1 / 3.0) : 7.787 * y + 16 / 116.0;
    double fz = z > 0.008856 ? pw(fabs(z), 1 / 3.0) : 7.787 * z + 16 / 116.0;
    o[0] = 116 * fy - 16;
    o[1] = 500 * (fx - fy);
    o[2] = 200 * (fy - fz);
}

typedef struct { const uint8_t *rgb; double *out; int64_t n; rf_pow_fn pw; double lut[256]; atomic_llong next; } labjob;
#define LAB_CHUNK 65536

static void lab_worker(void *arg, int tid) {
    (void)tid;
    labjob *J = (labjob *)arg;
    for (;;) {
        int64_t i0 = atomic_fetch_add(&J->next, LAB_CHUNK);
        if (i0 >= J->n) break;
        int64_t i1 = i0 + LAB_CHUNK < J->n ? i0 + LAB_CHUNK : J->n;
        for (int64_t i = i0; i < i1; i++) rf_lab_px(J->lut, J->pw, J->rgb + 3 * i, J->out + 3 * i);
    }
}

/* n rows of (r, g, b) -> n rows of (L, a, b); every row on its own, chunks on all threads */
RF_API void rf_lab_rows(const uint8_t *rgb, int64_t n, double *out) {
    labjob J;
    J.rgb = rgb; J.out = out; J.n = n; J.pw = rf_crt_pow();
    make_lut(J.pw, J.lut);
    atomic_init(&J.next, 0);
    int64_t chunks = (n + LAB_CHUNK - 1) / LAB_CHUNK;
    int nt = rf_threads();
    if ((int64_t)nt > chunks) nt = (int)chunks;
    rf_parallel(nt > 0 ? nt : 1, lab_worker, &J);
}

/* the transfer table as built here, for the identity check against rm_paint._SRGB_LUT */
RF_API void rf_srgb_lut(double *out) { make_lut(rf_crt_pow(), out); }

/* L only (the first column of rm_paint._lab_rows), for n rows: the same y and f(y) as the full conversion */
typedef struct { const uint8_t *rgb; double *out; int64_t n; rf_pow_fn pw; double lut[256]; atomic_llong next; } ljob;

static void l_worker(void *arg, int tid) {
    (void)tid;
    ljob *J = (ljob *)arg;
    for (;;) {
        int64_t i0 = atomic_fetch_add(&J->next, LAB_CHUNK);
        if (i0 >= J->n) break;
        int64_t i1 = i0 + LAB_CHUNK < J->n ? i0 + LAB_CHUNK : J->n;
        for (int64_t i = i0; i < i1; i++) {
            const uint8_t *p = J->rgb + 3 * i;
            double y = (0.2126 * J->lut[p[0]] + 0.7152 * J->lut[p[1]] + 0.0722 * J->lut[p[2]]);
            double fy = y > 0.008856 ? J->pw(fabs(y), 1 / 3.0) : 7.787 * y + 16 / 116.0;
            J->out[i] = 116 * fy - 16;
        }
    }
}

void rf_l_rows(const uint8_t *rgb, int64_t n, double *out) {
    ljob J;
    J.rgb = rgb; J.out = out; J.n = n; J.pw = rf_crt_pow();
    make_lut(J.pw, J.lut);
    atomic_init(&J.next, 0);
    int64_t chunks = (n + LAB_CHUNK - 1) / LAB_CHUNK;
    int nt = rf_threads();
    if ((int64_t)nt > chunks) nt = (int)chunks;
    rf_parallel(nt > 0 ? nt : 1, l_worker, &J);
}
