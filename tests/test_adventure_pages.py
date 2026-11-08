"""An ink adventure's pages share ONE design (the user, 11-07: "no design language, no consistency", pages that "suggest
they are links but aren't", page numbers "sitting by things"): nothing is drawn as a button, a page number stands only
where a printed book puts one, a section with nothing in it has no page, every portrait goes on as ink, and the loose
ideas under a scene never start a line with a dot."""
import re

from PIL import Image, ImageDraw

from paperdaemon.pipeline.games import adventure as AD


def _person(name, portrait=None, turn=1):
    return {"name": name, "race": "human", "sex": "female", "age": "40s", "role": "smith", "class": "fighter",
            "level": 1, "alignment": "neutral", "ac": 12, "hp": {"now": 9, "max": 9}, "status": "alive",
            "disposition": "friendly", "conditions": [], "criminal_record": [], "backstory": "", "personality": "",
            "secret": "", "equipment": ["hammer"], "look": {"height_cm": 170, "build": "lean", "hair": "red"},
            "met": {"turn": turn, "place": "the forge"}, "last_seen": {"turn": turn + 1, "place": "the mill"},
            "notes": [], "portrait": portrait, "known": {"fields": ["class"], "facts": ["She shoes horses.",
                                                                                     "She owes the miller."]}}


def _state(people=(), quests=(), lore=()):
    hero = {"name": "Elara Vane", "level": 1, "race": "human", "class": "druid", "height_cm": 165}
    return {"title": "The Silent Swarm", "hero": hero, "cast": {p["name"]: p for p in people}, "quests": list(quests),
            "lore": list(lore), "events": [{"n": 0, "place": "Oakhaven", "text": "It begins.", "roll": ""}],
            "place": "Oakhaven Apiary", "doc": "doc", "id": "adv-test", "format": "inline", "turns": []}


def _watch(monkeypatch):
    """Every string drawn, and every rounded box (what a button looks like)."""
    said, rounded = [], []
    text, rr = ImageDraw.ImageDraw.text, ImageDraw.ImageDraw.rounded_rectangle

    def _text(self, xy, s, *a, **k):
        said.append(str(s))
        return text(self, xy, s, *a, **k)

    def _rr(self, *a, **k):
        rounded.append(a)
        return rr(self, *a, **k)
    monkeypatch.setattr(ImageDraw.ImageDraw, "text", _text)
    monkeypatch.setattr(ImageDraw.ImageDraw, "rounded_rectangle", _rr)
    return said, rounded


def test_nothing_on_a_notebook_journal_is_drawn_as_a_button_or_a_page_badge(tmp_path, monkeypatch):
    monkeypatch.setattr(AD, "pictures_dir", lambda st: str(tmp_path))
    said, rounded = _watch(monkeypatch)
    st = _state([_person("Mira"), _person("Tamsin", turn=2)], quests=[{"name": "The Swarm", "goal": "Find out why.",
                                                                    "status": "open", "turn": 1, "updates": []}])
    plan = AD._journal_plan(st)
    nums = list(range(5, 5 + len(plan)))
    pages, links, _pics = AD._journal_pages(st, plan, number=lambda k: {"scene": 1, "sheet": 2, "log": 3}.get(k)
                                            if isinstance(k, str) else nums[k])
    assert len(pages) == len(plan) and links == {}                # a notebook page holds no link
    assert rounded == []                                          # no rounded box anywhere: nothing looks tappable
    assert not [s for s in said if re.match(r"^p\. ?\d+$", s) or "Journal: p." in s]
    assert "Contents" not in said and st["title"] in said        # no "Contents" buttons; the adventure's name titles it
    # the page numbers stand where a book puts them: the contents' right column, at the right of each name
    assert str(nums[plan.index(("person", 1))]) in said and "1" in said and "2" in said


def test_the_sheet_the_scene_and_the_log_have_no_buttons_either(tmp_path, monkeypatch):
    said, rounded = _watch(monkeypatch)
    st = _state()
    st["hero"] = AD.make_hero({"name": "Elara Vane", "race": "human", "class": "druid"}, AD.CH.Rng("0f" * 16))
    scene = {"place": "Oakhaven Apiary", "what_happened": "The hives are silent.", "around": "Mist.",
             "options": ["Open a hive", "Call for Barnaby"]}
    AD.sheet_png(st, str(tmp_path / "sheet.png"))
    AD.turn_png(st, scene, str(tmp_path / "turn.png"))
    AD.log_png(st, str(tmp_path / "log.png"))
    assert rounded == [] and "Journal" not in " ".join(said)
    assert "Elara Vane" in said and "Story" in said and "Oakhaven Apiary" in said


def test_no_kicker_and_no_heading_over_text_that_says_what_it_is(tmp_path, monkeypatch):
    # the user, 11-08: "WHY DO YOU ALWAYS LABEL THINGS LIKE THIS" -- over-labeling is "the biggest giveaway" of AI
    monkeypatch.setattr(AD, "pictures_dir", lambda st: str(tmp_path))
    labels, real = [], AD._caps
    monkeypatch.setattr(AD, "_caps", lambda d, xy, text, *a, **k: labels.append(str(text).upper()) or real(d, xy, text, *a, **k))
    st = _state([_person("Mira")], lore=[{"turn": 1, "text": "The bees sleep."}])
    st["hero"] = AD.make_hero({"name": "Elara Vane", "race": "human", "class": "druid", "personality": "Calm."},
                              AD.CH.Rng("0f" * 16))
    AD.sheet_png(st, str(tmp_path / "sheet.png"))
    AD.turn_png(st, {"place": "Oakhaven Apiary", "what_happened": "Silence.", "around": "Mist.", "options": []},
                str(tmp_path / "turn.png"))
    AD.log_png(st, str(tmp_path / "log.png"))
    AD._journal_pages(st)
    assert labels and not [l for l in labels if st["title"].upper() in l]     # no kicker naming the adventure
    assert not {"WHO THEY ARE", "WHAT YOU KNOW", "NOT YET KNOWN", "LOOKS", "THE ADVENTURE", "JOURNAL"} & set(labels)


