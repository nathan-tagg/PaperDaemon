"""The daemon's notes on a page (pipeline/daemon/notes.py): written on the page's own first layer inside the band
across the top, told by his own author id alone (11-22: no layer of his); every write erasing everything of his first, including what he put on the page in a
copy the page never showed back; the user's writing on his layer theirs; a tick in the retry box found; his notes
invisible to the renderer and to the fingerprint that says whether a page changed. And the host's account of its work,
and its reading of the handwriting, where it is."""
import dataclasses
import io
import os

from rmscene import read_blocks, write_blocks
from rmscene import scene_items as si
from rmscene import scene_stream as ss
from rmscene.crdt_sequence import CrdtSequenceItem
from rmscene.scene_stream import CrdtId
from rmscene.tagged_block_common import LwwValue

from paperdaemon.pipeline import TEMPLATES
from paperdaemon.pipeline.daemon import notes as N

FRAME = (1620.0, 2160.0)
DOC, PID = "a" * 8 + "-0000-0000-0000-" + "0" * 12, "b" * 8 + "-0000-0000-0000-" + "0" * 12


def _line(pts, parent, iid, left=CrdtId(0, 0), drawn=False):
    """A stroke as a hand makes it (its pressure and speed vary), or as a machine draws one (`drawn`: render.synthetic)."""
    line = si.Line(color=si.PenColor.BLACK, tool=si.Pen.FINELINER_2, thickness_scale=1.0, starting_length=0.0,
                   move_id=None, color_rgba=None,
                   points=[si.Point(x=x, y=y, speed=0 if drawn else 30 + i, direction=0 if drawn else 64, width=4,
                                    pressure=190 if drawn else 120 + i) for i, (x, y) in enumerate(pts)])
    return ss.SceneLineItemBlock(parent_id=parent, item=CrdtSequenceItem(
        item_id=iid, left_id=left, right_id=CrdtId(0, 0), deleted_length=0, value=line))


def _write(blocks):
    buf = io.BytesIO()
    write_blocks(buf, blocks)
    return buf.getvalue()


def _blocks(data):
    return list(read_blocks(io.BytesIO(data)))


def _page(*strokes, layer_name="Layer 1"):
    """The bundled blank page with the user's `strokes` (lists of points) on its Layer 1, renamed `layer_name`."""
    from paperdaemon import studio
    blocks = _blocks(studio._blank_page_bytes(os.path.dirname(TEMPLATES)))
    node = next(b for b in blocks if isinstance(b, ss.TreeNodeBlock) and getattr(b.group.label, "value", None) == "Layer 1")
    node.group.label = dataclasses.replace(node.group.label, value=layer_name)
    n, prev = 1000, CrdtId(0, 0)
    for pts in strokes:
        blocks.append(_line(pts, node.group.node_id, CrdtId(1, n), prev))
        prev, n = CrdtId(1, n), n + 1
    return _write(blocks)


def _his_layers(blocks):
    from paperdaemon.pipeline.page import render as R
    return R.daemon_layer_ids(blocks)


def _counts(data):
    """(his live strokes, the user's live strokes, his layers placed in the page's list of layers)."""
    mine, theirs = N._live_counts(data)
    blocks = _blocks(data)
    his = _his_layers(blocks)
    placed = sum(1 for b in blocks if isinstance(b, ss.SceneGroupItemBlock) and b.item.value is not None
                 and b.item.deleted_length == 0 and N._key(b.item.value) in his)
    return mine, theirs, placed


def _his_strokes(data):
    """His live strokes' ids: under PaperDaemon's notes author (the page's author table ties it), on any layer."""
    from paperdaemon.pipeline.page import render as R
    blocks = _blocks(data)
    own = N._notes_of(R.author_table(blocks))
    return {N._key(b.item.item_id) for b in blocks if isinstance(b, ss.SceneLineItemBlock) and b.item.value is not None
            and b.item.item_id.part1 in own}


