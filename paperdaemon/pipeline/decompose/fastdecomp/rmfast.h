/* rmfast -- the decomposer's stages in C, on the CPU, with output identical to the Python model (rm_model.py).
 *
 * This header: the device's wash rasterizer (rm_raster), the lossless pass (rm_lean.prune_join) and the two-run seam
 * (rm_model._seam), bit for bit the Python's. The other stages (the planner, the quantizer's cel pass, the speck
 * absorber, the shade zones, the region budget, components, outlines, hole filling) are reached through rmfast.py.
 * Doubles everywhere the Python uses doubles; sqrt where it uses sqrt; sorted int32 pixel sets where it uses sorted
 * numpy arrays. Built with `python -m ziglang cc` (clang) by
 * fastdecomp/build.py, -ffp-contract=off so no fused multiply-add changes a rounding the Python did not make.
 *
 * A stroke list: n strokes; counts[i] points each; xy[2*k], xy[2*k+1] the k-th point (page px, double); w[k] its
 * width field; wash[i] = 1 for a highlighter stroke; rgb[3*i..] the wash color (255,237,117 when the Python has None;
 * ink has no color here). Outputs are allocated by the library and released with rf_free.
 */
#ifndef RMFAST_H
#define RMFAST_H
#include <stdint.h>

#ifdef _WIN32
#define RF_API __declspec(dllexport)
#else
#define RF_API __attribute__((visibility("default")))
#endif

typedef struct {
    int32_t n;
    const int32_t *counts;
    const double *xy;
    const double *w;
    const uint8_t *wash;
    const int32_t *rgb;
    const int64_t *group;      /* per stroke: a key equal for strokes of one color, tool and pen color (the Python's group
                                  key without the width); the width joins it inside */
    const uint8_t *kind;       /* per stroke, 4 codes: the scalar type of the first point's x, y and the last point's
                                  x, y as the Python holds them -- RF_KIND_PY (a Python float or int), RF_KIND_F32
                                  (numpy.float32), RF_KIND_F64 (numpy.float64). NEP 50 promotion decides whether the
                                  join's distance and bucket keys are float32 or double arithmetic. NULL = all PY. */
    const uint8_t *pkind;      /* per point, 2 codes (x, y): every point's scalar kind, carried into rf_result.pkind
                                  (the stroke store's output types). NULL = none carried. */
} rf_strokes;

enum { RF_KIND_PY = 0, RF_KIND_F32 = 1, RF_KIND_F64 = 2 };

typedef struct {
    int32_t n;                 /* output strokes */
    int32_t *counts;
    double *xy;
    double *w;
    int32_t *src;              /* the input stroke each output stroke takes its tool, color and rgba from */
    int32_t pruned, joins;
    uint8_t *pkind;            /* per output point, 2 codes: the input's pkind (zeros when the input had none) */
} rf_result;

RF_API const char *rf_version(void);
/* the one stroke renderer (render.c): strokes over an RGB canvas, as the tablet draws them */
RF_API int32_t rf_render(uint8_t *rgb, int32_t W, int32_t H, int32_t ss, const double *xy, const double *w,
                         const int32_t *counts, const int32_t *kinds, const uint8_t *rgba, int32_t nstrokes, double *progress);
/* a .rm page's blocks, its strokes' fields read in one pass (rmlines.c): one row of rf_rm_cols() int64 a block */
RF_API int64_t rf_rm_blocks(const uint8_t *d, int64_t n, int64_t header, int64_t *rows, int64_t max_rows);
RF_API int32_t rf_rm_cols(void);
/* the same with a density per point (dens: 0..1, 1 solid): the pencils' grain and the light paintbrush and ballpoint */
RF_API int32_t rf_render_grain(uint8_t *rgb, int32_t W, int32_t H, int32_t ss, const double *xy, const double *w, const double *dens,
                               const int32_t *counts, const int32_t *kinds, const uint8_t *rgba, int32_t nstrokes, double *progress);
/* how far the decompose running now has come, in thousandths (0 before it starts, 1000 when it is done); safe to read
 * from another thread while rf_decompose* runs */
RF_API int32_t rf_progress(void);
RF_API void rf_progress_reset(void);
RF_API void rf_free(void *p);

/* The footprint of one wash: flat indices (row * W + col), ascending, of the pixels painted in the W x H grid whose
 * pixel (0, 0) is centered at (ox + .5, oy + .5), under the pixel-center rule widened (eps > 0) or shrunk (eps < 0).
 * Returns the count; *out is rf_free'd by the caller. */
