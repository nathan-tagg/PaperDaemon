r"""The daemon: watches PaperDaemon's mirror of the library for tagged pages and queues one job per notebook.

It keeps the mirror current (the cloud's push channel, with a poll as well), reads the ledger to see what
is new or changed, writes the job into the queue folder for the host, and waits for the host to record the outcome in the ledger. A page the user changed while
its job ran is queued again once the job is recorded.

Environment (set by the engine):
  RM_INTERVAL        idle poll seconds (default 1)
  RM_MAX_ATTEMPTS    attempts per page before giving up (default 2)
  RM_DRY_RUN         1 = never queue
"""
import json
import logging
import os
from paperdaemon import paths
import sys
import time

# rmscene logs "Some data has not been read. The data may have been written
# using a newer format than this reader supports." at WARNING the first time it
# meets a block it does not fully understand -- which is most .rm v6 pages. With
# no logging configured that goes to stderr via Python's last-resort handler and
# spams the daemon console on every scan.
#
# That warning is not the daemon's business. The daemon only fingerprints pages
# to decide whether one changed; partially-understood blocks do not affect that.
# Silencing it here loses nothing the daemon needs.
logging.getLogger("rmscene").setLevel(logging.ERROR)

_STATE = paths.state_dir()                      # the ledger, queue, logs and backups live here

# CLOUD MODE. The daemon keeps its own mirror of the library, pulled straight
# from reMarkable's sync API, and pushes changes back the same way. The desktop
# app stops being a component: no cache to depend on, no GUI to drive, no focus
# to steal.
#
# There is no fallback flag. The GUI path is gone: it depended on a window
# existing, stole the keyboard from the user, broke silently when focus moved, and
# could only sync a document by pretending someone had opened it. RM_CACHE can
# still be pointed at the app's old cache if it is ever needed for forensics.
# Export the library path the SAME way rm_cloud computes it, so a spawned job inherits a
# directory that exists. This used to hard-code a folder beside this file; when the mirror moved to the
# app's own store that path stopped existing, and because this is an ENV VAR it overrode the
# correct fallback in every module the job imported.
try:
    from paperdaemon.remarkable.sync import MIRROR as _LIBRARY
    os.environ.setdefault("RM_CACHE", _LIBRARY)
except Exception:
    pass

from paperdaemon import ledger as rm_scan

INTERVAL = int(os.environ.get("RM_INTERVAL", "1"))
# How often to re-report a scan error that keeps happening.
ERROR_BACKOFF = int(os.environ.get("RM_ERROR_BACKOFF", "60"))
MAX_ATTEMPTS = int(os.environ.get("RM_MAX_ATTEMPTS", "2"))
# A job has no time limit: it is done when the host records it in the ledger. The cloud is watched
# through its push channel, and polled as well, because the channel can stay connected while delivering
# nothing.
DRY = os.environ.get("RM_DRY_RUN", "0") == "1"
LOGFILE = os.path.join(_STATE, "rm-daemon.log")
# Ceiling for the log file. Emptied on every start as well, so this only bites
# during a single very long run.
LOG_CAP = int(os.environ.get("RM_LOG_CAP", str(256 * 1024)))

SPIN = "|/-\\"


def stamp():
    return time.strftime("%H:%M:%S")


def reset_log(path):
    """Start every run with an empty log. This runs on a personal computer, not a
    server -- a log that grows forever is just disk to think about, and the only
    run that matters is the one happening now."""
    try:
        open(path, "w", encoding="utf-8").close()
    except OSError:
        pass


