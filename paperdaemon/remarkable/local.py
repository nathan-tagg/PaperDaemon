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
import zlib

import numpy as np

from rmscene import read_blocks, write_blocks
from rmscene import scene_items as si
from rmscene import scene_stream as ss
from rmscene.crdt_sequence import CrdtSequence, CrdtSequenceItem
from rmscene.tagged_block_common import CrdtId, LwwValue

from .. import paths
from . import library as F
from .sync import page_deleted

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
    # (a page is deleted when its marker's value says so, as the library and the tablet read it: a marker of 0 is a
    # page the tablet brought back -- here counted as deleted, the window listed pages the editor could not open)
    return sorted((p for p in (c.get("cPages") or {}).get("pages") or [] if not page_deleted(p)),
                  key=lambda p: p["idx"]["value"])


def page_id(doc, page_no):
    live = _live(_content(doc))
    if not 1 <= page_no <= len(live):
        raise ValueError("there is no page %d" % page_no)
    return live[page_no - 1]["id"]


# ---------------------------------------------------------------- notebooks, folders, pages

def new_notebook(name, parent="", template="Blank", cover="last", tags=(), tablet=False):
    """A notebook with one page, in the Paper Pro's frame, as the tablet makes one: its cover the page last visited
    (`cover` "last") or its first page ("first"), its page's `template` (the tablet's file name, "P Grid medium";
    "Blank" for none). -> its id.

    `tablet`: ON THE TABLET'S OWN LIBRARY (the Mirror; the caller has checked that Mirror editing is on). Its page is
    one of the user's own tablet's, and the notebook is sent to the tablet at once, a document the cloud has never
    seen; a push that does not go through is said, and the notebook goes up with the next sync."""
    if not tablet:
        _guard()
    from paperdaemon import studio
    doc = str(uuid.uuid4())
    template = str(template or "Blank").strip()[:120] or "Blank"
    studio._new_notebook(M, _pipeline(), doc, (name or "Notebook").strip() or "Notebook", parent, _now())
    # the false mirror: the bundled Paper Pro page (no user library to copy); the tablet's: a page in its own frame
    blank = studio._blank_page_bytes(_pipeline(), M if tablet else None)
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
        _set_tags(doc, tags)                         # the notebook's own tags, as New notebook was given them
    if tablet:
        from . import sync
        r = sync.push_new_doc(doc, dry_run=False) or {}
        if r.get("root_put") != 200:
            raise ValueError("the notebook is made here and was not sent to the tablet (%s); it goes up with the next "
                             "sync" % str(r.get("error") or r.get("root_put") or "no answer")[:120])
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
    """-> how many went. EVERY PAGE CHOSEN: a blank page with no template made after them first (_blank_after), so the
    notebook keeps one -- the page it opens on next."""
    _guard()
    c, live, chosen = _chosen(doc, page_nos)
    if len(chosen) >= len(live):
        _blank_after(doc, live)
        c, live, chosen = _chosen(doc, page_nos)             # (the new page after them: the pages chosen keep their numbers)
    ids = {p["id"] for p in chosen}
    _mark_deleted(c, ids)
    c["pageTags"] = [t for t in c.get("pageTags") or [] if t.get("pageId") not in ids]
    _pages_done(doc, c)
    for pid in ids:
        _drop_page_files(doc, pid)
    return len(ids)


