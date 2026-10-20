r"""Where PaperDaemon keeps its files.

- The data folder holds the settings, PaperDaemon's own mirror of the reMarkable library (it never reads or
  writes the desktop app's cache), the job state and the caches: %APPDATA%\PaperDaemon on Windows,
  ~/.local/share/paperdaemon elsewhere, PAPERDAEMON_HOME to override.
- Content is looked for in two places: the user's content folder (PAPERDAEMON_CONTENT, else
  <data>/content), then the content the app ships with
  (paperdaemon/content). A user's copy wins, so a cast or a font can be replaced without touching the app.
  Content is never required: callers ask `installed(...)` and fall back, saying plainly what is missing.
"""
import os
import sys

APP = "PaperDaemon"
BUNDLED = os.path.join(os.path.dirname(os.path.abspath(__file__)), "content")


def data_dir():
    base = os.environ.get("PAPERDAEMON_HOME")
    if not base:
        if sys.platform == "win32":
            base = os.path.join(os.environ.get("APPDATA") or os.path.expanduser("~"), "PaperDaemon")
        else:
            base = os.path.join(os.path.expanduser("~"), ".local", "share", "paperdaemon")
    os.makedirs(base, exist_ok=True)
    return base


LOG_CAP = 2 * 1024 * 1024          # a log's ceiling; past it the most recent half is kept


