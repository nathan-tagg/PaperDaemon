r"""The job ledger: which tagged pages exist, what was asked, and what was done about each.

The daemon scans PaperDaemon's mirror of the library for tagged pages and records every one here; the
host claims a page, works it, and marks it done or skipped; the screens read the jobs back. The ledger is
<state>/rm-ledger.json: {"version": 1, "entries": {"<doc8>/<page8>": {...}}}, an entry naming its notebook
(`doc`, as first seen), `doc_id`, `page_id`, `page`, `status` (pending, working, done or skipped), `note`,
and the times it was first seen, claimed and completed.

On each scan a tagged page is classified:

  NEW       tag never seen before
  REOPENED  page content changed since it was completed -- the user edited it again
  RETAGGED  content identical, but the tag was removed and re-added: the user asks for another look
  PENDING   seen before but never completed
  DONE      completed and the page is unchanged since
  WAITING   tag present but the page has no content yet (the tag syncs before the ink)
  BASELINE  recorded as it is, never dispatched: a page already tagged at the start, or one of a notebook that
            would start more than NOTEBOOK_CAP jobs at once
  CLAIMED   another worker is on it right now

Tags inherit downward: a tag on a folder watches every page of every notebook in it, a tag on a notebook
every page in it, a tag on a page that page; the most specific tag reaching a page wins. After the start every
new or changed page is a job, except all of a notebook's at once when there are more than NOTEBOOK_CAP.

A worker claims a page before working it and heartbeats while it works; a claim older than CLAIM_TTL is
treated as dead, so a crashed worker cannot block the queue.
"""
import hashlib
import json
import os
import re
import time

from paperdaemon import paths
from paperdaemon.remarkable.sync import MIRROR as RM

LEDGER = os.path.join(paths.state_dir(), "rm-ledger.json")
# The tags that send a page to PaperDaemon: every lineup's tags (Lineup > Tagging), all live at once; the
# engine passes them in RM_TRIGGERS (a JSON list). A tag belongs to one lineup only, and that lineup works the
# page. TRIGGER is the first of them, for code that has no job's own tag to hand.
def _triggers():
    try:
        got = json.loads(os.environ.get("RM_TRIGGERS") or "null")
    except ValueError:
        got = None
    if not isinstance(got, list):
        got = [os.environ.get("RM_TRIGGER", "paperdaemon")]
    out = []
    for g in got:
        g = str(g or "").strip().lower()
        if g and g not in out:
            out.append(g)
    return out


TRIGGERS = _triggers()


def _trigger_lineups():
    """Each watched tag's lineup ({tag: lineup name}), from RM_TRIGGER_LINEUPS; {} when not given (a pipeline run by
    hand), and then no page is judged to be tagged for two lineups."""
    try:
        got = json.loads(os.environ.get("RM_TRIGGER_LINEUPS") or "null")
    except ValueError:
        got = None
    return dict((str(k).strip().lower(), str(v)) for k, v in got.items()) if isinstance(got, dict) else {}


LINEUP_OF = _trigger_lineups()
# The daemon's note on a page whose path carries tags of more than one lineup (the user's own words, as he wrote
# them); the daemon's signature -- a dash, its devil head and "Daemon" -- follows it.
TAGS_ACROSS_LINEUPS = "This page has tags across several lineups in its path. skipping it."
TRIGGER = TRIGGERS[0] if TRIGGERS else "paperdaemon"


def use_trigger(tag):
    """The current job's own watched tag becomes TRIGGER, so a page the job adds (a game's next page) is tagged
    for the same lineup."""
    global TRIGGER
    trig = trigger_of(tag)
    if trig:
        TRIGGER = trig
# The decompose inbox (Settings > Decompose inbox, "Folder/Notebook"): where Decompose sends pictures, never a
# request, whatever it is tagged with.
INBOX = str(os.environ.get("RM_INBOX") or "").strip()
# The OFF switch, and it is a real tag on the device rather than a setting in a file: put "ignore"
# on a folder, a notebook or a single page and nothing there is ever dispatched, whatever else it
# is tagged with. It exists because a notebook can be INSIDE the watched folder and still not be a
# request -- the studio's own outbox is the case that forced it: every picture sent to the tablet
# came back as a job, the daemon answering the studio's homework.
#
# IT IS NOT PRIVACY, and the name is chosen to avoid implying otherwise. The notebook is still
# pulled into the mirror, still opened, still parsed; "ignore" only means no job is dispatched
# from it. Nothing here hides anything from anyone.
#
# It deliberately does not start with the trigger word. "paperdaemon:off" would parse as a directive
# whose instruction is "off" and get dispatched -- the exact thing it is meant to prevent.
#
# TWO TAGS ARE SHARED BY EVERY LINEUP (named in Settings, "ignore" and "sprompt" unless renamed), matched
# without regard to case, and no lineup may watch for either:
#   "ignore"   at whatever level it is written -- a folder, a notebook or a page -- nothing there is
#              ever dispatched, whatever else is tagged
#   "sprompt"  ONLY as a page tag: that page is its notebook's standing instructions, read for every job
#              in the notebook whatever other tags it carries (the host's notebook_prompt), and never a job
#              itself. On a notebook or a folder it means nothing.
from paperdaemon.settings import IGNORE_TAG, SPROMPT_TAG  # noqa: E402
# their names as Settings gives them (the engine passes them in)
IGNORE_TAG = (os.environ.get("RM_IGNORE_TAG") or IGNORE_TAG).strip().lower()
SPROMPT_TAG = (os.environ.get("RM_SPROMPT_TAG") or SPROMPT_TAG).strip().lower()
MUTE = IGNORE_TAG
CLAIM_TTL = int(os.environ.get("RM_CLAIM_TTL", "900"))

