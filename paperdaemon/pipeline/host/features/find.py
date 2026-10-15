"""Looking: finding a thing on the page and the closer looks a drawing turn takes."""
import json
import os
import re
from PIL import Image
from paperdaemon.notepad import Notepad
from paperdaemon.pipeline.host.job import JOB
from paperdaemon.pipeline.page import render as R
from paperdaemon.pipeline.page import typed as TY
from paperdaemon.pipeline import host as H

# which calls may answer each kind of step's turn: the job protocols (host/jobs.py)
FIX_TOOLS = ("edit_figure", "undo_last", "draw_figure", "element")


def t_find(what):
    """Ground a description to a real region of the page (asked and read by the harness)."""
    doc, page = JOB.doc, JOB.page
    try:
        out = os.path.join(H.QUEUE, "_host_find.png")
        R.render(doc, page, out, typed=True, hide=H._hide(),
                 hide_typed=JOB.hide_typed, hide_images=JOB.hide_images)
        from PIL import Image as _I
        with _I.open(out) as _im:
            iw, ih = _im.size
        raw = open(out, "rb").read()
        reply, _finish = H.plain(H._H().locate_one(H._host(), what, raw))
    except Exception as ex:
        H._warn("grounding %r" % str(what)[:40], ex)
        return dict({"error": "could not look: %s" % type(ex).__name__}, **H._did())
    found = H._H().read_located_one(reply, iw, ih)
    if found is None:
        return dict({"found": False, "note": "not on the page"}, **H._did())
    boxes = H._boxes_from(found, iw, ih)
    if not boxes:
        return dict({"found": False,
                     "note": "no box came back: %s" % reply[:80]}, **H._did())
    snapped = H._snap_to_marks(doc, page, boxes[0])
    if not snapped:
        return dict({"found": False, "rough_box": [round(v) for v in boxes[0]],
                     "note": "nothing is drawn there"}, **H._did())
    JOB.found[str(what)[:60]] = snapped
    return dict({"found": True, "what": str(what)[:60], "box": snapped["bbox"],
                 "marks": snapped["marks"], "strokes": snapped["strokes"],
                 "owner": snapped["owner"],
                 "note": ("box is the EXACT extent of the strokes there, not an estimate. "
                          "Erase it with erase_marks(%s), or put something beside it with "
                          "near='mark:%d'." % (snapped["marks"], snapped["marks"][0]))},
                **H._did())


def _serve_look(fn, args, cid, msgs, doc, page):
    """show_marks / look_closer / render: a picture back to the model, no change to anything."""
    if fn == "show_marks":
        from paperdaemon.pipeline.page import marks as MK
        gap = {"fine": 0.0, "coarse": 30.0}.get(str(args.get("detail", "")).lower(), 8.0)
        try:
            png, ms = MK.overlay(doc, page, os.path.join(H.QUEUE, "_host_marks.png"),
                                 gap=gap, hide=H._hide())
        except Exception as ex:
            msgs.append({"role": "tool", "tool_call_id": cid,
                         "content": json.dumps({"error": str(ex)[:120]})})
            return
        JOB.mark_index = ms
        brief = [{k: m[k] for k in ("id", "owner", "count", "bbox")} for m in ms]
        msgs.append({"role": "tool", "tool_call_id": cid,
                     "content": json.dumps({"marks": brief})[:1400]})
        msgs.append(H.image_message(png, "Every separate mark is in its own color with its number on "
                                       "it. 'yours' means the user drew it; 'mine' means this system did."))
        return
    if fn == "look_closer":
        index = JOB.mark_index or []
        try:
            want = int(args.get("mark"))
        except Exception:
            want = None
        hit = [m for m in index if m["id"] == want]
        if not hit:
            msgs.append({"role": "tool", "tool_call_id": cid, "content": json.dumps(
                {"error": "give a mark number from the listing (1..%d)" % len(index)})})
            return
        bx = hit[0]["bbox"]
        try:
            out = os.path.join(H.QUEUE, "_host_closer.png")
            R.render(doc, page, out, typed=True, hide=H._hide(),
                     hide_typed=JOB.hide_typed, hide_images=JOB.hide_images)
            im = Image.open(out).convert("RGB")
            pad = max(60.0, 0.25 * max(bx[2] - bx[0], bx[3] - bx[1]))
            fw, fh = H._frame()
            kx, ky = im.width / fw, im.height / fh           # pixels per page unit
            crop = im.crop((max(0, int((bx[0] + fw / 2.0 - pad) * kx)), max(0, int((bx[1] - pad) * ky)),
                            min(im.width, int((bx[2] + fw / 2.0 + pad) * kx)),
                            min(im.height, int((bx[3] + pad) * ky))))
            k = min(900.0 / max(1, crop.width), 900.0 / max(1, crop.height))
            crop = crop.resize((max(1, int(crop.width * k)), max(1, int(crop.height * k))), Image.LANCZOS)
            crop.save(out)
        except Exception as ex:
            H._warn("cropping mark %s" % want, ex)
            msgs.append({"role": "tool", "tool_call_id": cid,
                         "content": json.dumps({"error": str(ex)[:110]})})
            return
        msgs.append({"role": "tool", "tool_call_id": cid, "content": json.dumps(
            {"mark": want, "owner": hit[0]["owner"], "strokes": hit[0]["count"],
             "box": [round(v) for v in bx]})})
        msgs.append(H.image_message(out, "Mark %d, close up and on its own." % want))
        return
    if fn == "page_history":
        _serve_history(args, cid, msgs, doc, page)
        return
    if fn == "changes":
        msgs.append({"role": "tool", "tool_call_id": cid, "content": json.dumps(_changes(doc, page))[:1800]})
        return
    if fn == "notepad_read":
        msgs.append({"role": "tool", "tool_call_id": cid, "content": json.dumps(_notepad_read(args, doc))[:6500]})
        return
    # render
    JOB.unseen = False
    JOB.looks = JOB.looks + 1
    msgs.append({"role": "tool", "tool_call_id": cid, "content": '{"ok":true}'})
    msgs.append(H.page_image(doc, page, "The page as it now stands, with your draft drawn on it."))