def cap_log(path):
    """Hard ceiling, so one long run cannot bloat the file either. Keeps the
    most recent half and drops the rest -- the tail is the part worth having."""
    try:
        if os.path.getsize(path) <= LOG_CAP:
            return
        with open(path, "rb") as f:
            f.seek(-(LOG_CAP // 2), os.SEEK_END)
            tail = f.read()
        with open(path, "wb") as f:
            f.write(b"[log truncated to the most recent %d bytes]\n"
                    % (LOG_CAP // 2))
            f.write(tail)
    except OSError:
        pass


def log(msg, to_console=True):
    line = "[%s] %s" % (stamp(), msg)
    try:
        cap_log(LOGFILE)
        with open(LOGFILE, "a", encoding="utf-8") as f:
            f.write(line + "\n")
    except OSError:
        pass
    if to_console:
        try:
            # on a console, wipe the spinner's line first; in a log file that wipe would be a blank line
            wipe = ("\r" + " " * 110 + "\r") if sys.stdout.isatty() else ""
            sys.stdout.write(wipe + line + "\n")
            sys.stdout.flush()
        except Exception:
            pass


def heartbeat(tick, note):
    """The spinner, on a console only: written to a log file it would grow it every second for nothing."""
    try:
        if not sys.stdout.isatty():
            return
        sys.stdout.write(chr(13) + "[%s] %s %-58s"
                         % (stamp(), SPIN[tick % 4], note[:58]))
        sys.stdout.flush()
    except Exception:
        pass


def _mirror_complete():
    try:
        from paperdaemon.remarkable import sync as _sync
        return bool(_sync.mirrored())
    except Exception:
        return False


def batch(todo):
    """One job per PAGE: each tagged page that is new or changed is its own job -- CHANGED PAGES FIRST, then new
    ones (the user's rule), each in notebook order and then page order -- so every page gets its own look and its
    own record."""
    order, by_doc = [], {}
    for q in todo:
        d = q["doc_id"]
        if d not in by_doc:
            by_doc[d] = []
            order.append(d)
        by_doc[d].append(q)
    out = []
    rows = [r for d in order for r in sorted(by_doc[d], key=lambda q: (q["page"] or 0))]
    rows.sort(key=lambda q: 0 if (q.get("why") == "changed" or q["status"] in ("REOPENED", "RETAGGED")) else 1)
    for row in rows:
        job = dict(row)
        job["batch"] = [row]
        job["keys"] = [row["key"]]
        job["bkey"] = row["key"]
        job["fp"] = row["state"]["sha"]
        out.append(job)
    return out


# --------------------------------------------------------- the daemon's voice
# Syncing and reporting are the daemon's jobs, not the model's. A change seen within SELF_WRITE seconds
# of the host recording a job is the job's own write landing; anything earlier is the user's, and the
# page is queued again.
SELF_WRITE = int(os.environ.get("RM_SELF_WRITE", "20"))


# sync() outcomes; PENDING models an owed push while the network or the cloud is unavailable
SYNC_OK, SYNC_FAIL = 0, 2
# Set when a push is owed to the tablet. The write already landed in the local
# cache, so nothing is lost by waiting -- it just is not on the device yet.
PENDING = {"sync": False, "at": 0.0}


# Pages that changed while their job ran; queued again once it is recorded.
REQUEUE = set()


def sync(why="", doc_id=None):
    """Push local changes to the tablet.

    Three HTTPS PUTs and a pointer move: no window, no clicks.
    """
    if DRY:
        log("  DRY RUN -- not syncing")
        return SYNC_OK
    from paperdaemon.remarkable import sync as cloud
    try:
        changed = list(cloud.changed_files())
        docs = ({doc_id} if doc_id else
                {n.split("/")[0].split(".")[0] for n, _, _ in changed})
        # Which PAGES actually changed, so stamping does not tell the device to
        # re-fetch every page of a long notebook.
        touched = {}
        for n, _, _ in changed:
            if "/" in n and n.endswith(".rm"):
                d, f = n.replace("\\", "/").split("/", 1)
                touched.setdefault(d.split(".")[0], set()).add(f[:-3])
        if not docs:
            return SYNC_OK
        owed = False
        for d in docs:
            # STAMP BEFORE PUSHING. A new .rm blob alone is invisible to the
            # device: it compares `lastModified` on the document and `modifed`
            # on the page, and both still hold whatever the TABLET last wrote.
            # Measured -- a drawing sat in the cloud matching the mirror
            # exactly and never appeared on the tablet across repeated syncs,
            # because nothing told the device the page had changed.
            try:
                t = cloud.touch(d, sorted(touched.get(d, [])) or None)
                if t.get("files"):
                    log("  stamped %s: %s" % (d[:8], ", ".join(t["files"])[:60]))
            except Exception as ex:
                log("  stamp failed for %s: %s" % (d[:8], str(ex)[:70]))
            r = cloud.push_doc(d, dry_run=False)
            # new files too: a page the host ADDED is in new_files, and logging only `files` made a
            # successful push of two new coloring pages read as if they had been left behind
            log("  pushed %s: %s%s" % (d[:8], r.get("files") or r.get("skipped"),
                                        ("; new: %s" % r["new_files"]) if r.get("new_files") else ""))
            if r.get("theirs"):
                # the tablet changed some of these since the last pull: pull them, then push what is still ours
                log("  the tablet changed %s meanwhile; pulling before pushing the rest" % ", ".join(r["theirs"])[:80])
                owed = True
        if owed:
            PENDING["sync"], PENDING["at"] = True, time.time()     # the engine pulls the tablet's change; then again
            return SYNC_FAIL
        PENDING["sync"] = False
        return SYNC_OK
    except Exception as e:
        log("  PUSH FAILED: %s" % e)
        PENDING["sync"] = True
        PENDING["at"] = time.time()
        return SYNC_FAIL


def content_bottom(doc_name, page_no):
    """Lowest occupied y on the page, so the footer can clear it.

    APPROXIMATE, and deliberately so. `rm_render.strokes` returns raw stroke
    coordinates, and on a page with typed text those are relative to a group
    anchor whose y offset the file does not record -- the skill's standing
    caveat. It is good enough here for one reason: the footer lives BELOW the
    safe area, where the user's content essentially never reaches, so this only
    has to catch the rare drawing that runs into the gutter. When it is wrong
    it is wrong by a margin that still leaves the footer on the paper.
    """
    lo = None
    try:
        from paperdaemon.pipeline.page import render as R
        doc = R.find_doc(doc_name)
        for line in R.strokes(doc, page_no):
            for pt in getattr(line, "points", ()):
                if lo is None or pt.y > lo:
                    lo = pt.y
    except Exception as e:
        log("  (could not measure strokes: %s)" % e)
    try:
        from paperdaemon.pipeline.page import typed as TY
        tb = TY.text_bottom(doc_name, page_no)
        if tb is not None and (lo is None or tb > lo):
            lo = tb
    except Exception:
        pass
    return lo


def note(doc_name, page_no, message):
    """Stamp one line and the signature into the page GUTTER, then sync.

    The gutter -- below the safe zone, hard against the paper edge -- is the
    only place the daemon is allowed to write. The user never puts anything
    there, so an unattended write cannot overlap or reflow their content. It is a
    stamp on the envelope, not an edit to the letter.
    """
    if DRY:
        log("  DRY RUN -- would note: %s" % message)
        return True
    try:
        from paperdaemon.pipeline import draw as A
        from paperdaemon.pipeline.draw import signature as SIG
    except Exception as e:
        log("  cannot write a note (%s)" % e)
        return False
    try:
        _backup_page(doc_name, page_no)
        d = A.Drawing()
        y = SIG.draw_footer(d, message, content_bottom=content_bottom(doc_name,
                                                                     page_no))
        res = d.write_rm(doc_name, page_no, keep_existing=True)
        log("  noted on %s p%s at y=%.0f (%s strokes)"
            % (doc_name, page_no, y, res.get("strokes") if
               isinstance(res, dict) else "?"))
    except Exception as e:
        log("  FAILED to write the note: %s" % e)
        return False
    # The note is on the page either way; only the push can be deferred.
    return sync("daemon note") != SYNC_FAIL


def _backup_page(doc_name, page_no):
    """Copy the page and the document's json before writing to it.

    Deliberately NOT the whole document directory, which can be tens of megabytes:
    a footer touches exactly one page, and this restores exactly that page.
    """
    import shutil
    from paperdaemon.pipeline.page import render as R
    doc = R.find_doc(doc_name)
    pid = R.live_pages(doc)[page_no - 1]["id"]
    dest = os.path.join(_STATE, "rm-backups", "%s-daemon-note-%s-p%s"
                        % (time.strftime("%Y%m%d-%H%M%S"), doc[:8], page_no))
    os.makedirs(os.path.join(dest, doc), exist_ok=True)
    for f in (doc + ".metadata", doc + ".content"):
        src = os.path.join(rm_scan.RM, f)
        if os.path.exists(src):
            shutil.copy2(src, os.path.join(dest, f))
    shutil.copy2(os.path.join(rm_scan.RM, doc, pid + ".rm"),
                 os.path.join(dest, doc, pid + ".rm"))
    log("  backed up -> %s" % os.path.basename(dest))


def report_failure(job, why):
    """Tell the user on the tablet, then settle the directive so it stops.

    Order matters: write, sync, THEN record. `mark` anchors the ledger to the
    page's content as it stands, and the note itself changes that content -- so
    recording first would leave the directive permanently re-opened by the very
    note that said it had been abandoned.
    """
    rows = job.get("batch") or [job]
    page = rows[0]
    # Timestamp FIRST, so that when the daemon logs again it lands right under its old
    # error: the gutter reads as a log, one stamped line per attempt, not a sentence
    # with a time bolted on the end.
    from paperdaemon import i18n
    note(job["doc"], page["page"], "%s  %s" % (i18n.clock(), why))
    for r in rows:
        rm_scan.mark(r["key"], "skipped", "daemon gave up: %s" % why, failed=True)


# The daemon and the host share two files: the queue (one JSON file per job) and the ledger.
QUEUE = os.path.join(_STATE, "rm-queue")


# --------------------------------------------------------------------- dispatch
# The daemon NEVER waits. It used to sit inside dispatch() polling the ledger
# for as long as a job took, which meant its 1 Hz heart stopped for the whole
# job: it could not notice new work, could not see the user editing a page, and
# any exception in there took the whole daemon down with it.
#
# Now it hands the job over and returns. One job is in flight at a time (still
# serial), and the queue needs no file: a claimed ledger entry
# with status "working" IS the queue, and it survives a restart.
INFLIGHT = {}


def elapsed(t):
    d = int(time.time() - t)
    return "%dm %02ds" % (d // 60, d % 60) if d >= 60 else "%ds" % d


def where(job):
    """'Meeting notes p18' -- what a human calls it. Keys are for the ledger."""
    return "%s %s" % (job["doc"], job.get("loc")
                      or ("p%s" % job["page"] if job["page"] else "doc"))


def host_started_at():
    """When the host last started (it stamps rm-queue/host-started), or 0."""
    try:
        return os.path.getmtime(os.path.join(QUEUE, "host-started"))
    except OSError:
        return 0.0


def queued_keys():
    """Keys already sitting in the queue, so we never enqueue the same work twice.

    Without this the daemon re-queued anything the host had not yet consumed --
    the queue held two copies each of two jobs, and the ledger claim made no
    difference because a restart forgets what was in flight.
    """
    out = set()
    try:
        names = os.listdir(QUEUE)
    except OSError:
        return out
    for n in names:
        if not n.endswith(".json"):
            continue
        try:
            with open(os.path.join(QUEUE, n), encoding="utf-8") as f:
                out.update(json.load(f).get("keys") or [])
        except Exception:
            pass
    return out


def hand_over(job):
    """Queue the job and return. The host works it when it is free."""
    keys = job.get("keys") or [job["key"]]
    key = job.get("bkey", job["key"])
    if set(keys) & queued_keys():
        return False                      # already waiting; do not duplicate it
    os.makedirs(QUEUE, exist_ok=True)
    stamp = "%d-%s" % (int(time.time() * 1000), key[:8])
    body = {"keys": keys, "where": where(job)}
    if job.get("conflict"):
        body["conflict"] = job["conflict"]
    with open(os.path.join(QUEUE, stamp + ".json"), "w", encoding="utf-8") as f:
        json.dump(body, f)
    log("QUEUED %s" % where(job))
    INFLIGHT.update(job=job, keys=keys, key=key, since=time.time(),
                    seen={r["key"]: (r["doc_id"], r.get("page_id"),
                                     r["state"]["sha"])
                          for r in (job.get("batch") or [job])},
                    moved={})
    return True


def hand_over_conflict():
    """The oldest page the tablet and a job both changed, handed to the host as a CONFLICT job: the page as the
    tablet has it, the job's copy that was set aside, and what the job did. -> True when one was handed over."""
    from paperdaemon.remarkable import sync as cloud
    rec = cloud.take_conflict()
    if not rec:
        return False
    led = rm_scan.load()["entries"]
    key = next((k for k, e in led.items() if e.get("doc_id") == rec["doc"] and e.get("page_id") == rec["page_id"]), None)
    if key is None:
        log("  a conflict on a page no tag watches (%s) -- the tablet's copy stands" % rec["page_id"][:8])
        return False
    if not rm_scan.claim(key, "daemon"):
        cloud.record_conflict(rec["doc"], rec["page_id"], rec["ours"])     # someone holds the page: later
        return False
    e = dict(led[key])
    try:
        state = rm_scan.page_state(rec["doc"], rec["page_id"])
    except Exception:
        state = {"sha": None}
    job = dict(e, key=key, keys=[key], bkey=key, state=state,
               conflict={"ours": rec["ours"], "made_by": str(e.get("note") or "")[:600]})
    if not hand_over(job):
        rm_scan.release(key, "daemon")
        return False
    log("  CONFLICT on %s handed over: the tablet's page stands, the job's copy is weighed against it" % where(job))
    return True


def watch_inflight():
    """Notice the user editing a page while its job runs, so the page is queued again once the job is
    recorded.
    """
    for k, (doc, pid, was) in list(INFLIGHT["seen"].items()):
        cur = rm_scan.page_state(doc, pid)["sha"]
        if cur != was:
            INFLIGHT["seen"][k] = (doc, pid, cur)
            INFLIGHT["moved"][k] = time.time()


def finish_job(attempts):
    """The in-flight job has recorded. Sync, re-anchor, re-queue, clear."""
    job, keys, key = INFLIGHT["job"], INFLIGHT["keys"], INFLIGHT["key"]
    log("  finished in %s" % elapsed(INFLIGHT["since"]))
    done_at = time.time()
    requeue = {k for k, when in INFLIGHT["moved"].items()
               if done_at - when > SELF_WRITE}
    attempts.pop(key, None)
    # Sync BEFORE re-anchoring: the push makes the app re-serialize the page and
    # move its hash, so anchoring first would re-open the directive.
    sync("job %s" % key)
    with rm_scan.locked():                 # nobody writes the ledger between this read and write
        led = rm_scan.load()
        touched = False
        for r in (job.get("batch") or [job]):
            ent = led["entries"].get(r["key"])
            if not ent:
                continue
            # THE HOST SAW THE PAGE CHANGE UNDER IT, and not by its own hand: it knows the page as it
            # found it and as it left it, which the timing test below cannot -- a request typed in a
            # job's last 20 s, or before its commit, was taken for the job's own write and swallowed.
            # Such a page is re-queued, exactly as a late edit is.
            checked = ent.pop("checked", None)
            if ent.pop("requeue", None):
                requeue.add(r["key"])
                touched = True
            elif checked:
                requeue.discard(r["key"])      # the host compared exactly; the timing guess stands down
                touched = True
            fresh = rm_scan.page_state(r["doc_id"], r.get("page_id"))
            if ent.get("handled_sha") != fresh["sha"]:
                ent["handled_sha"] = fresh["sha"]
                touched = True
            if ent.get("status") == "skipped":
                log("  SKIPPED %s: %s" % (r["key"], ent.get("note") or "?"))
        for k in requeue:
            e = led["entries"].get(k)
            if e:
                e["status"] = "pending"
                e["why"] = "changed"
                e["handled_sha"] = None
                e["handled_raw"] = None
                touched = True
        if requeue:
            log("  changed while it worked -- re-queued %s" % ", ".join(sorted(requeue)))
        if touched:
            rm_scan.save(led)
    INFLIGHT.clear()


# ------------------------------------------------------------------- main loop
def main():
    reset_log(LOGFILE)
    log("daemon start  interval=%ds dry=%s" % (INTERVAL, DRY))
    # The daemon never talks to a model: it queues jobs and the host chooses the model it runs
    log("watching for %s; jobs go to rm-queue/ for the host; log %s"
        % (", ".join(repr(t) for t in rm_scan.TRIGGERS) or "no tags yet", LOGFILE))
    # EVERY NOTEPAD MUST HAVE A NOTEBOOK. The mirror is the app's, so a document the user deleted
    # is gone from it -- but our own bookkeeping outlives it, which would leave a removed notebook
    # still readable here. Trashed counts as deleted: the trash is the user's holding area, not
    # ours to read from, and they should not have to empty it to be forgotten.
    try:
        from paperdaemon.remarkable import sync as _sync
        # only against a complete Mirror: one still filling would make every notebook not yet copied look
        # deleted, and drop its bookkeeping
        pruned = rm_scan.prune_notepads() if _sync.mirrored() else {}
        if pruned.get("ledger_entries") or pruned.get("history"):
            log("notepads without a notebook: dropped %d ledger entr%s and %d page histor%s"
                % (pruned.get("ledger_entries", 0),
                   "y" if pruned.get("ledger_entries", 0) == 1 else "ies",
                   len(pruned.get("history") or []),
                   "y" if len(pruned.get("history") or []) == 1 else "ies"))
    except Exception as ex:
        log("could not check notepads against notebooks: %s" % str(ex)[:80])
    log("jobs go to rm-queue/; the host feeds them to its model and owns the "
        "job's lifecycle")

    attempts = {}
    tick = 0
    last_fp = None
    cycles = 0
    err_state = {"sig": None, "n": 0, "last": 0.0, "since": 0.0}

    def release_dead():
        """A job claimed before the running host started died with the host that had it (an update restarts
        both): hand it over again. At the start, and once a minute while nothing is in flight."""
        started = host_started_at()
        if not started:
            return
        try:
            gone = rm_scan.release_dead_claims(started)
        except Exception as ex:
            log("could not check for jobs a stopped host had: %s" % str(ex)[:80])
            return
        for k in gone:
            log("  the host that had %s stopped -- handing it over again" % k)

    release_dead()
    while True:
        cycles += 1
        if not INFLIGHT and cycles % 60 == 0:
            release_dead()
        try:
            # UNDER THE LEDGER LOCK: this cycle writes back the whole ledger it read, and a host
            # "done" landing in between was put back to "pending" -- the daemon then waited 25
            # minutes on a job that had finished in under a second
            with rm_scan.locked():
                led = rm_scan.load()
                # THE START IS A COMPLETE MIRROR: the first look files every tagged page as it is, so taken while the
                # mirror is still filling, the pages copied after it would all look new
                if "watching_since" not in led and not _mirror_complete():
                    queue = []
                else:
                    queue = rm_scan.classify(rm_scan.scan(), led)
                fp = json.dumps({k: {kk: vv for kk, vv in v.items() if kk != "last_seen"}
                                 for k, v in led["entries"].items()}, sort_keys=True)
                if fp != last_fp or cycles % 60 == 0:
                    rm_scan.save(led)
                    last_fp = fp
        except Exception as e:
            # A REPEATING fault must not be able to write thousands of identical
            # lines at 1 Hz. A single missing dict key (document-level tags had
            # no "raw") once filled the log with the same line and buried the
            # one clue that mattered. Report it once, then back off and say so
            # periodically -- loudly enough to notice, quietly enough to read.
            sig = "%s: %s" % (type(e).__name__, e)
            errs = err_state
            if sig != errs["sig"]:
                errs["sig"], errs["n"], errs["since"] = sig, 1, time.time()
                log("scan error: %s" % sig)
                log("  backing off; will report every %ds while it persists"
                    % ERROR_BACKOFF)
            else:
                errs["n"] += 1
                if time.time() - errs["last"] >= ERROR_BACKOFF:
                    log("scan error persists (%dx over %ds): %s"
                        % (errs["n"], int(time.time() - errs["since"]), sig))
                    errs["last"] = time.time()
            time.sleep(min(ERROR_BACKOFF, max(INTERVAL, 5)))
            continue
        else:
            if err_state["sig"]:
                log("scan recovered after %d error(s)" % err_state["n"])
                err_state.update(sig=None, n=0, last=0.0, since=0.0)

        for d_ in sorted(set(q["doc"] for q in queue if q.get("too_many"))):
            log("  %s: more than %d pages new or changed at once -- none is a job; recorded as they are"
                % (d_, rm_scan.NOTEBOOK_CAP))
        todo = [q for q in queue if q["status"] in ("NEW", "PENDING", "REOPENED", "RETAGGED")]
        # A PAGE TAGGED FOR MORE THAN ONE LINEUP is nobody's job: the daemon says so on the page, once, and settles it
        # (it comes back when its tags are one lineup's again)
        for q in [q for q in todo if q.get("lineups")]:
            if not DRY:
                log("  %s has tags of %s -- skipping it" % (where(q), " and ".join(q["lineups"])))
                note(q["doc"], q["page"], rm_scan.TAGS_ACROSS_LINEUPS)
                rm_scan.mark(q["key"], "skipped", rm_scan.TAGS_ACROSS_LINEUPS, tag_conflict=True)
        todo = [q for q in todo if not q.get("lineups")]
        claimed = [q for q in queue if q["status"] == "CLAIMED"]
        waiting = [q for q in queue if q["status"] == "WAITING"]
        if DRY:
            note = "dry run"
        else:
            note = "idle"
        if claimed:
            note = "%s held by %s" % (claimed[0]["key"],
                                      claimed[0].get("claim_owner", "?"))
        now = time.time()

        if INFLIGHT:
            watch_inflight()
            ents = rm_scan.load()["entries"]
            sts = [ents.get(k, {}).get("status") for k in INFLIGHT["keys"]]
            if all(x in ("done", "skipped") for x in sts):
                finish_job(attempts)
                last_fp = None
            elif host_started_at() > INFLIGHT["since"] and not (set(INFLIGHT["keys"]) & queued_keys()):
                # THE HOST STARTED AGAIN AFTER TAKING THIS JOB, and never recorded it: it died or
                # was restarted mid-job, and the job went with it. Waiting for its record is waiting
                # forever (until the pages are marked by hand). The pages
                # are released and the job handed over again -- not counted as a failed attempt,
                # because nothing about the page failed.
                log("  the host restarted while it had %s -- handing it over again" % where(INFLIGHT["job"]))
                with rm_scan.locked():
                    led = rm_scan.load()
                    for k in INFLIGHT["keys"]:
                        e = led["entries"].get(k)
                        if e and e.get("status") not in ("done", "skipped"):
                            e["status"] = "pending"
                            e.pop("claim_owner", None)
                            e.pop("claim_at", None)
                    rm_scan.save(led)
                k0 = INFLIGHT.get("key")
                if k0 in attempts:
                    attempts[k0] = max(0, attempts[k0] - 1)
                INFLIGHT.clear()
            else:
                note = "%s  %s" % (where(INFLIGHT["job"]),
                                   elapsed(INFLIGHT["since"]))
        else:
          for job in batch(todo):
            keys = job["keys"]
            key = job["bkey"]
            if attempts.get(key, 0) >= MAX_ATTEMPTS:
                log("  GIVING UP on %s -- writing a note on the page" % key)
                from paperdaemon import i18n
                report_failure(job, i18n.say("page.gave_up", {"n": MAX_ATTEMPTS}))
                attempts.pop(key, None)
                note = "%s needs a human" % where(job)
                break
            if DRY:
                note = "would dispatch %s" % where(job)
                break                 # a dry run must not touch state
            attempts[key] = attempts.get(key, 0) + 1
            taken = []
            for k in keys:
                if rm_scan.claim(k, "daemon"):
                    taken.append(k)
                    continue
                log("  another worker holds %s -- leaving the notebook to them" % k)
                for t in taken:
                    rm_scan.release(t, "daemon")
                taken = None
                break
            if taken is None:
                break
            if not hand_over(job):
                for t in taken:
                    rm_scan.release(t, "daemon")
            break                      # one job at a time, always
          # CONFLICTS WAIT BEHIND EVERY OTHER JOB: handed over only when nothing else is owed
          if not todo and not DRY and not INFLIGHT:
              hand_over_conflict()

        # ---- the mirror: the engine keeps it current (keeper.py); the daemon only reads it ----

        # ---- a push we still owe the tablet ----
        # Only while nothing else is happening, and a minute between goes.
        if (PENDING["sync"] and not DRY and not todo
                and not claimed and (now - PENDING["at"]) >= 60):
            if sync("deferred push") == SYNC_OK:
                last_fp = None
                note = "deferred sync completed"
            else:
                note = "sync owed -- the cloud did not take it yet"
        elif PENDING["sync"]:
            note = "sync owed -- waiting for the daemon to be idle"

        # ---- cadence ----
        # Poll the queue every INTERVAL (1s). DETECTION is the daemon's job and
        # must stay responsive -- an earlier version slept 5s at a time while
        # idle to save wakeups, which made tagging a page feel laggy for no real
        # benefit. A stat of a handful of files once a second is nothing.
        for _ in range(max(1, INTERVAL)):
            heartbeat(tick, note)
            tick += 1
            time.sleep(1)


# Closing a console window with the X button does NOT raise KeyboardInterrupt --
# no Python cleanup runs at all. Windows instead sends CTRL_CLOSE_EVENT and
# gives roughly five seconds before killing the process, which is plenty to
# tear down what we own. Without this, "close the window" left orphans behind
# and only the next startup swept them up.
_HANDLERS = []


def on_close(fn):
    try:
        import ctypes
        from ctypes import wintypes
        proto = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.DWORD)

        def _h(event):
            if event in (0, 1, 2, 5, 6):   # C, BREAK, CLOSE, LOGOFF, SHUTDOWN
                try:
                    fn()
                except Exception:
                    pass
            return False                    # let the default handler proceed

        cb = proto(_h)
        _HANDLERS.append(cb)                # must outlive the call
        ctypes.windll.kernel32.SetConsoleCtrlHandler(cb, True)
    except Exception:
        pass


def _shutdown():
    log("daemon stopped")
