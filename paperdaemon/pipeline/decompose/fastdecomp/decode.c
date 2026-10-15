/* decode.c -- the source read as Pillow 12.3.0 reads a PNG: Image.open(png).convert("RGB"), pixel for pixel (INPUT
 * code: integers only).
 *
 * The file is parsed here: the signature, every chunk's length and type, IHDR first. Before the first IDAT every
 * chunk's CRC is checked (Pillow's _open checks them; it skips the IDAT CRCs and does not check the chunks after the
 * image data). The IDAT run is inflated by stb_image's zlib decoder (vendor/stb/stb_zlib.c) into a FIXED buffer --
 * what the image needs plus a small slack, so no stream, a decompression bomb included, makes a larger allocation; one
 * that would write more is refused -- the scanlines unfiltered (None, Sub, Up, Average, Paeth), Adam7 placed, and every sample turned into RGB as Pillow's modes and conversions do
 * (PngImagePlugin._MODES, Unpack.c, Convert.c):
 *   gray 1 bit ("1"): 0 or 255; gray 2 / 4 bit ("L;2" / "L;4"): the sample times 0x55 / 0x11; gray 8 ("L"): the
 *   sample; gray 16 ("I;16"): the sample, or 255 when it is 256 or more (I16_RGB); RGB 8 / 16: the samples / their high
 *   bytes; palette 1 to 8 bit ("P"): the PLTE entry, black past the palette's end (ImagingPaletteNew is calloc'd);
 *   gray + alpha 8 ("LA") / 16 ("RGBA" from LA;16B): the gray sample / its high byte; RGBA 8 / 16: the samples / their
 *   high bytes. Alpha and tRNS never change a pixel of convert("RGB").
 * Anything else is REFUSED (-2), never approximated, and the caller reads the file with Pillow: not a PNG; a chunk
 * cut short; a CRC that does not match before the image data; IHDR not first or twice, a size of 0, over 2^20 a
 * side or over Pillow's MAX_IMAGE_PIXELS (89,478,485), a depth / color pair Pillow does not know, a compression or
 * filter method other than 0, an interlace method other than 0 or 1; a palette image without PLTE before its data, a
 * PLTE that is empty, over 256 entries or not whole entries; IDAT chunks that are not one run; the chunks whose
 * handlers can fail or change what Pillow does (zTXt, iTXt, eXIf, acTL, fcTL, fdAT, CgBI, an unknown critical chunk;
 * an iCCP Pillow could fail on, see iccp_ok), and the ones it reads that are too short for its handler (tRNS, gAMA,
 * cHRM, sRGB, pHYs) or text over 1 MB;
 * a filter byte over 4; image data that inflates short.
 * Identity: a check -- every corpus picture, and generated PNGs of every color type, bit depth and
 * interlace with every filter, against Pillow. */
#include <stdlib.h>
#include <string.h>
#include "rmfast.h"
#include "internal.h"

int stbi_zlib_decode_buffer(char *obuffer, int olen, char const *ibuffer, int ilen);

#define PNG_MAX_SIDE (1 << 20)
#define PNG_MAX_PIXELS 89478485LL          /* PIL.Image.MAX_IMAGE_PIXELS */
#define PNG_MAX_TEXT (1 << 20)
#define PNG_SLACK (1 << 16)                 /* inflated bytes past what the image needs that are still read */

typedef struct {
    int32_t w, h;
    int bd, ct, interlace, mode;
    uint8_t pal[256 * 3];
    int npal, have_pal;
    int64_t idat_bytes;                     /* the IDAT run's data bytes */
    int64_t run_start, run_end;             /* the run's first and past-last byte offsets in the file */
} png_t;

static uint32_t be32(const uint8_t *p) { return ((uint32_t)p[0] << 24) | ((uint32_t)p[1] << 16) | ((uint32_t)p[2] << 8) | (uint32_t)p[3]; }