def _snapshot(doc, page, back=1):
    """The page as the `back`-th earlier job found it -> (its snapshot's json path, its kept .rm or None), or None."""
    from paperdaemon.pipeline import page as _P
    ents = _P.entries(doc, page)
    if not (1 <= back <= len(ents)):
        return None
    base = ents[back - 1]["path"]
    base = base[:-5] if base.endswith(".json") else base
    return base + ".json", (base + ".rm") if os.path.exists(base + ".rm") else None


def _serve_history(args, cid, msgs, doc, page):
    """page_history(back): the page as an earlier job found it, as a picture."""
    try:
        back = max(1, int(args.get("back") or 1))
    except (TypeError, ValueError):
        back = 1
    snap = _snapshot(doc, page, back)
    if snap is None or snap[1] is None:
        msgs.append({"role": "tool", "tool_call_id": cid, "content": json.dumps(
            {"error": "no earlier page %d job%s back is kept" % (back, "" if back == 1 else "s")})})
        return
    out = os.path.join(H.QUEUE, "_host_history.png")
    try:
        with R.reading(doc, JOB.page_id, snap[1]):
            R.render(doc, page, out, typed=True, blank_ok=True)
    except Exception as ex:
        msgs.append({"role": "tool", "tool_call_id": cid, "content": json.dumps({"error": str(ex)[:120]})})
        return
    msgs.append({"role": "tool", "tool_call_id": cid, "content": json.dumps({"ok": True, "back": back})})
    msgs.append(H.image_message(out, "The page as the job %d before this one found it." % back))


def _changes(doc, page):
    """changes(): what was added and what was erased since this system last worked on the page."""
    snap = _snapshot(doc, page, 1)
    if snap is None:
        return {"changes": "this system has not worked on this page before: everything on it is new"}
    from paperdaemon.pipeline import page as _P
    old_paras = []
    if snap[1]:
        for b in R.blocks_of(snap[1]):
            if isinstance(b, TY.ss.RootTextBlock):
                old_paras += [str(p.get("text", "")).strip() for p in TY._paragraphs_of(b.value)]
    norm = lambda t: " ".join(str(t or "").split()).lower()
    now = set(norm(t) for t in JOB.paras or [])
    gone = [t for t in old_paras if t and norm(t) not in now]
    old_sigs = set(x.get("sig") for x in (_P.load(snap[0]).get("strokes") or []))
    cur = set(JOB.keys_before or ())
    listing = JOB.listing or {}
    return {"added": [{"id": i, "text": (listing.get(i) or {}).get("text", "")[:200]} for i in JOB.new_refs or []],
            "typed_text_erased": [t[:200] for t in gone],
            "strokes_added": len(cur - old_sigs), "strokes_erased": len(old_sigs - cur)}


def _notepad_read(args, doc):
    """notepad_read(scope): this page's entries, or the whole notebook's, beyond the window the listing shows."""
    scope = str(args.get("scope") or "page").lower()
    try:
        numbers = dict((p["id"], i + 1) for i, p in enumerate(R.live_pages(doc)))
    except Exception:
        numbers = {}
    text = Notepad(doc).read(limit=6000, page_id=JOB.page_id, numbers=numbers)
    if scope != "notebook":
        text = "".join(e for e in re.split(r"(?m)^(?=## )", text) if "THIS page" in e.split("\n", 1)[0])
    return {"scope": "notebook" if scope == "notebook" else "page", "notepad": text or "(nothing)"}


def _look_round(msgs, doc, page):
    """Show the drawing back once; one fix is allowed. No call means it is fine."""
    for _ in range(H.DRAW_LOOKS):
        msgs.append(H.page_image(doc, page, "Here is the page with your drawing on it. Look at it as a "
                                          "stranger would. If ONE thing is clearly wrong, fix it: "
                                          "edit_figure(changes) for a part, undo_last(n) to take the "
                                          "last thing back, or draw_figure again. If it reads as the "
                                          "thing, reply with the single word ok and no call."))
        fn, args, res = H._turn(msgs, FIX_TOOLS, tries=1, choice="auto", accept_prose=True)
        if fn is None:
            break


# the tools this module serves, as the host offers them (the host's TOOLS keeps this order)
TOOLS = [
 ("find", "FIND one thing on the page and get its exact position back. Quote its words if it has "
          "words, or name the object (the bicycle drawing). Never by category or position. Returns "
          "the real extent of the strokes there, plus their mark numbers.", {"what": "string"}, t_find),
 ("look_closer", "Look at ONE mark close up, filling the whole image. Give a number from the mark "
                 "listing.", {"mark": "number"}, None),
 ("show_marks", "Look at the page with every separate mark outlined in its OWN COLOR and numbered. "
  "detail: 'coarse' (words and figures) or 'fine' (letters and single strokes).",
  {"detail": "string"}, None),
 ("render", "Look at the page with your draft drawn on it.", {}, None),
 ("page_history", "Look at the page as an earlier job found it: back = 1 for the last job, 2 for the one before.",
  {"back": "number"}, None),
 ("changes", "What was added to the page and what was erased since this system last worked on it.", {}, None),
 ("notepad_read", "Read this notebook's notepad beyond what the listing shows: scope = 'page' (this page's "
  "entries) or 'notebook' (all of them).", {"scope": "string"}, None),
]
