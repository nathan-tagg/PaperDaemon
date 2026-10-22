r"""Ink Adventure: a text adventure on the tablet, game-mastered by the model.

  PAGE 1   the hero's character sheet, D&D style: abilities, saves, skills, hit points, armor, the
           inventory, features -- drawn again whenever it changes
  PAGE 2   THE SCENE, drawn again IN PLACE every turn: a square picture of what the hero sees (rendered by
           the picture model, converted to strokes and laid over the page's frame), what happened, what is
           around, a few loose options, and a space at the bottom to write what you do
  PAGE 3   THE LOG: one entry per turn, the newest at the bottom; when the page is full the oldest entries
           leave the page (they stay in the game's state in the notepad)
The page count never grows. A game saved with an older page layout keeps its pages, plays on in place on
its current page, and gets its log page once.

THE CAST (a person must look the same in every picture and every telling): every named person the story
meets is an entry the ENGINE keeps -- race, role, class and level, rolled abilities, hit points, armor class, alignment,
looks (height, build, hair, eyes, skin, face, marks, clothing), equipment, status, disposition, conditions,
criminal record, backstory, a secret, where they were met and last seen, and a portrait painted once when they
first appear. The model proposes a person ONCE; the looks never change after that, and every other change
(status, hit points, equipment, record) goes through the engine. Every prompt carries the cast and the recent
events; every picture with a known person in it carries that person's fixed looks, written by the engine.
Pictures are first person, the frame written by the engine for new pictures and edits alike.

Whatever the picture shows is FAIR GAME: "I take the knife off the table" works when the knife is in
the picture, and the model looks at the picture itself (vision) before it counts. The picture of each
scene is kept beside the notepad before it is converted, so the next turn in the same place EDITS it
(the knife gone from the table) instead of drawing a new one (rm_host._edit_png).

The model is the GAME MASTER: it rules what an action takes (which check, how hard) and tells the story.
The ENGINE holds everything else: the state, every die (seeded, rm_chess.Rng), every change checked (an
item taken has to have been there; hit points stay in bounds), all of it kept in the notepad. This file
is the engine and the pages; rm_games runs a turn; rm_host supplies the model and the painter.

The rules are a small, faithful subset of the 5th edition System Reference Document (SRD 5.1, CC-BY-4.0):
the six abilities, eighteen skills, twelve classes at level 1, the common races, starting kits.
"""
from paperdaemon import paths
import json
import os
import re
import time
from paperdaemon.pipeline.games import chess as CH
from paperdaemon.pipeline.page import tablets as TB

HERE = os.path.dirname(os.path.abspath(__file__))
PAGE_W, PAGE_H = 1620, 2160      # its pages are designed at a Paper Pro page (tablets.picture_page fits them)

ABILITIES = ("STR", "DEX", "CON", "INT", "WIS", "CHA")
ABILITY_NAMES = {"STR": "Strength", "DEX": "Dexterity", "CON": "Constitution", "INT": "Intelligence",
                 "WIS": "Wisdom", "CHA": "Charisma"}
SKILLS = {"acrobatics": "DEX", "animal handling": "WIS", "arcana": "INT", "athletics": "STR",
          "deception": "CHA", "history": "INT", "insight": "WIS", "intimidation": "CHA",
          "investigation": "INT", "medicine": "WIS", "nature": "INT", "perception": "WIS",
          "performance": "CHA", "persuasion": "CHA", "religion": "INT", "sleight of hand": "DEX",
          "stealth": "DEX", "survival": "WIS"}
# class -> hit die, the order the rolled scores go into, saving throws, how many skills and from what,
# armor (name, base AC, dexterity counted: None | "full" | "max2"), shield, weapon (name, die, ability),
# kit, gold, spells (names only), features
CLASSES = {
    "barbarian": dict(die=12, order=("STR", "CON", "DEX", "WIS", "CHA", "INT"), saves=("STR", "CON"), n=2,
                      skills=("animal handling", "athletics", "intimidation", "nature", "perception", "survival"),
                      armor=("unarmored (10 + DEX + CON)", 10, "unarmored"), shield=False, weapon=("greataxe", "1d12", "STR"),
                      kit=["greataxe", "two handaxes", "explorer's pack", "four javelins"], gold=10, spells=[],
                      features=["Rage (2 a day)", "Unarmored Defense"]),
    "bard": dict(die=8, order=("CHA", "DEX", "CON", "WIS", "INT", "STR"), saves=("DEX", "CHA"), n=3, skills=tuple(SKILLS),
                 armor=("leather armor", 11, "full"), shield=False, weapon=("rapier", "1d8", "DEX"),
                 kit=["rapier", "lute", "leather armor", "dagger", "entertainer's pack"], gold=15,
                 spells=["vicious mockery", "minor illusion", "healing word", "charm person", "sleep"],
                 features=["Bardic Inspiration (d6)", "Spellcasting"]),
    "cleric": dict(die=8, order=("WIS", "CON", "STR", "CHA", "INT", "DEX"), saves=("WIS", "CHA"), n=2,
                   skills=("history", "insight", "medicine", "persuasion", "religion"),
                   armor=("scale mail", 14, "max2"), shield=True, weapon=("mace", "1d6", "STR"),
                   kit=["mace", "scale mail", "shield", "holy symbol", "priest's pack"], gold=15,
                   spells=["sacred flame", "guidance", "cure wounds", "bless", "guiding bolt"],
                   features=["Spellcasting", "Divine Domain"]),
    "druid": dict(die=8, order=("WIS", "CON", "DEX", "INT", "CHA", "STR"), saves=("INT", "WIS"), n=2,
                  skills=("arcana", "animal handling", "insight", "medicine", "nature", "perception", "religion", "survival"),
                  armor=("leather armor", 11, "full"), shield=True, weapon=("scimitar", "1d6", "DEX"),
                  kit=["scimitar", "wooden shield", "leather armor", "druidic focus", "explorer's pack"], gold=10,
                  spells=["druidcraft", "produce flame", "entangle", "healing word", "speak with animals"],
                  features=["Druidic", "Spellcasting"]),
    "fighter": dict(die=10, order=("STR", "CON", "DEX", "WIS", "CHA", "INT"), saves=("STR", "CON"), n=2,
                    skills=("acrobatics", "animal handling", "athletics", "history", "insight", "intimidation", "perception", "survival"),
                    armor=("chain mail", 16, None), shield=True, weapon=("longsword", "1d8", "STR"),
                    kit=["longsword", "shield", "chain mail", "light crossbow and 20 bolts", "dungeoneer's pack"], gold=10,
                    spells=[], features=["Fighting Style: Defense", "Second Wind"]),
    "monk": dict(die=8, order=("DEX", "WIS", "CON", "STR", "INT", "CHA"), saves=("STR", "DEX"), n=2,
                 skills=("acrobatics", "athletics", "history", "insight", "religion", "stealth"),
                 armor=("unarmored (10 + DEX + WIS)", 10, "monk"), shield=False, weapon=("shortsword", "1d6", "DEX"),
                 kit=["shortsword", "ten darts", "explorer's pack"], gold=5, spells=[],
                 features=["Unarmored Defense", "Martial Arts (d4)"]),
    "paladin": dict(die=10, order=("STR", "CHA", "CON", "WIS", "DEX", "INT"), saves=("WIS", "CHA"), n=2,
                    skills=("athletics", "insight", "intimidation", "medicine", "persuasion", "religion"),
                    armor=("chain mail", 16, None), shield=True, weapon=("longsword", "1d8", "STR"),
                    kit=["longsword", "shield", "chain mail", "five javelins", "holy symbol", "priest's pack"], gold=10,
                    spells=[], features=["Divine Sense", "Lay on Hands (5 hit points)"]),
    "ranger": dict(die=10, order=("DEX", "WIS", "CON", "STR", "INT", "CHA"), saves=("STR", "DEX"), n=3,
                   skills=("animal handling", "athletics", "insight", "investigation", "nature", "perception", "stealth", "survival"),
                   armor=("scale mail", 14, "max2"), shield=False, weapon=("longbow", "1d8", "DEX"),
                   kit=["longbow and 20 arrows", "two shortswords", "scale mail", "explorer's pack"], gold=10,
                   spells=[], features=["Favored Enemy", "Natural Explorer"]),
    "rogue": dict(die=8, order=("DEX", "INT", "CON", "CHA", "WIS", "STR"), saves=("DEX", "INT"), n=4,
                  skills=("acrobatics", "athletics", "deception", "insight", "intimidation", "investigation", "perception",
                          "performance", "persuasion", "sleight of hand", "stealth"),
                  armor=("leather armor", 11, "full"), shield=False, weapon=("rapier", "1d8", "DEX"),
                  kit=["rapier", "shortbow and 20 arrows", "leather armor", "two daggers", "thieves' tools", "burglar's pack"],
                  gold=15, spells=[], features=["Sneak Attack (1d6)", "Thieves' Cant", "Expertise"]),
    "sorcerer": dict(die=6, order=("CHA", "CON", "DEX", "WIS", "INT", "STR"), saves=("CON", "CHA"), n=2,
                     skills=("arcana", "deception", "insight", "intimidation", "persuasion", "religion"),
                     armor=("unarmored (10 + DEX)", 10, "full"), shield=False, weapon=("light crossbow", "1d8", "DEX"),
                     kit=["light crossbow and 20 bolts", "arcane focus", "two daggers", "dungeoneer's pack"], gold=10,
                     spells=["fire bolt", "light", "prestidigitation", "magic missile", "shield"], features=["Spellcasting", "Sorcerous Origin"]),
    "warlock": dict(die=8, order=("CHA", "CON", "DEX", "WIS", "INT", "STR"), saves=("WIS", "CHA"), n=2,
                    skills=("arcana", "deception", "history", "intimidation", "investigation", "nature", "religion"),
                    armor=("leather armor", 11, "full"), shield=False, weapon=("light crossbow", "1d8", "DEX"),
                    kit=["light crossbow and 20 bolts", "arcane focus", "leather armor", "two daggers", "scholar's pack"], gold=10,
                    spells=["eldritch blast", "minor illusion", "chill touch", "charm person"], features=["Otherworldly Patron", "Pact Magic"]),
    "wizard": dict(die=6, order=("INT", "CON", "DEX", "WIS", "CHA", "STR"), saves=("INT", "WIS"), n=2,
                   skills=("arcana", "history", "insight", "investigation", "medicine", "religion"),
                   armor=("unarmored (10 + DEX)", 10, "full"), shield=False, weapon=("quarterstaff", "1d6", "STR"),
                   kit=["quarterstaff", "spellbook", "component pouch", "scholar's pack"], gold=10,
                   spells=["fire bolt", "mage hand", "light", "magic missile", "shield", "sleep", "detect magic"],
                   features=["Spellcasting", "Arcane Recovery"]),
}
RACES = {
    "human": dict(bonus={a: 1 for a in ABILITIES}, speed=30, traits=[]),
    "elf": dict(bonus={"DEX": 2, "INT": 1}, speed=30, traits=["Darkvision", "Keen Senses", "Fey Ancestry"]),
    "dwarf": dict(bonus={"CON": 2, "WIS": 1}, speed=25, traits=["Darkvision", "Dwarven Resilience", "Stonecunning"]),
    "halfling": dict(bonus={"DEX": 2, "CHA": 1}, speed=25, traits=["Lucky", "Brave", "Nimble"]),
    "gnome": dict(bonus={"INT": 2, "CON": 1}, speed=25, traits=["Darkvision", "Gnome Cunning"]),
    "half-elf": dict(bonus={"CHA": 2, "DEX": 1, "CON": 1}, speed=30, traits=["Darkvision", "Fey Ancestry"]),
    "half-orc": dict(bonus={"STR": 2, "CON": 1}, speed=30, traits=["Darkvision", "Relentless Endurance", "Savage Attacks"]),
    "tiefling": dict(bonus={"CHA": 2, "INT": 1}, speed=30, traits=["Darkvision", "Hellish Resistance", "Infernal Legacy"]),
    "dragonborn": dict(bonus={"STR": 2, "CHA": 1}, speed=30, traits=["Breath Weapon", "Damage Resistance"]),
}
XP_LEVELS = (0, 300, 900, 2700, 6500, 14000, 23000, 34000, 48000, 64000)


# ------------------------------------------------------------------------------ dice
def roll(expr, rng):
    """'2d6+3', '1d20', '-1d4', '5' -> (total, [each die]). Every die from the game's generator."""
    s = str(expr).replace(" ", "").lower()
    sign = -1 if s.startswith("-") else 1
    s = s.lstrip("+-")
    total, dice = 0, []
    for term in re.findall(r"[+-]?[^+-]+", s):
        k = -1 if term.startswith("-") else 1
        term = term.lstrip("+-")
        m = re.fullmatch(r"(\d*)d(\d+)", term)
        if m:
            for _ in range(int(m.group(1) or 1)):
                v = rng.randint(1, int(m.group(2)))
                dice.append(v)
                total += k * v
        elif term.isdigit():
            total += k * int(term)
        else:
            raise ValueError("not dice: %r" % expr)
    return sign * total, dice


