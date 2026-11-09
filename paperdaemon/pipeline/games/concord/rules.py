"""ORDERS AND THEIR RESOLUTION, all at once, the standard way of games of this kind with two simplifications named in
the design (D3): an attack by a convoyed militia cuts a support like any other, so a convoy paradox never arises; and
a dislodged unit retreats where the engine finds room, nearest its family's harbors, with no retreat phase.

A unit is {"family": id, "kind": "fleet" | "militia"}; `units` maps each occupied shire to its unit. An order is
{"unit": the shire the ordered unit stands in, "kind": "hold" | "move" | "support" | "convoy", "to": where (a move's
destination; a supported move's destination, or None for a supported hold; a convoyed militia's destination),
"of": whose (a support's or convoy's unit, by its shire)}. `resolve` returns what happened to every order and every
unit, in words the pages and the log can use."""
import collections

from . import map as M

FLEET, MILITIA = "fleet", "militia"
HOLD, MOVE, SUPPORT, CONVOY = "hold", "move", "support", "convoy"
YEARS = 10                                  # the tenth autumn ends the game


def hold(unit):
    return {"unit": unit, "kind": HOLD}


def move(unit, to):
    return {"unit": unit, "kind": MOVE, "to": to}


def support(unit, of, to=None):
    return {"unit": unit, "kind": SUPPORT, "of": of, "to": to}


def convoy(unit, of, to):
    return {"unit": unit, "kind": CONVOY, "of": of, "to": to}


def words(order, units=None):
    """An order in words: 'Fleet Kettle Isle to Gull Reach', 'Militia Ash Hill supports Kettle Isle to Gull Reach'."""
    u = (units or {}).get(order["unit"]) or {}
    who = ("Fleet " if u.get("kind") == FLEET else "Militia " if u.get("kind") == MILITIA else "") + M.NAMES[order["unit"]]
    k = order["kind"]
    if k == MOVE:
        return "%s to %s" % (who, M.NAMES[order["to"]])
    if k == SUPPORT:
        return "%s supports %s%s" % (who, M.NAMES[order["of"]], (" to " + M.NAMES[order["to"]]) if order.get("to") else "")
    if k == CONVOY:
        return "%s convoys %s to %s" % (who, M.NAMES[order["of"]], M.NAMES[order["to"]])
    return "%s holds" % who


# ------------------------------------------------------------------------------ what an order may be
def legal(units, order):
    """-> (True, "") or (False, why): the order a unit can carry out as written, before anyone else's is known."""
    s = order.get("unit")
    u = units.get(s)
    if not u:
        return False, "no unit at %s" % M.NAMES.get(s, s)
    k = order.get("kind")
    if k == HOLD:
        return True, ""
    if k == MOVE:
        to = order.get("to")
        if to not in M.SHIRES or to == s:
            return False, "nowhere to go"
        if not M.can_stand(u["kind"], to):
            return False, "a %s cannot stand on %s" % (u["kind"], M.NAMES[to])
        if to in M.SHIRES[s]["neighbors"]:
            return True, ""
        if u["kind"] == MILITIA and M.is_coast(s) and M.is_coast(to):
            return True, ""                                   # by sea, if fleets convoy it
        return False, "%s does not touch %s" % (M.NAMES[s], M.NAMES[to])
    if k == SUPPORT:
        of, to = order.get("of"), order.get("to")
        if of not in units or of == s:
            return False, "no unit to support at %s" % M.NAMES.get(of, of)
        target = to or of
        if target not in M.SHIRES[s]["neighbors"] or not M.can_stand(u["kind"], target):
            return False, "%s cannot reach %s to support there" % (M.NAMES[s], M.NAMES.get(target, target))
        return True, ""
    if k == CONVOY:
        of, to = order.get("of"), order.get("to")
        if u["kind"] != FLEET or not M.is_sea(s):
            return False, "only a fleet at sea convoys"
        if units.get(of, {}).get("kind") != MILITIA or not M.is_coast(of):
            return False, "no militia on a coast at %s" % M.NAMES.get(of, of)
        if to not in M.SHIRES or not M.is_coast(to):
            return False, "%s is no coast to land on" % M.NAMES.get(to, to)
        return True, ""
    return False, "not an order"


