r"""Images placed on a page -- a "capture" from the reMarkable app -- which rmscene 0.8 does not
know (it reports block types 14 and 15 as unknown and skips them).

Read off a page where a picture was placed with the app:

  * the picture itself is a separate file in the document, `<doc>/<page>/<asset>.png`, which
    the cloud lists beside the .rm files (rm_cloud.WANT pulls .png/.jpg now);
  * block type 14 declares the asset: a 16-byte content hash and the asset's file name;
  * block type 15 is a scene item (parent, item id, left/right, deleted_length) whose value is
    a textured quad: the same 16-byte hash, then 16 floats -- four corners as (x, y, u, v) in
    PAGE coordinates (x centered at 0 like strokes, y from the top) -- and a triangle index list.

This module walks the raw block headers itself (4-byte length, 3 version bytes, 1 type byte, as
rmscene does) so it never depends on rmscene understanding the blocks.

    for im in rm_images.items(doc, page_no):
        im["path"], im["box"]          # the PNG on disk (or None), (x0, y0, x1, y1) on the page
"""
import glob
import os
from paperdaemon import paths
import re
import struct

HERE = os.path.dirname(os.path.abspath(__file__))
from paperdaemon.remarkable.sync import MIRROR as _LIBRARY
RM = os.environ.get("RM_CACHE") or _LIBRARY
_NAME = re.compile(rb"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}\.(?:png|jpg|jpeg)")
_QUAD = re.compile(rb"\x3c\x41\x00\x00\x00\x10")      # sub-block id 3, 65 bytes: count 16 then floats
_HASH16 = re.compile(rb"\x2c\x10\x00\x00\x00")           # sub-block id 2, 16 bytes: the asset hash


def blocks(data):
    """[(type, body)] straight off the file, tolerant of anything rmscene cannot read."""
    out = []
    i = 43                                              # the .rm v6 header
    n = len(data)
    while i + 8 <= n:
        ln, = struct.unpack_from("<I", data, i)
        bt = data[i + 7]
        out.append((bt, data[i + 8:i + 8 + ln]))
        i += 8 + ln
    return out


def has_images(data):
    return any(bt == 15 for bt, _ in blocks(data))


def max_author_id(body):
    """The largest part2 of any author-1 CrdtId among a block body's leading id tags (parent,
    item, left, right) and its value's ids -- so stroke ids never land on a picture's."""
    best = 0
    i = 0
    n = len(body)
    while i < n:
        tag = body[i]
        t = tag & 0xF
        if t == 0xF and i + 2 < n:
            p1 = body[i + 1]
            j = i + 2
            v, sh = 0, 0
            while j < n:
                b = body[j]
                j += 1
                v |= (b & 0x7F) << sh
                sh += 7
                if not b & 0x80:
                    break
            if p1 == 1:
                best = max(best, v)
            i = j
        elif t == 0xC and i + 5 <= n:
            i += 5                                  # step into the sub-block, keep scanning
        elif t == 0x4:
            i += 5
        elif t == 0x8:
            i += 9
        elif t == 0x1:
            i += 2
        else:
            i += 1                                  # a count byte or a float: keep walking
    return best


def strip(data):
    """The page bytes without any picture blocks (the assets on disk are the caller's to remove)."""
    out = bytearray(data[:43])
    for bt, body in blocks(data):
        if bt in (14, 15):
            continue
        # re-emit with the header the file had: we only know the type, so use the app's versions
        ver = (3, 3) if bt == 14 else (2, 2)
        out += struct.pack("<I", len(body)) + bytes([0, ver[0], ver[1], bt]) + body
    return bytes(out)


def remove_in_box(doc, page_no, box, page_id=None):
    """Take off the page every picture whose center lies inside `box` (x0, y0, x1, y1). Returns
    how many. Their blocks go, their files go; everything else stays byte for byte."""
    from paperdaemon.pipeline.page import render as R
    d = R.find_doc(doc) if hasattr(R, "find_doc") else doc
    pid = page_id or R.live_pages(d)[page_no - 1]["id"]
    path = os.path.join(RM, d, pid + ".rm")
    data = open(path, "rb").read()
    x0, y0, x1, y1 = (float(v) for v in box)
    # in PAGE coordinates, the frame every caller's box is in (an anchored picture's raw quad is
    # not -- see _to_page)
    live = [im for im in _to_page([dict(i) for i in parse(data) if not i["deleted"]], path, d, page_no)
            if not im["deleted"]]
    # A PICTURE'S OWN BOX NAMES THAT PICTURE. A redo, an "erase picture:N" and erase_all all pass
    # the picture's own box, and by the center rule alone a second picture whose center fell inside
    # it went too -- two overlapping week calendars on one page, one named, both would
    # have gone, while the preview (rm_render hides by exact box) showed the second one staying.
    # Only a box that is no picture's own falls back to "every picture centered inside it".
    victims = [im for im in live if all(abs(float(a) - b) < 1.5 for a, b in zip(im["box"], (x0, y0, x1, y1)))]
    if not victims:
        for im in live:
            cx = (im["box"][0] + im["box"][2]) / 2.0
            cy = (im["box"][1] + im["box"][3]) / 2.0
            if x0 <= cx <= x1 and y0 <= cy <= y1:
                victims.append(im)
    return _remove(d, pid, path, data, live, victims)


