"""THE BAY: twenty-eight shires from twenty-eight seed points. Each shire's cell is the part of the map nearer its seed
than any other's (a Voronoi partition clipped to the map's rectangle), so the cells tile the map with no overlap, and
two shires are neighbors exactly when their cells share an edge: what the drawing shows is what the rules use.

Kinds: SEA (water: fleets only), and land, which is COAST when it touches the water (fleets and militias) or INLAND
(militias only). Twenty shires are harbors (what the game counts); fourteen of them are the seven families' homes, two
each, and six belong to nobody at the start. Positions are in the map's own space, MAP_W x MAP_H, scaled to the page
by whoever draws it."""
import itertools
import math

MAP_W, MAP_H = 1000.0, 1300.0
SEA, COAST, INLAND = "sea", "coast", "inland"

# id: (name, kind of ground, harbor?, home family or None, seed x, seed y). Land shires are "land" here; the map
# makes each COAST or INLAND by whether its cell touches the water.
_SHIRES = [
    # the water: six reaches in a ring round the islands
    ("fogwater", "Fogwater", SEA, False, None, 301, 535),
    ("the-sound", "The Sound", SEA, False, None, 500, 420),
    ("drowned-bell-deep", "Drowned Bell Deep", SEA, False, None, 699, 765),
    ("the-narrows", "The Narrows", SEA, False, None, 301, 765),
    ("the-roads", "The Roads", SEA, False, None, 699, 535),
    ("the-outer-banks", "The Outer Banks", SEA, False, None, 500, 880),
    # the islands
    ("kettle-isle", "Kettle Isle", "land", True, None, 430, 585),
    ("gull-reach", "Gull Reach", "land", False, None, 570, 585),
    ("lantern-spit", "Lantern Spit", "land", True, None, 570, 715),
    ("pearl-shoal", "Pearl Shoal", "land", True, None, 430, 715),
    # the north shore: the Quills' quay, the town's civic rows
    ("merrow-point", "Merrow Point", "land", True, None, 130, 320),
    ("harbor-row", "Harbor Row", "land", True, "quill", 300, 215),
    ("the-archive", "The Archive", "land", True, "quill", 280, 60),
    ("the-ferry-landing", "The Ferry Landing", "land", True, "oakes", 500, 215),
    ("city-hall", "City Hall", "land", True, "oakes", 520, 60),
    ("clerks-row", "Clerk's Row", "land", True, "holloway", 745, 220),
    ("the-records-yard", "The Records Yard", "land", True, "holloway", 760, 60),
    # the east shore
    ("the-senate-steps", "The Senate Steps", "land", True, "hale", 960, 230),
    ("hales-landing", "Hale's Landing", "land", True, "hale", 900, 400),
    ("tanglewood", "Tanglewood", "land", True, "shellby", 960, 600),
    ("the-courthouse", "The Courthouse", "land", True, "shellby", 895, 640),
    ("the-strip", "The Strip", "land", True, None, 905, 880),
    # the south shore
    ("the-cannery", "The Cannery", "land", True, None, 740, 1110),
    ("strouds-wharf", "Stroud's Wharf", "land", True, "stroud", 500, 1150),
    ("the-lobster-grounds", "The Lobster Grounds", "land", True, "stroud", 270, 1130),
    ("salt-pans", "Salt Pans", "land", False, None, 520, 1255),
    # the west shore: the Tower
    ("the-tower", "The Tower", "land", True, "graves", 105, 560),
    ("graves-hill", "Graves Hill", "land", True, "graves", 90, 760),
]
FAMILIES = ("quill", "oakes", "holloway", "hale", "shellby", "graves", "stroud")
EPS = 1e-6


def _clip(poly, a, b):
    """The part of `poly` nearer seed a than seed b (Sutherland-Hodgman against the bisector)."""
    mx, my = (a[0] + b[0]) / 2.0, (a[1] + b[1]) / 2.0
    dx, dy = b[0] - a[0], b[1] - a[1]
    inside = lambda p: (p[0] - mx) * dx + (p[1] - my) * dy <= EPS
    out = []
    for i, p in enumerate(poly):
        q = poly[(i + 1) % len(poly)]
        pin, qin = inside(p), inside(q)
        if pin:
            out.append(p)
        if pin != qin:
            fp = (p[0] - mx) * dx + (p[1] - my) * dy
            fq = (q[0] - mx) * dx + (q[1] - my) * dy
            t = fp / (fp - fq)
            out.append((p[0] + (q[0] - p[0]) * t, p[1] + (q[1] - p[1]) * t))
    return out


def _cells(seeds):
    rect = [(0.0, 0.0), (MAP_W, 0.0), (MAP_W, MAP_H), (0.0, MAP_H)]
    cells = []
    for i, a in enumerate(seeds):
        poly = rect
        for j, b in enumerate(seeds):
            if i != j:
                poly = _clip(poly, a, b)
        cells.append(poly)
    return cells


