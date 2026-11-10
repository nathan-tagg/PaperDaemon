"""The Concord of Merrow Bay's map and rules (openspec/changes/add-concord-of-merrow-bay, D1 and D3): the shires tile
the bay and touch as drawn; orders resolve all at once -- a supported attack, a stand-off, a cut support, a head-to-head,
a convoy carried and one broken, no family dislodging its own, retreats, the autumn's harbors, builds and disbands, the
win."""
from paperdaemon.pipeline.games.concord import map as M
from paperdaemon.pipeline.games.concord import rules as R

F, Mi = R.FLEET, R.MILITIA


def U(**kw):
    """units from shire=(family, kind) pairs; shire ids with dashes written with underscores"""
    return {k.replace("_", "-"): {"family": f, "kind": kind} for k, (f, kind) in kw.items()}


# ------------------------------------------------------------------------------ the map
def test_the_shires_tile_the_bay_and_touch_as_drawn():
    assert len(M.SHIRES) == 28 and len(M.HARBORS) == 20 and M.MAJORITY == 11
    assert all(len(M.HOMES[f]) == 2 and all(M.SHIRES[s]["harbor"] for s in M.HOMES[f]) for f in M.FAMILIES)
    assert abs(sum(M.polygon_area(sh["poly"]) for sh in M.SHIRES.values()) - M.MAP_W * M.MAP_H) < 1.0
    for sid, sh in M.SHIRES.items():
        assert sid not in sh["neighbors"] and all(sid in M.SHIRES[n]["neighbors"] for n in sh["neighbors"])
        if sh["kind"] == M.COAST:
            assert any(M.is_sea(n) for n in sh["neighbors"])
        if sh["kind"] == M.INLAND:
            assert not any(M.is_sea(n) for n in sh["neighbors"])
    islands = {"kettle-isle", "gull-reach", "lantern-spit", "pearl-shoal"}
    assert all(n in islands or M.is_sea(n) for i in islands for n in M.SHIRES[i]["neighbors"])   # islands: by sea only
    assert M.distance("the-tower", {"the-strip"}, F) is not None                                   # fleets round the bay
    assert M.distance("the-archive", {"salt-pans"}, Mi) is not None                                # militias round the shore
    assert M.find("kettle") == "kettle-isle" and M.find("The Sound") == "the-sound" and M.find("sound") == "the-sound"
    assert M.find("Hale's Landing") == "hales-landing" and M.find("the") is None


# ------------------------------------------------------------------------------ orders, all at once
def test_a_supported_attack_dislodges_and_the_loser_retreats():
    units = U(the_sound=("oakes", F), fogwater=("quill", F), kettle_isle=("holloway", Mi))
    r = R.resolve(units, {"the-sound": R.move("the-sound", "kettle-isle"),
                          "fogwater": R.support("fogwater", "the-sound", "kettle-isle")})
    assert r["moved"] == {"the-sound": "kettle-isle"} and r["fates"]["fogwater"] == ("gave", "")
    assert r["dislodged"] == {"kettle-isle": {"from": "the-sound", "by": "oakes"}}
    assert r["retreats"]["kettle-isle"] in ("gull-reach", "pearl-shoal")       # an island militia has only islands to go to
    assert r["after"]["kettle-isle"] == {"family": "oakes", "kind": F} and "fogwater" in r["after"]


def test_equal_attacks_stand_off_and_nobody_moves():
    units = U(the_tower=("graves", F), harbor_row=("quill", F))
    r = R.resolve(units, {"the-tower": R.move("the-tower", "fogwater"), "harbor-row": R.move("harbor-row", "fogwater")})
    assert r["moved"] == {} and "fogwater" in r["contested"]
    assert r["fates"]["the-tower"] == ("failed", "stood off") and set(r["after"]) == {"the-tower", "harbor-row"}


def test_a_support_cut_from_a_third_shire_does_not_count():
    units = U(the_sound=("oakes", F), fogwater=("quill", F), kettle_isle=("holloway", Mi), the_narrows=("stroud", F))
    r = R.resolve(units, {"the-sound": R.move("the-sound", "kettle-isle"),
                          "fogwater": R.support("fogwater", "the-sound", "kettle-isle"),
                          "the-narrows": R.move("the-narrows", "fogwater")})
    assert r["cut"] == {"fogwater": "the-narrows"} and r["fates"]["fogwater"][0] == "cut"
    assert r["moved"] == {} and r["dislodged"] == {}                          # 1 against 1: the militia holds
    assert r["fates"]["the-narrows"] == ("failed", "turned back")              # and the cutter bounced off the fleet


