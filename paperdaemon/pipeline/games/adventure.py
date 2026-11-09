r"""Ink Adventure: a text adventure on the tablet, game-mastered by the model.

  PAGE 1   the hero's character sheet, D&D style: abilities, saves, hit points, armor, magic, the skills
           (one list, every entry with a proper name: trained skills, special abilities, spells with their
           cost in magic points), the inventory -- drawn again whenever it changes
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
# kit, gold, spells (SPELLS keys), features (FEATS keys: the class's special abilities)
CLASSES = {
    "barbarian": dict(die=12, order=("STR", "CON", "DEX", "WIS", "CHA", "INT"), saves=("STR", "CON"), n=2,
                      skills=("animal handling", "athletics", "intimidation", "nature", "perception", "survival"),
                      armor=("unarmored (10 + DEX + CON)", 10, "unarmored"), shield=False, weapon=("greataxe", "1d12", "STR"),
                      kit=["greataxe", "two handaxes", "explorer's pack", "four javelins"], gold=10, spells=[],
                      features=["Rage", "Unarmored Defense"]),
    "bard": dict(die=8, order=("CHA", "DEX", "CON", "WIS", "INT", "STR"), saves=("DEX", "CHA"), n=3, skills=tuple(SKILLS),
                 armor=("leather armor", 11, "full"), shield=False, weapon=("rapier", "1d8", "DEX"),
                 kit=["rapier", "lute", "leather armor", "dagger", "entertainer's pack"], gold=15,
                 spells=["vicious mockery", "minor illusion", "healing word", "charm person", "sleep"],
                 features=["Bardic Inspiration"]),
    "cleric": dict(die=8, order=("WIS", "CON", "STR", "CHA", "INT", "DEX"), saves=("WIS", "CHA"), n=2,
                   skills=("history", "insight", "medicine", "persuasion", "religion"),
                   armor=("scale mail", 14, "max2"), shield=True, weapon=("mace", "1d6", "STR"),
                   kit=["mace", "scale mail", "shield", "holy symbol", "priest's pack"], gold=15,
                   spells=["sacred flame", "guidance", "cure wounds", "bless", "guiding bolt"],
                   features=[]),
    "druid": dict(die=8, order=("WIS", "CON", "DEX", "INT", "CHA", "STR"), saves=("INT", "WIS"), n=2,
                  skills=("arcana", "animal handling", "insight", "medicine", "nature", "perception", "religion", "survival"),
                  armor=("leather armor", 11, "full"), shield=True, weapon=("scimitar", "1d6", "DEX"),
                  kit=["scimitar", "wooden shield", "leather armor", "druidic focus", "explorer's pack"], gold=10,
                  spells=["druidcraft", "produce flame", "entangle", "healing word", "speak with animals"],
                  features=["Druidic"]),
    "fighter": dict(die=10, order=("STR", "CON", "DEX", "WIS", "CHA", "INT"), saves=("STR", "CON"), n=2,
                    skills=("acrobatics", "animal handling", "athletics", "history", "insight", "intimidation", "perception", "survival"),
                    armor=("chain mail", 16, None), shield=True, weapon=("longsword", "1d8", "STR"),
                    kit=["longsword", "shield", "chain mail", "light crossbow and 20 bolts", "dungeoneer's pack"], gold=10,
                    spells=[], features=["Defensive Style", "Second Wind"]),
    "monk": dict(die=8, order=("DEX", "WIS", "CON", "STR", "INT", "CHA"), saves=("STR", "DEX"), n=2,
                 skills=("acrobatics", "athletics", "history", "insight", "religion", "stealth"),
                 armor=("unarmored (10 + DEX + WIS)", 10, "monk"), shield=False, weapon=("shortsword", "1d6", "DEX"),
                 kit=["shortsword", "ten darts", "explorer's pack"], gold=5, spells=[],
                 features=["Unarmored Defense", "Martial Arts"]),
    "paladin": dict(die=10, order=("STR", "CHA", "CON", "WIS", "DEX", "INT"), saves=("WIS", "CHA"), n=2,
                    skills=("athletics", "insight", "intimidation", "medicine", "persuasion", "religion"),
                    armor=("chain mail", 16, None), shield=True, weapon=("longsword", "1d8", "STR"),
                    kit=["longsword", "shield", "chain mail", "five javelins", "holy symbol", "priest's pack"], gold=10,
                    spells=[], features=["Divine Sense", "Lay on Hands"]),
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
                  gold=15, spells=[], features=["Sneak Attack", "Thieves' Cant", "Expertise"]),
    "sorcerer": dict(die=6, order=("CHA", "CON", "DEX", "WIS", "INT", "STR"), saves=("CON", "CHA"), n=2,
                     skills=("arcana", "deception", "insight", "intimidation", "persuasion", "religion"),
                     armor=("unarmored (10 + DEX)", 10, "full"), shield=False, weapon=("light crossbow", "1d8", "DEX"),
                     kit=["light crossbow and 20 bolts", "arcane focus", "two daggers", "dungeoneer's pack"], gold=10,
                     spells=["fire bolt", "light", "prestidigitation", "magic missile", "shield"], features=[]),
    "warlock": dict(die=8, order=("CHA", "CON", "DEX", "WIS", "INT", "STR"), saves=("WIS", "CHA"), n=2,
                    skills=("arcana", "deception", "history", "intimidation", "investigation", "nature", "religion"),
                    armor=("leather armor", 11, "full"), shield=False, weapon=("light crossbow", "1d8", "DEX"),
                    kit=["light crossbow and 20 bolts", "arcane focus", "leather armor", "two daggers", "scholar's pack"], gold=10,
                    spells=["eldritch blast", "minor illusion", "chill touch", "charm person"], features=[]),
    "wizard": dict(die=6, order=("INT", "CON", "DEX", "WIS", "CHA", "STR"), saves=("INT", "WIS"), n=2,
                   skills=("arcana", "history", "insight", "investigation", "medicine", "religion"),
                   armor=("unarmored (10 + DEX)", 10, "full"), shield=False, weapon=("quarterstaff", "1d6", "STR"),
                   kit=["quarterstaff", "spellbook", "component pouch", "scholar's pack"], gold=10,
                   spells=["fire bolt", "mage hand", "light", "magic missile", "shield", "sleep", "detect magic"],
                   features=["Arcane Recovery"]),
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

# THE HERO'S SKILLS ARE ONE LIST (the user, 11-09: "skills, spells, special abilities, everything, should be 'skills'
# in ink adventure -- to keep things simple", and each "should have a proper name, not just '+3 perception'"). Every
# entry has a proper name and says what it lets the hero do; a trained skill of the rules carries the check it trains
# ("trains", its proficiency), a spell its cost in magic points ("cost") and the dice of an attack ("die"), a few a
# small bonus ("mods"). The rules' eighteen skills, each with its proper name and what it lets the hero do:
SKILL_NAMES = {
    "acrobatics": ("Cat's Balance", "tumbles, balances, lands on their feet"),
    "animal handling": ("Gentle Hand", "calms a beast and reads its mood"),
    "arcana": ("Arcane Lore", "knows magic, its signs and its makers"),
    "athletics": ("Iron Limbs", "climbs, jumps, swims and grapples"),
    "deception": ("Silver Tongue", "tells a lie that holds"),
    "history": ("Old Chronicles", "knows what happened, and who did it"),
    "insight": ("Reader of Faces", "tells the truth from a lie"),
    "intimidation": ("Cold Stare", "frightens with a look or a word"),
    "investigation": ("Sharp Reasoning", "finds what is hidden and how it fits"),
    "medicine": ("Healer's Hands", "stops bleeding, judges a wound"),
    "nature": ("Woodcraft", "knows plants, beasts and weather"),
    "perception": ("Keen Eye", "notices what others miss"),
    "performance": ("Stage Presence", "holds a crowd with a song or a tale"),
    "persuasion": ("Honest Appeal", "wins people over"),
    "religion": ("Sacred Lore", "knows the gods and their rites"),
    "sleight of hand": ("Quick Fingers", "picks a pocket, palms a coin"),
    "stealth": ("Shadow Step", "moves unseen and unheard"),
    "survival": ("Wayfinder", "tracks, forages and finds the way"),
}
# the spells a class starts with: what each does, its cost in magic points (1 a small one, 2 a real one), and the dice
# it rolls when it is an attack
SPELLS = {
    "vicious mockery": ("a barbed insult that wounds, 1d4; the target falters", 1, "1d4"),
    "minor illusion": ("a sound or a small image, for a minute", 1, None),
    "healing word": ("a word of healing from across the room, 1d4+2", 2, None),
    "charm person": ("a person takes the hero for a friend, for an hour", 2, None),
    "sleep": ("those nearby fall asleep, the weakest first", 2, None),
    "sacred flame": ("radiant fire falls on one target, 1d8", 1, "1d8"),
    "guidance": ("a touch adds 1d4 to one check", 1, None),
    "cure wounds": ("a touch that heals 1d8+3", 2, None),
    "bless": ("three allies add 1d4 to attacks and saves", 2, None),
    "guiding bolt": ("a bolt of light, 4d6, that leaves the target easy to hit", 2, "4d6"),
    "druidcraft": ("a small trick of nature: a flower opens, a flame lights", 1, None),
    "produce flame": ("a flame in the hand for light, or thrown for 1d8", 1, "1d8"),
    "entangle": ("grasping weeds hold everyone on a patch of ground", 2, None),
    "speak with animals": ("talks with beasts for ten minutes", 2, None),
    "fire bolt": ("a dart of flame, 1d10, at range", 1, "1d10"),
    "light": ("an object shines like a torch for an hour", 1, None),
    "prestidigitation": ("a small magical trick: a spark, a clean, a mark", 1, None),
    "magic missile": ("three darts of force that never miss, 1d4+1 each", 2, "3d4+3"),
    "shield": ("a wall of force in an instant: +5 armor for a round", 2, None),
    "mage hand": ("a spectral hand lifts ten pounds at thirty feet", 1, None),
    "detect magic": ("sees magic and its kind, for ten minutes", 2, None),
    "eldritch blast": ("a beam of crackling force, 1d10", 1, "1d10"),
    "chill touch": ("a ghostly hand, 1d8; the target cannot heal this turn", 1, "1d8"),
}
# the classes' features and the races' traits, each a skill with its proper name: what it lets the hero do (a string),
# or that and more -- "trains" a proficiency, "die" and "ability" the dice of an attack, a spell's "kind" and "cost"
FEATS = {
    "Rage": "a fury: +2 damage, half from blows; twice a day",
    "Unarmored Defense": "armor from toughness alone, nothing worn",
    "Bardic Inspiration": "a word or a tune gives an ally a d6 for one roll",
    "Druidic": "speaks the secret tongue of druids, reads its signs",
    "Defensive Style": "+1 armor while wearing armor",
    "Second Wind": "a breath that heals 1d10 + level, once between rests",
    "Martial Arts": "fists and feet strike for 1d4, and a second blow follows",
    "Divine Sense": "feels the holy and the unholy nearby",
    "Lay on Hands": "a touch that heals, five hit points a day in all",
    "Favored Enemy": "knows one kind of foe: tracks and reads them with ease",
    "Natural Explorer": "never lost in the wild, and finds twice the food",
    "Sneak Attack": "+1d6 on a hit when the target is distracted or flanked",
    "Thieves' Cant": "the secret jargon and signs of thieves",
    "Expertise": "proficiency counted twice in two skills",
    "Arcane Recovery": "an hour's rest brings back 2 MP, once a day",
    "Darkvision": "sees sixty feet in the dark, in gray",
    "Keen Senses": {"effect": "an elf's sharp eye and ear", "trains": "perception"},
    "Fey Ancestry": "cannot be put to sleep by magic; charms slide off",
    "Dwarven Resilience": "poison does half, and saves against it have advantage",
    "Stonecunning": "reads stonework and its history like a book",
    "Lucky": "a 1 on the die is rolled again",
    "Brave": "advantage on saves against fear",
    "Nimble": "slips through the space of anyone larger",
    "Gnome Cunning": "advantage on saves of the mind against magic",
    "Relentless Endurance": "drops to 1 hit point instead of 0, once a day",
    "Savage Attacks": "a critical hit rolls one more damage die",
    "Hellish Resistance": "fire does half",
    "Infernal Legacy": {"effect": "a devil's small tricks: a booming voice, a flaring flame", "kind": "spell", "cost": 1},
    "Breath Weapon": {"effect": "a breath of fire in a line, 2d6; once between rests", "die": "2d6", "ability": "CON"},
    "Damage Resistance": "the breath's own element does half",
}
_OLD_FEATS = {"Fighting Style: Defense": "Defensive Style"}    # an older sheet's name for one
# the ability a class's magic runs on; anyone else's, the best of mind
CASTING = {"bard": "CHA", "cleric": "WIS", "druid": "WIS", "paladin": "CHA", "ranger": "WIS", "sorcerer": "CHA",
           "warlock": "CHA", "wizard": "INT"}


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
    traits = [e for e in (feat_skill(t) for t in Rc["traits"]) if e]
    given = {e["trains"] for e in traits if e.get("trains")}         # a race's own proficiency (an elf's Keen Senses)
    want = list(dict.fromkeys(s for s in (str(x).strip().lower() for x in (spec.get("skills") or []))
                              if s in C["skills"] and s not in given))
    for s in C["skills"]:
        if len(want) >= C["n"]:
            break
        if s not in want and s not in given:
            want.append(s)
    # ONE LIST OF SKILLS, each with a proper name: the trained skills of the rules (a rogue an expert in the first two),
    # the class's special abilities, the race's, then the spells with their cost in magic points
    skills = [trained_skill(s, expert=cls == "rogue" and i < 2) for i, s in enumerate(want[:C["n"]])]
    skills += [e for e in (feat_skill(f) for f in C["features"]) if e] + traits + [spell_skill(s) for s in C["spells"]]
    for e in skills:
        if e["name"] == "Expertise" and len(skills) > 1 and skills[0].get("trains") and skills[1].get("trains"):
            e["effect"] = "proficiency counted twice in %s and %s" % (skills[0]["name"], skills[1]["name"])
    hp = C["die"] + mod(ab["CON"])
    hero = {"name": str(spec.get("name") or "the hero")[:40], "race": race, "class": cls, "level": 1, "xp": 0,
            "background": str(spec.get("background") or "wanderer")[:40],
            "alignment": str(spec.get("alignment") or "neutral")[:30],
            "look": str(spec.get("look") or "")[:200], "height_cm": _cm(spec.get("height_cm")),
            "personality": str(spec.get("personality") or "")[:240],
            "backstory": str(spec.get("backstory") or "")[:600],
            "abilities": ab, "rolls": rolls, "hp": {"now": max(1, hp), "max": max(1, hp)},
            "speed": Rc["speed"], "saves": list(C["saves"]), "skills": skills,
            "weapon": {"name": C["weapon"][0], "die": C["weapon"][1], "ability": C["weapon"][2]},
            "inventory": [{"name": k, "qty": 1} for k in C["kit"]], "gold": C["gold"], "conditions": []}
    hero["ac"] = armor_class(hero)
    if any(e.get("cost") for e in skills):
        hero["mp"] = {"now": magic_max(hero), "max": magic_max(hero)}
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


def _proper(key):
    """'speak with animals' -> 'Speak with Animals': a spell's proper name from the rules' key."""
    small = {"with", "of", "the", "a", "an", "and", "on", "in"}
    return " ".join(w if (i and w in small) else w[:1].upper() + w[1:] for i, w in enumerate(str(key).split()))


def trained_skill(key, expert=False):
    """The rules' skill `key`, trained: a skill with its proper name, what it does, and the check it trains."""
    name, effect = SKILL_NAMES[key]
    e = {"name": name, "kind": "skill", "effect": effect, "trains": key}
    if expert:
        e["expert"] = True
    return e


