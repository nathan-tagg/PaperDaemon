import json

from paperdaemon.remarkable import sync


def meta(folder, uuid, name, kind, parent):
    (folder / (uuid + ".metadata")).write_text(json.dumps({"visibleName": name, "type": kind, "parent": parent}),
                                               encoding="utf-8")


def test_trash_is_gone(tmp_path):
    meta(tmp_path, "f1", "Old stuff", "CollectionType", "trash")
    meta(tmp_path, "n1", "Inside a trashed folder", "DocumentType", "f1")
    meta(tmp_path, "n2", "Trashed notebook", "DocumentType", "trash")
    meta(tmp_path, "n3", "Kept", "DocumentType", "")
    meta(tmp_path, "f2", "Folder", "CollectionType", "")
    meta(tmp_path, "n4", "Kept too", "DocumentType", "f2")
    names = sorted(n for _, n, _, _ in sync.library(mirror=str(tmp_path)))
    assert names == ["Folder", "Kept", "Kept too"]


def test_a_parent_loop_does_not_hang():
    assert sync.in_trash("a", {"a": "b", "b": "a"}) is False


def test_pulled_page_lists_keep_our_unpushed_pages(tmp_path, monkeypatch):
    monkeypatch.setattr(sync, "MIRROR", str(tmp_path))
    doc = tmp_path / "d"
    doc.mkdir()
    (doc / "ours.rm").write_bytes(b"page")
    ours = {"cPages": {"pages": [{"id": "p1"}, {"id": "p2"}, {"id": "ours"}]}, "pageCount": 3}
    (tmp_path / "d.content").write_text(json.dumps(ours), encoding="utf-8")
    st = {"files": {"d.content": "hash-of-what-the-cloud-had"}}      # our copy differs: an unpushed edit
    theirs = json.dumps({"cPages": {"pages": [{"id": "p2"}, {"id": "p1"}]}, "pageCount": 2}).encode()
    got = json.loads(sync._keep_our_pages("d.content", theirs, st))
    assert [p["id"] for p in got["cPages"]["pages"]] == ["p2", "p1", "ours"] and got["pageCount"] == 3


# ---------------------------------------------------------------- the one sync client, against an in-memory cloud

import hashlib  # noqa: E402

import pytest  # noqa: E402


class FakeCloud:
    """A content-addressed store and a root pointer with a generation, as the sync API keeps them."""

    def __init__(self):
        self.blobs = {}
        tree = "3\n"
        h = sync.index_hash([])
        self.blobs[h] = tree.encode()
        self.root, self.generation = h, 1
        self.uploads = []

    def get_root(self, token=None, _retry=True):
        return self.root, self.generation

    def get_blob(self, token, h, filename):
        return self.blobs[h]

    def put_blob(self, token, data, filename, hash=None):
        h = hash or hashlib.sha256(data).hexdigest()
        self.blobs[h] = data
        self.uploads.append(filename)
        return 200, b"", h

    def put_root(self, token, h, generation, broadcast=True):
        assert generation == self.generation, "the root moved under the push"
        self.root, self.generation = h, self.generation + 1
        return 200, json.dumps({"hash": h, "generation": self.generation}).encode()

    def doc_line(self, doc):
        tree = self.blobs[self.root].decode().splitlines()[1:]
        return next((l for l in tree if l.split(":")[2] == doc), None)


@pytest.fixture
def cloud(tmp_path, monkeypatch):
    fake = FakeCloud()
    mirror, safety = tmp_path / "mirror", tmp_path / "safety"
    mirror.mkdir()
    safety.mkdir()
    monkeypatch.setattr(sync, "MIRROR", str(mirror))
    monkeypatch.setattr(sync, "SAFETY", str(safety))
    monkeypatch.setattr(sync, "STATE", str(safety / "mirror-state.json"))
    monkeypatch.setattr(sync, "user_token", lambda force=False: "token")
    for name in ("get_root", "get_blob", "put_blob", "put_root"):
        monkeypatch.setattr(sync, name, getattr(fake, name))
    fake.mirror = mirror
    return fake


def notebook(mirror, doc, pages=("p1",), picture=False):
    (mirror / (doc + ".metadata")).write_text(json.dumps({"visibleName": "Notes", "type": "DocumentType",
                                                          "parent": ""}), encoding="utf-8")
    (mirror / (doc + ".content")).write_text(json.dumps({"cPages": {"pages": [{"id": p} for p in pages]}}),
                                             encoding="utf-8")
    (mirror / doc).mkdir(exist_ok=True)
    for p in pages:
        (mirror / doc / (p + ".rm")).write_bytes(b"strokes of " + p.encode())
    if picture:
        (mirror / doc / pages[0]).mkdir(exist_ok=True)
        (mirror / doc / pages[0] / "a.png").write_bytes(b"\x89PNG picture")


