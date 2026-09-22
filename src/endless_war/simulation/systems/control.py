"""Occupation, retreat, and army cleanup.

Control changes; ownership does not. Keeping `owner_faction_id` fixed is what
lets later work model liberation, resistance, and war-goal evaluation.
"""

from __future__ import annotations

import random
from typing import Any

from endless_war.domain.models import WorldState
from endless_war.simulation.systems.movement import armies_in

OCCUPIED_SUPPLY_PENALTY = 0.5


def apply_control_changes(
    world: WorldState,
    rng: random.Random,
    config: dict[str, Any],
    battle_records: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Transfer control of undefended provinces, retreat broken armies, cull the dead."""
    captures: list[dict[str, Any]] = []

    for record in battle_records:
        if not record["attacker_broke"]:
            continue
        province_id = record["province_id"]
        for army in armies_in(world, province_id):
            if army.faction_id != record["attacker_faction"]:
                continue
            friendly = [
                n for n in world.provinces[province_id].neighbors
                if world.provinces[n].controller_faction_id == army.faction_id
            ]
            if friendly:
                army.province_id = friendly[0]
                army.destination_id = None

    for pid in sorted(world.provinces):
        province = world.provinces[pid]
        present = [a for a in armies_in(world, pid) if a.manpower > 0]
        if not present:
            continue
        occupiers = {a.faction_id for a in present}
        if len(occupiers) != 1:
            continue
        occupier = next(iter(occupiers))
        current = province.controller_faction_id
        if occupier == current:
            continue
        if current is not None and occupier not in world.factions[current].at_war_with:
            continue
        captures.append(
            {"province_id": pid, "from_faction": current, "to_faction": occupier}
        )
        province.controller_faction_id = occupier
        province.supply_value *= OCCUPIED_SUPPLY_PENALTY

    for aid in [aid for aid in sorted(world.armies) if world.armies[aid].manpower <= 0]:
        del world.armies[aid]

    return captures
