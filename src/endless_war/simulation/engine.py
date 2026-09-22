"""Simulation orchestration.

The engine owns the clock and the single seeded RNG. Systems are stateless
functions called in the fixed order documented in docs/architecture.md.
"""

from __future__ import annotations

import random
from datetime import timedelta
from typing import Any

from endless_war.config import load_config
from endless_war.domain.models import WorldState
from endless_war.simulation.systems.battle import resolve_battles
from endless_war.simulation.systems.control import apply_control_changes
from endless_war.simulation.systems.diplomacy import (
    note_captures,
    update_diplomacy,
    update_exhaustion,
)
from endless_war.simulation.systems.economy import update_economy, update_recruitment
from endless_war.simulation.systems.movement import update_movement
from endless_war.simulation.systems.supply import update_supply


class SimulationEngine:
    def __init__(self, world: WorldState, config: dict[str, Any] | None = None) -> None:
        self.world = world
        self.config = config or load_config()
        self.rng = random.Random(world.seed)
        self.tick_hours: int = self.config["simulation"]["tick_hours"]

    def tick(self, hours: int | None = None) -> None:
        """Advance the world by one strategic tick.

        Systems run in the fixed order from docs/architecture.md. Later tasks
        insert their calls between the markers below; do not reorder them.
        """
        step = self.tick_hours if hours is None else hours
        self.world.current_time += timedelta(hours=step)
        self.world.tick_count += 1
        # --- SYSTEM PIPELINE START (fixed order, do not reorder) ---
        update_economy(self.world, self.rng, self.config)
        update_recruitment(self.world, self.rng, self.config)
        update_supply(self.world, self.rng, self.config)
        # AI decisions
        update_movement(self.world, self.rng, self.config)
        battle_records = resolve_battles(self.world, self.rng, self.config)
        capture_records = apply_control_changes(
            self.world, self.rng, self.config, battle_records
        )
        update_exhaustion(self.world, self.rng, self.config)
        note_captures(self.world, capture_records)
        diplomacy_events = update_diplomacy(self.world, self.rng, self.config)
        # events
        # --- SYSTEM PIPELINE END ---

    def run(self, ticks: int) -> None:
        """Advance the world by `ticks` strategic ticks."""
        for _ in range(ticks):
            self.tick()
