"""Who sits at a game: the table of characters, their feelings and memories, and the town's residents.

The optional behavior pack is loaded by games.cast.
"""
import json
import os
import re
import time

from paperdaemon import paths
from paperdaemon.pipeline.games import cast as rm_cast
from paperdaemon.pipeline.games import characters as RC

# ==================================================================================================
# The table: who sits at a game, what each character feels, what the table sees of it, and who
# says anything this turn. Game-agnostic; a game's engine only reports SITUATIONS.
#
# The rules this keeps:
#   - feelings are a character's general state, not aimed at the player alone; characters can make
#     each other angry; some characters lean to certain feelings, some are stones
#   - tells are small and varied (a face, a subtle mark, an act, a slip in what they say), several per
#     character, and nothing explains them: the player learns what they mean
#   - characters may talk to each other, but each can say only one thing per turn, and often should
#     say nothing
#   - speech bubbles do not linger: every turn's strip holds that turn's lines only (rm_games)
#
# One turn for one character:
#
#     plan = pre_turn(state, cid, situations, rng)       # feelings move, who speaks, tells rolled
#     ... ask the model (it sees plan["prompt_lines"]: how they feel, whether to speak, any slip) ...
#     out = post_turn(state, cid, plan, feel, intensity, at, truth, extra_situations)
#     out["shows"], out["marks"], out["acts"], out["says_hint"], out["speak"]
#
# Everything lives in state["table"] (JSON, the notepad keeps it) and every number is drawn from the
# game's seeded generator, a fixed count per character per turn, so a replay sees the same table.
# ==================================================================================================

EMOTIONS = RC.EMOTIONS

# how each situation moves a feeling, before a character's own leanings and volatility
IMPULSE = {
    "winning": {"happy": .15, "smug": .15}, "losing": {"worried": .2, "sad": .1}, "close": {"thinking": .1},
    "turning": {"happy": .25, "surprised": .1, "smug": .1}, "slipping": {"worried": .3, "surprised": .15, "angry": .1},
    "scored": {"happy": .25, "smug": .15}, "hit": {"angry": .2, "sad": .15, "worried": .1},
    "blundered": {"worried": .35, "angry": .2, "confused": .15}, "their_blunder": {"surprised": .25, "happy": .2, "smug": .1},
    "danger": {"worried": .35, "determined": .15}, "attacking": {"determined": .25, "smug": .1},
    "trap": {"smug": .25, "thinking": .1}, "strong_hand": {"happy": .15, "smug": .15}, "weak_hand": {"worried": .15},
    "bluffing": {"worried": .1, "smug": .1}, "lying": {}, "lucky": {"happy": .2, "surprised": .1},
    "unlucky": {"angry": .15, "sad": .15}, "insulted": {"angry": .4}, "praised": {"happy": .3},
    "teased": {"angry": .2, "jealous": .1}, "target_near": {"thinking": .1}, "fear_near": {"worried": .3},
    "fellow_near": {}, "rival_near": {"jealous": .1, "determined": .1}, "start": {},
    "won": {"happy": .5, "relieved": .2}, "lost": {"sad": .4, "angry": .15}}
# how much a situation makes a character want to say something (0..1)
DRAMA = {
    "winning": .2, "losing": .3, "close": .05, "turning": .6, "slipping": .6, "scored": .5, "hit": .6,
    "blundered": .7, "their_blunder": .6, "danger": .5, "attacking": .3, "trap": .15, "strong_hand": .1,
    "weak_hand": .1, "bluffing": .3, "lying": .3, "lucky": .5, "unlucky": .5, "insulted": .9, "praised": .6,
    "teased": .7, "target_near": .1, "fear_near": .2, "fellow_near": .05, "rival_near": .3, "start": .6,
    "won": 1.0, "lost": .8, "addressed": 1.0}
FEELING_SITUATIONS = ("lying", "bluffing")      # known only once the model has spoken


def seat(state, npcs):
    """Sit these characters at the game (ids). Keeps what is already there."""
    t = state.setdefault("table", {})
    t.setdefault("seats", [])
    for cid in npcs:
        if cid not in t["seats"]:
            t["seats"].append(cid)
    t.setdefault("feel", {})
    t.setdefault("turn", 0)
    for cid in t["seats"]:
        if cid not in t["feel"]:
            tm = now(state, cid)["temperament"]
            t["feel"][cid] = {tm["baseline"]: round(float(tm["level"]), 3)} if tm["baseline"] != "neutral" else {}
    return t