def _first_layer(data):
    """The page's first layer (Layer 1 of the bundled page)."""
    return next(N._key(b.group.node_id) for b in _blocks(data) if isinstance(b, ss.TreeNodeBlock)
                and getattr(b.group.label, "value", None) == "Layer 1")


def _parents_of_his(data):
    from paperdaemon.pipeline.page import render as R
    blocks = _blocks(data)
    own = N._notes_of(R.author_table(blocks))
    return {N._key(b.parent_id) for b in blocks if isinstance(b, ss.SceneLineItemBlock) and b.item.value is not None
            and b.item.item_id.part1 in own}


def _with_daemon_layer(data, author=1):
    """The page with a layer named "Daemon" made by the tablet (as the old notes made one), last in its list -> (bytes,
    the layer's node id)."""
    blocks = _blocks(data)
    lay = CrdtId(author, 300_000)
    last = [b for b in blocks if isinstance(b, ss.SceneGroupItemBlock) and b.parent_id == CrdtId(0, 1)][-1].item.item_id
    g = si.Group(node_id=lay)
    g.label = LwwValue(timestamp=CrdtId(author, 300_001), value="Daemon")
    g.visible = LwwValue(timestamp=CrdtId(author, 300_002), value=True)
    blocks += [ss.SceneTreeBlock(tree_id=lay, node_id=CrdtId(0, 0), is_update=True, parent_id=CrdtId(0, 1)),
               ss.TreeNodeBlock(group=g),
               ss.SceneGroupItemBlock(parent_id=CrdtId(0, 1), item=CrdtSequenceItem(
                   item_id=CrdtId(author, 300_003), left_id=last, right_id=CrdtId(0, 0), deleted_length=0, value=lay))]
    return _write(blocks), lay


def _his_place(blocks):
    his = _his_layers(blocks)
    return next(b for b in blocks if isinstance(b, ss.SceneGroupItemBlock) and b.item.value is not None
                and N._key(b.item.value) in his)


def _dead(data):
    return {N._key(b.item.item_id) for b in _blocks(data)
            if isinstance(b, (ss.SceneLineItemBlock, ss.SceneGroupItemBlock)) and b.item.value is None}


def _mirror(tmp_path, monkeypatch):
    """A one-page notebook the renderer and the ledger read from tmp_path -> its page file."""
    from paperdaemon import ledger as L
    from paperdaemon.pipeline.page import render as R
    (tmp_path / DOC).mkdir()
    monkeypatch.setattr(L, "RM", str(tmp_path))
    monkeypatch.setattr(R, "live_pages", lambda d: [{"id": PID}])
    monkeypatch.setattr(R, "page_file", lambda d, p: str(tmp_path / d / (p + ".rm")))
    monkeypatch.setattr(R, "_anchor_offsets", lambda *a: {})
    monkeypatch.setattr(R, "daemon_layer_name", lambda: "Daemon")
    return tmp_path / DOC / (PID + ".rm")


def _sha(f, data):
    from paperdaemon import ledger as L
    f.write_bytes(data)
    L._CONTENT_CACHE.clear()
    return L.page_state(DOC, PID)["sha"]












def test_a_note_is_his_own_on_the_first_layer_and_every_note_replaces_the_last():
    """11-22, the user's ruling: one page, no layer of his -- "the stroke author is sufficient to know the daemons
    writing". The note goes on the page's first layer under his notes' number (8), tied in the author table to
    PaperDaemon's id for notes; the next note erases the last by that author alone; no layer is made."""
    page = _page([(0.0, 900.0), (60.0, 950.0)], [(-300.0, 500.0), (-250.0, 520.0)])
    strokes, box = N.letter(["On it 2:31 PM -- Notebook p1"], FRAME)
    assert box is None
    a = N.with_note(page, strokes, {})
    assert _counts(a) == (len(strokes), 2, 0)
    blocks = _blocks(a)
    from paperdaemon.pipeline.page import render as R
    table = next(b for b in blocks if isinstance(b, ss.AuthorIdsBlock)).author_uuids
    assert sorted(table) == [1, 8] and table[8] == R.uuid_of("notes") and table[1] != R.uuid_of("notes")
    assert _parents_of_his(a) == {_first_layer(a)}
    groups = lambda d: sorted(N._key(b.item.value) for b in _blocks(d) if isinstance(b, ss.SceneGroupItemBlock)
                              and b.parent_id == CrdtId(0, 1) and b.item.value is not None)
    assert groups(a) == groups(page)                             # the page's list of layers as it was
    b = N.with_note(a, strokes[:3], {})
    assert _counts(b) == (3, 2, 0) and _his_strokes(a) <= _dead(b)
    c, n = N.erase(b, {})
    assert n == 3 and _counts(c) == (0, 2, 0)
    assert N.erase(c, {}) == (c, 0)


