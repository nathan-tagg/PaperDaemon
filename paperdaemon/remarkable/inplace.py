"""A page of the Mirror (the tablet's own library) edited in place, as the tablet edits a page (add-editable-mirror, D1-D3).

The False Mirror's pages are written anew from the editor's scene (local.write_scene): every layer and stroke under new
ids, ink anchored to the typed text written where it shows. On a tablet page that would replace the page's history and
unhook handwriting from the text it follows, so a Mirror page is written from its own file instead:

- every block the edit did not touch goes back BYTE FOR BYTE (the file is walked by its blocks' frames, each block's
  bytes carried as they are);
- a stroke no longer in the scene stays in the file as the tablet's tombstone: its item id and its neighbors' ids kept,
  `deleted_length` 1, no value, so the links of the strokes around it hold;
- a stroke with no id (new, a piece of a cut stroke, a stroke moved or changed) is added at the end of its group's
  sequence (after the last item, before nothing), under an id after the page's highest, by author 1 -- the tablet
  refuses a page with items of another author (render.HOST_AUTHOR); a stroke whose points, pen or color changed is a
  tombstone and a new stroke;
- typed text is edited by its CRDT: characters kept keep their ids, deleted ones are marked deleted where they are,
  inserted ones are new items between their neighbors; a paragraph's style is keyed by its newline's id;
- ink in a group anchored to the text stays in that group, and a new stroke that names that group goes into it;
- a layer's label or visibility is its node's value with a newer timestamp; a new layer is a new node placed above the
  others; what cannot be written in place exactly (a layer deleted or reordered, the text box moved) is refused with
  the reason, never guessed;
- a picture kept is left as it is; one removed is a tombstone (its asset stays listed, its file beside the page); one
  moved is a tombstone and a new item at its new corners, as a moved stroke is; one added is a new item on the page's
  first layer, its asset listed once (pipeline/page/images.py's own blocks);
- the daemon's layer is left exactly as it is.

SAFE TO WRITE (D2, D3): the scene carries a stamp of the page's bytes as read; a page that changed since is not written
(StalePage). The cloud is asked whether the tablet changed the page since PaperDaemon pulled it (check_cloud, the
module's one call to the cloud, which tests replace); if it did, nothing is written (TabletNewer). Before the first
write of a document, its files are copied as they are into <data>/mirror-backups/<doc>, newest per document.

REACHING THE TABLET: push() sends the document up by PaperDaemon's own sync (sync.push_edited) when the user saves or
closes it; the write is recorded in the job ledger as already seen, so the daemon does not take it for the user's
request."""
import copy
import hashlib
import io
import json
import os
import shutil
import struct

import numpy as np
from rmscene import SceneTree, write_blocks
from rmscene import scene_items as si
from rmscene import scene_stream as ss
from rmscene.crdt_sequence import CrdtSequence, CrdtSequenceItem
from rmscene.tagged_block_common import HEADER_V6, CrdtId, LwwValue

from .. import paths
from . import fastrm, local

ROOT = CrdtId(0, 1)
NONE = CrdtId(0, 0)
AUTHOR = 1                                       # the tablet's own author: every item written here is numbered as its
ITEM_TYPES = (3, 4, 5, 6, 8, 15)                 # glyph, group, stroke, text, tombstone and picture items
LINE_TYPE = ss.SceneLineItemBlock.BLOCK_TYPE
TEXT_TYPE = ss.RootTextBlock.BLOCK_TYPE


class Refused(Exception):
    """The page was not written; `reason` says why, for the editor: "stale", "tablet", "offline" or "cannot"."""
    reason = "cannot"


class StalePage(Refused):
    """The page's file changed since the scene was read from it."""
    reason = "stale"


class TabletNewer(Refused):
    """The tablet changed the page since PaperDaemon pulled it."""
    reason = "tablet"


class CloudUnreachable(Refused):
    """The cloud could not be asked whether the tablet changed the page."""
    reason = "offline"


class CannotWrite(Refused):
    """The edit asks for something that cannot be written in place exactly."""
    reason = "cannot"


def _mirror_only():
    if paths.local_only():
        raise local.NotHere("this is done only in the Mirror; the False Mirror's pages are written by its own engine")


def stamp_of(data):
    """The page's stamp: a digest of its bytes ("none" for a page with no file yet)."""
    return hashlib.sha256(data).hexdigest() if data is not None else "none"


def _page(doc, page_no):
    pid = local.page_id(doc, page_no)
    path = os.path.join(local.M, doc, pid + ".rm")
    data = open(path, "rb").read() if os.path.exists(path) else None
    return pid, path, data


def _blank():
    """What a page with no file yet starts from: the bundled blank page, the same every time (its layer's id is the one
    the scene read from it carries)."""
    from paperdaemon import studio
    return studio._blank_page_bytes(local._pipeline())


# ---------------------------------------------------------------- reading
def read_page(doc, page_no, arrays=False):
    """The page as the editor holds it (local.scene_of), with its ids, and its stamp ("stamp") to write it back with."""
    _pid, _path, data = _page(doc, page_no)
    scene = local.scene_of(doc, page_no, arrays=arrays, data=data if data is not None else _blank())
    scene["stamp"] = stamp_of(data)
    scene["inPlace"] = True
    return scene


