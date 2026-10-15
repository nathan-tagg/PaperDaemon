r"""The optional character-behavior pack.

A PACK is a folder in the content folder (see paperdaemon/paths.py): cast-runtime/<release>/. It holds Python modules
and data that give a cast of characters extra behavior in the games and chats (who is out for a
character with several personalities, what a character gives away, memories shared between
characters). The newest release folder that contains cast_host.py is used. Nothing here is required: with
no pack installed every function below does nothing or returns an empty result, and the games run on the
plain character profiles in games/characters.

A pack may also register hooks in a hooks.json beside cast_host.py, as {"name": "module:function"}:

    interact         (state, text, ask_text) -> result   once per player input, before the profiles are read
    scene_lines      (state) -> [line]                   narration lines the interaction produced this turn
    challenge_input  (state, participants, text, ask_text)   resolve an accusation before the replies
    effective_profile (profile, state) -> profile        the profile to play this turn (it may change mid-game)
    face_svg         (look, emotion, size, marks) -> svg  the pack's own faces for its characters

and "profiles": the folder (inside the pack) holding its characters' profiles,

and a list of extra face marks: {"marks": ["module", ...]} naming modules that define MARKS.
"""
import importlib
import json
import re
import sys
from pathlib import Path

from paperdaemon import paths

def _find_bundle():
    root = Path(paths.content_path("cast-runtime"))
    if not root.is_dir():
        return None
    for d in sorted((p for p in root.iterdir() if (p / "cast_host.py").is_file()), reverse=True):
        return d
    return None


BUNDLE = _find_bundle()
H = None
if BUNDLE is not None:
    sys.path.append(str(BUNDLE))          # last: a file in the pack can never stand in for the standard library
    try:
        import cast_host as H
    except Exception:                      # a damaged pack is the same as no pack
        H = None
AVAILABLE = H is not None

_HOOKS = {}
if AVAILABLE and (BUNDLE / "hooks.json").is_file():
    try:
        _HOOKS = json.loads((BUNDLE / "hooks.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        _HOOKS = {}


def hook(name):
    """The callable the pack registered under this name, or None."""
    spec = _HOOKS.get(name)
    if not isinstance(spec, str) or ":" not in spec:
        return None
    mod, _, fn = spec.partition(":")
    try:
        return getattr(importlib.import_module(mod), fn)
    except (ImportError, AttributeError):
        return None


def profile_path(cid):
    """Where the pack keeps a character's profile, or None (no pack, or the pack names no profiles folder)."""
    sub = _HOOKS.get("profiles") if AVAILABLE else None
    return BUNDLE.joinpath(*str(sub).split("/"), cid + ".json") if isinstance(sub, str) and sub else None


def _extra_marks():
    out = []
    for mod in _HOOKS.get("marks") or ():
        try:
            out += list(importlib.import_module(mod).MARKS)
        except (ImportError, AttributeError):
            pass
    return tuple(out)


# face marks a pack's characters can show: the generic signature and tell slots, then any a pack adds
MARKS = ("signature_1", "signature_2", "signature_3", "signature_4", "tell_1", "tell_2", "tell_3") + (
    _extra_marks() if AVAILABLE else ())


def roster():
    return H.roster() if H else {}


def identity(cid, front=None):
    return H.identity(cid, front) if H else cid


def members(cid):
    if not H:
        return {}
    s = H.system()
    return {k: dict(roster()[k], switch=s["switch"][k]) for k in s["members"]} if cid in s["members"] else {}


def memory_file(root, doc, cid):
    if not all(re.fullmatch(r"[\w-]+", v) for v in (doc, cid)):
        raise ValueError("Unsafe memory path")
    d = Path(root) / doc / "residents" / "players"
    d.mkdir(parents=True, exist_ok=True)
    return str(d / (cid + ".json"))


def legacy_memory(root, doc, cid):
    """Read-only migration of an older single-file memory into the per-character layout. Old files are
    kept; each later write goes to the new file."""
    if not H:
        return None
    system = H.system()
    # the old layout kept one file for the whole system, named for its body
    old = Path(root) / doc / "residents" / ((system["body"] if cid in system["members"] else cid) + ".json")
    if not old.exists():
        return None
    data = json.loads(old.read_text(encoding="utf-8"))
    if cid in system["members"]:
        aid = system["members"][cid]
        data["memories"] = [m for m in data.get("memories", []) if m.get("alter") in (aid, cid)]
        data["rapport"] = data.get("rapport_by", {}).get(aid, 0)
        data["met"] = data.get("met_by", {}).get(aid)
        data.pop("rapport_by", None)
        data.pop("met_by", None)
        for m in data["memories"]:
            m.pop("alter", None)
    data["id"] = cid
    data["migration_source"] = str(old)
    return data


# ---- calls the games make; each is a no-op without a pack -------------------------------------------
def prepare(state, cid, rng, situations=()):
    """Settle who is out for this turn; -> the character id to play."""
    return H.prepare(state, cid, rng, situations) if H else cid


def pack_front(state, cid):
    return H.front(state, cid) if H else None


def before(state, cid, plan):
    return H.before(state, cid, plan) if H else plan


def after(state, cid, plan, out, truth="", speech="", presentation=None):
    return H.after(state, cid, plan, out, truth, speech, presentation) if H else out


def parse_face(reply):
    return H.parse_face(reply) if H else None


def suspicion_from_reply(state, plan, reply):
    if H:
        H.suspicion_from_reply(state, plan, reply)


def borrowed(memroot, doc, cid, load, query="", limit=8):
    return H.borrowed(memroot, doc, cid, load, query, limit) if H else []


def interact(state, text, ask_text=None):
    fn = hook("interact")
    return fn(state, text, ask_text) if fn else None


def scene_lines(state):
    fn = hook("scene_lines")
    return list(fn(state)) if fn else []


def challenge_input(state, participants, text, ask_text=None):
    fn = hook("challenge_input")
    if fn:
        fn(state, participants, text, ask_text)


def effective_profile(profile, state):
    fn = hook("effective_profile")
    return fn(profile, state) if fn else profile