# ------------------------------------------------------------------------------ who is out (alters)
def front(state, cid):
    """The front record of a character with alters at this table, or None: {id (who is out), shows
    (who they pass as), since, turn, switched (this turn), pretending, arrives, seen, log}."""
    if rm_cast.members(cid):return rm_cast.pack_front(state,cid)
    return ((state.get("table") or {}).get("fronts") or {}).get(cid)


def now(state, cid):
    """The profile to play this turn: the character's, or -- one with alters -- whoever is out."""
    fr = front(state, cid)
    p=RC.profile(cid, fr["id"]) if fr else RC.get(cid)
    return rm_cast.effective_profile(p,state)


def who(state, cid):
    """The name the character goes by this turn: an alter's own name when one is out."""
    fr = front(state, cid)
    return RC.profile(cid,fr['id'])['short'] if fr else RC.get(cid)["short"]


def _pick(weights, r):
    items = sorted(weights.items())
    x = r * sum(v for _, v in items)
    for k, v in items:
        x -= v
        if x < 0:
            return k
    return items[-1][0]


def _refeel(state, cid):
    """A new alter out brings their own feelings: the table starts them at that alter's baseline."""
    tm = now(state, cid)["temperament"]
    state["table"]["feel"][cid] = {tm["baseline"]: round(float(tm["level"]), 3)} if tm["baseline"] != "neutral" else {}


def recent(state, cid):
    """What happened to a character lately, for choosing who is out before this turn's situations are
    known (a chess engine's strength follows the alter out, so it is decided before the search): their
    last turn's situations and whatever the others did to them since."""
    t = state.get("table") or {}
    last = next((e for e in reversed(t.get("log") or []) if e.get("cid") == cid), None)
    return set((last or {}).get("situations") or ()) | set((t.get("pending") or {}).get(cid, []))


def front_turn(state, cid, rng, situations=(), game=None):
    """WHO IS OUT this turn, for a character with alters (rm_characters). Chosen at random when they sit
    down (alters.start); then once a turn the one out may give way: its own chance (its chance for this
    game, if it has one) raised or lowered by what is happening (triggers), to whoever its weights
    favor, each weighed by how hard they push to be out (pull), whether the moment summons them and
    whether this game draws them. One who comes forward may pass as the one it replaced (pretends).
    Idempotent within a table turn. One draw when they sit down, three every turn after, whatever
    happens, so a replay sees the same table. -> the front record, or None (no alters)."""
    if rm_cast.members(cid):
        rm_cast.prepare(state,cid,rng,situations)
        return rm_cast.pack_front(state,cid)
    A = RC.alters(cid)
    if not A:
        return None
    t = seat(state, [cid])
    fronts = t.setdefault("fronts", {})
    fr, turn = fronts.get(cid), t.get("turn", 0)
    if fr and fr.get("turn") == turn:
        return fr
    game = game or state.get("game")
    sits = set(situations or ())
    if not fr:
        # who sits down: the start weights, times how much this game draws each (one alter may favor chess)
        first = _pick({a: float(w) * float((A[a]["switch"].get("draw") or {}).get(game, 1.0))
                       for a, w in RC.get(cid)["alters"]["start"].items()}, rng.random())
        fronts[cid] = fr = {"id": first, "shows": first, "since": turn, "turn": turn, "switched": True,
                            "pretending": False, "arrives": "", "seen": [first], "log": [[turn, first, False]]}
        _refeel(state, cid)
        return fr
    r_leave, r_to, r_pretend = rng.random(), rng.random(), rng.random()
    sw = A[fr["id"]]["switch"]
    chance = float((sw.get("chance_in") or {}).get(game, sw["chance"]))
    chance += sum(float(v) for s, v in (sw.get("triggers") or {}).items() if s in sits)
    chance = max(0.0, min(0.95, chance))
    fr.update(turn=turn, switched=False, arrives="")
    if r_leave >= chance:
        return fr
    weights = {}
    for to, base in sw["to"].items():
        o = A[to]["switch"]
        pull = float(o.get("pull", 1.0)) + sum(float(v) for s, v in (o.get("summoned") or {}).items() if s in sits)
        pull *= float((o.get("draw") or {}).get(game, 1.0))
        if base * pull > 0:
            weights[to] = float(base) * pull
    if not weights:
        return fr
    new = _pick(weights, r_to)
    pretend = r_pretend < float(A[new]["switch"].get("pretends", 0))
    fr.update(id=new, shows=fr["shows"] if pretend else new, since=turn, switched=True, pretending=pretend,
              arrives="" if pretend else (A[new]["switch"].get("arrives") or ""))
    if new not in fr["seen"]:
        fr["seen"].append(new)
    fr["log"] = (fr.get("log") or [])[-40:] + [[turn, new, pretend]]
    _refeel(state, cid)
    return fr


