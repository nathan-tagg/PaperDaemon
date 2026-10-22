/* PaperDaemon's ONE stroke renderer: every picture of strokes it draws (the pages on the Tablet screen, the page
   pictures cache, the Decompose preview, the host's drafts, what the model is shown of a page) comes from here.

   THE TABLET'S RULE: a pixel is inked when its CENTER is inside the stroke's exact shape -- no minimum width, no
   rounding of widths, half-open edges (measured on the device, 2026-10-01). At ss = 1 that is the tablet's own
   picture; for a screen, ss > 1 draws at ss times the size and averages each ss x ss block down (smooth edges,
   the same shapes).

   THE SHAPES AND THE LAYERING (measured from the desktop app's screenshots and the calibration pages), in FILE
   ORDER, each stroke over what is already there:
     RF_PEN          opaque in its color; each segment a capsule of the segment's mean width (round ends and joints)
     RF_HIGHLIGHTER  each segment a rectangle with FLAT ends, plus a bevel triangle across the OUTER corner of every
                     turn (nothing on the inner side); a per-channel MINIMUM ("darken") over what is under it, which
                     is idempotent, so a stroke crossing itself or one of its own color never darkens twice. Its sides
                     lie WASH_EPS of a target pixel past the width's half: the device paints a wash about a third of a
                     pixel beyond its exact footprint (measured on the zoomed screen share, 2026-10-01), so washes laid
                     edge to edge, as the decomposer lays them, leave no pinholes between them
     RF_SHADER       a translucent wash: its color at its alpha over what is under it, ONCE per pixel per stroke
                     (segments of one stroke overlap; another stroke over it deepens it)
     GRAIN           a pen stroke with a DENSITY per point (0..1, 1 solid): the share of its pixels the tablet inks.
                     The pencils, and the paintbrush and the ballpoint when light, are drawn by the tablet as scattered
                     grain, not as a lighter or thinner solid (measured on the pen-test pages, 2026-10-19: the inked
                     share climbs with pressure, the grain is short streaks along the stroke, denser toward its middle).
                     Each pixel of the stroke is decided ONCE (a stroke's own overlapping segments never ink a pixel
                     twice), from a hash of where it sits along and across the stroke, so the grain moves with the
                     stroke and another stroke over it fills it in.

   Coordinates: points in the canvas's pixels (x right, y down, 0,0 the top left corner of pixel 0,0), widths in
   pixels. The canvas is RGB, 8 bits a channel, W x H, row by row; what is on it (a PDF page, typed text, pictures)
   stays under the strokes. */
#include <math.h>
#include <stdint.h>
#include <stdlib.h>
#include <string.h>

#include "rmfast.h"

enum { RF_PEN = 0, RF_HIGHLIGHTER = 1, RF_SHADER = 2 };
#define WASH_EPS 0.35      /* how far past its exact footprint the device paints a wash, in target pixels (see above) */

typedef struct {
    uint8_t *px;          /* the working canvas, RGB, W x H (ss times the target's size) */
    int32_t W, H;
    int32_t *stamp;       /* the shader's and the grain's: the last stroke that decided each pixel (stroke index + 1), or NULL */
    int32_t ss;
} canvas;

/* a grain stroke's segment, as capsule() needs it: the stroke's seed, the length along the stroke at the segment's
   start, and the densities at its two ends */
typedef struct { uint32_t seed; double u0, da, db; } grain;


static inline uint32_t mix(uint32_t h) {
    h ^= h >> 16; h *= 0x7feb352dU; h ^= h >> 15; h *= 0x846ca68bU; h ^= h >> 16;
    return h;
}

static inline double hash01(uint32_t seed, int32_t a, int32_t b) {
    return mix(seed ^ mix((uint32_t)a * 0x9e3779b9U ^ mix((uint32_t)b + 0x85ebca6bU))) / 4294967296.0;
}

static inline int32_t lo_px(double v) { double f = floor(v - 0.5); return f < -1 ? -1 : (int32_t)f; }
static inline int32_t hi_px(double v) { return (int32_t)ceil(v - 0.5); }

