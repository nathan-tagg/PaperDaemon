"""A hero's skills are ONE list of named skills (the user, 11-09: "Each skill should have a proper name, not just
'+3 perception'. And spells should have an mp cost. Again, skills, spells, special abilities, everything, should be
'skills' in ink adventure - to keep things simple"): trained skills, the class's and race's special abilities and the
spells, each with a proper name and what it does; casters have magic points, and a cast costs its points."""
from PIL import ImageDraw

from paperdaemon.pipeline.games import adventure as AD

SEED = "0f" * 16


def _hero(cls, race="human", skills=(), name="Elara Vane"):
    return AD.make_hero({"name": name, "race": race, "class": cls, "skills": list(skills)}, AD.CH.Rng(SEED))


def _state(h):
    st = AD.new_state("doc", "The Drowning Light", "x", "eerie", h, seed=SEED)
    st["page_id"] = "pid"
    return st


def _said(monkeypatch):
    said, text = [], ImageDraw.ImageDraw.text

    def _text(self, xy, s, *a, **k):
        said.append(str(s))
        return text(self, xy, s, *a, **k)
    monkeypatch.setattr(ImageDraw.ImageDraw, "text", _text)
    return said


def test_every_skill_has_a_proper_name_and_the_old_lists_are_gone():
    h = _hero("wizard", "elf", ["perception", "arcana"])
    names = [s["name"] for s in h["skills"]]
    assert "features" not in h and "spells" not in h and "talents" not in h
    assert all(n[:1].isupper() and not n.startswith("+") and n.lower() not in AD.SKILLS for n in names)
    assert "Arcane Lore" in names and "Fire Bolt" in names and "Arcane Recovery" in names and "Darkvision" in names
    assert "Spellcasting" not in names                           # the spells themselves say it
    # the elf's Keen Senses IS the perception proficiency: asked for perception, the hero is not trained in it twice
    assert [s["name"] for s in h["skills"] if s.get("trains") == "perception"] == ["Keen Senses"]
    assert all(s.get("effect") for s in h["skills"])


def test_spells_cost_magic_points_and_only_casters_have_them():
    w, f = _hero("wizard"), _hero("fighter")
    spells = [s for s in w["skills"] if s["kind"] == "spell"]
    assert spells and all(s["cost"] in (1, 2) for s in spells)
    assert next(s for s in spells if s["name"] == "Fire Bolt")["cost"] == 1 and next(s for s in spells if s["name"] == "Fire Bolt")["die"] == "1d10"
    assert next(s for s in spells if s["name"] == "Magic Missile")["cost"] == 2
    assert w["mp"]["max"] == w["mp"]["now"] == 4 + max(0, AD.mod(w["abilities"]["INT"]))
    assert "mp" not in f and not [s for s in f["skills"] if s.get("cost")]
    assert [s["name"] for s in f["skills"]][2:] == ["Defensive Style", "Second Wind"]


def test_the_trained_check_runs_through_the_named_skill():
    r = _hero("rogue", "halfling", ["stealth", "sleight of hand", "perception"])
    dex, p = AD.mod(r["abilities"]["DEX"]), AD.prof(1)
    assert AD.bonus(r, "skill", "stealth") == dex + 2 * p                 # Expertise: the first two trained, twice
    assert AD.bonus(r, "skill", "perception") == AD.mod(r["abilities"]["WIS"]) + p
    assert AD.bonus(r, "skill", "athletics") == AD.mod(r["abilities"]["STR"])
    assert next(s for s in r["skills"] if s["name"] == "Expertise")["effect"] == "proficiency counted twice in Shadow Step and Quick Fingers"
    assert AD.skill_figure(r, r["skills"][0]) == "Stealth %+d" % (dex + 2 * p)
    assert AD.find_skill(r, "Shadow Step") is r["skills"][0] and AD.find_skill(r, "stealth") is r["skills"][0]


def test_a_cast_costs_its_points_and_one_the_hero_cannot_pay_for_does_not_happen():
    w = _hero("wizard")
    fire = AD.find_skill(w, "fire bolt")
    w["mp"]["now"] = 1
    assert AD.spend(w, fire) == "Fire Bolt cast for 1 MP (0 left)" and w["mp"]["now"] == 0
    assert AD.spend(w, AD.find_skill(w, "Magic Missile")) is None and w["mp"]["now"] == 0
    assert AD.spend(w, AD.find_skill(w, "Arcane Recovery")) == ""          # no cost, nothing taken
    # a spell attack rolls the spell's dice with the casting ability, and is named in the roll
    st = _state(w)
    r = AD.check(st, "attack", "INT", 5, used=fire)
    assert r["bonus"] == AD.mod(w["abilities"]["INT"]) + AD.prof(1) and r.get("with") == "Fire Bolt"
    if r["success"]:
        assert 1 <= r["damage"] <= 20 and len(r["damage_dice"]) in (1, 2)
    assert AD.describe_check(r).startswith("Fire Bolt: rolled")


