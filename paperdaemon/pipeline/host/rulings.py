"""The decision's rulings and its validity: what the model says about each thing on the page, and the host's
whole say about a decision.

A ruling is {id, is, then}: an item of the listing, what it is (a request, a question, the user's note ...),
and whether it comes off or stays. The model rules; the host checks that the decision is VALID -- every id it
names exists on this page, every item new since the last job is ruled, the rulings agree with themselves, each
step is one the lineup can do with fields that step declares, quotes are the user's words, a replaced picture
is this system's -- and refuses an invalid one with a turn that says what to fix. It never rewrites a decision.
"""
from paperdaemon.pipeline.host import steps as ST
from paperdaemon.pipeline.host.job import JOB

IS = ("request", "command", "asked_to_remove", "stale_work", "question", "conversation", "note", "other")
THEN = ("erase", "keep")
ERASABLE = ("request", "command", "asked_to_remove", "stale_work")
BECAUSE = {"request": "request", "command": "request", "asked_to_remove": "asked", "stale_work": "stale"}

# one ruling in a tool's schema: every key required, declared in the order a model writes them (the server's
# grammar holds a nested object's keys to their declared order), nothing else allowed
RULING_ITEM = {"type": "object",
               "properties": {"id": {"type": "string", "enum": list(ST.ERASE_IDS)},
                              "is": {"type": "string", "enum": list(IS)},
                              "then": {"type": "string", "enum": list(THEN)}},
               "required": ["id", "is", "then"], "additionalProperties": False}
RULINGS = {"type": "array", "items": RULING_ITEM, "description":
           "One ruling per thing on the page you rule on, and one for EVERY item listed as NEW: {\"id\": copied "
           "from the listing, \"is\": request | command | asked_to_remove | stale_work | question | conversation | "
           "note | other, \"then\": erase | keep}. erase only for a request or command this job carries out, "
           "what the user asked to have removed, or your own work this job makes stale."}
ANSWERS = {"type": "array", "items": {"type": "string", "enum": list(ST.ERASE_IDS)}, "description":
           "The ids of what on the page this carries out ([] when nothing there asked for it)."}


def _norm(s):
    return " ".join(str(s or "").lower().split())


