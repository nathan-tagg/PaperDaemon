"""The false mirror's own edits: what the user makes and changes in it from the window -- notebooks, folders and pages,
imports and exports, moves and deletes, tags, and a page's contents from the page editor.

ONLY IN THE FALSE MIRROR'S ENGINE (paths.local_only()): every function here refuses anywhere else, so nothing of the
tablet's library is ever written by them. What they write is what the tablet writes -- the same .metadata, .content,
.pagedata and .rm files -- so a page made here is a page the tablet could open, and the daemon reads it unchanged.

A PAGE, FOR THE EDITOR (scene_of / write_scene): its frame, its layers bottom to top with their strokes as the file
stores them, its typed text as paragraphs of runs, and whether the text and the template are shown. Writing builds
the page anew in the tablet's own structure (the root node, each layer's node and its place under the root, the
strokes under their layer, the root text block), keeping the page's header blocks."""
import io
import json
import os
import re
import threading
import time
import uuid

from rmscene import read_blocks, write_blocks
from rmscene import scene_items as si
from rmscene import scene_stream as ss
from rmscene.crdt_sequence import CrdtSequence, CrdtSequenceItem
from rmscene.tagged_block_common import CrdtId, LwwValue

from .. import paths
from . import library as F

M = F.M

# paragraph style codes as the file stores them, and the editor's names for them (D6 of add-page-editor: Title is
# HEADING, Section BOLD, Body PLAIN; Header is written as BASIC until a page from the tablet says otherwise)
STYLE_OF = {2: ("title", None), 0: ("header", None), 3: ("section", None), 1: ("body", None), 4: ("body", "bullet"),
            5: ("body", "bullet2"), 6: ("body", "check"), 7: ("body", "checked"), 10: ("body", "number")}
CODE_OF = {("title", None): 2, ("header", None): 0, ("section", None): 3, ("body", None): 1, ("body", "bullet"): 4,
           ("body", "bullet2"): 5, ("body", "check"): 6, ("body", "checked"): 7, ("body", "number"): 10}


class NotHere(PermissionError):
    """An edit asked of the tablet's mirror: these are the false mirror's alone."""


def _guard():
    if not paths.local_only():
        raise NotHere("this is done only in the False Mirror")


def _now():
    return int(time.time() * 1000)


def _pipeline():
    from paperdaemon.pipeline import TEMPLATES
    return os.path.dirname(TEMPLATES)


def _read(path):
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def _content(doc):
    return _read(os.path.join(M, doc + ".content"))


def _save_content(doc, c):
    paths.write_json_atomic(os.path.join(M, doc + ".content"), c)


def sync_request():
    """The false mirror syncs: the daemon looks at its pages' ink as it is now (ledger.py, _held_state)."""
    from paperdaemon import ledger
    p = ledger.sync_request_path()
    os.makedirs(os.path.dirname(p), exist_ok=True)
    with open(p, "w", encoding="utf-8") as f:
        f.write(str(_now()))


def _touch(u):
    """The item's modified time is now (its cover and the library's order follow)."""
    p = os.path.join(M, u + ".metadata")
    m = _read(p)
    m["lastModified"] = str(_now())
    paths.write_json_atomic(p, m)


def _live(c):
    if not c.get("cPages") and isinstance(c.get("pages"), list):  # an older document's layout: its page ids, in order
        return [{"id": p} for p in c["pages"] if isinstance(p, str)]
    return sorted((p for p in (c.get("cPages") or {}).get("pages") or [] if "deleted" not in p),
                  key=lambda p: p["idx"]["value"])


def page_id(doc, page_no):
    live = _live(_content(doc))
    if not 1 <= page_no <= len(live):
        raise ValueError("there is no page %d" % page_no)
    return live[page_no - 1]["id"]


# ---------------------------------------------------------------- notebooks, folders, pages

def new_notebook(name, parent="", template="Blank", cover="last", tags=()):
    """A notebook with one page, in the Paper Pro's frame, as the tablet makes one: its cover the page last visited
    (`cover` "last") or its first page ("first"), its page's `template` (the tablet's file name, "P Grid medium";
    "Blank" for none). -> its id."""
    _guard()
    from paperdaemon import studio
    doc = str(uuid.uuid4())
    template = str(template or "Blank").strip()[:120] or "Blank"
    studio._new_notebook(M, _pipeline(), doc, (name or "Notebook").strip() or "Notebook", parent, _now())
    blank = studio._blank_page_bytes(_pipeline())          # the bundled Paper Pro page: no user library to copy
    pid = str(uuid.uuid4())
    paths.write_atomic(os.path.join(M, doc, pid + ".rm"), blank)
    c = _content(doc)
    c["cPages"]["pages"] = [{"id": pid, "idx": {"timestamp": "1:2", "value": "ba"}, "modifed": str(_now()),
                             "template": {"timestamp": "1:1", "value": template}}]
    c["cPages"]["lastOpened"] = {"timestamp": "1:1", "value": pid}
    # the tablet's cover setting: -1 the page last visited, 0 the first page
    c.update(pageCount=1, sizeInBytes=str(len(blank)), coverPageNumber=0 if cover == "first" else -1)
    _save_content(doc, c)
    paths.write_atomic(os.path.join(M, doc + ".pagedata"), template + "\n")
    if tags:
        set_tags(doc, tags)                          # the notebook's own tags, as New notebook was given them
    return doc


