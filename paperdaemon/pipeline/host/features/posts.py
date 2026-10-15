"""Social posts as cards. A site a program can list (Reddit, 4chan, Hacker News, Bluesky, Mastodon, one X post by its
link) is read by the host; any other site is searched on the web and the model fills the cards from what the search
found (posts_search), every field the card has."""
import re
import time
import urllib.error
import urllib.parse
import urllib.request
from paperdaemon.pipeline.host.job import JOB
from paperdaemon.pipeline import host as H


REDDIT_TTL = 300
_REDDIT = {}


def _ago(posted):
    """'2025-03-14 17:58' (UTC) -> '8 h ago', as every site's cards say it (social.ago)."""
    import datetime as _dt
    from paperdaemon.pipeline.charts import social
    try:
        t = _dt.datetime.strptime(posted[:16], "%Y-%m-%d %H:%M").replace(tzinfo=_dt.timezone.utc)
    except Exception:
        return posted
    return social.ago(t.timestamp())


def _as_recorded(spec):
    """A spec as the picture's provenance keeps it: a clipped post's picture by where it came from,
    not its pixels. Recorded whole, a four-post card put 886 KB of base64 into pictures.json; a redo
    fetches the picture again (_fill_posts)."""
    if not isinstance(spec.get("posts"), list):
        return dict(spec)
    posts = []
    for p in spec["posts"]:
        p = dict(p)
        if isinstance(p.get("image"), dict):
            p["image"] = dict((k, v) for k, v in p["image"].items() if k != "url")
        posts.append(p)
    return dict(spec, posts=posts)


def listable(source):
    """True when the host can read the source's posts itself (_fill_posts); False sends the step to a web search."""
    low = str(source or "").strip().lower()
    if low == "reddit" or low.startswith(("r/", "4chan", "hn", "hackernews", "hacker news", "bsky", "bluesky",
                                          "mastodon")):
        return True
    # X by a post's link or id only: X lists nothing without a login
    return bool(re.search(r"status(?:es)?/\d+", low) or re.match(r"(x|twitter)/\d+\s*$", low))


POST_FIELDS = (
    "community (the site or community it was posted in, e.g. X or r/<sub>), author (the handle), posted (how long "
    "ago, e.g. 3 h ago, or the date), title (the post's own words), text (more of them), link (the domain of a link "
    "it carries), image (the address of the post's picture), score and score_label (its likes or upvotes, and which "
    "they are), comments and comments_label (how many replies or comments, and which), site (the domain, e.g. "
    "x.com), top (its top comments, at most two, each {author, text, score})")


def posts_search(step):
    """A web search for posts on a site the host cannot list -> {"results": [...]} or {"error"}. Each hit keeps
    its address and picture, so the cards can carry them."""
    src = str(step.get("source") or "").strip()
    q = " ".join(s for s in (src, str(step.get("search") or step.get("what") or "").strip(), "posts",
                             step.get("period") or "") if s)
    try:
        d = H._search(q)
    except Exception as e:
        return {"error": "search unavailable: %s" % str(e)[:80]}
    hits = [dict((k, v) for k, v in (("title", r.get("title")), ("url", r.get("url")),
                                     ("content", (r.get("content") or "")[:600]), ("image", r.get("img_src")),
                                     ("date", r.get("publishedDate"))) if v)
            for r in (d.get("results") or [])[:8]]
    if not hits:
        return {"error": "the search for %r found nothing" % q}
    H._scratch()["searches"].append({"query": q, "results": hits[:3]})
    return {"query": q, "results": hits}