def spell_skill(key):
    """A spell by its rules' name -> a skill: its proper name, what it does, its cost, and the dice of an attack."""
    effect, cost, die = SPELLS.get(str(key).lower(), ("", 2, None))
    e = {"name": _proper(key), "kind": "spell", "effect": effect, "cost": cost}
    if die:
        e["die"] = die
    return e


def feat_skill(key):
    """A class feature or a race trait by name -> a skill, or None for one the rules give no ability for ("Spellcasting"
    is the spells themselves). An older sheet's "Rage (2 a day)" and "Fighting Style: Defense" are found too."""
    k = str(key).strip()
    k = _OLD_FEATS.get(k) or re.sub(r"\s*\(.*\)$", "", k)
    v = FEATS.get(k)
    if v is None:
        return None
    return {"name": k, "kind": "ability", "effect": v} if isinstance(v, str) else dict({"name": k, "kind": "ability"}, **v)


def unify(h):
    """An older hero's trained skills (names), spells, features and talents -> the one skills list, in place. -> h"""
    old = [k for k in ("spells", "features", "talents") if k in h]
    if not old and all(isinstance(s, dict) for s in h.get("skills") or []):
        return h
    out = []
    for s in h.get("skills") or []:
        if isinstance(s, dict):
            out.append(s)
        elif str(s).lower() in SKILLS:
            out.append(trained_skill(str(s).lower()))
    out += [e for e in (feat_skill(f) for f in h.pop("features", None) or []) if e]
    out += [spell_skill(s) for s in h.pop("spells", None) or []]
    for t in h.pop("talents", None) or []:
        if isinstance(t, dict) and t.get("name"):
            e = {"name": str(t["name"]), "kind": "spell" if t.get("kind") == "spell" else "ability",
                 "effect": str(t.get("effect") or "")}
            if t.get("mods"):
                e["mods"] = dict(t["mods"])
            if e["kind"] == "spell":
                e["cost"] = 2
            out.append(e)
    seen, h["skills"] = set(), []
    for e in out:
        if e["name"].lower() not in seen:
            seen.add(e["name"].lower())
            h["skills"].append(e)
    if any(e.get("cost") for e in h["skills"]) and not h.get("mp"):
        h["mp"] = {"now": magic_max(h), "max": magic_max(h)}
    return h


def skills_of(h):
    """The hero's skills, one list (an older hero's made one first)."""
    unify(h)
    return h.setdefault("skills", [])


def trained(h):
    """The rules' skills the hero is trained in -> {key: the skill that trains it}."""
    return {s["trains"]: s for s in skills_of(h) if s.get("trains")}


def casting_ability(h):
    """The ability the hero's magic runs on: the class's, else the best of mind."""
    a = h["abilities"]
    return CASTING.get(h["class"]) or max(("INT", "WIS", "CHA"), key=lambda k: a[k])


def magic_max(h):
    """Magic points at full: 4 + the casting ability's modifier (never less than 4), and 2 more a level."""
    return 4 + max(0, mod(h["abilities"][casting_ability(h)])) + 2 * (max(1, int(h["level"])) - 1)


def find_skill(h, name):
    """The hero's skill called `name` -- or the one that trains the rules' skill of that name -- or None."""
    key = " ".join(str(name or "").split()).lower()
    if not key:
        return None
    for s in skills_of(h):
        if s["name"].lower() == key or s.get("trains") == key:
            return s
    if len(key) >= 4:
        return next((s for s in skills_of(h) if key in s["name"].lower() or s["name"].lower() in key), None)
    return None


def spend(h, used):
    """A cast: the spell's magic points come off. -> a note; None when the hero cannot pay for it."""
    cost = int(used.get("cost") or 0)
    if not cost:
        return ""
    mp = h.get("mp") or h.setdefault("mp", {"now": magic_max(h), "max": magic_max(h)})
    if mp["now"] < cost:
        return None
    mp["now"] -= cost
    return "%s cast for %d MP (%d left)" % (used["name"], cost, mp["now"])


def add_skill(h, t):
    """A SKILL the story grants -> a note, or '' when there is nothing to take. Each is the hero's own: a proper name
    nobody's list has twice, what it lets the hero do (the game master is told it every turn), for a spell its cost in
    magic points (1 or 2), and at most two small numbers ("mods": +-1 or +-2 to a skill's or an ability's checks),
    which most have none of. A name from the rules' list (or its proper name) trains that skill instead."""
    if isinstance(t, str):
        t = {"name": t}
    if not isinstance(t, dict):
        return ""
    name = " ".join(str(t.get("name") or "").split())[:40]
    if not name:
        return ""
    key = name.lower()
    by_name = {v[0].lower(): k for k, v in SKILL_NAMES.items()}
    if key in SKILLS or key in by_name:
        key = by_name.get(key, key)
        if key in trained(h):
            return "already trained: %s" % SKILL_NAMES[key][0]
        skills_of(h).append(trained_skill(key))
        return "trained in %s (%s)" % (SKILL_NAMES[key][0], key)
    if key in {s["name"].lower() for s in skills_of(h)}:
        return "already known: %s" % name
    mods = {}
    raw = t.get("mods") if isinstance(t.get("mods"), dict) else {}
    for k, v in list(raw.items())[:2]:
        k = str(k).strip()
        ab = next((a for a in ABILITIES if k.upper() == a or k.lower() == ABILITY_NAMES[a].lower()), None)
        mk = ab or k.lower()
        try:
            v = max(-2, min(2, int(v)))
        except (TypeError, ValueError):
            continue
        if v and (mk in ABILITIES or mk in SKILLS):
            mods[mk] = v
    try:
        cost = max(0, min(3, int(str(t.get("cost") or 0).strip().split()[0])))
    except (TypeError, ValueError, IndexError):
        cost = 0
    spell = str(t.get("kind") or "").strip().lower() == "spell" or cost > 0
    cost = cost or (1 if spell else 0)
    e = {"name": name, "kind": "spell" if spell else "ability", "effect": " ".join(str(t.get("effect") or "").split())[:140]}
    if mods:
        e["mods"] = mods
    if cost:
        e["cost"] = cost
        if not h.get("mp"):
            h["mp"] = {"now": magic_max(h), "max": magic_max(h)}
    skills_of(h).append(e)
    return "learned %s%s" % (name, (" (%d MP)" % cost) if cost else "")


def skill_mod(h, key):
    """What the hero's skills add to checks with `key` (a skill, or an ability)."""
    return sum(int((s.get("mods") or {}).get(key, 0)) for s in skills_of(h))


def attack_ability(h, used=None):
    """The ability behind an attack: the weapon's, or for a skill with dice of its own (a spell, a breath) its own."""
    if used and used.get("die"):
        return used.get("ability") or (casting_ability(h) if used.get("kind") == "spell" else h["weapon"]["ability"])
    return h["weapon"]["ability"]


def bonus(h, kind, key, used=None):
    """The bonus a check adds: a skill, an ability, a saving throw, or an attack with their weapon (or with `used`, a
    skill with dice of its own)."""
    a, p = h["abilities"], prof(h["level"])
    if kind == "skill":
        t = trained(h).get(key)
        return mod(a[SKILLS[key]]) + (p * (2 if t.get("expert") else 1) if t else 0) + skill_mod(h, key) + skill_mod(h, SKILLS[key])
    if kind == "save":
        return mod(a[key]) + (p if key in h["saves"] else 0) + skill_mod(h, key)
    if kind == "attack":
        return mod(a[attack_ability(h, used)]) + p
    return mod(a[key]) + skill_mod(h, key)


