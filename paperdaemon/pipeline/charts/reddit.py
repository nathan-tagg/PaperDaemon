r"""Reddit for the post cards: posts, and each post's top comments -- with votes once a key is set.

What reaches Reddit from a typical home machine, as measured:

  * the no-key JSON pages -- "403 Blocked";
  * old.reddit.com -- a login page; the ordinary pages -- a script check instead of content;
  * a headless browser -- "You've been blocked by network security". Not something to trick: it is
    Reddit's own bot protection;
  * the RSS feeds -- WORK: a subreddit's posts, a search, and a post's comments (author and text,
    in Reddit's "best" order), but no vote or comment counts;
  * Reddit's own EMBED CARD (embed.reddit.com, what other websites show a post with) -- WORKS, and
    carries the numbers: a post's upvotes and comment count, a comment's upvotes.

So posts and comments come from the feeds and their numbers from the embed cards (numbers()). A key
for Reddit's API can no longer be had (new apps have not been granted since November 2025); the API
path below stays for one that ever lands in the credential store as "key:reddit", holding
{"client_id": ..., "client_secret": ...} as JSON.
"""
import base64
import html
import json
import os
import re
import sys
import time
import urllib.parse
import urllib.request
from paperdaemon import net as _net

UA = "PaperDaemon/1.0 (reMarkable assistant)"
TTL = 300                        # a feed answers 429 to a few quick requests: each is kept 5 minutes
_CACHE = {}
_TOKEN = {}


_LAST = [0.0]
GAP = 6.5                        # seconds between feed requests at the least
_LAST_EMBED = [0.0]
EMBED_GAP = 1.5                  # the embed cards' host, paced on its own: a card's numbers are
#                                  fetched inside the wait for the next post's comments feed
_WINDOW = {"until": 0.0}         # when the feeds take a request again, as Reddit's own answer says


def _note_limit(headers):
    """Reddit states its limit on every feed answer: requests left in this window
    (x-ratelimit-remaining) and seconds until the next (x-ratelimit-reset). Measured from a home
    machine: ONE request a minute, windows on the minute. The next request waits for the
    window it names -- a guessed wait fired into a closed one: 30 s of retries, then the post's
    comments were lost."""
    try:
        left = float(headers.get("x-ratelimit-remaining"))
        reset = float(headers.get("x-ratelimit-reset"))
    except (TypeError, ValueError, AttributeError):
        return
    _WINDOW["until"] = time.time() + reset + 0.5 if left < 1 else 0.0


def _get(url, headers=None, data=None):
    feed = "oauth.reddit.com" not in url and "//embed.reddit.com" not in url
    if "oauth.reddit.com" not in url:            # the API has its own, far larger, allowance
        last, gap = (_LAST, GAP) if feed else (_LAST_EMBED, EMBED_GAP)
        wait = max(last[0] + gap, _WINDOW["until"] if feed else 0.0) - time.time()
        if wait > 0:
            time.sleep(wait)
        last[0] = time.time()
    req = urllib.request.Request(url, data=data, headers=dict({"User-Agent": UA}, **(headers or {})))
    try:
        resp = _net.urlopen(req, timeout=20)
    except urllib.error.HTTPError as ex:
        if feed:
            _note_limit(ex.headers)
        raise
    if feed:
        _note_limit(resp.headers)
    return resp.read()


def _cached(key, fn):
    hit = _CACHE.get(key)
    if hit and time.time() - hit[0] < TTL:
        return hit[1]
    out = fn()
    _CACHE[key] = (time.time(), out)
    return out


def _retry(fn, tries=3):
    """A polite retry of a rate limit (429), not a model clock: after the window Reddit names (which
    _get waits out), or 10 s then 20 s when it names none."""
    for i in range(tries):
        try:
            return fn()
        except urllib.error.HTTPError as ex:
            if ex.code == 429 and i < tries - 1:
                if _WINDOW["until"] <= time.time():
                    time.sleep(10 * (i + 1))
                continue
            raise


# ------------------------------------------------------------------ the API, when there is a key
def _key():
    try:
        from paperdaemon import vault
        k = json.loads(vault.get("key:reddit") or "null") or {}
        return k if k.get("client_id") and k.get("client_secret") else None
    except Exception:
        return None


def _token():
    k = _key()
    if not k:
        return None
    if _TOKEN.get("exp", 0) > time.time() + 60:
        return _TOKEN["tok"]
    auth = base64.b64encode(("%s:%s" % (k["client_id"], k["client_secret"])).encode()).decode()
    d = json.loads(_get("https://www.reddit.com/api/v1/access_token",
                        {"Authorization": "Basic " + auth},
                        urllib.parse.urlencode({"grant_type": "client_credentials"}).encode()))
    _TOKEN.update(tok=d["access_token"], exp=time.time() + int(d.get("expires_in", 3600)))
    return _TOKEN["tok"]


def _api(path):
    tok = _token()
    return json.loads(_get("https://oauth.reddit.com" + path, {"Authorization": "bearer " + tok}))


