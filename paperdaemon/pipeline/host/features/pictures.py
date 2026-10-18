"""Pictures from the image model: generated, edited, decomposed into strokes or placed as images, and coloring pages."""
import base64
import os
import re
import time
import urllib.error
import urllib.parse
import urllib.request
from PIL import Image
from paperdaemon.pipeline import decompose as M_
from paperdaemon.pipeline.host import steps as ST
from paperdaemon.pipeline.host.job import JOB
from paperdaemon.pipeline import host as H


def _slot(key, ctx=None, kv=None):
    """Put `key` on the card and wait for it. The studio owns the slot; this asks and then waits.

    Loading is asynchronous there -- /load returns at once and a thread does the work -- so the
    answer to "is it ready" is /status, not the response to /load.
    """
    body = dict(key=key)
    if ctx:
        body["ctx"] = ctx
    if kv:
        body["kv"] = kv
    H._studio("/load", body)
    while True:                       # ends when the engine has the model ready, or reports why it cannot
        st = H._studio("/status", timeout=60)
        if st.get("key") == key and st.get("phase") == "ready":
            return st
        if st.get("phase") == "error":
            raise RuntimeError(st.get("msg") or "the model would not load")
        time.sleep(2.0)


def _picture_model(fn):
    """Run fn() with the PICTURE model on the card, then put the talker back -- ONE hand-over for
    however many pictures fn makes. When the text model and the picture model cannot share the graphics card,
    the engine swaps them (the lineup's start scripts), which can take a minute each way.
    NESTED calls run inside the hand-over already under way (an Ink Adventure turn paints the
    newcomers' portraits and then the scene, through _paint.session, in one hand-over)."""
    if JOB.painter_on:
        return fn()
    try:
        before = H._studio("/status", timeout=60)
    except Exception as ex:
        raise RuntimeError("the picture studio is not answering on %s (%s), so there is no way to reach "
                           "the picture model" % (H.STUDIO, type(ex).__name__))
    talker = before.get("key")
    want = (before.get("tablet") or {}).get("image") or "image"
    JOB.picture_model = want
    try:
        H._slot(want)
        JOB.painter_on = True
        return fn()
    finally:
        JOB.take("painter_on")
        # ALWAYS hand the card back, even when the render failed -- otherwise the next turn has no
        # model to talk to and the job dies somewhere much less obvious than here.
        try:
            if talker:
                H._slot(talker, before.get("llm_ctx"), before.get("llm_kv"))
        except Exception as ex:
            H.log("could not reload %s: %s" % (talker, ex))


def _side_for(box):
    """The decomposer wants a square source at least the box's size; the painter wants a multiple
    of 64."""
    side = max(512, min(1024, int(max(box["w"], box["h"]))))
    return side - side % 64


def _dims_for(box):
    """(width, height) for the painter: the box's own shape, multiples of 64, about a megapixel at
    most. A coloring page is portrait; rendered square it filled the top half of the page."""
    ar = float(box["w"]) / max(1.0, float(box["h"]))
    if box.get("kind") == "coloring":
        # A COLORING PAGE IS THE BOX'S EXACT SHAPE -- on the whole screen, 3:4 -- or it sits in it with white bands:
        # the multiple-of-64 size nearest that shape, about a megapixel at most
        return min(((w, h) for w in range(512, 1217, 64) for h in range(512, 1217, 64) if w * h <= 1100000),
                   key=lambda d: (abs(d[0] / float(d[1]) - ar), -d[0] * d[1]))
    if 0.8 <= ar <= 1.25:
        s = H._side_for(box)
        return s, s
    w, h = (832, 832 / ar) if ar < 1 else (832 * ar, 832)
    w, h = int(round(w / 64.0)) * 64, int(round(h / 64.0)) * 64
    return max(512, min(1216, w)), max(512, min(1216, h))


def _user_numbers():
    """The step counts and seeds the user asked for: those a step backs with a quote of the user's words (checked
    by the decision: validity rule 7). The engine uses such a count as written, and keeps a count the model chose
    inside the image model's range."""
    out = set()
    for q in JOB.steps or []:
        if q.get("quote"):
            out.update(int(q[k]) for k in ("steps", "seed") if isinstance(q.get(k), int))
    return sorted(out)