def skill_figure(h, s):
    """What stands at the right of a skill on the sheet, and after it for the game master: a trained skill's check
    and bonus ("Perception +5"), a spell's cost ("1 MP"), a bonus the skill carries ("+1 Stealth"), or nothing."""
    if s.get("trains"):
        return "%s %+d" % (s["trains"].capitalize(), bonus(h, "skill", s["trains"]))
    if s.get("cost"):
        return "%d MP" % int(s["cost"])
    mods = s.get("mods") or {}
    return ", ".join("%+d %s" % (v, k if k in ABILITIES else k.capitalize()) for k, v in list(mods.items())[:2])


def skill_words(h):
    """Every skill of the hero's in words, for the game master: its name, what it does, and its number or cost."""
    return ["%s (%s)" % (s["name"], "; ".join(x for x in (s.get("effect"), skill_figure(h, s)) if x) or "no effect given")
            for s in skills_of(h)]


def check(state, kind, key, dc, adv=0, used=None):
    """Roll a check for the hero: d20 (twice, best or worst, with advantage or disadvantage) + the bonus
    against the DC. An attack that hits also rolls the damage: the weapon's, or `used`'s when the skill used has dice
    of its own (a spell, a breath). -> the result, also logged."""
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
    b = bonus(h, kind, key, used)
    total = nat + b
    ok = nat == 20 or (nat != 1 and total >= int(dc))
    out = {"kind": kind, "key": key, "dc": int(dc), "dice": d, "natural": nat, "bonus": b, "total": total,
           "success": ok, "critical": nat == 20, "fumble": nat == 1}
    own = used if kind == "attack" and used and used.get("die") else None
    if own:
        out["with"] = own["name"]
    if kind == "attack" and ok:
        die = own["die"] if own else h["weapon"]["die"]
        dmg, dd = roll(die, rng)
        if nat == 20:
            extra, ed = roll(die, rng)
            dmg, dd = dmg + extra, dd + ed
        if not own:
            dmg += mod(h["abilities"][h["weapon"]["ability"]])
        out["damage"] = max(1, dmg)
        out["damage_dice"] = dd
    state["rng"] = rng.state()
    return out


def describe_check(r):
    """'Stealth: rolled 14 +5 = 19 against 15, a success' -- for the page and the notepad."""
    name = r["key"] if r["kind"] in ("skill",) else ("%s save" % r["key"] if r["kind"] == "save" else
                                                     (r.get("with") or "attack") if r["kind"] == "attack" else r["key"])
    s = "%s: rolled %d %+d = %d against %d, %s" % (name.capitalize() if r["kind"] == "skill" else name, r["natural"], r["bonus"],
                                                  r["total"], r["dc"], "a critical success" if r["critical"] else
                                                  "a critical failure" if r["fumble"] else "a success" if r["success"] else "a failure")
    if r.get("damage"):
        s += ", %d damage" % r["damage"]
    return s


# ------------------------------------------------------------------------------ changes the story makes
def apply(state, ch, allowed_items=()):
    """What the story says changed -> what the ENGINE accepts, and why not the rest.

    ch = {hp: "+3" | "-1d6" | int, mp: "+2" | "all" | int, gain: [{name, qty}], lose: [names], gold: int, xp: int,
          skills_gain: [{name, effect, cost, mods} or a rules' skill's name], conditions_add: [...],
          conditions_remove: [...], flags_add: [...]}
    An item GAINED must be one the action was ruled to use from the picture (allowed_items) or be
    explicitly granted by a success the engine rolled (the caller passes it in allowed_items too).
    An item LOST must be one the hero has. Hit points stay in 0..max, magic points too. A SKILL the story
    teaches is taken once, by its proper name (add_skill): the hero's skills grow like the inventory."""
    h = unify(state["hero"])
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
    for s in list(ch.get("skills_gain") or []) + list(ch.get("talents_gain") or []):
        note = add_skill(h, s)
        if note:
            notes.append(note)
    if ch.get("mp") not in (None, "", 0, "0", "+0"):
        # MAGIC COMES BACK BY REST, as the story tells it: "+2" for an hour's, "all" after a night's sleep
        if not h.get("mp"):
            notes.append("no magic to restore")
        else:
            try:
                v = h["mp"]["max"] if str(ch["mp"]).strip().lower() in ("all", "full") else int(str(ch["mp"]).replace("+", ""))
                before = h["mp"]["now"]
                h["mp"]["now"] = max(0, min(h["mp"]["max"], before + v))
                if h["mp"]["now"] != before:
                    notes.append("magic %+d (%d/%d)" % (h["mp"]["now"] - before, h["mp"]["now"], h["mp"]["max"]))
            except ValueError:
                notes.append("magic: %r not understood" % ch["mp"])
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
            if h.get("mp"):
                h["mp"]["max"], h["mp"]["now"] = h["mp"]["max"] + 2, h["mp"]["now"] + 2
            notes.append("level %d (+%d hit points%s)" % (lvl, gain, ", +2 MP" if h.get("mp") else ""))
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
    # AT 0 HIT POINTS THE HERO IS DYING, not dead: they make death saves (dying_turn); healed by anyone meanwhile, they
    # are up again
    if h["hp"]["now"] <= 0 and state.get("status") != "dying":
        state["status"], state["death_saves"] = "dying", {"failed": 0}
    elif h["hp"]["now"] > 0 and state.get("status") == "dying":
        state["status"] = "playing"
        state.pop("death_saves", None)
    return notes


# ------------------------------------------------------------------------------ death saves, and after a death
# THE RULING (11-07): "real death saves should be offered, roll death save, or give up option, 3 failed rolls you die,
# 1 successful roll you get back up with 1 hp; if the character does die, the adventure must continue somehow." A
# dying hero's turn is a death save the engine rolls (a d20; DEATH_SAVE_DC or more is a success), or giving up; at
# DEATH_SAVES failures, or given up, the hero dies -- and the story goes on (AFTER_DEATH_PROMPT).
DEATH_SAVES = 3
DEATH_SAVE_DC = 10

DYING_PROMPT = """The hero of a text adventure, {name}, lies dying at 0 hit points, making death saves: {failed} of
{saves} failed so far (one more than that and they die; one success and they get back up with 1 hit point).
The player wrote: "{action}"
Do they roll a death save, or give up? Answer with one word: ROLL or GIVE_UP. Anything but giving up is a roll."""

AFTER_DEATH_PROMPT = """You are the game master of a text adventure. The adventure: {title} (tone: {tone}).
FOR THE GAME MASTER ONLY: the premise ({premise}).
The hero, {hero}, HAS DIED: {how}.
The people of this story. THEIR LOOKS ARE FIXED: never change anyone's race, height, build, hair, face or marks.
{cast}
What has happened so far:
{events}
Quests: {quests}
Where they were: {place}. What was around: {around}
THE ADVENTURE DOES NOT END. Tell how it goes on, creatively and true to the story's tone: the hero wakes in the great
beyond, or comes back years later as something else, or a successor takes up what they left behind, or anything else
that keeps the story going. The player plays on as whoever the story now follows.
Answer with JSON only:
{{"way": "one line: how the story goes on",
 "what_happened": "three to six sentences, second person: the death, then what comes after",
 "log": "one line for the adventure log, past tense",
 "place": "where the story is now, a few words", "around": "two sentences: what can be seen now",
 "options": ["three or four loose ideas, a few words each"],
 "present": ["the name of each person listed above who is in the next scene"],
 "new_people": [every named person appearing for the FIRST time, each {person}],
 "picture": {{"mode": "new", "prompt": "what the one the story now follows SEES: the place, the objects, where each
             person stands. Never describe them."}},
 "successor": null if the hero goes on themselves, else the new hero the player now plays: {{"name": "...", "race": one
             of {races}, "class": one of {classes}, "background": "...", "alignment": "...", "height_cm": a number,
             "look": "one sentence: build, hair, eyes, skin, clothing", "personality": "two sentences",
             "backstory": "three sentences: who they are, and what the fallen hero was to them"}},
 "changes": {{"conditions_add": ["what the hero who goes on now is, if anything: undead, a ghost ..."],
             "conditions_remove": []}}}}"""


def death_choice(state, action, ask_text):
    """A dying hero's turn: does the player roll a death save, or give up? The model reads what they wrote; anything
    but giving up is a roll. -> "roll" or "give_up"."""
    try:
        reply = ask_text(DYING_PROMPT.format(name=state["hero"]["name"], action=str(action)[:300],
                                             failed=(state.get("death_saves") or {}).get("failed", 0),
                                             saves=DEATH_SAVES))
    except Exception:
        reply = ""
    return "give_up" if re.search(r"(?i)\bGIVE[_ ]?UP\b", str(reply or "")) else "roll"


def death_save(state):
    """The engine rolls a dying hero's death save: a success and they are up with 1 hit point; a failure counts, and
    the last one kills them. -> {"roll": n, "success": bool, "failed": count, "died": bool}."""
    rng = CH.Rng(**state["rng"])
    n = rng.randint(1, 20)
    state["rng"] = rng.state()
    ds = state.setdefault("death_saves", {"failed": 0})
    if n >= DEATH_SAVE_DC:
        state["hero"]["hp"]["now"] = 1
        state["status"] = "playing"
        state.pop("death_saves", None)
        return {"roll": n, "success": True, "failed": ds["failed"], "died": False}
    ds["failed"] = int(ds.get("failed", 0)) + 1
    return {"roll": n, "success": False, "failed": ds["failed"], "died": ds["failed"] >= DEATH_SAVES}


def after_death(state, tell):
    """The hero has died and the story goes on (AFTER_DEATH_PROMPT's `tell`): a successor the engine makes from the
    model's proposal takes the hero's place, the fallen one kept in state["fallen"]; or the hero goes on themselves,
    their hit points whole again. Either way the story is playing again. -> a line for the turn's notes."""
    st = tell.get("successor")
    state.pop("death_saves", None)
    state["status"] = "playing"
    if isinstance(st, dict) and st.get("name"):
        rng = CH.Rng(**state["rng"])
        fallen = state["hero"]
        state.setdefault("fallen", []).append(fallen)
        state["hero"] = make_hero(st, rng)
        state["rng"] = rng.state()
        return "%s fell; %s takes up the story" % (fallen["name"], state["hero"]["name"])
    h = state["hero"]
    h["hp"]["now"] = h["hp"]["max"]
    return "%s died, and goes on: %s" % (h["name"], _s(tell.get("way") or "", 100))


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


