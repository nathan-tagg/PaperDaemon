r"""The daemon's notes on a page (Settings: "Notes on the page"): what he got, the work at hand, and how it ended,
lettered small in the band across the top of the page, under the tablet's toolbar, and signed.

THE BAND IS HIS AND NOTHING ELSE IS: every stroke lies above the page's safe area (page.safe_area: the toolbar's zone,
which nothing the user or the host writes may enter), on a layer of his own, PaperDaemon. Nothing that reads a page for
the host sees that layer -- render.strokes leaves it out, and so does the fingerprint that says whether a page changed
(ledger._content_sha) -- and before a page goes to the host his strokes are erased, so a note can neither start a job
nor be read as the user's.

HOW THEY REACH THE TABLET: the "got it" note and the work at hand go up as COPIES of the page (sync.push_doc's
`replace`): the page in the mirror, which the host reads and writes, is never touched while a job runs. The last note
is written into the page itself once the host is done, and pushed.

A RETRY BOX: a job that was skipped or failed ends its note with a small box; anything the user writes in it asks for
the job again (box_marks).

Everything here works on a page's BYTES, and refuses to return a page that does not read back as it should.
"""
import io
import os
import time

from rmscene import read_blocks, write_blocks
from rmscene import scene_stream as ss
from rmscene import scene_items as si
from rmscene.crdt_sequence import CrdtSequenceItem
from rmscene.scene_stream import CrdtId
from rmscene.tagged_block_common import LwwValue

LAYER = "PaperDaemon"               # his layer's name, on the page and in the tablet's layer list (render.DAEMON_LAYER)
SIZE = 15.0                         # the lettering's cap height, page units on a Paper Pro page
LEAD = 24.0                         # baseline to baseline
PEN_W = 5                           # the fineliner's width at that size
BOX = 40.0                          # the retry box's side: about 4.5 mm on a Paper Pro, room for a tick


def layer_ids(blocks):
    """The ids of his layer(s) on a page, from its blocks: {(part1, part2)} (render.daemon_layer_ids)."""
    from paperdaemon.pipeline.page import render as R
    return R.daemon_layer_ids(blocks)


def _key(cid):
    return (cid.part1, cid.part2)


def _live_line(b):
    return isinstance(b, ss.SceneLineItemBlock) and isinstance(getattr(b.item, "value", None), si.Line)


def _tombstone(b):
    it = b.item
    return ss.SceneLineItemBlock(parent_id=b.parent_id, item=CrdtSequenceItem(
        item_id=it.item_id, left_id=it.left_id, right_id=it.right_id, deleted_length=1, value=None))


def _next_id(blocks):
    """The first id nothing on the page uses: items, deleted ranges, layers and their values."""
    from paperdaemon.pipeline.draw import next_free_id
    n = next_free_id(blocks)
    for b in blocks:
        if isinstance(b, ss.SceneTreeBlock):
            n = max(n, b.tree_id.part2 + 1)
        elif isinstance(b, ss.TreeNodeBlock):
            g = b.group
            for v in (g.node_id, getattr(g.label, "timestamp", None), getattr(g.visible, "timestamp", None)):
                if isinstance(v, CrdtId):
                    n = max(n, v.part2 + 1)
    return n


def _counts(blocks, ids):
    mine = sum(1 for b in blocks if _live_line(b) and _key(b.parent_id) in ids)
    theirs = sum(1 for b in blocks if _live_line(b) and _key(b.parent_id) not in ids)
    return mine, theirs


# ------------------------------------------------------------------ the page, spliced
# A PAGE IS ITS BLOCKS' FRAMES, end to end after the header: the C pass (fastrm) says where each one starts and ends,
# its kind, and for a stroke its layer, its ids and whether it is erased. A note is a handful of blocks put in and a
# stroke's frame swapped for its tombstone's; everything else is copied byte for byte, so a page of a quarter of a
# million strokes is changed in a moment, not read and written whole. A page the C pass is not sure of goes through
# rmscene instead (_slow).
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


def _frame(block):
    """One block's frame, as it is written in a page."""
    from rmscene.tagged_block_common import HEADER_V6
    buf = io.BytesIO()
    write_blocks(buf, [block])
    return buf.getvalue()[len(HEADER_V6):]


def _tomb(r):
    return _frame(ss.SceneLineItemBlock(parent_id=CrdtId(r[5], r[6]), item=CrdtSequenceItem(
        item_id=CrdtId(r[7], r[8]), left_id=CrdtId(r[9], r[10]), right_id=CrdtId(r[11], r[12]),
        deleted_length=1, value=None)))


