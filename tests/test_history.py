from dataclasses import FrozenInstanceError
from datetime import timedelta

import pytest

from endless_war.config import load_config
from endless_war.simulation.engine import SimulationEngine
from endless_war.simulation.systems.history import record_history
from endless_war.simulation.worldgen import generate_world


def _engine(seed: int = 42) -> SimulationEngine:
    cfg = load_config()
    return SimulationEngine(generate_world(seed=seed, config=cfg), cfg)


def test_a_fresh_world_has_no_readings() -> None:
    assert _engine().world.casualty_history == []


def test_one_reading_per_simulated_date() -> None:
    engine = _engine()
    dates = []
    for _ in range(40):
        engine.tick()
        dates.append(engine.world.current_time.date())
    recorded = [r.simulated_at.date() for r in engine.world.casualty_history]
    assert recorded == sorted(set(dates))


def test_day_sized_ticks_still_record_every_date() -> None:
    # Offline catch-up may tick a day at a time; "every 4 ticks" would be wrong.
    engine = _engine()
    for _ in range(5):
        engine.tick(hours=24)
    readings = engine.world.casualty_history
    assert len(readings) == 5
    assert all(
        b.simulated_at - a.simulated_at == timedelta(days=1)
        for a, b in zip(readings, readings[1:])
    )


def test_a_reading_holds_every_factions_total_at_that_moment() -> None:
    world = _engine().world
    world.factions[0].casualties = 1234
    world.factions[3].casualties = 99
    record_history(world)
    reading = world.casualty_history[-1]
    assert reading.simulated_at == world.current_time
    assert reading.casualties == tuple(
        (fid, world.factions[fid].casualties) for fid in sorted(world.factions)
    )


def test_a_second_call_on_the_same_date_adds_nothing() -> None:
    world = _engine().world
    record_history(world)
    record_history(world)
    assert len(world.casualty_history) == 1


def test_readings_are_frozen() -> None:
    world = _engine().world
    record_history(world)
    with pytest.raises(FrozenInstanceError):
        world.casualty_history[0].casualties = ()  # type: ignore[misc]


def test_the_same_seed_records_the_same_series() -> None:
    a, b = _engine(7), _engine(7)
    a.run(4 * 60)
    b.run(4 * 60)
    assert a.world.casualty_history == b.world.casualty_history


def test_a_year_of_war_records_real_losses() -> None:
    # Premise guard: a series of zeros would pass every test above.
    engine = _engine()
    engine.run(4 * 365)
    last = dict(engine.world.casualty_history[-1].casualties)
    assert sum(last.values()) > 0
