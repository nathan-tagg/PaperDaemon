"""Decompose and send: a picture from the desktop becomes pen strokes, and a page with those strokes is
appended to the inbox notebook on the tablet.

The decomposer is the pipeline's (rm_model.decompose_into, region budget 10,000 strokes). The picture is
fitted into a square box at the top of a page, centered; the preview is the strokes rendered at the tablet's
own scale and cropped to the ink, exactly what the tablet will show. The picture the user drops in is not
kept (it lives in a temporary file deleted at once).

THE DECOMPS ARE KEPT ON DISK, not in memory: each one the Decompose screen makes is a folder of its own under
<data>/decomps/<id> -- its strokes (strokes.npz: the points, widths, pens and colors as arrays), its preview
(preview.png, at the tablet's own scale) and what it is (meta.json) -- and Send, Save and the screen's list read
them from there. They stay until deleted. Both engines (the Mirror's and the false mirror's) share the folder.

THE INBOX IS A TAG (Settings: tags.inbox, "inbox" unless renamed): a send adds its page to EVERY notebook carrying it,
in this engine's mirror (the Mirror's engine and the false mirror's each send to their own). A mirror with no notebook
tagged takes it at the end of its Quick sheets -- one per mirror, the document of that name at the root of the
library, as the tablet keeps it. A notebook with the inbox tag is never worked on (ledger.is_inbox).
"""
import base64
import urllib.request
import io
import json
import os
import tempfile
import threading
import time
import uuid

from . import paths
from . import settings as S
from paperdaemon import net as _net

PAGE_W, PAGE_H = 1620, 2160
SAFE_X0, SAFE_X1 = -800.0, 800.0
TOP = 176.0                      # the top of the picture's box, below the tablet's toolbar area
BOTTOM = 2130.0
BUDGET = 10000                   # the decomposer's region budget, in strokes
PREVIEW_SCALE = 1.0                # one preview pixel per tablet pixel: at half scale a 1,200-wide drawing showed as a 600-wide picture, enlarged

_lock = threading.Lock()         # one decompose or send at a time
FETCH_MAX = 40 * 1024 * 1024             # the largest picture fetched from a link
# the decompose running now, for the screen's progress ring: its job id (the screen's own), and the stage it is in
_now = {"job": None, "stage": "", "share": 0.0}
DECOMPOSE_SHARE = 0.6                    # the decompose's part of the whole; drawing the preview is the rest


def progress(job):
    """How far the screen's job `job` has come -> {state: waiting | running | unknown, done: 0..1}. The decompose
    reports from inside the C at its stage boundaries, the preview as its strokes are drawn."""
    if not job or _now["job"] != job:
        return {"state": "waiting", "done": 0.0}
    if _now["stage"] == "decompose":
        from paperdaemon.pipeline import decompose as M
        F = M.fast()
        f = F.progress() if F else 0.0               # without the C library there is nothing to report until done
        return {"state": "running", "done": round(DECOMPOSE_SHARE * f, 3)}
    if _now["stage"] == "preview":
        return {"state": "running", "done": round(DECOMPOSE_SHARE + (1 - DECOMPOSE_SHARE) * _now["share"], 3)}
    return {"state": "running", "done": 0.0}


def _bytes(image):
    """A data URL, bare base64, or a web link to a picture (an image dragged from a browser) -> bytes."""
    v = str(image or "")
    if v.startswith(("http://", "https://")):
        req = urllib.request.Request(v, headers={"User-Agent": "PaperDaemon", "Accept": "image/*"})
        with _net.urlopen(req, timeout=60) as r:
            data = r.read(FETCH_MAX + 1)
        if len(data) > FETCH_MAX:
            raise ValueError("the picture at that link is larger than 40 MB")
        return data
    if v.startswith("data:"):
        v = v.split(",", 1)[1]
    if not v:
        raise ValueError("no picture")
    return base64.b64decode(v)


def box_for(width):
    return int(max(200, min(int(width or SAFE_X1 - SAFE_X0), int(SAFE_X1 - SAFE_X0), int(BOTTOM - TOP - 20))))


def _preview(strokes, progress=None):
    """The strokes as a PNG data URL at the tablet's own scale, cropped to the ink."""
    return "data:image/png;base64," + base64.b64encode(_preview_png(strokes, progress)).decode("ascii")


