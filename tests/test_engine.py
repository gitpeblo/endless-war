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
