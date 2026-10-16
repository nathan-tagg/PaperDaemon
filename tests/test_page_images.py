"""Pictures in a group the tablet anchored to the typed text (images._to_page): their stored boxes are offset from the
page, by one amount for the whole group."""
from paperdaemon.pipeline.page import images as IM


def test_a_group_takes_the_offset_its_recorded_pictures_agree_on(monkeypatch):
    # three chess pieces in one anchored group: two where they were placed, and one the player dragged straight up
    # (it keeps its picture, so its hash still matches its old placement record). The group's offset is the one the
    # unmoved pieces agree on, and the dragged piece is read where it is -- not snapped back by its stale record.
    group = (1, 401)
    ims = [{"name": n, "hash": h, "parent": group, "deleted": False, "box": box,
            "quad": [(box[0], box[1]), (box[2], box[1]), (box[2], box[3]), (box[0], box[3])]}
           for n, h, box in (("a", "h1", (0.0, 1362.0, 171.0, 1533.0)),
                             ("b", "h2", (185.0, 1362.0, 356.0, 1533.0)),
                             ("moved", "h3", (370.0, 900.0, 541.0, 1071.0)))]
    records = {"a": {"hash": "h1", "box": [0.0, 1659.0, 171.0, 1830.0]},
               "b": {"hash": "h2", "box": [185.0, 1659.0, 356.0, 1830.0]},
               "moved": {"hash": "h3", "box": [370.0, 1659.0, 541.0, 1830.0]}}    # where it was placed, before the drag
    monkeypatch.setattr(IM, "_anchor_groups", lambda path: {group: (0.0, None)})
    monkeypatch.setattr(IM, "placements", lambda doc, page: records)
    monkeypatch.setattr(IM, "record_for", lambda im, placed, taken: placed[im["name"]])
    out = dict((im["name"], im) for im in IM._to_page(ims, "page.rm", "doc", 1))
    assert out["a"]["box"][1] == 1659.0 and out["b"]["box"][1] == 1659.0      # 297 below their stored boxes
    assert out["moved"]["box"][1] == 900.0 + 297.0                            # where the player put it
    assert not any(im["approx_y"] for im in out.values())


def test_pictures_are_drawn_in_the_tablets_order(tmp_path, monkeypatch):
    # a board drawn on Layer 1 after a group the tablet tied to the text: the group's pictures (chess pieces) are
    # drawn where the group sits among Layer 1's children, so the board lies on top of them -- as the tablet shows
    from rmscene import scene_stream as ss
    from rmscene.crdt_sequence import CrdtSequenceItem
    from rmscene.tagged_block_common import CrdtId
    from paperdaemon.pipeline.page import render as R
    def group_item(item, value, parent):
        return ss.SceneGroupItemBlock(parent_id=CrdtId(*parent), item=CrdtSequenceItem(
            item_id=CrdtId(*item), left_id=CrdtId(0, 0), right_id=CrdtId(0, 0), deleted_length=0, value=CrdtId(*value)))
    blocks = [group_item((0, 13), (0, 11), (0, 1)),            # Layer 1, in the page's root
              group_item((1, 130), (1, 129), (0, 11))]          # the tied group, a child of Layer 1
    page = tmp_path / "p.rm"
    page.write_bytes(b"x")
    monkeypatch.setattr(R, "blocks_of", lambda path: blocks)
    monkeypatch.setattr(IM, "parse", lambda data: [
        {"item": (1, 154), "parent": (1, 129), "deleted": False},    # a piece, in the group
        {"item": (1, 212), "parent": (0, 11), "deleted": False}])    # the board, right on Layer 1, written later
    st = IM.stacking(str(page))
    assert st[(1, 212)] > st[(1, 154)]                                # the board is drawn after: on top
