"""Render a reMarkable .rm v6 page to PNG.

Model verified against the reMarkable desktop app:

  strokes      SceneLineItemBlock where item.value is a Line.
               item.value is None for erased/undone strokes -- they persist in
               the file. Block count != stroke count; always filter.

  width        Point.width is the tablet's own per-sample width. Use it; do not
               model width from pressure. FINELINER/HIGHLIGHTER are constant
               (ts*8 and ts*120); PAINTBRUSH varies and tapers at stroke ends.

  color       Highlighters carry Line.color_rgba as an (R,G,B,A) tuple,
               or, without one, their color in the Line.color enum (HL_ENUM).
               A highlighter with rgba has Line.color HIGHLIGHT, useless then. Other pens use the Line.color enum and
               have color_rgba == None. Palette values are little-endian: read
               the raw bytes forward and orange comes out pale blue.

  blending     Measured from the desktop app (screenshots): strokes
               composite in file order; pens are opaque; the highlighter is a
               per-channel MINIMUM ("darken") wash -- stacked colors are min() of
               the stack (all 63 combinations verified exactly), same color twice is
               itself, a pen under a wash becomes min(pen, wash), a pen drawn after
               covers. The older note below was wrong about overlaps:
               OLD: Highlighter is flat and opaque -- overlapping strokes do
               not darken, mix, or accumulate opacity (unlike a real
               highlighter). Later strokes simply cover earlier ones. Verified
               where green avocado meets yellow toast: sharp edge, no olive.

  layering     File order matters (later calibration). The
               decomposer deliberately emits washes before opaque ink.

  frame        Notebook pages are 1620x2160 with x centered on 0 and y starting
               at 0. A PDF page is the PDF page itself at PDF_SCALE, centered
               the same way (page_frame). Ink outside the frame (x beyond
               +/-810, y negative) falls back to stroke extents.
"""
import collections, dataclasses, json, logging, math, os, random, threading
from PIL import Image, ImageChops, ImageDraw

from rmscene import read_blocks
from rmscene import scene_stream as ss
from rmscene.scene_items import Line

from paperdaemon.remarkable.sync import MIRROR as _LIBRARY
RM = os.environ.get("RM_CACHE") or _LIBRARY
PAGE_W, PAGE_H = 1620, 2160
# A PDF PAGE'S INK IS AT A FIXED SCALE: 1404 page units to 157.5 mm (226.4 to the inch),
# whatever the PDF page's size, centered on x = 0 with the page's top at y = 0. It is NOT the PDF
# fitted into SceneInfo's paper_size, which says 1404x1872 on every PDF page. The two agree only on
# a 157.5 x 210 mm page -- the size of the first PDFs checked -- so fitting looked verified.
# Handwritten marks on 870 x 1160 pt pages settled it: at this scale all of them sit on the page and
# strikethroughs run through the lines they strike (the scale came out within 0.3% of this one);
# fitted, most of the ink lay off the page.
PDF_SCALE = 1404 / (157.5 / 25.4 * 72)       # page units per PDF point

# THE TABLET'S COLORS, read off its own pixels (the screen share of the calibration notebook): every
# PenColor drawn by a fineliner and a marker. The earlier table was the desktop app's, which mutes them (its blue was
# (48,74,224), the tablet's is (0,0,255)). 9 (HIGHLIGHT) is invisible as a fineliner; 2 is white.
ENUM = {0: (0, 0, 0), 1: (148, 146, 148), 2: (255, 255, 255), 3: (255, 239, 115),
        4: (173, 255, 132), 5: (247, 158, 255), 6: (0, 0, 255), 7: (255, 0, 0),
        8: (189, 190, 189), 9: (255, 255, 255), 10: (0, 255, 0), 11: (0, 255, 255),
        12: (255, 0, 255), 13: (255, 255, 0)}
# THE DECOMPOSER'S PALETTE, frozen: the colors it chooses between (rm_lean, rm_paint), as they were, so its output stays
ENUM_WRITER = {0: (0, 0, 0), 1: (144, 144, 144), 2: (255, 255, 255), 3: (254, 253, 96), 4: (169, 250, 92), 5: (255, 85, 207),
               6: (48, 74, 224), 7: (194, 49, 50), 8: (191, 191, 191), 9: (255, 255, 255), 10: (145, 218, 113),
               11: (116, 210, 232), 12: (192, 127, 210), 13: (250, 231, 25)}
# THE MARKER in 8 (GRAY_OVERLAP) and 9 (HIGHLIGHT) is black on the tablet, where the fineliner is light gray and nothing
PEN_ENUM = {"MARKER": {8: (0, 0, 0), 9: (0, 0, 0)}}
# A HIGHLIGHTER WITH NO color_rgba says its color in the Line.color enum, and the tablet washes it in the pens' own
# color of that name (measured: yellow, blue (0,0,255), pink, green, gray (148,146,148)); HIGHLIGHT without an rgba
# leaves nothing.
HL_ENUM = dict(ENUM)
# A SHADER WITH NO color_rgba (one the tablet never writes itself; our own pen tests did): black is solid, gray a mid
# gray that darkens where it is laid twice (measured 148 once, 107 twice: ink 82 at 0.62); any other its pen color.
SHADER_PLAIN = {0: (0, 0, 0, 255), 1: (82, 82, 82, 158)}

# highlighter's width field uses a wider internal unit than the pens
WSCALE = {"HIGHLIGHTER": 0.25}
# pencil and mechanical pencil are rendered by the tablet with a procedural paper
# grain that is NOT in the file: mechanical pencil's width field is constant while
# pressure varies 179..255, so pressure must drive grain/darkness, not width.
# Approximated here by stippling -- close enough to preview, not pixel-exact.
PENCIL_FAMILY = ("PENCIL", "MECHANICAL")
# A PEN'S WIDTH ON THE TABLET is its width field / 4 page units: measured on the calibration notebook through
# the tablet's screen share (1:1), every pen at thickness 1-3 -- fineliner, ballpoint and calligraphy exactly field / 4,
# the rest by paint.WIDER. It was 0.144 ("ts=3 -> 3.5 px"), and every pen line drawn here was 0.58 of the tablet's.
WSCALE_DEFAULT = 0.25
# THE WRITERS' SCALE, frozen: the width field PaperDaemon gives a pixel it wants drawn (the lettering, the decomposer's
# pens). Their output stays as it was, as it looks on the tablet; only what the renderer draws follows the tablet.
WSCALE_WRITER = 0.144


