"""The decision turn and the plan: the brief and the tools the model is offered, the tools that end a decision, and the steps they add."""
import json
import math
import os
import re
from paperdaemon.pipeline import charts as CH
from paperdaemon.pipeline import page as ER
from paperdaemon.pipeline.host import layout as PL
from paperdaemon.pipeline.host import assists as AS
from paperdaemon.pipeline.host import rulings as RU
from paperdaemon.pipeline.host import steps as ST
from paperdaemon.pipeline.host.job import JOB
from paperdaemon.pipeline.page import render as R
from paperdaemon.pipeline import host as H

STEP_KINDS = "<step kinds>"         # filled in with this lineup's offered kinds (tool_schema)

CAL_BRIEF = {
    "page": """CALENDARS: a calendar, a month, a week, the forecast or the weather is one calendar
step (it takes the page); its chart call is {"type": "calendar", "year": 2026, "month": 10} for a
month or {"type": "week"} for the seven days from today.""",
}
_SITE_NAMES = {"reddit": "Reddit", "hackernews": "Hacker News", "bluesky": "Bluesky", "4chan": "4chan",
               "mastodon": "Mastodon"}
_ABILITY_WORDS = {
    "generate": "makes a picture from a sentence",
    "edit_reference": "edits a picture handed to it as a reference",
    "img2img": "redraws a picture starting from another one",
    "inpaint": "changes only a masked part of a picture",
}


def t_answer(answers, lines, rulings=None, size=34):
    """The decision when the whole job is words: the reply written and committed in one call. `answers` are the
    ids of what on the page it answers; `rulings` as for plan (checked the same way)."""
    rulings = rulings if isinstance(rulings, list) else []
    answers = answers if isinstance(answers, list) else []
    probs = RU.problems("answer", {"answers": answers, "rulings": rulings})
    if not probs:
        d, hint = AS.apply({"rulings": rulings}, getattr(H._H(), "assists", ()))
        if hint:
            return dict({"error": hint + " Answer again: keep your answer or change it."}, **H._did())
        rulings = d["rulings"]
    if probs:
        return dict({"error": "This answer cannot be written as it is. Fix it and answer again:\n- "
                              + "\n- ".join(probs)}, **H._did())
    return H._reply(lines, answers, rulings, size)


def _reply(lines, answers=(), rulings=(), size=34, task=None):
    """Write the reply under what is on the page, in the text column, and commit it."""
    if isinstance(lines, str):
        lines = [lines]
    lines = [str(l) for l in (lines or []) if str(l).strip()]
    if not lines:
        return dict({"error": "lines is empty. Give the reply, one string per line, in reading order."}, **H._did())
    task = task or RU.asked(rulings, answers) or "a reply"
    if not H._scratch().get("request"):
        H._scratch()["request"] = task[:300]            # what the notepad records as asked
    plan = JOB.plan or {}
    if not plan:
        n = len(lines)
        size_word = "small" if n <= 2 else "medium" if n <= 6 else "large"
        # the one-call path makes its own one-step plan: the write, with the rulings' erases run first
        # (answer() checked the decision already; ask() makes no rulings, so nothing comes off)
        steps = ST.build(ST.erase_steps(RU.erase_of(rulings))
                         + [{"do": "write", "what": str(task)[:120], "answers": list(answers)}])
        r = H._plan(steps, list(rulings), places=[{"id": "answer", "kind": "text", "size": size_word}])
        if r.get("error"):
            return dict(r, **H._did())
        plan = JOB.plan or {}
    if "answer" not in (plan.get("places") or {}):
        return dict({"error": "your plan has no place called 'answer'. Use write_paragraph with one of your own "
                              "places, or answer() before planning."}, **H._did())
    r = H.t_write_paragraph(lines, place="answer", size=int(size))
    if r.get("error"):
        return r
    r = H.t_commit()
    if r.get("error"):
        return r
    out = dict({"ok": True, "lines_written": len(lines), "committed": True,
                "note": "written and on the page."}, **H._did())
    out["already_on_page"] = list(JOB.ops)
    return out


def _off_steps(steps):
    """Why a planned step cannot run because its feature is off in the run file, or None."""
    feats = H.RUN.get("features") or {}
    if not feats:
        return None
    from paperdaemon.pipeline import features as F
    owner = F.Catalog().step_feature()
    for q in steps:
        n = owner.get(q["do"])
        st = (feats.get(n) if n else None) or {"state": "on"}
        if st["state"] == "off":
            return ("the %s step is off: %s is off because %s. Plan without it, or say in words that it is not "
                    "available." % (q["do"], n, "; ".join(st.get("because") or ["it is switched off"])))
    return None


def t_plan(steps, rulings=None, places=None):
    """The decision for a page that asks for work: its steps, in order, and the rulings on what is on the page.

    The model decides; the host checks the decision is valid (rulings.problems) and refuses an invalid one with a
    turn that says what to fix -- it never rewrites one. Then it walks the steps: erases first (placement is
    measured as though they were gone), the layout solved once for every content step, and each step done by the
    host or by a turn of its own.
    """
    rulings = rulings if isinstance(rulings, list) else []
    offered = [k for k in ST.KINDS if k not in H._off_steps_and_tools()[0]]
    probs = RU.problems("plan", {"steps": steps, "rulings": rulings}, offered=offered)
    if probs:
        return {"error": "This plan cannot run as it is. Fix it and plan again:\n- " + "\n- ".join(probs)}
    d, hint = AS.apply({"steps": steps, "rulings": rulings}, getattr(H._H(), "assists", ()))
    if hint:
        return {"error": hint + " Plan again: keep your plan or change it."}
    steps, rulings = d["steps"], d["rulings"]
    try:
        plan_steps = ST.build(ST.erase_steps(RU.erase_of(rulings)) + list(steps))
    except ST.StepError as ex:
        return {"error": str(ex)}
    return H._plan(plan_steps, rulings, places)


