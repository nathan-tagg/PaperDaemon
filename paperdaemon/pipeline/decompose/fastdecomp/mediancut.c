/* mediancut.c -- `small.quantize(colors, method=Image.Quantize.MEDIANCUT).convert("RGB")` on an RGB picture
 * (DECISION code: the clusters only classify).
 *
 * The median cut itself is Pillow 12.3.0's own code, vendored unchanged in fastdecomp/vendor/pillow (Quant.c's
 * quantize, QuantHash.c, QuantHeap.c). This file is ImagingQuantize's RGB part: each pixel as (r, g, b, 255), the
 * median cut with kmeans 0, then the "P" image read back through its palette, which is what convert("RGB") does.
 * Identity: checked against the reference (random and corpus pictures against Pillow) and the quantizer check. */
#include <stdlib.h>
#include "rmfast.h"
#include "vendor/pillow/QuantTypes.h"

int rf_pillow_quantize(Pixel *pixelData, uint32_t nPixels, uint32_t nQuantPixels, Pixel **palette, uint32_t *paletteLength,
                       uint32_t **quantizedPixels, int kmeans);

/* rgb: n pixels; out: their quantized colors (3 bytes each). -> the palette's length, or -1 (out of memory, n
 * outside 1 .. 2^31, colors outside 1 .. 256: Pillow refuses those too, or Pillow's own failure) */
RF_API int32_t rf_mediancut(const uint8_t *rgb, int64_t n, int32_t colors, uint8_t *out) {
    if (n < 1 || n > INT32_MAX || colors < 1 || colors > 256) return -1;
    Pixel *p = (Pixel *)calloc((size_t)n, sizeof(Pixel));
    if (!p) return -1;
    for (int64_t i = 0; i < n; i++) {
        p[i].c.r = rgb[3 * i]; p[i].c.g = rgb[3 * i + 1]; p[i].c.b = rgb[3 * i + 2]; p[i].c.a = 255;
    }
    Pixel *palette = NULL;
    uint32_t len = 0, *idx = NULL;
    int r = rf_pillow_quantize(p, (uint32_t)n, (uint32_t)colors, &palette, &len, &idx, 0);
    free(p);
    if (r <= 0) { free(palette); free(idx); return -1; }
    for (int64_t i = 0; i < n; i++) {
        /* the "P" image stores (unsigned char)idx; every index is below len <= colors <= 256 */
        const Pixel *c = &palette[(unsigned char)idx[i]];
        out[3 * i] = c->c.r; out[3 * i + 1] = c->c.g; out[3 * i + 2] = c->c.b;
    }
    free(palette); free(idx);
    return (int32_t)len;
}