def _live_counts(data):
    """(his live strokes, the user's) as the C pass reads the page, or None."""
    got = _scan(data)
    if got is None:
        return None
    rows, rest = got
    ids = layer_ids(rest)
    mine = sum(1 for r in rows if r[0] == LINE and r[14] and (r[5], r[6]) in ids)
    return mine, sum(1 for r in rows if r[0] == LINE and r[14]) - mine, ids


def erase(data, also=()):
    """The page with his strokes erased (tombstoned, as the tablet erases), and any of the user's strokes whose ids are
    in `also` (a tick in the retry box) -> (bytes, how many erased); (data, 0) when there is nothing to erase."""
    got = _scan(data)
    if got is None:
        return _slow_erase(data, also)
    from rmscene.tagged_block_common import HEADER_V6
    rows, rest = got
    ids, also = layer_ids(rest), set(also)
    out, n = [data[:len(HEADER_V6)]], 0
    for r in rows:
        if r[0] == LINE and r[14] and ((r[5], r[6]) in ids or (r[7], r[8]) in also):
            out.append(_tomb(r))
            n += 1
        else:
            out.append(data[r[1] - 8:r[2]])
    if not n:
        return data, 0
    new = b"".join(out)
    before, after = _live_counts(data), _live_counts(new)
    if after is None or after[0] + after[1] != before[0] + before[1] - n or after[0] != 0:
        raise RuntimeError("the page did not read back after erasing the daemon's note")
    return new, n


def with_note(data, strokes):
    """The page with the daemon's note: his old strokes erased, `strokes` (lettering.Drawing strokes: points, widths, tool,
    color, rgba) on his layer, which is made when the page has none. The user's strokes, text and pictures are as they
    were. -> bytes."""
    got = _scan(data)
    if got is None:
        return _slow_with_note(data, strokes)
    from rmscene.tagged_block_common import HEADER_V6
    rows, rest = got
    ids = layer_ids(rest)
    theirs0 = sum(1 for r in rows if r[0] == LINE and r[14] and (r[5], r[6]) not in ids)
    n = _next_id(rest)
    for r in rows:
        if r[0] == LINE:
            n = max(n, r[8] + max(1, r[13]))
    seq = [n]

    def nid():
        k = seq[0]
        seq[0] += 1
        return CrdtId(1, k)
    frames = [_tomb(r) if r[0] == LINE and r[14] and (r[5], r[6]) in ids else data[r[1] - 8:r[2]] for r in rows]
    kinds = [r[0] for r in rows]
    if ids:
        layer = CrdtId(*sorted(ids)[0])
    else:
        # HIS LAYER, made as the tablet makes one: a tree node under the root, its group (named, visible), and its
        # place in the root's list, each beside the blocks of its kind, before the first stroke
        layer = nid()
        g = si.Group(node_id=layer)
        g.label = LwwValue(timestamp=nid(), value=LAYER)
        g.visible = LwwValue(timestamp=nid(), value=True)
        root_items = [b.item for b in rest if isinstance(b, ss.SceneGroupItemBlock) and _key(b.parent_id) == (0, 1)]
        lefts = {_key(i.left_id) for i in root_items}
        tails = [i for i in root_items if _key(i.item_id) not in lefts]
        left = tails[-1].item_id if tails else CrdtId(0, 0)
        news = [(ss.SceneTreeBlock.BLOCK_TYPE, ss.SceneTreeBlock(tree_id=layer, node_id=CrdtId(0, 0), is_update=True,
                                                                  parent_id=CrdtId(0, 1))),
                (ss.TreeNodeBlock.BLOCK_TYPE, ss.TreeNodeBlock(group=g)),
                (ss.SceneGroupItemBlock.BLOCK_TYPE, ss.SceneGroupItemBlock(parent_id=CrdtId(0, 1), item=CrdtSequenceItem(
                    item_id=nid(), left_id=left, right_id=CrdtId(0, 0), deleted_length=0, value=layer)))]
        for kind, blk in news:
            at = max((i for i, k in enumerate(kinds) if k == kind), default=None)
            if at is None:
                at = next((i for i, k in enumerate(kinds) if k == LINE), len(kinds)) - 1
            frames.insert(at + 1, _frame(blk))
            kinds.insert(at + 1, kind)
    # the strokes, hung off the tail of his layer's own run
    mine = [r for r in rows if r[0] == LINE and (r[5], r[6]) == _key(layer)]
    lefts = {(r[9], r[10]) for r in mine}
    tails = [r for r in mine if (r[7], r[8]) not in lefts]
    prev = CrdtId(tails[-1][7], tails[-1][8]) if tails else CrdtId(0, 0)
    for st in strokes:
        pts, widths, tool, color = st[0], st[1], st[2], st[3]
        P = [si.Point(x=float(x), y=float(y), speed=0, direction=0, width=int(widths[i]), pressure=190)
             for i, (x, y) in enumerate(pts)]
        L = si.Line(color=color, tool=tool, points=P, thickness_scale=3.0, starting_length=0.0, move_id=None,
                    color_rgba=None)
        iid = nid()
        frames.append(_frame(ss.SceneLineItemBlock(parent_id=layer, item=CrdtSequenceItem(
            item_id=iid, left_id=prev, right_id=CrdtId(0, 0), deleted_length=0, value=L))))
        prev = iid
    new = data[:len(HEADER_V6)] + b"".join(frames)
    after = _live_counts(new)
    if after is None or _key(layer) not in after[2] or after[0] != len(strokes) or after[1] != theirs0:
        raise RuntimeError("the page did not read back with the daemon's note (%s)" % (after[:2] if after else "unreadable",))
    return new


