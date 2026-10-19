"""The false mirror's own edits: what the user makes and changes in it from the window -- notebooks, folders and pages,
imports and exports, moves and deletes, tags, and a page's contents from the page editor.

ONLY IN THE FALSE MIRROR'S ENGINE (paths.local_only()): every function here refuses anywhere else, so nothing of the
tablet's library is ever written by them. What they write is what the tablet writes -- the same .metadata, .content,
.pagedata and .rm files -- so a page made here is a page the tablet could open, and the daemon reads it unchanged.

A PAGE, FOR THE EDITOR (scene_of / write_scene): its frame, its layers bottom to top with their strokes as the file
stores them, its typed text as paragraphs of runs, and whether the text and the template are shown. Writing builds
the page anew in the tablet's own structure (the root node, each layer's node and its place under the root, the
strokes under their layer, the root text block), keeping the page's header blocks."""
import io
import json
import os
import time
import uuid

from rmscene import read_blocks, write_blocks
from rmscene import scene_items as si
from rmscene import scene_stream as ss
from rmscene.crdt_sequence import CrdtSequence, CrdtSequenceItem
from rmscene.tagged_block_common import CrdtId, LwwValue

from .. import paths
from . import library as F

M = F.M

# paragraph style codes as the file stores them, and the editor's names for them (D6 of add-page-editor: Title is
# HEADING, Section BOLD, Body PLAIN; Header is written as BASIC until a page from the tablet says otherwise)
STYLE_OF = {2: ("title", None), 0: ("header", None), 3: ("section", None), 1: ("body", None), 4: ("body", "bullet"),
            5: ("body", "bullet2"), 6: ("body", "check"), 7: ("body", "checked"), 10: ("body", "number")}
CODE_OF = {("title", None): 2, ("header", None): 0, ("section", None): 3, ("body", None): 1, ("body", "bullet"): 4,
           ("body", "bullet2"): 5, ("body", "check"): 6, ("body", "checked"): 7, ("body", "number"): 10}


class NotHere(PermissionError):
    """An edit asked of the tablet's mirror: these are the false mirror's alone."""


def _guard():
    if not paths.local_only():
        raise NotHere("this is done only in the False Mirror")


def _now():
    return int(time.time() * 1000)


def _pipeline():
    from paperdaemon.pipeline import TEMPLATES
    return os.path.dirname(TEMPLATES)


def _read(path):
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def _content(doc):
    return _read(os.path.join(M, doc + ".content"))


def _save_content(doc, c):
    paths.write_json_atomic(os.path.join(M, doc + ".content"), c)


def _touch(u):
    """The item's modified time is now (its cover and the library's order follow)."""
    p = os.path.join(M, u + ".metadata")
    m = _read(p)
    m["lastModified"] = str(_now())
    paths.write_json_atomic(p, m)


def _live(c):
    return sorted((p for p in (c.get("cPages") or {}).get("pages") or [] if "deleted" not in p),
                  key=lambda p: p["idx"]["value"])


def page_id(doc, page_no):
    live = _live(_content(doc))
    if not 1 <= page_no <= len(live):
        raise ValueError("there is no page %d" % page_no)
    return live[page_no - 1]["id"]


# ---------------------------------------------------------------- notebooks, folders, pages

def new_notebook(name, parent=""):
    """A notebook with one blank page, in the Paper Pro's frame. -> its id."""
    _guard()
    from paperdaemon import studio
    doc = str(uuid.uuid4())
    studio._new_notebook(M, _pipeline(), doc, (name or "Notebook").strip() or "Notebook", parent, _now())
    blank = studio._blank_page_bytes(_pipeline())          # the bundled Paper Pro page: no user library to copy
    pid = str(uuid.uuid4())
    paths.write_atomic(os.path.join(M, doc, pid + ".rm"), blank)
    c = _content(doc)
    c["cPages"]["pages"] = [{"id": pid, "idx": {"timestamp": "1:2", "value": "ba"}, "modifed": str(_now()),
                             "template": {"timestamp": "1:1", "value": "Blank"}}]
    c["cPages"]["lastOpened"] = {"timestamp": "1:1", "value": pid}
    c.update(pageCount=1, sizeInBytes=str(len(blank)))
    _save_content(doc, c)
    paths.write_atomic(os.path.join(M, doc + ".pagedata"), "Blank\n")
    return doc