def _meta(doc):
    return json.load(open(os.path.join(RM, doc + ".metadata")))


def find_doc(name, include_trash=False):
    """Resolve a visibleName to a doc id. A doc id passes straight through.

    Half the toolkit takes a NAME and half takes a UUID, and the two are freely
    mixed in practice. Accepting both here is what stops that being a bug: it
    is why `content_bottom` silently fell back to typed-text-only and let two
    daemon footers land on the same baseline.

    Names are not unique (two notebooks can share one) and trashed documents keep
    their name, so skip parent=='trash' and prefer the most recently modified.
    """
    if name and "-" in name and os.path.exists(os.path.join(RM, name + ".metadata")):
        # A UUID USED TO PASS STRAIGHT THROUGH, TRASHED OR NOT. A trashed document should be treated
        # as gone by the daemon and the whole pipeline; the app manages its trash itself.
        # Resolution by name already skipped the trash; by id it did not, so a trashed document
        # stayed fully reachable to everything downstream.
        if not include_trash:
            try:
                m = json.load(open(os.path.join(RM, name + ".metadata")))
                if m.get("parent") == "trash" or m.get("deleted"):
                    return None
            except Exception:
                pass
        return name
    hits = []
    for f in os.listdir(RM):
        if not f.endswith(".metadata"):
            continue
        try:
            m = json.load(open(os.path.join(RM, f)))
        except Exception:
            continue
        if m.get("visibleName") != name or m.get("deleted"):
            continue
        if not include_trash and m.get("parent") == "trash":
            continue
        hits.append((int(m.get("lastModified", 0)), f[:-9]))
    if not hits:
        raise KeyError("no live document named %r" % name)
    hits.sort(reverse=True)
    if len(hits) > 1:
        print("  note: %d live docs named %r; using most recent (%s)"
              % (len(hits), name, hits[0][1]))
    return hits[0][1]


_BLOCKS = {}          # path -> ((mtime_ns, size), blocks)


def blocks_of(path, arrays=False):
    """The parsed blocks of a page file, cached by the file's (mtime, size). READ ONLY.

    One job parsed the same page about sixty times -- strokes for the render, again for the marks,
    again for the arrows, the typed text for the paragraphs, again for the collision boxes, again
    for the text bottom, a snapshot before the write, another after -- and rmscene's parse of a
    busy page is a second or more. Measured: 153 of 173 s of the host's own work was
    `read_blocks`. Every reader goes through here now; every WRITER (rm_erase, rm_typed.insert,
    rm_art.write_rm, rm_images.insert) still parses its own fresh copy, because it mutates what
    it parsed, and the write changes mtime and size, which is what invalidates this.
    """
    st = os.stat(path)
    key = (st.st_mtime_ns, st.st_size)
    hit = _BLOCKS.get((path, arrays))
    if hit is not None and hit[0] == key:
        return hit[1]
    with open(path, "rb") as f:
        data = f.read()
    # its strokes read straight from the bytes, block for block what rmscene reads (fastrm), in one C pass where it can
    # be: a page with a decomp was seconds of rmscene for every picture drawn. `arrays`: each stroke's points its
    # fastrm.POINT array as read (the renderer's, which draws from arrays); else si.Point objects, as rmscene makes them
    try:
        from paperdaemon.remarkable import fastrm
        blocks = fastrm.read_blocks_arrays(data) if arrays else fastrm.read_blocks_points(data)
    except Exception:
        import io
        blocks = list(read_blocks(io.BytesIO(data)))
    if len(_BLOCKS) >= 12:
        _BLOCKS.clear()
    _BLOCKS[(path, arrays)] = (key, blocks)
    return blocks


_OTHER = {}          # path -> ((mtime_ns, size), blocks)
_LINES = {}          # path -> ((mtime_ns, size), fastrm.page_lines(...))


# THE DAEMON'S NOTES: across the top of a page, under the tablet's toolbar (pipeline/daemon/notes.py). The renderer
# never draws them -- strokes() leaves them out, so nothing that reads a page for the host sees them -- and the page's
# fingerprint leaves them out too (ledger._content_sha), so a note can neither be read as the user's writing nor start
# a job. Only the page editor shows them (it reads the page itself: remarkable/local.scene_of).
# WHAT IS HIS: a stroke on a layer with his layer's name (Settings: daemon.layer) or the name his notes had before
# ("PaperDaemon") that a machine drew -- every point at the one pressure (190) with no speed and no direction, which no
# hand on the tablet makes. NOT the user's strokes on his layer: the tablet writes on whatever layer is current, and
# the user's writing has landed there. HE WRITES AS THE TABLET'S OWN AUTHOR (1): the tablet will not open a page that
# holds an item of any author it does not know -- his notes under an author of their own (218) left every page they
# were on unreadable there (measured 2026-10-25: those pages opened again once the 218 items were taken out). What is
# left of 218 on a page is his, and the next note takes it out of the file outright (notes._write).
DAEMON_LAYER = "Daemon"
DAEMON_LEGACY = "PaperDaemon"
DAEMON_AUTHOR = 218                  # the author his notes once had: anything under it is his, and goes
SYNTH_PRESSURE = 190                 # a machine-drawn point: this pressure, speed 0, direction 0 (notes, the host)
# WHAT A JOB WRITES (its strokes, typed text and pictures) IS NUMBERED AS THE TABLET'S OWN (author 1), after every id
# the page holds. An author of its own (219) was tried in 0.1.79 so that what the user adds on the tablet while a job
# runs could never take the same ids -- and a page of strokes under it would not open on the tablet. Until another
# author is proven on the device, the writers stay on 1 (the per-author counting stays, ready for one).
HOST_AUTHOR = 1
HOST_UUID = __import__("uuid").uuid5(__import__("uuid").NAMESPACE_DNS, "host.paperdaemon")
_NAME = {"key": None, "name": DAEMON_LAYER}


def daemon_layer_name():
    """The daemon's layer name, from the settings (read again only when the settings file changes)."""
    try:
        from paperdaemon import paths as _paths
        f = _paths.settings_file()
        st = os.stat(f)
        key = (f, st.st_mtime_ns, st.st_size)
    except OSError:
        return _NAME["name"]
    if _NAME["key"] != key:
        try:
            from paperdaemon import settings as S
            name = str(S._get_path(S.load(), "daemon.layer") or "").strip() or DAEMON_LAYER
        except Exception:
            name = DAEMON_LAYER
        _NAME.update(key=key, name=name)
    return _NAME["name"]