def _plan(plan_steps, rulings=(), places=None):
    """Run a plan: its steps checked against the lineup, erases first, the layout solved, and the host's own steps
    done. The model's plan comes through t_plan, checked; the host's own come here directly."""
    refused = H._off_steps(plan_steps)
    if refused:
        JOB.refused.append(refused)
        return {"error": refused}
    JOB.kept_paras.update(int(i.split(":")[1]) for i in RU.kept(rulings) if i.startswith("para:"))
    if not H._scratch().get("request"):
        H._scratch()["request"] = RU.asked(rulings, [a for q in plan_steps for a in q.get("answers") or []])[:300]
    # a line of handwriting named by its id is the marks it is made of
    for q in plan_steps:
        if q["do"] == "erase":
            q["what"] = H._resolve_lines(q["what"])
        if q["do"] in ST.MARK_UP and q.get("target"):
            q["target"] = H._resolve_lines(q["target"])
    if not plan_steps:
        return {"error": "steps is empty. Say what this job does, in order, one step each; if the page asks for "
                         "nothing, skip()."}
    # A NEW PICTURE TAKES THE PLACE OF ONE THE PLAN ERASES: a chart, calendar or picture step with no placement of
    # its own takes the topmost erased picture's place (stacked, it would go below everything still on the page),
    # and the redo code below does the rest.
    _gone = [v for q in plan_steps if q["do"] == "erase"
             for k, v in ST.erase_targets(q["what"]) if k == "picture"]
    if _gone:
        _pb = dict((p_["n"], p_) for p_ in H._pictures(JOB.doc, JOB.page))
        _held = set(str(q.get("near") or "") for q in plan_steps)
        _gone = sorted((n_ for n_ in set(_gone) if n_ in _pb and "picture:%d" % n_ not in _held),
                       key=lambda n_: _pb[n_]["box"][1])
        for q in plan_steps:
            if (_gone and q["do"] in ("chart", "calendar", "image", "web_picture", "coloring")
                    and str(q.get("near") or "stack") == "stack"):
                n_ = _gone.pop(0)
                q["near"] = "picture:%d" % n_
                H.log("  step %d takes the place of picture:%d, which the plan erases" % (q["id"], n_))
    # THE PLACE IS THE STEP. Every content step gets one box, named after the step, so the tool that fills it
    # never has to echo an id. A caller that passes `places` (answer(), tests) has them matched to steps by kind,
    # in order.
    # POINTED AT (`at`, see _from_view). An erase step's target is resolved here, on the page: the picture it
    # lies in, else the typed paragraphs and the ink it covers. A content step's `at` says where it goes: a spot
    # is its tip, as an arrow's is; a box is an anchor it sits on or beside, padded out for a drawing, so a
    # circle drawn "on" a word goes round it.
    # AN ID IS NOT WORDS: `at` naming an id (para:1, mark:3, picture:2, line:4) is that thing, so it is
    # what an erase takes off and what any other step sits beside; grounded as words it is found nowhere
    for q in plan_steps:
        id_ = str(q.get("at") or "").strip().lower() if isinstance(q.get("at"), str) else ""
        if re.fullmatch(r"(para|mark|picture|line):\d+", id_):
            q.pop("at")
            if q["do"] == "erase":
                q["what"] = H._resolve_lines(id_)
            elif not q.get("near"):
                q["near"] = id_
            H.log("  step %d: at %s is an id, read as one" % (q["id"], id_))
    JOB.at_ink, JOB.at_anchor, JOB.at_tip = {}, {}, None
    # NEAR A LINE OF HANDWRITING (near="line:N"): the line's own box is the anchor, as a box pointed at is
    for q in plan_steps:
        m_ = re.fullmatch(r"line:(\d+)", str(q.get("near") or ""))
        ln_ = (JOB.ink_lines or {}).get(int(m_.group(1))) if m_ else None
        if ln_:
            JOB.at_anchor[2000 + int(m_.group(1))] = list(ln_[2])
            q["near"] = "mark:%d" % (2000 + int(m_.group(1)))
    _spot = lambda pt, r: (pt[0] - r, pt[1] - r, pt[0] + r, pt[1] + r)
    # IN WORDS: the host asks the model to ground them -- the one way its grounding is exact -- all
    # of the plan's in one question
    _grounded = H._at_ground([q["at"] for q in plan_steps if isinstance(q.get("at"), str)])
    _where = {}                                   # step id -> ("box" | "point", in page units)
    for q in plan_steps:
        at = q.get("at")
        if not at:
            continue
        if isinstance(at, str):
            g = _grounded.get(at)
            if g is None:
                H.log("  step %d: %r could not be found on the page" % (q["id"], at[:60]))
                q.pop("at", None)
                continue
            q["at_found"] = [round(v) for v in g[1]]
            H.log("  step %d: %r grounded to %s %s" % (q["id"], at[:60], g[0], q["at_found"]))
            _where[q["id"]] = (g[0], tuple(g[1]))
        else:
            _where[q["id"]] = ("point" if len(at) == 2 else "box", H._from_view(at))
    for q in plan_steps:
        w_ = _where.get(q["id"])
        if w_ is None:
            continue
        pt_, at = w_[0] == "point", w_[1]
        _pg = lambda a: tuple(a)
        if q["do"] == "erase":
            b = _pg(at) if not pt_ else _spot(_pg(at), 40.0)
            # a request's own words and arrow never take the THING another step acts on
            exc = ([w2[1] for i2, w2 in _where.items() if i2 != q["id"] and w2[0] == "box"]
                   if q.get("because") == "request" else [])
            got = H._at_resolve(b, exclude=exc)
            refs = ["picture:%d" % n for n in got["pictures"]] + ["para:%d" % n for n in got["paras"]]
            if got["keys"]:
                JOB.at_ink[len(JOB.at_ink) + 1] = got["keys"]
                refs.append("at:%d" % len(JOB.at_ink))
            H.log("  step %d points at x %d..%d, y %d..%d -> %s"
                % (q["id"], b[0], b[2], b[1], b[3], " ".join(refs) or "nothing there"))
            # what the erase list already names needs no second step
            listed_ = set(t for o in plan_steps if o is not q and o["do"] == "erase" and not o.get("at")
                          for t in str(o["what"]).split())
            if refs and not got["keys"] and set(refs) <= listed_:
                q["duplicate"] = True
                H.log("  step %d points at what the erase list already names; dropped" % q["id"])
            if refs:
                q["about"], q["what"] = q["what"], " ".join(refs)
        elif q["do"] in ST.MARK_UP:
            q["at_box"] = _pg(at) if not pt_ else H._thing_at(_pg(at))    # a mark goes round a THING
        elif q["do"] in ST.PLACE_KIND:
            if pt_ and JOB.at_tip is None:
                JOB.at_tip = _pg(at)
                q["near"] = "arrow"
                continue
            b = _pg(at) if not pt_ else _spot(_pg(at), 150.0)
            if q["do"] == "draw":
                gx, gy = max(30.0, 0.25 * (b[2] - b[0])), max(30.0, 0.35 * (b[3] - b[1]))
                b = (b[0] - gx, b[1] - gy, b[2] + gx, b[3] + gy)
            JOB.at_anchor[1000 + q["id"]] = list(b)
            q["near"] = "mark:%d" % (1000 + q["id"])
            q.setdefault("side", "on" if q["do"] == "draw" else "below")
            H.log("  step %d sits %s the box it points at: x %d..%d, y %d..%d"
                % (q["id"], q["side"], b[0], b[2], b[1], b[3]))
    if any(q.get("duplicate") for q in plan_steps):
        plan_steps[:] = [q for q in plan_steps if not q.get("duplicate")]
        for n_, q in enumerate(plan_steps, 1):
            q["id"] = n_
    content = [q for q in plan_steps if q["do"] in ST.PLACE_KIND]
    if places:
        if not isinstance(places, list):
            return {"error": "places must be a list of {id, kind, size} objects."}
        by_id = dict((str(p.get("id")), p) for p in places if isinstance(p, dict))
        free = [p for p in places if isinstance(p, dict)]
        for q in content:
            ref = q.get("place_ref")
            if ref and ref in by_id and by_id[ref] in free:
                q["place"] = ref
                free.remove(by_id[ref])
        for q in content:
            if q.get("place"):
                continue
            pick = next((p for p in free if p.get("kind") == ST.PLACE_KIND[q["do"]]), None)
            if pick is None and free:
                pick = free[0]
            if pick is None:
                pick = ST.place_for(q)
                places.append(pick)
            else:
                free.remove(pick)
            q["place"] = str(pick.get("id"))
    else:
        places = []
        for q in content:
            p = ST.place_for(q)
            q["place"] = p["id"]
            places.append(p)
    # A "LEFT" OR "RIGHT" NEEDS ITS OTHER HALF. The pair is one row; alone, "right" would be a half-width row of
    # its own below everything else. So a lone side takes the neighboring main-flow place (stack or center) as
    # its other half.
    _pl = [p for p in places if isinstance(p, dict)]
    for i, p in enumerate(_pl):
        side = p.get("near")
        if side not in ("left", "right"):
            continue
        other = "right" if side == "left" else "left"
        nb = [c for c in (_pl[i - 1] if i > 0 else None, _pl[i + 1] if i + 1 < len(_pl) else None) if c]
        if any(c.get("near") == other for c in nb):
            continue                                    # already a pair
        cand = next((c for c in (nb if side == "right" else nb[::-1])
                     if c.get("near") in (None, "stack", "center")), None)
        if cand:
            H.log("  %s is near=%s alone; %s becomes the %s half of its row (was near=%s)"
                % (p["id"], side, cand["id"], other, cand.get("near") or "stack"))
            cand["near"] = other
            cand.pop("side", None)
            for q in plan_steps:
                if q.get("place") == cand["id"]:
                    q["near"] = other
    # A COLORING PAGE TAKES A PAGE OF ITS OWN. Several asked for at once are a coloring book, one to a sheet: the
    # first goes on this page, each after it on a new page the host adds (_coloring_page), so it takes no place
    # in this page's layout.
    for q in [q for q in plan_steps if q["do"] == "coloring"][1:]:
        q["new_page"] = True
        places = [p for p in places if p.get("id") != q.get("place")]
    # The erase steps are the erase list, resolved at commit (mark numbers -> stroke signatures).
    erase = [q["what"] for q in plan_steps if q["do"] == "erase"]
    doc, page = JOB.doc, JOB.page
    from paperdaemon.pipeline.page import marks as MK
    index = JOB.mark_index or []
    # ANYTHING ON THE PAGE CAN BE AN ANCHOR. Marks (by the numbers show_marks() gave), pictures and
    # the typed text are the obstacles a placed thing must clear; the mark index is the one the
    # model has SEEN, so its numbers mean what the model thinks they mean.
    if not index:
        try:
            index = MK.marks(doc, page, 8.0, hide=H._hide())
        except Exception:
            index = []
    _anch = lambda near: re.fullmatch(r"mark:(\d+)", near) and int(near[5:]) in (JOB.at_anchor or {})
    if any(isinstance(p, dict) and str(p.get("near", "")).lower().startswith("mark")
           and not _anch(str(p.get("near", "")).lower())            # a box it pointed at needs no ink
           for p in places) and not index:
        return {"error": "near='mark:N' names an ink mark, but this page has no ink to anchor to. "
                         "Use near='stack', a corner, or 'center'."}
    if not places and not erase and not any(q["do"] in ST.MARK_UP for q in plan_steps):
        # AN ERASE-ONLY JOB has nothing to place, nor does a highlight: the step is the whole of the work.
        return {"error": "a plan needs at least one place, or an erase list. What goes on the "
                         "page, or what comes off it?"}
    # Resolve erase-by-number NOW, to stroke signatures: the numbers go stale the moment anything
    # is erased, the signatures never do. Only the user's ink is erased this way; a place's own
    # strokes are the model's to undo.
    ids, words = H._erase_refs(erase)
    if ids and not index:
        return {"error": "erase names an ink mark, but this page has no ink."}
    for q in plan_steps:
        if q["do"] == "erase":
            own, _w = H._erase_refs([q["what"]])
            q["sigs"] = [k for m in index if m["id"] in own for k in (m.get("keys") or m.get("sigs") or [])]
    JOB.mark_index = index            # the numbers the plan used are the numbers that hold
    sigs, named = [], []
    for mid in ids:
        m = next((m for m in index if m["id"] == mid), None)
        if m is None:
            return {"error": "erase names mark %d, but the marks on this page are numbered 1..%d."
                             % (mid, len(index))}
        sigs += list(m.get("keys") or m.get("sigs") or [])
        named.append("mark %d (%s, %d strokes)" % (mid, m.get("owner"), m.get("count", 0)))
    for k_, keys_ in sorted((JOB.at_ink or {}).items()):     # ink it pointed at
        sigs += list(keys_)
        named.append("the ink pointed at (%d strokes)" % len(keys_))
    # THE ERASES ARE STAGED BEFORE THE PAGE IS MEASURED, so placement is evaluated as though what comes off is
    # already gone: the plan's ink erases go into a provisional plan (so _hide() hides them), the typed erase
    # steps are staged, and only then is the free space measured and the boxes laid out.
    JOB.steps = plan_steps
    JOB.plan = {"tasks": [ST.describe(q) for q in plan_steps], "places": {},
                   "erase": words, "erase_sigs": sigs,
                   "erase_named": named, "warned": False}
    H._drain_host_steps(kinds=("erase",))
    # THE INK ON A PICTURE BEING REDONE GOES WITH IT, and before the page is measured -- the same
    # erase-first rule as a typed instruction: what this system wrote on the old one is the old one.
    _allp = dict((p_["n"], p_) for p_ in H._pictures(doc, page, hidden_too=True))
    for p in places:
        m_ = re.fullmatch(r"\s*(?:picture|pic|image|chart|calendar)\s*[:#=\-]?\s*(\d+)\s*",
                          str(p.get("near") or ""), re.I)
        if m_ and int(m_.group(1)) in _allp:
            ink = H._ink_on(_allp[int(m_.group(1))]["box"])
            if ink:
                H._stage("this system's ink on picture:%s, which is redone" % m_.group(1), sigs=sorted(ink))
                H.log("  %d stroke(s) of this system's ink on picture:%s go with it" % (len(ink), m_.group(1)))
    info = H.t_page_info()
    if info.get("error"):
        return info
    tip, tip_mark = None, None
    for a in info.get("arrows") or ():
        if a.get("points_at_mark") is None and a.get("tip"):
            tip, tip_mark = a["tip"], a.get("mark")
            break
    if JOB.at_tip:
        # THE MODEL'S OWN POINT WINS over the host's arrow detector, which can miss an arrow; the host's arrow
        # nearest that point, if it found one there, is still the arrow that comes off.
        tip = JOB.at_tip
        near_ = [a for a in (info.get("arrows") or ()) if a.get("tip")
                 and math.hypot(a["tip"][0] - tip[0], a["tip"][1] - tip[1]) < 150]
        tip_mark = near_[0].get("mark") if near_ else None
    # AN ARROW THAT A PLACE SITS AT comes off before the layout too: it is stale once the thing is there, and
    # left on the page it would push everything else stacked in the same job below it. Its tip is kept; the page
    # is measured again without it.
    if tip_mark is not None and any(isinstance(p, dict) and p.get("near") == "arrow" for p in places):
        try:
            for m in MK.marks(doc, page, 8.0):
                if m["id"] == tip_mark and m.get("owner") == "yours":
                    sigs += list(m.get("keys") or m.get("sigs") or [])
                    named.append("the arrow (%d strokes)" % m.get("count", 0))
            JOB.plan["erase_sigs"] = sigs
            info = H.t_page_info()
            if info.get("error"):
                return info
        except Exception as ex:
            H._warn("finding the arrow to erase", ex)
    hidden = H._hide()
    live_index = [m for m in index if not set(m.get("keys") or m.get("sigs") or []) <= hidden]
    marks = dict((m["id"], m["bbox"]) for m in index)          # anchors keep their numbers
    marks.update(JOB.at_anchor or {})                   # and the boxes it pointed at
    obstacles = [m["bbox"] for m in live_index]                # erased ink is no obstacle
    obstacles += [im["box"] for im in (info.get("pictures") or [])]
    obstacles += H._typed_boxes(doc, page)                       # skips paragraphs staged for erasing
    # A PLACE ON A PICTURE REDOES THAT PICTURE. near="picture:N" takes the picture's own box, exactly ("add more
    # events to the calendar" is the same calendar, redrawn in the same place), and the old picture comes off
    # when the new one lands. The step carries the old picture's spec so the model extends it rather than
    # starting blank.
    redo = {}
    # a picture the plan also ERASES is still one it can redo: the erase ran first and hid it, and
    # the two end the same way -- the old picture off, the new one in its box
    pics = dict((p["n"], p) for p in H._pictures(doc, page, hidden_too=True))
    for p in list(places):
        m = re.fullmatch(r"\s*(?:picture|pic|image|chart|calendar)\s*[:#=\-]?\s*(\d+)\s*", str(p.get("near") or ""), re.I)
        if not m:
            continue
        pic = pics.get(int(m.group(1)))
        if pic is None:
            return {"error": "place %r is on picture %s, but the pictures on this page are numbered %s."
                             % (p.get("id"), m.group(1), ", ".join(str(k) for k in sorted(pics)) or "(none)")}
        b = b_old = pic["box"]
        # ITS OWN BOX, EXACTLY, WHEN SOMETHING SITS BESIDE IT (a chart in a column by its notes). A picture with
        # its band of the page to itself takes the full width back, so "redo it bigger" can grow it.
        if not [o for o in obstacles if list(o) != list(b_old) and o[1] < b_old[3] and o[3] > b_old[1]
                and (o[2] <= b_old[0] or o[0] >= b_old[2])]:
            b = [H._safe()[0], b[1], H._safe()[2], b[3]]
        # A REDONE CALENDAR STARTS WHERE THE FIRST OF THE CALENDARS COMING OFF WITH IT BEGAN -- the
        # page keeps one calendar, and it goes at the top of the space they held, never lower
        if pic.get("what") in ("week", "calendar"):
            tops = [pics[n_]["box"][1] for n_ in (JOB.erased_pictures or {})
                    if n_ in pics and pics[n_].get("what") in ("week", "calendar")]
            if tops and min(tops) < b[1]:
                b = [b[0], min(tops), b[2], min(tops) + (b[3] - b[1])]
        redo[p["id"]] = PL._finish(p["id"], p.get("kind") or "chart", b[0], b[1], b[2], b[3])
        places.remove(p)
        obstacles = [o for o in obstacles if list(o) != list(b_old)]
        for q in plan_steps:
            if q.get("place") == p["id"]:
                q["replaces_picture"] = pic["n"]
                if pic.get("spec"):
                    q["base_spec"] = pic["spec"]
    if not places:
        boxes = dict(redo)
    else:
        try:
            _rb = [(b["x0"], b["y0"], b["x1"], b["y1"]) for b in redo.values()]
            boxes = PL.solve(places, first_free_y=info.get("first_free_y"), safe=H._safe(), arrow_tip=tip,
                             marks=marks, obstacles=obstacles + _rb, text_col=H._text_col(doc, page),
                             fixed=_rb)
        except PL.PlanError as ex:
            return {"error": str(ex)}
        boxes.update(redo)
    # WHAT THE LAYOUT IS RE-SOLVED FROM as each item lands (_reflow): the places still to be laid
    # out, the page as measured after the erases, and the boxes that are fixed.
    JOB.plan["reflow"] = {"specs": [dict(p) for p in places], "first_free_y": info.get("first_free_y"),
                             "marks": marks, "obstacles": obstacles, "text_col": H._text_col(doc, page)}
    # A PICTURE REDONE IN ITS PLACE LANDS FIRST: its new size is only known once it is drawn, and the stacked
    # things of the same job then flow below what actually landed.
    _redo_steps = [q for q in plan_steps if q.get("place") in redo]
    if _redo_steps:
        _rest = [q for q in plan_steps if q not in _redo_steps]
        _k = next((i for i, q in enumerate(_rest) if ST.TIER.get(q["do"], 2) >= 2), len(_rest))
        plan_steps[:] = _rest[:_k] + _redo_steps + _rest[_k:]
    JOB.plan.update({"places": boxes, "erase_sigs": sigs, "erase_named": named})
    # THE LAYOUT, in the log: which step went where, and how it was asked for
    H.log("  layout: " + "; ".join(
        "%d %s near=%s%s -> %s" % (q["id"], q["do"], q.get("near") or "stack",
                                  ("/" + q["side"]) if q.get("side") else "",
                                  ("x %d..%d y %d..%d" % (boxes[q["place"]]["x0"], boxes[q["place"]]["x1"],
                                                          boxes[q["place"]]["y0"], boxes[q["place"]]["y1"]))
                                  if q.get("place") in boxes else ("new page" if q.get("new_page") else "-"))
        for q in plan_steps if q["do"] in ST.PLACE_KIND))
    # The host runs every step it can before the model is asked anything, so what comes back here is already
    # the state after the erases and searches have happened.
    H._drain_host_steps()
    out = {"ok": True, "steps": [dict(q) for q in plan_steps], "layout": boxes,
           "note": ST.brief(plan_steps)}
    if named:
        out["will_erase_at_commit"] = named
    if words:
        out["you_erase_before_done"] = words
    return out