def new_folder(name, parent=""):
    _guard()
    u = str(uuid.uuid4())
    now = str(_now())
    paths.write_json_atomic(os.path.join(M, u + ".metadata"), {
        "createdTime": now, "lastModified": now, "new": False, "parent": parent, "pinned": False, "source": "",
        "type": "CollectionType", "visibleName": (name or "Folder").strip() or "Folder"})
    paths.write_json_atomic(os.path.join(M, u + ".content"), {"tags": []})
    return u


def new_page(doc, after=None):
    """A blank page after page `after` (1-based; the last page when None), in the notebook's own frame. -> its
    1-based number."""
    _guard()
    live = _live(_content(doc))
    if not live:
        raise ValueError("the notebook has no page to follow")
    at = len(live) if after is None else max(1, min(len(live), int(after)))
    F.insert_pages(doc, live[at - 1]["id"], 1)
    _touch(doc)
    return at + 1


def import_pdf(name, data, parent=""):
    """A PDF, as the tablet files one, in folder `parent`. -> its id."""
    _guard()
    if not data.startswith(b"%PDF"):
        raise ValueError("that is not a PDF")
    import tempfile
    from paperdaemon.pipeline.page import pdf as PDF
    fd, tmp = tempfile.mkstemp(suffix=".pdf")
    try:
        with os.fdopen(fd, "wb") as f:
            f.write(data)
        doc, _pages = PDF.stage((name or "Document").strip() or "Document", tmp)
    finally:
        try:
            os.remove(tmp)
        except OSError:
            pass
    if parent:
        F.move(doc, parent)
    return doc


def export_pdf(doc):
    """The document as a PDF, every page drawn by PaperDaemon's renderer, in order. -> bytes."""
    _guard()
    from PIL import Image
    from paperdaemon import thumbs
    pics = []
    for n in range(1, len(_live(_content(doc))) + 1):
        im = Image.open(thumbs.draw(doc, n, 2160))
        pics.append(im.convert("RGB"))
    if not pics:
        raise ValueError("the document has no pages")
    buf = io.BytesIO()
    pics[0].save(buf, format="PDF", save_all=True, append_images=pics[1:], resolution=229.0)
    return buf.getvalue()


def move(u, parent):
    _guard()
    if parent and (parent == u or parent not in F.items()):
        raise ValueError("that folder is not in the False Mirror")
    return F.move(u, parent)


def delete(u):
    """Into the trash, as the tablet deletes: out of every list, its files kept."""
    _guard()
    return F.move(u, "trash")


def set_tags(u, tags):
    """A folder's or a document's tags, as the tablet stores them."""
    _guard()
    p = os.path.join(M, u + ".content")
    c = _read(p) if os.path.exists(p) else {}
    was = {str(t.get("name") if isinstance(t, dict) else t): t for t in c.get("tags") or []}
    now = _now()
    c["tags"] = [was.get(t) if isinstance(was.get(t), dict) else {"name": t, "timestamp": now} for t in _clean(tags)]
    paths.write_json_atomic(p, c)
    _touch(u)


def set_page_tags(doc, page_no, tags):
    _guard()
    pid = page_id(doc, page_no)
    c = _content(doc)
    keep = [t for t in c.get("pageTags") or [] if t.get("pageId") != pid]
    was = {t.get("name"): t for t in c.get("pageTags") or [] if t.get("pageId") == pid}
    now = _now()
    c["pageTags"] = keep + [was.get(t) or {"name": t, "pageId": pid, "timestamp": now} for t in _clean(tags)]
    _save_content(doc, c)
    _touch(doc)


def _clean(tags):
    out = []
    for t in tags or []:
        t = str(t).strip()
        if t and t.lower() not in [x.lower() for x in out]:
            out.append(t[:64])
    return out


# ---------------------------------------------------------------- a page, for the editor

def _rm(doc, page_no):
    return os.path.join(M, doc, page_id(doc, page_no) + ".rm")