# THE USER'S RULES FOR WHAT BECOMES A JOB:
# - THE START is the first look at a complete mirror (the daemon waits for one): every page tagged then is
#   recorded as it is, and none is a job.
# - From then on, every page the mirror shows NEW or CHANGED is a job -- whether PaperDaemon was running when the
#   change was made or not. A tag's age decides nothing: a new page in a notebook tagged long ago is a new page.
# - A NOTEBOOK THAT WOULD START MORE THAN NOTEBOOK_CAP JOBS AT ONCE starts none: a notebook created, uploaded or
#   moved into a tagged folder arrives whole, and its pages are not a list of requests. All of them are recorded
#   as they are; an edit brings a page back.
# - CHANGED PAGES GO BEFORE NEW ONES when the daemon hands the next job over (`why` on the entry).
NOTEBOOK_CAP = int(os.environ.get("RM_NOTEBOOK_CAP", "10"))


# ------------------------------------------------------------------ ledger
# THE LEDGER IS READ WHILE IT IS WRITTEN. The daemon polls it every second, the host and the benches
# read it, and each writer swaps a new copy in with os.replace. Windows refuses that rename while
# ANY process has the file open -- whatever share mode the reader asked for (tested: FILE_SHARE_DELETE
# does not help MoveFileEx) -- and Defender opens every file just written, the tmp copy included.
# So a read at the wrong millisecond crashed the host's save at the END of a job ("Access is
# denied: rm-ledger.json.tmp -> rm-ledger.json"), losing the to-do list on the page and its record,
# reported as CRASHED. A reader holds the file for the few milliseconds json.load takes, so the
# rename waits for it to let go; every reader goes through load().
# ONE WRITER AT A TIME. The daemon and the host each read the ledger, change an entry and write the
# whole file back -- so each could write back a copy read before the other's change. The daemon's
# cycle did exactly that to a job that finished in under a second: the host's "done"
# landed between the daemon's read and its write, the write put the old entry back, and the daemon
# waited 25 minutes for a "done" that had been and gone. Every read-change-write now
# holds this lock (the OS drops it if the process dies); re-entrant within a process.
import threading as _threading
_LOCK_T = _threading.RLock()
_DEPTH = [0, None]


class locked(object):
    """`with locked(): led = load(); ...; save(led)` -- nobody else writes in between."""

    def __enter__(self):
        _LOCK_T.acquire()
        if _DEPTH[0] == 0:
            f = open(LEDGER + ".lock", "a+b")
            if os.name == "nt":
                import msvcrt
                while True:
                    try:
                        f.seek(0)
                        msvcrt.locking(f.fileno(), msvcrt.LK_NBLCK, 1)
                        break
                    except OSError:
                        time.sleep(0.02)
            else:
                import fcntl
                fcntl.flock(f.fileno(), fcntl.LOCK_EX)
            _DEPTH[1] = f
        _DEPTH[0] += 1
        return self

    def __exit__(self, *exc):
        _DEPTH[0] -= 1
        if _DEPTH[0] == 0 and _DEPTH[1] is not None:
            f, _DEPTH[1] = _DEPTH[1], None
            try:
                if os.name == "nt":
                    import msvcrt
                    f.seek(0)
                    msvcrt.locking(f.fileno(), msvcrt.LK_UNLCK, 1)
            except OSError:
                pass
            f.close()
        _LOCK_T.release()
        return False


def _under_lock(fn):
    """A read-change-write of the ledger, whole, under `locked`."""
    def wrapped(*a, **k):
        with locked():
            return fn(*a, **k)
    wrapped.__name__, wrapped.__doc__ = fn.__name__, fn.__doc__
    return wrapped


def replace(tmp, dest):
    """os.replace that waits out another process's moment with either file (up to 2 s)."""
    for i in range(40):
        try:
            return os.replace(tmp, dest)
        except PermissionError:
            if i == 39:
                raise
            time.sleep(0.05)


def load():
    for i in range(40):
        if not os.path.exists(LEDGER):
            return {"version": 1, "entries": {}}
        try:
            with open(LEDGER, encoding="utf-8") as f:
                return json.load(f)
        except (PermissionError, FileNotFoundError):
            # opened in the instant a writer's rename was replacing it
            if i == 39:
                raise
            time.sleep(0.05)


def save(led):
    # one tmp per process: the daemon and the host both save, and a shared "rm-ledger.json.tmp"
    # let one of them rename the other's half-written copy into place
    tmp = "%s.%d.tmp" % (LEDGER, os.getpid())
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(led, f, indent=2, sort_keys=True)
    replace(tmp, LEDGER)


