from datetime import datetime, timezone

from endless_war.domain.models import WorldState
from endless_war.simulation.engine import SimulationEngine


def test_tick_advances_time_by_six_hours() -> None:
    start = datetime(2000, 1, 1, tzinfo=timezone.utc)
    world = WorldState(seed=123, current_time=start)
    SimulationEngine(world).tick()
    assert (world.current_time - start).total_seconds() == 6 * 60 * 60
