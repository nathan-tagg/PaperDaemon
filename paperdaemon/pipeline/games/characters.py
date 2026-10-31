r"""Game characters: the profiles the model plays, the faces the chart layer draws.

One JSON file per character in games/characters/ (schema 2); games/characters/cast.md is the plan they
are written from (the setting, the circles, who is tied to whom). The host reads a profile to brief the
model -- who they are, what they carry, how they feel and show it, what they want, how good they are at
THIS game -- and the model decides each character's move and words within that. The model never holds
the game state; the game's engine does. The model writes the dialog, so a profile gives it material
(history, voice, agenda, secrets), never scripted lines.

An installed cast may declare its circles (the groups its characters belong to) in
games/characters/cast.json: {"name": "A title for the cast book", "setting": "where they live, for pictures",
"circles": {"harbor": "The Harbor", ...}}
(or "circles" as a plain list of ids). Declared circles are the only ones a profile may use and set the
order of the cast book; with none declared, any circle id is accepted.

    roster()                            # {id: profile}
    find(game="chess", elo=800)         # best matches, closest skill first
    skill("alice", "monopoly")          # 0..100, the profile's own number or derived (catalog)
    brief("bob", game="chess", table=["carol"])   # the text a model is given to play them
    reveal("alice", "surprised", .8, ["danger"], rng.random)   # what the table sees
    dialog([say("bob", "smug", "Shiny!"), narrate("Bob takes on f3.")])   # a chart spec

A PROFILE (validate_profile is the authority; every block is checked, stray keys are refused):

  id, name, short, kind, species?, sex (male | female), age, circle, summary, look
  backstory      {prose, facts: [what others could know]}
  secrets?       [{id, truth, known_by: [ids], slip: 0..1, hints: [...]}]
  groups?        [{id (games/characters/groups.json), role, secret: bool, sign?}]
  agenda?        {win_drive 0..1, goals: [...], target: id or null, prose}
  personality    {traits: the nine TRAITS 0..1, prose}
  temperament    {baseline: emotion, level 0..1, leanings: {emotion: 0.2..3}, volatility 0..1,
                  recovery 0..1, hot_buttons: [{situation, feeling, weight 0..3}], prose}
  expression     {expressiveness 0..1, mask: emotion or null, tells: [tell], prose}
      tell       {id, when: {feeling?, min?, situation?}, leak 0..1,
                  face?: emotion, mark?: faces.MARKS, act?: what the narrator sees, says?: a slip}
  voice          {style, samples, chattiness 0..1, truthfulness 0..1, advice 0..1, tics?: [...]}
  relationships? [{with: id, kind: REL_KINDS, feeling: emotion or null, strength 0..1, history, knows?}]
  abilities      the fourteen of games/catalog.json, 0..100
  games          {catalog game id: {skill? 0..100 | elo? (chess), style?, love? -1..1, notes?}}
  dnd?           {player: {skill, roleplay, tactics, rules 0..100, class, race, style},
                  dm: {skill, style} or null, table}
  consistency    {blunder 0..1, genius 0..1, prose}
  quirks?, likes?, dislikes?   [...]

FEELING and FACE are two things. A feeling is the character's own state, whoever caused it. What
reaches the table is reveal(): the face shows the feeling with probability expressiveness x (0.5 + 0.5 x
intensity), else the first tell that fires with a face, else the mask. A TELL fires on a feeling (and a
minimum intensity) and/or a SITUATION the game reports (bluffing, lying, fellow_near...), each with its
own leak, and shows through any of four channels: an emotion face, a subtle MARK on whatever face shows
(a glint on a lens, a bead of sweat -- faces.MARKS), an ACT the narrator describes ("taps her temple
twice"), or words SAID ("I never said that"). Nothing tells the player what a tell
means; they learn it.

Characters are FICTIONAL. Archetypes are welcome; real people are not, since a character speaks for
itself on the page.
"""
import base64
import glob
import json
import os
from paperdaemon import paths
from paperdaemon.pipeline.games import faces

HERE = os.path.dirname(os.path.abspath(__file__))
# the profiles and faces are installed content (see paperdaemon/paths.py); the catalog of games ships with the code
ROOT = paths.content_path("games", "characters")
# rendered faces are a cache: drawn on first use into the data folder's cache, never beside the profiles (the shipped cast
# sits in the program's own folder, which an installed app cannot write to)
FACES = paths.cache_dir("faces")
CATALOG = os.path.join(HERE, "catalog.json")
GROUPS = os.path.join(ROOT, "groups.json")
SCHEMA = 2
EMOTIONS = faces.EMOTIONS
MARKS = faces.MARKS
from paperdaemon.pipeline.games import cast as rm_cast
MARKS = tuple(dict.fromkeys((*MARKS,*rm_cast.MARKS)))
TRAITS = ("aggression", "caution", "risk", "patience", "ego", "humor", "sociability", "honesty", "focus")
KINDS = ("human", "animal", "robot", "wizard", "witch", "android")
SEXES = ("male", "female")
REL_KINDS = ("friend", "family", "partner", "ex", "affair", "crush", "rival", "enemy", "fear", "mentor",
             "student", "colleague", "boss", "creditor", "debtor", "blackmail", "investigating", "suspects",
             "protects", "contempt", "admires", "fan", "fellow", "pet", "owner", "neighbor", "client", "wary")
SITUATIONS = ("winning", "losing", "close", "turning", "slipping", "scored", "hit", "blundered",
              "their_blunder", "danger", "attacking", "trap", "strong_hand", "weak_hand", "bluffing", "lying",
              "lie_heard",       # someone at the table just told a lie (the listener's side of `lying`)
              "ward_hurt",       # someone they protect is in danger or was hit this turn
              "lucky", "unlucky", "insulted", "praised", "teased", "target_near", "fear_near", "fellow_near",
              "rival_near", "start", "won", "lost")
FACE_PX = 400                         # pre-rendered face size; the chart scales it down
ELO_MIN, ELO_MAX = 400, 3200
EXPRESSION_DEFAULT = {"expressiveness": 0.8, "mask": None, "tells": [], "prose": ""}
MAX_MARKS = 3

_CACHE = {"key": None, "roster": {}}
_FILES = {}


class CharacterError(ValueError):
    pass


def _json(path):
    """A JSON file, cached until it changes."""
    mt = os.path.getmtime(path)
    hit = _FILES.get(path)
    if not hit or hit[0] != mt:
        with open(path, encoding="utf-8") as f:
            _FILES[path] = (mt, json.load(f))
    return _FILES[path][1]


def catalog():
    """{"abilities": [...], "games": {id: {name, family, players, luck, weights, scale?}}}"""
    return _json(CATALOG)


def groups():
    """{id: {name, secret, about}}"""
    try:
        return _json(GROUPS)["groups"]
    except OSError:                                # no characters installed
        return {}


def abilities():
    return tuple(catalog()["abilities"])


def _cast_declaration():
    """The installed cast's own declarations (games/characters/cast.json), or {}."""
    try:
        decl = _json(os.path.join(ROOT, "cast.json"))
    except (OSError, ValueError):                  # no characters installed, or no declarations
        return {}
    return decl if isinstance(decl, dict) else {}


def circles():
    """{circle id: display name} the installed cast declares, in its order; {} when it declares none.
    cast.json's "circles" is an object of id -> name or a list of ids (the name is then made from the id)."""
    decl = _cast_declaration().get("circles")
    if isinstance(decl, dict):
        return {str(k): str(v) for k, v in decl.items()}
    if isinstance(decl, list):
        return {str(c): str(c).replace("-", " ").capitalize() for c in decl}
    return {}


def circle_name(circle):
    """A circle's display name: the cast's own, else made from the id."""
    return circles().get(circle) or str(circle).replace("-", " ").capitalize()


def setting():
    """Where the installed cast lives, for the pictures its games make: cast.json's "setting" ("a little harbor
    town"), else ""."""
    return str(_cast_declaration().get("setting") or "").strip()


def cast_name():
    """The title of the cast book: cast.json's "name", else "Characters"."""
    return str(_cast_declaration().get("name") or "Characters")