def t_need_step(do, what=None, size=None, near=None, side=None, query=None, place=None,
                about=None, prompt=None):
    """Ask for a step the plan did not have (the search came back useless, say).

    A plan written before the data is in cannot know what the data will say; this is the way to change it,
    rather than the model doing something that was never planned.
    """
    steps = JOB.steps or []
    if not steps:
        return dict({"error": "plan() first."}, **H._did())
    raw = {"do": do, "what": what or query or about or prompt, "size": size, "near": near,
           "side": side, "place": place}
    raw = dict((k, v) for k, v in raw.items() if v is not None)
    try:
        added = H._add_step(raw)
    except ST.StepError as ex:
        return dict({"error": str(ex)}, **H._did())
    except H._NoRoom as ex:
        return dict({"error": "no room for that step: %s" % str(ex)[:120]}, **H._did())
    H._drain_host_steps()
    return dict({"ok": True, "added": ST.describe(added), "note": ST.brief(steps)}, **H._did())


def _add_step(raw):
    """A step the plan did not have, put in before the current one -- right after the step just
    finished -- and, if it puts something on the page, given a box below everything. -> the step.
    Raises ST.StepError for a step that makes no sense, _NoRoom when the page has no room for it
    (the step stays in the list, without a box)."""
    steps = JOB.steps or []
    added = ST.insert_before(steps, ST.current(steps), raw)
    H.log("  step inserted: %s" % ST.describe(added))
    if added["do"] in ST.PLACE_KIND and not added.get("place"):
        # a content step needs a box: lay the new one out below everything, on its own
        try:
            p = ST.place_for(added)
            # A PLACE OF ITS OWN, named after the step's id: inserting renumbers the steps, so a name taken from
            # its number could collide with a place the plan already has and overwrite its box
            have = ((JOB.plan or {}).get("places") or {})
            base, k = p["id"], 2
            while p["id"] in have:
                p["id"] = "%s-%d" % (base, k)
                k += 1
            info = H.t_page_info()
            low = max([info.get("first_free_y") or H._safe()[1]] +
                      [b["y1"] + PL.GAP for b in ((JOB.plan or {}).get("places") or {}).values()])
            b = PL.solve([p], first_free_y=low, safe=H._safe(), text_col=H._text_col())[p["id"]]
            (JOB.plan or {}).setdefault("places", {})[p["id"]] = b
            added["place"] = p["id"]
        except Exception as ex:
            raise H._NoRoom(str(ex))
    return added


