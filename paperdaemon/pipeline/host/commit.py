"""The draft and the commit: what a job stages (strokes, typed text, pictures, erasures), checks, and writes to the page at the end."""
import os
import re
import time
from paperdaemon import ledger as S
from paperdaemon.pipeline import page as ER
from paperdaemon.pipeline.host import layout as PL
from paperdaemon.pipeline.host import steps as ST
from paperdaemon.pipeline.host.job import JOB
from paperdaemon.pipeline.page import render as R
from paperdaemon.pipeline.page import typed as TY
from paperdaemon.remarkable import sync as C
from paperdaemon.pipeline import host as H



def _hide():
    """Every stroke signature the page will lose at commit(): staged erasures plus what the plan
    named by mark number (and the anchor arrow), so previews show the page as it will be."""
    h = set(JOB.hide or {})
    plan = JOB.plan or {}
    if plan and not plan.get("erase_done"):
        h |= set(plan.get("erase_sigs") or [])
    return h


def _staged():
    """Anything erased in the draft but not yet committed, including the ink the PLAN named by mark number
    (as _hide() counts it): a job that only erases ink still has something to commit."""
    plan = JOB.plan or {}
    return bool(JOB.hide or JOB.hide_typed or JOB.hide_images
                or (plan.get("erase_sigs") and not plan.get("erase_done")))


def _stage(why, sigs=(), typed=(), images=()):
    """Record one erasing op: what it hides, so undo_last() can put exactly that back."""
    H._mark()
    JOB.ops.append(why)
    hide = JOB.hide
    for g in sigs:
        hide[g] = why
    JOB.hide_typed.extend(typed)
    JOB.hide_images.extend(images)
    JOB.erase_log.append({"op": len(JOB.ops), "why": why, "sigs": list(sigs),
                                            "typed": list(typed), "images": list(images)})


def _unstage(op_index):
    """Drop the erasing op with this 1-based index and rebuild what is hidden from the rest."""
    log_ = [e for e in (JOB.erase_log or []) if e["op"] != op_index]
    JOB.erase_log = log_
    JOB.hide = dict((g, e["why"]) for e in log_ for g in e["sigs"])
    JOB.hide_typed = [t for e in log_ for t in e["typed"]]
    JOB.hide_images = [b for e in log_ for b in e["images"]]


def _mark():
    """Stroke count before the current operation, so undo_last can rewind."""
    JOB.marks.append(len(JOB.draw.strokes))


def _drew():
    """True if this job has drawn a FIGURE on the draft, something worth the rounds of looking. A single
    element (one star, one tick) is not."""
    return any(op.startswith(("figure", "image"))
               for op in JOB.ops)


def t_undo_last(parts=1):
    """Take back the last thing(s) drawn, without binning the whole draft: `Drawing.strokes` is a plain
    list, so the last N operations can simply be dropped."""
    n = max(1, int(parts))
    if not JOB.ops:
        return dict({"error": "nothing drawn yet"}, **H._did())
    marks = JOB.marks or []
    kept = len(JOB.draw.strokes)
    for _ in range(min(n, len(JOB.ops))):
        idx = len(JOB.ops)
        JOB.ops.pop()
        kept = marks.pop() if marks else 0
        H._unstage(idx)                    # an erasing op: the strokes come back
    del JOB.draw.strokes[kept:]
    return dict({"ok": True, "strokes_left": len(JOB.draw.strokes),
                 "note": "render() to see what is left"}, **H._did())


def _page_box():
    """The coloring box a FRESH page gets: what the planner gives a full coloring place there."""
    return PL.solve([{"id": "page", "kind": "coloring", "size": "full", "near": "stack"}],
                    first_free_y=H._safe()[1], safe=H._safe(), screen=H._screen())["page"]


