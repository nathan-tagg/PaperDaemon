"""One lock across PaperDaemon's processes (the engine, the daemon and the host), held on a file.

    with FileLock(path):
        ...                       # no other process is inside a `with` on the same path

Re-entrant within a process (a nested `with` on the same lock does not wait for itself), and released by the
operating system if the process holding it dies."""
import os
import threading
import time


class FileLock(object):
    def __init__(self, path):
        self.path = path
        self._t = threading.RLock()
        self._depth = 0
        self._f = None

    def __enter__(self):
        self._t.acquire()
        if self._depth == 0:
            os.makedirs(os.path.dirname(self.path), exist_ok=True)
            f = open(self.path, "a+b")
            if os.name == "nt":
                import msvcrt
                while True:
                    try:
                        f.seek(0)
                        msvcrt.locking(f.fileno(), msvcrt.LK_NBLCK, 1)
                        break
                    except OSError:
                        time.sleep(0.05)
            else:
                import fcntl
                fcntl.flock(f.fileno(), fcntl.LOCK_EX)
            self._f = f
        self._depth += 1
        return self

    def __exit__(self, *exc):
        self._depth -= 1
        if self._depth == 0 and self._f is not None:
            f, self._f = self._f, None
            try:
                if os.name == "nt":
                    import msvcrt
                    f.seek(0)
                    msvcrt.locking(f.fileno(), msvcrt.LK_UNLCK, 1)
            except OSError:
                pass
            f.close()
        self._t.release()
        return False