def test_a_new_notebook_goes_up_in_one_root_move_with_its_pictures(cloud):
    notebook(cloud.mirror, "doc1", ("p1", "p2"), picture=True)
    plan = sync.push_new_doc("doc1", dry_run=True)
    assert plan["dry_run"] and cloud.generation == 1 and not cloud.uploads
    plan = sync.push_new_doc("doc1", dry_run=False)
    assert plan["root_put"] == 200 and cloud.generation == 2
    assert {"doc1.content", "doc1.metadata", "doc1/p1.rm", "doc1/p2.rm", "doc1/p1/a.png"} <= set(cloud.uploads)
    assert cloud.doc_line("doc1") is not None
    assert sync.push_new_doc("doc1", dry_run=False)["error"].startswith("the document already exists")


def test_a_folder_goes_up_as_its_metadata(cloud):
    (cloud.mirror / "fold.metadata").write_text(json.dumps({"visibleName": "Inbox", "type": "CollectionType",
                                                            "parent": ""}), encoding="utf-8")
    assert sync.push_new_doc("fold", dry_run=False)["root_put"] == 200
    assert "fold.metadata" in cloud.uploads and cloud.doc_line("fold")


def test_a_changed_page_goes_up_alone(cloud):
    notebook(cloud.mirror, "doc2", ("p1", "p2"))
    sync.push_new_doc("doc2", dry_run=False)
    before = cloud.doc_line("doc2")
    (cloud.mirror / "doc2" / "p2.rm").write_bytes(b"strokes of p2, answered")
    assert sync.changed_files("doc2")
    cloud.uploads.clear()
    plan = sync.push_doc("doc2", dry_run=False)
    assert plan["root_put"] == 200 and "doc2/p2.rm" in cloud.uploads and "doc2/p1.rm" not in cloud.uploads
    assert cloud.doc_line("doc2") != before
    assert sync.push_doc("doc2", dry_run=False).get("skipped")


def test_the_state_forgets_files_gone_from_the_mirror(cloud):
    notebook(cloud.mirror, "doc4")
    sync._save_state({"root": "r", "generation": 1, "docs": {"doc4": "x", "gone": "y"},
                      "files": {"doc4.content": "a", "gone.content": "b"}})
    st = sync._state()
    assert "gone.content" not in st["files"] and "gone" not in st["docs"] and "doc4" in st["docs"]


def _tablet_writes(cloud, doc, name, data):
    """The tablet uploads a new copy of one file of a document: a new blob, index and root."""
    h = hashlib.sha256(data).hexdigest()
    cloud.blobs[h] = data
    dline = cloud.doc_line(doc).split(":")
    di = cloud.blobs[dline[0]].decode().splitlines()
    files = [l.split(":") for l in di[1:]]
    for f in files:
        if f[2] == name:
            f[0], f[4] = h, str(len(data))
    files = [":".join(f) for f in files]
    dhash = sync.index_hash([l.split(":")[0] for l in files])
    cloud.blobs[dhash] = ("\n".join([di[0]] + files) + "\n").encode()
    dline[0] = dhash
    tree = cloud.blobs[cloud.root].decode().splitlines()
    tree = [tree[0]] + [":".join(dline) if l.split(":")[2] == doc else l for l in tree[1:]]
    root = sync.index_hash([l.split(":")[0] for l in tree[1:]])
    cloud.blobs[root] = ("\n".join(tree) + "\n").encode()
    cloud.root, cloud.generation = root, cloud.generation + 1


def test_a_push_never_sends_back_a_page_the_tablet_changed(cloud):
    notebook(cloud.mirror, "doc5", ("p1", "p2"))
    sync.push_new_doc("doc5", dry_run=False)
    _tablet_writes(cloud, "doc5", "doc5/p1.rm", b"strokes of p1 and the user's new writing")
    (cloud.mirror / "doc5" / "p2.rm").write_bytes(b"strokes of p2, answered")        # our job's edit
    cloud.uploads.clear()
    plan = sync.push_doc("doc5", dry_run=False)
    assert plan["root_put"] == 200 and plan["theirs"] == ["p1.rm"]
    assert "doc5/p2.rm" in cloud.uploads and "doc5/p1.rm" not in cloud.uploads
    # the pull brings the user's page down
    sync.pull()
    assert (cloud.mirror / "doc5" / "p1.rm").read_bytes() == b"strokes of p1 and the user's new writing"
    assert (cloud.mirror / "doc5" / "p2.rm").read_bytes() == b"strokes of p2, answered"