def _new_page():
    """Add a page to the job's notebook, right after the page that asked -> (page number, page id, ledger key or
    None).

    The daemon watches this notebook, and a new page with ink on it looks exactly like a new request. So the
    page is entered in the ledger BEFORE anything is drawn on it -- claimed, which the daemon never dispatches --
    with the tag fields of the job's own page, and marked done at its final content by _page_done(). A run with
    no daemon and no keys skips the ledger."""
    from paperdaemon.remarkable import library as PG
    from paperdaemon import ledger as S_
    doc = JOB.doc
    # RIGHT AFTER the page that asked, behind any page this job has already added: what a job makes goes next to
    # where it was asked for, and the pages after it move down
    after = (JOB.added_pages or [JOB.page_id])[-1]
    pid = PG.insert_pages(doc, after, 1)[0][0]
    JOB.added_pages.append(pid)
    live = R.live_pages(doc)
    pno = [p["id"] for p in live].index(pid) + 1
    key = None
    src = (S_.load()["entries"].get((JOB.keys or [None])[0]) if JOB.keys else None)
    if src:
        with S_.locked():
            led = S_.load()
            key = "%s/%s" % (doc[:8], pid[:8])
            now = int(time.time())
            e = dict((k, src.get(k)) for k in ("doc", "doc_id", "tag", "instruction", "tag_ts", "inherited"))
            e.update(page_id=pid, page=pno, first_seen=now, last_seen=now, status="working",
                     claim_owner="host", claim_at=now, note="a page this system is making")
            led["entries"][key] = e
            S_.save(led)
    return pno, pid, key


def _page_done(key, what):
    if key:
        from paperdaemon import ledger as S_
        S_.mark(key, "done", what)


def _stage_tag(what):
    """A tag for THIS page, put on at commit -> (ok, note). The decision's quote vouched that the user named it (in
    this notebook's instructions or on this page: validity rule 7), so the model never tags a page on its own.
    "ignore" is how a notebook says a finished page is never worked on again: the daemon never dispatches it."""
    name = str(what or "").strip().strip("\"'“”‘’").strip()
    if not name or len(name) > 40:
        return False, "say the tag's name, as the user wrote it"
    if name.lower() not in [t.lower() for t in JOB.tags]:
        JOB.tags.append(name)
    return True, "tag %r goes on at commit" % name


