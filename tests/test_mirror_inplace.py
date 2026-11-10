"""A Mirror page written in place (remarkable/inplace.py), as the tablet writes one: what the edit did not touch byte for
byte, an erased stroke a tombstone, new strokes appended under the editor's own author (never the tablet's: an edit
made here and writing the tablet has not yet synced must not take the same ids), typed text edited by its CRDT, anchored ink
left anchored; a stale page and a page the tablet changed refused; each document backed up once.

Every check works on COPIES of the benchmark's fixture pages (and pages the pipeline's own writers make) in a mirror of
its own, in a child Python whose data folder is a temporary one (the Mirror's place is read at import). The cloud is
never called: the check before a write is replaced."""
import json
import os
import subprocess
import sys
import textwrap

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
IP_AUTHOR = 127                               # inplace.AUTHOR: the editor's own, not the tablet's 1, not PaperDaemon's 100kkkkk
CASES = os.path.join(ROOT, "tests", "benchmark", "cases")

PRELUDE = """
import io, json, os, shutil, sys
sys.path.insert(0, %r)
import paperdaemon.pipeline  # noqa: F401
from paperdaemon import paths
from paperdaemon.remarkable import inplace as IP, local, fastrm
from rmscene import read_blocks
from rmscene import scene_stream as ss
from rmscene.tagged_block_common import CrdtId, HEADER_V6
M = paths.mirror_dir()
CLOUD = {"refuse": None}
def check(name):
    if CLOUD["refuse"]:
        raise CLOUD["refuse"]("refused by the stand-in cloud")
IP.check_cloud = check

def fixture(case):
    src = os.path.join(%r, case, "mirror")
    for f in os.listdir(src):
        p = os.path.join(src, f)
        (shutil.copytree if os.path.isdir(p) else shutil.copyfile)(p, os.path.join(M, f))
        if f.endswith(".content"):
            doc = f[:-8]
    return doc

def page_bytes(doc, n=1):
    return open(os.path.join(M, doc, local.page_id(doc, n) + ".rm"), "rb").read()

def frames(data):
    return [data[s:e] for _t, s, e in IP._frames(data)]

def out(**k):
    print(json.dumps(k))
""" % (ROOT, CASES)


def _run(code):
    import tempfile
    home = tempfile.mkdtemp(prefix="pd-inplace-")
    env = dict(os.environ, PAPERDAEMON_HOME=home, PYTHON_KEYRING_BACKEND="keyring.backends.null.Keyring",
               PYTHONIOENCODING="utf-8")
    for k in ("RM_STATE", "RM_MIRROR", "RM_CACHE", "RM_RUN", "RM_LOCAL_ONLY"):
        env.pop(k, None)
    r = subprocess.run([sys.executable, "-c", PRELUDE + textwrap.dedent(code)], env=env, capture_output=True,
                       text=True, timeout=300, cwd=ROOT)
    assert r.returncode == 0, r.stdout[-2000:] + r.stderr[-4000:]
    return json.loads(r.stdout.strip().splitlines()[-1])


def test_read_then_write_with_no_change_leaves_the_file_byte_for_byte():
    got = _run("""
        res = {}
        for case in ("ink-question", "typed-question"):
            doc = fixture(case)
            before = page_bytes(doc)
            scene = IP.read_page(doc, 1)
            w = IP.write_in_place(doc, 1, json.loads(json.dumps(scene)), scene["stamp"])
            # the editor's binary form too: points as the file has them
            s2 = fastrm.scene_from_bytes(fastrm.scene_bytes(IP.read_page(doc, 1, arrays=True)))
            w2 = IP.write_in_place(doc, 1, s2, s2["stamp"])
            res[case] = {"same": page_bytes(doc) == before, "changed": [w["changed"], w2["changed"]],
                         "ids": all(ln.get("id") and ln.get("group") for L in scene["layers"] for ln in L["lines"]),
                         "layer_ids": all(L.get("id") for L in scene["layers"]), "n": sum(len(L["lines"]) for L in scene["layers"]),
                         "backups": os.path.isdir(os.path.join(paths.data_dir(), "mirror-backups", doc))}
        out(**res)
    """)
    for case in ("ink-question", "typed-question"):
        assert got[case]["same"] and got[case]["changed"] == [False, False] and got[case]["layer_ids"], got
        assert got[case]["ids"] and not got[case]["backups"]       # nothing written, nothing backed up
    assert got["ink-question"]["n"] == 70


def test_an_erased_stroke_is_a_tombstone_and_every_other_block_is_as_it_was():
    got = _run("""
        doc = fixture("ink-question")
        before = page_bytes(doc)
        scene = IP.read_page(doc, 1)
        gone = scene["layers"][0]["lines"].pop(5)
        w = IP.write_in_place(doc, 1, scene, scene["stamp"])
        after = page_bytes(doc)
        a, b = frames(before), frames(after)
        diff = [k for k in range(len(a)) if a[k] != b[k]]
        old = list(read_blocks(io.BytesIO(HEADER_V6 + a[diff[0]])))[0]
        new = list(read_blocks(io.BytesIO(HEADER_V6 + b[diff[0]])))[0]
        # the tombstone as rmscene writes one
        from rmscene import write_blocks
        from rmscene.crdt_sequence import CrdtSequenceItem
        buf = io.BytesIO()
        write_blocks(buf, [ss.SceneLineItemBlock(parent_id=old.parent_id, item=CrdtSequenceItem(
            item_id=old.item.item_id, left_id=old.item.left_id, right_id=old.item.right_id, deleted_length=1, value=None))])
        back = local.scene_of(doc, 1)
        out(same_count=len(a) == len(b), diff=len(diff), erased=w["erased"], kept=w["kept"],
            id=[old.item.item_id.part1, old.item.item_id.part2] == gone["id"],
            tomb=new.item.value is None and new.item.deleted_length == 1 and new.item.item_id == old.item.item_id
                 and new.item.left_id == old.item.left_id and new.item.right_id == old.item.right_id,
            as_rmscene=buf.getvalue()[len(HEADER_V6):] == b[diff[0]], lines=sum(len(L["lines"]) for L in back["layers"]),
            backup=open(os.path.join(paths.data_dir(), "mirror-backups", doc, doc, local.page_id(doc, 1) + ".rm"), "rb").read() == before)
    """)
    assert got["same_count"] and got["diff"] == 1 and got["erased"] == 1 and got["kept"] == 69, got
    assert got["id"] and got["tomb"] and got["as_rmscene"] and got["lines"] == 69 and got["backup"]


