"""A page's strokes read and written in bulk.

rmscene (the reader PaperDaemon uses for .rm files) reads a stroke's points one at a time, as Python objects: a page
with a decomp on it (tens of thousands of strokes, over a million points) takes seconds each way. Here the stroke
blocks are read and written with rmscene's own block framing and tagged fields, exactly as it does, but each stroke's
points -- in the file a packed run of 14-byte records (x, y float32; speed, width uint16; direction, pressure uint8) --
go to and from a numpy array in one step. Every other block is rmscene's own, read and written by rmscene.

A stroke read here is an si.Line whose `points` is that array (POINT, a structured dtype), not a list of si.Point.
"""
import io

import numpy as np
from rmscene import scene_items as si
from rmscene import scene_stream as ss
from rmscene import tagged_block_reader as _rd, tagged_block_writer as _wr
from rmscene.tagged_block_common import CrdtId
from rmscene.crdt_sequence import CrdtSequenceItem

# rmscene's block reader and writer: the one class of each module whose name ends so
Reader = next(v for k, v in vars(_rd).items() if k.endswith("BlockReader") and isinstance(v, type))
Writer = next(v for k, v in vars(_wr).items() if k.endswith("BlockWriter") and isinstance(v, type))
POINT = np.dtype([("x", "<f4"), ("y", "<f4"), ("speed", "<u2"), ("width", "<u2"), ("direction", "u1"), ("pressure", "u1")])
_POINT_V1 = np.dtype([("x", "<f4"), ("y", "<f4"), ("speed", "<f4"), ("direction", "<f4"), ("width", "<f4"), ("pressure", "<f4")])
LINE = ss.SceneLineItemBlock


def _line_value(stream, version):
    """rmscene's line_from_stream, its points read in one step."""
    tool = si.Pen(stream.read_int(1))
    color = si.PenColor(stream.read_int(2))
    thickness_scale = stream.read_double(3)
    starting_length = stream.read_float(4)
    with stream.read_subblock(5) as info:
        raw = stream.data.read_bytes(info.size)
    if version == 1:                                   # rmscene's own conversion of the old layout
        a = np.frombuffer(raw, dtype=_POINT_V1)
        pts = np.empty(len(a), POINT)
        pts["x"], pts["y"] = a["x"], a["y"]
        pts["speed"] = np.clip(a["speed"] * 4, 0, 65535)
        pts["direction"] = np.clip(255 * a["direction"] / (np.pi * 2), 0, 255)
        pts["width"] = np.clip(np.round(a["width"] * 4), 0, 65535)
        pts["pressure"] = np.clip(a["pressure"] * 255, 0, 255)
    else:
        if len(raw) % POINT.itemsize:
            raise ValueError("point data size %d is not a multiple of %d" % (len(raw), POINT.itemsize))
        pts = np.frombuffer(raw, dtype=POINT)
    stream.read_id(6)                                  # the timestamp rmscene reads and drops
    move_id = None
    if stream.bytes_remaining_in_block() >= 3:
        try:
            move_id = stream.read_id(7)
        except Exception:
            move_id = None
    color_rgba = stream.read_color_optional(8)
    return si.Line(color, tool, pts, thickness_scale, starting_length, move_id, color_rgba)


def _line_block(stream):
    """rmscene's SceneItemBlock.from_stream for a stroke block, its value read by _line_value."""
    parent_id = stream.read_id(1)
    item_id = stream.read_id(2)
    left_id = stream.read_id(3)
    right_id = stream.read_id(4)
    deleted_length = stream.read_int(5)
    value, extra = None, b""
    if stream.has_subblock(6):
        with stream.read_subblock(6) as info:
            if stream.data.read_uint8() != LINE.ITEM_TYPE:
                raise ValueError("not a line item")
            value = _line_value(stream, stream.current_block.current_version)
        extra = info.extra_data
    return LINE(parent_id, CrdtSequenceItem(item_id, left_id, right_id, deleted_length, value), extra_value_data=extra)


class _Miss(Exception):
    """A stroke block not laid out as _raw_line_block reads it: rmscene reads that one."""


