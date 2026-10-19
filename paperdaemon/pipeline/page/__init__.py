r"""A page snapshot: what was on it, where, and under what anchor.

Two problems this exists to solve:

1. **Typed text pushes strokes around.** Strokes on a page with typed text are
   not loose on Layer 1 -- the app files them into anonymous groups, each with
   an `anchor_id` pointing at a CHARACTER POSITION in the text, plus
   `anchor_type` and `anchor_origin_x`. When the text reflows, the anchor
   character moves and every stroke in that group moves with it. One measured
   page has 24 such groups and only 2 of 1013 strokes directly on Layer 1.

   Worse, `write_rm` without `keep_existing` re-emits every stroke parented to
   Layer 1, which DE-ANCHORS all of them. So a careless write can itself be
   what moves things.

2. **You cannot fix what you cannot measure.** Snapshot before an operation,
   compare after, and a stroke that moved when it should not have is a
   two-line correction instead of an argument.

The stroke signature is TRANSLATION-INVARIANT on purpose: it hashes the deltas
between consecutive points, not the points. So the same stroke still matches
after it has been moved, and the offset falls out of comparing positions.
"""
import hashlib
import io
import json
import logging
import os
from paperdaemon import paths
import shutil
import sys
import time
from paperdaemon.pipeline.page import render as R
from rmscene import read_blocks, write_blocks
from rmscene import scene_stream as ss
from rmscene.crdt_sequence import CrdtSequenceItem
from rmscene.scene_stream import CrdtId
from rmscene.scene_items import Line

logging.getLogger("rmscene").setLevel(logging.ERROR)
from paperdaemon.pipeline.page import render as R
from rmscene import read_blocks
from rmscene import scene_stream as ss
from rmscene.scene_items import Line


def _sig(line):
    """Translation-invariant fingerprint of one stroke."""
    h = hashlib.sha256()
    h.update(("%s|%s|%s|%d|" % (
        getattr(line.tool, "value", line.tool),
        getattr(line.color, "value", line.color),
        line.color_rgba, len(line.points))).encode())
    pts = line.points
    for a, b in zip(pts, pts[1:]):
        h.update(("%.1f,%.1f;" % (b.x - a.x, b.y - a.y)).encode())
    return h.hexdigest()[:16]


def skey(line):
    """Signature PLUS position: the identity of one stroke ON THIS PAGE, for erasing and hiding.

    `_sig` alone is translation-invariant, so every identical glyph on a page shares it -- erasing
    "pear" by signature took the matching letters out of "apple" and "plum".
    Raw first-point coordinates are the same whether the stroke is read for a preview or for the
    erase, so the key is stable within a job; it is NOT meant to survive the app re-anchoring the
    page, which is what `_sig` is for. A stroke read where the tablet draws it (render.strokes moves an anchored
    group's strokes onto the page) carries the key of its stored self, so it still names the stroke in the file.
    """
    stored = getattr(line, "_stored_key", None)
    if stored:
        return stored
    pts = getattr(line, "points", None)
    if not pts:
        return _sig(line)
    return "%s@%d,%d" % (_sig(line), round(pts[0].x), round(pts[0].y))