def _image_of(d):
    u = d.get("url_overridden_by_dest") or d.get("url") or ""
    if re.search(r"(i\.redd\.it|i\.imgur\.com)/|\.(jpe?g|png|webp)(\?|$)", u, re.I):
        return u
    try:
        return html.unescape(d["preview"]["images"][0]["source"]["url"])
    except (KeyError, IndexError, TypeError):
        return ""


def _api_posts(sub, sort, period, limit):
    q = "?limit=%d%s" % (limit, ("&t=" + period) if sort == "top" else "")
    d = _api("/r/%s/%s%s" % (sub, sort, q))
    out = []
    for c in d["data"]["children"]:
        p = c["data"]
        out.append({"title": p.get("title", ""), "author": p.get("author", ""),
                    "score": p.get("score"), "comments": p.get("num_comments"),
                    "posted": time.strftime("%Y-%m-%d %H:%M", time.gmtime(p.get("created_utc", 0))),
                    "url": "https://www.reddit.com" + p.get("permalink", ""),
                    "link": p.get("url_overridden_by_dest") or "", "image": _image_of(p),
                    "text": (p.get("selftext") or "")[:700], "nsfw": bool(p.get("over_18"))})
    return out


def _api_comments(permalink, limit):
    path = re.sub(r"^https?://[^/]+", "", permalink).rstrip("/")
    d = _api(path + "?limit=%d&sort=top&depth=1" % (limit + 4))
    out = []
    for c in d[1]["data"]["children"]:
        if c.get("kind") != "t1":
            continue
        x = c["data"]
        if x.get("stickied") or (x.get("author") or "").lower() == "automoderator":
            continue
        out.append({"author": x.get("author"), "score": x.get("score"), "text": (x.get("body") or "")[:500]})
        if len(out) >= limit:
            break
    return out


# ------------------------------------------------------------------ the feeds, always
def _feed_entries(url):
    import xml.etree.ElementTree as ET
    data = _retry(lambda: _get(url))
    ns = {"a": "http://www.w3.org/2005/Atom"}
    return ET.fromstring(data).findall("a:entry", ns), ns


def _feed_posts(sub, sort, period, limit):
    path = "" if sort == "hot" else sort + "/"
    url = "https://www.reddit.com/r/%s/%s.rss?limit=%d%s" % (sub, path, limit, ("&t=" + period) if sort == "top" else "")
    return _posts_of_feed(url)


def _feed_search(query, sub, sort, period, limit):
    """Reddit's own SEARCH, as a feed: posts matching `query` sitewide or inside r/<sub>. The search
    feeds answer (measured: 25 posts for a model-name query, top of the week, sitewide and inside a
    subreddit) where the API wants an app Reddit no longer grants and a private feed token opens
    only a login page."""
    q = {"q": query, "sort": sort if sort in ("relevance", "top", "new", "hot", "comments") else "relevance",
         "t": period if period in ("hour", "day", "week", "month", "year", "all") else "all",
         "type": "link", "limit": str(limit)}
    if sub:
        q["restrict_sr"] = "on"
    url = "https://www.reddit.com/%ssearch.rss?%s" % (("r/%s/" % sub) if sub else "", urllib.parse.urlencode(q))
    return _posts_of_feed(url)


def _posts_of_feed(url):
    """A listing or search feed -> posts (title, author, community, when, link, picture, text)."""
    ents, ns = _feed_entries(url)
    out = []
    for e in ents:
        content = html.unescape(e.findtext("a:content", default="", namespaces=ns) or "")
        lk = re.search(r'<a href="([^"]+)">\[link\]', content)
        link = lk.group(1) if lk else ""
        image = link if re.search(r"(i\.redd\.it|i\.imgur\.com)/|\.(jpe?g|png|webp)(\?|$)", link, re.I) else ""
        if not image:
            im = re.search(r'<img src="(https://(?:preview|external-preview)\.redd\.it/[^"]+)"', content)
            image = im.group(1) if im else ""
        md = re.search(r'<div class="md">(.*?)</div>', content, re.S)
        el = e.find("a:link", ns)
        cat = e.find("a:category", ns)                  # its subreddit: a search's posts come from many
        out.append({"sub": cat.get("term") if cat is not None else "",
                    "title": (e.findtext("a:title", default="", namespaces=ns) or "").strip(),
                    "author": (e.findtext("a:author/a:name", default="", namespaces=ns) or "").replace("/u/", ""),
                    "score": None, "comments": None,
                    "posted": (e.findtext("a:updated", default="", namespaces=ns) or "")[:16].replace("T", " "),
                    "url": el.get("href") if el is not None else "", "link": link, "image": image,
                    "text": " ".join(html.unescape(re.sub(r"<[^>]+>", " ", md.group(1))).split())[:700] if md else "",
                    "nsfw": False})
    return out


