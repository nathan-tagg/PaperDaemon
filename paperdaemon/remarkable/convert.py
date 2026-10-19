"""CONVERT WITH THE TABLET (openspec add-epub-reading, D5): the false mirror's books converted by the user's own tablet.

With the false mirror's "Convert books with the tablet" on, an account signed in and a real mirror, every book of the
false mirror that has no PDF is sent, as the desktop app sends a book, to the root of the tablet's library, tagged with
the configured ignore tag so no job is ever made of it. The tablet converts a book when it next syncs (it may be off
for days). When its PDF reaches the real mirror, the PDF and the tablet's reading settings are copied into the false
mirror's book, and the copy in the tablet's library is deleted outright (never to the trash).

The false mirror never reaches the cloud, so this runs in the engine, which does (loop's supervisor calls `tick`).
What is waiting is kept in <false-mirror-state>/convert.json: {false-mirror doc: {"tablet": doc, "sent": time}}.
"""

import json
import os
import time
import uuid

from .. import paths

READING = ("margins", "textScale", "lineHeight", "textAlignment", "fontName")


def _state_path():
    return os.path.join(paths.false_mirror_state_dir(), "convert.json")


def waiting():
    try:
        with open(_state_path(), encoding="utf-8") as f:
            return json.load(f).get("books") or {}
    except (OSError, ValueError):
        return {}


def _save(books):
    paths.write_json_atomic(_state_path(), {"books": books})


def _read(path):
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def on(s=None):
    """True when books should be converted: the setting, an account, a real mirror and a false mirror."""
    from .. import settings as S
    from . import auth
    s = s or S.load()
    if not (s.get("false_mirror") or {}).get("convert") or not paths.false_mirror_exists():
        return False
    try:
        return bool(auth.describe().get("set")) and os.path.isdir(paths.mirror_dir())
    except Exception:
        return False


def _books(fm):
    """The false mirror's books without a PDF (not in its trash)."""
    out = []
    for n in os.listdir(fm):
        if not n.endswith(".epub"):
            continue
        doc = n[:-5]
        if os.path.exists(os.path.join(fm, doc + ".pdf")):
            continue
        try:
            if _read(os.path.join(fm, doc + ".metadata")).get("parent") == "trash":
                continue
        except (OSError, ValueError):
            continue
        out.append(doc)
    return sorted(out)


def _send(fm, doc, ignore):
    """The book, as the desktop app files one, at the root of the tablet's library with the ignore tag. -> its id."""
    from . import sync
    mirror = sync.MIRROR
    meta = _read(os.path.join(fm, doc + ".metadata"))
    content = _read(os.path.join(fm, doc + ".content"))
    tid = str(uuid.uuid4())
    with open(os.path.join(fm, doc + ".epub"), "rb") as f:
        data = f.read()
    n = int(content.get("pageCount") or 1)
    ids = [str(uuid.uuid4()) for _ in range(n)]
    now = str(int(time.time() * 1000))
    tc = {"coverPageNumber": 0, "customZoomCenterX": 0, "customZoomCenterY": 936, "customZoomOrientation": "portrait",
          "customZoomPageHeight": 1872, "customZoomPageWidth": 1404, "customZoomScale": 1,
          "documentMetadata": content.get("documentMetadata") or {}, "extraMetadata": {}, "fileType": "epub",
          "fontName": "", "formatVersion": 1, "lineHeight": 100, "orientation": "portrait", "originalPageCount": n,
          "pageCount": n, "pageTags": [], "pages": ids, "redirectionPageMap": list(range(n)),
          "sizeInBytes": str(len(data)), "tags": [{"name": ignore, "timestamp": int(now)}],
          "textAlignment": "justify", "textScale": 1, "zoomMode": "bestFit"}
    tm = {"createdTime": now, "lastModified": now, "lastOpened": "0", "lastOpenedPage": 0, "new": False,
          "parent": "", "pinned": False, "source": "", "type": "DocumentType",
          "visibleName": meta.get("visibleName") or "Book"}
    paths.write_atomic(os.path.join(mirror, tid + ".epub"), data)
    paths.write_json_atomic(os.path.join(mirror, tid + ".content"), tc)
    paths.write_json_atomic(os.path.join(mirror, tid + ".metadata"), tm)
    paths.write_atomic(os.path.join(mirror, tid + ".pagedata"), "Blank\n" * n)
    got = sync.push_new_doc(tid, dry_run=False)
    if got.get("root_put") != 200:
        for ext in (".epub", ".content", ".metadata", ".pagedata"):
            try:
                os.remove(os.path.join(mirror, tid + ext))
            except OSError:
                pass
        raise RuntimeError("the book could not be sent to the tablet: %s" % (got.get("error") or got.get("root_put")))
    return tid


