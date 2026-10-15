/* inkpass.c -- rm_paint.decompose's achromatic ink section and its contour pass (the painter's lines from
 * `ink = masks.get("_ink")` to the last contour line) as the painter runs them: SUBCELL_GEOMETRY and INK_AS_FILL on, no
 * flow hatch, no backstop, no soft edges, the contour pass on the ink ridge, hatch in black. DECISION code: which
 * pieces are washed, filled solid, dropped from the shade or hatched, and the order the strokes go down in. The stroke
 * points are made elsewhere: the fills by the ring planner through the store (store.c rf_store_fill_batch), the hatch
 * by hatch.c, the centerlines by skel.c, placed with rm_trace.place's arithmetic (plan.c, hatch.c).
 *
 * The Python's lines, in order (its masks are 0/255 images and every ImageChops step on them is the boolean operation
 * done here):
 *   colored = the union of the color classes; hatch = black, then hatch | (tone & ~colored);
 *   the tone-region wash: body = dilate(erode(tone, k), k) & tone & ~colored & ~black (k = _ker(TONE_REGION_OPEN)),
 *     each piece of components(body, draw_min, DRAW_MIN_AREA) a wash of its mean color (int() of each channel's exact
 *     sum over the count);
 *   the shade zones (zones.c rf_shadow_zones) added to hatch;
 *   the ink line loop is not run: under SUBCELL_GEOMETRY and INK_AS_FILL draw_component returns at once, so it draws
 *     nothing and takes nothing out of any mask;
 *   the black pass over components(ink, 1, 0): the ink density (specks.c rf_ink_density), the covered-speck test
 *     against colored (specks.c rf_speck_skip), each piece's decision (black.c): a no-core or mass wash of its color,
 *     or a solid fill (the marker plan) whose pixels leave hatch and join fill_mask;
 *   the gray loop: gray = tone & (L < tl_cut) (the line halo is empty: no line was drawn), the enclosure test of each
 *     piece of components(gray, min_span) against tone | ink | colored (owners.c rf_gray_sides); for each piece left,
 *     draw_component returns "tone" and the drop test reads the outline length (outline.c): a piece thin and short
 *     enough leaves hatch;
 *   the cel bands: Pillow's GaussianBlur(CEL_BLUR) of L (blur.c), darkness d = 1.0 - g / 255.0, the shade budget over
 *     the histogram of int(100 d) in [CEL_BANDS[0][0], 0.88), the floor raised to fit `shade` and held at the darkest
 *     bin, the split at numpy's linear quantile (HATCH_CROSS_AT) of d over the shaded pixels. d takes one value per
 *     gray level, so the histogram and the quantile's order statistics come from per-level counts: the same values
 *     numpy reads from the pixel array. The bands from cel.c; per band its washes (components of band & ~(colored |
 *     black), mean colors) and then its lines (hatch.c) as TONE_PEN strokes;
 *   the contour pass: keep = ridge & ~dilate(fill_mask, 2 clear + 1), its centerlines (skel.c) of two points or more
 *     as FINELINER_2 strokes.
 * The fills are planned as one batch on all threads after the decisions, in the order the Python makes them (its store
 * session defers them the same way), then the pen strokes are added; *order_out lists the store indices in the
 * painter's `out` order. Every value derived from a constant (_ker, _field, _gu, the floors) is the Python's expression.
 * Identity: each painter run's ink section through the twin's Python lines and through this (the strokes, their order
 * and the report compared), and the strict check of the model's strokes against the pure-Python model's. */
#include <float.h>
#include <math.h>
#include <stdlib.h>
#include <string.h>
#include "rmfast.h"
#include "internal.h"

static int finite_d(double x) { return x >= -DBL_MAX && x <= DBL_MAX; }      /* false for NaN and both infinities */

/* the entry's validation: every float of the parameters finite, and every one the passes divide by positive (ppg,
 * detail, the pen and highlighter scales) along with the grid-length scale up -> 1 when they may run */
