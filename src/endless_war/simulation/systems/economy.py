"""Economy and manpower.

Recruitment fills the gap between the current pool and a population-derived
ceiling, so it converges rather than growing without bound (docs/simulation-notes.md,
"avoid exponential snowballing").
"""

from __future__ import annotations

import random
from typing import Any

from endless_war.domain.models import Army, WorldState


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
        # Men already in the field count against the ceiling too. Counting only
        # the pool let reinforcement drain it into armies while recruitment
        # refilled it: 48M of 48.6M people under arms by year 30 (final review).
        fielded = sum(a.manpower for a in world.armies.values() if a.faction_id == fid)
        headroom = max(0.0, cap - fac.manpower - fielded)
        recruits = headroom * rate * (1.0 - fac.exhaustion)
        fac.manpower = max(0, int(fac.manpower + recruits))


def reinforce_armies(world: WorldState, config: dict[str, Any]) -> None:
    """Move reserves into the field: reinforce supplied armies, replace lost ones.

    Before this, armies destroyed in battle were never replaced: at seed 99 a
    faction held 29 provinces and a million reserves with no army at all, and
    the map froze as every side bled its field armies away.
    """
    balance = config["balance"]
    rate: float = balance["reinforcement_rate_per_tick"]
    min_armies: int = balance["min_field_armies"]
    new_share: float = balance["new_army_share"]
    low: float = balance["low_supply_threshold"]

    for fid in sorted(world.factions):
        fac = world.factions[fid]
        if fac.eliminated or fac.manpower <= 0:
            continue
        mine = [world.armies[aid] for aid in sorted(world.armies) if world.armies[aid].faction_id == fid]
        supplied = [
            a for a in mine
            if world.provinces[a.province_id].controller_faction_id == fid
            and world.provinces[a.province_id].supply_value >= low
        ]
        if supplied:
            each = int(fac.manpower * rate) // len(supplied)
            for army in supplied:
                army.manpower += each
                fac.manpower -= each
        if len(mine) >= min_armies:
            continue
        size = int(fac.manpower * new_share)
        if size < 5_000:
            continue
        capital = world.provinces.get(fac.capital_province_id)
        if capital is not None and capital.controller_faction_id == fid and capital.supply_value >= low:
            home = capital.id
        else:
            options = [
                p for p in sorted(world.provinces)
                if world.provinces[p].controller_faction_id == fid
                and world.provinces[p].supply_value >= low
            ]
            if not options:
                continue
            home = max(options, key=lambda p: (world.provinces[p].supply_value, -p))
        new_id = max(world.armies, default=-1) + 1
        world.armies[new_id] = Army(
            id=new_id, faction_id=fid, province_id=home, manpower=size,
            equipment=0.7, morale=0.7, organization=0.8, training=0.5,
        )
        fac.manpower -= size