def remove_items(doc, page_no, items, page_id=None):
    """Take these pictures off the page by their item ids ((author, n), as parse() gives them) --
    for two pictures in the same place, where a box cannot tell them apart. -> how many."""
    from paperdaemon.pipeline.page import render as R
    d = R.find_doc(doc) if hasattr(R, "find_doc") else doc
    pid = page_id or R.live_pages(d)[page_no - 1]["id"]
    path = os.path.join(RM, d, pid + ".rm")
    data = open(path, "rb").read()
    want = set(tuple(i) for i in items)
    live = [im for im in parse(data) if not im["deleted"]]
    return _remove(d, pid, path, data, live, [im for im in live if im.get("item") in want])


def _remove(d, pid, path, data, live, victims):
    if not victims:
        return 0
    # ERASED THE WAY THE TABLET ERASES: each victim's item becomes a tombstone (its ids kept, so the
    # sequence stays linked), and only its own asset leaves the asset list -- the tablet keeps every
    # asset of a page in one block 14 (_asset_entries), so dropping "the block that holds this hash"
    # dropped them all. An asset another live picture still shows stays.
    victim_ids = set(im["item"] for im in victims if im.get("item"))
    keep_h = set(bytes.fromhex(im["hash"]) for im in live if im not in victims and im["hash"])
    drop_h = set(bytes.fromhex(im["hash"]) for im in victims if im["hash"]) - keep_h
    out = bytearray(data[:43])
    gone, kept_names = set(), set()
    i = 43
    while i + 8 <= len(data):
        ln, = struct.unpack_from("<I", data, i)
        bt, head = data[i + 7], data[i + 4:i + 8]
        body = data[i + 8:i + 8 + ln]
        new = body
        if bt == 15 and _item_of(body) in victim_ids and not _is_deleted(body):
            new = _tombstone(body)
            if new is None:
                raise RuntimeError("a picture item laid out in a way this cannot tombstone")
        elif bt == 14:
            ents = _asset_entries(body)
            if ents is not None and any(h in drop_h for h, *_r in ents):
                keep = [e for e in ents if e[0] not in drop_h]
                gone.update(e[2] for e in ents if e[0] in drop_h and e[2])
                kept_names.update(e[2] for e in keep if e[2])
                tail = body[5 + struct.unpack_from("<I", body, 1)[0]:]
                new = (_sub(1, _varuint(len(keep)) + b"".join(body[s:e] for _h, _a, _n, s, e in keep)) + tail
                       if keep else None)
            elif ents:
                kept_names.update(e[2] for e in ents if e[2])
        if new is not None:
            out += struct.pack("<I", len(new)) + head + new
        i += 8 + ln
    new = bytes(out)
    # prove it back: every victim reads as deleted, every other picture is still live, and every live
    # picture still has its asset
    after = parse(new)
    alive = set(im["item"] for im in after if not im["deleted"])
    if alive & victim_ids or any(im["item"] not in alive for im in live if im not in victims):
        raise RuntimeError("the removal did not read back as meant")
    if any(not im["name"] for im in after if not im["deleted"] and im["hash"] and bytes.fromhex(im["hash"]) in keep_h):
        raise RuntimeError("a picture that stays lost its asset")
    paths.write_atomic(path, new)
    for nm in gone - kept_names:
        try:
            os.remove(os.path.join(RM, d, pid, nm))
        except OSError:
            pass
    return len(victims)


def digest(data):
    """Bytes that change when an image is added, moved or removed -- for a content fingerprint."""
    return b"".join(body for bt, body in blocks(data) if bt in (14, 15))


def _read_varuint(b, i):
    n = shift = 0
    while True:
        c = b[i]
        i += 1
        n |= (c & 0x7F) << shift
        if not c & 0x80:
            return n, i
        shift += 7


def _parent_of(body):
    """The parent group of a block-15 scene item: the body's first tag (id 1). None if absent."""
    try:
        if not body or body[0] != 0x1F:
            return None
        p1, i = _read_varuint(body, 1)
        p2, _ = _read_varuint(body, i)
        return (p1, p2)
    except IndexError:
        return None


