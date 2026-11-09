"""The Concord's orders from plain words (design D4): names found whole, by prefix or by the closest spelling; the
verb from the words left; builds and disbands; what cannot be placed handed back with why."""
from paperdaemon.pipeline.games.concord import orders as O
from paperdaemon.pipeline.games.concord import rules as R

UNITS = {"kettle-isle": {"family": "quill", "kind": R.FLEET}, "harbor-row": {"family": "quill", "kind": R.FLEET},
         "the-archive": {"family": "quill", "kind": R.MILITIA}, "fogwater": {"family": "graves", "kind": R.FLEET},
         "the-lobster-grounds": {"family": "stroud", "kind": R.MILITIA}, "the-narrows": {"family": "stroud", "kind": R.FLEET}}


def test_the_four_orders_in_plain_words():
    assert O.parse_line("Kettle Isle to Gull Reach") == dict(R.move("kettle-isle", "gull-reach"), text="Kettle Isle to Gull Reach")
    assert O.parse_line("fleet at Harbor Row holds")["kind"] == R.HOLD and O.parse_line("Harbor Row")["kind"] == R.HOLD
    assert O.parse_line("Harbor Row supports Kettle Isle to Gull Reach") == dict(R.support("harbor-row", "kettle-isle", "gull-reach"),
                                                                                  text="Harbor Row supports Kettle Isle to Gull Reach")
    assert O.parse_line("the Archive backs Harbor Row")["to"] is None               # a support to hold
    assert O.parse_line("the Narrows convoys the Lobster Grounds to Pearl Shoal") == dict(
        R.convoy("the-narrows", "the-lobster-grounds", "pearl-shoal"), text="the Narrows convoys the Lobster Grounds to Pearl Shoal")
    assert O.parse_line("Kettle Isle - Gull Reach")["kind"] == R.MOVE and O.parse_line("Kettle Isle -> Gull Reach")["to"] == "gull-reach"
    assert O.parse_line("our fleet in Fogwater attacks the Tower")["to"] == "the-tower"


def test_names_by_prefix_and_by_spelling_and_small_words_left_alone():
    assert O.find_shire(["kettle"]) == "kettle-isle" and O.find_shire(["Kettel", "Isle"]) == "kettle-isle"
    assert O.find_shire(["to"]) is None and O.find_shire(["the"]) is None and O.find_shire(["the", "tower"]) == "the-tower"
    assert O.parse_line("Kettel Isle to Gul Reach")["to"] == "gull-reach"
    assert O.parse_line("Habor Row holds")["unit"] == "harbor-row"


def test_builds_disbands_and_what_cannot_be_placed():
    assert O.parse_line("build fleet at Harbor Row") == {"want": "build", "unit_kind": R.FLEET, "shire": "harbor-row", "text": "build fleet at Harbor Row"}
    assert O.parse_line("build militia in the Archive")["unit_kind"] == R.MILITIA and O.parse_line("build at City Hall")["unit_kind"] is None
    assert O.parse_line("disband Fogwater") == {"want": "disband", "shire": "fogwater", "text": "disband Fogwater"}
    assert O.parse_line("hold the line")["kind"] == "unknown" and O.parse_line("Kettle Isle Gull Reach Pearl Shoal")["why"]
    assert O.parse_line("Harbor Row supports")["why"] == "supports whom?"


def test_the_family_s_lines_become_its_orders_and_the_rest_are_problems():
    orders, wants, problems = O.parse(["Kettle Isle to the Sound", "Harbor Row supports Kettle Isle to the Sound", "",
                                       "the Archive holds", "Fogwater to the Tower", "Kettle Isle holds",
                                       "the Archive to Fogwater", "build militia at the Archive", "disband the Narrows",
                                       "something unreadable"], UNITS, "quill")
    assert set(orders) == {"kettle-isle", "harbor-row", "the-archive"} and orders["the-archive"]["kind"] == R.HOLD
    assert wants == {"build": [(R.MILITIA, "the-archive")], "disband": []}
    assert [p[1] for p in problems] == ["the unit at Fogwater is not yours", "Kettle Isle already has its order",
                                        "a militia cannot stand on Fogwater", "no unit of yours at The Narrows", "no shire named"]