def test_new_strokes_go_at_the_end_of_their_layer_under_the_editor_s_own_author():
    got = _run("""
        doc = fixture("ink-question")
        before = page_bytes(doc)
        scene = IP.read_page(doc, 1)
        pt = lambda x, y: [x, y, 0, 0, 24, 128]
        L = scene["layers"][0]
        last = L["lines"][-1]["id"]
        L["lines"] += [{"penCode": 17, "color": 0, "colorRgba": None, "thicknessScale": 2.0, "points": [pt(-100, 900), pt(100, 950)]},
                       {"penCode": 18, "color": 9, "colorRgba": [255, 195, 140, 255], "thicknessScale": 1.0,
                        "points": [pt(-200, 1000), pt(0, 1010), pt(200, 1000)]}]
        w = IP.write_in_place(doc, 1, scene, scene["stamp"])
        after = page_bytes(doc)
        bl = list(read_blocks(io.BytesIO(after)))                  # rmscene's own reader
        lines = [b for b in bl if isinstance(b, ss.SceneLineItemBlock)]
        new = lines[-2:]
        highest = max(b.item.item_id.part2 for b in lines[:-2])
        back = local.scene_of(doc, 1)                              # the app's own reader
        bl2 = back["layers"][0]["lines"]
        out(prefix=after.startswith(before), added=w["added"], authors=[b.item.item_id.part1 for b in new],
            after_highest=all(b.item.item_id.part2 > highest for b in new),
            chain=[[b.item.left_id.part1, b.item.left_id.part2] for b in new] == [last, [new[0].item.item_id.part1, new[0].item.item_id.part2]],
            right=[b.item.right_id == CrdtId(0, 0) for b in new], parent=[b.parent_id == CrdtId(*L["id"]) for b in new],
            n=len(bl2), pts=[p[:2] for p in bl2[-1]["points"]], rgba=bl2[-1]["colorRgba"], pen=bl2[-2]["penCode"],
            table=1 in next(b for b in bl if isinstance(b, ss.AuthorIdsBlock)).author_uuids)
    """)
    assert got["prefix"] and got["added"] == 2 and got["authors"] == [IP_AUTHOR, IP_AUTHOR] and got["after_highest"], got
    assert got["chain"] and got["right"] == [True, True] and got["parent"] == [True, True] and got["table"]
    assert got["n"] == 72 and got["pts"] == [[-200, 1000], [0, 1010], [200, 1000]] and got["rgba"] == [255, 195, 140, 255]
    assert got["pen"] == 17


def test_a_cut_stroke_is_a_tombstone_and_its_pieces_new_strokes():
    got = _run("""
        doc = fixture("ink-question")
        scene = IP.read_page(doc, 1)
        L = scene["layers"][0]
        k = max(range(len(L["lines"])), key=lambda i: len(L["lines"][i]["points"]))
        cut = L["lines"][k]
        n = len(cut["points"])
        pieces = [dict(cut, points=cut["points"][:n // 3]), dict(cut, points=cut["points"][2 * n // 3:])]  # the editor's copies
        L["lines"][k:k + 1] = pieces
        w = IP.write_in_place(doc, 1, scene, scene["stamp"])
        bl = list(read_blocks(io.BytesIO(page_bytes(doc))))
        lines = {(b.item.item_id.part1, b.item.item_id.part2): b for b in bl if isinstance(b, ss.SceneLineItemBlock)}
        back = local.scene_of(doc, 1)["layers"][0]["lines"]
        out(erased=w["erased"], added=w["added"], kept=w["kept"], dead=lines[tuple(cut["id"])].item.value is None,
            n=len(back), tail=[[p[:2] for p in ln["points"]] for ln in back[-2:]] == [[p[:2] for p in q["points"]] for q in pieces])
    """)
    assert got == {"erased": 1, "added": 2, "kept": 69, "dead": True, "n": 71, "tail": True}, got


def test_typed_text_is_edited_by_its_crdt_and_kept_characters_keep_their_ids():
    got = _run("""
        from paperdaemon.pipeline.page import typed as TY
        doc = fixture("typed-question")
        def chars(data):
            rec = TY.from_blocks(TY.read_preserved(fastrm.without_strokes(data)), data)
            out_ = []
            for p in rec["paragraphs"]:
                for r in p["runs"]:
                    out_ += list(zip(r["text"], r["character_ids"]))
                out_.append(("\\n", None))
            return out_
        before = page_bytes(doc)
        scene = IP.read_page(doc, 1)
        old_text = [p["runs"] for p in scene["text"]["paras"]]
        p0 = scene["text"]["paras"][0]
        words = p0["runs"][0]["text"].split(" ")
        gone = words.pop(1)
        words.insert(3, "really")
        p0["runs"][0]["text"] = " ".join(words)
        w = IP.write_in_place(doc, 1, scene, scene["stamp"])
        after = page_bytes(doc)
        a, b = chars(before), chars(after)
        back = local.scene_of(doc, 1)["text"]
        ids_a = {i: c for c, i in a if i}
        kept_ids = all(ids_a.get(i) == c for c, i in b if i and i in ids_a)
        fa, fb = frames(before), frames(after)
        changed = [k for k in range(len(fa)) if fa[k] != fb[k]]
        bl = list(read_blocks(io.BytesIO(after)))
        out(text=back["paras"][0]["runs"][0]["text"], want=p0["runs"][0]["text"], rest=[p["runs"] for p in back["paras"][1:]] == old_text[1:],
            kept_ids=kept_ids, new_ids=sorted({i.split(":")[0] for c, i in b if i and i not in ids_a}), report=w["text"],
            changed=[type(list(read_blocks(io.BytesIO(HEADER_V6 + fb[k])))[0]).__name__ for k in changed], same_count=len(fa) == len(fb),
            gone=gone)
    """)
    assert got["text"] == got["want"] and got["rest"] and got["kept_ids"], got
    assert got["new_ids"] == [str(IP_AUTHOR)] and got["report"]["inserted"] == len("really ") and got["report"]["deleted"] == len(got["gone"]) + 1
    assert got["changed"] == ["RootTextBlock"] and got["same_count"]