def test_a_dislodged_unit_s_support_is_cut_even_by_the_shire_it_supported_into():
    # the first real game's autumn: the Oakes left Harbor Row for The Ferry Landing with a support and dislodged the
    # Holloways' fleet there, whose support for the Graves INTO Harbor Row still counted -- a stand-off where the
    # user's supported move should have gone in
    units = U(harbor_row=("oakes", F), city_hall=("oakes", Mi), the_ferry_landing=("holloway", F),
              merrow_point=("graves", F), fogwater=("quill", F), the_archive=("quill", Mi))
    r = R.resolve(units, {"harbor-row": R.move("harbor-row", "the-ferry-landing"),
                          "city-hall": R.support("city-hall", "harbor-row", "the-ferry-landing"),
                          "the-ferry-landing": R.support("the-ferry-landing", "merrow-point", "harbor-row"),
                          "merrow-point": R.move("merrow-point", "harbor-row"),
                          "fogwater": R.move("fogwater", "harbor-row"),
                          "the-archive": R.support("the-archive", "fogwater", "harbor-row")})
    assert "the-ferry-landing" in r["dislodged"] and r["cut"]["the-ferry-landing"] == "harbor-row"
    assert r["fates"]["the-ferry-landing"] == ("cut", "attacked from Harbor Row; dislodged from The Ferry Landing")
    assert r["moved"] == {"harbor-row": "the-ferry-landing", "fogwater": "harbor-row"}
    assert r["fates"]["merrow-point"] == ("failed", "turned back") and "harbor-row" not in r["contested"]
    # an attack from that shire that does NOT dislodge leaves the support standing
    r = R.resolve(units, {"harbor-row": R.move("harbor-row", "the-ferry-landing"),
                          "the-ferry-landing": R.support("the-ferry-landing", "merrow-point", "harbor-row"),
                          "merrow-point": R.move("merrow-point", "harbor-row")})
    assert r["cut"] == {} and r["fates"]["the-ferry-landing"] == ("gave", "")


def test_head_to_head_the_stronger_wins_and_equals_both_stay():
    units = U(the_sound=("oakes", F), fogwater=("quill", F))
    r = R.resolve(units, {"the-sound": R.move("the-sound", "fogwater"), "fogwater": R.move("fogwater", "the-sound")})
    assert r["moved"] == {} and r["dislodged"] == {}
    units = U(the_sound=("oakes", F), fogwater=("quill", F), kettle_isle=("oakes", F))
    r = R.resolve(units, {"the-sound": R.move("the-sound", "fogwater"), "fogwater": R.move("fogwater", "the-sound"),
                          "kettle-isle": R.support("kettle-isle", "the-sound", "fogwater")})
    assert r["moved"] == {"the-sound": "fogwater"} and "fogwater" in r["dislodged"]
    assert r["retreats"]["fogwater"] not in (None, "the-sound")             # never back where the attacker came from


def test_a_convoy_carries_a_militia_and_a_broken_one_does_not():
    units = U(the_lobster_grounds=("stroud", Mi), the_narrows=("stroud", F))
    orders = {"the-lobster-grounds": R.move("the-lobster-grounds", "pearl-shoal"),
              "the-narrows": R.convoy("the-narrows", "the-lobster-grounds", "pearl-shoal")}
    r = R.resolve(units, orders)
    assert r["moved"] == {"the-lobster-grounds": "pearl-shoal"} and r["fates"]["the-narrows"] == ("carried", "")
    units.update(U(fogwater=("graves", F), graves_hill=("graves", F)))
    orders.update({"fogwater": R.move("fogwater", "the-narrows"), "graves-hill": R.support("graves-hill", "fogwater", "the-narrows")})
    r = R.resolve(units, orders)
    assert "the-narrows" in r["dislodged"] and r["moved"] == {"fogwater": "the-narrows"}
    assert r["fates"]["the-lobster-grounds"] == ("failed", "no fleets carried it") and "the-lobster-grounds" in r["after"]


