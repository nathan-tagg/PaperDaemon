r"""The daemon's notes on a page (Settings: "Daemon notes"): that he is on it, what the host makes of the page and
does with it, step by step, and how it ended, lettered small in the band across the top of the page, under the
tablet's toolbar, and signed.

THE BAND IS HIS AND NOTHING ELSE IS: every stroke lies above the page's safe area (page.safe_area: the toolbar's zone,
which nothing the user or the host writes may enter), on a layer of his own, named as the user chose (Settings:
daemon.layer, "Daemon" unless they changed it), at the bottom of the tablet's list of layers. The renderer never draws
what is his (render.daemon_stroke), and the fingerprint that says whether a page changed leaves it out
(ledger._content_sha), so a note can neither start a job nor be read as the user's writing. Only the page editor shows
it.

HIS IDS: he writes as the tablet's own author (1) -- the tablet will not open a page holding an item of an author it
does not know, and the author number his notes once had (218, render.DAEMON_AUTHOR) left every page it was on
unreadable there. His ids are counted on from the highest of that author on the page with a wide gap (GAP), and kept
per page in daemon-ink.json, so nothing of his can share an id with the user's strokes, the host's, what the user adds
on the tablet meanwhile, or another note of his. Notes go up as copies of a page while the host works on the mirror's,
and the tablet merges what it receives: two notes with the same ids, made from different copies, were once merged into
a pile of three notes on top of each other. WHAT IS HIS on a page: the machine-drawn strokes on his layer
(render.daemon_stroke: every point at one pressure, with no speed and no direction, which no hand makes).

EVERY WRITE ERASES EVERYTHING OF HIS FIRST: his strokes erased (tombstoned, as the tablet erases), and the same for
everything he put on this page before that this copy of it has never seen (daemon-ink.json keeps what he laid), so the
merge on the tablet erases those too; his old notes on a layer named "PaperDaemon" with them. ANYTHING LEFT UNDER HIS
OLD AUTHOR (218) is taken out of the file outright -- strokes, tombstones, its layer and its entry in the author table
-- so a page it made unreadable opens again once the next note reaches it.
Then the note. HIS LAYER ITSELF STAYS, ONE PER PAGE: the tablet writes the user's strokes on whatever layer is
current, and the user's writing has landed on his. It is made once and sent whole with every note, so copies merge into
one layer; it is made anew only when the user deleted it on the tablet. Only his strokes on it are his.

A RETRY BOX: a job that was skipped or failed ends its note with a small box; anything the user writes in it asks for
the job again (box_marks).

Everything here works on a page's BYTES, and refuses to return a page that does not read back as it should.
"""
import io
import os
import time
import uuid

from rmscene import read_blocks, write_blocks
from rmscene import scene_stream as ss
from rmscene import scene_items as si
from rmscene.crdt_sequence import CrdtSequenceItem
from rmscene.scene_stream import CrdtId
from rmscene.tagged_block_common import LwwValue

from paperdaemon.pipeline.page.render import DAEMON_AUTHOR as LEGACY

AUTHOR_UUID = uuid.uuid5(uuid.NAMESPACE_DNS, "daemon.paperdaemon")   # his old entry in a page's author table (218)
# HE WRITES AS THE TABLET'S OWN AUTHOR (1): the tablet will not open a page holding an item of an author it does not
# know (his old 218 left every page it was on unreadable). His ids are counted on from the highest of the tablet's on
# the page with a wide gap (GAP), so what the user adds on the tablet while a note goes up -- numbered by the tablet
# from its own highest, which it has not yet seen ours above -- never takes the same ids. What is his on a page: the
# machine-drawn strokes on his layer (render.daemon_stroke), and anything left under 218, which goes outright.
AUTHOR = 1
GAP = 100_000
SIZE = 15.0                         # the lettering's cap height, page units on a Paper Pro page
LEAD = 24.0                         # baseline to baseline
PEN_W = 5                           # the fineliner's width at that size
BOX = 40.0                          # the retry box's side: about 4.5 mm on a Paper Pro, room for a tick
ROOT = (0, 1)                       # the page's list of layers
LAID_MAX = 40                       # what he laid that a page has not shown back yet, kept at most


