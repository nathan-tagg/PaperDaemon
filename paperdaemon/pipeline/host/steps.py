r"""The job as a list of typed steps the host walks, one at a time.

The decision gives the steps; the host holds the position, so nothing has to be remembered or re-derived. A step
is an object: `do` (one of KINDS), `what` (what it is about), `answers` (the ids on the page it carries out),
and the fields its kind declares (FIELDS), in any order. The PLACE IS THE STEP: the host makes one box per
content step and hands it to the tool that fills it.

Who does a step: HOST steps are carried out by the host from the step's own fields, with no model turn; MODEL
steps get a turn of their own (the words of a write step, the spec of a chart).

The order is the host's: erases first (placement is measured as though they were gone), then searches (data is
in before anything is built from it), then the rest in the order asked.
"""
import re

HOST, MODEL = "host", "model"

KINDS = {
    "erase": HOST, "search": HOST, "image": HOST, "web_picture": HOST, "coloring": HOST, "posts": HOST,
    "highlight": HOST, "circle": HOST, "underline": HOST, "strike": HOST,
    "tag": HOST, "chess": HOST, "adventure": HOST, "messages": HOST,
    "chart": MODEL, "calendar": MODEL, "write": MODEL, "draw": MODEL,
}
MARK_UP = ("highlight", "circle", "underline", "strike")
GAMES = ("chess", "adventure", "messages")
# what kind of box a content step gets (the layout's vocabulary)
PLACE_KIND = {"write": "text", "chart": "chart", "calendar": "calendar", "draw": "drawing",
              "image": "image", "web_picture": "image", "coloring": "coloring", "posts": "chart"}
TIER = {"erase": 0, "search": 1}

# THE FIELDS EACH KIND OF STEP DECLARES, beside the ones every step has. A field a kind does not declare is
# refused with the list (validity rule 4).
COMMON = ("do", "what", "answers", "size", "near", "side", "at", "replaces")
FIELDS = {
    "erase": (), "search": (), "write": (), "draw": (), "chart": (),
    "calendar": (),                                          # what: YYYY-MM or week
    "image": ("workflow", "source", "steps", "seed", "quote"),
    "coloring": ("steps", "seed", "quote"),
    "web_picture": ("site",),
    "posts": ("source", "search", "sort", "period", "count", "pictures"),
    "highlight": ("target", "words"), "circle": ("target", "words"),
    "underline": ("target", "words"), "strike": ("target", "words"),
    "tag": ("quote",),
    "chess": ("color", "strength", "opponent", "moves"),
    "adventure": (),
    "messages": ("members",),
}
WHAT_IS = {
    "erase": "what you point at, with at", "search": "the query", "image": "a sentence describing the picture",
    "web_picture": "which real picture to find on the web", "coloring": "what the coloring page shows",
    "posts": "the topic", "highlight": "what is highlighted", "circle": "what is circled",
    "underline": "what is underlined", "strike": "what is struck through",
    "tag": "the tag's name, as the user wrote it", "chess": "the opponent and the game as asked",
    "adventure": "the adventure and the hero asked for", "messages": "who to text, as asked",
    "chart": "what it shows and from which figures", "calendar": "the month as YYYY-MM, or week",
    "write": "what the words are about", "draw": "the thing to draw",
}
# WHAT THE MODEL IS TOLD ABOUT EACH KIND, in the brief's PLAN STEPS list, in this order: the kinds an entry
# covers and its text. A lineup is told only the kinds its features offer.
STEP_BRIEF = [
    (('erase',),
     '  erase        only what you point at with at (above)'),
    (('search',),
     '  search       a fact about the world, looked up; the results come with the next step'),
    (('write',),
     '  write        words, placed in the text column'),
    (('chart',),
     '  chart        numbers, dates, plans, lists of things -- bar, line, pie, table, timeline, gantt,\n               kanban, checklist, map and ~55 more; the kinds and their fields come with the step'),
    (('calendar',),
     '  calendar     what = the month as YYYY-MM, or week (the seven days from today); it takes the page'),
    (('draw',),
     '  draw         a simple figure or an icon'),
    (('image',),
     '  image        a picture generated from one sentence (subject, light, style), drawn onto the page\n               in strokes; steps and seed only when the user asked for them, with quote: their words'),
    (('web_picture',),
     '  web_picture  a real picture that exists, found by image search; one per step, never for facts;\n               site: the domain to search, when the request names one'),
    (('coloring',),
     '  coloring     a coloring page of what is named (say what it shows, not "a coloring page"):\n               generated like image, as black line art, and inserted as a picture that takes the page'),
    (('posts',),
     "  posts        social posts clipped onto the page as cards: source ('reddit', 'r/<sub>', '4chan/<board>',\n               'hn', 'bsky', 'bsky/<handle>', 'mastodon/<server>', 'x/<post link>', or any other site by\n               name, e.g. 'x', 'instagram', 'tiktok', which the host searches the web for), search (the topic's\n               words only), sort (hot, new, top, rising, relevance), period (hour, day, week, month,\n               year, all), count (1-4), pictures (true for picture posts); never write posts out"),
    (('highlight',),
     '  highlight    target (an id) and words (the exact words to mark, found inside the target); either\n               alone marks that; on a PDF, words from its text'),
    (('circle', 'underline', 'strike'),
     '  circle / underline / strike   the same target and words, or what at points to'),
    (('tag',),
     "  tag          a tag on this page, named as the user named it, with quote: the user's words that ask\n               for it -- ONLY when this notebook's system prompt or this page tells you to tag it"),
    (('chess',),
     '  chess        a chess game played on THIS page, which it takes whole (nothing else goes on it): color (white,\n               black or either), strength (a rating the user named), opponent (a resident the user\n               named), moves (the moves the request already makes, in order, as written: ["e4"])'),
    (('adventure',),
     '  adventure    an ink adventure (what = the adventure and the hero asked for): its scene takes THIS\n               page whole (nothing else goes on it), its sheet and log right after'),
    (('messages',),
     "  messages     texting the game's residents: members (who, one or several for a group chat); it\n               takes THIS page whole (nothing else goes on it). A picture OF a board is a chart, not a game"),
]