def _preview_png(strokes, progress=None):
    """The strokes as PNG bytes at the tablet's own scale, cropped to the ink."""
    from paperdaemon.pipeline.draw import preview
    from PIL import Image, ImageOps
    k = PREVIEW_SCALE
    fd, png = tempfile.mkstemp(suffix=".png", dir=paths.sub("tmp"))
    os.close(fd)
    try:
        preview([([((x + PAGE_W / 2.0) * k, y * k) for x, y in st[0]], [w * k for w in st[1]],
                   st[2], st[3], st[4]) for st in strokes], int(PAGE_W * k), int(PAGE_H * k), png, pad=0, progress=progress)
        with Image.open(png) as im:
            im = im.convert("RGB")
        ink = ImageOps.invert(im.convert("L")).getbbox()
        if ink:
            im = im.crop(ink)
        buf = io.BytesIO()
        im.save(buf, "PNG")
        return buf.getvalue()
    finally:
        for p in (png, png + ".ss.png"):
            try:
                os.remove(p)
            except OSError:
                pass


def decompose(image, width=None, preview=True, job=None, keep=None, height=None):
    """A picture (data URL or base64) -> ({preview, strokes, points, seconds, box, box_h, width, height}, the strokes).
    With `keep` (the picture's name), the decomp is kept on disk (see the module's note) and the answer carries its id,
    and its preview is the kept file's, not a data URL. `height`: the box as tall as that (up to the page below the
    toolbar), so a picture taller than wide still comes out `width` wide (the page editor's paste); else a square."""
    raw = _bytes(image)
    box = box_for(width)
    box_h = int(max(200, min(int(height), int(BOTTOM - TOP - 20)))) if height else box
    with _lock:
        _now.update(job=job, stage="decompose", share=0.0)
        try:
            out, strokes = _decompose_locked(raw, box, preview and keep is None, box_h)
            if keep is not None:
                _now["stage"] = "preview"
                png = _preview_png(strokes, lambda f: _now.update(share=f))
                out.update(_keep(strokes, png, dict(out, name=str(keep or "Picture")[:200], requested=int(width or box))))
            return out, strokes
        finally:
            _now.update(job=None, stage="", share=0.0)
            try:                                          # its preview drawn: the graphics card's helper let go
                from paperdaemon.pipeline.page import gpu
                gpu.release()
            except Exception:
                pass


def _decompose_locked(raw, box, preview, box_h=None):
    box_h = box_h or box
    _decomposer_cache()
    import paperdaemon.pipeline  # noqa: F401  (the decomposer's reference imports its neighbors by name)
    from paperdaemon.pipeline import decompose as M
    from PIL import Image
    F = M.fast()
    if F:
        F.lib().rf_progress_reset()              # the last picture's 100% is not this one's
    fd, src = tempfile.mkstemp(suffix=".png", dir=paths.sub("tmp"))
    os.close(fd)
    try:
        with Image.open(io.BytesIO(raw)) as im:
            im.convert("RGB").save(src)
        strokes, _params, secs = M.decompose_into(src, box, box_h, origin=(-box / 2.0, TOP), budget=BUDGET)
    finally:
        try:
            os.remove(src)
        except OSError:
            pass
    xs = [x for st in strokes for x, _y in st[0]]
    ys = [y for st in strokes for _x, y in st[0]]
    out = {"strokes": len(strokes), "points": len(xs), "seconds": secs, "box": box, "box_h": box_h,
           # the drawing's own size on the page, in tablet pixels
           "width": round(max(xs) - min(xs)) if xs else 0, "height": round(max(ys) - min(ys)) if ys else 0}
    if preview:
        _now["stage"] = "preview"
        out["preview"] = _preview(strokes, lambda f: _now.update(share=f))
    return out, strokes


# ---------------------------------------------------------------- the decomps, kept on disk

def _decomps():
    return paths.sub("decomps")


def _decomp_dir(did):
    if not (isinstance(did, str) and len(did) == 32 and all(c in "0123456789abcdef" for c in did)):
        raise ValueError("not a decomp id")
    p = os.path.join(_decomps(), did)
    if not os.path.isdir(p):
        raise FileNotFoundError("no such decomp")
    return p