int rf_ink_params_ok(const rf_ink_params *P) {
    const double v[] = {P->ppg, P->x0, P->y0, P->x1, P->y1, P->detail, P->shade, P->up, P->draw_min_page, P->min_span_g, P->min_len_page,
                        P->tone_region_open, P->shadow_edge_blur, P->shadow_min_border, P->shadow_l_step, P->shadow_min_chroma,
                        P->shadow_hue_tol, P->shadow_max_edge, P->shadow_min_internal_grad, P->shadow_l_pct, P->ink_speck_covered,
                        P->ink_core_min, P->absorb_max_area, P->ink_density_cell_page, P->black_mass_thick_paint, P->black_mass_thick_page,
                        P->ink_line_min_len_page, P->ink_line_max_density, P->paper_l, P->tone_line_l, P->gray_field_cover,
                        P->gray_line_max_page, P->gray_drop_g, P->cel_min_area, P->tone_pitch_page, P->tone_width_page, P->cel_lo,
                        P->cel_hi, P->cel_blur, P->hatch_cross_at, P->cel_speck_area, P->cel_field_cover, P->hatch_under_min_g,
                        P->hatch_angle, P->hatch_angle_2, P->hatch_pitch_mul, P->outline_clear_g, P->outline_min_len_page,
                        P->outline_width_page, P->hl_width_max, P->marker_width_max, P->hl_scale, P->pen_scale, P->fineliner_max};
    for (size_t i = 0; i < sizeof(v) / sizeof(v[0]); i++) if (!finite_d(v[i])) return 0;
    return P->ppg > 0.0 && P->detail > 0.0 && P->up > 0.0 && P->pen_scale > 0.0 && P->hl_scale > 0.0;
}

/* int(round(x)) of a finite x (half to even, as Python's round), clamped into int32's range */
static int64_t round_i(double x) {
    double r = rint(x);
    if (r > 2147483647.0) r = 2147483647.0;
    if (r < -2147483648.0) r = -2147483648.0;
    return (int64_t)r;
}
static int64_t max_i(int64_t a, int64_t b) { return a > b ? a : b; }
/* Python's max(a, b) / min(a, b) of floats: the first unless the second is strictly greater / smaller */
static double py_max(double a, double b) { return b > a ? b : a; }
static double py_min(double a, double b) { return b < a ? b : a; }

typedef struct { rf_fill_job *v; int32_t n, cap; } jobs_t;
typedef struct { int32_t *v; int64_t n, cap; } items_t;            /* >= 0: fill job k; < 0: pen stroke -(p + 1) */
typedef struct { int32_t *count, *style; int32_t n, cap; double *xy, *w; int64_t np, cap_p; } pens_t;

static int jobs_push(jobs_t *J, const rf_fill_job *j) {
    if (J->n == J->cap) {
        if (J->cap > INT32_MAX / 2) return -1;
        int32_t c = J->cap ? J->cap * 2 : 256;
        rf_fill_job *p = (rf_fill_job *)realloc(J->v, (size_t)c * sizeof(rf_fill_job));
        if (!p) return -1;
        J->v = p; J->cap = c;
    }
    J->v[J->n++] = *j;
    return 0;
}

static int items_push(items_t *I, int32_t x) {
    if (I->n == I->cap) {
        int64_t c = I->cap ? I->cap * 2 : 1024;
        int32_t *p = (int32_t *)realloc(I->v, (size_t)c * sizeof(int32_t));
        if (!p) return -1;
        I->v = p; I->cap = c;
    }
    I->v[I->n++] = x;
    return 0;
}

/* one pen stroke of c placed points, every width the field f, style st; also its item */
static int pens_push(pens_t *P, items_t *I, const double *xy, int32_t c, double f, int32_t st) {
    if (P->n == P->cap) {
        if (P->cap > INT32_MAX / 2) return -1;
        int32_t k = P->cap ? P->cap * 2 : 1024;
        int32_t *a = (int32_t *)realloc(P->count, (size_t)k * sizeof(int32_t));
        if (!a) return -1;
        P->count = a;
        int32_t *b = (int32_t *)realloc(P->style, (size_t)k * sizeof(int32_t));
        if (!b) return -1;
        P->style = b;
        P->cap = k;
    }
    if (P->np + c > P->cap_p) {
        int64_t k = P->cap_p ? P->cap_p : 4096;
        while (k < P->np + c) k *= 2;
        double *a = (double *)realloc(P->xy, (size_t)k * 2 * sizeof(double));
        if (!a) return -1;
        P->xy = a;
        double *b = (double *)realloc(P->w, (size_t)k * sizeof(double));
        if (!b) return -1;
        P->w = b;
        P->cap_p = k;
    }
    memcpy(P->xy + 2 * P->np, xy, (size_t)c * 2 * sizeof(double));
    for (int32_t t = 0; t < c; t++) P->w[P->np + t] = f;
    P->np += c;
    P->count[P->n] = c; P->style[P->n] = st;
    if (items_push(I, -(P->n + 1))) return -1;
    P->n++;
    return 0;
}