def test_anchored_ink_stays_anchored_and_untouched():
    got = _run("""
        from rmscene import write_blocks
        from rmscene import scene_items as si
        from rmscene.crdt_sequence import CrdtSequenceItem
        from rmscene.tagged_block_common import LwwValue
        from paperdaemon.pipeline import draw as A
        doc = fixture("typed-question")
        path = os.path.join(M, doc, local.page_id(doc, 1) + ".rm")
        # A GROUP ANCHORED TO THE TEXT, as the tablet files handwriting under a paragraph: its node, its place in Layer 1,
        # two strokes in it; and one plain stroke in the layer
        bl = list(read_blocks(io.BytesIO(open(path, "rb").read())))
        tb = next(b for b in bl if isinstance(b, ss.RootTextBlock))
        first = next(iter(tb.value.items._items.values())).item_id
        hi = A.next_free_id(bl, 1)
        layer = next(b.group.node_id for b in bl if isinstance(b, ss.TreeNodeBlock) and b.group.node_id != CrdtId(0, 1))
        g = si.Group(node_id=CrdtId(1, hi), label=LwwValue(CrdtId(1, hi + 1), ""), visible=LwwValue(CrdtId(1, hi + 2), True),
                     anchor_id=LwwValue(CrdtId(1, hi + 3), CrdtId(first.part1, first.part2 + 3)),
                     anchor_type=LwwValue(CrdtId(1, hi + 3), 2), anchor_threshold=LwwValue(CrdtId(1, hi + 3), 35.748),
                     anchor_origin_x=LwwValue(CrdtId(1, hi + 3), -572.0))
        P = lambda x, y: si.Point(x, y, 0, 0, 24, 128)
        line = lambda pts: si.Line(si.PenColor.BLACK, si.Pen.FINELINER_2, pts, 2.0, 0.0)
        bl += [ss.SceneTreeBlock(tree_id=g.node_id, node_id=CrdtId(0, 0), is_update=True, parent_id=layer),
               ss.TreeNodeBlock(group=g),
               ss.SceneGroupItemBlock(parent_id=layer, item=CrdtSequenceItem(CrdtId(1, hi + 4), CrdtId(0, 0), CrdtId(0, 0), 0, g.node_id)),
               ss.SceneLineItemBlock(parent_id=g.node_id, item=CrdtSequenceItem(CrdtId(1, hi + 5), CrdtId(0, 0), CrdtId(0, 0), 0,
                                                                                line([P(10, 20), P(60, 40)]))),
               ss.SceneLineItemBlock(parent_id=g.node_id, item=CrdtSequenceItem(CrdtId(1, hi + 6), CrdtId(1, hi + 5), CrdtId(0, 0), 0,
                                                                                line([P(80, 20), P(120, 60)]))),
               ss.SceneLineItemBlock(parent_id=layer, item=CrdtSequenceItem(CrdtId(1, hi + 7), CrdtId(1, hi + 4), CrdtId(0, 0), 0,
                                                                            line([P(-300, 1500), P(-200, 1600)])))]
        buf = io.BytesIO(); write_blocks(buf, bl); open(path, "wb").write(buf.getvalue())
        before = page_bytes(doc)
        res = {}
        for form in ("rows", "arrays"):
            sc = IP.read_page(doc, 1, arrays=form == "arrays")
            if form == "arrays":
                sc = fastrm.scene_from_bytes(fastrm.scene_bytes(sc))
            res[form] = IP.write_in_place(doc, 1, sc, sc["stamp"])["changed"]
        scene = IP.read_page(doc, 1)
        lines = scene["layers"][0]["lines"]
        shifted = [ln for ln in lines if tuple(ln["group"]) == (g.node_id.part1, g.node_id.part2)]
        moved = shifted[0]["points"][0][:2] != [10.0, 20.0]
        # erase the plain stroke; cut the second anchored one, its piece naming its group
        plain = next(ln for ln in lines if ln["id"] == [1, hi + 7])
        lines.remove(plain)
        second = shifted[1]
        lines[lines.index(second)] = dict(second, points=second["points"][:1] + [[(a + b) / 2 for a, b in zip(second["points"][0], second["points"][1])]])
        w = IP.write_in_place(doc, 1, scene, scene["stamp"])
        after = page_bytes(doc)
        fa, fb = frames(before), frames(after)
        names = lambda d: [type(list(read_blocks(io.BytesIO(HEADER_V6 + f)))[0]).__name__ for f in d]
        changed = [k for k in range(len(fa)) if fa[k] != fb[k]]
        bl2 = list(read_blocks(io.BytesIO(after)))
        piece = [b for b in bl2 if isinstance(b, ss.SceneLineItemBlock)][-1]
        back = local.scene_of(doc, 1)["layers"][0]["lines"]
        shown = next(ln for ln in back if ln["id"] == [piece.item.item_id.part1, piece.item.item_id.part2])
        out(unchanged=res, moved=moved, erased=w["erased"], added=w["added"], changed=sorted(names([fb[k] for k in changed])),
            piece_group=piece.parent_id == g.node_id, piece_left=piece.item.left_id == CrdtId(1, hi + 6),
            stored=[round(piece.item.value.points[0].x, 3), round(piece.item.value.points[0].y, 3)] == [80.0, 20.0],
            shown=[round(v, 3) for v in shown["points"][0][:2]] == [round(v, 3) for v in second["points"][0][:2]],
            nodes_kept=all(fa[k] == fb[k] for k, n in enumerate(names(fa)) if n in ("TreeNodeBlock", "SceneGroupItemBlock", "SceneTreeBlock")))
    """)
    assert got["unchanged"] == {"rows": False, "arrays": False} and got["moved"], got
    assert got["erased"] == 2 and got["added"] == 1 and got["changed"] == ["SceneLineItemBlock", "SceneLineItemBlock"]
    assert got["piece_group"] and got["piece_left"] and got["stored"] and got["shown"] and got["nodes_kept"]


def test_a_stale_page_and_a_page_the_tablet_changed_are_refused_and_the_backup_is_made_once():
    got = _run("""
        doc = fixture("ink-question")
        original = page_bytes(doc)
        path = os.path.join(M, doc, local.page_id(doc, 1) + ".rm")
        scene = IP.read_page(doc, 1)
        res = {}
        CLOUD["refuse"] = IP.TabletNewer
        s = json.loads(json.dumps(scene)); s["layers"][0]["lines"].pop()
        try:
            IP.write_in_place(doc, 1, s, scene["stamp"]); res["tablet"] = "written"
        except IP.TabletNewer as ex:
            res["tablet"] = ex.reason
        CLOUD["refuse"] = None
        res["untouched"] = page_bytes(doc) == original
        # the first write backs the document up; a second, of the page as PaperDaemon left it, does not again
        w1 = IP.write_in_place(doc, 1, s, scene["stamp"])
        bk = os.path.join(paths.data_dir(), "mirror-backups", doc)
        files = sorted(os.listdir(bk))
        t1 = os.stat(bk).st_mtime_ns
        s2 = IP.read_page(doc, 1); s2["layers"][0]["lines"].pop()
        w2 = IP.write_in_place(doc, 1, s2, s2["stamp"])
        res["backup_once"] = os.stat(bk).st_mtime_ns == t1 and open(os.path.join(bk, doc, local.page_id(doc, 1) + ".rm"), "rb").read() == original
        res["files"] = files
        # a stale stamp: the page changed after the editor read it
        try:
            IP.write_in_place(doc, 1, s2, s2["stamp"]); res["stale"] = "written"
        except IP.StalePage as ex:
            res["stale"] = ex.reason
        # what cannot be written in place is refused: a layer deleted
        s3 = IP.read_page(doc, 1); s3["layers"] = []
        try:
            IP.write_in_place(doc, 1, s3, s3["stamp"]); res["no_layer"] = "written"
        except IP.CannotWrite as ex:
            res["no_layer"] = str(ex)
        # a label changed: the layer's node, a newer value
        s4 = IP.read_page(doc, 1); s4["layers"][0]["label"] = "Sketch"
        b4 = page_bytes(doc)
        IP.write_in_place(doc, 1, s4, s4["stamp"])
        fa, fb = frames(b4), frames(page_bytes(doc))
        res["label"] = [local.scene_of(doc, 1)["layers"][0]["label"], sum(fa[k] != fb[k] for k in range(len(fa)))]
        res["counts"] = [w1["strokes"], w2["strokes"]]
        out(**res)
    """)
    assert got["tablet"] == "tablet" and got["untouched"] and got["backup_once"], got
    assert any(f.endswith(".content") for f in got["files"]) and len(got["files"]) >= 3
    assert got["stale"] == "stale" and "deleting a layer" in got["no_layer"]
    assert got["label"] == ["Sketch", 1] and got["counts"] == [69, 68]


