/* jconfigint.h for the vendored libjpeg-turbo 3.1.4.1, written by hand from jconfigint.h.in (see jconfig.h). */
#define BUILD  "fastdecomp"
#define HIDDEN  __attribute__((visibility("hidden")))
#undef inline
#define INLINE  __inline__ __attribute__((always_inline))
#define THREAD_LOCAL  _Thread_local
#define PACKAGE_NAME  "libjpeg-turbo"
#define VERSION  "3.1.4.1"
#define SIZEOF_SIZE_T  8
#define HAVE_BUILTIN_CTZL
#if defined(__has_attribute)
#if __has_attribute(fallthrough)
#define FALLTHROUGH  __attribute__((fallthrough));
#else
#define FALLTHROUGH
#endif
#else
#define FALLTHROUGH
#endif
#ifndef BITS_IN_JSAMPLE
#define BITS_IN_JSAMPLE  8
#endif
#undef C_ARITH_CODING_SUPPORTED
#undef D_ARITH_CODING_SUPPORTED
#undef WITH_SIMD