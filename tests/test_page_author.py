"""PaperDaemon's strokes say so themselves (his design, 11-07): a stroke keeps its author in one byte, and everything
PaperDaemon writes is numbered 100kkkkk -- the top three bits say it is PaperDaemon's, the low five what it was. All
of 128-159 open on the tablet (measured, a page per number from 1 to 512). Nothing is kept beside the page."""
import io

from rmscene import read_blocks
from rmscene import scene_items as si
from rmscene import scene_stream as ss
from rmscene.crdt_sequence import CrdtSequenceItem
from rmscene.scene_stream import CrdtId
from rmscene.tagged_block_common import LwwValue

from paperdaemon.pipeline.daemon import notes as N
from paperdaemon.pipeline.page import render as R


def test_each_kind_has_its_byte_and_every_one_opens_on_the_tablet():
    got = {k: R.author_of(k) for k in R.KINDS}
    assert got == {"other": 128, "written": 129, "decomp": 130, "svg": 131, "sketch": 132, "markup": 133,
                   "notes": 134, "picture": 135, "typed": 136}
    assert all(a in R.TABLET_OPENS for a in got.values())
    assert R.author_of(None) == 128 and R.author_of("nonsense") == 128


def test_the_byte_alone_says_whose_and_what():
    assert [a for a in range(256) if R.is_own(a)] == list(range(128, 160))
    assert not any(R.is_own(a) for a in (0, 1, 2, 127, 160, 218, 255))
    assert R.kind_of_author(130) == "decomp" and R.kind_of_author(134) == "notes"
    assert R.kind_of_author(1) is None and R.kind_of_author(159) == "other"


def test_each_kind_is_its_own_writer_in_the_pages_author_table():
    ids = {R.author_uuid(R.author_of(k)) for k in R.KINDS}
    assert len(ids) == len(R.KINDS) and R.author_uuid(128) == R.HOST_UUID


def test_a_drawings_strokes_carry_their_kind_and_a_steps_untold_ones_take_its_own():
    from paperdaemon.pipeline import draw as A
    d = A.Drawing()
    d.stroke([(0, 0), (10, 10)])                         # said nothing of what it is
    d.kind = "markup"
    d.hl([(0, 20), (10, 20)], (255, 230, 0, 120))       # drawn as a mark-up
    d.kind = None
    d.strokes.append(([(0, 30), (10, 30)], [4, 4], si.Pen.FINELINER_2, si.PenColor.BLACK, None))   # added raw
    d.tag(1, "written")
    kinds = [getattr(s, "kind", None) for s in d.strokes]
    assert kinds == [None, "markup", "written"]           # tag never overrides what a stroke already says
    pts, widths, tool, color, rgba = d.strokes[1][:5]    # still a stroke as every reader unpacks one
    assert tool == si.Pen.HIGHLIGHTER_2


def _blocks(data):
    return list(read_blocks(io.BytesIO(data)))


def test_notes_laid_as_the_tablets_author_are_erased_and_the_next_goes_up_as_paperdaemons_note():
    """From 0.1.81 to 0.2.30 his notes went up as the tablet's author (1), on a layer of his made under it. The next note
    takes that layer up (never a second one), erases what is on it, and goes up under the notes' byte (134); a record
    of what was laid then (four numbers, no layer author) still erases strokes a copy of the page never showed."""
    import os
    from paperdaemon import studio
    from paperdaemon.pipeline import TEMPLATES
    from test_daemon_notes import FRAME, _counts, _dead, _line, _write
    blocks = _blocks(studio._blank_page_bytes(os.path.dirname(TEMPLATES)))
    first = next(b for b in blocks if isinstance(b, ss.SceneGroupItemBlock) and b.parent_id == CrdtId(0, 1)).item.item_id
    lay = CrdtId(1, 200_000)
    g = si.Group(node_id=lay)
    g.label = LwwValue(timestamp=CrdtId(1, 200_001), value="Daemon")
    g.visible = LwwValue(timestamp=CrdtId(1, 200_002), value=True)
    blocks += [ss.SceneTreeBlock(tree_id=lay, node_id=CrdtId(0, 0), is_update=True, parent_id=CrdtId(0, 1)),
               ss.TreeNodeBlock(group=g),
               ss.SceneGroupItemBlock(parent_id=CrdtId(0, 1), item=CrdtSequenceItem(
                   item_id=CrdtId(1, 200_003), left_id=CrdtId(0, 0), right_id=first, deleted_length=0, value=lay)),
               _line([(-500.0, 20.0), (-400.0, 30.0)], lay, CrdtId(1, 200_004), drawn=True),
               _line([(0.0, 900.0), (60.0, 950.0)], CrdtId(0, 11), CrdtId(1, 1000))]
    page = _write(blocks)
    assert _counts(page) == (1, 1, 1)
    state = {"author": 1, "next": 200_010, "layer": [200_000, first.part1, first.part2, "Daemon", 1],
             "laid": [[200_000, 200_005, 200_006, 1]]}
    strokes, _ = N.letter(["On it."], FRAME)
    after = N.with_note(page, strokes, state)
    assert _counts(after) == (len(strokes), 1, 1)                 # his old layer taken up: still one layer
    bl = _blocks(after)
    new = [b for b in bl if isinstance(b, ss.SceneLineItemBlock) and b.item.value is not None and b.parent_id == lay]
    assert len(new) == len(strokes) and {b.item.item_id.part1 for b in new} == {8}
    assert {(1, 200_004), (1, 200_005), (1, 200_006)} <= _dead(after)
    table = next(b for b in bl if isinstance(b, ss.AuthorIdsBlock)).author_uuids
    assert table[8] == R.uuid_of("notes") and table[1] != R.uuid_of("notes")
    assert state["author"] == 8 and state["layer"][4] == 1 and state["laid"][-1][3:] == [8, 1]