def test_the_users_writing_on_an_old_daemon_layer_is_theirs_and_stays(tmp_path, monkeypatch):
    """11-22, Luna p2: the tablet kept drawing on the Daemon layer, each note wiped that layer whole, and the user's
    request went with it -- the job then saw a blank page. On a page whose notes have their own author, a layer named
    "Daemon" is an ordinary layer: what the user writes there is read as the page's and no note erases it; only the
    notes' own strokes, wherever they are, are replaced."""
    from paperdaemon.pipeline.page import render as R
    f = _mirror(tmp_path, monkeypatch)
    strokes, _ = N.letter(["On it."], FRAME)
    noted = N.with_note(_page([(0.0, 900.0), (60.0, 950.0)]), strokes)      # his notes' author is in the table now
    page, lay = _with_daemon_layer(noted)
    written = _write(_blocks(page) + [_line([(10.0, 600.0), (90.0, 640.0)], lay, CrdtId(1, 5000))])
    assert _sha(f, page) != _sha(f, written)                    # the user's stroke there is part of the page
    assert len(R.strokes(DOC, 1)) == 2
    again = N.with_note(written, strokes)
    assert (1, 5000) not in _dead(again) and _counts(again)[:2] == (len(strokes), 2)
    assert _his_strokes(noted) <= _dead(again)                  # the last note, erased by its author
    assert _parents_of_his(again) == {_first_layer(again)}


def test_a_page_with_no_layer_gets_layer_1_for_the_note():
    """A page whose list of layers is empty gets one, named as the tablet names its first (Layer 1); no Daemon layer."""
    blocks = [b for b in _blocks(_page()) if not (isinstance(b, ss.SceneGroupItemBlock) and b.parent_id == CrdtId(0, 1))]
    strokes, _ = N.letter(["On it."], FRAME)
    page = N.with_note(_write(blocks), strokes)
    names = [getattr(b.group.label, "value", None) for b in _blocks(page) if isinstance(b, ss.TreeNodeBlock)]
    assert "Daemon" not in names and _counts(page)[0] == len(strokes)


def test_on_a_page_from_before_everything_on_his_layer_goes_with_the_first_note(tmp_path, monkeypatch):
    """His notes went up as the tablet's author (1) from 0.1.81 to 0.2.30, on his layer: on a page whose author table
    does not name his notes' byte yet, everything on his layer is his (render.notes_own_layers) -- not the page's,
    and gone with the first note under the byte; after it, the user's strokes there are theirs."""
    from paperdaemon.pipeline.page import render as R
    f = _mirror(tmp_path, monkeypatch)
    blocks = _blocks(_page([(0.0, 900.0)]))
    lay = CrdtId(1, 200_000)
    first = next(b for b in blocks if isinstance(b, ss.SceneGroupItemBlock) and b.parent_id == CrdtId(0, 1)).item.item_id
    g = si.Group(node_id=lay)
    g.label = LwwValue(timestamp=CrdtId(1, 200_001), value="Daemon")
    g.visible = LwwValue(timestamp=CrdtId(1, 200_002), value=True)
    blocks += [ss.SceneTreeBlock(tree_id=lay, node_id=CrdtId(0, 0), is_update=True, parent_id=CrdtId(0, 1)),
               ss.TreeNodeBlock(group=g),
               ss.SceneGroupItemBlock(parent_id=CrdtId(0, 1), item=CrdtSequenceItem(
                   item_id=CrdtId(1, 200_003), left_id=CrdtId(0, 0), right_id=first, deleted_length=0, value=lay)),
               _line([(-500.0, 20.0), (-400.0, 30.0)], lay, CrdtId(1, 200_004), drawn=True)]
    before = _write(blocks)
    assert R.notes_own_layers(_blocks(before)) == {(1, 200_000)}
    f.write_bytes(before)
    assert len(R.strokes(DOC, 1)) == 1                          # the user's one stroke: the old note is not the page's
    strokes, _ = N.letter(["On it."], FRAME)
    after = N.with_note(before, strokes, {})
    assert (1, 200_004) in _dead(after) and R.notes_own_layers(_blocks(after)) == set()