RF_API int32_t rf_wash_pixels(const double *xy, const double *w, int32_t npts, double ox, double oy, int32_t W, int32_t H, double eps, int32_t **out);

/* rm_lean.prune_join: eps_out < 0 means None (the exact rule only). */
RF_API int rf_prune_join(const rf_strokes *in, double eps_out, double radius, double radius_w, int32_t max_points, rf_result *out);
RF_API void rf_result_free(rf_result *r);

/* rm_model._seam, footprint form: the base washes (the first run's) whose WASH_EPS footprint holds a pixel that the
 * combined washes leave unpainted. fx0/fy0/W/H: the frame. Returns the count of base washes to add; *out holds their
 * indices into `base`, ascending; rf_free'd by the caller. */
RF_API int32_t rf_seam(const rf_strokes *base, const rf_strokes *combined, double fx0, double fy0, int32_t W, int32_t H, double wash_eps, int32_t **out);

/* blur.c: Pillow's BoxBlur (gaussian = 0) / GaussianBlur (gaussian = 1) of an H x W image of nch interleaved 8-bit
 * channels; and the painter's gap densities (per class mask: the anchor of its pieces at least min_span wide or tall,
 * box-blurred by radius into dens[k] when it has a pixel; has[k] says whether it did). 0, or -1 out of memory. */
RF_API int32_t rf_box_blur(const uint8_t *in, uint8_t *out, int32_t H, int32_t W, int32_t nch, float radius, int32_t gaussian);
RF_API int32_t rf_gap_density(const uint8_t *const *masks, int32_t nk, int32_t H, int32_t W, int32_t min_span, float radius,
                              uint8_t *const *dens, uint8_t *has);

/* zones.c: the whole of rm_paint.shadow_zones (see there). 0; -1 out of memory; -2 grid under 2 x 2 (Python runs). */
RF_API int32_t rf_shadow_zones(const uint8_t *const *masks, int32_t n, int32_t H, int32_t W, const uint8_t *rgb,
                               float edge_blur, double min_border, double l_step, double min_chroma, double hue_tol,
                               double max_edge, double min_internal_grad, double l_pct,
                               uint8_t *out, double *l_cut_out, int32_t *pairs_out, int32_t *shadow_out);

/* mediancut.c: quantize(colors, MEDIANCUT).convert("RGB") of n RGB pixels into out (Pillow's code, vendored).
 * -> the palette's length, or -1. */
RF_API int32_t rf_mediancut(const uint8_t *rgb, int64_t n, int32_t colors, uint8_t *out);

/* xdog.c: the painter's ridge (rmb_lineart xdog, mask, thin) from the grid picture's RGB. 0, or -1 out of memory. */
RF_API int32_t rf_xdog_ridge(const uint8_t *rgb, int32_t H, int32_t W, float sigma, float sigma_k, double tau, double ink,
                             uint8_t *ridge, int64_t *count);
/* xdog.c: rmb_lineart.thin of an H x W mask into out (0/1). 0, or -1 out of memory. */
RF_API int32_t rf_thin(const uint8_t *fg, int32_t H, int32_t W, uint8_t *out);

/* flow.c: how many pixels of rm_flow.field's coherence reach min_coh, the Gaussian kernels given (NULL: no filter).
 * 0, or -1 out of memory. */
RF_API int32_t rf_flow_coherence(const uint8_t *gray, int32_t H, int32_t W, const double *wpre, int32_t rpre, const double *wsig,
                                 int32_t rsig, double min_coh, int64_t *count);

/* tonal.c: rmb_resolution.tonal_ink in two calls (see there) */
RF_API int64_t rf_tonal_protect(const uint8_t *ink_mask, const uint8_t *rgb, int32_t H, int32_t W, double thr, double max_diam,
                                const uint8_t *ladder, uint8_t *protect, int32_t *pidx, int32_t *palette, int32_t *npal);
RF_API void rf_tonal_apply(const uint8_t *const *masks_in, int32_t nin, uint8_t *const *out, int32_t nout, const uint8_t *protect,
                           const int32_t *pidx, const int32_t *slot, int32_t H, int32_t W);

