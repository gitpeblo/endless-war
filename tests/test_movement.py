import random

from endless_war.config import load_config
from endless_war.simulation.systems.movement import armies_in, update_movement
from endless_war.simulation.worldgen import generate_world


def test_every_faction_starts_with_armies() -> None:
    w = generate_world(seed=42, config=load_config())
    for fid in w.factions:
        assert [a for a in w.armies.values() if a.faction_id == fid]


def test_army_moves_only_to_an_adjacent_province() -> None:
    cfg = load_config()
    w = generate_world(seed=42, config=cfg)
    army = w.armies[0]
    origin = army.province_id
    army.destination_id = w.provinces[origin].neighbors[0]
    update_movement(w, random.Random(1), cfg)
    assert army.province_id in (origin, w.provinces[origin].neighbors[0])


def test_army_without_destination_stays_put() -> None:
    cfg = load_config()
    w = generate_world(seed=42, config=cfg)
    army = w.armies[0]
    army.destination_id = None
    origin = army.province_id
    update_movement(w, random.Random(1), cfg)
    assert army.province_id == origin


def test_move_into_hostile_province_is_blocked_until_battle_resolves() -> None:
    cfg = load_config()
    w = generate_world(seed=42, config=cfg)
    army = w.armies[0]
    target = w.provinces[army.province_id].neighbors[0]
    enemy = (army.faction_id + 1) % len(w.factions)
    w.factions[army.faction_id].at_war_with = {enemy}
    w.factions[enemy].at_war_with = {army.faction_id}
    w.provinces[target].controller_faction_id = enemy
    defender = next(
        a for a in w.armies.values() if a.faction_id == enemy
    )
    defender.province_id = target
    army.destination_id = target
    update_movement(w, random.Random(1), cfg)
    assert army.province_id != target, "cannot walk into a defended hostile province"


def test_armies_in_returns_only_that_province() -> None:
    w = generate_world(seed=42, config=load_config())
    army = w.armies[0]
    found = armies_in(w, army.province_id)
    assert army in found
    assert all(a.province_id == army.province_id for a in found)


def test_organization_recovers_when_well_supplied_and_idle() -> None:
    cfg = load_config()
    w = generate_world(seed=42, config=cfg)
    army = w.armies[0]
    army.organization = 0.4
    army.supply = 1.0
    army.destination_id = None
    update_movement(w, random.Random(1), cfg)
    assert army.organization > 0.4


def test_bounded_attributes_stay_in_range_over_many_ticks() -> None:
    cfg = load_config()
    w = generate_world(seed=42, config=cfg)
    rng = random.Random(1)
    for _ in range(500):
        update_movement(w, rng, cfg)
    for army in w.armies.values():
        for attr in ("morale", "organization", "supply", "training", "equipment"):
            assert 0.0 <= getattr(army, attr) <= 1.0