def company(state, cid):
    """Situations that come from who else sits at the table: someone they fear, a rival, their
    agenda's target, a fellow member of a secret group."""
    t = state.get("table") or {}
    here = [c for c in t.get("seats", []) if c != cid]
    p = now(state, cid)
    out = set()
    for rel in p.get("relationships") or []:
        if rel["with"] in here:
            if rel["kind"] == "fear":
                out.add("fear_near")
            if rel["kind"] in ("rival", "enemy"):
                out.add("rival_near")
    if (p.get("agenda") or {}).get("target") in here:
        out.add("target_near")
    mine = {g["id"] for g in p.get("groups") or [] if g["secret"]}
    for other in here:
        if mine & {g["id"] for g in now(state, other).get("groups") or [] if g["secret"]}:
            out.add("fellow_near")
    return out


def _store(state, cid, lv):
    lv = {e: round(min(1.0, max(0.0, v)), 3) for e, v in lv.items() if v > 0.02}
    state["table"]["feel"][cid] = lv
    if not lv:
        return "neutral", 0.1
    e = max(sorted(lv), key=lambda k: lv[k])
    return e, lv[e]


def _move(state, cid, situations):
    """Once a turn: feelings fade toward the baseline by the character's recovery, then move with the
    situations (by their leanings and volatility) and their hot buttons. -> (feeling, intensity)"""
    tm = now(state, cid)["temperament"]
    lv = dict(state["table"]["feel"].get(cid) or {})
    base = {tm["baseline"]: float(tm["level"])} if tm["baseline"] != "neutral" else {}
    rec = float(tm["recovery"])
    for e in set(lv) | set(base):
        b = base.get(e, 0.0)
        lv[e] = b + (lv.get(e, 0.0) - b) * (1.0 - rec)
    vol = 0.5 + float(tm["volatility"])
    lean = tm.get("leanings") or {}
    for s in situations:
        for e, amt in IMPULSE.get(s, {}).items():
            lv[e] = lv.get(e, 0.0) + amt * vol * float(lean.get(e, 1.0))
    for hb in tm.get("hot_buttons") or []:
        if hb["situation"] in situations:
            lv[hb["feeling"]] = lv.get(hb["feeling"], 0.0) + 0.3 * float(hb["weight"]) * vol
    return _store(state, cid, lv)


def _nudge(state, cid, feel, intensity):
    """The feeling the model named for the character joins what they feel. -> (feeling, intensity)"""
    lv = dict(state["table"]["feel"].get(cid) or {})
    if feel in EMOTIONS:
        lean = now(state, cid)["temperament"].get("leanings") or {}
        lv[feel] = lv.get(feel, 0.0) + 0.5 * float(0.6 if intensity is None else intensity) * float(lean.get(feel, 1.0))
    return _store(state, cid, lv)


