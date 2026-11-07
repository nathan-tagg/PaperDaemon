"""The web: searches, Wikipedia summaries and pictures fetched from a page or a site."""
import base64
import io
import json
import math
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
# STOCK-PHOTO SITES serve their pictures as watermarked previews: "a real photo" came back with the site's name across
# it. Their pictures are never taken; Wikimedia's (free, unmarked, described) are tried first.
_STOCK_HOSTS = ("shutterstock.", "depositphotos.", "alamy.", "istockphoto.", "gettyimages.", "dreamstime.", "123rf.",
                "stock.adobe.", "bigstockphoto.", "pond5.", "vectorstock.", "canstockphoto.", "stockfresh.", "fotolia.")


def _host_of(url):
    try:
        return urllib.parse.urlsplit(str(url or "")).netloc.lower()
    except ValueError:
        return ""


def _stock(r):
    """Is a search result a stock-photo site's (its page or its picture)?"""
    return any(s in _host_of(u) for u in (r.get("url"), r.get("img_src"), r.get("thumbnail_src")) for s in _STOCK_HOSTS)


def _free_first(cands):
    """Wikimedia's pictures before the rest, the search's own order kept within each."""
    return sorted(cands, key=lambda r: 0 if any("wikimedia.org" in _host_of(u) or "wikipedia.org" in _host_of(u)
                                                for u in (r.get("url"), r.get("img_src"))) else 1)


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
    # THE SAME QUERY ONCE A JOB: the decision turn's web_search, then a planned search step for the same words, ran
    # it twice (3 of 4 lookups in a dogfood run). What this job already found is kept (below) and given again.
    key = " ".join(str(query or "").split()).lower()
    for prev in H._scratch().get("searches") or []:
        if prev.get("web") and prev.get("results") and " ".join(str(prev.get("query") or "").split()).lower() == key:
            return {"results": list(prev["results"])}
    try:
        d = H._search(query)
    except Exception as e:
        return {"error": "search unavailable: %s" % str(e)[:80]}
    rs = d.get("results", [])[:5]
    if not rs:
        # NOTHING FOUND IS A SEARCH THAT FAILED, with the engines' own reasons: taken as done, it handed the answer
        # nothing, and the answer named a dozen states from memory. (A search service's engines refuse when they
        # are asked too often: "too many requests", a CAPTCHA.)
        why = "; ".join("%s: %s" % (e[0], e[1]) for e in (d.get("unresponsive_engines") or [])
                        if isinstance(e, (list, tuple)) and len(e) >= 2)[:160]
        return {"error": "the search found nothing" + (" -- the search engines refused (%s)" % why if why else "")}
    hits = [{"title": r.get("title"), "snippet": (r.get("content") or "")[:320]} for r in rs]
    # THE PAGES' OWN WORDS: a snippet is a line, and a write step given only those filled the rest in from memory
    # ("the next total eclipse crosses California, Nevada, Utah..." -- the 2044 path crosses Montana and the
    # Dakotas). The best pages are read side by side for the parts that bear on the question, and the first two that
    # give any text are kept: a page drawn by its scripts (a news site's) gives none.
    read = [(h, r.get("url")) for h, r in zip(hits, rs) if _readable_url(r.get("url"))][:4]
    if read:
        from concurrent.futures import ThreadPoolExecutor
        with ThreadPoolExecutor(len(read)) as pool:
            got = list(pool.map(lambda hu: _page_text(hu[1], query), read))
        for (h, _u), text in [(hu, t) for hu, t in zip(read, got) if t][:2]:
            h["page"] = text
    for r, h in zip(rs, hits):
        s = H._wiki_summary(r.get("url"))
        if s:
            h["summary"] = s                   # the first Wikipedia hit only: one fetch, the lead
            hits.remove(h)
            hits.insert(0, h)                  # first, so no length cap downstream can cut it
            break
    # Kept so a restart -- or a step asking the same -- does not have to search the web again for something it
    # already looked up.
    H._scratch()["searches"].append({"query": query, "results": hits, "web": True})     # (a picture search's: no)
    return {"results": hits}


_NOT_READ = ("wikipedia.org", "youtube.com", "youtu.be", "reddit.com", "facebook.com", "instagram.com", "tiktok.com",
             "x.com/", "twitter.com")      # Wikipedia's lead comes its own way; the rest are not pages of prose
