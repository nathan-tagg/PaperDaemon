"""The Concord as a game (design D5, D8): the family from the request, a new state with its seven families and their
planned orders, a season resolved from the user's orders, letters addressed by name, promises settled by the orders
that followed."""
from paperdaemon.pipeline.games import chess as CH
from paperdaemon.pipeline.games.concord import game as G
from paperdaemon.pipeline.games.concord import letters as LT
from paperdaemon.pipeline.games.concord import map as M
from paperdaemon.pipeline.games.concord import orders as O
from paperdaemon.pipeline.games.concord import rules as R


def test_the_family_is_read_from_the_request():
    assert G.family_from("start the Concord as the Hales") == "hale"
    assert G.family_from("a game of the Concord, I am Harriet Oakes") == "oakes"
    assert G.family_from("start the concord") == "quill" and G.family_from("play the Strouds") == "stroud"


def test_a_new_state_has_seven_families_and_the_cast_s_orders_planned():
    st = G.new_state("doc", "oakes", seed="ab" * 16)
    assert set(st["families"]) == set(M.FAMILIES) and st["families"]["oakes"]["cast"] is None
    assert st["families"]["oakes"]["player"] == "you" and st["families"]["graves"]["player"].startswith("Ottoline")
    assert len(st["units"]) == 14 and R.standing(st["owners"]) == {f: 2 for f in M.FAMILIES}
    assert set(st["planned"]) == set(M.FAMILIES) - {"oakes"}
    for f, orders in st["planned"].items():
        assert set(orders) == {s for s, u in st["units"].items() if u["family"] == f}
        assert all(R.legal(st["units"], o)[0] for o in orders.values())
    assert st["accords"][G.MI.pair("hale", "shellby")] != 0 if hasattr(G, "MI") else True


def test_a_season_resolves_the_user_s_orders_with_the_cast_s():
    st = G.new_state("doc", "quill", seed="12" * 16)
    lines = ["Harbor Row to Fogwater", "the Archive to Merrow Point"]
    mine, wants, problems = O.parse(lines, st["units"], "quill")
    assert set(mine) == {"harbor-row", "the-archive"} and not problems
    note = G.season(st, mine, wants, problems, ask_text=None)
    assert st["season_no"] == 1 and "Spring, year 1 resolved" in note
    assert st["last"]["mine"][0][0] == "Harbor Row to Fogwater" and st["last"]["mine"][0][1] in ("moved", "failed: stood off", "failed: turned back")
    assert st["log"][0]["season_no"] == 0 and any(line.startswith("The Quills:") for line in st["log"][0]["lines"])
    assert set(st["planned"]) == set(M.FAMILIES) - {"quill"}                # the next season is planned
    # the autumn counts harbors and builds
    mine, wants, problems = O.parse(["Merrow Point holds", "Fogwater holds"], st["units"], "quill") if "merrow-point" in st["units"] and st["units"]["merrow-point"]["family"] == "quill" else ({}, {"build": [], "disband": []}, [])
    G.season(st, mine, wants, problems, ask_text=None)
    assert st["season_no"] == 2 and sum(R.standing(st["owners"]).values()) >= 14


def test_letters_are_addressed_by_name_and_promises_are_settled_by_deeds():
    st = G.new_state("doc", "quill", seed="34" * 16)
    got = LT.families_named(st, "To Harriet,\nLeave Kettle Isle to me and I will back you at the Sound.\n\nJudge Shellby: a fair season to you.")
    assert [f for f, _ in got] == ["oakes", "shellby"] and got[0][1].startswith("Leave Kettle Isle")
    assert LT.families_named(st, "Hales -- stay out of the Sound") == [("hale", "stay out of the Sound")]
    assert LT.families_named(st, "nobody in particular") == []
    # a promise kept warms the accord and is counted; one broken cools it
    st["promises"] = [{"by": "oakes", "to_family": "quill", "kind": "no_attack", "keep": True, "until": 1, "season_no": 0},
                      {"by": "graves", "to_family": "quill", "kind": "support", "unit": "harbor-row", "to": "fogwater", "keep": False, "until": 1, "season_no": 0}]
    st["season_no"] = 1
    st["units_before"] = dict(st["units"])
    orders = {}
    for o in st["planned"].values():
        orders.update(o)
    before = dict(st["accords"])
    result = R.resolve(st["units"], orders)
    notes = LT.settle(st, result)
    assert "The Oakes kept their word (no attack)" in notes or "The Oakes broke their word (no attack)" in notes
    assert "The Graves broke their word (support)" in notes
    assert st["accords"][G.MI.pair("graves", "quill")] == round(before[G.MI.pair("graves", "quill")] - 0.3, 3)
    assert st["words"]["graves"] == {"kept": 0, "broken": 1}


