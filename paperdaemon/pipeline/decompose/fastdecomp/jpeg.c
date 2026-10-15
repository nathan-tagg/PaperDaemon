/* jpeg.c -- the source read as Pillow 12.3.0 reads a JPEG: Image.open(jpeg).convert("RGB"), pixel for pixel (INPUT
 * code: integers only).
 *
 * The decoding is libjpeg-turbo 3.1.4.1's, the library and version Pillow links (vendor/libjpeg-turbo, its sources
 * unchanged; configured as Pillow's Windows build configures it, without the SIMD code -- libjpeg-turbo's own tests
 * hold the plain C and SIMD builds to the same output for the integer IDCT and the fancy upsampling Pillow uses). It
 * is driven as Pillow's JpegDecode.c drives it: the default DCT method (integer, "islow") and fancy upsampling, the
 * output color space JCS_RGB for a three-component image (Pillow's mode "RGB") and JCS_GRAYSCALE for a one-component
 * image (mode "L", which convert("RGB") repeats into all three channels); the input color space as libjpeg-turbo
 * decides it from the markers (Pillow passes no hint).
 * Before that the markers are checked here the way Pillow's JpegImagePlugin reads them, and anything it could fail on
 * or treat differently is REFUSED (-2) -- the caller then reads the file with Pillow -- never approximated: not SOI
 * followed by whole segments back to back (no fill bytes, no junk), a marker other than APPn, DQT, DHT, DRI, COM and
 * one SOF0 / SOF1 / SOF2 before the first SOS (arithmetic, lossless and hierarchical coding refused), a segment shorter
 * than its handler reads (JFIF and Adobe need 7 bytes, DQT whole tables), an MPF (MPO) or Photoshop block, a
 * precision other than 8, a component count other than 1 or 3, a size of 0 or over Pillow's MAX_IMAGE_PIXELS, and any
 * warning or error libjpeg-turbo reports while decoding (a corrupt or cut-short stream).
 * Identity: a check -- JPEGs Pillow writes at many qualities, subsamplings, progressive and baseline,
 * gray and color, odd sizes, restart intervals, with and without JFIF / Exif / ICC / Adobe segments, against
 * Image.open(...).convert("RGB"). */
#include <setjmp.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include "rmfast.h"
#include "internal.h"
#include "vendor/libjpeg-turbo/src/jpeglib.h"

#define JPG_MAX_PIXELS 89478485LL          /* PIL.Image.MAX_IMAGE_PIXELS */

typedef struct { int32_t w, h, layers; } jpg_t;

static uint32_t be16(const uint8_t *p) { return ((uint32_t)p[0] << 8) | p[1]; }

/* -> 0, or -2 (refused) */
static int scan(const uint8_t *d, int64_t n, jpg_t *J) {
    memset(J, 0, sizeof(*J));
    if (n < 4 || d[0] != 0xFF || d[1] != 0xD8) return -2;
    int64_t pos = 2;
    int nsof = 0;
    for (;;) {
        if (n - pos < 4 || d[pos] != 0xFF) return -2;
        int m = d[pos + 1];
        uint32_t len = be16(d + pos + 2);
        if (len < 2 || (int64_t)len > n - pos - 2) return -2;
        const uint8_t *s = d + pos + 4;
        uint32_t sl = len - 2;
        if (m == 0xDA) break;                                        /* SOS: the image data follows */
        if (m >= 0xE0 && m <= 0xEF) {
            if (m == 0xE0 && sl >= 4 && memcmp(s, "JFIF", 4) == 0 && sl < 7) return -2;
            if (m == 0xEE && sl >= 5 && memcmp(s, "Adobe", 5) == 0 && sl < 7) return -2;
            if (m == 0xE2 && sl >= 4 && memcmp(s, "MPF\0", 4) == 0) return -2;
            if (m == 0xED && sl >= 14 && memcmp(s, "Photoshop 3.0\0", 14) == 0) return -2;
        } else if (m == 0xDB) {                                      /* DQT: whole tables only */
            uint32_t k = 0;
            while (k < sl) {
                uint32_t q = 1 + ((s[k] >> 4) == 0 ? 64u : 128u);
                if (sl - k < q) return -2;
                k += q;
            }
        } else if (m == 0xC0 || m == 0xC1 || m == 0xC2) {
            if (nsof++ || sl < 6) return -2;
            if (s[0] != 8) return -2;
            J->h = (int32_t)be16(s + 1); J->w = (int32_t)be16(s + 3); J->layers = s[5];
            if (J->layers != 1 && J->layers != 3) return -2;
            if (sl < 6 + 3u * (uint32_t)J->layers) return -2;
        } else if (m != 0xC4 && m != 0xDD && m != 0xFE) {
            return -2;
        }
        pos += 2 + (int64_t)len;
    }
    if (nsof != 1 || J->w <= 0 || J->h <= 0 || (int64_t)J->w * J->h > JPG_MAX_PIXELS) return -2;
    return 0;
}