def snapshot(doc_name, page_no):
    """Every stroke: signature, position, extent, parent group, anchor."""
    doc = R.find_doc(doc_name) if "-" not in doc_name else doc_name
    pid = R.live_pages(doc)[page_no - 1]["id"]
    path = os.path.join(R.RM, doc, pid + ".rm")

    groups = {}
    strokes = []
    # positions WHERE THE TABLET DRAWS them (a text-anchored group is stored offset from the page); `raw_bbox` is
    # the box as stored
    blocks = R.blocks_of(path)
    shifts = R._anchor_offsets(doc, page_no, blocks)
    for b in blocks:                                  # cached parse, read only
        if isinstance(b, ss.TreeNodeBlock):
            g = b.group
            groups[str(g.node_id)] = {
                "label": getattr(g.label, "value", ""),
                "anchor_id": str(getattr(getattr(g, "anchor_id", None), "value", "")),
                "anchor_type": getattr(getattr(g, "anchor_type", None), "value", None),
                "anchor_origin_x": getattr(
                    getattr(g, "anchor_origin_x", None), "value", None),
            }
        elif isinstance(b, ss.SceneLineItemBlock):
            v = getattr(b.item, "value", None)
            if not isinstance(v, Line):
                continue                      # tombstone from an erased stroke
            dx, dy = shifts.get(b.parent_id) or (0.0, 0.0)
            rx = [p.x for p in v.points]
            ry = [p.y for p in v.points]
            xs = [x + dx for x in rx]
            ys = [y + dy for y in ry]
            strokes.append({
                "sig": _sig(v),
                "item_id": str(b.item.item_id),
                "parent": str(b.parent_id),
                "tool": getattr(v.tool, "name", str(v.tool)),
                "color": getattr(v.color, "name", str(v.color)),
                "rgba": list(v.color_rgba) if v.color_rgba else None,
                "n": len(v.points),
                "x": xs[0] if xs else 0.0, "y": ys[0] if ys else 0.0,
                "bbox": [min(xs), min(ys), max(xs), max(ys)] if xs else None,
                "raw_bbox": [min(rx), min(ry), max(rx), max(ry)] if rx else None,
                "width": v.points[0].width if v.points else None,
            })
    return {"doc": doc, "doc_name": doc_name, "page": page_no, "pid": pid,
            "groups": groups, "strokes": strokes,
            "sha": hashlib.sha256(open(path, "rb").read()).hexdigest()[:16]}


def save(snap, path):
    with io.open(path, "w", encoding="utf-8") as f:
        json.dump(snap, f, indent=1)
    return path


def load(path):
    with io.open(path, encoding="utf-8") as f:
        return json.load(f)


def compare(before, after, tol=0.5):
    """What changed between two snapshots.

    Matching is by signature, so a stroke that only MOVED is reported as moved
    (with its offset) rather than as one removal plus one addition.
    """
    def index(snap):
        d = {}
        for s in snap["strokes"]:
            d.setdefault(s["sig"], []).append(s)
        return d

    bi, ai = index(before), index(after)
    moved, same, removed, added, reparented = [], [], [], [], []
    for sig, bs in bi.items():
        as_ = ai.get(sig, [])
        for i, b in enumerate(bs):
            if i < len(as_):
                a = as_[i]
                dx, dy = a["x"] - b["x"], a["y"] - b["y"]
                if abs(dx) > tol or abs(dy) > tol:
                    moved.append({"sig": sig, "dx": dx, "dy": dy,
                                  "from": [b["x"], b["y"]], "to": [a["x"], a["y"]],
                                  "tool": b["tool"]})
                else:
                    same.append(sig)
                if a["parent"] != b["parent"]:
                    reparented.append({"sig": sig, "from": b["parent"],
                                       "to": a["parent"]})
            else:
                removed.append(b)
    for sig, as_ in ai.items():
        extra = len(as_) - len(bi.get(sig, []))
        if extra > 0:
            added.extend(as_[-extra:])
    # How many of the "unmoved" strokes are ANCHORED? For those, equal raw
    # coordinates do NOT prove the device shows them in the same place -- the
    # app computes their position from the anchor at render time. Deleting
    # strokes from neighboring anchored groups can reflow the survivors while
    # every number in this file stays identical. That is exactly the mistake
    # this field exists to stop: a report of "745 unmoved" that was true about
    # the numbers and false about the page.
    anchored = 0
    for s in after["strokes"]:
        g = after["groups"].get(s["parent"], {})
        if g.get("anchor_type") is not None:
            anchored += 1
    return {"moved": moved, "unmoved": len(same), "removed": removed,
            "added": added, "reparented": reparented,
            "anchored_after": anchored,
            "device_verified": False,
            "n_before": len(before["strokes"]), "n_after": len(after["strokes"])}


