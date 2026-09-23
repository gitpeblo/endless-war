"""Strategic AI.

One decision per army per tick, from local information only: withdraw when
broken, attack the weakest adjacent hostile province, otherwise reinforce a
threatened friendly border province. No global planner — fronts emerge.
"""

from __future__ import annotations

import random
from typing import Any

from endless_war.domain.models import Army, WorldState

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


def choose_strategic_actions(
    world: WorldState, rng: random.Random, config: dict[str, Any]
) -> None:
    """Set `destination_id` and `stance` for every army."""
    broken_org: float = config["balance"]["broken_organization"]
    broken_mor: float = config["balance"]["broken_morale"]
    attack_ratio: float = config["balance"]["attack_strength_ratio"]
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
        threatened = [
            pid for pid in friendly
            if any(
                world.provinces[n].controller_faction_id
                in world.factions[army.faction_id].at_war_with
                for n in world.provinces[pid].neighbors
            )
        ]
        if threatened:
            army.destination_id = sorted(threatened)[0]
