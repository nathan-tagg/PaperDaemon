/* The region budget's merge rounds and the recolored picture: rm_regions.merge_to_budget and rm_regions.recolored,
 * with numpy's and scipy's arithmetic, step for step (DECISION code: which pieces merge into which).
 *
 * Each round:
 *   statistics and borders: regions.c's rf_region_stats and rf_region_edges (proven against _stats and _edges);
 *   the nearest-color drawable neighbor of every color piece: np.lexsort((dcol, src)) and the first row per src, i.e.
 *     the smallest dcol, the earliest row among equal ones (the a -> b rows before the b -> a rows, each in key order);
 *     dcol = sqrt((d0*d0 + d1*d1) + d2*d2) of the mean Lab difference, the mean = sum / max(area, 1);
 *   contrast: np.bincount(a, sde) + np.bincount(b, sde) (each a sum in row order from 0.0) over the same of the counts
 *     (at least 1.0);
 *   rarity: how many pieces share (class, floor(log2(max(area, 1)))) among the drawable ones, all the others sharing
 *     one key (np.unique(axis=0)'s counts read back per piece);
 *   density: np.add.at counts of the drawable pieces per cell (cx // cell, cy // cell: numpy's float floor_divide,
 *     which is CPython's float //), then scipy.ndimage.uniform_filter(size 3, mode "nearest"): axis 0, then axis 1 on
 *     the result, each line NI_UniformFilter1D's running sum (the first three values summed from 0.0, then
 *     tmp += in[i + 2] - in[i - 1], each output tmp / 3);
 *   value_of: its five terms added left to right (area * ppg * ppg as (area * ppg) * ppg); np.log and np.log2 are the
 *     C runtime's log and log2 on this build (ucrtbase.dll on Windows, resolved by lab.c);
 *   the picks: the k smallest values among the candidates, ties by index (np.argsort kind="stable"), with k Python's
 *     int(min(pool - budget, max(1, ROUND_FRACTION * pool)));
 *   the merge: scipy.sparse.csgraph.connected_components(directed=False) numbers the components by their smallest
 *     node, as a union-find relabeled in node order does; each component is named after its first member in
 *     np.lexsort((-area, picked, comp)): unpicked before picked, larger area first, lower index first.
 * The recolor: every pixel of a final region outside the piece the region is named after takes the mean source color
 * of the pixels inside it (sums in raster order), as uint8(clip(mean + 0.5, 0, 255)).
 * Proven: a check runs rm_regions' own functions and these on real pictures and budgets and compares
 * every round (kind, pool, picks, value cut), the final labels, names, classes, flags and the recolored picture.
 * Every allocation is checked; a failure returns -1 with nothing left allocated. */
#include <math.h>
#include <stdlib.h>
#include <string.h>
#include "rmfast.h"
#include "internal.h"

typedef struct { double v; int32_t i; } vi_t;

static int cmp_vi(const void *a, const void *b) {
    const vi_t *x = (const vi_t *)a, *y = (const vi_t *)b;
    if (x->v < y->v) return -1;
    if (x->v > y->v) return 1;
    return (x->i > y->i) - (x->i < y->i);
}

static int32_t uf_find(int32_t *par, int32_t x) {
    int32_t r = x;
    while (par[r] != r) r = par[r];
    while (par[x] != r) { int32_t nx = par[x]; par[x] = r; x = nx; }
    return r;
}

/* scipy's NI_UniformFilter1D with size 3, mode "nearest", origin 0, on the n values a[0], a[st], ... (n >= 1),
 * in place: the line is copied into buf (n + 2 values, the edges repeated) first, as scipy's line buffer is */
void rf_uniform3(double *a, int64_t n, int64_t st, double *buf) {
    buf[0] = a[0];
    for (int64_t i = 0; i < n; i++) buf[i + 1] = a[i * st];
    buf[n + 1] = a[(n - 1) * st];
    double tmp = 0.0;
    for (int ll = 0; ll < 3; ll++) tmp += buf[ll];
    a[0] = tmp / 3.0;
    for (int64_t ll = 1; ll < n; ll++) {
        tmp += buf[ll + 2] - buf[ll - 1];
        a[ll * st] = tmp / 3.0;
    }
}

