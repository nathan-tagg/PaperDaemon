"""The cast families' orders and the accords (design D7): every order the order-writer gives is legal, a kept promise
binds it, the ruthless attack what the gentle leave alone, the accords start from the profiles and move with deeds."""
from paperdaemon.pipeline.games import chess as CH
from paperdaemon.pipeline.games.concord import map as M
from paperdaemon.pipeline.games.concord import minds as MI
from paperdaemon.pipeline.games.concord import rules as R

CAST = {"quill": "lenora-quill", "oakes": "harriet-oakes", "holloway": "bea-holloway", "hale": "augustus-hale",
        "shellby": "cornelius-shellby", "graves": "ottoline-graves", "stroud": "eben-stroud"}


def test_every_order_the_writer_gives_is_legal_and_the_game_moves():
    units, owners = R.opening(M.FAMILIES)
    acc = MI.opening_accords(CAST)
    rng = CH.Rng("cd" * 16)
    moved = 0
    for season_no in range(6):
        orders = {}
        for f in M.FAMILIES:
            o = MI.write_orders(f, units, owners, acc, CAST, rng, (), season_no, others=orders)
            assert set(o) == {s for s, u in units.items() if u["family"] == f}
            for s, od in o.items():
                assert R.legal(units, od) == (True, ""), (f, od)
            orders.update(o)
        res = R.resolve(units, orders)
        moved += len(res["moved"])
        units = res["after"]
        if season_no % 2:
            owners = R.harbors_after(units, owners)
            for f in M.FAMILIES:
                units, _ = R.adjust(units, owners, f)
    assert moved > 10 and sum(R.standing(owners).values()) > 14          # harbors were taken


def test_the_same_seed_gives_the_same_season():
    units, owners = R.opening(M.FAMILIES)
    acc = MI.opening_accords(CAST)
    a = MI.write_orders("oakes", units, owners, acc, CAST, CH.Rng("ef" * 16), (), 0)
    b = MI.write_orders("oakes", units, owners, acc, CAST, CH.Rng("ef" * 16), (), 0)
    assert a == b


def test_a_kept_promise_binds_the_orders_and_a_broken_one_does_not():
    units, owners = R.opening(M.FAMILIES)
    units["kettle-isle"] = {"family": "quill", "kind": R.FLEET}        # the user's fleet, next to the Oakes' landing
    units["the-sound"] = {"family": "oakes", "kind": R.FLEET}
    acc = MI.opening_accords(CAST)
    kept = [{"by": "oakes", "to_family": "quill", "kind": "support", "unit": "kettle-isle", "to": "fogwater", "keep": True, "until": 9}]
    o = MI.write_orders("oakes", units, owners, acc, CAST, CH.Rng("01" * 16), kept, 1)
    assert o["the-sound"] == R.support("the-sound", "kettle-isle", "fogwater")
    broken = [dict(kept[0], keep=False)]
    o2 = MI.write_orders("oakes", units, owners, acc, CAST, CH.Rng("01" * 16), broken, 1)
    assert o2["the-sound"] != R.support("the-sound", "kettle-isle", "fogwater")
    # no_attack: the Oakes leave the Quills alone where otherwise they might not
    units2 = dict(units)
    units2["fogwater"] = {"family": "quill", "kind": R.FLEET}
    peace = [{"by": "oakes", "to_family": "quill", "kind": "no_attack", "keep": True, "until": 9}]
    acc2 = dict(acc, **{MI.pair("oakes", "quill"): -0.9})
    for seed in ("02", "03", "04"):
        o3 = MI.write_orders("oakes", units2, owners, acc2, CAST, CH.Rng(seed * 16), peace, 1)
        assert not any(od["kind"] == R.MOVE and od["to"] in units2 and units2[od["to"]]["family"] == "quill" for od in o3.values())


def test_the_ruthless_attack_whom_the_gentle_spare():
    t_cold = {"ruthless": 1.0}
    t_kind = {"ruthless": 0.0}
    assert MI.may_attack(t_cold, 0.3) and not MI.may_attack(t_cold, 0.55)
    assert MI.may_attack(t_kind, -0.5) and not MI.may_attack(t_kind, 0.0)
    assert MI.temperament("ottoline-graves")["ruthless"] > 0.8 > MI.temperament("eben-stroud")["ruthless"]
    assert MI.temperament(None) == MI.DEFAULT


def test_accords_start_from_the_profiles_and_move_with_deeds():
    acc = MI.opening_accords(CAST)
    assert set(acc) == {MI.pair(a, b) for a in CAST for b in CAST if a < b}
    assert acc[MI.pair("hale", "shellby")] != 0.0                          # the judge and the senator have history
    assert acc[MI.pair("stroud", "graves")] == 0.0                         # strangers
    units = {"the-sound": {"family": "oakes", "kind": R.FLEET}, "kettle-isle": {"family": "quill", "kind": R.MILITIA},
             "fogwater": {"family": "quill", "kind": R.FLEET}, "harbor-row": {"family": "holloway", "kind": R.FLEET}}
    res = R.resolve(units, {"the-sound": R.move("the-sound", "kettle-isle"), "harbor-row": R.support("harbor-row", "fogwater")})
    before = dict(acc)
    MI.after_season(acc, units, res)
    assert acc[MI.pair("oakes", "quill")] == round(before[MI.pair("oakes", "quill")] - 0.15, 3)   # an attack, not a dislodgement
    assert acc[MI.pair("holloway", "quill")] == round(before[MI.pair("holloway", "quill")] + 0.1, 3)
