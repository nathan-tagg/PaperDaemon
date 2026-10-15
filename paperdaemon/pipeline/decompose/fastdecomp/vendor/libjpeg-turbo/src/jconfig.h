/* jconfig.h for the vendored libjpeg-turbo 3.1.4.1 (fastdecomp/jpeg.c's reader), written by hand from jconfig.h.in
 * with the values Pillow 12.3.0's Windows build uses (winbuild/build_prepare.py: cmake -DWITH_JPEG8=TRUE, the
 * defaults otherwise), except that no SIMD code is compiled (libjpeg-turbo's tests hold the plain C and SIMD builds
 * to the same output for the integer IDCT and fancy upsampling) and arithmetic decoding is left out (the reader
 * refuses arithmetic-coded files before libjpeg-turbo sees them). */
#define JPEG_LIB_VERSION  80
#define LIBJPEG_TURBO_VERSION  3.1.4.1
#define LIBJPEG_TURBO_VERSION_NUMBER  3001004
#define MEM_SRCDST_SUPPORTED  1
#ifndef BITS_IN_JSAMPLE
#define BITS_IN_JSAMPLE  8
#endif
#ifdef _WIN32
#undef RIGHT_SHIFT_IS_UNSIGNED
#ifndef __RPCNDR_H__
typedef unsigned char boolean;
#endif
#define HAVE_BOOLEAN
#if !(defined(_BASETSD_H_) || defined(_BASETSD_H))
typedef short INT16;
typedef signed int INT32;
#endif
#define XMD_H
#endif