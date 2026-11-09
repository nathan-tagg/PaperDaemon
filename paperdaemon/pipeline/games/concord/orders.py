"""THE USER'S ORDERS FROM PLAIN WORDS, one a line (design D4): "Kettle Isle to Gull Reach", "fleet at the Spit holds",
"Ash Hill supports Kettle Isle to Gull Reach", "the Sound convoys Ash Hill to Pearl Shoal", and with the autumn's
orders "build fleet at Harbor Row", "disband Fogwater". Shire names are found first -- whole, by a prefix of four
letters or more, or by the closest spelling (the reader gets a name wrong by a letter) -- and the words left say what
the order is. A line that cannot be placed is handed back as not understood, with why, and that unit holds."""
import difflib
import re

from . import map as M
from . import rules as R

STOP = {"to", "the", "at", "in", "on", "of", "a", "an", "and", "with", "from", "into", "my", "our", "by", "for", "it",
        "them", "then", "sea", "via", "please", "let", "will", "shall", "i", "we"}
UNIT_WORDS = {"fleet", "fleets", "militia", "militias", "boat", "boats", "ship", "ships", "men", "army", "armies",
              "troops", "unit", "units"}
FLEET_WORDS = {"fleet", "fleets", "boat", "boats", "ship", "ships"}
VERB = {
    R.HOLD: {"hold", "holds", "holding", "stay", "stays", "stand", "stands", "wait", "waits"},
    R.MOVE: {"to", "into", "attack", "attacks", "move", "moves", "go", "goes", "take", "takes", "toward", "towards", "on",
             "onto", "sail", "sails", "march", "marches"},
    R.SUPPORT: {"support", "supports", "supporting", "back", "backs", "aid", "aids", "help", "helps"},
    R.CONVOY: {"convoy", "convoys", "carry", "carries", "ferry", "ferries", "transport", "transports", "bring", "brings"},
    "build": {"build", "builds", "raise", "raises"},
    "disband": {"disband", "disbands", "remove", "removes", "dismiss", "stand-down"},
}
_PLAIN = {sid: " ".join(sh["name"].lower().replace("'", "").split()) for sid, sh in M.SHIRES.items()}
_BARE = {sid: n[4:] if n.startswith("the ") else n for sid, n in _PLAIN.items()}


def find_shire(words):
    """A shire for one to three words: whole, 'the' dropped, a prefix of four letters or more, or the closest
    spelling. -> id or None."""
    key = " ".join(w.lower().replace("'", "") for w in words).strip()
    if not key or key in STOP:
        return None
    bare = key[4:] if key.startswith("the ") else key
    for sid in M.SHIRES:
        if _PLAIN[sid] == key or _BARE[sid] == bare:
            return sid
    if len(bare) >= 4:
        hits = [sid for sid in M.SHIRES if _BARE[sid].startswith(bare)]
        if len(hits) == 1:
            return hits[0]
        if len(bare) >= 5:
            # the closest spelling, among names of as many words (three words never pass for a two-word name)
            same = [b for b in _BARE.values() if len(b.split()) == len(bare.split())]
            close = difflib.get_close_matches(bare, same, n=1, cutoff=0.8)
            if close:
                return next(sid for sid, b in _BARE.items() if b == close[0])
    return None


def _tokens(line):
    t = str(line).lower().replace("->", " to ").replace("–", " to ").replace("—", " to ")
    t = re.sub(r"\s-\s", " to ", t)
    t = re.sub(r"[^a-z0-9' \-]", " ", t)
    return [w for w in t.split() if w]


def _shires(tokens):
    """The shire names in the line, longest first at each place -> (the rest of the words, [shire ids in order])."""
    out, rest, i = [], [], 0
    while i < len(tokens):
        hit = None
        for n in (3, 2, 1):
            if i + n <= len(tokens):
                sid = find_shire(tokens[i:i + n])
                if sid:
                    hit = (sid, n)
                    break
        if hit:
            out.append(hit[0])
            i += hit[1]
        else:
            rest.append(tokens[i])
            i += 1
    return rest, out


def parse_line(line):
    """One line -> an order ({unit, kind, to, of} plus "text"), a want ({"want": "build" | "disband", ...}), or
    {"kind": "unknown", "text", "why"}."""
    tokens = _tokens(line)
    rest, shires = _shires(tokens)
    verbs = {k for k, ws in VERB.items() if any(w in ws for w in rest)}
    text = " ".join(str(line).split())
    if "build" in verbs:
        if not shires:
            return {"kind": "unknown", "text": text, "why": "build where?"}
        kind = R.FLEET if any(w in FLEET_WORDS for w in rest) else R.MILITIA if any(w in UNIT_WORDS for w in rest) else None
        return {"want": "build", "unit_kind": kind, "shire": shires[0], "text": text}
    if "disband" in verbs:
        if not shires:
            return {"kind": "unknown", "text": text, "why": "disband what?"}
        return {"want": "disband", "shire": shires[0], "text": text}
    if not shires:
        return {"kind": "unknown", "text": text, "why": "no shire named"}
    if R.SUPPORT in verbs:
        if len(shires) < 2:
            return {"kind": "unknown", "text": text, "why": "supports whom?"}
        return dict(R.support(shires[0], shires[1], shires[2] if len(shires) > 2 else None), text=text)
    if R.CONVOY in verbs:
        if len(shires) < 3:
            return {"kind": "unknown", "text": text, "why": "convoys whom, to where?"}
        return dict(R.convoy(shires[0], shires[1], shires[2]), text=text)
    if R.HOLD in verbs or len(shires) == 1:
        if len(shires) > 1 and R.HOLD not in verbs:
            return {"kind": "unknown", "text": text, "why": "two shires and no verb"}
        return dict(R.hold(shires[0]), text=text)
    if len(shires) == 2:
        return dict(R.move(shires[0], shires[1]), text=text)
    return {"kind": "unknown", "text": text, "why": "too many shires for one order"}


def parse(lines, units, family):
    """The user's lines -> (orders {unit shire: order} for the family's units, wants {"build": [(kind, shire)],
    "disband": [shire]}, problems [(line, why)]). A unit ordered twice keeps its first order; another family's unit,
    or an empty shire, is a problem, not an order."""
    orders, wants, problems = {}, {"build": [], "disband": []}, []
    for line in lines:
        if not str(line).strip():
            continue
        o = parse_line(line)
        if o.get("kind") == "unknown":
            problems.append((o["text"], o["why"]))
            continue
        if o.get("want") == "build":
            wants["build"].append((o["unit_kind"], o["shire"]))
            continue
        if o.get("want") == "disband":
            if units.get(o["shire"], {}).get("family") != family:
                problems.append((o["text"], "no unit of yours at %s" % M.NAMES[o["shire"]]))
            else:
                wants["disband"].append(o["shire"])
            continue
        u = units.get(o["unit"])
        if not u:
            problems.append((o["text"], "no unit at %s" % M.NAMES[o["unit"]]))
            continue
        if u["family"] != family:
            problems.append((o["text"], "the unit at %s is not yours" % M.NAMES[o["unit"]]))
            continue
        ok, why = R.legal(units, o)
        if not ok:
            problems.append((o["text"], why))
            continue
        if o["unit"] in orders:
            problems.append((o["text"], "%s already has its order" % M.NAMES[o["unit"]]))
            continue
        orders[o["unit"]] = o
    return orders, wants, problems


__all__ = ["find_shire", "parse_line", "parse"]