def test_when_both_sides_changed_a_page_the_tablets_wins_and_ours_is_kept(cloud):
    notebook(cloud.mirror, "doc6")
    sync.push_new_doc("doc6", dry_run=False)
    _tablet_writes(cloud, "doc6", "doc6/p1.rm", b"the user's page")
    (cloud.mirror / "doc6" / "p1.rm").write_bytes(b"our unpushed answer")
    cloud.uploads.clear()
    assert sync.push_doc("doc6", dry_run=False).get("theirs") == ["p1.rm"] and not cloud.uploads
    sync.pull()
    assert (cloud.mirror / "doc6" / "p1.rm").read_bytes() == b"the user's page"
    kept = list((cloud.mirror.parent / "safety" / "conflicts").rglob("p1.rm"))
    assert len(kept) == 1 and kept[0].read_bytes() == b"our unpushed answer"


def test_a_page_both_sides_changed_owes_one_conflict_job(cloud):
    fake = lambda c: "-".join(c * n for n in (8, 4, 4, 4, 12))          # an id of the shape the files use
    doc, pid, other = fake("1"), fake("a"), fake("f")
    notebook(cloud.mirror, doc, (pid,))
    sync.push_new_doc(doc, dry_run=False)
    _tablet_writes(cloud, doc, "%s/%s.rm" % (doc, pid), b"the user's page")
    (cloud.mirror / doc / (pid + ".rm")).write_bytes(b"our answer")
    sync.pull()
    owed = sync.pending_conflicts()
    assert list(owed) == ["%s/%s" % (doc, pid)]
    first = owed["%s/%s" % (doc, pid)]["ours"]
    with open(first, "rb") as f:
        assert f.read() == b"our answer"
    sync.record_conflict(doc, pid, "a newer copy")                     # the user wrote again: one per page
    assert len(sync.pending_conflicts()) == 1
    sync.record_conflict(doc, other, "another page")
    got = sync.take_conflict()
    assert got["page_id"] == pid and got["ours"] == "a newer copy"     # the older one first
    assert list(sync.pending_conflicts()) == ["%s/%s" % (doc, other)]


def test_a_set_aside_page_is_read_without_touching_the_mirror():
    from paperdaemon.pipeline.page import render as R
    default = R.page_file("doc", "pid")
    with R.reading("doc", "pid", "C:/elsewhere/pid.rm"):
        assert R.page_file("doc", "pid") == "C:/elsewhere/pid.rm"
        assert R.page_file("doc", "other") != "C:/elsewhere/pid.rm"
    assert R.page_file("doc", "pid") == default


def test_a_pull_that_stops_part_way_carries_on_and_takes_nothing_for_an_edit(cloud, monkeypatch):
    # three notebooks on the tablet; the first pull stops (PaperDaemon quits) after the first one
    for doc in ("docA", "docB", "docC"):
        notebook(cloud.mirror, doc, ("p1", "p2"))
        (cloud.mirror / doc / "p2.rm").write_bytes(b"strokes of p2 in " + doc.encode())   # each notebook its own
        sync.push_new_doc(doc, dry_run=False)
    import shutil
    for f in list(cloud.mirror.iterdir()):                             # a new PC: nothing pulled yet
        shutil.rmtree(f) if f.is_dir() else f.unlink()
    (cloud.mirror.parent / "safety" / "mirror-state.json").unlink()
    real, n = sync._pull_document, [0]

    def stops(*a, **k):
        n[0] += 1
        if n[0] == 2:
            raise ConnectionError("the network dropped")
        return real(*a, **k)
    monkeypatch.setattr(sync, "_pull_document", stops)
    with pytest.raises(ConnectionError):
        sync.pull()
    monkeypatch.setattr(sync, "_pull_document", real)
    done = json.load(open(sync.STATE, encoding="utf-8"))
    assert len(done["docs"]) == 1                                      # the finished notebook was kept
    got = sync.pull()                                                  # the next pull carries on
    assert got["changed"] and not list((cloud.mirror.parent / "safety").glob("conflicts/*"))
    assert sync.pending_conflicts() == {} and sync.changed_files() == []
    assert sync.pull()["changed"] is False                             # and the mirror is complete
    for doc in ("docA", "docB", "docC"):
        assert (cloud.mirror / doc / "p2.rm").read_bytes() == b"strokes of p2 in " + doc.encode()


def test_files_a_stopped_pull_left_are_recorded_not_fetched_again(cloud):
    notebook(cloud.mirror, "docD")
    sync.push_new_doc("docD", dry_run=False)
    (cloud.mirror.parent / "safety" / "mirror-state.json").unlink()   # the record lost, the files still here
    got = sync.pull()
    assert got["downloaded"] == [] and not list((cloud.mirror.parent / "safety").glob("conflicts/*"))
