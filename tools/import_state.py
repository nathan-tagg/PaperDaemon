"""Import an existing pipeline state folder into PaperDaemon's data folder, so notebooks continue where
they were: their notepads (with any game in progress), the page history with its provenance and picture
records, staged documents, and the ledger of pages already answered.

    uv run python tools/import_state.py <state folder> [--to <data folder>] [--dry-run]

The data folder defaults to PaperDaemon's own (PAPERDAEMON_HOME, else %APPDATA%\\PaperDaemon). Nothing is
overwritten that is newer in PaperDaemon's copy:
  - files are copied when PaperDaemon has none, or has an older one;
  - the ledger is merged entry by entry, the more recently active entry winning; a page the old daemon
    was still working on is imported as pending, so PaperDaemon's daemon picks it up again.

What is imported (paths relative to the state folder):
  rm-ledger.json         the ledger: every page seen, its status and what was done
  rm-notepad/            each notebook's notepad (<doc>.md, game states inside it) and its folders
                         (scenes and portraits of a game, pictures, residents)
  rm-history/            per page: snapshots before each change, provenance.json (which strokes are
                         PaperDaemon's), pictures.json (the pictures placed on the page)
  rm-pdfdoc/             documents staged for the tablet
What is left behind: the queue, logs, locks and backups (transient), and cloud-safety/ (the old mirror's
sync state, which would not match PaperDaemon's own mirror), and any secrets.

Older states are brought up to the current format on the way in:
  - an adventure's journal record (the staged journal document: {doc, page_ids, sig, pages}) is kept
    under the key "journal"; a saved game that keeps it under another key has it moved there;
  - a "made_by" value is "this system" for what PaperDaemon made and "the user" for everything else, so
    any other value (a person's name) becomes "the user".
"""
import argparse
import json
import os
import re
import shutil
import sys

FOLDERS = ("rm-notepad", "rm-history", "rm-pdfdoc")
LEDGER = "rm-ledger.json"
GAME_STATE = re.compile(r"(<!-- game-state (\w+) (\S+)\n)(.*?)(\n-->)", re.S)
JOURNAL_KEYS = {"doc", "page_ids", "sig"}
MADE_BY_KEPT = {"this system", "the user"}


def _made_by(v):
    """Every made_by value that is not PaperDaemon's own becomes "the user". -> (value, changes)."""
    n = 0
    if isinstance(v, dict):
        out = {}
        for k, x in v.items():
            if k == "made_by" and isinstance(x, str) and x not in MADE_BY_KEPT:
                out[k] = "the user"
                n += 1
            else:
                out[k], m = _made_by(x)
                n += m
        return out, n
    if isinstance(v, list):
        out = []
        for x in v:
            y, m = _made_by(x)
            out.append(y)
            n += m
        return out, n
    return v, 0


def migrate_game(game, state):
    """A saved game in the current format. -> (state, changes)."""
    n = 0
    if game == "adventure" and isinstance(state, dict) and "journal" not in state:
        for k, v in list(state.items()):
            if isinstance(v, dict) and JOURNAL_KEYS <= set(v):
                state["journal"] = state.pop(k)
                n += 1
                break
    state, m = _made_by(state)
    return state, n + m


def migrate_notepad(text):
    """A notepad's text with every saved game in it migrated. -> (text, changes)."""
    total = [0]

    def one(m):
        try:
            state = json.loads(m.group(4))
        except ValueError:
            return m.group(0)
        state, n = migrate_game(m.group(2), state)
        if not n:
            return m.group(0)
        total[0] += n
        body = json.dumps(state, ensure_ascii=False, sort_keys=True, separators=(",", ":")).replace("-->", "--\\u003e")
        return m.group(1) + body + m.group(5)
    return GAME_STATE.sub(one, text), total[0]


def _migrated(path):
    """The bytes to write for a source file, migrated when its format calls for it; None to copy as is."""
    low = path.lower()
    try:
        if low.endswith(".md"):
            with open(path, encoding="utf-8") as f:
                text, n = migrate_notepad(f.read())
            return text.encode("utf-8") if n else None
        if low.endswith(".json"):
            with open(path, encoding="utf-8") as f:
                d = json.load(f)
            d, n = _made_by(d)
            return json.dumps(d, ensure_ascii=False, indent=2).encode("utf-8") if n else None
    except (OSError, ValueError, UnicodeDecodeError):
        return None
    return None


def data_dir():
    sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    from paperdaemon import paths
    return paths.data_dir()