# ---------------------------------------------------------------- the page's blocks as they are stored
def _frames(data):
    """[(block type, start, end)] of every block in the page's bytes, walked by their frames (each block: its length, 4
    bytes, then 3 bytes of versions and its type)."""
    if not data.startswith(HEADER_V6):
        raise CannotWrite("the page is not in the tablet's current format")
    out, pos, end = [], len(HEADER_V6), len(data)
    while pos < end:
        if pos + 8 > end:
            raise CannotWrite("the page's blocks do not add up")
        size = int.from_bytes(data[pos:pos + 4], "little")
        if pos + 8 + size > end:
            raise CannotWrite("the page's blocks do not add up")
        out.append((data[pos + 7], pos, pos + 8 + size))
        pos += 8 + size
    return out


def _item_head(body):
    """A scene item block's own fields, read from its bytes in order: (parent, item, left, right, deleted_length), or
    None when the block is not laid out that way."""
    from paperdaemon.pipeline.page import images as IM
    try:
        i, ids = 0, []
        for tag in (0x1F, 0x2F, 0x3F, 0x4F):
            if body[i] != tag:
                return None
            c, i = IM._read_cid(body, i + 1)
            ids.append(CrdtId(*c))
        if body[i] != 0x54:
            return None
        return ids + [struct.unpack_from("<I", body, i + 1)[0]]
    except (IndexError, struct.error):
        return None


def _one(block):
    """One block's bytes, framed, as rmscene writes it."""
    buf = io.BytesIO()
    write_blocks(buf, [block])
    return buf.getvalue()[len(HEADER_V6):]


def _lines_bytes(blocks):
    buf = io.BytesIO()
    fastrm.write_lines(buf, blocks)
    return buf.getvalue()


def _tombstone(head):
    """A stroke erased as the tablet erases one: its parent, its id and its neighbors' ids kept, one id deleted, no
    value."""
    parent, item, left, right, _dl = head
    return _lines_bytes([ss.SceneLineItemBlock(parent_id=parent, item=CrdtSequenceItem(
        item_id=item, left_id=left, right_id=right, deleted_length=1, value=None))])


def _highest(blocks):
    """The highest id author 1 holds on the page: its items, its typed characters, its pictures, its nodes and the
    timestamps of its values (they are counted on the same clock)."""
    from paperdaemon.pipeline import draw as A
    hi = A.next_free_id(blocks, AUTHOR) - 1

    def see(c):
        nonlocal hi
        if isinstance(c, CrdtId) and c.part1 == AUTHOR:
            hi = max(hi, c.part2)

    def lww(v):
        if isinstance(v, LwwValue):
            see(v.timestamp)
            see(v.value)
    for b in blocks:
        if isinstance(b, ss.SceneTreeBlock):
            see(b.tree_id)
        elif isinstance(b, ss.TreeNodeBlock):
            g = b.group
            see(g.node_id)
            for k in ("label", "visible", "anchor_id", "anchor_type", "anchor_threshold", "anchor_origin_x"):
                lww(getattr(g, k, None))
        elif isinstance(b, ss.SceneInfo):
            for k in ("current_layer", "background_visible", "root_document_visible"):
                lww(getattr(b, k, None))
        elif isinstance(b, ss.RootTextBlock):
            for v in b.value.styles.values():
                lww(v)
    return hi


# ---------------------------------------------------------------- comparing a stroke with the one in the file
def _same_line(ln, pts, line, shift):
    """Whether the scene's stroke `ln` (its points `pts`, a fastrm.POINT array) is the file's `line`, shown moved by
    `shift` (its group's place, or None): the same pen, color, width and points, exactly."""
    try:
        if int(ln.get("penCode", -1)) != int(line.tool) or int(ln.get("color", -1)) != int(line.color):
            return False
        rgba = ln.get("colorRgba")
        if (list(rgba) if rgba else None) != (list(line.color_rgba) if line.color_rgba else None):
            return False
        if float(ln.get("thicknessScale") or 0.0) != float(line.thickness_scale):
            return False
    except (TypeError, ValueError):
        return False
    held = fastrm.points_of(line.points)
    if len(held) != len(pts):
        return False
    if not shift or not (shift[0] or shift[1]):
        return held.tobytes() == pts.tobytes()
    for k in ("speed", "width", "direction", "pressure"):
        if not np.array_equal(held[k], pts[k]):
            return False
    # SHOWN MOVED: the editor got the stroke's points moved by its group's place, as rows (added in doubles, then
    # stored as floats) or as the binary form's arrays (added in floats) -- either is the stroke unchanged
    for k, d in (("x", shift[0]), ("y", shift[1])):
        a = (held[k].astype(np.float64) + float(d)).astype(np.float32)
        b = held[k] + np.float32(d)
        if not np.all((pts[k] == a) | (pts[k] == b)):
            return False
    return True


