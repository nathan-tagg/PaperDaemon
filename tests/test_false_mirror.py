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
        assert c.put("/api/v1/fm/library/" + doc + "/page/1/scene", json=scene).json()["strokes"] == 1     # and its version
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


def test_an_epub_imports_as_the_desktop_app_files_a_book():
    import base64
    book = _epub([("One", "The first chapter. " * 40), ("Two", "The second chapter. " * 400)])
    got = _run("""
        import base64, json, os
        from paperdaemon.remarkable import local, library, books
        data = base64.b64decode(%r)
        doc = local.import_file("Test book", data, "")
        c = json.load(open(os.path.join(library.M, doc + ".content")))
        from paperdaemon.pipeline.page import render as R
        kind, path, idx = R.source_page(doc, 2)
        import pypdfium2 as pdfium
        pd = pdfium.PdfDocument(path)
        w, h = pd[0].get_size(); n = len(pd)
        pd.close()
        print(json.dumps({"type": c["fileType"], "pages": c["pageCount"], "epub": os.path.getsize(os.path.join(library.M, doc + ".epub")),
                          "pdf_in_mirror": os.path.exists(os.path.join(library.M, doc + ".pdf")),
                          "in_cache": os.path.commonpath([path, os.path.join(os.environ["PAPERDAEMON_HOME"], "cache")]) != "",
                          "kind": kind, "idx": idx, "size": [w, h], "n": n, "margins": c.get("margins"),
                          "redirs": [p["redir"]["value"] for p in c["cPages"]["pages"]]}))
    """ % base64.b64encode(book).decode())
    assert got["type"] == "epub" and got["epub"] > 0
    assert not got["pdf_in_mirror"]                                 # filed as the desktop app files it: no PDF
    assert got["kind"] == "pdf" and got["idx"] == 1                 # drawn from PaperDaemon's own layout, kept in the cache
    assert got["n"] == got["pages"] >= 4                            # chapter two starts a page of its own, and a blank ends it
    assert got["size"] == [445.0, 594.0] and got["margins"] == 125  # the tablet's book page and settings
    assert got["redirs"] == list(range(got["pages"]))


def test_a_pages_pictures_round_trip_through_the_editor_scene():
    """The editor shows and keeps a page's pictures: one added beside the page and placed by a scene (upright, and
    turned) reads back at its corners; a second save keeps them; a scene without one takes it off the page."""
    got = _run("""
        import io, json
        from PIL import Image
        from paperdaemon.remarkable import local
        doc = local.new_notebook("Pictures")
        buf = io.BytesIO(); Image.new("RGB", (40, 20), (200, 30, 30)).save(buf, "PNG")
        a = local.add_picture(doc, 1, buf.getvalue())
        buf = io.BytesIO(); Image.new("RGB", (10, 10), (0, 0, 200)).save(buf, "JPEG")
        b = local.add_picture(doc, 1, buf.getvalue())
        scene = local.scene_of(doc, 1)
        scene["layers"][0]["lines"] = [{"penCode": 17, "color": 0, "colorRgba": None, "thicknessScale": 1,
                                        "points": [[-100, 300, 0, 0, 8, 128], [100, 300, 0, 0, 8, 128]]}]
        up = [[-200, 400], [200, 400], [200, 600], [-200, 600]]
        turned = [[0, 800], [100, 900], [0, 1000], [-100, 900]]
        scene["images"] = [{"name": a["name"], "quad": up}, {"name": b["name"], "quad": turned},
                           {"name": "not-a-picture.png", "quad": up}]
        n = local.write_scene(doc, 1, scene)
        first = local.scene_of(doc, 1)
        local.write_scene(doc, 1, first)
        second = local.scene_of(doc, 1)
        second["images"] = second["images"][1:]
        local.write_scene(doc, 1, second)
        third = local.scene_of(doc, 1)
        try:
            local.add_picture(doc, 1, b"not an image")
            refused = False
        except Exception:
            refused = True
        print(json.dumps({"a": a, "n": n, "first": first["images"], "second": second["images"], "third": third["images"],
                          "strokes": len(third["layers"][0]["lines"]), "refused": refused}))
    """)
    assert got["a"]["width"] == 40 and got["a"]["height"] == 20 and got["a"]["name"].endswith(".png")
    assert got["n"] == 1
    first = got["first"]
    assert [im["name"] for im in first] == [got["a"]["name"], first[1]["name"]] and first[1]["name"].endswith(".jpg")
    assert first[0]["quad"] == [[-200, 400], [200, 400], [200, 600], [-200, 600]]
    assert first[1]["quad"] == [[0, 800], [100, 900], [0, 1000], [-100, 900]]
    assert all(len(im["key"]) == 32 for im in first)
    assert [im["quad"] for im in got["second"]] == [first[1]["quad"]]
    assert [im["name"] for im in got["third"]] == [first[1]["name"]] and got["strokes"] == 1
    assert got["refused"] is True


