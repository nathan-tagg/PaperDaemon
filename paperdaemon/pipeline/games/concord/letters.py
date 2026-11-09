"""THE LETTERS (design D5): the user writes to a family on the letters page; the family answers in its own voice,
knowing its standing, its accord with the writer and the orders it has already decided for the coming season, and
may promise something -- a support, no attack, a shire left empty, a convoy -- which it means to keep or to break.
A promise meant is a constraint on the order-writer (minds.write_orders); one meant to be broken is broken by the
orders and held against the family when it comes out. A family also writes unasked, once a season at most, when the
user attacked it or when it wants a hand."""
import re

from . import map as M
from . import minds as MI
from . import rules as R

PROMISES = ("support", "no_attack", "demilitarize", "convoy")

LETTER_PROMPT = """You are this character, the head of your family in the Concord of Merrow Bay, a game of the bay's seven old
families: each season every family orders its fleets and militias (hold, move, support, convoy), all orders resolve at
once by the rules, and the only way to get help is to be believed. You are writing a letter back.
{brief}
YOUR STANDING: {standing}
HOW YOU STAND WITH {writer_name}: {accord_words} ({accord:+.2f}; their word to you so far: {their_word}).
THE MAP NOW: {board}
YOUR ORDERS THIS COMING SEASON, ALREADY DECIDED (they may promise what agrees with these, or lie): {orders}
{writer_name} wrote to you:
"{letter}"
Answer with JSON only:
{{"say": "your letter back, in your own voice, three to six sentences, signed as you would sign",
 "promise": null or {{"kind": one of {kinds}, "unit": "the shire of THEIR unit you will support or convoy, if any",
                      "to": "where that unit is going, if any", "shire": "the shire you will stay out of, for demilitarize",
                      "seasons": 1 or 2}},
 "keep": true if you mean to keep the promise, false if you are lying -- by your own truthfulness and your interest}}
Promise only what you could do: a support needs a unit of yours next to the shire. A refusal is an answer too: promise
null, and say why in your own way."""

UNASKED_PROMPT = """You are this character, the head of your family in the Concord of Merrow Bay (a game of letters and orders among
the bay's seven old families; orders resolve at once by the rules, and help comes only from being believed).
{brief}
YOUR STANDING: {standing}
HOW YOU STAND WITH {writer_name}: {accord_words} ({accord:+.2f}).
THE MAP NOW: {board}
WHY YOU WRITE: {why}
Write {writer_name} a short letter, two to four sentences, in your own voice, signed as you would sign. Answer with JSON
only: {{"say": "the letter"}}"""


def families_named(state, text):
    """The families a letter addresses: 'To Harriet,' / 'Harriet:' / 'Dear Judge Shellby,' / 'Oakes --' at the start of
    a line -> [(family id, the letter's text)], in order; text before any address goes to the first family named, or
    to nobody."""
    names = {}
    for fid, f in (state.get("families") or {}).items():
        if fid == state.get("user"):
            continue
        for n in [fid, f.get("name", ""), f.get("player", "")] + list(f.get("aliases") or []):
            for part in re.split(r"[\s,]+", str(n or "").lower()):
                part = part.strip("'\".:;()")
                if len(part) >= 3 and part not in ("the", "and", "judge", "mayor", "senator", "family", "families"):
                    names[part] = fid
    out, cur = [], None
    for raw in str(text or "").splitlines():
        line = raw.strip()
        if not line:
            continue
        m = re.match(r"^(?:to|dear|for)?\s*([A-Za-z'][A-Za-z' .]{1,40}?)\s*[,:;\-—]+\s*(.*)$", line, re.I)
        fid = None
        if m:
            for word in re.split(r"[\s.]+", m.group(1).lower()):
                if word.strip("'") in names:
                    fid = names[word.strip("'")]
            if fid:
                cur = fid
                out.append([fid, []])
                if m.group(2).strip():
                    out[-1][1].append(m.group(2).strip())
                continue
        if cur is None:
            # the first line of all: a family's name anywhere in it starts a letter to them
            hit = next((names[w.strip("'\".:;")] for w in line.lower().split() if w.strip("'\".:;") in names), None)
            if hit:
                cur = hit
                out.append([hit, [line]])
                continue
        if out:
            out[-1][1].append(line)
    return [(fid, " ".join(lines)) for fid, lines in out if lines]


