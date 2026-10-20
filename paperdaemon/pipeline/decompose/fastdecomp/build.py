r"""Build rmfast (the decomposer's C stages) with the clang that the `ziglang` package carries -- no system toolchain,
and the same command on any machine. -march=native: the binary is built for the CPU it runs on (recompiled when
the hardware changes); -ffp-contract=off and no fast-math: every floating-point rounding is the one the Python made,
which is what keeps the output bit-identical.

    uv run python paperdaemon/pipeline/fastdecomp/build.py            -> rmfast.dll beside it (or .so / .dylib)
    uv run python paperdaemon/pipeline/fastdecomp/build.py --generic  -> a build for any x86-64 (no -march=native)
    uv run python paperdaemon/pipeline/fastdecomp/build.py --check --out PATH
        -> the CHECKING build: undefined behavior and array bounds trapped (clang -fsanitize=undefined,bounds with
           -fsanitize-trap=all: a violation stops the process at the faulting instruction instead of continuing)
"""
import os
import subprocess
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
SOURCES = ["raster.c", "render.c", "rmlines.c", "sets.c", "pass.c", "seam.c", "plan.c", "quant.c", "label.c", "absorb.c", "npsum.c", "threads.c", "zones.c", "regions.c", "outline.c", "pockets.c", "store.c", "blur.c", "lab.c", "tonal.c", "flow.c", "stats.c", "xdog.c", "mediancut.c", "merge.c", "specks.c", "decode.c", "cel.c", "hatch.c", "skel.c", "owners.c", "rank.c", "black.c", "inkpass.c", "painter.c", "npsort.c", "palette.c", "model.c", "vendor/pillow/Quant.c", "vendor/pillow/QuantHash.c", "vendor/pillow/QuantHeap.c", "vendor/stb/stb_zlib.c", "jpeg.c", "vendor/libjpeg-turbo/src/jdapimin.c", "vendor/libjpeg-turbo/src/jdatasrc.c", "vendor/libjpeg-turbo/src/jdhuff.c", "vendor/libjpeg-turbo/src/jdinput.c", "vendor/libjpeg-turbo/src/jdlhuff.c", "vendor/libjpeg-turbo/src/jdmarker.c", "vendor/libjpeg-turbo/src/jdmaster.c", "vendor/libjpeg-turbo/src/jdphuff.c", "vendor/libjpeg-turbo/src/jerror.c", "vendor/libjpeg-turbo/src/jmemmgr.c", "vendor/libjpeg-turbo/src/jmemnobs.c", "vendor/libjpeg-turbo/src/jcomapi.c", "vendor/libjpeg-turbo/src/jpeg_nbits.c", "vendor/libjpeg-turbo/src/wrapper/jdapistd-12.c", "vendor/libjpeg-turbo/src/wrapper/jdapistd-16.c", "vendor/libjpeg-turbo/src/wrapper/jdapistd-8.c", "vendor/libjpeg-turbo/src/wrapper/jdcoefct-12.c", "vendor/libjpeg-turbo/src/wrapper/jdcoefct-8.c", "vendor/libjpeg-turbo/src/wrapper/jdcolor-12.c", "vendor/libjpeg-turbo/src/wrapper/jdcolor-16.c", "vendor/libjpeg-turbo/src/wrapper/jdcolor-8.c", "vendor/libjpeg-turbo/src/wrapper/jddctmgr-12.c", "vendor/libjpeg-turbo/src/wrapper/jddctmgr-8.c", "vendor/libjpeg-turbo/src/wrapper/jddiffct-12.c", "vendor/libjpeg-turbo/src/wrapper/jddiffct-16.c", "vendor/libjpeg-turbo/src/wrapper/jddiffct-8.c", "vendor/libjpeg-turbo/src/wrapper/jdlossls-12.c", "vendor/libjpeg-turbo/src/wrapper/jdlossls-16.c", "vendor/libjpeg-turbo/src/wrapper/jdlossls-8.c", "vendor/libjpeg-turbo/src/wrapper/jdmainct-12.c", "vendor/libjpeg-turbo/src/wrapper/jdmainct-16.c", "vendor/libjpeg-turbo/src/wrapper/jdmainct-8.c", "vendor/libjpeg-turbo/src/wrapper/jdmerge-12.c", "vendor/libjpeg-turbo/src/wrapper/jdmerge-8.c", "vendor/libjpeg-turbo/src/wrapper/jdpostct-12.c", "vendor/libjpeg-turbo/src/wrapper/jdpostct-16.c", "vendor/libjpeg-turbo/src/wrapper/jdpostct-8.c", "vendor/libjpeg-turbo/src/wrapper/jdsample-12.c", "vendor/libjpeg-turbo/src/wrapper/jdsample-16.c", "vendor/libjpeg-turbo/src/wrapper/jdsample-8.c", "vendor/libjpeg-turbo/src/wrapper/jidctflt-12.c", "vendor/libjpeg-turbo/src/wrapper/jidctflt-8.c", "vendor/libjpeg-turbo/src/wrapper/jidctfst-12.c", "vendor/libjpeg-turbo/src/wrapper/jidctfst-8.c", "vendor/libjpeg-turbo/src/wrapper/jidctint-12.c", "vendor/libjpeg-turbo/src/wrapper/jidctint-8.c", "vendor/libjpeg-turbo/src/wrapper/jidctred-12.c", "vendor/libjpeg-turbo/src/wrapper/jidctred-8.c", "vendor/libjpeg-turbo/src/wrapper/jquant1-12.c", "vendor/libjpeg-turbo/src/wrapper/jquant1-8.c", "vendor/libjpeg-turbo/src/wrapper/jquant2-12.c", "vendor/libjpeg-turbo/src/wrapper/jquant2-8.c", "vendor/libjpeg-turbo/src/wrapper/jutils-12.c", "vendor/libjpeg-turbo/src/wrapper/jutils-16.c", "vendor/libjpeg-turbo/src/wrapper/jutils-8.c"]