def _keep(strokes, png, meta):
    """A decomp into its own folder -> {id}: the strokes as arrays (each stroke's points and widths run together, its
    point count, pen, color and RGBA beside them), the preview, and what it is."""
    import numpy as np
    did = uuid.uuid4().hex
    tmp = os.path.join(_decomps(), "." + did)
    os.makedirs(tmp)
    counts = np.array([len(st[0]) for st in strokes], np.int32)
    xy = np.array([p for st in strokes for p in st[0]], np.float32).reshape(-1, 2)
    w = np.array([v for st in strokes for v in (st[1] if len(st[1]) == len(st[0]) else [st[1][0]] * len(st[0]))], np.float32)
    pens = np.array([int(st[2]) for st in strokes], np.int16)
    colors = np.array([int(st[3]) for st in strokes], np.int16)
    rgba = np.array([(list(st[4]) + [255])[:4] if len(st) > 4 and st[4] else [-1, -1, -1, -1] for st in strokes], np.int16).reshape(-1, 4)
    np.savez(os.path.join(tmp, "strokes.npz"), counts=counts, xy=xy, w=w, pens=pens, colors=colors, rgba=rgba)
    with open(os.path.join(tmp, "preview.png"), "wb") as f:
        f.write(png)
    meta = {k: meta[k] for k in ("name", "strokes", "points", "seconds", "box", "width", "height", "requested") if k in meta}
    meta.update(id=did, created=int(time.time() * 1000))
    with open(os.path.join(tmp, "meta.json"), "w", encoding="utf-8") as f:
        json.dump(meta, f)
    os.replace(tmp, os.path.join(_decomps(), did))
    return {"id": did}


def decomp_strokes(did):
    """A kept decomp's strokes, as the decomposer made them: [(points, widths, pen, color, rgba or None)]."""
    import numpy as np
    from rmscene.scene_items import Pen, PenColor
    with np.load(os.path.join(_decomp_dir(did), "strokes.npz")) as z:
        counts, xy, w, pens, colors, rgba = z["counts"], z["xy"], z["w"], z["pens"], z["colors"], z["rgba"]
    out, at = [], 0
    for i, n in enumerate(counts.tolist()):
        pts = [(float(x), float(y)) for x, y in xy[at:at + n].tolist()]
        out.append((pts, w[at:at + n].tolist(), Pen(int(pens[i])), PenColor(int(colors[i])),
                    tuple(int(v) for v in rgba[i]) if rgba[i][0] >= 0 else None))
        at += n
    return out


def decomp_meta(did):
    with open(os.path.join(_decomp_dir(did), "meta.json"), encoding="utf-8") as f:
        return json.load(f)


def decomp_preview(did):
    return os.path.join(_decomp_dir(did), "preview.png")


def decomps_page(offset=0, limit=10):
    """The kept decomps, newest first -> {total, items: [meta]} from `offset`, `limit` of them."""
    metas = []
    for n in os.listdir(_decomps()):
        if n.startswith("."):
            continue
        try:
            with open(os.path.join(_decomps(), n, "meta.json"), encoding="utf-8") as f:
                metas.append(json.load(f))
        except (OSError, ValueError):
            continue
    metas.sort(key=lambda m: m.get("created") or 0, reverse=True)
    offset, limit = max(0, int(offset)), max(1, min(500, int(limit)))
    return {"total": len(metas), "items": metas[offset:offset + limit]}


def delete_decomp(did):
    import shutil
    shutil.rmtree(_decomp_dir(did))


# ---------------------------------------------------------------- the inbox

QUICK_SHEETS = "Quick sheets"        # the tablet's own, one per library, at its root