# ------------------------------------------------------------------ scanning
def meta(doc):
    try:
        with open(os.path.join(RM, doc + ".metadata"), encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}


def content(doc):
    try:
        with open(os.path.join(RM, doc + ".content"), encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}


def live_pages(c):
    from paperdaemon.remarkable.sync import live_pages as live
    return live(c)


def page_state(doc, pid):
    """Fingerprint of a page's current content, so later edits are detectable.

    `sha` is a CONTENT digest, not the file's bytes. The desktop app
    re-serializes whichever page a document was last left on whenever that
    document is opened and closed -- and the sync step does exactly that, on the
    first library tile. Fingerprinting raw bytes therefore made every sync
    re-open any directive living on that page, forever, with nothing actually
    changed.

    `raw` is kept so a legacy ledger entry (which stored the raw sha) still
    matches on the first scan after this change instead of re-opening everything.
    """
    path = os.path.join(RM, doc, (pid or "") + ".rm")
    if not pid or not os.path.exists(path):
        return {"exists": False, "size": 0, "sha": None, "raw": None,
                "empty": True}
    data = open(path, "rb").read()
    raw = hashlib.sha256(data).hexdigest()[:16]
    return {"exists": True, "size": len(data),
            "sha": _content_sha(path, data, raw), "raw": raw,
            "empty": _is_empty(path, data)}


_CONTENT_CACHE = {}        # path -> ((mtime_ns, size), content_sha)


def _content_sha(path, data, raw):
    """Digest of what is ON the page: strokes and typed text, not file layout.

    Parsing every tagged page at 1 Hz would be wasteful, so this is cached on
    (mtime_ns, size) exactly like `_is_empty` -- it only re-parses when the file
    genuinely changes on disk. If parsing fails for any reason it falls back to
    the raw sha, which is the old behavior: a spurious re-open, never a missed
    one.
    """
    try:
        st = os.stat(path)
        key = (st.st_mtime_ns, st.st_size)
    except OSError:
        key = None
    hit = _CONTENT_CACHE.get(path)
    if key is not None and hit is not None and hit[0] == key:
        return hit[1]
    try:
        import io as _io
        from rmscene import read_blocks
        from rmscene import scene_stream as ss
        from rmscene.scene_items import Line
        h = hashlib.sha256()
        try:
            from paperdaemon.pipeline.page import images as _IM
            _dig = _IM.digest(data)
            if _dig:                                     # ONLY when a picture is there: every
                h.update(b"I" + _dig)                    # other page must keep its old sha, or the
        except Exception:                                # whole ledger re-opens (it did, once)
            pass
        for b in read_blocks(_io.BytesIO(data)):
            if isinstance(b, ss.SceneLineItemBlock):
                v = getattr(b.item, "value", None)
                if not isinstance(v, Line):
                    continue          # erased stroke; carries no content
                pts = v.points
                h.update(("L%s|%s|%s|%d|" % (
                    getattr(v.tool, "value", v.tool),
                    getattr(v.color, "value", v.color),
                    v.color_rgba, len(pts))).encode())
                # endpoints only: enough to catch an edit, cheap on 1000-stroke
                # pages, and immune to float noise from a re-serialize
                for p in (pts[0], pts[-1]) if pts else ():
                    h.update(("%.1f,%.1f;" % (p.x, p.y)).encode())
            elif isinstance(b, ss.RootTextBlock):
                try:
                    txt = "".join(str(i.value)
                                  for i in b.value.items.sequence_items()
                                  if isinstance(i.value, str))
                except Exception:
                    txt = ""
                h.update(b"T" + txt.encode("utf-8", "replace"))
        sha = h.hexdigest()[:16]
    except Exception:
        sha = raw
    if key is not None:
        _CONTENT_CACHE[path] = (key, sha)
    return sha


_EMPTY_CACHE = {}          # path -> ((mtime_ns, size), bool)
_BIG = 4000                # above this a page obviously has content


def _is_empty(path, data):
    """True only if the page really has nothing on it.

    This used to be a size threshold (`size <= 800`), which cannot tell an empty
    page from a SHORT TYPED REQUEST: a one-line typed request is a few hundred
    bytes, and sat in WAITING forever because of it.
    Now: no strokes AND no non-whitespace text. Only small files are parsed, so
    the 1 Hz poll stays cheap.
    """
    if len(data) > _BIG:
        return False
    try:
        from paperdaemon.pipeline.page import images as _IM
        if _IM.has_images(data):          # a picture placed with the app IS content
            return False
    except Exception:
        pass
    try:
        st = os.stat(path)
        key = (st.st_mtime_ns, st.st_size)
    except OSError:
        key = None
    hit = _EMPTY_CACHE.get(path)
    if key is not None and hit is not None and hit[0] == key:
        return hit[1]
    empty = True
    try:
        import io as _io
        from rmscene import read_blocks
        from rmscene import scene_stream as ss
        from rmscene.scene_items import Line
        for b in read_blocks(_io.BytesIO(data)):
            if isinstance(b, ss.SceneLineItemBlock) and isinstance(
                    getattr(b.item, "value", None), Line):
                empty = False
                break
            if isinstance(b, ss.RootTextBlock):
                try:
                    txt = "".join(str(i.value)
                                  for i in b.value.items.sequence_items()
                                  if isinstance(i.value, str))
                except Exception:
                    txt = ""
                if txt.strip():
                    empty = False
                    break
    except Exception:
        empty = len(data) <= 800          # fall back to the old guess
    if key is not None:
        _EMPTY_CACHE[path] = (key, empty)
    return empty


