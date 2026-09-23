"""Battle resolution.

docs/simulation-notes.md asks for bounded, explainable, testable formulas that
stay stable over long simulations. Power is combined multiplicatively from
normalized factors; losses are driven by each side's SHARE of combined power,
which keeps every per-tick rate on [0, 2 x base_casualty_rate].
"""

from __future__ import annotations

import random
from typing import Any

from endless_war.domain.models import Army, WorldState
from endless_war.simulation.systems import clamp
from endless_war.simulation.systems.movement import armies_in, hostile_armies_in


def effective_power(
    army: Army,
    world: WorldState,
    defending: bool,
    terrain_defence: dict[str, float],
) -> float:
    """Combat power from normalized factors. Zero for an army with no men.

    The quality coefficients below stay in code on purpose: they are the shape
    of the model, not balance dials, and moving them to config would invite
    tuning that silently changes what "power" means.
    """
    if army.manpower <= 0:
        return 0.0
    province = world.provinces[army.province_id]
    quality = (
        clamp(army.equipment)
        * (0.35 + 0.65 * clamp(army.morale))
        * (0.30 + 0.70 * clamp(army.organization))
        * (0.50 + 0.50 * clamp(army.training))
        * (0.40 + 0.60 * clamp(army.supply))
    )
    terrain = terrain_defence.get(province.terrain, 1.0) if defending else 1.0
    return army.manpower * quality * terrain


def _battle_provinces(world: WorldState) -> list[int]:
    """Provinces holding armies of two mutually hostile factions."""
    contested: list[int] = []
    for pid in sorted(world.provinces):
        present = armies_in(world, pid)
        factions = {a.faction_id for a in present if a.manpower > 0}
        if len(factions) < 2:
            continue
        for fid in sorted(factions):
            if world.factions[fid].at_war_with & (factions - {fid}):
                contested.append(pid)
                break
    return contested


def resolve_battles(
    world: WorldState, rng: random.Random, config: dict[str, Any]
) -> list[dict[str, Any]]:
    """Resolve one tick of combat in every contested province."""
    base: float = config["balance"]["base_casualty_rate"]
    terrain_defence: dict[str, float] = config["balance"]["terrain_defence"]
    attacker_break: float = config["balance"]["attacker_break_organization"]
    defender_break: float = config["balance"]["defender_break_organization"]
    records: list[dict[str, Any]] = []

    for pid in _battle_provinces(world):
        province = world.provinces[pid]
        present = [a for a in armies_in(world, pid) if a.manpower > 0]
        defender_faction = province.controller_faction_id
        defenders = [a for a in present if a.faction_id == defender_faction]
        attackers = [
            a for a in hostile_armies_in(world, pid, defender_faction) if a.manpower > 0
        ]
        if not defenders or not attackers:
            continue
        attacker_faction = attackers[0].faction_id

        att_power = sum(
            effective_power(a, world, False, terrain_defence) for a in attackers
        )
        def_power = sum(
            effective_power(d, world, True, terrain_defence) for d in defenders
        )
        att_power *= rng.uniform(0.9, 1.1)
        def_power *= rng.uniform(0.9, 1.1)
        total = att_power + def_power
        if total <= 0:
            continue

        attacker_share = att_power / total          # bounded [0, 1]
        attacker_rate = base * 2.0 * (1.0 - attacker_share)
        defender_rate = base * 2.0 * attacker_share

        attacker_losses = _apply_losses(attackers, attacker_rate)
        defender_losses = _apply_losses(defenders, defender_rate)

        world.factions[attacker_faction].casualties += attacker_losses
        world.factions[defender_faction].casualties += defender_losses

        attacker_broke = all(a.organization <= attacker_break for a in attackers)
        defender_broke = all(d.organization <= defender_break for d in defenders)

        records.append({
            "province_id": pid,
            "attacker_faction": attacker_faction,
            "defender_faction": defender_faction,
            "attacker_losses": attacker_losses,
            "defender_losses": defender_losses,
            "attacker_broke": attacker_broke,
            "defender_broke": defender_broke,
        })
    return records


def _apply_losses(armies: list[Army], rate: float) -> int:
    """Apply a per-tick casualty rate, returning total men lost."""
    lost = 0
    for army in armies:
        casualties = int(army.manpower * rate)
        army.manpower = max(0, army.manpower - casualties)
        army.organization = clamp(army.organization - rate * 2.5)
        army.morale = clamp(army.morale - rate * 1.2)
        army.equipment = clamp(army.equipment - rate * 0.4)
        lost += casualties
    return lost