def problems(kind, args, offered=None):
    """Everything wrong with a decision (`kind` plan or answer, its arguments), as what to fix -> [str]."""
    out = []
    listing = JOB.listing or {}
    rulings = args.get("rulings") or []
    if not isinstance(rulings, list):
        return ["rulings is a list of {\"id\", \"is\", \"then\"}."]
    seen = {}
    for i, r in enumerate(rulings, 1):
        if not isinstance(r, dict):
            out.append("ruling %d is not an object {\"id\", \"is\", \"then\"}." % i)
            continue
        rid, is_, then = str(r.get("id") or ""), str(r.get("is") or ""), str(r.get("then") or "")
        # 1. every id names something on this page
        if rid not in listing:
            out.append("ruling %d names %s, which is not on this page; copy an id from the listing." % (i, rid or "nothing"))
            continue
        if is_ not in IS or then not in THEN:
            out.append("ruling %d (%s): is is one of %s and then is erase or keep." % (i, rid, ", ".join(IS)))
            continue
        # 3. rulings agree with themselves
        if then == "erase" and is_ not in ERASABLE:
            out.append("ruling %d: %s is %s, which stays -- then: keep (only a request, a command, what the user "
                       "asked to remove or your own stale work comes off)." % (i, rid, is_))
        if is_ == "stale_work" and listing[rid].get("owner") != "system":
            out.append("ruling %d: %s is the user's, so it is not stale_work of yours." % (i, rid))
        if rid in seen and seen[rid] != (is_, then):
            out.append("%s is ruled twice, differently." % rid)
        seen[rid] = (is_, then)
    # 2. every item new since the last job is ruled
    unruled = [x for x in (JOB.new_refs or []) if x in listing and x not in seen]
    if unruled:
        out.append("rule every item listed as NEW: %s %s no ruling." % (", ".join(unruled),
                                                                       "has" if len(unruled) == 1 else "have"))
    answered = []
    if kind == "answer":
        answered = args.get("answers") or []
    steps = args.get("steps") if kind == "plan" else None
    if kind == "plan":
        if not isinstance(steps, list) or not steps:
            out.append("steps is a list of steps, one per thing asked, each {\"do\", \"what\", \"answers\"}; "
                       "a page that asks only for words is answer(), one that asks for nothing is skip().")
            steps = []
        replaced = {}
        for i, q in enumerate(steps, 1):
            # C24: a step is an object
            if not isinstance(q, dict):
                out.append("step %d is not an object {\"do\", \"what\", \"answers\"}." % i)
                continue
            do = str(q.get("do") or "")
            # 4. a step the lineup can do, with the fields its kind declares
            if do not in ST.KINDS or (offered is not None and do not in offered):
                out.append("step %d: %r is not a step this lineup does; do is one of %s."
                           % (i, do, ", ".join(offered if offered is not None else sorted(ST.KINDS))))
                continue
            extra = sorted(k for k in q if k not in ST.fields_of(do))
            if extra:
                out.append("step %d (%s) has no field %s; its fields are %s."
                           % (i, do, ", ".join(extra), ", ".join(ST.fields_of(do))))
            if not str(q.get("what") or "").strip() and do != "posts":
                out.append("step %d (%s) needs what: %s." % (i, do, ST.WHAT_IS.get(do, "what it does")))
            ans = q.get("answers")
            if ans is None or not isinstance(ans, list):
                out.append("step %d (%s): answers is the list of ids it carries out ([] for none)." % (i, do))
                ans = []
            answered += ans
            # 8. a replaced picture is this system's, and each is replaced once
            rep = q.get("replaces")
            if rep:
                if listing.get(rep, {}).get("owner") != "system" or not str(rep).startswith("picture:"):
                    out.append("step %d replaces %s, which is not a picture you made." % (i, rep))
                elif rep in replaced:
                    out.append("steps %d and %d both replace %s: one step changes a picture, carrying every "
                               "change asked for." % (replaced[rep], i, rep))
                else:
                    replaced[rep] = i
            # a mark-up's target is an id on this page
            if do in ST.MARK_UP and q.get("target") and q["target"] not in listing:
                out.append("step %d: target %s is not on this page." % (i, q["target"]))
            # 7. a quote is the user's words and holds the value it vouches for
            for k in ("steps", "seed"):
                if q.get(k) is not None:
                    why = _quote_problem(q.get("quote"), str(q[k]))
                    if why:
                        out.append("step %d (%s): %s %s" % (i, do, k, why))
            if do == "tag":
                why = _quote_problem(q.get("quote"), str(q.get("what") or ""))
                if why:
                    out.append("step %d tags the page %r: %s" % (i, q.get("what"), why))
            if do == "calendar" and not ST.calendar_what(q.get("what")):
                out.append("step %d (calendar): what is the month as YYYY-MM, or week." % i)
            if do == "chess" and q.get("color") not in (None, "white", "black", "either"):
                out.append("step %d (chess): color is white, black or either." % i)
            if do == "posts" and not str(q.get("source") or "").strip():
                out.append("step %d (posts): source is where the posts come from (r/<sub>, reddit, hn, bsky, "
                           "4chan/<board>, mastodon/<server>, x/<link>)." % i)
        # A GAME TAKES THE PAGE IT WAS ASKED ON, whole: anything else the plan would put there lands on the board
        games = [str(q.get("do")) for q in steps if isinstance(q, dict) and q.get("do") in ST.GAMES]
        others = [str(q.get("do")) for q in steps if isinstance(q, dict) and q.get("do") in ST.PLACE_KIND]
        if games and others:
            out.append("a %s game takes this page whole: nothing else goes on it, so plan the game alone (drop %s)."
                       % (games[0], ", ".join(sorted(set(others)))))
    for a in answered:
        if a not in listing:
            out.append("answers names %s, which is not on this page." % a)
    return out


def _quote_problem(quote, value):
    """Why a quote does not vouch for `value` (C18, C19), or None: it must be found in the notebook's
    instructions, the typed text or the reading of the user's ink, and must contain the value."""
    q = _norm(quote)
    if not q:
        return "needs quote: the user's own words that ask for it, copied exactly."
    if _norm(value) not in q:
        return "-- the quote %r does not say %s." % (str(quote)[:60], value)
    sources = [_norm(t.get("text")) for k, t in (JOB.listing or {}).items() if t.get("owner") == "user"]
    sources.append(_norm(JOB.sprompt or ""))
    if not any(q in s for s in sources if s):
        return "-- %r is not on this page or in this notebook's instructions; quote the user's words." % str(quote)[:60]
    return None


def erase_of(rulings):
    """The rulings that take something off -> erase entries [{id, because}]."""
    return [{"id": r["id"], "because": BECAUSE[r["is"]]} for r in rulings or ()
            if isinstance(r, dict) and r.get("then") == "erase" and r.get("is") in BECAUSE]


def kept(rulings):
    """The ids the model ruled to keep."""
    return set(r["id"] for r in rulings or () if isinstance(r, dict) and r.get("then") == "keep")


def asked(rulings, answers):
    """What this job carried out, in the user's words, for the notepad: the text of the items it answers."""
    listing = JOB.listing or {}
    ids = list(answers or []) or [r["id"] for r in rulings or () if r.get("is") in ("request", "command")]
    return " / ".join(str(listing[i].get("text") or "")[:160] for i in ids if i in listing and listing[i].get("text"))