def t_commit():
    """Actually write the draft onto the page. Additive, never destructive."""
    # a plan comes first: it is what places things and says what the job is
    if not JOB.plan:
        return dict({"error": "call plan() first. Say what this page asks for, what you are "
                              "putting on it and roughly how big -- the layout is worked out for "
                              "you and nothing can then overlap."}, **H._did())
    # THE PAGE BY ITS ID (_repage): by now the number may point at a different page. Writing nowhere beats
    # writing on the wrong sheet.
    if H._repage() is None:
        return dict({"error": "this job's page is no longer in the notebook's page list -- it changed "
                              "while the job ran (a tablet sync without it). Nothing was written."},
                    **H._did())
    # Guard on the DRAFT, not on the op list (which never empties), so a second commit cannot write the draft
    # again on top of the first. One write per drawing, at the end: once committed the ink is real and
    # undo_last, which only rewinds the draft, cannot take it back, so the rounds happen in the draft.
    if H._drew() and JOB.looks < H.DRAW_ROUNDS:
        return dict({"error": "not yet. The draft is free to change until you "
                              "commit, and committing early puts ink on the "
                              "page that undo_last cannot take back. Finish "
                              "your %d rounds, then commit once."
                              % H.DRAW_ROUNDS}, **H._did())
    if not JOB.draw.strokes and not (JOB.images or []) and not H._staged():
        return dict({"error": "nothing new to commit -- the draft is empty and nothing is staged "
                              "for erasing. Everything you have done is already on the page; "
                              "render(), then done()."}, **H._did())
    # DID THE PLAN ACTUALLY HAPPEN? Refuses once: a gate that cannot be passed is worse than none.
    plan = JOB.plan or {}
    if plan.get("places") and not plan.get("warned"):
        empty = [b["id"] for b in plan["places"].values()
                 if not PL.covered(b, JOB.draw.strokes)
                 and not any(im.get("place") == b["id"] for im in (JOB.images or []))]
        # THE DRAWING DECIDES, NOT THE BOX: ink that lies in no planned box is a figure the model placed where
        # it chose, and it covers the empty place.
        if empty:
            boxes = list(plan["places"].values())
            stray = [s for s in JOB.draw.strokes
                     if not any(PL.covered(b, [s]) for b in boxes)]
            if stray:
                H.log("  plan: %s empty, but %d stroke(s) lie outside every box -- taking them as the "
                    "figure" % (", ".join(empty), len(stray)))
                empty = []
        if empty:
            plan["warned"] = True
            return dict({"error": "you planned %s but nothing was drawn there. Either put "
                                  "something in %s, or commit again if you have changed your mind."
                                  % (", ".join(repr(e) for e in empty),
                                     "it" if len(empty) == 1 else "them")}, **H._did())
    doc, page = JOB.doc, JOB.page
    # a change to the page that is not this job's own, made while it worked (see run_job)
    try:
        ref = JOB.sha_commit or JOB.sha_start
        if ref and S.page_state(doc, JOB.page_id)["sha"] != ref:
            JOB.foreign = True
            H.log("  the page changed under the job before it wrote (not by the job)")
    except Exception:
        pass
    from paperdaemon.pipeline import page as P
    P.record(doc, page, note="before rm_host commit")
    name = S.meta(doc).get("visibleName", doc)

    # RECORD PROVENANCE, so whose() can tell this system's strokes from the user's and "delete the thing you
    # drew" never risks the user's ink. The signatures are read off the PAGE after the write (since= a snapshot
    # taken before it), so they cannot drift from what whose() computes later.
    # ERASURES GO FIRST -- everything staged in the draft, plus what the plan named by mark number (and the
    # arrow a place sat at). One cut, by stroke signature, then the new ink goes on.
    kill = set(JOB.hide or {})
    if not plan.get("erase_done"):
        kill |= set(plan.get("erase_sigs") or [])
    erased_n = 0
    # A FAILED ERASE IS NOT A QUIET ONE: it is a problem of the commit, not a log line (see _snap()).
    erase_failed = []
    if kill:
        try:
            H._snap("commit: erase")
            r_ = ER.erase(doc, page, lambda L: P.skey(L) in kill)
            erased_n = r_.get("erased", 0)
            plan["erase_done"] = True
            H.log("  ERASED %d strokes at commit (%d staged, %d planned) from %s p%s"
                % (erased_n, len(JOB.hide or {}), len(plan.get("erase_sigs") or []),
                   doc[:8], page))
        except Exception as ex:
            H._warn("erase at commit", ex)
            erase_failed.append("strokes: %s: %s" % (type(ex).__name__, str(ex)[:90]))
    pics_gone = 0
    for _hb in JOB.hide_images or []:
        try:
            from paperdaemon.pipeline.page import images as IM
            pics_gone += IM.remove_in_box(doc, page, tuple(_hb)) or 0
        except Exception as ex:
            H.log("  picture NOT removed: %s" % str(ex)[:80])
    overflow = H._validate_draft(doc, page)
    before = P.snapshot(doc, page)
    res = {"strokes": 0}
    if JOB.draw.strokes:
        res = JOB.draw.write_rm(name, page, keep_existing=True)
    if overflow:
        H._write_overflow(name, overflow)
        try:
            H._record_made(doc, page, before)
        except Exception as ex:
            H.log("  provenance NOT recorded: %s" % str(ex)[:90])
    # PICTURES go on after the ink is written: the same page file, the app's own image blocks, the asset beside
    # the page. rm_cloud.push_doc gathers the asset with the page.
    placed = []
    for _im in JOB.images or []:
        try:
            from paperdaemon.pipeline.page import images as IM
            for _ob in _im.get("replaces") or []:
                try:
                    IM.remove_in_box(doc, page, _ob)
                except Exception as ex:
                    H.log("  old picture NOT removed: %s" % str(ex)[:80])
            r_ = IM.insert(doc, page, _im["png"], _im["box"])
            placed.append({"place": _im["place"], "asset": r_["asset"].split("/")[-1],
                           "box": [round(v) for v in _im["box"]]})
            # PROVENANCE FOR PICTURES: where it went and what it is. The position survives the device re-filing it
            # into an anchored group (rm_images._to_page), and the spec lets a later job redo this picture.
            try:
                IM.record_placement(doc, page, r_["asset"].split("/")[-1], _im["box"],
                                    type=_im.get("type"), title=_im.get("title"),
                                    spec=_im.get("spec"))
            except Exception as ex:
                H._warn("recording the picture's placement", ex)
            H.log("  picture placed in %r: %s" % (_im["place"], r_["asset"][-44:]))
        except Exception as ex:
            H.log("  picture NOT placed in %r: %s: %s" % (_im["place"], type(ex).__name__, str(ex)[:100]))
            placed.append({"place": _im["place"], "error": str(ex)[:120]})
    JOB.images = []
    # TYPED TEXT staged for deletion goes last, after the work is on the page.
    typed_gone = 0
    typed_left = []
    for _want in JOB.hide_typed or []:
        try:
            H._snap("commit: erase typed text")
            r_ = ER.erase_text(doc, page, contains=_want)
            typed_gone += r_.get("items", 0)
            H.log("  ERASED typed text matching %r at commit (%d items)"
                % (_want[:40], r_.get("items", 0)))
            # staged, matched at staging time, and then nothing came off: that is a failure, not silence
            if not r_.get("items"):
                erase_failed.append("typed %r: matched nothing in the text block" % _want[:40])
                typed_left.append(_want)
        except Exception as ex:
            H._warn("typed erase at commit %r" % _want[:40], ex)
            erase_failed.append("typed %r: %s: %s" % (_want[:40], type(ex).__name__, str(ex)[:90]))
            typed_left.append(_want)
    # What failed stays STAGED, so a later commit retries it and the erase still counts as outstanding.
    JOB.hide, JOB.hide_images, JOB.erase_log = {}, [], []
    JOB.hide_typed = typed_left
    JOB.committed = True
    try:
        JOB.sha_commit = S.page_state(doc, JOB.page_id)["sha"]    # the page as the job left it
    except Exception:
        pass
    # A commit makes the draft real without changing the picture the model already looked at: the page stays seen.
    JOB.unseen = False
    # A commit CONSUMES the draft: anything drawn after it is new work, and committing twice writes nothing twice.
    JOB.draw = H._drawing()
    JOB.marks = []
    H.log("  committed %s strokes to %s p%s"
        % (res.get("strokes") if isinstance(res, dict) else "?", name, page))
    # A TAG IS THE PAGE'S LAST WORD: it goes on once the page is written and nothing in the job failed (an
    # "ignore" on a page whose picture never came would hide the request for good).
    tags = JOB.take("tags") or []
    if tags and not erase_failed and not ST.failed(JOB.steps or []):
        from paperdaemon.remarkable import library as PG_
        for t_ in tags:
            try:
                if PG_.tag_page(doc, JOB.page_id, t_):
                    H.log("  tagged %s p%s %r" % (name, page, t_))
            except Exception as ex:
                H._warn("tagging the page %r" % t_, ex)
    out = dict({"ok": True, "written": True}, **H._did())
    if erase_failed:
        out["erase_failed"] = erase_failed
        out["note"] = ("THE ERASE DID NOT HAPPEN: %s. The ink you drew is on the page; the text "
                       "that was meant to come off is still there. Quote the words differently "
                       "with erase_typed_text() and commit() again."
                       % "; ".join(erase_failed)[:300])
    if erased_n or pics_gone or typed_gone:
        out["erased"] = {"strokes": erased_n, "pictures": pics_gone, "typed_paragraphs": typed_gone}
    if placed:
        out["pictures"] = placed
    # _did() marks the page unseen, but a commit does not change the picture; cleared after _did().
    JOB.unseen = False
    return out


