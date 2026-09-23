"""Army movement, supply draw, and recovery.

An army advances at most one province per tick. Moving into a province held by
a hostile faction IS the attack: the army enters, and the battle system — which
runs later in the same tick — resolves the engagement there, with the province
controller's armies as defenders. A broken attacker is pushed back out by the
occupation system. See docs/decisions.md, 2026-09-23, "the contact rule".
"""

from __future__ import annotations

import random
from typing import Any

from endless_war.domain.models import Army, WorldState
from endless_war.simulation.systems import clamp


def armies_in(world: WorldState, province_id: int) -> list[Army]:
    """Every army standing in `province_id`, in deterministic id order."""
    return [world.armies[aid] for aid in sorted(world.armies)
            if world.armies[aid].province_id == province_id]


def hostile_armies_in(world: WorldState, province_id: int, faction_id: int) -> list[Army]:
    """Armies in `province_id` belonging to a faction at war with `faction_id`."""
    at_war = world.factions[faction_id].at_war_with
    return [a for a in armies_in(world, province_id) if a.faction_id in at_war]


def update_movement(world: WorldState, rng: random.Random, config: dict[str, Any]) -> None:
    """Draw supply, recover, then advance one province toward the destination."""
    org_recovery: float = config["balance"]["organization_recovery_per_tick"]
    morale_recovery: float = config["balance"]["morale_recovery_per_tick"]

    for aid in sorted(world.armies):
        army = world.armies[aid]
        here = world.provinces[army.province_id]

        # Armies draw the supply delivered to the province they occupy.
        army.supply = clamp(army.supply + (here.supply_value - army.supply) * 0.5)

        if army.supply < 0.35:
            army.organization = clamp(army.organization - (0.35 - army.supply) * 0.1)
            army.morale = clamp(army.morale - (0.35 - army.supply) * 0.05)
        elif army.destination_id is None:
            army.organization = clamp(army.organization + org_recovery * army.supply)
            army.morale = clamp(army.morale + morale_recovery * army.supply)

        if army.destination_id is None:
            continue

        target_id = army.destination_id
        if target_id not in here.neighbors:
            army.destination_id = None
            continue
        if army.organization < 0.15:
            army.destination_id = None
            continue

        army.province_id = target_id
        army.destination_id = None
        army.organization = clamp(army.organization - 0.03)