/* the CRC-32 of PNG (and zlib): polynomial 0xedb88320, reflected, the table built ahead */
static const uint32_t CRC_TABLE[256] = {
    0x00000000u, 0x77073096u, 0xee0e612cu, 0x990951bau, 0x076dc419u, 0x706af48fu, 0xe963a535u, 0x9e6495a3u,
    0x0edb8832u, 0x79dcb8a4u, 0xe0d5e91eu, 0x97d2d988u, 0x09b64c2bu, 0x7eb17cbdu, 0xe7b82d07u, 0x90bf1d91u,
    0x1db71064u, 0x6ab020f2u, 0xf3b97148u, 0x84be41deu, 0x1adad47du, 0x6ddde4ebu, 0xf4d4b551u, 0x83d385c7u,
    0x136c9856u, 0x646ba8c0u, 0xfd62f97au, 0x8a65c9ecu, 0x14015c4fu, 0x63066cd9u, 0xfa0f3d63u, 0x8d080df5u,
    0x3b6e20c8u, 0x4c69105eu, 0xd56041e4u, 0xa2677172u, 0x3c03e4d1u, 0x4b04d447u, 0xd20d85fdu, 0xa50ab56bu,
    0x35b5a8fau, 0x42b2986cu, 0xdbbbc9d6u, 0xacbcf940u, 0x32d86ce3u, 0x45df5c75u, 0xdcd60dcfu, 0xabd13d59u,
    0x26d930acu, 0x51de003au, 0xc8d75180u, 0xbfd06116u, 0x21b4f4b5u, 0x56b3c423u, 0xcfba9599u, 0xb8bda50fu,
    0x2802b89eu, 0x5f058808u, 0xc60cd9b2u, 0xb10be924u, 0x2f6f7c87u, 0x58684c11u, 0xc1611dabu, 0xb6662d3du,
    0x76dc4190u, 0x01db7106u, 0x98d220bcu, 0xefd5102au, 0x71b18589u, 0x06b6b51fu, 0x9fbfe4a5u, 0xe8b8d433u,
    0x7807c9a2u, 0x0f00f934u, 0x9609a88eu, 0xe10e9818u, 0x7f6a0dbbu, 0x086d3d2du, 0x91646c97u, 0xe6635c01u,
    0x6b6b51f4u, 0x1c6c6162u, 0x856530d8u, 0xf262004eu, 0x6c0695edu, 0x1b01a57bu, 0x8208f4c1u, 0xf50fc457u,
    0x65b0d9c6u, 0x12b7e950u, 0x8bbeb8eau, 0xfcb9887cu, 0x62dd1ddfu, 0x15da2d49u, 0x8cd37cf3u, 0xfbd44c65u,
    0x4db26158u, 0x3ab551ceu, 0xa3bc0074u, 0xd4bb30e2u, 0x4adfa541u, 0x3dd895d7u, 0xa4d1c46du, 0xd3d6f4fbu,
    0x4369e96au, 0x346ed9fcu, 0xad678846u, 0xda60b8d0u, 0x44042d73u, 0x33031de5u, 0xaa0a4c5fu, 0xdd0d7cc9u,
    0x5005713cu, 0x270241aau, 0xbe0b1010u, 0xc90c2086u, 0x5768b525u, 0x206f85b3u, 0xb966d409u, 0xce61e49fu,
    0x5edef90eu, 0x29d9c998u, 0xb0d09822u, 0xc7d7a8b4u, 0x59b33d17u, 0x2eb40d81u, 0xb7bd5c3bu, 0xc0ba6cadu,
    0xedb88320u, 0x9abfb3b6u, 0x03b6e20cu, 0x74b1d29au, 0xead54739u, 0x9dd277afu, 0x04db2615u, 0x73dc1683u,
    0xe3630b12u, 0x94643b84u, 0x0d6d6a3eu, 0x7a6a5aa8u, 0xe40ecf0bu, 0x9309ff9du, 0x0a00ae27u, 0x7d079eb1u,
    0xf00f9344u, 0x8708a3d2u, 0x1e01f268u, 0x6906c2feu, 0xf762575du, 0x806567cbu, 0x196c3671u, 0x6e6b06e7u,
    0xfed41b76u, 0x89d32be0u, 0x10da7a5au, 0x67dd4accu, 0xf9b9df6fu, 0x8ebeeff9u, 0x17b7be43u, 0x60b08ed5u,
    0xd6d6a3e8u, 0xa1d1937eu, 0x38d8c2c4u, 0x4fdff252u, 0xd1bb67f1u, 0xa6bc5767u, 0x3fb506ddu, 0x48b2364bu,
    0xd80d2bdau, 0xaf0a1b4cu, 0x36034af6u, 0x41047a60u, 0xdf60efc3u, 0xa867df55u, 0x316e8eefu, 0x4669be79u,
    0xcb61b38cu, 0xbc66831au, 0x256fd2a0u, 0x5268e236u, 0xcc0c7795u, 0xbb0b4703u, 0x220216b9u, 0x5505262fu,
    0xc5ba3bbeu, 0xb2bd0b28u, 0x2bb45a92u, 0x5cb36a04u, 0xc2d7ffa7u, 0xb5d0cf31u, 0x2cd99e8bu, 0x5bdeae1du,
    0x9b64c2b0u, 0xec63f226u, 0x756aa39cu, 0x026d930au, 0x9c0906a9u, 0xeb0e363fu, 0x72076785u, 0x05005713u,
    0x95bf4a82u, 0xe2b87a14u, 0x7bb12baeu, 0x0cb61b38u, 0x92d28e9bu, 0xe5d5be0du, 0x7cdcefb7u, 0x0bdbdf21u,
    0x86d3d2d4u, 0xf1d4e242u, 0x68ddb3f8u, 0x1fda836eu, 0x81be16cdu, 0xf6b9265bu, 0x6fb077e1u, 0x18b74777u,
    0x88085ae6u, 0xff0f6a70u, 0x66063bcau, 0x11010b5cu, 0x8f659effu, 0xf862ae69u, 0x616bffd3u, 0x166ccf45u,
    0xa00ae278u, 0xd70dd2eeu, 0x4e048354u, 0x3903b3c2u, 0xa7672661u, 0xd06016f7u, 0x4969474du, 0x3e6e77dbu,
    0xaed16a4au, 0xd9d65adcu, 0x40df0b66u, 0x37d83bf0u, 0xa9bcae53u, 0xdebb9ec5u, 0x47b2cf7fu, 0x30b5ffe9u,
    0xbdbdf21cu, 0xcabac28au, 0x53b39330u, 0x24b4a3a6u, 0xbad03605u, 0xcdd70693u, 0x54de5729u, 0x23d967bfu,
    0xb3667a2eu, 0xc4614ab8u, 0x5d681b02u, 0x2a6f2b94u, 0xb40bbe37u, 0xc30c8ea1u, 0x5a05df1bu, 0x2d02ef8du,
};

