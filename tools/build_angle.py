r"""Build ANGLE -- OpenGL ES 3 on Direct3D 11 -- for the engine's pictures on the graphics card (pipeline/page/gpu.py):
libEGL.dll and libGLESv2.dll, with ANGLE's LICENSE (BSD-3-Clause), into paperdaemon/pipeline/page/angle/, which the app
carries with the rest of the pipeline's files. The page editor draws through WebView2's own ANGLE; this is the engine's
copy of the same route, so both run ui/shaders.js as written, on the same Direct3D 11.

    uv run python tools/build_angle.py          -> the DLLs in place for ANGLE_PIN (nothing done when they already are)
    uv run python tools/build_angle.py --force  -> built again

A build needs, once: Visual Studio 2022 (Build Tools will do) with the C++ x64 tools and ATL, the Windows SDK the
checkout's build/vs_toolchain.py names (SDK_VERSION), depot_tools on PATH, and an ANGLE checkout (`fetch --no-history
angle`) named by ANGLE_SRC. DEPOT_TOOLS_WIN_TOOLCHAIN=0 is set here; vs2022_install is set from Visual Studio's own
installer when it is not set already (Build Tools sits under Program Files (x86), where the checkout does not look).
Only Direct3D 11 is built (no Vulkan, desktop GL or tests); the DLLs need nothing but Windows' own libraries and its
d3dcompiler_47.dll.
"""
import argparse
import os
import shutil
import subprocess
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT = os.path.join(ROOT, "paperdaemon", "pipeline", "page", "angle")
ANGLE_PIN = "5c5b6f5b1d01bd09beb5446bc5239163bb1da10f"            # ANGLE 2.1.1, this commit
FILES = ("libEGL.dll", "libGLESv2.dll")
ARGS = """# PaperDaemon's ANGLE (tools/build_angle.py): OpenGL ES 3 on Direct3D 11 only, a release build
is_debug = false
target_cpu = "x64"
is_component_build = false
symbol_level = 0
dcheck_always_on = false
angle_assert_always_on = false
angle_build_all = false
angle_build_tests = false
angle_has_frame_capture = false
angle_enable_d3d11 = true
angle_enable_gl = false
angle_enable_vulkan = false
angle_enable_null = false
angle_enable_wgpu = false
"""


def in_place():
    stamp = os.path.join(OUT, "ANGLE_COMMIT")
    return all(os.path.isfile(os.path.join(OUT, f)) for f in FILES + ("LICENSE",)) and os.path.isfile(stamp) and \
        open(stamp, encoding="ascii").read().strip() == ANGLE_PIN


def run(cmd, cwd, env):
    print("+ " + " ".join(cmd), flush=True)
    subprocess.run(cmd, cwd=cwd, env=env, check=True, shell=(os.name == "nt"))


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--force", action="store_true", help="build again even when the DLLs in place are ANGLE_PIN's")
    args = ap.parse_args()
    if in_place() and not args.force:
        print("ANGLE %s already in %s" % (ANGLE_PIN[:12], OUT))
        return 0
    src = os.environ.get("ANGLE_SRC")
    if not src or not os.path.isdir(os.path.join(src, ".git")):
        raise SystemExit("set ANGLE_SRC to an ANGLE checkout (`fetch --no-history angle`; see this script's note)")
    env = dict(os.environ, DEPOT_TOOLS_WIN_TOOLCHAIN="0")
    if not env.get("vs2022_install"):
        vswhere = os.path.join(os.environ.get("ProgramFiles(x86)", r"C:\Program Files (x86)"), "Microsoft Visual Studio",
                               "Installer", "vswhere.exe")
        if os.path.isfile(vswhere):
            path = subprocess.run([vswhere, "-version", "[17.0,18.0)", "-products", "*", "-requires",
                                   "Microsoft.VisualStudio.Component.VC.Tools.x86.x64", "-property", "installationPath"],
                                  capture_output=True, text=True).stdout.strip().splitlines()
            if path:
                env["vs2022_install"] = path[0]
    head = subprocess.run(["git", "rev-parse", "HEAD"], cwd=src, capture_output=True, text=True).stdout.strip()
    if head != ANGLE_PIN:                                     # the checkout to the pin, and its dependencies with it
        run(["git", "fetch", "--depth", "1", "origin", ANGLE_PIN], src, env)
        run(["git", "checkout", "--detach", ANGLE_PIN], src, env)
        run(["gclient", "sync", "--no-history", "-D"], src, env)
    out = os.path.join(src, "out", "PaperDaemon")
    os.makedirs(out, exist_ok=True)
    with open(os.path.join(out, "args.gn"), "w", encoding="ascii") as f:
        f.write(ARGS)
    run(["gn", "gen", out.replace("\\", "/")], src, env)
    run(["autoninja", "-C", out.replace("\\", "/")] + [f[:-4] for f in FILES], src, env)
    os.makedirs(OUT, exist_ok=True)
    for f in FILES:
        shutil.copy2(os.path.join(out, f), os.path.join(OUT, f))
    shutil.copy2(os.path.join(src, "LICENSE"), os.path.join(OUT, "LICENSE"))
    with open(os.path.join(OUT, "ANGLE_COMMIT"), "w", encoding="ascii") as f:
        f.write(ANGLE_PIN + "\n")
    print("ANGLE %s built into %s" % (ANGLE_PIN[:12], OUT))
    return 0


if __name__ == "__main__":
    sys.exit(main())