POST_SORTS = ("hot", "new", "top", "rising", "relevance")
POST_PERIODS = ("hour", "day", "week", "month", "year", "all")


def brief_list(offered):
    """The PLAN STEPS list for the kinds offered: each entry whose kinds are all offered (a shared line names
    only the ones offered)."""
    out = []
    for ks, text in STEP_BRIEF:
        have = [k for k in ks if k in offered]
        if not have:
            continue
        if len(have) < len(ks):
            text = re.sub(r"^  [\w /]+?(\s{2,})", lambda m: "  " + " / ".join(have) + m.group(1), text, count=1)
        out.append(text)
    return "\n".join(out)


def fields_of(do):
    return COMMON + FIELDS.get(do, ())


def calendar_what(what):
    """A calendar step's what -> ("month", year, month) or ("week",), or None when it is neither form."""
    w = str(what or "").strip().lower()
    if w == "week":
        return ("week",)
    m = re.fullmatch(r"(\d{4})-(\d{1,2})", w)
    if m and 1 <= int(m.group(2)) <= 12:
        return ("month", int(m.group(1)), int(m.group(2)))
    return None


class StepError(ValueError):
    pass


def build(raw):
    """[{do, what, answers, ...}] -> ordered steps. Raises StepError with what to fix. The decision's validity is
    checked before (rulings.problems); this is the same contract for a step added later (need_step)."""
    if not isinstance(raw, list) or not raw:
        return []
    out = []
    for i, s in enumerate(raw):
        if not isinstance(s, dict):
            raise StepError("step %d is not an object. Each step is {\"do\", \"what\", \"answers\"}." % (i + 1))
        do = str(s.get("do") or "").strip()
        if do not in KINDS:
            raise StepError("step %d: no such step %r. Use one of: %s." % (i + 1, s.get("do"), ", ".join(sorted(KINDS))))
        what = " ".join(str(s.get("what") or "").split())
        if not what and do != "posts":
            raise StepError("step %d (%s) needs what: %s." % (i + 1, do, WHAT_IS[do]))
        # an erase STEP is for what the model points at in words or on the picture (`at`); everything with an id
        # comes off by a ruling. A description matched nothing and left the request on the page.
        if do == "erase" and not ids_only(what) and not s.get("at"):
            raise StepError("step %d erases %r, which is not an id. What has an id comes off by a ruling "
                            "{\"id\", \"is\", \"then\": \"erase\"}; an erase step is only for what you point at with at."
                            % (i + 1, what[:60]))
        step = {"id": len(out) + 1, "do": do, "status": "todo", "what": what}
        for k in ("size", "near", "side", "because"):
            v = s.get(k)
            if isinstance(v, str) and v.strip():
                step[k] = v.strip().lower()
        ans = s.get("answers")
        step["answers"] = [str(a) for a in ans if str(a).strip()] if isinstance(ans, list) else []
        if isinstance(s.get("replaces"), str) and re.fullmatch(r"picture:\d+", s["replaces"].strip()):
            step["replaces"] = s["replaces"].strip()
            step["near"] = step["replaces"]                     # redrawn in its place
        for k in ("workflow", "quote", "site", "source", "search", "target", "words", "color", "opponent"):
            v = s.get(k)
            if isinstance(v, str) and v.strip():
                step[k] = v.strip() if k in ("workflow", "quote", "words", "search") else " ".join(v.split()).lower()
        for k in ("sort", "period"):
            v = str(s.get(k) or "").strip().lower()
            if v in (POST_SORTS if k == "sort" else POST_PERIODS):
                step[k] = v
        for k in ("steps", "seed", "count", "strength"):
            try:
                if s.get(k) is not None and str(s[k]).strip():
                    step[k] = int(float(s[k]))
            except (TypeError, ValueError):
                pass
        if s.get("pictures") is not None:
            step["pictures"] = bool(s["pictures"])
        # a chess game's MOVES ALREADY MADE in the request, in order from the start; the game checks each by the rules
        mv = s.get("moves")
        if isinstance(mv, str):
            mv = [t for t in re.split(r"[\s,;]+", mv) if t and not re.fullmatch(r"\d+\.+", t)]
        if isinstance(mv, list) and mv:
            step["moves"] = [str(m).strip()[:12] for m in mv if str(m).strip()][:40]
        mem = s.get("members")
        if isinstance(mem, list):
            step["members"] = [str(m).strip() for m in mem if str(m).strip()][:12]
        # WHERE, AS THE MODEL SEES IT: its own grounding on the page picture, [x1, y1, x2, y2] round a thing or
        # [x, y] for a spot, 0-1000 across the picture; or in words, which the host asks it to ground
        at = s.get("at")
        if isinstance(at, (list, tuple)) and len(at) in (2, 4):
            try:
                step["at"] = [float(v) for v in at]
            except (TypeError, ValueError):
                pass
        elif isinstance(at, str) and at.strip():
            step["at"] = " ".join(at.split())
        out.append(step)
    out.sort(key=lambda s: (TIER.get(s["do"], 2), s["id"]))
    for n, s in enumerate(out, 1):          # renumbered so ids read in the order they run
        s["id"] = n
    return out