def test_a_section_with_nothing_in_it_has_no_page_and_no_line_in_the_contents(tmp_path, monkeypatch):
    monkeypatch.setattr(AD, "pictures_dir", lambda st: str(tmp_path))
    said, _ = _watch(monkeypatch)
    st = _state([_person("Mira")])
    plan = AD._journal_plan(st)
    assert [e[0] for e in plan] == ["contents", "characters", "person"]
    AD._journal_pages(st, plan, number=lambda k: {"scene": 1, "sheet": 2, "log": 3}.get(k) if isinstance(k, str) else k + 4)
    assert "Characters" in said and "Quests" not in said and "Lore" not in said


def test_no_page_counts_what_is_on_it(tmp_path, monkeypatch):
    # the user, 11-08, of "10 things learned": "this stuff is literally making my stomach turn"
    monkeypatch.setattr(AD, "pictures_dir", lambda st: str(tmp_path))
    said, _ = _watch(monkeypatch)
    st = _state([_person("Mira")], quests=[{"name": "The Swarm", "goal": "Find out why.", "status": "open", "turn": 1,
                                           "updates": []}], lore=[{"turn": 1, "text": "The bees sleep."}])
    st["events"] += [{"n": 1, "place": "Oakhaven", "text": "She looked.", "roll": ""}]
    AD._journal_pages(st)
    AD.log_png(st, str(tmp_path / "log.png"))
    counts = re.compile(r"\b(learned|played|met|in all|yet)\b|^\d+ open")
    assert not [s for s in said if counts.search(s)]


def test_six_people_to_a_characters_page(tmp_path, monkeypatch):
    monkeypatch.setattr(AD, "pictures_dir", lambda st: str(tmp_path))
    plan = AD._journal_plan(_state([_person("P%d" % i, turn=i) for i in range(7)]))
    assert [e for e in plan if e[0] == "characters"] == [("characters", 0, 6), ("characters", 6, 7)]


def test_every_portrait_goes_on_as_ink_inside_its_frame(tmp_path, monkeypatch):
    monkeypatch.setattr(AD, "pictures_dir", lambda st: str(tmp_path))
    Image.new("RGB", (64, 64), "white").save(str(tmp_path / "mira.png"))
    st = _state([_person("Mira", portrait="mira.png"), _person("Tamsin")])
    plan = AD._journal_plan(st)
    _pages, _links, pics = AD._journal_pages(st, plan)
    grid, page = plan.index(("characters", 0, 2)), plan.index(("person", 0))
    for i in (grid, page):
        [(png, box)] = pics[i]                                    # Mira's; Tamsin has none, so her initials are drawn
        assert png.endswith("mira.png") and AD.X0 <= box[0] < box[2] <= AD.X1
    assert plan.index(("person", 1)) not in pics


def test_in_a_pdf_the_contents_lines_and_people_are_links(tmp_path, monkeypatch):
    monkeypatch.setattr(AD, "pictures_dir", lambda st: str(tmp_path))
    st = _state([_person("Mira")])
    plan = AD._journal_plan(st)
    own = {"sheet": 0, "scene": 1, "log": 2}
    _pages, links, _pics = AD._journal_pages(st, plan, number=lambda k: own[k] + 1 if isinstance(k, str) else k + 4,
                                             link=lambda k: own[k] if isinstance(k, str) else k + 3)
    assert sorted(t for _b, t in links[0]) == [0, 1, 2, 3 + plan.index(("characters", 0, 1))]
    assert 3 + plan.index(("person", 0)) in [t for _b, t in links[plan.index(("characters", 0, 1))]]


def test_the_loose_ideas_never_start_a_line_with_a_dot():
    d = ImageDraw.Draw(Image.new("RGB", (8, 8)))
    f = AD._style("small")[0]
    opts = ["Ask what the drones looked like before the spell was cast.", "Check if the stasis is weakening.",
            "Demand to know why he didn't tell the village immediately.", "Leave."]
    lines = AD._idea_lines(d, opts, f, AD.CW)
    assert len(lines) > 1 and lines[0].startswith("You could: Ask")
    assert not any(l.lstrip().startswith("·") for l in lines)


def test_kept_portrait_strokes_read_back_as_the_corpus_reader_reads_them(tmp_path):
    from paperdaemon.pipeline import decompose as M
    from paperdaemon.pipeline.draw import Pen, PenColor
    strokes = [([(0.0, 1.5), (2.25, 3.0)], [1.0, 2.5], Pen(17), PenColor(9), (185, 162, 162)),
               ([(5.0, 5.0), (6.0, 7.5), (8.0, 9.0)], [2.0, 2.0, 2.0], Pen(18), PenColor(9), None)]
    path = str(tmp_path / "p.npz")
    M.save_strokes(path, strokes)
    assert AD._load_ink(path) == M.load_strokes(path)