def _picture_report(item):
    """What the engine says it left out of a picture, in the job's log: a workflow the active image
    harness does not have (the subject went as a plain prompt), a LoRA file the server does not list
    (the picture was made without it)."""
    if item.get("workflow_missing"):
        H.log("  the image model's harness has no %r workflow: the subject went as a plain prompt"
            % item["workflow_missing"])
    for f in item.get("loras_missing") or []:
        H.log("  LoRA %r is not in the image server's LoRA folder: the picture was made without it" % f)


def _generate_png(prompt, side, seed=None, height=None, steps=None, workflow=None):
    """One picture from the loaded picture model -> a local PNG path (the caller deletes it: nothing
    the studio makes is kept anywhere). The picture model must already be on the card. `steps`
    None = the workflow's or the model's own. `workflow` names one of the image harness's workflows
    (the engine wraps `prompt` in its wording and applies its settings); None sends `prompt` exactly
    as it is."""
    body = dict(prompt=prompt, width=side, height=height or side, seed=int(seed) if seed is not None else -1,
                user_numbers=H._user_numbers())
    if steps:
        body["steps"] = int(steps)
    if workflow:
        body["workflow"] = str(workflow)
    g = H._studio("/generate", body)
    if g.get("error"):
        raise RuntimeError("the picture would not render: %s" % str(g["error"])[:160])
    H._picture_report(g)
    # /generate answers with the ITEM ITSELF ({kind, name, secs, seed, ...}). Looking for it under
    # "item"/"newest" found nothing and reported "nothing to draw" three times in a row while sd.log
    # showed three finished renders -- each a full swap of the card.
    item = g if g.get("name") else (g.get("item") or g.get("newest") or {})
    name = item.get("name")
    if not name:
        raise RuntimeError("the picture model returned nothing to draw")
    png = os.path.join(H.QUEUE, "_host_image_%d.png" % int(time.time() * 1000))
    with open(png, "wb") as fh:
        fh.write(H._studio_open("/image/" + urllib.parse.quote(name), timeout=120).read())
    JOB.last_render = {"steps": item.get("steps"), "seed": item.get("seed")}   # what it was really made with
    return png


def _edit_png(src_png, prompt, mode="ref", strength=None, mask_png=None, seed=None, steps=None,
              width=None, height=None, workflow=None):
    """An existing picture changed by the loaded picture model (the studio's /edit) -> a local PNG path
    (the caller deletes it). mode "ref" hands the picture in as a reference and the prompt says what
    to change; "img2img" starts from it, `strength` 0..1 saying how far
    to wander; "inpaint" changes only the white of `mask_png`. `workflow`: one of the image harness's
    workflows that starts from a picture. The picture model must be on the card."""
    with open(src_png, "rb") as fh:
        body = dict(prompt=prompt, image=base64.b64encode(fh.read()).decode(), mode=mode,
                    seed=int(seed) if seed is not None else -1, user_numbers=H._user_numbers())
    if strength is not None:
        body["strength"] = float(strength)
    if mask_png:
        with open(mask_png, "rb") as fh:
            body["mask"] = base64.b64encode(fh.read()).decode()
    for k, v in (("steps", steps), ("width", width), ("height", height)):
        if v:
            body[k] = int(v)
    if workflow:
        body["workflow"] = str(workflow)
    g = H._studio("/edit", body)
    if g.get("error"):
        raise RuntimeError("the picture would not edit: %s" % str(g["error"])[:160])
    H._picture_report(g)
    name = g.get("name")
    if not name:
        raise RuntimeError("the picture model returned nothing")
    png = os.path.join(H.QUEUE, "_host_edit_%d.png" % int(time.time() * 1000))
    with open(png, "wb") as fh:
        fh.write(H._studio_open("/image/" + urllib.parse.quote(name), timeout=120).read())
    JOB.last_render = {"steps": g.get("steps"), "seed": g.get("seed")}
    return png