def test_his_old_notes_are_erased_and_the_users_writing_beside_them_stays():
    """Before his author id his notes were on a layer named "PaperDaemon", with the tablet's ids; the user's writing
    landed there too, in groups the tablet made inside it."""
    blocks = _blocks(_page([(0.0, 900.0), (60.0, 950.0)]))
    old, group = CrdtId(1, 296), CrdtId(1, 1911)
    g = si.Group(node_id=old)
    g.label = LwwValue(timestamp=CrdtId(1, 297), value="PaperDaemon")
    g.visible = LwwValue(timestamp=CrdtId(1, 298), value=True)
    blocks += [ss.SceneTreeBlock(tree_id=old, node_id=CrdtId(0, 0), is_update=True, parent_id=CrdtId(0, 1)),
               ss.SceneTreeBlock(tree_id=group, node_id=CrdtId(0, 0), is_update=True, parent_id=old),
               ss.TreeNodeBlock(group=g), ss.TreeNodeBlock(group=si.Group(node_id=group)),
               ss.SceneGroupItemBlock(parent_id=CrdtId(0, 1), item=CrdtSequenceItem(
                   item_id=CrdtId(1, 299), left_id=CrdtId(0, 0), right_id=CrdtId(0, 0), deleted_length=0, value=old)),
               ss.SceneGroupItemBlock(parent_id=old, item=CrdtSequenceItem(
                   item_id=CrdtId(1, 1912), left_id=CrdtId(0, 0), right_id=CrdtId(0, 0), deleted_length=0, value=group)),
               _line([(-500.0, 20.0), (-400.0, 30.0)], old, CrdtId(1, 300), drawn=True),
               _line([(-500.0, 40.0), (-400.0, 50.0)], old, CrdtId(1, 301), CrdtId(1, 300), drawn=True),
               _line([(0.0, 300.0), (50.0, 330.0)], group, CrdtId(1, 1913))]
    page = _write(blocks)
    assert _counts(page) == (2, 2, 1)
    clean, n = N.erase(page, {})
    assert n == 2 and _counts(clean) == (0, 2, 1)


