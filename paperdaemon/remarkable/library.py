r"""Folders on the tablet: find or make one, and file a document into it.

A folder in the cloud is a single `.metadata` of type CollectionType; a document
is in a folder when its own `.metadata` names that folder as `parent`. So making
a folder is one new item and moving a document is one changed file. Nothing else
about the document changes -- its pages, ink and PDF are not touched.

Both are written to the mirror only; they reach the tablet with the next push
(sync.push_pending), the one way anything does.

    f = ensure_path("Projects/Reports/2026/09 September")
    move(doc_uuid, f)
"""
import glob
from paperdaemon.remarkable import sync as RC
import io
from paperdaemon import paths
import json
import os
import sys
import time
import uuid
from paperdaemon.pipeline.page import render as R
from rmscene import read_blocks, write_blocks
from rmscene import scene_stream as ss

M = RC.MIRROR


def _meta(u):
    try:
        return json.load(open(os.path.join(M, u + ".metadata"), encoding="utf-8"))
    except Exception:
        return None


def items():
    """uuid -> metadata, for everything in the mirror that is not in the trash."""
    out = {}
    for f in glob.glob(os.path.join(M, "*.metadata")):
        u = os.path.basename(f)[:-9]
        m = _meta(u)
        if m and m.get("parent") != "trash" and not m.get("deleted"):
            out[u] = m
    return out


def children(parent, kind=None):
    return {u: m for u, m in items().items()
            if m.get("parent", "") == parent and (kind is None or m.get("type") == kind)}


def ensure_folder(name, parent=""):
    """The folder called `name` directly inside `parent`, made if missing."""
    for u, m in children(parent, "CollectionType").items():
        if m.get("visibleName") == name:
            return u
    u = str(uuid.uuid4())
    now = str(int(time.time() * 1000))
    md = {"createdTime": now, "lastModified": now, "new": False,
          "parent": parent, "pinned": False, "source": "",
          "type": "CollectionType", "visibleName": name}
    paths.write_json_atomic(os.path.join(M, u + ".metadata"), md)
    return u                           # in the mirror; it reaches the tablet with the next push (sync.push_pending)


def ensure_path(path):
    """'Projects/Reports/2026' -> uuid of the last folder, making any that are missing.
    The leading parts must already exist or are made too; names match exactly."""
    parent = ""
    for part in [p for p in path.split("/") if p]:
        parent = ensure_folder(part, parent)
    return parent


def move(doc, folder):
    """File `doc` into `folder`, in the mirror; the move reaches the tablet with the next push (sync.push_pending).
    -> True when it moved."""
    path = os.path.join(M, doc + ".metadata")
    md = json.load(open(path, encoding="utf-8"))
    if md.get("parent") == folder:
        return False
    md["parent"] = folder
    md["lastModified"] = str(int(time.time() * 1000))
    paths.write_json_atomic(path, md)
    return True


# ==================================================================================================
# Append blank pages to a reMarkable notebook at the file level.
#
# The desktop app's own New Page control is the safest route, but it needs the
# GUI, which must not be hand-driven. This implements the recipe derived by
# diffing `.content` before/after the app did it:
#
#   * a new `<uuid>.rm` holding only the structural blocks
#   * `cPages.pages` gains {id, idx{timestamp,value}, modifed, template{..}}
#   * `pageCount` += 1, `sizeInBytes` updated
#
# Two things the recipe warns about, both handled here:
#
#   * `idx.value` is a FRACTIONAL ORDERING KEY, not an index. It must sort after
#     the previous page's key. Observed alphabet:
#     ba..bz then ca..cb.., i.e. carry into the preceding character, plus
#     interpolations like 'brb' inserted between 'br' and 'bs'.
#   * `cPages.uuids` is a CRDT author table and the app RENUMBERS references into
#     it (a document's page timestamps moved 1:2 -> 2:2 while this ran). So
#     never hardcode a timestamp: copy whatever the current last page uses.
#
# The structural template is taken from a real page in the same document, so the
# new pages inherit that document's paper size from its SceneInfo rather than a
# guessed one.
# ==================================================================================================

# Blocks that carry page CONTENT rather than page structure.
# SceneTombstoneItemBlock belongs here too: it is the residue of erased
# content, so a page used as a blank template must shed it. Left out, it fell
# through to the STRUCTURAL check and aborted the whole add on any template
# page that had ever had something erased.
# UnreadableBlock is content too: rmscene 0.8 reads a placed PICTURE (block types 14 and 15, see
# rm_images) as one, so a notebook whose last page held a chart could not get a new page --
# "unexpected structural blocks: ['UnreadableBlock', 'UnreadableBlock']".
CONTENT_BLOCKS = tuple(
    b for b in (getattr(ss, n, None) for n in
                ("SceneLineItemBlock", "RootTextBlock", "SceneGlyphItemBlock",
                 "SceneTombstoneItemBlock", "UnreadableBlock"))
    if b is not None)

