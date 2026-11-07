"""One writer of a page file at a time, across processes (paths.page_lock): two processes each reading a file, changing
it and writing it whole, as the daemon's notes and the host's commits do, lose none of each other's changes."""
import multiprocessing as mp
import os
import time

from paperdaemon import paths


def _writer(path, tag, n, locked):
    for i in range(n):
        if locked:
            with paths.page_lock(path):
                data = open(path, "rb").read()
                time.sleep(0.002)                    # the read and the write apart, as a page's change takes time
                paths.write_atomic(path, data + b"%s%d\n" % (tag, i))
        else:
            data = open(path, "rb").read()
            time.sleep(0.002)
            paths.write_atomic(path, data + b"%s%d\n" % (tag, i))


def _race(tmp_path, locked, n=40):
    path = str(tmp_path / ("page-%s.rm" % ("locked" if locked else "bare")))
    open(path, "wb").close()
    ctx = mp.get_context("spawn")
    ps = [ctx.Process(target=_writer, args=(path, tag, n, locked)) for tag in (b"note", b"host")]
    for p in ps:
        p.start()
    for p in ps:
        p.join(120)
    lines = open(path, "rb").read().split()
    return sum(1 for ln in lines if ln.startswith(b"note")), sum(1 for ln in lines if ln.startswith(b"host"))


def test_two_processes_lose_nothing_under_the_page_lock(tmp_path):
    assert _race(tmp_path, True) == (40, 40)


def test_the_lock_is_reentrant_and_one_per_page(tmp_path):
    a, b = str(tmp_path / "a.rm"), str(tmp_path / "b.rm")
    assert paths.page_lock(a) is paths.page_lock(a)
    assert paths.page_lock(a) is not paths.page_lock(b)
    with paths.page_lock(a):
        with paths.page_lock(a):                     # a commit holds it across the writes it makes
            pass


def test_locks_page_names_the_page_from_the_writers_arguments(tmp_path):
    seen = []

    @paths.locks_page(lambda doc, page_no, *a, **k: str(tmp_path / ("%s-%d.rm" % (doc, page_no))))
    def write(doc, page_no, what):
        lk = paths.page_lock(str(tmp_path / ("%s-%d.rm" % (doc, page_no))))
        seen.append((what, lk._depth))               # held (depth 1) while the writer runs
        return what

    assert write("d", 2, "x") == "x" and seen == [("x", 1)]

    @paths.locks_page(lambda *a, **k: 1 / 0)          # a page it cannot name: the writer runs as it is
    def plain(v):
        return v

    assert plain(5) == 5
    assert os.path.isdir(os.path.dirname(paths.page_lock(str(tmp_path / "x.rm")).path))