def _render_note(q):
    """'12 steps, seed 8080' -- how a picture step was rendered, for its notepad line (a redo the user
    asks for starts from it)."""
    r = q.get("render") or {}
    return ", ".join(s for s in (("%s steps" % r["steps"]) if r.get("steps") else "",
                                 ("seed %s" % r["seed"]) if r.get("seed") is not None else "") if s)


def _image_offer():
    """What the active image harness offers ({name, abilities, workflows, steps, steps_range}), as the
    engine wrote it for this host; {} without an image slot."""
    return H._harness().get("image") or {}


def _source_png(ref):
    """'picture:N' -> (a local copy of that picture's file, which the caller deletes, "") or (None, why)."""
    m = re.fullmatch(r"\s*picture\s*:\s*(\d{1,2})\s*", str(ref or ""))
    if not m:
        return None, "name the picture it starts from as source=picture:N"
    pic = next((p for p in H._pictures(JOB.doc, JOB.page) if p["n"] == int(m.group(1))), None)
    if pic is None:
        return None, "there is no picture:%s on this page" % m.group(1)
    path = pic.get("path")
    if not path or not os.path.isfile(path):
        return None, "picture:%s has no picture file to start from" % m.group(1)
    out = os.path.join(H.QUEUE, "_host_source_%d.png" % int(time.time() * 1000))
    Image.open(path).convert("RGB").save(out)
    return out, ""


def _ink_only(png, cut=150, bold=3):
    """A picture -> pure black lines on white, in place. Whatever gray, shading or color the painter
    added anyway goes (a coloring page has nothing filled in), and the lines are thickened a little
    so a child's crayon stays inside them."""
    from PIL import ImageFilter
    im = Image.open(png).convert("L")
    im = im.point(lambda v: 0 if v < cut else 255)
    if bold > 1:
        im = im.filter(ImageFilter.MinFilter(bold))
    im.convert("RGB").save(png)


def _trace_into(png, box, place, what, **kw):
    """Decompose a picture into strokes in the draft, fitted to `box`; the PNG is removed after."""
    H._mark()
    try:
        strokes, info, secs = M_.decompose_into(png, int(box["w"]), int(box["h"]),
                                                origin=(box["x0"], box["y0"]), **kw)
        # NOT TOO MANY STROKES ON A PAGE (validate): a picture that would take the page past its limit is drawn
        # again with a lower region budget, fewer and larger regions, until it fits
        budget = int(kw.pop("budget", M_.BUDGET))
        room = H._page_room(JOB.doc, JOB.page)
        while strokes and len(strokes) > room > 0 and budget > 250:
            budget = max(250, int(budget * room / len(strokes) * 0.9))
            H.log("  validate: %d strokes would pass the page's limit; redrawn with a region budget of %d"
                % (len(strokes), budget))
            strokes, info, secs = M_.decompose_into(png, int(box["w"]), int(box["h"]),
                                                    origin=(box["x0"], box["y0"]), budget=budget, **kw)
    finally:
        try:
            os.remove(png)
        except OSError:
            pass
    for st in strokes:
        JOB.draw.strokes.append(st)
    JOB.ops.append("%s in %r, %d strokes" % (what, place, len(strokes)))
    return len(strokes)


# A COLORING PAGE IS A PICTURE, NOT STROKES. Coloring book pages are direct inserted images, not
# decompositions: the rule is, if the user is going to color all over it and erase parts, it is a
# direct image insert (otherwise it is a decomposition). Traced into strokes, the lines would be
# ink like the user's: every stroke of the eraser would take a piece of the drawing with it. As the
# app's own image block, the user's coloring and erasing touch only their own ink.
def _picture_asset(png, box):
    """A picture fitted inside `box` (aspect kept, centered) -> (asset path, its box on the page)."""
    import uuid
    from PIL import Image as _Im
    with _Im.open(png) as im0:
        im = im0.convert("RGB")
    pw, ph = im.size
    s = min(float(box["w"]) / pw, float(box["h"]) / ph)
    wu, hu = pw * s, ph * s
    x0 = float(box["x0"]) + (float(box["w"]) - wu) / 2.0
    y0 = float(box["y0"]) + (float(box["h"]) - hu) / 2.0
    aw, ah = int(round(wu * 1.25)), int(round(hu * 1.25))       # ~1.1 device px per asset px
    if pw > aw:
        im = im.resize((aw, ah), _Im.LANCZOS)
    apath = os.path.join(H.QUEUE, "_host_img_%s.png" % uuid.uuid4().hex[:12])
    im.save(apath, "PNG", optimize=True)
    return apath, (x0, y0, x0 + wu, y0 + hu)