def place_for(step):
    """The layout place a content step gets. Its id is the step's, so nothing has to be echoed."""
    if step["do"] not in PLACE_KIND:
        return None
    p = {"id": step.get("place") or ("s%d" % step["id"]), "kind": PLACE_KIND[step["do"]],
         "size": step.get("size") or ("full" if step["do"] in ("calendar", "coloring") else "medium"),
         "near": step.get("near") or "stack"}
    if step.get("side"):
        p["side"] = step["side"]
    if step["do"] == "calendar":
        p["size"] = "full"
    return p


# ----------------------------------------------------------------- ids
# THE IDS ARE A FORCED CHOICE: the listing prints them, and the tools' schemas hold them as an enum, so the
# server's grammar lets a model write nothing else. The enum is STATIC (the full range, not this page's items):
# the tool schema is part of the cached prompt prefix and must not change from job to job. The host checks that
# an id exists on THIS page.
ERASE_RANGE = {"para": 30, "line": 40, "mark": 99, "picture": 12}
ERASE_IDS = tuple("%s:%d" % (k, n) for k in ("para", "line", "mark", "picture") for n in range(1, ERASE_RANGE[k] + 1))
ERASE_BECAUSE = ("request", "asked", "stale")
_ID = re.compile(r"(para|line|mark|picture):(\d+)(?:\.\.(\d+))?")


def ids_only(what):
    """True when `what` is nothing but listing ids (para:2, line:1, mark:3, picture:1, or a range mark:A..B)."""
    toks = [t for t in re.split(r"[\s,;]+", str(what or "").strip()) if t]
    return bool(toks) and all(_ID.fullmatch(t) for t in toks)


def erase_steps(items):
    """Erase entries ([{id, because}], from the rulings) -> erase steps for build()."""
    out = []
    for e in items or ():
        eid, because = str(e.get("id") or "").strip(), str(e.get("because") or "").strip().lower()
        if not _ID.fullmatch(eid) or "." in eid:
            raise StepError("%r is not an id from the page's listing." % eid[:60])
        step = {"do": "erase", "what": eid}
        if because in ERASE_BECAUSE:
            step["because"] = because
        out.append(step)
    return out


def erase_targets(what):
    """'para:2', 'mark:6..8', 'picture:1', 'at:1' (ink the model pointed at) -> [(kind, value)]. Nothing else is a
    target: an id or a point, never words."""
    out = []
    for kind, a, b in _ID.findall(str(what or "")):
        if kind == "mark" and b and int(a) <= int(b) <= int(a) + 80:
            out += [("mark", n) for n in range(int(a), int(b) + 1)]
        else:
            out.append((kind, int(a)))
    out += [("at", int(m)) for m in re.findall(r"\bat:(\d{1,3})\b", str(what or ""))]
    return out


# ----------------------------------------------------------------- the job's progress, for the window
# THE HOST KNOWS ITS STEPS once the plan is in: the window shows a bar on the page's cover and in the viewer (tablet.js),
# moving as steps finish. The host names the page when a job starts (begin); before the plan the bar has no count.
PROGRESS = {"path": None, "doc": None, "page": None, "plan": None}