def test_the_cloud_check_reads_the_pages_file_as_the_cloud_holds_it(tmp_path, monkeypatch):
    """sync.cloud_file: one request while the library has not moved; the document's index when it has."""
    import hashlib
    from paperdaemon.remarkable import sync
    blobs = {}

    def put(text):
        h = hashlib.sha256(text.encode()).hexdigest()
        blobs[h] = text.encode()
        return h
    doc, name = "d" * 36, "d" * 36 + "/p.rm"
    di = put("3\n%s:0:%s:0:4\n" % ("a" * 64, name))
    root = put("3\n%s:80000000:%s:1:4\n" % (di, doc))
    state = {"root": root, "generation": 1, "docs": {doc: di}, "files": {name: "a" * 64}}
    monkeypatch.setattr(sync, "SAFETY", str(tmp_path))
    monkeypatch.setattr(sync, "STATE", str(tmp_path / "mirror-state.json"))
    monkeypatch.setattr(sync, "MIRROR", str(tmp_path))
    (tmp_path / "mirror-state.json").write_text(json.dumps(dict(state, checked_against=str(tmp_path))), encoding="utf-8")
    calls = []
    now = {"root": root}
    monkeypatch.setattr(sync, "get_root", lambda t=None: (calls.append("root"), (now["root"], 2))[1])
    monkeypatch.setattr(sync, "get_blob", lambda t, h, f: (calls.append(f), blobs[h])[1])
    assert sync.cloud_file(name, token="x") == ("a" * 64, "a" * 64) and calls == ["root"]
    # the tablet wrote the page: a new document index, a new root
    di2 = put("3\n%s:0:%s:0:5\n" % ("b" * 64, name))
    now["root"] = put("3\n%s:80000000:%s:1:5\n" % (di2, doc))
    assert sync.cloud_file(name, token="x") == ("b" * 64, "a" * 64)


def test_the_editor_reads_and_saves_a_mirror_page_through_the_engine(monkeypatch):
    """The API: a page read with its ids and stamp, saved in place, a stale save and the tablet's newer page answered
    with their reasons, the job ledger told the page as written is PaperDaemon's, and the push handed to the sync."""
    import shutil
    from fastapi.testclient import TestClient
    from paperdaemon import ledger, server
    from paperdaemon.remarkable import inplace, local, sync
    src = os.path.join(CASES, "ink-question", "mirror")
    made = []
    for f in os.listdir(src):
        p, dest = os.path.join(src, f), os.path.join(local.M, f)
        (shutil.copytree if os.path.isdir(p) else shutil.copyfile)(p, dest)
        made.append(dest)
    doc = next(f[:-8] for f in os.listdir(src) if f.endswith(".content"))
    pid = local.page_id(doc, 1)
    try:
        cloud = {"newer": False}

        def check(name):
            assert name == "%s/%s.rm" % (doc, pid)
            if cloud["newer"]:
                raise inplace.TabletNewer("the tablet changed this page")
        monkeypatch.setattr(inplace, "check_cloud", check)
        pushed = []
        monkeypatch.setattr(sync, "push_edited", lambda d, pages=None: pushed.append((d, pages)) or {"root_put": 200})
        monkeypatch.setattr(sync, "changed_files", lambda d=None: [("%s/%s.rm" % (doc, pid), "x", "y")])
        with ledger.locked():
            led = ledger.load()
            led["entries"]["k"] = {"doc_id": doc, "page_id": pid, "status": "done", "handled_sha": "old", "handled_raw": "old"}
            ledger.save(led)
        c = TestClient(server.app)
        c.headers["Authorization"] = "Bearer " + server.pairing_token()
        url = "/api/v1/library/%s/page/1/mirror-scene" % doc
        r = c.get(url)
        assert r.status_code == 200
        scene = r.json()
        assert r.headers["etag"] == scene["stamp"] and scene["layers"][0]["lines"][0]["id"]
        scene["layers"][0]["lines"].pop(0)
        # Edit the Mirror, in Settings, off until the user turns it on: nothing written
        r = c.put(url, json=scene)
        assert r.status_code == 403 and r.json()["reason"] == "off", r.text
        monkeypatch.setattr(server, "_mirror_edit", lambda: True)
        r = c.put(url, json=scene)
        assert r.status_code == 200 and r.json()["erased"] == 1 and r.json()["changed"], r.text
        assert c.put(url, json=scene).json()["reason"] == "stale"
        e = ledger.load()["entries"]["k"]
        assert e["handled_sha"] == ledger.page_state(doc, pid)["sha"]
        fresh_scene = c.get(url + "?form=bin")
        assert fresh_scene.status_code == 200 and fresh_scene.content[:4] == b"PDS1"
        cloud["newer"] = True
        s2 = c.get(url).json()
        s2["layers"][0]["lines"].pop(0)
        r = c.put(url, json=s2)
        assert r.status_code == 409 and r.json()["reason"] == "tablet"
        cloud["newer"] = False
        s2["layers"] = []
        r = c.put(url, json=s2)
        assert r.status_code == 422 and r.json()["reason"] == "cannot"
        assert c.post("/api/v1/library/%s/push" % doc).json() == {"root_put": 200}
        assert pushed == [(doc, [pid])]
    finally:
        for p in made:
            shutil.rmtree(p, ignore_errors=True) if os.path.isdir(p) else os.remove(p)
        with ledger.locked():
            led = ledger.load()
            led["entries"].pop("k", None)
            ledger.save(led)


def test_a_pages_binary_form_is_kept_until_its_files_change(monkeypatch):
    """The editor's binary form of a page, kept by the page's files as they are: asked again, not read again; the page
    written, read anew (both routes: the page to read, and the Mirror's to edit)."""
    import shutil
    from fastapi.testclient import TestClient
    from paperdaemon import server
    from paperdaemon.remarkable import inplace, local
    src = os.path.join(CASES, "ink-question", "mirror")
    made = []
    for f in os.listdir(src):
        p, dest = os.path.join(src, f), os.path.join(local.M, f)
        (shutil.copytree if os.path.isdir(p) else shutil.copyfile)(p, dest)
        made.append(dest)
    doc = next(f[:-8] for f in os.listdir(src) if f.endswith(".content"))
    reads = []
    real_scene, real_page = local.scene_of, inplace.read_page
    monkeypatch.setattr(local, "scene_of", lambda *a, **k: (reads.append("scene"), real_scene(*a, **k))[1])
    monkeypatch.setattr(inplace, "read_page", lambda *a, **k: (reads.append("mirror"), real_page(*a, **k))[1])
    try:
        c = TestClient(server.app)
        c.headers["Authorization"] = "Bearer " + server.pairing_token()
        for route, read in (("scene", "scene"), ("mirror-scene", "mirror")):
            url = "/api/v1/library/%s/page/1/%s?form=bin" % (doc, route)
            a, b = c.get(url), c.get(url)
            assert a.status_code == b.status_code == 200 and a.content == b.content and a.headers["etag"] == b.headers["etag"]
            assert reads.count(read) == 1, (route, reads)                   # read once, the second time kept
            reads.clear()
        path = os.path.join(local.M, doc, local.page_id(doc, 1) + ".rm")
        data = open(path, "rb").read()
        with open(path, "wb") as f:                                           # the page written: its files are not as they were
            f.write(data + b"\0")
        os.utime(path, ns=(os.stat(path).st_atime_ns, os.stat(path).st_mtime_ns + 10 ** 9))
        with open(path, "wb") as f:
            f.write(data)
        c.get("/api/v1/library/%s/page/1/scene?form=bin" % doc)
        assert reads == ["scene"]                                           # its files changed: read anew
    finally:
        for p in made:
            shutil.rmtree(p, ignore_errors=True) if os.path.isdir(p) else os.remove(p)


