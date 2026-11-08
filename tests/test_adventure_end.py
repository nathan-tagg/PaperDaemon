"""An ink adventure that is over says so on its last scene page, where the next move's ideas would be: a story that
ended still showed "You could: ..." for a turn no game would take (a finished game gives its page back)."""
from PIL import ImageDraw

from paperdaemon.pipeline.games import adventure as AD


def _drawn(tmp_path, status, monkeypatch):
    said = []
    real = ImageDraw.ImageDraw.text

    def text(self, xy, s, *a, **k):
        said.append(str(s))
        return real(self, xy, s, *a, **k)
    monkeypatch.setattr(ImageDraw.ImageDraw, "text", text)
    state = {"turns": [{}] * 6, "place": "Oakhaven Apiary", "title": "The Silent Swarm",
             "hero": {"name": "Elara Vane"}, "status": status}
    scene = {"place": "Oakhaven Apiary", "what_happened": "The swarm closes in.", "around": "The hives hum on.",
             "options": ["Crawl to the cart", "Call for Barnaby"]}
    AD.turn_png(state, scene, str(tmp_path / ("%s.png" % status)))
    return said


def test_an_adventure_that_is_over_says_so_instead_of_offering_a_next_move(tmp_path, monkeypatch):
    assert "The end: Elara Vane has fallen." in _drawn(tmp_path, "down", monkeypatch)
    assert "The end: a victory." in _drawn(tmp_path, "victory", monkeypatch)
    died = _drawn(tmp_path, "death", monkeypatch)
    assert "The end: Elara Vane has died." in died and not any(s.startswith("You could") for s in died)


def test_one_still_played_offers_its_loose_ideas(tmp_path, monkeypatch):
    said = _drawn(tmp_path, "playing", monkeypatch)
    assert any(s.startswith("You could: Crawl to the cart") for s in said)
    assert not any(s.startswith("The end") for s in said)


def test_a_turn_where_nothing_in_view_changed_keeps_its_picture_and_never_takes_the_card(tmp_path):
    # an "edit" for a few words took 40 s to change nothing the page shows, and the text model came back cold
    from PIL import Image
    shot = tmp_path / "003.png"
    Image.new("RGB", (8, 8)).save(shot)
    calls = []

    class Paint(object):
        def session(self, fn):
            calls.append("card")
            return fn()

    def painted():
        calls.append("painted")
        return str(shot)
    assert AD._scene_picture(Paint(), {"mode": "keep"}, str(shot), [], painted) == str(shot) and calls == []
    AD._scene_picture(Paint(), {"mode": "keep"}, str(shot), [{"name": "Jory"}], painted)
    assert calls == ["card", "painted"]                  # someone new came: they are painted, the scene with them
    del calls[:]
    AD._scene_picture(Paint(), {"mode": "edit"}, str(shot), [], painted)
    assert calls == ["card", "painted"]
    del calls[:]
    AD._scene_picture(Paint(), {"mode": "keep"}, str(tmp_path / "none.png"), [], painted)
    assert calls == ["card", "painted"]                  # no picture to keep: one is painted


# ------------------------------------------------------------------ death saves, and after a death (the ruling, 11-07)
SEED = "0123456789abcdef0123456789abcdef"
_REAL_RNG = AD.CH.Rng


class _Dice(_REAL_RNG):
    """The engine's dice, set: each randint gives the next number set, then the real dice's."""
    rolls = []

    def randint(self, a, b):
        return _Dice.rolls.pop(0) if _Dice.rolls else _REAL_RNG.randint(self, a, b)


def _hero_state():
    rng = _REAL_RNG(seed=SEED, draws=0)
    hero = AD.make_hero({"name": "Elara Vane", "race": "elf", "class": "fighter"}, rng)
    st = AD.new_state("doc", "The Silent Swarm", "A queen gone mad.", "eerie", hero, seed=SEED)
    st["page_id"] = "pid"
    st["turns"] = [{"n": 1, "page_id": "pid", "scene": {"place": "Oakhaven Apiary", "what_happened": "Bees.",
                                                       "around": "Hives.", "options": []}, "picture": None}]
    st["place"] = "Oakhaven Apiary"
    return st


def test_at_no_hit_points_the_hero_is_dying_not_dead_and_healed_is_up_again():
    st = _hero_state()
    AD.apply(st, {"hp": -999})
    assert st["status"] == "dying" and st["death_saves"] == {"failed": 0} and st["hero"]["hp"]["now"] == 0
    AD.apply(st, {"hp": 3})
    assert st["status"] == "playing" and "death_saves" not in st


def test_one_death_save_and_the_hero_is_up_three_failed_and_they_die(monkeypatch):
    monkeypatch.setattr(AD.CH, "Rng", _Dice)
    st = _hero_state()
    AD.apply(st, {"hp": -999})
    _Dice.rolls = [14]
    r = AD.death_save(st)
    assert r["success"] and not r["died"] and st["status"] == "playing" and st["hero"]["hp"]["now"] == 1
    AD.apply(st, {"hp": -999})
    _Dice.rolls = [5, 9, 2]
    got = [AD.death_save(st) for _ in range(3)]
    assert [g["failed"] for g in got] == [1, 2, 3] and [g["died"] for g in got] == [False, False, True]


def test_the_player_chooses_to_roll_or_give_up_and_the_model_reads_which():
    st = _hero_state()
    st["status"], st["death_saves"] = "dying", {"failed": 1}
    asked = []

    def model(answer):
        def ask(prompt):
            asked.append(prompt)
            return answer
        return ask
    assert AD.death_choice(st, "I let go", model("GIVE_UP")) == "give_up"
    assert AD.death_choice(st, "roll!", model("ROLL")) == "roll"
    assert AD.death_choice(st, "hmm", model("")) == "roll"           # anything but giving up is a roll
    assert "1 of" in asked[0] and "I let go" in asked[0]