def daemon_layer_ids(blocks, names=None):
    """His layers on the page: named as his (`names`, else his layer's name and the old one), whoever made them, and
    any under his old author -> {(part1, part2)} of their node ids. Only the machine-drawn strokes on them are his
    (daemon_stroke)."""
    names = {daemon_layer_name(), DAEMON_LEGACY} if names is None else set(names)
    return {(b.group.node_id.part1, b.group.node_id.part2) for b in blocks
            if isinstance(b, ss.TreeNodeBlock) and (b.group.node_id.part1 == DAEMON_AUTHOR
                                                    or getattr(getattr(b.group, "label", None), "value", None) in names)}


def synthetic(points):
    """Were these points drawn by a machine: every one at SYNTH_PRESSURE, with speed 0 and direction 0 (a POINT array
    or rmscene Points)."""
    if points is None or not len(points):
        return False
    if hasattr(points, "dtype"):
        return bool((points["pressure"] == SYNTH_PRESSURE).all() and (points["speed"] == 0).all() and (points["direction"] == 0).all())
    return all(p.pressure == SYNTH_PRESSURE and p.speed == 0 and p.direction == 0 for p in points)


def daemon_stroke(author, parent, layers, drawn=None):
    """Is a stroke the daemon's: under his old author, or on one of his layers (daemon_layer_ids) and machine-drawn.
    `drawn`: whether its points are machine-drawn (synthetic), or a function that says so (asked only for a stroke
    on his layers); None where the caller cannot tell -- then a stroke on his layers counts as his."""
    if author == DAEMON_AUTHOR:
        return True
    if parent not in layers:
        return False
    if drawn is None:
        return True
    return bool(drawn() if callable(drawn) else drawn)


def _lines_of(path):
    """fastrm.page_lines for a page file, cached by its (mtime, size); None where the C reader is not sure of it."""
    st = os.stat(path)
    key = (st.st_mtime_ns, st.st_size)
    hit = _LINES.get(path)
    if hit is not None and hit[0] == key:
        return hit[1]
    try:
        from paperdaemon.remarkable import fastrm
        with open(path, "rb") as f:
            got = fastrm.page_lines(f.read())
    except Exception:
        got = None
    if len(_LINES) >= 6:
        _LINES.clear()
    _LINES[path] = (key, got)
    return got


def other_blocks_of(path):
    """The page's blocks OTHER THAN ITS STROKES (its typed text, groups and anchors, its settings, its pictures' blocks),
    cached by the file's (mtime, size) like blocks_of. READ ONLY. For the readers that need nothing else: the strokes
    are most of a busy page, and seconds to read for nothing."""
    st = os.stat(path)
    key = (st.st_mtime_ns, st.st_size)
    hit = _OTHER.get(path)
    if hit is not None and hit[0] == key:
        return hit[1]
    import io
    with open(path, "rb") as f:
        data = f.read()
    try:
        from paperdaemon.remarkable import fastrm
        data = fastrm.without_strokes(data)
    except Exception:
        pass
    blocks = [b for b in read_blocks(io.BytesIO(data)) if not isinstance(b, ss.SceneLineItemBlock)]
    if len(_OTHER) >= 24:
        _OTHER.clear()
    _OTHER[path] = (key, blocks)
    return blocks


def _joined(P):
    """Point arrays of one dtype joined into one, as raw bytes (numpy checks every structured array's fields when it
    joins them: a second for a page of a quarter of a million strokes); None when they are not all arrays of one dtype."""
    import numpy as _np
    if not P or not all(hasattr(p, "dtype") for p in P):
        return None
    dt = P[0].dtype
    if any(p.dtype != dt for p in P):
        return None
    return _np.concatenate([_np.ascontiguousarray(p).view(_np.uint8) for p in P]).view(dt)


def _lo_hi(arr, extra, lo):
    """min (lo) or max of an array's values and the extra numbers, as Python's min/max of them all would give."""
    vals = list(extra)
    if len(arr):
        vals.append(float(arr.min() if lo else arr.max()))
    return min(vals) if lo else max(vals)


def _coords(S, k):
    """Every point's x (k 0) or y (k 1) of strokes S as one float64 array, whether a stroke's points are si.Point
    objects or a point array (strokes(arrays=True)): the same numbers either way."""
    import numpy as _np
    J = _joined([L.points for L in S])
    if J is not None:
        return _np.asarray(J["xy"[k]], _np.float64)
    parts = []
    for L in S:
        P = L.points
        if hasattr(P, "dtype"):
            parts.append(_np.asarray(P["xy"[k]], _np.float64))
        elif len(P):
            parts.append(_np.array([p.x for p in P] if k == 0 else [p.y for p in P], _np.float64))
    return _np.concatenate(parts) if parts else _np.zeros(0)


def _ink(S, tx, ty):
    """Strokes S as the renderers draw them (paint.Flat), the whole page at once: each stroke of two points or more, in
    file order; its points moved by (tx, ty); its widths px_width's (the stored width times its pen's scale, a pixel at
    least), then the pen's response to its pressure and speed (paint.response: drawn() for pens and shaders, the
    density for pens); a pen's color by its color number, a highlighter's and a shader's by their own colors."""
    import numpy as _np
    from paperdaemon.pipeline.page.paint import Flat, drawn, response, KINDS
    keep = [L for L in S if len(L.points) >= 2]
    if not keep:
        return None
    counts = _np.fromiter((len(L.points) for L in keep), _np.int64, len(keep))
    A = _joined([L.points for L in keep])
    if A is not None:
        a = _np.empty((len(A), 5), _np.float64)
        for i, f in enumerate(("x", "y", "width", "pressure", "speed")):
            a[:, i] = A[f]
    else:
        a = _np.concatenate([_columns(L) for L in keep])
    names = [L.tool.name for L in keep]
    fams = [n.split("_")[0] for n in names]
    uniq = sorted(set(fams))
    fid = _np.array([uniq.index(f) for f in fams], _np.int64)
    fp = _np.repeat(fid, counts)
    scale = _np.array([WSCALE.get(f, WSCALE_DEFAULT) for f in uniq])
    widths = _np.maximum(1.0, a[:, 2] * scale[fp])
    k, dens = _np.ones(len(a)), _np.ones(len(a))
    for j, f in enumerate(uniq):
        m = fp == j
        k[m], dens[m] = response(f, a[m, 3], a[m, 4])
    kind = _np.array([KINDS["shader"] if n.startswith("SHADER") else KINDS["highlighter"] if n.startswith("HIGHLIGHTER")
                      else KINDS["pen"] for n in names], _np.int32)
    kp = _np.repeat(kind, counts)
    w = _np.where(kp == KINDS["highlighter"], widths, drawn(widths, k))
    # THE TABLET DRAWS NO PENCIL NARROWER THAN 2 UNITS (its screen share: width fields 3, 6 and 12 all drew 2 wide)
    least = _np.array([2.0 if f in PENCIL_FAMILY else 1.0 for f in uniq])[fp]
    w = _np.where((w > 0) & (kp == KINDS["pen"]), _np.maximum(w, least), w)
    d = _np.where(kp == KINDS["pen"], dens, 1.0)
    rgba = _np.empty((len(keep), 4), _np.uint8)
    for i, (L, n) in enumerate(zip(keep, names)):
        if n.startswith("SHADER"):
            c = tuple(L.color_rgba) if getattr(L, "color_rgba", None) else                 SHADER_PLAIN.get(L.color.value, ENUM.get(L.color.value, (0, 0, 0)) + (255,))
        elif n.startswith("HIGHLIGHTER"):
            c = tuple(L.color_rgba[:3]) if L.color_rgba else HL_ENUM.get(L.color.value, (255, 239, 115))
        else:
            c = PEN_ENUM.get(n.split("_")[0], {}).get(L.color.value) or ENUM.get(L.color.value, (0, 0, 0))
        rgba[i] = (list(c) + [255])[:4]
    xy = _np.ascontiguousarray(a[:, :2] + (tx, ty))
    return Flat(xy, _np.ascontiguousarray(w), _np.ascontiguousarray(d), counts.astype(_np.int32), kind, rgba)


