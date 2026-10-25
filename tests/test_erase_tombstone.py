"""Erasing as the tablet does: an erased stroke stays in the file as a tombstone (its id and its neighbors' links
kept, its value gone), and no stroke that was not erased changes. Run in a process of its own (the Mirror's place
is read at import)."""
import json
import os
import subprocess
import sys
import textwrap

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def test_an_erased_stroke_is_a_tombstone_and_nothing_else_moves(tmp_path):
    code = textwrap.dedent("""
        import io, json, os, shutil, sys, uuid
        sys.path.insert(0, %r)
        import paperdaemon.pipeline  # noqa: F401
        from paperdaemon import paths
        from paperdaemon.pipeline import TEMPLATES, draw as A, page as P
        from rmscene import read_blocks
        from rmscene import scene_stream as ss
        from rmscene.scene_items import Line
        M = paths.mirror_dir()
        doc, pid = str(uuid.uuid4()), str(uuid.uuid4())
        os.makedirs(os.path.join(M, doc))
        shutil.copyfile(os.path.join(TEMPLATES, "blank-page.rm"), os.path.join(M, doc, pid + ".rm"))
        json.dump({"cPages": {"pages": [{"id": pid, "idx": {"timestamp": "1:2", "value": "ba"}}]}, "fileType": "notebook",
                   "pageCount": 1}, open(os.path.join(M, doc + ".content"), "w"))
        json.dump({"visibleName": "T", "parent": "", "type": "DocumentType"}, open(os.path.join(M, doc + ".metadata"), "w"))
        d = A.Drawing(1620, 2160)
        for x in (-300, 0, 300):
            d.stroke([(x, 400), (x + 100, 500)])
        d.write_rm(doc, 1, keep_existing=True)

        def lines():
            out = {}
            for b in read_blocks(io.BytesIO(open(os.path.join(M, doc, pid + ".rm"), "rb").read())):
                if isinstance(b, ss.SceneLineItemBlock):
                    v = b.item.value
                    out[(b.item.item_id.part1, b.item.item_id.part2)] = (
                        None if v is None else [(round(p.x, 3), round(p.y, 3)) for p in v.points],
                        b.item.left_id, b.item.right_id)
            return out
        before = lines()
        r = P.erase(doc, 1, lambda L: abs(L.points[0].x) < 1)
        after = lines()
        gone = [k for k in before if before[k][0] is not None and after[k][0] is None]
        kept = [k for k in before if before[k][0] is not None and after[k][0] is not None]
        print(json.dumps({"erased": r.get("erased", r.get("hit", None)) if isinstance(r, dict) else None,
                          "gone": len(gone), "same_ids": sorted(before) == sorted(after),
                          "links_kept": all(before[k][1:] == after[k][1:] for k in before),
                          "others_unmoved": all(before[k] == after[k] for k in kept), "kept": len(kept)}))
    """) % ROOT
    env = dict(os.environ, PAPERDAEMON_HOME=str(tmp_path / "home"), PYTHON_KEYRING_BACKEND="keyring.backends.null.Keyring")
    for k in ("RM_STATE", "RM_MIRROR", "RM_CACHE", "RM_RUN"):
        env.pop(k, None)
    out = subprocess.run([sys.executable, "-c", code], env=env, capture_output=True, text=True, timeout=300)
    assert out.returncode == 0, out.stderr[-3000:]
    d = json.loads(out.stdout.strip().splitlines()[-1])
    assert d["gone"] == 1 and d["kept"] == 2 and d["same_ids"] and d["links_kept"] and d["others_unmoved"]


def test_what_a_job_writes_has_paperdaemons_own_author_and_ids(tmp_path):
    """A job's strokes and typed text are written under render.HOST_AUTHOR, numbered on from its own ids and never from
    the tablet's, with the author in the page's table: what the user adds on the tablet meanwhile can never take the
    same ids (a page with two items of one id would not open there)."""
    code = textwrap.dedent("""
        import io, json, os, shutil, sys, uuid
        sys.path.insert(0, %r)
        import paperdaemon.pipeline  # noqa: F401
        from paperdaemon import paths
        from paperdaemon.pipeline import TEMPLATES, draw as A
        from paperdaemon.pipeline.page import render as R, typed as TY
        from rmscene import read_blocks
        from rmscene import scene_stream as ss
        M = paths.mirror_dir()
        doc, pid = str(uuid.uuid4()), str(uuid.uuid4())
        os.makedirs(os.path.join(M, doc))
        shutil.copyfile(os.path.join(TEMPLATES, "blank-page.rm"), os.path.join(M, doc, pid + ".rm"))
        json.dump({"cPages": {"pages": [{"id": pid, "idx": {"timestamp": "1:2", "value": "ba"}}]}, "fileType": "notebook",
                   "pageCount": 1}, open(os.path.join(M, doc + ".content"), "w"))
        json.dump({"visibleName": "T", "parent": "", "type": "DocumentType"}, open(os.path.join(M, doc + ".metadata"), "w"))
        for k in range(2):
            d = A.Drawing(1620, 2160)
            d.stroke([(0, 400 + 100 * k), (100, 500 + 100 * k)])
            d.write_rm(doc, 1, keep_existing=True)
        TY.insert(doc, 1, "an answer")
        from PIL import Image
        from paperdaemon.pipeline.page import images as IM
        png = os.path.join(M, "dot.png"); Image.new("RGB", (8, 8), (200, 0, 0)).save(png)
        pic = IM.insert(doc, 1, png, (-100, 900, 100, 1100))
        pics = [im for im in IM.parse(open(os.path.join(M, doc, pid + ".rm"), "rb").read()) if not im["deleted"]]
        bl = list(read_blocks(io.BytesIO(open(os.path.join(M, doc, pid + ".rm"), "rb").read())))
        lines = [(b.item.item_id.part1, b.item.item_id.part2) for b in bl if isinstance(b, ss.SceneLineItemBlock)]
        tb = next(b for b in bl if isinstance(b, ss.RootTextBlock)).value
        text = [(i.item_id.part1, i.item_id.part2) for i in tb.items.sequence_items()]
        table = list(next(b for b in bl if isinstance(b, ss.AuthorIdsBlock)).author_uuids)
        print(json.dumps({"lines": lines, "text": text, "table": table, "host": R.HOST_AUTHOR,
                          "pic": [list(pic["asset_id"]), list(pic["item_id"])], "pics": len(pics)}))
    """) % ROOT
    env = dict(os.environ, PAPERDAEMON_HOME=str(tmp_path / "home"), PYTHON_KEYRING_BACKEND="keyring.backends.null.Keyring")
    for k in ("RM_STATE", "RM_MIRROR", "RM_CACHE", "RM_RUN"):
        env.pop(k, None)
    out = subprocess.run([sys.executable, "-c", code], env=env, capture_output=True, text=True, timeout=300)
    assert out.returncode == 0, out.stderr[-3000:]
    d = json.loads(out.stdout.strip().splitlines()[-1])
    h = d["host"]
    assert [tuple(x) for x in d["lines"]] == [(h, 1), (h, 2)]
    assert [tuple(x) for x in d["text"]] == [(h, 3)] and h in d["table"]
    assert d["pic"] == [[h, 12], [h, 13]] and d["pics"] == 1      # after the text's ids (3..11), its own
