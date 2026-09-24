"""Strategic AI.

One decision per army per tick: withdraw when broken, attack the weakest
adjacent hostile province, otherwise march toward the front sector that needs
it most. There is no global planner; fronts emerge from these choices.
"""

from __future__ import annotations

import random
from collections import deque
from typing import Any

from endless_war.domain.models import Army, WorldState
from endless_war.simulation.systems.battle import effective_power

def _hostile_neighbours(world: WorldState, army: Army) -> list[int]:
    at_war = world.factions[army.faction_id].at_war_with
    return [
        nid for nid in world.provinces[army.province_id].neighbors
        if world.provinces[nid].controller_faction_id in at_war
    ]


def _friendly_neighbours(world: WorldState, army: Army) -> list[int]:
    return [
        nid for nid in world.provinces[army.province_id].neighbors
        if world.provinces[nid].controller_faction_id == army.faction_id
    ]


def _standing_somewhere_safe(world: WorldState, army: Army) -> bool:
    """True when nothing hostile is adjacent to, or standing in, the army's province.

    A broken army in its own rear has nothing to withdraw from, and withdrawing
    is what keeps it from recovering. See docs/decisions.md, 2026-09-23.
    """
    at_war = world.factions[army.faction_id].at_war_with
    if not at_war:
        return True
    here = world.provinces[army.province_id]
    if any(world.provinces[nid].controller_faction_id in at_war for nid in here.neighbors):
        return False
    return not any(
        other.province_id == army.province_id and other.faction_id in at_war
        for other in world.armies.values()
    )


def _defenders_in(world: WorldState, province_id: int, faction_id: int) -> int:
    return sum(
        a.manpower for a in world.armies.values()
        if a.province_id == province_id and a.faction_id != faction_id
    )


def _front_pressure(
    world: WorldState, faction_id: int, terrain: dict[str, float]
) -> dict[int, float]:
    """Each front province's enemy strength next door, minus own strength in it.

    A front province is one this faction controls that borders a province of a
    faction it is at war with. Higher pressure is where reinforcement matters.
    """
    at_war = world.factions[faction_id].at_war_with
    if not at_war:
        return {}
    pressure: dict[int, float] = {}
    for pid in sorted(world.provinces):
        province = world.provinces[pid]
        if province.controller_faction_id != faction_id:
            continue
        hostile = {
            n for n in province.neighbors
            if world.provinces[n].controller_faction_id in at_war
        }
        if not hostile:
            continue
        value = 0.0
        for aid in sorted(world.armies):
            a = world.armies[aid]
            if a.province_id in hostile and a.faction_id in at_war:
                value += effective_power(a, world, False, terrain)
            elif a.province_id == pid and a.faction_id == faction_id:
                value -= effective_power(a, world, True, terrain)
        pressure[pid] = value
    return pressure


def _route(
    world: WorldState, army: Army, pressure: dict[int, float], terrain: dict[str, float]
) -> int | None:
    """One step toward the reachable front with the most pressure.

    Breadth-first over the army's own faction's provinces, neighbours in
    sorted order, so paths are deterministic. The chosen front's pressure is
    reduced by this army's strength, so the next idle army is sent elsewhere.
    """
    if not pressure:
        return None
    start = army.province_id
    parent: dict[int, int | None] = {start: None}
    distance = {start: 0}
    queue = deque([start])
    while queue:
        pid = queue.popleft()
        for nid in sorted(world.provinces[pid].neighbors):
            if nid in parent or world.provinces[nid].controller_faction_id != army.faction_id:
                continue
            parent[nid] = pid
            distance[nid] = distance[pid] + 1
            queue.append(nid)
    reachable = [pid for pid in pressure if pid in distance]
    if not reachable:
        return None
    target = min(reachable, key=lambda pid: (-pressure[pid], distance[pid], pid))
    pressure[target] -= effective_power(army, world, False, terrain)
    if target == start:
        return None
    step = target
    while parent[step] != start:
        step = parent[step]
    return step


def choose_strategic_actions(
    world: WorldState, rng: random.Random, config: dict[str, Any]
) -> None:
    """Set `destination_id` and `stance` for every army."""
    broken_org: float = config["balance"]["broken_organization"]
    broken_mor: float = config["balance"]["broken_morale"]
    attack_ratio: float = config["balance"]["attack_strength_ratio"]
    terrain: dict[str, float] = config["balance"]["terrain_defence"]
    fronts: dict[int, dict[int, float]] = {}  # per faction, computed once per tick
    for aid in sorted(world.armies):
        army = world.armies[aid]
        army.destination_id = None

        broken = army.organization < broken_org or army.morale < broken_mor
        friendly = _friendly_neighbours(world, army)
        if broken:
            army.stance = "withdrawal"
            if friendly and not _standing_somewhere_safe(world, army):
                friendly.sort(key=lambda pid: -world.provinces[pid].supply_value)
                army.destination_id = friendly[0]
            continue

        hostile = _hostile_neighbours(world, army)
        if hostile:
            hostile.sort(key=lambda pid: (_defenders_in(world, pid, army.faction_id), pid))
            weakest = hostile[0]
            if _defenders_in(world, weakest, army.faction_id) < army.manpower * attack_ratio:
                army.stance = "aggressive"
                army.destination_id = weakest
            else:
                army.stance = "defensive"
            continue

        army.stance = "balanced"
        # Not at the front: march toward the sector that needs it most. The
        # old rule sent every idle army to the lowest-numbered threatened
        # province, so reserves stacked on one spot and most of the front was
        # never attacked (the user's "isolated cells never get conquered").
        if army.faction_id not in fronts:
            fronts[army.faction_id] = _front_pressure(world, army.faction_id, terrain)
        army.destination_id = _route(world, army, fronts[army.faction_id], terrain)
