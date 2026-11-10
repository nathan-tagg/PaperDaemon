"""THE GAME (design D8): its state in the page's notepad like chess and the adventure; the start, which takes the
page that asked for the map and adds the orders, letters and seasons pages after it; a season, from the orders page;
letters, from the letters page. The engine resolves; the cast's orders are the order-writer's; the model only speaks."""
import os
import re
import time

from paperdaemon import paths
from paperdaemon.pipeline.games import adventure as AD
from paperdaemon.pipeline.games import chess as CH
from . import letters as LT
from . import map as M
from . import minds as MI
from . import orders as O
from . import pages as PG
from . import rules as R

TITLE = "The Concord of Merrow Bay"
CAST = {"quill": "lenora-quill", "oakes": "harriet-oakes", "holloway": "bea-holloway", "hale": "augustus-hale",
        "shellby": "cornelius-shellby", "graves": "ottoline-graves", "stroud": "eben-stroud"}
NAMES = {"quill": "The Quills", "oakes": "The Oakes", "holloway": "The Holloways", "hale": "The Hales",
         "shellby": "The Shellbys", "graves": "The Graves", "stroud": "The Strouds"}
MARKS = {"quill": "Qu", "oakes": "Oa", "holloway": "Ho", "hale": "Ha", "shellby": "Sh", "graves": "Gr", "stroud": "St"}

READ_PROMPT = """This is a player's handwriting under the rule on their page of the Concord of Merrow Bay, a game of orders and letters.
Orders are one a line and name the shires of the bay's map: {names}. A letter to one of the families ({families}) begins
with who it is to and may run on for several lines.
Copy every line exactly as written, in order, each line separated from the next by " / ". Read a shire's name as the
nearest of the names above. Answer with one line: WRITING: <first line> / <second line> / ..."""


def _log(log, msg):
    AD._log(log, msg)


def _whose(name):
    """The possessive of a family's name: the Hales' fleet, the Graves' militia."""
    return name + ("'" if name.endswith("s") else "'s")


# ------------------------------------------------------------------------------ the state
def family_from(what):
    """The family the request names ("as the Quills", "play the Hales", "as Harriet Oakes") -> family id, or
    'quill' when it names none."""
    t = " " + " ".join(str(what or "").lower().split()) + " "
    for fid in M.FAMILIES:
        if (" %s" % fid) in t or (" %ss" % fid) in t:
            return fid
    for fid, cid in CAST.items():
        first, last = cid.split("-")[0], cid.split("-")[-1]
        if (" %s " % first) in t or (" %s " % last) in t:
            return fid
    return "quill"


def new_state(doc, user, seed=None):
    seed = seed or CH.new_seed()
    rng = CH.Rng(seed)
    families = {}
    for fid in M.FAMILIES:
        cid = None if fid == user else CAST[fid]
        player = "you"
        if cid:
            try:
                from paperdaemon.pipeline.games import characters as C
                prof = C.profile(cid)
                player = prof.get("short") or prof["name"]
            except Exception:
                player = cid.replace("-", " ").title()
        families[fid] = {"name": NAMES[fid], "mark": MARKS[fid], "cast": cid, "player": player, "out": False}
    units, owners = R.opening(M.FAMILIES)
    now = int(time.time())
    st = {"game": "concord", "version": 1, "id": "con-" + seed[:8], "doc": doc, "page_id": None, "pages": [],
          "title": TITLE, "user": user, "families": families, "units": units, "owners": owners,
          "accords": MI.opening_accords({f: d["cast"] for f, d in families.items()}),
          "season_no": 0, "rng": {"seed": seed, "draws": 0}, "planned": {}, "promises": [], "words": {}, "letters": [],
          "log": [], "last": {}, "status": "playing", "winner": [], "placements": {}, "created": now, "updated": now}
    st["rng"] = rng.state()
    plan(st)
    return st


def plan(state):
    """The cast families' orders for the coming season, written now so the letters can speak of them (D5); a family
    out of the game writes none."""
    rng = CH.Rng(**state["rng"])
    fams = {f: d["cast"] for f, d in state["families"].items()}
    order = [f for f in M.FAMILIES if f != state["user"] and not state["families"][f]["out"]]
    rng.shuffle(order)
    planned = {}
    for f in order:
        planned[f] = MI.write_orders(f, state["units"], state["owners"], state["accords"], fams, rng, state.get("promises") or (),
                                     int(state["season_no"]), last=state.get("last_result"), others={s: o for d in planned.values() for s, o in d.items()})
    state["planned"] = planned
    state["rng"] = rng.state()
    return planned