def mod(score):
    return (int(score) - 10) // 2


def prof(level):
    return 2 + (max(1, int(level)) - 1) // 4


# ------------------------------------------------------------------------------ the hero
def make_hero(spec, rng):
    """A level-1 hero from what the model proposed ({name, race, class, background, alignment, look,
    personality, backstory, skills?}); the ENGINE rolls the abilities (4d6, the lowest dropped, six
    times, placed in the class's order), then everything else follows the rules."""
    cls = str(spec.get("class") or "fighter").lower()
    cls = cls if cls in CLASSES else "fighter"
    race = str(spec.get("race") or "human").lower()
    race = race if race in RACES else "human"
    C, Rc = CLASSES[cls], RACES[race]
    rolls = []
    for _ in range(6):
        four = sorted(rng.randint(1, 6) for _ in range(4))
        rolls.append(sum(four[1:]))
    rolls.sort(reverse=True)
    # THE PLAYER'S PRIORITIES FIRST (a request for a bard with high strength, charisma and constitution gets
    # those three the best scores, not the class's own order), then the class's order for the rest
    pri = [a for a in (str(x).strip().upper()[:3] for x in (spec.get("priority") or [])) if a in ABILITIES]
    order = list(dict.fromkeys(pri + list(C["order"])))
    ab = {a: v for a, v in zip(order, rolls)}
    for a, b in Rc["bonus"].items():
        ab[a] = ab[a] + b
    want = [s for s in (spec.get("skills") or []) if s in C["skills"]]
    for s in C["skills"]:
        if len(want) >= C["n"]:
            break
        if s not in want:
            want.append(s)
    hp = C["die"] + mod(ab["CON"])
    hero = {"name": str(spec.get("name") or "the hero")[:40], "race": race, "class": cls, "level": 1, "xp": 0,
            "background": str(spec.get("background") or "wanderer")[:40],
            "alignment": str(spec.get("alignment") or "neutral")[:30],
            "look": str(spec.get("look") or "")[:200], "height_cm": _cm(spec.get("height_cm")),
            "personality": str(spec.get("personality") or "")[:240],
            "backstory": str(spec.get("backstory") or "")[:600],
            "abilities": ab, "rolls": rolls, "hp": {"now": max(1, hp), "max": max(1, hp)},
            "speed": Rc["speed"], "saves": list(C["saves"]), "skills": want[:C["n"]],
            "weapon": {"name": C["weapon"][0], "die": C["weapon"][1], "ability": C["weapon"][2]},
            "inventory": [{"name": k, "qty": 1} for k in C["kit"]], "gold": C["gold"],
            "features": list(C["features"]) + list(Rc["traits"]), "spells": list(C["spells"]), "conditions": []}
    hero["ac"] = armor_class(hero)
    return hero


def armor_class(h):
    C = CLASSES[h["class"]]
    name, base, dex = C["armor"]
    a = h["abilities"]
    ac = base + {"full": mod(a["DEX"]), "max2": min(2, mod(a["DEX"])), None: 0,
                 "unarmored": mod(a["DEX"]) + mod(a["CON"]), "monk": mod(a["DEX"]) + mod(a["WIS"])}[dex]
    if C["shield"]:
        ac += 2
    if h["class"] == "fighter":
        ac += 1                                          # Fighting Style: Defense
    return ac


def bonus(h, kind, key):
    """The bonus a check adds: a skill, an ability, a saving throw, or an attack with their weapon."""
    a, p = h["abilities"], prof(h["level"])
    if kind == "skill":
        return mod(a[SKILLS[key]]) + (p if key in h["skills"] else 0)
    if kind == "save":
        return mod(a[key]) + (p if key in h["saves"] else 0)
    if kind == "attack":
        return mod(a[h["weapon"]["ability"]]) + p
    return mod(a[key])


def check(state, kind, key, dc, adv=0):
    """Roll a check for the hero: d20 (twice, best or worst, with advantage or disadvantage) + the bonus
    against the DC. An attack that hits also rolls the weapon's damage. -> the result, also logged."""
    h = state["hero"]
    rng = CH.Rng(**state["rng"])
    kind = kind if kind in ("skill", "ability", "save", "attack") else "ability"
    if kind == "skill" and key not in SKILLS:
        kind, key = "ability", "WIS"
    if kind in ("ability", "save") and key not in ABILITIES:
        key = "WIS"
    d = [rng.randint(1, 20)]
    if adv:
        d.append(rng.randint(1, 20))
    nat = max(d) if adv > 0 else min(d) if adv < 0 else d[0]
    b = bonus(h, kind, key)
    total = nat + b
    ok = nat == 20 or (nat != 1 and total >= int(dc))
    out = {"kind": kind, "key": key, "dc": int(dc), "dice": d, "natural": nat, "bonus": b, "total": total,
           "success": ok, "critical": nat == 20, "fumble": nat == 1}
    if kind == "attack" and ok:
        dmg, dd = roll(h["weapon"]["die"], rng)
        if nat == 20:
            extra, ed = roll(h["weapon"]["die"], rng)
            dmg, dd = dmg + extra, dd + ed
        dmg += mod(h["abilities"][h["weapon"]["ability"]])
        out["damage"] = max(1, dmg)
        out["damage_dice"] = dd
    state["rng"] = rng.state()
    return out


def describe_check(r):
    """'Stealth: rolled 14 +5 = 19 against 15, a success' -- for the page and the notepad."""
    name = r["key"] if r["kind"] in ("skill",) else ("%s save" % r["key"] if r["kind"] == "save" else
                                                     "attack" if r["kind"] == "attack" else r["key"])
    s = "%s: rolled %d %+d = %d against %d, %s" % (name.capitalize() if r["kind"] == "skill" else name, r["natural"], r["bonus"],
                                                  r["total"], r["dc"], "a critical success" if r["critical"] else
                                                  "a critical failure" if r["fumble"] else "a success" if r["success"] else "a failure")
    if r.get("damage"):
        s += ", %d damage" % r["damage"]
    return s