def _coloring_page(q, png, box):
    """One coloring page on a NEW page of the notebook -> (0, page number), inserted there as a
    picture. The first coloring page of a job goes on the job's own page; every one after it gets
    a sheet of its own, like the pages of a coloring book."""
    from paperdaemon.pipeline.page import images as IM
    H._ink_only(png)
    try:
        apath, pbox = H._picture_asset(png, box)
    finally:
        try:
            os.remove(png)
        except OSError:
            pass
    pno, pid, key = H._new_page()
    r_ = IM.insert(JOB.doc, pno, apath, pbox)
    try:
        IM.record_placement(JOB.doc, pno, r_["asset"].split("/")[-1], pbox, type="coloring",
                            title=str(q.get("what") or "")[:40])
    except Exception as ex:
        H._warn("recording the coloring page's placement", ex)
    H._page_done(key, "a coloring page made by the job on page %s" % JOB.page)
    JOB.new_pages.append(pno)
    # that page's own notepad entry, under its own ID: what was made on it (notepad_read)
    JOB.new_page_notes[pid] = "coloring page %r as a picture (%s)" % (str(q.get("what") or "")[:30],
                                                                                         H._render_note(q))
    H.log("  coloring page on a NEW page p%d, as a picture" % pno)
    return 0, pno


def _run_images(batch):
    """All pending image steps in ONE hand-over of the card. Each step is marked done or failed on
    its own; one picture failing does not cost the others."""
    steps = JOB.steps or []
    boxes = (JOB.plan or {}).get("places") or {}
    for q in batch:
        q["status"] = "doing"
    todo = [(q, H._page_box() if q.get("new_page") else boxes.get(q.get("place"))) for q in batch]
    for q, box in todo:
        if box is None:
            ST.finish(steps, q, False, "no box for this picture")
    todo = [(q, b) for q, b in todo if b is not None]
    if not todo:
        return

    offer = H._image_offer().get("workflows") or {}

    def make():
        out = []
        for q, box in todo:
            # THE WORKFLOW IS THE IMAGE HARNESS'S. A coloring step is the coloring book workflow unless
            # it names another; an image step uses one only when it names one, and otherwise its words
            # go to the image model exactly as the model wrote them. The steps the model gave (or the
            # user's number) travel as they are: the engine keeps the model's inside the image model's
            # range and applies the workflow's own when none is given.
            wf = q.get("workflow") or (H.COLORING_BOOK if q["do"] == "coloring" else None)
            src = None
            try:
                w_, h_ = H._dims_for(box)
                if wf and (offer.get(wf) or {}).get("reference"):
                    # a workflow that starts from a picture: the one the step names as its source
                    src, why = H._source_png(q.get("source"))
                    if src is None:
                        out.append((q, box, None, "the %s workflow starts from a picture: %s" % (wf, why)))
                        continue
                    png_ = H._edit_png(src, q["what"], mode="ref", seed=q.get("seed"), steps=q.get("steps"),
                                     width=w_, height=h_, workflow=wf)
                else:
                    png_ = H._generate_png(q["what"], w_, height=h_, seed=q.get("seed"),
                                         steps=max(1, min(150, int(q["steps"]))) if q.get("steps") else None,
                                         workflow=wf)
                q["render"] = dict(JOB.last_render or {})
                out.append((q, box, png_, None))
            except Exception as ex:
                out.append((q, box, None, "%s: %s" % (type(ex).__name__, str(ex)[:120])))
            finally:
                if src:
                    try:
                        os.remove(src)
                    except OSError:
                        pass
        return out
    try:
        made = H._picture_model(make)
    except Exception as ex:
        for q, _b in todo:
            ST.finish(steps, q, False, "could not reach the picture model: %s" % str(ex)[:120])
        return
    for q, box, png, err in made:
        if err or not png:
            ST.finish(steps, q, False, err or "no picture")
            continue
        try:
            q["draw_from"] = len(JOB.draw.strokes)
            if q.get("new_page"):
                n, pno = H._coloring_page(q, png, box)
                q["note"] = "on a new page, p%d" % pno
            elif q["do"] == "coloring":
                # black lines only, and ON AS A PICTURE (see _picture_asset): the user colors and
                # erases on it, and the eraser must not take the drawing with it
                H._ink_only(png)
                try:
                    apath, pbox = H._picture_asset(png, box)
                finally:
                    try:
                        os.remove(png)
                    except OSError:
                        pass
                JOB.images.append({"place": q.get("place"), "png": apath, "box": pbox,
                                                      "type": "coloring", "title": str(q["what"])[:40],
                                                      "spec": None, "replaces": []})
                H._mark()
                JOB.ops.append("coloring page %r as a picture in %r (%s)" % (str(q["what"])[:30], q.get("place"),
                                                                              H._render_note(q)))
                n = None
            else:
                n = H._trace_into(png, box, q.get("place"), "image (%s)" % H._render_note(q))
            q["draw_to"] = len(JOB.draw.strokes)
            ST.finish(steps, q, True, "as a picture" if n is None else "%d strokes" % n)
        except Exception as ex:
            ST.finish(steps, q, False, "would not trace: %s" % str(ex)[:100])