def _columns(L):
    """A stroke's points as rows (x, y, width, pressure, speed), float64, from either form of its points."""
    import numpy as _np
    P = L.points
    if hasattr(P, "dtype"):
        a = _np.empty((len(P), 5), _np.float64)
        for i, f in enumerate(("x", "y", "width", "pressure", "speed")):
            a[:, i] = P[f]
        return a
    return _np.array([(p.x, p.y, p.width, p.pressure, p.speed) for p in P], _np.float64)


# A PAGE READ FROM ANOTHER FILE, in this process only: {(doc, page id): path}. The conflict job renders the copy of a
# page a job had made (set aside when the tablet's copy won) without writing anything into the mirror.
_PAGE_FILES = {}


def page_file(doc, pid):
    """The .rm file a page is read from: the mirror's, unless `reading()` points it elsewhere."""
    return _PAGE_FILES.get((doc, pid)) or os.path.join(RM, doc, pid + ".rm")


class reading:
    """`with reading(doc, pid, path):` reads that page from `path` (renders, typed text) for the block's length."""

    def __init__(self, doc, pid, path):
        self.k, self.path = (doc, pid), path

    def __enter__(self):
        _PAGE_FILES[self.k] = self.path
        return self

    def __exit__(self, *a):
        _PAGE_FILES.pop(self.k, None)
        return False


def live_pages(doc):
    """Pages the app will show. cPages includes deleted pages; they have no .rm."""
    from paperdaemon.remarkable.sync import live_pages as live
    with open(os.path.join(RM, doc + ".content"), encoding="utf-8") as f:
        return live(json.load(f))


def dead_ranges(blocks):
    """Id ranges a tombstone has deleted: (start, end) inclusive.

    A tombstone's `deleted_length` deletes N ids from its own, so anything
    allocated inside one is erased as far as the device is concerned.
    """
    out = []
    for b in blocks:
        if isinstance(b, ss.SceneLineItemBlock) and (b.item.deleted_length or 0) > 1:
            s = b.item.item_id.part2
            out.append((s, s + b.item.deleted_length - 1))
    return out


_TEXT_START, _TEXT_END = (1 << 48) - 2, (1 << 48) - 1     # a group's anchor at the start or the end of the text


def _anchor_offsets(doc, page_no, blocks):
    """Where the tablet draws each group anchored to the typed text: its node id -> (dx, dy), its ancestors'
    shifts included. A group anchored to the text moves across by its `anchor_origin_x` and down to its anchor:
    the text's top (anchored at its start), its bottom (at its end), or the paragraph whose newline it names."""
    own, parent = {}, {}
    for b in blocks:
        if isinstance(b, ss.TreeNodeBlock):
            g = b.group
            a = getattr(getattr(g, "anchor_id", None), "value", None)
            if a is not None:
                own[g.node_id] = (float(getattr(getattr(g, "anchor_origin_x", None), "value", 0.0) or 0.0), a)
        elif isinstance(b, ss.SceneGroupItemBlock):
            child = getattr(b.item, "value", None)
            if child is not None:
                parent[child] = b.parent_id
    if not own:
        return {}
    top, bottom, starts = 0.0, 0.0, {}
    try:
        from paperdaemon.pipeline.page import typed as _TY
        tb, paras = _TY.paragraphs(doc, page_no)
        top = float(tb.pos_y) if tb is not None else 0.0
        bottom = float(_TY.text_bottom(doc, page_no) or top)
        starts = {tuple(p["start_id"]): float(p["y"]) for p in paras if p.get("start_id") is not None and p.get("y") is not None}
    except Exception:
        pass

    # MEASURED where a recorded picture is anchored to the same place (images.measured_anchors): exact, where the
    # typed-text layout below is an estimate
    try:
        from paperdaemon.pipeline.page import images as _IM
        measured = _IM.measured_anchors(doc, page_no)
    except Exception:
        measured = {}

    def anchor_y(a):
        if (a.part1, a.part2) in measured:
            return measured[(a.part1, a.part2)]
        if a.part1 == 0 and a.part2 == _TEXT_START:
            return top
        if a.part1 == 0 and a.part2 == _TEXT_END:
            return bottom
        return starts.get((a.part1, a.part2 + 1), bottom)       # the newline ending the paragraph before

    out = {}

    def shift(node, depth=0):
        if node in out:
            return out[node]
        dx = dy = 0.0
        if node in own:
            dx, dy = own[node][0], anchor_y(own[node][1])
        up = parent.get(node)
        if up is not None and depth < 32:
            pdx, pdy = shift(up, depth + 1)
            dx, dy = dx + pdx, dy + pdy
        out[node] = (dx, dy)
        return out[node]
    for n in list(own) + list(parent):
        shift(n)
    return out