def box_marks(data, box, pad=6.0):
    """The user's strokes (not his) with a point inside the retry box `box` (x0, y0, x1, y1, page units) -> their
    item ids [(part1, part2)]: a tick, a cross, a scribble -- anything written in it asks for the job again."""
    if not box:
        return []
    x0, y0, x1, y1 = box[0] - pad, box[1] - pad, box[2] + pad, box[3] + pad
    got = _scan(data)
    if got is None:
        return _slow_box_marks(data, (x0, y0, x1, y1))
    import numpy as np
    from paperdaemon.remarkable import fastrm
    rows, rest = got
    ids = layer_ids(rest)
    out = []
    for r in rows:
        if r[0] == LINE and r[14] and (r[5], r[6]) not in ids and r[20]:
            P = np.frombuffer(data, dtype=fastrm.POINT, count=r[20] // fastrm.POINT.itemsize, offset=r[19])
            if ((P["x"] >= x0) & (P["x"] <= x1) & (P["y"] >= y0) & (P["y"] <= y1)).any():
                out.append((r[7], r[8]))
    return out


# ------------------------------------------------------------------ the same, through rmscene (a page the C pass
# is not sure of)
def _slow_erase(data, also=()):
    blocks = list(read_blocks(io.BytesIO(data)))
    ids = layer_ids(blocks)
    also = set(also)
    out, n = [], 0
    for b in blocks:
        if _live_line(b) and (_key(b.parent_id) in ids or _key(b.item.item_id) in also):
            out.append(_tombstone(b))
            n += 1
        else:
            out.append(b)
    if not n:
        return data, 0
    buf = io.BytesIO()
    write_blocks(buf, out)
    new = buf.getvalue()
    back = list(read_blocks(io.BytesIO(new)))
    if len(back) != len(blocks) or sum(1 for b in back if _live_line(b)) != sum(1 for b in blocks if _live_line(b)) - n:
        raise RuntimeError("the page did not read back after erasing the daemon's note")
    return new, n


def _slow_with_note(data, strokes):
    """The page with the daemon's note: his old strokes erased, `strokes` (lettering.Drawing strokes: points, widths, tool,
    color, rgba) on his layer, which is made when the page has none. The user's strokes, text and pictures are as they
    were. -> bytes."""
    blocks = list(read_blocks(io.BytesIO(data)))
    ids = layer_ids(blocks)
    _mine0, theirs0 = _counts(blocks, ids)
    blocks = [_tombstone(b) if _live_line(b) and _key(b.parent_id) in ids else b for b in blocks]
    seq = [_next_id(blocks)]

    def nid():
        k = seq[0]
        seq[0] += 1
        return CrdtId(1, k)
    if ids:
        layer = CrdtId(*sorted(ids)[0])
    else:
        # HIS LAYER, made as the tablet makes one: a tree node under the root, its group (named, visible), and its
        # place in the root's list, each beside the blocks of its kind, before the first stroke
        layer = nid()
        tree = ss.SceneTreeBlock(tree_id=layer, node_id=CrdtId(0, 0), is_update=True, parent_id=CrdtId(0, 1))
        g = si.Group(node_id=layer)
        g.label = LwwValue(timestamp=nid(), value=LAYER)
        g.visible = LwwValue(timestamp=nid(), value=True)
        node = ss.TreeNodeBlock(group=g)
        root_items = [b.item for b in blocks if isinstance(b, ss.SceneGroupItemBlock) and _key(b.parent_id) == (0, 1)]
        lefts = {_key(i.left_id) for i in root_items}
        tails = [i for i in root_items if _key(i.item_id) not in lefts]
        left = tails[-1].item_id if tails else CrdtId(0, 0)
        place = ss.SceneGroupItemBlock(parent_id=CrdtId(0, 1), item=CrdtSequenceItem(
            item_id=nid(), left_id=left, right_id=CrdtId(0, 0), deleted_length=0, value=layer))

        def after_last(kind, new):
            at = max((i for i, b in enumerate(blocks) if isinstance(b, kind)), default=None)
            if at is None:
                at = next((i for i, b in enumerate(blocks) if isinstance(b, ss.SceneLineItemBlock)), len(blocks)) - 1
            blocks.insert(at + 1, new)
        after_last(ss.SceneTreeBlock, tree)
        after_last(ss.TreeNodeBlock, node)
        after_last(ss.SceneGroupItemBlock, place)
    # the strokes, each after the last of his layer's (a run of its own, hung off the layer's tail)
    mine = [b.item for b in blocks if isinstance(b, ss.SceneLineItemBlock) and _key(b.parent_id) == _key(layer)]
    lefts = {_key(i.left_id) for i in mine}
    tails = [i for i in mine if _key(i.item_id) not in lefts]
    prev = tails[-1].item_id if tails else CrdtId(0, 0)
    for st in strokes:
        pts, widths, tool, color = st[0], st[1], st[2], st[3]
        P = [si.Point(x=float(x), y=float(y), speed=0, direction=0, width=int(widths[i]), pressure=190)
             for i, (x, y) in enumerate(pts)]
        L = si.Line(color=color, tool=tool, points=P, thickness_scale=3.0, starting_length=0.0, move_id=None,
                    color_rgba=None)
        iid = nid()
        blocks.append(ss.SceneLineItemBlock(parent_id=layer, item=CrdtSequenceItem(
            item_id=iid, left_id=prev, right_id=CrdtId(0, 0), deleted_length=0, value=L)))
        prev = iid
    buf = io.BytesIO()
    write_blocks(buf, blocks)
    new = buf.getvalue()
    back = list(read_blocks(io.BytesIO(new)))
    ids2 = layer_ids(back)
    mine2, theirs2 = _counts(back, ids2)
    if _key(layer) not in ids2 or mine2 != len(strokes) or theirs2 != theirs0:
        raise RuntimeError("the page did not read back with the daemon's note (%d of %d of his, %d of %d of the user's)"
                           % (mine2, len(strokes), theirs2, theirs0))
    return new


def _slow_box_marks(data, box):
    x0, y0, x1, y1 = box
    blocks = list(read_blocks(io.BytesIO(data)))
    ids = layer_ids(blocks)
    return [_key(b.item.item_id) for b in blocks if _live_line(b) and _key(b.parent_id) not in ids
            and any(x0 <= p.x <= x1 and y0 <= p.y <= y1 for p in b.item.value.points)]


# ------------------------------------------------------------------ what a note says, lettered
def band(frame):
    """(left x, right x, top y, bottom y) of the band the daemon's notes live in, on a page of this frame: above the safe area."""
    from paperdaemon.pipeline import page as PG
    x0, top, x1, _ = PG.safe_area(tuple(frame))
    return x0, x1, 0.0, top


def letter(lines, frame, box=False):
    """`lines` lettered in the band, signed at the end of the last line, with a retry box after the signature when
    `box`. -> (Drawing strokes, the box (x0, y0, x1, y1) or None). Each line is cut to the band's width; lines past what
    the band holds are dropped (the last kept one ends with an ellipsis)."""
    from paperdaemon.pipeline import draw as A
    from paperdaemon.pipeline.draw import lettering as T
    from paperdaemon.pipeline.draw import signature as SIG
    x0, x1, top, bottom = band(frame)
    s = (bottom - top) / 115.0                                 # a Paper Pro page's band is 115 units deep
    size, lead = SIZE * s, LEAD * s
    first = top + lead + 2 * s
    rows = max(1, int((bottom - 4 * s - first) // lead) + 1)
    sig_w = size * 7.5                                         # the signature's room at the end of the last line
    box_w = (BOX * s + size * 5.5) if box else 0.0             # the retry box, at the band's right end, and its word
    width = x1 - x0 - box_w
    wrapped = []
    for ln in lines:
        wrapped += T.wrap(str(ln), size, width) or [""]
    if len(wrapped) > rows:
        wrapped = wrapped[:rows]
        wrapped[-1] = _cut(T, wrapped[-1] + " ...", size, width)
    last = len(wrapped) - 1
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