_STOP = set("the and for with from that this what which when where who whom whose how why are was were will would "
            "could should can into onto about over under than then them they their there these those its it's our "
            "your you not but all any some one two our has have had does did doing near next".split())


def _readable_url(url):
    return bool(url) and str(url).startswith(("http://", "https://")) and not any(h in url for h in _NOT_READ) \
        and not str(url).lower().split("?")[0].endswith((".pdf", ".jpg", ".png", ".gif", ".zip"))


def readable(html, query, cap=1200):
    """The part of a page's HTML that bears on `query`: its prose (no scripts, menus, headers, footers or forms), the
    paragraphs sharing the most of the query's words, kept in the page's order, up to `cap` characters -> text."""
    import html as _html
    h = re.sub(r"(?is)<(script|style|noscript|svg|nav|header|footer|aside|form|template)\b.*?</\1\s*>", " ", html)
    h = re.sub(r"(?is)<!--.*?-->", " ", h)
    h = re.sub(r"(?i)<(br|/p|/li|/h[1-6]|/td|/th|/tr|/div|/dd|/dt|/blockquote|/section|/article)\b[^>]*>", "\n", h)
    text = _html.unescape(re.sub(r"<[^>]+>", " ", h))
    paras = [p for p in (" ".join(line.split()) for line in text.split("\n")) if len(p) >= 40]
    words = {w for w in re.findall(r"[a-z]{3,}|[0-9]{2,}", str(query).lower()) if w not in _STOP}
    if not paras or not words:
        return ""
    # A WORD IS WORTH WHAT IT TELLS APART: on a page about eclipses every paragraph says "total solar eclipse", and
    # counting it chose the page's generic opening over the paragraph with the dates and the states. Each of the
    # question's words weighs by how few of this page's paragraphs hold it (an inverse document frequency).
    low = [p.lower() for p in paras]
    weight = {w: math.log((len(paras) + 1.0) / (1.0 + sum(1 for p in low if w in p))) + 1.0 for w in words}
    score = [sum(weight[w] for w in words if w in p) for p in low]
    # the best first, each only while it still fits: shown in the page's order, a lesser paragraph above the best
    # one took the room and the cap cut the best one off
    keep, n = set(), 0
    for i in sorted(range(len(paras)), key=lambda k: (-score[k], k)):
        if score[i] == 0 or n >= cap:
            break
        if keep and n + len(paras[i]) > cap:
            continue
        keep.add(i)
        n += len(paras[i]) + 5
    return " ... ".join(paras[i] for i in sorted(keep))[:cap]


def _page_text(url, query, cap=1200):
    """A search result's page, fetched and cut to what bears on `query` (readable) -> text, or "" when it cannot be
    read (not HTML, unreachable, the internet off)."""
    try:
        req = urllib.request.Request(url, headers=H.REDDIT_UA)
        with H._net.urlopen(req, timeout=12) as r:
            kind = str(r.headers.get("Content-Type") or "")
            if "html" not in kind:
                return ""
            raw = r.read(1500000)
            charset = r.headers.get_content_charset() or "utf-8"
        return readable(raw.decode(charset, "replace"), query, cap)
    except Exception:
        return ""


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
    cands = _free_first([r for r in d.get("results", [])
                         if r.get("img_src") and not r["img_src"].lower().split("?")[0].endswith((".svg", ".gif"))
                         and not any(s in str(r.get("engine", "")).lower() for s in _SKIP_ENGINES) and not _stock(r)])
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


def t_fetch(what, place=None, site=None, paste=False):
    """A picture from the web into a planned box, traced into strokes, or pasted as itself (paste) -- a host step,
    no model turn. (A picture posted on a social site is a posts step: it goes on as the post, never traced.)"""
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
    if paste:
        try:
            H._paste_into(png, box, place, "web picture", title=hit.get("title") or what)
        except Exception as ex:
            return {"error": "the picture would not paste: %s: %s" % (type(ex).__name__, str(ex)[:120])}
        H.log("  fetched %r (%s) -> pasted as a picture in %.0fs" % ((hit.get("title") or "")[:50], hit.get("engine"),
                                                                    time.time() - t0))
        return dict({"ok": True, "pasted": True, "box": box, "title": (hit.get("title") or "")[:80],
                     "seconds": round(time.time() - t0, 1)}, **H._did())
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