/* regions.c: rm_regions.pieces, _stats and _edges (see there) */
RF_API int32_t rf_pieces(const uint8_t *const *masks, int32_t nk, int32_t H, int32_t W, int32_t *labels, int32_t *count_per_class);
RF_API int32_t rf_region_stats(const int32_t *labels, const double *lab_img, int32_t H, int32_t W, int32_t n,
                               double *area, double *sum_lab, double *cx, double *cy, double *bw, double *bh);
RF_API int32_t rf_region_edges(const int32_t *labels, const double *lab_img, int32_t H, int32_t W, int32_t n,
                               int64_t **a_out, int64_t **b_out, double **cnt_out, double **sde_out);

/* merge.c: rm_regions.merge_to_budget's rounds and rm_regions.recolored's pixels (see there) */
RF_API int32_t rf_merge_to_budget(const int32_t *labels0, int32_t H, int32_t W, const int32_t *cls_of, const uint8_t *frozen_cls, int32_t n,
                                  const double *lab_img, double ppg, int64_t budget, const double *knobs, double absorb_max_area,
                                  double cell_page, double round_fraction, int32_t max_rounds, int32_t cut_specks,
                                  int32_t *labels, int64_t *orig_of, int32_t *cls, uint8_t *frozen,
                                  int32_t *r_kind, int64_t *r_pool, int64_t *r_merged, double *r_cut, double *r_secs, int64_t *counts);
RF_API int64_t rf_recolor(const uint8_t *rgb, const int32_t *labels0, const int32_t *labels, int32_t H, int32_t W, const int64_t *orig_of, int32_t m,
                          uint8_t *out);

/* specks.c: the black pass's covered grid (any of n masks non-zero) and its covered-speck test per component of
 * rf_components' output (see there) */
RF_API void rf_any_nonzero(const uint8_t *const *masks, int32_t n, int32_t H, int32_t W, uint8_t *out);
RF_API void rf_speck_skip(const int64_t *info, const uint8_t *crops, int32_t n, const uint8_t *covered, int32_t H, int32_t W,
                          int64_t draw_min, double covered_min, uint8_t *skip);
RF_API int32_t rf_ink_density(const uint8_t *black_left, const uint8_t *black, int32_t H, int32_t W, double ppg, double core_min,
                              double absorb_max_area, double cell, int32_t hh, int32_t hw, double *hist);
/* owners.c: the gap close's class for each gap pixel, written into the class masks (touched[j] = 1 for a class that got
 * one) -> the pixels given, -1 out of memory; the gray halo's kept pieces of n gray masks (keeps 0/1) -> the pixels
 * dropped, -1 out of memory */
RF_API int64_t rf_gap_assign(const uint8_t *const *dens, int32_t nk, int32_t H, int32_t W, const uint8_t *gap, const uint8_t *lum,
                             const uint8_t *rgb, int32_t paper_cut, int32_t ink_cut, const double *KL, uint8_t *const *masks,
                             uint8_t *touched);
RF_API int64_t rf_gray_halo(const uint8_t *const *masks, int32_t n, int32_t H, int32_t W, const uint8_t *skirt, double share,
                            uint8_t *const *keeps);
/* outline.c: rm_paint._outline of an h x w crop of an H x W mask: the chains at least min_len long (counts, xy: malloc'd,
 * the caller frees them) and the total length -> the chain count, -1 out of memory */
RF_API int32_t rf_outline(const uint8_t *a, int32_t H, int32_t W, int32_t w, int32_t h, double min_len, double *total_out,
                          int32_t **counts_out, double **xy_out);
/* black.c: the black pass's decision per piece of rf_components' output (info, crops) -> 0, -1 out of memory, -2 a
 * density grid with no cells; action 0 skipped, 1 no-core wash, 2 mass wash (mrgb its color), 3 solid fill */
RF_API int32_t rf_black_pieces(const int64_t *info, const uint8_t *crops, int32_t n, const uint8_t *skip, const uint8_t *black,
                               const uint8_t *rgb, int32_t H, int32_t W, double ppg, double thick_min, const double *hist, int32_t hh,
                               int32_t hw, double cell, double core_min, double line_min_len, double line_max_density, int8_t *action,
                               int32_t *mrgb);
/* rank.c: rmb_npops.rank_ext, the k x k maximum (ismax) or minimum with the edge replicated, src into dst -> 0, -1 out
 * of memory, -2 refused (k < 1) */
RF_API int32_t rf_rank_ext(const uint8_t *src, int32_t H, int32_t W, int32_t k, int32_t ismax, uint8_t *dst);
/* owners.c: the gray-line pass's enclosure test per component of rf_components' output (info: 5 per component) ->
 * 0, -1 out of memory */