def _record_made(doc, page, before):
    """Record this commit's strokes as MINE, each with WHAT it is -- the step that made it.

    The next job lists the ink as "mine (draw a small house, 14:20)", so a request about it ("make the house
    bigger") has something to latch onto. A stroke belongs to the content step whose box lies nearest its
    center; a commit with no content steps keeps the ops as its description."""
    from paperdaemon.pipeline import page as P
    boxes = (JOB.plan or {}).get("places") or {}
    steps = [q for q in (JOB.steps or [])
             if q["do"] in ST.PLACE_KIND and boxes.get(q.get("place"))]
    if not steps:
        # the ops that PUT INK DOWN: an erase adds none, so it never describes the ink
        erased = set(e["op"] for e in (JOB.erase_log or []))
        made = [op for i, op in enumerate(JOB.ops, 1) if i not in erased]
        return P.record_provenance(doc, page, since=before, kind="drawing",
                                   what="; ".join(made or JOB.ops)[:200])

    def nearest(s):
        x0, y0, x1, y1 = s["bbox"]
        cx, cy = (x0 + x1) / 2.0, (y0 + y1) / 2.0

        def gap(q):
            b = boxes[q["place"]]
            return max(b["x0"] - cx, 0.0, cx - b["x1"]) + max(b["y0"] - cy, 0.0, cy - b["y1"])
        return min(steps, key=gap)["id"]
    n = 0
    for q in steps:
        n += P.record_provenance(doc, page, since=before, kind=q["do"], what=ST.describe(q)[:120],
                                 only=lambda s, i=q["id"]: nearest(s) == i)
    return n