def lib_name():
    if sys.platform.startswith("win"):
        return "rmfast.dll"
    if sys.platform == "darwin":
        return "librmfast.dylib"
    return "librmfast.so"


# numpy's X86_V3 dispatch target: the one C++ file (the vendored x86-simd-sort's argsort, npsort_avx2.cpp) is compiled
# for exactly this level, whatever the rest of the build targets, so the library picks the AVX2 code numpy runs
X86_V3 = ["-mavx", "-mavx2", "-mfma", "-mf16c", "-mbmi", "-mbmi2", "-mlzcnt", "-mpopcnt", "-mmovbe", "-msse4.2", "-mssse3"]


def build(generic=False, verbose=True, out=None, check=False):
    out = out or os.path.join(HERE, lib_name())
    # zig keeps its compile cache beside the sources, not in the user profile
    env = dict(os.environ)
    cache = os.path.join(HERE, ".zig-cache-global")
    env.setdefault("ZIG_GLOBAL_CACHE_DIR", cache)
    env.setdefault("ZIG_LOCAL_CACHE_DIR", cache)
    t = time.time()
    obj = out + ".npsort_avx2.o"
    cpp = [sys.executable, "-m", "ziglang", "c++", "-c", "-O1" if check else "-O3", "-std=c++17", "-fno-exceptions", "-ffp-contract=off",
           "-fno-fast-math", "-Wno-nullability-completeness"] + X86_V3 + \
          (["-g", "-fsanitize=undefined,bounds", "-fsanitize-trap=all"] if check else []) + \
          ["-I", os.path.join(HERE, "vendor", "x86-simd-sort", "src"), "-o", obj, os.path.join(HERE, "npsort_avx2.cpp")]
    r = subprocess.run(cpp, capture_output=True, text=True, env=env)
    if r.returncode != 0:
        print(r.stdout)
        print(r.stderr)
        raise SystemExit("build failed (npsort_avx2.cpp)")
    cmd = [sys.executable, "-m", "ziglang", "cc", "-O1" if check else "-O3", "-std=c11", "-Wall", "-Wextra", "-Wno-unused-parameter",
           "-ffp-contract=off", "-fno-fast-math", "-shared", "-o", out] + [os.path.join(HERE, s) for s in SOURCES] + [obj, "-lc++"]
    if not generic:
        cmd.insert(5, "-march=native")
    if check:
        cmd[5:5] = ["-g", "-fsanitize=undefined,bounds", "-fsanitize-trap=all"]
    if not sys.platform.startswith("win"):
        cmd.append("-lm")
    r = subprocess.run(cmd, capture_output=True, text=True, env=env)
    if os.path.exists(obj):
        os.remove(obj)
    if r.returncode != 0:
        print(r.stdout)
        print(r.stderr)
        raise SystemExit("build failed")
    if r.stderr.strip() and verbose:
        print(r.stderr)
    if verbose:
        print("built %s in %.1f s (%s%s)" % (out, time.time() - t, "generic x86-64" if generic else "this machine's CPU",
                                            ", checking build" if check else ""))
    return out


if __name__ == "__main__":
    # --out PATH: build to another file (rmfast.py loads it when RMFAST_LIB names it), e.g. while a running process
    # holds the library open
    out = sys.argv[sys.argv.index("--out") + 1] if "--out" in sys.argv else None
    build(generic="--generic" in sys.argv, out=out, check="--check" in sys.argv)