RF_API int32_t rf_gray_sides(const int64_t *info, int32_t n, const uint8_t *nonpaper, int32_t H, int32_t W, int64_t pad, double cover,
                             uint8_t *skip);

/* decode.c: a PNG read as Pillow reads it (see there): info = width, height, Pillow's mode code; rgb = W x H x 3.
 * 0; -1 out of memory; -2 refused (Pillow reads it) */
RF_API int32_t rf_png_info(const uint8_t *data, int64_t n, int32_t *info);
RF_API int32_t rf_png_rgb(const uint8_t *data, int64_t n, uint8_t *rgb);
/* jpeg.c: a JPEG read as Pillow reads it (see there), the same calls and results */
RF_API int32_t rf_jpeg_info(const uint8_t *data, int64_t n, int32_t *info);
RF_API int32_t rf_jpeg_rgb(const uint8_t *data, int64_t n, uint8_t *rgb);

/* cel.c: rm_paint.cel_regions (see there); hatch.c: rm_paint.uniform_hatch (see there) */
RF_API int32_t rf_cel_regions(const uint8_t *lum, const uint8_t *mask, int32_t H, int32_t W, float blur, const double *lohi, int32_t nb,
                              int32_t k, double speck_area, double field_cover, int64_t min_area, uint8_t *const *outs);
/* skel.c: rm_paint._skeleton(mask, ppg, min_len, method="thin") (see there) */
RF_API int32_t rf_skeleton_thin(const uint8_t *mask, int32_t H, int32_t W, double min_len, double eps, int32_t smooth,
                                double **L_out, int32_t **cnt_out, double **xy_out, double *total, int32_t *pieces);
RF_API int64_t rf_uniform_hatch(const uint8_t *mask, int32_t H, int32_t W, const double *angles, int32_t na, double pitch, double min_len,
                                double **out);

/* lab.c: rm_paint._lab_rows on n (r, g, b) uint8 rows -> n (L, a, b) float64 rows; and its sRGB transfer table */
RF_API void rf_lab_rows(const uint8_t *rgb, int64_t n, double *out);
RF_API void rf_srgb_lut(double *out);

/* The stroke store (store.c): the painter's strokes held in C from the planner to the pass. A stroke has a style
 * (tool, pen color, rgb, wash flag, rgba key -- the Python keeps the objects), its points as doubles with each
 * coordinate's scalar kind (RF_KIND_*), its widths as doubles, and pyref >= 0 when it was made in Python (the wrapper
 * keeps that object). Orders are int32 arrays of stroke indices. Functions return < 0 when memory runs out. */
typedef struct rf_store rf_store;
RF_API rf_store *rf_store_new(void);
RF_API void rf_store_free(rf_store *S);
RF_API int32_t rf_store_style(rf_store *S, int32_t tool, int32_t color, int32_t r, int32_t g, int32_t b, int32_t wash, int32_t rgba_key);
RF_API int32_t rf_store_count(const rf_store *S);
RF_API void rf_store_arrays(const rf_store *S, const int32_t **count, const int32_t **style, const int32_t **pyref);
RF_API int32_t rf_store_fill(rf_store *S, const uint8_t *mask, int32_t h, int32_t w, double ppg, int32_t flat, double max_page,
                             double x0, double y0, double x1, double y1, int32_t offx, int32_t offy, int32_t gw, int32_t gh,
                             double hl_scale, double pen_scale, double fineliner_max, int32_t st_wash, int32_t st_fine, int32_t st_marker);
/* one zone of a batch: its mask (h x w, any non-zero byte set) at grid offset (offx, offy), flat (wash) or not, the
 * widest pen, and the styles its strokes get (the wash's, or the fineliner's and the marker's for an opaque fill) */
typedef struct {
    const uint8_t *mask;
    int32_t h, w, offx, offy, flat;
    double max_page;
    int32_t st_wash, st_fine, st_marker;
} rf_fill_job;
/* the jobs planned on all threads, appended in job order; made[k] = strokes job k added. Returns the total. */
RF_API int32_t rf_store_fill_batch(rf_store *S, const rf_fill_job *jobs, int32_t njobs, double ppg,
                                   double x0, double y0, double x1, double y1, int32_t gw, int32_t gh,
                                   double hl_scale, double pen_scale, double fineliner_max, int32_t *made);