def trigger_of(name):
    """The watched tag a tag name starts with ('PaperDaemon: highlight' -> 'paperdaemon'), or None. The longest
    match wins, so a lineup's "qwen fast" is not read as "qwen" with the words "fast"."""
    s = str(name or "").strip().lower()
    for trig in sorted(TRIGGERS, key=len, reverse=True):
        if s == trig or (s.startswith(trig) and s[len(trig):][:1] in (":", ",", "-", "–", " ")):
            return trig
    return None


def parse_directive(name):
    """'PaperDaemon: highlight the key bits' -> 'highlight the key bits' (or ''); None when no watched tag."""
    trig = trigger_of(name)
    if trig is None:
        return None
    rest = name.strip()[len(trig):].lstrip()
    while rest[:1] in (":", ",", "-", "–"):
        rest = rest[1:].lstrip()
    return rest


# Parsing every .content file on every poll costs tens of milliseconds on a large library.
# At 1 Hz that is pure waste, since almost nothing changes between polls. Cache
# the extracted directives per file, keyed by (mtime_ns, size), and re-parse only
# what actually changed. Steady state becomes ~156 stat() calls.
_DOC_CACHE = {}          # doc_id -> ((mtime_ns, size), extract)


# Folder -> notebook -> page. A tag INHERITS down: tagging a notebook watches
# every page in it, and tagging a folder watches every page of every notebook in
# it. That beats fingerprinting a notebook as one blob: it
# reuses the page machinery as-is, so "which page changed" is still answered by
# classify(), and every page keeps its own hash, claim and note.
#
# Inheritance is resolved UPWARD, from each document to its ancestors, not
# downward from the folder. Downward looked simpler and was wrong twice over:
# the folder's own uuid ended up standing in for the child notebook's when the
# page was fingerprinted (every inherited page read as "does not exist"), and a
# folder's .content does not change when a child gains a page, so the scan cache
# would never have noticed the new page at all.
_META_CACHE = {}           # uuid -> (stamp, metadata)
_CONT_CACHE = {}           # uuid -> (stamp, content)


def _cached(uuid, ext, cache, read):
    path = os.path.join(RM, uuid + ext)
    try:
        st = os.stat(path)
        key = (st.st_mtime_ns, st.st_size)
    except OSError:
        return None, {}
    hit = cache.get(uuid)
    if hit is not None and hit[0] == key:
        return key, hit[1]
    val = read(uuid)
    cache[uuid] = (key, val)
    return key, val


def _has_mute(c):
    """Is this document or folder tagged to be left alone?"""
    for t in (c.get("tags") or []):
        nm = t.get("name") if isinstance(t, dict) else t
        if str(nm).strip().lower() == MUTE:
            return True
    return False


def _muted_pages(c):
    """Page ids carrying the mute tag, so one page of a watched notebook can be left alone while
    its siblings still dispatch."""
    out = set()
    for t in (c.get("pageTags") or []):
        if str(t.get("name", "")).strip().lower() == MUTE and t.get("pageId"):
            out.add(t["pageId"])
    return out


def is_inbox(doc, m):
    """True for the decompose inbox notebook: its name and its folders match the setting."""
    if not INBOX or m.get("type") == "CollectionType":
        return False
    parts = [p.strip() for p in INBOX.replace("\\", "/").split("/") if p.strip()]
    if not parts or m.get("visibleName") != parts[-1]:
        return False
    parent = m.get("parent") or ""
    for f in reversed(parts[:-1]):
        if not parent or parent == "trash":
            return False
        _, pm = _cached(parent, ".metadata", _META_CACHE, meta)
        if pm.get("visibleName") != f:
            return False
        parent = pm.get("parent") or ""
    return not parent


def muted(doc, m):
    """True if this document, or any folder above it, carries the mute tag.

    Checked BEFORE anything is extracted, so a muted notebook costs one cached .content read and
    produces no directives at all -- not even baselined ones.
    """
    _, c = _cached(doc, ".content", _CONT_CACHE, content)
    if _has_mute(c) or is_inbox(doc, m):
        return True
    parent, depth = m.get("parent"), 0
    while parent and parent != "trash" and depth < 8:
        _, pm = _cached(parent, ".metadata", _META_CACHE, meta)
        _, pc = _cached(parent, ".content", _CONT_CACHE, content)
        if _has_mute(pc):
            return True
        parent = pm.get("parent")
        depth += 1
    return False