def board_words(state):
    """The map in words, for the model: each family's units and harbors."""
    units, owners = state["units"], state["owners"]
    rows = []
    for fid, f in (state.get("families") or {}).items():
        mine = sorted(s for s, u in units.items() if u["family"] == fid)
        hs = sorted(s for s, o in owners.items() if o == fid)
        rows.append("%s: %s; harbors %s" % (f.get("name", fid), ", ".join("%s at %s" % (units[s]["kind"], M.NAMES[s]) for s in mine) or "no units",
                                           ", ".join(M.NAMES[s] for s in hs) or "none"))
    free = sorted(M.NAMES[s] for s, o in owners.items() if not o)
    if free:
        rows.append("nobody's harbors: " + ", ".join(free))
    return "\n".join(rows)


def accord_words(a):
    return ("warm" if a > 0.4 else "friendly" if a > 0.15 else "cool" if a > -0.15 else "sour" if a > -0.45 else "hostile")


def their_word(state, fid):
    """What the family has seen of the user's word: promises the user made in letters are the model's to weigh; here
    the deeds -- attacks and supports between them -- in a phrase."""
    w = (state.get("words") or {}).get(fid) or {"kept": 0, "broken": 0}
    if not w["kept"] and not w["broken"]:
        return "untested"
    return "%d promise%s kept, %d broken" % (w["kept"], "" if w["kept"] == 1 else "s", w["broken"])


def _brief(cid, table):
    try:
        from paperdaemon.pipeline.games import characters as C
        return C.brief(cid, game="diplomacy", table=[t for t in table if t])
    except Exception:
        return "A head of one of the bay's families."


def answer(state, fid, letter, ask_text, rng, log=None):
    """The family's letter back, and its promise if any -> (text, promise or None); the promise is recorded in the
    state. Without a model the family does not answer."""
    from paperdaemon.pipeline.games import adventure as AD
    f = state["families"][fid]
    cid = f.get("cast")
    me = state["user"]
    t = MI.temperament(cid)
    planned = (state.get("planned") or {}).get(fid) or {}
    orders_words = "; ".join(R.words(o, state["units"]) for o in planned.values()) or "nothing decided yet"
    q = LETTER_PROMPT.format(brief=_brief(cid, [g.get("cast") for g in state["families"].values()]),
                             standing=_standing(state, fid), writer_name=state["families"][me]["name"],
                             accord_words=accord_words(MI.accord(state["accords"], fid, me)),
                             accord=MI.accord(state["accords"], fid, me), their_word=their_word(state, fid),
                             board=board_words(state), orders=orders_words, letter=letter[:1200], kinds=", ".join(PROMISES))
    reply = AD.parse_json(ask_text(q)) if ask_text else {}
    say = " ".join(str((reply or {}).get("say") or "").split())
    if not say:
        return "", None
    promise = None
    p = (reply or {}).get("promise")
    if isinstance(p, dict) and str(p.get("kind") or "").lower() in PROMISES:
        kind = str(p["kind"]).lower()
        unit = M.find(str(p.get("unit") or "")) if p.get("unit") else None
        to = M.find(str(p.get("to") or "")) if p.get("to") else None
        shire = M.find(str(p.get("shire") or "")) if p.get("shire") else None
        try:
            seasons = max(1, min(2, int(p.get("seasons") or 1)))
        except (TypeError, ValueError):
            seasons = 1
        ok = (kind == "no_attack" or (kind == "demilitarize" and shire) or (kind in ("support", "convoy") and unit and to))
        if ok:
            keep = bool((reply or {}).get("keep", True))
            # THE CHARACTER'S HONESTY has a say too: a liar's "keep" is believed less by the engine, a truthful one's more
            if keep and t["honest"] < 0.35 and rng.random() > t["honest"] + 0.3:
                keep = False
            promise = {"by": fid, "to_family": me, "kind": kind, "unit": unit, "to": to, "shire": shire,
                       "keep": keep, "until": int(state.get("season_no", 0)) + seasons, "season_no": int(state.get("season_no", 0)),
                       "said": say[:200]}
            state.setdefault("promises", []).append(promise)
    return say[:1200], promise


