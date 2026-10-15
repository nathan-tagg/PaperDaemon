"""Erasing: the ids the decision names, the user's requests once carried out, and this system's stale work."""
import math
import re
from paperdaemon.pipeline import page as ER
from paperdaemon.pipeline.host import steps as ST
from paperdaemon.pipeline.host.job import JOB
from paperdaemon.pipeline.page import render as R
from paperdaemon.pipeline import host as H


def _erase_refs(erase):
    """A plan's erase list -> (mark numbers, words). Paragraph numbers and 'all ink' are NOT words:
    the host runs those itself (_run_erase), so they are left out of both lists here."""
    ids, words = [], []
    for e in (erase or []):
        if isinstance(e, (int, float)) and not isinstance(e, bool):
            ids.append(int(e))
            continue
        for kind, v in ST.erase_targets(str(e)):
            if kind == "mark":
                ids.append(int(v))
            elif kind == "words":
                words.append(v)
    return ids, words


def _resolve_lines(s):
    """'line:N' -> the mark range of the line of handwriting the listing printed as line:N
    ('mark:A..B'). A line this page's listing does not have stays 'line:N', and its step fails."""
    lines = JOB.ink_lines or {}

    def one(m):
        r = lines.get(int(m.group(1)))
        if not r:
            return m.group(0)
        return ("mark:%d" % r[0]) if r[0] == r[1] else ("mark:%d..%d" % (r[0], r[1]))
    return re.sub(r"\bline:(\d+)\b", one, str(s or ""))


def t_erase_typed_text(text):
    """Delete typed text -- but only the part you name.

    Wiping every typed item on the page is wrong the moment a page holds a
    typed QUESTION and a typed instruction:
    carrying out the instruction and deleting both takes the question with it,
    and the skill's rule is that a question always survives its answer.
    Quoting what should go makes the destructive case the deliberate one.
    """
    doc, page = JOB.doc, JOB.page
    # THE INSTRUCTION SURVIVES UNTIL THE WORK LANDS. Tidying up is something you
    # do AFTER carrying the request out, and a job that erases the request and
    # then fails leaves the user with neither the work nor the thing they asked
    # for. One run got as far as erasing before it ran out of turns with an
    # uncommitted draft; only a quoting mismatch saved the text.
    # No "commit first" gate: the deletion is STAGED and applied at commit(), after the
    # work is written, so the instruction survives until the work lands by construction -- and an
    # erase-only job (nothing to draw) can finish.
    want = (text or "").strip().lower()
    if not want:
        return dict({"error": "say which text to remove -- quote a few words of "
                              "it. There is no 'erase all typed text'."}, **H._did())
    try:
        from paperdaemon.pipeline.page import typed as _TY
        _tb, paras = _TY.paragraphs(doc, page)
        have = [p.get("text", "") for p in paras]
    except Exception:
        have = []
    # SAME MATCH AS THE ERASE ITSELF. A raw lowercase substring test here and ER.erase_text's own
    # test could disagree, which is how a phrase passed staging and then erased nothing. One
    # normalizer, used by both.
    _n_want = ER._normalize(want)[0]
    if not have:
        # nothing typed at all: staging this "erased" 0 paragraphs and called the step done, with
        # the request -- ink on a PDF page -- still there
        return dict({"error": "this page has no typed text"}, **H._did())
    if not any(_n_want in ER._normalize(h or "")[0] for h in have):
        return dict({"error": "no typed text on this page contains %r. The "
                              "typed paragraphs are: %s"
                              % (text[:40], [h[:60] for h in have][:6])}, **H._did())
    if want in (JOB.hide_typed or []):
        return dict({"error": "that text is already staged for deletion; it goes at commit()."},
                    **H._did())
    H._stage("erase typed text containing %r" % text[:40], typed=[want])
    hits = [h for h in have if _n_want in ER._normalize(h or "")[0]]
    H.log("  staged typed-text erase matching %r (%d paragraph(s)) on %s p%s"
        % (text[:40], len(hits), doc[:8], page))
    return dict({"ok": True, "paragraphs": len(hits),
                 "note": "staged: gone from your renders from now on, deleted when you commit()."},
                **H._did())