def test_after_a_death_the_story_goes_on_with_a_successor_or_the_hero_themselves():
    st = _hero_state()
    st["status"], st["death_saves"] = "dying", {"failed": 3}
    note = AD.after_death(st, {"way": "a niece takes up the sword", "successor": {
        "name": "Mira Vane", "race": "human", "class": "rogue", "backstory": "Elara's niece."}})
    assert st["status"] == "playing" and "death_saves" not in st
    assert st["hero"]["name"] == "Mira Vane" and st["fallen"][0]["name"] == "Elara Vane"
    assert st["hero"]["hp"]["now"] == st["hero"]["hp"]["max"] > 0 and "Mira Vane" in note
    st2 = _hero_state()
    st2["hero"]["hp"]["now"], st2["status"] = 0, "dying"
    AD.after_death(st2, {"way": "she wakes in the great beyond", "successor": None})
    assert st2["hero"]["name"] == "Elara Vane" and st2["hero"]["hp"]["now"] == st2["hero"]["hp"]["max"]
    assert st2["status"] == "playing"


def test_a_dying_heros_page_offers_a_death_save_or_giving_up(tmp_path, monkeypatch):
    said = _drawn(tmp_path, "dying", monkeypatch)
    assert any(s.startswith("You could: Roll a death save") and "Give up" in s for s in said)
    assert "Elara Vane is dying: 0 of 3 death saves failed." in said
    assert not any("Crawl to the cart" in s for s in said) and not any(s.startswith("The end") for s in said)


def test_a_dying_turn_rolls_the_save_and_the_last_failure_carries_the_story_on(tmp_path, monkeypatch):
    import json
    monkeypatch.setattr(AD.CH, "Rng", _Dice)
    for name in ("_fixed", "_draw_play_page", "_redraw_log", "_redraw_sheet", "update_journal", "_inline_journal"):
        monkeypatch.setattr(AD, name, lambda *a, **k: None)
    monkeypatch.setattr(AD.CH, "save_state", lambda *a, **k: None)
    monkeypatch.setattr(AD, "_scene_picture", lambda *a, **k: None)
    monkeypatch.setattr(AD, "is_book", lambda st: False)
    monkeypatch.setattr(AD, "is_inline", lambda st: False)
    monkeypatch.setattr(AD, "read_action", lambda *a, **k: "I roll the save")
    st = _hero_state()
    AD.apply(st, {"hp": -999})
    asked = []

    def text(prompt):
        asked.append(prompt)
        if "ROLL or GIVE_UP" in prompt:
            return "ROLL"
        if "HAS DIED" in prompt:
            return json.dumps({"way": "she wakes in the great beyond", "what_happened": "You die. Then light.",
                               "log": "Elara died and woke beyond.", "place": "The Great Beyond",
                               "around": "Silver mist.", "options": ["Walk toward the light"], "successor": None,
                               "picture": {"mode": "new", "prompt": "silver mist"}})
        return json.dumps({"what_happened": "You slip further.", "log": "Elara clung on.", "place": "Oakhaven Apiary",
                           "around": "Hives.", "options": ["x"], "same_place": True, "picture": {"mode": "keep"}})
    _Dice.rolls = [3]
    out = AD.turn("doc", 1, "pid", st, text, lambda *a: "", workdir=str(tmp_path))
    assert out[0] == "done" and "death save: 3, a failure (1 of 3)" in out[1]
    assert st["status"] == "dying" and st["death_saves"]["failed"] == 1
    assert "a failure (1 of 3): Elara Vane lies dying" in asked[-1] and "2 more failures" in asked[-1]
    st["death_saves"]["failed"] = 2
    _Dice.rolls = [4]
    out = AD.turn("doc", 1, "pid", st, text, lambda *a: "", workdir=str(tmp_path))
    assert out[0] == "done" and st["status"] == "playing" and st["hero"]["hp"]["now"] == st["hero"]["hp"]["max"]
    assert any("HAS DIED" in a for a in asked) and st["place"] == "The Great Beyond"


def test_a_failed_death_save_is_not_undone_by_the_storys_healing(tmp_path, monkeypatch):
    # round 15: "death save: 5, a failure (2 of 3) · hit points +1 (1/14)" -- up with no success
    import json
    monkeypatch.setattr(AD.CH, "Rng", _Dice)
    for name in ("_fixed", "_draw_play_page", "_redraw_log", "_redraw_sheet", "update_journal", "_inline_journal"):
        monkeypatch.setattr(AD, name, lambda *a, **k: None)
    monkeypatch.setattr(AD.CH, "save_state", lambda *a, **k: None)
    monkeypatch.setattr(AD, "_scene_picture", lambda *a, **k: None)
    monkeypatch.setattr(AD, "is_book", lambda st: False)
    monkeypatch.setattr(AD, "is_inline", lambda st: False)
    monkeypatch.setattr(AD, "read_action", lambda *a, **k: "roll")
    st = _hero_state()
    AD.apply(st, {"hp": -999})

    def text(prompt):
        if "ROLL or GIVE_UP" in prompt:
            return "ROLL"
        return json.dumps({"what_happened": "You stir.", "log": "x", "place": "Oakhaven Apiary", "around": "Hives.",
                           "options": [], "same_place": True, "picture": {"mode": "keep"}, "changes": {"hp": "+1"}})
    _Dice.rolls = [5]
    AD.turn("doc", 1, "pid", st, text, lambda *a: "", workdir=str(tmp_path))
    assert st["status"] == "dying" and st["hero"]["hp"]["now"] == 0 and st["death_saves"]["failed"] == 1