def quick_sheets():
    """QUICK SHEETS, as the tablet's button opens them: the library's one Quick sheets (the document of that name at the
    root; made when there is none) on a new page at its end. -> (its id, the new page's number)."""
    from paperdaemon import studio
    _guard()
    docs, how = studio.inbox_docs(M, None)
    if how != "quick sheets":
        return new_notebook(studio.QUICK_SHEETS, ""), 1
    return docs[0], new_page(docs[0])


def new_folder(name, parent=""):
    _guard()
    u = str(uuid.uuid4())
    now = str(_now())
    paths.write_json_atomic(os.path.join(M, u + ".metadata"), {
        "createdTime": now, "lastModified": now, "new": False, "parent": parent, "pinned": False, "source": "",
        "type": "CollectionType", "visibleName": (name or "Folder").strip() or "Folder"})
    paths.write_json_atomic(os.path.join(M, u + ".content"), {"tags": []})
    return u


def new_page(doc, after=None):
    """A blank page after page `after` (1-based; the last page when None), in the notebook's own frame. -> its
    1-based number."""
    _guard()
    live = _live(_content(doc))
    if not live:
        raise ValueError("the notebook has no page to follow")
    at = len(live) if after is None else max(1, min(len(live), int(after)))
    F.insert_pages(doc, live[at - 1]["id"], 1)
    _touch(doc)
    return at + 1


def import_pdf(name, data, parent=""):
    """A PDF, as the tablet files one, in folder `parent`. -> its id."""
    _guard()
    if not data.startswith(b"%PDF"):
        raise ValueError("that is not a PDF")
    import tempfile
    from paperdaemon.pipeline.page import pdf as PDF
    fd, tmp = tempfile.mkstemp(suffix=".pdf")
    try:
        with os.fdopen(fd, "wb") as f:
            f.write(data)
        doc, _pages = PDF.stage((name or "Document").strip() or "Document", tmp)
    finally:
        try:
            os.remove(tmp)
        except OSError:
            pass
    if parent:
        F.move(doc, parent)
    return doc


def import_file(name, data, parent=""):
    """A PDF or an EPUB, told apart by its bytes. -> its id."""
    _guard()
    if data.startswith(b"%PDF"):
        return import_pdf(name, data, parent)
    if data.startswith(b"PK"):
        return import_epub(name, data, parent)
    raise ValueError("only PDF and EPUB files can be imported")


# A BOOK, AS THE DESKTOP APP FILES ONE: the .epub with its .content and .metadata, and no PDF -- PaperDaemon reads the
# book itself (books.py), laid out as the tablet lays it out, with the tablet's reading settings. The page list comes
# from that layout: one page per page of the book, each pointing at its page (redir), like a converted book.
def import_epub(name, data, parent=""):
    _guard()
    import zipfile
    from . import books
    try:
        with zipfile.ZipFile(io.BytesIO(data)) as z:
            if z.read("mimetype").strip() != b"application/epub+zip" or not books.spine(z):
                raise ValueError("that is not an EPUB")
    except (KeyError, zipfile.BadZipFile, AttributeError):
        raise ValueError("that is not an EPUB")
    doc = str(uuid.uuid4())
    epub = os.path.join(M, doc + ".epub")
    paths.write_atomic(epub, data)
    try:
        settings = books.settings_of(None)
        _pdf, index = books.lay_out(epub, settings)
    except Exception:
        os.remove(epub)
        raise ValueError("the book could not be laid out")
    n = int(index["pages"])
    pages, idxv = [], "ba"
    for i in range(n):
        pages.append({"id": str(uuid.uuid4()), "idx": {"timestamp": "1:2", "value": idxv},
                      "redir": {"timestamp": "1:2", "value": i}, "template": {"timestamp": "1:2", "value": "Blank"}})
        idxv = F.next_idx(idxv)
    title = (name or "Book").strip() or "Book"
    content = {
        "cPages": {"lastOpened": {"timestamp": "1:1", "value": pages[0]["id"]},
                   "original": {"timestamp": "1:1", "value": n}, "pages": pages},
        "coverPageNumber": 0, "customZoomCenterX": 0, "customZoomCenterY": books.H // 2,
        "customZoomOrientation": "portrait", "customZoomPageHeight": books.H, "customZoomPageWidth": books.W,
        "customZoomScale": 1, "documentMetadata": {"title": title}, "extraMetadata": {},
        "fileType": "epub", "fontName": "", "formatVersion": 2, "lineHeight": settings["line_height"],
        "margins": settings["margins"], "orientation": "portrait", "pageCount": n, "pageTags": [],
        "sizeInBytes": str(len(data)), "tags": [], "textAlignment": "justify", "textScale": settings["scale"],
        "zoomMode": "bestFit"}
    now = str(_now())
    metadata = {"createdTime": now, "lastModified": now, "lastOpened": "0", "lastOpenedPage": 0, "new": False,
                "parent": "", "pinned": False, "source": "", "type": "DocumentType", "visibleName": title}
    paths.write_json_atomic(os.path.join(M, doc + ".content"), content)
    paths.write_json_atomic(os.path.join(M, doc + ".metadata"), metadata)
    paths.write_atomic(os.path.join(M, doc + ".pagedata"), "Blank\n" * n)
    if parent:
        F.move(doc, parent)
    return doc


def export_pdf(doc):
    """The document as a PDF, every page drawn by PaperDaemon's renderer, in order. -> bytes."""
    _guard()
    from PIL import Image
    from paperdaemon import thumbs
    pics = []
    for n in range(1, len(_live(_content(doc))) + 1):
        im = Image.open(thumbs.draw(doc, n, 2160))
        pics.append(im.convert("RGB"))
    if not pics:
        raise ValueError("the document has no pages")
    buf = io.BytesIO()
    pics[0].save(buf, format="PDF", save_all=True, append_images=pics[1:], resolution=229.0)
    return buf.getvalue()