def _blank_after(doc, live):
    """A blank page with no template after the last of `live` -> its id: in the frame of a page of the notebook that has
    its file (insert_pages), else the bundled Paper Pro page new notebooks start from (a book's pages may have none)."""
    with_file = [p for p in reversed(live) if os.path.exists(_page_files(doc, p["id"])[0])]
    if with_file:
        [(pid, _key)] = F.insert_pages(doc, live[-1]["id"], 1, template_from=with_file[0]["id"])
    else:
        from paperdaemon import studio
        pid, last = str(uuid.uuid4()), live[-1]
        paths.write_atomic(_page_files(doc, pid)[0], studio._blank_page_bytes(_pipeline()))
        c = _content(doc)
        c["cPages"]["pages"].append({"id": pid, "idx": {"timestamp": last["idx"]["timestamp"], "value": F.key_between(last["idx"]["value"])},
                                     "modifed": str(_now())})
        _save_content(doc, c)
    c = _content(doc)
    for p in c["cPages"]["pages"]:
        if p["id"] == pid:
            p["template"] = {"timestamp": (p.get("template") or {}).get("timestamp") or "1:1", "value": "Blank"}
    _save_content(doc, c)
    return pid


def _mark_deleted(c, ids):
    """Pages `ids` marked deleted as the tablet marks them: value 1, stamped after everything the document holds."""
    gone = F._later(c)
    for p in c["cPages"]["pages"]:
        if p["id"] in ids:
            p["deleted"] = {"timestamp": gone, "value": 1}


def mend_deleted_pages():
    """PAGES DELETED HERE BEFORE 0.2.8 were marked {"timestamp": "1:2", "value": 0}: the marker the tablet keeps on a
    page it brought back, which the library reads as live, so each came back in the window as a page that could not be
    opened. In a notebook whose page count was written here (its pages counted without them), each such page whose ink
    went with it is marked deleted again; a page with its ink is left as it is. -> how many were mended."""
    _guard()
    n = 0
    for name in os.listdir(M):
        if not name.endswith(".content"):
            continue
        doc = name[:-len(".content")]
        try:
            c = _content(doc)
        except (OSError, ValueError):
            continue
        pages = (c.get("cPages") or {}).get("pages") or []
        if (c.get("fileType") or "notebook") != "notebook" or c.get("pageCount") != sum(1 for p in pages if "deleted" not in p):
            continue
        ids = {p.get("id") for p in pages if isinstance(p.get("deleted"), dict) and not p["deleted"].get("value")
               and not os.path.exists(_page_files(doc, str(p.get("id")))[0])}
        if ids:
            _mark_deleted(c, ids)
            _save_content(doc, c)
            n += len(ids)
    return n


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
    _mark_deleted(c, ids)
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
    _set_tags(u, tags)


def _set_tags(u, tags):
    p = os.path.join(M, u + ".content")
    c = _read(p) if os.path.exists(p) else {}
    was = {str(t.get("name") if isinstance(t, dict) else t): t for t in c.get("tags") or []}
    now = _now()
    c["tags"] = [was.get(t) if isinstance(was.get(t), dict) else {"name": t, "timestamp": now} for t in _clean(tags)]
    paths.write_json_atomic(p, c)
    _touch(u)


def clean_name(name):
    """A name as the tablet shows one: its spaces run together, at most 255 characters; none raises a ValueError."""
    name = " ".join(str(name or "").split())[:255]
    if not name:
        raise ValueError("a name is needed")
    return name


def rename(u, name):
    """A document's or a folder's name, as the tablet shows it (its .metadata's visibleName). -> whether it changed."""
    _guard()
    name = clean_name(name)
    p = os.path.join(M, u + ".metadata")
    m = _read(p)
    if m.get("visibleName") == name:
        return False
    m["visibleName"] = name
    m["lastModified"] = str(_now())
    paths.write_json_atomic(p, m)
    return True