static inline void put(canvas *c, int32_t x, int32_t y, int kind, const uint8_t *rgba, int32_t sid) {
    uint8_t *p = c->px + ((size_t)y * c->W + x) * 3;
    if (kind == RF_PEN) {
        p[0] = rgba[0]; p[1] = rgba[1]; p[2] = rgba[2];
    } else if (kind == RF_HIGHLIGHTER) {
        if (rgba[0] < p[0]) p[0] = rgba[0];
        if (rgba[1] < p[1]) p[1] = rgba[1];
        if (rgba[2] < p[2]) p[2] = rgba[2];
    } else {
        int32_t *s = c->stamp + (size_t)y * c->W + x;
        if (*s == sid) return;
        *s = sid;
        double a = rgba[3] / 255.0;
        for (int k = 0; k < 3; k++) p[k] = (uint8_t)lround(p[k] + (rgba[k] - p[k]) * a);
    }
}

/* is this pixel of a grain stroke inked? Decided once per stroke: the first segment to reach it decides, from where it
   sits along (u) and across (v) the stroke, in target pixels */
static inline int grain_ink(canvas *c, int32_t x, int32_t y, const grain *g, double u, double v, double r, double t, int32_t sid) {
    int32_t *s = c->stamp + (size_t)y * c->W + x;
    if (*s == sid) return 0;
    *s = sid;
    double d = g->da + (g->db - g->da) * t, q = r > 0 ? v / r : 0;
    (void)q;                                                /* even across the width, as the tablet's grain */
    if (d >= 1) return 1;
    if (d <= 0) return 0;
    /* THE PAPER'S GRAIN (ui/shaders.js FS_SEG): one texture fixed to the page, the same pixels for every stroke */
    double ss = c->ss;
    (void)u;
    return hash01(0x2545f491u, (int32_t)floor(x / ss), (int32_t)floor(y / ss)) < d;
}

/* a capsule: the points within r of the segment a-b (a disc when a == b); with `g`, a grain stroke's segment */
static void capsule(canvas *c, double ax, double ay, double bx, double by, double r, int kind, const uint8_t *rgba, int32_t sid,
                    const grain *g) {
    if (!(r > 0)) return;
    int32_t x0 = lo_px(fmin(ax, bx) - r), x1 = hi_px(fmax(ax, bx) + r);
    int32_t y0 = lo_px(fmin(ay, by) - r), y1 = hi_px(fmax(ay, by) + r);
    if (x0 < 0) x0 = 0;
    if (y0 < 0) y0 = 0;
    if (x1 > c->W - 1) x1 = c->W - 1;
    if (y1 > c->H - 1) y1 = c->H - 1;
    double dx = bx - ax, dy = by - ay, L2 = dx * dx + dy * dy, r2 = r * r, L = sqrt(L2);
    for (int32_t y = y0; y <= y1; y++) {
        double py = y + 0.5;
        for (int32_t x = x0; x <= x1; x++) {
            double px = x + 0.5, t = 0, tu = 0;
            if (L2 > 0) {
                tu = ((px - ax) * dx + (py - ay) * dy) / L2;
                t = tu < 0 ? 0 : (tu > 1 ? 1 : tu);
            }
            double ex = px - (ax + t * dx), ey = py - (ay + t * dy);
            if (ex * ex + ey * ey > r2) continue;
            if (g) {
                /* along: the projection, unclamped, so a pixel past the segment's end sits where the next one puts it;
                   across: the distance from the segment's line (from its center on a single point's disc) */
                double v = L > 0 ? ((px - ax) * dy - (py - ay) * dx) / L : sqrt(ex * ex + ey * ey);
                if (!grain_ink(c, x, y, g, g->u0 + tu * L, v, r, t, sid)) continue;
            }
            put(c, x, y, kind, rgba, sid);
        }
    }
}

/* a convex polygon (4 or 3 corners, either winding): its interior, half-open (a center exactly on an edge is in
   only on the edges facing up and left) */
