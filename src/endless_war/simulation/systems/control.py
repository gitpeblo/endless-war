"""Occupation, retreat, and army cleanup.

Control changes; ownership does not. Keeping `owner_faction_id` fixed is what
lets later work model liberation, resistance, and war-goal evaluation.
"""

from __future__ import annotations

import random
from typing import Any

from endless_war.domain.models import WorldState
from endless_war.simulation.systems.movement import armies_in


def _retreat(world: WorldState, province_id: int, faction_id: int) -> None:
    """Pull `faction_id`'s armies out of `province_id` to an adjacent friendly province.

    A force with nowhere friendly to fall back to stands where it is.
    """
    friendly = [
        nid for nid in world.provinces[province_id].neighbors
        if world.provinces[nid].controller_faction_id == faction_id
    ]
    if not friendly:
        return
    for army in armies_in(world, province_id):
        if army.faction_id == faction_id:
            army.province_id = friendly[0]
            army.destination_id = None


def apply_control_changes(
    world: WorldState,
    rng: random.Random,
    config: dict[str, Any],
    battle_records: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Transfer control of undefended provinces, retreat broken armies, cull the dead."""
    captures: list[dict[str, Any]] = []

    for record in battle_records:
        # Both sides fall back when broken. Defender retreat alone froze the
        # fronts (docs/decisions.md, 2026-09-23); it now comes with strength-
        # based attack decisions and routing, as that note recommended.
        if record["attacker_broke"]:
            _retreat(world, record["province_id"], record["attacker_faction"])
        if record["defender_broke"]:
            _retreat(world, record["province_id"], record["defender_faction"])

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

    for aid in [aid for aid in sorted(world.armies) if world.armies[aid].manpower <= 0]:
        del world.armies[aid]

    return captures


def surrender_trapped_armies(world: WorldState, config: dict[str, Any]) -> list[dict[str, Any]]:
    """Remove broken armies that share a province with an enemy and cannot retreat.

    Without this, a broken army with no friendly neighbour stood forever: it
    could not fight, recover or be destroyed (docs/decisions.md, 2026-09-23,
    "absorbing state"). Its men count as its faction's casualties.
    """
    broken_org: float = config["balance"]["broken_organization"]
    broken_mor: float = config["balance"]["broken_morale"]
    records: list[dict[str, Any]] = []
    for aid in sorted(world.armies):
        army = world.armies[aid]
        if army.organization >= broken_org and army.morale >= broken_mor:
            continue
        at_war = world.factions[army.faction_id].at_war_with
        enemy_here = any(
            other.province_id == army.province_id and other.faction_id in at_war
            and other.manpower > 0
            for other in world.armies.values()
        )
        if not enemy_here:
            continue
        way_out = any(
            world.provinces[n].controller_faction_id == army.faction_id
            for n in world.provinces[army.province_id].neighbors
        )
        if way_out:
            continue
        world.factions[army.faction_id].casualties += army.manpower
        records.append({"kind": "surrender", "province_id": army.province_id,
                        "faction": army.faction_id, "men": army.manpower})
        del world.armies[aid]
    return records