def _meta(mirror, doc):
    try:
        with open(os.path.join(mirror, doc + ".metadata"), encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        return {}


def _in_trash(mirror, m, depth=0):
    parent = m.get("parent") or ""
    if parent == "trash":
        return True
    if not parent or depth > 16:
        return False
    try:
        with open(os.path.join(mirror, parent + ".metadata"), encoding="utf-8") as f:
            pm = json.load(f)
    except (OSError, ValueError):
        return False
    return _in_trash(mirror, pm, depth + 1)


def inbox_docs(mirror, tag):
    """Where a send lands in this mirror -> ([doc id], how): every notebook carrying the inbox tag `tag` ("tag"),
    else the Quick sheets ("quick sheets": the newest at the root, should there be two), else ([], None)."""
    tag = str(tag or "").strip().lower()
    tagged, quick = [], []
    for f in os.listdir(mirror) if os.path.isdir(mirror) else []:
        if not f.endswith(".metadata"):
            continue
        doc = f[:-len(".metadata")]
        try:
            with open(os.path.join(mirror, f), encoding="utf-8") as fh:
                m = json.load(fh)
            with open(os.path.join(mirror, doc + ".content"), encoding="utf-8") as fh:
                c = json.load(fh)
        except (OSError, ValueError):
            continue
        if m.get("type") != "DocumentType" or m.get("deleted") or c.get("fileType") != "notebook" or _in_trash(mirror, m):
            continue
        if tag and any(str(t.get("name") if isinstance(t, dict) else t).strip().lower() == tag for t in (c.get("tags") or [])):
            tagged.append((str(m.get("visibleName") or ""), doc))
        elif m.get("visibleName") == QUICK_SHEETS and not (m.get("parent") or ""):
            quick.append((int(str(m.get("lastModified") or "0")) if str(m.get("lastModified") or "0").isdigit() else 0, doc))
    if tagged:
        return [d for _n, d in sorted(tagged)], "tag"
    if quick:
        return [max(quick)[1]], "quick sheets"
    return [], None


def _targets(s):
    """This engine's inbox notebooks -> [doc id]; a ValueError when the mirror has none."""
    from paperdaemon.pipeline.page import render as R
    tag = S.inbox_tag(s)
    docs, _how = inbox_docs(R.RM, tag)
    if not docs:
        raise ValueError("no notebook is tagged %s, and there is no Quick sheets" % tag)
    return docs


def _next_key(keys):
    """The idx keys the app sorts pages by: ba, bb, ... bz, ca, ..."""
    letters = "abcdefghijklmnopqrstuvwxyz"
    keys = [k for k in keys if isinstance(k, str) and len(k) == 2]
    if not keys:
        return "ba"
    last = max(keys)
    i = (ord(last[0]) - ord("b")) * 26 + letters.index(last[1]) + 1
    return chr(ord("b") + i // 26) + letters[i % 26]


def _blank_page_bytes(pipeline, mirror=None):
    """A new notebook's blank page: derived from a page of the user's own library in their tablet's frame
    (tablets.library_page), or the bundled Paper Pro page when the library has none."""
    from rmscene import read_blocks, write_blocks
    from rmscene import scene_stream as ss
    if mirror:
        from paperdaemon.pipeline.page import tablets as TB
        src = TB.library_page(mirror)
        if src:
            try:
                from paperdaemon.remarkable import library as F
                return F.blank_page_bytes(src)
            except Exception:
                pass
    with open(os.path.join(pipeline, "rm-templates", "blank-page.rm"), "rb") as f:
        data = f.read()
    blocks = [b for b in read_blocks(io.BytesIO(data))
              if not isinstance(b, (ss.SceneLineItemBlock, ss.RootTextBlock))]
    buf = io.BytesIO()
    write_blocks(buf, blocks)
    return buf.getvalue()


def _new_notebook(mirror, pipeline, doc, name, parent, now):
    os.makedirs(os.path.join(mirror, doc), exist_ok=True)
    with open(os.path.join(pipeline, "rm-templates", "notebook.content"), encoding="utf-8") as f:
        tpl = json.load(f)
    content = dict(tpl)
    content["cPages"] = {"lastOpened": {"timestamp": "1:1", "value": ""},
                         "original": {"timestamp": "0:0", "value": -1},
                         "pages": [], "uuids": tpl["cPages"]["uuids"]}
    # no tag: the daemon never takes the inbox's pages for requests, whatever it carries (ledger.is_inbox)
    content.update(pageCount=0, pageTags=[], coverPageNumber=-1, sizeInBytes="0", tags=[])
    with open(os.path.join(mirror, doc + ".content"), "w", encoding="utf-8") as f:
        json.dump(content, f, indent=4)
    with open(os.path.join(mirror, doc + ".metadata"), "w", encoding="utf-8") as f:
        json.dump({"createdTime": str(now), "lastModified": str(now), "lastOpened": "", "lastOpenedPage": 0,
                   "parent": parent, "pinned": False, "source": "", "type": "DocumentType", "visibleName": name},
                  f, indent=4)


def _decomposer_cache():
    """The decomposer's compiled code is cached in the data folder, not beside the app's files (which may
    be read-only in an installed app)."""
    os.environ.setdefault("NUMBA_CACHE_DIR", paths.sub("cache", "numba"))


def _inbox_pages(doc, count, now):
    """Append `count` blank pages to the inbox notebook `doc` -> [(page_no, page_id)]. The caller writes them and
    then calls _push_inbox."""
    from paperdaemon.pipeline import TEMPLATES
    from paperdaemon.pipeline.page import render as R
    pipeline = os.path.dirname(TEMPLATES)
    mirror = R.RM
    cpath = os.path.join(mirror, doc + ".content")
    with open(cpath, encoding="utf-8") as f:
        content = json.load(f)
    # an index entry whose page file never arrived would shift every page number after it
    content["cPages"]["pages"] = [q for q in content["cPages"]["pages"]
                                  if os.path.exists(os.path.join(mirror, doc, q["id"] + ".rm"))]
    pages = content["cPages"]["pages"]
    pids = []
    # A NEW PAGE IN ITS NOTEBOOK'S FRAME: copied from the inbox's own last page, the tablet it lives on; a new inbox's
    # from the user's library (_blank_page_bytes)
    blank = None
    live = [q for q in pages if not q.get("deleted")]
    if live:
        try:
            from paperdaemon.remarkable import library as F
            blank = F.blank_page_bytes(os.path.join(mirror, doc, live[-1]["id"] + ".rm"))
        except Exception:
            blank = None
    blank = blank or _blank_page_bytes(pipeline, mirror)
    for _ in range(count):
        pid = str(uuid.uuid4())
        key = _next_key([p["idx"]["value"] for p in pages if "idx" in p])
        with open(os.path.join(mirror, doc, pid + ".rm"), "wb") as f:
            f.write(blank)
        pages.append({"id": pid, "idx": {"timestamp": "1:2", "value": key}, "modifed": str(now),
                      "template": {"timestamp": "1:1", "value": "Blank"}})
        pids.append(pid)
    content["pageCount"] = len(pages)
    content["cPages"]["lastOpened"] = {"timestamp": "1:1", "value": pids[-1]}
    paths.write_atomic(cpath, json.dumps(content, indent=4))
    live = R.live_pages(doc)
    out = []
    for pid in pids:
        hit = [i for i, q in enumerate(live) if q["id"] == pid]
        if not hit:
            raise RuntimeError("the new page is not among the notebook's pages; the mirror may be out of step")
        out.append((hit[0] + 1, pid))
    return out


def _push_inbox(docs):
    """The inboxes' new pages, with each notebook's size brought up to date, pushed to the tablet."""
    from paperdaemon.pipeline.page import render as R
    from paperdaemon.remarkable import sync as C
    mirror = R.RM
    for doc in docs:
        cpath = os.path.join(mirror, doc + ".content")
        with open(cpath, encoding="utf-8") as f:
            content = json.load(f)
        content["sizeInBytes"] = str(sum(os.path.getsize(os.path.join(mirror, doc, p["id"] + ".rm"))
                                         for p in content["cPages"]["pages"]
                                         if os.path.exists(os.path.join(mirror, doc, p["id"] + ".rm"))))
        paths.write_atomic(cpath, json.dumps(content, indent=4))
    if paths.local_only():
        return                             # the false mirror's inboxes: written, and that is the whole of it
    # THE ONE WAY TO THE TABLET (sync.push_pending): the inboxes go up with everything else the mirror holds that the
    # cloud does not
    def missing():
        got = dict(C.push_pending()["pushed"])
        return [d for d in docs if (got.get(d) or {}).get("root_put") != 200 and d in got]
    left = missing()
    for _ in range(4):                     # the tablet syncing mid-push moves the generation
        if not left:
            break
        time.sleep(2)
        left = missing()
    if left:
        raise RuntimeError("the push did not go through for %d inbox(es)" % len(left))


def _settings():
    return S.load()


def send(image=None, width=None, s=None, decomp=None):
    """Append a page with the strokes of a kept decomp (`decomp`, its id) or of a picture decomposed now to every inbox
    notebook of this mirror (_targets) and push them. -> {sent, notebooks, strokes}."""
    s = s or _settings()
    _targets(s)                                   # somewhere to land, before a picture is decomposed for nothing
    strokes0 = decomp_strokes(decomp) if decomp else decompose(image, width, preview=False)[1]
    from paperdaemon.pipeline import draw as A
    from paperdaemon.remarkable import sync as C
    from paperdaemon.pipeline import page as PG
    from paperdaemon.pipeline.page import tablets as TB
    with _lock:
        if not paths.local_only():
            C.pull()
        docs = _targets(s)
        for doc in docs:
            [(page_no, pid)] = _inbox_pages(doc, 1, int(time.time() * 1000))
            # THE INBOX PAGE'S OWN TABLET: the strokes were laid out on a Paper Pro page; another tablet's page has
            # them scaled to its width (tablets.picture_page)
            frame = TB.frame_of(doc, page_no)
            k = TB.picture_page(frame)[1]
            strokes = strokes0 if abs(k - 1.0) <= 1e-6 else \
                [([(x * k, y * k) for x, y in st[0]], [w * k for w in st[1]]) + tuple(st[2:]) for st in strokes0]
            d = A.Drawing(*[int(round(v)) for v in frame])
            d.strokes = list(strokes)
            w = d.write_rm(doc, page_no)
            if not (w or {}).get("written"):
                raise RuntimeError("the page could not be written: %r" % (w,))
            PG.record_provenance(doc, page_no, strokes=d.strokes, what="decompose and send, %d strokes" % len(strokes),
                                 kind="drawing")
        _push_inbox(docs)
        return {"sent": True, "notebooks": len(docs), "strokes": len(strokes0)}


# ---------------------------------------------------------------- the logs, to the inbox

LOG_LINES = 300                          # the end of each log
LOG_PAGES = 30                           # at most this many pages in all


def _log_text():
    """The end of each of PaperDaemon's logs, under its own name."""
    files = []
    for folder in (paths.sub("logs"), paths.data_dir()):
        try:
            names = sorted(os.listdir(folder))
        except OSError:
            continue
        for n in names:
            if n.endswith((".out", ".err", ".log")) and os.path.isfile(os.path.join(folder, n)):
                files.append(os.path.join(folder, n))
    out = ["PaperDaemon logs, %s" % time.strftime("%Y-%m-%d %H:%M"), ""]
    for path in files:
        try:
            with open(path, encoding="utf-8", errors="replace") as f:
                lines = f.read().splitlines()[-LOG_LINES:]
        except OSError:
            continue
        out += ["==== %s (last %d lines)" % (os.path.basename(path), len(lines))] + lines + [""]
    return out


def _log_pages(lines, w=1404, h=1872):
    """The lines as page-sized pictures, in a monospace face -> [PIL image]."""
    import textwrap
    from PIL import Image, ImageDraw, ImageFont
    size, margin = 20, 60
    try:
        font = ImageFont.truetype(os.path.join(os.environ.get("WINDIR", "C:/Windows"), "Fonts", "consola.ttf"), size)
    except OSError:
        font = ImageFont.load_default(size=size)
    cols = int((w - 2 * margin) / (size * 0.55))
    rows = int((h - 2 * margin) / (size * 1.25))
    wrapped = []
    for ln in lines:
        wrapped += textwrap.wrap(ln.expandtabs(4), cols, drop_whitespace=False) or [""]
    pages = []
    for i in range(0, len(wrapped), rows):
        im = Image.new("RGB", (w, h), "white")
        d = ImageDraw.Draw(im)
        for k, ln in enumerate(wrapped[i:i + rows]):
            d.text((margin, margin + k * size * 1.25), ln, fill="black", font=font)
        pages.append(im)
    return pages[:LOG_PAGES]


def send_logs(s=None):
    """PaperDaemon's logs, as pages appended to every inbox notebook and pushed. -> {sent, notebooks, pages}."""
    s = s or S.load()
    pictures = _log_pages(_log_text())
    from paperdaemon.pipeline.page import images as IM
    from paperdaemon.remarkable import sync as C
    with _lock:
        if not paths.local_only():
            C.pull()
        docs = _targets(s)
        for doc in docs:
            made = _inbox_pages(doc, len(pictures), int(time.time() * 1000))
            for (page_no, pid), im in zip(made, pictures):
                fd, png = tempfile.mkstemp(suffix=".png", dir=paths.sub("tmp"))
                os.close(fd)
                try:
                    im.save(png)
                    from paperdaemon.pipeline.page import tablets as TB
                    IM.insert(doc, page_no, png, TB.picture_page(TB.frame_of(doc, page_no))[0], page_id=pid)
                finally:
                    try:
                        os.remove(png)
                    except OSError:
                        pass
        _push_inbox(docs)
        return {"sent": True, "notebooks": len(docs), "pages": len(pictures)}