def test_the_story_grants_named_skills_and_rest_brings_magic_back():
    f = _hero("fighter")
    st = _state(f)
    notes = AD.apply(st, {"skills_gain": [{"name": "Harbor Watch", "effect": "knows every hull in the bay", "cost": 0},
                                          {"name": "Saltlight", "effect": "calls a cold light from the sea", "cost": 1},
                                          "perception", "Harbor Watch", {"name": "+3 perception"}]})
    assert notes[:3] == ["learned Harbor Watch", "learned Saltlight (1 MP)", "trained in Keen Eye (perception)"]
    assert "already known: Harbor Watch" in notes
    assert f["mp"]["now"] == f["mp"]["max"] >= 4                        # a spell learned brings magic with it
    assert [s["name"] for s in f["skills"]][-4:] == ["Harbor Watch", "Saltlight", "Keen Eye", "+3 perception"]
    f["mp"]["now"] = 1
    assert AD.apply(st, {"mp": "+2"}) == ["magic +2 (3/%d)" % f["mp"]["max"]]
    assert AD.apply(st, {"mp": "all"}) == ["magic +%d (%d/%d)" % (f["mp"]["max"] - 3, f["mp"]["max"], f["mp"]["max"])]
    assert AD.apply(st, {"mp": "+2"}) == []                               # full stays full
    assert AD.apply(st, {"mp": "-1"}) == ["magic: a cast's cost is taken by the engine, not the story"]
    assert f["mp"]["now"] == f["mp"]["max"]                              # the story cannot spend it (DF215 took a cast twice)
    assert AD.apply(_state(_hero("fighter")), {"mp": "all"}) == ["no magic to restore"]


def test_an_older_hero_is_read_as_one_list():
    h = _hero("wizard", "elf")
    old = dict(h, skills=["arcana", "history"], spells=["fire bolt", "light"], talents=[
        {"name": "Gull-Speech", "kind": "talent", "effect": "speaks with gulls", "mods": {"perception": 1}}],
        features=["Spellcasting", "Arcane Recovery", "Darkvision", "Keen Senses", "Fighting Style: Defense"])
    old.pop("mp")
    names = [s["name"] for s in AD.skills_of(old)]
    assert names == ["Arcane Lore", "Old Chronicles", "Arcane Recovery", "Darkvision", "Keen Senses", "Defensive Style",
                     "Fire Bolt", "Light", "Gull-Speech"]
    assert "spells" not in old and "features" not in old and "talents" not in old and old["mp"]["max"] >= 4
    assert AD.bonus(old, "skill", "perception") == AD.mod(old["abilities"]["WIS"]) + AD.prof(1) + 1
    assert "skills: Arcane Lore (knows magic, its signs and its makers; Arcana" in AD.hero_line(old)
    assert "Gull-Speech (speaks with gulls; +1 Perception)" in AD.hero_line(old) and "magic" in AD.hero_line(old)


def test_the_sheet_shows_one_skills_list_with_names_figures_and_magic(tmp_path, monkeypatch):
    said = _said(monkeypatch)
    w = _hero("wizard", "elf", ["arcana"])
    AD.sheet_png(_state(w), str(tmp_path / "w.png"))
    assert "Arcane Lore" in said and "Fire Bolt" in said and "1 MP" in said and "2 MP" in said
    assert "Arcana %+d" % AD.bonus(w, "skill", "arcana") in said and "knows magic, its signs and its makers" in said
    assert "%d / %d" % (w["mp"]["now"], w["mp"]["max"]) in said
    caps = [s for s in said if len(s) == 1]                            # labels are lettered one capital at a time
    assert "".join(caps).count("SKILLS") == 1 and "FEATURES" not in "".join(caps) and "MAGIC" in "".join(caps)
    assert not [s for s in said if s.startswith("+") and len(s.split()) == 2 and s.split()[1].lower() in AD.SKILLS]
    said.clear()
    AD.sheet_png(_state(_hero("fighter")), str(tmp_path / "f.png"))
    assert "MAGIC" not in "".join(s for s in said if len(s) == 1) and "Second Wind" in said and "MP" not in " ".join(said)