def _standing(state, fid):
    st = R.standing(state["owners"])
    units = sorted(s for s, u in state["units"].items() if u["family"] == fid)
    return "%d harbor(s); units: %s" % (st.get(fid, 0), ", ".join("%s at %s" % (state["units"][s]["kind"], M.NAMES[s]) for s in units) or "none")


def unasked(state, fid, ask_text, rng, last):
    """A letter the family writes on its own after a season: when the user attacked it (a warning, or an appeal), or
    when its coming orders want the user's hand (a request) -- at most one a season, more likely from a talker.
    -> (text or "", why)."""
    me = state["user"]
    f = state["families"][fid]
    cid = f.get("cast")
    t = MI.temperament(cid)
    why = ""
    if last:
        attacked = any(o["kind"] == R.MOVE and o["to"] in (last.get("units_before") or {}) and
                       (last["units_before"][o["to"]]["family"] == fid) and (last["units_before"].get(s, {}).get("family") == me)
                       for s, o in (last.get("orders") or {}).items())
        if attacked:
            why = "%s moved against you last season" % state["families"][me]["name"]
    if not why:
        planned = (state.get("planned") or {}).get(fid) or {}
        for s, o in planned.items():
            if o["kind"] == R.MOVE and any(state["units"].get(n, {}).get("family") == me for n in M.SHIRES[o["to"]]["neighbors"]):
                why = "you mean to move on %s, and a unit of %s stands beside it: their support would carry it" % (
                    M.NAMES[o["to"]], state["families"][me]["name"])
                break
    if not why or rng.random() > 0.35 + 0.5 * t["negotiation"]:
        return "", ""
    from paperdaemon.pipeline.games import adventure as AD
    q = UNASKED_PROMPT.format(brief=_brief(cid, [g.get("cast") for g in state["families"].values()]), standing=_standing(state, fid),
                              writer_name=state["families"][me]["name"], accord_words=accord_words(MI.accord(state["accords"], fid, me)),
                              accord=MI.accord(state["accords"], fid, me), board=board_words(state), why=why)
    reply = AD.parse_json(ask_text(q)) if ask_text else {}
    say = " ".join(str((reply or {}).get("say") or "").split())
    return say[:900], why


def settle(state, result):
    """After a season: which promises to the user were kept or broken by the orders given -> notes. A kept promise
    warms the accord; a broken one, found out, cools it and counts against the family's word."""
    notes = []
    n = int(state.get("season_no", 0))
    me = state["user"]
    for p in list(state.get("promises") or []):
        if p.get("season_no", 0) >= n or p.get("settled"):
            continue
        fid = p["by"]
        given = result["orders"]
        kept = False
        if p["kind"] == "support":
            kept = any(o["kind"] == R.SUPPORT and o.get("of") == p.get("unit") and o.get("to") == p.get("to")
                       for s, o in given.items() if state["units_before"].get(s, {}).get("family") == fid)
        elif p["kind"] == "convoy":
            kept = any(o["kind"] == R.CONVOY and o.get("of") == p.get("unit") and o.get("to") == p.get("to")
                       for s, o in given.items() if state["units_before"].get(s, {}).get("family") == fid)
        elif p["kind"] == "no_attack":
            kept = not any(o["kind"] == R.MOVE and state["units_before"].get(o["to"], {}).get("family") == me
                           for s, o in given.items() if state["units_before"].get(s, {}).get("family") == fid)
        elif p["kind"] == "demilitarize":
            kept = not any(o["kind"] == R.MOVE and o["to"] == p.get("shire")
                           for s, o in given.items() if state["units_before"].get(s, {}).get("family") == fid)
        w = state.setdefault("words", {}).setdefault(fid, {"kept": 0, "broken": 0})
        if kept:
            w["kept"] += 1
            MI.nudge(state["accords"], fid, me, 0.1)
            notes.append("%s kept their word (%s)" % (state["families"][fid]["name"], p["kind"].replace("_", " ")))
        else:
            w["broken"] += 1
            MI.nudge(state["accords"], fid, me, -0.3)
            notes.append("%s broke their word (%s)" % (state["families"][fid]["name"], p["kind"].replace("_", " ")))
        if p.get("until", 0) <= n or not kept:
            p["settled"] = True
    return notes


__all__ = ["families_named", "answer", "unasked", "settle", "board_words", "PROMISES"]
