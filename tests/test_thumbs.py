"""The page picture cache: the window draws the pictures (on the graphics card) and hands them back; the engine keeps
them, draws none ahead (its background thread only works out chapters, and ends), keeps a picture through edits to its
page, and forgets it when the page is opened. Run in a process of its own (the Mirror's place is read at import)."""
import json
import os
import subprocess
import sys
import textwrap

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def test_pictures_are_kept_until_their_page_is_opened_and_none_are_drawn_ahead(tmp_path):
    code = textwrap.dedent("""
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
        out = {"before_mirror": thumbs.wake()}
        sync.mirrored = lambda: True
        out["woke"] = thumbs.wake()
        while thumbs.status()["running"]:
            time.sleep(0.1)
        files = lambda: sorted(os.path.join(dp, f) for dp, _, fs in os.walk(thumbs.folder()) for f in fs)
        out["drawn_ahead"], out["ended"] = len(files()), thumbs._state["thread"] is None
        A = docs["A"]
        out["missing"] = thumbs.cached(A, 2, thumbs.THUMB) is None
        # the window's drawing, kept
        b = io.BytesIO(); Image.new("RGB", (thumbs.THUMB, 480), "white").save(b, "WEBP")
        thumbs.put(A, 2, thumbs.THUMB, b.getvalue())
        out["kept"] = thumbs.cached(A, 2, thumbs.THUMB) is not None
        try:
            thumbs.put(A, 2, thumbs.THUMB, io.BytesIO(b"not a picture").getvalue()); out["refused"] = False
        except Exception:
            out["refused"] = True
        # its page written on: the picture stays until the page is opened
        pid = json.load(open(os.path.join(M, A + ".content")))["cPages"]["pages"][1]["id"]
        time.sleep(0.02)
        with open(os.path.join(M, A, pid + ".rm"), "ab") as f:
            f.write(b"")
        os.utime(os.path.join(M, A, pid + ".rm"), None)
        out["kept_through_an_edit"] = thumbs.cached(A, 2, thumbs.THUMB) is not None
        out["forgotten"] = thumbs.forget(A, 2)
        out["missing_after_open"] = thumbs.cached(A, 2, thumbs.THUMB) is None
        print(json.dumps(out))
    """) % ROOT
    env = dict(os.environ, PAPERDAEMON_HOME=str(tmp_path / "home"), PYTHON_KEYRING_BACKEND="keyring.backends.null.Keyring")
    for k in ("RM_STATE", "RM_MIRROR", "RM_CACHE", "RM_RUN"):
        env.pop(k, None)
    out = subprocess.run([sys.executable, "-c", code], env=env, capture_output=True, text=True, timeout=300)
    assert out.returncode == 0, out.stderr[-3000:]
    d = json.loads(out.stdout.strip().splitlines()[-1])
    assert d == {"before_mirror": False, "woke": True, "drawn_ahead": 0, "ended": True, "missing": True, "kept": True,
                 "refused": True, "kept_through_an_edit": True, "forgotten": 1, "missing_after_open": True}