def test_decompose_and_send_lands_in_the_false_mirrors_quick_sheets_without_an_account():
    # the False Mirror's engine with no reMarkable account and no notebook tagged inbox: Quick sheets takes the page;
    # the Quick sheets button opens on a new page of the same one
    got = _run("""
        import base64, io, json
        from PIL import Image, ImageDraw
        from paperdaemon import studio
        from paperdaemon.remarkable import local
        try:
            studio.send("data:image/png;base64,AA==", 400)
        except ValueError as ex:
            none = "Quick sheets" in str(ex)
        doc, page = local.quick_sheets()
        img = Image.new("RGB", (120, 90), "white")
        ImageDraw.Draw(img).ellipse((20, 15, 100, 75), fill=(30, 30, 30))
        buf = io.BytesIO(); img.save(buf, "PNG")
        sent = studio.send("data:image/png;base64," + base64.b64encode(buf.getvalue()).decode(), 400)
        again = local.quick_sheets()
        print(json.dumps([none, page, sent["sent"], sent["notebooks"], again == (doc, 3)]))
    """)
    assert got == [True, 1, True, 1, True]


def test_a_new_notebook_takes_the_tablets_options():
    got = _run("""
        import json
        from paperdaemon.remarkable import local
        a = local.new_notebook("Plain")
        b = local.new_notebook("Grid", template="P Grid medium", cover="first")
        def look(d):
            c = local._content(d)
            return [c["coverPageNumber"], c["cPages"]["pages"][0]["template"]["value"]]
        print(json.dumps([look(a), look(b)]))
    """)
    assert got == [[-1, "Blank"], [0, "P Grid medium"]]


def test_pages_chosen_are_deleted_duplicated_moved_and_tagged_as_the_tablet_does():
    got = _run("""
        import json, os
        from paperdaemon.remarkable import local
        a = local.new_notebook("A", tags=["Joi"])
        for _ in range(4):
            local.new_page(a)
        b = local.new_notebook("B")
        ids = lambda d: [p["id"] for p in local._live(local._content(d))]
        p = ids(a)
        out = {"tags": [t["name"] for t in local._content(a).get("tags") or []]}
        local.duplicate_pages(a, [2])
        now = ids(a)
        out["dup"] = [len(now), now[:2] == p[:2], now[2] not in p, now[3:] == p[2:]]
        local.move_pages(a, [1, 2], at=5, where="after")            # page 5 of six: the old fourth
        out["moved"] = ids(a)[:4] == [now[2], p[2], p[3], p[0]] and ids(a)[4] == p[1]
        local.move_pages(a, [6], at=1, where="before")
        out["first"] = ids(a)[0] == p[4]
        local.tag_pages(a, [1, 2], add=["Notes"])
        local.tag_pages(a, [1], remove=["notes"])
        pt = local._content(a).get("pageTags") or []
        out["ptags"] = sorted((ids(a).index(t["pageId"]) + 1, t["name"]) for t in pt)
        gone = ids(a)[1]
        local.move_pages(a, [2], to=b)
        out["across"] = [len(ids(a)), ids(b)[-1] == gone, gone not in ids(a), local._content(b)["pageCount"],
                         [t["name"] for t in local._content(b).get("pageTags") or []]]
        local.delete_pages(a, [1, 2])
        out["deleted"] = [len(ids(a)), local._content(a)["pageCount"]]
        try:
            local.delete_pages(a, list(range(1, len(ids(a)) + 1))); out["all"] = "deleted"
        except ValueError:
            out["all"] = "refused"
        c = local.duplicate(a)
        out["copy"] = [local._read(os.path.join(local.M, c + ".metadata"))["visibleName"], ids(c) == ids(a)]
        print(json.dumps(out))
    """)
    assert got["tags"] == ["Joi"]
    assert got["dup"] == [6, True, True, True]
    assert got["moved"] and got["first"]
    assert got["ptags"] == [[2, "Notes"]]
    assert got["across"] == [5, True, True, 2, ["Notes"]]
    assert got["deleted"] == [3, 3]
    assert got["all"] == "refused"
    assert got["copy"] == ["A copy", True]


