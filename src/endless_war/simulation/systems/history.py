"""Casualty history: one reading per simulated date.

Runs at the end of step 11 (event generation). The cadence is by date rather
than by tick count, because `SimulationEngine.tick(hours=...)` can run ticks
longer than six hours.
"""

from __future__ import annotations

from endless_war.domain.models import CasualtyReading, WorldState


def record_history(world: WorldState) -> None:
    """Append one casualty reading when the simulated date has moved on."""
    history = world.casualty_history
    if history and history[-1].simulated_at.date() >= world.current_time.date():
        return
    history.append(
        CasualtyReading(
            simulated_at=world.current_time,
            casualties=tuple(
                (fid, world.factions[fid].casualties) for fid in sorted(world.factions)
            ),
        )
    )