static void convex(canvas *c, const double *qx, const double *qy, int n, int kind, const uint8_t *rgba, int32_t sid) {
    double mnx = qx[0], mxx = qx[0], mny = qy[0], mxy = qy[0];
    double area = 0;
    for (int i = 0; i < n; i++) {
        mnx = fmin(mnx, qx[i]); mxx = fmax(mxx, qx[i]); mny = fmin(mny, qy[i]); mxy = fmax(mxy, qy[i]);
        int j = (i + 1) % n;
        area += qx[i] * qy[j] - qx[j] * qy[i];
    }
    if (fabs(area) < 1e-12) return;
    double sgn = area > 0 ? 1 : -1;
    int32_t x0 = lo_px(mnx), x1 = hi_px(mxx), y0 = lo_px(mny), y1 = hi_px(mxy);
    if (x0 < 0) x0 = 0;
    if (y0 < 0) y0 = 0;
    if (x1 > c->W - 1) x1 = c->W - 1;
    if (y1 > c->H - 1) y1 = c->H - 1;
    for (int32_t y = y0; y <= y1; y++) {
        double py = y + 0.5;
        for (int32_t x = x0; x <= x1; x++) {
            double px = x + 0.5;
            int in = 1;
            for (int i = 0; i < n && in; i++) {
                int j = (i + 1) % n;
                double e = sgn * ((qx[j] - qx[i]) * (py - qy[i]) - (qy[j] - qy[i]) * (px - qx[i]));
                if (e < 0) in = 0;
                else if (e == 0) {                         /* on the edge: in only for a top or left edge */
                    double ex = (qx[j] - qx[i]) * sgn, ey = (qy[j] - qy[i]) * sgn;
                    if (!(ey > 0 || (ey == 0 && ex < 0))) in = 0;
                }
            }
            if (in) put(c, x, y, kind, rgba, sid);
        }
    }
}

/* a grain stroke's seed: from where it starts (in target pixels), so it keeps its grain wherever it sits in the file */
static uint32_t stroke_seed(const double *xy, int32_t ss) {
    return mix((uint32_t)(int64_t)llround(xy[0] / ss * 16) * 0x27d4eb2dU ^ mix((uint32_t)(int64_t)llround(xy[1] / ss * 16)));
}

static void pen(canvas *c, const double *xy, const double *w, const double *dens, int32_t n, int kind, const uint8_t *rgba,
                int32_t sid) {
    grain g = {0, 0, 1, 1}, *gp = NULL;
    if (dens && kind == RF_PEN) {
        for (int32_t i = 0; i < n; i++)
            if (dens[i] < 1) { gp = &g; break; }
        if (gp) g.seed = stroke_seed(xy, c->ss);
    }
    if (n == 1) {
        if (gp) g.da = g.db = dens[0];
        capsule(c, xy[0], xy[1], xy[0], xy[1], w[0] / 2.0, kind, rgba, sid, gp);
        return;
    }
    for (int32_t i = 0; i + 1 < n; i++) {
        if (gp) { g.da = dens[i]; g.db = dens[i + 1]; }
        capsule(c, xy[2 * i], xy[2 * i + 1], xy[2 * i + 2], xy[2 * i + 3], (w[i] + w[i + 1]) / 4.0, kind, rgba, sid, gp);
        if (gp) g.u0 += hypot(xy[2 * i + 2] - xy[2 * i], xy[2 * i + 3] - xy[2 * i + 1]);
    }
}

static void highlighter(canvas *c, const double *xy, const double *w, int32_t n, int kind, const uint8_t *rgba, int32_t sid,
                        double *sx, double *sy, double *sw, double *dx, double *dy, double *hw) {
    /* the points, repeats dropped */
    int32_t m = 0;
    for (int32_t i = 0; i < n; i++) {
        if (m && fabs(xy[2 * i] - sx[m - 1]) <= 1e-6 && fabs(xy[2 * i + 1] - sy[m - 1]) <= 1e-6) continue;
        sx[m] = xy[2 * i]; sy[m] = xy[2 * i + 1]; sw[m] = w[i]; m++;
    }
    if (m < 2) return;
    for (int32_t i = 0; i + 1 < m; i++) {
        double ex = sx[i + 1] - sx[i], ey = sy[i + 1] - sy[i], L = sqrt(ex * ex + ey * ey);
        dx[i] = ex / L; dy[i] = ey / L;
        hw[i] = (sw[i] + sw[i + 1]) / 4.0 + WASH_EPS * c->ss;
    }
    for (int32_t i = 0; i + 1 < m; i++) {
        double nx = -dy[i] * hw[i], ny = dx[i] * hw[i];
        double qx[4] = {sx[i] + nx, sx[i + 1] + nx, sx[i + 1] - nx, sx[i] - nx};
        double qy[4] = {sy[i] + ny, sy[i + 1] + ny, sy[i + 1] - ny, sy[i] - ny};
        convex(c, qx, qy, 4, kind, rgba, sid);
    }
    for (int32_t i = 1; i + 1 < m; i++) {
        double cross = dx[i - 1] * dy[i] - dy[i - 1] * dx[i];
        if (fabs(cross) < 1e-6) continue;
        double s = cross > 0 ? -1.0 : 1.0;                /* the outer side of the turn */
        double qx[3] = {sx[i], sx[i] + s * (-dy[i - 1]) * hw[i - 1], sx[i] + s * (-dy[i]) * hw[i]};
        double qy[3] = {sy[i], sy[i] + s * dx[i - 1] * hw[i - 1], sy[i] + s * dx[i] * hw[i]};
        convex(c, qx, qy, 3, kind, rgba, sid);
    }
}

