"""The page picture cache: every page of every document drawn ahead, so a book of a thousand pages opens with its
pages grid at once, the way the reMarkable desktop app keeps its thumbnails.

A picture is kept under a key made of what the page IS -- its page id, its ink file's size and time, the page of the
document's PDF or EPUB it shows and that file's size and time -- so writing on one page of a book redraws that page
only, and a page nobody touched is never drawn twice. The pictures live in <data>/cache/pages/<renderer stamp>/:
a new build or an edited renderer starts the cache afresh.

The FILLER is one background thread. It starts once the Mirror is built, works out every book's chapters
(remarkable/chapters.cached), draws every page that has no picture yet (the documents opened most recently first),
and ends. It starts again only when an update from the tablet lands
(the daemon's pull, or the engine's own), and then draws only what changed. Pictures asked for by the screen are
drawn at once, ahead of it.
"""
import hashlib
import json
import os
import re
import shutil
import sys
import threading

from . import paths

THUMB, PAGE = 360, 2160                 # the pages grid's picture and the page view's, long side in pixels
_STAMP = []
_state = {"thread": None, "again": False, "drawn": 0, "left": 0, "running": False}
_lock = threading.Lock()


def renderer_stamp():
    """What draws the pages: the engine build when frozen, else the newest source file of the renderer; and whether
    the tablet's faces were there (typed text looks different without them)."""
    if _STAMP:
        return _STAMP[0]
    if getattr(sys, "frozen", False):
        stamp = "%x" % int(os.path.getmtime(sys.executable))
    else:
        here = os.path.dirname(os.path.abspath(__file__))
        newest = os.path.getmtime(os.path.abspath(__file__))         # how a page is sized for the screen counts too
        for sub in ("pipeline", "remarkable"):
            for dirpath, _dirs, files in os.walk(os.path.join(here, sub)):
                for f in files:
                    if f.endswith((".py", ".c")):            # the C renderer counts too
                        newest = max(newest, os.path.getmtime(os.path.join(dirpath, f)))
        stamp = "%x" % int(newest)
    from .pipeline.page import typed
    _STAMP.append(stamp + ("-faces" if typed._engine() else ""))
    return _STAMP[0]


def folder():
    """This renderer's cache folder; pages drawn by an older one are removed the first time it is asked for."""
    base = paths.cache_dir("pages")
    out = os.path.join(base, renderer_stamp())
    if not os.path.isdir(out):
        for old in os.listdir(base):
            p = os.path.join(base, old)
            try:
                shutil.rmtree(p) if os.path.isdir(p) else os.remove(p)
            except OSError:
                pass
        os.makedirs(out, exist_ok=True)
    return out


def _stat(path):
    try:
        st = os.stat(path)
        return "%d.%d" % (st.st_size, st.st_mtime_ns)
    except OSError:
        return "-"


def _live(doc):
    from .remarkable.sync import live_pages
    from .remarkable import library
    with open(os.path.join(library.M, doc + ".content"), encoding="utf-8") as f:
        return live_pages(json.load(f))


def page_key(doc, page, live=None):
    """What page `page` (1-based) of `doc` is, as a short string -> None when there is no such page."""
    from .remarkable import library
    live = live if live is not None else _live(doc)
    if not 0 < page <= len(live):
        return None
    p = live[page - 1]
    pid = p.get("id") or ""
    parts = [pid, _stat(os.path.join(library.M, doc, pid + ".rm")), str((p.get("redir") or {}).get("value", "")),
             str((p.get("template") or {}).get("value", ""))]
    for ext in (".pdf", ".epub"):
        src = os.path.join(library.M, doc + ext)
        if os.path.exists(src):
            parts.append(_stat(src))
    if os.path.exists(os.path.join(library.M, doc + ".epub")) and not os.path.exists(os.path.join(library.M, doc + ".pdf")):
        from .remarkable import books                    # a book PaperDaemon lays out: drawn again when its faces change
        parts.append("faces:" + books.mode())
    pics = os.path.join(library.M, doc, pid)            # pictures placed on the page
    if os.path.isdir(pics):
        parts.append(_stat(pics) + ":" + ",".join(sorted(os.listdir(pics))))
    return hashlib.sha1("|".join(parts).encode()).hexdigest()[:16]


def path_for(doc, page, size, top=False, live=None, square=False):
    key = page_key(doc, page, live)
    if key is None:
        return None
    return os.path.join(folder(), doc, "%s-%d%s%s.webp" % (key, size, "-top" if top else "", "-sq" if square else ""))