def duplicate(u):
    """A copy of a document beside it, as the tablet duplicates one: every file of it, under a new id, its name with
    " copy" after it. -> the copy's id."""
    _guard()
    import shutil
    md = _read(os.path.join(M, u + ".metadata"))
    if md.get("type") != "DocumentType":
        raise ValueError("only a document is duplicated")
    new = str(uuid.uuid4())
    for f in os.listdir(M):
        if f.startswith(u + ".") and not f.endswith(".metadata"):
            shutil.copyfile(os.path.join(M, f), os.path.join(M, new + f[len(u):]))
    if os.path.isdir(os.path.join(M, u)):
        shutil.copytree(os.path.join(M, u), os.path.join(M, new))
    now = str(_now())
    md.update(visibleName=(md.get("visibleName") or "Notebook") + " copy", createdTime=now, lastModified=now,
              lastOpened="", lastOpenedPage=0)
    paths.write_json_atomic(os.path.join(M, new + ".metadata"), md)
    return new


# ---------------------------------------------------------------- several pages at once (the page grid's selection)
# AS THE TABLET'S PAGE OVERVIEW DOES: the pages chosen are deleted (for good: a page skips the trash), duplicated
# (each copy right after its page), moved (before or after a page of this notebook or another, or to the end) or
# tagged. A notebook keeps at least one page. Pages are ordered by their keys alone (library.key_between): no other
# page's key, id or file changes.

def _chosen(doc, page_nos):
    c = _content(doc)
    live = _live(c)
    nos = sorted(set(int(n) for n in page_nos or []))
    if not nos or nos[0] < 1 or nos[-1] > len(live):
        raise ValueError("choose pages of the notebook")
    return c, live, [live[n - 1] for n in nos]


def _notebook(doc):
    if _content(doc).get("fileType", "notebook") != "notebook":
        raise ValueError("pages are moved and copied between notebooks only")


def _page_files(doc, pid):
    """A page's files: its ink, and the folder its pictures are kept in."""
    return os.path.join(M, doc, pid + ".rm"), os.path.join(M, doc, pid)


def _copy_page(src_doc, src_pid, dst_doc, dst_pid):
    import shutil
    rm, pics = _page_files(src_doc, src_pid)
    rm2, pics2 = _page_files(dst_doc, dst_pid)
    os.makedirs(os.path.dirname(rm2), exist_ok=True)
    if os.path.exists(rm):
        shutil.copyfile(rm, rm2)
    if os.path.isdir(pics):
        shutil.copytree(pics, pics2, dirs_exist_ok=True)


def _drop_page_files(doc, pid):
    import shutil
    rm, pics = _page_files(doc, pid)
    try:
        os.remove(rm)
    except OSError:
        pass
    shutil.rmtree(pics, ignore_errors=True)


def _pages_done(doc, c):
    """The notebook's page count and its older list of templates brought up to date, saved, and touched."""
    live = _live(c)
    c["pageCount"] = len(live)
    _save_content(doc, c)
    pd = os.path.join(M, doc + ".pagedata")
    if os.path.exists(pd):
        paths.write_atomic(pd, "".join(((p.get("template") or {}).get("value") or "Blank") + "\n" for p in live))
    _touch(doc)


def _keys_at(live, moving, at, where, n):
    """`n` keys for pages put before or after page `at` (1-based in `live`; None: after the last), the
    pages being moved left out of the reckoning."""
    rest = [p for p in live if p["id"] not in moving]
    if at is None:
        lo, hi = (rest[-1]["idx"]["value"] if rest else ""), None
    else:
        anchor = live[int(at) - 1]
        if anchor["id"] in moving:
            raise ValueError("choose a page that is not one of those being moved")
        i = next(k for k, p in enumerate(rest) if p["id"] == anchor["id"])
        if where == "before":
            lo, hi = (rest[i - 1]["idx"]["value"] if i else ""), anchor["idx"]["value"]
        else:
            lo, hi = anchor["idx"]["value"], (rest[i + 1]["idx"]["value"] if i + 1 < len(rest) else None)
    return F.keys_between(lo, hi, n)


def delete_pages(doc, page_nos):
    """-> how many went."""
    _guard()
    c, live, chosen = _chosen(doc, page_nos)
    if len(chosen) >= len(live):
        raise ValueError("a notebook keeps at least one page")
    ids = {p["id"] for p in chosen}
    for p in c["cPages"]["pages"]:
        if p["id"] in ids:
            p["deleted"] = {"timestamp": "1:2", "value": 0}
    c["pageTags"] = [t for t in c.get("pageTags") or [] if t.get("pageId") not in ids]
    _pages_done(doc, c)
    for pid in ids:
        _drop_page_files(doc, pid)
    return len(ids)


def duplicate_pages(doc, page_nos):
    """Each page chosen copied right after itself, its ink, pictures, template and tags with it. -> how many."""
    _guard()
    _notebook(doc)
    c, _live0, chosen = _chosen(doc, page_nos)
    now = str(_now())
    for p in chosen:
        live = _live(c)
        i = next(k for k, q in enumerate(live) if q["id"] == p["id"])
        key = F.key_between(p["idx"]["value"], live[i + 1]["idx"]["value"] if i + 1 < len(live) else None)
        new = str(uuid.uuid4())
        _copy_page(doc, p["id"], doc, new)
        entry = {"id": new, "idx": {"timestamp": p["idx"]["timestamp"], "value": key}, "modifed": now}
        if p.get("template"):
            entry["template"] = dict(p["template"])
        c["cPages"]["pages"].append(entry)
        c["pageTags"] = (c.get("pageTags") or []) + [dict(t, pageId=new) for t in c.get("pageTags") or []
                                                      if t.get("pageId") == p["id"]]
    _pages_done(doc, c)
    return len(chosen)