/* labels0: the pieces (H x W, -1 for none); cls_of / n: each piece's class; frozen_cls: per class, 1 when not a color
 * class; knobs: area, contrast, rarity, density, elong, contrast_floor. Out: labels (H x W) the final regions, and per
 * final region (room for n) orig_of, cls, frozen; per round (room for max_rounds) kind (0 specks, 1 budget), the
 * drawable pool, the merged count, the value cut (budget rounds), the seconds; counts = rounds, specks cut, color
 * pieces, drawable pieces, final color pieces, final drawable pieces. -> the final region count; -1 when memory ran
 * out; -2 when a budget round meets ppg 0 (where the Python's DENSITY_CELL_PAGE / ppg raises ZeroDivisionError). */
RF_API int32_t rf_merge_to_budget(const int32_t *labels0, int32_t H, int32_t W, const int32_t *cls_of, const uint8_t *frozen_cls, int32_t n,
                                  const double *lab_img, double ppg, int64_t budget, const double *knobs, double absorb_max_area,
                                  double cell_page, double round_fraction, int32_t max_rounds, int32_t cut_specks,
                                  int32_t *labels, int64_t *orig_of, int32_t *cls, uint8_t *frozen,
                                  int32_t *r_kind, int64_t *r_pool, int64_t *r_merged, double *r_cut, double *r_secs, int64_t *counts) {
    size_t N = (size_t)H * W, nn = (size_t)n + 1;
    int32_t ncls = 0;
    for (int32_t j = 0; j < n; j++) if (cls_of[j] + 1 > ncls) ncls = cls_of[j] + 1;
    double *area = (double *)malloc(sizeof(double) * nn), *sum_lab = (double *)malloc(sizeof(double) * 3 * nn);
    double *cx = (double *)malloc(sizeof(double) * nn), *cy = (double *)malloc(sizeof(double) * nn);
    double *bw = (double *)malloc(sizeof(double) * nn), *bh = (double *)malloc(sizeof(double) * nn);
    double *mean = (double *)malloc(sizeof(double) * 3 * nn), *best = (double *)malloc(sizeof(double) * nn);
    double *csa = (double *)malloc(sizeof(double) * nn), *csb = (double *)malloc(sizeof(double) * nn);
    double *cca = (double *)malloc(sizeof(double) * nn), *ccb = (double *)malloc(sizeof(double) * nn);
    double *value = (double *)malloc(sizeof(double) * nn);
    int64_t *gx = (int64_t *)malloc(sizeof(int64_t) * nn), *gy = (int64_t *)malloc(sizeof(int64_t) * nn), *band = (int64_t *)malloc(sizeof(int64_t) * nn);
    int64_t *tab = (int64_t *)malloc(sizeof(int64_t) * ((size_t)ncls * 64 + 1)), *tmp64 = (int64_t *)malloc(sizeof(int64_t) * nn);
    int32_t *target = (int32_t *)malloc(sizeof(int32_t) * nn), *pick = (int32_t *)malloc(sizeof(int32_t) * nn);
    int32_t *par = (int32_t *)malloc(sizeof(int32_t) * nn), *newid = (int32_t *)malloc(sizeof(int32_t) * nn);
    int32_t *comp = (int32_t *)malloc(sizeof(int32_t) * nn), *rep = (int32_t *)malloc(sizeof(int32_t) * nn), *tmp32 = (int32_t *)malloc(sizeof(int32_t) * nn);
    uint8_t *drawable = (uint8_t *)malloc(nn), *picked = (uint8_t *)malloc(nn), *tmp8 = (uint8_t *)malloc(nn);
    vi_t *cand = (vi_t *)malloc(sizeof(vi_t) * nn);
    double *hist = NULL, *line = NULL;
    int64_t *ea = NULL, *eb = NULL;
    double *ec = NULL, *ed = NULL;
    int32_t rc = -1;
    if (!area || !sum_lab || !cx || !cy || !bw || !bh || !mean || !best || !csa || !csb || !cca || !ccb || !value || !gx || !gy || !band || !tab ||
        !tmp64 || !target || !pick || !par || !newid || !comp || !rep || !tmp32 || !drawable || !picked || !tmp8 || !cand)
        goto done;
    rf_fn1 LOG = rf_crt_log(), LOG2 = rf_crt_log2();
    const double k_area = knobs[0], k_con = knobs[1], k_rar = knobs[2], k_den = knobs[3], k_el = knobs[4], k_floor = knobs[5];

    memcpy(labels, labels0, sizeof(int32_t) * N);
    int32_t m = n;
    for (int32_t j = 0; j < n; j++) { orig_of[j] = j; cls[j] = cls_of[j]; frozen[j] = frozen_cls[cls_of[j]] ? 1 : 0; }
    {   /* the report's starting counts */
        int64_t *a0 = tmp64, colors = 0, draw0 = 0;
        for (int32_t j = 0; j < n; j++) a0[j] = 0;
        for (size_t p = 0; p < N; p++) if (labels0[p] >= 0) a0[labels0[p]]++;
        for (int32_t j = 0; j < n; j++) {
            colors += !frozen[j];
            draw0 += !frozen[j] && (double)a0[j] > absorb_max_area;
        }
        counts[1] = 0; counts[2] = colors; counts[3] = draw0;
    }
    int32_t nrounds = 0;
    for (int32_t rnd = 0; rnd < max_rounds; rnd++) {
        double t0 = rf_now();
        if (rf_region_stats(labels, lab_img, H, W, m, area, sum_lab, cx, cy, bw, bh) != 0) goto done;
        int64_t pool = 0;
        for (int32_t j = 0; j < m; j++) { drawable[j] = !frozen[j] && area[j] > absorb_max_area; pool += drawable[j]; }
        int32_t E = rf_region_edges(labels, lab_img, H, W, m, &ea, &eb, &ec, &ed);
        if (E < 0) goto done;
        for (int32_t j = 0; j < m; j++) {
            double s = area[j] > 1.0 ? area[j] : 1.0;
            mean[3 * j] = sum_lab[3 * j] / s; mean[3 * j + 1] = sum_lab[3 * j + 1] / s; mean[3 * j + 2] = sum_lab[3 * j + 2] / s;
            target[j] = -1;
        }
        for (int pass = 0; pass < 2; pass++)
            for (int32_t e = 0; e < E; e++) {
                int64_t src = pass ? eb[e] : ea[e], dst = pass ? ea[e] : eb[e];
                if (frozen[src] || !drawable[dst]) continue;
                double d0 = mean[3 * src] - mean[3 * dst], d1 = mean[3 * src + 1] - mean[3 * dst + 1], d2 = mean[3 * src + 2] - mean[3 * dst + 2];
                double dcol = sqrt((d0 * d0 + d1 * d1) + d2 * d2);
                if (target[src] < 0 || dcol < best[src]) { target[src] = (int32_t)dst; best[src] = dcol; }
            }
        int64_t nspecks = 0;
        for (int32_t j = 0; j < m; j++) nspecks += !frozen[j] && !drawable[j] && target[j] >= 0;
        int32_t npick = 0, kind;
        double cut = 0.0;
        if (rnd == 0 && cut_specks && nspecks > 0) {
            for (int32_t j = 0; j < m; j++) if (!frozen[j] && !drawable[j] && target[j] >= 0) pick[npick++] = j;
            kind = 0;
            counts[1] = nspecks;
        } else {
            if (pool <= budget) break;
            for (int32_t j = 0; j < m; j++) { csa[j] = csb[j] = cca[j] = ccb[j] = 0.0; }
            for (int32_t e = 0; e < E; e++) { csa[ea[e]] += ed[e]; cca[ea[e]] += ec[e]; }
            for (int32_t e = 0; e < E; e++) { csb[eb[e]] += ed[e]; ccb[eb[e]] += ec[e]; }
            /* rarity: (class, band) counts among the drawable pieces; the others all share one key */
            for (size_t t = 0; t < (size_t)ncls * 64; t++) tab[t] = 0;
            int64_t others = 0;
            for (int32_t j = 0; j < m; j++) {
                /* area >= 1 and at most H * W < 2^62: the band is in 0..61 and the clamp never binds */
                double bd = floor(LOG2(area[j] > 1.0 ? area[j] : 1.0));
                band[j] = bd < 0.0 ? 0 : (bd > 63.0 ? 63 : (int64_t)bd);
                if (drawable[j]) tab[(size_t)cls[j] * 64 + (size_t)band[j]]++;
                else others++;
            }
            if (ppg == 0.0) { rc = -2; goto done; }    /* the Python's DENSITY_CELL_PAGE / ppg raises here */
            double cell = (cell_page / ppg > 4.0) ? cell_page / ppg : 4.0;
            int64_t gxm = 0, gym = 0;
            for (int32_t j = 0; j < m; j++) {
                /* the centers lie in [0, W) x [0, H): the cells are in range and the clamps never bind */
                double fx = rf_py_floordiv(cx[j], cell), fy = rf_py_floordiv(cy[j], cell);
                gx[j] = fx < 0.0 ? 0 : (fx > (double)W ? (int64_t)W : (int64_t)fx);
                gy[j] = fy < 0.0 ? 0 : (fy > (double)H ? (int64_t)H : (int64_t)fy);
                if (gx[j] > gxm) gxm = gx[j];
                if (gy[j] > gym) gym = gy[j];
            }
            int64_t hw_ = gxm + 1, hh = gym + 1;
            hist = (double *)calloc((size_t)hw_ * (size_t)hh, sizeof(double));
            line = (double *)malloc(sizeof(double) * (size_t)((hw_ > hh ? hw_ : hh) + 2));
            if (!hist || !line) goto done;
            for (int32_t j = 0; j < m; j++) if (drawable[j]) hist[(size_t)gy[j] * (size_t)hw_ + (size_t)gx[j]] += 1.0;
            for (int64_t x = 0; x < hw_; x++) rf_uniform3(hist + x, hh, hw_, line);
            for (int64_t y = 0; y < hh; y++) rf_uniform3(hist + (size_t)y * (size_t)hw_, hw_, 1, line);
            int32_t nc = 0;
            for (int32_t j = 0; j < m; j++) {
                double contrast = (csa[j] + csb[j]) / ((cca[j] + ccb[j]) > 1.0 ? (cca[j] + ccb[j]) : 1.0);
                double rarity = (double)(drawable[j] ? tab[(size_t)cls[j] * 64 + (size_t)band[j]] : others);
                double density = hist[(size_t)gy[j] * (size_t)hw_ + (size_t)gx[j]];
                double s = area[j] > 1.0 ? area[j] : 1.0;
                double elong = (bw[j] > bh[j] ? bw[j] : bh[j]) / sqrt(s);
                double ap = area[j] * ppg * ppg;
                value[j] = k_area * LOG(ap > 1e-3 ? ap : 1e-3) + k_con * LOG(contrast + k_floor) - k_rar * LOG(rarity > 1.0 ? rarity : 1.0)
                           - k_den * LOG(density > 1.0 ? density : 1.0) + k_el * LOG(elong > 1.0 ? elong : 1.0);
                if (target[j] >= 0 && drawable[j]) { cand[nc].v = value[j]; cand[nc].i = j; nc++; }
            }
            free(hist); hist = NULL;
            free(line); line = NULL;
            if (!nc) break;
            double f = round_fraction * (double)pool;
            double mx = f > 1.0 ? f : 1.0;                 /* max(1, f) */
            int64_t over = pool - budget;
            int64_t k = mx < (double)over ? (int64_t)mx : over;
            qsort(cand, (size_t)nc, sizeof(vi_t), cmp_vi);
            if (k > nc) k = nc;
            for (int64_t t = 0; t < k; t++) pick[npick++] = cand[t].i;
            cut = value[pick[0]];
            for (int32_t t = 1; t < npick; t++) if (value[pick[t]] > cut) cut = value[pick[t]];
            kind = 1;
        }
        /* this round's merges: every node joined through a picked edge becomes one region */
        for (int32_t j = 0; j < m; j++) { par[j] = j; picked[j] = 0; newid[j] = -1; rep[j] = -1; }
        for (int32_t t = 0; t < npick; t++) {
            int32_t a = uf_find(par, pick[t]), b = uf_find(par, target[pick[t]]);
            if (a != b) par[a < b ? b : a] = a < b ? a : b;
            picked[pick[t]] = 1;
        }
        int32_t ncomp = 0;
        for (int32_t j = 0; j < m; j++) {
            int32_t r = uf_find(par, j);
            if (newid[r] < 0) newid[r] = ncomp++;
            comp[j] = newid[r];
        }
        for (int32_t j = 0; j < m; j++) {
            int32_t c = comp[j], b = rep[c];
            if (b < 0 || picked[j] < picked[b] || (picked[j] == picked[b] && area[j] > area[b])) rep[c] = j;
        }
        for (size_t p = 0; p < N; p++) if (labels[p] >= 0) labels[p] = comp[labels[p]];
        for (int32_t c = 0; c < ncomp; c++) tmp32[c] = cls[rep[c]];
        memcpy(cls, tmp32, sizeof(int32_t) * (size_t)ncomp);
        for (int32_t c = 0; c < ncomp; c++) tmp8[c] = frozen[rep[c]];
        memcpy(frozen, tmp8, (size_t)ncomp);
        for (int32_t c = 0; c < ncomp; c++) tmp64[c] = orig_of[rep[c]];
        memcpy(orig_of, tmp64, sizeof(int64_t) * (size_t)ncomp);
        m = ncomp;
        r_kind[nrounds] = kind; r_pool[nrounds] = pool; r_merged[nrounds] = npick; r_cut[nrounds] = cut; r_secs[nrounds] = rf_now() - t0;
        nrounds++;
        free(ea); free(eb); free(ec); free(ed);
        ea = eb = NULL; ec = ed = NULL;
    }
    {   /* the final counts */
        int64_t *af = tmp64, colors = 0, draw = 0;
        for (int32_t j = 0; j < m; j++) af[j] = 0;
        for (size_t p = 0; p < N; p++) if (labels[p] >= 0) af[labels[p]]++;
        for (int32_t j = 0; j < m; j++) {
            colors += !frozen[j];
            draw += !frozen[j] && (double)af[j] > absorb_max_area;
        }
        counts[0] = nrounds; counts[4] = colors; counts[5] = draw;
    }
    rc = m;
done:
    free(ea); free(eb); free(ec); free(ed); free(hist); free(line);
    free(area); free(sum_lab); free(cx); free(cy); free(bw); free(bh); free(mean); free(best); free(csa); free(csb); free(cca); free(ccb);
    free(value); free(gx); free(gy); free(band); free(tab); free(tmp64); free(target); free(pick); free(par); free(newid); free(comp); free(rep);
    free(tmp32); free(drawable); free(picked); free(tmp8); free(cand);
    return rc;
}

