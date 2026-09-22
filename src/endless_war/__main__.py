from datetime import datetime, timezone

from endless_war.domain.models import WorldState
from endless_war.simulation.engine import SimulationEngine


def main() -> None:
    world = WorldState(seed=1, current_time=datetime.now(timezone.utc))
    sim = SimulationEngine(world)
    sim.tick()
    print(f"Endless War Simulator prototype: {world.current_time.isoformat()}")


if __name__ == "__main__":
    main()