def t_skip(note):
    """Finish having changed NOTHING, including abandoning a bad drawing: nothing is committed until the rounds
    are done, so the draft is simply dropped."""
    if JOB.committed:
        return dict({"error": "you have already written to the page, so this "
                              "was not a skip. Use done() and say what you "
                              "changed -- or erase what you added first."},
                    **H._did())

    JOB.outcome, JOB.note = "skipped", note
    return {"ok": True, "recorded": "skipped"}


def t_ask(lines):
    """Ask the user for what the request cannot be done without, and leave the request on the page: written like
    an answer, under what is on the page, and nothing comes off. The user's reply brings the page back as a new
    job, which does the work and erases the request, the reply and this question."""
    JOB.asking = True
    return H._reply(lines, task="asked the user for what the request needs")


def tool_schema():
    """The tools, rendered ONCE: the tool list is part of the cached prompt prefix, so it is byte-identical from
    call to call and from job to job. A step's `do` is an enum of the step kinds this lineup's features offer."""
    if H._SCHEMA is not None:
        return H._SCHEMA
    out = []
    off_steps, off_tools = H._off_steps_and_tools()
    kinds = [k for k in ST.KINDS if k not in off_steps]

    def fill(v):
        if isinstance(v, dict):
            return {k: (kinds if x == STEP_KINDS else fill(x)) for k, x in v.items()}
        if isinstance(v, list):
            return [fill(x) for x in v]
        return v
    for name, desc, params, _ in H.TOOLS:
        if name in off_tools:                        # a tool of a feature this lineup has off is not offered
            continue
        props, optional = {}, set()
        for k, ty in params.items():
            if isinstance(ty, dict):          # raw JSONSchema, used verbatim
                spec = fill(dict(ty))
                if spec.pop("optional", False):
                    optional.add(k)
                props[k] = spec
            elif ty == "array":
                props[k] = {"type": "array", "items": {"type": "string"}}
            else:
                props[k] = {"type": ty}
        out.append({"type": "function", "function": {
            "name": name, "description": desc,
            "parameters": {"type": "object", "properties": props,
                           "required": [k for k in params if k not in optional]}}})
    H._SCHEMA = out
    return out