def _fill_posts(spec, place=None):
    """A posts chart's posts, from the site itself -> an error string, or None. For a listed site the model
    names the source and the host reads the posts; for any other site the model hands them in, filled from the
    web search (posts_search), and they are kept as given.

    `pictures` takes picture posts only, which is what a Reddit picture is (t_fetch). A post goes on
    one card of a job at most: "the top three pictures" planned as three steps is three posts. The
    same place drawn again gets its own posts back."""
    if spec.get("posts"):
        # given already: a redo carries the posts it was made from, their pictures by address
        for p in spec["posts"]:
            if isinstance(p, dict) and isinstance(p.get("image"), str):
                p["image"] = {"src": p["image"]} if p["image"].strip() else None    # the model gives an address
            im = p.get("image") if isinstance(p, dict) else None
            if isinstance(im, dict) and not im.get("url") and im.get("src"):
                got = H._data_image(im["src"])
                p["image"] = dict(got, src=im["src"]) if got else None
        return None
    try:
        n = max(1, min(4, int(spec.get("count") or 4)))
    except (TypeError, ValueError):
        n = 4
    pictures = bool(spec.get("pictures"))
    used = JOB.reddit_used          # post -> the place it went on
    for u in [u for u, pl in used.items() if pl == place]:
        del used[u]
    # WHERE AND HOW, from the step's own fields: source, search (the topic's words only), sort and period
    src = str(spec.get("source") or "").strip()
    srcl = src.lower()
    search = " ".join(str(spec.get("search") or "").split())
    sort, period = spec.get("sort"), spec.get("period")
    ref = None
    if srcl == "reddit" or srcl.startswith("r/"):
        from paperdaemon.pipeline.charts import reddit as rm_reddit
        sub = srcl[2:] if srcl.startswith("r/") else None
        if search:
            # posts matching the topic, sitewide or inside r/<sub>, from Reddit's own search feed
            rsort = sort if sort in ("relevance", "top", "new", "hot", "comments") else "relevance"
            r = rm_reddit.search(search, sub, rsort, period if period in ("hour", "day", "week", "month", "year", "all")
                                 else "all", limit=25 if pictures else 12)
            if r.get("error"):
                return r["error"]
            cands = r["posts"]
            label = ("r/%s: %s" % (sub, search)) if sub else ("Reddit: %s" % search)
            for p in cands:
                p["community"], p["site"] = "r/%s" % (p.get("sub") or sub or "all"), "reddit"
                p["posted"] = H._ago(p.get("posted") or "")
            ref = True
        else:
            # a subreddit's (or Reddit's front page's) feed, with each post's top comments
            r = rm_reddit.posts(sub or "popular", sort if sort in ("hot", "top", "new", "rising") else "hot",
                                period if period in ("hour", "day", "week", "month", "year", "all") else "day")
            if r.get("error"):
                return r["error"]
            cands, label = r["posts"], "r/%s, %s" % (r["sub"], r["sort"])
            for p in cands:
                p["community"], p["site"] = "r/%s" % r["sub"], "reddit"
                p["posted"] = H._ago(p.get("posted") or "")
            ref = True
    else:
        # every other site a program can read without an account: 4chan, Hacker News, Bluesky, Mastodon, one post on X
        from paperdaemon.pipeline.charts import social
        sort = sort if sort in ("hot", "top", "new", "rising") else "hot"
        cands, why = social.fetch(src, sort, n + (4 if pictures else 0))
        if cands is None:
            return ("posts need source: 'reddit', 'r/<sub>', '4chan/<board>', 'hn', 'bsky', 'bsky/<handle>', "
                    "'mastodon/<server>' or 'x/<post link>' -- %s" % why)
        label = (cands[0].get("community") if cands else src) or src
        if not srcl.startswith("x/"):
            label = "%s, %s" % (label, sort)     # one post by its link has no "hot"
    out = []
    for p in cands:
        if len(out) >= n:
            break
        key = p.get("url") or p.get("title")
        if key in used or (pictures and not p.get("image")):
            continue
        link = p.get("link") or ""
        dom = re.sub(r"^https?://(www\.)?", "", link).split("/")[0] if link else ""
        post = {"community": p.get("community", ""), "author": (p.get("author") or "").lstrip("/"),
                "posted": p.get("posted", ""), "title": p.get("title", ""), "text": p.get("text") or "",
                "link": dom if dom and not re.search(r"reddit\.com|redd\.it", dom) else "",
                "site": p.get("site", ""), "score": p.get("score"), "comments": p.get("comments"),
                "score_label": p.get("score_label") or "votes", "comments_label": p.get("comments_label") or "comments",
                "top": list(p.get("top") or []), "_url": p.get("url") or ""}
        if p.get("image") and not p.get("nsfw"):     # a NSFW post's picture stays off the card
            got = H._data_image(p["image"])
            if not got and pictures:
                continue                     # its picture will not download: the next picture post
            post["image"] = dict(got, src=p["image"]) if got else None
        used[key] = place
        out.append(post)
    if not out:
        return "%s has no %s right now" % (label, "picture posts" if pictures else "posts")
    for p in out:
        url_ = p.pop("_url", "")
        if not (ref and url_):
            continue
        from paperdaemon.pipeline.charts import reddit as rm_reddit
        if not p["top"]:
            p["top"] = [dict(c) for c in rm_reddit.comments(url_, 2)]    # its own comments feed, paced
        # THE NUMBERS the feeds leave out -- upvotes, comment count, each comment's upvotes -- from
        # Reddit's own embed cards (rm_reddit.numbers). Their host is paced apart from the feeds', so
        # they are fetched inside the wait for the next post's comments.
        if p.get("score") is None:
            got = rm_reddit.numbers(url_)
            p["score"], p["comments"] = got["score"], got["comments"]
        for c in p["top"]:
            cu = c.pop("url", "")
            if c.get("score") is None and cu:
                c["score"] = rm_reddit.numbers(cu)["score"]
    spec["posts"] = out
    spec.setdefault("title", label)
    H.log("  %d post(s) clipped from %s%s%s" % (len(out), label,
                                             "; %d with comments" % sum(1 for p in out if p["top"]) if out else "",
                                             "; votes on %d" % sum(1 for p in out if p.get("score") is not None)
                                             if ref else ""))
    return None


