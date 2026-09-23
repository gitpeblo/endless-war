import random

from endless_war.ai.strategic import choose_strategic_actions
from endless_war.config import load_config
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
