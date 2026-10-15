/* npsort.c -- numpy.argsort(a) (kind "quicksort", the default) of an int64 array as numpy 2.5.3 computes it, the order
 * of equal keys included (DECISION code: the palette step processes its colors in this order).
 *
 * numpy's aquicksort_ hands a 64-bit integer array to x86-simd-sort when its dispatch finds a SIMD target the CPU has;
 * this numpy build's targets for it are X86_V4 and X86_V3, and on this machine it runs X86_V3 (AVX2: np.show_runtime
 * finds X86_V3, and the vendored AVX2 build matches np.argsort on every array tested). So:
 *   on a CPU at x86-64-v3: the vendored library's AVX2 argsort (npsort_avx2.cpp), for n <= 256 (its bitonic networks;
 *     past 256 the library may call std::sort, whose order of equal keys is the C++ library's: refused, -2);
 *   below it: numpy's own scalar aquicksort_ (quicksort.hpp: median of three, SMALL_QUICKSORT 15, insertion sort, an
 *     explicit stack, the depth limit 2 * msb(n) and aheapsort_ past it), reproduced here line for line.
 * A CPU at x86-64-v4 with a numpy build that dispatches X86_V4 would sort equal keys in another order; this numpy
 * build has no X86_V4 dispatch on this machine, so the case does not arise here.
 * Identity: np.argsort against this on random arrays with many equal keys; the scalar path against np.argsort with
 * numpy's SIMD dispatch switched off (NPY_DISABLE_CPU_FEATURES). */
#include <stdlib.h>
#include "rmfast.h"
#include "internal.h"

#if defined(__x86_64__) || defined(_M_X64)
#include <cpuid.h>
void rf_np_argsort_avx2(const int64_t *a, int64_t *arg, int64_t n);
#define HAVE_AVX2_SORT 1
#endif

#define SMALL_QUICKSORT 15
#define PYA_QS_STACK 128

static int msb(int64_t n) { int d = 0; while (n > 1) { n >>= 1; d++; } return d; }     /* npy_get_msb */

static void swap_i(int64_t *x, int64_t *y) { int64_t t = *x; *x = *y; *y = t; }

/* numpy's aheapsort_ on tosort[0 .. n) */
static void aheapsort(const int64_t *v, int64_t *tosort, int64_t n) {
    int64_t *a = tosort - 1, i, j, l, tmp;
    for (l = n >> 1; l > 0; --l) {
        tmp = a[l];
        for (i = l, j = l << 1; j <= n;) {
            if (j < n && v[a[j]] < v[a[j + 1]]) j += 1;
            if (v[tmp] < v[a[j]]) { a[i] = a[j]; i = j; j += j; }
            else break;
        }
        a[i] = tmp;
    }
    for (; n > 1;) {
        tmp = a[n];
        a[n] = a[1];
        n -= 1;
        for (i = 1, j = 2; j <= n;) {
            if (j < n && v[a[j]] < v[a[j + 1]]) j++;
            if (v[tmp] < v[a[j]]) { a[i] = a[j]; i = j; j += j; }
            else break;
        }
        a[i] = tmp;
    }
}