def t_image(prompt, place=None, seed=None):
    """Generate a picture on this machine and trace it into a planned box.

    A PICTURE CAN BE SLOW. On a lineup whose two models cannot share the graphics card, making a picture means
    swapping them and back; that is why the tool's description tells the model to ask once rather than
    iterate. The conversation survives it: the host keeps the message list and re-sends it, so a server
    restart costs the cache, not the job.

    Which picture model is used is the lineup's, never the model's choice; the model describes what it wants
    to see.
    """
    plan = JOB.plan or {}
    boxes = plan.get("places") or {}
    if not boxes:
        return {"error": "call plan() first and give the picture a place of its own, "
                         "e.g. {\"id\": \"picture\", \"kind\": \"image\", \"size\": \"large\"}."}
    if place is None:
        place = H._cur_place()
    if place not in boxes:
        return {"error": "there is no place called %r in your plan. You planned: %s."
                         % (place, ", ".join(sorted(boxes)))}
    box = boxes[place]
    if box["kind"] != "image":
        return {"error": "the place %r is a %s, not an image. Plan it as kind='image'."
                         % (place, box["kind"])}
    prompt = (prompt or "").strip()
    if len(prompt) < 12:
        return {"error": "describe the picture properly -- what is in it, how it is lit, what "
                         "style. %r is not enough to render." % prompt[:40]}

    t0 = time.time()
    try:
        png = H._picture_model(lambda: H._generate_png(prompt, H._side_for(box), seed))
    except Exception as ex:
        return {"error": "could not make the picture: %s: %s" % (type(ex).__name__, str(ex)[:140])}
    try:
        n = H._trace_into(png, box, place, "image")
    except Exception as ex:
        return {"error": "the picture would not trace: %s: %s" % (type(ex).__name__, str(ex)[:120])}
    return dict({"ok": True, "strokes": n, "box": box,
                 "seconds": round(time.time() - t0, 1),
                 "note": "The picture is in the draft, not on the page. render() and LOOK at it. "
                         "If it is wrong, say so in done() rather than generating another -- each "
                         "one costs a minute of handing the card back and forth."},
                **H._did())


# the tools this module serves, as the host offers them (the host's TOOLS keeps this order)
TOOLS = [
 ("image", "MAKE A PICTURE from your description, on this machine, into your box. Say what is in it, "
  "how it is lit and what style it is in; a bare noun gives a bare picture. SLOW (about a minute: the "
  "card is handed to the picture model and back), so describe it well and ask once.",
  {"prompt": "string", "place": {"type": "string", "optional": True},
   "seed": {"type": "integer", "optional": True}}, t_image),
]
