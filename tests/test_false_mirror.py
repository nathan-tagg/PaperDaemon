"""The false mirror: a library on this computer only. Its edits (remarkable/local.py) refuse outside a local-only
process, a page written from the editor's scene reads back the same, and nothing of it reaches the cloud.

Each check runs in a child Python whose environment is the false mirror's (the modules take where the mirror is when
they are first imported, so this process, whose modules point elsewhere, cannot stand in for it)."""
import json
import os
import subprocess
import sys
import tempfile
import textwrap

import pytest


def _run(code, local=True):
    home = tempfile.mkdtemp(prefix="pd-fm-")
    lib, state = os.path.join(home, "false-mirror"), os.path.join(home, "false-mirror-state")
    os.makedirs(lib)
    os.makedirs(state)
    env = dict(os.environ, PAPERDAEMON_HOME=home, RM_MIRROR=lib, RM_CACHE=lib, RM_STATE=state, PYTHONIOENCODING="utf-8")
    env.pop("RM_LOCAL_ONLY", None)
    if local:
        env["RM_LOCAL_ONLY"] = "1"
    r = subprocess.run([sys.executable, "-c", textwrap.dedent(code)], env=env, capture_output=True, text=True,
                       timeout=300, cwd=os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    assert r.returncode == 0, r.stdout + r.stderr
    return json.loads(r.stdout.strip().splitlines()[-1])


def test_edits_refuse_outside_the_false_mirror():
    got = _run("""
        import json
        from paperdaemon.remarkable import local
        try:
            local.new_notebook("x"); print(json.dumps("made"))
        except local.NotHere:
            print(json.dumps("refused"))
    """, local=False)
    assert got == "refused"


def test_a_page_round_trips_through_the_editor_scene():
    got = _run("""
        import json
        from paperdaemon.remarkable import local, library
        doc = local.new_notebook("Notes")
        scene = local.scene_of(doc, 1)
        assert scene["paperSize"] == [1620, 2160], scene["paperSize"]
        pt = lambda x, y: [x, y, 0, 0, 24, 128]
        scene["layers"] = [
            {"label": "Layer 1", "visible": True, "lines": [{"penCode": 17, "color": 0, "colorRgba": None, "thicknessScale": 3,
                                                           "points": [pt(-200, 400), pt(0, 420), pt(200, 400)]}]},
            {"label": "Layer 2", "visible": False, "lines": [{"penCode": 18, "color": 3, "colorRgba": [255, 195, 140, 255],
                                                            "thicknessScale": 1, "points": [pt(-300, 600), pt(300, 600)]}]}]
        scene["text"] = {"x": -468, "y": 234, "width": 936, "paras": [
            {"style": "title", "list": None, "runs": [{"text": "A title", "bold": False, "italic": False}]},
            {"style": "body", "list": None, "runs": [{"text": "plain ", "bold": False, "italic": False},
                                                     {"text": "bold", "bold": True, "italic": False}]},
            {"style": "body", "list": "number", "runs": [{"text": "first", "bold": False, "italic": False}]},
            {"style": "body", "list": "checked", "runs": [{"text": "done", "bold": False, "italic": True}]}]}
        scene["textVisible"] = False
        n = local.write_scene(doc, 1, scene)
        back = local.scene_of(doc, 1)
        p2 = local.new_page(doc)
        local.set_tags(doc, ["ask", "ask", " "])
        local.set_page_tags(doc, 2, ["todo"])
        c = json.load(open(library.M + "/" + doc + ".content"))
        from paperdaemon.pipeline.page import render as R
        import os, tempfile
        out = os.path.join(tempfile.mkdtemp(), "p.png")
        R.render(doc, 1, out)
        print(json.dumps({"n": n, "back": back, "p2": p2, "tags": [t["name"] for t in c["tags"]],
                          "ptags": [t["name"] for t in c["pageTags"]], "pages": c["pageCount"], "png": os.path.getsize(out)}))
    """)
    assert got["n"] == 2
    b = got["back"]
    assert [L["label"] for L in b["layers"]] == ["Layer 1", "Layer 2"]
    assert [L["visible"] for L in b["layers"]] == [True, False]
    assert b["layers"][1]["lines"][0]["colorRgba"] == [255, 195, 140, 255]
    assert b["layers"][0]["lines"][0]["points"][1][:2] == [0, 420]
    assert b["textVisible"] is False and b["templateVisible"] is True
    t = b["text"]
    assert (t["x"], t["width"]) == (-468, 936)
    assert [(p["style"], p["list"]) for p in t["paras"]] == [("title", None), ("body", None), ("body", "number"), ("body", "checked")]
    assert t["paras"][1]["runs"] == [{"text": "plain ", "bold": False, "italic": False}, {"text": "bold", "bold": True, "italic": False}]
    assert t["paras"][3]["runs"][0]["italic"] is True
    assert got["p2"] == 2 and got["pages"] == 2
    assert got["tags"] == ["ask"] and got["ptags"] == ["todo"]
    assert got["png"] > 0


def test_the_false_mirror_never_reaches_the_cloud():
    got = _run("""
        import json
        from paperdaemon.remarkable import sync
        out = {"mirrored": sync.mirrored(), "push": sync.push_pending()}
        try:
            sync.get_root("x"); out["root"] = "reached"
        except sync.LocalOnly:
            out["root"] = "refused"
        try:
            sync.put_blob("x", b"y", "z"); out["blob"] = "reached"
        except sync.LocalOnly:
            out["blob"] = "refused"
        print(json.dumps(out))
    """)
    assert got == {"mirrored": True, "push": {"pushed": [], "owed": False}, "root": "refused", "blob": "refused"}


def test_one_job_at_a_time_across_processes():
    """The lock a host holds while it works a job: a second holder waits until the first lets go."""
    got = _run("""
        import json, subprocess, sys, time, os
        from paperdaemon import paths
        child = "import time\\nfrom paperdaemon import paths\\nwith paths.one_job():\\n    print('held', flush=True)\\n    time.sleep(2)\\n"
        p = subprocess.Popen([sys.executable, "-c", child], stdout=subprocess.PIPE, text=True, env=os.environ)
        assert p.stdout.readline().strip() == "held"
        t0 = time.time()
        with paths.one_job():
            waited = time.time() - t0
        p.wait()
        print(json.dumps({"waited": waited}))
    """)
    assert got["waited"] > 1.0


def test_the_false_mirror_through_the_engine():
    """Create a false mirror through the API: its own engine starts, the False Mirror tab's requests reach it through
    /fm/..., its edits work there and are refused by the Mirror's engine, and deleting it takes its folders."""
    from fastapi.testclient import TestClient
    from paperdaemon import paths, server
    c = TestClient(server.app)
    c.headers["Authorization"] = "Bearer " + server.pairing_token()
    try:
        r = c.post("/api/v1/false-mirror")
        assert r.status_code == 200 and r.json()["false_mirror"]["exists"]
        assert os.path.isdir(paths.false_mirror_dir()) and os.path.isdir(paths.false_mirror_state_dir())
        lib = c.get("/api/v1/fm/library").json()
        assert [x["name"] for x in lib] == ["Notebook"], lib
        # the Mirror's own engine refuses the false mirror's edits
        assert c.post("/api/v1/library/notebook", json={"name": "no"}).status_code == 404
        folder = c.post("/api/v1/fm/library/folder", json={"name": "Recipes"}).json()["id"]
        doc = c.post("/api/v1/fm/library/notebook", json={"name": "Soup", "parent": folder}).json()["id"]
        assert c.post("/api/v1/fm/library/" + doc + "/pages", json={}).json() == {"page": 2}
        scene = c.get("/api/v1/fm/library/" + doc + "/page/1/scene").json()
        scene["layers"][0]["lines"] = [{"penCode": 15, "color": 0, "thicknessScale": 2,
                                        "points": [[-100, 500, 0, 0, 16, 128], [100, 520, 0, 0, 16, 128]]}]
        assert c.put("/api/v1/fm/library/" + doc + "/page/1/scene", json=scene).json() == {"strokes": 1}
        png = c.get("/api/v1/fm/library/" + doc + "/page/1.png")
        assert png.status_code == 200 and len(png.content) > 100
        assert c.put("/api/v1/fm/library/" + folder + "/tags", json={"tags": ["ask"]}).status_code == 200
        lib = {x["name"]: x for x in c.get("/api/v1/fm/library").json()}
        assert lib["Recipes"]["tags"] == ["ask"] and lib["Soup"]["parent"] == folder and lib["Soup"]["pages"] == 2
        pdf = c.get("/api/v1/fm/library/" + doc + "/export.pdf")
        assert pdf.status_code == 200 and pdf.content.startswith(b"%PDF")
        imported = c.post("/api/v1/fm/library/import?name=Copy&parent=" + folder, content=pdf.content).json()["id"]
        assert c.post("/api/v1/fm/library/" + imported + "/move", json={"parent": ""}).json() == {"moved": True}
        assert c.delete("/api/v1/fm/library/" + doc).json() == {"deleted": True}
        names = sorted(x["name"] for x in c.get("/api/v1/fm/library").json())
        assert names == ["Copy", "Notebook", "Recipes"], names
    finally:
        r = c.delete("/api/v1/false-mirror")
    assert r.status_code == 200 and not r.json()["false_mirror"]["exists"]
    assert not os.path.exists(paths.false_mirror_dir()) and not os.path.exists(paths.false_mirror_state_dir())


def _epub(chapters):
    """A small EPUB 3: its chapters in OEBPS/Text, an image in OEBPS/Images, a nav, a spine."""
    import base64
    import io
    import zipfile
    png = base64.b64decode("iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNkYPhfDwAChwGA60e6kgAAAABJRU5ErkJggg==")
    b = io.BytesIO()
    with zipfile.ZipFile(b, "w") as z:
        z.writestr("mimetype", "application/epub+zip", compress_type=zipfile.ZIP_STORED)
        z.writestr("META-INF/container.xml", '<?xml version="1.0"?><container version="1.0" xmlns="urn:oasis:names:tc:opendocument:xmlns:container">'
                   '<rootfiles><rootfile full-path="OEBPS/content.opf" media-type="application/oebps-package+xml"/></rootfiles></container>')
        items = "".join('<item id="c%d" href="Text/c%d.xhtml" media-type="application/xhtml+xml"/>' % (i, i) for i in range(len(chapters)))
        spine = "".join('<itemref idref="c%d"/>' % i for i in range(len(chapters)))
        z.writestr("OEBPS/content.opf", '<?xml version="1.0"?><package xmlns="http://www.idpf.org/2007/opf" version="3.0" unique-identifier="id">'
                   '<metadata xmlns:dc="http://purl.org/dc/elements/1.1/"><dc:title>Test</dc:title><dc:identifier id="id">x</dc:identifier></metadata>'
                   '<manifest><item id="nav" href="nav.xhtml" properties="nav" media-type="application/xhtml+xml"/>' + items +
                   '<item id="img" href="Images/dot.png" media-type="image/png"/></manifest><spine>' + spine + '</spine></package>')
        z.writestr("OEBPS/nav.xhtml", '<html xmlns="http://www.w3.org/1999/xhtml" xmlns:epub="http://www.idpf.org/2007/ops"><body><nav epub:type="toc"><ol>' +
                   "".join('<li><a href="Text/c%d.xhtml">%s</a></li>' % (i, t) for i, (t, _) in enumerate(chapters)) + "</ol></nav></body></html>")
        for i, (title, text) in enumerate(chapters):
            z.writestr("OEBPS/Text/c%d.xhtml" % i, '<html xmlns="http://www.w3.org/1999/xhtml"><head><title>%s</title></head><body><h1>%s</h1>'
                       '<img src="../Images/dot.png" alt=""/><p>%s</p></body></html>' % (title, title, text))
        z.writestr("OEBPS/Images/dot.png", png)
    return b.getvalue()


@pytest.mark.skipif(not any(os.path.isfile(os.path.join(r, "Microsoft", "Edge", "Application", "msedge.exe"))
                            for r in filter(None, (os.environ.get("ProgramFiles(x86)"), os.environ.get("ProgramFiles")))),
                    reason="laying out a book needs Microsoft Edge")
def test_an_epub_imports_as_the_tablet_files_a_book():
    import base64
    book = _epub([("One", "The first chapter. " * 40), ("Two", "The second chapter. " * 400)])
    got = _run("""
        import base64, json, os
        from paperdaemon.remarkable import local, library
        data = base64.b64decode(%r)
        doc = local.import_file("Test book", data, "")
        c = json.load(open(os.path.join(library.M, doc + ".content")))
        from paperdaemon.pipeline.page import render as R
        kind, path, idx = R.source_page(doc, 2)
        import pypdfium2 as pdfium
        pd = pdfium.PdfDocument(os.path.join(library.M, doc + ".pdf"))
        w, h = pd[0].get_size(); n = len(pd); t1 = pd[0].get_textpage().get_text_range(); last = pd[n - 1].get_textpage().get_text_range()
        pd.close()
        print(json.dumps({"type": c["fileType"], "pages": c["pageCount"], "epub": os.path.getsize(os.path.join(library.M, doc + ".epub")),
                          "kind": kind, "idx": idx, "ratio": h / w, "n": n, "first": t1[:40], "last": last[-60:]}))
    """ % base64.b64encode(book).decode())
    assert got["type"] == "epub" and got["epub"] > 0
    assert got["kind"] == "pdf" and got["idx"] == 1                 # an EPUB's page is drawn from its PDF, as the tablet's
    assert got["n"] == got["pages"] >= 3                            # chapter two starts a page of its own and runs on
    assert abs(got["ratio"] - 4 / 3) < 0.01                         # the Paper Pro's shape
    assert "One" in got["first"] and "second chapter" in got["last"]
