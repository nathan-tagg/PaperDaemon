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


def test_the_two_typed_readers_are_paired_by_identity_not_place(monkeypatch):
    """11-16, the Tools notebook: on a page edited inside older text the old parse put paragraphs in another order than
    the measured reader (and garbled one); paired by index, the newest typing took an older paragraph's words. Paired by
    identity (the style key is the newline before a paragraph: its start id less one), in the measured reader's order."""
    from paperdaemon.pipeline.page import typed as TY
    old = [{"start_id": (0, 15), "text": "Hello", "lines": ["Hello"]},
           {"start_id": (127, 900), "text": "te throec garbled", "lines": ["x"]},     # the old parse's order and words
           {"start_id": (127, 500), "text": "older line", "lines": ["x"]}]
    got = [{"style_key": "0:0", "text": "Hello", "bbox": [0, 234, 10, 10], "style_code": 1, "lines": []},
           {"style_key": "127:499", "text": "older line", "bbox": [0, 300, 10, 10], "style_code": 1, "lines": []},
           {"style_key": "127:899", "text": "Fix this page, newest", "bbox": [0, 400, 10, 10], "style_code": 1, "lines": []}]
    monkeypatch.setattr(TY, "_engine", lambda: object())
    monkeypatch.setattr(TY, "_layout", lambda d, n: {"paragraphs": got})
    out = TY._measured("doc", 1, old)
    assert [(p["start_id"], p["text"], p["y"]) for p in out] == [
        ((0, 15), "Hello", 234), ((127, 500), "older line", 300), ((127, 900), "Fix this page, newest", 400)]


def test_a_job_asked_for_on_a_tagged_page_goes_back_in_the_queue(monkeypatch):
    """11-16: "force paperdaemon to run a job on a tagged page" -- put back as the retry box puts it, asked for again;
    a page being worked is left to its job, and a page no tag watches is no job."""
    import contextlib
    led = {"entries": {"d/p1": {"doc_id": "d", "page_id": "p1", "status": "done", "note": "wrote: hi", "handled_sha": "s"},
                       "d/p2": {"doc_id": "d", "page_id": "p2", "status": "working"}}}
    monkeypatch.setattr(L, "load", lambda: led)
    monkeypatch.setattr(L, "save", lambda x: None)
    monkeypatch.setattr(L, "locked", contextlib.nullcontext)
    assert L.run_again("d", "p1") == "queued"
    e = led["entries"]["d/p1"]
    assert e["status"] == "pending" and e["handled_sha"] is None and e["retry"] == {"asked": True, "note": "wrote: hi"}
    assert L.run_again("d", "p2") == "working" and led["entries"]["d/p2"]["status"] == "working"
    assert L.run_again("d", "p3") is None