def _snap(why):
    """Always recoverable before a destructive edit.

    NAME COLLISION: a later `def _snap(doc, page, box)` (the grounding helper, now
    `_snap_to_marks`) shadowed this one, so every commit-time erase raised TypeError inside its
    own try/except and was logged, not raised. The model was told the text was staged, commit
    reported ok, and the page kept the text. That is why the handlers below now report the
    failure instead of only logging it.
    """
    from paperdaemon.pipeline import page as P
    P.record(JOB.doc, JOB.page, note="before rm_host %s" % why)


def _erase(kill, why):
    """STAGE an erasure -- nothing leaves the page until commit().

    Erasing is a draft like drawing: the strokes vanish from every render and mark list, undo_last() brings
    them back, skip() forgets them, and commit() takes them off the page for real. A wrong id costs an undo,
    never the user's ink.
    """
    from paperdaemon.pipeline import page as P
    doc, page = JOB.doc, JOB.page
    hide = JOB.hide
    sigs = []
    for L in R.strokes(doc, page):
        g = P.skey(L)
        if g in hide:
            continue
        try:
            if kill(L):
                sigs.append(g)
        except Exception as ex:
            # the stroke SURVIVES when this throws, and the model is told it erased it
            H._warn("erasing a stroke", ex)
    H._stage("%s: %d strokes" % (why, len(sigs)), sigs=sigs)
    live = len(R.strokes(doc, page)) - len(JOB.hide)
    H.log("  staged erase of %d strokes (%s) on %s p%s" % (len(sigs), why, doc[:8], page))
    return dict({"ok": True, "erased": len(sigs), "left_on_page": live,
                 "note": "staged: gone from your renders from now on, taken off the page when "
                         "you commit(). undo_last() brings them back. render() to check."},
                **H._did())


def _boxes_from(boxes, iw, ih):
    """Boxes in the picture's pixels (what the harness read from the reply) -> page coordinates."""
    out = []
    fw, fh = H._frame()
    for x0, y0, x1, y1 in boxes:
        px0 = x0 * (fw / iw) - fw / 2.0
        px1 = x1 * (fw / iw) - fw / 2.0
        py0 = y0 * (fh / ih)
        py1 = y1 * (fh / ih)
        out.append((min(px0, px1), min(py0, py1), max(px0, px1), max(py0, py1)))
    return out


def _snap_to_marks(doc, page, box, pad=40.0):
    """A roughly-right box -> the marks actually inside it, and their EXACT extent.

    The grounded box is 4-40 px out. That is fine for saying WHICH thing and not fine for putting
    ink beside it, so the model's answer is only ever used to select, never to measure.
    """
    from paperdaemon.pipeline.page import marks as MK
    x0, y0 = box[0] - pad, box[1] - pad
    x1, y1 = box[2] + pad, box[3] + pad
    hit = []
    for m in MK.marks(doc, page, 30.0, hide=H._hide()):
        bx = m["bbox"]
        cx, cy = (bx[0] + bx[2]) / 2.0, (bx[1] + bx[3]) / 2.0
        if x0 <= cx <= x1 and y0 <= cy <= y1:
            hit.append(m)
    if not hit:
        return None
    ex = [min(m["bbox"][0] for m in hit), min(m["bbox"][1] for m in hit),
          max(m["bbox"][2] for m in hit), max(m["bbox"][3] for m in hit)]
    return {"marks": [m["id"] for m in hit], "bbox": [round(v) for v in ex],
            "strokes": sum(m["count"] for m in hit),
            "owner": "mixed" if len({m["owner"] for m in hit}) > 1 else hit[0]["owner"]}


# --------------------------------------------------------------- the host walks the steps


def _ink_on(box, share=0.5):
    """Signatures of the ink THIS SYSTEM drew mostly inside `box` -- what it wrote on a picture.

    A picture that comes off takes that ink with it: the on-this-day facts written over an old
    calendar are part of the old calendar, and left behind they are content the next placement has
    to go below -- the new calendar lands lower than the one it replaces. The user's own ink is
    never returned."""
    x0, y0, x1, y1 = (float(v) for v in box)
    keys = set()
    for m in JOB.mark_index or []:
        if m.get("owner") != "mine":
            continue
        a0, b0, a1, b1 = m["bbox"]
        ix = max(0.0, min(a1, x1) - max(a0, x0))
        iy = max(0.0, min(b1, y1) - max(b0, y0))
        if ix * iy / max(1.0, (a1 - a0) * (b1 - b0)) > share:
            keys |= set(m.get("keys") or m.get("sigs") or [])
    return keys - set(JOB.hide or {})


