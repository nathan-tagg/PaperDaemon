/* Sorted unique int32 sets: numpy's union1d / setdiff1d / intersect1d / setxor1d / isin on assume_unique arrays,
 * and CPython's float floor division (GEOMETRY code). A set that cannot be allocated comes back NULL with its count
 * -1; the caller fails its stage. */
#include <math.h>
#include <stdlib.h>
#include "internal.h"

static int32_t *grab(int32_t n) { return (int32_t *)malloc(sizeof(int32_t) * (n > 0 ? n : 1)); }

int32_t rf_union_to(const int32_t *a, int32_t na, const int32_t *b, int32_t nb, int32_t *o) {
    int32_t i = 0, j = 0, k = 0;
    while (i < na && j < nb) {
        if (a[i] < b[j]) o[k++] = a[i++];
        else if (b[j] < a[i]) o[k++] = b[j++];
        else { o[k++] = a[i]; i++; j++; }
    }
    while (i < na) o[k++] = a[i++];
    while (j < nb) o[k++] = b[j++];
    return k;
}

int32_t rf_setdiff_to(const int32_t *a, int32_t na, const int32_t *b, int32_t nb, int32_t *o) {
    int32_t i = 0, j = 0, k = 0;
    while (i < na) {
        while (j < nb && b[j] < a[i]) j++;
        if (j < nb && b[j] == a[i]) { i++; continue; }
        o[k++] = a[i++];
    }
    return k;
}

int32_t rf_intersect_to(const int32_t *a, int32_t na, const int32_t *b, int32_t nb, int32_t *o) {
    int32_t i = 0, j = 0, k = 0;
    while (i < na && j < nb) {
        if (a[i] < b[j]) i++;
        else if (b[j] < a[i]) j++;
        else { o[k++] = a[i]; i++; j++; }
    }
    return k;
}

int32_t rf_setxor_to(const int32_t *a, int32_t na, const int32_t *b, int32_t nb, int32_t *o) {
    int32_t i = 0, j = 0, k = 0;
    while (i < na && j < nb) {
        if (a[i] < b[j]) o[k++] = a[i++];
        else if (b[j] < a[i]) o[k++] = b[j++];
        else { i++; j++; }
    }
    while (i < na) o[k++] = a[i++];
    while (j < nb) o[k++] = b[j++];
    return k;
}

int32_t *rf_union(const int32_t *a, int32_t na, const int32_t *b, int32_t nb, int32_t *n_out) {
    int32_t *o = grab(na + nb);
    if (!o) { *n_out = -1; return NULL; }
    *n_out = rf_union_to(a, na, b, nb, o);
    return o;
}

int32_t *rf_setdiff(const int32_t *a, int32_t na, const int32_t *b, int32_t nb, int32_t *n_out) {
    int32_t *o = grab(na);
    if (!o) { *n_out = -1; return NULL; }
    *n_out = rf_setdiff_to(a, na, b, nb, o);
    return o;
}

int32_t *rf_intersect(const int32_t *a, int32_t na, const int32_t *b, int32_t nb, int32_t *n_out) {
    int32_t *o = grab(na < nb ? na : nb);
    if (!o) { *n_out = -1; return NULL; }
    *n_out = rf_intersect_to(a, na, b, nb, o);
    return o;
}

int32_t *rf_setxor(const int32_t *a, int32_t na, const int32_t *b, int32_t nb, int32_t *n_out) {
    int32_t *o = grab(na + nb);
    if (!o) { *n_out = -1; return NULL; }
    *n_out = rf_setxor_to(a, na, b, nb, o);
    return o;
}
void rf_isin_add(const int32_t *a, int32_t na, const int32_t *b, int32_t nb, uint16_t *mine) {
    int32_t i = 0, j = 0;
    while (i < na && j < nb) {
        if (a[i] < b[j]) i++;
        else if (b[j] < a[i]) j++;
        else { mine[i] += 1; i++; j++; }
    }
}

double rf_py_floordiv(double a, double b) {
    double mod = fmod(a, b);
    double div = (a - mod) / b;
    if (mod != 0.0) {
        if ((b < 0) != (mod < 0)) { mod += b; div -= 1.0; }
    } else {
        mod = copysign(0.0, b);
    }
    double floordiv;
    if (div != 0.0) {
        floordiv = floor(div);
        if (div - floordiv > 0.5) floordiv += 1.0;
    } else {
        floordiv = copysign(0.0, a / b);
    }
    return floordiv;
}

/* numpy's float32 floor division (npy_floor_dividef -> npy_divmodf), the arithmetic of `np.float32 // float` under
 * NEP 50: the Python float is cast to float32 and every step is single precision. */
float rf_np_floordivf(float a, float b) {
    if (b == 0.0f) return a / b;
    float mod = fmodf(a, b);
    float div = (a - mod) / b;
    if (mod != 0.0f) {
        if ((b < 0) != (mod < 0)) { mod += b; div -= 1.0f; }
    } else {
        mod = copysignf(0.0f, b);
    }
    float floordiv;
    if (div != 0.0f) {
        floordiv = floorf(div);
        if (div - floordiv > 0.5f) floordiv += 1.0f;
    } else {
        floordiv = copysignf(0.0f, a / b);
    }
    return floordiv;
}

/* a monotonic clock in seconds, for the stages' phase timers */
#ifdef _WIN32
__declspec(dllimport) int __stdcall QueryPerformanceCounter(long long *count);
__declspec(dllimport) int __stdcall QueryPerformanceFrequency(long long *freq);
double rf_now(void) { long long f, c; QueryPerformanceFrequency(&f); QueryPerformanceCounter(&c); return (double)c / (double)f; }
#else
#include <time.h>
double rf_now(void) { struct timespec t; clock_gettime(CLOCK_MONOTONIC, &t); return t.tv_sec + 1e-9 * t.tv_nsec; }
#endif