def _feed_comments(permalink, limit):
    ents, ns = _feed_entries(permalink.rstrip("/") + "/.rss?limit=%d" % (limit + 6))
    out = []
    for e in ents[1:]:                          # the first entry is the post itself
        who = (e.findtext("a:author/a:name", default="", namespaces=ns) or "").replace("/u/", "")
        body = html.unescape(e.findtext("a:content", default="", namespaces=ns) or "")
        text = " ".join(html.unescape(re.sub(r"<[^>]+>", " ", body)).split())
        if not text or who.lower() in ("automoderator", "") or text in ("[removed]", "[deleted]"):
            continue
        if re.match(r"^(hi and )?welcome to r/", text, re.I):     # a sub's own greeting bot
            continue
        # a sub's other bots, pinned above the people: the feed has no "stickied", their words say it
        # ("...I am a bot and this action was performed automatically", "UPVOTE this comment")
        if re.search(r"\bI(?:'m| am) a bot\b|performed automatically|\b(?:up|down)vote this comment\b", text, re.I):
            continue
        el = e.find("a:link", ns)                  # the comment's own address: its numbers (numbers())
        out.append({"author": who, "score": None, "text": text[:500], "url": el.get("href") if el is not None else ""})
        if len(out) >= limit:
            break
    return out


# ------------------------------------------------------------------ the embed cards: the numbers
def _count_of(s):
    """'70' / '1,234' / '1.2K' -> 70 / 1234 / 1200, or None."""
    s = (s or "").replace(",", "").strip()
    mult = {"k": 1000, "m": 1000000}.get(s[-1:].lower(), 1)
    try:
        return int(round(float(s[:-1] if mult > 1 else s) * mult))
    except ValueError:
        return None


def _embed_numbers(permalink):
    """What Reddit's own embed card shows for a post or a comment -> {"score", "comments"}, None where
    the card shows none. Measured on one post: "539 upvotes", "View 70 comments"; on one of its
    comments "25 upvotes" (and "View 4 comments": its replies). The page's script also holds
    a "blocked by network security" message -- an error string it keeps, not a block."""
    path = re.sub(r"^https?://[^/]+", "", permalink).split("?")[0]
    path = path if path.endswith("/") else path + "/"
    body = _retry(lambda: _get("https://embed.reddit.com%s?embed=true&showmedia=false" % path)).decode("utf-8", "replace")
    s = re.search(r'<faceplate-number number="(-?\d+)"[^>]*>\s*</faceplate-number>\s*upvotes?\b', body)
    c = re.search(r"\bView\s+([\d.,]+[kKmM]?)\s+comments?\b", body)
    return {"score": int(s.group(1)) if s else None, "comments": _count_of(c.group(1)) if c else None}


def numbers(permalink):
    """A post's upvotes and comment count, or a comment's upvotes -> {"score", "comments"}; Nones
    when the card cannot be read."""
    try:
        return _cached(("numbers", permalink), lambda: _embed_numbers(permalink))
    except Exception:
        return {"score": None, "comments": None}


# ------------------------------------------------------------------ what the host calls
def posts(sub, sort="hot", period="day", limit=12):
    """The posts on r/<sub> -> {"sub", "sort", "votes": bool, "posts": [...]} or {"error"}. Each post:
    title, author, score, comments (None without a key), posted (UTC), url, link, image, text."""
    def go():
        if _key():
            try:
                return _api_posts(sub, sort, period, limit), True
            except Exception:
                pass                            # a bad key or a hiccup: the feed still answers
        return _feed_posts(sub, sort, period, limit), False
    try:
        got, votes = _cached(("posts", sub, sort, period, limit), go)
    except Exception as ex:
        return {"error": "reddit unavailable for r/%s: %s" % (sub, type(ex).__name__)}
    return {"sub": sub, "sort": sort + (" of the " + period if sort == "top" else ""), "votes": votes,
            "posts": got}


def search(query, sub=None, sort="relevance", period="all", limit=12):
    """Reddit's search for `query`, sitewide or inside r/<sub> -> {"sub", "query", "sort", "votes",
    "posts"} or {"error"}. Each post carries its own subreddit ("sub")."""
    try:
        got = _cached(("search", query, sub, sort, period, limit),
                      lambda: _feed_search(query, sub, sort, period, limit))
    except Exception as ex:
        return {"error": "reddit search unavailable for %r: %s" % (query, type(ex).__name__)}
    # A CROSS-POST is one story in several communities: it gets one card, the first Reddit ranks.
    # Otherwise the same story can fill two of four cards, one from each community.
    seen, uniq = set(), []
    for p in got:
        keys = [k for k in ((p.get("link") or "").split("?")[0].rstrip("/").lower(),
                            " ".join(str(p.get("title") or "").lower().split())) if k]
        if any(k in seen for k in keys):
            continue
        seen.update(keys)
        uniq.append(p)
    return {"sub": sub or "", "query": query, "sort": sort + (" of the " + period if sort == "top" else ""),
            "votes": False, "posts": uniq}


def comments(permalink, limit=3):
    """A post's top comments -> [{author, score (None without a key), text}]; [] if unreadable."""
    def go():
        if _key():
            try:
                return _api_comments(permalink, limit)
            except Exception:
                pass
        return _feed_comments(permalink, limit)
    try:
        return _cached(("comments", permalink, limit), go)
    except Exception:
        return []