def set_cover(doc, first):
    """A document's cover, as the tablet's own setting: its first page (`first`; coverPageNumber 0) or the page last
    visited (-1). -> whether it changed."""
    _guard()
    c = _content(doc)
    want = 0 if first else -1
    if c.get("coverPageNumber") == want:
        return False
    c["coverPageNumber"] = want
    _save_content(doc, c)
    _touch(doc)
    return True


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
    pressure] -- from a fastrm array in one step, or from rmscene's si.Point list. (Nothing imported for the arrays: a
    stroke at a time, an import was a tenth of a second of a page of 150,000 strokes.)"""
    if isinstance(points, np.ndarray):
        if arrays:
            return points
        cols = [points[k].tolist() for k in ("x", "y", "speed", "direction", "width", "pressure")]
        return [list(t) for t in zip(*cols)]
    from paperdaemon.remarkable import fastrm
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
    """A short stamp of the page as its files are now: its .rm, and what the notebook's .content says of THIS page
    (which page it is, its template, the page of the book under it, the book's kind) -- the same stamp, the same page.
    Not the whole .content: a page added, moved, deleted or tagged elsewhere in the notebook leaves this page's stamp,
    and its form kept by the engine, as they were. The editor asks with it, and a page that has not changed is not read."""
    path = _rm(doc, page_no)
    try:
        st = os.stat(path)
        out = ["%x.%x" % (st.st_mtime_ns, st.st_size)]
    except OSError:
        out = ["-"]
    try:
        c = _content(doc)
    except (OSError, ValueError):
        return out[0] + "--"
    live = _live(c)
    p = live[page_no - 1] if 1 <= page_no <= len(live) else {}
    said = json.dumps([c.get("fileType"), p.get("id"), p.get("template"), p.get("redir")], sort_keys=True)
    return out[0] + "-%08x" % (zlib.crc32(said.encode("utf-8")) & 0xFFFFFFFF)


def scene_head(doc, page_no):
    """THE PAGE WITHOUT ITS STROKES, as the editor holds it (scene_of, each layer's lines empty): its frame, template,
    typed text, the book's page under it and its pictures -- read without reading a stroke (their blocks skipped unread,
    fastrm.without_strokes), so at once whatever the page's size. The editor shows it while its strokes come."""
    path = _rm(doc, page_no)
    if os.path.exists(path):
        from paperdaemon.remarkable import fastrm
        got = scene_of(doc, page_no, data=fastrm.without_strokes(open(path, "rb").read()))
    else:
        got = scene_of(doc, page_no)
    for L in got.get("layers") or []:
        L["lines"] = []
    return got


def scene_of(doc, page_no, arrays=False, data=None, columns=False):
    """The page as the editor holds it (see the module's note). With `arrays`, each stroke's points are its fastrm.POINT
    array as read, for the editor's binary form (scene_bytes); else rows [x, y, speed, direction, width, pressure].

    EACH THING CARRIES ITS ID, for a page written in place (inplace.py): a stroke its item id ("id", [part1, part2]) and
    the group it sits in ("group": its layer, or a group anchored to the text inside one), a layer its node id ("id");
    and "shifts" lists each group the page draws moved ([{group, by: [dx, dy]}]), so a stroke shown moved is known
    again unchanged. `data`: read these bytes as the page (a page with no file yet, read as the blank it starts from)."""
    from paperdaemon.remarkable import fastrm
    from rmscene import SceneTree
    from paperdaemon.pipeline.page import typed as TY
    from paperdaemon.pipeline.page import render as R
    path = _rm(doc, page_no)
    # A PAGE OF A PDF OR A BOOK: drawn on as the tablet allows (no typing there), its page under the ink (source.png)
    kind, _src, idx = R.source_page(doc, page_no)
    source = kind if kind in ("pdf", "epub") and idx is not None else None
    if data is None and not os.path.exists(path):    # never written on: no page file yet, the page's own frame
        w, h = R.page_frame(doc, page_no)
        return {"paperSize": [w, h], "layers": [{"label": "Layer 1", "visible": True, "lines": []}], "text": None,
                "textVisible": True, "templateVisible": True, "template": page_template(doc, page_no), "source": source,
                "images": []}
    if data is None:
        data = open(path, "rb").read()
    # THE FILE IS PARSED ONCE: the tree is built from the same blocks (rmscene's read_tree parses it again), and the typed
    # text's own reader runs only when the page has typed text -- a page with a decomp on it is seconds a parse
    # IN ONE PASS where it can be (fastrm.scene_parts: the strokes read in C, the few other blocks by rmscene); a page it
    # does not cover is read block by block, the strokes' points in one step each (fastrm.read_blocks)
    # (columns: each layer's strokes left as the C reader's rows over the page's bytes, for scene_bytes to write as
    # columns -- "rows", "data", "shift" in place of "lines"; where the C reader is not sure, the strokes as ever)
    parts = fastrm.scene_rows(data) if columns else fastrm.scene_parts(data)
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
        gid = [group.node_id.part1, group.node_id.part2]
        for iid, item in group.children.items():
            if isinstance(item, si.Line):
                out.append({"pen": item.tool.name if hasattr(item.tool, "name") else str(item.tool),
                            "penCode": int(item.tool), "color": int(item.color),
                            "colorRgba": list(item.color_rgba) if getattr(item, "color_rgba", None) else None,
                            "thicknessScale": float(item.thickness_scale),
                            "points": _moved(_rows(item.points, arrays), dx, dy),
                            "id": [iid.part1, iid.part2], "group": gid})
            elif isinstance(item, si.Group):
                lines_in(item, out)
        return out

    layers = []
    for g in tree.root.children.values():
        if isinstance(g, si.Group):
            extra = {}
            if parts and columns:
                rs = parts[1].get(g.node_id)
                extra = {"rows": rs if rs is not None else np.zeros((0, 26), np.int64), "data": data,
                         "shift": offs.get(g.node_id, (0.0, 0.0))}
                lines = None
            elif parts:
                dx, dy = offs.get(g.node_id, (0.0, 0.0))
                lines = [dict(ln, points=_moved(_rows(ln["points"], arrays), dx, dy)) for ln in parts[1].get(g.node_id, [])]
            else:
                lines = lines_in(g, [])
            # THE DAEMON'S LAYER (named as his, or under his old author): shown, and marked, so the editor leaves it to him
            layers.append({"label": g.label.value or "Layer %d" % (len(layers) + 1), "visible": bool(g.visible.value),
                           **({"lines": lines} if lines is not None else extra), "daemon": g.node_id.part1 == R.DAEMON_AUTHOR
                           or g.label.value in (R.daemon_layer_name(), R.DAEMON_LEGACY),
                           "id": [g.node_id.part1, g.node_id.part2]})
    if not layers:
        layers = [{"label": "Layer 1", "visible": True, "lines": []}]
    text = scene_text(data) if typed_here else None
    size = list(info.paper_size) if info is not None and info.paper_size else [1620, 2160]
    lww = lambda v, d: (v.value if isinstance(v, LwwValue) else v) if v is not None else d
    if source:
        size = list(R.page_frame(doc, page_no))
    return {"paperSize": size, "layers": layers, "text": text,
            "textVisible": bool(lww(getattr(info, "root_document_visible", None), True)),
            "templateVisible": bool(lww(getattr(info, "background_visible", None), True)),
            "template": page_template(doc, page_no), "source": source, "images": pictures_of(doc, page_no, data),
            "zoom": _content(doc).get("zoomMode") or "bestFit",
            "shifts": [{"group": [k.part1, k.part2], "by": [float(v[0]), float(v[1])]} for k, v in offs.items() if v[0] or v[1]],
            # typed text that is on the page and could not be read (text None): said, so nobody takes the page for one
            # without words. It can be emptied in place (a save with no paragraphs), nothing else
            "textUnread": bool(typed_here and text is None and has_text(data))}


def has_text(data):
    """Whether the page's bytes hold typed characters that show (a text block with a live character in it), read
    without ordering them."""
    from paperdaemon.remarkable import fastrm
    from paperdaemon.pipeline.page import typed as TY
    try:
        for b in TY.read_preserved(fastrm.without_strokes(data)):
            items = getattr(getattr(getattr(b, "value", None), "items", None), "_items", None)
            if items and any(isinstance(i.value, str) and i.value.strip() and not i.deleted_length for i in items.values()):
                return True
    except Exception:
        return True                              # not even its blocks read: there is something
    return False


def scene_text(data):
    """A page's typed text as the editor holds it ({x, y, width, paras: [{style, list, runs: [{text, bold, italic}]}]}),
    or None when it has none or it cannot be read."""
    from paperdaemon.remarkable import fastrm
    from paperdaemon.pipeline.page import typed as TY
    try:
        # the text read from the page without its strokes: they are most of the file, and seconds to read on a page
        # with a decomp, for nothing the text needs
        rec = TY.from_blocks(TY.read_preserved(fastrm.without_strokes(data)), data)
        if not rec.get("column"):
            return None
        paras = []
        for p in rec["paragraphs"]:
            style, lst = STYLE_OF.get(p.get("style_code"), ("body", None))
            paras.append({"style": style, "list": lst, "runs": [{"text": r["text"], "bold": bool(r["format"].get("bold")),
                                                                  "italic": bool(r["format"].get("italic"))}
                                                                 for r in p.get("runs") or []]})
        col = rec["column"]
        out = {"x": col["x"], "y": col["y"], "width": col["width"], "paras": paras}
        if any(w.get("text_order") for w in rec.get("warnings") or []):
            out["inexact"] = True                # its items in a ring: shown, and only ever emptied (inplace.edit)
        return out
    except Exception:
        return None


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
            pic = {"name": im["name"], "key": im.get("hash") or "", "quad": [[float(x), float(y)] for x, y in im["quad"]]}
            if im.get("item"):
                pic["id"] = list(im["item"])           # its item id, for a page written in place (inplace.py)
            out.append(pic)
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
    return _add_picture(doc, page_no, data)


def _add_picture(doc, page_no, data):
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


def _picture_blocks(doc, page_no, pictures, layer, nid, oid=None):
    """The asset and item blocks of the scene's pictures, as raw bytes in the tablet's form, and how many. `oid(id)`:
    the new id of something that had `id` (a picture of PaperDaemon's stays under its author byte)."""
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
        asset, item = (oid(pic.get("id")), oid(pic.get("id"))) if oid else (nid(), nid())
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


def _text_frames(data):
    """The page's typed-text blocks as they are in its bytes, each block's whole frame, found by walking the frames
    (as _line_blocks_in does) without reading a block -> [bytes]; none when the frames do not add up."""
    from rmscene.tagged_block_common import HEADER_V6
    if not data.startswith(HEADER_V6):
        return []
    pos, end, out = len(HEADER_V6), len(data), []
    while pos + 8 <= end:
        size = int.from_bytes(data[pos:pos + 4], "little")
        if data[pos + 7] == ss.RootTextBlock.BLOCK_TYPE:
            out.append(data[pos:pos + 8 + size])
        pos += 8 + size
    return out if pos == end else []


def _past_ids(frame):
    """The first id past every id a kept text block uses (a text item of n characters holds n ids), so a page written
    around it never gives one id to two things; past a block that cannot be read, far past anything a page holds."""
    from rmscene.tagged_block_common import HEADER_V6
    try:
        tb = next(b for b in read_blocks(io.BytesIO(HEADER_V6 + frame)) if isinstance(b, ss.RootTextBlock))
        top = tb.block_id.part2
        for it in tb.value.items.sequence_items():
            n = len(it.value) if isinstance(it.value, str) else max(1, it.deleted_length or 0)
            top = max(top, it.item_id.part2 + n - 1)
        for k in tb.value.styles:
            top = max(top, k.part2)
        return top + 1
    except Exception:
        return 1 << 24


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
    # the engine's own lock, and the page's across the processes (the daemon's notes, the host's commits)
    with _writing, paths.page_lock(_rm(doc, page_no)):
        return _write_scene(doc, page_no, scene)


def _write_scene(doc, page_no, scene):
    """The page made anew from the editor's scene, its header blocks kept. -> the number of strokes written. A stroke's
    points are rows [x, y, speed, direction, width, pressure] or a fastrm.POINT array (the editor's binary form)."""
    from paperdaemon.remarkable import fastrm
    from paperdaemon.pipeline.page import render as R
    _guard()
    path = _rm(doc, page_no)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    old = _leading_blocks(open(path, "rb").read()) if os.path.exists(path) else []
    head = [b for b in old if isinstance(b, (ss.AuthorIdsBlock, ss.MigrationInfoBlock))]
    info = next((b for b in old if isinstance(b, ss.SceneInfo)), None)
    if not any(isinstance(b, ss.AuthorIdsBlock) for b in head):
        head.insert(0, ss.AuthorIdsBlock(author_uuids={1: uuid.uuid4()}))
    # NO TEXT IN THE SAVE IS "LEAVE THE TEXT AS IT IS", as the Mirror has it (a save that deletes it all sends a text
    # with no paragraphs): the page's own text blocks go back exactly as they were, and the new ids start past theirs.
    # Written from a scene whose text could not be read, a page lost its typed text.
    kept = _text_frames(open(path, "rb").read()) if scene.get("text") is None and os.path.exists(path) else []
    seq = [max([16] + [_past_ids(f) for f in kept])]

    def nid(n=1):
        k = seq[0]
        seq[0] += n
        return CrdtId(1, k)

    # WHAT PAPERDAEMON WROTE STAYS ITS OWN (render.author_of): a stroke or a picture whose id said so is written anew
    # under that same author byte, numbered past everything kept, and the page's author table names it; the rest is the
    # user's (1). Written anew under the editor's ids, a page's answers, pieces and pictures all became the user's after
    # any edit. Anything under his notes' old author (218, never written again) is a note of his (`his`: a stroke from
    # the page on his layer of a page from before his notes had a byte -- see below).
    own_seq, own_kind = {}, {}
    table0 = R.author_table(head)
    notes = R.page_author(table0, "notes")
    kinds0 = R.own_authors(table0)

    def oid(of, his=False):
        a = (of or [1])[0] if isinstance(of, (list, tuple)) and of else 1
        if a == R.DAEMON_AUTHOR or (his and of):
            k = "notes"
        else:                                         # the page's table says whose it is; an old byte (0.2.33 to 0.2.60,
            k = kinds0.get(a) or R.kind_of_author(a)  # which the tablet does not draw) its kind, written anew 2 to 10
            if k is None:
                return nid()
        a = R.page_author(table0, k)
        own_kind[a] = k
        own_seq[a] = own_seq.get(a, seq[0] + 100_000) + 1
        return CrdtId(a, own_seq[a])

    layers = scene.get("layers") or [{"label": "Layer 1", "visible": True, "lines": []}]
    # THE DAEMON'S LAYER IS HIS, AND THE USER DRAWS THERE TOO (the user's word, 11-07: "let me draw on it and keep my
    # strokes"): the layer itself -- its name, whether it shows, its place at the bottom of the list -- is kept from the
    # file as he made it (_daemon_blocks), and on it go the strokes the editor has there, each as whose it is: his under
    # his byte (their ids say so), the user's as the user's. (Written anew under the editor's ids, his notes once became
    # the user's strokes: he could no longer erase them, and made himself another layer.) His layers go with the save's in
    # order; one the save no longer has is gone (deleted), and one more than the page has is written as a layer -- as is
    # one made under his old author, which his next note takes out of the page with everything on it.
    on_his = [L for L in layers if L.get("daemon")]
    layers = [L for L in layers if not L.get("daemon")] or [{"label": "Layer 1", "visible": True, "lines": []}]
    his = _daemon_blocks(path) if on_his else None
    pairs = list(zip(his["order"], on_his)) if his else []
    his_at = [(n, L) for n, L in pairs if n.part1 != R.DAEMON_AUTHOR]
    layers += [dict(L, daemon=False) for n, L in pairs if n.part1 == R.DAEMON_AUTHOR] + \
              [dict(L, daemon=False) for L in on_his[len(pairs):]]
    # A PAGE FROM BEFORE HIS NOTES HAD A BYTE (its author table does not name it): everything on his layer is his until
    # his first note under it (render.notes_own_layers), so the first stroke of the user's there would go with that note.
    # The save that brings one makes the page's layer as it would be: what it holds from the page written under his
    # byte (his old notes, under the tablet's author then), and the table naming it -- the user's stroke stays theirs.
    old_page = notes not in next((b.author_uuids for b in head if isinstance(b, ss.AuthorIdsBlock)), {})
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
    strokes = []
    # WHOSE A STROKE ON HIS LAYER IS, AS THE PAGE SAYS: one the save carries exactly as the page holds it (its points as
    # stored) keeps the page's author byte. The editor's ids are as it last read them, and the page may have been
    # written since with his old notes laid again under his byte (below): taken from the ids, they went back to the user.
    his_keys = {(n.part1, n.part2) for n, _L in his_at}
    known = _his_strokes(path, his_keys) if his_keys else {}

    def put(L, n, his=False):
        on_his_layer = known and (n.part1, n.part2) in his_keys
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
            of = ln.get("id")
            if of and on_his_layer:
                a = known.get((n.part1, n.part2, pts.tobytes()))
                of = [a, 0] if a is not None else of
            iid = oid(of, his)
            strokes.append(ss.SceneLineItemBlock(parent_id=n, item=CrdtSequenceItem(
                item_id=iid, left_id=prev, right_id=CrdtId(0, 0), deleted_length=0, value=line)))
            prev = iid
    for L, n in zip(layers, nodes):
        put(L, n)
    for n, L in his_at:                              # his strokes after the editor's, the user's there with them
        put(L, n, old_page and any(not ln.get("id") for ln in L.get("lines") or []))
    count = len(strokes)
    # the pictures' ids now, so the page's author table names every author byte of PaperDaemon's the page is written with
    pics, npics = _picture_blocks(doc, page_no, scene.get("images"), nodes[0], nid, oid)
    for k, b in enumerate(head):
        if isinstance(b, ss.AuthorIdsBlock) and any(a not in b.author_uuids for a in own_seq):
            head[k] = ss.AuthorIdsBlock(author_uuids={**b.author_uuids,
                                                      **{a: R.uuid_of(own_kind[a]) for a in own_seq if a not in b.author_uuids}})
    text = _text_block(scene.get("text"), nid)
    if info is not None:
        info.root_document_visible = LwwValue(timestamp=CrdtId(1, 1), value=bool(scene.get("textVisible", True)))
        info.background_visible = LwwValue(timestamp=CrdtId(1, 1), value=bool(scene.get("templateVisible", True)))
    chars = sum(len(r.get("text") or "") for p in ((scene.get("text") or {}).get("paras") or []) for r in p.get("runs") or [])
    lines = len(((scene.get("text") or {}).get("paras")) or [])
    was = next((b for b in old if isinstance(b, ss.PageInfoBlock)), None)
    if kept and was is not None:
        chars, lines = was.text_chars_count, was.text_lines_count          # the kept text's own counts
    blocks = head + [ss.PageInfoBlock(loads_count=1, merges_count=0, text_chars_count=chars, text_lines_count=lines)]
    if his_at:
        # his layers at the bottom of the list again, before the editor's first layer, as he made them
        at = {(n.part1, n.part2) for n, _L in his_at}
        tree += [b for b in his["tree"] if (b.tree_id.part1, b.tree_id.part2) in at]
        groups += [b for b in his["nodes"] if (b.group.node_id.part1, b.group.node_id.part2) in at]
        place_of = {(p.item.value.part1, p.item.value.part2): p for p in his["places"]}
        hp = [place_of[(n.part1, n.part2)] for n, _L in his_at if (n.part1, n.part2) in place_of]
        first = placed[0].item.item_id if placed else CrdtId(0, 0)
        placed[:0] = [ss.SceneGroupItemBlock(parent_id=p.parent_id, item=CrdtSequenceItem(
            item_id=p.item.item_id, left_id=hp[i - 1].item.item_id if i else CrdtId(0, 0),
            right_id=hp[i + 1].item.item_id if i + 1 < len(hp) else first, deleted_length=0, value=p.item.value))
            for i, p in enumerate(hp)]
    blocks += ([info] if info is not None else []) + tree + groups + placed + ([text] if text else [])
    buf = io.BytesIO()
    write_blocks(buf, blocks)
    for f in kept:
        buf.write(f)                                 # the page's text, byte for byte
    fastrm.write_lines(buf, strokes)                 # the strokes last, as rmscene would write them, in bulk (fastrm)
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


def _his_strokes(path, layers):
    """The live strokes on these layers of the page file (node ids), by their points exactly as stored -> {(layer part1,
    part2, points bytes): author byte}."""
    from paperdaemon.remarkable import fastrm
    if not layers or not os.path.exists(path):
        return {}
    data = open(path, "rb").read()
    got = fastrm._c_pass(data, rows_only=True)
    out = {}
    if got is not None:
        for r in got[0].tolist():
            if r[0] == ss.SceneLineItemBlock.BLOCK_TYPE and r[14] and (r[5], r[6]) in layers:
                out[(r[5], r[6], data[r[19]:r[19] + r[20]])] = r[7]
        return out
    for b in fastrm.read_blocks(data):
        if isinstance(b, ss.SceneLineItemBlock) and isinstance(b.item.value, si.Line) \
                and (b.parent_id.part1, b.parent_id.part2) in layers:
            out[(b.parent_id.part1, b.parent_id.part2,
                 fastrm.points_of(_rows(b.item.value.points, True)).tobytes())] = b.item.item_id.part1
    return out


def _daemon_blocks(path):
    """The daemon's own layers in the page file (render.daemon_layer_ids: named as his, whoever made them, or under his
    old author) as he made them: their tree blocks and nodes, their places in the list of layers, and their node ids in
    the list's order, as the editor's scene has them (scene_of) -> {tree, nodes, places, order}, or None when the page
    has none. Their strokes are the save's (write_scene). (Found by his old author alone, his layer made under any other
    author was lost on a save.)"""
    from paperdaemon.remarkable import fastrm
    from paperdaemon.pipeline.page import render as R
    if not os.path.exists(path):
        return None
    blocks = list(fastrm.read_blocks(fastrm.without_strokes(open(path, "rb").read())))
    his = R.daemon_layer_ids(blocks)
    out = {"tree": [], "nodes": [], "places": [], "order": []}
    roots = []
    for b in blocks:
        if isinstance(b, ss.SceneTreeBlock) and (b.tree_id.part1, b.tree_id.part2) in his:
            out["tree"].append(b)
        elif isinstance(b, ss.TreeNodeBlock) and (b.group.node_id.part1, b.group.node_id.part2) in his:
            out["nodes"].append(b)
        elif isinstance(b, ss.SceneGroupItemBlock) and b.parent_id == CrdtId(0, 1):
            roots.append(b.item)
            if b.item.value is not None and b.item.deleted_length == 0 \
                    and (getattr(b.item.value, "part1", None), getattr(b.item.value, "part2", None)) in his:
                out["places"].append(b)
    try:
        keys = list(CrdtSequence(roots).keys())
    except Exception:
        keys = [it.item_id for it in roots]
    live = {it.item_id: it.value for it in roots if it.value is not None and not it.deleted_length}
    out["order"] = [live[k] for k in keys if k in live and (live[k].part1, live[k].part2) in his]
    return out if out["nodes"] and out["order"] else None


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
