"""The page pictures: the pages grid's pictures and the documents' covers, KEPT, so the library and a book of a
thousand pages show at once, the way the reMarkable desktop app keeps its thumbnails -- through updates of PaperDaemon
too.

Each picture lives in <data>/cache/thumbs/<doc>/ with what it was drawn from beside it (its STAMP: the page's id, its
template, the page of the document's PDF or EPUB it shows and that file, the faces a book PaperDaemon lays out is set
in, and the page's INK, its file's size and time). A look at a picture gets the kept one at once, always; one whose page
has changed since (a page written on, here or on the tablet) is answered as out of date, and the window draws it again,
quietly, and hands it back (put) with the stamp it drew from. One never drawn is answered "missing" (with the page, the
size and the stamp wanted). Nothing is drawn ahead, and nothing here: the window draws them, on the graphics card, with
the page editor's own renderer, one at a time.

draw() is the engine's own drawing of a page (render.py), for the full-size page pictures it still serves; those live
in <data>/cache/pages/<renderer stamp>/, and a new build starts them afresh.

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
_KEPT = []                             # the kept pictures' folder, once the old ones are moved in
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
    """This renderer's folder for the engine's own drawings (draw); pages drawn by an older one are removed the first
    time it is asked for (the window's pictures kept before they were kept through updates moved out of them first)."""
    kept_folder()
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


def _what(doc, p):
    """What the page entry `p` of `doc` is, but its ink: its id, the page of the PDF or EPUB it shows, its template, that
    file's size and time, and the faces of a book PaperDaemon lays out."""
    from .remarkable import library
    pid = p.get("id") or ""
    parts = [pid, str((p.get("redir") or {}).get("value", "")), str((p.get("template") or {}).get("value", ""))]
    for ext in (".pdf", ".epub"):
        src = os.path.join(library.M, doc + ext)
        if os.path.exists(src):
            parts.append(_stat(src))
    if os.path.exists(os.path.join(library.M, doc + ".epub")) and not os.path.exists(os.path.join(library.M, doc + ".pdf")):
        from .remarkable import books                    # a book PaperDaemon lays out: drawn again when its faces change
        parts.append("faces:" + books.mode())
    return parts


def _sha(parts):
    return hashlib.sha1("|".join(parts).encode()).hexdigest()[:16]


def _ink(doc, p):
    """The page's ink file's size and time ("-" while it has none: a page never written on)."""
    from .remarkable import library
    return _stat(os.path.join(library.M, doc, (p.get("id") or "") + ".rm"))


def page_stamp(doc, page, live=None):
    """What page `page` (1-based) of `doc` is drawn from, as a short string -- what it is (_what) and its ink: a picture
    drawn from another stamp is out of date. -> None when there is no such page."""
    live = live if live is not None else _live(doc)
    if not 0 < page <= len(live):
        return None
    p = live[page - 1]
    return _sha(_what(doc, p) + [_ink(doc, p)])


def path_for(doc, page, size, top=False, live=None):
    """Where the engine's own drawing of page `page` at `size` is (draw): named by its stamp, ink and all."""
    key = page_stamp(doc, page, live)
    if key is None:
        return None
    return os.path.join(folder(), doc, "%s-%d%s.webp" % (key, size, "-top" if top else ""))


# ---------------------------------------------------------------- the kept pictures

def kept_folder():
    """Where the window's pictures are kept, through updates: <data>/cache/thumbs."""
    if _KEPT:
        return _KEPT[0]
    with _lock:
        if not _KEPT:
            out = paths.cache_dir("thumbs")
            try:
                _move_in(out)
            except Exception:
                pass                                        # (none moved in: they are drawn again, quietly)
            _KEPT.append(out)
    return _KEPT[0]


def _pic(base, doc, pid, size):
    """A kept picture's file: the grid's for page id `pid`, or the document's one cover (`size` COVER, whichever page it
    shows). Its stamp is beside it, in <the same name>.from."""
    return os.path.join(base, doc, ("cover-%d.webp" % size) if size == COVER else ("%s-%d.webp" % (pid, size)))


def _keep(pic, data, stamp):
    """`data` (WebP bytes) kept as `pic`, drawn from `stamp`: the picture first, then its stamp (a look between the two
    finds it out of date, never a stamp ahead of its picture)."""
    paths.write_atomic(pic, data)
    paths.write_atomic(pic[:-5] + ".from", stamp)


def _move_in(out):
    """ONCE: the pictures kept before they were kept through updates (in a build's own folder, <data>/cache/pages/
    <renderer stamp>/, named by what their page is without its ink) moved in -- a page's as drawn from the page as it
    is now when the page was last written before the picture was made, else (and every cover) as out of date, shown
    and drawn again quietly at the next look."""
    mark = os.path.join(out, "moved-in")
    if os.path.exists(mark):
        return
    base = paths.cache_dir("pages")
    olds = [os.path.join(base, s) for s in os.listdir(base)]
    olds = sorted((o for o in olds if os.path.isdir(o)), key=os.path.getmtime, reverse=True)   # the newest build's first
    for old in olds:
        for doc in os.listdir(old):
            d = os.path.join(old, doc)
            if not re.fullmatch(r"[0-9a-fA-F-]{36}", doc) or not os.path.isdir(d):
                continue
            try:
                live = _live(doc)
            except (OSError, ValueError):
                continue
            covers = []
            for p in live:
                was = _sha(_what(doc, p))
                src = os.path.join(d, "%s-%d-top.webp" % (was, THUMB))
                pic = _pic(out, doc, p.get("id") or "", THUMB)
                if os.path.isfile(src) and not os.path.exists(pic):
                    ink = os.path.join(_mirror(), doc, (p.get("id") or "") + ".rm")
                    current = not os.path.exists(ink) or os.path.getmtime(ink) < os.path.getmtime(src)
                    with open(src, "rb") as f:
                        _keep(pic, f.read(), _sha(_what(doc, p) + [_ink(doc, p)]) if current else "moved")
                src = os.path.join(d, "%s-%d-top.webp" % (was, COVER))
                if os.path.isfile(src):
                    covers.append(src)
            pic = _pic(out, doc, "", COVER)
            if covers and not os.path.exists(pic):
                with open(max(covers, key=os.path.getmtime), "rb") as f:
                    _keep(pic, f.read(), "moved")
    paths.write_atomic(mark, "")


def _mirror():
    from .remarkable import library
    return library.M


def kept(doc, page, size, live=None):
    """The kept picture of page `page` at `size` (the grid's; the document's cover when `size` is COVER, showing page
    `page`; the top of the page in a 3:4 card) -> {"path": its file, None when none was ever drawn, "fresh": drawn from
    the page as it is now, "stamp": the page's stamp now}. Raises when there is no such page."""
    live = live if live is not None else _live(doc)
    stamp = page_stamp(doc, page, live)
    if stamp is None:
        raise ValueError("there is no page %d" % page)
    pic = _pic(kept_folder(), doc, live[page - 1].get("id") or "", size)
    if not os.path.isfile(pic):
        return {"path": None, "fresh": False, "stamp": stamp}
    try:
        with open(pic[:-5] + ".from", encoding="utf-8") as f:
            was = f.read().strip()
    except OSError:
        was = ""
    return {"path": pic, "fresh": was == stamp, "stamp": stamp}


def put(doc, page, size, data, stamp=None):
    """The window's drawing of page `page` at `size`, as image bytes (WebP or PNG), kept, drawn from `stamp` (the
    page's stamp it was asked with; the page's now when not given) -> its path. Refused when it is not a picture of that
    width."""
    import io
    from PIL import Image
    live = _live(doc)
    now = page_stamp(doc, page, live)
    if now is None:
        raise ValueError("there is no page %d" % page)
    stamp = stamp if stamp and re.fullmatch(r"[0-9a-f]{16}", stamp) else now
    out = _pic(kept_folder(), doc, live[page - 1].get("id") or "", size)
    with Image.open(io.BytesIO(data)) as im:
        im.load()
        if im.size[0] != size or not 0 < im.size[1] <= 4 * size:
            raise ValueError("a picture %d wide was wanted, not %dx%d" % (size, im.size[0], im.size[1]))
        rgb = im.convert("RGB")
    if not (data[:4] == b"RIFF" and data[8:12] == b"WEBP"):
        b = io.BytesIO()
        rgb.save(b, format="WEBP", quality=90, method=4)
        data = b.getvalue()
    _keep(out, data, stamp)
    return out


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