def strokes(doc, page_no, arrays=False):
    """Live strokes on a 1-based page number, as the app numbers them.

    EXCLUDES strokes whose id sits inside a deleted RANGE, because the device
    does. This function is the eyes of the whole system -- previews, collision
    checks, the model's own render() -- so it must agree with the device or it
    actively misleads. This renderer
    draws any Line it finds; the device does not -- it honors other items'
    `deleted_length`. That gap once hid 44 strokes written into ids 872..915
    while a tombstone covered 827..931: perfect previews here, blank page on
    the tablet, for hours. If this warns, the page WILL look wrong on the
    device no matter how good the PNG looks.
    """
    pid = live_pages(doc)[page_no - 1]["id"]
    path = page_file(doc, pid)
    if not os.path.exists(path):
        return []                   # never written on: a PDF or EPUB page, or a blank sheet, has no ink file
    fast = _lines_of(path) if arrays else None
    if fast is not None:                              # the renderer's: straight from the C pass, no block objects
        blocks, dead, made = fast
    else:
        blocks = blocks_of(path, arrays)
        dead = dead_ranges(blocks)
        made = None
    # WHERE THE TABLET DRAWS EACH STROKE, always: a group the tablet anchored to the typed text is stored offset
    # from the page, and read at its stored place it was drawn, ruled on, collided with and pointed at somewhere
    # it is not (a sentence over the board read as lying across the user's handwriting at the top). The copy keeps
    # its STORED identity (P.skey), which is what erasing and hiding match in the file.
    shifts = _anchor_offsets(doc, page_no, blocks)
    out, buried = [], 0
    # the erased ranges merged and sorted, each stroke's id looked up by bisection (a page with many tombstones and many
    # strokes was hundreds of millions of comparisons, one range at a time)
    import bisect
    spans = []
    for a, z in sorted(dead):
        if spans and a <= spans[-1][1] + 1:
            spans[-1][1] = max(spans[-1][1], z)
        else:
            spans.append([a, z])
    lows = [a for a, _z in spans]

    def is_dead(n):
        i = bisect.bisect_right(lows, n) - 1
        return i >= 0 and n <= spans[i][1]
    found = made if made is not None else (
        (b.item.item_id.part2, b.parent_id, b.item.value, b.item.item_id.part1) for b in blocks
        if isinstance(b, ss.SceneLineItemBlock) and isinstance(getattr(b.item, "value", None), Line))
    daemon = daemon_layer_ids(blocks)
    for n, parent, v, author in found:
        if daemon_stroke(author, (parent.part1, parent.part2), daemon, lambda v=v: synthetic(v.points)):
            continue                                      # the daemon's note, never the page's content
        if is_dead(n):
            buried += 1          # the device treats this as erased
        else:
            d = shifts.get(parent)
            if d and (d[0] or d[1]):             # where the tablet draws it
                if hasattr(v.points, "dtype"):    # an array: moved in float64, as the objects' floats are
                    import numpy as _np
                    P = v.points
                    Q = _np.empty(len(P), [(f, _np.float64) for f in P.dtype.names])
                    for f in P.dtype.names:
                        Q[f] = P[f]
                    Q["x"] += d[0]; Q["y"] += d[1]
                    v = dataclasses.replace(v, points=Q)
                else:
                    from paperdaemon.pipeline import page as _P
                    key = _P.skey(v)
                    v = dataclasses.replace(v, points=[dataclasses.replace(p, x=p.x + d[0], y=p.y + d[1]) for p in v.points])
                    v._stored_key = key
            out.append(v)
    if buried:
        logging.getLogger("rm_render").error(
            "%d stroke(s) on %s p%s have ids inside a DELETED RANGE %s -- the "
            "device treats them as erased, so they are EXCLUDED from this "
            "render. The page really is missing them.",
            buried, str(doc)[:8], page_no, dead)
    return out


_PDF_SIZES = {}


def pdf_page_size(path, idx):
    """A PDF page's (width, height) in points, or None when it cannot be read."""
    try:
        key = (path, os.path.getmtime(path), idx)
    except OSError:
        return None
    if key not in _PDF_SIZES:
        try:
            import pypdfium2 as pdfium
            from paperdaemon.pdflock import LOCK
            with LOCK:                               # PDFium is not safe on two threads at once
                pdf = pdfium.PdfDocument(path)
                try:
                    _PDF_SIZES[key] = tuple(pdf[idx].get_size()) if 0 <= idx < len(pdf) else None
                finally:
                    pdf.close()
        except Exception:
            _PDF_SIZES[key] = None
    return _PDF_SIZES[key]


def page_frame(doc, page_no):
    """The page's own frame in page units, (width, height), x centered on 0 and y down from 0.
    A PDF page is its PDF page at PDF_SCALE. Any other page takes SceneInfo's paper_size, which
    varies per document -- 1404x1872 and 1620x2160 both occur -- so never assume one."""
    kind, path, idx = source_page(doc, page_no)
    if kind == "pdf" and path is not None and idx is not None:
        size = pdf_page_size(path, idx)
        if size:
            return (size[0] * PDF_SCALE, size[1] * PDF_SCALE)
    pid = live_pages(doc)[page_no - 1]["id"]
    path = page_file(doc, pid)
    for b in (other_blocks_of(path) if os.path.exists(path) else []):
        if isinstance(b, ss.SceneInfo) and getattr(b, "paper_size", None):
            return tuple(b.paper_size)
    return (PAGE_W, PAGE_H)


def source_image(doc, page_no):
    """The page of the PDF or book under a page, alone (no ink, no text), the page's frame in size: what the page
    editor draws its ink on. -> a PIL image, or None for a page with no source page."""
    from PIL import Image
    kind, path, idx = source_page(doc, page_no)
    if kind not in ("pdf", "epub") or idx is None:
        return None
    pw, ph = page_frame(doc, page_no)
    canvas = Image.new("RGB", (int(round(pw)), int(round(ph))), "white")
    _paste_source(canvas, doc, page_no, (pw, ph), lambda p, _h=pw / 2: (p.x + _h, p.y))
    return canvas


def px_width(L, pt):
    fam = L.tool.name.split("_")[0]
    return max(1.0, pt.width * WSCALE.get(fam, WSCALE_DEFAULT))


