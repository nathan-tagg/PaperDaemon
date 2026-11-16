"""The Mirror's library changed from the window (add-mirror-library-actions): with Edit the Mirror off every action is
refused; with it on, each is made by the False Mirror's own function on the tablet's library, the items it changes
checked against the cloud and backed up first and pushed after, what it makes sent to the tablet as new, and nothing
written when the tablet changed an item since it was pulled. The cloud is never called: the check and the pushes are
stood in for."""
import json
import os
import shutil

from fastapi.testclient import TestClient

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CASES = os.path.join(ROOT, "tests", "benchmark", "cases")


import pytest


@pytest.fixture(autouse=True)
def _empty_mirror_after():
    """The test session's mirror left empty, as the other tests' fixtures expect it."""
    yield
    from paperdaemon.remarkable import local
    for f in os.listdir(local.M):
        p = os.path.join(local.M, f)
        shutil.rmtree(p, ignore_errors=True) if os.path.isdir(p) else os.remove(p)


def _setup(monkeypatch):
    from paperdaemon import server
    from paperdaemon.remarkable import inplace, local, sync
    src = os.path.join(CASES, "ink-question", "mirror")
    import tempfile                                           # (the test session's own mirror, emptied for each test)
    assert os.path.realpath(local.M).lower().startswith(os.path.realpath(tempfile.gettempdir()).lower())
    for f in os.listdir(local.M):
        p = os.path.join(local.M, f)
        shutil.rmtree(p, ignore_errors=True) if os.path.isdir(p) else os.remove(p)
    for f in os.listdir(src):
        p, dest = os.path.join(src, f), os.path.join(local.M, f)
        (shutil.copytree if os.path.isdir(p) else shutil.copyfile)(p, dest)
    doc = next(f[:-8] for f in os.listdir(src) if f.endswith(".content"))
    cloud = {"newer": False, "asked": [], "edited": [], "new": []}

    def check(name):
        cloud["asked"].append(name)
        if cloud["newer"]:
            raise inplace.TabletNewer("the tablet changed this page")
    monkeypatch.setattr(inplace, "check_cloud", check)
    monkeypatch.setattr(sync, "push_edited", lambda d, pages=None: cloud["edited"].append(d) or {"root_put": 200})
    monkeypatch.setattr(sync, "push_new_doc", lambda d, dry_run=True: cloud["new"].append(d) or {"root_put": 200})
    monkeypatch.setattr(sync, "changed_files", lambda d=None: [])
    monkeypatch.setattr(sync, "pull", lambda *a, **k: None)
    monkeypatch.setattr(sync, "_state", lambda: {"docs": {doc: "h"}, "files": {}})
    inplace.sending()                                         # (nothing left over from another test)
    c = TestClient(server.app)
    c.headers["Authorization"] = "Bearer " + server.pairing_token()
    return c, doc, cloud


def _sent():
    """Once the background sends are done: what did not go."""
    from paperdaemon.remarkable import inplace
    return inplace.sending()


def _meta(u):
    from paperdaemon.remarkable import local
    return json.load(open(os.path.join(local.M, u + ".metadata"), encoding="utf-8"))


def _content(u):
    from paperdaemon.remarkable import local
    return json.load(open(os.path.join(local.M, u + ".content"), encoding="utf-8"))


def test_every_library_action_is_refused_with_edit_the_mirror_off(monkeypatch):
    c, doc, cloud = _setup(monkeypatch)
    A = "/api/v1/library"
    for r in (c.post(A + "/folder", json={"name": "F"}), c.post(A + "/quick-sheets"),
              c.post(A + "/import?name=x", content=b"%PDF-1.4"), c.post(A + "/%s/move" % doc, json={"parent": ""}),
              c.delete(A + "/" + doc), c.put(A + "/%s/tags" % doc, json={"tags": ["a"]}),
              c.post(A + "/%s/pages" % doc, json={}), c.post(A + "/%s/duplicate" % doc),
              c.post(A + "/%s/pages/tags" % doc, json={"pages": [1], "add": ["a"]}),
              c.put(A + "/%s/page/1/tags" % doc, json={"tags": ["a"]})):
        assert r.status_code == 403 and r.json()["reason"] == "off", r.text
    assert _meta(doc).get("parent", "") == "" and not cloud["edited"] and not cloud["new"]