def inherited_tag(m):
    """The nearest tagged ancestor folder, and a stamp of the whole chain.

    The stamp goes into the scan cache key, so a tag added to or removed from
    ANY ancestor re-extracts this document's directives on the next poll.
    """
    found, stamps, parent, depth = None, [], m.get("parent"), 0
    while parent and parent != "trash" and depth < 8:
        k1, pm = _cached(parent, ".metadata", _META_CACHE, meta)
        k2, pc = _cached(parent, ".content", _CONT_CACHE, content)
        stamps.append((parent, k1, k2))
        if found is None:
            for t in (pc.get("tags") or []):
                nm = t.get("name") if isinstance(t, dict) else t
                instr = parse_directive(str(nm))
                if instr is not None:
                    found = (str(nm), instr,
                             t.get("timestamp") if isinstance(t, dict) else None)
                    break
        parent = pm.get("parent")
        depth += 1
    return found, tuple(stamps)


def _pages_of(doc, m, pages, tag, instr, tag_ts, via, rank):
    """One directive per live page -- the inherited form."""
    return [{
        "key": "%s/%s" % (doc[:8], (p.get("id") or "doc")[:8]),
        "doc_id": doc, "doc": m.get("visibleName", doc),
        "scope": "page", "page_id": p.get("id"), "page": i + 1,
        "tag": tag, "instruction": instr, "tag_ts": tag_ts,
        "inherited": via,              # None, "document" or "collection"
        "siblings": len(pages), "rank": rank, "modifed": p.get("modifed"),
    } for i, p in enumerate(pages)]


def _extract(doc, m, c, inh=None):
    """Directives this document is subject to, one per PAGE.

    A page can be reached three ways at once. The most specific wins: a tag put
    on THE PAGE beats one on the notebook, which beats one on a folder above it.
    """
    if m.get("type") == "CollectionType":
        return []                      # a folder acts on its children, not itself
    pages = live_pages(c)
    index = {p.get("id"): i + 1 for i, p in enumerate(pages)}
    items = []
    for t in (c.get("pageTags") or []):
        instr = parse_directive(str(t.get("name", "")))
        if instr is None:
            continue
        pid = t.get("pageId")
        items.append({
            "key": "%s/%s" % (doc[:8], (pid or "doc")[:8]),
            "doc_id": doc, "doc": m.get("visibleName", doc),
            "scope": "page", "page_id": pid, "page": index.get(pid),
            "tag": str(t.get("name", "")), "instruction": instr,
            "tag_ts": t.get("timestamp"), "inherited": None,
            "siblings": 1, "rank": 0,
            "modifed": (pages[index[pid] - 1].get("modifed")
                        if index.get(pid) else None),
        })
    for t in (c.get("tags") or []):
        nm = t.get("name") if isinstance(t, dict) else t
        instr = parse_directive(str(nm))
        if instr is None:
            continue
        ts = t.get("timestamp") if isinstance(t, dict) else None
        items.extend(_pages_of(doc, m, pages, str(nm), instr, ts, "document", 1))
        break
    if inh:
        items.extend(_pages_of(doc, m, pages, inh[0], inh[1], inh[2],
                               "collection", 2))
    best, lineups = {}, {}
    for it in items:
        k = it["key"]
        if k not in best or it["rank"] < best[k]["rank"]:
            best[k] = it
        lu = LINEUP_OF.get(trigger_of(it["tag"]) or "")
        if lu:
            lineups.setdefault(k, set()).add(lu)
    # TAGS OF MORE THAN ONE LINEUP IN A PAGE'S PATH (on the page, its notebook or a folder above): no lineup works it;
    # the daemon says so on the page (TAGS_ACROSS_LINEUPS). Two tags of one lineup are fine: the most specific wins.
    for k, lus in lineups.items():
        if len(lus) > 1:
            best[k] = dict(best[k], lineups=sorted(lus))
    # MUTE BEATS EVERYTHING, at whatever level it was set. Applied last, after the most-specific
    # tag has already won, so "tagged for the model AND tagged ignore" resolves to ignore rather
    # than to whichever tag happened to be more specific.
    skip = set(_muted_pages(c))
    # AN SPROMPT PAGE IS NEVER WORK. It holds the notebook's standing instructions for the model
    # (the host's notebook_prompt reads it); under an inherited tag it was dispatched as a job of
    # its own and the model was asked to act on its own instructions.
    skip |= set(t.get("pageId") for t in (c.get("pageTags") or [])
                if str(t.get("name", "")).strip().lower() == SPROMPT_TAG)
    return [it for it in best.values() if it.get("page_id") not in skip]