# TYPED TEXT IS DRAWN AS IT LOOKS, NOT IN A MARKER COLOR.
# It used to be #5a00a0 violet, "provably outside the device gamut" -- and that proof was never
# sound: the gamut is a symptom of the tablet screen, not of the render that is generated,
# and highlighters take any RGBA, so nothing stopped a decomposition painting that exact
# color. The planning pass now gets the page as accurately as it can be drawn.
# It costs nothing, because the model can already tell: with the app's own faces (typed_layout)
# native text is a proportional typeface, the assistant's replies are the monoline stroke font, and
# the user's hand is irregular. Verified by eye on a page where all three appear together.
# TYPED_HIGHLIGHT is for ERASURE work only -- when the question is "which of these marks is typed
# and may not be touched", ask for it explicitly with render(..., mark_typed=True).
TYPED_COLOR = (0, 0, 0)
TYPED_HIGHLIGHT = (90, 0, 160)


def source_page(doc, page_no):
    """The page of the underlying PDF/EPUB this .rm annotates, if any.

    Returns (kind, path, index) or (None, None, None). Most of the library is
    NOT a plain notebook -- 69 PDFs and 50 EPUBs against 41 notebooks -- so a
    renderer that ignores this is wrong for the majority of pages.

    The link is per page: each entry in cPages.pages carries `redir.value`,
    the 0-based index into the source document.

    **Never use the page's POSITION for this.** Measured on the real library:
    863 pages have `redir != position`. Pages get inserted and reordered, and
    several .rm pages can annotate the SAME source page -- a calendar PDF runs
    0, 1, 1, 2, 2, 3 because a page was added after each one. Positional
    indexing would render the wrong page for most of the library.

    A page with NO `redir` is a blank sheet APPENDED past the end of the source,
    not a failure: every such page in the library sits beyond its document's
    page count (one document has a 1-page PDF and blanks at positions 2-5).
    Those render as blank paper, correctly, with no warning.
    """
    from paperdaemon import ledger as _S
    c = _S.content(doc)
    kind = c.get("fileType")
    if kind not in ("pdf", "epub"):
        return None, None, None
    pages = _S.live_pages(c)
    if page_no - 1 >= len(pages):
        return kind, None, None
    idx = (pages[page_no - 1].get("redir") or {}).get("value")
    if kind == "epub":
        # the tablet lays a book out and sends its pages as a PDF beside the EPUB -- the pages the ink was written on --
        # so an EPUB page is that PDF's page; until the tablet has sent one (and always in the false mirror, unless the
        # tablet converted it) PaperDaemon lays the book out as the tablet does (remarkable/books.py)
        pdf = os.path.join(RM, doc + ".pdf")
        if os.path.exists(pdf):
            return "pdf", pdf, idx
        try:
            from paperdaemon.remarkable import books
            laid = books.rendition(doc, RM)
        except Exception:
            laid = None
        if laid:
            return "pdf", laid, idx
    path = os.path.join(RM, doc + "." + kind)
    return kind, (path if os.path.exists(path) else None), idx


def _paste_source(canvas, doc, page_no, page, T):
    """Draw the source document page UNDER the ink. Returns a note, or ''.

    Exact: a PDF page's frame is the PDF page at PDF_SCALE (page_frame), so the
    page is rendered at that scale and laid at the frame's top left. How the
    tablet shows the page -- `customZoom*`, `verticalScroll` -- does not move the
    ink: two scrolled pages carry handwritten marks exactly where they were
    made.
    """
    kind, path, idx = source_page(doc, page_no)
    if kind is None:
        return ""
    if idx is None:
        return ""              # blank page appended past the end of the source
    if path is None:
        return "%s SOURCE MISSING -- ink shown on blank paper" % kind.upper()
    if kind == "epub":
        # the book could not be laid out: say so loudly rather than render a blank sheet that looks complete
        return "EPUB TEXT NOT RENDERED -- ink is shown without the book text"
    try:
        import pypdfium2 as pdfium
    except ImportError:
        return "PDF NOT RENDERED -- pypdfium2 is not installed"
    try:
        pw, ph = page
        from paperdaemon.pdflock import LOCK
        with LOCK:                                   # PDFium is not safe on two threads at once
            pdf = pdfium.PdfDocument(path)
            # CLOSED, always: an open PdfDocument keeps the file locked on Windows, and a document rebuilt in place
            # right after a render could not be replaced -- "Access is denied"
            try:
                if idx >= len(pdf):
                    return "PDF page %d out of range" % idx
                x0, y0 = T(_Pt(-pw / 2.0, 0.0))
                im = pdf[idx].render(scale=PDF_SCALE).to_pil().convert("RGB")
            finally:
                pdf.close()
        canvas.paste(im, (int(round(x0)), int(round(y0))))
        return ""
    except Exception as e:
        return "PDF RENDER FAILED (%s)" % type(e).__name__


class _Pt(object):
    __slots__ = ("x", "y")

    def __init__(self, x, y):
        self.x, self.y = x, y


def _frame(S, page=(PAGE_W, PAGE_H), extra=()):
    """THE PICTURE'S FRAME -> (width, height, transform), one pixel a page unit: THE WHOLE PAGE, always, grown on any
    side where something sits past it (ink, typed text, a picture: `extra` is a list of (x, y) page points that must
    be inside too) to hold it, with a margin. Nothing on the page is left out of its picture, and no part of the page
    is either. transform(p) is p's pixel; the picture's top-left corner is page point -transform(0, 0) (render() returns
    it), so a picture's pixel maps back to the page whatever the frame came out as."""
    pw, ph = page
    X, Y = _coords(S, 0), _coords(S, 1)
    ex, ey = [e[0] for e in extra], [e[1] for e in extra]
    x0, y0, x1, y1 = -pw / 2, 0.0, pw / 2, ph
    pad = 60
    if len(X) or ex:
        x_lo, x_hi, y_lo, y_hi = _lo_hi(X, ex, True), _lo_hi(X, ex, False), _lo_hi(Y, ey, True), _lo_hi(Y, ey, False)
        if x_lo < x0:
            x0 = math.floor(x_lo - pad)
        if y_lo < y0:
            y0 = math.floor(y_lo - pad)
        if x_hi > x1:
            x1 = x_hi + pad
        if y_hi > y1:
            y1 = y_hi + pad
    return int(round(x1 - x0)), int(round(y1 - y0)), lambda p: (p.x - x0, p.y - y0)