/* Draw `nstrokes` strokes over the RGB canvas `rgb` (W x H), at `ss` times its size averaged down (1 = the tablet's
   own pixels). Stroke s has counts[s] points from xy (x, y pairs) and w (widths), its kind (RF_PEN, RF_HIGHLIGHTER,
   RF_SHADER) and rgba[4 s .. 4 s + 3]; `dens`, when not NULL, a density per point (see GRAIN above; a pen stroke whose
   densities are all 1 is solid). `progress`, when not NULL, is set to the share of the strokes drawn.
   -> 0, or -1 when memory ran out (the canvas is then unchanged). */
int32_t rf_render_grain(uint8_t *rgb, int32_t W, int32_t H, int32_t ss, const double *xy, const double *w, const double *dens,
                        const int32_t *counts, const int32_t *kinds, const uint8_t *rgba, int32_t nstrokes, double *progress) {
    if (ss < 1) ss = 1;
    canvas c = {NULL, W * ss, H * ss, NULL, ss};
    int32_t most = 1, shader = 0;
    size_t total = 0;
    for (int32_t s = 0; s < nstrokes; s++) {
        if (counts[s] > most) most = counts[s];
        if (kinds[s] == RF_SHADER) shader = 1;
        total += (size_t)(counts[s] > 0 ? counts[s] : 0);
    }
    if (dens)
        for (size_t i = 0; i < total && !shader; i++)
            if (dens[i] < 1) shader = 1;                 /* the grain decides each pixel once too: it needs the stamps */
    double *sd = dens ? (double *)malloc(sizeof(double) * (size_t)most) : NULL;
    double *scratch = (double *)malloc(sizeof(double) * 6 * (size_t)most);
    double *sxy = (double *)malloc(sizeof(double) * 2 * (size_t)most);
    double *sw = (double *)malloc(sizeof(double) * (size_t)most);
    if (ss == 1) c.px = rgb;
    else c.px = (uint8_t *)malloc((size_t)c.W * c.H * 3);
    if (shader) c.stamp = (int32_t *)calloc((size_t)c.W * c.H, sizeof(int32_t));
    if (!scratch || !sxy || !sw || !c.px || (shader && !c.stamp) || (dens && !sd)) {
        free(scratch); free(sxy); free(sw); free(c.stamp); free(sd);
        if (ss != 1) free(c.px);
        return -1;
    }
    if (ss != 1)                                          /* what is under the strokes, at the working size */
        for (int32_t y = 0; y < c.H; y++)
            for (int32_t x = 0; x < c.W; x++)
                memcpy(c.px + ((size_t)y * c.W + x) * 3, rgb + ((size_t)(y / ss) * W + x / ss) * 3, 3);
    size_t at = 0;
    for (int32_t s = 0; s < nstrokes; s++) {
        int32_t n = counts[s];
        if (n > 0) {
            for (int32_t i = 0; i < n; i++) {
                sxy[2 * i] = xy[2 * (at + i)] * ss;
                sxy[2 * i + 1] = xy[2 * (at + i) + 1] * ss;
                sw[i] = w[at + i] * ss;
                if (sd) sd[i] = dens[at + i];
            }
            const uint8_t *col = rgba + 4 * (size_t)s;
            if (kinds[s] == RF_HIGHLIGHTER)
                highlighter(&c, sxy, sw, n, RF_HIGHLIGHTER, col, s + 1, scratch, scratch + most, scratch + 2 * most,
                            scratch + 3 * most, scratch + 4 * most, scratch + 5 * most);
            else
                pen(&c, sxy, sw, sd, n, kinds[s] == RF_SHADER ? RF_SHADER : RF_PEN, col, s + 1);
        }
        at += (size_t)n;
        if (progress && (s & 511) == 0) *progress = (double)s / (double)nstrokes;
    }
    if (ss != 1) {                                        /* each ss x ss block averaged down */
        int32_t k2 = ss * ss;
        for (int32_t y = 0; y < H; y++)
            for (int32_t x = 0; x < W; x++)
                for (int ch = 0; ch < 3; ch++) {
                    int32_t sum = 0;
                    for (int32_t j = 0; j < ss; j++) {
                        const uint8_t *row = c.px + ((size_t)(y * ss + j) * c.W + (size_t)x * ss) * 3 + ch;
                        for (int32_t i = 0; i < ss; i++) sum += row[3 * i];
                    }
                    rgb[((size_t)y * W + x) * 3 + ch] = (uint8_t)((sum + k2 / 2) / k2);
                }
        free(c.px);
    }
    if (progress) *progress = 1.0;
    free(scratch); free(sxy); free(sw); free(c.stamp); free(sd);
    return 0;
}