def scan():
    out = []
    for f in os.listdir(RM):
        if not f.endswith(".content"):
            continue
        doc = f[:-8]
        path = os.path.join(RM, f)
        try:
            st = os.stat(path)
        except OSError:
            continue
        _, m = _cached(doc, ".metadata", _META_CACHE, meta)
        if m.get("parent") == "trash" or m.get("deleted"):
            continue
        if muted(doc, m):
            continue
        inh, astamp = inherited_tag(m)
        stamp_ = (st.st_mtime_ns, st.st_size, astamp, inh)
        hit = _DOC_CACHE.get(doc)
        if hit is not None and hit[0] == stamp_:
            items = hit[1]
        else:
            items = _extract(doc, m, content(doc), inh)
            _DOC_CACHE[doc] = (stamp_, items)
        # page hashes are always fresh -- the .rm changes without .content changing
        for it in items:
            e = dict(it)
            # A DOCUMENT-level tag has no page to fingerprint, so it gets a
            # synthetic state. It must carry every key page_state() returns --
            # omitting "raw" here put the daemon into a 1 Hz KeyError loop the
            # moment a whole document was tagged.
            e["state"] = (page_state(it["doc_id"], it["page_id"])
                          if it["scope"] == "page"
                          else {"exists": True, "size": 0, "sha": None,
                                "raw": None, "empty": False})
            out.append(e)
    # A page can carry the trigger tag more than once, which produced duplicate
    # identical directives. One job per key.
    seen, uniq = set(), []
    for e in out:
        if e["key"] in seen:
            continue
        seen.add(e["key"])
        uniq.append(e)
    return uniq


BEFORE_WATCHING = "tagged before PaperDaemon was watching: not a job; an edit or a new tag brings it back"


TOO_MANY = ("more than %d pages of this notebook were new or changed at once, so none is a job (a notebook that "
            "arrives whole is not a list of requests); an edit brings a page back" % NOTEBOOK_CAP)


def classify(found, led):
    now = int(time.time())
    entries = led["entries"]
    # THE START: a new ledger's first scan files every page that is already tagged as seen, never a backlog. From
    # then on a page met for the first time is a new page, whatever the age of the tag that reaches it.
    first = "watching_since" not in led and not entries
    led.setdefault("watching_since", now)
    queue = []
    for f in found:
        e = entries.get(f["key"])
        st = f["state"]
        if e is None:
            baseline = first
            entries[f["key"]] = {
                "doc": f["doc"], "doc_id": f["doc_id"], "page_id": f["page_id"],
                "page": f["page"], "tag": f["tag"], "instruction": f["instruction"],
                "tag_ts": f.get("tag_ts"), "inherited": f.get("inherited"),
                "first_seen": now, "last_seen": now,
                "status": "skipped" if baseline else "pending", "why": None if baseline else "new",
                "handled_sha": st.get("sha") if baseline else None,
                "handled_tag_ts": f.get("tag_ts") if baseline else None,
                "note": BEFORE_WATCHING if baseline else None,
                "completed_at": now if baseline else None,
            }
            if baseline:
                status = "BASELINE"
            else:
                status = "WAITING" if st.get("empty") else "NEW"
        else:
            e["last_seen"] = now
            e["page"] = f["page"]
            e["inherited"] = f.get("inherited")
            e["tag_ts"] = f.get("tag_ts")
            # Migration: an entry settled before retag detection existed has no
            # baseline. Adopt the CURRENT stamp rather than treating "unknown"
            # as "changed" -- otherwise every settled directive re-opens once,
            # for nothing.
            if e.get("status") in ("done", "skipped") and e.get("handled_tag_ts") is None:
                e["handled_tag_ts"] = f.get("tag_ts")
            if e.get("tag") != f["tag"]:
                e["tag"] = f["tag"]
                e["instruction"] = f["instruction"]
                e["tag_ts"] = f.get("tag_ts")
                e["status"] = "pending"
                e["why"] = "changed"
                e["handled_sha"] = None
            held = e.get("claim_owner")
            age = now - e.get("claim_at", 0)
            if held and age < CLAIM_TTL and e["status"] == "working":
                f["status"] = "CLAIMED"
                f["claim_owner"] = held
                queue.append(f)
                continue
            if held and age >= CLAIM_TTL:
                # the worker died holding it; make it available again
                e.pop("claim_owner", None)
                e.pop("claim_at", None)
                if e["status"] == "working":
                    e["status"] = "pending"
            if e.get("tag_conflict") and not f.get("lineups") and e["status"] == "skipped":
                # SKIPPED FOR TAGS OF TWO LINEUPS, and now one lineup's alone: the page is that lineup's to work, though
                # nothing on it changed
                e.pop("tag_conflict", None)
                e["status"] = "pending"
                e["why"] = "changed"
            if e["status"] in ("done", "skipped"):
                # Both settled states re-open on a content change. Skipped must
                # behave like done here: a page skipped for "no request yet" has
                # to come back when a real request is finally written on it,
                # otherwise it is ignored forever.
                # `handled_sha` on entries written before content-fingerprinting
                # holds a RAW sha, so accept that too -- otherwise every settled
                # directive re-opens once on the upgrade.
                # A TAG CAN BE REMOVED AND PUT BACK. Re-tagging a page
                # is the user asking for another LOOK, and the content may be
                # byte-identical -- so a content-only test reports DONE and the
                # page is never examined again. reMarkable stamps every tag with
                # a timestamp and a re-added tag gets a NEW one, which is what
                # makes this detectable at all.
                retagged = (f.get("tag_ts") is not None
                            and e.get("handled_tag_ts") is not None
                            and f["tag_ts"] != e["handled_tag_ts"])
                unchanged = (e.get("handled_sha") in (st.get("sha"), st.get("raw"))
                             or e.get("handled_raw") == st.get("raw"))
                if unchanged and not retagged:
                    status = "DONE" if e["status"] == "done" else "SKIPPED"
                elif st.get("empty"):
                    # CHANGED TO NOTHING: the page was cleared. There is nothing to answer until
                    # something is written on it, so it waits like a new page -- dispatched, it
                    # cost a job that could only say "the page is blank"
                    status = "WAITING"
                    e["status"] = "pending"
                else:
                    status = "RETAGGED" if (retagged and unchanged) else "REOPENED"
                    e["status"] = "pending"
                    e["why"] = "changed"
            else:
                status = "WAITING" if st.get("empty") else "PENDING"
        f["status"] = status
        f["why"] = entries[f["key"]].get("why")
        queue.append(f)
    # A NOTEBOOK THAT WOULD START MORE THAN NOTEBOOK_CAP JOBS AT ONCE starts none (see NOTEBOOK_CAP): every page of it
    # this scan made a job is recorded as it is
    burst = {}
    for f in queue:
        if f["status"] in ("NEW", "REOPENED", "RETAGGED"):
            burst.setdefault(f["doc_id"], []).append(f)
    for doc, fs in burst.items():
        if len(fs) <= NOTEBOOK_CAP:
            continue
        for f in fs:
            e = entries[f["key"]]
            e.update(status="skipped", why=None, note=TOO_MANY, completed_at=now, handled_sha=f["state"].get("sha"),
                     handled_raw=f["state"].get("raw"), handled_tag_ts=f.get("tag_ts"))
            f["status"], f["why"], f["too_many"] = "BASELINE", None, True
    # A CLAIM ON A PAGE THE SCAN NO LONGER FINDS (untagged, deleted, moved) expires too: checked only for the pages
    # found, a job that died holding one stayed "working" for good
    seen = set(f["key"] for f in found)
    gone = []
    for k, e in entries.items():
        if k not in seen and e.get("status") == "working" and now - e.get("claim_at", 0) >= CLAIM_TTL:
            e.pop("claim_owner", None)
            e.pop("claim_at", None)
            e["status"] = "pending"
        # A JOB WHOSE PAGE WAS DELETED is no job: nothing can be done on a page that is not there, and left waiting
        # it showed in Jobs as about to run. One being worked is released first (above) and goes on a later scan.
        if k not in seen and e.get("status") == "pending" and _page_deleted(e):
            gone.append(k)
    for k in gone:
        del entries[k]
    return queue