def pre_turn(state, cid, situations, rng, addressed=False, others_speaking=0, budget=1, interaction=None):
    """Before the model is asked: the feelings move with what the game reports, the character's
    company is added, the dice decide whether they speak at all this turn, and every tell is rolled
    (one draw each, fired or not). For a character with alters, who is out is settled first (front_turn:
    no draws if the game already settled it this turn), and everything after is theirs. -> the plan."""
    cid=rm_cast.prepare(state,cid,rng,situations)
    seat(state, [cid])
    # what others at the table did to this character since its last turn (post_turn's broadcast)
    waiting = (state["table"].get("pending") or {}).pop(cid, [])
    fr = front_turn(state, cid, rng, set(situations or ()) | set(waiting))
    p = now(state, cid)
    name = who(state, cid)
    sits = set(situations or ()) | company(state, cid) | set(waiting)
    feel, level = _move(state, cid, sits)
    drama = max([DRAMA.get(s, 0.0) for s in sits] + [DRAMA["addressed"] if addressed else 0.0] + [0.0])
    chat = float(p["voice"]["chattiness"])
    r_speak, r_face = rng.random(), rng.random()
    ex = RC.expression(p)
    rolls = [rng.random() for _ in ex["tells"]]
    want = chat * (0.2 + 0.8 * drama) if not addressed else min(1.0, chat + 0.5)
    speak = others_speaking < budget and r_speak < want
    armed = [t for t, r in zip(ex["tells"], rolls) if r < t["leak"]]
    slips = [t for t in armed if t.get("says")]
    lines = []
    if fr and fr["switched"] and fr["since"] > 0:
        lines.append("%s has just come forward this turn%s." % (name, (", passing as " + RC.alters(cid)[fr["shows"]]["name"])
                                                               if fr["pretending"] else ""))
    lines.append("How %s feels right now, truly: %s (%d/10)%s." % (name, feel, round(level * 10),
                 (" -- " + ", ".join(sorted(sits))) if sits else ""))
    if speak:
        lines.append("This turn %s says ONE short thing (to the player, or to someone at the table by name)." % name)
    else:
        lines.append("This turn %s stays silent: no SAY line." % name)
    for t in slips:
        cond = t["when"].get("situation") or t["when"].get("feeling")
        lines.append("If %s is %s this turn, it slips out in what they say: %s." % (name, cond, t["says"]))
    return rm_cast.before(state,cid,{"cid": cid, "situations": sorted(sits), "feel": feel, "level": level, "speak": speak,
            "r_face": r_face, "armed": [t["id"] for t in armed], "prompt_lines": lines, "drama": round(drama, 2),
            "front": dict(fr) if fr else None, "interaction": interaction or ('conversation' if state.get('game')=='messages' else 'gameplay')})


def post_turn(state, cid, plan, feel=None, intensity=None, at="", truth="", extra=(), speech="", presentation=None):
    """After the model answered: its named feeling joins the state, what it said adds `lying` or
    `bluffing`, and the rolled tells whose triggers hold now fire. -> {feeling, intensity, at, shows,
    why, marks, acts, says_hint, fired}; for a character with alters also front (who is out), look (whose
    face the table sees: who they pass as) and arrives (what the table saw them come forward as, this
    turn only)"""
    cid=plan.get('cid',cid)
    p = now(state, cid)
    ex = RC.expression(p)
    sits = set(plan["situations"]) | set(extra or ())
    if truth in ("lie", "lying"):
        sits.add("lying")
    if truth in ("bluff", "bluffing"):
        sits.add("bluffing")
    f, k = _nudge(state, cid, feel, intensity)
    felt = plan["r_face"] < RC.face_probability(p,f,k)
    fired = [t for t in ex["tells"] if t["id"] in plan["armed"] and RC._active(t, f, k, sits)]
    face = next((t["face"] for t in fired if t.get("face")), None)
    marks = []
    for t in fired:
        if t.get("mark") and t["mark"] not in marks and len(marks) < RC.MAX_MARKS:
            marks.append(t["mark"])
    shows = f if felt else (face or ex["mask"] or "neutral")
    out = {"feeling": f, "intensity": round(k, 2), "at": at or "", "shows": shows,
           "why": "felt" if felt else ("tell" if face else "mask"), "marks": marks,
           "acts": list(dict.fromkeys(t["act"] for t in fired if t.get("act"))),
           "says_hint": list(dict.fromkeys(t["says"] for t in fired if t.get("says"))),
           "fired": [t["id"] for t in fired], "situations": sorted(sits),
           "speech": speech or "", "player_id": None}     # a cast pack may rewrite these (rm_cast.after)
    fr = front(state, cid)
    if fr:
        out.update(front=fr["id"], look=fr["shows"],
                   arrives=fr["arrives"] if fr["switched"] and fr["turn"] == state["table"].get("turn", 0) else "")
    out=rm_cast.after(state,cid,plan,out,truth,speech,presentation)
    t = state["table"]
    t.setdefault("log", [])
    t["log"] = (t["log"] + [dict(out, cid=cid, turn=t.get("turn", 0))])[-80:]
    _broadcast(state, cid, sits)
    return out


