x86-simd-sort, vendored UNCHANGED from the copy numpy 2.5.3 builds against: the src/ headers and LICENSE.md of
numpy-2.5.3/numpy/_core/src/npysort/x86-simd-sort in the numpy 2.5.3 source distribution from PyPI
(numpy-2.5.3.tar.gz, sha256 df2d5874ff183595a4ba404edd04f6bd9b5505c1d7708573f6a6c17489a67563).
fastdecomp/npsort_avx2.cpp compiles its 64-bit argsort for the X86_V3 (AVX2) target, the build numpy dispatches
np.argsort to on a CPU with that level (fastdecomp/npsort.c).
