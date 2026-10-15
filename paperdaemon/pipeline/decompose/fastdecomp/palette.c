/* palette.c -- rm_paint.quantize as the painter calls it (no blur, not exact, no despeckle median, CEL_DE > 0, no device
 * chroma clamp, no white floor), whole: DECISION code -- every grid pixel's class.
 *
 * The Python's steps, in order:
 *   Pillow's MEDIANCUT of the grid picture (mediancut.c, Pillow's own code vendored) read back as RGB; np.unique of the
 *     packed colors (quant.c rf_unique_rgb);
 *   _cel_palette: each color's pixel count, its Lab (lab.c, _lab_rows' arithmetic), its device Lab (np.hypot -- the C
 *     runtime's _hypot -- and the chroma ceiling CEIL / C); the colors visited in np.argsort(-counts) order, equal
 *     counts included (npsort.c: numpy's own argsort for this machine); each one's nearest leader by
 *     math.sqrt(float((d0 ** 2 + d1 ** 2) + d2 ** 2)) with numpy's scalar ** 2 (the C runtime's pow), the first of equal
 *     distances, joined when <= CEL_DE, else a new leader; the kept colors in index order and every pixel's new index;
 *   classify_many: the class ladder per palette color (paper, black, tone, base, rgb) on its Lab and CPython's
 *     math.hypot chroma, each wash keyed by _tc_key (Python's half-to-even round, twice);
 *   the color slots in first-appearance order, the neutral and chromatic flags, the cel window r, each color's
 *     luminance (0.299 r + 0.587 g) + 0.114 b, the three cuts int(round(v * 2.55));
 *   the per-pixel work (quant.c rf_quant_tail: Pillow's L, the cel pass, the class masks, first positions, counts);
 *   the dict's order: tone, black and the washes by first raster position (2 p, and 2 p + 1 for a wash's base
 *     pixels), "_ink" last.
 * Identity: every call of real model runs through rm_paint.quantize and through this (keys, order, pixels and the
 * cover), and the sort's own check (npsort.c). */
#include <float.h>
#include <math.h>
#include <stdlib.h>
#include <string.h>
#include "rmfast.h"
#include "internal.h"

static int64_t round_i(double x) {
    double r = rint(x);
    if (r > 2147483647.0) r = 2147483647.0;
    if (r < -2147483648.0) r = -2147483648.0;
    return (int64_t)r;
}
static int finite_d(double x) { return x >= -DBL_MAX && x <= DBL_MAX; }

/* rm_paint._tc_key of one channel */
static int32_t tc_chan(int64_t c, double step) { return (int32_t)round_i(rint((double)c / step) * step); }

typedef struct { int64_t pos; int32_t kind, slot; } qorder;        /* kind 0 tone, 1 black, 2 a wash (slot) */
static int cmp_qorder(const void *a, const void *b) {
    const qorder *x = (const qorder *)a, *y = (const qorder *)b;
    return x->pos < y->pos ? -1 : (x->pos > y->pos);
}

int rf_quant_params_ok(const rf_quant_params *Q) {
    const double v[] = {Q->black_l, Q->chroma_min, Q->detail, Q->ppg, Q->cel_de, Q->dev_chroma_ceil, Q->tc_paper_l, Q->tc_paper_chroma,
                        Q->tc_ink_chroma, Q->ink_neutral, Q->ink_sat, Q->black_chroma, Q->tc_ink_l, Q->ink_chroma_max, Q->ink_l,
                        Q->paper_l, Q->cel_color_r, Q->up, Q->cel_mode_max_dl, Q->detail_precise, Q->despeckle_max_ppg};
    for (size_t i = 0; i < sizeof(v) / sizeof(v[0]); i++) if (!finite_d(v[i])) return 0;
    return Q->tc_quant >= 2 && Q->clusters >= 1 && Q->clusters <= 256 && Q->detail > 0.0 && Q->cel_de > 0.0 && Q->dev_chroma_ceil >= 0.0;
}