def layer_name():
    from paperdaemon.pipeline.page import render as R
    return R.daemon_layer_name()


def _key(cid):
    return (cid.part1, cid.part2)


# ------------------------------------------------------------------ the page, spliced
# A PAGE IS ITS BLOCKS' FRAMES, end to end after the header: the C pass (fastrm) says where each one starts and ends,
# its kind, and for a stroke its layer, its ids and whether it is erased. A note is a handful of blocks put in and a
# stroke's frame swapped for its tombstone's; everything else is copied byte for byte, so a page of a quarter of a
# million strokes is changed in a moment, not read and written whole. A page the C pass is not sure of is written
# once through rmscene, and read by the C pass from that.
LINE = ss.SceneLineItemBlock.BLOCK_TYPE


def _scan(data):
    from paperdaemon.remarkable import fastrm
    try:
        got = fastrm._c_pass(data)
    except Exception:
        got = None
    if got is None:
        return None
    rows, rest = got
    return [list(r) for r in (rows.tolist() if hasattr(rows, "tolist") else rows)], rest


def _parts(data):
    """(the page's bytes, its rows, each row's block -- None for a stroke)."""
    got = _scan(data)
    if got is None:
        buf = io.BytesIO()
        write_blocks(buf, list(read_blocks(io.BytesIO(data))))
        data = buf.getvalue()
        got = _scan(data)
        if got is None:
            raise RuntimeError("the page could not be read for the daemon's note")
    rows, rest = got
    it = iter(rest)
    return data, rows, [None if r[0] == LINE else next(it) for r in rows]


def _frame(block):
    """One block's frame, as it is written in a page."""
    from rmscene.tagged_block_common import HEADER_V6
    buf = io.BytesIO()
    write_blocks(buf, [block])
    return buf.getvalue()[len(HEADER_V6):]


def _line_tomb(parent, iid, left, right=(0, 0)):
    return _frame(ss.SceneLineItemBlock(parent_id=CrdtId(*parent), item=CrdtSequenceItem(
        item_id=CrdtId(*iid), left_id=CrdtId(*left), right_id=CrdtId(*right), deleted_length=1, value=None)))


def _tomb(r):
    return _line_tomb((r[5], r[6]), (r[7], r[8]), (r[9], r[10]), (r[11], r[12]))


def _old_layers(blocks):
    """His layers on the page (render.daemon_layer_ids): named as his, whoever made them, or under his old author."""
    from paperdaemon.pipeline.page import render as R
    return R.daemon_layer_ids(blocks)