# ------------------------------------------------------------------------------ changes the story makes
def apply(state, ch, allowed_items=()):
    """What the story says changed -> what the ENGINE accepts, and why not the rest.

    ch = {hp: "+3" | "-1d6" | int, gain: [{name, qty}], lose: [names], gold: int, xp: int,
          conditions_add: [...], conditions_remove: [...], flags_add: [...]}
    An item GAINED must be one the action was ruled to use from the picture (allowed_items) or be
    explicitly granted by a success the engine rolled (the caller passes it in allowed_items too).
    An item LOST must be one the hero has. Hit points stay in 0..max."""
    h = state["hero"]
    rng = CH.Rng(**state["rng"])
    notes = []
    if ch.get("hp") not in (None, "", 0, "0", "+0"):
        try:
            v, _ = roll(ch["hp"], rng) if isinstance(ch["hp"], str) else (int(ch["hp"]), [])
            before = h["hp"]["now"]
            h["hp"]["now"] = max(0, min(h["hp"]["max"], before + v))
            notes.append("hit points %+d (%d/%d)" % (h["hp"]["now"] - before, h["hp"]["now"], h["hp"]["max"]))
        except ValueError:
            notes.append("hit points: %r not understood" % ch["hp"])
    ok_items = {str(x).lower() for x in allowed_items}
    for g in ch.get("gain") or []:
        name = str(g.get("name") if isinstance(g, dict) else g).strip()[:40]
        qty = int(g.get("qty", 1)) if isinstance(g, dict) else 1
        if not name:
            continue
        if not any(w in name.lower() or name.lower() in w for w in ok_items):
            notes.append("not taken: %s (not in the picture, and nothing gave it)" % name)
            continue
        for it in h["inventory"]:
            if it["name"].lower() == name.lower():
                it["qty"] += max(1, qty)
                break
        else:
            h["inventory"].append({"name": name, "qty": max(1, qty)})
        notes.append("gained %s" % name)
    for name in ch.get("lose") or []:
        name = str(name).strip()
        hit = next((it for it in h["inventory"] if it["name"].lower() == name.lower() or name.lower() in it["name"].lower()), None)
        if not hit:
            notes.append("cannot lose %s: not carried" % name)
            continue
        hit["qty"] -= 1
        if hit["qty"] <= 0:
            h["inventory"].remove(hit)
        notes.append("lost %s" % hit["name"])
    if ch.get("gold"):
        g = int(ch["gold"])
        h["gold"] = max(0, h["gold"] + g)
        notes.append("gold %+d (%d)" % (g, h["gold"]))
    if ch.get("xp"):
        h["xp"] += max(0, int(ch["xp"]))
        lvl = sum(1 for x in XP_LEVELS if h["xp"] >= x)
        if lvl > h["level"]:
            gain = max(1, CLASSES[h["class"]]["die"] // 2 + 1 + mod(h["abilities"]["CON"]))
            h["level"], h["hp"]["max"], h["hp"]["now"] = lvl, h["hp"]["max"] + gain, h["hp"]["now"] + gain
            notes.append("level %d (+%d hit points)" % (lvl, gain))
    for c in ch.get("conditions_add") or []:
        if c not in h["conditions"]:
            h["conditions"].append(str(c)[:30])
    for c in ch.get("conditions_remove") or []:
        if c in h["conditions"]:
            h["conditions"].remove(c)
    for f in ch.get("flags_add") or []:
        if f not in state["flags"]:
            state["flags"].append(str(f)[:40])
    state["rng"] = rng.state()
    if h["hp"]["now"] <= 0:
        state["status"] = "down"
    return notes


# ------------------------------------------------------------------------------ the cast
# armor by the SRD: (words in an equipment name, base AC, the most dexterity counts: None = none, 99 = all)
ARMOR = (("half plate", 15, 2), ("plate", 18, None), ("splint", 17, None), ("chain mail", 16, None),
         ("ring mail", 14, None), ("breastplate", 14, 2), ("scale mail", 14, 2), ("chain shirt", 13, 2),
         ("hide", 12, 2), ("studded leather", 12, 99), ("leather", 11, 99), ("padded", 11, 99))
STATUSES = ("alive", "injured", "unconscious", "captured", "fled", "dead")
DISPOSITIONS = ("friendly", "neutral", "wary", "hostile")
LOOK_KEYS = ("build", "hair", "eyes", "skin", "face", "marks", "clothing")
PERSON_JSON = ('{"name": "...", "race": "...", "sex": "...", "age": "...", "role": "what they are: innkeeper, guard, smuggler...", '
               '"class": one of ' + ", ".join(CLASSES) + ' or "commoner", "level": 1 to 5, "alignment": "...", '
               '"look": {"height_cm": a number, "build": "...", "hair": "...", "eyes": "...", "skin": "...", "face": "...", '
               '"marks": "scars, tattoos, or none", "clothing": "..."}, "equipment": ["what they wear and carry"], '
               '"personality": "one sentence", "backstory": "two sentences", '
               '"criminal_record": ["known crimes, convictions or warrants; empty when none"], '
               '"disposition": one of ' + ", ".join(DISPOSITIONS) + ', "secret": "one sentence the player is not told"}')


def _cm(v):
    try:
        return max(50, min(400, int(float(v))))
    except (TypeError, ValueError):
        return None


def _s(v, n=80):
    return " ".join(str(v or "").split())[:n]


def person_ac(p):
    """10 + DEX, or the armor it wears by the SRD; a shield adds 2."""
    dex = mod(p["abilities"]["DEX"])
    ac = 10 + dex
    gear = [str(e).lower() for e in p.get("equipment") or []]
    for words, base, cap in ARMOR:
        if any(words in g for g in gear):
            ac = base + (0 if cap is None else min(dex, cap))
            break
    if any("shield" in g for g in gear):
        ac += 2
    return ac


def make_person(spec, rng, turn_no, place):
    """A person the story meets, from what the model proposed; the ENGINE rolls the abilities (4d6, the lowest
    dropped, in the fixed order) and the hit points (the class's die per level + CON), and works out the armor."""
    cls = _s(spec.get("class"), 20).lower() or "commoner"
    cls = cls if cls in CLASSES else "commoner"
    try:
        level = max(1, min(5, int(spec.get("level") or 1)))
    except (TypeError, ValueError):
        level = 1
    ab = {}
    for a in ABILITIES:
        four = sorted(rng.randint(1, 6) for _ in range(4))
        ab[a] = sum(four[1:])
    die = CLASSES[cls]["die"] if cls in CLASSES else 8
    hp = max(1, sum(rng.randint(1, die) for _ in range(level)) + mod(ab["CON"]) * level)
    lk = spec.get("look") if isinstance(spec.get("look"), dict) else {"build": _s(spec.get("look"), 160)}
    look = {"height_cm": _cm(lk.get("height_cm"))}
    look.update({k: _s(lk.get(k), 90) for k in LOOK_KEYS})
    disp = _s(spec.get("disposition"), 12).lower()
    p = {"name": _s(spec.get("name"), 40), "race": _s(spec.get("race"), 30) or "human", "sex": _s(spec.get("sex"), 20),
         "age": _s(spec.get("age"), 20), "role": _s(spec.get("role"), 60), "class": cls, "level": level,
         "alignment": _s(spec.get("alignment"), 30) or "neutral", "look": look, "abilities": ab,
         "hp": {"now": hp, "max": hp}, "equipment": [_s(e, 50) for e in (spec.get("equipment") or []) if _s(e)][:12],
         "personality": _s(spec.get("personality"), 240), "backstory": _s(spec.get("backstory"), 500),
         "criminal_record": [_s(e, 120) for e in (spec.get("criminal_record") or []) if _s(e)][:12],
         "disposition": disp if disp in DISPOSITIONS else "neutral", "status": "alive", "conditions": [],
         "secret": _s(spec.get("secret"), 240), "met": {"turn": turn_no, "place": place},
         "last_seen": {"turn": turn_no, "place": place}, "notes": [], "portrait": None,
         "known": {"fields": [], "facts": []}}
    p["ac"] = person_ac(p)
    return p


def find_person(state, name):
    """A cast member by name: the whole name, else the first name; None when the story has not met them."""
    n = _s(name, 60).lower()
    if not n:
        return None
    cast = state.get("cast") or {}
    for p in cast.values():
        if p["name"].lower() == n:
            return p
    first = n.split()[0]
    for p in cast.values():
        if p["name"].lower().split()[0] == first:
            return p
    # a name one misread letter away (handwriting: "Clara" for Elara) is the same person, not a newcomer
    import difflib
    names = {p["name"].lower(): p for p in cast.values()}
    near = difflib.get_close_matches(n, list(names), n=1, cutoff=0.8)
    return names[near[0]] if near else None


def add_people(state, specs, rng, turn_no, place):
    """New people -> the cast (anyone already in it is left exactly as they are). -> the new entries."""
    cast = state.setdefault("cast", {})
    new = []
    for sp in specs or []:
        if not isinstance(sp, dict) or not _s(sp.get("name")) or find_person(state, sp.get("name")):
            continue
        p = make_person(sp, rng, turn_no, place)
        cast[p["name"]] = p
        new.append(p)
    return new


def hurt(p, amount):
    """Damage to a cast member; at 0 hit points they drop unconscious."""
    p["hp"]["now"] = max(0, min(p["hp"]["max"], p["hp"]["now"] - int(amount)))
    if p["hp"]["now"] == 0 and p["status"] in ("alive", "injured"):
        p["status"] = "unconscious"
    elif p["hp"]["now"] < p["hp"]["max"] and p["status"] == "alive":
        p["status"] = "injured"


def apply_people(state, changes, rng, turn_no, place):
    """What the story says changed for the cast -> what the ENGINE accepts. Looks, race, height and build are
    never changed. The dead stay dead. Equipment is lost only when carried. -> notes."""
    notes = []
    for ch in changes or []:
        if not isinstance(ch, dict):
            continue
        p = find_person(state, ch.get("name"))
        if p is None:
            continue
        st = _s(ch.get("status"), 12).lower()
        if st in STATUSES and st != p["status"]:
            if p["status"] == "dead":
                notes.append("%s stays dead" % p["name"])
            else:
                p["status"] = st
                notes.append("%s: %s" % (p["name"], st))
        dp = _s(ch.get("disposition"), 12).lower()
        if dp in DISPOSITIONS:
            p["disposition"] = dp
        if ch.get("hp") not in (None, "", 0, "0", "+0") and p["status"] != "dead":
            try:
                v, _ = roll(ch["hp"], rng) if isinstance(ch["hp"], str) else (int(ch["hp"]), [])
                hurt(p, -v)
            except ValueError:
                pass
        for c in ch.get("conditions_add") or []:
            if _s(c, 30) and _s(c, 30) not in p["conditions"]:
                p["conditions"].append(_s(c, 30))
        for c in ch.get("conditions_remove") or []:
            if c in p["conditions"]:
                p["conditions"].remove(c)
        for e in ch.get("equipment_gain") or []:
            if _s(e) and len(p["equipment"]) < 16:
                p["equipment"].append(_s(e, 50))
        for e in ch.get("equipment_lose") or []:
            hit = next((g for g in p["equipment"] if _s(e).lower() and (_s(e).lower() in g.lower() or g.lower() in _s(e).lower())), None)
            if hit:
                p["equipment"].remove(hit)
        for r in ch.get("record_add") or []:
            if _s(r) and len(p["criminal_record"]) < 20:
                p["criminal_record"].append(_s(r, 120))
                notes.append("%s: %s" % (p["name"], _s(r, 60)))
        if _s(ch.get("note")):
            p["notes"] = (p["notes"] + ["turn %d: %s" % (turn_no, _s(ch["note"], 160))])[-10:]
        # WHAT THE HERO NOW KNOWS about them: the journal shows only this (their class, if known)
        kn = p.setdefault("known", {"fields": [], "facts": []})
        for f in ch.get("learned") or []:
            if _s(f) and _s(f, 200) not in kn["facts"]:
                kn["facts"] = (kn["facts"] + [_s(f, 200)])[-20:]
        for f in ch.get("revealed") or []:
            f = _s(f, 20).lower()
            if f in KNOWABLE and f not in kn["fields"]:
                kn["fields"].append(f)
        p["ac"] = person_ac(p)
    return notes


KNOWABLE = ("class", "level", "alignment", "backstory", "record", "personality")


def apply_story(state, tell, turn_no):
    """The lore the hero learned and the quests, as the ENGINE keeps them. -> notes."""
    notes = []
    lore = state.setdefault("lore", [])
    have = set(x["text"].lower() for x in lore)
    for f in tell.get("lore") or []:
        f = _s(f, 300)
        if f and f.lower() not in have and len(lore) < 300:
            lore.append({"turn": turn_no, "text": f})
            have.add(f.lower())
    quests = state.setdefault("quests", [])
    for q in tell.get("quests") or []:
        if not isinstance(q, dict) or not _s(q.get("name")):
            continue
        name = _s(q["name"], 60)
        cur = next((x for x in quests if x["name"].lower() == name.lower()), None)
        st = _s(q.get("status"), 10).lower()
        if cur is None:
            cur = {"name": name, "goal": _s(q.get("goal"), 240), "status": "open", "turn": turn_no, "updates": []}
            quests.append(cur)
            notes.append("new quest: %s" % name)
        if st in ("open", "done", "failed") and st != cur["status"]:
            cur["status"] = st
            notes.append("quest %s: %s" % (st, name))
        if _s(q.get("update")):
            cur["updates"] = (cur["updates"] + ["turn %d: %s" % (turn_no, _s(q["update"], 200))])[-12:]
    return notes


def lore_block(state, n=25):
    return "\n".join("- " + x["text"] for x in (state.get("lore") or [])[-n:]) or "- nothing yet"


def quests_line(state):
    q = state.get("quests") or []
    return "; ".join("%s (%s): %s" % (x["name"], x["status"], x["goal"]) for x in q[-8:]) or "none yet"


def _relative(cm, hero_cm):
    if not cm or not hero_cm:
        return ""
    d = cm - hero_cm
    return (" (about the hero's height)" if abs(d) < 6 else " (much taller than the hero)" if d >= 25 else
            " (taller than the hero)" if d > 0 else " (much shorter than the hero)" if d <= -25 else " (shorter than the hero)")


def person_look(p, hero_cm=None):
    """How a person looks, in words, exactly as recorded -- for every picture they are in."""
    lk = p["look"]
    parts = [w for w in (p["race"], p["sex"], p["age"]) if w]
    if lk.get("height_cm"):
        parts.append("%d cm tall%s" % (lk["height_cm"], _relative(lk["height_cm"], hero_cm)))
    for k in ("build", "hair", "eyes", "skin", "face", "marks"):
        v = lk.get(k)
        if v and v.lower() != "none":
            # "gray" alone could be anything: the eyes and the skin are named
            parts.append(v + (" " + k if k in ("eyes", "skin") and k.rstrip("s") not in v.lower() else ""))
    if lk.get("clothing"):
        parts.append("wearing " + lk["clothing"])
    if p["equipment"]:
        parts.append("carrying " + ", ".join(p["equipment"][:3]))
    return "%s: %s" % (p["name"], ", ".join(parts))


def person_line(p, hero_cm=None):
    """Everything the game master must keep true about a person."""
    return ("%s -- %s (%s %d), %s; armor %d, %d/%d hit points; %s, %s%s; record: %s; backstory: %s; personality: %s; "
            "secret: %s; met turn %d at %s, last seen turn %d at %s%s" % (
                person_look(p, hero_cm), p["role"] or "a stranger", p["class"], p["level"], p["alignment"], p["ac"],
                p["hp"]["now"], p["hp"]["max"], p["status"], p["disposition"],
                ("; " + ", ".join(p["conditions"])) if p["conditions"] else "", "; ".join(p["criminal_record"]) or "none",
                p["backstory"] or "-", p["personality"] or "-", p["secret"] or "-", p["met"]["turn"], p["met"]["place"] or "?",
                p["last_seen"]["turn"], p["last_seen"]["place"] or "?", ("; notes: " + " | ".join(p["notes"][-3:])) if p["notes"] else ""))


def cast_block(state, names=None):
    """The cast for a prompt: the named people, or everyone (the most recently seen first, twelve at most)."""
    cast = list((state.get("cast") or {}).values())
    if names is not None:
        cast = [p for p in cast if p["name"] in names]
    cast.sort(key=lambda p: -p["last_seen"]["turn"])
    hcm = state["hero"].get("height_cm")
    return "\n".join("- " + person_line(p, hcm) for p in cast[:12]) or "- nobody yet"


def events_block(state, n=10):
    ev = state.get("events") or []
    return "\n".join("- turn %d (%s): %s" % (e["n"], e.get("place") or "?", e["text"]) for e in ev[-n:]) or "- the adventure has just begun"


def hero_look(h):
    return (h.get("look") or "not described") + ((", %d cm tall" % h["height_cm"]) if h.get("height_cm") else "")


# ------------------------------------------------------------------------------ the state
def new_state(doc, title, premise, tone, hero, seed=None):
    seed = seed or CH.new_seed()
    now = int(time.time())
    return {"game": "adventure", "version": 1, "id": "adv-" + seed[:8], "doc": doc, "page_id": None,
            "title": title, "premise": premise, "tone": tone, "rng": {"seed": seed, "draws": 0}, "hero": hero,
            "sheet": {"page_id": None, "hash": None, "box": None}, "turns": [], "place": "", "flags": [],
            "status": "playing", "created": now, "updated": now,
            "layout": "fixed", "log_page": None, "cast": {}, "events": [], "present": []}


def summary_lines(state):
    h = state["hero"]
    return ["ink adventure %s: %s" % (state["id"], state["title"]),
            "%s, a level %d %s %s; %d/%d hit points; %d turns; %s" % (h["name"], h["level"], h["race"], h["class"],
                                                                      h["hp"]["now"], h["hp"]["max"], len(state["turns"]),
                                                                      state["place"] or "no place yet"),
            "inventory: %s" % ", ".join("%s%s" % (it["name"], (" x%d" % it["qty"]) if it["qty"] > 1 else "") for it in h["inventory"])]


CH.SUMMARIES["adventure"] = summary_lines


def scenes_dir(doc, game=None):
    """Where each scene's picture is KEPT before it is converted, so a later turn can edit it and the
    model can look at it. A game played inside the user's own notebook keeps its pictures in a folder of its own
    (`game`, its id): one notebook can hold several."""
    d = os.path.join(CH.NOTEPAD_DIR, doc, "scenes", *([game] if game else []))
    os.makedirs(d, exist_ok=True)
    return d


def pictures_dir(state):
    """The game's own picture folder."""
    return scenes_dir(state["doc"], state["id"] if is_inline(state) else None)


# ------------------------------------------------------------------------------ the pages
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


INK, GRAY, RULE = (24, 24, 26), (100, 100, 106), (205, 205, 210)


def sheet_png(state, out):
    """PAGE 1: the character sheet, drawn at the page's own size (1620 x 2160)."""
    from PIL import Image, ImageDraw
    h = state["hero"]
    im = Image.new("RGB", (PAGE_W, PAGE_H), "white")
    d = ImageDraw.Draw(im)
    M, W = 80, PAGE_W - 160
    big, bold, reg, med, small = (_font("reMarkableSans-Bold.ttf", 60), _font("reMarkableSans-Bold.ttf", 34),
                                  _font("reMarkableSans-Regular.ttf", 30), _font("reMarkableSans-Medium.ttf", 30),
                                  _font("reMarkableSans-Regular.ttf", 24))
    y = int(CH.TOP)                                   # below the tablet's toolbar
    d.text((M, y), h["name"], font=big, fill=INK)
    y += 80
    d.text((M, y), "Level %d %s %s  ·  %s  ·  %s" % (h["level"], h["race"].capitalize(), h["class"].capitalize(),
                                                            h["background"], h["alignment"]), font=reg, fill=GRAY)
    y += 44
    d.text((M, y), "%s  ·  XP %d" % (state["title"], h["xp"]), font=small, fill=GRAY)
    y += 60
    # the six abilities: a box each, the modifier big, the score small
    bw = W // 6
    for i, a in enumerate(ABILITIES):
        x = M + i * bw
        d.rounded_rectangle((x + 8, y, x + bw - 8, y + 170), 18, outline=INK, width=3)
        t = ABILITY_NAMES[a].upper()
        d.text((x + (bw - d.textlength(t, font=small)) / 2, y + 12), t, font=small, fill=GRAY)
        m = "%+d" % mod(h["abilities"][a])
        d.text((x + (bw - d.textlength(m, font=big)) / 2, y + 44), m, font=big, fill=INK)
        s = str(h["abilities"][a])
        d.text((x + (bw - d.textlength(s, font=reg)) / 2, y + 122), s, font=reg, fill=INK)
    y += 200
    # armor, hit points, speed, proficiency, initiative
    stats = [("ARMOR", str(h["ac"])), ("HIT POINTS", "%d / %d" % (h["hp"]["now"], h["hp"]["max"])),
             ("SPEED", "%d ft" % h["speed"]), ("PROFICIENCY", "%+d" % prof(h["level"])),
             ("INITIATIVE", "%+d" % mod(h["abilities"]["DEX"])), ("GOLD", str(h["gold"]))]
    bw = W // len(stats)
    for i, (k, v) in enumerate(stats):
        x = M + i * bw
        d.rounded_rectangle((x + 8, y, x + bw - 8, y + 120), 14, outline=INK, width=3)
        d.text((x + (bw - d.textlength(k, font=small)) / 2, y + 12), k, font=small, fill=GRAY)
        d.text((x + (bw - d.textlength(v, font=bold)) / 2, y + 54), v, font=bold, fill=INK)
    y += 150
    col = W // 2 - 20
    # left: saves and skills; right: attack, features, spells, conditions
    ly = y
    d.text((M, ly), "Saving throws", font=med, fill=INK)
    ly += 44
    for a in ABILITIES:
        on = a in h["saves"]
        d.ellipse((M, ly + 8, M + 16, ly + 24), fill=INK if on else None, outline=INK, width=2)
        d.text((M + 28, ly), "%+d  %s" % (bonus(h, "save", a), ABILITY_NAMES[a]), font=small, fill=INK)
        ly += 34
    ly += 16
    d.text((M, ly), "Skills", font=med, fill=INK)
    ly += 44
    for s in sorted(SKILLS):
        on = s in h["skills"]
        d.ellipse((M, ly + 8, M + 16, ly + 24), fill=INK if on else None, outline=INK, width=2)
        d.text((M + 28, ly), "%+d  %s (%s)" % (bonus(h, "skill", s), s.capitalize(), SKILLS[s]), font=small, fill=INK)
        ly += 32
    rx, ry = M + col + 40, y
    d.text((rx, ry), "Attack", font=med, fill=INK)
    ry += 44
    w = h["weapon"]
    d.text((rx, ry), "%s: %+d to hit, %s%+d" % (w["name"].capitalize(), bonus(h, "attack", None), w["die"],
                                               mod(h["abilities"][w["ability"]])), font=small, fill=INK)
    ry += 48
    for title, items in (("Features", h["features"]), ("Spells", h["spells"]), ("Conditions", h["conditions"])):
        if not items:
            continue
        d.text((rx, ry), title, font=med, fill=INK)
        ry += 44
        for line in _wrap(d, ", ".join(items), small, col):
            d.text((rx, ry), line, font=small, fill=INK)
            ry += 32
        ry += 16
    y = max(ly, ry) + 20
    d.line((M, y, M + W, y), fill=RULE, width=2)
    y += 20
    d.text((M, y), "Inventory", font=med, fill=INK)
    y += 46
    inv = ["%s%s" % (it["name"], (" x%d" % it["qty"]) if it["qty"] > 1 else "") for it in h["inventory"]]
    for i, line in enumerate(inv):
        x = M + (i % 2) * (W // 2)
        d.text((x, y + (i // 2) * 34), "• " + line, font=small, fill=INK)
    y += ((len(inv) + 1) // 2) * 34 + 24
    if h.get("personality") and y < PAGE_H - 200:
        d.text((M, y), "Who they are", font=med, fill=INK)
        y += 44
        for line in _wrap(d, h["personality"] + " " + h.get("backstory", ""), small, W)[:8]:
            d.text((M, y), line, font=small, fill=INK)
            y += 32
    im.save(out)
    return out


# the turn page: where each part goes, in page pixels (1620 x 2160, y from the top)
# the square the picture is converted into: from the top of the page's safe area (below the tablet's
# toolbar) down to 1270, centered
_SCENE_SIDE = 1270 - int(CH.TOP)
SCENE_BOX = ((PAGE_W - _SCENE_SIDE) // 2, int(CH.TOP), (PAGE_W + _SCENE_SIDE) // 2, 1270)
TEXT_TOP, WRITE_TOP = 1300, 1810            # the story, then the player's space: the turn page's picture ends there,
                                            # and under it is the page itself, to type or write in (inputarea.py)


def scene_frame_page(s=1.0):
    """The picture's box in the page's own coordinates (x from the center), for the strokes; `s` scales the designed
    page to the page's own tablet (tablets.picture_page)."""
    x0, y0, x1, y1 = SCENE_BOX
    return ((x0 - PAGE_W / 2.0) * s, y0 * s, (x1 - PAGE_W / 2.0) * s, y1 * s)


def turn_png(state, scene, out, roll_line="", n=None, col_px=None):
    """A TURN PAGE's picture: a frame where the scene goes (its strokes are laid over it), what happened,
    what is around, a few loose options, and at its foot where to answer, from `col_px` (the typed-text column's
    left edge, design pixels). `n`: the turn's number (the next one). On the page it is cut at WRITE_TOP."""
    from PIL import Image, ImageDraw
    im = Image.new("RGB", (PAGE_W, PAGE_H), "white")
    d = ImageDraw.Draw(im)
    M, W = 80, PAGE_W - 160
    # A STORY TOLD IN FULL (a character's tale is three to six sentences) must fit above the box: the largest
    # type that holds it all
    for size, LH in ((30, 40), (26, 35), (23, 31)):
        reg, ital, med, small = (_font("reMarkableSans-Regular.ttf", size), _font("reMarkableSans-RegularItalic.ttf", size - 2),
                                 _font("reMarkableSans-Medium.ttf", 30), _font("reMarkableSans-Regular.ttf", 24))
        need = TEXT_TOP + 46 + (36 if roll_line else 0) + 64
        for part, font in ((scene.get("what_happened"), reg), (scene.get("around"), ital)):
            need += len(_wrap(d, part or "", font, W)) * LH + 10
        if need <= WRITE_TOP - 30:
            break
    x0, y0, x1, y1 = SCENE_BOX
    d.rounded_rectangle((x0 - 6, y0 - 6, x1 + 6, y1 + 6), 16, outline=RULE, width=3)
    y = TEXT_TOP
    head = "%s  ·  turn %d" % (scene.get("place") or state["place"] or state["title"], n or len(state["turns"]) + 1)
    d.text((M, y), head, font=med, fill=INK)
    y += 46
    if roll_line:
        d.text((M, y), roll_line, font=small, fill=GRAY)
        y += 36
    for part, font in ((scene.get("what_happened"), reg), (scene.get("around"), ital)):
        if part:
            for line in _wrap(d, part, font, W):
                if y > WRITE_TOP - 30 - LH:
                    break
                d.text((M, y), line, font=font, fill=INK)
                y += LH
            y += 10
    opts = [o for o in (scene.get("options") or []) if str(o).strip()][:4]
    from paperdaemon.pipeline.games import inputarea as IA
    if opts and y < WRITE_TOP - 60:
        line = "You could: " + "  ·  ".join(opts)
        for l in _wrap(d, line, small, W)[:2]:
            if y + 32 > WRITE_TOP - IA.LABEL_H - 6:
                break                                    # clear of the instruction at the foot
            d.text((M, y), l, font=small, fill=GRAY)
            y += 32
    IA.foot(im, WRITE_TOP, "What do you do? Type or write it below", M if col_px is None else col_px, _font("reMarkableSans-Medium.ttf", 30), IA.LABEL_INK, RULE)
    im.save(out)
    return out


# ------------------------------------------------------------------------------ the model's prompts
SETUP_PROMPT = """You are the game master of a text adventure played on a paper tablet.
The player asked: "{what}"
Invent the adventure and the hero the request asks for (if it names none, choose something good).
Answer with JSON only:
{{"title": "a short title", "premise": "two sentences the player is not told", "tone": "a few words",
 "hero": {{"name": "...", "race": one of {races}, "class": one of {classes}, "background": "...",
          "alignment": "...", "height_cm": a number, "look": "one sentence: build, hair, eyes, skin, clothing",
          "priority": ["the abilities the player asked to be highest, in their order, as STR, DEX, CON, INT, WIS or CHA; [] if none"],
          "personality": "two sentences", "backstory": "three sentences",
          "skills": ["up to four skills from: {skills}"]}},
 "opening": {{"place": "where the story begins, a few words", "what_happened": "two to four sentences, second person",
             "around": "two sentences: what the hero can see around them", "options": ["three or four loose ideas"],
             "people": [every named person in the opening scene, each {person}],
             "picture": "what the hero SEES in front of them: the place, the objects in it, where each person stands. Never describe the hero."}}}}
"around" and "options" name only what the hero can see: never the premise, a secret or a hidden place."""

RULE_PROMPT = """You are the game master of a text adventure. The hero:
{hero}
Where they are: {place}. What the player saw last: {around}
The people here (an attack on one of them must beat their armor):
{people}
What has happened lately:
{events}
THE PICTURE of the scene is attached: it is what the hero sees. Anything visible in it is really there.
The player wrote: "{action}"
Rule on it. Answer with JSON only:
{{"understood": "what the player means, one sentence", "possible": true or false, "why_not": "if impossible, why, in one sentence",
 "uses": ["each object or person FROM THE PICTURE the action relies on, as you see it there -- only what is visible"],
 "check": null or {{"kind": "skill" | "ability" | "save" | "attack", "key": a skill ({skills}) or an ability ({abilities}),
                  "dc": 5 to 25, "advantage": -1, 0 or 1, "why": "why this check", "target": "for an attack, the name of the person attacked"}}}}
Ask for a check only when the outcome is uncertain and matters; an attack's dc is the target's armor class."""

TELL_PROMPT = """You are the game master of a text adventure. The adventure: {title} (tone: {tone}).
FOR THE GAME MASTER ONLY -- the hero knows none of this until the story reveals it in what_happened: the premise
({premise}), and every person's secret, class, level, alignment, backstory and record in the list below.
The hero: {hero}
The hero looks like: {look}
The people of this story. THEIR LOOKS ARE FIXED: never change anyone's race, height, build, hair, face or marks.
{cast}
What has happened so far:
{events}
What the hero has learned (the lore):
{lore}
Quests: {quests}
Where they were: {place}. What was around: {around}
The player wrote: "{action}" -- which you ruled means: {understood}
{roll}
Tell what happens next, true to the roll, true to the people above and to what has happened, and set the next scene.
MOVE THE STORY. When the player asks for something and gets it (the roll succeeded, or none was needed), deliver it in
full THIS turn: a story asked for is told in the person's own words, three to six sentences with real names, places
and events; information asked for is given plainly; never just "they are grateful" or "they will tell you later".
Every turn brings something new: a fact, a choice, a danger or a consequence.
NO LEAKS. "around" and "options" name only what the hero can see now or has already been told. Never mention a
hidden place, a secret or the premise until what_happened itself reveals it.
The player's words were read from handwriting by a machine: a name that looks like one of the people above means
that person -- never make the hero get a name wrong.
Answer with JSON only:
{{"what_happened": "two to six sentences, second person, what the action led to (a story asked for, told in full)",
 "log": "one line for the adventure log, past tense: what the hero did and what came of it",
 "place": "where the hero is now, a few words", "same_place": true if the hero is still looking at the same scene,
 "around": "two sentences: what the hero can see now",
 "options": ["three or four loose ideas, not the only choices"],
 "present": ["the name of each person listed above who is in the next scene"],
 "new_people": [every named person appearing for the FIRST time, each {person}],
 "people_changes": [{{"name": "...", "status": one of {statuses}, "disposition": one of {dispositions}, "hp": "0",
                     "conditions_add": [], "conditions_remove": [], "equipment_gain": [], "equipment_lose": [],
                     "record_add": ["a crime they committed or were charged with this turn"],
                     "learned": ["what the hero learned about this person this turn"],
                     "revealed": ["any of {fields} that the hero now knows about them"], "note": "one line"}}],
 "lore": ["each fact about the world, a place, a people or its history that the hero learned this turn"],
 "quests": [{{"name": "a short name", "goal": "for a new quest: what must be done", "status": "open | done | failed",
             "update": "one line: what changed"}}],
 "picture": {{"mode": "edit" if same_place and the scene only changed a little (say the change: "remove the lantern from
             the table, keep everything else") else "new", "prompt": "the change, or for a new scene what the hero SEES in
             front of them: the place, the objects, where each person stands. Never describe the hero."}},
 "changes": {{"hp": "0", "gain": [{{"name": "...", "qty": 1}}], "lose": ["..."], "gold": 0, "xp": 0,
             "conditions_add": [], "conditions_remove": [], "flags_add": []}},
 "over": null or "death" or "victory"}}
Only give items the hero actually took or was given; hit point loss can be dice like "-1d6". Leave out what did not change."""

READ_PROMPT = """This is the player's handwriting from the bottom of a page of a text adventure on a tablet, alone:
what they do next (or the rest of it, after what they typed). Answer with one line:
ACTION: <exactly what they wrote, spelling fixed>, or NOTHING if nothing is written or it is unreadable.
The names in this story: {names}. A handwritten word that looks like one of them IS that name."""

# ONE STYLE, every picture, every game: the same words in new pictures, edits and portraits, so the art style
# stays consistent
STYLE = ("Hand-inked graphic-novel illustration in full color: detailed ink line work, bold clean black outlines, "
         "muted earthy colors, warm light, high contrast.")
POV = ("First-person view through the eyes of %s: the hero is NOT in the picture, at most the hero's own hands at the "
       "bottom edge.")


def place_of(state, place, words=""):
    """THE PLACE, as it was first seen (so the setting does not drift from picture to picture): a place's
    description is recorded the first time the story goes there and given with every later picture of it."""
    places = state.setdefault("places", {})
    key = _s(place, 80).lower()
    if key and key not in places and _s(words):
        places[key] = _s(words, 600)
    return places.get(key, "")


def scene_prompt(state, pic_prompt, present, setting=""):
    """A NEW scene's picture prompt, framed by the engine: what is in front (the model's words), the place as first
    seen, each person in it exactly as recorded, the first-person frame, then the style (Klein follows the subject
    first)."""
    hcm = state["hero"].get("height_cm")
    people = [person_look(p, hcm) for p in present]
    s = _s(pic_prompt, 900).rstrip(". ") + ". "
    if setting and setting.lower() not in s.lower():
        s += "The place: " + setting.rstrip(". ") + ". "
    if people:
        s += "The people in it, exactly so: " + "; ".join(people) + ". "
    return s + POV % state["hero"]["name"] + " " + STYLE


def edit_prompt(state, change, present, new_people, setting=""):
    """An EDIT of the last scene (the last picture goes in as the reference): the change, then the whole scene as it
    must stay -- the place, everyone in it as recorded, the frame and the style -- so the picture keeps them even
    where the reference alone would not."""
    hcm = state["hero"].get("height_cm")
    s = "Change only this: " + _s(change, 600).rstrip(". ") + ". "
    if new_people:
        s += "New in the scene, exactly so: " + "; ".join(person_look(p, hcm) for p in new_people) + ". "
    s += "Keep everything else exactly as in the reference picture"
    if setting:
        s += ": the place (" + setting.rstrip(". ") + ")"
    old = [p for p in present if p not in new_people]
    if old:
        s += "; the people, exactly so: " + "; ".join(person_look(p, hcm) for p in old)
    return s + ". " + POV % state["hero"]["name"] + " " + STYLE


def portrait_prompt(state, p):
    return ("Portrait of %s, head and shoulders, facing the viewer, plain light background. %s" % (
        person_look(p, state["hero"].get("height_cm")), STYLE))


def known_names(state):
    return [state["hero"]["name"]] + list((state.get("cast") or {}).keys())


def fix_names(state, text):
    """HANDWRITING MISREAD AS ANOTHER NAME ("Elara" read as "Clara", and the story would have the hero get a
    name wrong): a capitalized word close to a name the story knows IS that name."""
    import difflib
    names = known_names(state)

    def sub(m):
        w = m.group(0)
        if w in names:
            return w
        c = difflib.get_close_matches(w, names, n=1, cutoff=0.8)
        return c[0] if c else w
    return re.sub(r"\b[A-Z][a-z]{2,}\b", sub, str(text or ""))


def parse_json(text):
    """The first JSON object in a model's answer, or {}."""
    m = re.search(r"\{.*\}", str(text or ""), re.S)
    if not m:
        return {}
    try:
        return json.loads(m.group(0))
    except ValueError:
        return {}


def _log(log, msg):
    if log:
        log(msg)


# ------------------------------------------------------------------------------ putting pages together
def _put_full(doc, page_no, page_id, png, kind, state):
    """A page-sized picture (the sheet, a turn's page) -> its placement."""
    from paperdaemon.pipeline.page import images as IM
    box = TB.picture_page(TB.frame_of(doc, page_no))[0]           # the page's own tablet's frame
    r = IM.insert(doc, page_no, png, box, page_id=page_id)
    IM.record_placement(r["doc"], page_no, r["name"], box, hash=r["hash"], kind=kind, game=state["id"])
    return {"page_id": page_id, "hash": r["hash"], "name": r["name"], "box": list(box)}


def _draw_scene(doc, page_no, scene_png):
    """The scene's picture, converted to strokes and laid over the page's frame."""
    from paperdaemon.pipeline import draw as A
    from paperdaemon.pipeline import decompose as M
    # THE PAGE'S OWN COORDINATES, x = 0 at the center. SCENE_BOX is in the turn picture's pixels (x from
    # the left edge); handing it over as it is would put the whole scene half a page to the right of its
    # frame, more than half of it off the page.
    frame = TB.frame_of(doc, page_no)
    x0, y0, x1, y1 = scene_frame_page(TB.picture_page(frame)[1])
    strokes, info, secs = M.decompose_into(scene_png, int(x1 - x0), int(y1 - y0), origin=(x0, y0))
    d = A.Drawing(*[int(round(v)) for v in frame])
    d.strokes = list(strokes)
    d.write_rm(doc, page_no, keep_existing=True)
    return len(strokes), secs


def _keep(state, turn_no, png):
    """The scene's picture KEPT beside the notepad (for an edit next turn, and for the model to see)."""
    import shutil
    dst = os.path.join(pictures_dir(state), "%03d.png" % turn_no)
    shutil.copyfile(png, dst)
    return dst


def _with_card(paint, fn):
    """fn() inside ONE hand-over of the card to the picture model when the host offers one (paint.session), so a
    turn's portraits and its scene cost one swap instead of one each."""
    session = getattr(paint, "session", None)
    return session(fn) if session else fn()


def cast_dir(state):
    d = os.path.join(pictures_dir(state), "cast")
    os.makedirs(d, exist_ok=True)
    return d


def _slug(name):
    return re.sub(r"[^a-z0-9]+", "-", str(name).lower()).strip("-")[:40] or "person"


def _portraits(paint, state, people, log=None):
    """A portrait of each newcomer, painted ONCE when they first appear and kept beside the notepad
    (scenes/cast/<name>.png): what they look like, for the player and for every later picture of them."""
    import shutil
    for p in people:
        try:
            png = paint(portrait_prompt(state, p), "new", None)
        except Exception as ex:
            _log(log, "  adventure: no portrait of %s: %s" % (p["name"], str(ex)[:100]))
            continue
        if png:
            dst = os.path.join(cast_dir(state), _slug(p["name"]) + ".png")
            shutil.copyfile(png, dst)
            try:
                os.remove(png)
            except OSError:
                pass
            p["portrait"] = "cast/" + os.path.basename(dst)


def _paint_scene(paint, state, pic, prev_png, present=(), newcomers=(), log=None, fallback="", setting=""):
    """The next scene's picture: an EDIT of the last one when the story stays in the same place and says
    what changed, else a new picture -- both framed by the engine (scene_prompt, edit_prompt): first person,
    and everyone in it exactly as the cast records them. An edit that fails draws the scene anew from
    `fallback` (what the hero sees now). -> a PNG path (the caller keeps it), or None."""
    if paint is None:
        return None
    mode = (pic or {}).get("mode") or "new"
    prompt = _s((pic or {}).get("prompt"), 900) or _s(fallback, 900)
    if not prompt:
        return None
    if mode == "edit" and prev_png and os.path.exists(prev_png):
        try:
            return paint(edit_prompt(state, prompt, present, newcomers, setting), "edit", prev_png)
        except Exception as ex:
            _log(log, "  adventure: the edit failed (%s); drawing the scene anew" % str(ex)[:100])
            prompt = _s(fallback, 900) or prompt
    try:
        return paint(scene_prompt(state, prompt, present, setting), "new", None)
    except Exception as ex:
        _log(log, "  adventure: the picture failed: %s" % str(ex)[:120])
        return None


def _page_no(doc, page_id):
    from paperdaemon.pipeline.page import render as R
    live = [p["id"] for p in R.live_pages(doc)]
    return live.index(page_id) + 1 if page_id in live else None


def _clear_page(doc, page_id):
    """Everything off a page the game owns -- its page picture, the scene's strokes, what the player wrote (read
    already) -- so it can be drawn again in place. The page file is rebuilt from its own structure
    (rm_pages.blank_page_bytes), so no tombstones pile up turn after turn. -> the page number."""
    from paperdaemon.pipeline.page import images as IM
    from paperdaemon.remarkable import library as PG
    from paperdaemon.pipeline.page import render as R
    pno = _page_no(doc, page_id)
    if pno is None:
        raise RuntimeError("the game's page is gone from the notebook")
    try:
        IM.remove_in_box(doc, pno, TB.picture_page(TB.frame_of(doc, pno))[0], page_id=page_id)
    except Exception:
        pass
    path = os.path.join(R.RM, doc, page_id + ".rm")
    paths.write_atomic(path, PG.blank_page_bytes(path))
    return pno


def _draw_play_page(doc, state, scene, roll_line, scene_png, workdir, log=None, clear=True):
    """PAGE 2, drawn again IN PLACE: cleared, then this turn's page picture (text, frame, the space to write)
    and the scene's strokes over the frame."""
    pid = state["page_id"]
    pno = _clear_page(doc, pid) if clear else _page_no(doc, pid)
    png = os.path.join(workdir, "_adv_turn_%d.png" % int(time.time() * 1000))
    try:
        from paperdaemon.pipeline.games import inputarea as IA
        from paperdaemon.pipeline.page import images as IM
        turn_png(state, scene, png, roll_line, col_px=IA.column_px(doc, pno, PAGE_W))
        r = IA.place(doc, pno, pid, png, WRITE_TOP)                # the picture ends where the player's space begins
        IM.record_placement(r["doc"], pno, r["name"], r["box"], hash=r["hash"], kind="adventure-turn", game=state["id"])
    finally:
        try:
            os.remove(png)
        except OSError:
            pass
    if scene_png:
        n, secs = _draw_scene(doc, pno, scene_png)
        _log(log, "  adventure: the scene is %d strokes (%.0fs)" % (n, secs))
    return pno


def log_png(state, out):
    """PAGE 3: the adventure log, the newest entry at the bottom; what does not fit leaves the page (the state
    keeps every entry)."""
    from PIL import Image, ImageDraw
    im = Image.new("RGB", (PAGE_W, PAGE_H), "white")
    d = ImageDraw.Draw(im)
    M, W, LH = 80, PAGE_W - 160, 40
    reg, med, small = (_font("reMarkableSans-Regular.ttf", 30), _font("reMarkableSans-Medium.ttf", 30),
                       _font("reMarkableSans-Regular.ttf", 24))
    t0 = int(CH.TOP)                                  # below the tablet's toolbar
    d.text((M, t0), "%s  ·  the story so far" % state["title"], font=med, fill=INK)
    d.line((M, t0 + 52, M + W, t0 + 52), fill=RULE, width=3)
    blocks = []
    for e in state.get("events") or []:
        head = ("Turn %d" % e["n"]) if e["n"] else "The beginning"
        lines = [("%s  ·  %s" % (head, e.get("place") or ""), med, INK)]
        lines += [(l, reg, INK) for l in _wrap(d, e.get("text") or "", reg, W)]
        lines += [(l, small, GRAY) for l in _wrap(d, e.get("roll") or "", small, W)]
        blocks.append(lines)
    top, bottom = t0 + 80, PAGE_H - 60
    room = bottom - top - LH                     # one line kept for the note on earlier turns
    fit = []
    for b in reversed(blocks):
        need = len(b) * LH + LH // 2
        if need > room:
            break
        fit.insert(0, b)
        room -= need
    y = top
    if len(fit) < len(blocks):
        d.text((M, y), "Earlier turns are kept in the game's notes.", font=small, fill=GRAY)
        y += LH
    for b in fit:
        for text, font, col in b:
            d.text((M, y), text, font=font, fill=col)
            y += LH
        y += LH // 2
    im.save(out)
    return out


def _redraw_log(doc, state, workdir):
    """PAGE 3 again, in place."""
    pid = state.get("log_page")
    if not pid or _page_no(doc, pid) is None:
        return
    pno = _clear_page(doc, pid)
    png = os.path.join(workdir, "_adv_log_%d.png" % int(time.time() * 1000))
    try:
        log_png(state, png)
        jp = (state.get("journal_pages") or [None])[0] if is_inline(state) else None
        if jp and _page_no(doc, jp):
            # a notebook page holds no link: the journal's page number where the book had its Journal button
            from PIL import Image
            with Image.open(png) as im:
                im = im.convert("RGB")
                s = im.width / float(BOOK_W)
                _button(im, tuple(int(v * s) for v in JOURNAL_BTN), "Journal: p. %d" % _page_no(doc, jp))
                im.save(png)
        _put_full(doc, pno, pid, png, "adventure-log", state)
    finally:
        try:
            os.remove(png)
        except OSError:
            pass


# ------------------------------------------------------------------------------ the journal: a PDF beside the notebook
# The hero's journal is a page with links to a characters page, a quests page and a lore page; the characters page
# has an image of each character, a link on the image takes the reader to a page detailing that person (their class,
# if known, name, etc.). A notebook page cannot hold a link; a PDF can (rm_pdfdoc.write_pdf's GoTo links, which the
# tablet follows). So the journal is a PDF document of its own beside the notebook, rebuilt IN PLACE in the mirror
# whenever what it shows changes, and pushed with the job like everything else. It shows ONLY what the hero
# knows -- never a secret or an unrevealed class.
def journal_name(state):
    return "Ink Adventure: %s - Journal" % state["title"]


def _jr_fonts():
    return dict(title=_font("reMarkableSans-Bold.ttf", 52), head=_font("reMarkableSans-Medium.ttf", 34),
                reg=_font("reMarkableSans-Regular.ttf", 28), small=_font("reMarkableSans-Regular.ttf", 23),
                label=_font("reMarkableSans-Medium.ttf", 24))


def _portrait_img(state, p, side):
    """A cast member's portrait at side x side, or their initials when none was painted."""
    from PIL import Image, ImageDraw
    path = os.path.join(pictures_dir(state), p["portrait"]) if p.get("portrait") else None
    if path and os.path.exists(path):
        with Image.open(path) as im:
            return im.convert("RGB").resize((side, side), Image.LANCZOS)
    im = Image.new("RGB", (side, side), (236, 236, 239))
    d = ImageDraw.Draw(im)
    ini = "".join(w[0] for w in p["name"].split()[:2]).upper() or "?"
    f = _font("reMarkableSans-Medium.ttf", max(20, side // 3))
    d.text(((side - d.textlength(ini, font=f)) / 2, side / 3), ini, font=f, fill=GRAY)
    return im


def _jr_wrap_rows(rows, F, width):
    """[(label or None, text, font key)] -> wrapped lines [(text, font key, color, x offset)] for laying out pages."""
    from PIL import Image, ImageDraw
    d = ImageDraw.Draw(Image.new("RGB", (8, 8)))
    out = []
    for label, text, fk in rows:
        if label:
            out.append((label, "label", GRAY, 0))
        for line in _wrap(d, text, F[fk], width) or [""]:
            out.append((line, fk, INK if fk != "small" else GRAY, 0))
        out.append(("", "gap", INK, 0))
    return out


LINE_H = {"title": 64, "head": 46, "reg": 38, "small": 32, "label": 32, "gap": 14}


def _paginate(lines, top, bottom):
    pages, cur, y = [], [], top
    for ln in lines:
        h = LINE_H[ln[1]]
        if y + h > bottom and cur:
            pages.append(cur)
            cur, y = [], top
        cur.append(ln)
        y += h
    return pages + [cur] if cur or not pages else pages


def _journal_pages(state):
    """-> (the pages as images, {page index: [(box, target page index)]})."""
    from paperdaemon.pipeline.page import pdf as PD
    from PIL import Image, ImageDraw
    W, H = PD.PAGE_W, PD.PAGE_H
    F = _jr_fonts()
    M = 70
    # EVERY PAGE STARTS BELOW THE TABLET'S TOOLBAR: the layout below was drawn from y 58; it moves down
    # by DY to the top of this page's safe area
    try:
        from paperdaemon.pipeline import page as P_
        DY = max(0, int(round(P_.safe_area((W, H))[1])) - 58)
    except Exception:
        DY = 81
    hcm = state["hero"].get("height_cm")
    people = sorted((state.get("cast") or {}).values(), key=lambda p: (p["met"]["turn"], p["name"]))
    quests = sorted(state.get("quests") or [], key=lambda q: (q["status"] != "open", q.get("turn", 0)))
    lore = state.get("lore") or []
    PER = 9
    n_grid = max(1, -(-len(people) // PER))
    q_rows = []
    for q in quests:
        q_rows.append((None, "%s  ·  %s" % (q["name"], q["status"]), "head"))
        if q.get("goal"):
            q_rows.append((None, q["goal"], "reg"))
        for u in q.get("updates", [])[-4:]:
            q_rows.append((None, u, "small"))
    q_pages = _paginate(_jr_wrap_rows(q_rows or [(None, "No quests yet.", "reg")], F, W - 2 * M), 180 + DY, H - 80)
    l_pages = _paginate(_jr_wrap_rows([(None, ("Turn %d: " % x["turn"] if x.get("turn") else "") + x["text"], "reg")
                                       for x in lore] or [(None, "Nothing learned yet.", "reg")], F, W - 2 * M), 180 + DY, H - 80)
    i_grid, i_person = 1, 1 + n_grid
    i_quests = i_person + len(people)
    i_lore = i_quests + len(q_pages)
    pages, links = [], {}

    def page(title, back=True):
        im = Image.new("RGB", (W, H), "white")
        d = ImageDraw.Draw(im)
        d.text((M, 58 + DY), title, font=F["title"], fill=INK)
        d.line((M, 138 + DY, W - M, 138 + DY), fill=RULE, width=3)
        idx = len(pages)
        links[idx] = []
        if back:
            box = (W - 300, 60 + DY, W - M, 122 + DY)
            d.rounded_rectangle(box, 14, outline=INK, width=3)
            d.text((box[0] + 30, box[1] + 12), "Contents", font=F["head"], fill=INK)
            links[idx].append((box, 0))
        return im, d, idx

    def draw_lines(d, lines, y):
        for text, fk, col, dx in lines:
            if fk != "gap":
                d.text((M + dx, y), text, font=F[fk], fill=col)
            y += LINE_H[fk]
        return y

    # 0 -- contents
    im, d, idx = page(state["title"], back=False)
    d.text((M, 170 + DY), "%s's journal: %s." % (state["hero"]["name"], "each heading's page is beside it" if is_inline(state)
                                                  else "tap a heading"), font=F["reg"], fill=GRAY)
    y = 250 + DY
    for name, sub, target in (("Characters", "%d met" % len(people), i_grid),
                              ("Quests", "%d open, %d in all" % (sum(q["status"] == "open" for q in quests), len(quests)), i_quests),
                              ("Lore", "%d thing%s learned" % (len(lore), "" if len(lore) == 1 else "s"), i_lore)):
        box = (M, y, W - M, y + 210)
        d.rounded_rectangle(box, 26, outline=INK, width=4)
        d.text((M + 44, y + 42), name, font=F["title"], fill=INK)
        d.text((M + 44, y + 124), sub, font=F["reg"], fill=GRAY)
        links[idx].append((box, target))
        y += 260
    pages.append(im)
    # the characters, nine to a page, each portrait a link to that person's page
    tile = (W - 2 * M) // 3
    side = tile - 40
    for g in range(n_grid):
        im, d, idx = page("Characters" + ("  (%d of %d)" % (g + 1, n_grid) if n_grid > 1 else ""))
        chunk = people[g * PER:(g + 1) * PER]
        if not chunk:
            d.text((M, 180 + DY), "Nobody yet.", font=F["reg"], fill=GRAY)
        for k, p in enumerate(chunk):
            r, c = divmod(k, 3)
            x0, y0 = M + c * tile + 20, 175 + DY + r * (side + 110)
            im.paste(_portrait_img(state, p, side), (x0, y0))
            d.rectangle((x0, y0, x0 + side, y0 + side), outline=RULE, width=2)
            tw = d.textlength(p["name"], font=F["head"])
            d.text((x0 + (side - tw) / 2, y0 + side + 10), p["name"], font=F["head"], fill=INK)
            sub = p["status"] if p["status"] != "alive" else p["disposition"]
            sw = d.textlength(sub, font=F["small"])
            d.text((x0 + (side - sw) / 2, y0 + side + 56), sub, font=F["small"], fill=GRAY)
            links[idx].append(((x0, y0, x0 + side, y0 + side + 90), i_person + g * PER + k))
        pages.append(im)
    # a page per person: what the hero has seen and learned, nothing more
    for k, p in enumerate(people):
        im, d, idx = page(p["name"])
        ps = 560
        im.paste(_portrait_img(state, p, ps), ((W - ps) // 2, 165 + DY))
        d.rectangle(((W - ps) // 2, 165 + DY, (W + ps) // 2, 165 + DY + ps), outline=RULE, width=2)
        kn = p.get("known") or {"fields": [], "facts": []}
        f = set(kn.get("fields") or [])
        cls = "unknown"
        if "class" in f:
            cls = p["class"] + ((", level %d" % p["level"]) if "level" in f else "")
        rows = [("Who", p["role"] or "a stranger", "reg"),
                ("Looks", person_look(p, hcm).split(": ", 1)[-1], "reg"),
                ("Now", "%s, %s%s" % (p["status"], p["disposition"], ("; " + ", ".join(p["conditions"])) if p["conditions"] else ""), "reg"),
                ("Class", cls, "reg"),
                ("Alignment", p["alignment"] if "alignment" in f else "unknown", "reg")]
        if "personality" in f:
            rows.append(("Personality", p["personality"] or "-", "reg"))
        if "backstory" in f:
            rows.append(("Backstory", p["backstory"] or "-", "reg"))
        rows.append(("Record", ("; ".join(p["criminal_record"]) or "none") if "record" in f else "unknown", "reg"))
        rows.append(("What you know", "; ".join(kn.get("facts") or []) or "nothing yet", "reg"))
        rows.append(("Met", "turn %d at %s; last seen turn %d at %s" % (p["met"]["turn"], p["met"]["place"] or "?",
                                                                       p["last_seen"]["turn"], p["last_seen"]["place"] or "?"), "small"))
        lines = _jr_wrap_rows(rows, F, W - 2 * M)
        fit = _paginate(lines, 165 + DY + ps + 30, H - 140)[0]
        draw_lines(d, fit, 165 + DY + ps + 30)
        back = (M, H - 115, M + 420, H - 50)
        d.rounded_rectangle(back, 14, outline=INK, width=3)
        d.text((back[0] + 30, back[1] + 14), "All characters", font=F["head"], fill=INK)
        links[idx].append((back, i_grid + k // PER))
        pages.append(im)
    for title, chunks in (("Quests", q_pages), ("Lore", l_pages)):
        for t, chunk in enumerate(chunks):
            im, d, idx = page(title + ("  (%d of %d)" % (t + 1, len(chunks)) if len(chunks) > 1 else ""))
            draw_lines(d, chunk, 180 + DY)
            pages.append(im)
    return pages, links


def update_journal(state, log=None):
    """Rebuild the journal PDF when what it shows changed, and update it in place on the tablet (a new one the first
    time). Never fails a turn: a journal that could not be made is logged and tried again next turn."""
    try:
        import hashlib
        from paperdaemon.pipeline.page import pdf as PD
        sig = hashlib.sha1(json.dumps([state.get("title"), state.get("cast"), state.get("quests"), state.get("lore")],
                                      sort_keys=True, default=str).encode()).hexdigest()
        jr = state.get("journal") or {}
        if jr.get("sig") == sig and jr.get("doc"):
            return
        pages, links = _journal_pages(state)
        out_dir = os.path.join(paths.state_dir(), "rm-pdfdoc")
        os.makedirs(out_dir, exist_ok=True)
        pdf = PD.write_pdf(pages, os.path.join(out_dir, "journal-%s.pdf" % state["id"]), links=links)
        meta = json.load(open(os.path.join(PD.MIRROR, state["doc"] + ".metadata"), encoding="utf-8"))
        # staged in the mirror only: it reaches the tablet with the job's own push (sync.push_pending)
        doc, page_ids = PD.stage(journal_name(state), pdf, folder=meta.get("parent") or "", doc=jr.get("doc"),
                                 page_ids=jr.get("page_ids"))
        state["journal"] = {"doc": doc, "page_ids": {str(k): v for k, v in page_ids.items()}, "sig": sig, "pages": len(pages)}
        _log(log, "  adventure: the journal is %d pages" % len(pages))
    except Exception as ex:
        _log(log, "  adventure: the journal was not updated: %s: %s" % (type(ex).__name__, str(ex)[:160]))


# ------------------------------------------------------------------------------ THE BOOK: the whole game, one PDF
# The journal belongs in the same document as the adventure, and is maintained there too. A link lives only in a
# PDF, and a notebook cannot hold PDF pages -- so a game is ONE PDF-backed document: page 1 the sheet, 2 the scene
# (its frame and text the PDF page, the scene's strokes and the player's writing the page's ink), 3 the log, 4+ the
# journal, its pages linked to each other, the log's "Journal" button to the journal and the journal's "The story"
# button back to the scene. Every turn rebuilds the PDF IN PLACE (page ids kept); only page 2's ink is cleared and
# drawn again. A PDF page is 1404 x 1872 page units, the notebook's 1620 x 2160 at 0.8667 (both 3:4, x centered), so
# every picture and stroke is the notebook's, scaled.
BOOK_W, BOOK_H = 1404, 1872
BK = BOOK_W / float(PAGE_W)
JOURNAL_BTN = (BOOK_W - 300, 22, BOOK_W - 50, 82)      # the log page's way into the journal, above its title rule


def is_book(state):
    return state.get("format") == "book"


def _bk(png):
    from PIL import Image
    with Image.open(png) as im:
        return im.convert("RGB").resize((BOOK_W, BOOK_H), Image.LANCZOS)


def _button(im, box, text):
    from PIL import ImageDraw
    d = ImageDraw.Draw(im)
    d.rounded_rectangle(box, 14, fill="white", outline=INK, width=3)
    f = _font("reMarkableSans-Medium.ttf", 32)
    d.text((box[0] + (box[2] - box[0] - d.textlength(text, font=f)) / 2, box[1] + 12), text, font=f, fill=INK)


def _book_pages(state, scene, roll_line, workdir, n=None):
    """Every page of the book as pictures, and its links: 1 sheet, 2 scene, 3 log, 4+ the journal."""
    out = []
    for name, draw in (("sheet", lambda p: sheet_png(state, p)), ("turn", lambda p: turn_png(state, scene, p, roll_line, n)),
                       ("log", lambda p: log_png(state, p))):
        png = os.path.join(workdir, "_adv_%s_%d.png" % (name, int(time.time() * 1000)))
        try:
            draw(png)
            out.append(_bk(png))
        finally:
            try:
                os.remove(png)
            except OSError:
                pass
    jr, jr_links = _journal_pages(state)
    links = {i + 3: [(box, t + 3) for box, t in ls] for i, ls in jr_links.items()}
    journal_btn = JOURNAL_BTN
    _button(out[2], journal_btn, "Journal")
    links[2] = [(journal_btn, 3)]
    story_btn = (BOOK_W - 330, 60, BOOK_W - 70, 122)
    _button(jr[0], story_btn, "The story")
    links.setdefault(3, []).append((story_btn, 1))
    return out + jr, links


def _write_book(doc, state, pages, links, name=None, parent=None, reset=()):
    """The book's files in the mirror: its PDF (rewritten in place), one page entry per page with the SAME ids turn
    after turn, a blank ink layer for every new page and for each page in `reset`; every other page's ink is kept."""
    import uuid
    from paperdaemon.remarkable import library as P
    from paperdaemon.pipeline.page import pdf as PD
    M_ = PD.MIRROR
    ids = state.setdefault("book_pages", [])
    while len(ids) < len(pages):
        ids.append(str(uuid.uuid4()))
    del ids[len(pages):]
    state["sheet"] = dict(state.get("sheet") or {}, page_id=ids[0])
    state["page_id"], state["log_page"] = ids[1], ids[2]
    state["pages"] = list(ids)
    state.pop("journal", None)
    # THE GAME IS SAVED BEFORE ITS PAGES EXIST: the daemon sees new pages the moment they land in the mirror, and a
    # job that found no game behind them would take the ordinary path -- an arrow search over the scene's tens of
    # thousands of strokes that can run for many minutes
    CH.save_state(state)
    pdf = os.path.join(M_, doc + ".pdf")
    PD.write_pdf(pages, pdf + ".tmp", links=links)
    os.replace(pdf + ".tmp", pdf)
    _, blank = PD.find_template()
    ddir = os.path.join(M_, doc)
    os.makedirs(ddir, exist_ok=True)
    entries, idxv = [], "ba"
    for i, pid in enumerate(ids):
        f = os.path.join(ddir, pid + ".rm")
        if pid in reset or not os.path.exists(f):
            paths.write_atomic(f, blank)
        entries.append({"id": pid, "idx": {"timestamp": "1:2", "value": idxv}, "redir": {"timestamp": "1:2", "value": i},
                        "template": {"timestamp": "1:2", "value": "Blank"}})
        idxv = P.next_idx(idxv)
    cp = os.path.join(M_, doc + ".content")
    c = json.load(open(cp, encoding="utf-8")) if os.path.exists(cp) else {
        "coverPageNumber": 0, "customZoomCenterX": 0, "customZoomCenterY": BOOK_H // 2, "customZoomOrientation": "portrait",
        "customZoomPageHeight": BOOK_H, "customZoomPageWidth": BOOK_W, "customZoomScale": 1, "extraMetadata": {},
        "fileType": "pdf", "fontName": "", "formatVersion": 2, "lineHeight": -1, "orientation": "portrait", "pageTags": [],
        "tags": [], "textAlignment": "justify", "textScale": 1, "zoomMode": "bestFit"}
    c["cPages"] = {"lastOpened": {"timestamp": "1:1", "value": ids[1]}, "original": {"timestamp": "1:1", "value": len(ids)},
                   "pages": entries}
    c["pageCount"] = len(ids)
    c["sizeInBytes"] = str(os.path.getsize(pdf))
    c["documentMetadata"] = {"title": name or "Ink Adventure: %s" % state["title"]}
    paths.write_json_atomic(cp, c)
    mp =os.path.join(M_, doc + ".metadata")
    now = str(int(time.time() * 1000))
    md = json.load(open(mp, encoding="utf-8")) if os.path.exists(mp) else {
        "createdTime": now, "lastOpened": now, "lastOpenedPage": 1, "new": False, "pinned": False, "source": "",
        "type": "DocumentType", "visibleName": name or "Ink Adventure: %s" % state["title"], "parent": parent or ""}
    md["lastModified"] = now
    paths.write_json_atomic(mp, md)
    paths.write_atomic(os.path.join(M_, doc + ".pagedata"), "Blank\n" * len(ids))


def _draw_scene_book(doc, scene_png):
    """The scene's strokes onto the book's page 2, in the PDF page's units."""
    from paperdaemon.pipeline import draw as A
    from paperdaemon.pipeline import decompose as M
    x0, y0, x1, y1 = scene_frame_page()
    strokes, info, secs = M.decompose_into(scene_png, int((x1 - x0) * BK), int((y1 - y0) * BK), origin=(x0 * BK, y0 * BK))
    d = A.Drawing(BOOK_W, BOOK_H)
    d.strokes = list(strokes)
    d.write_rm(doc, 2, keep_existing=True)
    return len(strokes), secs


def _render_book(doc, state, scene, roll_line, scene_png, workdir, log=None, name=None, parent=None, n=None):
    """The whole book again: every page's picture rebuilt in place, page 2's ink cleared and the scene drawn."""
    pages, links = _book_pages(state, scene, roll_line, workdir, n)
    _write_book(doc, state, pages, links, name=name, parent=parent,
                reset=[state["page_id"]] if state.get("book_pages") else ())
    if scene_png:
        k, secs = _draw_scene_book(doc, scene_png)
        _log(log, "  adventure: the scene is %d strokes (%.0fs)" % (k, secs))
    _log(log, "  adventure: the book is %d pages (journal %d)" % (len(pages), len(pages) - 3))


def _fixed(doc, state, log=None):
    """A game saved with the older page layout: it plays on IN PLACE on its current page, and gets its log page once
    (its earlier turns become the log's first entries)."""
    if state.get("layout") == "fixed" and state.get("log_page"):
        return
    from paperdaemon.remarkable import library as PG
    from paperdaemon.pipeline.page import render as R
    pid = PG.insert_pages(doc, state["page_id"], 1)[0][0]      # the log right after the page it is played on
    state["log_page"] = pid
    state.setdefault("pages", []).append(pid)
    state.setdefault("cast", {})
    state.setdefault("present", [])
    if not state.get("events"):
        state["events"] = [{"n": t["n"] - 1, "place": t["scene"].get("place") or "",
                            "text": _s(t["scene"].get("what_happened"), 300), "roll": ""} for t in state["turns"]]
    state["layout"] = "fixed"
    _log(log, "  adventure: fixed pages from now on; the log is page %d" % _page_no(doc, pid))


def _redraw_sheet(doc, state, workdir):
    """PAGE 1 again, when the hero changed: the old sheet picture off, the new one on."""
    from paperdaemon.pipeline.page import images as IM
    from paperdaemon.pipeline.page import render as R
    sh = state["sheet"]
    live = [p["id"] for p in R.live_pages(doc)]
    if sh.get("page_id") not in live:
        return
    pno = live.index(sh["page_id"]) + 1
    if sh.get("box"):
        try:
            IM.remove_in_box(doc, pno, tuple(sh["box"]), page_id=sh["page_id"])
        except Exception:
            pass
    png = os.path.join(workdir, "_adv_sheet_%d.png" % int(time.time() * 1000))
    try:
        sheet_png(state, png)
        state["sheet"] = _put_full(doc, pno, sh["page_id"], png, "adventure-sheet", state)
    finally:
        try:
            os.remove(png)
        except OSError:
            pass


# ------------------------------------------------------------------------------ INLINE: the game in the user's notebook
# Where a game is asked for, it is played: the scene on the page that asked (start(here=True)), its other pages RIGHT
# AFTER it, in the same notebook (or PDF), and the pages behind move down. Each new page gets an ordering key between its neighbors'
# (library.insert_pages), so no other page changes -- a PDF's own pages keep their place in its file, and its links
# still land where they did. Page 1 the sheet, 2 the scene, 3 the log, 4+ the journal, each a page picture (the
# scene's strokes over its frame), drawn again in place turn after turn. A notebook page cannot hold a link, so the
# journal's links become page numbers ("p. 12") beside what was tappable in the book.
def is_inline(state):
    return state.get("format") == "inline"


def _label(im, box, text):
    """A page number beside a box that was a link in the book: inside a big box at its bottom right; to the right
    of a small one (a button), or under it when the page has no room there."""
    from PIL import ImageDraw
    d = ImageDraw.Draw(im)
    f = _font("reMarkableSans-Medium.ttf", 26)
    w = d.textlength(text, font=f)
    if box[3] - box[1] >= 120:
        x0, y0 = box[2] - w - 22, box[3] - 42
    elif box[2] + w + 34 <= im.width - 20:
        x0, y0 = box[2] + 12, (box[1] + box[3]) / 2.0 - 18
    else:
        x0, y0 = box[2] - w - 16, box[3] + 8
    d.rounded_rectangle((x0, y0, x0 + w + 16, y0 + 36), 8, fill="white", outline=INK, width=2)
    d.text((x0 + 8, y0 + 3), text, font=f, fill=INK)


def _inline_journal(doc, state, workdir, log=None, force=False):
    """The journal's pages, after the log page: as many as it needs (pages added after the last of them, or taken
    back), each drawn again when what the journal shows changed."""
    import hashlib
    from paperdaemon.remarkable import library as PG
    try:
        sig = hashlib.sha1(json.dumps([state.get("title"), state.get("cast"), state.get("quests"), state.get("lore")],
                                      sort_keys=True, default=str).encode()).hexdigest()
        if not force and state.get("journal_sig") == sig:
            return
        pages, links = _journal_pages(state)
        ids = [p for p in (state.get("journal_pages") or []) if _page_no(doc, p)]
        if len(ids) < len(pages):
            after = ids[-1] if ids else state["log_page"]
            ids += [pid for pid, _ in PG.insert_pages(doc, after, len(pages) - len(ids))]
        elif len(ids) > len(pages):
            PG.delete_pages(doc, ids[len(pages):])
            ids = ids[:len(pages)]
        state["journal_pages"] = ids
        state["pages"] = [state["sheet"]["page_id"], state["page_id"], state["log_page"]] + ids
        CH.save_state(state)
        nums = [_page_no(doc, p) for p in ids]
        for i, (im, pid) in enumerate(zip(pages, ids)):
            im = im.convert("RGB")
            for box, target in links.get(i) or []:
                if 0 <= target < len(nums) and nums[target]:
                    _label(im, box, "p. %d" % nums[target])
            pno = _clear_page(doc, pid)
            png = os.path.join(workdir, "_adv_journal_%d_%d.png" % (i, int(time.time() * 1000)))
            try:
                im.save(png)
                _put_full(doc, pno, pid, png, "adventure-journal", state)
            finally:
                try:
                    os.remove(png)
                except OSError:
                    pass
        state["journal_sig"] = sig
        _log(log, "  adventure: the journal is %d pages, from page %d" % (len(ids), nums[0] if nums else 0))
    except Exception as ex:
        _log(log, "  adventure: the journal was not updated: %s: %s" % (type(ex).__name__, str(ex)[:160]))


def _start_inline(doc, after, state, scene, kept, workdir, log, here=False):
    """The game's first pages: the scene, the sheet, the log, then the journal. `here`: the scene is played on the
    page that asked (`after`) and the sheet and the log follow it; else all of them go right after that page."""
    from paperdaemon.remarkable import library as PG
    if here:
        sheet, logp = [pid for pid, _ in PG.insert_pages(doc, after, 2)]
        ids = [after, sheet, logp]
        state["sheet"] = {"page_id": sheet, "hash": None, "box": None}
        state["page_id"], state["log_page"] = after, logp
    else:
        ids = [pid for pid, _ in PG.insert_pages(doc, after, 3)]
        state["sheet"] = {"page_id": ids[0], "hash": None, "box": None}
        state["page_id"], state["log_page"] = ids[1], ids[2]
    state["pages"], state["journal_pages"] = list(ids), []
    # THE GAME IS SAVED BEFORE ITS PAGES ARE DRAWN: a job on one of them must find the game behind it
    CH.save_state(state)
    png = os.path.join(workdir, "_adv_sheet_%d.png" % int(time.time() * 1000))
    try:
        sheet_png(state, png)
        state["sheet"] = _put_full(doc, _page_no(doc, ids[0]), ids[0], png, "adventure-sheet", state)
    finally:
        try:
            os.remove(png)
        except OSError:
            pass
    _draw_play_page(doc, state, scene, "", kept, workdir, log, clear=False)
    _inline_journal(doc, state, workdir, log, force=True)
    _redraw_log(doc, state, workdir)


# ------------------------------------------------------------------------------ a new adventure
def start(what, ask_text, paint=None, log=None, workdir=None, parent=None, doc=None, after=None, here=False):
    """A new Ink Adventure: the model invents the adventure, the hero and the people of the opening scene, the
    engine rolls them, and the game's pages go right after the page `after` of the notebook `doc` that asked (the
    sheet, the opening scene, the log, the journal; see INLINE). Without `doc`, a book of its own (an older caller).
    -> (state, doc)."""
    from paperdaemon.remarkable import library as PG
    from paperdaemon.pipeline.page import render as R
    workdir = workdir or os.path.join(paths.state_dir(), "rm-queue")
    os.makedirs(workdir, exist_ok=True)
    spec = parse_json(ask_text(SETUP_PROMPT.format(what=str(what)[:400], races=", ".join(RACES), classes=", ".join(CLASSES),
                                                   skills=", ".join(SKILLS), person=PERSON_JSON))) if ask_text else {}
    if not spec.get("hero"):
        spec = {"title": "The Lantern Road", "premise": "A road that only appears at night.", "tone": "eerie",
                "hero": {"name": "Wren", "race": "halfling", "class": "rogue"},
                "opening": {"place": "a crossroads at dusk", "what_happened": "You wake at a crossroads as the sun goes down.",
                            "around": "Four roads, a signpost with no words, a lantern hanging from it.",
                            "options": ["take the lantern", "read the signpost", "pick a road"],
                            "picture": "a crossroads at dusk with a blank wooden signpost and a lit lantern hanging from it"}}
    seed = CH.new_seed()
    rng = CH.Rng(seed)
    hero = make_hero(spec["hero"], rng)
    title = str(spec.get("title") or "An Ink Adventure")[:60]
    import uuid
    inline = bool(doc and after)
    # INLINE in the notebook that asked; else THE BOOK, one PDF document of its own, made below by _render_book
    doc = doc if inline else str(uuid.uuid4())
    state = new_state(doc, title, str(spec.get("premise") or "")[:400], str(spec.get("tone") or "")[:60], hero, seed=seed)
    state["rng"] = rng.state()
    if inline:
        state["format"] = "inline"
    else:
        state["format"], state["book_pages"] = "book", []
    op = spec.get("opening") or {}
    scene = {"place": str(op.get("place") or "")[:80], "what_happened": str(op.get("what_happened") or "")[:1200],
             "around": str(op.get("around") or "")[:500], "options": [str(o)[:80] for o in (op.get("options") or [])][:4]}
    rng = CH.Rng(**state["rng"])
    present = add_people(state, op.get("people"), rng, 1, scene["place"])
    state["rng"] = rng.state()
    place_of(state, scene["place"], op.get("picture") or scene["around"])

    def pictures():
        _portraits(paint, state, present, log)
        return _paint_scene(paint, state, {"mode": "new", "prompt": op.get("picture") or scene["around"]}, None,
                            present, present, log, fallback=scene["around"])
    pic = _with_card(paint, pictures) if paint else None
    kept = _keep(state, 1, pic) if pic else None
    if pic:
        try:
            os.remove(pic)
        except OSError:
            pass
    state["place"] = scene["place"]
    state["present"] = [p["name"] for p in present]
    state["events"] = [{"n": 0, "place": scene["place"], "text": _s(scene["what_happened"], 300), "roll": ""}]
    if inline:
        _start_inline(doc, after, state, scene, kept, workdir, log, here=here)
    else:
        _render_book(doc, state, scene, "", kept, workdir, log, parent=parent or "", n=1)
    state["turns"].append({"n": 1, "page_id": state["page_id"], "scene": scene,
                           "picture": os.path.basename(kept) if kept else None, "action": None, "check": None, "notes": []})
    CH.save_state(state)
    _log(log, "  adventure: %s started (%s)" % (title, hero_line(hero)[:120]))
    return state, doc


# ------------------------------------------------------------------------------ one turn
def read_action(doc, page_no, ask_vision, workdir, names=()):
    """What the player answered under the turn page's picture -> text, or '': what they typed, then what they
    handwrote in the space (inputarea.read). `names`: the story's names, so the reader reads a handwritten name as
    the name it is."""
    from paperdaemon.pipeline.games import inputarea as IA
    s = TB.picture_page(TB.frame_of(doc, page_no))[1]
    return IA.read(doc, page_no, WRITE_TOP * s, ask_vision, READ_PROMPT.format(names=", ".join(names) or "none yet"),
                   "ACTION", workdir)


def turn(doc, page_no, page_id, state, ask_text, ask_vision, paint=None, log=None, workdir=None):
    """One turn: read what the player wrote, rule on it against the picture, roll, tell what happens, apply
    what changed (the hero's and the cast's, through the engine), and draw the next scene on the SAME page,
    the log on page 3. -> (outcome, note)."""
    workdir = workdir or os.path.join(paths.state_dir(), "rm-queue")
    if state["status"] != "playing":
        return "skipped", "the adventure is over (%s)" % state["status"]
    if page_id != state["page_id"]:
        return "skipped", "ink adventure: an earlier page; the story goes on at the last one"
    if ask_vision is None or ask_text is None:
        return "skipped", "ink adventure: the model is not answering, so nobody can read the page"
    action = fix_names(state, read_action(doc, page_no, ask_vision, workdir, known_names(state)))
    if not action:
        return "skipped", "ink adventure: nothing typed or written under the page yet"
    _fixed(doc, state, log)
    last = state["turns"][-1]
    scene = last["scene"]
    shot = os.path.join(pictures_dir(state), last["picture"]) if last.get("picture") else None
    h = state["hero"]
    here = [n for n in (state.get("present") or []) if n in (state.get("cast") or {})]
    rule_q = RULE_PROMPT.format(hero=hero_line(h), place=state["place"] or "unknown", around=scene.get("around", ""),
                                people=cast_block(state, here) if here else "- nobody the story has met",
                                events=events_block(state, 6), action=action[:300], skills=", ".join(SKILLS),
                                abilities=", ".join(ABILITIES))
    rule = parse_json(ask_vision(rule_q, shot) if shot and os.path.exists(shot) else ask_text(rule_q)) or {}
    possible = rule.get("possible", True) is not False
    result, roll_line = None, ""
    ck = rule.get("check") if possible else None
    if isinstance(ck, dict) and ck.get("key"):
        try:
            # AN ATTACK ON SOMEONE THE STORY KNOWS: their armor is the DC, and the damage is theirs (the engine's)
            target = find_person(state, ck.get("target")) if str(ck.get("kind")) == "attack" else None
            result = check(state, str(ck.get("kind") or "skill"), str(ck["key"]).lower() if ck.get("kind") == "skill" else str(ck["key"]).upper(),
                           target["ac"] if target else int(ck.get("dc") or 12), int(ck.get("advantage") or 0))
            roll_line = describe_check(result)
            if target and result.get("damage"):
                hurt(target, result["damage"])
                result["target"] = target["name"]
                roll_line += "; %s at %d/%d hit points" % (target["name"], target["hp"]["now"], target["hp"]["max"])
        except (ValueError, KeyError) as ex:
            _log(log, "  adventure: the check was not understood: %s" % ex)
    if not possible:
        roll = "It cannot be done: %s" % (rule.get("why_not") or "the scene does not allow it")
    elif result:
        roll = "The engine rolled: %s." % roll_line
    else:
        roll = "No roll was needed: it simply happens."
    tell = parse_json(ask_text(TELL_PROMPT.format(title=state["title"], premise=state["premise"], tone=state["tone"],
                                                  hero=hero_line(h), look=hero_look(h), cast=cast_block(state),
                                                  events=events_block(state), place=state["place"] or "unknown",
                                                  around=scene.get("around", ""), action=action[:300],
                                                  understood=rule.get("understood") or action[:200], roll=roll,
                                                  person=PERSON_JSON, statuses=", ".join(STATUSES),
                                                  dispositions=", ".join(DISPOSITIONS), lore=lore_block(state),
                                                  quests=quests_line(state), fields=", ".join(KNOWABLE)))) or {}
    allowed = list(rule.get("uses") or []) if possible else []
    if result and result["success"]:
        allowed += [g.get("name") if isinstance(g, dict) else g for g in ((tell.get("changes") or {}).get("gain") or [])]
    notes = apply(state, tell.get("changes") or {}, allowed)
    if result and result.get("damage"):
        notes.append("dealt %d damage" % result["damage"])
    if tell.get("over") in ("death", "victory"):
        state["status"] = tell["over"]
    new_scene = {"place": str(tell.get("place") or state["place"])[:80],
                 "what_happened": str(tell.get("what_happened") or "")[:1200],
                 "around": str(tell.get("around") or "")[:500],
                 "options": [str(o)[:80] for o in (tell.get("options") or [])][:4]}
    n = len(state["turns"]) + 1
    # THE CAST, through the engine: newcomers rolled and recorded once, changes checked, looks never touched
    rng = CH.Rng(**state["rng"])
    newcomers = add_people(state, tell.get("new_people"), rng, n, new_scene["place"])
    people_notes = apply_people(state, tell.get("people_changes"), rng, n, new_scene["place"])
    people_notes += apply_story(state, tell, n - 1)
    state["rng"] = rng.state()
    present = [p for p in (find_person(state, x) for x in (tell.get("present") or [])) if p]
    present += [p for p in newcomers if p not in present]
    for p in present:
        p["last_seen"] = {"turn": n, "place": new_scene["place"]}
    pic_spec = tell.get("picture") or {"mode": "new", "prompt": new_scene["around"]}
    if not tell.get("same_place"):
        pic_spec = dict(pic_spec, mode="new")
    # the place as it was FIRST seen: an earlier turn there (a game from before places were kept), else this
    # turn's own words for a new place
    first_there = next((t["scene"].get("around") for t in state["turns"] if t["scene"].get("place") == new_scene["place"]), "")
    setting = place_of(state, new_scene["place"], first_there or (pic_spec.get("prompt") if pic_spec.get("mode") == "new"
                                                                  else new_scene["around"]))

    def pictures():
        _portraits(paint, state, newcomers, log)
        return _paint_scene(paint, state, pic_spec, shot, present, newcomers, log, fallback=new_scene["around"],
                            setting=setting)
    pic = _with_card(paint, pictures) if paint else None
    kept = _keep(state, n, pic) if pic else None
    last["action"], last["check"], last["notes"], last["understood"] = action, result, notes, rule.get("understood")
    if notes:
        roll_line = (roll_line + "  ·  " if roll_line else "") + "; ".join(notes)
    if people_notes:
        roll_line = (roll_line + "  ·  " if roll_line else "") + "; ".join(people_notes[:3])
    state.setdefault("events", []).append({"n": n - 1, "place": state["place"] or new_scene["place"],
                                           "text": _s(tell.get("log") or new_scene["what_happened"], 300), "roll": roll_line})
    if is_book(state):
        _render_book(doc, state, new_scene, roll_line, kept, workdir, log, n=n)
    else:
        _draw_play_page(doc, state, new_scene, roll_line, kept, workdir, log)
    if pic:
        try:
            os.remove(pic)
        except OSError:
            pass
    state["place"] = new_scene["place"]
    state["present"] = [p["name"] for p in present]
    state["turns"].append({"n": n, "page_id": state["page_id"], "scene": new_scene,
                           "picture": os.path.basename(kept) if kept else None,
                           "action": None, "check": None, "notes": [], "picture_mode": pic_spec.get("mode")})
    if not is_book(state):
        if is_inline(state):
            _inline_journal(doc, state, workdir, log)     # first: the log shows the journal's page number
        _redraw_log(doc, state, workdir)
        if notes or result:
            _redraw_sheet(doc, state, workdir)
        if not is_inline(state):
            update_journal(state, log)
    CH.save_state(state)
    return "done", "ink adventure turn %d: %s%s" % (n - 1, action[:80], (" (%s)" % roll_line) if roll_line else "")


def hero_line(h):
    return ("%s, a level %d %s %s (%s); %d/%d hit points, armor %d; carries %s; %s" % (
        h["name"], h["level"], h["race"], h["class"], h["background"], h["hp"]["now"], h["hp"]["max"], h["ac"],
        ", ".join(it["name"] for it in h["inventory"]) or "nothing",
        ("conditions: " + ", ".join(h["conditions"])) if h["conditions"] else "no conditions"))