def _clip(v, n):
    """_s for what is read as a sentence (the story log): longer than n, cut at its last whole word, with "..." --
    cut at n characters, the story so far ended "knocks a heavy iron wrench fr"."""
    t = _s(v, 1 << 20)
    if len(t) <= n:
        return t
    # A WHOLE SENTENCE when one ends far enough in: cut at a word, the journal's beginning read "...a sturdy oak box
    # on a stand, and..." -- stopped mid-thought
    ends = [m.end() for m in re.finditer(r"[.!?][\"”')]?(?=\s)", t[:n])]
    if ends and ends[-1] >= 0.4 * n:
        return t[:ends[-1]]
    return t[:max(1, n - 3)].rsplit(" ", 1)[0].rstrip(" ,;:-") + "..."


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
            "%s, a level %d %s %s; %d/%d hit points%s; %d turns; %s" % (
                h["name"], h["level"], h["race"], h["class"], h["hp"]["now"], h["hp"]["max"],
                ("; %d/%d MP" % (h["mp"]["now"], h["mp"]["max"])) if h.get("mp") else "", len(state["turns"]),
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


def _wrap2(d, text, font, first, rest):
    """Words on at most two lines: the first `first` wide (room left for a figure at its right), the second `rest`,
    cut with an ellipsis when they do not fit."""
    words = str(text).split()
    if not words:
        return []
    line = ""
    while words and (not line or d.textlength(line + " " + words[0], font=font) <= first):
        line = (line + " " + words.pop(0)).strip()
    if not words:
        return [line]
    return [line, _ellipsis(d, " ".join(words), font, rest)]


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


# ------------------------------------------------------------------------------ ONE DESIGN for every page
# The user, 11-07, of the pages as they were: "no design language, no consistency, the character pages aren't decoms
# like the rest, the page numbers sitting by things are nonsensical", and "the ink adventure pages suggest they are links
# but aren't". Every page of a game is drawn from these parts, and nothing else:
#   ONE COLUMN, the scene picture's width -- the tablet's own typed-text column (inputarea.COLUMN_X) -- so every title,
#     line, cell and picture starts and ends where the player's own typing does.
#   ONE HEADER (_header): the page's title, a line saying what is on the page, and a hairline across the column, each
#     at the same height on every page, and NOTHING OVER THE TITLE: a kicker naming the adventure and the part of the
#     book ("THE DROWNING LIGHT · CHARACTER SHEET") was noise, and so is any heading over text that says what it is
#     ("WHO THEY ARE") -- the user, 11-08. The adventure's own name is the contents page's title, where a book has it.
#     The scene page's picture is its header: the place's name comes under it, then the turn and the roll in small gray.
#   ONE TYPE SCALE (STYLES): the title; a name (a place, a person, a quest, a line of the contents); the body; small gray
#     text (a roll, where and when); a label (small gray capitals: the name of a field or a section).
#   NOTHING THAT LOOKS LIKE A BUTTON: a notebook page cannot be tapped, so nothing is drawn as one. A cell of numbers is
#     a hairline box, a picture has a hairline frame.
#   PAGE NUMBERS WHERE A BOOK PUTS THEM: in the contents, at the right after a dotted leader, and at the right of a
#     person's name on the characters page, on the name's own line -- never a badge on a box. In a PDF (the book) those
#     same lines are its links.
#   EVERY PICTURE IS INK: the scene and every portrait are decomposed into strokes, laid inside their frames.
_SCENE_SIDE = 1270 - int(CH.TOP)
SCENE_BOX = ((PAGE_W - _SCENE_SIDE) // 2, int(CH.TOP), (PAGE_W + _SCENE_SIDE) // 2, 1270)
X0, X1 = SCENE_BOX[0], SCENE_BOX[2]               # the column
CW = X1 - X0
TITLE_Y, RULE_Y, BODY_Y = 134, 222, 254              # the title, the hairline under it, the body: the same on every page
FOOT_Y = PAGE_H - 80                               # the lowest any page's text goes
STYLES = {                                         # (face, size, line height, color)
    "title": ("reMarkableSans-Bold.ttf", 56, 70, INK),
    "name": ("reMarkableSans-Medium.ttf", 34, 46, INK),
    "sub": ("reMarkableSans-Regular.ttf", 28, 40, GRAY),
    "body": ("reMarkableSans-Regular.ttf", 28, 40, INK),
    "italic": ("reMarkableSans-RegularItalic.ttf", 28, 40, INK),
    "small": ("reMarkableSans-Regular.ttf", 23, 32, GRAY),
    "label": ("reMarkableSans-Medium.ttf", 20, 32, GRAY),
}
TRACK = 2                                          # a label's letter spacing


def _style(name, size=None):
    """A style -> (font, line height, color); `size` scales it."""
    face, base, lh, col = STYLES[name]
    size = size or base
    return _font(face, size), int(round(lh * size / float(base))), col


def _fit(d, text, name, width, least=0.7):
    """The style's font at the largest size, down to `least` of it, that sets `text` on one line in `width`."""
    face, base = STYLES[name][0], STYLES[name][1]
    size = base
    while size > base * least and d.textlength(text, font=_font(face, size)) > width:
        size -= 1
    return _font(face, size)


def _ellipsis(d, text, font, width):
    """`text` cut to `width`, with an ellipsis when it had to be."""
    text = str(text)
    if d.textlength(text, font=font) <= width:
        return text
    while text and d.textlength(text + "…", font=font) > width:
        text = text[:-1]
    return text.rstrip() + "…"


def _caps_w(d, text, font, track=TRACK):
    return sum(d.textlength(c, font=font) for c in text) + track * max(0, len(text) - 1)


def _caps(d, xy, text, font=None, fill=GRAY, width=None, align="left"):
    """A LABEL: small gray capitals, letter-spaced. `align`: "left" (xy is its left end), "center" or "right". `width`:
    the room it has -- a longer one is set smaller, then cut with an ellipsis. -> its width."""
    font = font or _style("label")[0]
    text = str(text).upper()
    if width:
        while _caps_w(d, text, font) > width and font.size > 15:
            font = font.font_variant(size=font.size - 1)
        while _caps_w(d, text, font) > width and len(text) > 2:
            text = text.rstrip("…")[:-1].rstrip() + "…"
    w = _caps_w(d, text, font)
    x = xy[0] - (w if align == "right" else w / 2.0 if align == "center" else 0)
    for c in text:
        d.text((x, xy[1]), c, font=font, fill=fill)
        x += d.textlength(c, font=font) + TRACK
    return w


def _header(d, title, sub=""):
    """THE HEADER of every page but the scene's: the title and the hairline under it, the same on every page, nothing
    over the title. `sub`: what a page has to say first (the hero's level, class and background; a person's role), the
    first line under the hairline -- never a count of what is on the page ("10 things learned", "6 turns played", "1
    met": the user, 11-08, "this stuff is literally making my stomach turn"). -> where the page's body starts."""
    d.text((X0, TITLE_Y), title, font=_fit(d, title, "title", CW), fill=INK)
    d.line((X0, RULE_Y, X1, RULE_Y), fill=RULE, width=2)
    if not sub:
        return BODY_Y
    f, lh, col = _style("sub")
    d.text((X0, BODY_Y), _ellipsis(d, sub, f, CW), font=f, fill=col)
    return BODY_Y + lh + 22


def _frame(d, box):
    """A picture's hairline frame, 6 outside its box: the picture's strokes are laid inside the box."""
    d.rectangle((box[0] - 6, box[1] - 6, box[2] + 6, box[3] + 6), outline=RULE, width=2)


def _leader(d, x0, x1, y):
    """A dotted leader from x0 to x1 at the height y: a contents line's way to its page number. The dots sit on a grid
    of their own, so the leaders of lines one under the other line up."""
    x = x0 + (12 - x0 % 12)
    while x < x1:
        d.ellipse((x - 1.6, y - 1.6, x + 1.6, y + 1.6), fill=GRAY)
        x += 12


def sheet_png(state, out):
    """THE CHARACTER SHEET, D&D style, drawn at the page's own size (1620 x 2160) in the one design: the header (the
    hero's name; level, race, class, background, alignment, experience), the six abilities and the numbers (armor, hit
    points, magic for a caster, speed, proficiency, initiative, gold) in hairline cells across the column, the saving
    throws at the left and the attack and conditions at the right, the skills in one list, then the inventory and who
    the hero is."""
    from paperdaemon.pipeline.draw import scaled as SD
    h = unify(state["hero"])
    im, d = SD.canvas(PAGE_W, PAGE_H)                 # (laid out in design pixels; sent at twice the tablet's resolution)
    y = _header(d, h["name"], "Level %d %s %s  ·  %s  ·  %s  ·  %d XP" % (
        h["level"], h["race"], h["class"], h["background"], h["alignment"], h["xp"]))
    big, name_f = _style("title")[0], _style("name")[0]
    body_f, body_lh, _ = _style("body")
    small_f = _style("small")[0]
    G = 14
    cw = (CW - 5 * G) / 6.0
    # the six abilities: the modifier large, the score under it
    for i, a in enumerate(ABILITIES):
        x = X0 + i * (cw + G)
        d.rectangle((x, y, x + cw, y + 158), outline=RULE, width=2)
        _caps(d, (x + cw / 2.0, y + 16), ABILITY_NAMES[a], width=cw - 16, align="center")
        m = "%+d" % mod(h["abilities"][a])
        d.text((x + (cw - d.textlength(m, font=big)) / 2.0, y + 46), m, font=big, fill=INK)
        s = str(h["abilities"][a])
        d.text((x + (cw - d.textlength(s, font=small_f)) / 2.0, y + 118), s, font=small_f, fill=GRAY)
    y += 158 + G
    stats = [("Armor", str(h["ac"])), ("Hit points", "%d / %d" % (h["hp"]["now"], h["hp"]["max"]))]
    if h.get("mp"):
        stats.append(("Magic", "%d / %d" % (h["mp"]["now"], h["mp"]["max"])))
    stats += [("Speed", "%d ft" % h["speed"]), ("Proficiency", "%+d" % prof(h["level"])),
              ("Initiative", "%+d" % mod(h["abilities"]["DEX"])), ("Gold", str(h["gold"]))]
    sw = (CW - (len(stats) - 1) * G) / float(len(stats))
    lab = _style("label")[0]
    while lab.size > 15 and any(_caps_w(d, k.upper(), lab) > sw - 16 for k, _ in stats):
        lab = lab.font_variant(size=lab.size - 1)       # one size for the whole row: its longest label sets it
    for i, (k, v) in enumerate(stats):
        x = X0 + i * (sw + G)
        d.rectangle((x, y, x + sw, y + 108), outline=RULE, width=2)
        _caps(d, (x + sw / 2.0, y + 16), k, font=lab, width=sw - 16, align="center")
        d.text((x + (sw - d.textlength(v, font=name_f)) / 2.0, y + 50), v, font=name_f, fill=INK)
    y += 108 + 50
    col = (CW - 48) / 2.0
    # left: the saving throws; right: the attack, and the conditions when there are any
    ly = y
    _caps(d, (X0, ly), "Saving throws")
    ly += 40
    for a in ABILITIES:
        on = a in h["saves"]
        d.ellipse((X0, ly + 12, X0 + 16, ly + 28), fill=INK if on else None, outline=INK, width=2)
        d.text((X0 + 32, ly), "%+d  %s" % (bonus(h, "save", a), ABILITY_NAMES[a]), font=body_f, fill=INK)
        ly += body_lh
    rx, ry = X0 + col + 48, y
    w = h["weapon"]
    _caps(d, (rx, ry), "Attack")
    ry += 40
    for l in _wrap(d, "%s: %+d to hit, %s%+d" % (w["name"].capitalize(), bonus(h, "attack", None), w["die"],
                                                mod(h["abilities"][w["ability"]])), body_f, col):
        d.text((rx, ry), l, font=body_f, fill=INK)
        ry += body_lh
    if h["conditions"]:
        ry += 24
        _caps(d, (rx, ry), "Conditions")
        ry += 40
        for line in _wrap(d, ", ".join(h["conditions"]), body_f, col):
            d.text((rx, ry), line, font=body_f, fill=INK)
            ry += body_lh
    y = max(ly, ry) + 24
    # THE SKILLS, one list (the user, 11-09: skills, spells and special abilities are all "skills", each with "a proper
    # name, not just '+3 perception'"): the name; what it lets the hero do; and at the right its figure -- the check a
    # trained skill is good at with its bonus, or a spell's cost in magic points. The story adds to it as it goes
    # (apply: skills_gain), like the inventory.
    _caps(d, (X0, y), "Skills")
    y += 40
    sub_f = _style("sub")[0]
    ex0 = X0 + 300
    for s in skills_of(h):
        d.text((X0, y), _ellipsis(d, s["name"], body_f, 276), font=body_f, fill=INK)
        fig = skill_figure(h, s)
        if fig:
            d.text((X1 - d.textlength(fig, font=body_f), y), fig, font=body_f, fill=INK)
        room = X1 - ex0 - ((d.textlength(fig, font=body_f) + 24) if fig else 0)
        lines = _wrap2(d, s.get("effect") or "", sub_f, room, X1 - ex0) or [""]
        for l in lines:
            if l:
                d.text((ex0, y), l, font=sub_f, fill=GRAY)
            y += body_lh
    if not skills_of(h):
        d.text((X0, y), "None yet", font=body_f, fill=GRAY)
        y += body_lh
    y += 24
    d.line((X0, y, X1, y), fill=RULE, width=2)
    y += 32
    _caps(d, (X0, y), "Inventory")
    y += 40
    inv = ["%s%s" % (it["name"], (" x%d" % it["qty"]) if it["qty"] > 1 else "") for it in h["inventory"]]
    half = -(-len(inv) // 2)                           # down the left column, then the right
    for i, line in enumerate(inv):
        d.text((X0 + (i // half) * (col + 48), y + (i % half) * body_lh), "•  " + _ellipsis(d, line, body_f, col - 30),
               font=body_f, fill=INK)
    if not inv:
        d.text((X0, y), "Nothing", font=body_f, fill=GRAY)
    y += max(1, half) * body_lh + 32
    # the hero's personality and story: a paragraph of its own under a hairline, with no heading over it (a heading
    # over text that says what it is, "WHO THEY ARE", is noise -- the user, 11-08)
    who = " ".join(x for x in (h.get("personality"), h.get("backstory")) if x)
    if who and y < FOOT_Y - 120:
        d.line((X0, y, X1, y), fill=RULE, width=2)
        y += 32
        for line in _wrap(d, who, body_f, CW):
            if y + body_lh > FOOT_Y:
                break
            d.text((X0, y), line, font=body_f, fill=INK)
            y += body_lh
    im.save(out)
    return out


# the turn page: where each part goes, in page pixels (1620 x 2160, y from the top). The square the picture is
# converted into (SCENE_BOX, above): from the top of the page's safe area (below the tablet's toolbar) down to 1270,
# centered; its sides are the column every page keeps to.
TEXT_TOP, WRITE_TOP = 1304, 1810            # the story, then the player's space: the turn page's picture ends there,
                                            # and under it is the page itself, to type or write in (inputarea.py)


def scene_frame_page(s=1.0):
    """The picture's box in the page's own coordinates (x from the center), for the strokes; `s` scales the designed
    page to the page's own tablet (tablets.picture_page)."""
    x0, y0, x1, y1 = SCENE_BOX
    return ((x0 - PAGE_W / 2.0) * s, y0 * s, (x1 - PAGE_W / 2.0) * s, y1 * s)


def _idea_lines(d, opts, font, width):
    """The loose ideas, "You could: a  ·  b  ·  c", broken into lines BETWEEN ideas only: the separator ends a line,
    and the next one starts with an idea (a line that began with a dot read as a stray mark). An idea too long for a
    line of its own is wrapped."""
    lines, cur = [], "You could: " + opts[0]
    for o in opts[1:]:
        if d.textlength(cur + "  ·  " + o, font=font) <= width:
            cur += "  ·  " + o
        else:
            lines.append(cur + "  ·")
            cur = o
    lines.append(cur)
    return [w for l in lines for w in _wrap(d, l, font, width)]


def turn_png(state, scene, out, roll_line="", n=None):
    """A TURN PAGE's picture, in the one design: the scene's frame at the top (its strokes are laid inside it), the
    picture being the page's header; under it the place's name, the turn and the roll in small gray, what happened,
    what is around and a few loose options; then a hairline across the column, the top of the player's space (where to
    write is plain to see). `n`: the turn's number (the next one). On the page it is cut at WRITE_TOP."""
    from paperdaemon.pipeline.draw import scaled as SD
    im, d = SD.canvas(PAGE_W, PAGE_H)                 # (laid out in design pixels; sent at twice the tablet's resolution)
    _frame(d, SCENE_BOX)
    n = n or len(state["turns"]) + 1
    name_f, name_lh, _ = _style("name")
    small_f, small_lh, _ = _style("small")
    place = scene.get("place") or state["place"] or state["title"]
    # THE END SAYS SO, where the next move's ideas would be: a story that is over showed "You could: ..." for a turn
    # no game would take (a finished game gives its page back, and what is written there next is a new request)
    end = {"victory": "The end: a victory.", "death": "The end: %s has died.",
           "down": "The end: %s has fallen."}.get(state.get("status"))
    # A DYING HERO: the death saves failed so far, and the two things to do -- roll one, or give up
    dying = state.get("status") == "dying" and not end
    top, bottom = TEXT_TOP, WRITE_TOP - 26
    # A STORY TOLD IN FULL (a character's tale is three to six sentences) must fit: the largest body type that holds it
    for size in (28, 26, 24, 22, 20):
        body, lh, _ = _style("body", size)
        ital = _style("italic", size)[0]
        told = [(l, body) for l in _wrap(d, scene.get("what_happened") or "", body, CW)]
        around = [(l, ital) for l in _wrap(d, scene.get("around") or "", ital, CW)]
        need = (name_lh + small_lh + 8 + (len(told) + len(around)) * lh + 24
                + (name_lh if end or dying else 0) + 2 * small_lh)
        if top + need <= bottom:
            break
    y = top
    d.text((X0, y), place, font=_fit(d, place, "name", CW), fill=INK)
    y += name_lh
    meta = "Turn %d" % n + ("  ·  " + roll_line if roll_line else "")
    d.text((X0, y), _ellipsis(d, meta, small_f, CW), font=small_f, fill=GRAY)
    y += small_lh + 8
    for group in (told, around):
        for line, font in group:
            if y + lh > bottom:
                break
            d.text((X0, y), line, font=font, fill=INK)
            y += lh
        if group:
            y += 12
    if end:
        d.text((X0, y), end % state["hero"]["name"] if "%s" in end else end, font=name_f, fill=INK)
    if dying:
        failed = int((state.get("death_saves") or {}).get("failed", 0))
        d.text((X0, y), "%s is dying: %d of %d death saves failed." % (state["hero"]["name"], failed, DEATH_SAVES),
               font=name_f, fill=INK)
        y += name_lh
    # the loose ideas: as many WHOLE ones as two lines and the room hold, never one cut off mid-phrase
    opts = [] if end else (["Roll a death save", "Give up"] if dying else
                           [str(o).strip() for o in (scene.get("options") or []) if str(o).strip()][:4])
    while opts:
        lines = _idea_lines(d, opts, small_f, CW)
        if len(lines) <= 2 and y + small_lh * len(lines) <= bottom:
            for l in lines:
                d.text((X0, y), l, font=small_f, fill=GRAY)
                y += small_lh
            break
        opts = opts[:-1]
    # the player's space: under a hairline across the column
    d.line((X0, WRITE_TOP - 2, X1, WRITE_TOP - 2), fill=RULE, width=2)
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
             "around": "two sentences: what the hero can see around them", "options": ["three or four loose ideas, a few words each"],
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
 "skill": "the hero's skill the action uses, by its name from the hero's list above (a spell, a special ability, a trained skill), or null",
 "check": null or {{"kind": "skill" | "ability" | "save" | "attack", "key": a skill ({skills}) or an ability ({abilities}),
                  "dc": 5 to 25, "advantage": -1, 0 or 1, "why": "why this check", "target": "for an attack, the name of the person attacked"}}}}
Ask for a check only when the outcome is uncertain and matters; an attack's dc is the target's armor class. A spell
costs the magic points its entry names: the engine takes them, and a cast the hero cannot pay for does not happen."""

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
 "options": ["three or four loose ideas, a few words each, not the only choices"],
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
 "picture": {{"mode": "keep" if same_place and nothing in view changed (words were said, a look, a thought), "edit" if
             same_place and the scene only changed a little (say the change: "remove the lantern from the table, keep
             everything else") else "new", "prompt": "the change, or for a new scene what the hero SEES in front of them:
             the place, the objects, where each person stands. Never describe the hero."}},
 "changes": {{"hp": "0", "mp": "0", "gain": [{{"name": "...", "qty": 1}}], "lose": ["..."], "gold": 0, "xp": 0,
             "skills_gain": [{{"name": "a proper name", "effect": "one short line: what it lets the hero do",
                               "cost": "a spell's magic points, 1 or 2; 0 for anything else", "mods": {{}}}}],
             "conditions_add": [], "conditions_remove": [], "flags_add": []}},
 "over": null, or "death" when the hero is struck down (they drop to 0 hit points and make death saves), or "victory"}}
Only give items the hero actually took or was given; hit point loss can be dice like "-1d6". Leave out what did not change.
Skills are earned, and rare: only when the story truly teaches, grants or awakens one. Every skill has a proper name
of its own (Harbor Watch, Gull-Speech, Saltlight), never a bare number, and says what it lets the hero do (sense a
storm coming, speak with gulls, call light from the sea); a spell costs magic points, 1 for a small one and 2 for a real
one. A trained skill of the rules may be learned too, by its name from: {skills}. Most change what the hero can do,
not a number; a few may carry one small number in "mods", as {{"perception": 1}} or {{"DEX": 2}} (a skill or an
ability, at most +2). Magic spent comes back only by rest: "mp" is "+2" for an hour's rest, "all" after a night's
sleep."""

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
    """A cast member's portrait, for the journal. ON PLAIN WHITE: it is decomposed onto the page, and white is the
    page's own -- "light" came back cream, sage or gray, a colored square round one person and none round the next."""
    return ("Portrait of %s, head and shoulders, facing the viewer, on a plain white background. %s" % (
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
    d.kind = "decomp"                                 # a picture traced into strokes (render.author_of)
    d.strokes = list(strokes)
    d.write_rm(doc, page_no, keep_existing=True)
    return len(strokes), secs


def _load_ink(path):
    """Strokes kept by decompose.save_strokes -> [(pts, widths, tool, color, rgb)]. Each array is read ONCE: the
    corpus reader takes them from the file per stroke, and a portrait's 10,000 strokes took it 20 s."""
    import numpy as np
    from paperdaemon.pipeline.draw import Pen, PenColor
    with np.load(path) as z:
        counts, pts, wid = z["counts"].tolist(), z["points"].tolist(), z["widths"].tolist()
        tools, colors, rgba = z["tools"].tolist(), z["colors"].tolist(), z["rgba"].tolist()
    out, i = [], 0
    for n, tool, color, rgb in zip(counts, tools, colors, rgba):
        out.append(([tuple(p) for p in pts[i:i + n]], wid[i:i + n], Pen(tool), PenColor(color),
                    None if rgb[0] < 0 else tuple(rgb)))
        i += n
    return out


def _portrait_strokes(png, box, s):
    """A portrait decomposed into its box (design pixels) on a page `s` page units a design pixel -> its strokes, in
    the page's units (x from the center). KEPT beside the portrait (<portrait>.<w>x<h>.npz, at the box's top left): a
    portrait never changes once painted, and a journal page is drawn again whenever what it says changes."""
    from paperdaemon.pipeline import decompose as M
    x0, y0, x1, y1 = box
    w, h = int(round((x1 - x0) * s)), int(round((y1 - y0) * s))
    ox, oy = (x0 - PAGE_W / 2.0) * s, y0 * s
    kept = "%s.%dx%d.npz" % (os.path.splitext(png)[0], w, h)
    strokes = None
    if os.path.exists(kept) and os.path.getmtime(kept) >= os.path.getmtime(png):
        try:
            strokes = _load_ink(kept)
        except Exception:
            strokes = None
    if strokes is None:
        strokes = M.decompose_into(png, w, h, origin=(0.0, 0.0))[0]
        try:
            M.save_strokes(kept, strokes)
            strokes = _load_ink(kept)                 # (the first drawing as every later one: the kept numbers)
        except Exception:
            pass
    return [tuple([[(px + ox, py + oy) for px, py in st[0]]] + list(st[1:5])) for st in strokes]


def _ink_pictures(doc, page_no, items, s, frame):
    """PICTURES AS INK: each (picture, box in design pixels) decomposed into strokes inside its box and written onto the
    page, over the frame the page's picture drew round it. `s`: page units a design pixel on this page; `frame`: the
    page's (width, height). -> the strokes written."""
    from paperdaemon.pipeline import draw as A
    strokes = []
    for png, box in items:
        if png and os.path.exists(png):
            strokes += _portrait_strokes(png, box, s)
    if strokes:
        d = A.Drawing(*[int(round(v)) for v in frame])
        d.kind = "decomp"                             # a picture traced into strokes (render.author_of)
        d.strokes = strokes
        d.write_rm(doc, page_no, keep_existing=True)
    return len(strokes)


def _keep(state, turn_no, png):
    """The scene's picture KEPT beside the notepad (for an edit next turn, and for the model to see)."""
    import shutil
    dst = os.path.join(pictures_dir(state), "%03d.png" % turn_no)
    shutil.copyfile(png, dst)
    return dst


def _scene_picture(paint, pic_spec, shot, newcomers, pictures, log=None):
    """The turn's scene picture -> a PNG path, or None. NOTHING IN VIEW CHANGED ("keep": words were said, a look, a
    thought) and nobody new came: the last scene's picture stays as it was -- no repaint and no hand-over of the card.
    An "edit" for a few words took 40 s to change nothing the page shows (a mean difference of 4%), and the text model
    came back cold for the next job. Else `pictures()` paints, inside one hand-over (_with_card). The log says which,
    and why (a turn that repainted said nothing of it)."""
    mode = (pic_spec or {}).get("mode") or "new"
    if mode == "keep" and shot and os.path.exists(shot) and not newcomers:
        _log(log, "  adventure: the picture is kept (nothing in view changed)")
        return shot
    _log(log, "  adventure: the picture is %s%s" % ({"edit": "edited", "keep": "painted anew"}.get(mode, "painted anew"),
                                                    " (someone new came)" if mode == "keep" and newcomers else
                                                    " (no picture to keep)" if mode == "keep" else
                                                    ": %s" % str((pic_spec or {}).get("prompt") or "")[:80]))
    return _with_card(paint, pictures) if paint else None


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
    with paths.page_lock(path):                               # (one writer of the page at a time)
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
        turn_png(state, scene, png, roll_line)
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
    """THE LOG, "Story", in the one design: an entry a turn, the newest at the bottom -- the turn and the
    place as a label, what happened, the roll; what does not fit leaves the page, the oldest first (the state keeps
    every entry)."""
    from paperdaemon.pipeline.draw import scaled as SD
    im, d = SD.canvas(PAGE_W, PAGE_H)                 # (laid out in design pixels; sent at twice the tablet's resolution)
    ev = state.get("events") or []
    top = _header(d, "Story")
    body_f, body_lh, _ = _style("body")
    small_f, small_lh, _ = _style("small")
    label_lh = _style("label")[1]
    blocks = []
    for e in ev:
        head = ("Turn %d" % e["n"]) if e["n"] else "The beginning"
        rows = [("label", "%s  ·  %s" % (head, e["place"]) if e.get("place") else head, label_lh)]
        rows += [("body", l, body_lh) for l in _wrap(d, e.get("text") or "", body_f, CW)]
        rows += [("small", l, small_lh) for l in _wrap(d, e.get("roll") or "", small_f, CW)]
        blocks.append(rows)
    gap = 30
    room = FOOT_Y - top - small_lh - gap              # a line kept for the note on earlier turns
    fit = []
    for b in reversed(blocks):
        need = sum(r[2] for r in b) + gap
        if need > room:
            break
        fit.insert(0, b)
        room -= need
    y = top
    if len(fit) < len(blocks):
        d.text((X0, y), "Earlier turns are kept in the game's notes.", font=small_f, fill=GRAY)
        y += small_lh + gap
    for b in fit:
        for kind, text, lh in b:
            if kind == "label":
                _caps(d, (X0, y), text, width=CW)
            else:
                d.text((X0, y), text, font=body_f if kind == "body" else small_f, fill=INK if kind == "body" else GRAY)
            y += lh
        y += gap
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


def _people(state):
    return sorted((state.get("cast") or {}).values(), key=lambda p: (p["met"]["turn"], p["name"]))


def _quest_list(state):
    return sorted(state.get("quests") or [], key=lambda q: (q["status"] != "open", q.get("turn", 0)))


def _measure():
    """A drawing to measure text with, in design pixels (the faces as they are laid out)."""
    from PIL import Image, ImageDraw
    return ImageDraw.Draw(Image.new("RGB", (8, 8)))


def _standing(p):
    """Who a person is to the hero, in a few words: their role, and how they stand (their state when it is not
    "alive", else their disposition)."""
    how = p["status"] if p["status"] != "alive" else p["disposition"]
    return "  ·  ".join(x for x in (p.get("role") or "", how) if x)


def _quest_blocks(d, state):
    """Each quest as rows [(kind, text, height, aside)]: its name with its state at the right, its goal, its last
    updates."""
    body_f, body_lh, _ = _style("body")
    small_f, small_lh, _ = _style("small")
    out = []
    for q in _quest_list(state):
        rows = [("name", q["name"], _style("name")[1], q["status"])]
        rows += [("body", l, body_lh, None) for l in _wrap(d, q.get("goal") or "", body_f, CW)]
        for u in (q.get("updates") or [])[-4:]:
            rows += [("small", l, small_lh, None) for l in _wrap(d, u[:1].upper() + u[1:], small_f, CW)]
        out.append(rows)
    return out


def _lore_blocks(d, state):
    """The things learned as rows, a block a turn: the turn as a label, then each thing learned on it."""
    body_f, body_lh, _ = _style("body")
    out, turn = [], object()
    for x in state.get("lore") or []:
        if x.get("turn") != turn or not out:
            turn = x.get("turn")
            out.append([("label", "Turn %d" % turn, _style("label")[1], None)] if turn else [])
        else:
            out[-1].append(("gap", "", 8, None))
        out[-1] += [("body", l, body_lh, None) for l in _wrap(d, x["text"], body_f, CW)]
    return out


ENTRY_GAP = 30                                   # between two entries: a quest, a thing learned, a turn of the log


def _entry_pages(blocks):
    """Blocks of rows onto pages, each block whole on one page -> [[block]]."""
    pages, cur, y = [], [], BODY_Y
    for b in blocks:
        need = sum(r[2] for r in b)
        if cur and y + need > FOOT_Y:
            pages.append(cur)
            cur, y = [], BODY_Y
        cur.append(b)
        y += need + ENTRY_GAP
    return pages + ([cur] if cur else [])


def _draw_rows(d, rows, y):
    """Rows [(kind, text, height, aside)] down the column from y -> the y under them. A name's `aside` (a quest's
    state) is a label at the right, on the name's own line."""
    name_f = _style("name")[0]
    for kind, text, h, aside in rows:
        if kind == "gap":
            pass
        elif kind == "label":
            _caps(d, (X0, y), text, width=CW)
        elif kind == "name":
            room = CW - (_caps_w(d, aside.upper(), _style("label")[0]) + 24 if aside else 0)
            d.text((X0, y), _ellipsis(d, text, name_f, room), font=name_f, fill=INK)
            if aside:
                _caps(d, (X1, y + 12), aside, align="right")
        else:
            f, _lh, col = _style(kind)
            d.text((X0, y), text, font=f, fill=col)
        y += h
    return y


# PEOPLE ON A CHARACTERS PAGE: two rows of three. A portrait in ink is about 9,700 strokes at a third of the column
# (its size sets that; the decomposer's region budget barely changes it), so six keep the page near one scene's
# (about 42,000) -- nine made it twice that.
JOURNAL_PER = 6


def _journal_plan(state):
    """THE JOURNAL'S PAGES, in order, before any is drawn (an inline game makes its pages first, so it needs their
    count): ("contents",); ("characters", first, end) for each JOURNAL_PER people; ("person", k) for each; ("quests",
    blocks) and ("lore", blocks) for each page of them. A section with nothing in it has no page: the contents says
    so."""
    d = _measure()
    people = _people(state)
    plan = [("contents",)]
    plan += [("characters", g, min(len(people), g + JOURNAL_PER)) for g in range(0, len(people), JOURNAL_PER)]
    plan += [("person", k) for k in range(len(people))]
    plan += [("quests", chunk) for chunk in _entry_pages(_quest_blocks(d, state))]
    plan += [("lore", chunk) for chunk in _entry_pages(_lore_blocks(d, state))]
    return plan


def _journal_pages(state, plan=None, number=None, link=None):
    """The journal's pages as pictures, in the one design -> (pages, links, portraits).

    `number(key)`: the page number shown for `key` -- "scene", "sheet" or "log" (the game's own pages) or a journal
    page's index -- or None: no number (the page is not in this document, or not there at all). `link(key)`: the page
    index a PDF's link goes to, or None (a notebook page holds no link). links: {page index: [(box, target)]};
    portraits: {page index: [(the portrait's picture, its box)]}, laid on the page as ink (_ink_pictures). Boxes in
    design pixels."""
    from paperdaemon.pipeline.draw import scaled as SD
    plan = plan or _journal_plan(state)
    number = number or (lambda key: None)
    link = link or (lambda key: None)
    h = state["hero"]
    hcm = h.get("height_cm")
    people = _people(state)
    first = {}
    for i, e in enumerate(plan):
        first.setdefault(e[0], i)
    person_at = {e[1]: i for i, e in enumerate(plan) if e[0] == "person"}
    grid_at = {k: i for i, e in enumerate(plan) if e[0] == "characters" for k in range(e[1], e[2])}
    name_f, name_lh, _ = _style("name")
    body_f, body_lh, _ = _style("body")
    small_f, small_lh, _ = _style("small")
    label_lh = _style("label")[1]
    pages, links, pics = [], {}, {}

    def numbered(d, key, x, y, room):
        """The page number for `key` at the right end of a line (x + room), gray, in the name face -> its width."""
        n = number(key) if key is not None else None
        if not n:
            return 0
        w = d.textlength(str(n), font=name_f)
        d.text((x + room - w, y), str(n), font=name_f, fill=GRAY)
        return w

    def go(i, box, key):
        t = link(key) if key is not None else None
        if t is not None:
            links.setdefault(i, []).append((box, t))

    def picture(d, i, p, box):
        """A person's portrait in its box: as ink over the page, or their initials when none was painted."""
        path = os.path.join(pictures_dir(state), p["portrait"]) if p.get("portrait") else None
        if path and os.path.exists(path):
            pics.setdefault(i, []).append((path, tuple(int(round(v)) for v in box)))
            return
        ini = "".join(w[0] for w in p["name"].split()[:2]).upper() or "?"
        f = _font(STYLES["title"][0], max(24, int((box[2] - box[0]) / 3)))
        d.text(((box[0] + box[2] - d.textlength(ini, font=f)) / 2.0, (box[1] + box[3]) / 2.0 - f.size * 0.62), ini,
               font=f, fill=RULE)

    for i, e in enumerate(plan):
        im, d = SD.canvas(PAGE_W, PAGE_H)             # (laid out in design pixels; sent at twice the tablet's resolution)
        kind = e[0]
        if kind != "contents":                        # in a PDF, the title of every journal page leads to the contents
            go(i, (X0, TITLE_Y - 10, X1, RULE_Y - 4), 0)
        if kind == "contents":
            # EVERY PAGE OF THE ADVENTURE, in page order, as a book's contents is: each page's name, a dotted leader,
            # its number -- the game's own pages when they are in this document, then, after a space, the journal's
            # sections that have a page. Its title is the adventure's own name. Nothing else: no headings over the
            # groups, no counts under the names ("10 things learned", "1 met"), no "None yet" for a section with no page.
            y = _header(d, state["title"])
            groups = []
            if number("scene") or link("scene") is not None:
                # in page order: a notebook's game starts at the scene, the book at the sheet
                groups.append(sorted([("Scene", "scene"), ("Character sheet", "sheet"), ("Story", "log")],
                                     key=lambda r: number(r[1]) or 0))
            groups.append([(t, first[k]) for t, k in (("Characters", "characters"), ("Quests", "quests"), ("Lore", "lore"))
                           if k in first])
            asc = name_f.getmetrics()[0]
            for g, rows in enumerate(groups):
                y += 36 if g else 0
                for title, key in rows:
                    d.text((X0, y), title, font=name_f, fill=INK)
                    nw = numbered(d, key, X0, y, CW)
                    if nw:
                        _leader(d, X0 + d.textlength(title, font=name_f) + 20, X1 - nw - 20, y + asc - 3)
                    go(i, (X0, y - 14, X1, y + name_lh + 14), key)
                    y += name_lh + 28
        elif kind == "characters":
            # THE CHARACTERS, six to a page: each portrait in its frame, the name under it, the page about them at the
            # right of the name, on its line; who they are under that
            _k, g0, g1 = e
            y0 = _header(d, "Characters")
            G = 36
            side = int((CW - 2 * G) / 3)
            for k in range(g0, g1):
                p = people[k]
                r, c = divmod(k - g0, 3)
                x, y = X0 + c * (side + G), y0 + r * (side + 146)
                box = (x + 6, y + 6, x + side - 6, y + side - 6)
                _frame(d, box)
                picture(d, i, p, box)
                ny = y + side + 16
                nw = numbered(d, person_at.get(k), x, ny, side)
                d.text((x, ny), _ellipsis(d, p["name"], name_f, side - (nw + 16 if nw else 0)), font=name_f, fill=INK)
                d.text((x, ny + name_lh), _ellipsis(d, _standing(p), small_f, side), font=small_f, fill=GRAY)
                go(i, (x, y, x + side, ny + name_lh + small_lh), person_at.get(k))
        elif kind == "person":
            # A PERSON: what the hero has seen and learned of them, nothing more -- the portrait, and at its right
            # their standing and what is on record (a field not known yet is not there at all); under both, with no
            # heading over them (the text says what it is), how they look, their personality and story once known,
            # and what the hero has learned of them, a bullet each
            p = people[e[1]]
            kn = p.get("known") or {"fields": [], "facts": []}
            f = set(kn.get("fields") or [])
            y0 = _header(d, p["name"], p.get("role") or "")
            ps = 470
            box = (X0 + 6, y0 + 6, X0 + ps - 6, y0 + ps - 6)
            _frame(d, box)
            picture(d, i, p, box)
            go(i, (X0, y0, X0 + ps, y0 + ps), grid_at.get(e[1]))     # (in a PDF, the portrait leads back to them all)
            facts = [("Status", "%s, %s%s" % (p["status"], p["disposition"],
                                               ("; " + ", ".join(p["conditions"])) if p["conditions"] else ""))]
            for field, label, value in (
                    ("class", "Class", lambda: p["class"] + ((", level %d" % p["level"]) if "level" in f else "")),
                    ("alignment", "Alignment", lambda: p["alignment"]),
                    ("record", "Record", lambda: "; ".join(p["criminal_record"]) or "none")):
                if field in f:
                    facts.append((label, value()))
            facts.append(("Met", "Turn %d, %s" % (p["met"]["turn"], p["met"]["place"] or "somewhere")))
            if (p["last_seen"]["turn"], p["last_seen"]["place"]) != (p["met"]["turn"], p["met"]["place"]):
                facts.append(("Last seen", "Turn %d, %s" % (p["last_seen"]["turn"], p["last_seen"]["place"] or "somewhere")))
            rx = X0 + ps + 44
            ry = y0
            for label, value in facts:
                _caps(d, (rx, ry), label)
                ry += label_lh
                for l in _wrap(d, value[:1].upper() + value[1:], body_f, X1 - rx)[:3]:
                    d.text((rx, ry), l, font=body_f, fill=INK)
                    ry += body_lh
                ry += 18
            y = max(y0 + ps, ry) + 44
            rows = [person_look(p, hcm).split(": ", 1)[-1]]
            rows += [p[k] for k in ("personality", "backstory") if k in f and p.get(k)]
            # what the hero knows of them: each thing on its own, a bullet and a hanging indent (joined into one line,
            # "footprints.; The stasis..." read as one broken sentence)
            known = [str(x).strip() for x in kn.get("facts") or [] if str(x).strip()]
            if known:
                rows.append(known)
            for value in rows:
                if y + body_lh > FOOT_Y:
                    break
                items = value if isinstance(value, list) else [value]
                for item in items:
                    bullet = isinstance(value, list) and len(items) > 1
                    dx = 30 if bullet else 0
                    for j, l in enumerate(_wrap(d, item[:1].upper() + item[1:], body_f, CW - dx)):
                        if y + body_lh > FOOT_Y:
                            break
                        if bullet and not j:
                            d.text((X0, y), "•", font=body_f, fill=INK)
                        d.text((X0 + dx, y), l, font=body_f, fill=INK)
                        y += body_lh
                    y += 6 if bullet else 0
                y += 24
        else:
            # QUESTS and LORE: their entries, each whole on one page
            y = _header(d, "Quests" if kind == "quests" else "Lore")
            for b in e[1]:
                y = _draw_rows(d, b, y) + ENTRY_GAP
        pages.append(im)
    return pages, links, pics


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
        # the journal alone in its document: its own pages numbered and linked, the game's pages are elsewhere
        pages, links, pics = _journal_pages(state, _journal_plan(state), number=lambda k: None if isinstance(k, str) else k + 1,
                                            link=lambda k: None if isinstance(k, str) else k)
        out_dir = os.path.join(paths.state_dir(), "rm-pdfdoc")
        os.makedirs(out_dir, exist_ok=True)
        pdf = PD.write_pdf([_bk(im) for im in pages], os.path.join(out_dir, "journal-%s.pdf" % state["id"]),
                           links=_bk_links(links))
        meta = json.load(open(os.path.join(PD.MIRROR, state["doc"] + ".metadata"), encoding="utf-8"))
        # staged in the mirror only: it reaches the tablet with the job's own push (sync.push_pending)
        doc, page_ids = PD.stage(journal_name(state), pdf, folder=meta.get("parent") or "", doc=jr.get("doc"),
                                 page_ids=jr.get("page_ids"))
        for i, items in pics.items():                 # (a restage starts from blank pages: the portraits go on as ink)
            _ink_pictures(doc, i + 1, items, BK, (BOOK_W, BOOK_H))
        state["journal"] = {"doc": doc, "page_ids": {str(k): v for k, v in page_ids.items()}, "sig": sig, "pages": len(pages)}
        _log(log, "  adventure: the journal is %d pages" % len(pages))
    except Exception as ex:
        _log(log, "  adventure: the journal was not updated: %s: %s" % (type(ex).__name__, str(ex)[:160]))


# ------------------------------------------------------------------------------ THE BOOK: the whole game, one PDF
# The journal belongs in the same document as the adventure, and is maintained there too. A link lives only in a
# PDF, and a notebook cannot hold PDF pages -- so a game is ONE PDF-backed document: page 1 the sheet, 2 the scene
# (its frame and text the PDF page, the scene's strokes and the player's writing the page's ink), 3 the log, 4+ the
# journal. Its links are the lines a book would have anyway: every line of the contents (the game's own pages
# among them) goes to its page, each person on the characters page to theirs, a person's portrait back to them all,
# and every journal page's title back to the contents. Every turn rebuilds the PDF IN PLACE (page ids kept); page
# 2's ink is cleared and drawn again, and so is each journal page whose picture changed (its portraits are ink). A
# PDF page is 1404 x 1872 page units, the notebook's 1620 x 2160 at 0.8667 (both 3:4, x centered), so every picture
# and stroke is the notebook's, scaled.
BOOK_W, BOOK_H = 1404, 1872
BK = BOOK_W / float(PAGE_W)


def is_book(state):
    return state.get("format") == "book"


def IM_K():
    from paperdaemon.pipeline.page.images import PICTURE_K
    return PICTURE_K


def _bk(src):                                           # (a book page: the book's pixels, PICTURE_K a pixel)
    """A page's picture (a file, or a picture) at the book's size."""
    from PIL import Image
    im = Image.open(src) if isinstance(src, str) else src
    try:
        return im.convert("RGB").resize((BOOK_W * IM_K(), BOOK_H * IM_K()), Image.LANCZOS)
    finally:
        if isinstance(src, str):
            im.close()


def _bk_links(links):
    """Links laid out in design pixels -> in the book's."""
    return {i: [(tuple(v * BK for v in box), t) for box, t in ls] for i, ls in links.items()}


def _book_pages(state, scene, roll_line, workdir, n=None):
    """Every page of the book as pictures, its links and the journal's portraits: 1 sheet, 2 scene, 3 log, 4+ the
    journal."""
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
    own = {"sheet": 0, "scene": 1, "log": 2}                 # (page indexes: the book's page numbers less one)
    jr, jr_links, pics = _journal_pages(state, _journal_plan(state),
                                        number=lambda k: own[k] + 1 if isinstance(k, str) else k + 4,
                                        link=lambda k: own[k] if isinstance(k, str) else k + 3)
    links = {i + 3: ls for i, ls in _bk_links(jr_links).items()}
    return out + [_bk(im) for im in jr], links, {i + 3: v for i, v in pics.items()}


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
    d.kind = "decomp"                                 # a picture traced into strokes (render.author_of)
    d.strokes = list(strokes)
    d.write_rm(doc, 2, keep_existing=True)
    return len(strokes), secs


def _render_book(doc, state, scene, roll_line, scene_png, workdir, log=None, name=None, parent=None, n=None):
    """The whole book again: every page's picture rebuilt in place, page 2's ink cleared and the scene drawn, and
    each journal page whose picture changed cleared and its portraits drawn as ink."""
    import hashlib
    pages, links, pics = _book_pages(state, scene, roll_line, workdir, n)
    was, drawn = list(state.get("book_pages") or []), dict(state.get("book_drawn") or {})
    sigs = {i: hashlib.sha1(pages[i].tobytes() + json.dumps(pics.get(i) or []).encode()).hexdigest()
            for i in range(3, len(pages))}
    redo = [i for i in sigs if i >= len(was) or drawn.get(was[i]) != sigs[i]]
    _write_book(doc, state, pages, links, name=name, parent=parent,
                reset=([state["page_id"]] if was else []) + [was[i] for i in redo if i < len(was)])
    if scene_png:
        k, secs = _draw_scene_book(doc, scene_png)
        _log(log, "  adventure: the scene is %d strokes (%.0fs)" % (k, secs))
    for i in redo:
        if pics.get(i):
            _ink_pictures(doc, i + 1, pics[i], BK, (BOOK_W, BOOK_H))
    ids = state["book_pages"]
    state["book_drawn"] = {ids[i]: sigs[i] for i in sigs}
    _log(log, "  adventure: the book is %d pages (journal %d, %d drawn again)" % (len(pages), len(pages) - 3, len(redo)))


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
                            "text": _clip(t["scene"].get("what_happened"), 300), "roll": ""} for t in state["turns"]]
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
# still land where they did. The scene, the sheet, the log, then the journal, each a page picture (the scene's and the
# portraits' strokes over their frames), drawn again in place turn after turn. A notebook page cannot hold a link, so
# nothing on these pages is drawn as one: the contents gives each page's number, as a printed book's does, and the
# characters page gives each person's at the right of their name.
def is_inline(state):
    return state.get("format") == "inline"


def _inline_journal(doc, state, workdir, log=None, force=False):
    """The journal's pages, after the log page: as many as it needs (pages added after the last of them, or taken
    back), each drawn again only when its picture changed -- what it says, or a page number it gives (pages put in
    before the game's move them) -- its portraits as ink. `force`: every page drawn again."""
    import hashlib
    from paperdaemon.remarkable import library as PG
    try:
        plan = _journal_plan(state)
        ids = [p for p in (state.get("journal_pages") or []) if _page_no(doc, p)]
        if len(ids) < len(plan):
            after = ids[-1] if ids else state["log_page"]
            ids += [pid for pid, _ in PG.insert_pages(doc, after, len(plan) - len(ids))]
        elif len(ids) > len(plan):
            PG.delete_pages(doc, ids[len(plan):])
            ids = ids[:len(plan)]
        state["journal_pages"] = ids
        state["pages"] = [state["sheet"]["page_id"], state["page_id"], state["log_page"]] + ids
        CH.save_state(state)
        own = {"scene": _page_no(doc, state["page_id"]), "sheet": _page_no(doc, state["sheet"]["page_id"]),
               "log": _page_no(doc, state["log_page"])}
        nums = [_page_no(doc, p) for p in ids]
        pages, _links, pics = _journal_pages(state, plan, number=lambda k: own.get(k) if isinstance(k, str) else nums[k])
        drawn = {} if force else dict(state.get("journal_drawn") or {})
        again = 0
        for i, (im, pid) in enumerate(zip(pages, ids)):
            sig = hashlib.sha1(im.tobytes() + json.dumps(pics.get(i) or []).encode()).hexdigest()
            if drawn.get(pid) == sig:
                continue
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
            if pics.get(i):
                frame = TB.frame_of(doc, pno)
                _ink_pictures(doc, pno, pics[i], TB.picture_page(frame)[1], frame)
            drawn[pid] = sig
            again += 1
        state["journal_drawn"] = {pid: drawn[pid] for pid in ids if pid in drawn}
        _log(log, "  adventure: the journal is %d pages, from page %d (%d drawn again)" % (
            len(ids), nums[0] if nums else 0, again))
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
    # (sheet, scene, log -- the order _inline_journal keeps them in; `here` makes the asking page the scene, not the first)
    sheet_id = state["sheet"]["page_id"]
    state["pages"], state["journal_pages"] = [sheet_id, state["page_id"], state["log_page"]], []
    # THE GAME IS SAVED BEFORE ITS PAGES ARE DRAWN: a job on one of them must find the game behind it
    CH.save_state(state)
    png = os.path.join(workdir, "_adv_sheet_%d.png" % int(time.time() * 1000))
    try:
        sheet_png(state, png)
        # ON THE SHEET'S OWN PAGE: drawn on ids[0], which `here` makes the scene's, the sheet went over the story,
        # and each turn's new sheet (_redraw_sheet, by this page) wiped the story off from then on
        state["sheet"] = _put_full(doc, _page_no(doc, sheet_id), sheet_id, png, "adventure-sheet", state)
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
             "around": str(op.get("around") or "")[:500], "options": [_clip(o, 96) for o in (op.get("options") or [])][:4]}
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
    state["events"] = [{"n": 0, "place": scene["place"], "text": _clip(scene["what_happened"], 300), "roll": ""}]
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
    if state["status"] not in ("playing", "dying"):
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
    h = unify(state["hero"])
    here = [n for n in (state.get("present") or []) if n in (state.get("cast") or {})]
    dying, died, how, saved = state["status"] == "dying", False, "", None
    cast, used = "", None
    if dying:
        # A DYING HERO'S TURN: a death save the engine rolls, or giving up -- nothing else is ruled on
        rule, possible, result, ck = {"understood": "a death save"}, True, None, None
        if death_choice(state, action, ask_text) == "give_up":
            died, how = True, "they gave up at death's door"
            roll_line = "%s gave up" % h["name"]
        else:
            saved = death_save(state)
            died, how = saved["died"], "%d death saves failed" % DEATH_SAVES
            roll_line = ("death save: %d, a success -- up with 1 hit point" % saved["roll"] if saved["success"] else
                         "death save: %d, a failure (%d of %d)" % (saved["roll"], saved["failed"], DEATH_SAVES))
    else:
        rule_q = RULE_PROMPT.format(hero=hero_line(h), place=state["place"] or "unknown", around=scene.get("around", ""),
                                    people=cast_block(state, here) if here else "- nobody the story has met",
                                    events=events_block(state, 6), action=action[:300], skills=", ".join(SKILLS),
                                    abilities=", ".join(ABILITIES))
        rule = parse_json(ask_vision(rule_q, shot) if shot and os.path.exists(shot) else ask_text(rule_q)) or {}
        possible = rule.get("possible", True) is not False
        result, roll_line = None, ""
        # THE SKILL USED: a spell costs its magic points, taken here; a cast the hero cannot pay for cannot be done
        used = find_skill(h, rule.get("skill")) if possible else None
        if used and used.get("cost"):
            cast = spend(h, used)
            if cast is None:
                possible, cast = False, ""
                rule["why_not"] = "%s costs %d MP and %s has %d" % (used["name"], used["cost"], h["name"], h["mp"]["now"])
        ck = rule.get("check") if possible else None
    if isinstance(ck, dict) and ck.get("key"):
        try:
            # AN ATTACK ON SOMEONE THE STORY KNOWS: their armor is the DC, and the damage is theirs (the engine's)
            kind = str(ck.get("kind") or "skill")
            key = str(ck["key"]).lower() if kind == "skill" else str(ck["key"]).upper()
            if kind == "skill" and key not in SKILLS:
                s = find_skill(h, key)                           # a skill by its proper name -> the check it trains
                key = s["trains"] if s and s.get("trains") else key
            target = find_person(state, ck.get("target")) if kind == "attack" else None
            result = check(state, kind, key, target["ac"] if target else int(ck.get("dc") or 12),
                           int(ck.get("advantage") or 0), used=used)
            roll_line = describe_check(result)
            if target and result.get("damage"):
                hurt(target, result["damage"])
                result["target"] = target["name"]
                roll_line += "; %s at %d/%d hit points" % (target["name"], target["hp"]["now"], target["hp"]["max"])
        except (ValueError, KeyError) as ex:
            _log(log, "  adventure: the check was not understood: %s" % ex)
    if dying and saved and saved["success"]:
        roll = "The engine rolled a death save: %d, a success: %s gets back up with 1 hit point." % (saved["roll"],
                                                                                                 h["name"])
    elif dying and saved and not died:
        left = DEATH_SAVES - saved["failed"]
        roll = ("The engine rolled a death save: %d, a failure (%d of %d): %s lies dying, unconscious at 0 hit points; "
                "%d more failure%s and they die, one success and they get back up with 1 hit point."
                % (saved["roll"], saved["failed"], DEATH_SAVES, h["name"], left, "" if left == 1 else "s"))
    elif not possible:
        roll = "It cannot be done: %s" % (rule.get("why_not") or "the scene does not allow it")
    elif result:
        roll = "The engine rolled: %s.%s" % (roll_line, (" %s." % cast) if cast else "")
    else:
        roll = "No roll was needed: it simply happens.%s" % ((" %s." % cast) if cast else "")
    if died:
        # THE HERO HAS DIED, AND THE STORY GOES ON (after_death): how, the model's to tell
        tell = parse_json(ask_text(AFTER_DEATH_PROMPT.format(
            title=state["title"], premise=state["premise"], tone=state["tone"], hero=hero_line(h), how=how,
            cast=cast_block(state), events=events_block(state), quests=quests_line(state),
            place=state["place"] or "unknown", around=scene.get("around", ""), person=PERSON_JSON,
            races=", ".join(RACES), classes=", ".join(CLASSES)))) or {}
    else:
        tell = parse_json(ask_text(TELL_PROMPT.format(title=state["title"], premise=state["premise"], tone=state["tone"],
                                                      hero=hero_line(h), look=hero_look(h), cast=cast_block(state),
                                                      events=events_block(state), place=state["place"] or "unknown",
                                                      around=scene.get("around", ""), action=action[:300],
                                                      understood=rule.get("understood") or action[:200], roll=roll,
                                                      person=PERSON_JSON, statuses=", ".join(STATUSES),
                                                      dispositions=", ".join(DISPOSITIONS), lore=lore_block(state),
                                                      quests=quests_line(state), fields=", ".join(KNOWABLE),
                                                      skills=", ".join(SKILLS)))) or {}
    allowed = list(rule.get("uses") or []) if possible else []
    if result and result["success"]:
        allowed += [g.get("name") if isinstance(g, dict) else g for g in ((tell.get("changes") or {}).get("gain") or [])]
    death_note = after_death(state, tell) if died else ""
    changes = tell.get("changes") or {}
    if dying and saved and not saved["success"] and not died and changes.get("hp") not in (None, "", 0, "0", "+0"):
        # A FAILED DEATH SAVE LEAVES THE HERO DYING: the story's hit points on that turn are not taken -- a failure and
        # "+1 hit point" at once got the hero up with no success, and the third failure never came. The dice decide.
        changes = dict(changes)
        changes.pop("hp", None)
    notes = apply(state, changes, allowed)
    if cast:
        notes.insert(0, cast)
    if death_note:
        notes.insert(0, death_note)
    if result and result.get("damage"):
        notes.append("dealt %d damage" % result["damage"])
    if tell.get("over") == "victory" and state["status"] == "playing":
        state["status"] = "victory"
    elif tell.get("over") == "death" and state["status"] == "playing" and not died:
        # STRUCK DOWN: the hero drops to 0 hit points and makes death saves; nobody simply dies
        state["hero"]["hp"]["now"] = 0
        state["status"], state["death_saves"] = "dying", {"failed": 0}
    new_scene = {"place": str(tell.get("place") or state["place"])[:80],
                 "what_happened": str(tell.get("what_happened") or "")[:1200],
                 "around": str(tell.get("around") or "")[:500],
                 "options": [_clip(o, 96) for o in (tell.get("options") or [])][:4]}
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
    pic = _scene_picture(paint, pic_spec, shot, newcomers, pictures, log)
    kept = _keep(state, n, pic) if pic else None
    last["action"], last["check"], last["notes"], last["understood"] = action, result, notes, rule.get("understood")
    if notes:
        roll_line = (roll_line + "  ·  " if roll_line else "") + "; ".join(notes)
    if people_notes:
        roll_line = (roll_line + "  ·  " if roll_line else "") + "; ".join(people_notes[:3])
    state.setdefault("events", []).append({"n": n - 1, "place": state["place"] or new_scene["place"],
                                           "text": _clip(tell.get("log") or new_scene["what_happened"], 300), "roll": roll_line})
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
        if notes or result or dying:
            _redraw_sheet(doc, state, workdir)
        if not is_inline(state):
            update_journal(state, log)
    CH.save_state(state)
    return "done", "ink adventure turn %d: %s%s" % (n - 1, action[:80], (" (%s)" % roll_line) if roll_line else "")


def hero_line(h):
    """The hero for the game master: who they are, their numbers, what they carry, every skill by its proper name with
    what it does and its figure (a trained check's bonus, a spell's cost), their conditions."""
    unify(h)
    magic = ("; magic %d/%d MP" % (h["mp"]["now"], h["mp"]["max"])) if h.get("mp") else ""
    return ("%s, a level %d %s %s (%s); %d/%d hit points, armor %d%s; carries %s; skills: %s; %s" % (
        h["name"], h["level"], h["race"], h["class"], h["background"], h["hp"]["now"], h["hp"]["max"], h["ac"], magic,
        ", ".join(it["name"] for it in h["inventory"]) or "nothing", "; ".join(skill_words(h)) or "none",
        ("conditions: " + ", ".join(h["conditions"])) if h["conditions"] else "no conditions"))