def test_no_family_dislodges_its_own_unit():
    units = U(harbor_row=("quill", F), fogwater=("quill", F), the_tower=("quill", F))
    r = R.resolve(units, {"harbor-row": R.move("harbor-row", "fogwater"), "the-tower": R.support("the-tower", "harbor-row", "fogwater")})
    assert r["moved"] == {} and r["dislodged"] == {}
    # and a family's support never helps dislodge its own unit
    units = U(harbor_row=("oakes", F), fogwater=("quill", F), the_tower=("quill", F))
    r = R.resolve(units, {"harbor-row": R.move("harbor-row", "fogwater"), "the-tower": R.support("the-tower", "harbor-row", "fogwater")})
    assert r["moved"] == {}


def test_a_ring_of_moves_all_go_and_a_unit_leaving_lets_another_in():
    units = U(the_sound=("oakes", F), fogwater=("quill", F), kettle_isle=("stroud", F))
    r = R.resolve(units, {"the-sound": R.move("the-sound", "fogwater"), "fogwater": R.move("fogwater", "kettle-isle"),
                          "kettle-isle": R.move("kettle-isle", "the-sound")})
    assert r["moved"] == {"the-sound": "fogwater", "fogwater": "kettle-isle", "kettle-isle": "the-sound"}
    units = U(the_sound=("oakes", F), fogwater=("quill", F))
    r = R.resolve(units, {"the-sound": R.move("the-sound", "fogwater"), "fogwater": R.move("fogwater", "the-tower")})
    assert r["moved"] == {"the-sound": "fogwater", "fogwater": "the-tower"} and r["dislodged"] == {}


def test_an_order_a_unit_cannot_carry_out_is_a_hold_with_its_reason():
    units = U(the_archive=("quill", Mi), harbor_row=("quill", F))
    r = R.resolve(units, {"the-archive": R.move("the-archive", "fogwater"), "harbor-row": R.move("harbor-row", "the-strip")})
    assert r["illegal"]["the-archive"].startswith("a militia cannot stand on") and "does not touch" in r["illegal"]["harbor-row"]
    assert r["fates"] == {"the-archive": ("held", ""), "harbor-row": ("held", "")}


# ------------------------------------------------------------------------------ the autumn
def test_autumn_counts_harbors_builds_and_disbands_and_names_the_winner():
    units, owners = R.opening(M.FAMILIES)
    assert len(units) == 14 and R.standing(owners) == {f: 2 for f in M.FAMILIES}
    assert units["harbor-row"]["kind"] == F and units["the-archive"]["kind"] == Mi     # a coast and an inland home
    units["kettle-isle"] = {"family": "oakes", "kind": F}
    del units["the-ferry-landing"]                                                  # the fleet that went there
    owners = R.harbors_after(units, owners)
    assert owners["kettle-isle"] == "oakes" and R.standing(owners)["oakes"] == 3
    after, notes = R.adjust(units, owners, "oakes")
    assert after["the-ferry-landing"] == {"family": "oakes", "kind": F} and notes == ["built a fleet at The Ferry Landing"]
    after, notes = R.adjust(units, owners, "oakes", wants={"build": [(Mi, "the-ferry-landing")]})
    assert after["the-ferry-landing"]["kind"] == Mi
    # holloway loses a harbor to the Hales: one unit too many, the farthest goes
    owners2 = dict(owners, **{"clerks-row": "hale"})
    units2 = dict(units)
    units2["kettle-isle"] = {"family": "holloway", "kind": F}
    after, notes = R.adjust(units2, owners2, "holloway")
    assert [s for s, u in after.items() if u["family"] == "holloway"] == ["the-records-yard"] and notes[0].startswith("disbanded")
    assert R.winner(owners, 3) == []
    assert R.winner({s: "oakes" for s in M.HARBORS}, 1) == ["oakes"]
    assert R.winner(owners, 10) == ["oakes"]                                        # most harbors after the tenth autumn
    tie = dict(owners, **{"kettle-isle": None})
    assert R.winner(tie, 10) == sorted(M.FAMILIES)