def _moved_back(pts, shift):
    """A new stroke's points as its group stores them: the points shown, less the group's place."""
    if not shift or not (shift[0] or shift[1]):
        return pts
    out = pts.copy()
    out["x"] = (pts["x"].astype(np.float64) - float(shift[0])).astype(np.float32)
    out["y"] = (pts["y"].astype(np.float64) - float(shift[1])).astype(np.float32)
    return out


# ---------------------------------------------------------------- typed text, edited by its CRDT
def _runs(paras):
    """Paragraphs with their runs as one reads them: empty runs dropped, neighbors of one format joined."""
    out = []
    for p in paras or []:
        runs = []
        for r in p.get("runs") or []:
            t = r.get("text") or ""
            f = (bool(r.get("bold")), bool(r.get("italic")))
            if not t:
                continue
            if runs and runs[-1][1] == f:
                runs[-1] = (runs[-1][0] + t, f)
            else:
                runs.append((t, f))
        out.append(((p.get("style") or "body", p.get("list") or None), runs))
    return out


def _same_text(a, b):
    if a is None or b is None:
        return a is None and b is None
    if any(float(a.get(k, 0)) != float(b.get(k, 0)) for k in ("x", "y", "width")):
        return False
    return _runs(a.get("paras")) == _runs(b.get("paras"))


def _tokens(paras):
    """The text as the file holds it, one token a character or a format mark (1/2 bold on/off, 3/4 italic on/off), the
    paragraphs joined by their newlines -- as local._text_block writes it."""
    out, state = [], {"bold": False, "italic": False}
    for i, (_style, runs) in enumerate(_runs(paras)):
        if i:
            out.append("\n")
        for text, (bold, italic) in runs:
            for k, on, off, want in (("bold", 1, 2, bold), ("italic", 3, 4, italic)):
                if want != state[k]:
                    state[k] = want
                    out.append(on if want else off)
            out.extend(text)
    return out


def _edit_text(text, paras, nid):
    """The text block's CRDT (`text`, an si.Text read with its style codes kept) edited to read as `paras`. -> how many
    characters were kept, deleted and inserted."""
    import difflib
    from rmscene.text import expand_text_item
    raw = list(text.items._items.values())
    expanded = {}
    for it in raw:
        for e in expand_text_item(it):
            expanded[e.item_id] = e
    order = CrdtSequence(list(expanded.values())).keys()
    live = [i for i in order if not expanded[i].deleted_length]
    want = _tokens(paras)
    got = [expanded[i].value for i in live]
    after = {k: (order[n + 1] if n + 1 < len(order) else NONE) for n, k in enumerate(order)}
    dead, added, seq = set(), [], []           # seq: the text's tokens after the edit, (id, value)

    def insert(prev, tokens):
        """New items for `tokens`, in order, after `prev` and before what follows it in the file's order."""
        right = after.get(prev, NONE) if prev != NONE else (order[0] if order else NONE)
        k = 0
        while k < len(tokens):
            if isinstance(tokens[k], int):
                value, n = tokens[k], 1
            else:
                n = 1
                while k + n < len(tokens) and not isinstance(tokens[k + n], int):
                    n += 1
                value = "".join(tokens[k:k + n])
            first = nid(n)
            added.append((prev, CrdtSequenceItem(item_id=first, left_id=prev, right_id=right, deleted_length=0,
                                                 value=value)))
            for j in range(n):
                seq.append((CrdtId(first.part1, first.part2 + j), tokens[k + j]))
            prev = CrdtId(first.part1, first.part2 + n - 1)
            k += n
        return prev

    prev = NONE
    for op, i1, i2, j1, j2 in difflib.SequenceMatcher(None, got, want, autojunk=False).get_opcodes():
        if op == "equal":
            for k in range(i1, i2):
                seq.append((live[k], got[k]))
            prev = live[i2 - 1]
            continue
        dead.update(live[i1:i2])
        if j2 > j1:
            insert(prev, want[j1:j2])
            # what follows anchors on the last old character kept, never on a new one (the next op is "equal" or the end)

    # THE ITEMS: one untouched kept as it is; one with characters deleted cut where they are, each piece its own item
    # with its ids and neighbors as the tablet reads them, a deleted piece a tombstone of its length
    by_anchor = {}
    for anchor, item in added:
        by_anchor.setdefault(anchor, []).append(item)
    out = list(by_anchor.pop(NONE, []))
    for it in raw:
        chars = list(expand_text_item(it))
        if it.deleted_length or not any(c.item_id in dead for c in chars):
            out.append(it)
        else:
            k = 0
            while k < len(chars):
                gone = chars[k].item_id in dead
                n = 1
                while k + n < len(chars) and (chars[k + n].item_id in dead) == gone:
                    n += 1
                piece = chars[k:k + n]
                value = "" if gone else (piece[0].value if isinstance(piece[0].value, int) else "".join(c.value for c in piece))
                out.append(CrdtSequenceItem(item_id=piece[0].item_id, left_id=piece[0].left_id, right_id=piece[-1].right_id,
                                            deleted_length=n if gone else 0, value=value))
                k += n
        for c in chars:
            out.extend(by_anchor.pop(c.item_id, []))
    for rest in by_anchor.values():             # anchored on nothing the loop met: never expected, kept all the same
        out.extend(rest)
    text.items = CrdtSequence(out)

    # EACH PARAGRAPH'S STYLE, keyed by the newline before it (the first by 0:0): a style the paragraph already reads as
    # is left as the file has it
    keys = [NONE] + [i for i, v in seq if v == "\n"]
    for key, (style, _runs_) in zip(keys, _runs(paras)):
        old = text.styles.get(key)
        code = int(old.value) if old is not None else None
        if (local.STYLE_OF.get(code, ("body", None)) if old is not None else ("body", None)) == style:
            continue
        text.styles[key] = LwwValue(timestamp=nid(1), value=local.CODE_OF.get(style, 1))
    return {"kept": sum(1 for i, _v in seq if i in expanded), "deleted": len(dead),
            "inserted": sum(1 for i, _v in seq if i not in expanded)}