def report(cmp_):
    out = ["strokes %d -> %d  |  unmoved %d  moved %d  added %d  removed %d"
           % (cmp_["n_before"], cmp_["n_after"], cmp_["unmoved"],
              len(cmp_["moved"]), len(cmp_["added"]), len(cmp_["removed"]))]
    if cmp_["reparented"]:
        out.append("REPARENTED %d strokes -- anchoring changed, they will move "
                   "with different text now" % len(cmp_["reparented"]))
    if cmp_.get("anchored_after"):
        out.append("CAUTION: %d strokes are in ANCHORED groups. 'unmoved' above "
                   "means their RAW COORDINATES are unchanged -- it does NOT "
                   "prove the device draws them in the same place. Anchored "
                   "position is computed at render time. Verify on the device."
                   % cmp_["anchored_after"])
    if cmp_["moved"]:
        deltas = {}
        for m in cmp_["moved"]:
            k = (round(m["dx"], 1), round(m["dy"], 1))
            deltas[k] = deltas.get(k, 0) + 1
        out.append("MOVED offsets (dx, dy) -> count:")
        for k, v in sorted(deltas.items(), key=lambda kv: -kv[1])[:8]:
            out.append("   %-18s %d strokes" % (str(k), v))
    return "\n".join(out)


# --------------------------------------------------------------- safe area
# THE ONE DEFINITION. rm_plan, rm_host and rm_refcard import this; nothing else may restate it.
# Page coordinates on the 1620x2160 Paper Pro sheet run x -810..810 (0 at the center), y 0..2160.
# The safe area is where content may be placed without sitting under the device's floating toolbar
# (a reply written at x=-718 was under it when the toolbar was docked on the left, 120 px in). It is
# x0, y0, x1, y1 on a 1620x2160 page: 10 px from the sides and the foot. The wide
# left margin was the tablet's controls, docked on the left; with the controls moved to the top the
# margin widens the usable space for charts, images, etc. to about 10 px from the edge.
# THE TOP IS THE TOOLBAR'S. Docked at the top it covers about the top 122 px of the page (95 px of a
# screen capture of the tablet taken at 0.78 scale), and content placed from y=100 -- pictures,
# calendars, the chess page -- began under it. TOP_MARGIN clears it with room to spare. Every kind of
# content takes its top from here (rm_plan, rm_host, the game pages, PDF documents); if the toolbar
# still covers ink, THIS is the number to change.
# MEASURED ON THE TABLET: the user drew a highlighter line whose top edge marks where the toolbar's
# zone ends -- y 115 (centered at 130, 30 wide). Text, replies and other ordinary content start there. Content
# that takes the whole screen (a coloring page) is not held to it: the screen is the page frame, y 0..2160.
TOP_MARGIN = 115.0


def safe_area(frame=(1620.0, 2160.0), fitted=False):
    """The safe area on a page of this frame (width, height): the same margins, scaled with the
    page's width. A PDF page is shown fitted to the screen as a notebook page is, so its margins
    fall where the notebook's do -- and a 157.5 x 210 mm PDF page is 1404 wide, where the notebook's
    x -800..800 ran ~100 past each side and its y 2150 ~280 past the foot.

    A TABLET'S OWN PAGE (tablets.TABLETS) is in that tablet's screen pixels, and a toolbar is the same size in the hand
    whatever the screen: its margins scale with the pixel density (a Paper Pro Move's 264 ppi against the Paper Pro's
    229), not with the width -- scaled by width, the Move's top would sit at 68, under its toolbar. Measured on the
    Paper Pro only; the others' are this scaling, not a measurement. `fitted`: a PDF page, shown fitted to the screen
    whatever its size -- scaled with the width, as above, even when its frame happens to equal a tablet's."""
    from paperdaemon.pipeline.page import tablets as TB
    fw, fh = float(frame[0]), float(frame[1])
    t = None if fitted else TB.of_frame(frame)
    s = t["ppi"] / float(TB.DEFAULT[3]) if t else fw / 1620.0
    return (-fw / 2.0 + 10.0 * s, TOP_MARGIN * s, fw / 2.0 - 10.0 * s, fh - 10.0 * s)


SAFE_AREA = safe_area()                # (-800, 115, 800, 2150) on the 1620 x 2160 notebook page