def test_the_editor_leaves_the_daemons_layer_to_him():
    """The editor shows the daemon's note and saves the page around it: his layer, his strokes and their ids stay his,
    so his next note replaces the last rather than piling on top of a copy he can no longer erase."""
    got = _run("""
        import io, json
        from rmscene import read_blocks, scene_stream as ss, scene_items as si
        from paperdaemon.remarkable import local
        from paperdaemon.pipeline.daemon import notes as N
        a = local.new_notebook("A")
        scene = local.scene_of(a, 1)
        scene["layers"][0]["lines"].append({"pen": "FINELINER_2", "penCode": 17, "color": 0, "thicknessScale": 1.0,
                                            "points": [[0, 900, 0, 0, 16, 190], [60, 950, 0, 0, 16, 190]]})
        local.write_scene(a, 1, scene)
        path = local._rm(a, 1)
        state = {}
        first, _ = N.letter(["Saw it 1:02 PM. Now: read the page"], (1620.0, 2160.0))
        data = N.with_note(open(path, "rb").read(), first, state); open(path, "wb").write(data)
        sc = local.scene_of(a, 1)                                  # the editor opens the page and saves it
        marked = [L["label"] for L in sc["layers"] if L.get("daemon")]
        sc["layers"][[i for i, L in enumerate(sc["layers"]) if not L.get("daemon")][0]]["lines"].append(
            {"pen": "FINELINER_2", "penCode": 17, "color": 0, "thicknessScale": 1.0,
             "points": [[-300, 500, 0, 0, 16, 190], [-250, 520, 0, 0, 16, 190]]})
        local.write_scene(a, 1, sc)
        last, _ = N.letter(["Saw it 1:02 PM. Finished 1:04 PM in 2 min: answered"], (1620.0, 2160.0))
        data = N.with_note(open(path, "rb").read(), last, state); open(path, "wb").write(data)
        bl = list(read_blocks(io.BytesIO(open(path, "rb").read())))
        names = {(b.group.node_id.part1, b.group.node_id.part2): b.group.label.value for b in bl if isinstance(b, ss.TreeNodeBlock)}
        live = [b for b in bl if isinstance(b, ss.SceneLineItemBlock) and isinstance(b.item.value, si.Line)]
        daemon_layers = [k for k, v in names.items() if v == "Daemon"]
        print(json.dumps({"marked": marked, "daemon_layers": len(daemon_layers),
                          "his": sum(1 for b in live if (b.parent_id.part1, b.parent_id.part2) in daemon_layers), "want": len(last),
                          "users": sum(1 for b in live if (b.parent_id.part1, b.parent_id.part2) not in daemon_layers)}))
    """)
    assert got["marked"] == ["Daemon"]
    assert got["daemon_layers"] == 1
    assert got["his"] == got["want"]
    assert got["users"] == 2