# ---------------------------------------------------------------- profiles
def validate_profile(p, path="profile"):
    """Raise CharacterError naming the first thing wrong with a profile; return it when sound. Checks
    one profile on its own; check_roster() checks the ties between them."""
    def need(cond, msg):
        if not cond:
            raise CharacterError("%s: %s" % (path, msg))

    def num(v, lo, hi):
        return isinstance(v, (int, float)) and not isinstance(v, bool) and lo <= v <= hi

    def text(v, empty=False):
        return isinstance(v, str) and (empty or v.strip() != "")

    def keys(obj, allowed, where, required=()):
        need(isinstance(obj, dict), "%s must be an object" % where)
        stray = set(obj) - set(allowed)
        need(not stray, "%s: unknown key(s) %s" % (where, ", ".join(sorted(stray))))
        for k in required:
            need(k in obj, "%s: missing %r" % (where, k))

    top = ("schema", "id", "name", "short", "kind", "species", "sex", "age", "circle", "summary", "look",
           "backstory", "secrets", "groups", "agenda", "personality", "temperament", "expression", "voice",
           "relationships", "abilities", "games", "dnd", "consistency", "quirks", "likes", "dislikes",
           "player", "alters", "adapts")
    keys(p, top, "profile", ("schema", "id", "name", "short", "kind", "sex", "age", "circle", "summary",
                             "look", "backstory", "personality", "temperament", "expression", "voice",
                             "abilities", "games", "consistency"))
    need(p["schema"] == SCHEMA, "schema must be %d" % SCHEMA)
    need(text(p["id"]) and p["id"] == p["id"].lower() and " " not in p["id"], "id must be lowercase, no spaces")
    for k in ("name", "short", "age", "summary"):
        need(text(p[k]), "%s is text" % k)
    # male or female, nothing more
    need(p["sex"] in SEXES, "sex is male or female")
    need(p["kind"] in KINDS, "kind is one of %s" % ", ".join(KINDS))
    declared = circles()
    need(text(p["circle"]) and (not declared or p["circle"] in declared),
         "circle is one of %s" % ", ".join(declared) if declared else "circle is text")
    look = p["look"]
    need(isinstance(look, dict) and all(k in look for k in ("badge", "head", "skin")), "look needs badge, head, skin")
    b = p["backstory"]
    keys(b, ("prose", "facts"), "backstory", ("prose", "facts"))
    need(text(b["prose"]) and isinstance(b["facts"], list) and all(text(f) for f in b["facts"]),
         "backstory has prose and a list of facts")
    for i, s in enumerate(p.get("secrets") or []):
        w = "secrets[%d]" % i
        keys(s, ("id", "truth", "known_by", "slip", "hints"), w, ("id", "truth", "known_by", "slip"))
        need(text(s["id"]) and text(s["truth"]), "%s: id and truth are text" % w)
        need(isinstance(s["known_by"], list), "%s.known_by is a list of ids" % w)
        need(num(s["slip"], 0, 1), "%s.slip is 0..1" % w)
    for i, g in enumerate(p.get("groups") or []):
        w = "groups[%d]" % i
        keys(g, ("id", "role", "secret", "sign"), w, ("id", "role", "secret"))
        need(text(g["id"]) and text(g["role"]) and isinstance(g["secret"], bool), "%s: id, role, secret" % w)
    ag = p.get("agenda")
    if ag is not None:
        keys(ag, ("win_drive", "goals", "target", "prose"), "agenda", ("win_drive", "goals", "prose"))
        need(num(ag["win_drive"], 0, 1), "agenda.win_drive is 0..1")
        need(isinstance(ag["goals"], list) and all(text(g) for g in ag["goals"]), "agenda.goals is a list")
        need(ag.get("target") is None or text(ag["target"]), "agenda.target is an id or null")
    per = p["personality"]
    keys(per, ("traits", "prose"), "personality", ("traits", "prose"))
    need(set(per["traits"]) == set(TRAITS), "personality.traits has exactly %s" % ", ".join(TRAITS))
    need(all(num(v, 0, 1) for v in per["traits"].values()), "every trait is 0..1")
    need(text(per["prose"]), "personality.prose is text")
    t = p["temperament"]
    keys(t, ("baseline", "level", "leanings", "volatility", "recovery", "hot_buttons", "prose"), "temperament",
         ("baseline", "level", "leanings", "volatility", "recovery", "prose"))
    need(t["baseline"] in EMOTIONS and num(t["level"], 0, 1), "temperament.baseline is an emotion, level 0..1")
    need(isinstance(t["leanings"], dict) and all(e in EMOTIONS and num(v, 0.2, 3) for e, v in t["leanings"].items()),
         "temperament.leanings maps emotions to 0.2..3")
    need(num(t["volatility"], 0, 1) and num(t["recovery"], 0, 1), "temperament.volatility and recovery are 0..1")
    for i, h in enumerate(t.get("hot_buttons") or []):
        w = "temperament.hot_buttons[%d]" % i
        keys(h, ("situation", "feeling", "weight"), w, ("situation", "feeling", "weight"))
        need(h["situation"] in SITUATIONS and h["feeling"] in EMOTIONS and num(h["weight"], 0, 3),
             "%s: a situation, a feeling, a weight 0..3" % w)
    ex = p["expression"]
    keys(ex, ("expressiveness", "mask", "tells", "prose", "proclivity"), "expression", ("expressiveness", "mask", "tells", "prose"))
    if 'proclivity' in ex:
        need(isinstance(ex['proclivity'],dict) and set(ex['proclivity'])<=set(EMOTIONS) and all(num(v,0,1) for v in ex['proclivity'].values()), 'expression.proclivity accepts core-expression overrides; omitted values default to 0.7')
    need(num(ex["expressiveness"], 0, 1), "expression.expressiveness is 0..1")
    need(ex["mask"] is None or ex["mask"] in EMOTIONS, "expression.mask is an emotion or null")
    need(isinstance(ex["tells"], list), "expression.tells is a list")
    ids = set()
    for i, tl in enumerate(ex["tells"]):
        w = "expression.tells[%d]" % i
        keys(tl, ("id", "when", "leak", "face", "mark", "act", "says"), w, ("id", "when", "leak"))
        need(text(tl["id"]) and tl["id"] not in ids, "%s.id is text and unique" % w)
        ids.add(tl["id"])
        wh = tl["when"]
        keys(wh, ("feeling", "min", "situation"), w + ".when")
        need("feeling" in wh or "situation" in wh, "%s.when names a feeling or a situation" % w)
        need(wh.get("feeling") is None or wh["feeling"] in EMOTIONS, "%s.when.feeling is an emotion" % w)
        need(wh.get("situation") is None or wh["situation"] in SITUATIONS, "%s.when.situation is one of SITUATIONS" % w)
        need(wh.get("min") is None or num(wh["min"], 0, 1), "%s.when.min is 0..1" % w)
        need(num(tl["leak"], 0, 1), "%s.leak is 0..1" % w)
        need(tl.get("face") is None or tl["face"] in EMOTIONS, "%s.face is an emotion" % w)
        need(tl.get("mark") is None or tl["mark"] in MARKS, "%s.mark is one of faces.MARKS" % w)
        need(tl.get("act") is None or text(tl["act"]), "%s.act is text" % w)
        need(tl.get("says") is None or text(tl["says"]), "%s.says is text" % w)
        need(any(tl.get(k) for k in ("face", "mark", "act", "says")), "%s shows through face, mark, act or says" % w)
    need(text(ex["prose"], empty=True), "expression.prose is text")
    v = p["voice"]
    keys(v, ("style", "samples", "chattiness", "truthfulness", "advice", "tics"), "voice",
         ("style", "samples", "chattiness", "truthfulness"))
    need(text(v["style"]) and isinstance(v["samples"], list) and v["samples"] and all(text(s) for s in v["samples"]),
         "voice has a style and sample lines")
    need(num(v["chattiness"], 0, 1) and num(v["truthfulness"], 0, 1) and num(v.get("advice", 0), 0, 1),
         "voice.chattiness, truthfulness and advice are 0..1")
    need(all(text(s) for s in v.get("tics") or []), "voice.tics are text")
    for i, r in enumerate(p.get("relationships") or []):
        w = "relationships[%d]" % i
        keys(r, ("with", "kind", "feeling", "strength", "history", "knows"), w, ("with", "kind", "feeling", "strength", "history"))
        need(text(r["with"]) and r["with"] != p["id"], "%s.with is another character's id" % w)
        need(r["kind"] in REL_KINDS, "%s.kind is one of %s" % (w, ", ".join(REL_KINDS)))
        need(r["feeling"] is None or r["feeling"] in EMOTIONS, "%s.feeling is an emotion or null" % w)
        need(num(r["strength"], 0, 1) and text(r["history"]), "%s: strength 0..1 and a history" % w)
    ab = p["abilities"]
    need(isinstance(ab, dict) and set(ab) == set(abilities()), "abilities has exactly %s" % ", ".join(abilities()))
    need(all(num(x, 0, 100) for x in ab.values()), "every ability is 0..100")
    games = catalog()["games"]
    need(isinstance(p["games"], dict), "games is an object")
    for g, e in p["games"].items():
        w = "games.%s" % g
        need(g in games, "%s is not in games/catalog.json" % w)
        keys(e, ("skill", "elo", "style", "love", "preference", "notes"), w)
        need(not ('love' in e and 'preference' in e), w+': use preference, not both names')
        need('preference' not in e or num(e['preference'],-1,1),w+'.preference is -1..1')
        need(not ("skill" in e and "elo" in e), "%s: skill or elo, not both" % w)
        if "elo" in e:
            need(g == "chess" and isinstance(e["elo"], int) and ELO_MIN <= e["elo"] <= ELO_MAX,
                 "%s.elo is for chess, %d..%d" % (w, ELO_MIN, ELO_MAX))
        need("skill" not in e or num(e["skill"], 0, 100), "%s.skill is 0..100" % w)
        need("love" not in e or num(e["love"], -1, 1), "%s.love is -1..1" % w)
        need(all(text(e[k]) for k in ("style", "notes") if k in e), "%s: style and notes are text" % w)
    d = p.get("dnd")
    if d is not None:
        keys(d, ("player", "dm", "table"), "dnd", ("player", "dm", "table"))
        keys(d["player"], ("skill", "roleplay", "tactics", "rules", "class", "race", "style"), "dnd.player",
             ("skill", "roleplay", "tactics", "rules", "class", "style"))
        need(all(num(d["player"][k], 0, 100) for k in ("skill", "roleplay", "tactics", "rules")), "dnd.player numbers are 0..100")
        if d["dm"] is not None:
            keys(d["dm"], ("skill", "style"), "dnd.dm", ("skill", "style"))
            need(num(d["dm"]["skill"], 0, 100), "dnd.dm.skill is 0..100")
        need(text(d["table"]), "dnd.table says how they are at the table")
    con = p["consistency"]
    keys(con, ("blunder", "genius", "prose"), "consistency", ("blunder", "genius"))
    need(num(con["blunder"], 0, 1) and num(con["genius"], 0, 1), "consistency.blunder and genius are 0..1")
    for k in ("quirks", "likes", "dislikes"):
        need(k not in p or (isinstance(p[k], list) and all(text(x) for x in p[k])), "%s is a list of text" % k)
    pl = p.get("player")
    if pl is not None:
        # how they stand with THE PLAYER before anything has happened in a notebook: most residents
        # start as strangers (rapport 0); a profile may start elsewhere
        keys(pl, ("rapport", "prose"), "player", ("rapport", "prose"))
        need(num(pl["rapport"], -1, 1) and text(pl["prose"]), "player: rapport -1..1 and prose")
    ad = p.get("adapts")
    if ad is not None:
        # A LEVEL THAT FOLLOWS THE PLAYER'S at every game (a character that wins gets easier, and so on,
        # across all its stats); rm_residents.level/adapt keep it
        keys(ad, ("prose",), "adapts", ("prose",))
        need(text(ad["prose"]), "adapts.prose is text")
    if p.get("alters") is not None:
        _validate_alters(p, need, num, text, keys)
    return p


