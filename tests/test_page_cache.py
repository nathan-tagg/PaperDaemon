"""A page saved between the daemon's read of it and its look at the file (11-16, DF239: a typed request written the
instant its notebook was made) is never taken for the page it replaced: the empty test and the content fingerprint are
kept by the bytes read, not by the file's time and size looked up after."""
import hashlib
import os

from paperdaemon import ledger as L

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CASES = os.path.join(ROOT, "tests", "benchmark", "cases")


def _pages():
    """A page with nothing on it, and one with a typed request (from the benchmark's fixtures)."""
    import paperdaemon.pipeline  # noqa: F401
    from paperdaemon import studio
    from paperdaemon.pipeline import TEMPLATES
    blank = studio._blank_page_bytes(os.path.dirname(TEMPLATES), None)
    src = os.path.join(CASES, "typed-question", "mirror")
    doc = next(f[:-8] for f in os.listdir(src) if f.endswith(".content"))
    folder = os.path.join(src, doc)
    page = next(os.path.join(folder, f) for f in os.listdir(folder) if f.endswith(".rm"))
    return blank, open(page, "rb").read()


def test_a_page_saved_between_the_read_and_the_look_is_read_again(tmp_path):
    blank, typed = _pages()
    path = str(tmp_path / "page.rm")
    with open(path, "wb") as f:
        f.write(typed)                                   # the file as it is now: the request saved
    raw_blank = hashlib.sha256(blank).hexdigest()[:16]
    # the daemon read the blank page a moment before (its bytes), then looked at the file (already the new one)
    assert L._is_empty(path, blank, raw_blank) is True
    sha_blank = L._content_sha(path, blank, raw_blank)
    # the next look reads the file as it is: the request is there, and its fingerprint is its own
    data = open(path, "rb").read()
    raw = hashlib.sha256(data).hexdigest()[:16]
    assert L._is_empty(path, data, raw) is False
    assert L._content_sha(path, data, raw) != sha_blank