def _item_of(body):
    """The item's own CrdtId: the tag after the parent (id 2). None if absent."""
    try:
        if not body or body[0] != 0x1F:
            return None
        _p1, i = _read_varuint(body, 1)
        _p2, i = _read_varuint(body, i)
        if body[i] != 0x2F:
            return None
        a, i = _read_varuint(body, i + 1)
        b, _ = _read_varuint(body, i)
        return (a, b)
    except IndexError:
        return None


def _deleted_of(body):
    """A block-15 item's deleted_length: tag id 5 (0x54, a 4-byte value) read IN ORDER after its four
    ids (parent, item, left, right) -> the length, or None when the body is not laid out that way.
    It used to be found by searching for the byte 0x54, which is also the id 84: the 24th picture on a
    page (item (1, 84)) read as deleted and its insert refused itself."""
    try:
        i = 0
        for tag in (0x1F, 0x2F, 0x3F, 0x4F):
            if body[i] != tag:
                return None
            _a, i = _read_varuint(body, i + 1)
            _b, i = _read_varuint(body, i)
        if body[i] != 0x54:
            return None
        return struct.unpack_from("<I", body, i + 1)[0]
    except (IndexError, struct.error):
        return None


def _is_deleted(body):
    """Whether a block-15 item is a tombstone: _deleted_of, and the old byte search only for a body
    laid out some other way."""
    dl = _deleted_of(body)
    if dl is None:
        k = body.find(b"\x54")
        dl = struct.unpack_from("<I", body, k + 1)[0] if 0 <= k and k + 5 <= len(body) else 0
    return dl > 0


def _tombstone(body):
    """A block-15 item deleted the way the tablet deletes one: its four ids (parent, item, left,
    right) byte for byte, deleted_length 1, no value. None when the body is not laid out that way."""
    try:
        i = 0
        for tag in (0x1F, 0x2F, 0x3F, 0x4F):
            if body[i] != tag:
                return None
            _a, i = _read_varuint(body, i + 1)
            _b, i = _read_varuint(body, i)
        return bytes(body[:i]) + b"\x54" + struct.pack("<I", 1)
    except IndexError:
        return None


def _asset_entries(body):
    """The assets a block 14 declares: [(hash16, asset_id, name, start, end)], each with its span in
    `body`; None when the body is not laid out as a list.

    BLOCK 14 IS A LIST: sub1[ count | count x sub0[ hash16 | sub1[ id(asset) | sub2[ name ] ]
    | sub2[ ... ] ] ]. The host writes one asset per block; the tablet, when it saves the page,
    merges them all into ONE block -- a page of game pieces after its first drag: 34 assets in
    one. Read as one asset per block, 33 of those pictures had no file, and removing the old speech
    strip dropped the whole block and took every picture on the page with it."""
    try:
        if body[0] != 0x1C:
            return None
        count, i = _read_varuint(body, 5)
        out = []
        for _ in range(count):
            if body[i] != 0x0C:
                return None
            n, = struct.unpack_from("<I", body, i + 1)
            start, end = i, i + 5 + n
            e = body[start + 5:end]
            aid = None
            if len(e) > 23 and e[16] == 0x1C and e[21] == 0x1F:
                a, j = _read_varuint(e, 22)
                b, _ = _read_varuint(e, j)
                aid = (a, b)
            m = _NAME.search(e)
            out.append((bytes(e[:16]), aid, m.group(0).decode() if m else None, start, end))
            i = end
        return out
    except (IndexError, struct.error):
        return None


def parse(data):
    """[{hash, name, quad, box, parent, deleted}] from a page's bytes. `box` and `quad` are RAW:
    in the parent group's frame, which is the page frame only on Layer 1 (see items())."""
    assets = {}                                         # hash -> file name
    for bt, body in blocks(data):
        if bt != 14:
            continue
        ents = _asset_entries(body)
        if ents is not None:
            assets.update((h, nm) for h, _aid, nm, _s, _e in ents if nm)
            continue
        m = _NAME.search(body)
        if not m:
            continue
        # the 16-byte hash sits right before the sub-block that carries the name
        pos = body.rfind(b"\x1c", 0, m.start())
        assets[body[max(0, pos - 16):pos] if pos >= 16 else b""] = m.group(0).decode()
    out = []
    for bt, body in blocks(data):
        if bt != 15:
            continue
        deleted = _is_deleted(body)
        hm = _HASH16.search(body)
        h = body[hm.end():hm.end() + 16] if hm else b""
        q = _QUAD.search(body)
        if not q or q.end() + 64 > len(body):
            continue
        vals = struct.unpack_from("<16f", body, q.end())
        quad = [(vals[4 * j], vals[4 * j + 1]) for j in range(4)]
        xs, ys = [p[0] for p in quad], [p[1] for p in quad]
        out.append({"hash": h.hex(), "name": assets.get(h) or (next(iter(assets.values())) if len(assets) == 1 else None),
                    "quad": quad, "box": (min(xs), min(ys), max(xs), max(ys)),
                    "parent": _parent_of(body), "item": _item_of(body), "deleted": deleted})
    return out