def _write_progress(done=None, total=None):
    import json
    import os
    import time
    p = PROGRESS["path"]
    if not p:
        return
    try:
        os.makedirs(os.path.dirname(p), exist_ok=True)
        tmp = p + ".part"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump({"doc": PROGRESS["doc"], "page": PROGRESS["page"], "done": done, "total": total, "at": time.time(),
                       "plan": PROGRESS["plan"]}, f)
        os.replace(tmp, p)
    except OSError:
        pass


def begin(path, doc, page):
    PROGRESS.update(path=path, doc=doc, page=page, plan=None)
    _write_progress()


def report(steps):
    """The plan's steps, done or failed of all, to the window -- and THE WORK AT HAND, each step as "<kind>: <what>",
    which the daemon writes on the page for the user (pipeline/daemon/notes.py) once it is there."""
    steps = steps or []
    if PROGRESS["plan"] is None and steps:
        PROGRESS["plan"] = [("%s: %s" % (s.get("do"), str(s.get("what") or "").strip())).rstrip(": ") for s in steps]
    _write_progress(sum(1 for s in steps if s.get("status") in ("done", "failed")), len(steps))


def end():
    import os
    p = PROGRESS["path"]
    PROGRESS.update(path=None, doc=None, page=None, plan=None)
    if p:
        try:
            os.remove(p)
        except OSError:
            pass


# ----------------------------------------------------------------- walking the list
def current(steps):
    """The step being worked on: the first that is not finished."""
    for s in steps or ():
        if s["status"] in ("todo", "doing"):
            return s
    return None


def left(steps):
    return [s for s in (steps or ()) if s["status"] in ("todo", "doing")]


def failed(steps):
    """Steps that were tried and did not work: shown to the model and recorded in the job's note."""
    return [s for s in (steps or ()) if s["status"] == "failed"]


def is_host(step):
    return bool(step) and KINDS[step["do"]] == HOST


def describe(step):
    """One short phrase, for a message to the model or a line in the log."""
    d, w = step["do"], step.get("what", "")
    if d == "erase":
        bits = [("the ink pointed at (%s)" % (step.get("about") or "as grounded")) if kind == "at" else
                {"para": "typed paragraph %s", "line": "line of handwriting %s", "mark": "ink mark %s",
                 "picture": "picture %s"}[kind] % v for kind, v in erase_targets(w)]
        return "erase " + (", ".join(bits) or w)
    if d in MARK_UP:
        aim = " ".join(x for x in (repr(step["words"]) if step.get("words") else "",
                                   ("in " if step.get("words") else "") + step["target"] if step.get("target") else "") if x)
        return "%s %s" % ("strike through" if d == "strike" else d, aim or w)
    return {
        "search": "search for %s", "image": "make a picture of %s", "web_picture": "find a real picture on the web: %s",
        "coloring": "make a coloring page of %s", "posts": "clip posts: %s",
        "tag": "tag this page %r", "chart": "chart %s", "calendar": "calendar: %s", "write": "write %s",
        "chess": "start a chess game: %s", "adventure": "start an adventure: %s", "messages": "start messages: %s",
        "draw": "draw %s",
    }[d] % ((step.get("source") or w) if d == "posts" else w)


def brief(steps, extra=None):
    """The whole list with the current step marked -- the shape of the job in a few lines."""
    cur = current(steps)
    lines = []
    for s in steps:
        mark = "->" if s is cur else {"done": "ok", "failed": "XX"}.get(s["status"], "  ")
        lines.append("  %s %d. %s%s" % (mark, s["id"], describe(s),
                                        (" -- FAILED: %s" % s.get("note", "")) if s["status"] == "failed" else ""))
    if cur is None:
        bad = failed(steps)
        head = "Every step is done." if not bad else "Nothing left to try, but %d step(s) FAILED." % len(bad)
    else:
        head = "STEP %d OF %d." % (cur["id"], len(steps))
    msg = head + "\n" + "\n".join(lines)
    if extra:
        msg += "\n" + extra
    return msg


def finish(steps, step, ok=True, note=""):
    step["status"] = "done" if ok else "failed"
    if note:
        step["note"] = str(note)[:200]
    report(steps)
    return current(steps)


def insert_before(steps, cur, raw):
    """A step the plan did not have (a search that came back useless, a chart only now known to be needed), put
    in before the current one."""
    new = build([raw])
    if not new:
        raise StepError("say what the extra step should do.")
    s = new[0]
    at = steps.index(cur) if cur in steps else len(steps)
    s["status"] = "todo"
    steps.insert(at, s)
    for n, q in enumerate(steps, 1):
        q["id"] = n
    report(steps)
    return s