def check_roster(r=None):
    """The ties between profiles -> [problems]: every id named (relationships, secrets, agenda) is a
    character; every group is in groups.json; a bond both sides call a partnership, a marriage, a
    family or an ex agrees from both sides; a secret group's members all carry its secret."""
    r = roster() if r is None else r
    out = []
    gs = groups()
    for cid, p in sorted(r.items()):
        for rel in p.get("relationships") or []:
            if rel["with"] not in r:
                out.append("%s: relationship with unknown %r" % (cid, rel["with"]))
            elif rel["kind"] in ("partner", "ex", "family", "affair"):
                back = [x for x in r[rel["with"]].get("relationships") or [] if x["with"] == cid]
                if not back or back[0]["kind"] != rel["kind"]:
                    out.append("%s: %s with %s is not mirrored" % (cid, rel["kind"], rel["with"]))
        for s in p.get("secrets") or []:
            out += ["%s: secret %s known by unknown %r" % (cid, s["id"], k) for k in s["known_by"] if k not in r]
        tgt = (p.get("agenda") or {}).get("target")
        if tgt and tgt not in r:
            out.append("%s: agenda target unknown %r" % (cid, tgt))
        for aid, al in alters(cid).items():        # an alter's own ties and targets name real people too
            pr = al.get("profile") or {}
            out += ["%s as %s: relationship with unknown %r" % (cid, aid, rel["with"])
                    for rel in pr.get("relationships") or [] if rel["with"] not in r]
            atgt = (pr.get("agenda") or {}).get("target")
            if atgt and atgt not in r:
                out.append("%s as %s: agenda target unknown %r" % (cid, aid, atgt))
        for g in p.get("groups") or []:
            if g["id"] not in gs:
                out.append("%s: group unknown %r" % (cid, g["id"]))
            elif gs[g["id"]]["secret"] and not any(s["id"] == g["id"] for s in p.get("secrets") or []):
                out.append("%s: in the secret group %s but carries no secret of that id" % (cid, g["id"]))
    return out


def roster():
    """{id: profile}, reloaded when any profile file changes. Profiles only: the plan (cast.md), the
    catalog and groups.json are not characters.

    A PROFILE THAT DOES NOT VALIDATE IS LEFT OUT, not fatal: one bad or half-written file took every
    character off every game (a character vanished from a live game while the roster was being
    rewritten). roster_errors() says which, and the checks fail on them."""
    if rm_cast.AVAILABLE:
        if _CACHE['key']==('cast-pack',):return _CACHE['roster']
        out=rm_cast.roster()
        errors=[]
        for cid,p in out.items():
            try:validate_profile(p,cid)
            except ValueError as ex:errors.append(str(ex))
        if errors:raise CharacterError('Invalid installed cast: '+ '; '.join(errors))
        _CACHE.update(key=('cast-pack',),roster=out,errors=[])
        return out
    files = sorted(f for f in glob.glob(os.path.join(ROOT, "*.json")) if os.path.basename(f) not in ("groups.json", "cast.json"))
    key = tuple((f, os.path.getmtime(f)) for f in files)
    if key != _CACHE["key"]:
        out, errors = {}, []
        for f in files:
            try:
                with open(f, encoding="utf-8") as fh:
                    p = validate_profile(json.load(fh), os.path.basename(f))
            except (ValueError, OSError) as ex:
                errors.append("%s: %s" % (os.path.basename(f), ex))
                continue
            if p["id"] in out:
                errors.append("%s: a second profile with the id %r" % (os.path.basename(f), p["id"]))
                continue
            out[p["id"]] = p
        _CACHE.update(key=key, roster=out, errors=errors)
    return _CACHE["roster"]


def roster_errors():
    """The profiles roster() left out, and why."""
    roster()
    return list(_CACHE.get("errors") or [])


def get(cid):
    r = roster()
    if cid not in r:
        raise CharacterError("no character %r; have %s" % (cid, ", ".join(sorted(r))))
    return r[cid]


def _p(p):
    return get(p) if isinstance(p, str) else p


# ---------------------------------------------------------------- alters: one body, many people
# A character may be a system of several personalities (alters) in one body, each with its own goals,
# capacities, tells and even some face elements (eyebags, dimples) and chances of expressing. They
# share one memory file, but some alters have no awareness of what others have done, or do not care,
# and some are aware or present. When a game starts the alter that is out is chosen at random; each has
# a set chance to change and a set likelihood of changing to each other alter; some pretend they have
# not changed, some are trying to take over. The odds of change in general are low for most alters.
#
# A profile may carry
#   alters  {prose: how the system works (every alter's brief carries it),
#            start: {alter: weight} -- who is out when a game or a chat begins (seeded, rm_table),
#            list: [ALTER]}
#   ALTER   {id, name, role, self (who they feel they are), summary,
#            aware: {of: [alter ids] or ["*"], cares: bool, prose} -- whose memories they can reach
#                   (rm_residents), and whether they care what the others do,
#            switch: {chance: the chance a turn that they give way (low for most), chance_in?: {game:
#                     chance} (one alter may hold on through chess and let go of anything else), triggers?:
#                     {situation: added to chance, may be negative}, to: {alter: weight} -- who takes
#                     over from them, pull? (default 1): how hard THEY push to be out (the ones trying
#                     to take over), summoned?: {situation: added to pull}, draw?: {game: pull times},
#                     pretends?: the chance that, coming forward, they pass as the one they replaced,
#                     arrives?: what the table sees when they come forward (unless pretending)},
#            look?: {features: [face parts], face_add: [parts], face_drop: [part names], marks: [the
#                    habits the face always shows], hair, brows, eyes, body, anchors, mouth_fill},
#            profile?: the blocks that differ, over the character's own -- personality (traits merge),
#                      temperament, expression (their own tells), voice, agenda, abilities, games
#                      (their own chess), consistency, dnd, player, relationships (merge by `with`),
#                      backstory, secrets, quirks, likes, dislikes}
# profile(cid, front) is the character as that alter plays; each one is validated like any profile.
ALTER_OVERRIDES = ("backstory", "secrets", "agenda", "personality", "temperament", "expression", "voice",
                   "relationships", "abilities", "games", "dnd", "consistency", "quirks", "likes", "dislikes",
                   "player")