/* the mean color of a component's pixels inside the grid (its crop clipped to the grid): each channel's exact sum over
 * the count, truncated as int() of numpy's float64 mean -> the count */
static int64_t crop_mean(const int64_t *f, const uint8_t *crop, const uint8_t *rgb, int32_t H, int32_t W, int32_t *m) {
    int64_t bx = f[1], by = f[2], cw = f[3] + 2, ch = f[4] + 2;
    int64_t x0 = bx - 1 > 0 ? bx - 1 : 0, y0 = by - 1 > 0 ? by - 1 : 0;
    int64_t x1 = bx - 1 + cw < W ? bx - 1 + cw : W, y1 = by - 1 + ch < H ? by - 1 + ch : H;
    int64_t n = 0, s0 = 0, s1 = 0, s2 = 0;
    for (int64_t gy = y0; gy < y1; gy++) {
        const uint8_t *row = crop + (gy - (by - 1)) * cw;
        for (int64_t gx = x0; gx < x1; gx++) {
            if (!row[gx - (bx - 1)]) continue;
            size_t p = 3 * ((size_t)gy * (size_t)W + (size_t)gx);
            n++; s0 += rgb[p]; s1 += rgb[p + 1]; s2 += rgb[p + 2];
        }
    }
    if (n) {
        m[0] = (int32_t)((double)s0 / (double)n);
        m[1] = (int32_t)((double)s1 / (double)n);
        m[2] = (int32_t)((double)s2 / (double)n);
    }
    return n;
}

/* PIL's paste of the value v through a component's crop at its offset (clipped to the grid) */
static void crop_paste(const int64_t *f, const uint8_t *crop, uint8_t *g, int32_t H, int32_t W, uint8_t v) {
    int64_t bx = f[1], by = f[2], cw = f[3] + 2, ch = f[4] + 2;
    for (int64_t y = 0; y < ch; y++) {
        int64_t gy = by - 1 + y;
        if (gy < 0 || gy >= H) continue;
        for (int64_t x = 0; x < cw; x++) {
            int64_t gx = bx - 1 + x;
            if (gx >= 0 && gx < W && crop[y * cw + x]) g[(size_t)gy * (size_t)W + (size_t)gx] = v;
        }
    }
}

typedef struct { int64_t *info; uint8_t *crops; int64_t *at; int32_t n; } comps_t;

static void comps_free(comps_t *C) { rf_free(C->info); rf_free(C->crops); free(C->at); memset(C, 0, sizeof(*C)); }

/* rmb_npops.components(mask, min_span, min_area) (label.c) with each crop's start -> 0, -1 out of memory */
static int comps_of(const uint8_t *m, int32_t H, int32_t W, int64_t min_span, int64_t min_area, comps_t *C) {
    memset(C, 0, sizeof(*C));
    int64_t len = 0;
    int32_t n = rf_components(m, H, W, (int32_t)(min_span > INT32_MAX ? INT32_MAX : min_span), min_area, &C->info, &C->crops, &len);
    if (n < 0) return -1;
    C->n = n;
    C->at = (int64_t *)malloc(sizeof(int64_t) * (size_t)(n > 0 ? n : 1));
    if (!C->at) { comps_free(C); return -1; }
    int64_t off = 0;
    for (int32_t t = 0; t < n; t++) { C->at[t] = off; off += (C->info[5 * (size_t)t + 4] + 2) * (C->info[5 * (size_t)t + 3] + 2); }
    return 0;
}