def test_what_a_job_writes_is_remembered_as_its_own():
    """The host records the ink it commits as its own, so the next job reads it as this system's work, not the user's.
    (Since 0.1.15 it recorded only with an overflow page: a traced picture of 13,000 strokes was read as the user's,
    searched for an arrowhead, and the model was shown its own answers as requests.)"""
    got = _run("""
        import json
        from paperdaemon.remarkable import local
        from paperdaemon.pipeline import draw as A
        from paperdaemon.pipeline import host as H
        from paperdaemon.pipeline.host import job as J
        from paperdaemon.pipeline.page import marks as M
        from paperdaemon.pipeline.page import render as R
        a = local.new_notebook("A")
        J.begin(doc=a, page=1, page_id=R.live_pages(a)[0]["id"], frame=(1620.0, 2160.0), draw=A.Drawing(),
                ops=["write a word"])
        H.JOB.plan = {"steps": []}
        H.JOB.draw.stroke([(-500, 650), (300, 650)])
        H.JOB.draw.stroke([(-500, 690), (100, 690)])
        res = H.t_commit()
        print(json.dumps({"error": res.get("error"), "owners": sorted(m["owner"] for m in M.marks(a, 1))}))
    """)
    assert got == {"error": None, "owners": ["mine"]}


def test_the_editor_draws_a_group_where_the_tablet_does():
    """A group anchored to the typed text is drawn moved by its anchor, in the editor as in the renderer (both forms of
    the scene). Read at its stored coordinates it sat at the top left, over the text."""
    got = _run("""
        import json
        from paperdaemon.remarkable import local
        from paperdaemon.pipeline.page import render as R
        a = local.new_notebook("A")
        sc = local.scene_of(a, 1)
        sc["layers"][0]["lines"].append({"pen": "FINELINER_2", "penCode": 17, "color": 0, "thicknessScale": 1.0,
                                         "points": [[0, 100, 0, 0, 16, 190], [60, 150, 0, 0, 16, 190]]})
        local.write_scene(a, 1, sc)
        R._anchor_offsets = lambda doc, page, blocks: {b.group.node_id: (210.0, 900.0) for b in blocks
                                                       if type(b).__name__ == "TreeNodeBlock" and b.group.label is not None
                                                       and b.group.label.value == "Layer 1"}
        rows = local.scene_of(a, 1)["layers"][0]["lines"][0]["points"]
        arr = local.scene_of(a, 1, arrays=True)["layers"][0]["lines"][0]["points"]
        print(json.dumps({"rows": [rows[0][:2], rows[1][:2]], "arr": [float(arr["x"][0]), float(arr["y"][0])]}))
    """)
    assert got == {"rows": [[210.0, 1000.0], [270.0, 1050.0]], "arr": [210.0, 1000.0]}


def test_a_page_naming_one_item_twice_still_opens():
    """A layer holding a group and a stroke under one id (an older writer left pages so) opens in the editor whole,
    as the renderer draws it, rather than failing with "Already have item"."""
    got = _run("""
        import io, json, dataclasses
        from rmscene import read_blocks, write_blocks, scene_stream as ss, scene_items as si
        from rmscene.crdt_sequence import CrdtSequenceItem
        from rmscene.scene_stream import CrdtId
        from rmscene.tagged_block_common import LwwValue
        from paperdaemon.remarkable import local
        from paperdaemon.pipeline.page import render as R
        a = local.new_notebook("A")
        sc = local.scene_of(a, 1)
        sc["layers"][0]["lines"].append({"pen": "FINELINER_2", "penCode": 17, "color": 0, "thicknessScale": 1.0,
                                         "points": [[0, 900, 0, 0, 16, 190], [60, 950, 0, 0, 16, 190]]})
        local.write_scene(a, 1, sc)
        path = local._rm(a, 1)
        blocks = list(read_blocks(io.BytesIO(open(path, "rb").read())))
        line = next(b for b in blocks if isinstance(b, ss.SceneLineItemBlock))
        node = CrdtId(1, 900)
        g = si.Group(node_id=node)
        g.label = LwwValue(timestamp=CrdtId(1, 901), value="")
        blocks[-1:-1] = [ss.SceneTreeBlock(tree_id=node, node_id=CrdtId(0, 0), is_update=True, parent_id=line.parent_id),
                         ss.TreeNodeBlock(group=g),
                         ss.SceneGroupItemBlock(parent_id=line.parent_id, item=CrdtSequenceItem(
                             item_id=line.item.item_id, left_id=CrdtId(0, 0), right_id=CrdtId(0, 0), deleted_length=0, value=node))]
        buf = io.BytesIO(); write_blocks(buf, blocks); open(path, "wb").write(buf.getvalue())
        sc = local.scene_of(a, 1)
        print(json.dumps([sum(len(L["lines"]) for L in sc["layers"]), len(R.strokes(a, 1))]))
    """)
    assert got == [1, 1]