RF_API int32_t rf_jpeg_info(const uint8_t *data, int64_t n, int32_t *info) {
    jpg_t J;
    int r = scan(data, n, &J);
    if (r) return r;
    info[0] = J.w; info[1] = J.h; info[2] = J.layers == 1 ? 1 : 3;       /* decode.c's mode codes: 1 "L", 3 "RGB" */
    return 0;
}

/* libjpeg-turbo's errors end the decoding here (longjmp); its warnings are counted and refuse the file */
typedef struct { struct jpeg_error_mgr pub; jmp_buf jb; } jerr_t;

static void on_error(j_common_ptr c) { longjmp(((jerr_t *)c->err)->jb, 1); }
static void on_message(j_common_ptr c) { (void)c; }

RF_API int32_t rf_jpeg_rgb(const uint8_t *data, int64_t n, uint8_t *rgb) {
    jpg_t J;
    int r = scan(data, n, &J);
    if (r) return r;
    if (n > 0x7fffffffLL) return -2;
    /* the library's state lives on the heap: after a longjmp only these pointers are read, and they do not change
       once set (an automatic object changed after setjmp would be indeterminate there) */
    struct jpeg_decompress_struct *volatile ci = (struct jpeg_decompress_struct *)calloc(1, sizeof(struct jpeg_decompress_struct));
    jerr_t *volatile er = (jerr_t *)calloc(1, sizeof(jerr_t));
    JSAMPLE *volatile row = (JSAMPLE *)malloc((size_t)J.w * 3);
    if (!ci || !er || !row) { free(ci); free(er); free(row); return -1; }
    ci->err = jpeg_std_error(&er->pub);
    er->pub.error_exit = on_error;
    er->pub.output_message = on_message;
    if (setjmp(er->jb)) {
        jpeg_destroy_decompress(ci);
        free(ci); free(er); free(row);
        return -2;
    }
    jpeg_create_decompress(ci);
    jpeg_mem_src(ci, data, (unsigned long)n);
    int32_t rc = -2;
    if (jpeg_read_header(ci, TRUE) == JPEG_HEADER_OK && (int32_t)ci->image_width == J.w && (int32_t)ci->image_height == J.h
            && ci->num_components == J.layers) {
        ci->out_color_space = J.layers == 1 ? JCS_GRAYSCALE : JCS_RGB;
        jpeg_start_decompress(ci);
        int comps = ci->output_components;
        if ((int32_t)ci->output_width == J.w && (int32_t)ci->output_height == J.h && comps == (J.layers == 1 ? 1 : 3)) {
            /* one row per call, as Pillow reads them; the row count bounds the loop (a stalled read is refused) */
            int32_t y = 0;
            for (; y < J.h; y++) {
                JSAMPROW rp = row;
                if (jpeg_read_scanlines(ci, &rp, 1) != 1) break;
                uint8_t *o = rgb + 3 * (size_t)y * (size_t)J.w;
                if (comps == 3) memcpy(o, row, 3 * (size_t)J.w);
                else for (int32_t x = 0; x < J.w; x++) o[3 * x] = o[3 * x + 1] = o[3 * x + 2] = row[x];
            }
            if (y == J.h) {
                jpeg_finish_decompress(ci);
                rc = er->pub.num_warnings ? -2 : 0;
            }
        }
    }
    jpeg_destroy_decompress(ci);
    free(ci); free(er); free(row);
    return rc;
}
