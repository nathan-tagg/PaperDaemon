"""The daemon's notes on a page (pipeline/daemon/notes.py): written on a layer of his own inside the band across the
top, under his own author id; every write erasing everything of his first, including what he put on the page in a
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
    """His live strokes' ids: machine-drawn, on his layer."""
    from paperdaemon.pipeline.page import render as R
    blocks = _blocks(data)
    his = _his_layers(blocks)
    return {N._key(b.item.item_id) for b in blocks if isinstance(b, ss.SceneLineItemBlock) and b.item.value is not None
            and N._key(b.parent_id) in his and R.synthetic(b.item.value.points)}


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


def test_a_note_is_his_own_and_every_write_erases_everything_of_his_first():
    page = _page([(0.0, 900.0), (60.0, 950.0)], [(-300.0, 500.0), (-250.0, 520.0)])
    strokes, box = N.letter(["On it 2:31 PM -- Notebook p1"], FRAME)
    assert box is None
    state = {}
    a = N.with_note(page, strokes, state)
    assert _counts(a) == (len(strokes), 2, 1)
    blocks = _blocks(a)
    # HE WRITES AS THE TABLET'S OWN AUTHOR: nothing of another author in the page (the tablet will not open such a page)
    assert list(next(b for b in blocks if isinstance(b, ss.AuthorIdsBlock)).author_uuids) == [1]
    assert {N._key(b.item.item_id)[0] for b in blocks if isinstance(b, ss.SceneLineItemBlock)} == {1}
    # his layer goes at the bottom of the list of layers, under the user's
    place = _his_place(blocks).item
    assert N._key(place.left_id) == (0, 0) and place.right_id.part1 == 0
    b = N.with_note(a, strokes[:3], state)                      # the next note: everything of the last one erased
    assert _counts(b) == (3, 2, 1)
    assert _his_strokes(a) <= _dead(b)
    c, n = N.erase(b, state)
    assert n == 3 and _counts(c) == (0, 2, 1)                   # his layer stays: the user may have written on it
    assert N.erase(c, state) == (c, 0)                          # nothing of his left: the page as it is


def test_copies_of_one_page_never_share_ids_and_a_later_one_erases_what_the_earlier_carried():
    """Notes go up as copies made from the page as it was handed over; the tablet merges them. Each has stroke ids
    of its own and the same one layer, and each erases what the ones before it put up, though its base never had it."""
    base = _page([(0.0, 900.0), (60.0, 950.0)])
    state = {}
    s1, _ = N.letter(["On it"], FRAME, latest=True)
    s2, _ = N.letter(["On it", "Read: wrote 'hello'"], FRAME, latest=True)
    c1 = N.with_note(base, s1, state)
    c2 = N.with_note(base, s2, state)
    assert not (_his_strokes(c1) & (_his_strokes(c2) - _dead(c2)))
    assert _his_strokes(c1) <= _dead(c2)
    layers = [{N._key(b.tree_id) for b in _blocks(c) if isinstance(b, ss.SceneTreeBlock) and N._key(b.tree_id) in _his_layers(_blocks(c))}
              for c in (c1, c2)]
    assert layers[0] == layers[1] and len(layers[0]) == 1         # one layer, the same blocks in every copy
    assert _counts(c2) == (len(s2), 1, 1)
    final = N.with_note(base, s1, state)                         # the last note, on the host's page
    assert (_his_strokes(c1) | _his_strokes(c2)) <= _dead(final) and _counts(final) == (len(s1), 1, 1)
    # what the page showed erased when it came is forgotten; what is erased only now is kept
    back = N.with_note(final, s1, state)
    assert len(state["laid"]) == 2 and _counts(back) == (len(s1), 1, 1)


