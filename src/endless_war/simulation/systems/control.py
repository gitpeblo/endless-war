"""Occupation, retreat, and army cleanup.

Control changes here; ownership does not. During a war an occupier only
controls what it takes; when the war ends, `diplomacy._settle` makes occupied
land the occupier's, unless the owner is still at war with it over it.
"""

from __future__ import annotations

import random
from typing import Any

from endless_war.domain.models import WorldState
from endless_war.simulation.systems.garrison import garrison_broken
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

    ticks_needed: int = config["balance"]["occupation_ticks"]
    for pid in sorted(world.provinces):
        province = world.provinces[pid]
        present = [a for a in armies_in(world, pid) if a.manpower > 0]
        occupiers = {a.faction_id for a in present}
        current = province.controller_faction_id
        if len(occupiers) != 1:
            province.occupation = None  # empty, or still contested
            continue
        occupier = next(iter(occupiers))
        if occupier == current or (
            current is not None and occupier not in world.factions[current].at_war_with
        ):
            province.occupation = None
            continue
        if not garrison_broken(province, config):
            province.occupation = None  # the garrison still holds; fight it first
            continue
        # A capture takes `occupation_ticks` of holding the province alone and
        # uninterrupted; leaving or being contested resets it. Before this, an
        # army walking in captured at once, so two armies trading an empty
        # province produced 620 captures from 60 battles (seed 42).
        held = 1
        if province.occupation is not None and province.occupation[0] == occupier:
            held = province.occupation[1] + 1
        if held < ticks_needed:
            province.occupation = (occupier, held)
            continue
        province.occupation = None
        captures.append(
            {"province_id": pid, "from_faction": current, "to_faction": occupier}
        )
        province.controller_faction_id = occupier

    for aid in [aid for aid in sorted(world.armies) if world.armies[aid].manpower <= 0]:
        del world.armies[aid]

    return captures


def _broken(army, config: dict[str, Any]) -> bool:
    return (
        army.organization < config["balance"]["broken_organization"]
        or army.morale < config["balance"]["broken_morale"]
    )


def surrender_trapped_armies(world: WorldState, config: dict[str, Any]) -> list[dict[str, Any]]:
    """Remove broken armies that share a province with an unbroken enemy and cannot retreat.

    Without this, a broken army with no friendly neighbour stood forever: it
    could not fight, recover or be destroyed (docs/decisions.md, 2026-09-23,
    "absorbing state"). Its men count as its faction's casualties. Every army
    is judged before any is removed, so the outcome does not depend on army
    order, and nobody surrenders to an enemy that is itself broken.
    """
    doomed = []
    for aid in sorted(world.armies):
        army = world.armies[aid]
        if not _broken(army, config):
            continue
        at_war = world.factions[army.faction_id].at_war_with
        captor_here = any(
            other.province_id == army.province_id and other.faction_id in at_war
            and other.manpower > 0 and not _broken(other, config)
            for other in world.armies.values()
        )
        if not captor_here:
            continue
        way_out = any(
            world.provinces[n].controller_faction_id == army.faction_id
            for n in world.provinces[army.province_id].neighbors
        )
        if not way_out:
            doomed.append(aid)
    records: list[dict[str, Any]] = []
    for aid in doomed:
        army = world.armies.pop(aid)
        world.factions[army.faction_id].casualties += army.manpower
        records.append({"kind": "surrender", "province_id": army.province_id,
                        "faction": army.faction_id, "men": army.manpower})
    return records


def disband_stranded_armies(world: WorldState, config: dict[str, Any]) -> None:
    """Send broken armies that can never recover back to the reserve pool.

    A broken army on unsupplied ground with no route over its own land to a
    supplied province, and no enemy beside it, sat at zero organization for
    ever (final review; a consequence of the kept no-fallback-supply rule).
    """
    low: float = config["balance"]["low_supply_threshold"]
    for aid in sorted(world.armies):
        army = world.armies[aid]
        if not _broken(army, config) or world.provinces[army.province_id].supply_value >= low:
            continue
        at_war = world.factions[army.faction_id].at_war_with
        if any(o.province_id == army.province_id and o.faction_id in at_war for o in world.armies.values()):
            continue  # an enemy is here: surrender or battle decides it
        seen = {army.province_id}
        frontier = [army.province_id]
        reachable = False
        while frontier and not reachable:
            nxt = []
            for pid in frontier:
                for nid in sorted(world.provinces[pid].neighbors):
                    if nid in seen or world.provinces[nid].controller_faction_id != army.faction_id:
                        continue
                    if world.provinces[nid].supply_value >= low:
                        reachable = True
                        break
                    seen.add(nid)
                    nxt.append(nid)
                if reachable:
                    break
            frontier = nxt
        if not reachable:
            world.factions[army.faction_id].manpower += army.manpower
            del world.armies[aid]