RF_API int32_t rf_store_add(rf_store *S, int32_t n, const int32_t *counts, const double *xy, const double *w, const uint8_t *kinds,
                            const int32_t *style, const int32_t *pyref);
RF_API int32_t rf_store_wash_first(const rf_store *S, const int32_t *order, int32_t n, int32_t hl_tool, int32_t *out);
RF_API int32_t rf_store_extent(const rf_store *S, const int32_t *order, int32_t n, int32_t hl_tool, double hl_scale, double pen_scale,
                               double *val, uint8_t *kind);
RF_API int32_t rf_store_select(const rf_store *S, const int32_t *order, int32_t n, int32_t want_wash, int32_t *out);
RF_API int32_t rf_store_seam(const rf_store *S, const int32_t *base, int32_t nbase, const int32_t *washes, int32_t nwashes,
                             double fx0, double fy0, int32_t W, int32_t H, double wash_eps, int32_t **add);
RF_API int32_t rf_store_prune_join(const rf_store *S, const int32_t *order, int32_t n, double eps_out, double radius, double radius_w,
                                   int32_t max_points, rf_result *out);
/* the style of (tool, pen color, wash) with the rgba (r, g, b), found or registered with the rgba key every style of
 * that rgba shares; the styles from `first` on as 7 ints each (tool, pen color, r, g, b, has an rgba, wash); the style
 * count */
RF_API int32_t rf_store_style_rgb(rf_store *S, int32_t tool, int32_t color, int32_t r, int32_t g, int32_t b, int32_t wash);
RF_API int32_t rf_store_styles(const rf_store *S, int32_t first, int32_t *out);
RF_API int32_t rf_store_style_count(const rf_store *S);

/* pockets.c, outline.c, absorb.c: the pocket loops, rm_paint._fill_holes and the speck absorber's steps (see there) */
RF_API int32_t rf_pockets(const uint8_t *pockets, int32_t H, int32_t W, int32_t k, int32_t nkeys, uint8_t **keys);
RF_API int32_t rf_tone_pockets(const uint8_t *inv, int32_t Hi, int32_t Wi, const uint8_t *tone, const uint8_t *lum, const uint8_t *rgb,
                               double thr, int64_t **info_out, int64_t **xy_out);
RF_API int32_t rf_fill_holes(const uint8_t *mask, int32_t H, int32_t W, double small, double thin, uint8_t *out);
RF_API int64_t rf_absorb_prepare_masks(const uint8_t *const *masks, int32_t nk, int32_t H, int32_t W, int32_t min_span, int64_t min_area,
                                       int32_t *own_lab, int32_t *lab_img, uint8_t *weak);
RF_API void rf_split_labels(const int32_t *lab, int32_t nk, int32_t H, int32_t W, uint8_t *const *outs);
RF_API int32_t rf_absorb_run(const int32_t *own_lab, const int32_t *lab_img, const uint8_t *weak, const double *lab_all, int32_t nk,
                             int32_t H, int32_t W, int64_t max_area, double max_de, double max_de2, int32_t *out_lab, int64_t *stats);

/* label.c: rmb_npops.components (see there) */
RF_API int32_t rf_components(const uint8_t *m, int32_t H, int32_t W, int32_t min_span, int64_t min_area, int64_t **info, uint8_t **crops,
                             int64_t *crops_len);

/* inkpass.c: the painter's ink section and contour pass (see there). The picture's frame and the painter's constants, in
 * this order (the Python face builds the same structure); the store's style ids for the black pens and the hatch. */