def _prefs_sentence():
    """How the user writes temperatures, times and weeks, for what the model writes itself; where a request for
    posts looks when it names no site; and whether PaperDaemon may reach the internet at all."""
    p = H._CT.prefs()
    out = (" Write temperatures in %s, times on a %s clock (%s), and weeks from %s."
           % ("Celsius" if p["temperature"] == "celsius" else "Fahrenheit",
              "24-hour" if p["clock"] == "24" else "12-hour", "14:30" if p["clock"] == "24" else "2:30 PM",
              p["week_start"].capitalize()))
    if (H._CT._setting("network") or {}).get("allowed") is False:
        return out + " The internet is off: no web search, weather, social posts or Wikipedia."
    sites = [_SITE_NAMES.get(x, x) for x in ((H._CT._setting("social") or {}).get("sites") or [])]
    if sites:
        out += " Social posts asked for without a site come from %s; a site the request names is always used." % (
            ", ".join(sites[:-1]) + " and " + sites[-1] if len(sites) > 1 else sites[0])
    return out


def system_brief():
    """The system prompt. STATIC: nothing in it changes between jobs, so the server's cached prompt prefix holds.
    The date and the time are said in the first user message instead, after the cached part.
    """
    if H._BRIEF is None:
        H._BRIEF = (H.BRIEF.replace("<<CALENDAR>>", CAL_BRIEF["page"])
                       .replace("<<PICTURES>>", H.pictures_brief(H._image_offer()))
                       .replace("<<HOME>>", ((" The user lives in %s." % H.HOME_PLACE) if H.HOME_PLACE
                                else " The user's place is not set.") + H._prefs_sentence())
                       .replace("<<SAFE_X0>>", str(int(H._safe()[0]))).replace("<<SAFE_X1>>", str(int(H._safe()[2])))
                       .replace("<<SAFE_Y0>>", str(int(H._safe()[1]))).replace("<<SAFE_Y1>>", str(int(H._safe()[3]))))
        extra = (H._harness().get("brief_additions") or "").strip()
        if extra:
            H._BRIEF += "\n\n" + extra
        off = H._off_steps_and_tools()[0]
        H._BRIEF = H._BRIEF.replace("<<STEPS>>", ST.brief_list([k for k in ST.KINDS if k not in off]))
    return H._BRIEF


