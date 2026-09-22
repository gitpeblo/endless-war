from datetime import datetime, timezone

from endless_war.domain.models import WorldState
from endless_war.simulation.engine import SimulationEngine


def _engine(seed: int) -> SimulationEngine:
    world = WorldState(seed=seed, current_time=datetime(2030, 1, 1, tzinfo=timezone.utc))
    return SimulationEngine(world)


def test_same_seed_produces_same_random_stream() -> None:
    a = [_engine(7).rng.random() for _ in range(1)][0]
    b = [_engine(7).rng.random() for _ in range(1)][0]
    assert a == b


def test_different_seed_produces_different_stream() -> None:
    assert _engine(7).rng.random() != _engine(8).rng.random()


def test_tick_increments_tick_count() -> None:
    eng = _engine(1)
    assert eng.world.tick_count == 0
    eng.tick()
    eng.tick()
    assert eng.world.tick_count == 2


def test_tick_hours_comes_from_config() -> None:
    assert _engine(1).tick_hours == 6