/* THE HIGHLIGHTERS FOR THE GRAPHICS CARD (pipeline/page/gpu.py, ui/shaders.js VS_HL), by highlighter()'s own rules:
   for each highlighter stroke's points, which are KEPT (repeats dropped against the last point kept) and, on the kept
   ones, the flags the shader reads -- 1 a segment from this point to the next kept one, 4 a bevel at this point (the
   turn from the segment before: |cross| >= 1e-6), 8 that bevel on the other side (cross > 0) -- with 128 marking a point
   kept. Points in the target's pixels, as rf_render_grain takes them. flags: one byte a point of every stroke (left 0 for
   strokes that are not highlighters). -> 0. */
int32_t rf_hl_marks(const double *xy, const int32_t *counts, const int32_t *kinds, int32_t nstrokes, uint8_t *flags) {
    int64_t at = 0;
    for (int32_t s = 0; s < nstrokes; s++) {
        int32_t n = counts[s];
        if (n <= 0) continue;
        if (kinds[s] != RF_HIGHLIGHTER) { at += n; continue; }
        const double *p = xy + 2 * at;
        uint8_t *f = flags + at;
        int32_t last = 0, prev_seg = -1;                  /* last: the point kept last; prev_seg: where the segment before starts */
        double pdx = 0, pdy = 0;
        f[0] = 128;
        for (int32_t i = 1; i < n; i++) {
            f[i] = 0;
            if (fabs(p[2 * i] - p[2 * last]) <= 1e-6 && fabs(p[2 * i + 1] - p[2 * last + 1]) <= 1e-6) continue;
            double ex = p[2 * i] - p[2 * last], ey = p[2 * i + 1] - p[2 * last + 1], L = sqrt(ex * ex + ey * ey);
            double dx = ex / L, dy = ey / L;
            f[last] |= 1;                                  /* a segment from `last` to i */
            if (prev_seg >= 0) {
                double cross = pdx * dy - pdy * dx;
                if (fabs(cross) >= 1e-6) f[last] |= cross > 0 ? (4 | 8) : 4;
            }
            f[i] = 128;
            pdx = dx; pdy = dy; prev_seg = last; last = i;
        }
        at += n;
    }
    return 0;
}

/* the same, every stroke solid */
int32_t rf_render(uint8_t *rgb, int32_t W, int32_t H, int32_t ss, const double *xy, const double *w,
                  const int32_t *counts, const int32_t *kinds, const uint8_t *rgba, int32_t nstrokes, double *progress) {
    return rf_render_grain(rgb, W, H, ss, xy, w, NULL, counts, kinds, rgba, nstrokes, progress);
}
