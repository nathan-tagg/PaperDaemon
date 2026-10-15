import importlib.util
import json
import os
import time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
spec = importlib.util.spec_from_file_location("import_state", os.path.join(ROOT, "tools", "import_state.py"))
imp = importlib.util.module_from_spec(spec)
spec.loader.exec_module(imp)


def write(path, text):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        f.write(text)


def test_import_keeps_newer_files_and_merges_the_ledger(tmp_path):
    src, dst = tmp_path / "old", tmp_path / "new"
    write(str(src / "rm-notepad" / "doc-a.md"), "## old a\n")
    write(str(src / "rm-notepad" / "doc-b.md"), "## old b\n<!-- game-state chess 1\n{}\n-->\n")
    write(str(src / "rm-notepad" / "doc-b" / "scenes" / "001.png"), "png")
    write(str(src / "rm-history" / "doc-a-p01" / "provenance.json"), '{"mine": {}}')
    write(str(src / "rm-pdfdoc" / "calendar.pdf"), "pdf")
    write(str(src / "rm-queue" / "job.json"), "{}")                       # transient: left behind
    write(str(src / "cloud-safety" / "mirror-state.json"), "{}")         # the old mirror's: left behind
    write(str(src / "rm-ledger.json"), json.dumps({"version": 1, "entries": {
        "aaaa/0001": {"status": "done", "completed_at": 100},
        "aaaa/0002": {"status": "working", "claim_owner": "daemon", "claim_at": 300},
        "aaaa/0003": {"status": "done", "completed_at": 50}}}))
    time.sleep(0.05)
    write(str(dst / "rm-notepad" / "doc-a.md"), "## newer in PaperDaemon\n")
    write(str(dst / "rm-ledger.json"), json.dumps({"version": 1, "entries": {
        "aaaa/0003": {"status": "done", "completed_at": 500, "note": "PaperDaemon's"}}}))

    r = imp.run(str(src), str(dst))
    assert r["copied"] == 4 and r["kept"] == 1
    assert (dst / "rm-notepad" / "doc-a.md").read_text() == "## newer in PaperDaemon\n"
    assert "game-state" in (dst / "rm-notepad" / "doc-b.md").read_text()
    assert (dst / "rm-notepad" / "doc-b" / "scenes" / "001.png").is_file()
    assert (dst / "rm-history" / "doc-a-p01" / "provenance.json").is_file()
    assert (dst / "rm-pdfdoc" / "calendar.pdf").is_file()
    assert not (dst / "rm-queue").exists() and not (dst / "cloud-safety").exists()
    led = json.loads((dst / "rm-ledger.json").read_text())["entries"]
    assert led["aaaa/0001"]["status"] == "done"
    assert led["aaaa/0002"]["status"] == "pending" and "claim_owner" not in led["aaaa/0002"]
    assert led["aaaa/0003"]["note"] == "PaperDaemon's"
    assert (r["ledger_added"], r["ledger_kept"]) == (2, 1)


def test_a_dry_run_changes_nothing(tmp_path):
    src, dst = tmp_path / "old", tmp_path / "new"
    write(str(src / "rm-notepad" / "doc-a.md"), "## a\n")
    write(str(src / "rm-ledger.json"), json.dumps({"version": 1, "entries": {"k": {"status": "done"}}}))
    r = imp.run(str(src), str(dst), dry=True)
    assert r["copied"] == 1 and r["ledger_added"] == 1
    assert not (dst / "rm-notepad").exists() and not (dst / "rm-ledger.json").exists()


def test_older_saved_games_are_brought_up_to_the_current_format(tmp_path):
    src, dst = tmp_path / "old", tmp_path / "new"
    state = {"game": "adventure", "id": "a1", "page_id": "p", "title": "The Lighthouse",
             "older_key": {"doc": "d", "page_ids": {"1": "x"}, "sig": "s", "pages": 3},
             "pictures": [{"made_by": "Someone Else", "what": "scene"}, {"made_by": "this system"}]}
    body = json.dumps(state, sort_keys=True, separators=(",", ":"))
    write(str(src / "rm-notepad" / "doc-a.md"), "## 10:00, page id p\n- a turn\n<!-- game-state adventure a1\n%s\n-->\n"
          % body)
    write(str(src / "rm-history" / "doc-a-p01" / "pictures.json"),
          json.dumps({"asset": {"made_by": "Someone Else", "box": [0, 0, 1, 1]}}))
    r = imp.run(str(src), str(dst))
    assert r["migrated"] == 2
    text = (dst / "rm-notepad" / "doc-a.md").read_text(encoding="utf-8")
    got = json.loads(text.split("<!-- game-state adventure a1\n", 1)[1].split("\n-->", 1)[0])
    assert got["journal"] == {"doc": "d", "page_ids": {"1": "x"}, "sig": "s", "pages": 3} and "older_key" not in got
    assert [p["made_by"] for p in got["pictures"]] == ["the user", "this system"]
    assert text.startswith("## 10:00, page id p\n- a turn\n")
    pics = json.loads((dst / "rm-history" / "doc-a-p01" / "pictures.json").read_text())
    assert pics["asset"]["made_by"] == "the user"


def test_a_current_saved_game_is_copied_as_it_is(tmp_path):
    src, dst = tmp_path / "old", tmp_path / "new"
    body = json.dumps({"game": "chess", "id": "c1", "journal": {"doc": "d", "page_ids": {}, "sig": "s"}})
    write(str(src / "rm-notepad" / "doc-c.md"), "<!-- game-state chess c1\n%s\n-->\n" % body)
    r = imp.run(str(src), str(dst))
    assert r["migrated"] == 0
    assert (dst / "rm-notepad" / "doc-c.md").read_text() == (src / "rm-notepad" / "doc-c.md").read_text()