def test_a_layer_the_user_deleted_is_made_anew():
    state = {}
    strokes, _ = N.letter(["On it."], FRAME)
    blocks = _blocks(N.with_note(_page([(0.0, 900.0)]), strokes, state))
    first = state["layer"][0]
    place = _his_place(blocks)
    blocks = [ss.SceneGroupItemBlock(parent_id=b.parent_id, item=dataclasses.replace(b.item, deleted_length=1, value=None))
              if b is place else b for b in blocks]
    again = N.with_note(_write(blocks), strokes, state)
    assert state["layer"][0] != first and _counts(again) == (len(strokes), 1, 1)


def test_a_record_lost_never_makes_a_second_layer_and_two_become_one():
    """The page says which layer is his: a record (daemon-ink.json) lost takes up the layer the page already shows; a
    page that already has two of his (from before) keeps the first and takes the empty other out of the list."""
    strokes, _ = N.letter(["On it."], FRAME)
    page = N.with_note(_page([(0.0, 900.0)]), strokes, {})
    again = N.with_note(page, strokes, {})                      # its record gone
    assert _counts(again) == (len(strokes), 1, 1)
    frames, kinds = [], []
    from rmscene.tagged_block_common import HEADER_V6
    data, rows, _b = N._parts(page)
    for r in rows:
        frames.append(data[r[1] - 8:r[2]]); kinds.append(r[0])
    first = _his_place(_blocks(page)).item.value
    frames, kinds = N._put(frames, kinds, N._layer_blocks(500_000, "Daemon", (first.part1, first.part2)))
    two = data[:len(HEADER_V6)] + b"".join(frames)
    assert _counts(two)[2] == 2
    one = N.with_note(two, strokes, {})
    assert _counts(one) == (len(strokes), 1, 1)


def test_a_record_file_that_cannot_be_read_is_not_written_over(tmp_path, monkeypatch):
    from paperdaemon.pipeline import daemon as D
    ink = tmp_path / "daemon-ink.json"
    ink.write_text('{"x/1": {"next": 5}, "x/2": {"next": 9}}', encoding="utf-8")
    monkeypatch.setattr(D, "INK", str(ink))
    monkeypatch.setattr(D.time, "sleep", lambda s: None)
    real = open
    monkeypatch.setattr("builtins.open", lambda f, *a, **k: (_ for _ in ()).throw(PermissionError("busy")) if str(f) == str(ink) else real(f, *a, **k))
    D._ink_keep("x", "3", {"next": 1})
    monkeypatch.setattr("builtins.open", real)
    assert set(__import__("json").loads(ink.read_text(encoding="utf-8"))) == {"x/1", "x/2"}


def test_the_users_writing_on_his_layer_is_theirs_and_stays(tmp_path, monkeypatch):
    """The tablet writes on whatever layer is current: the user's strokes that land on his layer are read, kept, and
    change the page's fingerprint."""
    from paperdaemon.pipeline.page import render as R
    f = _mirror(tmp_path, monkeypatch)
    state = {}
    strokes, _ = N.letter(["On it."], FRAME)
    page = N.with_note(_page([(0.0, 900.0), (60.0, 950.0)]), strokes, state)
    layer = CrdtId(N.AUTHOR, state["layer"][0])
    written = _write(_blocks(page) + [_line([(10.0, 600.0), (90.0, 640.0)], layer, CrdtId(1, 5000))])
    assert _sha(f, page) != _sha(f, written)
    assert len(R.strokes(DOC, 1)) == 2 and len(R.strokes(DOC, 1, arrays=True)) == 2
    assert _counts(N.with_note(written, strokes, state)) == (len(strokes), 2, 1)


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
    assert list(next(b for b in after if isinstance(b, ss.AuthorIdsBlock)).author_uuids) == [1]
    assert _counts(page) == (len(strokes), 1, 1)
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
    assert n == len(strokes) + 1 and _counts(clean) == (0, 1, 1)
    # on a page with typed text the tablet keeps a tick in a group anchored to the text, stored far from where it is
    # drawn: it is found where it is drawn
    layer = next(b.group.node_id for b in _blocks(page) if isinstance(b, ss.TreeNodeBlock)
                 and getattr(b.group.label, "value", None) == "Layer 1")
    moved = _page([(cx - 6 + 572, cy - 297), (cx + 572, cy + 6 - 297)])
    assert N.box_marks(moved, box) == []
    assert len(N.box_marks(moved, box, shifts={N._key(layer): (-572.0, 297.0)})) == 1