# ------------------------------------------------------------------- history
# A snapshot history, pruned past about 1 GiB.
#
# The reason it earns its keep: when an edit is reported to have moved an ANSWERS
# block, the only way to answer honestly was to dig ad-hoc backups out of
# rm-backups and diff them by hand. With a history that is one call. A snapshot
# is small (JSON, no point data -- signatures and bounding boxes), so the cap is
# generous and mostly protects against the .rm copies stored alongside.
HISTORY = os.path.join(paths.state_dir(), "rm-history")
HISTORY_CAP = int(os.environ.get("RM_HISTORY_CAP", str(1024 ** 3)))   # 1 GiB


def _hist_dir(snap):
    return os.path.join(HISTORY, "%s-p%02d" % (snap["doc"], snap["page"]))


def record(doc_name, page_no, note="", keep_rm=True):
    """Snapshot a page into the history. Returns the entry path.

    `keep_rm` also copies the raw .rm, which is what makes a real restore
    possible rather than just a diff. That copy is the bulk of the size, and
    the pruner drops oldest-first.
    """
    snap = snapshot(doc_name, page_no)
    snap["note"] = note
    snap["at"] = int(time.time())
    d = _hist_dir(snap)
    os.makedirs(d, exist_ok=True)
    stamp = time.strftime("%Y%m%d-%H%M%S", time.localtime(snap["at"]))
    base = os.path.join(d, stamp)
    save(snap, base + ".json")
    if keep_rm:
        src = os.path.join(R.RM, snap["doc"], snap["pid"] + ".rm")
        if os.path.exists(src):
            shutil.copy2(src, base + ".rm")
    prune()
    return base


def entries(doc_name=None, page_no=None):
    """History newest-first: [{at, path, note, strokes, sha}]."""
    out = []
    if not os.path.isdir(HISTORY):
        return out
    want = None
    if doc_name is not None:
        doc = R.find_doc(doc_name) if "-" not in doc_name else doc_name
        want = "%s-p%02d" % (doc, page_no) if page_no else doc
    for sub in os.listdir(HISTORY):
        if want and not sub.startswith(want):
            continue
        for f in os.listdir(os.path.join(HISTORY, sub)):
            # provenance.json lives in the same directory but is NOT a
            # snapshot -- it is the record of which strokes are mine. Listing
            # it as history handed callers an entry with no strokes and a path
            # that `load` could not open.
            # pictures.json is the placement record of the page's pictures (rm_images), not a
            # snapshot either -- listed here, prune() deleted it as "the oldest entry" and every
            # picture the host had placed lost its position and its spec
            if not f.endswith(".json") or f in ("provenance.json", "pictures.json"):
                continue
            p = os.path.join(HISTORY, sub, f)
            try:
                s = load(p)
            except Exception:
                continue
            out.append({"at": s.get("at", 0), "path": p[:-5], "json": p,
                        "note": s.get("note", ""),
                        "strokes": len(s.get("strokes", [])), "sha": s.get("sha"),
                        "doc_name": s.get("doc_name"), "page": s.get("page")})
    return sorted(out, key=lambda e: -e["at"])


def history_size():
    total = 0
    for root, _, files in os.walk(HISTORY):
        for f in files:
            try:
                total += os.path.getsize(os.path.join(root, f))
            except OSError:
                pass
    return total


def prune(cap=None):
    """Drop the OLDEST entries until the history fits under the cap.

    Oldest-first, and the .json goes with its .rm so an entry is never half
    present. Always keeps the newest entry per page, however big it is --
    running out of budget must not leave a page with no history at all.
    """
    cap = cap or HISTORY_CAP
    if history_size() <= cap:
        return 0
    all_e = entries()
    newest_per_page = {}
    for e in all_e:
        k = (e["doc_name"], e["page"])
        if k not in newest_per_page:
            newest_per_page[k] = e["path"]
    dropped = 0
    for e in sorted(all_e, key=lambda e: e["at"]):
        if history_size() <= cap:
            break
        if e["path"] in newest_per_page.values():
            continue
        for ext in (".json", ".rm"):
            try:
                os.remove(e["path"] + ext)
            except OSError:
                pass
        dropped += 1
    return dropped


