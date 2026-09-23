"""Strategic AI.

One decision per army per tick, from local information only: withdraw when
broken, attack the weakest adjacent hostile province, otherwise reinforce a
threatened friendly border province. No global planner — fronts emerge.
"""

from __future__ import annotations

import random
from typing import Any

from endless_war.domain.models import Army, WorldState

BROKEN_ORGANIZATION = 0.30
BROKEN_MORALE = 0.25


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


def _defenders_in(world: WorldState, province_id: int, faction_id: int) -> int:
    return sum(
        a.manpower for a in world.armies.values()
        if a.province_id == province_id and a.faction_id != faction_id
    )


def choose_strategic_actions(
    world: WorldState, rng: random.Random, config: dict[str, Any]
) -> None:
    """Set `destination_id` and `stance` for every army."""
    for aid in sorted(world.armies):
        army = world.armies[aid]
        army.destination_id = None

        broken = army.organization < BROKEN_ORGANIZATION or army.morale < BROKEN_MORALE
        friendly = _friendly_neighbours(world, army)
        if broken:
            army.stance = "withdrawal"
            if friendly:
                friendly.sort(key=lambda pid: -world.provinces[pid].supply_value)
                army.destination_id = friendly[0]
            continue

        hostile = _hostile_neighbours(world, army)
        if hostile:
            hostile.sort(key=lambda pid: (_defenders_in(world, pid, army.faction_id), pid))
            weakest = hostile[0]
            if _defenders_in(world, weakest, army.faction_id) < army.manpower * 1.2:
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