def _off_features():
    """The features this lineup has switched off (the run file's resolved features), by name."""
    return {n for n, st in (H.RUN.get("features") or {}).items() if (st or {}).get("state") == "off"}


def _off_steps_and_tools():
    """The step kinds and the tools no enabled feature offers: a step or tool of a feature that is off, unless
    another feature that is on offers it too."""
    from paperdaemon.pipeline import features as F
    off = H._off_features()
    if not off:
        return set(), set()
    cat = F.Catalog()
    on_steps = {s for f in cat.by_name.values() if f.name not in off for s in f.steps}
    on_tools = {x for f in cat.by_name.values() if f.name not in off for x in f.tools}
    steps = {s for f in cat.by_name.values() if f.name in off for s in f.steps} - on_steps
    tools = {x for f in cat.by_name.values() if f.name in off for x in f.tools} - on_tools
    return steps, tools


def pictures_brief(offer):
    """What the brief says about the active image model, from its harness: its abilities, its workflows
    (a coloring step is the coloring book one) and the steps it takes. Static for a lineup, so the
    cached prompt prefix holds from job to job; the engine restarts the host when it changes."""
    if not offer:
        if os.environ.get("RM_RUN"):
            return ("THERE IS NO IMAGE MODEL in this lineup: image and coloring steps cannot be made; say so "
                    "rather than planning one.")
        # a host run without the engine's harness file: the default image model's steps
        offer = {"name": "", "abilities": [], "workflows": {}, "steps": 4, "steps_range": [4, 12]}
    can = [_ABILITY_WORDS[a] for a in offer.get("abilities") or () if a in _ABILITY_WORDS]
    lines = []
    if offer.get("name"):
        said = (can[0] if len(can) == 1 else " and ".join(can) if len(can) == 2
                else ", ".join(can[:-1]) + ", and " + can[-1]) if can else ""
        lines.append("THE IMAGE MODEL is %s%s." % (offer["name"], (": it " + said) if said else ""))
    wfs = offer.get("workflows") or {}
    if wfs:
        lines.append("Its WORKFLOWS -- name one as workflow on an image step; a coloring step is %s unless it "
                     "names another. A workflow brings its own wording and style, so what says only what the "
                     "picture shows (\"an owl on a branch\"); without one, your words go to the model exactly as "
                     "you write them:" % H.COLORING_BOOK)
        for n, w in sorted(wfs.items()):
            w = w if isinstance(w, dict) else {"about": str(w)}
            lines.append("  %s -- %s%s" % (n, w.get("about") or "", " (it starts from a picture on the page: "
                                                                   "give source=\"picture:N\")" if w.get("reference") else ""))
    lo, hi = (list(offer.get("steps_range") or []) + [None, None])[:2]
    dflt = offer.get("steps")
    if lo is not None and hi is not None and lo < hi:
        lines.append("steps and seed, on image and coloring: leave steps out (%s) unless the picture is "
                     "complex, the user was unhappy with an earlier render, or they ask for more effort, then up "
                     "to %s; a number of steps or a seed the user names goes in exactly, whatever the number: "
                     "\"steps\": N, \"seed\": N." % (dflt, hi))
    else:
        lines.append("steps and seed, on image and coloring: leave steps out (this model takes %s); a number of "
                     "steps or a seed the user names goes in exactly, whatever the number: \"steps\": N, "
                     "\"seed\": N." % dflt)
    return "\n".join(lines)