# ---------------------------------------------------------------- the edit
def edit(doc, page_no, data, scene):
    """The page's bytes `data` with the editor's `scene` written into them in place (see the module's note). -> (the new
    bytes, what was done)."""
    from paperdaemon.pipeline.page import typed as TY
    frames, blocks, stored, heads = _index(data)
    before = local.scene_of(doc, page_no, arrays=True, data=data)

    # the page's groups: which group each sits in, so each stroke's layer is known
    up, alive = {}, set()
    for b in blocks:
        if isinstance(b, ss.SceneGroupItemBlock) and b.item.value is not None and not b.item.deleted_length:
            up[b.item.value] = b.parent_id
            alive.add(b.item.value)

    def layer_of(g):
        seen = 0
        while g in up and up[g] != ROOT and seen < 64:
            g, seen = up[g], seen + 1
        return g if up.get(g) == ROOT else None

    seqs = {}
    for k, head in heads.items():
        seqs.setdefault(head[0], []).append(CrdtSequenceItem(item_id=head[1], left_id=head[2], right_id=head[3],
                                                             deleted_length=head[4], value=0))
    highest = _highest(blocks)
    for head in heads.values():                  # the items' own ids too, strokes among them (not in `blocks`)
        if head[1].part1 == AUTHOR:
            highest = max(highest, head[1].part2 + max(head[4], 1) - 1)
    ids = [highest]

    def nid(n=1):
        first = ids[0] + 1
        ids[0] += n
        return CrdtId(AUTHOR, first)

    repl, done = {}, {"kept": 0, "erased": 0, "added": 0, "text": None, "layers": 0}

    # ---- layers
    daemon = {tuple(L["id"]) for L in before["layers"] if L.get("daemon") and L.get("id")}
    mine = [L for L in before["layers"] if L.get("id") and not L.get("daemon")]
    file_layers = [tuple(L["id"]) for L in mine]
    wanted = [L for L in scene.get("layers") or [] if not L.get("daemon") and not (L.get("id") and tuple(L["id"]) in daemon)]
    named = [tuple(L["id"]) for L in wanted if L.get("id")]
    if len(set(named)) != len(named) or any(i not in file_layers for i in named):
        raise CannotWrite("the save names a layer the page does not have")
    if [i for i in file_layers if i not in named]:
        raise CannotWrite("deleting a layer of a tablet page is not written in place yet")
    if named != file_layers:
        raise CannotWrite("reordering the layers of a tablet page is not written in place yet")
    fresh = False
    for L in wanted:
        if not L.get("id"):
            fresh = True
        elif fresh:
            raise CannotWrite("a new layer goes above the page's own layers")
    nodes = {}
    for k, b in enumerate(blocks):
        if isinstance(b, ss.TreeNodeBlock):
            nodes.setdefault((b.group.node_id.part1, b.group.node_id.part2), []).append(k)
    was = {tuple(L["id"]): L for L in mine}
    for L in wanted:
        if not L.get("id"):
            continue
        lid, old = tuple(L["id"]), was[tuple(L["id"])]
        label, visible = str(L.get("label") or old["label"]), bool(L.get("visible", True))
        if label == old["label"] and visible == old["visible"]:
            continue
        if not nodes.get(lid):
            raise CannotWrite("a layer's settings are not where the page keeps them")
        k = nodes[lid][-1]
        nb = copy.deepcopy(blocks[k])
        if label != old["label"]:
            nb.group.label = LwwValue(timestamp=nid(), value=label)
        if visible != old["visible"]:
            nb.group.visible = LwwValue(timestamp=nid(), value=visible)
        repl[k] = _one(nb)
        done["layers"] += 1

    # ---- strokes
    shifts = {}
    for s_ in (scene.get("shifts") if scene.get("shifts") is not None else before.get("shifts")) or []:
        try:
            shifts[CrdtId(*s_["group"])] = (float(s_["by"][0]), float(s_["by"][1]))
        except (KeyError, TypeError, ValueError, IndexError):
            raise CannotWrite("the save's group places cannot be read")
    claimed, adds = set(), []                    # adds: (scene layer index, target group or None, points, the stroke)
    for n, L in enumerate(wanted):
        lid = CrdtId(*L["id"]) if L.get("id") else None
        for ln in L.get("lines") or []:
            pts = ln.get("points")
            pts = fastrm.points_of(pts) if pts is not None and len(pts) else None
            if pts is None or not len(pts):
                continue
            sid = tuple(ln["id"]) if ln.get("id") else None
            if sid and lid is not None and sid in stored and sid not in claimed:
                _k, parent, line = stored[sid]
                if line is not None and layer_of(parent) == lid and _same_line(ln, pts, line, shifts.get(parent)):
                    claimed.add(sid)
                    done["kept"] += 1
                    continue
            group = CrdtId(*ln["group"]) if ln.get("group") else None
            target = group if (lid is not None and group is not None and group in alive and layer_of(group) == lid) else lid
            adds.append((n, target, pts, ln))
    keep_layers = {CrdtId(*i) for i in file_layers}
    for sid, (k, parent, line) in stored.items():
        if line is None or sid in claimed or layer_of(parent) not in keep_layers:
            continue                             # already erased, kept, or not the user's (the daemon's, outside layers)
        repl[k] = _tombstone(heads[k])
        done["erased"] += 1

    # ---- typed text
    want_text, had_text = scene.get("text", before.get("text")), before.get("text")
    roots = [k for k, (t, _s, _e) in enumerate(frames) if t == TEXT_TYPE]
    text_at = None
    if not _same_text(want_text, had_text):
        if want_text is None:
            raise CannotWrite("the save has no typed text where the page has some; to delete it all, send no paragraphs")
        if len(roots) > 1 or (roots and had_text is None):
            raise CannotWrite("the page's typed text cannot be read exactly, so it is not written in place")
        if had_text is not None and any(float(want_text.get(k, had_text[k])) != float(had_text[k]) for k in ("x", "y", "width")):
            raise CannotWrite("moving or resizing the typed text of a tablet page is not written in place")
        if roots:
            k = roots[0]
            t, s, e = frames[k]
            tb = TY.read_preserved(HEADER_V6 + data[s:e])[0]
            done["text"] = _edit_text(tb.value, want_text.get("paras"), nid)
            repl[k] = _one(tb)
        elif _runs(want_text.get("paras")) and any(r for _s, r in _runs(want_text.get("paras"))):
            tb = local._text_block(want_text, nid)
            text_at = max((k for k, (t, _s, _e) in enumerate(frames) if t == ss.SceneTreeBlock.BLOCK_TYPE), default=len(frames) - 1)
            done["text"] = {"kept": 0, "deleted": 0, "inserted": len([x for x in _tokens(want_text.get("paras")) if isinstance(x, str)])}
            text_new = _one(tb)

    # ---- the page's settings: the typed text and the template shown or hidden
    info_k = next((k for k, b in enumerate(blocks) if isinstance(b, ss.SceneInfo)), None)
    flags = [(f, a) for f, a in (("textVisible", "root_document_visible"), ("templateVisible", "background_visible"))
             if f in scene and bool(scene[f]) != bool(before.get(f, True))]
    if flags:
        if info_k is None:
            raise CannotWrite("the page has no settings block to show or hide its text or template")
        nb = copy.deepcopy(blocks[info_k])
        for f, a in flags:
            setattr(nb, a, LwwValue(timestamp=nid(), value=bool(scene[f])))
        repl[info_k] = _one(nb)

    # ---- pictures: one kept as it is; one gone a tombstone, as the pipeline erases one (images._remove); one moved, or
    # new, a new item at its corners on the page's first layer, its asset listed once (images.insert's own blocks)
    pic_blocks, pics_meant = [], None
    if "images" in scene:
        from paperdaemon.pipeline.page import images as IM

        def sig(p):
            try:
                return (p.get("name"), p.get("key") or "", [[float(x), float(y)] for x, y in p.get("quad") or []])
            except (TypeError, ValueError):
                raise CannotWrite("a picture of the save cannot be read")
        had = {tuple(p["id"]): p for p in before.get("images") or [] if p.get("id")}
        left, news = set(had), []
        for p in scene.get("images") or []:
            key = tuple(p["id"]) if p.get("id") else None
            if key in left and sig(p) == sig(had[key]):
                left.discard(key)
                continue
            news.append(p)
        if left or news:
            frame_of = {(heads[k][1].part1, heads[k][1].part2): k for k, (t, _s, _e) in enumerate(frames) if t == 15 and k in heads}
            for key in left:
                k = frame_of.get(key)
                t, s, e = frames[k] if k is not None else (None, 0, 0)
                tomb = IM._tombstone(data[s + 8:e]) if k is not None else None
                if tomb is None:
                    raise CannotWrite("a picture of the page is laid out in a way that cannot be erased in place")
                repl[k] = struct.pack("<I", len(tomb)) + data[s + 4:s + 8] + tomb
            assets = {}
            for t, s, e in frames:
                if t == 14:
                    for h, aid, _nm, _a, _b in IM._asset_entries(data[s + 8:e]) or []:
                        if aid is not None:
                            assets.setdefault(h, aid)
            for p in news:
                name, quad = p.get("name"), sig(p)[2]
                if not local.picture_path(doc, page_no, name) or len(quad) != 4:
                    raise CannotWrite("a picture of the save has no file beside the page")
                if not file_layers:
                    raise CannotWrite("the page has no layer to put a picture on")
                try:
                    h = bytes.fromhex(p.get("key") or "")
                except ValueError:
                    h = b""
                if len(h) != 16:
                    h = hashlib.md5(name.encode("ascii")).digest()
                if h not in assets:
                    aid = nid()
                    assets[h] = (aid.part1, aid.part2)
                    pic_blocks.append(IM.asset_block(h, name, assets[h]))
                item = nid()
                pic_blocks.append(IM.item_block_quad(file_layers[0], (item.part1, item.part2), assets[h], h, quad))
            pics_meant = len([1 for im in IM.parse(data) if not im["deleted"]]) - len(left) + len(news)
            done["pictures"] = {"erased": len(left) - sum(1 for p in news if p.get("id") and tuple(p["id"]) in left),
                                "moved": sum(1 for p in news if p.get("id") and tuple(p["id"]) in left),
                                "added": sum(1 for p in news if not (p.get("id") and tuple(p["id"]) in left))}

    # ---- new layers, then new strokes, after every block of the page
    tail = []
    lays = {}
    root_last = [CrdtSequence(seqs[ROOT]).keys()[-1] if seqs.get(ROOT) else NONE]
    for n, L in enumerate(wanted):
        if L.get("id"):
            continue
        if not file_layers and not L.get("lines") and not any(a[0] == n for a in adds):
            continue                             # the placeholder of a page with no layer, left empty: nothing to add
        node = nid()
        g = si.Group(node_id=node)
        g.label = LwwValue(timestamp=nid(), value=str(L.get("label") or "Layer %d" % (len(file_layers) + len(lays) + 1)))
        g.visible = LwwValue(timestamp=nid(), value=bool(L.get("visible", True)))
        place = nid()
        tail += [_one(ss.SceneTreeBlock(tree_id=node, node_id=NONE, is_update=True, parent_id=ROOT)),
                 _one(ss.TreeNodeBlock(group=g)),
                 _one(ss.SceneGroupItemBlock(parent_id=ROOT, item=CrdtSequenceItem(
                     item_id=place, left_id=root_last[0], right_id=NONE, deleted_length=0, value=node)))]
        root_last[0] = place
        lays[n] = node
        done["layers"] += 1
    last = {}
    new_lines = []
    for n, target, pts, ln in adds:
        target = target if target is not None else lays.get(n)
        if target is None:
            raise CannotWrite("a stroke has no layer to go in")
        if target not in last:
            last[target] = CrdtSequence(seqs[target]).keys()[-1] if seqs.get(target) else NONE
        rgba = ln.get("colorRgba")
        try:
            line = si.Line(color=local._enum(si.PenColor, ln.get("color", 0)), tool=local._enum(si.Pen, ln.get("penCode", 17)),
                           points=_moved_back(pts, shifts.get(target)), thickness_scale=float(ln.get("thicknessScale") or 1.0),
                           starting_length=0.0, move_id=None, color_rgba=tuple(int(v) for v in rgba) if rgba else None)
        except (TypeError, ValueError):
            raise CannotWrite("a stroke of the save cannot be read")
        iid = nid()
        new_lines.append(ss.SceneLineItemBlock(parent_id=target, item=CrdtSequenceItem(
            item_id=iid, left_id=last[target], right_id=NONE, deleted_length=0, value=line)))
        last[target] = iid
        done["added"] += 1

    # ---- the author table names author 1 when anything new is numbered as it
    if ids[0] > highest:
        k = next((k for k, b in enumerate(blocks) if isinstance(b, ss.AuthorIdsBlock)), None)
        if k is None:
            raise CannotWrite("the page has no author table")
        if AUTHOR not in blocks[k].author_uuids:
            from paperdaemon.pipeline.page import render as R
            repl[k] = _one(ss.AuthorIdsBlock(author_uuids={**blocks[k].author_uuids, AUTHOR: R.HOST_UUID}))

    out = [HEADER_V6]
    for k, (t, s, e) in enumerate(frames):
        out.append(repl.get(k, data[s:e]))
        if k == text_at:
            out.append(text_new)
    out += tail
    out.append(_lines_bytes(new_lines))
    out += pic_blocks
    new = b"".join(out)
    done["strokes"] = sum(1 for _sid, (_k, _p, line) in stored.items() if line is not None) - done["erased"] + done["added"]
    done["untouched"] = len(frames) - len(repl)
    _check(new, len(frames) + (text_at is not None) + len(tail) + len(new_lines) + len(pic_blocks), done["strokes"],
           want_text if done["text"] is not None else None)
    if pics_meant is not None:
        from paperdaemon.pipeline.page import images as IM
        if len([1 for im in IM.parse(new) if not im["deleted"]]) != pics_meant:
            raise RuntimeError("the page's pictures did not read back")
    return new, done