def _stipple(d, L, col, pts, rng):
    """Approximate pencil grain: scatter dots across the stroke, density and tone
    driven by pressure. The real texture is procedural on-device."""
    for i in range(len(pts) - 1):
        (x0, y0), (x1, y1) = pts[i], pts[i+1]
        w = px_width(L, L.points[i])
        pr = L.points[i].pressure / 255.0
        seg = math.hypot(x1 - x0, y1 - y0)
        n = max(2, int(seg * max(w, 1.2) * 0.9 * (0.4 + 0.6 * pr)))
        for _ in range(n):
            t = rng.random()
            cx, cy = x0 + (x1-x0)*t, y0 + (y1-y0)*t
            a = rng.random() * 2 * math.pi
            r = (w / 2 + 0.5) * math.sqrt(rng.random())
            k = (0.35 + 0.5 * pr) * (0.45 + 0.55 * rng.random())
            tone = tuple(int(255 - (255 - c) * min(1.0, k)) for c in col)
            d.point([(int(cx + math.cos(a)*r), int(cy + math.sin(a)*r))], fill=tone)


def _draw(d, L, col, pts):
    """THE DECOMPOSER REFERENCE'S stroke shape (rm_lean and rm_raster measure with it; the pictures are drawn by
    pipeline/page/paint.py). One stroke: round-capped, round-joined, per-point width. The HIGHLIGHTER has FLAT ends
    (measured on the app, on calibration pages): each segment a
    rectangle, and no joint -- the outer wedge of every turn stays unpainted."""
    if L.tool.name.split("_")[0] in PENCIL_FAMILY:
        _stipple(d, L, col, pts, random.Random(int(pts[0][0]) * 7919 + int(pts[0][1])))
        return
    if L.tool.name.startswith("HIGHLIGHTER"):
        # one rectangle per segment (flat ends) + a bevel triangle on the outer side of each
        # interior vertex, nothing on the inner side (measured on calibration pages)
        Q, Wp = [pts[0]], [L.points[0]]
        for i in range(1, len(pts)):
            if abs(pts[i][0] - Q[-1][0]) > 1e-6 or abs(pts[i][1] - Q[-1][1]) > 1e-6:
                Q.append(pts[i]); Wp.append(L.points[i])
        n = len(Q)
        if n < 2:
            return
        dirs, hw = [], []
        for i in range(n - 1):
            dx, dy = Q[i + 1][0] - Q[i][0], Q[i + 1][1] - Q[i][1]
            ln = (dx * dx + dy * dy) ** 0.5
            dirs.append((dx / ln, dy / ln))
            hw.append(max(0.5, (px_width(L, Wp[i]) + px_width(L, Wp[i + 1])) / 4.0))
        for i in range(n - 1):
            (x0, y0), (x1, y1) = Q[i], Q[i + 1]
            nx, ny = -dirs[i][1] * hw[i], dirs[i][0] * hw[i]
            d.polygon([(x0 + nx, y0 + ny), (x1 + nx, y1 + ny), (x1 - nx, y1 - ny), (x0 - nx, y0 - ny)], fill=col)
        for i in range(1, n - 1):
            (d1x, d1y), (d2x, d2y) = dirs[i - 1], dirs[i]
            cross = d1x * d2y - d1y * d2x
            if abs(cross) < 1e-6:
                continue
            sgn = -1.0 if cross > 0 else 1.0
            vx, vy = Q[i]
            p1 = (vx + sgn * (-d1y) * hw[i - 1], vy + sgn * d1x * hw[i - 1])
            p2 = (vx + sgn * (-d2y) * hw[i], vy + sgn * d2x * hw[i])
            d.polygon([(vx, vy), p1, p2], fill=col)
        return
        dirs = []
        for i in range(n - 1):
            dx, dy = pts[i + 1][0] - pts[i][0], pts[i + 1][1] - pts[i][1]
            ln = (dx * dx + dy * dy) ** 0.5
            dirs.append((dx / ln, dy / ln) if ln > 1e-9 else (dirs[-1] if dirs else (1.0, 0.0)))
        norms = [(-dy, dx) for dx, dy in dirs]
        ms = []
        for i in range(n):
            if i == 0:
                m = norms[0]
            elif i == n - 1:
                m = norms[-1]
            else:
                sx, sy = norms[i - 1][0] + norms[i][0], norms[i - 1][1] + norms[i][1]
                ln = (sx * sx + sy * sy) ** 0.5
                m = (sx / ln, sy / ln) if ln > 1e-6 else norms[i]
            ms.append(m)
        for i in range(n - 1):
            h0 = max(0.5, px_width(L, L.points[i]) / 2.0); h1 = max(0.5, px_width(L, L.points[i + 1]) / 2.0)
            (x0, y0), (x1, y1) = pts[i], pts[i + 1]
            (m0x, m0y), (m1x, m1y) = ms[i], ms[i + 1]
            d.polygon([(x0 + m0x * h0, y0 + m0y * h0), (x1 + m1x * h1, y1 + m1y * h1),
                       (x1 - m1x * h1, y1 - m1y * h1), (x0 - m0x * h0, y0 - m0y * h0)], fill=col)
        return
    if len({p.width for p in L.points}) == 1:
        w = px_width(L, L.points[0])
        d.line(pts, fill=col, width=int(round(w)), joint="curve")
        r = w / 2
        for (x, y) in (pts[0], pts[-1]):
            d.ellipse([x-r, y-r, x+r, y+r], fill=col)
        return
    for i in range(len(pts) - 1):
        w = (px_width(L, L.points[i]) + px_width(L, L.points[i+1])) / 2
        d.line([pts[i], pts[i+1]], fill=col, width=int(round(max(1, w))))
        r = w / 2; x, y = pts[i]
        d.ellipse([x-r, y-r, x+r, y+r], fill=col)
    w = px_width(L, L.points[-1]); r = w / 2; x, y = pts[-1]
    d.ellipse([x-r, y-r, x+r, y+r], fill=col)


def render(doc, page_no, out, typed=True, hide=None, hide_typed=None, hide_images=None,
           mark_typed=False, blank_ok=False):
    """Render a page to PNG -- strokes AND typed text -- at one pixel a page unit, the whole page and anything past
    it (_frame). -> (strokes, (width, height), tools, typed paragraphs, (x, y)): the last the page point at the
    picture's top-left corner, so a pixel (u, v) is page point (x + u, y + v), whatever the frame came out as.

    TYPED TEXT IS DRAWN BY DEFAULT, and that is not a nicety. This renderer used
    to draw strokes only, so on a page with typed text every preview showed the
    drawing on a blank sheet. Content placed "below the questions" looked
    perfect locally and landed straight on top of them on the device. A preview
    that omits half the page is worse than no preview, because it is believed.

    The typed layout is APPROXIMATE -- the app's font metrics are not ours, so
    wrapping can differ by a word. It is exact enough for the question a preview
    has to answer: what is already here, and where does it end. Pass typed=False
    only when you specifically want ink alone.
    """
    return _render(doc, page_no, out, typed, hide, hide_typed, hide_images, mark_typed, blank_ok)


