import random

from endless_war.ai.strategic import choose_strategic_actions
from endless_war.config import load_config
from endless_war.simulation.systems.movement import update_movement
from endless_war.simulation.worldgen import generate_world


def test_at_peace_armies_are_given_no_offensive_orders() -> None:
    cfg = load_config()
    w = generate_world(seed=42, config=cfg)
    choose_strategic_actions(w, random.Random(1), cfg)
    for army in w.armies.values():
        if army.destination_id is not None:
            assert w.provinces[army.destination_id].controller_faction_id == army.faction_id


def test_at_war_some_army_is_ordered_toward_the_enemy() -> None:
    cfg = load_config()
    w = generate_world(seed=42, config=cfg)
    # Faction 0 and faction 1 share no border at seed 42; use faction 3,
    # which borders faction 0 at provinces [17, 28, 39, 50].
    w.factions[0].at_war_with = {3}
    w.factions[3].at_war_with = {0}
    # Place one of faction 0's armies on the shared border explicitly; the
    # starting layout does not guarantee an army starts adjacent to faction 3.
    border = next(
        pid for pid in sorted(w.provinces)
        if w.provinces[pid].controller_faction_id == 0
        and any(w.provinces[n].controller_faction_id == 3 for n in w.provinces[pid].neighbors)
    )
    next(a for a in w.armies.values() if a.faction_id == 0).province_id = border
    choose_strategic_actions(w, random.Random(1), cfg)
    ordered = [
        a for a in w.armies.values()
        if a.faction_id == 0
        and a.destination_id is not None
        and w.provinces[a.destination_id].controller_faction_id == 3
    ]
    assert ordered, "faction 0 should push into faction 3 territory"


def test_destinations_are_always_adjacent() -> None:
    cfg = load_config()
    w = generate_world(seed=42, config=cfg)
    w.factions[0].at_war_with = {3}
    w.factions[3].at_war_with = {0}
    choose_strategic_actions(w, random.Random(1), cfg)
    for army in w.armies.values():
        if army.destination_id is not None:
            assert army.destination_id in w.provinces[army.province_id].neighbors


def test_broken_army_is_ordered_to_withdraw_to_friendly_ground() -> None:
    cfg = load_config()
    w = generate_world(seed=42, config=cfg)
    w.factions[0].at_war_with = {3}
    w.factions[3].at_war_with = {0}
    army = next(a for a in w.armies.values() if a.faction_id == 0)
    army.organization = 0.1
    army.morale = 0.1
    choose_strategic_actions(w, random.Random(1), cfg)
    if army.destination_id is not None:
        assert w.provinces[army.destination_id].controller_faction_id == 0
    assert army.stance == "withdrawal"


def test_ai_is_deterministic_for_a_given_seed() -> None:
    cfg = load_config()
    a = generate_world(seed=42, config=cfg)
    b = generate_world(seed=42, config=cfg)
    for w in (a, b):
        w.factions[0].at_war_with = {3}
        w.factions[3].at_war_with = {0}
    choose_strategic_actions(a, random.Random(7), cfg)
    choose_strategic_actions(b, random.Random(7), cfg)
    assert [x.destination_id for x in a.armies.values()] == [
        x.destination_id for x in b.armies.values()
    ]


def test_broken_army_at_war_in_the_rear_is_not_ordered_to_withdraw() -> None:
    """The AI half of the recovery ruling, exercised through the real path.

    `test_broken_army_in_safe_territory_recovers` reaches
    `_standing_somewhere_safe` through its `if not at_war: return True`
    short-circuit, so re-introducing the unconditional withdrawal order would
    not fail it. This one is at war, so the predicate has to do its real work:
    nothing hostile adjacent, nothing hostile standing here, therefore hold.

    Fixture from worldgen at seed 42: army 0 (faction 0) is in province 13,
    every neighbour of which faction 0 also controls -- asserted, not assumed --
    and factions 0 and 3 genuinely border, so the war is not a fiction.
    """
    cfg = load_config()
    w = generate_world(seed=42, config=cfg)
    army = w.armies[0]
    assert army.faction_id == 0 and army.province_id == 13
    assert all(w.provinces[n].controller_faction_id == 0 for n in w.provinces[13].neighbors), (
        "fixture: province 13 must be interior to faction 0"
    )
    w.factions[0].at_war_with = {3}
    w.factions[3].at_war_with = {0}
    assert w.factions[0].at_war_with, "fixture: the safety predicate must not short-circuit"
    assert not [
        a for a in w.armies.values() if a.province_id == 13 and a.faction_id in {3}
    ], "fixture: no hostile army may be standing in province 13"

    army.organization = 0.20          # broken
    army.supply = 1.0

    choose_strategic_actions(w, random.Random(1), cfg)

    assert army.stance == "withdrawal"
    assert army.destination_id is None, (
        "a broken army in its own rear must hold, not be marched around; "
        "marching is what keeps it from ever recovering"
    )

    update_movement(w, random.Random(1), cfg)
    assert army.organization > 0.20, "and holding must let it recover"