def _turn(msgs, allowed, tries=3, choice="required", accept_prose=False, final=None, temperature=None):
    """One model turn that has to end in one of `allowed`.

    Returns (fn, args, result) for the first allowed call that succeeded. Looks (show_marks, look_closer, find,
    render) are served and the model is re-asked; a call that is not allowed right now is refused with the
    list; a refused or failed call gets its error back and one more go. `tries` bounds it. With accept_prose, a
    reply with no call is an answer in itself ("ok") and comes back as (None, None, {"said": text}).

    `final` names the calls that END the turn; any other allowed call is a HELPER (history() before a calendar,
    say): it runs, its result goes back, and the model is asked again.
    """
    last = None
    looks = 0
    helpers = 0
    # THE DECISION'S LOOKING IS BOUNDED BY TOKENS, never by a count or a clock: what the inspections add to the
    # conversation and what the model writes, against the harness's budget; the same look twice is refused
    deciding = set(allowed) == set(H.PLAN_TOOLS)
    budget = int(getattr(H._H(), "inspect_tokens", 12000) or 12000)
    start_tokens, spent, asked = None, 0, set()
    for _ in range(tries + 4):
        try:
            m, usage, cut = H.chat(msgs, tool_choice=choice, temperature=temperature)
        except Exception as ex:
            H.log("  model error: %s" % str(ex)[:120])
            return None, None, {"error": "model: %s" % str(ex)[:100]}
        used = usage.get("prompt_tokens") or 0
        JOB.ctx_peak = max(JOB.ctx_peak, used)
        if deciding:
            start_tokens = used if start_tokens is None else start_tokens
            spent = (used - start_tokens) + (usage.get("completion_tokens") or 0)
        said = (m.get("content") or "").strip()
        calls = H._H().calls(m)
        # prose here is a reply that should have been a call; it is never taken as the request
        if usage.get("runaway"):
            msgs.extend(H._H().nudge_runaway(said, allowed))
            tries -= 1
            if tries < 0:
                return None, None, {"error": "the model kept repeating itself"}
            continue
        if not calls:
            if accept_prose:
                msgs.append({"role": "assistant", "content": said or "ok"})
                return None, None, {"said": said}
            H.log("  no tool call -- %s" % said[:80])
            # what it said goes back short, so a long prose reply does not fill the retry's context
            msgs.extend(H._H().nudge_no_call(said, allowed))
            tries -= 1
            if tries < 0:
                return None, None, {"error": "no tool call in %d tries" % (tries + 1)}
            continue
        msgs.append({"role": "assistant", "content": m.get("content"), "tool_calls": calls})
        got = None
        round_helpers = 0
        for c in calls:
            call = H._H().read_call(c, cut)
            fn, cid, args = call.name, call.id, call.args
            if call.error:
                msgs.append({"role": "tool", "tool_call_id": cid, "content": json.dumps({"error": call.error})})
                last = {"error": call.error}
                continue
            H.log("  -> %s(%s)" % (fn, json.dumps(args)[:700 if fn in ("plan", "answer", "write_paragraph") else 100]))   # a plan and a reply whole
            if fn in H.LOOK_TOOLS and fn != "find":
                key = (fn, json.dumps(args, sort_keys=True))
                if deciding and key in asked:
                    msgs.append({"role": "tool", "tool_call_id": cid, "content": json.dumps(
                        {"error": "already shown: that look is above. Decide: one of %s." % ", ".join(allowed)})})
                    continue
                if deciding and spent >= budget:
                    msgs.append({"role": "tool", "tool_call_id": cid, "content": json.dumps(
                        {"error": "the looking is done (its budget is spent). Decide now: one of %s."
                                  % ", ".join(allowed)})})
                    continue
                asked.add(key)
                H._serve_look(fn, args, cid, msgs, JOB.doc, JOB.page)
                looks += 1
                continue
            if fn not in allowed:
                msgs.append({"role": "tool", "tool_call_id": cid, "content": json.dumps(H._H().nudge_refused(allowed))})
                last = {"error": "called %s instead of %s" % (fn, "/".join(allowed))}
                continue
            if fn in H.PLAN_TOOLS and "remember" in args:
                args = dict(args)
                JOB.remember = args.pop("remember")     # applied when the job ends (memories)
            try:
                res = H.DISPATCH[fn](**args) if fn in H.DISPATCH else {"error": "no such tool"}
            except TypeError as ex:
                res = {"error": "bad arguments: %s" % str(ex)[:110]}
            except Exception as ex:
                res = {"error": "%s: %s" % (type(ex).__name__, str(ex)[:100])}
            msgs.append({"role": "tool", "tool_call_id": cid, "content": json.dumps(res)[:1500 if fn in ("history", "web_search") else 600]})
            if isinstance(res, dict) and not res.get("error"):
                H._close_step(fn)
                if final is not None and fn not in final:
                    helpers += 1                  # gathered something; the step is still open
                    round_helpers += 1
                    continue
                if got is None:
                    got = (fn, args, res)
            else:
                # why a call was refused, in the log
                H.log("  %s refused: %s" % (fn, str((res or {}).get("error") if isinstance(res, dict) else res)[:220]))
                last = res
        if got is not None:
            return got
        if looks > 3 and not deciding:
            return None, None, {"error": "kept looking without acting"}
        if deciding and spent >= budget and not got and looks:
            tries -= 1                            # past the budget, every round without a decision is a try
        if helpers > 4:
            return None, None, {"error": "kept gathering without doing the step"}
        if round_helpers:
            msgs.append(H._H().nudge_gathered(final or allowed))
            continue                              # a helper round is not a failed try
        tries -= 1
        if tries < 0:
            return None, None, last or {"error": "no usable call"}
    return None, None, last or {"error": "no usable call"}


