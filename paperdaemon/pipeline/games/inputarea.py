r"""THE PLAYER'S SPACE on a game page that is a picture (messages, the adventure): where they answer, by hand or by
keyboard.

THE PICTURE ENDS WHERE THE SPACE BEGINS. The tablet puts typed text below a picture on the page, so a picture
covering the whole page, its writing box painted inside it, left nowhere to type: the text went under the picture,
past the foot of the page. Typing is the stronger way to answer, so the page's picture stops at the top of the space,
and the space under it is the page itself, to type or write in. The picture's foot carries the instruction, from the
left edge of the typed-text column, so it sits right over the first typed line.

A TURN READS BOTH: the typed text on the page (exactly, no model needed: the game itself types nothing), then the
handwriting in the space (the vision model, on the player's ink alone), and takes both off the page once they are
read, since they are the player's message now.
"""
import os
import re
import time

from paperdaemon.pipeline.page import tablets as TB

COLUMN_X = -576.0            # the typed-text column's left edge on a page with no text yet: the tablet's wide column
LABEL_H = 46                 # design pixels: the instruction's row at the picture's foot
LABEL_INK = (70, 70, 70)     # dark enough to read at a glance, lighter than the thread's words


def column_x(doc, page_no):
    """The left edge of the page's typed-text column, in page units (x from the center)."""
    try:
        from paperdaemon.pipeline.page import typed as TY
        tb, _paras = TY.paragraphs(doc, page_no)
        if tb is not None:
            return float(tb.pos_x)
    except Exception:
        pass
    return COLUMN_X


def foot(im, top, label, col_px, font, color, rule):
    """The instruction at the picture's foot, above `top` (design pixels): `label` from `col_px` (the typed-text
    column's left edge, design pixels), and a rule along the picture's last row, the top of the player's space."""
    from PIL import ImageDraw
    d = ImageDraw.Draw(im)
    d.line((0, top - 2, im.width, top - 2), fill=rule, width=3)
    d.text((col_px, top - LABEL_H + 4), label, font=font, fill=color)


def column_px(doc, page_no, page_w):
    """The typed-text column's left edge in the design's pixels, on this page's own tablet."""
    s = TB.picture_page(TB.frame_of(doc, page_no))[1]
    return max(0, int(round(page_w / 2.0 + column_x(doc, page_no) / s)))


def place(doc, page_no, page_id, png, top):
    """The page's picture, cut at `top` (design pixels: where the player's space begins), onto the page -> its
    placement {hash, name, box}."""
    from PIL import Image
    from paperdaemon.pipeline.page import images as IM
    with Image.open(png) as im:
        im.crop((0, 0, im.width, int(top))).save(png)
    x0, y0, x1, _y1 = TB.picture_page(TB.frame_of(doc, page_no))[0]
    s = TB.picture_page(TB.frame_of(doc, page_no))[1]
    box = (x0, y0, x1, top * s)
    r = IM.insert(doc, page_no, png, box, page_id=page_id)
    return {"doc": r["doc"], "hash": r["hash"], "name": r["name"], "box": box}


def typed(doc, page_no):
    """What the player typed on the page, its paragraphs as one line."""
    try:
        from paperdaemon.pipeline.page import typed as TY
        _tb, paras = TY.paragraphs(doc, page_no)
    except Exception:
        return ""
    return " ".join(" ".join(str(p.get("text") or "").split()) for p in paras if str(p.get("text") or "").strip())


def handwriting(doc, page_no, top, ask_vision, prompt, key, workdir):
    """The player's handwriting from `top` (page units) down, read: their ink alone (no picture, no typed text),
    cropped close, for the vision model. `key`: the word the answer starts with ("MESSAGE"). -> text, or ''."""
    from PIL import Image, ImageOps
    from paperdaemon.pipeline.page import images as IM
    from paperdaemon.pipeline.page import render as R
    png = os.path.join(workdir, "_player_read_%d.png" % int(time.time() * 1000))
    try:
        try:
            boxes = [im["box"] for im in IM.items(doc, page_no) if im.get("box")]
            _ox, oy = R.render(doc, page_no, png, typed=False, hide_images=boxes)[4]   # one pixel a page unit
        except ValueError:
            return ""                                          # no ink on the page at all
        with Image.open(png) as im:
            w, h = im.size
            page = im.convert("L").crop((0, max(0, int(top - oy)), w, h))
        # the writing alone, with a margin: a vision model shrinks a big picture, and the page is mostly paper
        ink = ImageOps.invert(page).point(lambda v: 255 if v > 40 else 0).getbbox()
        if not ink:
            return ""
        pad = 40
        page.crop((max(0, ink[0] - pad), max(0, ink[1] - pad), min(page.width, ink[2] + pad),
                   min(page.height, ink[3] + pad))).save(png)
        reply = ask_vision(prompt, png)
    finally:
        try:
            os.remove(png)
        except OSError:
            pass
    m = re.search(r"(?im)^\s*%s:\s*(.+)$" % re.escape(key), str(reply or ""))
    return m.group(1).strip().strip('"') if m else ""


def read(doc, page_no, top, ask_vision, prompt, key, workdir):
    """The player's answer: what they typed, then what they wrote from `top` (page units) down -> text, or ''."""
    said = [typed(doc, page_no), handwriting(doc, page_no, top, ask_vision, prompt, key, workdir)]
    return " ".join(t for t in said if t).strip()


def clear(doc, page_no, top):
    """The player's answer off the page once it is read: their typed text, and their ink from `top` down."""
    from paperdaemon.pipeline import page as PG
    if typed(doc, page_no):
        try:
            PG.erase_text(doc, page_no)
        except Exception:
            pass

    def inside(L):
        pts = getattr(L, "points", None) or []
        return bool(pts) and min(p.y for p in pts) >= top
    try:
        PG.erase(doc, page_no, inside)
    except Exception:
        pass
