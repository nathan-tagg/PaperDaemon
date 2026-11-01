"""The page pictures: the window draws them (on the graphics card) and hands them back; the engine keeps them, through
updates too, and draws none ahead (its background thread only works out chapters, and ends). A kept picture is always
shown; one whose page has changed since is answered as out of date, so the window draws it again, quietly. Run in a
process of its own (the Mirror's place is read at import)."""
import json
import os
import subprocess
import sys
import textwrap

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

SETUP = """
    import io, json, os, shutil, sys, time, uuid
    sys.path.insert(0, %r)
    from PIL import Image
    from paperdaemon import paths, thumbs
    from paperdaemon.pipeline import TEMPLATES
    from paperdaemon.remarkable import sync
    M = paths.mirror_dir()
    docs = {}
    for name, n in (("A", 3), ("B", 2)):
        doc = str(uuid.uuid4()); docs[name] = doc
        os.makedirs(os.path.join(M, doc))
        ids = [str(uuid.uuid4()) for _ in range(n)]
        for pid in ids:
            shutil.copyfile(os.path.join(TEMPLATES, "blank-page.rm"), os.path.join(M, doc, pid + ".rm"))
        json.dump({"cPages": {"pages": [{"id": p, "idx": {"timestamp": "1:2", "value": "b" + chr(97 + i)}}
                                        for i, p in enumerate(ids)]}, "fileType": "notebook", "pageCount": n},
                  open(os.path.join(M, doc + ".content"), "w"))
        json.dump({"visibleName": name, "parent": "", "type": "DocumentType", "lastOpened": "1"},
                  open(os.path.join(M, doc + ".metadata"), "w"))
    A, B = docs["A"], docs["B"]
    pids = lambda d: [p["id"] for p in json.load(open(os.path.join(M, d + ".content")))["cPages"]["pages"]]
    def webp(w, h=480, color="white"):
        b = io.BytesIO(); Image.new("RGB", (w, h), color).save(b, "WEBP"); return b.getvalue()
    def write_on(d, pid):
        time.sleep(0.02)
        with open(os.path.join(M, d, pid + ".rm"), "ab") as f:
            f.write(b" ")
"""


def _run(tmp_path, body):
    code = textwrap.dedent(SETUP) % ROOT + textwrap.dedent(body)
    env = dict(os.environ, PAPERDAEMON_HOME=str(tmp_path / "home"), PYTHON_KEYRING_BACKEND="keyring.backends.null.Keyring")
    for k in ("RM_STATE", "RM_MIRROR", "RM_CACHE", "RM_RUN"):
        env.pop(k, None)
    out = subprocess.run([sys.executable, "-c", code], env=env, capture_output=True, text=True, timeout=300)
    assert out.returncode == 0, out.stderr[-3000:]
    return json.loads(out.stdout.strip().splitlines()[-1])


