"""The user's own typed list made a checklist where it is (the ruling, 11-07: native checkboxes): a checkbox step names
the typed paragraphs, the host stages them, and at commit they take the tablet's own checkbox style -- never a drawn
copy beside them. A style is a last-writer-wins value: PaperDaemon's is stamped past every id on the page."""
import io

from rmscene import read_blocks, write_blocks
from rmscene import scene_items as si
from rmscene import scene_stream as ss
from rmscene.crdt_sequence import CrdtSequence, CrdtSequenceItem
from rmscene.scene_items import ParagraphStyle
from rmscene.tagged_block_common import CrdtId, LwwValue

from paperdaemon.pipeline.host import steps as ST


def _typed_page(lines):
    """A blank page with `lines` typed as the tablet types them (author 1), each paragraph styled PLAIN."""
    import os
    from paperdaemon import studio
    from paperdaemon.pipeline import TEMPLATES
    blocks = list(read_blocks(io.BytesIO(studio._blank_page_bytes(os.path.dirname(TEMPLATES)))))
    text = "\n".join(lines)
    items = CrdtSequence([CrdtSequenceItem(item_id=CrdtId(1, 20), left_id=CrdtId(0, 0), right_id=CrdtId(0, 0),
                                           deleted_length=0, value=text)])
    styles, clock = {CrdtId(0, 0): LwwValue(timestamp=CrdtId(1, 15), value=ParagraphStyle.PLAIN)}, 300
    for i, ch in enumerate(text):
        if ch == "\n":
            styles[CrdtId(1, 20 + i)] = LwwValue(timestamp=CrdtId(1, clock), value=ParagraphStyle.PLAIN)
            clock += 1
    blocks.append(ss.RootTextBlock(block_id=CrdtId(0, 0), value=si.Text(items=items, styles=styles, pos_x=-576.0,
                                                                         pos_y=234.0, width=1152.0)))
    buf = io.BytesIO()
    write_blocks(buf, blocks)
    return buf.getvalue()


def _styles(data):
    from paperdaemon.pipeline.page import typed as TY
    tb = next(b for b in read_blocks(io.BytesIO(data)) if isinstance(b, ss.RootTextBlock))
    return {text: (int(getattr(tb.value.styles[k].value, "value", tb.value.styles[k].value)), tb.value.styles[k].timestamp)
            for text, k in TY._para_keys(tb) if k in tb.value.styles}


def test_typed_paragraphs_take_the_tablets_own_checkboxes_stamped_newest():
    from paperdaemon.pipeline.page import typed as TY
    from paperdaemon.pipeline.page import render as R
    page = _typed_page(["Groceries", "milk", "eggs", "bread"])
    out, n = TY.restyle_bytes(page, [("milk", ParagraphStyle.CHECKBOX), ("  eggs ", ParagraphStyle.CHECKBOX_CHECKED),
                                     ("cheese", ParagraphStyle.CHECKBOX)])
    assert n == 2                                        # cheese is not on the page
    st = _styles(out)
    assert st["milk"][0] == 6 and st["eggs"][0] == 7 and st["bread"][0] == 1 and st["Groceries"][0] == 1
    # stamped as PaperDaemon's typed text, one past the stamp each replaced (milk's was 300, eggs' 301): newer than
    # that, and older than the tablet's next change, which takes the page's next item number
    d = R.author_of("typed")
    assert st["milk"][1].part1 == d == 136 and st["milk"][1].part2 == 301 and st["eggs"][1].part2 == 302
    table = next(b for b in read_blocks(io.BytesIO(out)) if isinstance(b, ss.AuthorIdsBlock)).author_uuids
    assert table[d] == R.author_uuid(d)
    assert TY.restyle_bytes(page, [("cheese", ParagraphStyle.CHECKBOX)]) == (page, 0)


def test_a_checkbox_step_names_its_paragraphs():
    got = ST.build([{"do": "checkbox", "what": "the grocery list", "answers": ["para:5"],
                     "targets": ["para:2", "para:3"], "checked": "true"}])
    assert got[0]["targets"] == ["para:2", "para:3"] and got[0]["checked"] is True
    import pytest
    with pytest.raises(ST.StepError):
        ST.build([{"do": "checkbox", "what": "the list", "answers": []}])


def test_the_host_stages_typed_paragraphs_only(monkeypatch):
    from paperdaemon.pipeline.host.job import JOB
    from paperdaemon.pipeline.host.features import write as W
    monkeypatch.setattr(JOB, "listing", {"para:2": {"owner": "user", "text": "milk"},
                                         "para:3": {"owner": "user", "text": "eggs"},
                                         "line:4": {"owner": "user", "text": "bread"}})
    monkeypatch.setattr(JOB, "restyle_typed", [])
    ok, note = W._stage_checkbox(["para:2", "para:3", "line:4"], checked=False)
    assert ok and JOB.restyle_typed == [("milk", 6), ("eggs", 6)] and "line:4" in note
    ok, note = W._stage_checkbox(["line:4"])
    assert not ok


def test_the_plan_is_refused_when_its_checkboxes_go_on_ink_or_on_paragraphs_coming_off(monkeypatch):
    from paperdaemon.pipeline.host import rulings as RL
    from paperdaemon.pipeline.host.job import JOB
    monkeypatch.setattr(JOB, "listing", {"para:1": {"owner": "user", "text": "Make this a checklist"},
                                         "para:2": {"owner": "user", "text": "milk"},
                                         "line:3": {"owner": "user", "text": "eggs"}})
    monkeypatch.setattr(JOB, "new_refs", [])
    base = {"rulings": [{"id": "para:1", "is": "request", "then": "erase"}, {"id": "para:2", "is": "note", "then": "keep"}]}
    good = dict(base, steps=[{"do": "checkbox", "what": "the list", "answers": ["para:1"], "targets": ["para:2"]}])
    assert not [p for p in RL.problems("plan", good) if "checkbox" in p]
    ink = dict(base, steps=[{"do": "checkbox", "what": "the list", "answers": ["para:1"], "targets": ["line:3"]}])
    assert any("not a typed paragraph" in p for p in RL.problems("plan", ink))
    gone = dict(base, steps=[{"do": "checkbox", "what": "the list", "answers": ["para:1"], "targets": ["para:1"]}])
    assert any("ruled to come off" in p for p in RL.problems("plan", gone))
