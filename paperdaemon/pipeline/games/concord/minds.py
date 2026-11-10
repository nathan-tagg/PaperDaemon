"""THE CAST FAMILIES' ORDERS AND THE ACCORDS (design D7). A cast family's orders come from an order-writer, not the
model: deterministic given the seed, so a season is reproducible and testable. The character's temperament shapes it
-- ruthlessness decides whose harbors are fair game, nerve the taste for a move that can bounce, read how far ahead it
looks, negotiation how readily it supports an ally -- and the promises its letters made (D5) are constraints. The model
only speaks (letters.py); the engine decides what the family does.

ACCORD: a number from -1 to 1 for every pair of families, from the profiles' relationships at the start, raised by
support given and promises kept, lowered by attacks, dislodgements and promises broken."""
from . import map as M
from . import rules as R

# how a profile's relationship kinds start an accord
WARMTH = {"friend": 0.6, "family": 0.7, "partner": 0.6, "affair": 0.3, "crush": 0.4, "colleague": 0.3, "admires": 0.4,
          "fan": 0.4, "fellow": 0.4, "client": 0.3, "mentor": 0.5, "student": 0.4, "protects": 0.5, "pet": 0.5,
          "owner": 0.5, "boss": 0.1, "neighbor": 0.1, "ex": -0.1, "creditor": -0.2, "debtor": -0.2, "rival": -0.4,
          "wary": -0.3, "fear": -0.3, "suspects": -0.4, "investigating": -0.4, "blackmail": -0.5, "contempt": -0.6,
          "enemy": -0.8}
DEFAULT = {"ruthless": 0.5, "nerve": 0.5, "read": 0.5, "negotiation": 0.5, "bluff": 0.5, "honest": 0.7, "drive": 0.6}


def temperament(cid):
    """The character's knobs, 0..1, from their profile's abilities and voice; the defaults for a family nobody plays."""
    if not cid:
        return dict(DEFAULT)
    try:
        from paperdaemon.pipeline.games import characters as C
        p = C.profile(cid)
    except Exception:
        return dict(DEFAULT)
    ab = p.get("abilities") or {}
    k = lambda n: max(0.0, min(1.0, float(ab.get(n, 50)) / 100.0))
    return {"ruthless": k("ruthlessness"), "nerve": k("nerve"), "read": k("read"), "negotiation": k("negotiation"),
            "bluff": k("bluff"), "honest": max(0.0, min(1.0, float((p.get("voice") or {}).get("truthfulness", 0.7)))),
            "drive": max(0.0, min(1.0, float((p.get("agenda") or {}).get("win_drive", 0.6))))}


def pair(a, b):
    return "|".join(sorted((a, b)))


def accord(accords, a, b):
    return 0.0 if a == b else float(accords.get(pair(a, b), 0.0))


def opening_accords(families):
    """{family: character id or None} -> the accords at the start, from the profiles' relationships (each side's
    feeling for the other, averaged); families nobody plays, and pairs with no history, start at 0."""
    out = {}
    try:
        from paperdaemon.pipeline.games import characters as C
    except Exception:
        C = None
    rel = {}
    if C:
        for f, cid in families.items():
            if not cid:
                continue
            try:
                p = C.profile(cid)
            except Exception:
                continue
            for r in p.get("relationships") or []:
                g = next((h for h, c in families.items() if c == r.get("with")), None)
                if g and g != f:
                    rel.setdefault(pair(f, g), []).append(WARMTH.get(r.get("kind"), 0.0) * float(r.get("strength", 0.5)))
    fams = list(families)
    for i, a in enumerate(fams):
        for b in fams[i + 1:]:
            vals = rel.get(pair(a, b)) or []
            out[pair(a, b)] = round(sum(vals) / len(vals), 3) if vals else 0.0
    return out


def nudge(accords, a, b, by):
    if a == b:
        return
    k = pair(a, b)
    accords[k] = round(max(-1.0, min(1.0, float(accords.get(k, 0.0)) + by)), 3)


def after_season(accords, units_before, result):
    """What the season's deeds did to the accords: an attack on a family's unit or harbor -0.15, dislodging it another
    -0.25, a support given to a family's unit +0.1."""
    fam = lambda s: units_before[s]["family"]
    for s, o in result["orders"].items():
        if o["kind"] == R.MOVE and o["to"] in units_before and fam(o["to"]) != fam(s):
            nudge(accords, fam(s), fam(o["to"]), -0.15)
        elif o["kind"] == R.SUPPORT and o["of"] in units_before and fam(o["of"]) != fam(s) and s not in result["cut"]:
            nudge(accords, fam(s), fam(o["of"]), 0.1)
    for s, d in result["dislodged"].items():
        nudge(accords, d["by"], fam(s), -0.25)
    return accords