def test_what_is_left_under_his_old_author_goes_out_of_the_file():
    """His notes once had an author of their own (218), and the tablet would not open a page holding them: the next
    note takes every trace of it out -- strokes, tombstones, his old layer, its place and the author table's entry --
    and the user's strokes stay as they were."""
    from rmscene.tagged_block_common import HEADER_V6
    blocks = _blocks(_page([(0.0, 900.0), (60.0, 950.0)]))
    old = CrdtId(218, 1)
    g = si.Group(node_id=old)
    g.label = LwwValue(timestamp=CrdtId(218, 2), value="Daemon")
    g.visible = LwwValue(timestamp=CrdtId(218, 3), value=True)
    table = next(i for i, b in enumerate(blocks) if isinstance(b, ss.AuthorIdsBlock))
    blocks[table] = ss.AuthorIdsBlock(author_uuids={**blocks[table].author_uuids, 218: N.AUTHOR_UUID})
    blocks += [ss.SceneTreeBlock(tree_id=old, node_id=CrdtId(0, 0), is_update=True, parent_id=CrdtId(0, 1)),
               ss.TreeNodeBlock(group=g),
               ss.SceneGroupItemBlock(parent_id=CrdtId(0, 1), item=CrdtSequenceItem(
                   item_id=CrdtId(218, 4), left_id=CrdtId(0, 0), right_id=CrdtId(0, 0), deleted_length=0, value=old)),
               _line([(-500.0, 20.0), (-400.0, 30.0)], old, CrdtId(218, 5), drawn=True),
               ss.SceneLineItemBlock(parent_id=old, item=CrdtSequenceItem(item_id=CrdtId(218, 6), left_id=CrdtId(218, 5),
                                                                       right_id=CrdtId(0, 0), deleted_length=1, value=None))]
    strokes, _ = N.letter(["On it."], FRAME)
    page = N.with_note(_write(blocks), strokes, {})
    after = _blocks(page)
    ids = [N._key(b.item.item_id) for b in after if hasattr(b, "item")] + [N._key(b.tree_id) for b in after if isinstance(b, ss.SceneTreeBlock)]
    assert not [k for k in ids if k[0] == 218]
    from paperdaemon.pipeline.page import render as R
    assert sorted(next(b for b in after if isinstance(b, ss.AuthorIdsBlock)).author_uuids) == [1, 8]
    assert _counts(page) == (len(strokes), 1, 0)
    clean, n = N.erase(_write(blocks), {})
    assert n == 1 and _counts(clean) == (0, 1, 0)


def test_a_note_stays_in_the_band_above_the_safe_area():
    x0, x1, top, bottom = N.band(FRAME)
    for lines in (["Done 2:34 PM in 2m 05s: messages: start a chat"], ["a long note " * 60, "and more " * 60]):
        strokes, box = N.letter(lines, FRAME, box=True)
        pts = [p for st in strokes for p in st[0]]
        assert all(x0 - 1 <= x <= x1 + 1 and top <= y <= bottom for x, y in pts)
        assert top <= box[1] < box[3] <= bottom and box[2] <= x1


def test_a_note_is_one_line_and_never_wraps(monkeypatch):
    """ONE message, rewritten each time: when he saw the job, what it is doing, how it ended. Too long, it is cut."""
    from paperdaemon.pipeline.draw import lettering as T
    seen = []
    real = T.text
    monkeypatch.setattr(T, "text", lambda d, s, *a, **k: seen.append(s) or real(d, s, *a, **k))
    N.letter(["Saw it 1:02 PM. Now: step 2 done"], FRAME)
    assert seen == ["Saw it 1:02 PM. Now: step 2 done"]
    seen.clear()
    N.letter(["Saw it 1:02 PM. Finished 1:04 PM in 2 min: " + "a long account " * 40], FRAME, box=True)
    assert seen[1:] == ["retry"] and seen[0].endswith("...")     # the box's word beside it


def test_a_tick_in_the_retry_box_is_found_and_erased_with_the_note():
    strokes, box = N.letter(["Did not work.", "Tick the box to try again."], FRAME, box=True)
    cx, cy = (box[0] + box[2]) / 2, (box[1] + box[3]) / 2
    state = {}
    page = N.with_note(_page([(cx - 6, cy), (cx, cy + 6), (cx + 9, cy - 9)], [(0.0, 900.0), (60.0, 950.0)]), strokes, state)
    tick = N.box_marks(page, box)
    assert len(tick) == 1
    assert N.box_marks(N.with_note(_page([(0.0, 900.0), (60.0, 950.0)]), strokes, {}), box) == []
    clean, n = N.erase(page, state, also=tick)
    assert n == len(strokes) + 1 and _counts(clean) == (0, 1, 0)
    # on a page with typed text the tablet keeps a tick in a group anchored to the text, stored far from where it is
    # drawn: it is found where it is drawn
    layer = next(b.group.node_id for b in _blocks(page) if isinstance(b, ss.TreeNodeBlock)
                 and getattr(b.group.label, "value", None) == "Layer 1")
    moved = _page([(cx - 6 + 572, cy - 297), (cx + 572, cy + 6 - 297)])
    assert N.box_marks(moved, box) == []
    assert len(N.box_marks(moved, box, shifts={N._key(layer): (-572.0, 297.0)})) == 1