STRUCTURAL = ("AuthorIdsBlock", "MigrationInfoBlock", "PageInfoBlock",
              "SceneInfo", "SceneTreeBlock", "TreeNodeBlock",
              "SceneGroupItemBlock")


def blank_page_bytes(src_rm):
    """A structural-only page derived from an existing page of the same doc."""
    allb = list(read_blocks(io.BytesIO(open(src_rm, "rb").read())))
    blocks = [b for b in allb if not isinstance(b, CONTENT_BLOCKS)]
    names = [type(b).__name__ for b in blocks]
    unexpected = [n for n in names if n not in STRUCTURAL]
    if unexpected:
        raise RuntimeError("unexpected structural blocks: %r" % unexpected)
    if not any(isinstance(b, ss.TreeNodeBlock)
               and b.group.label.value == "Layer 1" for b in blocks):
        raise RuntimeError("template page has no 'Layer 1'")
    buf = io.BytesIO()
    write_blocks(buf, blocks)
    data = buf.getvalue()
    # must survive a round trip, and must still be a usable empty page
    rb = [type(b).__name__ for b in read_blocks(io.BytesIO(data))]
    if rb != names:
        raise RuntimeError("round trip changed blocks: %r != %r" % (rb, names))
    return data


def next_idx(prev):
    """Next fractional-ordering key after `prev`, carrying like ...bz -> ca."""
    ch = list(prev)
    i = len(ch) - 1
    while i >= 0:
        if ch[i] < "z":
            ch[i] = chr(ord(ch[i]) + 1)
            out = "".join(ch)
            break
        ch[i] = "a"
        i -= 1
    else:
        out = "a" + "".join(ch)
    if not out > prev:
        raise RuntimeError("idx %r does not sort after %r" % (out, prev))
    return out


def key_between(a, b=None):
    """An ordering key strictly after `a` and before `b` (no upper bound when b is None). The app orders pages by
    plain string comparison of these keys, and makes keys of any length itself ('nna' < 'nnba' < 'nnbb'), so a key
    between two neighbors is a longer one when they leave no room. Never ends in 'a', so there is always room
    before it too."""
    if b is not None and not a < b:
        raise ValueError("idx %r is not before %r" % (a, b))
    if b is None:                            # after the last page: the next key, as the app appends
        try:
            return next_idx(a)
        except RuntimeError:                 # 'zz' has no next key of its length: a longer one
            pass
    out, i, bounded = [], 0, b is not None
    while True:
        ca = ord(a[i]) if i < len(a) else ord("a")
        cb = ord(b[i]) if bounded and i < len(b) else ord("z") + 1
        if bounded and i >= len(b):          # cannot happen: a < b and b is a prefix only when a is shorter
            raise ValueError("no key fits between %r and %r" % (a, b))
        if ca == cb:
            out.append(chr(ca))
            i += 1
            continue
        mid = (ca + cb) // 2
        if mid > ca:
            key = "".join(out) + chr(mid)
            if not (key > a and (b is None or key < b)):
                raise RuntimeError("idx %r does not fit between %r and %r" % (key, a, b))
            return key
        out.append(chr(ca))                  # the neighbors differ by one here: go one character deeper,
        i += 1                               # where everything after a's prefix is below b
        bounded = False


def keys_between(a, b, n):
    """`n` keys in order strictly between a and b (b None: after a), split evenly so they stay short."""
    if n <= 0:
        return []
    if b is None:
        out, k = [], a
        for _ in range(n):
            k = key_between(k, None)
            out.append(k)
        return out
    mid = key_between(a, b)
    left = (n - 1) // 2
    return keys_between(a, mid, left) + [mid] + keys_between(mid, b, n - 1 - left)


