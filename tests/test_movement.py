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


def test_move_into_hostile_province_is_the_attack() -> None:
    """Advancing into a defended hostile province is how an attack begins.

    docs/decisions.md (2026-09-23, contact rule): battle.py takes the province
    controller's armies as defenders and the hostile armies standing in that
    province as attackers, and control.py retreats broken *attackers* back out.
    Neither is reachable unless movement lets the attacker in, so it must.

    Fixture: at seed 42, faction 4 holds province 61 with army 14 and faction 3
    holds the adjacent province 62 with army 10, both straight from worldgen --
    no controller is forced, and (3, 4) is a real bordering pair.
    """
    cfg = load_config()
    w = generate_world(seed=42, config=cfg)
    attacker, defender = w.armies[14], w.armies[10]
    origin, target = 61, 62
    assert attacker.province_id == origin and attacker.faction_id == 4
    assert defender.province_id == target and defender.faction_id == 3
    assert w.provinces[origin].controller_faction_id == 4
    assert w.provinces[target].controller_faction_id == 3
    assert target in w.provinces[origin].neighbors

    w.factions[4].at_war_with = {3}
    w.factions[3].at_war_with = {4}
    attacker.destination_id = target

    update_movement(w, random.Random(1), cfg)

    assert attacker.province_id == target, (
        "an army ordered into a defended hostile province must enter it; "
        "the battle system resolves the engagement later in the same tick"
    )


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


def test_army_that_advances_does_not_recover_that_tick() -> None:
    """Recovery is for armies that held position, not for ones that marched.

    docs/decisions.md (2026-09-23, recovery rule): the gate is whether the army
    actually moved, not whether it holds an order. An advancing army already
    pays the -0.03 march cost, so it must not also be handed recovery.
    """
    cfg = load_config()
    w = generate_world(seed=42, config=cfg)
    army = w.armies[0]
    origin = army.province_id
    target = w.provinces[origin].neighbors[0]
    assert w.provinces[target].controller_faction_id == army.faction_id
    army.organization = 0.5
    army.supply = 1.0
    army.destination_id = target

    update_movement(w, random.Random(1), cfg)

    assert army.province_id == target, "fixture: the army was supposed to advance"
    assert army.organization < 0.5, "an advancing army must not recover organization"


def test_army_too_disorganized_to_move_recovers() -> None:
    """The recovery deadlock, as a regression.

    An army that holds an order it cannot execute used to be locked out of
    recovery forever, because the recovery branch was gated on having no
    destination at all. Organization has exactly one source of increase in the
    whole simulation; an army that never moves must be able to reach it.
    """
    cfg = load_config()
    w = generate_world(seed=42, config=cfg)
    army = w.armies[0]
    origin = army.province_id
    army.organization = 0.10          # below the 0.15 floor needed to advance
    army.supply = 1.0
    army.destination_id = w.provinces[origin].neighbors[0]

    update_movement(w, random.Random(1), cfg)

    assert army.province_id == origin, "fixture: too disorganized to advance"
    assert army.organization > 0.10, (
        "an army that holds position must recover even while under orders"
    )