/* a wash fill job for component t of C in the color m (its style found or registered) and its item */
static int wash_job(rf_store *S, const rf_ink_params *P, const comps_t *C, int32_t t, const int32_t *m, jobs_t *J, items_t *I) {
    int32_t st = rf_store_style_rgb(S, P->tool_hl, P->color_hl, m[0], m[1], m[2], 1);
    if (st < 0) return -1;
    const int64_t *f = C->info + 5 * (size_t)t;
    rf_fill_job j = {C->crops + C->at[t], (int32_t)(f[4] + 2), (int32_t)(f[3] + 2), (int32_t)(f[1] - 1), (int32_t)(f[2] - 1), 1,
                     P->hl_width_max, st, -1, -1};
    if (jobs_push(J, &j)) return -1;
    return items_push(I, J->n - 1);
}

static int any_set(const uint8_t *a, size_t n) {
    for (size_t i = 0; i < n; i++) if (a[i]) return 1;
    return 0;
}

/* numpy.quantile(v, q), method "linear", of values given as per-level counts: val[] in ascending order, cnt[] each
 * value's count, n their total (> 0). The order statistics are read from the counts; the virtual index, the floor, the
 * neighbors and the two-sided lerp are numpy's (zones.c rf_np_percentile has the same arithmetic). */
static double kth_counts(const int64_t *cnt, const double *val, int nv, int64_t k) {
    int64_t acc = 0;
    for (int i = 0; i < nv; i++) { acc += cnt[i]; if (k < acc) return val[i]; }
    return val[nv - 1];
}
static double quantile_counts(const int64_t *cnt, const double *val, int nv, int64_t n, double q) {
    double virt = (double)(n - 1) * q;
    double pf = floor(virt);
    int64_t prev, next;
    if (virt >= (double)(n - 1)) { prev = next = n - 1; pf = -1.0; }
    else if (virt < 0) { prev = next = 0; pf = 0.0; }
    else { prev = (int64_t)pf; next = prev + 1; }
    double a = kth_counts(cnt, val, nv, prev);
    double b = next == prev ? a : kth_counts(cnt, val, nv, next);
    double t = virt - pf;
    double diff = b - a;
    return t >= 0.5 ? b - diff * (1 - t) : a + diff * t;
}

/* rep (RF_INK_REP doubles, see rmfast.h). -> 0; -1 out of memory; -2 refused (a grid under 2 x 2 for the shade zones, or
 * a hatch call refused: the Python runs, and raises where it does) */