def test_a_page_unchanged_is_not_read_again():
    # the editor asks with the version it has: the same page answers 304 and is not read; a write gives the new one
    got = _run("""
        import json
        from fastapi.testclient import TestClient
        from paperdaemon import server
        from paperdaemon.remarkable import local
        doc = local.new_notebook("Notes")
        c = TestClient(server.app); c.headers["Authorization"] = "Bearer " + server.pairing_token()
        url = "/api/v1/library/%s/page/1/scene" % doc
        a = c.get(url); v = a.headers.get("etag")
        same = c.get(url, headers={"If-None-Match": v})
        scene = a.json()
        scene["layers"][0]["lines"] = [{"penCode": 17, "color": 0, "colorRgba": None, "thicknessScale": 2,
                                        "points": [[0, 400, 0, 0, 16, 190], [100, 420, 0, 0, 16, 190]]}]
        w = c.put(url, json=scene).json()
        after = c.get(url, headers={"If-None-Match": v})
        print(json.dumps([a.status_code, bool(v), same.status_code, w["version"] != v, after.status_code, after.headers.get("etag") == w["version"]]))
    """)
    assert got == [200, True, 304, True, 200, True]


def test_a_page_goes_both_ways_in_the_binary_form_as_rmscene_reads_it():
    # the editor's binary form in and out, and the file it writes read by rmscene itself: the same strokes
    got = _run("""
        import io, json
        import numpy as np
        from rmscene import read_blocks
        from rmscene import scene_stream as ss
        from paperdaemon.remarkable import local, fastrm
        doc = local.new_notebook("Notes")
        sc = local.scene_of(doc, 1)
        rows = [[float(i), 400.5 + i, 3, 7, 24 + i % 3, 190] for i in range(50)]
        sc["layers"][0]["lines"] = [{"penCode": 17, "color": 0, "colorRgba": None, "thicknessScale": 2, "points": rows},
                                    {"penCode": 18, "color": 3, "colorRgba": [255, 195, 140, 255], "thicknessScale": 1, "points": rows[:5]}]
        local.write_scene(doc, 1, fastrm.scene_from_bytes(fastrm.scene_bytes(local.scene_of(doc, 1, arrays=True) | {"layers": sc["layers"]})))
        back = fastrm.scene_from_bytes(fastrm.scene_bytes(local.scene_of(doc, 1, arrays=True)))
        lines = back["layers"][0]["lines"]
        ref = [b.item.value for b in read_blocks(io.BytesIO(open(local._rm(doc, 1), "rb").read())) if isinstance(b, ss.SceneLineItemBlock)]
        same = all([[p.x, p.y, p.speed, p.direction, p.width, p.pressure] for p in r.points] ==
                   [[float(q["x"]), float(q["y"]), int(q["speed"]), int(q["direction"]), int(q["width"]), int(q["pressure"])] for q in ln["points"]]
                   for r, ln in zip(ref, lines))
        print(json.dumps([len(lines), len(lines[0]["points"]), lines[1]["colorRgba"], same]))
    """)
    assert got == [2, 50, [255, 195, 140, 255], True]


def test_the_model_reads_the_users_bold_and_italic():
    got = _run("""
        import json
        from paperdaemon.remarkable import local
        from paperdaemon.pipeline.page import typed as TY
        doc = local.new_notebook("Play")
        scene = local.scene_of(doc, 1)
        scene["text"] = {"x": -468, "y": 234, "width": 936, "paras": [
            {"style": "body", "list": None, "runs": [{"text": "She ", "bold": False, "italic": False},
                                                     {"text": "draws her sword", "bold": False, "italic": True},
                                                     {"text": " and says ", "bold": False, "italic": False},
                                                     {"text": "now", "bold": True, "italic": False}]}]}
        local.write_scene(doc, 1, scene)
        _tb, ps = TY.paragraphs(doc, 1)
        print(json.dumps([(p["text"], p["marked"]) for p in ps if p["text"].strip()]))
    """)
    assert got == [["She draws her sword and says now", "She *draws her sword* and says **now**"]]
