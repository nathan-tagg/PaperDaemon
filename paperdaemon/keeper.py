"""The mirror keeper: while PaperDaemon runs and has a reMarkable login, its copy of the library stays current,
whether or not the daemon is working pages.

It holds the account's notice connection (sync.Notifier: the cloud says when the tablet changed something) and pulls
on each notice, once at the start, and on every connect (a notice is never sent again, so whatever changed while the
connection was down is fetched then). A timed check runs only while that connection is down. A pull that fails is
tried again on its own once a minute; what it had fetched is kept (sync.pull). The error stays up as ONE error, the
same one, until a pull succeeds (server._pull_once).
Every pull with something new shows on the Tablet screen's bar (server.run_pull).

The daemon pulls nothing: it only watches the mirror for tagged pages. Pull and push share one lock across the
processes (sync._one_at_a_time), so a job's push and the keeper's pull never write over each other."""
import threading
import time

CHECK_WHILE_DOWN = 60                  # seconds between timed checks while the notice connection is down
RETRY_FIRST, RETRY_MOST = 60, 60       # a failed pull (no internet, say) is tried again once a minute

_started = threading.Event()


def start():
    """Keep the mirror current from now on (once per process)."""
    if _started.is_set():
        return
    _started.set()
    threading.Thread(target=_keep, name="mirror-keeper", daemon=True).start()


def _logged_in():
    from .remarkable import auth
    try:
        return bool(auth.describe().get("set"))
    except Exception:
        return False


def _keep():
    from . import server
    from .remarkable import sync
    want = threading.Event()
    want.set()                                         # the first look, as PaperDaemon starts
    notifier, was_alive = None, False
    retry_at, retry_wait, last = None, RETRY_FIRST, 0.0
    while True:
        try:
            if not _logged_in():
                if notifier is not None:
                    notifier.stop()
                    notifier, was_alive = None, False
                want.set()                             # a login arriving brings a pull at once
                time.sleep(5)
                continue
            if notifier is None:
                notifier = sync.Notifier(on_change=lambda source=None: want.set()).start()
            alive = bool(notifier.alive)
            if alive and not was_alive:
                want.set()                             # connected or back: catch up on what was missed
            was_alive = alive
            now = time.time()
            due = (want.is_set() or (retry_at is not None and now >= retry_at)
                   or (not alive and now - last >= CHECK_WHILE_DOWN))
            if due:
                want.clear()
                ok = server.run_pull()
                last = time.time()
                if ok:
                    retry_at, retry_wait = None, RETRY_FIRST
                elif server._pull.get("error"):
                    retry_at = time.time() + retry_wait
                    retry_wait = min(RETRY_MOST, retry_wait * 2)
                else:
                    want.set()                         # another pull was running (the Tablet screen's): look again
                    time.sleep(2)
        except Exception:
            time.sleep(5)                              # never let the keeper die; it tries again
        want.wait(1)