# ----------------------------------------------------------------- where a picture REALLY is
# THE DEVICE RE-FILES PICTURES INTO TEXT-ANCHORED GROUPS. Measured: the host
# placed a week calendar on Layer 1 at (-690, 200)-(720, 864); the user typed on the page; the tablet
# deleted that item and re-created it inside a new group anchored to a text character, with
# anchor_origin_x -572 and the quad rewritten RELATIVE to the anchor: (-118, -237)-(1292, 427).
# Nothing moved on the tablet. Everything here read the raw quad, so the host believed the calendar
# sat off the top-right of the page, measured the page as free where it was, and wrote a list over
# it. x is exact: page_x = anchor_origin_x + raw_x (anchored coordinates). y follows the
# anchor character's line, which only the app lays out exactly -- so for a picture THIS SYSTEM
# placed, the placement is recorded (record_placement) and is the answer while the x still agrees
# (the picture was re-filed, not moved); otherwise y is estimated from the paragraph model and the
# item says so (approx_y).
def _placements_path(doc, page_no):
    from paperdaemon.pipeline import page as _P
    return os.path.join(_P.HISTORY, "%s-p%02d" % (doc, page_no), "pictures.json")


def placements(doc, page_no):
    """{asset name: {box, type, spec, title, at}} for pictures this system placed on the page."""
    import json
    try:
        return json.load(open(_placements_path(doc, page_no), encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def record_placement(doc, page_no, name, box, hash=None, **meta):
    """Remember where (and what) a placed picture is -- the page box, and e.g. the chart spec. Keyed
    by the asset's file name, and carrying the item's HASH, which is what survives the device
    re-filing the item into an anchored group (it keeps the hash, not the item id)."""
    import json
    import time as _t
    rec = placements(doc, page_no)
    if hash is None:
        hash = _hash_of_name(doc, page_no, name)
    rec[name] = dict(meta, box=[round(float(v), 1) for v in box], at=int(_t.time()), hash=hash)
    p = _placements_path(doc, page_no)
    os.makedirs(os.path.dirname(p), exist_ok=True)
    paths.write_json_atomic(p, rec, indent=1, default=str)


def _hash_of_name(doc, page_no, name):
    """The hash the page's asset block `name` carries (hex), or None."""
    try:
        from paperdaemon.pipeline.page import render as R
        d = R.find_doc(doc) if "-" not in doc else doc
        pid = R.live_pages(d)[page_no - 1]["id"]
        data = open(os.path.join(RM, d, pid + ".rm"), "rb").read()
        for bt, body in blocks(data):
            if bt != 14:
                continue
            for h, _aid, nm, _s, _e in _asset_entries(body) or []:
                if nm == name:
                    return h.hex()
    except Exception:
        return None
    return None


def record_for(im, recs, taken=()):
    """The placement record that describes picture `im`: by hash (unique per asset), and for
    older pictures that share a hash, the one whose x agrees and whose box no other (Layer-1)
    picture already sits at exactly. None when the picture is not one this system placed."""
    cands = [r for r in recs.values() if r.get("hash") and r["hash"] == im.get("hash")]
    if len(cands) == 1:
        return cands[0]
    if not cands:
        r = recs.get(im.get("name") or "")
        return r if r and not r.get("hash") else None
    free = [r for r in cands if not any(all(abs(a - b) < 1.5 for a, b in zip(r["box"], t))
                                        for t in taken)]
    return (free or cands)[0]


def _anchor_groups(path):
    """{(part1, part2): (anchor_origin_x, anchor_id)} for every anchored group on the page."""
    from paperdaemon.pipeline.page import render as R
    from rmscene import scene_stream as ss
    out = {}
    for b in R.blocks_of(path):
        if isinstance(b, ss.TreeNodeBlock):
            g = b.group
            ox = getattr(getattr(g, "anchor_origin_x", None), "value", None)
            if ox is not None:
                aid = getattr(getattr(g, "anchor_id", None), "value", None)
                out[(g.node_id.part1, g.node_id.part2)] = (float(ox), aid)
    return out


def _anchor_y(doc, page_no, aid):
    """The y of the typed line an anchor character leads into, from the paragraph model: the
    paragraph after the anchor if the anchor is a newline, else the paragraph that holds it (a
    deleted anchor sits where it was). None when it cannot be found."""
    try:
        from paperdaemon.pipeline.page import typed as TY
        tb, ps = TY.paragraphs(doc, page_no)
        if tb is None or aid is None:
            return None
        k = 0
        for it in tb.items._items.values():
            iid = it.item_id
            n = len(it.value) if isinstance(it.value, str) and it.value else (it.deleted_length or 0)
            live = isinstance(it.value, str) and it.value and not it.deleted_length
            if iid.part1 == aid.part1 and iid.part2 <= aid.part2 < iid.part2 + max(1, n):
                if live:
                    off = aid.part2 - iid.part2
                    k += it.value[:off + 1].count("\n")
                return ps[min(k, len(ps) - 1)]["y"] if ps else None
            if live:
                k += it.value.count("\n")
    except Exception:
        return None
    return None


def _to_page(ims, path, doc, page_no):
    """Rewrite each item's box/quad into PAGE coordinates (see the note above)."""
    groups = _anchor_groups(path) if any(im.get("parent") for im in ims) else {}
    placed = None
    # boxes of the pictures that are NOT anchored: their raw box is their page box, so a record at
    # exactly that box is theirs and not a candidate for an anchored twin
    taken = [tuple(im["box"]) for im in ims if not groups.get(tuple(im.get("parent") or ()))]
    # SEVERAL ANCHORED PICTURES SHARING ONE HASH (placed before hashes were unique) are paired with
    # their records by vertical order -- the lowest raw quad with the lowest placement. Pictures
    # placed since hashes became unique have a hash of their own and never come through here.
    pairs = {}
    anchored = [im for im in ims if im.get("parent") and groups.get(tuple(im["parent"]))]
    by_hash = {}
    for im in anchored:
        by_hash.setdefault(im.get("hash"), []).append(im)
    for h, group in by_hash.items():
        if h and len(group) > 1:
            if placed is None:
                placed = placements(doc, page_no)
            recs_h = sorted([r for r in placed.values() if r.get("hash") == h and not any(
                all(abs(a - b) < 1.5 for a, b in zip(r["box"], t)) for t in taken)],
                key=lambda r: r["box"][1])
            if len(recs_h) >= len(group):
                for im, r in zip(sorted(group, key=lambda i: i["box"][1]), recs_h):
                    pairs[id(im)] = r
    for im in ims:
        g = groups.get(tuple(im["parent"])) if im.get("parent") else None
        if g is None:
            continue                                   # Layer 1: raw IS page
        ox, aid = g
        rx0, ry0, rx1, ry1 = im["box"]
        if placed is None:
            placed = placements(doc, page_no)
        rec = pairs.get(id(im)) or record_for(im, placed, taken)
        if rec and abs((rx0 + ox) - rec["box"][0]) < 2.0:
            dx, dy = ox, rec["box"][1] - ry0
            im["approx_y"] = False
        else:
            ay = _anchor_y(doc, page_no, aid)
            dx, dy = ox, (ay if ay is not None else 0.0)
            im["approx_y"] = True
        im["raw_box"] = im["box"]
        im["box"] = (rx0 + dx, ry0 + dy, rx1 + dx, ry1 + dy)
        im["quad"] = [(x + dx, y + dy) for x, y in im["quad"]]
        im["anchored"] = True
    return ims


_ITEMS = {}


def items(doc, page_no, page_id=None):
    """The live images of a page with their files resolved. [] when there are none."""
    try:
        from paperdaemon.pipeline.page import render as R
        d = R.find_doc(doc) if hasattr(R, "find_doc") else doc
        pid = page_id or R.live_pages(d)[page_no - 1]["id"]
    except Exception:
        d, pid = doc, page_id
    if not pid:
        return []
    path = os.path.join(RM, d, pid + ".rm")
    if not os.path.exists(path):
        return []
    # the parse is cached by the file's (mtime, size) -- see rm_render.blocks_of for why
    st = os.stat(path)
    key = (path, st.st_mtime_ns, st.st_size)
    parsed = _ITEMS.get(key)
    if parsed is None:
        parsed = parse(open(path, "rb").read())
        if len(_ITEMS) >= 12:
            _ITEMS.clear()
        _ITEMS[key] = parsed
    out = []
    live = _to_page([dict(i) for i in parsed if not i["deleted"]], path, d, page_no)
    for im in live:
        if im["deleted"]:
            continue
        f = None
        if im["name"]:
            cand = os.path.join(RM, d, pid, im["name"])
            f = cand if os.path.exists(cand) else None
        if f is None:                                   # the asset by any name in the page's folder
            found = glob.glob(os.path.join(RM, d, pid, "*.png")) + glob.glob(os.path.join(RM, d, pid, "*.jp*g"))
            f = found[0] if len(found) == 1 else None
        im["path"] = f
        out.append(im)
    return out


# ----------------------------------------------------------------- writing one
# The app's own bytes, read off a capture and reproduced field for field:
#
#   block 14 (versions 3,3) = sub1[ 01 | sub0[ hash16 | sub1[ id(asset) | sub2[ string name ] ]
#                                             | sub2[ id(0,0) | sub2[ 11 00 ] ] ] ]
#   block 15 (versions 2,2) = id1 parent(layer) | id2 item | id3 left(0,0) | id4 right(0,0)
#                             | u4_5 deleted 0 | sub6[ 07 | sub1[ id(item) | sub2[ hash16 ] ]
#                                                       | id2 asset | sub3[ 0x10 + 16 f32 ]
#                                                       | sub4[ 0x06 + 6 u32 ] ]
#
# The 16 floats are four corners as (x, y, u, v); the six indices are two triangles 0,1,2 2,3,0.
# The hash is any 16 bytes unique to the asset (the app's did not match md5/sha of the file); the
# file name is what the device loads.
import hashlib
import shutil
import uuid as _uuid


def _varuint(n):
    out = bytearray()
    while True:
        b = n & 0x7F
        n >>= 7
        if n:
            out.append(b | 0x80)
        else:
            out.append(b)
            return bytes(out)


def _id(tag_id, part1, part2):
    return bytes([(tag_id << 4) | 0xF]) + _varuint(part1) + _varuint(part2)


def _sub(tag_id, body):
    return bytes([(tag_id << 4) | 0xC]) + struct.pack("<I", len(body)) + body


def _u4(tag_id, v):
    return bytes([(tag_id << 4) | 0x4]) + struct.pack("<I", v)


def _string(s):
    b = s.encode("utf-8")
    return _varuint(len(b)) + b"\x01" + b


def _block(btype, body, min_version, cur_version):
    return struct.pack("<I", len(body)) + bytes([0, min_version, cur_version, btype]) + body


def asset_block(hash16, name, asset_id):
    inner = (hash16
             + _sub(1, _id(1, *asset_id) + _sub(2, _string(name)))
             + _sub(2, _id(1, 0, 0) + _sub(2, b"\x11\x00")))
    return _block(14, _sub(1, b"\x01" + _sub(0, inner)), 3, 3)


def item_block(layer_id, item_id, asset_id, hash16, box):
    x0, y0, x1, y1 = (float(v) for v in box)
    corners = [(x0, y0, 0.0, 0.0), (x1, y0, 1.0, 0.0), (x1, y1, 1.0, 1.0), (x0, y1, 0.0, 1.0)]
    verts = b"\x10" + b"".join(struct.pack("<4f", *c) for c in corners)
    tris = b"\x06" + struct.pack("<6I", 0, 1, 2, 2, 3, 0)
    value = (b"\x07"
             + _sub(1, _id(1, *item_id) + _sub(2, hash16))
             + _id(2, *asset_id)
             + _sub(3, verts)
             + _sub(4, tris))
    body = (_id(1, *layer_id) + _id(2, *item_id) + _id(3, 0, 0) + _id(4, 0, 0)
            + _u4(5, 0) + _sub(6, value))
    return _block(15, body, 2, 2)


def insert(doc, page_no, png_path, box, page_id=None):
    """Place a picture on a notebook page the way the app does. Returns what was written.

    `box` = (x0, y0, x1, y1) in page coordinates (x centered at 0, y from the top). The picture is
    fitted to that rectangle exactly as given -- keep the aspect yourself. The file is copied to
    `<doc>/<page>/<uuid>.png` beside the page and the page gets an asset block and an item block
    appended, on Layer 1, with fresh CrdtIds after every id already used. Push the document
    afterwards (rm_cloud.push_doc gathers the asset with the page).
    """
    import io
    from paperdaemon.pipeline import draw as A
    from rmscene import read_blocks
    from rmscene import scene_stream as ss
    try:
        from paperdaemon.pipeline.page import render as R
        d = R.find_doc(doc) if hasattr(R, "find_doc") else doc
        pid = page_id or R.live_pages(d)[page_no - 1]["id"]
    except Exception:
        d, pid = doc, page_id
    path = os.path.join(RM, d, pid + ".rm")
    data = open(path, "rb").read()
    blocks_ = list(read_blocks(io.BytesIO(data)))
    layer = None
    for b in blocks_:
        if isinstance(b, ss.TreeNodeBlock) and getattr(b.group.label, "value", None) == "Layer 1":
            layer = b.group.node_id
    if layer is None:
        raise RuntimeError("no Layer 1 on that page")
    n = A.next_free_id(blocks_)
    # rmscene does not see image items, so their ids are not in next_free_id's view: step past
    # every (1, k) a picture on this page already took, item or asset, read as the varuints they are
    # (a single byte stopped being enough at id 128)
    for bt, body in blocks(data):
        if bt == 15:
            it = _item_of(body)
            if it and it[0] == 1:
                n = max(n, it[1] + 1)
        elif bt == 14:
            for _h, aid, _nm, _s, _e in _asset_entries(body) or []:
                if aid and aid[0] == 1:
                    n = max(n, aid[1] + 1)
    asset_id, item_id = (1, n), (1, n + 1)
    raw = open(png_path, "rb").read()
    name = str(_uuid.uuid4()) + os.path.splitext(png_path)[1].lower().replace(".jpeg", ".jpg")
    # UNIQUE PER ASSET, not per image content. It was md5(file): two renders of the same week are
    # byte-identical, so a second calendar got the first one's hash, and the page could no longer say
    # which picture was which. The device only needs the hash to link item and
    # asset; the app's own were not a digest of the file either.
    hash16 = hashlib.md5(raw + name.encode("ascii")).digest()
    folder = os.path.join(RM, d, pid)
    os.makedirs(folder, exist_ok=True)
    shutil.copyfile(png_path, os.path.join(folder, name))
    new = data + asset_block(hash16, name, asset_id) + item_block((layer.part1, layer.part2), item_id, asset_id, hash16, box)
    # prove it back before it touches the page: rmscene still reads the rest, and our own reader
    # finds exactly one more picture, at the box we meant
    list(read_blocks(io.BytesIO(new)))
    got = [im for im in parse(new) if not im["deleted"]]
    before = [im for im in parse(data) if not im["deleted"]]
    if len(got) != len(before) + 1 or got[-1]["name"] != name:
        raise RuntimeError("the written picture does not read back")
    bx = got[-1]["box"]
    if any(abs(a - float(b)) > 0.01 for a, b in zip(bx, box)):
        raise RuntimeError("the written box reads back as %r" % (bx,))
    paths.write_atomic(path, new)
    return {"doc": d, "page_id": pid, "asset": "%s/%s/%s" % (d, pid, name), "box": tuple(float(v) for v in box),
            "asset_id": asset_id, "item_id": item_id, "bytes": len(new) - len(data),
            "hash": hash16.hex(), "name": name}


# ----------------------------------------------------------------- to the top
# THE TABLET STACKS PICTURES BY ID: every item the host writes links (0,0)/(0,0), so the sequence
# orders them by id -- a later picture lies on top. The tablet itself, moving a picture, tombstones
# its item and adds a new one after the last (a dragged chess piece: the old square's item dead, a new
# one for the target square). to_front does the same, so a picture put on the page since (a board redrawn each turn)
# ends up under these again.
def to_front(doc, page_no, keys, page_id=None):
    """Bring pictures to the top of the page: each is tombstoned and added again as a new item after
    every other, with its own asset, hash and box. keys = hashes (hex). -> how many."""
    import io
    from paperdaemon.pipeline import draw as A
    from rmscene import read_blocks
    try:
        from paperdaemon.pipeline.page import render as R
        d = R.find_doc(doc) if hasattr(R, "find_doc") else doc
        pid = page_id or R.live_pages(d)[page_no - 1]["id"]
    except Exception:
        d, pid = doc, page_id
    path = os.path.join(RM, d, pid + ".rm")
    data = open(path, "rb").read()
    want = [bytes.fromhex(k) for k in keys]
    aid = {h: a for bt, b in blocks(data) if bt == 14 for h, a, _n, _s, _e in _asset_entries(b) or []}
    n = A.next_free_id(list(read_blocks(io.BytesIO(data))))
    for bt, body in blocks(data):
        if bt == 15:
            it = _item_of(body)
            if it and it[0] == 1:
                n = max(n, it[1] + 1)
        elif bt == 14:
            n = max([n] + [a[1] + 1 for _h, a, _nm, _s, _e in _asset_entries(body) or [] if a and a[0] == 1])
    out, again = bytearray(data[:43]), []
    i = 43
    while i + 8 <= len(data):
        ln, = struct.unpack_from("<I", data, i)
        bt, head, body = data[i + 7], data[i + 4:i + 8], data[i + 8:i + 8 + ln]
        hm = _HASH16.search(body) if bt == 15 else None
        h = body[hm.end():hm.end() + 16] if hm else b""
        if bt == 15 and h in want and not _is_deleted(body) and h in aid:
            q = _QUAD.search(body)
            vals = struct.unpack_from("<16f", body, q.end())
            xs, ys = [vals[4 * j] for j in range(4)], [vals[4 * j + 1] for j in range(4)]
            again.append((_parent_of(body), h, (min(xs), min(ys), max(xs), max(ys))))
            body = _tombstone(body)
        out += struct.pack("<I", len(body)) + head + body
        i += 8 + ln
    for parent, h, box in sorted(again, key=lambda g: want.index(g[1])):
        out += item_block(parent, (1, n), aid[h], h, box)
        n += 1
    new = bytes(out)
    list(read_blocks(io.BytesIO(new)))
    live = [im for im in parse(new) if not im["deleted"]]
    top = [im["hash"] for im in live[-len(again):]] if again else []
    if top != [g[1].hex() for g in sorted(again, key=lambda g: want.index(g[1]))]:
        raise RuntimeError("the pictures did not come to the front")
    paths.write_atomic(path, new)
    return len(again)


# ----------------------------------------------------------------- moving one
# A picture MOVES by its quad: the item keeps its id, its asset and its place in the file (so what was
# above stays above), and only the corners' x and y change -- u and v, the texture's corners, stay.
# Written for game pieces (rm_chess): the host snaps a piece to its square after every turn.
def move(doc, page_no, moves, page_id=None):
    """Move pictures already on the page. `moves` = [(key, box)], key = the picture's hash (hex) or
    its asset's file name, box = (x0, y0, x1, y1) in PAGE coordinates. -> [{key, item, from, to}]
    Raises when a key names no live picture or more than one, and writes nothing then."""
    import io
    from rmscene import read_blocks
    try:
        from paperdaemon.pipeline.page import render as R
        d = R.find_doc(doc) if hasattr(R, "find_doc") else doc
        pid = page_id or R.live_pages(d)[page_no - 1]["id"]
    except Exception:
        d, pid = doc, page_id
    path = os.path.join(RM, d, pid + ".rm")
    data = bytearray(open(path, "rb").read())
    by_name = {}
    for bt, body in blocks(bytes(data)):
        if bt == 14:
            by_name.update((nm, h.hex()) for h, _aid, nm, _s, _e in _asset_entries(body) or [] if nm)
    # where each live item's 16 floats sit in the file, by hash
    spots = {}
    i = 43
    while i + 8 <= len(data):
        ln, = struct.unpack_from("<I", data, i)
        bt, start = data[i + 7], i + 8
        body = bytes(data[start:start + ln])
        if bt == 15:
            hm, q = _HASH16.search(body), _QUAD.search(body)
            if not _is_deleted(body) and hm and q and q.end() + 64 <= len(body):
                spots.setdefault(body[hm.end():hm.end() + 16].hex(), []).append(start + q.end())
        i += 8 + ln
    # the page frame against the raw one, per item (an anchored picture's raw quad is offset)
    live = _to_page([dict(im) for im in parse(bytes(data)) if not im["deleted"]], path, d, page_no)
    page_box = {im["hash"]: (im["box"], im.get("raw_box", im["box"])) for im in live}
    done, want = [], {}
    for key, box in moves:
        h = key if re.fullmatch(r"[0-9a-f]{32}", str(key)) else by_name.get(str(key))
        if not h or len(spots.get(h, [])) != 1 or h not in page_box:
            raise RuntimeError("no single live picture for %r" % (key,))
        (px0, py0, _px1, _py1), (rx0, ry0, _rx1, _ry1) = page_box[h]
        dx, dy = px0 - rx0, py0 - ry0
        nx0, ny0, nx1, ny1 = (float(v) for v in box)
        rnx0, rny0, rnx1, rny1 = nx0 - dx, ny0 - dy, nx1 - dx, ny1 - dy
        off = spots[h][0]
        vals = list(struct.unpack_from("<16f", data, off))
        xs, ys = [vals[4 * j] for j in range(4)], [vals[4 * j + 1] for j in range(4)]
        ox0, ox1, oy0, oy1 = min(xs), max(xs), min(ys), max(ys)
        for j in range(4):
            vals[4 * j] = rnx0 if abs(xs[j] - ox0) <= abs(xs[j] - ox1) else rnx1
            vals[4 * j + 1] = rny0 if abs(ys[j] - oy0) <= abs(ys[j] - oy1) else rny1
        struct.pack_into("<16f", data, off, *vals)
        want[h] = (rnx0, rny0, rnx1, rny1)
        done.append({"key": key, "hash": h, "from": page_box[h][0], "to": (nx0, ny0, nx1, ny1)})
    new = bytes(data)
    # prove it back: rmscene still reads the page, every moved item reads at its new raw box, and
    # nothing else changed size or order
    list(read_blocks(io.BytesIO(new)))
    after = {im["hash"]: im for im in parse(new) if not im["deleted"]}
    for h, bx in want.items():
        if any(abs(a - b) > 0.01 for a, b in zip(after[h]["box"], bx)):
            raise RuntimeError("the moved picture reads back at %r" % (after[h]["box"],))
    paths.write_atomic(path, new)
    return done