RF_API int32_t rf_ink_pass(rf_store *S, const rf_ink_params *P, int32_t H, int32_t W, const uint8_t *black, const uint8_t *tone,
                           const uint8_t *ink, const uint8_t *const *colors, int32_t ncol, const uint8_t *rgb, const uint8_t *lum,
                           const uint8_t *ridge, int32_t **order_out, int32_t *norder, double *rep) {
    *order_out = NULL; *norder = 0;
    for (int i = 0; i < RF_INK_REP; i++) rep[i] = 0.0;
    if (H <= 0 || W <= 0 || !ink || !rf_ink_params_ok(P)) return -2;
    size_t N = (size_t)H * (size_t)W;
    int32_t rc = -1;
    jobs_t J = {0}; items_t I = {0}; pens_t PN = {0};
    comps_t Ct = {0}, Cb = {0}, Cg = {0}, Cn[2] = {{0}, {0}};
    rf_outline_buf ob; memset(&ob, 0, sizeof(ob));
    uint8_t *colored = (uint8_t *)malloc(N), *hatch = (uint8_t *)malloc(N), *t1 = (uint8_t *)malloc(N), *t2 = (uint8_t *)malloc(N);
    uint8_t *fill_mask = (uint8_t *)calloc(N, 1), *skip = NULL, *bands[2] = {NULL, NULL};
    int8_t *action = NULL; int32_t *mrgb = NULL, *made = NULL, *pyref = NULL, *order = NULL;
    double *hist = NULL, *lines = NULL, *sL = NULL, *sxy = NULL, *placed = NULL; int32_t *scnt = NULL;
    uint8_t *kinds = NULL;
    if (!colored || !hatch || !t1 || !t2 || !fill_mask) goto done;

    /* ppg, detail, up and the pen scale are finite and positive (rf_ink_params_ok above): every division by them below
     * has a non-zero divisor and a finite result; every other divisor is a count of at least one */
    const double ppg = P->ppg, up = P->up;
    const int64_t draw_min = max_i(2, round_i(P->draw_min_page / ppg));
    const int64_t min_span = max_i(2, round_i((P->min_span_g * up) / P->detail));
    const double min_len_g = py_max((3.0 * up) / P->detail, (P->min_len_page / ppg) / P->detail);
    double ox, oy, scale;
    rf_place_frame(P->x0, P->y0, P->x1, P->y1, W, H, &ox, &oy, &scale);

    /* colored, and hatch = black | (tone & ~colored) */
    rf_any_nonzero(colors, ncol, H, W, colored);
    for (size_t i = 0; i < N; i++) hatch[i] = (uint8_t)((black && black[i]) || (tone && tone[i] && !colored[i]));

    /* the tone-region wash */
    if (P->tone_region_wash && tone) {
        int32_t k = (int32_t)(2 * max_i(1, round_i(P->tone_region_open * up)) + 1);
        if (rf_rank_ext(tone, H, W, k, 0, t1) || rf_rank_ext(t1, H, W, k, 1, t2)) goto done;
        for (size_t i = 0; i < N; i++) t2[i] = (uint8_t)(t2[i] && tone[i] && !colored[i] && !(black && black[i]));
        int64_t n_tw = 0;
        if (any_set(t2, N)) {
            if (comps_of(t2, H, W, draw_min, P->draw_min_area, &Ct)) goto done;
            for (int32_t t = 0; t < Ct.n; t++) {
                int32_t m[3];
                if (!crop_mean(Ct.info + 5 * (size_t)t, Ct.crops + Ct.at[t], rgb, H, W, m)) continue;
                if (wash_job(S, P, &Ct, t, m, &J, &I)) goto done;
                n_tw++;
            }
        }
        rep[0] = 1.0; rep[1] = (double)n_tw;
    }

    /* the shade zones */
    if (P->shadow_hatch) {
        rep[2] = 1.0; rep[3] = (double)ncol;
        if (ncol >= 2) {
            double l_cut = 0.0; int32_t pairs = 0, shadow = 0;
            int32_t r = rf_shadow_zones(colors, ncol, H, W, rgb, (float)P->shadow_edge_blur, P->shadow_min_border, P->shadow_l_step,
                                        P->shadow_min_chroma, P->shadow_hue_tol, P->shadow_max_edge, P->shadow_min_internal_grad,
                                        P->shadow_l_pct, t1, &l_cut, &pairs, &shadow);
            if (r == -2) { rc = -2; goto done; }
            if (r != 0) goto done;
            rep[4] = (double)shadow; rep[5] = (double)pairs; rep[6] = 1.0; rep[7] = l_cut;
            for (size_t i = 0; i < N; i++) hatch[i] |= t1[i] != 0;
        }
    }

    /* the black pass (black_left is the whole ink mask: the line loop took nothing out of it) */
    {
        int32_t hh = 0, hw = 0;
        double cell = 0.0;
        if (P->ink_core_min > 0 && black) {
            cell = py_max(4.0, P->ink_density_cell_page / ppg);
            double fh = rf_py_floordiv((double)H, cell), fw = rf_py_floordiv((double)W, cell);
            hh = (int32_t)fh + 2; hw = (int32_t)fw + 2;          /* H // cell <= H: in range */
            hist = (double *)calloc((size_t)hh * (size_t)hw, sizeof(double));
            if (!hist) goto done;
            int32_t r = rf_ink_density(ink, black, H, W, ppg, P->ink_core_min, P->absorb_max_area, cell, hh, hw, hist);
            if (r < 0) goto done;
            if (r == 0) { free(hist); hist = NULL; }
        }
        if (comps_of(ink, H, W, 1, 0, &Cb)) goto done;
        if (Cb.n > 0) {
            skip = (uint8_t *)calloc((size_t)Cb.n, 1);
            action = (int8_t *)malloc((size_t)Cb.n);
            mrgb = (int32_t *)malloc(sizeof(int32_t) * 3 * (size_t)Cb.n);
            if (!skip || !action || !mrgb) goto done;
            if (P->ink_speck_on_color)
                rf_speck_skip(Cb.info, Cb.crops, Cb.n, colored, H, W, draw_min, P->ink_speck_covered, skip);
            double thick_min = P->painterly ? P->black_mass_thick_paint : P->black_mass_thick_page;
            int32_t r = rf_black_pieces(Cb.info, Cb.crops, Cb.n, P->ink_speck_on_color ? skip : NULL, black, rgb, H, W, ppg, thick_min,
                                        hist, hh, hw, cell, P->ink_core_min, P->ink_line_min_len_page, P->ink_line_max_density, action, mrgb);
            if (r == -2) { rc = -2; goto done; }
            if (r != 0) goto done;
            int64_t fills = 0, no_core = 0, mass = 0;
            for (int32_t t = 0; t < Cb.n; t++) {
                if (P->ink_speck_on_color && skip[t]) continue;
                if (action[t] == 1 || action[t] == 2) {
                    if (wash_job(S, P, &Cb, t, mrgb + 3 * (size_t)t, &J, &I)) goto done;
                    if (action[t] == 1) { if (!no_core && !mass) rep[11] = 1.0; no_core++; }
                    else { if (!no_core && !mass) rep[11] = 2.0; mass++; }
                    continue;
                }
                const int64_t *f = Cb.info + 5 * (size_t)t;
                rf_fill_job j = {Cb.crops + Cb.at[t], (int32_t)(f[4] + 2), (int32_t)(f[3] + 2), (int32_t)(f[1] - 1), (int32_t)(f[2] - 1), 0,
                                 P->marker_width_max, -1, P->st_fine, P->st_marker};
                if (jobs_push(&J, &j) || items_push(&I, J.n - 1)) goto done;
                crop_paste(f, Cb.crops + Cb.at[t], hatch, H, W, 0);
                crop_paste(f, Cb.crops + Cb.at[t], fill_mask, H, W, 1);
                fills++;
            }
            rep[8] = (double)fills; rep[9] = (double)no_core; rep[10] = (double)mass;
        }
    }

    /* the gray loop */
    if (tone) {
        int64_t tl_cut = round_i(py_min(P->paper_l, P->tone_line_l + 12.0 * (P->detail - 1.0)) * 2.55);
        for (size_t i = 0; i < N; i++) {
            t1[i] = (uint8_t)(tone[i] && (int64_t)lum[i] < tl_cut);
            t2[i] = (uint8_t)(tone[i] || ink[i] || colored[i]);
        }
        int64_t pad = max_i(3, round_i(10.0 / ppg)), dropped = 0;
        if (comps_of(t1, H, W, min_span, 0, &Cg)) goto done;
        if (Cg.n > 0) {
            free(skip);
            skip = (uint8_t *)malloc((size_t)Cg.n);
            if (!skip || rf_gray_sides(Cg.info, Cg.n, t2, H, W, pad, P->gray_field_cover, skip)) goto done;
            for (int32_t t = 0; t < Cg.n; t++) {
                if (skip[t]) continue;
                const int64_t *f = Cg.info + 5 * (size_t)t;
                const uint8_t *crop = Cg.crops + Cg.at[t];
                int32_t cw = (int32_t)(f[3] + 2), ch = (int32_t)(f[4] + 2);
                double per = 0.0;
                if (rf_outline_length(crop, ch, cw, cw, ch, &ob, &per) < 0) goto done;
                double est = per != 0.0 ? (2.0 * (double)f[0]) / per : 99.0;
                if (est * ppg <= 1.6 * P->gray_line_max_page && est <= P->gray_drop_g * up) {
                    crop_paste(f, crop, hatch, H, W, 0);
                    dropped++;
                }
            }
        }
        rep[12] = 1.0; rep[13] = (double)dropped;
    }

    /* the cel bands and their hatch */
    if (P->tone && any_set(hatch, N)) {
        double mn = ((P->cel_min_area * (double)W) * (double)H) / P->detail;
        int64_t min_area_px = mn < 9.0e18 ? (int64_t)mn : (int64_t)9.0e18;
        double pitch_g = py_max(1.2, P->tone_pitch_page / ppg);
        double tf = (double)max_i(2, round_i(P->tone_width_page / P->pen_scale));
        double d_min = P->cel_lo, budget = (P->shade * (double)W) * (double)H;
        if (rf_box_blur(lum, t1, H, W, 1, (float)P->cel_blur, 1)) goto done;
        int64_t cnt[256] = {0};
        double dv[256];
        for (int g = 0; g < 256; g++) dv[g] = 1.0 - (double)g / 255.0;
        for (size_t i = 0; i < N; i++) if (hatch[i]) cnt[t1[i]]++;
        int64_t hist101[101] = {0}, shaded = 0;
        for (int g = 0; g < 256; g++) {
            double d = dv[g];
            if (!(d >= P->cel_lo && d < 0.88) || !cnt[g]) continue;
            double b = d * 100.0;
            int64_t bi = b < 0.0 ? 0 : (b > 100.0 ? 100 : (int64_t)b);
            hist101[bi] += cnt[g];
            shaded += cnt[g];
        }
        rep[14] = 1.0; rep[15] = (double)shaded / (double)((int64_t)W * H);
        if ((double)shaded > budget) {
            int64_t acc = 0;
            for (int i = 100; i >= 0; i--) {
                acc += hist101[i];
                if ((double)acc > budget) { d_min = py_max(d_min, (i + 1) / 100.0); break; }
            }
            int top = -1;
            for (int i = 0; i <= 100; i++) if (hist101[i]) top = i;
            if (top >= 0) d_min = py_min(d_min, top / 100.0);
        }
        rep[16] = d_min;
        double hi = P->cel_hi, sval[256];
        int64_t lcnt[256], nsd = 0;
        for (int i = 0; i < 256; i++) {          /* ascending darkness = descending gray level */
            int g = 255 - i;
            sval[i] = dv[g];
            lcnt[i] = (dv[g] >= d_min && dv[g] < hi) ? cnt[g] : 0;
            nsd += lcnt[i];
        }
        double mid = nsd ? quantile_counts(lcnt, sval, 256, nsd, P->hatch_cross_at) : (d_min + hi) / 2.0;
        double lohi[4] = {d_min, mid, mid, hi};
        bands[0] = (uint8_t *)malloc(N); bands[1] = (uint8_t *)malloc(N);
        if (!bands[0] || !bands[1]) goto done;
        if (rf_cel_regions(lum, hatch, H, W, (float)P->cel_blur, lohi, 2, P->cel_median, P->cel_speck_area, P->cel_field_cover,
                           min_area_px, bands)) goto done;
        int64_t hmin = max_i(2, round_i(P->hatch_under_min_g * up)), hatch_wash = 0, tone_lines = 0;
        for (int bi = 0; bi < 2; bi++) {
            const uint8_t *region = bands[bi];
            if (P->hatch_under_wash) {
                int any = 0;
                for (size_t i = 0; i < N; i++) { t2[i] = (uint8_t)(region[i] && !colored[i] && !(black && black[i])); any |= t2[i]; }
                if (any) {                       /* each band's pieces are kept: the jobs read their crops at the batch */
                    if (comps_of(t2, H, W, hmin, 0, &Cn[bi])) goto done;
                    for (int32_t t = 0; t < Cn[bi].n; t++) {
                        int32_t m[3];
                        if (!crop_mean(Cn[bi].info + 5 * (size_t)t, Cn[bi].crops + Cn[bi].at[t], rgb, H, W, m)) continue;
                        if (wash_job(S, P, &Cn[bi], t, m, &J, &I)) goto done;
                        hatch_wash++;
                    }
                }
            }
            double angles[2] = {P->hatch_angle, P->hatch_angle_2};
            int64_t n = rf_uniform_hatch(region, H, W, angles, bi == 0 ? 1 : 2, pitch_g * P->hatch_pitch_mul, min_len_g, &lines);
            if (n == -2) { rc = -2; goto done; }
            if (n < 0) goto done;
            for (int64_t s = 0; s < n; s++) {
                double pts[4];
                rf_place_points(lines + 4 * s, 2, ox, oy, scale, pts);
                if (pens_push(&PN, &I, pts, 2, tf, P->st_tone)) goto done;
            }
            rf_free(lines); lines = NULL;
            rep[17 + bi] = (double)n;
            tone_lines += n;
        }
        rep[19] = (double)tone_lines; rep[20] = (double)hatch_wash;
    }

    /* the contour pass */
    if (P->outline) {
        int32_t k = (int32_t)(2 * max_i(1, round_i(P->outline_clear_g * up)) + 1);
        if (rf_rank_ext(fill_mask, H, W, k, 1, t1)) goto done;
        int any = 0;
        for (size_t i = 0; i < N; i++) { t2[i] = (uint8_t)(ridge[i] && !t1[i]); any |= t2[i]; }
        int64_t nout = 0;
        if (any) {
            double min_len_out = py_max(min_len_g, P->outline_min_len_page / ppg), tot = 0.0;
            int32_t pieces = 0;
            int32_t n = rf_skeleton_thin(t2, H, W, min_len_out, P->line_smooth ? 0.7 : 0.35, P->line_smooth ? 1 : 0, &sL, &scnt, &sxy, &tot, &pieces);
            if (n < 0) goto done;
            double wf = (double)max_i(2, round_i(P->outline_width_page / P->pen_scale));
            int64_t o = 0, most = 0;
            for (int32_t i = 0; i < n; i++) if (scnt[i] > most) most = scnt[i];
            placed = (double *)malloc(sizeof(double) * 2 * (size_t)(most > 0 ? most : 1));
            if (!placed) goto done;
            for (int32_t i = 0; i < n; i++) {
                if (scnt[i] >= 2) {
                    rf_place_points(sxy + 2 * o, scnt[i], ox, oy, scale, placed);
                    if (pens_push(&PN, &I, placed, scnt[i], wf, P->st_outline)) goto done;
                    nout++;
                }
                o += scnt[i];
            }
        }
        rep[21] = (double)nout;
    }

    /* the fills as one batch, then the pen strokes, then the order */
    {
        int32_t base = rf_store_count(S);
        made = (int32_t *)calloc((size_t)(J.n > 0 ? J.n : 1), sizeof(int32_t));
        if (!made) goto done;
        if (J.n > 0 && rf_store_fill_batch(S, J.v, J.n, ppg, P->x0, P->y0, P->x1, P->y1, W, H, P->hl_scale, P->pen_scale,
                                           P->fineliner_max, made) < 0) goto done;
        int32_t pen_base = rf_store_count(S);
        if (PN.n > 0) {
            pyref = (int32_t *)malloc(sizeof(int32_t) * (size_t)PN.n);
            kinds = (uint8_t *)calloc((size_t)(2 * PN.np), 1);                /* RF_KIND_PY: Python floats */
            if (!pyref || !kinds) goto done;
            for (int32_t i = 0; i < PN.n; i++) pyref[i] = -1;
            if (rf_store_add(S, PN.n, PN.count, PN.xy, PN.w, kinds, PN.style, pyref) < 0) goto done;
        }
        int64_t total = PN.n;
        for (int32_t k = 0; k < J.n; k++) total += made[k];
        if (total > INT32_MAX) goto done;
        order = (int32_t *)malloc(sizeof(int32_t) * (size_t)(total > 0 ? total : 1));
        int32_t *first = (int32_t *)malloc(sizeof(int32_t) * (size_t)(J.n > 0 ? J.n : 1));
        if (!order || !first) { free(first); goto done; }
        int32_t at = base;
        for (int32_t k = 0; k < J.n; k++) { first[k] = at; at += made[k]; }
        int64_t o = 0;
        for (int64_t i = 0; i < I.n; i++) {
            int32_t it = I.v[i];
            if (it >= 0) for (int32_t s = 0; s < made[it]; s++) order[o++] = first[it] + s;
            else order[o++] = pen_base + (-it - 1);
        }
        free(first);
        *order_out = order; *norder = (int32_t)o; order = NULL;
        rc = 0;
    }

done:
    free(colored); free(hatch); free(t1); free(t2); free(fill_mask); free(skip); free(bands[0]); free(bands[1]);
    free(action); free(mrgb); free(made); free(pyref); free(order); free(hist); free(placed); free(kinds);
    rf_free(lines); rf_free(sL); rf_free(scnt); rf_free(sxy);
    rf_outline_buf_free(&ob);
    comps_free(&Cb); comps_free(&Cg); comps_free(&Cn[0]); comps_free(&Cn[1]);
    free(J.v); free(I.v); free(PN.count); free(PN.style); free(PN.xy); free(PN.w);
    comps_free(&Ct);
    return rc;
}