def test_a_push_stamps_the_pages_written_and_none_when_only_the_documents_settings_changed():
    """touch, before a push: the pages named (every page when none are named) stamped so the tablet fetches them again;
    an empty list stamps none -- a cover changed moves only the document's modified time."""
    got = _run("""
        from paperdaemon.remarkable import sync
        doc = fixture("ink-question")
        cp, mp = os.path.join(M, doc + ".content"), os.path.join(M, doc + ".metadata")
        def stamps():
            c = json.load(open(cp, encoding="utf-8"))
            return [p.get("modifed") for p in c["cPages"]["pages"]], json.load(open(mp, encoding="utf-8")).get("lastModified")
        p0, _m0 = stamps()
        sync.touch(doc, [], when=1000)
        p1, m1 = stamps()
        sync.touch(doc, None, when=2000)
        p2, m2 = stamps()
        out(none=[p1 == p0, m1], every=[all(x == "2000000" for x in p2), m2])
    """)
    assert got == {"none": [True, "1000000"], "every": [True, "2000000"]}


def test_a_mirror_documents_cover_is_set_in_place_and_sent_through_the_engine(monkeypatch):
    """The cover setting of a Mirror document: refused with Edit the Mirror off, written into its .content (every other
    key as it was) after a backup and sent to the tablet, not written over a tablet change, and shown in the library."""
    import shutil
    from fastapi.testclient import TestClient
    from paperdaemon import paths, server
    from paperdaemon.remarkable import inplace, local, sync
    src = os.path.join(CASES, "ink-question", "mirror")
    made = []
    for f in os.listdir(src):
        p, dest = os.path.join(src, f), os.path.join(local.M, f)
        (shutil.copytree if os.path.isdir(p) else shutil.copyfile)(p, dest)
        made.append(dest)
    doc = next(f[:-8] for f in os.listdir(src) if f.endswith(".content"))
    content = os.path.join(local.M, doc + ".content")
    try:
        cloud = {"newer": False, "asked": []}

        def check(name):
            cloud["asked"].append(name)
            if cloud["newer"]:
                raise inplace.TabletNewer("the tablet changed this page")
        monkeypatch.setattr(inplace, "check_cloud", check)
        pushed = []
        monkeypatch.setattr(sync, "push_edited", lambda d, pages=None: pushed.append((d, pages)) or {"root_put": 200})
        monkeypatch.setattr(sync, "changed_files", lambda d=None: [(doc + ".content", "x", "y")])
        was = json.load(open(content, encoding="utf-8"))
        first = "last" if was.get("coverPageNumber") != -1 else "first"     # whichever it is not now
        c = TestClient(server.app)
        c.headers["Authorization"] = "Bearer " + server.pairing_token()
        url = "/api/v1/library/%s/cover" % doc
        r = c.put(url, json={"cover": first})
        assert r.status_code == 403 and r.json()["reason"] == "off", r.text
        monkeypatch.setattr(server, "_mirror_edit", lambda: True)
        r = c.put(url, json={"cover": first})
        assert r.status_code == 200 and r.json() == {"cover": first, "changed": True, "push": {"root_put": 200}}, r.text
        now = json.load(open(content, encoding="utf-8"))
        assert now["coverPageNumber"] == (0 if first == "first" else -1)
        assert {k: v for k, v in now.items() if k != "coverPageNumber"} == {k: v for k, v in was.items() if k != "coverPageNumber"}
        assert cloud["asked"] == [doc + ".content"] and pushed == [(doc, [])]           # no page stamped
        assert os.path.isfile(os.path.join(paths.data_dir(), "mirror-backups", doc, doc + ".content"))
        assert next(x for x in c.get("/api/v1/library").json() if x["id"] == doc)["cover"] == first
        assert c.put(url, json={"cover": first}).json() == {"cover": first, "changed": False}   # as it is: nothing sent
        cloud["newer"] = True
        back = "first" if first == "last" else "last"
        r = c.put(url, json={"cover": back})
        assert r.status_code == 409 and r.json()["reason"] == "tablet" and "cover" in r.json()["error"], r.text
        assert json.load(open(content, encoding="utf-8")) == now and len(pushed) == 1
    finally:
        for p in made:
            shutil.rmtree(p, ignore_errors=True) if os.path.isdir(p) else os.remove(p)


def test_a_mirror_documents_name_is_set_in_place_and_sent_through_the_engine(monkeypatch):
    """The name of a Mirror document: refused with Edit the Mirror off, written into its .metadata (every other key but
    when it changed as it was) after a backup and sent to the tablet, never written over a tablet change."""
    import shutil
    from fastapi.testclient import TestClient
    from paperdaemon import paths, server
    from paperdaemon.remarkable import inplace, local, sync
    src = os.path.join(CASES, "ink-question", "mirror")
    made = []
    for f in os.listdir(src):
        p, dest = os.path.join(src, f), os.path.join(local.M, f)
        (shutil.copytree if os.path.isdir(p) else shutil.copyfile)(p, dest)
        made.append(dest)
    doc = next(f[:-8] for f in os.listdir(src) if f.endswith(".content"))
    meta = os.path.join(local.M, doc + ".metadata")
    try:
        cloud = {"newer": False, "asked": []}

        def check(name):
            cloud["asked"].append(name)
            if cloud["newer"]:
                raise inplace.TabletNewer("the tablet changed this page")
        monkeypatch.setattr(inplace, "check_cloud", check)
        pushed = []
        monkeypatch.setattr(sync, "push_edited", lambda d, pages=None: pushed.append((d, pages)) or {"root_put": 200})
        monkeypatch.setattr(sync, "changed_files", lambda d=None: [(doc + ".metadata", "x", "y")])
        was = json.load(open(meta, encoding="utf-8"))
        c = TestClient(server.app)
        c.headers["Authorization"] = "Bearer " + server.pairing_token()
        url = "/api/v1/library/%s/name" % doc
        r = c.put(url, json={"name": "Field notes"})
        assert r.status_code == 403 and r.json()["reason"] == "off", r.text
        monkeypatch.setattr(server, "_mirror_edit", lambda: True)
        assert c.put(url, json={"name": "  "}).status_code == 400
        r = c.put(url, json={"name": "Field notes"})
        assert r.status_code == 200 and r.json() == {"name": "Field notes", "changed": True, "push": {"root_put": 200}}, r.text
        now = json.load(open(meta, encoding="utf-8"))
        assert now["visibleName"] == "Field notes"
        assert {k: v for k, v in now.items() if k not in ("visibleName", "lastModified")} ==             {k: v for k, v in was.items() if k not in ("visibleName", "lastModified")}
        assert cloud["asked"] == [doc + ".metadata"] and pushed == [(doc, [])]           # no page stamped
        assert os.path.isfile(os.path.join(paths.data_dir(), "mirror-backups", doc, doc + ".metadata"))
        assert c.put(url, json={"name": "Field notes"}).json() == {"name": "Field notes", "changed": False}
        cloud["newer"] = True
        r = c.put(url, json={"name": "Other"})
        assert r.status_code == 409 and r.json()["reason"] == "tablet" and "renamed" in r.json()["error"], r.text
        assert json.load(open(meta, encoding="utf-8")) == now and len(pushed) == 1
    finally:
        for p in made:
            shutil.rmtree(p, ignore_errors=True) if os.path.isdir(p) else os.remove(p)