def test_the_renderer_never_draws_his_notes(tmp_path, monkeypatch):
    """A page with the daemon's note fingerprints as it did without it, and reads the same strokes; a layer named as his
    is his, whatever is on it."""
    from paperdaemon.pipeline.page import render as R
    f = _mirror(tmp_path, monkeypatch)
    page = _page([(0.0, 900.0), (60.0, 950.0)])
    strokes, _ = N.letter(["On it."], FRAME)
    assert _sha(f, page) == _sha(f, N.with_note(page, strokes, {}))
    assert len(R.strokes(DOC, 1)) == 1 and len(R.strokes(DOC, 1, arrays=True)) == 1
    f.write_bytes(_page([(0.0, 900.0), (60.0, 950.0)], layer_name="Daemon"))
    assert len(R.strokes(DOC, 1)) == 0


def test_in_the_false_mirror_the_note_goes_into_the_page_as_it_is_now(tmp_path, monkeypatch):
    """The false mirror has no tablet to send a copy to: the note goes into the page itself, where its editor shows it,
    and the page reads the same to the host. It is read and written under the page's lock (paths.page_lock, its race
    in test_page_lock), so what the host wrote since the last note is kept under the new one."""
    import paperdaemon.pipeline.daemon as D
    f = _mirror(tmp_path, monkeypatch)
    page = _page([(0.0, 900.0), (60.0, 950.0)])
    before = _sha(f, page)
    monkeypatch.setattr(D.paths, "local_only", lambda: True)
    monkeypatch.setattr(N, "page_file", lambda d, p: str(f))
    monkeypatch.setattr(D, "log", lambda *a, **k: None)
    monkeypatch.setattr(D, "_frame_of", lambda d, p: FRAME)
    D._note_copy(DOC, PID, page, ["On it"], "start")
    mine, users, placed = _counts(f.read_bytes())
    assert mine > 0 and users == 1 and placed == 0
    from paperdaemon import ledger as L
    L._CONTENT_CACHE.clear()
    assert L.page_state(DOC, PID)["sha"] == before                # the host and the fingerprint never see it
    host = _page([(0.0, 900.0), (60.0, 950.0)], [(-300.0, 500.0), (-250.0, 520.0)])
    f.write_bytes(host)                                            # the host wrote the page since the last note
    D._note_copy(DOC, PID, page, ["Done"], "end")
    mine, users, placed = _counts(f.read_bytes())
    assert users == 2 and mine > 0                                 # the host's stroke kept, the note on the page


def test_settings_notes_and_retries_are_off():
    from paperdaemon import settings as S
    assert S.DEFAULTS["daemon"] == {"retries": 0, "page_notes": False}        # (no layer of his since 11-22)


def test_a_failed_job_is_tried_again_as_many_times_as_allowed(monkeypatch):
    import paperdaemon.pipeline.daemon as D
    monkeypatch.setattr(D, "log", lambda *a, **k: None)
    e = {"status": "skipped", "failed": True, "note": "step 1 failed: nobody to text"}
    assert D.next_try(dict(e), 0) is False                   # Retries 0: left as it is
    for n in (1, 2):                                         # Retries 2: twice, then left
        assert D.next_try(e, 2) and e["status"] == "pending" and e["retry"] == {"n": n, "note": e["note"], "request": ""}
        e.update(status="skipped", failed=True)
    assert D.next_try(e, 2) and e["status"] == "skipped" and "retry" not in e
    e.update(status="done", failed=False)                    # it worked: the count starts again
    assert D.next_try(e, 2) and "retries_used" not in e
    nothing = {"status": "skipped", "failed": False, "note": "nothing new on the page"}
    assert D.next_try(nothing, 5) is False and nothing["status"] == "skipped"   # nothing to do is never retried