ALTER_LOOK = ("features", "face_add", "face_drop", "marks", "hair", "brows", "eyes", "body", "anchors",
              "mouth_fill")
_FRONTS = {}


def _validate_alters(p, need, num, text, keys):
    al = p["alters"]
    keys(al, ("prose", "start", "list"), "alters", ("prose", "start", "list"))
    need(text(al["prose"]), "alters.prose is text")
    lst = al["list"]
    need(isinstance(lst, list) and 2 <= len(lst) <= 24 and all(isinstance(a, dict) for a in lst),
         "alters.list holds 2 to 24 alters")
    ids = [a.get("id") for a in lst]
    need(len(set(ids)) == len(ids), "alters: every alter has its own id")
    games = catalog()["games"]
    for i, a in enumerate(lst):
        w = "alters.list[%d]" % i
        keys(a, ("id", "name", "role", "self", "summary", "aware", "switch", "look", "profile"), w,
             ("id", "name", "role", "self", "summary", "aware", "switch"))
        need(text(a["id"]) and a["id"] == a["id"].lower() and " " not in a["id"], "%s.id is lowercase, no spaces" % w)
        for k in ("name", "role", "self", "summary"):
            need(text(a[k]), "%s.%s is text" % (w, k))
        aw = a["aware"]
        keys(aw, ("of", "cares", "prose"), w + ".aware", ("of", "cares", "prose"))
        need(isinstance(aw["of"], list) and all(x == "*" or x in ids for x in aw["of"]),
             "%s.aware.of lists alter ids, or *" % w)
        need(isinstance(aw["cares"], bool) and text(aw["prose"]), "%s.aware: cares true or false, and prose" % w)
        sw = a["switch"]
        keys(sw, ("chance", "chance_in", "triggers", "to", "pull", "summoned", "draw", "pretends", "arrives"),
             w + ".switch", ("chance", "to"))
        need(num(sw["chance"], 0, 1), "%s.switch.chance is 0..1" % w)
        need(isinstance(sw["to"], dict) and sw["to"]
             and all(t in ids and t != a["id"] and num(v, 0, 10) for t, v in sw["to"].items()),
             "%s.switch.to maps other alters to weights 0..10" % w)
        need(all(g in games and num(v, 0, 1) for g, v in (sw.get("chance_in") or {}).items()),
             "%s.switch.chance_in maps catalog games to 0..1" % w)
        need(all(s in SITUATIONS and num(v, -1, 1) for s, v in (sw.get("triggers") or {}).items()),
             "%s.switch.triggers maps SITUATIONS to -1..1" % w)
        need(num(sw.get("pull", 1), 0, 5), "%s.switch.pull is 0..5" % w)
        need(all(s in SITUATIONS and num(v, 0, 5) for s, v in (sw.get("summoned") or {}).items()),
             "%s.switch.summoned maps SITUATIONS to 0..5" % w)
        need(all(g in games and num(v, 0, 5) for g, v in (sw.get("draw") or {}).items()),
             "%s.switch.draw maps catalog games to 0..5" % w)
        need(num(sw.get("pretends", 0), 0, 1), "%s.switch.pretends is 0..1" % w)
        need(sw.get("arrives") is None or text(sw["arrives"]), "%s.switch.arrives is text" % w)
        lk = a.get("look") or {}
        keys(lk, ALTER_LOOK, w + ".look")
        need(all(m in MARKS for m in lk.get("marks") or []), "%s.look.marks are faces.MARKS" % w)
        keys(a.get("profile") or {}, ALTER_OVERRIDES, w + ".profile")
    need(isinstance(al["start"], dict) and al["start"] and all(t in ids and num(v, 0, 10) for t, v in al["start"].items()),
         "alters.start maps alters to weights 0..10")
    for a in lst:                             # every alter, as it plays, is a sound profile
        validate_profile(_merge(p, a), "%s as %s" % (p.get("id"), a["id"]))


def _alter_look(base, over):
    import copy
    look = copy.deepcopy(base)
    if not over:
        return look
    drop = set(over.get("face_drop") or ())
    face = [x for x in look.get("face") or [] if x.get("part") not in drop]
    face += copy.deepcopy(over.get("face_add") or [])
    face += [{"part": f} for f in over.get("features") or []]
    look["face"] = face
    for k in ("hair", "brows", "eyes", "body", "mouth_fill"):
        if k in over:
            look[k] = copy.deepcopy(over[k])
    if over.get("anchors"):
        look["anchors"] = dict(look.get("anchors") or {}, **over["anchors"])
    if over.get("marks"):
        look["marks"] = list(over["marks"])
    return look


def _merge(p, al):
    """The character as one alter plays: their own blocks over the character's."""
    import copy
    m = copy.deepcopy({k: v for k, v in p.items() if k != "alters"})
    for k, v in (al.get("profile") or {}).items():
        v = copy.deepcopy(v)
        if k == "personality":
            per = dict(m["personality"])
            if "traits" in v:
                per["traits"] = dict(per["traits"], **v["traits"])
            if "prose" in v:
                per["prose"] = v["prose"]
            m[k] = per
        elif k in ("temperament", "voice", "agenda", "consistency", "backstory", "expression", "dnd", "player"):
            m[k] = dict(m.get(k) or {}, **v)
        elif k in ("abilities", "games"):
            m[k] = dict(m[k], **v)
        elif k == "relationships":
            ties = {r["with"]: r for r in m.get("relationships") or []}
            ties.update((r["with"], r) for r in v)
            m[k] = list(ties.values())
        else:
            m[k] = v
    m["look"] = _alter_look(m["look"], al.get("look"))
    return m


def alters(cid):
    """{alter id: alter} in the profile's order, or {} for a character without alters."""
    if rm_cast.members(cid):return rm_cast.members(cid)
    al = get(cid).get("alters")
    return {a["id"]: a for a in al["list"]} if al else {}


def profile(cid, front=None):
    """The character as they play now: the profile itself, or -- one with alters -- as `front` plays.
    Carries "front" (the alter's id) and "alter" (the alter) when there is one."""
    if front and rm_cast.members(cid):return get(rm_cast.identity(cid,front))
    p = get(cid)
    if not front or not p.get("alters"):
        return p
    key = (cid, front, _CACHE["key"])
    hit = _FRONTS.get(key)
    if hit is None:
        A = alters(cid)
        if front not in A:
            raise CharacterError("%s has no alter %r; has %s" % (cid, front, ", ".join(A)))
        hit = _merge(p, A[front])
        hit["front"], hit["alter"] = front, A[front]
        if len(_FRONTS) > 256:
            _FRONTS.clear()
        _FRONTS[key] = hit
    return hit


def aware_of(cid, front):
    """The alters whose doings `front` knows (their memories, their games) -- always itself."""
    A = alters(cid)
    if not A or front not in A:
        return set()
    of = A[front]["aware"]["of"]
    return set(A) if "*" in of else set(of) | {front}


# ---------------------------------------------------------------- how good at what
def derived(p, game):
    """0..100 at a game from the character's abilities and traits, weighted by the catalog. A game
    of pure luck has no weights: everyone is 50."""
    p = _p(p)
    w = catalog()["games"][game]["weights"]
    if not w:
        return 50.0
    tr, ab = p["personality"]["traits"], p["abilities"]
    total = sum(w.values())
    return round(sum(v * (ab[k] if k in ab else 100.0 * tr[k]) for k, v in w.items()) / total, 1)


def skill(p, game):
    """0..100 at a game: the profile's own number (chess: its Elo, mapped), else derived()."""
    p = _p(p)
    g = p["games"].get(game) or {}
    if game == "chess":
        return round(max(0,100.0 * (chess_elo(p) - ELO_MIN) / (ELO_MAX - ELO_MIN)), 1)
    return float(g["skill"]) if "skill" in g else derived(p, game)


def chess_elo(p):
    """A character's chess strength: their own Elo, else one read off their derived chess skill."""
    p = _p(p)
    g = p["games"].get("chess") or {}
    if "elo" in g:
        return int(g["elo"])
    if "skill" in g:
        s = float(g["skill"])
    else:
        s = derived(p, "chess")
    return int(round(ELO_MIN + (ELO_MAX - ELO_MIN) * s / 100.0))