def _points(raw, version):
    if version == 1:                                   # rmscene's own conversion of the old layout
        a = np.frombuffer(raw, dtype=_POINT_V1)
        pts = np.empty(len(a), POINT)
        pts["x"], pts["y"] = a["x"], a["y"]
        pts["speed"] = np.clip(a["speed"] * 4, 0, 65535)
        pts["direction"] = np.clip(255 * a["direction"] / (np.pi * 2), 0, 255)
        pts["width"] = np.clip(np.round(a["width"] * 4), 0, 65535)
        pts["pressure"] = np.clip(a["pressure"] * 255, 0, 255)
        return pts
    if len(raw) % POINT.itemsize:
        raise ValueError("point data size %d is not a multiple of %d" % (len(raw), POINT.itemsize))
    return np.frombuffer(raw, dtype=POINT)


def _raw_line_block(data, p, end, version):
    """A stroke block's tagged fields read straight from its bytes data[p:end], in the order and with the tags rmscene
    reads them (SceneItemBlock.from_stream, line_from_stream) -> (LINE, its trailing bytes). Anything else -> _Miss."""
    import struct

    def vu(p):
        r = sh = 0
        while True:
            if p >= end:
                raise _Miss()
            b = data[p]
            p += 1
            r |= (b & 0x7F) << sh
            sh += 7
            if not b & 0x80:
                return r, p

    def tag(p, idx, typ):
        x, q = vu(p)
        if x != (idx << 4 | typ):
            raise _Miss()
        return q

    def cid(p, idx):
        p = tag(p, idx, 0xF)
        a = data[p]
        b, p = vu(p + 1)
        return CrdtId(a, b), p

    def u32(p):
        if p + 4 > end:
            raise _Miss()
        return int.from_bytes(data[p:p + 4], "little"), p + 4

    def peek(p, idx, typ):
        try:
            return p < end and vu(p)[0] == (idx << 4 | typ)
        except _Miss:
            return False

    parent, p = cid(p, 1)
    item, p = cid(p, 2)
    left, p = cid(p, 3)
    right, p = cid(p, 4)
    deleted, p = u32(tag(p, 5, 0x4))
    value, sub_extra = None, b""
    if peek(p, 6, 0xC):
        n, p = u32(tag(p, 6, 0xC))
        sub_end = p + n
        if sub_end > end or data[p] != LINE.ITEM_TYPE:
            raise _Miss()
        p += 1
        tool, p = u32(tag(p, 1, 0x4))
        color, p = u32(tag(p, 2, 0x4))
        p = tag(p, 3, 0x8)
        thickness = struct.unpack_from("<d", data, p)[0]
        p = tag(p + 8, 4, 0x4)
        starting = struct.unpack_from("<f", data, p)[0]
        k, p = u32(tag(p + 4, 5, 0xC))
        if p + k > sub_end:
            raise _Miss()
        pts = _points(bytes(data[p:p + k]), version)
        _ts, p = cid(p + k, 6)
        move_id = None
        if end - p >= 3 and peek(p, 7, 0xF):           # rmscene: tried when 3 bytes or more are left in the block
            move_id, p = cid(p, 7)
        rgba = None
        if p < sub_end and peek(p, 8, 0x4):
            packed, p = u32(tag(p, 8, 0x4))
            rgba = ((packed >> 16) & 0xFF, (packed >> 8) & 0xFF, packed & 0xFF, (packed >> 24) & 0xFF)
        if p > sub_end:
            raise _Miss()
        sub_extra = bytes(data[p:sub_end])
        p = sub_end
        value = si.Line(si.PenColor(color), si.Pen(tool), pts, thickness, starting, move_id, rgba)
    return LINE(parent, CrdtSequenceItem(item, left, right, deleted, value), extra_value_data=sub_extra), bytes(data[p:end])


def read_blocks(data):
    """rmscene.read_blocks over a page's bytes, its stroke blocks read here (points as arrays)."""
    stream = Reader(io.BytesIO(data))
    stream.read_header()
    while True:
        with stream.read_block() as info:
            if info is None:
                return
            block, extra = None, None
            if info.block_type == LINE.BLOCK_TYPE:
                try:                                    # its fields straight from the bytes, then past the block
                    block, extra = _raw_line_block(data, info.offset, info.offset + info.size, info.current_version)
                    stream.data.data.seek(info.offset + info.size)
                except (_Miss, ValueError, IndexError):
                    stream.data.data.seek(info.offset)   # anything unexpected: rmscene reads this one as it would
                    block = None
            if block is None:
                kind = ss.Block.lookup(info.block_type)
                if kind:
                    try:
                        block = kind.from_stream(stream)
                    except Exception as e:
                        stream.data.data.seek(info.offset)
                        block = ss.UnreadableBlock(str(e), stream.data.read_bytes(info.size), info)
                else:
                    block = ss.UnreadableBlock("unknown block type %d" % info.block_type, stream.data.read_bytes(info.size), info)
        block.extra_data = info.extra_data if extra is None else extra
        yield block