def scene_of(doc, page_no):
    """The page as the editor holds it (see the module's note)."""
    from rmscene import read_tree
    from paperdaemon.pipeline.page import typed as TY
    path = _rm(doc, page_no)
    data = open(path, "rb").read()
    blocks = list(read_blocks(io.BytesIO(data)))
    info = next((b for b in blocks if isinstance(b, ss.SceneInfo)), None)
    tree = read_tree(io.BytesIO(data))

    def lines_in(group, out):
        for item in group.children.values():
            if isinstance(item, si.Line):
                out.append({"pen": item.tool.name if hasattr(item.tool, "name") else str(item.tool),
                            "penCode": int(item.tool), "color": int(item.color),
                            "colorRgba": list(item.color_rgba) if getattr(item, "color_rgba", None) else None,
                            "thicknessScale": float(item.thickness_scale),
                            "points": [[p.x, p.y, p.speed, p.direction, p.width, p.pressure] for p in item.points]})
            elif isinstance(item, si.Group):
                lines_in(item, out)
        return out

    layers = []
    for g in tree.root.children.values():
        if isinstance(g, si.Group):
            layers.append({"label": g.label.value or "Layer %d" % (len(layers) + 1), "visible": bool(g.visible.value),
                           "lines": lines_in(g, [])})
    if not layers:
        layers = [{"label": "Layer 1", "visible": True, "lines": []}]
    text = None
    try:
        rec = TY.from_blocks(TY.read_preserved(data), data)
        if rec.get("column"):
            paras = []
            for p in rec["paragraphs"]:
                style, lst = STYLE_OF.get(p.get("style_code"), ("body", None))
                paras.append({"style": style, "list": lst, "runs": [{"text": r["text"], "bold": bool(r["format"].get("bold")),
                                                                      "italic": bool(r["format"].get("italic"))}
                                                                     for r in p.get("runs") or []]})
            col = rec["column"]
            text = {"x": col["x"], "y": col["y"], "width": col["width"], "paras": paras}
    except Exception:
        text = None
    size = list(info.paper_size) if info is not None and info.paper_size else [1620, 2160]
    lww = lambda v, d: (v.value if isinstance(v, LwwValue) else v) if v is not None else d
    return {"paperSize": size, "layers": layers, "text": text,
            "textVisible": bool(lww(getattr(info, "root_document_visible", None), True)),
            "templateVisible": bool(lww(getattr(info, "background_visible", None), True)),
            "template": "Blank"}


def _enum(kind, v):
    try:
        return kind(int(v))
    except ValueError:
        return int(v)