def move_pages(doc, page_nos, to=None, at=None, where="after"):
    """The pages chosen, in their order, put before or after page `at` of notebook `to` (this one when None; `at`
    None: at its end). -> how many."""
    _guard()
    where = "before" if where == "before" else "after"
    to = to or doc
    c, live, chosen = _chosen(doc, page_nos)
    ids = [p["id"] for p in chosen]
    if to == doc:
        for p, key in zip(chosen, _keys_at(live, set(ids), at, where, len(ids))):
            p["idx"] = {"timestamp": p["idx"]["timestamp"], "value": key}
        _pages_done(doc, c)
        return len(chosen)
    _notebook(doc)
    _notebook(to)
    if len(chosen) >= len(live):
        raise ValueError("a notebook keeps at least one page")
    dc = _content(to)
    dlive = _live(dc)
    if at is not None and not 1 <= int(at) <= len(dlive):
        raise ValueError("there is no page %s there" % at)
    now = str(_now())
    for p, key in zip(chosen, _keys_at(dlive, set(), at, where, len(ids))):
        _copy_page(doc, p["id"], to, p["id"])
        entry = {"id": p["id"], "idx": {"timestamp": p["idx"]["timestamp"], "value": key}, "modifed": now}
        if p.get("template"):
            entry["template"] = dict(p["template"])
        dc["cPages"]["pages"].append(entry)
        dc["pageTags"] = (dc.get("pageTags") or []) + [t for t in c.get("pageTags") or [] if t.get("pageId") == p["id"]]
    _pages_done(to, dc)
    for p in c["cPages"]["pages"]:
        if p["id"] in ids:
            p["deleted"] = {"timestamp": "1:2", "value": 0}
    c["pageTags"] = [t for t in c.get("pageTags") or [] if t.get("pageId") not in ids]
    _pages_done(doc, c)
    for pid in ids:
        _drop_page_files(doc, pid)
    return len(chosen)


def tag_pages(doc, page_nos, add=(), remove=()):
    """Tags put on and taken off every page chosen (no case: "Joi" is "joi"). -> how many pages."""
    _guard()
    c, _live0, chosen = _chosen(doc, page_nos)
    add, gone = _clean(add), {t.lower() for t in _clean(remove)}
    now = _now()
    tags = list(c.get("pageTags") or [])
    for p in chosen:
        mine = [t for t in tags if t.get("pageId") == p["id"]]
        keep = [t for t in mine if str(t.get("name", "")).lower() not in gone]
        have = {str(t.get("name", "")).lower() for t in keep}
        keep += [{"name": t, "pageId": p["id"], "timestamp": now} for t in add if t.lower() not in have]
        tags = [t for t in tags if t.get("pageId") != p["id"]] + keep
    c["pageTags"] = tags
    _save_content(doc, c)
    _touch(doc)
    return len(chosen)


def move(u, parent):
    _guard()
    if parent and (parent == u or parent not in F.items()):
        raise ValueError("that folder is not in the False Mirror")
    return F.move(u, parent)


def delete(u):
    """Into the trash, as the tablet deletes: out of every list, its files kept."""
    _guard()
    return F.move(u, "trash")


def set_tags(u, tags):
    """A folder's or a document's tags, as the tablet stores them."""
    _guard()
    p = os.path.join(M, u + ".content")
    c = _read(p) if os.path.exists(p) else {}
    was = {str(t.get("name") if isinstance(t, dict) else t): t for t in c.get("tags") or []}
    now = _now()
    c["tags"] = [was.get(t) if isinstance(was.get(t), dict) else {"name": t, "timestamp": now} for t in _clean(tags)]
    paths.write_json_atomic(p, c)
    _touch(u)


def set_page_tags(doc, page_no, tags):
    _guard()
    pid = page_id(doc, page_no)
    c = _content(doc)
    keep = [t for t in c.get("pageTags") or [] if t.get("pageId") != pid]
    was = {t.get("name"): t for t in c.get("pageTags") or [] if t.get("pageId") == pid}
    now = _now()
    c["pageTags"] = keep + [was.get(t) or {"name": t, "pageId": pid, "timestamp": now} for t in _clean(tags)]
    _save_content(doc, c)
    _touch(doc)


def set_page_template(doc, page_no, file):
    """A page's template, by its file name as the tablet records it ("P Grid medium"; "Blank" for none)."""
    _guard()
    file = str(file or "Blank").strip()[:120] or "Blank"
    pid = page_id(doc, page_no)
    c = _content(doc)
    for p in c["cPages"]["pages"]:
        if p.get("id") == pid:
            ts = (p.get("template") or {}).get("timestamp") or "1:1"
            p["template"] = {"timestamp": ts, "value": file}
    _save_content(doc, c)
    pd = os.path.join(M, doc + ".pagedata")
    if os.path.exists(pd):                         # the older list of each page's template, one a line
        live = [p["id"] for p in _live(c)]
        lines = open(pd, encoding="utf-8").read().splitlines()
        if page_no - 1 < len(lines) and len(lines) == len(live):
            lines[page_no - 1] = file
            paths.write_atomic(pd, "\n".join(lines) + "\n")
    _touch(doc)