def convoy_path(units, orders, of, to, broken=()):
    """The fleets that carry the militia at `of` to `to`: a chain of sea shires, each with a fleet ordered to convoy
    exactly that, from a sea touching `of` to one touching `to`; `broken` fleets carry nothing. -> frozenset of the
    chain's shires, or None."""
    carriers = {s for s, o in orders.items() if o["kind"] == CONVOY and o.get("of") == of and o.get("to") == to
                and s not in broken and units.get(s, {}).get("kind") == FLEET and M.is_sea(s)}
    if not carriers:
        return None
    starts = [s for s in carriers if s in M.SHIRES[of]["neighbors"]]
    seen, q, prev = set(starts), collections.deque(starts), {s: None for s in starts}
    while q:
        x = q.popleft()
        if to in M.SHIRES[x]["neighbors"]:
            path, y = set(), x
            while y is not None:
                path.add(y)
                y = prev[y]
            return frozenset(path)
        for y in M.SHIRES[x]["neighbors"]:
            if y in carriers and y not in seen:
                seen.add(y)
                prev[y] = x
                q.append(y)
    return None


# ------------------------------------------------------------------------------ the season, all at once
def resolve(units, orders):
    """Every order of the season -> what came of each (`moved`, `held`, `failed` with why), who was dislodged by whom
    and where they retreated, the supports cut, the convoys that carried or broke, the shires fought over, and the
    units afterwards. `orders`: {shire: order}; a unit without one holds."""
    units = {s: dict(u) for s, u in units.items()}
    fam = lambda s: units[s]["family"]
    done = {}                                         # shire -> order as carried out (illegal ones hold, with why)
    why = {}
    for s in units:
        o = orders.get(s) or hold(s)
        ok, reason = legal(units, o)
        if not ok:
            why[s] = reason
            o = hold(s)
        done[s] = dict(o, unit=s)
    broken, result = set(), None
    for _ in range(8):
        result = _once(units, done, broken)
        now_broken = {f for f in result["carriers"] if f in result["dislodged"]}
        if now_broken <= broken:
            break
        broken |= now_broken
    result["illegal"] = why
    result["orders"] = done
    # THE UNITS AFTERWARDS: movers moved, the dislodged gone from where they stood
    after = {}
    for s, u in units.items():
        if s in result["dislodged"]:
            continue
        dest = result["moved"].get(s)
        after[dest or s] = dict(u)
    retreats = {}
    for s, d in result["dislodged"].items():
        u = units[s]
        home = M.HOMES.get(u["family"], ())
        harbors = d.get("harbors") or home
        options = [n for n in M.SHIRES[s]["neighbors"] if M.can_stand(u["kind"], n) and n not in after
                   and n not in result["contested"] and n != d["from"]]
        options.sort(key=lambda n: (M.distance(n, set(harbors), u["kind"]) if M.distance(n, set(harbors), u["kind"]) is not None else 99, n))
        if options:
            after[options[0]] = dict(u)
            retreats[s] = options[0]
        else:
            retreats[s] = None
    result["retreats"] = retreats
    result["after"] = after
    return result


