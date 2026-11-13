"""WORK ON ANOTHER PAGE: an elsewhere step hands its request to a page of this notebook, a new page right after this
one, or a new notebook made beside this one. The host makes the page or the notebook when it is new, tags it for the
job's lineup when no tag reaches it, and files it in the ledger as asked for -- with the request, word for word, and
the page it came from. The daemon then runs it as any job: the model there reads what it needs (read_page) and writes
on its own page, and the Daemon's note goes on that page. Nothing here writes ink.

Until 11-12 a job could only work on the page that woke it: asked to write a new version of page 2 on a new page, the
Opus lineup told the user to write the request there and tag it themselves."""
import os
import time

from paperdaemon import ledger as S
from paperdaemon.pipeline.host.job import JOB
from paperdaemon.pipeline.page import render as R
from paperdaemon.pipeline import host as H


def _source_entry():
    key = (JOB.keys or [None])[0]
    return key, (S.load()["entries"].get(key) if key else None)


def _tagged_whole(doc, tag):
    """Does the notebook itself carry `tag` (every page of it inherits it)?"""
    try:
        c = S.content(doc)
    except Exception:
        return False
    return any(str(t.get("name", "")).strip().lower() == str(tag or "").strip().lower() for t in (c.get("tags") or []))


def _folder(path, doc):
    """The folder a new notebook goes in -> its id ("" the library's top): `path` a folder's name or a path of names
    ("Work/Resumes"), each matched by name (case aside) under the one before it, or anywhere when it is a single name
    met once; a part that does not exist is made (and sent to the tablet). "/" is the top; no path, this notebook's
    folder. Raises ValueError for a single name that several folders share."""
    from paperdaemon import paths
    from paperdaemon.remarkable import local
    if path is None or not str(path).strip():
        parent = (S.meta(doc) or {}).get("parent") or ""
        return "" if parent == "trash" else parent
    parts = [p.strip() for p in str(path).strip().split("/") if p.strip()]
    folders = {}
    for f in os.listdir(S.RM):
        if f.endswith(".metadata"):
            m = S.meta(f[:-9])
            if m.get("type") == "CollectionType" and not m.get("deleted") and m.get("parent") != "trash":
                folders[f[:-9]] = (str(m.get("visibleName") or "").strip().lower(), m.get("parent") or "")
    if len(parts) == 1 and not str(path).strip().startswith("/"):
        hits = [u for u, (n, _p) in folders.items() if n == parts[0].lower()]
        if len(hits) == 1:
            return hits[0]
        if len(hits) > 1:
            raise ValueError("%d folders are named %r: give its path (\"Parent/%s\")" % (len(hits), parts[0], parts[0]))
    parent = ""
    for name in parts:
        hit = next((u for u, (n, p) in folders.items() if n == name.lower() and p == parent), None)
        if hit is None:
            hit = local.new_folder(name, parent, tablet=not paths.local_only())
            folders[hit] = (name.lower(), parent)
            H.log("  made the folder %r" % name)
        parent = hit
    return parent


def _target(step, src):
    """-> (doc, page id, page number, notebook name, why not or None): the page the work goes to, made when new."""
    from paperdaemon import paths
    from paperdaemon.remarkable import library as PG
    doc = JOB.doc
    if step.get("notebook"):
        from paperdaemon.remarkable import local
        try:
            parent = _folder(step.get("folder"), doc)
            new = local.new_notebook(step["notebook"], parent=parent, tags=(src.get("tag"),) if src.get("tag") else (),
                                     tablet=not paths.local_only())
        except ValueError as ex:                     # made here, not yet on the tablet: it goes up with the next sync
            H.log("  the new notebook: %s" % str(ex)[:160])
            return None, None, None, None, "the new notebook could not be made: %s" % str(ex)[:160]
        pid = R.live_pages(new)[0]["id"]
        return new, pid, 1, step["notebook"], None
    if step.get("page") == "new":
        live = [p["id"] for p in R.live_pages(doc)]
        af = step.get("after")
        if af == "end":
            after = live[-1]
        elif af:
            if not 1 <= int(af) <= len(live):
                return None, None, None, None, "after: this notebook has %d page%s" % (len(live), "" if len(live) == 1 else "s")
            after = live[int(af) - 1]
        else:
            after = (JOB.added_pages or [JOB.page_id])[-1]      # right after this page, behind what the job added
        pid = PG.insert_pages(doc, after, 1)[0][0]
        JOB.added_pages.append(pid)
        n = [p["id"] for p in R.live_pages(doc)].index(pid) + 1
        return doc, pid, n, None, None
    pages = R.live_pages(doc)
    n = int(step.get("page") or 0)
    if not 1 <= n <= len(pages):
        return None, None, None, None, "this notebook has %d page%s" % (len(pages), "" if len(pages) == 1 else "s")
    if n == JOB.page:
        return None, None, None, None, "that is this page: do the work here, with the steps that write on it"
    return doc, pages[n - 1]["id"], n, None, None


def run(step):
    """The elsewhere step carried out -> (ok, note)."""
    key, src = _source_entry()
    if not src:
        return False, "this run has no ledger entry to hand the work from"
    what = str(step.get("what") or "").strip()
    if not what:
        return False, "say the request for that page"
    doc, pid, n, notebook, why = _target(step, src)
    if why:
        return False, why
    tag = src.get("tag")
    if tag and not notebook and not _tagged_whole(doc, tag):
        from paperdaemon.remarkable import library as PG
        PG.tag_page(doc, pid, tag)                   # the page is the lineup's, as the asking page is
    name = notebook or src.get("doc") or (S.meta(doc) or {}).get("visibleName") or doc
    here = "%s, page %s" % (src.get("doc") or JOB.doc, JOB.page)
    now = int(time.time())
    k = "%s/%s" % (doc[:8], pid[:8])
    with S.locked():
        led = S.load()
        e = led["entries"].get(k) or {}
        e.update({f: src.get(f) for f in ("tag", "instruction", "tag_ts")})
        e.update(doc=name, doc_id=doc, page_id=pid, page=n, first_seen=e.get("first_seen") or now, last_seen=now,
                 status="pending", why="asked", handled_sha=None, handled_raw=None, completed_at=None,
                 inherited=bool(notebook) or _tagged_whole(doc, tag) or e.get("inherited"),
                 asked={"from": here, "what": what[:4000]})
        for gone in ("claim_owner", "claim_at", "failed", "retry", "retries_used", "note"):
            e.pop(gone, None)
        led["entries"][k] = e
        S.save(led)
    where = ("page 1 of the new notebook %r" % notebook if notebook else
             "page %d (a new page)" % n if step.get("page") == "new" else "page %d" % n)
    JOB.ops.append("handed to %s: %s" % (where, what[:80]))
    H.log("  handed to %s: %s" % (where, what[:160]))
    return True, "a job runs on %s with this request" % where


def asked_text(asked):
    """What the job on the page that was asked for is told: where its request came from, and the request."""
    return ("THIS PAGE'S REQUEST COMES FROM %s, which handed the work here. Carry it out ON THIS PAGE; read the pages "
            "it names with read_page. The request, word for word:\n%s" % (asked.get("from") or "another page",
                                                                          asked.get("what") or ""))
