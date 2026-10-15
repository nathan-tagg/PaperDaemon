/* numpy's float64 sum of a contiguous 1-D array (np.add.reduce -> DOUBLE_pairwise_sum): under 8 values a plain
 * running sum; up to 128, eight interleaved partial sums combined as ((r0+r1)+(r2+r3))+((r4+r5)+(r6+r7)) and the
 * remainder added after; above that, the two halves (the first a multiple of 8 long) summed recursively. The
 * reduction starts from the identity 0.0, so the result is 0.0 + pairwise(a). */
#include "rmfast.h"
#include "internal.h"

double rf_pairwise_sum(const double *a, int64_t n) {
    if (n < 8) {
        double res = 0.0;
        for (int64_t i = 0; i < n; i++) res += a[i];
        return res;
    }
    if (n <= 128) {
        double r[8], res;
        int64_t i;
        for (int j = 0; j < 8; j++) r[j] = a[j];
        for (i = 8; i < n - (n % 8); i += 8)
            for (int j = 0; j < 8; j++) r[j] += a[i + j];
        res = ((r[0] + r[1]) + (r[2] + r[3])) + ((r[4] + r[5]) + (r[6] + r[7]));
        for (; i < n; i++) res += a[i];
        return res;
    }
    int64_t n2 = n / 2;
    n2 -= n2 % 8;
    return rf_pairwise_sum(a, n2) + rf_pairwise_sum(a + n2, n - n2);
}

RF_API double rf_np_sum(const double *a, int64_t n) { return 0.0 + rf_pairwise_sum(a, n); }
