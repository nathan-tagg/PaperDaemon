"""Start PaperDaemon: the engine (its local API) and, unless --headless, the desktop window.

A hidden entry, --run-pipeline <module> [args], runs one of the pipeline's modules as `python -m` would.
The engine starts its children this way in a packaged build, where sys.executable is PaperDaemon itself
rather than a Python interpreter.
"""
import argparse
import os
import sys
import threading


def run_pipeline(argv):
    """Run a pipeline module as __main__, the way `python -m <module> [args]` would."""
    import runpy
    if not argv:
        print("--run-pipeline needs a module")
        return 2
    sys.argv = [argv[0]] + list(argv[1:])
    try:
        runpy.run_module(argv[0], run_name="__main__", alter_sys=True)
    except SystemExit as ex:
        return ex.code if isinstance(ex.code, int) else (0 if ex.code is None else 1)
    except BaseException:
        # the traceback goes to the child's log; a windowed build would otherwise stop on an error dialog
        import traceback
        traceback.print_exc()
        return 1
    return 0


def uninstall_cleanup():
    """What the uninstaller runs before it deletes the program: every credential entry PaperDaemon keeps, by
    its exact name, then the data folder (settings, lineups, harnesses, the library mirror, notepads, job
    records, logs, start-script copies, run files, caches, and the content folder inside it). A content folder
    set elsewhere with PAPERDAEMON_CONTENT is the user's own and stays. Nothing of the reMarkable app, the model
    servers or the model files is touched."""
    import shutil
    from . import paths, vault
    try:
        vault.forget_all()
    except Exception as ex:
        print("PaperDaemon could not remove its saved sign-ins: %s" % ex)
    data = os.path.abspath(os.environ.get("PAPERDAEMON_HOME") or paths.data_dir())
    if not os.path.isdir(data):
        return 0
    # never a drive's root, the user's home or a folder above it: a data folder pointed there is not deleted
    home = os.path.abspath(os.path.expanduser("~"))
    norm = lambda p: os.path.normcase(os.path.normpath(p))
    if os.path.dirname(data) == data or norm(home) == norm(data) or norm(home).startswith(norm(data) + os.sep):
        print("PaperDaemon did not delete its data folder %s: it is a drive, your home folder or above it." % data)
        return 1
    shutil.rmtree(data, ignore_errors=True)
    return 0


def _parent_alive(pid):
    """True while process `pid` runs (Windows: a handle that is not yet signaled)."""
    if sys.platform != "win32":
        try:
            os.kill(pid, 0)
            return True
        except OSError:
            return False
    import ctypes
    k = ctypes.windll.kernel32
    h = k.OpenProcess(0x00100000, False, pid)          # SYNCHRONIZE
    if not h:
        return False
    try:
        return k.WaitForSingleObject(h, 0) == 0x102        # WAIT_TIMEOUT: still running
    finally:
        k.CloseHandle(h)


def false_mirror_engine(port):
    """THE FALSE MIRROR'S ENGINE: the same API over the false mirror's library and state, on 127.0.0.1 only, with the
    cloud switched off. The engine starts it, hands it its pairing token (PAPERDAEMON_PAIRING_TOKEN) and passes the
    False Mirror tab's requests to it; it ends when the engine that started it ends."""
    from . import paths
    lib, state = paths.false_mirror_dir(), paths.false_mirror_state_dir()
    if not os.path.isdir(lib) or not os.path.isdir(state):     # only the Create button makes them
        print("there is no false mirror")
        return 1
    # before anything reads where the mirror is (the modules take it when they are first imported)
    os.environ.update(RM_MIRROR=lib, RM_CACHE=lib, RM_STATE=state, RM_LOCAL_ONLY="1")
    from . import server, thumbs
    server.serve(port, ["127.0.0.1"])
    if not server.wait_up(port):
        print("the false mirror's engine could not start on port %d" % port)
        return 1
    thumbs.wake()
    parent = int(os.environ.get("PAPERDAEMON_PARENT") or 0)
    import time
    while True:
        time.sleep(3)
        if parent and not _parent_alive(parent):
            return 0


def _streams():
    """A windowed build started without output handles has no streams: print() would fail. Output goes
    nowhere, and errors to <data>/logs/engine.err."""
    if sys.stdout is None:
        sys.stdout = open(os.devnull, "w", encoding="utf-8")
    if sys.stderr is None:
        try:
            from . import paths
            err = os.path.join(paths.sub("logs"), "engine.err")
            paths.cap_file(err)
            sys.stderr = open(err, "a", encoding="utf-8", buffering=1)
        except OSError:
            sys.stderr = open(os.devnull, "w", encoding="utf-8")


def main(argv=None):
    argv = list(sys.argv[1:] if argv is None else argv)
    if argv[:1] == ["--uninstall-cleanup"]:
        # before _streams(): it opens an error log inside the data folder, which then could not be deleted
        if sys.stdout is None:
            sys.stdout = open(os.devnull, "w", encoding="utf-8")
        if sys.stderr is None:
            sys.stderr = open(os.devnull, "w", encoding="utf-8")
        return uninstall_cleanup()
    _streams()
    if argv[:1] == ["--run-pipeline"]:
        return run_pipeline(argv[1:])
    if argv[:1] == ["--false-mirror"] and len(argv) > 1:
        return false_mirror_engine(int(argv[1]))
    if argv[:1] == ["--books"]:                    # a book laid out as the tablet lays it out (remarkable/books.py)
        from .remarkable import books
        return books.main(argv[1:])

    from . import __version__, scripts, server, settings
    ap = argparse.ArgumentParser(prog="paperdaemon", description="PaperDaemon %s" % __version__)
    ap.add_argument("--headless", action="store_true", help="run the engine without a window")
    # for the desktop shell that starts the engine: once the API answers, one line on stdout,
    # PAPERDAEMON_READY {"port": ..., "token": ..., "webview": [the window's web view arguments: gpus.window_args]}.
    # The pipe goes only to that parent process.
    ap.add_argument("--announce", action="store_true", help=argparse.SUPPRESS)
    args = ap.parse_args(argv)

    s = settings.load()
    port, hosts = s["server"]["port"], s["server"]["listen"]
    server.serve(port, hosts)
    if not server.wait_up(port):
        print("PaperDaemon could not start its API on port %d -- is something else using it?" % port)
        return 1
    token = server.pairing_token()
    from . import keeper, thumbs
    thumbs.wake()                    # the page pictures the Mirror has no picture for yet; ends when done
    keeper.start()                   # the Mirror kept current for as long as PaperDaemon runs
    server.fm_start()                # the false mirror's engine, when there is a false mirror
    if args.announce:
        import json
        from . import gpus
        server._engine["announced"] = True
        webview = gpus.window_args(want=settings._get_path(s, "render.card") or "")
        print("PAPERDAEMON_READY " + json.dumps({"port": port, "token": token, "webview": webview}), flush=True)
        server.tell_shell("status Idle")
    if args.headless:
        print("PaperDaemon %s -- API on %s, port %d" % (__version__, ", ".join(hosts), port))
        try:
            threading.Event().wait()
        except KeyboardInterrupt:
            pass
        return 0
    from . import desktop
    desktop.run(port, token)
    return 0


def entry():
    """The packaged app's entry: an error ends the process with its traceback in the error log, never with
    a dialog box a supervisor cannot see."""
    try:
        code = main()
    except SystemExit:
        raise
    except BaseException:
        import traceback
        _streams()
        traceback.print_exc()
        code = 1
    sys.exit(code)


if __name__ == "__main__":
    sys.exit(main())