/* rm_regions.recolored's pixels: out = rgb, then every pixel of a final region (labels) that lies outside the piece
 * the region is named after (labels0 != orig_of[region]) takes that piece's mean color. -> the count of such pixels,
 * or -1 when memory ran out. */
RF_API int64_t rf_recolor(const uint8_t *rgb, const int32_t *labels0, const int32_t *labels, int32_t H, int32_t W, const int64_t *orig_of, int32_t m,
                          uint8_t *out) {
    size_t N = (size_t)H * W;
    double *cnt = (double *)calloc((size_t)m + 1, sizeof(double)), *sum = (double *)calloc(3 * ((size_t)m + 1), sizeof(double));
    if (!cnt || !sum) { free(cnt); free(sum); return -1; }
    memcpy(out, rgb, 3 * N);
    for (size_t p = 0; p < N; p++) {
        int32_t r = labels[p];
        if (r < 0 || (int64_t)labels0[p] != orig_of[r]) continue;
        cnt[r] += 1.0;
        sum[3 * (size_t)r] += (double)rgb[3 * p]; sum[3 * (size_t)r + 1] += (double)rgb[3 * p + 1]; sum[3 * (size_t)r + 2] += (double)rgb[3 * p + 2];
    }
    int64_t moved = 0;
    for (size_t p = 0; p < N; p++) {
        int32_t r = labels[p];
        if (r < 0 || (int64_t)labels0[p] == orig_of[r]) continue;
        double s = cnt[r] > 1.0 ? cnt[r] : 1.0;
        for (int c = 0; c < 3; c++) {
            double v = sum[3 * (size_t)r + c] / s + 0.5;
            if (v < 0.0) v = 0.0;
            if (v > 255.0) v = 255.0;
            out[3 * p + c] = (uint8_t)v;
        }
        moved++;
    }
    free(cnt); free(sum);
    return moved;
}