def _page_deleted(e):
    """True when the entry's notebook is in a complete Mirror and no longer has its page. False whenever that cannot
    be shown (a pull still filling the Mirror, an unreadable notebook): a job is never dropped on a guess. A notebook
    that is gone altogether is prune_notepads' to forget."""
    from paperdaemon.remarkable import sync as _sync
    doc, pid = e.get("doc_id"), e.get("page_id")
    if not (doc and pid) or not _sync.mirrored():
        return False
    try:
        with open(os.path.join(RM, doc + ".content"), encoding="utf-8") as f:
            live = _sync.live_pages(json.load(f))
    except (OSError, ValueError):
        return False
    return pid not in set(p.get("id") for p in live)


@_under_lock
def claim(key, owner):
    """Take a directive. Returns False if someone else holds a live claim."""
    led = load()
    e = led["entries"].get(key)
    if e is None:
        print("no ledger entry %r -- run a scan first" % key)
        return False
    held = e.get("claim_owner")
    fresh = (time.time() - e.get("claim_at", 0)) < CLAIM_TTL
    if held and held != owner and fresh:
        print("%s is already claimed by %s (%ds ago)"
              % (key, held, int(time.time() - e.get("claim_at", 0))))
        return False
    e["claim_owner"] = owner
    e["claim_at"] = int(time.time())
    e["started_at"] = e["claim_at"]          # this job's start: claim_at is refreshed while it runs, and dropped at the end
    e["status"] = "working"
    save(led)
    print("%s claimed by %s" % (key, owner))
    return True


@_under_lock
def release_dead_claims(before):
    """Release every claim taken before `before` (when the host now running started): its host is gone, and the
    job with it. The daemon remembers what it handed over only while it runs, so after a restart of both (an
    update) this is how a job that was in flight is handed over again rather than shown "working" for ever.
    -> the keys released."""
    led = load()
    out = []
    for k, e in led["entries"].items():
        if e.get("status") == "working" and e.get("claim_at", 0) < before:
            e.pop("claim_owner", None)
            e.pop("claim_at", None)
            e["status"] = "pending"
            out.append(k)
    if out:
        save(led)
    return out


@_under_lock
def release(key, owner):
    """Give a claim back untaken -- used when a batch cannot be claimed whole."""
    led = load()
    e = led["entries"].get(key)
    if e is None or e.get("claim_owner") != owner:
        return False
    e.pop("claim_owner", None)
    e.pop("claim_at", None)
    if e.get("status") == "working":
        e["status"] = "pending"
    save(led)
    return True