/* -> the key count (tone / black / washes in the dict's order, then _ink), -1 out of memory, -2 refused (a call the
 * painter does not make: the despeckle median, or parameters out of range). keys: 4 ints per key (kind 0 tone, 1 black,
 * 2 rgb, 3 _ink; r, g, b); planes: one H x W 0/255 grid per key; counts: each key's pixels (the cover). All three
 * rf_free'd by the caller (each plane too). */
RF_API int32_t rf_quantize(const uint8_t *rgb, int32_t H, int32_t W, const rf_quant_params *Q, int32_t **keys_out, uint8_t ***planes_out,
                           int64_t **counts_out) {
    *keys_out = NULL; *planes_out = NULL; *counts_out = NULL;
    if (H <= 0 || W <= 0 || !rf_quant_params_ok(Q)) return -2;
    if (Q->detail < Q->detail_precise && Q->ppg <= Q->despeckle_max_ppg) return -2;          /* the 3 x 3 median: not run */
    size_t N = (size_t)H * (size_t)W;
    int32_t rc = -1, nu = 0, nk = 0, n2 = 0;
    uint8_t *q = (uint8_t *)malloc(3 * N), *tone = NULL, *black = NULL, *ink = NULL, **karr = NULL, **planes = NULL;
    int32_t *codes = (int32_t *)malloc(sizeof(int32_t) * 65536), *inv = (int32_t *)malloc(sizeof(int32_t) * N);
    int32_t *keys = NULL, *kidx = NULL, *ckeys = NULL;
    int64_t *first = NULL, *cnts = NULL, *counts = NULL;
    int8_t *cat = NULL;
    if (!q || !codes || !inv) goto done;
    if (rf_mediancut(rgb, (int64_t)N, Q->clusters, q) < 0) goto done;
    nu = rf_unique_rgb(q, (int64_t)N, codes, 65536, inv);
    if (nu < 0) goto done;
    if (nu > 256) { rc = -2; goto done; }            /* a median cut of at most 256 colors has at most 256 */
    rf_pow_fn pw = rf_crt_pow(), hyp = rf_crt_hypot();
    double lut[256];
    rf_lab_lut(pw, lut);
    uint8_t uc[256 * 3];
    double lab[256 * 3], dlab[256 * 3];
    int64_t ucount[256] = {0}, negc[256], ord[256];
    for (int32_t i = 0; i < nu; i++) {
        uc[3 * i] = (uint8_t)((codes[i] >> 16) & 255); uc[3 * i + 1] = (uint8_t)((codes[i] >> 8) & 255); uc[3 * i + 2] = (uint8_t)(codes[i] & 255);
        rf_lab_px(lut, pw, uc + 3 * i, lab + 3 * i);
        double C = hyp(lab[3 * i + 1], lab[3 * i + 2]), k = 1.0;
        if (C > Q->dev_chroma_ceil) k = Q->dev_chroma_ceil / C;             /* C > the ceiling >= 0 (validated): C > 0 */
        dlab[3 * i] = lab[3 * i]; dlab[3 * i + 1] = lab[3 * i + 1] * k; dlab[3 * i + 2] = lab[3 * i + 2] * k;
    }
    for (size_t p = 0; p < N; p++) ucount[inv[p]]++;
    for (int32_t i = 0; i < nu; i++) negc[i] = -ucount[i];
    if (rf_np_argsort_i64(negc, ord, nu) != 0) { rc = -2; goto done; }
    /* _cel_palette's leader clustering */
    int32_t lead[256], nl = 0, remap[256];
    for (int32_t t = 0; t < nu; t++) {
        int32_t i = (int32_t)ord[t];
        if (ucount[i] == 0) { remap[i] = nl ? lead[0] : 0; continue; }
        int32_t best = -1; double bd = 0.0;
        for (int32_t s = 0; s < nl; s++) {
            int32_t j = lead[s];
            double e0 = pw(dlab[3 * i] - dlab[3 * j], 2.0), e1 = pw(dlab[3 * i + 1] - dlab[3 * j + 1], 2.0), e2 = pw(dlab[3 * i + 2] - dlab[3 * j + 2], 2.0);
            double d = sqrt((e0 + e1) + e2);
            if (best < 0 || d < bd) { best = j; bd = d; }
        }
        if (best >= 0 && bd <= Q->cel_de) remap[i] = best;
        else { lead[nl++] = i; remap[i] = i; }
    }
    int32_t newidx[256], keep[256];
    uint8_t used[256] = {0};
    for (int32_t i = 0; i < nu; i++) used[remap[i]] = 1;
    for (int32_t i = 0; i < nu; i++) if (used[i]) { newidx[i] = n2; keep[n2++] = i; }
    for (size_t p = 0; p < N; p++) inv[p] = newidx[remap[inv[p]]];
    /* classify_many on the kept colors, the slots, the flags */
    double ulum[256], uch[256];
    uint8_t nflag[256], cflag[256];
    cat = (int8_t *)malloc(256); kidx = (int32_t *)malloc(sizeof(int32_t) * 256); ckeys = (int32_t *)malloc(sizeof(int32_t) * 3 * 256);
    if (!cat || !kidx || !ckeys) goto done;
    const double step = 255.0 / (double)(Q->tc_quant - 1);
    for (int32_t t = 0; t < n2; t++) {
        const uint8_t *c = uc + 3 * keep[t];
        const double *lb = lab + 3 * keep[t];
        double L = lb[0], chroma = rf_py_hypot(lb[1], lb[2]);
        uch[t] = chroma;
        int inkish = chroma < Q->tc_ink_chroma && (chroma <= Q->ink_neutral || chroma <= Q->ink_sat * L);
        int k;                                            /* 0 paper, 1 base, 2 black / tone, 3 rgb */
        if (L >= Q->tc_paper_l && chroma < Q->tc_paper_chroma) k = 0;
        else if (inkish && L < Q->black_l && chroma < Q->black_chroma) k = 2;
        else if (inkish && L < Q->tc_ink_l) k = Q->dark_gray_washed ? 1 : 2;
        else if (chroma < Q->chroma_min) k = 1;
        else k = 3;
        cat[t] = (int8_t)k;
        kidx[t] = -1;
        if (k == 1 || k == 3) {
            int32_t tc[3] = {tc_chan(c[0], step), tc_chan(c[1], step), tc_chan(c[2], step)}, s;
            for (s = 0; s < nk; s++) if (ckeys[3 * s] == tc[0] && ckeys[3 * s + 1] == tc[1] && ckeys[3 * s + 2] == tc[2]) break;
            if (s == nk) { ckeys[3 * nk] = tc[0]; ckeys[3 * nk + 1] = tc[1]; ckeys[3 * nk + 2] = tc[2]; nk++; }
            kidx[t] = s;
        }
        nflag[t] = (uint8_t)(chroma <= Q->ink_neutral || chroma <= Q->ink_sat * L);
        cflag[t] = (uint8_t)(chroma >= Q->ink_chroma_max);
        ulum[t] = (0.299 * c[0] + 0.587 * c[1]) + 0.114 * c[2];
    }
    int32_t mode_r = 0;                                   /* max(1, int(round(_gu(CEL_COLOR_R) / max(0.5, detail)))) */
    if (Q->cel_color_r > 0) {
        int64_t r = round_i((Q->cel_color_r * Q->up) / (Q->detail > 0.5 ? Q->detail : 0.5));
        mode_r = (int32_t)(r > 1 ? r : 1);
    }
    tone = (uint8_t *)malloc(N); black = (uint8_t *)malloc(N); ink = (uint8_t *)malloc(N);
    karr = (uint8_t **)calloc((size_t)(nk > 0 ? nk : 1), sizeof(uint8_t *));
    first = (int64_t *)malloc(sizeof(int64_t) * (size_t)(2 + 2 * nk)); cnts = (int64_t *)malloc(sizeof(int64_t) * (size_t)(3 + nk));
    if (!tone || !black || !ink || !karr || !first || !cnts) goto done;
    for (int32_t s = 0; s < nk; s++) if (!(karr[s] = (uint8_t *)malloc(N))) goto done;
    if (rf_quant_tail(inv, n2, ulum, nflag, cflag, uch, cat, kidx, nk, rgb, H, W, mode_r, Q->cel_mode_max_dl, (int32_t)round_i(Q->black_l * 2.55),
                      (int32_t)round_i(Q->ink_l * 2.55), (int32_t)round_i(Q->paper_l * 2.55), Q->black_chroma, tone, black, karr, ink, first,
                      cnts) != 0) goto done;
    /* the dict's order */
    qorder *ord2 = (qorder *)malloc(sizeof(qorder) * (size_t)(2 + nk));
    if (!ord2) goto done;
    int32_t no = 0;
    if (first[0] >= 0) { ord2[no].pos = 2 * first[0]; ord2[no].kind = 0; ord2[no].slot = -1; no++; }
    if (first[1] >= 0) { ord2[no].pos = 2 * first[1]; ord2[no].kind = 1; ord2[no].slot = -1; no++; }
    for (int32_t s = 0; s < nk; s++) {
        int64_t f3 = first[2 + 2 * s], f1 = first[3 + 2 * s];
        if (f3 < 0 && f1 < 0) continue;
        int64_t pos = f3 >= 0 ? 2 * f3 : 2 * f1 + 1;
        if (f1 >= 0 && 2 * f1 + 1 < pos) pos = 2 * f1 + 1;
        ord2[no].pos = pos; ord2[no].kind = 2; ord2[no].slot = s; no++;
    }
    qsort(ord2, (size_t)no, sizeof(qorder), cmp_qorder);      /* the positions are distinct: the order is the stable one */
    keys = (int32_t *)malloc(sizeof(int32_t) * 4 * (size_t)(no + 1));
    planes = (uint8_t **)calloc((size_t)(no + 1), sizeof(uint8_t *));
    counts = (int64_t *)malloc(sizeof(int64_t) * (size_t)(no + 1));
    if (!keys || !planes || !counts) { free(ord2); goto done; }
    for (int32_t t = 0; t < no; t++) {
        const qorder *o = &ord2[t];
        if (o->kind == 0) { keys[4 * t] = 0; keys[4 * t + 1] = keys[4 * t + 2] = keys[4 * t + 3] = 0; planes[t] = tone; tone = NULL; counts[t] = cnts[0]; }
        else if (o->kind == 1) { keys[4 * t] = 1; keys[4 * t + 1] = keys[4 * t + 2] = keys[4 * t + 3] = 0; planes[t] = black; black = NULL; counts[t] = cnts[1]; }
        else {
            keys[4 * t] = 2; keys[4 * t + 1] = ckeys[3 * o->slot]; keys[4 * t + 2] = ckeys[3 * o->slot + 1]; keys[4 * t + 3] = ckeys[3 * o->slot + 2];
            planes[t] = karr[o->slot]; karr[o->slot] = NULL; counts[t] = cnts[3 + o->slot];
        }
    }
    keys[4 * no] = 3; keys[4 * no + 1] = keys[4 * no + 2] = keys[4 * no + 3] = 0;
    planes[no] = ink; ink = NULL; counts[no] = cnts[2];
    free(ord2);
    *keys_out = keys; *planes_out = planes; *counts_out = counts;
    keys = NULL; planes = NULL; counts = NULL;
    rc = no + 1;

done:
    free(q); free(codes); free(inv); free(tone); free(black); free(ink); free(kidx); free(ckeys); free(first); free(cnts); free(cat);
    if (karr) for (int32_t s = 0; s < nk; s++) free(karr[s]);
    free(karr); free(keys); free(planes); free(counts);
    return rc;
}
