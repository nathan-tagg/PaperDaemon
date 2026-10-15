/* npsort_avx2.cpp -- numpy.argsort's X86_V3 (AVX2) build for int64: what numpy 2.5.3's x86_simd_argsort.dispatch.cpp
 * compiles for that target, x86simdsortStatic::argsort(arr, arg, size, true) from the vendored x86-simd-sort (unchanged,
 * vendor/x86-simd-sort). This file is built on its own with the X86_V3 flags only (build.py), so the library selects its
 * AVX2 code whatever -march the rest of the build uses; npsort.c calls it only on a CPU at that level, as numpy's
 * dispatch does. Arrays of at most 256 values only: past that the library can fall back to std::sort, whose order of
 * equal keys belongs to the C++ library numpy was built with.
 * Identity: np.argsort against this on random arrays with many equal keys, every length 0-256. */
#include <cstdint>
#include "x86simdsort-static-incl.h"

extern "C" void rf_np_argsort_avx2(const int64_t *a, int64_t *arg, int64_t n) {
    for (int64_t i = 0; i < n; i++) arg[i] = i;
    static_assert(sizeof(size_t) == sizeof(int64_t), "64-bit indices, as numpy's npy_intp");
    x86simdsortStatic::argsort(a, reinterpret_cast<size_t *>(arg), static_cast<size_t>(n), true);
}