def _broadcast(state, cid, sits):
    """What this character's turn does to the OTHERS at the table, for their next turn: a lie told is a
    lie heard by everyone else (who may or may not catch it); a character hurt or in danger is felt by
    anyone who protects them."""
    t = state["table"]
    pend = t.setdefault("pending", {})
    for other in t.get("seats", []):
        if other == cid:
            continue
        add = set()
        if "lying" in sits:
            add.add("lie_heard")
        if sits & {"hit", "danger"}:
            try:
                if any(r["with"] == cid and r["kind"] == "protects" for r in now(state, other).get("relationships") or []):
                    add.add("ward_hurt")
            except RC.CharacterError:
                pass
        if add:
            pend[other] = sorted(set(pend.get(other, [])) | add)


def next_turn(state):
    t = state.setdefault("table", {})
    t["turn"] = int(t.get("turn", 0)) + 1
    return t["turn"]


# ==================================================================================================
# What the residents of the town remember -- per notebook, per resident. Every resident has a memory in
# each notebook, and it updates with what the player says and the games they play; because a resident
# remembers everything within a notebook, a memory can be cross-referenced from anywhere in it.
#
# Every notebook has its own town: in one notebook alice has played you at chess and texted you
# twice; in another she has never heard of you. What a resident remembers there:
#   - what you said to them, and what they said back (chats, remarks across a board)
#   - chats they were part of, including what the others said there
#   - the games they played with you: every game in the notebook is read live (rm_chess.games), so a
#     game on page 1 is there when you text them on page 7
#   - what they chose to remember (the model's REMEMBER line after an exchange)
#   - what they heard from someone else
#
# Kept in rm-notepad\<doc>\residents\<id>.json, one file per resident who has met you in that notebook:
#
#     {"id": "alice", "doc": "...", "met": 1790000000, "rapport": 0.1,
#      "memories": [{"at": 1790000000, "page": "<page id>", "kind": "said|heard|chat|game|fact|feeling",
#                    "text": "...", "with": ["bob"], "weight": 0.5}]}
#
# recall(doc, cid, query) is the cross-reference: the resident's own memories that bear on what is being
# said now (the words and the people it names, how recent, how much it mattered), the games they are
# playing or played here, and what they heard -- a short block of lines for the model's prompt.
#
# ONE FILE, MANY PEOPLE: a resident with alters (rm_characters) keeps one memory file, and every memory
# says which alter was out when it was made. An alter reaches only the memories of the alters it is
# aware of (aware.of: itself always), and the games they played; it has met you only if one of them has;
# each alter has its own rapport with you. So the one who played you at chess last night may be the one
# who texts back today -- or someone who has never heard of the game.
# ==================================================================================================

HERE = os.path.dirname(os.path.abspath(__file__))
KINDS = ("said", "heard", "chat", "game", "fact", "feeling")
MAX_MEMORIES = 400                 # per resident per notebook; the least worth keeping goes first
STOP = set("""a an the and or but if then so to of in on at for with by from up down out over into is are was
were be been being i you he she it we they me him her us them my your his its our their this that these those
what which who whom whose when where why how all any both each few more most other some such no nor not only
own same than too very can will just don should now do does did have has had i'm you're it's that's there
here about as ok okay yeah yes hey hi hello lol""".split())


def notepad_dir():
    from paperdaemon.pipeline.games import chess as CH
    return CH.NOTEPAD_DIR


def _file(doc, cid):
    return rm_cast.memory_file(notepad_dir(),doc,cid)


def _start_rapport(cid, alter=None):
    """How a resident stands with the player before anything happens: 0 (a stranger), or what the
    profile's player block says."""
    try:
        from paperdaemon.pipeline.games import characters as RC
        return float((RC.profile(cid, alter).get("player") or {}).get("rapport", 0.0))
    except Exception:
        return 0.0