def test_the_host_reports_what_it_does_for_the_daemon(tmp_path):
    import json
    from paperdaemon.pipeline.host import steps as ST
    p = str(tmp_path / "progress.json")
    ST.begin(p, "doc", 1)
    try:
        ST.event("Read: wrote 'hello'")
        steps = [{"id": 1, "do": "write", "what": "a reply", "status": "todo"},
                 {"id": 2, "do": "draw", "what": "a cat", "status": "todo"}]
        ST.report(steps)
        ST.finish(steps, steps[0])
        ST.finish(steps, steps[1], ok=False, note="nothing drawn")
        with open(p, encoding="utf-8") as f:
            got = json.load(f)
    finally:
        ST.end()
    assert got["events"] == ["Read: wrote 'hello'", "The plan: write: a reply; draw: a cat",
                             "Step 1 of 2 done -- write: a reply", "Step 2 of 2 FAILED -- draw: a cat: nothing drawn"]
    assert (got["done"], got["total"]) == (2, 2)


def test_handwriting_is_read_where_the_render_puts_it(monkeypatch, tmp_path):
    """The render is the whole page and what lies past its frame, from a page point at its top-left: a word the
    reader finds at a pixel belongs to the mark at that point, not at a point scaled into the frame."""
    from PIL import Image
    from paperdaemon import reader
    from paperdaemon.pipeline import host as H
    from paperdaemon.pipeline.host import intake as I
    from paperdaemon.pipeline.page import render as R

    def fake_render(doc, page, out, **k):
        Image.new("RGB", (1700, 3000), "white").save(out)    # wider and much taller than the frame
        return None, (1700, 3000), None, None, (-850.0, -40.0)
    monkeypatch.setattr(R, "render", fake_render)
    monkeypatch.setattr(reader, "read_picture", lambda img, scale=2: [{"text": "hello", "x": 1050, "y": 2640, "w": 80, "h": 30}]
                        if isinstance(img, str) else [])
    monkeypatch.setattr(H, "QUEUE", str(tmp_path))
    monkeypatch.setattr(H, "_frame", lambda: FRAME)
    monkeypatch.setattr(H, "_hide", lambda: None)
    marks = [{"id": 1, "owner": "yours", "count": 5, "bbox": (230, 2610, 300, 2650)},     # where the word is
             {"id": 2, "owner": "yours", "count": 5, "bbox": (-100, 1850, 300, 1950)}]   # where scaling put it
    assert I._mark_words("doc", 1, marks) == {1: "hello"}


def test_the_retry_box_is_on_the_notes_line_at_its_right_end():
    """The user's word (11-11): under the line, at its left, the box sat under the tablet's always-on dot. It is on the
    note's own line, right-aligned after the signature, inside the band; a long note is cut before it."""
    x0, x1, top, bottom = N.band(FRAME)
    strokes, box = N.letter(["Skipped after 1m 34s: " + "a long reason " * 30], FRAME, box=True)
    plain, _ = N.letter(["Skipped after 1m 34s: " + "a long reason " * 30], FRAME)
    text_y = [y for st in plain for (_x, y) in st[0]]
    assert top <= box[1] < box[3] <= bottom and x1 - 200 < box[0] < box[2] <= x1
    assert box[1] < max(text_y) and box[3] > min(text_y)                 # on the same line as the words
    left_of_box = [x for st in strokes for (x, y) in st[0] if x < box[0]]
    assert max(left_of_box) < box[0]                                       # nothing of the note runs into it




