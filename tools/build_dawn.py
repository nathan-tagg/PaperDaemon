r"""Build Dawn -- WebGPU on Direct3D 12 and 11 -- for the engine's pictures on the graphics card (pipeline/page/gpu.py):
webgpu_dawn.dll, with Dawn's LICENSE (BSD-3-Clause), into paperdaemon/pipeline/page/dawn/, which the app carries with
the rest of the pipeline's files -- and beside it the build's own webgpu.h made into plain C declarations (webgpu.cdef,
which gpu.py hands to cffi: every struct as this build lays it out), its flag constants (webgpu.flags.json), and cffi's
out-of-line module of those declarations (_dawn_cffi.py, made again on every run: the engine parses none at run time). The
page editor draws with WebView2's WebGPU, which is Dawn; this is the engine's build of the same, so both run
ui/shaders.js's WGSL as written.

    uv run python tools/build_dawn.py          -> the DLL in place for DAWN_PIN (nothing done when it already is)
    uv run python tools/build_dawn.py --force  -> built again

A build needs, once: Visual Studio 2022 (Build Tools will do) with the C++ x64 tools and the Windows SDK; CMake and
Ninja on PATH or in the folder DAWN_TOOLS names; and a Dawn checkout named by DAWN_SRC
(`git clone https://dawn.googlesource.com/dawn`). Dawn's own script fetches its dependencies (DAWN_FETCH_DEPENDENCIES).
Only Direct3D 12 and 11 are built (no Vulkan, OpenGL, samples or tests), with the C runtime linked in: the DLL needs
nothing but Windows' own libraries and its d3dcompiler_47.dll.
"""
import argparse
import json
import os
import re
import shutil
import subprocess

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT = os.path.join(ROOT, "paperdaemon", "pipeline", "page", "dawn")
DAWN_PIN = "106704a9ac3fc21b1580ea85aea302ac17d416f1"            # Dawn main, the commit built
DLL = "webgpu_dawn.dll"
OPTIONS = ["-DCMAKE_BUILD_TYPE=Release", "-DCMAKE_MSVC_RUNTIME_LIBRARY=MultiThreaded", "-DABSL_MSVC_STATIC_RUNTIME=ON",
           "-DDAWN_FETCH_DEPENDENCIES=ON", "-DDAWN_FORCE_SYSTEM_COMPONENT_LOAD=ON",   # Windows' own d3dcompiler_47.dll
           "-DDAWN_BUILD_MONOLITHIC_LIBRARY=SHARED", "-DDAWN_ENABLE_D3D12=ON", "-DDAWN_ENABLE_D3D11=ON",
           "-DDAWN_ENABLE_VULKAN=OFF", "-DDAWN_ENABLE_DESKTOP_GL=OFF", "-DDAWN_ENABLE_OPENGLES=OFF", "-DDAWN_ENABLE_NULL=OFF",
           "-DDAWN_ENABLE_WEBGPU_ON_WEBGPU=OFF", "-DDAWN_BUILD_SAMPLES=OFF", "-DDAWN_BUILD_TESTS=OFF", "-DDAWN_USE_GLFW=OFF",
           "-DDAWN_USE_WINDOWS_UI=OFF", "-DDAWN_BUILD_PROTOBUF=OFF", "-DTINT_BUILD_IR_BINARY=OFF", "-DTINT_BUILD_TESTS=OFF",
           "-DTINT_BUILD_CMD_TOOLS=OFF", "-DTINT_BUILD_GLSL_WRITER=OFF", "-DTINT_BUILD_GLSL_VALIDATOR=OFF",
           "-DTINT_BUILD_SPV_READER=OFF", "-DTINT_BUILD_SPV_WRITER=OFF", "-DTINT_BUILD_MSL_WRITER=OFF"]


FILES = (DLL, "LICENSE", "LICENSE-abseil", "webgpu.cdef", "webgpu.flags.json")


def in_place():
    stamp = os.path.join(OUT, "DAWN_COMMIT")
    return all(os.path.isfile(os.path.join(OUT, f)) for f in FILES) and os.path.isfile(stamp) and \
        open(stamp, encoding="ascii").read().strip() == DAWN_PIN