def page_template(doc, page_no):
    pid = page_id(doc, page_no)
    for p in _live(_content(doc)):
        if p.get("id") == pid:
            return (p.get("template") or {}).get("value") or "Blank"
    return "Blank"


def _clean(tags):
    out = []
    for t in tags or []:
        t = str(t).strip()
        if t and t.lower() not in [x.lower() for x in out]:
            out.append(t[:64])
    return out


# ---------------------------------------------------------------- a page, for the editor

def _rm(doc, page_no):
    return os.path.join(M, doc, page_id(doc, page_no) + ".rm")


def _rows(points, arrays):
    """A stroke's points as the editor takes them: the array itself (arrays), or rows [x, y, speed, direction, width,
    pressure] -- from a fastrm array in one step, or from rmscene's si.Point list."""
    import numpy as np
    from paperdaemon.remarkable import fastrm
    if isinstance(points, np.ndarray):
        if arrays:
            return points
        cols = [points[k].tolist() for k in ("x", "y", "speed", "direction", "width", "pressure")]
        return [list(t) for t in zip(*cols)]
    rows = [[p.x, p.y, p.speed, p.direction, p.width, p.pressure] for p in points]
    return fastrm.points_of(rows) if arrays else rows


def _moved(points, dx, dy):
    """A stroke's points (rows, or a fastrm.POINT array) moved by (dx, dy): a copy, the page's own left alone."""
    if not dx and not dy:
        return points
    import numpy as np
    if isinstance(points, np.ndarray):
        out = points.copy()
        out["x"] += dx
        out["y"] += dy
        return out
    return [[r[0] + dx, r[1] + dy] + list(r[2:]) for r in points]


def page_version(doc, page_no):
    """A short stamp of the page as its files are now (the page's .rm, and the notebook's .content, which holds its
    template): the same stamp, the same page. The editor asks with it, and a page that has not changed is not read."""
    out = []
    for p in (_rm(doc, page_no), os.path.join(M, doc + ".content")):
        try:
            st = os.stat(p)
            out.append("%x.%x" % (st.st_mtime_ns, st.st_size))
        except OSError:
            out.append("-")
    return "-".join(out)


def scene_of(doc, page_no, arrays=False):
    """The page as the editor holds it (see the module's note). With `arrays`, each stroke's points are its fastrm.POINT
    array as read, for the editor's binary form (scene_bytes); else rows [x, y, speed, direction, width, pressure]."""
    from paperdaemon.remarkable import fastrm
    from rmscene import SceneTree
    from paperdaemon.pipeline.page import typed as TY
    from paperdaemon.pipeline.page import render as R
    path = _rm(doc, page_no)
    # A PAGE OF A PDF OR A BOOK: drawn on as the tablet allows (no typing there), its page under the ink (source.png)
    kind, _src, idx = R.source_page(doc, page_no)
    source = kind if kind in ("pdf", "epub") and idx is not None else None
    if not os.path.exists(path):                     # never written on: no page file yet, the page's own frame
        w, h = R.page_frame(doc, page_no)
        return {"paperSize": [w, h], "layers": [{"label": "Layer 1", "visible": True, "lines": []}], "text": None,
                "textVisible": True, "templateVisible": True, "template": page_template(doc, page_no), "source": source,
                "images": []}
    data = open(path, "rb").read()
    # THE FILE IS PARSED ONCE: the tree is built from the same blocks (rmscene's read_tree parses it again), and the typed
    # text's own reader runs only when the page has typed text -- a page with a decomp on it is seconds a parse
    # IN ONE PASS where it can be (fastrm.scene_parts: the strokes read in C, the few other blocks by rmscene); a page it
    # does not cover is read block by block, the strokes' points in one step each (fastrm.read_blocks)
    parts = fastrm.scene_parts(data)
    blocks = parts[0] if parts else list(fastrm.read_blocks(data))
    info = next((b for b in blocks if isinstance(b, ss.SceneInfo)), None)
    tree = SceneTree()
    _build_tree(tree, blocks)
    typed_here = any(isinstance(b, ss.RootTextBlock) for b in blocks)
    if parts:
        groups = [g for g in tree.root.children.values() if isinstance(g, si.Group)]
        nested = any(isinstance(c, si.Group) for g in groups for c in g.children.values())
        if nested or set(parts[1]) - {g.node_id for g in groups}:
            parts = None                            # groups in a layer, or strokes outside the layers: read as before
            blocks = list(fastrm.read_blocks(data))
            tree = SceneTree()
            _build_tree(tree, blocks)

    # WHERE THE TABLET DRAWS EACH GROUP: one anchored to the typed text moves with it (render._anchor_offsets, as the
    # renderer places it). Read at their stored coordinates, a drawing anchored below the text sat at the top left,
    # over the text -- and a save from the editor wrote it there.
    offs = R._anchor_offsets(doc, page_no, blocks)

    def lines_in(group, out):
        dx, dy = offs.get(group.node_id, (0.0, 0.0))
        for item in group.children.values():
            if isinstance(item, si.Line):
                out.append({"pen": item.tool.name if hasattr(item.tool, "name") else str(item.tool),
                            "penCode": int(item.tool), "color": int(item.color),
                            "colorRgba": list(item.color_rgba) if getattr(item, "color_rgba", None) else None,
                            "thicknessScale": float(item.thickness_scale),
                            "points": _moved(_rows(item.points, arrays), dx, dy)})
            elif isinstance(item, si.Group):
                lines_in(item, out)
        return out

    layers = []
    for g in tree.root.children.values():
        if isinstance(g, si.Group):
            if parts:
                dx, dy = offs.get(g.node_id, (0.0, 0.0))
                lines = [dict(ln, points=_moved(_rows(ln["points"], arrays), dx, dy)) for ln in parts[1].get(g.node_id, [])]
            else:
                lines = lines_in(g, [])
            # THE DAEMON'S LAYER (named as his, or under his old author): shown, and marked, so the editor leaves it to him
            layers.append({"label": g.label.value or "Layer %d" % (len(layers) + 1), "visible": bool(g.visible.value),
                           "lines": lines, "daemon": g.node_id.part1 == R.DAEMON_AUTHOR
                           or g.label.value in (R.daemon_layer_name(), R.DAEMON_LEGACY)})
    if not layers:
        layers = [{"label": "Layer 1", "visible": True, "lines": []}]
    text = None
    try:
        # the text read from the page without its strokes: they are most of the file, and seconds to read on a page
        # with a decomp, for nothing the text needs
        rec = TY.from_blocks(TY.read_preserved(fastrm.without_strokes(data)), data) if typed_here else {}
        if rec.get("column"):
            paras = []
            for p in rec["paragraphs"]:
                style, lst = STYLE_OF.get(p.get("style_code"), ("body", None))
                paras.append({"style": style, "list": lst, "runs": [{"text": r["text"], "bold": bool(r["format"].get("bold")),
                                                                      "italic": bool(r["format"].get("italic"))}
                                                                     for r in p.get("runs") or []]})
            col = rec["column"]
            text = {"x": col["x"], "y": col["y"], "width": col["width"], "paras": paras}
    except Exception:
        text = None
    size = list(info.paper_size) if info is not None and info.paper_size else [1620, 2160]
    lww = lambda v, d: (v.value if isinstance(v, LwwValue) else v) if v is not None else d
    if source:
        size = list(R.page_frame(doc, page_no))
    return {"paperSize": size, "layers": layers, "text": text,
            "textVisible": bool(lww(getattr(info, "root_document_visible", None), True)),
            "templateVisible": bool(lww(getattr(info, "background_visible", None), True)),
            "template": page_template(doc, page_no), "source": source, "images": pictures_of(doc, page_no, data),
            "zoom": _content(doc).get("zoomMode") or "bestFit"}