def _newer(src, dst):
    """True when src should replace dst: dst is missing, or older."""
    try:
        return os.path.getmtime(src) > os.path.getmtime(dst)
    except OSError:
        return True


def copy_tree(src_root, dst_root, dry, report):
    for folder, _dirs, files in os.walk(src_root):
        rel = os.path.relpath(folder, src_root)
        target = os.path.normpath(os.path.join(dst_root, rel))
        for n in files:
            if n.endswith((".tmp", ".lock", ".part")):
                continue
            s, d = os.path.join(folder, n), os.path.join(target, n)
            if not os.path.exists(d):
                report["copied"] += 1
            elif _newer(s, d):
                report["updated"] += 1
            else:
                report["kept"] += 1
                continue
            data = _migrated(s)
            if data is not None:
                report["migrated"] += 1
            if not dry:
                os.makedirs(target, exist_ok=True)
                if data is None:
                    shutil.copy2(s, d)
                else:
                    with open(d, "wb") as f:
                        f.write(data)
                    st = os.stat(s)
                    os.utime(d, (st.st_atime, st.st_mtime))     # keep the source's time for the newer-check


def _activity(e):
    vals = [e.get(k) for k in ("completed_at", "last_seen", "claim_at", "first_seen")]
    nums = []
    for v in vals:
        try:
            nums.append(float(v))
        except (TypeError, ValueError):
            pass
    return max(nums) if nums else 0.0


def merge_ledger(src, dst, dry, report):
    try:
        with open(src, encoding="utf-8") as f:
            theirs = (json.load(f) or {}).get("entries") or {}
    except (OSError, ValueError):
        return
    try:
        with open(dst, encoding="utf-8") as f:
            mine = json.load(f) or {}
    except (OSError, ValueError):
        mine = {}
    ours = mine.get("entries") or {}
    for key, e in theirs.items():
        if not isinstance(e, dict):
            continue
        e = dict(e)
        if e.get("status") == "working":
            # the old daemon's claim ends here: PaperDaemon's daemon picks the page up again
            e["status"] = "pending"
            for k in ("claim_owner", "claim_at"):
                e.pop(k, None)
        if key not in ours:
            ours[key] = e
            report["ledger_added"] += 1
        elif _activity(e) > _activity(ours[key]):
            ours[key] = e
            report["ledger_updated"] += 1
        else:
            report["ledger_kept"] += 1
    if not dry:
        out = {"version": mine.get("version") or 1, "entries": ours}
        tmp = dst + ".import.tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(out, f, indent=2, sort_keys=True)
        os.replace(tmp, dst)


def run(src, dst, dry=False):
    if not os.path.isdir(src):
        raise SystemExit("no such folder: %s" % src)
    report = {"copied": 0, "updated": 0, "kept": 0, "migrated": 0, "ledger_added": 0, "ledger_updated": 0,
              "ledger_kept": 0, "folders": []}
    os.makedirs(dst, exist_ok=True)
    for name in FOLDERS:
        p = os.path.join(src, name)
        if os.path.isdir(p):
            report["folders"].append(name)
            copy_tree(p, os.path.join(dst, name), dry, report)
    if os.path.isfile(os.path.join(src, LEDGER)):
        merge_ledger(os.path.join(src, LEDGER), os.path.join(dst, LEDGER), dry, report)
    return report


def main(argv=None):
    ap = argparse.ArgumentParser(description="Import a pipeline state folder into PaperDaemon's data folder.")
    ap.add_argument("source", help="the state folder to import from")
    ap.add_argument("--to", help="PaperDaemon's data folder (default: its own)")
    ap.add_argument("--dry-run", action="store_true", help="count what would be copied, change nothing")
    args = ap.parse_args(argv)
    dst = os.path.abspath(args.to) if args.to else data_dir()
    r = run(os.path.abspath(args.source), dst, args.dry_run)
    print("%s %s" % ("would import into" if args.dry_run else "imported into", dst))
    print("  folders: %s" % (", ".join(r["folders"]) or "none found"))
    print("  files: %d new, %d updated, %d kept (PaperDaemon's were newer), %d brought up to the current format"
          % (r["copied"], r["updated"], r["kept"], r["migrated"]))
    print("  ledger: %d entries added, %d updated, %d kept" % (r["ledger_added"], r["ledger_updated"],
                                                               r["ledger_kept"]))
    return 0


if __name__ == "__main__":
    sys.exit(main())
