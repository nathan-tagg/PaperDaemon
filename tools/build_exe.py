"""Build PaperDaemon's engine as a one-folder Windows program with PyInstaller: build/engine/PaperDaemon/PaperDaemon.exe
(a step of tools/build_app.py, which copies it into dist/app/engine: dist/ holds only the app).

    uv run python tools/build_exe.py [--clean]

The app is windowed (no console). It runs the desktop window by default and the engine alone with
--headless, which is how a desktop shell supervises it. In the build, sys.executable is the app itself,
so the engine starts the pipeline's daemon and host as `PaperDaemon.exe --run-pipeline <module>`
(see paperdaemon/__main__.py and loop.pipeline_command).

What goes in, beside the engine's own code:
  paperdaemon/ui               the window's page
  paperdaemon/pipeline         the pipeline's modules (collected) and its small assets (templates, game
                               data, the decomposer's C library)
  paperdaemon/content          the content the app ships with: the curated cast
  paperdaemon/harnesses        the shipped harness files
  tests/benchmark/cases        the benchmark's fixture pages, as paperdaemon/benchmark_cases
Every module the pipeline imports is scanned and named as a hidden import. Stockfish is added beside the
app by tools/build_app.py.

PYINSTALLER_CONFIG_DIR, when set, is where PyInstaller keeps its cache.
"""
import argparse
import ast
import importlib.util
import os
import shutil
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PACKAGE = os.path.join(ROOT, "paperdaemon")
PIPELINE = os.path.join(PACKAGE, "pipeline")
CASES = os.path.join(ROOT, "tests", "benchmark", "cases")
BUILD = os.path.join(ROOT, "build", "pyinstaller")
DIST = os.path.join(ROOT, "build", "engine")
NAME = "PaperDaemon"
SKIP_DIRS = {"__pycache__"}
SKIP_SUFFIXES = (".pyc", ".c", ".h", ".log", ".tmp", ".pdb", ".lib")
# packages whose data files or plugins PyInstaller's hooks may not find from a hidden import alone
COLLECT_ALL = ("rmscene", "vl_convert", "jsonschema", "jsonschema_specifications", "pypdfium2",
               "pypdfium2_raw", "winrt", "webview")
# the decomposer's Python reference runs on these, and the app never loads them (tests/test_light_engine.py):
# left out of the build, with everything that only they pull in
REFERENCE_ONLY = ("cv2", "numba", "llvmlite", "scipy", "skimage", "shapely")


def pipeline_files():
    for folder, dirs, files in os.walk(PIPELINE):
        dirs[:] = [d for d in dirs if d not in SKIP_DIRS]
        for n in files:
            if not n.endswith(SKIP_SUFFIXES):
                yield os.path.join(folder, n)


def local_modules():
    """Names the pipeline's own files and folders provide (imported from the pipeline folder at run time)."""
    names = set()
    for folder, dirs, files in os.walk(PIPELINE):
        dirs[:] = [d for d in dirs if d not in SKIP_DIRS]
        for n in files:
            if n.endswith(".py"):
                names.add(n[:-3])
        for d in dirs:
            names.add(d)
    return names


def pipeline_modules():
    """Every module of the pipeline package, by dotted name (the engine starts them with -m)."""
    out = []
    for folder, dirs, files in os.walk(PIPELINE):
        dirs[:] = [d for d in dirs if d not in SKIP_DIRS and d != "vendor"]
        for n in files:
            if n.endswith(".py"):
                rel = os.path.relpath(os.path.join(folder, n), ROOT)[:-3].replace(os.sep, ".")
                out.append(rel[:-len(".__init__")] if rel.endswith(".__init__") else rel)
    return sorted(out)


def pipeline_imports():
    """Every module the pipeline imports that is not its own, by full dotted name."""
    local, found = local_modules(), set()
    for path in pipeline_files():
        if not path.endswith(".py"):
            continue
        with open(path, encoding="utf-8", errors="replace") as f:
            try:
                tree = ast.parse(f.read(), path)
            except SyntaxError:
                continue
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                found.update(a.name for a in node.names)
            elif isinstance(node, ast.ImportFrom) and node.module and not node.level:
                found.add(node.module)
                for a in node.names:                  # "from scipy import ndimage" imports a submodule
                    found.add(node.module + "." + a.name)
    out = set()
    for name in found:
        if name.split(".")[0] in local or name.split(".")[0] in REFERENCE_ONLY:
            continue
        try:
            if importlib.util.find_spec(name) is not None:
                out.add(name)
        except (ImportError, ValueError, AttributeError):
            continue
    return sorted(out)


def entry_script():
    os.makedirs(BUILD, exist_ok=True)
    path = os.path.join(BUILD, "paperdaemon_entry.py")
    with open(path, "w", encoding="utf-8") as f:
        f.write("from paperdaemon.__main__ import entry\nentry()\n")
    return path


