"""Books (openspec add-epub-reading): the tablet's PDF arriving on a book is never a job, and PaperDaemon lays a book
out as the tablet does, with its faces."""
import json
import os
import subprocess
import sys
import textwrap

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

SCAN = textwrap.dedent("""
    import json
    from paperdaemon import ledger as S
    led = {"entries": {}}
    S.classify(S.scan(), led)                             # the first look files what is there
    if %(convert)s:
        # THE TABLET CONVERTS THE BOOK: its PDF lands beside the EPUB, its reading settings in the .content, and its page
        # list now runs to the book's length -- pages with nothing written on them
        open(S.RM + "/book.pdf", "wb").write(b"%%PDF-1.4 the tablet's pages")
        c = json.load(open(S.RM + "/book.content"))
        c.update(margins=125, textScale=1, lineHeight=100)
        c["cPages"]["pages"] += [{"id": "p%%d" %% i, "redir": {"value": i - 1}} for i in range(3, 9)]
        json.dump(c, open(S.RM + "/book.content", "w"))
        S._DOC_CACHE.clear()
    q = S.classify(S.scan(), led)
    print(json.dumps(sorted(f["status"] for f in q)))
""")


def _scan(tmp_path, convert):
    m = tmp_path / ("mirror-%d" % convert)
    m.mkdir()
    (m / "f-books.metadata").write_text(json.dumps({"visibleName": "Books", "parent": "", "type": "CollectionType"}))
    (m / "f-books.content").write_text(json.dumps({"tags": [{"name": "PaperDaemon", "timestamp": 1}]}))
    (m / "book.metadata").write_text(json.dumps({"visibleName": "A book", "parent": "f-books", "type": "DocumentType"}))
    (m / "book.content").write_text(json.dumps({"fileType": "epub", "tags": [], "pageTags": [],
                                               "cPages": {"pages": [{"id": "p1", "redir": {"value": 0}},
                                                                    {"id": "p2", "redir": {"value": 1}}]}}))
    (m / "book.epub").write_bytes(b"PK")
    env = dict(os.environ, RM_CACHE=str(m), RM_MIRROR=str(m), RM_STATE=str(tmp_path), RM_TRIGGERS='["PaperDaemon"]',
               PAPERDAEMON_HOME=str(tmp_path / "home"))
    out = subprocess.run([sys.executable, "-c", SCAN % {"convert": convert}], env=env, capture_output=True, text=True,
                         timeout=300, cwd=ROOT)
    assert out.returncode == 0, out.stderr[-2000:]
    return json.loads(out.stdout.strip().splitlines()[-1])


def test_the_tablets_pdf_arriving_starts_no_job(tmp_path):
    before = _scan(tmp_path, False)
    after = _scan(tmp_path, True)
    jobs = {"NEW", "REOPENED", "RETAGGED", "PENDING"}
    assert not jobs & set(before)
    assert not jobs & set(after), after                   # nothing on any page: nothing to answer


CONVERT = textwrap.dedent("""
    import json, os
    from paperdaemon import paths, settings as S
    from paperdaemon.remarkable import auth, convert, sync
    fm, mirror = paths.false_mirror_dir(), sync.MIRROR
    calls = []
    auth.describe = lambda: {"set": True}                  # an account is signed in
    def push_new_doc(doc, dry_run=True):                   # the cloud, as far as this test goes
        calls.append(("push", json.load(open(os.path.join(mirror, doc + ".content")))["tags"][0]["name"],
                      json.load(open(os.path.join(mirror, doc + ".metadata")))["parent"]))
        return {"root_put": 200}
    def delete_doc(doc):
        calls.append(("delete", doc))
        for f in os.listdir(mirror):
            if f.startswith(doc):
                os.remove(os.path.join(mirror, f))
        return {"deleted": True}
    sync.push_new_doc, sync.delete_doc = push_new_doc, delete_doc
    s = S.load(); s.setdefault("false_mirror", {})["convert"] = True; S.save(s)
    first = convert.tick()
    tid = convert.waiting()["book"]["tablet"]
    second = convert.tick()                                # the tablet has not synced: nothing more
    # THE TABLET CONVERTS IT: its PDF and reading settings reach the real mirror, with two pages more than PaperDaemon laid out
    open(os.path.join(mirror, tid + ".pdf"), "wb").write(b"%PDF the tablet's")
    c = json.load(open(os.path.join(mirror, tid + ".content"))); c.update(margins=125, pageCount=4, textScale=1)
    json.dump(c, open(os.path.join(mirror, tid + ".content"), "w"))
    third = convert.tick()
    fc = json.load(open(os.path.join(fm, "book.content")))
    print(json.dumps({"first": first, "second": second, "third": third, "calls": calls, "left": convert.waiting(),
                      "pdf": open(os.path.join(fm, "book.pdf"), "rb").read().decode(), "margins": fc.get("margins"),
                      "pages": fc["pageCount"], "ink_page_kept": fc["cPages"]["pages"][0]["id"],
                      "tablet_copy": sorted(f for f in os.listdir(mirror) if f.startswith(tid))}))
""")