def _render(doc, page_no, out, typed, hide, hide_typed, hide_images, mark_typed, blank_ok):
    # the points as arrays, as they are drawn (strokes(arrays=True)); a job's staged erasures name strokes by their keys,
    # which are taken from point objects, so a render with any hides reads those
    S = strokes(doc, page_no, arrays=not hide)
    # STAGED ERASURES (rm_host): strokes, typed paragraphs and pictures the current job has
    # erased in its draft are left out, so a preview shows the page as commit() will leave it.
    if hide:
        from paperdaemon.pipeline import page as _P
        S = [L for L in S if _P.skey(L) not in hide]
    tb = None
    if typed:
        try:
            from paperdaemon.pipeline.page import typed as _TY
            tb, _paras = _TY.paragraphs(doc, page_no)
        except Exception:
            tb = None
    # IMAGES placed with the app (a "capture"): drawn under the ink, and counted as content. A page
    # holding only a picture used to raise here and the daemon read it as blank.
    try:
        from paperdaemon.pipeline.page import images as _IM
        _imgs = [im for im in _IM.items(doc, page_no) if im.get("path")]
        # IN THE TABLET'S DRAWING ORDER: drawn in the file's order, a picture the tablet shows under another
        # (white pieces in a group under a board drawn after it) showed on top here
        try:
            _st = _IM.stacking(page_file(doc, live_pages(doc)[page_no - 1]["id"]))
            _imgs.sort(key=lambda im: _st.get(tuple(im.get("item") or ()), (0, 0, 0, 0)))
        except Exception:
            pass
        if hide_images:
            def _hid(im):
                return any(all(abs(float(a) - float(b)) < 1.5 for a, b in zip(im["box"], hb))
                           for hb in hide_images)
            _imgs = [im for im in _imgs if not _hid(im)]
    except Exception:
        _imgs = []
    if not S and tb is None and not _imgs and not blank_ok:      # the viewer draws an unwritten page as it is
        raise ValueError("no strokes and no typed text on page %d" % page_no)
    # The frame MUST account for typed text. _frame() sizes to the strokes, so
    # on a page where the text sits below (or outside) the ink, the text was
    # simply cropped out of the picture -- the render looked complete and was
    # missing the very thing the reader needed. Measured on a real page:
    # strokes end at y=634, the typed feedback is at y~1163, and it vanished.
    _extra = []
    if tb is not None:
        try:
            from paperdaemon.pipeline.page import typed as _TY2
            _bot = _TY2.text_bottom(doc, page_no) or tb.pos_y
            _extra = [(tb.pos_x, tb.pos_y), (tb.pos_x + tb.width, _bot)]
        except Exception:
            _extra = []
    for _im in _imgs:
        _x0, _y0, _x1, _y1 = _im["box"]
        _extra = list(_extra) + [(_x0, _y0), (_x1, _y1)]
    _page = page_frame(doc, page_no)
    W, H, T = _frame(S, _page, extra=_extra)
    canvas = Image.new("RGB", (W, H), "white")
    _note = _paste_source(canvas, doc, page_no, _page, T)
    for _im in _imgs:
        try:
            class _Q:
                __slots__ = ("x", "y")
                def __init__(self, x, y): self.x, self.y = x, y
            _x0, _y0, _x1, _y1 = _im["box"]
            _a, _b = T(_Q(_x0, _y0)), T(_Q(_x1, _y1))
            _w, _h = max(1, int(round(_b[0] - _a[0]))), max(1, int(round(_b[1] - _a[1])))
            _pic = Image.open(_im["path"]).convert("RGBA").resize((_w, _h), Image.LANCZOS)
            canvas.paste(_pic, (int(round(_a[0])), int(round(_a[1]))), _pic)
        except Exception:
            pass
    d = ImageDraw.Draw(canvas)
    if _note:
        # Stamped ON the image on purpose: a reader looking at the picture must
        # not be able to miss that part of the page is not shown.
        d.rectangle([0, 0, W, 46], fill=(220, 30, 30))
        d.text((12, 14), _note, fill=(255, 255, 255))
    _typed_n = 0
    if tb is not None:
        try:
            from paperdaemon.pipeline.page import typed as _TY
            # under the ink: the app draws text first, and this way a stroke
            # written over text still reads as being on top
            class _P:                      # T() expects something with .x/.y
                __slots__ = ("x", "y")
                def __init__(self, x, y): self.x, self.y = x, y
            # OUT-OF-GAMUT ON PURPOSE (the marking color for typed text, used only when
            # mark_typed is set).
            # The tablet's color space is a CLOSED, FINITE set: 14 PenColor
            # values plus 6 highlighter palette colors plus paper white. So a
            # color outside that set cannot have come from the device, and
            # "this mark is my overlay" stops being a convention and becomes
            # evidence. Gray failed exactly here -- #c7c7c6 gray is a real
            # highlighter color, so a gray stroke and a gray overlay were the
            # same pixels.
            # Deep violet #5a00a0 sits 137 RGB units from the nearest device
            # color (gray), and is obvious to the eye as well as to a test.
            _typed_n = _TY.draw(d, doc, page_no,
                                xform=lambda x, y: T(_P(x, y)),
                                color=(TYPED_HIGHLIGHT if mark_typed else TYPED_COLOR),
                                skip=hide_typed)
        except Exception:
            pass
    # THE STROKES, by PaperDaemon's one renderer (pipeline/page/paint.py: fastdecomp/render.c), as the tablet draws them:
    # file order; pens opaque in their measured colors; the highlighter a per-channel minimum ("darken") wash; the
    # shader a translucent wash; each pen answering its pressure as the tablet does (paint.response: the pencils' grain,
    # the light paintbrush and ballpoint). ONE RENDER: at the tablet's own pixels, for every picture the engine makes.
    from paperdaemon.pipeline.page.paint import paint_flat
    import numpy as _np

    class _O:                                       # T() is a translation: where it puts the page's origin
        __slots__ = ("x", "y")
        def __init__(self, x, y): self.x, self.y = x, y
    _tx, _ty = T(_O(0.0, 0.0))
    paint_flat(canvas, _ink(S, _tx, _ty))
    canvas.save(out)
    tools = collections.Counter(L.tool.name for L in S)
    return len(S), (W, H), tools, _typed_n, (-_tx, -_ty)