def arguments(clean=False, dist=DIST):
    sep = os.pathsep
    args = [entry_script(), "--name", NAME, "--onedir", "--windowed", "--noconfirm",
            "--distpath", dist, "--workpath", os.path.join(BUILD, "work"), "--specpath", BUILD,
            "--paths", ROOT,
            "--add-data", "%s%spaperdaemon/ui" % (os.path.join(PACKAGE, "ui"), sep),
            "--add-data", "%s%spaperdaemon/content" % (os.path.join(PACKAGE, "content"), sep),
            "--add-data", "%s%spaperdaemon/harnesses/shipped" % (os.path.join(PACKAGE, "harnesses", "shipped"), sep),
            "--add-data", "%s%spaperdaemon/harnesses/examples" % (os.path.join(PACKAGE, "harnesses", "examples"), sep),
            "--add-data", "%s%spaperdaemon/harnesses" % (os.path.join(PACKAGE, "harnesses", "GUIDE-llm.md"), sep),
            "--add-data", "%s%spaperdaemon/harnesses" % (os.path.join(PACKAGE, "harnesses", "GUIDE-image.md"), sep)]
    if clean:
        args.append("--clean")
    for path in pipeline_files():
        rel = os.path.relpath(os.path.dirname(path), PACKAGE).replace(os.sep, "/")
        args += ["--add-data", "%s%spaperdaemon/%s" % (path, sep, rel)]
    if os.path.isdir(CASES):
        args += ["--add-data", "%s%spaperdaemon/benchmark_cases" % (CASES, sep)]
    for name in pipeline_imports():
        args += ["--hidden-import", name]
    for name in pipeline_modules():
        args += ["--hidden-import", name]
    for mod in REFERENCE_ONLY:
        args += ["--exclude-module", mod]
    for pkg in COLLECT_ALL:
        if importlib.util.find_spec(pkg) is not None:
            args += ["--collect-all", pkg]
    # the engine's own modules are found from the entry; these are imported lazily, inside functions
    for mod in ("paperdaemon.studio", "paperdaemon.benchmark", "paperdaemon.benchmark.fixtures",
                "paperdaemon.desktop", "paperdaemon.remarkable.sync", "paperdaemon.remarkable.desktop_token",
                "paperdaemon.reader", "httpx", "uvicorn.logging", "uvicorn.loops.auto", "uvicorn.protocols.http.auto",
                "uvicorn.lifespan.on"):
        args += ["--hidden-import", mod]
    # THE WHOLE STANDARD LIBRARY: a harness in the user's llm folder is Python the app loads at start, and may
    # import anything Python ships, not only what the engine happens to use
    for mod in stdlib_modules():
        spec = importlib.util.find_spec(mod)
        args += ["--collect-submodules" if spec.submodule_search_locations else "--hidden-import", mod]
    return args


# standard library modules a harness can have no use for, or that do not run frozen on Windows
_STDLIB_SKIP = {"antigravity", "this", "idlelib", "tkinter", "turtle", "turtledemo", "test", "lib2to3", "ensurepip",
                "venv", "pydoc_data", "curses", "readline", "tty", "pty", "termios", "fcntl", "grp", "pwd", "resource",
                "syslog", "posix", "_curses", "_curses_panel", "_tkinter", "nis", "spwd", "crypt", "ossaudiodev",
                "msilib", "xxsubtype", "_posixsubprocess", "_posixshmem", "__phello__", "__hello__"}


def stdlib_modules():
    """The standard library's top-level modules that import on this Python (and so in the frozen app)."""
    out = []
    for name in sorted(getattr(sys, "stdlib_module_names", ())):
        if name in _STDLIB_SKIP or name.startswith("_"):
            continue
        try:
            if importlib.util.find_spec(name) is not None:
                out.append(name)
        except (ImportError, ValueError):
            continue
    return out


def free_to_replace(folder):
    """True when `folder` is absent or nothing runs from it. Windows will not rename a folder that holds a running
    program, so a rename there and back tells, before PyInstaller deletes the old build file by file and stops
    half way at the first one that is in use."""
    if not os.path.isdir(folder):
        return True
    probe = folder + ".in-use-check"
    try:
        os.rename(folder, probe)
    except OSError:
        return False
    os.rename(probe, folder)
    return True


def main(argv=None):
    ap = argparse.ArgumentParser(description="Build build/engine/PaperDaemon with PyInstaller.")
    ap.add_argument("--clean", action="store_true", help="empty PyInstaller's cache and the old build first")
    ap.add_argument("--print", action="store_true", help="print the PyInstaller arguments and stop")
    ap.add_argument("--dist", default=DIST, help="the folder the engine is built into (default: build/engine/)")
    args = ap.parse_args(argv)
    pa = arguments(args.clean, os.path.abspath(args.dist))
    if args.print:
        print("\n".join(pa))
        return 0
    dist = os.path.abspath(args.dist)
    if not free_to_replace(os.path.join(dist, NAME)):
        print("%s is in use (a copy of PaperDaemon is running from it): close it, then build again"
              % os.path.join(dist, NAME))
        return 1
    if args.clean:
        shutil.rmtree(os.path.join(dist, NAME), ignore_errors=True)
    import PyInstaller.__main__
    PyInstaller.__main__.run(pa)
    exe = os.path.join(dist, NAME, NAME + ".exe")
    print("built %s" % exe if os.path.isfile(exe) else "the build did not produce %s" % exe)
    return 0 if os.path.isfile(exe) else 1


if __name__ == "__main__":
    sys.exit(main())