def _once(units, orders, broken):
    """One pass of the resolution with the convoys in `broken` carrying nothing (the loop in `resolve` finds them)."""
    fam = lambda s: units[s]["family"]
    movers = {s for s, o in orders.items() if o["kind"] == MOVE}
    carriers = set()
    valid = {}                                        # mover -> True (a move that is at least possible this pass)
    via = {}                                          # mover -> the convoy chain used, if any
    for s in movers:
        o = orders[s]
        if o["to"] in M.SHIRES[s]["neighbors"]:
            valid[s] = True
            continue
        path = convoy_path(units, orders, s, o["to"], broken)
        if path:
            valid[s], via[s] = True, path
            carriers |= path
        else:
            valid[s] = False
    attacks = collections.defaultdict(list)           # destination -> attackers (valid movers)
    for s in movers:
        if valid[s]:
            attacks[orders[s]["to"]].append(s)
    # SUPPORTS: cut when attacked from any shire but the one the support goes into, by another family
    supports = {s for s, o in orders.items() if o["kind"] == SUPPORT}
    cut = {}
    for s in supports:
        o = orders[s]
        target = o.get("to") or o["of"]
        attacker = next((x for x in attacks.get(s, []) if x != target and fam(x) != fam(s)), None)
        cut[s] = attacker
    # a support counts for a move only if the supported unit really makes that move; for a hold only if it stays
    def backing(x, kind, against=None):
        n = 0
        for s in supports:
            if cut[s]:
                continue
            o = orders[s]
            if o["of"] != x or (against and fam(s) == against):
                continue
            if kind == MOVE and o.get("to") and o["to"] == orders[x]["to"] and x in movers and valid.get(x):
                n += 1
            elif kind == HOLD and not o.get("to") and x not in movers:
                n += 1
        return n
    strength = lambda x, against=None: 1 + backing(x, MOVE, against)
    hold_strength = lambda y: 1 if y in movers else 1 + backing(y, HOLD)
    # THE MOVES: to a fixpoint. success[x] is True, False or missing (not yet known)
    success = {}
    contested = set()
    for x in movers:
        if not valid[x]:
            success[x] = False
    # head-to-head pairs first: both overland, into each other's shires
    for x in list(movers):
        if not valid[x] or x in via:
            continue
        y = orders[x]["to"]
        if y in movers and valid[y] and y not in via and orders[y]["to"] == x:
            if fam(x) == fam(y):
                success[x] = success[y] = False
            else:
                sx, sy = strength(x, fam(y)), strength(y, fam(x))
                if sx > sy:
                    success[y] = False
                elif sy > sx:
                    success[x] = False
                else:
                    success[x] = success[y] = False
    for _ in range(40):
        changed = False
        for d, xs in attacks.items():
            live = [x for x in xs if success.get(x) is not False]
            if not live:
                continue
            occupant = d if d in units else None
            best = max(strength(x) for x in live)
            top = [x for x in live if strength(x) == best]
            if len(top) > 1:
                for x in live:
                    if success.get(x) is not False:
                        success[x], changed = False, True
                contested.add(d)
                continue
            c = top[0]
            for x in live:
                if x != c and success.get(x) is not False:
                    success[x], changed = False, True
            if c in success:
                continue
            if occupant is None or occupant == c:
                success[c], changed = True, True
                continue
            if occupant in movers and valid.get(occupant):
                if success.get(occupant) is True:
                    success[c], changed = True, True
                elif success.get(occupant) is False:
                    if fam(c) != fam(occupant) and strength(c, fam(occupant)) > 1:
                        success[c], changed = True, True
                    else:
                        success[c], changed = False, True
                # else: the occupant's own move is still open; wait
                continue
            if fam(c) != fam(occupant):
                success[c], changed = (strength(c, fam(occupant)) > hold_strength(occupant)), True
            else:
                success[c], changed = False, True
        if not changed:
            # what is left open waits on itself: a ring of moves each into the next one's shire. They all go.
            open_ = [x for x in movers if valid[x] and x not in success]
            if not open_:
                break
            for x in open_:
                success[x] = True
            changed = True
    moved = {x: orders[x]["to"] for x in movers if success.get(x)}
    dislodged = {}
    for d, xs in attacks.items():
        winner = next((x for x in xs if success.get(x)), None)
        if winner and d in units and d not in moved:
            dislodged[d] = {"from": winner, "by": units[winner]["family"]}
    fates = {}
    for s, o in orders.items():
        if o["kind"] == MOVE:
            if success.get(s):
                fates[s] = ("moved", "")
            elif not valid[s]:
                fates[s] = ("failed", "no fleets carried it" if orders[s]["to"] not in M.SHIRES[s]["neighbors"] else "could not go")
            elif orders[s]["to"] in contested:
                fates[s] = ("failed", "stood off")
            else:
                fates[s] = ("failed", "held back")
        elif o["kind"] == SUPPORT:
            fates[s] = ("cut", "attacked from %s" % M.NAMES[cut[s]]) if cut.get(s) else ("gave", "")
        elif o["kind"] == CONVOY:
            fates[s] = ("carried", "") if s in carriers and s not in broken else ("idle", "no militia to carry" if s not in carriers else "broken")
        else:
            fates[s] = ("held", "")
        if s in dislodged:
            fates[s] = (fates[s][0], (fates[s][1] + "; " if fates[s][1] else "") + "dislodged from %s" % M.NAMES[s])
    return {"moved": moved, "dislodged": dislodged, "cut": {s: a for s, a in cut.items() if a}, "contested": contested,
            "carriers": carriers, "fates": fates, "valid": valid}


