"""The daemon's notes on a page (pipeline/daemon/notes.py): written on a layer of his own inside the band across the
top, replaced and erased without touching the user's strokes, a tick in the retry box found, and his layer invisible to
what reads a page for the host and to the fingerprint that says whether it changed."""
import io
import os

from rmscene import read_blocks, write_blocks
from rmscene import scene_items as si
from rmscene import scene_stream as ss
from rmscene.crdt_sequence import CrdtSequenceItem
from rmscene.scene_stream import CrdtId

from paperdaemon.pipeline import TEMPLATES
from paperdaemon.pipeline.daemon import notes as N

FRAME = (1620.0, 2160.0)


def _page(*strokes):
    """The bundled blank page with the user's `strokes` (lists of points) on its Layer 1."""
    from paperdaemon import studio
    data = studio._blank_page_bytes(os.path.dirname(TEMPLATES))
    blocks = list(read_blocks(io.BytesIO(data)))
    layer = next(b.group.node_id for b in blocks
                 if isinstance(b, ss.TreeNodeBlock) and getattr(b.group.label, "value", None) == "Layer 1")
    n, prev = N._next_id(blocks) + 10, CrdtId(0, 0)
    for pts in strokes:
        line = si.Line(color=si.PenColor.BLACK, tool=si.Pen.FINELINER_2, thickness_scale=1.0, starting_length=0.0,
                       move_id=None, color_rgba=None,
                       points=[si.Point(x=x, y=y, speed=0, direction=0, width=4, pressure=190) for x, y in pts])
        iid = CrdtId(1, n)
        blocks.append(ss.SceneLineItemBlock(parent_id=layer, item=CrdtSequenceItem(
            item_id=iid, left_id=prev, right_id=CrdtId(0, 0), deleted_length=0, value=line)))
        prev, n = iid, n + 1
    buf = io.BytesIO()
    write_blocks(buf, blocks)
    return buf.getvalue()


def _counts(data):
    blocks = list(read_blocks(io.BytesIO(data)))
    return N._counts(blocks, N.layer_ids(blocks))


def test_a_note_is_written_replaced_and_erased_and_the_users_strokes_stay():
    page = _page([(0.0, 900.0), (60.0, 950.0)], [(-300.0, 500.0), (-250.0, 520.0)])
    strokes, box = N.letter(["Got it 2:31 PM -- Notebook p1. On it now."], FRAME)
    assert box is None
    a = N.with_note(page, strokes)
    assert _counts(a) == (len(strokes), 2)
    b = N.with_note(a, strokes[:3])                      # the next note takes the last one's place
    assert _counts(b) == (3, 2)
    c, n = N.erase(b)
    assert n == 3 and _counts(c) == (0, 2)
    assert N.erase(c) == (c, 0)                          # nothing of his left: the page as it is


def test_a_note_stays_in_the_band_above_the_safe_area():
    x0, x1, top, bottom = N.band(FRAME)
    for lines in (["Done 2:34 PM in 2m 05s: messages: start a chat"], ["a long note " * 60, "and more " * 60]):
        strokes, box = N.letter(lines, FRAME, box=True)
        pts = [p for st in strokes for p in st[0]]
        assert all(x0 - 1 <= x <= x1 + 1 and top <= y <= bottom for x, y in pts)
        assert top <= box[1] < box[3] <= bottom and box[2] <= x1


def test_a_tick_in_the_retry_box_is_found_and_erased_with_the_note():
    strokes, box = N.letter(["Didn't work.", "Tick the box to try again."], FRAME, box=True)
    cx, cy = (box[0] + box[2]) / 2, (box[1] + box[3]) / 2
    page = N.with_note(_page([(cx - 6, cy), (cx, cy + 6), (cx + 9, cy - 9)], [(0.0, 900.0), (60.0, 950.0)]), strokes)
    tick = N.box_marks(page, box)
    assert len(tick) == 1
    assert N.box_marks(N.with_note(_page([(0.0, 900.0), (60.0, 950.0)]), strokes), box) == []
    clean, n = N.erase(page, also=tick)
    assert n == len(strokes) + 1 and _counts(clean) == (0, 1)


def test_his_layer_is_not_the_page(tmp_path, monkeypatch):
    """A page with the daemon's note fingerprints as it did without it, and reads the same strokes for the host."""
    from paperdaemon import ledger as L
    from paperdaemon.pipeline.page import render as R
    page = _page([(0.0, 900.0), (60.0, 950.0)])
    doc, pid = "a" * 8 + "-0000-0000-0000-" + "0" * 12, "b" * 8 + "-0000-0000-0000-" + "0" * 12
    (tmp_path / doc).mkdir()
    (tmp_path / doc / (pid + ".rm")).write_bytes(page)
    monkeypatch.setattr(L, "RM", str(tmp_path))
    before = L.page_state(doc, pid)["sha"]
    strokes, _ = N.letter(["Got it."], FRAME)
    (tmp_path / doc / (pid + ".rm")).write_bytes(N.with_note(page, strokes))
    L._CONTENT_CACHE.clear()
    assert L.page_state(doc, pid)["sha"] == before
    monkeypatch.setattr(R, "live_pages", lambda d: [{"id": pid}])
    monkeypatch.setattr(R, "page_file", lambda d, p: str(tmp_path / d / (p + ".rm")))
    monkeypatch.setattr(R, "_anchor_offsets", lambda *a: {})
    assert len(R.strokes(doc, 1)) == 1


def test_notes_and_retries_are_off_until_the_user_turns_them_on():
    from paperdaemon import settings as S
    assert S.DEFAULTS["daemon"] == {"retries": 0, "page_notes": False}


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