static uint32_t crc32_of(const uint8_t *type, const uint8_t *data, uint32_t len) {
    const uint32_t *table = CRC_TABLE;
    uint32_t c = 0xffffffffu;
    for (int i = 0; i < 4; i++) c = table[(c ^ type[i]) & 0xff] ^ (c >> 8);
    for (uint32_t i = 0; i < len; i++) c = table[(c ^ data[i]) & 0xff] ^ (c >> 8);
    return c ^ 0xffffffffu;
}

/* Pillow's mode for (depth, color type): 0 "1", 1 "L", 2 "I;16", 3 "RGB", 4 "P", 5 "LA", 6 "RGBA"; -1 unknown */
static int pil_mode(int bd, int ct) {
    switch (ct) {
    case 0: return bd == 1 ? 0 : (bd == 2 || bd == 4 || bd == 8) ? 1 : bd == 16 ? 2 : -1;
    case 2: return (bd == 8 || bd == 16) ? 3 : -1;
    case 3: return (bd == 1 || bd == 2 || bd == 4 || bd == 8) ? 4 : -1;
    case 4: return bd == 8 ? 5 : bd == 16 ? 6 : -1;
    case 6: return (bd == 8 || bd == 16) ? 6 : -1;
    default: return -1;
    }
}

static int is_type(const uint8_t *t, const char *s) { return memcmp(t, s, 4) == 0; }