def _page_room(doc, page):
    """How many more strokes this page can take, counting what is on it and what the draft holds."""
    try:
        have = len(R.strokes(doc, page))
    except Exception:
        have = 0
    return H.PAGE_STROKE_LIMIT - have - len(JOB.draw.strokes)


def _validate_draft(doc, page):
    """validate(), run on the draft just before it is written -> the strokes that continue on a new page.

    1. THE _safe() ZONES: a stroke with any point off the safe area's sides or above its top (under the toolbar) is
       refused, and the job's record says so. BELOW is open: a page scrolls, and the layout runs long content past the
       first screen on purpose; refusing it there cut letters in half and dropped the rest of a reply.
    2. NOT TOO MANY STROKES: past PAGE_STROKE_LIMIT the newest strokes do not go on this page; they continue on a
       new page right after it (pictures were already redone with a lower region budget as they were drawn).
    The harness's own validate() then adds what it refuses (it can add, never remove)."""
    from paperdaemon.pipeline import page as _P
    x0, y0, x1, y1 = _P.safe_area(H._frame())
    keep, out = [], 0
    for st in JOB.draw.strokes:
        if all(x0 <= p[0] <= x1 and y0 <= p[1] for p in st[0]):
            keep.append(st)
        else:
            out += 1
    if out:
        JOB.warnings.append("%d stroke(s) outside the page's safe area were not written" % out)
        H.log("  validate: %d stroke(s) outside the safe area refused" % out)
    JOB.draw.strokes = keep
    try:
        for why in H._H().validate(H._host(), JOB.draw) or []:
            JOB.warnings.append(str(why)[:200])
    except Exception as ex:
        H._warn("the harness's validate()", ex)
    room = H._page_room(doc, page) + len(JOB.draw.strokes)
    if len(JOB.draw.strokes) <= room:
        return []
    cut = max(0, room)
    over = JOB.draw.strokes[cut:]
    JOB.draw.strokes = JOB.draw.strokes[:cut]
    H.log("  validate: the page would pass %d strokes; %d continue on a new page" % (H.PAGE_STROKE_LIMIT, len(over)))
    return over


def _write_overflow(name, strokes):
    """Strokes past the page's limit, on a new page right after it: moved up so the first starts at the safe top."""
    from paperdaemon.pipeline import page as _P
    try:
        pno, pid, key = H._new_page()
        top = min(p[1] for st in strokes for p in st[0])
        dy = _P.safe_area(H._frame())[1] + H.PAD - top
        d = H._drawing()
        d.strokes = [([(p[0], p[1] + dy) for p in st[0]],) + tuple(st[1:]) for st in strokes]
        d.write_rm(name, pno, keep_existing=True)
        H._page_done(key, "the rest of a page that passed %d strokes" % H.PAGE_STROKE_LIMIT)
        JOB.ops.append("%d stroke(s) continued on page %d" % (len(strokes), pno))
    except Exception as ex:
        H._warn("continuing on a new page", ex)


def _finished_page(fp):
    """A page a harness's model finished itself (harnesses.text.FinishedPage) -> problems. Its erasures go through
    the listing's ids exactly as a plan's do, its strokes and pictures into the draft, then the host's own commit
    and the check from the file: the model never writes the page."""
    problems = []
    try:
        H.t_plan([], erase=list(fp.erase or []))
        H._drain_host_steps()
    except Exception as ex:
        problems.append("its erasures were refused: %s" % str(ex)[:120])
        return problems
    for s in fp.strokes or []:
        pts = [(float(p[0]), float(p[1])) for p in (s.get("points") or []) if len(p) >= 2]
        if len(pts) >= 2:
            JOB.draw.stroke(pts, width=int(s.get("width") or 24))
    for k, pic in enumerate(fp.pictures or []):
        x0, y0, x1, y1 = [float(v) for v in pic["box"]]
        apath, box = H._picture_asset(pic["png"], {"x0": x0, "y0": y0, "w": x1 - x0, "h": y1 - y0})
        JOB.images.append({"place": "finished-%d" % k, "png": apath, "box": box, "type": "image",
                                              "title": "", "spec": None, "replaces": []})
    if fp.strokes or fp.pictures:
        H._mark()
        JOB.ops.append("the model's own page: %d stroke(s), %d picture(s)%s"
                          % (len(fp.strokes or []), len(fp.pictures or []), (" -- " + fp.note[:120]) if fp.note else ""))
    if JOB.draw.strokes or JOB.images or H._staged():
        r = H._host_commit()
        if r.get("error"):
            problems.append("commit refused: %s" % str(r["error"])[:120])
    return problems + H._verify(JOB.doc, JOB.page)


