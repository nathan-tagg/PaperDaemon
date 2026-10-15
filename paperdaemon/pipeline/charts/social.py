r"""Posts from the sites that let a program read them without an account -- for the post cards.

The sites below were tested with no account and no key:

  4chan         the official read-only API: a board's catalog, a thread's replies, the pictures
  Hacker News   the official API: stories with their scores and comment counts, the comments
  Bluesky       the public AppView: a feed or an account's posts, likes/reposts/replies, the thread
  Mastodon      a server's public API: trending posts or a hashtag, favorites/boosts, the replies
  X / Twitter   ONE post, by its link, through its public embed data (text, likes, replies) --
                search and timelines need a login, so a request for "top tweets" has to find the
                posts first (a web search) and then fetch each by its link
  Instagram,    not readable without logging in (their public endpoints and embeds need a Meta app
  Facebook      token) -- not done

Reddit is rm_reddit. Every reader returns posts in the post card's own shape:
    {community, author, posted, title, text, link, image (a URL), score, comments, site,
     top: [{author, score, text}], nsfw}
A NSFW post's picture is left off its card (the card still says what it is).

    py rm_social.py 4chan/g             a probe of one source
"""
import html
import json
import math
import re
import sys
import time
import urllib.parse
import urllib.request
from paperdaemon import net as _net

UA = "PaperDaemon/1.0 (reMarkable assistant)"
TTL = 300
_CACHE = {}


def _json(url):
    hit = _CACHE.get(url)
    if hit and time.time() - hit[0] < TTL:
        return hit[1]
    d = json.loads(_net.urlopen(urllib.request.Request(url, headers={"User-Agent": UA}), timeout=20).read())
    _CACHE[url] = (time.time(), d)
    return d


def _plain(s):
    """HTML -> plain text, line breaks kept as spaces. <wbr> is a place a long word MAY break, not a
    space: 4chan puts one every 35 characters of a link, and turning it into a space cuts a link
    in two ("example.com/some-lo ng-path")."""
    s = re.sub(r"<wbr\s*/?>", "", s or "")
    s = re.sub(r"<br\s*/?>", " ", s)
    return " ".join(html.unescape(re.sub(r"<[^>]+>", " ", s)).split())


