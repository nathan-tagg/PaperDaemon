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


def read_blocks(data):
    """rmscene.read_blocks over a page's bytes, its stroke blocks read here (points as arrays)."""
    stream = Reader(io.BytesIO(data))
    stream.read_header()
    while True:
        with stream.read_block() as info:
            if info is None:
                return
            block = None
            if info.block_type == LINE.BLOCK_TYPE:
                try:
                    block = _line_block(stream)
                except Exception:
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
        block.extra_data = info.extra_data
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


def write_lines(buf, blocks):
    """Stroke blocks (LINE, their values si.Line with POINT arrays) appended to `buf`, after a page already written by
    rmscene.write_blocks: each framed and tagged as rmscene's own writer does (line version 2), its points in one step."""
    w = Writer(buf)
    for b in blocks:
        with w.write_block(LINE.BLOCK_TYPE, 2, 2):
            w.write_id(1, b.parent_id)
            w.write_id(2, b.item.item_id)
            w.write_id(3, b.item.left_id)
            w.write_id(4, b.item.right_id)
            w.write_int(5, b.item.deleted_length)
            line = b.item.value
            if line is not None:
                with w.write_subblock(6):
                    w.data.write_uint8(LINE.ITEM_TYPE)
                    w.write_int(1, line.tool)
                    w.write_int(2, line.color)
                    w.write_double(3, line.thickness_scale)
                    w.write_float(4, line.starting_length)
                    with w.write_subblock(5):
                        w.data.write_bytes(points_of(line.points).tobytes())
                    w.write_id(6, CrdtId(0, 1))
                    if line.move_id is not None:
                        w.write_id(7, line.move_id)
                    if line.color_rgba is not None:
                        w.write_color(8, line.color_rgba)
            w.data.write_bytes(b.extra_data or b"")


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