def test_convert_with_the_tablet(tmp_path):
    home = tmp_path / "home"
    fm, mirror = home / "false-mirror", home / "mirror"
    for d in (fm, mirror, home / "false-mirror-state"):
        d.mkdir(parents=True)
    (fm / "book.epub").write_bytes(b"PK the book")
    (fm / "book.metadata").write_text(json.dumps({"visibleName": "A book", "parent": "", "type": "DocumentType"}))
    (fm / "book.content").write_text(json.dumps({"fileType": "epub", "pageCount": 2, "cPages": {"pages": [
        {"id": "ink", "idx": {"value": "ba"}, "redir": {"value": 0}}, {"id": "p2", "idx": {"value": "bb"}, "redir": {"value": 1}}]}}))
    env = dict(os.environ, PAPERDAEMON_HOME=str(home), RM_MIRROR=str(mirror))
    out = subprocess.run([sys.executable, "-c", CONVERT], env=env, capture_output=True, text=True, timeout=300, cwd=ROOT)
    assert out.returncode == 0, out.stderr[-2000:]
    d = json.loads(out.stdout.strip().splitlines()[-1])
    assert d["first"]["sent"] == ["book"] and not d["second"]["sent"] and not d["second"]["back"]
    assert d["calls"][0] == ["push", "ignore", ""]        # to the root of the tablet's library, with the ignore tag
    assert d["third"]["back"] == ["book"] and d["calls"][-1][0] == "delete" and d["left"] == {}
    assert d["pdf"] == "%PDF the tablet's" and d["margins"] == 125
    assert d["pages"] == 4 and d["ink_page_kept"] == "ink"
    assert d["tablet_copy"] == []


HELD = textwrap.dedent("""
    import json, os, time
    from paperdaemon import ledger as S
    from paperdaemon.remarkable import local
    pid = "p1"
    path = os.path.join(S.RM, "nb", pid + ".rm")
    first = S.scan()[0]["state"]["sha"]
    open(path, "ab").write(b"x" * 64)                       # the editor saves a stroke: not synced yet
    held = S.scan()[0]["state"]["sha"]
    time.sleep(0.05); local.sync_request()                   # Ctrl+S
    after = S.scan()[0]["state"]["sha"]
    print(json.dumps({"first": first, "held": held, "after": after}))
""")


def test_the_false_mirror_daemon_sees_ink_as_of_the_last_sync(tmp_path):
    home = tmp_path / "home"
    fm = home / "false-mirror"
    (fm / "nb").mkdir(parents=True)
    (home / "false-mirror-state").mkdir()
    (fm / "nb.metadata").write_text(json.dumps({"visibleName": "Nb", "parent": "", "type": "DocumentType"}))
    (fm / "nb.content").write_text(json.dumps({"fileType": "notebook", "tags": [{"name": "PaperDaemon", "timestamp": 1}],
                                              "cPages": {"pages": [{"id": "p1", "idx": {"value": "ba"}}]}}))
    (fm / "nb" / "p1.rm").write_bytes(b"reMarkable .lines file, version=6          " + b"\0" * 32)
    env = dict(os.environ, PAPERDAEMON_HOME=str(home), RM_MIRROR=str(fm), RM_CACHE=str(fm), RM_LOCAL_ONLY="1",
               RM_STATE=str(home / "false-mirror-state"), RM_TRIGGERS='["PaperDaemon"]')
    out = subprocess.run([sys.executable, "-c", HELD], env=env, capture_output=True, text=True, timeout=300, cwd=ROOT)
    assert out.returncode == 0, out.stderr[-2000:]
    d = json.loads(out.stdout.strip().splitlines()[-1])
    assert d["held"] == d["first"]                         # drawn but not synced: the daemon sees the page as it was
    assert d["after"] != d["first"]                        # synced: it sees the new ink