def points_of(rows):
    """A stroke's points as POINT: from an array already, or from rows [x, y, speed, direction, width, pressure]."""
    if isinstance(rows, np.ndarray) and rows.dtype == POINT:
        return rows
    a = np.asarray(rows, dtype=np.float64).reshape(-1, 6)
    out = np.empty(len(a), POINT)
    out["x"], out["y"] = a[:, 0], a[:, 1]
    out["speed"] = np.clip(np.round(a[:, 2]), 0, 65535)
    out["direction"] = np.clip(np.round(a[:, 3]), 0, 255) % 256
    out["width"] = np.clip(np.round(a[:, 4]), 0, 65535)
    out["pressure"] = np.clip(np.round(a[:, 5]), 0, 255)
    return out


def _vu(n):
    out = bytearray()
    while True:
        b = n & 0x7F
        n >>= 7
        if n:
            out.append(b | 0x80)
        else:
            out.append(b)
            return bytes(out)


def _tag(idx, typ):
    return _vu(idx << 4 | typ)


def _cid(idx, c):
    return _tag(idx, 0xF) + bytes([c.part1]) + _vu(c.part2)


def write_lines(buf, blocks):
    """Stroke blocks (LINE, their values si.Line with POINT arrays or rows) appended to `buf`, after a page already
    written by rmscene.write_blocks: framed and tagged byte for byte as rmscene's own writer does (line version 2:
    SceneItemBlock.to_stream, line_to_stream), each block put together in one piece."""
    import struct
    out = []
    for b in blocks:
        body = (_cid(1, b.parent_id) + _cid(2, b.item.item_id) + _cid(3, b.item.left_id) + _cid(4, b.item.right_id) +
                _tag(5, 0x4) + struct.pack("<I", b.item.deleted_length))
        line = b.item.value
        if line is not None:
            pts = points_of(line.points).tobytes()
            v = (bytes([LINE.ITEM_TYPE]) + _tag(1, 0x4) + struct.pack("<I", int(line.tool)) + _tag(2, 0x4) + struct.pack("<I", int(line.color)) +
                 _tag(3, 0x8) + struct.pack("<d", line.thickness_scale) + _tag(4, 0x4) + struct.pack("<f", line.starting_length) +
                 _tag(5, 0xC) + struct.pack("<I", len(pts)) + pts + _cid(6, CrdtId(0, 1)))
            if line.move_id is not None:
                v += _cid(7, line.move_id)
            if line.color_rgba is not None:
                r, g, bl, al = line.color_rgba
                v += _tag(8, 0x4) + struct.pack("<I", bl | (g << 8) | (r << 16) | (al << 24))
            body += _tag(6, 0xC) + struct.pack("<I", len(v)) + v
        body += b.extra_data or b""
        out.append(struct.pack("<IBBBB", len(body), 0, 2, 2, LINE.BLOCK_TYPE) + body)
    buf.write(b"".join(out))


# ---------------------------------------------------------------- the page editor's binary form of a scene
# "PDS1", the length of what follows as JSON (uint32, little-endian), that JSON -- the scene as scene_of gives it, each
# stroke's points replaced by their count, "n" -- then every stroke's points, in the scene's order, as POINT records
# (14 bytes each, the .rm file's own layout). A page with a decomp on it is a quarter of its size as JSON, and is
# neither turned into text nor read back from it.
MAGIC = b"PDS1"


def scene_bytes(scene):
    """A scene whose strokes' points are POINT arrays (scene_of(..., arrays=True)) -> its binary form."""
    import json
    meta, parts = dict(scene), []
    meta["layers"] = []
    for L in scene.get("layers") or []:
        lines = []
        for ln in L.get("lines") or []:
            pts = points_of(ln.get("points") if ln.get("points") is not None else [])
            parts.append(pts.tobytes())
            lines.append({k: v for k, v in ln.items() if k != "points"} | {"n": len(pts)})
        meta["layers"].append({k: v for k, v in L.items() if k != "lines"} | {"lines": lines})
    head = json.dumps(meta, separators=(",", ":")).encode("utf-8")
    return MAGIC + len(head).to_bytes(4, "little") + head + b"".join(parts)


