"""Each lineup's memories: what its model has learned about working for this user.

A memory is a lesson -- a complaint, a correction, "erase my request when I write x" -- never system-prompt
material, never the work on a page and never personal data (a notebook's own context is its notepad). The
model makes, replaces and removes them through its decision (the host's `remember` field); the user reads,
edits and deletes them on the lineup's Memories tab, and cannot add one. Every job of the lineup is shown
them. A lineup keeps at most MAX; when it is full, the model must replace one rather than add.

All of it is one file in the data folder, <data>/memories.json: {lineup name: [{id, text, saved}]}. Renaming a
lineup keeps its memories; deleting it deletes them.
"""
import json
import os
import threading
import time

from . import paths

MAX = 30
TEXT_MAX = 400                     # characters of one memory
_lock = threading.RLock()


def _file():
    return os.path.join(paths.data_dir(), "memories.json")


def _load():
    try:
        with open(_file(), encoding="utf-8") as f:
            got = json.load(f)
        return got if isinstance(got, dict) else {}
    except (OSError, ValueError):
        return {}


def _save(d):
    path = _file()
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(d, f, indent=2)
    os.replace(tmp, path)


def _clean(text):
    return " ".join(str(text or "").split())[:TEXT_MAX]


def _next_id(items):
    n = 0
    for m in items:
        try:
            n = max(n, int(str(m.get("id") or "m0")[1:]))
        except ValueError:
            pass
    return "m%d" % (n + 1)


def of(lineup):
    """The lineup's memories, oldest first -> [{id, text, saved}]."""
    with _lock:
        return [dict(m) for m in _load().get(lineup) or []]


def add(lineup, text):
    """A new memory -> it, or raises ValueError (empty, or the lineup is full)."""
    text = _clean(text)
    if not text:
        raise ValueError("a memory needs its text")
    with _lock:
        d = _load()
        items = d.setdefault(lineup, [])
        if len(items) >= MAX:
            raise ValueError("this lineup already keeps %d memories; replace one instead" % MAX)
        m = {"id": _next_id(items), "text": text, "saved": time.strftime("%Y-%m-%d")}
        items.append(m)
        _save(d)
        return dict(m)


def edit(lineup, mid, text):
    """New text for a memory (the model's replace, or the user's edit) -> it, or raises KeyError / ValueError."""
    text = _clean(text)
    if not text:
        raise ValueError("a memory needs its text")
    with _lock:
        d = _load()
        for m in d.get(lineup) or []:
            if m.get("id") == mid:
                m.update(text=text, saved=time.strftime("%Y-%m-%d"))
                _save(d)
                return dict(m)
    raise KeyError("no memory %s" % mid)


def remove(lineup, mid):
    """-> True when it was there."""
    with _lock:
        d = _load()
        items = d.get(lineup) or []
        keep = [m for m in items if m.get("id") != mid]
        if len(keep) == len(items):
            return False
        d[lineup] = keep
        _save(d)
        return True


def rename(old, new):
    with _lock:
        d = _load()
        if old in d and old != new:
            d[new] = d.pop(old)
            _save(d)


def drop(lineup):
    with _lock:
        d = _load()
        if d.pop(lineup, None) is not None:
            _save(d)


def apply(lineup, changes):
    """The model's `remember` list from one decision: each {"text"} adds, {"text", "replaces": id} replaces,
    {"replaces": id} with no text removes -> [what was done, for the job's log]."""
    done = []
    for c in changes or []:
        if not isinstance(c, dict):
            continue
        text, mid = _clean(c.get("text")), str(c.get("replaces") or "").strip()
        try:
            if mid and not text:
                if remove(lineup, mid):
                    done.append("forgot %s" % mid)
            elif mid:
                done.append("replaced %s: %s" % (mid, edit(lineup, mid, text)["text"]))
            elif text:
                m = add(lineup, text)
                done.append("remembered %s: %s" % (m["id"], m["text"]))
        except (KeyError, ValueError) as ex:
            done.append("not kept (%s)" % str(ex).strip("'\""))
    return done