# ------------------------------------------------------------------------------ the order-writer
def _promises_for(promises, fid, season_no):
    """The family's promises still binding this season: those it means to keep."""
    return [p for p in promises or [] if p.get("by") == fid and p.get("keep") and p.get("until", 0) >= season_no]


def may_attack(t, acc):
    """Whether a family of temperament `t` attacks one it stands at accord `acc` with: the ruthless attack anyone
    but a close friend, the gentle only an enemy."""
    return acc < 0.6 * t["ruthless"] - 0.1


def write_orders(fid, units, owners, accords, families, rng, promises=(), season_no=0, cast_id=None, last=None,
                 others=None):
    """The family's orders for the season -> {shire: order}, every one legal. `families`: {fid: cast id or None};
    `last`: the season before's result, whose stand-offs this one remembers; `others`: orders other families have
    already written this season (what the letters between them settled, abstracted: a family backs a friend's attack
    and keeps out of a friend's way)."""
    t = temperament(cast_id if cast_id is not None else families.get(fid))
    mine = sorted(s for s, u in units.items() if u["family"] == fid)
    if not mine:
        return {}
    others = others or {}
    bind = _promises_for(promises, fid, season_no)
    no_attack = {p.get("to_family") for p in bind if p.get("kind") == "no_attack"}
    keep_empty = {p.get("shire") for p in bind if p.get("kind") in ("demilitarize", "no_attack") and p.get("shire")}
    contested_before = set((last or {}).get("contested") or ())
    tempers = {g: temperament(c) for g, c in families.items()}
    my_harbors = {s for s, f in owners.items() if f == fid}
    targets = {s for s in M.HARBORS if owners.get(s) != fid}
    standing = R.standing(owners)
    leader = max(standing, key=lambda g: (standing[g], g)) if standing else None
    autumn = season_no % 2 == 1                                    # harbors count at autumn's end: spring is for moving
    friends = {g for g in families if g != fid and accord(accords, fid, g) > 0.1}
    # THE ENEMY OF MY ENEMY: a family already attacking one we may attack too is a friend for the season
    for x, o in others.items():
        g = units.get(x, {}).get("family")
        if g and g != fid and o["kind"] == R.MOVE and o["to"] in units and accord(accords, fid, g) >= -0.1:
            h = units[o["to"]]["family"]
            if h != fid and may_attack(t, accord(accords, fid, h)):
                friends.add(g)

    def hostile(g):
        return g != fid and may_attack(tempers.get(g, DEFAULT), accord(accords, g, fid))

    def danger(n, besides=None):
        """units of other families that could move on n"""
        return sum(1 for x in M.SHIRES[n]["neighbors"] if x in units and units[x]["family"] != fid and x != besides
                   and M.can_move(units[x]["kind"], x, n) and hostile(units[x]["family"]))

    threatened = {s for s in mine if danger(s)}
    friends_going = {o["to"] for s, o in others.items() if o["kind"] == R.MOVE and units.get(s, {}).get("family") in friends}

    def score_move(s, n):
        u = units[s]
        own = owners.get(n)
        if n in keep_empty or n in friends_going:
            return -50.0
        sc = 0.0
        if n in units:
            g = units[n]["family"]
            if g == fid or g in no_attack or not may_attack(t, accord(accords, fid, g)):
                return -50.0
            defend = 1 + sum(1 for x in M.SHIRES[n]["neighbors"] if x in units and units[x]["family"] == g)
            helpers = sum(1 for x in M.SHIRES[n]["neighbors"] if x in units and x != s and M.can_stand(units[x]["kind"], n)
                          and (units[x]["family"] == fid or (units[x]["family"] in friends
                                                             and may_attack(tempers[units[x]["family"]], accord(accords, units[x]["family"], g)))))
            odds = 1.0 if helpers + 1 > defend else 0.6 if helpers + 1 == defend else 0.25 + 0.35 * t["nerve"]
            sc += (10.0 if M.SHIRES[n]["harbor"] else 3.0) * odds
            if g == leader and standing.get(g, 0) > standing.get(fid, 0):
                sc += 2.0 * t["read"]                                # the one pulling ahead is everyone's problem
        elif M.SHIRES[n]["harbor"] and own != fid:
            if own and (own in no_attack or not may_attack(t, accord(accords, fid, own))):
                return -50.0
            sc += 12.0 if own is None else 9.0
        else:
            d_now = M.distance(s, targets, u["kind"])
            d_then = M.distance(n, targets, u["kind"])
            if d_now is not None and d_then is not None and d_then < d_now:
                sc += 3.0 * t["drive"]
        if s in my_harbors and danger(s):
            sc -= (8.0 if autumn else 2.0) * (1.0 - 0.3 * t["nerve"])    # leaving a threatened harbor of ours empty
        sc -= 2.0 * danger(n) * (1.0 - t["nerve"]) * (0.5 if n in units else 1.0)
        if n in contested_before:
            sc -= 4.0 * (1.0 - 0.5 * t["read"])                  # we stood off there last season: think again
        return sc

    def score_hold(s):
        return (1.0 + ((6.0 if autumn else 3.0) if s in threatened and s in my_harbors else 0.0)) * (1.2 - 0.4 * t["drive"])

    # EVERY UNIT'S CHOICES, best first; then the family takes them in order of worth, no two into one shire, and a
    # unit whose best is taken falls back to its next, or holds. Near-equal choices are a coin's: the same bounce every
    # season is nobody's plan.
    choices = {}
    for s in mine:
        u = units[s]
        opts = [(score_hold(s), R.hold(s))]
        for n in M.SHIRES[s]["neighbors"]:
            if M.can_move(u["kind"], s, n):
                opts.append((score_move(s, n), R.move(s, n)))
        opts = [(sc + rng.random() * 1.5 * t["nerve"], o) for sc, o in opts]
        opts.sort(key=lambda x: -x[0])
        choices[s] = opts
    orders, taken = {}, set()
    for s in sorted(mine, key=lambda s: -choices[s][0][0]):
        for sc, o in choices[s]:
            dest = o.get("to")
            if o["kind"] == R.MOVE and dest in taken:
                continue
            orders[s] = o
            if o["kind"] == R.MOVE:
                taken.add(dest)
            break
    # PROMISES KEPT come first, whatever the plan was: a support or a convoy written as promised, by a unit that can
    for p in bind:
        if p.get("kind") == "support" and p.get("unit") in units and p.get("to"):
            able = [s for s in mine if p["to"] in M.SHIRES[s]["neighbors"] and M.can_stand(units[s]["kind"], p["to"])]
            able.sort(key=lambda s: (orders[s]["kind"] != R.HOLD, s))
            if able:
                orders[able[0]] = R.support(able[0], p["unit"], p["to"])
        if p.get("kind") == "convoy" and p.get("unit") in units and p.get("to"):
            fleet = next((s for s in mine if units[s]["kind"] == R.FLEET and M.is_sea(s)), None)
            if fleet:
                orders[fleet] = R.convoy(fleet, p["unit"], p["to"])
    # SUPPORTS: a holding unit backs a move of ours next door that meets a defender or that another family can also
    # reach; else a friend's attack on a family we may attack too; else a threatened harbor of ours; else, when we
    # stand well with them, a neighbor's unit under threat
    for s in mine:
        if orders[s]["kind"] != R.HOLD:
            continue
        u = units[s]
        backed = False
        for x in sorted(mine, key=lambda x: -choices[x][0][0]):
            o = orders[x]
            if o["kind"] != R.MOVE or o["to"] not in M.SHIRES[s]["neighbors"] or not M.can_stand(u["kind"], o["to"]):
                continue
            if o["to"] in units or danger(o["to"], besides=x) or o["to"] in contested_before:
                orders[s] = R.support(s, x, o["to"])
                backed = True
                break
        if backed:
            continue
        for x, o in others.items():
            g = units.get(x, {}).get("family")
            if g not in friends or o["kind"] != R.MOVE or o["to"] not in M.SHIRES[s]["neighbors"] or not M.can_stand(u["kind"], o["to"]):
                continue
            held_by = units.get(o["to"], {}).get("family")
            if held_by and held_by != fid and held_by not in no_attack and may_attack(t, accord(accords, fid, held_by)):
                orders[s] = R.support(s, x, o["to"])
                backed = True
                break
        if backed:
            continue
        ally = next((x for x in M.SHIRES[s]["neighbors"] if x in units and units[x]["family"] == fid and x in threatened
                     and orders[x]["kind"] == R.HOLD and M.can_stand(u["kind"], x)), None)
        if ally:
            orders[s] = R.support(s, ally)
        elif t["negotiation"] > 0.55:
            friend = next((x for x in M.SHIRES[s]["neighbors"] if x in units and units[x]["family"] in friends
                           and danger(x) and M.can_stand(u["kind"], x)), None)
            if friend:
                orders[s] = R.support(s, friend)
    for s, o in orders.items():
        ok, _ = R.legal(units, o)
        if not ok:
            orders[s] = R.hold(s)
    return orders


def wants(fid, units, owners, rng):
    """The family's autumn builds and disbands, left to the rules' defaults (a fleet on a coast, a militia inland;
    the farthest unit disbanded)."""
    return {}


__all__ = ["temperament", "opening_accords", "accord", "nudge", "after_season", "write_orders", "may_attack", "wants", "pair"]