def write_scene(doc, page_no, scene):
    """The page made anew from the editor's scene, its header blocks kept. -> the number of strokes written."""
    _guard()
    path = _rm(doc, page_no)
    old = list(read_blocks(io.BytesIO(open(path, "rb").read())))
    head = [b for b in old if isinstance(b, (ss.AuthorIdsBlock, ss.MigrationInfoBlock))]
    info = next((b for b in old if isinstance(b, ss.SceneInfo)), None)
    if not any(isinstance(b, ss.AuthorIdsBlock) for b in head):
        head.insert(0, ss.AuthorIdsBlock(author_uuids={1: uuid.uuid4()}))
    seq = [16]

    def nid(n=1):
        k = seq[0]
        seq[0] += n
        return CrdtId(1, k)

    layers = scene.get("layers") or [{"label": "Layer 1", "visible": True, "lines": []}]
    nodes = [CrdtId(0, 11)] + [nid() for _ in layers[1:]]
    tree = [ss.SceneTreeBlock(tree_id=n, node_id=CrdtId(0, 0), is_update=True, parent_id=CrdtId(0, 1)) for n in nodes]
    groups = [ss.TreeNodeBlock(group=si.Group(node_id=CrdtId(0, 1)))]
    for L, n in zip(layers, nodes):
        g = si.Group(node_id=n)
        g.label = LwwValue(timestamp=nid(), value=str(L.get("label") or "Layer"))
        g.visible = LwwValue(timestamp=nid(), value=bool(L.get("visible", True)))
        groups.append(ss.TreeNodeBlock(group=g))
    placed, prev = [], CrdtId(0, 0)
    for n in nodes:
        gid = nid()
        placed.append(ss.SceneGroupItemBlock(parent_id=CrdtId(0, 1), item=CrdtSequenceItem(
            item_id=gid, left_id=prev, right_id=CrdtId(0, 0), deleted_length=0, value=n)))
        prev = gid
    strokes, count = [], 0
    for L, n in zip(layers, nodes):
        prev = CrdtId(0, 0)
        for ln in L.get("lines") or []:
            pts = [si.Point(x=float(p[0]), y=float(p[1]), speed=int(p[2]), direction=int(p[3]), width=int(p[4]),
                            pressure=int(p[5])) for p in ln.get("points") or []]
            if not pts:
                continue
            rgba = ln.get("colorRgba")
            line = si.Line(color=_enum(si.PenColor, ln.get("color", 0)), tool=_enum(si.Pen, ln.get("penCode", 17)),
                           points=pts, thickness_scale=float(ln.get("thicknessScale") or 1.0), starting_length=0.0,
                           move_id=None, color_rgba=tuple(int(v) for v in rgba) if rgba else None)
            iid = nid()
            strokes.append(ss.SceneLineItemBlock(parent_id=n, item=CrdtSequenceItem(
                item_id=iid, left_id=prev, right_id=CrdtId(0, 0), deleted_length=0, value=line)))
            prev = iid
            count += 1
    text = _text_block(scene.get("text"), nid)
    if info is not None:
        info.root_document_visible = LwwValue(timestamp=CrdtId(1, 1), value=bool(scene.get("textVisible", True)))
        info.background_visible = LwwValue(timestamp=CrdtId(1, 1), value=bool(scene.get("templateVisible", True)))
    chars = sum(len(r.get("text") or "") for p in ((scene.get("text") or {}).get("paras") or []) for r in p.get("runs") or [])
    blocks = head + [ss.PageInfoBlock(loads_count=1, merges_count=0, text_chars_count=chars,
                                      text_lines_count=len(((scene.get("text") or {}).get("paras")) or []))]
    blocks += ([info] if info is not None else []) + tree + groups + placed + ([text] if text else []) + strokes
    buf = io.BytesIO()
    write_blocks(buf, blocks)
    data = buf.getvalue()
    back = [b for b in read_blocks(io.BytesIO(data)) if isinstance(b, ss.SceneLineItemBlock)]
    if len(back) != count:
        raise RuntimeError("the page did not read back: %d strokes written, %d read" % (count, len(back)))
    paths.write_atomic(path, data)
    _touch(doc)
    return count


def _text_block(text, nid):
    """The root text block: the paragraphs as text items (bold and italic as the format items 1-4 between runs), each
    paragraph's style keyed by the newline before it (the first by 0:0)."""
    paras = (text or {}).get("paras") or []
    if not paras:
        return None
    items, styles, prev = [], {}, CrdtId(0, 0)
    state = {"bold": False, "italic": False}

    def add(value, n):
        nonlocal prev
        iid = nid(n)
        items.append(CrdtSequenceItem(item_id=iid, left_id=prev, right_id=CrdtId(0, 0), deleted_length=0, value=value))
        prev = CrdtId(iid.part1, iid.part2 + n - 1)
        return iid

    for i, p in enumerate(paras):
        code = CODE_OF.get((p.get("style") or "body", p.get("list") or None), 1)
        if i:
            key = add("\n", 1)
            styles[key] = LwwValue(timestamp=nid(), value=code)
        else:
            styles[CrdtId(0, 0)] = LwwValue(timestamp=nid(), value=code)
        for r in p.get("runs") or []:
            for k, on, off in (("bold", 1, 2), ("italic", 3, 4)):
                if bool(r.get(k)) != state[k]:
                    state[k] = bool(r.get(k))
                    add(on if state[k] else off, 1)
            t = r.get("text") or ""
            if t:
                add(t, len(t))
    return ss.RootTextBlock(block_id=CrdtId(0, 0), value=si.Text(
        items=CrdtSequence(items), styles=styles, pos_x=float(text.get("x", -576)), pos_y=float(text.get("y", 234)),
        width=float(text.get("width", 1152))))
