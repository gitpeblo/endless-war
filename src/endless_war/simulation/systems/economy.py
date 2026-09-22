"""Economy and manpower.

Recruitment fills the gap between the current pool and a population-derived
ceiling, so it converges rather than growing without bound (docs/simulation-notes.md,
"avoid exponential snowballing").
"""

from __future__ import annotations

import random
from typing import Any

from endless_war.domain.models import WorldState


def _controlled_provinces(world: WorldState, faction_id: int) -> list[Any]:
    return [
        world.provinces[pid]
        for pid in sorted(world.provinces)
        if world.provinces[pid].controller_faction_id == faction_id
    ]


def update_economy(world: WorldState, rng: random.Random, config: dict[str, Any]) -> None:
    """Accrue income from controlled industry and pay army upkeep."""
    income_rate: float = config["balance"]["income_per_industry"]
    upkeep_rate: float = config["balance"]["upkeep_per_manpower"]

    for fid in sorted(world.factions):
        fac = world.factions[fid]
        income = sum(
            p.industry * p.infrastructure * income_rate for p in _controlled_provinces(world, fid)
        )
        upkeep = sum(
            army.manpower * upkeep_rate
            for army in world.armies.values()
            if army.faction_id == fid
        )
        fac.treasury = max(0.0, fac.treasury + income - upkeep)


def update_recruitment(world: WorldState, rng: random.Random, config: dict[str, Any]) -> None:
    """Draw recruits toward the mobilization ceiling, slowed by exhaustion."""
    rate: float = config["balance"]["base_recruitment_rate"]
    ceiling: float = config["balance"]["mobilization_ceiling"]

    for fid in sorted(world.factions):
        fac = world.factions[fid]
        population = sum(p.population for p in _controlled_provinces(world, fid))
        cap = population * ceiling
        headroom = max(0.0, cap - fac.manpower)
        recruits = headroom * rate * (1.0 - fac.exhaustion)
        fac.manpower = max(0, int(fac.manpower + recruits))