def _key(p):
    return (round(p[0], 4), round(p[1], 4))


def _build():
    seeds = [(float(s[5]), float(s[6])) for s in _SHIRES]
    cells = _cells(seeds)
    shires = {}
    for s, poly in zip(_SHIRES, cells):
        sid, name, kind, harbor, home, x, y = s
        shires[sid] = {"id": sid, "name": name, "kind": kind, "harbor": bool(harbor), "home": home, "seed": (float(x), float(y)),
                       "poly": [(round(px, 3), round(py, 3)) for px, py in poly], "neighbors": []}
    # NEIGHBORS: cells that share an edge (two vertices in common; a corner alone is not a border)
    verts = {sid: {_key(p) for p in sh["poly"]} for sid, sh in shires.items()}
    for a, b in itertools.combinations(shires, 2):
        if len(verts[a] & verts[b]) >= 2:
            shires[a]["neighbors"].append(b)
            shires[b]["neighbors"].append(a)
    for sh in shires.values():
        sh["neighbors"].sort()
        if sh["kind"] != SEA:
            sh["kind"] = COAST if any(shires[n]["kind"] == SEA for n in sh["neighbors"]) else INLAND
        sx, sy = sh["seed"]
        # the label stands at the cell's center of mass, which keeps it inside the shire
        xs = [p[0] for p in sh["poly"]]
        ys = [p[1] for p in sh["poly"]]
        sh["label"] = (round(sum(xs) / len(xs), 1), round(sum(ys) / len(ys), 1))
    return shires


SHIRES = _build()
NAMES = {sid: sh["name"] for sid, sh in SHIRES.items()}
HARBORS = tuple(sid for sid, sh in SHIRES.items() if sh["harbor"])
HOMES = {f: tuple(sid for sid, sh in SHIRES.items() if sh["home"] == f) for f in FAMILIES}
MAJORITY = len(HARBORS) // 2 + 1


def is_sea(sid):
    return SHIRES[sid]["kind"] == SEA


def is_land(sid):
    return SHIRES[sid]["kind"] != SEA


def is_coast(sid):
    return SHIRES[sid]["kind"] == COAST


def can_stand(kind, sid):
    """A fleet stands on water and coasts; a militia on land."""
    return is_sea(sid) or is_coast(sid) if kind == "fleet" else is_land(sid)


def can_move(kind, a, b):
    """One step: a fleet between water and coasts that touch, a militia between land shires that touch (by sea it
    needs a convoy: rules.convoy_paths)."""
    return b in SHIRES[a]["neighbors"] and can_stand(kind, a) and can_stand(kind, b)


def distance(a, targets, kind=None):
    """Steps from shire a to the nearest of `targets`: over any shire when `kind` is None, else over the shires a unit
    of that kind may stand on (a convoy not counted); None when unreachable."""
    if a in targets:
        return 0
    seen, front, n = {a}, [a], 0
    while front:
        n += 1
        nxt = []
        for x in front:
            for y in SHIRES[x]["neighbors"]:
                if y in seen or (kind and not can_stand(kind, y)):
                    continue
                if y in targets:
                    return n
                seen.add(y)
                nxt.append(y)
        front = nxt
    return None


def find(name):
    """A shire by its name, loosely: exact, then 'the' dropped, then a unique prefix. -> id or None."""
    key = " ".join(str(name or "").lower().replace("'", "").split())
    if not key:
        return None
    plain = lambda s: " ".join(s.lower().replace("'", "").split())
    for sid, sh in SHIRES.items():
        if plain(sh["name"]) == key or plain(sh["name"]).removeprefix("the ") == key.removeprefix("the "):
            return sid
    hits = [sid for sid, sh in SHIRES.items() if plain(sh["name"]).removeprefix("the ").startswith(key.removeprefix("the "))]
    return hits[0] if len(hits) == 1 else None


def bounds():
    return (0.0, 0.0, MAP_W, MAP_H)


def polygon_area(poly):
    return abs(sum(poly[i][0] * poly[(i + 1) % len(poly)][1] - poly[(i + 1) % len(poly)][0] * poly[i][1]
                   for i in range(len(poly)))) / 2.0


def describe(sid):
    sh = SHIRES[sid]
    return "%s (%s%s%s)" % (sh["name"], sh["kind"], ", a harbor" if sh["harbor"] else "",
                            (", home of the %s" % sh["home"].capitalize() + "s") if sh["home"] else "")


__all__ = ["SHIRES", "NAMES", "HARBORS", "HOMES", "FAMILIES", "MAJORITY", "MAP_W", "MAP_H", "SEA", "COAST", "INLAND",
           "is_sea", "is_land", "is_coast", "can_stand", "can_move", "distance", "find", "describe", "polygon_area",
           "math"]