def step_message(cur):
    steps = JOB.steps or []
    box = ((JOB.plan or {}).get("places") or {}).get(cur.get("place"))
    L = ["STEP %d OF %d: %s." % (cur["id"], len(steps), ST.describe(cur))]
    if box:
        L.append("Its box: x %d..%d, y %d..%d (center %d, %d; %d wide, %d tall). What you make for "
                 "this step lands there." % (box["x0"], box["x1"], box["y0"], box["y1"], box["cx"],
                                            box["cy"], box["w"], box["h"]))
    if cur.get("replaces_picture"):
        L.append("This REDOES picture:%d, which comes off the page when the new one lands. %s"
                 % (cur["replaces_picture"],
                    ("It was made from this spec -- start from it, keep what it had, and change or add "
                     "what is asked (a week's events and cards go under \"days\", a month's under "
                     "\"marks\"): %s" % json.dumps(H._as_shown(cur["base_spec"]))[:1500])
                    if cur.get("base_spec") else "Make the whole replacement."))
    for q in steps:
        if q["do"] == "search" and q["status"] == "done" and q.get("results"):
            L.append("Search results for %r: %s" % (q["what"][:60], q["results"][:3200]))
    if cur.get("posts_found"):
        f = cur["posts_found"]
        try:
            n = max(1, min(4, int(cur.get("count") or 4)))
        except (TypeError, ValueError):
            n = 4
        L.append("POSTS FROM A WEB SEARCH: %s cannot be listed by a program, so the host searched the web for %r. "
                 "Call chart({\"type\": \"posts\", \"title\": .., \"posts\": [..]}) with up to %d posts these "
                 "results show. Give each post every field the results support: %s. Leave out a field the results "
                 "do not say. Results: %s"
                 % (cur.get("source"), f.get("query"), n, H.POST_FIELDS,
                    json.dumps(f.get("results") or [], ensure_ascii=False)[:5000]))
    # WHAT THE CHART TOOL CAN DO, said at the moment it is used (rm_chart.POWERS -- one line per
    # type, kept beside the validator). A calendar step gets the calendar and week lines in full;
    # a chart step gets every type, so it picks the one that fits instead of the three it knows.
    if cur["do"] == "write":
        figs = H._chart_figures()
        if figs:
            L.append(figs)
    if cur["do"] == "calendar":
        L.append("WHAT A CALENDAR CAN CARRY -- use it:\n" + CH.powers(["week", "calendar"]))
        facts = H._calendar_facts(cur)
        if facts:
            L.append(facts)
    elif cur["do"] == "chart" and not cur.get("posts_found"):
        L.append("WHAT chart(spec) CAN DRAW -- pick the type that fits the data and the ask; the host "
                 "fills in what is marked AUTOMATIC:\n" + CH.powers())
    want = {"write": "write_paragraph(lines) -- the host places and wraps them; say what the step deserves",
            "chart": "chart(spec) with the data; the host places it",
            "calendar": "chart(spec): {\"type\": \"calendar\", \"year\": .., \"month\": ..} or "
                        "{\"type\": \"week\"}, its cards from the on-this-day facts above",
            "draw": "draw_figure(parts) for something you can say exactly, element(name, cx, cy, r) "
                    "for one small shape, or image(prompt) for something that has to look real -- "
                    "inside the box"}.get(cur["do"], "the tool for it")
    L.append("Call %s. Only this step; the host moves you on." % want)
    return "\n".join(L)


def _conflict_turn(harness, doc_id, page, wake, conflict):
    """A CONFLICT job's first turn after the system message: the user's page and the job's set-aside copy as two
    pictures (the copy read from its own file, the mirror untouched), and what the job did."""
    yours = os.path.join(H.QUEUE, "_host_yours.png")
    ours = os.path.join(H.QUEUE, "_host_ours.png")
    R.render(doc_id, page, yours, typed=True)
    with R.reading(doc_id, JOB.page_id, conflict["ours"]):
        R.render(doc_id, page, ours, typed=True, blank_ok=True)
    return harness.conflict(H._host(), yours, ours, (conflict.get("made_by") or "(not recorded)") + "\n\n" + wake)


# the tools this module serves, as the host offers them (the host's TOOLS keeps this order)
TOOLS = [
 ("plan", "Your ONE decision for a page that asks for work other than plain words: its steps, in order "
  "(PLAN STEPS), and your RULINGS on the page.",
  # each nested object declares only its required keys, in the order a model writes them (the server's grammar
  # holds an object's declared keys to their declared order); a step's other fields are free and named in PLAN STEPS
  {"steps": {"type": "array", "items": {"type": "object", "description":
       "One step: do, what and answers, then any of its kind's fields (PLAN STEPS), in any order.",
       "properties": {"do": {"type": "string", "enum": STEP_KINDS}, "what": {"type": "string"},
                      "answers": RU.ANSWERS},
       "required": ["do", "what", "answers"], "additionalProperties": True}},
   "rulings": RU.RULINGS, "remember": H.REMEMBER}, t_plan),
 ("answer", "Your ONE decision when the whole job is WORDS -- a question, a greeting, a fact, an opinion, a list. "
  "answers = the ids of what it answers; lines = the reply, one string per line, at the length the question "
  "deserves (the host fits it to the page); rulings = your RULINGS on the page. Written below what is on the page, "
  "in the text column, and put on the page at once.",
  {"answers": RU.ANSWERS, "lines": "array", "rulings": RU.RULINGS, "size": {"type": "number", "optional": True},
   "remember": H.REMEMBER}, t_answer),
 ("ask", "Your ONE decision when the request cannot be done without something only the user can tell "
  "you (ASKING): lines = your question, in your own words, one string per line. It is written under the "
  "request and nothing comes off; the request stays until the user's reply lets a later job do it.",
  {"lines": "array", "remember": H.REMEMBER}, t_ask),
 ("skip", "Your ONE decision when THIS page asks for nothing, or when this notebook's system prompt "
  "says to leave it alone: say what is on it and why you are not acting. Nothing changes. What "
  "another page answered never answers a request on this one.", {"note": "string", "remember": H.REMEMBER},
  t_skip),
 ("need_step", "The plan missed something -- a search that came back useless, a second chart you only "
  "now know you need. Adds one step BEFORE the one you are on; same shape as a step in plan().",
  {"do": {"type": "string", "enum": STEP_KINDS}, "what": {"type": "string"},
   "size": {"type": "string", "optional": True}, "near": {"type": "string", "optional": True},
   "side": {"type": "string", "optional": True}},
  t_need_step),
]