# ------------------------------------------------------------------------------ the pages
def _page_no(doc, page_id):
    return AD._page_no(doc, page_id)


def _place(state, doc, page_id, png, kind):
    """A page's picture on its page, the one before it off first."""
    from paperdaemon.pipeline.page import images as IM
    pno = _page_no(doc, page_id)
    if pno is None:
        return
    old = (state.get("placements") or {}).get(page_id)
    if old and old.get("box"):
        try:
            IM.remove_in_box(doc, pno, tuple(old["box"]), page_id=page_id)
        except Exception:
            pass
    state.setdefault("placements", {})[page_id] = AD._put_full(doc, pno, page_id, png, kind, state)


def _draw(state, doc, workdir, which=("map", "orders", "letters", "log"), log=None):
    os.makedirs(workdir, exist_ok=True)
    stamp = int(time.time() * 1000)
    jobs = []
    if "map" in which:
        jobs.append((state["map_page"], PG.map_png, "concord-map"))
    if "orders" in which:
        jobs.append((state["orders_page"], PG.orders_png, "concord-orders"))
    if "log" in which:
        jobs.append((state["log_page"], PG.log_png, "concord-log"))
    for i, (pid, fn, kind) in enumerate(jobs):
        png = os.path.join(workdir, "_concord_%s_%d_%d.png" % (kind, stamp, i))
        try:
            fn(state, png)
            _place(state, doc, pid, png, kind)
        finally:
            try:
                os.remove(png)
            except OSError:
                pass
    if "letters" in which:
        _draw_letters(state, doc, workdir, log)


def _draw_letters(state, doc, workdir, log=None):
    """The letters pages: one for every seven letters, added after the last when the letters outgrow it."""
    from paperdaemon.remarkable import library as LIB
    plan_ = PG.letters_plan(state)
    pages = state.setdefault("letters_pages", [])
    while len(pages) < len(plan_):
        new = [pid for pid, _ in LIB.insert_pages(doc, pages[-1], 1)]
        pages.extend(new)
        state["pages"] = [state["orders_page"], state["map_page"]] + pages + [state["log_page"]]
        _log(log, "  concord: a letters page added (%d)" % len(pages))
    stamp = int(time.time() * 1000)
    for i, (first, last) in enumerate(plan_):
        png = os.path.join(workdir, "_concord_letters_%d_%d.png" % (stamp, i))
        try:
            PG.letters_png(state, png, first, last)
            _place(state, doc, pages[i], png, "concord-letters")
        finally:
            try:
                os.remove(png)
            except OSError:
                pass


# ------------------------------------------------------------------------------ the start
def start(what, ask_text=None, doc=None, after=None, log=None, workdir=None):
    """A new Concord in the notebook `doc`: the page `after` (cleared by the caller) becomes the user's page -- their
    orders and letters are written there, under the rule, and it carries the tag they gave it, so a sync on it is a
    turn -- and the map, the letters and the seasons pages go right after it. -> state."""
    from paperdaemon.remarkable import library as LIB
    workdir = workdir or os.path.join(paths.state_dir(), "rm-queue")
    user = family_from(what)
    state = new_state(doc, user)
    ids = [pid for pid, _ in LIB.insert_pages(doc, after, 3)]
    state["orders_page"], state["map_page"], state["letters_pages"], state["log_page"] = after, ids[0], [ids[1]], ids[2]
    state["page_id"] = state["orders_page"]
    state["pages"] = [after, ids[0], ids[1], ids[2]]
    CH.save_state(state)                                  # saved before its pages are drawn: a job on one finds it
    _draw(state, doc, workdir, log=log)
    CH.save_state(state)
    _log(log, "  concord: started, the user plays %s; pages %s" % (NAMES[user], state["pages"]))
    return state