def restore(entry_path, doc_name=None, page_no=None):
    """Put a historical .rm back. Snapshots the CURRENT state first, so an
    undo is always undoable."""
    snap = load(entry_path + ".json")
    src = entry_path + ".rm"
    if not os.path.exists(src):
        raise RuntimeError("no .rm kept for %s -- diff only" % entry_path)
    dst = os.path.join(R.RM, snap["doc"], snap["pid"] + ".rm")
    record(snap["doc_name"], snap["page"], note="auto: before restore of %s"
           % os.path.basename(entry_path))
    with open(src, "rb") as f:
        paths.write_atomic(dst, f.read())            # whole or not at all: never half a page in the mirror
    return dst


# --------------------------------------------------------------- provenance
# Drawing and reading feel like the same problem, so the
# solved libraries ought to help read a page back.
#
# The experiment says half-yes. Matching a stroke against rm_text's glyph
# outlines gives error 0.00 -- the geometry is preserved EXACTLY. What defeats
# recovery is SEGMENTATION: knowing which strokes form one glyph. That is the
# hard part of handwriting recognition and it does not get easier just because
# the system drew it.
#
# But the whole exercise is backwards. At WRITE time the system knows precisely what it
# put down and what it said. Recovering it later is solving a hard problem to
# recover information that was thrown away. So record it instead.
#
# The signature is translation-invariant, which is what makes this survive the
# app: re-anchoring MOVES strokes, and a recorded signature still matches.
def record_provenance(doc_name, page_no, strokes=None, what="", kind="text",
                      since=None, only=None):
    """Remember that these strokes are MINE, and what they were.

    Two ways to say which strokes, and they are not equally good:

    `since` -- a snapshot() taken BEFORE the write. Everything now on the page
    that was not there before is recorded, with the signatures read off the
    PAGE. Prefer this. It cannot drift from what a later whose() will compute,
    because it is the same bytes. `only(stroke_dict)` narrows it to some of them -- one step's
    strokes of a job that made several things, each recorded with its own `what`.

    `strokes` -- what you were about to write, either `Drawing.strokes` tuples
    or bare point-lists. _sig() covers TOOL and COLOR, so a bare point-list is
    assumed FINELINER_2/BLACK and every HIGHLIGHTER stroke passed that way gets
    a signature that can never match the page: color fills then read as
    "unknown" forever, which is the exact failure this function exists to
    prevent. Reconstructing a Line also re-rounds the coordinates, so a few
    strokes per hundred miss even when the tool is right. Measured on the
    General cover: 426 written, 80 of them highlighter -> 89 unknown.
    """
    snap = snapshot(doc_name, page_no)
    from rmscene.scene_items import Line, Point, Pen, PenColor
    sigs = []
    if since is not None:
        had = set()
        for s in since["strokes"]:
            had.add(s["sig"])
        sigs = [s["sig"] for s in snap["strokes"] if s["sig"] not in had and (only is None or only(s))]
    for s in (strokes or []):
        tool, color, rgba = Pen.FINELINER_2, PenColor.BLACK, None
        pts = s
        # A Drawing.strokes tuple is (pts, widths, tool, color, rgba). A bare
        # 5-POINT polyline is also length 5, so discriminate on the shape of
        # the first element, not on len().
        if (isinstance(s, (tuple, list)) and len(s) == 5
                and isinstance(s[0], (tuple, list)) and s[0]
                and isinstance(s[0][0], (tuple, list))):
            pts, _widths, tool, color, rgba = s
        P = [Point(x=float(x), y=float(y), speed=0, direction=0, width=12,
                   pressure=190) for x, y in pts]
        sigs.append(_sig(Line(color=color, tool=tool,
                              points=P, thickness_scale=3.0,
                              starting_length=0.0, move_id=None,
                              color_rgba=(tuple(rgba) + (255,) if rgba else None))))
    d = _hist_dir(snap)
    os.makedirs(d, exist_ok=True)
    path = os.path.join(d, "provenance.json")
    try:
        rec = json.load(io.open(path, encoding="utf-8"))
    except Exception:
        rec = {"mine": {}}
    for s in sigs:
        rec["mine"][s] = {"what": what, "kind": kind, "at": int(time.time())}
    io.open(path, "w", encoding="utf-8").write(json.dumps(rec, indent=1))
    return len(sigs)