def load(doc, cid):
    """A resident's memory in this notebook (a fresh one if they have never met you here)."""
    try:
        with open(_file(doc, cid), encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        old=rm_cast.legacy_memory(notepad_dir(),doc,cid)
        if old is not None:return old
        return {"id": cid, "doc": doc, "met": None, "rapport": _start_rapport(cid), "memories": []}


def _reach(cid, alter):
    """The alters whose memories `alter` can reach, or None (a resident without alters: all of them)."""
    if not alter:
        return None
    from paperdaemon.pipeline.games import characters as RC
    return RC.aware_of(cid, alter) or None


def save(m):
    path = _file(m["doc"], m["id"])
    tmp = path + ".%d.tmp" % os.getpid()
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(m, f, ensure_ascii=False, indent=1)
    os.replace(tmp, path)


def remember(doc, cid, text, kind="fact", page=None, with_=(), weight=0.5, when=None, alter=None):
    """Add one memory for a resident in this notebook (`alter`: who was out, for a resident with
    alters). -> the memory."""
    cid=rm_cast.identity(cid,alter);alter=None
    text = " ".join(str(text or "").split())[:400]
    if not text:
        return None
    m = load(doc, cid)
    now = int(when or time.time())
    m["met"] = m.get("met") or now
    if alter:
        m.setdefault("met_by", {}).setdefault(alter, now)
    mem = {"at": now, "page": page, "kind": kind if kind in KINDS else "fact", "text": text,
           "with": sorted(set(w for w in with_ if w and w != cid)), "weight": round(max(0.0, min(1.0, float(weight))), 2)}
    if alter:
        mem["alter"] = alter
    m["memories"].append(mem)
    if len(m["memories"]) > MAX_MEMORIES:
        # keep what mattered and what is recent: drop the least weight among the oldest half
        old = m["memories"][: len(m["memories"]) // 2]
        drop = min(range(len(old)), key=lambda i: (old[i]["weight"], old[i]["at"]))
        m["memories"].pop(drop)
    save(m)
    return mem


def rapport(doc, cid, alter=None, m=None):
    """-1..1: how they feel about you in this notebook (an alter's own, for a resident with alters)."""
    cid=rm_cast.identity(cid,alter);alter=None
    m = m or load(doc, cid)
    if alter:
        by = m.get("rapport_by") or {}
        return float(by[alter]) if alter in by else _start_rapport(cid, alter)
    return float(m.get("rapport") or 0)


def level(doc, cid, game, base):
    """A resident's level at a game in this notebook -- Elo for chess, 0..100 for anything else. Only a
    resident whose profile ADAPTS has one of its own; for everyone else, and before their first
    game here, it is `base`."""
    lv = ((load(doc, cid).get("levels") or {}).get(game)) or {}
    return lv.get("value", base)


def adapt(doc, cid, game, base, result):
    """After a game with the player, an adapting resident's level moves toward the player's: they won ->
    a step easier, they lost -> a step harder, a draw -> as it was. The steps start large and shrink with
    the games played here (160 Elo down to 40; 12 points down to 3), so the resident finds the player's
    level and then keeps the games close. -> the new level."""
    import math
    from paperdaemon.pipeline.games import characters as RC
    m = load(doc, cid)
    levels = m.setdefault("levels", {})
    lv = levels.get(game) or {"value": base, "games": 0}
    n = int(lv.get("games") or 0)
    if game == "chess":
        step, lo, hi = max(40.0, 160.0 / math.sqrt(1 + n)), RC.ELO_MIN, RC.ELO_MAX
    else:
        step, lo, hi = max(3.0, 12.0 / math.sqrt(1 + n)), 0, 100
    v = float(lv.get("value", base)) + {"won": -step, "lost": step}.get(result, 0.0)
    levels[game] = {"value": int(round(max(lo, min(hi, v)))), "games": n + 1, "last": result}
    save(m)
    return levels[game]["value"]


def warm(doc, cid, by, alter=None):
    """Rapport with the player, -1..1: how they feel about you in this notebook, moved a little by each
    exchange (the model's FEEL toward you, a game's result); an alter's own when `alter` is given."""
    cid=rm_cast.identity(cid,alter);alter=None
    m = load(doc, cid)
    r = round(max(-1.0, min(1.0, rapport(doc, cid, alter, m) + float(by))), 3)
    if alter:
        m.setdefault("rapport_by", {})[alter] = r
    else:
        m["rapport"] = r
    save(m)
    return r


def residents(doc):
    """Every resident with a memory in this notebook."""
    d = os.path.join(notepad_dir(), doc, "residents", "players")
    try:
        return sorted(f[:-5] for f in os.listdir(d) if f.endswith(".json"))
    except OSError:
        return []


def _words(text):
    return {w for w in re.findall(r"[a-z0-9']+", str(text).lower()) if len(w) > 2 and w not in STOP}


def _names():
    """{word: id} for every resident's names, so a message that names someone finds memories of them."""
    from paperdaemon.pipeline.games import characters as RC
    out = {}
    for cid, p in RC.roster().items():
        for n in {p["short"], p["name"], cid.split("-")[0]}:
            for w in re.findall(r"[A-Za-z']+", n):
                if len(w) > 2:
                    out.setdefault(w.lower(), cid)
    return out


def _games_with(doc, cid, alter=None):
    """Lines about the games in this notebook this resident played with you, read from the games
    themselves (so the one on page 1 is always current) -- for an alter, only the games one of the
    alters it knows was out for."""
    from paperdaemon.pipeline.games import chess as CH
    reach = _reach(cid, alter)
    out = []
    for g in CH.games(doc):
        if g.get("game") == "chess" and (g.get("persona") or {}).get("character") == cid:
            seen = set((((g.get("table") or {}).get("fronts") or {}).get(cid) or {}).get("seen") or ())
            if reach is not None and seen and not (seen & reach):
                continue
            n = len(g.get("history") or [])
            me = "Black" if g["colors"]["user"] == "w" else "White"
            if g["status"] == "playing":
                last = CH.movetext(g, last=4) or "no moves yet"
                out.append("We are playing chess in this notebook (I am %s): %d moves so far, lately %s." % (me, n, last))
            else:
                won = (g["result"] == "1-0") == (me == "White") and g["result"] != "1/2-1/2"
                out.append("We played chess in this notebook (I was %s): %s after %d moves (%s)." % (
                    me, "I won" if won else ("a draw" if g["result"] == "1/2-1/2" else "you won"), n, g["status"].replace("_", " ")))
    return out


def recall(doc, cid, query="", k=12, with_=(), alter=None):
    """THE CROSS-REFERENCE: what this resident remembers that bears on `query`, as lines for a prompt.

    Scored by the words the query shares with a memory, the people it names (a memory about Bob when
    Bob is mentioned), who is in the conversation now (`with_`), how recent it is, and how much it
    mattered; the games they play with you here come first, read live; the newest few always come in
    so the thread of the conversation holds. For a resident with alters, `alter` (who is out) reaches
    only what the alters it knows lived through."""
    cid=rm_cast.identity(cid,alter);alter=None
    m = load(doc, cid)
    reach = _reach(cid, alter)
    mems = [x for x in m["memories"] if reach is None or not x.get("alter") or x["alter"] in reach]
    lines = [] if rm_cast.members(cid) else _games_with(doc, cid, alter)
    lines += rm_cast.borrowed(notepad_dir(),doc,cid,load,query,min(k,8))
    if not mems:
        return lines
    q = _words(query)
    names = _names()
    named = {names[w] for w in q if w in names} | set(with_)
    now = time.time()
    scored = []
    for i, x in enumerate(mems):
        s = x["weight"]
        s += 0.6 * len(q & _words(x["text"]))
        s += 0.8 * len(named & set(x.get("with") or [])) + 0.5 * sum(1 for n in named if n.split("-")[0] in x["text"].lower())
        age_days = (now - x["at"]) / 86400.0
        s += 0.5 / (1.0 + age_days)
        scored.append((s, i))
    keep = set(i for _s, i in sorted(scored, reverse=True)[:k])
    keep |= set(range(max(0, len(mems) - 4), len(mems)))          # the latest, whatever they are
    for i in sorted(keep):
        x = mems[i]
        day = time.strftime("%b %d", time.localtime(x["at"]))
        lines.append("(%s, %s) %s" % (day, x["kind"], x["text"]))
    return lines


def about_player(doc, cid, alter=None):
    """One line: whether they know you here, since when, and how they feel about you (for a resident
    with alters: whether the alters `alter` knows have met you, and `alter`'s own feeling)."""
    cid=rm_cast.identity(cid,alter);alter=None
    m = load(doc, cid)
    r = rapport(doc, cid, alter, m)
    feel = next(w for t, w in ((0.6, "you like them a lot"), (0.25, "you like them"), (-0.25, "you're neutral about them"),
                               (-0.6, "you're wary of them"), (-1.1, "you dislike them")) if r >= t)
    reach = _reach(cid, alter)
    met = m.get("met")
    if reach is not None:
        met = min([t for a, t in (m.get("met_by") or {}).items() if a in reach] or [None], key=lambda t: t or 0)
    if not met:
        return "You have never met the player in this notebook: they are new to you%s." % (
            "" if abs(r) < 0.25 else "; even so, " + feel)
    return "You have known the player here since %s; %s." % (time.strftime("%B %d", time.localtime(met)), feel)
