from datetime import datetime, timezone

from endless_war.config import load_config
from endless_war.domain.models import WorldState
from endless_war.simulation.engine import SimulationEngine
from endless_war.simulation.worldgen import generate_world


def test_tick_advances_time_by_six_hours() -> None:
    start = datetime(2000, 1, 1, tzinfo=timezone.utc)
    world = WorldState(seed=123, current_time=start)
    SimulationEngine(world).tick()
    assert (world.current_time - start).total_seconds() == 6 * 60 * 60


def test_armies_in_contact_produce_combat() -> None:
    """Regression: two hostile armies in contact must actually fight.

    Before the 2026-09-23 contact ruling, `update_movement` refused to advance
    into a hostile-occupied province while `resolve_battles` only fired on
    hostile armies already co-located -- so in a ten-year run the pipeline
    produced 0 battles and 0 casualties across 14,600 ticks. This asserts the
    property the CONTINUE_OFFLINE.md checkpoint needs: contact yields combat,
    not merely that an army moved.

    Fixture, straight from worldgen at seed 42 (nothing is forced but the war):
    faction 3 holds province 62 with army 10 (51,207 men) and faction 4 holds
    the adjacent province 61 with army 14 (24,713 men); (3, 4) is a real
    bordering pair. No War record is created, so the diplomacy system cannot
    end the war underneath the assertion.
    """
    cfg = load_config()
    world = generate_world(seed=42, config=cfg)
    assert world.armies[10].faction_id == 3 and world.armies[10].province_id == 62
    assert world.armies[14].faction_id == 4 and world.armies[14].province_id == 61
    assert 61 in world.provinces[62].neighbors
    world.factions[3].at_war_with = {4}
    world.factions[4].at_war_with = {3}

    engine = SimulationEngine(world, cfg)
    for _ in range(20):
        engine.tick()

    casualties = sum(f.casualties for f in world.factions.values())
    assert casualties > 0, "armies in contact fought no battle in 20 ticks"


def test_broken_army_in_safe_territory_recovers() -> None:
    """Regression: a broken army in its own rear must dig in and recover.

    The AI used to issue a withdrawal order to every broken army on every tick,
    and movement only recovered organization when no order was held -- so an
    army could not recover because it was retreating, and retreated because it
    had not recovered. Measured over a ten-year run before the fix: 76.0% of
    army-ticks carried a destination, 75.9% were broken, and 12 of 15 armies
    sat at identical organization values in all ten years.

    Fixture: at seed 42 army 0 (faction 0) stands in province 13, every one of
    whose neighbours is also controlled by faction 0 -- a genuine interior
    province, verified below rather than assumed.
    """
    cfg = load_config()
    world = generate_world(seed=42, config=cfg)
    army = world.armies[0]
    assert army.faction_id == 0 and army.province_id == 13
    assert all(
        world.provinces[n].controller_faction_id == 0
        for n in world.provinces[13].neighbors
    ), "fixture: province 13 must be interior to faction 0"

    army.organization = 0.20          # broken: below BROKEN_ORGANIZATION (0.30)
    army.supply = 1.0

    engine = SimulationEngine(world, cfg)
    for _ in range(10):
        engine.tick()

    assert all(
        world.provinces[n].controller_faction_id == 0
        for n in world.provinces[13].neighbors
    ), "fixture: the front was supposed to stay far away during the test"
    assert world.provinces[13].supply_value >= 0.35, (
        "fixture: province 13 must stay above the low-supply threshold, or the army "
        "would be taking the attrition branch instead of the recovery branch"
    )
    assert army.province_id == 13, "a safe broken army should hold, not wander"
    assert army.organization > 0.20, "a safe broken army must recover organization"