def find(game=None, elo=None, skill_at=None, traits=None, n=3, exclude=()):
    """The best-matching characters, best first: [(score, id)]. Lower score is closer.

    game + elo (chess) or game + skill_at (0..100) ranks by how close their strength is; traits
    ({"aggression": .9, ...}) ranks by personality distance; both together add up."""
    out = []
    for cid, p in roster().items():
        if cid in exclude:
            continue
        s = 0.0
        if game and elo is not None and game == "chess":
            s += abs(chess_elo(p) - elo) / 280.0          # 280 Elo ~ one "step" of difference
        elif game and skill_at is not None:
            s += abs(skill(p, game) - skill_at) / 10.0
        if traits:
            tr = p["personality"]["traits"]
            s += sum((tr.get(k, .5) - float(v)) ** 2 for k, v in traits.items()) ** 0.5 * 5
        out.append((round(s, 3), cid))
    out.sort()
    return out[:n]


# ---------------------------------------------------------------- the brief
def _words(x, scale):
    return next(w for t, w in scale if x >= t)


def _system_lines(cid, front, shows=None):
    """For a character with alters: the system, who is out, what they know of the others."""
    base, A = get(cid), alters(cid)
    al = A[front]
    lines = ["%s is several people sharing one body, who take turns being out. %s" % (base["short"], base["alters"]["prose"]),
             "OUT RIGHT NOW: %s -- %s, %s. %s" % (al["name"], al["role"], al["self"], al["summary"])]
    if shows and shows != front and shows in A:
        lines.append("%s has just come forward and is PASSING AS %s, who was out before: keep up %s's manner, "
                     "answer to that name, and deny any change; %s's own habits may still show."
                     % (al["name"], A[shows]["name"], A[shows]["name"], al["name"]))
    known = [A[x] for x in A if x in aware_of(cid, front) and x != front]
    if known:
        lines.append("%s knows about: %s. %s" % (al["name"], "; ".join("%s (%s)" % (x["name"], x["role"]) for x in known),
                                               al["aware"]["prose"]))
    else:
        lines.append(al["aware"]["prose"])
    if not al["aware"]["cares"]:
        lines.append("%s does not care what the others do or want." % al["name"])
    lines.append("Speak and play as %s only. The memories you are given are the ones %s can reach; never "
                 "claim what %s cannot know." % (al["name"], al["name"], al["name"]))
    return lines


def brief(cid, game=None, table=(), front=None, shows=None):
    """The profile as the model is given it to play the character: who they are, what they carry,
    how they feel and show it, what they want, how they talk, and -- for the characters at THIS table
    only -- how they stand with them. `table` = the other characters present (ids). For a character
    with alters, `front` is who is out (the brief is theirs) and `shows` who they pass as."""
    p = profile(cid, front)
    tr = p["personality"]["traits"]
    lines = ["%s (%s, %s, %s) -- %s" % (p["name"], p["sex"], p["age"], p.get("species") or p["kind"], p["summary"])]
    if front and get(cid).get("alters"):
        lines += _system_lines(cid, front, shows)
    lines += ["Story: " + p["backstory"]["prose"],
              "Personality: " + p["personality"]["prose"],
              "Traits (0-1): " + ", ".join("%s %.2f" % (k, tr[k]) for k in TRAITS),
              "Temperament: " + p["temperament"]["prose"]]
    if p.get("player"):
        lines.append("With the player: " + p["player"]["prose"])
    if p.get("adapts"):
        lines.append("Your strength follows the player's: the game sets it (%s) Play naturally at the level "
                     "you are given; never mention it." % p["adapts"]["prose"].rstrip("."))
    v = p["voice"]
    talk = _words(v["chattiness"], ((0.7, "talks a lot"), (0.4, "talks now and then"), (0.15, "speaks rarely"),
                                    (0.0, "almost never speaks")))
    # Literal examples repeatedly became dialog (and even invented evidence) in local-model checks.
    # Keep them in the authoring profile, but brief the model on cadence rather than canned lines.
    lines.append("Voice: %s %s %s." % (v["style"], p["short"], talk))
    if v.get("tics"):
        lines.append("Verbal habits: " + "; ".join(v["tics"]))
    if v["truthfulness"] < 0.5:
        lines.append("They lie often (truthfulness %.2f): much of what they say is untrue, and they know it." % v["truthfulness"])
    if v.get("advice", 0) >= 0.3:
        lines.append("They cannot watch a bad move without saying the better one, even to an opponent.")
    ag = p.get("agenda")
    if ag:
        drive = _words(ag["win_drive"], ((0.8, "badly"), (0.5, "fairly"), (0.2, "a little"), (0.0, "barely")))
        tgt = ""
        if ag.get("target"):
            try:
                tgt = " It is about %s." % get(ag["target"])["name"]
            except CharacterError:
                tgt = " It is about %s." % ag["target"]
        lines.append("What they want: they care %s about winning. %s%s %s" % (drive, "; ".join(ag["goals"]), ".", ag["prose"] + tgt))
    lines.append("PRIVATE ROLE GUIDANCE: Play this person, not an exposition delivery system. "
                 "Separate public facts, private knowledge, suspicions, and mistaken beliefs. "
                 "Another character does not know a secret just because it is in this brief. "
                 "Do not invent evidence, memories, accusations, or a new twist to fill silence. "
                 "Without supplied move history, do not invent a move number, capture, trap, or result. "
                 "An unsupported guess from the player is not proof. Concrete evidence can change a "
                 "response; do not deny established facts or withhold forever to preserve a mystery. "
                 "Sample lines are cadence examples, never mandatory catchphrases. "
                 "Let trust, conflicting obligations, and the present conversation affect choices. "
                 "Most turns can concern the game alone. Physical cues are supplied by the engine; "
                 "never add a tell or explain what an observed action means.")
    for s in p.get("secrets") or []:
        lines.append("PRIVATE SECRET (not a random confession quota): " + s["truth"])
        if s.get("hints"):
            lines.append("Possible evidence, ONLY if already established in play or directly relevant: "
                         + "; ".join(s["hints"]) + ". Do not assert that these events happened this turn.")
    for g in p.get("groups") or []:
        if g["secret"]:
            lines.append("Secretly in %s (%s)%s." % (groups().get(g["id"], {}).get("name", g["id"]), g["role"],
                                                    ("; sign: " + g["sign"]) if g.get("sign") else ""))
    here = set(table or ())
    for rel in p.get("relationships") or []:
        if rel["with"] in here:
            try:
                who = get(rel["with"])["name"]
            except CharacterError:
                who = rel["with"]
            lines.append("At this table: %s (%s%s). %s%s" % (who, rel["kind"],
                         (", makes them %s" % rel["feeling"]) if rel["feeling"] else "", rel["history"],
                         (" They know: " + rel["knows"]) if rel.get("knows") else ""))
    if game:
        g = p["games"].get(game) or {}
        name = catalog()["games"].get(game, {}).get("name", game)
        lvl = ("about %d Elo" % chess_elo(p)) if game == "chess" else "skill %d/100" % round(skill(p, game))
        love = g.get("preference",g.get("love"))
        feel = "" if love is None else _words(love, ((0.6, " They love this game."), (0.2, " They like it."),
                                                     (-0.2, ""), (-0.6, " They don't care for it."),
                                                     (-1.1, " They hate it.")))
        lines.append("%s: %s. %s%s" % (name, lvl, g.get("style", ""), feel))
    con = p["consistency"]
    lines.append("Consistency: blunders %.0f%% of the time, finds a brilliant move %.0f%% of the time. %s"
                 % (con["blunder"] * 100, con["genius"] * 100, con.get("prose", "")))
    ex = expression(p)
    open_ = _words(ex["expressiveness"], ((0.9, "an open book"), (0.7, "expressive"), (0.45, "composed"),
                                          (0.25, "guarded"), (0.0, "hard to read")))
    lines.append("Face: %s. %s Always name the true feeling; the game decides what the table sees." % (open_, ex["prose"]))
    if p.get("quirks"):
        lines.append("Quirks: " + "; ".join(p["quirks"]))
    return "\n".join(l.strip() for l in lines)


# ---------------------------------------------------------------- feelings and faces
def expression(p):
    """A profile's expression block with the defaults filled in."""
    ex = _p(p).get("expression") or {}
    return {"expressiveness": float(ex.get("expressiveness", EXPRESSION_DEFAULT["expressiveness"])),
            "mask": ex.get("mask", EXPRESSION_DEFAULT["mask"]),
            "tells": list(ex.get("tells", EXPRESSION_DEFAULT["tells"])),
            "prose": ex.get("prose", "")}


def face_probability(who,feeling,intensity):
    p=_p(who);ex=expression(p)
    default=.7 if p.get('look',{}).get('portrait_language')=='cast-v2' else 1
    tendency=p.get('expression',{}).get('proclivity',{}).get(feeling,default)
    return min(1,ex['expressiveness']*(0.5+0.5*_level(intensity))*tendency)


