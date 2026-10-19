"""The reMarkable tablets a page can come from, known by the frame the page carries.

A NOTEBOOK PAGE CARRIES ITS FRAME. Every .rm page stores it in its SceneInfo (paper_size), and a new page on a
tablet is normally that tablet's screen size: the page is laid out in it, x from -width/2 to +width/2 with 0 at the
center, y from 0 at the top down (render.page_frame reads it). But a frame does NOT say which tablet made the page:
the user's Paper Pro wrote a page of 1404 x 1872, the reMarkable 2's. So the frame decides the layout, never a claim
about the tablet. The other models open the page scaled to their own
screen, so content laid out in a page's own frame shows right on every tablet the library reaches. A PDF page is not
one of these: its frame is the PDF page's own size (render.PDF_SCALE), whatever SceneInfo says.

Sources: the published specs (reMarkable's comparison page, the Paper Pro Move user guide, reviews of the Paper Pure)
and a writer built from real device files (RM-Sticker-Press, rm_writer.js DEVICES). The Paper Pro's own frame and
its toolbar's zone (page.TOP_MARGIN) were measured on the user's tablet; the others' toolbar zones are that one,
scaled with the width (page.safe_area) -- not measured.
"""

# (name, (width, height) in page units -- the screen's pixels, shows color, pixels per inch)
TABLETS = (
    ("Paper Pro", (1620, 2160), True, 229),
    ("Paper Pro Move", (954, 1696), True, 264),
    ("reMarkable 2 or Paper Pure", (1404, 1872), False, 226),   # one frame: the Paper Pure keeps the reMarkable 2's screen
)
DEFAULT = TABLETS[0]                                          # a page that says nothing: the Paper Pro, as before


def of_frame(frame):
    """The tablet whose page has this frame -> {"name", "frame", "color"}, or None for a frame no tablet writes (a
    PDF page at its own size)."""
    try:
        w, h = (int(round(float(v))) for v in frame)
    except (TypeError, ValueError):
        return None
    for name, (tw, th), color, ppi in TABLETS:
        if (w, h) == (tw, th):
            return {"name": name, "frame": (tw, th), "color": color, "ppi": ppi}
    return None


# A PAGE DRAWN AS ONE PICTURE (a chat page, an adventure's pages, the Decompose inbox's) is designed at the Paper
# Pro's size, 3:4. On another tablet's page it is fitted to the page's width from the top: exactly the page on a
# reMarkable 2 or Paper Pure (3:4 too), the top of a Paper Pro Move's taller page. Its own coordinates are scaled the
# same way (`s`).
DESIGN = DEFAULT[1]


def picture_page(frame):
    """A designed page on a page of this frame -> (its box in page units, scale s from design units to page units)."""
    w = float(frame[0]) if frame else float(DESIGN[0])
    s = w / DESIGN[0]
    return (-w / 2.0, 0.0, w / 2.0, DESIGN[1] * s), s


def frame_of(doc, page_no):
    """The page's frame, or the Paper Pro's when it cannot be read."""
    try:
        from paperdaemon.pipeline.page import render as R
        return tuple(float(v) for v in R.page_frame(doc, page_no))
    except Exception:
        return tuple(float(v) for v in DESIGN)


def library_page(mirror, sample=60):
    """A notebook page of the user's own library in the frame most of its notebook pages carry -- the tablet they
    write on -- for a notebook PaperDaemon makes from nothing (the Decompose inbox): its blank page is derived from
    that page, real bytes of their own tablet, and not from a Paper Pro page bundled with PaperDaemon. -> the .rm
    path, or None (an empty library: the bundled page). Reads the SceneInfo of the smallest pages only."""
    import collections, glob, io, json, os
    try:
        from rmscene import read_blocks
        from rmscene import scene_stream as ss
    except Exception:
        return None
    notebooks = set()
    for f in glob.glob(os.path.join(mirror, "*.content")):
        try:
            with open(f, encoding="utf-8") as fh:
                if (json.load(fh).get("fileType") or "notebook") == "notebook":
                    notebooks.add(os.path.basename(f)[:-len(".content")])
        except (OSError, ValueError):
            pass
    pages = [p for p in glob.glob(os.path.join(mirror, "*", "*.rm"))
             if os.path.basename(os.path.dirname(p)) in notebooks]
    by = collections.defaultdict(list)
    for p in sorted(pages, key=os.path.getsize)[:sample]:
        try:
            with open(p, "rb") as fh:
                for b in read_blocks(io.BytesIO(fh.read())):
                    if isinstance(b, ss.SceneInfo) and getattr(b, "paper_size", None):
                        if of_frame(b.paper_size):
                            by[tuple(b.paper_size)].append(p)
                        break
        except Exception:
            continue
    if not by:
        return None
    return max(by.values(), key=len)[0]


def coordinates(frame):
    """The page's coordinates, in words, for the model: this page's own size and where its edges are. Nothing about
    the tablet: A FRAME DOES NOT SAY WHICH TABLET MADE THE PAGE -- the user's Paper Pro wrote a 1404 x 1872 page (a
    reMarkable 2's frame) -- so neither its model nor whether it shows color is claimed from it."""
    w, h = (float(v) for v in frame)
    return ("THIS PAGE is %d x %d page units: x from %d to %d with 0 at the center, y from 0 at the top to %d at the "
            "bottom of the first screen (it scrolls below that)." % (w, h, -w / 2, w / 2, h))
