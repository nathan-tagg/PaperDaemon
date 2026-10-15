/* Worker threads for the stages whose pieces are independent (the pass's footprints and its join groups). Each
 * stage hands out its pieces through an atomic counter and keeps every piece's result in the piece's own slot, so the
 * output is assembled in the same order whatever the scheduling: the thread count changes the speed, never the result.
 * RMFAST_THREADS in the environment sets the count (1 = everything on the calling thread); the default is every
 * logical processor. A stage that runs inside another stage's worker (a plan inside the batch of plans) gets one
 * thread: the outer split already uses the cores.
 */
#include <stdlib.h>
#include "internal.h"

#ifdef _WIN32
#include <windows.h>
#else
#include <pthread.h>
#include <unistd.h>
#endif

static _Thread_local int in_pool;           /* this thread is running a share of an rf_parallel job */

int rf_threads(void) {
    if (in_pool) return 1;
    const char *e = getenv("RMFAST_THREADS");
    if (e && *e) {
        int n = atoi(e);
        return n < 1 ? 1 : (n > 256 ? 256 : n);
    }
#ifdef _WIN32
    DWORD n = GetActiveProcessorCount(ALL_PROCESSOR_GROUPS);
    return n < 1 ? 1 : (n > 256 ? 256 : (int)n);
#else
    long n = sysconf(_SC_NPROCESSORS_ONLN);
    return n < 1 ? 1 : (n > 256 ? 256 : (int)n);
#endif
}

typedef struct { void (*fn)(void *, int); void *arg; int tid; } job_t;

#ifdef _WIN32
static DWORD WINAPI run_job(LPVOID p) { job_t *j = (job_t *)p; in_pool = 1; j->fn(j->arg, j->tid); return 0; }
#else
static void *run_job(void *p) { job_t *j = (job_t *)p; in_pool = 1; j->fn(j->arg, j->tid); return NULL; }
#endif

static void run_here(void (*fn)(void *, int), void *arg, int tid) {
    int was = in_pool;
    in_pool = 1;
    fn(arg, tid);
    in_pool = was;
}

void rf_parallel(int n, void (*fn)(void *arg, int tid), void *arg) {
    if (n <= 1) { fn(arg, 0); return; }
    job_t *jobs = (job_t *)malloc(sizeof(job_t) * n);
#ifdef _WIN32
    HANDLE *h = (HANDLE *)calloc(n, sizeof(HANDLE));
    if (!jobs || !h) {                    /* no memory for the threads: every share on this thread, in order */
        free(jobs); free(h);
        for (int t = 0; t < n; t++) run_here(fn, arg, t);
        return;
    }
#else
    pthread_t *h = (pthread_t *)malloc(sizeof(pthread_t) * n);
    int *ok = (int *)calloc(n, sizeof(int));
    if (!jobs || !h || !ok) {
        free(jobs); free(h); free(ok);
        for (int t = 0; t < n; t++) run_here(fn, arg, t);
        return;
    }
#endif
    for (int t = 1; t < n; t++) {
        jobs[t].fn = fn; jobs[t].arg = arg; jobs[t].tid = t;
#ifdef _WIN32
        h[t] = CreateThread(NULL, 0, run_job, &jobs[t], 0, NULL);
#else
        ok[t] = pthread_create(&h[t], NULL, run_job, &jobs[t]) == 0;
#endif
    }
    run_here(fn, arg, 0);
    for (int t = 1; t < n; t++) {
#ifdef _WIN32
        if (h[t]) { WaitForSingleObject(h[t], INFINITE); CloseHandle(h[t]); }
        else run_here(fn, arg, t);       /* a thread that could not start: its share runs here */
#else
        if (ok[t]) pthread_join(h[t], NULL);
        else run_here(fn, arg, t);
#endif
    }
#ifndef _WIN32
    free(ok);
#endif
    free(h); free(jobs);
}
