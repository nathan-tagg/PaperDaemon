"""A lineup's features and the host's run file.

Whenever the engine starts its children it judges every feature of the catalog (pipeline/features.py)
against each lineup's slots, the settings and the installed content, and writes the result, with the
harness's values and the settings the host needs, into <data>/run/lineup.json. The host reads its
settings only from that file; the engine restarts it when the file's content changes.
"""
import json
import os

from .. import paths
from .. import settings as S
from ..pipeline import features as F
from . import slots

CATALOG = F.Catalog()


def _content():
    out = []
    if paths.games_installed():
        out.append("characters")
    if paths.stockfish():
        out.append("chess engine")
    return out


def facts(s=None, lineup=None):
    """What feature requirements are judged by, for the named lineup (the active one by default)."""
    s = s or S.load()
    lu = S.lineup(s, lineup) if lineup else S.active(s)
    text = slots.caps("text", s, lu["text"])
    image = workflows = None
    if str(lu["image"].get("location") or "").strip():
        h = slots.pick("image", s, lu["image"])[0]
        image, workflows = list(h.abilities), sorted(h.workflows)
    search = lu.get("search") or {}
    filled = ["location"] if (s.get("location") or {}).get("name") or (s.get("location") or {}).get("lat") is not None else []
    off = {n: "it is switched off in the settings" for n in (s.get("features") or {}).get("off") or []}
    for n in (slots.pick("text", s, lu["text"])[0].fields().get("features") or {}).get("off") or []:
        off.setdefault(n, "the text model's harness switches it off")
    if (s.get("network") or {}).get("allowed") is False:          # what only the internet gives
        for n in ("search", "posts"):
            off.setdefault(n, "network access is off in the settings")
    # WHAT THE TEXT HARNESS DECLARES: the job kinds it supports (a feature whose every step kind it does not is
    # off), and abilities its model provides itself (its own pictures, its own web search), which count as met
    declared = slots.pick("text", s, lu["text"])[0].declare()
    kinds, provides = declared.get("kinds"), set(declared.get("provides") or ())
    if kinds is not None:
        for f in CATALOG.by_name.values():
            if f.steps and not set(f.steps) & set(kinds):
                off.setdefault(f.name, "this harness does not do %s" % f.summary)
    if "pictures" in provides and image is None:
        image, workflows = ["generate"], []
    has_search = bool(search.get("url") if search.get("kind") == "local"
                      else search.get("provider") if search.get("kind") == "api" else False)
    return {"text": text, "image": image, "workflows": workflows or [],
            "search": has_search or "search" in provides,
            "content": _content(), "settings": filled, "off": off,
            "provided": sorted(provides)}


def features(s=None, lineup=None):
    """{feature: {"state", "because", "summary"}} for the named lineup."""
    fa = facts(s, lineup)
    got = F.resolve(CATALOG, fa)
    provided = {"pictures": ("generate",), "search": ()}
    for name, st in got.items():
        st["summary"] = CATALOG.by_name[name].summary
        f = CATALOG.by_name[name]
        if st["state"] != "off" and (("pictures" in fa["provided"] and set(f.requires.image) & set(provided["pictures"]))
                                     or ("search" in fa["provided"] and f.requires.search)):
            st["because"] = list(st["because"]) + ["the model does it itself"]
    return got


def run_file(per_lineup, s=None):
    """The host's run file's content. `per_lineup` is {lineup name: its text harness's values} (what
    loop.harness_values gives); each lineup gets its resolved features, web search and tags beside them. Every
    lineup is live: the host picks one per job by the job's tag (`tag_lineup`), and the top level holds the
    first lineup's values until it does. `settings` is what the host reads that belongs to no lineup."""
    s = s or S.load()
    loc = s.get("location") or {}
    lineups = {}
    for name, values in (per_lineup or {}).items():
        lu = S.lineup(s, name)
        if lu is None:
            continue
        lineups[name] = dict(values, features=features(s, name), search=dict(lu.get("search") or {}),
                             tags=[dict(t) for t in lu.get("tags") or []])
    ignore, sprompt = S.fixed_tags(s)
    first = next(iter(lineups.values()), {})
    return dict(first, lineups=lineups,
                tag_lineup={tag.lower(): name for tag, name in S.all_tags(s)},
                settings={"location": {"name": loc.get("name") or "", "lat": loc.get("lat"), "lon": loc.get("lon"),
                                       "holidays": loc.get("holidays") or ""},
                          "prefs": dict(s.get("prefs") or {}),
                          "network": dict(s.get("network") or {}), "social": dict(s.get("social") or {}),
                          "search": dict(first.get("search") or {}),
                          "tags": {"ignore": ignore, "sprompt": sprompt}})


def write_run_file(content, folder=None):
    """<data>/run/lineup.json, written whole. -> its path."""
    folder = folder or paths.sub("run")
    path = os.path.join(folder, "lineup.json")
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(content, f, indent=2, sort_keys=True)
    os.replace(tmp, path)
    return path