def _run_erase(what, because=None):
    """One erase step, by the ids it names (from a ruling) or the ink it pointed at. -> (ok, note).

    para:N is the Nth typed paragraph as listed to the model (JOB.paras), erased by its full text; mark:N was
    resolved to stroke signatures by the plan and comes off at commit; picture:N is staged by its box. The ruling
    decided that it comes off; the host checked the ruling (rulings.problems) and carries it out.
    """
    plan = JOB.plan or {}
    notes, hit = [], 0
    for kind, v in ST.erase_targets(what):
        if kind == "para":
            paras = JOB.paras or []
            if not (0 < int(v) <= len(paras)):
                notes.append("there is no para:%s (this page has %d typed paragraph%s)"
                             % (v, len(paras), "" if len(paras) == 1 else "s"))
                continue
            r = H.t_erase_typed_text(paras[int(v) - 1])
            if r.get("ok") or "already staged" in str(r.get("error", "")):
                hit += 1
            else:
                notes.append(str(r.get("error", ""))[:120])
        elif kind == "line":
            # the plan turns every line the listing printed into its marks, so a line:N still here is not on this page
            notes.append("there is no line:%s on this page (it lists %d)" % (v, len(JOB.ink_lines or {})))
        elif kind == "mark":
            if any(m["id"] == int(v) for m in (JOB.mark_index or [])) and plan.get("erase_sigs"):
                hit += 1                  # resolved by the plan; applied at commit
            else:
                notes.append("no mark:%s on this page" % v)
        elif kind == "picture":
            pic = next((q for q in H._pictures(JOB.doc, JOB.page) if q["n"] == int(v)), None)
            if pic is None:
                notes.append("no picture:%s on this page" % v)
            else:
                # the ink this system wrote on its own picture goes with it (_ink_on)
                ink = H._ink_on(pic["box"])
                H._stage("erase picture:%s" % v, sigs=sorted(ink), images=[list(pic["box"])])
                JOB.erased_pictures[int(v)] = pic.get("asset")
                H.log("  picture:%s staged for erasing (%s)%s"
                      % (v, pic.get("what") or "a picture",
                         (", with %d stroke(s) of this system's ink on it" % len(ink)) if ink else ""))
                hit += 1
        elif kind == "at":
            # the ink it pointed at, resolved by the plan to the strokes there and taken off at commit
            if (JOB.at_ink or {}).get(int(v)):
                hit += 1
            else:
                notes.append("no ink where it pointed")
    return (hit > 0 and not notes), "; ".join(notes)


def _keep_unanswered():
    """Rule 10: a request comes off only once every step that answers it has landed. The erase a ruling made of a
    request answered by a step that failed is undone -- its typed text and pictures un-staged, its ink kept -- so
    the page still says what was asked. What the user asked to have removed, and stale work, are not affected."""
    steps = JOB.steps or []
    failed = set(a for q in steps if q["status"] == "failed" for a in q.get("answers") or [])
    if not failed:
        return
    plan = JOB.plan or {}
    for q in steps:
        if q["do"] != "erase" or q["status"] != "done" or q.get("because") != "request":
            continue
        ids = set("%s:%d" % (k, v) for k, v in ST.erase_targets(q["what"]) if k != "at")
        if not ids & failed:
            continue
        for op in q.get("ops") or []:
            H._unstage(op)
        if q.get("sigs"):
            plan["erase_sigs"] = [g for g in plan.get("erase_sigs") or [] if g not in set(q["sigs"])]
        q["status"], q["note"] = "failed", "kept: the step that answers it did not land"
        H.log("  %s stays on the page: the step that answers it failed" % " ".join(sorted(ids)))


def t_erase_all_strokes():
    """Rub out every stroke on the page, and every picture placed on it. Typed text is left alone."""
    res = H._erase(lambda line: True, "erase_all_strokes")
    try:
        from paperdaemon.pipeline.page import images as IM
        boxes = [list(im["box"]) for im in IM.items(JOB.doc, JOB.page)
                 if list(im["box"]) not in (JOB.hide_images or [])]
        if boxes:
            JOB.erase_log[-1]["images"].extend(boxes)
            JOB.hide_images.extend(boxes)
            res["pictures_removed"] = len(boxes)
    except Exception as ex:
        H.log("  picture erase failed: %s" % str(ex)[:80])
    return res