def test_a_page_the_pipeline_wrote_with_the_daemons_layer_a_picture_and_a_new_layer():
    """A page written by the pipeline's own writers (strokes, typed text, a picture), with a layer of the daemon's: the
    daemon's layer and the picture stay as they are whatever the save says of them, a picture changed is refused, a new
    layer is a new node above the others; and a page with no file yet is made from the blank page it was read as."""
    got = _run("""
        import uuid
        from rmscene import write_blocks
        from rmscene import scene_items as si
        from rmscene.crdt_sequence import CrdtSequenceItem
        from rmscene.tagged_block_common import LwwValue
        from paperdaemon.pipeline import TEMPLATES, draw as A
        from paperdaemon.pipeline.page import typed as TY, images as IM, render as R
        from PIL import Image
        doc, pid, pid2 = str(uuid.uuid4()), str(uuid.uuid4()), str(uuid.uuid4())
        os.makedirs(os.path.join(M, doc))
        shutil.copyfile(os.path.join(TEMPLATES, "blank-page.rm"), os.path.join(M, doc, pid + ".rm"))
        json.dump({"cPages": {"pages": [{"id": pid, "idx": {"timestamp": "1:2", "value": "ba"}},
                                        {"id": pid2, "idx": {"timestamp": "1:2", "value": "bb"}}]},
                   "fileType": "notebook", "pageCount": 2}, open(os.path.join(M, doc + ".content"), "w"))
        json.dump({"visibleName": "T", "parent": "", "type": "DocumentType"}, open(os.path.join(M, doc + ".metadata"), "w"))
        d = A.Drawing(1620, 2160)
        for x in (-300, 0, 300):
            d.stroke([(x, 400), (x + 100, 500)])
        d.write_rm(doc, 1, keep_existing=True)
        TY.insert(doc, 1, "an answer")
        png = os.path.join(M, "dot.png"); Image.new("RGB", (8, 8), (200, 0, 0)).save(png)
        IM.insert(doc, 1, png, (-100, 900, 100, 1100))
        # THE DAEMON'S LAYER, under his old author, with a stroke of his
        path = os.path.join(M, doc, pid + ".rm")
        bl = list(read_blocks(io.BytesIO(open(path, "rb").read())))
        h = CrdtId(R.DAEMON_AUTHOR, 1)
        g = si.Group(node_id=h, label=LwwValue(CrdtId(R.DAEMON_AUTHOR, 2), R.daemon_layer_name()), visible=LwwValue(CrdtId(R.DAEMON_AUTHOR, 3), True))
        stroke = si.Line(si.PenColor.BLACK, si.Pen.FINELINER_2, [si.Point(0, 1800, 0, 0, 24, 128), si.Point(50, 1850, 0, 0, 24, 128)], 2.0, 0.0)
        bl += [ss.SceneTreeBlock(tree_id=h, node_id=CrdtId(0, 0), is_update=True, parent_id=CrdtId(0, 1)),
               ss.TreeNodeBlock(group=g),
               ss.SceneGroupItemBlock(parent_id=CrdtId(0, 1), item=CrdtSequenceItem(CrdtId(R.DAEMON_AUTHOR, 4), CrdtId(0, 0), CrdtId(0, 0), 0, h)),
               ss.SceneLineItemBlock(parent_id=h, item=CrdtSequenceItem(CrdtId(R.DAEMON_AUTHOR, 5), CrdtId(0, 0), CrdtId(0, 0), 0, stroke))]
        buf = io.BytesIO(); write_blocks(buf, [b for b in bl if not isinstance(b, ss.UnreadableBlock)])
        pics = b"".join(open(path, "rb").read()[s:e] for t, s, e in IP._frames(open(path, "rb").read()) if t in (14, 15))
        open(path, "wb").write(buf.getvalue() + pics)
        before = page_bytes(doc)
        scene = IP.read_page(doc, 1)
        res = {"layers": [(L["label"], bool(L.get("daemon"))) for L in scene["layers"]], "pics": len(scene["images"])}
        same = IP.write_in_place(doc, 1, json.loads(json.dumps(scene)), scene["stamp"])
        res["unchanged"] = same["changed"] is False and page_bytes(doc) == before
        # a new layer of the user's with a stroke on it (his layer as it was read: drawing there is
        # test_the_user_draws_on_his_layer_of_a_mirror_page_and_keeps_it)
        pt = lambda x, y: [x, y, 0, 0, 24, 128]
        scene["layers"].append({"label": "Notes", "visible": True,
                                "lines": [{"penCode": 15, "color": 0, "thicknessScale": 2, "points": [pt(-400, 1300), pt(400, 1300)]}]})
        w = IP.write_in_place(doc, 1, scene, scene["stamp"])
        after = page_bytes(doc)
        fa, fb = frames(before), frames(after)
        back = local.scene_of(doc, 1)
        res.update(prefix=after.startswith(before), added=w["added"], erased=w["erased"], new_layers=w["layers"],
                   back=[(L["label"], len(L["lines"]), bool(L.get("daemon"))) for L in back["layers"]], back_pics=len(back["images"]),
                   rm=len(list(read_blocks(io.BytesIO(after)))),
                   on_his=sorted(ln["id"][0] for L in back["layers"] if L.get("daemon") for ln in L["lines"]))
        # PICTURES: one moved (its item a tombstone, a new item at its corners, its asset listed once), one added from a
        # file put beside the page, then that one erased
        s3 = IP.read_page(doc, 1)
        old_id = s3["images"][0]["id"]
        for c in s3["images"][0]["quad"]:
            c[0] += 50
        png2 = os.path.join(M, "dot2.png"); Image.new("RGB", (8, 8), (0, 0, 200)).save(png2)
        added = IP.add_picture(doc, 1, open(png2, "rb").read())
        s3["images"].append({"name": added["name"], "key": "", "quad": [[300, 300], [400, 300], [400, 400], [300, 400]]})
        w3 = IP.write_in_place(doc, 1, s3, s3["stamp"])
        live = [im for im in IM.parse(page_bytes(doc)) if not im["deleted"]]
        s5 = IP.read_page(doc, 1)
        shown = [(p["name"] == added["name"], [round(v) for v in p["quad"][0]], p["id"] != old_id) for p in s5["images"]]
        s5["images"] = [p for p in s5["images"] if p["name"] != added["name"]]
        w5 = IP.write_in_place(doc, 1, s5, s5["stamp"])
        res["picture"] = [w3["pictures"], len(live), sorted(shown), w5["pictures"], len(local.scene_of(doc, 1)["images"]),
                          sorted(IM._deleted_of(body) for bt, body in IM.blocks(page_bytes(doc)) if bt == 15)]
        # A PAGE WITH NO FILE YET: read as the blank page, written from it
        s4 = IP.read_page(doc, 2)
        unchanged = IP.write_in_place(doc, 2, json.loads(json.dumps(s4)), s4["stamp"])["changed"]
        res["none"] = [s4["stamp"], len(s4["layers"]), bool(s4["layers"][0].get("id")), unchanged,
                       os.path.exists(os.path.join(M, doc, pid2 + ".rm"))]
        s4["layers"][0]["lines"].append({"penCode": 15, "color": 0, "thicknessScale": 2, "points": [pt(0, 300), pt(10, 310)]})
        w4 = IP.write_in_place(doc, 1 + 1, s4, s4["stamp"])
        res["made"] = [w4["strokes"], len(local.scene_of(doc, 2)["layers"]), local.scene_of(doc, 2)["layers"][0]["lines"][0]["id"][0]]
        out(**res)
    """)
    # his layer's place ties with Layer 1's at the start of the list, and his higher author sorts it first
    assert [L[1] for L in got["layers"]] == [True, False] and got["layers"][1][0] == "Layer 1", got
    assert got["pics"] == 1 and got["unchanged"], got
    assert got["prefix"] and got["added"] == 1 and got["erased"] == 0 and got["new_layers"] == 1, got
    assert [b[1:] for b in got["back"]] == [[1, True], [3, False], [1, False]] and got["back"][2][0] == "Notes", got
    assert got["on_his"] == [218], got
    assert got["back_pics"] == 1 and got["rm"] > 0
    moved, live, shown, erased, left, dead = got["picture"]
    assert moved == {"erased": 0, "moved": 1, "added": 1} and live == 2, got["picture"]
    assert shown == [[False, [-50, 900], True], [True, [300, 300], True]], got["picture"]
    assert erased == {"erased": 1, "moved": 0, "added": 0} and left == 1 and dead == [0, 1, 1], got["picture"]
    assert got["none"] == ["none", 1, True, False, False] and got["made"] == [1, 1, IP_AUTHOR], got