def _mine(r, old, data):
    """Is a stroke (a C-pass row) his: under his old author, or machine-drawn on one of his layers (`old`)."""
    if r[7] == LEGACY:
        return True
    if (r[5], r[6]) not in old or not r[20]:
        return False
    from paperdaemon.remarkable import fastrm
    return fastrm.synthetic_at(data, r[19], r[20] // fastrm.POINT.itemsize)


def _live_counts(data):
    """(his live strokes, the user's) as the C pass reads the page, or None."""
    got = _scan(data)
    if got is None:
        return None
    rows, rest = got
    old = _old_layers(rest)
    mine = sum(1 for r in rows if r[0] == LINE and r[14] and _mine(r, old, data))
    return mine, sum(1 for r in rows if r[0] == LINE and r[14]) - mine


def _layer_blocks(n, name, right):
    """His layer n, as the tablet makes one: its tree node under the root, its group (named, visible), and its place
    FIRST in the root's list (the bottom of the tablet's layers, under the user's), before `right`. Ids n (the layer),
    n+1 and n+2 (its name's and visibility's), n+3 (its place)."""
    layer = CrdtId(AUTHOR, n)
    g = si.Group(node_id=layer)
    g.label = LwwValue(timestamp=CrdtId(AUTHOR, n + 1), value=name)
    g.visible = LwwValue(timestamp=CrdtId(AUTHOR, n + 2), value=True)
    return [(ss.SceneTreeBlock.BLOCK_TYPE, _frame(ss.SceneTreeBlock(tree_id=layer, node_id=CrdtId(0, 0), is_update=True,
                                                                    parent_id=CrdtId(*ROOT)))),
            (ss.TreeNodeBlock.BLOCK_TYPE, _frame(ss.TreeNodeBlock(group=g))),
            (ss.SceneGroupItemBlock.BLOCK_TYPE, _frame(ss.SceneGroupItemBlock(parent_id=CrdtId(*ROOT), item=CrdtSequenceItem(
                item_id=CrdtId(AUTHOR, n + 3), left_id=CrdtId(0, 0), right_id=CrdtId(*right), deleted_length=0,
                value=layer))))]


def _put(frames, kinds, news):
    """`news` [(kind, frame)] into the page, each after the last block of its kind (before the first stroke when there
    is none); strokes at the end."""
    out_f, out_k = list(frames), list(kinds)
    for kind in (ss.SceneTreeBlock.BLOCK_TYPE, ss.TreeNodeBlock.BLOCK_TYPE, ss.SceneGroupItemBlock.BLOCK_TYPE):
        batch = [f for k, f in news if k == kind]
        if not batch:
            continue
        at = max((i for i, k in enumerate(out_k) if k == kind), default=None)
        if at is None:
            at = next((i for i, k in enumerate(out_k) if k == LINE), len(out_k)) - 1
        out_f[at + 1:at + 1] = batch
        out_k[at + 1:at + 1] = [kind] * len(batch)
    lines = [f for k, f in news if k == LINE]
    return out_f + lines, out_k + [LINE] * len(lines)


def _first_layer(items):
    """The first item of the root's list of layers, in the list's own order (CRDT), or (0, 0)."""
    from rmscene.crdt_sequence import CrdtSequence
    try:
        keys = list(CrdtSequence(items).keys())
    except Exception:
        keys = [i.item_id for i in items]
    return _key(keys[0]) if keys else (0, 0)


def _write(data, state, strokes=None, also=()):
    """THE ONE WAY THE DAEMON CHANGES A PAGE: everything of his on it erased (see the module's note), the user's
    strokes whose ids are in `also` erased (a tick in the retry box), and, given `strokes`, the note on his layer.
    `state` (daemon-ink.json's entry for the page: {"next": his next id there, "layer": [its id, the id it goes before,
    its name], "laid": [[layer, first id, last id], ...]}) is brought up to date. -> (bytes, how many strokes erased,
    whether anything changed)."""
    from rmscene.tagged_block_common import HEADER_V6
    data, rows, blocks = _parts(data)
    old = _old_layers([b for b in blocks if b is not None])
    also = set(also)
    theirs0 = sum(1 for r in rows if r[0] == LINE and r[14] and not _mine(r, old, data) and (r[7], r[8]) not in also)
    frames, kinds = [], []
    seen, dead, trees, nodes, places = set(), set(), set(), set(), {}
    top, erased, changed, table = 0, 0, False, False
    root_items = []
    # HIS LAYERS AS THE PAGE HAS THEM: each live place of his in the root's list -> (its layer, where the place frame
    # is, its item); and whose strokes (live, not his) lie on which layer
    his_places, users_on = {}, set()
    for r, b in zip(rows, blocks):
        raw = data[r[1] - 8:r[2]]
        if r[0] == LINE:
            k = (r[7], r[8])
            if r[7] == LEGACY:                       # under his old author: out of the file, every trace of it
                erased += 1 if r[14] else 0
                changed = True
                continue
            seen.add(k)
            if r[14] and not _mine(r, old, data):
                users_on.add((r[5], r[6]))
            if r[14] and (_mine(r, old, data) or k in also):
                raw, erased, changed = _tomb(r), erased + 1, True
            elif not r[14]:
                dead.add(k)
            if r[7] == AUTHOR:
                top = max(top, r[8])
        elif isinstance(b, ss.SceneGroupItemBlock):
            it = b.item
            k = _key(it.item_id)
            if k[0] == LEGACY or getattr(it.value, "part1", None) == LEGACY:
                changed = True
                continue
            seen.add(k)
            if k[0] == AUTHOR:
                top = max(top, k[1])
                places[k] = it.value is not None and it.deleted_length == 0
            if _key(b.parent_id) == ROOT:
                root_items.append(it)
                if it.value is not None and it.deleted_length == 0 and _key(it.value) in old:
                    his_places[_key(it.value)] = (len(frames), it)
        elif isinstance(b, ss.SceneTreeBlock):
            if b.tree_id.part1 == LEGACY:
                changed = True
                continue
            trees.add(_key(b.tree_id))
            if b.tree_id.part1 == AUTHOR:
                top = max(top, b.tree_id.part2 + 3)
        elif isinstance(b, ss.TreeNodeBlock):
            if b.group.node_id.part1 == LEGACY:
                changed = True
                continue
            nodes.add(_key(b.group.node_id))
        elif isinstance(b, ss.AuthorIdsBlock):
            table = True
            if LEGACY in b.author_uuids:
                raw = _frame(ss.AuthorIdsBlock(author_uuids={a: u for a, u in b.author_uuids.items() if a != LEGACY}))
                changed = True
        elif isinstance(b, ss.RootTextBlock):
            for tid, ti in b.value.items._items.items():   # the typed text's ids are the tablet's author's too
                if tid.part1 == AUTHOR:
                    span = max(len(ti.value) if isinstance(ti.value, str) else 0, ti.deleted_length or 0, 1)
                    top = max(top, tid.part2 + span - 1)
        elif b is not None and isinstance(getattr(b, "data", None), (bytes, bytearray)):
            from paperdaemon.pipeline.page import images as _IM   # a picture: its ids, read off its bytes
            top = max(top, _IM.max_author_id(bytes(b.data), AUTHOR))
        frames.append(raw)
        kinds.append(r[0])
    # WHAT HE LAID BEFORE that this copy of the page has never seen, erased all the same: the tablet merges it with the
    # copy that carried it. What the page already showed erased when it came here is forgotten (what is erased only
    # now is not: a copy made later from an older page still has to erase it).
    news, keep = [], []
    for rec in list(state.get("laid") or []):
        try:
            lay, a, z, au = int(rec[0]), int(rec[1]), int(rec[2]), int(rec[3])
        except (TypeError, ValueError, IndexError):
            continue                                  # laid under his old author: gone with it
        if au != AUTHOR:
            continue
        ids = [(AUTHOR, k) for k in range(a, z + 1)]
        if all(k in dead for k in ids):
            continue
        keep.append([lay, a, z, AUTHOR])
        top = max(top, z)
        for i, k in enumerate(ids):
            if k not in seen:
                news.append((LINE, _line_tomb((AUTHOR, lay), k, ids[i - 1] if i else (0, 0))))
    if news:
        changed = True
    # his ids: on from the highest of the tablet's author on the page, with a wide gap (see AUTHOR); a record from his
    # old author counts for nothing
    n = max(int(state.get("next") or 1) if state.get("author") == AUTHOR else 1, top + 1 + GAP)
    state["author"] = AUTHOR
    if strokes is not None:
        if not table:
            raise RuntimeError("the page has no author table for the daemon's note")
        # HIS LAYER: one per page, made once and sent whole with every note (the same blocks, the same ids, so copies
        # merge into one layer); a new one only when the user deleted it on the tablet. THE PAGE SAYS WHICH: the
        # record kept (state) is used while the page still has that layer; else the layer of his the page already
        # shows is taken up again -- a record lost must never make a second one. More than one of his on the page
        # (from before): the first is his, and each other one that holds nothing of the user's is taken out of the
        # list of layers (its place erased, as the tablet deletes a layer).
        lay = state.get("layer")
        if lay and (len(lay) < 5 or int(lay[4]) != AUTHOR):
            lay = None                                # a layer recorded under his old author: gone with it
        if lay and (places.get((AUTHOR, int(lay[0]) + 3)) is False or
                    (his_places and (AUTHOR, int(lay[0])) not in his_places)):
            lay = None
        if not lay and his_places:
            ln0 = min(his_places)
            it0 = his_places[ln0][1]
            lay = [ln0[1], it0.right_id.part1, it0.right_id.part2, layer_name(), ln0[0]]
        for lk, (at, it) in sorted(his_places.items()):
            if lay and lk == (AUTHOR, int(lay[0])) or lk in users_on:
                continue
            frames[at] = _frame(ss.SceneGroupItemBlock(parent_id=CrdtId(*ROOT), item=CrdtSequenceItem(
                item_id=it.item_id, left_id=it.left_id, right_id=it.right_id, deleted_length=1, value=None)))
        if not lay:
            first = _first_layer(root_items)
            lay = [n, first[0], first[1], layer_name(), AUTHOR]
            n += 4
        ln = int(lay[0])
        for kind, frame in _layer_blocks(ln, str(lay[3]), (int(lay[1]), int(lay[2]))):
            if (kind == ss.SceneTreeBlock.BLOCK_TYPE and (AUTHOR, ln) not in trees) or \
                    (kind == ss.TreeNodeBlock.BLOCK_TYPE and (AUTHOR, ln) not in nodes) or \
                    (kind == ss.SceneGroupItemBlock.BLOCK_TYPE and (AUTHOR, ln + 3) not in seen):
                news.append((kind, frame))
        state["layer"] = lay
        prev, a = CrdtId(0, 0), n
        for st in strokes:
            pts, widths, tool, color = st[0], st[1], st[2], st[3]
            P = [si.Point(x=float(x), y=float(y), speed=0, direction=0, width=int(widths[i]), pressure=190)
                 for i, (x, y) in enumerate(pts)]
            L = si.Line(color=color, tool=tool, points=P, thickness_scale=3.0, starting_length=0.0, move_id=None,
                        color_rgba=None)
            iid = CrdtId(AUTHOR, n)
            news.append((LINE, _frame(ss.SceneLineItemBlock(parent_id=CrdtId(AUTHOR, ln), item=CrdtSequenceItem(
                item_id=iid, left_id=prev, right_id=CrdtId(0, 0), deleted_length=0, value=L)))))
            prev, n = iid, n + 1
        if n > a:
            keep.append([ln, a, n - 1, AUTHOR])
        changed = True
    state["laid"] = keep[-LAID_MAX:]
    state["next"] = n
    if not changed:
        return data, 0, False
    frames, kinds = _put(frames, kinds, news)
    new = data[:len(HEADER_V6)] + b"".join(frames)
    after = _live_counts(new)
    want = len(strokes) if strokes is not None else 0
    if after is None or after != (want, theirs0):
        raise RuntimeError("the page did not read back with the daemon's note (%s)" % (after,))
    return new, erased, True


def erase(data, state=None, also=()):
    """The page with everything of his erased, and any of the user's strokes whose ids are in `also` (a tick in the
    retry box) -> (bytes, how many strokes erased); (data, 0) when there is nothing to erase."""
    new, n, changed = _write(data, {} if state is None else state, None, also)
    return (new, n) if changed else (data, 0)


def with_note(data, strokes, state=None):
    """The page with everything of his erased and `strokes` (lettering.Drawing strokes: points, widths, tool, color,
    rgba) on his layer. The user's strokes, text and pictures are as they were. -> bytes."""
    return _write(data, {} if state is None else state, strokes)[0]


def box_marks(data, box, pad=6.0, shifts=None):
    """The user's strokes (not his) with a point inside the retry box `box` (x0, y0, x1, y1, page units) -> their
    item ids [(part1, part2)]: a tick, a cross, a scribble -- anything written in it asks for the job again.
    `shifts`: {group (part1, part2): (dx, dy)}, where the tablet draws a group it anchored to the typed text
    (render._anchor_offsets) -- on a page with typed text the tablet puts the user's tick in such a group, stored
    hundreds of units from where it is drawn."""
    if not box:
        return []
    import numpy as np
    from paperdaemon.remarkable import fastrm
    data, rows, blocks = _parts(data)
    old = _old_layers([b for b in blocks if b is not None])
    shifts = shifts or {}
    out = []
    for r in rows:
        if r[0] == LINE and r[14] and not _mine(r, old, data) and r[20]:
            dx, dy = shifts.get((r[5], r[6])) or (0.0, 0.0)
            x0, y0, x1, y1 = box[0] - pad - dx, box[1] - pad - dy, box[2] + pad - dx, box[3] + pad - dy
            P = np.frombuffer(data, dtype=fastrm.POINT, count=r[20] // fastrm.POINT.itemsize, offset=r[19])
            if ((P["x"] >= x0) & (P["x"] <= x1) & (P["y"] >= y0) & (P["y"] <= y1)).any():
                out.append((r[7], r[8]))
    return out


# ------------------------------------------------------------------ what a note says, lettered
def band(frame):
    """(left x, right x, top y, bottom y) of the band the daemon's notes live in, on a page of this frame: above the safe area."""
    from paperdaemon.pipeline import page as PG
    x0, top, x1, _ = PG.safe_area(tuple(frame))
    return x0, x1, 0.0, top


def letter(lines, frame, box=False, latest=False):
    """The note: ONE line in the band, `lines` run together, signed at its end, with a retry box at the band's right
    end when `box`. -> (Drawing strokes, the box (x0, y0, x1, y1) or None). It never wraps: a note too long for the
    line is cut, with an ellipsis, where the signature (and the box) begin. (`latest` is kept for its callers; one line
    is all there is.)"""
    from paperdaemon.pipeline import draw as A
    from paperdaemon.pipeline.draw import lettering as T
    from paperdaemon.pipeline.draw import signature as SIG
    x0, x1, top, bottom = band(frame)
    s = (bottom - top) / 115.0                                 # a Paper Pro page's band is 115 units deep
    size, lead = SIZE * s, LEAD * s
    first = top + lead + 2 * s
    sig_w = size * 0.9 + SIG.signature_width(size * 0.9)       # the signature's room at the end of the last line
    box_w = (BOX * s + size * 5.5) if box else 0.0             # the retry box, at the band's right end, and its word
    width = x1 - x0 - box_w
    wrapped = [" ".join(" ".join(str(ln).split()) for ln in lines)]
    last = 0
    wrapped[last] = _cut(T, wrapped[last], size, width - sig_w)
    d = A.Drawing(int(round(frame[0])), int(round(frame[1])))
    y = first
    end = x0
    for i, ln in enumerate(wrapped):
        y = first + i * lead
        end = x0 + T.text(d, ln, x0, y, size=size, width=PEN_W)
    cur = end + size * 0.9
    SIG.draw_signature(d, cur, y, height=size * 0.9)
    got = None
    if box:
        # the box at the band's right end, centered in its depth, the word "retry" after it
        side = BOX * s
        bx = x1 - side - size * 4.6
        by = top + ((bottom - top) - side) / 2.0
        b = (bx, by, bx + side, by + side)
        d.stroke([(b[0], b[1]), (b[2], b[1]), (b[2], b[3]), (b[0], b[3]), (b[0], b[1])], width=PEN_W)
        T.text(d, "retry", b[2] + size * 0.5, by + side / 2.0 + size / 2.0, size=size, width=PEN_W)
        got = b
    return d.strokes, got


def _cut(T, s, size, width):
    if T.measure(s, size) <= width:
        return s
    while s and T.measure(s + "...", size) > width:
        s = s[:-1]
    return s.rstrip() + "..."


def clock():
    from paperdaemon import i18n
    try:
        return i18n.clock()
    except Exception:
        return time.strftime("%H:%M")


def page_file(doc, page_id):
    from paperdaemon.remarkable.sync import MIRROR
    return os.path.join(MIRROR, doc, page_id + ".rm")
