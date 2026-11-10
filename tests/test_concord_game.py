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
    assert st["last"]["mine"][0][0] == "Harbor Row to Fogwater" and st["last"]["mine"][0][1] in ("moved", "failed: stood off", "failed: held back")
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

