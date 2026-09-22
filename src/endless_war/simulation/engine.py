"""Simulation orchestration.

The engine intentionally starts small. Add systems in a fixed, documented order.
"""

from datetime import timedelta
import random

from endless_war.domain.models import WorldState


class SimulationEngine:
    def __init__(self, world: WorldState) -> None:
        self.world = world
        self.rng = random.Random(world.seed)

    def tick(self, hours: int = 6) -> None:
        """Advance the world by one strategic tick."""
        self.world.current_time += timedelta(hours=hours)
        # TODO: economy
        # TODO: recruitment
        # TODO: supply
        # TODO: AI decisions
        # TODO: movement
        # TODO: battles
        # TODO: control changes
        # TODO: exhaustion/stability
        # TODO: diplomacy
        # TODO: events