def _host_commit():
    """The host's commit: the same write as commit(), without the gates that make a model look first: the host
    has already decided, and checks the file afterwards instead."""
    JOB.looks = max(JOB.looks, H.DRAW_ROUNDS)
    JOB.unseen = False
    plan = JOB.plan or {}
    if plan:
        plan["warned"] = True            # empty places are reported by _verify, not refused here
    r = H.t_commit()
    if r.get("error"):
        H.log("  commit refused: %s" % str(r["error"])[:140])
    return r


def _verify(doc, page):
    """Read the PAGE FILE back and compare it with the plan -> a list of what did NOT happen.

    Is each erased paragraph gone, are the erased strokes gone, did each content step put something in its box,
    which steps failed. What it finds goes into the ledger note verbatim, so the user reads what happened, not
    what was claimed.
    """
    out = []
    steps = JOB.steps or []
    plan = JOB.plan or {}
    try:
        paras = [str(p.get("text", "")) for p in TY.paragraphs(doc, page)[1]]
    except Exception:
        paras = None
    try:
        from paperdaemon.pipeline import page as _P
        strokes = R.strokes(doc, page)
        keys = set(_P.skey(l) for l in strokes)
    except Exception:
        strokes, keys = [], None
    for q in steps:
        if q["status"] == "failed":
            out.append("step %d (%s) failed: %s" % (q["id"], ST.describe(q), q.get("note", "")))
            continue
        if q["status"] != "done":
            out.append("step %d (%s) was never done" % (q["id"], ST.describe(q)))
            continue
        if q["do"] == "erase":
            for kind, v in ST.erase_targets(q["what"]):
                if kind == "para" and paras is not None:
                    if int(v) in (JOB.kept_paras or ()):
                        continue                    # a question the host kept on purpose
                    src = JOB.paras or []
                    want = src[int(v) - 1] if 0 < int(v) <= len(src) else None
                    nw = ER._normalize(want)[0] if want else ""
                    if nw and any(nw in ER._normalize(t)[0] for t in paras):
                        out.append("typed paragraph %s is still on the page" % v)
                elif kind == "all_ink" and keys is not None:
                    left = JOB.keys_before & keys
                    if left:
                        out.append("%d of the strokes to erase are still there" % len(left))
                elif kind == "picture":
                    name_ = (JOB.erased_pictures or {}).get(int(v))
                    try:
                        from paperdaemon.pipeline.page import images as IM
                        if name_ and any(im.get("name") == name_ for im in IM.items(doc, page)):
                            out.append("picture %s is still on the page" % v)
                    except Exception:
                        pass
        elif q["do"] in ST.PLACE_KIND:
            box = (plan.get("places") or {}).get(q.get("place"))
            if box and strokes and not PL.covered(box, strokes):
                try:
                    from paperdaemon.pipeline.page import images as IM
                    pic = any(im["box"][0] < box["x1"] and im["box"][2] > box["x0"]
                              and im["box"][1] < box["y1"] and im["box"][3] > box["y0"]
                              for im in IM.items(doc, page))
                except Exception:
                    pic = False
                if not pic:
                    out.append("nothing landed in the box for step %d (%s)" % (q["id"], ST.describe(q)))
    if keys is not None and plan.get("erase_sigs"):
        left = set(plan["erase_sigs"]) & keys
        if left:
            out.append("%d ink stroke(s) named for erasing are still there" % len(left))
    if JOB.hide_typed:
        out.append("typed text staged for erasing was not erased: %s"
                   % "; ".join(t[:40] for t in JOB.hide_typed))
    return out


# the tools this module serves, as the host offers them (the host's TOOLS keeps this order)
TOOLS = [
 ("undo_last", "Take back the last thing(s) you drew, keeping the rest.", {"parts": "number"}, t_undo_last),
]