def _bring_back(fm, doc, tid):
    """The tablet's PDF and reading settings into the false mirror's book; its pages follow the tablet's count (pages
    added for a longer book, none taken away: ink stays where it was written)."""
    from . import sync, library
    mirror = sync.MIRROR
    tc = _read(os.path.join(mirror, tid + ".content"))
    with open(os.path.join(mirror, tid + ".pdf"), "rb") as f:
        pdf = f.read()
    cpath = os.path.join(fm, doc + ".content")
    c = _read(cpath)
    for k in READING:
        if k in tc:
            c[k] = tc[k]
    n = int(tc.get("pageCount") or 0)
    pages = (c.get("cPages") or {}).get("pages") or []
    if n > len(pages):
        idxv = pages[-1]["idx"]["value"] if pages else "ba"
        for i in range(len(pages), n):
            idxv = library.next_idx(idxv)
            pages.append({"id": str(uuid.uuid4()), "idx": {"timestamp": "1:2", "value": idxv},
                          "redir": {"timestamp": "1:2", "value": i}, "template": {"timestamp": "1:2", "value": "Blank"}})
        c["cPages"]["pages"] = pages
        c["pageCount"] = len([p for p in pages if "deleted" not in p])
        paths.write_atomic(os.path.join(fm, doc + ".pagedata"), "Blank\n" * c["pageCount"])
    paths.write_atomic(os.path.join(fm, doc + ".pdf"), pdf)
    paths.write_json_atomic(cpath, c)


def tick():
    """One look: send what waits to be sent, bring back what the tablet has converted. -> what it did."""
    from .. import settings as S
    s = S.load()
    if not on(s):
        return {}
    from . import sync
    fm = paths.false_mirror_dir()
    ignore = S.fixed_tags(s)[0]
    books = waiting()
    did = {"sent": [], "back": [], "errors": []}
    for doc in _books(fm):
        if doc in books:
            continue
        try:
            books[doc] = {"tablet": _send(fm, doc, ignore), "sent": int(time.time())}
            did["sent"].append(doc)
        except Exception as ex:
            did["errors"].append("%s: %s" % (doc[:8], str(ex)[:160]))
        _save(books)
    for doc, w in list(books.items()):
        tid = w.get("tablet")
        if not os.path.exists(os.path.join(fm, doc + ".epub")):
            # the book left the false mirror before the tablet converted it: the tablet's copy goes too
            try:
                sync.delete_doc(tid)
            except Exception as ex:
                did["errors"].append("%s: %s" % (doc[:8], str(ex)[:160]))
                continue
            books.pop(doc)
            _save(books)
            continue
        if not os.path.exists(os.path.join(sync.MIRROR, tid + ".metadata")):
            books.pop(doc)                             # the copy left the tablet's library (deleted there): sent again
            _save(books)
            continue
        if not os.path.exists(os.path.join(sync.MIRROR, tid + ".pdf")):
            continue                                   # not converted yet: the tablet has not synced it
        try:
            _bring_back(fm, doc, tid)
            sync.delete_doc(tid)
            books.pop(doc)
            did["back"].append(doc)
        except Exception as ex:
            did["errors"].append("%s: %s" % (doc[:8], str(ex)[:160]))
        _save(books)
    return did
