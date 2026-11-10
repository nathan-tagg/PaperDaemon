"""THE CONCORD'S PAGES, in the adventure's design (one column, one header, one type scale, nothing that looks like a
button, no counts): the map, the orders page, the letters and the seasons. Each is drawn at the page's own size and
put on its page as a picture, as the adventure's sheet is. The families are told apart by their marks -- a letter on
each counter and by each harbor -- never by color alone."""
import math

from paperdaemon.pipeline.games import adventure as AD
from . import map as M
from . import rules as R

PAGE_W, PAGE_H = AD.PAGE_W, AD.PAGE_H
X0, X1, CW = AD.X0, AD.X1, AD.CW
INK, GRAY, RULE = AD.INK, AD.GRAY, AD.RULE
WATER = (232, 233, 236)
SHORE = (90, 90, 96)
SCALE = CW / M.MAP_W                                 # the map's own space onto the column
_TOP = [AD.BODY_Y + 62]                              # where the map starts: under the header's season line (map_png sets it)
ORDERS_TOP = 1180                                    # where the user writes their orders (and their letters)
SEASONS = ("Spring", "Autumn")


def season_words(state):
    n = int(state.get("season_no", 0))
    return "%s of year %d" % (SEASONS[n % 2], n // 2 + 1)


def family_name(state, fid):
    f = (state.get("families") or {}).get(fid) or {}
    return f.get("name") or ("The %ss" % fid.capitalize())


def mark(state, fid):
    f = (state.get("families") or {}).get(fid) or {}
    return (f.get("mark") or fid[:1]).upper()


def _to_page(x, y):
    return (X0 + x * SCALE, _TOP[0] + y * SCALE)


def _counter(d, x, y, kind, letter, mine, font):
    """A unit: a fleet as a hull with a sail, a militia as a tower; the family's letter beside it; the user's own
    drawn solid."""
    fill = INK if mine else None
    if kind == R.FLEET:
        d.polygon([(x - 16, y + 4), (x + 16, y + 4), (x + 10, y + 12), (x - 10, y + 12)], fill=fill or (255, 255, 255), outline=INK, width=2)
        d.polygon([(x - 2, y + 2), (x - 2, y - 16), (x + 12, y + 2)], fill=fill or (255, 255, 255), outline=INK, width=2)
    else:
        d.rectangle((x - 9, y - 12, x + 9, y + 12), fill=fill or (255, 255, 255), outline=INK, width=2)
        for i in range(3):
            d.rectangle((x - 9 + i * 7, y - 16, x - 5 + i * 7, y - 12), fill=INK)
    d.text((x + 22, y - 12), letter, font=font, fill=INK)


def map_png(state, out):
    """THE MAP: the shires as the data draws them, water shaded, names in small type, each harbor a ring (filled
    with its holder's mark when held), each unit a counter with its family's letter; under it the families, their
    marks and their harbors, and the season."""
    from paperdaemon.pipeline.draw import scaled as SD
    im, d = SD.canvas(PAGE_W, PAGE_H)
    me = state.get("user")
    y = AD._header(d, state.get("title") or "The Concord of Merrow Bay",
                   "%s  ·  %s" % (season_words(state), standing_words(state, me)))
    _TOP[0] = y + 6
    map_bottom = int(_TOP[0] + M.MAP_H * SCALE)
    small_f, small_lh, _ = AD._style("small")
    label_f = AD._style("label")[0]
    body_f, body_lh, _ = AD._style("body")
    units, owners = state["units"], state["owners"]
    # the water first, then every border, then the coastlines a shade darker
    for sid, sh in M.SHIRES.items():
        pts = [_to_page(px, py) for px, py in sh["poly"]]
        d.polygon(pts, fill=WATER if M.is_sea(sid) else (255, 255, 255))
    for sid, sh in M.SHIRES.items():
        pts = [_to_page(px, py) for px, py in sh["poly"]]
        for i in range(len(pts)):
            a, b = pts[i], pts[(i + 1) % len(pts)]
            d.line((a, b), fill=RULE, width=2)
    for sid, sh in M.SHIRES.items():
        if M.is_sea(sid):
            continue
        pts = [_to_page(px, py) for px, py in sh["poly"]]
        for i in range(len(pts)):
            a, b = pts[i], pts[(i + 1) % len(pts)]
            # an edge shared with the water is a coastline
            mid = ((a[0] + b[0]) / 2.0, (a[1] + b[1]) / 2.0)
            if any(M.is_sea(n) and _on_edge(mid, M.SHIRES[n]["poly"]) for n in sh["neighbors"]):
                d.line((a, b), fill=SHORE, width=3)
    d.rectangle((X0, _TOP[0], X0 + M.MAP_W * SCALE, map_bottom), outline=RULE, width=2)
    for sid, sh in M.SHIRES.items():
        lx, ly = _to_page(*sh["label"])
        # THE NAME AND WHAT STANDS UNDER IT STAY INSIDE THEIR SHIRE: at the label's own height when the cell has the
        # room there, on two lines when one is too long, else at the nearest height where it has ("Gull Reach" and
        # "Drowned Bell Deep" ran over their shores, "Tanglewood" out of the map, "The Senate Steps" across a border)
        lx, ly, names = _fit(d, sh, lx, ly, small_f, small_lh)
        top = ly - small_lh * len(names) - 6
        for k, n in enumerate(names):
            d.text((lx - d.textlength(n, font=small_f) / 2.0, top + k * small_lh), n, font=small_f,
                   fill=GRAY if M.is_sea(sid) else INK)
        # under the name: the harbor's ring at the left (filled when held), the unit's counter and its family's mark;
        # a held harbor with nobody on it names its holder beside the ring
        cy = ly + 10
        if sh["harbor"]:
            own = owners.get(sid)
            cx = lx - (40 if sid in units else 0)
            d.ellipse((cx - 9, cy - 9, cx + 9, cy + 9), fill=GRAY if own else (255, 255, 255), outline=INK, width=2)
            if own and sid not in units:
                d.text((cx + 15, cy - 12), mark(state, own), font=label_f, fill=GRAY)
            elif own and units[sid]["family"] != own:
                # another family's unit on it: the holder's mark stands before the ring, the unit's after its counter
                m = mark(state, own)
                d.text((cx - 15 - d.textlength(m, font=label_f), cy - 12), m, font=label_f, fill=GRAY)
        if sid in units:
            u = units[sid]
            _counter(d, lx, cy, u["kind"], mark(state, u["family"]), u["family"] == me, label_f)
    # THE FAMILIES: mark, name, who plays them, harbors; two rows
    y = map_bottom + 36
    fams = list((state.get("families") or {}).items())
    col = (CW - 36) / 2.0
    st = R.standing(owners)
    for i, (fid, f) in enumerate(fams):
        x = X0 + (i % 2) * (col + 36)
        yy = y + (i // 2) * (body_lh + 6)
        who = f.get("player") or ("you" if fid == me else "")
        line = "%s  %s%s" % (mark(state, fid), family_name(state, fid), (" (%s)" % who) if who else "")
        d.text((x, yy), AD._ellipsis(d, line, body_f, col - 90), font=body_f, fill=INK if not f.get("out") else GRAY)
        hs = "%d harbor%s" % (st.get(fid, 0), "" if st.get(fid, 0) == 1 else "s") if not f.get("out") else "out of the game"
        d.text((x + col - d.textlength(hs, font=small_f), yy + 4), hs, font=small_f, fill=GRAY)
    im.save(out)
    return out


def _room(poly, y):
    """The cell's extent, left to right, at the height y (page pixels) -> (x0, x1), or None when the height misses
    the cell."""
    pts = [_to_page(px, py) for px, py in poly]
    xs = []
    for i in range(len(pts)):
        (ax, ay), (bx, by) = pts[i], pts[(i + 1) % len(pts)]
        if (ay <= y < by) or (by <= y < ay):
            xs.append(ax + (bx - ax) * (y - ay) / (by - ay))
    return (min(xs), max(xs)) if len(xs) >= 2 else None


MARK_L, MARK_R = 52, 58                        # what stands under a name reaches this far left and right of its middle


def _fit(d, sh, lx, ly, font, lh):
    """Where a shire's name and the row under it (ring, counter, mark) go -> (x, y, the name's lines): the label's own
    point when both fit inside the cell there, else the nearest height where they do, the name on one line or two;
    when the cell has no such height, the place where the least of them runs over. The room is taken over the whole
    height of the lines and of the row, so a slanted border counts where it is nearest."""
    name = sh["name"]
    words = name.split()
    ways = [[name]]
    if len(words) > 1:
        cut = min(range(1, len(words)), key=lambda k: abs(d.textlength(" ".join(words[:k]), font=font)
                                                           - d.textlength(" ".join(words[k:]), font=font)))
        ways.append([" ".join(words[:cut]), " ".join(words[cut:])])
    best = None
    for step in range(0, 9):
        for dy in ((0,) if step == 0 else (12 * step, -12 * step)):
            y = ly + dy
            for names in ways:
                top = y - lh * len(names) - 6
                rows = [_room(sh["poly"], v) for v in (top + 2, top + lh * len(names) / 2.0, top + lh * len(names) - 2)]
                under = [_room(sh["poly"], v) for v in (y - 6, y + 10, y + 26)]
                if any(r is None for r in rows + under):
                    continue
                w = max(d.textlength(n, font=font) for n in names)
                lo = max(max(max(r[0] for r in rows), X0) + 10 + w / 2.0, max(max(r[0] for r in under), X0) + 6 + MARK_L)
                hi = min(min(min(r[1] for r in rows), X1) - 10 - w / 2.0, min(min(r[1] for r in under), X1) - 6 - MARK_R)
                over = max(0.0, lo - hi)
                x = min(max(lx, lo), hi) if lo <= hi else (lo + hi) / 2.0
                if over == 0:
                    return x, y, names
                if best is None or over < best[0]:
                    best = (over, x, y, names)
    if best is None:
        return lx, ly, ways[0]
    return best[1], best[2], best[3]


def _on_edge(pt, poly, eps=0.6):
    """Whether the point lies on one of the polygon's edges (in page pixels)."""
    pts = [_to_page(px, py) for px, py in poly]
    for i in range(len(pts)):
        a, b = pts[i], pts[(i + 1) % len(pts)]
        dx, dy = b[0] - a[0], b[1] - a[1]
        L = math.hypot(dx, dy) or 1.0
        t = ((pt[0] - a[0]) * dx + (pt[1] - a[1]) * dy) / (L * L)
        if -0.01 <= t <= 1.01:
            px, py = a[0] + t * dx, a[1] + t * dy
            if math.hypot(px - pt[0], py - pt[1]) <= eps:
                return True
    return False


def standing_words(state, fid):
    st = R.standing(state["owners"])
    n = st.get(fid, 0)
    return "%s hold %d harbor%s" % (family_name(state, fid), n, "" if n == 1 else "s")


def orders_png(state, out):
    """THE ORDERS PAGE: last season's orders of the user's as the engine read them, each with what came of it, what
    could not be read, and the cast's moves that touched them; then a hairline and the space to write this season's."""
    from paperdaemon.pipeline.draw import scaled as SD
    im, d = SD.canvas(PAGE_W, PAGE_H)
    y = AD._header(d, "Orders and letters", "%s  ·  write under the rule" % season_words(state))
    body_f, body_lh, _ = AD._style("body")
    small_f, small_lh, _ = AD._style("small")
    last = state.get("last") or {}
    rows = []
    for text, fate in last.get("mine") or []:
        rows.append((text, fate, INK))
    for text, why in last.get("problems") or []:
        rows.append((text, "not understood: %s" % why, GRAY))
    for text in last.get("others") or []:
        rows.append((text, "", GRAY))
    if rows:
        AD._caps(d, (X0, y), "Last season, as read")
        y += 40
        for text, fate, col in rows:
            if y + body_lh > ORDERS_TOP - 60:
                break
            if not fate:
                # a note of the season's (a retreat, a harbor taken): whole lines, wrapped
                for line in AD._wrap(d, text, body_f, CW):
                    d.text((X0, y), line, font=body_f, fill=col)
                    y += body_lh
                continue
            tw, fw = d.textlength(text, font=body_f), d.textlength(fate, font=small_f)
            if tw + fw + 40 <= CW:
                d.text((X0, y), text, font=body_f, fill=col)
                d.text((X1, y + 5), fate, font=small_f, fill=GRAY, anchor="ra")    # set from its right end: exact
                y += body_lh
            else:
                # what came of it on its own line when the order and its fate do not share one
                d.text((X0, y), AD._ellipsis(d, text, body_f, CW), font=body_f, fill=col)
                y += body_lh
                for line in AD._wrap(d, fate, small_f, CW - 40):
                    d.text((X0 + 40, y), line, font=small_f, fill=GRAY)
                    y += small_lh
    elif state.get("season_no", 0) == 0:
        for line in AD._wrap(d, "Your units stand on your home harbors. Write an order for each under the rule, one a "
                                "line: 'Harbor Row to Fogwater' moves, 'Harbor Row holds' holds, 'the Archive supports "
                                "Harbor Row to Fogwater' backs a move, 'Fogwater convoys Harbor Row to Kettle Isle' "
                                "carries a militia by sea. A unit with no order holds. In autumn, 'build fleet at Harbor "
                                "Row' and 'disband Fogwater' are heard too. A letter to a family starts with its name "
                                "('To Harriet, ...') and may run on; letters are answered first, and the season resolves "
                                "when there are orders. Everything written is read when the page syncs.",
                            body_f, CW):
            d.text((X0, y), line, font=body_f, fill=GRAY)
            y += body_lh
    d.line((X0, ORDERS_TOP - 2, X1, ORDERS_TOP - 2), fill=RULE, width=2)
    im.save(out)
    return out


def letters_png(state, out, first, last_index):
    """A LETTERS PAGE: the letters from `first` to `last_index` of the game's, each under its season and its writer,
    the user's own as they were read; the last page keeps the space to write under a hairline."""
    from paperdaemon.pipeline.draw import scaled as SD
    im, d = SD.canvas(PAGE_W, PAGE_H)
    y = AD._header(d, "Letters", season_words(state) if last_index >= len(state.get("letters") or []) - 1 else "")
    body_f, body_lh, _ = AD._style("body")
    name_f, name_lh, _ = AD._style("name")
    italic_f = AD._style("italic")[0]
    letters = (state.get("letters") or [])[first:last_index + 1]
    for L in letters:
        who = "You, to %s" % family_name(state, L["to"]) if L.get("from") == state.get("user") else family_name(state, L["from"])
        AD._caps(d, (X0, y), season_label(L.get("season_no", 0)))
        y += 30
        d.text((X0, y), who, font=name_f, fill=INK)
        y += name_lh + 4
        f = italic_f if L.get("from") == state.get("user") else body_f
        for line in AD._wrap(d, L.get("text") or "", f, CW)[:_letter_room(y, body_lh)]:
            d.text((X0, y), line, font=f, fill=INK)
            y += body_lh
        y += LETTER_GAP
    im.save(out)
    return out


LETTER_GAP = 28


def _letter_room(y, body_lh):
    """How many more lines fit from y down to the page's foot (a letter longer than a whole page ends there)."""
    return max(0, int((AD.FOOT_Y - y) // body_lh))


def _letter_height(d, state, L):
    """A letter's height on the page as letters_png draws it, without the gap under it."""
    body_f, body_lh, _ = AD._style("body")
    name_lh = AD._style("name")[1]
    f = AD._style("italic")[0] if L.get("from") == state.get("user") else body_f
    return 30 + name_lh + 4 + len(AD._wrap(d, L.get("text") or "", f, CW)) * body_lh


def season_label(n):
    return "%s, year %d" % (SEASONS[n % 2], n // 2 + 1)


def letters_plan(state):
    """Which letters go on which letters page: each page takes the letters that fit WHOLE, measured as they are
    drawn (seven to a page by count cut the seventh off mid-sentence at the foot) -> [(first, last_index)], at least
    one page. Letters are only ever added, so a page once full keeps its letters."""
    from paperdaemon.pipeline.draw import scaled as SD
    letters = state.get("letters") or []
    if not letters:
        return [(0, -1)]
    d = SD.canvas(PAGE_W, 200)[1]
    top = AD._header(d, "Letters", "Spring of year 1")
    out, first, y = [], 0, top
    for i, L in enumerate(letters):
        h = _letter_height(d, state, L)
        if i > first and y + h > AD.FOOT_Y:
            out.append((first, i - 1))
            first, y = i, top
        y += h + LETTER_GAP
    out.append((first, len(letters) - 1))
    return out


def log_png(state, out):
    """THE SEASONS: one line a family a season, the newest last; the oldest leave when the page is full."""
    from paperdaemon.pipeline.draw import scaled as SD
    im, d = SD.canvas(PAGE_W, PAGE_H)
    y = AD._header(d, "Seasons", season_words(state))
    body_f, body_lh, _ = AD._style("body")
    small_f, small_lh, _ = AD._style("small")
    # every season's lines, wrapped; the newest seasons that fit whole stay on the page, the oldest leave
    blocks = []
    for e in state.get("log") or []:
        lines = [("caps", season_label(e["season_no"]))]
        for ln in e.get("lines") or []:
            wrapped = AD._wrap(d, ln, body_f, CW)
            lines += [("body", wrapped[0])] + [("more", w) for w in wrapped[1:]]
        blocks.append(lines)
    room = int((AD.FOOT_Y - y) / body_lh)
    shown = []
    for lines in reversed(blocks):
        if sum(len(b) for b in shown) + len(lines) + 1 > room:
            break
        shown.insert(0, lines)
    if not shown and blocks:
        shown = [blocks[-1][:room]]
    for lines in shown:
        for kind, text in lines:
            if kind == "caps":
                AD._caps(d, (X0, y + 8), text)
            else:
                d.text((X0 + (36 if kind == "more" else 0), y), text, font=body_f, fill=INK)
            y += body_lh
        y += 18
    im.save(out)
    return out


__all__ = ["map_png", "orders_png", "letters_png", "letters_plan", "log_png", "season_words", "season_label",
           "family_name", "mark", "ORDERS_TOP", "standing_words"]