def draw(doc, page, size, top=False, live=None, square=False):
    """Page `page` of `doc` as a picture `size` pixels at most on its long side (`top`: the top of the page in a 3:4
    card, `size` wide), from the cache or drawn now -> its path. Raises when it cannot be drawn."""
    from PIL import Image
    from .pipeline.page import render as R
    out = path_for(doc, page, size, top, live, square)
    if out is None:
        raise ValueError("there is no page %d" % page)
    if os.path.isfile(out):
        return out
    os.makedirs(os.path.dirname(out), exist_ok=True)
    tmp = out[:-5] + ".%d.full.png" % threading.get_ident()
    try:
        R.render(doc, page, tmp, blank_ok=True, displayed=True, square=square)   # as the tablet shows it; unwritten pages too
        with Image.open(tmp) as im:
            if top:
                w, h = im.size
                im = im.crop((0, 0, w, min(h, int(round(w * 4 / 3)))))
                im = im.resize((size, int(round(im.size[1] * size / w))), Image.LANCZOS) if w > size else im
            else:
                # by WIDTH: a page `size` tall at the tablet's 3:4 is size * 3/4 wide, and a taller page (written past
                # its first screen) keeps that width and runs on down, as the tablet scrolls it
                w, h = im.size
                width = min(w, int(round(size * 3 / 4)))
                if width < w:
                    im = im.resize((width, int(round(h * width / w))), Image.LANCZOS)
            part = out + ".%d.part" % threading.get_ident()
            # WebP at quality 90: a quarter of the PNG's size (a library of 43,546 pages is about 1.1 GB, not 4.8)
            im.convert("RGB").save(part, format="WEBP", quality=90, method=4)
        os.replace(part, out)
    finally:
        try:
            os.remove(tmp)
        except OSError:
            pass
    return out


# ---------------------------------------------------------------- the filler

def status():
    return {"running": _state["running"], "drawn": _state["drawn"], "left": _state["left"]}


def _documents():
    """Every document in the Mirror, the most recently opened first."""
    from .remarkable import library
    docs = [(d, m) for d, m in library.items().items()
            if m.get("type") == "DocumentType" and m.get("parent") != "trash" and not m.get("deleted")]
    docs.sort(key=lambda dm: int(dm[1].get("lastOpened") or 0 if str(dm[1].get("lastOpened") or "0").isdigit() else 0),
              reverse=True)
    return [d for d, _ in docs if re.fullmatch(r"[0-9a-fA-F-]{36}", d)]


def _fill():
    """Draw every page's grid picture that is missing; again while updates keep landing; then end."""
    try:
        while True:
            with _lock:
                _state["again"] = False
            from .remarkable import chapters, library
            for doc in _documents():                 # every book's chapters first: seconds each for a big EPUB
                if _state["again"]:
                    break
                try:
                    chapters.cached(library.M, doc)
                except Exception:
                    pass
            todo = []
            for doc in _documents():
                try:
                    live = _live(doc)
                except (OSError, ValueError):
                    continue
                for n in range(1, len(live) + 1):
                    p = path_for(doc, n, THUMB, True, live)
                    if p and not os.path.isfile(p):
                        todo.append((doc, n))
            _state["left"] = len(todo)
            live_of = {}
            for doc, n in todo:
                if _state["again"]:
                    break                        # the Mirror changed under it: look again from the top
                try:
                    if doc not in live_of:
                        live_of.clear()
                        live_of[doc] = _live(doc)
                    draw(doc, n, THUMB, True, live_of[doc])
                    _state["drawn"] += 1
                except Exception:
                    pass                         # a page that cannot be drawn is drawn when it is asked for
                _state["left"] = max(0, _state["left"] - 1)
            with _lock:
                if not _state["again"]:
                    _state.update(thread=None, running=False, left=0)
                    return
    except Exception:
        with _lock:
            _state.update(thread=None, running=False)


def wake():
    """The Mirror is built, or an update landed: fill what is missing, in the background, then end. A filler already
    running looks again once it is through."""
    from .remarkable import sync
    try:
        if not sync.mirrored():
            return False
    except Exception:
        return False
    with _lock:
        if _state["thread"] is not None:
            _state["again"] = True
            return True
        th = threading.Thread(target=_fill, name="page-thumbnails", daemon=True)
        _state.update(thread=th, running=True)
    th.start()
    return True
