r"""The daemon's notes on a page (Settings: "Daemon notes"): that he is on it, what the host makes of the page and
does with it, step by step, and how it ended, lettered small in the band across the top of the page, under the
tablet's toolbar, and signed.

THE BAND IS HIS AND NOTHING ELSE IS: every stroke lies above the page's safe area (page.safe_area: the toolbar's zone,
which nothing the user or the host writes may enter), on a layer of his own, named as the user chose (Settings:
daemon.layer, "Daemon" unless they changed it), at the bottom of the tablet's list of layers. The renderer never draws
what is his (render.daemon_stroke), and the fingerprint that says whether a page changed leaves it out
(ledger._content_sha), so a note can neither start a job nor be read as the user's writing. Only the page editor shows
it.

HIS IDS: his notes are written under the page's number for PaperDaemon's notes (render.page_author: 8 unless the page's
author table already ties another), never as the tablet (1) -- the author number his notes once had (218,
render.DAEMON_AUTHOR) left every page it was on unreadable on the tablet -- numbered past every counter on the page.

EVERY WRITE WIPES HIS LAYER (the user's word, 11-11: "It should not care what is on that layer, it should wipe it EVERY
time it wants to write something new to that layer"): every live stroke on it is erased (tombstoned, as the tablet
erases), whoever drew it, and any note of his left elsewhere with it. NOTHING IS KEPT BESIDE THE PAGE: the page itself
says where his layer is and which numbers are free (there was a record, daemon-ink.json, of what he had laid on every
page; once the notes' author numbers changed under it, it hung erase marks on layers the pages no longer had, and the
tablet drew nothing on them). ANYTHING LEFT UNDER HIS OLD AUTHOR (218) is taken out of the file outright -- strokes,
tombstones, its layer and its entry in the author table -- so a page it made unreadable opens again.
Then the note. HIS LAYER ITSELF STAYS, ONE PER PAGE: the first of his the page shows is used again, any other comes out
of the list of layers, and with none a new one is made at the bottom of the tablet's list.

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

from paperdaemon.pipeline.page.render import DAEMON_AUTHOR as LEGACY, author_of

AUTHOR_UUID = uuid.uuid5(uuid.NAMESPACE_DNS, "daemon.paperdaemon")   # his old entry in a page's author table (218)
NOTES = author_of("notes")          # his notes' byte from 0.2.33 to 0.2.60, still his where a page has it
SIZE = 15.0                         # the lettering's cap height, page units on a Paper Pro page
LEAD = 24.0                         # baseline to baseline
PEN_W = 5                           # the fineliner's width at that size
BOX = 24.0                          # the retry box's side: about 2.7 mm on a Paper Pro (40 was too big)
ROOT = (0, 1)                       # the page's list of layers


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


def _mine(r, layers, notes):
    """Is a stroke (a C-pass row) his to erase: ON HIS LAYER, whoever drew it (the user's word, 11-11: "it should not
    care what is on that layer, it should wipe it EVERY time"), or under his notes' author anywhere, or under his old
    one. `layers`: his layers on the page (by name); `notes`: his notes' author numbers there."""
    return (r[5], r[6]) in layers or r[7] in notes or r[7] == LEGACY


def _notes_of(authors):
    """His notes' author numbers on a page with this author table (the table's tie, and the byte of 0.2.33 to 0.2.60)."""
    from paperdaemon.pipeline.page import render as R
    return {n for n, k in R.own_authors(authors).items() if k == "notes"} | {NOTES}


def _live_counts(data):
    """(his live strokes, the user's) as the C pass reads the page, or None."""
    from paperdaemon.pipeline.page import render as R
    got = _scan(data)
    if got is None:
        return None
    rows, rest = got
    layers, notes = _old_layers(rest), _notes_of(R.author_table(rest))
    mine = sum(1 for r in rows if r[0] == LINE and r[14] and _mine(r, layers, notes))
    return mine, sum(1 for r in rows if r[0] == LINE and r[14]) - mine


def _write(data, state=None, strokes=None, also=()):
    """THE ONE WAY THE DAEMON CHANGES A PAGE: everything on his layer erased, whoever drew it, with any note of his
    elsewhere, the user's strokes whose ids are in `also` (a tick in the retry box) erased too, and, given `strokes`,
    the note on his layer. NOTHING IS KEPT BESIDE THE PAGE (the user's word, 11-11: "The daemon shouldn't need that"):
    the page says where his layer is and which numbers are free. `state` is no longer read or written (kept for its
    callers). -> (bytes, how many strokes erased, whether anything changed)."""
    from rmscene.tagged_block_common import HEADER_V6
    from paperdaemon.pipeline import draw as _A
    from paperdaemon.pipeline.page import render as R
    data, rows, blocks = _parts(data)
    others = [b for b in blocks if b is not None]
    layers = _old_layers(others)                     # his layers, by name: wiped, and where the note goes
    authors = R.author_table(others)
    notes = _notes_of(authors)
    me = R.page_author(authors, "notes")           # his notes' number on this page, tied to PaperDaemon's id for notes
    also = set(also)
    theirs0 = sum(1 for r in rows if r[0] == LINE and r[14] and not _mine(r, layers, notes) and (r[7], r[8]) not in also)
    frames, kinds = [], []
    seen, trees, nodes, linked = set(), set(), set(), set()
    erased, changed, table = 0, False, None
    root_items = []
    his_places = {}                                  # each live place of his in the root's list -> (frame, its item)
    for r, b in zip(rows, blocks):
        raw = data[r[1] - 8:r[2]]
        if r[0] == LINE:
            k = (r[7], r[8])
            if r[7] == LEGACY or r[5] == LEGACY:     # under his old author, or on his layer made under it (which goes):
                erased += 1 if r[14] else 0          # out of the file, every trace of it
                changed = True
                continue
            seen.add(k)
            if r[14] and (_mine(r, layers, notes) or k in also):
                raw, erased, changed = _tomb(r), erased + 1, True
        elif isinstance(b, ss.SceneGroupItemBlock):
            it = b.item
            k = _key(it.item_id)
            if k[0] == LEGACY or getattr(it.value, "part1", None) == LEGACY:
                changed = True
                continue
            seen.add(k)
            if _key(b.parent_id) == ROOT:
                root_items.append(it)
                if it.value is not None and it.deleted_length == 0 and _key(it.value) in layers:
                    his_places[_key(it.value)] = (len(frames), it)
        elif isinstance(b, ss.SceneTreeBlock):
            if b.tree_id.part1 == LEGACY:
                changed = True
                continue
            trees.add(_key(b.tree_id))
            if not b.is_update:
                linked.add(_key(b.node_id))
        elif isinstance(b, ss.TreeNodeBlock):
            if b.group.node_id.part1 == LEGACY:
                changed = True
                continue
            nodes.add(_key(b.group.node_id))
        elif isinstance(b, ss.AuthorIdsBlock):
            table = len(frames)
            if LEGACY in b.author_uuids:
                raw = _frame(ss.AuthorIdsBlock(author_uuids={a: u for a, u in b.author_uuids.items() if a != LEGACY}))
                changed = True
        frames.append(raw)
        kinds.append(r[0])
    news = []
    # his ids: past EVERY counter on the page, whatever its author, as the tablet numbers its own
    every = max([0] + [int(r[8]) + max(int(r[13] or 0), 1) - 1 for r in rows if r[0] == LINE])
    n = max(every, _A.next_free_id(others) - 1) + 1
    if strokes is not None:
        if table is None:
            raise RuntimeError("the page has no author table for the daemon's note")
        if str(authors.get(me)) != str(R.uuid_of("notes")):   # the page's author table names his notes' author
            frames[table] = _frame(ss.AuthorIdsBlock(author_uuids={
                **{a: u for a, u in authors.items() if a != LEGACY}, me: R.uuid_of("notes")}))
        # HIS LAYER, ONE PER PAGE, AS THE PAGE HAS IT: the first of his it shows is taken up again, and any other of
        # his comes out of the list of layers (its place erased, as the tablet deletes a layer); with none, a new one,
        # at the bottom of the tablet's list
        if his_places:
            la, ln = min(his_places)
            for lk, (at, it) in sorted(his_places.items()):
                if lk != (la, ln):
                    frames[at] = _frame(ss.SceneGroupItemBlock(parent_id=CrdtId(*ROOT), item=CrdtSequenceItem(
                        item_id=it.item_id, left_id=it.left_id, right_id=it.right_id, deleted_length=1, value=None)))
        else:
            first = _first_layer(root_items)
            la, ln = me, n
            news += _layer_blocks(la, ln, layer_name(), first)
            n += 4
        # THE TABLET'S SECOND RECORD OF A LAYER IT MAKES (tree: the layer's node, not an update, under nothing): without
        # it the tablet listed no Daemon layer and drew nothing on it (the Sonnet page, 11-11)
        if (la, ln) not in linked:
            news.append((ss.SceneTreeBlock.BLOCK_TYPE, _frame(ss.SceneTreeBlock(
                tree_id=CrdtId(me, n), node_id=CrdtId(la, ln), is_update=False, parent_id=CrdtId(0, 0)))))
            n += 1
        prev = CrdtId(0, 0)
        for st in strokes:
            pts, widths, tool, color = st[0], st[1], st[2], st[3]
            P = [si.Point(x=float(x), y=float(y), speed=0, direction=0, width=int(widths[i]), pressure=190)
                 for i, (x, y) in enumerate(pts)]
            L = si.Line(color=color, tool=tool, points=P, thickness_scale=3.0, starting_length=0.0, move_id=None,
                        color_rgba=None)
            iid = CrdtId(me, n)
            news.append((LINE, _frame(ss.SceneLineItemBlock(parent_id=CrdtId(la, ln), item=CrdtSequenceItem(
                item_id=iid, left_id=prev, right_id=CrdtId(0, 0), deleted_length=0, value=L)))))
            prev, n = iid, n + 1
        changed = True
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
    """The page with everything on his layer erased, and any of the user's strokes whose ids are in `also` (a tick in
    the retry box) -> (bytes, how many strokes erased); (data, 0) when there is nothing to erase."""
    new, n, changed = _write(data, None, None, also)
    return (new, n) if changed else (data, 0)


def with_note(data, strokes, state=None):
    """The page with everything on his layer erased and `strokes` (lettering.Drawing strokes: points, widths, tool,
    color, rgba) there. The user's strokes elsewhere, text and pictures are as they were. -> bytes."""
    return _write(data, None, strokes)[0]


def box_marks(data, box, pad=6.0, shifts=None):
    """The user's strokes with a point inside the retry box `box` (x0, y0, x1, y1, page units) -> their item ids
    [(part1, part2)]: a tick, a cross, a scribble -- anything written in it asks for the job again, ON ANY LAYER (a tick
    made on his layer is the user's all the same: told by its author, not its layer). `shifts`: {group (part1, part2):
    (dx, dy)}, where the tablet draws a group it anchored to the typed text (render._anchor_offsets) -- on a page with
    typed text the tablet puts the user's tick in such a group, stored hundreds of units from where it is drawn."""
    if not box:
        return []
    import numpy as np
    from paperdaemon.remarkable import fastrm
    from paperdaemon.pipeline.page import render as R
    data, rows, blocks = _parts(data)
    notes = _notes_of(R.author_table([b for b in blocks if b is not None]))
    shifts = shifts or {}
    out = []
    for r in rows:
        if r[0] == LINE and r[14] and r[7] not in notes and r[7] != LEGACY and r[20]:
            dx, dy = shifts.get((r[5], r[6])) or (0.0, 0.0)
            x0, y0, x1, y1 = box[0] - pad - dx, box[1] - pad - dy, box[2] + pad - dx, box[3] + pad - dy
            P = np.frombuffer(data, dtype=fastrm.POINT, count=r[20] // fastrm.POINT.itemsize, offset=r[19])
            if ((P["x"] >= x0) & (P["x"] <= x1) & (P["y"] >= y0) & (P["y"] <= y1)).any():
                out.append((r[7], r[8]))
    return out


def _layer_blocks(author, n, name, right):
    """His layer (author, n), as the tablet makes one: its tree node under the root, its group (named, visible), and
    its place FIRST in the root's list (the bottom of the tablet's layers, under the user's), before `right`. Ids n (the
    layer), n+1 and n+2 (its name's and visibility's), n+3 (its place), all of `author`."""
    layer = CrdtId(author, n)
    g = si.Group(node_id=layer)
    g.label = LwwValue(timestamp=CrdtId(author, n + 1), value=name)
    g.visible = LwwValue(timestamp=CrdtId(author, n + 2), value=True)
    return [(ss.SceneTreeBlock.BLOCK_TYPE, _frame(ss.SceneTreeBlock(tree_id=layer, node_id=CrdtId(0, 0), is_update=True,
                                                                    parent_id=CrdtId(*ROOT)))),
            (ss.TreeNodeBlock.BLOCK_TYPE, _frame(ss.TreeNodeBlock(group=g))),
            (ss.SceneGroupItemBlock.BLOCK_TYPE, _frame(ss.SceneGroupItemBlock(parent_id=CrdtId(*ROOT), item=CrdtSequenceItem(
                item_id=CrdtId(author, n + 3), left_id=CrdtId(0, 0), right_id=CrdtId(*right), deleted_length=0,
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


# ------------------------------------------------------------------ what a note says, lettered
def band(frame):
    """(left x, right x, top y, bottom y) of the band the daemon's notes live in, on a page of this frame: above the safe area."""
    from paperdaemon.pipeline import page as PG
    x0, top, x1, _ = PG.safe_area(tuple(frame))
    return x0, x1, 0.0, top


def letter(lines, frame, box=False, latest=False):
    """The note: ONE line in the band, `lines` run together, signed at its end, with a retry box when `box`: on the
    same line, right-aligned at the band's right end, after the signature. -> (Drawing strokes, the box (x0, y0, x1,
    y1) or None). It never wraps: a note too long for the line is cut, with an ellipsis, where the signature (and the
    box) begin. (`latest` is kept for its callers; one line is all there is.)"""
    from paperdaemon.pipeline import draw as A
    from paperdaemon.pipeline.draw import lettering as T
    from paperdaemon.pipeline.draw import signature as SIG
    x0, x1, top, bottom = band(frame)
    s = (bottom - top) / 115.0                                 # a Paper Pro page's band is 115 units deep
    size, lead = SIZE * s, LEAD * s
    first = top + lead + 2 * s
    sig_w = size * 0.9 + SIG.signature_width(size * 0.9)       # the signature's room at the end of the last line
    side = BOX * s
    box_w = (side + size * 0.5 + T.measure("retry", size) + size) if box else 0.0   # the box and its word, at the right
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
        # THE BOX ON THE NOTE'S LINE, right-aligned at the band's right end, the word "retry" after it (his word,
        # 11-11: under the line, at the left, it sat under the tablet's always-on dot)
        rw = T.measure("retry", size)
        bx = x1 - rw - size * 0.5 - side
        by = y - (size + side) / 2.0
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