@_under_lock
def touch(key, owner):
    """Refresh a claim during a long job, so it is not judged dead."""
    led = load()
    e = led["entries"].get(key)
    if e is None or e.get("claim_owner") != owner:
        return False
    e["claim_at"] = int(time.time())
    save(led)
    return True


@_under_lock
def mark(key, status, note, failed=False, tag_conflict=False):
    """Record a job's outcome. `failed`: it did not do what was asked (the window shows it as failed, whatever the
    status); a skip because there was nothing to do is not a failure. `tag_conflict`: skipped for tags of two lineups,
    so the page is worked once its tags are one lineup's again (classify)."""
    led = load()
    e = led["entries"].get(key)
    if e is None:
        print("no ledger entry %r -- run a scan first" % key)
        return 1
    st = page_state(e["doc_id"], e.get("page_id"))
    e["status"] = status
    e["note"] = note
    e["failed"] = bool(failed)
    e["completed_at"] = int(time.time())
    e["handled_sha"] = st["sha"]
    e["handled_raw"] = st.get("raw")
    e["handled_tag_ts"] = e.get("tag_ts")
    if tag_conflict:
        e["tag_conflict"] = True
    else:
        e.pop("tag_conflict", None)
    e.pop("claim_owner", None)
    e.pop("claim_at", None)
    save(led)
    print("%s -> %s (sha %s)" % (key, status, st["sha"]))
    return 0


def entries(state=None):
    """The ledger's entries, read from `state` (default: this process's state folder)."""
    try:
        with open(os.path.join(state or paths.state_dir(), "rm-ledger.json"), encoding="utf-8") as f:
            d = json.load(f)
        return (d or {}).get("entries") or {}
    except (OSError, ValueError):
        return {}


def notebook_name(doc, state=None, mirror=None):
    """A notebook's name: from the mirror's metadata, else as the ledger first saw it, else ""."""
    try:
        with open(os.path.join(mirror or os.environ.get("RM_MIRROR") or paths.mirror_dir(), doc + ".metadata"),
                  encoding="utf-8") as f:
            name = (json.load(f) or {}).get("visibleName")
        if name:
            return name
    except (OSError, ValueError):
        pass
    for e in entries(state).values():
        if isinstance(e, dict) and e.get("doc_id") == doc and e.get("doc"):
            return e["doc"]
    return ""


def jobs(limit=50, state=None):
    """The most recent jobs, newest first: [{key, notebook, doc_id, page, status, note, started, finished, lineup
    (the one that worked it; None before it ran), tag}]."""
    rows = []
    for key, e in entries(state).items():
        if not isinstance(e, dict):
            continue
        note = str(e.get("note") or "")
        if e.get("status") == "skipped" and (note.startswith("baselined") or note in (BEFORE_WATCHING, TOO_MANY)):
            continue                          # pages that were there before PaperDaemon looked are not jobs
        started = e.get("started_at") or e.get("claim_at") or e.get("first_seen")
        finished = e.get("completed_at") if e.get("status") in ("done", "skipped") else None
        rows.append({"key": key, "notebook": e.get("doc") or "", "doc_id": e.get("doc_id"), "page": e.get("page"),
                     "status": e.get("status"), "note": note, "failed": bool(e.get("failed")),
                     "started": started, "finished": finished,
                     "lineup": e.get("lineup") or None, "tag": e.get("tag") or ""})
    rows.sort(key=lambda r: max(float(r["finished"] or 0), float(r["started"] or 0)), reverse=True)
    return rows[:max(0, int(limit))]


# ---------------------------------------------------------------- every notepad has a notebook

def prune_notepads(dry_run=False, include_trashed=True):
    """Drop the ledger entries and page histories of notebooks the mirror no longer holds (trashed counts as
    deleted), so a notebook the user removed is not kept readable here. Run when the daemon starts."""
    import glob
    import shutil
    live_full = set()
    for f in glob.glob(os.path.join(RM, "*.metadata")):
        uid = os.path.basename(f)[:-len(".metadata")]
        if include_trashed:
            try:
                with open(f, encoding="utf-8") as fh:
                    m = json.load(fh)
            except (OSError, ValueError):
                m = {}
            if m.get("parent") == "trash" or m.get("deleted"):
                continue
        live_full.add(uid)
    live8 = {u[:8] for u in live_full}
    out = {"ledger": [], "history": [], "dry_run": dry_run}
    with locked():
        book = load()
        dead = [k for k in book.get("entries", {}) if k.split("/")[0] not in live8]
        out["ledger"] = sorted({k.split("/")[0] for k in dead})
        if dead and not dry_run:
            for k in dead:
                del book["entries"][k]
            save(book)
    out["ledger_entries"] = len(dead)
    hist = os.path.join(paths.state_dir(), "rm-history")
    if os.path.isdir(hist):
        for d in sorted(os.listdir(hist)):
            uuid = d.rsplit("-p", 1)[0]
            if uuid and uuid not in live_full:
                out["history"].append(d)
                if not dry_run:
                    shutil.rmtree(os.path.join(hist, d), ignore_errors=True)
    return out