def add_picture(doc, page_no, data):
    """A new picture's file (PNG or JPEG bytes) beside a Mirror page, under a name of its own, for the editor to place
    with its next save. -> {name, width, height}."""
    _mirror_only()
    return local._add_picture(doc, page_no, data)


def _index(data, values=True):
    """The page's blocks as the edit needs them -> (frames [(type, start, end)]; blocks, each read by rmscene, None for a
    stroke; strokes {(part1, part2): (frame index, parent, si.Line or None for a tombstone)}; heads {frame index:
    [parent, item, left, right, deleted_length]} of every item). The strokes in ONE C PASS (fastrm._c_pass), their points
    over the page's bytes, where it covers the page as it is; else every block read (fastrm.read_blocks). Without
    `values`, a stroke's value is only True (the read-back check counts them)."""
    frames = _frames(data)
    blocks, strokes, heads = [], {}, {}

    def add(k, head, line):
        key = (head[1].part1, head[1].part2)
        if key in strokes:
            raise CannotWrite("the page holds one stroke id twice")
        strokes[key] = (k, head[0], line)
        heads[k] = head
    got = fastrm._c_pass(data, rows_only=True)
    if got is not None:
        rows, rest = got
        if len(rows) != len(frames) or any(r[0] != t or r[1] - 8 != s or r[2] != e for r, (t, s, e) in zip(rows.tolist(), frames)):
            got = None
    if got is not None:
        rest = iter(rest)
        try:
            for k, r in enumerate(rows.tolist()):
                if r[0] != LINE_TYPE:
                    blocks.append(next(rest))
                    continue
                blocks.append(None)
                line = None
                if r[14] and not values:
                    line = True
                elif r[14]:
                    rgba = None
                    if r[24]:
                        p = r[25] & 0xFFFFFFFF
                        rgba = ((p >> 16) & 0xFF, (p >> 8) & 0xFF, p & 0xFF, (p >> 24) & 0xFF)
                    line = si.Line(si.PenColor(r[16]), si.Pen(r[15]),
                                   np.frombuffer(data, dtype=fastrm.POINT, count=r[20] // fastrm.POINT.itemsize, offset=r[19]),
                                   struct.unpack("<d", struct.pack("<q", r[17]))[0],
                                   struct.unpack("<f", struct.pack("<I", r[18] & 0xFFFFFFFF))[0],
                                   CrdtId(r[22], r[23]) if r[21] else None, rgba)
                add(k, [CrdtId(r[5], r[6]), CrdtId(r[7], r[8]), CrdtId(r[9], r[10]), CrdtId(r[11], r[12]), r[13]], line)
        except ValueError:                       # a pen or color this reader does not know: read block by block
            got, blocks, strokes, heads = None, [], {}, {}
    if got is None:
        for k, b in enumerate(fastrm.read_blocks(data)):
            if isinstance(b, ss.SceneLineItemBlock):
                it = b.item
                add(k, [b.parent_id, it.item_id, it.left_id, it.right_id, it.deleted_length], it.value)
                b = None
            blocks.append(b)
        if len(blocks) != len(frames):
            raise CannotWrite("the page's blocks could not all be read")
    for k, (t, s, e) in enumerate(frames):
        if t in ITEM_TYPES and k not in heads:
            head = _item_head(data[s + 8:e])
            if head is None:
                raise CannotWrite("an item of the page is not laid out as expected")
            heads[k] = head
    return frames, blocks, strokes, heads


def _check(new, nblocks, strokes, text):
    """The page written reads back: its blocks add up to the blocks meant, its tree builds with every stroke under a
    group it has, the strokes counted are the strokes meant, and the typed text reads as the editor's."""
    got = _frames(new)
    if len(got) != nblocks:
        raise RuntimeError("the page did not read back: %d blocks meant, %d read" % (nblocks, len(got)))
    _f, blocks, stored, _h = _index(new, values=False)
    tree = SceneTree()
    local._build_tree(tree, [b for b in blocks if b is not None])
    if any(parent not in tree for _k, parent, _line in stored.values()):
        raise RuntimeError("the page did not read back: a stroke under a group it does not have")
    live = sum(1 for _k, _p, line in stored.values() if line is not None)
    if live != strokes:
        raise RuntimeError("the page did not read back: %d strokes meant, %d read" % (strokes, live))
    if local._line_blocks_in(new) != sum(1 for t, _s, _e in got if t == LINE_TYPE):
        raise RuntimeError("the page's stroke blocks do not add up")
    if text is not None:
        back = local.scene_text(new)
        if back is None or _read_as(back.get("paras")) != _read_as(text.get("paras")):
            raise RuntimeError("the page's typed text did not read back as written")


def _read_as(paras):
    """Paragraphs as a reader sees them: a text of one empty paragraph is no text."""
    r = _runs(paras)
    return [] if len(r) == 1 and not r[0][1] else r


# ---------------------------------------------------------------- safe to write
def check_cloud(name):
    """THE ONE CALL TO THE CLOUD before a page is written (tests replace it): the page's file as the cloud holds it now
    must be the one PaperDaemon last pulled or pushed."""
    from . import sync
    try:
        cloud, known = sync.cloud_file(name)
    except Exception as ex:
        raise CloudUnreachable("the tablet's library could not be checked, so the page was not saved (%s)" % str(ex)[:160])
    if cloud != known:
        raise TabletNewer("the tablet changed this page since PaperDaemon read it, so PaperDaemon's version was not saved")


def _backups():
    return paths.sub("mirror-backups")


def _doc_files(doc):
    """{name: path} of every file of the document in the Mirror: its own files beside it and everything in its folder."""
    out = {}
    for f in os.listdir(local.M):
        p = os.path.join(local.M, f)
        if f.startswith(doc + ".") and os.path.isfile(p):
            out[f] = p
    top = os.path.join(local.M, doc)
    for dirpath, _dirs, files in os.walk(top):
        for f in files:
            p = os.path.join(dirpath, f)
            out[doc + "/" + os.path.relpath(p, top).replace(os.sep, "/")] = p
    return out


def _seen(doc):
    """The document's files as they are: {name: [size, modified]}."""
    out = {}
    for name, p in _doc_files(doc).items():
        try:
            st = os.stat(p)
            out[name] = [st.st_size, st.st_mtime_ns]
        except OSError:
            pass
    return out


def _written_path(doc):
    return os.path.join(_backups(), doc + ".written.json")


def _record_written(doc):
    """The document as PaperDaemon left it: while it is so, the next write needs no new backup."""
    paths.write_json_atomic(_written_path(doc), _seen(doc))


def backup(doc):
    """THE DOCUMENT AS IT WAS (D3), before PaperDaemon writes it: its files copied into <data>/mirror-backups/<doc>,
    replacing an older copy -- unless the document is still as PaperDaemon itself last left it, whose copy from before
    stands. -> the folder written, or None."""
    folder = os.path.join(_backups(), doc)
    try:
        with open(_written_path(doc), encoding="utf-8") as f:
            left = json.load(f)
    except (OSError, ValueError):
        left = None
    if os.path.isdir(folder) and left == _seen(doc):
        return None
    tmp = folder + ".part"
    shutil.rmtree(tmp, ignore_errors=True)
    for name, p in _doc_files(doc).items():
        dest = os.path.join(tmp, name.replace("/", os.sep))
        os.makedirs(os.path.dirname(dest), exist_ok=True)
        shutil.copy2(p, dest)
    os.makedirs(tmp, exist_ok=True)
    shutil.rmtree(folder, ignore_errors=True)
    os.replace(tmp, folder)
    return folder


def _settle_ledger(doc, pid):
    """The page as written is PaperDaemon's own: a job settled on it stays settled (its page's state is now this one),
    as the daemon's own writes are recorded -- the user's edit in the window is not a request to the daemon."""
    from paperdaemon import ledger
    with ledger.locked():
        led = ledger.load()
        st, touched = None, False
        for e in (led.get("entries") or {}).values():
            if e.get("doc_id") == doc and e.get("page_id") == pid and e.get("status") in ("done", "skipped"):
                st = st or ledger.page_state(doc, pid)
                e["handled_sha"], e["handled_raw"] = st["sha"], st.get("raw")
                touched = True
        if touched:
            ledger.save(led)


# ---------------------------------------------------------------- writing and pushing
def write_in_place(doc, page_no, scene, stamp):
    """The editor's `scene` of a Mirror page written into the page in place (see the module's note), if the page is still
    the one the scene was read from (`stamp`) and the tablet has not changed it. -> {strokes, kept, erased, added, text,
    layers, untouched, changed, stamp (the page's new stamp), version}. Raises a Refused, or local.NotHere in the False
    Mirror."""
    _mirror_only()
    with local._writing:
        pid, path, data = _page(doc, page_no)
        if stamp_of(data) != str(stamp or ""):
            raise StalePage("the page changed since the editor read it; it was not saved")
        check_cloud("%s/%s.rm" % (doc, pid))
        base = data if data is not None else _blank()
        new, done = edit(doc, page_no, base, scene)
        if new == base:                          # nothing changed: no file written (a page with none yet stays so)
            return dict(done, changed=False, stamp=stamp, version=local.page_version(doc, page_no))
        backup(doc)
        paths.write_atomic(path, new)
    _settle_ledger(doc, pid)
    _record_written(doc)
    return dict(done, changed=True, stamp=stamp_of(new), version=local.page_version(doc, page_no))


def push(doc):
    """The document's edits up to the tablet by PaperDaemon's own sync, now (the editor's Ctrl+S, or the document
    closed). A job at work on the notebook is left its push: the edit goes up with the job's work. -> what the push
    said."""
    _mirror_only()
    from paperdaemon import ledger
    from . import sync
    working = [e for e in (ledger.load().get("entries") or {}).values()
               if e.get("doc_id") == doc and e.get("status") == "working"]
    if working:
        return {"skipped": "a job is working on this notebook; the edit goes up with its work", "owed": True}
    pages = sorted({n.split("/", 1)[1][:-3] for n, _k, _h in sync.changed_files(doc) if "/" in n and n.endswith(".rm")})
    r = sync.push_edited(doc, pages or None)
    _record_written(doc)
    return r
