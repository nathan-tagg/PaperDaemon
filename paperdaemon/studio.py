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

The inbox is the notebook named in the settings (tablet.inbox, a path such as "Folder/Inbox"). It is
created on the first send, carrying the ignore tag so the daemon never treats the pictures as requests.
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


def decompose(image, width=None, preview=True, job=None, keep=None):
    """A picture (data URL or base64) -> ({preview, strokes, points, seconds, box, width, height}, the strokes). With
    `keep` (the picture's name), the decomp is kept on disk (see the module's note) and the answer carries its id, and
    its preview is the kept file's, not a data URL."""
    raw = _bytes(image)
    box = box_for(width)
    with _lock:
        _now.update(job=job, stage="decompose", share=0.0)
        try:
            out, strokes = _decompose_locked(raw, box, preview and keep is None)
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


def _decompose_locked(raw, box, preview):
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
        strokes, _params, secs = M.decompose_into(src, box, box, origin=(-box / 2.0, TOP), budget=BUDGET)
    finally:
        try:
            os.remove(src)
        except OSError:
            pass
    xs = [x for st in strokes for x, _y in st[0]]
    ys = [y for st in strokes for _x, y in st[0]]
    out = {"strokes": len(strokes), "points": len(xs), "seconds": secs, "box": box,
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
    meta.update(id=did, created=int(time.time() * 1000), sent=None)
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


def decomp_sent(did, page):
    """The page a kept decomp landed on, kept with it."""
    m = decomp_meta(did)
    m["sent"] = page
    with open(os.path.join(_decomp_dir(did), "meta.json"), "w", encoding="utf-8") as f:
        json.dump(m, f)


def delete_decomp(did):
    import shutil
    shutil.rmtree(_decomp_dir(did))


# ---------------------------------------------------------------- the inbox

def _meta(mirror, doc):
    try:
        with open(os.path.join(mirror, doc + ".metadata"), encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        return {}


def _children(mirror, parent, kind):
    out = {}
    for n in os.listdir(mirror):
        if not n.endswith(".metadata"):
            continue
        d = n[:-len(".metadata")]
        m = _meta(mirror, d)
        if m.get("parent") == parent and m.get("type") == kind and not m.get("deleted"):
            out[d] = m
    return out


def split_inbox(path):
    """"Folder/Sub/Inbox" -> (["Folder", "Sub"], "Inbox")."""
    parts = [p.strip() for p in str(path or "").replace("\\", "/").split("/") if p.strip()]
    if not parts:
        raise ValueError("the inbox has no name")
    return parts[:-1], parts[-1]


def _first_made(items):
    """Of several folders or notebooks with one name, the one made first (the maintainer's rule: never refuse)."""
    def made(dm):
        v = str(dm[1].get("createdTime") or "")
        return (int(v) if v.isdigit() else 1 << 62, dm[0])
    return min(items, key=made)[0] if items else None


def find_inbox(mirror, path):
    """The inbox notebook's doc id in the mirror, or None (folders must match too). Where two share a name (an
    edge case), the one made first is used; a send is never refused for it."""
    folders, name = split_inbox(path)
    parent = ""
    for f in folders:
        hit = _first_made([(d, m) for d, m in _children(mirror, parent, "CollectionType").items() if m.get("visibleName") == f
                           and m.get("parent") != "trash"])
        if not hit:
            return None
        parent = hit
    return _first_made([(d, m) for d, m in _children(mirror, parent, "DocumentType").items() if m.get("visibleName") == name
                        and m.get("parent") != "trash"])


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


def _inbox_pages(s, count, now):
    """Append `count` blank pages to the inbox notebook (made when it is not there)
    -> (doc, [(page_no, page_id)], created). The caller writes them and then calls _push_inbox."""
    from paperdaemon.pipeline import TEMPLATES
    from paperdaemon.pipeline.page import render as R
    pipeline = os.path.dirname(TEMPLATES)
    mirror = R.RM
    folders, name = split_inbox(s["tablet"]["inbox"])
    doc = find_inbox(mirror, s["tablet"]["inbox"])
    created = doc is None
    if created:
        parent = ""
        if folders:
            from paperdaemon.remarkable import library as F
            for f in folders:
                parent = F.ensure_folder(f, parent)
        doc = str(uuid.uuid4())
        _new_notebook(mirror, pipeline, doc, name, parent, now)
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
    return doc, out, created


def _push_inbox(doc, pids, created):
    """The inbox's new pages, with the notebook's size brought up to date, pushed to the tablet."""
    from paperdaemon.pipeline.page import render as R
    from paperdaemon.remarkable import sync as C
    mirror = R.RM
    cpath = os.path.join(mirror, doc + ".content")
    with open(cpath, encoding="utf-8") as f:
        content = json.load(f)
    content["sizeInBytes"] = str(sum(os.path.getsize(os.path.join(mirror, doc, p["id"] + ".rm"))
                                     for p in content["cPages"]["pages"]
                                     if os.path.exists(os.path.join(mirror, doc, p["id"] + ".rm"))))
    paths.write_atomic(cpath, json.dumps(content, indent=4))
    if paths.local_only():
        return                             # the false mirror's inbox: written, and that is the whole of it
    # THE ONE WAY TO THE TABLET (sync.push_pending): the inbox (and its folder, when it was just made) goes up with
    # everything else the mirror holds that the cloud does not
    def ours():
        got = dict(C.push_pending()["pushed"])
        return got.get(doc) or {}
    out = ours()
    for _ in range(4):                     # the tablet syncing mid-push moves the generation
        if out.get("root_put") == 200:
            break
        time.sleep(2)
        out = ours()
    if out.get("root_put") != 200:
        raise RuntimeError("the push did not go through: %r" % (out,))


def _settings():
    """The settings, with the inbox this mirror's: in the false mirror's engine, its own decompose inbox."""
    s = S.load()
    if paths.local_only():
        s["tablet"] = dict(s.get("tablet") or {}, inbox=str((s.get("false_mirror") or {}).get("inbox") or ""))
    return s


def send(image=None, width=None, s=None, decomp=None):
    """Append a page with the strokes of a kept decomp (`decomp`, its id) or of a picture decomposed now to the inbox
    notebook and push it. -> {sent, doc, page}."""
    s = s or _settings()
    if not str((s.get("tablet") or {}).get("inbox") or "").strip():
        raise ValueError("set an inbox in the Settings tab first")
    strokes = decomp_strokes(decomp) if decomp else decompose(image, width, preview=False)[1]
    from paperdaemon.pipeline import draw as A
    from paperdaemon.remarkable import sync as C
    from paperdaemon.pipeline import page as PG
    with _lock:
        if not paths.local_only():
            C.pull()
        doc, [(page_no, pid)], created = _inbox_pages(s, 1, int(time.time() * 1000))
        # THE INBOX PAGE'S OWN TABLET: the strokes were laid out on a Paper Pro page; another tablet's page has them
        # scaled to its width (tablets.picture_page)
        from paperdaemon.pipeline.page import tablets as TB
        frame = TB.frame_of(doc, page_no)
        k = TB.picture_page(frame)[1]
        if abs(k - 1.0) > 1e-6:
            strokes = [([(x * k, y * k) for x, y in st[0]], [w * k for w in st[1]]) + tuple(st[2:]) for st in strokes]
        d = A.Drawing(*[int(round(v)) for v in frame])
        d.strokes = list(strokes)
        w = d.write_rm(doc, page_no)
        if not (w or {}).get("written"):
            raise RuntimeError("the page could not be written: %r" % (w,))
        PG.record_provenance(doc, page_no, strokes=d.strokes, what="decompose and send, %d strokes" % len(strokes),
                             kind="drawing")
        _push_inbox(doc, [pid], created)
        return {"sent": True, "doc": doc, "page": page_no, "created": created, "strokes": len(strokes)}


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
    """PaperDaemon's logs, as pages appended to the inbox notebook and pushed. -> {sent, doc, pages, first}."""
    s = s or S.load()
    if not str((s.get("tablet") or {}).get("inbox") or "").strip():
        raise ValueError("set an inbox in the settings first")
    pictures = _log_pages(_log_text())
    from paperdaemon.pipeline.page import images as IM
    from paperdaemon.remarkable import sync as C
    with _lock:
        if not paths.local_only():
            C.pull()
        doc, made, created = _inbox_pages(s, len(pictures), int(time.time() * 1000))
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
        _push_inbox(doc, [pid for _n, pid in made], created)
        return {"sent": True, "doc": doc, "pages": len(made), "first": made[0][0]}
