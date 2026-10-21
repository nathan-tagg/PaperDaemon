"""The page picture cache: the pages grid's pictures and the documents' covers, kept so a book of a thousand pages
opens with its pages grid at once, the way the reMarkable desktop app keeps its thumbnails.

THE WINDOW DRAWS THEM, on the graphics card: a picture the cache does not have is answered "missing" (with the page and
the size wanted), and the window draws that page with the page editor's own renderer, one picture at a time, and hands
it back (put). Nothing is drawn ahead and nothing is drawn here for the grid or the covers: a picture is made only
when it is missing and asked for.

A picture is kept under a key made of what the page IS -- its page id, its template, the page of the document's PDF
or EPUB it shows and that file's size and time -- and NOT its ink: writing on a page leaves its picture as it was until
the page (or, for its cover, the document) is opened again, which forgets it (forget), and the next look draws it
anew. The pictures live in <data>/cache/pages/<renderer stamp>/: a new build starts the cache afresh.

draw() is the engine's own drawing of a page (render.py), for the full-size page pictures it still serves.

The FILLER is one background thread: it works out every book's chapters (remarkable/chapters.cached) once the Mirror
is built, and again when an update from the tablet lands. It draws no pictures.
"""
import hashlib
import json
import os
import re
import shutil
import sys
import threading

from . import paths

THUMB, COVER, PAGE = 360, 480, 2160    # the pages grid's picture (its width), a cover's (its width) and the page view's
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
    # not the ink file: a page written on keeps its picture until it is opened again (forget)
    parts = [pid, str((p.get("redir") or {}).get("value", "")), str((p.get("template") or {}).get("value", ""))]
    for ext in (".pdf", ".epub"):
        src = os.path.join(library.M, doc + ext)
        if os.path.exists(src):
            parts.append(_stat(src))
    if os.path.exists(os.path.join(library.M, doc + ".epub")) and not os.path.exists(os.path.join(library.M, doc + ".pdf")):
        from .remarkable import books                    # a book PaperDaemon lays out: drawn again when its faces change
        parts.append("faces:" + books.mode())
    return hashlib.sha1("|".join(parts).encode()).hexdigest()[:16]


def path_for(doc, page, size, top=False, live=None):
    key = page_key(doc, page, live)
    if key is None:
        return None
    return os.path.join(folder(), doc, "%s-%d%s.webp" % (key, size, "-top" if top else ""))


def cached(doc, page, size, top=True):
    """The kept picture of page `page` at `size` (the grid's or a cover's: the top of the page in a 3:4 card) -> its
    path, or None when it is missing (the window draws it: put)."""
    out = path_for(doc, page, size, top)
    return out if out and os.path.isfile(out) else None


def put(doc, page, size, data, top=True):
    """The window's drawing of page `page` at `size`, as image bytes (WebP or PNG), kept -> its path. Refused when it is
    not a picture of that width."""
    import io
    from PIL import Image
    out = path_for(doc, page, size, top)
    if out is None:
        raise ValueError("there is no page %d" % page)
    with Image.open(io.BytesIO(data)) as im:
        im.load()
        if im.size[0] != size or not 0 < im.size[1] <= 4 * size:
            raise ValueError("a picture %d wide was wanted, not %dx%d" % (size, im.size[0], im.size[1]))
        rgb = im.convert("RGB")
    os.makedirs(os.path.dirname(out), exist_ok=True)
    part = out + ".%d.part" % threading.get_ident()
    if data[:4] == b"RIFF" and data[8:12] == b"WEBP":
        with open(part, "wb") as f:
            f.write(data)
    else:
        rgb.save(part, format="WEBP", quality=90, method=4)
    os.replace(part, out)
    return out


def forget(doc, page):
    """Page `page`'s kept pictures, every size, gone: the page (or its document) was opened, and the next look at its
    picture draws it anew."""
    key = page_key(doc, page)
    d = os.path.join(folder(), doc)
    if key is None or not os.path.isdir(d):
        return 0
    n = 0
    for f in os.listdir(d):
        if f.startswith(key + "-"):
            try:
                os.remove(os.path.join(d, f))
                n += 1
            except OSError:
                pass
    return n


def draw(doc, page, size, top=False, live=None):
    """Page `page` of `doc` as a picture `size` pixels at most on its long side (`top`: the top of the page in a 3:4
    card, `size` wide), from the cache or drawn now -> its path. Raises when it cannot be drawn."""
    from PIL import Image
    from .pipeline.page import render as R
    out = path_for(doc, page, size, top, live)
    if out is None:
        raise ValueError("there is no page %d" % page)
    if os.path.isfile(out):
        return out
    os.makedirs(os.path.dirname(out), exist_ok=True)
    tmp = out[:-5] + ".%d.full.png" % threading.get_ident()
    try:
        R.render(doc, page, tmp, blank_ok=True)               # the one render: the whole page; unwritten pages too
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
    """Work out every book's chapters; again while updates keep landing; then end. (The pictures are the window's.)"""
    try:
        while True:
            with _lock:
                _state["again"] = False
            from .remarkable import chapters, library
            for doc in _documents():                 # seconds each for a big EPUB
                if _state["again"]:
                    break
                try:
                    chapters.cached(library.M, doc)
                except Exception:
                    pass
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