# ---------------------------------------------------------------- pictures on a page
# THE EDITOR SHOWS AND KEEPS A PAGE'S PICTURES (captures, a pasted image, the daemon's coloring pages and chess pieces):
# each is its file beside the page (<doc>/<page>/<name>) and its four corners on the page, as the tablet stores them
# (pipeline/page/images.py reads and writes the blocks). A save writes them back after the strokes, on Layer 1 at their
# page corners, each with its own asset and hash.
PICTURE_NAME = re.compile(r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}\.(png|jpg)$")


def pictures_of(doc, page_no, data=None):
    """[{name, key, quad: [[x, y] x 4]}] of the page's live pictures, in page coordinates, lowest first."""
    from paperdaemon.pipeline.page import images as IM
    try:
        pid = page_id(doc, page_no)
        got = IM.items(doc, page_no, page_id=pid)
    except Exception:
        return []
    out = []
    for im in got:
        if im.get("name") and PICTURE_NAME.match(im["name"]) and im.get("path"):
            out.append({"name": im["name"], "key": im.get("hash") or "", "quad": [[float(x), float(y)] for x, y in im["quad"]]})
    return out


def picture_path(doc, page_no, name):
    """The file of a picture on the page, or None."""
    if not PICTURE_NAME.match(name or ""):
        return None
    p = os.path.join(M, doc, page_id(doc, page_no), name)
    return p if os.path.isfile(p) else None


def add_picture(doc, page_no, data):
    """A new picture's file (PNG or JPEG bytes) beside the page, under a name of its own. -> {name, width, height}."""
    _guard()
    from PIL import Image
    with Image.open(io.BytesIO(data)) as im:
        kind, (w, h) = (im.format or "").upper(), im.size
    if kind not in ("PNG", "JPEG"):
        raise ValueError("a picture is a PNG or a JPEG")
    name = str(uuid.uuid4()) + (".png" if kind == "PNG" else ".jpg")
    folder = os.path.join(M, doc, page_id(doc, page_no))
    os.makedirs(folder, exist_ok=True)
    paths.write_atomic(os.path.join(folder, name), data)
    return {"name": name, "width": w, "height": h}


def _picture_blocks(doc, page_no, pictures, layer, nid):
    """The asset and item blocks of the scene's pictures, as raw bytes in the tablet's form, and how many."""
    import hashlib
    from paperdaemon.pipeline.page import images as IM
    out, n = b"", 0
    for pic in pictures or []:
        name, quad = pic.get("name"), pic.get("quad") or []
        if not picture_path(doc, page_no, name) or len(quad) != 4:
            continue
        try:
            h = bytes.fromhex(pic.get("key") or "")
        except ValueError:
            h = b""
        if len(h) != 16:
            h = hashlib.md5(name.encode("ascii")).digest()
        asset, item = nid(), nid()
        out += IM.asset_block(h, name, (asset.part1, asset.part2))
        out += IM.item_block_quad((layer.part1, layer.part2), (item.part1, item.part2), (asset.part1, asset.part2), h, quad)
        n += 1
    return out, n


def _enum(kind, v):
    try:
        return kind(int(v))
    except ValueError:
        return int(v)