/* Pillow's chunk_iCCP cannot fail on this one: a profile name of 1 to 79 bytes, its null, compression method 0, and
 * a zlib stream that inflates to at most 1 MB - 1 (Pillow raises past MAX_TEXT_CHUNK, 1 MB). The profile never
 * changes a pixel. */
static int iccp_ok(const uint8_t *s, uint32_t len) {
    uint32_t i = 0;
    while (i < len && i < 80 && s[i]) i++;
    if (i == 0 || i >= 80 || i + 2 > len || s[i] != 0 || s[i + 1] != 0) return 0;
    /* inflated into a FIXED buffer of 1 MB - 1: a profile that does not fit (a bomb included) fails there and is
       refused, as Pillow raises past MAX_TEXT_CHUNK; nothing larger is ever allocated */
    char *buf = (char *)malloc(PNG_MAX_TEXT - 1);
    if (!buf) return 0;
    int n = stbi_zlib_decode_buffer(buf, PNG_MAX_TEXT - 1, (const char *)s + i + 2, (int)(len - i - 2));
    free(buf);
    return n >= 0;
}

/* -> 0, or -2 (refused) */
static int parse(const uint8_t *d, int64_t n, png_t *P) {
    static const uint8_t sig[8] = {137, 80, 78, 71, 13, 10, 26, 10};
    memset(P, 0, sizeof(*P));
    if (n < 8 || memcmp(d, sig, 8) != 0) return -2;
    int64_t pos = 8, text = 0;
    int seen_ihdr = 0, seen_idat = 0, run_open = 0;
    while (pos < n) {
        if (n - pos < 12) return -2;
        uint32_t len = be32(d + pos);
        if (len > 0x7fffffffu || (int64_t)len > n - pos - 12) return -2;
        const uint8_t *t = d + pos + 4, *s = d + pos + 8;
        for (int k = 0; k < 4; k++) if (!((t[k] >= 'A' && t[k] <= 'Z') || (t[k] >= 'a' && t[k] <= 'z'))) return -2;
        int64_t next = pos + 12 + (int64_t)len;
        if (!seen_ihdr && !is_type(t, "IHDR")) return -2;
        if (is_type(t, "IDAT")) {
            if (seen_idat && !run_open) return -2;
            if (!seen_idat) { P->run_start = pos; seen_idat = 1; run_open = 1; }
            P->idat_bytes += len;
            P->run_end = next;
            pos = next;
            continue;
        }
        run_open = 0;
        if (!seen_idat && crc32_of(t, s, len) != be32(d + pos + 8 + len)) return -2;
        if (is_type(t, "IEND")) {
            if (!seen_idat) return -2;
            break;
        }
        if (is_type(t, "IHDR")) {
            if (seen_ihdr || len != 13) return -2;
            seen_ihdr = 1;
            uint32_t w = be32(s), h = be32(s + 4);
            P->bd = s[8]; P->ct = s[9]; P->interlace = s[12];
            if (w == 0 || h == 0 || w > PNG_MAX_SIDE || h > PNG_MAX_SIDE || (int64_t)w * (int64_t)h > PNG_MAX_PIXELS) return -2;
            if (s[10] != 0 || s[11] != 0 || P->interlace > 1) return -2;
            P->mode = pil_mode(P->bd, P->ct);
            if (P->mode < 0) return -2;
            P->w = (int32_t)w; P->h = (int32_t)h;
        } else if (is_type(t, "PLTE")) {
            if (!seen_idat && P->ct == 3) {
                if (len == 0 || len > 768 || len % 3 != 0) return -2;
                memcpy(P->pal, s, len);
                P->npal = (int)(len / 3);
                P->have_pal = 1;
            }
        } else if (is_type(t, "tRNS")) {
            if ((P->mode == 0 || P->mode == 1 || P->mode == 2) && len < 2) return -2;
            if (P->mode == 3 && len < 6) return -2;
        } else if (is_type(t, "gAMA")) {
            if (len < 4) return -2;
        } else if (is_type(t, "cHRM")) {
            if (len % 4 != 0) return -2;
        } else if (is_type(t, "sRGB")) {
            if (len < 1) return -2;
        } else if (is_type(t, "pHYs")) {
            if (len < 9) return -2;
        } else if (is_type(t, "tEXt")) {
            text += len;
            if (text > PNG_MAX_TEXT) return -2;
        } else if (is_type(t, "iCCP")) {
            if (!iccp_ok(s, len)) return -2;
        } else if (is_type(t, "zTXt") || is_type(t, "iTXt") || is_type(t, "eXIf") || is_type(t, "acTL")
                   || is_type(t, "fcTL") || is_type(t, "fdAT") || is_type(t, "CgBI")) {
            return -2;
        } else if (t[0] >= 'A' && t[0] <= 'Z') {
            return -2;                                       /* an unknown critical chunk */
        }
        pos = next;
    }
    if (!seen_ihdr || !seen_idat) return -2;
    if (P->ct == 3 && !P->have_pal) return -2;
    return 0;
}