def ago(ts):
    """When a post was made, the way a card says it: minutes, hours, days -- and past a month the
    date itself ("7491 d ago" for a post from 2006 says nothing). Every site's cards use this."""
    s = time.time() - float(ts)
    if s >= 30 * 86400:
        return time.strftime("%b %d, %Y", time.localtime(float(ts))).replace(" 0", " ")
    return ("%d min ago" % max(1, s // 60) if s < 3600 else "%d h ago" % (s // 3600) if s < 172800
            else "%d d ago" % (s // 86400))


def _iso(t):
    try:
        import datetime as dt
        return dt.datetime.fromisoformat(str(t).replace("Z", "+00:00")).timestamp()
    except Exception:
        return time.time()


# ----------------------------------------------------------------------------- 4chan
def chan(board, sort="hot", count=4, replies=2):
    """A 4chan board's threads. sort: hot/top (most replies), new (newest)."""
    board = board.strip("/")
    boards = _json("https://a.4cdn.org/boards.json").get("boards", [])
    ws = next((b.get("ws_board", 0) for b in boards if b.get("board") == board), 0)
    threads = [t for pg in _json("https://a.4cdn.org/%s/catalog.json" % board) for t in pg.get("threads", [])]
    threads = [t for t in threads if not t.get("sticky")]
    threads.sort(key=(lambda t: -t.get("time", 0)) if sort == "new" else (lambda t: -t.get("replies", 0)))
    out = []
    for t in threads[:count]:
        # a video or a GIF is shown by its still: 4chan keeps one for every file (a thread whose
        # first post is a .webm would otherwise get a card with no picture at all)
        img = ("https://i.4cdn.org/%s/%s%s" % (board, t["tim"], t["ext"])
               if t.get("tim") and t.get("ext") in (".jpg", ".jpeg", ".png") else
               "https://i.4cdn.org/%s/%ss.jpg" % (board, t["tim"]) if t.get("tim") else "")
        top = []
        if replies:
            try:
                posts = _json("https://a.4cdn.org/%s/thread/%d.json" % (board, t["no"])).get("posts", [])[1:]
                for r in posts:
                    txt = _plain(r.get("com"))
                    txt = re.sub(r">>\d+\s*", "", txt).strip()
                    if txt:
                        top.append({"author": r.get("name") or "Anonymous", "score": None, "text": txt[:400]})
                    if len(top) >= replies:
                        break
            except Exception:
                pass
        body = re.sub(r">>\d+\s*&?\s*", "", _plain(t.get("com"))).strip()     # reply links are noise on paper
        out.append({"community": "/%s/" % board, "author": t.get("name") or "Anonymous",
                    "posted": ago(t.get("time", time.time())), "title": _plain(t.get("sub")) or body[:120],
                    "text": body[:600] if t.get("sub") else "", "link": "",
                    "image": img, "score": None, "comments": t.get("replies"), "site": "4chan",
                    "comments_label": "replies",
                    "top": top, "nsfw": not ws})
    return out


# ----------------------------------------------------------------------------- Hacker News
def hn(which="top", count=4, replies=2):
    """Hacker News stories. which: top / new / best / ask / show."""
    ids = _json("https://hacker-news.firebaseio.com/v0/%sstories.json" % which)[:count]
    out = []
    for i in ids:
        s = _json("https://hacker-news.firebaseio.com/v0/item/%d.json" % i)
        top = []
        for k in (s.get("kids") or [])[:replies + 2]:          # the API's name for a story's comment ids
            try:
                c = _json("https://hacker-news.firebaseio.com/v0/item/%d.json" % k)
            except Exception:
                continue
            if c and not c.get("deleted") and not c.get("dead") and c.get("text"):
                top.append({"author": c.get("by"), "score": None, "text": _plain(c["text"])[:400]})
            if len(top) >= replies:
                break
        dom = re.sub(r"^https?://(www\.)?", "", s.get("url") or "").split("/")[0]
        out.append({"community": "Hacker News", "author": s.get("by"), "posted": ago(s.get("time", time.time())),
                    "title": s.get("title", ""), "text": _plain(s.get("text"))[:600], "link": dom,
                    "image": "", "score": s.get("score"), "comments": s.get("descendants"),
                    "site": "news.ycombinator.com", "top": top, "nsfw": False, "score_label": "points"})
    return out


# ----------------------------------------------------------------------------- Bluesky
_BSKY = "https://public.api.bsky.app/xrpc/"
HOT = "at://did:plc:z72i7hdynmk6r22z27h6tvur/app.bsky.feed.generator/whats-hot"


def _bsky_post(p, top=()):
    rec = p.get("record") or {}
    au = p.get("author") or {}
    img = ""
    emb = p.get("embed") or {}
    for im in (emb.get("images") or (emb.get("media") or {}).get("images") or []):
        img = im.get("fullsize") or im.get("thumb") or ""
        break
    # a video's still, or the preview picture of a link it shares
    img = (img or emb.get("thumbnail") or (emb.get("media") or {}).get("thumbnail")
           or (emb.get("external") or {}).get("thumb") or "")
    labels = [l.get("val") for l in (p.get("labels") or [])]
    return {"community": "Bluesky", "author": "@" + (au.get("handle") or ""),
            "posted": ago(_iso(rec.get("createdAt"))), "title": (rec.get("text") or "")[:280], "text": "",
            "link": "", "image": img, "score": p.get("likeCount"), "comments": p.get("replyCount"),
            "site": "bsky.app", "top": list(top), "score_label": "likes", "comments_label": "replies",
            "nsfw": any(l in ("porn", "sexual", "nudity", "graphic-media") for l in labels)}


def bluesky(who="", count=4, replies=2):
    """Bluesky posts: an account's ('bsky/<handle>'), or the What's Hot feed ('bsky')."""
    if who:
        feed = _json(_BSKY + "app.bsky.feed.getAuthorFeed?actor=%s&limit=%d&filter=posts_no_replies"
                     % (urllib.parse.quote(who), count + 4)).get("feed", [])
    else:
        feed = _json(_BSKY + "app.bsky.feed.getFeed?feed=%s&limit=%d" % (urllib.parse.quote(HOT), count + 4)).get("feed", [])
    out = []
    for item in feed:
        p = item.get("post") or {}
        if item.get("reason"):                       # a repost: the post is someone else's
            continue
        top = []
        if replies and p.get("replyCount"):
            try:
                th = _json(_BSKY + "app.bsky.feed.getPostThread?uri=%s&depth=1" % urllib.parse.quote(p["uri"]))
                rs = sorted((th.get("thread") or {}).get("replies") or [],
                            key=lambda r: -((r.get("post") or {}).get("likeCount") or 0))
                for r in rs:
                    rp = r.get("post") or {}
                    txt = ((rp.get("record") or {}).get("text") or "").strip()
                    if not txt:
                        continue             # a picture-only reply is a name and nothing under it
                    top.append({"author": "@" + ((rp.get("author") or {}).get("handle") or ""),
                                "score": rp.get("likeCount"), "text": txt[:400]})
                    if len(top) >= replies:
                        break
            except Exception:
                pass
        out.append(_bsky_post(p, top))
        if len(out) >= count:
            break
    return out


# ----------------------------------------------------------------------------- Mastodon
def mastodon(where="mastodon.social", count=4, replies=2):
    """Mastodon: 'mastodon/<server>' trending posts, 'mastodon/<server>/tags/<tag>' a hashtag."""
    parts = where.split("/")
    server = parts[0] or "mastodon.social"
    if len(parts) >= 3 and parts[1] == "tags":
        items = _json("https://%s/api/v1/timelines/tag/%s?limit=%d" % (server, urllib.parse.quote(parts[2]), count))
    else:
        items = _json("https://%s/api/v1/trends/statuses?limit=%d" % (server, count))
    out = []
    for s in items[:count]:
        top = []
        if replies and s.get("replies_count"):
            try:
                ctx = _json("https://%s/api/v1/statuses/%s/context" % (server, s["id"]))
                ds = sorted([d for d in ctx.get("descendants", []) if d.get("in_reply_to_id") == s["id"]],
                            key=lambda d: -(d.get("favorites_count") or 0))
                for d in ds:
                    txt = _plain(d.get("content"))
                    if not txt:
                        continue
                    top.append({"author": "@" + (d.get("account") or {}).get("acct", ""),
                                "score": d.get("favorites_count"), "text": txt[:400]})
                    if len(top) >= replies:
                        break
            except Exception:
                pass
        img = next((m.get("preview_url") or m.get("url") for m in s.get("media_attachments") or []
                    if m.get("type") == "image"), "")
        out.append({"community": server, "author": "@" + (s.get("account") or {}).get("acct", ""),
                    "posted": ago(_iso(s.get("created_at"))), "title": _plain(s.get("content"))[:280], "text": "",
                    "link": "", "image": img, "score": s.get("favorites_count"), "comments": s.get("replies_count"),
                    "site": server, "top": top, "nsfw": bool(s.get("sensitive")),
                    "score_label": "likes", "comments_label": "replies"})
    return out


# ----------------------------------------------------------------------------- X / Twitter
def x_post(url_or_id):
    """ONE post on X, by its link or id, from its public embed data -- no login, no search."""
    m = re.search(r"status(?:es)?/(\d+)", str(url_or_id)) or re.search(r"(\d{1,25})\s*$", str(url_or_id))
    if not m:
        return []
    tid = m.group(1)
    tok = re.sub(r"(0+|\.)", "", _b36((int(tid) / 1e15) * math.pi)) or "a"
    d = _json("https://cdn.syndication.twimg.com/tweet-result?id=%s&token=%s" % (tid, tok))
    user = d.get("user") or {}
    img = next((p.get("url") for p in d.get("photos") or []), "") or \
        next((m_.get("media_url_https") for m_ in d.get("mediaDetails") or [] if m_.get("type") == "photo"), "")
    return [{"community": "X", "author": "@" + (user.get("screen_name") or ""),
             "posted": ago(_iso(d.get("created_at"))), "title": d.get("text", "")[:280], "text": "",
             "link": "", "image": img, "score": d.get("favorite_count"), "comments": d.get("conversation_count"),
             "site": "x.com", "top": [], "nsfw": bool(d.get("possibly_sensitive")),
             "score_label": "likes", "comments_label": "replies"}]


def _b36(x):
    """A float in base 36, the way JavaScript's toString(36) writes it (what the embed token is)."""
    digits = "0123456789abcdefghijklmnopqrstuvwxyz"
    ip, fp = int(x), x - int(x)
    s = ""
    while ip:
        s = digits[ip % 36] + s
        ip //= 36
    s = (s or "0") + "."
    for _ in range(12):
        fp *= 36
        d = int(fp)
        s += digits[d]
        fp -= d
    return s


# ----------------------------------------------------------------------------- the one door
def fetch(source, sort="hot", count=4):
    """'4chan/g', 'hn', 'hn/new', 'bsky', 'bsky/<handle>', 'mastodon/<server>[/tags/<tag>]',
    'x/<post link>' -> ([posts], None) or (None, why)."""
    s = str(source or "").strip()
    low = s.lower()
    try:
        if low.startswith("4chan"):
            return chan(s.split("/", 1)[1] if "/" in s else "b", sort, count), None
        if low in ("hn", "hackernews", "hacker news") or low.startswith("hn/"):
            return hn(s.split("/", 1)[1] if "/" in s else ("new" if sort == "new" else "top"), count), None
        if low.startswith("bsky") or low.startswith("bluesky"):
            return bluesky(s.split("/", 1)[1] if "/" in s else "", count), None
        if low.startswith("mastodon"):
            return mastodon(s.split("/", 1)[1] if "/" in s else "mastodon.social", count), None
        if low.startswith(("x/", "twitter/")) or "x.com/" in low or "twitter.com/" in low:
            return x_post(s), None
        if low.startswith(("instagram", "facebook", "fb/")):
            return None, "Instagram and Facebook cannot be read without logging in"
    except Exception as ex:
        return None, "%s unavailable: %s" % (s, type(ex).__name__)
    return None, "no reader for %r" % s