def scene_from_bytes(data):
    """The binary form -> the scene, each stroke's points a POINT array."""
    import json
    if data[:4] != MAGIC:
        raise ValueError("not a PaperDaemon page")
    n = int.from_bytes(data[4:8], "little")
    scene = json.loads(data[8:8 + n].decode("utf-8"))
    at = 8 + n
    for L in scene.get("layers") or []:
        for ln in L.get("lines") or []:
            k = int(ln.pop("n", 0)) * POINT.itemsize
            if at + k > len(data):
                raise ValueError("the page's points end early")
            ln["points"] = np.frombuffer(data, dtype=POINT, count=k // POINT.itemsize, offset=at)
            at += k
    if at != len(data):
        raise ValueError("the page has %d bytes past its points" % (len(data) - at))
    return scene


# ---------------------------------------------------------------- the whole page in one pass, for the editor
# The C library (fastdecomp rmlines.c) walks the page's blocks and reads every stroke's fields; the strokes are laid
# out from its rows and their points taken from the page's bytes where they are. The few other blocks (the layers, the
# text, the page's settings) are rmscene's, read from those blocks alone. A page this does not cover as it is -- a stroke
# block laid out otherwise, the old point layout, strokes not stored in their order, a layer holding groups -- gives
# None, and the caller reads it as before.
_COLS = None


def _lib():
    global _COLS
    import os
    import sys
    here = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "pipeline", "decompose", "fastdecomp")
    if here not in sys.path:
        sys.path.insert(0, here)
    import rmfast
    L = rmfast.lib()
    if _COLS is None:
        _COLS = int(L.rf_rm_cols())
    return L


def scene_parts(data):
    """A page's bytes -> (its blocks other than strokes, {layer node id: [stroke, in order]}), each stroke a dict as the
    editor takes it, its points a POINT array over the page's bytes; or None (see above)."""
    import ctypes
    from rmscene.tagged_block_common import HEADER_V6
    try:
        L = _lib()
    except OSError:
        return None
    if not data.startswith(HEADER_V6):
        return None
    cap = len(data) // 8 + 16
    rows = np.empty((cap, _COLS), np.int64)
    n = L.rf_rm_blocks(data, len(data), len(HEADER_V6), rows.ctypes.data_as(ctypes.POINTER(ctypes.c_int64)), cap)
    if n < 0:
        return None
    rows = rows[:n]
    T, START, END, VERSION, ODD = 0, 1, 2, 3, 4
    lines = rows[rows[:, T] == LINE.BLOCK_TYPE]
    if (lines[:, ODD] != 0).any() or (lines[:, VERSION] != 2).any():
        return None
    # the other blocks, read by rmscene from their own frames
    others = rows[rows[:, T] != LINE.BLOCK_TYPE]
    frames = b"".join(data[s - 8:e] for s, e in others[:, [START, END]].tolist())
    blocks = list(ss.read_blocks(io.BytesIO(HEADER_V6 + frames)))
    # each layer's strokes, which must be stored in their order: the first after nothing, each after the one before
    by_parent = {}
    for r in lines.tolist():
        by_parent.setdefault((r[5], r[6]), []).append(r)
    out = {}
    for parent, rs in by_parent.items():
        prev = (0, 0)
        for r in rs:
            if (r[9], r[10]) != prev:
                return None
            prev = (r[7], r[8])
        lst = []
        for r in rs:
            if not r[14]:                                   # a tombstone: kept in the file, not on the page
                continue
            import struct
            tool, color = si.Pen(r[15]), si.PenColor(r[16])
            rgba = None
            if r[24]:
                p = r[25] & 0xFFFFFFFF
                rgba = [(p >> 16) & 0xFF, (p >> 8) & 0xFF, p & 0xFF, (p >> 24) & 0xFF]
            lst.append({"pen": tool.name, "penCode": int(tool), "color": int(color), "colorRgba": rgba,
                        "thicknessScale": struct.unpack("<d", struct.pack("<q", r[17]))[0],
                        "points": np.frombuffer(data, dtype=POINT, count=r[20] // POINT.itemsize, offset=r[19])})
        out[CrdtId(*parent)] = lst
    return blocks, out