typedef struct {
    double ppg, x0, y0, x1, y1, detail, shade, up;
    int32_t tone, painterly, tone_region_wash, shadow_hatch, ink_speck_on_color, hatch_under_wash, outline, line_smooth, cel_median;
    int32_t tool_hl, color_hl, st_fine, st_marker, st_tone, st_outline;
    int64_t draw_min_area;
    double draw_min_page, min_span_g, min_len_page, tone_region_open;
    double shadow_edge_blur, shadow_min_border, shadow_l_step, shadow_min_chroma, shadow_hue_tol, shadow_max_edge,
           shadow_min_internal_grad, shadow_l_pct;
    double ink_speck_covered, ink_core_min, absorb_max_area, ink_density_cell_page, black_mass_thick_paint, black_mass_thick_page,
           ink_line_min_len_page, ink_line_max_density;
    double paper_l, tone_line_l, gray_field_cover, gray_line_max_page, gray_drop_g;
    double cel_min_area, tone_pitch_page, tone_width_page, cel_lo, cel_hi, cel_blur, hatch_cross_at, cel_speck_area, cel_field_cover;
    double hatch_under_min_g, hatch_angle, hatch_angle_2, hatch_pitch_mul;
    double outline_clear_g, outline_min_len_page, outline_width_page;
    double hl_width_max, marker_width_max, hl_scale, pen_scale, fineliner_max;
} rf_ink_params;
/* the entries' validation of these (inkpass.c): every float finite, ppg, detail, up and the two pen scales positive -> 1 */
int rf_ink_params_ok(const rf_ink_params *P);
/* the report: [0] tone wash ran, [1] its washes; [2] shade zones ran, [3] zones, [4] shadow, [5] pairs, [6] l_cut set,
 * [7] l_cut; [8] black fills, [9] no-core washes, [10] mass washes, [11] which came first (1 no-core, 2 mass); [12] gray
 * loop ran, [13] gray pieces dropped; [14] cel bands ran, [15] shade cover, [16] shade floor, [17] [18] each band's
 * lines, [19] tone lines, [20] hatch washes; [21] contour lines */
#define RF_INK_REP 24
RF_API int32_t rf_ink_pass(rf_store *S, const rf_ink_params *P, int32_t H, int32_t W, const uint8_t *black, const uint8_t *tone,
                           const uint8_t *ink, const uint8_t *const *colors, int32_t ncol, const uint8_t *rgb, const uint8_t *lum,
                           const uint8_t *ridge, int32_t **order_out, int32_t *norder, double *rep);

/* npsort.c: numpy.argsort of int64 values as numpy dispatches it here (see there); the scalar path alone */
RF_API int32_t rf_np_argsort_i64(const int64_t *a, int64_t *arg, int64_t n);
RF_API int32_t rf_np_argsort_i64_scalar(const int64_t *a, int64_t *arg, int64_t n);
/* quant.c: np.unique of packed colors, and quantize's per-pixel work (see there) */
RF_API int32_t rf_unique_rgb(const uint8_t *rgb, int64_t n, int32_t *codes, int32_t cap, int32_t *inv);
RF_API int32_t rf_quant_tail(const int32_t *inv0, int32_t nu, const double *ulum, const uint8_t *neutral, const uint8_t *chromatic,
                             const double *uchroma, const int8_t *cat, const int32_t *kidx, int32_t nkeys, const uint8_t *rgb,
                             int32_t H, int32_t W, int32_t mode_r, double mode_max_dl, int32_t black_cut, int32_t ink_cut,
                             int32_t paper_cut, double black_chroma, uint8_t *tone, uint8_t *black, uint8_t *const *keys,
                             uint8_t *ink, int64_t *first, int64_t *counts);
/* palette.c: rm_paint.quantize whole (see there). Its arguments and the painter's constants: */
typedef struct {
    int32_t clusters, tc_quant, dark_gray_washed;
    double black_l, chroma_min, detail, ppg, cel_de, dev_chroma_ceil, tc_paper_l, tc_paper_chroma, tc_ink_chroma, ink_neutral, ink_sat,
           black_chroma, tc_ink_l, ink_chroma_max, ink_l, paper_l, cel_color_r, up, cel_mode_max_dl, detail_precise, despeckle_max_ppg;
} rf_quant_params;
/* every float finite, TC_QUANT >= 2, 1 <= clusters <= 256, detail and CEL_DE positive, the chroma ceiling >= 0 -> 1 */
int rf_quant_params_ok(const rf_quant_params *Q);
RF_API int32_t rf_quantize(const uint8_t *rgb, int32_t H, int32_t W, const rf_quant_params *Q, int32_t **keys_out, uint8_t ***planes_out,
                           int64_t **counts_out);

/* painter.c: the painter's body from the quantized masks to its last stroke (see there). The head's constants: */
typedef struct {
    double pocket_l, gap_close_g, gap_close_page, paper_l, ink_l, hl_min_page, chroma_min, painterly_chroma_share, black_l,
           black_mass_thick_paint, fill_hole_page, absorb_max_de, gray_halo_open, gray_halo_share, tc_ink_l;
    int32_t tc_quant, absorb_max_area;
} rf_head_params;
/* the report: [0] tone pockets absorbed, [1] their pixels; [2] gap close ran, [3] its pixels, [4] its radius; [5]
 * painterly, [6] the chroma share; [7] tonal ink pixels, [8] its wash colors; [9] the coarsening cell, [10] its changed
 * pixels, [11] its occupied cells, [12] whether it voted; [13] the absorber (0 not run: page-scale labels, 1 nothing to
 * absorb, 2 ran), [14] its share, [15] mixed pixels kept, [16] changed pixels; [17] gray halo ran, [18] its pixels;
 * [19] [20] [21] the seconds of the head, the zones and the ink pass; [32 ..] the ink pass's report (RF_INK_REP) */