def _leading_blocks(data):
    """The blocks before the page's first stroke (the header ones write_scene keeps): read up to there and no further,
    since the strokes after them are most of the file and seconds to read on a page with a decomp."""
    out = []
    for b in read_blocks(io.BytesIO(data)):
        if isinstance(b, ss.SceneLineItemBlock):
            break
        out.append(b)
    return out


def _line_blocks_in(data):
    """The stroke blocks in a page's bytes, counted by walking the blocks' frames (each block: its length, 4 bytes,
    then 3 bytes of versions and its type), the walk ending exactly at the end -> how many; or -1 when the frames do
    not add up. It reads none of the blocks, so a page of tens of thousands of strokes checks in milliseconds."""
    from rmscene.tagged_block_common import HEADER_V6
    if not data.startswith(HEADER_V6):
        return -1
    pos, n, end = len(HEADER_V6), 0, len(data)
    while pos < end:
        if pos + 8 > end:
            return -1
        size = int.from_bytes(data[pos:pos + 4], "little")
        if data[pos + 7] == ss.SceneLineItemBlock.BLOCK_TYPE:
            n += 1
        pos += 8 + size
    return n if pos == end else -1


_writing = threading.Lock()                          # one page written at a time: a save never meets another half way


def _build_tree(tree, blocks):
    """rmscene's build_tree, but a page that names one item twice in a layer (a group and a stroke under one id, as a
    writer once left them) is read whole, as the tablet and the renderer draw it: the second keeps its place under an
    id of its own instead of the page failing to open ("Already have item")."""
    from dataclasses import replace
    spare = [0]

    def add(item, parent):
        try:
            tree.add_item(item, parent)
        except ValueError as ex:
            if "Already have item" not in str(ex):
                raise
            spare[0] += 1
            tree.add_item(replace(item, item_id=CrdtId(0x7FFF, spare[0])), parent)
    for b in blocks:
        if isinstance(b, ss.SceneGroupItemBlock):
            node_id = b.item.value
            if node_id is None:
                continue
            if node_id not in tree:
                raise ValueError("Node does not exist for SceneGroupItemBlock: %s" % node_id)
            add(replace(b.item, value=tree[node_id]), b.parent_id)
        elif isinstance(b, (ss.SceneLineItemBlock, ss.SceneGlyphItemBlock)):
            add(b.item, b.parent_id)
        else:
            ss.build_tree(tree, [b])


def write_scene(doc, page_no, scene):
    with _writing:
        return _write_scene(doc, page_no, scene)


def _write_scene(doc, page_no, scene):
    """The page made anew from the editor's scene, its header blocks kept. -> the number of strokes written. A stroke's
    points are rows [x, y, speed, direction, width, pressure] or a fastrm.POINT array (the editor's binary form)."""
    from paperdaemon.remarkable import fastrm
    _guard()
    path = _rm(doc, page_no)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    old = _leading_blocks(open(path, "rb").read()) if os.path.exists(path) else []
    head = [b for b in old if isinstance(b, (ss.AuthorIdsBlock, ss.MigrationInfoBlock))]
    info = next((b for b in old if isinstance(b, ss.SceneInfo)), None)
    if not any(isinstance(b, ss.AuthorIdsBlock) for b in head):
        head.insert(0, ss.AuthorIdsBlock(author_uuids={1: uuid.uuid4()}))
    seq = [16]

    def nid(n=1):
        k = seq[0]
        seq[0] += n
        return CrdtId(1, k)

    layers = scene.get("layers") or [{"label": "Layer 1", "visible": True, "lines": []}]
    # THE DAEMON'S LAYER IS HIS: the editor's copy of it is dropped, and his own blocks are kept from the file as he
    # wrote them (_daemon_blocks). Written anew under the editor's ids, his notes became the user's strokes: he could
    # no longer erase them, and made himself another layer.
    keep_his = any(L.get("daemon") for L in layers)
    layers = [L for L in layers if not L.get("daemon")] or [{"label": "Layer 1", "visible": True, "lines": []}]
    his = _daemon_blocks(path) if keep_his else None
    nodes = [CrdtId(0, 11)] + [nid() for _ in layers[1:]]
    tree = [ss.SceneTreeBlock(tree_id=n, node_id=CrdtId(0, 0), is_update=True, parent_id=CrdtId(0, 1)) for n in nodes]
    groups = [ss.TreeNodeBlock(group=si.Group(node_id=CrdtId(0, 1)))]
    for L, n in zip(layers, nodes):
        g = si.Group(node_id=n)
        g.label = LwwValue(timestamp=nid(), value=str(L.get("label") or "Layer"))
        g.visible = LwwValue(timestamp=nid(), value=bool(L.get("visible", True)))
        groups.append(ss.TreeNodeBlock(group=g))
    placed, prev = [], CrdtId(0, 0)
    for n in nodes:
        gid = nid()
        placed.append(ss.SceneGroupItemBlock(parent_id=CrdtId(0, 1), item=CrdtSequenceItem(
            item_id=gid, left_id=prev, right_id=CrdtId(0, 0), deleted_length=0, value=n)))
        prev = gid
    strokes, count = [], 0
    for L, n in zip(layers, nodes):
        prev = CrdtId(0, 0)
        for ln in L.get("lines") or []:
            pts = ln.get("points")
            pts = fastrm.points_of(pts) if pts is not None and len(pts) else None    # rows or an array, as one array
            if pts is None or not len(pts):
                continue
            rgba = ln.get("colorRgba")
            line = si.Line(color=_enum(si.PenColor, ln.get("color", 0)), tool=_enum(si.Pen, ln.get("penCode", 17)),
                           points=pts, thickness_scale=float(ln.get("thicknessScale") or 1.0), starting_length=0.0,
                           move_id=None, color_rgba=tuple(int(v) for v in rgba) if rgba else None)
            iid = nid()
            strokes.append(ss.SceneLineItemBlock(parent_id=n, item=CrdtSequenceItem(
                item_id=iid, left_id=prev, right_id=CrdtId(0, 0), deleted_length=0, value=line)))
            prev = iid
            count += 1
    text = _text_block(scene.get("text"), nid)
    if info is not None:
        info.root_document_visible = LwwValue(timestamp=CrdtId(1, 1), value=bool(scene.get("textVisible", True)))
        info.background_visible = LwwValue(timestamp=CrdtId(1, 1), value=bool(scene.get("templateVisible", True)))
    chars = sum(len(r.get("text") or "") for p in ((scene.get("text") or {}).get("paras") or []) for r in p.get("runs") or [])
    blocks = head + [ss.PageInfoBlock(loads_count=1, merges_count=0, text_chars_count=chars,
                                      text_lines_count=len(((scene.get("text") or {}).get("paras")) or []))]
    if his:
        # his layer at the bottom of the list again, before the editor's first layer; his strokes after the editor's
        tree += his["tree"]
        groups += his["nodes"]
        for p in his["places"]:
            placed.insert(0, ss.SceneGroupItemBlock(parent_id=p.parent_id, item=CrdtSequenceItem(
                item_id=p.item.item_id, left_id=CrdtId(0, 0), right_id=placed[0].item.item_id if placed else CrdtId(0, 0),
                deleted_length=0, value=p.item.value)))
        strokes += his["lines"]
        count += len(his["lines"])
    blocks += ([info] if info is not None else []) + tree + groups + placed + ([text] if text else [])
    buf = io.BytesIO()
    write_blocks(buf, blocks)
    fastrm.write_lines(buf, strokes)                 # the strokes last, as rmscene would write them, in bulk (fastrm)
    pics, npics = _picture_blocks(doc, page_no, scene.get("images"), nodes[0], nid)
    data = buf.getvalue() + pics
    back = _line_blocks_in(data)
    if back != count:
        raise RuntimeError("the page did not read back: %d strokes written, %d read" % (count, back))
    if npics:
        from paperdaemon.pipeline.page import images as IM
        if len([im for im in IM.parse(data) if not im["deleted"]]) != npics:
            raise RuntimeError("the page's pictures did not read back")
    paths.write_atomic(path, data)
    _touch(doc)
    return count