def test_pictures_are_kept_through_updates_and_drawn_again_only_when_their_page_changes(tmp_path):
    d = _run(tmp_path, """
        # a picture kept the way the builds before kept them: in a build's own folder, named without the page's ink
        old = os.path.join(paths.cache_dir("pages"), "5f00-faces", A)
        os.makedirs(old)
        p1 = json.load(open(os.path.join(M, A + ".content")))["cPages"]["pages"][0]
        open(os.path.join(old, thumbs._sha(thumbs._what(A, p1)) + "-360-top.webp"), "wb").write(webp(360, color="red"))
        p3 = json.load(open(os.path.join(M, A + ".content")))["cPages"]["pages"][2]
        open(os.path.join(old, thumbs._sha(thumbs._what(A, p3)) + "-360-top.webp"), "wb").write(webp(360))
        write_on(A, p3["id"])                      # written on after it was drawn: out of date
        out = {"before_mirror": thumbs.wake()}
        sync.mirrored = lambda: True
        out["woke"] = thumbs.wake()
        while thumbs.status()["running"]:
            time.sleep(0.1)
        out["ended"] = thumbs._state["thread"] is None
        k1, k3 = thumbs.kept(A, 1, thumbs.THUMB), thumbs.kept(A, 3, thumbs.THUMB)
        out["moved_in"] = [bool(k1["path"]), k1["fresh"], bool(k3["path"]), k3["fresh"]]
        out["red"] = Image.open(k1["path"]).convert("RGB").getpixel((5, 5)) [0] > 200
        thumbs.folder()                            # a new build: its own drawings start afresh, the kept stay
        out["through_a_new_build"] = bool(thumbs.kept(A, 1, thumbs.THUMB)["path"])
        out["drawn_ahead"] = len([f for _, _, fs in os.walk(thumbs.kept_folder()) for f in fs if f.endswith(".webp")])
        k = thumbs.kept(A, 2, thumbs.THUMB)
        out["missing"] = k["path"] is None and len(k["stamp"]) == 16
        thumbs.put(A, 2, thumbs.THUMB, webp(thumbs.THUMB), k["stamp"])
        out["kept"] = thumbs.kept(A, 2, thumbs.THUMB)["fresh"]
        try:
            thumbs.put(A, 2, thumbs.THUMB, b"not a picture"); out["refused"] = False
        except Exception:
            out["refused"] = True
        # its page written on: the picture is still shown, as out of date, until it is drawn again
        asked = thumbs.kept(A, 2, thumbs.THUMB)["stamp"]
        write_on(A, pids(A)[1])
        k = thumbs.kept(A, 2, thumbs.THUMB)
        out["after_an_edit"] = [bool(k["path"]), k["fresh"]]
        thumbs.put(A, 2, thumbs.THUMB, webp(thumbs.THUMB), asked)        # drawn from the page as it was asked for
        out["drawn_from_before_the_edit"] = thumbs.kept(A, 2, thumbs.THUMB)["fresh"]
        thumbs.put(A, 2, thumbs.THUMB, webp(thumbs.THUMB), k["stamp"])
        out["drawn_again"] = thumbs.kept(A, 2, thumbs.THUMB)["fresh"]
        # the cover: the document's one, out of date when it shows another page
        thumbs.put(A, 1, thumbs.COVER, webp(thumbs.COVER, 640), thumbs.kept(A, 1, thumbs.COVER)["stamp"])
        c1, c2 = thumbs.kept(A, 1, thumbs.COVER), thumbs.kept(A, 2, thumbs.COVER)
        out["cover"] = [c1["fresh"], bool(c2["path"]), c2["fresh"]]
        out["other_document"] = thumbs.kept(B, 1, thumbs.THUMB)["path"] is None
        print(json.dumps(out))
    """)
    assert d == {"before_mirror": False, "woke": True, "ended": True, "moved_in": [True, True, True, False], "red": True,
                 "through_a_new_build": True, "drawn_ahead": 2, "missing": True, "kept": True, "refused": True,
                 "after_an_edit": [True, False], "drawn_from_before_the_edit": False, "drawn_again": True,
                 "cover": [True, True, False], "other_document": True}


def test_the_engine_serves_kept_pictures_and_the_page_last_open(tmp_path):
    d = _run(tmp_path, """
        from fastapi.testclient import TestClient
        from paperdaemon import server
        c = TestClient(server.app)
        c.headers["Authorization"] = "Bearer " + server.pairing_token()
        at = lambda: {x["name"]: [x["at_page"], x["cover_page"]] for x in c.get("/api/v1/library").json()}
        out = {"at_first": at()["A"]}
        r = c.get("/api/v1/library/%s/thumb/2.png" % A)
        j = r.json()
        out["missing"] = [r.status_code, j.get("missing"), j.get("page"), j.get("size")]
        r = c.put("/api/v1/library/%s/thumb/2?size=360&from=%s" % (A, j["stamp"]), content=webp(360))
        out["put"] = r.json()
        r = c.get("/api/v1/library/%s/thumb/2.png" % A)
        out["kept"] = [r.status_code, r.headers.get("x-pd-fresh"), r.headers.get("x-pd-page"), r.headers.get("x-pd-size")]
        write_on(A, pids(A)[1])
        r = c.get("/api/v1/library/%s/thumb/2.png" % A)
        out["after_an_edit"] = [r.status_code, r.headers.get("x-pd-fresh"), r.headers.get("x-pd-stamp") != j["stamp"]]
        # the page last open here: the page the document opens at next, and its cover when the tablet says the last
        content = json.load(open(os.path.join(M, A + ".content")))
        content["coverPageNumber"] = -1
        json.dump(content, open(os.path.join(M, A + ".content"), "w"))
        out["opened"] = c.post("/api/v1/library/%s/opened?page=3" % A).json()
        out["at_after"] = at()["A"]
        out["no_such_page"] = c.post("/api/v1/library/%s/opened?page=9" % A).status_code
        out["cover_page"] = c.get("/api/v1/library/%s/cover.png" % A).json().get("page")
        # the tablet opens another page of it: the tablet's page from then on
        content["cPages"]["lastOpened"] = {"timestamp": "1:9", "value": pids(A)[1]}
        json.dump(content, open(os.path.join(M, A + ".content"), "w"))
        out["tablet_after"] = at()["A"]
        out["nothing_in_the_document"] = "lastOpenedPage" not in json.load(open(os.path.join(M, A + ".metadata")))
        print(json.dumps(out))
    """)
    assert d == {"at_first": [1, 1], "missing": [404, True, 2, 360], "put": {"kept": True}, "kept": [200, "1", "2", "360"],
                 "after_an_edit": [200, "0", True], "opened": {"at": 3}, "at_after": [3, 3], "no_such_page": 400,
                 "cover_page": 3, "tablet_after": [2, 2], "nothing_in_the_document": True}