def cap_file(path, cap=LOG_CAP):
    """Keep an append-only file under `cap` bytes: past it, only its most recent half stays. Logs, journals
    and child output use it; notepads never do."""
    try:
        if os.path.getsize(path) <= cap:
            return
        with open(path, "rb") as f:
            f.seek(-(cap // 2), os.SEEK_END)
            tail = f.read()
        nl = tail.find(b"\n")
        tail = tail[nl + 1:] if 0 <= nl < len(tail) - 1 else tail
        with open(path, "wb") as f:
            f.write(tail)
    except OSError:
        pass


def write_atomic(path, data):
    """Write a file whole or not at all: a temporary file beside it, then a rename. A crash, a full disk or a quit
    mid-write leaves the old file as it was, never half of a page. `data` is bytes, or text (written UTF-8). The
    rename waits out another process's moment with the file (a reader, a virus scanner), up to 2 s."""
    import time
    if isinstance(data, str):
        data = data.encode("utf-8")
    d = os.path.dirname(os.path.abspath(path))
    os.makedirs(d, exist_ok=True)
    import threading
    # its own name for each write: two writes of one file at once (two threads of the engine) never share a part file
    tmp = "%s.%d.%d.part" % (path, os.getpid(), threading.get_ident())
    with open(tmp, "wb") as f:
        f.write(data)
        f.flush()
        os.fsync(f.fileno())
    for i in range(40):
        try:
            os.replace(tmp, path)
            return path
        except PermissionError:
            if i == 39:
                raise
            time.sleep(0.05)


def write_json_atomic(path, obj, indent=4, **kw):
    """`obj` as JSON, written with write_atomic."""
    import json
    return write_atomic(path, json.dumps(obj, indent=indent, **kw))


def sub(*parts):
    """A directory under the data directory, created on first use."""
    p = os.path.join(data_dir(), *parts)
    os.makedirs(p, exist_ok=True)
    return p


def mirror_dir():
    """PaperDaemon's own copy of the library, built straight from the cloud."""
    return sub("mirror")


def safety_dir():
    """The cloud client's record of what it pulled, its lock, and the pages set aside in a conflict."""
    return sub("cloud-safety")


def settings_file():
    return os.path.join(data_dir(), "settings.json")


def state_dir():
    """Where the pipeline keeps its working state: RM_STATE (set by the engine for its children), else the
    data folder."""
    return os.environ.get("RM_STATE") or data_dir()


# THE FALSE MIRROR: a library kept only on this computer, beside the Mirror (a sibling folder, never inside it), with
# its own job state beside it. The daemon answers it as it answers the tablet; nothing of it reaches the cloud.
def false_mirror_dir():
    """The false mirror's library (not created here: it exists only once the user creates it)."""
    return os.path.join(data_dir(), "false-mirror")


def false_mirror_state_dir():
    """The false mirror's job state: its ledger, queue, notes and logs."""
    return os.path.join(data_dir(), "false-mirror-state")


def false_mirror_exists():
    return os.path.isdir(false_mirror_dir())


def local_only():
    """True in a process working the false mirror: nothing is pulled from or pushed to the cloud."""
    return os.environ.get("RM_LOCAL_ONLY") == "1"


class one_job(object):
    """ONE JOB AT A TIME, ACROSS EVERY MIRROR: a host holds this lock (a file in the data folder, shared by the
    Mirror's host and the false mirror's) while it works a job, so two jobs never load the model at once. The system
    lets go of it when the process ends, however it ends."""

    def __init__(self):
        self.f = None

    def __enter__(self):
        import time
        path = os.path.join(sub("run"), "one-job.lock")
        self.f = open(path, "a+b")
        while True:
            try:
                if sys.platform == "win32":
                    import msvcrt
                    self.f.seek(0)
                    msvcrt.locking(self.f.fileno(), msvcrt.LK_NBLCK, 1)
                else:
                    import fcntl
                    fcntl.flock(self.f.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
                return self
            except OSError:
                time.sleep(1)

    def __exit__(self, *exc):
        try:
            if sys.platform == "win32":
                import msvcrt
                self.f.seek(0)
                msvcrt.locking(self.f.fileno(), msvcrt.LK_UNLCK, 1)
        except OSError:
            pass
        self.f.close()
        return False


def cache_dir(*parts):
    """A cache folder under the data folder, created on first use."""
    return sub("cache", *parts)


# ---------------------------------------------------------------- content

def content_dir():
    """The user's content folder (it may not exist)."""
    return os.environ.get("PAPERDAEMON_CONTENT") or os.path.join(data_dir(), "content")


def content_path(*parts):
    """A file or folder of the content: the user's copy when there is one, else the app's own, else the
    path it would have in the user's content folder."""
    mine = os.path.join(content_dir(), *parts)
    if os.path.exists(mine):
        return mine
    shipped = os.path.join(BUNDLED, *parts)
    return shipped if os.path.exists(shipped) else mine


def installed(*parts):
    """True when this file or folder of the content exists (and a folder is not empty)."""
    p = content_path(*parts)
    if os.path.isdir(p):
        try:
            return bool(os.listdir(p))
        except OSError:
            return False
    return os.path.exists(p)


def not_installed(what, *parts):
    """The sentence a caller gives when content is missing."""
    return "%s is not installed (expected in %s; set PAPERDAEMON_CONTENT to use another folder)" % (
        what, os.path.join(content_dir(), *parts))


def fonts_dir():
    return content_path("rm-fonts")


def font_file(name):
    """The path of an installed face (`name` with or without .ttf), or None."""
    if not name.lower().endswith((".ttf", ".otf")):
        name += ".ttf"
    p = os.path.join(fonts_dir(), name)
    return p if os.path.isfile(p) else None


def pil_font(name, size):
    """A PIL font: the installed face `name` at `size`, else PIL's bundled font at that size."""
    from PIL import ImageFont
    p = font_file(name)
    if p:
        try:
            return ImageFont.truetype(p, size)
        except OSError:
            pass
    return ImageFont.load_default(size)


def games_installed():
    """True when the character profiles the games play are installed."""
    return installed("games", "characters")


# ---------------------------------------------------------------- what the pipeline reads

_RUN = {}


def run_file():
    """The host's run file (RM_RUN, written by the engine: the lineup's harness values, its resolved features
    and the settings the host reads), or {} in a process the engine did not start that way."""
    path = os.environ.get("RM_RUN")
    if not path:
        return {}
    if _RUN.get("path") != path:
        import json
        try:
            with open(path, encoding="utf-8") as f:
                _RUN.update(path=path, content=json.load(f) or {})
        except (OSError, ValueError):
            _RUN.update(path=path, content={})
    return _RUN["content"]


def _setting(key):
    """A setting the pipeline reads: from the run file in the host, else from the settings file."""
    run = run_file()
    if run:
        return (run.get("settings") or {}).get(key)
    import json
    try:
        with open(settings_file(), encoding="utf-8") as f:
            return (json.load(f) or {}).get(key)
    except (OSError, ValueError):
        return None


def prefs():
    """The user's preferences: {"temperature": "fahrenheit" | "celsius", "clock": "12" | "24", "week_start":
    "sunday" | "monday" | "saturday"}; until they choose, what the computer's region settings say."""
    from . import region
    p, d = _setting("prefs") or {}, region.defaults()
    return {k: p.get(k) or d[k] for k in ("temperature", "clock", "week_start")}


def home():
    """The user's home place, for weather, sunrise and holidays: (name, latitude, longitude, holiday
    region), from the location setting; with none set, no place and the computer's own country's holidays."""
    loc = _setting("location") or {}
    name, lat, lon, region = loc.get("name") or "", loc.get("lat"), loc.get("lon"), loc.get("holidays")
    try:
        lat, lon = (float(lat), float(lon)) if lat not in (None, "") and lon not in (None, "") else (None, None)
    except (TypeError, ValueError):
        lat, lon = None, None
    if not region:
        from . import region as _region
        region = _region.defaults()["country"]
    return str(name or ""), lat, lon, str(region)


# ---------------------------------------------------------------- the chess engine

AVX2_NAME, PLAIN_NAME = "stockfish-avx2.exe", "stockfish.exe"


def _has_avx2():
    try:
        import ctypes
        return bool(ctypes.windll.kernel32.IsProcessorFeaturePresent(40))   # PF_AVX2_INSTRUCTIONS_AVAILABLE
    except (AttributeError, OSError):
        return False


def _pick_stockfish(folder):
    """The build to run from a folder: the AVX2 build when the processor has AVX2 and the folder has one,
    else the plain one; the choice is kept in the cache, so it is made once."""
    avx2, plain = os.path.join(folder, AVX2_NAME), os.path.join(folder, PLAIN_NAME)
    if not os.path.isfile(avx2):
        return plain if os.path.isfile(plain) else None
    if not os.path.isfile(plain):
        return avx2
    choice = os.path.join(cache_dir(), "stockfish-build.txt")
    try:
        with open(choice, encoding="utf-8") as f:
            name = f.read().strip()
        if name in (AVX2_NAME, PLAIN_NAME):
            return os.path.join(folder, name)
    except OSError:
        pass
    name = AVX2_NAME if _has_avx2() else PLAIN_NAME
    try:
        with open(choice, "w", encoding="utf-8") as f:
            f.write(name)
    except OSError:
        pass
    return os.path.join(folder, name)


def stockfish():
    """The chess engine to run: PAPERDAEMON_STOCKFISH, the content folder's engines/stockfish, the copy the
    app ships beside itself (stockfish/), then `stockfish` on the executable search path; None without one."""
    import shutil
    explicit = os.environ.get("PAPERDAEMON_STOCKFISH")
    if explicit and os.path.isfile(explicit):
        return explicit
    folders = [content_path("engines", "stockfish")]
    if getattr(sys, "frozen", False):
        folders.append(os.path.join(os.path.dirname(sys.executable), "stockfish"))
    for folder in folders:
        if os.path.isdir(folder):
            found = _pick_stockfish(folder)
            if found:
                return found
            for name in sorted(os.listdir(folder)):
                if name.lower().startswith("stockfish") and name.lower().endswith(".exe"):
                    return os.path.join(folder, name)
    return shutil.which("stockfish")
def geo_dir():
    """Cache for geocoding, weather and history lookups."""
    return os.path.join(data_dir(), "geo")


def generated_fonts_dir():
    """Where the stroke-lettering font file is built."""
    return os.path.join(data_dir(), "fonts")