def _daemon_blocks(path):
    """The daemon's own blocks in the page file -- his layers' tree blocks and nodes, their places in the list of
    layers, and every stroke block on them (tombstones too, so what he erased stays erased) -> {tree, nodes, places,
    lines}, or None when the page has none."""
    from paperdaemon.remarkable import fastrm
    from paperdaemon.pipeline.page import render as R
    if not os.path.exists(path):
        return None
    me = R.DAEMON_AUTHOR
    out = {"tree": [], "nodes": [], "places": [], "lines": []}
    for b in fastrm.read_blocks(open(path, "rb").read()):
        if isinstance(b, ss.SceneTreeBlock) and b.tree_id.part1 == me:
            out["tree"].append(b)
        elif isinstance(b, ss.TreeNodeBlock) and b.group.node_id.part1 == me:
            out["nodes"].append(b)
        elif isinstance(b, ss.SceneGroupItemBlock) and b.item.value is not None and b.item.deleted_length == 0 \
                and getattr(b.item.value, "part1", None) == me and b.parent_id == CrdtId(0, 1):
            out["places"].append(b)
        elif isinstance(b, ss.SceneLineItemBlock) and b.parent_id.part1 == me:
            out["lines"].append(b)
    return out if out["nodes"] else None


def _text_block(text, nid):
    """The root text block: the paragraphs as text items (bold and italic as the format items 1-4 between runs), each
    paragraph's style keyed by the newline before it (the first by 0:0)."""
    paras = (text or {}).get("paras") or []
    if not paras:
        return None
    items, styles, prev = [], {}, CrdtId(0, 0)
    state = {"bold": False, "italic": False}

    def add(value, n):
        nonlocal prev
        iid = nid(n)
        items.append(CrdtSequenceItem(item_id=iid, left_id=prev, right_id=CrdtId(0, 0), deleted_length=0, value=value))
        prev = CrdtId(iid.part1, iid.part2 + n - 1)
        return iid

    for i, p in enumerate(paras):
        code = CODE_OF.get((p.get("style") or "body", p.get("list") or None), 1)
        if i:
            key = add("\n", 1)
            styles[key] = LwwValue(timestamp=nid(), value=code)
        else:
            styles[CrdtId(0, 0)] = LwwValue(timestamp=nid(), value=code)
        for r in p.get("runs") or []:
            for k, on, off in (("bold", 1, 2), ("italic", 3, 4)):
                if bool(r.get(k)) != state[k]:
                    state[k] = bool(r.get(k))
                    add(on if state[k] else off, 1)
            t = r.get("text") or ""
            if t:
                add(t, len(t))
    return ss.RootTextBlock(block_id=CrdtId(0, 0), value=si.Text(
        items=CrdtSequence(items), styles=styles, pos_x=float(text.get("x", -576)), pos_y=float(text.get("y", 234)),
        width=float(text.get("width", 1152))))
