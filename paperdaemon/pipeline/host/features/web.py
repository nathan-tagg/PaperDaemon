"""The web: searches, Wikipedia summaries and pictures fetched from a page or a site."""
import base64
import io
import json
import os
import re
import time
import urllib.error
import urllib.parse
import urllib.request
from PIL import Image
from paperdaemon.pipeline.host.job import JOB
from paperdaemon.pipeline import host as H

SKETCH_UA = {"User-Agent": "PaperDaemon/1.0 (reMarkable assistant)"}
_SKIP_ENGINES = ("lucide", "devicons", "svgrepo", "material icons")


def _wiki_summary(url):
    """The lead of a Wikipedia article, from its REST summary: the facts a search snippet cuts off (a snippet
    can stop one word short of the answer, and the model fills the gap from memory)."""
    m = re.match(r"https?://en\.(?:m\.)?wikipedia\.org/wiki/([^#?]+)", str(url or ""))
    if not m:
        return None
    # the first eight sentences, not the REST "summary": for a mountain peak that summary can be ONE
    # sentence (height only) and the county is in the next paragraph
    try:
        u = ("https://en.wikipedia.org/w/api.php?action=query&prop=extracts&exsentences=8&explaintext=1"
             "&redirects=1&format=json&titles=" + m.group(1))
        req = urllib.request.Request(u, headers={"User-Agent": "PaperDaemon/1.0 (reMarkable assistant)"})
        d = json.loads(H._net.urlopen(req, timeout=6).read())
        text = " ".join(p.get("extract") or "" for p in (d.get("query") or {}).get("pages", {}).values())
    except Exception:
        return None
    text = text.split("== See also ==")[0]
    text = re.sub(r"==+[^=]*==+", " ", text)
    text = " ".join(text.split())
    return text[:1100] or None


def t_web_search(query):
    try:
        d = H._search(query)
    except Exception as e:
        return {"error": "search unavailable: %s" % str(e)[:80]}
    rs = d.get("results", [])[:5]
    hits = [{"title": r.get("title"), "snippet": (r.get("content") or "")[:320]} for r in rs]
    for r, h in zip(rs, hits):
        s = H._wiki_summary(r.get("url"))
        if s:
            h["summary"] = s                   # the first Wikipedia hit only: one fetch, the lead
            hits.remove(h)
            hits.insert(0, h)                  # first, so no length cap downstream can cut it
            break
    # Kept so a restart does not have to search the web again for something it
    # already looked up.
    H._scratch()["searches"].append({"query": query, "results": hits[:3]})
    return {"results": hits}


def _search(q, images=False):
    """A web search by the active lineup, through the engine (paperdaemon/search.py): a search service or the
    lineup's local search server, in SearXNG's shape."""
    try:
        return H._studio("/search?q=%s&images=%d" % (urllib.parse.quote(q), 1 if images else 0))
    except urllib.error.HTTPError as ex:
        try:
            msg = json.loads(ex.read().decode("utf-8", "replace")).get("error")
        except Exception:
            msg = None
        raise RuntimeError(msg or "search unavailable (%s)" % ex.code)


def _fetch_path():
    """Where a downloaded picture waits for the decomposer (which deletes it). The process is in the name: the
    queue folder is shared by the host and any test."""
    return os.path.join(H.QUEUE, "_host_fetch_%d_%d.png" % (os.getpid(), int(time.time() * 1000)))


def _data_image(url, width=1000):
    """A picture from the web -> {url: data URI, w, h} for a chart to embed, or None. Scaled down
    and re-encoded so a card with four pictures stays a small spec."""
    try:
        raw = H._net.urlopen(urllib.request.Request(url, headers=H.REDDIT_UA), timeout=20).read()
        im = Image.open(io.BytesIO(raw))
        im.load()
        im = im.convert("RGB")
        if im.width > width:
            im = im.resize((width, int(im.height * width / float(im.width))), Image.LANCZOS)
        buf = io.BytesIO()
        im.save(buf, "JPEG", quality=85)
        return {"url": "data:image/jpeg;base64," + base64.b64encode(buf.getvalue()).decode(),
                "w": im.width, "h": im.height}
    except Exception:
        return None


def _fetch_png(what, site=None, tries=6):
    """An image search, the first raster that downloads -> local PNG path, a source for the decomposer. The step's
    `site` narrows the search (site:<domain>). Icon fonts and SVGs are skipped; a candidate must be a raster at
    least 256 px on its short side."""
    q = ("%s site:%s" % (what, site)) if site else what
    d = H._search(q, images=True)
    cands = [r for r in d.get("results", [])
             if r.get("img_src") and not r["img_src"].lower().split("?")[0].endswith((".svg", ".gif"))
             and not any(s in str(r.get("engine", "")).lower() for s in _SKIP_ENGINES)]
    H._scratch()["searches"].append({"query": q, "results": [
        {"title": r.get("title"), "snippet": (r.get("img_src") or "")[:120]} for r in cands[:3]]})
    tried = 0
    for r in cands:
        if tried >= tries:
            break
        tried += 1
        try:
            req = urllib.request.Request(r["img_src"], headers=SKETCH_UA)
            raw = H._net.urlopen(req, timeout=20).read()
            im = Image.open(io.BytesIO(raw))
            im.load()
            if min(im.size) < 256:
                continue
            png = H._fetch_path()
            im.convert("RGB").save(png)
            return png, r
        except Exception:
            continue
    raise RuntimeError("no usable picture found for %r (%d candidates, %d tried)" % (what[:60], len(cands), tried))


def t_fetch(what, place=None, site=None):
    """A picture from the web into a planned box, traced into strokes -- a host step, no model turn. (A picture
    posted on a social site is a posts step: it goes on as the post, never traced.)"""
    boxes = (JOB.plan or {}).get("places") or {}
    if place is None:
        place = H._cur_place()
    box = boxes.get(place)
    if box is None:
        return {"error": "no box to put the picture in (place %r)" % place}
    t0 = time.time()
    try:
        png, hit = H._fetch_png(what, site)
    except Exception as ex:
        return {"error": "could not fetch a picture: %s: %s" % (type(ex).__name__, str(ex)[:140])}
    try:
        n = H._trace_into(png, box, place, "web picture")
    except Exception as ex:
        return {"error": "the picture would not trace: %s: %s" % (type(ex).__name__, str(ex)[:120])}
    H.log("  fetched %r (%s) -> %d strokes in %.0fs" % ((hit.get("title") or "")[:50], hit.get("engine"), n, time.time() - t0))
    return dict({"ok": True, "strokes": n, "box": box, "title": (hit.get("title") or "")[:80],
                 "seconds": round(time.time() - t0, 1)}, **H._did())


# the tools this module serves, as the host offers them (the host's TOOLS keeps this order)
TOOLS = [
 ("web_search", "Search the web, for a fact you cannot already know.", {"query": "string"}, t_web_search),
]
