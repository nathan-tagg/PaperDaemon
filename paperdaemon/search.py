"""Web search for the host, by the active lineup: a search service with an API key (Brave, Tavily, Exa or Serper), or
a search server hosted locally (SearXNG's JSON API), started by the lineup's own start script when a search is
needed and nothing answers. Every answer comes back in SearXNG's shape -- {"results": [{"title", "url",
"content", "img_src"}]} -- so the host reads one format whatever the lineup uses. The key is the credential
store's key:search:<service>, never a file."""
import json
import threading
import time
import urllib.error
import urllib.parse
import urllib.request

from . import settings as S
from . import vault
from paperdaemon import net as _net

PROVIDERS = {"brave": "Brave Search", "tavily": "Tavily", "exa": "Exa", "serper": "Serper"}
UA = {"User-Agent": "PaperDaemon", "Accept": "application/json"}
_lock = threading.Lock()


class SearchError(Exception):
    pass


def _get(url, headers=None):
    req = urllib.request.Request(url, headers=dict(UA, **(headers or {})))
    with _net.urlopen(req, timeout=30) as r:
        return json.loads(r.read().decode("utf-8", "replace"))


def _post(url, body, headers=None):
    req = urllib.request.Request(url, data=json.dumps(body).encode(), method="POST",
                                 headers=dict(UA, **{"Content-Type": "application/json"}, **(headers or {})))
    with _net.urlopen(req, timeout=30) as r:
        return json.loads(r.read().decode("utf-8", "replace"))


def _brave(q, images, key):
    h = {"X-Subscription-Token": key}
    if images:
        d = _get("https://api.search.brave.com/res/v1/images/search?count=20&q=" + urllib.parse.quote(q), h)
        return [{"title": r.get("title") or "", "url": r.get("url") or "",
                 "img_src": (r.get("properties") or {}).get("url") or (r.get("thumbnail") or {}).get("src") or ""}
                for r in d.get("results") or []]
    d = _get("https://api.search.brave.com/res/v1/web/search?count=10&q=" + urllib.parse.quote(q), h)
    return [{"title": r.get("title") or "", "url": r.get("url") or "", "content": r.get("description") or ""}
            for r in (d.get("web") or {}).get("results") or []]


def _tavily(q, images, key):
    d = _post("https://api.tavily.com/search", {"query": q, "max_results": 10, "include_images": bool(images)},
              {"Authorization": "Bearer " + key})
    if images:
        return [{"title": "", "url": "", "img_src": (i if isinstance(i, str) else i.get("url") or "")}
                for i in d.get("images") or []]
    return [{"title": r.get("title") or "", "url": r.get("url") or "", "content": r.get("content") or ""}
            for r in d.get("results") or []]


def _serper(q, images, key):
    h = {"X-API-KEY": key}
    if images:
        d = _post("https://google.serper.dev/images", {"q": q}, h)
        return [{"title": r.get("title") or "", "url": r.get("link") or "", "img_src": r.get("imageUrl") or ""}
                for r in d.get("images") or []]
    d = _post("https://google.serper.dev/search", {"q": q}, h)
    return [{"title": r.get("title") or "", "url": r.get("link") or "", "content": r.get("snippet") or ""}
            for r in d.get("organic") or []]


def _exa(q, images, key):
    d = _post("https://api.exa.ai/search", {"query": q, "numResults": 10, "contents": {"text": {"maxCharacters": 600}}},
              {"x-api-key": key})
    rs = d.get("results") or []
    if images:                                       # Exa has no image search: the pages' own lead images
        return [{"title": r.get("title") or "", "url": r.get("url") or "", "img_src": r.get("image") or ""}
                for r in rs if r.get("image")]
    return [{"title": r.get("title") or "", "url": r.get("url") or "", "content": r.get("text") or ""} for r in rs]


SERVICES = {"brave": _brave, "tavily": _tavily, "exa": _exa, "serper": _serper}


def _local_url(sr, q, images):
    return "%s/search?q=%s&format=json%s" % (sr["url"].rstrip("/"), urllib.parse.quote(q), "&categories=images" if images else "")


def searxng_shape(d):
    """True when an answer is SearXNG's JSON: an object whose "results" is a list of objects, each with a "url"
    (a list may be empty). Anything else on that address is not a search server PaperDaemon can use."""
    if not isinstance(d, dict) or not isinstance(d.get("results"), list):
        return False
    return all(isinstance(r, dict) and isinstance(r.get("url"), str) for r in d["results"])


def _answering(sr):
    """The local search server answers a test search in SearXNG's shape. Whoever started it: a server already
    answering is used as it is, and its start script is not run."""
    try:
        return searxng_shape(_get(_local_url(sr, "paperdaemon", False)))
    except Exception:
        return False


def _ensure_local(sr, s):
    """The local search server answering: when it is not and the lineup has a start script, run it (PaperDaemon
    owns what it starts, and Pause and Quit end it) and wait until the server answers or the script ends."""
    if _answering(sr):
        return
    if not str(sr.get("script_text") or "").strip():
        raise SearchError("the search server at %s is not answering" % sr["url"])
    from . import scripts
    from .models import hotswap
    with _lock:
        srv = hotswap.ours("search")
        if srv is None:
            path = scripts.runnable("search", sr)
            env = hotswap.environment("text", s)
            parts = urllib.parse.urlsplit(sr["url"])
            env.update(PAPERDAEMON_ROLE="search", PAPERDAEMON_LOCATION=sr["url"], PAPERDAEMON_HOST=parts.hostname or "",
                       PAPERDAEMON_PORT=str(parts.port or (443 if parts.scheme == "https" else 80)))
            proc, job = hotswap._spawn(path, env)
            srv = hotswap._servers["search"] = hotswap.Server("search", proc, job, path, S.active(s)["name"])
    while srv.alive():
        if _answering(sr):
            srv.ready = True
            return
        time.sleep(hotswap.POLL)
    if not _answering(sr):
        raise SearchError("the search start script ended and %s is not answering" % sr["url"])


def query(q, images=False, s=None):
    """Search with the active lineup's web search -> {"results": [...]} in SearXNG's shape."""
    s = s or S.load()
    sr = S.active(s).get("search") or {}
    kind = sr.get("kind") or "none"
    if kind == "api":
        fn = SERVICES.get(sr.get("provider") or "")
        key = vault.get(vault.key_name("search", sr.get("provider") or ""))
        if not fn:
            raise SearchError("the lineup's search service is not one PaperDaemon knows")
        if not key:
            raise SearchError("the search service has no API key")
        try:
            return {"results": fn(q, images, key)}
        except urllib.error.HTTPError as ex:
            raise SearchError("%s answered %s" % (PROVIDERS[sr["provider"]], ex.code))
    if kind == "local":
        _ensure_local(sr, s)
        return _get(_local_url(sr, q, images))
    raise SearchError("this lineup has no web search")