def declarations(header):
    """webgpu.h -> (what cffi's cdef reads, {flag constant: value}): no preprocessor lines (nor what sits inside
    #ifdef __cplusplus), no attribute macros, no comments; the flag constants (static const ... = 0x...) taken out"""
    out, flags, skip, cont = [], {}, 0, False
    for line in open(header, encoding="utf-8").read().splitlines():
        s = line.strip()
        if cont:                                               # a #define's continuation lines
            cont = s.endswith("\\")
            continue
        if s.startswith("#"):
            if s.startswith("#ifdef __cplusplus"):
                skip += 1
            elif skip and s.startswith("#endif"):
                skip -= 1
            cont = s.endswith("\\")
            continue
        if skip:
            continue
        m = re.match(r"static const \w+ (\w+) = (0x[0-9A-Fa-f]+)\s*;", s)
        if m:
            flags[m.group(1)] = int(m.group(2), 16)
            continue
        out.append(line)
    cdef = "\n".join(out)
    cdef = re.sub(r"\bWGPU_(EXPORT|FUNCTION_ATTRIBUTE|STRUCTURE_ATTRIBUTE|NULLABLE|ENUM_ATTRIBUTE|OBJECT_ATTRIBUTE)\b", "", cdef)
    cdef = re.sub(r"//[^\n]*", "", cdef)
    cdef = re.sub(r"/\*.*?\*/", "", cdef, flags=re.S)
    return cdef, flags


def vcvars():
    """Visual Studio's x64 environment script, found by its own installer's vswhere"""
    vswhere = os.path.join(os.environ.get("ProgramFiles(x86)", r"C:\Program Files (x86)"), "Microsoft Visual Studio",
                           "Installer", "vswhere.exe")
    path = subprocess.run([vswhere, "-version", "[17.0,18.0)", "-products", "*", "-requires",
                           "Microsoft.VisualStudio.Component.VC.Tools.x86.x64", "-property", "installationPath"],
                          capture_output=True, text=True).stdout.strip().splitlines() if os.path.isfile(vswhere) else []
    bat = os.path.join(path[0], "VC", "Auxiliary", "Build", "vcvars64.bat") if path else ""
    if not os.path.isfile(bat):
        raise SystemExit("no Visual Studio 2022 with the C++ x64 tools (see this script's note)")
    return bat


def run(cmd, cwd, env, bat=None):
    line = subprocess.list2cmdline(cmd)
    print("+ " + line, flush=True)
    if bat:                                                    # inside Visual Studio's environment
        line = 'call "%s" >nul && %s' % (bat, line)
    subprocess.run(line if bat else cmd, cwd=cwd, env=env, check=True, shell=bool(bat))


def cffi_module():
    """cffi's out-of-line module of the declarations (gpu.made_module), made again from webgpu.cdef as it is: the engine
    reads none of them at run time"""
    import sys
    sys.path.insert(0, ROOT)
    from paperdaemon.pipeline.page import gpu
    print("cffi's module of the declarations: %s" % gpu.made_module())


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--force", action="store_true", help="build again even when the DLL in place is DAWN_PIN's")
    args = ap.parse_args()
    if in_place() and not args.force:
        print("Dawn %s already in %s" % (DAWN_PIN[:12], OUT))
        cffi_module()
        return 0
    src = os.environ.get("DAWN_SRC")
    if not src or not os.path.isdir(os.path.join(src, ".git")):
        raise SystemExit("set DAWN_SRC to a Dawn checkout (see this script's note)")
    env = dict(os.environ)
    if os.environ.get("DAWN_TOOLS"):
        env["PATH"] = os.environ["DAWN_TOOLS"] + os.pathsep + env.get("PATH", "")
    head = subprocess.run(["git", "rev-parse", "HEAD"], cwd=src, capture_output=True, text=True).stdout.strip()
    if head != DAWN_PIN:
        run(["git", "fetch", "--depth", "1", "origin", DAWN_PIN], src, env)
        run(["git", "checkout", "--detach", DAWN_PIN], src, env)
    bat = vcvars()
    out = os.path.join(src, "out", "PaperDaemon")
    run(["cmake", "-S", src, "-B", out, "-G", "Ninja"] + OPTIONS, src, env, bat)
    run(["cmake", "--build", out, "--target", "webgpu_dawn"], src, env, bat)
    built = next((os.path.join(d, DLL) for d, _, files in os.walk(out) if DLL in files), None)
    if not built:
        raise SystemExit("the build made no %s" % DLL)
    os.makedirs(OUT, exist_ok=True)
    shutil.copy2(built, os.path.join(OUT, DLL))
    shutil.copy2(os.path.join(src, "LICENSE"), os.path.join(OUT, "LICENSE"))
    shutil.copy2(os.path.join(src, "third_party", "abseil-cpp", "LICENSE"), os.path.join(OUT, "LICENSE-abseil"))   # linked in
    cdef, flags = declarations(os.path.join(out, "gen", "include", "dawn", "webgpu.h"))
    with open(os.path.join(OUT, "webgpu.cdef"), "w", encoding="utf-8", newline="\n") as f:
        f.write(cdef)
    with open(os.path.join(OUT, "webgpu.flags.json"), "w", encoding="utf-8", newline="\n") as f:
        json.dump(flags, f, indent=0, sort_keys=True)
    with open(os.path.join(OUT, "DAWN_COMMIT"), "w", encoding="ascii") as f:
        f.write(DAWN_PIN + "\n")
    print("Dawn %s in %s" % (DAWN_PIN[:12], OUT))
    cffi_module()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