def whose(doc_name, page_no):
    """Split the page into {mine, theirs} by RECORDED provenance.

    Exact where a record exists. Everything else is reported as unknown rather
    than guessed -- a width or group heuristic nearly deleted the user's own
    writing once, and 'unknown' is the honest answer for strokes written before this
    existed.
    """
    snap = snapshot(doc_name, page_no)
    d = _hist_dir(snap)
    try:
        rec = json.load(io.open(os.path.join(d, "provenance.json"), encoding="utf-8"))
    except Exception:
        rec = {"mine": {}}
    mine, unknown = [], []
    for s in snap["strokes"]:
        (mine if s["sig"] in rec["mine"] else unknown).append(s)
    return {"mine": mine, "unknown": unknown,
            "recorded": len(rec["mine"]),
            "note": ("no provenance recorded for this page yet"
                     if not rec["mine"] else "")}



# ==================================================================================================
# Erase strokes the way the DEVICE erases them: tombstone, never remove.
#
# A hand-rolled erase loop is exactly the situation where the tempting shortcut
# (drop the `SceneLineItemBlock`) gets taken by accident, so the recipe lives here.
#
# Why tombstoning and not dropping: a stroke is an item in a CRDT sequence, and
# its neighbors reference it by `left_id`/`right_id`. Remove the block and those
# links dangle, which leaves the app free to re-lay-out whatever is left.
# Measured on a real page: dropping 147 stroke blocks took dangling
# `left_id` refs from 7 to 9, while tombstoning the same 147 left it at 7. The
# device's own convention is the same -- that page already held 138 device-written
# tombstones before any of this ran.
#
# A tombstone keeps `item_id`, `left_id`, `right_id` and the parent, sets
# `deleted_length=1`, and drops only the `value`.
#
#     import rm_erase as E
#     E.erase("Notebook", 15, lambda L: L.points[0].width == 24)
# ==================================================================================================

def _page_path(doc_name, page_no):
    doc = R.find_doc(doc_name) if "-" not in doc_name else doc_name
    pid = R.live_pages(doc)[page_no - 1]["id"]
    return os.path.join(R.RM, doc, pid + ".rm")


def erase(doc_name, page_no, kill, dry_run=False):
    """Tombstone every live stroke for which `kill(Line)` is true.

    Returns a dict with the counts, and refuses to write if the round trip
    does not show exactly the intended strokes gone, the block count
    unchanged, and any RootTextBlock still present.
    """
    src = _page_path(doc_name, page_no)
    allb = list(read_blocks(io.BytesIO(open(src, "rb").read())))

    out, hit = [], 0
    for b in allb:
        v = getattr(getattr(b, "item", None), "value", None)
        if isinstance(b, ss.SceneLineItemBlock) and isinstance(v, Line) and kill(v):
            it = b.item
            out.append(ss.SceneLineItemBlock(
                parent_id=b.parent_id,
                item=CrdtSequenceItem(item_id=it.item_id, left_id=it.left_id,
                                      right_id=it.right_id, deleted_length=1,
                                      value=None)))
            hit += 1
        else:
            out.append(b)

    live_before = sum(1 for b in allb if isinstance(b, ss.SceneLineItemBlock)
                      and isinstance(getattr(b.item, "value", None), Line))
    text_before = sum(1 for b in allb if isinstance(b, ss.RootTextBlock))

    buf = io.BytesIO()
    write_blocks(buf, out)
    data = buf.getvalue()

    rb = list(read_blocks(io.BytesIO(data)))
    live_after = sum(1 for b in rb if isinstance(b, ss.SceneLineItemBlock)
                     and isinstance(getattr(b.item, "value", None), Line))
    text_after = sum(1 for b in rb if isinstance(b, ss.RootTextBlock))

    if live_after != live_before - hit:
        raise RuntimeError("round trip: %d live strokes, expected %d"
                           % (live_after, live_before - hit))
    if len(rb) != len(allb):
        raise RuntimeError("block count changed: %d -> %d" % (len(allb), len(rb)))
    if text_after != text_before:
        raise RuntimeError("RootTextBlock count changed: %d -> %d"
                           % (text_before, text_after))

    res = dict(erased=hit, live_before=live_before, live_after=live_after,
               blocks=len(rb), bytes=len(data), path=src, written=False)
    if not dry_run:
        paths.write_atomic(src, data)
        res["written"] = True
    return res