def test_the_user_draws_on_his_layer_of_a_mirror_page_and_keeps_it():
    """The user's word, 11-07: "let me draw on it and keep my strokes". On a Mirror page his layer takes the user's
    stroke as any layer does (written in place, every other block as it was), and his next note takes only his own. On
    a page from before his byte -- his old note under the tablet's author, or his layer under his old author (218) --
    the save that brings the user's first stroke there lays what the layer held again as his (notes.adopt)."""
    got = _run("""
        import uuid
        from rmscene import write_blocks
        from rmscene import scene_items as si
        from rmscene.crdt_sequence import CrdtSequenceItem
        from rmscene.tagged_block_common import LwwValue
        from paperdaemon.pipeline import TEMPLATES
        from paperdaemon.pipeline.daemon import notes as N
        from paperdaemon.pipeline.page import render as R

        def page(build):
            doc, pid = str(uuid.uuid4()), str(uuid.uuid4())
            os.makedirs(os.path.join(M, doc))
            json.dump({"cPages": {"pages": [{"id": pid, "idx": {"timestamp": "1:2", "value": "ba"}}]}, "fileType": "notebook",
                       "pageCount": 1}, open(os.path.join(M, doc + ".content"), "w"))
            json.dump({"visibleName": "T", "parent": "", "type": "DocumentType"}, open(os.path.join(M, doc + ".metadata"), "w"))
            path = os.path.join(M, doc, pid + ".rm")
            data = build(open(os.path.join(TEMPLATES, "blank-page.rm"), "rb").read())
            open(path, "wb").write(data)
            return doc, path

        def old_layer(author, n, ys):                # his layer as an older version left it, strokes on it
            def build(data):
                bl = list(read_blocks(io.BytesIO(data)))
                h = CrdtId(author, n)
                g = si.Group(node_id=h, label=LwwValue(CrdtId(author, n + 1), R.daemon_layer_name()),
                             visible=LwwValue(CrdtId(author, n + 2), True))
                bl += [ss.SceneTreeBlock(tree_id=h, node_id=CrdtId(0, 0), is_update=True, parent_id=CrdtId(0, 1)),
                       ss.TreeNodeBlock(group=g),
                       ss.SceneGroupItemBlock(parent_id=CrdtId(0, 1), item=CrdtSequenceItem(CrdtId(author, n + 3), CrdtId(0, 0),
                                                                                            CrdtId(0, 0), 0, h))]
                prev = CrdtId(0, 0)
                for k, y in enumerate(ys):
                    line = si.Line(si.PenColor.BLACK, si.Pen.FINELINER_2, [si.Point(0, y, 0, 0, 24, 190), si.Point(50, y, 0, 0, 24, 190)],
                                   3.0, 0.0)
                    iid = CrdtId(author, n + 10 + k)
                    bl.append(ss.SceneLineItemBlock(parent_id=h, item=CrdtSequenceItem(iid, prev, CrdtId(0, 0), 0, line)))
                    prev = iid
                buf = io.BytesIO(); write_blocks(buf, [b for b in bl if not isinstance(b, ss.UnreadableBlock)])
                return buf.getvalue()
            return build

        def a_note(data):
            strokes, _ = N.letter(["Saw it 1:02 PM."], (1620.0, 2160.0))
            return N.with_note(data, strokes, {})

        def his(doc, path):
            bl = list(read_blocks(io.BytesIO(open(path, "rb").read())))
            back = local.scene_of(doc, 1)
            return {"on_his": sorted(ln["id"][0] for L in back["layers"] if L.get("daemon") for ln in L["lines"]),
                    "his_layers": sum(1 for L in back["layers"] if L.get("daemon")), "old_page": bool(R.notes_own_layers(bl))}

        res = {}
        for name, build in (("byte", a_note), ("tablet", old_layer(1, 900, [40, 70])), ("218", old_layer(R.DAEMON_AUTHOR, 1, [40]))):
            doc, path = page(build)
            before = open(path, "rb").read()
            sc = IP.read_page(doc, 1)
            next(L for L in sc["layers"] if L.get("daemon"))["lines"].append(
                {"penCode": 15, "color": 0, "thicknessScale": 2, "points": [[-300, 1700, 0, 0, 24, 128], [300, 1700, 0, 0, 24, 128]]})
            w = IP.write_in_place(doc, 1, sc, sc["stamp"])
            drawn = dict(his(doc, path), added=w["added"], erased=w["erased"], prefix=open(path, "rb").read().startswith(before))
            note, _ = N.letter(["Saw it 1:05 PM."], (1620.0, 2160.0))
            data = N.with_note(open(path, "rb").read(), note, {}); open(path, "wb").write(data)
            res[name] = {"drawn": drawn, "noted": his(doc, path), "note": len(note)}
        out(**res)
    """)
    byte, tablet, old = got["byte"], got["tablet"], got["218"]
    assert byte["drawn"]["prefix"] and byte["drawn"]["added"] == 1 and byte["drawn"]["erased"] == 0, byte
    assert byte["drawn"]["on_his"][0] == IP_AUTHOR and set(byte["drawn"]["on_his"][1:]) == {134} and not byte["drawn"]["old_page"], byte
    assert tablet["drawn"] == {"on_his": [IP_AUTHOR, 134, 134], "his_layers": 1, "old_page": False, "added": 1, "erased": 0, "prefix": False}, tablet
    assert old["drawn"] == {"on_his": [IP_AUTHOR, 134], "his_layers": 1, "old_page": False, "added": 1, "erased": 0, "prefix": False}, old
    for case in (byte, tablet, old):                      # his next note takes his own and leaves the user's stroke
        assert case["noted"] == {"on_his": [IP_AUTHOR] + [134] * case["note"], "his_layers": 1, "old_page": False}, case