RF_API int32_t rf_png_info(const uint8_t *data, int64_t n, int32_t *info) {
    png_t P;
    int r = parse(data, n, &P);
    if (r) return r;
    info[0] = P.w; info[1] = P.h; info[2] = P.mode;
    return 0;
}

static int paeth(int a, int b, int c) {
    int p = a + b - c, pa = abs(p - a), pb = abs(p - b), pc = abs(p - c);
    if (pa <= pb && pa <= pc) return a;
    return pb <= pc ? b : c;
}

/* sample k of pixel i of an unfiltered row */
static uint32_t sample(const uint8_t *row, int64_t i, int k, int ch, int bd) {
    if (bd == 8) return row[i * ch + k];
    if (bd == 16) { int64_t o = 2 * (i * ch + k); return ((uint32_t)row[o] << 8) | row[o + 1]; }
    int64_t bit = i * bd;                                    /* bd < 8: one channel, packed from the top bit */
    return (uint32_t)(row[bit >> 3] >> (8 - bd - (int)(bit & 7))) & ((1u << bd) - 1u);
}

static void to_rgb(const png_t *P, const uint8_t *row, int64_t i, uint8_t *o) {
    int bd = P->bd;
    uint32_t v;
    switch (P->ct) {
    case 0:
        v = sample(row, i, 0, 1, bd);
        if (bd == 1) v = v ? 255 : 0;
        else if (bd == 2) v *= 0x55;
        else if (bd == 4) v *= 0x11;
        else if (bd == 16) v = v < 256 ? v : 255;
        o[0] = o[1] = o[2] = (uint8_t)v;
        return;
    case 2:
        for (int k = 0; k < 3; k++) { v = sample(row, i, k, 3, bd); o[k] = (uint8_t)(bd == 16 ? v >> 8 : v); }
        return;
    case 3:
        v = sample(row, i, 0, 1, bd);
        if ((int)v < P->npal) { o[0] = P->pal[3 * v]; o[1] = P->pal[3 * v + 1]; o[2] = P->pal[3 * v + 2]; }
        else o[0] = o[1] = o[2] = 0;
        return;
    case 4:
        v = sample(row, i, 0, 2, bd);
        o[0] = o[1] = o[2] = (uint8_t)(bd == 16 ? v >> 8 : v);
        return;
    default:                                                 /* 6 */
        for (int k = 0; k < 3; k++) { v = sample(row, i, k, 4, bd); o[k] = (uint8_t)(bd == 16 ? v >> 8 : v); }
        return;
    }
}