def test_with_edit_the_mirror_on_each_change_is_checked_backed_up_and_sent(monkeypatch):
    from paperdaemon import paths, server
    c, doc, cloud = _setup(monkeypatch)
    monkeypatch.setattr(server, "_mirror_edit", lambda: True)
    A = "/api/v1/library"
    # a folder: made here and sent as new
    r = c.post(A + "/folder", json={"name": "Projects"})
    assert r.status_code == 200, r.text
    folder = r.json()["id"]
    assert r.json()["sending"] is True and _sent() == []
    assert cloud["new"] == [folder] and _meta(folder)["type"] == "CollectionType"
    # the notebook moved into it: its .metadata checked, backed up, changed, pushed
    r = c.post(A + "/%s/move" % doc, json={"parent": folder})
    assert r.status_code == 200 and r.json()["moved"] is True, r.text
    assert _sent() == [] and _meta(doc)["parent"] == folder and cloud["edited"] == [doc]
    assert doc + ".metadata" in cloud["asked"] and doc + ".content" in cloud["asked"]
    assert os.path.isfile(os.path.join(paths.data_dir(), "mirror-backups", doc, doc + ".metadata"))
    # its tags, a new page, a page's tags
    assert c.put(A + "/%s/tags" % doc, json={"tags": ["Luna"]}).status_code == 200
    assert [t["name"] for t in _content(doc)["tags"]] == ["Luna"]
    n0 = _content(doc)["pageCount"] if "pageCount" in _content(doc) else None
    r = c.post(A + "/%s/pages" % doc, json={})
    assert r.status_code == 200 and r.json()["page"] == 2, r.text
    assert c.put(A + "/%s/page/2/tags" % doc, json={"tags": ["ignore"]}).status_code == 200
    assert any(t["name"] == "ignore" for t in _content(doc)["pageTags"])
    # a copy: sent as new
    r = c.post(A + "/%s/duplicate" % doc)
    assert r.status_code == 200 and _sent() == [], r.text
    assert cloud["new"][-1] == r.json()["id"]
    # deleted: into the trash, as the tablet deletes
    r = c.delete(A + "/" + r.json()["id"])
    assert r.status_code == 200 and _meta(cloud["new"][-1])["parent"] == "trash", r.text
    # the tablet changed it since: nothing written, nothing sent
    assert _sent() == []
    cloud["newer"] = True
    sent = list(cloud["edited"])
    r = c.post(A + "/%s/move" % doc, json={"parent": ""})
    assert r.status_code == 409 and r.json()["reason"] == "tablet" and "moved" in r.json()["error"], r.text
    assert _sent() == [] and _meta(doc)["parent"] == folder and cloud["edited"] == sent
    assert n0 is None or n0 >= 1
    # a send that does not go through is said once, by name, and the change stays here
    from paperdaemon.remarkable import sync
    monkeypatch.setattr(sync, "push_new_doc", lambda d, dry_run=True: {"root_put": 412})
    r = c.post(A + "/folder", json={"name": "Later"})
    assert r.status_code == 200 and _meta(r.json()["id"])["visibleName"] == "Later", r.text
    errs = _sent()
    assert len(errs) == 1 and '"Later" was not sent to the tablet' in errs[0] and _sent() == []


def test_a_book_imported_to_the_mirror_is_filed_as_the_desktop_app_files_one(monkeypatch):
    from paperdaemon import server
    from paperdaemon.remarkable import local
    c, _doc, cloud = _setup(monkeypatch)
    monkeypatch.setattr(server, "_mirror_edit", lambda: True)
    from paperdaemon.remarkable import books
    monkeypatch.setattr(books, "lay_out", lambda epub, settings: (None, {"pages": 3}))
    monkeypatch.setattr(books, "settings_of", lambda x: {})
    import io
    import zipfile
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as z:
        z.writestr("mimetype", "application/epub+zip")
    monkeypatch.setattr(books, "spine", lambda z: ["x"])
    r = c.post("/api/v1/library/import?name=My%20book", content=buf.getvalue())
    assert r.status_code == 200, r.text
    u = r.json()["id"]
    con = _content(u)
    assert con["fileType"] == "epub" and con["pageCount"] == 3 and len(con["pages"]) == 3 and "cPages" not in con
    assert _meta(u)["visibleName"] == "My book" and os.path.isfile(os.path.join(local.M, u + ".epub"))
    assert _sent() == [] and cloud["new"] == [u]


def test_a_page_paperdaemon_drew_with_links_answers_them(monkeypatch):
    """11-16: the ink adventure's journal had no links. A notebook page PaperDaemon drew keeps its links beside it, each
    to a page by its id; /links answers them with the page numbers as they are now."""
    from paperdaemon import paths
    from paperdaemon.remarkable import local
    c, doc, cloud = _setup(monkeypatch)
    pid = local.page_id(doc, 1)
    paths.write_json_atomic(paths.own_links_file(doc, pid), {"aspect": 4 / 3.0, "links": [
        {"box": [0.1, 0.2, 0.9, 0.25], "page_id": pid}, {"box": [0.1, 0.3, 0.9, 0.35], "page_id": "gone"}]})
    r = c.get("/api/v1/library/%s/links/1" % doc)
    assert r.status_code == 200 and r.json() == {"aspect": 4 / 3.0, "links": [{"box": [0.1, 0.2, 0.9, 0.25], "go": 1, "uri": None}]}, r.text