# ------------------------------------------------------------------------------ the autumn
def harbors_after(units, owners):
    """Every harbor to whoever stands in it after autumn; the rest keep their owner (None: nobody's yet)."""
    out = dict(owners)
    for s in M.HARBORS:
        if s in units:
            out[s] = units[s]["family"]
    return out


def adjust(units, owners, family, wants=None):
    """The family's builds (in its empty home harbors it holds: a fleet on a coast, a militia inland, or as `wants`
    says: {"build": [(kind, shire)], "disband": [shire]}) or disbands (the units farthest from its harbors) to match
    its harbors. -> (units afterwards, notes)."""
    wants = wants or {}
    units = {s: dict(u) for s, u in units.items()}
    mine = [s for s, u in units.items() if u["family"] == family]
    held = [s for s, f in owners.items() if f == family]
    delta = len(held) - len(mine)
    notes = []
    if delta > 0:
        spots = [s for s in M.HOMES.get(family, ()) if owners.get(s) == family and s not in units]
        asked = [(k, s) for k, s in (wants.get("build") or []) if s in spots and M.can_stand(k, s)]
        for k, s in asked[:delta]:
            units[s] = {"family": family, "kind": k}
            notes.append("built a %s at %s" % (k, M.NAMES[s]))
            spots.remove(s)
        for s in spots[: max(0, delta - len(asked[:delta]))]:
            k = FLEET if M.is_coast(s) else MILITIA
            units[s] = {"family": family, "kind": k}
            notes.append("built a %s at %s" % (k, M.NAMES[s]))
        if len(held) - len([s for s, u in units.items() if u["family"] == family]) > 0 and not spots:
            notes.append("no home harbor free to build in")
    elif delta < 0:
        asked = [s for s in (wants.get("disband") or []) if s in units and units[s]["family"] == family]
        far = sorted(mine, key=lambda s: (-(M.distance(s, set(held)) if held and M.distance(s, set(held)) is not None else 99), s))
        for s in (asked + [s for s in far if s not in asked])[: -delta]:
            notes.append("disbanded the %s at %s" % (units[s]["kind"], M.NAMES[s]))
            del units[s]
    return units, notes


def standing(owners):
    """Harbors held by each family -> {family: count}."""
    out = collections.Counter(f for f in owners.values() if f)
    return dict(out)


def winner(owners, year):
    """The family with a majority of the harbors at an autumn's end; after the tenth autumn the most (a tie: all of
    them). -> list of families, or []."""
    st = standing(owners)
    best = [f for f, n in st.items() if n >= M.MAJORITY]
    if best:
        return best
    if year >= YEARS and st:
        top = max(st.values())
        return sorted(f for f, n in st.items() if n == top)
    return []


def opening(families):
    """The start: each family's two units on its home harbors, a fleet on a coast and a militia inland (two coasts:
    one of each). -> (units, owners)."""
    units, owners = {}, {s: None for s in M.HARBORS}
    for f in families:
        homes = list(M.HOMES[f])
        coasts = [s for s in homes if M.is_coast(s)]
        for i, s in enumerate(homes):
            kind = FLEET if (s in coasts and (len(coasts) == 1 or i == 0)) else MILITIA
            units[s] = {"family": f, "kind": kind}
            owners[s] = f
    return units, owners


__all__ = ["FLEET", "MILITIA", "HOLD", "MOVE", "SUPPORT", "CONVOY", "YEARS", "hold", "move", "support", "convoy", "words",
           "legal", "convoy_path", "resolve", "harbors_after", "adjust", "standing", "winner", "opening"]