def test_a_page_the_c_reader_does_not_cover_is_written_the_same():
    """Where the one C pass does not cover a page, every block is read instead: the same bytes come out."""
    got = _run("""
        doc = fixture("ink-question")
        original = page_bytes(doc)
        path = os.path.join(M, doc, local.page_id(doc, 1) + ".rm")
        scene = IP.read_page(doc, 1)
        scene["layers"][0]["lines"].pop(3)
        pt = lambda x, y: [x, y, 0, 0, 24, 128]
        scene["layers"][0]["lines"].append({"penCode": 17, "color": 0, "thicknessScale": 2.0, "points": [pt(0, 900), pt(50, 950)]})
        fast = IP.edit(doc, 1, original, json.loads(json.dumps(scene)))
        fastrm._c_pass = lambda *a, **k: None
        slow = IP.edit(doc, 1, original, json.loads(json.dumps(scene)))
        out(same=fast[0] == slow[0], done=[fast[1]["erased"], fast[1]["added"], slow[1]["erased"], slow[1]["added"]])
    """)
    assert got == {"same": True, "done": [1, 1, 1, 1]}, got


def test_text_typed_on_a_page_without_any_is_a_new_text_block_and_the_ink_is_kept():
    got = _run("""
        doc = fixture("ink-question")
        before = page_bytes(doc)
        scene = IP.read_page(doc, 1)
        assert scene["text"] is None
        scene["text"] = {"x": -576, "y": 234, "width": 1152, "paras": [
            {"style": "title", "list": None, "runs": [{"text": "Answer", "bold": False, "italic": False}]},
            {"style": "body", "list": None, "runs": [{"text": "four ", "bold": False, "italic": False},
                                                     {"text": "moons", "bold": True, "italic": False}]}]}
        w = IP.write_in_place(doc, 1, scene, scene["stamp"])
        after = page_bytes(doc)
        fa, fb = frames(before), frames(after)
        kinds = [type(list(read_blocks(io.BytesIO(HEADER_V6 + f)))[0]).__name__ for f in fb if f not in fa]
        back = local.scene_of(doc, 1)
        out(kinds=kinds, kept=all(f in fb for f in fa), n=sum(len(L["lines"]) for L in back["layers"]),
            text=[(p["style"], [(r["text"], r["bold"]) for r in p["runs"]]) for p in back["text"]["paras"]], inserted=w["text"]["inserted"])
    """)
    assert got["kinds"] == ["RootTextBlock"] and got["kept"] and got["n"] == 70, got
    assert got["text"] == [["title", [["Answer", False]]], ["body", [["four ", False], ["moons", True]]]]


def test_a_text_whose_items_point_at_each_other_is_shown_and_can_only_be_emptied():
    """The first real collision (a notebook typed in from the app and the tablet within a minute, both numbering as
    author 1) left the text's items in a ring: rmscene's order refuses them. The page's words are still shown, read
    in a loose order and marked as not exact (so nobody takes the page for one without words); an edit of that text
    is refused; and the one edit that needs no order is taken: every character deleted where it stands."""
    got = _run("""
        from rmscene import write_blocks
        from rmscene.crdt_sequence import CrdtSequence, CrdtSequenceItem
        from paperdaemon.pipeline.page import typed as TY
        doc = fixture("typed-question")
        path = os.path.join(M, doc, local.page_id(doc, 1) + ".rm")
        bl = list(read_blocks(io.BytesIO(open(path, "rb").read())))
        tb = next(b for b in bl if isinstance(b, ss.RootTextBlock))
        from rmscene.text import expand_text_item
        items = [e for it in tb.value.items._items.values() for e in expand_text_item(it)]     # a character an item
        a, b = items[0], items[1]
        ring = [CrdtSequenceItem(a.item_id, b.item_id, a.right_id, a.deleted_length, a.value),
                CrdtSequenceItem(b.item_id, a.item_id, b.right_id, b.deleted_length, b.value)] + items[2:]
        tb.value.items = CrdtSequence(ring)
        buf = io.BytesIO(); write_blocks(buf, bl); open(path, "wb").write(buf.getvalue())
        sc = IP.read_page(doc, 1)
        live = lambda: sum(len(i.value) for b in read_blocks(io.BytesIO(open(path, "rb").read())) if isinstance(b, ss.RootTextBlock)
                           for i in b.value.items._items.values() if isinstance(i.value, str) and not i.deleted_length)
        words = "".join(r["text"] for p in sc["text"]["paras"] for r in p["runs"])
        res = dict(inexact=sc["text"].get("inexact"), words=len(words), unread=sc["textUnread"], live_before=live())
        try:
            IP.write_in_place(doc, 1, dict(sc, text=dict(sc["text"], paras=[
                {"style": "body", "list": None, "runs": [{"text": "hello", "bold": False, "italic": False}]}])), sc["stamp"])
            res["refused"] = False
        except IP.CannotWrite as ex:
            res["refused"] = str(ex)
        same = IP.write_in_place(doc, 1, json.loads(json.dumps(sc)), sc["stamp"])          # nothing changed: nothing refused
        w = IP.write_in_place(doc, 1, dict(sc, text=dict(sc["text"], paras=[])), sc["stamp"])
        back = IP.read_page(doc, 1)
        res.update(same=same["changed"], report=w["text"], live_after=live(), unread_after=back["textUnread"],
                   after=[p for p in (back["text"] or {}).get("paras", []) if p["runs"]],
                   strokes=w["kept"] == len(sc["layers"][0]["lines"]))
        out(**res)
    """)
    assert got["inexact"] is True and got["unread"] is False and got["live_before"] > 20, got
    assert got["words"] >= got["live_before"] - 3, got                    # every word is there to be read
    assert "cannot be read exactly" in got["refused"] and got["same"] is False, got
    assert got["report"] == {"kept": 0, "deleted": got["report"]["deleted"], "inserted": 0} and got["report"]["deleted"] >= got["live_before"], got
    assert got["live_after"] == 0 and got["unread_after"] is False and got["after"] == [] and got["strokes"], got


def test_a_value_the_editor_sets_is_stamped_one_past_the_one_it_replaces():
    """A paragraph's style, set here: newer than the style it replaces and no newer than that, under the editor's own
    author. Stamped past every id on the page, it could win a merge against a change the user made on the tablet
    afterwards (the tablet stamps with the page's next item number)."""
    got = _run("""
        doc = fixture("typed-question")
        path = os.path.join(M, doc, local.page_id(doc, 1) + ".rm")
        styles = lambda: {(k.part1, k.part2): (v.timestamp.part1, v.timestamp.part2, int(getattr(v.value, "value", v.value)))
                          for b in read_blocks(io.BytesIO(open(path, "rb").read())) if isinstance(b, ss.RootTextBlock)
                          for k, v in b.value.styles.items()}
        before = styles()
        sc = IP.read_page(doc, 1)
        sc["text"]["paras"][0]["style"] = "header" if sc["text"]["paras"][0]["style"] != "header" else "body"
        IP.write_in_place(doc, 1, sc, sc["stamp"])
        after = styles()
        changed = {k: v for k, v in after.items() if before.get(k) != v}
        out(changed=[[list(k), list(v), list(before.get(k) or [0, 0, 0])] for k, v in changed.items()])
    """)
    assert len(got["changed"]) == 1, got
    key, new, old = got["changed"][0]
    assert key == [0, 0] and new[0] == IP_AUTHOR and new[1] == old[1] + 1, got