def test_a_family_writes_unasked_about_the_season_to_come_and_never_asks_for_the_user_s_own():
    # the first real game: Harriet wrote of "your fleet at Harbor Row" after taking Harbor Row herself, and the Graves
    # asked for a hand toward a harbor of the user's -- the letters were written from the season just played
    st = G.new_state("doc", "quill", seed="78" * 16)
    fog, point, tower, row = (M.find(n) for n in ("Fogwater", "Merrow Point", "The Tower", "Harbor Row"))
    st["units"] = {fog: {"family": "quill", "kind": R.FLEET}, tower: {"family": "graves", "kind": R.FLEET}}
    st["planned"] = {"graves": {tower: R.move(tower, point)}}
    why = LT.reason(st, "graves")
    assert "your fleet at The Tower is ordered to Merrow Point" in why
    assert '"Fogwater supports The Tower to Merrow Point"' in why
    assert R.legal(st["units"], R.support(fog, tower, point))[0]           # the order asked for is one they can write
    # a harbor of the user's is never what they are asked to help take; nor a shire their own unit stands on
    st["units"] = {fog: {"family": "quill", "kind": R.FLEET}, point: {"family": "graves", "kind": R.FLEET}}
    st["planned"] = {"graves": {point: R.move(point, row)}}
    assert st["owners"][row] == "quill" and LT.reason(st, "graves") == ""
    st["planned"] = {"graves": {point: R.move(point, fog)}}
    assert LT.reason(st, "graves") == ""
    # a move of the user's on them last season is named as it was
    last = {"units_before": {fog: {"family": "quill", "kind": R.FLEET}, point: {"family": "graves", "kind": R.FLEET}},
            "orders": {fog: R.move(fog, point)}}
    assert LT.reason(st, "graves", last) == "last season The Quills' fleet at Fogwater moved on your fleet at Merrow Point"
    # and in a season the letters are asked after the next orders are planned, with the surname and no given name
    st = G.new_state("doc", "quill", seed="12" * 16)
    seen = []

    def ask(q):
        seen.append((q, dict(st["planned"])))
        return '{"say": "A word, Quill."}'
    mine, wants, problems = O.parse(["Harbor Row to Fogwater"], st["units"], "quill")
    for _ in range(4):                                                   # a few seasons: somebody writes
        at = len(seen)
        G.season(st, mine, wants, problems, ask_text=ask)
        assert all(planned == st["planned"] for _, planned in seen[at:])  # asked with the coming season's orders
        mine, wants, problems = {s: R.hold(s) for s, u in st["units"].items() if u["family"] == "quill"}, {"build": [], "disband": []}, []
    assert seen
    assert all("surname Quill" in q and "never by a name you made up" in q for q, _ in seen)
    for q, planned in seen:
        if "is ordered to" in q:
            line = q.split("WHY YOU WRITE: ")[1]
            assert any(("at %s is ordered to %s" % (M.NAMES[s], M.NAMES[o["to"]])) in line
                       for d in planned.values() for s, o in d.items() if o["kind"] == R.MOVE)