#define RF_BODY_REP 64
/* stats.c: rm_paint.dark_field (see there) */
RF_API int32_t rf_dark_field(const uint8_t *rgb, int32_t H, int32_t W, double black_l, double min_cover, double min_region,
                             int32_t *on, double *share_out, double *big_out);

/* model.c: rm_model.decompose as one call (see there). The constants of every stage; in `ink`, `head` and `quant` the
 * per-picture fields (ppg, the box, black_l) are set by the call, the rest (and the store's style ids) by the caller. */
typedef struct {
    rf_ink_params ink;
    rf_head_params head;
    rf_quant_params quant;
    double edge_margin_page, black_l, black_l_field, dark_field_min_cover, dark_field_min_region, xdog_sigma_ref, xdog_k, xdog_tau, xdog_ink;
    double knobs[6];                /* rm_regions.KNOBS: area, contrast, rarity, density, elong, contrast_floor */
    double absorb_max_area, density_cell_page, round_fraction, wash_eps, pass_radius, pass_radius_w, origin_x, origin_y;
    int32_t budget_max_rounds, pass_max_points;
} rf_model_params;
/* every float finite and every stage's parameters valid -> 1 */
int rf_model_params_ok(const rf_model_params *M);
typedef struct {
    rf_result res;                  /* the pass's output (rf_result_free) */
    int64_t drawable, final_drawable, specks_cut;
    int32_t touched, engine_strokes, seam_patches, w, h, has_extent;
    double extent[4];
    uint8_t extent_kind[4];
    double secs[5];                 /* the painter, the budget, the painter again, seam, pass */
    double prof[16];                /* per painter run (8 each): dark field, quantize, L and ridge, the body's head, its zones, its
                                       ink pass, the end (wash grouping and extent), unused */
    /* the first painter run's report (its params): ppg, the dark field (on, share, biggest), black_l, the ridge's pixels,
     * the picture's size, the body's report (RF_BODY_REP), the quantized keys (4 ints each: kind, r, g, b) with their pixel counts, and the
     * body's final keys (rf_model_out_free releases the arrays and the result) */
    double ppg, dark_share, dark_big, black_l;
    int32_t dark_on, nq, nf, grid_w, grid_h;
    int64_t ridge_px;
    int32_t *qkeys;
    int64_t *qcounts;
    int32_t *fkeys;
    double body_rep[RF_BODY_REP];
} rf_model_out;
RF_API int32_t rf_decompose_rgb(rf_store *S, const uint8_t *rgb, int32_t H, int32_t W, int32_t width, int64_t budget,
                                const rf_model_params *M, rf_model_out *out);
RF_API int32_t rf_decompose(rf_store *S, const uint8_t *data, int64_t n, int32_t width, int64_t budget, const rf_model_params *M,
                            rf_model_out *out);
/* rm_model.decompose_into: the box w x h given (at the parameters' origin) */
RF_API int32_t rf_decompose_box_rgb(rf_store *S, const uint8_t *rgb, int32_t H, int32_t W, int32_t w, int32_t h, int64_t budget,
                                    const rf_model_params *M, rf_model_out *out);
RF_API int32_t rf_decompose_box(rf_store *S, const uint8_t *data, int64_t n, int32_t w, int32_t h, int64_t budget, const rf_model_params *M,
                                rf_model_out *out);
RF_API void rf_model_out_free(rf_model_out *out);
RF_API int32_t rf_painter_body(rf_store *S, const rf_ink_params *P, const rf_head_params *Hp, int32_t H, int32_t W, int32_t nk,
                              const int32_t *kinds, const int32_t *rgbs, const uint8_t *const *planes, const uint8_t *rgb,
                              const uint8_t *lum, const uint8_t *ridge, int32_t **order_out, int32_t *norder, int32_t **keys_out,
                              int32_t *nkeys_out, double *rep);

#endif
