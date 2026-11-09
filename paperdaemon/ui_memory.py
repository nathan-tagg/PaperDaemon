"""What the window keeps for itself between starts -- the screen it showed, the folder of each library screen, a list's
page size, a note seen -- in the engine's data folder, not in the web view's own storage.

The web view's storage does not survive a restart in every install: its store drops the tail of its log after a hard
stop (an update's restart is one) and keeps writing after the dropped part, so from then on nothing kept there lives
past the next start. Seen 2026-11-09 on the maintainer's machine, where the window came back on the Overview and in no
folder after every update. A small JSON file, written whole and atomically, is kept instead: names to short strings,
numbers or true/false; a null forgets one."""
import json
import os
import re

from . import paths

FILE = "ui-memory.json"
NAME = re.compile(r"^[a-z][a-z0-9_.:-]{0,63}$")
MOST = 200                                          # things remembered, and the longest string's length


def path():
    return os.path.join(paths.data_dir(), FILE)


def load():
    """Everything remembered -> {name: value}; nothing yet, or an unreadable file, is {}."""
    try:
        with open(path(), encoding="utf-8") as f:
            got = json.load(f)
        return got if isinstance(got, dict) else {}
    except (OSError, ValueError):
        return {}


def remember(changes):
    """Merge `changes` ({name: value, name: null to forget}) into what is remembered and write it. -> all of it.
    A bad name or value raises ValueError, and nothing is written."""
    if not isinstance(changes, dict):
        raise ValueError("a {name: value} object")
    cur = load()
    for k, v in changes.items():
        if not isinstance(k, str) or not NAME.match(k):
            raise ValueError("not a name: %r" % str(k)[:40])
        if v is None:
            cur.pop(k, None)
        elif isinstance(v, bool) or isinstance(v, (int, float)) or (isinstance(v, str) and len(v) <= MOST):
            cur[k] = v
        else:
            raise ValueError("%s: a short string, a number or true/false" % k)
    if len(cur) > MOST:
        raise ValueError("too many things remembered")
    os.makedirs(os.path.dirname(path()), exist_ok=True)
    tmp = path() + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(cur, f, indent=1, sort_keys=True)
    os.replace(tmp, path())
    return cur