RF_API int32_t rf_png_rgb(const uint8_t *data, int64_t n, uint8_t *rgb) {
    png_t P;
    int r = parse(data, n, &P);
    if (r) return r;
    int ch = P.ct == 0 ? 1 : P.ct == 2 ? 3 : P.ct == 3 ? 1 : P.ct == 4 ? 2 : 4;
    int64_t bits = (int64_t)ch * P.bd, fb = bits < 8 ? 1 : bits / 8;           /* the filters' byte distance */
    static const int X0[7] = {0, 4, 0, 2, 0, 1, 0}, Y0[7] = {0, 0, 4, 0, 2, 0, 1}, DX[7] = {8, 8, 4, 4, 2, 2, 1}, DY[7] = {8, 8, 8, 4, 4, 2, 2};
    int npass = P.interlace ? 7 : 1;
    int64_t need = 0, maxrow = 0;
    for (int p = 0; p < npass; p++) {
        int64_t x0 = P.interlace ? X0[p] : 0, y0 = P.interlace ? Y0[p] : 0, dx = P.interlace ? DX[p] : 1, dy = P.interlace ? DY[p] : 1;
        int64_t pw = P.w > x0 ? (P.w - x0 + dx - 1) / dx : 0, ph = P.h > y0 ? (P.h - y0 + dy - 1) / dy : 0;
        if (!pw || !ph) continue;
        int64_t rb = (pw * bits + 7) / 8;
        need += ph * (1 + rb);
        if (rb > maxrow) maxrow = rb;
    }
    if (need > 0x7fffffff - PNG_SLACK || P.idat_bytes > 0x7fffffff) return -2;
    /* the IDAT run's data, gathered (the chunks' headers and CRCs left out) */
    uint8_t *z = (uint8_t *)malloc((size_t)(P.idat_bytes ? P.idat_bytes : 1));
    uint8_t *prev = (uint8_t *)calloc((size_t)maxrow + 1, 1), *cur = (uint8_t *)malloc((size_t)maxrow + 1);
    if (!z || !prev || !cur) { free(z); free(prev); free(cur); return -1; }
    int64_t zn = 0;
    for (int64_t pos = P.run_start; pos < P.run_end;) {
        uint32_t len = be32(data + pos);
        memcpy(z + zn, data + pos + 8, len);
        zn += len;
        pos += 12 + (int64_t)len;
    }
    /* inflated into a FIXED buffer: what the image needs plus PNG_SLACK for data past it (Pillow stops at what it
       needs and ignores the rest); a stream that would write more fails there and is refused (Pillow reads it), so
       a decompression bomb never makes a larger allocation */
    uint8_t *raw = (uint8_t *)malloc((size_t)(need + PNG_SLACK));
    int outlen = raw ? stbi_zlib_decode_buffer((char *)raw, (int)(need + PNG_SLACK), (const char *)z, (int)zn) : -1;
    free(z);
    if (!raw) { free(prev); free(cur); return -1; }
    if (outlen < 0 || (int64_t)outlen < need) { free(raw); free(prev); free(cur); return -2; }
    int64_t off = 0;
    int rc = 0;
    for (int p = 0; p < npass && !rc; p++) {
        int64_t x0 = P.interlace ? X0[p] : 0, y0 = P.interlace ? Y0[p] : 0, dx = P.interlace ? DX[p] : 1, dy = P.interlace ? DY[p] : 1;
        int64_t pw = P.w > x0 ? (P.w - x0 + dx - 1) / dx : 0, ph = P.h > y0 ? (P.h - y0 + dy - 1) / dy : 0;
        if (!pw || !ph) continue;
        int64_t rb = (pw * bits + 7) / 8;
        memset(prev, 0, (size_t)rb);
        for (int64_t j = 0; j < ph; j++) {
            int f = raw[off];
            const uint8_t *in = raw + off + 1;
            off += 1 + rb;
            if (f > 4) { rc = -2; break; }
            for (int64_t b = 0; b < rb; b++) {
                int a = b >= fb ? cur[b - fb] : 0, up = prev[b], c = b >= fb ? prev[b - fb] : 0, x = in[b];
                switch (f) {
                case 1: x += a; break;
                case 2: x += up; break;
                case 3: x += (a + up) >> 1; break;
                case 4: x += paeth(a, up, c); break;
                default: break;
                }
                cur[b] = (uint8_t)x;
            }
            int64_t y = y0 + j * dy;
            for (int64_t i = 0; i < pw; i++) to_rgb(&P, cur, i, rgb + 3 * ((size_t)y * (size_t)P.w + (size_t)(x0 + i * dx)));
            uint8_t *t = prev; prev = cur; cur = t;
        }
    }
    free(raw);
    free(prev); free(cur);
    return rc;
}