# ------------------------------------------------------------------------------ a season
def season(state, my_orders, wants, problems, ask_text, log=None):
    """The user's orders are in: the season resolves with the cast's planned orders, the autumn counts its harbors,
    the log and the accords take the season, promises are settled, the families write unasked, and the next season's
    cast orders are planned. -> the season's note for the receipt."""
    n = int(state["season_no"])
    me = state["user"]
    units_before = {s: dict(u) for s, u in state["units"].items()}
    orders = {}
    for f, o in (state.get("planned") or {}).items():
        orders.update(o)
    orders.update(my_orders)
    state["units_before"] = units_before
    result = R.resolve(units_before, orders)
    MI.after_season(state["accords"], units_before, result)
    word_notes = LT.settle(state, result)
    units = result["after"]
    # THE RECORD of the user's orders as read, each with what came of it
    mine_rows = []
    for s, o in my_orders.items():
        fate = result["fates"].get(s, ("", ""))
        text = o.get("text") or R.words(o, units_before)
        mine_rows.append((text, (fate[0] + ((": " + fate[1]) if fate[1] else "")).strip()))
    for s in sorted(s for s, u in units_before.items() if u["family"] == me and s not in my_orders):
        fate = result["fates"].get(s, ("held", ""))
        mine_rows.append((R.words(R.hold(s), units_before) + " (no order)", fate[0]))
    retreat_notes = []
    for s, to in result["retreats"].items():
        u = units_before[s]
        retreat_notes.append("%s %s at %s was dislodged and %s" % (_whose(state["families"][u["family"]]["name"]), u["kind"], M.NAMES[s],
                                                                    ("retreated to " + M.NAMES[to]) if to else "disbanded"))
    lines = []
    for f in M.FAMILIES:
        if state["families"][f]["out"]:
            continue
        fo = [(s, o) for s, o in orders.items() if units_before.get(s, {}).get("family") == f]
        if not fo:
            continue
        parts = []
        for s, o in sorted(fo):
            fate = result["fates"].get(s, ("", ""))
            parts.append("%s (%s)" % (R.words(o, units_before), fate[0] + ((", " + fate[1]) if fate[1] and fate[0] != "held" else "")))
        lines.append("%s: %s" % (state["families"][f]["name"], "; ".join(parts)))
    lines += retreat_notes + word_notes
    autumn_notes = []
    if n % 2 == 1:
        owners = R.harbors_after(units, state["owners"])
        for s, f in owners.items():
            if f != state["owners"].get(s) and f:
                autumn_notes.append("%s took %s%s" % (state["families"][f]["name"], M.NAMES[s],
                                                      (" from %s" % state["families"][state["owners"][s]]["name"]) if state["owners"].get(s) else ""))
        state["owners"] = owners
        for f in M.FAMILIES:
            if state["families"][f]["out"]:
                continue
            if not any(o == f for o in owners.values()):
                state["families"][f]["out"] = True
                units = {s: u for s, u in units.items() if u["family"] != f}
                autumn_notes.append("%s hold no harbor and are out of the game" % state["families"][f]["name"])
                continue
            units, notes = R.adjust(units, owners, f, wants if f == me else None)
            autumn_notes += ["%s %s" % (state["families"][f]["name"], x) for x in notes]
        win = R.winner(owners, n // 2 + 1)
        if win:
            state["status"], state["winner"] = "won", win
            autumn_notes.append("THE CONCORD IS WON by %s" % " and ".join(state["families"][f]["name"] for f in win))
    state["units"] = units
    state["log"].append({"season_no": n, "lines": lines + autumn_notes})
    state["last"] = {"mine": mine_rows, "problems": list(problems), "others": [x for x in retreat_notes + autumn_notes][:6]}
    state["last_result"] = {"contested": sorted(result["contested"]), "orders": result["orders"], "units_before": units_before}
    state["season_no"] = n + 1
    note = "%s resolved: %s" % (PG.season_label(n), "; ".join(r[0] + " -- " + r[1] for r in mine_rows) or "no orders of yours")
    if autumn_notes:
        note += ". " + "; ".join(autumn_notes[:4])
    if state["status"] == "playing":
        # the families write unasked, one letter a season at most each, then the next season is planned
        rng = CH.Rng(**state["rng"])
        for f in M.FAMILIES:
            if f == me or state["families"][f]["out"] or ask_text is None:
                continue
            try:
                text, why = LT.unasked(state, f, ask_text, rng, state["last_result"])
            except Exception as ex:
                _log(log, "  concord: %s's letter failed: %s" % (f, str(ex)[:80]))
                text = ""
            if text:
                state["letters"].append({"from": f, "to": me, "text": text, "season_no": state["season_no"], "why": why})
        state["rng"] = rng.state()
        plan(state)
    return note


# ------------------------------------------------------------------------------ a turn
def _read(doc, page_no, ask_vision, workdir, prompt, key):
    from paperdaemon.pipeline.games import inputarea as IA
    from paperdaemon.pipeline.page import tablets as TB
    s = TB.picture_page(TB.frame_of(doc, page_no))[1]
    top = PG.ORDERS_TOP * s
    typed = IA.typed(doc, page_no)
    written = IA.handwriting(doc, page_no, top, ask_vision, prompt, key, workdir) if ask_vision else ""
    return typed, written, top


def _lines(typed, written):
    out = []
    for chunk in (typed, written):
        for part in re.split(r"\s*/\s*|\n", str(chunk or "")):
            if part.strip():
                out.append(part.strip())
    return out


def sort_lines(state, lines):
    """The user's lines -> (letters [(family, text)], order lines, problems [(line, why)]). A line that addresses a
    family opens a letter, and every line after it is that letter's until the next address or the next order of
    theirs; a line that reads as an order of theirs (or a build or disband) is an order; a line that is neither,
    with no letter open, is a problem."""
    me = state["user"]
    letters, order_lines, problems, open_ = [], [], [], False
    for line in lines:
        a = LT.address(state, line)
        if a:
            letters.append([a[0], a[1]])
            open_ = True
            continue
        o = O.parse_line(line)
        is_order = bool(o.get("want"))
        if not is_order and o.get("kind") != "unknown":
            u = state["units"].get(o["unit"])
            is_order = bool(u and u["family"] == me and R.legal(state["units"], o)[0])
        if is_order and not (open_ and o.get("kind") == R.HOLD and "text" in o and len(line.split()) > 4):
            order_lines.append(line)
            open_ = False
            continue
        if open_:
            letters[-1][1] = (letters[-1][1] + " " + line).strip()
            continue
        problems.append((line, o.get("why") or ("no unit of yours at %s" % M.NAMES.get(o.get("unit"), "there"))))
    return [(f, t) for f, t in letters if t], order_lines, problems


def deliver(state, letters, ask_text, log=None):
    """The user's letters go out and the families answer -> the names of those who answered."""
    me = state["user"]
    rng = CH.Rng(**state["rng"])
    answered = []
    for fid, body in letters:
        if state["families"][fid]["out"]:
            continue
        state["letters"].append({"from": me, "to": fid, "text": body, "season_no": int(state["season_no"])})
        say, promise = "", None
        if ask_text is not None:
            try:
                say, promise = LT.answer(state, fid, body, ask_text, rng, log)
            except Exception as ex:
                _log(log, "  concord: %s's answer failed: %s" % (fid, str(ex)[:80]))
        if say:
            state["letters"].append({"from": fid, "to": me, "text": say, "season_no": int(state["season_no"]),
                                     "promise": promise["kind"] if promise else None})
            answered.append(state["families"][fid]["name"])
    state["rng"] = rng.state()
    return answered


def turn(doc, page_no, page_id, state, ask_text, ask_vision, paint=None, log=None, workdir=None):
    """A job on the user's page: their letters go out and are answered first; then, when they wrote orders, the season
    resolves. The other pages take nothing. -> (outcome, note)."""
    from paperdaemon.pipeline.games import inputarea as IA
    workdir = workdir or os.path.join(paths.state_dir(), "rm-queue")
    if state.get("status") != "playing":
        return "skipped", "the Concord is over: %s" % (" and ".join(state["families"][f]["name"] for f in state.get("winner") or []) or "finished")
    if page_id != state.get("orders_page"):
        return "skipped", "concord: orders and letters go on the game's first page, under the rule"
    me = state["user"]
    typed, written, top = _read(doc, page_no, ask_vision, workdir, READ_PROMPT.format(
        names=", ".join(M.NAMES[s] for s in M.SHIRES),
        families=", ".join("%s (%s)" % (d["name"], d["player"]) for f, d in state["families"].items() if f != me)), "WRITING")
    lines = _lines(typed, written)
    if not lines:
        return "skipped", "concord: nothing written under the rule yet"
    letters, order_lines, problems = sort_lines(state, lines)
    notes = []
    if letters:
        answered = deliver(state, letters, ask_text, log)
        notes.append("letters to %s%s" % (", ".join(state["families"][f]["name"] for f, _ in letters),
                                          (", answered by " + ", ".join(answered)) if answered else ", no answer came"))
    my_orders, wants, more = O.parse(order_lines, state["units"], me)
    problems += more
    if my_orders or wants["build"] or wants["disband"]:
        notes.append(season(state, my_orders, wants, problems, ask_text, log))
    elif problems and not letters:
        notes.append("nothing read as an order: " + "; ".join("%s (%s)" % p for p in problems[:3]))
        state["last"] = dict(state.get("last") or {}, problems=list(problems))
    IA.clear(doc, page_no, top)
    _draw(state, doc, workdir, log=log)
    CH.save_state(state)
    note = "concord: " + "; ".join(notes)
    _log(log, "  " + note[:240])
    return "done", note


__all__ = ["TITLE", "CAST", "NAMES", "MARKS", "family_from", "new_state", "plan", "start", "season", "sort_lines", "deliver", "turn"]