def test_a_promise_binds_the_season_its_letter_came_in():
    # the first real game: the Graves promised to keep clear of Harbor Row "for this single season" and moved on it
    # that same season, on orders written before the letter
    st = G.new_state("doc", "quill", seed="bc" * 16)
    row, fog, tower = (M.find(n) for n in ("Harbor Row", "Fogwater", "The Tower"))
    assert st["units"][tower]["family"] == "graves" and R.legal(st["units"], R.support(tower, row, fog))[0]

    def ask(q):
        assert "AS THEY STAND" in q
        return ('{"say": "Quill, you shall have it. Ottoline", "promise": {"kind": "support", "unit": "Harbor Row", '
                '"to": "Fogwater", "seasons": 1}, "keep": true}')
    answered = G.deliver(st, [("graves", "Back my fleet into Fogwater this season.")], ask)
    assert answered == ["The Graves"] and st["promises"][0]["until"] == 0 == st["promises"][0]["season_no"]
    mine_ = st["planned"]["graves"][tower]
    assert (mine_["kind"], mine_["of"], mine_["to"]) == (R.SUPPORT, row, fog)       # written again, with the promise
    mine, wants, problems = O.parse(["Harbor Row to Fogwater"], st["units"], "quill")
    note = G.season(st, mine, wants, problems, ask_text=None)
    assert "moved" in note and st["words"]["graves"] == {"kept": 1, "broken": 0}
    assert any("The Graves kept their word (support)" in ln for ln in st["log"][0]["lines"])
    # a promise of no attack covers the user's harbors and the shire it names
    st = G.new_state("doc", "quill", seed="bc" * 16)
    st["promises"] = [{"by": "graves", "to_family": "quill", "kind": "no_attack", "shire": fog, "keep": True, "until": 0, "season_no": 0}]
    G.plan(st)
    assert not any(o["kind"] == R.MOVE and (o["to"] == fog or st["owners"].get(o["to"]) == "quill")
                   for o in st["planned"]["graves"].values())


def test_a_letters_page_takes_the_letters_that_fit_whole():
    # the first real game: seven letters to a page by count, and the seventh ended mid-sentence at the page's foot
    from paperdaemon.pipeline.draw import scaled as SD
    from paperdaemon.pipeline.games import adventure as AD
    from paperdaemon.pipeline.games.concord import pages as PG
    st = G.new_state("doc", "quill", seed="9a" * 16)
    assert PG.letters_plan(st) == [(0, -1)]
    long = "Quill, the bay is small and the winter long, and a neighbor who keeps her word is worth three fleets. " * 5
    st["letters"] = [{"from": "oakes" if i % 3 else "quill", "to": "quill" if i % 3 else "oakes", "text": long if i % 3 else "A short word.",
                      "season_no": i // 3} for i in range(16)]
    plan = PG.letters_plan(st)
    assert len(plan) > 2 and plan[0][0] == 0 and plan[-1][1] == 15
    assert all(b[0] == a[1] + 1 for a, b in zip(plan, plan[1:]))                  # every letter on one page, in order
    d = SD.canvas(PG.PAGE_W, 200)[1]
    top = AD._header(d, "Letters", "Spring of year 1")
    for first, last in plan:
        y = top
        for L in st["letters"][first:last + 1]:
            y += PG._letter_height(d, st, L)
            assert y <= AD.FOOT_Y                                                 # its last line is on the page
            y += PG.LETTER_GAP
    grown = dict(st, letters=st["letters"] + [dict(st["letters"][1])])
    assert PG.letters_plan(grown)[:len(plan) - 1] == plan[:-1]                    # a full page keeps its letters


def test_the_state_is_kept_in_the_notepad_like_any_game_s():
    # the first real start failed here: the notepad's entry was written with chess's summary (KeyError: 'fen')
    import json
    st = G.new_state("doc", "quill", seed="56" * 16)
    st["page_id"] = "pid"
    mine, wants, problems = O.parse(["Harbor Row to Fogwater"], st["units"], "quill")
    G.season(st, mine, wants, problems, ask_text=None)
    entry = CH._entry(st)
    assert "the Concord of Merrow Bay con-" in entry and "the user plays The Quills" in entry
    body = entry.split("<!-- game-state concord %s" % st["id"])[1].split("-->")[0].strip()
    back = json.loads(body)
    assert back["game"] == "concord" and back["season_no"] == 1 and back["units"] == json.loads(json.dumps(st["units"]))

