"""The page picture cache: filled in the background once the Mirror is built, the thread ending when it is through;
a page is drawn again only when it changed. Run in a process of its own (the Mirror's place is read at import)."""
import json
import os
import subprocess
import sys
import textwrap

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def test_the_filler_draws_every_page_once_then_ends(tmp_path):
    code = textwrap.dedent("""
        import json, os, shutil, sys, time, uuid
        sys.path.insert(0, %r)
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
        first = files()
        out["drawn"], out["ended"] = len(first), thumbs._state["thread"] is None
        # one page changes: only it is drawn again
        pid = json.load(open(os.path.join(M, docs["A"] + ".content")))["cPages"]["pages"][1]["id"]
        time.sleep(0.02)
        with open(os.path.join(M, docs["A"], pid + ".rm"), "ab") as f:
            f.write(b"")
        os.utime(os.path.join(M, docs["A"], pid + ".rm"), None)
        before = thumbs.status()["drawn"]
        thumbs.wake()
        while thumbs.status()["running"]:
            time.sleep(0.1)
        out["redrawn"] = thumbs.status()["drawn"] - before
        out["asked_for"] = os.path.isfile(thumbs.draw(docs["B"], 1, thumbs.THUMB, True))
        print(json.dumps(out))
    """) % ROOT
    env = dict(os.environ, PAPERDAEMON_HOME=str(tmp_path / "home"), PYTHON_KEYRING_BACKEND="keyring.backends.null.Keyring")
    for k in ("RM_STATE", "RM_MIRROR", "RM_CACHE", "RM_RUN"):
        env.pop(k, None)
    out = subprocess.run([sys.executable, "-c", code], env=env, capture_output=True, text=True, timeout=300)
    assert out.returncode == 0, out.stderr[-3000:]
    d = json.loads(out.stdout.strip().splitlines()[-1])
    assert d == {"before_mirror": False, "woke": True, "drawn": 5, "ended": True, "redrawn": 1, "asked_for": True}