def insert_pages(doc, after_page_id, count, template_from=None):
    """`count` blank pages right AFTER the page `after_page_id`, the pages behind them moving down: each gets an
    ordering key between that page's and the next live page's, so no other page's key, id or file changes (a
    PDF's own pages keep their `redir`, so its links still land where they did). -> [(page id, idx)], in order."""
    cpath = os.path.join(R.RM, doc + ".content")
    c = json.load(open(cpath, encoding="utf-8"))
    pages = c["cPages"]["pages"]
    live = sorted((p for p in pages if not RC.page_deleted(p)), key=lambda p: p["idx"]["value"])
    at = next((i for i, p in enumerate(live) if p["id"] == after_page_id), None)
    if at is None:
        raise RuntimeError("page %s is not in the document" % after_page_id)
    lo = live[at]["idx"]["value"]
    hi = live[at + 1]["idx"]["value"] if at + 1 < len(live) else None
    src = template_from or live[at]["id"]
    template = blank_page_bytes(os.path.join(R.RM, doc, src + ".rm"))
    idx_ts = live[at]["idx"]["timestamp"]
    tpl = live[at].get("template") or next((q["template"] for q in live if "template" in q), None)
    added, new = [], []
    now = str(int(time.time() * 1000))
    for key in keys_between(lo, hi, count):
        pid = str(uuid.uuid4())
        added.append((pid, key))
        entry = {"id": pid, "idx": {"timestamp": idx_ts, "value": key}, "modifed": now}
        if tpl is not None:
            entry["template"] = dict(tpl)
        new.append(entry)
    # stored in the app's order, right after the page that asked (the app keeps the list sorted by key)
    at_raw = next(i for i, p in enumerate(pages) if p["id"] == after_page_id)
    pages[at_raw + 1:at_raw + 1] = new
    for pid, _ in added:
        paths.write_atomic(os.path.join(R.RM, doc, pid + ".rm"), template)
    c["pageCount"] = len([p for p in pages if not RC.page_deleted(p)])
    c["sizeInBytes"] = str(int(c.get("sizeInBytes") or 0) + len(template) * count)
    if os.path.exists(os.path.join(R.RM, doc + ".pagedata")):
        with open(os.path.join(R.RM, doc + ".pagedata"), "a") as f:
            f.write("Blank\n" * count)
    paths.write_atomic(cpath, json.dumps(c, indent=4, sort_keys=True))
    return added


def tag_page(doc, page_id, name):
    """Put the tag `name` on one page, in the notebook's .content -> True, or False if it already
    carries it. The caller pushes the document (after a job, the daemon does)."""
    path =os.path.join(R.RM, doc + ".content")
    c = json.load(open(path, encoding="utf-8"))
    tags = c.get("pageTags") or []
    if any(t.get("pageId") == page_id and str(t.get("name", "")).strip().lower() == name.lower() for t in tags):
        return False
    tags.append({"name": name, "pageId": page_id, "timestamp": int(time.time() * 1000)})
    c["pageTags"] = tags
    paths.write_atomic(path, json.dumps(c, indent=4))
    return True



def _later(c):
    """A timestamp later than every one the document holds ("author:counter", the tablet's 1 counted on): a deletion
    stamped 1:1 lost to the tablet's own marker on a live page ({"timestamp": "1:2", "value": 0}) and was undone."""
    import re as _re
    n = max([int(b) for a, b in _re.findall(r'"timestamp": "(\d+):(\d+)"', json.dumps(c)) if a == "1"] or [1])
    return "1:%d" % (n + 1)


def delete_pages(doc_name, page_ids, dry_run=False):
    """Delete pages the way the app does: the `cPages.pages` entry STAYS, marked
    `deleted: {timestamp, value: 1}`, its `.rm` goes, `pageCount` is the live count.

    Observed: a deleted entry keeps its id and idx and carries the
    marker; `live_pages()` skips it. Removing the entry outright would leave the app's
    CRDT with a reference it never saw deleted. Meant for taking back blank pages that a
    test appended to a bench notebook, one per run.
    """
    doc = R.find_doc(doc_name) if "-" not in doc_name else doc_name
    cpath = os.path.join(R.RM, doc + ".content")
    c = json.load(open(cpath, encoding="utf-8"))
    want = set(page_ids)
    gone, missing = [], []
    for p in c["cPages"]["pages"]:
        if p["id"] in want and not RC.page_deleted(p):
            p["deleted"] = {"timestamp": _later(c), "value": 1}
            p["modifed"] = str(int(time.time() * 1000))
            gone.append(p["id"])
    missing = sorted(want - set(gone))
    live = [p for p in c["cPages"]["pages"] if not RC.page_deleted(p)]
    c["pageCount"] = len(live)
    if dry_run:
        return dict(deleted=gone, not_found=missing, written=False, page_count=c["pageCount"])
    for pid in gone:
        f = os.path.join(R.RM, doc, pid + ".rm")
        if os.path.exists(f):
            c["sizeInBytes"] = str(max(0, int(c.get("sizeInBytes") or 0) - os.path.getsize(f)))
            os.remove(f)
    paths.write_atomic(cpath, json.dumps(c, indent=4, sort_keys=True))
    return dict(deleted=gone, not_found=missing, written=True, page_count=c["pageCount"])