def _level(intensity):
    return 0.5 if intensity is None else min(1.0, max(0.0, float(intensity)))


def _active(tell, feeling, intensity, situations):
    w = tell["when"]
    if w.get("feeling") and (w["feeling"] != feeling or _level(intensity) < float(w.get("min") or 0)):
        return False
    if w.get("situation") and w["situation"] not in situations:
        return False
    return True


def reveal(who, feeling, intensity, situations, rand):
    """What the table sees of a character this turn -> {"shows": emotion, "why": "felt" | "tell" | "mask",
    "marks": [...], "acts": [...], "says": [...], "fired": [tell ids]}.

    `feeling` is their true state (an emotion), `intensity` 0..1, `situations` what the game reports
    for them this turn (SITUATIONS), `rand` the game's seeded generator (no arguments, [0, 1)).

      1. the feeling reaches the face with probability expressiveness x (0.5 + 0.5 x intensity)
      2. every tell whose trigger holds leaks with its own probability; a fired tell adds its mark,
         act and words whatever the face does, and lends the face its emotion when the feeling did
         not show (the first such tell)
      3. otherwise the face is the mask (a poker face, a salesman's grin), or neutral

    Exactly one number is drawn for the face and one per tell, fired or not, so a game's draws stay
    in step whatever happens."""
    ex = expression(who)
    if feeling not in EMOTIONS:
        raise CharacterError("no emotion %r; have %s" % (feeling, ", ".join(EMOTIONS)))
    situations = set(situations or ())
    felt = rand() < face_probability(who,feeling,intensity)
    fired = [t for t in ex["tells"] if rand() < t["leak"] and _active(t, feeling, intensity, situations)]
    face = next((t["face"] for t in fired if t.get("face")), None)
    marks = []
    for t in fired:
        if t.get("mark") and t["mark"] not in marks and len(marks) < MAX_MARKS:
            marks.append(t["mark"])
    return {"shows": feeling if felt else (face or ex["mask"] or "neutral"),
            "why": "felt" if felt else ("tell" if face else "mask"),
            "marks": marks, "acts": list(dict.fromkeys(t["act"] for t in fired if t.get("act"))),
            "says": list(dict.fromkeys(t["says"] for t in fired if t.get("says"))), "fired": [t["id"] for t in fired]}


def shown(who, feeling, intensity, rand, situations=()):
    """reveal(), in the shape the first games used: {"shows", "why", "cue"} -- cue is the first act."""
    r = reveal(who, feeling, intensity, situations, rand)
    return {"shows": r["shows"], "why": r["why"], "cue": (r["acts"] or [""])[0], "marks": r["marks"],
            "acts": r["acts"], "says": r["says"]}


def odds(who, feeling, intensity, situations=()):
    """The chances behind reveal() for one feeling: {"felt", "tell", "mask"} (a tell = one that lends
    the face its emotion), summing to 1."""
    ex = expression(who)
    felt = face_probability(who,feeling,intensity)
    hidden = 1.0
    for t in ex["tells"]:
        if t.get("face") and _active(t, feeling, intensity, set(situations or ())):
            hidden *= 1.0 - t["leak"]
    return {"felt": felt, "tell": (1.0 - felt) * (1.0 - hidden), "mask": (1.0 - felt) * hidden}


# ---------------------------------------------------------------- faces
def look_of(cid, front=None):
    """The face a character wears: their look, or -- one with alters -- the look of `front`."""
    return profile(cid, front)["look"]


def face_svg(cid, emotion, marks=(), front=None):
    return faces.face_svg(look_of(cid, front), emotion, marks=tuple(marks))


def _frame(emotion, marks=()):
    return "+".join([emotion] + sorted(marks))


def _face_files(cid, emotion, marks=(), front=None):
    d = os.path.join(FACES, cid, front) if front else os.path.join(FACES, cid)
    f = _frame(emotion, marks)
    return os.path.join(d, f + ".svg"), os.path.join(d, f + ".png")


def _render(cid, emotion, marks=(), front=None):
    from paperdaemon.pipeline import charts as CH
    svg_path, png_path = _face_files(cid, emotion, marks, front)
    os.makedirs(os.path.dirname(svg_path), exist_ok=True)
    svg = face_svg(cid, emotion, marks, front)
    with open(svg_path, "w", encoding="utf-8") as f:
        f.write(svg)
    with open(png_path, "wb") as f:
        f.write(CH._vlc().svg_to_png(svg, scale=FACE_PX / 200.0))


def face_png(cid, emotion, marks=(), front=None):
    """The pre-rendered PNG for a face (with any marks; for a character with alters, `front`'s face),
    built on first use or when the profile or the face kit is newer."""
    if emotion not in EMOTIONS:
        raise CharacterError("no emotion %r; have %s" % (emotion, ", ".join(EMOTIONS)))
    bad = [m for m in marks if m not in MARKS]
    if bad:
        raise CharacterError("no mark %r; have %s" % (bad[0], ", ".join(MARKS)))
    if front and front not in alters(cid):
        front = None
    get(cid)
    _svg, png_path = _face_files(cid, emotion, marks, front)
    prof = os.path.join(ROOT, cid + ".json")
    kit = max(os.path.getmtime(f) for f in glob.glob(os.path.join(HERE, "faces", "*.py")))
    from paperdaemon.pipeline.games import cast as rm_cast
    if rm_cast.BUNDLE:
        # a pack's renderer modules and profiles live in the pack, not in games/characters:
        # include them in PNG cache invalidation
        authored=list(rm_cast.BUNDLE.glob('*.py'))
        prof=str(rm_cast.profile_path(cid) or prof)
        if authored:kit=max(kit,max(f.stat().st_mtime for f in authored))
    stale = (not os.path.exists(png_path)) or max(os.path.getmtime(prof) if os.path.exists(prof) else 0, kit) > os.path.getmtime(png_path)
    if stale:
        _render(cid, emotion, marks, front)
    return png_path


def face_url(cid, emotion, marks=(), front=None):
    with open(face_png(cid, emotion, marks, front), "rb") as f:
        return "data:image/png;base64," + base64.b64encode(f.read()).decode()


# ---------------------------------------------------------------- a character's page
# For the tablet (rm_pdfdoc): who someone is, one page each. The TELLS are for the player to work out,
# so the cast page holds what everyone knows -- faces, facts, games, public ties -- and spoilers=True
# the rest: secrets, agenda, temperament, every tell with the frame it shows.
PUBLIC_TIES = ("friend", "family", "partner", "ex", "rival", "enemy", "fear", "mentor", "student", "colleague",
               "boss", "creditor", "debtor", "contempt", "admires", "fan", "pet", "owner", "neighbor", "client",
               "wary", "protects")
SHEET_W, SHEET_H = 1404, 1872


def _font(name, size):
    from paperdaemon import paths
    return paths.pil_font(name, size)


def _wrap(d, text, font, width):
    out, line = [], ""
    for w in str(text).split():
        t = (line + " " + w).strip()
        if d.textlength(t, font=font) > width and line:
            out.append(line)
            line = w
        else:
            line = t
    if line:
        out.append(line)
    return out


def by_circle():
    """[(circle, [ids])] in the cast's order (the declared circles first, then any others by id), each
    circle's people by name."""
    r = roster()
    order = list(circles())
    order += sorted({p["circle"] for p in r.values()} - set(order))
    return [(c, sorted((cid for cid, p in r.items() if p["circle"] == c), key=lambda i: r[i]["name"]))
            for c in order if any(p["circle"] == c for p in r.values())]


INDEX_LINK = (SHEET_W - 190, 16, SHEET_W - 40, 60)     # every page's way back to the index (a link)


def _index_tag(d):
    x0, y0, x1, y1 = INDEX_LINK
    f = _font("reMarkableSans-Medium.ttf", 24)
    d.rounded_rectangle(INDEX_LINK, 14, outline=(150, 150, 156), width=2)
    d.text((x0 + (x1 - x0 - d.textlength("Index", font=f)) / 2, y0 + 8), "Index", font=f, fill=(80, 80, 86))