_FOLD = {u"‘": "'", u"’": "'", u"“": '"', u"”": '"',
         u"–": "-", u"—": "-", u"…": "..."}


def _normalize(s):
    """Lowercase, fold the app's typographic characters, collapse whitespace.

    Returns (normalized, back) where `back[i]` is the index in `s` of the character that
    produced `normalized[i]` -- so a match found in the normalized copy can be turned back into
    a span of the real text.
    """
    out, back, space = [], [], False
    for i, ch in enumerate(s):
        if ch.isspace() or ch in u"   ":
            if space or not out:
                continue            # runs collapse; leading space is dropped
            out.append(" ")
            back.append(i)
            space = True
            continue
        space = False
        for c in _FOLD.get(ch, ch).lower():
            out.append(c)
            back.append(i)
    while out and out[-1] == " ":   # and so is a trailing one
        out.pop()
        back.pop()
    return "".join(out), back


def erase_text(doc_name, page_no, keep=None, contains=None, dry_run=False, data=None):
    """Tombstone typed text in the RootTextBlock, the way the device does.

    Typed text is a CRDT sequence exactly like strokes are, and it tombstones
    the same way: keep `item_id`, `left_id`, `right_id`, blank the `value` and
    set `deleted_length` to the character count. `sequence_items()` hides
    tombstones, so the raw dict `tb.items._items` is what has to be walked --
    a page will normally already hold several device-written text tombstones
    and this matches that convention.

    `keep(text)` -> True protects an item, evaluated PER RAW ITEM. That is fine for "keep
    everything" (`keep=None` erases every live item) but wrong for finding a phrase: a
    CrdtSequenceItem is one edit run, not one paragraph. `rm_host.seed()`/bench text is typed
    in one shot and lands as a single item, so a substring check against `it.value` alone
    happened to work there -- and then did NOTHING on a real device-typed page, where the same
    paragraph is ordinarily split across several small items from separate keystrokes or edits.
    The staging check in `t_erase_typed_text` uses `rm_typed.paragraphs()`, which assembles the
    full text first; this walked per-item, so it silently disagreed with what it had just told
    the model was staged.

    `contains="..."` fixes that: match against the WHOLE assembled live text of the block, then
    tombstone every item whose span overlaps a match, however many items the phrase crosses.

    Typed text is the user's. Erase it when asked, not as tidying.

    `data` starts from those bytes instead of the page's file (so erasures can be chained in a dry run); a dry
    run returns its result as `data`.
    """
    src = _page_path(doc_name, page_no)
    allb = list(read_blocks(io.BytesIO(data if data is not None else open(src, "rb").read())))

    hit = chars = 0
    for b in allb:
        if not isinstance(b, ss.RootTextBlock):
            continue
        items = b.value.items._items
        hit_ids = None
        if contains is not None:
            # Dict order == file order == document order, the same assumption rm_typed's own
            # paragraph assembly already makes for this file format.
            live = [(cid, it) for cid, it in items.items()
                    if isinstance(it.value, str) and it.value and not it.deleted_length]    # bold/italic marks are numbers
            full, offsets, pos = [], [], 0
            for cid, it in live:
                offsets.append((cid, pos, pos + len(it.value)))
                full.append(it.value)
                pos += len(it.value)
            # MATCH THE WAY A READER READS, not the way the bytes fell. The needle comes from
            # the model quoting text it saw rendered, so it will not carry the block's newlines,
            # U+2028 separators, doubled spaces or the app's curly quotes. Matching raw meant a
            # phrase that plainly IS on the page matched nothing, the erase came off as a silent
            # no-op, and the instruction stayed put. So search a normalized
            # copy and map the hits back to real offsets.
            full = "".join(full)
            norm, back = _normalize(full)
            needle, _ = _normalize(contains)
            spans, start = [], 0
            while needle:
                i = norm.find(needle, start)
                if i < 0:
                    break
                # back[] holds the ORIGINAL index of each normalized character, so the end of
                # the span is one past the last matched character's original index.
                spans.append((back[i], back[i + len(needle) - 1] + 1))
                start = i + 1
            # A PARAGRAPH GOES WITH THE NEWLINE IN FRONT OF IT (its style is keyed to that newline),
            # so no empty line is left where it was
            spans = [(a_ - 1 if a_ > 0 and full[a_ - 1] == "\n" else a_, b_) for a_, b_ in spans]
            # EXACTLY THE MATCHED CHARACTERS, never a whole item. An item is one edit RUN, not one
            # paragraph: typed in one go, five paragraphs were a single item, and erasing the last
            # one -- the request -- as a whole item took the four paragraphs of notes above it with
            # it. An item a match only partly covers is split into runs
            # the way the device writes a deletion: character ids are implicit (item_id + offset),
            # each run's left is the character before it, and every run keeps the item's right.
            rebuilt, touched = {}, False
            spans_of = {}
            for cid, s, e in offsets:
                cut = sorted((max(a_, s) - s, min(b_, e) - s) for a_, b_ in spans if a_ < e and s < b_)
                if cut:
                    spans_of[cid] = cut
            for cid, it in items.items():
                cut = spans_of.get(cid)
                if not cut:
                    rebuilt[cid] = it
                    continue
                touched = True
                marks, merged = [], []
                for a_, b_ in cut:                          # overlapping matches -> one range
                    if merged and a_ <= merged[-1][1]:
                        merged[-1] = (merged[-1][0], max(merged[-1][1], b_))
                    else:
                        merged.append((a_, b_))
                pos_ = 0
                for a_, b_ in merged:
                    if a_ > pos_:
                        marks.append((pos_, a_, False))
                    marks.append((a_, b_, True))
                    pos_ = b_
                if pos_ < len(it.value):
                    marks.append((pos_, len(it.value), False))
                p1, p2 = it.item_id.part1, it.item_id.part2
                for s_, e_, gone in marks:
                    nid = CrdtId(p1, p2 + s_)
                    left = it.left_id if s_ == 0 else CrdtId(p1, p2 + s_ - 1)
                    rebuilt[nid] = CrdtSequenceItem(
                        item_id=nid, left_id=left, right_id=it.right_id,
                        deleted_length=(e_ - s_) if gone else 0,
                        value="" if gone else it.value[s_:e_])
                    if gone:
                        hit += 1
                        chars += e_ - s_
            if touched:
                items.clear()
                items.update(rebuilt)
            continue                                        # this block is done
        for cid, it in list(items.items()):
            if not isinstance(it.value, str) or not it.value or it.deleted_length:   # a bold/italic mark stays
                continue
            if hit_ids is not None:
                if cid not in hit_ids:
                    continue
            elif keep and keep(it.value):
                continue
            items[cid] = CrdtSequenceItem(
                item_id=it.item_id, left_id=it.left_id, right_id=it.right_id,
                deleted_length=len(it.value), value="")
            hit += 1
            chars += len(it.value)

    buf = io.BytesIO()
    write_blocks(buf, allb)
    data = buf.getvalue()

    rb = list(read_blocks(io.BytesIO(data)))
    if len(rb) != len(allb):
        raise RuntimeError("block count changed: %d -> %d" % (len(allb), len(rb)))
    live = 0
    for b in rb:
        if isinstance(b, ss.RootTextBlock):
            live += sum(1 for it in b.value.items._items.values()
                        if it.value and not it.deleted_length)
    # This guards the "erase everything" call (keep=None, contains=None) only -- it asserted on
    # `keep is None` alone, which used to mean the same thing but no longer does now that
    # `contains` can make a correct, SELECTIVE erase while leaving `keep` unset.
    if keep is None and contains is None and live:
        raise RuntimeError("%d text items still live after erase" % live)

    res = dict(items=hit, chars=chars, live_text_after=live,
               blocks=len(rb), bytes=len(data), path=src, written=False)
    if not dry_run:
        paths.write_atomic(src, data)
        res["written"] = True
    else:
        res["data"] = data
    return res