def test_on_the_mirror_each_note_goes_into_the_page_with_new_ids_and_up_to_the_tablet(tmp_path, monkeypatch):
    """The Mirror's on-it and progress notes used to go up on copies of the page as handed over, each numbered from the
    same page: every note took the ids of the last, the tablet kept the items it already held, and its old notes piled
    up (11-11: four signatures over two Daemon layers). Now each goes into the page itself, erases the last as the
    tablet erases, takes ids no note had, and the page as written goes up. Once the host has written the page, a note
    waits for the final one (the job's work goes up only with the job's end)."""
    import paperdaemon.pipeline.daemon as D
    f = _mirror(tmp_path, monkeypatch)
    page = _page([(0.0, 900.0), (60.0, 950.0)])
    _sha(f, page)
    sent = []
    monkeypatch.setattr(D.paths, "local_only", lambda: False)
    monkeypatch.setattr(N, "page_file", lambda d, p: str(f))
    monkeypatch.setattr(D, "log", lambda *a, **k: None)
    monkeypatch.setattr(D, "_frame_of", lambda d, p: FRAME)
    monkeypatch.setattr(D, "_push_copy", lambda d, p, data, what: sent.append(data))
    monkeypatch.setitem(D.FLIGHTS, DOC, {"job": {"note_base": page}})
    D._note_copy(DOC, PID, page, ["On it"], "on-it")
    first = _his_strokes(f.read_bytes())
    D._note_copy(DOC, PID, page, ["Now: reading"], "progress")
    data = f.read_bytes()
    second = _his_strokes(data)
    assert first and second and not (set(first) & set(second))      # no id used twice
    assert set(first) <= _dead(data)                                  # the last note erased as the tablet erases
    assert len(sent) == 2 and sent[-1] == data                        # the page as written went up
    host = _page([(0.0, 900.0), (60.0, 950.0)], [(-300.0, 500.0), (-250.0, 520.0)])
    f.write_bytes(host)                                               # the host wrote the page
    D._note_copy(DOC, PID, page, ["Now: drawing"], "progress")
    assert f.read_bytes() == host and len(sent) == 2                  # the note waits for the final one


def test_a_retry_carries_the_request_and_leads_with_what_failed(monkeypatch):
    """11-21, Luna p2: the request came off, the answer never landed, and the retry found a blank page. A retry carries
    the request the failed try read, and its note leads with what did not happen (it had been cut off after 600
    characters of what was done)."""
    import paperdaemon.pipeline.daemon as D
    monkeypatch.setattr(D, "log", lambda *a, **k: None)
    done = "; ".join("erase mark %d" % n for n in range(60))
    e = {"status": "done", "failed": True, "note": done + " [NOT DONE: step 31 (write) failed: no tool call]",
         "last_request": "Research the unsteady vortex particle method"}
    assert D.next_try(e, 1)
    assert e["retry"]["note"].startswith("[NOT DONE: step 31 (write) failed")
    assert e["retry"]["request"] == "Research the unsteady vortex particle method"


def test_an_old_daemon_layer_with_nothing_on_it_goes_out_of_the_list_of_layers():
    """11-25, Luna p3: the page kept its old Daemon layer, empty, and the tablet kept it the layer in use, so the eraser
    (which works on that layer only) touched nothing. A note takes an old Daemon layer with nothing on it out of the
    page's list of layers, as the tablet records a layer the user deletes; one with the user's stroke on it stays."""
    strokes, _ = N.letter(["On it."], FRAME)
    noted = N.with_note(_page([(0.0, 900.0), (60.0, 950.0)]), strokes)
    page, lay = _with_daemon_layer(noted)
    listed = lambda d: {N._key(b.item.value) for b in _blocks(d) if isinstance(b, ss.SceneGroupItemBlock)
                        and b.parent_id == CrdtId(0, 1) and b.item.value is not None}
    assert N._key(lay) in listed(page)
    again = N.with_note(page, strokes)
    assert listed(again) == {_first_layer(again)} and _counts(again)[:2] == (len(strokes), 1)
    assert N.erase(again)[1] == len(strokes) and N._key(lay) not in listed(N.erase(again)[0])
    written = _write(_blocks(page) + [_line([(10.0, 600.0), (90.0, 640.0)], lay, CrdtId(1, 5000))])
    kept = N.with_note(written, strokes)
    assert N._key(lay) in listed(kept) and (1, 5000) not in _dead(kept)