def cover_page(title=None, subtitle="the cast"):
    """Everyone at once: each circle a row of faces with names -- the first page of a cast book, at
    the largest face size that fits everyone (the title is cast_name() unless given). -> (PIL image,
    [(cid, box)]): where each face and its name sit, so the book can link them to their pages."""
    from PIL import Image, ImageDraw
    title = title or cast_name()
    from paperdaemon.pipeline.draw import scaled as SD
    im, d = SD.canvas(SHEET_W, SHEET_H)                # (laid out in the page's pixels; sent at twice the tablet's resolution)
    big, reg = _font("reMarkableSans-Bold.ttf", 64), _font("reMarkableSans-Medium.ttf", 30)
    d.text((64, 56), title, font=big, fill=(24, 24, 26))
    d.text((64, 136), subtitle, font=reg, fill=(95, 95, 100))
    groups, r = by_circle(), roster()
    for s in (118, 110, 104, 98, 92, 86, 80, 74):
        per = max(1, (SHEET_W - 128 + 9) // (s + 9))
        if 196 + sum(40 + -(-len(ids) // per) * (s + 26) + 14 for _c, ids in groups) <= SHEET_H - 20:
            break
    small = _font("reMarkableSans-Regular.ttf", 18 if s >= 98 else 16)
    y, boxes = 196, []
    for circle, ids in groups:
        d.text((64, y), circle_name(circle), font=reg, fill=(24, 24, 26))
        y += 40
        for i, cid in enumerate(ids):
            x = 64 + (i % per) * (s + 9)
            yy = y + (i // per) * (s + 26)
            with Image.open(face_png(cid, "neutral")) as f:
                SD.paste(im, f.convert("RGBA"), (x, yy), (s, s), mask=True)
            name = r[cid]["short"]
            d.text((x + (s - d.textlength(name, font=small)) / 2, yy + s + 2), name, font=small, fill=(60, 60, 64))
            boxes.append((cid, (x, yy, x + s, yy + s + 24)))
        y += -(-len(ids) // per) * (s + 26) + 14
    return im, boxes


def sheet_png(cid, out, spoilers=False, front=None):
    """One page for the tablet about a character -> the PNG path (sheet_image)."""
    sheet_image(cid, spoilers, front).save(out)
    return out


def _alter_lines(cid, front):
    """An alter's coming and going, and what they know, as plain lines for its page."""
    A, base = alters(cid), get(cid)
    al, sw = A[front], A[front]["switch"]
    start = base["alters"]["start"]
    total = float(sum(start.values())) or 1.0
    names = lambda ids: ", ".join(A[i]["name"] for i in ids if i in A)
    lines = ["Out when a game starts: %d%% of the time." % round(100 * start.get(front, 0) / total),
             "Gives way on %d%% of turns%s." % (round(100 * sw["chance"]), "".join(
                 "; %d%% in %s" % (round(100 * v), catalog()["games"][g]["name"]) for g, v in (sw.get("chance_in") or {}).items()))]
    if sw.get("triggers"):
        lines.append("More or less likely to go when: " + "; ".join("%s %+d%%" % (s.replace("_", " "), round(100 * v))
                                                                   for s, v in sw["triggers"].items()) + ".")
    tot = float(sum(sw["to"].values())) or 1.0
    lines.append("Makes way for: " + ", ".join("%s %d%%" % (A[t]["name"], round(100 * v / tot))
                                               for t, v in sorted(sw["to"].items(), key=lambda kv: -kv[1])) + ".")
    if float(sw.get("pull", 1)) != 1.0:
        lines.append("Pushes to be out: %.1f times as hard as most." % float(sw.get("pull", 1)))
    if sw.get("summoned"):
        lines.append("Called out by: " + ", ".join(s.replace("_", " ") for s in sw["summoned"]) + ".")
    if sw.get("draw"):
        lines.append("Drawn by: " + ", ".join(catalog()["games"][g]["name"] for g in sw["draw"]) + ".")
    if sw.get("pretends"):
        lines.append("Passes as the one they replaced %d%% of the time." % round(100 * sw["pretends"]))
    if sw.get("arrives"):
        lines.append("Coming forward, %s %s." % (al["name"], sw["arrives"].rstrip(".")))
    of = aware_of(cid, front) - {front}
    lines.append(("Knows about %s. " % names(of) if of else "Knows about no one else. ") + al["aware"]["prose"]
                 + ("" if al["aware"]["cares"] else " Does not care what the others do."))
    return lines


def sheet_image(cid, spoilers=False, front=None):
    """One page about a character, as a PIL image.

    The CAST page (spoilers=False) is what everyone knows: every face they make -- all eighteen, not
    just the neutral one -- the facts, their games, their public ties. The SPOILERS page holds the
    rest: story, secrets, wants, temperament, every tell with the frame it shows. `front` makes one
    ALTER's page for the spoilers book: their eighteen faces, how they come and go, what they know,
    their tells. Every page carries
    an Index tag at the top right, which the book links back to its first page."""
    from PIL import Image, ImageDraw
    base = get(cid)
    p = profile(cid, front)
    from paperdaemon.pipeline.draw import scaled as SD
    im, d = SD.canvas(SHEET_W, SHEET_H)                # (laid out in the page's pixels; sent at twice the tablet's resolution)
    ink, gray = (24, 24, 26), (95, 95, 100)
    M, W = 64, SHEET_W - 128
    reg, ital, med = (_font("reMarkableSans-Regular.ttf", 26), _font("reMarkableSans-RegularItalic.ttf", 26),
                      _font("reMarkableSans-Medium.ttf", 28))
    label = _font("reMarkableSans-Regular.ttf", 21)
    _index_tag(d)

    def face(emotion, box, marks=()):
        with Image.open(face_png(cid, emotion, marks, front)) as f:
            SD.paste(im, f.convert("RGBA"), (box[0], box[1]), (box[2], box[2]), mask=True)

    def para(text, y, font=reg, color=ink, width=W, x=M, gap=34):
        for line in _wrap(d, text, font, width):
            if y > SHEET_H - 50:
                break
            d.text((x, y), line, font=font, fill=color)
            y += gap
        return y

    def head(title, y):
        d.text((M, y), title, font=med, fill=ink)
        d.line((M, y + 38, M + W, y + 38), fill=(200, 200, 204), width=2)
        return y + 50

    def faces(y, s=168, per=6):
        """All eighteen faces, `per` to a row, each named."""
        for i, e in enumerate(EMOTIONS):
            fx, fy = M + (i % per) * (W // per) + (W // per - s) // 2, y + (i // per) * (s + 34)
            face(e, (fx, fy, s))
            d.text((fx + (s - d.textlength(e, font=label)) / 2, fy + s + 2), e, font=label, fill=gray)
        return y + -(-len(EMOTIONS) // per) * (s + 34) + 6

    face("neutral", (M, 56, 210))
    x = M + 236
    al = alters(cid).get(front) if front else None
    title = "%s: %s" % (base["short"], al["name"]) if al else p["name"]
    size = 50
    while size > 30 and d.textlength(title, font=_font("reMarkableSans-Bold.ttf", size)) > INDEX_LINK[0] - 20 - x:
        size -= 2
    d.text((x, 64), title, font=_font("reMarkableSans-Bold.ttf", size), fill=ink)
    meta = ("%s  ·  %s" % (al["role"], al["self"]) if al else
            "%s  ·  %s  ·  %s  ·  %s  ·  %s" % (p["short"], p["sex"], p["age"], p.get("species") or p["kind"],
                                               p["circle"].replace("-", " ")))
    y = para(meta, 128, reg, gray, W - 236, x)
    y = para(al["summary"] if al else p["summary"], y + 8, ital, ink, W - 236, x)
    y = max(y, 56 + 210) + 22
    if front:
        y = head("Faces", y)
        y = faces(y, 150)
        y = head("Coming and going", y)
        for line in _alter_lines(cid, front):
            y = para(line, y)
        ex = expression(p)
        y = head("Tells (face %d%% readable, resting face: %s)" % (round(100 * ex["expressiveness"]), ex["mask"] or "neutral"), y + 6)
        for t in ex["tells"]:
            w = t["when"]
            trig = " and ".join(v for v in (("feeling " + w["feeling"] + (" at %d/10+" % round(10 * w["min"]) if w.get("min") else ""))
                                             if w.get("feeling") else "", ("when " + w["situation"].replace("_", " ")) if w.get("situation") else "") if v)
            shows = "; ".join(v for v in (("face: " + t["face"]) if t.get("face") else "", ("mark: " + t["mark"]) if t.get("mark") else "",
                                          ("does: " + t["act"]) if t.get("act") else "", ("says: " + t["says"]) if t.get("says") else "") if v)
            y = para("%s (%d%%): %s" % (trig, round(100 * t["leak"]), shows), y)
        v, ag = p["voice"], p.get("agenda") or {}
        y = head("Plays", y + 6)
        y = para("Chess about %d Elo. Talks %d%% of turns at most; truthful %d%%. %s" % (
            chess_elo(p), round(100 * v["chattiness"]), round(100 * v["truthfulness"]), v["style"].split(". Sample")[0].rstrip(".") + "."), y)
        if ag:
            y = para("Wants: " + "; ".join(ag["goals"]) + ".", y)
        return im
    if not spoilers:
        y = head("Faces", y)
        y = faces(y)
        y = head("What everyone knows", y)
        for f in p["backstory"]["facts"]:
            y = para("• " + f, y)
        y += 8
        if y > SHEET_H - 200:
            return im
        y = head("Games", y)
        # their own games first (the ones the profile names), then where skill, not luck, makes them
        # stand out: a baccarat "skill" says nothing
        cat = catalog()["games"]
        own = sorted((g for g, e in p["games"].items() if e.get("preference",e.get("love", 0)) >= 0), key=lambda g: -skill(p, g))[:6]
        rest = sorted((g for g in cat if g not in own and cat[g]["luck"] <= 0.4),
                      key=lambda g: -(skill(p, g) - 50) * (1 - cat[g]["luck"]))
        ranked = (own + rest)[:8]
        col = W // 2
        for i, g in enumerate(ranked):
            gx, gy = M + (i % 2) * col, y + (i // 2) * 36
            if gy > SHEET_H - 50:
                break
            val = ("%d Elo" % chess_elo(p)) if g == "chess" else "%d" % round(skill(p, g))
            d.text((gx, gy), "%s  %s" % (catalog()["games"][g]["name"], val), font=reg, fill=ink)
        y += ((len(ranked) + 1) // 2) * 36 + 8
        if "chess" not in ranked:
            y = para("Chess: about %d Elo." % chess_elo(p), y, reg, gray)
        dn = p.get("dnd")
        if dn:
            y = para("D&D: plays a %s%s. %s" % ((dn["player"]["race"] + " ") if dn["player"].get("race") else "",
                                               dn["player"]["class"], dn["player"]["style"]), y, reg, gray)
        y += 8
        ties = [r for r in p.get("relationships") or [] if r["kind"] in PUBLIC_TIES]
        if ties and y < SHEET_H - 120:
            y = head("Ties", y)
            for r in ties:
                try:
                    who = get(r["with"])["name"]
                except CharacterError:
                    who = r["with"]
                if y > SHEET_H - 60:
                    break
                y = para("%s — %s" % (who, r["kind"]), y, reg, ink)
    else:
        # every face on this page too, smaller, so the tells below can be read against them
        y = head("Faces", y)
        y = faces(y, 118, per=9)
        if alters(cid):
            y = para("%d alters share this body; the next pages are theirs." % len(alters(cid)), y, ital, gray)
        y = head("The story", y)
        y = para(p["backstory"]["prose"], y)
        for s_ in p.get("secrets") or []:
            y = head("Secret", y + 6)
            y = para(s_["truth"], y)
        ag = p.get("agenda")
        if ag:
            y = head("What they want (cares about winning: %d%%)" % round(100 * ag["win_drive"]), y + 6)
            y = para("; ".join(ag["goals"]) + ". " + ag["prose"], y)
        y = head("Temperament", y + 6)
        y = para(p["temperament"]["prose"], y)
        v = p["voice"]
        y = para("Talks %d%% of turns at most; truthful %d%%%s." % (round(100 * v["chattiness"]), round(100 * v["truthfulness"]),
                 "; tells you your best move" if v.get("advice", 0) >= 0.3 else ""), y, reg, gray)
        ex = expression(p)
        y = head("Tells (face %d%% readable, resting face: %s)" % (round(100 * ex["expressiveness"]), ex["mask"] or "neutral"), y + 6)
        for t in ex["tells"]:
            if y > SHEET_H - 100:
                break
            face(t.get("face") or ex["mask"] or "neutral", (M, y, 84), [t["mark"]] if t.get("mark") else ())
            w = t["when"]
            trig = " and ".join(x for x in (("feeling " + w["feeling"] + (" at %d/10+" % round(10 * w["min"]) if w.get("min") else ""))
                                             if w.get("feeling") else "", ("when " + w["situation"].replace("_", " ")) if w.get("situation") else "") if x)
            shows = "; ".join(x for x in (("face: " + t["face"]) if t.get("face") else "", ("mark: " + t["mark"]) if t.get("mark") else "",
                                          ("does: " + t["act"]) if t.get("act") else "", ("says: " + t["says"]) if t.get("says") else "") if x)
            ty = para("%s (%d%%): %s" % (trig, round(100 * t["leak"]), shows), y + 6, reg, ink, W - 110, M + 104)
            y = max(ty, y + 90) + 6
        if ex["prose"] and y < SHEET_H - 80:
            y = para(ex["prose"], y, ital, gray)
    return im


def system_page(cid):
    """A character with alters, for the spoilers book: every alter's face with their name, role and
    chess -> (PIL image, [(alter id, box)]), the boxes for links to each alter's page."""
    from PIL import Image, ImageDraw
    base, A = get(cid), alters(cid)
    from paperdaemon.pipeline.draw import scaled as SD
    im, d = SD.canvas(SHEET_W, SHEET_H)                # (laid out in the page's pixels; sent at twice the tablet's resolution)
    ink, gray = (24, 24, 26), (95, 95, 100)
    _index_tag(d)
    d.text((64, 60), "%s: the system" % base["short"], font=_font("reMarkableSans-Bold.ttf", 50), fill=ink)
    d.text((64, 128), base["alters"]["prose"][:110] + ("..." if len(base["alters"]["prose"]) > 110 else ""),
           font=_font("reMarkableSans-RegularItalic.ttf", 22), fill=gray)
    per, s = 5, 190
    col = (SHEET_W - 128) // per
    name_f, small = _font("reMarkableSans-Medium.ttf", 22), _font("reMarkableSans-Regular.ttf", 18)
    boxes = []
    for i, (aid, al) in enumerate(A.items()):
        x = 64 + (i % per) * col + (col - s) // 2
        y = 190 + (i // per) * (s + 96)
        with Image.open(face_png(cid, "neutral", (), aid)) as f:
            SD.paste(im, f.convert("RGBA"), (x, y), (s, s), mask=True)
        cx = x + s / 2.0
        d.text((cx - d.textlength(al["name"], font=name_f) / 2, y + s + 4), al["name"], font=name_f, fill=ink)
        for j, line in enumerate(_wrap(d, "%s · chess %d" % (al["role"], chess_elo(profile(cid, aid))), small, col - 8)[:2]):
            d.text((cx - d.textlength(line, font=small) / 2, y + s + 32 + 22 * j), line, font=small, fill=gray)
        boxes.append((aid, (x, y, x + s, y + s + 76)))
    return im, boxes


def book(spoilers=False):
    """A cast book, page by page -> ([page() -> PIL image], {page index: [(box, target page)]}).
    Page 0 is the index: every face links to its character's page, and every
    other page's Index tag links back. The spoilers book gives a character with alters a page for the
    system (each face links to that alter's page) and a page per alter."""
    from functools import partial
    cover, boxes = cover_page(subtitle="spoilers" if spoilers else "the cast")
    pages, links, first = [lambda: cover], {}, {}
    for _circle, ids in by_circle():
        for cid in ids:
            first[cid] = len(pages)
            pages.append(partial(sheet_image, cid, spoilers))
            if spoilers and alters(cid):
                sys_im, sys_boxes = system_page(cid)
                sys_at = len(pages)
                pages.append(lambda im=sys_im: im)
                at = {}
                for aid in alters(cid):
                    at[aid] = len(pages)
                    pages.append(partial(sheet_image, cid, True, aid))
                links[sys_at] = [(box, at[aid]) for aid, box in sys_boxes]
    links[0] = [(box, first[cid]) for cid, box in boxes]
    for i in range(1, len(pages)):
        links.setdefault(i, []).append((INDEX_LINK, 0))
    return pages, links


def write_book(out_pdf, spoilers=False):
    """The cast book as a PDF with its links -> (path, page count)."""
    from paperdaemon.pipeline.page import pdf as PD
    pages, links = book(spoilers)
    PD.write_pdf((pg() for pg in pages), out_pdf, links=links)
    return out_pdf, len(pages)


# ---------------------------------------------------------------- dialog charts
def say(cid, emotion, text, marks=(), front=None):
    """A speaker's line; `front` = whose face it is, for a character with alters (who they pass as)."""
    line = {"speaker": cid, "emotion": emotion, "text": text}
    if marks:
        line["marks"] = list(marks)[:MAX_MARKS]
    if front:
        line["front"] = front
    return line


def emote(cid, emotion, marks=(), front=None):
    line = {"speaker": cid, "emotion": emotion}
    if marks:
        line["marks"] = list(marks)[:MAX_MARKS]
    if front:
        line["front"] = front
    return line


def narrate(text):
    return {"narrator": text}


def dialog(lines, page="strip", title=None):
    """A 'dialog' chart spec (rm_chart renders it): speakers with faces and bubbles, the narrator
    in plain text, emotes as a face alone, in the order given."""
    spec = {"type": "dialog", "version": 1, "page": page, "lines": list(lines)}
    if title:
        spec["title"] = title
    return spec