def test_the_renderer_never_draws_his_notes(tmp_path, monkeypatch):
    """A page with the daemon's note fingerprints as it did without it, and reads the same strokes; on a layer named as
    his, what a hand wrote is read (only what a machine drew is his)."""
    from paperdaemon.pipeline.page import render as R
    f = _mirror(tmp_path, monkeypatch)
    page = _page([(0.0, 900.0), (60.0, 950.0)])
    strokes, _ = N.letter(["On it."], FRAME)
    assert _sha(f, page) == _sha(f, N.with_note(page, strokes, {}))
    assert len(R.strokes(DOC, 1)) == 1 and len(R.strokes(DOC, 1, arrays=True)) == 1
    f.write_bytes(_page([(0.0, 900.0), (60.0, 950.0)], layer_name="Daemon"))
    assert len(R.strokes(DOC, 1)) == 1


def test_in_the_false_mirror_the_note_goes_into_the_page_unless_the_host_wrote_it_meanwhile(tmp_path, monkeypatch):
    """The false mirror has no tablet to send a copy to: the note goes into the page itself, where its editor shows it,
    and the page reads the same to the host. A page that changed while the note was made keeps what was written."""
    import paperdaemon.pipeline.daemon as D
    f = _mirror(tmp_path, monkeypatch)
    page = _page([(0.0, 900.0), (60.0, 950.0)])
    before = _sha(f, page)
    monkeypatch.setattr(D.paths, "local_only", lambda: True)
    monkeypatch.setattr(N, "page_file", lambda d, p: str(f))
    monkeypatch.setattr(D, "INK", str(tmp_path / "daemon-ink.json"))
    monkeypatch.setattr(D, "log", lambda *a, **k: None)
    monkeypatch.setattr(D, "_frame_of", lambda d, p: FRAME)
    D._note_copy(DOC, PID, page, ["On it"], "start")
    mine, users, placed = _counts(f.read_bytes())
    assert mine > 0 and users == 1 and placed == 1
    from paperdaemon import ledger as L
    L._CONTENT_CACHE.clear()
    assert L.page_state(DOC, PID)["sha"] == before                # the host and the fingerprint never see it
    host = _page([(0.0, 900.0), (60.0, 950.0)], [(-300.0, 500.0), (-250.0, 520.0)])
    real = N.with_note
    def meanwhile(data, strokes, state):                          # the host writes the page as the note is made
        f.write_bytes(host)
        os.utime(f, ns=(1, 1))
        return real(data, strokes, state)
    monkeypatch.setattr(N, "with_note", meanwhile)
    D._note_copy(DOC, PID, page, ["Done"], "end")
    assert f.read_bytes() == host


def test_settings_notes_and_retries_are_off_and_his_layer_is_named_daemon():
    from paperdaemon import settings as S
    assert S.DEFAULTS["daemon"] == {"retries": 0, "page_notes": False, "layer": "Daemon"}


def test_a_failed_job_is_tried_again_as_many_times_as_allowed(monkeypatch):
    import paperdaemon.pipeline.daemon as D
    monkeypatch.setattr(D, "log", lambda *a, **k: None)
    e = {"status": "skipped", "failed": True, "note": "step 1 failed: nobody to text"}
    assert D.next_try(dict(e), 0) is False                   # Retries 0: left as it is
    for n in (1, 2):                                         # Retries 2: twice, then left
        assert D.next_try(e, 2) and e["status"] == "pending" and e["retry"] == {"n": n, "note": e["note"]}
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