/* numpy's scalar aquicksort_ on tosort[0 .. num), already holding the indices */
static void aquicksort_scalar(const int64_t *v, int64_t *tosort, int64_t num) {
    int64_t vp, vi;
    int64_t *pl = tosort, *pr = tosort + num - 1, *pm, *pi, *pj, *pk;
    int64_t *stack[PYA_QS_STACK], **sptr = stack;
    int depth[PYA_QS_STACK], *psdepth = depth;
    int cdepth = msb(num) * 2;
    for (;;) {
        if (cdepth < 0) {
            aheapsort(v, pl, pr - pl + 1);
            goto stack_pop;
        }
        while ((pr - pl) > SMALL_QUICKSORT) {
            pm = pl + ((pr - pl) >> 1);
            if (v[*pm] < v[*pl]) swap_i(pm, pl);
            if (v[*pr] < v[*pm]) swap_i(pr, pm);
            if (v[*pm] < v[*pl]) swap_i(pm, pl);
            vp = v[*pm];
            pi = pl;
            pj = pr - 1;
            swap_i(pm, pj);
            for (;;) {
                do { ++pi; } while (v[*pi] < vp);
                do { --pj; } while (vp < v[*pj]);
                if (pi >= pj) break;
                swap_i(pi, pj);
            }
            pk = pr - 1;
            swap_i(pi, pk);
            if (pi - pl < pr - pi) { *sptr++ = pi + 1; *sptr++ = pr; pr = pi - 1; }
            else { *sptr++ = pl; *sptr++ = pi - 1; pl = pi + 1; }
            *psdepth++ = --cdepth;
        }
        for (pi = pl + 1; pi <= pr; ++pi) {
            vi = *pi;
            vp = v[vi];
            pj = pi;
            pk = pi - 1;
            while (pj > pl && vp < v[*pk]) *pj-- = *pk--;
            *pj = vi;
        }
    stack_pop:
        if (sptr == stack) break;
        pr = *(--sptr);
        pl = *(--sptr);
        cdepth = *(--psdepth);
    }
}

/* whether numpy's X86_V3 dispatch would run here: the CPU at x86-64-v3 -- the x86-64-v2 set (SSE3, SSSE3, SSE4.1,
 * SSE4.2, POPCNT, CMPXCHG16B, LAHF) and AVX, AVX2, FMA, BMI1, BMI2, F16C, LZCNT, MOVBE -- with the OS saving the SSE and
 * AVX state (XGETBV), read with CPUID */
static int cpu_v3(void) {
#ifdef HAVE_AVX2_SORT
    unsigned a, b, c, d;
    if (!__get_cpuid(1, &a, &b, &c, &d)) return 0;
    const unsigned need1 = (1u << 0) | (1u << 9) | (1u << 12) | (1u << 13) | (1u << 19) | (1u << 20) | (1u << 22) | (1u << 23) |
                           (1u << 27) | (1u << 28) | (1u << 29);
    if ((c & need1) != need1) return 0;
    unsigned lo, hi;
    __asm__ volatile("xgetbv" : "=a"(lo), "=d"(hi) : "c"(0));
    (void)hi;
    if ((lo & 6u) != 6u) return 0;
    if (!__get_cpuid_count(7, 0, &a, &b, &c, &d)) return 0;
    const unsigned need7 = (1u << 3) | (1u << 5) | (1u << 8);
    if ((b & need7) != need7) return 0;
    if (!__get_cpuid(0x80000001u, &a, &b, &c, &d)) return 0;
    return (c & 1u) && (c & (1u << 5));
#else
    return 0;
#endif
}

/* -> 0; -2 refused (more than 256 values on the SIMD path); arg gets the order */
RF_API int32_t rf_np_argsort_i64(const int64_t *a, int64_t *arg, int64_t n) {
    if (n <= 0) return 0;
#ifdef HAVE_AVX2_SORT
    if (cpu_v3()) {
        if (n > 256) return -2;      /* unreachable from the model: the palette has at most 256 colors (the median cut's cap) */
        rf_np_argsort_avx2(a, arg, n);
        return 0;
    }
#endif
    for (int64_t i = 0; i < n; i++) arg[i] = i;
    if (n > 1) aquicksort_scalar(a, arg, n);
    return 0;
}

/* the scalar path alone (for its identity check against numpy with its SIMD dispatch switched off) */
RF_API int32_t rf_np_argsort_i64_scalar(const int64_t *a, int64_t *arg, int64_t n) {
    if (n <= 0) return 0;
    for (int64_t i = 0; i < n; i++) arg[i] = i;
    if (n > 1) aquicksort_scalar(a, arg, n);
    return 0;
}
